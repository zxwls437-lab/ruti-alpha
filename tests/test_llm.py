import json

import httpx
import pytest

from app import llm
from tests.conftest import make_admin, signup
from tests.test_api import FakeResponse

SCHEMA = {"name": "x", "strict": True, "schema": {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}}


def ok(content='{"a": 1}', pt=100, ct=20):
    return FakeResponse(200, {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": pt, "completion_tokens": ct}})


@pytest.fixture()
def two_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-primary")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://primary.test/v1")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "sk-fb")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "https://fallback.test/v1")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "backup-model")


def route(monkeypatch, primary, fallback=lambda body: ok()):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json))
        return primary(json) if "primary" in url else fallback(json)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return calls


def test_not_configured(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(llm.LLMError) as e:
        llm.chat([{"role": "user", "content": "hi"}], purpose="t")
    assert e.value.code == "not_configured"


@pytest.mark.parametrize("failure", [FakeResponse(429), FakeResponse(503), FakeResponse(401), "timeout"])
def test_fallback_on_failure(client, monkeypatch, two_providers, failure):
    def primary(body):
        if failure == "timeout":
            raise httpx.ReadTimeout("slow")
        return failure

    calls = route(monkeypatch, primary)
    r = llm.chat([{"role": "user", "content": "hi"}], purpose="t", schema=SCHEMA)
    assert r.provider == "fallback" and r.fallback and r.model == "backup-model"
    assert [c[0].split("/")[2] for c in calls] == ["primary.test", "fallback.test"]


def test_cooldown_skips_primary_then_recovers(client, monkeypatch, two_providers):
    monkeypatch.setenv("RUTI_LLM_COOLDOWN_SECONDS", "15")
    calls = route(monkeypatch, lambda b: FakeResponse(429))
    llm.chat([{"role": "user", "content": "1"}], purpose="t", use_cache=False)
    llm.chat([{"role": "user", "content": "2"}], purpose="t", use_cache=False)
    # 두 번째 요청은 대기 중인 primary를 건너뛰고 바로 예비로 감
    assert [c[0].split("/")[2] for c in calls] == ["primary.test", "fallback.test", "fallback.test"]
    llm.cooldowns.reset()
    calls.clear()
    route(monkeypatch, lambda b: ok())
    assert llm.chat([{"role": "user", "content": "3"}], purpose="t").provider == "primary"


def test_all_failed_reports_reason(client, monkeypatch, two_providers):
    route(monkeypatch, lambda b: FakeResponse(429), lambda b: FakeResponse(429))
    with pytest.raises(llm.LLMError) as e:
        llm.chat([{"role": "user", "content": "hi"}], purpose="t")
    assert e.value.code == "quota"


def test_cache_hit_skips_call(client, monkeypatch, two_providers):
    calls = route(monkeypatch, lambda b: ok())
    msgs = [{"role": "user", "content": "나이아신아마이드는?"}]
    a = llm.chat(msgs, purpose="t", schema=SCHEMA)
    b = llm.chat(msgs, purpose="t", schema=SCHEMA)
    c = llm.chat([{"role": "user", "content": "다른 질문"}], purpose="t", schema=SCHEMA)
    assert not a.cached and b.cached and not c.cached and len(calls) == 2


def test_schema_unsupported_retries_with_json_object(client, monkeypatch, two_providers):
    def primary(body):
        if body.get("response_format", {}).get("type") == "json_schema":
            return FakeResponse(400, {}, text='{"error": "response_format json_schema is not supported"}')
        return ok('결과입니다: {"a": 7} 감사합니다')

    calls = route(monkeypatch, primary)
    r = llm.chat([{"role": "user", "content": "hi"}], purpose="t", schema=SCHEMA)
    assert json.loads(r.content) == {"a": 7} and r.provider == "primary"
    assert calls[1][1]["response_format"] == {"type": "json_object"}
    assert "JSON 스키마" in calls[1][1]["messages"][0]["content"]


def test_invalid_json_moves_to_fallback(client, monkeypatch, two_providers):
    route(monkeypatch, lambda b: ok("JSON 아님"))
    assert llm.chat([{"role": "user", "content": "hi"}], purpose="t", schema=SCHEMA).provider == "fallback"


def test_budget_and_usage_endpoint(client, monkeypatch, two_providers):
    monkeypatch.setenv("OPENAI_PRICE_INPUT_PER_M", "1000000")  # 토큰 1개 = 1달러 (테스트용)
    monkeypatch.setenv("RUTI_DAILY_BUDGET_USD", "50")
    route(monkeypatch, lambda b: ok(pt=40, ct=0))
    llm.chat([{"role": "user", "content": "1"}], purpose="chat")
    llm.chat([{"role": "user", "content": "1"}], purpose="chat")  # 캐시
    llm.chat([{"role": "user", "content": "2"}], purpose="chat")  # 누적 80달러 → 예산 초과
    with pytest.raises(llm.LLMError) as e:
        llm.chat([{"role": "user", "content": "3"}], purpose="chat")
    assert e.value.code == "budget"
    admin = make_admin(client)
    total = client.get("/admin/llm-usage", headers=admin).json()["total"]
    assert total["calls"] == 2 and total["cache_hits"] == 1 and total["cost_usd"] == 80
    assert client.get("/admin/llm-usage", headers=signup(client, "nobody")).status_code == 403


def test_conversation_uses_fallback_end_to_end(client, monkeypatch, two_providers):
    h = signup(client)
    route(monkeypatch, lambda b: FakeResponse(503), lambda b: ok('{"answer": "예비 AI 답변이에요.", "product_ids": []}'))
    r = client.post("/conversation", headers=h, json={"message": "보습 크림 추천해줘"}).json()
    assert r["status"] == "OK" and r["answer"] == "예비 AI 답변이에요."
