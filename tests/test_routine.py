from app import routine
from tests.conftest import signup


def _add(client, headers, name, text):
    r = client.post("/vanity", headers=headers, json={"product_name": name, "text": text})
    assert r.status_code == 201, r.text
    return {i["product_name"]: i["id"] for i in r.json()["items"]}


def test_guess_step_and_slots():
    assert routine.guess_step("데일리 선크림 SPF50", ["정제수"]) == "sunscreen"
    assert routine.guess_step("이름없는 제품", ["정제수", "징크옥사이드"]) == "sunscreen"
    assert routine.guess_step("약산성 클렌징 폼", []) == "cleanser"
    assert routine.guess_step("수분 크림", []) == "cream"
    assert routine.guess_slots("serum", ["정제수", "레티놀"]) == "pm"
    assert routine.guess_slots("toner", ["살리실릭애씨드"]) == "pm"
    assert routine.guess_slots("sunscreen", []) == "am"
    assert routine.guess_slots("cream", ["글리세린"]) == "am,pm"


def test_recommend_rules():
    dry = routine.recommend(["건성 피부", "주름이 고민이에요"])
    assert dry["skin"] == "건성" and dry["am"][-1]["step"] == "sunscreen"
    assert any("레티놀" in s["title"] for s in dry["pm"])
    assert any("세라마이드" in s["look_for"] for s in dry["am"] if s["step"] == "cream")
    # 민감성: 단계 줄이고 레티놀·BHA 빼고 향료 피하기
    sens = routine.recommend(["건성 피부", "민감성 피부", "주름이 고민이에요"])
    assert not any(s["step"] == "toner" for s in sens["am"])
    assert not any("레티놀" in s["title"] for s in sens["pm"]) and "향료" in sens["avoid"]
    # 레티놀에 민감하다고 했으면 추천에서 뺌, 임신 중에도 뺌
    assert not any("레티놀" in s["title"] for s in routine.recommend(["주름이 고민이에요", "레티놀에 민감해요"])["pm"])
    preg = routine.recommend(["주름이 고민이에요", "임신·수유 중이에요"])
    assert not any("레티놀" in s["title"] for s in preg["pm"]) and any("임신" in n for n in preg["notes"])
    oily = routine.recommend(["지성 피부", "트러블이 잘 나요"])
    assert any("BHA" in s["title"] for s in oily["pm"])
    assert routine.recommend([])["needs_skin_info"]


def test_routine_api_checks_logs_and_conflicts(client):
    h = signup(client, "routine1")
    client.post("/memory", headers=h, json={"content": "향료에 민감해요"})
    ids = _add(client, h, "데일리 선크림", "정제수, 징크옥사이드, 글리세린")
    ids = _add(client, h, "나이트 레티놀 세럼", "정제수, 레티놀, 글리세린")
    ids = _add(client, h, "라벤더 수분 크림", "정제수, 글리세린, 향료")
    r = client.get("/routine/today", headers=h).json()
    am = [i["product_name"] for i in r["routine"]["am"]]
    pm = [i["product_name"] for i in r["routine"]["pm"]]
    assert am == ["라벤더 수분 크림", "데일리 선크림"]  # 보습 → 선크림 순서, 레티놀은 아침에 없음
    assert pm == ["나이트 레티놀 세럼", "라벤더 수분 크림"]
    assert next(i for i in r["routine"]["am"] if i["product_name"] == "라벤더 수분 크림")["conflict"] == "향료에 민감해요"
    # 오늘 체크
    r = client.post("/routine/check", headers=h, json={"item_id": ids["데일리 선크림"], "slot": "am"}).json()
    assert next(i for i in r["routine"]["am"] if i["id"] == ids["데일리 선크림"])["done"] is True
    r = client.post("/routine/check", headers=h, json={"item_id": ids["데일리 선크림"], "slot": "am", "done": False}).json()
    assert not any(i["done"] for i in r["routine"]["am"])
    # 단계·시간 바꾸기
    r = client.patch(f"/routine/items/{ids['라벤더 수분 크림']}", headers=h, json={"slots": ["pm"]}).json()
    assert [i["product_name"] for i in r["routine"]["am"]] == ["데일리 선크림"]
    # 피부 컨디션 기록 (하루 한 번, 다시 쓰면 바뀜)
    client.put("/routine/log", headers=h, json={"mood": 2})
    r = client.put("/routine/log", headers=h, json={"mood": 3, "note": "촉촉해요"}).json()
    assert len(r["logs"]) == 1 and r["logs"][0]["mood"] == 3
    # 화장대에서 빼면 체크 기록도 함께 지움
    client.post("/routine/check", headers=h, json={"item_id": ids["데일리 선크림"], "slot": "am"})
    assert client.delete(f"/vanity/{ids['데일리 선크림']}", headers=h).status_code == 200
    # 민감정보 동의를 철회하면 피부 컨디션 기록도 지우고, 새로 기록할 수 없음
    client.put("/me/consents", headers=h, json={"consents": {"sensitive": False}})
    r = client.get("/routine/today", headers=h).json()
    assert r["logs"] == [] and r["can_log"] is False
    assert client.put("/routine/log", headers=h, json={"mood": 1}).status_code == 403
    # 다른 사람 제품은 못 건드림
    other = signup(client, "routine2")
    assert client.post("/routine/check", headers=other, json={"item_id": ids["나이트 레티놀 세럼"], "slot": "pm"}).status_code == 404


def test_recommend_more_concerns():
    r = routine.recommend(["지성 피부", "속건조가 고민이에요", "다크서클이 고민이에요"])
    assert any(s["title"] == "아이크림" for s in r["am"])
    assert any("속건조" in n for n in r["notes"])
    r = routine.recommend(["탄력이 고민이에요", "레티놀에 민감해요"])
    assert any("펩타이드" in s["title"] for s in r["pm"]) and not any("레티놀 (" in s["title"] for s in r["pm"])
    r = routine.recommend(["여드름 자국이 고민이에요"])
    assert any("비타민C" in s["title"] for s in r["am"])
    r = routine.recommend(["중성 피부", "각질이 고민이에요"])
    assert any("각질 케어" in s["title"] for s in r["pm"])
    r = routine.recommend(["에센셜 오일에 민감해요", "파라벤에 민감해요"])
    assert {"에센셜 오일", "파라벤"} <= set(r["avoid"])
