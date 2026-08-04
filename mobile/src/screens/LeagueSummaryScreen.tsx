import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
  position as positionColors,
} from '../theme/chalkline';
import { Badge, Icon, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import PlayerCard from '../components/PlayerCard';
import {
  getPowerRankings,
  getOutlook,
  type PowerRankedPlayer,
  type PowerRankedTeam,
  type LeagueOutlookResponse,
  type OutlookTeam,
  type OutlookMeta,
} from '../api/league';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { relativeTime } from '../utils/relativeTime';
import { registerScrollToTop } from '../navigation/scrollToTop';

// League rankings ("power rankings", #142/#144/#169) — every team in the league
// as a stacked bar in a value-ranked chart, from GET /api/league/power-rankings.
//
// League Analyzer replication (2026-07-26, DynastyGM teardown
// docs/business/product/2026-07-26-dynastygm-app-teardown.md): the chart is now
// a VERTICAL stacked-bar chart — x-axis = rank 1..N (numerals under each bar,
// the caller's numeral in an ice pill), bars position-stacked in the position
// hexes, tallest = rank 1 at the left, scaled to the league max. Below it the
// ranked team list rows (rank numeral, name, value, chevron; caller's row
// highlighted).
//   - Position filter (single OR multi, "All" default): on change the bars
//     RE-VALUE to the selected position(s) only and RE-SORT teams — a pure
//     client-side transform over per-position values (no refetch). Restyled
//     to colored outline pills, selected = solid fill.
//   - All · Starters · Bench segmented control (2026-07-26): "Starters" is
//     the DERIVED value-optimal lineup the server computes per team
//     (payload `teams[].starters` — the league's slot template filled with
//     each team's highest-value eligible players; NO per-week lineup data),
//     "Bench" is the rest. Selecting either recomputes EVERY team's
//     per-position values from that subset and re-ranks the whole league;
//     the drill-in filters to the same subset. Rendered ONLY when the
//     payload says `starters_available` (honest degradation — platforms
//     without a slot template hide the control entirely).
//   - Basis toggle: Consensus (universal-pool values) | My board (the caller's
//     own values, consensus fallback for unranked players). Redraft is a
//     disabled "(soon)" chip — the backend reserves basis=redraft but answers
//     501 not_available. The derived starters split is basis-aware (the
//     server computes it from the same values it ranks with).
//   - Drill-in focus (2026-07-26): tapping a team (bar or row) keeps ITS bar
//     in full position colors and switches every other bar to muted-gray
//     segments; the card caption swaps to the team name + "League rank: N/M";
//     the roster panel renders inline below the chart with per-position group
//   - #237 mirrored filters (2026-08-02): the drill-in roster panel renders
//     the SAME filter button set as the chart card — the All/Starters/Bench
//     segmented control plus the position pills — and both sections share ONE
//     state (`subset` + `posFilter`); changing a filter in either place
//     updates both instantly. The panel's formerly-independent `drillPos`
//     filter is gone.
//   - #243 drill-in filter dedup, V1 (2026-08-03, approved mock
//     mockups/polish-lab-2026-08/drilldown-filter-dedup.html): WHILE A TEAM
//     IS FOCUSED the chart card collapses to a slim strip — the card's own
//     SubsetControl/PosFilterPills do NOT mount (a passive "Filtered by: …"
//     caption, testID league-summary.filter-caption, takes their place), the
//     X close control becomes a "‹ All teams" back affordance (keeps testID
//     league-summary.roster-close; inner label league-summary.back-all-teams),
//     the hint line tightens, and the tab-root "League home" row hides. The
//     drill panel's mirrored controls become the single visible set. This is
//     VISIBILITY ONLY: the #237 shared `subset`/`posFilter` state model and
//     the unfocused rendering (both control sets, home row, X-restores) are
//     untouched — unfocusing restores today's layout exactly.
//     headers "(count) · positional total · rank/M" (rank chip color-coded by
//     league tercile: top third pos-green, middle warn-amber, bottom
//     neg-red) and per-player positional value ranks ("RB2", "NR" for zero
//     value). X (testID league-summary.roster-close, unchanged) restores.
//
// #181 — this screen serves TWO routes:
//   • 'LeagueRankings' — the League TAB's root (TabNav's LeagueStack): the
//     primary page the tab lands on. Adds a "League home" entry row (the
//     classic league page, pushed as 'LeagueHome') and registers the
//     focused-re-tap scroll-to-top handler for the League tab.
//   • 'LeagueSummary' — the legacy ROOT-stack push (RootNav), kept for old
//     entry points (deep link app/league/summary, stored whats-new routes).
//     No home row, no re-tap registration (it isn't the tab root).
//
// #169 OUTLOOK ODDS layer (flag `outlook.odds`, DARK): the playoff/title-odds
// view lives between the basis toggle and the dynasty chart. It is a SEPARATE
// gated section — when `outlook.odds` is off (the default; the flag is absent
// from LAUNCHED_FLAG_DEFAULTS) the section does NOT render and GET
// /api/league/outlook is NOT called (it 404s while the modeling backend is
// dark). Only when on do we fetch + render. Every odds figure is a projection:
// the section carries a "Projected · preseason · beta" ribbon + a strength-
// source caption so no percentage ever reads as authoritative (see
// mockups/outlook-odds/outlook-card.html — the amber "Season outlook" block).
// The basis toggle governs BOTH the odds fetch and the dynasty chart.

type UiBasis = 'consensus' | 'personal';
type CorePos = 'QB' | 'RB' | 'WR' | 'TE';
// #14 FR1 — the filterable chart keys: the four positions plus the
// draft-capital group ("Picks"). Picks isn't a position, so it renders in a
// neutral ink tone, never a position hex (cross-client-invariants). Picks are
// neither starters nor bench, so the Picks key only exists in the All subset.
type FilterKey = CorePos | 'PICKS';
// 2026-07-26 — league-wide roster subset. 'starters' = the derived
// value-optimal lineup (payload teams[].starters); 'bench' = everything else.
// ("Optimal" as a separate mode is deliberately NOT built — Starters IS the
// optimal lineup by construction.)
type Subset = 'all' | 'starters' | 'bench';

const CORE_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const satisfies readonly CorePos[];
const PICKS_COLOR = chalk.faint;
const SUBSETS: ReadonlyArray<{ key: Subset; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'starters', label: 'Starters' },
  { key: 'bench', label: 'Bench' },
];
const CHART_HEIGHT = 160;

// Drill-in focus (2026-07-26): every non-selected bar renders its segments in
// muted grays — existing ink/chalk tokens only (design-system rule: no new
// hues), one distinct step per position so segments stay distinguishable.
const GRAY_SEGMENT: Record<FilterKey, string> = {
  QB: chalk.dim,
  RB: ink.lineStrong,
  WR: chalk.faint,
  TE: ink.line,
  PICKS: ink.ink3,
};

// Scoring-format key → the caption label ("Dynasty · SF TEP"). Unknown keys
// degrade to the raw key uppercased rather than fabricating a format.
const FORMAT_LABELS: Record<string, string> = {
  '1qb_ppr': '1QB PPR',
  sf_tep: 'SF TEP',
};

// Compact 0–10k value for chart bar labels + the per-group mini-summary.
function fmtK(v: number): string {
  if (v >= 1000) return `${(Math.round(v / 100) / 10).toFixed(1)}k`;
  return String(Math.round(v));
}

function posColor(pos: string): string {
  return positionColors[pos.toLowerCase() as keyof typeof positionColors] ?? chalk.dim;
}

// League-tercile color for in-league positional rank chips (2026-07-26):
// top third = pos green, middle third = warn amber, bottom third = neg red.
// Chalkline semantic tokens only — the position hex stays on the position
// label; the tercile color applies to the RANK chip.
function tercileColor(rank: number, total: number): string {
  if (total <= 0 || rank <= 0) return chalk.dim;
  const t = rank / total;
  if (t <= 1 / 3) return semantic.pos;
  if (t <= 2 / 3) return semantic.warn;
  return semantic.neg;
}

// Per-team stats under the active subset. For 'all' the server's authoritative
// per-position summary is used; for starters/bench the values are recomputed
// from the roster rows in (or out of) the derived starters set.
interface TeamComputed {
  team: PowerRankedTeam;
  /** Roster rows in the active subset (drives the drill-in + player ranks). */
  rows: PowerRankedPlayer[];
  posValues: Record<CorePos, number>;
  /** Core-position value sum under the subset (players only, no picks). */
  coreTotal: number;
}

function computeSubset(team: PowerRankedTeam, subset: Subset): TeamComputed {
  const starterSet = new Set(team.starters ?? []);
  const rows =
    subset === 'all'
      ? team.roster
      : team.roster.filter(
          (r) => starterSet.has(r.player_id) === (subset === 'starters'),
        );
  const posValues: Record<CorePos, number> = { QB: 0, RB: 0, WR: 0, TE: 0 };
  if (subset === 'all') {
    for (const p of CORE_POSITIONS) {
      posValues[p] = team.positions?.[p]?.value ?? 0;
    }
  } else {
    for (const r of rows) {
      if ((CORE_POSITIONS as readonly string[]).includes(r.position)) {
        posValues[r.position as CorePos] += r.value;
      }
    }
  }
  const coreTotal = CORE_POSITIONS.reduce((s, p) => s + posValues[p], 0);
  return { team, rows, posValues, coreTotal };
}

// The value a team contributes under the active subset + position filter.
// All-subset with no filter = the team's authoritative total (matches the
// backend rank; includes draft capital). Starters/bench = the recomputed
// core-position sum (picks are neither starters nor bench). A non-empty
// filter = the summed value of the selected groups.
function activeTotal(tc: TeamComputed, subset: Subset, filter: Set<FilterKey>): number {
  if (filter.size === 0) {
    return subset === 'all' ? tc.team.total_value : tc.coreTotal;
  }
  let sum = 0;
  filter.forEach((p) => {
    if (p === 'PICKS') sum += subset === 'all' ? tc.team.picks?.value ?? 0 : 0;
    else sum += tc.posValues[p];
  });
  return sum;
}

export default function LeagueSummaryScreen() {
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  // #181 — which of the two registrations is rendering (see header comment).
  const navigation = useNavigation<any>();
  const route = useRoute();
  const isTabRoot = route.name === 'LeagueRankings';
  // S1 PRD-05 (flag ux.retap_active_tab) — as the League tab's root, this
  // screen owns the tab's focused-re-tap scroll-to-top handler (moved here
  // from LeagueScreen with #181). The root-stack variant must NOT register:
  // it would clobber the tab root's handler while both are mounted.
  const retapOn = useFlag('ux.retap_active_tab');
  const scrollRef = useRef<ScrollView>(null);
  useEffect(
    () =>
      isTabRoot && retapOn
        ? registerScrollToTop('League', () =>
            scrollRef.current?.scrollTo({ y: 0, animated: true }),
          )
        : undefined,
    [isTabRoot, retapOn],
  );
  const [basis, setBasis] = useState<UiBasis>('consensus');
  // Empty set = "All" (unfiltered). Non-empty = single/multi position select.
  const [posFilter, setPosFilter] = useState<Set<FilterKey>>(new Set());
  // 2026-07-26 — league-wide All/Starters/Bench subset.
  const [subset, setSubset] = useState<Subset>('all');
  // Store the selected team's id (not the object) so a basis switch while
  // the drill-in is open re-derives the team from fresh data.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // #237 — the drill-in roster panel shares `subset` + `posFilter` with the
  // chart card (one state, two mirrored button sets). No separate drill
  // filter.

  const query = useQuery({
    queryKey: ['league-power-rankings', leagueId, basis],
    queryFn: () => getPowerRankings(leagueId!, basis),
    enabled: !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // #169 outlook odds — DARK behind `outlook.odds`. `enabled` is false unless
  // the flag is on AND a league is selected, so GET /api/league/outlook never
  // fires while the layer is dark (the endpoint 404s). Shares the `basis` state
  // with the dynasty chart. Off by default: the flag is absent from
  // LAUNCHED_FLAG_DEFAULTS, so `useFlag` returns false until a live map turns
  // it on.
  const oddsEnabled = useFlag('outlook.odds');
  const outlookQuery = useQuery({
    queryKey: ['league-outlook', leagueId, basis],
    queryFn: () => getOutlook(leagueId!, basis),
    enabled: oddsEnabled && !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const teams = query.data?.teams ?? [];
  // 2026-07-26 — the All/Starters/Bench control renders only when the server
  // says the derived split exists for every team (starters_available). Old
  // servers omit the field → false → All-only (today's behavior). Belt and
  // braces: also require the per-team lists to actually be present.
  const startersAvailable =
    query.data?.starters_available === true &&
    teams.length > 0 &&
    teams.every((t) => Array.isArray(t.starters));
  // If the split disappears (league switch, basis refetch against an older
  // server), fall back to All rather than render fabricated subsets.
  useEffect(() => {
    if (!startersAvailable && subset !== 'all') setSubset('all');
  }, [startersAvailable, subset]);

  // Picks pill/segments only when the league actually carries draft capital
  // (ESPN + demo leagues report zero; old servers omit the field entirely)
  // AND the All subset is active (picks are neither starters nor bench).
  const hasPicks = teams.some((t) => (t.picks?.value ?? 0) > 0);
  const showPicksKey = hasPicks && subset === 'all';

  // Per-team subset stats, recomputed when the subset changes.
  const computed = useMemo(
    () => teams.map((t) => computeSubset(t, subset)),
    [teams, subset],
  );

  // Client-side re-value + re-sort for the active subset + position filter.
  // Teams tie-break on user_id asc so the order is deterministic (mirrors the
  // backend).
  const ranked = useMemo(() => {
    const rows = computed.map((tc) => ({
      tc,
      active: activeTotal(tc, subset, posFilter),
    }));
    rows.sort(
      (a, b) =>
        b.active - a.active || (a.tc.team.user_id < b.tc.team.user_id ? -1 : 1),
    );
    return rows;
  }, [computed, subset, posFilter]);

  const maxActive = useMemo(
    () => Math.max(1, ...ranked.map((r) => r.active)),
    [ranked],
  );

  // League-average line (2026-07-26 amendment): the mean of EXACTLY the
  // values the bars are showing — position pills × subset × basis all
  // applied (no filter = full-roster average including picks). Recomputes
  // with every filter change because `ranked` does.
  const avgActive = useMemo(
    () =>
      ranked.length > 0
        ? ranked.reduce((s, r) => s + r.active, 0) / ranked.length
        : 0,
    [ranked],
  );

  // In-league positional rank per team (drill-in group headers, 2026-07-26):
  // rank of this team's position-group value among all teams', under the
  // active subset. 1 + count of strictly greater values (ties share a rank).
  const teamPosRank = useMemo(() => {
    const out = {} as Record<CorePos, Map<string, number>>;
    for (const p of CORE_POSITIONS) {
      const m = new Map<string, number>();
      for (const tc of computed) {
        const mine = tc.posValues[p];
        let greater = 0;
        for (const other of computed) if (other.posValues[p] > mine) greater += 1;
        m.set(tc.team.user_id, greater + 1);
      }
      out[p] = m;
    }
    return out;
  }, [computed]);

  // Per-player positional value rank league-wide under the active subset
  // ("RB2"; zero-value → no entry → rendered "NR"). Computed from the roster
  // rows the payload already carries for every team.
  const playerPosRank = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of CORE_POSITIONS) {
      const rows: PowerRankedPlayer[] = [];
      for (const tc of computed) {
        for (const r of tc.rows) if (r.position === p && r.value > 0) rows.push(r);
      }
      rows.sort(
        (a, b) => b.value - a.value || (a.player_id < b.player_id ? -1 : 1),
      );
      rows.forEach((r, i) => m.set(r.player_id, `${p}${i + 1}`));
    }
    return m;
  }, [computed]);

  const selectedIdx = selectedId
    ? ranked.findIndex((r) => r.tc.team.user_id === selectedId)
    : -1;
  const selected = selectedIdx >= 0 ? ranked[selectedIdx] : null;

  const togglePos = (setter: React.Dispatch<React.SetStateAction<Set<FilterKey>>>) =>
    (pos: FilterKey | 'ALL') => {
      setter((prev) => {
        if (pos === 'ALL') return new Set();
        const next = new Set(prev);
        if (next.has(pos)) next.delete(pos);
        else next.add(pos);
        return next;
      });
    };

  // Switching off All drops the Picks key from the shared filter — picks are
  // neither starters nor bench, so a stale PICKS selection would zero bars.
  const switchSubset = (s: Subset) => {
    setSubset(s);
    if (s !== 'all') {
      setPosFilter((prev) => {
        if (!prev.has('PICKS')) return prev;
        const next = new Set(prev);
        next.delete('PICKS');
        return next;
      });
    }
  };

  const fmtKey = query.data?.scoring_format ?? '';
  const formatCaption = `Dynasty · ${FORMAT_LABELS[fmtKey] ?? fmtKey.toUpperCase()}`;

  // #243 — passive filter caption for the focused-state slim strip:
  // "All" / "Starters · WR" / "All · WR + TE + Picks". Positions read in the
  // canonical QB→RB→WR→TE order (#195), Picks last.
  const subsetLabel = SUBSETS.find((s) => s.key === subset)?.label ?? 'All';
  const filterPosLabel = [
    ...CORE_POSITIONS.filter((p) => posFilter.has(p)),
    ...(posFilter.has('PICKS') ? ['Picks'] : []),
  ].join(' + ');
  const filterCaptionLabel = filterPosLabel
    ? `${subsetLabel} · ${filterPosLabel}`
    : subsetLabel;

  if (!leagueId) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <View style={styles.center}>
          <Text style={type.heading}>No league selected</Text>
          <Text style={[type.bodySm, styles.centerBody]}>
            Pick a league from the league switcher to see its rankings.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={query.isFetching && !!query.data}
            onRefresh={() => query.refetch()}
            tintColor={ice.base}
          />
        }
      >
        {/* #181 — the classic league page's entry point, tab-root variant
            only (the root-stack push still exits via its back control).
            LeagueRow construction: hairline list row, title + body-sm
            chalk-dim meta + chevron. #243 — hidden while a team is focused
            (a nav-away affordance is irrelevant mid roster review); returns
            the moment focus clears. */}
        {isTabRoot && !selected ? (
          <Pressable
            testID="league-summary.league-home"
            onPress={() => navigation.navigate('LeagueHome')}
            accessibilityRole="button"
            accessibilityLabel="League home"
            style={({ pressed }) => [styles.homeRow, pressed && { backgroundColor: ink.ink3 }]}
          >
            <View style={styles.homeMain}>
              <Text style={type.title}>League home</Text>
              <Text style={[type.bodySm, styles.homeSub]}>
                Matches, members, coverage, leaderboards & league tools
              </Text>
            </View>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ) : null}

        {/* Basis toggle — subnav-pill construction (hairline chip, active =
            ink-3 well + line-strong border). Redraft is informational-only:
            disabled with a "(soon)" suffix until a redraft value source
            exists (backend answers 501 not_available). */}
        <View style={styles.basisRow}>
          <BasisChip
            testID="league-summary.basis.consensus"
            label="Consensus"
            active={basis === 'consensus'}
            onPress={() => setBasis('consensus')}
          />
          <BasisChip
            testID="league-summary.basis.personal"
            label="My board"
            active={basis === 'personal'}
            onPress={() => setBasis('personal')}
          />
          <BasisChip
            testID="league-summary.basis.redraft"
            label="Redraft (soon)"
            active={false}
            disabled
          />
        </View>

        {/* #169 outlook-odds layer — gated on `outlook.odds` (dark). Rendered
            only when the flag is on; the fetch is likewise gated so nothing
            fires while dark. Basis-driven (shares the toggle above). */}
        {oddsEnabled ? <OddsSection query={outlookQuery} /> : null}

        {/* ── Chart card (2026-07-26 League Analyzer treatment) ─────────── */}
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <View style={styles.cardHeadMain}>
              {selected ? (
                <>
                  <Text style={type.title} numberOfLines={1}>
                    {selected.tc.team.display_name ||
                      selected.tc.team.username ||
                      selected.tc.team.user_id}
                  </Text>
                  <Text
                    style={[type.bodySm, styles.cardCaption]}
                    testID="league-summary.focus-caption"
                  >
                    {`League rank: ${selectedIdx + 1}/${ranked.length}`}
                  </Text>
                </>
              ) : (
                <>
                  <Text style={type.title} numberOfLines={1}>
                    {league?.league_name || 'League'}
                  </Text>
                  <Text style={[type.bodySm, styles.cardCaption]}>{formatCaption}</Text>
                </>
              )}
            </View>
            {selected ? (
              /* #243 slim strip — the close control is a "‹ All teams" back
                 affordance (approved mock, V1 frame). Same function as the
                 old X, so it KEEPS testID league-summary.roster-close; the
                 label carries the new back-affordance id. */
              <Pressable
                testID="league-summary.roster-close"
                onPress={() => setSelectedId(null)}
                hitSlop={12}
                accessibilityRole="button"
                accessibilityLabel="Back to all teams"
                style={({ pressed }) => [styles.backLink, pressed && { opacity: 0.6 }]}
              >
                <Icon name="chevron-left" size={14} color={ice.base} />
                <Text testID="league-summary.back-all-teams" style={styles.backLinkText}>
                  All teams
                </Text>
              </Pressable>
            ) : (
              <Pressable
                testID="league-summary.refresh"
                onPress={() => query.refetch()}
                hitSlop={12}
                accessibilityRole="button"
                accessibilityLabel="Refresh league rankings"
                style={({ pressed }) => [styles.headBtn, pressed && styles.headBtnPressed]}
              >
                <Icon name="swap" size={18} color={chalk.dim} />
              </Pressable>
            )}
          </View>

          {/* #14 FR6 — compute freshness + the pull-to-refresh above. */}
          {query.data?.updated_at ? (
            <Text testID="league-summary.updated-at" style={[type.data, styles.updatedAt]}>
              {`Updated ${relativeTime(query.data.updated_at)} · pull to refresh`}
            </Text>
          ) : null}

          {/* 2026-07-26 — league-wide subset. Hidden entirely when the server
              can't derive the split (never fabricate). #237 — the same
              control (same shared state) also renders in the drill-in
              roster panel below. #243 — while a team is focused the card's
              copy does NOT mount (the drill panel's copy is the single
              visible set; shared state untouched). */}
          {startersAvailable && !selected ? (
            <SubsetControl
              idPrefix="league-summary.subset"
              subset={subset}
              onSwitch={switchSubset}
            />
          ) : null}

          {/* Position filter — single or multi select; "All" clears. Reorders
              + rescales the chart live over the already-returned per-position
              values (no refetch). #243 — hidden while focused, same dedup as
              the subset control above. */}
          {!selected ? (
            <PosFilterPills
              idPrefix="league-summary.posfilter"
              filter={posFilter}
              onToggle={togglePos(setPosFilter)}
              showPicks={showPicksKey}
            />
          ) : (
            /* #243 slim strip — passive caption of the active filter in place
               of the card's interactive controls. */
            <View style={styles.filterCaption} testID="league-summary.filter-caption">
              <Text style={[type.bodySm, styles.filterCaptionText]}>
                {'Filtered by: '}
                <Text style={styles.filterCaptionValue}>{filterCaptionLabel}</Text>
                {' — change filters below'}
              </Text>
            </View>
          )}
          <Text style={[type.bodySm, styles.hint, selected ? styles.hintTight : null]}>
            {`${subset === 'starters' ? 'Best starting lineup only. ' : subset === 'bench' ? 'Bench only. ' : ''}${
              posFilter.size === 0
                ? basis === 'consensus'
                  ? 'Ranked by roster value on community consensus.'
                  : 'Ranked by roster value on YOUR board — unranked players use consensus.'
                : `Ranked by ${[...posFilter].join(' + ')} value only — chart reordered.`
            }`}
          </Text>

          {query.isLoading ? (
            <View style={styles.center}>
              <ActivityIndicator color={ice.base} />
            </View>
          ) : query.isError ? (
            <View style={styles.center}>
              <Text style={[type.bodySm, styles.centerBody]}>
                {(query.error as any)?.message === 'verification_required'
                  ? 'Verify your account to view your data.'
                  : (query.error as any)?.message || 'Couldn’t load league rankings — pull to retry.'}
              </Text>
            </View>
          ) : ranked.length === 0 ? (
            <View style={styles.center}>
              <Text style={[type.bodySm, styles.centerBody]}>
                No teams to rank yet.
              </Text>
            </View>
          ) : (
            <>
              <View style={styles.chartWrap}>
                <View style={styles.chartRow}>
                  {ranked.map((r, idx) => (
                    <BarColumn
                      key={r.tc.team.user_id}
                      tc={r.tc}
                      rank={idx + 1}
                      active={r.active}
                      maxActive={maxActive}
                      subset={subset}
                      filter={posFilter}
                      focused={selectedId === r.tc.team.user_id}
                      grayed={!!selectedId && selectedId !== r.tc.team.user_id}
                      onPress={() => setSelectedId(r.tc.team.user_id)}
                    />
                  ))}
                </View>
                {/* League-average line — dashed chalk-dim hairline at the
                    mean of the currently shown bar values (filters + subset
                    + basis applied). pointerEvents none so bar taps pass
                    through; label clamped inside the chart area. Hidden
                    when the view sums to zero. */}
                {avgActive > 0
                  ? (() => {
                      const topPx = Math.min(
                        Math.max(CHART_HEIGHT * (1 - avgActive / maxActive), 15),
                        CHART_HEIGHT - 2,
                      );
                      return (
                        <View
                          testID="league-summary.avg-line"
                          pointerEvents="none"
                          accessible
                          accessibilityLabel={`League average ${Math.round(avgActive).toLocaleString('en-US')} in this view`}
                          style={styles.avgOverlay}
                        >
                          <View style={[styles.avgLine, { top: topPx }]} />
                          <Text style={[styles.avgLabel, { top: topPx - 15 }]}>
                            {`Avg ${fmtK(avgActive)}`}
                          </Text>
                        </View>
                      );
                    })()
                  : null}
              </View>
              {/* Position legend — the stack encoding. */}
              <View style={styles.legend}>
                {CORE_POSITIONS.map((p) => (
                  <View key={p} style={styles.legendItem}>
                    <View style={[styles.legendSwatch, { backgroundColor: posColor(p) }]} />
                    <Text style={styles.legendLabel}>{p}</Text>
                  </View>
                ))}
                {showPicksKey ? (
                  <View style={styles.legendItem}>
                    <View style={[styles.legendSwatch, { backgroundColor: PICKS_COLOR }]} />
                    <Text style={styles.legendLabel}>Picks</Text>
                  </View>
                ) : null}
              </View>
            </>
          )}
        </View>

        {/* Below the chart: either the ranked team list, or — with a team
            focused — the drill-in roster panel (#144/#169, inline since the
            2026-07-26 League Analyzer treatment so the grayscale chart stays
            visible above it). */}
        {selected ? (
          <View style={styles.drillPanel}>
            <Text style={[type.data, styles.drillSub]}>
              {`#${selectedIdx + 1} of ${ranked.length} · ${
                selected.active > 0
                  ? Math.round(selected.active).toLocaleString('en-US')
                  : '—'
              }${subset === 'all' ? '' : subset === 'starters' ? ' starter' : ' bench'} value`}
            </Text>
            {/* #237 — mirrored filter set: the SAME subset control + position
                pills as the chart card, bound to the SAME state, so the two
                sections can never disagree. */}
            {startersAvailable ? (
              <SubsetControl
                idPrefix="league-summary.roster-subset"
                subset={subset}
                onSwitch={switchSubset}
              />
            ) : null}
            <PosFilterPills
              idPrefix="league-summary.roster-posfilter"
              filter={posFilter}
              onToggle={togglePos(setPosFilter)}
              style={styles.drillFilter}
              showPicks={showPicksKey}
            />
            <View style={styles.drillList}>
              {groupRows(selected.tc.rows, posFilter).map((g) => {
                const isCore = (CORE_POSITIONS as readonly string[]).includes(g.pos);
                const rank = isCore
                  ? teamPosRank[g.pos as CorePos].get(selected.tc.team.user_id) ?? 0
                  : 0;
                return (
                  <View key={g.pos}>
                    <View style={styles.groupHead}>
                      <Text style={[styles.groupLabel, { color: posColor(g.pos) }]}>
                        {g.pos}
                      </Text>
                      <View style={styles.groupMetaRow}>
                        <Text style={[type.data, styles.groupMeta]}>
                          {`${g.rows.length} · ${fmtK(g.value)}`}
                        </Text>
                        {isCore && rank > 0 ? (
                          <View
                            style={[styles.rankChip, { borderColor: tercileColor(rank, ranked.length) }]}
                            accessibilityRole="text"
                            accessibilityLabel={`${g.pos} ranked ${rank} of ${ranked.length}`}
                          >
                            <Text
                              style={[styles.rankChipText, { color: tercileColor(rank, ranked.length) }]}
                            >
                              {`${rank}/${ranked.length}`}
                            </Text>
                          </View>
                        ) : null}
                      </View>
                    </View>
                    {g.rows.map((r) => (
                      <View key={r.player_id} style={styles.rosterRow}>
                        <PlayerCard
                          dense
                          player={{
                            id: r.player_id,
                            name: r.name,
                            position: r.position,
                            team: r.team,
                            age: r.age,
                          }}
                          value={Math.round(r.value)}
                          posRank={playerPosRank.get(r.player_id) ?? 'NR'}
                        />
                      </View>
                    ))}
                  </View>
                );
              })}
              {/* #14 FR1 — draft capital: the team's owned picks, priced on
                  the generic ladder. All subset only (picks are neither
                  starters nor bench); hidden for leagues without pick data. */}
              {subset === 'all' &&
              (posFilter.size === 0 || posFilter.has('PICKS')) &&
              (selected.tc.team.picks?.items?.length ?? 0) > 0 ? (
                <View testID="league-summary.roster-picks">
                  <View style={styles.groupHead}>
                    <Text style={[styles.groupLabel, { color: PICKS_COLOR }]}>
                      Draft capital
                    </Text>
                    <Text style={[type.data, styles.groupMeta]}>
                      {`${selected.tc.team.picks!.count} · ${fmtK(selected.tc.team.picks!.value)}`}
                    </Text>
                  </View>
                  {selected.tc.team.picks!.items.map((p, i) => (
                    <View key={`${p.label}-${i}`} style={styles.pickRow}>
                      <Text style={type.title} numberOfLines={1}>{p.label}</Text>
                      <Text style={type.data}>{Math.round(p.value).toLocaleString('en-US')}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          </View>
        ) : (
          <View style={styles.list}>
            {ranked.map((r, idx) => (
              <TeamRow
                key={r.tc.team.user_id}
                team={r.tc.team}
                rank={idx + 1}
                active={r.active}
                onPress={() => setSelectedId(r.tc.team.user_id)}
              />
            ))}
          </View>
        )}
      </ScrollView>
      {/* #188 — the root-stack push variant covers RootNav's FAB mount, so
          it carries its own (no tab bar underneath). The tab-root variant
          (LeagueRankings) is already covered by the RootNav mount — a second
          FAB there would double up. */}
      {!isTabRoot ? (
        <FeedbackFAB activeScreen="LeagueSummary" aboveTabBar={false} />
      ) : null}
    </SafeAreaView>
  );
}

// Bucket subset roster rows (already server-ordered) into position sections
// for the drill-in headers. Rows keep their value-desc order within each
// group. A non-empty `filter` limits the sections to the selected core
// positions (the "Other" bucket only ever appears in the unfiltered view;
// the PICKS key is not a roster section — draft capital renders separately).
function groupRows(
  rows: PowerRankedPlayer[],
  filter: Set<FilterKey>,
): Array<{ pos: string; rows: PowerRankedPlayer[]; value: number }> {
  const buckets = new Map<string, PowerRankedPlayer[]>();
  for (const r of rows) {
    const key = (CORE_POSITIONS as readonly string[]).includes(r.position) ? r.position : 'Other';
    const arr = buckets.get(key);
    if (arr) arr.push(r);
    else buckets.set(key, [r]);
  }
  // #195 — filtered sections keep the canonical QB→RB→WR→TE order (the Set's
  // insertion order is toggle order), matching the pills and the bar stack.
  const selected = CORE_POSITIONS.filter((k) => filter.has(k));
  const order: string[] =
    filter.size > 0 ? selected : [...CORE_POSITIONS, 'Other'];
  return order
    .filter((k) => buckets.has(k))
    .map((k) => ({
      pos: k,
      rows: buckets.get(k)!,
      value: buckets.get(k)!.reduce((s, r) => s + r.value, 0),
    }));
}

function BasisChip({ label, active, onPress, disabled, testID }: {
  label: string;
  active: boolean;
  onPress?: () => void;
  disabled?: boolean;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ selected: active, disabled: !!disabled }}
      style={({ pressed }) => [
        styles.basisChip,
        active && styles.basisChipActive,
        pressed && !disabled && { backgroundColor: ink.ink3 },
        disabled && styles.basisChipDisabled,
      ]}
    >
      <Text style={[type.label, active ? styles.basisChipTextActive : null]}>{label}</Text>
    </Pressable>
  );
}

// #237 — the All/Starters/Bench segmented control, rendered by BOTH the
// chart card (idPrefix league-summary.subset) and the drill-in roster panel
// (idPrefix league-summary.roster-subset). One shared `subset` state drives
// both instances, so they always match.
function SubsetControl({ idPrefix, subset, onSwitch }: {
  idPrefix: string;
  subset: Subset;
  onSwitch: (s: Subset) => void;
}) {
  return (
    <View
      style={styles.subsetRow}
      accessibilityRole="tablist"
      accessibilityLabel="Roster subset filter"
    >
      {SUBSETS.map((s) => {
        const on = subset === s.key;
        return (
          <Pressable
            key={s.key}
            testID={`${idPrefix}.${s.key}`}
            onPress={() => onSwitch(s.key)}
            accessibilityRole="button"
            accessibilityLabel={`Show ${s.label.toLowerCase()} value`}
            accessibilityState={{ selected: on }}
            style={[styles.subsetSeg, on && styles.subsetSegOn]}
          >
            <Text style={[styles.subsetSegText, on && styles.subsetSegTextOn]}>
              {s.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// Shared filter pill row (chart + drill-in). "All" pill clears the set; each
// position pill is a colored OUTLINE pill whose selected state is a SOLID
// fill in the position hex (2026-07-26 restyle — label text carries the
// encoding alongside color, per the a11y floor). The neutral "Picks" pill
// (#14 FR1) appears only when the league actually has draft capital and the
// All subset is active. Multi-select.
function PosFilterPills({ idPrefix, filter, onToggle, style, showPicks }: {
  idPrefix: string;
  filter: Set<FilterKey>;
  onToggle: (pos: FilterKey | 'ALL') => void;
  style?: any;
  showPicks?: boolean;
}) {
  const allOn = filter.size === 0;
  return (
    <View style={[styles.posFilter, style]}>
      <Pressable
        testID={`${idPrefix}.all`}
        onPress={() => onToggle('ALL')}
        accessibilityRole="button"
        accessibilityState={{ selected: allOn }}
        style={[styles.pill, { borderColor: ice.base }, allOn && { backgroundColor: ice.base }]}
      >
        <Text style={[styles.pillText, { color: allOn ? ice.on : ice.base }]}>All</Text>
      </Pressable>
      {CORE_POSITIONS.map((p) => {
        const on = filter.has(p);
        return (
          <Pressable
            key={p}
            testID={`${idPrefix}.${p.toLowerCase()}`}
            onPress={() => onToggle(p)}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            style={[styles.pill, { borderColor: posColor(p) }, on && { backgroundColor: posColor(p) }]}
          >
            <Text style={[styles.pillText, { color: on ? ink.ink0 : posColor(p) }]}>{p}</Text>
          </Pressable>
        );
      })}
      {showPicks ? (
        <Pressable
          testID={`${idPrefix}.picks`}
          onPress={() => onToggle('PICKS')}
          accessibilityRole="button"
          accessibilityState={{ selected: filter.has('PICKS') }}
          style={[styles.pill, { borderColor: PICKS_COLOR }, filter.has('PICKS') && { backgroundColor: PICKS_COLOR }]}
        >
          <Text style={[styles.pillText, { color: filter.has('PICKS') ? ink.ink0 : chalk.dim }]}>
            Picks
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// One team as a VERTICAL stacked column (2026-07-26): position segments
// TOP-DOWN QB→RB→WR→TE — the same order as the filter pills (#195) — with
// the neutral Picks segment at the BASE in the All view (picks stay last in
// the QB→RB→WR→TE→Picks reading order, so the former top "cap" becomes the
// base under the top-down flip). Height scaled to the league max, slightly
// rounded top (≤8px per Chalkline), rank numeral underneath (the caller's
// numeral in an ice pill). In drill-in focus every non-selected column
// renders muted-gray segments.
function BarColumn({ tc, rank, active, maxActive, subset, filter, focused, grayed, onPress }: {
  tc: TeamComputed;
  rank: number;
  active: number;
  maxActive: number;
  subset: Subset;
  filter: Set<FilterKey>;
  focused: boolean;
  grayed: boolean;
  onPress: () => void;
}) {
  const team = tc.team;
  const shownBase: FilterKey[] =
    filter.size > 0
      ? [...filter]
      : subset === 'all'
        ? [...CORE_POSITIONS, 'PICKS']
        : [...CORE_POSITIONS];
  // Stable stacking order regardless of Set insertion order: QB→RB→WR→TE
  // top-down (#195, filter-pill order), Picks last (= the base).
  const orderOf = (p: FilterKey) =>
    p === 'PICKS' ? CORE_POSITIONS.length : CORE_POSITIONS.indexOf(p as CorePos);
  const shown = shownBase.sort((a, b) => orderOf(a) - orderOf(b));
  const segValue = (p: FilterKey): number =>
    p === 'PICKS'
      ? subset === 'all' ? team.picks?.value ?? 0 : 0
      : tc.posValues[p];
  const segColor = (p: FilterKey): string =>
    grayed ? GRAY_SEGMENT[p] : p === 'PICKS' ? PICKS_COLOR : posColor(p);
  const segSum = shown.reduce((s, p) => s + segValue(p), 0);
  const heightPct = active > 0 ? Math.max((active / maxActive) * 100, 3) : 0;
  // #195 — render top→bottom in `shown` order directly (QB at the top,
  // Picks at the base), matching the filter-pill order.
  const stack = shown;
  const name = team.display_name || team.username || team.user_id;

  return (
    <Pressable
      testID={`league-summary.bar.${team.user_id}`}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Rank ${rank}, ${name}, ${Math.round(active).toLocaleString('en-US')} total`}
      accessibilityState={{ selected: focused }}
      style={styles.col}
      hitSlop={{ top: 8, bottom: 0, left: 1, right: 1 }}
    >
      <View style={styles.colWell}>
        {heightPct > 0 ? (
          <View style={[styles.colBar, { height: `${heightPct}%` }]}>
            {segSum > 0
              ? stack.map((p) => {
                  const v = segValue(p);
                  if (v <= 0) return null;
                  return (
                    <View
                      key={p}
                      style={{ height: `${(v / segSum) * 100}%`, backgroundColor: segColor(p) }}
                    />
                  );
                })
              : null}
          </View>
        ) : null}
      </View>
      <View style={[styles.colRankWrap, team.is_you && styles.colRankWrapYou]}>
        <Text style={[styles.colRank, team.is_you && styles.colRankYou]}>{rank}</Text>
      </View>
    </Pressable>
  );
}

// One team as a ranked list row under the chart: rank numeral, name + You
// badge, active value, chevron. The caller's row is surface+border
// highlighted (state via border and surface color, per Chalkline).
function TeamRow({ team, rank, active, onPress }: {
  team: PowerRankedTeam;
  rank: number;
  active: number;
  onPress: () => void;
}) {
  return (
    <Pressable
      testID={`league-summary.team.${team.user_id}`}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`View ${team.display_name || team.username} roster, rank ${rank}`}
      style={({ pressed }) => [
        styles.listRow,
        team.is_you && styles.listRowYou,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <Text style={[styles.listRank, team.is_you && { color: ice.base }]}>{rank}</Text>
      <View style={styles.listNameRow}>
        <Text style={[type.title, styles.listName]} numberOfLines={1}>
          {team.display_name || team.username || team.user_id}
        </Text>
        {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
      </View>
      <View style={styles.listRight}>
        <Text style={type.data}>{active > 0 ? Math.round(active).toLocaleString('en-US') : '—'}</Text>
        <Icon name="chevron-right" size={14} color={chalk.dim} />
      </View>
    </Pressable>
  );
}

// ── #169 outlook odds ────────────────────────────────────────────────────
// Friendly captions for the backend's roster-strength source. Unknown keys
// degrade to a generic projection caption rather than leaking a raw enum.
const STRENGTH_SOURCE_CAPTION: Record<string, string> = {
  roster_value: 'Preseason roster-value projection',
  trailing_scores: 'Based on recent scoring',
  blended: 'Blended projection',
};
function sourceCaption(src: string): string {
  return STRENGTH_SOURCE_CAPTION[src] ?? 'Projected from team strength';
}

// The load-bearing honesty label. `meta.beta`/`meta.is_preseason` are true
// today (July, zero games), so this reads "Projected · preseason · beta" —
// never a bare authoritative percentage.
function betaRibbonLabel(meta: OutlookMeta): string {
  const parts = ['Projected'];
  if (meta.is_preseason) parts.push('preseason');
  if (meta.beta) parts.push('beta');
  return parts.join(' · ');
}

// 0..1 fraction → whole-percent string. Preseason values are 0.0 → "0%".
function pct(frac: number): string {
  return `${Math.round((frac ?? 0) * 100)}%`;
}

function record(t: OutlookTeam): string {
  const base = `${t.wins}-${t.losses}`;
  return t.ties > 0 ? `${base}-${t.ties}` : base;
}

// The playoff/title-odds section. Rendered only when `outlook.odds` is on;
// degrades quietly (renders nothing) while the endpoint is dark/404s so the
// screen never shows a broken projection block.
function OddsSection({ query }: { query: UseQueryResult<LeagueOutlookResponse> }) {
  const data = query.data;

  if (query.isLoading && !data) {
    return (
      <View style={styles.oddsSection} testID="league-summary.odds.section">
        <TickLabel color={semantic.warn}>Playoff picture</TickLabel>
        <View style={styles.oddsLoading}>
          <ActivityIndicator color={semantic.warn} />
        </View>
      </View>
    );
  }

  // No data (dark endpoint / error / empty league) → render nothing. Better a
  // missing section than a fabricated or broken one.
  if (!data || data.teams.length === 0) return null;

  const { meta, teams } = data;

  return (
    <View style={styles.oddsSection} testID="league-summary.odds.section">
      <View style={styles.oddsHead}>
        <TickLabel color={semantic.warn}>Playoff picture</TickLabel>
        <View
          style={styles.betaRibbon}
          testID="league-summary.odds.beta-ribbon"
          accessibilityRole="text"
        >
          <Text style={styles.betaRibbonText}>{betaRibbonLabel(meta)}</Text>
        </View>
      </View>
      <Text
        style={[type.bodySm, styles.oddsSource]}
        testID="league-summary.odds.source"
      >
        {`${sourceCaption(meta.strength_source)} · ${meta.sims.toLocaleString('en-US')} sims · top ${meta.playoff_slots} make the playoffs`}
      </Text>

      <View style={styles.oddsList}>
        {teams.map((t, idx) => (
          <OddsRow key={t.roster_id} team={t} rank={idx + 1} />
        ))}
      </View>
    </View>
  );
}

// One team's projected odds: order numeral (payload is pre-sorted by
// playoff_pct desc), name + You badge, record + projected seed, then the two
// headline odds (playoff / title) as figure + thin warn meter.
function OddsRow({ team, rank }: { team: OutlookTeam; rank: number }) {
  return (
    <View
      style={styles.oddsRow}
      testID={`league-summary.odds.row.${team.roster_id}`}
    >
      <Text style={[styles.oddsRank, team.is_you && { color: ice.base }]}>{rank}</Text>
      <View style={styles.oddsMid}>
        <View style={styles.oddsNameRow}>
          <Text style={[type.title, styles.oddsName]} numberOfLines={1}>
            {team.display_name || team.username || String(team.roster_id)}
          </Text>
          {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
        </View>
        <Text style={[type.data, styles.oddsSub]}>
          {`${record(team)} · proj seed ${team.odds.projected_seed.toFixed(1)}`}
        </Text>
        <View style={styles.oddsStats}>
          <OddStat label="Playoff" frac={team.odds.playoff_pct} />
          <OddStat label="Title" frac={team.odds.title_pct} />
        </View>
      </View>
    </View>
  );
}

// A single projected-odds figure with a thin warn meter. Warn (amber) is the
// "this is projected, not settled" signal — matches the mockup's amber block.
function OddStat({ label, frac }: { label: string; frac: number }) {
  const fillPct = Math.max(0, Math.min(1, frac ?? 0)) * 100;
  return (
    <View style={styles.oddStat}>
      <Text style={styles.oddStatLabel}>{label}</Text>
      <Text style={[type.data, styles.oddStatValue]}>{pct(frac)}</Text>
      <View style={styles.oddStatTrack}>
        {fillPct > 0 ? (
          <View style={[styles.oddStatFill, { width: `${fillPct}%` }]} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl },

  // #181 — League home entry row (LeagueRow construction, mirrors
  // LeagueScreen's explore rows).
  homeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    marginBottom: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  homeMain: { flex: 1, gap: 2 },
  homeSub: { color: chalk.dim },

  basisRow: { flexDirection: 'row', gap: space.sm, marginBottom: space.md },
  basisChip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
  },
  basisChipActive: {
    backgroundColor: ink.ink3,
    borderColor: ink.lineStrong,
  },
  basisChipTextActive: { color: chalk.base },
  basisChipDisabled: { opacity: 0.45 },

  // ── Chart card (2026-07-26) ───────────────────────────────────────────
  card: {
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    marginBottom: space.md,
  },
  cardHead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  cardHeadMain: { flex: 1, gap: 2 },
  cardCaption: { color: chalk.dim },
  headBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headBtnPressed: { backgroundColor: ink.ink3 },
  updatedAt: { color: chalk.faint, marginTop: space.xs },

  // #243 focused-state slim strip — "‹ All teams" back affordance (replaces
  // the X while focused; same 32pt control height) + the passive filter
  // caption that stands in for the card's interactive controls.
  backLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    minHeight: 32,
  },
  backLinkText: { ...type.label, color: ice.base },
  filterCaption: {
    marginTop: space.sm,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
  },
  filterCaptionText: { color: chalk.dim },
  filterCaptionValue: { color: chalk.base, fontWeight: '600' },

  subsetRow: {
    flexDirection: 'row',
    marginTop: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  subsetSeg: {
    flex: 1,
    paddingVertical: space.sm,
    alignItems: 'center',
    minHeight: 34,
    justifyContent: 'center',
  },
  subsetSegOn: { backgroundColor: ink.ink3 },
  subsetSegText: { ...type.label, color: chalk.dim },
  subsetSegTextOn: { color: chalk.base },

  posFilter: { flexDirection: 'row', gap: space.sm, flexWrap: 'wrap', marginTop: space.md },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radii.pill,
    borderWidth: 1,
  },
  pillText: { ...type.label, letterSpacing: 0.5 },

  hint: { marginTop: space.sm, marginBottom: space.md, color: chalk.dim },
  // #243 — tighter hint margins in the focused slim strip only (audit fix #3).
  hintTight: { marginTop: space.xs, marginBottom: space.sm },

  // Vertical stacked columns — x-axis = rank 1..N.
  chartWrap: { position: 'relative' },
  chartRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 3,
  },
  // League-average overlay — spans the bar region only (CHART_HEIGHT), so
  // the line lands on the same scale the bars use.
  avgOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: CHART_HEIGHT,
  },
  avgLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 0,
    borderTopWidth: 1,
    borderStyle: 'dashed',
    borderColor: chalk.dim,
  },
  avgLabel: {
    position: 'absolute',
    right: 0,
    ...type.label,
    fontSize: 11,
    color: chalk.dim,
  },
  col: { flex: 1, alignItems: 'stretch' },
  colWell: {
    height: CHART_HEIGHT,
    justifyContent: 'flex-end',
  },
  colBar: {
    width: '100%',
    borderTopLeftRadius: radii.sm,
    borderTopRightRadius: radii.sm,
    overflow: 'hidden',
  },
  colRankWrap: {
    alignSelf: 'center',
    marginTop: space.xs,
    minWidth: 20,
    paddingHorizontal: 3,
    paddingVertical: 1,
    borderRadius: radii.pill,
    alignItems: 'center',
  },
  colRankWrapYou: { backgroundColor: ice.base },
  colRank: { ...type.data, fontSize: 11, lineHeight: 15, color: chalk.dim },
  colRankYou: { color: ice.on },

  legend: { flexDirection: 'row', gap: space.lg, flexWrap: 'wrap', marginTop: space.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendSwatch: { width: 9, height: 9, borderRadius: radii.xs },
  legendLabel: { ...type.bodySm, color: chalk.dim },

  // Ranked team list (chart unfocused).
  list: { gap: 2 },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    paddingHorizontal: space.xs,
    minHeight: 44,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  listRowYou: {
    backgroundColor: ink.ink2,
    borderBottomColor: ink.lineStrong,
  },
  listRank: {
    ...type.data,
    width: 24,
    textAlign: 'center',
    color: chalk.dim,
  },
  listNameRow: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.sm },
  listName: { flexShrink: 1 },
  listRight: { flexDirection: 'row', alignItems: 'center', gap: space.xs },

  // Drill-in roster panel (inline, replaces the list while focused).
  drillPanel: { marginBottom: space.md },
  drillSub: { color: chalk.dim },
  drillFilter: { marginTop: space.sm },
  drillList: { marginTop: space.xs, gap: space.xs },

  groupHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
  },
  groupLabel: { ...type.label },
  groupMetaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  groupMeta: { color: chalk.dim },
  rankChip: {
    borderWidth: 1,
    borderRadius: radii.xs,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  rankChipText: { ...type.data, fontSize: 11, lineHeight: 15 },
  rosterRow: { marginBottom: space.xs },
  pickRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: 40,
    paddingHorizontal: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },

  // #169 outlook odds section — sits between the basis toggle and the chart,
  // fenced off with a bottom hairline. Warn (amber) is the projection signal.
  oddsSection: {
    marginBottom: space.lg,
    paddingBottom: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  oddsHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  betaRibbon: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: semantic.warn,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  betaRibbonText: { ...type.label, color: semantic.warn },
  oddsSource: { marginTop: space.sm, color: chalk.dim },
  oddsLoading: { paddingVertical: space.xl, alignItems: 'center' },

  oddsList: { marginTop: space.md, gap: 2 },
  oddsRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  oddsRank: {
    ...type.data,
    width: 22,
    textAlign: 'center',
    color: chalk.dim,
    marginTop: 2,
  },
  oddsMid: { flex: 1, gap: 5 },
  oddsNameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  oddsName: { flexShrink: 1 },
  oddsSub: { color: chalk.dim },
  oddsStats: { flexDirection: 'row', gap: space.md, marginTop: 2 },
  oddStat: { flex: 1, gap: 4 },
  oddStatLabel: { ...type.label, color: chalk.faint },
  oddStatValue: { color: chalk.base },
  oddStatTrack: {
    height: 5,
    backgroundColor: ink.ink3,
    borderRadius: 3,
    overflow: 'hidden',
  },
  oddStatFill: { height: '100%', backgroundColor: semantic.warn, borderRadius: 3 },

  center: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.sm,
  },
  centerBody: { textAlign: 'center' },
});
