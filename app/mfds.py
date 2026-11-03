"""식약처 공공데이터(data.go.kr) 가져오기.

1) fetch: API 응답 원본을 mfds_records 테이블에 그대로 저장
2) build: 원본을 RUTI용 성분 사전(ingredients)과 제품(products)으로 변환

API마다 필드 이름이 달라서, 후보 이름 목록 + 이름 패턴으로 찾는다.
probe 결과를 보고 FIELD_CANDIDATES만 고치면 다시 받지 않고 build만 다시 하면 된다.
"""
import hashlib
import json
from collections.abc import Iterator

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import env
from .db import utcnow
from .models import PRODUCT_APPROVED, SOURCE_MFDS, Ingredient, MfdsRecord, Product

# 데이터셋 이름 → (.env 변수 이름, 설명)
DATASETS = {
    "ingredient": ("MFDS_INGREDIENT_URL", "화장품 원료성분정보"),
    "restricted": ("MFDS_RESTRICTED_URL", "화장품 사용제한 원료정보"),
    "functional_report": ("MFDS_FUNCTIONAL_REPORT_URL", "기능성화장품 보고품목정보"),
    "functional_review": ("MFDS_FUNCTIONAL_REVIEW_URL", "기능성화장품 심사품목 정보"),
    "cosmetics_info": ("MFDS_COSMETICS_INFO_URL", "화장품 관련 정보"),
}

# 필드 후보 (대문자 비교). 앞에 있을수록 우선.
FIELD_CANDIDATES = {
    "id": ["ITEM_SEQ", "INGR_SEQ", "SEQ", "ID", "CSMTC_SEQ", "REPORT_SEQ"],
    "name_ko": ["INGR_KOR_NAME", "INGR_STD_NAME", "KOR_NAME", "INGR_NAME", "STD_NAME", "REGULATE_NAME"],
    "name_en": ["INGR_ENG_NAME", "ENG_NAME", "INGR_STD_ENG_NAME"],
    "cas_no": ["CAS_NO", "CASNO", "CAS"],
    "synonyms": ["INGR_SYNONYM", "SYNONYM", "OTHER_NAME"],
    "description": ["ORIGIN_MAJOR_KOR_NAME", "ORIGIN", "DEFINITION", "INGR_DESC"],
    "restriction": ["LIMIT_COND", "PROVIS_ATRCL", "LIMIT", "REGULATE_TYPE", "RESTRICT", "NOTICE_INGR_NAME"],
    "product_name": ["ITEM_NAME", "PRDUCT", "PRDLST_NM", "PRODUCT_NAME", "PRDT_NM"],
    "company": ["ENTP_NAME", "BSSH_NM", "COMPANY_NAME", "MANUF_NAME", "ENTRPS"],
    "effect": ["EFFECT", "EE_DOC_DATA", "EFCY_QESITM", "EFFICACY", "FUNC_TYPE", "COSMETIC_REPORT_TYPE", "ITEM_PERMIT_TYPE"],
    "usage": ["USAGE_DOSAGE", "UD_DOC_DATA", "USE_METHOD"],
    "ingredients": ["MAIN_INGR", "INGR_NAME_LIST", "MATERIAL_NAME", "MAIN_ITEM_INGR"],
    "date": ["REPORT_DATE", "ITEM_PERMIT_DATE", "PERMIT_DATE", "REG_DATE"],
}
# 후보에 없을 때 키 이름에 이 글자가 들어가면 사용
FIELD_PATTERNS = {
    "name_ko": [("KOR", "NAME")], "name_en": [("ENG", "NAME")], "restriction": [("LIMIT",), ("ATRCL",)],
    "product_name": [("ITEM", "NAME")], "company": [("ENTP",), ("BSSH",)], "effect": [("EFFECT",), ("EFCY",)],
}


class MfdsError(Exception):
    pass


def pick(item: dict, field: str) -> str:
    upper = {str(k).upper(): v for k, v in item.items()}
    for key in FIELD_CANDIDATES.get(field, []):
        value = upper.get(key)
        if value not in (None, ""):
            return str(value).strip()
    for parts in FIELD_PATTERNS.get(field, []):
        for key, value in upper.items():
            if all(p in key for p in parts) and value not in (None, ""):
                return str(value).strip()
    return ""


def _find(obj, name: str):
    """중첩 dict에서 키 이름으로 첫 번째 값을 찾는다."""
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        for v in obj.values():
            found = _find(v, name)
            if found is not None:
                return found
    return None


def parse_page(payload: dict) -> tuple[list[dict], int]:
    """data.go.kr JSON 응답에서 (항목 목록, 전체 개수)를 꺼낸다. 여러 응답 모양을 지원."""
    code = _find(payload, "resultCode")
    if code not in (None, "00", "0", 0, "INFO-000"):
        raise MfdsError(f"API 오류 {code}: {_find(payload, 'resultMsg')}")
    items = _find(payload, "items")
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []
    items = [i.get("item", i) if isinstance(i, dict) and set(i) == {"item"} else i for i in items]
    total = _find(payload, "totalCount")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(items)
    return [i for i in items if isinstance(i, dict)], total


def dataset_url(dataset: str) -> str:
    if dataset not in DATASETS:
        raise MfdsError(f"알 수 없는 데이터셋: {dataset} (가능: {', '.join(DATASETS)})")
    var, label = DATASETS[dataset]
    url = env(var)
    if not url:
        raise MfdsError(f".env에 {var}(={label} End Point 주소)를 입력하세요.")
    return complete_url(url)


def complete_url(url: str) -> str:
    """End Point만 적었으면 식약처 규칙대로 오퍼레이션을 붙인다.
    예: .../CsmtcsIngdCpntInfoService01 → .../CsmtcsIngdCpntInfoService01/getCsmtcsIngdCpntInfoService01"""
    url = url.strip().rstrip("/").split("?")[0]
    last = url.rsplit("/", 1)[-1]
    if last.lower().startswith("get"):
        return url
    return f"{url}/get{last}"


def fetch_page(dataset: str, page: int, rows: int) -> tuple[list[dict], int]:
    key = env("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise MfdsError(".env에 DATA_GO_KR_SERVICE_KEY(공공데이터포털 '일반 인증키(Decoding)')를 입력하세요.")
    params = {"serviceKey": key, "pageNo": page, "numOfRows": rows, "type": "json"}
    try:
        resp = httpx.get(dataset_url(dataset), params=params, timeout=60)
    except httpx.HTTPError as e:
        raise MfdsError(f"연결 실패: {type(e).__name__}") from None
    text = resp.text.strip()
    if text.startswith("<"):
        # 인증 오류 등은 JSON을 요청해도 XML로 온다
        import re
        msg = re.search(r"<(returnAuthMsg|resultMsg|errMsg)>([^<]*)<", text)
        raise MfdsError(f"API 오류 (HTTP {resp.status_code}): {msg.group(2) if msg else text[:200]}")
    if resp.status_code >= 400:
        raise MfdsError(f"API 오류 HTTP {resp.status_code}: {text[:200]}")
    try:
        return parse_page(resp.json())
    except ValueError:
        raise MfdsError(f"JSON이 아닌 응답: {text[:200]}") from None


def record_key(item: dict) -> str:
    rid = pick(item, "id")
    if rid:
        return rid[:200]
    return hashlib.sha1(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def iter_pages(dataset: str, rows: int = 100, max_pages: int = 0) -> Iterator[tuple[int, int, list[dict]]]:
    page = 1
    while True:
        items, total = fetch_page(dataset, page, rows)
        yield page, total, items
        if not items or page * rows >= total or (max_pages and page >= max_pages):
            return
        page += 1


def save_records(db: Session, dataset: str, items: list[dict]) -> int:
    keys = [record_key(i) for i in items]
    existing = {r.record_key: r for r in db.scalars(select(MfdsRecord).where(MfdsRecord.dataset == dataset, MfdsRecord.record_key.in_(keys)))}
    for key, item in zip(keys, items):
        data = json.dumps(item, ensure_ascii=False)
        if key in existing:
            existing[key].data, existing[key].fetched_at = data, utcnow()
        else:
            row = MfdsRecord(dataset=dataset, record_key=key, data=data)
            db.add(row)
            existing[key] = row
    db.commit()
    return len(items)


def records(db: Session, dataset: str) -> Iterator[dict]:
    for row in db.scalars(select(MfdsRecord).where(MfdsRecord.dataset == dataset).order_by(MfdsRecord.id)).yield_per(1000):
        yield json.loads(row.data)


def build_ingredients(db: Session) -> int:
    """원료성분정보 + 사용제한 원료정보 → ingredients 테이블을 새로 만든다."""
    by_name: dict[str, Ingredient] = {}
    for item in records(db, "ingredient"):
        name = pick(item, "name_ko")
        if not name:
            continue
        by_name[name] = Ingredient(name_ko=name[:300], name_en=pick(item, "name_en")[:300], cas_no=pick(item, "cas_no")[:200],
                                   synonyms=pick(item, "synonyms"), description=pick(item, "description"))
    for item in records(db, "restricted"):
        name = pick(item, "name_ko")
        if not name:
            continue
        rule = pick(item, "restriction") or "사용제한 원료"
        ing = by_name.get(name)
        if ing is None:
            ing = by_name[name] = Ingredient(name_ko=name[:300], name_en=pick(item, "name_en")[:300], cas_no=pick(item, "cas_no")[:200])
        ing.restriction = (ing.restriction + " / " + rule) if ing.restriction else rule
    db.execute(delete(Ingredient))
    db.add_all(by_name.values())
    db.commit()
    return len(by_name)


def build_products(db: Session) -> int:
    """기능성화장품 보고·심사 품목 → products (출처 mfds, 자동 승인)."""
    count = 0
    for dataset, label in (("functional_report", "기능성화장품 보고품목"), ("functional_review", "기능성화장품 심사품목")):
        existing = {p.external_key: p for p in db.scalars(select(Product).where(Product.source == SOURCE_MFDS, Product.external_key.like(f"{dataset}:%")))}
        for item in records(db, dataset):
            name = pick(item, "product_name")
            if not name:
                continue
            key = f"{dataset}:{record_key(item)}"[:200]
            effect, usage, date = pick(item, "effect"), pick(item, "usage"), pick(item, "date")
            desc = "\n".join(x for x in (f"[식약처 {label}]", f"기능: {effect}" if effect else "", f"사용법: {usage}" if usage else "",
                                          f"보고/심사일: {date}" if date else "") if x)
            p = existing.get(key) or Product(source=SOURCE_MFDS, external_key=key)
            p.name, p.brand, p.category = name[:200], pick(item, "company")[:150], "기능성화장품"
            p.key_ingredients, p.description, p.status = pick(item, "ingredients")[:2000], desc[:4000], PRODUCT_APPROVED
            p.review_note = "식약처 공공데이터 자동 등록"
            if key not in existing:
                db.add(p)
                existing[key] = p
            count += 1
            if count % 1000 == 0:
                db.commit()
    db.commit()
    return count
