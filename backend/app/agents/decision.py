"""Structured decision contract between the LLM and the engine (the Action Parser)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.llm.json_utils import extract_json_object

DECISION_FIELDS = {"thought", "action", "params", "message", "target_agent", "memory_to_save", "importance", "tone", "next_activity", "goal", "mood", "topic"}

DECISION_SCHEMA_HINT = (
    '{"thought": "private reasoning, 1-2 sentences", "action": "<one action name>", "params": {...}, '
    '"message": "what you say out loud, or null", "target_agent": "slug or null", "memory_to_save": "something worth remembering, or null", '
    '"importance": 1-10, "tone": "friendly|curious|playful|neutral|tense|hostile", "next_activity": "short phrase", '
    '"goal": "your current goal (optional)", "mood": "one word (optional)"}'
)


class DecisionParseError(ValueError):
    pass


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    thought: str = Field(default="", max_length=3000)
    action: str = Field(max_length=60)
    params: dict[str, Any] = Field(default_factory=dict)
    message: str | None = Field(default=None, max_length=5000)
    target_agent: str | None = Field(default=None, max_length=80)
    memory_to_save: str | None = Field(default=None, max_length=2000)
    importance: float = 3.0
    tone: str | None = Field(default="neutral", max_length=30)
    next_activity: str | None = Field(default=None, max_length=200)
    goal: str | None = Field(default=None, max_length=300)
    mood: str | None = Field(default=None, max_length=30)
    topic: str | None = Field(default=None, max_length=200)

    @field_validator("importance", mode="before")
    @classmethod
    def _imp(cls, v: Any) -> float:
        try:
            return max(1.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return 3.0

    @field_validator("params", mode="before")
    @classmethod
    def _params(cls, v: Any) -> dict[str, Any]:
        return v if isinstance(v, dict) else {}

    @field_validator("message", "target_agent", "memory_to_save", "goal", "mood", "next_activity", "topic", mode="before")
    @classmethod
    def _nullish(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a"):
            return None
        return v if isinstance(v, str) else str(v)


def parse_decision(text: str) -> tuple[Decision, dict[str, Any]]:
    raw = extract_json_object(text)
    if raw is None:
        raise DecisionParseError("no JSON object in model output")
    if "action" not in raw:
        for alt in ("tool", "name", "act"):
            if alt in raw:
                raw["action"] = raw[alt]
                break
    if isinstance(raw.get("action"), dict):  # {"action": {"name": ..., "params": ...}}
        inner = raw["action"]
        raw["action"] = inner.get("name") or inner.get("type")
        raw.setdefault("params", inner.get("params") or {})
    try:
        return Decision.model_validate(raw), raw
    except ValidationError as exc:
        raise DecisionParseError(str(exc)[:300]) from exc


MESSAGE_KEYS = {
    "talk": "message", "meet_agent": "message", "leave_conversation": "message", "respond_invitation": "message",
    "invite_agent": "message", "reply_topic": "content", "create_note": "content",
    "propose_law": "text", "vote_law": "reason", "perform": "details", "write_book": "content", "give_item": "note",
    "play_invented_game": "move", "finish_invented_game": "result",
}
TARGET_KEYS = {"talk": "target_agent", "meet_agent": "target_agent", "invite_agent": "target_agent", "play_game": "opponent",
               "give_item": "target_agent", "home_guest": "target_agent"}


def build_params(decision: Decision, raw: dict[str, Any], tool_name: str) -> dict[str, Any]:
    params = dict(decision.params)
    # Models often put params at the top level; accept them.
    for k, v in raw.items():
        if k not in DECISION_FIELDS and k not in params:
            params[k] = v
    mk = MESSAGE_KEYS.get(tool_name)
    if mk and decision.message and not params.get(mk):
        params[mk] = decision.message
    tk = TARGET_KEYS.get(tool_name)
    if tk and decision.target_agent and not params.get(tk):
        params[tk] = decision.target_agent
    if tool_name == "respond_invitation" and "accept" not in params:
        params["accept"] = str(decision.action).lower() not in ("decline", "decline_invitation")
    return params
