# Opportunity Intelligence Agent

An autonomous system that discovers opportunities — jobs, grants, fellowships,
programmes, competitions — researches them against a personal profile, scores
them on evidence rather than vibes, and explains every recommendation it makes.

The guiding constraint is that a recommendation is only useful if you can audit
it. Every score decomposes into named dimensions, every dimension traces back to
a stored piece of evidence, and every piece of evidence carries a URL, a
retrieval timestamp, and a claim type. The system says "I don't know" instead of
guessing.

> **Status: Phase 1 (Foundation) complete.** The data model, API surface, auth,
> security primitives, migration, container stack, and frontend shell are built
> and tested. The agent graph, retrieval stack, and tool layer are specified in
> `/docs` and land in Phases 2–6.

## Documentation

| Document | What it covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System context, module map, request lifecycles, deployment topology |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | All 18 tables, column semantics, scoring arithmetic, migration policy |
| [`docs/AGENT_DESIGN.md`](docs/AGENT_DESIGN.md) | Graph topology, agent contracts, routing rules, autonomy budgets |
| [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) | Endpoint-by-endpoint request/response contracts and error shapes |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Phase-by-phase deliverables, exit criteria, dependency justifications |
| [`docs/EVALUATION_PLAN.md`](docs/EVALUATION_PLAN.md) | Datasets, metrics, CI gates, baselines the system must beat |
| [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) | Trust hierarchy, prompt-injection defence, authz, egress control |

## Quick start

### Docker (everything)

```bash
cp .env.example .env          # then set SECURITY__SECRET_KEY
make up                       # postgres + pgvector, redis, api, frontend
make migrate
```

API at http://localhost:8000, interactive schema at http://localhost:8000/docs,
dashboard at http://localhost:3000.

### Local (backend and frontend separately)

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate    # source .venv/bin/activate on Unix
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

If you have no PostgreSQL to hand, set `DATABASE__URL=sqlite+aiosqlite:///./oia_dev.db`
in `.env` and everything in Phase 1 runs unchanged — the migration and all
endpoints work on SQLite. Vector search (Phase 3) is what genuinely requires
PostgreSQL with the `vector` extension, and `make up` will start just that
service if you prefer to run the application processes on the host.

## Development

```bash
make check      # ruff + mypy + pytest, the same gate CI runs
make test       # pytest
make smoke      # end-to-end smoke test only
make fmt        # ruff check --fix, then ruff format
make web-build  # production frontend build
```

The test suite applies the real Alembic migration to a temporary SQLite database
on every run, so schema drift between the ORM and the migration fails a test
rather than a deployment.

## What exists today

**Backend** — FastAPI on SQLAlchemy 2.0 async, with configuration that refuses
to start on unsafe production settings, structured logging with request and
trace correlation, RFC-9457 problem-details errors, sliding-window rate
limiting, Argon2id password hashing, and JWT access/refresh tokens.

**Database** — 18 tables covering users and profiles, goals, documents and
chunks, opportunity sources and opportunities, scores, evidence, events,
applications and outcomes, agent runs, tasks and tool calls, memory, feedback,
and evaluation runs. Embedding columns are `vector(768)` on PostgreSQL with
HNSW indexes and degrade to JSON on SQLite so the schema stays testable.

**API** — health (live/ready/info), auth (register/login/refresh/me), profile
(get/put/patch), goals (CRUD), and opportunities (list with filtering, sorting,
and keyset pagination; detail with scores and evidence).

**Security** — the trust hierarchy from `docs/SECURITY_MODEL.md` is enforced in
code: external content is sanitized, scanned for injection patterns, and
rendered into prompts inside nonce-delimited blocks that carry no instruction
authority.

**Frontend** — Next.js 15 with TypeScript and Tailwind 4: dashboard, opportunity
explorer, goals manager, and system status, against a typed API client.

## Layout

```
backend/    FastAPI application, ORM, migrations, tests
frontend/   Next.js dashboard
docs/       architecture and design documents
infra/      Docker Compose stack and service images
```

## License

Not yet licensed. All rights reserved.
