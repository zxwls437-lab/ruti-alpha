import httpx

from app import ai
from tests.conftest import make_admin, signup, signup_body

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
    for path in ("/", "/chat", "/scan", "/community", "/mypage", "/admin", "/static/common.css", "/static/common.js"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path


def test_auth_required(client):
    assert client.get("/memory").status_code == 401
    assert client.get("/memory", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_signup_login_logout(client):
    signup(client, "alice")
    assert client.post("/auth/signup", json=signup_body("alice")).status_code == 409
    assert client.post("/auth/login", json={"username": "alice", "password": "nope-nope"}).status_code == 401
    token = client.post("/auth/login", json={"username": "ALICE", "password": "password123"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=h).json()
    assert me["username"] == "alice" and me["name"] == "테스터" and me["is_admin"] is False and me["needs_consent"] == []
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_signup_validation(client):
    assert client.post("/auth/signup", json=signup_body("a")).status_code == 422
    assert client.post("/auth/signup", json=signup_body("bob", "short")).status_code == 422


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
    def __init__(self, status_code, payload=None, text=""):
        self.status_code, self._payload, self.text = status_code, payload, text

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


def test_normalize_db_url():
    from app.db import normalize_url
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("sqlite:///./ruti.db") == "sqlite:///./ruti.db"


def test_bootstrap_admin(client, monkeypatch):
    from app.main import bootstrap_admin
    monkeypatch.setenv("RUTI_BOOTSTRAP_ADMIN_USERNAME", "Boss")
    monkeypatch.setenv("RUTI_BOOTSTRAP_ADMIN_PASSWORD", "bosspass1")
    bootstrap_admin()
    bootstrap_admin()  # 두 번 실행해도 중복 생성 없음
    login = lambda pw: client.post("/auth/login", json={"username": "boss", "password": pw})
    assert login("bosspass1").json()["user"]["is_admin"] is True
    monkeypatch.setenv("RUTI_BOOTSTRAP_ADMIN_PASSWORD", "newbosspass")
    bootstrap_admin()
    assert login("bosspass1").status_code == 401
    assert login("newbosspass").status_code == 200


def test_eval_checker():
    from scripts.run_eval import check
    ok = ai.AIResult("건성이시니까 세라마이드가 든 크림을 써보세요.", "openai", [1])
    assert check({"message": "x"}, ok, False, {1}) == []
    bad = ai.AIResult("승인된 제품 목록이 없어요. **완치**됩니다", "openai", [2])
    problems = check({"message": "x"}, bad, False, {1})
    assert any("승인" in p for p in problems) and any("제품 ID" in p for p in problems)
    assert check({"message": "x", "expect_safety_hold": True}, ok, False, {1}) == ["응급 표현인데 안전 안내로 막히지 않음"]


def test_eval_questions_safety_flags_match_rules():
    import json
    from pathlib import Path
    qs = json.loads(Path("data/eval_questions.json").read_text(encoding="utf-8"))
    for q in qs:
        assert ai.needs_safety_hold(q["message"]) == q.get("expect_safety_hold", False), q["id"]


def test_ai_urgent_flag_turns_into_safety_guidance(client, monkeypatch):
    h = signup(client)
    msg = "로션 바르고 나서 숨이 턱 막히고 목이 조여요"
    assert not ai.needs_safety_hold(msg)  # 단어 목록으로는 못 잡는 표현
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: FakeResponse(200, {"choices": [{"message": {"content":
        '{"answer": "보습 크림을 바꿔 보세요", "product_ids": [], "urgent": true}'}}]}))
    r = client.post("/conversation", headers=h, json={"message": msg}).json()
    assert r["status"] == "SAFETY_HOLD" and r["engine"] == "safety_ai" and "119" in r["answer"] and r["product_ids"] == []


def test_pwa_files(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["content-type"].startswith("application/manifest+json")
    data = m.json()
    assert data["display"] == "standalone" and data["start_url"].startswith("/home")
    for icon in data["icons"]:
        r = client.get(icon["src"])
        assert r.status_code == 200 and r.content[:4] == b"\x89PNG", icon["src"]
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"] and sw.headers["service-worker-allowed"] == "/"
    assert client.get("/static/offline.html").status_code == 200
    assert client.get("/static/icons/../main.py").status_code == 404
    assert 'rel="manifest"' in client.get("/scan").text
    # 새 화면: 홈(/ 와 /home), 루틴, 개발 현황(/dev)
    for path in ("/", "/home", "/routine", "/dev", "/static/explain.js"):
        assert client.get(path).status_code == 200, path
    assert "홈" in client.get("/static/common.js").text


def test_legal_pages_public_and_filled(client, monkeypatch):
    monkeypatch.setenv("RUTI_OPERATOR_NAME", "루티 <테스트>")
    monkeypatch.setenv("RUTI_CONTACT_EMAIL", "help@example.com")
    for path in ("/privacy", "/terms", "/account-deletion"):
        r = client.get(path)  # 로그인 없이 열람 가능 (구글 플레이 제출용)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "{{" not in r.text and "루티 &lt;테스트&gt;" in r.text
    assert "OpenAI" in client.get("/privacy").text and "국외 이전" in client.get("/privacy").text
    assert "초안" in client.get("/terms").text
    monkeypatch.setenv("RUTI_LEGAL_DRAFT", "false")
    assert "초안" not in client.get("/terms").text
    assert client.get("/legal/legal.css").status_code == 200


def test_conversation_saves_new_skin_info_from_chat(client, monkeypatch):
    headers = signup(client, "chatmemo1")
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["body"] = json
        content = ('{"answer": "향료 없는 보습제를 써 보세요.", "product_ids": [], "urgent": false,'
                   ' "new_memories": ["건성 피부", "향료에 민감해요", "향료에 민감해요", "x"]}')
        return FakeResponse(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "post", fake_post)
    client.post("/memory", headers=headers, json={"content": "건성 피부"})
    r = client.post("/conversation", headers=headers, json={"message": "건성이고 향료 쓰면 빨개져요"}).json()
    # 이미 있던 '건성 피부', 중복, 너무 짧은 글은 빼고 새 정보만 저장
    assert r["saved_memories"] == ["향료에 민감해요"]
    mems = [m["content"] for m in client.get("/memory", headers=headers).json()["memories"]]
    assert mems == ["건성 피부", "향료에 민감해요"]
    # 이름으로 부르도록 이름이 프롬프트에 들어감
    assert "테스터" in " ".join(m["content"] for m in captured["body"]["messages"])
    # 민감정보 동의를 철회하면 자동 저장하지 않음
    client.put("/me/consents", headers=headers, json={"consents": {"sensitive": False}})
    client.post("/conversation", headers=headers, json={"message": "지성으로 바뀐 것 같아요"})
    assert client.get("/memory", headers=headers).status_code == 403 or \
        client.get("/memory", headers=headers).json()["memories"] == []


def test_clean_new_memories():
    assert ai.clean_new_memories(["  지성  피부 ", "건성", None, "가" * 50], ["건성 피부"]) == ["지성 피부"]
    assert ai.clean_new_memories("not a list", []) == []


def test_admin_users_sorted_and_visitor_counts(client):
    admin = make_admin(client, "mmadmin")
    for name in ("zeta01", "Alpha01", "bravo01"):
        signup(client, name)
    users = client.get("/admin/users", headers=admin).json()["users"]
    assert [u["username"] for u in users] == ["alpha01", "bravo01", "mmadmin", "zeta01"]  # 아이디 A→Z
    assert "password_hash" not in users[0]
    assert [u["username"] for u in client.get("/admin/users?q=bra", headers=admin).json()["users"]] == ["bravo01"]
    v = client.get("/admin/stats/visitors", headers=admin).json()
    # 가입하면서 로그인한 사용자는 '지금 접속 중'으로 셈
    assert v["total_users"] == 4 and v["online_now"] >= 1 and v["today"] >= 1 and v["new_today"] == 4
    user = signup(client, "plainuser")
    assert client.get("/admin/users", headers=user).status_code == 403


def test_app_info_public(client, monkeypatch):
    monkeypatch.setenv("RUTI_CONTACT_EMAIL", "help@example.com")
    r = client.get("/app-info").json()
    assert r["contact_email"] == "help@example.com" and r["version"] and r["terms_version"]


def test_find_products_by_name(client):
    from app.db import SessionLocal
    from app.models import Product, ProductIngredientList
    headers = signup(client, "finder1")
    with SessionLocal() as db:
        db.add(Product(name="데일리 선크림", brand="B사", category="기능성화장품", status="approved", source="mfds",
                       description="[식약처 기능성화장품 보고품목]\n기능: 자외선 차단 SPF50+ PA++++\n사용법: 외출 15분 전 바른다"))
        db.add(ProductIngredientList(brand="B사", name="데일리 선크림", name_key="b사데일리선크림", ingredients='["정제수", "징크옥사이드", "글리세린"]', list_hash="x"))
        db.add(ProductIngredientList(brand="", name="촉촉 토너", name_key="촉촉토너", ingredients='["정제수", "글리세린", "판테놀"]', list_hash="y"))
        db.commit()
    r = client.get("/products/find?q=선크림", headers=headers).json()["products"]
    assert r[0]["name"] == "데일리 선크림" and "SPF50+" in r[0]["functions"] and "15분" in r[0]["usage"]
    assert r[0]["ingredients"][:2] == ["정제수", "징크옥사이드"]
    assert client.get("/products/find?q=촉촉", headers=headers).json()["products"][0]["source"] == "shared"
    assert client.get("/products/find?q=a", headers=headers).json()["products"] == []
