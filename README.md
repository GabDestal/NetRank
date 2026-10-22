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

> **Status:** Phase 2 (data). The graph is loaded; endpoints, GDS, ML and the agent arrive in later phases.

## Quick start

Requirements: Docker with Compose v2, GNU make, Python 3.11 (or [uv](https://docs.astral.sh/uv/)).

```bash
cp .env.example .env          # then set NEO4J_PASSWORD (>= 8 letters/digits)
make install                  # .venv with runtime + dev dependencies
make docker-run               # neo4j + api + nginx, returns once all three are healthy
make download                 # Sackmann files, verified against the pinned commit
# tennis-data.co.uk files: download by hand, see "Datasets" below
make ingest                   # load Neo4j (~1 min) and regenerate docs/data_exploration.md
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

## Datasets

Two independent sources, linked by entity resolution. Full profile, match rates per year and per
tournament series, and the validation are in [docs/data_exploration.md](docs/data_exploration.md).

### Jeff Sackmann — ATP results and players

- **What:** tour-level ATP matches (Grand Slams, Masters, ATP Tour, Tour Finals) from 1991-01-01
  to 8 June 2026, with both players' serve statistics, ranks, seeds and ages; player birth dates,
  handedness, height and country.
- **Where it comes from now:** the original repository `github.com/JeffSackmann/tennis_atp` has been
  **removed from GitHub**. Its final commit,
  [`712be0c5`](https://github.com/Kadantte/tennis_atp/tree/712be0c5ade693cdab9e69c23a71a0edf5a23c44)
  ("thru 8 jun 2026", authored by Jeff Sackmann), survives unchanged in many forks; we download from
  the fork [`Kadantte/tennis_atp`](https://github.com/Kadantte/tennis_atp) **pinned to that commit**.
- **Integrity:** `make download` checks every file against its Git blob hash from the commit's tree,
  so the bytes are provably identical to Sackmann's last upstream version, whichever fork serves
  them. The hashes are written to `data/raw/sackmann/manifest.json`.
- **Licence:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), which still
  applies to every copy. Attribution: *Tennis databases, files, and algorithms* by
  [Jeff Sackmann / Tennis Abstract](http://www.tennisabstract.com/). Non-commercial use only; this
  project is coursework.

### tennis-data.co.uk — results with bookmaker odds

- **What:** ATP match results with closing odds from several bookmakers, 2000 to 2026.
- **How to get it:** download by hand. The site allows use by private individuals but forbids
  automated downloads, bots and AI tools, so this repository contains no scraper. Open
  <https://www.tennis-data.co.uk/alldata.php>, download the ATP files for 2000–2026 (27 files; not
  the women's files, whose paths contain `w`) and save them unrenamed in `data/raw/tennis_data/`
  (`2000.xls` … `2012.xls`, `2013.xlsx` … `2026.xlsx`). The files and anything derived from them
  row by row stay out of Git.
- **Copyright:** tennis-data.co.uk keeps copyright over the files; only aggregates are published here.

### Linking the two

Each odds row is linked to one Sackmann match when the odds date falls in
[tournament start, start + 16 days], both players' names agree, and the round and tournament break
ties. Rows after Sackmann's cutoff (8 June 2026) are reported as out of coverage. Current result:
**98.74%** of in-coverage odds rows linked; on links where both sources give ATP ranks, 98–99% agree
exactly on both players' ranks. Each `Match` records how its odds were linked (`oddsLinkMethod`).

### Graph after `make ingest`

| Element | Count |
| --- | ---: |
| `Player` | 2,316 |
| `Tournament` (yearly edition) | 2,494 |
| `Match` | 102,417 |
| `Bookmaker` | 4 (Bet365, Pinnacle, Expekt, Ladbrokes) |
| `WON` / `LOST` | 102,417 each |
| `PART_OF` | 102,417 |
| `PRICED` | 181,474 |

## Makefile

| Command | Does |
| --- | --- |
| `make help` | List all targets |
| `make install` | Create `.venv` (Python 3.11) and install `requirements-dev.txt` |
| `make run` | Run the API on :8000 with reload (needs Neo4j from `make docker-run`) |
| `make download` | Download the Sackmann files and verify them against commit `712be0c5` |
| `make ingest` | Load Neo4j from `data/raw/` and regenerate `docs/data_exploration.md` |
| `make docker-run` | Build and start the stack, wait until every service is healthy |
| `make docker-down` | Stop the stack (Neo4j data volume kept) |
| `make test` | All tests with coverage (fails under 60%); integration/container tests skip if services are down |
| `make test-stack` | Container health tests against the running stack |
| `make lint` | pylint on `app/`, `tests/`, `scripts/` (fails under 9.5) |
| `make clean` | Remove caches and coverage files |

## Tests

- `tests/unit` — API, driver wrapper, download verification, loaders, name keys, entity resolution
  and report, all without services.
- `tests/integration` — Cypher tests on a live server: parameterised round trip, GDS presence,
  constraints and indexes, idempotent loads, relationship properties, `PRICED` and constraint
  violations (on throwaway `TEST-` records).
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
