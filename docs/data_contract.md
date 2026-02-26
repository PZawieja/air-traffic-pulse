# Data Contract — Air Traffic Pulse

## Overview

This document describes the expected structure of data ingested from the
[OpenSky Network REST API](https://opensky-network.org/apidoc/), the
assumptions made by the ingestion layer, and how deviations are handled.

---

## Raw layer design principle

> **The raw layer is an append-only snapshot log.**

Every call to the OpenSky `/states/all` endpoint produces a new batch of
rows in `raw.opensky_states`.  No existing rows are updated or deleted.
This means:

- Historical snapshots are preserved in full.
- Re-running ingestion for the same time window produces duplicate rows.
- Deduplication and "latest state" logic is delegated to the dbt staging
  and mart models.

---

## Expected OpenSky payload structure

The `/states/all` endpoint returns a JSON object:

```json
{
  "time": 1700000000,
  "states": [
    [
      "3c4b12",      // 0  icao24
      "DLH1234",     // 1  callsign
      "Germany",     // 2  origin_country
      1700000000,    // 3  time_position
      1700000000,    // 4  last_contact
      13.4050,       // 5  longitude
      52.5200,       // 6  latitude
      10500.0,       // 7  baro_altitude
      false,         // 8  on_ground
      245.3,         // 9  velocity
      180.0,         // 10 true_track
      0.0,           // 11 vertical_rate
      null,          // 12 sensors
      10800.0,       // 13 geo_altitude
      "1234",        // 14 squawk
      false,         // 15 spi
      0              // 16 position_source
    ]
  ]
}
```

### Field count assumption

**Each state vector is assumed to have exactly 17 fields (indices 0–16).**

This is the current OpenSky API specification as of 2024.  The raw schema
was designed against this version.

---

## How short vectors are handled

If a state vector has **fewer than 17 fields**, `ingestion/opensky_client.py`
logs a `WARNING` and skips that row entirely:

```python
if len(sv) < 17:
    log.warning("Short state vector for icao24=%s — skipping.", sv[0])
    continue
```

This prevents `IndexError` exceptions from breaking the whole ingestion run.
The row is simply omitted from that snapshot.

---

## Null handling and defensive parsing

All scalar fields are parsed with safe-cast helpers (`_safe_int`,
`_safe_float`, `_safe_bool`, `_safe_str`) that return `None` on any
type error rather than raising.  The following fields are expected to be
`NULL` under normal conditions:

| Column | NULL when |
|---|---|
| `time_position` | Aircraft has no position report yet |
| `longitude` / `latitude` | Position unknown (same condition) |
| `baro_altitude` | `on_ground = true` |
| `geo_altitude` | Same as baro_altitude |
| `sensors` | No sensor info in feed (common for anonymous access) |
| `callsign` | Transponder reports blank callsign |
| `squawk` | No squawk assigned |
| `vertical_rate` | Rate unknown |

---

## Callsign normalisation

Callsigns are stripped of surrounding whitespace.  A callsign that is
blank after stripping is stored as `NULL`, not as an empty string.

`icao24` addresses are lower-cased at the staging layer (`stg_opensky_states`).

---

## What happens if new fields appear

If the OpenSky API adds an **18th field** (index 17+), the ingestion layer
will silently ignore it — the state vector is sliced to the first 17 fields.
No error will be raised, and ingestion will continue normally.

If the API **removes or reorders** existing fields, state vectors will
parse incorrectly (wrong values in columns) or raise in the safe-cast
helpers (logged as warnings).  A schema-drift alert should be added if
this becomes a concern.

---

## ingestion_runs audit table

Every execution of `make ingest` (or `python -m air_traffic_pulse ingest`)
writes one record to `raw.ingestion_runs`:

| Column | Meaning |
|---|---|
| `run_id` | UUID v4 — unique per run |
| `started_at` | UTC wall-clock start |
| `finished_at` | UTC wall-clock end (`NULL` if still running) |
| `status` | `running` → `success` or `failed` |
| `records_loaded` | Rows written to `raw.opensky_states` |
| `error_msg` | Exception message on failure, `NULL` otherwise |

Runs that crash mid-flight remain in `status = 'running'` indefinitely.
This is intentional — it preserves the audit trail without requiring a
cleanup job.

---

## dbt transformation contract

The raw tables are consumed exclusively by dbt staging models:

| Raw table | Staging model | Key transformations |
|---|---|---|
| `raw.opensky_states` | `stg_opensky_states` | lowercase icao24, null-callsign, derived `has_position` / `ingestion_date` |
| `raw.ingestion_runs` | `stg_ingestion_runs` | derived `run_duration_seconds`, `is_success` |

Downstream mart models (`mart_*`) **must not** reference raw tables directly.
All access goes through staging.
