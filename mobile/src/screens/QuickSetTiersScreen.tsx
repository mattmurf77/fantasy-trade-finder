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
  LayoutChangeEvent,
  AppState,
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
import { TickLabel, Button, Icon, Text as ChalkText } from '../components/chalkline';
import Toast from '../components/Toast';
import FormatToggle from '../components/FormatToggle';
import { setPinnedBottomBarHeight } from '../components/FeedbackFAB';
import RookieScopeControl, { RookieScopeEmpty } from '../components/RookieScopeControl';
import { useRookieScope } from '../state/rookieScope';
import { getRankings, saveTiers, splitRankings } from '../api/rankings';
import { TIERS, TIER_LABEL, tierForElo } from '../utils/tierBands';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { useScoringFormat } from '../hooks/useScoringFormat';
import { getOnboardingState, patchOnboardingState } from '../state/useOnboardingState';
import { setPendingQuicksetRegen } from '../state/onboardingBus';
import { track } from '../api/events';
import {
  requestGuideStep,
  guidedAvatarActive,
  guideV2Active,
  recordGuideReceipt,
} from '../state/useGuide';
import { S as GUIDE, GUIDE_RECEIPTS } from '../components/analystScript';
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

  // S2 PRD-04 ride-along (flag visual.chalkline_cleanup): 9px chip metas
  // rise to the 11px type floor; faint content text promotes to dim.
  const cleanup = useFlag('visual.chalkline_cleanup');

  // S3 PRD-01 — report the pinned walk footer to the feedback FAB so it
  // rides above Back/Skip/Save instead of covering them. Focused-only
  // (stack screens stay mounted behind pushes); FAB ignores reports while
  // ux.touch_polish is off.
  const isFocused = useIsFocused();
  const [footerH, setFooterH] = useState(0);
  React.useEffect(() => {
    setPinnedBottomBarHeight('quickset', isFocused ? footerH : 0);
  }, [isFocused, footerH]);
  React.useEffect(() => () => setPinnedBottomBarHeight('quickset', 0), []);

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

  // Guided Onboarding v2 — `quickset_started {position, source}`: the
  // client-observable INTENT half of the Quick Set funnel, and `N1`'s
  // declared adoption event. Its completion twin (`quickset_completed`) is
  // SERVER-fired (per via:'quickset'-tagged tier commit — NOT per completed
  // position; a walk that accepts consensus by tapping through saves
  // nothing and is server-invisible) and can never be observed here, so the
  // client receipt written at the end of the walk stands in for it. The
  // per-position completion read is analysis-side: `quickset_step_advanced`
  // with tier_index == tier_count - 1.
  //
  // `source` is the guided hand-off vs. an organic entry. `onboardingReturn`
  // is that hand-off's marker today (TradesScreen's `acceptQuicksetPrompt`
  // and the s5.5 next-position CTA both set it); `guidedArrival` is read
  // alongside it so a guided route that carries the chain marker instead
  // (PRD §5.3-A moves s3.2's CTA to RankHome) is still attributed.
  //
  // Fires once per MOUNT, on the position the walk OPENED on — a mid-walk
  // position switch restarts the walk in place and is not a second start.
  React.useEffect(() => {
    if (!guideV2Active()) return;
    const source =
      onboardingReturn || typeof route.params?.guidedArrival === 'string'
        ? 'guide'
        : 'organic';
    // Event only, no receipt: `quickset_started` is not in S1's
    // `GUIDE_RECEIPTS` vocabulary and no step retires on it (`n1` declares
    // it as its `adoptionEvent`, which is analysis-side and never read by
    // the engine). The receipt that matters is `quickset_completed_local`,
    // written at the end of the walk below.
    track('quickset_started', { position, source }, 'QuickSetTiers');
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

  // ── P0-7 F3/F4 · Quick Set per-rung telemetry ───────────────────────
  // Refs, not state: none of this renders, and a blur/unmount handler
  // reads them at a moment when a closed-over state value would be stale.
  const stepStartRef = React.useRef(Date.now());       // reset on every advance
  const walkStartRef2 = React.useRef(Date.now());      // whole-walk clock for F4
  const abandonRef = React.useRef({ tierIdx: 0, tiersDone: 0, position });
  const completedRef = React.useRef(false);            // set in goTo's done branch
  const abandonFiredRef = React.useRef(false);         // blur AND unmount both fire

  React.useEffect(() => {
    abandonRef.current = {
      tierIdx,
      tiersDone: Object.keys(savedByTier).length,
      position,
    };
  }, [tierIdx, savedByTier, position]);

  // P0-7 F4 — the drop-off curve. `screen_left` gives dwell but not WHERE
  // in the ladder they stopped, which is the whole question. Fires on
  // blur (the reliable signal: completion navigates to another TAB, which
  // does not unmount this screen) and on unmount, deduped, and only when
  // there is progress to report and the walk did not complete.
  React.useEffect(() => {
    const fire = (reason: 'nav' | 'background') => {
      if (abandonFiredRef.current || completedRef.current) return;
      const { tierIdx: ti, tiersDone, position: pos } = abandonRef.current;
      if (ti === 0 && tiersDone === 0) return;      // never started — not an abandon
      abandonFiredRef.current = true;
      track('quickset_abandoned', {
        position: pos,
        tier_index: ti,
        tiers_done: tiersDone,
        ms: Date.now() - walkStartRef2.current,
        reason,
      }, 'QuickSetTiers');
    };
    const unsubBlur = navigation.addListener('blur', () => fire('nav'));
    const appSub = AppState.addEventListener('change', (st) =>
      st === 'background' ? fire('background') : undefined,
    );
    return () => {
      unsubBlur();
      appSub.remove();
      fire('nav');                                  // unmount without a blur
    };
  }, [navigation]);

  const tier = TIERS[tierIdx];
  const isLastTier = tierIdx === TIERS.length - 1;

  // rookie-draft M2 — the walk's pool narrows to the rookie subset. Scope
  // rides the query key (a strict suffix, so every existing prefix
  // invalidation still covers it) and the walk restarts on a scope change.
  const rookieScope = useRookieScope();
  const rankingsQuery = useQuery({
    queryKey: rookieScope.isRookie
      ? ['rankings', activeFormat, position, 'rookie']
      : ['rankings', activeFormat, position],
    queryFn: () => getRankings(position, { scope: rookieScope.param }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const { rows: rankingRows, empty: scopeEmpty } = useMemo(() => {
    const s = splitRankings(rankingsQuery.data);
    return { rows: s.rows as RankedPlayer[], empty: s.empty };
  }, [rankingsQuery.data]);

  const players = useMemo(
    () => rankingRows.slice().sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0)),
    [rankingRows],
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

  // rookie-draft M2 — start the ladder at the FIRST ROOKIE-BEARING RUNG.
  // A rookie class rarely reaches the top of an 8-rung pick ladder, so an
  // unscoped start would open the walk on two or three empty steps and read
  // as "there's nothing here". The first rung that currently holds a scoped
  // player is the honest entry point; the user can still walk Back into the
  // higher rungs (they stay in the ladder, they just aren't the start).
  const firstScopedTierIdx = useMemo(() => {
    if (!rookieScope.isRookie || players.length === 0) return 0;
    let best = TIERS.length;
    for (const p of players) {
      const t = tierForElo(p.elo, position, fmt);
      if (!t) continue;
      const i = TIERS.indexOf(t);
      if (i >= 0 && i < best) best = i;
    }
    return best === TIERS.length ? 0 : best;
  }, [rookieScope.isRookie, players, position, fmt]);

  // Apply that start ONCE per (position, format, scope) walk — never on a
  // background refetch, which would yank the user out of the step they are
  // standing in. `isPlaceholderData` is the load-bearing guard: the query
  // keeps the PREVIOUS key's rows on screen while the new scope fetches, so
  // without it the start rung would be computed from the wrong pool and
  // then never recomputed (the key would already be marked applied).
  const walkStartRef = React.useRef<string>('');
  React.useEffect(() => {
    if (players.length === 0 || rankingsQuery.isPlaceholderData) return;
    const key = `${position}:${fmt}:${rookieScope.scope}`;
    if (walkStartRef.current === key) return;
    walkStartRef.current = key;
    if (firstScopedTierIdx > 0) {
      setTierIdx(firstScopedTierIdx);
      setSelected(new Set());
      setSearch('');
    }
  }, [players.length, position, fmt, rookieScope.scope, firstScopedTierIdx,
      rankingsQuery.isPlaceholderData]);

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

  // P0-7 F3 — `seeded_accepted` is the operator's fairness point: the grid
  // arrives pre-seeded from consensus (gridPlayers are the players whose
  // CURRENT tier is this rung or unclaimed), so a rung can clear in one tap
  // and "32 taps" overstates the work. True <=> the user saved EXACTLY the
  // consensus-seeded set for this rung — no additions, no omissions.
  const trackStepAdvanced = (ids: string[], via: 'save' | 'skip' | 'empty') => {
    const seeded = gridPlayers
      .filter((p) => tierForElo(p.elo, position, fmt) === tier)
      .map((p) => p.id);
    const same =
      ids.length > 0 &&
      ids.length === seeded.length &&
      ids.every((id) => seeded.includes(id));
    track('quickset_step_advanced', {
      position,
      tier_index: tierIdx,
      tier_count: TIERS.length,
      seeded_accepted: same,
      picked_n: ids.length,
      via,
      ms: Date.now() - stepStartRef.current,
    }, 'QuickSetTiers');
    stepStartRef.current = Date.now();
  };

  // Move the walk to `idx`, pre-selecting whatever that tier already got
  // this run. Past the last tier → done, back to the Tiers board.
  const goTo = useCallback(
    (idx: number, savedMap: Partial<Record<Tier, string[]>>) => {
      if (idx >= TIERS.length) {
        completedRef.current = true;   // P0-7 F4 — walked the ladder; not an abandon
        // rookie-draft M2 (the client mirror of server invariant I-4): a
        // ROOKIES-ONLY walk has not completed the position, so it must not
        // write the completion record. `quicksetCompletedPositions` feeds
        // state/quicksetProgress.ts, which drives #244 launch routing (a
        // "complete" QB would route a no-pref user to Trios) plus the Trades
        // provenance chip and LeagueScreen's ranked count. The server-side
        // twin of this rule lives in the scoped save (no save_tiers_position,
        // no `quickset_completed` — our saves carry via:'rookie_quickset').
        // The forensic trail for a scoped walk is that `via` tag.
        if (!rookieScope.isRookie) {
          // Onboarding: record the completed position — the Trades provenance
          // chip flips CONSENSUS VALUES → YOUR BOARD off this list. Inert
          // write when onboarding surfaces are dark.
          const donePositions = getOnboardingState().quicksetCompletedPositions;
          if (!donePositions.includes(position)) {
            patchOnboardingState({
              quicksetCompletedPositions: [...donePositions, position],
            });
          }
          // No client `quickset_completed` here either (2026-08-13): the
          // name is SERVER-fired and the taxonomy's client/server namespaces
          // are disjoint by an import-time assert, so this call was dropped
          // behind a 200 since it shipped. Removed rather than renamed; its
          // lost `onboarding` prop is recorded as accepted loss in the
          // 2026-08-13 tracking-plan addendum. CORRECTION (2026-08-24): the
          // server row is NOT a per-completed-position signal and never was
          // — it fires per via:'quickset'-tagged tier commit (dark until
          // this build, which is the first to send the tag), and a walk
          // that tap-accepts consensus commits nothing. The authoritative
          // per-position completion read is `quickset_step_advanced` with
          // tier_index == tier_count - 1; see
          // docs/business/analytics/2026-08-24-quickset-via-gap.md.
          //
          // Guided Onboarding v2 (FR-E3) — the CLIENT receipt that stands in
          // for that server-fired name, so `N1`/`s3.2` can actually retire.
          // Same guard as the completion record above by construction: a
          // rookie-scoped walk has not completed the position, so it writes
          // no receipt either. No analytics row — this is engine
          // bookkeeping; `quickset_started` is the client's event.
          recordGuideReceipt(GUIDE_RECEIPTS.quicksetCompletedLocal);
        }
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
    [navigation, position, rookieScope.isRookie, onboardingReturn],
  );

  const saveMutation = useMutation({
    mutationFn: ({ ids, cleared, demoted }: { ids: string[]; cleared: string[]; demoted: string[] }) =>
      saveTiers(
        position,
        ids.length > 0 ? { [tier]: ids } : {},
        cleared,
        demoted,
        // rookie-draft M2 — merged-band scoped save + the forensic via tag.
        // Unscoped walks tag via:'quickset' (2026-08-24): the server has
        // branched on that value since analytics P0 (FR-20
        // `quickset_completed` per tagged commit, tier_save's `via` prop,
        // ranking_method written 'quickset' at the point of use) but no
        // client ever sent it — every mobile Quick Set save landed as plain
        // 'tiers' and all three reads were dark. See
        // docs/business/analytics/2026-08-24-quickset-via-gap.md.
        rookieScope.isRookie
          ? { scope: 'rookie', via: 'rookie_quickset' }
          : { via: 'quickset' },
      ),
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
      trackStepAdvanced(ids, 'save');   // P0-7 F3 — after a SUCCESSFUL save only
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
      // no assignments and no clears is a 400 on the backend). Skip ≠
      // demote (#161): only an explicit save with picks demotes anyone.
      trackStepAdvanced([], 'empty');   // P0-7 F3
      goTo(tierIdx + 1, savedByTier);
      return;
    }
    // #161 — demotion rule: an EXPLICIT save of this tier (≥1 player
    // picked) says "these are my <tier> players". Anyone still visible in
    // this step's grid whose CURRENT tier is this tier or higher was
    // passed over, so they must not silently keep that tier: they're sent
    // to unranked (below every band — pending placement), never to an
    // arbitrarily deeper tier. Players claimed by an earlier tier this
    // run aren't in the grid and are never demoted; lower-tier players
    // still get their own steps later in the walk.
    //
    // rookie-draft M2 / operator decision O4: this derives from
    // `gridPlayers`, which under scope IS the rookie subset — so a scoped
    // save demotes only rookies that were VISIBLE and unselected, and an
    // unshown vet is never touched. No scope branch is needed: the rule was
    // already bounded by what the user could see.
    const tierRank = TIERS.indexOf(tier);
    const demoted =
      ids.length === 0
        ? [] // clear-only save — restores the suggested tier, no demotion
        : gridPlayers
            .filter((p) => !selected.has(p.id))
            .filter((p) => {
              const cur = tierForElo(p.elo, position, fmt);
              return cur != null && TIERS.indexOf(cur) <= tierRank;
            })
            .map((p) => p.id);
    saveMutation.mutate({ ids, cleared, demoted });
  }, [gridPlayers, selected, savedByTier, tier, tierIdx, goTo, saveMutation, position, fmt]);

  const onSkip = useCallback(() => {
    trackStepAdvanced([], 'skip');      // P0-7 F3
    goTo(tierIdx + 1, savedByTier);
  }, [tierIdx, savedByTier, goTo]);
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
            <ChalkText
              scale="dense"
              style={[
                styles.chipTier,
                cleanup && styles.chipMetaFloor,
                { color: tierColors[currentTier] },
              ]}
            >
              {TIER_LABEL[currentTier]}
            </ChalkText>
          </View>
        </Pressable>
      );
    },
    [selected, toggle, position, fmt, cleanup],
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

      {/* rookie-draft M2 — the shared All players | Rookies control. A scope
          flip restarts the walk (the ladder start, the grid and the
          this-run bookkeeping all belong to one scope). */}
      <RookieScopeControl
        surface="quick-set"
        disabled={saving}
        onChange={() => {
          setTierIdx(0);
          setSelected(new Set());
          setSavedByTier({});
          setSearch('');
        }}
      />

      {/* Position switcher — PositionTabs spec, same construction as the
          Tiers board's. */}
      <View style={styles.switcher}>
        {POSITIONS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              testID={`quick-set.pos-tab.${p}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
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
          Tap every {rookieScope.isRookie ? 'rookie ' : ''}{position} who
          belongs in {TIER_LABEL[tier]}, then save to move on. Each card shows
          the tier the player is in now.
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
      ) : scopeEmpty ? (
        /* rookie-draft M2 — designed state, not an error. */
        <RookieScopeEmpty surface="quick-set" empty={scopeEmpty} position={position} />
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
            /* S2 PRD-04 — explanatory content, not a placeholder: faint
               promotes to dim under visual.chalkline_cleanup. */
            <Text style={[styles.emptyText, cleanup && styles.emptyTextDim]}>
              {query.length > 0 && gridPlayers.length > 0
                ? `No ${position} here matches “${search.trim()}”.`
                : `Every ${position} is already placed in an earlier tier.`}
            </Text>
          }
        />
      )}

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
          disabled={tierIdx === 0 || saving}
          onPress={onBack}
        />
        {/* #233 — with zero selected, Skip is HIDDEN: it duplicated the
            primary (the empty save composes as a skip), so two buttons
            offered one advance path. It reappears the moment a chip is
            picked. */}
        {selectedCount > 0 ? (
          <Button
            variant="secondary"
            compact
            label={isLastTier ? 'Skip & finish' : 'Skip'}
            disabled={saving}
            onPress={onSkip}
          />
        ) : null}
        {/* #233 (supersedes the #159 label; approved mock
            rank-method-consolidation-v2 §C) — with zero chips selected the
            primary becomes the position-aware action-first CTA
            "Continue — no QBs this high" ("Continue & finish" on the last
            tier, the short-fit fallback: "this high" reads wrong at FA and
            the full string + suffix would overflow). It reverts instantly
            via `selectedCount` (derived from the selection state) the
            moment a chip is tapped. LABEL ONLY: the press still runs
            onSave, whose empty branch composes as a Skip (and #161
            demotion only ever fires on a save with ≥1 pick — see onSave). */}
        <Pressable
          testID="quick-set.save-btn"
          accessibilityRole="button"
          accessibilityLabel={
            selectedCount === 0
              ? isLastTier
                ? 'No players this tier, continue and finish'
                : `No ${position}s this high, continue to the next tier`
              : `Save ${TIER_LABEL[tier]}${isLastTier ? ' and finish' : ''}`
          }
          accessibilityState={{ disabled: saving || rankingsQuery.isLoading, busy: saving }}
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
              {selectedCount === 0
                ? isLastTier
                  ? 'Continue & finish'
                  : `Continue — no ${position}s this high`
                : `Save ${TIER_LABEL[tier]} (${selectedCount})${isLastTier ? ' & finish' : ''}`}
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
  // S2 PRD-04 (visual.chalkline_cleanup) — 11px type floor for the chip
  // meta row (was 9px, below the global floor; components.md updated).
  chipMetaFloor: { fontSize: 11 },
  emptyText: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    paddingVertical: space.xl,
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
