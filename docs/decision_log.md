# Decision log

Decisions taken so far, each with the alternatives on the table and the checklist item it serves.
This is a list for the author to write up in the modeling rationale; the reasoning is deliberately
not written here.

## Phase 1 — Scaffold

| # | Decision | Alternatives considered | Checklist item |
| --- | --- | --- | --- |
| D1 | Neo4j `5.26.32` Community (5.x LTS) | Neo4j 2025.x calendar releases; Enterprise (Docker eval licence) | Docker: official image |
| D2 | GDS installed by `NEO4J_PLUGINS` at container start, cached in a `plugins` volume | Custom Neo4j image with the jar baked in; manual jar mount | GDS projection + algorithms |
| D3 | Neo4j Python driver 6.x with `execute_query` and explicit read/write routing | Driver 5.x; session/transaction functions; `graphdatascience` client | Optimization: parameterised queries |
| D4 | API container publishes no port; nginx is the single entry point; Neo4j ports bound to 127.0.0.1 | Publish API port directly; Traefik; API-key auth only | SE: reverse proxy or auth (3 pts) |
| D5 | Liveness (`/api/health`, no DB) separate from readiness (`/api/health/ready`, Neo4j + GDS); Docker healthcheck uses liveness | Single health endpoint; healthcheck on readiness | Tests: container health |
| D6 | Missing GDS reported as `503 degraded`, not a crash | Fail startup; 200 with a flag | FastAPI: error handling |
| D7 | `.pylintrc` = course template, with missing-docstring checks re-enabled and `suggestion-mode` commented (removed in pylint 4) | Template verbatim; pylint defaults | Clean code: pylint ≥ 9.5, docstrings |
| D8 | GHCR (`ghcr.io/gabdestal/netrank-api`), pushed by CI from `main` after the stack test passes | Docker Hub; manual push | Docker: public registry |
| D9 | Coverage badge from `python-coverage-comment-action` (data branch in this repo) | Codecov / Coveralls (third-party account) | SE: badges |
| D10 | Tests split unit / integration / container; CI fails instead of skipping when services are missing | One flat suite; mocks only | Tests: unit/API/Neo4j, container health |
| D11 | `requirements.txt` (runtime, in the image) vs `requirements-dev.txt` (tests, lint) | One file; `pyproject.toml` extras | Repository contents |
| D12 | Neo4j heap 1G, page cache 512M (revisit after ingestion sizes are known) | Image defaults; `neo4j-admin server memory-recommendation` | Optimization |
