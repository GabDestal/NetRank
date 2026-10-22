.PHONY: help venv install run download ingest gds train eval eval-replay benchmark docker-build docker-run docker-down docker-logs test test-unit test-stack lint clean

PYTHON ?= python3
VENV := .venv
# The venv layout differs on Windows (Git Bash / scoop make) and Unix.
ifeq ($(OS),Windows_NT)
BIN := $(VENV)/Scripts
else
BIN := $(VENV)/bin
endif
PY := $(BIN)/python
LINT_PATHS := app tests $(wildcard scripts/*.py)

help: ## Show this help
	@echo "NetRank make targets:"
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-14s %s\n", $$1, $$2}'

venv: ## Create the Python 3.11 virtualenv (.venv); uses uv when available
	@if [ -d "$(VENV)" ]; then echo "$(VENV) already exists"; \
	elif command -v uv >/dev/null 2>&1; then uv venv --no-project --python 3.11 $(VENV); \
	else $(PYTHON) -m venv $(VENV) && $(PY) -m pip install --upgrade pip; fi

install: venv ## Install runtime + dev dependencies into .venv
	@if command -v uv >/dev/null 2>&1; then uv pip install --python $(VENV) -r requirements-dev.txt; \
	else $(PY) -m pip install -r requirements-dev.txt; fi

run: ## Run the API with reload on http://localhost:8000 (needs Neo4j: make docker-run)
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

download: ## Download and verify Sackmann data (tennis-data files are manual, see README)
	$(PY) -m scripts.download_sackmann

ingest: ## Load Neo4j from data/raw and write docs/data_exploration.md (needs make docker-run)
	$(PY) -m scripts.ingest

gds: ## Recompute prestige, style similarity and styles (after make ingest)
	$(PY) -m scripts.gds_refresh

train: ## Train and evaluate the match-outcome model -> models/, docs/model_report.md (after make gds)
	# One GDS thread: parallel PageRank sums in varying order (~1e-14), which moved weights by ~1e-10
	# and changed the model version between identical runs.
	GDS_CONCURRENCY=1 $(PY) -m scripts.train

eval: ## Live agent evaluation on eval/questions.json (needs GROQ_API_KEY; records eval/recordings/)
	$(PY) -m scripts.eval_agent

eval-replay: ## Re-score the recorded agent runs without calling Groq
	$(PY) -m scripts.eval_agent --replay

benchmark: ## PROFILE before/after query benchmarks -> docs/benchmarks.md (needs the loaded graph)
	$(PY) -m scripts.benchmark

docker-build: ## Build the API image
	docker compose build

docker-run: .env ## Build and start neo4j, api and nginx; returns once all are healthy
	docker compose up -d --build --wait --wait-timeout 300
	@echo "API: http://localhost:$${NGINX_PORT:-8080}/docs   Neo4j Browser: http://localhost:7474"

docker-down: ## Stop the stack (keeps the Neo4j volume)
	docker compose down

docker-logs: ## Follow the logs of all services
	docker compose logs -f

test: ## Run all tests with coverage (integration/container tests skip when services are down)
	$(PY) -m pytest --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=60

test-unit: ## Run unit tests only
	$(PY) -m pytest tests/unit

test-stack: ## Run the container health tests against the running stack
	$(PY) -m pytest tests/container -v

# --jobs=1 overrides the template's jobs=0: the parallel pool occasionally crashed on Windows
# (BrokenProcessPool), and a single worker takes ~15 s on this codebase.
lint: ## Run pylint (fails below 9.5/10)
	$(PY) -m pylint --jobs=1 --fail-under=9.5 $(LINT_PATHS)

clean: ## Remove caches, coverage and build artefacts (keeps .venv and .env)
	rm -rf .pytest_cache .coverage .coverage.* coverage.xml htmlcov build dist *.egg-info
	find . -path ./$(VENV) -prune -o -type d -name __pycache__ -exec rm -rf {} +

.env:
	@echo "Missing .env: run 'cp .env.example .env' and set NEO4J_PASSWORD." && exit 1
