# Course guidelines — GraphDB (AIDAMS 3A, CentraleSupélec)

> **Provenance.** Verbatim copy of the course project specification so that every
> decision in this repo can be traced to a graded criterion.
>
> - Spec + 100-point checklist: gist `bdallard/2ada69b40c3abfe3a7b3f6ed402b4b51`,
>   file `projects_spec.md`, revision `f62ca93d` (updated 2026-08-24). The standalone
>   `project_checklist.md` in the same gist is identical to the checklist section below.
> - Required pylint rules: gist `bdallard/f74fe36835b6f0510e8d30bc7ee05023`,
>   file `.pylintrc-template`, revision `b72566f5` (updated 2025-08-16) — reproduced in the appendix.
> - Course slides `GraphDB_26_27.pdf` (slide 4): projects are 30% of the course grade,
>   handwritten exams 70%; the slides link to the gist above as the project spec.
>
> Fetched 2026-10-22. Do not edit the content below; re-fetch if the gist changes.

---

# GraphDB Projects Specification — AIDAMS 3A

## Table of Contents

- [Project goals and organization 🎯](#project-goals-and-organization-)
- [Working with AI coding assistants 🤖](#working-with-ai-coding-assistants-)
- [Project list](#project-list)
  - [Level 1 — Modeling & Cypher foundations](#level-1--modeling--cypher-foundations)
  - [Level 2 — Graph engineering](#level-2--graph-engineering)
  - [Level 3 — Advanced graph & GDS](#level-3--advanced-graph--gds)
  - [Level 3+ — Agentic / GraphRAG](#level-3--agentic--graphrag)
- [Propose your own project](#propose-your-own-project)
- [Common Technical Stack](#common-technical-stack)
- [Suggested Project Structure 🥸](#suggested-project-structure-)
- [Minimal Makefile template](#minimal-makefile-template)
- [Implementation Tips](#implementation-tips)
- [Project Evaluation Criteria](#project-evaluation-criteria)
- [Project Evaluation Checklist](#project-evaluation-checklist)
- [Expected Deliverables](#expected-deliverables)
- [Important Notes](#important-notes)

---

# Project goals and organization 🎯

## Your mission

Build an **end-to-end graph-backed application** using Neo4j and Python.

Your project must:

- Model a real-world use case as a graph.
- Ingest and clean data through ETL/ELT scripts.
- Expose meaningful graph queries through a FastAPI service.
- Run using Docker Compose.
- Include automated tests and clear documentation.
- Use Docker, Make and Git as part of the development workflow.
- Include at least one **LLM-over-graph or agentic component**.

The goal is not only to produce a functional application. You must also demonstrate that you understand and can justify the main engineering decisions behind your project.

---

## Expected repository contents

Your GitHub repository must include:

- `docker-compose.yml`
- `app/`
- `scripts/`
- `tests/`
- `Makefile`
- `.env.example`
- `requirements.txt`
- `demo.ipynb`
- a comprehensive root `README.md`

The README must contain:

- project description;
- installation and execution instructions;
- API examples;
- screenshots of the working application;
- graph schema;
- system architecture;
- dataset sources;
- modeling rationale.

You must also provide a **graph-schema diagram** and explain the modeling alternatives you considered and rejected.

Use a diagramming tool such as draw.io.

---

## Team size

Projects must be completed in groups of **up to 5 students**.

A team lead must be identified for each group.

The team lead is responsible for:

- coordinating Git branches;
- assigning or reviewing Pull Requests;
- ensuring that contributions remain reasonably balanced.

---

# Agentic / GraphRAG requirement

Every project must include at least one component placing an LLM or an agent on top of the graph.

The expected complexity depends on the project level.

### Levels 1–2

A **Natural Language → Cypher** system is sufficient.

Example:

> What do I still need to take before I can enroll in Machine Learning?

The system should:

1. receive the natural-language question;
2. generate a Cypher query;
3. validate the generated query;
4. execute it against Neo4j;
5. return a structured response.

Guardrails must prevent unsafe, invalid or inappropriate queries.

### Levels 3–3+

A genuine **LangGraph agent** is expected.

The agent should be able to:

- reason over several steps;
- call tools;
- query Neo4j;
- optionally call external APIs;
- combine multiple sources of information;
- expose the sequence of tool calls or graph paths used to produce the answer.

The objective is not simply to call an LLM.

You must explicitly address the fact that LLM-generated information can be unreliable.

Depending on the project, consider:

- query validation;
- confidence scores;
- schema constraints;
- allow-listed Cypher operations;
- structured outputs;
- fact verification;
- distinction between verified facts and AI-generated hypotheses.

---

# Working with AI coding assistants 🤖

Using tools such as ChatGPT, Claude, GitHub Copilot or similar coding assistants is allowed and encouraged 🥷

However, **a working project alone is not sufficient**.

Modern AI assistants can easily generate:

- FastAPI scaffolding;
- Neo4j CRUD endpoints;
- Dockerfiles;
- simple Cypher queries;
- tests;
- basic documentation.

*Your evaluation therefore focuses strongly on the engineering decisions behind the implementation.*


⚠️ You must be able to explain ⚠️

- why you chose a particular graph schema;
- why something is represented as a node rather than a property;
- why a relationship exists;
- why an index is useful;
- how a Cypher query works;
- how its complexity behaves as the graph grows;
- how the LLM component is constrained;
- how unreliable AI-generated outputs are detected or handled;
- why you selected one graph algorithm over another.

---

## Modeling & anti-genericity requirement

Your README or demonstration notebook must contain a short appendix comparing:

1. the graph schema used in your project;
2. a basic graph schema generated by an AI assistant from the same project description.

Explain where your model differs and **why**.

The purpose is not to avoid AI tools.

The purpose is to demonstrate that your team made deliberate modeling decisions rather than accepting the first generated schema without analysis.

---

# Project list

### Difficulty levels

| Level | Focus |
|---|---|
| **1** | Modeling and Cypher foundations |
| **2** | Graph engineering, Docker, FastAPI, GDS |
| **3** | Advanced graph algorithms, GDS and ML |
| **3+** | Agentic systems and GraphRAG |

Datasets have been selected to be real, documented and sufficiently large to support meaningful graph analysis.

---

# Level 1 — Modeling & Cypher foundations

## 1. University Course Prerequisite Planner

### Use Case

Help students plan their academic path.

### Graph Model

Possible entities:

- Courses
- Students
- Professors
- Semesters

Possible relationships:

- `REQUIRES`
- `ENROLLED_IN`
- `TEACHES`

### API Features

- Check prerequisite eligibility  
  `GET /api/students/{id}/eligibility?course_id={cid}`

- Suggest an optimal course sequence  
  `GET /api/students/{id}/plan/sequence?target={goal}`

- Find graduation paths  
  `GET /api/students/{id}/paths/graduation`

- Detect circular prerequisite dependencies  
  `GET /api/courses/prerequisites/cycles`

### Agentic component

Implement an NL-to-Cypher endpoint.

Example:

> What do I still need to take before I can enroll in Machine Learning?

### Difficulty

**1**

### Data Sources

- [University of Illinois prerequisites dataset](https://github.com/illinois/prerequisites-dataset)
- [Open University Learning Analytics Dataset — OULAD](https://www.kaggle.com/datasets/rocki37/open-university-learning-analytics-dataset)

### Points to master for the defense

You should be able to explain:

- how cycle detection works;
- the Cypher query used;
- how its cost changes as the graph grows;
- how prerequisite chains are modeled.

---

## 2. Global Flight Network Explorer

### Use Case

Model the global air-travel network and answer routing, connectivity and centrality questions.

### Graph Model

Possible entities:

- Airports
- Airlines
- Routes

Possible relationships:

- `ROUTE`
- `OPERATED_BY`

Relevant properties may include:

- distance;
- country;
- continent;
- airport codes.

### API Features

- Shortest route by number of hops  
  `GET /api/routes/shortest?from={iata_a}&to={iata_b}`

- Most central airports  
  `GET /api/airports/central?metric=degree`

- Connected components by continent  
  `GET /api/network/components?continent={c}`

- Reachability within *k* hops  
  `GET /api/airports/{iata}/reachable?hops={k}`

### Agentic component

NL-to-Cypher endpoint over the flight network.

### Difficulty

**1**

### Data Source

[OpenFlights](https://github.com/jpatokal/openflights/tree/master/data)

Use:

- `airports.dat`
- `routes.dat`

The dataset contains more than 3,000 airports and tens of thousands of routes.

### Points to master for the defense

Be prepared to explain why graph traversal is appropriate for questions such as:

> Which airports are reachable within four connections?

Compare this with the equivalent relational approach.

---

# Level 2 — Graph engineering

## 3. Supply Chain Resilience & Impact Simulator

### Use Case

Model a supply chain from manufacturers to consumers and simulate disruptions.

### Graph Model

Possible entities:

- Suppliers
- Manufacturers
- Distributors
- Retailers
- Products
- Locations

### API Features

- Product provenance  
  `GET /api/products/{sku}/provenance`

- Bottleneck detection  
  `GET /api/supply/bottlenecks?product={sku}`

- Failure-impact simulation  
  `GET /api/suppliers/{id}/impact?depth={n}`

The simulation should remove or disable a supplier and propagate the impact downstream.

Possible metrics include:

- affected SKUs;
- affected manufacturers;
- affected retailers;
- additional lead time;
- alternative suppliers.

- Delivery-time estimation  
  `GET /api/orders/{id}/eta`

### Agentic component

Create an agent that receives a disruption scenario in natural language, runs the relevant graph queries and summarizes:

- affected products;
- bottlenecks;
- possible alternatives;
- mitigation strategies.

### Difficulty

**2**

### Data Sources

- [DataCo Smart Supply Chain](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis)
- [Shipping & logistics datasets](https://github.com/austinlasseter/datasets-shipping-logistics)

### Points to master for the defense

Be prepared to explain:

- how disruption propagation works;
- how traversal depth is bounded;
- how you prevent the simulation from becoming computationally expensive.

---

## 4. Movie Recommender in Production

### Use Case

Build a production-grade recommendation service over a user/movie bipartite graph.

### Graph Model

Example:

```text
(:User)-[:RATED]->(:Movie)
(:Movie)-[:IN_GENRE]->(:Genre)
```

You must explicitly consider whether genres should be represented as:

- nodes;
- properties;
- or both.

### API Features

- Similar movies  
  `GET /api/movies/{id}/similar`

- Personalized recommendations  
  `GET /api/users/{id}/recommendations`

- Community-based discovery  
  `GET /api/users/{id}/discover`

- Popularity / centrality ranking  
  `GET /api/movies/trending`

Recommended techniques include:

- similarity algorithms;
- Louvain;
- PageRank.

### Agentic component

Implement:

- NL-to-Cypher;
- a **"Why was this recommended?"** endpoint.

The explanation should rely on actual graph paths rather than an unsupported LLM explanation.

### Difficulty

**2**

### Data Source

[MovieLens](https://grouplens.org/datasets/movielens/)

You may use:

- `ml-latest-small` during development;
- `ml-25m` for larger-scale experimentation and GDS.

### Points to master for the defense

Be prepared to justify the modeling trade-off between genres as nodes and genres as properties.

---

## 5. Fraud Ring Detection System

### Use Case

Analyze banking transaction networks to identify suspicious structures and possible fraud rings.

### Graph Model

Possible entities:

- Accounts
- Transactions
- Merchants
- Devices
- IP addresses

Possible relationships:

- `TRANSACTED_WITH`
- `USED_DEVICE`
- `SHARES_IP`

### API Features

- Suspicious transaction detection  
  `GET /api/fraud/transactions/suspicious?account_id={id}`

- Fraud-ring analysis  
  `GET /api/fraud/rings?seed_account={id}`

- Network-based risk scoring  
  `GET /api/accounts/{id}/risk`

- Unusual connection alerts  
  `GET /api/fraud/alerts?account_id={id}`

### Agentic component

Create an agent that builds an **investigation brief** for a flagged account.

It should traverse the graph and summarize relevant evidence such as:

- shared devices;
- shared IPs;
- suspicious transaction patterns;
- unusual community structures;
- high-risk neighbors.

### Difficulty

**2–3**

### Data Sources

- [Amazon Fraud Dataset Benchmark / IEEE-CIS](https://github.com/amazon-science/fraud-dataset-benchmark)
- [Sparkov simulated transactions](https://www.kaggle.com/datasets/kartik2112/fraud-detection)

### Points to master for the defense

Be prepared to discuss false positives.

For example:

- several users from the same household may share an IP;
- thousands of users may legitimately share the same merchant;
- dense graph structures do not automatically imply fraud.

---

# Level 3 — Advanced graph & GDS

## 6. Elliptic++ Bitcoin AML System

### Use Case

Build an Anti-Money Laundering analysis system over Bitcoin transaction graphs.

### Graph Model

Possible entities:

- Transactions
- Addresses / Wallets
- Entities

Entity types may include:

- Exchange
- Marketplace
- Gambling
- Mining Pool
- Mixer
- Ponzi scheme

Possible relationships:

- `INPUT_OF`
- `OUTPUT_TO`
- `OWNS`
- `ASSOCIATED_WITH`

### API Features

- Transaction risk scoring  
  `GET /api/tx/{id}/risk`

- Address risk scoring  
  `GET /api/addresses/{addr}/risk`

- Funds-flow tracing  
  `GET /api/flows?from_tx={id}&direction=forward&hops=3`

- Entity attribution  
  `GET /api/addresses/{addr}/entity`

- Investigation subgraph export  
  `GET /api/subgraph?center={id}&radius=2`

### Agentic component

The project must combine:

- a node-classification ML workflow for licit/illicit classification;
- an agent capable of explaining a flow-of-funds investigation.

### Difficulty

**3**

### Data Source

[Elliptic++](https://github.com/git-disl/EllipticPlusPlus)

The dataset contains transaction and wallet graphs together with entity information.

---

## 7. Panama Papers — Offshore Financial Network Analysis

### Use Case

Investigate beneficial ownership and offshore corporate structures.

### Graph Model

Possible entities:

- People
- Companies
- Officers
- Intermediaries
- Addresses
- Jurisdictions

### API Features

- Beneficial-ownership path tracing  
  `GET /api/entities/{id}/ownership/paths`

- Intermediary hubs and circular control  
  `GET /api/networks/intermediaries/top?limit=20`

- Red-flag queries  
  `GET /api/networks/redflags?address={addr}&max_layers={n}`

- Entity risk summary  
  `GET /api/entities/{id}/risk`

### Agentic component

Build an agent capable of answering questions such as:

> Is there a path linking person A to entity B, and through whom?

The answer must explain the chain using the graph.

### Difficulty

**3**

### Data Sources

- [ICIJ Offshore Leaks](https://offshoreleaks.icij.org/pages/database)
- [Neo4j Panama Papers example](https://github.com/neo4j-graph-examples/icij-panama-papers)
- [ICIJ OffshoreLeaks data packages](https://github.com/ICIJ/offshoreleaks-data-packages)

### Points to master for the defense

Large ownership graphs can produce expensive traversals.

Your implementation should demonstrate:

- pagination;
- depth limits;
- query limits;
- appropriate indexes;
- controlled usage of `shortestPath()` or `allShortestPaths()`.

---

# Level 3+ — Agentic / GraphRAG

These projects place the agentic component at the center of the architecture.

A recurring issue is the difference between:

- **verified structured data**;
- **LLM-extracted or LLM-suggested relationships**.

Your application must make this distinction explicit.

Possible mechanisms include:

- confidence values;
- provenance;
- source references;
- relation status;
- validation pipelines;
- visual distinction between facts and hypotheses.

---

## 8. Document-to-Graph GraphRAG Assistant

### Use Case

Transform a document corpus into a queryable knowledge graph.

### Graph Model

Possible entities:

- Documents
- Chunks
- Entities
- Topics
- Relations

Possible relationships:

- `MENTIONS`
- `RELATED_TO`
- `PART_OF`
- `NEXT`

Some nodes and relationships will be extracted using an LLM.

### API Features

- Document ingestion and extraction  
  `POST /api/corpus/import`

- Hybrid retrieval  
  `GET /api/ask?q={question}`

- Related-concept exploration  
  `GET /api/topics/{id}/graph?depth=2`

- Answer with graph-path citations

The response should expose the graph traversal or sources used to construct the answer.

### Agentic component

The project itself is a GraphRAG system.

Build a LangGraph workflow combining:

- vector search;
- Cypher traversal;
- structured tool calls;
- response generation.

### Difficulty

**3+**

### Data Sources

You may select a free document corpus such as:

- Wikipedia;
- technical documentation;
- scientific publications;
- press articles;
- public reports.

Reference architectures:

- [LangChain Neo4j RAG App](https://github.com/hfhoffman1144/langchain_neo4j_rag_app)
- [Neo4j Labs — LangGraph integration](https://neo4j.com/labs/genai-ecosystem/genai-frameworks/langgraph/)

These repositories may be studied as architectural references, but your implementation and modeling decisions must remain your own.

### Points to master for the defense

Explain:

- how entities are extracted;
- how relationships are validated;
- how confidence is represented;
- how hallucinated edges are avoided or detected.

---

## 9. Biomedical Drug-Repurposing Agent — Hetionet

### Use Case

Reason over a biomedical knowledge graph to identify potential drug–disease relationships.

### Graph Model

Hetionet contains entities such as:

- Genes
- Diseases
- Compounds

and multiple biomedical relationship types.

### API Features

- NL-to-Cypher  
  `GET /api/ask?q={question}`

- Multi-hop reasoning  
  `GET /api/repurpose?disease={id}`

- Path explanation  
  `GET /api/paths/explain?from={cid}&to={did}`

Example question:

> Which compounds might treat disease X through gene Y?

### Agentic component

Build a LangGraph agent combining:

- text-to-Cypher;
- graph traversal;
- metapath reasoning;
- path explanation.

### Difficulty

**3+**

### Data Source

[Hetionet](https://github.com/hetio/hetionet)

It contains approximately:

- 47,000 nodes;
- more than 2 million relationships.

Public demo:

[neo4j.het.io](https://neo4j.het.io)

### Points to master for the defense

You must understand the concept of a **metapath**.

A graph-derived drug–disease connection must be presented as a hypothesis when appropriate, not automatically as a scientific fact.

---

## 10. Geopolitical Event ↔ Market Correlation Agent

### Use Case

Analyze relationships between geopolitical/economic events and market movements.

Examples:

- disruption in the Strait of Hormuz → oil and currencies;
- tensions around Taiwan → semiconductor stocks;
- central-bank announcements → FX or bond markets.

The graph acts as a traceable structured memory between events and market data.

### Graph Model

Example:

```text
(:Event)-[:OCCURRED_IN]->(:Country)
(:Event)-[:MENTIONS]->(:Commodity)
(:Event)-[:MENTIONS]->(:Currency)
(:PriceSeries)-[:PRICE_ON]->(:TradingDay)
```

Possible analytical relationships:

- `CORRELATES_WITH`
- `PRECEDES`

### API Features

- Import events  
  `POST /api/events/import`

- Synchronize market series  
  `POST /api/market/sync`

- Event/market correlation analysis  
  `GET /api/correlation/event-market?entity={eur_usd}`

- Explain recent asset movement  
  `GET /api/explain/move?asset={ticker}&window={d}`

- Asset event timeline  
  `GET /api/timeline/{asset}`

### Agentic component

Build a LangGraph agent capable of traversing:

```text
event → theme/entity → market series
```

The agent may **propose possible relationships**, but must never present temporal correlation alone as proof of causation.

### Difficulty

**3+**

### Data Sources

- [GDELT](https://www.gdeltproject.org/)
- [FRED](https://fred.stlouisfed.org/docs/api/fred/)
- [`fredapi`](https://github.com/mortada/fredapi)
- [`yfinance`](https://github.com/ranaroussi/yfinance)

### Important requirement

**Correlation ≠ causation.**

Your application must explicitly prevent the agent from presenting a simple temporal correlation as a proven causal relationship.

This project is for **educational and analytical purposes only** and must not execute financial orders.

Include this disclaimer in your README.

---

## 11. Corporate Ownership & Supply-Chain Exposure Agent

### Use Case

Map:

- companies;
- institutional shareholders;
- subsidiaries;
- sectors;
- supply-chain relationships.

Example question:

> What is my portfolio's indirect exposure to Taiwanese semiconductors?

### Graph Model

Possible entities:

- Companies
- Institutions
- Holdings
- Sectors
- Subsidiaries

Possible relationships:

- `OWNS_STAKE`
- `SUBSIDIARY_OF`
- `IN_SECTOR`
- `SUPPLIES`

### API Features

- Common shareholders  
  `GET /api/companies/common-holders?a={cik_a}&b={cik_b}`

- Indirect sector exposure  
  `GET /api/portfolio/exposure?sector={s}`

- Ownership path tracing  
  `GET /api/entities/{id}/ownership/paths`

### Agentic component

Build an agent capable of answering portfolio and exposure questions in natural language by traversing the ownership graph.

### Difficulty

**3+**

### Data Sources

- [SEC EDGAR Form 13F datasets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)
- [stock-relation reference architecture](https://github.com/supat-roong/stock-relation)
- [Neo4j SEC EDGAR notebooks](https://github.com/neo4j-examples/sec-edgar-notebooks)
- [Neo4j + Google agent lab](https://github.com/neo4j-partners/hands-on-lab-neo4j-and-google)

### Points to master for the defense

Entity resolution is an important part of this project.

For example:

- 13F datasets use **CUSIP** identifiers;
- SEC corporate filings use **CIK** identifiers.

You must document how your application reconciles identifiers from different datasets.

---

# Propose your own project

You may propose your own project instead of choosing one from the list.

The project must have a comparable scope and level of difficulty.

Your proposal must include:

- a graph representation of the architecture;
- an ER diagram when starting from relational data;
- a `docker-compose.yml` orchestrating at least **three services**;
- a FastAPI API;
- a heterogeneous dataset or at least two distinct data sources/constraints;
- an NL-to-Cypher component at minimum;
- a genuine agent for Level 3+ projects;
- automated tests;
- comprehensive documentation;
- a modeling rationale;
- an anti-genericity appendix;
- a dedicated Python virtual environment;
- object-oriented design where it improves clarity or reuse;
- adherence to the [required pylint rules](https://gist.github.com/bdallard/f74fe36835b6f0510e8d30bc7ee05023).

---

# Common Technical Stack

```yaml
Stack:
  - Neo4j 5.x
  - Python 3.11+
  - FastAPI
  - Docker
  - Neo4j Python Driver
  - Pydantic
  - pytest
  - LangGraph / LangChain
  - LLM provider or local LLM
```

## GitHub Workflow

Each team must use:

- `main` as the stable branch;
- feature branches for development;
- Pull Requests for merging work;
- code review;
- GitHub Actions for linting and testing.

The team lead is responsible for coordinating merges and code-review assignments.

---

## LLM providers and API keys

Never commit API keys or credentials.

Use:

```text
.env
```

for local credentials and provide:

```text
.env.example
```

in the repository.

`.env` must be included in `.gitignore`.

Using a local model through **Ollama** is acceptable and can satisfy the LLM requirement without requiring a paid API.

---

# Suggested Project Structure 🥸

```text
project-name/
├── docker-compose.yml
├── .env.example
├── README.md
├── Makefile
├── app/
│   ├── main.py
│   ├── models/
│   ├── routers/
│   ├── services/
│   ├── agent/
│   │   ├── graph.py
│   │   ├── tools.py
│   │   └── guardrails.py
│   └── database/
├── tests/
├── scripts/
│   └── seed_data.py
├── demo.ipynb
└── requirements.txt
```

The exact structure may vary if you can justify another architecture.

---

# Minimal Makefile template

Use this template as a starting point and adapt commands and paths to your project.

If you are new to `make`, see:

[Makefile tutorial](https://courses.dallard.tech/linux/makefile/) 🤓

```makefile
.PHONY: help run docker-build docker-run test clean venv install lint format tree

TAG ?= graph-api:dev

help:
	@echo "Commands:"
	@echo "  make venv           Create local virtualenv (.venv)"
	@echo "  make install        Install requirements into .venv"
	@echo "  make run            Run FastAPI (uvicorn) on :8000"
	@echo "  make docker-build   Build Docker image (TAG=$(TAG))"
	@echo "  make docker-run     Start the Docker Compose stack"
	@echo "  make test           Run pytest suite"
	@echo "  make lint           Run pylint"
	@echo "  make format         Run black code formatter"
	@echo "  make clean          Remove caches and temp files"
	@echo "  make tree           Show project tree (depth 3)"

venv:
	@if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
		. .venv/bin/activate && pip install --upgrade pip; \
		echo "Created .venv"; \
	else echo ".venv already exists"; fi
	@echo "To activate: source .venv/bin/activate"

install: venv
	@. .venv/bin/activate && pip install -r requirements.txt

run:
	@. .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker compose build

docker-run:
	docker compose up --build

test:
	@. .venv/bin/activate && pytest -q --cov=app --cov-report=term-missing

lint:
	@. .venv/bin/activate && pylint app

format:
	@. .venv/bin/activate && black app -l 120

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} \; || true
	find . -type f -name "*.pyc" -delete || true

tree:
	@if command -v tree >/dev/null 2>&1; then \
		tree -L 3 -I "node_modules|dist|.git|.venv|__pycache__"; \
	else find . -maxdepth 3 -type d -not -path '*/\.*' | sort; fi
```

---

# Implementation Tips

A recommended workflow is:

1. **Download and explore the dataset.**

   Understand its structure before designing the graph.

2. **Design the graph model.**

   Identify:

   - nodes;
   - relationships;
   - directions;
   - properties;
   - constraints;
   - indexes.

   Document the modeling alternatives you rejected.

3. **Create data-import scripts.**

   Use the Neo4j Python Driver and efficient bulk-import techniques.

4. **Build the FastAPI endpoints.**

   Include CRUD operations where relevant, but focus mainly on meaningful graph queries.

5. **Implement the agentic component early.**

   Do not add NL-to-Cypher or LangGraph only at the end of the project.

   Guardrails should be designed from the beginning.

6. **Dockerize the application.**

   Neo4j, FastAPI and supporting services must run through Docker Compose.

7. **Benchmark and optimize your queries.**

   Use:

   ```cypher
   EXPLAIN
   ```

   and:

   ```cypher
   PROFILE
   ```

   Capture before/after results when adding indexes or rewriting queries.

---

# Project Evaluation Criteria

The project is graded out of **100 points**.

---

## Core Technical Components — 25 points

### Docker Infrastructure & Services — 9 pts

- **[2]** Functional `docker-compose.yml` with at least 3 services
- **[2]** Proper `Dockerfile` per custom service or correctly configured official image
- **[2]** Environment variables managed through `.env.example`; no hardcoded secrets
- **[2]** At least one image pushed to a public registry, with link in README
- **[1]** Project starts cleanly using Docker Compose

### Neo4j Graph Database — 10 pts

- **[3]** Graph schema with at least 3 node labels, 3 relationship types and meaningful properties
- **[2]** At least 2 relevant constraints
- **[2]** Appropriate indexes for frequent queries
- **[2]** Data-ingestion script using the selected dataset
- **[1]** Dataset source documented and justified

### FastAPI — 6 pts

- **[2]** At least 4 endpoints covering the main use cases, including at least 3 advanced graph queries
- **[2]** Pydantic models for input/output validation
- **[1]** Functional Swagger/OpenAPI documentation at `/docs`
- **[1]** Proper error handling with meaningful HTTP codes and messages

---

# Advanced Neo4j & Agentic — 27 points

## Advanced Cypher — 9 pts

- **[4]** Pathfinding or graph algorithms in at least 2 endpoints
- **[3]** Complex graph-pattern matching
- **[2]** Analytical queries using techniques such as:
  - `WITH`
  - `UNWIND`
  - subqueries
  - aggregations

## Optimization & Performance — 5 pts

- **[5]** Optimized queries demonstrating appropriate use of:
  - `LIMIT`;
  - parameterized queries;
  - subqueries;
  - indexes;
  - pagination;
  - avoidance of Cartesian products;
  - before/after benchmarks or latency measurements.

## Graph Data Science & Agentic — 13 pts

- **[2]** GDS in-memory projection and at least 2 graph algorithms
- **[3]** ML workflow predicting links or classifying nodes
- **[4]** LangGraph / GraphRAG or NL-to-Cypher component with tool use, prompting and structured response handling
- **[4]** LLM reliability mechanisms:
  - guardrails;
  - generated Cypher validation;
  - confidence or validation mechanisms;
  - distinction between verified facts and AI-generated suggestions;
  - brief evaluation of the component.

---

# Architecture, Documentation & Clean Code — 16 points

## Schemas & Modeling — 7 pts

- **[2]** Neo4j graph-schema diagram
- **[2]** System-architecture diagram showing services, ports and data flows
- **[3]** Modeling rationale and anti-genericity appendix

## Documentation — 5 pts

- **[3]** Complete root `README.md`
- **[2]** `demo.ipynb` containing graph exploration and visualizations

## Clean Code & Linting — 4 pts

- **[2]** `.pylintrc` present, pylint score ≥ 9.5/10, functional `make lint`
- **[1]** PEP 8 compliance and clean project structure
- **[1]** Docstrings throughout the codebase

---

# Makefile & Automation — 3 points

- **[1]** Makefile containing the main project commands
- **[1]** Commands are functional and `make help` is clear
- **[1]** Makefile usage documented in README

Expected commands include:

```text
make help
make install
make run
make docker-run
make test
make lint
make clean
```

---

# Tests & Quality — 10 points

- **[3]** Pytest suite covering unit tests, API tests and Neo4j connectivity
- **[2]** Container health tests for Neo4j and FastAPI
- **[2]** Cypher query tests runnable through `make test`
- **[2]** Test coverage ≥ 60%
- **[1]** All tests pass and a coverage report is generated

---

# Software Engineering Best Practices — 9 points

- **[1]** Lint workflow running on push or Pull Request
- **[1]** Test workflow with coverage
- **[1]** Build/test/coverage badges in README
- **[1]** Documented code reviews with at least 2 constructive comments per PR
- **[3]** Reverse proxy such as Nginx/Traefik **or** authentication on a sensitive endpoint
- **[2]** Strategic index usage demonstrated with `EXPLAIN` or `PROFILE`

---

# Collaboration & Git Management — 10 points

- **[2]** At least 2 active branches and feature branches used by team members
- **[1]** Proper `.gitignore`
- **[3]** Reasonably balanced commit distribution
- **[3]** At least one substantial merged Pull Request per member
- **[1]** Clear commit messages

Recommended commit prefixes:

```text
feat:
fix:
test:
docs:
refactor:
chore:
```

---

# Scoring Summary

| Section | Points |
| --- | ---: |
| Core Technical Components | 25 |
| Advanced Neo4j & Agentic | 27 |
| Architecture, Documentation & Clean Code | 16 |
| Makefile & Automation | 3 |
| Tests & Quality | 10 |
| Software Engineering Best Practices | 9 |
| Collaboration & Git Management | 10 |
| **Total** | **100** |

---

# Project Evaluation Checklist

| Category | Criterion | Points | ✅ | 💬 |
| --- | --- | ---: | :--: | --- |
| **Docker Infra & Services** | `docker-compose.yml` with ≥3 services | 2 | [ ] | |
| | Proper `Dockerfile` / official image | 2 | [ ] | |
| | `.env.example`, no secrets committed | 2 | [ ] | |
| | ≥1 image on public registry | 2 | [ ] | |
| | Docker Compose starts cleanly | 1 | [ ] | |
| **Neo4j Database** | Schema: ≥3 labels, ≥3 relation types | 3 | [ ] | |
| | ≥2 constraints | 2 | [ ] | |
| | Appropriate indexes | 2 | [ ] | |
| | Dataset ingestion script | 2 | [ ] | |
| | Dataset source documented | 1 | [ ] | |
| **FastAPI** | ≥4 endpoints, ≥3 advanced graph queries | 2 | [ ] | |
| | Pydantic validation | 2 | [ ] | |
| | Swagger `/docs` works | 1 | [ ] | |
| | Proper error handling | 1 | [ ] | |
| **Advanced Cypher** | Pathfinding/GDS in ≥2 endpoints | 4 | [ ] | |
| | Complex pattern matching | 3 | [ ] | |
| | `WITH`, `UNWIND`, subqueries, aggregations | 2 | [ ] | |
| **Optimization** | Optimized queries + benchmarks | 5 | [ ] | |
| **GDS & Agentic** | GDS projection + ≥2 algorithms | 2 | [ ] | |
| | ML prediction/classification workflow | 3 | [ ] | |
| | LangGraph / GraphRAG / NL-to-Cypher | 4 | [ ] | |
| | LLM reliability and guardrails | 4 | [ ] | |
| **Schemas & Modeling** | Neo4j graph diagram | 2 | [ ] | |
| | System architecture diagram | 2 | [ ] | |
| | Modeling rationale + anti-genericity appendix | 3 | [ ] | |
| **Documentation** | Complete README + screenshots | 3 | [ ] | |
| | Demonstration notebook | 2 | [ ] | |
| **Clean Code** | `.pylintrc`, pylint ≥9.5, `make lint` | 2 | [ ] | |
| | PEP 8 + clean architecture | 1 | [ ] | |
| | Docstrings | 1 | [ ] | |
| **Makefile** | Required commands | 1 | [ ] | |
| | Commands functional | 1 | [ ] | |
| | Usage documented | 1 | [ ] | |
| **Tests** | Unit/API/Neo4j tests | 3 | [ ] | |
| | Container health checks | 2 | [ ] | |
| | Cypher tests | 2 | [ ] | |
| | Coverage ≥60% | 2 | [ ] | |
| | All tests pass | 1 | [ ] | |
| **SE Best Practices** | Lint workflow | 1 | [ ] | |
| | Test workflow | 1 | [ ] | |
| | README badges | 1 | [ ] | |
| | Code reviews | 1 | [ ] | |
| | Reverse proxy or authentication | 3 | [ ] | |
| | `EXPLAIN` / `PROFILE` demonstration | 2 | [ ] | |
| **Git** | Branch workflow | 2 | [ ] | |
| | Proper `.gitignore` | 1 | [ ] | |
| | Balanced contributions | 3 | [ ] | |
| | ≥1 substantial merged PR/member | 3 | [ ] | |
| | Clear commit messages | 1 | [ ] | |

---

# Expected Deliverables

## In your GitHub repository

1. Complete source code
2. Functional `docker-compose.yml`
3. Documented `Makefile`
4. `.pylintrc`
5. Comprehensive `README.md`
6. Neo4j graph-schema diagram
7. Modeling rationale and anti-genericity appendix
8. `demo.ipynb`
9. Automated test suite
10. Swagger/OpenAPI documentation
11. Screenshots or links to merged Pull Requests
12. Functional NL-to-Cypher or LangGraph/GraphRAG component
13. Documentation of the LLM guardrails

---

# Live Demonstration

During the project demonstration, your team must be able to run:

```bash
make help
make lint
make test
make docker-run
```

You must also demonstrate:

- the application running successfully;
- Neo4j connectivity;
- FastAPI endpoints;
- Swagger;
- Docker images;
- contribution history;
- merged Pull Requests;
- the agentic component.

For the LLM component, demonstrate at least:

1. one successful request;
2. one case where a guardrail detects or rejects an invalid LLM output.

---

# Git Contribution Verification

Useful commands:

```bash
git shortlog -sn
git log --author="name" --oneline | wc -l
git log --format='%aN' | sort | uniq -c | sort -rn
```

GitHub also provides:

```text
Insights → Contributors
```

Example of an acceptable distribution for 100 commits:

```text
30 / 27 / 25 / 18
```

Example of a strongly unbalanced distribution:

```text
55 / 25 / 15 / 5
```

Commit count is not the only measure of contribution. The quality and substance of the work will also be considered.

---

# Important Notes

⚠️ **Non-functional Makefile**

Broken required commands may result in a **−3 point penalty**.

---

⚠️ **Pylint requirement**

Missing `.pylintrc` or a pylint score below **9.5/10** may result in a **−8 point penalty**.

---

⚠️ **Non-functional project**

If the project cannot start or the main endpoints do not function, a penalty of up to **−25 points** may be applied.

---

⚠️ **Missing agentic component**

A project without a functional NL-to-Cypher, LangGraph or GraphRAG component may receive a **−15 point penalty**.

The agentic component is a core project requirement.

---

⚠️ **Generic and undefended graph schema**

A graph schema copied directly from a generic AI-generated solution without modeling justification may receive a penalty of up to **−5 points**.

You must be able to defend your own graph-modeling decisions.

---

⚠️ **Unequal contribution**

Possible penalties include:

- contribution below 10%: **−5 points**;
- no substantial merged PR: **−3 points per member**;
- cosmetic-only commits: individual re-evaluation.

---

⚠️ **Plagiarism**

Detected plagiarism may result in:

**0/100 for the group and an administrative report.**

Using an AI assistant is not considered plagiarism by itself.

However, every student remains responsible for understanding and being able to explain the code and architecture submitted by the team.

---

⚠️ **Exposed credentials**

Committed API keys, passwords, `.env` files or other secrets may result in:

**−5 points per exposed secret or credential file.**

Use `.env.example` and environment variables instead.

---

✨ **Teamwork**

The project lead is responsible for maintaining:

- a healthy PR workflow;
- meaningful code reviews;
- organized branches;
- reasonably balanced work distribution.

---

# Example README Section — Team Contributions

```markdown
## 👥 Team Contributions

| Member  | Commits | Percentage | Pull Requests |
|---------|---------|------------|---------------|
| Alice   | 32      | 28%        | 4 merged      |
| Bob     | 30      | 26%        | 3 merged      |
| Charlie | 28      | 25%        | 3 merged      |
| Diana   | 24      | 21%        | 2 merged      |

**Total:** 114 commits

### Role Distribution

- **Alice:** Neo4j architecture, graph modeling, ingestion scripts
- **Bob:** FastAPI backend, endpoints, OpenAPI documentation
- **Charlie:** Pytest suite, Docker, Makefile
- **Diana:** LangGraph agent and guardrails
```

---

# Appendix — Required `.pylintrc` template

Source: gist `bdallard/f74fe36835b6f0510e8d30bc7ee05023`, revision `b72566f5`.

```ini
[MASTER]
# A comma-separated list of package or module names from where C extensions may
# be loaded. Extensions are loading into the active Python interpreter and may
# run arbitrary code.
extension-pkg-whitelist=

# Add files or directories to the blacklist. They should be base names, not
# paths.
ignore=CVS,LiLt, MPLT,pb_interfaces

# Add files or directories matching the regex patterns to the blacklist. The
# regex matches against base names, not paths.
ignore-patterns=

# Python code to execute, usually for sys.path manipulation such as
# pygtk.require().
# init-hook=

# Use multiple processes to speed up Pylint. Specifying 0 will auto-detect the
# number of processors available to use.
jobs=0

# Control the amount of potential inferred values when inferring a single
# object. This can help the performance when dealing with large functions or
# complex, nested conditions.
limit-inference-results=100

# List of plugins (as comma separated values of python module names) to load,
# usually to register additional checkers.
load-plugins=

# Pickle collected data for later comparisons.
persistent=yes

# Specify a configuration file.
#rcfile=

# When enabled, pylint would attempt to guess common misconfiguration and emit
# user-friendly hints instead of false-positive error messages.
suggestion-mode=yes

# Allow loading of arbitrary C extensions. Extensions are imported into the
# active Python interpreter and may run arbitrary code.
unsafe-load-any-extension=no


[MESSAGES CONTROL]

# Only show warnings with the listed confidence levels. Leave empty to show
# all. Valid levels: HIGH, INFERENCE, INFERENCE_FAILURE, UNDEFINED.
confidence=

# Disable the message, report, category or checker with the given id(s). You
# can either give multiple identifiers separated by comma (,) or put this
# option multiple times (only on the command line, not in the configuration
# file where it should appear only once). You can also use "--disable=all" to
# disable everything first and then reenable specific checks. For example, if
# you want to run only the similarities checker, you can use "--disable=all
# --enable=similarities". If you want to run only the classes checker, but have
# no Warning level messages displayed, use "--disable=all --enable=classes
# --disable=W".
disable=missing-module-docstring,
        missing-class-docstring,
        missing-function-docstring,
        too-few-public-methods,
        logging-fstring-interpolation,
        duplicate-code,
        no-member,
        cell-var-from-loop,
        undefined-loop-variable,
        attribute-defined-outside-init,
        protected-access,
        wrong-import-order,

# Enable the message, report, category or checker with the given id(s). You can
# either give multiple identifier separated by comma (,) or put this option
# multiple time (only on the command line, not in the configuration file where
# it should appear only once). See also the "--disable" option for examples.
enable=c-extension-no-member, useless-suppression


[REPORTS]

# Python expression which should return a score less than or equal to 10. You
# have access to the variables 'error', 'warning', 'refactor', and 'convention'
# which contain the number of messages in each category, as well as 'statement'
# which is the total number of statements analyzed. This score is used by the
# global evaluation report (RP0004).
evaluation=10.0 - ((float(5 * error + warning + refactor + convention) / statement) * 10)

# Template used to display messages. This is a python new-style format string
# used to format the message information. See doc for all details.
#msg-template=

# Set the output format. Available formats are text, parseable, colorized, json
# and msvs (visual studio). You can also give a reporter class, e.g.
# mypackage.mymodule.MyReporterClass.
output-format=colorized

# Tells whether to display a full report or only the messages.
reports=yes

# Activate the evaluation score.
score=yes


[REFACTORING]

# Maximum number of nested blocks for function / method body
max-nested-blocks=5

# Complete name of functions that never returns. When checking for
# inconsistent-return-statements if a never returning function is called then
# it will be considered as an explicit return statement and no message will be
# printed.
never-returning-functions=sys.exit


[LOGGING]

# Format style used to check logging format string. `old` means using %
# formatting, `new` is for `{}` formatting,and `fstr` is for f-strings.
logging-format-style=new

# Logging modules to check that the string format arguments are in logging
# function parameter format.
logging-modules=logging


[SPELLING]

# Limits count of emitted suggestions for spelling mistakes.
max-spelling-suggestions=4

# Spelling dictionary name. Available dictionaries: none. To make it work,
# install the python-enchant package.
spelling-dict=

# Listc of comma separated words that should not be checked.
spelling-ignore-words=

# A path to a file that contains the private dictionary; one word per line.
spelling-private-dict-file=

# Tells whether to store unknown words to the private dictionary (see the
# --spelling-private-dict-file option) instead of raising a message.
spelling-store-unknown-words=no


[MISCELLANEOUS]

# List of note tags to take in consideration, separated by a comma.
notes=FIXME,
      XXX,
      TODO


[TYPECHECK]

# List of decorators that produce context managers, such as
# contextlib.contextmanager. Add to this list to register other decorators that
# produce valid context managers.
contextmanager-decorators=contextlib.contextmanager

# List of members which are set dynamically and missed by pylint inference
# system, and so shouldn't trigger E1101 when accessed. Python regular
# expressions are accepted.
generated-members=

# Tells whether missing members accessed in mixin class should be ignored. A
# mixin class is detected if its name ends with "mixin" (case insensitive).
ignore-mixin-members=yes

# Tells whether to warn about missing members when the owner of the attribute
# is inferred to be None.
ignore-none=yes

# This flag controls whether pylint should warn about no-member and similar
# checks whenever an opaque object is returned when inferring. The inference
# can return multiple potential results while evaluating a Python object, but
# some branches might not be evaluated, which results in partial inference. In
# that case, it might be useful to still emit no-member and other checks for
# the rest of the inferred objects.
ignore-on-opaque-inference=yes

# List of class names for which member attributes should not be checked (useful
# for classes with dynamically set attributes). This supports the use of
# qualified names.
ignored-classes=optparse.Values,thread._local,_thread._local

# List of module names for which member attributes should not be checked
# (useful for modules/projects where namespaces are manipulated during runtime
# and thus existing member attributes cannot be deduced by static analysis). It
# supports qualified module names, as well as Unix pattern matching.
ignored-modules=pipeline_core.pb_interfaces




# Show a hint with possible names when a member name was not found. The aspect
# of finding the hint is based on edit distance.
missing-member-hint=yes

# The minimum edit distance a name should have in order to be considered a
# similar match for a missing member name.
missing-member-hint-distance=1

# The total number of similar names that should be taken in consideration when
# showing a hint for a missing member.
missing-member-max-choices=1

# List of decorators that change the signature of a decorated function.
signature-mutators=


[VARIABLES]

# List of additional names supposed to be defined in builtins. Remember that
# you should avoid defining new builtins when possible.
additional-builtins=

# Tells whether unused global variables should be treated as a violation.
allow-global-unused-variables=yes

# List of strings which can identify a callback function by name. A callback
# name must start or end with one of those strings.
callbacks=cb_,
          _cb

# A regular expression matching the name of dummy variables (i.e. expected to
# not be used).
dummy-variables-rgx=_+$|(_[a-zA-Z0-9_]*[a-zA-Z0-9]+?$)|dummy|^ignored_|^unused_

# Argument names that match this expression will be ignored. Default to name
# with leading underscore.
ignored-argument-names=_.*|^ignored_|^unused_

# Tells whether we should check for unused import in __init__ files.
init-import=no

# List of qualified module names which can have objects that can redefine
# builtins.
redefining-builtins-modules=six.moves,past.builtins,future.builtins,builtins,io



[FORMAT]

# Expected format of line ending, e.g. empty (any line ending), LF or CRLF.
expected-line-ending-format=LF

# Regexp for a line that is allowed to be longer than the limit.
ignore-long-lines=^\s*(# )?<?https?://\S+>?$

# Number of spaces of indent required inside a hanging or continued line.
indent-after-paren=4

# String used as indentation unit. This is usually "    " (4 spaces) or "\t" (1
# tab).
indent-string='    '

# Maximum number of characters on a single line.
max-line-length=120

# Maximum number of lines in a module.
max-module-lines=1000

# Allow the body of a class to be on the same line as the declaration if body
# contains single statement.
single-line-class-stmt=no

# Allow the body of an if to be on the same line as the test if there is no
# else.
single-line-if-stmt=no


[SIMILARITIES]

# Ignore comments when computing similarities.
ignore-comments=yes

# Ignore docstrings when computing similarities.
ignore-docstrings=yes

# Ignore imports when computing similarities.
ignore-imports=yes

# Minimum lines number of a similarity.
min-similarity-lines=4


[BASIC]

# Naming style matching correct argument names.
argument-naming-style=snake_case

# Regular expression matching correct argument names. Overrides argument-
# naming-style.
#argument-rgx=

# Naming style matching correct attribute names.
# attr-naming-style=snake_case,camelCase

# Regular expression matching correct attribute names. Overrides attr-naming-
# style.
attr-rgx=(([a-z][a-z0-9_]{2,30})|(_[a-z0-9_]*)|(id))$

# Bad variable names which should always be refused, separated by a comma.
bad-names=foo,
          bar,
          baz,
          toto,
          tutu,
          tata

# Naming style matching correct class attribute names.
# class-attribute-naming-style=snake_case,camelCase

# Regular expression matching correct class attribute names. Overrides class-
# attribute-naming-style.
class-attribute-rgx=([A-Za-z_][A-Za-z0-9_]{2,30}|(__.*__)|(id))$

# Naming style matching correct class names.
class-naming-style=PascalCase

# Regular expression matching correct class names. Overrides class-naming-
# style.
#class-rgx=

# Naming style matching correct constant names.
const-naming-style=UPPER_CASE

# Regular expression matching correct constant names. Overrides const-naming-
# style.
#const-rgx=

# Minimum line length for functions/classes that require docstrings, shorter
# ones are exempt.
docstring-min-length=-1

# Naming style matching correct function names.
function-naming-style=snake_case

# Regular expression matching correct function names. Overrides function-
# naming-style.
#function-rgx=

# Good variable names which should always be accepted, separated by a comma.
good-names=i,
           j,
           k,
           ex,
           Run,
           x,
           y,
           x0, x1, y0, y1, w, h,
           k,
           v,
           df,
           _

# Include a hint for the correct naming format with invalid-name.
include-naming-hint=no

# Naming style matching correct inline iteration names.
inlinevar-naming-style=snake_case

# Regular expression matching correct inline iteration names. Overrides
# inlinevar-naming-style.
#inlinevar-rgx=

# Naming style matching correct method names.
method-naming-style=snake_case

# Regular expression matching correct method names. Overrides method-naming-
# style.
#method-rgx=

# Naming style matching correct module names.
module-naming-style=snake_case

# Regular expression matching correct module names. Overrides module-naming-
# style.
#module-rgx=

# Colon-delimited sets of names that determine each other's naming style when
# the name regexes allow several styles.
name-group=

# Regular expression which should only match function or class names that do
# not require a docstring.
no-docstring-rgx=^_

# List of decorators that produce properties, such as abc.abstractproperty. Add
# to this list to register other decorators that produce valid properties.
# These decorators are taken in consideration only for invalid-name.
property-classes=abc.abstractproperty

# Naming style matching correct variable names.
variable-naming-style=snake_case

# Regular expression matching correct variable names. Overrides variable-
# naming-style.
#variable-rgx=


[STRING]

# This flag controls whether the implicit-str-concat-in-sequence should
# generate a warning on implicit string concatenation in sequences defined over
# several lines.
check-str-concat-over-line-jumps=yes


[IMPORTS]

# List of modules that can be imported at any level, not just the top level
# one.
allow-any-import-level=tensorflow, keras

# Allow wildcard imports from modules that define __all__.
allow-wildcard-with-all=no

# Analyse import fallback blocks. This can be used to support both Python 2 and
# 3 compatible code, which means that the block might have code that exists
# only in one or another interpreter, leading to false positives when analysed.
analyse-fallback-blocks=no

# Deprecated modules which should not be used, separated by a comma.
deprecated-modules=optparse,tkinter.tix

# Create a graph of external dependencies in the given file (report RP0402 must
# not be disabled).
ext-import-graph=

# Create a graph of every (i.e. internal and external) dependencies in the
# given file (report RP0402 must not be disabled).
import-graph=

# Create a graph of internal dependencies in the given file (report RP0402 must
# not be disabled).
int-import-graph=

# Force import order to recognize a module as part of the standard
# compatibility libraries.
known-standard-library=

# Force import order to recognize a module as part of a third party library.
known-third-party=enchant

# Couples of modules and preferred modules, separated by a comma.
preferred-modules=

[CLASSES]

# List of method names used to declare (i.e. assign) instance attributes.
defining-attr-methods=__init__,
                      __new__,
                      setUp,
                      __post_init__

# List of member names, which should be excluded from the protected access
# warning.
exclude-protected=_asdict,
                  _fields,
                  _replace,
                  _source,
                  _make

# List of valid names for the first argument in a class method.
valid-classmethod-first-arg=cls

# List of valid names for the first argument in a metaclass class method.
valid-metaclass-classmethod-first-arg=cls


[DESIGN]

# Maximum number of arguments for function / method.
max-args=5

# Maximum number of attributes for a class (see R0902).
max-attributes=10

# Maximum number of boolean expressions in an if statement (see R0916).
max-bool-expr=5

# Maximum number of branch for function / method body.
max-branches=12

# Maximum number of locals for function / method body.
max-locals=15

# Maximum number of parents for a class (see R0901).
max-parents=7

# Maximum number of public methods for a class (see R0904).
max-public-methods=20

# Maximum number of return / yield for function / method body.
max-returns=6

# Maximum number of statements in function / method body.
max-statements=50

# Minimum number of public methods for a class (see R0903).
min-public-methods=1
```
