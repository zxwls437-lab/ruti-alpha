# RUTI — 스킨케어 상담 AI

사용자의 피부 정보(기억)와 **관리자가 승인한 제품만** 참고해서 답하는 스킨케어 정보 도우미입니다. 의료 진단은 하지 않습니다.

> 이어서 작업한다면 먼저 [docs/HANDOFF.md](docs/HANDOFF.md)(인수인계 노트)를 읽으세요.

## 화면
| 주소 | 내용 |
|---|---|
| `/chat` | AI 상담 (회원가입·로그인, 상담, 내 피부 정보) |
| `/scan` | 전성분 분석 (사진·글자, 내 피부 판정, 후기, 내 화장대) |
| `/community` | 커뮤니티 (질문·이야기·유튜브 영상 공유, 댓글) |
| `/mypage` | 내 정보 (프로필, 피부 정보, 동의·알림, 비밀번호, 내 데이터 내려받기, 회원 탈퇴) |
| `/admin` | 관리자 (제품 검토, 후기·커뮤니티 신고 관리, AI 사용량) |
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

브라우저에서 `http://127.0.0.1:8000/chat` 을 여세요.

**관리자 아이디/비밀번호를 잊었을 때** (서버를 끄고 실행):
- 관리자 아이디 확인: `.\.venv\Scripts\python.exe -m scripts.create_admin --list`
- 비밀번호 재설정: `.\.venv\Scripts\python.exe -m scripts.create_admin 아이디` → 새 비밀번호 입력 포트 8000이 사용 중이면 `--port 8001`로 바꾸세요.

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

## 커뮤니티 (`app/community.py`, `/community`)
- 글 종류: 질문 · 이야기 · **유튜브 영상 공유**(youtube.com·youtu.be·쇼츠 링크만, 영상은 저장하지 않고 공식 썸네일·임베드 주소 사용)
- 영상 글은 **협찬·광고 포함 여부 선택 필수** → "광고 포함" 표시
- 관련 제품명을 적으면 RUTI에 전성분이 있는 경우 **보는 사람 피부 기준 판정**(🟢🟡🔴) 표시
- 나와 비슷한 피부 글만 보기, 의약품 표현 감지·안내, 댓글, 도움돼요, 신고(3건 자동 숨김) → 관리자 화면 "커뮤니티 관리"에서 숨김·복구·삭제
- 탈퇴 시 글·댓글·투표 삭제, 내 데이터 내려받기에 포함
- API: `GET·POST /community/posts`, `GET·DELETE /community/posts/{id}`, `POST /community/posts/{id}/comments`, `DELETE /community/comments/{id}`, `POST /community/posts/{id}/helpful`, `POST /community/{posts|comments}/{id}/report`

## 내 화장대 (`app/vanity.py`)
- 분석 결과에서 "내 화장대에 담기" (또는 제품명+전성분 글자로 추가), 최대 `RUTI_VANITY_MAX`개
- 제품끼리 성분 조합을 **고정 규칙**으로 점검 (AI 아님, 일반 스킨케어 안내 수준):
  레티놀류+각질 제거(AHA·BHA·PHA)가 서로 다른 제품에 / 각질 제거 성분 여러 제품 / 레티놀류 중복 / 임신·수유+레티놀류 / 향료 민감+향료 / 비타민C+레티놀·각질 제거(참고)
- API: `GET /vanity`, `POST /vanity {scan_id}` 또는 `{product_name, text}`, `DELETE /vanity/{id}` · 탈퇴·내보내기 반영

## 사용 후기 (`app/reviews.py`)
- 제품은 브랜드+제품명 정규화 키로 묶음 (제품별 전성분과 같은 방식). 한 제품당 1인 1후기(다시 쓰면 수정), 하루 `RUTI_REVIEWS_PER_DAY`개
- 별점, 보습 만족 / 자극 / 재구매 체크, 본문(10~1000자). **사진은 받지 않음**(얼굴 사진 문제 방지)
- **인증 후기**: 같은 제품을 RUTI로 사진 분석한 기록이 있으면 자동 인증
- **협찬·체험단** 체크 → "광고 포함" 표시, 통계 제외 / **의약품 표현**(치료·완치·나았다·여드름이 사라졌다 등) → 통계·AI 요약 제외 + 작성자 안내
- **나와 비슷한 피부 통계**: 작성 당시 피부 정보(건성·지성·복합성·중성·민감성·향료 민감·트러블·임신·수유)를 저장해 같은 피부 타입끼리 집계. 인증·비협찬·의약품 표현 없는 후기만, **5개 미만이면 비율 숨김**
- 피부 타입 공개는 작성자 선택, 이름 대신 닉네임 표시, 탈퇴 시 후기 삭제
- 도움돼요(1인 1회), 신고(3건이면 자동 숨김) → 관리자 화면 "후기 관리"(신고됨·숨김·의약품 표현·전체)에서 숨김·복구·삭제
- API: `POST /reviews`, `GET /reviews?product=&similar=&sort=`, `GET /reviews/summary`, `GET /reviews/mine`, `DELETE /reviews/{id}`, `POST /reviews/{id}/helpful`, `POST /reviews/{id}/report`
- 웹: 전성분 분석 결과 아래 "이 제품 후기" (통계, 목록, 쓰기, 도움돼요, 신고)
- **AI 반영**: 상담 질문이나 분석한 제품명에 후기가 충분한 제품이 나오면 통계를 `<review_stats>`로 AI에 전달. "RUTI 사용자 N명의 경험"으로만 말하고 효능 근거로 쓰지 않도록 지시

## 요금제·이용 한도 (`app/plans.py`)
- 회원별 요금제(무료 / RUTI Plus, 만료일). 하루 한도는 DB 기록으로 세어 재시작해도 유지 (한국 시간 자정 기준)
- `RUTI_FREE_CHAT_PER_DAY`, `RUTI_FREE_SCAN_PER_DAY`, `RUTI_PLUS_*` (0 = 제한 없음, **기본값은 모두 0**) → 출시 시 예: 무료 상담 5 · 사진 1
- 관리자는 제한 없음. 결제 연동 전까지 관리자 화면에서 테스터에게 Plus 지급 (`POST /admin/users/{아이디}/plan`)
- `GET /me`에 요금제와 오늘 사용량 포함, 내 정보 화면에 표시
- 남은 일: App Store / Google Play 구독 영수증 검증 연동

## 회원 정보·동의 (`app/account.py`)
- 회원가입: 아이디·비밀번호·**이름**(필수), 닉네임(선택, 비우면 "촉촉한토너123"처럼 자동 생성), **동의**
  - 필수: 만 14세 이상(`age14`), 이용약관(`terms`), 개인정보 수집·이용(`privacy`), 피부 상태 등 민감정보 처리(`sensitive`) / 선택: 마케팅(`marketing`)
- 동의는 **이력으로 저장**(종류·동의 여부·약관 버전 `RUTI_TERMS_VERSION`·시각). 가장 최근 기록이 현재 상태
- 민감정보 동의가 없으면 피부 정보 저장 불가, **철회하면 저장된 피부 정보 즉시 삭제**
- 동의 기록이 없는 기존 계정은 로그인 시 `needs_consent`로 표시되고 웹 화면에서 동의 창을 띄움
- API: `GET·PATCH /me`(프로필), `GET·PUT /me/consents`, `POST /me/password`(다른 기기 로그아웃), `GET /me/export`(내 데이터 내려받기), `DELETE /me`(회원 탈퇴: 개인 데이터 삭제, 공유된 제품 전성분은 작성자 정보만 제거)

## 보안
- 비밀번호: PBKDF2-SHA256(60만 회) 해시 저장
- 로그인 토큰: 무작위 생성, DB에는 해시만 저장, 기본 7일 만료, 로그아웃 시 폐기
- 요청 제한: 상담 분당 10회, 로그인 15분당 10회, 가입 IP당 시간당 10회 (`.env`에서 조정)
- 사용자별 데이터 격리(기억·상담 기록), 관리자 권한 분리
- 보안 헤더(nosniff, 프레임 차단), 화면은 사용자 입력을 HTML로 해석하지 않음

## 전성분 분석 (`/scan`)
결과는 **한눈에 보는 판정**으로 먼저 보여줍니다: 🟢 잘 맞을 가능성이 높아요 / 🟡 확인이 필요해요 / 🔴 맞지 않을 수 있어요. 판정은 서버 규칙(내 피부 정보와 충돌, 국내 사용금지, 판독 상태)으로 정하고, AI는 그 판정을 쉬운 말로 설명만 합니다(`POST /scan/{id}/explain`). 전체 성분 목록은 접어 두고 필요할 때 펼칩니다. 피부 정보가 없으면 버튼으로 바로 입력할 수 있습니다.

화장품 뒷면 전성분을 **사진으로 찍거나 글자로 붙여넣으면** 성분 사전과 대조합니다.
- AI는 사진의 글자를 **옮겨 적기만** 하고, 규제·주의 판단은 서버가 식약처 성분 사전과 사용자 피부 정보(기억)로 합니다.
- 표시: **국내 사용금지**(빨강) / **국내 사용한도**(주황) / 내 피부 정보와 충돌(주황) / 일부 해외 규제(회색 정보, 경고 아님) / 글자 확인 필요 / 사전에 없음
- 사진 판독 상태: 흐리면 "정확하지 않을 수 있음" 안내, 거의 안 보이면 다시 찍기 요청
- **앞면 사진**: AI가 앞/뒷면을 구분하고 브랜드·제품명을 읽음 → 사용자들이 뒷면을 찍어 저장한 제품별 전성분(`product_ingredient_lists`)에서 찾아 분석. 없으면 뒷면 촬영 안내
- **사진에 제품이 여러 개**면 어떤 제품을 볼지 고르게 함 (같은 사진 재요청은 캐시라 AI 비용 없음). 뒷면에 여러 제품이 찍히면 공유 저장하지 않음(제품명 직접 입력 시만 저장)
- 또렷하게 읽힌 뒷면(또는 제품명과 함께 붙여넣은 성분)은 제품별 전성분으로 저장되고, 같은 목록이 다시 등록되면 확인 횟수가 올라감 (개인정보 없음)
- 사진은 저장하지 않습니다. 휴대폰에서 최대 2000px JPEG로 줄여 전송합니다. 결과(성분 목록)만 본인 기록에 저장됩니다.
- 사진 분석은 하루 `RUTI_SCAN_PER_DAY`회(기본 20) 제한, 글자 붙여넣기는 AI 비용이 없어 제한하지 않습니다.
- API: `POST /scan/image`, `POST /scan/text`, `GET /scan/history`, `GET·DELETE /scan/{id}`
- 결과 화면의 "RUTI에게 물어보기"로 주의 성분을 담은 질문을 상담 화면에 바로 채웁니다.

## 식약처 공공데이터 (성분 사전 · 기능성 화장품)
data.go.kr에서 활용 승인을 받은 API로 성분 사전과 기능성 화장품 목록을 만듭니다.

| 데이터셋 이름 | API | .env 변수 |
|---|---|---|
| ingredient | 화장품 원료성분정보 | `MFDS_INGREDIENT_URL` |
| restricted | 화장품 사용제한 원료정보 | `MFDS_RESTRICTED_URL` |
| functional_report | 기능성화장품 보고품목정보 | `MFDS_FUNCTIONAL_REPORT_URL` |
| functional_review | 기능성화장품 심사품목 정보 | `MFDS_FUNCTIONAL_REVIEW_URL` |
| cosmetics_info | 화장품 관련 정보 (원본 저장만) | `MFDS_COSMETICS_INFO_URL` |

1. `.env`에 `DATA_GO_KR_SERVICE_KEY`(일반 인증키 **Decoding**)와 각 API 요청주소(End Point/오퍼레이션)를 넣습니다.
2. 연결 확인: `python -m scripts.mfds probe ingredient`
3. 전체 다운로드: `python -m scripts.mfds fetch all` (중단해도 받은 만큼 저장, 다시 실행하면 이어서 갱신)
4. 변환: `python -m scripts.mfds build` → 확인: `python -m scripts.mfds status`

- 원본은 `mfds_records`에 그대로 보관합니다. 필드 이름이 예상과 다르면 `app/mfds.py`의 `FIELD_CANDIDATES`만 고치고 `build`를 다시 실행하면 됩니다.
- 식약처 기능성 제품은 공식 출처이므로 자동 승인(`source=mfds`)됩니다. 직접 등록한 제품은 여전히 근거 URL + 관리자 승인이 필요합니다.
- 상담 시 질문에 나온 성분은 성분 사전에서 찾아 AI에 전달하고(사용제한 원료면 주의 안내), 제품은 DB에서 질문 키워드로 후보를 골라 전달합니다.
- 출처 표기: 식품의약품안전처, 공공데이터포털(data.go.kr)

## AI 호출 관문 (`app/llm.py`)
모든 AI 호출(상담·사진 분석)은 한 곳을 거칩니다. [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi)(MIT)의 라우터 설계를 참고했습니다.
- **예비 AI 자동 전환**: 주 공급자가 429·5xx·시간초과·인증 오류면 대기시간(15초→최대 5분)을 걸고 `LLM_FALLBACK_*` 공급자로 전환
- **응답 캐시**: 정확히 같은 요청(같은 질문·맥락, 같은 사진)은 AI를 다시 부르지 않음 (메모리, 기본 500개·24시간)
- **구조화 출력 대체**: json_schema를 지원하지 않는 공급자는 json_object + 지시문으로 재시도, 응답에서 JSON만 추출
- **프롬프트 압축**: 빈 값·출처 URL 제거, 사용법·보고일 줄 제거, 긴 글 자르기, 공백 없는 JSON, 후보 제품 15개
- **사용량·비용**: `/admin/llm-usage` 및 관리자 화면 표, `RUTI_DAILY_BUDGET_USD`로 하루 비용 상한
- 가상 벤치마크: `python -m scripts.benchmark_llm`

**개발할 때만** 로컬 FreeLLMAPI를 연결해 무료로 테스트할 수 있습니다: `OPENAI_BASE_URL=http://localhost:3001/v1`, `OPENAI_API_KEY=<FreeLLMAPI 통합 키>`, `OPENAI_MODEL=auto`.
FreeLLMAPI는 스스로 "개인 실험용, 실서비스 전에 유료 API로 교체"라고 안내하고, 무료 등급 약관상 여러 사용자에게 제공하는 서비스에 쓰면 안 됩니다. 실제 사용자 트래픽에는 유료 API를 쓰세요.

## 상담 품질 점검
`data/eval_questions.json`의 질문 30개(보습·트러블·자극·성분·임신·의료·응급·목록 외 브랜드·주제 외·프롬프트 공격)를 실제 AI에 보내고 보고서를 만듭니다.
```powershell
.\.venv\Scripts\python.exe -m scripts.run_eval
```
- `reports\eval_날짜.html` 이 생성됩니다 (브라우저로 열기). 상담 기록에는 저장되지 않습니다.
- 자동 검사: 내부 용어·의료 효능 표현·길이·응급 안내·제품 ID. 답변 내용은 사람이 직접 읽고 평가하세요.
- 질문 수만큼 OpenAI 요금이 발생합니다. 일부만: `--only sens-1,brand-1`

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
- 비밀번호 찾기(현재는 관리자 스크립트로만 가능)(개인정보 삭제), 개인정보 처리방침·이용약관
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
