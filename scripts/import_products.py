"""JSON 파일의 제품을 '검토 대기' 상태로 가져온다. 승인은 /admin 화면에서 사람이 한다.

사용법:  python -m scripts.import_products data/products_template.json
같은 브랜드+제품명이 이미 있으면 건너뛴다.
"""
import json
import sys

from pydantic import ValidationError
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import ProductIn, apply_product_fields
from app.models import PRODUCT_PENDING, Product


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("사용법: python -m scripts.import_products 파일.json")
    with open(sys.argv[1], encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        sys.exit("JSON 최상위는 제품 목록(배열)이어야 합니다.")
    init_db()
    added = skipped = failed = 0
    with SessionLocal() as db:
        for i, raw in enumerate(rows, 1):
            try:
                data = ProductIn.model_validate(raw).model_dump()
            except ValidationError as e:
                failed += 1
                print(f"[{i}] 오류: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
                continue
            exists = db.scalar(select(Product).where(Product.name == data["name"], Product.brand == data["brand"]))
            if exists:
                skipped += 1
                continue
            item = Product(status=PRODUCT_PENDING)
            apply_product_fields(item, data)
            db.add(item)
            added += 1
        db.commit()
    print(f"추가 {added}개 · 중복 건너뜀 {skipped}개 · 오류 {failed}개 (추가된 제품은 /admin 에서 승인해야 사용됩니다)")


if __name__ == "__main__":
    main()
