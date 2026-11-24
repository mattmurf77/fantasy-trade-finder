import AsyncStorage from '@react-native-async-storage/async-storage';

import { queryClient } from './queryClient';
import { usePresentationDismissed } from './presentationDismissed';
import { useClaimsPending } from './claimsPending';
import { useNotifications } from './useNotifications';
import { usePremiumImport } from './premiumImport';

// accountReset — the ONE place that drops what the device holds for the
// account that just left (sign-out, or a sign-in as someone else).
//
// WHY THIS EXISTS (2026-11-22, Release build, two accounts on one simulator).
// Sign-out cleared the session keys and the device-held trade pages and
// nothing else, so the next account inherited the previous one's:
//   • TanStack Query cache. Most keys carry the league id but not the user
//     (['account'], ['league-summary', leagueId], ['league-prefs', leagueId],
//     ['progress', leagueId, fmt] …), so two accounts in one league shared
//     entries: Settings showed "@A" (the hub reads ['account'] from the cache
//     without fetching) and Home showed A's outlook, rank and position tiles
//     until a pull-to-refresh. Five key families were also persisted to disk
//     (App.tsx PERSIST_KEYS) and came back on the next cold start.
//   • Entitlement state. useEntitlements reset to "not entitled" on sign-out
//     but only re-asked the server on an A → B change, never on the
//     null → B sign-in that follows a sign-out, so a Pro account read
//     "See plans" until the next foreground refresh.
//   • Device-wide progress marks keyed by league only (Team review "done",
//     roster-first setup) — those are now keyed by account in their stores;
//     the stores' in-memory copies are dropped here so they re-read for the
//     new account.
//
// Called from useSession: at the end of signOut() (after the token is gone, so
// nothing refetched in between can carry the old token's answers back in), and
// from setUser / startDemoSession when a DIFFERENT account replaces the
// current one. Every sign-out path in the app goes through useSession.signOut
// (Settings › Account & data, the hub-off Settings list, the league picker,
// the Trades wrong-account alert, account deletion, the tester stage reset);
// tests/check-signout-reset.js pins that.
//
// KEPT on purpose (device-level, not account data): feature flags, onboarding
// / guide progress, the What's-new marker, the rating-prompt anchor, the
// ranking-method / scoring-format / fairness / trios speed-mode preferences,
// the device id, the last username behind SignIn's "Continue as @…" (Keychain
// `ftf.lastUsername`), the analytics and pick-recording queues, and every key
// that already carries the user id (trade queue, outlook strip, paywall offer
// marker, founder welcome, new-partner dismissals, the platform credential
// vault — bound to its user_id at read). The feedback notes stay too: their
// inbox already hides notes /api/feedback/mine does not return for the
// signed-in account.
//
// Never throws: a storage failure must not strand the user half signed out.

/** The persisted query cache's AsyncStorage key — the persister's default,
 *  named here so App.tsx passes the same constant and this file can drop it. */
export const QUERY_CACHE_STORAGE_KEY = 'REACT_QUERY_OFFLINE_CACHE';

/** Device keys whose value is the previous account's data or progress and
 *  whose name does not carry the account. Removed outright. */
export const ACCOUNT_DEVICE_KEYS: readonly string[] = [
  QUERY_CACHE_STORAGE_KEY,
  'ftf.entitlements.v1',            // useEntitlements cache (also dropped by resetEntitlements)
  'ftf_tiers_saved_cache_v1',       // quicksetProgress: the server's saved-tiers answer
  'ftf:tradecalc:v1',               // TradeCalculatorScreen draft (that account's player ids)
  'ftf_pick_board_confirmed_v1',    // PickAssignmentScreen per-season review marks
  'ftf.premium_import.v1',          // premiumImport "imported N weeks ago" stamps
];
/** Same, for keys that carry a format suffix. */
export const ACCOUNT_DEVICE_KEY_PREFIXES: readonly string[] = [
  'ftf_anchor_done_v1_',            // PickAnchorScreen done positions, per format
];

function attempt(fn: () => unknown): void {
  try {
    const r = fn();
    if (r && typeof (r as Promise<unknown>).catch === 'function') (r as Promise<unknown>).catch(() => {});
  } catch {
    /* best effort — see the header */
  }
}

/** Drop everything the device holds for the account that is leaving. Memory
 *  first, synchronously, then the disk keys. Resolves when the disk removals
 *  have settled; never rejects. */
export async function resetAccountState(): Promise<void> {
  // ── Query cache: memory, then (below) its persisted copy.
  attempt(() => queryClient.cancelQueries());
  attempt(() => queryClient.clear());

  // ── Entitlements: not-entitled AND not-yet-known, so Settings › Subscription
  // renders nothing until the next account's own answer lands.
  // Lazy requires: these stores import useSession, which calls us.
  attempt(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { resetEntitlements } = require('./useEntitlements') as typeof import('./useEntitlements');
    return resetEntitlements();
  });

  // ── In-memory per-account stores.
  attempt(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { clearQuicksetProgress } = require('./quicksetProgress') as typeof import('./quicksetProgress');
    clearQuicksetProgress();
  });
  attempt(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { useTradeQueue } = require('./useTradeQueue') as typeof import('./useTradeQueue');
    useTradeQueue.setState({ byLeague: {}, hydrated: false });
  });
  attempt(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { resetTeamReviewCompletion } = require('./teamReviewCompletion') as typeof import('./teamReviewCompletion');
    resetTeamReviewCompletion();
  });
  attempt(() => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { resetRosterSetup } = require('./rosterSetup') as typeof import('./rosterSetup');
    resetRosterSetup();
  });
  attempt(() => usePremiumImport.setState({ stamps: {}, hydrated: false }));
  attempt(() => usePresentationDismissed.setState({ byLeague: {} }));
  attempt(() => useClaimsPending.setState({ keys: new Set<string>() }));
  attempt(() => useNotifications.getState().clear());

  // ── Disk.
  let prefixed: string[] = [];
  try {
    const all = await AsyncStorage.getAllKeys();
    prefixed = all.filter((k) => ACCOUNT_DEVICE_KEY_PREFIXES.some((p) => k.startsWith(p)));
  } catch {
    /* no listing — the fixed keys below still go */
  }
  try {
    await AsyncStorage.multiRemove([...ACCOUNT_DEVICE_KEYS, ...prefixed]);
  } catch {
    /* best effort */
  }
}
