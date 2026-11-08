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
    name: Mapped[str] = mapped_column(String(50), default="")          # RUTI가 불러주는 이름 (다른 사람에게 안 보임)
    nickname: Mapped[str] = mapped_column(String(30), default="", index=True)  # 커뮤니티에서 보이는 이름
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str] = mapped_column(String(10), default="free")         # free | plus
    plus_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)  # 마지막 접속 (1분 단위)


class Consent(Base):
    """동의 기록 (추가만 하는 이력). 종류별 가장 최근 기록이 현재 상태다."""
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))       # age14 | terms | privacy | sensitive | marketing
    agreed: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(30))    # 동의한 약관 버전
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


class ProductIngredientList(Base):
    """사용자들이 뒷면을 찍어 함께 채우는 제품별 전성분 (앞면 사진으로 찾을 때 사용).
    같은 제품에 같은 목록이 다시 등록되면 confirmations가 올라가 신뢰도가 높아진다. 개인정보는 저장하지 않는다."""
    __tablename__ = "product_ingredient_lists"
    __table_args__ = (UniqueConstraint("name_key", "list_hash"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(String(150), default="")
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(400), index=True)
    ingredients: Mapped[str] = mapped_column(Text)  # JSON 배열
    list_hash: Mapped[str] = mapped_column(String(64))
    confirmations: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Review(Base):
    """사용 후기. 제품은 브랜드+제품명 정규화 키(name_key)로 묶는다 (제품별 전성분과 같은 방식)."""
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("user_id", "name_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    brand: Mapped[str] = mapped_column(String(150), default="")
    product_name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(400), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    felt_moisture: Mapped[bool] = mapped_column(Boolean, default=False)    # 보습이 만족스러웠어요
    felt_irritation: Mapped[bool] = mapped_column(Boolean, default=False)  # 자극을 느꼈어요
    would_rebuy: Mapped[bool] = mapped_column(Boolean, default=False)      # 다시 살 거예요
    sponsored: Mapped[bool] = mapped_column(Boolean, default=False)        # 협찬·체험단 (광고 포함)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)         # 이 제품을 사진 분석한 기록이 있음
    medical_claim: Mapped[bool] = mapped_column(Boolean, default=False)    # 의약품식 표현 (통계 제외)
    skin_tags: Mapped[str] = mapped_column(String(200), default="")        # 작성 당시 피부 정보 "건성,민감성"
    show_skin: Mapped[bool] = mapped_column(Boolean, default=True)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewVote(Base):
    """도움돼요·신고 (1인 1회)."""
    __tablename__ = "review_votes"
    __table_args__ = (UniqueConstraint("user_id", "review_id", "kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # helpful | report
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VanityItem(Base):
    """내 화장대: 가지고 있는(쓰는) 제품과 전성분."""
    __tablename__ = "vanity_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    ingredients: Mapped[str] = mapped_column(Text)  # JSON 배열
    scan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Post(Base):
    """커뮤니티 글: 질문(question) · 자유(talk) · 유튜브 영상 공유(video)."""
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text, default="")
    video_id: Mapped[str] = mapped_column(String(20), default="")   # 유튜브 영상 ID (영상은 저장하지 않음)
    sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    product_name: Mapped[str] = mapped_column(String(200), default="")
    medical_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    skin_tags: Mapped[str] = mapped_column(String(200), default="")
    show_skin: Mapped[bool] = mapped_column(Boolean, default=True)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    medical_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CommunityVote(Base):
    """글·댓글 도움돼요·신고 (1인 1회)."""
    __tablename__ = "community_votes"
    __table_args__ = (UniqueConstraint("user_id", "target", "target_id", "kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target: Mapped[str] = mapped_column(String(10))   # post | comment
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))     # helpful | report
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserBlock(Base):
    """사용자 차단: 차단한 사람의 글·댓글·후기를 내 화면에서 숨긴다 (구글 플레이 UGC 정책 필수 기능)."""
    __tablename__ = "user_blocks"
    __table_args__ = (UniqueConstraint("user_id", "blocked_user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
