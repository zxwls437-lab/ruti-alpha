"""커뮤니티: 질문·자유 글·유튜브 영상 공유, 댓글, 도움돼요·신고, 영상 속 제품의 '내 피부 적합도' 표시."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import env_int
from .db import get_db
from .models import Comment, CommunityVote, Post, User
from .reviews import AUTO_HIDE_REPORTS, _my_tags, has_medical_claim, is_similar
from .scan import analyze, build_verdict, find_ingredient_list
from .security import current_user, limiter, require_admin

router = APIRouter(tags=["커뮤니티"])
KINDS = {"question": "질문", "talk": "이야기", "video": "영상"}
_YT = [re.compile(p) for p in (
    r"^https?://(?:www\.|m\.)?youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})",
    r"^https?://youtu\.be/([A-Za-z0-9_-]{11})",
    r"^https?://(?:www\.|m\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})",
)]


def youtube_id(url: str) -> str | None:
    url = url.strip()
    for pattern in _YT:
        m = pattern.match(url)
        if m:
            return m.group(1)
    return None


def _video(vid: str) -> dict | None:
    if not vid:
        return None
    return {"id": vid, "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "watch_url": f"https://www.youtube.com/watch?v={vid}", "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}"}


def _product_check(db: Session, viewer: User, product_name: str, memories: list[str]) -> dict | None:
    """글에 적힌 제품의 전성분이 RUTI에 있으면, 보는 사람 피부 기준 판정을 붙인다."""
    if not product_name:
        return None
    found = find_ingredient_list(db, "", product_name)
    if not found:
        return {"product_name": product_name, "found": False}
    result = analyze(db, json.loads(found.ingredients), memories)
    v = build_verdict(result, memories)
    return {"product_name": product_name, "found": True, "level": v["level"], "title": v["title"]}


def _blocked(db: Session, user: User) -> set[int]:
    from .blocks import blocked_ids  # 순환 import 방지
    return blocked_ids(db, user)


def _memories(db: Session, user: User) -> list[str]:
    from .account import has_sensitive_consent
    from .models import Memory
    if not has_sensitive_consent(db, user):
        return []
    return list(db.scalars(select(Memory.content).where(Memory.user_id == user.id)))


def _post_view(db: Session, p: Post, author: User | None, viewer: User, helpful: set[int], memories: list[str]) -> dict:
    return {
        "id": p.id, "kind": p.kind, "kind_label": KINDS[p.kind], "title": p.title, "body": p.body,
        "video": _video(p.video_id), "sponsored": p.sponsored, "product_name": p.product_name,
        "product_check": _product_check(db, viewer, p.product_name, memories),
        "medical_claim": p.medical_claim,
        "author": author.nickname if author and author.nickname else "탈퇴한 사용자",
        "skin_tags": [t for t in p.skin_tags.split(",") if t] if p.show_skin else [],
        "helpful_count": p.helpful_count, "helpful_by_me": p.id in helpful, "comment_count": p.comment_count,
        "mine": p.user_id == viewer.id, "created_at": p.created_at.isoformat(),
    }


def _helpful_set(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(CommunityVote.target_id).where(CommunityVote.user_id == user.id, CommunityVote.target == "post",
                                                               CommunityVote.kind == "helpful")))


# ---------- 글 ----------

class PostIn(BaseModel):
    kind: str
    title: str = Field(min_length=2, max_length=100)
    body: str = Field(default="", max_length=3000)
    video_url: str = Field(default="", max_length=300)
    sponsored: bool | None = None
    product_name: str = Field(default="", max_length=200)
    show_skin: bool = True

    @field_validator("kind")
    @classmethod
    def v_kind(cls, v: str) -> str:
        if v not in KINDS:
            raise ValueError("kind는 question/talk/video 중 하나예요.")
        return v

    @field_validator("title", "body", "product_name", "video_url")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


@router.post("/community/posts", status_code=201)
def create_post(payload: PostIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    vid = ""
    if payload.kind == "video":
        vid = youtube_id(payload.video_url) or ""
        if not vid:
            raise HTTPException(422, "유튜브 영상 주소를 확인해 주세요 (youtube.com, youtu.be, 쇼츠 주소).")
        if payload.sponsored is None:
            raise HTTPException(422, "영상에 협찬·광고가 포함됐는지 선택해 주세요.")
    elif len(payload.body) < 5:
        raise HTTPException(422, "내용을 5자 이상 적어 주세요.")
    if not limiter.hit(f"post:{user.id}", env_int("RUTI_POSTS_PER_DAY", 20), 86400):
        raise HTTPException(429, "오늘 쓸 수 있는 글 수를 넘었어요.")
    post = Post(user_id=user.id, kind=payload.kind, title=payload.title, body=payload.body, video_id=vid,
                sponsored=bool(payload.sponsored), product_name=payload.product_name, show_skin=payload.show_skin,
                medical_claim=has_medical_claim(payload.title + " " + payload.body), skin_tags=",".join(_my_tags(db, user)))
    db.add(post)
    db.commit()
    notices = ["'치료·완치·나았다' 같은 의약품 표현은 화장품 이야기에 쓰지 말아 주세요. 다른 분들께 오해를 줄 수 있어요."] if post.medical_claim else []
    return {"post": _post_view(db, post, user, user, set(), _memories(db, user)), "notices": notices}


@router.get("/community/posts")
def list_posts(kind: str = "", similar: bool = False, limit: int = 20, offset: int = 0,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Post).where(Post.hidden.is_(False)).order_by(Post.id.desc())
    if kind:
        if kind not in KINDS:
            raise HTTPException(400, "kind는 question/talk/video 중 하나예요.")
        stmt = stmt.where(Post.kind == kind)
    rows = list(db.scalars(stmt.limit(500)))
    hidden_authors = _blocked(db, user)
    rows = [p for p in rows if p.user_id not in hidden_authors]
    if similar:
        mine = set(_my_tags(db, user))
        rows = [p for p in rows if is_similar(mine, set(p.skin_tags.split(",")) - {""})]
    total = len(rows)
    rows = rows[max(offset, 0): max(offset, 0) + max(1, min(limit, 50))]
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_({p.user_id for p in rows})))} if rows else {}
    helpful, memories = _helpful_set(db, user), _memories(db, user)
    return {"total": total, "posts": [_post_view(db, p, authors.get(p.user_id), user, helpful, memories) for p in rows]}


def _visible_post(db: Session, post_id: int) -> Post:
    p = db.get(Post, post_id)
    if not p or p.hidden:
        raise HTTPException(404, "글을 찾을 수 없어요.")
    return p


@router.get("/community/posts/{post_id}")
def get_post(post_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _visible_post(db, post_id)
    if p.user_id in _blocked(db, user):
        raise HTTPException(404, "글을 찾을 수 없어요.")
    hidden_authors = _blocked(db, user)
    comments = [c for c in db.scalars(select(Comment).where(Comment.post_id == p.id, Comment.hidden.is_(False)).order_by(Comment.id))
                if c.user_id not in hidden_authors]
    ids = {p.user_id} | {c.user_id for c in comments}
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
    nick = lambda uid: authors[uid].nickname if uid in authors and authors[uid].nickname else "탈퇴한 사용자"
    return {"post": _post_view(db, p, authors.get(p.user_id), user, _helpful_set(db, user), _memories(db, user)),
            "comments": [{"id": c.id, "author": nick(c.user_id), "body": c.body, "medical_claim": c.medical_claim,
                          "mine": c.user_id == user.id, "is_post_author": c.user_id == p.user_id, "created_at": c.created_at.isoformat()}
                         for c in comments]}


@router.delete("/community/posts/{post_id}")
def delete_post(post_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Post, post_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "글을 찾을 수 없어요.")
    _purge_post(db, p)
    db.commit()
    return {"deleted": True}


def _purge_post(db: Session, p: Post) -> None:
    cids = list(db.scalars(select(Comment.id).where(Comment.post_id == p.id)))
    if cids:
        db.execute(delete(CommunityVote).where(CommunityVote.target == "comment", CommunityVote.target_id.in_(cids)))
    db.execute(delete(Comment).where(Comment.post_id == p.id))
    db.execute(delete(CommunityVote).where(CommunityVote.target == "post", CommunityVote.target_id == p.id))
    db.delete(p)


# ---------- 댓글 ----------

class CommentIn(BaseModel):
    body: str = Field(min_length=2, max_length=1000)


@router.post("/community/posts/{post_id}/comments", status_code=201)
def add_comment(post_id: int, payload: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _visible_post(db, post_id)
    if not limiter.hit(f"comment:{user.id}", env_int("RUTI_COMMENTS_PER_DAY", 100), 86400):
        raise HTTPException(429, "오늘 쓸 수 있는 댓글 수를 넘었어요.")
    c = Comment(post_id=p.id, user_id=user.id, body=payload.body.strip(), medical_claim=has_medical_claim(payload.body))
    db.add(c)
    p.comment_count += 1
    db.commit()
    return {"id": c.id, "body": c.body, "medical_claim": c.medical_claim}


@router.delete("/community/comments/{comment_id}")
def delete_comment(comment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Comment, comment_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "댓글을 찾을 수 없어요.")
    post = db.get(Post, c.post_id)
    if post:
        post.comment_count = max(0, post.comment_count - 1)
    db.execute(delete(CommunityVote).where(CommunityVote.target == "comment", CommunityVote.target_id == c.id))
    db.delete(c)
    db.commit()
    return {"deleted": True}


# ---------- 도움돼요·신고 ----------

@router.post("/community/posts/{post_id}/helpful")
def toggle_post_helpful(post_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _visible_post(db, post_id)
    if p.user_id == user.id:
        raise HTTPException(400, "내 글에는 누를 수 없어요.")
    vote = db.scalar(select(CommunityVote).where(CommunityVote.user_id == user.id, CommunityVote.target == "post",
                                                 CommunityVote.target_id == p.id, CommunityVote.kind == "helpful"))
    if vote:
        db.delete(vote)
    else:
        db.add(CommunityVote(user_id=user.id, target="post", target_id=p.id, kind="helpful"))
    db.flush()
    p.helpful_count = db.scalar(select(func.count()).select_from(CommunityVote).where(
        CommunityVote.target == "post", CommunityVote.target_id == p.id, CommunityVote.kind == "helpful"))
    db.commit()
    return {"helpful_by_me": vote is None, "helpful_count": p.helpful_count}


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


@router.post("/community/{target}/{target_id}/report")
def report(target: str, target_id: int, payload: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    model = {"posts": Post, "comments": Comment}.get(target)
    if not model:
        raise HTTPException(404)
    obj = db.get(model, target_id)
    if not obj or obj.hidden:
        raise HTTPException(404, "찾을 수 없어요.")
    if obj.user_id == user.id:
        raise HTTPException(400, "내 글은 신고할 수 없어요.")
    kind_target = "post" if model is Post else "comment"
    if db.scalar(select(CommunityVote).where(CommunityVote.user_id == user.id, CommunityVote.target == kind_target,
                                             CommunityVote.target_id == obj.id, CommunityVote.kind == "report")):
        return {"reported": True, "already": True}
    db.add(CommunityVote(user_id=user.id, target=kind_target, target_id=obj.id, kind="report", reason=payload.reason.strip()))
    obj.report_count += 1
    if obj.report_count >= AUTO_HIDE_REPORTS:
        obj.hidden = True
    db.commit()
    return {"reported": True, "already": False}


# ---------- 관리자 ----------

@router.get("/admin/community", tags=["관리자"])
def admin_community(status: str = "reported", _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if status not in ("reported", "hidden", "medical"):
        raise HTTPException(400, "status는 reported/hidden/medical 중 하나예요.")
    out = []
    for model, target in ((Post, "post"), (Comment, "comment")):
        stmt = select(model)
        stmt = {"reported": stmt.where(model.report_count > 0), "hidden": stmt.where(model.hidden.is_(True)),
                "medical": stmt.where(model.medical_claim.is_(True))}[status]
        for obj in db.scalars(stmt.order_by(model.report_count.desc()).limit(100)):
            reasons = list(db.scalars(select(CommunityVote.reason).where(CommunityVote.target == target, CommunityVote.target_id == obj.id,
                                                                         CommunityVote.kind == "report")))
            out.append({"target": target, "id": obj.id, "title": getattr(obj, "title", ""), "body": obj.body, "hidden": obj.hidden,
                        "report_count": obj.report_count, "report_reasons": reasons, "medical_claim": obj.medical_claim})
    return {"items": out}


@router.post("/admin/community/{target}/{target_id}/{action}", tags=["관리자"])
def admin_community_action(target: str, target_id: int, action: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = {"post": Post, "comment": Comment}.get(target)
    obj = db.get(model, target_id) if model else None
    if not obj:
        raise HTTPException(404, "찾을 수 없어요.")
    if action == "hide":
        obj.hidden = True
    elif action == "restore":
        obj.hidden, obj.report_count = False, 0
        db.execute(delete(CommunityVote).where(CommunityVote.target == target, CommunityVote.target_id == obj.id, CommunityVote.kind == "report"))
    elif action == "delete":
        if model is Post:
            _purge_post(db, obj)
        else:
            post = db.get(Post, obj.post_id)
            if post:
                post.comment_count = max(0, post.comment_count - 1)
            db.execute(delete(CommunityVote).where(CommunityVote.target == "comment", CommunityVote.target_id == obj.id))
            db.delete(obj)
    else:
        raise HTTPException(400, "action은 hide/restore/delete 중 하나예요.")
    db.commit()
    return {"ok": True}


def delete_user_content(db: Session, user_id: int) -> None:
    """회원 탈퇴 시 글·댓글·투표 삭제."""
    for p in list(db.scalars(select(Post).where(Post.user_id == user_id))):
        _purge_post(db, p)
    for c in list(db.scalars(select(Comment).where(Comment.user_id == user_id))):
        post = db.get(Post, c.post_id)
        if post:
            post.comment_count = max(0, post.comment_count - 1)
        db.execute(delete(CommunityVote).where(CommunityVote.target == "comment", CommunityVote.target_id == c.id))
        db.delete(c)
    db.execute(delete(CommunityVote).where(CommunityVote.user_id == user_id))
    from .blocks import delete_user_blocks
    delete_user_blocks(db, user_id)
