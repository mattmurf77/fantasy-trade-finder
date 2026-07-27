import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import PositionChip from './PositionChip';
import { Icon, TickLabel } from './chalkline';
import type { CalcEvener } from '../api/calc';
import { chalk, ice, ink, radii, space, type } from '../theme/chalkline';

interface Props {
  eveners: CalcEvener[];
  /** Section label, e.g. "Recommended to even it — add from your roster". */
  title: string;
  onAdd: (evener: CalcEvener) => void;
}

// "Recommended to even it" rows (DynastyGM teardown 2026-07-26): the one-tap
// evener assets POST /api/trade/evaluate returns (`eveners`) when a trade is
// uneven — up to three single assets (players or owned picks; picks show
// their pick label) plus at most one 2-piece package row. Tapping + adds the
// asset(s) to the side `gap.add_to` points at (the host wires that) and the
// evaluate re-run refreshes or clears these rows as the trade evens. Renders
// nothing without candidates — honest empty state. Chalkline: ice = action
// (the + affordance), transparent-bordered rows, no new hues.
export default function EvenerRows({ eveners, title, onAdd }: Props) {
  if (eveners.length === 0) return null;
  return (
    <View style={styles.wrap}>
      <TickLabel>{title}</TickLabel>
      {eveners.map((e) => (
        <View
          key={e.id}
          testID={`calc.evener.${e.id}`}
          accessible={false}
          style={styles.row}
        >
          <PositionChip position={e.position} size="sm" />
          <Text style={styles.name} numberOfLines={1}>
            {e.name}
          </Text>
          <Text style={[type.data, styles.value]}>
            {Math.round(e.value).toLocaleString()}
          </Text>
          <Pressable
            testID={`calc.evener-add.${e.id}`}
            style={({ pressed }) => [styles.addBtn, pressed && styles.addBtnPressed]}
            onPress={() => onAdd(e)}
            accessibilityRole="button"
            accessibilityLabel={`Add ${e.name} to even the trade`}
            hitSlop={6}
          >
            <Icon name="plus" size={16} color={ice.base} />
          </Pressable>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingVertical: space.xs,
    paddingHorizontal: space.md,
    minHeight: 44,
  },
  name: { ...type.bodySm, color: chalk.base, flex: 1 },
  value: { minWidth: 56, textAlign: 'right' },
  addBtn: {
    minWidth: 32,
    minHeight: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ice.base,
  },
  addBtnPressed: { backgroundColor: ink.ink3 },
});
