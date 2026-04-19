import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { registerDeviceForPush } from '../api/notifications';

// Display pushes while app is foregrounded. Setting this once per module
// rather than per-hook-invocation avoids any ordering surprises.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList:   true,
    shouldPlaySound:  true,
    shouldSetBadge:   true,
  }),
});

/**
 * Request permission, fetch an Expo push token, register it with our backend.
 *
 * - Safe to call with `userId === null` (no-ops until the user signs in).
 * - Silent on permission deny — caller sees no error, push just doesn't work
 *   until the user grants permission in Settings.
 * - Tolerant of missing projectId (pre-EAS-init) — logs and moves on.
 * - Sets up listeners for both foreground-delivery and notification-tap so
 *   the caller can pass an `onOpenMatchesTab` callback for deep-linking.
 */
export function usePushNotifications(
  userId: string | null,
  onTapMatchNotification?: (matchId?: string | number) => void,
) {
  const receivedSubRef = useRef<Notifications.EventSubscription | null>(null);
  const responseSubRef = useRef<Notifications.EventSubscription | null>(null);

  useEffect(() => {
    if (!userId) return;

    // Simulator emulators can't actually receive pushes; bail early so
    // the permission prompt isn't triggered during dev.
    if (!Device.isDevice) {
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        // 1) Ensure permission. If the user already granted or denied,
        //    Notifications.getPermissionsAsync returns the existing state.
        const existing = await Notifications.getPermissionsAsync();
        let status = existing.status;
        if (status !== 'granted') {
          const req = await Notifications.requestPermissionsAsync();
          status = req.status;
        }
        if (status !== 'granted') return;
        if (cancelled) return;

        // 2) Fetch an Expo push token. Requires a projectId once EAS is
        //    initialized; missing projectId is a dev-only speed bump.
        const projectId: string | undefined =
          (Constants.expoConfig as any)?.extra?.eas?.projectId ??
          (Constants.easConfig as any)?.projectId;

        const tokenResp = await Notifications.getExpoPushTokenAsync(
          projectId ? { projectId } : undefined,
        );
        const token = tokenResp?.data;
        if (!token || cancelled) return;

        // 3) POST to the backend. Best-effort — helper already swallows errors.
        const platform = Platform.OS === 'ios' ? 'ios' : 'android';
        await registerDeviceForPush(token, platform);
      } catch {
        // Silent — push is non-critical.
      }
    })();

    // 4) Listen for notification events. Wire the tap handler so tapping
    //    a "trade match" push surfaces the Matches tab.
    receivedSubRef.current = Notifications.addNotificationReceivedListener(() => {
      // Default handler above already displays the banner. Nothing extra
      // to do here — but keeping the hook so Phase 6 can add a badge
      // counter or in-app toast if desired.
    });
    responseSubRef.current = Notifications.addNotificationResponseReceivedListener((resp) => {
      try {
        const data = resp?.notification?.request?.content?.data as any;
        if (data?.type === 'trade_match' && onTapMatchNotification) {
          onTapMatchNotification(data.match_id);
        }
      } catch {
        // ignore
      }
    });

    return () => {
      cancelled = true;
      receivedSubRef.current?.remove();
      responseSubRef.current?.remove();
      receivedSubRef.current = null;
      responseSubRef.current = null;
    };
  }, [userId, onTapMatchNotification]);
}
