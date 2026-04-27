import { useEffect, useRef } from 'react';
import { AppState, AppStateStatus, Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { registerDeviceForPush } from '../api/notifications';
import { useNotifications, type PushPermissionStatus } from '../state/useNotifications';

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
 * The OS permission prompt is the most disruptive thing in the entire app
 * onboarding, so we DEFER asking for it until the user has earned the
 * Trade Finder unlock (i.e. ranked enough trios). Pre-unlock we still wire
 * the foreground/tap listeners so any pushes that *do* arrive (e.g. via a
 * previously-granted permission on a reinstall) get captured into the
 * in-app feed; we just don't trigger the iOS dialog yet.
 *
 * - Safe to call with `userId === null` (no-ops until the user signs in).
 * - Permission ask + token registration are gated on `enabled`. Flip it to
 *   true once `progress.unlocked === true`.
 * - Silent on permission deny — caller sees no error, push just doesn't work
 *   until the user grants permission in Settings.
 * - Tolerant of missing projectId (pre-EAS-init) — logs and moves on.
 */
export function usePushNotifications(
  userId: string | null,
  onTapMatchNotification?: (matchId?: string | number) => void,
  enabled: boolean = true,
) {
  const receivedSubRef = useRef<Notifications.EventSubscription | null>(null);
  const responseSubRef = useRef<Notifications.EventSubscription | null>(null);
  // Cache whether we've already done the registration round-trip in this
  // session. Prevents firing the prompt twice if `enabled` toggles.
  const registeredRef = useRef(false);

  // ── Permission ask + token registration (deferred until `enabled`) ──
  // Publishes the OS permission status into useNotifications so screens
  // can render a "denied" banner — once the user denies we cannot
  // re-prompt; only Settings can flip it back.
  useEffect(() => {
    if (!userId) return;
    if (!enabled) return;
    if (registeredRef.current) return;
    if (!Device.isDevice) return;            // simulators can't receive pushes

    let cancelled = false;

    (async () => {
      try {
        const existing = await Notifications.getPermissionsAsync();
        let status = existing.status;
        // Publish the pre-prompt state so the banner can show "ask"
        // copy if undetermined or "denied" if already declined.
        useNotifications.getState().setPermissionStatus(
          status === 'granted' ? 'granted'
          : status === 'denied' ? 'denied'
          : 'undetermined',
        );
        if (status !== 'granted') {
          const req = await Notifications.requestPermissionsAsync();
          status = req.status;
          useNotifications.getState().setPermissionStatus(
            status === 'granted' ? 'granted' : 'denied',
          );
        }
        if (status !== 'granted') return;
        if (cancelled) return;

        const projectId: string | undefined =
          (Constants.expoConfig as any)?.extra?.eas?.projectId ??
          (Constants.easConfig as any)?.projectId;

        const tokenResp = await Notifications.getExpoPushTokenAsync(
          projectId ? { projectId } : undefined,
        );
        const token = tokenResp?.data;
        if (!token || cancelled) return;

        const platform = Platform.OS === 'ios' ? 'ios' : 'android';
        await registerDeviceForPush(token, platform);
        if (!cancelled) registeredRef.current = true;
      } catch {
        // Silent — push is non-critical.
      }
    })();

    return () => { cancelled = true; };
  }, [userId, enabled]);

  // ── Foreground delivery + tap listeners (always wired post-signin) ──
  // These don't trigger any OS prompts — they just observe events that
  // may arrive after the user has eventually granted permission.
  useEffect(() => {
    if (!userId) return;
    receivedSubRef.current = Notifications.addNotificationReceivedListener((evt) => {
      // Capture into the in-app feed so the TopBar bell can show it.
      // The OS banner is also shown (set above) — these two are independent.
      try {
        const req = evt?.request;
        const content = req?.content;
        const id =
          (req as any)?.identifier ||
          (content?.data as any)?.id ||
          `n-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
        useNotifications.getState().add({
          id: String(id),
          title: content?.title || 'Notification',
          body:  content?.body  || '',
          data:  (content?.data as Record<string, unknown>) || undefined,
        });
      } catch {
        // best-effort — never let store updates crash the listener
      }
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
      receivedSubRef.current?.remove();
      responseSubRef.current?.remove();
      receivedSubRef.current = null;
      responseSubRef.current = null;
    };
  }, [userId, onTapMatchNotification]);

  // ── Refresh permission status when the app foregrounds ───────────────
  // The "denied" banner on LeagueScreen tells the user "enable in Settings
  // to fix." If we don't re-read permission on return-to-foreground, the
  // banner will persist even after they fix it — until the next cold
  // launch. AppState's 'active' transition is the right hook: cheap, fires
  // exactly when we need it, and doesn't churn while the app is in the
  // background. iOS-only check would be tighter but expo-notifications
  // works on Android too, so we keep it cross-platform.
  useEffect(() => {
    if (!userId || !Device.isDevice) return;
    const handleAppStateChange = async (next: AppStateStatus) => {
      if (next !== 'active') return;
      try {
        const perm = await Notifications.getPermissionsAsync();
        const status: PushPermissionStatus =
          perm.status === 'granted' ? 'granted'
          : perm.status === 'denied' ? 'denied'
          : 'undetermined';
        useNotifications.getState().setPermissionStatus(status);
      } catch {
        // best-effort — leave the cached status alone on read failure
      }
    };
    const sub = AppState.addEventListener('change', handleAppStateChange);
    return () => sub.remove();
  }, [userId]);
}
