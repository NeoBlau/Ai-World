"""Action registry: the complete whitelist of things an agent may do."""

from __future__ import annotations

from app.agents.actions.base import Tool
from app.agents.actions.tools import ALL_TOOLS

REGISTRY: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}

# Friendly aliases models sometimes produce.
ALIASES = {
    "say": "talk", "speak": "talk", "chat": "talk", "reply": "talk", "respond": "talk", "move": "walk", "go": "walk", "go_to": "walk",
    "goto": "walk", "enter_room": "join_room", "post_topic": "create_topic", "new_topic": "create_topic", "comment": "reply_topic",
    "play": "play_game", "start_game": "play_game", "make_move": "play_game", "read": "read_book", "paint": "create_art", "draw": "create_art",
    "write": "create_note", "write_note": "create_note", "sleep": "rest", "wait": "observe", "idle": "observe", "listen": "observe",
    "introduce": "meet_agent", "meet": "meet_agent", "invite": "invite_agent", "attend": "attend_event", "join_event": "attend_event",
    "accept_invitation": "respond_invitation", "decline_invitation": "respond_invitation", "decline": "respond_invitation",
    "accept": "respond_invitation", "leave": "leave_conversation", "end_conversation": "leave_conversation", "goodbye": "leave_conversation",
    "upvote": "vote_topic", "vote": "vote_topic", "bookmark": "save_topic", "organize_event": "create_event", "organise_event": "create_event",
}


def resolve_action(name: str | None) -> Tool | None:
    if not name:
        return None
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    key = ALIASES.get(key, key)
    return REGISTRY.get(key)


def action_specs(names: list[str] | None = None) -> list[dict[str, str]]:
    return [t.spec() for n, t in REGISTRY.items() if names is None or n in names]
