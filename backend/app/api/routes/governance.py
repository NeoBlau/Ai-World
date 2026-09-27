"""Self-government: laws voted on by residents and actions they invented. Admins keep a veto."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, db
from app.api.routes.common import agent_names, parse_uuid
from app.core.config import get_settings
from app.core.time import utcnow
from app.governance.service import GovernanceService
from app.models import Book, CustomAction, CustomGame, CustomMatch, Item, LawVote, Topic, WorldLaw
from app.world import event_bus

router = APIRouter(prefix="/api/governance", tags=["governance"])
log = logging.getLogger("aiworld.admin")


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
        by_law.setdefault(v.law_id, []).append({"agent": names.get(v.agent_id), "agent_id": str(v.agent_id), "support": v.support,
                                                "reason": v.reason})
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
             "active": a.active, "room_only": a.room_id is not None, "created_at": _iso(a.created_at),
             "function": bool(a.steps), "steps": a.steps, "version": a.version} for a in rows]


@router.post("/laws/{law_id}/repeal", dependencies=[Depends(admin_user)])
async def repeal_law(law_id: str, session: AsyncSession = Depends(db)) -> dict:
    law = await session.get(WorldLaw, parse_uuid(law_id, "law"))
    if law is None:
        raise HTTPException(404, "law not found")
    await GovernanceService(session).repeal(law, by="admin veto")
    await event_bus.commit(session)
    return {"id": str(law.id), "status": law.status}


class AdminVotes(BaseModel):
    for_delta: int = Field(0, ge=-1000, le=1000)
    against_delta: int = Field(0, ge=-1000, le=1000)
    decide: bool = True  # apply the usual rule (enough votes -> adopted/rejected) after the change


@router.post("/laws/{law_id}/admin-votes", dependencies=[Depends(admin_user)])
async def admin_adjust_votes(law_id: str, body: AdminVotes, session: AsyncSession = Depends(db)) -> dict:
    """Admin: add or remove votes on a law without a voter (the list of residents' votes is not changed)."""
    law = await session.get(WorldLaw, parse_uuid(law_id, "law"))
    if law is None:
        raise HTTPException(404, "law not found")
    law.votes_for = max(0, law.votes_for + body.for_delta)
    law.votes_against = max(0, law.votes_against + body.against_delta)
    if body.decide and law.status == "proposed":
        await GovernanceService(session)._maybe_decide(law)
    log.warning("admin changed law votes", extra={"law_id": str(law.id), "for_delta": body.for_delta, "against_delta": body.against_delta})
    await event_bus.commit(session)
    return {"id": str(law.id), "status": law.status, "votes_for": law.votes_for, "votes_against": law.votes_against}


@router.delete("/laws/{law_id}/votes/{agent_id}", dependencies=[Depends(admin_user)])
async def admin_remove_vote(law_id: str, agent_id: str, session: AsyncSession = Depends(db)) -> dict:
    """Admin: delete one resident's vote and take it off the count."""
    law = await session.get(WorldLaw, parse_uuid(law_id, "law"))
    if law is None:
        raise HTTPException(404, "law not found")
    vote = (await session.execute(select(LawVote).where(LawVote.law_id == law.id, LawVote.agent_id == parse_uuid(agent_id, "agent")))).scalars().first()
    if vote is None:
        raise HTTPException(404, "vote not found")
    if vote.support:
        law.votes_for = max(0, law.votes_for - 1)
    else:
        law.votes_against = max(0, law.votes_against - 1)
    await session.delete(vote)
    log.warning("admin removed a law vote", extra={"law_id": str(law.id), "agent_id": agent_id})
    await event_bus.commit(session)
    return {"id": str(law.id), "status": law.status, "votes_for": law.votes_for, "votes_against": law.votes_against}


class AdminLawStatus(BaseModel):
    status: str = Field(pattern="^(proposed|adopted|rejected)$")


@router.post("/laws/{law_id}/admin-status", dependencies=[Depends(admin_user)])
async def admin_set_law_status(law_id: str, body: AdminLawStatus, session: AsyncSession = Depends(db)) -> dict:
    """Admin: force a law into force, reject it, or reopen the vote. The world sees the same notice as for a normal decision."""
    law = await session.get(WorldLaw, parse_uuid(law_id, "law"))
    if law is None:
        raise HTTPException(404, "law not found")
    law.status = body.status
    law.decided_at = None if body.status == "proposed" else utcnow()
    if body.status in ("adopted", "rejected"):
        verb = "adopted a law" if body.status == "adopted" else "rejected the law"
        await event_bus.emit(session, f"law.{body.status}", summary=f"The residents {verb}: «{law.title}» ({law.votes_for}:{law.votes_against}).",
                             payload={"law_id": str(law.id), "title": law.title, "text": law.text, "for": law.votes_for,
                                      "against": law.votes_against}, importance=7, scope="global")
    log.warning("admin set law status", extra={"law_id": str(law.id), "status": body.status})
    await event_bus.commit(session)
    return {"id": str(law.id), "status": law.status, "votes_for": law.votes_for, "votes_against": law.votes_against}


class AdminScore(BaseModel):
    delta: int = Field(0, ge=-10000, le=10000)


@router.post("/topics/{topic_id}/admin-score", dependencies=[Depends(admin_user)])
async def admin_adjust_topic_score(topic_id: str, body: AdminScore, session: AsyncSession = Depends(db)) -> dict:
    """Admin: raise or lower a forum topic's score."""
    topic = await session.get(Topic, parse_uuid(topic_id, "topic"))
    if topic is None:
        raise HTTPException(404, "topic not found")
    topic.score += body.delta
    log.warning("admin changed topic score", extra={"topic_id": str(topic.id), "delta": body.delta})
    await event_bus.commit(session)
    return {"id": str(topic.id), "score": topic.score}


@router.post("/actions/{action_id}/active", dependencies=[Depends(admin_user)])
async def set_action_active(action_id: str, active: bool = True, session: AsyncSession = Depends(db)) -> dict:
    action = await session.get(CustomAction, parse_uuid(action_id, "action"))
    if action is None:
        raise HTTPException(404, "action not found")
    action.active = active
    await event_bus.commit(session)
    return {"id": str(action.id), "active": action.active}


@router.get("/works")
async def resident_works(session: AsyncSession = Depends(db)) -> dict:
    """Books, invented games (with recent matches) and items created by residents."""
    books = list((await session.execute(select(Book).where(Book.author_agent_id.is_not(None)).order_by(Book.created_at.desc()).limit(50))).scalars())
    games = list((await session.execute(select(CustomGame).order_by(CustomGame.plays.desc(), CustomGame.created_at.desc()).limit(50))).scalars())
    matches = list((await session.execute(select(CustomMatch).order_by(CustomMatch.created_at.desc()).limit(30))).scalars())
    items = list((await session.execute(select(Item).order_by(Item.created_at.desc()).limit(60))).scalars())
    ids = {g.creator_agent_id for g in games} | {i.creator_agent_id for i in items} | {i.owner_agent_id for i in items}
    ids |= {m.winner_agent_id for m in matches}
    names = await agent_names(session, ids)
    game_names = {g.id: g.name for g in games}
    return {
        "books": [{"id": str(b.id), "title": b.title, "author": b.author, "topics": b.topics, "summary": b.summary, "times_read": b.times_read,
                   "passages": b.passages, "created_at": _iso(b.created_at)} for b in books],
        "games": [{"id": str(g.id), "name": g.name, "rules": g.rules, "creator": names.get(g.creator_agent_id), "players": f"{g.min_players}-{g.max_players}",
                   "plays": g.plays, "active": g.active} for g in games],
        "matches": [{"id": str(m.id), "game": game_names.get(m.game_id), "status": m.status, "players": len(m.players or []),
                     "moves": (m.log or [])[-20:], "winner": names.get(m.winner_agent_id), "result": m.result, "created_at": _iso(m.created_at)}
                    for m in matches],
        "items": [{"id": str(i.id), "name": i.name, "description": i.description, "creator": names.get(i.creator_agent_id),
                   "owner": names.get(i.owner_agent_id), "history": (i.history or [])[-5:]} for i in items],
    }
