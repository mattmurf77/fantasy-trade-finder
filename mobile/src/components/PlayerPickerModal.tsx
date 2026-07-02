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
import PositionChip from './PositionChip';
import { Button } from './chalkline';
import { CalcPlayer } from '../data/tradeCalcMock';
import type { Position } from '../shared/types';
import {
  ink,
  chalk,
  position as positionColor,
  type,
  space,
  radii,
  shadowSheet,
  scrim,
} from '../theme/chalkline';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

interface Props {
  visible: boolean;
  title: string;
  players: CalcPlayer[];
  selectedIds: string[];
  /** Value on the roster owner's board (what it costs them / what they'd demand). */
  ownerBoardValue: (p: CalcPlayer) => number;
  /** Value on your board (what it's worth to you). Omitted when picking from your own roster. */
  yourBoardValue?: (p: CalcPlayer) => number;
  onPick: (p: CalcPlayer) => void;
  onClose: () => void;
}

// Search + position-filter player picker for the Trade Calculator. Currently
// fed by the calculator's mock rosters; the plan doc's reusable
// PlayerPickerSheet over the universal pool can grow out of this later.
export default function PlayerPickerModal({
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
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.backdrop} edges={['top']}>
        <View style={styles.sheet}>
          <SafeAreaView style={styles.sheetInner} edges={['bottom']}>
            <View style={styles.grabber} />
            <View style={styles.header}>
              <Text style={type.heading}>{title}</Text>
              <Button label="Done" variant="ghost" onPress={onClose} />
            </View>

            <TextInput
              style={styles.search}
              placeholder="Search players…"
              placeholderTextColor={chalk.faint}
              value={query}
              onChangeText={setQuery}
              autoCorrect={false}
            />

            <View style={styles.filters}>
              {POSITIONS.map((pos) => {
                const active = posFilter === pos;
                const tint = positionColor[pos.toLowerCase() as keyof typeof positionColor];
                return (
                  <Pressable
                    key={pos}
                    hitSlop={4}
                    accessibilityRole="button"
                    style={({ pressed }) => [
                      styles.filterChip,
                      (active || pressed) && styles.filterChipActive,
                      active && { borderColor: tint },
                    ]}
                    onPress={() => setPosFilter(active ? null : pos)}
                  >
                    <Text style={[type.label, active && styles.filterTextActive]}>{pos}</Text>
                  </Pressable>
                );
              })}
            </View>

            <FlatList
              data={filtered}
              keyExtractor={(p) => p.id}
              contentContainerStyle={{ paddingBottom: space.xl }}
              renderItem={({ item }) => (
                <Pressable
                  style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
                  onPress={() => onPick(item)}
                >
                  <PositionChip position={item.pos} size="sm" />
                  <View style={styles.info}>
                    <Text style={type.title}>{item.name}</Text>
                    <Text style={type.bodySm}>
                      {item.nflTeam} · {item.age} yrs
                    </Text>
                  </View>
                  <View style={styles.values}>
                    <Text style={type.data}>{ownerBoardValue(item).toLocaleString()}</Text>
                    {yourBoardValue ? (
                      <Text style={styles.yourValue}>
                        you: {yourBoardValue(item).toLocaleString()}
                      </Text>
                    ) : null}
                  </View>
                </Pressable>
              )}
            />
          </SafeAreaView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: scrim, justifyContent: 'flex-end' },
  sheet: {
    flex: 1,
    marginTop: space.xxl,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  sheetInner: { flex: 1, paddingHorizontal: space.lg },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  search: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink2,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: space.md,
  },
  filters: { flexDirection: 'row', gap: space.sm, paddingVertical: space.md },
  filterChip: {
    height: 36,
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: space.md,
  },
  filterChipActive: { backgroundColor: ink.ink3 },
  filterTextActive: { color: chalk.base },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  info: { flex: 1 },
  values: { alignItems: 'flex-end' },
  yourValue: { ...type.data, color: chalk.dim },
});
