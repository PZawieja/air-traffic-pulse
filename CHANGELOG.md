# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-02-26

### Added

**Ingestion**
- `OpenSkyClient` with tenacity retry/backoff (HTTP 429, 5xx, network errors).
- `parse_states()` with defensive type-casting; short vectors are skipped with a warning.
- `raw.opensky_states` append-only snapshot log in DuckDB.
- `raw.ingestion_runs` audit table (one row per run, status lifecycle: running → success/failed).
- Demo mode (`AIR_TRAFFIC_PULSE_DEMO_MODE=1`): loads bundled fixture JSON, no network required.

**Analytics layer (dbt)**
- Staging models: `stg_opensky_states` (lower-case icao24, null-callsign normalisation,
  derived `has_position` / `ingestion_date`) and `stg_ingestion_runs` (derived
  `run_duration_seconds`, `is_success`).
- Mart models: `mart_latest_snapshot_by_bbox`, `mart_traffic_timeseries_5min`,
  `mart_latest_ingestion_run`.
- Column-level dbt tests: `not_null`, `unique`, `accepted_values`,
  `dbt_utils.unique_combination_of_columns`.
- dbt Exposure: `streamlit_air_traffic_pulse` (lineage: marts → Streamlit dashboard).
- MetricFlow semantic models and metrics: `aircraft_count`, `positioned_aircraft_count`,
  `on_ground_count`.

**Dashboard**
- Streamlit app reading from dbt mart tables via DuckDB (read-only connection).
- One-click **Fetch & refresh** button: triggers ingestion + `dbt build` in-process
  and reruns the page.
- Per-region selector (Berlin, Frankfurt, London, Warsaw) in live and demo mode.
- Day/night activity curve visible in the 5-minute timeseries chart.

**Infrastructure**
- Isolated `.venv` — never touches the global Python environment.
- `make setup` / `make demo` / `make watch` / `make demo-app` one-command workflows.
- GitHub Actions CI: lint (`ruff`) → unit tests (`pytest`) → demo ingest → `dbt build`.
- `tools/seed_demo_data.py`: generates 24 h of synthetic aircraft data with day/night curve.

**Governance**
- `docs/data_contract.md`: OpenSky payload structure, null handling, append-only guarantee.
- `VERSION` file at repo root.
- This `CHANGELOG.md`.

### Regions

| City | Bbox |
|---|---|
| 🇩🇪 Berlin | 52.3–52.7°N, 13.0–13.8°E |
| 🇩🇪 Frankfurt | 49.9–50.2°N, 8.3–8.9°E |
| 🇬🇧 London | 51.3–51.7°N, −0.6–0.3°E |
| 🇵🇱 Warsaw | 52.0–52.4°N, 20.7–21.3°E |

---

[Unreleased]: https://github.com/PZawieja/air-traffic-pulse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/PZawieja/air-traffic-pulse/releases/tag/v0.1.0
