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
// back to the hub's Trade DNA panel (navigates to TradesHome with
// `editDna: true`, which auto-expands the in-place editor).
//
// Deliberately self-contained (own session read, own prefs query on the
// shared ['league-prefs', leagueId] cache key, own flag read) so
// TradesScreen — owned by another agent this round — mounts it with a
// single line and nothing else.
//
// Renders null unless flag `trade.outlook_direction` is live AND the
// resolved outlook is directional. Resolution mirrors the engine's
// (backend #175): the declared team_outlook, else the backend's
// inference — when the bias came from an inference the copy says
// "you look" instead of "you're", so the receipt never overclaims.
// `not_sure` / nothing resolved ⇒ the engine applies no bias ⇒ no
// receipt. Flare tick + border-free quiet bar per the mock (flare =
// informational highlight, same family as the board-refresh note).

const LEAN: Record<string, { lean: string; name: string }> = {
  rebuilder: { lean: 'young + picks', name: 'Rebuilding' },
  jets: { lean: 'max youth + picks', name: 'Tanking' },
  championship: { lean: 'vets + win-now', name: 'All-in' },
  contender: { lean: 'balanced', name: 'Contending' },
};

export default function OutlookBiasReceipt({ navigation }: { navigation: any }) {
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
  const resolved = declared ?? prefsQuery.data?.inferred_outlook ?? null;
  const entry = resolved ? LEAN[resolved] : undefined;
  if (!directionOn || !entry) return null;

  return (
    <View testID="trades.outlook-receipt" style={styles.receipt}>
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
        onPress={() => navigation?.navigate?.('TradesHome', { editDna: true })}
      >
        {({ pressed }) => (
          <Text style={[styles.change, pressed && { color: ice.press }]}>
            Change
          </Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  receipt: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: space.sm,
    marginBottom: space.md,
  },
  tick: { width: 3, height: 12, backgroundColor: flare.base },
  text: { ...type.bodySm, flex: 1, color: chalk.dim },
  strong: { color: chalk.base, fontFamily: fonts.uiSemi },
  change: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
});
