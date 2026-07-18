// tradePregen.ts — onboarding item 4 (docs/plans/onboarding-conversion/plan.md,
// flag onboarding.trades_first): kick the trade-generation job the moment a
// league session init completes, so cards are ready/streaming by the time the
// user reaches the Trades tab (hazard H3 — hooked into the EXISTING init
// paths, not a new flow).
//
// Contract: fire-and-forget. Never blocks navigation, never throws, no-ops
// entirely unless the onboarding.trades_first feature is live (master
// onboarding.v2 AND its own flag — see useFeatureFlags.onboardingEnabled).
// The server keeps the job/cache warm either way; TradesScreen's own
// generate call adopts the cached job when it mounts.
//
// Layering note: like api/events.ts, this module reads the feature-flag
// zustand store imperatively (no React) because the gate is client-side.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { onboardingEnabled } from '../state/useFeatureFlags';
import { generateTrades } from './trades';

// Fairness pref — single source shared with TradesScreen so the pregen job
// lands in the SAME server cache slot the screen's Find-a-Trade tap reads
// (`_trade_job_is_fresh` keys on fairness_threshold; a mismatched pregen
// would be wasted work).
export const FAIRNESS_PREF_KEY = 'ftf:trades:fairness_on';
export const FAIRNESS_ON_THRESHOLD = 0.75;
export const FAIRNESS_OFF_THRESHOLD = 0.5;

// Double-kick guard: one pregen per league per app launch. The server also
// dedupes (a running/fresh job is returned, not restarted), so this is a
// client-side courtesy to avoid pointless POSTs on every foreground
// revalidate.
const kickedLeagueIds = new Set<string>();

/** Fire-and-forget trade pregeneration for a just-initialized league
 *  session. Safe to call from any session-init success path. */
export function maybePregenTrades(leagueId: string | null | undefined): void {
  if (!leagueId) return;
  if (!onboardingEnabled('onboarding.trades_first')) return;
  if (kickedLeagueIds.has(leagueId)) return;
  kickedLeagueIds.add(leagueId);
  void (async () => {
    try {
      const raw = await AsyncStorage.getItem(FAIRNESS_PREF_KEY);
      const threshold = raw === 'off' ? FAIRNESS_OFF_THRESHOLD : FAIRNESS_ON_THRESHOLD;
      await generateTrades({ league_id: leagueId, fairness_threshold: threshold });
    } catch {
      // Best-effort by contract — the screen's own generate is the fallback.
    }
  })();
}
