// 루틴 알림: 아침·저녁 정해진 시각에 매일 로컬 알림 (서버 없이 폰 안에서만 동작)
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

export type ReminderSetting = { am: string | null; pm: string | null }; // "08:00" 형식, null이면 끔

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;
const TEXT = {
  am: { title: '☀️ 아침 루틴 시간이에요', body: '세안 → 보습 → 선크림까지, 오늘도 가볍게 체크해 볼까요?' },
  pm: { title: '🌙 저녁 루틴 시간이에요', body: '하루 동안 고생한 피부, 오늘 루틴 체크하고 쉬어요.' },
};

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
});

async function ensurePermission(): Promise<boolean> {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('routine', {
      name: '루틴 알림',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  const asked = await Notifications.requestPermissionsAsync();
  return asked.granted;
}

/** 설정대로 알림을 다시 건다. 결과: 'ok' | 'denied' | 'invalid' */
export async function applyReminders(setting: ReminderSetting): Promise<'ok' | 'denied' | 'invalid'> {
  for (const v of [setting.am, setting.pm]) if (v !== null && !TIME.test(v)) return 'invalid';
  await Notifications.cancelAllScheduledNotificationsAsync();
  if (!setting.am && !setting.pm) return 'ok';
  if (!(await ensurePermission())) return 'denied';
  for (const slot of ['am', 'pm'] as const) {
    const t = setting[slot];
    if (!t) continue;
    const [hour, minute] = t.split(':').map(Number);
    await Notifications.scheduleNotificationAsync({
      content: { ...TEXT[slot], data: { path: '/routine' } },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour, minute, channelId: 'routine' },
    });
  }
  return 'ok';
}
