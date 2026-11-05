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


@st.cache_resource
def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE SECRET r2 (TYPE S3, KEY_ID ?, SECRET ?, ENDPOINT ?, REGION 'auto', URL_STYLE 'path')",
        [
            _setting("r2_access_key_id"),
            _setting("r2_secret_access_key"),
            _setting("r2_s3_host"),
        ],
    )
    return con


@st.cache_data(ttl=3600, show_spinner="Loading warehouse data…")
def load(table: str) -> pd.DataFrame:
    bucket = _setting("r2_bucket", "nfl")
    local_dir = _setting("local_warehouse_dir")
    if local_dir:
        path = f"{local_dir}/data_warehouse/{TABLES[table]}"
    else:
        path = f"s3://{bucket}/data_warehouse/{TABLES[table]}"
    return _con().execute(f"SELECT * FROM read_parquet('{path}')").fetchdf()
