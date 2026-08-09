import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import MemberEnteredMarker from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Icon, TickLabel } from './chalkline';
import type { CalcEvener } from '../api/calc';
import { chalk, ice, ink, radii, space, type } from '../theme/chalkline';

interface Props {
  eveners: CalcEvener[];
  /** Section label, e.g. "Recommended to even it — add from your roster". */
  title: string;
  onAdd: (evener: CalcEvener) => void;
  /** W3 M-C (D17) — the league whose assignment grid holds any asserted
   *  pick recommended here. The In-league mount passes it; the open
   *  calculator's generic-pick eveners have no league and no `source`. */
  leagueId?: string | null;
}

// "Recommended to even it" rows (DynastyGM teardown 2026-07-26): the one-tap
// evener assets POST /api/trade/evaluate returns (`eveners`) when a trade is
// uneven — up to three single assets (players or owned picks; picks show
// their pick label) plus at most one 2-piece package row. Tapping + adds the
// asset(s) to the side `gap.add_to` points at (the host wires that) and the
// evaluate re-run refreshes or clears these rows as the trade evens. Renders
// nothing without candidates — honest empty state. Chalkline: ice = action
// (the + affordance), transparent-bordered rows, no new hues.
export default function EvenerRows({ eveners, title, onAdd, leagueId }: Props) {
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
          <View style={styles.body}>
            <Text style={styles.name} numberOfLines={1}>
              {e.name}
            </Text>
            {/* D17 — priced surface 3 of 5: the evener chip. This is the
                sweetener FTF ACTIVELY recommends ("ask them to add their
                2027 1st"), so it is the surface where an unmarked assertion
                does the most damage (plan §6.4 S4). UNCONDITIONAL; the
                marker self-gates on the flag and on `source === 'user'`. */}
            <MemberEnteredMarker
              source={e.source}
              pickId={e.pick_id ?? e.id}
              season={e.season}
              leagueId={leagueId}
              testID={`calc.evener.member-entered.${e.id}`}
            />
          </View>
          {/* #277 (operator overrule of #263's scope-out): player eveners
              show their pick-tier label like every other player row. Picks
              (their name IS a ladder rung) and 2-piece PKG combos (a sum
              has no single tier) keep the numeric value, as do old-server
              payloads without the field. */}
          {e.tier ? (
            <View style={styles.tierSlot}>
              <TierBadge tier={e.tier} size="sm" />
            </View>
          ) : (
            <Text style={[type.data, styles.value]}>
              {Math.round(e.value).toLocaleString()}
            </Text>
          )}
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
  // The name column became a stack when the provenance marker joined it;
  // with no marker it renders exactly as the single Text did.
  body: { flex: 1, gap: space.xs },
  name: { ...type.bodySm, color: chalk.base },
  value: { minWidth: 56, textAlign: 'right' },
  // TierBadge hardcodes alignSelf:'flex-start'; this row centers its
  // children, so re-center the badge itself (TradeSide precedent).
  tierSlot: { alignSelf: 'center' },
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
