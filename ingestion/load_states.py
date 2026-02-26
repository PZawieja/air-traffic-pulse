"""Orchestration: fetch aircraft states for configured bboxes and load into DuckDB.

Run via:
    python -m air_traffic_pulse ingest
    make ingest
"""

from __future__ import annotations

import datetime as dt

from warehouse.duckdb_conn import get_connection

from air_traffic_pulse.config import get_settings
from air_traffic_pulse.log import get_logger
from ingestion.opensky_client import fetch_states

log = get_logger(__name__)


def _states_to_rows(
    api_response: dict,
    bbox_name: str,
    ingested_at: dt.datetime,
) -> list[dict]:
    """Convert the raw OpenSky JSON into a list of flat row dicts."""
    states = api_response.get("states") or []
    rows = []
    for s in states:
        rows.append(
            {
                "ingested_at": ingested_at,
                "bbox_name": bbox_name,
                "icao24": s[0],
                "callsign": (s[1] or "").strip() or None,
                "origin_country": s[2],
                "time_position": s[3],
                "last_contact": s[4],
                "longitude": s[5],
                "latitude": s[6],
                "baro_altitude": s[7],
                "on_ground": s[8],
                "velocity": s[9],
                "true_track": s[10],
                "vertical_rate": s[11],
                "geo_altitude": s[13],
                "squawk": s[14],
                "spi": s[15],
                "position_source": s[16],
            }
        )
    return rows


def main() -> None:
    """Entry-point called by the CLI."""
    settings = get_settings()
    con = get_connection(settings.duckdb_path)
    ingested_at = dt.datetime.now(tz=dt.UTC)

    total_rows = 0
    for bbox_name, bbox in settings.active_bboxes.items():
        log.info("Fetching states for preset '%s' …", bbox_name)
        try:
            response = fetch_states(**bbox)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to fetch '%s': %s", bbox_name, exc)
            continue

        rows = _states_to_rows(response, bbox_name, ingested_at)
        if rows:
            import pandas as pd  # local import — keep top-level deps explicit

            df = pd.DataFrame(rows)  # noqa: F841  — referenced by DuckDB via local-var scan
            con.execute("INSERT INTO raw_states SELECT * FROM df")
            log.info("Loaded %d rows for '%s'.", len(rows), bbox_name)
            total_rows += len(rows)
        else:
            log.info("No aircraft found in '%s' at this time.", bbox_name)

    log.info("Ingestion complete — %d total rows loaded.", total_rows)
    con.close()


if __name__ == "__main__":
    main()
