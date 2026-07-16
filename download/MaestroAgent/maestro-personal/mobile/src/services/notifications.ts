/**
 * notifications.ts — Push notification registration + handler.
 *
 * Issue 6: Registers the device for push notifications on login, sends
 * the Expo push token to the backend, and handles notification taps
 * with deep links to the right screen.
 */

import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import * as api from '../api/client';

// Configure how notifications appear when the app is in the foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  } as any),
});

/**
 * Request notification permission and register the push token with the backend.
 * Called on login and during onboarding.
 * Returns the token string, or null if permission was denied.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  // Web doesn't support push notifications — return early without throwing
  if (Platform.OS === 'web') return null;

  try {
    const existingResult = await Notifications.getPermissionsAsync() as any;
    let finalStatus = existingResult.status || existingResult.granted ? 'granted' : 'denied';

    if (finalStatus !== 'granted') {
      const newResult = await Notifications.requestPermissionsAsync() as any;
      finalStatus = newResult.status || (newResult.granted ? 'granted' : 'denied');
    }

    if (finalStatus !== 'granted') {
      return null;
    }

    const token = (await Notifications.getExpoPushTokenAsync()).data;

    // Send to backend
    try {
      await api.registerPushToken(token);
    } catch (e) {
      console.warn('Failed to register push token:', e);
    }

    // Android channels
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('stale-commitments', {
        name: 'Stale Commitments',
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
      });
      await Notifications.setNotificationChannelAsync('meeting-reminders', {
        name: 'Meeting Reminders',
        importance: Notifications.AndroidImportance.HIGH,
      });
      await Notifications.setNotificationChannelAsync('daily-briefing', {
        name: 'Daily Briefing',
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }

    return token;
  } catch (e) {
    console.warn('Push notification registration failed:', e);
    return null;
  }
}

/**
 * Set up the notification tap handler. When the user taps a notification,
 * navigate to the right screen based on the notification's data payload.
 * Call this once in App.tsx on mount.
 */
export function setupNotificationHandler(navigation: any) {
  Notifications.addNotificationResponseReceivedListener((response: any) => {
    const data = response.notification.request.content.data || {};

    if (data.type === 'stale_commitment') {
      navigation.navigate('Commitments', { focusEntity: data.entity });
    } else if (data.type === 'whisper') {
      navigation.navigate('Dashboard');
    } else if (data.type === 'daily_briefing') {
      navigation.navigate('Dashboard');
    } else if (data.type === 'connector_sync') {
      // P1-7 fix (audit 2026-07-15): 'Connectors' tab was deleted in the
      // V2 4-tab redesign and merged into 'More'. Routing to the deleted
      // tab name caused a silent no-op (the navigator would log a warning
      // but show nothing). Now routes to 'More' where connectors live.
      navigation.navigate('More');
    }
  });
}
