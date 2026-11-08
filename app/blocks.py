"""사용자 차단. 글·댓글·후기에서 작성자를 차단하면 그 사람의 콘텐츠가 내 화면에서 사라진다.
차단 사실은 상대에게 알리지 않는다."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Comment, Post, Review, User, UserBlock
from .security import current_user

router = APIRouter(prefix="/blocks", tags=["차단"])


def blocked_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(UserBlock.blocked_user_id).where(UserBlock.user_id == user.id)))


class BlockIn(BaseModel):
    target: str  # post | comment | review
    id: int


@router.post("", status_code=201)
def block(payload: BlockIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    model = {"post": Post, "comment": Comment, "review": Review}.get(payload.target)
    obj = db.get(model, payload.id) if model else None
    if not obj:
        raise HTTPException(404, "찾을 수 없어요.")
    if obj.user_id == user.id:
        raise HTTPException(400, "나 자신은 차단할 수 없어요.")
    if not db.scalar(select(UserBlock).where(UserBlock.user_id == user.id, UserBlock.blocked_user_id == obj.user_id)):
        db.add(UserBlock(user_id=user.id, blocked_user_id=obj.user_id))
        db.commit()
    return {"blocked": True}


@router.get("")
def my_blocks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(UserBlock.id, User.nickname, UserBlock.created_at).join(User, User.id == UserBlock.blocked_user_id)
                      .where(UserBlock.user_id == user.id).order_by(UserBlock.id.desc())).all()
    return {"blocks": [{"id": i, "nickname": n or "이름 없음", "created_at": c.isoformat()} for i, n, c in rows]}


@router.delete("/{block_id}")
def unblock(block_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(UserBlock, block_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "차단 기록을 찾을 수 없어요.")
    db.delete(row)
    db.commit()
    return {"unblocked": True}


def delete_user_blocks(db: Session, user_id: int) -> None:
    db.execute(delete(UserBlock).where((UserBlock.user_id == user_id) | (UserBlock.blocked_user_id == user_id)))
