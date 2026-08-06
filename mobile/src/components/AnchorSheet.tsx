import React, { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMutation } from '@tanstack/react-query';

import { Button } from './chalkline';
import PositionChip from './PositionChip';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import { saveAnchor, type AnchorKey, type AnchorSaveResponse, type AnchorVia }
  from '../api/rankings';
import { ANCHOR_ROWS } from '../utils/anchorRows';
import { TIER_LABEL } from '../utils/tierBands';
import { chalk, ice, ink, radii, scrim, semantic, shadowSheet, space, type }
  from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { Position, Tier } from '../shared/types';

// Anchor sheet — "what's this guy worth?" answered without leaving the
// screen you asked it on (draft-extensions W1, plan §4 / lld §4.1.4).
//
// This is NET-NEW (HLD RB-11): `saveAnchor` had exactly ONE caller and it
// was a full SCREEN (PickAnchorScreen). The plan's phrase "the anchor
// sheet" named a component that did not exist. What is reused is what
// matters — the shipped WRITE LANE (`saveAnchor` → POST /api/anchor/save,
// unchanged apart from the request-only `via`) and the shipped RUNG GRID
// (`utils/anchorRows`, extracted from the wizard rather than copied), so
// no second anchor vocabulary can appear.
//
// THE ANCHOR LANE ONLY. This sheet must never reach /api/tiers/save,
// save_tiers_position or the merged-band path — that is the one
// construction that can destroy a board, and it is pinned by AST + runtime
// tests in backend/tests/test_draft_extensions_w1.py.
//
// Three gestures, no confirm step: long-press → "Set my value" → a rung.
// D1's bar is "≤3 taps AND no navigation away", which leaves no budget for
// a fourth. Mis-taps are recovered by CORRECTION, not by a fake undo: the
// sheet stays open after a save with every rung still live, so fixing a
// wrong answer is one more tap on the same grid. (A true undo would have to
// restore the player's prior Elo, and the anchor lane has no such call —
// inventing one would be exactly the kind of new write path W1 forbids.)
//
// Modal ⇒ no FeedbackFAB (root CLAUDE.md: "Exceptions: modals/sheets").

export interface AnchorTarget {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  /** The row's current board value, if it has one — for the "was" line. */
  value?: number | null;
  valued?: boolean;
}

interface Props {
  visible: boolean;
  target: AnchorTarget | null;
  /** Which surface asked. Rides the request only; the response is unchanged. */
  via?: AnchorVia;
  onClose: () => void;
  /** Fired with the server's authoritative result so the host can re-price
   *  its cached board. Never fired on failure — nothing was written. */
  onSaved?: (playerId: string, res: AnchorSaveResponse) => void;
}

export default function AnchorSheet({
  visible,
  target,
  via,
  onClose,
  onSaved,
}: Props) {
  const reduceMotion = useReducedMotionSafe();
  const [placed, setPlaced] = useState<AnchorSaveResponse | null>(null);

  // A fresh player is a fresh question — never show the last guy's answer.
  useEffect(() => {
    setPlaced(null);
  }, [target?.player_id, visible]);

  const mutation = useMutation({
    mutationFn: ({ playerId, anchor }: { playerId: string; anchor: AnchorKey }) =>
      saveAnchor(playerId, anchor, via),
    onSuccess: (res, vars) => {
      haptics.selection();
      setPlaced(res);
      onSaved?.(vars.playerId, res);
    },
  });

  const meta = target
    ? [target.team || 'FA', target.position || null].filter(Boolean).join(' · ')
    : '';

  return (
    <Modal
      visible={visible}
      transparent
      animationType={reduceMotion ? 'fade' : 'slide'}
      onRequestClose={onClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet} testID="anchor-sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          {target ? (
            <View style={styles.header}>
              <PositionChip position={target.position as Position} size="sm" />
              <View style={styles.headerText}>
                <Text style={type.title} numberOfLines={1}>
                  {target.name}
                </Text>
                {meta ? <Text style={type.bodySm}>{meta}</Text> : null}
              </View>
            </View>
          ) : null}

          <Text style={styles.question}>Worth how much in draft capital?</Text>

          {ANCHOR_ROWS.map((row, i) => (
            <View key={i} style={styles.buttonRow}>
              {row.map(({ key, label }) => (
                <Button
                  key={key}
                  testID={`anchor-sheet.rung.${key}`}
                  label={label}
                  compact
                  disabled={mutation.isPending || !target}
                  onPress={() =>
                    target &&
                    mutation.mutate({ playerId: target.player_id, anchor: key })
                  }
                  style={styles.rungBtn}
                />
              ))}
            </View>
          ))}

          {mutation.isError ? (
            <Text testID="anchor-sheet.error" style={styles.error}>
              Save failed — check your connection and tap again.
            </Text>
          ) : placed ? (
            <Text testID="anchor-sheet.result" style={styles.result}>
              Set to{' '}
              {placed.tier
                ? (TIER_LABEL[placed.tier as Tier] ?? placed.tier)
                : 'No value'}
              {' · '}≈ {Math.round(placed.value).toLocaleString()}
              {'\n'}
              <Text style={styles.resultHint}>
                Tap another rung to change it.
              </Text>
            </Text>
          ) : (
            <Text style={styles.hint}>
              Anchors are pick-denominated on purpose: a 1st means the same
              thing on every team, so this value lands on your board
              everywhere.
            </Text>
          )}

          <Button
            testID="anchor-sheet.done"
            variant="ghost"
            label="Done"
            onPress={onClose}
            style={styles.done}
          />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  headerText: { flex: 1, gap: 2 },
  question: { ...type.label, textAlign: 'center' },
  buttonRow: { flexDirection: 'row', gap: space.sm },
  rungBtn: { flex: 1 },
  result: { ...type.data, textAlign: 'center', color: ice.base },
  resultHint: { ...type.bodySm, color: chalk.dim },
  hint: { ...type.bodySm, textAlign: 'center', color: chalk.dim },
  error: { ...type.bodySm, textAlign: 'center', color: semantic.neg },
  done: { marginTop: space.xs },
});
