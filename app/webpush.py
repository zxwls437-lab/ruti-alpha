"""웹 알림(Web Push) 보내기: VAPID 서명(RFC 8292) + 메시지 암호화(RFC 8291, aes128gcm).

외부 라이브러리 없이 cryptography만 쓴다. 키는 환경 변수:
  RUTI_VAPID_PRIVATE  — P-256 개인키 (base64url, 32바이트 원시값)
  RUTI_VAPID_PUBLIC   — 공개키 (base64url, 65바이트 비압축 점)
  RUTI_VAPID_SUBJECT  — 연락처 (mailto:...). 없으면 mailto:admin@ruti.app
"""
import base64
import json
import os
import struct
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def generate_keys() -> tuple[str, str]:
    """(개인키, 공개키) base64url — 처음 한 번 만들어 환경 변수에 넣는다."""
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64u(priv), b64u(pub)


def public_key() -> str:
    return os.getenv("RUTI_VAPID_PUBLIC", "").strip()


def configured() -> bool:
    return bool(public_key() and os.getenv("RUTI_VAPID_PRIVATE", "").strip())


def _private_key() -> ec.EllipticCurvePrivateKey:
    raw = int.from_bytes(unb64u(os.environ["RUTI_VAPID_PRIVATE"].strip()), "big")
    return ec.derive_private_key(raw, ec.SECP256R1())


def _vapid_header(endpoint: str) -> str:
    url = urlparse(endpoint)
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64u(json.dumps({"aud": f"{url.scheme}://{url.netloc}", "exp": int(time.time()) + 12 * 3600,
                              "sub": os.getenv("RUTI_VAPID_SUBJECT", "mailto:admin@ruti.app")}).encode())
    der = _private_key().sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    token = f"{header}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={public_key()}"


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """RFC 8291 aes128gcm 본문 (헤더 + 암호문 한 덩어리)."""
    ua_public = unb64u(p256dh)
    auth_secret = unb64u(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    as_key = ec.generate_private_key(ec.SECP256R1())
    as_public = as_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = as_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    record = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # \x02 = 마지막 레코드 구분자
    return salt + struct.pack("!IB", 4096, len(as_public)) + as_public + record


def send(sub: dict, message: dict, ttl: int = 3600) -> int:
    """알림 하나 보내기. HTTP 상태 코드를 돌려준다 (404·410이면 구독이 사라진 것)."""
    body = encrypt(json.dumps(message, ensure_ascii=False).encode(), sub["p256dh"], sub["auth"])
    headers = {"Authorization": _vapid_header(sub["endpoint"]), "Content-Encoding": "aes128gcm",
               "Content-Type": "application/octet-stream", "TTL": str(ttl), "Urgency": "normal"}
    r = httpx.post(sub["endpoint"], content=body, headers=headers, timeout=15)
    return r.status_code
