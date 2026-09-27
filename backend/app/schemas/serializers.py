"""Output serialisers shared by the REST API and WebSocket snapshots.

Nothing sensitive (system prompts are fine to show to owners/admins only;
API keys never exist on these objects at all).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.games.service import public_view
from app.models import (
    ActivityLog,
    Agent,
    AgentMemory,
    Creation,
    Game,
    GameMove,
    Message,
    Relationship,
    Room,
    SocialEvent,
    Topic,
    TopicReply,
    WorldEvent,
)
from app.relationships.service import label


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def agent_summary(a: Agent, rooms: dict[uuid.UUID, Room] | None = None) -> dict[str, Any]:
    st = a.state
    room = rooms.get(st.location_room_id) if rooms and st and st.location_room_id else None
    dest = rooms.get(st.destination_room_id) if rooms and st and st.destination_room_id else None
    return {
        "id": str(a.id), "slug": a.slug, "name": a.name, "avatar": a.avatar, "provider": a.provider, "model": a.model,
        "personality": a.personality, "interests": a.interests, "status": a.status, "speaking_style": a.speaking_style,
        "is_seed": a.is_seed,
        "state": {
            "energy": round(st.energy, 1), "social_need": round(st.social_need, 1), "curiosity": round(st.curiosity, 1),
            "playfulness": round(st.playfulness, 1), "creativity": round(st.creativity, 1), "mood": st.mood,
            "activity": st.activity, "activity_detail": st.activity_detail, "availability": st.availability,
            "location": {"id": str(room.id), "slug": room.slug, "name": room.name} if room else None,
            "destination": {"id": str(dest.id), "slug": dest.slug, "name": dest.name} if dest else None,
            "arrive_at": iso(st.arrive_at), "current_goal": st.current_goal, "last_action": st.last_action,
            "last_action_at": iso(st.last_action_at), "last_provider": st.last_provider, "last_model": st.last_model,
            "conversation_id": str(st.current_conversation_id) if st.current_conversation_id else None,
            "game_id": str(st.current_game_id) if st.current_game_id else None,
            "event_id": str(st.current_event_id) if st.current_event_id else None,
        } if st else None,
    }


def agent_detail(a: Agent, rooms: dict[uuid.UUID, Room], *, include_private: bool = False) -> dict[str, Any]:
    out = agent_summary(a, rooms)
    out.update({
        "character": a.character, "biography": a.biography, "traits": a.traits, "preferences": a.preferences,
        "temperature": a.temperature, "fallback_providers": a.fallback_providers, "created_at": iso(a.created_at),
        "last_thought": a.state.last_thought if a.state else None, "cycles": a.state.cycles if a.state else 0,
    })
    if include_private:
        out["system_prompt"] = a.system_prompt
    return out


def room_out(r: Room, occupancy: int = 0, agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": str(r.id), "slug": r.slug, "name": r.name, "description": r.description, "kind": r.kind, "capacity": r.capacity,
        "allowed_actions": r.allowed_actions, "is_private": r.is_private, "position": r.position, "theme": r.theme, "ambience": r.ambience,
        "occupancy": occupancy, "agents": agents or [],
    }


def message_out(m: Message, names: dict[uuid.UUID, str] | None = None, user_names: dict[uuid.UUID, str] | None = None) -> dict[str, Any]:
    sender_name = None
    if m.sender_agent_id and names:
        sender_name = names.get(m.sender_agent_id)
    if m.sender_user_id and user_names:
        sender_name = user_names.get(m.sender_user_id)
    return {
        "id": str(m.id), "conversation_id": str(m.conversation_id) if m.conversation_id else None, "room_id": str(m.room_id) if m.room_id else None,
        "sender_type": m.sender_type, "sender_agent_id": str(m.sender_agent_id) if m.sender_agent_id else None,
        "sender_name": sender_name or ("system" if m.sender_type == "system" else "human"),
        "recipient_agent_id": str(m.recipient_agent_id) if m.recipient_agent_id else None,
        "recipient_name": names.get(m.recipient_agent_id) if names and m.recipient_agent_id else None,
        "content": m.content, "tone": m.tone, "created_at": iso(m.created_at),
    }


def world_event_out(e: WorldEvent) -> dict[str, Any]:
    return {"id": str(e.id), "type": e.event_type, "summary": e.summary, "agent_id": str(e.agent_id) if e.agent_id else None,
            "room_id": str(e.room_id) if e.room_id else None, "payload": e.payload, "importance": e.importance,
            "created_at": iso(e.created_at), "world_time": iso(e.world_time), "targets": []}


def memory_out(m: AgentMemory, score: float | None = None) -> dict[str, Any]:
    return {"id": str(m.id), "type": m.memory_type, "content": m.content, "importance": m.importance, "source": m.source,
            "related_agent_id": str(m.related_agent_id) if m.related_agent_id else None, "is_archived": m.is_archived,
            "access_count": m.access_count, "created_at": iso(m.created_at), "world_time": iso(m.world_time),
            "score": round(score, 3) if score is not None else None, "embedding_model": m.embedding_model}


def relationship_out(r: Relationship, other: Agent | None) -> dict[str, Any]:
    return {"other_agent": {"id": str(other.id), "slug": other.slug, "name": other.name, "avatar": other.avatar} if other else None,
            "familiarity": round(r.familiarity, 1), "trust": round(r.trust, 1), "friendship": round(r.friendship, 1),
            "respect": round(r.respect, 1), "conflict": round(r.conflict, 1), "interactions": r.interactions, "label": label(r),
            "shared_history": r.shared_history[-8:], "last_interaction_at": iso(r.last_interaction_at)}


def topic_out(t: Topic, author_name: str | None) -> dict[str, Any]:
    return {"id": str(t.id), "title": t.title, "body": t.body, "category": t.category, "author_type": t.author_type,
            "author_agent_id": str(t.author_agent_id) if t.author_agent_id else None, "author_name": author_name, "score": t.score,
            "reply_count": t.reply_count, "is_pinned": t.is_pinned, "created_at": iso(t.created_at), "last_activity_at": iso(t.last_activity_at)}


def reply_out(r: TopicReply, author_name: str | None) -> dict[str, Any]:
    return {"id": str(r.id), "author_type": r.author_type, "author_agent_id": str(r.author_agent_id) if r.author_agent_id else None,
            "author_name": author_name or ("AI WORLD builders" if r.author_type == "system" else None), "content": r.content,
            "created_at": iso(r.created_at)}


def event_out(e: SocialEvent, room: Room | None, participants: list[dict[str, Any]] | None = None, organizer: str | None = None) -> dict[str, Any]:
    return {"id": str(e.id), "title": e.title, "description": e.description, "category": e.category, "status": e.status,
            "room": {"id": str(room.id), "slug": room.slug, "name": room.name} if room else None, "starts_at": iso(e.starts_at),
            "ends_at": iso(e.ends_at), "capacity": e.capacity, "tags": e.tags, "organizer": organizer, "organizer_type": e.organizer_type,
            "participants": participants or []}


def game_out(g: Game, moves: list[GameMove] | None = None) -> dict[str, Any]:
    out = {"id": str(g.id), "game_type": g.game_type, "status": g.status, "players": g.players, "spectators": g.spectators,
           "current_turn": g.current_turn, "winner": g.winner, "result": g.result, "move_count": g.move_count,
           "room_id": str(g.room_id) if g.room_id else None, "view": public_view(g) if g.state else {"type": g.game_type},
           "created_at": iso(g.created_at), "updated_at": iso(g.updated_at), "finished_at": iso(g.finished_at)}
    if moves is not None:
        out["moves"] = [{"number": m.move_number, "player_id": m.player_id, "move": m.move, "comment": m.comment, "created_at": iso(m.created_at)}
                        for m in moves]
    return out


def activity_out(a: ActivityLog) -> dict[str, Any]:
    return {"id": str(a.id), "action": a.action, "activity": a.activity, "params": a.params, "thought": a.thought, "result": a.result,
            "success": a.success, "error": a.error, "decided_by": a.decided_by, "provider": a.provider, "model": a.model,
            "latency_ms": a.latency_ms, "started_at": iso(a.started_at), "room_id": str(a.room_id) if a.room_id else None}


def creation_out(c: Creation, author: str | None) -> dict[str, Any]:
    return {"id": str(c.id), "kind": c.kind, "title": c.title, "content": c.content, "data": c.data, "author": author,
            "agent_id": str(c.agent_id), "created_at": iso(c.created_at)}
