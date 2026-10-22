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

> **Status:** Phase 5 (match-outcome model). The agent arrives in the next phase.

## Quick start

Requirements: Docker with Compose v2, GNU make, Python 3.11 (or [uv](https://docs.astral.sh/uv/)).

```bash
cp .env.example .env          # then set NEO4J_PASSWORD (>= 8 letters/digits)
make install                  # .venv with runtime + dev dependencies
make docker-run               # neo4j + api + nginx, returns once all three are healthy
make download                 # Sackmann files, verified against the pinned commit
# tennis-data.co.uk files: download by hand, see "Datasets" below
make ingest                   # load Neo4j (~1 min) and regenerate docs/data_exploration.md
make gds                      # PageRank prestige, style similarity (KNN) and styles (Louvain), ~5 s
make train                    # match-outcome model -> models/, docs/model_report.md, ~1 min
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

## API

Every list is paginated (`page`, `size` <= 100, response carries `total`). Errors return
`{"detail": "..."}` with 400 (inconsistent parameters), 404 (unknown player, no chain), 422
(invalid parameter) or 503 (Neo4j down). Full schemas at <http://localhost:8080/docs>.

| Endpoint | What it answers | Graph technique |
| --- | --- | --- |
| `GET /api/players?q=` | Find a player by name (accents and case ignored) | Full-text index |
| `GET /api/players/{id}` | Career record, titles, best rank, per surface | Subqueries, conditional aggregation |
| `GET /api/players/{id}/matches` | Match history with odds; `surface`, `since`, `until` filters | Anchored traversal, pagination |
| `GET /api/h2h?p1=&p2=` | Head-to-head overall and per surface | Pattern anchored at both players |
| `GET /api/players/{id}/nemesis` | Who beats this player; non-transitive triangles | 3-cycles on `BEAT` |
| `GET /api/path?from=&to=` | Shortest "beat chain", each hop backed by a match | `SHORTEST` path, bounded |
| `GET /api/players/{id}/prestige?era=` | Prestige score and rank, all-time or in an era (`2000s`, `2004-2008`) | PageRank (native or per-era Cypher projection) |
| `GET /api/prestige?era=` | Prestige leaderboard | PageRank |
| `GET /api/players/{id}/similar` | Players with the closest playing style | KNN on standardised serve/return features |
| `GET /api/styles`, `GET /api/styles/{id}` | Playing-style communities with readable traits and members | Louvain on the KNN graph |
| `POST /api/admin/gds/refresh` | Recompute prestige, similarity and styles (header `X-API-Key`) | Projections, write mode |
| `GET /api/predict?p1=&p2=&surface=` | P(p1 wins) from graph features, tagged `predicted`; with `match_id`, bookmaker odds and result tagged `verified` | Leakage-free PageRank / FastRP snapshots + history |

```bash
curl "localhost:8080/api/players?q=federer&size=1"
# {"items":[{"id":103819,"name":"Roger Federer",...}],"page":1,"size":1,"total":1}

curl "localhost:8080/api/h2h?p1=104925&p2=104745"
# Djokovic vs Nadal: {"player1Wins":30,"player2Wins":28,"bySurface":[...],"matches":[...]}

curl "localhost:8080/api/path?from=100532&to=103819"
# Johan Kriek > Fabrice Santoro > Roger Federer, 2 hops, with the match behind each hop

curl "localhost:8080/api/players/103819/nemesis?size=3&triangles=2"
# Djokovic (27-22) and Nadal (24-16) lead; 783 non-transitive triangles, the strongest:
# Federer leads Agassi 8-3, Agassi leads Rafter 10-5, Rafter leads Federer 3-0
```

### Graph Data Science

`make gds` (or `POST /api/admin/gds/refresh` with `X-API-Key: $ADMIN_API_KEY`) writes the results the
API reads, then drops its in-memory projections, so a Neo4j restart loses nothing. Era prestige is the
only computation done per request: a projection of the matches in the window, PageRank streamed,
cached per era. Missing results answer 503 with the command to run.

```bash
curl "localhost:8080/api/players/104925/prestige?era=2010s"
# Djokovic: rank 1 of 774 players active in 2010-2019

curl "localhost:8080/api/players/103819/similar?size=3"
# closest style to Federer: Jannik Sinner (0.98), ...

curl "localhost:8080/api/styles?size=3"
# style 3: "risky second serve", "dominant first serve", "big server" -> Ivanisevic, Rusedski, Rosset

curl -X POST -H "X-API-Key: $ADMIN_API_KEY" localhost:8080/api/admin/gds/refresh   # 401 without, 403 wrong key
```

Similarity means playing style, not network position: Louvain on the who-beat-whom graph only
recovers generations (debut year explains 91% of its partition), while the style communities explain
50% of the style features. See D41–D42 in [docs/decision_log.md](docs/decision_log.md).

### Match-outcome model

`make train` builds one row per played match since 1995 from graph features computed **only from
earlier matches** (season snapshots of PageRank and FastRP, head-to-head and surface record before the
match date), trains a logistic regression (train 1995-2018, validation 2019-2021) and evaluates it
once on 2022-2026 against the bookmakers. Full report: [docs/model_report.md](docs/model_report.md).

| Test 2022-2026, 9,923 identical matches | Log loss | Brier | Accuracy |
| --- | ---: | ---: | ---: |
| Pinnacle (margin removed) | 0.586 | 0.2015 | 68.1% |
| Bet365 (margin removed) | 0.587 | 0.2017 | 67.8% |
| Ranking baseline (ATP ranks) | 0.632 | 0.2209 | 63.9% |
| Graph model (graph features only) | 0.638 | 0.2232 | 64.0% |

The market wins clearly; graph features alone reach the level of ATP rankings, which also count
matches below tour level that this graph does not contain.

```bash
curl "localhost:8080/api/predict?p1=103819&p2=104745&match_id=2019-540-225"
# Wimbledon 2019 SF re-predicted as of 2019-07-01: model 0.39 for Federer ("predicted"),
# Pinnacle 0.43 and Bet365 0.45 ("verified"); result: Federer won ("verified")
```

### Query performance

`make benchmark` profiles each optimisation before and after and writes
[docs/benchmarks.md](docs/benchmarks.md). Highlights on the loaded graph:

| Case | db hits before → after | latency before → after |
| --- | ---: | ---: |
| Beat cycles through Djokovic (`BEAT` instead of `Match` hops) | 71.2M → 23k | 10.0 s → 7 ms |
| Beat chain, 3 hops (`SHORTEST` on `BEAT`) | 335k → 365 | 123 ms → 3 ms |
| Career totals (one subquery instead of chained `OPTIONAL MATCH`) | 983k → 7.4k | 229 ms → 4 ms |
| Matches in one week (`Match.date` index) | 205k → 130 | 39 ms → 3 ms |

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
| `BEAT` (derived: who beat whom, with win counts) | 66,624 |

## Makefile

| Command | Does |
| --- | --- |
| `make help` | List all targets |
| `make install` | Create `.venv` (Python 3.11) and install `requirements-dev.txt` |
| `make run` | Run the API on :8000 with reload (needs Neo4j from `make docker-run`) |
| `make download` | Download the Sackmann files and verify them against commit `712be0c5` |
| `make ingest` | Load Neo4j from `data/raw/` and regenerate `docs/data_exploration.md` |
| `make gds` | Recompute prestige, style similarity and styles (same as the admin endpoint) |
| `make train` | Train and evaluate the match-outcome model (`models/`, `docs/model_report.md`) |
| `make benchmark` | PROFILE before/after benchmarks, written to `docs/benchmarks.md` |
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
