import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getPaywallConfig } from '../api/billing';
import { useFlag } from './useFeatureFlags';
import { useSession } from './useSession';
import { subscriptionSessionState } from './subscriptionSession';

// Tip jar C1 (PR #569's docs/plans/tip-jar/plan.md §3, head-eng GO
// 2026-11-01): keeps ['paywall-config','ios'] warm so the Settings tip row
// (useTipsOffered, a never-fetching subscriber) can see `tips[]` for a user
// who never opened the paywall. Same key and queryFn as PaywallScreen,
// TipJarScreen and useTipsOffered: one cache entry. Mounted ONCE, under
// RootNav's `Main`, which stays mounted beneath every Settings push, so the
// entry is never GC'd and the Settings hub stays zero-network. Verified
// sessions only (#474 S2d; demo, unverified and unknown fetch nothing). The
// queryClient default is `refetchOnWindowFocus: false`, so it is turned on
// here: App.tsx bridges focusManager to AppState, and a foreground past
// `staleTime` refetches.
//
// Not verified ⇒ the entry is REMOVED (release-lead QA on #575): nothing else
// clears it, and gcTime is 30 min, so a demo or unverified session started in
// the same process would otherwise read a verified session's `tips[]`. A user
// change (verification back to unknown) lands here. So does a sign-out, but
// not at its first `set`: a null user with `session_verified` true still
// counts as verified. The clear comes from sign-out's second `set`
// (verification → null), or from the next `Main` mount if `Main` unmounts in
// between. Keyed on `verified` alone, so it runs once per drop (or on a
// not-verified mount), never while this observer is enabled, and never loops.

export function useWarmPaywallConfig(): void {
  const queryClient = useQueryClient();
  const paywallOn = useFlag('monetize.paywall');
  const verified = useSession((s) => subscriptionSessionState(s) === 'verified');
  useQuery({
    queryKey: ['paywall-config', 'ios'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: paywallOn && verified,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
  useEffect(() => {
    if (!verified) queryClient.removeQueries({ queryKey: ['paywall-config'] });
  }, [verified, queryClient]);
}

/** Renders nothing; mounts the warm observer. */
export function WarmPaywallConfig(): null {
  useWarmPaywallConfig();
  return null;
}
