"""Seed the DuckDB database with synthetic air-traffic timeseries data.

Generates *hours* × 3 bboxes × ~5–30 aircraft rows at 5-minute intervals,
creating a realistic day/night activity curve so the Streamlit timeseries
chart looks good immediately after `make demo`.

Usage:
    python tools/seed_demo_data.py                  # 24 h, 5-min intervals
    python tools/seed_demo_data.py --hours 48       # 48 h of history
    python tools/seed_demo_data.py --interval 10    # 10-min intervals
    DUCKDB_PATH=./data/demo.duckdb python tools/seed_demo_data.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import pathlib
import random
import sys
import uuid
from typing import Any

# Make repo-root packages importable when called directly.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from warehouse.duckdb_conn import get_connection, init_schema  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration mirrors src/air_traffic_pulse/config.py
# ---------------------------------------------------------------------------

BBOX_PRESETS: dict[str, dict[str, float]] = {
    "berlin": {"lamin": 52.3, "lomin": 13.0, "lamax": 52.7, "lomax": 13.8},
    "frankfurt": {"lamin": 49.9, "lomin": 8.3, "lamax": 50.2, "lomax": 8.9},
    "london": {"lamin": 51.3, "lomin": -0.6, "lamax": 51.7, "lomax": 0.3},
    "warsaw": {"lamin": 52.0, "lomin": 20.7, "lamax": 52.4, "lomax": 21.3},
}

# Airline callsign prefixes typical for each city's main airport.
_CALLSIGN_PREFIXES: dict[str, list[str]] = {
    "berlin": ["DLH", "EWG", "BER", "RYR", "WZZ", "EZY", "THY", "SAS"],
    "frankfurt": ["DLH", "LHA", "CFG", "EZY", "THY", "UAE", "ANA", "SIA"],
    "london": ["BAW", "EZY", "VIR", "TOM", "RYR", "IBE", "AFR", "KLM"],
    "warsaw": ["LOT", "RYR", "WZZ", "EZY", "DLH", "AFL", "SAS", "THY"],
}

_ORIGIN_COUNTRIES: dict[str, list[str]] = {
    "berlin": ["Germany", "Germany", "Germany", "Ireland", "Hungary", "Turkey", "United Kingdom"],
    "frankfurt": [
        "Germany",
        "Germany",
        "Germany",
        "Turkey",
        "United Arab Emirates",
        "Japan",
        "Singapore",
    ],
    "london": [
        "United Kingdom",
        "United Kingdom",
        "Ireland",
        "Spain",
        "France",
        "Netherlands",
        "United States",
    ],
    "warsaw": ["Poland", "Poland", "Poland", "Ireland", "Hungary", "Germany", "Russia"],
}

# Peak aircraft count per bbox at midday.
_PEAK_AIRCRAFT: dict[str, int] = {
    "berlin": 22,
    "frankfurt": 28,
    "london": 32,
    "warsaw": 18,
}

# Number of distinct aircraft kept in each bbox's pool.
_POOL_SIZE = 60

# ---------------------------------------------------------------------------
# Anomaly events (baked into demo data for interesting z-score output)
# ---------------------------------------------------------------------------
# Each entry: (hours_before_now, duration_minutes, traffic_multiplier).
# A multiplier > 1 creates a spike; < 1 creates a drop.
# Applied deterministically regardless of --seed so anomalies are always visible.
_ANOMALY_EVENTS: list[tuple[float, int, float]] = [
    (3.0, 25, 3.8),  # spike: intense landing-sequence / airshow overfly  3 h ago
    (10.5, 15, 3.5),  # spike: morning rush surge                          ~10.5 h ago
    (18.0, 20, 0.12),  # near-zero: overnight temporary airspace closure    ~18 h ago
]


def _event_multiplier(snap_ts: dt.datetime, now: dt.datetime) -> float:
    """Return the traffic multiplier for *snap_ts*, or 1.0 if no event applies."""
    for hours_before, duration_min, multiplier in _ANOMALY_EVENTS:
        event_start = now - dt.timedelta(hours=hours_before)
        event_end = event_start + dt.timedelta(minutes=duration_min)
        if event_start <= snap_ts <= event_end:
            return multiplier
    return 1.0


# Column order must match raw.opensky_states in schema.sql exactly.
_STATE_COLUMNS: tuple[str, ...] = (
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
)

_INSERT_STATES = (
    f"INSERT INTO raw.opensky_states ({', '.join(_STATE_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * len(_STATE_COLUMNS))})"
)

_INSERT_RUN = """
    INSERT INTO raw.ingestion_runs (run_id, started_at, finished_at, status, records_loaded)
    VALUES (?, ?, ?, 'success', ?)
"""

# ---------------------------------------------------------------------------
# Aircraft pool generation
# ---------------------------------------------------------------------------


def _random_hex(n: int) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))


def _build_aircraft_pool(bbox_name: str) -> list[dict[str, Any]]:
    """Return a stable pool of synthetic aircraft for one bbox.

    Each entry carries a randomised "personality" (altitude preference,
    typical velocity, heading) that drifts slightly each snapshot to
    simulate actual flight paths.
    """
    bounds = BBOX_PRESETS[bbox_name]
    prefixes = _CALLSIGN_PREFIXES[bbox_name]
    countries = _ORIGIN_COUNTRIES[bbox_name]

    pool = []
    for _ in range(_POOL_SIZE):
        on_ground = random.random() < 0.06
        pool.append(
            {
                "icao24": _random_hex(6),
                "callsign": f"{random.choice(prefixes)}{random.randint(1, 9999):04d}",
                "origin_country": random.choice(countries),
                # Slowly-drifting position anchored within the bbox.
                "_lon": random.uniform(bounds["lomin"], bounds["lomax"]),
                "_lat": random.uniform(bounds["lamin"], bounds["lamax"]),
                "_altitude": random.uniform(1800.0, 11500.0),
                "_velocity": random.uniform(120.0, 290.0),
                "_track": random.uniform(0.0, 360.0),
                "_vrate": random.uniform(-5.0, 5.0),
                "_on_ground": on_ground,
                "_pos_src": random.choices([0, 1, 2], weights=[0.80, 0.10, 0.10])[0],
            }
        )
    return pool


# ---------------------------------------------------------------------------
# Per-snapshot helpers
# ---------------------------------------------------------------------------


def _active_count(t: dt.datetime, bbox_name: str) -> int:
    """Return how many aircraft from the pool are visible at time *t*."""
    hour = t.hour + t.minute / 60.0
    peak = _PEAK_AIRCRAFT[bbox_name]

    # Smooth day/night activity curve: busy 06–22, quiet overnight.
    if 6.0 <= hour <= 22.0:
        factor = 0.55 + 0.45 * math.sin((hour - 6.0) * math.pi / 16.0)
    else:
        factor = 0.15 + 0.10 * math.sin(hour * math.pi / 6.0)

    jitter = 0.80 + 0.40 * random.random()
    return max(3, min(_POOL_SIZE, int(peak * factor * jitter)))


def _drift_aircraft(aircraft: dict[str, Any], bounds: dict[str, float]) -> None:
    """Nudge the aircraft's position, track, and altitude in-place."""
    aircraft["_lon"] = _clamp(
        aircraft["_lon"] + random.gauss(0, 0.02),
        bounds["lomin"],
        bounds["lomax"],
    )
    aircraft["_lat"] = _clamp(
        aircraft["_lat"] + random.gauss(0, 0.015),
        bounds["lamin"],
        bounds["lamax"],
    )
    aircraft["_track"] = (aircraft["_track"] + random.gauss(0, 3)) % 360.0
    aircraft["_altitude"] = _clamp(
        aircraft["_altitude"] + random.gauss(0, 80),
        1500.0,
        12500.0,
    )
    aircraft["_velocity"] = _clamp(
        aircraft["_velocity"] + random.gauss(0, 4),
        80.0,
        310.0,
    )
    aircraft["_vrate"] = _clamp(
        aircraft["_vrate"] + random.gauss(0, 0.5),
        -12.0,
        12.0,
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _make_state_row(
    aircraft: dict[str, Any],
    bbox_name: str,
    ingestion_ts: dt.datetime,
    data_ts: int,
) -> tuple:
    """Return a positional tuple aligned with _STATE_COLUMNS."""
    on_ground = aircraft["_on_ground"]
    baro_alt: float | None = None if on_ground else round(aircraft["_altitude"], 1)
    geo_alt: float | None = (
        None if on_ground else round(aircraft["_altitude"] + random.uniform(0, 250), 1)
    )
    lon: float | None = round(aircraft["_lon"], 5)
    lat: float | None = round(aircraft["_lat"], 5)
    velocity = 0.0 if on_ground else round(aircraft["_velocity"], 1)

    row: dict[str, Any] = {
        "ingestion_ts": ingestion_ts,
        "data_ts": data_ts,
        "bbox_name": bbox_name,
        "icao24": aircraft["icao24"],
        "callsign": aircraft["callsign"],
        "origin_country": aircraft["origin_country"],
        "time_position": data_ts if not on_ground else None,
        "last_contact": data_ts,
        "longitude": lon,
        "latitude": lat,
        "baro_altitude": baro_alt,
        "on_ground": on_ground,
        "velocity": velocity,
        "true_track": round(aircraft["_track"], 1),
        "vertical_rate": round(aircraft["_vrate"], 2),
        "sensors": None,
        "geo_altitude": geo_alt,
        "squawk": f"{random.randint(1000, 7777):04d}",
        "spi": False,
        "position_source": aircraft["_pos_src"],
    }
    return tuple(row[col] for col in _STATE_COLUMNS)


# ---------------------------------------------------------------------------
# Main seeding routine
# ---------------------------------------------------------------------------


def seed(
    duckdb_path: str,
    hours: int = 24,
    interval_minutes: int = 5,
    bboxes: list[str] | None = None,
    seed_value: int | None = None,
) -> None:
    """Populate *duckdb_path* with synthetic timeseries data.

    Args:
        duckdb_path:        Path to the DuckDB file (created if absent).
        hours:              How many hours of history to generate.
        interval_minutes:   Interval between synthetic snapshots in minutes.
        bboxes:             Subset of bbox names (defaults to all three).
        seed_value:         Optional RNG seed for reproducibility.
    """
    if seed_value is not None:
        random.seed(seed_value)

    active_bboxes = bboxes or list(BBOX_PRESETS.keys())
    now = dt.datetime.now(tz=dt.UTC).replace(second=0, microsecond=0)

    # Build synthetic snapshots at *interval_minutes* steps ending at *now*.
    step = dt.timedelta(minutes=interval_minutes)
    n_snapshots = int(hours * 60 / interval_minutes)
    snapshots: list[dt.datetime] = [now - step * i for i in range(n_snapshots, 0, -1)]

    print(
        f"Seeding {len(snapshots)} snapshots × {len(active_bboxes)} bboxes "
        f"= {len(snapshots) * len(active_bboxes)} ingestion runs  "
        f"into '{duckdb_path}' …"
    )

    con = get_connection(duckdb_path)
    init_schema(con)

    # One aircraft pool per bbox — persists across snapshots so the same
    # planes appear repeatedly, mimicking real flight paths.
    pools: dict[str, list[dict[str, Any]]] = {
        name: _build_aircraft_pool(name) for name in active_bboxes
    }

    total_state_rows = 0

    for snap_ts in snapshots:
        data_ts = int(snap_ts.timestamp())
        started_at = snap_ts
        finished_at = snap_ts + dt.timedelta(seconds=random.uniform(0.8, 2.5))
        run_id = str(uuid.uuid4())
        run_rows = 0

        # Apply anomaly multiplier once per snapshot (same event window for all bboxes).
        multiplier = _event_multiplier(snap_ts, now)

        state_tuples: list[tuple] = []

        for bbox_name in active_bboxes:
            pool = pools[bbox_name]
            bounds = BBOX_PRESETS[bbox_name]
            base_count = _active_count(snap_ts, bbox_name)
            # Clamp to pool size; for spikes > pool, sample_with pool size cap.
            n_active = max(0, min(_POOL_SIZE, int(base_count * multiplier)))
            active = random.sample(pool, n_active)

            for aircraft in active:
                _drift_aircraft(aircraft, bounds)
                state_tuples.append(_make_state_row(aircraft, bbox_name, snap_ts, data_ts))
                run_rows += 1

        if state_tuples:
            con.executemany(_INSERT_STATES, state_tuples)

        con.execute(_INSERT_RUN, [run_id, started_at, finished_at, run_rows])
        total_state_rows += run_rows

    con.close()
    print(
        f"Done.  {total_state_rows:,} aircraft-state rows across "
        f"{len(snapshots):,} synthetic ingestion runs."
    )
    n_events = len(_ANOMALY_EVENTS)
    print(f"{n_events} anomaly event(s) injected — look for z-score spikes in the dashboard.")
    print(f"Run `make demo-app` (or DUCKDB_PATH={duckdb_path} make app) to view the dashboard.")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--hours", type=int, default=24, help="Hours of history to generate (default: 24)"
    )
    p.add_argument(
        "--interval", type=int, default=5, help="Snapshot interval in minutes (default: 5)"
    )
    p.add_argument(
        "--bboxes",
        nargs="+",
        default=None,
        choices=list(BBOX_PRESETS.keys()),
        help="Bbox names to seed (default: all)",
    )
    p.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    db_path = os.environ.get("DUCKDB_PATH", "./data/air_traffic_pulse_demo.duckdb")
    seed(
        duckdb_path=db_path,
        hours=args.hours,
        interval_minutes=args.interval,
        bboxes=args.bboxes,
        seed_value=args.seed,
    )
