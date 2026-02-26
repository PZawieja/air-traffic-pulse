"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Built-in bounding-box presets  (lamin, lomin, lamax, lomax)
# ---------------------------------------------------------------------------
BBOX_PRESETS: dict[str, dict[str, float]] = {
    "berlin":    {"lamin": 52.3, "lomin": 13.0, "lamax": 52.7, "lomax": 13.8},
    "frankfurt": {"lamin": 49.9, "lomin":  8.3, "lamax": 50.2, "lomax":  8.9},
    "london":    {"lamin": 51.3, "lomin": -0.6, "lamax": 51.7, "lomax":  0.3},
    "warsaw":    {"lamin": 52.0, "lomin": 20.7, "lamax": 52.4, "lomax": 21.3},
}

# Human-readable display names with country flags, used in the dashboard.
REGION_DISPLAY: dict[str, str] = {
    "berlin":    "🇩🇪 Berlin",
    "frankfurt": "🇩🇪 Frankfurt",
    "london":    "🇬🇧 London",
    "warsaw":    "🇵🇱 Warsaw",
}


class Settings(BaseSettings):
    """Central settings object.  Values are read from the environment or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenSky credentials — both optional; anonymous access is rate-limited.
    opensky_username: str | None = None
    opensky_password: str | None = None

    # DuckDB file path (resolved at runtime relative to the repo root).
    duckdb_path: str = "./data/air_traffic_pulse.duckdb"

    # Comma-separated preset names to ingest on each run.
    opensky_bbox_presets: str = "berlin,frankfurt,london"

    # Demo mode: skip all network calls and load bundled fixture JSON instead.
    # Set AIR_TRAFFIC_PULSE_DEMO_MODE=1 to enable.
    air_traffic_pulse_demo_mode: bool = False

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def bbox_preset_list(self) -> list[str]:
        """Return the individual preset names as a list."""
        return [name.strip() for name in self.opensky_bbox_presets.split(",") if name.strip()]

    @property
    def active_bboxes(self) -> dict[str, dict[str, float]]:
        """Return the bounding-box dicts for the configured presets."""
        return {name: BBOX_PRESETS[name] for name in self.bbox_preset_list}

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("opensky_bbox_presets")
    @classmethod
    def validate_bbox_presets(cls, value: str) -> str:
        names = [n.strip() for n in value.split(",") if n.strip()]
        unknown = [n for n in names if n not in BBOX_PRESETS]
        if unknown:
            available = ", ".join(sorted(BBOX_PRESETS))
            raise ValueError(
                f"Unknown bbox preset(s): {unknown!r}. "
                f"Available presets: {available}. "
                "Add custom presets to BBOX_PRESETS in config.py."
            )
        if not names:
            raise ValueError("OPENSKY_BBOX_PRESETS must contain at least one preset name.")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application settings singleton (loaded once, then cached)."""
    return Settings()
