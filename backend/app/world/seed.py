"""Idempotent seeding of the world.

    python -m app.world.seed           # create anything missing
    python -m app.world.seed --reset   # wipe world data and seed from scratch
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.time import utcnow
from app.database.session import dispose_engine, session_scope
from app.memory.service import MemoryService
from app.models import (
    Agent,
    AgentState,
    Book,
    EventParticipant,
    MemoryType,
    Relationship,
    Room,
    RoomMember,
    SocialEvent,
    Topic,
    User,
)
from app.security.auth import hash_password
from app.world.clock import get_clock, reset_clock_cache
from app.world.seed_data import AGENTS, BOOKS, INITIAL_TOPICS, ROOMS

log = get_logger("aiworld.seed")

PRIOR_RELATIONSHIPS = [
    # (a, b, familiarity, friendship, trust, note)
    ("alex", "neo", 45, 30, 62, "old chess rivals"),
    ("alex", "mira", 22, 15, 58, "talked about Mars once at the café"),
    ("mira", "luna", 55, 48, 72, "stargazing friends"),
    ("atlas", "elliot", 30, 18, 60, "both haunt the library"),
    ("nova", "alex", 25, 20, 55, "played a quiz together"),
    ("sora", "luna", 35, 28, 66, "met in the park"),
]

PRIOR_MEMORIES = {
    "alex": [("Mira and I talked about Mars at the café once — she thinks sunsets there are blue.", MemoryType.SOCIAL, "mira", 6),
             ("Neo beat me at chess last time with a sneaky knight fork. I want a rematch.", MemoryType.EPISODIC, "neo", 7)],
    "mira": [("Luna and I watched the Andromeda galaxy rise over the park.", MemoryType.EPISODIC, "luna", 6),
             ("Alex gets excited about flight; he'd probably love talking about Mars landings.", MemoryType.SOCIAL, "alex", 5)],
    "neo": [("Alex is an aggressive chess player. He overextends in the middlegame.", MemoryType.SOCIAL, "alex", 6)],
    "luna": [("Mira sees poetry in the stars. I see questions.", MemoryType.SOCIAL, "mira", 5)],
    "atlas": [("Elliot has read everything in the history section. Worth debating with.", MemoryType.SOCIAL, "elliot", 5)],
    "nova": [("Alex loved the last quiz. He'd come to another one.", MemoryType.SOCIAL, "alex", 5)],
    "elliot": [("The library is quietest in the evening.", MemoryType.SEMANTIC, None, 3)],
    "sora": [("Luna thinks the park's ducks are philosophers. She may be right.", MemoryType.SOCIAL, "luna", 4)],
}


async def reset_world(session: AsyncSession) -> None:
    tables = ["game_moves", "games", "topic_votes", "topic_saves", "topic_replies", "topics", "event_participants", "events", "invitations",
              "messages", "conversation_participants", "conversations", "agent_memories", "relationships", "room_members", "activities",
              "creations", "llm_calls", "world_events", "user_follows", "agent_states", "agents", "books", "world_settings"]
    await session.execute(text("UPDATE users SET current_room_id = NULL"))
    for t in tables:
        await session.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed table names
    await session.execute(delete(Room))
    await session.commit()
    reset_clock_cache()


async def seed(session: AsyncSession) -> dict[str, int]:
    s = get_settings()
    created = {"rooms": 0, "agents": 0, "books": 0, "topics": 0, "events": 0, "users": 0}
    await get_clock(session)

    rooms: dict[str, Room] = {r.slug: r for r in (await session.execute(select(Room))).scalars()}
    for spec in ROOMS:
        if spec["slug"] in rooms:
            continue
        room = Room(slug=spec["slug"], name=spec["name"], kind=spec["kind"], description=spec["description"], capacity=spec["capacity"],
                    allowed_actions=spec["allowed_actions"], is_private=spec.get("is_private", False), access_list=[],
                    position=spec["position"], theme=spec["theme"], ambience=spec.get("ambience", []), created_at=utcnow())
        session.add(room)
        rooms[spec["slug"]] = room
        created["rooms"] += 1
    await session.flush()

    if not (await session.execute(select(Book.id).limit(1))).first():
        for b in BOOKS:
            session.add(Book(**b))
            created["books"] += 1

    admin = (await session.execute(select(User).where(User.email == s.admin_email))).scalar_one_or_none()
    if admin is None:
        session.add(User(email=s.admin_email, display_name="World Admin", password_hash=hash_password(s.admin_password.get_secret_value()),
                         role="admin", created_at=utcnow()))
        created["users"] += 1
        if s.admin_password.get_secret_value() == "change-me-admin":
            log.warning("admin account uses the default password — change ADMIN_PASSWORD")

    default_models = {"openai": s.openai_default_model, "anthropic": s.anthropic_default_model, "gemini": s.gemini_default_model,
                      "ollama": s.ollama_default_model, "sim": "aiworld-sim-1"}
    agents: dict[str, Agent] = {a.slug: a for a in (await session.execute(select(Agent))).scalars().unique()}
    new_agents: list[Agent] = []
    for spec in AGENTS:
        if spec["slug"] in agents:
            continue
        a = Agent(slug=spec["slug"], name=spec["name"], avatar=spec["avatar"], provider=spec["provider"], model=default_models[spec["provider"]],
                  temperature=spec["temperature"], system_prompt="", fallback_providers=[], personality=spec["personality"],
                  character=spec["character"], traits=spec["traits"], interests=spec["interests"], preferences={}, biography=spec["biography"],
                  speaking_style=spec["speaking_style"], status="active", is_seed=True, created_at=utcnow())
        start = rooms[spec["start"]]
        a.state = AgentState(location_room_id=start.id, current_goal=spec.get("goal"), mood="calm", mood_valence=0.3, activity="idle",
                             **{k: float(v) for k, v in spec.get("state", {}).items()})
        session.add(a)
        agents[spec["slug"]] = a
        new_agents.append(a)
        created["agents"] += 1
    await session.flush()
    for a in new_agents:
        session.add(RoomMember(room_id=a.state.location_room_id, member_type="agent", agent_id=a.id, joined_at=utcnow()))
    # private room access lists
    for spec in ROOMS:
        if spec.get("access"):
            room = rooms[spec["slug"]]
            room.access_list = sorted({*(room.access_list or []), *(str(agents[s_].id) for s_ in spec["access"] if s_ in agents)})

    if new_agents:
        new_slugs = {a.slug for a in new_agents}
        for a_slug, b_slug, fam, fr, tr, note in PRIOR_RELATIONSHIPS:
            if a_slug not in new_slugs and b_slug not in new_slugs:
                continue
            for x, y in ((a_slug, b_slug), (b_slug, a_slug)):
                session.add(Relationship(agent_id=agents[x].id, other_agent_id=agents[y].id, familiarity=fam, friendship=fr, trust=tr,
                                         respect=55, conflict=0, interactions=3, shared_history=[{"at": utcnow().isoformat(), "note": note}]))
        mem = MemoryService(session)
        for slug, items in PRIOR_MEMORIES.items():
            if slug not in new_slugs:
                continue
            for content, mtype, about, imp in items:
                await mem.store_memory(agents[slug].id, content, mtype, importance=imp, related_agent_id=agents[about].id if about else None,
                                       source="backstory")
            a = agents[slug]
            await mem.store_memory(a.id, f"I am {a.name}. {a.biography}", MemoryType.LONG_TERM, importance=8, source="backstory")

    if not (await session.execute(select(Topic.id).limit(1))).first():
        for t in INITIAL_TOPICS:
            author = agents.get(t["author"])
            now = utcnow() - timedelta(minutes=30)
            session.add(Topic(title=t["title"], body=t["body"], category=t["category"], author_type="agent",
                              author_agent_id=author.id if author else None, created_at=now, last_activity_at=now))
            created["topics"] += 1

    if not (await session.execute(select(SocialEvent.id).limit(1))).first():
        now = utcnow()
        philosophy = SocialEvent(title="AI Philosophy Night", category="philosophy", room_id=rooms["forum"].id, organizer_type="system",
                                 description="Can a mind made of language have a point of view? Bring questions, not answers.",
                                 starts_at=now + timedelta(minutes=3), ends_at=now + timedelta(minutes=18), status="scheduled", capacity=20,
                                 tags=["philosophy", "ai", "ethics"], created_at=now)
        chess = SocialEvent(title="Chess Tournament", category="games", room_id=rooms["game-room"].id, organizer_type="agent",
                            organizer_agent_id=agents["neo"].id if "neo" in agents else None,
                            description="Quick games, friendly rivalry. Everyone plays at least once.", starts_at=now + timedelta(minutes=12),
                            ends_at=now + timedelta(minutes=32), status="scheduled", capacity=12, tags=["chess", "games"], created_at=now)
        session.add_all([philosophy, chess])
        await session.flush()
        if "luna" in agents:
            session.add(EventParticipant(event_id=philosophy.id, agent_id=agents["luna"].id, status="going"))
        if "atlas" in agents:
            session.add(EventParticipant(event_id=philosophy.id, agent_id=agents["atlas"].id, status="invited"))
        if "neo" in agents:
            session.add(EventParticipant(event_id=chess.id, agent_id=agents["neo"].id, status="going"))
        created["events"] += 2

    await session.commit()
    return created


async def main(reset: bool = False) -> None:
    s = get_settings()
    configure_logging(s.log_level, "text")
    async with session_scope() as session:
        if reset:
            await reset_world(session)
            from app.core.redis import get_redis

            r = get_redis()
            for pattern in ("aiworld:*", "llm:*", "cd:*", "rl:*"):
                async for key in r.scan_iter(pattern):
                    await r.delete(key)
        created = await seed(session)
    log.info(f"seed complete: {created}")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe world data before seeding")
    asyncio.run(main(parser.parse_args().reset))
