"""내 루틴: 화장대 제품으로 아침·저녁 루틴을 만들고, 오늘 체크와 피부 컨디션을 기록하고, 피부 정보로 루틴을 추천한다.

추천은 AI가 아니라 고정 규칙이다 (항상 같은 결과, 비용 0). 피부과·화장품 업계에서 일반적으로 안내하는
순서(세안 → 토너 → 에센스 → 세럼 → 보습 → 선크림)와 피부 타입·고민별 성분 안내 수준이며 의료 판단이 아니다.
"""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select, true
from sqlalchemy.orm import Session

from . import account
from .db import get_db
from .models import PRODUCT_APPROVED, SOURCE_MFDS, Memory, Product, RoutineCheck, SkinLog, User, VanityItem
from .plans import KST
from .scan import SENSITIVITY_GROUPS, matching_memo, normalize, strip_parens
from .security import current_user

router = APIRouter(prefix="/routine", tags=["내 루틴"])

STEPS = {  # 순서대로
    "cleanser": "세안", "toner": "토너", "essence": "에센스", "serum": "세럼·앰플", "cream": "보습", "sunscreen": "선크림", "other": "기타",
}
STEP_ORDER = list(STEPS)
_NAME_HINTS = [  # 제품 이름으로 단계 추정 (앞에 있을수록 우선)
    ("sunscreen", ("선크림", "선스크린", "선블록", "썬크림", "선젤", "선로션", "선스틱", "spf", "자외선")),
    ("cleanser", ("클렌저", "클렌징", "폼", "세안", "워시", "비누")),
    ("toner", ("토너", "스킨", "패드", "미스트")),
    ("essence", ("에센스", "부스터")),
    ("serum", ("세럼", "앰플", "트리트먼트")),
    ("cream", ("크림", "로션", "에멀전", "에멀젼", "밤", "젤", "모이스처")),
]
_UV_FILTERS = {normalize(n) for n in ("징크옥사이드", "티타늄디옥사이드", "에틸헥실메톡시신나메이트", "호모살레이트", "옥토크릴렌",
                                       "비스에틸헥실옥시페놀메톡시페닐트리아진", "에틸헥실살리실레이트", "부틸메톡시다이벤조일메탄")}
_GROUP_NAMES = {g: {normalize(n) for n in names} for g, (_, names) in SENSITIVITY_GROUPS.items()}


def guess_step(name: str, ingredients: list[str]) -> str:
    low = name.lower()
    for step, words in _NAME_HINTS:
        if any(w in low for w in words):
            return step
    if any(normalize(strip_parens(i)) in _UV_FILTERS for i in ingredients):
        return "sunscreen"
    return "other"


def _has_group(ingredients: list[str], group: str) -> bool:
    return any(normalize(strip_parens(i)) in _GROUP_NAMES[group] or normalize(i) in _GROUP_NAMES[group] for i in ingredients)


def guess_slots(step: str, ingredients: list[str]) -> str:
    if step == "sunscreen":
        return "am"
    # 레티놀·각질 제거 성분은 햇빛에 예민해질 수 있어 저녁에
    if _has_group(ingredients, "retinoid") or _has_group(ingredients, "exfoliant"):
        return "pm"
    return "am,pm"


def item_view(v: VanityItem) -> dict:
    ings = json.loads(v.ingredients)
    step = v.step or guess_step(v.product_name, ings)
    slots = v.slots or guess_slots(step, ings)
    return {"id": v.id, "product_name": v.product_name, "step": step, "step_label": STEPS.get(step, "기타"),
            "slots": [s for s in slots.split(",") if s in ("am", "pm")], "guessed": not v.step,
            "retinoid": _has_group(ings, "retinoid"), "exfoliant": _has_group(ings, "exfoliant"), "ingredients": ings,
            "no_ingredients": not ings}


def today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


# ---------- 루틴 추천 (규칙) ----------
# 각 단계: (단계, 이름, 찾아볼 성분, 이유). 피부 타입·고민·민감 성분으로 고른다.

def recommend(memories: list[str]) -> dict:
    text = " ".join(memories)
    has = lambda *words: any(w in text for w in words)  # noqa: E731
    skin = ("건성" if has("건성") else "지성" if has("지성") else "복합성" if has("복합성") else "중성" if has("중성") else "")
    sensitive = has("민감성")
    avoid_groups = {g for g, (words, _) in SENSITIVITY_GROUPS.items() for m in memories
                    if any(w in m.lower() for w in words) and ("민감" in m or "안 맞" in m or "따가" in m or "빨개" in m or "붉어" in m)}
    pregnant = has("임신", "수유")
    concern = {k: has(*w) for k, w in {
        "dry": ("건조함", "속건조"), "dehydrated": ("속건조",), "oil": ("피지", "번들"), "acne": ("트러블", "여드름이"),
        "marks": ("자국",), "pore": ("모공", "블랙헤드"), "flake": ("각질이 고민",), "red": ("붉어짐", "홍조"),
        "wrinkle": ("주름",), "firm": ("탄력",), "tone": ("잡티", "톤", "칙칙"), "eye": ("다크서클",)}.items()}
    gentle = sensitive or concern["red"]
    can_retinol = not pregnant and "retinoid" not in avoid_groups and not gentle
    can_bha = "exfoliant" not in avoid_groups and not gentle

    moist = {"건성": ("세라마이드", "글리세린", "스쿠알란"), "지성": ("히알루론산", "판테놀"), "복합성": ("히알루론산", "세라마이드"),
             "중성": ("글리세린", "히알루론산")}.get(skin, ("글리세린", "세라마이드"))
    texture = {"건성": "크림 제형", "지성": "가벼운 젤·로션", "복합성": "T존은 가볍게, 볼은 크림"}.get(skin, "로션이나 크림")
    notes: list[str] = []

    am = [("cleanser", "세안", ("약산성",) if skin != "지성" else ("약산성", "젤 타입"),
           "건성·민감성이라면 아침엔 물세안이나 순한 세안제로 충분해요." if skin == "건성" or gentle else "밤사이 나온 피지를 순하게 씻어내요.")]
    pm = [("cleanser", "세안", ("약산성",), "선크림·메이크업을 했다면 클렌징 후 한 번 더 세안해요.")]
    if not gentle:
        am.append(("toner", "토너", ("판테놀", "글리세린"), "세안 후 피부 결을 정돈해요. 생략해도 괜찮아요."))
        pm.append(("toner", "토너", ("판테놀", "글리세린"), "세안 후 피부 결을 정돈해요. 생략해도 괜찮아요."))

    # 아침 세럼
    if (concern["tone"] or concern["marks"]) and not gentle:
        am.append(("serum", "비타민C 세럼", ("아스코빅애씨드", "나이아신아마이드"), "잡티·칙칙함·자국 고민에 도움을 줄 수 있어요. 아침에 바르고 선크림을 꼭 함께 발라요."))
    elif concern["marks"]:
        am.append(("serum", "세럼", ("나이아신아마이드", "판테놀"), "자국과 톤 관리에 도움을 줄 수 있는 순한 성분이에요."))
    elif concern["acne"] or concern["pore"] or concern["oil"] or skin in ("지성", "복합성"):
        am.append(("serum", "세럼", ("나이아신아마이드",), "피지와 피부 결 관리에 도움을 줄 수 있어요."))
    elif concern["red"] or gentle:
        am.append(("serum", "진정 세럼", ("판테놀", "병풀추출물"), "예민한 피부를 편안하게 해 주는 성분이에요."))
    if concern["dehydrated"]:
        moist = ("히알루론산", "판테놀", "글리세린")
        notes.append("속건조는 겉은 번들거려도 속은 건조한 상태예요. 가벼운 수분 제품을 여러 번 얇게 발라 보세요.")
    am.append(("cream", "보습", moist, f"{texture}가 잘 맞아요."))
    if concern["eye"]:
        am.append(("cream", "아이크림", ("카페인", "나이아신아마이드"), "눈가는 피부가 얇아요. 약지로 톡톡 두드려 발라요."))
    am.append(("sunscreen", "선크림", ("징크옥사이드",) if gentle else (), "아침 루틴의 마지막은 꼭 선크림이에요. 흐린 날에도 발라요."))

    # 저녁 세럼·트리트먼트
    if (concern["wrinkle"] or concern["firm"]) and can_retinol:
        pm.append(("serum", "레티놀 (주 2~3회부터)", ("레티놀",), "주름·탄력 고민에 도움을 줄 수 있어요. 처음엔 주 2~3회, 소량으로 시작해요."))
        notes.append("레티놀을 쓰는 날엔 다음 날 아침 선크림을 꼭 발라 주세요.")
    elif concern["wrinkle"] or concern["firm"]:
        pm.append(("serum", "펩타이드 세럼", ("아데노신", "펩타이드"), "레티놀 대신 순하게 주름·탄력을 관리할 수 있는 성분이에요."))
    elif (concern["acne"] or concern["pore"] or concern["oil"] or skin == "지성") and can_bha:
        pm.append(("serum", "BHA (주 2~3회)", ("살리실릭애씨드",), "모공 속 피지와 각질 관리에 도움을 줄 수 있어요. 매일 쓰지 말고 주 2~3회만요."))
    elif concern["flake"] and "exfoliant" not in avoid_groups and not gentle:
        pm.append(("serum", "순한 각질 케어 (주 1~2회)", ("글루코노락톤", "락틱애씨드"), "PHA·젖산은 각질 제거 성분 중 순한 편이에요. 주 1~2회만 써요."))
    elif concern["dry"] or skin == "건성":
        pm.append(("serum", "보습 세럼", ("히알루론산", "세라마이드"), "자는 동안 수분이 날아가지 않게 채워 줘요."))
    elif gentle:
        pm.append(("serum", "진정 세럼", ("판테놀", "병풀추출물"), "예민해진 피부를 편안하게 해 주는 성분이에요."))
    pm.append(("cream", "보습", moist, f"{texture}로 마무리해요."))

    if gentle:
        notes.append("예민한 피부는 단계를 줄일수록 편해요. 새 제품은 팔 안쪽에 먼저 발라 보고 하나씩 더해요.")
    if pregnant:
        notes.append("임신·수유 중에는 레티놀류를 피하고, 새 성분은 의사·약사와 상의해 주세요.")
    if "retinoid" in avoid_groups or "exfoliant" in avoid_groups:
        notes.append("민감하다고 알려주신 레티놀·각질 제거 성분은 추천에서 뺐어요.")
    labels = {"fragrance": "향료", "alcohol": "알코올", "exfoliant": "각질 제거 성분(AHA·BHA)", "retinoid": "레티놀",
              "paraben": "파라벤", "essential_oil": "에센셜 오일"}
    avoid = sorted({labels[g] for g in avoid_groups} | ({"향료"} if gentle else set()))
    as_dict = lambda steps: [{"step": s, "title": t, "look_for": list(f), "why": w, "examples": example_kind(s, t, gentle)}  # noqa: E731
                             for s, t, f, w in steps]
    return {"skin": skin, "sensitive": sensitive, "am": as_dict(am), "pm": as_dict(pm), "avoid": avoid, "notes": notes,
            "based_on": memories[:6], "needs_skin_info": not memories}


# ---------- 추천 단계별 제품 예시 (식약처 기능성 화장품) ----------
# 식약처 데이터에는 기능성(자외선 차단·미백·주름) 제품만 있어서, 그 기능이 핵심인 단계에만 예시를 붙인다.
# 광고·순위가 아니라 '이 조건에 맞는 신고 제품' 예시이며, 날마다 섞어서 특정 제품만 계속 나오지 않게 한다.
_SUN = ("선크림", "선젤", "선로션", "선세럼", "선밀크", "선에센스", "선스크린", "썬크림")
EXAMPLES = {
    "sun": {"label": "SPF50+ · PA++++ 선크림", "name": (_SUN,),
            "desc": (("SPF50+",), ("PA4", "PA++++"))},
    "sun_mild": {"label": "무기자차(순한) 선크림 · SPF50+", "name": (_SUN, ("무기", "마일드", "민감", "순한")), "desc": (("SPF50+",),)},
    "brighten": {"label": "미백 기능성 세럼·앰플", "name": (("세럼", "앰플", "에센스"),), "desc": (("미백",),)},
    "wrinkle": {"label": "주름개선 기능성 세럼·앰플", "name": (("세럼", "앰플", "에센스"),), "desc": (("주름",),)},
    "retinol": {"label": "주름개선 기능성 레티놀 제품", "name": (("레티놀",),), "desc": (("주름",),)},
    "eye": {"label": "주름개선 기능성 아이크림", "name": (("아이크림", "아이세럼", "아이 크림"),), "desc": (("주름",),)},
}


def _desc_line(desc: str, head: str) -> str:
    return next((line[len(head):].strip() for line in (desc or "").splitlines() if line.startswith(head)), "")


def example_kind(step: str, title: str, gentle: bool) -> str | None:
    if step == "sunscreen":
        return "sun_mild" if gentle else "sun"
    if "아이크림" in title:
        return "eye"
    if "레티놀" in title:
        return "retinol"
    if "펩타이드" in title:
        return "wrinkle"
    if "비타민C" in title:
        return "brighten"
    return None


_example_cache: dict[str, tuple[float, list[dict]]] = {}  # 종류 → (만든 시각, 후보 최대 300개). 20만 개를 매번 훑지 않게
_EXAMPLE_TTL = 6 * 3600


def _example_pool(db: Session, kind: str) -> list[dict]:
    import random  # noqa: PLC0415
    import time  # noqa: PLC0415

    from .retrieval import like  # noqa: PLC0415
    hit = _example_cache.get(kind)
    if hit and time.monotonic() - hit[0] < _EXAMPLE_TTL:
        return hit[1]
    spec = EXAMPLES[kind]
    conds = [or_(*(Product.name.ilike(like(w), escape="\\") for w in any_of)) for any_of in spec["name"]]
    for any_of in spec["desc"]:
        conds.append(or_(*(Product.description.ilike(like(w), escape="\\") for w in any_of)))
    # 이름이 숫자 코드로 시작하는 것(시판명이 아닌 내부 코드)은 제외
    not_code = ~Product.name.op("~")("^[0-9]") if db.bind.dialect.name == "postgresql" else true()
    rows = db.scalars(select(Product).where(Product.status == PRODUCT_APPROVED, Product.source == SOURCE_MFDS, *conds, not_code)
                      .order_by(Product.id.desc()).limit(400)).all()
    # 예시에는 특정 대상(임산부·아기·남성)용 제품을 넣지 않는다
    from .ai import audience_mismatch  # noqa: PLC0415
    rows = [p for p in rows if not audience_mismatch({"name": p.name, "category": p.category}, [], "")][:300]
    pool = [{"id": p.id, "name": p.display_name or p.name, "brand": p.brand, "source": p.source, "functions": _desc_line(p.description, "기능:"),
             "usage": _desc_line(p.description, "사용법:"), "ingredients": []} for p in rows]
    random.Random(kind).shuffle(pool)
    _example_cache[kind] = (time.monotonic(), pool)
    return pool


@router.get("/examples")
def step_examples(kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind not in EXAMPLES:
        raise HTTPException(404, "알 수 없는 종류예요.")
    import random  # noqa: PLC0415
    pool = _example_pool(db, kind)
    # 광고·순위가 아니라 예시: 날마다, 사람마다 다른 12개
    picks = random.Random(f"{today()}:{user.id}:{kind}").sample(pool, min(12, len(pool)))
    return {"label": EXAMPLES[kind]["label"], "products": picks}


def _memories(db: Session, user: User) -> list[str]:
    if not account.has_sensitive_consent(db, user):
        return []
    return list(db.scalars(select(Memory.content).where(Memory.user_id == user.id).order_by(Memory.id)))


def _match_products(rec: dict, items: list[dict]) -> None:
    """추천 단계마다 내 화장대에서 맞는 제품을 붙인다."""
    for slot in ("am", "pm"):
        for st in rec[slot]:
            # 세럼처럼 '어떤 성분'이 핵심인 단계만 확인 (세안의 '약산성' 같은 건 성분명이 아니다)
            wanted = [normalize(f) for f in st["look_for"]] if st["step"] in ("serum", "essence") else []
            st["mine"] = [{"id": i["id"], "product_name": i["product_name"],
                           # 추천 성분이 실제로 들어 있는지 (같은 '세럼' 단계라도 레티놀 세럼은 보습 세럼이 아니다)
                           "fits": not wanted or any(w in normalize(n) for w in wanted for n in i["ingredients"])}
                          for i in items if i["step"] == st["step"] and slot in i["slots"]]


def _view(db: Session, user: User) -> dict:
    rows = list(db.scalars(select(VanityItem).where(VanityItem.user_id == user.id).order_by(VanityItem.id)))
    items = [item_view(v) for v in rows]
    order = lambda i: (STEP_ORDER.index(i["step"]) if i["step"] in STEP_ORDER else 99, i["id"])  # noqa: E731
    day = today()
    checks = {(c.slot, c.item_id) for c in db.scalars(select(RoutineCheck).where(RoutineCheck.user_id == user.id, RoutineCheck.day == day))}
    routine = {}
    for slot in ("am", "pm"):
        routine[slot] = [{**{k: i[k] for k in ("id", "product_name", "step", "step_label", "guessed", "no_ingredients")}, "done": (slot, i["id"]) in checks}
                         for i in sorted(items, key=order) if slot in i["slots"]]
    memories = _memories(db, user)
    # 제품끼리 조합 점검(내 화장대 규칙) + 선크림 빠짐
    from .vanity import check_combinations  # 순환 import 방지
    warnings = [{"title": c["title"], "detail": c["detail"], "products": c["products"], "explainer": c.get("explainer")}
                for c in check_combinations([{"product_name": i["product_name"], "ingredients": i["ingredients"]} for i in items], memories)]
    if any(i["retinoid"] or i["exfoliant"] for i in items) and not any("am" in i["slots"] and i["step"] == "sunscreen" for i in items):
        warnings.append({"title": "아침 선크림이 루틴에 없어요", "products": [], "explainer": None,
                         "detail": "레티놀·각질 제거 제품을 쓰면 햇빛에 예민해질 수 있어요. 아침 마지막 단계에 선크림을 꼭 넣어 주세요."})
    # 내 피부 정보와 맞지 않는 성분이 든 제품은 루틴에서 표시
    for i in items:
        i["conflict"] = next((m for m in (matching_memo(n, memories) for n in i["ingredients"]) if m), "") if memories else ""
    for slot in ("am", "pm"):
        for r in routine[slot]:
            r["conflict"] = next(i["conflict"] for i in items if i["id"] == r["id"])
    rec = recommend(memories)
    _match_products(rec, items)
    since = (datetime.now(KST) - timedelta(days=6)).strftime("%Y-%m-%d")
    logs = [{"day": g.day, "mood": g.mood, "note": g.note} for g in db.scalars(
        select(SkinLog).where(SkinLog.user_id == user.id, SkinLog.day >= since).order_by(SkinLog.day))]
    return {"today": day, "routine": routine, "items": [{k: i[k] for k in ("id", "product_name", "step", "step_label", "slots", "guessed", "no_ingredients")} for i in items],
            "warnings": warnings, "recommendation": rec, "logs": logs, "steps": STEPS,
            "can_log": account.has_sensitive_consent(db, user)}


@router.get("/today")  # 화면 주소(/routine)와 겹치지 않게
def my_routine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _view(db, user)


class ItemSetting(BaseModel):
    step: str | None = Field(default=None, max_length=20)
    slots: list[str] | None = None


@router.patch("/items/{item_id}")
def set_item(item_id: int, payload: ItemSetting, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(VanityItem, item_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "화장대에서 찾을 수 없어요.")
    if payload.step is not None:
        if payload.step not in STEPS:
            raise HTTPException(422, "알 수 없는 단계예요.")
        row.step = payload.step
    if payload.slots is not None:
        slots = [s for s in ("am", "pm") if s in payload.slots]
        row.slots = ",".join(slots) or "off"
    db.commit()
    return _view(db, user)


class CheckIn(BaseModel):
    item_id: int
    slot: str = Field(pattern="^(am|pm)$")
    done: bool = True


@router.post("/check")
def check(payload: CheckIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(VanityItem, payload.item_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "화장대에서 찾을 수 없어요.")
    day = today()
    existing = db.scalar(select(RoutineCheck).where(RoutineCheck.user_id == user.id, RoutineCheck.day == day,
                                                    RoutineCheck.slot == payload.slot, RoutineCheck.item_id == row.id))
    if payload.done and not existing:
        db.add(RoutineCheck(user_id=user.id, item_id=row.id, day=day, slot=payload.slot))
    elif not payload.done and existing:
        db.delete(existing)
    db.commit()
    return _view(db, user)


class LogIn(BaseModel):
    mood: int = Field(ge=1, le=3)
    note: str = Field(default="", max_length=200)


@router.put("/log")
def log_today(payload: LogIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not account.has_sensitive_consent(db, user):
        raise HTTPException(403, "피부 컨디션을 기록하려면 '피부 상태 등 민감정보 처리'에 동의해 주세요.")
    day = today()
    row = db.scalar(select(SkinLog).where(SkinLog.user_id == user.id, SkinLog.day == day))
    if row:
        row.mood, row.note = payload.mood, payload.note.strip()
    else:
        db.add(SkinLog(user_id=user.id, day=day, mood=payload.mood, note=payload.note.strip()))
    db.commit()
    return _view(db, user)


def delete_item_checks(db: Session, item_id: int) -> None:
    db.execute(delete(RoutineCheck).where(RoutineCheck.item_id == item_id))


# ---------- 피부 아바타 + 레벨업 ----------
# 원칙: 아바타 얼굴은 '사용자가 기록한 피부 상태'(고른 고민 + 오늘 피부 기록)만 보여준다. 제품 효과를 예측·약속하지 않는다.
# 레벨·배지는 꾸준함(루틴 체크·기록한 날)으로만 오른다.
AVATAR_CONCERNS = {"acne": ("트러블", "여드름"), "red": ("붉어짐", "홍조"), "dry": ("건조", "속건조", "당김", "건성"),
                   "oil": ("피지", "번들", "지성"), "tone": ("잡티", "칙칙", "톤"), "pore": ("모공", "블랙헤드"), "wrinkle": ("주름", "탄력")}
LEVELS = [(0, "새싹"), (30, "물방울"), (80, "촉촉"), (150, "말랑"), (250, "반짝"), (400, "빛나는"), (600, "보석"), (900, "별빛")]
BADGES = [("first_check", "첫 루틴 체크", "🌱"), ("first_log", "첫 피부 기록", "📝"), ("streak3", "3일 연속", "🔥"),
          ("streak7", "7일 연속", "💪"), ("streak14", "2주 연속", "🌟"), ("streak30", "30일 연속", "👑"), ("days30", "30일 기록", "🏅")]


def _streak(days: set[str], now: datetime) -> int:
    """오늘(또는 아직 안 했으면 어제)부터 거꾸로 이어진 날 수."""
    d = now.date()
    if d.strftime("%Y-%m-%d") not in days:
        d -= timedelta(days=1)
    n = 0
    while d.strftime("%Y-%m-%d") in days:
        n += 1
        d -= timedelta(days=1)
    return n


def avatar_state(memories: list[str], logs: list[tuple[str, int]], check_days: set[str], now: datetime) -> dict:
    text = " ".join(memories)
    concerns = [k for k, words in AVATAR_CONCERNS.items() if any(w in text for w in words)]
    logs = sorted(logs)
    recent = [m for _, m in logs[-3:]]
    # 최근 기록이 좋을수록 고민 표시가 옅어진다 (기록이 없으면 중간)
    calm = (sum(recent) / len(recent) - 1) / 2 if recent else 0.4
    intensity = round(max(0.15, 1 - 0.75 * calm), 2)
    log_days = {d for d, _ in logs}
    xp = 10 * len(check_days) + 5 * len(log_days) + 5 * max(0, _streak(check_days, now) - 1)
    level_i = max(i for i, (need, _) in enumerate(LEVELS) if xp >= need)
    cur, nxt = LEVELS[level_i][0], (LEVELS[level_i + 1][0] if level_i + 1 < len(LEVELS) else None)
    streak = _streak(check_days, now)
    got = {"first_check": bool(check_days), "first_log": bool(log_days), "streak3": streak >= 3, "streak7": streak >= 7,
           "streak14": streak >= 14, "streak30": streak >= 30, "days30": len(check_days | log_days) >= 30}
    week = lambda a, b: [m for d, m in logs if (now.date() - timedelta(days=b)).strftime("%Y-%m-%d") <= d <= (now.date() - timedelta(days=a)).strftime("%Y-%m-%d")]  # noqa: E731
    first = [m for _, m in logs[:7]]
    last7 = week(0, 6)
    return {
        "concerns": concerns, "intensity": intensity, "mood": logs[-1][1] if logs and logs[-1][0] == now.strftime("%Y-%m-%d") else 0,
        "level": level_i + 1, "level_name": LEVELS[level_i][1], "xp": xp, "level_xp": cur, "next_xp": nxt,
        "streak": streak, "check_days": len(check_days), "log_days": len(log_days),
        "badges": [{"id": b, "name": n, "icon": i, "got": got[b]} for b, n, i in BADGES],
        "compare": {"first_avg": round(sum(first) / len(first), 2) if first else None,
                    "last7_avg": round(sum(last7) / len(last7), 2) if last7 else None, "enough": len(logs) >= 8},
    }


@router.get("/avatar")
def my_avatar(user: User = Depends(current_user), db: Session = Depends(get_db)):
    memories = _memories(db, user)
    logs = [(d, m) for d, m in db.execute(select(SkinLog.day, SkinLog.mood).where(SkinLog.user_id == user.id))]
    check_days = set(db.scalars(select(RoutineCheck.day).where(RoutineCheck.user_id == user.id)))
    return avatar_state(memories, logs, check_days, datetime.now(KST))
