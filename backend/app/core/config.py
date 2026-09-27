"""Application settings loaded from environment variables (.env).

Secrets (API keys, JWT secret) are only ever read here, on the server side.
They are wrapped in ``SecretStr`` so they never leak through repr/logging.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"

    database_url: str = "postgresql+asyncpg://aiworld:aiworld@localhost:5432/aiworld"
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM providers -------------------------------------------------
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"

    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_default_model: str = "claude-haiku-4-5"

    gemini_api_key: SecretStr = SecretStr("")
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_default_model: str = "gemini-3.8-flash"
    # Backup models of the same provider, tried when the main one is overloaded or retired.
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-flash-lite"
    openai_fallback_models: str = ""
    anthropic_fallback_models: str = ""
    ollama_fallback_models: str = ""

    ollama_base_url: str = ""
    ollama_default_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    llm_fallback_chain: str = "openai,anthropic,gemini,ollama"
    allow_sim_fallback: bool = True
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 400
    llm_max_calls_per_agent_per_hour: int = 40
    llm_global_calls_per_minute: int = 60
    llm_daily_budget_usd: float = 2.0
    game_moves_use_llm: bool = False

    embedding_provider: str = "auto"

    # Research mode: remove behavioural limits (style rules, room action lists, cooldowns,
    # talk rate limit, energy blocking, the "think only when salient" gate, short messages).
    # The security sandbox (whitelisted world actions, no shell/files/network/secrets) always stays.
    research_mode: bool = False
    # Language residents speak inside the world: "en" or "ru" (any language name also works, e.g. "German").
    world_language: str = "en"

    # --- Scheduler / simulation ---------------------------------------
    scheduler_tick_seconds: float = 1.0
    scheduler_concurrency: int = 4
    agent_min_wake_seconds: float = 6.0
    agent_max_wake_seconds: float = 90.0
    world_time_scale: float = 6.0

    # --- Auth / API ----------------------------------------------------
    jwt_secret: SecretStr = SecretStr("dev-only-change-me-please-use-a-long-random-secret")
    jwt_expire_minutes: int = 60 * 24 * 7
    admin_email: str = "admin@aiworld.local"
    admin_password: SecretStr = SecretStr("change-me-admin")
    cors_origins: str = "http://localhost:3000"
    api_rate_limit_per_minute: int = 120
    auto_seed: bool = True
    # Public URL of the backend as seen by outside AIs (e.g. a Cloudflare tunnel). Used in invitation texts.
    public_api_url: str = ""
    # Optional permanent invite code for outside AIs (paste the same invitation into every chat).
    static_invite_code: str = ""
    static_invite_max_guests: int = 10
    # Self-government: "for" votes a proposed world law needs (and must outnumber "against") to be adopted.
    law_min_votes: int = 3

    # Tuning constants that rarely need to change.
    memory_embedding_dim: int = Field(default=384, frozen=True)

    @field_validator("llm_fallback_chain")
    @classmethod
    def _normalize_chain(cls, v: str) -> str:
        return ",".join(p.strip().lower() for p in v.split(",") if p.strip())

    @property
    def language_name(self) -> str:
        code = self.world_language.strip().lower()
        return {"en": "English", "ru": "Russian", "de": "German", "es": "Spanish", "fr": "French", "uk": "Ukrainian"}.get(code, self.world_language.strip() or "English")

    @property
    def is_russian(self) -> bool:
        return self.language_name == "Russian"

    @property
    def max_message_chars(self) -> int:
        return 4000 if self.research_mode else 700

    @property
    def fallback_chain(self) -> list[str]:
        return [p for p in self.llm_fallback_chain.split(",") if p]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def assert_safe_for_production(self) -> None:
        """Refuse to boot in production with development secrets."""
        if not self.is_production:
            return
        problems = []
        if self.jwt_secret.get_secret_value().startswith("dev-only") or len(self.jwt_secret.get_secret_value()) < 32:
            problems.append("JWT_SECRET must be a long random value")
        if self.admin_password.get_secret_value() in {"", "change-me-admin"}:
            problems.append("ADMIN_PASSWORD must be changed")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
