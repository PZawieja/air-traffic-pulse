"""Air Traffic Pulse — Streamlit dashboard.

Reads from dbt mart tables in DuckDB.  Run the pipeline first:
    make ingest   → populate raw tables
    make dbt      → build staging + mart models
    make app      → launch this dashboard
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
import sys
import time

import duckdb
import pandas as pd
import streamlit as st

from air_traffic_pulse.config import BBOX_PRESETS, REGION_DISPLAY, get_settings

# ── Constants ─────────────────────────────────────────────────────────────────
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# REGION_DISPLAY comes from config.py — adding a new preset there is enough.
REGION_FLAGS = REGION_DISPLAY  # alias kept for readability in this file

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Air Traffic Pulse",
    page_icon="✈️",
    layout="wide",
)

settings = get_settings()
db_path = pathlib.Path(settings.duckdb_path)
demo_mode = settings.air_traffic_pulse_demo_mode

# ── Fetch logic (runs before any rendering) ───────────────────────────────────


def _run_fetch(regions: list[str]) -> tuple[bool, str]:
    """Trigger ingestion + dbt build, returning (success, error_message)."""
    env = os.environ.copy()

    if demo_mode:
        # In demo mode: append 1 h of fresh synthetic snapshots to the demo DB.
        ingest_cmd = [
            sys.executable,
            str(_REPO_ROOT / "tools" / "seed_demo_data.py"),
            "--hours",
            "1",
            "--bboxes",
            *regions,
        ]
    else:
        # Live mode: call the real OpenSky API for the selected regions.
        env["OPENSKY_BBOX_PRESETS"] = ",".join(regions)
        ingest_cmd = [sys.executable, "-m", "air_traffic_pulse", "ingest"]

    r = subprocess.run(ingest_cmd, env=env, capture_output=True, text=True, cwd=str(_REPO_ROOT))
    if r.returncode != 0:
        return False, r.stderr or r.stdout or "Ingestion failed with no output."

    # Rebuild dbt models so the marts reflect the new data.
    dbt_bin = str(pathlib.Path(sys.executable).parent / "dbt")
    r = subprocess.run(
        [dbt_bin, "build", "--project-dir", "dbt", "--profiles-dir", "dbt"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    if r.returncode != 0:
        return False, r.stderr or r.stdout or "dbt build failed with no output."

    return True, ""


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("✈️ Air Traffic Pulse")
    st.markdown(
        "Real-time air-traffic analytics built on open data.\n\n"
        "**What this shows**\n\n"
        "Aircraft currently airborne or taxiing over three European cities, "
        "sourced from the [OpenSky Network](https://opensky-network.org/) — "
        "a crowd-sourced ADS-B receiver network that provides free, live "
        "position data for commercial and private flights.\n\n"
        "---\n"
        "**Monitored regions**\n\n"
        "| Region | Approx. area |\n"
        "|---|---|\n"
        "| 🇩🇪 Berlin | ~50 × 60 km box |\n"
        "| 🇩🇪 Frankfurt | ~35 × 55 km box |\n"
        "| 🇬🇧 London | ~45 × 90 km box |\n"
        "| 🇵🇱 Warsaw | ~45 × 65 km box |\n\n"
        "---\n"
        "**Data pipeline**\n\n"
        "```\n"
        "OpenSky API\n"
        "    ↓  make ingest\n"
        "DuckDB  (raw tables)\n"
        "    ↓  make dbt\n"
        "dbt models  (staging + marts)\n"
        "    ↓\n"
        "This dashboard\n"
        "```\n\n"
        "---\n"
    )

    # ── Fetch panel ───────────────────────────────────────────────────────────
    st.subheader("📡 Fetch new data")

    if demo_mode:
        st.info(
            "Running in **demo mode** — clicking Fetch will add 1 hour of fresh "
            "synthetic aircraft data (no real API calls).",
            icon="🧪",
        )
        fetch_regions = list(REGION_FLAGS.keys())
    else:
        fetch_regions = st.multiselect(
            "Regions to fetch",
            options=list(BBOX_PRESETS.keys()),
            default=list(BBOX_PRESETS.keys()),
            format_func=lambda x: REGION_FLAGS.get(x, x.title()),
            help="Select which regions to poll. Fetching fewer regions is faster.",
        )

    fetch_clicked = st.button(
        "🔄 Fetch & refresh",
        disabled=not fetch_regions,
        help=(
            "Pull fresh synthetic data and rebuild the analytics layer."
            if demo_mode
            else "Poll the OpenSky API for the selected regions and rebuild the analytics layer."
        ),
    )

    st.markdown("---")
    st.caption("Use `make watch` in a terminal to poll automatically every 5 minutes.")
    st.caption(f"Database: `{db_path}`")


# ── Run fetch if button was clicked ──────────────────────────────────────────
# This runs before any data is loaded so the page renders fresh data after rerun.
if fetch_clicked:
    label = (
        "Adding synthetic data"
        if demo_mode
        else f"Fetching {', '.join(REGION_FLAGS[r] for r in fetch_regions)}"
    )
    with st.spinner(f"{label} and rebuilding models — this takes a few seconds…"):
        ok, err = _run_fetch(fetch_regions)

    if ok:
        st.toast("Data updated!", icon="✅")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error(
            f"Something went wrong during the fetch. Details below:\n\n```\n{err}\n```",
            icon="🚨",
        )
        st.stop()


# ── Guard: database must exist ───────────────────────────────────────────────
if not db_path.exists():
    st.warning(
        f"Database not found at `{db_path}`.  "
        "Run **`make ingest`** first to populate the raw tables, "
        "then **`make dbt`** to build the analytics layer.",
        icon="⚠️",
    )
    st.stop()

con = duckdb.connect(str(db_path), read_only=True)


# ── Helper ────────────────────────────────────────────────────────────────────
def _table_exists(schema: str, table: str) -> bool:
    return (
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()[0]
        > 0
    )


# ── Guard: dbt marts must exist ───────────────────────────────────────────────
_REQUIRED_MARTS = [
    "mart_latest_ingestion_run",
    "mart_latest_snapshot_by_bbox",
    "mart_traffic_timeseries_5min",
    "mart_latest_insights_by_bbox",
    "mart_traffic_anomalies_5min",
]
missing = [t for t in _REQUIRED_MARTS if not _table_exists("dbt", t)]
if missing:
    st.info(
        "The analytics layer hasn't been built yet.  "
        "Run **`make dbt`** in a terminal, then refresh this page.\n\n"
        f"Missing tables: `{', '.join(missing)}`",
        icon="ℹ️",
    )
    con.close()
    st.stop()

# ── Load mart data ─────────────────────────────────────────────────────────────
run_df = con.execute("SELECT * FROM dbt.mart_latest_ingestion_run").df()
snapshot_df = con.execute("SELECT * FROM dbt.mart_latest_snapshot_by_bbox ORDER BY bbox_name").df()
timeseries_df = con.execute(
    "SELECT * FROM dbt.mart_traffic_timeseries_5min ORDER BY bbox_name, bucket_ts"
).df()
insights_df = con.execute("SELECT * FROM dbt.mart_latest_insights_by_bbox ORDER BY bbox_name").df()
anomalies_df = con.execute(
    "SELECT * FROM dbt.mart_traffic_anomalies_5min WHERE is_anomaly = true ORDER BY bucket_ts DESC"
).df()
con.close()

# ── Page header ───────────────────────────────────────────────────────────────
st.title("✈️ Air Traffic Pulse")

if not run_df.empty:
    row0 = run_df.iloc[0]
    finished = row0.get("finished_at")
    finished_str = str(finished)[:19] if finished is not None else None
    started_str = str(row0["started_at"])[:19] if row0["started_at"] is not None else "unknown"
    data_note = f"Last data collected: **{finished_str or started_str} UTC**"
    st.caption(
        "Tracking live air traffic over **Berlin · Frankfurt · London · Warsaw** · "
        + data_note
        + ("  ·  🧪 Demo mode" if demo_mode else "")
    )
else:
    st.caption(
        "Tracking live air traffic over **Berlin · Frankfurt · London · Warsaw**"
        + ("  ·  🧪 Demo mode" if demo_mode else "")
    )

st.divider()

# ── Section 1: Pipeline status ────────────────────────────────────────────────
st.subheader("🔄 Pipeline status")
st.markdown(
    "Shows the outcome of the most recent data collection run. "
    "Each run polls the OpenSky API for all three regions and writes "
    "the raw aircraft state vectors into DuckDB."
)

if run_df.empty:
    st.info(
        "No ingestion runs recorded yet.  "
        "Click **Fetch & refresh** in the sidebar to collect the first batch of data.",
        icon="ℹ️",
    )
else:
    row = run_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)

    status_icon = {"success": "✅", "failed": "❌", "running": "🔄"}.get(row["status"], "❓")
    col1.metric(
        label="Last run result",
        value=f"{status_icon} {row['status'].capitalize()}",
        help="Whether the last ingestion run completed without errors.",
    )
    col2.metric(
        label="Aircraft states collected",
        value=f"{int(row['records_loaded']):,}",
        help="Total rows written to the database — one row per aircraft per region per run.",
    )
    duration = row["run_duration_seconds"]
    col3.metric(
        label="Run duration",
        value=f"{int(duration)}s" if duration is not None else "—",
        help="Wall-clock time from start to finish of the last ingestion run.",
    )
    started = row["started_at"]
    col4.metric(
        label="Started at (UTC)",
        value=str(started)[:19] if started is not None else "—",
        help="UTC timestamp when the last ingestion run began.",
    )

    if row["status"] == "failed" and row.get("error_msg"):
        st.error(f"Error detail: {row['error_msg']}", icon="🚨")

st.divider()

# ── Section 2: Latest snapshot ────────────────────────────────────────────────
st.subheader("📍 Latest snapshot by region")
st.markdown(
    "A *snapshot* is a single poll of the OpenSky API. "
    "The table below shows the most recent snapshot for each monitored region. "
    "**Aircraft detected** counts every transponder signal received. "
    "**GPS-positioned** is the subset with a valid latitude/longitude fix. "
    "**On ground** are aircraft detected at the airport (taxiing or parked)."
)

if snapshot_df.empty:
    st.info(
        "No aircraft data yet.  Click **Fetch & refresh** in the sidebar to collect data.",
        icon="ℹ️",
    )
else:
    display_df = snapshot_df.copy()
    display_df["bbox_name"] = display_df["bbox_name"].map(lambda x: REGION_FLAGS.get(x, x.title()))
    display_df["avg_velocity_mps"] = display_df["avg_velocity_mps"].round(1)

    display_cols = {
        "bbox_name": "Region",
        "snapshot_ingestion_ts": "Captured at (UTC)",
        "aircraft_count": "Aircraft detected",
        "positioned_aircraft_count": "GPS-positioned",
        "on_ground_count": "On ground",
        "avg_velocity_mps": "Avg ground speed (m/s)",
    }
    st.dataframe(
        display_df[list(display_cols.keys())].rename(columns=display_cols),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Ground speed is averaged over airborne aircraft only. "
        "Typical cruising speed for a commercial jet is 220–260 m/s (790–940 km/h)."
    )

st.divider()

# ── Section 3: Traffic insights ───────────────────────────────────────────────
st.subheader("🧠 Traffic insights")
st.markdown(
    "Statistical summary for the most recent 5-minute bucket per region. "
    "The **z-score** measures how many standard deviations the current count "
    "is from the 28-day rolling baseline — values beyond ±3 are flagged as anomalies. "
    "**1h trend** is the % change vs the preceding hour's average."
)

if insights_df.empty:
    st.info("No insights data yet. Click **Fetch & refresh** in the sidebar.", icon="ℹ️")
else:

    def _status_label(row: pd.Series) -> str:
        if row.get("latest_is_anomaly"):
            direction = row.get("latest_anomaly_direction")
            if direction == "spike":
                return "⚠️ Spike"
            if direction == "drop":
                return "⬇️ Drop"
            return "⚠️ Anomaly"
        return "✅ Normal"

    def _fmt_z(val: object) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        return f"+{val:.1f}" if float(val) >= 0 else f"{float(val):.1f}"  # type: ignore[arg-type]

    def _fmt_pct(val: object) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        return f"+{val:.1f}%" if float(val) >= 0 else f"{float(val):.1f}%"  # type: ignore[arg-type]

    ins = insights_df.copy()
    ins["Region"] = ins["bbox_name"].map(lambda x: REGION_FLAGS.get(x, x.title()))
    ins["Status"] = ins.apply(_status_label, axis=1)
    ins["Aircraft now"] = ins["latest_aircraft_count"]
    ins["Baseline avg"] = ins["baseline_mean_aircraft"].round(1)
    ins["Baseline σ"] = ins["baseline_std_aircraft"].round(1)
    ins["Z-score"] = ins["latest_z_aircraft"].apply(_fmt_z)
    ins["1h trend"] = ins["trend_1h_pct"].apply(_fmt_pct)

    insight_cols = [
        "Region",
        "Status",
        "Aircraft now",
        "Baseline avg",
        "Baseline σ",
        "Z-score",
        "1h trend",
    ]
    st.dataframe(ins[insight_cols], width="stretch", hide_index=True)
    st.caption(
        "Z-score = (current − 28d mean) / 28d std.  "
        "Anomaly threshold: |z| ≥ 3.  "
        "1h trend compares latest bucket to the average of the preceding 12 buckets."
    )

    # Show recent anomaly events if any exist.
    if not anomalies_df.empty:
        with st.expander(f"🚨 Recent anomaly events ({len(anomalies_df)} detected)", expanded=True):
            anom_display = anomalies_df.head(20).copy()
            anom_display["bucket_ts"] = anom_display["bucket_ts"].astype("datetime64[us, UTC]")
            anom_display["Region"] = anom_display["bbox_name"].map(
                lambda x: REGION_FLAGS.get(x, x.title())
            )
            anom_display["Direction"] = (
                anom_display["anomaly_direction"].fillna("—").str.capitalize()
            )
            anom_display["Z-score"] = anom_display["z_aircraft"].apply(_fmt_z)
            anom_display["Aircraft"] = anom_display["aircraft_count"]
            anom_display["Baseline"] = anom_display["baseline_mean_aircraft"].round(1)
            anom_display["Time (UTC)"] = anom_display["bucket_ts"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(
                anom_display[
                    ["Time (UTC)", "Region", "Direction", "Aircraft", "Baseline", "Z-score"]
                ],
                width="stretch",
                hide_index=True,
            )

st.divider()

# ── Section 4: Timeseries ─────────────────────────────────────────────────────
st.subheader("📈 Aircraft count over time")
st.markdown(
    "Each data point represents a **5-minute bucket** — the number of distinct aircraft "
    "detected in the selected region during that interval.\n\n"
    "- **All aircraft** — every transponder signal received\n"
    "- **GPS-positioned** — the subset with a valid latitude/longitude fix\n"
    "- The gap between the two lines is aircraft whose transponder is active "
    "but whose position has not yet been resolved\n\n"
    "Peaks during the day and a dip overnight are typical for European airspace."
)

if timeseries_df.empty:
    st.info(
        "No timeseries data yet.  Click **Fetch & refresh** in the sidebar to collect data.",
        icon="ℹ️",
    )
else:
    label_to_key = {v: k for k, v in REGION_FLAGS.items() if k in timeseries_df["bbox_name"].values}

    col_sel, col_win = st.columns([2, 2])
    selected_label = col_sel.selectbox(
        "Region",
        options=list(label_to_key.keys()),
        help="Select which monitored region to display.",
    )
    window_hours = col_win.select_slider(
        "Time window",
        options=[1, 3, 6, 12, 24, 72, 168],
        value=24,
        format_func=lambda h: f"Last {h}h" if h < 24 else f"Last {h // 24}d",
        help="How far back in history to show. Widen this if the chart looks flat or empty.",
    )

    selected_bbox = label_to_key[selected_label]
    bbox_df = timeseries_df[timeseries_df["bbox_name"] == selected_bbox].copy()
    bbox_df["bucket_ts"] = bbox_df["bucket_ts"].astype("datetime64[us, UTC]")

    cutoff = bbox_df["bucket_ts"].max() - pd.Timedelta(hours=window_hours)
    filtered_df = bbox_df[bbox_df["bucket_ts"] >= cutoff]

    n_points = len(filtered_df)
    total_points = len(bbox_df)

    if n_points == 0:
        st.info(
            f"No data in the selected window ({window_hours}h). "
            "Try widening the time window, or click **Fetch & refresh** in the sidebar.",
            icon="ℹ️",
        )
    else:
        if n_points < 3:
            st.warning(
                f"Only **{n_points}** data point(s) visible — click **Fetch & refresh** a few "
                f"more times to build a meaningful chart. "
                f"({total_points} total buckets in the database)",
                icon="💡",
            )

        chart_df = (
            filtered_df.set_index("bucket_ts")[["aircraft_count", "positioned_aircraft_count"]]
            .rename(
                columns={
                    "aircraft_count": "All aircraft",
                    "positioned_aircraft_count": "GPS-positioned",
                }
            )
            .sort_index()
        )

        st.line_chart(chart_df)
        st.caption(
            f"Showing **{n_points}** of {total_points} total 5-minute buckets · "
            f"region: **{selected_label}** · "
            "click Fetch & refresh to add more data points"
        )

        # ── Anomaly table for this bbox ────────────────────────────────────
        bbox_anomalies = anomalies_df[anomalies_df["bbox_name"] == selected_bbox].copy()

        if bbox_anomalies.empty:
            st.caption("No anomaly buckets detected for this region in the current dataset.")
        else:
            with st.expander(
                f"🚨 Anomaly buckets for {selected_label} ({len(bbox_anomalies)} total)"
            ):
                ba = bbox_anomalies.head(10).copy()
                ba["bucket_ts"] = ba["bucket_ts"].astype("datetime64[us, UTC]")
                ba["Time (UTC)"] = ba["bucket_ts"].dt.strftime("%Y-%m-%d %H:%M")
                ba["Direction"] = ba["anomaly_direction"].fillna("—").str.capitalize()
                ba["Aircraft"] = ba["aircraft_count"]
                ba["Baseline"] = ba["baseline_mean_aircraft"].round(1)
                ba["Z-score"] = ba["z_aircraft"].apply(_fmt_z)
                st.dataframe(
                    ba[["Time (UTC)", "Direction", "Aircraft", "Baseline", "Z-score"]],
                    width="stretch",
                    hide_index=True,
                )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
_version = "0.1.0"
with contextlib.suppress(OSError):
    _version = (pathlib.Path(__file__).parent.parent / "VERSION").read_text().strip()

st.caption(
    f"**Air Traffic Pulse** · Analytics Engineering Portfolio Project · "
    f"v{_version} · "
    f"[GitHub](https://github.com/PZawieja/air-traffic-pulse) · "
    f"Data: [OpenSky Network](https://opensky-network.org/)"
)
