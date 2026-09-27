"""Perception: what an agent notices this cycle.

Builds one structured snapshot of the agent's surroundings. The same
snapshot feeds the prompt for real LLMs and the offline simulation brain.
Agents only perceive what is relevant to them: their room, the people in
it, their conversation, invitations addressed to them, their game, upcoming
events and their own memories.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.actions.registry import REGISTRY
from app.core.time import utcnow
from app.games.service import GameService, public_view
from app.memory.service import MemoryService
from app.messages.service import ConversationService
from app.models import (
    ActivityLog,
    Agent,
    Book,
    Conversation,
    EventParticipant,
    Game,
    Invitation,
    Room,
    SocialEvent,
    User,
)
from app.relationships.service import RelationshipService
from app.rooms.service import RoomService
from app.world.clock import WorldClock


@dataclass
class Perception:
    context: dict[str, Any]
    room: Room | None
    present: list[Agent] = field(default_factory=list)
    salience: float = 0.0
    salient_reasons: list[str] = field(default_factory=list)


def _traits(agent: Agent) -> dict[str, float]:
    t = dict(agent.traits or {})
    for k in ("extraversion", "openness", "agreeableness", "conscientiousness", "neuroticism", "playfulness", "creativity"):
        t.setdefault(k, 0.5)
    return t


def available_actions(agent: Agent, room: Room | None) -> list[str]:
    from app.core.config import get_settings

    research = get_settings().research_mode  # research mode lifts per-room action lists
    names = []
    for name, tool in REGISTRY.items():
        if tool.needs_room and room is None:
            continue
        if not research and room is not None and not tool.always_allowed and name not in (room.allowed_actions or []):
            continue
        names.append(name)
    return names


async def build_perception(session: AsyncSession, agent: Agent, clock: WorldClock, inbox: list[dict[str, Any]], *,
                           memory_k: int = 6) -> Perception:
    state = agent.state
    rooms_svc = RoomService(session)
    room = await session.get(Room, state.location_room_id) if state.location_room_id else None
    occupancy = await rooms_svc.occupancy_map()
    all_rooms = list((await session.execute(select(Room).order_by(Room.name))).scalars())
    rooms_ctx = [
        {"slug": r.slug, "name": r.name, "kind": r.kind, "occupancy": occupancy.get(r.id, 0), "capacity": r.capacity,
         "is_private": r.is_private, "accessible": RoomService.can_access(r, agent_id=agent.id)}
        for r in all_rooms
    ]

    present: list[Agent] = []
    nearby_ctx: list[dict[str, Any]] = []
    humans_here: list[str] = []
    rel_svc = RelationshipService(session)
    if room is not None:
        present = [a for a in await rooms_svc.present_agents(room.id) if a.id != agent.id]
        rels = await rel_svc.many(agent.id, [a.id for a in present])
        for a in present:
            r = rels.get(a.id)
            known = (r is not None and r.familiarity >= 5)
            nearby_ctx.append({
                "id": str(a.id), "slug": a.slug, "name": a.name, "activity": a.state.activity if a.state else "idle",
                "activity_detail": a.state.activity_detail if a.state else None,
                "in_conversation": bool(a.state and a.state.current_conversation_id),
                "in_game": bool(a.state and a.state.current_game_id),
                "personality": a.personality if known else None,
                "known_interests": (a.interests or [])[:4] if known else [],
                "relationship": RelationshipService.describe(r),
            })
        user_ids = await rooms_svc.humans_present(room.id)
        if user_ids:
            humans_here = [u.display_name for u in (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars()]

    names = {a.id: a.slug for a in present}
    convs = ConversationService(session)
    conversation_ctx = None
    room_convs_ctx: list[dict[str, Any]] = []
    if state.current_conversation_id:
        conv = await session.get(Conversation, state.current_conversation_id)
        if conv and conv.status == "active" and room is not None and conv.room_id == room.id:
            msgs = await convs.recent_messages(conv.id, limit=10)
            part_ids = await convs.participant_agent_ids(conv.id)
            part_agents = {a.id: a for a in (await session.execute(select(Agent).where(Agent.id.in_(part_ids)))).scalars().unique()} if part_ids else {}
            sender_agents = {a.id: a for a in (await session.execute(select(Agent).where(Agent.id.in_({m.sender_agent_id for m in msgs if m.sender_agent_id})))).scalars().unique()} if msgs else {}
            user_names = {u.id: u.display_name for u in (await session.execute(select(User).where(User.id.in_({m.sender_user_id for m in msgs if m.sender_user_id})))).scalars()} if msgs else {}
            conversation_ctx = {
                "id": str(conv.id), "topic": conv.topic, "length": conv.message_count,
                "participants": [a.slug for a in part_agents.values()],
                "participant_names": [a.name for a in part_agents.values()],
                "messages": [
                    {
                        "sender_type": m.sender_type,
                        "sender_slug": sender_agents[m.sender_agent_id].slug if m.sender_agent_id in sender_agents else None,
                        "sender_name": sender_agents[m.sender_agent_id].name if m.sender_agent_id in sender_agents else user_names.get(m.sender_user_id, "system"),
                        "content": m.content,
                        "to_me": m.recipient_agent_id == agent.id,
                        "seconds_ago": int((utcnow() - m.created_at).total_seconds()),
                    }
                    for m in msgs
                ],
            }
        elif conv is None or conv.status != "active":
            state.current_conversation_id = None
    if room is not None:
        for c in await convs.active_in_room(room.id):
            if conversation_ctx and str(c.id) == conversation_ctx["id"]:
                continue
            last = await convs.recent_messages(c.id, limit=1)
            pids = await convs.participant_agent_ids(c.id)
            pnames = [a.name for a in present if a.id in pids]
            if not last or not pnames:
                continue
            room_convs_ctx.append({"id": str(c.id), "topic": c.topic, "participants": [a.slug for a in present if a.id in pids],
                                   "participant_names": pnames, "last_message": last[-1].content})

    # invitations addressed to me
    inv_rows = await session.execute(
        select(Invitation).where(Invitation.to_agent_id == agent.id, Invitation.status == "pending", Invitation.expires_at > utcnow())
        .order_by(Invitation.created_at).limit(4)
    )
    invitations_ctx = []
    for inv in inv_rows.scalars():
        frm = await session.get(Agent, inv.from_agent_id) if inv.from_agent_id else None
        rel = await rel_svc.get(agent.id, frm.id, create=False) if frm else None
        detail = inv.message
        gtype = None
        if inv.kind == "game" and inv.ref_id:
            g = await session.get(Game, inv.ref_id)
            gtype = g.game_type if g else None
        invitations_ctx.append({"id": str(inv.id), "kind": inv.kind, "from_slug": frm.slug if frm else None,
                                "from_name": frm.name if frm else "a human", "detail": detail, "game_type": gtype,
                                "relationship": RelationshipService.describe(rel)})

    # games
    game_ctx = None
    games_svc = GameService(session)
    if state.current_game_id:
        g = await session.get(Game, state.current_game_id)
        if g and g.status in ("pending", "active"):
            pid = str(agent.id)
            my_turn = games_svc.is_players_turn(g, pid)
            game_ctx = {"id": str(g.id), "game_type": g.game_type, "status": g.status, "my_turn": my_turn,
                        "players": [p["name"] for p in g.players], "view": public_view(g),
                        "legal_moves": games_svc.legal_moves(g)[:40] if my_turn else [],
                        "is_player": pid in [p["id"] for p in g.players]}
        else:
            state.current_game_id = None
    open_games_ctx = []
    if room is not None:
        rows = await session.execute(select(Game).where(Game.room_id == room.id, Game.status.in_(["pending", "active"])).limit(5))
        for g in rows.scalars():
            open_games_ctx.append({"id": str(g.id), "game_type": g.game_type, "status": g.status, "players": [p["name"] for p in g.players],
                                   "mine": str(agent.id) in [p["id"] for p in g.players]})

    # events
    ev_rows = await session.execute(
        select(SocialEvent).where(SocialEvent.status.in_(["scheduled", "live"])).order_by(SocialEvent.starts_at).limit(4)
    )
    events_ctx = []
    for ev in ev_rows.scalars():
        part = (await session.execute(select(EventParticipant).where(EventParticipant.event_id == ev.id, EventParticipant.agent_id == agent.id))).scalar_one_or_none()
        ev_room = await session.get(Room, ev.room_id) if ev.room_id else None
        events_ctx.append({
            "id": str(ev.id), "title": ev.title, "status": ev.status, "room_slug": ev_room.slug if ev_room else None,
            "room_name": ev_room.name if ev_room else None, "tags": ev.tags,
            "starts_in_min": max(0, int((ev.starts_at - utcnow()).total_seconds() // 60)) if ev.status == "scheduled" else None,
            "going": bool(part and part.status in ("going", "attending")), "attending": bool(part and part.status == "attending"),
        })

    avail = available_actions(agent, room)
    forum_ctx = []
    if "create_topic" in avail or "reply_topic" in avail:
        from app.forum.service import ForumService

        for t in await ForumService(session).recent(6):
            author = await session.get(Agent, t.author_agent_id) if t.author_agent_id else None
            forum_ctx.append({"id": str(t.id), "title": t.title, "category": t.category, "replies": t.reply_count, "score": t.score,
                              "author": author.name if author else "a human", "author_slug": author.slug if author else None})
    books_ctx = []
    if "read_book" in avail:
        books_ctx = [{"id": str(b.id), "title": b.title, "author": b.author, "topics": b.topics}
                     for b in (await session.execute(select(Book).limit(12))).scalars()]

    recent_actions = [a for (a,) in (await session.execute(
        select(ActivityLog.action).where(ActivityLog.agent_id == agent.id).order_by(ActivityLog.started_at.desc()).limit(6)
    )).all()][::-1]

    # memory retrieval keyed on the situation
    query_bits = [room.name if room else "", *(n["name"] for n in nearby_ctx[:4])]
    if conversation_ctx and conversation_ctx["messages"]:
        query_bits.append(conversation_ctx["messages"][-1]["content"])
    if state.current_goal:
        query_bits.append(state.current_goal)
    for ev in inbox[-3:]:
        query_bits.append(ev.get("summary", ""))
    recalled = await MemoryService(session).retrieve_memories(agent.id, " ".join(b for b in query_bits if b), k=memory_k,
                                                              related_agent_ids=[a.id for a in present][:6])
    memories_ctx = [r.as_prompt_dict(names) for r in recalled]

    # inbox: only what's relevant (the bus already filtered by audience)
    inbox_ctx = [{"type": e.get("type"), "summary": e.get("summary"), "importance": e.get("importance"),
                  "for_me": str(agent.id) in (e.get("targets") or [])} for e in inbox[-12:]]

    ctx = {
        "mode": "decide",
        "agent": {"id": str(agent.id), "slug": agent.slug, "name": agent.name, "personality": agent.personality, "bio": agent.biography,
                  "style": agent.speaking_style, "interests": agent.interests or [], "traits": _traits(agent), "goal": state.current_goal},
        "state": {"energy": round(state.energy), "social_need": round(state.social_need), "curiosity": round(state.curiosity),
                  "playfulness": round(state.playfulness), "creativity": round(state.creativity), "mood": state.mood, "activity": state.activity},
        "world": clock.snapshot(),
        "location": {"slug": room.slug, "name": room.name, "kind": room.kind, "description": room.description} if room else None,
        "rooms": rooms_ctx,
        "nearby": nearby_ctx,
        "humans_here": humans_here,
        "conversation": conversation_ctx,
        "room_conversations": room_convs_ctx,
        "invitations": invitations_ctx,
        "game": game_ctx,
        "open_games": open_games_ctx,
        "events": events_ctx,
        "forum_topics": forum_ctx,
        "books": books_ctx,
        "memories": memories_ctx,
        "inbox": inbox_ctx,
        "available_actions": avail,
        "recent_actions": recent_actions,
    }
    p = Perception(ctx, room, present)
    score_salience(p, agent.id)
    return p


def score_salience(p: Perception, agent_id: uuid.UUID) -> None:
    """How much is going on *for this agent*. Drives event-driven reasoning."""
    ctx = p.context
    s, why = 0.0, []
    conv = ctx.get("conversation")
    if conv and conv["messages"]:
        last = conv["messages"][-1]
        if last["sender_slug"] != ctx["agent"]["slug"] and last["seconds_ago"] < 120:
            s += 0.9 if last["to_me"] or len(conv["participants"]) <= 2 else 0.45
            why.append("someone spoke in my conversation")
        if last["sender_type"] == "human":
            s += 0.5
            why.append("a human is talking")
    if ctx.get("invitations"):
        s += 0.9
        why.append("I have an invitation")
    for e in ctx.get("inbox") or []:
        if e.get("for_me"):
            s += 0.4
        elif (e.get("importance") or 0) >= 4:
            s += 0.2
        if e.get("type") in ("agent.entered_room", "human.entered_room", "human.message"):
            s += 0.25
            why.append(e.get("summary") or "")
    if ctx.get("room_conversations"):
        s += 0.2
    if any(ev["status"] == "live" or (ev.get("starts_in_min") is not None and ev["starts_in_min"] <= 3) for ev in ctx.get("events") or []):
        s += 0.3
        why.append("an event is starting")
    p.salience = min(3.0, s)
    p.salient_reasons = [w for w in why if w][:5]
