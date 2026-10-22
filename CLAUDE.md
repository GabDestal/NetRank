# NetRank — brief for Claude Code

Solo course project, GraphDB (AIDAMS 3A, CentraleSupélec), **Level 3 — Advanced graph & GDS**.
`docs/guidelines.md` is the spec and the 100-point checklist: every decision must map to a criterion.
Previous project (ThreatGraph CTI) is archived under tag `archive/threatgraph-cti`; nothing is reused.

## What NetRank is
A tennis knowledge graph: PageRank prestige on who-beat-whom, playing-style communities, match-outcome
prediction benchmarked against bookmaker odds, and a LangGraph agent answering questions.

- Data: Jeff Sackmann `tennis_atp` (ATP, matches 1991+, players; CC BY-NC-SA) and tennis-data.co.uk
  (yearly files with bookmaker odds, 2000+). Entity resolution on date + tournament + normalised names;
  log unmatched rows and report the match rate.
- Sackmann upstream repo is GONE from GitHub. `make download` fetches fork `Kadantte/tennis_atp` pinned
  to commit 712be0c5 and verifies every file by Git blob hash. Data ends 2026-06-08.
- tennis-data.co.uk forbids automated/AI downloads (terms + robots.txt). NEVER fetch from that site;
  the user downloads the files by hand into `data/raw/tennis_data/`. Commit aggregates only, never
  row-level tennis-data content (`data/processed/` is gitignored).
- Stack (pin every version): Neo4j 5 + GDS (official image), FastAPI, Pydantic, neo4j driver, LangGraph,
  Groq free tier, pytest, Python 3.11.
- Services: `neo4j`, `api` (Dockerfile, pushed to GHCR), `nginx`. Each has a healthcheck.

## Schema as loaded (decided with the user in Phase 2; see docs/decision_log.md D13–D30)
- Labels: Player, Match, Tournament (= one yearly edition), Bookmaker (Bet365, Pinnacle, Expekt, Ladbrokes).
- (Player)-[:WON {rank, seed, entry, age, aces, ...}]->(Match), same for LOST: per-player match facts
  live on the relationship. (Match)-[:PART_OF]->(Tournament).
  (Bookmaker)-[:PRICED {winnerOdds, loserOdds, overround}]->(Match). Max/Avg market odds and odds-link
  provenance (oddsLinkMethod, oddsDayOffset) are Match properties.
- Scope: tour-level G/M/A/F from 1991-01-01. Match.walkover / Match.retired flags; walkovers must be
  excluded from the GDS projection (Player)-[:LOST_TO {weight}]->(Player).
- Constraints: Player.id, Match.id, Tournament.id, Bookmaker.name. Indexes: Match.date, Player.name.
- Communities = Louvain on the beat graph, described as competition clusters, not playing styles.
- Entity resolution window is [tourney_date, +16] as the user specified (not [-2, +16]).
- GDS: PageRank, FastRP, KNN, Louvain. ML: scikit-learn winner classifier on FastRP, PageRank,
  head-to-head; temporal train/test split; benchmark vs bookmaker implied probabilities.

## Endpoints (paginate every list)
`GET /api/players/{id}/prestige?era=`, `GET /api/players/{id}/similar`, `GET /api/styles`,
`GET /api/styles/{id}`, `GET /api/path?from=&to=` (shortest beat chain),
`GET /api/players/{id}/nemesis` (H2H + non-transitive triangles), `GET /api/predict?p1=&p2=&surface=`,
`POST /api/agent/ask` (returns tool-call trace), `POST /api/admin/gds/refresh` (API-key auth).

## Agent guardrails
Read-only Cypher allow-list; EXPLAIN-validate before executing; labels/rel types checked against the
schema; LIMIT enforced; Pydantic output tagging each claim verified / predicted / interpreted;
20-question evaluation set. Demo must show one success and one guardrail rejection.

## Hard constraints
- pylint ≥ 9.5 (`make lint`, else −8). `.pylintrc` = course template + docstring checks re-enabled.
- Every Makefile target works (else −3): help, install, run, docker-run, test, lint, clean.
- Coverage ≥ 60% (`make test`). Docstrings on every module, class, function. Max line 120.
- Parameterised Cypher only. Pydantic models on every endpoint. Meaningful HTTP codes.
- Never commit `.env` or secrets (−5 each). Keep `.env.example` current.

## Workflow
- One branch per phase, conventional commits (feat:, fix:, test:, docs:, refactor:, chore:), PR into main.
  Never commit to main. When CI is green, squash-merge the PR yourself, then continue; still stop for
  the user on modeling decisions. No Claude attribution lines in commits/PRs.
- Logging: the course .pylintrc expects f-strings in log calls (logging-format-style=new).
- Do NOT write the modeling rationale or the anti-genericity appendix. Record each decision with its
  alternatives in `docs/decision_log.md`; the user writes the reasoning.
- Code reviews (1 pt) need ≥ 2 constructive comments per PR: the user leaves these, not Claude.

## Phases
0 reset ✔ → 1 scaffold ✔ → 2 data exploration + ingestion ✔ →
3 Cypher endpoints + PROFILE before/after benchmarks → 4 GDS endpoints → 5 ML → 6 agent + guardrails →
7 docs + demo.ipynb.

## Commands
`make install` (uv if present, Python 3.11), `make docker-run` (waits for healthy), `make download`,
`make ingest` (~1 min, regenerates docs/data_exploration.md), `make test`, `make test-stack`, `make lint`. Local `.venv` is at `.venv/Scripts` on Windows, `.venv/bin` elsewhere.

## Layout
```
app/  main.py, config.py, routers/, services/ (Cypher), models/ (Pydantic), database/client.py, agent/
scripts/  download + ingestion      tests/  unit/, integration/, container/
nginx/  default.conf                docs/   guidelines.md, decision_log.md, diagrams
```
