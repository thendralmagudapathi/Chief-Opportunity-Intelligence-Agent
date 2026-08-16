# Agent Design

Status: `v0.1` — design frozen, implementation lands in Phases 4–6
Orchestration: LangGraph (explicit state machine, no free-running loops)

---

## 1. Why a graph and not an agent loop

A single "agent with tools" loop fails this problem in three specific ways:
it cannot bound cost, it cannot be evaluated per-capability, and it cannot
express *adversarial* steps (a contrarian pass that is required to run even when
the optimistic path is confident). So the system is a supervised graph of narrow
agents, each with a typed contract, executed under an explicit budget.

Every agent is defined by an `AgentCard` — identity, capabilities, input schema,
output schema, cost class, side-effect class. This is the same shape A2A needs
(§15), so promoting an agent to a remote service later is a transport change,
not a redesign.

```python
class AgentCard(BaseModel):
    name: str
    version: str
    description: str
    capabilities: list[str]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    cost_class: Literal["small", "standard", "reasoning"]
    side_effects: Literal["none", "internal_write", "external"]
    max_attempts: int = 2
    timeout_s: float = 60.0
```

---

## 2. Graph topology

```
                        ┌──────────────┐
                        │  understand  │  objective → InvestigationPlan
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │ load_context │  profile RAG + active goals + memory
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │  plan        │  supervisor: which agents, which budget
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │  discover    │  parallel over sources (fan-out/in)
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │  normalize   │  extract → validate → dedupe → persist
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │  triage      │  cheap deterministic prefilter → top-M
                        └──────┬───────┘
                               ▼
        ┌──────────────────────┴───────────────────────┐
        │           per-candidate subgraph (parallel)  │
        │  research → qualify → match → risk           │
        └──────────────────────┬───────────────────────┘
                               ▼
                        ┌──────────────┐
                        │  contrarian  │  runs on the current top-N, always
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │  verify      │  high-impact claims only
                        └──────┬───────┘
                     ┌─────────┴─────────┐
          needs_more │                   │ sufficient
                     ▼                   ▼
              ┌────────────┐      ┌──────────────┐
              │  replan    │      │  score       │  deterministic engine
              │ (bounded)  │      └──────┬───────┘
              └─────┬──────┘             ▼
                    │              ┌──────────────┐
                    └─────────────▶│  decide      │  recommendation + reasons
                                   └──────┬───────┘
                                          ▼
                                   ┌──────────────┐
                                   │  act (draft) │  artifacts only
                                   └──────┬───────┘
                                          ▼
                                   ┌──────────────┐
                                   │ human_gate   │  interrupt() if external
                                   └──────┬───────┘
                                          ▼
                                   ┌──────────────┐
                                   │  report      │  FinalOpportunityReport
                                   └──────────────┘
```

Routing rules are pure functions over state — no LLM decides control flow
without its decision being validated against an enum:

| Edge | Condition |
|------|-----------|
| `triage → subgraph` | `len(candidates) > 0` else → `report(empty)` |
| `verify → replan` | `unresolved_high_impact_claims > 0 and iterations < max_iterations and budget_remaining` |
| `replan → discover` | plan requests new sources |
| `replan → research` | plan requests deeper research on existing candidates |
| `verify → score` | otherwise (including budget exhaustion, with `degraded=true`) |
| `act → human_gate` | `action.side_effects == "external"` |

`max_iterations` defaults to 3. The replan edge is the only cycle in the graph.

---

## 3. Shared state

```python
class InvestigationState(TypedDict, total=False):
    # immutable inputs
    run_id: UUID
    trace_id: str
    user_id: UUID
    objective: str
    goals: list[GoalRef]

    # derived
    plan: InvestigationPlan
    profile_context: list[RetrievedChunk]
    search_strategy: SearchStrategy

    # working set
    candidates: list[OpportunityRef]          # after dedupe
    findings: dict[UUID, ResearchDossier]     # per opportunity
    eligibility: dict[UUID, EligibilityAssessment]
    matches: dict[UUID, ProfileMatch]
    risks: dict[UUID, RiskAssessment]
    counterpoints: dict[UUID, ContrarianAnalysis]
    evidence: list[EvidenceItem]

    # outputs
    scores: dict[UUID, ScoreResult]
    decisions: dict[UUID, AgentDecision]
    report: FinalOpportunityReport | None

    # control
    iterations: int
    budget: Budget            # tool calls, tokens, wall clock, usd
    errors: list[AgentError]
    degraded: bool
    pending_approval: ApprovalRequest | None
```

State is checkpointed to Postgres per node (LangGraph `AsyncPostgresSaver`), so
a crashed worker resumes at the last committed node and a human-gate interrupt
can survive a restart.

Reducers: `evidence` and `errors` append; `findings`/`eligibility`/`matches`
merge by opportunity id; scalar control fields last-write-wins. Parallel
per-candidate branches therefore never conflict.

---

## 4. Agents

Each agent below lists: purpose · input → output · model tier · failure mode.

### Supervisor
Owns `understand`, `plan`, `replan`, budget accounting and termination.
`ObjectiveRequest → InvestigationPlan` (which agents, which sources, how many
candidates, budget split, stop conditions). Reasoning tier. On failure the run
aborts with a structured error — there is no "try anyway" path.

The supervisor is *not* allowed to call tools directly. It only produces plans.
This keeps its evaluation tractable (plan quality) and prevents it becoming a
god-agent.

### Discovery Agent
`SearchStrategy → list[RawCandidate]`. Generates and expands queries per source,
calls `OpportunitySource.search()/fetch()`, extracts candidates. Small/extraction
tier. Per-source circuit breaker; a dead source degrades the run, never fails it.

### Extraction (inside `normalize`, not a conversational agent)
`RawCandidate → OpportunityExtraction` under constrained decoding. This is the
single highest-volume LLM call in the system and the first fine-tuning target
(Phase 8). Validation failure → repair pass → drop candidate with a logged
reason.

### Research Agent
`OpportunityRef + ResearchQuestions → ResearchDossier`. Investigates
organisation, funding, reputation, market, competition. Uses `search_web`,
`research_company`, and RAG over previously gathered evidence. Reasoning tier,
budget-capped at *k* tool calls per candidate. Emits evidence rows for every
non-trivial claim.

### Qualification Agent
`Opportunity + Profile → EligibilityAssessment` — hard requirements only:
location, work authorisation, experience floor, education, technical
prerequisites, financial requirements, deadline validity, application
requirements, and `missing_requirements`. Output is tri-state per requirement
(`met` / `not_met` / `unknown`) with the evidence id that decided it. A single
`not_met` hard requirement forces `INELIGIBLE` downstream regardless of score —
that rule lives in the decision service, not the prompt.

### Profile Matching Agent
`Opportunity + profile RAG → ProfileMatch`: matched skills, gaps, transferable
evidence, seniority delta, and a per-dimension rationale. Retrieval is scoped to
the requesting user at the SQL level. Emits *factors*, not a score.

### Risk Agent
`Opportunity + dossier → RiskAssessment`: red flags, scam indicators,
unrealistic claims, hidden costs, competition intensity, eligibility
uncertainty, time/financial/reputation risk. Any finding at severity ≥ `high`
must cite an evidence id or it is downgraded automatically.

### Contrarian Agent
Runs on the current top-N, unconditionally. Prompted against the accumulated
positive case: "what contradicts this, what assumption is load-bearing and
weak, what is the opportunity cost, what would have to be true?" Output
`ContrarianAnalysis` with `contradicting_evidence`, `weak_assumptions`,
`failure_modes`, `opportunity_cost`, `verdict_pressure ∈ [0,1]`. Its output
feeds the score as a penalty factor and is shown in the UI as "the case against".

### Verification Agent
Selects high-impact claims (those that move a score dimension by more than a
threshold, or that support a `STRONGLY PURSUE`) and independently re-checks
them. Assigns `claim_type ∈ {FACT, INFERENCE, ESTIMATE, ASSUMPTION, UNKNOWN}`
and a calibrated confidence. Conflicting sources produce two evidence rows and a
confidence penalty — never a silent pick.

### Scoring (deterministic engine, not an agent)
`OpportunityScoreFactors + Weights → ScoreResult`. Pure function, no I/O, unit
tested with property tests (monotonicity in each dimension, bounded output,
weight-normalisation invariance). The LLM's only contribution is the factor
values and their evidence.

### Decision Agent
`ScoreResult + eligibility + risk + contrarian → AgentDecision` with
`recommendation ∈ {STRONGLY_PURSUE, PURSUE, CONSIDER, WAIT, LOW_PRIORITY,
IGNORE, INELIGIBLE}`, ranked reasons, and the explainability payload
(WHY THIS / WHY NOW / WHY ME / WHAT COULD GO WRONG / SUPPORTING /
CONTRADICTING / MISSING / NEXT STEP). Hard gates applied deterministically
before the LLM sees the case: ineligible → `INELIGIBLE`; expired → `IGNORE`;
confidence below floor → capped at `CONSIDER`.

### Action Agent
Produces artifacts only: application drafts, outreach drafts, document
checklists, prepared forms, follow-up tasks. Every artifact is stored on
`applications.artifacts`. Anything with an external effect emits an
`ApprovalRequest` and the graph interrupts.

---

## 5. Human-in-the-loop

The `human_gate` node uses LangGraph's `interrupt()`. The run persists as
`awaiting_approval`; the API exposes the pending request with ACTION, REASON,
EVIDENCE, RISK, EXPECTED OUTCOME; the user replies `approve` / `reject` /
`edit`, and the graph resumes from the checkpoint. Approval requests carry an
idempotency key so a double-approve cannot double-send.

Actions requiring approval: submitting applications, sending outreach or email,
spending money, sharing private documents externally, and any tool whose
`side_effects` class is `external`.

---

## 6. Cost control

`Budget` is part of state and decremented by the tool layer, not by the agents:

```
max_tool_calls_total, max_tool_calls_per_candidate,
max_llm_calls, max_input_tokens, max_output_tokens,
max_wall_clock_s, max_cost_usd, max_iterations
```

Early stopping: when *k* independent sources agree on a claim above a confidence
threshold, further verification of that claim is skipped. When the marginal
candidate's optimistic score ceiling cannot enter the top-N, its research
subgraph is pruned before it runs. Budget exhaustion is a normal termination
path that produces a report flagged `degraded`, not an exception.

---

## 7. Prompt management

Prompts live in `prompts/<agent>/<name>.vN.md` with YAML front-matter
(`version`, `model_tier`, `output_schema`, `changelog`). They are loaded through
`PromptRegistry`, which records the resolved version on every `agent_tasks` row
and OTel span, so an evaluation result can always be attributed to an exact
prompt version. No prompt strings in Python source.

---

## 8. Prompt-injection posture inside the graph

Retrieved page content, opportunity descriptions and uploaded documents enter
prompts only through `render_external(content, source)`, which wraps them in a
labelled, non-instruction block and prefixes the standing rule that the enclosed
text is data. Additionally:

* An injection classifier flags candidate content; flagged content is quarantined
  and summarised by a small model in a separate context before use.
* Tool invocation arguments derived from external content are re-validated
  against the tool schema and the SSRF/domain allowlist.
* The Action Agent may never target a recipient that appeared only in external
  content.

See [`SECURITY_MODEL.md`](./SECURITY_MODEL.md).

---

## 9. Testability contract

Because every agent is `(typed input) -> (typed output)` with injected
providers, each is testable in isolation with a `FakeLLMProvider` returning
canned structured outputs. Graph-level tests assert routing decisions, retry
behaviour, iteration ceilings, budget exhaustion, malicious-input handling and
resumption after an interrupt — without a live model. See
[`EVALUATION_PLAN.md`](./EVALUATION_PLAN.md) §Agent.
