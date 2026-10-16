# Final audit (2026-10-16)

The official 100-point checklist from the course spec was not available when this was written, so
this audit uses the hard constraints in `CLAUDE.md`, the LLM requirements, and the items asked for
explicitly (diagrams, registry image, README contents, benchmarks, health and Cypher tests, demo commands).
Commands were run on 2026-10-16 on the merged `main` plus this branch.

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Graph schema diagram (draw.io) | Met | `docs/schema.drawio`, exported as `docs/schema.png` and `.svg`, shown in the README |
| 2 | System architecture diagram (services, ports, data flows) | Partial | Text diagram and service table in the README (Architecture section, this PR). No draw.io architecture diagram in `docs/` |
| 3 | Image pushed to a public registry, linked in the README | Missing | Nothing is published yet |
| 4 | README: description, install and run, API examples, schema, architecture, dataset sources, rationale, Makefile, badges | Met | README sections Architecture, Getting started, Data, Running, API, Agent, Makefile; lint and test badges |
| 4b | README: screenshots | Missing | No screenshots of the Neo4j browser, Swagger UI or an agent answer |
| 5 | EXPLAIN/PROFILE before/after benchmarks | Missing | Query costs are explained in comments next to each query in `app/services/`, and some timings are in D14–D17, but there is no PROFILE before/after comparison (for example with and without an index) |
| 6 | Container health tests | Met | Healthchecks on `neo4j`, `api` and `nginx` (nginx added in this PR); `tests/test_health.py` covers `/health`, and `/health/db` both up and down (503) |
| 7 | Cypher tests run by `make test` | Partial | `make test` checks every query's parameters, read-only keywords and result mapping with a fake driver (`tests/test_api.py`, `test_analytics_*`, `test_guardrails.py`). Real Cypher only runs in `make test-integration` (13 tests, all passing locally), which needs a loaded Neo4j and so is skipped in CI |
| 8 | Demo commands | Met | `make help` lists 17 targets; `make lint` 10.00/10; `make test` 250 passed, 98.76% coverage; `make docker-run` starts all three services healthy, and `/health`, `/health/db`, a GDS endpoint and `/agent/ask` answer on :8080 |
| 9 | pylint ≥ 9.5 | Met | 10.00/10; `lint.yml` is a required check on `main` |
| 10 | Coverage ≥ 60% | Met | 98.76%; `test.yml` fails under 80% and is a required check |
| 11 | Makefile: help, install, run, docker-run, test, lint, clean | Met | All run on 2026-10-16 (`make run` served `/health` on :8000) |
| 12 | No secrets committed; `.env.example` kept up to date | Met | `.env` is gitignored; a scan of the full git history finds no keys or passwords; `.env.example` lists every setting, including the LLM ones |
| 13 | Docstrings, PEP 8, line length 120 | Met | Enforced by pylint (`missing-docstring` is on for `app/` and `scripts/`) |
| 14 | Pydantic models for every endpoint; meaningful HTTP codes | Met | `app/models/`; 404, 422 and 503 tested in `tests/test_api.py`, `tests/test_agent.py` |
| 15 | All Cypher parameterized | Met, one stated exception | Every service query uses parameters. The agent's fallback runs LLM-written Cypher as text by design; it is guarded instead (D19) |
| 16 | Compose stack: neo4j (GDS + APOC), api, nginx | Met | `docker-compose.yml`; Neo4j memory capped |
| 17 | One feature per branch, PRs, commit prefixes | Met | PRs #1–#18 merged into a protected `main` with required checks |
| 18 | Modeling options with trade-offs, rejected alternatives logged | Met | `docs/modeling_rationale.md` D1–D19 and the rejected-alternatives table |
| 19 | Non-trivial Cypher explained, with cost growth | Met | Comment above each query in `app/services/` and `app/agent/tools.py` |
| 20 | LLM: read-only allow-list rejecting writes and `CALL dbms.*` | Met | `app/agent/guardrails.py` (all `CALL` banned), `tests/test_guardrails.py` |
| 21 | LLM: EXPLAIN before executing, enforced LIMIT | Met | `explain()` checks Neo4j's query type and unknown schema; LIMIT capped at 50 |
| 22 | LLM: verified vs inferred facts | Met | Provenance set by the server from citations (`tag_facts`), D18 suggestions kept apart |
| 23 | LLM: tool calls and graph paths exposed | Met | `tool_calls`, `path`, `cypher` and `guardrail_events` in every `/agent/ask` response |
| 24 | LLM: guardrail rejection demo | Met | `make guardrail-demo`, `demo.ipynb` section 6, and a real rejection in the evaluation (D19) |
| 25 | Agent evaluation | Met | `make evaluate-agent`: 13/15 on Groq; failures and limits in D19 |
| 26 | Anti-genericity appendix | Missing | Blocked: the unedited AI baseline schema (`docs/ai_baseline_schema.md`) has not been provided yet |
| 27 | Demo notebook | Met | `demo.ipynb`, committed with outputs and five charts (#18) |
| 28 | Data provenance and reproducibility | Met | `data/raw/manifest.json` (URL, version, SHA-256), `:ImportMeta` per source, pinned versions, count checks after every ingest |

Fixed in this PR (documentation or configuration only): README description, architecture and
Makefile sections; nginx healthcheck; nginx `proxy_read_timeout` raised to 300 s, because an agent
answer that waits on rate limits took up to about 140 s in the evaluation, longer than nginx's 60 s
default.
