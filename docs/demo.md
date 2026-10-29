# Defense runbook

The order of the live demo, with the expected output of each step. Commands run from the repo root in
Git Bash (or any POSIX shell). The graph must already be loaded (`make ingest`, `make gds`, `make train`;
see the README quick start).

> **Groq quota.** The live agent question in step 6 uses the Groq free tier (200k tokens per rolling
> 24 h; one question is about 5k prompt tokens). Run **no `make eval` in the 24 hours before the defense**,
> and check `make quota` the day before. `make quota` covers `make eval` sessions only: rehearsal calls to the
> agent API are not logged. If Groq fails, see [If something fails](#if-something-fails).

## 1. `make help`

Lists every target with its description; the same list as the README Makefile table (a unit test keeps
them identical).

## 2. `make lint`

```text
Your code has been rated at 10.00/10
```

Fails below 9.5. About 40 s.

## 3. `make test`

```text
283 passed
Required test coverage of 60% reached. Total coverage: ~82%
```

Unit tests, Cypher tests on the live Neo4j and container health tests. With the stack down, the
integration and container tests skip. About 1 min.

## 4. `make docker-run`

Starts `neo4j`, `api` and `nginx` and returns once all three are healthy. If the stack is already up it
returns in a few seconds. Show `docker compose ps`: three services, all `healthy`.

## 5. Swagger and four endpoint calls

Open <http://localhost:8080/docs> (nginx is the only public entry point). Every endpoint has typed
parameters and response models; lists are paginated.

Then, in the terminal (or with "Try it out"):

```bash
# Head-to-head, overall and per surface
curl "localhost:8080/api/h2h?p1=104925&p2=104745"
# Novak Djokovic 30-28 Rafael Nadal; Clay 8-19, Grass 2-2, Hard 20-7

# Shortest beat chain (BEAT relationships)
curl "localhost:8080/api/path?from=100532&to=103819"
# 2 hops: Johan Kriek beat Fabrice Santoro (Lyon 1991), who beat Roger Federer

# Prestige for an era (PageRank on a Cypher projection over the 2010s matches)
curl "localhost:8080/api/players/104925/prestige?era=2010s"
# Djokovic: rank 1 of 774 players, 2010-2019

# Prediction of a played match, as of its date (no leakage): 2023 Wimbledon final
curl "localhost:8080/api/predict?p1=207989&p2=104925&match_id=2023-540-226"
# model ("predicted"): Alcaraz 50.7%; Bet365 36.8%, Pinnacle 37.5% ("verified");
# result ("verified"): Alcaraz won 1-6 7-6(6) 6-1 3-6 6-4
```

Points to make on the predict call: features are taken from before `featuresBefore`, each number carries
its tag, and `topContributions` explains the logit.

## 6. The agent

**Live question** (uses Groq quota, about 5k prompt tokens):

```bash
curl -s -X POST localhost:8080/api/agent/ask -H "Content-Type: application/json" \
  -d '{"question": "How many titles has Roger Federer won in the NetRank data?"}' | python -m json.tool
```

This is q01 of the evaluation set, answered correctly in live-5. Show in the response: `answer.claims`
with their `verified` / `predicted` / `interpreted` tags and `sources`, then `trace` (each tool call, its
arguments and result), `steps` and `downgradedClaims`. A live answer can differ from the recorded one.

**Offline backup** (no Groq call):

```bash
make demo-guardrail
```

Replays a scripted write query (`SET p.name = 'hacked'`) and a wrong-property query through the
guardrail layers: the write is stopped by the static check, by `EXPLAIN` (write operator in the plan) and
by the READ transaction; graph node and relationship counts are identical before and after. For a real
model run instead of the scripted one:

```bash
make demo-guardrail REC=eval/recordings/live-5/q21.json
```

live-5 q21: `m.duration` rejected by `EXPLAIN` with the list of real properties, then the corrected
`m.minutes` query accepted; later `exists(m.minutes)` rejected as removed Neo4j 5 syntax and
`m.minutes IS NOT NULL` accepted.

Evaluation results: [agent_eval.md](agent_eval.md) (live-5: 22/24) and
[agent_eval/failure_breakdown.md](agent_eval/failure_breakdown.md).

## 7. The GHCR image

The Docker workflow pushes the API image on every push to `main`, tagged `latest` and with the short
commit SHA. The package is public:

```bash
docker pull ghcr.io/gabdestal/netrank-api:latest
```

Page: <https://github.com/GabDestal/NetRank/pkgs/container/netrank-api>.

## 8. The merged PR history

<https://github.com/GabDestal/NetRank/pulls?q=is%3Apr+is%3Amerged>: one branch per phase or feature,
conventional commits, squash-merged once CI (lint, tests, Docker) is green.
PRs #1-#25 belong to the previous project, archived under the tag `archive/threatgraph-cti`. NetRank
starts at #26:

| PR | Branch content |
| --- | --- |
| #26 | Reset the repo for NetRank |
| #27 | Phase 1: scaffold (compose, Makefile, CI, lint) |
| #28 | Phase 2: data exploration and ingestion |
| #29 | Phase 3: Cypher endpoints and PROFILE benchmarks |
| #30 | Phase 4: Graph Data Science (prestige, style similarity, styles, admin refresh) |
| #31 | Phase 5: leakage-free match-outcome model and `/api/predict` |
| #32 | README update |
| #33 | Phase 6: LangGraph agent, layered Cypher guardrails and evaluation |
| #34 | Pre-commit hooks |
| #35 | Groq quota log |
| #36 | Phase 7: architecture diagram and `demo.ipynb` |
| #37 | live-5 evaluation (22/24) |
| #38 | Cypher retry budget, Neo4j 5 syntax hints, steps left, submit-only last step |
| #39 | `demo.ipynb` re-run |

## If something fails

- **Groq is down or rate-limited:** replay the recorded live-5 answer to the same question, offline:
  `make eval-replay RUN=live-5 ONLY=q01` (Federer, 103 titles, with its tool calls; nothing is saved).
  Then `make demo-guardrail` for the guardrails.
- **Ports are busy** (8080, 7474, 7687): stop the other containers first. n8n runs on this machine:
  `docker ps` lists what is up, `docker ps --filter publish=8080` shows what holds a port, and
  `docker compose down` in the other project's folder (or `docker stop <name>`) frees it. `NGINX_PORT` in
  `.env` moves the API to another port if 8080 cannot be freed.
- **Before the defense:** start the stack and load the data in advance (`make docker-run`, `make ingest`,
  `make gds`, `make train`), so nothing has to be downloaded or ingested live. The Neo4j volume keeps
  the graph across `make docker-down`; check `make test` passes on the morning.
