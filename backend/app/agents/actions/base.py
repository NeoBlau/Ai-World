"""Tool (action) framework.

An LLM never executes anything. It *names* an action from a fixed whitelist
and supplies parameters. The flow is always:

    LLM output -> ActionParser -> PermissionLayer -> Tool.run -> ToolResult

Tools only touch the world through the domain services (rooms, messages,
games, ...). None of them can reach the shell, the filesystem, the network,
environment variables or raw SQL.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, AgentState, Room, RoomMember
from app.world.clock import WorldClock


class ActionError(Exception):
    """The action was allowed but could not be carried out (e.g. target left)."""


class PermissionDenied(Exception):
    """The action is not permitted for this agent right now."""


class SecurityViolation(PermissionDenied):
    """The model attempted something categorically forbidden (shell, secrets, ...)."""


class Params(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class NoParams(Params):
    pass


@dataclass
class ToolResult:
    ok: bool
    summary: str
    activity: str | None = None
    activity_detail: str | None = None
    memory: str | None = None
    memory_type: str = "episodic"
    importance: float = 3.0
    related_agent_id: uuid.UUID | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    wake_in: float | None = None  # suggested seconds until next cycle


@dataclass
class ActionContext:
    session: AsyncSession
    agent: Agent
    room: Room | None
    clock: WorldClock
    rng: random.Random = field(default_factory=random.Random)
    decision: dict[str, Any] = field(default_factory=dict)
    human_initiated: bool = False

    @property
    def state(self) -> AgentState:
        return self.agent.state

    @property
    def world_time(self):
        return self.clock.world_time()

    async def resolve_agent(self, ref: str | None, *, must_be_present: bool = False) -> Agent | None:
        """Resolve an agent by id, slug or name. Returns None if unknown."""
        if not ref:
            return None
        ref = str(ref).strip().lstrip("@")
        agent: Agent | None = None
        try:
            agent = await self.session.get(Agent, uuid.UUID(ref))
        except ValueError:
            pass
        if agent is None:
            key = ref.lower()
            rows = await self.session.execute(select(Agent).where((Agent.slug == key) | (Agent.name.ilike(ref))))
            agent = rows.scalars().first()
        if agent is None or agent.id == self.agent.id:
            return None
        if must_be_present:
            if self.room is None:
                return None
            present = await self.session.execute(
                select(RoomMember.id).where(RoomMember.room_id == self.room.id, RoomMember.agent_id == agent.id, RoomMember.left_at.is_(None))
            )
            if present.first() is None:
                return None
        return agent


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    params_model: ClassVar[type[Params]] = NoParams
    energy_cost: ClassVar[float] = 0.5
    cooldown_seconds: ClassVar[float] = 0.0
    always_allowed: ClassVar[bool] = False  # not restricted by the room's allowed_actions
    needs_room: ClassVar[bool] = True
    param_hint: ClassVar[str] = "{}"

    async def check(self, ctx: ActionContext, params: Params) -> None:  # noqa: B027 - optional hook
        """Tool-specific permission checks. Raise PermissionDenied."""

    async def run(self, ctx: ActionContext, params: Params) -> ToolResult:
        raise NotImplementedError

    def spec(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description, "params": self.param_hint}
