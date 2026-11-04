import json

from app.db import SessionLocal
from app.models import Consent, Memory, ProductIngredientList, ScanResult, User
from app.security import hash_password
from tests.conftest import ALL_CONSENTS, signup, signup_body


def test_signup_requires_name_and_required_consents(client):
    no_name = signup_body("user1"); no_name.pop("name")
    assert client.post("/auth/signup", json=no_name).status_code == 422
    assert client.post("/auth/signup", json=signup_body("user2", name="  ")).status_code == 422
    for kind in ("age14", "terms", "privacy", "sensitive"):
        body = signup_body("user3"); body["consents"][kind] = False
        r = client.post("/auth/signup", json=body)
        assert r.status_code == 422 and "필수 항목" in r.json()["detail"], kind
    body = signup_body("user4"); body["consents"]["unknown"] = True
    assert client.post("/auth/signup", json=body).status_code == 422
    # 마케팅은 선택
    r = client.post("/auth/signup", json=signup_body("user5", name="지우"))
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["name"] == "지우" and user["needs_consent"] == [] and len(user["nickname"]) >= 2


def test_consents_are_recorded_with_version(client, monkeypatch):
    monkeypatch.setenv("RUTI_TERMS_VERSION", "v-test")
    signup(client, "rec")
    with SessionLocal() as db:
        rows = db.query(Consent).all()
    assert {(c.kind, c.agreed, c.version) for c in rows} == {(k, v, "v-test") for k, v in ALL_CONSENTS.items()}


def test_nickname_auto_unique_and_custom(client):
    a = client.post("/auth/signup", json=signup_body("nick1", nickname="민트라떼")).json()["user"]
    assert a["nickname"] == "민트라떼"
    r = client.post("/auth/signup", json=signup_body("nick2", nickname="민트라떼"))
    assert r.status_code == 409
    assert client.post("/auth/signup", json=signup_body("nick3", nickname="a")).status_code == 422
    nicks = {client.post("/auth/signup", json=signup_body(f"auto{i}")).json()["user"]["nickname"] for i in range(5)}
    assert len(nicks) == 5


def test_profile_view_and_update(client):
    h = signup(client, "prof")
    other = client.post("/auth/signup", json=signup_body("prof2", nickname="겹치는닉")).json()
    me = client.get("/me", headers=h).json()
    assert me["name"] == "테스터" and me["consents"]["marketing"] is False and me["counts"]["skin_info"] == 0
    assert {i["kind"] for i in me["consent_items"]} == set(ALL_CONSENTS)
    r = client.patch("/me", headers=h, json={"name": "새이름", "nickname": "보들보들"}).json()
    assert r["name"] == "새이름" and r["nickname"] == "보들보들"
    assert client.patch("/me", headers=h, json={"nickname": "겹치는닉"}).status_code == 409
    assert client.patch("/me", headers=h, json={"nickname": "공백 안됨"}).status_code == 422
    assert client.get("/me").status_code == 401


def test_consent_changes(client):
    h = signup(client, "cons")
    assert client.post("/memory", headers=h, json={"content": "건성 피부"}).status_code == 201
    # 마케팅 동의 켜기/끄기
    assert client.put("/me/consents", headers=h, json={"consents": {"marketing": True}}).json()["consents"]["marketing"] is True
    # 필수 약관은 철회 불가
    assert client.put("/me/consents", headers=h, json={"consents": {"terms": False}}).status_code == 400
    # 민감정보 철회 → 피부 정보 삭제, 저장 불가
    r = client.put("/me/consents", headers=h, json={"consents": {"sensitive": False}}).json()
    assert r["deleted_skin_info"] == 1 and r["needs_consent"] == ["sensitive"]
    assert client.get("/memory", headers=h).json()["memories"] == []
    r = client.post("/memory", headers=h, json={"content": "다시 저장"})
    assert r.status_code == 403 and "민감정보" in r.json()["detail"]
    # 다시 동의하면 저장 가능
    client.put("/me/consents", headers=h, json={"consents": {"sensitive": True}})
    assert client.post("/memory", headers=h, json={"content": "다시 저장"}).status_code == 201
    with SessionLocal() as db:
        assert db.query(Consent).filter_by(kind="sensitive").count() == 3  # 동의 → 철회 → 재동의 이력


def test_legacy_user_needs_consent(client):
    with SessionLocal() as db:
        db.add(User(username="olduser", password_hash=hash_password("password123")))
        db.commit()
    r = client.post("/auth/login", json={"username": "olduser", "password": "password123"}).json()
    assert r["user"]["needs_consent"] == ["age14", "terms", "privacy", "sensitive"]
    h = {"Authorization": f"Bearer {r['token']}"}
    assert client.post("/memory", headers=h, json={"content": "x"}).status_code == 403
    client.put("/me/consents", headers=h, json={"consents": {k: True for k in ("age14", "terms", "privacy", "sensitive")}})
    assert client.get("/auth/me", headers=h).json()["needs_consent"] == []


def test_password_change_logs_out_other_sessions(client):
    h1 = signup(client, "pwuser")
    t2 = client.post("/auth/login", json={"username": "pwuser", "password": "password123"}).json()["token"]
    h2 = {"Authorization": f"Bearer {t2}"}
    assert client.post("/me/password", headers=h1, json={"current_password": "wrong", "new_password": "newpass123"}).status_code == 400
    assert client.post("/me/password", headers=h1, json={"current_password": "password123", "new_password": "newpass123"}).status_code == 200
    assert client.get("/auth/me", headers=h1).status_code == 200
    assert client.get("/auth/me", headers=h2).status_code == 401
    assert client.post("/auth/login", json={"username": "pwuser", "password": "newpass123"}).status_code == 200


def test_export_my_data(client):
    h = signup(client, "exp")
    client.post("/memory", headers=h, json={"content": "향료에 민감"})
    client.post("/scan/text", headers=h, json={"text": "정제수, 향료", "product_name": "테스트"})
    r = client.get("/me/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = json.loads(r.content)
    assert data["profile"]["username"] == "exp"
    assert data["skin_info"][0]["content"] == "향료에 민감"
    assert data["scans"][0]["product_name"] == "테스트"
    assert len(data["consent_history"]) == 5


def test_delete_account(client):
    h = signup(client, "bye")
    client.post("/memory", headers=h, json={"content": "건성"})
    client.post("/scan/text", headers=h, json={"text": "정제수, 글리세린, 향료", "product_name": "공유될 크림"})
    assert client.request("DELETE", "/me", headers=h, json={"password": "wrong"}).status_code == 400
    assert client.request("DELETE", "/me", headers=h, json={"password": "password123"}).json() == {"deleted": True}
    assert client.get("/auth/me", headers=h).status_code == 401
    with SessionLocal() as db:
        assert db.query(User).filter_by(username="bye").count() == 0
        assert db.query(Memory).count() == 0 and db.query(ScanResult).count() == 0 and db.query(Consent).count() == 0
        shared = db.query(ProductIngredientList).one()  # 개인정보가 아닌 제품 전성분은 남고 작성자만 지워짐
        assert shared.name == "공유될 크림" and shared.created_by is None
    # 같은 아이디로 다시 가입 가능
    assert client.post("/auth/signup", json=signup_body("bye")).status_code == 201
