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
    local_dir = _setting("local_warehouse_dir")
    if local_dir:
        # Local mirror layout: <dir>/data_warehouse (nfl bucket root) and
        # <dir>/ncaaf/data_warehouse (ncaaf bucket root).
        sub = "" if sport == "nfl" else f"{sport}/"
        path = f"{local_dir}/{sub}data_warehouse/{TABLES[table]}"
    else:
        path = f"s3://{bucket}/data_warehouse/{TABLES[table]}"
    try:
        return _con().execute(f"SELECT * FROM read_parquet('{path}')").fetchdf()
    except Exception as exc:  # surface a readable reason instead of a redacted crash
        raise RuntimeError(f"Failed to load {table} ({sport}) from {path}: {type(exc).__name__}: {_masked(str(exc))}") from None
