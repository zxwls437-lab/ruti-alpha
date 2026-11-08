import { NativeTabs } from 'expo-router/native-tabs';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';

import { COLORS } from '@/config';

SplashScreen.preventAutoHideAsync();
// 서버가 늦게 깨어나도 시작 화면에 갇히지 않게
setTimeout(() => SplashScreen.hideAsync().catch(() => {}), 6000);

// 진짜 안드로이드/iOS 하단 탭. 각 탭 안에는 RUTI 화면이 들어간다.
export default function TabLayout() {
  const c = COLORS[useColorScheme() === 'dark' ? 'dark' : 'light'];
  return (
    <NativeTabs
      backgroundColor={c.card}
      indicatorColor={c.bg}
      iconColor={{ default: c.muted, selected: c.brand }}
      labelStyle={{ default: { color: c.muted }, selected: { color: c.brand } }}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>분석</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/scan.png')} renderingMode="template" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="community">
        <NativeTabs.Trigger.Label>커뮤니티</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/community.png')} renderingMode="template" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="chat">
        <NativeTabs.Trigger.Label>상담</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/chat.png')} renderingMode="template" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="mypage">
        <NativeTabs.Trigger.Label>내 정보</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/me.png')} renderingMode="template" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
