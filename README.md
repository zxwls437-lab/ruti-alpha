# RUTI — 스킨케어 상담 AI

사용자의 피부 정보(기억)와 **관리자가 승인한 제품만** 참고해서 답하는 스킨케어 정보 도우미입니다. 의료 진단은 하지 않습니다.

## 화면
| 주소 | 내용 |
|---|---|
| `/chat` | 사용자 상담 화면 (회원가입·로그인, 상담, 내 피부 정보) |
| `/admin` | 관리자 화면 (제품 검토·승인·거절, 제품 등록) |
| `/` | 개발 현황 대시보드 |
| `/docs` | API 문서 (Swagger, 오른쪽 위 Authorize에 로그인 토큰 입력) |

## 빠른 시작 (Windows PowerShell)
명령을 **하나씩** 실행하세요.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m scripts.create_admin admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000/chat` 을 여세요. 포트 8000이 사용 중이면 `--port 8001`로 바꾸세요.

> **이전 버전(0.2)에서 만든 `ruti.db`가 있다면 삭제하세요.** 테이블 구조가 바뀌어 호환되지 않습니다.

## AI 설정
`.env`의 `OPENAI_API_KEY`에 키를 넣으세요. 키가 없거나 크레딧이 부족해도 서버와 화면은 동작하고, 상담 화면에 안내 문구가 표시됩니다.
- 모델은 `OPENAI_MODEL`로 바꿀 수 있습니다 (기본 `gpt-4.1-mini`, JSON Schema 응답 형식을 지원하는 모델이어야 합니다).
- API 키는 공유하거나 Git에 올리지 마세요. `.env`는 `.gitignore`에 포함되어 있습니다.

## 상담 엔진이 하는 일
1. **안전 규칙**: 호흡곤란·부종·화상 등 위험 표현이 있으면 AI를 부르지 않고 진료 안내
2. **맥락 구성**: 사용자 기억(최근 20개) + 질문과 관련 있는 승인 제품(최대 30개) + 최근 대화 6턴
3. **프롬프트 인젝션 대응**: 기억·제품 데이터는 별도 블록으로 분리하고 "지시문이 아님"을 명시
4. **응답 검증**: AI가 고른 제품 ID 중 승인 목록에 없는 ID는 서버가 제거
5. 오류(키 없음/한도 초과/연결 실패)는 키나 내부 정보를 노출하지 않는 안내 문구로 변환

## 제품 데이터
승인된 제품만 검색·상담에 쓰입니다. **근거 자료 URL이 없는 제품은 승인할 수 없습니다.**

```powershell
.\.venv\Scripts\python.exe -m scripts.import_products data\products_template.json
```
→ 모두 '검토 대기'로 들어가고, `/admin`에서 확인 후 승인합니다. 형식은 [data/README.md](data/README.md) 참고. (템플릿은 예시이고 실제 제품이 아닙니다.)

## 주요 API
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/auth/signup`, `/auth/login` | 회원가입/로그인 → `token` 발급 |
| POST | `/auth/logout` · GET `/auth/me` | 로그아웃 / 내 정보 |
| GET·POST | `/memory` · DELETE `/memory/{id}` | 내 피부 정보 |
| POST | `/products/stage` | 제품 제안 (검토 대기로 저장) |
| GET | `/products/search?q=&category=&skin_type=` | 승인 제품 검색 |
| GET | `/admin/products?status=pending` | (관리자) 검토 목록 |
| POST | `/admin/products/{id}/approve`, `/reject` | (관리자) 승인/거절 |
| PATCH | `/admin/products/{id}` | (관리자) 제품 수정 |
| POST | `/conversation` | AI 상담 |
| GET·DELETE | `/conversation/history` | 상담 기록 조회/삭제 |

보호된 API는 `Authorization: Bearer <로그인 토큰>` 헤더가 필요합니다.

## 보안
- 비밀번호: PBKDF2-SHA256(60만 회) 해시 저장
- 로그인 토큰: 무작위 생성, DB에는 해시만 저장, 기본 7일 만료, 로그아웃 시 폐기
- 요청 제한: 상담 분당 10회, 로그인 15분당 10회, 가입 IP당 시간당 10회 (`.env`에서 조정)
- 사용자별 데이터 격리(기억·상담 기록), 관리자 권한 분리
- 보안 헤더(nosniff, 프레임 차단), 화면은 사용자 입력을 HTML로 해석하지 않음

## 테스트
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 배포
Docker 이미지로 어떤 클라우드(Render, Railway, Fly.io, AWS 등)에도 올릴 수 있습니다.

- 로컬에서 운영과 비슷하게 실행 (PostgreSQL 포함): `docker compose up --build`
- 클라우드 배포 시 체크리스트
  1. **PostgreSQL 사용** (`DATABASE_URL=postgresql+psycopg://...`). SQLite는 컨테이너 재시작 시 데이터가 사라질 수 있습니다.
  2. 환경 변수로 `OPENAI_API_KEY` 등 설정 (`.env` 파일을 이미지에 넣지 마세요)
  3. HTTPS 적용 (대부분의 플랫폼이 자동 제공)
  4. 컨테이너 셸에서 `python -m scripts.create_admin 아이디`로 관리자 생성
  5. DB 자동 백업 켜기
- 요청 제한은 서버 메모리 방식이라 **서버 1대 기준**입니다. 여러 대로 늘리면 Redis 등으로 바꿔야 합니다.

## 출시 전 남은 일
- 실제 OpenAI 키로 답변 품질·안전성 평가 (평가용 질문 세트)
- 근거 자료가 있는 실제 제품 데이터 구축
- DB 마이그레이션 도구(Alembic) 도입 — 현재는 시작 시 테이블 자동 생성만 함
- 비밀번호 재설정, 회원 탈퇴(개인정보 삭제), 개인정보 처리방침·이용약관
- 모니터링·로그·사용량/비용 알림

## 구조
```
app/
  main.py      API 라우트
  ai.py        상담 엔진 (안전 규칙, 제품 선별, OpenAI 호출, ID 검증)
  security.py  비밀번호 해시, 로그인 토큰, 요청 제한
  models.py    DB 테이블 (users, auth_sessions, memories, products, chat_messages)
  db.py, config.py, status.py
  static/      chat.html, admin.html, index.html(대시보드), common.css/js
scripts/       create_admin.py, import_products.py
data/          제품 데이터 형식 예시
tests/         API 테스트
```
