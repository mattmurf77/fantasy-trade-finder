import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Icon, Text } from '../chalkline';
import { chalk, fonts, ink, radii, space, type } from '../../theme/chalkline';

// One Home hub status row (scope.md D1): a 40pt full-width row inside the
// shared status card. The WHOLE row is the button and "View ›" is only its
// visual affordance, so there is never a nested control. Prop-driven: the
// hub owns the query behind each row, its analytics and its navigation.
//
// States, as drawn in the mockup's D edge states:
//   loading     — static ink-2 bar, no shimmer; not tappable.
//   error       — "Couldn't load", the affordance becomes Retry (onRetry).
//   unavailable — dim copy, no affordance, not tappable (ESPN/MFL standings,
//                 fewer than 3 valued rosters).
//   ready       — value + optional detail, affordance `action` (onPress).

export type StatusRowState = 'loading' | 'error' | 'unavailable' | 'ready';

interface Props {
  label: string;
  testID: string;
  state: StatusRowState;
  value?: string;
  detail?: string | null;
  /** Data numerals ("5–1", "5th of 12") render in Plex Mono. */
  valueMono?: boolean;
  detailMono?: boolean;
  /** Ready-state affordance word: "View", or "Set" when nothing is set yet. */
  action?: string;
  onPress?: () => void;
  onRetry?: () => void;
  /** The card's last row draws no bottom hairline. */
  last?: boolean;
}

export default function StatusRow({
  label,
  testID,
  state,
  value,
  detail,
  valueMono = false,
  detailMono = false,
  action = 'View',
  onPress,
  onRetry,
  last = false,
}: Props) {
  const pressable = state === 'ready' || state === 'error';
  const a11yLabel =
    state === 'loading'
      ? `${label}, loading`
      : state === 'error'
        ? `${label}, couldn't load. Retry`
        : state === 'unavailable'
          ? `${label}, ${value ?? ''}`
          : `${label}, ${value ?? ''}${detail ? `, ${detail}` : ''}. ${action}`;
  return (
    <Pressable
      testID={testID}
      disabled={!pressable}
      onPress={state === 'error' ? onRetry : onPress}
      accessibilityRole={pressable ? 'button' : undefined}
      accessibilityLabel={a11yLabel}
      accessibilityState={{ disabled: !pressable }}
      style={({ pressed }) => [styles.row, !last && styles.divider, pressed && styles.pressed]}
    >
      <Text scale="dense" style={[type.label, styles.key]}>
        {label}
      </Text>
      <View style={styles.value}>
        {state === 'loading' ? (
          <View style={styles.skel} />
        ) : state === 'error' ? (
          <Text style={styles.dim}>Couldn’t load</Text>
        ) : state === 'unavailable' ? (
          <Text style={styles.dim}>{value}</Text>
        ) : (
          <>
            <Text style={[styles.main, valueMono && styles.mainMono]}>{value}</Text>
            {detail ? (
              <Text style={[styles.detail, detailMono && styles.detailMono]}>{detail}</Text>
            ) : null}
          </>
        )}
      </View>
      {state === 'error' ? (
        <View style={styles.go}>
          <Icon name="reload" size={14} />
          <Text style={styles.goText}>Retry</Text>
        </View>
      ) : state === 'unavailable' ? null : (
        <View style={styles.go}>
          <Text style={styles.goText}>{action}</Text>
          <Icon name="chevron-right" size={14} />
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // 40pt by operator ruling (R3) — under the 44pt floor, but the target is
  // the full card width. minHeight so Dynamic Type can grow it.
  row: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
  },
  divider: { borderBottomWidth: 1, borderBottomColor: ink.line },
  pressed: { backgroundColor: ink.ink3 },
  key: { width: 100 },
  value: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.xs,
  },
  main: { fontFamily: fonts.uiSemi, fontSize: 14, lineHeight: 20, color: chalk.base },
  mainMono: { fontFamily: fonts.dataSemi, fontVariant: ['tabular-nums'] },
  detail: { fontFamily: fonts.ui, fontSize: 12, lineHeight: 16, color: chalk.dim },
  detailMono: { fontFamily: fonts.data, fontVariant: ['tabular-nums'] },
  dim: type.bodySm,
  skel: { width: 96, height: 12, backgroundColor: ink.ink2, borderRadius: radii.xs },
  go: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  goText: { fontFamily: fonts.uiMedium, fontSize: 13, color: chalk.dim },
});
