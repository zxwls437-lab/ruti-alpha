"""요금제(무료 / RUTI Plus)와 하루 이용 한도.

한도는 DB 기록(오늘 보낸 상담 질문 수, 오늘 사진 분석 수)으로 세서 서버를 재시작해도 유지된다.
값이 0이면 제한 없음. 출시 전 기본값은 모두 0(테스트 편의), 출시할 때 .env로 켠다.
결제(App Store / Google Play 영수증 검증)는 아직 없고, 관리자가 Plus를 지급할 수 있다.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import env_int
from .db import get_db, utcnow
from .models import ChatMessage, ScanResult, User
from .security import require_admin

router = APIRouter(tags=["요금제"])
KST = timezone(timedelta(hours=9))


def is_plus(user: User) -> bool:
    return user.plan == "plus" and (user.plus_until is None or user.plus_until > utcnow())


def today_start_utc() -> datetime:
    """한국 시간 자정을 UTC(타임존 없는 값)로."""
    now_kst = datetime.now(KST)
    start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def limits(user: User) -> dict:
    if user.is_admin:
        return {"chat": 0, "scan": 0}
    if is_plus(user):
        return {"chat": env_int("RUTI_PLUS_CHAT_PER_DAY", 0), "scan": env_int("RUTI_PLUS_SCAN_PER_DAY", 0)}
    return {"chat": env_int("RUTI_FREE_CHAT_PER_DAY", 0), "scan": env_int("RUTI_FREE_SCAN_PER_DAY", 0)}


def usage_today(db: Session, user: User) -> dict:
    since = today_start_utc()
    chat = db.scalar(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.user_id == user.id, ChatMessage.role == "user", ChatMessage.created_at >= since)) or 0
    scan = db.scalar(select(func.count()).select_from(ScanResult).where(
        ScanResult.user_id == user.id, ScanResult.source == "image", ScanResult.created_at >= since)) or 0
    return {"chat": chat, "scan": scan}


def plan_info(db: Session, user: User) -> dict:
    lim, used = limits(user), usage_today(db, user)
    return {"plan": "plus" if is_plus(user) else "free", "plus_until": user.plus_until.isoformat() if user.plus_until and is_plus(user) else None,
            "today": {"chat_used": used["chat"], "chat_limit": lim["chat"], "scan_used": used["scan"], "scan_limit": lim["scan"]}}


def check_quota(db: Session, user: User, kind: str) -> None:
    """kind: chat | scan. 한도를 넘었으면 429."""
    limit = limits(user)[kind]
    if limit <= 0:
        return
    if usage_today(db, user)[kind] >= limit:
        label = {"chat": "상담", "scan": "사진 분석"}[kind]
        if is_plus(user):
            raise HTTPException(429, f"오늘 {label} 이용량을 모두 썼어요. 내일 다시 이용해 주세요.")
        raise HTTPException(429, f"오늘 무료 {label} {limit}회를 모두 썼어요. 내일 다시 이용하거나 RUTI Plus로 더 많이 이용할 수 있어요."
                                 + (" 성분표 글자 붙여넣기는 계속 쓸 수 있어요." if kind == "scan" else ""))


class GrantIn(BaseModel):
    plan: str = Field(pattern="^(free|plus)$")
    days: int = Field(default=30, ge=0, le=3660, description="plus 기간(일). 0이면 기한 없음")


@router.post("/admin/users/{username}/plan", tags=["관리자"])
def admin_set_plan(username: str, payload: GrantIn, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username.lower()))
    if not user:
        raise HTTPException(404, "회원을 찾을 수 없어요.")
    user.plan = payload.plan
    user.plus_until = (utcnow() + timedelta(days=payload.days)) if payload.plan == "plus" and payload.days else None
    db.commit()
    return {"username": user.username, **plan_info(db, user)}
