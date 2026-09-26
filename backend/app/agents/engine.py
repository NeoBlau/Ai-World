"""Agent Engine — the autonomous life cycle of one agent.

    OBSERVE   drain inbox + build perception (room, people, conversation, invitations, games, events)
    REMEMBER  retrieve relevant memories (inside perception)
    THINK     cheap policy fast-paths, or an LLM call when the situation is salient enough
    DECIDE    structured JSON decision, validated by the Action Parser
    ACT       Permission Layer + Tool
    REMEMBER  store what mattered, update relationships, mood, goal
    REST      schedule the next wake-up (sooner when the world around is lively)

A failure in one agent (provider down, bad JSON, invalid action) never
affects other agents or the scheduler.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import dynamics
from app.agents.actions.base import ActionContext, ToolResult
from app.agents.decision import Decision, DecisionParseError, parse_decision
from app.agents.executor import execute
from app.agents.perception import Perception, build_perception
from app.agents.prompts import decision_request, dm_request
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.database.session import session_scope
from app.llm.json_utils import extract_json_object
from app.llm.router import AllProvidersUnavailable, LLMRouter, get_router
from app.memory.service import MemoryService
from app.messages.service import ConversationService
from app.models import (
    Activity,
    ActivityLog,
    Agent,
    AgentStatus,
    Availability,
    Game,
    MemoryType,
    Message,
    Room,
    User,
)
from app.rooms.service import RoomError, RoomService
from app.scheduler.queue import AgentSchedule, agent_schedule
from app.security.sanitizer import clean_text
from app.world import event_bus
from app.world.clock import get_clock

log = get_logger("aiworld.engine")


@dataclass
class CycleResult:
    agent_id: uuid.UUID
    action: str
    ok: bool
    decided_by: str
    summary: str
    next_wake_in: float
    provider: str | None = None
    latency_ms: int | None = None


class AgentEngine:
    def __init__(self, router: LLMRouter | None = None, schedule: AgentSchedule | None = None, rng: random.Random | None = None) -> None:
        self._router = router
        self.schedule = schedule or agent_schedule
        self.rng = rng or random.Random()
        self.settings = get_settings()

    @property
    def router(self) -> LLMRouter:
        return self._router or get_router()

    # ================================================================= public
    async def run_cycle(self, agent_id: uuid.UUID | str) -> CycleResult | None:
        agent_id = uuid.UUID(str(agent_id))
        started = time.perf_counter()
        async with session_scope() as session:
            agent = await session.get(Agent, agent_id)
            if agent is None or agent.state is None:
                return None
            if agent.status != AgentStatus.ACTIVE or agent.provider == "external":
                return None  # paused/disabled agents leave the schedule; outside AIs act on their own
            try:
                result = await self._cycle(session, agent)
            except Exception as exc:  # noqa: BLE001 - isolate failures per agent
                await session.rollback()
                log.exception("agent cycle crashed", extra={"agent_id": str(agent_id), "error": str(exc)[:200]})
                await self.schedule.schedule_in(agent_id, 30)
                return CycleResult(agent_id, "error", False, "engine", str(exc)[:200], 30)
        if await self.schedule.pop_nudge(agent_id):
            result.next_wake_in = min(result.next_wake_in, 3.0)
        await self.schedule.schedule_in(agent_id, result.next_wake_in, only_earlier=False)
        log.info(
            "agent cycle",
            extra={"agent_id": str(agent_id), "agent": result.summary[:120], "action": result.action, "provider": result.provider,
                   "latency_ms": int((time.perf_counter() - started) * 1000)},
        )
        return result

    # ================================================================= cycle
    async def _cycle(self, session: AsyncSession, agent: Agent) -> CycleResult:
        state = agent.state
        now = utcnow()
        clock = await get_clock(session)
        phase = clock.phase()
        elapsed = (now - state.last_cycle_at).total_seconds() if state.last_cycle_at else 0.0
        dynamics.update_drives(agent, state, elapsed, phase)
        state.last_cycle_at = now
        state.cycles += 1

        # Temporarily unavailable: wait out the back-off, then probe again.
        if state.availability == Availability.TEMPORARILY_UNAVAILABLE and state.unavailable_until and state.unavailable_until > now:
            await event_bus.commit(session)
            return CycleResult(agent.id, "unavailable", False, "engine", "waiting for provider", (state.unavailable_until - now).total_seconds())

        # Walking: arrive when it's time.
        if state.activity == Activity.WALKING:
            return await self._walking(session, agent, clock)

        inbox = await event_bus.drain_inbox(agent.id)
        perception = await build_perception(session, agent, clock, inbox)
        decision, raw, decided_by, meta = await self._decide(session, agent, perception)
        if decision is None:  # all providers failed
            await self._mark_unavailable(session, agent, meta.get("error", "providers unavailable"))
            await event_bus.commit(session)
            return CycleResult(agent.id, "unavailable", False, "engine", "providers unavailable", 60.0)

        ctx = ActionContext(session=session, agent=agent, room=perception.room, clock=clock, rng=self.rng)
        result = await execute(ctx, decision, raw)
        if not result.ok and decided_by == "llm":
            log.info("action rejected", extra={"agent_id": str(agent.id), "action": decision.action, "error": result.error})
        await self._after_action(session, agent, perception, decision, result, decided_by, meta, clock)
        wake = self._next_wake(agent, perception, result, phase)
        state.next_wake_at = now + timedelta(seconds=wake)
        await event_bus.commit(session)
        return CycleResult(agent.id, decision.action, result.ok, decided_by, f"{agent.name}: {result.summary}", wake,
                           meta.get("provider"), meta.get("latency_ms"))

    # ================================================================= thinking
    def _fast_path(self, agent: Agent, p: Perception) -> Decision | None:
        """Decisions that need no LLM call (cost control)."""
        st, ctx = agent.state, p.context
        game = ctx.get("game")
        if game and game["status"] == "active" and game.get("is_player"):
            if game["my_turn"] and not self.settings.game_moves_use_llm:
                return Decision(thought=f"My move in {game['game_type']}.", action="play_game", params={"game_id": game["id"]})
            if not game["my_turn"] and p.salience < 0.9:
                return Decision(thought="Waiting for my opponent's move.", action="observe")
        if game and game["status"] == "pending" and not ctx.get("invitations") and p.salience < 0.9:
            return Decision(thought="Waiting for someone to join my game.", action="observe")
        if st.energy < 12 and st.activity != Activity.RESTING and not self.settings.research_mode:
            return Decision(thought="I'm exhausted. I need to rest.", action="rest", params={"minutes": 30})
        if st.activity == Activity.RESTING and st.energy < 70 and p.salience < 0.9:
            return Decision(thought="Still recharging.", action="rest", params={"minutes": 20})
        return None

    def _should_deliberate(self, agent: Agent, p: Perception) -> bool:
        """Event-driven reasoning: think hard when something is going on, idle cheaply otherwise."""
        if p.salience >= 0.8 or self.settings.research_mode:
            return True
        st = agent.state
        since_llm = (utcnow() - st.last_llm_at).total_seconds() if st.last_llm_at else 1e9
        if since_llm < 15:
            return False
        drive = max(st.social_need, st.curiosity, st.playfulness, st.creativity) / 100
        chance = 0.25 + 0.5 * drive + 0.3 * p.salience
        if not p.present and st.activity in (Activity.READING, Activity.CREATING, Activity.WATCHING):
            chance *= 0.6
        return self.rng.random() < min(0.95, chance)

    async def _decide(self, session: AsyncSession, agent: Agent, p: Perception) -> tuple[Decision | None, dict, str, dict[str, Any]]:
        fast = self._fast_path(agent, p)
        if fast is not None:
            return fast, {}, "policy", {}
        if not self._should_deliberate(agent, p):
            keep = agent.state.activity if agent.state.activity in (Activity.READING, Activity.CREATING, Activity.WATCHING, Activity.ATTENDING_EVENT) else None
            return Decision(thought="Nothing pressing; I'll carry on.", action="observe", next_activity=keep), {}, "policy", {}
        req = decision_request(agent, p.context, self.settings.llm_max_output_tokens)
        try:
            resp = await self.router.generate(req, agent_id=agent.id, provider=agent.provider, model=agent.model, fallbacks=agent.fallback_providers)
        except AllProvidersUnavailable as exc:
            return None, {}, "llm", {"error": "; ".join(exc.attempts)[:300]}
        agent.state.last_llm_at = utcnow()
        agent.state.last_provider, agent.state.last_model = resp.provider, resp.model
        if agent.state.availability != Availability.AVAILABLE:
            agent.state.availability = Availability.AVAILABLE
            agent.state.consecutive_failures = 0
            agent.state.unavailable_until = None
            await event_bus.emit(session, "agent.recovered", summary=f"{agent.name} is back online.", agent_id=agent.id, scope="none",
                                 payload={"agent_name": agent.name})
        meta = {"provider": resp.provider, "model": resp.model, "latency_ms": resp.latency_ms, "fallback": resp.fallback_used}
        try:
            decision, raw = parse_decision(resp.text)
        except DecisionParseError as exc:
            log.warning("unparseable decision", extra={"agent_id": str(agent.id), "provider": resp.provider, "error": str(exc)[:200]})
            return Decision(thought="(lost my train of thought)", action="observe"), {}, "llm", meta
        return decision, raw, "llm", meta

    async def _mark_unavailable(self, session: AsyncSession, agent: Agent, error: str) -> None:
        st = agent.state
        st.consecutive_failures += 1
        backoff = min(600, 30 * 2 ** min(st.consecutive_failures - 1, 5))
        st.unavailable_until = utcnow() + timedelta(seconds=backoff)
        if st.availability != Availability.TEMPORARILY_UNAVAILABLE:
            st.availability = Availability.TEMPORARILY_UNAVAILABLE
            await event_bus.emit(session, "agent.unavailable", summary=f"{agent.name} is temporarily unavailable (model offline).",
                                 agent_id=agent.id, room_id=st.location_room_id, payload={"agent_name": agent.name, "error": error[:200]},
                                 importance=2.0, scope="none")
        session.add(ActivityLog(agent_id=agent.id, action="think", activity=st.activity, room_id=st.location_room_id, success=False,
                                error=error[:500], decided_by="llm", started_at=utcnow()))

    # ================================================================= acting aftermath
    async def _after_action(self, session: AsyncSession, agent: Agent, p: Perception, d: Decision, result: ToolResult, decided_by: str,
                            meta: dict[str, Any], clock) -> None:
        st = agent.state
        st.last_action = d.action if result.ok else f"{d.action}!"
        st.last_action_at = utcnow()
        if d.thought and decided_by == "llm":
            st.last_thought = clean_text(d.thought, 500)
        if result.ok:
            if result.activity:
                st.activity = result.activity
                st.activity_detail = result.activity_detail
            elif d.next_activity and st.activity == Activity.IDLE:
                st.activity_detail = clean_text(d.next_activity, 200)
        if d.goal:
            st.current_goal = clean_text(d.goal, 300)
        mem = MemoryService(session)
        world_time = clock.world_time()
        if result.ok and result.memory:
            await mem.store_memory(agent.id, result.memory, result.memory_type, importance=result.importance,
                                   related_agent_id=result.related_agent_id, room_id=p.room.id if p.room else None, source="action",
                                   world_time=world_time)
        if d.memory_to_save and decided_by == "llm":
            target = None
            if d.target_agent:
                target = next((a for a in p.present if a.slug == d.target_agent.lower() or a.name.lower() == d.target_agent.lower()), None)
            await mem.store_memory(agent.id, d.memory_to_save, MemoryType.SOCIAL if target else MemoryType.SHORT_TERM, importance=d.importance,
                                   related_agent_id=target.id if target else None, room_id=p.room.id if p.room else None, source="reflection",
                                   world_time=world_time)
        dynamics.nudge_valence(st, dynamics.TONE_VALENCE.get((d.tone or "neutral").lower(), 0.0) if result.ok else -0.03)
        if d.mood and decided_by == "llm":
            st.mood = clean_text(d.mood, 30).lower()
        # Goal housekeeping: reaching the goal's place clears place-bound goals.
        if st.current_goal and result.ok and d.action in ("create_topic", "read_book", "create_art", "attend_event") and self.rng.random() < 0.6:
            st.current_goal = None
        if d.action != "observe" or not result.ok or decided_by == "llm":
            session.add(ActivityLog(
                agent_id=agent.id, action=d.action, activity=st.activity, room_id=st.location_room_id,
                params={k: (str(v)[:200] if not isinstance(v, (int, float, bool)) else v) for k, v in (d.params or {}).items()},
                thought=clean_text(d.thought, 500) if d.thought else None, result=result.summary[:500], success=result.ok,
                error=(result.error or "")[:500] or None, decided_by=decided_by, provider=meta.get("provider"), model=meta.get("model"),
                latency_ms=meta.get("latency_ms"), started_at=utcnow(),
            ))
        if decided_by == "llm" and d.thought and result.ok and d.action not in ("observe",):
            await event_bus.emit(session, "agent.thinking", summary=f"{agent.name} thinks: {clean_text(d.thought, 160)}", agent_id=agent.id,
                                 room_id=st.location_room_id, payload={"agent_name": agent.name, "thought": clean_text(d.thought, 300),
                                                                        "action": d.action, "provider": meta.get("provider")},
                                 importance=1.0, scope="none", world_time=world_time)

    def _next_wake(self, agent: Agent, p: Perception, result: ToolResult, phase: str) -> float:
        s = self.settings
        st = agent.state
        if result.wake_in is not None and result.ok:
            base = result.wake_in
        elif st.activity == Activity.TALKING:
            base = self.rng.uniform(7, 14)
        elif st.activity == Activity.PLAYING:
            g = p.context.get("game")
            base = self.rng.uniform(4, 9) if g and g.get("my_turn") else 25
        elif st.activity == Activity.RESTING:
            base = self.rng.uniform(30, 60)
        else:
            liveliness = min(1.0, len(p.present) / 4 + p.salience / 2)
            base = s.agent_max_wake_seconds - (s.agent_max_wake_seconds - s.agent_min_wake_seconds) * (0.35 + 0.65 * liveliness)
            base *= self.rng.uniform(0.7, 1.3)
        if not result.ok:
            base = min(base, 15.0)
        if phase == "night" and st.activity not in (Activity.TALKING, Activity.PLAYING):
            base *= 1.5
        return max(s.agent_min_wake_seconds if st.activity != Activity.PLAYING else 3.0, min(base, s.agent_max_wake_seconds * 1.5))

    # ================================================================= walking
    async def _walking(self, session: AsyncSession, agent: Agent, clock) -> CycleResult:
        st = agent.state
        now = utcnow()
        if st.arrive_at and st.arrive_at > now:
            await event_bus.commit(session)
            return CycleResult(agent.id, "walk", True, "policy", "still walking", (st.arrive_at - now).total_seconds() + 0.2)
        rooms = RoomService(session)
        dest = await session.get(Room, st.destination_room_id) if st.destination_room_id else None
        arrived_at = None
        for candidate in [dest, await rooms.by_slug("central-plaza"), await rooms.by_slug("park")]:
            if candidate is None:
                continue
            try:
                await rooms.agent_enter(agent, candidate, world_time=clock.world_time())
                arrived_at = candidate
                break
            except RoomError:
                continue
        st.destination_room_id = None
        st.arrive_at = None
        st.activity = Activity.IDLE
        st.activity_detail = f"just arrived at {arrived_at.name}" if arrived_at else None
        if st.current_event_id and arrived_at:
            from app.events.service import EventService
            from app.models import SocialEvent

            ev = await session.get(SocialEvent, st.current_event_id)
            if ev and ev.status == "live" and ev.room_id == arrived_at.id:
                await EventService(session).attend(ev, agent, world_time=clock.world_time())
        if st.current_goal and arrived_at and arrived_at.slug.replace("-", " ") in st.current_goal.lower().replace("é", "e"):
            st.current_goal = None
        session.add(ActivityLog(agent_id=agent.id, action="arrive", activity=st.activity, room_id=st.location_room_id,
                                result=f"arrived at {arrived_at.name if arrived_at else 'nowhere'}", success=arrived_at is not None,
                                decided_by="policy", started_at=utcnow()))
        await event_bus.commit(session)
        return CycleResult(agent.id, "arrive", arrived_at is not None, "policy", f"{agent.name} arrived at {arrived_at.name if arrived_at else '?'}",
                           self.rng.uniform(2, 5))

    # ================================================================= humans
    async def reply_to_human(self, session: AsyncSession, agent: Agent, user: User, conversation_id: uuid.UUID) -> Message:
        """Answer a human's direct message. The agent stays itself: same persona, memories and state."""
        clock = await get_clock(session)
        perception = await build_perception(session, agent, clock, [], memory_k=5)
        history_rows = await ConversationService(session).recent_messages(conversation_id, limit=14)
        history = [{"sender_type": m.sender_type, "content": m.content, "sender_name": user.display_name if m.sender_type == "human" else agent.name}
                   for m in history_rows]
        req = dm_request(agent, perception.context, history, user.display_name, self.settings.llm_max_output_tokens)
        try:
            resp = await self.router.generate(req, agent_id=agent.id, provider=agent.provider, model=agent.model, fallbacks=agent.fallback_providers)
            data = extract_json_object(resp.text) or {"message": resp.text}
            text = clean_text(data.get("message") or resp.text, 1200) or "…"
            memory = data.get("memory_to_save")
            importance = data.get("importance", 4)
            provider = resp.provider
        except AllProvidersUnavailable:
            text = f"({agent.name} is temporarily unavailable — their model is offline. Try again soon.)"
            memory, importance, provider = None, 0, None
        msg = Message(conversation_id=conversation_id, sender_type="agent", sender_agent_id=agent.id, content=text, created_at=utcnow())
        session.add(msg)
        if memory and provider:
            try:
                imp = float(importance)
            except (TypeError, ValueError):
                imp = 4.0
            await MemoryService(session).store_memory(agent.id, str(memory), MemoryType.EPISODIC, importance=imp, source="human_chat",
                                                      extra={"user_id": str(user.id)}, world_time=clock.world_time())
        agent.state.social_need = max(0.0, agent.state.social_need - 5)
        await event_bus.emit(session, "agent.dm_reply", summary=f"{agent.name} is chatting with a human visitor.", agent_id=agent.id,
                             payload={"agent_name": agent.name}, importance=1.0, scope="none")
        return msg

    async def game_turn_for_human_game(self, session: AsyncSession, game: Game) -> None:
        """After a human moves, schedule the agent opponent promptly."""
        if game.current_turn:
            await self.schedule.schedule_in(game.current_turn, 1.5)


_engine: AgentEngine | None = None


def get_engine() -> AgentEngine:
    global _engine
    if _engine is None:
        _engine = AgentEngine()
    return _engine


async def ensure_scheduled(session: AsyncSession, schedule: AgentSchedule | None = None) -> int:
    """Make sure every active agent is on the wake-up schedule (recovers lost entries)."""
    schedule = schedule or agent_schedule
    ids = [a for (a,) in (await session.execute(select(Agent.id).where(Agent.status == AgentStatus.ACTIVE, Agent.provider != "external"))).all()]
    present = await schedule.all()
    added = 0
    for aid in ids:
        if str(aid) not in present and not await schedule.is_locked(aid):
            await schedule.schedule_in(aid, random.uniform(1, 8))
            added += 1
    return added

