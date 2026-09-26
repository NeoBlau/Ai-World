"""Fixed-window rate limiting backed by Redis."""

from __future__ import annotations

import time

from app.core.redis import get_redis


async def hit(key: str, limit: int, window_seconds: int) -> bool:
    """Record a hit; return True if still within ``limit`` for the current window."""
    bucket = int(time.time() // window_seconds)
    k = f"rl:{key}:{bucket}"
    r = get_redis()
    pipe = r.pipeline()
    pipe.incr(k)
    pipe.expire(k, window_seconds + 1)
    count, _ = await pipe.execute()
    return int(count) <= limit


async def cooldown_active(key: str) -> bool:
    return bool(await get_redis().exists(f"cd:{key}"))


async def start_cooldown(key: str, seconds: float) -> None:
    if seconds > 0:
        await get_redis().set(f"cd:{key}", "1", px=int(seconds * 1000))
