import base64
import json

from app import reviews, scan
from app.db import SessionLocal
from app.models import Review, ReviewVote
from tests.conftest import make_admin, signup
from tests.test_api import FakeResponse

TEXT = "바르고 나면 당김이 줄고 촉촉해요. 향이 없어서 좋아요."


def body(**kw):
    return {"brand": "라운드랩", "product_name": "자작나무 수분 크림", "rating": 5, "text": TEXT,
            "felt_moisture": True, "felt_irritation": False, "would_rebuy": True, **kw}


def scan_image(client, h, monkeypatch, product="라운드랩 자작나무 수분크림", n=1):
    content = json.dumps({"is_ingredient_list": True, "ingredients": ["정제수", "글리세린", "판테놀"], "note": "", "readability": "clear",
                          "side": "back", "brand": "", "product_name": product, "products": []}, ensure_ascii=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: FakeResponse(200, {"choices": [{"message": {"content": content}}]}))
    img = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + bytes([n]) * 40).decode()
    assert client.post("/scan/image", headers=h, json={"image": img}).status_code == 200


def user_with_skin(client, name, skin):
    h = signup(client, name)
    for s in skin:
        client.post("/memory", headers=h, json={"content": s})
    return h


def test_medical_claim_and_skin_tags():
    assert reviews.has_medical_claim("한 달 쓰고 여드름이 싹 사라졌어요")
    assert reviews.has_medical_claim("아토피가 나았어요")
    assert not reviews.has_medical_claim("보습에 도움이 됐고 순해요")
    assert reviews.skin_tags_from(["건성 피부예요", "향료에 민감해요"]) == ["건성", "민감성", "향료 민감"]
    assert reviews.is_similar({"건성", "민감성"}, {"건성", "민감성", "향료 민감"})
    assert not reviews.is_similar({"건성"}, {"지성"})
    assert not reviews.is_similar({"건성", "민감성"}, {"건성"})
    assert not reviews.is_similar(set(), {"건성"})


def test_write_update_and_verification(client, monkeypatch):
    h = user_with_skin(client, "writer", ["건성 피부", "향료에 민감해요"])
    r = client.post("/reviews", headers=h, json=body()).json()
    assert r["created"] and not r["review"]["verified"] and any("사진 분석" in n for n in r["notices"])
    assert r["review"]["skin_tags"] == ["건성", "민감성", "향료 민감"] and r["review"]["author"]
    # 같은 제품을 사진 분석하면 다시 쓸 때 인증 + 기존 후기 수정 (1인 1후기)
    scan_image(client, h, monkeypatch)
    r = client.post("/reviews", headers=h, json=body(rating=4)).json()
    assert not r["created"] and r["review"]["verified"] and r["review"]["rating"] == 4
    with SessionLocal() as db:
        assert db.query(Review).count() == 1
    # 피부 정보 비공개 선택
    r = client.post("/reviews", headers=h, json=body(show_skin=False)).json()
    assert r["review"]["skin_tags"] == []


def test_validation_and_limits(client, monkeypatch):
    h = signup(client, "valid")
    assert client.post("/reviews", headers=h, json=body(text="짧아요")).status_code == 422
    assert client.post("/reviews", headers=h, json=body(rating=6)).status_code == 422
    assert client.post("/reviews", json=body()).status_code == 401
    monkeypatch.setenv("RUTI_REVIEWS_PER_DAY", "1")
    assert client.post("/reviews", headers=h, json=body()).status_code == 201
    assert client.post("/reviews", headers=h, json=body(product_name="다른 제품")).status_code == 429


def test_sponsored_and_medical_flags(client):
    h = signup(client, "flags")
    r = client.post("/reviews", headers=h, json=body(sponsored=True, text="협찬받아 써봤는데 아토피가 나았어요 정말로")).json()
    assert r["review"]["sponsored"] and r["review"]["excluded_from_stats"]
    assert any("의약품" in n for n in r["notices"]) and any("광고 포함" in n for n in r["notices"])


def test_summary_uses_only_verified_and_similar(client, monkeypatch):
    # 비슷한 피부(건성·민감성) 인증 후기 5개 + 지성 인증 후기 2개 + 미인증 1개 + 협찬 1개
    for i in range(5):
        h = user_with_skin(client, f"dry{i}", ["건성 피부", "민감한 편"])
        scan_image(client, h, monkeypatch, n=10 + i)
        client.post("/reviews", headers=h, json=body(felt_irritation=(i == 0), would_rebuy=(i < 3)))
    for i in range(2):
        h = user_with_skin(client, f"oily{i}", ["지성 피부"])
        scan_image(client, h, monkeypatch, n=20 + i)
        client.post("/reviews", headers=h, json=body(felt_moisture=False))
    client.post("/reviews", headers=user_with_skin(client, "noverify", ["건성", "민감"]), json=body())
    hs = user_with_skin(client, "sponsor", ["건성", "민감"])
    scan_image(client, hs, monkeypatch, n=30)
    client.post("/reviews", headers=hs, json=body(sponsored=True))

    viewer = user_with_skin(client, "viewer", ["건성 피부예요", "민감성"])
    s = client.get("/reviews/summary", headers=viewer, params={"product": "자작나무 수분 크림", "brand": "라운드랩"}).json()
    assert s["total_reviews"] == 9 and s["counted_reviews"] == 7
    assert s["overall"]["n"] == 7 and s["overall"]["moisture_pct"] == 71
    assert s["similar"]["n"] == 5 and s["similar"]["enough"] is True
    assert s["similar"]["irritation_pct"] == 20 and s["similar"]["rebuy_pct"] == 60 and s["similar"]["my_skin_tags"] == ["건성", "민감성"]
    # 지성 사용자에게는 비슷한 후기가 2개뿐 → 비율 숨김
    s2 = client.get("/reviews/summary", headers=user_with_skin(client, "oilyviewer", ["지성"]), params={"product": "자작나무 수분 크림"}).json()
    assert s2["similar"] == {"n": 2, "enough": False, "my_skin_tags": ["지성"]}
    # 목록: 비슷한 피부만
    lst = client.get("/reviews", headers=viewer, params={"product": "자작나무 수분 크림", "similar": True}).json()
    assert lst["total"] == 7  # 비슷한 피부 = 인증 5 + 미인증 1 + 협찬 1 (목록에는 보이되 표시로 구분)


def test_helpful_report_and_admin(client):
    author = signup(client, "auth1")
    rid = client.post("/reviews", headers=author, json=body()).json()["review"]["id"]
    v = [signup(client, f"voter{i}") for i in range(3)]
    assert client.post(f"/reviews/{rid}/helpful", headers=author).status_code == 400
    assert client.post(f"/reviews/{rid}/helpful", headers=v[0]).json() == {"helpful_by_me": True, "helpful_count": 1}
    assert client.post(f"/reviews/{rid}/helpful", headers=v[0]).json() == {"helpful_by_me": False, "helpful_count": 0}
    lst = client.get("/reviews", headers=v[1], params={"product": "자작나무 수분 크림"}).json()["reviews"]
    assert lst[0]["id"] == rid and lst[0]["mine"] is False
    # 신고 3번이면 자동 숨김, 중복 신고는 무시
    client.post(f"/reviews/{rid}/report", headers=v[0], json={"reason": "광고 같아요"})
    assert client.post(f"/reviews/{rid}/report", headers=v[0], json={"reason": "또"}).json()["already"] is True
    client.post(f"/reviews/{rid}/report", headers=v[1], json={"reason": "욕설"})
    client.post(f"/reviews/{rid}/report", headers=v[2], json={"reason": "가짜"})
    assert client.get("/reviews", headers=v[1], params={"product": "자작나무 수분 크림"}).json()["total"] == 0
    admin = make_admin(client)
    rep = client.get("/admin/reviews", headers=admin, params={"status": "hidden"}).json()["reviews"]
    assert rep[0]["id"] == rid and sorted(rep[0]["report_reasons"]) == ["가짜", "광고 같아요", "욕설"]
    assert client.get("/admin/reviews", headers=v[0]).status_code == 403
    client.post(f"/admin/reviews/{rid}/restore", headers=admin)
    assert client.get("/reviews", headers=v[1], params={"product": "자작나무 수분 크림"}).json()["total"] == 1
    client.post(f"/admin/reviews/{rid}/delete", headers=admin)
    with SessionLocal() as db:
        assert db.query(Review).count() == 0 and db.query(ReviewVote).count() == 0


def test_my_reviews_delete_and_account_deletion(client):
    h = signup(client, "mine1")
    rid = client.post("/reviews", headers=h, json=body()).json()["review"]["id"]
    other = signup(client, "mine2")
    client.post(f"/reviews/{rid}/helpful", headers=other)
    assert [r["id"] for r in client.get("/reviews/mine", headers=h).json()["reviews"]] == [rid]
    assert client.delete(f"/reviews/{rid}", headers=other).status_code == 404
    assert json.loads(client.get("/me/export", headers=h).content)["reviews"][0]["rating"] == 5
    client.request("DELETE", "/me", headers=h, json={"password": "password123"})
    with SessionLocal() as db:
        assert db.query(Review).count() == 0 and db.query(ReviewVote).count() == 0
