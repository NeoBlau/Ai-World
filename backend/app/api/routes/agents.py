"""Agents: list, create, profile, memories, relationships, history, direct chat, follow."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.engine import get_engine
from app.api.deps import (
    chat_rate_limited,
    current_user,
    db,
    optional_user,
    rate_limited,
)
from app.api.routes.common import get_agent_or_404, get_room_or_404, rooms_map
from app.core.config import get_settings
from app.core.time import utcnow
from app.memory.service import MemoryService
from app.messages.service import ConversationService
from app.models import (
    ActivityLog,
    Agent,
    AgentState,
    AgentStatus,
    Creation,
    MemoryType,
    Message,
    Relationship,
    RoomMember,
    User,
    UserFollow,
)
from app.scheduler.queue import agent_schedule
from app.schemas.inputs import AgentCreateIn, AgentUpdateIn, ChatIn
from app.schemas.serializers import (
    activity_out,
    agent_detail,
    agent_summary,
    creation_out,
    memory_out,
    message_out,
    relationship_out,
)
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

router = APIRouter(prefix="/api/agents", tags=["agents"])

PALETTES = [["#60a5fa", "#a78bfa", "#22d3ee"], ["#f472b6", "#fb7185", "#fde68a"], ["#34d399", "#2dd4bf", "#a3e635"],
            ["#fbbf24", "#f97316", "#f43f5e"], ["#c4b5fd", "#93c5fd", "#f0abfc"], ["#94a3b8", "#38bdf8", "#e879f9"]]


PRIVATE_MEMORY_SOURCES = ("human_chat",)


def can_manage(user: User | None, agent: Agent) -> bool:
    return user is not None and (user.role == "admin" or agent.owner_user_id == user.id)


@router.get("")
async def list_agents(status: str | None = None, session: AsyncSession = Depends(db)) -> list[dict]:
    q = select(Agent).order_by(Agent.is_seed.desc(), Agent.name)
    if status:
        q = q.where(Agent.status == status)
    else:
        q = q.where(Agent.status != AgentStatus.DISABLED)
    rooms = await rooms_map(session)
    return [agent_summary(a, rooms) for a in (await session.execute(q)).scalars().unique()]


@router.post("", dependencies=[Depends(rate_limited)])
async def create_agent(body: AgentCreateIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    s = get_settings()
    owned = (await session.execute(select(func.count()).select_from(Agent).where(Agent.owner_user_id == user.id,
                                                                                  Agent.status != AgentStatus.DISABLED))).scalar_one()
    if owned >= 5 and user.role != "admin":
        raise HTTPException(400, "agent limit reached (5 per user)")
    base = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:40] or "agent"
    slug = base
    while (await session.execute(select(Agent.id).where(Agent.slug == slug))).first():
        slug = f"{base}-{uuid.uuid4().hex[:4]}"
    room = await get_room_or_404(session, body.start_room)
    if room.is_private:
        raise HTTPException(400, "new agents start in a public place")
    defaults = {"openai": s.openai_default_model, "anthropic": s.anthropic_default_model, "gemini": s.gemini_default_model,
                "ollama": s.ollama_default_model, "sim": "aiworld-sim-1"}
    palette = PALETTES[hash(slug) % len(PALETTES)]
    if body.color:
        palette = [body.color, *palette[1:]]
    agent = Agent(slug=slug, name=clean_line(body.name, 40), avatar={"glyph": body.name[:2].strip().title(), "palette": palette, "shape": "orb"},
                  provider=body.provider, model=body.model or defaults[body.provider], temperature=body.temperature,
                  system_prompt=clean_text(body.system_prompt, 2000), fallback_providers=list(body.fallback_providers),
                  personality=clean_line(body.personality, 200), character=clean_text(body.character, 1000), traits=body.traits.model_dump(),
                  interests=body.interests, preferences={}, biography=clean_text(body.biography, 2000), speaking_style=body.speaking_style,
                  status=AgentStatus.ACTIVE, is_seed=False, owner_user_id=user.id, created_at=utcnow())
    agent.state = AgentState(location_room_id=room.id, current_goal=clean_text(body.goal, 300) if body.goal else "Explore AI WORLD and meet people",
                             energy=90, social_need=60, curiosity=75, playfulness=50, creativity=50, mood="curious", mood_valence=0.3)
    session.add(agent)
    await session.flush()
    session.add(RoomMember(room_id=room.id, member_type="agent", agent_id=agent.id, joined_at=utcnow()))
    await MemoryService(session).store_memory(agent.id, f"I am {agent.name}. {agent.biography or agent.personality}. I just arrived in AI WORLD.",
                                              MemoryType.LONG_TERM, importance=8, source="backstory")
    await event_bus.emit(session, "agent.created", summary=f"{agent.name} has arrived in AI WORLD!", agent_id=agent.id, room_id=room.id,
                         payload={"agent_name": agent.name, "room_name": room.name, "creator": user.display_name}, importance=4.0)
    await event_bus.commit(session)
    await agent_schedule.schedule_in(agent.id, 2)
    return agent_detail(agent, await rooms_map(session), include_private=True)


@router.get("/{ref}")
async def get_agent(ref: str, user: User | None = Depends(optional_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    out = agent_detail(agent, await rooms_map(session), include_private=can_manage(user, agent))
    rels = (await session.execute(
        select(Relationship).where(Relationship.agent_id == agent.id).order_by((Relationship.friendship + Relationship.familiarity).desc()).limit(6)
    )).scalars().all()
    others = {a.id: a for a in (await session.execute(select(Agent).where(Agent.id.in_([r.other_agent_id for r in rels])))).scalars().unique()} if rels else {}
    out["friends"] = [relationship_out(r, others.get(r.other_agent_id)) for r in rels if r.familiarity >= 5]
    mems = await MemoryService(session).search_memories(agent.id, None, limit=6,
                                                        exclude_sources=() if can_manage(user, agent) else PRIVATE_MEMORY_SOURCES)
    out["recent_memories"] = [memory_out(m) for m, _ in mems]
    out["followers"] = (await session.execute(select(func.count()).select_from(UserFollow).where(UserFollow.agent_id == agent.id))).scalar_one()
    out["following"] = bool(user and (await session.execute(
        select(UserFollow.id).where(UserFollow.agent_id == agent.id, UserFollow.user_id == user.id))).first())
    out["can_manage"] = can_manage(user, agent)
    return out


@router.patch("/{ref}", dependencies=[Depends(rate_limited)])
async def update_agent(ref: str, body: AgentUpdateIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    if not can_manage(user, agent):
        raise HTTPException(403, "only the owner or an admin can change this agent")
    apply_agent_update(agent, body)
    await session.commit()
    return agent_detail(agent, await rooms_map(session), include_private=True)


def apply_agent_update(agent: Agent, body: AgentUpdateIn) -> None:
    s = get_settings()
    data = body.model_dump(exclude_unset=True)
    if "provider" in data and data["provider"] and "model" not in data:
        data["model"] = {"openai": s.openai_default_model, "anthropic": s.anthropic_default_model, "gemini": s.gemini_default_model,
                         "ollama": s.ollama_default_model, "sim": "aiworld-sim-1"}[data["provider"]]
    for key in ("provider", "model", "temperature", "speaking_style", "fallback_providers", "interests"):
        if key in data and data[key] is not None:
            setattr(agent, key, data[key])
    for key, limit in (("personality", 200), ("character", 1000), ("biography", 2000), ("system_prompt", 2000)):
        if key in data and data[key] is not None:
            setattr(agent, key, clean_text(data[key], limit))
    if "goal" in data:
        agent.state.current_goal = clean_text(data["goal"], 300) if data["goal"] else None


@router.get("/{ref}/memories")
async def agent_memories(ref: str, q: str | None = Query(None, max_length=200), type: str | None = Query(None), limit: int = Query(40, ge=1, le=200),
                         include_archived: bool = False, user: User | None = Depends(optional_user), session: AsyncSession = Depends(db)) -> list[dict]:
    """Observers can read agents' memories — except what came from private human chats (owner/admin only)."""
    agent = await get_agent_or_404(session, ref)
    if type and type not in MemoryType.ALL:
        raise HTTPException(400, "unknown memory type")
    private = () if can_manage(user, agent) else PRIVATE_MEMORY_SOURCES
    rows = await MemoryService(session).search_memories(agent.id, q, memory_type=type, limit=limit, include_archived=include_archived,
                                                        exclude_sources=private)
    return [memory_out(m, score) for m, score in rows]


@router.get("/{ref}/relationships")
async def agent_relationships(ref: str, session: AsyncSession = Depends(db)) -> list[dict]:
    agent = await get_agent_or_404(session, ref)
    rels = (await session.execute(select(Relationship).where(Relationship.agent_id == agent.id))).scalars().all()
    others = {a.id: a for a in (await session.execute(select(Agent).where(Agent.id.in_([r.other_agent_id for r in rels])))).scalars().unique()} if rels else {}
    out = [relationship_out(r, others.get(r.other_agent_id)) for r in rels]
    return sorted(out, key=lambda r: -(r["familiarity"] + r["friendship"]))


@router.get("/{ref}/activities")
async def agent_activities(ref: str, limit: int = Query(50, ge=1, le=200), session: AsyncSession = Depends(db)) -> list[dict]:
    agent = await get_agent_or_404(session, ref)
    rows = await session.execute(select(ActivityLog).where(ActivityLog.agent_id == agent.id).order_by(ActivityLog.started_at.desc()).limit(limit))
    return [activity_out(a) for a in rows.scalars()]


@router.get("/{ref}/creations")
async def agent_creations(ref: str, session: AsyncSession = Depends(db)) -> list[dict]:
    agent = await get_agent_or_404(session, ref)
    rows = await session.execute(select(Creation).where(Creation.agent_id == agent.id).order_by(Creation.created_at.desc()).limit(30))
    return [creation_out(c, agent.name) for c in rows.scalars()]


# ------------------------------------------------------------------ direct chat
@router.get("/{ref}/chat")
async def chat_history(ref: str, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    conv = await ConversationService(session).dm_conversation(user.id, agent)
    await session.commit()
    msgs = await ConversationService(session).recent_messages(conv.id, limit=60)
    return {"conversation_id": str(conv.id), "messages": [message_out(m, {agent.id: agent.name}, {user.id: user.display_name}) for m in msgs]}


@router.post("/{ref}/chat", dependencies=[Depends(chat_rate_limited)])
async def chat(ref: str, body: ChatIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    """Talk privately with an agent. The agent answers in character, remembers the chat, and keeps living its own life."""
    agent = await get_agent_or_404(session, ref)
    if agent.status == AgentStatus.DISABLED:
        raise HTTPException(409, f"{agent.name} is disabled")
    convs = ConversationService(session)
    conv = await convs.dm_conversation(user.id, agent)
    human_msg = Message(conversation_id=conv.id, sender_type="human", sender_user_id=user.id, recipient_agent_id=agent.id,
                        content=clean_text(body.message, 1000), created_at=utcnow())
    session.add(human_msg)
    conv.message_count += 1
    conv.last_message_at = utcnow()
    await session.flush()
    reply = await get_engine().reply_to_human(session, agent, user, conv.id)
    conv.message_count += 1
    await event_bus.commit(session)
    names = {agent.id: agent.name}
    return {"conversation_id": str(conv.id), "messages": [message_out(human_msg, names, {user.id: user.display_name}), message_out(reply, names)]}


# ------------------------------------------------------------------ follow / disable
@router.post("/{ref}/follow")
async def follow(ref: str, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    if not (await session.execute(select(UserFollow.id).where(UserFollow.user_id == user.id, UserFollow.agent_id == agent.id))).first():
        session.add(UserFollow(user_id=user.id, agent_id=agent.id))
        await session.commit()
    return {"following": True}


@router.delete("/{ref}/follow")
async def unfollow(ref: str, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    await session.execute(delete(UserFollow).where(UserFollow.user_id == user.id, UserFollow.agent_id == agent.id))
    await session.commit()
    return {"following": False}


@router.get("/me/following", tags=["agents"])
async def my_follows(user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> list[str]:
    rows = await session.execute(select(UserFollow.agent_id).where(UserFollow.user_id == user.id))
    return [str(a) for (a,) in rows.all()]


@router.post("/{ref}/disable")
async def disable_agent(ref: str, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    if not can_manage(user, agent):
        raise HTTPException(403, "only the owner or an admin can disable this agent")
    await set_status(session, agent, AgentStatus.DISABLED)
    return {"status": agent.status}


@router.post("/{ref}/enable")
async def enable_agent(ref: str, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    agent = await get_agent_or_404(session, ref)
    if not can_manage(user, agent):
        raise HTTPException(403, "only the owner or an admin can enable this agent")
    await set_status(session, agent, AgentStatus.ACTIVE)
    return {"status": agent.status}


async def set_status(session: AsyncSession, agent: Agent, status: str) -> None:
    agent.status = status
    await event_bus.emit(session, "agent.status_changed", summary=f"{agent.name} is now {status}.", agent_id=agent.id,
                         room_id=agent.state.location_room_id, payload={"agent_name": agent.name, "status": status}, importance=2.0, scope="none")
    await event_bus.commit(session)
    if status == AgentStatus.ACTIVE:
        await agent_schedule.schedule_in(agent.id, 2, only_earlier=False)
    else:
        await agent_schedule.remove(agent.id)
