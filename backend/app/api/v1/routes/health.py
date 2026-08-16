"""Liveness, readiness and build information.

Liveness never touches a dependency: a slow database must not cause the
orchestrator to kill an otherwise healthy process. Readiness does the opposite.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep
from app.core.logging import get_logger
from app.schemas.common import HealthCheck, HealthResponse, ServiceInfo

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


@router.get("/live", response_model=HealthResponse, summary="Liveness probe")
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def ready(session: SessionDep, settings: SettingsDep, response: Response) -> HealthResponse:
    checks: list[HealthCheck] = []

    started = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
        checks.append(
            HealthCheck(
                name="database",
                status="ok",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        )
    except Exception as exc:
        logger.error("readiness_database_failed", exc_info=exc)
        checks.append(HealthCheck(name="database", status="error", detail="unreachable"))

    if settings.redis.enabled:
        checks.append(await _check_redis(settings.redis.url))

    overall = "ok" if all(c.status == "ok" for c in checks) else "error"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status=overall, checks=checks)


async def _check_redis(url: str) -> HealthCheck:
    started = time.perf_counter()
    try:
        import redis.asyncio as redis

        client = redis.from_url(url, socket_connect_timeout=2)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return HealthCheck(
            name="redis", status="ok", latency_ms=round((time.perf_counter() - started) * 1000, 2)
        )
    except Exception as exc:
        logger.error("readiness_redis_failed", exc_info=exc)
        return HealthCheck(name="redis", status="error", detail="unreachable")


@router.get("/info", response_model=ServiceInfo, summary="Build information")
async def info(settings: SettingsDep) -> ServiceInfo:
    return ServiceInfo(
        name=settings.project_name,
        version=settings.version,
        environment=str(settings.environment),
        git_sha=settings.git_sha,
    )
