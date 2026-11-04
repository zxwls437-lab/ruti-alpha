"""회원 정보: 이름·닉네임, 동의 기록, 비밀번호 변경, 내 데이터 내려받기, 회원 탈퇴."""
import json
import random
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .config import env
from .db import get_db, utcnow
from .models import (AuthSession, ChatMessage, Comment, Consent, Memory, Post, Product, ProductIngredientList, Review,
                     ReviewVote, ScanResult, User, VanityItem)
from .plans import plan_info
from .security import _token_hash, bearer, current_user, hash_password, verify_password

router = APIRouter(prefix="/me", tags=["회원 정보"])

# 동의 항목: (설명, 필수 여부)
CONSENT_KINDS = {
    "age14": ("만 14세 이상", True),
    "terms": ("이용약관", True),
    "privacy": ("개인정보 수집·이용", True),
    "sensitive": ("피부 상태 등 민감정보 처리", True),
    "marketing": ("새 기능·혜택 알림 (마케팅)", False),
}
REQUIRED = [k for k, (_, req) in CONSENT_KINDS.items() if req]
NICKNAME_RE = re.compile(r"^[0-9A-Za-z가-힣_]{2,20}$")
_ADJ = ["촉촉한", "보송한", "말랑한", "산뜻한", "포근한", "맑은", "부드러운", "향긋한", "싱그러운", "차분한"]
_NOUN = ["토너", "크림", "세럼", "미스트", "로션", "앰플", "밤", "젤", "에센스", "클렌저"]


def terms_version() -> str:
    return env("RUTI_TERMS_VERSION", "2026-11-04")


# ---------- 닉네임 ----------

def check_nickname(v: str) -> str:
    v = v.strip()
    if not NICKNAME_RE.match(v):
        raise ValueError("닉네임은 한글·영문·숫자·밑줄 2~20자여야 해요.")
    return v


def nickname_taken(db: Session, nickname: str, except_user: int | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.nickname) == nickname.lower())
    if except_user:
        stmt = stmt.where(User.id != except_user)
    return db.scalar(stmt) is not None


def generate_nickname(db: Session) -> str:
    for _ in range(50):
        nick = f"{random.choice(_ADJ)}{random.choice(_NOUN)}{random.randint(10, 9999)}"
        if not nickname_taken(db, nick):
            return nick
    return f"루티{random.randint(100000, 999999)}"


# ---------- 동의 ----------

def current_consents(db: Session, user: User) -> dict[str, bool]:
    state = {k: False for k in CONSENT_KINDS}
    for row in db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.id)):
        if row.kind in state:
            state[row.kind] = row.agreed
    return state


def missing_required(db: Session, user: User) -> list[str]:
    state = current_consents(db, user)
    return [k for k in REQUIRED if not state[k]]


def has_sensitive_consent(db: Session, user: User) -> bool:
    return current_consents(db, user)["sensitive"]


def record_consents(db: Session, user: User, changes: dict[str, bool]) -> None:
    version = terms_version()
    for kind, agreed in changes.items():
        db.add(Consent(user_id=user.id, kind=kind, agreed=bool(agreed), version=version))


def validate_signup_consents(consents: dict[str, bool]) -> None:
    unknown = set(consents) - set(CONSENT_KINDS)
    if unknown:
        raise HTTPException(422, f"알 수 없는 동의 항목: {', '.join(sorted(unknown))}")
    missing = [CONSENT_KINDS[k][0] for k in REQUIRED if not consents.get(k)]
    if missing:
        raise HTTPException(422, "필수 항목에 동의해 주세요: " + ", ".join(missing))


def user_public(db: Session, user: User) -> dict:
    return {"username": user.username, "name": user.name, "nickname": user.nickname, "is_admin": user.is_admin,
            "needs_consent": missing_required(db, user)}


# ---------- API ----------

@router.get("")
def my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))
    return {
        **user_public(db, user),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "consents": current_consents(db, user),
        "consent_items": [{"kind": k, "label": label, "required": req} for k, (label, req) in CONSENT_KINDS.items()],
        "terms_version": terms_version(),
        "counts": {"skin_info": count(Memory), "scans": count(ScanResult), "chat_messages": count(ChatMessage)},
        **plan_info(db, user),
    }


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    nickname: str | None = None

    @field_validator("name")
    @classmethod
    def v_name(cls, v):
        return v.strip() if v is not None else v

    @field_validator("nickname")
    @classmethod
    def v_nick(cls, v):
        return check_nickname(v) if v is not None else v


@router.patch("")
def update_profile(payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.nickname is not None:
        if nickname_taken(db, payload.nickname, except_user=user.id):
            raise HTTPException(409, "이미 사용 중인 닉네임이에요.")
        user.nickname = payload.nickname
    if payload.name is not None:
        if not payload.name:
            raise HTTPException(422, "이름을 입력해 주세요.")
        user.name = payload.name
    db.commit()
    return user_public(db, user)


@router.get("/consents")
def get_consents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"consents": current_consents(db, user), "needs_consent": missing_required(db, user), "terms_version": terms_version()}


class ConsentUpdate(BaseModel):
    consents: dict[str, bool]


@router.put("/consents")
def update_consents(payload: ConsentUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """동의하기/철회하기. 이용약관·개인정보·나이 동의는 철회할 수 없음(탈퇴 이용).
    민감정보 동의를 철회하면 저장된 피부 정보를 바로 삭제한다."""
    unknown = set(payload.consents) - set(CONSENT_KINDS)
    if unknown:
        raise HTTPException(422, f"알 수 없는 동의 항목: {', '.join(sorted(unknown))}")
    for kind, agreed in payload.consents.items():
        if not agreed and kind in ("age14", "terms", "privacy"):
            raise HTTPException(400, f"'{CONSENT_KINDS[kind][0]}' 동의는 철회할 수 없어요. 서비스를 그만 쓰시려면 회원 탈퇴를 이용해 주세요.")
    before = current_consents(db, user)
    changes = {k: v for k, v in payload.consents.items() if before[k] != v}
    record_consents(db, user, changes)
    deleted = 0
    if changes.get("sensitive") is False:
        deleted = db.execute(delete(Memory).where(Memory.user_id == user.id)).rowcount or 0
    db.commit()
    return {"consents": current_consents(db, user), "needs_consent": missing_required(db, user), "deleted_skin_info": deleted}


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
def change_password(payload: PasswordChange, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "현재 비밀번호가 올바르지 않아요.")
    user.password_hash = hash_password(payload.new_password)
    # 다른 기기의 로그인은 모두 끊고, 지금 쓰는 로그인만 유지
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != _token_hash(creds.credentials)))
    db.commit()
    return {"changed": True}


@router.get("/export")
def export_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """내 데이터 전체 내려받기 (개인정보 열람권)."""
    rows = lambda model, order: db.scalars(select(model).where(model.user_id == user.id).order_by(order)).all()
    data = {
        "exported_at": utcnow().isoformat(),
        "profile": {"username": user.username, "name": user.name, "nickname": user.nickname,
                    "created_at": user.created_at.isoformat() if user.created_at else None},
        "consent_history": [{"kind": c.kind, "agreed": c.agreed, "version": c.version, "at": c.created_at.isoformat()}
                            for c in rows(Consent, Consent.id)],
        "skin_info": [{"content": m.content, "at": m.created_at.isoformat()} for m in rows(Memory, Memory.id)],
        "chat_messages": [{"role": m.role, "content": m.content, "at": m.created_at.isoformat()} for m in rows(ChatMessage, ChatMessage.id)],
        "posts": [{"kind": p.kind, "title": p.title, "body": p.body, "at": p.created_at.isoformat()} for p in rows(Post, Post.id)],
        "comments": [{"post_id": c.post_id, "body": c.body, "at": c.created_at.isoformat()} for c in rows(Comment, Comment.id)],
        "vanity": [{"product_name": v.product_name, "ingredients": json.loads(v.ingredients), "at": v.created_at.isoformat()}
                   for v in rows(VanityItem, VanityItem.id)],
        "reviews": [{"product_name": r.product_name, "brand": r.brand, "rating": r.rating, "text": r.text, "at": r.created_at.isoformat()}
                    for r in rows(Review, Review.id)],
        "scans": [{"product_name": s.product_name, "source": s.source, "result": json.loads(s.result), "at": s.created_at.isoformat()}
                  for s in rows(ScanResult, ScanResult.id)],
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="ruti-my-data-{user.username}.json"'})


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@router.delete("")
def delete_account(payload: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """회원 탈퇴: 계정과 개인 데이터를 모두 삭제. 공유된 제품 전성분 등 개인정보가 아닌 기여는 작성자 정보만 지운다."""
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(400, "비밀번호가 올바르지 않아요.")
    uid = user.id
    from .community import delete_user_content  # 순환 import 방지
    delete_user_content(db, uid)
    my_reviews = list(db.scalars(select(Review.id).where(Review.user_id == uid)))
    if my_reviews:
        db.execute(delete(ReviewVote).where(ReviewVote.review_id.in_(my_reviews)))
    for model in (AuthSession, Memory, ChatMessage, ScanResult, Consent, ReviewVote, Review, VanityItem):
        db.execute(delete(model).where(model.user_id == uid))
    db.execute(update(Product).where(Product.submitted_by == uid).values(submitted_by=None))
    db.execute(update(Product).where(Product.reviewed_by == uid).values(reviewed_by=None))
    db.execute(update(ProductIngredientList).where(ProductIngredientList.created_by == uid).values(created_by=None))
    db.delete(user)
    db.commit()
    return {"deleted": True}
