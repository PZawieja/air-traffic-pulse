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


# ── Business presentation helpers ─────────────────────────────────────────────


def _traffic_status(z: object, direction: object) -> str:
    """Convert an internal deviation score to a business-friendly status label."""
    if z is None or (isinstance(z, float) and pd.isna(z)):
        return "✓ Normal"
    z_f = float(z)  # type: ignore[arg-type]
    if abs(z_f) >= 3:
        return "🔺 Unusual Spike" if (direction == "spike" or z_f > 0) else "🔻 Unusual Drop"
    if abs(z_f) >= 2:
        return "⚠ Elevated"
    return "✓ Normal"


def _deviation_pct(current: object, baseline: object) -> str:
    """Format the % deviation from normal level for display."""
    if baseline is None or (isinstance(baseline, float) and pd.isna(baseline)):
        return "—"
    b = float(baseline)  # type: ignore[arg-type]
    if b == 0:
        return "—"
    pct = (float(current) - b) / b * 100  # type: ignore[arg-type]
    return f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"


def _fmt_trend(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    v = float(val)  # type: ignore[arg-type]
    return f"+{v:.0f}%" if v >= 0 else f"{v:.0f}%"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("✈️ Air Traffic Pulse")
    st.markdown(
        "Real-time air-traffic analytics built on open data.\n\n"
        "**What this shows**\n\n"
        "Aircraft currently airborne or taxiing over four European cities, "
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

    with st.expander("ℹ️ How traffic monitoring works"):
        st.markdown(
            "**Detecting unusual activity**\n\n"
            "We continuously track what normal traffic looks like for each region "
            "by analysing recent historical patterns. When current traffic deviates "
            "significantly from that pattern, it is flagged automatically.\n\n"
            "**Status labels explained**\n\n"
            "- **✓ Normal** — traffic matches typical patterns\n"
            "- **⚠ Elevated** — noticeably higher or lower than usual, "
            "but within an acceptable range\n"
            "- **🔺 Unusual Spike** — significantly more aircraft than the historical pattern\n"
            "- **🔻 Unusual Drop** — significantly fewer aircraft than the historical pattern\n\n"
            "---\n"
        )
        with st.expander("Technical details"):
            st.markdown(
                "A 28-day rolling baseline (mean and population standard deviation) "
                "is computed per region from the `mart_traffic_baseline_28d` dbt model. "
                "A deviation score (z-score) is calculated for each 5-minute bucket:\n\n"
                "`z = (current − baseline_mean) / baseline_std`\n\n"
                "- **Anomaly** (Unusual Spike/Drop): `|z| ≥ 3`\n"
                "- **Elevated**: `|z| ≥ 2`\n\n"
                "The baseline is recomputed on every `dbt build`."
            )

    st.markdown("---")

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
    "Each run polls the OpenSky API for all four regions and writes "
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

# ── Section 3: Traffic vs Normal Activity ─────────────────────────────────────
st.subheader("📊 Traffic vs Normal Activity")
st.markdown(
    "How does current traffic in each region compare to what we'd normally expect? "
    "The table below highlights any regions where traffic is running unusually high or low."
)

if insights_df.empty:
    st.info("No insights data yet. Click **Fetch & refresh** in the sidebar.", icon="ℹ️")
else:
    ins = insights_df.copy()
    ins["Region"] = ins["bbox_name"].map(lambda x: REGION_FLAGS.get(x, x.title()))
    ins["Status"] = ins.apply(
        lambda r: _traffic_status(r["latest_z_aircraft"], r["latest_anomaly_direction"]),
        axis=1,
    )
    ins["Health Score"] = ins["traffic_health_score"].apply(
        lambda v: int(v) if v is not None and not (isinstance(v, float) and pd.isna(v)) else "—"
    )
    ins["Health"] = ins["traffic_health_label"].fillna("—")
    ins["Current Traffic"] = ins["latest_aircraft_count"]
    ins["Normal Level"] = ins["baseline_mean_aircraft"].round(0).fillna(0).astype(int)
    ins["Deviation"] = ins.apply(
        lambda r: _deviation_pct(r["latest_aircraft_count"], r["baseline_mean_aircraft"]),
        axis=1,
    )
    ins["1h Trend"] = ins["trend_1h_pct"].apply(_fmt_trend)

    business_cols = [
        "Region",
        "Status",
        "Health Score",
        "Health",
        "Current Traffic",
        "Normal Level",
        "Deviation",
        "1h Trend",
    ]
    st.dataframe(ins[business_cols], width="stretch", hide_index=True)
    st.caption(
        "**Health Score** — 0–100, higher is healthier (closer to normal).  "
        "**Current Traffic** — aircraft observed in the latest 5-minute window.  "
        "**Normal Level** — average based on recent historical patterns.  "
        "**Deviation** — how far current traffic is from the normal level.  "
        "**1h Trend** — change vs the preceding hour's average."
    )

    with st.expander("ℹ️ How is 'Normal Traffic' calculated?"):
        st.markdown(
            "We continuously learn what normal traffic looks like for each region by "
            "analysing recent historical patterns.\n\n"
            "**Normal Level** is the average number of aircraft observed over recent history. "
            "When current traffic deviates significantly from that average, it is flagged "
            "with a status indicator.\n\n"
            "**Status labels:**\n\n"
            "- **✓ Normal** — traffic is in line with typical patterns\n"
            "- **⚠ Elevated** — noticeably higher or lower than usual, "
            "but within a tolerable range\n"
            "- **🔺 Unusual Spike** — significantly more aircraft than the historical pattern\n"
            "- **🔻 Unusual Drop** — significantly fewer aircraft than the historical pattern\n"
        )
        with st.expander("Technical note"):
            st.markdown(
                "The model uses a rolling historical baseline and standard deviation "
                "(z-score approach). A deviation score is computed for each 5-minute bucket:\n\n"
                "`z = (current − baseline_mean) / baseline_std`\n\n"
                "An anomaly is flagged when the deviation exceeds 3 standard deviations "
                "(`|z| ≥ 3`). Elevated is flagged at `|z| ≥ 2`. "
                "The baseline window covers the trailing 28 days and is recomputed on every "
                "`dbt build`.\n\n"
                "**Health Score** is derived via exponential decay of the deviation severity:\n\n"
                "`score = 100 × exp(−0.35 × |z|)`, clamped to 0–100.\n\n"
                "Label thresholds: Excellent ≥ 90 · Good ≥ 70 · Watch ≥ 40 · Investigate < 40."
            )

    # Show recent anomaly events if any exist.
    if not anomalies_df.empty:
        with st.expander(
            f"🚨 Unusual activity events ({len(anomalies_df)} detected)", expanded=True
        ):
            anom_display = anomalies_df.head(20).copy()
            anom_display["bucket_ts"] = anom_display["bucket_ts"].astype("datetime64[us, UTC]")
            anom_display["Region"] = anom_display["bbox_name"].map(
                lambda x: REGION_FLAGS.get(x, x.title())
            )
            anom_display["Status"] = anom_display.apply(
                lambda r: _traffic_status(r["z_aircraft"], r["anomaly_direction"]),
                axis=1,
            )
            anom_display["Aircraft"] = anom_display["aircraft_count"]
            anom_display["Normal Level"] = (
                anom_display["baseline_mean_aircraft"].round(0).astype(int)
            )
            anom_display["Deviation"] = anom_display.apply(
                lambda r: _deviation_pct(r["aircraft_count"], r["baseline_mean_aircraft"]),
                axis=1,
            )
            anom_display["Time (UTC)"] = anom_display["bucket_ts"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(
                anom_display[
                    ["Time (UTC)", "Region", "Status", "Aircraft", "Normal Level", "Deviation"]
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
    "- **Normal level** — the historical average for this region (28-day baseline)\n"
    "- The gap between All and GPS-positioned is aircraft whose transponder is active "
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

    # Compact health indicator for the selected region.
    if not insights_df.empty:
        ins_row = insights_df[insights_df["bbox_name"] == selected_bbox]
        if not ins_row.empty:
            _score = ins_row.iloc[0]["traffic_health_score"]
            _label = ins_row.iloc[0]["traffic_health_label"]
            _score_str = (
                str(int(_score))
                if _score is not None and not (isinstance(_score, float) and pd.isna(_score))
                else "—"
            )
            _label_str = (
                _label
                if _label is not None and not (isinstance(_label, float) and pd.isna(_label))
                else "—"
            )  # noqa: E501
            st.metric(
                label="Current Health Score",
                value=f"{_score_str} / 100",
                help=(
                    f"Health: **{_label_str}**  —  "
                    "Summarises how close current traffic is to its normal range. "
                    "100 = perfectly normal. See 'How is Normal Traffic calculated?' above for details."
                ),
            )

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

        # Context sentence: unusual activity check for this region in the last 24h.
        recent_cutoff = bbox_df["bucket_ts"].max() - pd.Timedelta(hours=24)
        bbox_anomalies = anomalies_df[anomalies_df["bbox_name"] == selected_bbox].copy()
        if not bbox_anomalies.empty:
            bbox_anomalies["bucket_ts"] = bbox_anomalies["bucket_ts"].astype("datetime64[us, UTC]")
            recent_events = bbox_anomalies[bbox_anomalies["bucket_ts"] >= recent_cutoff]
        else:
            recent_events = bbox_anomalies  # empty

        if not recent_events.empty:
            st.warning(
                f"⚠ Unusual activity detected in **{selected_label}** in the last 24 hours "
                f"({len(recent_events)} event(s)). See the activity log below the chart.",
                icon="🔔",
            )
        else:
            st.success(
                f"Traffic in **{selected_label}** is within the normal operating range.",
                icon="✅",
            )

        # Add historical normal level as a reference line.
        baseline_mean: float | None = None
        if not insights_df.empty:
            row_ins = insights_df[insights_df["bbox_name"] == selected_bbox]
            if not row_ins.empty:
                val = row_ins.iloc[0]["baseline_mean_aircraft"]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    baseline_mean = float(val)

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

        if baseline_mean is not None:
            chart_df["Normal level (28d avg)"] = baseline_mean

        st.line_chart(chart_df)
        st.caption(
            f"Showing **{n_points}** of {total_points} total 5-minute buckets · "
            f"region: **{selected_label}** · "
            "click Fetch & refresh to add more data points"
        )

        # Unusual activity log for this bbox.
        if not bbox_anomalies.empty:
            with st.expander(
                f"🚨 Unusual activity log for {selected_label} ({len(bbox_anomalies)} events)"
            ):
                ba = bbox_anomalies.head(10).copy()
                ba["Time (UTC)"] = ba["bucket_ts"].dt.strftime("%Y-%m-%d %H:%M")
                ba["Status"] = ba.apply(
                    lambda r: _traffic_status(r["z_aircraft"], r["anomaly_direction"]),
                    axis=1,
                )
                ba["Aircraft"] = ba["aircraft_count"]
                ba["Normal Level"] = ba["baseline_mean_aircraft"].round(0).astype(int)
                ba["Deviation"] = ba.apply(
                    lambda r: _deviation_pct(r["aircraft_count"], r["baseline_mean_aircraft"]),
                    axis=1,
                )
                st.dataframe(
                    ba[["Time (UTC)", "Status", "Aircraft", "Normal Level", "Deviation"]],
                    width="stretch",
                    hide_index=True,
                )
        else:
            st.caption(f"No unusual activity detected for {selected_label} in the current dataset.")

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
