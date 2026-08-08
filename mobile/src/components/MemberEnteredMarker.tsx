import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Icon } from './chalkline';
import type { PickSource } from '../api/pickAssignment';
import { navigationRef } from '../navigation/RootNav';
import { useFlag } from '../state/useFeatureFlags';
import { chalk, flare, fonts, ice, ink, radii, space } from '../theme/chalkline';

// ── D17: provenance is inescapable (draft-extensions W3 M-C) ─────────────
//
// An ESPN league has no platform record of pick ownership, so under
// `picks.assign` a LEAGUEMATE types the grid in and FTF becomes the league's
// system of record. Under `picks.assign_tradeable` those asserted rows reach
// trade math — the calculator, the eveners, the swap sheet, the power
// rankings. Nothing on ESPN's side will ever contradict a wrong grid
// (plan §6.9.3), and the person harmed by a bad assignment is usually not
// the person who made it (§6.9.1). So every surface that renders a PRICE for
// an asserted pick must say so, and must offer the fix in ONE action.
//
// This component IS that rule, and it self-gates on BOTH conditions so a
// host can render it unconditionally beside the price:
//
//   1. `picks.assign_tradeable` off  ⇒ null. The flag ships OFF and is
//      backend-owned; `useFlag` on an absent key is falsy, so an app built
//      before the flag exists is fail-closed, not fail-open.
//   2. `source !== 'user'`           ⇒ null. Platform-owned picks (Sleeper,
//      MFL, and any future ESPN sync) are facts, not assertions, and a
//      marker on them would be a lie in the other direction.
//
// Rendering it unconditionally is the point: `mobile/tests/
// check-member-entered-marker.js` parses the real TSX and FAILS if the
// marker drifts inside a ternary or `&&` on any of the five surfaces. A grep
// would happily pass on a marker that had become conditional, which is
// exactly the regression worth catching — a priced pick with the marker
// suppressed is indistinguishable from platform truth.
//
// Chalkline (ADR-004/005): flare tick = informational highlight, 11px UI
// text at the scale floor in `chalk.dim`, one small ice chevron for the
// action. Deliberately quieter than the price it annotates (`type.data`,
// 13px `chalk.base`) — a marker that shouts louder than the number it
// qualifies gets tuned out, and it must not read as a warning: an assigned
// grid is the intended state, not an error.

/** The registered cross-client copy. Three clients say EXACTLY this string
 *  (docs/cross-client-invariants.md § Asserted pick ownership). Never
 *  abbreviate, re-word or truncate it — provenance that varies by surface
 *  teaches users the marker is decorative. */
export const MEMBER_ENTERED_COPY = 'Member-entered — not verified with ESPN';

export interface Props {
  /** Server-authoritative provenance for THIS asset. Absent on players,
   *  demo assets and platform-owned picks — all of which render nothing. */
  source?: PickSource | string | null;
  /** `draft_picks.pick_id` — the slot the correction link focuses. */
  pickId?: string | null;
  /** The pick's season; lands the grid on the right season tab even when
   *  the payload no longer contains `pickId` (a re-seed with fewer rounds). */
  season?: number | null;
  /** The league whose grid holds the slot. */
  leagueId?: string | null;
  testID?: string;
}

/** The one-action correction path (plan §6, M-C): the shipped assignment
 *  grid, deep-linked to the exact slot — it switches to that season, expands
 *  the round and highlights the row. Uses `navigationRef` rather than a
 *  navigation prop because three of the five surfaces are modals/sheets
 *  rendered far from any screen that owns a navigator. */
export function openPickCorrection(
  leagueId: string,
  pickId: string,
  season?: number | null,
) {
  if (!navigationRef.isReady()) return;
  navigationRef.navigate('PickAssignment', {
    leagueId,
    season: season ?? undefined,
    focusPickId: pickId,
  });
}

/** THE predicate — one definition, so no surface can read the enum a second
 *  way (and the AST test can pin it). Not a hook: two of the five surfaces
 *  evaluate it per row inside a list renderer. */
export function isMemberEntered(source?: PickSource | string | null): boolean {
  return source === 'user';
}

/** The M-C kill switch. Backend-owned and shipping OFF; `useFlag` on an
 *  absent key is falsy, so a binary built before the flag exists is
 *  fail-closed. Hosts that fold the marker into a row's a11y contract read
 *  it once at the top of their component. */
export function usePicksTradeable(): boolean {
  return useFlag('picks.assign_tradeable');
}

export default function MemberEnteredMarker({
  source,
  pickId,
  season,
  leagueId,
  testID,
}: Props) {
  const tradeable = usePicksTradeable();
  // Both gates, plus the two ids the correction path needs. A marker that
  // cannot route is worse than none: it names a problem and hides the fix.
  if (!tradeable || !isMemberEntered(source) || !pickId || !leagueId) return null;
  return (
    <Pressable
      testID={testID}
      onPress={() => openPickCorrection(leagueId, pickId, season)}
      accessibilityRole="button"
      accessibilityLabel={MEMBER_ENTERED_COPY}
      accessibilityHint="Opens the league's pick assignment grid at this pick"
      hitSlop={6}
      style={({ pressed }) => [styles.marker, pressed && styles.markerPressed]}
    >
      <View style={styles.tick} />
      <Text style={styles.text} numberOfLines={2}>
        {MEMBER_ENTERED_COPY}
      </Text>
      <Icon name="chevron-right" size={12} color={ice.base} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  marker: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    alignSelf: 'flex-start',
    minHeight: 24,
    paddingRight: space.xs,
    borderRadius: radii.xs,
  },
  markerPressed: { backgroundColor: ink.ink3 },
  // Flare = informational highlight (ADR-005); never an action color.
  tick: { width: 3, height: 10, backgroundColor: flare.base },
  text: {
    fontFamily: fonts.ui,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
    flexShrink: 1,
  },
});
