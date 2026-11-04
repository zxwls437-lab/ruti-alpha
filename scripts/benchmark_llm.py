"""AI 호출 효율 가상 벤치마크 (실제 API 호출 없음).

비교: 이전 방식(전부 보내기, 예비 AI·캐시 없음) vs 현재 방식(압축 + 캐시 + 예비 AI 전환)
  1) 질문 1회당 입력 토큰 (프롬프트 압축)
  2) 가상 트래픽에서 실제 AI 호출 수 (응답 캐시)
  3) 공급자 장애 상황에서 성공률 (예비 AI 전환)
사용법: python -m scripts.benchmark_llm
모든 트래픽·장애 비율은 아래 ASSUMPTIONS의 가정값이다. 실제 운영 수치는 /admin/llm-usage로 확인.
"""
import json
import os
import random
import re
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["RUTI_LLM_COOLDOWN_SECONDS"] = "0"

from app import ai, llm  # noqa: E402

ASSUMPTIONS = {
    "chat_requests": 2000,
    "faq_share": 0.25,          # 기억·대화 기록 없이 하는 첫 질문 중 자주 묻는 질문 비율
    "faq_pool": 40,             # 자주 묻는 질문 종류 수 (인기도는 Zipf 분포)
    "scan_requests": 300,
    "scan_duplicate_share": 0.10,  # 같은 사진 파일을 다시 올리는 비율
    "primary_failure_rate": 0.08,  # 주 공급자 실패율 (429·5xx·시간초과)
    "fallback_failure_rate": 0.03,
    "output_tokens": 250,
    "price_in_per_m": 0.40, "price_out_per_m": 1.60,  # gpt-4.1-mini 단가 가정 (USD)
}


def estimate_tokens(text: str) -> float:
    """tiktoken을 쓸 수 없을 때의 추정: 한글 음절 0.8, 그 외 글자 3.5자당 1토큰."""
    hangul = len(re.findall(r"[가-힣]", text))
    other = len(re.sub(r"[가-힣\s]", "", text))
    spaces = len(re.findall(r"\s", text))
    return hangul * 0.8 + other / 3.5 + spaces * 0.15


def count(messages: list) -> float:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return sum(len(enc.encode(m["content"])) + 4 for m in messages)
    except Exception:
        return sum(estimate_tokens(m["content"]) + 4 for m in messages)


# ---------- 이전 방식 (압축 전) ----------

def legacy_build_messages(message, memories, products, history, ingredients):
    data = (f"<user_memories>{json.dumps(memories, ensure_ascii=False)}</user_memories>\n"
            f"<approved_products>{json.dumps(products, ensure_ascii=False)}</approved_products>\n"
            f"<ingredient_info>{json.dumps(ingredients or [], ensure_ascii=False)}</ingredient_info>")
    msgs = [{"role": "system", "content": ai.SYSTEM_PROMPT}, {"role": "system", "content": data}]
    msgs += [{"role": h["role"], "content": h["content"]} for h in history]
    msgs.append({"role": "user", "content": message})
    return msgs


# ---------- 현실적인 가상 데이터 ----------

def mfds_product(i):
    func_ = random.choice(["피부의 미백에 도움을 주는", "피부의 주름 개선에 도움을 주는", "자외선으로부터 피부를 보호하는 데 도움을 주는"])
    return {"id": i, "name": f"기능성 제품 {i} 브라이트닝 에센스", "brand": f"{random.choice(['가나', '다라', '마바'])}코스메틱", "category": "기능성화장품",
            "skin_types": [], "key_ingredients": random.choice(["", "나이아신아마이드", "아데노신", "에칠헥실메톡시신나메이트"]),
            "description": f"[식약처 기능성화장품 보고품목]\n기능: {func_} 기능성 화장품\n사용법: 적당량을 취해 얼굴 전체에 펴 바른 후 흡수시킨다. "
                           f"자외선 차단제는 외출 15~30분 전에 바르고 2~3시간마다 덧바른다. 눈에 들어가지 않도록 주의한다.\n보고/심사일: 2024{i % 12 + 1:02d}15",
            "cautions": "", "source_url": "", "source": "mfds"}


def manual_product(i):
    return {"id": 1000 + i, "name": f"세라마이드 보습 크림 {i}", "brand": "예시브랜드", "category": "크림", "skin_types": ["건성", "복합성"],
            "key_ingredients": "세라마이드, 판테놀, 글리세린, 스쿠알란", "description": "건조하고 민감한 피부를 위한 보습 크림입니다. 피부 장벽을 지켜주는 성분을 담았습니다." * 2,
            "cautions": "사용 중 붉은 반점, 부어오름, 가려움 등의 이상이 있으면 사용을 중지하고 전문의와 상담할 것.",
            "source_url": "https://example.com/product/" + str(i), "source": "manual"}


def ingredient(name):
    return {"id": 1, "name_ko": name, "name_en": "Retinol", "cas_no": "68-26-8", "synonyms": "비타민 A, Vitamin A alcohol, all-trans-retinol, Axerophthol",
            "description": "비타민 A의 한 형태로 피부 컨디셔닝제로 쓰인다." * 3,
            "restriction": " / ".join(f"[{c}] 제한 - 얼굴용 제품 0.3%, 바디로션 0.05% 이하로 사용" for c in ["EU", "캐나다", "아세안", "중국", "영국", "스위스"])[:600]}


def prompt_pair(q):
    memories = q.get("memories", []) + ["가벼운 제형 선호"]
    products = [mfds_product(i) for i in range(25)] + [manual_product(i) for i in range(5)]
    history = [{"role": "user", "content": "요즘 피부가 건조해요"},
               {"role": "assistant", "content": "건조할 때는 보습이 가장 중요해요. " * 12}]
    ings = [ingredient("레티놀")] if re.search(r"레티놀|성분|AHA|나이아신", q["message"]) else []
    old = legacy_build_messages(q["message"], memories, products, history, ings)  # 이전: 후보 30개 전부
    new = ai.build_messages(q["message"], memories, products[:int(os.environ.get("RUTI_MAX_PRODUCTS_IN_PROMPT", 15))], history, ings)
    return count(old), count(new)


# ---------- 가상 공급자 ----------

def install_fake_provider(rng, primary_fail, fallback_fail):
    def fake_post(url, json, headers, timeout):
        fail = primary_fail if "primary" in url else fallback_fail
        if rng.random() < fail:
            return _Resp(rng.choice([429, 503]))
        content = '{"answer": "ok", "product_ids": []}' if "answer" in str(json.get("response_format")) else '{"is_ingredient_list": true, "ingredients": ["정제수"], "note": ""}'
        return _Resp(200, {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 250}})

    llm.httpx.post = fake_post


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code, self._p, self.text = code, payload, ""

    def json(self):
        return self._p


def run_traffic(rng, with_fallback: bool, with_cache: bool):
    os.environ["OPENAI_API_KEY"] = "sk-sim"
    os.environ["OPENAI_BASE_URL"] = "https://primary.sim/v1"
    if with_fallback:
        os.environ.update(LLM_FALLBACK_API_KEY="sk-fb", LLM_FALLBACK_BASE_URL="https://fallback.sim/v1", LLM_FALLBACK_MODEL="backup")
    else:
        for k in ("LLM_FALLBACK_API_KEY", "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_MODEL"):
            os.environ.pop(k, None)
    llm.cache.reset(); llm.cooldowns.reset(); llm.usage.record = lambda *a, **k: None  # 기록은 생략
    install_fake_provider(rng, ASSUMPTIONS["primary_failure_rate"], ASSUMPTIONS["fallback_failure_rate"])
    calls = {"n": 0, "billed": 0}
    real_post = llm.httpx.post

    def counting(*a, **k):
        calls["n"] += 1
        resp = real_post(*a, **k)
        calls["billed"] += resp.status_code == 200
        return resp

    llm.httpx.post = counting
    faq = [f"자주 묻는 질문 {i}" for i in range(ASSUMPTIONS["faq_pool"])]
    weights = [1 / (i + 1) ** 1.1 for i in range(len(faq))]
    ok = total = hits = 0
    for n in range(ASSUMPTIONS["chat_requests"]):
        if rng.random() < ASSUMPTIONS["faq_share"]:
            msgs = [{"role": "system", "content": ai.SYSTEM_PROMPT}, {"role": "user", "content": rng.choices(faq, weights)[0]}]
        else:
            msgs = [{"role": "system", "content": ai.SYSTEM_PROMPT}, {"role": "user", "content": f"개인 질문 {n}"}]
        total += 1
        try:
            hits += llm.chat(msgs, purpose="chat", schema=ai.RESPONSE_SCHEMA, use_cache=with_cache).cached
            ok += 1
        except llm.LLMError:
            pass
    images = []
    for n in range(ASSUMPTIONS["scan_requests"]):
        img = rng.choice(images) if images and rng.random() < ASSUMPTIONS["scan_duplicate_share"] else f"image-{n}"
        images.append(img)
        total += 1
        try:
            hits += llm.chat([{"role": "user", "content": img}], purpose="scan", schema={"name": "ingredient_list", "schema": {}}, vision=True, use_cache=with_cache).cached
            ok += 1
        except llm.LLMError:
            pass
    llm.httpx.post = real_post
    return {"requests": total, "success": ok, "provider_calls": calls["n"], "billed": calls["billed"], "cache_hits": hits}


def main():
    random.seed(7)
    questions = json.loads(Path("data/eval_questions.json").read_text(encoding="utf-8"))
    pairs = [prompt_pair(q) for q in questions]
    old_in = sum(p[0] for p in pairs) / len(pairs)
    new_in = sum(p[1] for p in pairs) / len(pairs)

    before = run_traffic(random.Random(1), with_fallback=False, with_cache=False)
    after = run_traffic(random.Random(1), with_fallback=True, with_cache=True)

    a = ASSUMPTIONS
    def per_call(in_tokens):
        return (in_tokens * a["price_in_per_m"] + a["output_tokens"] * a["price_out_per_m"]) / 1_000_000

    # 성공한 답변 1,000건당 비용 = 과금된(성공) 호출 수 / 성공 답변 수 × 호출 1회 비용
    cost_before = per_call(old_in) * before["billed"] / before["success"] * 1000
    cost_after = per_call(new_in) * after["billed"] / after["success"] * 1000
    hit_rate = after["cache_hits"] / after["success"]
    sb, sa = before["success"] / before["requests"] * 100, after["success"] / after["requests"] * 100

    print("가정:", json.dumps(a, ensure_ascii=False))
    print("\n=== 1. 질문 1회당 입력 토큰 (프롬프트 압축) ===")
    print(f"이전 {old_in:,.0f} → 현재 {new_in:,.0f} 토큰  ({(1 - new_in / old_in) * 100:.1f}% 감소)")
    print("\n=== 2. 응답 캐시 (가상 트래픽: 상담 %d건 + 사진 %d건) ===" % (a["chat_requests"], a["scan_requests"]))
    print(f"캐시 적중 {after['cache_hits']}건 / 성공 {after['success']}건 = {hit_rate * 100:.1f}% → AI를 부르지 않고 응답")
    print("\n=== 3. 공급자 장애 시 성공률 (주 공급자 실패율 %.0f%%, 예비 %.0f%%) ===" % (a["primary_failure_rate"] * 100, a["fallback_failure_rate"] * 100))
    print(f"이전 {sb:.1f}% → 현재 {sa:.1f}%  (+{sa - sb:.1f}%p, 실패한 상담 {(1 - (100 - sa) / (100 - sb)) * 100:.0f}% 감소)")
    print("\n=== 종합: 성공한 답변 1,000건당 추정 AI 비용 ===")
    print(f"이전 ${cost_before:.4f} → 현재 ${cost_after:.4f}  ({(1 - cost_after / cost_before) * 100:.1f}% 절감)")


if __name__ == "__main__":
    main()
