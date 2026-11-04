"""RUTI API 서버: 회원/로그인, 사용자 기억, 제품 승인 워크플로, AI 상담, 화면(대시보드·상담·관리자)."""
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from . import account, ai, retrieval, scan
from .config import env, env_bool, env_int
from .db import SessionLocal, get_db, init_db, utcnow
from .models import PRODUCT_APPROVED, PRODUCT_PENDING, PRODUCT_REJECTED, SOURCE_MANUAL, ChatMessage, Ingredient, LlmUsage, Memory, Product, User
from .security import bearer, create_session, current_user, hash_password, limiter, require_admin, revoke_session, verify_password
from .status import STATUS

STATIC = Path(__file__).resolve().parent / "static"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


def bootstrap_admin() -> None:
    """RUTI_BOOTSTRAP_ADMIN_USERNAME/PASSWORD 환경 변수가 있으면 그 관리자 계정을 보장한다.
    서버 셸에 접속할 수 없는 클라우드(예: Render 무료)에서 관리자를 만들거나 비밀번호를 재설정할 때 쓴다."""
    username = env("RUTI_BOOTSTRAP_ADMIN_USERNAME").lower()
    password = env("RUTI_BOOTSTRAP_ADMIN_PASSWORD")
    if not username and not password:
        return
    if not USERNAME_RE.match(username) or len(password) < 8:
        print("[RUTI] 관리자 자동 생성 건너뜀: 아이디(영문/숫자 3~30자)와 비밀번호(8자 이상)를 확인하세요.")
        return
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
            print(f"[RUTI] 관리자 계정 '{username}'을 만들었습니다.")
        else:
            user.is_admin = True
            if not verify_password(password, user.password_hash):
                user.password_hash = hash_password(password)
                print(f"[RUTI] 관리자 계정 '{username}'의 비밀번호를 환경 변수 값으로 바꿨습니다.")
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    bootstrap_admin()
    yield


app = FastAPI(title="RUTI API", version="0.4.0", lifespan=lifespan)
app.include_router(scan.router)
app.include_router(account.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # 화면 파일은 항상 최신 버전을 확인하게 한다 (업데이트 후 옛 화면이 남아 오류 나는 것 방지)
    path = request.url.path
    if path in ("/", "/chat", "/scan", "/admin") or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- 요청/응답 모델 ----------

class SignupIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=30)
    nickname: str | None = None
    consents: dict[str, bool] = Field(default_factory=dict, description="age14, terms, privacy, sensitive(필수), marketing(선택)")

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력해 주세요.")
        return v

    @field_validator("nickname")
    @classmethod
    def check_nick(cls, v):
        return account.check_nickname(v) if v else None

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("아이디는 영문/숫자/밑줄 3~30자여야 합니다.")
        return v.lower()


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


def clean_skin_types(values: list[str]) -> list[str]:
    return [s.strip().replace(",", " ")[:30] for s in values if s.strip()]


def check_source_url(value: str) -> str:
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("source_url은 http:// 또는 https:// 로 시작해야 합니다.")
    return value


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=150)
    category: str = Field(default="", max_length=50)
    skin_types: list[str] = Field(default_factory=list, max_length=10)
    key_ingredients: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=4000)
    cautions: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=500)

    @field_validator("skin_types")
    @classmethod
    def v_skin_types(cls, v: list[str]) -> list[str]:
        return clean_skin_types(v)

    @field_validator("source_url")
    @classmethod
    def v_source_url(cls, v: str) -> str:
        return check_source_url(v)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=150)
    category: str | None = Field(default=None, max_length=50)
    skin_types: list[str] | None = None
    key_ingredients: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=4000)
    cautions: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=500)

    @field_validator("skin_types")
    @classmethod
    def v_skin_types(cls, v: list[str] | None) -> list[str] | None:
        return clean_skin_types(v) if v is not None else v

    @field_validator("source_url")
    @classmethod
    def v_source_url(cls, v: str | None) -> str | None:
        return check_source_url(v) if v is not None else v


class ReviewIn(BaseModel):
    note: str = Field(default="", max_length=1000)


class ConversationIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def apply_product_fields(item: Product, data: dict) -> None:
    for key, value in data.items():
        if key == "skin_types":
            value = ",".join(value or [])
        setattr(item, key, value)


# ---------- 화면 ----------

@app.get("/", include_in_schema=False)
def dashboard_page():
    return FileResponse(STATIC / "index.html")


@app.get("/chat", include_in_schema=False)
def chat_page():
    return FileResponse(STATIC / "chat.html")


@app.get("/scan", include_in_schema=False)
def scan_page():
    return FileResponse(STATIC / "scan.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/static/{name}", include_in_schema=False)
def static_file(name: str):
    if name not in {"common.css", "common.js"}:
        raise HTTPException(404)
    return FileResponse(STATIC / name)


# ---------- 상태 ----------

@app.get("/health", tags=["상태"])
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "service": "RUTI"}


@app.get("/status", tags=["상태"])
def status():
    return STATUS


# ---------- 회원/로그인 ----------

@app.post("/auth/signup", status_code=201, tags=["인증"])
def signup(payload: SignupIn, request: Request, db: Session = Depends(get_db)):
    if not env_bool("RUTI_ALLOW_SIGNUP", True):
        raise HTTPException(403, "현재 회원가입이 닫혀 있습니다.")
    if not limiter.hit(f"signup:{client_ip(request)}", env_int("RUTI_SIGNUP_RATE_PER_HOUR", 10), 3600):
        raise HTTPException(429, "잠시 후 다시 시도해 주세요.")
    account.validate_signup_consents(payload.consents)
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")
    if payload.nickname and account.nickname_taken(db, payload.nickname):
        raise HTTPException(409, "이미 사용 중인 닉네임이에요.")
    user = User(username=payload.username, password_hash=hash_password(payload.password), name=payload.name,
                nickname=payload.nickname or account.generate_nickname(db))
    db.add(user)
    db.flush()
    account.record_consents(db, user, {k: payload.consents.get(k, False) for k in account.CONSENT_KINDS})
    db.commit()
    return {"token": create_session(db, user), "user": account.user_public(db, user)}


@app.post("/auth/login", tags=["인증"])
def login(payload: LoginIn, db: Session = Depends(get_db)):
    username = payload.username.lower()
    if not limiter.hit(f"login:{username}", env_int("RUTI_LOGIN_RATE_PER_15MIN", 10), 900):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 15분 후 다시 시도해 주세요.")
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    return {"token": create_session(db, user), "user": account.user_public(db, user)}


@app.post("/auth/logout", tags=["인증"])
def logout(creds: HTTPAuthorizationCredentials | None = Depends(bearer), _user: User = Depends(current_user), db: Session = Depends(get_db)):
    revoke_session(db, creds.credentials)
    return {"logged_out": True}


@app.get("/auth/me", tags=["인증"])
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return account.user_public(db, user)


# ---------- 사용자 기억 ----------

@app.get("/memory", tags=["사용자 기억"])
def list_memories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.id)).all()
    return {"memories": [{"id": r.id, "content": r.content} for r in rows]}


@app.post("/memory", status_code=201, tags=["사용자 기억"])
def create_memory(payload: MemoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not account.has_sensitive_consent(db, user):
        raise HTTPException(403, "피부 정보를 저장하려면 '피부 상태 등 민감정보 처리'에 동의해 주세요.")
    count = db.scalar(select(func.count()).select_from(Memory).where(Memory.user_id == user.id))
    if count >= env_int("RUTI_MAX_MEMORIES", 50):
        raise HTTPException(400, "저장할 수 있는 기억 개수를 초과했습니다. 오래된 기억을 삭제해 주세요.")
    item = Memory(user_id=user.id, content=payload.content.strip())
    db.add(item)
    db.commit()
    return {"id": item.id, "content": item.content}


@app.delete("/memory/{memory_id}", tags=["사용자 기억"])
def delete_memory(memory_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Memory, memory_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "기억을 찾을 수 없습니다.")
    db.delete(item)
    db.commit()
    return {"deleted": True}


# ---------- 제품 ----------

_like = retrieval.like


@app.post("/products/stage", status_code=201, tags=["제품"])
def stage_product(payload: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """제품 제안. 항상 '검토 대기'로 저장되며 관리자 승인 전에는 검색/상담에 쓰이지 않는다."""
    item = Product(status=PRODUCT_PENDING, submitted_by=user.id)
    apply_product_fields(item, payload.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id, "name": item.name, "status": item.status}


@app.get("/products/search", tags=["제품"])
def search_products(q: str = "", category: str = "", skin_type: str = "", limit: int = 20, offset: int = 0,
                    _user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 100))
    stmt = select(Product).where(Product.status == PRODUCT_APPROVED)
    if q.strip():
        pattern = _like(q.strip())
        stmt = stmt.where(or_(*(col.ilike(pattern, escape="\\") for col in (
            Product.name, Product.brand, Product.category, Product.key_ingredients, Product.description))))
    if category.strip():
        stmt = stmt.where(Product.category == category.strip())
    if skin_type.strip():
        stmt = stmt.where(Product.skin_types.ilike(_like(skin_type.strip()), escape="\\"))
    rows = db.scalars(stmt.order_by(Product.id).limit(limit).offset(max(offset, 0))).all()
    return {"products": [r.to_public() for r in rows]}


@app.get("/ingredients/search", tags=["성분"])
def search_ingredients(q: str, limit: int = 20, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    """성분 사전 검색 (식약처 원료성분정보·사용제한 원료정보)."""
    q = q.strip()
    if not q:
        return {"ingredients": []}
    pattern = _like(q)
    stmt = (select(Ingredient)
            .where(or_(Ingredient.name_ko.ilike(pattern, escape="\\"), Ingredient.name_en.ilike(pattern, escape="\\"),
                       Ingredient.synonyms.ilike(pattern, escape="\\")))
            .order_by(func.length(Ingredient.name_ko), Ingredient.id).limit(max(1, min(limit, 100))))
    return {"ingredients": [i.to_public() for i in db.scalars(stmt).all()]}


@app.get("/products/{product_id}", tags=["제품"])
def get_product(product_id: int, _user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Product, product_id)
    if not item or item.status != PRODUCT_APPROVED:
        raise HTTPException(404, "제품을 찾을 수 없습니다.")
    return item.to_public()


# ---------- 관리자: 제품 검토 ----------

@app.get("/admin/products", tags=["관리자"])
def admin_list_products(status: str = PRODUCT_PENDING, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if status not in (PRODUCT_PENDING, PRODUCT_APPROVED, PRODUCT_REJECTED, "all"):
        raise HTTPException(400, "status는 pending/approved/rejected/all 중 하나입니다.")
    stmt = select(Product).order_by(Product.id)
    if status != "all":
        stmt = stmt.where(Product.status == status)
    return {"products": [r.to_admin() for r in db.scalars(stmt).all()]}


@app.patch("/admin/products/{product_id}", tags=["관리자"])
def admin_update_product(product_id: int, payload: ProductUpdate, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(Product, product_id)
    if not item:
        raise HTTPException(404, "제품을 찾을 수 없습니다.")
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    apply_product_fields(item, data)
    db.commit()
    return item.to_admin()


def _review(product_id: int, new_status: str, note: str, admin: User, db: Session) -> dict:
    item = db.get(Product, product_id)
    if not item:
        raise HTTPException(404, "제품을 찾을 수 없습니다.")
    if new_status == PRODUCT_APPROVED and item.source == SOURCE_MANUAL and not item.source_url:
        raise HTTPException(400, "근거 자료(source_url)가 없는 제품은 승인할 수 없습니다.")
    item.status, item.review_note = new_status, note
    item.reviewed_by, item.reviewed_at = admin.id, utcnow()
    db.commit()
    return item.to_admin()


@app.post("/admin/products/{product_id}/approve", tags=["관리자"])
def admin_approve(product_id: int, payload: ReviewIn = ReviewIn(), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _review(product_id, PRODUCT_APPROVED, payload.note, admin, db)


@app.post("/admin/products/{product_id}/reject", tags=["관리자"])
def admin_reject(product_id: int, payload: ReviewIn = ReviewIn(), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _review(product_id, PRODUCT_REJECTED, payload.note, admin, db)


@app.get("/admin/llm-usage", tags=["관리자"])
def admin_llm_usage(days: int = 7, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """AI 사용량·추정 비용 (최근 N일). 비용은 .env의 단가 기준 추정치."""
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=max(1, min(days, 90)) - 1)).isoformat()
    rows = db.scalars(select(LlmUsage).where(LlmUsage.day >= since).order_by(LlmUsage.day.desc(), LlmUsage.purpose)).all()
    items = [{"day": r.day, "provider": r.provider, "model": r.model, "purpose": r.purpose, "calls": r.calls, "cache_hits": r.cache_hits,
              "errors": r.errors, "fallbacks": r.fallbacks, "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
              "cost_usd": round(r.cost_usd, 6)} for r in rows]
    calls = sum(i["calls"] for i in items)
    return {"items": items, "total": {"calls": calls, "cache_hits": sum(i["cache_hits"] for i in items),
                                      "cost_usd": round(sum(i["cost_usd"] for i in items), 6),
                                      "cost_per_call_usd": round(sum(i["cost_usd"] for i in items) / calls, 6) if calls else 0}}


# ---------- AI 상담 ----------

def _ids_to_str(ids: list[int]) -> str:
    return ",".join(str(i) for i in ids)


def _str_to_ids(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.isdigit()]


@app.post("/conversation", tags=["AI 상담"])
def conversation(payload: ConversationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not limiter.hit(f"chat:{user.id}", env_int("RUTI_CHAT_RATE_PER_MIN", 10), 60):
        raise HTTPException(429, "질문이 너무 많아요. 1분 후 다시 시도해 주세요.")
    message = payload.message.strip()

    if ai.needs_safety_hold(message):
        result = ai.AIResult(ai.SAFETY_ANSWER, "safety_rule")
        status_code = "SAFETY_HOLD"
    else:
        memories = list(db.scalars(select(Memory.content).where(Memory.user_id == user.id).order_by(Memory.id.desc()).limit(20)).all())
        limit = env_int("RUTI_MAX_PRODUCTS_IN_PROMPT", 15)
        products = retrieval.candidate_products(db, message, memories, limit)
        ingredients = retrieval.ingredients_in_text(db, message + " " + " ".join(memories))
        turns = env_int("RUTI_HISTORY_TURNS", 6) * 2
        recent = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(turns)).all()
        history = [{"role": m.role, "content": m.content} for m in reversed(recent)]
        result = ai.generate_answer(message, memories[::-1], products, history, ingredients)
        status_code = "OK" if result.ok else "AI_UNAVAILABLE"

    # 상담 기록 저장 (AI 오류 응답은 다음 대화 맥락에 섞이지 않게 저장하지 않음)
    if status_code != "AI_UNAVAILABLE":
        db.add(ChatMessage(user_id=user.id, role="user", content=message))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=result.answer, product_ids=_ids_to_str(result.product_ids)))
        db.commit()

    cited = [db.get(Product, pid) for pid in result.product_ids]
    return {
        "status": status_code,
        "answer": result.answer,
        "engine": result.engine,
        "product_ids": result.product_ids,
        "products": [p.to_public() for p in cited if p and p.status == PRODUCT_APPROVED],
    }


@app.get("/conversation/history", tags=["AI 상담"])
def conversation_history(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    rows = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(limit)).all()
    all_ids = {pid for m in rows for pid in _str_to_ids(m.product_ids)}
    products = {p.id: p.to_public() for p in db.scalars(select(Product).where(Product.id.in_(all_ids), Product.status == PRODUCT_APPROVED)).all()} if all_ids else {}
    return {"messages": [
        {"role": m.role, "content": m.content, "products": [products[i] for i in _str_to_ids(m.product_ids) if i in products],
         "created_at": m.created_at.isoformat()}
        for m in reversed(rows)
    ]}


@app.delete("/conversation/history", tags=["AI 상담"])
def clear_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.commit()
    return {"deleted": True}
