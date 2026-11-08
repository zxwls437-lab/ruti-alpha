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

def _run_sync() -> None:
    try:
        with SessionLocal() as db:
            for d in ("ingredient", "restricted"):
                saved = 0
                for _page, total, items in mfds.iter_pages(d, 100):
                    saved += mfds.save_records(db, d, items)
                    job["message"] = f"{mfds.DATASETS[d][1]} {saved:,} / {total:,}건 받는 중"
            job["message"] = "성분 사전으로 정리하는 중"
            n = mfds.build_ingredients(db)
            n_prod = 0
            for d in ("functional_report", "functional_review"):
                if env(mfds.DATASETS[d][0]):  # 주소(상세기능)가 설정된 기능성 제품 데이터만
                    try:
                        for _page, _total, items in mfds.iter_pages(d, 100):
                            mfds.save_records(db, d, items)
                    except mfds.MfdsError as e:
                        log.warning("기능성 제품 %s 실패: %s", d, e)
            n_prod = mfds.build_products(db)
        from .scan import index
        index.reset()
        job.update(state="done", message=f"완료: 성분 {n:,}개, 기능성 제품 {n_prod:,}개")
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


@router.post("/mfds-sync", status_code=202)
def mfds_sync(_admin: User = Depends(require_admin)):
    if not env("DATA_GO_KR_SERVICE_KEY"):
        raise HTTPException(400, "서버에 DATA_GO_KR_SERVICE_KEY가 설정되어 있지 않아요.")
    with _job_lock:
        if job["state"] == "running":
            raise HTTPException(409, "이미 받는 중이에요.")
        job.update(state="running", message="시작하는 중", started_at=time.time(), finished_at=None)
    threading.Thread(target=_run_sync, daemon=True, name="mfds-sync").start()
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
