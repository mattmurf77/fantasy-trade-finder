import React, { useMemo, useState } from 'react';
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Player, Position } from '../data/mock';
import { PositionChip } from './PositionChip';
import { colors, fontSize, radius, spacing } from '../theme';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

interface Props {
  visible: boolean;
  title: string;
  players: Player[];
  selectedIds: string[];
  /** Value on the roster owner's board (what it costs them / what they'd demand). */
  ownerBoardValue: (p: Player) => number;
  /** Value on your board (what it's worth to you). Omitted when picking from your own roster. */
  yourBoardValue?: (p: Player) => number;
  onPick: (p: Player) => void;
  onClose: () => void;
}

export function PlayerPickerModal({
  visible,
  title,
  players,
  selectedIds,
  ownerBoardValue,
  yourBoardValue,
  onPick,
  onClose,
}: Props) {
  const [query, setQuery] = useState('');
  const [posFilter, setPosFilter] = useState<Position | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return players
      .filter((p) => !selectedIds.includes(p.id))
      .filter((p) => (posFilter ? p.pos === posFilter : true))
      .filter((p) => (q ? p.name.toLowerCase().includes(q) : true))
      .sort((a, b) => ownerBoardValue(b) - ownerBoardValue(a));
  }, [players, selectedIds, posFilter, query, ownerBoardValue]);

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable onPress={onClose} hitSlop={8}>
            <Text style={styles.close}>Done</Text>
          </Pressable>
        </View>

        <TextInput
          style={styles.search}
          placeholder="Search players…"
          placeholderTextColor={colors.muted}
          value={query}
          onChangeText={setQuery}
          autoCorrect={false}
        />

        <View style={styles.filters}>
          {POSITIONS.map((pos) => {
            const active = posFilter === pos;
            return (
              <Pressable
                key={pos}
                style={[
                  styles.filterChip,
                  active && { backgroundColor: colors.position[pos] + '33', borderColor: colors.position[pos] },
                ]}
                onPress={() => setPosFilter(active ? null : pos)}
              >
                <Text style={[styles.filterText, active && { color: colors.position[pos] }]}>{pos}</Text>
              </Pressable>
            );
          })}
        </View>

        <FlatList
          data={filtered}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ paddingBottom: spacing.xl }}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => onPick(item)}>
              <PositionChip pos={item.pos} />
              <View style={styles.info}>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.meta}>
                  {item.nflTeam} · {item.age} yrs
                </Text>
              </View>
              <View style={styles.values}>
                <Text style={styles.value}>{ownerBoardValue(item).toLocaleString()}</Text>
                {yourBoardValue ? (
                  <Text style={styles.yourValue}>you: {yourBoardValue(item).toLocaleString()}</Text>
                ) : null}
              </View>
            </Pressable>
          )}
        />
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: spacing.lg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  title: { color: colors.text, fontSize: fontSize.lg, fontWeight: '700' },
  close: { color: colors.accent, fontSize: fontSize.base, fontWeight: '600' },
  search: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: fontSize.base,
  },
  filters: { flexDirection: 'row', gap: spacing.sm, paddingVertical: spacing.md },
  filterChip: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  filterText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '600' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  info: { flex: 1 },
  name: { color: colors.text, fontSize: fontSize.base, fontWeight: '600' },
  meta: { color: colors.muted, fontSize: fontSize.xs },
  values: { alignItems: 'flex-end' },
  value: { color: colors.text, fontSize: fontSize.sm, fontWeight: '700' },
  yourValue: { color: colors.muted, fontSize: fontSize.xs },
});
