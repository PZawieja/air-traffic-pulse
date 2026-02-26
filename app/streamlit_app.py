"""Air Traffic Pulse — Streamlit dashboard.

Run with:
    make app
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import pathlib

import streamlit as st

from air_traffic_pulse.config import get_settings
from air_traffic_pulse.log import get_logger

log = get_logger(__name__)

st.set_page_config(
    page_title="Air Traffic Pulse",
    page_icon="✈️",
    layout="wide",
)

st.title("✈️ Air Traffic Pulse")
st.caption("Live air-traffic analytics · OpenSky → DuckDB → dbt → Streamlit")

settings = get_settings()
db_path = pathlib.Path(settings.duckdb_path)

# ---------------------------------------------------------------------------
# Helper: open DuckDB read-only if the file exists, else show a prompt.
# ---------------------------------------------------------------------------
if not db_path.exists():
    st.warning(
        f"No database found at `{db_path}`. Run **`make ingest`** first to populate it.",
        icon="⚠️",
    )
    st.stop()

import duckdb  # noqa: E402  — deferred so missing db path exits cleanly

con = duckdb.connect(str(db_path), read_only=True)

# ---------------------------------------------------------------------------
# Metrics row
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)

total_rows = con.execute("SELECT count(*) FROM raw.opensky_states").fetchone()[0]
col1.metric("Total state vectors", f"{total_rows:,}")

run_count = con.execute("SELECT count(*) FROM raw.ingestion_runs").fetchone()[0]
col2.metric("Ingestion runs", run_count)

last_run = con.execute(
    "SELECT status, started_at, records_loaded "
    "FROM raw.ingestion_runs "
    "ORDER BY started_at DESC "
    "LIMIT 1"
).fetchone()

if last_run:
    status, started_at, records_loaded = last_run
    col3.metric(
        "Last run",
        status.upper(),
        delta=f"{records_loaded:,} rows  ·  {started_at:%Y-%m-%d %H:%M UTC}",
    )

# ---------------------------------------------------------------------------
# Latest ingestion run detail
# ---------------------------------------------------------------------------
st.subheader("Recent ingestion runs")
runs_df = con.execute(
    "SELECT run_id, started_at, finished_at, status, records_loaded, error_msg "
    "FROM raw.ingestion_runs "
    "ORDER BY started_at DESC "
    "LIMIT 10"
).df()

if runs_df.empty:
    st.info("No runs recorded yet.")
else:
    st.dataframe(runs_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Bbox breakdown
# ---------------------------------------------------------------------------
st.subheader("Aircraft states by bounding box")
bbox_df = con.execute(
    "SELECT bbox_name, count(*) AS state_count "
    "FROM raw.opensky_states "
    "GROUP BY bbox_name "
    "ORDER BY state_count DESC"
).df()

if bbox_df.empty:
    st.info("No data yet — run `make ingest` to populate.")
else:
    st.bar_chart(bbox_df.set_index("bbox_name")["state_count"])

con.close()
