"""내 화장대: 쓰고 있는 제품을 모아 두고, 제품끼리의 성분 조합을 규칙으로 점검한다.

규칙은 일반적인 스킨케어 안내 수준이며 의료 판단이 아니다. AI가 아니라 고정 규칙이라 결과가 항상 같다.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import account
from .config import env_int
from .db import get_db
from .models import Memory, ScanResult, User, VanityItem
from .scan import normalize, split_ingredients, strip_parens
from .security import current_user

router = APIRouter(prefix="/vanity", tags=["내 화장대"])

# 성분 그룹 (식약처 표준 국문명 기준, 띄어쓰기 무시)
GROUPS = {
    "retinoid": ("레티노이드(레티놀류)", ["레티놀", "레티닐팔미테이트", "레티닐아세테이트", "레티날", "하이드록시피나코론레티노에이트", "레티닐레티노에이트"]),
    "aha": ("AHA(각질 제거)", ["글라이콜릭애씨드", "락틱애씨드", "만델릭애씨드", "말릭애씨드", "타타릭애씨드"]),
    "bha": ("BHA(각질 제거)", ["살리실릭애씨드", "베타인살리실레이트"]),
    "pha": ("PHA(각질 제거)", ["글루코노락톤", "락토바이오닉애씨드"]),
    "vitc": ("비타민C(아스코빅애씨드)", ["아스코빅애씨드"]),
    "fragrance": ("향료", ["향료"]),
}
_INDEX = {normalize(n): g for g, (_, names) in GROUPS.items() for n in names}


def groups_of(ingredients: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name in ingredients:
        for cand in (name, strip_parens(name)):
            g = _INDEX.get(normalize(cand))
            if g:
                found.setdefault(g, []).append(name)
                break
    return found


def check_combinations(items: list[dict], memories: list[str]) -> list[dict]:
    """items: [{"id", "product_name", "ingredients": [...]}] → 점검 결과 목록 (주의 먼저)."""
    per = [(it, groups_of(it["ingredients"])) for it in items]
    having = lambda *gs: [it["product_name"] for it, g in per if any(x in g for x in gs)]
    out = []

    retinoid, exfol = having("retinoid"), having("aha", "bha", "pha")
    if retinoid and exfol and len(set(retinoid) | set(exfol)) > 1:
        out.append({"level": "caution", "kind": "retinoid_exfoliant",
                    "title": "레티놀류와 각질 제거 성분을 함께 쓰고 있어요",
                    "detail": "같은 시간에 겹쳐 바르면 자극이 커질 수 있어요. 아침·저녁으로 나누거나 번갈아 쓰는 걸 권해요.",
                    "products": sorted(set(retinoid) | set(exfol)), "explainer": "combo"})
    if len(set(exfol)) >= 2:
        out.append({"level": "caution", "kind": "multiple_exfoliants",
                    "title": f"각질 제거 성분이 {len(set(exfol))}개 제품에 들어 있어요",
                    "detail": "AHA·BHA·PHA를 여러 제품으로 매일 쓰면 피부가 예민해질 수 있어요. 횟수를 줄이거나 하나만 골라 쓰세요.",
                    "products": sorted(set(exfol))})
    if len(set(retinoid)) >= 2:
        out.append({"level": "caution", "kind": "duplicate_retinoid",
                    "title": "레티놀류가 여러 제품에 겹쳐 있어요",
                    "detail": "같은 계열 성분을 겹쳐 쓰면 자극이 생기기 쉬워요. 한 제품만 쓰는 걸 권해요.",
                    "products": sorted(set(retinoid))})
    mem = " ".join(memories)
    if ("임신" in mem or "수유" in mem) and retinoid:
        out.append({"level": "caution", "kind": "pregnancy_retinoid",
                    "title": "임신·수유 중이라고 알려주셨어요",
                    "detail": "레티놀류 성분은 사용 전에 의사·약사와 상의해 주세요.", "products": sorted(set(retinoid))})
    if "향료" in mem:
        frag = having("fragrance")
        if frag:
            out.append({"level": "caution", "kind": "fragrance_sensitive",
                        "title": f"향료가 든 제품이 {len(frag)}개 있어요",
                        "detail": "향료에 민감하다고 알려주셨어요. 따가움이 있으면 이 제품들부터 쉬어 보세요.", "products": sorted(set(frag))})
    vitc = having("vitc")
    if vitc and (retinoid or exfol):
        out.append({"level": "info", "kind": "vitc_timing",
                    "title": "비타민C와 레티놀·각질 제거 제품이 함께 있어요",
                    "detail": "예민한 피부라면 비타민C는 아침, 레티놀·각질 제거 제품은 저녁처럼 나눠 쓰면 편해요.",
                    "products": sorted(set(vitc) | set(retinoid) | set(exfol))})
    return out


def _items(db: Session, user: User) -> list[VanityItem]:
    return list(db.scalars(select(VanityItem).where(VanityItem.user_id == user.id).order_by(VanityItem.id)))


def _view(db: Session, user: User) -> dict:
    rows = _items(db, user)
    items = [{"id": r.id, "product_name": r.product_name, "ingredients": json.loads(r.ingredients), "scan_id": r.scan_id,
              "created_at": r.created_at.isoformat()} for r in rows]
    memories = list(db.scalars(select(Memory.content).where(Memory.user_id == user.id))) if account.has_sensitive_consent(db, user) else []
    for it in items:
        it["groups"] = {g: GROUPS[g][0] for g in groups_of(it["ingredients"])}
    return {"items": items, "checks": check_combinations(items, memories), "max_items": env_int("RUTI_VANITY_MAX", 50)}


@router.get("")
def my_vanity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _view(db, user)


class VanityIn(BaseModel):
    scan_id: int | None = None
    product_name: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10_000, description="scan_id 없이 전성분 글자로 추가할 때")


@router.post("", status_code=201)
def add_to_vanity(payload: VanityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(VanityItem).where(VanityItem.user_id == user.id))
    if count >= env_int("RUTI_VANITY_MAX", 50):
        raise HTTPException(400, "화장대에 담을 수 있는 제품 수를 넘었어요. 안 쓰는 제품을 빼 주세요.")
    if payload.scan_id is not None:
        scan_row = db.get(ScanResult, payload.scan_id)
        if not scan_row or scan_row.user_id != user.id:
            raise HTTPException(404, "분석 기록을 찾을 수 없어요.")
        names = [i["input"] for i in json.loads(scan_row.result).get("items", [])]
        product = payload.product_name.strip() or scan_row.product_name or "이름 없는 제품"
        if db.scalar(select(VanityItem).where(VanityItem.user_id == user.id, VanityItem.scan_id == scan_row.id)):
            raise HTTPException(409, "이미 화장대에 담은 제품이에요.")
    else:
        names = split_ingredients(payload.text)
        product = payload.product_name.strip()
        if not names or not product:
            raise HTTPException(422, "제품 이름과 전성분을 입력해 주세요.")
    if not names:
        raise HTTPException(422, "전성분 정보가 없는 제품이에요.")
    db.add(VanityItem(user_id=user.id, product_name=product[:200], ingredients=json.dumps(names, ensure_ascii=False), scan_id=payload.scan_id))
    db.commit()
    return _view(db, user)


@router.delete("/{item_id}")
def remove_from_vanity(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(VanityItem, item_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "화장대에서 찾을 수 없어요.")
    db.delete(row)
    db.commit()
    return _view(db, user)
