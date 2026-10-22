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
| D17 | ~~Communities: Louvain on the who-beat-whom graph, presented as competition clusters (not playing styles)~~ **Superseded by D42** | Style vectors from serve stats -> KNN `SIMILAR_STYLE` -> Louvain; run both and compare | GDS: algorithms |
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

## Phase 3 — Cypher endpoints and benchmarks

Measurements for each choice are in [benchmarks.md](benchmarks.md).

| # | Decision | Alternatives considered | Checklist item |
| --- | --- | --- | --- |
| D31 | Name search through a full-text index (`standard-folding` analyser); each word becomes a folded prefix; ties broken by career length | `toLower(name) CONTAINS`; TEXT index; a normalised `searchName` property with a range index and `STARTS WITH` | Indexes; FastAPI endpoints |
| D32 | Derived `(Player)-[:BEAT {wins, firstWin, lastWin}]->(Player)`, all-time, walkovers excluded, rebuilt on every `make ingest`; `Match` stays the source of truth | One `BEAT` per pair and season; no materialisation (traverse `Match` every time) | Schema; optimisation |
| D33 | Nemeses ranked by the opponent's wins over the player, then by head-to-head margin; `min_wins` filter (default 2) | Rank by margin; rank by win share | Complex pattern matching |
| D34 | Non-transitive triangle = player > second > third > player where every `>` is a strict head-to-head lead; sorted by the weakest lead | Any single win per edge; return only the count | Complex pattern matching |
| D35 | Beat chain = `SHORTEST 1` over `BEAT`, search capped at 6 hops (a literal: quantifier bounds cannot be parameters), `max_hops` parameter (default 4) rejects longer chains; each hop backed by the latest played match | `allShortestPaths`; unbounded search; weighted path (e.g. recency) via GDS | Pathfinding in an endpoint |
| D36 | Offset pagination (`page`, `size` <= 100) returning `total` on every list | Keyset/cursor pagination; no total | Optimisation: pagination |
| D37 | Services raise `NotFoundError` / `InvalidRequestError`; app-level handlers map them to 404 / 400, driver outages to 503 on every endpoint; validation errors stay 422 | try/except in each router | FastAPI: error handling |
| D38 | Cypher kept as named constants in `app/services`, fully parameterised; services return typed Pydantic models | Query builder / OGM; raw dicts to routers | Clean architecture; Pydantic |
| D39 | Benchmarks force the "before" plan with `USING SCAN` instead of dropping indexes; each pair must return identical results; cases without gain are reported, not dropped | Drop and recreate indexes; report only improvements | Optimisation: benchmarks; EXPLAIN/PROFILE |

## Phase 4 — Graph Data Science

| # | Decision | Alternatives considered | Checklist item |
| --- | --- | --- | --- |
| D40 | Prestige = weighted PageRank where losers point to winners (weight = wins). All-time: native projection of `BEAT` reversed, written by the refresh. `?era=`: Cypher-aggregation projection over `Match` inside the window (BEAT's wins are career totals and cannot be cut by date), streamed per request | Per-season BEAT; precomputed decades only; unweighted PageRank; ArticleRank / eigenvector centrality | GDS projection + algorithms; pathfinding/GDS in endpoints |
| D41 | "Similar" = playing style: 11 career features per player (ace %, double-fault %, 1st-serve in / won %, 2nd-serve won %, break points saved %, return points won %, break points converted %, clay/grass/hard win shares), z-scored, only for players with >= 50 matches with serve statistics (712 players); KNN cosine, topK = 10, written as `SIMILAR_STYLE {score}` | FastRP on `BEAT` (encodes era and circuit, see D42 evidence); stats concatenated with FastRP; unscaled features; Euclidean distance; threshold 30 (828 players) or 100 (520) | GDS algorithms; endpoints |
| D42 | Styles (`/api/styles`) = Louvain on the undirected KNN graph (`toUndirected`, MAX), weighted by similarity: 9 styles, modularity 0.62. Louvain on `BEAT` is shown in the notebook only, as the counter-example (table below) | Louvain on `BEAT` (D17); Leiden; K-means on the feature vectors | GDS algorithms; modeling rationale |
| D43 | Lifecycle: the refresh writes everything the API reads (`prestige`, `prestigeRank`, style features, `styleVector`, `styleId`, `SIMILAR_STYLE`) and drops its projections, so a Neo4j restart loses nothing. Era PageRank is the only per-request projection: unique name, dropped in `finally`, one at a time (lock), results cached per era (32 eras, cleared by the refresh). Missing results or GDS failures answer 503 with what to run | Keep named projections in the catalog and stream everything; rebuild projections at API startup; precompute all eras | Optimisation; error handling |
| D44 | `POST /api/admin/gds/refresh` protected by `X-API-Key` = `ADMIN_API_KEY` from the environment, compared with `secrets.compare_digest`: 401 when missing, 403 when wrong, 503 when the server has no key configured. Same work available offline as `make gds` | OAuth2 / JWT; HTTP Basic; restriction at the nginx layer only | Reverse proxy or authentication |
| D45 | FastRP is exposed only as `fastrp_embeddings(cutoff)`: projects played matches strictly before the cutoff (undirected, weighted by wins), dimension 64, `iterationWeights [0, 1, 1]`, for Phase 5 features; never written to the database | Write one embedding property for all time (leaks future matches into training features); GraphSAGE | ML workflow (leakage) |
| D46 | Reproducibility: `randomSeed 42` on FastRP and KNN; KNN and Louvain always run with concurrency 1 (GDS rejects `randomSeed` on KNN otherwise, and Louvain ids become `styleId`s); PageRank and FastRP use `GDS_CONCURRENCY` (1 in tests, up to 4 on Community) after checking they are identical at 4 (FastRP bit-identical; PageRank same order, scores within 1e-14). A test runs the refresh twice and compares | Seed only; same concurrency everywhere; accept run-to-run variation | Tests; GDS |
| D47 | PageRank: damping 0.85, `maxIterations` 100, tolerance 1e-7 (converges in 94 iterations; at 50 it did not converge although the top 20 was already identical) | Defaults (20 iterations); tolerance 1e-6 (80 iterations) | GDS |
| D48 | Style communities stored as `Player.styleId` (renumbered 1..k by size), not as `Style` nodes; each style's traits are computed from its centroid (top 3 features with \|z\| >= 0.5, fixed labels such as "big server", "strong returner") without any LLM | `Style` nodes with `HAS_STYLE`; LLM-generated style names | Schema; agent "interpreted" vs "verified" (Phase 6) |
| D49 | Era syntax `2000s`, `2004-2008` or `2010`, clipped to 1991–2026; a player absent from the era gets a 404 naming them | Separate `since`/`until` parameters; dates instead of seasons | FastAPI: validation, error handling |

### Evidence for D42: what Louvain finds on each graph

Same 712 styled players, Louvain with concurrency 1. η² is the share of a variable's variance explained by the
community assignment; country purity is the average share of each community's most common nationality.

| Partition | Communities (>= 10 members) | Debut year η² | Country purity | Style features η² (mean of 11) |
| --- | ---: | ---: | ---: | ---: |
| Louvain on `BEAT` (who beat whom) | 4 | **0.91** | 0.12 | 0.06 |
| Louvain on style KNN | 9 | 0.13 | 0.20 | **0.50** |

The four `BEAT` communities are generations: median debut 1991 (left-censored at the start of the data),
1996, 2004 and 2017. They are **not** regional: the largest nationality is ~12% of each. Style communities
mix eras and explain half the variance of the style features. Consistency check for D40: an era covering
every season ranks the top 200 players in exactly the same order as the native all-time projection.
