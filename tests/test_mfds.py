import json

import pytest

from app import ai, mfds, retrieval
from app.db import SessionLocal
from app.models import Ingredient, MfdsRecord, Product
from tests.conftest import make_admin, signup
from tests.test_api import FakeResponse


# ---------- 응답 해석 ----------

@pytest.mark.parametrize("payload", [
    {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "items": [{"A": 1}, {"A": 2}]}},
    {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": "2", "items": {"item": [{"A": 1}, {"A": 2}]}}}},
    {"body": {"totalCount": 2, "items": [{"item": {"A": 1}}, {"item": {"A": 2}}]}},
])
def test_parse_page_shapes(payload):
    items, total = mfds.parse_page(payload)
    assert total == 2 and [i["A"] for i in items] == [1, 2]


def test_parse_page_single_item_and_error():
    items, total = mfds.parse_page({"body": {"totalCount": 1, "items": {"item": {"A": 1}}}})
    assert items == [{"A": 1}] and total == 1
    with pytest.raises(mfds.MfdsError):
        mfds.parse_page({"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED"}})


def test_pick_candidates_and_patterns():
    assert mfds.pick({"ingr_kor_name": " 나이아신아마이드 "}, "name_ko") == "나이아신아마이드"
    assert mfds.pick({"SOMETHING_KOR_NAME": "글리세린"}, "name_ko") == "글리세린"
    assert mfds.pick({"X": ""}, "name_ko") == ""
    assert mfds.pick({"INGR_ENG_NAME": "None", "ENG_NAME": "Glycerin"}, "name_en") == "Glycerin"


def test_fetch_page_reports_xml_error(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "k")
    monkeypatch.setenv("MFDS_INGREDIENT_URL", "https://example.com/api")

    class R:
        status_code, text = 200, "<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></OpenAPI_ServiceResponse>"

    monkeypatch.setattr(mfds.httpx, "get", lambda *a, **k: R())
    with pytest.raises(mfds.MfdsError, match="SERVICE_KEY_IS_NOT_REGISTERED"):
        mfds.fetch_page("ingredient", 1, 10)


def test_missing_settings(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    with pytest.raises(mfds.MfdsError, match="DATA_GO_KR_SERVICE_KEY"):
        mfds.fetch_page("ingredient", 1, 10)


# ---------- 저장 → 변환 ----------

def seed(client):
    with SessionLocal() as db:
        mfds.save_records(db, "ingredient", [
            {"INGR_KOR_NAME": "나이아신아마이드", "INGR_ENG_NAME": "Niacinamide", "CAS_NO": "98-92-0", "ORIGIN_MAJOR_KOR_NAME": "비타민 B3 유도체"},
            {"INGR_KOR_NAME": "레티놀", "INGR_ENG_NAME": "Retinol", "ORIGIN_MAJOR_KOR_NAME": "비타민 A"},
        ])
        mfds.save_records(db, "restricted", [
            {"INGR_STD_NAME": "레티놀", "COUNTRY_NAME": "EU", "REGULATE_TYPE": "제한", "LIMIT_COND": "배합 한도 예시"},
            {"INGR_STD_NAME": "레티놀", "COUNTRY_NAME": "대한민국", "REGULATE_TYPE": "제한", "LIMIT_COND": None},
            {"INGR_STD_NAME": "금지성분", "INGR_ENG_NAME": "Banned", "COUNTRY_NAME": "아세안", "REGULATE_TYPE": "금지", "PROVIS_ATRCL": "None"},
        ])
        mfds.save_records(db, "functional_report", [
            {"ITEM_SEQ": "A1", "ITEM_NAME": "브라이트닝 세럼", "ENTP_NAME": "가나화장품", "EFFECT": "피부의 미백에 도움"},
        ])
        # 같은 항목을 다시 저장해도 중복되지 않음
        mfds.save_records(db, "functional_report", [
            {"ITEM_SEQ": "A1", "ITEM_NAME": "브라이트닝 세럼 리뉴얼", "ENTP_NAME": "가나화장품", "EFFECT": "피부의 미백에 도움"},
        ])
        assert db.query(MfdsRecord).filter_by(dataset="functional_report").count() == 1
        assert mfds.build_ingredients(db) == 3
        assert mfds.build_products(db) == 1
        assert mfds.build_products(db) == 1  # 다시 변환해도 중복 없음
        assert db.query(Product).filter_by(source="mfds").count() == 1


def test_build_and_search(client):
    seed(client)
    h = signup(client)
    with SessionLocal() as db:
        retinol = db.query(Ingredient).filter_by(name_ko="레티놀").one()
        assert retinol.restriction == "[대한민국] 제한 / [EU] 제한 - 배합 한도 예시" and retinol.description == "비타민 A"
        banned = db.query(Ingredient).filter_by(name_ko="금지성분").one()
        assert banned.restriction == "[아세안] 금지" and banned.name_en == "Banned"
    found = client.get("/ingredients/search", headers=h, params={"q": "niacin"}).json()["ingredients"]
    assert [i["name_ko"] for i in found] == ["나이아신아마이드"]
    prods = client.get("/products/search", headers=h, params={"q": "미백"}).json()["products"]
    assert prods[0]["name"] == "브라이트닝 세럼 리뉴얼" and prods[0]["source"] == "mfds" and prods[0]["brand"] == "가나화장품"


def test_conversation_uses_ingredients_and_mfds_products(client, monkeypatch):
    seed(client)
    admin = make_admin(client)
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["body"] = json
        data = next(m["content"] for m in json["messages"] if "</approved_products>" in m["content"])
        ids = [p["id"] for p in __import__("json").loads(data.split("<approved_products>")[1].split("</approved_products>")[0])]
        content = __import__("json").dumps({"answer": "레티놀은 주의가 필요해요.", "product_ids": ids[:1]}, ensure_ascii=False)
        return FakeResponse(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "post", fake_post)
    r = client.post("/conversation", headers=admin, json={"message": "레티놀이랑 미백 세럼 같이 써도 돼?"}).json()
    data = next(m["content"] for m in captured["body"]["messages"] if "<ingredient_info>" in m["content"] and "</ingredient_info>" in m["content"])
    info = json.loads(data.split("<ingredient_info>")[1].split("</ingredient_info>")[0])
    assert [i["name_ko"] for i in info] == ["레티놀"] and info[0]["restriction"].startswith("[대한민국] 제한")
    assert r["products"][0]["source"] == "mfds"


def test_mfds_products_need_no_source_url(client):
    seed(client)
    admin = make_admin(client)
    with SessionLocal() as db:
        pid = db.query(Product).filter_by(source="mfds").one().id
    assert client.post(f"/admin/products/{pid}/approve", headers=admin).status_code == 200


# ---------- 검색 도우미 ----------

def test_keywords_strip_particles():
    kws = retrieval.keywords("레티놀이랑 비타민C를 같이 써도 돼? 보습크림 추천해줘")
    assert "레티놀" in kws and "비타민c" in kws and "보습크림" in kws
    assert "추천해줘" not in kws


def test_ingredient_match_prefers_longer_names(client):
    with SessionLocal() as db:
        db.add_all([Ingredient(name_ko="비타민"), Ingredient(name_ko="비타민 C"), Ingredient(name_ko="글리세린")])
        db.commit()
        names = [i["name_ko"] for i in retrieval.ingredients_in_text(db, "비타민 C랑 글리세린")]
    assert names == ["비타민 C", "글리세린"]


def test_add_missing_columns(tmp_path):
    import sqlalchemy as sa
    from app import db as dbmod
    url = f"sqlite:///{tmp_path}/old.db"
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(200))"))
        c.execute(sa.text("INSERT INTO products (name) VALUES ('옛 제품')"))
    old_engine = dbmod.engine
    dbmod.engine = eng
    try:
        dbmod.add_missing_columns()
    finally:
        dbmod.engine = old_engine
    cols = {c["name"] for c in sa.inspect(eng).get_columns("products")}
    assert {"source", "external_key", "status"} <= cols
    with eng.connect() as c:
        assert c.execute(sa.text("SELECT source FROM products")).scalar() == "manual"


def test_complete_url():
    base = "https://apis.data.go.kr/1471000/CsmtcsIngdCpntInfoService01"
    assert mfds.complete_url(base) == base + "/getCsmtcsIngdCpntInfoService01"
    assert mfds.complete_url(base + "/") == base + "/getCsmtcsIngdCpntInfoService01"
    assert mfds.complete_url(base + "/getOther") == base + "/getOther"
