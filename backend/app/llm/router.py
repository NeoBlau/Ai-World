"""LLM router: provider selection, fallback chain, circuit breaker, budgets.

    agent.provider  ->  agent.fallback_providers / LLM_FALLBACK_CHAIN  ->  sim

* A provider that is not configured is skipped.
* A provider whose circuit is open (recent repeated failures) is skipped.
* When the per-agent / global rate limit or the daily budget is exhausted,
  only free local providers (ollama, sim) are tried.
* Every attempt is recorded (llm_calls table + Redis counters) for the admin panel.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderHealth,
)
from app.llm.pricing import FREE_PROVIDERS, estimate_cost
from app.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from app.llm.simulated import SimulatedProvider

log = get_logger("aiworld.llm")

KNOWN_PROVIDERS = ("openai", "anthropic", "gemini", "ollama", "sim")
CB_FAIL_THRESHOLD = 3
CB_OPEN_SECONDS = 60
CB_AUTH_OPEN_SECONDS = 600
CB_BILLING_OPEN_SECONDS = 3600


class AllProvidersUnavailable(Exception):
    def __init__(self, attempts: list[str]) -> None:
        super().__init__("all providers failed: " + "; ".join(attempts))
        self.attempts = attempts


@dataclass
class CallRecord:
    agent_id: uuid.UUID | None
    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool
    error: str | None


async def _persist_call(rec: CallRecord) -> None:
    """Write the call to the llm_calls table (own short transaction)."""
    from app.database.session import session_scope
    from app.models import LLMCall

    try:
        async with session_scope() as session:
            session.add(
                LLMCall(
                    agent_id=rec.agent_id,
                    provider=rec.provider,
                    model=rec.model,
                    purpose=rec.purpose,
                    prompt_tokens=rec.prompt_tokens,
                    completion_tokens=rec.completion_tokens,
                    cost_usd=rec.cost_usd,
                    latency_ms=rec.latency_ms,
                    success=rec.success,
                    error=rec.error,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - accounting must never break the world
        log.warning("failed to persist llm call record", exc_info=True)


class LLMRouter:
    def __init__(self, settings: Settings | None = None, providers: dict[str, LLMProvider] | None = None) -> None:
        self.settings = settings or get_settings()
        self.providers: dict[str, LLMProvider] = providers or {
            "openai": OpenAIProvider(self.settings),
            "anthropic": AnthropicProvider(self.settings),
            "gemini": GeminiProvider(self.settings),
            "ollama": OllamaProvider(self.settings),
            "sim": SimulatedProvider(),
        }
        self.persist = _persist_call

    # ------------------------------------------------------------------ chain
    def chain_for(self, preferred: str, fallbacks: list[str] | None = None) -> list[str]:
        order = [preferred, *(fallbacks or []), *self.settings.fallback_chain]
        if self.settings.allow_sim_fallback:
            order.append("sim")
        seen: list[str] = []
        for name in order:
            name = (name or "").lower()
            if name in self.providers and name not in seen:
                if name == "sim" and not self.settings.allow_sim_fallback and preferred != "sim":
                    continue
                seen.append(name)
        return seen

    def default_model(self, provider: str) -> str:
        p = self.providers.get(provider)
        return p.default_model if p else ""

    # ------------------------------------------------------------------ circuit breaker
    async def circuit_open(self, provider: str) -> bool:
        return bool(await get_redis().exists(f"llm:cb:{provider}:open"))

    async def _record_failure(self, provider: str, err: ProviderError) -> None:
        r = get_redis()
        if getattr(err, "billing", False):
            await r.set(f"llm:cb:{provider}:open", "no credits", ex=CB_BILLING_OPEN_SECONDS)
            log.warning("provider has no credits — skipping it for an hour", extra={"provider": provider})
            return
        if not err.retryable:
            await r.set(f"llm:cb:{provider}:open", "auth", ex=CB_AUTH_OPEN_SECONDS)
            return
        key = f"llm:cb:{provider}:fails"
        fails = await r.incr(key)
        await r.expire(key, 120)
        if fails >= CB_FAIL_THRESHOLD:
            await r.set(f"llm:cb:{provider}:open", "failures", ex=CB_OPEN_SECONDS)
            await r.delete(key)
            log.warning("circuit opened", extra={"provider": provider, "error": str(err)})

    async def _record_success(self, provider: str) -> None:
        await get_redis().delete(f"llm:cb:{provider}:fails")

    # ------------------------------------------------------------------ budgets
    async def paid_calls_allowed(self, agent_id: uuid.UUID | None) -> tuple[bool, str]:
        r = get_redis()
        now = datetime.now(timezone.utc)
        spent = float(await r.get(f"llm:cost:{now:%Y%m%d}") or 0.0)
        if spent >= self.settings.llm_daily_budget_usd:
            return False, "daily budget exhausted"
        glob = int(await r.get(f"llm:rate:global:{now:%Y%m%d%H%M}") or 0)
        if glob >= self.settings.llm_global_calls_per_minute:
            return False, "global rate limit"
        if agent_id is not None:
            per_agent = int(await r.get(f"llm:rate:agent:{agent_id}:{now:%Y%m%d%H}") or 0)
            if per_agent >= self.settings.llm_max_calls_per_agent_per_hour:
                return False, "agent hourly limit"
        return True, ""

    async def _count(self, agent_id: uuid.UUID | None, rec: CallRecord) -> None:
        r = get_redis()
        now = datetime.now(timezone.utc)
        pipe = r.pipeline()
        day = f"{now:%Y%m%d}"
        pipe.incr(f"llm:calls:{day}")
        pipe.expire(f"llm:calls:{day}", 3 * 86400)
        pipe.incrby(f"llm:tokens:{day}", rec.prompt_tokens + rec.completion_tokens)
        pipe.expire(f"llm:tokens:{day}", 3 * 86400)
        if rec.cost_usd:
            pipe.incrbyfloat(f"llm:cost:{day}", rec.cost_usd)
            pipe.expire(f"llm:cost:{day}", 3 * 86400)
        if rec.provider not in FREE_PROVIDERS:
            pipe.incr(f"llm:rate:global:{now:%Y%m%d%H%M}")
            pipe.expire(f"llm:rate:global:{now:%Y%m%d%H%M}", 120)
            if agent_id is not None:
                k = f"llm:rate:agent:{agent_id}:{now:%Y%m%d%H}"
                pipe.incr(k)
                pipe.expire(k, 3700)
        await pipe.execute()

    # ------------------------------------------------------------------ generate
    def models_for(self, prov: LLMProvider, first: str) -> list[str]:
        """Models to try within one provider: the requested one, the default, then configured backups."""
        extra = getattr(self.settings, f"{prov.name}_fallback_models", "") or ""
        out: list[str] = []
        for m in [first, prov.default_model, *extra.split(",")]:
            m = m.strip()
            if m and m not in out:
                out.append(m)
        return out

    async def _generate_with_model_fallback(self, prov: LLMProvider, request: LLMRequest, first: str) -> tuple[LLMResponse, str]:
        """Overloaded (429/5xx) or retired (404) model -> next model of the same provider."""
        models = self.models_for(prov, first)
        last: ProviderError | None = None
        for i, m in enumerate(models):
            req = LLMRequest(**{**request.__dict__, "model": m})
            try:
                resp = await asyncio.wait_for(prov.generate(req), timeout=self.settings.llm_timeout_seconds + 5)
                if i:
                    log.info("used backup model", extra={"provider": prov.name, "model": m})
                return resp, m
            except ProviderError as exc:
                last = exc
                if exc.status in (404, 429, 500, 503) and not exc.billing and prov.name not in FREE_PROVIDERS and i + 1 < len(models):
                    log.warning("model unavailable, trying next", extra={"provider": prov.name, "model": m, "error": str(exc)[:120]})
                    await asyncio.sleep(0.5)
                    continue
                raise
        assert last is not None
        raise last

    async def generate(
        self,
        request: LLMRequest,
        *,
        agent_id: uuid.UUID | None = None,
        provider: str = "sim",
        model: str | None = None,
        fallbacks: list[str] | None = None,
    ) -> LLMResponse:
        chain = self.chain_for(provider, fallbacks)
        paid_ok, why = await self.paid_calls_allowed(agent_id)
        if not paid_ok:
            chain = [p for p in chain if p in FREE_PROVIDERS]
        attempts: list[str] = [] if paid_ok else [f"paid providers skipped: {why}"]
        for name in chain:
            prov = self.providers[name]
            if not prov.is_configured():
                attempts.append(f"{name}: not configured")
                continue
            if await self.circuit_open(name):
                attempts.append(f"{name}: circuit open")
                continue
            req_model = model if (name == provider and model) else prov.default_model
            started = time.perf_counter()
            try:
                resp, req_model = await self._generate_with_model_fallback(prov, request, req_model)
            except (ProviderError, asyncio.TimeoutError) as exc:
                err = exc if isinstance(exc, ProviderError) else ProviderError(name, "timeout")
                latency = int((time.perf_counter() - started) * 1000)
                attempts.append(f"{name}: {err}")
                await self._record_failure(name, err)
                rec = CallRecord(agent_id, name, req_model, request.purpose, 0, 0, 0.0, latency, False, str(err)[:500])
                await self.persist(rec)
                log.warning(
                    "llm call failed",
                    extra={"agent_id": str(agent_id) if agent_id else None, "provider": name, "model": req_model, "latency_ms": latency, "error": str(err)},
                )
                continue
            await self._record_success(name)
            resp.fallback_used = name != provider
            cost = estimate_cost(name, resp.model, resp.prompt_tokens, resp.completion_tokens)
            rec = CallRecord(agent_id, name, resp.model, request.purpose, resp.prompt_tokens, resp.completion_tokens, cost, resp.latency_ms, True, None)
            await self._count(agent_id, rec)
            await self.persist(rec)
            log.info(
                "llm call",
                extra={
                    "agent_id": str(agent_id) if agent_id else None,
                    "provider": name,
                    "model": resp.model,
                    "latency_ms": resp.latency_ms,
                    "tokens": resp.total_tokens,
                    "event": request.purpose,
                },
            )
            return resp
        raise AllProvidersUnavailable(attempts)

    # ------------------------------------------------------------------ health
    async def health(self) -> list[dict]:
        out = []
        results = await asyncio.gather(*(p.health() for p in self.providers.values()), return_exceptions=True)
        for (name, _prov), res in zip(self.providers.items(), results):
            if isinstance(res, BaseException):
                res = ProviderHealth(name, True, False, type(res).__name__)
            out.append(
                {
                    "name": name,
                    "configured": res.configured,
                    "healthy": res.healthy,
                    "detail": res.detail,
                    "default_model": res.default_model,
                    "circuit_open": await self.circuit_open(name),
                }
            )
        return out


_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def set_router(router: LLMRouter | None) -> None:
    global _router
    _router = router
