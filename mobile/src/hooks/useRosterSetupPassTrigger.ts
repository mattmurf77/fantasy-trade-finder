import { useCallback, useEffect, useRef } from 'react';

import { useRosterSetup } from '../state/rosterSetup';
import { useMyRosterAssets } from './useMyRosterAssets';
import { shouldPushSetupOnPass } from '../utils/rosterSetup';

// Roster-first setup's ONLY automatic entry (flag `trades.roster_setup`;
// prd §3.1 as amended by the operator 2026-11-10): the setup is pushed on
// the user's FIRST DECLINED Find a Trade suggestion in a league — never on a
// landing focus.
//
// TradesScreen (both the `TradesHome` deck and a pushed `TradeDeck`) calls
// the returned function at the moments a pass has COMMITTED:
//   • a plain pass, right after its swipe write is dispatched and the deck
//     has advanced;
//   • an undo-held pass (`ux.swipe_undo`), when its undo window expires and
//     the held write is flushed — so the push never covers the Undo toast;
//   • a reasoned pass (`feedback.decline_reasons`), right after
//     `commitReasonAdvance()` at its three callers — layer 2 answered, layer 2
//     text sent, or a banked overlay closed — so the push never interrupts
//     or swallows the reason capture.
// The pass itself is untouched: the same events and the same swipe write
// fire before this runs. The push lands ON TOP of the deck, which stays
// mounted at its position underneath.
//
// Gating: the caller passes `enabled = flag on && not demo`. With it false
// the roster reads below are disabled and the function is a no-op, so the
// flag-off pass path is unchanged. The decision itself is the pure
// `shouldPushSetupOnPass` (flag, non-demo league, store hydrated, NO device
// record for the league, non-empty roster, once per league per app session).

const pushedThisSession = new Set<string>();

export function useRosterSetupPassTrigger({
  enabled,
  leagueId,
  userId,
  isDemo,
  navigation,
}: {
  enabled: boolean;
  leagueId: string | null;
  userId: string;
  isDemo: boolean;
  navigation: any;
}): () => void {
  const roster = useMyRosterAssets(leagueId, userId, enabled);
  const hydrated = useRosterSetup((s) => s.hydrated);

  useEffect(() => {
    if (enabled) void useRosterSetup.getState().hydrate();
  }, [enabled]);

  // Players alone decide "has a roster" once rosters answer; with no
  // players, wait for the picks read to settle.
  const assetCount = !roster.rostersReady
    ? null
    : roster.playerIds.length > 0
      ? roster.playerIds.length
      : roster.picksSettled ? roster.assetIds.length : null;

  const latest = useRef({ enabled, leagueId, isDemo, hydrated, assetCount, navigation });
  latest.current = { enabled, leagueId, isDemo, hydrated, assetCount, navigation };

  return useCallback(() => {
    const l = latest.current;
    if (!l.enabled || !l.leagueId) return;
    const go = shouldPushSetupOnPass({
      flagOn: l.enabled,
      leagueId: l.leagueId,
      isDemo: l.isDemo,
      hydrated: l.hydrated,
      // Read at call time, not render time: a record written moments ago
      // (a skip on another entry) must win.
      hasRecord: !!useRosterSetup.getState().byLeague[l.leagueId],
      assetCount: l.assetCount,
      alreadyPushedThisSession: pushedThisSession.has(l.leagueId),
    });
    if (!go) return;
    pushedThisSession.add(l.leagueId);
    l.navigation.navigate('RosterSetup', { entry: 'first_pass' });
  }, []);
}
