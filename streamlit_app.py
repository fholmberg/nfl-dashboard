"""Matchup Board — NFL + NCAAF decision-support dashboard (private).

Presents statistics and market data from the elt-pipeline semantic layer
for users to make their own decisions. It does not recommend bets.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from data import load

st.set_page_config(page_title="Matchup Board", page_icon="🏈", layout="wide")

CSS = """
<style>
  .block-container { padding-top: 2.2rem; max-width: 1180px; }
  h1 { font-size: 2rem; letter-spacing: -0.02em; }
  h2, h3 { letter-spacing: -0.01em; }
  .team-name { font-size: 1.55rem; font-weight: 750; line-height: 1.1; }
  .team-sub { color: #9db2c3; font-size: 0.9rem; margin-top: 0.15rem; }
  .vs { font-size: 1.1rem; color: #7e93a6; text-align: center; padding-top: 0.7rem; }
  .pill { display: inline-block; padding: 0.18rem 0.6rem; border-radius: 999px;
          background: #1d2f22; color: #7bd79e; font-size: 0.82rem; font-weight: 650; }
  .duel { display: flex; height: 18px; border-radius: 6px; overflow: hidden; margin: 0.35rem 0 0.2rem; }
  .duel > div { height: 100%; }
  .cmp-row { display: grid; grid-template-columns: 1fr 130px 1fr; align-items: center; gap: 10px; margin: 0.3rem 0; }
  .cmp-label { text-align: center; color: #9db2c3; font-size: 0.82rem; }
  .bar-track { background: #22303f; height: 10px; border-radius: 5px; position: relative; }
  .bar-fill { height: 100%; border-radius: 5px; }
  .bar-val { font-size: 0.85rem; font-weight: 650; }
  .small { color: #9db2c3; font-size: 0.85rem; }
  div[data-testid="stMetric"] { background: #151f2a; border: 1px solid #22303f;
    border-radius: 10px; padding: 0.7rem 0.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

TEAM_COLORS = {
    "Cardinals": "#97233F", "Falcons": "#A71930", "Ravens": "#5e6bb8", "Bills": "#4a7fc9",
    "Panthers": "#0085CA", "Bears": "#e08a3c", "Bengals": "#FB4F14", "Browns": "#FF3C00",
    "Cowboys": "#8fa9c9", "Broncos": "#FB4F14", "Lions": "#0076B6", "Packers": "#FFB612",
    "Texans": "#e14b5a", "Colts": "#7d9cc4", "Jaguars": "#2ba8a0", "Chiefs": "#E31837",
    "Raiders": "#A5ACAF", "Chargers": "#FFC20E", "Rams": "#5a86d6", "Dolphins": "#2aa198",
    "Vikings": "#9a7fc9", "Patriots": "#5b84ae", "Saints": "#D3BC8D", "Giants": "#5b7fc0",
    "Jets": "#4f9e79", "Eagles": "#4DB8A6", "Steelers": "#FFB612", "49ers": "#d06a6a",
    "Seahawks": "#69BE28", "Buccaneers": "#D50A0A", "Titans": "#4B92DB", "Commanders": "#c9a227",
}


_PALETTE = ["#4a7fc9", "#2ba8a0", "#e08a3c", "#9a7fc9", "#e14b5a", "#69BE28",
            "#c9a227", "#5a86d6", "#d06a6a", "#4f9e79", "#8fa9c9", "#FB4F14"]


def color(team: str) -> str:
    # NFL short names have brand colors; NCAAF full names get a stable
    # per-team color from the palette.
    if team in TEAM_COLORS:
        return TEAM_COLORS[team]
    return _PALETTE[sum(ord(c) for c in str(team)) % len(_PALETTE)]


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
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.title("🏈 Matchup Board")
        with st.form("login"):
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Enter", width="stretch") and pw == expected:
                st.session_state["authed"] = True
                st.rerun()
            elif pw:
                st.error("Incorrect password.")
    return False


def pct(x) -> str:
    return "—" if pd.isna(x) else f"{float(x) * 100:.0f}%"


def band_label(share: float) -> str:
    if pd.isna(share):
        return "—"
    for edge, label in [(0.8, "80% +"), (0.7, "70-80%"), (0.6, "60-70%"), (0.5, "50-60%"),
                        (0.4, "40-50%"), (0.3, "30-40%"), (0.2, "20-30%")]:
        if share >= edge:
            return label
    return "Under 20%"


def line_bucket(abs_spread: float) -> str:
    if abs_spread == 0:
        return "Pick'em (0)"
    for edge, label in [(2.5, "0.5-2.5 pts"), (6.5, "3-6.5 pts"), (9.5, "7-9.5 pts"), (13.5, "10-13.5 pts")]:
        if abs_spread <= edge:
            return label
    return "14+ pts"


def total_bucket(line: float, sport: str = "nfl") -> str:
    if sport == "ncaaf":  # college totals run higher; mirrors fct_ncaaf_team_market_games
        if line < 45:
            return "Under 45"
        for edge, label in [(49.5, "45-49.5"), (54.5, "50-54.5"), (59.5, "55-59.5"), (64.5, "60-64.5")]:
            if line <= edge:
                return label
        return "65+"
    if line < 40:
        return "Under 40"
    for edge, label in [(43.5, "40-43.5"), (47.5, "44-47.5"), (51.5, "48-51.5"), (55.5, "52-55.5")]:
        if line <= edge:
            return label
    return "56+"


def team_block(team: str, record: str, rank_text: str, spread_pts, align: str = "left") -> None:
    st.markdown(
        f'<div style="text-align:{align}"><div class="team-name">'
        f'<span style="color:{color(team)}">●</span> {team}</div>'
        f'<div class="team-sub">{record} · {rank_text}</div></div>',
        unsafe_allow_html=True,
    )
    st.metric("Spread (pts)", f"{spread_pts:+.1f}" if pd.notna(spread_pts) else "—")


def duel_bar(away_team: str, away_share, home_team: str, home_share) -> None:
    if pd.isna(away_share) or pd.isna(home_share):
        st.caption("No consensus data for this game yet.")
        return
    a = int(round(float(away_share) * 100))
    st.markdown(
        f'<div class="duel"><div style="width:{a}%;background:{color(away_team)}"></div>'
        f'<div style="width:{100 - a}%;background:{color(home_team)}"></div></div>'
        f'<div style="display:flex;justify-content:space-between" class="small">'
        f"<span>{away_team} {a}%</span><span>betting consensus</span><span>{home_team} {100 - a}%</span></div>",
        unsafe_allow_html=True,
    )


def compare_row(label: str, away_val, home_val, away_team: str, home_team: str) -> None:
    def side(val, team, flip: bool) -> str:
        if pd.isna(val):
            return '<div class="bar-val">—</div>'
        w = int(round(float(val) * 100))
        style = f"width:{w}%;background:{color(team)};" + ("margin-left:auto;" if flip else "")
        return (f'<div style="display:flex;align-items:center;gap:8px;'
                f'{"flex-direction:row-reverse;" if flip else ""}">'
                f'<div class="bar-track" style="flex:1"><div class="bar-fill" style="{style}"></div></div>'
                f'<div class="bar-val">{pct(val)}</div></div>')

    st.markdown(
        f'<div class="cmp-row"><div>{side(away_val, away_team, True)}</div>'
        f'<div class="cmp-label">{label}</div><div>{side(home_val, home_team, False)}</div></div>',
        unsafe_allow_html=True,
    )


def _band_row(bands: pd.DataFrame, team: str, season: int, band: str) -> str:
    r = bands[(bands["team_name"] == team) & (bands["season"] == season) & (bands["consensus_band"] == band)]
    if r.empty:
        return "no history"
    r = r.iloc[0]
    return f"{pct(r.cover_pct)} cover (n={int(r.games)}), {pct(r.win_pct)} won"


def band_panel(g, sport: str = "nfl") -> str:
    bands = load("spread_bands", sport)
    team_bands = bands[bands["scope"] == "Team"]
    league_bands = bands[bands["scope"] == "League"]
    lines = ["**When a team sits in tonight's consensus band, how often has it covered?**", ""]
    for team, share in ((g.away_team, g.away_consensus_pct), (g.home_team, g.home_consensus_pct)):
        band = band_label(share)
        lines.append(f"- **{team}** — {pct(share)} consensus tonight (band **{band}**): "
                     f"this season {_band_row(team_bands, team, int(g.season), band)}; "
                     f"all seasons {_band_row(team_bands, team, 0, band)}.")
    for team, share in ((g.away_team, g.away_consensus_pct), (g.home_team, g.home_consensus_pct)):
        band = band_label(share)
        r = league_bands[(league_bands["season"] == int(g.season)) & (league_bands["consensus_band"] == band)]
        r_all = league_bands[(league_bands["season"] == 0) & (league_bands["consensus_band"] == band)]
        def fmt(r):
            return "no history" if r.empty else f"{pct(r.iloc[0].cover_pct)} cover (n={int(r.iloc[0].games)}), {pct(r.iloc[0].win_pct)} won"
        lines.append(f"- **All teams, {band} band** — this season {fmt(r)}; all seasons {fmt(r_all)}.")

    totals = load("total_bands", sport)
    side = "Over" if (pd.notna(g.over_consensus_pct) and g.over_consensus_pct >= 0.5) else "Under"
    share = g.over_consensus_pct if side == "Over" else g.under_consensus_pct
    band = band_label(share) if pd.notna(share) else "—"
    league = totals[(totals["scope"] == "League") & (totals["totals_consensus_side"] == side) & (totals["consensus_band"] == band)]
    bits = []
    for season, label in ((int(g.season), "this season"), (0, "all seasons")):
        r = league[league["season"] == season]
        bits.append(f"{label}: {pct(r.iloc[0].hit_pct) if not r.empty else '—'} (n={int(r.iloc[0].games) if not r.empty else 0})")
    lines.append(f"- **Total** — consensus favors the **{side}** at {pct(share)} (band **{band}**): league hit rate {'; '.join(bits)}.")

    sl = load("spread_line_bands", sport)
    sl = sl[sl["scope"] == "League"]
    bucket = line_bucket(abs(float(g.away_spread_points))) if pd.notna(g.away_spread_points) else "—"
    lines.append("")
    lines.append(f"**By the line — {bucket} spreads ({g.spread_favorite} favored):**")
    for role in ("Favorite", "Underdog"):
        for season, label in ((int(g.season), "this season"), (0, "all seasons")):
            r = sl[(sl["season"] == season) & (sl["spread_role"] == role) & (sl["spread_line_bucket"] == bucket)]
            if not r.empty:
                r = r.iloc[0]
                lines.append(f"- {role}s, {label}: {pct(r.cover_pct)} cover (n={int(r.games)}), {pct(r.win_pct)} won outright.")
    tl = load("total_line_bands", sport)
    tl = tl[tl["scope"] == "League"]
    tbucket = total_bucket(float(g.totals_line_points), sport) if pd.notna(g.totals_line_points) else "—"
    for season, label in ((int(g.season), "this season"), (0, "all seasons")):
        r = tl[(tl["season"] == season) & (tl["totals_line_bucket"] == tbucket)]
        if not r.empty:
            r = r.iloc[0]
            lines.append(f"- Totals line {tbucket} ({g.totals_line_points}), {label}: over hit {pct(r.over_pct)} (n={int(r.games)}).")
    return "\n".join(lines)


def page_today(sport: str = "nfl") -> None:
    st.header("Today's games")
    df = load("upcoming", sport)
    if df.empty:
        sched = "Fri / Sat, Pacific" if sport == "ncaaf" else "Sun / Mon / Thu, Pacific"
        st.info(f"No games scheduled today. The board refreshes on the pipeline schedule ({sched}).")
        return
    if len(df) > 1:
        labels = [f"{r.away_team} @ {r.home_team}" for r in df.itertuples()]
        pick = st.selectbox("Game", labels)
        df = df[[f"{r.away_team} @ {r.home_team}" == pick for r in df.itertuples()]]
    for _, g in df.iterrows():
        fav = g.spread_favorite if pd.notna(g.spread_favorite) else "—"
        with st.container(border=True):
            def rank_text(rank, season_rank) -> str:
                if sport == "ncaaf":
                    return f"AP Top 25: #{int(rank)}" if pd.notna(rank) else "Unranked (AP)"
                return f"Rank #{int(season_rank) if pd.notna(season_rank) else '—'}"

            a, mid, h = st.columns([2, 1, 2])
            with a:
                team_block(g.away_team, g.away_record_display,
                           rank_text(getattr(g, "away_rank", None), g.away_season_rank), g.away_spread_points)
            with mid:
                st.markdown('<div class="vs">@</div>', unsafe_allow_html=True)
                top25 = sport == "ncaaf" and bool(getattr(g, "is_top25_matchup", False))
                pill = "Top-25 matchup" if top25 else f"{fav} favored"
                st.markdown(f'<div style="text-align:center;margin-top:0.45rem"><span class="pill">{pill}</span></div>', unsafe_allow_html=True)
                st.metric("Total (pts)", g.totals_line_points)
            with h:
                team_block(g.home_team, g.home_record_display,
                           rank_text(getattr(g, "home_rank", None), g.home_season_rank), g.home_spread_points, align="right")
            duel_bar(g.away_team, g.away_consensus_pct, g.home_team, g.home_consensus_pct)
            st.divider()
            compare_row("Win %", g.away_win_pct, g.home_win_pct, g.away_team, g.home_team)
            compare_row("Cover % (ATS)", g.away_against_the_spread_win_pct, g.home_against_the_spread_win_pct, g.away_team, g.home_team)
            compare_row("Over %", g.away_over_pct, g.home_over_pct, g.away_team, g.home_team)
            compare_row("Consensus spread accuracy", g.away_consensus_spread_accuracy, g.home_consensus_spread_accuracy, g.away_team, g.home_team)
            compare_row("Consensus total accuracy", g.away_consensus_total_accuracy, g.home_consensus_total_accuracy, g.away_team, g.home_team)
            c1, c2 = st.columns(2)
            c1.metric(f"{g.away_team} avg points", f"{g.away_avg_points_scored:.1f}")
            c2.metric(f"{g.home_team} avg points", f"{g.home_avg_points_scored:.1f}")
            with st.expander("What history says in this spot — consensus band & line context"):
                st.markdown(band_panel(g, sport))
        st.caption("ATS = against the spread. Cover % excludes pushes. The panel below the expander "
                   "conditions on tonight's consensus band and spread size — always check n=")


def band_chart(d: pd.DataFrame, x: str, y: str, title: str) -> None:
    order_col = next((c for c in d.columns if c.endswith("_band_order")), None)
    x_enc = alt.X(x, sort=alt.SortField(order_col, order="descending"), title=None) if order_col else alt.X(x, sort=None, title=None)
    chart = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=x_enc,
            y=alt.Y(y, title=title, axis=alt.Axis(format="%")),
            tooltip=[x, alt.Tooltip(y, format=".0%"), "games"],
            color=alt.Color(x, legend=None, scale=alt.Scale(scheme="greens")),
        )
        .properties(height=240)
    )
    st.altair_chart(chart, width="stretch")


def page_consensus(sport: str = "nfl") -> None:
    st.header("Consensus — does the crowd cover?")
    st.caption("Rates are conditional on a team's own consensus share (mirrored bands). "
               "Cover % excludes pushes; win % is outright. Small n = weak evidence.")
    bands = load("spread_bands", sport)
    latest = int(bands["season"].max())
    seasons_avail = [latest, 0] + sorted([int(s) for s in bands["season"].unique() if s not in (0, latest)], reverse=True)
    season_pick = st.segmented_control("Season (0 = all seasons)", seasons_avail, default=latest)

    league = bands[(bands["scope"] == "League") & (bands["season"] == season_pick)]
    tab_fav, tab_dog, tab_tot, tab_line = st.tabs(["Favorites", "Underdogs", "Totals", "By the line"])
    with tab_fav:
        d = league[league["consensus_role"] == "Favorite"].sort_values("consensus_band_order")
        band_chart(d.assign(cover_pct=d["cover_pct"]), "consensus_band", "cover_pct", "Cover %")
        st.dataframe(d[["consensus_band", "games", "covers", "pushes", "cover_pct", "game_wins", "win_pct"]], hide_index=True, width="stretch")
    with tab_dog:
        d = league[league["consensus_role"] == "Underdog"].sort_values("consensus_band_order")
        band_chart(d.assign(cover_pct=d["cover_pct"]), "consensus_band", "cover_pct", "Cover %")
        st.dataframe(d[["consensus_band", "games", "covers", "pushes", "cover_pct", "game_wins", "win_pct"]], hide_index=True, width="stretch")
    with tab_tot:
        totals = load("total_bands", sport)
        d = totals[(totals["scope"] == "League") & (totals["season"] == season_pick)]
        side = st.segmented_control("Favored side", ["Over", "Under"], default="Over")
        dd = d[d["totals_consensus_side"] == side].sort_values("consensus_band_order")
        band_chart(dd.rename(columns={"hit_pct": "cover_pct", "hits": "covers", "games": "games"})[["consensus_band", "cover_pct", "games"]],
                   "consensus_band", "cover_pct", "Hit %")
        st.dataframe(dd[["consensus_band", "games", "hits", "pushes", "hit_pct"]], hide_index=True, width="stretch")
    with tab_line:
        sl = load("spread_line_bands", sport)
        d = sl[(sl["scope"] == "League") & (sl["season"] == season_pick) & (sl["spread_role"] != "Even")]
        role = st.segmented_control("Role ", ["Favorite", "Underdog"], default="Favorite")
        dd = d[d["spread_role"] == role].sort_values("spread_line_bucket_order")
        band_chart(dd, "spread_line_bucket", "cover_pct", "Cover %")
        st.dataframe(dd[["spread_line_bucket", "games", "covers", "pushes", "cover_pct", "win_pct"]], hide_index=True, width="stretch")
        tl = load("total_line_bands", sport)
        d = tl[(tl["scope"] == "League") & (tl["season"] == season_pick)].sort_values("totals_line_bucket_order")
        st.markdown("**Totals line — over hit rate**")
        band_chart(d.rename(columns={"over_pct": "cover_pct", "overs": "covers"})[["totals_line_bucket", "cover_pct", "games"]],
                   "totals_line_bucket", "cover_pct", "Over %")
        st.dataframe(d[["totals_line_bucket", "games", "overs", "pushes", "over_pct", "under_pct"]], hide_index=True, width="stretch")

    st.subheader("Team splits")
    team = st.selectbox("Team", sorted(bands[bands["scope"] == "Team"]["team_name"].dropna().unique()))
    d = bands[(bands["scope"] == "Team") & (bands["team_name"] == team) & (bands["season"] == season_pick)]
    st.dataframe(d.sort_values("consensus_band_order")[
        ["consensus_band", "consensus_role", "games", "covers", "cover_pct", "game_wins", "win_pct"]],
        hide_index=True, width="stretch")


def page_form(sport: str = "nfl") -> None:
    st.header("Team form")
    form = load("form", sport)
    seasons = sorted(form["season"].unique(), reverse=True)
    season = st.segmented_control("Season", seasons, default=seasons[0])
    d = form[form["season"] == season].sort_values("season_rank")
    st.dataframe(
        d,
        hide_index=True, width="stretch",
        column_config={
            "season_rank": st.column_config.NumberColumn("Rank"),
            "team_name": st.column_config.TextColumn("Team"),
            "record_display": st.column_config.TextColumn("Record"),
            "win_pct": st.column_config.ProgressColumn("Win %", min_value=0, max_value=1, format="%.2f"),
            "against_the_spread_win_pct": st.column_config.ProgressColumn("ATS win %", min_value=0, max_value=1, format="%.2f"),
            "over_pct": st.column_config.ProgressColumn("Over %", min_value=0, max_value=1, format="%.2f"),
        },
        column_order=["season_rank", "team_name", "record_display", "win_pct",
                      "against_the_spread_win_pct", "over_pct", "avg_points_scored",
                      "avg_points_allowed", "games_with_market"],
    )
    team = st.selectbox("Team detail", d["team_name"].tolist())
    row = d[d["team_name"] == team].iloc[0]
    a, b, c, dd = st.columns(4)
    a.metric("Record", row.record_display)
    b.metric("Win %", pct(row.win_pct))
    c.metric("ATS win %", pct(row.against_the_spread_win_pct))
    dd.metric("Over %", pct(row.over_pct))
    chart = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("team_name", sort="-y", title=None),
            y=alt.Y("win_pct", title="Win %", axis=alt.Axis(format="%")),
            tooltip=["team_name", alt.Tooltip("win_pct", format=".0%"), "games_played"],
            color=alt.Color("team_name", legend=None),
        )
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch")


def page_trends(sport: str = "nfl") -> None:
    st.header("Trends")
    res = load("results", sport)
    form = load("form", sport)
    team = st.selectbox("Team", sorted(form["team_name"].unique()))
    seasons = sorted(res["season"].unique(), reverse=True)
    season = st.segmented_control("Season ", seasons, default=seasons[0])
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

    long = played.melt(id_vars=["game", "game_date"], value_vars=["points_scored", "points_allowed"],
                       var_name="kind", value_name="points")
    chart = (
        alt.Chart(long)
        .mark_line(point=True)
        .encode(x=alt.X("game", title="Game #"), y=alt.Y("points", title="Points"),
                color="kind", tooltip=["game_date", "kind", "points"])
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch")

    totals_chart = (
        alt.Chart(played)
        .mark_line(point=True)
        .encode(x=alt.X("game", title="Game #"), y=alt.Y("total_points", title="Points"),
                tooltip=["game_date", "total_points", "totals_line_points"])
        .properties(height=220)
    ) + alt.Chart(played).mark_line(strokeDash=[5, 4], color="#9db2c3").encode(x="game", y="totals_line_points")
    st.caption("Game total (solid) vs totals line (dashed)")
    st.altair_chart(totals_chart, width="stretch")
    st.dataframe(
        played[["game_date", "week", "home_team", "away_team", "home_score", "away_score",
                "totals_line_points", "totals_result", "spread_cover_side"]],
        hide_index=True, width="stretch",
    )


if not require_password():
    st.stop()

sport_label = st.sidebar.radio("Sport", ["NFL", "NCAAF"])
sport = sport_label.lower()

st.title(f"{'🏈' if sport == 'nfl' else '🎓'} {sport_label} Matchup Board")
src = "ESPN + Covers" if sport == "ncaaf" else "nflverse + Covers"
st.caption(
    f"Data: {src} via the elt-pipeline warehouse (semantic layer). "
    "For information only — statistics and market data for your own decision; "
    "no bet recommendations. Lines move; verify before acting."
)

page = st.sidebar.radio("Page", ["Today", "Team Form", "Trends", "Consensus"])
{"Today": page_today, "Team Form": page_form, "Trends": page_trends, "Consensus": page_consensus}[page](sport)
