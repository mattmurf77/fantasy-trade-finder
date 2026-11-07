import { useEffect } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { FAIRNESS_PREF_KEY, fairnessOnFromPref, fairnessThresholdFor } from '../api/tradePregen';
import { onTradePageInputsSettled } from '../state/devicePageStore';
import { prepareTradePage } from '../state/tradePagePreparation';
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
      void prepareTradePage(key, async () => {
        const raw = await AsyncStorage.getItem(FAIRNESS_PREF_KEY).catch(() => null);
        const request = { league_id: leagueId!, fairness_threshold: fairnessThresholdFor(fairnessOnFromPref(raw)) };
        const scope = devicePageScope(request);
        return scope && (format === '1qb_ppr' || format === 'sf_tep')
          ? { key, scope, format, request } : null;
      }, stillCurrent);
    };
    prepare(revision);
    let lastEditWarm: number | undefined;
    const unsubscribe = onTradePageInputsSettled(() => {
      // Coalesce rapid edits; an older preference read can't win the race.
      const attempt = ++revision;
      clearTimeout(timer);
      // Ranking gestures may each commit a write. Let an explicit tap run
      // immediately, but never start another speculative generation per swipe.
      const delay = lastEditWarm === undefined ? 300 : Math.max(300, 30000 - (Date.now() - lastEditWarm));
      timer = setTimeout(() => {
        if (!current()) return;
        lastEditWarm = Date.now();
        prepare(attempt);
      }, delay);
    });
    return () => { cancelled = true; clearTimeout(timer); unsubscribe(); };
  }, [enabled, active, hasToken, switching, isDemo, userId, leagueId, format]);
}
