# RUTI 안드로이드·iOS 앱 (Expo)

RUTI 서버의 화면(분석·커뮤니티·상담·내 정보)을 **진짜 앱 하단 탭** 안에 담은 앱입니다.
서버 화면을 고치면 앱을 다시 내지 않아도 바로 바뀝니다.

## 앱이 하는 일 (웹사이트를 그냥 감싼 앱이 아님)
- 안드로이드·iOS 기본 하단 탭 (NativeTabs), 시작 화면, 앱 아이콘
- 카메라로 성분표 촬영 (권한 안내 문구 포함)
- 안드로이드 뒤로가기 버튼 → 화면 안에서 먼저 뒤로
- 인터넷이 끊기면 앱 자체 안내 화면 + 다시 시도
- 구매처·유튜브 링크는 휴대폰 브라우저/앱으로 열기
- 한 탭에서 로그인·로그아웃하면 다른 탭도 자동 반영
- 웹 ↔ 앱 연결 통로 (`window.ReactNativeWebView`) — 나중에 구독 결제(Google Play Billing)를 여기에 붙임

## 서버 주소 바꾸기
배포한 주소가 정해지면 `eas.json`의 `EXPO_PUBLIC_RUTI_URL` 세 곳과 `app.json`의 `extra.serverUrl`을 바꿉니다.
(지금은 `https://ruti.onrender.com`으로 되어 있음)

## 앱 파일 만들기 (EAS Build, 클라우드에서 빌드 — PC에 안드로이드 스튜디오 필요 없음)
1. expo.dev 가입 (무료)
2. PC에서 (Node.js 설치 후, 이 `mobile` 폴더에서):
   ```
   npm install
   npx eas-cli@latest login
   npx eas-cli@latest init
   npx eas-cli@latest build --platform android --profile preview
   ```
3. 15~20분 뒤 나오는 링크를 **안드로이드 휴대폰**으로 열면 APK를 바로 설치해 볼 수 있음 (테스트용)
4. 구글 플레이 제출용: `--profile production` (AAB 파일) → 구글 플레이 콘솔의 **비공개 테스트**에 올림 → 테스터 12명 · 14일

## 개발 중 확인
```
npx expo start          # 휴대폰의 Expo Go 앱으로 QR 찍기
npm run typecheck       # 타입 검사
```
개발 중에 PC에서 돌리는 서버를 보려면: `EXPO_PUBLIC_RUTI_URL=http://(PC의 IP):8000 npx expo start`
