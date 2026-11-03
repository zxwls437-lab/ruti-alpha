"""식약처 공공데이터 가져오기 도구.

사용법 (PowerShell, RUTI 폴더에서):
  python -m scripts.mfds probe 데이터셋       API 연결 확인 + 필드 이름 보기 (저장 안 함)
  python -m scripts.mfds fetch 데이터셋       전체 다운로드 → 원본 저장   (--max-pages 5 로 일부만)
  python -m scripts.mfds fetch all            .env에 주소가 있는 데이터셋 전부
  python -m scripts.mfds build                원본 → 성분 사전 / 기능성 제품으로 변환
  python -m scripts.mfds status               저장된 개수 보기

데이터셋: ingredient, restricted, functional_report, functional_review, cosmetics_info
"""
import json
import sys

from sqlalchemy import func, select

from app.config import env
from app.db import SessionLocal, init_db
from app.mfds import DATASETS, MfdsError, build_ingredients, build_products, fetch_page, iter_pages, save_records
from app.models import SOURCE_MFDS, Ingredient, MfdsRecord, Product


def probe(dataset: str) -> None:
    items, total = fetch_page(dataset, 1, 3)
    print(f"[{DATASETS[dataset][1]}] 연결 성공 · 전체 {total:,}건\n")
    if not items:
        print("항목이 비어 있습니다.")
        return
    print("필드 이름과 예시 값 (첫 번째 항목):")
    for k, v in items[0].items():
        print(f"  {k}: {str(v)[:60]!r}")


def fetch(dataset: str, max_pages: int) -> None:
    targets = [d for d in DATASETS if env(DATASETS[d][0])] if dataset == "all" else [dataset]
    if not targets:
        raise MfdsError(".env에 요청주소(MFDS_..._URL)가 하나도 없습니다.")
    with SessionLocal() as db:
        for d in targets:
            saved = 0
            for page, total, items in iter_pages(d, 100, max_pages):
                saved += save_records(db, d, items)
                print(f"\r[{DATASETS[d][1]}] {saved:,} / {total:,}", end="", flush=True)
            print(f"\n[{DATASETS[d][1]}] 저장 완료 {saved:,}건")


def build() -> None:
    with SessionLocal() as db:
        n_ing = build_ingredients(db)
        n_prod = build_products(db)
    print(f"성분 사전 {n_ing:,}개, 기능성 제품 {n_prod:,}개로 변환했습니다.")


def status() -> None:
    with SessionLocal() as db:
        for d, (_var, label) in DATASETS.items():
            n = db.scalar(select(func.count()).select_from(MfdsRecord).where(MfdsRecord.dataset == d))
            print(f"  원본 {label}: {n:,}건")
        n_ing = db.scalar(select(func.count()).select_from(Ingredient))
        n_res = db.scalar(select(func.count()).select_from(Ingredient).where(Ingredient.restriction != ""))
        n_prod = db.scalar(select(func.count()).select_from(Product).where(Product.source == SOURCE_MFDS))
        print(f"  성분 사전: {n_ing:,}개 (사용제한 {n_res:,}개) · 식약처 기능성 제품: {n_prod:,}개")


def main() -> None:
    args = sys.argv[1:]
    max_pages = 0
    if "--max-pages" in args:
        i = args.index("--max-pages")
        max_pages = int(args[i + 1])
        del args[i:i + 2]
    init_db()
    try:
        if len(args) == 2 and args[0] == "probe":
            probe(args[1])
        elif len(args) == 2 and args[0] == "fetch":
            fetch(args[1], max_pages)
        elif args == ["build"]:
            build()
        elif args == ["status"]:
            status()
        else:
            print(__doc__)
    except MfdsError as e:
        sys.exit(f"오류: {e}")
    except KeyboardInterrupt:
        sys.exit("\n중단했습니다. 지금까지 받은 데이터는 저장되어 있습니다.")


if __name__ == "__main__":
    main()
