"""Evaluation run endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentSuperuser, CurrentUser, SessionDep, SettingsDep
from app.evaluation.harness import CIHarness, run_ci_harness
from app.evaluation.service import EvaluationService
from app.schemas.evaluation import (
    EvaluationRunListResponse,
    EvaluationRunRead,
    EvaluationTriggerRequest,
    EvaluationTriggerResponse,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("", response_model=EvaluationRunListResponse, summary="List evaluation runs")
async def list_evaluations(
    user: CurrentUser,
    session: SessionDep,
) -> EvaluationRunListResponse:
    del user
    rows = await EvaluationService(session).list_runs()
    return EvaluationRunListResponse(items=[EvaluationRunRead.model_validate(row) for row in rows])


@router.get("/{run_id}", response_model=EvaluationRunRead, summary="Get an evaluation run")
async def get_evaluation(
    run_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> EvaluationRunRead:
    del user
    row = await EvaluationService(session).get_run(run_id)
    return EvaluationRunRead.model_validate(row)


@router.post(
    "",
    response_model=EvaluationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an evaluation suite (admin only)",
)
async def trigger_evaluation(
    payload: EvaluationTriggerRequest,
    admin: CurrentSuperuser,
    session: SessionDep,
    settings: SettingsDep,
) -> EvaluationTriggerResponse:
    service = EvaluationService(session)
    row = await service.create_run(
        name=f"{payload.suite}_{payload.dataset_version}",
        suite=payload.suite,
        dataset_name=CIHarness.DATASET_NAME,
        dataset_version=payload.dataset_version,
        git_sha=settings.git_sha,
        config={"triggered_by": str(admin.id)},
    )
    await service.mark_running(row)
    result = await run_ci_harness(
        session,
        settings,
        user_id=admin.id,
        persist_mlflow=True,
    )
    notes = None if result.passed else "; ".join(result.failures)
    status_label = "passed" if result.passed else "failed"
    await service.mark_succeeded(row, dict(result.metrics), notes=notes or status_label)
    await session.commit()
    return EvaluationTriggerResponse(
        run_id=row.id,
        passed=result.passed,
        metrics=result.metrics,
        failures=list(result.failures),
    )
