# Air Traffic Pulse

> Live anomaly detection on aircraft activity — the same pattern I use for revenue monitoring, applied to a data stream anyone can see.

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)](#)
[![DuckDB](https://img.shields.io/badge/DuckDB-FDD023?style=flat&logo=duckdb&logoColor=black)](#)
[![dbt](https://img.shields.io/badge/dbt-FF694B?style=flat&logo=dbt&logoColor=white)](#)

---

## Why aircraft data

The anomaly detection pattern I built in the past — snapshot a metric, build a rolling baseline, flag deviations, route an alert — is domain-agnostic. Air traffic over European cities gives me a live, publicly accessible data stream to demonstrate the same architecture on, without using proprietary company data.

The pattern: **observe → baseline → compare → flag → explain**.

This is the same pattern behind the twice-daily revenue anomaly alerts I built in production, and the MRR drop detection that caught a Salesforce field rename before anyone else noticed it.

---

## What it does

Tracks live aircraft activity over four European cities (Berlin, Warsaw, Amsterdam, Kraków) using the OpenSky Network ADS-B API. For each city and time window it:

1. Builds a rolling historical baseline (mean + standard deviation)
2. Computes a z-score for the current observation
3. Flags deviations above a configurable threshold
4. Generates a human-readable explanation of the anomaly

---

## Architecture

```
OpenSky Network API  (live ADS-B data)
    ↓
Python ingestion layer
    ↓
DuckDB  (local warehouse)
    ├── stg_aircraft_observations    — raw, typed, deduplicated
    ├── int_activity_baselines       — rolling mean + stddev per city × hour
    └── fct_anomaly_signals          — z-score + flag + severity
    ↓
Alert layer  (console / extensible to Slack)
```

The dbt layer mirrors the medallion architecture I use in production: staging for source conformance, intermediate for business logic, mart for the signal output.

---

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Seed historical baseline (runs 24h of observations)
python scripts/seed_baseline.py

# Run live detection
python scripts/detect_anomalies.py

# Or build the full dbt layer
dbt deps && dbt build
```

---

## Project structure

```
air-traffic-pulse/
├── dbt/
│   └── models/
│       ├── staging/          # stg_aircraft_observations
│       ├── intermediate/     # int_activity_baselines
│       └── mart/             # fct_anomaly_signals
├── scripts/
│   ├── ingest.py             # OpenSky API → DuckDB
│   ├── seed_baseline.py      # Historical baseline builder
│   └── detect_anomalies.py   # Anomaly detection runner
└── README.md
```

---

## The revenue connection

The specific anomaly detection logic (z-score against a rolling window baseline, with configurable sensitivity thresholds) is the same approach behind:

- CARR snapshot monitoring that flags >5% intraday drops
- MRR anomaly detection that caught a Salesforce field rename causing a 40% apparent revenue drop
- Chargebee webhook lag detection (subscription events arriving >24h late)

Air traffic is the demo; revenue monitoring is the production application.

---

## Related work

- [Revenue Intelligence Agent](https://github.com/PZawieja/revenue-intelligence-agent) — AI-assisted CS on warehouse signals
- [Experimentation Analytics Platform](https://github.com/PZawieja/experimentation-analytics-platform) — A/B testing pipeline
- [Event Analytics Platform](https://github.com/PZawieja/event-analytics-platform) — Behavioural event pipeline
