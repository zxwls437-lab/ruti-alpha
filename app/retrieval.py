"""질문에 맞는 제품·성분을 DB에서 찾는다 (제품이 수만 개여도 전부 불러오지 않음)."""
import re
import threading
import time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .models import PRODUCT_APPROVED, SOURCE_MANUAL, Ingredient, Product

# 한국어 조사·어미 (긴 것부터 떼어냄)
_PARTICLES = sorted(["이랑", "에서", "으로", "에게", "한테", "까지", "부터", "처럼", "인데", "인가요", "인가", "이에요", "예요", "이야",
                     "을", "를", "이", "가", "은", "는", "에", "로", "랑", "도", "만", "의", "와", "과", "요", "야"], key=len, reverse=True)
_STOP = {"추천", "추천해줘", "추천해", "알려줘", "제품", "화장품", "어떤", "어때", "어때요", "좋은", "있어", "있나요", "해줘", "뭐가", "뭐야",
         "너무", "요즘", "그리고", "근데", "피부", "사용", "써도", "돼요", "되나요", "있는", "하나만", "골라줘"}


def like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def keywords(text: str, limit: int = 12) -> list[str]:
    out: list[str] = []
    for raw in re.split(r"[\s,./()\[\]!?~·'\"]+", text.lower()):
        word = raw
        for p in _PARTICLES:
            if len(word) > len(p) + 1 and word.endswith(p):
                word = word[: -len(p)]
                break
        if len(word) >= 2 and word not in _STOP and word not in out:
            out.append(word)
    return out[:limit]


def candidate_products(db: Session, message: str, memories: list[str], limit: int) -> list[dict]:
    kws = keywords(message + " " + " ".join(memories))
    cols = (Product.name, Product.brand, Product.category, Product.key_ingredients, Product.description, Product.skin_types)
    rows: list[Product] = []
    if kws:
        cond = or_(*(c.ilike(like(k), escape="\\") for k in kws for c in cols))
        rows = list(db.scalars(select(Product).where(Product.status == PRODUCT_APPROVED, cond).limit(300)).all())
    if len(rows) < limit:
        # 직접 등록한(검증한) 제품은 키워드가 안 맞아도 후보로 보여준다
        seen = {r.id for r in rows}
        extra = db.scalars(select(Product).where(Product.status == PRODUCT_APPROVED, Product.source == SOURCE_MANUAL)
                           .order_by(Product.id).limit(limit)).all()
        rows += [r for r in extra if r.id not in seen]

    def score(p: Product) -> tuple:
        text = " ".join((p.name, p.brand, p.category, p.key_ingredients, p.description, p.skin_types)).lower()
        return (-sum(1 for k in kws if k in text), p.source != SOURCE_MANUAL, p.id)

    return [p.to_public() for p in sorted(rows, key=score)[:limit]]


class _IngredientNames:
    """성분 이름 목록을 메모리에 들고 있다가, 개수가 바뀌면 다시 읽는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._names: list[tuple[str, int]] = []
        self._count = -1
        self._checked = 0.0

    def get(self, db: Session) -> list[tuple[str, int]]:
        with self._lock:
            if time.monotonic() - self._checked > 30 or self._count < 0:
                count = db.scalar(select(func.count()).select_from(Ingredient)) or 0
                self._checked = time.monotonic()
                if count != self._count:
                    names = []
                    for iid, ko, en in db.execute(select(Ingredient.id, Ingredient.name_ko, Ingredient.name_en)):
                        if ko and len(ko) >= 2:
                            names.append((ko.lower(), iid))
                        if en and len(en) >= 4:
                            names.append((en.lower(), iid))
                    names.sort(key=lambda x: -len(x[0]))
                    self._names, self._count = names, count
            return self._names

    def reset(self) -> None:
        with self._lock:
            self._count, self._names = -1, []


ingredient_names = _IngredientNames()


def ingredients_in_text(db: Session, text: str, limit: int = 5) -> list[dict]:
    """질문에 등장하는 성분 이름을 찾아 성분 정보를 돌려준다 (긴 이름 우선)."""
    lowered = text.lower()
    found: list[int] = []
    matched: list[str] = []
    for name, iid in ingredient_names.get(db):
        if name in lowered and iid not in found and not any(name in m for m in matched):
            found.append(iid)
            matched.append(name)
            if len(found) >= limit:
                break
    if not found:
        return []
    rows = {i.id: i for i in db.scalars(select(Ingredient).where(Ingredient.id.in_(found)))}
    result = []
    for iid in found:
        d = rows[iid].to_public()
        d["description"] = d["description"][:400]
        d["synonyms"] = d["synonyms"][:200]
        d["restriction"] = d["restriction"][:600]
        result.append(d)
    return result
