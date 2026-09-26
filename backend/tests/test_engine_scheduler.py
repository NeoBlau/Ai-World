import time

from sqlalchemy import select

from app.agents.engine import AgentEngine
from app.llm.base import LLMProvider, ProviderError
from app.llm.router import LLMRouter
from app.models import ActivityLog, AgentStatus, Availability, WorldEvent
from app.scheduler.queue import AgentSchedule
from app.scheduler.worker import Worker
from tests.conftest import get_agent


async def test_schedule_claim_nudge_lock(_clean):
    sch = AgentSchedule()
    await sch.schedule("a", time.time() - 1)
    await sch.schedule("b", time.time() + 100)
    await sch.nudge("b", 50)  # only earlier
    assert await sch.next_wake("b") < time.time() + 60
    await sch.nudge("b", 500)
    assert await sch.next_wake("b") < time.time() + 60
    assert await sch.claim_due(10) == ["a"]
    assert await sch.claim_due(10) == []  # claimed atomically, gone
    tok = await sch.acquire("a")
    assert tok and await sch.acquire("a") is None
    await sch.release("a", tok)
    assert await sch.acquire("a")


async def test_engine_cycle_acts_and_logs(world):
    alex = await get_agent(world, "alex")
    engine = AgentEngine()
    for _ in range(3):
        res = await engine.run_cycle(alex.id)
        assert res is not None and res.next_wake_in > 0
    async with __import__("app.database.session", fromlist=["x"]).session_scope() as s:
        logs = (await s.execute(select(ActivityLog).where(ActivityLog.agent_id == alex.id))).scalars().all()
        events = (await s.execute(select(WorldEvent))).scalars().all()
    assert logs and events


class DownProvider(LLMProvider):
    name = "openai"

    def is_configured(self):
        return True

    @property
    def default_model(self):
        return "x"

    async def _generate(self, request, model):
        raise ProviderError("openai", "down")


async def test_provider_outage_marks_unavailable_and_world_continues(world):
    from app.core.config import Settings

    router = LLMRouter(Settings(allow_sim_fallback=False, llm_fallback_chain=""), providers={"openai": DownProvider()})

    async def noop(rec):
        return None

    router.persist = noop
    engine = AgentEngine(router=router)
    alex = await get_agent(world, "alex")
    alex.state.social_need = 100
    alex.state.current_goal = None
    await world.commit()
    for _ in range(4):  # some cycles may take the cheap policy path first
        await engine.run_cycle(alex.id)
    await world.refresh(alex.state)
    assert alex.state.availability == Availability.TEMPORARILY_UNAVAILABLE
    # other agents are unaffected (they use the default sim-backed router)
    neo = await get_agent(world, "neo")
    assert (await AgentEngine().run_cycle(neo.id)) is not None


async def test_worker_step_runs_due_agents(world):
    sch = AgentSchedule()
    alex = await get_agent(world, "alex")
    await sch.schedule(alex.id, time.time() - 1)
    w = Worker(schedule=sch, concurrency=2)
    assert await w.step() == 1
    import asyncio

    await asyncio.wait(w.running, timeout=30)
    assert w.cycles == 1
    assert await sch.next_wake(alex.id) is not None  # rescheduled itself


async def test_paused_agent_is_skipped(world):
    alex = await get_agent(world, "alex")
    alex.status = AgentStatus.PAUSED
    await world.commit()
    assert await AgentEngine().run_cycle(alex.id) is None
