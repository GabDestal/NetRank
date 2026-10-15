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

## Data

```bash
make download           # fetch every source into data/raw/ (skips files already there)
make download FORCE=1   # re-download everything
python -m scripts.download --only kev nvd   # selected sources
```

| Source | Version | File |
|--------|---------|------|
| MITRE ATT&CK Enterprise (STIX 2.1) | 20.0, pinned | `data/raw/attack/enterprise-attack-20.0.json` |
| CISA KEV catalog | latest (version recorded) | `data/raw/kev/known_exploited_vulnerabilities.json` |
| CTID Mappings Explorer, KEV → ATT&CK | 16.1, file `kev-07.28.2025` | `data/raw/ctid/kev-07.28.2025_attack-16.1-enterprise.json` |
| NVD API 2.0, every CVE in KEV | retrieval date | `data/raw/nvd/nvd_kev_cves.json` |

NVD records come from the API's `hasKev` filter (4 paged requests); any KEV CVE it misses is fetched
individually. Set `NVD_API_KEY` in `.env` to raise the rate limit
([request a key](https://nvd.nist.gov/developers/request-an-api-key)).
Each download is validated (expected version, expected structure) before it is kept, and recorded in
`data/raw/manifest.json` with its URL, version, SHA-256, size and download time.

## Running

```bash
make run          # API only, on http://localhost:8000 (auto-reload)
make docker-run   # neo4j + api + nginx
make docker-down  # stop the stack, keep the Neo4j volume
```

Once Neo4j is up, create the constraints and indexes (safe to re-run):

```bash
make schema
```

Then load the downloaded data (creates the schema first; re-runs update in place):

```bash
make ingest     # ATT&CK, then KEV + NVD; every count is verified after loading
```

| Source | Loads | Counts (2026-10-15) |
|--------|-------|---------------------|
| ATT&CK v20 | groups, campaigns, software, techniques, tactics, mitigations and their relationships | 1,842 nodes, 21,838 relationships |
| KEV + NVD | CVEs, CWEs, products, vendors; `HAS_WEAKNESS`, `AFFECTS`, `MADE_BY` | 1,745 CVEs, 203 CWEs, 3,599 products, 393 vendors; 37,040 relationships |

The Docker stack needs `.env` with `NEO4J_PASSWORD` set (letters and digits only). The first start downloads the APOC and GDS plugins, which can take a few minutes.

| Service | URL | Notes |
|---------|-----|-------|
| nginx → api | http://localhost:8080 | `GET /health` → `{"status": "ok"}`; `GET /health/db` → Neo4j version, or 503 if unreachable |
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
