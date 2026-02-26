"""End-to-end smoke test for demo mode: fixture ingest, no network."""

from __future__ import annotations

import pathlib

import duckdb
import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear the lru_cache before and after each test so env-var changes take effect."""
    from air_traffic_pulse.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestDemoModeIngestion:
    def test_ingest_loads_rows_without_network(self, tmp_path: pathlib.Path, monkeypatch):
        """Demo-mode ingest must populate raw.opensky_states using fixture files only."""
        db_file = str(tmp_path / "demo_test.duckdb")
        monkeypatch.setenv("AIR_TRAFFIC_PULSE_DEMO_MODE", "1")
        monkeypatch.setenv("DUCKDB_PATH", db_file)

        from ingestion.load_states import main

        main()  # must not raise and must not make any network calls

        con = duckdb.connect(db_file, read_only=True)
        state_count = con.execute("SELECT count(*) FROM raw.opensky_states").fetchone()[0]
        run_count = con.execute("SELECT count(*) FROM raw.ingestion_runs").fetchone()[0]
        status = con.execute(
            "SELECT status FROM raw.ingestion_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()[0]
        con.close()

        assert state_count > 0, "Expected rows in raw.opensky_states after demo ingest"
        assert run_count == 1, "Expected exactly one ingestion run record"
        assert status == "success", f"Expected run status 'success', got {status!r}"

    def test_ingest_covers_all_configured_bboxes(self, tmp_path: pathlib.Path, monkeypatch):
        """Each configured bbox must produce at least one row."""
        db_file = str(tmp_path / "bbox_test.duckdb")
        monkeypatch.setenv("AIR_TRAFFIC_PULSE_DEMO_MODE", "1")
        monkeypatch.setenv("DUCKDB_PATH", db_file)

        from ingestion.load_states import main

        main()

        con = duckdb.connect(db_file, read_only=True)
        bboxes = {
            r[0]
            for r in con.execute("SELECT DISTINCT bbox_name FROM raw.opensky_states").fetchall()
        }
        con.close()

        # Default presets: berlin, frankfurt, london
        assert "berlin" in bboxes
        assert "frankfurt" in bboxes
        assert "london" in bboxes

    def test_london_fixture_has_distinct_aircraft(self, tmp_path: pathlib.Path, monkeypatch):
        """London fixture has 4 distinct aircraft (from opensky_states_sample_london.json)."""
        db_file = str(tmp_path / "london_test.duckdb")
        monkeypatch.setenv("AIR_TRAFFIC_PULSE_DEMO_MODE", "1")
        monkeypatch.setenv("DUCKDB_PATH", db_file)

        from ingestion.load_states import main

        main()

        con = duckdb.connect(db_file, read_only=True)
        london_count = con.execute(
            "SELECT count(DISTINCT icao24) FROM raw.opensky_states WHERE bbox_name = 'london'"
        ).fetchone()[0]
        con.close()

        assert london_count == 4
