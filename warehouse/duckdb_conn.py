"""DuckDB connection factory and schema initialisation."""

from __future__ import annotations

import pathlib

import duckdb

from air_traffic_pulse.log import get_logger

log = get_logger(__name__)

_SCHEMA_SQL = pathlib.Path(__file__).with_name("schema.sql")


def get_connection(db_path: str = "./data/air_traffic_pulse.duckdb") -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB file and ensure the schema is initialised.

    Parameters
    ----------
    db_path:
        Path to the ``.duckdb`` file.  The parent directory is created if it
        does not already exist.
    """
    resolved = pathlib.Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    log.debug("Connecting to DuckDB at %s", resolved)
    con = duckdb.connect(str(resolved))
    _ensure_schema(con)
    return con


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Run schema.sql once to create tables if they don't exist yet."""
    if not _SCHEMA_SQL.exists():
        log.warning("schema.sql not found at %s — skipping schema init.", _SCHEMA_SQL)
        return
    ddl = _SCHEMA_SQL.read_text(encoding="utf-8")
    con.executescript(ddl)
    log.debug("Schema initialised from %s.", _SCHEMA_SQL.name)
