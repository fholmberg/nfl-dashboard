# Matchup Board (NFL + NCAAF)

Private-use Streamlit dashboard over the elt-pipeline semantic layer.
Sidebar switches between the NFL and NCAAF sections (same pages, each
sport reads its own R2 bucket: `nfl` / `ncaaf`).
Reads published Parquet exports from Cloudflare R2 (read-only keys in
Streamlit secrets). Presents statistics and market data for users to make
their own decisions; it does not recommend bets.

Deploy: Streamlit Community Cloud -> main file `streamlit_app.py`.
Secrets: see `.streamlit/secrets.toml.example`.
