"""Request bodies (validated at the API boundary)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROVIDERS = ("openai", "anthropic", "gemini", "ollama", "sim")
STYLES = ("enthusiastic", "warm", "analytical", "dreamy", "skeptical", "playful", "laconic", "gentle")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$"


class RegisterIn(Strict):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=40)


class LoginIn(Strict):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class Traits(Strict):
    extraversion: float = Field(0.5, ge=0, le=1)
    openness: float = Field(0.5, ge=0, le=1)
    agreeableness: float = Field(0.5, ge=0, le=1)
    conscientiousness: float = Field(0.5, ge=0, le=1)
    neuroticism: float = Field(0.3, ge=0, le=1)
    playfulness: float = Field(0.5, ge=0, le=1)
    creativity: float = Field(0.5, ge=0, le=1)


class AgentCreateIn(Strict):
    name: str = Field(min_length=2, max_length=40)
    provider: Literal["openai", "anthropic", "gemini", "ollama", "sim"] = "sim"
    model: str | None = Field(default=None, max_length=120)
    temperature: float = Field(0.8, ge=0, le=1.5)
    personality: str = Field(min_length=3, max_length=200)
    character: str = Field(default="", max_length=1000)
    biography: str = Field(default="", max_length=2000)
    interests: list[str] = Field(default_factory=list, max_length=8)
    speaking_style: Literal["enthusiastic", "warm", "analytical", "dreamy", "skeptical", "playful", "laconic", "gentle"] = "warm"
    system_prompt: str = Field(default="", max_length=2000)
    fallback_providers: list[Literal["openai", "anthropic", "gemini", "ollama", "sim"]] = Field(default_factory=list, max_length=5)
    traits: Traits = Field(default_factory=Traits)
    start_room: str = Field(default="central-plaza", max_length=60)
    goal: str | None = Field(default=None, max_length=300)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("interests")
    @classmethod
    def _interests(cls, v: list[str]) -> list[str]:
        return [i.strip()[:40] for i in v if i.strip()]


class AgentUpdateIn(Strict):
    provider: Literal["openai", "anthropic", "gemini", "ollama", "sim"] | None = None
    model: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=1.5)
    personality: str | None = Field(default=None, min_length=3, max_length=200)
    character: str | None = Field(default=None, max_length=1000)
    biography: str | None = Field(default=None, max_length=2000)
    interests: list[str] | None = Field(default=None, max_length=8)
    speaking_style: Literal["enthusiastic", "warm", "analytical", "dreamy", "skeptical", "playful", "laconic", "gentle"] | None = None
    system_prompt: str | None = Field(default=None, max_length=2000)
    fallback_providers: list[Literal["openai", "anthropic", "gemini", "ollama", "sim"]] | None = None
    goal: str | None = Field(default=None, max_length=300)


class ChatIn(Strict):
    message: str = Field(min_length=1, max_length=1000)


class RoomMessageIn(Strict):
    message: str = Field(min_length=1, max_length=1000)
    target_agent: str | None = Field(default=None, max_length=80)


class RoomCreateIn(Strict):
    name: str = Field(min_length=3, max_length=60)
    description: str = Field(default="", max_length=600)
    capacity: int = Field(8, ge=2, le=40)
    is_private: bool = False
    allowed_actions: list[str] = Field(default_factory=lambda: ["talk", "meet_agent", "invite_agent", "create_note"], max_length=20)
    invite_agents: list[str] = Field(default_factory=list, max_length=12)


class TopicIn(Strict):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=4000)
    category: str = Field(default="general", max_length=30)


class ReplyIn(Strict):
    content: str = Field(min_length=1, max_length=3000)


class VoteIn(Strict):
    value: Literal[1, -1] = 1


class EventIn(Strict):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="social", max_length=30)
    room: str = Field(max_length=60)
    starts_in_minutes: float = Field(10, ge=1, le=24 * 60)
    duration_minutes: int = Field(30, ge=5, le=240)
    tags: list[str] = Field(default_factory=list, max_length=6)
    invite_agents: list[str] = Field(default_factory=list, max_length=12)


class GameIn(Strict):
    game_type: Literal["chess", "tictactoe", "quiz"]
    opponent: str = Field(max_length=80)


class MoveIn(Strict):
    move: str = Field(min_length=1, max_length=20)


class EnterRoomIn(Strict):
    room: str = Field(max_length=60)
