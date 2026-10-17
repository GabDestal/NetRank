# ThreatGraph — project brief for Claude Code

## What this is
Solo course project for "Graph Database & Knowledge" (CentraleSupélec, AIDAMS 3A).
A Cyber Threat Intelligence knowledge graph in Neo4j linking:
- MITRE ATT&CK (Enterprise, STIX 2.1): threat groups, techniques/sub-techniques, tactics, mitigations, software
- CISA KEV: actively exploited CVEs
- NVD API 2.0: CVE details (CVSS, CWE, affected products/CPE) — only for CVEs in KEV
- A CVE ↔ ATT&CK bridge (candidate: Center for Threat-Informed Defense Mappings Explorer, KEV → ATT&CK)

Exposed through FastAPI, with a LangGraph agent on top (NL questions → graph tools → cited answer).

Project level: 3 ("Advanced graph & GDS"). The core is graph analytics (GDS centrality and communities,
live node similarity, bounded shortest paths, link prediction, mitigation cover plan); the agent is one
component built on top.

## Hard constraints (graded — do not break)
- pylint score >= 9.5 on `app/` (`make lint`). Below that = -8 points.
- Every Makefile command must work: help, install, run, docker-run, test, lint, clean.
- Never commit secrets. Credentials only via `.env` (gitignored); keep `.env.example` updated.
- Test coverage >= 60% (`make test`). Add tests with every feature.
- Docstrings on every module, class and public function. PEP 8, max line length 120.
- Pydantic models for every endpoint's input and output. Meaningful HTTP error codes.
- All Cypher must be parameterized. No string-formatted queries.
- Docker Compose stack: neo4j (GDS + APOC), api, nginx. Must start cleanly with `make docker-run`.

## Workflow rules
- One feature per branch (`feat/...`, `fix/...`, `test/...`, `docs/...`), merged via PR into `main`.
- Commit prefixes: feat:, fix:, test:, docs:, refactor:, chore:. Small, focused commits.
- Run `make lint` and `make test` before proposing any commit.

## How to work with me
- I must be able to defend every decision at the oral defense. For any modeling or design choice
  (node vs property, relationship direction, index, algorithm choice), present the options with
  trade-offs and let me decide. Do not silently pick a graph schema.
- Explain non-trivial Cypher queries: what they match and how cost grows with graph size.
- Keep a running log of rejected modeling alternatives in `docs/modeling_rationale.md`.
- Prefer simple, readable code over clever abstractions.

## Layout
```
app/
  main.py          FastAPI app
  routers/         endpoints
  services/        business logic + Cypher
  models/          Pydantic schemas
  database/        Neo4j driver/session management
  agent/           graph.py (LangGraph), tools.py, guardrails.py
scripts/           download + ingestion scripts
tests/             pytest
data/raw/          downloaded datasets (gitignored)
docs/              diagrams, rationale, anti-genericity appendix
```

## LLM component requirements (for later)
- Read-only Cypher allow-list; reject writes (CREATE, MERGE, DELETE, SET, REMOVE, DROP, CALL dbms.*).
- Validate generated Cypher with EXPLAIN before executing; enforce LIMIT.
- Distinguish verified facts (from ATT&CK/KEV/NVD) from LLM-inferred links in responses.
- Expose the tool calls / graph paths used for each answer.
- Need at least one demo where a guardrail rejects an invalid LLM output.