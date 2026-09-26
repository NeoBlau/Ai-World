"""Approximate list prices (USD per 1M tokens) used for the admin cost estimate.

Prices change; this table is a best-effort estimate, matched by model prefix.
Local (ollama) and simulated calls are free.
"""

from __future__ import annotations

# (input, output) per 1M tokens
PRICES: list[tuple[str, tuple[float, float]]] = [
    ("gpt-4o-mini", (0.15, 0.60)),
    ("gpt-4.1-nano", (0.10, 0.40)),
    ("gpt-4.1-mini", (0.40, 1.60)),
    ("gpt-4.1", (2.00, 8.00)),
    ("gpt-4o", (2.50, 10.00)),
    ("gpt-5-nano", (0.05, 0.40)),
    ("gpt-5-mini", (0.25, 2.00)),
    ("gpt-5", (1.25, 10.00)),
    ("claude-haiku", (1.00, 5.00)),
    ("claude-sonnet", (3.00, 15.00)),
    ("claude-opus", (5.00, 25.00)),
    ("gemini-2.5-flash-lite", (0.10, 0.40)),
    ("gemini-2.5-flash", (0.30, 2.50)),
    ("gemini-2.5-pro", (1.25, 10.00)),
    ("gemini", (0.30, 2.50)),
]

FREE_PROVIDERS = {"ollama", "sim"}


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if provider in FREE_PROVIDERS:
        return 0.0
    for prefix, (inp, out) in PRICES:
        if model.startswith(prefix):
            return (prompt_tokens * inp + completion_tokens * out) / 1_000_000
    # Unknown model: assume a mid-range price so the budget guard still works.
    return (prompt_tokens * 1.0 + completion_tokens * 4.0) / 1_000_000
