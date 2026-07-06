import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import PositionChip from './PositionChip';
import { Button, Card, Icon, TickLabel } from './chalkline';
import { CalcPlayer } from '../data/tradeCalcMock';
import { ink, type, space, radii } from '../theme/chalkline';

interface Props {
  title: string;
  teamName: string;
  players: CalcPlayer[];
  /** Value of each selected player on the viewer-relevant board. */
  valueOf: (p: CalcPlayer) => number;
  accent: string;
  onAdd: () => void;
  onRemove: (id: string) => void;
}

// One side of a hand-built trade (You send / You receive) for the Trade
// Calculator: selected players with their board values + an add button.
export default function TradeSide({ title, teamName, players, valueOf, accent, onAdd, onRemove }: Props) {
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
              </View>
              <Text style={type.data}>{valueOf(p).toLocaleString()}</Text>
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

        <Button label="Add player" variant="secondary" compact onPress={onAdd} style={styles.addBtn} />
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
});
