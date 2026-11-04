from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow

PRODUCT_PENDING = "pending"
PRODUCT_APPROVED = "approved"
PRODUCT_REJECTED = "rejected"
SOURCE_MANUAL = "manual"   # 사람이 등록 → 관리자 승인 필요
SOURCE_MFDS = "mfds"       # 식약처 공공데이터 → 공식 출처라 자동 승인


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(150), default="")
    category: Mapped[str] = mapped_column(String(50), default="", index=True)
    # 쉼표로 구분: "건성,복합성"
    skin_types: Mapped[str] = mapped_column(String(200), default="")
    key_ingredients: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cautions: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default=PRODUCT_PENDING, index=True)
    source: Mapped[str] = mapped_column(String(20), default=SOURCE_MANUAL, index=True)
    external_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "skin_types": [s for s in self.skin_types.split(",") if s],
            "key_ingredients": self.key_ingredients,
            "description": self.description,
            "cautions": self.cautions,
            "source_url": self.source_url,
            "source": self.source,
        }

    def to_admin(self) -> dict:
        data = self.to_public()
        data.update(
            status=self.status,
            review_note=self.review_note,
            submitted_by=self.submitted_by,
            reviewed_by=self.reviewed_by,
            reviewed_at=self.reviewed_at.isoformat() if self.reviewed_at else None,
            created_at=self.created_at.isoformat() if self.created_at else None,
        )
        return data


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    product_ids: Mapped[str] = mapped_column(String(500), default="")  # "1,2"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Ingredient(Base):
    """화장품 성분 사전 (식약처 원료성분정보 + 사용제한 원료정보에서 만든다)."""
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(300), index=True)
    name_en: Mapped[str] = mapped_column(String(300), default="", index=True)
    cas_no: Mapped[str] = mapped_column(String(200), default="")
    synonyms: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    restriction: Mapped[str] = mapped_column(Text, default="")  # 비어 있으면 사용제한 원료 아님
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_public(self) -> dict:
        return {"id": self.id, "name_ko": self.name_ko, "name_en": self.name_en, "cas_no": self.cas_no,
                "synonyms": self.synonyms, "description": self.description, "restriction": self.restriction}


class MfdsRecord(Base):
    """공공데이터 API에서 받은 원본 그대로. 변환 규칙을 바꿔도 다시 받을 필요가 없게 보관한다."""
    __tablename__ = "mfds_records"
    __table_args__ = (UniqueConstraint("dataset", "record_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(50), index=True)
    record_key: Mapped[str] = mapped_column(String(200))
    data: Mapped[str] = mapped_column(Text)  # JSON
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScanResult(Base):
    """전성분 분석 기록. 사진은 저장하지 않고 인식된 성분 목록과 분석 결과만 남긴다."""
    __tablename__ = "scan_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(10))  # image | text
    product_name: Mapped[str] = mapped_column(String(200), default="")
    result: Mapped[str] = mapped_column(Text)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LlmUsage(Base):
    """AI 사용량 (하루·공급자·모델·용도별 합계)."""
    __tablename__ = "llm_usage"
    __table_args__ = (UniqueConstraint("day", "provider", "model", "purpose"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(30))
    calls: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    fallbacks: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
