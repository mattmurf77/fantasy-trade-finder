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

/**
 * Resolve the stored fairness preference to a boolean.
 *
 * DEFAULT IS OFF (operator decision 2026-08-17): an unset preference now
 * means the wide net (0.5), so testers see and judge more trades and the
 * decline-reason capture has verdicts to collect. Only an explicit `'on'`
 * turns balancing on — a user who deliberately flipped the toggle keeps
 * their choice, and nothing rewrites or clears anyone's stored value.
 * (This inverts the old `raw === 'off' ? OFF : ON` reading, where unset
 * meant on.)
 *
 * THE WHOLE POINT OF THIS HELPER is that both readers agree. The screen's
 * Find-a-Trade and the session-init pregen must resolve the SAME threshold
 * or the pregen lands in a different server cache slot and is wasted work
 * (`_trade_job_is_fresh` keys on fairness_threshold — see the note above).
 * Neither caller may re-derive this; call it.
 */
export function fairnessOnFromPref(raw: string | null | undefined): boolean {
  return raw === 'on';
}

/** The `fairness_threshold` to send for a resolved preference. OFF still
 *  sends a (low) value rather than dropping the field, so the server cache
 *  key stays stable. */
export function fairnessThresholdFor(fairnessOn: boolean): number {
  return fairnessOn ? FAIRNESS_ON_THRESHOLD : FAIRNESS_OFF_THRESHOLD;
}

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
      const threshold = fairnessThresholdFor(fairnessOnFromPref(raw));
      await generateTrades({ league_id: leagueId, fairness_threshold: threshold });
    } catch {
      // Best-effort by contract — the screen's own generate is the fallback.
    }
  })();
}
