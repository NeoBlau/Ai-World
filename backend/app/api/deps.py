"""FastAPI dependencies: DB session, current user, admin guard, rate limiting."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import get_sessionmaker
from app.models import User
from app.security.auth import decode_token
from app.security.rate_limit import hit

bearer = HTTPBearer(auto_error=False)


async def db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def optional_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), session: AsyncSession = Depends(db)) -> User | None:
    if creds is None:
        return None
    payload = decode_token(creds.credentials)
    if not payload:
        return None
    try:
        user = await session.get(User, uuid.UUID(payload["sub"]))
    except (KeyError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required", headers={"WWW-Authenticate": "Bearer"})
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def rate_limited(request: Request) -> None:
    """Per-IP limit for write endpoints."""
    limit = get_settings().api_rate_limit_per_minute
    if not await hit(f"api:{client_ip(request)}", limit, 60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")


async def chat_rate_limited(request: Request, user: User = Depends(current_user)) -> None:
    """LLM-backed endpoints are expensive: stricter per-user limit."""
    if not await hit(f"chat:{user.id}", 12, 60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "slow down — too many messages")
