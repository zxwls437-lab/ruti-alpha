import base64
import json

import pytest

from app import scan
from app.db import SessionLocal
from app.models import Ingredient
from tests.conftest import signup
from tests.test_api import FakeResponse

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
JPEG_URL = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 100).decode()


def seed_ingredients():
    with SessionLocal() as db:
        db.add_all([
            Ingredient(name_ko="정제수", name_en="Water"),
            Ingredient(name_ko="글리세린", name_en="Glycerin", restriction="[중국] 제한 - 다이에틸렌글라이콜 0.1% 이하 / [아세안] 제한 - 불순물 기준"),
            Ingredient(name_ko="살리실릭애씨드", name_en="Salicylic Acid", restriction="[대한민국] 배합한도 - 씻어내는 제품 2% / [EU] 제한 - 3%"),
            Ingredient(name_ko="1,2-헥산다이올", name_en="1,2-Hexanediol"),
            Ingredient(name_ko="나이아신아마이드", name_en="Niacinamide", description="비타민 B3"),
            Ingredient(name_ko="향료", name_en="Fragrance"),
            Ingredient(name_ko="하이드로퀴논", name_en="Hydroquinone", restriction="[대한민국] 금지 / [EU] 금지"),
            Ingredient(name_ko="레티놀", name_en="Retinol", restriction="[EU] 제한 - 0.3%"),
            Ingredient(name_ko="부틸렌글라이콜", name_en="Butylene Glycol", synonyms="1,3-Butanediol"),
        ])
        db.commit()


# ---------- 성분 나누기 ----------

def test_split_keeps_numeric_commas_and_strips_prefix():
    text = "[전성분] 정제수, 글리세린,1,2-헥산다이올 , 향료(리모넨)\n나이아신아마이드; 정제수"
    assert scan.split_ingredients(text) == ["정제수", "글리세린", "1,2-헥산다이올", "향료(리모넨)", "나이아신아마이드"]


def test_split_ingredients_english():
    assert scan.split_ingredients("Ingredients: Water, Glycerin, 1,3-Butanediol.") == ["Water", "Glycerin", "1,3-Butanediol"]


# ---------- 대조 ----------

def test_analyze_flags(client):
    seed_ingredients()
    with SessionLocal() as db:
        r = scan.analyze(db, ["정제수", "글리세린", "향료(리모넨)", "하이드로퀴논", "레티놀", "나이아신아마이드드", "1,3-Butanediol", "알수없는성분"],
                         ["건성 피부", "향료에 민감해요"])
    by = {i["input"]: i for i in r["items"]}
    assert by["정제수"]["flags"] == [] and by["정제수"]["match"] == "exact"
    assert by["글리세린"]["flags"] == ["foreign_regulated"]  # 해외 불순물 기준만 있는 성분은 경고가 아님
    assert by["향료(리모넨)"]["ingredient"]["name_ko"] == "향료" and "memory_conflict" in by["향료(리모넨)"]["flags"]
    assert by["하이드로퀴논"]["flags"] == ["kr_ban"]
    assert by["레티놀"]["flags"] == ["foreign_regulated"]
    assert by["나이아신아마이드드"]["match"] == "fuzzy" and "check_spelling" in by["나이아신아마이드드"]["flags"]
    assert by["1,3-Butanediol"]["ingredient"]["name_ko"] == "부틸렌글라이콜"
    assert by["알수없는성분"]["ingredient"] is None
    assert r["summary"] == {"total": 8, "matched": 7, "kr_ban": 1, "kr_limit": 0, "foreign_regulated": 2, "memory_conflict": 1, "unknown": 1}


def test_classify_restriction():
    assert scan.classify_restriction("") is None
    assert scan.classify_restriction("[대한민국] 금지 / [EU] 금지") == "kr_ban"
    assert scan.classify_restriction("[EU] 금지 / [대한민국] 배합한도 - 2%") == "kr_limit"
    assert scan.classify_restriction("[중국] 제한 - 불순물") == "foreign"
    with SessionLocal() as db:
        pass


# ---------- 글자 붙여넣기 API ----------

def test_text_scan_api_and_history(client):
    seed_ingredients()
    a, b = signup(client, "usera"), signup(client, "userb")
    client.post("/memory", headers=a, json={"content": "향료에 민감"})
    r = client.post("/scan/text", headers=a, json={"text": "정제수, 향료, 하이드로퀴논", "product_name": "테스트 크림"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["kr_ban"] == 1 and data["summary"]["memory_conflict"] == 1
    hist = client.get("/scan/history", headers=a).json()["scans"]
    assert hist[0]["product_name"] == "테스트 크림" and hist[0]["summary"]["total"] == 3
    sid = data["id"]
    assert client.get(f"/scan/{sid}", headers=a).json()["items"][2]["input"] == "하이드로퀴논"
    assert client.get(f"/scan/{sid}", headers=b).status_code == 404
    assert client.delete(f"/scan/{sid}", headers=b).status_code == 404
    assert client.delete(f"/scan/{sid}", headers=a).status_code == 200
    assert client.post("/scan/text", headers=a, json={"text": " , ; "}).status_code == 422
    assert client.post("/scan/text", json={"text": "정제수"}).status_code == 401


# ---------- 사진 API ----------

def test_decode_image():
    assert scan.decode_image(JPEG_URL)[1] == "image/jpeg"
    assert scan.decode_image(base64.b64encode(PNG).decode())[1] == "image/png"
    with pytest.raises(scan.ScanError) as e:
        scan.decode_image(base64.b64encode(b"GIF89a....").decode())
    assert e.value.status == 415
    with pytest.raises(scan.ScanError):
        scan.decode_image("!!!not base64!!!")


def test_image_scan_without_key(client):
    h = signup(client)
    r = client.post("/scan/image", headers=h, json={"image": JPEG_URL})
    assert r.status_code == 503 and "붙여넣어" in r.json()["detail"]


def ocr_response(names, is_list=True, note="", readability="clear", side=None, brand="", product_name="", products=None):
    side = side or ("back" if names else "other")
    if products is None:
        products = [{"brand": brand, "product_name": product_name}] if (brand or product_name) else []
    content = json.dumps({"is_ingredient_list": is_list, "ingredients": names, "note": note, "readability": readability,
                          "side": side, "brand": brand, "product_name": product_name, "products": products}, ensure_ascii=False)
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def test_image_scan_with_ocr(client, monkeypatch):
    seed_ingredients()
    h = signup(client)
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent["body"] = json
        return ocr_response(["정제수", "글리세린, 레티놀", "하이드로퀴논"])

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", fake_post)
    r = client.post("/scan/image", headers=h, json={"image": JPEG_URL, "product_name": "세럼"})
    assert r.status_code == 200, r.text
    assert [i["input"] for i in r.json()["items"]] == ["정제수", "글리세린", "레티놀", "하이드로퀴논"]
    assert r.json()["source"] == "image"
    image_part = sent["body"]["messages"][1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_image_scan_not_ingredient_list(client, monkeypatch):
    h = signup(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: ocr_response([], False, "고양이 사진"))
    r = client.post("/scan/image", headers=h, json={"image": JPEG_URL})
    assert r.status_code == 422 and "고양이 사진" in r.json()["detail"]


def test_image_scan_daily_limit(client, monkeypatch):
    h = signup(client)
    monkeypatch.setenv("RUTI_SCAN_PER_DAY", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: FakeResponse(429))
    assert client.post("/scan/image", headers=h, json={"image": JPEG_URL}).status_code == 503
    assert client.post("/scan/image", headers=h, json={"image": JPEG_URL}).status_code == 429
    # 글자 붙여넣기는 제한 없음
    assert client.post("/scan/text", headers=h, json={"text": "정제수"}).status_code == 200


def test_image_scan_readability(client, monkeypatch):
    seed_ingredients()
    h = signup(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: ocr_response(["정제수", "글리세린"], readability="partial"))
    r = client.post("/scan/image", headers=h, json={"image": JPEG_URL})
    assert r.status_code == 200 and r.json()["readability"] == "partial"
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: ocr_response(["정제수"], readability="poor"))
    r = client.post("/scan/image", headers=h, json={"image": base64.b64encode(PNG).decode()})
    assert r.status_code == 422 and "가까이서" in r.json()["detail"]


def img(n):
    return "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + bytes([n]) * 50).decode()


def test_front_photo_uses_shared_ingredient_list(client, monkeypatch):
    seed_ingredients()
    a, b = signup(client, "first"), signup(client, "second")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # 1) 아직 아무도 뒷면을 안 찍은 제품의 앞면
    monkeypatch.setattr(scan.httpx, "post", lambda *x, **k: ocr_response([], False, side="front", brand="라운드랩", product_name="자작나무 수분 크림"))
    r = client.post("/scan/image", headers=b, json={"image": img(1)}).json()
    assert r["mode"] == "front_not_found" and r["title"] == "라운드랩 자작나무 수분 크림"
    # 2) 첫 사용자가 뒷면을 또렷하게 찍음 (제품명은 사진에서 읽음)
    monkeypatch.setattr(scan.httpx, "post", lambda *x, **k: ocr_response(["정제수", "글리세린", "하이드로퀴논", "향료"], brand="라운드랩", product_name="자작나무 수분크림"))
    r = client.post("/scan/image", headers=a, json={"image": img(2)}).json()
    assert r["mode"] == "back" and r["shared"] is True and r["product_name"] == "라운드랩 자작나무 수분크림"
    # 3) 두 번째 사용자가 앞면만 찍으면 저장된 전성분으로 분석
    client.post("/memory", headers=b, json={"content": "향료에 민감해요"})
    monkeypatch.setattr(scan.httpx, "post", lambda *x, **k: ocr_response([], False, side="front", brand="라운드랩", product_name="자작나무 수분 크림"))
    r = client.post("/scan/image", headers=b, json={"image": img(3)}).json()
    assert r["mode"] == "front_found" and r["from_database"]["confirmations"] == 1
    assert r["summary"]["kr_ban"] == 1 and r["summary"]["memory_conflict"] == 1


def test_blurry_back_is_not_shared_and_confirmations_count(client, monkeypatch):
    seed_ingredients()
    h = signup(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", lambda *x, **k: ocr_response(["정제수", "글리세린", "향료"], readability="partial", product_name="흐린 크림"))
    assert client.post("/scan/image", headers=h, json={"image": img(4)}).json()["shared"] is False
    # 글자 입력 + 제품명 → 저장, 같은 목록 다시 → 확인 횟수 증가
    for _ in range(2):
        assert client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린, 향료", "product_name": "수분 토너"}).json()["shared"] is True
    with SessionLocal() as db:
        from app.models import ProductIngredientList
        rows = db.query(ProductIngredientList).all()
    assert [(r.name, r.confirmations) for r in rows] == [("수분 토너", 2)]
    # 성분이 너무 적거나 제품명이 없으면 저장 안 함
    assert client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린", "product_name": "짧은 것"}).json()["shared"] is False
    assert client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린, 향료"}).json()["shared"] is False


def test_multiple_products_in_photo(client, monkeypatch):
    seed_ingredients()
    a, b = signup(client, "aa1"), signup(client, "bb1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls = {"n": 0}
    two = [{"brand": "Vaseline", "product_name": "Daily Moisture Lotion"}, {"brand": "", "product_name": "Lemon Verbena Body Lotion"}]

    def front_two(*x, **k):
        calls["n"] += 1
        return ocr_response([], False, side="front", brand="Vaseline", product_name="Daily Moisture Lotion", products=two)

    # 레몬 버베나 전성분을 누군가 저장해 둠
    client.post("/scan/text", headers=a, json={"text": "정제수, 글리세린, 향료", "product_name": "Lemon Verbena Body Lotion"})
    monkeypatch.setattr(scan.httpx, "post", front_two)
    r = client.post("/scan/image", headers=b, json={"image": img(9)}).json()
    assert r["mode"] == "multiple_products" and [p["title"] for p in r["products"]] == ["Vaseline Daily Moisture Lotion", "Lemon Verbena Body Lotion"]
    r = client.post("/scan/image", headers=b, json={"image": img(9), "selected": 1}).json()
    assert r["mode"] == "front_found" and r["from_database"]["name"] == "Lemon Verbena Body Lotion"
    assert calls["n"] == 1  # 고른 뒤 재요청은 캐시라 AI를 다시 부르지 않음
    r = client.post("/scan/image", headers=b, json={"image": img(9), "selected": 0}).json()
    assert r["mode"] == "front_not_found" and r["title"] == "Vaseline Daily Moisture Lotion"


def test_back_with_multiple_products_not_shared(client, monkeypatch):
    seed_ingredients()
    h = signup(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    two = [{"brand": "A", "product_name": "크림"}, {"brand": "B", "product_name": "로션"}]
    monkeypatch.setattr(scan.httpx, "post", lambda *x, **k: ocr_response(["정제수", "글리세린", "향료"], brand="A", product_name="크림", products=two))
    r = client.post("/scan/image", headers=h, json={"image": img(10)}).json()
    assert r["mode"] == "back" and r["multiple_products"] is True and r["shared"] is False
    r = client.post("/scan/image", headers=h, json={"image": img(10), "product_name": "A 크림"}).json()
    assert r["shared"] is True


# ---------- 쉬운 판정 ----------

def _result(**counts):
    items, n = [], 0
    for flag, k in counts.items():
        for j in range(k):
            n += 1
            items.append({"input": f"{flag}{j}", "flags": [] if flag == "plain" else ([] if flag == "unknown" else [flag]), "ingredient": None if flag == "unknown" else {}})
    summary = {"total": len(items), "unknown": counts.get("unknown", 0)}
    return {"items": items, "summary": summary}


def test_verdict_rules():
    assert scan.build_verdict(_result(plain=10), ["건성 피부"])["level"] == "good"
    v = scan.build_verdict(_result(plain=10), [])
    assert v["level"] == "good" and v["needs_skin_info"] and v["title"] == "피해야 할 성분은 보이지 않아요"
    # 농도 기준 성분(보존제 등)은 판정을 낮추지 않음
    v = scan.build_verdict(_result(plain=10, kr_limit=2), ["건성"])
    assert v["level"] == "good" and "기준 안에서" in v["reasons"][0]
    assert scan.build_verdict(_result(plain=10, kr_ban=1), ["건성"])["level"] == "avoid"
    assert scan.build_verdict(_result(plain=5, unknown=4), ["건성"])["level"] == "check"
    assert scan.build_verdict(_result(plain=10), ["건성"], readability="partial")["level"] == "check"


def test_verdict_memory_conflict_reason(client):
    seed_ingredients()
    with SessionLocal() as db:
        r = scan.analyze(db, ["정제수", "향료", "글리세린"], ["향료에 민감해요"])
    v = scan.build_verdict(r, ["향료에 민감해요"])
    assert v["level"] == "avoid" and v["title"] == "맞지 않을 수 있어요"
    assert v["reasons"][0] == "향료가 들어 있어요. '향료에 민감해요'라고 알려주셨어요."
    # 그림 설명: 충돌한 성분에 맞는 애니메이션 + 그 사람이 적은 피부 정보
    assert v["explainers"] == [{"scenario": "fragrance", "ingredient": "향료", "memo": "향료에 민감해요", "personal": True}]


def test_explainer_scenarios():
    assert scan.explainer_scenario("향료(Fragrance)") == "fragrance"
    assert scan.explainer_scenario("레티놀") == "retinol"
    assert scan.explainer_scenario("살리실릭애씨드") == "exfoliant"
    assert scan.explainer_scenario("변성알코올") == "alcohol"
    assert scan.explainer_scenario("나이아신아마이드") == "generic"
    items = [{"input": "세라마이드엔피", "flags": []}, {"input": "페녹시에탄올", "flags": ["kr_limit"]}]
    ex = scan.build_explainers(items, ["건성 피부"], "good")
    assert [e["scenario"] for e in ex] == ["limit", "ceramide"]
    assert ex[0]["personal"] is False and ex[1]["memo"] == "건성 피부"
    # 피부 정보가 없으면 세라마이드 설명은 붙이지 않음 (맞춤 근거가 없으므로)
    assert [e["scenario"] for e in scan.build_explainers(items, [], "good")] == ["limit"]


def test_scan_returns_verdict_and_explain_endpoint(client, monkeypatch):
    seed_ingredients()
    h = signup(client)
    r = client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린, 향료, 나이아신아마이드"}).json()
    assert r["verdict"]["level"] == "good" and r["verdict"]["needs_skin_info"] is True
    # AI 없이 설명 요청 → 판정은 유지, 설명은 없음
    e = client.post(f"/scan/{r['id']}/explain", headers=h).json()
    assert e["explanation"] is None and e["verdict"]["level"] == "good"
    # 피부 정보 추가 후 다시 판정 + AI 설명
    client.post("/memory", headers=h, json={"content": "향료에 민감해요"})
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent["body"] = json
        return FakeResponse(200, {"choices": [{"message": {"content": '{"summary": "향료가 들어 있어 **자극**이 될 수 있어요.", "points": ["글리세린은 보습에 도움을 줄 수 있어요"]}'}}]})

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", fake_post)
    e = client.post(f"/scan/{r['id']}/explain", headers=h).json()
    assert e["verdict"]["level"] == "avoid" and e["summary"]["memory_conflict"] == 1
    assert e["explanation"] == {"summary": "향료가 들어 있어 자극이 될 수 있어요.", "points": ["글리세린은 보습에 도움을 줄 수 있어요"]}
    analysis = json.loads(sent["body"]["messages"][1]["content"][len("<analysis>"):-len("</analysis>")])
    assert analysis["level"] == "avoid" and analysis["user_skin_info"] == ["향료에 민감해요"]
    # 저장되어 기록에서 다시 볼 수 있음
    assert client.get(f"/scan/{r['id']}", headers=h).json()["explanation"]["points"][0].startswith("글리세린")
    assert client.post(f"/scan/{r['id']}/explain", headers=signup(client, "other")).status_code == 404


def test_sensitivity_groups_match_picker_choices(client):
    seed_ingredients()
    with SessionLocal() as db:
        db.add_all([Ingredient(name_ko="에탄올", name_en="Alcohol"), Ingredient(name_ko="세틸알코올", name_en="Cetyl Alcohol"),
                    Ingredient(name_ko="글라이콜릭애씨드", name_en="Glycolic Acid")])
        db.commit()
    mems = ["알코올에 민감해요", "각질 제거 성분(AHA·BHA)에 민감해요", "향료에 민감해요"]
    with SessionLocal() as db:
        r = scan.analyze(db, ["정제수", "에탄올", "세틸알코올", "Glycolic Acid", "Fragrance", "레티놀"], mems)
    flagged = {i["input"] for i in r["items"] if "memory_conflict" in i["flags"]}
    # 세틸알코올(보습 성분)은 '알코올'이어도 제외, 영어로 적힌 성분도 묶음으로 잡음
    assert flagged == {"에탄올", "Glycolic Acid", "Fragrance"}
    v = scan.build_verdict(r, mems)
    assert v["level"] == "avoid" and "'알코올에 민감해요'라고 알려주셨어요" in v["reasons"][0]
    assert {e["scenario"] for e in v["explainers"]} >= {"alcohol", "exfoliant"}
    assert all(e["memo"] for e in v["explainers"] if e["personal"])


def test_paraben_and_essential_oil_groups():
    assert scan.group_of("메틸파라벤") == "paraben"
    assert scan.group_of("라벤더오일") == "essential_oil"
    assert scan.group_of("티트리잎오일(Tea Tree Leaf Oil)") == "essential_oil"
    assert scan.group_of("호호바씨오일") is None      # 씨앗 기름은 향 오일이 아님
    assert scan.group_of("세틸알코올") is None
    assert scan.matching_memo("프로필파라벤", ["파라벤에 민감해요"]) == "파라벤에 민감해요"
    assert scan.matching_memo("베르가모트열매오일", ["에센셜 오일에 민감해요"]) == "에센셜 오일에 민감해요"
    assert scan.matching_memo("스쿠알란", ["에센셜 오일에 민감해요"]) == ""
