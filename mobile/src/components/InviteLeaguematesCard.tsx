import React from 'react';
import { View, StyleSheet } from 'react-native';

import { chalk, space, type, fonts } from '../theme/chalkline';
import { TickLabel, Button, Card, Text } from './chalkline';
import { inviteSocialProof, INVITE_RATIONALE } from '../utils/inviteSocialProof';

// P1-5 (audit A-14) — the promoted league invite on League Home.
//
// WHAT THIS REPLACES. Today the only invite affordance on this screen is an
// underlined text link spliced into a sentence inside LeagueProgressModule
// ("…unlocks mutual matches. Invite them"). That link is a nested <Text>, so
// it has no 44pt target — the component says so itself — and it disappears
// entirely once the league's unlocks complete, leaving a fully-unlocked
// league with un-joined members no way to invite anybody. This card is a
// real Button: 44pt, accessibilityRole="button", present regardless of
// unlock state. Closing that documented deviation is the point, not a side
// effect.
//
// BUTTON WEIGHT IS `secondary`, DELIBERATELY (operator decision D-P1-13 ·
// OG-13). League Home's day-one action row already owns the screen's
// primary ("Find a trade", solid ice) and this card sits directly above it.
// Two adjacent solid-ice buttons would be a Chalkline hierarchy break and
// would put the invite in competition with the action that delivers value
// today. The existing primary keeps precedence.
//
// NO PLATFORM GATE — and that was checked, not assumed. The P1-5 plan
// recommended withholding this card on ESPN/MFL/Fleaflicker leagues on the
// premise that invite links "cannot resolve" there. The invite path was
// traced end to end and the premise is only half true, in a way that argues
// against the gate:
//   • Nothing platform-conditional exists anywhere in the emit path —
//     buildInviteUrl (InviteLeaguematesBanner), the /app/league/join/<id>
//     redirect (backend/server.py), the mobile ?league= deep-link reader
//     (utils/deepLinks.ts) and LeagueJoinScreen all handle every platform
//     identically. The link is a plain URL and it is shareable anywhere.
//   • What actually degrades is the RECIPIENT's landing: auto-pin can only
//     match a league already in the invitee's own list, and a linked-platform
//     league only enters that list once the invitee authenticates to that
//     platform themselves (backend/database.py load_espn_leagues_for_user
//     filters on league_members + leagues.platform). On web it is worse —
//     the list the ?league= auto-select searches is built from
//     /api/sleeper/leagues, which excludes numeric platform-native ids
//     (backend/database.py:6107), so a non-Sleeper id can never match.
//   • But the OUTCOME the card asks for is still reachable on mobile: an
//     ESPN leaguemate who installs the app and links their own ESPN account
//     lands in the same league and increments leaguemates_joined.
// Withholding the card would therefore suppress a working outcome while the
// legacy inline link — which emits the identical URL — stays put, so the
// gate would not prevent the degraded journey, only the promoted one. The
// card ships everywhere and every invite event carries the league
// `platform` prop, so how ESPN invites actually convert becomes a measured
// question instead of an assumed one.

interface Props {
  /** Leaguemates excluding the viewing user (/api/league/summary aggregate). */
  totalMates:  number;
  /** How many of those have joined FTF (same aggregate, same request). */
  joinedMates: number;
  /** `!!summaryQuery.data` — the object having ARRIVED, not the numbers
   *  being non-zero. A 0 produced by absence is indistinguishable from a 0
   *  produced by truth, so the card waits for the object. */
  summaryArrived: boolean;
  /** Delegates to shareInvite({ surface: 'league_home' }). A callback rather
   *  than the card sharing directly, so the screen keeps ONE invite handler
   *  serving both this card and LeagueProgressModule's inline link — one
   *  handler, one surface value, no chance of the two reporting differently. */
  onShare: () => void;
}

export default function InviteLeaguematesCard({
  totalMates,
  joinedMates,
  summaryArrived,
  onShare,
}: Props) {
  // L1 — no data yet. No skeleton, no em dash, no placeholder: an invite
  // card that appears with a fabricated number is worse than one that
  // appears a beat late.
  if (!summaryArrived) return null;
  // L2 — one call decides both "is there anything to say" and "what does it
  // say". Covers the solo/unknown league and the everyone-joined case
  // (D-P1-13 · PR-10: absent, not congratulatory) without a second
  // predicate that could drift from the sentence.
  const proof = inviteSocialProof(totalMates, joinedMates);
  if (proof === null) return null;

  return (
    <View testID="league.invite-card" style={styles.wrap}>
      <TickLabel>Grow your league</TickLabel>
      <Card>
        <View style={styles.body}>
          <Text testID="league.invite-social-proof" style={styles.proof}>
            {proof}
          </Text>
          <Text style={type.bodySm}>{INVITE_RATIONALE}</Text>
          <Button
            testID="league.invite-cta"
            label="Invite leaguemates"
            variant="secondary"
            onPress={onShare}
          />
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  body: { gap: space.sm },
  proof: {
    ...type.title,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
  },
});
