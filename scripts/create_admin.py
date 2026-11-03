"""관리자 계정 만들기 / 기존 계정에 관리자 권한 주기 / 비밀번호 재설정.

사용법:  python -m scripts.create_admin 아이디
         python -m scripts.create_admin --list      (관리자 아이디 목록 보기)
기존 계정이면 관리자 권한을 주고, 새 비밀번호를 입력하면 비밀번호도 바꾼다(빈칸이면 유지).
"""
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import USERNAME_RE
from app.models import User
from app.security import hash_password


def ask_password(allow_blank: bool) -> str | None:
    password = getpass.getpass("새 비밀번호 (8자 이상" + (", 그대로 두려면 Enter" if allow_blank else "") + "): ")
    if allow_blank and not password:
        return None
    if len(password) < 8 or password != getpass.getpass("비밀번호 확인: "):
        sys.exit("비밀번호가 너무 짧거나 서로 다릅니다. 다시 실행해 주세요.")
    return password


def main() -> None:
    if sys.argv[1:] == ["--list"]:
        init_db()
        with SessionLocal() as db:
            names = db.scalars(select(User.username).where(User.is_admin.is_(True))).all()
        print("관리자 계정: " + (", ".join(names) if names else "없음"))
        return
    if len(sys.argv) != 2 or not USERNAME_RE.match(sys.argv[1]):
        sys.exit("사용법: python -m scripts.create_admin 아이디  (영문/숫자/밑줄 3~30자)")
    username = sys.argv[1].lower()
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user:
            password = ask_password(allow_blank=True)
            user.is_admin = True
            if password:
                user.password_hash = hash_password(password)
                print(f"계정 '{username}'의 비밀번호를 바꾸고 관리자 권한을 주었습니다.")
            else:
                print(f"기존 계정 '{username}'에 관리자 권한을 주었습니다 (비밀번호는 그대로).")
        else:
            password = ask_password(allow_blank=False)
            db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
            print(f"관리자 계정 '{username}'을 만들었습니다.")
        db.commit()


if __name__ == "__main__":
    main()
