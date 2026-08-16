# Technical Architecture — Opportunity Intelligence Agent

Status: `v0.1` — foundation (Phase 1)
Owner: platform
Last updated: 2026-08-16

---

## 1. Problem statement

Opportunity discovery is a solved problem. Search engines, job boards, grant
databases and newsletters already produce far more candidate opportunities than
any individual can evaluate. The scarce resource is not *information*, it is
*judgement under a personal objective*.

This system therefore optimises for a different output than a search engine:

> Given the user's **active objectives**, **verified profile** and a **budgeted**
> amount of research, produce a small, ranked, explained and auditable set of
> opportunities together with a recommended next action — and explicitly
> suppress everything else.

Two consequences drive the whole architecture:

1. **Value is relative to an objective.** The same opportunity scores
   differently under an "income in 6 months" objective than under a
   "relocate to Germany" objective. Scores are therefore always computed
   *per (opportunity, goal)* pair, never stored as a single global number.
2. **Recommendations must be auditable.** Every score is produced by a
   deterministic engine from structured factors, and every factor is backed by
   evidence records with a source, timestamp, confidence and *claim type*.
   The LLM supplies evidence and structured factors; it never supplies the
   final number.

---

## 2. Architectural principles

| # | Principle | Consequence in the code |
|---|-----------|-------------------------|
| P1 | Deterministic where possible, probabilistic only where necessary | Scoring, deduplication, freshness, eligibility arithmetic and ranking are pure Python. LLMs extract and judge; they do not compute. |
| P2 | Every provider is replaceable behind an interface | `LLMProvider`, `EmbeddingProvider`, `VectorStore`, `Reranker`, `OpportunitySource`, `CacheBackend`, `ObjectStorage` are protocols with adapters. |
| P3 | External content is data, never instruction | All retrieved content passes through the content-isolation layer (§32 of the brief, `app/security/`) before reaching a prompt. |
| P4 | Structured in, structured out | Every agent has a Pydantic input and output schema. Unvalidated model text never reaches business logic. |
| P5 | Bounded autonomy | The graph has explicit states, max iterations, per-run tool budgets, cost ceilings and early-stopping on confidence. |
| P6 | Everything is traceable | One `trace_id` per investigation, propagated through agent tasks, tool calls, retrieval and LLM calls; persisted to the database *and* exported over OpenTelemetry. |
| P7 | Modular monolith first | A single deployable backend with hard module boundaries, so agents, retrieval and workers can be extracted into services (and A2A remote agents) without rewriting call sites. |
| P8 | Never fabricate | Insufficient evidence yields `UNKNOWN`, not a guess. |

Explicit non-goals for the MVP: microservices, a service mesh, multi-tenancy
beyond per-user row scoping, and autonomous execution of external side effects.

---

## 3. System context

```
┌──────────────┐        ┌──────────────────────────────────────────────┐
│  Next.js UI  │  HTTPS │                  Backend                     │
│  Gradio lab  ├────────▶  FastAPI  ─  API v1  ─  auth / RBAC / limits  │
└──────────────┘  SSE   └───────┬──────────────────────────────────────┘
                                │
                 ┌──────────────┼───────────────────────────┐
                 ▼              ▼                           ▼
        ┌────────────────┐  ┌────────────┐          ┌───────────────┐
        │ Supervisor     │  │ Services   │          │ Celery worker │
        │ (LangGraph)    │  │ (CRUD,     │          │ discovery /   │
        │                │  │  scoring)  │          │ revalidation  │
        └───────┬────────┘  └─────┬──────┘          └───────┬───────┘
                │                 │                         │
        ┌───────▼─────────────────▼─────────────────────────▼───────┐
        │  Tool layer (native + MCP)  ·  Retrieval  ·  Model layer   │
        └───────┬───────────────┬───────────────────┬───────────────┘
                ▼               ▼                   ▼
        ┌──────────────┐ ┌─────────────┐   ┌──────────────────┐
        │ PostgreSQL   │ │ Redis       │   │ Ollama / vLLM    │
        │  + pgvector  │ │ cache/queue │   │ external sources │
        └──────────────┘ └─────────────┘   └──────────────────┘
                                │
                                ▼
                    OpenTelemetry ▸ Langfuse / MLflow
```

### Runtime processes

| Process | Responsibility | Phase |
|---------|----------------|-------|
| `api` | FastAPI, request handling, SSE streaming, auth | 1 |
| `worker` | Celery worker: discovery, revalidation, embedding, evaluation | 10 (stub in 1) |
| `beat` | Celery beat: scheduled intelligence (§35) | 10 |
| `postgres` | System of record + vector index | 1 |
| `redis` | Cache, semantic cache, broker, rate-limit buckets | 1 (infra), used from 5 |
| `ollama` | Local inference | 9 (optional profile in 1) |

Long-running investigations never run inside a request. `POST /investigate`
creates an `agent_run` row, enqueues the job and returns `202` with a run id;
the client subscribes to `GET /agent-runs/{id}/stream` (SSE).

---

## 4. Layered module map

```
app/
  api/            HTTP boundary only. No business logic, no SQL.
    v1/routes/    Thin controllers -> services. Pydantic in/out.
    deps.py       DI: session, current user, settings, rate limiter.
  core/           Cross-cutting: settings, logging, errors, security prims.
  db/             Engine, session factory, base metadata, custom types,
                  Alembic migrations.
  models/         SQLAlchemy ORM (persistence shape).
  schemas/        Pydantic (wire + agent shape). Deliberately separate.
  services/       Business logic + repository access. Transaction owners.
  agents/         Agent implementations + LangGraph assembly + state.
  tools/          Native tool implementations (typed, validated, budgeted).
  mcp/            MCP server exposing the tool registry over the protocol.
  retrieval/      Chunking, embeddings, vector stores, hybrid search, rerank.
  memory/         Short-term / episodic / semantic / outcome memory.
  evaluation/     Datasets, metrics, harness, regression gates.
  security/       Content isolation, injection detection, SSRF guard, policy.
  observability/  Tracing, metrics, cost accounting, prompt versioning.
  workers/        Celery app, tasks, schedules.
```

Dependency rule (enforced by review, later by `import-linter`):

```
api  ->  services  ->  {models, retrieval, agents, memory, security}
agents -> {tools, retrieval, memory, schemas, observability}
tools  -> {services, retrieval, security}
core, db, schemas  ->  (leaf; depend on nothing internal except core)
```

`models` never imports `api`; `agents` never imports `api`; `tools` never
import `agents` (prevents tool→agent recursion).

---

## 5. Request lifecycles

### 5.1 Synchronous read (Phase 1)

```
client → middleware(request-id, rate limit, security headers)
       → route → dependency(current_user, AsyncSession)
       → service (repository query, row-level user scoping)
       → Pydantic response model → ORJSON
```

### 5.2 Investigation (Phase 4+)

```
POST /api/v1/opportunities/investigate
  → validate objective, resolve active goal(s)
  → create agent_run(status=pending, trace_id)
  → enqueue celery task, return 202 {run_id, trace_id}

worker
  → LangGraph invoke with checkpointer (Postgres)
  → nodes emit AgentEvent -> redis pubsub -> SSE to UI
  → each node writes agent_tasks / tool_calls / evidence rows
  → terminal node writes opportunity_scores + FinalOpportunityReport
  → run status=succeeded | failed | awaiting_approval
```

Durability: the LangGraph checkpointer persists state per node, so a worker
crash resumes at the last committed node rather than restarting the run.

---

## 6. Data architecture

PostgreSQL 16 is the single system of record. `pgvector` holds embeddings in
the same transaction as the rows they describe, which removes a whole class of
consistency bugs at MVP scale. The `VectorStore` interface keeps Qdrant/Chroma/
FAISS viable (§12 of the brief).

Key modelling decisions:

* **Opportunities are shared, scores are personal.** `opportunities` holds the
  objective facts of the opportunity; `opportunity_scores` is keyed by
  `(opportunity_id, goal_id, weights_version)`. Rescoring under a new objective
  never mutates the opportunity.
* **Evidence is first class.** `opportunity_evidence` rows carry
  `claim_type ∈ {FACT, INFERENCE, ESTIMATE, ASSUMPTION, UNKNOWN}`, a source URL,
  a retrieval timestamp, a confidence and a `supports` flag so contrarian and
  verification findings are stored beside supporting ones.
* **Freshness is a column, not a job artifact.** `discovered_at`,
  `last_verified_at`, `expires_at` and a derived `freshness_score` live on the
  opportunity; the ranking query filters stale rows rather than relying on a
  cleanup job having run.
* **Provenance on memory.** `memory_records` store `valid_from`/`valid_to` and a
  `provenance` document, so memory can be contradicted but never silently
  overwrites a fact.

Full column-level detail: [`DATA_MODEL.md`](./DATA_MODEL.md).

---

## 7. Retrieval architecture

```
query + objective
  → query expansion (LLM, cached, n variants)
  → parallel: dense (pgvector cosine)  +  lexical (tsvector / BM25)
  → reciprocal-rank fusion → top-K (K≈50)
  → cross-encoder rerank → top-N (N≈8)
  → context filter (dedupe, token budget, isolation wrapping)
  → agent
```

Two logically separate indexes share one implementation: the **private profile
index** (`document_chunks`, never leaves the user's scope) and the
**opportunity index** (`opportunities.embedding`, shared). The retrieval router
chooses index, expansion depth and rerank width based on query type, which is
how "adaptive retrieval" is implemented without a second framework.

---

## 8. Model layer

`LLMProvider` exposes `complete()`, `structured()` and `stream()`; adapters:
`OllamaProvider` (dev), `VLLMProvider` (prod, schema-constrained decoding),
`CloudProvider` (fallback/eval baseline). A router maps *task classes* to model
handles:

| Task class | Model tier | Rationale |
|------------|-----------|-----------|
| `classify`, `route` | small | cheap, high volume |
| `extract` | structured-output tuned / constrained decoding | schema fidelity matters |
| `reason`, `contrarian`, `decide` | strong reasoning | quality dominates cost |
| `embed` | dedicated embedding model | separate lifecycle |
| `rerank` | cross-encoder | not a generative task |

The router is configuration, not code: `settings.models.routing` maps task class
→ provider + model, so a fine-tuned specialist (Phase 8) is a config change.

---

## 9. Security architecture

Summarised here, detailed in [`SECURITY_MODEL.md`](./SECURITY_MODEL.md).

* Trust hierarchy `SYSTEM > POLICY > USER > TRUSTED_DB > EXTERNAL` is a real
  enum in `app/security/trust.py`; external content is wrapped in
  non-instruction delimiters and stripped of imperative directives.
* Tools declare a permission scope and a side-effect class; anything with an
  external side effect requires a human approval checkpoint.
* Egress passes an SSRF guard (scheme/host/IP-range allowlisting, redirect
  re-validation).
* Profile documents are private by construction: every retrieval query against
  the profile index is scoped by `user_id` at the SQL level, not by prompt.

---

## 10. Observability

One `trace_id` per investigation, generated at the API boundary, stored on
`agent_runs` and attached to every child row and every OTel span. Spans are
emitted for supervisor decisions, agent tasks, tool calls, retrieval stages,
rerank, LLM calls (with prompt version, token counts, cost) and DB calls.
Langfuse consumes the OTel stream; MLflow tracks evaluation/fine-tuning runs.
The UI's Agent Trace page reads the persisted rows, so tracing works even if the
external collector is down.

---

## 11. Failure model

| Failure | Handling |
|---------|----------|
| Source/API unavailable | Circuit breaker per source, degrade to remaining sources, record `partial_results=true` on the run |
| LLM timeout | Retry with backoff (tenacity), then fall back to a smaller model, then fail the node |
| Structured-output validation failure | Retry with validation errors injected → constrained repair → log → node returns `UNKNOWN` |
| Vector store unavailable | Fall back to lexical-only retrieval, mark degraded retrieval in the run |
| Tool failure | Recorded on `tool_calls`, supervisor re-plans within budget |
| Conflicting evidence | Verification agent records both sides; confidence drops; recommendation caps at `CONSIDER` |
| Budget exhausted | Early stop, return best-effort report flagged `budget_exhausted` |

A run never dies silently: every terminal state writes a row and a span.

---

## 12. Deployment topology

* **Dev**: Docker Compose — `postgres+pgvector`, `redis`, `api`, `worker`,
  `frontend`, optional `ollama` profile.
* **Prod**: containers on Kubernetes — `api` (HPA on RPS), `worker` (HPA on
  queue depth), `beat` (single replica), managed Postgres with pgvector,
  managed Redis, vLLM on a GPU node pool. Health at `/health/live`, readiness at
  `/health/ready` (checks DB, and Redis when enabled).

---

## 13. Current state (Phase 1)

Implemented: configuration, structured logging, error contract, request-id and
rate-limit middleware, SQLAlchemy 2.0 async models for all 18 entities, the
vector type abstraction, Alembic with a hand-written initial migration, JWT
authentication with Argon2 hashing, health/auth/profile/goals/opportunity-read
endpoints, Docker development environment, Next.js dashboard skeleton, and an
end-to-end smoke test that runs migrations and exercises the API.

Deliberately *not* implemented yet (each is scheduled in
[`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)): agents, LangGraph,
retrieval, tools, MCP, evaluation harness, workers, fine-tuning. Their packages
exist with an `__init__.py` and a `README`-style docstring describing the
contract they will satisfy, so the boundaries are fixed before the code lands.
