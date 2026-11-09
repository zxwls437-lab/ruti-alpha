"""배포 서버로 식약처 성분 데이터를 옮기는 관리자 기능.

두 가지 방법을 모두 둔다 (해외 서버에서 공공데이터포털 접속이 막힐 수 있어서):
  1) 서버가 식약처 API에서 직접 받기   POST /admin/data/mfds-sync  (백그라운드, 진행 상황은 status)
  2) 파일로 옮기기                     PC: python -m scripts.mfds export → 관리자 화면에서 파일 올리기
                                      (POST /admin/data/ingredients-import, gzip JSON)
"""
import gzip
import json
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import mfds
from .config import env
from .db import SessionLocal, get_db
from .models import SOURCE_MFDS, Ingredient, MfdsRecord, Product, ProductIngredientList, User
from .security import require_admin

log = logging.getLogger("ruti.datasync")
router = APIRouter(prefix="/admin/data", tags=["관리자 데이터"])

FIELDS = ("name_ko", "name_en", "cas_no", "synonyms", "description", "restriction")
MAX_UPLOAD = 40 * 1024 * 1024  # gzip 기준 40MB (성분 2만 7천 개는 수 MB)

_job_lock = threading.Lock()
job: dict = {"state": "idle", "message": "", "started_at": None, "finished_at": None}


# ---------- 내보내기 / 가져오기 ----------

def export_ingredients(db: Session) -> bytes:
    rows = [{f: getattr(i, f) or "" for f in FIELDS} for i in db.scalars(select(Ingredient).order_by(Ingredient.id))]
    payload = {"format": "ruti-ingredients-v1", "count": len(rows), "ingredients": rows}
    return gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def parse_ingredients(raw: bytes) -> list[dict]:
    try:
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise ValueError("파일을 읽을 수 없어요. scripts.mfds export로 만든 파일인지 확인해 주세요.") from e
    rows = data.get("ingredients") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ValueError("성분 목록이 비어 있어요.")
    out = []
    for r in rows:
        if not isinstance(r, dict) or not str(r.get("name_ko") or "").strip():
            continue
        out.append({f: str(r.get(f) or "")[: (300 if f in ("name_ko", "name_en") else 200 if f == "cas_no" else 3000 if f == "restriction" else 20000)]
                    for f in FIELDS})
    if not out:
        raise ValueError("올바른 성분이 하나도 없어요.")
    return out


def replace_ingredients(db: Session, rows: list[dict]) -> int:
    from .scan import index  # 순환 import 방지
    db.execute(delete(Ingredient))
    db.add_all(Ingredient(**r) for r in rows)
    db.commit()
    index.reset()
    return len(rows)


# ---------- 식약처에서 직접 받기 (백그라운드) ----------

def _run_sync(products_only: bool = False) -> None:
    try:
        with SessionLocal() as db:
            for d in (() if products_only else ("ingredient", "restricted")):
                saved = 0
                for _page, total, items in mfds.iter_pages(d, 100):
                    saved += mfds.save_records(db, d, items)
                    job["message"] = f"{mfds.DATASETS[d][1]} {saved:,} / {total:,}건 받는 중"
            n = 0
            if not products_only:
                job["message"] = "성분 사전으로 정리하는 중"
                n = mfds.build_ingredients(db)
            n_prod = 0
            if products_only:
                # 기능성 화장품: 원본은 저장하지 않고 페이지마다 바로 제품으로 (이어 받기: job["resume"])
                for d in ("functional_review", "functional_report"):
                    start = job.get("resume", {}).get(d, 1)

                    def progress(page, total, added, d=d):
                        job.setdefault("resume", {})[d] = page + 1
                        job["message"] = f"{mfds.DATASETS[d][1]} {min(page * 100, total):,} / {total:,}건 확인 · 새 제품 {added:,}개"
                    try:
                        n_prod += mfds.sync_products(db, d, progress, start)
                    except mfds.MfdsError as e:
                        raise mfds.MfdsError(f"{mfds.DATASETS[d][1]}: {e} (다시 누르면 이어서 받아요)") from None
        from .scan import index
        index.reset()
        if products_only:
            job.pop("resume", None)
        job.update(state="done", message=(f"완료: 새 기능성 제품 {n_prod:,}개" if products_only else f"완료: 성분 {n:,}개"))
    except mfds.MfdsError as e:
        job.update(state="error", message=f"식약처 연결 실패: {e}. 해외 서버에서 막혔다면 '파일로 올리기'를 써 주세요.")
    except Exception as e:  # noqa: BLE001 - 관리자에게 원인을 보여주고 기록
        log.exception("mfds sync failed")
        job.update(state="error", message=f"오류: {type(e).__name__}")
    finally:
        job["finished_at"] = time.time()


# ---------- API ----------

@router.get("/status")
def status(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    count = lambda q: db.scalar(q) or 0  # noqa: E731
    raw = dict(db.execute(select(MfdsRecord.dataset, func.count()).group_by(MfdsRecord.dataset)).all())
    return {
        "ingredients": count(select(func.count()).select_from(Ingredient)),
        "restricted": count(select(func.count()).select_from(Ingredient).where(Ingredient.restriction != "")),
        "mfds_products": count(select(func.count()).select_from(Product).where(Product.source == SOURCE_MFDS)),
        "shared_lists": count(select(func.count()).select_from(ProductIngredientList)),
        "raw": {k: raw.get(k, 0) for k in mfds.DATASETS},
        "has_key": bool(env("DATA_GO_KR_SERVICE_KEY")),
        "job": job,
    }


@router.post("/mfds-probe")
def mfds_probe(_admin: User = Depends(require_admin)):
    """데이터셋마다 첫 페이지만 받아 연결과 필드 이름을 확인한다 (저장 안 함)."""
    out = {}
    for d in mfds.DATASETS:
        try:
            items, total = mfds.fetch_page(d, 1, 2)
            sample = {k: (str(v)[:120] if v is not None else None) for k, v in items[0].items()} if items else {}
            out[d] = {"ok": True, "total": total, "fields": sorted(items[0].keys()) if items else [], "sample": sample,
                      "url": mfds.dataset_url(d).split("?")[0]}
        except mfds.MfdsError as e:
            out[d] = {"ok": False, "error": str(e)[:300], "url": mfds.dataset_url(d).split("?")[0] if d in mfds.DEFAULT_URLS else ""}
    return out


@router.post("/mfds-sync", status_code=202)
def mfds_sync(products: bool = False, _admin: User = Depends(require_admin)):
    if not env("DATA_GO_KR_SERVICE_KEY"):
        raise HTTPException(400, "서버에 DATA_GO_KR_SERVICE_KEY가 설정되어 있지 않아요.")
    with _job_lock:
        if job["state"] == "running":
            raise HTTPException(409, "이미 받는 중이에요.")
        job.update(state="running", message="시작하는 중", started_at=time.time(), finished_at=None)
    threading.Thread(target=lambda: _run_sync(products), daemon=True, name="mfds-sync").start()
    return job


@router.get("/ingredients-export")
def ingredients_export(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return Response(export_ingredients(db), media_type="application/gzip",
                    headers={"Content-Disposition": 'attachment; filename="ruti-ingredients.json.gz"'})


@router.post("/ingredients-import")
async def ingredients_import(request: Request, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "파일이 비어 있어요.")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 커요.")
    if job["state"] == "running":
        raise HTTPException(409, "식약처에서 받는 중이에요. 끝난 뒤 다시 해 주세요.")
    try:
        rows = parse_ingredients(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    n = replace_ingredients(db, rows)
    return {"imported": n, "restricted": sum(1 for r in rows if r["restriction"])}


# ---------- 제품 전성분 일괄 등록 (앞면 사진·제품명으로 바로 찾게) ----------
# 붙여 넣기 형식 (제품마다):
#   브랜드 | 제품명
#   정제수, 글리세린, ... (여러 줄 가능)
# 또는 한 줄로:  브랜드 | 제품명 | 정제수, 글리세린, ...
ADMIN_CONFIRMATIONS = 5  # 관리자가 직접 확인한 목록은 사용자 1명 촬영보다 우선


class BulkIn(BaseModel):
    text: str = Field(min_length=1, max_length=400_000)
    dry_run: bool = True


def parse_bulk(text: str) -> list[dict]:
    from .scan import split_ingredients
    products: list[dict] = []
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            brand, name = (parts[0], parts[1]) if len(parts) >= 2 else ("", parts[0])
            cur = {"brand": brand[:150], "name": name[:200], "raw": " ".join(parts[2:])}
            products.append(cur)
        elif cur is not None:
            cur["raw"] += ("," if cur["raw"] else "") + line
    for p in products:
        p["ingredients"] = split_ingredients(p.pop("raw"))
    return products


@router.post("/product-lists")
def bulk_product_lists(payload: BulkIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from .scan import index, name_key, save_ingredient_list
    idx = index.get(db)
    out = []
    for p in parse_bulk(payload.text)[:500]:
        unknown = [n for n in p["ingredients"] if idx.lookup(n)[1] == "none"]
        problem = ("제품명이 없어요" if len(name_key("", p["name"])) < 2 else
                   "성분이 3개보다 적어요" if len(p["ingredients"]) < 3 else
                   "모르는 성분이 너무 많아요 (오타·줄바꿈 확인)" if len(unknown) > len(p["ingredients"]) * .5 else "")
        item = {"brand": p["brand"], "name": p["name"], "count": len(p["ingredients"]), "unknown": unknown[:10],
                "status": "error" if problem else ("ok" if payload.dry_run else "saved"), "message": problem}
        if not problem and not payload.dry_run:
            save_ingredient_list(db, admin, p["brand"], p["name"], p["ingredients"])
            row = db.scalar(select(ProductIngredientList).where(ProductIngredientList.name_key == name_key(p["brand"], p["name"]))
                            .order_by(ProductIngredientList.updated_at.desc()).limit(1))
            if row and row.confirmations < ADMIN_CONFIRMATIONS:
                row.confirmations = ADMIN_CONFIRMATIONS
                db.commit()
        out.append(item)
    if not out:
        raise HTTPException(400, "제품을 찾지 못했어요. '브랜드 | 제품명' 줄 다음에 전성분을 적어 주세요.")
    return {"dry_run": payload.dry_run, "products": out,
            "ok": sum(1 for i in out if i["status"] != "error"), "errors": sum(1 for i in out if i["status"] == "error")}


@router.get("/product-lists")
def list_product_lists(q: str = "", _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from .scan import name_key
    stmt = select(ProductIngredientList).order_by(ProductIngredientList.updated_at.desc()).limit(50)
    key = name_key("", q)
    if key:
        stmt = stmt.where(ProductIngredientList.name_key.contains(key))
    rows = db.scalars(stmt).all()
    return {"items": [{"id": r.id, "brand": r.brand, "name": r.name, "count": len(json.loads(r.ingredients)),
                       "confirmations": r.confirmations, "updated_at": r.updated_at.isoformat()} for r in rows]}


@router.delete("/product-lists/{list_id}")
def delete_product_list(list_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(ProductIngredientList, list_id)
    if not row:
        raise HTTPException(404, "없는 제품이에요.")
    db.delete(row)
    db.commit()
    return {"deleted": list_id}
