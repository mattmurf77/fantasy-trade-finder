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
import MemberEnteredMarker, {
  MEMBER_ENTERED_COPY,
  isMemberEntered,
  openPickCorrection,
  usePicksTradeable,
} from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Badge, Button, TickLabel } from './chalkline';
import { TIER_LABEL } from '../utils/tierBands'; // tier name in the composed a11y label
import { CalcPlayer, CalcPos } from '../data/tradeCalcMock';
import type { Tier } from '../shared/types';
import {
  ink,
  chalk,
  flare,
  position as positionColor,
  type,
  space,
  radii,
  shadowSheet,
  scrim,
} from '../theme/chalkline';

const POSITIONS: CalcPos[] = ['QB', 'RB', 'WR', 'TE', 'PICK'];

// #203 — one "Suggested" row: an asset close in value to the current trade
// gap, with `need` marking that its position is a roster need of the team
// that would receive it. The host computes the list; this modal only renders.
export interface SuggestedPlayer {
  player: CalcPlayer;
  need: boolean;
}

interface Props {
  visible: boolean;
  title: string;
  players: CalcPlayer[];
  /** #203 — gap-closing suggestions pinned above the list (≤4 rows). */
  suggested?: SuggestedPlayer[];
  selectedIds: string[];
  /** Value on the roster owner's board (what it costs them / what they'd demand). */
  ownerBoardValue: (p: CalcPlayer) => number;
  /** #263 — pick-value ladder tier for the row (replaces `ownerBoardValue`'s
   *  number for players; picks keep their numeric value). Omitted/null per
   *  row falls back to the numeric value. */
  tierOf?: (p: CalcPlayer) => Tier | null | undefined;
  /** Second board's value shown under the primary (e.g. what it's worth to you). */
  secondaryValue?: (p: CalcPlayer) => number;
  /** #277 — pick-value ladder tier for the secondary board's line (the
   *  dual-board demo comparison). When it resolves, the line reads
   *  `them: 2nd` instead of `them: 950` — a cross-tier disagreement still
   *  shows two different labels. Falls back to the numeric secondaryValue
   *  when omitted/null (picks, unwired callers). */
  secondaryTierOf?: (p: CalcPlayer) => Tier | null | undefined;
  /** Prefix for the secondary value line, e.g. "you" or "them". */
  secondaryPrefix?: string;
  /** Optional arbitrage badge per row (e.g. TARGET / SELL HIGH). */
  badgeFor?: (p: CalcPlayer) => { label: string; color: string } | null;
  /** W3 M-C (D17) — the league whose assignment grid holds any asserted
   *  pick in this pool. Only the In-league calculator's two pickers pass
   *  it; the deck's target picker and the demo calculator hold no league
   *  picks at all, so the marker there has nothing to mark. */
  leagueId?: string | null;
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
  suggested,
  selectedIds,
  ownerBoardValue,
  tierOf,
  secondaryValue,
  secondaryTierOf,
  secondaryPrefix = 'you',
  badgeFor,
  leagueId,
  onPick,
  onClose,
}: Props) {
  const [query, setQuery] = useState('');
  const [posFilter, setPosFilter] = useState<CalcPos | null>(null);
  // W3 M-C (D17). The row Pressable is an accessible container, so on iOS
  // it swallows the marker's own a11y node — the disclosure and the
  // correction are therefore ALSO folded into the row's own contract
  // (label + a custom action). Sighted users get the marker; VoiceOver
  // users get the same sentence and the same one-action fix.
  const picksTradeable = usePicksTradeable();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return players
      .filter((p) => !selectedIds.includes(p.id))
      .filter((p) => (posFilter ? p.pos === posFilter : true))
      .filter((p) => (q ? p.name.toLowerCase().includes(q) : true))
      .sort((a, b) => ownerBoardValue(b) - ownerBoardValue(a));
  }, [players, selectedIds, posFilter, query, ownerBoardValue]);

  // #203 — suggestions render only in the untouched picker state; a search
  // or position filter means the user is looking for someone specific.
  const showSuggested =
    !!suggested && suggested.length > 0 && !query.trim() && !posFilter;

  // Shared row renderer — the suggested rows are the same row with their own
  // testID plus a flare NEED badge (informational highlight, not an action).
  const renderRow = (item: CalcPlayer, testID: string, need = false) => {
    const marked =
      picksTradeable && isMemberEntered(item.pickSource) && !!item.id && !!leagueId;
    const itemTier = tierOf?.(item);
    const valuePhrase = itemTier
      ? `tier ${TIER_LABEL[itemTier]}`
      : `value ${ownerBoardValue(item).toLocaleString()}`;
    return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={`${item.name}, ${item.pos}, ${
        item.pick ? 'draft capital' : `${item.nflTeam}, ${item.age} years`
      }, ${valuePhrase}${
        need ? ', fills a roster need for the receiving team' : ''
      }${marked ? `. ${MEMBER_ENTERED_COPY}` : ''}`}
      accessibilityHint="Adds this player to the trade"
      accessibilityActions={
        marked ? [{ name: 'correct', label: 'Correct this pick' }] : undefined
      }
      onAccessibilityAction={
        marked
          ? (e) => {
              if (e.nativeEvent.actionName === 'correct') {
                openPickCorrection(leagueId as string, item.id, item.pickSeason);
              }
            }
          : undefined
      }
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
      onPress={() => onPick(item)}
    >
      <PositionChip position={item.pos} size="sm" />
      <View style={styles.info}>
        <View style={styles.nameRow}>
          <Text style={type.title}>{item.name}</Text>
          {need ? <Badge label="NEED" color={flare.base} colorText /> : null}
          {badgeFor?.(item) ? (
            <Badge label={badgeFor(item)!.label} color={badgeFor(item)!.color} colorText />
          ) : null}
        </View>
        <Text style={type.bodySm}>
          {item.pick ? 'Draft capital' : `${item.nflTeam} · ${item.age} yrs`}
        </Text>
        {/* D17 — priced surface 1 of 5: the trade-away / acquire picker.
            UNCONDITIONAL (the marker self-gates); the row already shows the
            price this pick would add, so it must also show that the price
            rests on a leaguemate's assertion. */}
        <MemberEnteredMarker
          source={item.pickSource}
          pickId={item.id}
          season={item.pickSeason}
          leagueId={leagueId}
          testID={`calc.picker.member-entered.${item.id}`}
        />
      </View>
      <View style={styles.values}>
        {itemTier ? (
          // TierBadge hardcodes alignSelf:'flex-start'; this column
          // right-aligns its children, so re-align the badge itself.
          <View style={styles.tierSlot}>
            <TierBadge tier={itemTier} />
          </View>
        ) : (
          <Text style={type.data}>{ownerBoardValue(item).toLocaleString()}</Text>
        )}
        {secondaryValue ? (
          (() => {
            // #277 — the other board's read as a tier label; numeric only
            // when no tier resolves (picks, unwired callers).
            const st = secondaryTierOf?.(item);
            return (
              <Text style={styles.yourValue}>
                {secondaryPrefix}:{' '}
                {st ? TIER_LABEL[st] : secondaryValue(item).toLocaleString()}
              </Text>
            );
          })()
        ) : null}
      </View>
    </Pressable>
    );
  };

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
              ListHeaderComponent={
                showSuggested ? (
                  <View style={styles.suggestedWrap}>
                    <TickLabel>Suggested</TickLabel>
                    {suggested!.map((s) => (
                      <React.Fragment key={s.player.id}>
                        {renderRow(s.player, `calc.picker.suggested.${s.player.id}`, s.need)}
                      </React.Fragment>
                    ))}
                    <View style={styles.suggestedFoot}>
                      <TickLabel>All players</TickLabel>
                    </View>
                  </View>
                ) : null
              }
              renderItem={({ item }) => renderRow(item, `calc.picker.row.${item.id}`)}
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
  suggestedWrap: { paddingTop: space.xs },
  suggestedFoot: { paddingTop: space.md },
  info: { flex: 1 },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  values: { alignItems: 'flex-end' },
  tierSlot: { alignSelf: 'flex-end' },
  yourValue: { ...type.data, color: chalk.dim },
});
