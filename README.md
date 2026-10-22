# NetRank

[![Lint](https://github.com/GabDestal/NetRank/actions/workflows/lint.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/lint.yml)
[![Tests](https://github.com/GabDestal/NetRank/actions/workflows/tests.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/tests.yml)
[![Docker](https://github.com/GabDestal/NetRank/actions/workflows/docker.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/docker.yml)
[![Coverage](https://raw.githubusercontent.com/GabDestal/NetRank/python-coverage-comment-action-data/badge.svg)](https://github.com/GabDestal/NetRank/tree/python-coverage-comment-action-data)

A tennis knowledge graph on Neo4j + Graph Data Science. NetRank ranks ATP players by prestige
(PageRank on who-beat-whom), finds playing-style communities, predicts match outcomes against
bookmaker odds, and answers questions through a LangGraph agent whose claims are tagged as
verified, predicted or interpreted.

Course project, GraphDB (AIDAMS 3A, CentraleSupélec), Level 3 — Advanced graph & GDS.
Spec and grading checklist: [docs/guidelines.md](docs/guidelines.md).

> **Status:** Phase 1 (scaffold). Data, endpoints, GDS, ML and the agent arrive in later phases.

## Quick start

Requirements: Docker with Compose v2, GNU make, Python 3.11 (or [uv](https://docs.astral.sh/uv/)).

```bash
cp .env.example .env          # then set NEO4J_PASSWORD (>= 8 letters/digits)
make install                  # .venv with runtime + dev dependencies
make docker-run               # neo4j + api + nginx, returns once all three are healthy
curl http://localhost:8080/api/health/ready
```

| URL | What |
| --- | --- |
| http://localhost:8080/docs | Swagger UI (through nginx) |
| http://localhost:8080/api/health/ready | Readiness: Neo4j + GDS versions |
| http://localhost:7474 | Neo4j Browser (localhost only) |

## Services

| Service | Image | Host port | Healthcheck |
| --- | --- | --- | --- |
| `neo4j` | `neo4j:5.26.32` + GDS plugin | 7474, 7687 (127.0.0.1) | `cypher-shell 'RETURN gds.version()'` |
| `api` | [`ghcr.io/gabdestal/netrank-api`](https://github.com/GabDestal/NetRank/pkgs/container/netrank-api) (built from `Dockerfile`) | none (behind nginx) | `GET /api/health` |
| `nginx` | `nginx:1.30.6-alpine` | `${NGINX_PORT:-8080}` | `GET /nginx-health` |

## Makefile

| Command | Does |
| --- | --- |
| `make help` | List all targets |
| `make install` | Create `.venv` (Python 3.11) and install `requirements-dev.txt` |
| `make run` | Run the API on :8000 with reload (needs Neo4j from `make docker-run`) |
| `make docker-run` | Build and start the stack, wait until every service is healthy |
| `make docker-down` | Stop the stack (Neo4j data volume kept) |
| `make test` | All tests with coverage (fails under 60%); integration/container tests skip if services are down |
| `make test-stack` | Container health tests against the running stack |
| `make lint` | pylint on `app/`, `tests/`, `scripts/` (fails under 9.5) |
| `make clean` | Remove caches and coverage files |

## Tests

- `tests/unit` — API and driver-wrapper tests with Neo4j faked.
- `tests/integration` — parameterised round trip, Neo4j 5.x and GDS presence on a live server.
- `tests/container` — nginx → api → neo4j chain and `docker compose ps` health for all three services.

CI runs lint, unit + integration tests (Neo4j service container) with coverage, and the full compose
stack. In CI, `NETRANK_REQUIRE_SERVICES=1` turns "service down" skips into failures.

## Project layout

```text
app/            FastAPI app: routers/, services/ (Cypher), models/ (Pydantic), database/, agent/
scripts/        download and ingestion scripts
tests/          unit/, integration/, container/
nginx/          reverse-proxy config
docs/           guidelines, decision log, diagrams
```
