import httpx

from app import ai
from tests.conftest import make_admin, signup

PRODUCT = {
    "name": "테스트 수분 크림", "brand": "테스트브랜드", "category": "크림",
    "skin_types": ["건성", "복합성"], "key_ingredients": "세라마이드, 판테놀",
    "description": "보습용 크림", "source_url": "https://example.com/product",
}


def add_approved_product(client, admin, **overrides):
    data = {**PRODUCT, **overrides}
    pid = client.post("/products/stage", headers=admin, json=data).json()["id"]
    assert client.post(f"/admin/products/{pid}/approve", headers=admin, json={}).status_code == 200
    return pid


# ---------- 기본 / 인증 ----------

def test_health_status_and_pages(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "estimated_progress_percent" in client.get("/status").json()
    for path in ("/", "/chat", "/admin", "/static/common.css", "/static/common.js"):
        assert client.get(path).status_code == 200, path


def test_auth_required(client):
    assert client.get("/memory").status_code == 401
    assert client.get("/memory", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_signup_login_logout(client):
    signup(client, "alice")
    assert client.post("/auth/signup", json={"username": "alice", "password": "password123"}).status_code == 409
    assert client.post("/auth/login", json={"username": "alice", "password": "nope-nope"}).status_code == 401
    token = client.post("/auth/login", json={"username": "ALICE", "password": "password123"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=h).json() == {"username": "alice", "is_admin": False}
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_signup_validation(client):
    assert client.post("/auth/signup", json={"username": "a", "password": "password123"}).status_code == 422
    assert client.post("/auth/signup", json={"username": "bob", "password": "short"}).status_code == 422


def test_login_rate_limit(client):
    signup(client, "carol")
    codes = [client.post("/auth/login", json={"username": "carol", "password": "wrongpass"}).status_code for _ in range(11)]
    assert codes[-1] == 429


# ---------- 기억 ----------

def test_memory_isolated_per_user(client):
    a, b = signup(client, "usera"), signup(client, "userb")
    mid = client.post("/memory", headers=a, json={"content": "가벼운 제형 선호"}).json()["id"]
    assert len(client.get("/memory", headers=a).json()["memories"]) == 1
    assert client.get("/memory", headers=b).json()["memories"] == []
    assert client.delete(f"/memory/{mid}", headers=b).status_code == 404
    assert client.delete(f"/memory/{mid}", headers=a).status_code == 200


# ---------- 제품 승인 워크플로 ----------

def test_product_approval_workflow(client):
    user, admin = signup(client), make_admin(client)
    staged = client.post("/products/stage", headers=user, json=PRODUCT).json()
    assert staged["status"] == "pending"
    assert client.get("/products/search", headers=user).json()["products"] == []
    assert client.post(f"/admin/products/{staged['id']}/approve", headers=user).status_code == 403
    assert client.get("/admin/products", headers=admin).json()["products"][0]["id"] == staged["id"]
    assert client.post(f"/admin/products/{staged['id']}/approve", headers=admin, json={"note": "확인함"}).json()["status"] == "approved"
    found = client.get("/products/search", headers=user, params={"q": "세라마이드"}).json()["products"]
    assert [p["id"] for p in found] == [staged["id"]]
    assert found[0]["skin_types"] == ["건성", "복합성"]


def test_cannot_approve_without_source(client):
    admin = make_admin(client)
    pid = client.post("/products/stage", headers=admin, json={**PRODUCT, "source_url": ""}).json()["id"]
    assert client.post(f"/admin/products/{pid}/approve", headers=admin).status_code == 400
    client.patch(f"/admin/products/{pid}", headers=admin, json={"source_url": "https://example.com/x"})
    assert client.post(f"/admin/products/{pid}/approve", headers=admin).status_code == 200


def test_reject_and_filters(client):
    admin = make_admin(client)
    add_approved_product(client, admin)
    add_approved_product(client, admin, name="지성용 토너", category="토너", skin_types=["지성"])
    rej = client.post("/products/stage", headers=admin, json={**PRODUCT, "name": "거절될 제품"}).json()["id"]
    client.post(f"/admin/products/{rej}/reject", headers=admin, json={"note": "근거 부족"})
    names = lambda **p: [x["name"] for x in client.get("/products/search", headers=admin, params=p).json()["products"]]
    assert names() == ["테스트 수분 크림", "지성용 토너"]
    assert names(category="토너") == ["지성용 토너"]
    assert names(skin_type="건성") == ["테스트 수분 크림"]
    assert names(q="100%") == []


def test_invalid_source_url(client):
    h = signup(client)
    assert client.post("/products/stage", headers=h, json={**PRODUCT, "source_url": "javascript:alert(1)"}).status_code == 422


# ---------- 상담 ----------

def test_safety_hold(client):
    h = signup(client)
    r = client.post("/conversation", headers=h, json={"message": "바르고 나서 호흡곤란이 있어요"}).json()
    assert r["status"] == "SAFETY_HOLD" and r["engine"] == "safety_rule"


def test_conversation_without_ai_key(client):
    h = signup(client)
    r = client.post("/conversation", headers=h, json={"message": "건성 피부 크림 추천해줘"}).json()
    assert r["status"] == "AI_UNAVAILABLE" and r["engine"] == "ai_not_configured"
    assert client.get("/conversation/history", headers=h).json()["messages"] == []


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code, self._payload = status_code, payload

    def json(self):
        return self._payload


def test_conversation_with_ai_validates_product_ids(client, monkeypatch):
    admin = make_admin(client)
    pid = add_approved_product(client, admin)
    pending = client.post("/products/stage", headers=admin, json={**PRODUCT, "name": "미승인"}).json()["id"]
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["body"] = json
        content = '{"answer": "세라마이드 크림을 써보세요.", "product_ids": [%d, %d, 999]}' % (pid, pending)
        return FakeResponse(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "post", fake_post)
    client.post("/memory", headers=admin, json={"content": "건성 피부"})
    r = client.post("/conversation", headers=admin, json={"message": "보습 크림 추천해줘"}).json()
    assert r["status"] == "OK"
    assert r["product_ids"] == [pid]  # 미승인/존재하지 않는 ID는 제거
    assert r["products"][0]["name"] == "테스트 수분 크림"
    prompt = " ".join(m["content"] for m in captured["body"]["messages"])
    assert "건성 피부" in prompt and "미승인" not in prompt
    hist = client.get("/conversation/history", headers=admin).json()["messages"]
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[1]["products"][0]["id"] == pid
    # 두 번째 질문에는 이전 대화가 맥락으로 들어간다
    client.post("/conversation", headers=admin, json={"message": "더 저렴한 건?"})
    assert any(m["content"] == "보습 크림 추천해줘" for m in captured["body"]["messages"])
    assert client.delete("/conversation/history", headers=admin).status_code == 200
    assert client.get("/conversation/history", headers=admin).json()["messages"] == []


def test_ai_error_codes(client, monkeypatch):
    h = signup(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: FakeResponse(429))
    assert client.post("/conversation", headers=h, json={"message": "안녕"}).json()["engine"] == "ai_quota_or_rate_limit"

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(ai.httpx, "post", boom)
    assert client.post("/conversation", headers=h, json={"message": "안녕"}).json()["engine"] == "ai_error"


def test_chat_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RUTI_CHAT_RATE_PER_MIN", "2")
    h = signup(client)
    codes = [client.post("/conversation", headers=h, json={"message": "안녕"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_product_selection_and_parsing():
    products = [{"id": i, "name": f"제품{i}", "brand": "", "category": "", "skin_types": [], "key_ingredients": "", "description": ""} for i in range(5)]
    products[3]["key_ingredients"] = "나이아신아마이드"
    picked = ai.select_relevant_products("나이아신아마이드 들어간 거", [], products, 2)
    assert picked[0]["id"] == 3 and len(picked) == 2
    assert ai.parse_model_output("not json", {1}) == ("not json", [])
    assert ai.needs_safety_hold("얼굴이 붓고 아파요")
