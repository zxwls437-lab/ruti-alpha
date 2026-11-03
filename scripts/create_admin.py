"""관리자 계정 만들기 / 기존 계정에 관리자 권한 주기.

사용법:  python -m scripts.create_admin 아이디
"""
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import USERNAME_RE
from app.models import User
from app.security import hash_password


def main() -> None:
    if len(sys.argv) != 2 or not USERNAME_RE.match(sys.argv[1]):
        sys.exit("사용법: python -m scripts.create_admin 아이디  (영문/숫자/밑줄 3~30자)")
    username = sys.argv[1].lower()
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user:
            user.is_admin = True
            print(f"기존 계정 '{username}'에 관리자 권한을 주었습니다.")
        else:
            password = getpass.getpass("새 비밀번호 (8자 이상): ")
            if len(password) < 8 or password != getpass.getpass("비밀번호 확인: "):
                sys.exit("비밀번호가 너무 짧거나 서로 다릅니다.")
            db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
            print(f"관리자 계정 '{username}'을 만들었습니다.")
        db.commit()


if __name__ == "__main__":
    main()
