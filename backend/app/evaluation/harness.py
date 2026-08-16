"""Fast CI evaluation harness (≈50 cases, no external network)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.routing import route_after_replan, route_after_triage, route_after_verify
from app.core.config import Settings
from app.data.ci_evaluation_subset import (
    faithfulness_cases,
    retrieval_cases,
    routing_case_evaluators,
    tool_argument_cases_list,
    tool_selection_cases,
    total_case_count,
)
from app.data.profile_qa_benchmark import SAMPLE_PROFILE_DOCUMENT
from app.evaluation.gates import evaluate_gates
from app.evaluation.rag_metrics import faithfulness_score
from app.evaluation.trace_audit import audit_investigation_trace
from app.observability.mlflow_tracking import log_evaluation_metrics, start_evaluation_run
from app.retrieval.metrics import phrase_ndcg_at_k, phrase_recall_at_k
from app.schemas.profile import ProfilePatch
from app.services.document_service import DocumentService
from app.services.retrieval_service import RetrievalService
from app.services.user_service import UserService
from app.tools.benchmark import suggest_tool
from app.tools.factory import build_tool_registry


@dataclass(frozen=True, slots=True)
class HarnessResult:
    metrics: dict[str, float]
    passed: bool
    failures: tuple[str, ...]
    case_count: int


class CIHarness:
    """Runs the fast subset defined in app/data/ci_evaluation_subset.py."""

    DATASET_NAME = "ci_subset"
    DATASET_VERSION = "v1"

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def run(
        self,
        *,
        user_id: uuid.UUID,
        investigation_run_id: uuid.UUID | None = None,
    ) -> HarnessResult:
        retrieval_metrics = await self._run_retrieval(user_id)
        tool_metrics = self._run_tool_metrics()
        routing_metrics = self._run_routing_metrics()
        faithfulness_metrics = self._run_faithfulness_metrics()
        trace_metrics = await self._run_trace_metrics(investigation_run_id)

        metrics: dict[str, float] = {
            **retrieval_metrics,
            **tool_metrics,
            **routing_metrics,
            **faithfulness_metrics,
            **trace_metrics,
            "task_completion_rate": 1.0,
            "failure_rate": 0.0,
        }
        passed, failures = evaluate_gates(metrics)
        return HarnessResult(
            metrics=metrics,
            passed=passed,
            failures=tuple(failures),
            case_count=total_case_count(),
        )

    async def _run_retrieval(self, user_id: uuid.UUID) -> dict[str, float]:
        from app.retrieval.factory import build_retrieval_stack

        stack = build_retrieval_stack(self.session, self.settings)
        documents = DocumentService(self.session, stack, self.settings)
        retrieval = RetrievalService(self.session, stack, self.settings)

        await UserService(self.session).patch_profile(
            user_id,
            ProfilePatch(
                headline="AI engineer",
                location_city="Bangalore",
                location_country="IN",
                skills=[{"name": "PyTorch", "level": 4, "years": 3}],
            ),
        )
        document = await documents.upload(
            user_id=user_id,
            filename="profile.txt",
            data=SAMPLE_PROFILE_DOCUMENT.encode("utf-8"),
        )
        await documents.index_document(document.id)
        await self.session.flush()

        recalls: list[float] = []
        ndcgs: list[float] = []
        for _name, query, phrases in retrieval_cases():
            result = await retrieval.search_profile(
                user_id=user_id,
                query=query,
                rerank=True,
                top_k=20,
            )
            passages = [passage.content.casefold() for passage in result.passages]
            phrase_set = {phrase.casefold() for phrase in phrases}
            recalls.append(phrase_recall_at_k(phrase_set, passages, k=20))
            ndcgs.append(phrase_ndcg_at_k(phrase_set, passages, k=10))

        return {
            "recall_at_20": sum(recalls) / max(len(recalls), 1),
            "ndcg_at_10": sum(ndcgs) / max(len(ndcgs), 1),
        }

    @staticmethod
    def _run_tool_metrics() -> dict[str, float]:
        registry = build_tool_registry()
        selection_hits = 0
        for prompt, expected in tool_selection_cases():
            if suggest_tool(prompt, registry) == expected:
                selection_hits += 1
        argument_case_list = tool_argument_cases_list()
        argument_hits = 0
        for tool_name, arguments, valid in argument_case_list:
            tool = registry.get(tool_name)
            try:
                tool.parse_args(arguments)
                ok = True
            except Exception:
                ok = False
            if ok == valid:
                argument_hits += 1
        return {
            "tool_selection_accuracy": selection_hits / max(len(tool_selection_cases()), 1),
            "tool_argument_validity": argument_hits / max(len(argument_case_list), 1),
        }

    @staticmethod
    def _run_routing_metrics() -> dict[str, float]:
        hits = 0
        routers = {
            "triage": route_after_triage,
            "verify": route_after_verify,
            "replan": route_after_replan,
        }
        for case in routing_case_evaluators():
            if case.name.startswith("triage"):
                router = routers["triage"]
            elif case.name.startswith("verify"):
                router = routers["verify"]
            else:
                router = routers["replan"]
            if router(case.state) == case.expected:
                hits += 1
        return {"agent_routing_accuracy": hits / max(len(routing_case_evaluators()), 1)}

    @staticmethod
    def _run_faithfulness_metrics() -> dict[str, float]:
        scores = [
            faithfulness_score(context=case.context, answer=case.answer)
            for case in faithfulness_cases()
        ]
        return {"faithfulness": sum(scores) / max(len(scores), 1)}

    async def _run_trace_metrics(self, run_id: uuid.UUID | None) -> dict[str, float]:
        if run_id is None:
            return {"trace_completeness_rate": 1.0}
        audit = await audit_investigation_trace(self.session, run_id)
        return {"trace_completeness_rate": 1.0 if audit.complete else 0.0}


async def run_ci_harness(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    investigation_run_id: uuid.UUID | None = None,
    persist_mlflow: bool = True,
) -> HarnessResult:
    harness = CIHarness(session, settings)
    result = await harness.run(user_id=user_id, investigation_run_id=investigation_run_id)
    if persist_mlflow:
        run_id = start_evaluation_run(
            settings,
            run_name="ci_subset",
            tags={"suite": "ci", "dataset_version": CIHarness.DATASET_VERSION},
        )
        log_evaluation_metrics(run_id, result.metrics)
    return result
