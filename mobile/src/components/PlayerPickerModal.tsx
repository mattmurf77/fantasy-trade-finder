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
import { Badge, Button } from './chalkline';
import { CalcPlayer, CalcPos } from '../data/tradeCalcMock';
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

const POSITIONS: CalcPos[] = ['QB', 'RB', 'WR', 'TE', 'PICK'];

interface Props {
  visible: boolean;
  title: string;
  players: CalcPlayer[];
  selectedIds: string[];
  /** Value on the roster owner's board (what it costs them / what they'd demand). */
  ownerBoardValue: (p: CalcPlayer) => number;
  /** Second board's value shown under the primary (e.g. what it's worth to you). */
  secondaryValue?: (p: CalcPlayer) => number;
  /** Prefix for the secondary value line, e.g. "you" or "them". */
  secondaryPrefix?: string;
  /** Optional arbitrage badge per row (e.g. TARGET / SELL HIGH). */
  badgeFor?: (p: CalcPlayer) => { label: string; color: string } | null;
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
  secondaryValue,
  secondaryPrefix = 'you',
  badgeFor,
  onPick,
  onClose,
}: Props) {
  const [query, setQuery] = useState('');
  const [posFilter, setPosFilter] = useState<CalcPos | null>(null);

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
              <Button label="Done" variant="ghost" testID="calc.picker.done" onPress={onClose} />
            </View>

            <TextInput
              testID="calc.picker.search"
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
                const tint =
                  positionColor[pos.toLowerCase() as keyof typeof positionColor] ?? chalk.dim;
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
                  testID={`calc.picker.row.${item.id}`}
                  accessibilityRole="button"
                  accessibilityLabel={`${item.name}, ${item.pos}, ${
                    item.pick ? 'draft capital' : `${item.nflTeam}, ${item.age} years`
                  }, value ${ownerBoardValue(item).toLocaleString()}`}
                  accessibilityHint="Adds this player to the trade"
                  style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
                  onPress={() => onPick(item)}
                >
                  <PositionChip position={item.pos} size="sm" />
                  <View style={styles.info}>
                    <View style={styles.nameRow}>
                      <Text style={type.title}>{item.name}</Text>
                      {badgeFor?.(item) ? (
                        <Badge
                          label={badgeFor(item)!.label}
                          color={badgeFor(item)!.color}
                          colorText
                        />
                      ) : null}
                    </View>
                    <Text style={type.bodySm}>
                      {item.pick ? 'Draft capital' : `${item.nflTeam} · ${item.age} yrs`}
                    </Text>
                  </View>
                  <View style={styles.values}>
                    <Text style={type.data}>{ownerBoardValue(item).toLocaleString()}</Text>
                    {secondaryValue ? (
                      <Text style={styles.yourValue}>
                        {secondaryPrefix}: {secondaryValue(item).toLocaleString()}
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
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  values: { alignItems: 'flex-end' },
  yourValue: { ...type.data, color: chalk.dim },
});
