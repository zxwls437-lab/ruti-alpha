// 한 탭에서 로그인·로그아웃하면 다른 탭 화면도 다시 불러오게 알린다.
// (WebView끼리 저장소는 공유되지만, 이미 열린 화면은 새로고침해야 반영된다)
type Listener = (source: string) => void;
const listeners = new Set<Listener>();

export function onAuthChange(fn: Listener) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function emitAuthChange(source: string) {
  listeners.forEach((fn) => fn(source));
}
