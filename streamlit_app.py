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
                "": ["Win %", "ATS win %", "Over %", "Avg points scored", "Consensus spread accuracy", "Consensus total accuracy"],
                g.away_team: [pct(g.away_win_pct), pct(g.away_against_the_spread_win_pct), pct(g.away_over_pct),
                              f"{g.away_avg_points_scored:.1f}", pct(g.away_consensus_spread_accuracy), pct(g.away_consensus_total_accuracy)],
                g.home_team: [pct(g.home_win_pct), pct(g.home_against_the_spread_win_pct), pct(g.home_over_pct),
                              f"{g.home_avg_points_scored:.1f}", pct(g.home_consensus_spread_accuracy), pct(g.home_consensus_total_accuracy)],
            }
        )
        st.dataframe(form, hide_index=True, width="stretch")
        st.caption("ATS = against the spread. Consensus accuracy = how often the consensus pick has been right for that team this season.")


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

page = st.sidebar.radio("Page", ["Today", "Team Form", "Trends"])
{"Today": page_today, "Team Form": page_form, "Trends": page_trends}[page]()
