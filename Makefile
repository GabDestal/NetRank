PYTHON ?= python
SRC := app scripts tests

.PHONY: help install download schema run docker-run docker-down lint test coverage clean

help:
	@echo "make install      Install dependencies"
	@echo "make download     Download source datasets into data/raw/ (skips existing; FORCE=1 to refresh)"
	@echo "make schema       Create Neo4j constraints and indexes (needs Neo4j running)"
	@echo "make run          Run the API locally with auto-reload (port 8000)"
	@echo "make docker-run   Build and start neo4j, api and nginx (http://localhost:8080)"
	@echo "make docker-down  Stop the stack (keeps the Neo4j volume)"
	@echo "make lint         Run pylint"
	@echo "make test         Run tests with coverage"
	@echo "make coverage     Run tests and write an HTML coverage report"
	@echo "make clean        Remove caches and coverage output"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

download:
	$(PYTHON) -m scripts.download $(if $(FORCE),--force,)

schema:
	$(PYTHON) -m scripts.init_schema

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

coverage:
	$(PYTHON) -m pytest --cov=app --cov=scripts --cov-report=html
	@echo "Report written to htmlcov/index.html"

clean:
	rm -rf .pytest_cache .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
