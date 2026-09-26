"""LLM-backed summarisers with cost control and offline fallback."""

from __future__ import annotations

from typing import Any

from app.agents.prompts import conversation_summary_request, memory_summary_request
from app.llm.json_utils import extract_json_object
from app.llm.router import AllProvidersUnavailable, get_router
from app.models import Agent, Conversation, Room

# Short conversations are summarised by the free local engine; long ones deserve a real model.
MIN_MESSAGES_FOR_LLM = 6


async def conversation_summarizer(conversation: Conversation, transcript: list[dict[str, Any]], agent: Agent) -> dict[str, Any]:
    from sqlalchemy import inspect

    location = None
    sess = inspect(conversation).session
    if sess is not None and conversation.room_id:
        room = await sess.get(Room, conversation.room_id)
        location = room.name if room else None
    req = conversation_summary_request(agent, transcript, location)
    provider = agent.provider if len(transcript) >= MIN_MESSAGES_FOR_LLM else "sim"
    try:
        resp = await get_router().generate(req, agent_id=agent.id, provider=provider, model=agent.model if provider == agent.provider else None,
                                           fallbacks=agent.fallback_providers)
    except AllProvidersUnavailable:
        return {}
    data = extract_json_object(resp.text) or {}
    facts = data.get("facts") if isinstance(data.get("facts"), list) else []
    return {"summary": str(data.get("summary") or "")[:500], "facts": [str(f)[:200] for f in facts[:3]], "topic": data.get("topic")}


def memory_summarizer_for(agent: Agent):
    async def _summarize(items: list[dict[str, Any]]) -> tuple[str | None, float | None]:
        req = memory_summary_request(agent, items)
        try:
            resp = await get_router().generate(req, agent_id=agent.id, provider=agent.provider, model=agent.model, fallbacks=agent.fallback_providers)
        except AllProvidersUnavailable:
            return None, None
        data = extract_json_object(resp.text) or {}
        summary = data.get("summary")
        try:
            imp = float(data.get("importance", 5))
        except (TypeError, ValueError):
            imp = 5.0
        return (str(summary)[:600] if summary else None), imp

    return _summarize
