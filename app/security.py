"""비밀번호 해시, 로그인 세션 토큰, 요청 제한."""
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import env, env_int
from .db import get_db, utcnow
from .models import AuthSession, User

# ---------- 비밀번호 ----------

def hash_password(password: str) -> str:
    iterations = env_int("RUTI_PBKDF2_ITERATIONS", 600_000)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# ---------- 세션 토큰 ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> str:
    """원본 토큰은 사용자에게 한 번만 돌려주고 DB에는 해시만 저장한다."""
    token = secrets.token_urlsafe(32)
    hours = env_int("RUTI_SESSION_HOURS", 24 * 7)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at < utcnow()))
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token), expires_at=utcnow() + timedelta(hours=hours)))
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    db.commit()


bearer = HTTPBearer(auto_error=False, description="POST /auth/login 으로 받은 토큰")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "로그인이 필요합니다.")
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(creds.credentials)))
    if row is None or row.expires_at < utcnow():
        raise HTTPException(401, "로그인이 만료되었거나 유효하지 않습니다.")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "사용자를 찾을 수 없습니다.")
    # 접속자 수 집계용: 1분에 한 번만 기록 (요청마다 쓰지 않게)
    now = utcnow()
    if user.last_seen_at is None or (now - user.last_seen_at).total_seconds() > 60:
        user.last_seen_at = now
        db.commit()
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return user


# ---------- 요청 제한 (단일 서버 프로세스용 메모리 방식) ----------

class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """허용되면 True. limit <= 0 이면 제한 없음."""
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 50_000:  # 키를 바꿔 가며 보내는 요청으로 메모리가 끝없이 늘지 않게, 빈 기록은 정리
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 86_400]:
                    del self._hits[k]
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


# ---------- 접속한 사람의 IP ----------

def client_ip(request: Request) -> str:
    """요청 제한에 쓰는 IP.

    기본은 uvicorn --proxy-headers가 정한 값(X-Forwarded-For의 맨 앞)인데, 이 값은 요청을 보내는 사람이 마음대로
    적을 수 있다. 배포 환경의 프록시가 덮어써서 위조할 수 없는 헤더(예: cf-connecting-ip, true-client-ip)가
    확인되면 RUTI_CLIENT_IP_HEADER에 그 이름을 넣는다. 확인은 관리자 GET /admin/debug/client-ip.
    """
    header = env("RUTI_CLIENT_IP_HEADER", "").strip().lower()
    if header:
        value = request.headers.get(header, "").split(",")[0].strip()
        if value:
            return value
    return request.client.host if request.client else "unknown"


# ---------- 요청 크기 제한 ----------

class BodySizeLimit:
    """너무 큰 요청 본문을 읽기 전에 413으로 거절한다 (큰 요청 몇 개로 서버 메모리를 다 쓰게 하는 공격 방지).
    사진 분석(base64 최대 9MB)이 들어가도록 기본 10MB."""

    def __init__(self, app, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes or env_int("RUTI_MAX_BODY_BYTES", 10_000_000)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.max_bytes
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            body = '{"detail":"요청이 너무 커요. 사진은 더 작게 줄여서 보내 주세요."}'.encode()
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                    (b"connection", b"close")]})
            await send({"type": "http.response.body", "body": body})
            return
        received = 0

        async def limited_receive():  # content-length 없이 나눠 보내는 요청도 받은 만큼 세어서 막는다
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "요청이 너무 커요. 사진은 더 작게 줄여서 보내 주세요.")
            return message

        await self.app(scope, limited_receive, send)
