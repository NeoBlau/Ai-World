"""Self-government: laws voted on by residents and actions they invented. Admins keep a veto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, db
from app.api.routes.common import agent_names, parse_uuid
from app.core.config import get_settings
from app.governance.service import GovernanceService
from app.models import CustomAction, LawVote, WorldLaw
from app.world import event_bus

router = APIRouter(prefix="/api/governance", tags=["governance"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


@router.get("/laws")
async def list_laws(status: str | None = Query(None, pattern="^(proposed|adopted|rejected|repealed)$"), limit: int = Query(100, ge=1, le=300),
                    session: AsyncSession = Depends(db)) -> dict:
    q = select(WorldLaw)
    if status:
        q = q.where(WorldLaw.status == status)
    laws = list((await session.execute(q.order_by(WorldLaw.created_at.desc()).limit(limit))).scalars())
    votes = list((await session.execute(select(LawVote).where(LawVote.law_id.in_([x.id for x in laws])).order_by(LawVote.created_at)))
                 .scalars()) if laws else []
    names = await agent_names(session, {x.proposer_agent_id for x in laws} | {v.agent_id for v in votes})
    by_law: dict = {}
    for v in votes:
        by_law.setdefault(v.law_id, []).append({"agent": names.get(v.agent_id), "support": v.support, "reason": v.reason})
    return {
        "min_votes": get_settings().law_min_votes,
        "laws": [{"id": str(x.id), "title": x.title, "text": x.text, "status": x.status, "proposer": names.get(x.proposer_agent_id),
                  "votes_for": x.votes_for, "votes_against": x.votes_against, "created_at": _iso(x.created_at), "decided_at": _iso(x.decided_at),
                  "votes": by_law.get(x.id, [])} for x in laws],
    }


@router.get("/actions")
async def list_actions(session: AsyncSession = Depends(db)) -> list[dict]:
    rows = list((await session.execute(select(CustomAction).order_by(CustomAction.created_at.desc()).limit(300))).scalars())
    names = await agent_names(session, {a.creator_agent_id for a in rows})
    return [{"id": str(a.id), "name": a.name, "description": a.description, "creator": names.get(a.creator_agent_id), "uses": a.uses,
             "active": a.active, "room_only": a.room_id is not None, "created_at": _iso(a.created_at)} for a in rows]


@router.post("/laws/{law_id}/repeal", dependencies=[Depends(admin_user)])
async def repeal_law(law_id: str, session: AsyncSession = Depends(db)) -> dict:
    law = await session.get(WorldLaw, parse_uuid(law_id, "law"))
    if law is None:
        raise HTTPException(404, "law not found")
    await GovernanceService(session).repeal(law, by="admin veto")
    await event_bus.commit(session)
    return {"id": str(law.id), "status": law.status}


@router.post("/actions/{action_id}/active", dependencies=[Depends(admin_user)])
async def set_action_active(action_id: str, active: bool = True, session: AsyncSession = Depends(db)) -> dict:
    action = await session.get(CustomAction, parse_uuid(action_id, "action"))
    if action is None:
        raise HTTPException(404, "action not found")
    action.active = active
    await event_bus.commit(session)
    return {"id": str(action.id), "active": action.active}
