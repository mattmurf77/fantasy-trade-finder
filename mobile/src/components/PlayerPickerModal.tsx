import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
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
  ice,
  position as positionColor,
  type,
  space,
  radii,
  shadowSheet,
  scrim,
} from '../theme/chalkline';

const POSITIONS: CalcPos[] = ['QB', 'RB', 'WR', 'TE', 'PICK'];

// B3 follow-up (2026-08-18) — pick identity is now SERVER-SUPPLIED, and this
// is the first client migrated off the magic string.
//
// PREFERRED: `isPick`, mapped straight off `/api/trade/values`' `is_pick`
// (docs/cross-client-invariants.md "Pick identity on the wire"). The server
// derives it from the canonical predicate `trade_service.is_pick_asset`
// (backend/trade_service.py:1138-1147), so a client that reads it can never
// disagree with the engine. Only an explicit boolean is authoritative — an
// `isPick: undefined` from a mapper wired against an older server must fall
// through, not read as `false`.
//
// THE FALLBACK STAYS, and is not dead code. `is_pick` is additive: it is
// absent on any server older than this change, on cached/`stale-while-
// revalidate` responses served from before it deployed, and on the pick
// shapes that never come from this endpoint at all — owned league picks
// (pos 'PICK', nflTeam 'PICK', built client-side from `/api/league/picks`)
// and the demo calculator's mock picks (pos 'PICK', nflTeam '—'). BOTH
// fields are needed: the universal pool's generic rungs carry a FAKE player
// position (`_PICK_POS`, backend/server.py:1464) and are marked as picks by
// `team === 'PICK'` alone. Deleting either arm re-opens feedback #222 /
// sweep B3. The magic string is the server's; do not drift it alone.
// (The body stays on the `=>` line: check-picker-pick-filter.js lifts it out
// with `const isPickAsset = (p: CalcPlayer) => ([^;]+);` and runs it.)
const isPickAsset = (p: CalcPlayer) => ('isPick' in p && typeof p.isPick === 'boolean'
  ? p.isPick
  : p.pos === 'PICK' || p.nflTeam === 'PICK');

// B3 — two-sided position filter. The PICK chip keeps every pick asset (a
// generic rung typed 'RB' server-side included, which is why the old
// one-field `p.pos === posFilter` painted a blank sheet); a player chip
// keeps that position MINUS picks, so a 1st stops listing under "RB".
const matchesPosFilter = (p: CalcPlayer, posFilter: CalcPos | null) => {
  if (!posFilter) return true;
  return posFilter === 'PICK' ? isPickAsset(p) : p.pos === posFilter && !isPickAsset(p);
};

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
   *  number). #320/D-320-1 superseded #263's "picks keep their numeric
   *  value" carve-out: the in-league calculator now resolves owned picks
   *  too. Omitted/null per row falls back to the numeric value (old
   *  servers, unpriced rows, unwired callers). */
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
  /** B3 — the pool's queries are still in flight. An in-flight pool is
   *  UNKNOWN, not empty, so this suppresses the empty state (see the
   *  ListEmptyComponent below). Mirrors the sibling picker's contract —
   *  `SwapPlayerSheet loading={...}` in TradesScreen. Defaults false, so
   *  callers whose pool is static (the demo calculator's mock rosters)
   *  need not pass it. */
  loading?: boolean;
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
  loading = false,
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
      .filter((p) => matchesPosFilter(p, posFilter))
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
    // B3 — one verdict drives the chip, the a11y label and the subtitle, so
    // a generic rung stops badging "RB" while its row calls itself a pick.
    const isPick = isPickAsset(item);
    const posLabel: CalcPos = isPick ? 'PICK' : item.pos;
    const itemTier = tierOf?.(item);
    const valuePhrase = itemTier
      ? `tier ${TIER_LABEL[itemTier]}`
      : `value ${ownerBoardValue(item).toLocaleString()}`;
    return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={`${item.name}, ${posLabel}, ${
        isPick ? 'draft capital' : `${item.nflTeam}, ${item.age} years`
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
      {/* #320 — fixed-width chip slot: PICK (4 chars) is wider than
          QB/RB/WR/TE, so a self-sized chip pushed pick rows' names right;
          the slot left-aligns every row's name at one x. PositionChip
          itself is untouched (shared with Tiers/Trades/Matches — no
          drive-by). Same 44pt constant as TradeSide.chipCol; keep them in
          lockstep (mobile/tests/check-picker-chip-alignment.js). */}
      <View style={styles.chipCol}>
        <PositionChip position={posLabel} size="sm" />
      </View>
      <View style={styles.info}>
        <View style={styles.nameRow}>
          <Text style={type.title}>{item.name}</Text>
          {need ? <Badge label="NEED" color={flare.base} colorText /> : null}
          {badgeFor?.(item) ? (
            <Badge label={badgeFor(item)!.label} color={badgeFor(item)!.color} colorText />
          ) : null}
        </View>
        <Text style={type.bodySm}>
          {isPick ? 'Draft capital' : `${item.nflTeam} · ${item.age} yrs`}
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
                    testID={`calc.picker.filter.${pos.toLowerCase()}`}
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
              ListEmptyComponent={
                loading ? (
                  // B3 — `filtered === []` during a fetch is not an empty
                  // pool, and "No players match." there is a false
                  // statement. Not theoretical: the TradesScreen target
                  // picker's two queries are ENABLED BY THIS SHEET OPENING
                  // (`enabled: deck.length > 0 || targetPickerOpen`), so a
                  // cold Trades home starts both fetches from zero at open
                  // and the list is empty until they land.
                  <View style={styles.loadingRow}>
                    <ActivityIndicator color={ice.base} />
                    <Text testID="calc.picker.loading" style={type.bodySm}>
                      Loading players…
                    </Text>
                  </View>
                ) : (
                  <View style={styles.empty}>
                    <Text testID="calc.picker.empty" style={styles.emptyText}>
                      {posFilter === 'PICK'
                        ? 'No draft picks available here.'
                        : 'No players match.'}
                    </Text>
                  </View>
                )
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
  // House empty-state construction (FreeAgentsScreen.centerFill/emptyBody).
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xl,
    paddingHorizontal: space.lg,
  },
  emptyText: { ...type.bodySm, textAlign: 'center' },
  // Mirrors SwapPlayerSheet.loadingRow; centered because it stands in the
  // same slot as the centered empty state.
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.md,
    paddingVertical: space.xl,
  },
  suggestedWrap: { paddingTop: space.xs },
  suggestedFoot: { paddingTop: space.md },
  info: { flex: 1 },
  // #320 — fixed chip slot so PICK/QB/RB/WR/TE rows all start the name
  // column at the same x. 44 clears the sm PICK chip; same constant in
  // TradeSide.chipCol.
  chipCol: { width: 44, alignItems: 'flex-start' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  values: { alignItems: 'flex-end' },
  tierSlot: { alignSelf: 'flex-end' },
  yourValue: { ...type.data, color: chalk.dim },
});
