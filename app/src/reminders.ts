import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { picksKey } from './picks';
import type { RaceInfo } from './types';

// A local notification an hour before lights out, only while the user hasn't made picks for that race.
// Scheduled on the phone, so there's no push server involved.

const ID = 'pick-reminder';
const PREF = 'reminders-enabled';
const LEAD_MS = 60 * 60 * 1000;
const supported = Platform.OS === 'ios';

if (supported) {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
  });
}

export type ReminderStatus = 'unsupported' | 'undetermined' | 'on' | 'off';

async function status(): Promise<ReminderStatus> {
  if (!supported) return 'unsupported';
  const perm = await Notifications.getPermissionsAsync();
  if (perm.status === 'undetermined') return 'undetermined';
  if (perm.status !== 'granted') return 'off';
  return (await AsyncStorage.getItem(PREF)) === '0' ? 'off' : 'on';
}

/** Schedules or clears the reminder for this race, based on the setting and whether picks exist. */
export async function syncReminder(race: RaceInfo | null | undefined, hasPicks?: boolean): Promise<void> {
  if (!supported) return;
  try {
    await Notifications.cancelScheduledNotificationAsync(ID).catch(() => {});
    if (!race?.race_start || (await status()) !== 'on') return;
    if (hasPicks ?? !!(await AsyncStorage.getItem(picksKey(race.season, race.round)))) return;
    const at = new Date(race.race_start).getTime() - LEAD_MS;
    if (at <= Date.now()) return;
    await Notifications.scheduleNotificationAsync({
      identifier: ID,
      content: {
        title: `${race.race_name}: lights out in an hour`,
        body: "You haven't made your picks yet. Set your finishing order before they lock.",
        data: { url: '/predict' },
      },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: new Date(at) },
    });
  } catch {
    // A reminder is a nice-to-have; never let it break the app.
  }
}

export function useReminders(race: RaceInfo | null | undefined) {
  const [value, setValue] = useState<ReminderStatus | null>(null);

  useEffect(() => {
    status().then(setValue).catch(() => setValue('unsupported'));
  }, []);

  const setEnabled = useCallback(
    async (on: boolean) => {
      if (on) {
        const perm = await Notifications.requestPermissionsAsync();
        if (perm.status !== 'granted') {
          setValue('off');
          return false;
        }
      }
      await AsyncStorage.setItem(PREF, on ? '1' : '0');
      setValue(on ? 'on' : 'off');
      await syncReminder(race);
      return true;
    },
    [race],
  );

  return { status: value, setEnabled };
}

/** Opens the Predict tab when a reminder is tapped. */
export function useReminderTaps(open: (url: string) => void) {
  useEffect(() => {
    if (!supported) return;
    const sub = Notifications.addNotificationResponseReceivedListener((r) => {
      const url = r.notification.request.content.data?.url;
      if (typeof url === 'string') open(url);
    });
    return () => sub.remove();
  }, [open]);
}
