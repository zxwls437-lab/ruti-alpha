"""오류 기록: 서버 500 오류와 사용자 화면의 자바스크립트 오류를 모아 관리자가 본다.

같은 (종류, 경로, 메시지)는 한 줄로 묶어 횟수만 늘린다. 화면 오류는 로그인 없이도 받지만 IP당 분당 20건까지만,
메시지는 500자로 자르고 숫자·이메일처럼 보이는 것은 지워서 개인정보가 남지 않게 한다.
"""
import logging
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, utcnow
from .models import ErrorLog, User
from .security import client_ip, limiter, require_admin

router = APIRouter(tags=["오류 기록"])
log = logging.getLogger("ruti")
_SCRUB = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"), (re.compile(r"\d{4,}"), "<n>"),
          (re.compile(r"Bearer\s+\S+", re.I), "Bearer <token>")]


def _clean(text: str, size: int) -> str:
    text = (text or "").strip()
    for pat, rep in _SCRUB:
        text = pat.sub(rep, text)
    return text[:size]


def record(kind: str, path: str, message: str) -> None:
    path, message = _clean(path.split("?")[0], 200), _clean(message, 500)
    try:
        with SessionLocal() as db:
            row = db.scalar(select(ErrorLog).where(ErrorLog.kind == kind, ErrorLog.path == path, ErrorLog.message == message))
            if row:
                row.count += 1
                row.last_at = utcnow()
            else:
                db.add(ErrorLog(kind=kind, path=path, message=message))
            db.commit()
    except Exception:  # noqa: BLE001  (오류 기록이 실패해도 서비스는 계속)
        log.exception("error log failed")


class ClientError(BaseModel):
    path: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=2000)


@router.post("/client-error", status_code=204)
def client_error(payload: ClientError, request: Request):
    ip = client_ip(request)
    if limiter.hit("client-error:" + ip, 20, 60):
        record("client", payload.path, payload.message)


@router.get("/admin/errors")
def list_errors(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ErrorLog).order_by(ErrorLog.last_at.desc()).limit(100)).all()
    return {"errors": [{"id": r.id, "kind": r.kind, "path": r.path, "message": r.message, "count": r.count,
                        "first_at": r.first_at.isoformat(), "last_at": r.last_at.isoformat()} for r in rows]}


@router.delete("/admin/errors")
def clear_errors(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    db.query(ErrorLog).delete()
    db.commit()
    return {"cleared": True}
