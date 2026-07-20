import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button } from './chalkline';
import PositionChip from './PositionChip';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import {
  chalk,
  ink,
  radii,
  scrim,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';
import type { Player } from '../shared/types';

// Shared player long-press context menu (teardown S3 PRD-02, flag
// `ux.player_context_menu`). ONE long-press vocabulary for player rows on
// command surfaces (Trades deck, Matches tiles): holding a player opens
// this sheet instead of firing an invisible single-purpose gesture. The
// header doubles as the "Player info" disclosure (name + position + team +
// age); the rows below are the per-surface commands the caller passes in
// (Mark/remove untouchable, Swap player, …). Drag-lift keeps its long-press
// meaning only inside explicit reorder surfaces (Tiers, ManualRanks) —
// those never mount this menu.
//
// Chalkline bottom-sheet construction mirrors SwapPlayerSheet; slide falls
// back to fade under Reduce Motion (`useReducedMotionSafe`).

export interface PlayerMenuAction {
  key: string;
  label: string;
  /** Muted single-line hint under the label (optional). */
  hint?: string;
  onPress: () => void;
}

interface Props {
  visible: boolean;
  player: Player | null;
  actions: PlayerMenuAction[];
  onClose: () => void;
}

export default function PlayerContextMenu({ visible, player, actions, onClose }: Props) {
  const reduceMotion = useReducedMotionSafe();
  const meta = player
    ? [player.team || 'FA', player.age != null ? `${player.age} yo` : null]
        .filter(Boolean)
        .join(' · ')
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
      <View style={styles.sheet} testID="player-menu">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          {/* Header = the player-info disclosure. */}
          {player ? (
            <View style={styles.header}>
              <PositionChip position={player.position} size="sm" />
              <View style={styles.headerText}>
                <Text style={type.title} numberOfLines={1}>
                  {player.name}
                </Text>
                {meta ? <Text style={type.bodySm}>{meta}</Text> : null}
              </View>
            </View>
          ) : null}
          {actions.map((a) => (
            <Pressable
              key={a.key}
              testID={`player-menu.${a.key}`}
              accessibilityRole="button"
              accessibilityLabel={a.label}
              onPress={a.onPress}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
            >
              <Text style={styles.rowLabel}>{a.label}</Text>
              {a.hint ? <Text style={styles.rowHint}>{a.hint}</Text> : null}
            </Pressable>
          ))}
          <Button variant="ghost" label="Cancel" onPress={onClose} style={styles.cancel} />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

// ── Lock glyph — untouchable visible twin (S3 PRD-02) ────────────────────
// Local Svg (Chalkline construction: 20×20 viewBox, stroke 1.75, square
// caps) rather than an Icon.tsx addition, to keep this wave conflict-free
// with parallel chalkline owners. Fold into chalkline/Icon at flag cleanup.
export function LockGlyph({
  size = 14,
  color = chalk.dim,
  locked = true,
}: {
  size?: number;
  color?: string;
  locked?: boolean;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke={color}
      strokeWidth={1.75}
      strokeLinecap="square"
    >
      <Rect x={4} y={9} width={12} height={8} />
      {locked ? (
        // Closed shackle.
        <Path d="M7 9V6a3 3 0 016 0v3" />
      ) : (
        // Open shackle (swung left).
        <Path d="M7 9V6a3 3 0 015.6-1.5" />
      )}
    </Svg>
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
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    marginBottom: space.xs,
  },
  headerText: { flex: 1, gap: 2 },
  row: {
    minHeight: 48,
    justifyContent: 'center',
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowLabel: { ...type.body, color: chalk.base },
  rowHint: { ...type.bodySm, color: chalk.dim, marginTop: 2 },
  cancel: { marginTop: space.sm },
});
