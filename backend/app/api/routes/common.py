"""Small query helpers shared by routes."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Room, User


async def rooms_map(session: AsyncSession) -> dict[uuid.UUID, Room]:
    return {r.id: r for r in (await session.execute(select(Room))).scalars()}


async def agent_names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {a.id: a.name for a in (await session.execute(select(Agent).where(Agent.id.in_(ids)))).scalars().unique()}


async def user_names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.display_name for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars()}


async def get_agent_or_404(session: AsyncSession, ref: str) -> Agent:
    agent = None
    try:
        agent = await session.get(Agent, uuid.UUID(ref))
    except ValueError:
        agent = (await session.execute(select(Agent).where(Agent.slug == ref.lower()))).scalars().first()
    if agent is None:
        raise HTTPException(404, "agent not found")
    return agent


async def get_room_or_404(session: AsyncSession, ref: str) -> Room:
    from app.rooms.service import RoomService

    room = await RoomService(session).resolve(ref)
    if room is None:
        raise HTTPException(404, "room not found")
    return room


def parse_uuid(value: str, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(404, f"{what} not found") from exc
