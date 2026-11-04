"""AI 호출 관문 (모든 OpenAI 호환 호출은 여기를 거친다).

FreeLLMAPI(github.com/tashfeenahmed/freellmapi, MIT)의 라우터 설계를 참고해 RUTI에 맞게 단순화:
  1. 예비 공급자 자동 전환: 429/5xx/시간초과/인증오류면 대기시간(cooldown)을 걸고 다음 공급자로
  2. 정확히 같은 요청은 메모리 캐시에서 응답 (AI를 다시 부르지 않음)
  3. json_schema를 지원하지 않는 공급자는 json_object + 지시문으로 재시도
  4. 사용량·추정 비용 기록, 하루 예산 상한
"""
import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date

import httpx

from .config import env, env_int


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    vision_model: str
    price_in: float   # USD / 1M 입력 토큰 (추정치, .env로 조정)
    price_out: float  # USD / 1M 출력 토큰


def _float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


def providers() -> list[Provider]:
    out = []
    key = env("OPENAI_API_KEY")
    if key:
        model = env("OPENAI_MODEL", "gpt-4.1-mini")
        out.append(Provider("primary", env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"), key, model,
                            env("OPENAI_VISION_MODEL") or model, _float("OPENAI_PRICE_INPUT_PER_M", 0.40), _float("OPENAI_PRICE_OUTPUT_PER_M", 1.60)))
    fb_key, fb_url, fb_model = env("LLM_FALLBACK_API_KEY"), env("LLM_FALLBACK_BASE_URL"), env("LLM_FALLBACK_MODEL")
    if fb_key and fb_url and fb_model:
        out.append(Provider("fallback", fb_url.rstrip("/"), fb_key, fb_model, env("LLM_FALLBACK_VISION_MODEL") or fb_model,
                            _float("LLM_FALLBACK_PRICE_INPUT_PER_M", 0.0), _float("LLM_FALLBACK_PRICE_OUTPUT_PER_M", 0.0)))
    return out


class LLMError(Exception):
    def __init__(self, code: str, retry_after: int = 0):
        super().__init__(code)
        self.code, self.retry_after = code, retry_after  # not_configured | quota | auth | budget | error


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    cached: bool = False
    fallback: bool = False
    usage: dict = field(default_factory=dict)


# ---------- 대기시간 (cooldown) ----------

class Cooldowns:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._until: dict[str, float] = {}
        self._strikes: dict[str, int] = {}

    def active(self, name: str) -> float:
        with self._lock:
            return max(0.0, self._until.get(name, 0) - time.monotonic())

    def hit(self, name: str, kind: str) -> None:
        base = env_int("RUTI_LLM_COOLDOWN_SECONDS", 15)
        with self._lock:
            strikes = self._strikes.get(name, 0) + 1
            self._strikes[name] = strikes
            if kind == "quota":
                seconds = min(base * 2 ** (strikes - 1), 300)   # 15 → 30 → 60 … 최대 5분
            elif kind == "auth":
                seconds = base * 40                               # 키 문제는 길게 (기본 10분)
            else:
                seconds = base * 2 / 3                            # 일시 오류 (기본 10초)
            self._until[name] = time.monotonic() + seconds

    def ok(self, name: str) -> None:
        with self._lock:
            self._strikes.pop(name, None)
            self._until.pop(name, None)

    def reset(self) -> None:
        with self._lock:
            self._until.clear()
            self._strikes.clear()


cooldowns = Cooldowns()


# ---------- 응답 캐시 (정확히 같은 요청만) ----------

class ResponseCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, LLMResult]] = OrderedDict()

    @staticmethod
    def key(messages: list, schema: dict | None, vision: bool, max_tokens: int) -> str:
        raw = json.dumps({"m": messages, "s": schema, "v": vision, "t": max_tokens}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> LLMResult | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires, result = item
            if expires < time.monotonic():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return result

    def put(self, key: str, result: LLMResult) -> None:
        size = env_int("RUTI_LLM_CACHE_SIZE", 500)
        if size <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + env_int("RUTI_LLM_CACHE_TTL_SECONDS", 86400), result)
            self._data.move_to_end(key)
            while len(self._data) > size:
                self._data.popitem(last=False)

    def reset(self) -> None:
        with self._lock:
            self._data.clear()


cache = ResponseCache()


# ---------- 사용량 기록 ----------

class Usage:
    """하루 단위 사용량. 메모리에 모으고 DB(llm_usage)에도 반영한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cost_today: dict[str, float] = {}

    def cost_today(self) -> float:
        with self._lock:
            return self._cost_today.get(date.today().isoformat(), 0.0)

    def record(self, provider: str, model: str, purpose: str, *, prompt: int = 0, completion: int = 0, cost: float = 0.0,
               cache_hit: bool = False, error: bool = False, fallback: bool = False) -> None:
        day = date.today().isoformat()
        with self._lock:
            self._cost_today[day] = self._cost_today.get(day, 0.0) + cost
        try:
            from .db import SessionLocal
            from .models import LlmUsage
            with SessionLocal() as db:
                row = db.query(LlmUsage).filter_by(day=day, provider=provider, model=model, purpose=purpose).first()
                if row is None:
                    row = LlmUsage(day=day, provider=provider, model=model, purpose=purpose, calls=0, cache_hits=0, errors=0,
                                   fallbacks=0, prompt_tokens=0, completion_tokens=0, cost_usd=0.0)
                    db.add(row)
                row.calls += 0 if cache_hit else 1
                row.cache_hits += 1 if cache_hit else 0
                row.errors += 1 if error else 0
                row.fallbacks += 1 if fallback else 0
                row.prompt_tokens += prompt
                row.completion_tokens += completion
                row.cost_usd += cost
                db.commit()
        except Exception:  # 기록 실패가 상담을 막으면 안 된다
            pass

    def reset(self) -> None:
        with self._lock:
            self._cost_today.clear()


usage = Usage()


# ---------- 호출 ----------

def extract_json(text: str) -> str | None:
    """앞뒤에 설명이 붙은 응답에서도 JSON 객체를 꺼낸다."""
    try:
        json.loads(text)
        return text
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(0))
            return m.group(0)
        except ValueError:
            return None
    return None


def _schema_fallback_messages(messages: list, schema: dict) -> list:
    hint = "반드시 다음 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요: " + json.dumps(schema["schema"], ensure_ascii=False, separators=(",", ":"))
    return [{"role": "system", "content": hint}, *messages]


def chat(messages: list, *, purpose: str, schema: dict | None = None, max_tokens: int = 500, vision: bool = False,
         timeout: int = 30, use_cache: bool = True) -> LLMResult:
    provs = providers()
    if not provs:
        raise LLMError("not_configured")
    budget = _float("RUTI_DAILY_BUDGET_USD", 0.0)
    if budget > 0 and usage.cost_today() >= budget:
        raise LLMError("budget")

    ckey = ResponseCache.key(messages, schema, vision, max_tokens) if use_cache else None
    if ckey:
        hit = cache.get(ckey)
        if hit:
            usage.record(hit.provider, hit.model, purpose, cache_hit=True)
            return LLMResult(hit.content, hit.provider, hit.model, cached=True)

    last_error, attempted, soonest = "error", False, 0.0
    for i, p in enumerate(provs):
        wait = cooldowns.active(p.name)
        if wait > 0:
            soonest = wait if not soonest else min(soonest, wait)
            last_error = "quota"
            continue
        attempted = True
        model = p.vision_model if vision else p.model
        body = {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": schema}
        try:
            resp = httpx.post(f"{p.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {p.api_key}"}, timeout=timeout)
            if resp.status_code == 400 and schema and re.search(r"response_format|json_schema", getattr(resp, "text", "") or ""):
                # 구조화 출력 미지원 공급자 → json_object + 지시문으로 한 번 더
                body["messages"] = _schema_fallback_messages(messages, schema)
                body["response_format"] = {"type": "json_object"}
                resp = httpx.post(f"{p.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {p.api_key}"}, timeout=timeout)
        except httpx.HTTPError:
            cooldowns.hit(p.name, "transient")
            usage.record(p.name, model, purpose, error=True)
            last_error = "error"
            continue
        code = resp.status_code
        if code in (401, 403):
            cooldowns.hit(p.name, "auth")
            usage.record(p.name, model, purpose, error=True)
            last_error = "auth"
            continue
        if code == 429:
            cooldowns.hit(p.name, "quota")
            usage.record(p.name, model, purpose, error=True)
            last_error = "quota"
            continue
        if code >= 400:
            if code >= 500:
                cooldowns.hit(p.name, "transient")
            usage.record(p.name, model, purpose, error=True)
            last_error = "error"
            continue
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            usage.record(p.name, model, purpose, error=True)
            last_error = "error"
            continue
        if schema:
            fixed = extract_json(content)
            if fixed is None:
                usage.record(p.name, model, purpose, error=True)
                last_error = "error"
                continue
            content = fixed
        u = data.get("usage") or {}
        pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        cost = (pt * p.price_in + ct * p.price_out) / 1_000_000
        cooldowns.ok(p.name)
        usage.record(p.name, model, purpose, prompt=pt, completion=ct, cost=cost, fallback=i > 0)
        result = LLMResult(content, p.name, model, fallback=i > 0, usage={"prompt_tokens": pt, "completion_tokens": ct, "cost_usd": cost})
        if ckey:
            cache.put(ckey, result)
        return result

    raise LLMError(last_error, int(soonest) if not attempted else 0)
