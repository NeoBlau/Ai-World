from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db, rate_limited
from app.core.time import utcnow
from app.models import User
from app.schemas.inputs import LoginIn, RegisterIn
from app.security.auth import create_token, hash_password, verify_password
from app.security.rate_limit import hit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": u.role}


@router.post("/register", dependencies=[Depends(rate_limited)])
async def register(body: RegisterIn, session: AsyncSession = Depends(db)) -> dict:
    email = body.email.lower()
    if (await session.execute(select(User.id).where(func.lower(User.email) == email))).first():
        raise HTTPException(409, "email already registered")
    user = User(email=email, display_name=body.display_name, password_hash=hash_password(body.password), role="user", created_at=utcnow())
    session.add(user)
    await session.commit()
    return {"token": create_token(user.id, user.role), "user": user_out(user)}


@router.post("/login", dependencies=[Depends(rate_limited)])
async def login(body: LoginIn, session: AsyncSession = Depends(db)) -> dict:
    email = body.email.lower()
    if not await hit(f"login:{email}", 10, 300):
        raise HTTPException(429, "too many attempts, try again later")
    user = (await session.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid email or password")
    user.last_seen_at = utcnow()
    await session.commit()
    return {"token": create_token(user.id, user.role), "user": user_out(user)}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)
