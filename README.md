# threatgraph

[![lint](https://github.com/GabDestal/threatgraph/actions/workflows/lint.yml/badge.svg)](https://github.com/GabDestal/threatgraph/actions/workflows/lint.yml)
[![test](https://github.com/GabDestal/threatgraph/actions/workflows/test.yml/badge.svg)](https://github.com/GabDestal/threatgraph/actions/workflows/test.yml)

A knowledge graph for cyber threat intelligence (CTI).

![ThreatGraph schema](docs/schema.png)

Schema decisions and rejected alternatives: [`docs/modeling_rationale.md`](docs/modeling_rationale.md).
Diagram source: [`docs/schema.drawio`](docs/schema.drawio).

## Layout

```
app/            Python package (application code)
scripts/        One-off and maintenance scripts
tests/          pytest suite
nginx/          Reverse proxy config for the Docker stack
docs/           Schema diagram (draw.io) and modeling rationale
demo.ipynb      Walkthrough notebook
.env.example    Template for local settings
```

## Getting started

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
make install
cp .env.example .env
```

## Running

```bash
make run          # API only, on http://localhost:8000 (auto-reload)
make docker-run   # neo4j + api + nginx
make docker-down  # stop the stack, keep the Neo4j volume
```

The Docker stack needs `.env` with `NEO4J_PASSWORD` set (letters and digits only). The first start downloads the APOC and GDS plugins, which can take a few minutes.

| Service | URL | Notes |
|---------|-----|-------|
| nginx → api | http://localhost:8080 | `GET /health` returns `{"status": "ok"}` |
| Neo4j Browser | http://localhost:7474 | user `neo4j`, password from `.env` |
| Neo4j Bolt | bolt://localhost:7687 | |

## Development

```bash
make lint       # pylint (fails under 9.5/10)
make test       # pytest + coverage (fails under 80%)
make coverage   # HTML report in htmlcov/
```

CI runs the same checks on every push to `main` and on every pull request:

- `lint.yml`: pylint, minimum score 9.5
- `test.yml`: pytest with coverage

## Contributing

`main` is protected, so every change lands through a pull request that passes both checks.

Commit messages use a type prefix:

- `feat:` new functionality
- `fix:` bug fixes
- `test:` tests only
- `docs:` documentation only
- `refactor:` code changes with no behavior change
- `chore:` tooling, dependencies, housekeeping
