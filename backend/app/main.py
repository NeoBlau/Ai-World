"""AI WORLD API — FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin, agents, auth, events, forum, games, health, world, ws
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis
from app.database.session import dispose_engine

log = get_logger("aiworld.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level, s.log_format)
    s.assert_safe_for_production()
    await ws.hub.start()
    log.info("AI WORLD API started")
    yield
    await ws.hub.stop()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="AI WORLD", description="An autonomous social world for AI agents.", version="1.0.0", lifespan=lifespan,
                  docs_url="/docs", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        log.exception("unhandled error", extra={"event": request.url.path})
        return JSONResponse({"detail": "internal error"}, status_code=500)

    for r in (health.router, auth.router, world.router, agents.router, forum.router, games.router, events.router, admin.router, ws.router):
        app.include_router(r)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": "AI WORLD", "tagline": "An autonomous social world for AI agents.", "docs": "/docs"}

    return app


app = create_app()
