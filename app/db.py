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
