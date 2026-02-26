"""Air Traffic Pulse — Streamlit dashboard.

Scaffold only.  Run with:
    make app
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

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

st.info(
    "Dashboard coming soon.  "
    f"Configured bboxes: **{', '.join(settings.bbox_preset_list)}**.  "
    "Run `make ingest` to populate the database, then refresh.",
    icon="ℹ️",
)

with st.expander("Active bounding-box presets"):
    for name, bbox in settings.active_bboxes.items():
        st.write(f"**{name}**: {bbox}")
