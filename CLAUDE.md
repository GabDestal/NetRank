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
- Stack (pin every version): Neo4j 5 + GDS (official image), FastAPI, Pydantic, neo4j driver, LangGraph,
  Groq free tier, pytest, Python 3.11.
- Services: `neo4j`, `api` (Dockerfile, pushed to GHCR), `nginx`. Each has a healthcheck.

## Starting schema (the user will challenge it: explain every choice, let them decide)
- Labels: Player, Match, Tournament, Bookmaker.
- (Player)-[:WON]->(Match), (Player)-[:LOST]->(Match), (Match)-[:PART_OF]->(Tournament),
  (Bookmaker)-[:PRICED {winnerOdds, loserOdds}]->(Match).
- GDS projection: (Player)-[:LOST_TO {weight}]->(Player).
- ≥ 2 uniqueness constraints; indexes on Match.date and Player.name.
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
  Never commit to main. Stop after each phase for review. No Claude attribution lines in commits/PRs.
- Do NOT write the modeling rationale or the anti-genericity appendix. Record each decision with its
  alternatives in `docs/decision_log.md`; the user writes the reasoning.
- Code reviews (1 pt) need ≥ 2 constructive comments per PR: the user leaves these, not Claude.

## Phases
0 reset ✔ → 1 scaffold (compose, Makefile, CI, lint) → 2 data exploration + ingestion →
3 Cypher endpoints + PROFILE before/after benchmarks → 4 GDS endpoints → 5 ML → 6 agent + guardrails →
7 docs + demo.ipynb.

## Commands
`make install` (uv if present, Python 3.11), `make docker-run` (waits for healthy), `make test`,
`make test-stack`, `make lint`. Local `.venv` is at `.venv/Scripts` on Windows, `.venv/bin` elsewhere.

## Layout
```
app/  main.py, config.py, routers/, services/ (Cypher), models/ (Pydantic), database/client.py, agent/
scripts/  download + ingestion      tests/  unit/, integration/, container/
nginx/  default.conf                docs/   guidelines.md, decision_log.md, diagrams
```
