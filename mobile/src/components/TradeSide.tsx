import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import MemberEnteredMarker from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Button, Card, Icon, TickLabel } from './chalkline';
import { CalcPlayer } from '../data/tradeCalcMock';
import { ink, type, space, radii } from '../theme/chalkline';
import type { Tier } from '../shared/types';

interface Props {
  title: string;
  teamName: string;
  players: CalcPlayer[];
  /** Value of each selected player on the viewer-relevant board. */
  valueOf: (p: CalcPlayer) => number;
  /** #263 — pick-value ladder tier for the row's display (replaces the raw
   *  `valueOf` number for players; picks keep their numeric value since a
   *  pick effectively already IS a tier rung). Omitted or null for a given
   *  row falls back to the numeric value — e.g. picks, or a caller that
   *  hasn't wired tier data. */
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
}

// One side of a hand-built trade (You send / You receive) for the Trade
// Calculator: selected players with their pick-value tier + an add button.
export default function TradeSide({ title, teamName, players, valueOf, tierOf, accent, onAdd, onRemove, addTestID, leagueId }: Props) {
  return (
    <Card>
      <View style={styles.inner}>
        <View style={styles.header}>
          <TickLabel color={accent}>{title}</TickLabel>
          <Text style={type.bodySm}>{teamName}</Text>
        </View>

        {players.length === 0 ? (
          <Text style={styles.empty}>No players yet — add someone to start the trade.</Text>
        ) : (
          players.map((p) => (
            <View key={p.id} style={styles.row}>
              <PositionChip position={p.pos} size="sm" />
              <View style={styles.info}>
                <Text style={type.title}>{p.name}</Text>
                <Text style={type.bodySm}>
                  {p.pick ? 'Draft capital' : `${p.nflTeam} · ${p.age} yrs`}
                </Text>
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
              {(() => {
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
                hitSlop={6}
                style={({ pressed }) => [styles.remove, pressed && styles.removePressed]}
                accessibilityRole="button"
                accessibilityLabel={`Remove ${p.name}`}
              >
                <Icon name="x" size={16} />
              </Pressable>
            </View>
          ))
        )}

        <Button label="Add player" variant="secondary" compact testID={addTestID} onPress={onAdd} style={styles.addBtn} />
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
});
