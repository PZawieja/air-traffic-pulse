"""Unit tests for OpenSkyClient.parse_states — no network calls."""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime

import pytest
from ingestion.opensky_client import OpenSkyClient

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "opensky_states_sample.json"
_BBOX_NAME = "berlin"
_INGESTION_TS = datetime(2024, 2, 25, 12, 0, 0, tzinfo=UTC)

# All column keys that every parsed row must contain.
_REQUIRED_KEYS = {
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
}


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed_rows(payload: dict) -> list[dict]:
    return OpenSkyClient.parse_states(payload, bbox_name=_BBOX_NAME, ingestion_ts=_INGESTION_TS)


class TestParseStatesLength:
    def test_two_rows_returned(self, parsed_rows):
        assert len(parsed_rows) == 2


class TestRequiredKeys:
    def test_all_required_keys_present_row0(self, parsed_rows):
        assert _REQUIRED_KEYS.issubset(parsed_rows[0].keys())

    def test_all_required_keys_present_row1(self, parsed_rows):
        assert _REQUIRED_KEYS.issubset(parsed_rows[1].keys())


class TestRow0:
    """Row 0: DLH1234, Germany, sensors list, all numeric fields present."""

    def test_icao24(self, parsed_rows):
        assert parsed_rows[0]["icao24"] == "3c6444"

    def test_callsign_stripped(self, parsed_rows):
        # Raw value is "DLH1234 " — trailing space must be stripped.
        assert parsed_rows[0]["callsign"] == "DLH1234"

    def test_origin_country(self, parsed_rows):
        assert parsed_rows[0]["origin_country"] == "Germany"

    def test_on_ground_false(self, parsed_rows):
        assert parsed_rows[0]["on_ground"] is False

    def test_baro_altitude(self, parsed_rows):
        assert parsed_rows[0]["baro_altitude"] == pytest.approx(9500.0)

    def test_sensors_encoded_as_json_string(self, parsed_rows):
        sensors = parsed_rows[0]["sensors"]
        assert isinstance(sensors, str)
        assert json.loads(sensors) == [1001, 1002]

    def test_bbox_name_propagated(self, parsed_rows):
        assert parsed_rows[0]["bbox_name"] == _BBOX_NAME

    def test_ingestion_ts_propagated(self, parsed_rows):
        assert parsed_rows[0]["ingestion_ts"] == _INGESTION_TS

    def test_data_ts_from_payload_time(self, parsed_rows):
        assert parsed_rows[0]["data_ts"] == 1708900000


class TestRow1:
    """Row 1: anonymous Irish aircraft on ground, most fields null."""

    def test_icao24(self, parsed_rows):
        assert parsed_rows[1]["icao24"] == "4ca7b5"

    def test_callsign_none_from_null(self, parsed_rows):
        assert parsed_rows[1]["callsign"] is None

    def test_sensors_none_from_null(self, parsed_rows):
        assert parsed_rows[1]["sensors"] is None

    def test_longitude_none(self, parsed_rows):
        assert parsed_rows[1]["longitude"] is None

    def test_latitude_none(self, parsed_rows):
        assert parsed_rows[1]["latitude"] is None

    def test_on_ground_true(self, parsed_rows):
        assert parsed_rows[1]["on_ground"] is True

    def test_bbox_name_propagated(self, parsed_rows):
        assert parsed_rows[1]["bbox_name"] == _BBOX_NAME

    def test_ingestion_ts_propagated(self, parsed_rows):
        assert parsed_rows[1]["ingestion_ts"] == _INGESTION_TS

    def test_data_ts_from_payload_time(self, parsed_rows):
        # data_ts comes from payload["time"], not the per-vector time_position.
        assert parsed_rows[1]["data_ts"] == 1708900000


class TestParseStatesValidation:
    def test_missing_time_raises(self):
        with pytest.raises(ValueError, match="'time'"):
            OpenSkyClient.parse_states({"states": []}, "berlin", _INGESTION_TS)

    def test_missing_states_raises(self):
        with pytest.raises(ValueError, match="'states'"):
            OpenSkyClient.parse_states({"time": 0}, "berlin", _INGESTION_TS)

    def test_empty_states_returns_empty_list(self):
        rows = OpenSkyClient.parse_states({"time": 0, "states": []}, "berlin", _INGESTION_TS)
        assert rows == []

    def test_null_states_returns_empty_list(self):
        rows = OpenSkyClient.parse_states({"time": 0, "states": None}, "berlin", _INGESTION_TS)
        assert rows == []
