"""Air Traffic Pulse — Streamlit dashboard.

Reads from dbt mart tables in DuckDB.  Run the pipeline first:
    make ingest   → populate raw tables
    make dbt      → build staging + mart models
    make app      → launch this dashboard
"""

from __future__ import annotations

import pathlib

import duckdb
import streamlit as st

from air_traffic_pulse.config import get_settings

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Air Traffic Pulse",
    page_icon="✈️",
    layout="wide",
)

st.title("✈️ Air Traffic Pulse")
st.caption("Live air-traffic analytics · OpenSky → DuckDB → dbt → Streamlit")

settings = get_settings()
db_path = pathlib.Path(settings.duckdb_path)

# ── Guard: database must exist ───────────────────────────────────────────────
if not db_path.exists():
    st.warning(
        f"Database not found at `{db_path}`.  "
        "Run **`make ingest`** first to populate the raw tables.",
        icon="⚠️",
    )
    st.stop()

con = duckdb.connect(str(db_path), read_only=True)


# ── Helper ───────────────────────────────────────────────────────────────────
def _table_exists(schema: str, table: str) -> bool:
    return (
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()[0]
        > 0
    )


# ── Guard: dbt marts must exist ──────────────────────────────────────────────
_REQUIRED_MARTS = [
    "mart_latest_ingestion_run",
    "mart_latest_snapshot_by_bbox",
    "mart_traffic_timeseries_5min",
]
missing = [t for t in _REQUIRED_MARTS if not _table_exists("dbt", t)]
if missing:
    st.info(
        "dbt mart tables not found yet.  "
        "Run **`make dbt`** to build the analytics layer, then refresh this page.\n\n"
        f"Missing: `{', '.join(missing)}`",
        icon="ℹ️",
    )
    con.close()
    st.stop()

# ── Load mart data ────────────────────────────────────────────────────────────
run_df = con.execute("SELECT * FROM dbt.mart_latest_ingestion_run").df()
snapshot_df = con.execute("SELECT * FROM dbt.mart_latest_snapshot_by_bbox ORDER BY bbox_name").df()
timeseries_df = con.execute(
    "SELECT * FROM dbt.mart_traffic_timeseries_5min ORDER BY bbox_name, bucket_ts"
).df()
con.close()

# ── Top metrics: last run ─────────────────────────────────────────────────────
st.subheader("Last ingestion run")

if run_df.empty:
    st.info("No ingestion runs recorded yet.  Run **`make ingest`** to start.", icon="ℹ️")
else:
    row = run_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)

    status_icon = {"success": "✅", "failed": "❌", "running": "🔄"}.get(row["status"], "❓")
    col1.metric("Status", f"{status_icon} {row['status'].upper()}")

    col2.metric("Records loaded", f"{int(row['records_loaded']):,}")

    duration = row["run_duration_seconds"]
    col3.metric("Duration", f"{int(duration)}s" if duration is not None else "—")

    started = row["started_at"]
    col4.metric("Started at", str(started)[:19] if started is not None else "—")

    if row["status"] == "failed" and row.get("error_msg"):
        st.error(f"Error: {row['error_msg']}", icon="🚨")

st.divider()

# ── Latest snapshot table ─────────────────────────────────────────────────────
st.subheader("Latest snapshot by bounding box")

if snapshot_df.empty:
    st.info("No aircraft data yet.  Run **`make ingest`** then **`make dbt`**.", icon="ℹ️")
else:
    display_cols = {
        "bbox_name": "Bbox",
        "snapshot_ingestion_ts": "Snapshot time (UTC)",
        "aircraft_count": "Aircraft",
        "positioned_aircraft_count": "With position",
        "on_ground_count": "On ground",
        "avg_velocity_mps": "Avg speed (m/s)",
    }
    st.dataframe(
        snapshot_df[list(display_cols.keys())].rename(columns=display_cols),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ── Timeseries chart ──────────────────────────────────────────────────────────
st.subheader("Traffic timeseries (5-minute buckets)")

if timeseries_df.empty:
    st.info("No timeseries data yet.", icon="ℹ️")
else:
    available_bboxes = sorted(timeseries_df["bbox_name"].unique().tolist())

    col_sel, col_win = st.columns([2, 2])
    selected_bbox = col_sel.selectbox("Bounding box", available_bboxes)
    window_hours = col_win.select_slider(
        "Show last …",
        options=[1, 3, 6, 12, 24, 72, 168],
        value=24,
        format_func=lambda h: f"{h}h" if h < 24 else f"{h // 24}d",
    )

    bbox_df = timeseries_df[timeseries_df["bbox_name"] == selected_bbox].copy()
    # bucket_ts comes back as object/string from DuckDB; coerce to datetime
    bbox_df["bucket_ts"] = bbox_df["bucket_ts"].astype("datetime64[us, UTC]")

    cutoff = bbox_df["bucket_ts"].max() - __import__("pandas").Timedelta(hours=window_hours)
    filtered_df = bbox_df[bbox_df["bucket_ts"] >= cutoff]

    n_points = len(filtered_df)
    total_points = len(bbox_df)

    if n_points == 0:
        st.info(f"No data in the last {window_hours}h. Widen the window or run `make ingest`.")
    elif n_points < 3:
        st.warning(
            f"Only **{n_points}** data point(s) visible — the chart will look sparse.  "
            f"Run `make ingest` a few more times to build up the timeseries "
            f"({total_points} total buckets across all time).",
            icon="💡",
        )

    chart_df = (
        filtered_df.set_index("bucket_ts")[["aircraft_count", "positioned_aircraft_count"]]
        .rename(
            columns={
                "aircraft_count": "Total aircraft",
                "positioned_aircraft_count": "With position fix",
            }
        )
        .sort_index()
    )

    st.line_chart(chart_df)
    st.caption(
        f"**{n_points}** 5-minute buckets shown · "
        f"{total_points} total · "
        f"each point = distinct aircraft over **{selected_bbox}** · "
        f"run `make ingest` to add more"
    )
