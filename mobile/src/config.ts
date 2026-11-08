import Constants from 'expo-constants';

// RUTI 서버 주소. 배포 후 app.json의 extra.serverUrl을 실제 주소로 바꾸거나,
// 빌드할 때 EXPO_PUBLIC_RUTI_URL 환경 변수로 넣는다 (예: 개발 중 PC 주소 http://192.168.0.10:8000).
const fromEnv = process.env.EXPO_PUBLIC_RUTI_URL;
const fromConfig = (Constants.expoConfig?.extra as { serverUrl?: string } | undefined)?.serverUrl;

export const SERVER_URL = (fromEnv || fromConfig || 'https://ruti.onrender.com').replace(/\/+$/, '');
export const SERVER_ORIGIN = new URL(SERVER_URL).origin;

// 네이티브 탭과 서버 화면 주소의 짝. 다른 탭 주소로 가는 링크는 탭 전환으로 바꾼다.
export const TABS = {
  index: '/scan',
  community: '/community',
  chat: '/chat',
  mypage: '/mypage',
} as const;
export type TabName = keyof typeof TABS;

export const COLORS = {
  light: { bg: '#FBF8F3', card: '#FFFFFF', text: '#3A3330', muted: '#736A64', brand: '#4F7D6E', line: '#EEE7DD' },
  dark: { bg: '#1B1816', card: '#25211E', text: '#EFE8E1', muted: '#B3A79E', brand: '#8DBBA9', line: '#3A3430' },
};
