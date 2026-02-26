"""HTTP client for the OpenSky Network REST API.

Docs: https://openskynetwork.github.io/opensky-api/rest.html

Only the ``/states/all`` endpoint is used at this stage.
Authentication is optional but strongly recommended to avoid strict rate limits.
"""

from __future__ import annotations

from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from air_traffic_pulse.config import get_settings
from air_traffic_pulse.log import get_logger

log = get_logger(__name__)

_BASE_URL = "https://opensky-network.org/api"
_STATES_PATH = "/states/all"
_TIMEOUT_SEC = 30


def _build_session() -> requests.Session:
    """Return a requests Session, optionally with HTTP Basic Auth."""
    settings = get_settings()
    session = requests.Session()
    if settings.opensky_username and settings.opensky_password:
        session.auth = (settings.opensky_username, settings.opensky_password)
        log.debug("OpenSky session: authenticated as '%s'.", settings.opensky_username)
    else:
        log.debug("OpenSky session: anonymous (rate-limited).")
    return session


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    reraise=True,
)
def fetch_states(
    lamin: float,
    lomin: float,
    lamax: float,
    lomax: float,
) -> dict[str, Any]:
    """Fetch current aircraft states within a bounding box.

    Parameters
    ----------
    lamin, lomin, lamax, lomax:
        Bounding box in WGS-84 decimal degrees.

    Returns
    -------
    Raw JSON response dict from the OpenSky API.
    Raises ``requests.HTTPError`` on non-2xx responses after retries.
    """
    session = _build_session()
    params: dict[str, float] = {
        "lamin": lamin,
        "lomin": lomin,
        "lamax": lamax,
        "lomax": lomax,
    }
    url = f"{_BASE_URL}{_STATES_PATH}"
    log.info("GET %s  bbox=(%.2f,%.2f,%.2f,%.2f)", url, lamin, lomin, lamax, lomax)

    response = session.get(url, params=params, timeout=_TIMEOUT_SEC)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]
