# Evaluation Plan

Status: `v0.1` — harness lands in Phase 7, datasets start accumulating in Phase 2
Principle: "the answer looks good" is not a measurement.

---

## 1. What we are actually measuring

The product claim is *decision quality under an objective*, so the metric stack
has four layers, and each one exists to catch a failure the layer above cannot
see:

| Layer | Catches |
|-------|---------|
| Retrieval | The right evidence was never in the context |
| RAG / generation | The evidence was there and the model ignored or distorted it |
| Agent | The right tools/agents were never invoked, or the run looped/failed |
| Opportunity intelligence | Everything worked and the recommendation was still wrong |
| Outcome | The recommendation looked right and reality disagreed |

---

## 2. Datasets

All datasets are versioned files under `ml/datasets/`, referenced by
`evaluation_runs.dataset_version`. Nothing is auto-promoted from production;
promotion is a reviewed pull request.

| Dataset | Size (target) | Built from | Used by |
|---------|---------------|-----------|---------|
| `profile_qa` | 120 Q/A over synthetic + consented real profile docs | hand-authored | retrieval, RAG |
| `opportunity_corpus` | 500 real, legally fetchable postings across ≥ 8 categories | discovery snapshots, frozen | extraction, dedup, ranking |
| `extraction_gold` | 200 postings with hand-labelled fields | annotation of the corpus | extraction, deadline, requirements |
| `eligibility_gold` | 150 (profile, opportunity) pairs with tri-state labels | annotation | qualification |
| `ranking_pairs` | 400 pairwise preferences under a stated objective | expert annotation | ranking correlation |
| `risk_gold` | 120 postings incl. 30 known scams/low-quality | curated | risk detection |
| `injection_suite` | 80 adversarial documents and pages | authored + public corpora | security |
| `agent_traces` | 60 investigations with expected tool/agent sequences | recorded then corrected | agent metrics |
| `outcomes` | grows continuously | `outcomes` table | outcome evaluation |

Annotation rules: two annotators per label, disagreements adjudicated, inter-
annotator agreement (Cohen's κ) reported per dataset. A dataset with κ < 0.7 is
not used as a gate.

---

## 3. Retrieval metrics

Computed over `profile_qa` and `opportunity_corpus` with graded relevance.

| Metric | Gate | Notes |
|--------|------|-------|
| Recall@20 | ≥ 0.90 | before reranking; measures the candidate net |
| Precision@5 | ≥ 0.70 | after reranking |
| MRR | ≥ 0.75 | |
| NDCG@10 | ≥ 0.80 | primary retrieval gate |
| Context precision | ≥ 0.75 | fraction of supplied context actually used |
| Context recall | ≥ 0.85 | fraction of needed context supplied |

Ablations reported every phase: dense-only, lexical-only, hybrid, hybrid+rerank,
hybrid+expansion+rerank. Reranking must justify its latency cost with ≥ 10%
NDCG@10 improvement or it is disabled by configuration.

---

## 4. RAG metrics (RAGAs)

Faithfulness ≥ 0.85 (gate), answer relevance ≥ 0.80, context precision/recall as
above. Faithfulness is the hard gate because an unfaithful recommendation is
worse than no recommendation — it is the metric that detects the system
inventing eligibility or compensation facts.

A judge model is used for these; the judge is pinned by version, and a 40-case
human-scored subset calibrates it each release. Judge/human correlation below
0.7 invalidates the run.

---

## 5. Agent metrics

Computed over `agent_traces` with a `FakeLLMProvider`-free but sandboxed tool
layer.

| Metric | Definition | Gate |
|--------|-----------|------|
| Tool selection accuracy | correct tool chosen at each decision point | ≥ 0.90 |
| Tool argument validity | args validate + semantically correct | ≥ 0.95 / ≥ 0.85 |
| Agent routing accuracy | graph edge taken matches expert edge | ≥ 0.90 |
| Task completion rate | run reaches `report` without fatal error | ≥ 0.95 |
| Loop frequency | runs hitting `max_iterations` | ≤ 0.10 |
| Failure rate | runs ending `failed` | ≤ 0.03 |
| Budget adherence | runs exceeding declared budget | 0 (hard) |
| Graceful degradation | injected source/LLM/vector failures that still produce a report | ≥ 0.90 |

---

## 6. Opportunity-intelligence metrics

These are the custom metrics that make this project a product rather than a
pipeline.

| Metric | Definition | Gate |
|--------|-----------|------|
| Opportunity classification accuracy | predicted `category` vs gold | ≥ 0.92 |
| Deadline extraction accuracy | exact date match, `UNKNOWN` counted correct when gold is absent | ≥ 0.90 |
| Requirement extraction F1 | set F1 over required skills/requirements | ≥ 0.80 |
| Eligibility accuracy | tri-state match | ≥ 0.88 |
| Eligibility false-positive rate | told eligible, actually ineligible | ≤ 0.05 (hard) |
| Risk detection recall | known scams/low-quality flagged | ≥ 0.90 |
| Risk false-positive rate | clean opportunities flagged high-severity | ≤ 0.10 |
| Ranking correlation | Kendall's τ vs expert order under a stated objective | ≥ 0.70 |
| Recommendation accuracy | decision bucket within one step of expert | ≥ 0.85 |
| Noise suppression | fraction of corpus correctly suppressed as `IGNORE`/`LOW_PRIORITY` | ≥ 0.60 with ≤ 0.05 suppression of expert-`PURSUE` items |
| Evidence coverage | high-impact claims with ≥ 1 evidence row | 1.00 (hard) |
| Claim-type discipline | inferences labelled `FACT` | 0 tolerated above 0.02 |

The two hard gates — eligibility false positives and evidence coverage — encode
the product's honesty contract. A release cannot ship with either failing.

### Calibration

Confidence must be calibrated, not decorative. We report Expected Calibration
Error over confidence-bucketed predictions and a reliability diagram; ECE ≤ 0.10
is the gate. Systematic over-confidence triggers a temperature/threshold
recalibration rather than a prompt tweak.

---

## 7. Security evaluation

Run against `injection_suite` each phase from 5 onward:

* Injection success rate (system follows embedded instruction): **0 tolerated**.
* Exfiltration attempts blocked: 100%.
* SSRF probes blocked: 100%.
* Unauthorised tool invocation: 0.
* Quarantine precision (benign content wrongly quarantined) ≤ 0.05.

---

## 8. Outcome evaluation

Once real usage exists, the only metric that ultimately matters:

* Interview rate for `PURSUE`+ recommendations vs the user's baseline.
* Application-to-interview conversion, split by predicted probability bucket —
  this is a direct calibration test of `probability_of_success`.
* Acceptance rate; opportunity success rate.
* Regret analysis: opportunities the system suppressed that the user pursued
  successfully anyway (false suppression) — tracked explicitly because it is the
  most damaging silent failure.

Outcome data is observational and confounded; it is reported with confidence
intervals and never used as a training signal without an explicit dataset
promotion step.

---

## 9. Operational quality metrics

Tracked continuously, alerting on degradation (§22 of the brief): p50/p95
latency per stage, tokens and cost per investigation, structured-output
validation failure rate, tool failure rate per tool, retrieval hit-rate drift,
cache hit rate, and embedding/model version distribution.

---

## 10. Harness and CI

```
ml/evaluation/
  runner.py        # loads dataset version, runs the system under test
  metrics/         # retrieval, rag, agent, opportunity, calibration, security
  reports/         # markdown + json artifacts per run
```

`python -m ml.evaluation.runner --suite retrieval --dataset-version v3`
writes an `evaluation_runs` row and an MLflow run, and emits a markdown diff
against the current baseline.

CI runs a fast subset (≈50 cases, no external network, local small model) on
every PR touching `app/agents`, `app/retrieval`, `app/tools` or `prompts/`.
A gate-metric regression beyond the noise band fails the build. The full suite
runs nightly.

**Noise band**: each gate metric's run-to-run standard deviation is measured
over five identical runs at phase start; a regression must exceed 2σ to count.
This prevents chasing sampling noise while still catching real regressions.

---

## 11. Baselines to beat

Every phase reports against these, so improvement claims are grounded:

1. **Keyword baseline** — BM25 over the corpus, no LLM, sorted by recency.
2. **Prompt-only baseline** — single LLM call with the posting and profile.
3. **RAG baseline** — retrieval + single-call generation, no agents.
4. **Full system**.

If the full system does not beat baseline 3 on ranking correlation and
recommendation accuracy, the added complexity is not yet earning its place —
and that finding gets written down rather than hidden.
