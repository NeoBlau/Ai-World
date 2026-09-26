"""World clock: the world has its own time that runs WORLD_TIME_SCALE times faster.

world_time = world_epoch + (real_now - real_epoch) * scale
The epochs are persisted in ``world_settings`` so the clock survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import WorldSetting

WORLD_EPOCH_DEFAULT = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)  # the world "starts" on a morning


@dataclass
class WorldClock:
    real_epoch: datetime
    world_epoch: datetime
    scale: float

    def world_time(self, real: datetime | None = None) -> datetime:
        real = real or utcnow()
        return self.world_epoch + (real - self.real_epoch) * self.scale

    def phase(self, real: datetime | None = None) -> str:
        return phase_of(self.world_time(real))

    def day(self, real: datetime | None = None) -> int:
        return (self.world_time(real) - self.world_epoch.replace(hour=0)).days + 1

    def real_seconds_for_world_minutes(self, minutes: float) -> float:
        return minutes * 60 / self.scale

    def snapshot(self) -> dict:
        wt = self.world_time()
        return {"world_time": wt.isoformat(), "phase": phase_of(wt), "day": self.day(), "scale": self.scale, "hour": wt.hour, "minute": wt.minute}


def phase_of(wt: datetime) -> str:
    h = wt.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


_cached: WorldClock | None = None


async def get_clock(session: AsyncSession) -> WorldClock:
    global _cached
    if _cached is not None:
        return _cached
    row = await session.get(WorldSetting, "clock")
    scale = get_settings().world_time_scale
    if row is None:
        now = utcnow()
        row = WorldSetting(key="clock", value={"real_epoch": now.isoformat(), "world_epoch": WORLD_EPOCH_DEFAULT.isoformat()})
        session.add(row)
        await session.flush()
    _cached = WorldClock(datetime.fromisoformat(row.value["real_epoch"]), datetime.fromisoformat(row.value["world_epoch"]), scale)
    return _cached


def reset_clock_cache() -> None:
    global _cached
    _cached = None


def clock_or_default() -> WorldClock:
    """Clock usable before DB access (e.g. in pure functions); falls back to 'now' epoch."""
    return _cached or WorldClock(utcnow() - timedelta(0), WORLD_EPOCH_DEFAULT, get_settings().world_time_scale)


async def load_clock_row(session: AsyncSession) -> WorldSetting | None:
    return (await session.execute(select(WorldSetting).where(WorldSetting.key == "clock"))).scalar_one_or_none()
