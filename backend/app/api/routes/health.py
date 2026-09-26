from __future__ import annotations

import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.redis import get_redis
from app.database.session import get_engine
from app.llm.router import get_router

router = APIRouter(tags=["health"])
_provider_cache: dict = {"at": 0.0, "data": []}


@router.get("/health")
async def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Readiness: database, redis, LLM providers."""
    checks: dict = {}
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            ext = (await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))).scalar()
        checks["database"] = {"ok": True, "pgvector": ext}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": type(exc).__name__}
    try:
        r = get_redis()
        await r.ping()
        workers = [k async for k in r.scan_iter("aiworld:worker:*")]
        checks["redis"] = {"ok": True, "workers": len(workers)}
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"ok": False, "error": type(exc).__name__}
    if time.time() - _provider_cache["at"] > 60:
        try:
            _provider_cache["data"] = await get_router().health()
        except Exception:  # noqa: BLE001
            _provider_cache["data"] = []
        _provider_cache["at"] = time.time()
    checks["llm_providers"] = _provider_cache["data"]
    ok = checks["database"]["ok"] and checks["redis"]["ok"]
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


@router.get("/api/providers", tags=["providers"])
async def providers_public() -> list[dict]:
    """Which providers are configured (never exposes keys)."""
    if time.time() - _provider_cache["at"] > 60:
        _provider_cache["data"] = await get_router().health()
        _provider_cache["at"] = time.time()
    return _provider_cache["data"]
