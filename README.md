# NetRank

[![Lint](https://github.com/GabDestal/NetRank/actions/workflows/lint.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/lint.yml)
[![Tests](https://github.com/GabDestal/NetRank/actions/workflows/tests.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/tests.yml)
[![Docker](https://github.com/GabDestal/NetRank/actions/workflows/docker.yml/badge.svg)](https://github.com/GabDestal/NetRank/actions/workflows/docker.yml)
[![Coverage](https://raw.githubusercontent.com/GabDestal/NetRank/python-coverage-comment-action-data/badge.svg)](https://github.com/GabDestal/NetRank/tree/python-coverage-comment-action-data)

NetRank is a tennis knowledge graph built with Neo4j. It uses ATP matches from 1991 to 2026 to:

- rank players by "prestige" (PageRank on who beat whom),
- group players by playing style,
- predict who wins a match and compares with the bookmakers,
- answers questions using a LangGraph agent.

## Quick start

Requires: Docker (w/ Compose v2), make and Python 3.11.

```bash
cp .env.example .env    # set NEO4J_PASSWORD, ADMIN_API_KEY and GROQ_API_KEY
make install            # create .venv and install dependencies
make docker-run         # start neo4j, api and nginx
make download           # get the Sackmann files
# download the tennis-data.co.uk files by hand (see Datasets)
make ingest             # load the data into Neo4j (~1 min)
make gds                # compute prestige, similarity and styles
make train              # train the match model (~1 min)
```

API docs: <http://localhost:8080/docs>.

## Architecture

The project runs as three Docker services:

| Service | Role | Port |
| --- | --- | --- |
| `neo4j` | Neo4j 5.26 with the GDS plugin | 7474, 7687 (localhost only) |
| `api` | FastAPI app ([image on GHCR](https://github.com/GabDestal/NetRank/pkgs/container/netrank-api)) | behind nginx |
| `nginx` | Reverse proxy, the only public entry point | 8080 |

<!-- TODO: add docs/diagrams/architecture.png (services, ports, data flows) -->
![Architecture](docs/diagrams/architecture.png)

## Graph schema

<!-- TODO: add docs/diagrams/schema.png (draw.io) -->
![Graph schema](docs/diagrams/schema.png)

- **Nodes:** `Player`, `Match`, `Tournament`, `Bookmaker`
- **Relationships:** `(Player)-[:WON]->(Match)`, `(Player)-[:LOST]->(Match)`,
  `(Match)-[:PART_OF]->(Tournament)`, `(Bookmaker)-[:PRICED]->(Match)`
- **Derived:** `(Player)-[:BEAT {wins}]->(Player)`, rebuilt from the matches at each ingest

| Element | Count |
| --- | ---: |
| Players | 2,316 |
| Tournaments (one per yearly edition) | 2,494 |
| Matches | 102,417 |
| Bookmaker prices | 181,474 |
| `BEAT` edges | 66,624 |

### Modeling choices

<!-- TODO: write the modeling rationale (from docs/decision_log.md) -->

## Datasets

**Jeff Sackmann, ATP results.** All tour-level matches from 1991 to 8 June 2026, with player stats.
(NOTE: The original repo was removed from GitHub, so I download it from a fork pinned to his last commit)
([`712be0c5`](https://github.com/Kadantte/tennis_atp/tree/712be0c5ade693cdab9e69c23a71a0edf5a23c44)).
`make download` checks every file against that commit, so the data is identical to his.
Licence: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), non-commercial use only.

**tennis-data.co.uk, bookmaker odds.** ATP results with bookmaker odds, 2000 to 2026. The graph keeps four
bookmakers: Bet365 (from 2002), Pinnacle and Expekt (from 2004) and Ladbrokes (from 2007). The site does not
allow automated downloads, so you'll have to get the files manually:

<https://www.tennis-data.co.uk/alldata.php>.

These files are not in the repo, and only aggregates are published.

**Linking the two.** An odds row is matched to a Sackmann match when the dates fit the tournament
and both player names agree. 98.74% of the odds rows are linked. Details are in
[docs/data_exploration.md](docs/data_exploration.md).

## API

All lists are paginated (`page`, `size`). Full docs at <http://localhost:8080/docs>.

| Endpoint | What it does |
| --- | --- |
| `GET /api/players?q=` | Search a player by name |
| `GET /api/players/{id}` | Career record, titles and best rank |
| `GET /api/players/{id}/matches` | Match history with odds |
| `GET /api/h2h?p1=&p2=` | Head-to-head, overall and per surface |
| `GET /api/players/{id}/nemesis` | Who beats this player, and non-transitive triangles |
| `GET /api/path?from=&to=` | Shortest "beat chain" between two players |
| `GET /api/players/{id}/prestige?era=` | Prestige rank (PageRank), all-time or for an era |
| `GET /api/players/{id}/similar` | Players with the closest playing style (KNN) |
| `GET /api/styles` | Playing-style groups (Louvain) |
| `GET /api/predict?p1=&p2=` | Chance that p1 wins |
| `POST /api/agent/ask` | Ask the agent a question |
| `POST /api/admin/gds/refresh` | Recompute the GDS results (needs `X-API-Key`) |

Examples:

```bash
curl "localhost:8080/api/h2h?p1=104925&p2=104745"
# Djokovic vs Nadal: 30-28

curl "localhost:8080/api/path?from=100532&to=103819"
# Johan Kriek beat Fabrice Santoro, who beat Roger Federer

curl "localhost:8080/api/players/104925/prestige?era=2010s"
# Djokovic is #1 of 774 players in the 2010s
```

## Results

**Match prediction.** I trained a logistic regression on graph features only, using matches up to
2021, and tested it on 9,923 matches from 2022 to 2026. Every feature only uses matches played
before the match being predicted. The bookmakers do better, but the graph model reaches the same
level as the ATP ranking.

| Method | Log loss | Accuracy |
| --- | ---: | ---: |
| Pinnacle | 0.586 | 68.1% |
| Bet365 | 0.587 | 67.8% |
| ATP ranking | 0.632 | 63.9% |
| Graph model | 0.638 | 64.0% |

Full report: [docs/model_report.md](docs/model_report.md).

**Query optimisation.** I measured each query with PROFILE before and after optimising it.

| Query | Before | After |
| --- | ---: | ---: |
| Beat cycles through Djokovic | 10.0 s | 7 ms |
| Beat chain, 3 steps | 123 ms | 3 ms |
| Career totals | 229 ms | 4 ms |
| Matches in one week | 39 ms | 3 ms |

Full report: [docs/benchmarks.md](docs/benchmarks.md).

## Agent

The agent is built with LangGraph and uses an LLM from Groq. It answers questions by calling tools
that query the graph, and it shows every tool call it made.

Guardrails:

- It uses typed tools first (Free Cypher is only a fallback)
- Generated Cypher is checked before running: no writes, only known labels, `EXPLAIN` must pass,
  and a `LIMIT` is added.
- Queries run in a read-only transaction w/ a timeout.
- Each claim in an answer is tagged **verified** (from the graph), **predicted** (from the model)
  or **interpreted** (from the LLM). A number tagged verified must appear in a tool result.
- Ambiguous player names lead to a clarification question.

The agent is tested on 24 questions with answers computed from the graph. Run it with `make eval`.
On the latest live run (live-5, `openai/gpt-oss-120b`, 24 October 2026) it answered 22 of the 24 questions
correctly (19 of the original 20) and handled the 3 adversarial ones safely. 12 of the 24 answers needed
salvage: the model often sends its answer to a tool that does not exist, and the agent keeps it only if it
matches the answer schema and passes the verifier. The score of every run is in
[docs/agent_eval.md](docs/agent_eval.md).
`make demo-guardrail` replays a write query through the guardrails without calling the LLM.

> **Disclaimer:** NetRank is a school project. It does not give betting advice, and the agent
> refuses to recommend bets.

## Screenshots

<!-- TODO: Swagger UI, an agent answer with its tool calls, a guardrail rejection -->

## Makefile

| Command | What it does |
| --- | --- |
| `make help` | List all commands |
| `make install` | Create `.venv` and install dependencies |
| `make run` | Run the API locally on port 8000 |
| `make docker-run` | Start the three services |
| `make docker-down` | Stop the services (data is kept) |
| `make download` | Download the Sackmann files |
| `make ingest` | Load the data into Neo4j |
| `make gds` | Compute prestige, similarity and styles |
| `make train` | Train and test the match model |
| `make benchmark` | Run the PROFILE benchmarks |
| `make eval` | Run the agent evaluation |
| `make eval-replay RUN=<label>` | Re-score a recorded run without calling Groq |
| `make quota` | Check that Groq's daily quota is fresh (`make eval` refuses to start otherwise) |
| `make demo-guardrail` | Show the guardrails rejecting a write query (offline) |
| `make test` | Run the tests with coverage |
| `make lint` | Run pylint (must stay above 9.5) |
| `make hooks` | Install the git hooks (pre-commit checks; pylint and unit tests before a push) |
| `make clean` | Remove caches |

## Tests

The tests are split into unit tests, Cypher tests on a live Neo4j, and container health tests.
CI runs lint, tests with coverage, and the full Docker stack on every push

## Contributions

Solo project so all contributions are mine

## Appendix: my schema vs an AI-generated schema

<!-- TODO: compare with a basic schema generated by an AI assistant and explain the differences -->
