from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import env


def utcnow() -> datetime:
    """모든 시각은 timezone 정보 없는 UTC로 저장한다 (SQLite/PostgreSQL 동일 동작)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_url(url: str) -> str:
    """클라우드가 주는 postgres:// 주소를 설치된 psycopg(3) 드라이버용으로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str):
    url = normalize_url(url)
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        # 메모리 DB는 연결마다 새 DB가 생기므로 하나의 연결을 공유해야 한다.
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


DATABASE_URL = env("DATABASE_URL", "sqlite:///./ruti.db")
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db


def init_db() -> None:
    from . import models  # noqa: F401  (테이블 등록)

    Base.metadata.create_all(engine)
    add_missing_columns()
    add_search_indexes()


def add_search_indexes() -> None:
    """PostgreSQL이면 제품명·회사명 부분 검색(ILIKE '%..%')을 빠르게 하는 trigram 색인을 만든다 (제품 약 20만 개)."""
    import logging

    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_name_trgm ON products USING gin (name gin_trgm_ops)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_brand_trgm ON products USING gin (brand gin_trgm_ops)"))
    except Exception:  # noqa: BLE001  (색인이 없어도 검색은 된다, 느릴 뿐)
        logging.getLogger("ruti").exception("검색 색인 만들기 실패")


def add_missing_columns() -> None:
    """이전 버전 DB에 새로 생긴 열을 추가한다 (간단한 자동 마이그레이션: 열 추가만)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                default = column.default.arg if column.default is not None and not callable(column.default.arg) else None
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'
                if default is not None:
                    ddl += " DEFAULT " + (f"'{default}'" if isinstance(default, str) else str(default))
                conn.execute(text(ddl))
