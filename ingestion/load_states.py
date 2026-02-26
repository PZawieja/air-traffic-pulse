"""Orchestration: fetch aircraft states for configured bboxes and persist into DuckDB.

Run via:
    python -m air_traffic_pulse ingest          # live mode (requires network)
    AIR_TRAFFIC_PULSE_DEMO_MODE=1 make ingest   # demo mode (offline, uses fixture data)
    make ingest                                  # make target
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import time
import uuid

from warehouse.duckdb_conn import get_connection, init_schema

from air_traffic_pulse.config import get_settings
from air_traffic_pulse.log import get_logger
from ingestion.opensky_client import OpenSkyClient, StateRow

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column ordering must mirror raw.opensky_states in schema.sql exactly.
# ---------------------------------------------------------------------------
_STATE_COLUMNS: tuple[str, ...] = (
    "ingestion_ts",
    "data_ts",
    "bbox_name",
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "last_contact",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
    "true_track",
    "vertical_rate",
    "sensors",
    "geo_altitude",
    "squawk",
    "spi",
    "position_source",
)

_INSERT_STATES = (
    f"INSERT INTO raw.opensky_states ({', '.join(_STATE_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * len(_STATE_COLUMNS))})"
)

_INSERT_RUN = """
    INSERT INTO raw.ingestion_runs (run_id, started_at, status, records_loaded)
    VALUES (?, ?, 'running', 0)
"""

_UPDATE_RUN = """
    UPDATE raw.ingestion_runs
    SET finished_at = ?, status = ?, records_loaded = ?, error_msg = ?
    WHERE run_id = ?
"""

# ---------------------------------------------------------------------------
# Demo-mode fixture mapping
# ---------------------------------------------------------------------------
_FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"

_DEMO_FIXTURE_MAP: dict[str, pathlib.Path] = {
    "berlin": _FIXTURES_DIR / "opensky_states_sample.json",
    "frankfurt": _FIXTURES_DIR / "opensky_states_sample.json",
    "london": _FIXTURES_DIR / "opensky_states_sample_london.json",
    "warsaw": _FIXTURES_DIR / "opensky_states_sample.json",
}


def _load_demo_payload(bbox_name: str) -> dict:
    """Return a fixture payload for *bbox_name*, stamped with the current time."""
    fixture_path = _DEMO_FIXTURE_MAP.get(
        bbox_name,
        next(iter(_DEMO_FIXTURE_MAP.values())),  # fall back to first fixture
    )
    payload: dict = json.loads(fixture_path.read_text(encoding="utf-8"))
    # Stamp with current unix time so the data looks fresh in the dashboard.
    payload["time"] = int(dt.datetime.now(tz=dt.UTC).timestamp())
    return payload


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rows_to_tuples(rows: list[StateRow]) -> list[tuple]:
    """Convert StateRow dicts to positional tuples aligned with _STATE_COLUMNS."""
    return [tuple(row[col] for col in _STATE_COLUMNS) for row in rows]  # type: ignore[literal-required]


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry-point called by the CLI.

    In *live mode* (default) each bbox is polled from the OpenSky Network.
    In *demo mode* (``AIR_TRAFFIC_PULSE_DEMO_MODE=1``) bundled fixture JSON
    files are loaded instead — no network required.

    Raises on unrecoverable error (after marking the run as failed in DuckDB).
    """
    settings = get_settings()
    demo_mode = settings.air_traffic_pulse_demo_mode

    if demo_mode:
        log.info("Demo mode enabled — using fixture data (no network calls).")
    else:
        client = OpenSkyClient(
            username=settings.opensky_username,
            password=settings.opensky_password,
        )

    con = get_connection(settings.duckdb_path)
    init_schema(con)

    run_id = str(uuid.uuid4())
    started_at = dt.datetime.now(tz=dt.UTC)
    con.execute(_INSERT_RUN, [run_id, started_at])
    log.info("Ingestion run started  run_id=%s  demo=%s", run_id, demo_mode)

    total_rows = 0
    try:
        bboxes = list(settings.active_bboxes.items())
        for i, (bbox_name, bbox) in enumerate(bboxes):
            if i > 0 and not demo_mode:
                # Be polite to the OpenSky API between bbox calls.
                time.sleep(1.0)

            log.info("[%d/%d] Processing bbox '%s' …", i + 1, len(bboxes), bbox_name)

            if demo_mode:
                payload = _load_demo_payload(bbox_name)
            else:
                payload = client.get_states_all_bbox(**bbox)  # type: ignore[possibly-undefined]

            rows = OpenSkyClient.parse_states(payload, bbox_name, started_at)

            if rows:
                con.executemany(_INSERT_STATES, _rows_to_tuples(rows))
                total_rows += len(rows)
                log.info(
                    "  → %d rows loaded for '%s'  (total so far: %d)",
                    len(rows),
                    bbox_name,
                    total_rows,
                )
            else:
                log.info("  → no aircraft found in '%s' at this time.", bbox_name)

        finished_at = dt.datetime.now(tz=dt.UTC)
        con.execute(_UPDATE_RUN, [finished_at, "success", total_rows, None, run_id])
        log.info(
            "Ingestion run complete  run_id=%s  total_rows=%d  duration=%.1fs",
            run_id,
            total_rows,
            (finished_at - started_at).total_seconds(),
        )

    except Exception as exc:
        finished_at = dt.datetime.now(tz=dt.UTC)
        con.execute(_UPDATE_RUN, [finished_at, "failed", total_rows, str(exc), run_id])
        log.error("Ingestion run FAILED  run_id=%s  error=%s", run_id, exc)
        raise

    finally:
        con.close()


if __name__ == "__main__":
    main()
