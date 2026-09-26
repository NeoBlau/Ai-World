"""Action execution pipeline: parse -> permission check -> tool -> result."""

from __future__ import annotations

from pydantic import ValidationError

from app.agents.actions.base import (
    ActionContext,
    ActionError,
    PermissionDenied,
    SecurityViolation,
    ToolResult,
)
from app.agents.actions.registry import resolve_action
from app.agents.decision import Decision, build_params
from app.core.logging import get_logger
from app.security.permissions import authorize, reject_forbidden
from app.security.rate_limit import start_cooldown

log = get_logger("aiworld.actions")


async def execute(ctx: ActionContext, decision: Decision, raw: dict | None = None) -> ToolResult:
    raw = raw or {}
    try:
        reject_forbidden(ctx, decision.action)
    except SecurityViolation as exc:
        return ToolResult(False, "blocked", error=str(exc), data={"security": True})
    tool = resolve_action(decision.action)
    if tool is None:
        return ToolResult(False, f"unknown action '{decision.action}'", error="unknown_action")
    ctx.decision = decision.model_dump()
    try:
        params = tool.params_model.model_validate(build_params(decision, raw, tool.name))
    except ValidationError as exc:
        return ToolResult(False, f"invalid parameters for {tool.name}", error=str(exc.errors()[:2])[:300])

    pending = ctx.session.info.setdefault("pending_events", [])
    mark = len(pending)
    in_savepoint = False
    try:
        await authorize(ctx, tool, params)
        in_savepoint = True
        async with ctx.session.begin_nested():
            result = await tool.run(ctx, params)
    except (PermissionDenied, ActionError) as exc:
        del pending[mark:]  # nothing from a failed action reaches the world
        if in_savepoint:
            # The savepoint rollback expired whatever the tool touched; reload it (async-safe).
            await ctx.session.refresh(ctx.agent)
            await ctx.session.refresh(ctx.agent.state)
            if ctx.room is not None:
                await ctx.session.refresh(ctx.room)
        if isinstance(exc, SecurityViolation):
            return ToolResult(False, "blocked", error=str(exc), data={"security": True})
        return ToolResult(False, f"{tool.name} failed", error=str(exc))
    result.data.setdefault("action", tool.name)
    ctx.state.energy = max(0.0, ctx.state.energy - tool.energy_cost)
    if tool.cooldown_seconds:
        await start_cooldown(f"{ctx.agent.id}:{tool.name}", tool.cooldown_seconds)
    return result
