import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  ActivityIndicator,
  LayoutChangeEvent,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute, useIsFocused } from '@react-navigation/native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Svg, { Path } from 'react-native-svg';

import {
  ink,
  chalk,
  semantic,
  tier as tierColors,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
} from '../theme/chalkline';
import { Button, Icon, Text as CText } from '../components/chalkline';
import RankChipGrid from '../components/RankChipGrid';
import RosterTierBoard, { type RosterTierChip } from '../components/RosterTierBoard';
import TierTargetChips from '../components/TierTargetChips';
import { LockGlyph } from '../components/PlayerContextMenu';
import { setPinnedBottomBarHeight } from '../components/FeedbackFAB';
import { getAssetPrefs, setAssetPref, type OwnedPick } from '../api/league';
import { reorderRankings, saveTiers } from '../api/rankings';
import { track } from '../api/events';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { useRosterSetup } from '../state/rosterSetup';
import { setPendingGuidedRegen } from '../state/onboardingBus';
import { useMyRosterAssets } from '../hooks/useMyRosterAssets';
import { useSetupSections } from '../hooks/useSetupSections';
import { haptics } from '../utils/haptics';
import { tierForElo, TIER_LABEL } from '../utils/tierBands';
import {
  SETUP_POSITIONS,
  changedCount,
  countStates,
  keepGuardNote,
  listForState,
  orderedIdsForSave,
  picksBeyondCap,
  playerSection,
  trackedAssetIds,
  prefillStates,
  rankSteps,
  sortPicks,
  applyTierMove,
  tierMoveCounts,
  tierPrefill,
  tierRebase,
  tierOfMap,
  tierSavePayloads,
  type AssetSetupState,
  type TierBoard,
  type TierBoardPlayer,
} from '../utils/rosterSetup';
import type { Position, RankedPlayer, ScoringFormat, Tier } from '../shared/types';

// Roster-first setup for Find a Trade (flag `trades.roster_setup`;
// docs/plans/roster-first-trade-setup/prd.md §3–§7).
//
// A pushed screen in the TRADES stack. Tab-stack ⇒ it mounts NO FeedbackFAB
// of its own: RootNav's single global mount covers it (#188 / #196 / #197).
// The pinned footer reports its height through `setPinnedBottomBarHeight`
// instead, exactly as Quick Set / Quick Rank do.
//
// Three steps:
//   1. toggles — every rostered player + owned pick, Move · — · Keep, each
//      tap autosaved through POST /api/league/asset-prefs (list ∈
//      trade_block | untouchable | none — nothing else, ever).
//   2. rank    — one position at a time over the caller's own roster
//      players, Quick Rank's chip grammar (shared RankChipGrid), each saved
//      position posted to /api/rankings/reorder with NO `via` (prd §5.2 —
//      `via:'quickrank'` would feed this flow into the Quick Rank funnel).
//   3. done    — summary; when anything changed, the onboarding regen bus
//      gets source 'roster_setup' and TradesHome forces one fresh job.
//
// The deck under this push keeps loading the whole time: nothing here
// blocks, cancels or waits on it, so Skip costs no time (prd §7).

type Entry = 'first_pass' | 'roster_changed' | 'manual_dna' | 'entry_card';
type Step = 'toggles' | 'rank' | 'tiers' | 'done';

interface SetupAsset {
  id: string;
  isPick: boolean;
  /** Section key: QB | RB | WR | TE | PICK. */
  section: Position | 'PICK';
  name: string;
  meta: string;
  tier: Tier | null;
  beyondCap: boolean;
  /** Board Elo when the player is on the caller's board (rankable). */
  elo: number | null;
  team?: string | null;
  age?: number | null;
}

// Tier encode colors for the "Move to" chips (data encodings).
const tierAccent = (t: Tier): string => tierColors[t];

const SECTIONS: (Position | 'PICK')[] = [...SETUP_POSITIONS, 'PICK'];
const SECTION_LABEL: Record<Position | 'PICK', string> = {
  QB: 'QB', RB: 'RB', WR: 'WR', TE: 'TE', PICK: 'Picks',
};

// Picks carry the 1st-round tier teal as their data color, the same as the
// Trade DNA sheet's PICK dot (dnaPosColor).
function sectionColor(s: Position | 'PICK'): string {
  if (s === 'PICK') return tierColors.first_1;
  return positionColors[s.toLowerCase() as keyof typeof positionColors] ?? ink.lineStrong;
}

function union(a: readonly string[], b: readonly string[]): string[] {
  return Array.from(new Set([...a, ...b]));
}

// Arrow-out-of-the-box: the Move segment's glyph (prd §4.2 — state is fill
// PLUS glyph, never color alone; #360 R-15). Stroke-only, Chalkline icon
// construction (20×20 viewBox, 1.75 weight, square caps).
function MoveGlyph({ size = 12, color = chalk.dim }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={color}
      strokeWidth={1.75} strokeLinecap="square">
      <Path d="M9 4H4v12h12v-5" />
      <Path d="M12 3h5v5M17 3l-8 8" />
    </Svg>
  );
}

function SetupToggle({
  assetId,
  name,
  value,
  onChange,
}: {
  assetId: string;
  name: string;
  value: AssetSetupState;
  onChange: (next: AssetSetupState) => void;
}) {
  const segs: { key: AssetSetupState; label: string; a11y: string }[] = [
    { key: 'move', label: 'Move', a11y: `Move ${name}` },
    { key: 'open', label: '—', a11y: `No opinion on ${name}` },
    { key: 'keep', label: 'Keep', a11y: `Keep ${name}` },
  ];
  return (
    <View style={styles.toggle}>
      {segs.map((s, i) => {
        const selected = value === s.key;
        const color = selected ? chalk.base : chalk.dim;
        return (
          <Pressable
            key={s.key}
            testID={`roster-setup.row.${assetId}.${s.key}`}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={s.a11y}
            onPress={() => onChange(s.key)}
            hitSlop={{ top: 6, bottom: 6 }}
            style={({ pressed }) => [
              styles.seg,
              i > 0 && styles.segDivider,
              selected && styles.segSelected,
              pressed && !selected && { backgroundColor: ink.ink2 },
            ]}
          >
            {s.key === 'move' && selected ? <MoveGlyph color={color} /> : null}
            {s.key === 'keep' && selected ? <LockGlyph size={12} color={color} /> : null}
            <Text style={[styles.segText, { color }, selected && styles.segTextSel]}>
              {s.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function RosterSetupScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const queryClient = useQueryClient();
  const isFocused = useIsFocused();

  const entry: Entry = route.params?.entry ?? 'manual_dna';
  const filterIds: string[] | null = Array.isArray(route.params?.filterAssetIds)
    ? route.params.filterAssetIds.map(String)
    : null;

  // Defensive gate (scope §3 check 4): the route is registered
  // unconditionally (a flag revalidation must never break an in-flight
  // push), so the SCREEN carries the flag. Every entry point is already
  // gated; a stale deep push with the flag off renders nothing but Back.
  const rosterSetupOn = useFlag('trades.roster_setup');

  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const leagueName = league?.league_name ?? null;
  const userId = useSession((s) => s.user)?.user_id || '';
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';

  const writeRecord = useRosterSetup((s) => s.write);

  // ── Data ────────────────────────────────────────────────────────────
  const roster = useMyRosterAssets(leagueId, userId, rosterSetupOn);
  const prefsQuery = useQuery({
    queryKey: ['asset-prefs', leagueId],
    queryFn: () => getAssetPrefs(leagueId!),
    enabled: rosterSetupOn && !!leagueId,
    staleTime: 60_000,
  });
  // The board + values reads that decide each player's section, shared
  // with the TradesHome card so both apply ONE rule (`useSetupSections`).
  const { valuesQuery, boardsSettled, boardByPos, sectionOf } = useSetupSections(rosterSetupOn);

  const loading =
    (!roster.rostersReady && !roster.rostersError)
    || !roster.picksSettled
    || prefsQuery.isLoading
    || valuesQuery.isLoading
    || !boardsSettled;
  const loadError = roster.rostersError || prefsQuery.isError || valuesQuery.isError;

  // Every asset, in render order: sections QB/RB/WR/TE (board Elo desc, then
  // consensus value desc for players off the board), then picks (season,
  // round, priced value). Non-core positions (K, DEF) have no section.
  const assets: SetupAsset[] = useMemo(() => {
    if (loading || loadError) return [];
    const values = new Map((valuesQuery.data?.players ?? []).map((v) => [String(v.id), v]));
    const players: (SetupAsset & { sortVal: number })[] = [];
    for (const id of roster.playerIds) {
      const v = values.get(id);
      const section = playerSection(id, boardByPos, v?.position);
      if (!section) continue;
      const found: RankedPlayer | undefined = boardByPos[section]?.get(id);
      const team = found?.team ?? v?.team ?? null;
      const age = found?.age ?? v?.age ?? null;
      players.push({
        id,
        isPick: false,
        section,
        name: found?.name ?? v?.name ?? `Player ${id}`,
        meta: [team ?? 'FA', age != null ? String(age) : null].filter(Boolean).join(' · '),
        tier: found ? tierForElo(found.elo, section, fmt) : v?.tier ?? null,
        beyondCap: false,
        elo: found ? found.elo : null,
        team,
        age,
        // Board players first (Elo), then off-board players (consensus).
        sortVal: found ? 1e9 + found.elo : v?.value ?? 0,
      });
    }
    players.sort((a, b) => b.sortVal - a.sortVal);
    const beyond = picksBeyondCap(roster.picks);
    const picks: SetupAsset[] = sortPicks(roster.picks).map((pk: OwnedPick) => ({
      id: pk.pick_id,
      isPick: true,
      section: 'PICK',
      name: pk.label,
      meta: pk.tier ? TIER_LABEL[pk.tier] : 'Pick',
      tier: pk.tier ?? null,
      beyondCap: beyond.has(pk.pick_id),
      elo: null,
    }));
    return [...players.map(({ sortVal: _s, ...a }) => a), ...picks];
  }, [loading, loadError, valuesQuery.data, roster.playerIds, roster.picks, boardByPos, fmt]);

  // What the snapshot records: THE tracked set (`utils/rosterSetup.trackedAssetIds`),
  // the same set the TradesHome card diffs — every player listed above, every pick.
  const allAssetIds = useMemo(
    () => (assets.length === 0 ? [] : trackedAssetIds(roster.playerIds, sectionOf, roster.picks.map((p) => p.pick_id))),
    [assets, roster.playerIds, roster.picks, sectionOf],
  );
  const visibleAssets = useMemo(
    () => (filterIds ? assets.filter((a) => filterIds.includes(a.id)) : assets),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [assets, filterIds?.join('|')],
  );

  // ── Toggle state: seeded ONCE from the saved tags ─────────────────────
  const [states, setStates] = useState<Record<string, AssetSetupState>>({});
  const prefillRef = useRef<Record<string, AssetSetupState> | null>(null);
  const confirmedRef = useRef<Record<string, AssetSetupState>>({});
  useEffect(() => {
    if (prefillRef.current || loading || loadError || assets.length === 0 || !prefsQuery.data) return;
    const seed = prefillStates(allAssetIds, prefsQuery.data);
    prefillRef.current = seed;
    confirmedRef.current = { ...seed };
    setStates(seed);
  }, [loading, loadError, assets.length, allAssetIds, prefsQuery.data]);
  const seeded = prefillRef.current != null;

  const [step, setStep] = useState<Step>('toggles');
  const stepRef = useRef<Step>('toggles');
  stepRef.current = step;
  const openedAt = useRef(Date.now());

  // roster_setup_shown — once per entry, on the first render that has the
  // roster (an error or empty roster is not "shown").
  const shownRef = useRef(false);
  useEffect(() => {
    if (shownRef.current || !seeded || !leagueId) return;
    shownRef.current = true;
    const prefill = prefillRef.current ?? {};
    track('roster_setup_shown', {
      league_id: leagueId,
      entry,
      roster_size: assets.filter((a) => !a.isPick).length,
      pick_count: assets.filter((a) => a.isPick).length,
      prefilled_count: Object.values(prefill).filter((s) => s !== 'open').length,
    }, 'RosterSetup');
  }, [seeded, leagueId, entry, assets]);

  // ── Autosave (#236 machinery, per asset) ──────────────────────────────
  // One POST in flight at a time. A tap on an asset whose write is already
  // queued REPLACES the queued value (coalesced; last write wins), and a
  // queued value equal to what the server already holds is dropped. On a
  // failure the asset reverts to the last confirmed state unless the user
  // has tapped it again since.
  const desiredRef = useRef<Map<string, AssetSetupState>>(new Map());
  const inFlightRef = useRef(false);
  const drainWaiters = useRef<(() => void)[]>([]);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [pendingWrites, setPendingWrites] = useState(0);

  const flush = useCallback(async () => {
    if (inFlightRef.current || !leagueId) return;
    const next = desiredRef.current.entries().next();
    if (next.done) {
      setPendingWrites(0);
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
      const waiters = drainWaiters.current;
      drainWaiters.current = [];
      waiters.forEach((w) => w());
      return;
    }
    const [id, desired] = next.value;
    desiredRef.current.delete(id);
    if (confirmedRef.current[id] === desired) {
      void flush();
      return;
    }
    inFlightRef.current = true;
    try {
      await setAssetPref(leagueId, id, listForState(desired));
      confirmedRef.current[id] = desired;
    } catch (e: any) {
      if (!desiredRef.current.has(id)) {
        setStates((s) => ({ ...s, [id]: confirmedRef.current[id] ?? 'open' }));
      }
      setWriteError(e?.message || 'Could not save that change');
    } finally {
      inFlightRef.current = false;
      void flush();
    }
  }, [leagueId, queryClient]);

  const drain = useCallback(
    () => new Promise<void>((resolve) => {
      if (!inFlightRef.current && desiredRef.current.size === 0) resolve();
      else drainWaiters.current.push(resolve);
    }),
    [],
  );

  const onToggle = useCallback((id: string, next: AssetSetupState) => {
    haptics.selection();
    setWriteError(null);
    setStates((s) => ({ ...s, [id]: next }));
    desiredRef.current.set(id, next);
    setPendingWrites(desiredRef.current.size + (inFlightRef.current ? 1 : 0));
    void flush();
  }, [flush]);

  const counts = useMemo(() => countStates(assets, states), [assets, states]);
  const guard = keepGuardNote(counts);

  // ── Rank step ───────────────────────────────────────────────────────
  // Rankable = the caller's roster players that are ON their board, in
  // board order. With the roster-changed entry, only positions that gained
  // a player are walked (prd §3.3).
  const rankableByPos = useMemo(() => {
    const out: Partial<Record<Position, SetupAsset[]>> = {};
    for (const a of assets) {
      if (a.isPick || a.elo == null) continue;
      const p = a.section as Position;
      (out[p] ??= []).push(a);
    }
    for (const p of SETUP_POSITIONS) out[p]?.sort((x, y) => (y.elo ?? 0) - (x.elo ?? 0));
    return out;
  }, [assets]);
  const rankPositions = useMemo(() => {
    const only = filterIds
      ? new Set(assets.filter((a) => !a.isPick && filterIds.includes(a.id)).map((a) => a.section))
      : null;
    const n: Partial<Record<Position, number>> = {};
    for (const p of SETUP_POSITIONS) n[p] = rankableByPos[p]?.length ?? 0;
    return rankSteps(n, only);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankableByPos, assets, filterIds?.join('|')]);

  const [rankIdx, setRankIdx] = useState(0);
  const [clicked, setClicked] = useState<string[]>([]);
  const [rankSaving, setRankSaving] = useState(false);
  const [rankError, setRankError] = useState<string | null>(null);
  const [ranked, setRanked] = useState<{ position: Position; count: number }[]>([]);
  const rankedRef = useRef(ranked);
  rankedRef.current = ranked;
  const rankPos = rankPositions[Math.min(rankIdx, Math.max(rankPositions.length - 1, 0))];
  const rankMembers = (rankPos ? rankableByPos[rankPos] : undefined) ?? [];
  const isLastRank = rankIdx >= rankPositions.length - 1;

  // ── Tier step (flag `trades.roster_tier_rank`; scope-tier-rank.md §2) ─
  // Step 2 forks on this flag at Continue. Off ⇒ the rank step above,
  // untouched. On ⇒ one page: every rostered QB/RB/WR/TE under the eight
  // pick-value tiers, tap players then a tier, Save posts only the moved
  // players, one scoped save per position. Picks are not on this page
  // (operator decision 3, 2026-11-11).
  const tierRankOn = useFlag('trades.roster_tier_rank');
  const tierPlayers = useMemo(() => {
    const onBoard: TierBoardPlayer[] = [];
    const offBoard: Partial<Record<Tier, string[]>> = {};
    const chips: Record<string, RosterTierChip> = {};
    const positionOf: Record<string, Position> = {};
    for (const a of assets) {
      if (a.isPick) continue;
      if (filterIds && !filterIds.includes(a.id)) continue;
      const position = a.section as Position;
      chips[a.id] = { id: a.id, name: a.name, position, team: a.team };
      if (a.elo != null && a.tier) {
        onBoard.push({ id: a.id, position, elo: a.elo, tier: a.tier });
        positionOf[a.id] = position;
      } else {
        // Not on the caller's board: read-only under the consensus tier
        // (a save would drop him anyway, ranking_service.py:2000-2001).
        (offBoard[a.tier ?? 'waivers'] ??= []).push(a.id);
      }
    }
    return { onBoard, offBoard, chips, positionOf };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets, filterIds?.join('|')]);
  // Consensus tier per roster player, from the values query the screen
  // already runs (operator decision 5's market label).
  const marketTierById = useMemo(() => {
    const out: Record<string, Tier | null> = {};
    for (const v of valuesQuery.data?.players ?? []) {
      const id = String(v.id);
      if (tierPlayers.chips[id]) out[id] = v.tier ?? null;
    }
    return out;
  }, [valuesQuery.data, tierPlayers.chips]);

  // Seeded ONCE on entering the step, so a refetch after a partial save
  // never re-seeds over the user's moves. `tierHome` = the pre-fill (the
  // moved/up/down counts); `tierBase` = what the server holds now (the save
  // baseline, advanced per saved position — the "was" marker and the edge
  // placement are judged against it, as the server judges the move).
  const [tierHome, setTierHome] = useState<TierBoard | null>(null);
  const [tierBase, setTierBase] = useState<TierBoard | null>(null);
  const [tierBoard, setTierBoard] = useState<TierBoard | null>(null);
  const [tierSel, setTierSel] = useState<string[]>([]);
  const [tierSaving, setTierSaving] = useState(false);
  const [tierError, setTierError] = useState<string | null>(null);
  const [tierFailed, setTierFailed] = useState<Position[]>([]);
  const [reTiered, setReTiered] = useState(0);
  const tierOpenedAt = useRef(0);
  const tierSavedPositionsRef = useRef<Set<Position>>(new Set());
  const pendingTierPayloads = useMemo(
    () => (tierBoard && tierBase ? tierSavePayloads(tierBoard, tierBase, tierPlayers.positionOf) : []),
    [tierBoard, tierBase, tierPlayers.positionOf],
  );
  const tierDirtyRef = useRef(false);
  tierDirtyRef.current = pendingTierPayloads.length > 0;
  // The "was <tier>" marker names the tier the SERVER holds the player in
  // (the save baseline), so it marks exactly the unsaved moves.
  const prefillTierById = useMemo(() => (tierBase ? tierOfMap(tierBase) : {}), [tierBase]);
  // True from the first await of a Save/Retry until the sequence settles —
  // a ref, so a second tap and a back gesture see it without a re-render.
  const tierSavingRef = useRef(false);

  // ── Exits ───────────────────────────────────────────────────────────
  const exitHandledRef = useRef(false);
  const finalizedRef = useRef(false);
  const changedRef = useRef(false);

  const anyChange = useCallback(
    () => changedCount(states, prefillRef.current ?? {}) > 0
      || rankedRef.current.length > 0
      || tierSavedPositionsRef.current.size > 0,
    [states],
  );

  /** Store `done` + post the regen marker when anything changed. Idempotent. */
  const finalizeDone = useCallback(() => {
    if (finalizedRef.current || !leagueId) return;
    finalizedRef.current = true;
    const prev = useRosterSetup.getState().byLeague[leagueId];
    changedRef.current = anyChange();
    writeRecord(leagueId, {
      status: 'done',
      seenAssetIds: union(prev?.seenAssetIds ?? [], allAssetIds),
      rankedPositions: union(
        prev?.rankedPositions ?? [],
        [...rankedRef.current.map((r) => r.position), ...tierSavedPositionsRef.current],
      ) as Position[],
      prompt: null,
    });
    // TradesHome's focus effect consumes this on the pop: snapshot the deck
    // that loaded underneath, force ONE fresh job, diff (prd §6, AC-8).
    if (changedRef.current) setPendingGuidedRegen('roster_setup');
  }, [leagueId, allAssetIds, anyChange, writeRecord]);

  /** Skip on Step 1 (button, back, error): taps already autosaved stay;
   *  nothing regenerates. A `done` record is never downgraded. */
  const recordSkip = useCallback(() => {
    if (!leagueId) return;
    const prev = useRosterSetup.getState().byLeague[leagueId];
    writeRecord(leagueId, {
      status: prev?.status === 'done' ? 'done' : 'skipped',
      // The roster-changed card keeps prompting for the assets it named;
      // every other entry showed the whole roster, so it was seen.
      seenAssetIds: entry === 'roster_changed' || allAssetIds.length === 0
        ? prev?.seenAssetIds ?? []
        : union(prev?.seenAssetIds ?? [], allAssetIds),
    });
  }, [leagueId, entry, allAssetIds, writeRecord]);

  const trackSkipped = useCallback((stage: 'toggles' | 'rank' | 'tiers') => {
    if (!leagueId) return;
    track('roster_setup_skipped', { league_id: leagueId, entry, stage }, 'RosterSetup');
  }, [leagueId, entry]);

  const leave = useCallback(() => {
    exitHandledRef.current = true;
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('TradesHome');
  }, [navigation]);

  // Back (header control or edge swipe) = Skip at the current step (prd §7).
  // Bookkeeping only — the pop itself proceeds. On the rank step the setup
  // counts as done (toggles were confirmed with Continue) and the skip names
  // the stage; on the done step there is nothing left to record.
  // The tier step is the one exception that holds the pop: with unsaved
  // moves it asks "Discard your tier changes?" first (scope §2.2).
  const implicitExitRef = useRef<(e: any) => void>(() => {});
  implicitExitRef.current = (e: any) => {
    if (exitHandledRef.current || !rosterSetupOn) return;
    // A tier save in flight holds the pop with no prompt and no bookkeeping:
    // the user stays until the sequence settles (Skip is disabled meanwhile).
    if (stepRef.current === 'tiers' && tierSavingRef.current) {
      e?.preventDefault?.();
      return;
    }
    if (stepRef.current === 'tiers' && tierDirtyRef.current) {
      e?.preventDefault?.();
      confirmDiscardTiers(() => {
        exitHandledRef.current = true;
        finalizeDone();
        trackSkipped('tiers');
        navigation.dispatch(e.data.action);
      });
      return;
    }
    exitHandledRef.current = true;
    const s = stepRef.current;
    if (s === 'toggles') {
      recordSkip();
      trackSkipped('toggles');
    } else if (s === 'rank') {
      finalizeDone();
      trackSkipped('rank');
    } else if (s === 'tiers') {
      finalizeDone();
      trackSkipped('tiers');
    }
  };
  useEffect(
    () => navigation.addListener('beforeRemove', (e: any) => implicitExitRef.current(e)),
    [navigation],
  );

  const onSkip = useCallback(() => {
    recordSkip();
    trackSkipped('toggles');
    leave();
  }, [recordSkip, trackSkipped, leave]);

  const goDone = useCallback(() => {
    setStep('done');
    setClicked([]);
  }, []);

  const onContinue = useCallback(() => {
    if (!leagueId) return;
    const prefill = prefillRef.current ?? {};
    track('roster_setup_toggles_done', {
      league_id: leagueId,
      entry,
      move_count: counts.move,
      keep_count: counts.keep,
      open_count: counts.open,
      pick_move_count: counts.pickMove,
      pick_keep_count: counts.pickKeep,
      changed_count: changedCount(states, prefill),
      duration_ms: Date.now() - openedAt.current,
    }, 'RosterSetup');
    haptics.selection();
    if (tierRankOn) {
      // Step 2 = the one-page tier placement. Nothing on the caller's
      // board to place ⇒ straight to done, as the rank walk does.
      if (tierPlayers.onBoard.length === 0) goDone();
      else {
        const pre = tierPrefill(tierPlayers.onBoard);
        setTierHome(pre);
        setTierBase(pre);
        setTierBoard(pre);
        setTierSel([]);
        tierOpenedAt.current = Date.now();
        setStep('tiers');
      }
    } else if (rankPositions.length === 0) goDone();
    else {
      setRankIdx(0);
      setClicked([]);
      setStep('rank');
    }
  }, [leagueId, entry, counts, states, rankPositions.length, goDone, tierRankOn, tierPlayers.onBoard]);

  const toggleChip = useCallback((pid: string) => {
    setClicked((prev) => (prev.includes(pid) ? prev.filter((id) => id !== pid) : [...prev, pid]));
    haptics.selection();
  }, []);

  /** Save the current position (if anything was tapped), then advance —
   *  or, with `finish`, go to the done step. Nothing tapped = the current
   *  order stands; no POST. */
  const saveRank = useCallback(async (finish: boolean) => {
    if (!rankPos || rankSaving || !leagueId) return;
    setRankError(null);
    const advance = () => {
      setClicked([]);
      if (finish || isLastRank) goDone();
      else setRankIdx((i) => i + 1);
    };
    if (clicked.length === 0) {
      advance();
      return;
    }
    const ids = orderedIdsForSave(clicked, rankMembers.map((p) => p.id));
    setRankSaving(true);
    try {
      // No `via` — see the header.
      await reorderRankings(rankPos, ids);
      track('roster_setup_rank_saved', {
        league_id: leagueId,
        position: rankPos,
        players_ranked: clicked.length,
        players_total: rankMembers.length,
      }, 'RosterSetup');
      setRanked((r) => [...r.filter((x) => x.position !== rankPos), { position: rankPos, count: ids.length }]);
      rankedRef.current = [...rankedRef.current.filter((x) => x.position !== rankPos), { position: rankPos, count: ids.length }];
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      haptics.success();
      advance();
    } catch (e: any) {
      setRankError(e?.message || 'Could not save that order');
    } finally {
      setRankSaving(false);
    }
  }, [rankPos, rankSaving, leagueId, clicked, rankMembers, isLastRank, goDone, queryClient, activeFormat]);

  // ── Tier step handlers ─────────────────────────────────────────────
  const onTierToggle = useCallback((id: string) => {
    if (tierSaving) return;
    setTierSel((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    haptics.selection();
  }, [tierSaving]);

  /** Move to a tier: the merged-band edge rule applied locally (moved up ⇒
   *  bottom of the new tier, moved down ⇒ top), so the page shows what the
   *  server will save. Clears the selection. */
  const onTierMove = useCallback((ids: string[], t: Tier) => {
    if (tierSaving || !tierBase) return;
    setTierBoard((b) => (b ? applyTierMove(b, tierBase, ids, t) : b));
    setTierSel([]);
    setTierError(null);
    haptics.selection();
  }, [tierSaving, tierBase]);

  function confirmDiscardTiers(onDiscard: () => void) {
    Alert.alert('Discard your tier changes?', undefined, [
      { text: 'Keep editing', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: onDiscard },
    ]);
  }

  /** Save (or Retry with `only`): one scoped save per position that has a
   *  move, sequentially. A position that saves stays saved; a failure keeps
   *  its moves on the page and Retry re-posts only the failed positions.
   *  Nothing moved ⇒ no POST, straight to done. */
  const saveTierMoves = useCallback(async (only?: readonly Position[]) => {
    if (!tierBoard || !tierBase || !tierHome || tierSaving || tierSavingRef.current || !leagueId) return;
    const all = tierSavePayloads(tierBoard, tierBase, tierPlayers.positionOf);
    const payloads = only ? all.filter((p) => only.includes(p.position)) : all;
    setTierError(null);
    setTierSel([]);
    let base = tierBase;
    let savedNow = false;
    const failed: Position[] = [];
    let lastErr: any = null;
    if (payloads.length > 0) setTierSaving(true);
    tierSavingRef.current = true;
    try {
      for (const p of payloads) {
        try {
          await saveTiers(p.position, p.tiers as Record<string, string[]>, [], { scope: 'roster', via: 'roster_setup' });
          base = tierRebase(base, p);
          tierSavedPositionsRef.current.add(p.position);
          savedNow = true;
        } catch (e: any) {
          failed.push(p.position);
          lastErr = e;
        }
      }
    } finally {
      tierSavingRef.current = false;
    }
    setTierBase(base);
    setTierSaving(false);
    if (savedNow) {
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
    }
    if (failed.length > 0) {
      setTierFailed(failed);
      setTierError(lastErr?.message || "Couldn't save your tiers");
      return;
    }
    setTierFailed([]);
    // A Retry can succeed with newer moves still unsaved: stay on the page.
    if (tierSavePayloads(tierBoard, base, tierPlayers.positionOf).length > 0) return;
    if (tierSavedPositionsRef.current.size > 0) {
      const c = tierMoveCounts(tierBoard, tierHome);
      setReTiered(c.moved);
      track('roster_setup_tiers_saved', {
        league_id: leagueId,
        entry,
        moved_count: c.moved,
        moved_up_count: c.up,
        moved_down_count: c.down,
        players_total: tierPlayers.onBoard.length,
        positions_saved: tierSavedPositionsRef.current.size,
        duration_ms: Date.now() - tierOpenedAt.current,
      }, 'RosterSetup');
      haptics.success();
    }
    goDone();
  }, [tierBoard, tierBase, tierHome, tierSaving, leagueId, entry, tierPlayers, queryClient, activeFormat, goDone]);

  const onTierSkip = useCallback(() => {
    const go = () => {
      exitHandledRef.current = true;
      finalizeDone();
      trackSkipped('tiers');
      leave();
    };
    if (tierDirtyRef.current) confirmDiscardTiers(go);
    else go();
  }, [finalizeDone, trackSkipped, leave]);

  // Done state renders ⇒ the setup is complete: store, bus, event.
  const completedRef = useRef(false);
  useEffect(() => {
    if (step !== 'done' || completedRef.current || !leagueId) return;
    completedRef.current = true;
    finalizeDone();
    track('roster_setup_completed', {
      league_id: leagueId,
      entry,
      ranked_positions: rankedRef.current.length + tierSavedPositionsRef.current.size,
      changed: changedRef.current,
      duration_ms: Date.now() - openedAt.current,
    }, 'RosterSetup');
  }, [step, leagueId, entry, finalizeDone]);

  const [leaving, setLeaving] = useState(false);
  const onSeeTrades = useCallback(async () => {
    // Let queued tag writes land before TradesHome forces the fresh job, so
    // the regenerated deck reads the final tags.
    setLeaving(true);
    await drain();
    leave();
  }, [drain, leave]);

  // ── FAB offset (S3 PRD-01 contract: focused-only, 0 on blur/unmount) ─
  const [footerH, setFooterH] = useState(0);
  const footerVisible = rosterSetupOn && seeded && !loadError;
  useEffect(() => {
    setPinnedBottomBarHeight('roster_setup', isFocused && footerVisible ? footerH : 0);
  }, [isFocused, footerVisible, footerH]);
  useEffect(() => () => setPinnedBottomBarHeight('roster_setup', 0), []);
  const onFooterLayout = (e: LayoutChangeEvent) => setFooterH(e.nativeEvent.layout.height);

  // ── Render ──────────────────────────────────────────────────────────
  if (!rosterSetupOn) {
    return <SafeAreaView style={styles.safe} edges={['bottom']} testID="roster-setup.screen" />;
  }

  const errorView = (message: string) => (
    <View style={styles.centered}>
      <Text style={styles.errorText}>{message}</Text>
      {loadError ? (
        <Button variant="ghost" compact label="Try again" onPress={() => {
          roster.refetch();
          void prefsQuery.refetch();
          void valuesQuery.refetch();
        }} />
      ) : null}
      <Button
        variant="secondary"
        compact
        label="Skip to trades"
        testID="roster-setup.error.skip"
        onPress={onSkip}
      />
    </View>
  );

  let body: React.ReactNode;
  if (loadError) {
    body = errorView("Couldn't load your roster.");
  } else if (loading || (!seeded && assets.length > 0)) {
    body = (
      <View style={styles.centered}>
        <ActivityIndicator color={chalk.dim} />
      </View>
    );
  } else if (assets.length === 0 || visibleAssets.length === 0) {
    body = errorView(
      filterIds ? 'Those assets are no longer on your roster.' : 'No roster found for you in this league.',
    );
  } else if (step === 'toggles') {
    body = (
      <>
        <View style={styles.header}>
          {leagueName ? <Text style={styles.leagueName}>{leagueName}</Text> : null}
          <Text style={styles.heading} accessibilityRole="header">
            {filterIds ? 'New on your roster' : 'Your roster'}
          </Text>
          <Text style={styles.lede}>
            {filterIds
              ? 'Set the new arrivals. Everything else stays as you left it.'
              : "Tell us who's available. We'll build trades around it."}
          </Text>
        </View>
        <View style={styles.counter} testID="roster-setup.counter">
          <Text style={styles.counterText}>
            {`${counts.move} MOVE · ${counts.keep} KEEP · ${counts.open} OPEN`}
          </Text>
          {guard ? <Text style={styles.guard}>{guard}</Text> : null}
          {writeError ? <Text style={styles.writeError}>{writeError}</Text> : null}
        </View>
        <ScrollView contentContainerStyle={styles.list}>
          {SECTIONS.map((sec) => {
            const rows = visibleAssets.filter((a) => a.section === sec);
            if (rows.length === 0) return null;
            return (
              <View key={sec} style={styles.section}>
                <View style={styles.sectionHdr}>
                  <View style={[styles.sectionBar, { backgroundColor: sectionColor(sec) }]} />
                  <Text style={styles.sectionLabel}>{SECTION_LABEL[sec]}</Text>
                  <Text style={styles.sectionCount}>{rows.length}</Text>
                </View>
                {rows.map((a) => (
                  <View key={a.id} style={styles.row}>
                    <View style={[styles.rowMain, a.beyondCap && styles.rowGreyed]}>
                      <View style={styles.rowTop}>
                        {a.tier ? (
                          <View
                            style={[styles.tierDot, { backgroundColor: tierColors[a.tier] }]}
                            accessibilityLabel={TIER_LABEL[a.tier]}
                          />
                        ) : null}
                        <Text style={styles.rowName} numberOfLines={1}>{a.name}</Text>
                      </View>
                      <Text style={styles.rowMeta} numberOfLines={1}>
                        {a.beyondCap ? `${a.meta} · not in trade search` : a.meta}
                      </Text>
                    </View>
                    <SetupToggle
                      assetId={a.id}
                      name={a.name}
                      value={states[a.id] ?? 'open'}
                      onChange={(next) => onToggle(a.id, next)}
                    />
                  </View>
                ))}
              </View>
            );
          })}
        </ScrollView>
        <View style={styles.footer} onLayout={onFooterLayout}>
          <Pressable
            testID="roster-setup.skip"
            accessibilityRole="button"
            onPress={onSkip}
            hitSlop={8}
            style={styles.textBtn}
          >
            <Text style={styles.textBtnLabel}>Skip for now</Text>
          </Pressable>
          <Button
            label="Continue"
            testID="roster-setup.continue"
            onPress={onContinue}
            style={styles.primaryBtn}
          />
        </View>
      </>
    );
  } else if (step === 'rank' && rankPos) {
    body = (
      <>
        <View style={styles.header}>
          <Text style={styles.leagueName}>Step 2 of 2 · optional</Text>
          <Text style={styles.heading} accessibilityRole="header">{`Rank your ${rankPos}s`}</Text>
          <Text style={styles.lede}>
            Tap in the order you value them. Untapped players keep their current order.
          </Text>
        </View>
        <View style={styles.posRow}>
          {rankPositions.map((p, i) => {
            const done = ranked.some((r) => r.position === p) || i < rankIdx;
            const active = i === rankIdx;
            return (
              <View
                key={p}
                style={[
                  styles.posTab,
                  active && styles.posTabActive,
                  active && { borderBottomColor: sectionColor(p) },
                ]}
              >
                <Text style={[styles.posTabText, active && styles.posTabTextActive]}>{p}</Text>
                {done && !active ? <Icon name="check" size={12} color={chalk.dim} /> : null}
              </View>
            );
          })}
        </View>
        <Text style={styles.tapCount}>
          {isLastRank && clicked.length === 0
            ? 'LAST POSITION'
            : `${clicked.length} OF ${rankMembers.length} TAPPED`}
        </Text>
        {rankError ? <Text style={styles.writeError}>{rankError}</Text> : null}
        <RankChipGrid
          testID={`roster-setup.rank.${rankPos}.chip`}
          players={rankMembers.map((a) => ({
            id: a.id, name: a.name, position: a.section, team: a.team, age: a.age,
          }))}
          clicked={clicked}
          onToggle={toggleChip}
        />
        <View style={styles.footer} onLayout={onFooterLayout}>
          <Button
            variant="secondary"
            compact
            label="Done ranking"
            testID="roster-setup.rank.done"
            disabled={rankSaving}
            onPress={() => void saveRank(true)}
          />
          <Button
            label={isLastRank ? 'Save & finish' : 'Save & next'}
            testID="roster-setup.rank.save"
            loading={rankSaving}
            disabled={rankSaving}
            onPress={() => void saveRank(false)}
            style={styles.primaryBtn}
          />
        </View>
      </>
    );
  } else if (step === 'tiers' && tierBoard) {
    const dirty = pendingTierPayloads.length > 0;
    body = (
      <>
        <RosterTierBoard
          board={tierBoard}
          players={tierPlayers.chips}
          prefillTier={prefillTierById}
          marketTier={marketTierById}
          offBoard={tierPlayers.offBoard}
          selected={tierSel}
          onToggle={onTierToggle}
          onMove={onTierMove}
          bottomInset={footerH}
          header={
            <View style={styles.tierHeader}>
              <CText style={styles.leagueName}>Step 2 of 2 · optional</CText>
              <CText style={styles.heading} accessibilityRole="header">Place your players</CText>
              <CText style={styles.lede}>
                Tap players, then a tier. Everyone starts where your board has them.
              </CText>
            </View>
          }
        />
        <View style={[styles.footer, styles.footerCol]} onLayout={onFooterLayout}>
          {tierError ? <CText style={styles.tierError}>{tierError}</CText> : null}
          {tierSel.length > 0 ? (
            <>
              <View style={styles.selRow}>
                <CText style={styles.selCount}>{`${tierSel.length} SELECTED`}</CText>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setTierSel([])}
                  hitSlop={8}
                  style={styles.textBtn}
                >
                  <CText style={styles.textBtnLabel}>Clear</CText>
                </Pressable>
              </View>
              <TierTargetChips
                accentFor={tierAccent}
                onPick={(t) => onTierMove(tierSel, t)}
                testIDPrefix="roster-setup.tiers.move"
              />
            </>
          ) : (
            <View style={styles.footerRow}>
              <Pressable
                testID="roster-setup.tiers.skip"
                accessibilityRole="button"
                onPress={onTierSkip}
                disabled={tierSaving}
                hitSlop={8}
                style={styles.textBtn}
              >
                <CText style={styles.textBtnLabel}>Skip</CText>
              </Pressable>
              {tierFailed.length > 0 ? (
                <Button
                  label="Retry"
                  testID="roster-setup.tiers.retry"
                  loading={tierSaving}
                  disabled={tierSaving}
                  onPress={() => void saveTierMoves(tierFailed)}
                  style={styles.primaryBtn}
                />
              ) : (
                <Button
                  label={dirty ? 'Save tiers' : 'Done'}
                  testID="roster-setup.tiers.save"
                  loading={tierSaving}
                  disabled={tierSaving}
                  onPress={() => void saveTierMoves()}
                  style={styles.primaryBtn}
                />
              )}
            </View>
          )}
        </View>
      </>
    );
  } else {
    const moves = assets.filter((a) => states[a.id] === 'move');
    const rankedPlayers = ranked.reduce((n, r) => n + r.count, 0);
    const changed = changedRef.current || anyChange();
    body = (
      <>
        <View style={styles.header}>
          {leagueName ? <Text style={styles.leagueName}>{leagueName}</Text> : null}
          <Text style={styles.heading} accessibilityRole="header">You&apos;re set</Text>
        </View>
        <ScrollView contentContainerStyle={styles.list}>
          {changed ? (
            <View style={styles.doneCard}>
              <Text style={styles.doneCounts}>
                {tierHome
                  ? `${counts.move} to move · ${counts.keep} to keep · ${reTiered} re-tiered`
                  : `${counts.move} to move · ${counts.keep} to keep · ${rankedPlayers} ranked`}
              </Text>
              {moves.slice(0, 3).map((a) => (
                <View key={a.id} style={styles.doneRow}>
                  <Text style={styles.doneName} numberOfLines={1}>{a.name}</Text>
                  <Text style={styles.doneTag}>MOVE</Text>
                </View>
              ))}
              {moves.length > 3 ? (
                <Text style={styles.doneMore}>{`+${moves.length - 3} more`}</Text>
              ) : null}
              <Text style={styles.doneNext}>Building trades from your roster.</Text>
            </View>
          ) : (
            <Text style={styles.lede}>Nothing changed. Your trades use consensus values.</Text>
          )}
          <Text style={styles.doneHint}>Change any of this later in Trade DNA › Your roster.</Text>
        </ScrollView>
        <View style={styles.footer} onLayout={onFooterLayout}>
          <Button
            label="See trades"
            testID="roster-setup.done.cta"
            loading={leaving && pendingWrites > 0}
            disabled={leaving}
            onPress={() => void onSeeTrades()}
            style={styles.primaryBtn}
          />
        </View>
      </>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="roster-setup.screen">
      {body}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    gap: space.xs,
  },
  leagueName: { ...type.label },
  heading: { ...type.heading },
  lede: { ...type.bodySm },
  counter: {
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    marginTop: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    gap: 2,
  },
  counterText: { ...type.data, color: chalk.base, letterSpacing: 0.5 },
  // Keep guard — `warn` is the semantic for a caution (mockup frame B);
  // informational only, never blocks Continue.
  guard: { ...type.bodySm, color: semantic.warn },
  writeError: { ...type.bodySm, color: semantic.neg, paddingHorizontal: space.lg },
  list: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: 120, // room for the pinned footer
    gap: space.md,
  },
  section: { gap: space.xs },
  sectionHdr: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginBottom: 2,
  },
  sectionBar: { width: 3, height: 14, borderRadius: radii.xs },
  sectionLabel: { ...type.label, color: chalk.base },
  sectionCount: { ...type.label, fontFamily: fonts.data },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 48,
    paddingVertical: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowMain: { flex: 1, minWidth: 0 },
  rowGreyed: { opacity: 0.5 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  tierDot: { width: 8, height: 8, borderRadius: radii.xs },
  rowName: { ...type.body, fontFamily: fonts.uiSemi, flexShrink: 1 },
  rowMeta: { ...type.bodySm, fontSize: 11, lineHeight: 14 },
  toggle: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  seg: {
    minWidth: 52,
    minHeight: 36,
    paddingHorizontal: space.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  segDivider: { borderLeftWidth: 1, borderLeftColor: ink.line },
  // Neutral fill for the selected segment (prd §4.2): ink-3 well + chalk
  // label + glyph. No red/green — Chalkline reserves ice for actions.
  segSelected: { backgroundColor: ink.ink3 },
  segText: { fontFamily: fonts.uiSemi, fontSize: 12 },
  segTextSel: { fontFamily: fonts.uiBold },
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
  primaryBtn: { flex: 1 },
  footerCol: { flexDirection: 'column', alignItems: 'stretch', gap: space.xs },
  footerRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  tierHeader: { gap: space.xs, paddingTop: space.sm, paddingBottom: space.xs },
  tierError: { ...type.bodySm, color: semantic.neg },
  selRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  selCount: { ...type.label, fontFamily: fonts.data },
  textBtn: { paddingHorizontal: space.md, paddingVertical: 10 },
  textBtnLabel: { ...type.bodySm, color: chalk.dim },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.xl,
  },
  errorText: { ...type.body, color: chalk.dim, textAlign: 'center' },
  posRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  posTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    minHeight: 40,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  posTabActive: { backgroundColor: ink.ink3 },
  posTabText: { ...type.label },
  posTabTextActive: { color: chalk.base },
  tapCount: {
    ...type.label,
    fontFamily: fonts.data,
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.sm,
  },
  doneCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.md,
    gap: space.sm,
  },
  doneCounts: { ...type.data, color: chalk.base },
  doneRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  doneName: { ...type.body, flexShrink: 1 },
  doneTag: { ...type.label, fontFamily: fonts.data, color: chalk.dim },
  doneMore: { ...type.bodySm },
  doneNext: { ...type.bodySm, color: chalk.base },
  doneHint: { ...type.bodySm, marginTop: space.sm },
});
