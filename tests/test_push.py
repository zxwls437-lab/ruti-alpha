from datetime import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app import push, webpush
from app.plans import KST
from tests.conftest import signup


def _hkdf(salt, ikm, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def test_encrypt_roundtrip():
    """브라우저(받는 쪽) 입장에서 RFC 8291대로 풀어 원문이 나오는지."""
    ua = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    body = webpush.encrypt(b'{"title":"hi"}', webpush.b64u(ua_pub), webpush.b64u(auth))
    salt, idlen = body[:16], body[20]
    as_pub = body[21:21 + idlen]
    shared = ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
    assert plain == b'{"title":"hi"}\x02'


def test_vapid_header(monkeypatch):
    priv, pub = webpush.generate_keys()
    monkeypatch.setenv("RUTI_VAPID_PRIVATE", priv)
    monkeypatch.setenv("RUTI_VAPID_PUBLIC", pub)
    h = webpush._vapid_header("https://fcm.googleapis.com/fcm/send/abc")
    assert h.startswith("vapid t=") and h.endswith("k=" + pub) and h.count(".") == 2


def test_subscribe_and_tick(client, monkeypatch):
    priv, pub = webpush.generate_keys()
    monkeypatch.setenv("RUTI_VAPID_PRIVATE", priv)
    monkeypatch.setenv("RUTI_VAPID_PUBLIC", pub)
    headers = signup(client, "pushuser1")
    assert client.get("/push/key").json() == {"key": pub, "enabled": True}
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}, "am": "08:00", "pm": "22:00"}
    assert client.post("/push/subscribe", json={**sub, "am": "8시"}, headers=headers).status_code == 422
    assert client.post("/push/subscribe", json=sub, headers=headers).status_code == 200
    # 설정한 시각이 이미 지났으면 오늘은 보내지 않게 표시돼 있을 수 있어 초기화
    from app.db import SessionLocal
    from app.models import PushSubscription
    with SessionLocal() as db:
        row = db.query(PushSubscription).one(); row.last_am = row.last_pm = ""; db.commit()
    sent = []
    at = lambda h, m: datetime(2026, 11, 27, h, m, tzinfo=KST)  # noqa: E731
    assert push.run_tick(at(7, 59), lambda s, m: sent.append(m) or 201) == {"sent": 0, "gone": 0, "failed": 0}
    assert push.run_tick(at(8, 5), lambda s, m: sent.append(m) or 201)["sent"] == 1
    assert push.run_tick(at(8, 15), lambda s, m: sent.append(m) or 201)["sent"] == 0  # 하루 한 번
    assert sent[0]["url"] == "/routine" and "아침" in sent[0]["title"]
    assert push.run_tick(at(23, 30), lambda s, m: 201)["sent"] == 0  # 40분 지나면 안 보냄
    # 알림을 끈 기기(410)는 지운다
    with SessionLocal() as db:
        row = db.query(PushSubscription).one(); row.last_am = ""; db.commit()
    assert push.run_tick(at(8, 1), lambda s, m: 410)["gone"] == 1
    with SessionLocal() as db:
        assert db.query(PushSubscription).count() == 0
