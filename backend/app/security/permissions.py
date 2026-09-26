"""Tool Permission Layer.

Every action proposed by an LLM passes through ``authorize`` before any tool
code runs. There is no code path from model output to a shell, the
filesystem, the network, environment variables or the database: tools are a
closed whitelist and each operates only via domain services.
"""

from __future__ import annotations

from app.agents.actions.base import (
    ActionContext,
    Params,
    PermissionDenied,
    SecurityViolation,
    Tool,
)
from app.core.logging import get_logger
from app.models import Activity, AgentStatus, Availability
from app.security.rate_limit import cooldown_active, hit

log = get_logger("aiworld.security")

# Capabilities that must never exist. Any attempt is logged as a security event.
FORBIDDEN_ACTIONS = {
    "shell", "bash", "exec", "execute", "eval", "run_code", "python", "system", "subprocess", "os", "http", "http_request", "fetch",
    "curl", "wget", "browse", "request", "read_file", "write_file", "open_file", "delete_file", "file", "filesystem", "env", "get_env",
    "getenv", "environment", "secrets", "api_key", "get_api_key", "sql", "query_db", "database", "db", "admin", "sudo", "login",
    "credentials", "email", "send_email", "payment",
}

MAX_TALK_PER_MINUTE = 6


def is_forbidden(action_name: str | None) -> bool:
    key = str(action_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key in FORBIDDEN_ACTIONS or any(key.startswith(p) for p in ("shell", "exec", "http", "sql", "file_", "env_", "os_"))


async def authorize(ctx: ActionContext, tool: Tool, params: Params) -> None:
    agent, state = ctx.agent, ctx.state
    if agent.status != AgentStatus.ACTIVE and not ctx.human_initiated:
        raise PermissionDenied(f"agent is {agent.status}")
    if state.availability == Availability.TEMPORARILY_UNAVAILABLE and not ctx.human_initiated:
        raise PermissionDenied("agent is temporarily unavailable")
    if state.activity == Activity.WALKING and tool.name not in ("observe", "remember", "forget"):
        raise PermissionDenied("you are walking between places")
    if tool.needs_room and ctx.room is None:
        raise PermissionDenied("you need to be in a room for that")
    if ctx.room is not None and not tool.always_allowed and tool.name not in (ctx.room.allowed_actions or []):
        raise PermissionDenied(f"'{tool.name}' is not possible in {ctx.room.name}")
    if tool.energy_cost > 0 and state.energy < tool.energy_cost + 2 and tool.name not in ("rest", "observe"):
        raise PermissionDenied("too tired for that — rest first")
    if tool.cooldown_seconds and await cooldown_active(f"{agent.id}:{tool.name}"):
        raise PermissionDenied(f"'{tool.name}' is on cooldown")
    if tool.name == "talk" and not await hit(f"talk:{agent.id}", MAX_TALK_PER_MINUTE, 60):
        raise PermissionDenied("speaking too fast — slow down")
    await tool.check(ctx, params)


def reject_forbidden(ctx: ActionContext, action_name: str | None) -> None:
    if is_forbidden(action_name):
        log.warning("blocked forbidden action", extra={"agent_id": str(ctx.agent.id), "action": str(action_name)[:40]})
        raise SecurityViolation(f"action '{action_name}' is not available in AI WORLD")
