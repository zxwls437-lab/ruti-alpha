"""비밀번호 해시, 로그인 세션 토큰, 요청 제한."""
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import env_int
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
