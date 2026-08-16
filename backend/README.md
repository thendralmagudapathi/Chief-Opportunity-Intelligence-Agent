# Backend — Opportunity Intelligence Agent

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/pgvector + Alembic.

## Local development

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
# source .venv/bin/activate                          # macOS / Linux
pip install -e ".[dev]"

cp ../.env.example ../.env
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive schema at http://localhost:8000/docs (development only).

## Commands

| Task | Command |
|------|---------|
| Tests | `pytest` |
| Smoke test only | `pytest -m smoke` |
| Coverage | `pytest --cov=app --cov-report=term-missing` |
| Lint | `ruff check app tests` |
| Format | `ruff format app tests` |
| Types | `mypy app` |
| New migration | `alembic revision --autogenerate -m "message"` |
| Render SQL without a server | `alembic upgrade head --sql` |

The test suite runs the real Alembic migration against a temporary SQLite
database, so migrations are exercised on every run and schema drift between the
ORM and the migration fails a test rather than a deployment.

## Layout

```
app/
  api/            HTTP boundary (routes, dependencies, middleware)
  core/           config, logging, errors, security primitives
  db/             engine, session, base metadata, portable types, migrations
  models/         SQLAlchemy ORM
  schemas/        Pydantic wire and agent contracts
  services/       business logic and queries
  agents/         LangGraph orchestration and specialised agents   (Phase 4-6)
  tools/          native tool registry                             (Phase 5)
  mcp/            MCP transport over the tool registry             (Phase 5)
  retrieval/      embeddings, vector stores, hybrid search, rerank (Phase 3)
  memory/         episodic / semantic / outcome memory             (Phase 6)
  security/       trust hierarchy, content isolation, egress guard
  evaluation/     metric emission and CI gates                     (Phase 7)
  observability/  tracing, metrics, cost accounting                (Phase 7)
  workers/        Celery tasks and schedules                       (Phase 10)
```

Architecture and rationale: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).
