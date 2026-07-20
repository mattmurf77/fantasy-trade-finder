import React, { useCallback, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  FlatList,
  Alert,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
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
import { TickLabel, Button, Icon } from '../components/chalkline';
import Toast from '../components/Toast';
import FormatToggle from '../components/FormatToggle';
import { getRankings, saveTiers } from '../api/rankings';
import { TIERS, TIER_LABEL, tierForElo } from '../utils/tierBands';
import { useSession } from '../state/useSession';
import { useScoringFormat } from '../hooks/useScoringFormat';
import { getOnboardingState, patchOnboardingState } from '../state/useOnboardingState';
import { setPendingQuicksetRegen } from '../state/onboardingBus';
import { track } from '../api/events';
import { requestGuideStep, guidedAvatarActive } from '../state/useGuide';
import { S as GUIDE } from '../components/analystScript';
import type { Position, RankedPlayer, ScoringFormat, Tier } from '../shared/types';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

// #140 — the walk is position-scoped (the active tab names the position),
// so the chip's POS token is redundant here and its width is spent on
// TEAM + AGE instead. Conditional, not deleted: any cross-position reuse
// of this chip construction flips this on to get the POS token back.
const SHOW_POSITION = false;

// 1.5.4 #104 — guided tier quick-set. One position at a time, walking the
// tiers top → bottom ("4+ 1sts" → FA, 8 steps since the #117 ladder):
// each step shows a grid of small tappable player
// chips (name + team + age + the tier they're CURRENTLY in — #140);
// tapping toggles
// membership in the tier being set; Save commits that one tier via the
// standard /api/tiers/save contract and advances. Players claimed by an
// earlier tier drop out of later grids. Entered from the Tiers header
// ("Quick set"); finishing (or backing out) returns to the Tiers board,
// which refetches via the query invalidations below.
//
// Save semantics — saves COMPOSE with the existing board because
// apply_tiers only touches the pids submitted: each step sends
// `{ tiers: { <tier>: [ids] } }` plus, when the user re-visits a tier via
// Back and deselects someone saved earlier in this run, that pid in
// `cleared_pids` (deleting the override → back to the suggested tier).
export default function QuickSetTiersScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const queryClient = useQueryClient();
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';
  // #137 — SF/1QB toggle in the walk header, wired like TiersScreen's:
  // setFormat flips the server session + local mirrors and marks the
  // choice explicit so the league-default applier won't override it.
  const { setFormat, switching: formatSwitching } = useScoringFormat();

  const [position, setPosition] = useState<Position>(
    route.params?.position ?? 'QB',
  );
  // Onboarding item 7 — entered from the Trades prompt card. Changes only
  // the EXIT: skip the Quick Rank offer, post a pending deck-regeneration
  // to the onboarding bus, and bounce back to the Trades tab so the user
  // sees their board change the suggestions (the F2 "aha").
  const onboardingReturn: boolean = !!route.params?.onboardingReturn;

  // Guided tour S4.1 — one quiet-coach line at the top of the first walk
  // (once ever); The Analyst then stays silent through the tiers.
  React.useEffect(() => {
    if (onboardingReturn && guidedAvatarActive()) {
      requestGuideStep(GUIDE.s4_1());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [tierIdx, setTierIdx] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  // #138 — per-step player-name filter over the chip grid.
  const [search, setSearch] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  // Tiers committed THIS RUN: tier → pids (for Back pre-selection +
  // cleared_pids on re-save) and pid → tier (to drop claimed players
  // from later grids).
  const [savedByTier, setSavedByTier] = useState<Partial<Record<Tier, string[]>>>({});
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  const tier = TIERS[tierIdx];
  const isLastTier = tierIdx === TIERS.length - 1;

  const rankingsQuery = useQuery({
    queryKey: ['rankings', activeFormat, position],
    queryFn: () => getRankings(position),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const players = useMemo(
    () =>
      ((rankingsQuery.data?.rankings as RankedPlayer[] | undefined) ?? [])
        .slice()
        .sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0)),
    [rankingsQuery.data],
  );

  // pid → tier claimed earlier in this run. A player claimed by ANOTHER
  // tier is hidden from the current grid; players claimed by THIS tier
  // (re-visited via Back) stay visible and pre-selected.
  const claimedBy = useMemo(() => {
    const map = new Map<string, Tier>();
    for (const t of TIERS) for (const id of savedByTier[t] ?? []) map.set(id, t);
    return map;
  }, [savedByTier]);

  const gridPlayers = useMemo(
    () =>
      players.filter((p) => {
        const claimed = claimedBy.get(p.id);
        return claimed == null || claimed === tier;
      }),
    [players, claimedBy, tier],
  );

  // #138 — what the grid RENDERS. Selection lives in the pid set and save
  // reads gridPlayers, so filtering the view can never drop a picked
  // player from the submit.
  const query = search.trim().toLowerCase();
  const visiblePlayers = useMemo(
    () =>
      query.length === 0
        ? gridPlayers
        : gridPlayers.filter((p) => p.name.toLowerCase().includes(query)),
    [gridPlayers, query],
  );

  const toggle = useCallback((pid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      return next;
    });
    haptics.selection();
  }, []);

  // Move the walk to `idx`, pre-selecting whatever that tier already got
  // this run. Past the last tier → done, back to the Tiers board.
  const goTo = useCallback(
    (idx: number, savedMap: Partial<Record<Tier, string[]>>) => {
      if (idx >= TIERS.length) {
        // Onboarding: record the completed position — the Trades provenance
        // chip flips CONSENSUS VALUES → YOUR BOARD off this list. Inert
        // write when onboarding surfaces are dark.
        const donePositions = getOnboardingState().quicksetCompletedPositions;
        if (!donePositions.includes(position)) {
          patchOnboardingState({
            quicksetCompletedPositions: [...donePositions, position],
          });
        }
        track('quickset_completed', { position, onboarding: onboardingReturn }, 'QuickSetTiers');
        if (onboardingReturn) {
          // Item 7 exit: no Quick Rank offer (suppressed by ruling F2), post
          // the regen handoff, and return to Trades. Unknown route names
          // bubble up from the Rank stack to the tab navigator.
          setPendingQuicksetRegen(position);
          navigation.navigate('Trades');
          return;
        }
        // #119 — with 'quickset' as a launch route this screen can be the
        // stack's first mount (no history); fall through to the Tiers board
        // it just wrote, same fallback as the header back control.
        const exit = () => {
          if (navigation.canGoBack()) navigation.goBack();
          else navigation.navigate('Tiers');
        };
        // #136 — offer Quick Rank as the natural next step: order the
        // players inside the tiers the user just set.
        Alert.alert(
          'Tiers set',
          'Rank within your tiers? Tap players best-first, one tier at a ' +
            'time, to fine-tune the order inside each tier.',
          [
            { text: 'Not now', style: 'cancel', onPress: exit },
            {
              text: 'Quick rank',
              onPress: () => navigation.navigate('QuickRank', { position }),
            },
          ],
        );
        return;
      }
      setTierIdx(idx);
      setSelected(new Set(savedMap[TIERS[idx]] ?? []));
      setSearch(''); // #138 — the filter is per step
    },
    [navigation, position],
  );

  const saveMutation = useMutation({
    mutationFn: ({ ids, cleared }: { ids: string[]; cleared: string[] }) =>
      saveTiers(position, ids.length > 0 ? { [tier]: ids } : {}, cleared),
    onSuccess: (_data, { ids }) => {
      const nextSaved = { ...savedByTier, [tier]: ids };
      setSavedByTier(nextSaved);
      // Same cache scoping as TiersScreen's save: the board + overall
      // ranks read the rewritten ELO overrides through these keys.
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, position] });
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, 'all'] });
      haptics.success();
      goTo(tierIdx + 1, nextSaved);
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Save failed', tone: 'warn' });
    },
  });

  const onSave = useCallback(() => {
    // Submit in grid (elo-desc) order — apply_tiers spreads the tier band
    // top-down in submitted order, preserving a sane intra-tier ranking.
    const ids = gridPlayers.filter((p) => selected.has(p.id)).map((p) => p.id);
    const cleared = (savedByTier[tier] ?? []).filter((id) => !selected.has(id));
    if (ids.length === 0 && cleared.length === 0) {
      // Nothing picked and nothing to un-pick — same as Skip (a save with
      // no assignments and no clears is a 400 on the backend).
      goTo(tierIdx + 1, savedByTier);
      return;
    }
    saveMutation.mutate({ ids, cleared });
  }, [gridPlayers, selected, savedByTier, tier, tierIdx, goTo, saveMutation]);

  const onSkip = useCallback(() => goTo(tierIdx + 1, savedByTier), [tierIdx, savedByTier, goTo]);
  const onBack = useCallback(() => goTo(tierIdx - 1, savedByTier), [tierIdx, savedByTier, goTo]);

  // Position switch restarts the walk for the new position. Committed
  // saves are already on the server; only the in-progress selection is
  // local, so no confirmation needed.
  const onPosition = useCallback((p: Position) => {
    if (p === position) return;
    setPosition(p);
    setTierIdx(0);
    setSelected(new Set());
    setSavedByTier({});
    setSearch('');
    haptics.selection();
  }, [position]);

  // #137 — format switch restarts the walk on the other format's board.
  // Committed saves this run belong to the PREVIOUS format (every save
  // went to that format's server session), so savedByTier must reset with
  // the step state; the pool query re-reads through its format-scoped key
  // ['rankings', activeFormat, position] once the switch lands.
  const onFormat = useCallback(
    async (f: ScoringFormat) => {
      haptics.selection();
      const ok = await setFormat(f);
      if (!ok) {
        setToast({ msg: 'Could not switch format', tone: 'warn' });
        return;
      }
      setTierIdx(0);
      setSelected(new Set());
      setSavedByTier({});
      setSearch('');
    },
    [setFormat],
  );

  const renderChip = useCallback(
    ({ item }: { item: RankedPlayer }) => {
      const isSelected = selected.has(item.id);
      const currentTier = tierForElo(item.elo, position, fmt);
      const posKey = String(item.position).toLowerCase() as keyof typeof positionColors;
      return (
        <Pressable
          testID={`quick-set.chip.${item.id}`}
          accessibilityRole="button"
          accessibilityState={{ selected: isSelected }}
          accessibilityLabel={`${item.name}, currently ${TIER_LABEL[currentTier]}`}
          onPress={() => toggle(item.id)}
          style={[styles.chip, isSelected && styles.chipSelected]}
        >
          <View style={styles.chipTop}>
            <Text style={styles.chipName} numberOfLines={1}>
              {item.name}
            </Text>
            {isSelected ? <Icon name="check" size={12} color={ice.base} /> : null}
          </View>
          <View style={styles.chipMeta}>
            {SHOW_POSITION ? (
              <Text style={[styles.chipPos, { color: positionColors[posKey] ?? chalk.dim }]}>
                {item.position}
              </Text>
            ) : null}
            <Text style={styles.chipTeam}>{item.team ?? 'FA'}</Text>
            {item.age != null ? (
              <Text style={styles.chipAge}>{item.age}</Text>
            ) : null}
            <Text style={[styles.chipTier, { color: tierColors[currentTier] }]}>
              {TIER_LABEL[currentTier]}
            </Text>
          </View>
        </Pressable>
      );
    },
    [selected, toggle, position, fmt],
  );

  const saving = saveMutation.isPending;
  const selectedCount = selected.size;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {/* #138 — keyboard-avoiding wrapper (EspnLinkSheet pattern): the
          walk's footer is pinned absolute-bottom, so without this the iOS
          keyboard covers Back / Skip / Save while the search input has
          focus. 'padding' lifts the footer (absolute insets respect the
          parent's padding in RN). */}
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
          Tiers board (format row above the position switcher). Switching
          restarts the walk on the other format's board. */}
      <View style={styles.formatRow} testID="quick-set.format-toggle">
        <FormatToggle
          value={activeFormat}
          onChange={onFormat}
          disabled={formatSwitching || saving}
        />
      </View>

      {/* Position switcher — PositionTabs spec, same construction as the
          Tiers board's. */}
      <View style={styles.switcher}>
        {POSITIONS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              testID={`quick-set.pos-tab.${p}`}
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

      {/* Step header — the tier being set (tick label in the tier's
          color; the label itself reads in pick terms) and where we are
          in the walk. */}
      <View style={styles.stepHeader}>
        <View style={styles.stepTitleRow}>
          <TickLabel color={tierColors[tier]}>{TIER_LABEL[tier]}</TickLabel>
          <Text style={styles.stepProgress}>{`Tier ${tierIdx + 1} of ${TIERS.length}`}</Text>
        </View>
        <Text style={styles.stepHint}>
          Tap every {position} who belongs in {TIER_LABEL[tier]}, then save to
          move on. Each card shows the tier the player is in now.
        </Text>
      </View>

      {/* #138 — compact name filter over the grid. Design-system Input
          construction (ink-2 fill, line-strong border, radius sm, faint
          placeholder, ice focus border); clears on every step / position /
          format change. Filtering only narrows the VIEW — selections made
          before narrowing stay picked and still save. */}
      <TextInput
        testID="quick-set.search"
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
      ) : (
        <FlatList
          data={visiblePlayers}
          keyExtractor={(p) => p.id}
          renderItem={renderChip}
          numColumns={3}
          columnWrapperStyle={styles.gridRow}
          contentContainerStyle={styles.grid}
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={
            <Text style={styles.emptyText}>
              {query.length > 0 && gridPlayers.length > 0
                ? `No ${position} here matches “${search.trim()}”.`
                : `Every ${position} is already placed in an earlier tier.`}
            </Text>
          }
        />
      )}

      {/* Walk controls pinned to the bottom: Back / Skip / Save-and-next. */}
      <View style={styles.footer}>
        <Button
          variant="ghost"
          compact
          label="Back"
          disabled={tierIdx === 0 || saving}
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
          testID="quick-set.save-btn"
          disabled={saving || rankingsQuery.isLoading}
          onPress={onSave}
          style={({ pressed }) => [
            styles.saveBtn,
            pressed && { backgroundColor: ice.press },
            (saving || rankingsQuery.isLoading) && { opacity: 0.45 },
          ]}
        >
          {saving ? (
            <ActivityIndicator color={ice.on} />
          ) : (
            <Text style={styles.saveBtnText}>
              {`Save ${TIER_LABEL[tier]}${selectedCount > 0 ? ` (${selectedCount})` : ''}`}
              {isLastTier ? ' & finish' : ''}
            </Text>
          )}
        </Pressable>
      </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  kav: { flex: 1 },
  // #137 — row hosting the SF/1QB FormatToggle, above the position
  // switcher (consistent slot with TiersScreen's formatRow).
  formatRow: {
    marginHorizontal: space.lg,
    marginTop: space.sm,
  },
  // #138 — Input construction per the design system: 1px line-strong
  // border, ink-2 fill, radius sm, chalk text, faint placeholder; focus =
  // ice border. Compact single row between the step header and the grid.
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
  // Small selectable player card: ink-1 surface, hairline, radius sm.
  // Selected = ice border + check icon (two signals, matching the board's
  // multi-select convention). Three per row; ≥48px tall for touch targets.
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
  chipMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 2,
  },
  // Position + current-tier micro-labels. Color is paired with the text
  // itself (the label IS the encoding), per the accessibility floor.
  // #140: POS renders only when SHOW_POSITION; team + age (bottom-row
  // mockup spec — team 9px uiSemi chalk-dim uppercase, age 9px Plex Mono
  // data numeral, existing bare 6px gaps, no dot glyphs) sit before the
  // tier label at the chip's unchanged dimensions.
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
  chipAge: {
    fontFamily: fonts.data,
    fontSize: 9,
    color: chalk.dim,
  },
  chipTier: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  emptyText: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    paddingVertical: space.xl,
  },
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
