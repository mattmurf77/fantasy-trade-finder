// The Mock side of the room's `Real draft | Mock` switch.
//
// Every refusal renders HERE, in the room — the user is never pushed into a
// session screen only to be told it isn't possible. Four honest states, and
// which of them the client can know in advance is decided by the contract,
// not by taste:
//
//   league too small     client-derived (`teams`). The engine sets
//                        `teams = len(owners)` with NO floor (gap G5), so
//                        the threshold is a product call the client makes;
//                        it is `MOCK_MIN_TEAMS` here and nowhere else.
//   class not loaded     derivable in advance from the BOARD's own
//                        `class_not_loaded` notice. The room's "Show last
//                        year's class" toggle must NOT arm this card: the
//                        mock pool is `_rookie_player_ids(state.season)`
//                        with no season override (gap G7), so an armed card
//                        would be a button that lies.
//   live / complete      a mock started mid-draft can never catch up — the
//                        pool is snapshotted at creation and INV-10 forbids
//                        any later platform read — and a mock over a
//                        drafted class is the rejected replay mode. Both
//                        are correctness refusals, not taste.
//   bots not validated   `cpu_model_unvalidated` is returned by POST ONLY
//                        (gap G2): GET with no active row says
//                        `no_active_mock` and nothing about whether a
//                        create would succeed. So this one necessarily
//                        arrives AFTER the tap; the host remembers it and
//                        passes it back down, and from then on the card is
//                        muted without a second request.

import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '../chalkline';
import { chalk, flare, ice, ink, radii, semantic, space, type } from '../../theme/chalkline';

/** A mock needs enough teams for the CPU drafters to take anything
 *  interesting off the board. Client-side because the engine has no floor
 *  (gap G5) — if a `league_too_small` refusal ever lands server-side, this
 *  constant should be deleted rather than kept in sync. */
export const MOCK_MIN_TEAMS = 6;

export interface MockBlock {
  title: string;
  body: string;
  /** The dead CTA's label — it states the condition, never "Start". */
  cta: string;
  testID: string;
}

export default function MockEntryPanel({
  loading,
  errorText,
  block,
  meta,
  headline,
  body,
  primary,
  secondary,
  retry,
}: {
  loading?: boolean;
  errorText?: string | null;
  /** Non-null ⇒ muted card + dead CTA. Wins over everything below. */
  block?: MockBlock | null;
  /** "4 rounds · 12 teams · linear · order randomized". */
  meta?: string | null;
  headline?: string;
  body?: string;
  primary?: { label: string; onPress: () => void; testID: string };
  secondary?: { label: string; onPress: () => void; testID: string };
  /** Rendered inside the `errorText` branch. No reachable state of this
   *  panel may render zero interactive controls (#292 dead-end 2): the error
   *  branch shipped with none, and react-query holds a mutation's `isError`
   *  until the next `mutate`/`reset`, so one failed create replaced the card
   *  permanently. */
  retry?: { label: string; onPress: () => void; testID: string };
}) {
  if (block) {
    return (
      <View testID={block.testID} style={[styles.card, styles.cardMuted]}>
        <Text style={[styles.title, { color: chalk.dim }]}>{block.title}</Text>
        <Text style={styles.body}>{block.body}</Text>
        <Button label={block.cta} variant="secondary" disabled onPress={() => {}} />
      </View>
    );
  }

  if (loading) {
    return (
      <View testID="mock-entry.loading" style={styles.center}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }

  if (errorText) {
    return (
      <View testID="mock-entry.error" style={[styles.card, styles.cardMuted]}>
        <Text style={styles.error}>{errorText}</Text>
        {retry ? (
          <View style={styles.btnRow}>
            <View style={styles.btnCell}>
              <Button
                testID={retry.testID}
                label={retry.label}
                variant="primary"
                onPress={retry.onPress}
              />
            </View>
          </View>
        ) : null}
      </View>
    );
  }

  return (
    <View testID="mock-entry.card" style={styles.card}>
      <Text style={styles.title}>{headline}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
      {meta ? <Text style={styles.meta}>{meta}</Text> : null}
      <View style={styles.btnRow}>
        {primary ? (
          <View style={styles.btnCell}>
            <Button
              testID={primary.testID}
              label={primary.label}
              variant="primary"
              onPress={primary.onPress}
            />
          </View>
        ) : null}
        {secondary ? (
          <View style={styles.btnCell}>
            <Button
              testID={secondary.testID}
              label={secondary.label}
              variant="ghost"
              onPress={secondary.onPress}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    // Flare = informational highlight (ADR-005). Ice stays on the CTA.
    borderColor: flare.base,
    borderRadius: radii.sm,
    padding: space.md,
    gap: space.sm,
  },
  cardMuted: { borderColor: ink.line },
  title: { ...type.title, color: chalk.base },
  body: { ...type.bodySm, color: chalk.dim },
  meta: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  btnRow: { flexDirection: 'row', gap: space.sm },
  btnCell: { flex: 1 },
  error: { ...type.bodySm, color: semantic.neg },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.xl },
});
