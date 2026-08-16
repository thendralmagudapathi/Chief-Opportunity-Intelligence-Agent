# Data Model

Status: `v0.1` — matches migration `0001_initial_schema`
Engine: PostgreSQL 16 + `pgvector`
ORM: SQLAlchemy 2.0 (async, `Mapped[...]` style) · Migrations: Alembic

---

## 1. Conventions

| Concern | Decision | Reason |
|---------|----------|--------|
| Primary keys | `UUID` (v4), application-generated | Safe to mint before insert, no cross-service collisions, no enumeration |
| Timestamps | `TIMESTAMP WITH TIME ZONE`, always UTC | Deadlines and freshness are timezone-critical |
| Audit columns | `created_at`, `updated_at` on every mutable table | Provided by `TimestampMixin` |
| Enums | `VARCHAR` + `CHECK` (`native_enum=False`) | Adding a value is a cheap migration; keeps SQLite usable for tests |
| Free-form structures | `JSONB` | Requirement lists and factor payloads evolve faster than DDL |
| Embeddings | `Vector(768)` via `app.db.types.Vector` | pgvector on Postgres, JSON fallback on SQLite so tests run without a server |
| Deletes | Soft where history matters (`status` columns); hard cascade for owned children | Outcomes and evidence must survive |
| Money | `NUMERIC(14,2)` + explicit `currency` (ISO-4217) | Never float, never implicit currency |
| Scores | `NUMERIC(6,4)` normalised to `[0,1]`, plus a display `overall_score` in `[0,100]` | Weighted arithmetic stays exact and comparable |

The embedding dimension is fixed in DDL (768, matching `nomic-embed-text`).
Changing it is an explicit migration, not a runtime setting; `settings.rag.embedding_dim`
must agree and is asserted at startup.

---

## 2. Entity relationship overview

```
users ─1:1─ user_profiles
  │
  ├─1:N─ goals ───────────────┐
  ├─1:N─ documents ─1:N─ document_chunks (vector, tsv)
  ├─1:N─ memory_records (vector)
  ├─1:N─ agent_runs ─1:N─ agent_tasks ─1:N─ tool_calls
  ├─1:N─ applications ─1:N─ outcomes
  └─1:N─ feedback
                                │
opportunity_sources ─1:N─ opportunities (vector, tsv)
                                ├─1:N─ opportunity_scores  ◀── goals
                                ├─1:N─ opportunity_evidence
                                ├─1:N─ opportunity_events
                                ├─1:N─ applications
                                └─1:N─ feedback

evaluation_runs  (standalone; references git sha + dataset version)
```

---

## 3. Tables

### 3.1 `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `email` | varchar(320) | unique, stored lower-cased |
| `hashed_password` | varchar(255) | Argon2id |
| `full_name` | varchar(255) | nullable |
| `is_active` | boolean | default `true`; inactive users cannot authenticate |
| `is_superuser` | boolean | default `false` |
| `last_login_at` | timestamptz | nullable |
| `created_at` / `updated_at` | timestamptz | |

### 3.2 `user_profiles`

One row per user; the structured half of the personal knowledge base (the
unstructured half lives in `documents` / `document_chunks`).

`headline`, `summary`, `location_country` (ISO-3166-1 alpha-2), `location_city`,
`timezone`, `years_experience` (numeric 4,1), `salary_expectation_min/max`
(numeric 14,2), `salary_currency`, and JSONB documents: `skills`,
`work_authorization`, `education`, `certifications`, `languages`, `interests`,
`preferences`, `constraints`. Unique on `user_id`, cascade delete.

JSONB shapes are validated by Pydantic on write (`schemas/profile.py`), e.g.
`skills: [{name, level: 1..5, years, evidence_document_id?}]`.

### 3.3 `goals`

The objective engine (§9 of the brief). Scores are meaningless without one.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `user_id` | uuid FK → users | cascade |
| `title` | varchar(255) | e.g. "Move to Germany and secure an AI engineering role" |
| `description` | text | |
| `objective_profile` | enum | `career`, `income`, `business`, `learning`, `networking`, `startup`, `research` — selects the default scoring weight set |
| `priority` | smallint | 1 (highest) … 5 |
| `status` | enum | `active`, `paused`, `achieved`, `abandoned` |
| `deadline` | timestamptz | nullable |
| `desired_outcome` | text | |
| `constraints` | jsonb | e.g. `{"max_relocation": true, "min_salary_eur": 70000}` |
| `acceptable_tradeoffs` | jsonb | |
| `weights_override` | jsonb | per-goal override of the scoring weight vector |

Index: `(user_id, status, priority)` — the ranking query's entry point.

### 3.4 `documents` / `document_chunks`

`documents`: `user_id`, `filename`, `content_type`, `size_bytes`,
`storage_uri`, `sha256` (unique per user — idempotent re-upload),
`doc_type` (`resume`, `cv`, `cover_letter`, `portfolio`, `transcript`,
`certificate`, `note`, `other`), `status` (`pending`, `parsing`, `indexed`,
`failed`), `error`, `parsed_at`, `meta`.

`document_chunks`: `document_id`, `user_id` (denormalised for cheap row-level
scoping), `chunk_index`, `content`, `token_count`, `embedding Vector(768)`,
`embedding_model`, `meta`. Unique `(document_id, chunk_index)`.
Postgres-only: IVFFlat index on `embedding` (cosine) and a GIN index on
`to_tsvector('english', content)` for the lexical half of hybrid search.

### 3.5 `opportunity_sources`

Registry backing the `OpportunitySource` interface: `key` (unique slug),
`name`, `source_type` (`api`, `rss`, `feed`, `html`, `manual`), `base_url`,
`enabled`, `requires_auth`, `rate_limit_per_minute`, `robots_respected`,
`config` jsonb, `last_run_at`, `last_error`. Sources are rows, not code
constants, so enabling a source is an operational action.

### 3.6 `opportunities`

The canonical, *objective* record. Nothing user-specific lives here.

| Group | Columns |
|-------|---------|
| Identity | `id`, `source_id` FK, `external_id`, `title`, `category`, `subcategory` |
| Org | `organization_name`, `organization_domain` |
| Content | `description`, `summary`, `language`, `raw` jsonb |
| Location | `location_country`, `location_city`, `remote_status` (`onsite`, `hybrid`, `remote`, `unknown`) |
| Money | `compensation_min`, `compensation_max`, `compensation_currency`, `compensation_period` (`hour`, `day`, `month`, `year`, `project`, `total`) |
| Requirements | `requirements`, `eligibility`, `required_skills`, `preferred_skills` (all jsonb) |
| Time | `posted_at`, `deadline`, `discovered_at`, `last_verified_at`, `expires_at`, `freshness_score` |
| Dedup | `source_url`, `canonical_url`, `content_hash` (sha256 of normalised text), `simhash` (bigint) |
| Lifecycle | `status` (`discovered`, `enriched`, `qualified`, `scored`, `recommended`, `archived`, `expired`, `rejected`, `duplicate`), `duplicate_of_id` self-FK |
| Vector | `embedding Vector(768)`, `embedding_model` |

`category` enum covers the full brief: `job`, `freelance`, `consulting`,
`client`, `startup`, `grant`, `fellowship`, `scholarship`, `accelerator`,
`incubator`, `competition`, `conference`, `speaking`, `research`, `partnership`,
`business`, `open_source`, `other`.

Constraints and indexes:

* unique `(source_id, external_id)` where both present — source-level idempotency
* unique `content_hash` — exact-duplicate short-circuit
* index `canonical_url`, `(category, status)`, `deadline`, `discovered_at desc`,
  `(organization_domain, title)` — organisation+title near-duplicate probe
* Postgres-only: IVFFlat on `embedding`, GIN on `to_tsvector(title || description)`

Deduplication (§24) reads these in ascending cost order: canonical URL →
`content_hash` → `(organization_domain, title)` trigram → embedding cosine
above threshold. The winner keeps the row; the loser gets
`status='duplicate'` and `duplicate_of_id`.

### 3.7 `opportunity_scores`

Keyed by `(opportunity_id, goal_id, weights_version)` — the same opportunity has
one row per objective it was evaluated against. Never overwritten in place;
re-scoring inserts a new `weights_version`/`computed_at` row so ranking changes
are explainable after the fact.

Dimensions, each `NUMERIC(6,4)` in `[0,1]`: `fit_score`, `value_score`,
`probability_of_success`, `strategic_value`, `time_sensitivity`, `effort_score`,
`risk_score`, `learning_value`, `network_value`, `long_term_value`.
Plus `overall_score` (`NUMERIC(6,2)`, 0–100 display), `confidence`,
`scoring_profile`, `weights_version`, `engine_version`, `factors` jsonb (the
structured evidence-backed factors the LLM produced), `explanation` jsonb
(the WHY THIS / WHY NOW / WHY ME payload), `agent_run_id`, `computed_at`.

### 3.8 `opportunity_evidence`

| Column | Notes |
|--------|-------|
| `claim` | the assertion in plain text |
| `claim_type` | `FACT`, `INFERENCE`, `ESTIMATE`, `ASSUMPTION`, `UNKNOWN` |
| `stance` | `supports`, `contradicts`, `neutral` — contrarian findings are first-class |
| `value` | jsonb, the structured form of the claim when it has one |
| `source_url`, `source_title`, `source_trust` | provenance |
| `retrieved_at`, `confidence` | freshness + calibration |
| `agent_run_id`, `agent_name` | who asserted it |

No high-severity risk or recommendation may reference a claim that has no
evidence row. This is enforced in the decision service, not in a prompt.

### 3.9 `opportunity_events`

Append-only lifecycle log: `opportunity_id`, `user_id` (nullable for system
events), `event_type` (`discovered`, `deduplicated`, `enriched`, `scored`,
`recommended`, `viewed`, `dismissed`, `revalidated`, `expired`,
`status_changed`), `payload` jsonb, `agent_run_id`, `created_at`.
Feeds the "new since last check" view and the outcome dataset.

### 3.10 `applications` / `outcomes`

`applications`: `user_id`, `opportunity_id`, `status` (`draft`,
`awaiting_approval`, `approved`, `submitted`, `withdrawn`, `rejected`,
`accepted`), `channel`, `submitted_at`, `artifacts` jsonb (draft documents,
checklist), `approved_by_user_at`, `notes`.

`outcomes`: `application_id` (nullable — an opportunity can be ignored without
an application), `opportunity_id`, `user_id`, `outcome` (`applied`,
`interviewed`, `rejected`, `accepted`, `ignored`, `expired`, `successful`),
`occurred_at`, `details` jsonb. This table is the label source for outcome
evaluation and any future fine-tuning dataset.

### 3.11 `agent_runs` / `agent_tasks` / `tool_calls`

`agent_runs`: `user_id`, `goal_id`, `trace_id` (unique), `objective_text`,
`run_type` (`search`, `investigate`, `refresh`, `evaluate`, `scheduled`),
`status` (`pending`, `running`, `awaiting_approval`, `succeeded`, `failed`,
`cancelled`), `graph_version`, `iterations`, `started_at`, `finished_at`,
`latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`, `budget` jsonb,
`degraded` bool, `error`, `result` jsonb.

`agent_tasks`: `agent_run_id`, `parent_task_id` (self-FK, hierarchical
delegation), `agent_name`, `capability`, `status` (`pending`, `running`,
`succeeded`, `failed`, `skipped`), `attempt`, `input`/`output` jsonb, `error`,
`started_at`, `finished_at`, `latency_ms`, token/cost columns, `prompt_version`.

`tool_calls`: `agent_run_id`, `agent_task_id`, `tool_name`, `transport`
(`native`, `mcp`), `arguments` jsonb, `result` jsonb (truncated + hashed when
large), `status` (`succeeded`, `failed`, `denied`, `timeout`), `error`,
`latency_ms`, `cost_usd`, `cache_hit`.

Together these three tables *are* the Agent Trace page and the agent evaluation
dataset — tracing is not a side-effect of an external SaaS being reachable.

### 3.12 `memory_records`

`user_id`, `memory_type` (`episodic`, `semantic`, `outcome`), `key`, `content`,
`embedding Vector(768)`, `importance`, `confidence`, `provenance` jsonb,
`source_ref`, `valid_from`, `valid_to` (null = current), `superseded_by_id`
self-FK. Memory is bitemporal-lite: a contradicted fact is closed off with
`valid_to`, never deleted or silently edited.

### 3.13 `feedback`

`user_id`, `opportunity_id`, `agent_run_id`, `signal` (`relevant`,
`irrelevant`, `high_value`, `not_eligible`, `too_much_effort`, `low_value`,
`applied`, `successful`), `comment`, `payload` jsonb. Stored raw; never used to
auto-tune. Promotion into an evaluation or training dataset is an explicit,
reviewed step (§36).

### 3.14 `evaluation_runs`

`name`, `dataset_name`, `dataset_version`, `git_sha`, `config` jsonb,
`metrics` jsonb, `status`, `started_at`, `finished_at`, `mlflow_run_id`,
`notes`. Every architectural change is expected to produce a row here before it
is considered done (§40).

---

## 4. Scoring arithmetic

Stored dimensions are normalised; the engine is a pure function
`score(factors, weights) -> ScoreResult` with no I/O and no model access.

```
benefit = Σ wᵢ · dᵢ            for d ∈ {value, fit, probability, strategic,
                                        time_sensitivity, learning, network,
                                        long_term}
cost    = 1 + wₑ·effort + w_r·risk
overall = 100 · benefit / cost      clipped to [0, 100]
```

A multiplicative form (as sketched in the brief) collapses to zero when any one
dimension is unknown, so the implementation uses a weighted-sum benefit over a
penalty denominator, with unknown dimensions excluded from the sum and their
weight redistributed. `weights_version` pins the weight vector; the
`objective_profile` of the goal selects the default vector, `weights_override`
on the goal replaces it. Every stored score can therefore be recomputed and
diffed offline from `factors` alone.

---

## 5. Migration policy

* One Alembic head; no branch merges without an explicit merge revision.
* Every migration has a working `downgrade`.
* pgvector-specific DDL (`CREATE EXTENSION`, IVFFlat, GIN/tsvector) is guarded
  by a dialect check so the same migration runs on SQLite in tests.
* Schema drift is caught by `tests/test_migrations.py`, which upgrades a scratch
  database and asserts the resulting tables/columns equal `Base.metadata`.
