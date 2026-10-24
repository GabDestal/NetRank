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
- Sackmann upstream repo is GONE from GitHub. `make download` fetches fork `Kadantte/tennis_atp` pinned
  to commit 712be0c5 and verifies every file by Git blob hash. Data ends 2026-06-08.
- tennis-data.co.uk forbids automated/AI downloads (terms + robots.txt). NEVER fetch from that site;
  the user downloads the files by hand into `data/raw/tennis_data/`. Commit aggregates only, never
  row-level tennis-data content (`data/processed/` is gitignored).
- Stack (pin every version): Neo4j 5 + GDS (official image), FastAPI, Pydantic, neo4j driver, LangGraph,
  Groq free tier, pytest, Python 3.11.
- Services: `neo4j`, `api` (Dockerfile, pushed to GHCR), `nginx`. Each has a healthcheck.

## Schema as loaded (decided with the user in Phase 2; see docs/decision_log.md D13–D30)
- Labels: Player, Match, Tournament (= one yearly edition), Bookmaker (Bet365, Pinnacle, Expekt, Ladbrokes).
- (Player)-[:WON {rank, seed, entry, age, aces, ...}]->(Match), same for LOST: per-player match facts
  live on the relationship. (Match)-[:PART_OF]->(Tournament).
  (Bookmaker)-[:PRICED {winnerOdds, loserOdds, overround}]->(Match). Max/Avg market odds and odds-link
  provenance (oddsLinkMethod, oddsDayOffset) are Match properties.
- Scope: tour-level G/M/A/F from 1991-01-01. Match.walkover / Match.retired flags; walkovers must be
  excluded from the GDS projection (Player)-[:LOST_TO {weight}]->(Player).
- Constraints: Player.id, Match.id, Tournament.id, Bookmaker.name. Indexes: Match.date, Player.name.
- Derived (Player)-[:BEAT {wins, firstWin, lastWin}]->(Player), all-time, walkovers excluded, rebuilt by
  make ingest (D32). Path/nemesis/triangles use BEAT; era-filtered queries must traverse Match.
  GDS LOST_TO can be a native projection of BEAT reversed with weight = wins.
- Full-text index player_name_ft (standard-folding) backs /api/players?q=.
- GDS (Phase 4, D40-D49): all-time prestige = PageRank on native reversed-BEAT projection, written by
  `make gds` / POST /api/admin/gds/refresh; era prestige = per-request Cypher projection over Match,
  cached per era. Similar = KNN on 11 z-scored style features (players >= 50 stat matches);
  styles = Louvain on undirected KNN graph -> Player.styleId. Refresh writes results and drops projections.
- KNN and Louvain must run with concurrency 1 (randomSeed rule, stable styleIds); PageRank/FastRP use
  GDS_CONCURRENCY. FastRP only via fastrp_embeddings(cutoff) for leakage-free ML features (Phase 5).
- Phase 7 notebook MUST include the Louvain-on-BEAT vs style-Louvain comparison (numbers in D42).
- ML (Phase 5, D50-D59): app/ml/features.py is shared by scripts/train.py and /api/predict. Features are
  p1-p2 differences from a season snapshot (Jan 1) + history strictly before the match date; never use
  stored Player.prestige as a feature (leaks). The test set (2022+) is frozen: never tune on it.
  Model = logistic JSON in models/ (gitignored, mounted into api). make train runs GDS_CONCURRENCY=1.
  Probabilities are tagged: model "predicted", odds/results "verified" (reuse in the agent, Phase 6).
- Entity resolution window is [tourney_date, +16] as the user specified (not [-2, +16]).
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

- Agent (Phase 6, D60-D70): app/agent/ (graph, tools, guardrails, verifier, llm, replay). Groq model from
  GROQ_MODEL (default openai/gpt-oss-120b; llama-3.3-70b-versatile is retired). Free tier = 8k tokens/min:
  pace live runs (`make eval LABEL=live-N`, 60 s pause). CI never calls Groq (recordings in eval/recordings/).
  Every eval run is kept (eval/runs/, docs/agent_eval/); a new live run gets a new label, never overwrite;
  fixes are re-scored as new replay runs (replay-fixed-of-live-N). Question sets are versioned
  (eval/questions_v1.json = 20, v2 = 24). Daily Groq cap ~200k tokens: a full v2 run needs a fresh day.
- D71-D75: misrouted answers (`json`/`commentary` tools) recovered only if valid + verified; prompt cuts
  (specs, trimmed results); 429s logged, daily cap stops the run; `make demo-guardrail` (offline).
- D77: every live Groq session is logged in eval/quota_log.json; a live eval refuses to start within 24 h of the
  last logged use (`make quota` shows when it is fresh). No override flag: correct the log in a commit.
- D78: Cypher retry budget 2 fixes (closes after 3 rejections), Neo4j 5 syntax hints in EXPLAIN feedback, null note
  on Match.minutes (Cypher is never rewritten), steps left shown, submit_answer only on the last step;
  answer kind "incomplete" (+ required `missing`) for partial results. Replays
  report recordings that no longer fit as "out of sync (replay)", not scored. live-5 (22/24) is the headline.

## Hard constraints
- pylint ≥ 9.5 (`make lint`, else −8). `.pylintrc` = course template + docstring checks re-enabled.
- Every Makefile target works (else −3): help, install, run, docker-run, test, lint, clean.
- Coverage ≥ 60% (`make test`). Docstrings on every module, class, function. Max line 120.
- Parameterised Cypher only. Pydantic models on every endpoint. Meaningful HTTP codes.
- Never commit `.env` or secrets (−5 each). Keep `.env.example` current.

## Workflow
- One branch per phase, conventional commits (feat:, fix:, test:, docs:, refactor:, chore:), PR into main.
  Never commit to main. When CI is green, squash-merge the PR yourself, then continue; still stop for
  the user on modeling decisions. No Claude attribution lines in commits/PRs.
- Logging: the course .pylintrc expects f-strings in log calls (logging-format-style=new).
- Do NOT write the modeling rationale or the anti-genericity appendix. Record each decision with its
  alternatives in `docs/decision_log.md`; the user writes the reasoning.
- Code reviews (1 pt) need ≥ 2 constructive comments per PR: the user leaves these, not Claude.

## Phases
0 reset ✔ → 1 scaffold ✔ → 2 data exploration + ingestion ✔ →
3 Cypher endpoints + PROFILE before/after benchmarks ✔ → 4 GDS endpoints ✔ → 5 ML ✔ → 6 agent + guardrails ✔ (live-5 scored in a later docs: PR) →
7 docs + demo.ipynb.

## Commands
`make install` (uv if present, Python 3.11), `make docker-run` (waits for healthy), `make download`,
`make ingest` (~1 min, regenerates docs/data_exploration.md), `make gds` (~5 s), `make train` (~1 min), `make benchmark` (~2 min, docs/benchmarks.md),
`make test`, `make test-stack`, `make lint`.
- `make hooks` installs pre-commit (D76): gitleaks/black/file checks/data guard on commit, pylint + unit tests on push.
  Hook revs are frozen SHAs; keep new revs at least two weeks old. CI is the authority.
- API conventions: services raise NotFoundError/InvalidRequestError (app/errors.py), mapped in app/main.py;
  lists return Page[T] (app/models/common.py) with page/size from app/routers/params.py. Local `.venv` is at `.venv/Scripts` on Windows, `.venv/bin` elsewhere.

## Layout
```
app/  main.py, config.py, routers/, services/ (Cypher), models/ (Pydantic), database/client.py, agent/
scripts/  download + ingestion      tests/  unit/, integration/, container/
nginx/  default.conf                docs/   guidelines.md, decision_log.md, diagrams
```
