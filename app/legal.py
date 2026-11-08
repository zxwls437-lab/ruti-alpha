"""개인정보 처리방침·이용약관·계정 삭제 안내 공개 페이지 (로그인 없이 열람, 구글 플레이 제출용 웹 주소).

운영자 이름·연락처는 환경 변수로 채운다. 출시 전 전문가 검토가 끝나면 RUTI_LEGAL_DRAFT=false.
"""
import html
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from .account import terms_version
from .config import env, env_bool

router = APIRouter(include_in_schema=False)
LEGAL = Path(__file__).resolve().parent / "legal"
PAGES = {"/privacy": "privacy.html", "/terms": "terms.html", "/account-deletion": "account-deletion.html"}
DRAFT_NOTE = ('<p class="draft">이 문서는 출시 전 검토 중인 초안이에요. 운영자 정보와 세부 내용은 '
              '정식 출시 때 확정돼요.</p>')


def render(name: str) -> str:
    values = {
        "OPERATOR": env("RUTI_OPERATOR_NAME", "[운영자 이름]"),
        "EMAIL": env("RUTI_CONTACT_EMAIL", "[문의 이메일]"),
        "OFFICER": env("RUTI_PRIVACY_OFFICER", "[개인정보 보호책임자]"),
        "HOSTING": env("RUTI_HOSTING_PROVIDER", "Render Services, Inc. (미국 법인 · 서버 위치 싱가포르)"),
        "VERSION": terms_version(),
    }
    text = (LEGAL / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", html.escape(value))
    return text.replace("{{DRAFT}}", DRAFT_NOTE if env_bool("RUTI_LEGAL_DRAFT", True) else "")


def _page(name: str):
    return lambda: HTMLResponse(render(name), headers={"Cache-Control": "public, max-age=600"})


for _path, _file in PAGES.items():
    router.add_api_route(_path, _page(_file), methods=["GET"])


@router.get("/legal/legal.css")
def legal_css():
    return FileResponse(LEGAL / "legal.css", media_type="text/css")
