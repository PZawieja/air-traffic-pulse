"""DuckDB connection factory and schema initialisation."""

from __future__ import annotations

import pathlib

import duckdb

from air_traffic_pulse.log import get_logger

log = get_logger(__name__)

_SCHEMA_SQL = pathlib.Path(__file__).with_name("schema.sql")


def get_connection(db_path: str = "./data/air_traffic_pulse.duckdb") -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB file at *db_path*.

    The parent directory is created automatically if it does not exist.
    Call :func:`init_schema` on the returned connection before first use.
    """
    resolved = pathlib.Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    log.debug("Connecting to DuckDB at %s", resolved)
    return duckdb.connect(str(resolved))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Execute ``warehouse/schema.sql`` to create all tables if they don't exist.

    Idempotent — safe to call on every startup.  DuckDB's ``execute()``
    handles one statement at a time, so the SQL file is split on ``';'``.
    """
    if not _SCHEMA_SQL.exists():
        log.warning("schema.sql not found at %s — skipping schema init.", _SCHEMA_SQL)
        return

    ddl = _SCHEMA_SQL.read_text(encoding="utf-8")
    for stmt in ddl.split(";"):
        stripped = stmt.strip()
        if stripped:
            con.execute(stripped)

    log.debug("Schema initialised from %s.", _SCHEMA_SQL.name)
