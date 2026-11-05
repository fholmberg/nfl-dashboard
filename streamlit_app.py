"""NFL decision-support dashboard (private).

Reads the semantic layer published by elt-pipeline. Presents data for the
user to make their own decision — it does not recommend bets.

Pages: Today (today's games with lines/form), Team Form (season explorer),
Trends (per-team trends from game results).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data import load

st.set_page_config(page_title="NFL Matchup Board", layout="wide")


def require_password() -> bool:
    expected = ""
    try:
        expected = str(st.secrets.get("app_password", ""))
    except Exception:
        pass
    if not expected:
        st.error("App password is not configured in Streamlit secrets.")
        return False
    if st.session_state.get("authed"):
        return True
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Enter") and pw == expected:
            st.session_state["authed"] = True
            st.rerun()
        elif pw:
            st.error("Incorrect password.")
    return False


def pct(x) -> str:
    return "—" if pd.isna(x) else f"{float(x) * 100:.0f}%"


def consensus_bar(label: str, share: float, color: str = "#4c78a8") -> None:
    if pd.isna(share):
        st.caption(f"{label}: no consensus data")
        return
    st.markdown(f"{label} — **{pct(share)}**")
    st.progress(min(max(float(share), 0.0), 1.0))


def band_label(share: float) -> str:
    if pd.isna(share):
        return "—"
    for edge, label in [(0.8, "80% +"), (0.7, "70-80%"), (0.6, "60-70%"), (0.5, "50-60%"),
                        (0.4, "40-50%"), (0.3, "30-40%"), (0.2, "20-30%")]:
        if share >= edge:
            return label
    return "Under 20%"


def _band_row(bands: pd.DataFrame, team: str, season: int, band: str) -> str:
    r = bands[(bands["team_name"] == team) & (bands["season"] == season) & (bands["consensus_band"] == band)]
    if r.empty:
        return "no history"
    r = r.iloc[0]
    return f"{pct(r.cover_pct)} cover (n={int(r.games)}), {pct(r.win_pct)} won"


def band_panel(g) -> str:
    """Tonight's consensus-band context per team (this season + all-time)."""
    bands = load("spread_bands")
    bands = bands[bands["scope"] == "Team"]
    lines = ["**When a team sits in tonight's consensus band, how often has it covered?**", ""]
    for team, share in ((g.away_team, g.away_consensus_pct), (g.home_team, g.home_consensus_pct)):
        band = band_label(share)
        season_txt = _band_row(bands, team, int(g.season), band)
        all_txt = _band_row(bands, team, 0, band)
        lines.append(f"- **{team}** — {pct(share)} consensus tonight (band **{band}**): "
                     f"this season {season_txt}; all seasons {all_txt}.")
    totals = load("total_bands")
    side = "Over" if (pd.notna(g.over_consensus_pct) and g.over_consensus_pct >= 0.5) else "Under"
    share = g.over_consensus_pct if side == "Over" else g.under_consensus_pct
    band = band_label(share) if pd.notna(share) else "—"
    league = totals[(totals["scope"] == "League") & (totals["totals_consensus_side"] == side) & (totals["consensus_band"] == band)]
    bits = []
    for season, label in ((int(g.season), "this season"), (0, "all seasons")):
        r = league[league["season"] == season]
        bits.append(f"{label}: {pct(r.iloc[0].hit_pct) if not r.empty else '—'} (n={int(r.iloc[0].games) if not r.empty else 0})")
    lines.append(f"- **Total** — consensus favors the **{side}** at {pct(share)} (band **{band}**): league hit rate {'; '.join(bits)}.")
    return "\n".join(lines)


def page_today() -> None:
    st.header("Today's games")
    df = load("upcoming")
    if df.empty:
        st.info("No games scheduled today. The board refreshes on the pipeline schedule (Sun / Mon / Thu, Pacific).")
        return
    for _, g in df.iterrows():
        st.subheader(f"{g.away_team} @ {g.home_team} — {g.game_date:%a %b %d}")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**{g.away_team}** ({g.away_record_display}, rank #{int(g.away_season_rank)})")
            st.metric("Away spread (pts)", g.away_spread_points)
            consensus_bar(f"Consensus on {g.away_team}", g.away_consensus_pct)
        with c2:
            st.markdown(f"**{g.home_team}** ({g.home_record_display}, rank #{int(g.home_season_rank)})")
            st.metric("Home spread (pts)", g.home_spread_points)
            consensus_bar(f"Consensus on {g.home_team}", g.home_consensus_pct)
        with c3:
            st.metric("Total (over/under, pts)", g.totals_line_points)
            consensus_bar("Consensus over", g.over_consensus_pct)
            consensus_bar("Consensus under", g.under_consensus_pct)
        form = pd.DataFrame(
            {
                "": ["Win %", "ATS win %", "Over %", "Avg points scored"],
                g.away_team: [pct(g.away_win_pct), pct(g.away_against_the_spread_win_pct), pct(g.away_over_pct),
                              f"{g.away_avg_points_scored:.1f}"],
                g.home_team: [pct(g.home_win_pct), pct(g.home_against_the_spread_win_pct), pct(g.home_over_pct),
                              f"{g.home_avg_points_scored:.1f}"],
            }
        )
        st.dataframe(form, hide_index=True, width="stretch")
        st.markdown(band_panel(g))
        st.caption("ATS = against the spread. Band = the team's share of consensus bets tonight; "
                   "cover % = how often teams in that band have covered (pushes excluded), win % = outright wins.")


def page_consensus() -> None:
    st.header("Consensus — does the crowd cover?")
    st.caption(
        "Rates are conditional on a team's own consensus share (mirrored bands). "
        "Cover % excludes pushes; win % is outright. Small n means weak evidence — "
        "check the games column before trusting a rate."
    )
    bands = load("spread_bands")
    season_pick = st.selectbox("Season (0 = all seasons)", [2026, 0] + sorted(
        [int(s) for s in bands["season"].unique() if s not in (0, 2026)], reverse=True))
    league = bands[(bands["scope"] == "League") & (bands["season"] == season_pick)]
    for role in ("Favorite", "Underdog"):
        st.subheader(f"League — consensus {role.lower()}s")
        d = league[league["consensus_role"] == role].sort_values("consensus_band_order")
        st.dataframe(d[["consensus_band", "games", "covers", "pushes", "cover_pct", "game_wins", "win_pct"]],
                     hide_index=True, width="stretch")
        st.bar_chart(d.set_index("consensus_band")["cover_pct"], height=220)

    st.subheader("Team splits")
    team = st.selectbox("Team", sorted(bands[bands["scope"] == "Team"]["team_name"].dropna().unique()))
    d = bands[(bands["scope"] == "Team") & (bands["team_name"] == team) & (bands["season"] == season_pick)]
    st.dataframe(d.sort_values("consensus_band_order")[
        ["consensus_band", "consensus_role", "games", "covers", "cover_pct", "game_wins", "win_pct"]],
        hide_index=True, width="stretch")

    st.subheader("Totals — favored side hit rate")
    totals = load("total_bands")
    d = totals[(totals["scope"] == "League") & (totals["season"] == season_pick)]
    for side in ("Over", "Under"):
        dd = d[d["totals_consensus_side"] == side].sort_values("consensus_band_order")
        if not dd.empty:
            st.markdown(f"**Consensus on the {side}**")
            st.dataframe(dd[["consensus_band", "games", "hits", "pushes", "hit_pct"]],
                         hide_index=True, width="stretch")


def page_form() -> None:
    st.header("Team form")
    form = load("form")
    seasons = sorted(form["season"].unique(), reverse=True)
    season = st.selectbox("Season", seasons, index=0)
    d = form[form["season"] == season].sort_values("season_rank")
    st.dataframe(
        d[["season_rank", "team_name", "record_display", "win_pct", "against_the_spread_win_pct",
           "over_pct", "avg_points_scored", "avg_points_allowed", "games_with_market"]],
        hide_index=True, width="stretch",
    )
    team = st.selectbox("Team detail", d["team_name"].tolist())
    row = d[d["team_name"] == team].iloc[0]
    a, b, c, dd = st.columns(4)
    a.metric("Record", row.record_display)
    b.metric("Win %", pct(row.win_pct))
    c.metric("ATS win %", pct(row.against_the_spread_win_pct))
    dd.metric("Over %", pct(row.over_pct))
    st.bar_chart(d.set_index("team_name")["win_pct"], height=260)


def page_trends() -> None:
    st.header("Trends")
    res = load("results")
    form = load("form")
    team = st.selectbox("Team", sorted(form["team_name"].unique()))
    seasons = sorted(res["season"].unique(), reverse=True)
    season = st.selectbox("Season ", seasons, index=0)
    played = res[(res["season"] == season) & ((res["home_team"] == team) | (res["away_team"] == team))].copy()
    if played.empty:
        st.info("No played games for that selection.")
        return
    played["points_scored"] = played.apply(lambda r: r.home_score if r.home_team == team else r.away_score, axis=1)
    played["points_allowed"] = played.apply(lambda r: r.away_score if r.home_team == team else r.home_score, axis=1)
    played = played.sort_values("game_date")
    played["game"] = range(1, len(played) + 1)
    x, y, z = st.columns(3)
    x.metric("Games", len(played))
    y.metric("Avg scored", f"{played.points_scored.mean():.1f}")
    z.metric("Avg allowed", f"{played.points_allowed.mean():.1f}")
    st.caption("Points per game (in game order)")
    st.line_chart(played.set_index("game")[["points_scored", "points_allowed"]], height=260)
    st.caption("Game totals vs the totals line")
    chart = played.set_index("game")[["total_points", "totals_line_points"]]
    st.line_chart(chart, height=240)
    st.dataframe(
        played[["game_date", "week", "home_team", "away_team", "home_score", "away_score",
                "totals_line_points", "totals_result", "spread_cover_side"]],
        hide_index=True, width="stretch",
    )


if not require_password():
    st.stop()

st.title("NFL Matchup Board")
st.caption(
    "Data: nflverse + Covers via the elt-pipeline warehouse (semantic layer). "
    "For information only — this dashboard presents statistics and market data; "
    "it does not recommend bets. Lines and consensus move; verify before acting."
)

page = st.sidebar.radio("Page", ["Today", "Team Form", "Trends", "Consensus"])
{"Today": page_today, "Team Form": page_form, "Trends": page_trends, "Consensus": page_consensus}[page]()
