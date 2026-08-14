import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { ink, chalk, ice, flare, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { getLeaguePreferences } from '../api/league';

// #231 — deck bias receipt (approved mock mockups/polish-lab-2026-08/
// trade-dna-outlook-v3.html, row 2): one quiet line above the finder deck
// connecting its shape to the user's outlook, with an ice "Change" link
// into the Trade DNA editor. #246 (guided-first landing): with the hub
// unrouted, Change no longer navigates to TradesHome {editDna:true} — the
// host passes `onChange`, which opens the DNA editor as a bottom sheet
// OVER the deck (TradeDnaSheet), so the user watches their bias change
// the trades behind it.
//
// Deliberately self-contained otherwise (own session read, own prefs
// query on the shared ['league-prefs', leagueId] cache key, own flag
// read) so TradesScreen mounts it with a single line and nothing else.
//
// Renders null unless flag `trade.outlook_direction` is live AND the
// resolved outlook is directional. Resolution mirrors the engine's
// (backend #175): the declared team_outlook, else the backend's
// inference — when the bias came from an inference the copy says
// "you look" instead of "you're", so the receipt never overclaims.
// `not_sure` / nothing resolved ⇒ the engine applies no bias ⇒ no
// receipt. Flare tick + border-free quiet bar per the mock (flare =
// informational highlight, same family as the board-refresh note).

// #253 — CANONICAL DISPLAY ORDER: All-in → Contending → Rebuilding →
// Tanking. This is a lookup, not a rendered list, but it is kept in the
// canonical order so the four outlooks read the same way in every file.
const LEAN: Record<string, { lean: string; name: string }> = {
  championship: { lean: 'vets + win-now', name: 'All-in' },
  contender: { lean: 'balanced', name: 'Contending' },
  rebuilder: { lean: 'young + picks', name: 'Rebuilding' },
  jets: { lean: 'max youth + picks', name: 'Tanking' },
};

// #254 — the receipt is THE outlook surface on the deck, but it can
// legitimately render nothing (flag off, or the resolved outlook isn't
// directional). TradesScreen suppresses its own duplicate outlook row
// exactly when this returns true, so the two surfaces can never both
// appear and can never both vanish. One table, two consumers.
export function outlookReceiptCovers(
  directionOn: boolean,
  declared: string | null | undefined,
  inferred: string | null | undefined,
): boolean {
  if (!directionOn) return false;
  const resolved = declared ?? inferred ?? null;
  return !!resolved && !!LEAN[resolved];
}

export default function OutlookBiasReceipt({
  onChange,
  details,
}: {
  onChange: () => void;
  /** #315 — optional dim second row summarizing the sheet's OTHER
   *  configurations (chasing/shopping positions, trade-idea lane,
   *  untouchables count), composed by the HOST from state it already owns
   *  — the receipt stays self-contained for row 1, presentational for
   *  row 2. Empty/absent ⇒ row 1 renders exactly the pre-#315 banner.
   *  The banner caps at two rows ("can spill to two rows", never three):
   *  this row is one ellipsized line. Team scope and specific players are
   *  deliberately not summarized here — those are the interactive filters
   *  #314 mounted directly below the banner. */
  details?: string;
}) {
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const directionOn = useFlag('trade.outlook_direction');

  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: directionOn && !!leagueId,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const declared = prefsQuery.data?.team_outlook ?? null;
  const inferred = prefsQuery.data?.inferred_outlook ?? null;
  const resolved = declared ?? inferred ?? null;
  const entry = resolved ? LEAN[resolved] : undefined;
  // Same predicate TradesScreen gates its duplicate row on (#254).
  if (!outlookReceiptCovers(directionOn, declared, inferred) || !entry) {
    return null;
  }

  return (
    <View testID="trades.outlook-receipt" style={styles.receipt}>
      <View style={styles.row}>
        <View style={styles.tick} />
        <Text style={styles.text} numberOfLines={2}>
          Leaning <Text style={styles.strong}>{entry.lean}</Text> —{' '}
          {declared ? "you're" : 'you look'}{' '}
          <Text style={styles.strong}>{entry.name}</Text>.
        </Text>
        <Pressable
          testID="trades.outlook-receipt.change"
          accessibilityRole="button"
          accessibilityLabel="Change outlook"
          hitSlop={8}
          onPress={onChange}
        >
          {({ pressed }) => (
            <Text style={[styles.change, pressed && { color: ice.press }]}>
              Change
            </Text>
          )}
        </Pressable>
      </View>
      {/* #315 — row 2, only when the host composed a non-empty summary.
          One dim ellipsized line (13pt bodySm ≥ the 11px floor); no new
          colors, ink/chalk only. Gated on `details` so the no-other-config
          state renders exactly today's one-row banner. */}
      {details ? (
        <Text
          testID="trades.outlook-receipt.details"
          style={styles.details}
          numberOfLines={1}
        >
          {details}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  receipt: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: space.sm,
    marginBottom: space.md,
    gap: 2,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tick: { width: 3, height: 12, backgroundColor: flare.base },
  text: { ...type.bodySm, flex: 1, color: chalk.dim },
  strong: { color: chalk.base, fontFamily: fonts.uiSemi },
  change: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  // Indented past the flare tick (3pt) + the row gap so the summary reads
  // as a sub-line of the lean sentence, not a second tick row.
  details: { ...type.bodySm, color: chalk.dim, marginLeft: 3 + space.sm },
});
