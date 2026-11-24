# Matchup Board (NFL + NCAAF)

Streamlit dashboard over the elt-pipeline semantic layer.
Sidebar switches between the NFL and NCAAF sections (same pages, each
sport reads its own R2 bucket: `nfl` / `ncaaf`).
Reads published Parquet exports from Cloudflare R2 (read-only keys in
Streamlit secrets). Presents statistics and market data for users to make
their own decisions; it does not recommend bets.

Live: https://dzzheeqfpuy774nutwccl2.streamlit.app/

Deploy: Streamlit Community Cloud -> main file `streamlit_app.py`.
Secrets: see `.streamlit/secrets.toml.example` (`app_password` optional;
without it the board is public read-only).

Note: this is a standalone export for Streamlit Cloud. The source of
truth is `dashboard/` in https://github.com/holmbergf/elt-pipeline —
re-copy `streamlit_app.py`, `data.py`, `requirements.txt`, and
`.streamlit/*` from there when updating.
