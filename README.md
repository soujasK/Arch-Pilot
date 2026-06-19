# ArchPilot

**Repository Architecture Intelligence Platform**

ArchPilot answers the questions your IDE can't:

> *What breaks if I change this file? Which modules are most critical? Where are my circular dependencies? What's the safest migration order?*

It fetches any public GitHub repository, extracts its dependency graph using AST/regex parsing, runs graph algorithms to find architectural risks, and surfaces AI-generated explanations grounded in deterministic analysis — not hallucinations.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                         ArchPilot                              │
│                                                                │
│  GitHub URL ──► Repository Parser ──► Dependency Extractor    │
│                                              │                 │
│                                       Adjacency List           │
│                                              │                 │
│              ┌───────────────────────────────┤                 │
│              │       Graph Algorithms        │                 │
│              │  DFS · BFS · Tarjan SCC       │                 │
│              │  Cycle Detection · PageRank   │                 │
│              │  Topological Sort             │                 │
│              └───────────────┬───────────────┘                 │
│                              │                                 │
│                   Architecture Analysis                        │
│               Health Score · Risk Detection                    │
│               Hotspot ID · Decomposition                       │
│                              │                                 │
│                         AI Layer                               │
│            (consumes structured results, not code)             │
│                              │                                 │
│                    React Dashboard                             │
│         Graph Viz · Impact Analysis · Chat                     │
└────────────────────────────────────────────────────────────────┘
```

**Key design decision:** AI receives structured analysis output — dependency graphs, SCC results, risk scores — never raw source code. This prevents hallucination and keeps explanations auditable.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI 0.111 + Python 3.12 |
| ORM | SQLAlchemy 2.0 async |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Migrations | Alembic |
| Graph Algorithms | Pure Python (no networkx) |
| HTTP Client | httpx (async) |
| Frontend | React 18 + TypeScript |
| Graph Visualization | React Flow 11 |
| State / Fetching | TanStack Query v5 |
| Styling | TailwindCSS 3 |
| Containerization | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio |

---

## Graph Algorithms

All algorithms operate on pure `dict[str, list[str]]` adjacency lists — no ORM dependency, fully unit-testable.

| Algorithm | Implementation | Use Case |
|---|---|---|
| DFS | Iterative (stack) | Impact analysis — "what breaks?" |
| BFS | Iterative (queue) | Dependency distance, layer analysis |
| Cycle Detection | DFS 3-color coloring | Circular dependency detection |
| Tarjan's SCC | Iterative Lowlink | Tightly coupled module clusters |
| Topological Sort | Kahn's algorithm | Safe migration ordering |
| PageRank | 20-iter power method | Critical node identification |
| Graph Metrics | Fan-in/out, density | Coupling score, hotspot detection |
| Impact Analysis | Reverse graph + DFS | Blast radius calculation |

**Implementation note:** Tarjan's SCC and DFS use iterative implementations (explicit stack) to avoid Python's recursion limit on large repositories.

---

## API Reference

### Repository Management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/repositories/analyze` | Trigger full repository analysis |
| `GET` | `/repositories` | List all analyzed repositories |
| `GET` | `/repositories/{id}` | Repository details |
| `GET` | `/repositories/{id}/summary` | Analysis summary |
| `GET` | `/repositories/{id}/tree` | File tree structure |
| `GET` | `/repositories/{id}/status` | Analysis status |

### Graph Analysis

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/repositories/{id}/graph` | Full dependency graph |
| `GET` | `/repositories/{id}/cycles` | Detected circular dependencies |
| `GET` | `/repositories/{id}/scc` | Strongly Connected Components |
| `GET` | `/repositories/{id}/topo-sort` | Topological ordering |
| `GET` | `/repositories/{id}/metrics` | Graph metrics (PageRank, coupling, density) |
| `GET` | `/repositories/{id}/report` | Full architecture intelligence report |
| `POST` | `/repositories/{id}/impact` | Impact analysis for a specific file |
| `POST` | `/repositories/{id}/chat` | AI architecture assistant |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- A GitHub Personal Access Token (for higher API rate limits)
- An OpenAI API key (for AI explanations)

### 1. Clone the repository

```bash
git clone https://github.com/yourhandle/archpilot.git
cd archpilot
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
GITHUB_TOKEN=ghp_your_token_here
OPENAI_API_KEY=sk-your_key_here
```

### 3. Start the stack

```bash
docker-compose up --build
```

This will:
1. Start PostgreSQL and Redis
2. Run Alembic migrations
3. Start the FastAPI backend on `:8000`
4. Build and serve the React frontend on `:3000`

### 4. Open the dashboard

Navigate to [http://localhost:3000](http://localhost:3000) and enter any public GitHub repository URL.

---

## Local Development (without Docker)

### Backend

```bash
cd backend

# Create virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Start PostgreSQL and Redis (e.g. via Docker)
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=archpilot -e POSTGRES_DB=archpilot -e POSTGRES_USER=archpilot postgres:16-alpine
docker run -d -p 6379:6379 redis:7-alpine

# Copy env and configure
cp .env.example .env

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

npm install
npm run dev   # starts on :3000 with API proxy to :8000
```

---

## Testing

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run only algorithm tests (no DB required)
pytest app/tests/test_algorithms.py -v
```

The algorithm tests are pure unit tests — they don't touch PostgreSQL or Redis. The `TestGraphMetrics`, `TestTarjanSCC`, and `TestCycleDetection` suites cover all graph algorithm implementations with cyclic, acyclic, and edge-case inputs.

---

## Project Structure

```
archpilot/
├── backend/
│   ├── app/
│   │   ├── algorithms/
│   │   │   └── graph_algorithms.py     # All graph algorithms
│   │   ├── api/
│   │   │   └── routes/
│   │   │       └── repositories.py     # All API endpoints
│   │   ├── core/
│   │   │   ├── config.py               # Pydantic settings
│   │   │   ├── constants.py            # Enums, weights, system prompts
│   │   │   └── logging.py              # structlog JSON/pretty
│   │   ├── db/
│   │   │   ├── database.py             # Async engine + session factory
│   │   │   └── models/models.py        # SQLAlchemy ORM models
│   │   ├── parsers/
│   │   │   ├── python_parser.py        # AST + regex fallback
│   │   │   └── js_ts_parser.py         # ES modules + CommonJS + TS
│   │   ├── schemas/
│   │   │   └── schemas.py              # All Pydantic v2 schemas
│   │   ├── services/
│   │   │   ├── github_service.py       # GitHub API + exponential backoff
│   │   │   ├── repository_service.py   # Full analysis pipeline
│   │   │   ├── graph_service.py        # Algorithm orchestration + caching
│   │   │   ├── analysis_service.py     # Architecture health + risk scoring
│   │   │   └── ai_service.py           # LLM integration layer
│   │   ├── tests/
│   │   │   └── test_algorithms.py      # ~25 algorithm unit tests
│   │   └── main.py                     # FastAPI app + lifespan
│   ├── alembic/
│   │   └── versions/
│   │       └── 001_initial_schema.py   # Full schema migration
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── conftest.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                     # All views (single-file SPA)
│   │   ├── main.tsx                    # React entry point
│   │   ├── index.css                   # Tailwind + custom utilities
│   │   ├── services/api.ts             # Axios API client (typed)
│   │   └── types/index.ts              # TypeScript interfaces
│   ├── public/
│   │   └── favicon.svg
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
│
└── docker-compose.yml
```

---

## Architecture Decisions

### Why pure adjacency lists for algorithms?

All graph algorithm functions take `dict[str, list[str]]` and return plain Python objects. No ORM, no async, no database. This makes them:
- **Instantly testable** with `pytest` and zero fixtures
- **Composable** — impact analysis reuses DFS; architecture reports reuse metrics
- **Portable** — the algorithm layer has zero external dependencies

### Why iterative DFS and SCC?

Python's default recursion limit is 1,000. A real repository (like Django or FastAPI itself) can have hundreds of interconnected modules. Iterative implementations using explicit stacks avoid `RecursionError` on production-scale repos.

### Why does AI not see raw source code?

Three reasons:
1. **Grounding** — every AI claim can be traced to a deterministic algorithm result
2. **Cost** — structured JSON context is orders of magnitude cheaper than dumping file contents
3. **Accuracy** — LLMs hallucinate when reading large codebases; they explain well when given structured facts

### Why UUID primary keys?

Avoids sequential enumeration via the API, enables distributed inserts without coordination, and makes IDs safe to expose in URLs without leaking table size.

### Health Score formula

```
score = 100
score -= min(5, num_cycles) * 15     # -15 per cycle, max 5 cycles
score -= max(0, coupling - 30) * 0.5 # penalty above 30 coupling units
score -= max(0, density - 0.1) * 10  # penalty above 10% density
score -= (large_scc_count > 0) * 10  # SCC > 5 nodes is an architectural smell
score -= max(0, dead_code_pct - 10) * 2  # dead code above 10%
score = max(0, score)
```

---

## Supported Languages

| Language | Parser | Detection Method |
|---|---|---|
| Python | `python_parser.py` | AST (`ast.parse`), regex fallback |
| JavaScript | `js_ts_parser.py` | Regex (ES modules + CommonJS) |
| TypeScript | `js_ts_parser.py` | Regex (ES modules + triple-slash refs) |

---

## Roadmap

- [ ] Java/Kotlin parser (Maven/Gradle dependency resolution)
- [ ] Go parser (`import` block analysis)
- [ ] WebSocket streaming for real-time analysis progress
- [ ] GitHub App integration (webhook-triggered analysis)
- [ ] Diff-based re-analysis (only parse changed files)
- [ ] Architecture diff: compare two commits
- [ ] Export to Mermaid / DOT / JSON

---

## License

MIT
