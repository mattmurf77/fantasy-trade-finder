import { useEffect } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { FAIRNESS_PREF_KEY, fairnessOnFromPref, fairnessThresholdFor } from '../api/tradePregen';
import { hydrateDevicePages, refreshDevicePage, onTradePageInputsSettled } from '../state/devicePageStore';
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
    let revision = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const prepare = (attempt: number) => {
      const stillCurrent = () => attempt === revision && current();
      void Promise.all([
        hydrateDevicePages(),
        AsyncStorage.getItem(FAIRNESS_PREF_KEY).catch(() => null),
      ]).then(async ([, raw]) => {
        if (!stillCurrent()) return;
        // Foreground work joins the session-init already started by App.tsx;
        // never race its token/format replacement with a generation request.
        await useSession.getState().revalidateSession();
        if (!stillCurrent()) return;
        const request = { league_id: leagueId!, fairness_threshold: fairnessThresholdFor(fairnessOnFromPref(raw)) };
        const scope = devicePageScope(request);
        if (scope) return refreshDevicePage({ key, scope, request }, Date.now(), stillCurrent);
      }).catch(() => { /* background preparation never blocks navigation */ });
    };
    prepare(revision);
    const unsubscribe = onTradePageInputsSettled(() => {
      // Coalesce rapid edits; an older preference read can't win the race.
      const attempt = ++revision;
      clearTimeout(timer);
      timer = setTimeout(() => { if (current()) prepare(attempt); }, 300);
    });
    return () => { cancelled = true; clearTimeout(timer); unsubscribe(); };
  }, [enabled, active, hasToken, switching, isDemo, userId, leagueId, format]);
}
