import { useEffect } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { FAIRNESS_PREF_KEY, fairnessOnFromPref, fairnessThresholdFor } from '../api/tradePregen';
import { hydrateDevicePages, refreshDevicePage } from '../state/devicePageStore';
import { useSession } from '../state/useSession';
import { useFlag, useFeatureFlags } from '../state/useFeatureFlags';
import { devicePageKey, devicePageScope } from '../utils/devicePage';
import { useAppActive } from './useAppActive';

/** Warm the organic calculator's page while the user is on Home/Rank too.
 * The tap remains synchronous; no pins, intent, opponent or force enter
 * this background request. The server and existing page TTL remain the
 * authority. A session/league/format change cancels pending adoption. */
export function useTradePagePrewarm(): void {
  const enabled = useFlag('trade.first_page_store');
  const userId = useSession((s) => s.user?.user_id);
  const leagueId = useSession((s) => s.league?.league_id);
  const format = useSession((s) => s.activeFormat);
  const switching = useSession((s) => s.switching);
  const isDemo = useSession((s) => s.isDemo);
  const hasToken = useSession((s) => s.hasToken);
  const active = useAppActive();
  useEffect(() => {
    const key = enabled && active && hasToken && !switching && !isDemo
      ? devicePageKey(userId, leagueId, format) : null;
    if (!key || leagueId === 'league_demo' || leagueId === 'no_league') return;
    let cancelled = false;
    const current = () => {
      const s = useSession.getState();
      return !cancelled && AppState.currentState === 'active'
        && !!useFeatureFlags.getState().flags['trade.first_page_store']
        && s.hasToken && !s.switching && !s.isDemo
        && devicePageKey(s.user?.user_id, s.league?.league_id, s.activeFormat) === key;
    };
    void Promise.all([
      hydrateDevicePages(),
      AsyncStorage.getItem(FAIRNESS_PREF_KEY).catch(() => null),
    ]).then(async ([, raw]) => {
      if (!current()) return;
      // Foreground work joins the session-init already started by App.tsx;
      // never race its token/format replacement with a generation request.
      await useSession.getState().revalidateSession();
      if (!current()) return;
      const request = { league_id: leagueId!, fairness_threshold: fairnessThresholdFor(fairnessOnFromPref(raw)) };
      const scope = devicePageScope(request);
      if (scope) return refreshDevicePage({ key, scope, request }, Date.now(), current);
    }).catch(() => { /* background preparation never blocks navigation */ });
    return () => { cancelled = true; };
  }, [enabled, active, hasToken, switching, isDemo, userId, leagueId, format]);
}

