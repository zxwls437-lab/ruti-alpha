import NetInfo from '@react-native-community/netinfo';
import { router, useFocusEffect } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, Linking, Platform, Pressable, StyleSheet, Text, useColorScheme, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { WebView, type WebViewMessageEvent, type WebViewNavigation, type WebViewProps } from 'react-native-webview';
import type { ShouldStartLoadRequest } from 'react-native-webview/lib/WebViewTypes';

import { emitAuthChange, onAuthChange } from '@/auth-events';
import { COLORS, SERVER_ORIGIN, SERVER_URL, TABS, type TabName } from '@/config';

const APP_VERSION = '1.0.0';

// 웹 화면에 "앱 안"이라는 걸 알려서 웹의 하단 탭을 숨기게 한다 (네이티브 탭을 쓰므로).
const BRIDGE = `
  window.RUTI_NATIVE = { platform: ${JSON.stringify(Platform.OS)}, version: ${JSON.stringify(APP_VERSION)} };
  (function mark() {
    if (document.documentElement) document.documentElement.classList.add('ruti-native');
    else document.addEventListener('readystatechange', mark, { once: true });
  })();
  true;
`;

// react-native-webview의 기본 타입 매개변수(undefined)가 TypeScript 6에서 props를 never로 만들어서 object로 고정
type Web = WebView<object>;
const Web = WebView as unknown as new (props: WebViewProps) => Web;

const TAB_BY_PATH: Record<string, TabName> = Object.fromEntries(
  Object.entries(TABS).map(([tab, path]) => [path, tab as TabName]),
) as Record<string, TabName>;

function parse(url: string) {
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

export function RutiWeb({ tab }: { tab: TabName }) {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const c = COLORS[scheme];
  const ref = useRef<Web>(null);
  const canGoBack = useRef(false);
  const focused = useRef(false);
  const stale = useRef(false);
  const [failed, setFailed] = useState(false);
  const [offline, setOffline] = useState(false);
  const [key, setKey] = useState(0);
  const home = SERVER_URL + TABS[tab] + '?source=app';

  // 인터넷 연결 상태 (끊기면 앱 자체 안내 화면)
  useEffect(() => NetInfo.addEventListener((s) => setOffline(s.isConnected === false)), []);

  // 다른 탭에서 로그인·로그아웃하면 이 탭은 다음에 보일 때 새로고침
  useEffect(
    () =>
      onAuthChange((source) => {
        if (source === tab) return;
        if (focused.current) ref.current?.reload();
        else stale.current = true;
      }),
    [tab],
  );

  useFocusEffect(
    useCallback(() => {
      focused.current = true;
      if (stale.current) {
        stale.current = false;
        ref.current?.reload();
      }
      // 안드로이드 뒤로가기: 화면 안에서 먼저 뒤로
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        if (canGoBack.current) {
          ref.current?.goBack();
          return true;
        }
        return false;
      });
      return () => {
        focused.current = false;
        sub.remove();
      };
    }, []),
  );

  const onShouldStart = useCallback(
    (req: ShouldStartLoadRequest) => {
      const url = parse(req.url);
      if (!url || req.url.startsWith('about:') || req.url.startsWith('data:') || req.url.startsWith('blob:')) return true;
      if (url.origin !== SERVER_ORIGIN) {
        // 구매처·유튜브·전화 등 바깥 링크는 휴대폰의 다른 앱/브라우저로
        if (req.isTopFrame === false) return true; // 유튜브 미리보기 이미지 등 화면 안 요소
        Linking.openURL(req.url).catch(() => {});
        return false;
      }
      const other = TAB_BY_PATH[url.pathname];
      if (other && other !== tab) {
        router.navigate(other === 'index' ? '/' : `/${other}`);
        return false;
      }
      return true;
    },
    [tab],
  );

  const onMessage = useCallback(
    (e: WebViewMessageEvent) => {
      let msg: { type?: string; url?: string } = {};
      try {
        msg = JSON.parse(e.nativeEvent.data);
      } catch {
        return;
      }
      if (msg.type === 'auth') emitAuthChange(tab);
      if (msg.type === 'openExternal' && msg.url && /^https?:\/\//.test(msg.url)) Linking.openURL(msg.url).catch(() => {});
    },
    [tab],
  );

  const retry = () => {
    setFailed(false);
    setKey((k) => k + 1);
  };

  if (offline || failed) {
    return (
      <SafeAreaView style={[styles.fill, styles.center, { backgroundColor: c.bg }]}>
        <Text style={[styles.title, { color: c.text }]}>{offline ? '인터넷 연결이 끊겼어요' : 'RUTI에 연결하지 못했어요'}</Text>
        <Text style={[styles.body, { color: c.muted }]}>
          {offline ? '와이파이나 데이터를 켠 뒤 다시 시도해 주세요.' : '잠시 후 다시 시도해 주세요. 서버가 깨어나는 데 1분쯤 걸릴 수 있어요.'}
        </Text>
        <Pressable accessibilityRole="button" onPress={retry} style={[styles.button, { backgroundColor: c.brand }]}>
          <Text style={[styles.buttonText, { color: c.card }]}>다시 시도</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['top']} style={[styles.fill, { backgroundColor: c.bg }]}>
      <Web
        key={key}
        ref={ref}
        source={{ uri: home }}
        style={[styles.fill, { backgroundColor: c.bg }]}
        applicationNameForUserAgent={`RUTIApp/${APP_VERSION}`}
        injectedJavaScriptBeforeContentLoaded={BRIDGE}
        onShouldStartLoadWithRequest={onShouldStart}
        onNavigationStateChange={(n: WebViewNavigation) => {
          canGoBack.current = n.canGoBack;
        }}
        onMessage={onMessage}
        onLoadEnd={() => SplashScreen.hideAsync().catch(() => {})}
        onError={() => setFailed(true)}
        onHttpError={(e: { nativeEvent: { statusCode: number } }) => {
          if (e.nativeEvent.statusCode >= 500) setFailed(true);
        }}
        onRenderProcessGone={() => setKey((k) => k + 1)}
        onContentProcessDidTerminate={() => ref.current?.reload()}
        startInLoadingState
        renderLoading={() => (
          <View style={[StyleSheet.absoluteFill, styles.center, { backgroundColor: c.bg }]}>
            <ActivityIndicator color={c.brand} />
          </View>
        )}
        setSupportMultipleWindows={false}
        javaScriptEnabled
        domStorageEnabled
        sharedCookiesEnabled
        allowsBackForwardNavigationGestures
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction
        allowFileAccess={false}
        pullToRefreshEnabled
        overScrollMode="never"
        textZoom={100}
        webviewDebuggingEnabled={__DEV__}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 },
  title: { fontSize: 20, fontWeight: '700', textAlign: 'center' },
  body: { fontSize: 15, lineHeight: 22, textAlign: 'center' },
  button: { marginTop: 8, minHeight: 48, paddingHorizontal: 28, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  buttonText: { fontSize: 16, fontWeight: '700' },
});
