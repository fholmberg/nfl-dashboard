"""Warehouse access for the dashboard.

Reads the published Parquet exports in R2 (data_warehouse/semantic/*.parquet)
with DuckDB. Credentials come from Streamlit secrets (Streamlit Cloud) or
environment variables (local). Results are cached for an hour; the pipeline
only publishes a few times a week.
"""

from __future__ import annotations

import os

import duckdb
import pandas as pd
import streamlit as st

TABLES = {
    "upcoming": "semantic/semantic_upcoming_matchups.parquet",
    # Silver upcoming holds ALL future fixtures; the Today page filters to
    # the current date at read time (the semantic table is build-day only
    # and goes stale between pipeline runs).
    "upcoming_all": "silver/fct_{sport}_betting_upcoming.parquet",
    "settled_all": "silver/fct_{sport}_betting_settled.parquet",
    "form": "semantic/semantic_team_season_form.parquet",
    "results": "semantic/semantic_game_results.parquet",
    "spread_bands": "semantic/semantic_consensus_spread_bands.parquet",
    "total_bands": "semantic/semantic_consensus_total_bands.parquet",
    "spread_line_bands": "semantic/semantic_spread_line_bands.parquet",
    "total_line_bands": "semantic/semantic_total_line_bands.parquet",
}


def _setting(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name.upper(), default)))
    except Exception:
        return os.getenv(name.upper(), default)


def _masked(message: str) -> str:
    """Strip credential values so Streamlit does not redact the whole error."""
    for name in ("r2_access_key_id", "r2_secret_access_key", "app_password"):
        value = _setting(name)
        if len(value) > 4:
            message = message.replace(value, "***")
    return message


@st.cache_resource
def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    esc = lambda v: v.replace("'", "''")
    con.execute(
        "CREATE OR REPLACE SECRET r2 (TYPE S3, "
        f"KEY_ID '{esc(_setting('r2_access_key_id'))}', "
        f"SECRET '{esc(_setting('r2_secret_access_key'))}', "
        f"ENDPOINT '{esc(_setting('r2_s3_host'))}', "
        "REGION 'auto', URL_STYLE 'path')"
    )
    return con


@st.cache_data(ttl=3600, show_spinner="Loading warehouse data…")
def load(table: str, sport: str = "nfl") -> pd.DataFrame:
    # Each sport publishes the same semantic filenames to its own bucket.
    bucket = _setting("r2_bucket_ncaaf", "ncaaf") if sport == "ncaaf" else _setting("r2_bucket", "nfl")
    rel = TABLES[table].format(sport=sport)
    local_dir = _setting("local_warehouse_dir")
    if local_dir:
        # Local mirror layout: <dir>/data_warehouse (nfl bucket root) and
        # <dir>/ncaaf/data_warehouse (ncaaf bucket root).
        sub = "" if sport == "nfl" else f"{sport}/"
        path = f"{local_dir}/{sub}data_warehouse/{rel}"
    else:
        path = f"s3://{bucket}/data_warehouse/{rel}"
    try:
        return _con().execute(f"SELECT * FROM read_parquet('{path}')").fetchdf()
    except Exception as exc:  # surface a readable reason instead of a redacted crash
        raise RuntimeError(f"Failed to load {table} ({sport}) from {path}: {type(exc).__name__}: {_masked(str(exc))}") from None


_FORM_COLS = ["wins", "losses", "record_display", "win_pct", "season_rank",
              "against_the_spread_win_pct", "over_pct", "avg_points_scored",
              "consensus_spread_accuracy", "consensus_total_accuracy"]


def _market_shape(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "home_spread": "home_spread_points", "away_spread": "away_spread_points",
        "spread_line": "spread_line_points", "market_favorite_team": "spread_favorite",
        "spread_home_consensus_pct": "home_consensus_pct",
        "spread_away_consensus_pct": "away_consensus_pct",
        "over_under_line": "totals_line_points",
    })


def _join_form(df: pd.DataFrame, sport: str) -> pd.DataFrame:
    form = load("form", sport)
    for side in ("home", "away"):
        f = form[["team_name", "season"] + _FORM_COLS].rename(
            columns={"team_name": f"{side}_team", **{c: f"{side}_{c}" for c in _FORM_COLS}}
        )
        df = df.merge(f, on=[f"{side}_team", "season"], how="left")
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    return df


@st.cache_data(ttl=3600, show_spinner="Loading upcoming games…")
def load_today(sport: str = "nfl") -> pd.DataFrame:
    """Future fixtures with season form joined, in the semantic column shape
    the Today page renders. game_date is filtered by the caller."""
    return _join_form(_market_shape(load("upcoming_all", sport).copy()), sport)


@st.cache_data(ttl=3600, show_spinner="Loading historical games…")
def load_history(sport: str = "nfl") -> pd.DataFrame:
    """Played games (scores from the semantic results table) with market
    context and season form joined, same shape as load_today plus scores."""
    res = load("results", sport)[
        ["game_date", "season", "week", "home_team", "away_team", "home_score",
         "away_score", "winner", "totals_result", "spread_cover_side",
         *[c for c in ("home_rank", "away_rank", "is_top25_matchup") if c in load("results", sport).columns]]
    ].copy()
    settled = _market_shape(load("settled_all", sport).copy())
    keep = ["game_date", "home_team", "away_team", "home_spread_points", "away_spread_points",
            "spread_line_points", "spread_favorite", "home_consensus_pct", "away_consensus_pct",
            "totals_line_points", "over_consensus_pct", "under_consensus_pct"]
    df = res.merge(settled[keep], on=["game_date", "home_team", "away_team"], how="left")
    return _join_form(df, sport)


def games_for_day(df: pd.DataFrame, day) -> tuple[pd.DataFrame, object, bool]:
    """Rows for `day`; if none, the next future game day. Past rows never show."""
    if df.empty:
        return df, day, True
    dates = sorted(df["game_date"].unique())
    if day in dates:
        return df[df["game_date"] == day], day, True
    future = [d for d in dates if d > day]
    if future:
        return df[df["game_date"] == future[0]], future[0], False
    return df.iloc[0:0], day, True
