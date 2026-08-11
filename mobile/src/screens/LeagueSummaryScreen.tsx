import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
  BackHandler,
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
  fonts,
  position as positionColors,
} from '../theme/chalkline';
import { Badge, Icon, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import MemberEnteredMarker from '../components/MemberEnteredMarker';
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
import { useOutlookStripExpanded } from '../state/outlookStrip';
import { track } from '../api/events';
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
//     RE-VALUE to the selected keys and RE-SORT teams — a pure client-side
//     transform over per-position values (no refetch). Restyled to colored
//     outline pills, selected = solid fill. Under
//     `league.picks_always_counted` (#293/#294, shipped ON v1.12.0; the flag is a kill switch) the selected
//     keys ALWAYS include draft capital unless the user explicitly
//     deselects the Picks pill: tapping the first position pill auto-adds
//     PICKS, so a filter never silently drops a team's pick value. With the
//     flag OFF the bars re-value to the selected position(s) ONLY, which is
//     the shipped pre-#293 behavior.
//   - All · Starters · Bench segmented control (2026-07-26): "Starters" is
//     the DERIVED value-optimal lineup the server computes per team
//     (payload `teams[].starters` — the league's slot template filled with
//     each team's highest-value eligible players; NO per-week lineup data),
//     "Bench" is the rest. Selecting either recomputes EVERY team's
//     per-position values from that subset and re-ranks the whole league
//     (draft capital is NOT recomputed — under
//     `league.picks_always_counted` it is added to both subsets whole; see
//     `activeTotal`); the drill-in filters to the same subset. Rendered
//     ONLY when the payload says `starters_available` (honest degradation —
//     platforms without a slot template hide the control entirely).
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
//   - #248 combined rank bars, V2 (2026-08-05, approved mock
//     mockups/polish-lab-2026-08/combined-rank-bars.html): ONE chart carries
//     BOTH boards. The screen now runs TWO parallel queries (one per basis —
//     same endpoint, same per-basis queryKeys as before, cache-compatible);
//     the basis toggle's new role is choosing which basis draws the BARS
//     (labels flip to "Consensus sorts" / "My board sorts" once both boards
//     are loaded and differ). The OTHER basis renders as a dashed ice tick
//     overlay per column (testID league-summary.tick.<user_id>) at that
//     team's other-board total, plus a signed ▲/▼ delta chip (testID
//     league-summary.delta.<user_id>, semantic pos/neg) when the two bases'
//     ranks differ by ≥2. Bars + ticks + the avg line share ONE max scale so
//     a tick can never clip off the top. Tick/delta math reuses the exact
//     same client-side derivation as the bars (computeSubset + activeTotal
//     over the other payload's own basis-aware rosters/starters), so the
//     All/Starters/Bench + position filters recompute both signals
//     consistently; if the other payload can't derive starters
//     (starters_available false), ticks hide for the starters/bench subsets
//     rather than fabricate. When the caller has no my-board data the two
//     payloads are value-identical (personal Elo = consensus seed) — ticks,
//     chips and the "sorts" labels all hide and the screen renders exactly
//     the pre-#248 consensus-only chart. Drill-in focus hides every
//     non-focused tick/chip (mock rule) and the focus caption + drill
//     subline state both ranks ("My board rank 7/12 · Consensus rank 2/12").
//   - #208 ranks follow the position filter (2026-08-08): the reported
//     symptom (rank numerals pinned to the unfiltered ordering) does NOT
//     reproduce here — every numeral is an index into `ranked`, which takes
//     `posFilter` as a memo dependency, and the server's `team.rank` is read
//     nowhere. See docs/feedback/items/208-ranks-follow-position-filter/.
//     What #208 DID find is that #248's overlay made its values filter-aware
//     but not its DRAW decision: `ticksOn` gated on the whole-roster
//     `boardsDiffer`, so a filtered view in which the two bases hold
//     identical values (filter to QB when only RBs were re-ranked) still drew
//     a tick on every bar top and printed "Consensus rank 3/12 · My board
//     rank 3/12". `ticksOn` now gates on `boardsDifferInView` — the same
//     comparison over the values on screen. `boardsDiffer` keeps its
//     unfiltered identity meaning and keeps driving the "… sorts" labels, so
//     the toggle copy doesn't flicker per pill. Also: the dual-rank captions
//     divide the other basis' rank by the OTHER payload's team count
//     (`otherCount`), not the bars'.
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
// #169 SEASON OUTLOOK layer (flag `outlook.odds`, DARK): ONE merged section
// between the basis toggle and the dynasty chart. It is a SEPARATE gated
// section — when `outlook.odds` is off (the default; the flag is absent from
// LAUNCHED_FLAG_DEFAULTS) nothing renders and GET /api/league/outlook is NOT
// called (it 404s while the modeling backend is dark). Only when on do we
// fetch + render. The basis toggle governs BOTH the outlook fetch and the
// dynasty chart.
//
// v2 (2026-08-10, docs/feedback/items/169-outlook-league-summary/
// odds-surface-audit.md § ranked build order item 1; mockup
// mockups/outlook-odds/league-summary-outlook-v2.html frames B + C1 + D). The
// design is a calibration result, not a style preference —
// calibration-combined-2026-08-10.md is the authority and none of the
// following may be "improved" without re-measuring:
//   • PROJECTED STANDINGS AND PLAYOFF ODDS ARE ONE THING. Row order (by
//     `odds.projected_seed`) plus the dashed cutline IS the projected
//     standings; the three-band chip IS the playoff odds. No second list, no
//     toggle, no separate screen.
//   • NO RAW PERCENTAGES. The engine is over-confident at the extremes (a 95%
//     preseason call realizes 78%), so bands — Likely / Toss-up / Unlikely,
//     thresholds in docs/cross-client-invariants.md — are the finest
//     granularity the evidence supports.
//   • NO TITLE ODDS, ANYWHERE. `odds.title_pct` has no demonstrated skill (CI
//     spans zero; 3 of 6 backtested league-seasons lose to guessing). It is
//     absent, not caveated.
//   • `meta.beta` IS THE TWO-STATE SWITCH, and it is the only one. It clears
//     at `completed_weeks >= 6`, the week the playoff Brier nearly halves.
//     Weeks 0–5 (beta true): order + bands, NO win-loss numbers — a projected
//     record is the same false-precision point estimate as "71%" in a
//     different unit. Week 6+ (beta false): rows gain current + projected
//     records.
//   • IDP CAPTION. When `meta.priced_slot_coverage` reports partial coverage
//     AND `affects_strength`, the section says the projection reads offensive
//     starters only. Never captioned when `affects_strength` is false (a
//     `trailing_scores` payload never read a value board).
//   • NON-SLEEPER LEAGUES get an honest one-row unavailable state and no
//     request — `backend/outlook/league_state.py` implements Sleeper only, so
//     the others would 501.
// Amber/warn is the projection signal throughout (the established "Projected"
// visual language on this screen).

type UiBasis = 'consensus' | 'personal';
type CorePos = 'QB' | 'RB' | 'WR' | 'TE';
// #14 FR1 — the filterable chart keys: the four positions plus the
// draft-capital group ("Picks"). Picks isn't a position, so it renders in a
// neutral ink tone, never a position hex (cross-client-invariants).
// #293/#294 (flag `league.picks_always_counted`, shipped ON v1.12.0; kill switch): the Picks key
// exists in EVERY subset — draft capital is subset-independent, so it is
// selectable and charted in Starters and Bench too. With the flag OFF the
// key only exists in the All subset (the shipped pre-#293 rule).
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
// backend rank; includes draft capital). A non-empty filter = the summed
// value of the selected groups.
//
// #293/#294, flag `league.picks_always_counted` (shipped ON v1.12.0; kill switch) — a REVERSAL of
// the shipped "picks are neither starters nor bench" rule, on the operator's
// ruling that a team's draft-pick value contribution is subset-independent
// and filter-independent: switching to Starters/Bench or filtering to a
// position must never make a team's value silently drop by its draft capital.
//   ON  — starters/bench = the recomputed core-position sum PLUS the team's
//         full `picks.value`, and a `PICKS` filter member contributes that
//         value in every subset.
//   OFF — starters/bench = the core-position sum alone and a `PICKS` member
//         contributes a literal 0 outside All (the pre-#293 behavior).
// `all` keeps returning `total_value` in BOTH states and must never add
// `picks.value` again — the server already summed it in
// (total_value = positions_value + picks.value, docs/api-reference.md).
//
// NAMED CONSEQUENCE of the ON state: because the same `picks.value` is
// counted in both halves, Starters + Bench deliberately no longer partition
// All (starters_active + bench_active = positions_value + 2·P). The screen
// never displays that sum, and the hint copy names the second component
// ("Best starting lineup + draft capital.") rather than claiming "only".
//
// PILL INVARIANT (state it in exactly this qualified form — the unqualified
// version is FALSE for an empty filter): *whenever the filter is non-empty,
// the Picks pill's selected state is exactly equal to whether pick value is
// in the chart. An empty filter means every key — including picks — with no
// pill selected.*
//
// The flag arrives as a REQUIRED 4th parameter with NO default: this function
// is module-scope and cannot close over the component's `useFlag` result, and
// a defaulted parameter would let an unthreaded call site compile while
// silently behaving as OFF. Both call sites (`ranked`, `otherByTeam`) MUST
// pass it — threading only the bars would make the #248 other-basis overlay
// disagree with them by exactly P and reintroduce #208's spurious ticks.
function activeTotal(
  tc: TeamComputed,
  subset: Subset,
  filter: Set<FilterKey>,
  picksAlwaysCounted: boolean,
): number {
  if (filter.size === 0) {
    if (subset === 'all') return tc.team.total_value;
    return picksAlwaysCounted ? tc.coreTotal + (tc.team.picks?.value ?? 0) : tc.coreTotal;
  }
  let sum = 0;
  filter.forEach((p) => {
    if (p === 'PICKS') {
      sum += picksAlwaysCounted
        ? tc.team.picks?.value ?? 0
        : subset === 'all'
          ? tc.team.picks?.value ?? 0
          : 0;
    } else sum += tc.posValues[p];
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
        ? registerScrollToTop('League', () => {
            // #302 — re-tapping the ACTIVE tab means "put this tab back to
            // its root state". Scrolling to the top of a focused team's
            // roster is only half of that: the user is still inside a
            // drill-in they have no other way out of once they've scrolled.
            // Clear the focus first, then scroll.
            setSelectedId(null);
            scrollRef.current?.scrollTo({ y: 0, animated: true });
          })
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

  // #248 — the screen holds BOTH bases at once via two parallel queries
  // against the same endpoint (chosen over a combined-payload backend change:
  // the per-basis payload is a per-league aggregate the server computes in
  // one pass, the queryKeys are byte-identical to the pre-#248 single query
  // so the cache carries over, and no backend/API-contract change is
  // needed). `basis` picks which payload draws the BARS; the other payload
  // drives the tick/delta overlay. The personal query fails quietly for
  // unverified callers (no ticks); toggling to My board surfaces the same
  // verification error as before.
  const consensusQuery = useQuery({
    queryKey: ['league-power-rankings', leagueId, 'consensus'],
    queryFn: () => getPowerRankings(leagueId!, 'consensus'),
    enabled: !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const personalQuery = useQuery({
    queryKey: ['league-power-rankings', leagueId, 'personal'],
    queryFn: () => getPowerRankings(leagueId!, 'personal'),
    enabled: !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const query = basis === 'personal' ? personalQuery : consensusQuery;
  const otherQuery = basis === 'personal' ? consensusQuery : personalQuery;
  const refetchBoth = () => {
    consensusQuery.refetch();
    personalQuery.refetch();
  };

  // #169 season outlook — DARK behind `outlook.odds`. `enabled` is false unless
  // the flag is on AND a league is selected AND the platform is one the
  // simulator implements, so GET /api/league/outlook never fires while the
  // layer is dark (the endpoint 404s) nor for a league the engine would 501
  // on. Shares the `basis` state with the dynasty chart. Off by default: the
  // flag is absent from LAUNCHED_FLAG_DEFAULTS, so `useFlag` returns false
  // until a live map turns it on.
  const oddsEnabled = useFlag('outlook.odds');
  // Client-side platform gate (audit surface #12). `backend/outlook/
  // league_state.py` registers ESPN/MFL/Fleaflicker as NotImplemented stubs,
  // so an outlook request for one of them is a guaranteed 501 — and the League
  // tab IS reachable for those leagues, which makes silence a mystery rather
  // than honest degradation. Resolve the platform the same way every other
  // client gate does (`api/espn.ts:isEspnLeague`, `api/platformLink.ts`):
  // match the active id against the cached league list. UNKNOWN RESOLVES TO
  // SUPPORTED — a league missing from the list (or a server that didn't stamp
  // `platform`) must not lose the section on a guess; only a positively
  // identified non-Sleeper platform is gated out.
  // Selected as a BOOLEAN, not as the leagues array: the store compares with
  // Object.is, so the screen re-renders only when the answer actually flips —
  // with the flag dark this subscription can never change what renders.
  const outlookSupported = useSession(
    (s) =>
      (s.leagues.find((lg) => lg.league_id === leagueId)?.platform ?? 'sleeper') ===
      'sleeper',
  );
  const outlookQuery = useQuery({
    queryKey: ['league-outlook', leagueId, basis],
    queryFn: () => getOutlook(leagueId!, basis),
    enabled: oddsEnabled && outlookSupported && !!leagueId,
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

  // #293/#294 — the ONE read of `league.picks_always_counted` (shipped ON
  // v1.12.0; the flag is a kill switch, not a dark launch).
  // Every gated expression on this screen resolves to THIS boolean within a
  // render: the flag switches the whole set atomically or not at all. Bar
  // SEGMENT heights are percentages of their own sum while a bar's HEIGHT
  // comes from the team total, so a partially-gated build would grow the bar
  // by the pick value while silently stretching the four position segments to
  // fill it — a bar that looks right and encodes a lie. The two module-scope
  // consumers that cannot close over this identifier (`activeTotal`,
  // `BarColumn`) take it as a REQUIRED, undefaulted parameter/prop so `tsc`
  // catches an unthreaded caller. Never call `useFlag` for this key again.
  const picksAlwaysCounted = useFlag('league.picks_always_counted');

  // Picks pill/segments only when the league actually carries draft capital
  // (ESPN + demo leagues report zero; old servers omit the field entirely).
  // #293/#294: with the flag ON that is the whole condition — draft capital
  // is charted in every subset, so its pill and legend key render in every
  // subset too. With the flag OFF the key additionally requires the All
  // subset (the pre-#293 "picks are neither starters nor bench" rule).
  const hasPicks = teams.some((t) => (t.picks?.value ?? 0) > 0);
  const showPicksKey = picksAlwaysCounted ? hasPicks : hasPicks && subset === 'all';
  // Is pick value actually part of the charted value right now? Drives the
  // three hint/subline strings so none of them claims "only" while draft
  // capital is in the bar. Gated on the flag itself, or the copy would change
  // while the arithmetic did not.
  const picksInView =
    picksAlwaysCounted && hasPicks && (posFilter.size === 0 || posFilter.has('PICKS'));

  // #293/#294 kill-switch reconciliation. Flag ON makes
  // (subset ≠ all ∧ PICKS ∈ posFilter) a routine state; it is UNREACHABLE
  // with the flag OFF. If the operator pulls the switch mid-session the
  // server map wins on the next revalidate while `posFilter` — component
  // state — persists, leaving an invisible, unremovable filter member
  // silently zeroing the view (worst case: every bar 0, no pill on screen to
  // explain it). Same shape as the `startersAvailable` fallback above.
  // A no-op in a never-ON session, so first-render OFF stays byte-identical.
  // This does NOT replace `switchSubset`'s synchronous OFF-path strip — that
  // one runs before the render, this one after; dropping either is a
  // regression, not a simplification.
  useEffect(() => {
    if (!picksAlwaysCounted && subset !== 'all' && posFilter.has('PICKS')) {
      setPosFilter((prev) => {
        const next = new Set(prev);
        next.delete('PICKS');
        return next;
      });
    }
  }, [picksAlwaysCounted, subset, posFilter]);

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
      active: activeTotal(tc, subset, posFilter, picksAlwaysCounted),
    }));
    rows.sort(
      (a, b) =>
        b.active - a.active || (a.tc.team.user_id < b.tc.team.user_id ? -1 : 1),
    );
    return rows;
  }, [computed, subset, posFilter, picksAlwaysCounted]);

  const maxActive = useMemo(
    () => Math.max(1, ...ranked.map((r) => r.active)),
    [ranked],
  );

  // ── #248 — other-basis overlay (ghost tick + delta chips) ──────────────
  // A caller with no my-board data gets personal values identical to
  // consensus (personal Elo starts at the consensus seed) — in that case the
  // overlay would only mark the bars against themselves, so it hides and the
  // screen renders exactly the pre-#248 single-basis chart.
  // `boardsDiffer` answers ONE question: does the caller have a my-board that
  // is distinct from consensus AT ALL (whole roster, every position)? That is
  // an identity check, so it stays unfiltered — it drives the basis-toggle's
  // "… sorts" labels, whose meaning doesn't change as the user pages through
  // position pills. Whether the overlay should DRAW is a different, filtered
  // question — see `boardsDifferInView` / `ticksOn` below (#208).
  const otherTeams = otherQuery.data?.teams ?? [];
  const boardsDiffer = useMemo(() => {
    if (!query.data || !otherQuery.data) return false;
    const totals = new Map(teams.map((t) => [t.user_id, t.total_value]));
    return otherTeams.some((t) => totals.get(t.user_id) !== t.total_value);
  }, [query.data, otherQuery.data, teams, otherTeams]);
  const otherStartersAvailable =
    otherQuery.data?.starters_available === true &&
    otherTeams.length > 0 &&
    otherTeams.every((t) => Array.isArray(t.starters));
  // Ticks/deltas recompute per the filtered subset using the SAME derivation
  // as the bars (computeSubset + activeTotal over the other payload's own
  // basis-aware rosters + starters). Honest degradation: if the other
  // payload can't derive starters, the overlay hides for starters/bench
  // rather than fabricate a subset.
  const otherComputed = useMemo(
    () => otherTeams.map((t) => computeSubset(t, subset)),
    [otherTeams, subset],
  );
  // Per-team other-basis active value + rank under the active filters (same
  // sort + tie-break as the bars).
  // #293/#294 — `picksAlwaysCounted` is MANDATORY here, exactly as on the
  // bars. `picks.value` is basis-independent (_power_picks_by_owner takes no
  // basis), so threading both call sites gives the two bases the SAME
  // per-team constant and leaves `boardsDifferInView` — a pure difference
  // comparison — invariant. Threading only the bars would make every
  // picks-holding team's two values differ by exactly P, flipping
  // `boardsDifferInView` true and drawing a fabricated tick and rank-swing
  // chip on every column: #208's reported symptom, reintroduced.
  const otherByTeam = useMemo(() => {
    const rows = otherComputed.map((tc) => ({
      id: tc.team.user_id,
      active: activeTotal(tc, subset, posFilter, picksAlwaysCounted),
    }));
    rows.sort((a, b) => b.active - a.active || (a.id < b.id ? -1 : 1));
    const m = new Map<string, { active: number; rank: number }>();
    rows.forEach((r, i) => m.set(r.id, { active: r.active, rank: i + 1 }));
    return m;
  }, [otherComputed, subset, posFilter, picksAlwaysCounted]);
  // Denominator for the other basis' rank — its OWN team count, not the bars'.
  // The two parallel queries can briefly hold different team sets (a
  // membership change landing between fetches, or one payload served stale via
  // placeholderData), and "#8 of 12" against an 11-team board is a wrong label.
  const otherCount = otherByTeam.size;

  // #208 — the overlay's DRAW decision, under the active filter. Every signal
  // it gates (ticks, delta chips, dual-rank captions, legend key, hint copy) is
  // computed from filtered values, so the "do the boards actually differ?"
  // test has to be filtered too — otherwise a view in which the two bases hold
  // identical values (e.g. filter to QB when the caller has only re-ranked RBs)
  // still draws a tick on top of every bar and prints "Consensus rank 3/12 ·
  // My board rank 3/12", asserting a comparison this view doesn't contain.
  // This is #248's own rule ("identical boards ⇒ the overlay would only mark
  // the bars against themselves, so it hides") applied to the values on screen
  // rather than to the whole roster — a strict generalization: the unfiltered
  // view behaves exactly as it did before.
  const boardsDifferInView = useMemo(() => {
    if (!boardsDiffer) return false;
    return ranked.some((r) => {
      const o = otherByTeam.get(r.tc.team.user_id);
      return !o || o.active !== r.active;
    });
  }, [boardsDiffer, ranked, otherByTeam]);
  const ticksOn =
    boardsDifferInView &&
    otherTeams.length > 0 &&
    (subset === 'all' || otherStartersAvailable);

  // One shared max scale across BOTH bases (mock rule) so a tick whose
  // other-board value beats every bar can never clip off the chart top.
  const scaleMax = useMemo(() => {
    if (!ticksOn) return maxActive;
    let m = maxActive;
    otherByTeam.forEach((v) => {
      if (v.active > m) m = v.active;
    });
    return m;
  }, [ticksOn, maxActive, otherByTeam]);

  const basisLabel = basis === 'personal' ? 'my board' : 'consensus';
  const otherLabel = basis === 'personal' ? 'consensus' : 'my board';

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
  // #248 — the focused team's other-basis rank (focus caption + drill
  // subline state both ranks when the overlay is live).
  const focusOther =
    selected && ticksOn
      ? otherByTeam.get(selected.tc.team.user_id) ?? null
      : null;

  // ── #302 — the drill-in exit lives on the fixed stack header ──────────
  // The drill-in is component state (`selectedId`), not a stack push, so
  // NOTHING in the OS gives the user a way back: no stack back (this is the
  // stack root), no iOS edge-swipe, and — until the BackHandler below — no
  // Android back either. The only control was an 11px caption in the chart
  // card's top-RIGHT, above 1,600pt of roster, so it scrolled away the
  // moment the user did the thing they drilled in for.
  //
  // The fix costs zero vertical space: while a team is focused the already-
  // fixed header takes a `headerLeft` "‹ All teams" — top-LEFT, matching iOS
  // and this app's own `subScreenOptions` (TabNav.tsx) — and its title swaps
  // to the team name, which also answers "which team am I looking at?" at
  // any scroll depth.
  //
  // TAB ROOT ONLY. The legacy root-stack registration ('LeagueSummary',
  // RootNav.tsx:508-530, reached by deep link) already owns its `headerLeft`
  // — the explicit JS back control that exists because native back is dead
  // over `headerShown: false` (RNS#3294). Overwriting it would strip the
  // screen's own exit, and it cannot be restored from here. That variant
  // keeps the in-card link below instead; the two are mutually exclusive, so
  // there is never a second back control on screen.
  const focusedTeamName = selected
    ? selected.tc.team.display_name ||
      selected.tc.team.username ||
      selected.tc.team.user_id
    : null;
  useEffect(() => {
    if (!isTabRoot) return;
    if (focusedTeamName) {
      navigation.setOptions({
        title: focusedTeamName,
        headerTitle: () => <StackHeaderTitle>{focusedTeamName}</StackHeaderTitle>,
        // Keeps testID `league-summary.roster-close` — same function as the
        // control it replaces (#243 did the same when it turned the X into
        // the link), so existing Maestro flows keep working.
        headerLeft: () => (
          <Pressable
            testID="league-summary.roster-close"
            onPress={() => setSelectedId(null)}
            hitSlop={space.md}
            accessibilityRole="button"
            accessibilityLabel="Back to all teams"
            style={({ pressed }) => [styles.headerBack, pressed && { opacity: 0.6 }]}
          >
            <Icon name="chevron-left" size={16} color={chalk.base} />
            <Text testID="league-summary.back-all-teams" style={styles.headerBackText}>
              All teams
            </Text>
          </Pressable>
        ),
      });
    } else {
      navigation.setOptions({
        title: 'League rankings',
        headerTitle: () => <StackHeaderTitle>League rankings</StackHeaderTitle>,
        headerLeft: undefined,
      });
    }
  }, [isTabRoot, navigation, focusedTeamName]);

  // #302 — Android hardware/gesture back. There were ZERO BackHandler
  // registrations in this file, so on Android the drill-in swallowed the
  // system back gesture's meaning entirely: back left the tab (or the app)
  // rather than returning to all teams. Registered only while focused, so
  // unfocused back keeps its normal navigator behaviour.
  useEffect(() => {
    if (!selectedId) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      setSelectedId(null);
      return true; // handled — do not fall through to the navigator
    });
    return () => sub.remove();
  }, [selectedId]);

  // The single shared pill factory — both pill rows use it, so the drill-in
  // panel mirrors the chart card automatically.
  //
  // #294, flag `league.picks_always_counted`: selecting a position must not
  // remove draft capital, so the plain toggle gains two rules (ON only):
  //   A — auto-add: the FIRST position tap out of the unfiltered state also
  //       selects PICKS, so the filter never silently drops pick value. The
  //       pill lights up, so the inclusion is visible and one tap reverses it.
  //   B — exit: removing a position that leaves NO core position selected
  //       clears the filter to All, instead of stranding the user in a
  //       picks-only ranking they never asked for. This is what keeps the
  //       position pill reversible — tap RB on, tap RB off, back where you
  //       started. Its one cost: starting at {PICKS}, adding RB, then
  //       removing RB lands on All rather than back on {PICKS} (one extra
  //       tap). Distinguishing those would need a hidden "the user chose
  //       picks by hand" state axis, which is deliberately NOT built.
  // Both rules are memoryless functions of `prev`, `pos` and `hasPicks`.
  //
  // Invariant, in exactly this qualified form: *whenever the filter is
  // non-empty, the Picks pill's selected state is exactly equal to whether
  // pick value is in the chart. An empty filter means every key — including
  // picks — with no pill selected.* The unqualified version is FALSE in the
  // empty-filter case (picks ARE charted while the pill reads unselected,
  // exactly as QB value is charted while the QB pill reads unselected) and
  // must not be propagated.
  const togglePos = (setter: React.Dispatch<React.SetStateAction<Set<FilterKey>>>) =>
    (pos: FilterKey | 'ALL') => {
      setter((prev) => {
        if (pos === 'ALL') return new Set();
        const next = new Set(prev);
        const removing = next.has(pos);
        if (removing) next.delete(pos);
        else next.add(pos);
        if (picksAlwaysCounted && pos !== 'PICKS') {
          if (prev.size === 0 && hasPicks) next.add('PICKS'); // rule A
          if (removing && !CORE_POSITIONS.some((p) => next.has(p))) return new Set(); // rule B
        }
        return next;
      });
    };

  // #293/#294 — with `league.picks_always_counted` ON, switching subset never
  // mutates the filter: pick value counts in Starters and Bench too, so a
  // PICKS selection is valid everywhere and stripping it would be the very
  // silent drop the operator's ruling forbids.
  // With the flag OFF, switching off All drops the Picks key from the shared
  // filter — picks are neither starters nor bench there, so a stale PICKS
  // selection would zero bars. This strip is SYNCHRONOUS; the ON→OFF
  // reconciliation effect above runs after a render and covers a different
  // case (the flag changing under a mounted screen). Both are needed.
  const switchSubset = (s: Subset, source: 'chart' | 'roster' = 'chart') => {
    // P0-7 — guarded on a real change; the auto-fallback effect above calls
    // setSubset DIRECTLY and is deliberately silent (a server-driven
    // fallback is not a user switching a subset).
    if (s !== subset) {
      track('league_subset_changed', {
        subset: s,
        from: subset,
        source,
        filter_count: posFilter.size,
        // The synchronous OFF-path PICKS strip below actually fired.
        picks_stripped: !picksAlwaysCounted && s !== 'all' && posFilter.has('PICKS'),
      }, route.name);
    }
    setSubset(s);
    if (!picksAlwaysCounted && s !== 'all') {
      setPosFilter((prev) => {
        if (!prev.has('PICKS')) return prev;
        const next = new Set(prev);
        next.delete('PICKS');
        return next;
      });
    }
  };

  // ── P0-7 · league_view (surface: league_rankings) ───────────────────
  // ONCE per mount. This screen holds two parallel queries with
  // placeholderData (#248), so it re-renders constantly and a naive
  // effect would double-fire; the firedRef is the guard and
  // query.isFetched is the trigger. Declared above the `if (!leagueId)`
  // early return — hooks may not sit below it.
  const viewFiredRef = useRef(false);
  useEffect(() => {
    if (viewFiredRef.current) return;
    if (leagueId && !query.isFetched) return;
    viewFiredRef.current = true;
    track('league_view', {
      surface: 'league_rankings',
      state: !leagueId ? 'no_league'
             : query.isError ? 'error'
             : teams.length > 0 ? 'ready' : 'empty',
      platform: useSession.getState().leagues
                  .find((lg) => lg.league_id === leagueId)?.platform ?? 'unknown',
      team_count: teams.length || null,
      basis,
      subset,
      starters_available: startersAvailable,
      // outlook.odds is OFF in config/features.json, so this is `false` on
      // every row until the flag flips. That is correct and honest — do
      // not read the constant as a bug (plan-p0-7 §10.2).
      outlook_shown: oddsEnabled && outlookSupported,
      is_tab_root: isTabRoot,
    }, route.name);
  }, [leagueId, query.isFetched, query.isError, teams.length, basis, subset,
      startersAvailable, oddsEnabled, outlookSupported, isTabRoot, route.name]);

  // P0-7 — the two BasisChips called setBasis directly; route both through
  // one helper so the event has a single choke point. Guarded on a real
  // change, so re-tapping the active chip emits nothing (a no-op row is
  // noise in a funnel).
  const changeBasis = (b: UiBasis) => {
    if (b === basis) return;
    track('league_basis_changed', {
      basis: b,
      from: basis,
      boards_differ: boardsDiffer,
      team_focused: selectedId !== null,
    }, route.name);
    setBasis(b);
  };

  // P0-7 — the two drill-in entry points. `rank` is the 1-based ON-SCREEN
  // rank under the active filters (what the user actually tapped), never
  // the server's unfiltered team.rank. `is_self` is deliberately absent:
  // session-user ↔ PowerRankedTeam.user_id identity was never proven and a
  // guessed prop is worse than a missing one (hld.md S-33).
  const openTeam = (id: string, via: 'bar' | 'row', rank: number) => {
    track('league_team_opened', {
      via, rank, basis, subset, filter_count: posFilter.size,
    }, route.name);
    setSelectedId(id);
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
            onRefresh={refetchBoth}
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
            exists (backend answers 501 not_available). #248 — with both
            boards loaded (and differing) the toggle no longer swaps WHICH
            data you see, only which basis draws the bars (ticks always show
            the other), so the labels flip to the mock's "… sorts" wording. */}
        <View style={styles.basisRow}>
          <BasisChip
            testID="league-summary.basis.consensus"
            label={boardsDiffer ? 'Consensus sorts' : 'Consensus'}
            active={basis === 'consensus'}
            onPress={() => changeBasis('consensus')}
          />
          <BasisChip
            testID="league-summary.basis.personal"
            label={boardsDiffer ? 'My board sorts' : 'My board'}
            active={basis === 'personal'}
            onPress={() => changeBasis('personal')}
          />
          <BasisChip
            testID="league-summary.basis.redraft"
            label="Redraft (soon)"
            active={false}
            disabled
          />
        </View>

        {/* #169 season-outlook layer — gated on `outlook.odds` (dark).
            Rendered only when the flag is on; the fetch is likewise gated so
            nothing fires while dark. Basis-driven (shares the toggle above).
            A non-Sleeper league gets the honest unavailable row instead of the
            section — and no request. Frame E: the layer mounts collapsed as a
            one-line strip; OutlookStripAndSection owns the strip/section
            switch so this mount site stays one expression. */}
        {oddsEnabled ? (
          outlookSupported ? (
            <OutlookStripAndSection query={outlookQuery} leagueId={leagueId} />
          ) : (
            <OutlookUnsupportedRow />
          )
        ) : null}

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
                    {focusOther
                      ? basis === 'personal'
                        ? `My board rank ${selectedIdx + 1}/${ranked.length} · Consensus rank ${focusOther.rank}/${otherCount}`
                        : `Consensus rank ${selectedIdx + 1}/${ranked.length} · My board rank ${focusOther.rank}/${otherCount}`
                      : `League rank: ${selectedIdx + 1}/${ranked.length}`}
                  </Text>
                </>
              ) : (
                <>
                  <Text style={type.title} numberOfLines={1}>
                    {league?.league_name || 'League'}
                  </Text>
                  <Text style={[type.bodySm, styles.cardCaption]}>
                    {ticksOn ? `${formatCaption} — both boards` : formatCaption}
                  </Text>
                </>
              )}
            </View>
            {selected && !isTabRoot ? (
              /* #243 slim strip — the close control is a "‹ All teams" back
                 affordance (approved mock, V1 frame). Same function as the
                 old X, so it KEEPS testID league-summary.roster-close; the
                 label carries the new back-affordance id.
                 #302 — on the TAB ROOT this moved to the stack header (see
                 the setOptions effect above): in the card it sat above
                 1,600pt of roster and scrolled away. It survives only on the
                 legacy root-stack push, whose headerLeft is already taken by
                 that screen's own back control. Exactly one of the two
                 renders, so the ids stay unique on screen. */
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
            ) : selected ? null : (
              <Pressable
                testID="league-summary.refresh"
                onPress={refetchBoth}
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
              source="chart"
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
          {/* #281 — the ticksOn branch used to narrate the chart encodings
              here ("Bar height = … Dashed line = … Arrows mark …"), which
              duplicated the below-graph key row (#248 tick swatch + #260
              ▲▼N entry). Operator: keep only the below-graph key — this
              hint now always states the ranking basis. */}
          <Text style={[type.bodySm, styles.hint, selected ? styles.hintTight : null]}>
            {/* #293 — the word "only" is false whenever draft capital is in
                the bar, so the subset prefix names the second component
                instead. #294 — the filtered branch prints the canonical
                QB→RB→WR→TE label (Picks last, title-cased) rather than the
                raw enum in tap order; that one gates on the FLAG, not on
                `picksInView`, because it is a casing/ordering fix that must
                apply even when the user has deselected Picks — while flag
                OFF must still render today's raw `[...posFilter].join`. */}
            {`${
              subset === 'starters'
                ? picksInView
                  ? 'Best starting lineup + draft capital. '
                  : 'Best starting lineup only. '
                : subset === 'bench'
                  ? picksInView
                    ? 'Bench + draft capital. '
                    : 'Bench only. '
                  : ''
            }${
              posFilter.size === 0
                ? basis === 'consensus'
                  ? 'Ranked by roster value on community consensus.'
                  : 'Ranked by roster value on YOUR board — unranked players use consensus.'
                : `Ranked by ${picksAlwaysCounted ? filterPosLabel : [...posFilter].join(' + ')} value only — chart reordered.`
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
                  {ranked.map((r, idx) => {
                    const id = r.tc.team.user_id;
                    // #248 — the other-basis overlay renders on every column
                    // in the nominal state; while a team is focused only ITS
                    // tick + chip survive (mock declutter rule, matching the
                    // gray-out of non-focused segments).
                    const overlayOn = ticksOn && (!selectedId || selectedId === id);
                    const other = overlayOn ? otherByTeam.get(id) : undefined;
                    const delta = other ? other.rank - (idx + 1) : 0;
                    return (
                      <BarColumn
                        key={id}
                        tc={r.tc}
                        rank={idx + 1}
                        active={r.active}
                        maxActive={scaleMax}
                        subset={subset}
                        filter={posFilter}
                        picksAlwaysCounted={picksAlwaysCounted}
                        focused={selectedId === id}
                        grayed={!!selectedId && selectedId !== id}
                        onPress={() => openTeam(id, 'bar', idx + 1)}
                        showDeltaRow={ticksOn}
                        tickPct={
                          other && other.active > 0
                            ? Math.min((other.active / scaleMax) * 100, 100)
                            : null
                        }
                        delta={Math.abs(delta) >= 2 ? delta : null}
                        otherRank={other?.rank ?? null}
                        otherLabel={otherLabel}
                      />
                    );
                  })}
                </View>
                {/* League-average line — dashed chalk-dim hairline at the
                    mean of the currently shown bar values (filters + subset
                    + basis applied). pointerEvents none so bar taps pass
                    through; label clamped inside the chart area. Hidden
                    when the view sums to zero. */}
                {avgActive > 0
                  ? (() => {
                      // #248 — scaleMax (not maxActive) so the line lands on
                      // the same shared scale the bars + ticks use.
                      const topPx = Math.min(
                        Math.max(CHART_HEIGHT * (1 - avgActive / scaleMax), 15),
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
                {/* #248 — the ghost-tick encoding key (dashed ice = the
                    other basis' total under the same filters). */}
                {ticksOn ? (
                  <View style={styles.legendItem}>
                    <View style={styles.legendTickSwatch} />
                    <Text style={styles.legendLabel}>{`${otherLabel} rank`}</Text>
                  </View>
                ) : null}
                {/* #260 — the delta-chip encoding key (▲/▼N above a bar =
                    that team's rank swing between the two boards, shown
                    only once the swing is ≥2 spots — same threshold the
                    chip itself uses). */}
                {ticksOn ? (
                  <View style={styles.legendItem}>
                    <Text style={styles.legendDeltaGlyph}>{'▲▼N'}</Text>
                    <Text style={styles.legendLabel}>{`rank swing ≥2 vs ${otherLabel}`}</Text>
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
              {`#${selectedIdx + 1} of ${ranked.length}${
                focusOther
                  ? ` (${basisLabel}) · #${focusOther.rank} of ${otherCount} (${otherLabel})`
                  : ''
              } · ${
                selected.active > 0
                  ? // #279 — pick-equivalent label, valid only when `active`
                    // equals the server's authoritative total_value (subset
                    // 'all', no position filter); numeric fallback otherwise.
                    (subset === 'all' && posFilter.size === 0 &&
                      selected.tc.team.total_value_label) ||
                    Math.round(selected.active).toLocaleString('en-US')
                  : '—'
              }${subset === 'all' ? '' : subset === 'starters' ? ' starter' : ' bench'}${
                picksInView && subset !== 'all' ? ' + picks' : ''
              } value`}
            </Text>
            {/* #237 — mirrored filter set: the SAME subset control + position
                pills as the chart card, bound to the SAME state, so the two
                sections can never disagree. */}
            {startersAvailable ? (
              <SubsetControl
                idPrefix="league-summary.roster-subset"
                subset={subset}
                onSwitch={switchSubset}
                source="roster"
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
                // #279 — pick-equivalent label for this position's subtotal,
                // valid only in the 'all' subset (there `g.value` is a
                // client-side resum of the SAME rows the server priced its
                // per-position `value` from, so the two numbers agree;
                // starters/bench recompute a different, unpriced subtotal).
                const posLabel =
                  isCore && subset === 'all'
                    ? selected.tc.team.positions?.[g.pos as CorePos]?.value_label
                    : undefined;
                return (
                  <View key={g.pos}>
                    <View style={styles.groupHead}>
                      <Text style={[styles.groupLabel, { color: posColor(g.pos) }]}>
                        {g.pos}
                      </Text>
                      <View style={styles.groupMetaRow}>
                        <Text style={[type.data, styles.groupMeta]}>
                          {`${g.rows.length} · ${posLabel ?? fmtK(g.value)}`}
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
                          // #299 — this caller passes no `statsSlot`, so the
                          // dense row's line 2 held one tier badge and
                          // nothing else. `denseSingleLine` moves the badge
                          // into the right cluster (left of `posRank`) and
                          // drops line 2: 60pt → 32pt, 64pt → 36pt pitch,
                          // nothing dropped. Opt-in on purpose — the Tiers
                          // board and the FA list keep the 60pt two-line row.
                          denseSingleLine
                          player={{
                            id: r.player_id,
                            name: r.name,
                            position: r.position,
                            team: r.team,
                            age: r.age,
                          }}
                          // #277/#278 — the numeric board value is replaced
                          // by the server-walked pick-tier label
                          // (PowerRankedPlayer.tier). Old servers /
                          // unpriceable rows (K/DEF) → no badge, no number.
                          tier={r.tier ?? null}
                          posRank={playerPosRank.get(r.player_id) ?? 'NR'}
                        />
                      </View>
                    ))}
                  </View>
                );
              })}
              {/* #14 FR1 — draft capital: the team's owned picks, priced on
                  the generic ladder. Hidden for leagues (or teams) without
                  pick data, and when the user has explicitly deselected the
                  Picks pill. #293, flag `league.picks_always_counted`: with
                  the flag ON this group renders under EVERY subset, matching
                  the bar — pick value is in the Starters and Bench totals, so
                  the panel that itemises those totals has to show it. With
                  the flag OFF it stays All-subset only (picks are neither
                  starters nor bench). It is not a roster section: `groupRows`
                  never emits it, so it renders here, below the position
                  groups. */}
              {(picksAlwaysCounted || subset === 'all') &&
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
                      <View style={styles.pickRowBody}>
                        <Text style={type.title} numberOfLines={1}>{p.label}</Text>
                        {/* D17 — priced surface 5 of 5: the draft-capital
                            group. These picks are summed into the team's
                            total and into the league ranking, so a wrong
                            assertion silently reorders the standings.
                            UNCONDITIONAL; the marker self-gates on the flag
                            and on `source === 'user'`. */}
                        <MemberEnteredMarker
                          source={p.source}
                          pickId={p.pick_id}
                          season={p.season}
                          leagueId={leagueId}
                          testID={`league-summary.member-entered.${p.pick_id ?? p.label}`}
                        />
                      </View>
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
                totalLabel={
                  subset === 'all' && posFilter.size === 0
                    ? r.tc.team.total_value_label
                    : undefined
                }
                onPress={() => openTeam(r.tc.team.user_id, 'row', idx + 1)}
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
function SubsetControl({ idPrefix, subset, onSwitch, source }: {
  idPrefix: string;
  subset: Subset;
  onSwitch: (s: Subset, source: 'chart' | 'roster') => void;
  // P0-7 — which of the two mirrored control instances was touched. The
  // two share ONE state (#237), so without this the event cannot tell the
  // chart control from the drill-in roster control.
  source: 'chart' | 'roster';
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
            onPress={() => onSwitch(s.key, source)}
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
// (#14 FR1) appears whenever the league actually has draft capital — in
// EVERY subset under `league.picks_always_counted` (#293/#294), and in the
// All subset only when that flag is OFF. Its selected state is the user's
// explicit opt-in/opt-out of pick value; see `togglePos` for the rules that
// keep it in sync and for the (qualified) pill invariant. Multi-select.
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
// the neutral Picks segment at the BASE (picks stay last in the
// QB→RB→WR→TE→Picks reading order, so the former top "cap" becomes the base
// under the top-down flip). #293, flag `league.picks_always_counted`: ON, the
// Picks segment renders in EVERY subset; OFF, only in the All view.
// `picksAlwaysCounted` is a REQUIRED prop, passed as the bare identifier from
// the component body — this function is module-scope and must never call
// `useFlag` itself. It is what keeps the flag ATOMIC: segment heights are
// `segValue(p) / segSum` while the bar's own height comes from `active`, so
// if `activeTotal` counted picks and `shownBase`/`segValue` did not, the bar
// would grow by the pick value while the four position segments silently
// stretched to fill it — right-looking and wrong.
// Height scaled to the league max, slightly
// rounded top (≤8px per Chalkline), rank numeral underneath (the caller's
// numeral in an ice pill). In drill-in focus every non-selected column
// renders muted-gray segments.
// #248 — combined-bars overlay props: `showDeltaRow` reserves a fixed-height
// chip row above EVERY column whenever the overlay is live (so bars stay
// baseline-aligned whether or not a chip renders); `tickPct` places the
// dashed ice consensus/other-board tick as a bottom-% inside the column well
// (shared scale with the bars); `delta` is the signed rank swing (bar basis
// vs other basis), already thresholded to |Δ| ≥ 2 by the caller — null = no
// chip. All three are null/false when the overlay is off, rendering the
// exact pre-#248 column.
function BarColumn({ tc, rank, active, maxActive, subset, filter, picksAlwaysCounted, focused, grayed, onPress, showDeltaRow, tickPct, delta, otherRank, otherLabel }: {
  tc: TeamComputed;
  rank: number;
  active: number;
  maxActive: number;
  subset: Subset;
  filter: Set<FilterKey>;
  picksAlwaysCounted: boolean;
  focused: boolean;
  grayed: boolean;
  onPress: () => void;
  showDeltaRow: boolean;
  tickPct: number | null;
  delta: number | null;
  otherRank: number | null;
  otherLabel: string;
}) {
  const team = tc.team;
  const shownBase: FilterKey[] =
    filter.size > 0
      ? [...filter]
      : picksAlwaysCounted || subset === 'all'
        ? [...CORE_POSITIONS, 'PICKS']
        : [...CORE_POSITIONS];
  // Stable stacking order regardless of Set insertion order: QB→RB→WR→TE
  // top-down (#195, filter-pill order), Picks last (= the base).
  const orderOf = (p: FilterKey) =>
    p === 'PICKS' ? CORE_POSITIONS.length : CORE_POSITIONS.indexOf(p as CorePos);
  const shown = shownBase.sort((a, b) => orderOf(a) - orderOf(b));
  const segValue = (p: FilterKey): number =>
    p === 'PICKS'
      ? picksAlwaysCounted
        ? team.picks?.value ?? 0
        : subset === 'all' ? team.picks?.value ?? 0 : 0
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
      accessibilityLabel={`Rank ${rank}, ${name}, ${Math.round(active).toLocaleString('en-US')} total${
        otherRank != null ? `, ${otherLabel} rank ${otherRank}` : ''
      }`}
      accessibilityState={{ selected: focused }}
      style={styles.col}
      hitSlop={{ top: 8, bottom: 0, left: 1, right: 1 }}
    >
      {/* #248 — delta chip row: fixed height on every column while the
          overlay is live so a chip never shifts a bar's baseline. */}
      {showDeltaRow ? (
        <View style={styles.deltaWrap}>
          {delta != null ? (
            <View
              testID={`league-summary.delta.${team.user_id}`}
              style={[
                styles.deltaChip,
                { backgroundColor: delta > 0 ? `${semantic.pos}24` : `${semantic.neg}24` },
              ]}
            >
              <Text
                style={[
                  styles.deltaChipText,
                  { color: delta > 0 ? semantic.pos : semantic.neg },
                ]}
              >
                {delta > 0 ? `▲${delta}` : `▼${-delta}`}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}
      <View style={styles.colWell}>
        {/* #248 — dashed ice ghost tick: the other basis' total for this
            team on the shared bar scale (end-cap dot marks the right edge,
            matching the mock). */}
        {tickPct != null ? (
          <View
            testID={`league-summary.tick.${team.user_id}`}
            pointerEvents="none"
            style={[styles.consTick, { bottom: `${tickPct}%` }]}
          >
            <View style={styles.consTickDot} />
          </View>
        ) : null}
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
function TeamRow({ team, rank, active, totalLabel, onPress }: {
  team: PowerRankedTeam;
  rank: number;
  active: number;
  /** #279 — pick-equivalent label for `active`, passed only when it's known
   *  to equal the server's authoritative `total_value` (subset 'all', no
   *  position filter) AND the caller is targeted by `aggregate_tier_labels`.
   *  Undefined ⇒ render the numeric total exactly as before. */
  totalLabel?: string;
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
        <Text style={type.data}>
          {active > 0 ? (totalLabel ?? Math.round(active).toLocaleString('en-US')) : '—'}
        </Text>
        <Icon name="chevron-right" size={14} color={chalk.dim} />
      </View>
    </Pressable>
  );
}

// ── #169 season outlook ──────────────────────────────────────────────────
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

// The load-bearing honesty label. Weeks 0–5 this reads
// "Projected · preseason · beta"; from week 6 `meta.beta` is false and the
// ribbon shortens to "Projected" — never a bare authoritative percentage.
function betaRibbonLabel(meta: OutlookMeta): string {
  const parts = ['Projected'];
  if (meta.is_preseason) parts.push('preseason');
  if (meta.beta) parts.push('beta');
  return parts.join(' · ');
}

// ── Playoff bands (cross-client invariant) ───────────────────────────────
// Keys, labels, thresholds and colors are registered in
// docs/cross-client-invariants.md § "Playoff outlook bands" — web parity is a
// later item that MUST read them from there rather than re-derive them.
// Thresholds are the calibration verdict: the preseason table's ≥0.65 buckets
// realize 0.60–0.78 and its ≤0.35 buckets realize 0.0–0.5, so three bands are
// the finest granularity the evidence supports. Colors reuse the pos/warn/neg
// tercile-chip precedent already shipped on this screen (a data encoding, not
// chrome).
type PlayoffBand = 'likely' | 'tossup' | 'unlikely';
const PLAYOFF_BAND_LIKELY_MIN = 0.65;
const PLAYOFF_BAND_UNLIKELY_MAX = 0.35;
const PLAYOFF_BAND_LABEL: Record<PlayoffBand, string> = {
  likely: 'Likely',
  tossup: 'Toss-up',
  unlikely: 'Unlikely',
};
const PLAYOFF_BAND_COLOR: Record<PlayoffBand, string> = {
  likely: semantic.pos,
  tossup: semantic.warn,
  unlikely: semantic.neg,
};
function playoffBand(frac: number): PlayoffBand {
  const p = frac ?? 0;
  if (p >= PLAYOFF_BAND_LIKELY_MIN) return 'likely';
  if (p < PLAYOFF_BAND_UNLIKELY_MAX) return 'unlikely';
  return 'tossup';
}

// OPERATOR RISK OPTION — OFF, and it ships off (mockup frame C2, audit § open
// questions Q1). Turning this true replaces the week-6+ band chip with a
// playoff percentage rounded to 5%. It is defensible ONLY on the POOLED
// in-season calibration table, which is not stratified by week — an inference,
// not a measurement — so it is an operator's risk call and nobody else's. Two
// rules travel with it and are enforced below: the 5% rounding is load-bearing
// (never render 73%), and it never applies while `meta.beta` is true. Title
// odds stay banned either way. If the operator ever wants this on, the audit's
// recommendation is to make it a server-side presentation flag so it reverts
// without a client build; this constant is the local placeholder for that
// decision, not the decision.
const OUTLOOK_WEEK6_PERCENT_ENABLED = false;
// Load-bearing: the granularity IS the honesty claim.
const OUTLOOK_PERCENT_ROUNDING = 0.05;
function roundedPct(frac: number): string {
  const p = Math.max(0, Math.min(1, frac ?? 0));
  // Round in PERCENTAGE POINTS, not fractions: 0.75/0.05*0.05 is
  // 0.7500000000000001 in float, which would print "75.00000000000001%".
  const step = OUTLOOK_PERCENT_ROUNDING * 100;
  return `${Math.round((p * 100) / step) * step}%`;
}

function record(wins: number, losses: number, ties: number): string {
  const base = `${wins}-${losses}`;
  return ties > 0 ? `${base}-${ties}` : base;
}

// Week 6+ only: "4-2 · proj 9-5". `projected_wins` is a validated output
// post-BUG-1; the projected losses are the remainder of the regular season, so
// the pair always sums to `regular_season_weeks` and reads on the same scale
// the platform's own standings do. Ties are NOT projected (the simulator
// resolves every matchup), so a league with ties on the board shows them in
// the current record only.
function projectedRecord(team: OutlookTeam, meta: OutlookMeta): string {
  const games = meta.regular_season_weeks;
  const wins = Math.max(0, Math.min(games, Math.round(team.odds.projected_wins)));
  return `${wins}-${games - wins}`;
}

// The IDP / partial-coverage caption (mockup frame D). Renders ONLY when the
// board actually fed the odds (`affects_strength`) AND it could not price the
// whole starting lineup. A `trailing_scores` payload reports coverage with
// `affects_strength: false` — its odds never read a value board, so captioning
// it would be a false qualification. Copy states the limitation in LEAGUE
// terms ("8 defensive/kicker slots"), never payload terms.
function coverageCaption(meta: OutlookMeta): string | null {
  const cov = meta.priced_slot_coverage;
  if (!cov || !cov.affects_strength || cov.fraction >= 1) return null;
  const named = cov.unpriced_slots ?? [];
  const count = named.length || Math.max(0, cov.total_slots - cov.priced_slots);
  if (count === 0) return null;
  // Name only the slot families the payload actually named, so a kicker-only
  // league never reads "defensive" — and a payload that named none stays
  // generic rather than guessing at what they were.
  const hasKicker = named.some((s) => (s || '').toUpperCase() === 'K');
  const hasDefense = named.some((s) => (s || '').toUpperCase() !== 'K');
  const kind =
    hasKicker && hasDefense
      ? 'defensive/kicker'
      : hasKicker
        ? 'kicker'
        : hasDefense
          ? 'defensive'
          : 'lineup';
  const noun = count === 1 ? 'slot' : 'slots';
  return `Based on your offensive starters. This league starts ${count} ${kind} ${noun} FTF can't price yet, so the projection reads QB/RB/WR/TE strength only.`;
}

// THE ORDER IS THE PRODUCT. Sort by projected seed ascending so the rows
// literally are the projected standings — the payload's own ordering is by
// playoff_pct, which is nearly but not exactly the same thing, and "nearly"
// would put a team below the cutline above one that is projected to finish
// ahead of it. Ties resolve on playoff odds then roster_id so the order is
// deterministic across refetches. Shared by the section's rows AND the
// strip's "projected Nth" phrase (frame E) so strip-vs-section divergence is
// structurally impossible.
function orderOutlookTeams(teams: OutlookTeam[]): OutlookTeam[] {
  return [...teams].sort(
    (a, b) =>
      a.odds.projected_seed - b.odds.projected_seed ||
      b.odds.playoff_pct - a.odds.playoff_pct ||
      a.roster_id - b.roster_id,
  );
}

// Tiny ordinal helper for the strip's "projected Nth" phrase — 1st/2nd/3rd
// with the 11/12/13 exception (11th, never 11st). No library.
function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

// Frame E (#169): the collapsed one-liner — your own outlook at a glance,
// the full section one tap away. The label restates TickLabel's tick+label
// construction locally rather than reusing the component: TickLabel
// hardcodes accessibilityRole="header" (wrong inside a button) and takes no
// other a11y props. The Pressable is the accessible unit; the band chip
// inside is NOT separately accessible and carries NO testID (an accessible
// container collapses its subtree on iOS — flow-authoring law 3; the band is
// asserted via the strip's accessibilityLabel at lighting time). Chevron
// swaps, never rotates (AdjustmentsDisclosure precedent).
function OutlookStrip({
  you,
  rank,
  count,
  expanded,
  onToggle,
}: {
  you: OutlookTeam;
  rank: number;
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const band = playoffBand(you.odds.playoff_pct);
  return (
    <Pressable
      testID="league-summary.odds.strip"
      onPress={onToggle}
      accessibilityRole="button"
      accessibilityState={{ expanded }}
      accessibilityLabel={`Season outlook. ${PLAYOFF_BAND_LABEL[band]} to make the playoffs. Projected ${ordinal(rank)} of ${count}.`}
      style={({ pressed }) => [
        styles.oddsStrip,
        expanded && styles.oddsStripExpanded,
        pressed && { opacity: 0.6 },
      ]}
    >
      <View style={styles.oddsStripTick} />
      <Text style={styles.oddsStripLabel}>Season outlook</Text>
      <View style={[styles.oddsBand, { borderColor: PLAYOFF_BAND_COLOR[band] }]}>
        <Text style={[styles.oddsBandText, { color: PLAYOFF_BAND_COLOR[band] }]}>
          {PLAYOFF_BAND_LABEL[band]}
        </Text>
      </View>
      <Text style={[type.bodySm, styles.oddsStripPhrase]} numberOfLines={1}>
        {`for the playoffs · projected ${ordinal(rank)} of ${count}`}
      </Text>
      <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={chalk.dim} />
    </Pressable>
  );
}

// Strip-height loading shell (frame E degenerate state): label + a small
// warn spinner, no value text, not tappable. Stands in for the section's
// full-height loading branch in the collapsed default so the fold position
// doesn't jump when data lands. No testID — the ledger's
// `league-summary.odds.strip` names the tappable strip Pressable only.
function OutlookStripLoadingShell() {
  return (
    <View style={styles.oddsStrip}>
      <View style={styles.oddsStripTick} />
      <Text style={styles.oddsStripLabel}>Season outlook</Text>
      <View style={styles.oddsStripSpacer} />
      <ActivityIndicator size="small" color={semantic.warn} />
    </View>
  );
}

// Frame E owner (#169): decides strip vs. full section so the mount site
// stays one expression. Collapsed by default (absent storage entry);
// per-user, per-league memory via useOutlookStripExpanded. While expanded
// the strip stays mounted (it is the collapse affordance) and the unchanged
// SeasonOutlookSection renders directly beneath it. Degenerate states:
// loading with no data → the strip-height shell (plus the section's own
// loading branch when expanded); no data / empty league post-load → null,
// exactly as today; no `is_you` team → full section with no strip (the
// strip's content is "your" outlook — without an identified user row it has
// nothing true to say).
function OutlookStripAndSection({
  query,
  leagueId,
}: {
  query: UseQueryResult<LeagueOutlookResponse>;
  leagueId: string | null;
}) {
  const userId = useSession((s) => s.user?.user_id ?? null);
  const [expanded, setExpanded] = useOutlookStripExpanded(userId, leagueId);
  const data = query.data;

  if (query.isLoading && !data) {
    return (
      <>
        <OutlookStripLoadingShell />
        {expanded ? <SeasonOutlookSection query={query} /> : null}
      </>
    );
  }

  if (!data || data.teams.length === 0) return null;

  const you = data.teams.find((t) => t.is_you);
  if (!you) return <SeasonOutlookSection query={query} />;

  const rank = orderOutlookTeams(data.teams).findIndex((t) => t.is_you) + 1;
  const onToggle = () => {
    const next = !expanded;
    setExpanded(next);
    track(
      'outlook_strip_toggled',
      { league_id: leagueId, expanded: next },
      'LeagueSummary',
    );
  };

  return (
    <>
      <OutlookStrip
        you={you}
        rank={rank}
        count={data.teams.length}
        expanded={expanded}
        onToggle={onToggle}
      />
      {expanded ? <SeasonOutlookSection query={query} /> : null}
    </>
  );
}

// The merged season-outlook section: projected standings (row order + cutline)
// and playoff odds (band chip) as ONE thing. Rendered only when `outlook.odds`
// is on; degrades quietly (renders nothing) while the endpoint is dark/404s so
// the screen never shows a broken projection block.
function SeasonOutlookSection({
  query,
}: {
  query: UseQueryResult<LeagueOutlookResponse>;
}) {
  const data = query.data;

  if (query.isLoading && !data) {
    return (
      <View style={styles.oddsSection} testID="league-summary.odds.section">
        <TickLabel color={semantic.warn}>Season outlook</TickLabel>
        <View style={styles.oddsLoading}>
          <ActivityIndicator color={semantic.warn} />
        </View>
      </View>
    );
  }

  // No data (dark endpoint / error / empty league / pre_draft league with no
  // schedule) → render nothing. Better a missing section than a fabricated one.
  if (!data || data.teams.length === 0) return null;

  const { meta, teams } = data;
  const ordered = orderOutlookTeams(teams);
  // `meta.beta` is the two-state switch — see the header comment. It is false
  // only from `completed_weeks >= 6`.
  const showRecords = !meta.beta;
  const cutAfter =
    meta.playoff_slots > 0 && meta.playoff_slots < ordered.length
      ? meta.playoff_slots
      : null;
  const coverage = coverageCaption(meta);

  return (
    <View style={styles.oddsSection} testID="league-summary.odds.section">
      <View style={styles.oddsHead}>
        <TickLabel color={semantic.warn}>Season outlook</TickLabel>
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
        {[
          sourceCaption(meta.strength_source),
          'order = projected finish',
          // Only claim a playoff line when the payload actually has one.
          meta.playoff_slots > 0
            ? `top ${meta.playoff_slots} make the playoffs`
            : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </Text>

      <View style={styles.oddsList}>
        {ordered.map((t, idx) => (
          <React.Fragment key={t.roster_id}>
            <OutlookRow
              team={t}
              meta={meta}
              rank={idx + 1}
              showRecord={showRecords}
              last={idx === ordered.length - 1}
            />
            {cutAfter === idx + 1 ? (
              <View style={styles.oddsCutline} testID="league-summary.odds.cutline">
                <View style={styles.oddsCutRule} />
                <Text style={styles.oddsCutText}>
                  {`top ${meta.playoff_slots} make the playoffs`}
                </Text>
                <View style={styles.oddsCutRule} />
              </View>
            ) : null}
          </React.Fragment>
        ))}
      </View>

      {coverage ? (
        <View style={styles.oddsCoverage} testID="league-summary.odds.coverage-note">
          <Text style={[type.bodySm, styles.oddsCoverageText]}>{coverage}</Text>
        </View>
      ) : null}
    </View>
  );
}

// One team's row: order numeral (= projected finish), name + You badge, the
// record pair from week 6, and the band chip. Deliberately single-line — the
// whole league plus the top of the value chart has to fit one screen, which
// the old two-meter block made impossible. No projected seed decimal, no title
// odds, no raw playoff percentage.
function OutlookRow({
  team,
  meta,
  rank,
  showRecord,
  last,
}: {
  team: OutlookTeam;
  meta: OutlookMeta;
  rank: number;
  showRecord: boolean;
  last: boolean;
}) {
  const band = playoffBand(team.odds.playoff_pct);
  // The percentage option only ever exists past the beta gate (§7: "only from
  // week 6"), so `showRecord` — which IS `!meta.beta` — guards it too.
  const asPercent = OUTLOOK_WEEK6_PERCENT_ENABLED && showRecord;
  return (
    <View
      // The section already carries a bottom hairline fence; the last row's
      // own rule would double it.
      style={[styles.oddsRow, last && styles.oddsRowLast]}
      testID={`league-summary.odds.row.${team.roster_id}`}
    >
      <Text style={[styles.oddsRank, team.is_you && { color: ice.base }]}>{rank}</Text>
      <View style={styles.oddsNameRow}>
        <Text style={[type.title, styles.oddsName]} numberOfLines={1}>
          {team.display_name || team.username || String(team.roster_id)}
        </Text>
        {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
      </View>
      {showRecord ? (
        <Text style={[type.data, styles.oddsRecord]} numberOfLines={1}>
          {`${record(team.wins, team.losses, team.ties)} · proj ${projectedRecord(team, meta)}`}
        </Text>
      ) : null}
      {asPercent ? (
        <View style={styles.oddsPctChip} testID={`league-summary.odds.pct.${team.roster_id}`}>
          <Text style={[type.data, styles.oddsPctChipText]}>
            {roundedPct(team.odds.playoff_pct)}
          </Text>
        </View>
      ) : (
        <View
          style={[styles.oddsBand, { borderColor: PLAYOFF_BAND_COLOR[band] }]}
          testID={`league-summary.odds.band.${team.roster_id}`}
          accessibilityRole="text"
          accessibilityLabel={`${PLAYOFF_BAND_LABEL[band]} to make the playoffs`}
        >
          <Text style={[styles.oddsBandText, { color: PLAYOFF_BAND_COLOR[band] }]}>
            {PLAYOFF_BAND_LABEL[band]}
          </Text>
        </View>
      )}
    </View>
  );
}

// Honest unavailable state for a non-Sleeper league (audit surface #12). Today
// the section simply doesn't render for these leagues, which reads as a bug;
// one row explaining why is the whole fix. No retry affordance — there is
// nothing the user can do, and offering one would imply there is.
function OutlookUnsupportedRow() {
  return (
    <View style={styles.oddsSection} testID="league-summary.odds.unsupported">
      <TickLabel color={semantic.warn}>Season outlook</TickLabel>
      <Text style={[type.bodySm, styles.oddsSource]}>
        Season outlook needs schedule and scoring history — Sleeper leagues only for now.
      </Text>
    </View>
  );
}

// #302 — stack-header title rendered by this screen, because the title has to
// swap to the focused team's name. Deliberately a LOCAL copy of TabNav's
// private `HeaderTitle` (same Barlow-Condensed-caps style): importing it from
// '../navigation/TabNav' would close the cycle TabNav → LeagueSummaryScreen →
// TabNav. Native-stack `headerTitleStyle` can't express letterSpacing or
// textTransform, which is why the title is a component at all.
function StackHeaderTitle({ children }: { children: string }) {
  return (
    <Text
      testID="league-summary.header-title"
      numberOfLines={1}
      style={styles.headerTitle}
    >
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },

  // #302 — stack-header controls. Mirrors TabNav's `headerBack` / `headerTitle`
  // so the League tab's focused header is indistinguishable from every other
  // pushed sub-screen's: chevron + chalk label (never the greyed native
  // arrow), condensed-caps title scaled to the native bar.
  headerBack: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.xs,
    paddingRight: space.md,
  },
  headerBackText: { color: chalk.base, fontFamily: fonts.uiSemi, fontSize: 14 },
  headerTitle: {
    fontFamily: fonts.displaySemi,
    fontSize: 18,
    letterSpacing: 0.54,
    textTransform: 'uppercase',
    color: chalk.base,
  },
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

  // #248 — combined-bars overlay: fixed-height delta-chip row above every
  // column (baseline alignment), dashed ice ghost tick + end-cap dot inside
  // the column well, and the legend's tick swatch. Same dashed-hairline
  // construction as avgLine; ice is the established tick vocabulary.
  deltaWrap: {
    height: 15,
    marginBottom: 3,
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  deltaChip: {
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
  },
  deltaChipText: { ...type.data, fontSize: 9, lineHeight: 12, fontWeight: '700' },
  consTick: {
    position: 'absolute',
    left: -2,
    right: -2,
    height: 0,
    borderTopWidth: 2,
    borderStyle: 'dashed',
    borderColor: ice.base,
    zIndex: 2,
  },
  consTickDot: {
    position: 'absolute',
    right: -1,
    top: -3,
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: ice.base,
  },
  legendTickSwatch: {
    width: 14,
    height: 0,
    borderTopWidth: 2,
    borderStyle: 'dashed',
    borderColor: ice.base,
  },

  // #281 — the surviving (below-graph) key row sits one bodySm line-height
  // (18) lower now that the duplicate descriptive key text above the chart
  // is gone: operator's "move them together a line down".
  legend: { flexDirection: 'row', gap: space.lg, flexWrap: 'wrap', marginTop: space.md + 18 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendSwatch: { width: 9, height: 9, borderRadius: radii.xs },
  legendLabel: { ...type.bodySm, color: chalk.dim },
  // #260 — glyph stand-in for the delta chip's swatch (no single fill color
  // since the live chip is pos/neg-tinted; the legend entry stays neutral).
  legendDeltaGlyph: { ...type.data, fontSize: 9, fontWeight: '700', color: chalk.dim },

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
  // The label column became a stack when the W3 M-C provenance marker
  // joined it; with no marker it renders exactly as the single Text did.
  pickRowBody: { flex: 1, gap: space.xs },
  // #299 — the draft-capital rows are NOT PlayerCards, so they don't shrink
  // with the tiles. Brought into proportion with the new 32pt tile (was 40)
  // so the picks group doesn't read as conspicuously tall beside the roster.
  // `minHeight`, not `height`: with a MemberEnteredMarker in the body the row
  // is legitimately taller and must still grow.
  pickRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: 32,
    paddingHorizontal: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },

  // #169 season outlook section — sits between the basis toggle and the chart,
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

  // Frame E collapsed strip (#169) — full-width warn-tinted row, mounted
  // where the section mounts. Collapsed it keeps the section's bottom rhythm
  // (space.lg before the chart card); expanded the section follows directly,
  // so the margin tightens.
  oddsStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: semantic.warn,
    borderRadius: radii.sm,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    marginBottom: space.lg,
  },
  oddsStripExpanded: { marginBottom: space.md },
  // The label restates TickLabel's 3×14 tick + uppercase-label construction
  // in the warn voice (see OutlookStrip for why the component isn't reused).
  oddsStripTick: { width: 3, height: 14, backgroundColor: semantic.warn },
  oddsStripLabel: { ...type.label, color: semantic.warn },
  oddsStripPhrase: { flex: 1, color: chalk.dim },
  oddsStripSpacer: { flex: 1 },

  oddsList: { marginTop: space.md },
  // Single-line rows: numeral · name · (record from week 6) · band chip. The
  // whole league has to fit above the fold alongside the chart, which the
  // pre-v2 two-meter block made impossible.
  oddsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  oddsRowLast: { borderBottomWidth: 0 },
  oddsRank: {
    ...type.data,
    width: 22,
    textAlign: 'center',
    color: chalk.dim,
  },
  oddsNameRow: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  oddsName: { flexShrink: 1 },
  oddsRecord: { color: chalk.dim },
  // Band chip — border-in-encode-color, Chalkline badge construction. The
  // color IS the band (cross-client invariant), so the label always ships
  // alongside it: color alone would fail a color-blind read.
  oddsBand: {
    borderWidth: 1,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  oddsBandText: { ...type.label },
  // Operator risk option only (OUTLOOK_WEEK6_PERCENT_ENABLED, off).
  oddsPctChip: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  oddsPctChipText: { color: chalk.base },
  // The playoff cutline — a dashed rule is not available in RN, so the rule is
  // a hairline and the label carries the meaning.
  oddsCutline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
  },
  oddsCutRule: { flex: 1, height: 1, backgroundColor: ink.lineStrong },
  oddsCutText: { ...type.label, color: chalk.faint },
  // Partial-coverage (IDP) caption — warn rail, matching the mockup's
  // border-left treatment. No glyph: the chalkline icon set has no "!" and
  // emoji are banned.
  oddsCoverage: {
    marginTop: space.md,
    padding: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderLeftWidth: 2,
    borderLeftColor: semantic.warn,
    borderRadius: radii.sm,
  },
  oddsCoverageText: { color: chalk.dim },

  center: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.sm,
  },
  centerBody: { textAlign: 'center' },
});
