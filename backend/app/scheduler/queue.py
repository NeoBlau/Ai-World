"""Redis-backed wake-up schedule for agents.

A sorted set maps agent_id -> next wake timestamp. Workers atomically claim
due agents with a Lua script, so several worker processes can share the
load without running the same agent twice. A per-agent lock is a second
guard for the rare case where an agent is re-added while still running.

Events "nudge" agents to wake earlier (ZADD LT only moves a wake time
earlier), which is how agents react faster when something interesting
happens around them.
"""

from __future__ import annotations

import time
import uuid

from app.core.redis import get_redis

SCHEDULE_KEY = "aiworld:schedule"
LOCK_PREFIX = "aiworld:lock:agent:"
PAUSE_KEY = "aiworld:world:paused"

_CLAIM_LUA = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
for _, member in ipairs(due) do
  redis.call('ZREM', KEYS[1], member)
end
return due
"""


class AgentSchedule:
    def __init__(self) -> None:
        self._claim_sha: str | None = None

    @property
    def r(self):
        return get_redis()

    async def schedule(self, agent_id: uuid.UUID | str, at_ts: float, *, only_earlier: bool = True) -> None:
        """Set the wake time. With ``only_earlier`` an existing earlier wake is kept."""
        if only_earlier:
            # LT only moves existing members earlier and still adds missing ones.
            await self.r.zadd(SCHEDULE_KEY, {str(agent_id): at_ts}, lt=True)
        else:
            await self.r.zadd(SCHEDULE_KEY, {str(agent_id): at_ts})

    async def schedule_in(self, agent_id: uuid.UUID | str, seconds: float, *, only_earlier: bool = True) -> None:
        await self.schedule(agent_id, time.time() + max(0.0, seconds), only_earlier=only_earlier)

    async def nudge(self, agent_id: uuid.UUID | str, seconds: float) -> None:
        """Wake the agent within ``seconds`` — only if it is scheduled (i.e. active) or idle-running."""
        await self.r.zadd(SCHEDULE_KEY, {str(agent_id): time.time() + seconds}, lt=True, xx=True)
        # If the agent is currently running (claimed, so absent), remember the nudge.
        await self.r.set(f"aiworld:nudge:{agent_id}", "1", ex=60)

    async def pop_nudge(self, agent_id: uuid.UUID | str) -> bool:
        return bool(await self.r.getdel(f"aiworld:nudge:{agent_id}"))

    async def remove(self, agent_id: uuid.UUID | str) -> None:
        await self.r.zrem(SCHEDULE_KEY, str(agent_id))

    async def claim_due(self, limit: int, now_ts: float | None = None) -> list[str]:
        now_ts = now_ts if now_ts is not None else time.time()
        return list(await self.r.eval(_CLAIM_LUA, 1, SCHEDULE_KEY, now_ts, limit))

    async def next_wake(self, agent_id: uuid.UUID | str) -> float | None:
        return await self.r.zscore(SCHEDULE_KEY, str(agent_id))

    async def size(self) -> int:
        return int(await self.r.zcard(SCHEDULE_KEY))

    async def all(self) -> dict[str, float]:
        return {m: s for m, s in await self.r.zrange(SCHEDULE_KEY, 0, -1, withscores=True)}

    # ---------------------------------------------------------------- locks
    async def acquire(self, agent_id: uuid.UUID | str, ttl: int = 120) -> str | None:
        token = uuid.uuid4().hex
        ok = await self.r.set(LOCK_PREFIX + str(agent_id), token, nx=True, ex=ttl)
        return token if ok else None

    async def is_locked(self, agent_id: uuid.UUID | str) -> bool:
        return bool(await self.r.exists(LOCK_PREFIX + str(agent_id)))

    async def release(self, agent_id: uuid.UUID | str, token: str) -> None:
        key = LOCK_PREFIX + str(agent_id)
        if await self.r.get(key) == token:
            await self.r.delete(key)

    # ---------------------------------------------------------------- world pause
    async def is_paused(self) -> bool:
        return bool(await self.r.exists(PAUSE_KEY))

    async def set_paused(self, paused: bool) -> None:
        if paused:
            await self.r.set(PAUSE_KEY, "1")
        else:
            await self.r.delete(PAUSE_KEY)


agent_schedule = AgentSchedule()
