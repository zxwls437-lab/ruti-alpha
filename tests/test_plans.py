import json

from app import plans, scan
from app.db import SessionLocal
from app.models import User
from tests.conftest import make_admin, signup
from tests.test_api import FakeResponse


def answer(*a, **k):
    return FakeResponse(200, {"choices": [{"message": {"content": '{"answer": "네", "product_ids": [], "urgent": false}'}}]})


def test_default_is_unlimited(client):
    h = signup(client, "free1")
    me = client.get("/me", headers=h).json()
    assert me["plan"] == "free" and me["today"]["chat_limit"] == 0 and me["today"]["chat_used"] == 0


def test_free_chat_quota_and_plus_grant(client, monkeypatch):
    monkeypatch.setenv("RUTI_FREE_CHAT_PER_DAY", "2")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(scan.httpx, "post", answer)
    h = signup(client, "free2")
    assert client.post("/conversation", headers=h, json={"message": "안녕 1"}).status_code == 200
    assert client.post("/conversation", headers=h, json={"message": "안녕 2"}).status_code == 200
    r = client.post("/conversation", headers=h, json={"message": "안녕 3"})
    assert r.status_code == 429 and "RUTI Plus" in r.json()["detail"]
    assert client.get("/me", headers=h).json()["today"] == {"chat_used": 2, "chat_limit": 2, "scan_used": 0, "scan_limit": 0}
    admin = make_admin(client)
    assert client.post("/admin/users/free2/plan", headers=h, json={"plan": "plus"}).status_code == 403
    g = client.post("/admin/users/FREE2/plan", headers=admin, json={"plan": "plus", "days": 30}).json()
    assert g["plan"] == "plus" and g["plus_until"]
    assert client.post("/conversation", headers=h, json={"message": "안녕 4"}).status_code == 200
    # Plus 회수
    client.post("/admin/users/free2/plan", headers=admin, json={"plan": "free"})
    assert client.post("/conversation", headers=h, json={"message": "안녕 5"}).status_code == 429
    assert client.post("/admin/users/nobody/plan", headers=admin, json={"plan": "plus"}).status_code == 404


def test_expired_plus_falls_back_to_free(client, monkeypatch):
    from datetime import timedelta
    from app.db import utcnow
    monkeypatch.setenv("RUTI_FREE_CHAT_PER_DAY", "1")
    h = signup(client, "exp1")
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="exp1").one()
        u.plan, u.plus_until = "plus", utcnow() - timedelta(days=1)
        db.commit()
        assert not plans.is_plus(u)
    assert client.get("/me", headers=h).json()["plan"] == "free"


def test_free_scan_quota_counts_images_only(client, monkeypatch):
    import base64
    monkeypatch.setenv("RUTI_FREE_SCAN_PER_DAY", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    content = json.dumps({"is_ingredient_list": True, "ingredients": ["정제수"], "note": "", "readability": "clear", "side": "back",
                          "brand": "", "product_name": "", "products": []})
    monkeypatch.setattr(scan.httpx, "post", lambda *a, **k: FakeResponse(200, {"choices": [{"message": {"content": content}}]}))
    h = signup(client, "scanq")
    img = lambda n: "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + bytes([n]) * 30).decode()
    assert client.post("/scan/image", headers=h, json={"image": img(1)}).status_code == 200
    r = client.post("/scan/image", headers=h, json={"image": img(2)})
    assert r.status_code == 429 and "붙여넣기" in r.json()["detail"]
    assert client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린"}).status_code == 200
    # 관리자는 제한 없음
    admin = make_admin(client)
    assert client.post("/scan/image", headers=admin, json={"image": img(3)}).status_code == 200
    assert client.post("/scan/image", headers=admin, json={"image": img(4)}).status_code == 200
