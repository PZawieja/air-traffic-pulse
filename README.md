# Air Traffic Pulse

A self-contained analytics-engineering portfolio project that tracks live
air-traffic data end-to-end — from raw API calls to an interactive dashboard.

**What it does:**
1. **Ingest** — pulls real-time aircraft state vectors from the
   [OpenSky Network REST API](https://openskynetwork.github.io/opensky-api/rest.html)
   for configurable city bounding boxes (Berlin, Frankfurt, London by default).
2. **Store** — writes raw data into a local [DuckDB](https://duckdb.org) file
   with a typed schema; no external database required.
3. **Transform** — a [dbt-duckdb](https://github.com/duckdb/dbt-duckdb) project
   models staging views and analytical marts on top of the raw tables.
4. **Visualise** — a [Streamlit](https://streamlit.io) dashboard renders live
   maps, flight counts, and trend charts directly from DuckDB.

The entire stack runs locally inside a single repo with one setup command.

---

## Quickstart

### Option A — using `uv` (recommended)

```bash
# Install uv if you don't have it yet:
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/PZawieja/air-traffic-pulse.git
cd air-traffic-pulse

make setup          # creates .venv and installs all dependencies via uv
cp .env.example .env
# edit .env — optional, but improves OpenSky rate limits
```

### Option B — built-in `venv` + pip

```bash
git clone https://github.com/PZawieja/air-traffic-pulse.git
cd air-traffic-pulse

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env — optional
```

> **Note on OpenSky rate limits**
> Anonymous API access is heavily rate-limited (≈1 request / 10 s).
> Register a free account at <https://opensky-network.org> and add your
> credentials to `.env` (`OPENSKY_USERNAME` / `OPENSKY_PASSWORD`) to get a
> more generous quota.

---

## Day-to-day commands

| Command | What it does |
|---|---|
| `make ingest` | Fetch current aircraft states → DuckDB |
| `make dbt` | Run `dbt deps` + `dbt build` |
| `make app` | Launch the Streamlit dashboard |
| `make fmt` | Auto-format + fix lints with ruff |
| `make test` | Run the pytest suite |
| `make clean` | Remove `.venv` and all build artefacts |

---

## Project layout

```
.
├── src/air_traffic_pulse/   # Core package (config, logging, CLI)
├── ingestion/               # OpenSky API client + DuckDB loader
├── warehouse/               # DuckDB connection factory + schema SQL
├── dbt/                     # dbt project (staging → marts)
├── app/                     # Streamlit dashboard
└── tests/                   # pytest suite
```

## Configuration

All settings are read from `.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OPENSKY_USERNAME` | _(empty)_ | OpenSky account username |
| `OPENSKY_PASSWORD` | _(empty)_ | OpenSky account password |
| `DUCKDB_PATH` | `./data/air_traffic_pulse.duckdb` | DuckDB file path |
| `OPENSKY_BBOX_PRESETS` | `berlin,frankfurt,london` | Comma-separated city presets to ingest |

Built-in bounding-box presets: `berlin`, `frankfurt`, `london`.
Additional presets can be added in `src/air_traffic_pulse/config.py`.
