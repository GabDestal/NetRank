.PHONY: help venv install run docker-build docker-run docker-down docker-logs test test-unit test-stack lint clean

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

lint: ## Run pylint (fails below 9.5/10)
	$(PY) -m pylint --fail-under=9.5 $(LINT_PATHS)

clean: ## Remove caches, coverage and build artefacts (keeps .venv and .env)
	rm -rf .pytest_cache .coverage .coverage.* coverage.xml htmlcov build dist *.egg-info
	find . -path ./$(VENV) -prune -o -type d -name __pycache__ -exec rm -rf {} +

.env:
	@echo "Missing .env: run 'cp .env.example .env' and set NEO4J_PASSWORD." && exit 1
