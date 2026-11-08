"""관리자: 회원 목록(아이디 A→Z)과 접속자 수.

접속자 수는 로그인한 사용자가 마지막으로 RUTI를 쓴 시각(users.last_seen_at, 1분 단위)으로 센다.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db, utcnow
from .models import ScanResult, User
from .plans import is_plus, today_start_utc
from .security import require_admin

router = APIRouter(prefix="/admin", tags=["관리자 회원"])
ONLINE_MINUTES = 5


@router.get("/stats/visitors")
def visitors(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    now, today_start = utcnow(), today_start_utc()
    count = lambda *where: db.scalar(select(func.count()).select_from(User).where(*where)) or 0  # noqa: E731
    return {
        "online_now": count(User.last_seen_at >= now - timedelta(minutes=ONLINE_MINUTES)),
        "today": count(User.last_seen_at >= today_start),
        "week": count(User.last_seen_at >= now - timedelta(days=7)),
        "total_users": count(),
        "new_today": count(User.created_at >= today_start),
        "online_minutes": ONLINE_MINUTES,
    }


@router.get("/users")
def list_users(q: str = "", limit: int = 200, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(func.lower(User.username)).limit(max(1, min(limit, 500)))
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.nickname.ilike(like), User.name.ilike(like)))
    users = db.scalars(stmt).all()
    scans = dict(db.execute(select(ScanResult.user_id, func.count()).where(ScanResult.user_id.in_([u.id for u in users]))
                            .group_by(ScanResult.user_id)).all()) if users else {}
    online_since = utcnow() - timedelta(minutes=ONLINE_MINUTES)
    return {"users": [{
        "username": u.username, "name": u.name, "nickname": u.nickname, "is_admin": u.is_admin,
        "plan": "plus" if is_plus(u) else "free", "created_at": u.created_at.isoformat(),
        "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
        "online": bool(u.last_seen_at and u.last_seen_at >= online_since), "scans": scans.get(u.id, 0),
    } for u in users]}
