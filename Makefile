# =============================================================================
# Air Traffic Pulse — Makefile
#
# All targets use the repo-local .venv so your global Python is untouched.
# Prefer `uv` when available; fall back to built-in venv + pip automatically.
# =============================================================================

# Detect OS so we pick the right interpreter path.
ifeq ($(OS),Windows_NT)
  PYTHON  := .venv/Scripts/python.exe
  PIP     := .venv/Scripts/pip.exe
else
  PYTHON  := .venv/bin/python
  PIP     := .venv/bin/pip
endif

# Use uv if it exists; otherwise fall back to the system python3 / pip.
UV := $(shell command -v uv 2>/dev/null)

# Dedicated database path used by `make demo` so it never overwrites real data.
DEMO_DB := ./data/air_traffic_pulse_demo.duckdb

.PHONY: help venv install setup fmt lint test ingest watch dbt app demo demo-app clean

# Default target — show available targets.
help:
	@echo ""
	@echo "  Air Traffic Pulse"
	@echo ""
	@echo "  make setup      Create .venv and install all dependencies"
	@echo "  make fmt        Format and auto-fix lint (ruff)"
	@echo "  make lint       Lint check without auto-fix"
	@echo "  make test       Run pytest"
	@echo "  make ingest     Fetch live aircraft states → DuckDB (single run)"
	@echo "  make watch      Continuous live ingestion every 5 min (Ctrl-C to stop)"
	@echo "  make dbt        Run dbt deps + dbt build"
	@echo "  make app        Launch Streamlit dashboard"
	@echo "  make demo       Seed 48h of synthetic data + anomaly events → dbt build (offline)"
	@echo "  make demo-app   Launch dashboard against the demo database"
	@echo "  make clean      Remove .venv and build artefacts"
	@echo ""

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

# Resolve a Python 3.11+ interpreter (prefer 3.11, fall back to 3.12/3.13).
PYTHON3 := $(shell command -v python3.11 2>/dev/null \
             || command -v python3.12 2>/dev/null \
             || command -v python3.13 2>/dev/null \
             || command -v python3 2>/dev/null)

venv:
ifdef UV
	@echo "→ Creating .venv with uv …"
	uv venv --python 3.11 .venv
else
	@echo "→ uv not found — creating .venv with $(PYTHON3) …"
	$(PYTHON3) -m venv .venv
endif

install:
ifdef UV
	@echo "→ Installing dependencies with uv pip …"
	uv pip install --python $(PYTHON) -e ".[dev]"
else
	@echo "→ Installing dependencies with pip …"
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
endif

setup: venv install
	@echo ""
	@echo "✓ Setup complete.  Copy .env.example → .env and fill in credentials."
	@echo ""

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

fmt:
	$(PYTHON) -m ruff format src ingestion warehouse app tests tools
	$(PYTHON) -m ruff check --fix src ingestion warehouse app tests tools

lint:
	$(PYTHON) -m ruff format --check src ingestion warehouse app tests tools
	$(PYTHON) -m ruff check src ingestion warehouse app tests tools

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test:
	$(PYTHON) -m pytest

# ---------------------------------------------------------------------------
# Application targets
# ---------------------------------------------------------------------------

ingest:
	$(PYTHON) -m air_traffic_pulse ingest

watch:
	@echo "Continuous live ingestion every 5 minutes — Ctrl-C to stop."
	@while true; do \
		$(MAKE) --no-print-directory ingest; \
		echo "Sleeping 5 min …  (Ctrl-C to stop)"; \
		sleep 300; \
	done

dbt:
	$(PYTHON) -m air_traffic_pulse dbt

app:
	$(PYTHON) -m air_traffic_pulse app

# ---------------------------------------------------------------------------
# Demo mode (offline — no network required)
# ---------------------------------------------------------------------------

demo:
	@echo "→ Seeding 48 h of synthetic timeseries data (seed=42) …"
	DUCKDB_PATH=$(DEMO_DB) $(PYTHON) tools/seed_demo_data.py --hours 48 --seed 42
	@echo "→ Building dbt models …"
	DUCKDB_PATH=$(DEMO_DB) $(PYTHON) -m air_traffic_pulse dbt
	@echo ""
	@echo "✓ Demo ready.  Launch the dashboard with:  make demo-app"
	@echo ""

demo-app:
	DUCKDB_PATH=$(DEMO_DB) $(PYTHON) -m air_traffic_pulse app

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

clean:
	rm -rf .venv .pytest_cache .ruff_cache dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
