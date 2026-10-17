# Final audit (2026-10-17)

Project level: 3 ("Advanced graph & GDS"). Checked against the course's 100-point checklist. Commands were run on 2026-10-17 on `main` plus the
`chore/final-gaps` branch, with the Docker stack up and the full data loaded.

Status: **Met**, **Partial** (part of it is there; what is missing is stated), **Missing**, or
**Solo** (a team criterion; this is a solo project, so ask the instructor how it is graded).

| Area | Criterion | Pts | Status | Evidence |
|---|---|---:|---|---|
| Docker | Compose with ≥ 3 services | 2 | Met | `docker-compose.yml`: `neo4j`, `api`, `nginx` (+ optional `ollama` profile) |
| Docker | Dockerfile / official images | 2 | Met | `Dockerfile` on `python:3.12-slim`; official `neo4j:5.26-community` and `nginx:1.27-alpine` |
| Docker | `.env.example`, no secrets | 2 | Met | `.env` gitignored and in `.dockerignore`; full git history scanned (no keys); pushed image checked: only `app/` and `requirements.txt`, no `.env` |
| Docker | ≥ 1 image on a public registry | 2 | Met | [`gabdestal/threatgraph-api:1.0`](https://hub.docker.com/r/gabdestal/threatgraph-api) on Docker Hub, public (`sha256:7485c238…`); pull command in the README |
| Docker | Compose starts cleanly | 1 | Met | `make docker-run`: all three services healthy; `/health`, `/health/db` and `/docs` answer on :8080 |
| Neo4j | ≥ 3 labels and ≥ 3 relationship types | 3 | Met | 14 labels (Group, Technique, CVE, Product, …) and 11 relationship types in the loaded graph; `docs/schema.png` |
| Neo4j | ≥ 2 constraints | 2 | Met | 17 uniqueness constraints (`app/database/schema.py`, `make schema`) |
| Neo4j | Indexes | 2 | Met | 17 constraint-backed range indexes + `cve_cvss_score` (D8); their effect is measured in `docs/benchmarks.md` |
| Neo4j | Ingestion script | 2 | Met | `scripts/ingest_attack.py`, `ingest_kev_nvd.py`, `ingest_ctid.py` (`make ingest`), batched `UNWIND` writes (D13), count checks after each source |
| Neo4j | Dataset source documented | 1 | Met | README "Data"; `data/raw/manifest.json` (URL, version, SHA-256); one `:ImportMeta` node per source |
| FastAPI | ≥ 4 endpoints, ≥ 3 advanced graph queries | 2 | Met | 15 paths in `/openapi.json`; advanced: product exposure (4 hops), connection path (shortestPath), CVE → groups, mitigation plan, GDS similarity, centrality |
| FastAPI | Pydantic | 2 | Met | `app/models/`, every endpoint has a `response_model` and typed inputs |
| FastAPI | Swagger `/docs` | 1 | Met | `http://localhost:8080/docs` returns 200 through nginx |
| FastAPI | Error handling | 1 | Met | 404 (unknown ids), 422 (bad input), 503 (Neo4j or LLM down), tested in `tests/test_api.py`, `test_health.py`, `test_agent.py` |
| Advanced Cypher | Pathfinding / GDS in ≥ 2 endpoints | 4 | Met | `/paths/connection` runs a bounded Cypher `shortestPath` over verified links (D20); `/groups/{id}/similar` runs GDS node similarity live on a temporary projection (D17). Also `/techniques/central` serves GDS betweenness and Louvain computed by `make analytics` (D15, D16) |
| Advanced Cypher | Complex pattern matching | 3 | Met | Multi-hop patterns with type alternation (`EXPLOITS_VIA\|PRIMARY_IMPACT\|SECONDARY_IMPACT`), optional sub-technique expansion, `EXISTS` filters (`app/services/`) |
| Advanced Cypher | WITH / UNWIND / subqueries / aggregations | 2 | Met | 34 `COLLECT {}` / `COUNT {}` / `EXISTS {}` / `UNWIND` uses in `app/services/`, plus `WITH … ORDER BY … LIMIT` rankings |
| Optimization | Optimized queries + benchmarks | 5 | Met | `docs/benchmarks.md`, `make benchmark`: PROFILE before/after for 3 queries (db hits 4,053 → 147; 7,200 → 3; 185,838 → 15,987); cost comment above each query |
| GDS & Agentic | GDS projection + ≥ 2 algorithms | 2 | Met | Degree, betweenness, Louvain (`scripts/analytics.py`), node similarity (live), FastRP (D18) |
| GDS & Agentic | ML link / node workflow | 3 | Met | Link prediction for CVE → technique (`make predict`, `docs/link_prediction.md`): time split, leakage checks, baseline comparison. The model did not beat the baseline, so nothing is stored, and this is documented |
| GDS & Agentic | LangGraph / GraphRAG / NL-to-Cypher | 4 | Met | `app/agent/graph.py` (LangGraph), 9 fixed tools + guarded `run_cypher` fallback; `POST /agent/ask`; evaluation 13/15 (D19) |
| GDS & Agentic | LLM reliability and guardrails | 4 | Met | Read-only allow-list, `EXPLAIN` check, LIMIT 50, READ session, 10 s timeout, server-side provenance (`app/agent/guardrails.py`); `make guardrail-demo`; rejected attacks in the evaluation |
| Schemas | Neo4j graph diagram | 2 | Met | `docs/schema.drawio`, `.png`, `.svg`, in the README |
| Schemas | Architecture diagram | 2 | Partial | Text diagram and services table in the README; the README links `docs/architecture.drawio`, which is not committed yet |
| Schemas | Modeling rationale + anti-genericity appendix | 3 | Met | `docs/modeling_rationale.md` D1–D19 with a rejected-alternatives table; `docs/anti_genericity_appendix.md` compares our schema with the unedited AI baseline (`docs/ai_baseline_schema.md`), including a CVE-regex check over ATT&CK v20 |
| Docs | README + screenshots | 3 | Partial | README is complete (description, architecture, install, data, API, agent, Makefile, Docker image). The Screenshots section points to `docs/screenshots/`, but the 3 images are not committed yet |
| Docs | Demo notebook | 2 | Met | `demo.ipynb`, committed with outputs and five charts |
| Clean code | `.pylintrc`, pylint ≥ 9.5, `make lint` | 2 | Met | `.pylintrc`; `make lint` 10.00/10 |
| Clean code | PEP 8 + structure | 1 | Met | Max line length 120 enforced by pylint; `app/` split into routers, services, models, database, agent |
| Clean code | Docstrings | 1 | Met | `missing-docstring` enabled for `app/` and `scripts/` |
| Makefile | Required commands | 1 | Met | help, install, run, docker-run, test, lint, clean (+ download, ingest, analytics, predict, benchmark, …) |
| Makefile | Functional | 1 | Met | All run on 2026-10-16; `make test`, `make lint` and `make benchmark` re-run on 2026-10-17 |
| Makefile | Documented | 1 | Met | `make help` and the README Makefile table |
| Tests | Unit / API / Neo4j tests | 3 | Met | 284 tests: unit (fake driver), API (`TestClient`), and 14 against the real Neo4j |
| Tests | Container health checks | 2 | Met | Docker healthchecks on `neo4j`, `api`, `nginx`; `tests/test_health.py` (`/health`, `/health/db` up and down) |
| Tests | Cypher tests | 2 | Met | `make test` now includes `tests/test_integration.py` (real Cypher, guardrails against the real server); its tests skip with the reason when Neo4j is unreachable or empty, so CI stays green |
| Tests | Coverage ≥ 60% | 2 | Met | 98.8% (`make test`); CI fails under 80% |
| Tests | All pass | 1 | Met | 284 passed locally; CI green on every merged PR |
| SE | Lint workflow | 1 | Met | `.github/workflows/lint.yml`, required check on `main` |
| SE | Test workflow | 1 | Met | `.github/workflows/test.yml`, required check on `main` |
| SE | README badges | 1 | Met | lint and test badges at the top of the README |
| SE | Code reviews | 1 | Solo | Every change went through a PR with required checks, but there is no second person to review. Ask the instructor |
| SE | Reverse proxy or auth | 3 | Met | nginx in front of the api (only :8080 is public; the api port is internal), `nginx/` config |
| SE | EXPLAIN / PROFILE demo | 2 | Met | PROFILE: `docs/benchmarks.md`, `make benchmark`. EXPLAIN: every LLM query is validated with EXPLAIN (`POST /agent/check-cypher`, notebook section 6) |
| Git | Branch workflow | 2 | Met | One branch per feature (`feat/`, `fix/`, `docs/`, `chore/`), merged by PR into a protected `main` |
| Git | `.gitignore` | 1 | Met | `.gitignore` covers `.env`, `.venv`, `data/`, caches, coverage |
| Git | Balanced contributions | 3 | Solo | One author. Ask the instructor |
| Git | ≥ 1 merged PR per member | 3 | Solo | 21 merged PRs from the only member. Ask the instructor |
| Git | Clear commits | 1 | Met | Prefixes feat/fix/test/docs/refactor/chore, small focused commits |

## Summary

| Status | Points |
|---|---:|
| Met | 88 |
| Partial | 5 (architecture diagram 2, README + screenshots 3) |
| Solo, ask the instructor | 7 |
| Missing | 0 |

The two partial rows only need files: `docs/architecture.drawio` and the 3 images in `docs/screenshots/`
(`neo4j-browser.png`, `swagger.png`, `agent-answer.png`).
