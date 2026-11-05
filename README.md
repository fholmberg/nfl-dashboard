# NFL Matchup Board

Private-use Streamlit dashboard over the elt-pipeline semantic layer.
Reads published Parquet exports from Cloudflare R2 (read-only keys in
Streamlit secrets). Presents statistics and market data for users to make
their own decisions; it does not recommend bets.

Deploy: Streamlit Community Cloud -> main file `streamlit_app.py`.
Secrets: see `.streamlit/secrets.toml.example`.
