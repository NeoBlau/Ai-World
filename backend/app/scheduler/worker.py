"""Background worker: wakes agents on schedule and runs world maintenance.

Run with:  python -m app.scheduler.worker

Several workers can run side by side: due agents are claimed atomically
from Redis, each agent is protected by a lock, and maintenance runs under a
single-owner lease. Nothing here runs inside an HTTP request.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import time

from app.agents.engine import AgentEngine, ensure_scheduled
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis, get_redis
from app.database.session import dispose_engine, session_scope
from app.scheduler.maintenance import Maintenance
from app.scheduler.queue import AgentSchedule, agent_schedule

log = get_logger("aiworld.worker")


class Worker:
    def __init__(self, engine: AgentEngine | None = None, schedule: AgentSchedule | None = None, concurrency: int | None = None,
                 tick: float | None = None) -> None:
        s = get_settings()
        self.engine = engine or AgentEngine()
        self.schedule = schedule or agent_schedule
        self.concurrency = concurrency or s.scheduler_concurrency
        self.tick = tick or s.scheduler_tick_seconds
        self.maintenance = Maintenance()
        self.name = f"{socket.gethostname()}:{os.getpid()}"
        self.running: set[asyncio.Task] = set()
        self.cycles = 0
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def _run_agent(self, agent_id: str) -> None:
        token = await self.schedule.acquire(agent_id)
        if token is None:
            await self.schedule.schedule_in(agent_id, 3)
            return
        try:
            await self.engine.run_cycle(agent_id)
            self.cycles += 1
        except Exception:  # noqa: BLE001 - never let one agent kill the worker
            log.exception("agent task failed", extra={"agent_id": agent_id})
            await self.schedule.schedule_in(agent_id, 30)
        finally:
            await self.schedule.release(agent_id, token)

    async def step(self) -> int:
        """One scheduler tick. Returns number of agents started."""
        if await self.schedule.is_paused():
            return 0
        capacity = self.concurrency - len(self.running)
        if capacity <= 0:
            return 0
        started = 0
        for agent_id in await self.schedule.claim_due(capacity):
            task = asyncio.create_task(self._run_agent(agent_id))
            self.running.add(task)
            task.add_done_callback(self.running.discard)
            started += 1
        return started

    async def heartbeat(self) -> None:
        await get_redis().set(f"aiworld:worker:{self.name}", str(time.time()), ex=20)

    async def run(self) -> None:
        log.info("worker starting", extra={"event": self.name})
        async with session_scope() as session:
            added = await ensure_scheduled(session, self.schedule)
        log.info("agents scheduled", extra={"event": f"{added} added"})
        last_maint = 0.0
        last_beat = 0.0
        while not self._stop.is_set():
            try:
                await self.step()
                now = time.monotonic()
                if now - last_beat > 5:
                    await self.heartbeat()
                    last_beat = now
                if now - last_maint > 5 and await self.maintenance.acquire_lease(self.name):
                    last_maint = now
                    stats = await self.maintenance.run_once()
                    if any(stats.values()):
                        log.info("maintenance", extra={"event": str(stats)})
            except Exception:  # noqa: BLE001
                log.exception("scheduler loop error")
                await asyncio.sleep(2)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick)
            except asyncio.TimeoutError:
                pass
        if self.running:
            await asyncio.wait(self.running, timeout=30)
        log.info("worker stopped")


async def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_format)
    s.assert_safe_for_production()
    worker = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:  # pragma: no cover - windows
            pass
    try:
        await worker.run()
    finally:
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
