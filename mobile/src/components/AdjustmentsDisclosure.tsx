import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Icon } from './chalkline';
import type { CalcAdjustment } from '../api/calc';
import { chalk, ink, semantic, space, type } from '../theme/chalkline';

interface Props {
  adjustments?: { give: CalcAdjustment[]; receive: CalcAdjustment[] };
  naiveTotals?: { give: number; receive: number };
  /** Displayed (adjusted) side totals — the verdict's give/receive values. */
  giveTotal: number;
  receiveTotal: number;
}

// "Value adjustments" disclosure (DynastyDealer teardown 2026-07-26): a
// collapsed-by-default row under the calculator verdict that, expanded,
// itemizes why each side's displayed package value differs from the naive
// sum of its asset values ("sum of parts N → M"): labeled rows with a signed
// amount (pos green / neg red) and a plain-language why. Renders nothing
// when the server sent no adjustments — displayed totals never change; this
// is pure transparency. Used by ConsensusVerdictCard and the In-league
// verdict. Chalkline: dim informational text, no new hues.
export default function AdjustmentsDisclosure({
  adjustments,
  naiveTotals,
  giveTotal,
  receiveTotal,
}: Props) {
  const [open, setOpen] = useState(false);
  const sides = (['give', 'receive'] as const).filter(
    (s) => (adjustments?.[s] ?? []).length > 0,
  );
  if (!adjustments || sides.length === 0) return null;

  const totals = { give: giveTotal, receive: receiveTotal };
  const sideLabel = { give: 'You send', receive: 'You receive' } as const;
  const fmt = (n: number) => Math.round(n).toLocaleString();
  const signed = (n: number) => (n > 0 ? `+${fmt(n)}` : fmt(n));

  return (
    <View style={styles.wrap}>
      <Pressable
        testID="calc.adjustments.toggle"
        onPress={() => setOpen((o) => !o)}
        accessibilityRole="button"
        accessibilityLabel={open ? 'Hide value adjustments' : 'Show value adjustments'}
        style={styles.toggle}
        hitSlop={6}
      >
        <Text style={[type.label, styles.toggleText]}>Value adjustments</Text>
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={14} color={chalk.dim} />
      </Pressable>
      {open
        ? sides.map((side) => (
            <View key={side} style={styles.side}>
              <View style={styles.lineBetween}>
                <Text style={[type.bodySm, styles.sideLabel]}>{sideLabel[side]}</Text>
                {naiveTotals ? (
                  <Text style={[type.bodySm, styles.sumLine]}>
                    Sum of parts {fmt(naiveTotals[side])} → {fmt(totals[side])}
                  </Text>
                ) : null}
              </View>
              {adjustments[side].map((row) => (
                <View
                  key={row.key}
                  testID={`calc.adjustments.row.${side}-${row.key}`}
                  accessible={false}
                  style={styles.row}
                >
                  <View style={styles.lineBetween}>
                    <Text style={[type.bodySm, styles.rowLabel]}>{row.label}</Text>
                    <Text
                      style={[
                        type.data,
                        { color: row.amount >= 0 ? semantic.pos : semantic.neg },
                      ]}
                    >
                      {signed(row.amount)}
                    </Text>
                  </View>
                  <Text style={styles.why}>{row.why}</Text>
                </View>
              ))}
            </View>
          ))
        : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.sm,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.sm,
  },
  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 32,
  },
  toggleText: { color: chalk.dim },
  side: { gap: space.xs },
  sideLabel: { color: chalk.base },
  sumLine: { color: chalk.dim },
  lineBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  row: { gap: 2 },
  rowLabel: { color: chalk.base },
  why: { ...type.bodySm, color: chalk.dim },
});
