# API Contracts — v1

Base path: `/api/v1` · Auth: `Authorization: Bearer <access_token>`
Content type: `application/json` (uploads use `multipart/form-data`)
Interactive schema: `/docs` (development only), OpenAPI at `/api/v1/openapi.json`

Legend: ✅ implemented in Phase 1 · ⏳ contract frozen, implementation scheduled.

---

## 1. Conventions

**Errors** follow a single problem-details shape:

```json
{
  "type": "validation_error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "1 field failed validation",
  "instance": "/api/v1/goals",
  "trace_id": "0f9c1e0a4b7d4c1e9a5b",
  "errors": [{ "field": "body.priority", "message": "Input should be <= 5" }]
}
```

Stack traces and internal messages are never returned; `trace_id` correlates a
client report with server logs and the persisted run.

**Pagination** is keyset-based for list endpoints:
`?limit=20&cursor=<opaque>` → `{ "items": [...], "next_cursor": "...", "has_more": true }`.
`limit` is bounded to `[1, 100]`.

**Idempotency**: `POST` endpoints that create side effects accept an
`Idempotency-Key` header; a repeated key within 24h returns the original result.

**Versioning**: breaking changes create `/api/v2`; additive fields do not.
Every response carries `X-Request-ID`; investigation responses also carry
`X-Trace-ID`.

---

## 2. Health ✅

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health/live` | none | Process liveness. Never touches dependencies. |
| GET | `/health/ready` | none | Dependency readiness: database, and Redis when enabled. `503` with per-check detail if degraded. |
| GET | `/health/info` | none | Name, version, environment, git sha. |

```json
// GET /api/v1/health/ready → 200
{ "status": "ok", "checks": [ { "name": "database", "status": "ok", "latency_ms": 3.1 } ] }
```

---

## 3. Auth ✅

| Method | Path | Body → Response |
|--------|------|-----------------|
| POST | `/auth/register` | `{email, password, full_name?}` → `201 UserRead` |
| POST | `/auth/login` | `{email, password}` → `200 {access_token, refresh_token, token_type, expires_in}` |
| POST | `/auth/refresh` | `{refresh_token}` → `200 TokenPair` |
| GET | `/auth/me` | — → `200 UserRead` |

Password policy: ≥ 12 characters, not in the common-password denylist.
Login failures return a uniform `401 invalid_credentials` regardless of cause.
Auth endpoints have a tighter rate-limit bucket than the rest of the API.

---

## 4. Profile ✅

| Method | Path | Description |
|--------|------|-------------|
| GET | `/profile` | Current user's structured profile (created empty on first read) |
| PUT | `/profile` | Full replace, validated JSONB sections |
| PATCH | `/profile` | Partial update |

```json
// PATCH /api/v1/profile
{
  "headline": "AI engineer",
  "location_country": "IN",
  "skills": [ { "name": "PyTorch", "level": 4, "years": 3 } ],
  "work_authorization": [ { "country": "IN", "status": "citizen" } ],
  "salary_expectation_min": 90000, "salary_currency": "EUR"
}
```

---

## 5. Goals ✅

| Method | Path | Description |
|--------|------|-------------|
| GET | `/goals` | List, filterable by `status` |
| POST | `/goals` | Create. `objective_profile` selects the default scoring weights |
| GET | `/goals/{id}` | Detail |
| PATCH | `/goals/{id}` | Update (including `weights_override`) |
| POST | `/goals/{id}/score` | Score every active opportunity against this goal |
| DELETE | `/goals/{id}` | Delete |

```json
// POST /api/v1/goals
{
  "title": "Move to Germany and secure an AI engineering role",
  "objective_profile": "career",
  "priority": 1,
  "deadline": "2027-03-31T00:00:00Z",
  "desired_outcome": "Signed offer, relocation covered",
  "constraints": { "min_salary_eur": 75000, "requires_visa_sponsorship": true },
  "acceptable_tradeoffs": ["smaller company", "hybrid over remote"]
}
```

---

## 6. Opportunities

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/opportunities` | ✅ | Ranked list. Filters: `category`, `status`, `country`, `remote_status`, `min_score`, `deadline_before`, `goal_id`, `q`. Sort: `score` (default), `deadline`, `discovered_at` |
| GET | `/opportunities/{id}` | ✅ | Detail with scores, evidence, risks, missing requirements, freshness |
| POST | `/opportunities/search` | ⏳ P4 | Objective-driven search; `202` + `run_id` when `mode=agentic`, `200` + results when `mode=index` |
| POST | `/opportunities/investigate` | ⏳ P4 | Full investigation. `202 { run_id, trace_id, stream_url }` |
| POST | `/opportunities/{id}/refresh` | ✅ P2 | Recompute freshness from stored facts; may set `EXPIRED` |
| POST | `/opportunities/{id}/evaluate` | ⏳ P4 | Re-score against a specified `goal_id` |
| POST | `/opportunities/{id}/apply` | ⏳ P6 | Create an application draft; external submission requires approval |
| POST | `/opportunities/{id}/feedback` | ⏳ P6 | Record a feedback signal |

```json
// GET /api/v1/opportunities/{id} → 200 (shape frozen now, fields populated by phase)
{
  "id": "…", "title": "…", "category": "job", "organization_name": "…",
  "source_url": "…", "location_country": "DE", "remote_status": "hybrid",
  "compensation": { "min": 80000, "max": 95000, "currency": "EUR", "period": "year" },
  "deadline": "2026-09-30T23:59:59Z",
  "freshness": { "discovered_at": "…", "last_verified_at": "…", "expires_at": "…", "score": 0.82 },
  "score": {
    "overall_score": 87.4, "confidence": 0.71, "scoring_profile": "career",
    "weights_version": "career.v1",
    "dimensions": { "fit_score": 0.82, "value_score": 0.75, "probability_of_success": 0.44,
                    "strategic_value": 0.9, "time_sensitivity": 0.6,
                    "effort_score": 0.35, "risk_score": 0.2,
                    "learning_value": 0.7, "network_value": 0.5, "long_term_value": 0.8 }
  },
  "recommendation": "PURSUE",
  "explanation": { "why_this": [...], "why_now": [...], "why_me": [...],
                   "what_could_go_wrong": [...], "supporting_evidence": [...],
                   "contradicting_evidence": [...], "missing_information": [...],
                   "next_step": "…" },
  "eligibility": { "verdict": "eligible", "requirements": [
      { "name": "EU work authorization", "state": "unknown", "evidence_id": "…" } ] },
  "risks": [ { "severity": "medium", "kind": "competition", "detail": "…", "evidence_id": "…" } ],
  "status": "recommended"
}
```

---

## 7. Documents ⏳ (P3)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents` | `multipart/form-data` upload → `202 { document_id, status: "pending" }` |
| GET | `/documents` | List with parse/index status |
| GET | `/documents/{id}` | Metadata |
| DELETE | `/documents/{id}` | Delete document, chunks and vectors |

Limits: 20 MB, `pdf|docx|md|txt`, content type sniffed rather than trusted.

---

## 8. Research ⏳ (P4)

`POST /research` — ad-hoc research task (`{question, scope, budget?}`) →
`202 { run_id, trace_id, stream_url }`.

---

## 9. Agent runs ⏳ (P4)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agent-runs` | List runs for the user |
| GET | `/agent-runs/{id}` | Run with tasks, tool calls, evidence, cost and token totals |
| GET | `/agent-runs/{id}/stream` | **SSE** progress stream |
| POST | `/agent-runs/{id}/cancel` | Cooperative cancellation |
| GET | `/agent-runs/{id}/approvals` | Pending approval request, if any |
| POST | `/agent-runs/{id}/approvals/{approval_id}` | `{decision: approve\|reject\|edit, edits?}` → resumes the graph |

SSE event stream (`text/event-stream`):

```
event: stage
data: {"stage":"discovery","status":"running","message":"Searching opportunity sources"}

event: stage
data: {"stage":"dedup","status":"done","message":"61 unique opportunities","counts":{"before":87,"after":61}}

event: approval_required
data: {"approval_id":"…","action":"send_outreach","risk":"medium"}

event: done
data: {"run_id":"…","status":"succeeded","report_url":"/api/v1/agent-runs/…"}
```

Heartbeat comments every 15 s; the client reconnects with `Last-Event-ID`.

---

## 10. Applications & outcomes ⏳ (P6)

`GET/POST /applications`, `GET/PATCH /applications/{id}`,
`POST /applications/{id}/outcome`. Status transitions are validated
server-side; `submitted` is only reachable through an approved action.

---

## 11. Evaluations ⏳ (P7)

`GET /evaluations` (runs with metrics), `GET /evaluations/{id}`,
`POST /evaluations` (trigger a suite; admin only).

---

## 12. Status codes

`200` ok · `201` created · `202` accepted (async work started) · `204` no content ·
`400` malformed · `401` unauthenticated · `403` forbidden · `404` not found or
not owned · `409` conflict/idempotency mismatch · `413` payload too large ·
`422` validation failed · `429` rate limited (with `Retry-After`) ·
`500` internal · `503` dependency unavailable.
