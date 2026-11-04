import json

from app import vanity
from tests.conftest import signup


def items(*pairs):
    return [{"id": i, "product_name": name, "ingredients": ings} for i, (name, ings) in enumerate(pairs)]


def kinds(checks):
    return [c["kind"] for c in checks]


def test_groups_ignore_spacing_and_parens():
    assert vanity.groups_of(["정제수", "살리실릭 애씨드", "레티놀(비타민A)", "향료"]) == {"bha": ["살리실릭 애씨드"], "retinoid": ["레티놀(비타민A)"], "fragrance": ["향료"]}


def test_combination_rules():
    serum = ("레티놀 세럼", ["정제수", "레티놀"])
    toner = ("BHA 토너", ["정제수", "살리실릭애씨드"])
    peel = ("AHA 필링", ["글라이콜릭애씨드"])
    vitc = ("비타민C 세럼", ["아스코빅애씨드"])
    cream = ("향 크림", ["정제수", "향료"])
    c = vanity.check_combinations(items(serum, toner), [])
    assert kinds(c) == ["retinoid_exfoliant"] and c[0]["products"] == ["BHA 토너", "레티놀 세럼"]
    assert "multiple_exfoliants" in kinds(vanity.check_combinations(items(toner, peel), []))
    assert "duplicate_retinoid" in kinds(vanity.check_combinations(items(serum, ("레티날 크림", ["레티날"])), []))
    assert "pregnancy_retinoid" in kinds(vanity.check_combinations(items(serum), ["임신 중이에요"]))
    assert "fragrance_sensitive" in kinds(vanity.check_combinations(items(cream), ["향료에 민감해요"]))
    assert "vitc_timing" in kinds(vanity.check_combinations(items(vitc, serum), []))
    assert vanity.check_combinations(items(("수분크림", ["정제수", "글리세린"]), cream), []) == []
    # 한 제품에만 레티놀+BHA가 함께 있으면 '여러 제품 조합' 경고는 아님
    assert "retinoid_exfoliant" not in kinds(vanity.check_combinations(items(("올인원", ["레티놀", "살리실릭애씨드"])), []))


def test_vanity_api_flow(client):
    h = signup(client, "vanity1")
    client.post("/memory", headers=h, json={"content": "향료에 민감해요"})
    sid = client.post("/scan/text", headers=h, json={"text": "정제수, 레티놀, 향료", "product_name": "레티놀 크림"}).json()["id"]
    v = client.post("/vanity", headers=h, json={"scan_id": sid}).json()
    assert v["items"][0]["product_name"] == "레티놀 크림" and set(v["items"][0]["groups"]) == {"retinoid", "fragrance"}
    assert kinds(v["checks"]) == ["fragrance_sensitive"]
    assert client.post("/vanity", headers=h, json={"scan_id": sid}).status_code == 409
    v = client.post("/vanity", headers=h, json={"product_name": "BHA 토너", "text": "정제수, 살리실릭애씨드"}).json()
    assert "retinoid_exfoliant" in kinds(v["checks"]) and len(v["items"]) == 2
    assert client.post("/vanity", headers=h, json={"text": "정제수"}).status_code == 422
    other = signup(client, "vanity2")
    assert client.post("/vanity", headers=other, json={"scan_id": sid}).status_code == 404
    assert client.delete(f"/vanity/{v['items'][0]['id']}", headers=other).status_code == 404
    v = client.delete(f"/vanity/{v['items'][0]['id']}", headers=h).json()
    assert [i["product_name"] for i in v["items"]] == ["BHA 토너"] and v["checks"] == []
    assert json.loads(client.get("/me/export", headers=h).content)["vanity"][0]["product_name"] == "BHA 토너"
