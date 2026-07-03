import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Player } from '../data/mock';
import { PositionChip } from './PositionChip';
import { colors, fontSize, radius, spacing } from '../theme';

interface Props {
  title: string;
  teamName: string;
  players: Player[];
  /** Value of each selected player on the viewer-relevant board. */
  valueOf: (p: Player) => number;
  accent: string;
  onAdd: () => void;
  onRemove: (id: string) => void;
}

export function TradeSide({ title, teamName, players, valueOf, accent, onAdd, onRemove }: Props) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: accent }]}>{title}</Text>
        <Text style={styles.team}>{teamName}</Text>
      </View>

      {players.length === 0 ? (
        <Text style={styles.empty}>No players yet — add someone to start the trade.</Text>
      ) : (
        players.map((p) => (
          <View key={p.id} style={styles.row}>
            <PositionChip pos={p.pos} />
            <View style={styles.info}>
              <Text style={styles.name}>{p.name}</Text>
              <Text style={styles.meta}>
                {p.nflTeam} · {p.age} yrs
              </Text>
            </View>
            <Text style={styles.value}>{valueOf(p).toLocaleString()}</Text>
            <Pressable
              onPress={() => onRemove(p.id)}
              hitSlop={8}
              style={styles.remove}
              accessibilityLabel={`Remove ${p.name}`}
            >
              <Text style={styles.removeText}>✕</Text>
            </Pressable>
          </View>
        ))
      )}

      <Pressable style={[styles.addBtn, { borderColor: accent }]} onPress={onAdd}>
        <Text style={[styles.addText, { color: accent }]}>＋ Add player</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  title: { fontSize: fontSize.base, fontWeight: '700' },
  team: { fontSize: fontSize.sm, color: colors.muted },
  empty: { color: colors.muted, fontSize: fontSize.sm, paddingVertical: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  info: { flex: 1 },
  name: { color: colors.text, fontSize: fontSize.base, fontWeight: '600' },
  meta: { color: colors.muted, fontSize: fontSize.xs },
  value: { color: colors.text, fontSize: fontSize.sm, fontWeight: '700' },
  remove: {
    width: 24,
    height: 24,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeText: { color: colors.muted, fontSize: fontSize.xs },
  addBtn: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    alignItems: 'center',
  },
  addText: { fontSize: fontSize.sm, fontWeight: '600' },
});
