PYTHON ?= python
SRC := app scripts tests

.PHONY: help install lint test coverage clean

help:
	@echo "make install   Install dependencies"
	@echo "make lint      Run pylint"
	@echo "make test      Run tests with coverage"
	@echo "make coverage  Run tests and write an HTML coverage report"
	@echo "make clean     Remove caches and coverage output"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m pylint --fail-under=9.5 $(SRC)

test:
	$(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80

coverage:
	$(PYTHON) -m pytest --cov=app --cov-report=html
	@echo "Report written to htmlcov/index.html"

clean:
	rm -rf .pytest_cache .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
