import React, { useCallback, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  FlatList,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  LayoutChangeEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, useIsFocused } from '@react-navigation/native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { haptics } from '../utils/haptics';
import {
  ink,
  chalk,
  ice,
  semantic,
  tier as tierColors,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
} from '../theme/chalkline';
import { TickLabel, Button, Text as ChalkText } from '../components/chalkline';
import Toast from '../components/Toast';
import FormatToggle from '../components/FormatToggle';
import { setPinnedBottomBarHeight } from '../components/FeedbackFAB';
import { getRankings, reorderRankings } from '../api/rankings';
import { TIERS, TIER_LABEL, tierForElo } from '../utils/tierBands';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { useScoringFormat } from '../hooks/useScoringFormat';
import type { Position, RankedPlayer, ScoringFormat, Tier } from '../shared/types';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

// #140 — same conditional-POS rule as the Quick set walk: this walk is
// position-scoped (the active tab names the position), so the chip's POS
// token is redundant and its width goes to TEAM + AGE. Conditional, not
// deleted: cross-position reuse flips this on.
const SHOW_POSITION = false;

// #136 — Quick Rank: the within-tier polish pass after Quick Set. Same
// guided construction as QuickSetTiersScreen (position tabs, tier-by-tier
// walk down the 8-tier ladder, per-tier save), but instead of assigning
// players TO a tier, the user orders the players already IN it: every
// player in the tier renders as a chip; tapping stamps the next rank
// number (click order); tapping again unclicks and renumbers. Save posts
// the tier's players to /api/rankings/reorder — clicked order first, any
// unclicked players appended in their current (elo-desc) order, exactly
// the owner's spec ("first 6 clicked → the other 4 rank 7-10").
//
// Save semantics — apply_reorder is subset-safe (v1.7.0 permutation
// semantics): it permutes the Elo multiset of exactly the ids posted, so
// reordering a tier's own players can never move anyone across a tier
// boundary and never touches the rest of the board (pinned by
// backend/tests/test_tier_occupancy.py::test_subset_reorder_within_tier_*).
//
// The walk only visits tiers with 2+ players (empty and 1-player tiers
// have nothing to order — auto-skipped by construction: the step list is
// derived from live tier membership, which reorders leave invariant).
export default function QuickRankScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const queryClient = useQueryClient();
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';
  // #137 — SF/1QB toggle in the walk header, same wiring as Quick set's.
  const { setFormat, switching: formatSwitching } = useScoringFormat();

  // S2 PRD-04 ride-along (flag visual.chalkline_cleanup): 9px chip metas
  // rise to the 11px type floor; faint content text promotes to dim.
  const cleanup = useFlag('visual.chalkline_cleanup');

  // S3 PRD-01 — report the pinned walk footer to the feedback FAB (same
  // contract as Quick set: focused-only, FAB ignores it while
  // ux.touch_polish is off). The reporting effect lives below, after the
  // step derivation — the footer only renders when there's a tier to walk.
  const isFocused = useIsFocused();
  const [footerH, setFooterH] = useState(0);

  const [position, setPosition] = useState<Position>(
    route.params?.position ?? 'QB',
  );
  const [stepIdx, setStepIdx] = useState(0);
  // Ordered click sequence — index IS the rank (0-based).
  const [clicked, setClicked] = useState<string[]>([]);
  // #138 — per-step player-name filter over the chip grid.
  const [search, setSearch] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  const rankingsQuery = useQuery({
    queryKey: ['rankings', activeFormat, position],
    queryFn: () => getRankings(position),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  // Tier → members (elo desc). Membership is invariant under our own saves
  // (pure permutation), so the step list stays stable across the walk.
  const membersByTier = useMemo(() => {
    const rows = ((rankingsQuery.data?.rankings as RankedPlayer[] | undefined) ?? [])
      .slice()
      .sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0));
    const map = new Map<Tier, RankedPlayer[]>();
    for (const p of rows) {
      const t = tierForElo(p.elo, position, fmt);
      if (!t) continue; // below every band — nothing to rank
      const arr = map.get(t);
      if (arr) arr.push(p);
      else map.set(t, [p]);
    }
    return map;
  }, [rankingsQuery.data, position, fmt]);

  // The walk's steps: ladder order, tiers with 2+ players only (a lone
  // player is already "ranked" within its tier).
  const steps = useMemo(
    () => TIERS.filter((t) => (membersByTier.get(t)?.length ?? 0) >= 2),
    [membersByTier],
  );
  const tier = steps[Math.min(stepIdx, Math.max(steps.length - 1, 0))];
  const isLastTier = stepIdx >= steps.length - 1;
  const members = (tier ? membersByTier.get(tier) : undefined) ?? [];

  // S3 PRD-01 — FAB-offset reporting (see the state block above). The
  // footer only renders on the walkable branch, so report 0 whenever the
  // empty/loading/error states own the screen.
  const footerVisible =
    !rankingsQuery.isLoading && !rankingsQuery.isError && steps.length > 0 && !!tier;
  React.useEffect(() => {
    setPinnedBottomBarHeight('quickrank', isFocused && footerVisible ? footerH : 0);
  }, [isFocused, footerVisible, footerH]);
  React.useEffect(() => () => setPinnedBottomBarHeight('quickrank', 0), []);

  // #138 — what the grid RENDERS. Click order lives in the pid list and
  // save reads the full member set, so filtering the view can never drop
  // an already-stamped player from the submit.
  const query = search.trim().toLowerCase();
  const visibleMembers = useMemo(
    () =>
      query.length === 0
        ? members
        : members.filter((p) => p.name.toLowerCase().includes(query)),
    [members, query],
  );

  const rankOf = useCallback(
    (pid: string) => {
      const i = clicked.indexOf(pid);
      return i === -1 ? null : i + 1;
    },
    [clicked],
  );

  const toggle = useCallback((pid: string) => {
    setClicked((prev) =>
      prev.includes(pid) ? prev.filter((id) => id !== pid) : [...prev, pid],
    );
    haptics.selection();
  }, []);

  const finish = useCallback(() => {
    // Same exit as QuickSetTiers: back to the board this wrote to.
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('Tiers');
  }, [navigation]);

  const goTo = useCallback(
    (idx: number) => {
      if (idx >= steps.length) {
        finish();
        return;
      }
      setStepIdx(Math.max(idx, 0));
      setClicked([]);
      setSearch(''); // #138 — the filter is per step
    },
    [steps.length, finish],
  );

  const saveMutation = useMutation({
    mutationFn: (orderedIds: string[]) => reorderRankings(position, orderedIds, 'quickrank'),
    onSuccess: () => {
      // Same consumers as ManualRanks' reorder save: every rankings read
      // for this format, plus tier/progress derivatives.
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      haptics.success();
      goTo(stepIdx + 1);
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Save failed', tone: 'warn' });
    },
  });

  const onSave = useCallback(() => {
    if (clicked.length === 0) {
      // Nothing clicked = the current order stands — same as Skip.
      goTo(stepIdx + 1);
      return;
    }
    // Owner's spec: clicked order first, unclicked appended in their
    // current order (they become ranks N+1…end on save).
    const unclicked = members.map((p) => p.id).filter((id) => !clicked.includes(id));
    saveMutation.mutate([...clicked, ...unclicked]);
  }, [clicked, members, stepIdx, goTo, saveMutation]);

  const onSkip = useCallback(() => goTo(stepIdx + 1), [stepIdx, goTo]);
  const onBack = useCallback(() => goTo(stepIdx - 1), [stepIdx, goTo]);

  const onPosition = useCallback((p: Position) => {
    if (p === position) return;
    setPosition(p);
    setStepIdx(0);
    setClicked([]);
    setSearch('');
    haptics.selection();
  }, [position]);

  // #137 — format switch restarts the walk on the other format's board
  // (the step list is derived from that format's live tier membership,
  // read through the format-scoped ['rankings', activeFormat, position]
  // key once the switch lands).
  const onFormat = useCallback(
    async (f: ScoringFormat) => {
      haptics.selection();
      const ok = await setFormat(f);
      if (!ok) {
        setToast({ msg: 'Could not switch format', tone: 'warn' });
        return;
      }
      setStepIdx(0);
      setClicked([]);
      setSearch('');
    },
    [setFormat],
  );

  const renderChip = useCallback(
    ({ item }: { item: RankedPlayer }) => {
      const rank = rankOf(item.id);
      const posKey = String(item.position).toLowerCase() as keyof typeof positionColors;
      return (
        <Pressable
          testID={`quick-rank.chip.${item.id}`}
          accessibilityRole="button"
          accessibilityState={{ selected: rank != null }}
          accessibilityLabel={
            rank != null ? `${item.name}, ranked ${rank}` : item.name
          }
          onPress={() => toggle(item.id)}
          style={[styles.chip, rank != null && styles.chipSelected]}
        >
          <View style={styles.chipTop}>
            <Text style={styles.chipName} numberOfLines={1}>
              {item.name}
            </Text>
            {rank != null ? (
              <View style={styles.rankBadge}>
                <Text style={styles.rankBadgeText}>{rank}</Text>
              </View>
            ) : null}
          </View>
          {/* S2 PRD-04 ride-along — meta row through the chalkline Text
              primitive (dense Dynamic-Type tier); the 9px sizes rise to
              the 11px floor under visual.chalkline_cleanup. */}
          <View style={styles.chipMeta}>
            {SHOW_POSITION ? (
              <ChalkText
                scale="dense"
                style={[
                  styles.chipPos,
                  cleanup && styles.chipMetaFloor,
                  { color: positionColors[posKey] ?? chalk.dim },
                ]}
              >
                {item.position}
              </ChalkText>
            ) : null}
            <ChalkText scale="dense" style={[styles.chipTeam, cleanup && styles.chipMetaFloor]}>
              {item.team ?? 'FA'}
            </ChalkText>
            {item.age != null ? (
              <ChalkText scale="dense" style={[styles.chipAge, cleanup && styles.chipMetaFloor]}>
                {item.age}
              </ChalkText>
            ) : null}
          </View>
        </Pressable>
      );
    },
    [rankOf, toggle, cleanup],
  );

  const saving = saveMutation.isPending;
  const clickedCount = clicked.length;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {/* #138 — keyboard-avoiding wrapper (EspnLinkSheet pattern): the
          walk's footer is pinned absolute-bottom, so without this the iOS
          keyboard covers Back / Skip / Save while the search input has
          focus. */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      {/* #137 — SF/1QB scoring-format toggle, same slot convention as the
          quick-set walk (format row above the position switcher).
          Switching restarts the walk on the other format's board. */}
      <View style={styles.formatRow} testID="quick-rank.format-toggle">
        <FormatToggle
          value={activeFormat}
          onChange={onFormat}
          disabled={formatSwitching || saving}
        />
      </View>

      {/* Position switcher — PositionTabs spec, same construction as the
          quick-set walk's. */}
      <View style={styles.switcher}>
        {POSITIONS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              testID={`quick-rank.pos-tab.${p}`}
              onPress={() => onPosition(p)}
              style={({ pressed }) => [
                styles.switcherBtn,
                isActive && styles.switcherBtnActive,
                isActive && {
                  borderBottomColor:
                    positionColors[p.toLowerCase() as keyof typeof positionColors],
                },
                pressed && !isActive && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.switcherText, isActive && styles.switcherTextActive]}>
                {p}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {rankingsQuery.isLoading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={chalk.dim} />
        </View>
      ) : rankingsQuery.isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Button
            variant="ghost"
            compact
            label="Try again"
            onPress={() => rankingsQuery.refetch()}
          />
        </View>
      ) : steps.length === 0 || !tier ? (
        <View style={styles.centered}>
          {/* S2 PRD-04 — explanatory content: faint → dim under cleanup. */}
          <Text style={[styles.emptyText, cleanup && styles.emptyTextDim]}>
            No {position} tier has two or more players to order yet — set
            tiers first with Quick set.
          </Text>
          <Button
            variant="ghost"
            compact
            label="Done"
            onPress={finish}
          />
        </View>
      ) : (
        <>
          {/* Step header — the tier being ordered + walk progress, same
              construction as the quick-set step header. */}
          <View style={styles.stepHeader}>
            <View style={styles.stepTitleRow}>
              <TickLabel color={tierColors[tier]}>{TIER_LABEL[tier]}</TickLabel>
              <Text style={styles.stepProgress}>{`Tier ${stepIdx + 1} of ${steps.length}`}</Text>
            </View>
            <Text style={styles.stepHint}>
              Tap players best-first — each tap sets the next rank. Anyone you
              don't tap slots in below your last pick, in their current order.
            </Text>
          </View>

          {/* #138 — compact name filter over the grid (Input construction,
              same as Quick set's). Clears per step; view-only narrowing —
              stamped ranks survive the filter. */}
          <TextInput
            testID="quick-rank.search"
            style={[styles.search, searchFocused && styles.searchFocused]}
            placeholder={`Search ${position}s…`}
            placeholderTextColor={chalk.faint}
            value={search}
            onChangeText={setSearch}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            autoCorrect={false}
            autoCapitalize="none"
            returnKeyType="done"
            clearButtonMode="while-editing"
            accessibilityLabel="Search players in this step"
          />

          <FlatList
            data={visibleMembers}
            keyExtractor={(p) => p.id}
            renderItem={renderChip}
            extraData={clicked}
            numColumns={3}
            columnWrapperStyle={styles.gridRow}
            contentContainerStyle={styles.grid}
            keyboardShouldPersistTaps="handled"
            ListEmptyComponent={
              query.length > 0 ? (
                <Text style={[styles.emptyText, cleanup && styles.emptyTextDim]}>
                  {`No ${position} here matches “${search.trim()}”.`}
                </Text>
              ) : null
            }
          />

          {/* Walk controls pinned to the bottom: Back / Skip / Save-and-next.
              onLayout feeds the S3 PRD-01 FAB-offset registry. */}
          <View
            style={styles.footer}
            onLayout={(e: LayoutChangeEvent) => setFooterH(e.nativeEvent.layout.height)}
          >
            <Button
              variant="ghost"
              compact
              label="Back"
              disabled={stepIdx === 0 || saving}
              onPress={onBack}
            />
            <Button
              variant="secondary"
              compact
              label={isLastTier ? 'Skip & finish' : 'Skip'}
              disabled={saving}
              onPress={onSkip}
            />
            <Pressable
              testID="quick-rank.save-btn"
              disabled={saving}
              onPress={onSave}
              style={({ pressed }) => [
                styles.saveBtn,
                pressed && { backgroundColor: ice.press },
                saving && { opacity: 0.45 },
              ]}
            >
              {saving ? (
                <ActivityIndicator color={ice.on} />
              ) : (
                <Text style={styles.saveBtnText}>
                  {`Save ${TIER_LABEL[tier]}${clickedCount > 0 ? ` (${clickedCount}/${members.length})` : ''}`}
                  {isLastTier ? ' & finish' : ''}
                </Text>
              )}
            </Pressable>
          </View>
        </>
      )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  kav: { flex: 1 },
  // #137 — row hosting the SF/1QB FormatToggle, above the position
  // switcher (consistent slot with the quick-set walk's).
  formatRow: {
    marginHorizontal: space.lg,
    marginTop: space.sm,
  },
  // #138 — Input construction per the design system (same as Quick set's
  // search): line-strong border, ink-2 fill, radius sm, faint placeholder,
  // ice focus border.
  search: {
    ...type.body,
    height: 40,
    marginHorizontal: space.lg,
    marginBottom: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: 0,
  },
  searchFocused: { borderColor: ice.base },
  switcher: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  switcherBtnActive: { backgroundColor: ink.ink3 },
  switcherText: { ...type.label },
  switcherTextActive: { color: chalk.base },
  stepHeader: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.sm,
  },
  stepTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  stepProgress: {
    ...type.label,
    marginLeft: 'auto',
  },
  stepHint: { ...type.bodySm, marginTop: space.xs },
  grid: {
    paddingHorizontal: space.lg,
    paddingBottom: 96, // room for the footer bar
    gap: space.xs,
  },
  gridRow: { gap: space.xs },
  // Same small selectable card as the quick-set grid; selected = ice
  // border + the rank number badge (two signals).
  chip: {
    flex: 1,
    minHeight: 48,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.sm,
    paddingVertical: 6,
    justifyContent: 'center',
  },
  chipSelected: { borderColor: ice.base },
  chipTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  chipName: {
    fontFamily: fonts.uiSemi,
    fontSize: 12,
    color: chalk.base,
    flexShrink: 1,
  },
  // Rank number badge: data numeral (Plex Mono) on an ice-bordered square
  // — radius xs per the badge spec; number is the click order.
  rankBadge: {
    marginLeft: 'auto',
    minWidth: 16,
    height: 16,
    paddingHorizontal: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ice.base,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankBadgeText: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    color: ice.base,
  },
  chipMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 2,
  },
  chipPos: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
  },
  chipTeam: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    color: chalk.dim,
    textTransform: 'uppercase',
  },
  // #140 — age numeral: 9px Plex Mono (data-numeral rule), chalk-dim,
  // bare-gap separated like the rest of the meta row.
  chipAge: {
    fontFamily: fonts.data,
    fontSize: 9,
    color: chalk.dim,
  },
  // S2 PRD-04 (visual.chalkline_cleanup) — 11px type floor for the chip
  // meta row (was 9px; components.md updated). The 10px rank-badge numeral
  // is untouched: it sits inside a fixed 16px badge (raising it means
  // resizing the badge — a coordinated spec change, not a ride-along).
  chipMetaFloor: { fontSize: 11 },
  emptyText: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    paddingHorizontal: space.xl,
  },
  // S2 PRD-04 (visual.chalkline_cleanup) — content text ≥ dim.
  emptyTextDim: { color: chalk.dim },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  errorText: { ...type.body, color: semantic.neg },
  footer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.md,
    backgroundColor: ink.ink0,
    borderTopColor: ink.line,
    borderTopWidth: 1,
  },
  saveBtn: {
    flex: 1,
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
  },
  saveBtnText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: ice.on,
  },
});
