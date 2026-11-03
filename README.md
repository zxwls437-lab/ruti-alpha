# RUTI 통합 예제 — 개발 현황 대시보드 + FastAPI 백엔드

> **중요:** 기존 사용자 PC의 원본 프로젝트를 직접 복제한 것이 아닙니다. 2026-10-16까지 확인된 작업 기록을 바탕으로 만든 **독립 실행형 참고 프로젝트**입니다. 기존 폴더를 덮어쓰지 마세요.

## 포함 기능
- `/` : RUTI 개발 현황 대시보드 (35%는 추정치, 2026-10-16 기준)
- `/health`, `/status`, `/docs` : 상태/개발 정보/API 문서
- `/memory` : 사용자 기억 조회·추가, `/memory/{id}` : 삭제
- `/products/stage` : 미승인 제품 등록, `/products/search` : 승인 제품만 검색
- `/conversation` : 안전 문구 검사, 사용자 기억 및 승인 제품을 참고한 AI 상담
- OpenAI API 키가 없거나 크레딧이 부족해도 서버와 대시보드 작동

## Windows PowerShell 실행

1. ZIP을 **기존 프로젝트와 다른 폴더**에 압축 해제하세요.
2. 해당 폴더에서 PowerShell을 열고 아래 명령을 **하나씩** 실행하세요.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. 브라우저에서 `http://127.0.0.1:8000/` (대시보드) 및 `http://127.0.0.1:8000/docs` (API 문서)를 여세요.

**포트 8000을 기존 RUTI 서버가 사용 중이라면** 마지막 명령의 `--port 8000`을 `--port 8001`로 변경하세요.

## 데이터베이스
기본값은 별도 설치가 필요 없는 **SQLite (`ruti.db`)** 입니다. 기존 PostgreSQL을 사용하려면 `.env`의 `DATABASE_URL`을 설정할 수 있지만, **기존 RUTI 데이터베이스에 바로 연결하지 마세요.** 이 예제의 테이블 정의가 기존 DB와 다를 수 있습니다. 새 테스트 DB를 사용하세요.

## 인증
`.env`의 `RUTI_API_TOKEN` 값을 바꾸세요. 개발 테스트용 기본값은 `change-this-local-token`입니다. 보호된 API 호출에는 `Authorization: Bearer <토큰>` 및 `x-ruti-user: testuser1` 헤더가 필요합니다. 이 헤더 방식은 **로컬 테스트용**이며 실제 서비스의 로그인/인증을 대체하지 않습니다.

## AI 설정
`.env`에 `OPENAI_API_KEY`를 설정하거나 실행 프로세스의 환경 변수로 주입하세요. API 키는 공유하거나 Git에 커밋하지 마세요. OpenAI API 사용에는 별도 과금이 발생할 수 있습니다. 크레딧이 없는 경우 AI 호출을 반복하지 마세요.

## 테스트
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 실제 출시 전에 필요한 작업
- 사용자 계정 기반 인증, 권한 및 데이터 격리 강화
- 제품 근거 검증 및 승인 워크플로 구축
- 프롬프트 인젝션 대응, 안전성/품질 평가, 민감정보 보호
- 운영 DB 마이그레이션, 백업, 모니터링, 사용량 제한
- AI 응답의 제품 ID/추천 근거 검증 및 실제 사용자 UI 구현

## 주요 파일
- `app/main.py`: FastAPI 백엔드
- `app/static/index.html`: 반응형 개발 현황 대시보드
- `tests/test_api.py`: 기본 API 테스트
- `.env.example`: 환경 설정 예시
