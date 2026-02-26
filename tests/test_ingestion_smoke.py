"""Smoke test for the end-to-end write path — no network calls."""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime

import pytest
from ingestion.load_states import _INSERT_STATES, _STATE_COLUMNS, _rows_to_tuples
from ingestion.opensky_client import OpenSkyClient
from warehouse.duckdb_conn import get_connection, init_schema

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "opensky_states_sample.json"
_INGESTION_TS = datetime(2024, 2, 25, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def tmp_db(tmp_path: pathlib.Path):
    """Yield an initialised DuckDB connection backed by a temp file."""
    db_file = str(tmp_path / "test.duckdb")
    con = get_connection(db_file)
    init_schema(con)
    yield con
    con.close()


@pytest.fixture()
def parsed_rows() -> list[dict]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return OpenSkyClient.parse_states(payload, bbox_name="berlin", ingestion_ts=_INGESTION_TS)


class TestSchemaInit:
    def test_opensky_states_table_exists(self, tmp_db):
        result = tmp_db.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'raw' AND table_name = 'opensky_states'"
        ).fetchone()
        assert result[0] == 1

    def test_ingestion_runs_table_exists(self, tmp_db):
        result = tmp_db.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'raw' AND table_name = 'ingestion_runs'"
        ).fetchone()
        assert result[0] == 1

    def test_init_schema_is_idempotent(self, tmp_db):
        """Calling init_schema twice must not raise."""
        init_schema(tmp_db)


class TestInsertAndQuery:
    def test_insert_two_rows(self, tmp_db, parsed_rows):
        tmp_db.executemany(_INSERT_STATES, _rows_to_tuples(parsed_rows))
        count = tmp_db.execute("SELECT count(*) FROM raw.opensky_states").fetchone()[0]
        assert count == 2

    def test_row_count_matches_parsed(self, tmp_db, parsed_rows):
        tmp_db.executemany(_INSERT_STATES, _rows_to_tuples(parsed_rows))
        count = tmp_db.execute("SELECT count(*) FROM raw.opensky_states").fetchone()[0]
        assert count == len(parsed_rows)

    def test_bbox_name_stored(self, tmp_db, parsed_rows):
        tmp_db.executemany(_INSERT_STATES, _rows_to_tuples(parsed_rows))
        names = {
            r[0]
            for r in tmp_db.execute("SELECT DISTINCT bbox_name FROM raw.opensky_states").fetchall()
        }
        assert names == {"berlin"}

    def test_sensors_stored_as_json_string(self, tmp_db, parsed_rows):
        tmp_db.executemany(_INSERT_STATES, _rows_to_tuples(parsed_rows))
        sensors_vals = [
            r[0]
            for r in tmp_db.execute(
                "SELECT sensors FROM raw.opensky_states ORDER BY icao24"
            ).fetchall()
        ]
        # Row with icao24=3c6444 has sensors; row with 4ca7b5 has NULL.
        non_null = [v for v in sensors_vals if v is not None]
        assert len(non_null) == 1
        assert json.loads(non_null[0]) == [1001, 1002]

    def test_null_fields_accepted(self, tmp_db, parsed_rows):
        """Rows with multiple NULL fields must insert without error."""
        tmp_db.executemany(_INSERT_STATES, _rows_to_tuples(parsed_rows))
        row = tmp_db.execute(
            "SELECT longitude, latitude, baro_altitude FROM raw.opensky_states "
            "WHERE icao24 = '4ca7b5'"
        ).fetchone()
        assert row == (None, None, None)

    def test_column_count_matches_schema(self, tmp_db):
        """Number of columns in raw.opensky_states must match _STATE_COLUMNS."""
        cols = tmp_db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'opensky_states'"
        ).fetchall()
        assert len(cols) == len(_STATE_COLUMNS)
