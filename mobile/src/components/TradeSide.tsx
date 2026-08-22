import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import MemberEnteredMarker from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Button, Card, Icon, TickLabel } from './chalkline';
import { CalcPlayer } from '../data/calcTypes';
import { ink, type, space, radii } from '../theme/chalkline';
import type { Tier } from '../shared/types';

interface Props {
  title: string;
  teamName: string;
  players: CalcPlayer[];
  /** Value of each selected player on the viewer-relevant board. */
  valueOf: (p: CalcPlayer) => number;
  /** #263 — pick-value ladder tier for the row's display (replaces the raw
   *  `valueOf` number). #320/D-320-1 superseded #263's "picks keep their
   *  numeric value" carve-out: the in-league caller now resolves owned
   *  picks too (server-computed off the pick's discounted pool_value).
   *  Omitted or null for a given row still falls back to the numeric
   *  value — old servers, unpriced rows, or a caller that hasn't wired
   *  tier data. */
  tierOf?: (p: CalcPlayer) => Tier | null | undefined;
  accent: string;
  onAdd: () => void;
  onRemove: (id: string) => void;
  /** UI-test harness id for the Add button (registry: components/CLAUDE.md). */
  addTestID?: string;
  /** W3 M-C (D17) — the league whose assignment grid holds any asserted
   *  pick on this side. Only the In-league mount passes it; without it the
   *  marker has no correction target and renders nothing. */
  leagueId?: string | null;
  /** #384 — column mode. The merged calculator layout stands the two sides
   *  side by side, which halves the available width to roughly 165pt on a
   *  375pt screen. The stacked row (44pt chip slot + name + tier + a 32pt
   *  remove target) does not fit in that, so column mode re-flows each row
   *  to two lines and drops the fixed chip slot.
   *
   *  It does NOT shrink type: the Chalkline 11pt floor holds, and the 32pt
   *  remove control keeps its hit area (it gains `hitSlop` rather than
   *  losing size). Only layout changes — no row is removed, no value is
   *  hidden, and `MemberEnteredMarker` still renders. */
  compact?: boolean;
  /** #384 W4 — spotlight target for the tour's "add a player" beat. The
   *  guide measures a real node, so the ref must reach the actual button;
   *  registering a target that can never measure is the "points at nothing"
   *  defect the script lint exists to catch. */
  addRef?: React.RefObject<View | null>;
}

// One side of a hand-built trade (You send / You receive) for the Trade
// Calculator: selected players with their pick-value tier + an add button.
export default function TradeSide({ title, teamName, players, valueOf, tierOf, accent, onAdd, onRemove, addTestID, leagueId, compact, addRef }: Props) {
  return (
    <Card>
      <View style={styles.inner}>
        <View style={[styles.header, compact && styles.headerCompact]}>
          <TickLabel color={accent}>{title}</TickLabel>
          <Text style={type.bodySm} numberOfLines={1}>{teamName}</Text>
        </View>

        {players.length === 0 ? (
          <Text style={styles.empty}>No players yet — add someone to start the trade.</Text>
        ) : (
          players.map((p) => (
            <View key={p.id} style={[styles.row, compact && styles.rowCompact]}>
              {/* #320 — fixed-width chip slot: PICK (4 chars) is wider than
                  QB/RB/WR/TE, so a self-sized chip pushed pick rows' names
                  right. The slot pins one name x-position for every row.
                  PositionChip itself is untouched — it's shared with
                  Tiers/Trades/Matches (no drive-by). Same 44pt constant as
                  PlayerPickerModal's chipCol; keep the two in lockstep
                  (mobile/tests/check-picker-chip-alignment.js). */}
              {compact ? null : (
                <View style={styles.chipCol}>
                  <PositionChip position={p.pos} size="sm" />
                </View>
              )}
              <View style={styles.info}>
                {compact ? (
                  <View style={styles.compactTopLine}>
                    <PositionChip position={p.pos} size="sm" />
                    <Text style={[type.title, styles.compactName]} numberOfLines={1}>
                      {p.name}
                    </Text>
                  </View>
                ) : (
                  <Text style={type.title}>{p.name}</Text>
                )}
                <View style={compact ? styles.compactMetaLine : undefined}>
                  <Text style={type.bodySm} numberOfLines={1}>
                    {p.pick ? 'Draft capital' : `${p.nflTeam} · ${p.age} yrs`}
                  </Text>
                  {/* Column mode has no room for a trailing value column, so
                      the tier/value rides the meta line. It is MOVED, never
                      dropped — a narrower row that silently stops pricing an
                      asset would be worse than a wrapped one. */}
                  {compact
                    ? (() => {
                        const t = tierOf?.(p);
                        return t ? (
                          <TierBadge tier={t} />
                        ) : (
                          <Text style={type.data}>{valueOf(p).toLocaleString()}</Text>
                        );
                      })()
                    : null}
                </View>
                {/* D17 — priced surface 4 of 5: the calculator's pick rows.
                    UNCONDITIONAL by design; the marker self-gates on the
                    flag AND `source === 'user'`, so wrapping this in a
                    ternary would only create a way for a priced assertion
                    to render as platform truth. */}
                <MemberEnteredMarker
                  source={p.pickSource}
                  pickId={p.id}
                  season={p.pickSeason}
                  leagueId={leagueId}
                  testID={`calc.member-entered.${p.id}`}
                />
              </View>
              {compact ? null : (() => {
                const t = tierOf?.(p);
                return t ? (
                  // TierBadge hardcodes alignSelf:'flex-start' (fine in its
                  // usual flex-wrap header contexts); this row centers its
                  // children, so re-center the badge itself rather than
                  // let it fight the row's alignItems.
                  <View style={styles.tierSlot}>
                    <TierBadge tier={t} />
                  </View>
                ) : (
                  <Text style={type.data}>{valueOf(p).toLocaleString()}</Text>
                );
              })()}
              <Pressable
                onPress={() => onRemove(p.id)}
                // Column mode narrows the row, not the target: the control
                // keeps its 32pt box and gains slop instead of shrinking.
                hitSlop={compact ? 12 : 6}
                style={({ pressed }) => [styles.remove, pressed && styles.removePressed]}
                accessibilityRole="button"
                accessibilityLabel={`Remove ${p.name}`}
              >
                <Icon name="x" size={16} />
              </Pressable>
            </View>
          ))
        )}

        {/* Wrapped rather than ref-forwarded: `Button` is shared across the
            app and does not forward refs, and adding forwardRef to it for one
            spotlight would be a drive-by change to every caller. A wrapper
            View measures the same box the spotlight needs. */}
        <View ref={addRef}>
          <Button label="Add player" variant="secondary" compact testID={addTestID} onPress={onAdd} style={styles.addBtn} />
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.sm },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  empty: { ...type.bodySm, paddingVertical: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  info: { flex: 1 },
  // #320 — fixed chip slot so PICK/QB/RB/WR/TE rows all start the name
  // column at the same x. 44 clears the sm PICK chip; same constant in
  // PlayerPickerModal.chipCol.
  chipCol: { width: 44, alignItems: 'flex-start' },
  remove: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removePressed: { backgroundColor: ink.ink3 },
  addBtn: { marginTop: space.xs },
  tierSlot: { alignSelf: 'center' },
  // #384 column mode. Type sizes are untouched (Chalkline 11pt floor); only
  // the row's flow changes — chip+name on line 1, meta+value on line 2.
  headerCompact: { flexDirection: 'column', alignItems: 'flex-start', gap: 2 },
  rowCompact: { alignItems: 'flex-start', gap: space.xs },
  compactTopLine: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  compactName: { flexShrink: 1 },
  compactMetaLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.xs,
  },
});
