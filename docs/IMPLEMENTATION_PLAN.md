# Implementation Plan

Status: Phase 1 complete · Phases 2–10 planned
Rule: a phase is done when its exit criteria pass, not when its code exists.

---

## 0. Ground rules

1. Every phase ends with: tests green, lint/type clean, migrations applied,
   API boots, docs updated.
2. From Phase 7 onward, every phase also ends with an `evaluation_runs` row and
   a comparison against the previous baseline. A regression in a gate metric
   blocks the merge.
3. No phase introduces a dependency without a one-line justification in the
   dependency table below.
4. Interfaces land before implementations. If two options are plausible, the
   interface ships first and both adapters follow.

---

## Phase 1 — Foundation ✅

**Delivered**

| Area | Detail |
|------|--------|
| Config | `pydantic-settings` with nested sections (`app`, `db`, `security`, `rag`, `models`, `observability`), `.env` loading, environment-aware defaults, fail-fast validation of production secrets |
| Logging | `structlog` JSON in prod / console in dev, request-id + trace-id binding |
| Errors | Single `AppError` hierarchy → RFC-9457-style problem responses, handlers for validation/HTTP/unhandled |
| Middleware | Request id, access log with latency, security headers, sliding-window rate limiting, CORS |
| Persistence | SQLAlchemy 2.0 async, 18 entities, `Vector` type with pgvector/JSON dialect fallback, Alembic with hand-written `0001_initial_schema` |
| Auth | Register / login / refresh / me, JWT access+refresh, Argon2id hashing, active-user and superuser dependencies |
| API v1 | `/health/*`, `/auth/*`, `/profile`, `/goals` CRUD, `/opportunities` list+detail (read) |
| Infra | Docker Compose: `postgres:16` + pgvector, `redis:7`, `api`, `frontend`, optional `ollama` profile; multi-stage backend image; `.env.example` |
| Frontend | Next.js 15 App Router + TypeScript + Tailwind, typed API client, dashboard / opportunities / goals / health pages |
| Tests | Unit (config, security, scoring stub, schemas) + integration (migrations on scratch DB) + end-to-end smoke (register → login → me → goal → list → health) |

**Exit criteria** — `pytest` green, `ruff`/`mypy` clean, `alembic upgrade head` renders on Postgres and applies on SQLite, `/health/ready` returns 200 against Compose, frontend builds.

---

## Phase 2 — Opportunity Engine

Deterministic core, no LLM required.

* `OpportunityService`: create / upsert / list with filters (category, country,
  remote, score floor, deadline window, status) and keyset pagination.
* Normalisation: URL canonicalisation, text normalisation, currency/period
  normalisation, deadline parsing (rule-based first, LLM fallback in Phase 4).
* Deduplication cascade: canonical URL → `content_hash` → org+title trigram →
  embedding cosine (embedding step no-ops until Phase 3).
* Freshness service: `freshness_score`, `expires_at` derivation, automatic
  transition to `EXPIRED`, and exclusion of stale rows from ranking.
* Status lifecycle state machine with legal transitions and `opportunity_events`
  emission.
* **Scoring engine**: `Weights`, `ScoringProfile` (career/income/business/
  learning/networking/startup/research), `score()` pure function, per-goal
  overrides, `weights_version` pinning, explanation payload.
* Seed script for `opportunity_sources` and a fixture corpus of ~50 real,
  legally-fetchable opportunities used by tests and evaluation.

**Exit criteria** — property tests on the scoring engine (bounded, monotonic,
weight-normalisation invariant, unknown-dimension redistribution); dedup recall
on a hand-labelled duplicate set ≥ 0.95 precision ≥ 0.98; ranking endpoint
returns deterministic order for a fixed corpus.

**Risks** — deadline parsing across locales; mitigated by rule-based parsing
with an explicit `UNKNOWN` rather than a guess.

---

## Phase 3 — RAG

* Document ingestion pipeline: upload → object storage → parse (PyMuPDF/
  `python-docx`; LlamaParse adapter behind `DocumentParser` for hard PDFs) →
  chunk (structure-aware, token-bounded, overlap) → embed → index.
* `EmbeddingProvider` (Ollama `nomic-embed-text` dev, TEI/vLLM prod) with a
  content-hash embedding cache in Redis.
* `VectorStore` interface + `PgVectorStore` (default), `QdrantStore`,
  `ChromaStore`, `FaissStore` (eval only).
* Hybrid search: dense cosine + Postgres full-text, fused by RRF.
* `Reranker` interface + `CrossEncoderReranker` (`bge-reranker-v2-m3`).
* Profile knowledge base assembled from `user_profiles` + indexed documents.

**Exit criteria** — retrieval benchmark on a labelled profile-QA set:
Recall@20 ≥ 0.90, NDCG@10 improves ≥ 10% with reranking vs without; p95
retrieval latency < 400 ms warm.

**Risks** — embedding dimension lock-in; mitigated by dimension recorded per
row (`embedding_model`) and a documented re-embed migration path.

---

## Phase 4 — Agent System

* `LLMProvider` interface + `OllamaProvider`, structured-output helper with
  validate → repair → retry → fallback.
* `AgentCard`, `BaseAgent`, `FakeLLMProvider` for tests.
* LangGraph assembly of the topology in `AGENT_DESIGN.md`, Postgres checkpointer.
* Agents: Supervisor, Discovery, Research, Qualification, Matching, Risk,
  Decision. Extraction node with constrained decoding.
* `POST /opportunities/investigate` → `202` + run id; SSE progress stream;
  persistence of `agent_runs` / `agent_tasks`.
* Prompt registry with versioned files under `prompts/`.

**Exit criteria** — the §48 demo scenario runs end to end on a local model and
produces a persisted report with evidence; graph tests cover routing, retries,
max-iteration termination and structured-output repair.

**Risks** — local model quality on structured extraction; mitigated by
constrained decoding and by keeping the graph model-agnostic so a cloud model
can be routed in for the extraction task class.

---

## Phase 5 — Tools + MCP

* Tool framework: Pydantic argument schema, description, timeout, retry policy,
  permission scope, side-effect class, budget accounting, tracing, error
  normalisation.
* Native tools: `search_opportunities`, `search_web`, `research_company`,
  `get_company_information`, `extract_deadline`, `check_eligibility`,
  `search_user_profile`, `search_user_documents`, `calculate_opportunity_score`,
  `get_previous_opportunities`, `create_follow_up`, `prepare_application`,
  `generate_outreach`, `save_opportunity`, `update_opportunity_status`.
* MCP server exposing the same registry over the protocol (one registry, two
  transports — no duplicated business logic).
* Tool permission layer + SSRF guard + per-tool rate limits.

**Exit criteria** — tool-selection accuracy ≥ 0.90 and argument validity ≥ 0.95
on the tool benchmark; every tool has a denial test and a timeout test; MCP
server passes a protocol conformance check.

---

## Phase 6 — Advanced Intelligence

Query expansion, cross-encoder reranking in the agent path, Contrarian Agent,
Verification Agent with claim typing and calibrated confidence, A2A-compatible
agent card endpoints, memory subsystem (episodic/semantic/outcome) with
provenance, outcome tracking, and feedback capture.

**Exit criteria** — recommendation quality on the golden set improves over the
Phase 4 baseline; contrarian pass demonstrably changes ≥ 15% of borderline
decisions; no memory write ever mutates an existing fact (audited by test).

---

## Phase 7 — Observability + Evaluation

OpenTelemetry instrumentation end to end, Langfuse/LangSmith export, MLflow
tracking, RAGAs integration, the golden dataset, the agent and ranking
evaluation harness, cost/latency/drift dashboards and alerts, and the CI
regression gate.

**Exit criteria** — every investigation produces a complete trace; the harness
runs in CI on a 50-case subset in under 10 minutes; gate metrics defined with
thresholds in `EVALUATION_PLAN.md`.

---

## Phase 8 — Fine-tuning

Only after a measured baseline. Dataset built from extraction corrections,
eligibility labels, ranking pairs and outcomes; SFT with LoRA/QLoRA on the
extraction and classification tasks; four-way comparison (base / prompted /
RAG / RAG+FT); registration of the winner in MLflow with a rollback path.

**Exit criteria** — a fine-tuned specialist beats the prompted baseline on its
narrow task by a margin larger than the eval noise band, or the experiment is
recorded as negative and shipped as such.

---

## Phase 9 — Production Inference

vLLM deployment, schema-constrained tool calling, the model gateway with
routing/fallback/cost accounting, semantic caching, and a load test.

---

## Phase 10 — Production Deployment

Celery + Redis workers and beat schedules, Kubernetes manifests, secrets
management, health/readiness probes, HPA, structured log shipping, backup and
restore drill, and the scheduled-intelligence digest.

---

## Dependency justification

| Dependency | Phase | Why this and not something else |
|-----------|-------|---------------------------------|
| FastAPI + Uvicorn | 1 | Async, Pydantic-native, SSE and DI built in |
| SQLAlchemy 2.0 + asyncpg | 1 | Typed async ORM; asyncpg is the fastest driver |
| Alembic | 1 | Only mature migration tool for SQLAlchemy |
| Pydantic v2 + pydantic-settings | 1 | Structured outputs and config share one validation engine |
| pgvector | 1 | Vectors in the same transaction as rows; removes a second datastore at MVP scale |
| PyJWT + argon2-cffi | 1 | Minimal, audited primitives; avoids the deprecated `crypt` chain in passlib |
| structlog | 1 | Structured logs without a bespoke formatter |
| Redis | 1 (infra) | One system for cache, rate limits, pub/sub and broker |
| LangGraph | 4 | Explicit state machine + durable checkpointing; the loop-avoidance requirement rules out plain agent loops |
| LlamaIndex | 3 | Ingestion/parsing breadth; used as a library, not as the architecture |
| sentence-transformers | 3 | Cross-encoder reranking |
| MCP SDK | 5 | Tool interoperability layer required by the brief |
| OpenTelemetry | 7 | Vendor-neutral; Langfuse consumes it |
| MLflow | 7/8 | Experiment and model registry |
| RAGAs | 7 | Standard RAG metrics; custom metrics live beside it |
| Celery | 10 | Mature scheduling + retries; alternatives evaluated but Redis is already present |

Deferred dependencies are declared as optional extras in `pyproject.toml` so
Phase 1 installs in seconds and CI stays fast.

---

## Sequencing rationale

Deterministic subsystems (Phase 2) precede retrieval (3), which precedes agents
(4), because each later layer's evaluation depends on the earlier layer being
fixed. Observability (7) is late in numbering but its *hooks* are created in
Phases 1 and 4 — persisted `agent_runs`/`tool_calls` mean the trace UI works
before any external collector exists.
