"""Minimal CLI entry-point for Air Traffic Pulse.

Usage:
    python -m air_traffic_pulse ingest   — pull live states from OpenSky into DuckDB
    python -m air_traffic_pulse dbt      — run dbt deps + dbt build
    python -m air_traffic_pulse app      — launch the Streamlit dashboard
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from air_traffic_pulse.log import get_logger

log = get_logger(__name__)

_COMMANDS = ("ingest", "dbt", "app")


def _usage() -> None:
    print(
        "Usage: python -m air_traffic_pulse <command>\n\n"
        "Commands:\n"
        "  ingest   Pull live aircraft states from OpenSky into DuckDB\n"
        "  dbt      Run dbt deps + dbt build\n"
        "  app      Launch the Streamlit dashboard\n",
        file=sys.stderr,
    )


def _run_ingest() -> None:
    from ingestion.load_states import main as ingest_main

    log.info("Starting ingestion run …")
    ingest_main()


def _run_dbt() -> None:
    # Resolve the dbt CLI from the same virtualenv as the running Python so
    # the system dbt-fusion (or any other global dbt) cannot shadow it.
    _dbt_bin = str(pathlib.Path(sys.executable).parent / "dbt")
    _DBT_FLAGS = ["--project-dir", "dbt", "--profiles-dir", "dbt"]

    log.info("Running: dbt deps  (%s)", _dbt_bin)
    result = subprocess.run([_dbt_bin, "deps", *_DBT_FLAGS], check=False)
    if result.returncode != 0:
        log.error("dbt deps failed (exit %d).", result.returncode)
        sys.exit(result.returncode)

    log.info("Running: dbt build  (%s)", _dbt_bin)
    result = subprocess.run([_dbt_bin, "build", *_DBT_FLAGS], check=False)
    if result.returncode != 0:
        log.error("dbt build failed (exit %d).", result.returncode)
        sys.exit(result.returncode)


def _run_app() -> None:
    log.info("Launching Streamlit dashboard …")
    result = subprocess.run(
        ["streamlit", "run", "app/streamlit_app.py"],
        check=False,
    )
    sys.exit(result.returncode)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        _usage()
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "ingest":
            _run_ingest()
        elif command == "dbt":
            _run_dbt()
        elif command == "app":
            _run_app()
    except KeyboardInterrupt:
        log.info("Interrupted.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error in '%s': %s", command, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
