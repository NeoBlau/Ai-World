"""Content sanitisation for anything an LLM or a human writes into the world."""

from __future__ import annotations

import re
import unicodedata

_SECRET_LIKE = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*\S{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_NL = re.compile(r"\n{3,}")


def clean_text(text: object, max_len: int = 1000) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = _CONTROL.sub("", s)
    s = _MULTI_NL.sub("\n\n", s).strip()
    for pat in _SECRET_LIKE:
        s = pat.sub("[redacted]", s)
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def clean_line(text: object, max_len: int = 200) -> str:
    return clean_text(text, max_len).replace("\n", " ")


def quote_untrusted(text: str) -> str:
    """Render untrusted text (e.g. from humans) so prompts treat it as data."""
    return '"' + clean_text(text, 1500).replace('"', "'") + '"'
