"""HTTP client for the OpenSky Network REST API.

Docs: https://openskynetwork.github.io/opensky-api/rest.html

Only the ``/states/all`` endpoint is used at this stage.
Authentication is optional but strongly recommended to avoid strict rate limits.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, TypedDict

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from air_traffic_pulse.log import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Typed output row — mirrors raw.opensky_states columns exactly
# ---------------------------------------------------------------------------


class StateRow(TypedDict):
    ingestion_ts: datetime
    data_ts: int | None
    bbox_name: str
    icao24: str | None
    callsign: str | None
    origin_country: str | None
    time_position: int | None
    last_contact: int | None
    longitude: float | None
    latitude: float | None
    baro_altitude: float | None
    on_ground: bool | None
    velocity: float | None
    true_track: float | None
    vertical_rate: float | None
    sensors: str | None
    geo_altitude: float | None
    squawk: str | None
    spi: bool | None
    position_source: int | None


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _should_retry(exc: BaseException) -> bool:
    """Return True for transient network errors and 429 / 5xx HTTP responses."""
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        if response is not None:
            return response.status_code == 429 or response.status_code >= 500
        return False
    return isinstance(exc, requests.exceptions.RequestException)


_RETRY_KWARGS: dict[str, Any] = {
    "stop": stop_after_attempt(5),
    "wait": wait_random_exponential(multiplier=1, min=2, max=60),
    "retry": retry_if_exception(_should_retry),
    "before_sleep": before_sleep_log(log, logging.WARNING),
    "reraise": True,
}


# ---------------------------------------------------------------------------
# Safe type-cast helpers
# ---------------------------------------------------------------------------


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_bool(v: Any) -> bool | None:
    if v is None:
        return None
    return bool(v)


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenSkyClient:
    """Thin wrapper around the OpenSky Network REST API.

    Parameters
    ----------
    base_url:
        API root URL (override in tests to point at a mock server).
    username / password:
        Optional HTTP Basic Auth credentials.  Anonymous access is rate-limited
        to roughly one request per 10 seconds.
    timeout_s:
        Per-request timeout in seconds.
    """

    DEFAULT_BASE_URL = "https://opensky-network.org/api"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        username: str | None = None,
        password: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._session = requests.Session()
        if username and password:
            self._session.auth = (username, password)
            log.debug("OpenSkyClient: authenticated as '%s'.", username)
        else:
            log.debug("OpenSkyClient: anonymous mode (rate-limited).")

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    @retry(**_RETRY_KWARGS)
    def get_states_all_bbox(
        self,
        lamin: float,
        lomin: float,
        lamax: float,
        lomax: float,
    ) -> dict[str, Any]:
        """Fetch current aircraft states within the given bounding box.

        Retries automatically on transient network errors, HTTP 429, and 5xx
        responses (up to 5 attempts with exponential back-off and jitter).

        Returns
        -------
        Raw JSON response dict (keys: ``time``, ``states``).
        Raises ``requests.HTTPError`` on non-retryable non-2xx responses.
        """
        url = f"{self._base_url}/states/all"
        params: dict[str, float] = {
            "lamin": lamin,
            "lomin": lomin,
            "lamax": lamax,
            "lomax": lomax,
        }
        log.info(
            "GET %s  bbox=(lamin=%.2f lomin=%.2f lamax=%.2f lomax=%.2f)",
            url,
            lamin,
            lomin,
            lamax,
            lomax,
        )
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_states(
        payload: dict[str, Any],
        bbox_name: str,
        ingestion_ts: datetime,
    ) -> list[StateRow]:
        """Convert a raw ``/states/all`` JSON response into typed row dicts.

        Parameters
        ----------
        payload:
            The dict returned by :meth:`get_states_all_bbox`.
        bbox_name:
            The human-readable preset name (e.g. ``"berlin"``).
        ingestion_ts:
            The UTC datetime at which this ingestion run started.

        Returns
        -------
        List of :class:`StateRow` dicts, one per aircraft state vector.

        Raises
        ------
        ValueError
            If the payload is missing the required ``"time"`` or ``"states"``
            keys, indicating a malformed or unexpected API response.
        """
        if "time" not in payload:
            raise ValueError("OpenSky payload is missing the required 'time' field.")
        if "states" not in payload:
            raise ValueError("OpenSky payload is missing the required 'states' field.")

        data_ts: int | None = _safe_int(payload["time"])
        raw_states: list[list[Any]] = payload["states"] or []

        rows: list[StateRow] = []
        for s in raw_states:
            if len(s) < 17:
                log.warning(
                    "Skipping short state vector for icao24=%r (expected 17 fields, got %d).",
                    s[0] if s else "?",
                    len(s),
                )
                continue

            # Field 12 is sensors: list[int] | None
            sensors_raw = s[12]
            sensors: str | None = json.dumps(sensors_raw) if isinstance(sensors_raw, list) else None

            # Callsign is trimmed; empty string → None
            callsign_raw = s[1]
            callsign: str | None = callsign_raw.strip() if isinstance(callsign_raw, str) else None
            if callsign == "":
                callsign = None

            row: StateRow = {
                "ingestion_ts": ingestion_ts,
                "data_ts": data_ts,
                "bbox_name": bbox_name,
                "icao24": _safe_str(s[0]),
                "callsign": callsign,
                "origin_country": _safe_str(s[2]),
                "time_position": _safe_int(s[3]),
                "last_contact": _safe_int(s[4]),
                "longitude": _safe_float(s[5]),
                "latitude": _safe_float(s[6]),
                "baro_altitude": _safe_float(s[7]),
                "on_ground": _safe_bool(s[8]),
                "velocity": _safe_float(s[9]),
                "true_track": _safe_float(s[10]),
                "vertical_rate": _safe_float(s[11]),
                "sensors": sensors,
                "geo_altitude": _safe_float(s[13]),
                "squawk": _safe_str(s[14]),
                "spi": _safe_bool(s[15]),
                "position_source": _safe_int(s[16]),
            }
            rows.append(row)

        log.debug(
            "parse_states: bbox=%r  data_ts=%s  vectors_in=%d  rows_out=%d",
            bbox_name,
            data_ts,
            len(raw_states),
            len(rows),
        )
        return rows
