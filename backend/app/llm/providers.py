"""Concrete HTTP providers: OpenAI, Anthropic, Google Gemini, Ollama.

They use plain ``httpx`` against each vendor's public REST API, so there is
no SDK lock-in and every request goes through the same timeout/error rules.
API keys are sent only in headers (never in URLs) so they do not end up in
proxy or access logs.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderHealth,
)

BILLING_MARKERS = ("insufficient_quota", "no credits remaining", "credit balance is too low", "billing_hard_limit")
# (not "exceeded your current quota": Gemini uses it for short per-minute limits too)
OPENAI_EMBED_MODEL = "text-embedding-3-small"
GEMINI_EMBED_MODEL = "gemini-embedding-001"


def _raise_for_status(provider: str, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    # Do not echo the response body wholesale: it can contain request details.
    snippet = resp.text[:200].replace("\n", " ")
    retryable = resp.status_code in (408, 409, 425, 429) or resp.status_code >= 500
    low = resp.text[:2000].lower()
    if any(m in low for m in BILLING_MARKERS):
        # An empty balance is not an overload: retrying (or another model of the same account) will not help.
        raise ProviderError(provider, f"HTTP {resp.status_code} (no credits): {snippet}", retryable=False, status=resp.status_code, billing=True)
    raise ProviderError(provider, f"HTTP {resp.status_code}: {snippet}", retryable=retryable, status=resp.status_code)


class _HttpProvider(LLMProvider):
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.settings.llm_timeout_seconds, connect=5.0))
        return self._client

    async def _post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            resp = await self.client.post(url, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, "timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {type(exc).__name__}") from exc
        _raise_for_status(self.name, resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(self.name, "invalid JSON from provider") from exc

    async def _probe(self, url: str, headers: dict[str, str]) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth(self.name, False, None, "not configured", self.default_model)
        try:
            resp = await self.client.get(url, headers=headers, timeout=5.0)
            ok = resp.status_code < 400
            return ProviderHealth(self.name, True, ok, "ok" if ok else f"HTTP {resp.status_code}", self.default_model)
        except httpx.HTTPError as exc:
            return ProviderHealth(self.name, True, False, type(exc).__name__, self.default_model)


# --------------------------------------------------------------------------- OpenAI
class OpenAIProvider(_HttpProvider):
    name = "openai"

    def is_configured(self) -> bool:
        return bool(self.settings.openai_api_key.get_secret_value())

    @property
    def default_model(self) -> str:
        return self.settings.openai_default_model

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"}

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        return model.startswith(("o1", "o3", "o4", "gpt-5"))

    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse:
        messages: list[dict[str, str]] = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {"model": model, "messages": messages}
        if self._is_reasoning_model(model):
            body["max_completion_tokens"] = request.max_tokens * 4
        else:
            body["max_tokens"] = request.max_tokens
            body["temperature"] = request.temperature
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        data = await self._post(f"{self.settings.openai_base_url.rstrip('/')}/chat/completions", body, self._headers())
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc
        usage = data.get("usage") or {}
        return LLMResponse(text, self.name, model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.is_configured():
            return None
        body = {"model": OPENAI_EMBED_MODEL, "input": texts, "dimensions": self.settings.memory_embedding_dim}
        data = await self._post(f"{self.settings.openai_base_url.rstrip('/')}/embeddings", body, self._headers())
        return [item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])]

    async def health(self) -> ProviderHealth:
        return await self._probe(f"{self.settings.openai_base_url.rstrip('/')}/models", self._headers())


# --------------------------------------------------------------------------- Anthropic
class AnthropicProvider(_HttpProvider):
    name = "anthropic"
    API_VERSION = "2023-06-01"

    def is_configured(self) -> bool:
        return bool(self.settings.anthropic_api_key.get_secret_value())

    @property
    def default_model(self) -> str:
        return self.settings.anthropic_default_model

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.settings.anthropic_api_key.get_secret_value(),
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse:
        body: dict[str, Any] = {
            "model": model,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "temperature": min(max(request.temperature, 0.0), 1.0),
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        data = await self._post(f"{self.settings.anthropic_base_url.rstrip('/')}/v1/messages", body, self._headers())
        try:
            text = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc
        usage = data.get("usage") or {}
        return LLMResponse(text, self.name, model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    async def health(self) -> ProviderHealth:
        return await self._probe(f"{self.settings.anthropic_base_url.rstrip('/')}/v1/models", self._headers())


# --------------------------------------------------------------------------- Gemini
class GeminiProvider(_HttpProvider):
    name = "gemini"

    def is_configured(self) -> bool:
        return bool(self.settings.gemini_api_key.get_secret_value())

    @property
    def default_model(self) -> str:
        return self.settings.gemini_default_model

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.settings.gemini_api_key.get_secret_value()}

    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse:
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]} for m in request.messages
        ]
        gen_cfg: dict[str, Any] = {"temperature": request.temperature, "maxOutputTokens": request.max_tokens}
        if request.json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        if "flash" in model:
            # Hidden "thinking" tokens would eat the output budget; agents reason in the JSON "thought".
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        body = {"systemInstruction": {"parts": [{"text": request.system}]}, "contents": contents, "generationConfig": gen_cfg}
        url = f"{self.settings.gemini_base_url.rstrip('/')}/models/{model}:generateContent"
        data = await self._post(url, body, self._headers())
        try:
            parts = data["candidates"][0]["content"]["parts"]
            # Thinking models may return thought parts; only the answer counts.
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError, TypeError) as exc:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(self.name, f"empty response ({reason})") from exc
        usage = data.get("usageMetadata") or {}
        return LLMResponse(text, self.name, model, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.is_configured():
            return None
        body = {
            "requests": [
                {
                    "model": f"models/{GEMINI_EMBED_MODEL}",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": self.settings.memory_embedding_dim,
                }
                for t in texts
            ]
        }
        url = f"{self.settings.gemini_base_url.rstrip('/')}/models/{GEMINI_EMBED_MODEL}:batchEmbedContents"
        data = await self._post(url, body, self._headers())
        return [e["values"] for e in data["embeddings"]]

    async def health(self) -> ProviderHealth:
        return await self._probe(f"{self.settings.gemini_base_url.rstrip('/')}/models?pageSize=1", self._headers())


# --------------------------------------------------------------------------- Ollama
class OllamaProvider(_HttpProvider):
    name = "ollama"

    def is_configured(self) -> bool:
        return bool(self.settings.ollama_base_url)

    @property
    def default_model(self) -> str:
        return self.settings.ollama_default_model

    async def _generate(self, request: LLMRequest, model: str) -> LLMResponse:
        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.json_mode:
            body["format"] = "json"
        data = await self._post(f"{self.settings.ollama_base_url.rstrip('/')}/api/chat", body, {})
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc
        return LLMResponse(text, self.name, model, data.get("prompt_eval_count", 0), data.get("eval_count", 0))

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.is_configured():
            return None
        body = {"model": self.settings.ollama_embedding_model, "input": texts}
        data = await self._post(f"{self.settings.ollama_base_url.rstrip('/')}/api/embed", body, {})
        return data["embeddings"]

    async def health(self) -> ProviderHealth:
        return await self._probe(f"{self.settings.ollama_base_url.rstrip('/')}/api/tags", {})
