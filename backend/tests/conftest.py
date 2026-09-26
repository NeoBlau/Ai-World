"""Test fixtures: real PostgreSQL (+pgvector) for SQL fidelity, fakeredis for Redis."""

from __future__ import annotations

import os

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+asyncpg://aiworld:aiworld@localhost:5432/aiworld_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OLLAMA_BASE_URL"):
    os.environ[key] = ""
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LOG_FORMAT"] = "text"
os.environ["ENVIRONMENT"] = "test"

import fakeredis  # noqa: E402
import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.redis import set_redis  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import configure_engine, get_engine, get_sessionmaker  # noqa: E402
from app.llm import embeddings as emb_mod  # noqa: E402
from app.llm import router as router_mod  # noqa: E402
from app.world.clock import reset_clock_cache  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    configure_engine(os.environ["TEST_DATABASE_URL"])
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.attributes["database_url"] = os.environ["TEST_DATABASE_URL"]
    async with get_engine().begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await get_engine().dispose()
    import asyncio

    await asyncio.to_thread(command.upgrade, cfg, "head")
    configure_engine(os.environ["TEST_DATABASE_URL"])
    yield
    await get_engine().dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    set_redis(redis)
    router_mod.set_router(None)
    emb_mod._service = None
    reset_clock_cache()
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))
    yield redis
    await redis.aclose()
    set_redis(None)


@pytest_asyncio.fixture
async def session():
    async with get_sessionmaker()() as s:
        yield s


@pytest_asyncio.fixture
async def world(session):
    from app.world.seed import seed

    await seed(session)
    return session


@pytest_asyncio.fixture
async def client():
    from app.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: httpx.AsyncClient, email: str = "admin@aiworld.local", password: str = "change-me-admin") -> dict:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def register(client: httpx.AsyncClient, email: str = "human@example.com", name: str = "Human") -> dict:
    r = await client.post("/api/auth/register", json={"email": email, "password": "password123", "display_name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def get_agent(session, slug: str):
    from sqlalchemy import select

    from app.models import Agent

    return (await session.execute(select(Agent).where(Agent.slug == slug))).scalars().first()
