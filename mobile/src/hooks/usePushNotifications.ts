import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { registerDeviceForPush } from '../api/notifications';
import { useNotifications } from '../state/useNotifications';
import { usePushPriming } from '../state/usePushPriming';
import { useFeatureFlags } from '../state/useFeatureFlags';
import { resolveNotificationTarget } from '../utils/deepLinks';

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
// (tab, matchId) — tab is one of the bottom-tab route names. Pass undefined
// matchId for non-trade kinds; the receiving screen ignores it.
type TapRouter = (tab: 'Matches' | 'League' | 'Rank' | 'Trades',
                  matchId?: string | number) => void;

export function usePushNotifications(
  userId: string | null,
  onTapMatchNotification?: TapRouter,
  enabled: boolean = true,
) {
  const receivedSubRef = useRef<Notifications.EventSubscription | null>(null);
  const responseSubRef = useRef<Notifications.EventSubscription | null>(null);
  // Cache whether we've already done the registration round-trip in this
  // session. Prevents firing the prompt twice if `enabled` toggles.
  const registeredRef = useRef(false);
  // S5 PRD-02 (flag `notif.tap_routing_v2`): the last tap that launched or
  // resumed the app. Cold-start taps never reach the response listener (it
  // registers too late), so this hook is the only reliable source for them.
  // Called unconditionally (rules of hooks); consumed only when the flag is
  // on. Dedupe set shared with the live listener — a warm tap can surface
  // through BOTH paths and must route once.
  const lastResponse = Notifications.useLastNotificationResponse();
  const handledTapIdsRef = useRef<Set<string>>(new Set());

  // ── Cold-start tap replay (flag `notif.tap_routing_v2`) ──
  useEffect(() => {
    if (!userId || !lastResponse || !onTapMatchNotification) return;
    if (!useFeatureFlags.getState().flags['notif.tap_routing_v2']) return;
    try {
      const respId = lastResponse?.notification?.request?.identifier ?? null;
      if (respId) {
        if (handledTapIdsRef.current.has(respId)) return;
        handledTapIdsRef.current.add(respId);
      }
      const data = lastResponse?.notification?.request?.content?.data as any;
      const target = resolveNotificationTarget(data);
      // The tap router buffers until navigationRef.isReady() and replays,
      // so a cold-start tap survives the boot gap instead of being dropped.
      if (target) onTapMatchNotification(target.tab, target.matchId);
    } catch {
      // best-effort — never let tap routing crash the root
    }
  }, [userId, lastResponse, onTapMatchNotification]);

  // ── Permission ask + token registration (deferred until `enabled`) ──
  useEffect(() => {
    if (!userId) return;
    if (!enabled) return;
    if (registeredRef.current) return;
    if (!Device.isDevice) return;            // simulators can't receive pushes

    let cancelled = false;

    // Inner: actually call OS permission prompt + fetch token + register.
    // Used both directly (already-granted path) and as the `accept` callback
    // that the priming modal invokes.
    const requestAndRegister = async () => {
      try {
        const req = await Notifications.requestPermissionsAsync();
        if (req.status !== 'granted' || cancelled) return;
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
      } finally {
        usePushPriming.getState().clear();
      }
    };

    (async () => {
      try {
        const existing = await Notifications.getPermissionsAsync();
        if (existing.status === 'granted') {
          // Already granted on a prior session — skip priming, refresh token.
          await requestAndRegister();
          return;
        }
        // Permission is `undetermined` (first-run) or `denied`. We don't
        // re-prompt after explicit denials. For undetermined, hand off to
        // the priming modal — it will call back into requestAndRegister
        // only after the user opts in via the in-app sheet.
        if (existing.status === 'undetermined') {
          usePushPriming.getState().request(requestAndRegister);
        }
      } catch {
        // ignore — push registration is best-effort
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
        if (!data?.type || !onTapMatchNotification) return;
        // V2 (flag `notif.tap_routing_v2`, read at event time): shared kind
        // map from utils/deepLinks (adds `bundle_summary`), match_id passed
        // through, and dedupe against the cold-start replay above.
        if (useFeatureFlags.getState().flags['notif.tap_routing_v2']) {
          const respId = resp?.notification?.request?.identifier ?? null;
          if (respId) {
            if (handledTapIdsRef.current.has(respId)) return;
            handledTapIdsRef.current.add(respId);
          }
          const target = resolveNotificationTarget(data);
          if (target) onTapMatchNotification(target.tab, target.matchId);
          return;
        }
        // Route by `data.type` (set by backend = the push `kind`). Legacy
        // 'trade_match' value still routes to Matches for older payloads
        // already sitting in iOS Notification Center.
        const kind = String(data.type);
        const matchKinds = new Set([
          'trade_match', 'new_match', 'first_match', 'match_accepted',
          'match_expiring', 'counter_offer',
          'weekly_digest', 'pending_review',
          'winback_matches', 'winback_dormant', 'season_start',
        ]);
        const leagueKinds = new Set([
          'league_member_joined', 'league_member_unlocked_trades',
        ]);
        const rankKinds = new Set(['finish_ranking']);
        if (matchKinds.has(kind)) {
          onTapMatchNotification('Matches', data.match_id);
        } else if (leagueKinds.has(kind)) {
          onTapMatchNotification('League', undefined);
        } else if (rankKinds.has(kind)) {
          onTapMatchNotification('Rank', undefined);
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
}
