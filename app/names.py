"""식약처 제품명 띄어쓰기: '라운드랩1025독도선크림' → '라운드랩 1025독도선크림'.

식약처 기능성 화장품 이름은 대부분 붙여 써 있어 읽기 힘들다. 같은 회사(신고 회사)의 제품들이 함께 쓰는 앞부분은
대개 브랜드명이므로, 그 앞부분이 끝나는 곳(뒤 글자가 제품마다 달라지는 곳)에 한 칸을 띄운다. 화면 표시용이며 원래 이름은 그대로 둔다.
"""
import logging
import threading
from collections import Counter

from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from .models import SOURCE_MFDS, Product

MIN_SHARED = 3      # 같은 회사 제품 3개 이상이 같은 앞부분을 써야 브랜드로 본다
MAX_BRAND = 8       # 브랜드는 길어야 8글자
log = logging.getLogger("ruti")


def split_points(names: list[str]) -> dict[str, str]:
    """한 회사의 제품 이름들 → {원래 이름: 띄어 쓴 이름} (바꿀 게 없으면 빠짐)."""
    counts: Counter[str] = Counter()
    for n in set(names):
        for size in range(2, min(len(n), MAX_BRAND + 1) + 1):
            counts[n[:size]] += 1
    out: dict[str, str] = {}
    for n in set(names):
        if " " in n or len(n) < 5:
            continue
        for size in range(2, min(len(n) - 2, MAX_BRAND) + 1):
            here, nxt = counts[n[:size]], counts[n[:size + 1]]
            # 여기까지는 여러 제품이 같이 쓰고, 다음 글자부터 제품마다 갈라지면 = 브랜드 끝
            if here >= MIN_SHARED and nxt <= here * 0.7:
                if n[size - 1].isdigit() and n[size].isdigit():
                    break  # 숫자 중간은 자르지 않는다 (예: 1025)
                out[n] = n[:size] + " " + n[size:]
                break
    return out


def fill_display_names(db: Session, batch: int = 2000) -> int:
    """식약처 제품의 display_name을 채운다. 바꾼 개수를 돌려준다."""
    rows = db.execute(select(Product.id, Product.brand, Product.name).where(Product.source == SOURCE_MFDS)
                      .order_by(Product.brand)).all()
    by_brand: dict[str, list[tuple[int, str]]] = {}
    for pid, brand, name in rows:
        by_brand.setdefault(brand or "", []).append((pid, name))
    changes: list[dict] = []
    for items in by_brand.values():
        split = split_points([n for _, n in items])
        changes += [{"pid": pid, "dn": split[n][:220]} for pid, n in items if n in split]
    stmt = update(Product).where(Product.id == bindparam("pid")).values(display_name=bindparam("dn"))
    for i in range(0, len(changes), batch):
        db.connection().execute(stmt.execution_options(synchronize_session=False), changes[i:i + batch])
        db.commit()
    return len(changes)


def fill_in_background(session_factory) -> None:
    """서버 시작 때 아직 안 채워졌으면 뒤에서 한 번 채운다 (시작을 막지 않게). 운영 DB(PostgreSQL)에서만."""
    from .db import engine  # noqa: PLC0415
    if engine.dialect.name != "postgresql":
        return  # SQLite(개발·테스트)는 연결을 나눠 쓰므로 백그라운드로 건드리지 않는다

    def run() -> None:
        try:
            with session_factory() as db:
                pending = db.scalar(select(Product.id).where(Product.source == SOURCE_MFDS, Product.display_name == "").limit(1))
                done = db.scalar(select(Product.id).where(Product.source == SOURCE_MFDS, Product.display_name != "").limit(1))
                if pending and not done:
                    log.info("제품명 띄어쓰기: %s개 바꿈", fill_display_names(db))
        except Exception:  # noqa: BLE001  (표시용이라 실패해도 서비스엔 영향 없음)
            log.exception("제품명 띄어쓰기 실패")
    threading.Thread(target=run, daemon=True).start()


def shown(p: Product) -> str:
    return p.display_name or p.name
