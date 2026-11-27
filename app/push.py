"""루틴 웹 알림: 구독 저장 + 시간이 되면 보내기.

무료 서버는 잠들 수 있어서, 바깥(GitHub Actions 10분마다)에서 /push/tick 을 불러 깨우고 보낼 것을 보낸다.
tick은 누가 불러도 '보낼 시간이 지났고 오늘 아직 안 보낸 것'만 보내므로 여러 번 불려도 중복이 없다.
"""
import logging
import re
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import webpush
from .db import SessionLocal, get_db
from .models import PushSubscription, User
from .plans import KST
from .security import current_user, limiter

router = APIRouter(prefix="/push", tags=["웹 알림"])
log = logging.getLogger("ruti")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
WINDOW = timedelta(minutes=40)  # 정한 시각부터 40분 안에만 보낸다 (서버가 늦게 깨도 너무 늦은 알림은 안 보냄)
TEXT = {"am": {"title": "☀️ 아침 루틴 시간이에요", "body": "세안 → 보습 → 선크림까지, 오늘도 가볍게 체크해 볼까요?"},
        "pm": {"title": "🌙 저녁 루틴 시간이에요", "body": "하루 동안 고생한 피부, 오늘 루틴 체크하고 쉬어요."}}
_tick_lock = threading.Lock()


@router.get("/key")
def vapid_key():
    return {"key": webpush.public_key(), "enabled": webpush.configured()}


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class SubscribeIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: Keys
    am: str | None = None
    pm: str | None = None


@router.post("/subscribe")
def subscribe(payload: SubscribeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not webpush.configured():
        raise HTTPException(503, "알림 기능이 아직 준비되지 않았어요.")
    if not payload.endpoint.startswith("https://"):
        raise HTTPException(422, "알림 주소가 올바르지 않아요.")
    for v in (payload.am, payload.pm):
        if v and not TIME.match(v):
            raise HTTPException(422, "시간을 다시 골라 주세요.")
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if row is None:
        row = PushSubscription(endpoint=payload.endpoint, user_id=user.id, p256dh=payload.keys.p256dh, auth=payload.keys.auth)
        db.add(row)
    row.user_id, row.p256dh, row.auth = user.id, payload.keys.p256dh, payload.keys.auth
    row.am, row.pm = payload.am or "", payload.pm or ""
    # 지금 바꾼 시각이 이미 지났으면 오늘은 보내지 않는다 (설정하자마자 알림이 오는 것 방지)
    now = datetime.now(KST)
    for slot in ("am", "pm"):
        t = getattr(row, slot)
        if t and now.strftime("%H:%M") >= t:
            setattr(row, "last_" + slot, now.strftime("%Y-%m-%d"))
    db.commit()
    return {"ok": True, "am": row.am, "pm": row.pm}


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(PushSubscription).where(PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id))
    db.commit()
    return {"ok": True}


def due(row: PushSubscription, slot: str, now: datetime) -> bool:
    t = getattr(row, slot)
    if not t or getattr(row, "last_" + slot) == now.strftime("%Y-%m-%d"):
        return False
    h, m = map(int, t.split(":"))
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return at <= now < at + WINDOW


def run_tick(now: datetime | None = None, sender=None) -> dict:
    now = now or datetime.now(KST)
    sender = sender or webpush.send
    sent = gone = failed = 0
    with SessionLocal() as db:
        for row in db.scalars(select(PushSubscription).where((PushSubscription.am != "") | (PushSubscription.pm != ""))).all():
            for slot in ("am", "pm"):
                if not due(row, slot, now):
                    continue
                setattr(row, "last_" + slot, now.strftime("%Y-%m-%d"))  # 실패해도 오늘 다시 시도하지 않음 (폭주 방지)
                try:
                    code = sender({"endpoint": row.endpoint, "p256dh": row.p256dh, "auth": row.auth},
                                  {**TEXT[slot], "url": "/routine"})
                except Exception:  # noqa: BLE001
                    log.exception("push send failed")
                    failed += 1
                    continue
                if code in (404, 410):  # 사용자가 알림을 끄거나 앱을 지움
                    db.delete(row)
                    gone += 1
                    break
                if code >= 400:
                    failed += 1
                else:
                    sent += 1
        db.commit()
    return {"sent": sent, "gone": gone, "failed": failed}


@router.post("/tick")
@router.get("/tick")
def tick():
    """10분마다 바깥에서 부른다 (서버 깨우기 겸). 한 번에 하나만 돌고, 1분에 6번까지만."""
    if not webpush.configured():
        return {"enabled": False}
    if not limiter.hit("push-tick", 6, 60) or not _tick_lock.acquire(blocking=False):
        return {"skipped": True}
    try:
        return run_tick()
    finally:
        _tick_lock.release()
