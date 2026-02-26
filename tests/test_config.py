"""Tests for the Settings / configuration module."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from air_traffic_pulse.config import BBOX_PRESETS, Settings, get_settings


class TestDefaultSettings:
    """Default settings load without any environment customisation."""

    def test_default_duckdb_path(self):
        s = Settings()
        assert s.duckdb_path == "./data/air_traffic_pulse.duckdb"

    def test_default_bbox_presets_string(self):
        s = Settings()
        assert s.opensky_bbox_presets == "berlin,frankfurt,london"

    def test_default_bbox_preset_list(self):
        s = Settings()
        assert s.bbox_preset_list == ["berlin", "frankfurt", "london"]

    def test_credentials_default_to_none(self):
        s = Settings()
        assert s.opensky_username is None
        assert s.opensky_password is None


class TestActiveBboxes:
    """active_bboxes returns the correct dicts for the default presets."""

    def test_active_bboxes_keys(self):
        s = Settings()
        assert set(s.active_bboxes.keys()) == {"berlin", "frankfurt", "london"}

    def test_berlin_coords(self):
        s = Settings()
        berlin = s.active_bboxes["berlin"]
        assert berlin["lamin"] == pytest.approx(52.3)
        assert berlin["lomin"] == pytest.approx(13.0)
        assert berlin["lamax"] == pytest.approx(52.7)
        assert berlin["lomax"] == pytest.approx(13.8)


class TestBboxValidation:
    """Validator rejects unknown preset names with a clear error."""

    def test_unknown_preset_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            Settings(opensky_bbox_presets="berlin,atlantis")
        assert "atlantis" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            Settings(opensky_bbox_presets="")

    def test_single_valid_preset(self):
        s = Settings(opensky_bbox_presets="london")
        assert s.bbox_preset_list == ["london"]

    def test_all_builtin_presets_valid(self):
        preset_str = ",".join(BBOX_PRESETS.keys())
        s = Settings(opensky_bbox_presets=preset_str)
        assert set(s.bbox_preset_list) == set(BBOX_PRESETS.keys())


class TestGetSettings:
    """get_settings() is memoised and returns a Settings instance."""

    def test_returns_settings_instance(self):
        result = get_settings()
        assert isinstance(result, Settings)

    def test_is_memoised(self):
        assert get_settings() is get_settings()
