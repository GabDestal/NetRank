# Decision log

Decisions taken so far, each with the alternatives on the table and the checklist item it serves.
This is a list for the author to write up in the modeling rationale; the reasoning is deliberately
not written here.

## Phase 1 — Scaffold

| # | Decision | Alternatives considered | Checklist item |
| --- | --- | --- | --- |
| D1 | Neo4j `5.26.32` Community (5.x LTS) | Neo4j 2025.x calendar releases; Enterprise (Docker eval licence) | Docker: official image |
| D2 | GDS installed by `NEO4J_PLUGINS` at container start, cached in a `plugins` volume | Custom Neo4j image with the jar baked in; manual jar mount | GDS projection + algorithms |
| D3 | Neo4j Python driver 6.x with `execute_query` and explicit read/write routing | Driver 5.x; session/transaction functions; `graphdatascience` client | Optimization: parameterised queries |
| D4 | API container publishes no port; nginx is the single entry point; Neo4j ports bound to 127.0.0.1 | Publish API port directly; Traefik; API-key auth only | SE: reverse proxy or auth (3 pts) |
| D5 | Liveness (`/api/health`, no DB) separate from readiness (`/api/health/ready`, Neo4j + GDS); Docker healthcheck uses liveness | Single health endpoint; healthcheck on readiness | Tests: container health |
| D6 | Missing GDS reported as `503 degraded`, not a crash | Fail startup; 200 with a flag | FastAPI: error handling |
| D7 | `.pylintrc` = course template, with missing-docstring checks re-enabled and `suggestion-mode` commented (removed in pylint 4) | Template verbatim; pylint defaults | Clean code: pylint ≥ 9.5, docstrings |
| D8 | GHCR (`ghcr.io/gabdestal/netrank-api`), pushed by CI from `main` after the stack test passes | Docker Hub; manual push | Docker: public registry |
| D9 | Coverage badge from `python-coverage-comment-action` (data branch in this repo) | Codecov / Coveralls (third-party account) | SE: badges |
| D10 | Tests split unit / integration / container; CI fails instead of skipping when services are missing | One flat suite; mocks only | Tests: unit/API/Neo4j, container health |
| D11 | `requirements.txt` (runtime, in the image) vs `requirements-dev.txt` (tests, lint) | One file; `pyproject.toml` extras | Repository contents |
| D12 | Neo4j heap 1G, page cache 512M (revisit after ingestion sizes are known) | Image defaults; `neo4j-admin server memory-recommendation` | Optimization |

## Phase 2 — Data exploration and ingestion

Evidence for each choice is in [data_exploration.md](data_exploration.md).

| # | Decision | Alternatives considered | Checklist item |
| --- | --- | --- | --- |
| D13 | `Tournament` = one yearly edition (`tourney_id`), with year, level, surface, draw size | Edition + series nodes (`EDITION_OF`); edition node with a normalised `seriesKey` property | Schema: labels and properties |
| D14 | Scope: tour-level matches (Grand Slam, Masters, ATP Tour, Tour Finals) dated 1991-01-01 or later; Davis Cup and Olympics excluded | Add Davis Cup (~10k matches, ~1.7k low-degree players); all levels in the files | Dataset documented and justified |
| D15 | Walkovers kept as `Match {walkover: true}` (to be excluded from the `LOST_TO` projection); retirements flagged `retired: true` | Drop walkovers at load time; treat retirements like walkovers | Schema: meaningful properties |
| D16 | Each player's match facts (rank, seed, entry, age, serve stats) as properties of their own `WON` / `LOST` relationship | `Performance` node between Player and Match; flat `w_*` / `l_*` properties on Match | Schema: relationship properties |
| D17 | Communities: Louvain on the who-beat-whom graph, presented as competition clusters (not playing styles) | Style vectors from serve stats -> KNN `SIMILAR_STYLE` -> Louvain; run both and compare | GDS: algorithms |
| D18 | Source duplicate players (same name and birth date) merged into the id with most matches | Keep both ids; hand-maintained mapping | Ingestion / data quality |
| D19 | `surface` stored on both `Tournament` and `Match` | `Surface` node; on Tournament only | Indexes / query patterns |
| D20 | Sackmann data from a fork pinned to the final upstream commit `712be0c5`, every file verified by Git blob hash | Unpinned mirror; Kaggle re-uploads; another results dataset | Dataset source documented |
| D21 | tennis-data.co.uk files downloaded manually; no scraper in the repo (site terms forbid automated/AI downloads) | Scripted download; ask the site for permission; drop the odds source | Dataset source documented; second source |
| D22 | Entity resolution: odds date in [tourney_date, +16 days] -> names (exact; surname variants; surname only with cross-source rank agreement) -> round, then tournament-name similarity; one odds row per match; rows after 2026-06-08 out of coverage | Window [-2, +16] (+611 links); fuzzy-matching library; alias table for the remaining names; no rank check on surname-only | Ingestion; data quality |
| D23 | `Bookmaker` nodes for Bet365, Pinnacle, Expekt, Ladbrokes (>= 10 seasons); `PRICED {winnerOdds, loserOdds, overround}`; Max/Avg market odds as `Match` properties | Every bookmaker with any coverage; Bet365 + Pinnacle only; Max/Avg as aggregate Bookmaker nodes | Schema; ML benchmark source |
| D24 | Odds-link provenance on `Match` (`oddsLinkMethod`, `oddsDayOffset`, `oddsSourceRow`) | Provenance only in the gitignored logs | Data quality / traceability |
| D25 | `Player.id` = Sackmann `player_id`; names taken from the players file, whitespace normalised | Names from match rows | Constraints |
| D26 | Only players appearing in in-scope matches are loaded (2,316 of 66,912) | Load the whole players file | Graph size / GDS projection |
| D27 | Uniqueness constraints on `Player.id`, `Match.id`, `Tournament.id`, `Bookmaker.name`; range indexes on `Match.date`, `Player.name` | Node key constraints; full-text index on names (revisit in Phase 3 with PROFILE) | Constraints (>= 2); indexes |
| D28 | Batched `UNWIND $rows ... MERGE` loads (2,000 rows per transaction) through the API's `Neo4jClient` | `LOAD CSV`; `neo4j-admin import`; row-by-row writes | Ingestion script; parameterised queries |
| D29 | ETL dependencies (pandas, openpyxl, xlrd) in `requirements-etl.txt`, kept out of the API image | One requirements file | Docker: image size |
| D30 | `make lint` runs pylint with `--jobs=1` (template has `jobs=0`) after an intermittent Windows process-pool crash | Keep `jobs=0` | Makefile: commands functional |
