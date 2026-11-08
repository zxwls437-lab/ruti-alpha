# RUTI 인터넷 배포 (Render) — 휴대폰으로 따라 하기

RUTI 저장소에는 `render.yaml`(배포 설계도)이 들어 있어서, 버튼 몇 번이면 **웹 서버 + 데이터베이스**가 함께 만들어집니다.

## 0. 준비물
- GitHub 계정 (이미 있음)
- OpenAI API 키 (`sk-`로 시작)
- 관리자 아이디·비밀번호 (새로 정하기, 비밀번호 8자 이상)
- (선택) 공공데이터포털 서비스 키 — 식약처 성분 데이터를 서버가 직접 받을 때

## 1. Render 가입
1. render.com 접속 → **Get Started** → **GitHub**로 가입
2. GitHub가 권한을 물으면 **zxwls437-lab/ruti-alpha** 저장소 접근을 허용

## 2. 블루프린트로 한 번에 만들기
1. Render 대시보드 → **New +** → **Blueprint**
2. 저장소 **ruti-alpha** 선택 → Render가 `render.yaml`을 읽어 `ruti`(웹)와 `ruti-db`(데이터베이스)를 보여줌
3. 빈칸 채우기 (값은 이 화면에만 입력하고 채팅·GitHub에는 절대 올리지 않기)

| 이름 | 넣을 값 |
|---|---|
| `OPENAI_API_KEY` | `sk-`로 시작하는 키 전체 |
| `RUTI_BOOTSTRAP_ADMIN_USERNAME` | 관리자 아이디 (영문·숫자) |
| `RUTI_BOOTSTRAP_ADMIN_PASSWORD` | 관리자 비밀번호 (8자 이상) |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 키 (없으면 비워 두기) |
| `RUTI_OPERATOR_NAME` | 처리방침에 나올 운영자 이름 (개인이면 본인 이름) |
| `RUTI_CONTACT_EMAIL` | 문의 받을 이메일 |
| `RUTI_PRIVACY_OFFICER` | 개인정보 보호책임자 이름 |

4. **Apply** → 5~10분 기다리기 (처음 빌드)
5. 완료되면 `https://ruti-xxxx.onrender.com` 같은 주소가 생김 → 휴대폰으로 열어 보기

## 3. 식약처 성분 데이터 채우기
1. `https://(내 주소)/admin` → 관리자로 로그인 → **식약처 성분 데이터**
2. **식약처에서 바로 받기** → 몇 분 기다리면 "완료: 성분 27,000여 개"
3. "식약처 연결 실패"가 나오면 (해외 서버 접속 차단):
   - PC의 RUTI 폴더에서 `python -m scripts.mfds export` → `ruti-ingredients.json.gz` 파일 생김
   - PC 브라우저로 관리자 화면 → **파일로 올리기** → 그 파일 선택

## 4. 확인
- `/health` → `"status": "ok"`
- `/privacy`, `/terms`, `/account-deletion` 열리는지 (구글 플레이에 이 주소를 냄)
- 회원가입 → 성분 사진 분석 → 상담

## 요금
| | 무료 | 유료 (시범 운영부터 권장) |
|---|---|---|
| 웹 서버 | 15분 동안 안 쓰면 잠듦, 깨는 데 약 50초 | Starter 약 $7/월, 항상 켜짐 |
| 데이터베이스 | **30일 뒤 만료** (데이터 삭제) | Basic 약 $6/월 |

무료로 동작을 확인한 뒤, **30명 시범 운영 전에** Render 화면에서 두 서비스의 플랜을 유료로 바꾸세요 (주소·데이터 그대로 유지).
