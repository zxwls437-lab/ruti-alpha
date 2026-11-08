"""사용 후기: 인증 후기, 협찬 표시, 의약품 표현 감지, 나와 비슷한 피부 통계, 도움돼요·신고, 관리자 검토."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from . import account
from .config import env_int
from .db import get_db, utcnow
from .models import Memory, Review, ReviewVote, ScanResult, User
from .scan import name_key
from .security import current_user, limiter, require_admin

router = APIRouter(tags=["후기"])

MIN_SAMPLE = 5          # 이보다 적으면 비율을 보여주지 않음
AUTO_HIDE_REPORTS = 3   # 신고가 이만큼 쌓이면 자동 숨김

# 화장품 후기에 쓰면 안 되는 의약품식 표현 (통계·AI 요약에서 제외)
MEDICAL_PATTERNS = [
    r"치료", r"완치", r"나았", r"낫더", r"나아졌", r"재생", r"처방", r"약\s*대신",
    r"(여드름|아토피|습진|피부염|기미|흉터|모공)[이가은는]?\s*(싹\s*)?(사라|없어|없애)",
]
_MEDICAL = re.compile("|".join(MEDICAL_PATTERNS))

SKIN_KEYWORDS = [  # (태그, 피부 정보 문장에서 찾을 단어)
    ("건성", ("건성",)), ("지성", ("지성",)), ("복합성", ("복합성",)), ("중성", ("중성",)),
    ("민감성", ("민감",)), ("향료 민감", ("향료",)), ("트러블", ("여드름", "트러블")), ("임신·수유", ("임신", "수유")),
]
SKIN_TYPES = {"건성", "지성", "복합성", "중성"}


def has_medical_claim(text: str) -> bool:
    return bool(_MEDICAL.search(text))


def skin_tags_from(memories: list[str]) -> list[str]:
    text = " ".join(memories)
    return [tag for tag, words in SKIN_KEYWORDS if any(w in text for w in words)]


def is_similar(mine: set[str], theirs: set[str]) -> bool:
    """피부 타입이 같고, 내가 민감성이면 상대도 민감성일 때 '비슷한 피부'."""
    if not mine or not theirs:
        return False
    my_type, their_type = mine & SKIN_TYPES, theirs & SKIN_TYPES
    if my_type and my_type != their_type:
        return False
    if "민감성" in mine and "민감성" not in theirs:
        return False
    return bool(my_type) or bool(mine & theirs)


def product_filter(brand: str, product: str):
    full, only = name_key(brand, product), name_key("", product)
    conds = [Review.name_key == full]
    if len(only) >= 4:
        conds.append(Review.name_key.contains(only))
    return or_(*conds)


def _my_tags(db: Session, user: User) -> list[str]:
    if not account.has_sensitive_consent(db, user):
        return []
    return skin_tags_from(list(db.scalars(select(Memory.content).where(Memory.user_id == user.id))))


def _verified(db: Session, user: User, key: str) -> bool:
    """이 사용자가 같은 제품을 사진으로 분석한 기록이 있으면 인증."""
    for name in db.scalars(select(ScanResult.product_name).where(ScanResult.user_id == user.id, ScanResult.source == "image")):
        k = name_key("", name)
        if len(k) >= 2 and (k == key or (len(k) >= 4 and (k in key or key in k))):
            return True
    return False


def _counts_for_stats(r: Review) -> bool:
    return r.verified and not r.sponsored and not r.medical_claim and not r.hidden


def _public(r: Review, author: User | None, viewer: User, helpful_by_me: set[int]) -> dict:
    return {
        "id": r.id, "brand": r.brand, "product_name": r.product_name, "rating": r.rating, "text": r.text,
        "felt": {"moisture": r.felt_moisture, "irritation": r.felt_irritation, "rebuy": r.would_rebuy},
        "author": author.nickname if author and author.nickname else "탈퇴한 사용자",
        "skin_tags": [t for t in r.skin_tags.split(",") if t] if r.show_skin else [],
        "verified": r.verified, "sponsored": r.sponsored, "excluded_from_stats": not _counts_for_stats(r),
        "helpful_count": r.helpful_count, "helpful_by_me": r.id in helpful_by_me, "mine": r.user_id == viewer.id,
        "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
    }


# ---------- 작성·수정 ----------

class ReviewIn(BaseModel):
    brand: str = Field(default="", max_length=150)
    product_name: str = Field(min_length=1, max_length=200)
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=10, max_length=1000)
    felt_moisture: bool = False
    felt_irritation: bool = False
    would_rebuy: bool = False
    sponsored: bool = False
    show_skin: bool = True

    @field_validator("text", "product_name", "brand")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


@router.post("/reviews", status_code=201)
def write_review(payload: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    key = name_key(payload.brand, payload.product_name)
    if len(key) < 2:
        raise HTTPException(422, "제품 이름을 확인해 주세요.")
    if len(payload.text) < 10:
        raise HTTPException(422, "후기는 10자 이상 적어 주세요.")
    if not limiter.hit(f"review:{user.id}", env_int("RUTI_REVIEWS_PER_DAY", 10), 86400):
        raise HTTPException(429, "오늘 작성할 수 있는 후기 수를 넘었어요. 내일 다시 써 주세요.")
    review = db.scalar(select(Review).where(Review.user_id == user.id, Review.name_key == key))
    created = review is None
    if created:
        review = Review(user_id=user.id, name_key=key)
        db.add(review)
    review.brand, review.product_name, review.rating, review.text = payload.brand, payload.product_name, payload.rating, payload.text
    review.felt_moisture, review.felt_irritation, review.would_rebuy = payload.felt_moisture, payload.felt_irritation, payload.would_rebuy
    review.sponsored, review.show_skin = payload.sponsored, payload.show_skin
    review.medical_claim = has_medical_claim(payload.text)
    review.verified = _verified(db, user, key)
    review.skin_tags = ",".join(_my_tags(db, user))
    review.updated_at = utcnow()
    db.commit()

    notices = []
    if review.medical_claim:
        notices.append("'치료·완치·나았다' 같은 의약품 표현이 있어 이 후기는 통계와 AI 요약에서 제외돼요. 화장품 후기는 '보습에 도움이 됐어요'처럼 써 주세요.")
    if not review.verified:
        notices.append("이 제품을 RUTI로 사진 분석하면 '인증 후기'가 되어 비슷한 피부 통계에 반영돼요.")
    if review.sponsored:
        notices.append("협찬·체험단 후기는 '광고 포함'으로 표시되고 통계에서 제외돼요.")
    return {"created": created, "review": _public(review, user, user, set()), "notices": notices}


# ---------- AI에 넘길 후기 통계 ----------

def reviews_in_text(db: Session, user: User, text: str, limit: int = 2) -> list[dict]:
    """질문(또는 분석한 제품명)에 등장하는 제품의 후기 통계. 집계 가능한(표본 충분) 것만 돌려준다."""
    key = name_key("", text)
    if len(key) < 6:
        return []
    found, seen = [], set()
    for brand, product in db.execute(select(Review.brand, Review.product_name).where(Review.hidden.is_(False)).distinct()):
        only = name_key("", product)
        if len(only) < 6 or only in seen or only not in key:
            continue
        seen.add(only)
        s = summary_data(db, user, brand, product)
        if s["overall"]["enough"]:
            found.append({"product": f"{brand} {product}".strip(), "overall": s["overall"],
                          "similar_skin": {k: v for k, v in s["similar"].items() if k != "my_skin_tags"}})
        if len(found) >= limit:
            break
    return found


# ---------- 조회 ----------

@router.get("/reviews")
def list_reviews(product: str, brand: str = "", similar: bool = False, sort: str = "helpful", limit: int = 20, offset: int = 0,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    if sort not in ("helpful", "recent"):
        raise HTTPException(400, "sort는 helpful 또는 recent예요.")
    stmt = select(Review).where(product_filter(brand, product), Review.hidden.is_(False))
    stmt = stmt.order_by(Review.helpful_count.desc(), Review.id.desc()) if sort == "helpful" else stmt.order_by(Review.id.desc())
    rows = db.scalars(stmt).all()
    from .blocks import blocked_ids  # 순환 import 방지
    hidden_authors = blocked_ids(db, user)
    rows = [r for r in rows if r.user_id not in hidden_authors]
    if similar:
        mine = set(_my_tags(db, user))
        rows = [r for r in rows if is_similar(mine, set(r.skin_tags.split(",")) - {""})]
    total = len(rows)
    rows = rows[max(offset, 0): max(offset, 0) + max(1, min(limit, 50))]
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows})))} if rows else {}
    mine_helpful = set(db.scalars(select(ReviewVote.review_id).where(ReviewVote.user_id == user.id, ReviewVote.kind == "helpful")))
    return {"total": total, "reviews": [_public(r, authors.get(r.user_id), user, mine_helpful) for r in rows]}


def _stats(rows: list[Review]) -> dict:
    n = len(rows)
    if n < MIN_SAMPLE:
        return {"n": n, "enough": False}
    pct = lambda attr: round(100 * sum(1 for r in rows if getattr(r, attr)) / n)
    return {"n": n, "enough": True, "avg_rating": round(sum(r.rating for r in rows) / n, 1),
            "moisture_pct": pct("felt_moisture"), "irritation_pct": pct("felt_irritation"), "rebuy_pct": pct("would_rebuy")}


@router.get("/reviews/summary")
def review_summary(product: str, brand: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """인증·비협찬·의약품 표현 없는 후기만 집계. 표본이 5개 미만이면 비율을 숨긴다."""
    return summary_data(db, user, brand, product)


def summary_data(db: Session, user: User, brand: str, product: str) -> dict:
    rows = db.scalars(select(Review).where(product_filter(brand, product), Review.hidden.is_(False))).all()
    counted = [r for r in rows if _counts_for_stats(r)]
    mine = set(_my_tags(db, user))
    similar = [r for r in counted if is_similar(mine, set(r.skin_tags.split(",")) - {""})]
    return {"total_reviews": len(rows), "counted_reviews": len(counted), "min_sample": MIN_SAMPLE,
            "overall": _stats(counted), "similar": {**_stats(similar), "my_skin_tags": sorted(mine)}}


@router.get("/reviews/mine")
def my_reviews(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Review).where(Review.user_id == user.id).order_by(Review.id.desc())).all()
    return {"reviews": [{**_public(r, user, user, set()), "hidden": r.hidden} for r in rows]}


@router.delete("/reviews/{review_id}")
def delete_my_review(review_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "후기를 찾을 수 없어요.")
    db.execute(delete(ReviewVote).where(ReviewVote.review_id == r.id))
    db.delete(r)
    db.commit()
    return {"deleted": True}


# ---------- 도움돼요·신고 ----------

def _visible(db: Session, review_id: int) -> Review:
    r = db.get(Review, review_id)
    if not r or r.hidden:
        raise HTTPException(404, "후기를 찾을 수 없어요.")
    return r


@router.post("/reviews/{review_id}/helpful")
def toggle_helpful(review_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _visible(db, review_id)
    if r.user_id == user.id:
        raise HTTPException(400, "내 후기에는 누를 수 없어요.")
    vote = db.scalar(select(ReviewVote).where(ReviewVote.user_id == user.id, ReviewVote.review_id == r.id, ReviewVote.kind == "helpful"))
    if vote:
        db.delete(vote)
    else:
        db.add(ReviewVote(user_id=user.id, review_id=r.id, kind="helpful"))
    db.flush()
    r.helpful_count = db.scalar(select(func.count()).select_from(ReviewVote).where(ReviewVote.review_id == r.id, ReviewVote.kind == "helpful"))
    db.commit()
    return {"helpful_by_me": vote is None, "helpful_count": r.helpful_count}


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


@router.post("/reviews/{review_id}/report")
def report_review(review_id: int, payload: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _visible(db, review_id)
    if r.user_id == user.id:
        raise HTTPException(400, "내 후기는 신고할 수 없어요.")
    exists = db.scalar(select(ReviewVote).where(ReviewVote.user_id == user.id, ReviewVote.review_id == r.id, ReviewVote.kind == "report"))
    if exists:
        return {"reported": True, "already": True}
    db.add(ReviewVote(user_id=user.id, review_id=r.id, kind="report", reason=payload.reason.strip()))
    r.report_count += 1
    if r.report_count >= AUTO_HIDE_REPORTS:
        r.hidden = True
    db.commit()
    return {"reported": True, "already": False}


# ---------- 관리자 ----------

@router.get("/admin/reviews", tags=["관리자"])
def admin_reviews(status: str = "reported", _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(Review).order_by(Review.report_count.desc(), Review.id.desc())
    if status == "reported":
        stmt = stmt.where(Review.report_count > 0)
    elif status == "hidden":
        stmt = stmt.where(Review.hidden.is_(True))
    elif status == "medical":
        stmt = stmt.where(Review.medical_claim.is_(True))
    elif status != "all":
        raise HTTPException(400, "status는 reported/hidden/medical/all 중 하나예요.")
    rows = db.scalars(stmt.limit(200)).all()
    reasons = {}
    for v in db.scalars(select(ReviewVote).where(ReviewVote.kind == "report", ReviewVote.review_id.in_({r.id for r in rows}))) if rows else []:
        reasons.setdefault(v.review_id, []).append(v.reason)
    return {"reviews": [{"id": r.id, "product_name": r.product_name, "brand": r.brand, "text": r.text, "rating": r.rating,
                         "report_count": r.report_count, "report_reasons": reasons.get(r.id, []), "hidden": r.hidden,
                         "medical_claim": r.medical_claim, "sponsored": r.sponsored, "verified": r.verified} for r in rows]}


@router.post("/admin/reviews/{review_id}/{action}", tags=["관리자"])
def admin_review_action(review_id: int, action: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "후기를 찾을 수 없어요.")
    if action == "hide":
        r.hidden = True
    elif action == "restore":
        r.hidden, r.report_count = False, 0
        db.execute(delete(ReviewVote).where(ReviewVote.review_id == r.id, ReviewVote.kind == "report"))
    elif action == "delete":
        db.execute(delete(ReviewVote).where(ReviewVote.review_id == r.id))
        db.delete(r)
    else:
        raise HTTPException(400, "action은 hide/restore/delete 중 하나예요.")
    db.commit()
    return {"ok": True}
