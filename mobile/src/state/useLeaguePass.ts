import { useFeatureFlags, useFlag } from './useFeatureFlags';
import { useEntitlements } from './useEntitlements';
import { proForLeague } from '../utils/leaguePass';

// League pass, the store-side seam (flag `monetize.league_pass`, dark;
// docs/plans/monetization/league-pass/lld.md §8, D-281).
//
// `useEntitlements` holds the server's `league_passes`; this module is where
// the CLIENT flag and the `covered_until` clock are applied, so no caller
// reads the raw list as a grant. Kept out of useEntitlements.ts on purpose:
// that store is executed under plain node by check-paywall-gate and
// check-signout-reset with a fixed import set, and the flag read belongs to
// the callers that gate UI, not to the cache.
//
// With the flag off, `proForLeague(id)` IS `pro`: the same value every
// pre-check read before this feature.

/** The league pass client flag. Purchase entry points also need
 *  `monetize.paywall` (the "no purchase UI" flag). */
export function useLeaguePassOn(): boolean {
  return useFlag('monetize.league_pass');
}

/** `pro` OR a live pass covering this user in `leagueId` (lld §8). UI only:
 *  the server's 402 gate stays the authority. Re-renders on entitlement or
 *  flag changes; the clock is read at render. */
export function useProForLeague(leagueId: string | null | undefined): boolean {
  const flagOn = useFlag('monetize.league_pass');
  const pro = useEntitlements((s) => s.pro);
  const passes = useEntitlements((s) => s.leaguePasses);
  return proForLeague(pro, passes, leagueId, flagOn, Date.now());
}

/** The same answer, read imperatively (a tap handler outside render). */
export function proForLeagueNow(leagueId: string | null | undefined): boolean {
  const { pro, leaguePasses } = useEntitlements.getState();
  const flagOn = useFeatureFlags.getState().flags['monetize.league_pass'] === true;
  return proForLeague(pro, leaguePasses, leagueId, flagOn, Date.now());
}
