"""Ops endpoints (OBS-1, OBS-2): /healthz, /readyz, /metrics."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.logging import get_logger
from app.core.metrics import metrics

router = APIRouter(tags=["ops"])
log = get_logger("health")

CheckStatus = Literal["ok", "error", "not_configured"]
CHECK_TIMEOUT_S = 5.0


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness. Instant: touches no database and no Redis (Render health check, wake ping)."""
    return HealthResponse()


async def _check_db(request: Request) -> CheckStatus:
    engine = request.app.state.db_engine
    if engine is None:
        return "not_configured"
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        return "ok"
    except Exception as exc:  # report, never crash the probe
        log.warning("readyz_db_failed", error_type=type(exc).__name__)
        return "error"


async def _check_redis(request: Request) -> CheckStatus:
    redis = request.app.state.redis
    if redis is None:
        return "not_configured"
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            await redis.ping()
        return "ok"
    except Exception as exc:
        log.warning("readyz_redis_failed", error_type=type(exc).__name__)
        return "error"


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(request: Request) -> Response:
    """Readiness. Checks the database and Redis only when they are configured."""
    db, redis = await asyncio.gather(_check_db(request), _check_redis(request))
    checks: dict[str, CheckStatus] = {"database": db, "redis": redis}
    healthy = all(value != "error" for value in checks.values())
    body = ReadyResponse(status="ok" if healthy else "degraded", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if healthy else 503)


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> str:
    return metrics.render()
