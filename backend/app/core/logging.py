"""Structured logging.

Every log record can carry world context (agent_id, action, room, model,
latency_ms, error). A redaction filter scrubs anything that looks like an
API key, plus the literal values of configured secrets, before output.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

CONTEXT_FIELDS = ("agent_id", "agent", "action", "room", "model", "provider", "latency_ms", "error", "event", "tokens")

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),  # OpenAI / Anthropic style
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google (classic)
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),  # Google (new key format)
    re.compile(r"(?i)(api[_-]?key|authorization|x-api-key|bearer)\s*[:=]\s*\S+"),
]


class _Redactor:
    def __init__(self) -> None:
        self._literals: list[str] = []

    def register(self, *values: str) -> None:
        for v in values:
            if v and len(v) >= 8 and v not in self._literals:
                self._literals.append(v)

    def scrub(self, text: str) -> str:
        for lit in self._literals:
            if lit in text:
                text = text.replace(lit, "[REDACTED]")
        for pat in _SECRET_PATTERNS:
            text = pat.sub("[REDACTED]", text)
        return text


redactor = _Redactor()


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redactor.scrub(record.msg)
        if record.args:
            record.args = tuple(redactor.scrub(a) if isinstance(a, str) else a for a in record.args)  # type: ignore[assignment]
        for key in CONTEXT_FIELDS:
            val = getattr(record, key, None)
            if isinstance(val, str):
                setattr(record, key, redactor.scrub(val))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in CONTEXT_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = redactor.scrub(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{datetime.fromtimestamp(record.created).strftime('%H:%M:%S')} {record.levelname:<5} {record.name}: {record.getMessage()}"
        extras = " ".join(f"{k}={getattr(record, k)}" for k in CONTEXT_FIELDS if getattr(record, k, None) is not None)
        out = f"{base} {extras}".rstrip()
        if record.exc_info:
            out += "\n" + redactor.scrub(self.formatException(record.exc_info))
        return out


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    from app.core.config import get_settings

    s = get_settings()
    redactor.register(
        s.openai_api_key.get_secret_value(),
        s.anthropic_api_key.get_secret_value(),
        s.gemini_api_key.get_secret_value(),
        s.jwt_secret.get_secret_value(),
        s.admin_password.get_secret_value(),
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "asyncio", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
