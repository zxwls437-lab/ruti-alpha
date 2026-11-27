"""보안 점검(모의 해킹)에서 찾은 문제가 다시 생기지 않는지 확인."""
from tests.conftest import make_admin, signup, signup_body


def login(client, username, password, ip):
    return client.post("/auth/login", json={"username": username, "password": password}, headers={"X-Client-IP-Test": ip})


def test_big_body_rejected_before_reading(client):
    r = client.post("/auth/login", content=b'{"username":"' + b"a" * 11_000_000 + b'","password":"x"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert client.get("/health").status_code == 200


def test_validation_error_does_not_echo_input(client):
    r = client.post("/auth/signup", json=signup_body(password="Zq9!x"))  # 8자 미만 → 422
    assert r.status_code == 422
    assert "Zq9!x" not in r.text and '"input"' not in r.text


def test_attacker_cannot_lock_victim_out(client, monkeypatch):
    monkeypatch.setenv("RUTI_CLIENT_IP_HEADER", "x-client-ip-test")
    signup(client, "victim1", "password123")
    for _ in range(12):
        login(client, "victim1", "wrong-password", "6.6.6.6")
    assert login(client, "victim1", "wrong-password", "6.6.6.6").status_code == 429  # 공격자는 막힘
    assert login(client, "victim1", "password123", "2.2.2.2").status_code == 200  # 본인은 다른 곳에서 로그인 가능


def test_password_spraying_from_one_ip_is_limited(client, monkeypatch):
    monkeypatch.setenv("RUTI_CLIENT_IP_HEADER", "x-client-ip-test")
    codes = [login(client, f"nouser{i}", "password123", "7.7.7.7").status_code for i in range(35)]
    assert codes[:30] == [401] * 30 and set(codes[30:]) == {429}
    assert login(client, "nouser99", "password123", "8.8.8.8").status_code == 401


def test_client_ip_header_setting(client, monkeypatch):
    admin = make_admin(client)
    user = signup(client, "plainuser")
    assert client.get("/admin/debug/client-ip", headers=user).status_code == 403
    monkeypatch.setenv("RUTI_CLIENT_IP_HEADER", "cf-connecting-ip")
    r = client.get("/admin/debug/client-ip", headers={**admin, "CF-Connecting-IP": "203.0.113.5", "X-Forwarded-For": "1.2.3.4"})
    assert r.json()["used_for_rate_limit"] == "203.0.113.5"
