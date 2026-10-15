PYTHON ?= python
SRC := app scripts tests

.PHONY: help install download schema ingest analytics predict test-integration run docker-run docker-down lint test coverage clean

help:
	@echo "make install      Install dependencies"
	@echo "make download     Download source datasets into data/raw/ (skips existing; FORCE=1 to refresh)"
	@echo "make schema       Create Neo4j constraints and indexes (needs Neo4j running)"
	@echo "make ingest       Load downloaded data into Neo4j (ATT&CK, KEV, NVD, CTID; needs Neo4j running)"
	@echo "make analytics    Compute technique centrality and communities with GDS (run by make ingest)"
	@echo "make predict      Evaluate link prediction and store suggestions only if it beats the baseline"
	@echo "make run          Run the API locally with auto-reload (port 8000)"
	@echo "make docker-run   Build and start neo4j, api and nginx (http://localhost:8080)"
	@echo "make docker-down  Stop the stack (keeps the Neo4j volume)"
	@echo "make lint         Run pylint"
	@echo "make test         Run tests with coverage"
	@echo "make test-integration  Run end-to-end API tests against the loaded Neo4j"
	@echo "make coverage     Run tests and write an HTML coverage report"
	@echo "make clean        Remove caches and coverage output"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

download:
	$(PYTHON) -m scripts.download $(if $(FORCE),--force,)

schema:
	$(PYTHON) -m scripts.init_schema

ingest: schema
	$(PYTHON) -m scripts.ingest_attack
	$(PYTHON) -m scripts.ingest_kev_nvd
	$(PYTHON) -m scripts.ingest_ctid
	$(MAKE) analytics

analytics:
	$(PYTHON) -m scripts.analytics

predict:
	$(PYTHON) -m scripts.predict

run:
	$(PYTHON) -m uvicorn app.main:app --reload

docker-run:
	@test -f .env || (echo "Missing .env: copy .env.example to .env and set NEO4J_PASSWORD" && exit 1)
	docker compose up -d --build

docker-down:
	docker compose down

lint:
	$(PYTHON) -m pylint --fail-under=9.5 $(SRC)

test:
	$(PYTHON) -m pytest --cov=app --cov=scripts --cov-report=term-missing --cov-fail-under=80

test-integration:
	THREATGRAPH_INTEGRATION=1 $(PYTHON) -m pytest tests/test_integration.py -v

coverage:
	$(PYTHON) -m pytest --cov=app --cov=scripts --cov-report=html
	@echo "Report written to htmlcov/index.html"

clean:
	rm -rf .pytest_cache .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
