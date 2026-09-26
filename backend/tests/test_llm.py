import httpx
import pytest
import respx

from app.agents.decision import DecisionParseError, build_params, parse_decision
from app.core.config import Settings
from app.llm.base import ChatMessage, LLMRequest, ProviderError
from app.llm.json_utils import extract_json_object
from app.llm.providers import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAIProvider
from app.llm.router import AllProvidersUnavailable, LLMRouter
from app.llm.simulated import SimulatedProvider


def settings(**kw) -> Settings:
    base = dict(openai_api_key="sk-test-openai-key-123456", anthropic_api_key="sk-ant-test-123456", gemini_api_key="AIzaTestKey1234567890abcdef",
                ollama_base_url="http://ollama:11434")
    base.update(kw)
    return Settings(**base)


REQ = LLMRequest(system="sys", messages=[ChatMessage("user", "hi")], max_tokens=50)


@respx.mock
async def test_openai_provider():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "choices": [{"message": {"content": '{"action":"observe"}'}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}))
    resp = await OpenAIProvider(settings()).generate(REQ)
    assert resp.text == '{"action":"observe"}' and resp.prompt_tokens == 10
    sent = route.calls.last.request
    assert sent.headers["authorization"].startswith("Bearer sk-test")
    assert b"json_object" in sent.content


@respx.mock
async def test_anthropic_provider():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json={
        "content": [{"type": "text", "text": "hello"}], "usage": {"input_tokens": 7, "output_tokens": 2}}))
    resp = await AnthropicProvider(settings()).generate(REQ)
    assert resp.text == "hello" and resp.completion_tokens == 2
    assert route.calls.last.request.headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_gemini_provider_key_in_header_not_url():
    route = respx.post(url__regex=r".*/models/gemini-3.8-flash:generateContent").mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}}))
    resp = await GeminiProvider(settings()).generate(REQ)
    req = route.calls.last.request
    assert resp.text == "ok" and "key=" not in str(req.url) and req.headers["x-goog-api-key"]


@respx.mock
async def test_ollama_provider_and_errors():
    respx.post("http://ollama:11434/api/chat").mock(return_value=httpx.Response(200, json={"message": {"content": "hey"}, "eval_count": 3}))
    assert (await OllamaProvider(settings()).generate(REQ)).text == "hey"
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderError) as e:
        await OpenAIProvider(settings()).generate(REQ)
    assert e.value.retryable


@respx.mock
async def test_router_fallback_and_circuit_breaker():
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(503, text="down"))
    respx.post(url__regex=r".*generateContent").mock(return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "from gemini"}]}}]}))
    s = settings(anthropic_api_key="", llm_fallback_chain="gemini,ollama")
    router = LLMRouter(s)
    calls = []

    async def record(rec):
        calls.append(rec)

    router.persist = record
    resp = await router.generate(REQ, provider="openai")
    assert resp.provider == "gemini" and resp.fallback_used
    assert [c.success for c in calls] == [False, True]
    for _ in range(3):
        await router.generate(REQ, provider="openai")
    assert await router.circuit_open("openai")


async def test_router_all_unavailable_without_sim():
    router = LLMRouter(Settings(allow_sim_fallback=False))
    router.persist = lambda rec: _noop()
    with pytest.raises(AllProvidersUnavailable):
        await router.generate(REQ, provider="openai")


async def _noop():
    return None


async def test_budget_exhausted_uses_free_providers_only(_clean):
    s = settings(llm_daily_budget_usd=0.0, ollama_base_url="")
    router = LLMRouter(s)
    router.persist = lambda rec: _noop()
    resp = await router.generate(LLMRequest(system="s", messages=[], context={"mode": "decide", "available_actions": ["observe"]}), provider="openai")
    assert resp.provider == "sim"


async def test_sim_provider_produces_valid_decision():
    ctx = {"mode": "decide", "agent": {"slug": "alex", "name": "Alex", "style": "enthusiastic", "interests": ["aviation"], "traits": {}},
           "state": {"energy": 80, "social_need": 90}, "location": {"slug": "ai-cafe", "name": "AI Café"},
           "available_actions": ["talk", "meet_agent", "observe", "walk"], "rooms": [{"slug": "park", "name": "Park", "occupancy": 0}],
           "nearby": [{"slug": "mira", "name": "Mira", "activity": "idle", "relationship": {"familiarity": 30}, "known_interests": ["astronomy"]}], "seed": 1}
    resp = await SimulatedProvider().generate(LLMRequest(system="", messages=[], context=ctx))
    decision, raw = parse_decision(resp.text)
    assert decision.action in ctx["available_actions"]


def test_json_extraction_and_decision_parsing():
    assert extract_json_object('Sure! ```json\n{"a": {"b": 1}}\n``` done') == {"a": {"b": 1}}
    assert extract_json_object('noise {"x": "}"} tail') == {"x": "}"}
    d, raw = parse_decision('{"action": "talk", "message": "hi", "target_agent": "mira", "importance": 99}')
    assert d.importance == 10
    assert build_params(d, raw, "talk") == {"message": "hi", "target_agent": "mira"}
    d, raw = parse_decision('{"action": "walk", "room": "library"}')
    assert build_params(d, raw, "walk")["room"] == "library"
    with pytest.raises(DecisionParseError):
        parse_decision("I think I'll just wander around")


@respx.mock
async def test_router_retries_retired_model_with_default():
    retired = respx.post(url__regex=r".*/models/gemini-old:generateContent").mock(return_value=httpx.Response(404, text="no longer available"))
    current = respx.post(url__regex=r".*/models/gemini-3.8-flash:generateContent").mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "answer"}]}}]}))
    router = LLMRouter(settings(openai_api_key="", anthropic_api_key="", ollama_base_url="", llm_fallback_chain="", allow_sim_fallback=False))
    router.persist = lambda rec: _noop()
    resp = await router.generate(REQ, provider="gemini", model="gemini-old")
    assert retired.called and current.called
    assert resp.model == "gemini-3.8-flash" and resp.text == "answer"


@respx.mock
async def test_router_retries_transient_overload_once():
    route = respx.post(url__regex=r".*generateContent").mock(side_effect=[
        httpx.Response(503, text="high demand"),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}),
    ])
    router = LLMRouter(settings(openai_api_key="", anthropic_api_key="", ollama_base_url="", llm_fallback_chain="", allow_sim_fallback=False))
    router.persist = lambda rec: _noop()
    resp = await router.generate(REQ, provider="gemini")
    assert resp.text == "ok" and route.call_count == 2


@respx.mock
async def test_router_switches_to_backup_model_when_overloaded():
    busy = respx.post(url__regex=r".*/models/gemini-3.8-flash:generateContent").mock(return_value=httpx.Response(503, text="high demand"))
    backup = respx.post(url__regex=r".*/models/gemini-3.6-flash:generateContent").mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "from backup"}]}}]}))
    router = LLMRouter(settings(openai_api_key="", anthropic_api_key="", ollama_base_url="", llm_fallback_chain="", allow_sim_fallback=False))
    router.persist = lambda rec: _noop()
    resp = await router.generate(REQ, provider="gemini")
    assert busy.called and backup.called and resp.model == "gemini-3.6-flash" and resp.text == "from backup"
