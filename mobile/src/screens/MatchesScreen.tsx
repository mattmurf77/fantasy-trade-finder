import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Pressable,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useIsFocused, useNavigation, useRoute } from '@react-navigation/native';
import { haptics } from '../utils/haptics';
import { track } from '../api/events';
import { getBaseUrl } from '../api/client';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';

import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { Button, Badge, Icon } from '../components/chalkline';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import PlayerContextMenu, { type PlayerMenuAction } from '../components/PlayerContextMenu';
import HelpSheet from '../components/HelpSheet';
import {
  getAllMatches,
  getAwaitingTrades,
  dismissMatch,
  dismissAwaitingTrade,
  getStandingOffers,
  revokeStandingOffer,
  type StandingOffer,
} from '../api/trades';
import MatchValueSection from '../components/MatchValueSection';
import {
  getAssetPrefs,
  setAssetPref,
  getLeagueCoverage,
  getLeagueSummary,
} from '../api/league';
import LeagueProgressModule from '../components/LeagueProgressModule';
import { shareInvite } from '../components/InviteLeaguematesBanner';
import { inviteSocialProof, INVITE_RATIONALE } from '../utils/inviteSocialProof';
import { useSession } from '../state/useSession';
import { usePushPriming } from '../state/usePushPriming';
import { useFlag } from '../state/useFeatureFlags';
import { registerScrollToTop } from '../navigation/scrollToTop';
import { relativeTime } from '../utils/relativeTime';
import {
  filterVisible,
  countsByLeague,
  matchHiddenKey,
  awaitingHiddenKey,
  matchRowKey,
  awaitingRowKey,
} from '../utils/matchesDerive';
import { readErrorCopy } from '../utils/verification';
import {
  guideV2Active,
  markGuideStepConsumed,
  requestGuideStep,
} from '../state/useGuide';
import { S as GUIDE } from '../components/analystScript';
import type { TradeMatch, AwaitingTrade, Player } from '../shared/types';

// Triage undo (S3 PRD-03, flag ux.swipe_undo): how long a dismiss's archive
// POST is held (and the Undo toast shown) before committing.
const UNDO_HOLD_MS = 5000;

type LeagueFilter = string | 'all';
// #362 — round → ordinal, for the standing-offer rows. v1 only ever writes
// round 1; the map exists because the column does.
const ROUND_WORDS: Record<number, string> = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' };
function roundWordFor(round: number): string {
  return ROUND_WORDS[round] ?? `round ${round}`;
}

// #362 — 'standing' is the manage surface for the caller's own standing
// offers. Deliberately THREE members and no more: Edit and Repost from
// mockup §5 are out of v1 (revoke-then-repost achieves both with no new
// route and no second entry point into the post-like sheet, and the
// writer's one-live-offer rule makes that sequence safe).
type Segment = 'mutual' | 'awaiting' | 'standing';

// Cross-league matches inbox. Pulls /api/trades/matches/all so users can
// see pending / accepted / declined matches regardless of which league is
// currently active in the session. A horizontally-scrollable filter row
// at the top lets them narrow to a single league client-side.
//
// On Accept: deep-link to the Sleeper trade-propose URL so the user can
// ratify the trade on Sleeper directly.
//
// The "Awaiting them" segment surfaces the gap between "I swiped accept"
// and "we both swiped accept" — trades the caller has liked that haven't
// yet been mirrored by the counterparty. Backed by /api/trades/awaiting.
export default function MatchesScreen() {
  const queryClient = useQueryClient();
  const navigation = useNavigation<any>();
  const leagues = useSession((s) => s.leagues);
  const activeLeague = useSession((s) => s.league);
  // P1-5 — needed for the invite link's `?ref=<username>` attribution.
  // Without it this surface would silently drop referrer attribution while
  // League Home kept it, and the two surfaces would not be comparable.
  const user = useSession((s) => s.user);
  const [toast, setToast] = useState<{
    msg: string;
    tone?: 'success' | 'warn' | 'error';
    holdMs?: number;
    action?: { label: string; onPress: () => void };
  } | null>(null);
  const [filterLeagueId, setFilterLeagueId] = useState<LeagueFilter>('all');
  const [segment, setSegment] = useState<Segment>('mutual');

  // #334 (R-1) — render-layer pending-dismiss suppression. Keys of rows a
  // dismiss has hidden; the visible-list memos below exclude them, so a
  // background cache rewrite (mount refetch, pull-to-refresh, reconnect,
  // league-switch invalidation, tab-press prefetch, TradesScreen's guide-v2
  // fetchQuery) can NEVER resurrect a dismissed tile — visibility no longer
  // depends on cache contents. A Set, not a single key: a previous
  // dismiss's POST can be in flight while a new dismiss is pending.
  // Lifecycle (R-2): added at tap time in handleDismiss[Awaiting] (both
  // flag branches); removed in undoDismiss (instant restore), in onError
  // (immediately — the snapshot restore honestly returned the row), and in
  // onSuccess (only AFTER the awaited reconcile refetch resolves — B-1).
  const [hiddenKeys, setHiddenKeys] = useState<ReadonlySet<string>>(() => new Set());
  function hideKey(k: string) {
    setHiddenKeys((prev) => {
      if (prev.has(k)) return prev;
      const next = new Set(prev);
      next.add(k);
      return next;
    });
  }
  function unhideKey(k: string) {
    setHiddenKeys((prev) => {
      if (!prev.has(k)) return prev;
      const next = new Set(prev);
      next.delete(k);
      return next;
    });
  }

  // ── Teardown-remediation flags (all default false — flag off is
  // byte-identical behavior) ──────────────────────────────────────────
  const swipeUndoOn = useFlag('ux.swipe_undo');           // S3 PRD-03
  const inlineHomeOn = useFlag('calc.inline_home');       // D-158 B1
  const menuOn = useFlag('ux.player_context_menu');       // S3 PRD-02
  // S1 PRD-05 (flag ux.retap_active_tab) — focused Matches re-tap scrolls
  // the active segment's list to top. Only one FlatList is mounted at a
  // time (segment toggle), so scroll whichever ref is live.
  const retapOn = useFlag('ux.retap_active_tab');
  const matchesListRef = useRef<FlatList<any> | null>(null);
  const awaitingListRef = useRef<FlatList<any> | null>(null);
  useEffect(
    () =>
      retapOn
        ? registerScrollToTop('Matches', () => {
            matchesListRef.current?.scrollToOffset({ offset: 0, animated: true });
            awaitingListRef.current?.scrollToOffset({ offset: 0, animated: true });
          })
        : undefined,
    [retapOn],
  );
  const emptyCtasOn = useFlag('ux.empty_state_ctas');     // S4 PRD-05
  const helpOn = useFlag('ux.help_surface');              // S4 PRD-01
  const cleanupOn = useFlag('visual.chalkline_cleanup');  // S2 PRD-04 ride-along

  // S4 PRD-01 — "How matching works" sheet from the empty state.
  const [matchingHelpOpen, setMatchingHelpOpen] = useState(false);
  // S3 PRD-02 — shared player context menu target.
  const [menuTarget, setMenuTarget] = useState<{
    leagueId: string;
    player: Player;
    side: 'give' | 'receive';
  } | null>(null);

  // FB-91 — the League tab's Matches tiles deep-link into a specific
  // segment: navigate('Matches', { segment, at }). `at` (a timestamp)
  // changes on every tap so re-tapping the same tile still lands on the
  // requested segment after the user has toggled away.
  //
  // #307 (frozen contract, wave-league @ 6368e31 §4.3) — the param set gains
  // an optional `leagueId`: a producer (League home's Matches tiles) scopes
  // this inbox to its league. Lenient consumer: an id not in filterChips
  // degrades to the existing "No matches in this league yet" empty state —
  // never a crash, never a silent ignore. Absent/empty leagueId leaves
  // filterLeagueId untouched, so push-tap routing and plain tab presses are
  // unaffected by construction. Keying on `at` preserves the re-tap
  // contract: tile → manually toggle the chip to "All" → tile again still
  // rescopes, because `at` changed even though leagueId didn't (S-10).
  const route = useRoute<any>();
  // ── Guided Onboarding v2 (flag onboarding.guide_v2) ──────────────────
  // `N6.1`'s primary CTA navigates here as `{segment:'awaiting', at,
  // guidedArrival:'n6.1'}` — the chain marker that (a) sources the
  // `awaiting_segment_viewed` funnel row and (b) suppresses `N9`, whose
  // teaching that arrival has already done.
  const guidedArrival: string | null =
    typeof route.params?.guidedArrival === 'string'
      ? route.params.guidedArrival
      : null;
  // How the CURRENT awaiting episode was entered. Latched when the segment
  // changes rather than read at emit time: route params outlive the episode
  // (they stay on the route after a manual toggle back and forth), so
  // reading them at emit time would report `guide` for a later tab visit.
  const awaitingSourceRef = useRef<'guide' | 'tab'>('tab');
  useEffect(() => {
    const s = route.params?.segment;
    if (s === 'mutual' || s === 'awaiting') setSegment(s);
    if (s === 'awaiting') {
      awaitingSourceRef.current = guidedArrival === 'n6.1' ? 'guide' : 'tab';
    }
    const lid = route.params?.leagueId;
    if (typeof lid === 'string' && lid) setFilterLeagueId(lid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.params?.segment, route.params?.leagueId, route.params?.at]);

  // `awaiting_segment_viewed {source}` — the N6.1 funnel step (NOT its
  // adoption event: N6.1's own CTA causes this, so reading it as adoption
  // would manufacture a ~100% win — PRD §5.3). One row per episode: the
  // segment being on screen while the tab is focused. Toggling away and
  // back is a genuine second view; a re-render is not.
  //
  // `source` is `guide | tab` only. The taxonomy registers `push` as well,
  // but no push payload routes to this segment today — `routeNotificationTap`
  // passes `{match_id, src:'push', ts}` and never a `segment`
  // (`utils/deepLinks.ts`), so every push arrival lands on `mutual` and any
  // subsequent awaiting view is a real toggle. Emitting `push` for it would
  // be a false attribution; the value stays reserved for a push path that
  // actually targets the segment.
  const isFocused = useIsFocused();
  // Reactive read of the owning flag. `guideV2Active()` stays the gate (it
  // also carries the `onboarding.v2` master switch); this exists so the two
  // effects below re-run if the flag payload lands after this screen mounts
  // — a cold start whose first destination is this tab (a push tap).
  const guideV2Flag = useFlag('onboarding.guide_v2');
  const awaitingViewedRef = useRef(false);
  useEffect(() => {
    if (!guideV2Active()) return;
    if (!isFocused || segment !== 'awaiting') {
      awaitingViewedRef.current = false;
      return;
    }
    if (awaitingViewedRef.current) return;
    awaitingViewedRef.current = true;
    track('awaiting_segment_viewed', { source: awaitingSourceRef.current }, 'Matches');
  }, [isFocused, segment, guideV2Flag]);

  // `N9` — the first-visit floor for this screen (O-7). Requested on every
  // focus; the engine's `once` + `maxDisplayCount` refuse the repeats, so
  // "first visit ever" needs no second persistence layer here. A guided
  // arrival consumes it instead: N6.1 already taught this moment, and
  // consuming (rather than dropping) keeps the beat from ambushing the user
  // on their next, unguided visit.
  useFocusEffect(
    useCallback(() => {
      if (!guideV2Active()) return;
      if (guidedArrival) {
        // `'matched'` is the engine's "a call site decided this teaching
        // already happened" value on the closed `GuideBlockedBy` union
        // (useGuide.ts) — it marks the step seen + retired and measures the
        // suppression, with no bubble and no `guide_step_shown`.
        markGuideStepConsumed('n9', 'matched');
        return;
      }
      requestGuideStep(GUIDE.n9());
    }, [guidedArrival, guideV2Flag]),
  );

  // Stable query key — `'all'` not the active league. The endpoint returns
  // every-league results, so league switching shouldn't invalidate this
  // cache. Filtering is done client-side below.
  // `placeholderData: (prev) => prev` keeps the previous list visible
  // across refetches so the screen doesn't blank on re-entry.
  const matchesQuery = useQuery({
    queryKey: ['matches', 'all'],
    queryFn:  getAllMatches,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });

  // Awaiting trades — fetched on MOUNT (#335 R-7), not lazily on first
  // segment open: the segment pill and chip counts must be correct on
  // landing, before the segment is ever tapped. Costs one extra GET per
  // Matches visit for users who never open the segment (an endpoint already
  // called opportunistically on TradesScreen focus, bounded by staleTime).
  // Same cross-league scope as matches/all; client-side league filter is
  // reused. `placeholderData` for parity with matchesQuery — no blank on
  // re-entry.
  const awaitingQuery = useQuery({
    queryKey: ['awaiting-trades'],
    queryFn:  getAwaitingTrades,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });

  // #229/#234 — the mutual empty state mounts the compact
  // LeagueProgressModule for the ACTIVE league (same story League home
  // tells; the two surfaces can't disagree). Same query keys/staleTime as
  // LeagueScreen, so the cache is shared and this is usually free.
  const activeLeagueId = activeLeague?.league_id || null;
  const leagueSummaryQuery = useQuery({
    queryKey: ['league-summary', activeLeagueId],
    queryFn:  () => getLeagueSummary(activeLeagueId!),
    enabled:  !!activeLeagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const leagueCoverageQuery = useQuery({
    queryKey: ['league-coverage', activeLeagueId],
    queryFn:  () => getLeagueCoverage(activeLeagueId!),
    enabled:  !!activeLeagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Dismiss = archive the match from THIS user's inbox. Persisted + per-user
  // + ELO-neutral (see /api/trades/matches/:id/dismiss). Replaces the old
  // accept/decline dispositions on mutual matches — the real "do the trade"
  // action is now the Send-in-Sleeper button, so the only inbox verb left is
  // "clear it."
  const dismissMutation = useMutation({
    mutationFn: (id: string) => dismissMatch(id),
    onMutate: async (id) => {
      // #334 (R-3) — kill any in-flight list read so a response that left
      // the server pre-dismiss can't overwrite the optimistic removal.
      await queryClient.cancelQueries({ queryKey: ['matches', 'all'] });
      // Optimistic — drop the match from the list so the UI feels instant.
      const prev = queryClient.getQueryData<TradeMatch[]>(['matches', 'all']);
      if (prev) {
        queryClient.setQueryData(
          ['matches', 'all'],
          prev.filter((m) => m.match_id !== id),
        );
      }
      return { prev };
    },
    onError: (_err, id, ctx) => {
      // #334 (R-2) — unhide IMMEDIATELY: the snapshot restore below
      // honestly returns the row, and it must render at once.
      unhideKey(matchHiddenKey(id));
      if (ctx?.prev) queryClient.setQueryData(['matches', 'all'], ctx.prev);
      // Undo path (ux.swipe_undo): the row was removed at TAP time, so
      // ctx.prev here is the already-filtered list — refetch to restore
      // the failed-dismiss row instead of leaving it invisibly archived.
      if (swipeUndoOn) {
        queryClient.invalidateQueries({ queryKey: ['matches', 'all'] });
      }
      setToast({ msg: 'Could not dismiss — try again', tone: 'warn' });
    },
    onSuccess: async (_res, id) => {
      // Dismissed matches are gone server-side, so refetch to reconcile
      // (the optimistic removal already hid it locally).
      //
      // #334 (R-2, B-1) — ORDERED unhide: a GET that started after
      // onMutate's cancelQueries (pull-to-refresh / reconnect / guide-v2
      // fetchQuery racing the POST round-trip) can read the row PRE-commit
      // server-side and resurrect the cache. Unhiding before that cache is
      // reconciled would re-show the tile for one round-trip — the exact
      // #334 symptom. `invalidateQueries`' promise settles when its refetch
      // completes (and settles even if the refetch fails, so no tile is
      // hidden forever) — only then is the hidden key cleared, against a
      // post-commit list.
      await queryClient.invalidateQueries({ queryKey: ['matches', 'all'] });
      unhideKey(matchHiddenKey(id));
    },
  });

  // #318 — mirror of dismissMutation, against the awaiting cache. The like
  // is keyed by the row tuple (no single id — see dismissAwaitingTrade); the
  // cache row is keyed `${league_id}:${trade_id}` (the list's keyExtractor).
  // Server-fired analytics (`awaiting_trade_dismissed`) — no client event.
  const dismissAwaitingMutation = useMutation({
    mutationFn: (row: AwaitingTrade) => dismissAwaitingTrade(row),
    onMutate: async (row) => {
      // #334 (R-3) — same cancellation hygiene as the mutual mutation.
      await queryClient.cancelQueries({ queryKey: ['awaiting-trades'] });
      const prev = queryClient.getQueryData<AwaitingTrade[]>(['awaiting-trades']);
      if (prev) {
        queryClient.setQueryData(
          ['awaiting-trades'],
          prev.filter((a) => `${a.league_id}:${a.trade_id}` !== `${row.league_id}:${row.trade_id}`),
        );
      }
      return { prev };
    },
    onError: (_err, row, ctx) => {
      // #334 (R-2) — unhide immediately; the restore below is honest.
      unhideKey(awaitingHiddenKey(row.league_id, row.trade_id));
      if (ctx?.prev) queryClient.setQueryData(['awaiting-trades'], ctx.prev);
      // Undo path: same reasoning as the mutual mutation above — the row was
      // removed at TAP time, so ctx.prev is the already-filtered list;
      // refetch to honestly restore the failed-dismiss row.
      if (swipeUndoOn) {
        queryClient.invalidateQueries({ queryKey: ['awaiting-trades'] });
      }
      setToast({ msg: 'Could not dismiss — try again', tone: 'warn' });
    },
    onSuccess: async (_res, row) => {
      // #334 (R-2, B-1) — ordered unhide; see dismissMutation.onSuccess.
      await queryClient.invalidateQueries({ queryKey: ['awaiting-trades'] });
      unhideKey(awaitingHiddenKey(row.league_id, row.trade_id));
    },
  });

  // ── Dismiss undo (S3 PRD-03, flag ux.swipe_undo) ─────────────────────
  // Same design decision as the Trades pass-undo: the archive POST is
  // DELAYED for UNDO_HOLD_MS rather than reversed (there is no un-dismiss
  // endpoint — #318's route is idempotent, so the delayed POST is also
  // retry-safe). The row is removed optimistically at tap time; Undo
  // restores the snapshotted list and drops the pending write. A second
  // dismiss, or unmount, flushes the pending one first. #318 generalizes
  // the holder: `kind` selects which cache + mutation the flush targets.
  const pendingDismissRef = useRef<
    | {
        kind: 'match';
        id: string;
        prev: TradeMatch[] | undefined;
        timer: ReturnType<typeof setTimeout>;
      }
    | {
        kind: 'awaiting';
        row: AwaitingTrade;
        prev: AwaitingTrade[] | undefined;
        timer: ReturnType<typeof setTimeout>;
      }
    | null
  >(null);

  function flushPendingDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    if (p.kind === 'match') dismissMutation.mutate(p.id);
    else dismissAwaitingMutation.mutate(p.row);
  }
  const flushPendingDismissRef = useRef(flushPendingDismiss);
  flushPendingDismissRef.current = flushPendingDismiss;

  function undoDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    if (p.kind === 'match') {
      // #334 (R-2) — clear the hidden key so the snapshot restore renders
      // in the same frame.
      unhideKey(matchHiddenKey(p.id));
      if (p.prev) queryClient.setQueryData(['matches', 'all'], p.prev);
      track('match_dismiss_undone', { match_id: p.id }, 'Matches');
    } else {
      unhideKey(awaitingHiddenKey(p.row.league_id, p.row.trade_id));
      // Awaiting undo fires nothing — the mutual path's event above is
      // already unregistered/dropped by ingest; we don't replicate a dead
      // emitter (plan § Analytics, waived in writing).
      if (p.prev) queryClient.setQueryData(['awaiting-trades'], p.prev);
    }
  }

  // Commit any pending dismiss on unmount — leaving ends the undo window.
  useEffect(
    () => () => {
      flushPendingDismissRef.current();
    },
    [],
  );

  async function handleDismiss(m: TradeMatch) {
    haptics.selection();
    // Double-fire guard: the tile's Dismiss can only be pending once.
    // (Moved above the flag branch for #334; with the flag off the ref is
    // always null, so this stays a no-op there.)
    if (
      pendingDismissRef.current?.kind === 'match'
      && pendingDismissRef.current.id === m.match_id
    ) return;
    // #334 (R-1/R-2) — hide at TAP time, in BOTH flag branches: the tile
    // leaves in this frame and no cache rewrite can bring it back.
    hideKey(matchHiddenKey(m.match_id));
    if (!swipeUndoOn) {
      dismissMutation.mutate(m.match_id);
      return;
    }
    flushPendingDismiss();
    // #334 (R-3) — kill any in-flight list read before snapshotting, so the
    // snapshot can't be overwritten by a pre-dismiss payload. Re-flush after
    // the await: if another dismiss landed during it, its hold must commit
    // before we overwrite the single-slot ref below.
    await queryClient.cancelQueries({ queryKey: ['matches', 'all'] });
    flushPendingDismiss();
    // Optimistic removal now; the POST waits out the undo window.
    const prev = queryClient.getQueryData<TradeMatch[]>(['matches', 'all']);
    if (prev) {
      queryClient.setQueryData(
        ['matches', 'all'],
        prev.filter((x) => x.match_id !== m.match_id),
      );
    }
    pendingDismissRef.current = {
      kind: 'match',
      id: m.match_id,
      prev,
      timer: setTimeout(() => flushPendingDismissRef.current(), UNDO_HOLD_MS),
    };
    setToast({
      msg: 'Dismissed',
      tone: 'success',
      holdMs: UNDO_HOLD_MS,
      action: { label: 'Undo', onPress: undoDismiss },
    });
  }

  // #318 — mirror of handleDismiss for the awaiting segment. Honest UI
  // guarantees are identical: optimistic removal is reversed on error (S-9),
  // and the delayed-POST undo means a post-window failure refetches so the
  // row reappears rather than staying invisibly un-dismissed.
  async function handleDismissAwaiting(a: AwaitingTrade) {
    haptics.selection();
    const rowKey = `${a.league_id}:${a.trade_id}`;
    // Double-fire guard, keyed the way the list is keyed. (Above the flag
    // branch for #334; a no-op with the flag off — the ref is always null.)
    if (
      pendingDismissRef.current?.kind === 'awaiting'
      && `${pendingDismissRef.current.row.league_id}:${pendingDismissRef.current.row.trade_id}` === rowKey
    ) return;
    // #334 (R-1/R-2) — hide at TAP time, in both flag branches.
    hideKey(awaitingHiddenKey(a.league_id, a.trade_id));
    if (!swipeUndoOn) {
      dismissAwaitingMutation.mutate(a);
      return;
    }
    flushPendingDismiss();
    // #334 (R-3) — same cancel-then-re-flush as handleDismiss above.
    await queryClient.cancelQueries({ queryKey: ['awaiting-trades'] });
    flushPendingDismiss();
    const prev = queryClient.getQueryData<AwaitingTrade[]>(['awaiting-trades']);
    if (prev) {
      queryClient.setQueryData(
        ['awaiting-trades'],
        prev.filter((x) => `${x.league_id}:${x.trade_id}` !== rowKey),
      );
    }
    pendingDismissRef.current = {
      kind: 'awaiting',
      row: a,
      prev,
      timer: setTimeout(() => flushPendingDismissRef.current(), UNDO_HOLD_MS),
    };
    setToast({
      msg: 'Dismissed',
      tone: 'success',
      holdMs: UNDO_HOLD_MS,
      action: { label: 'Undo', onPress: undoDismiss },
    });
  }

  // #319 — hand a Matches row to the manual calculator, prefilled (#190
  // contract). Matches is a cross-league inbox but TradeCalculatorScreen
  // hard-wires In-league mode to the ACTIVE league, so a cross-league row
  // switches leagues FIRST via useSession.switchLeague — the same machinery
  // the TopBar switcher uses (it re-runs the backend league handshake, then
  // persists the new active league; plain setLeague would leave the server
  // session bound to the old league). A row whose league is no longer in the
  // cached list toasts honestly instead of navigating into the wrong league.
  async function handleOpenInCalc(row: {
    league_id: string;
    counterparty_user_id: string;
    my_side_player_ids: string[];
    their_side_player_ids: string[];
  }) {
    haptics.selection();
    // App-wide convention name (TradesScreen's #190 emitter). Known gap,
    // stated honestly: not yet in ALLOWED_CLIENT_EVENTS, so ingest
    // accepts-and-drops it today — as it does the existing TradesScreen
    // emitter. Registration is a flagged repo-wide defect; firing the
    // conventional name lights this up the moment registration lands.
    track('trade_edit_in_calculator_tapped', undefined, 'Matches');
    if (row.league_id !== activeLeagueId) {
      const target = leagues.find((l) => l.league_id === row.league_id);
      if (!target) {
        setToast({ msg: 'Switch to that league to open the calculator', tone: 'warn' });
        return;
      }
      try {
        await useSession.getState().switchLeague({
          league_id: target.league_id,
          league_name: target.name,
        });
      } catch {
        setToast({ msg: 'Could not switch leagues — try again', tone: 'warn' });
        return;
      }
    }
    // D-158 review fix B1 — with the inline home on, the pushed page has no
    // In-league mode to land a prefill in (it silently dropped the package);
    // the guided landing hosts the canvas now, so the package rides a route
    // param that TradesScreen consumes into `loadCanvasPrefill`.
    if (inlineHomeOn) {
      navigation.navigate('Trades', {
        screen: 'TradesHome',
        params: {
          canvasPrefill: {
            opponentId: row.counterparty_user_id,
            give: row.my_side_player_ids,
            receive: row.their_side_player_ids,
          },
          canvasPrefillSeq: Date.now(),
        },
      });
      return;
    }
    // TradeCalculator is registered in the Trades tab's stack — from the
    // Matches tab the navigate must be nested (same pattern as the
    // empty-state "Find a trade" CTA below).
    navigation.navigate('Trades', {
      screen: 'TradeCalculator',
      params: {
        prefill: {
          opponentUserId: row.counterparty_user_id,
          giveIds: row.my_side_player_ids,
          receiveIds: row.their_side_player_ids,
        },
      },
    });
  }

  const allMatches: TradeMatch[] = matchesQuery.data || [];
  const allAwaiting: AwaitingTrade[] = awaitingQuery.data || [];

  // S4 PRD-04 (ux.prompt_arbiter) — want-it moment for the push primer:
  // the first mutual match seen this session is the "get pinged when a
  // match drops" payoff made concrete. No-op unless the arbiter flag is on
  // AND a backoff-suppressed primer is parked (see usePushPriming).
  const wantItFiredRef = useRef(false);
  useEffect(() => {
    if (wantItFiredRef.current || allMatches.length === 0) return;
    wantItFiredRef.current = true;
    usePushPriming.getState().wantItMoment();
  }, [allMatches.length]);

  // ── Untouchables (feedback #95, flag trade.preference_lists) ─────────
  // Long-press a player on the YOU SEND side to mark/unmark them
  // untouchable — the trade engine then never offers them from your
  // roster. Matches are cross-league, so prefs are fetched per league
  // present in either segment; `combine` memoizes the league→Set map so
  // TradeCard's memo isn't busted every render.
  // ── #362 standing offers — the manage surface (flag trade.standing_offers)
  // Cross-league, like the rest of this screen. Two honesty constraints come
  // straight from the route's contract:
  //   * `league_name` is OMITTED for rows outside the session's current
  //     league — the server does not guess a name, so neither do we.
  //   * `stale` (the offered player has left the sender's roster) is only
  //     COMPUTED for the session league; cross-league rows always report
  //     `false`, which means "not checked here", NOT "verified live". So
  //     `stale` is only ever rendered when true, and no row anywhere claims
  //     to have been verified. `days_left` and `revoked_at` are computed for
  //     every row, so the Active / Expired split is honest everywhere.
  const standingOffersOn = useFlag('trade.standing_offers');
  const standingQuery = useQuery({
    queryKey: ['standing-offers', 'all'],
    queryFn: () => getStandingOffers(),
    enabled: standingOffersOn,
    staleTime: 60_000,
    retry: false,
  });

  const untouchablesEnabled = useFlag('trade.preference_lists');
  const prefLeagueIds = useMemo(() => {
    const ids = new Set<string>();
    allMatches.forEach((m) => m.league_id && ids.add(m.league_id));
    allAwaiting.forEach((a) => a.league_id && ids.add(a.league_id));
    return Array.from(ids).sort();
  }, [allMatches, allAwaiting]);

  const untouchablesByLeague = useQueries({
    queries: prefLeagueIds.map((lid) => ({
      queryKey: ['asset-prefs', lid],
      queryFn: () => getAssetPrefs(lid),
      staleTime: 60_000,
      enabled: untouchablesEnabled,
    })),
    combine: (results) => {
      const map = new Map<string, Set<string>>();
      results.forEach((r, i) => {
        if (r.data) map.set(prefLeagueIds[i], new Set(r.data.untouchables || []));
      });
      return map;
    },
  });

  const untouchableMutation = useMutation({
    mutationFn: ({ leagueId, playerId, list }: {
      leagueId: string;
      playerId: string;
      list: 'untouchable' | 'none';
    }) => setAssetPref(leagueId, playerId, list),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', vars.leagueId] });
      setToast({
        msg: vars.list === 'untouchable'
          ? 'Marked untouchable — never offered in trade ideas'
          : 'Untouchable removed',
        tone: 'success',
      });
    },
    onError: () => {
      setToast({ msg: 'Could not update untouchable — try again', tone: 'warn' });
    },
  });

  function handleToggleUntouchable(leagueId: string, p: Player) {
    if (untouchableMutation.isPending) return;
    haptics.selection();
    const marked = untouchablesByLeague.get(leagueId)?.has(p.id) ?? false;
    // S3 PRD-02 discoverability metric — gated so flag-off emits nothing new.
    if (menuOn) {
      track('untouchable_toggled', { marked: !marked }, 'Matches');
    }
    untouchableMutation.mutate({
      leagueId,
      playerId: p.id,
      list: marked ? 'none' : 'untouchable',
    });
  }

  // #334 (R-1) — the rendered lists derive through the shared hidden-aware
  // filter: league scope AND pending-dismiss suppression in one predicate.
  const visibleMatches = useMemo(
    () => filterVisible(allMatches, filterLeagueId, hiddenKeys, matchRowKey),
    [allMatches, filterLeagueId, hiddenKeys],
  );

  const visibleAwaiting = useMemo(
    () => filterVisible(allAwaiting, filterLeagueId, hiddenKeys, awaitingRowKey),
    [allAwaiting, filterLeagueId, hiddenKeys],
  );

  // #335 (R-8/R-10) — count inputs: hidden-aware, league-UNfiltered arrays
  // (league chips count the whole segment, whatever chip is active). `null`
  // while the list's first fetch is unresolved — a pill/chip then renders
  // NO count, never a fabricated 0. Same helper family as the visible
  // lists, so a dismissed tile and its counts move in the same frame.
  const hiddenAwareMatches = useMemo(
    () => (matchesQuery.data === undefined
      ? null
      : filterVisible(matchesQuery.data, 'all', hiddenKeys, matchRowKey)),
    [matchesQuery.data, hiddenKeys],
  );
  const hiddenAwareAwaiting = useMemo(
    () => (awaitingQuery.data === undefined
      ? null
      : filterVisible(awaitingQuery.data, 'all', hiddenKeys, awaitingRowKey)),
    [awaitingQuery.data, hiddenKeys],
  );
  const matchCounts = useMemo(
    () => countsByLeague(hiddenAwareMatches ?? undefined),
    [hiddenAwareMatches],
  );
  const awaitingCounts = useMemo(
    () => countsByLeague(hiddenAwareAwaiting ?? undefined),
    [hiddenAwareAwaiting],
  );
  // Segment pills count rows under the ACTIVE league filter (the list the
  // pill would show) — literally the rendered array's length, so pill and
  // list can never disagree.
  const mutualPillCount =
    hiddenAwareMatches === null ? null : visibleMatches.length;
  const awaitingPillCount =
    hiddenAwareAwaiting === null ? null : visibleAwaiting.length;
  // #362 — the standing-offer rows, split Active / Expired.
  //
  // REVOKED rows are dropped entirely rather than grouped: the user killed
  // them, and a "revoked" bucket is a list of things they already decided
  // they were done with. A STALE offer (its player has left the roster) is
  // dead regardless of the clock — the injector enforces exactly that — so
  // it groups with Expired, never with Active.
  const allStanding = standingQuery.data ?? [];
  const standingRows = useMemo(() => {
    const live: StandingOffer[] = [];
    const dead: StandingOffer[] = [];
    for (const o of allStanding) {
      if (o.revoked_at) continue;
      if (filterLeagueId !== 'all' && o.league_id !== filterLeagueId) continue;
      (o.days_left > 0 && !o.stale ? live : dead).push(o);
    }
    return { live, dead };
  }, [allStanding, filterLeagueId]);
  const standingCounts = useMemo(
    () =>
      countsByLeague(
        standingQuery.data === undefined
          ? undefined
          : standingQuery.data.filter((o) => !o.revoked_at),
      ),
    [standingQuery.data],
  );
  const standingPillCount =
    standingQuery.data === undefined
      ? null
      : standingRows.live.length + standingRows.dead.length;

  // League chips count rows in the ACTIVE segment.
  const segmentChipCounts =
    segment === 'mutual'
      ? matchCounts
      : segment === 'awaiting'
        ? awaitingCounts
        : standingCounts;
  const segmentChipTotal =
    segment === 'mutual'
      ? (hiddenAwareMatches === null ? null : hiddenAwareMatches.length)
      : segment === 'awaiting'
        ? (hiddenAwareAwaiting === null ? null : hiddenAwareAwaiting.length)
        : (standingQuery.data === undefined
            ? null
            : standingQuery.data.filter((o) => !o.revoked_at).length);

  // Revoke — the only action on a standing-offer row (R-10). No Edit, no
  // Repost: both would need a second entry point into the post-like sheet
  // for no capability revoke-then-repost does not already give.
  const revokeMutation = useMutation({
    mutationFn: (offer: StandingOffer) => revokeStandingOffer(offer.offer_id),
    onSuccess: (_res, offer) => {
      queryClient.invalidateQueries({ queryKey: ['standing-offers', 'all'] });
      queryClient.invalidateQueries({ queryKey: ['standing-offers', offer.league_id] });
      // Counts only, never id lists. `age_days` answers "did users broadcast
      // more widely than they meant?" — a revoke inside 48h is the signal.
      const created = Date.parse(offer.created_at);
      track(
        'standing_offer_revoked',
        {
          age_days: Number.isFinite(created)
            ? Math.max(0, Math.floor((Date.now() - created) / 86_400_000))
            : 0,
        },
        'Matches',
      );
      setToast({ msg: 'Standing offer revoked', tone: 'success' });
    },
    onError: () => {
      setToast({ msg: 'Could not revoke that offer — try again', tone: 'warn' });
    },
  });

  // Filter chips: "All" + one per league. Default to the cached session
  // leagues so chips are stable even if the user has matches in leagues no
  // longer in their cache. Awaiting trades can also surface unknown
  // leagues — fold both lists into the "extras" set so neither segment is
  // missing chips for the leagues it actually contains.
  const filterChips = useMemo(() => {
    const seenIds = new Set(leagues.map((l) => l.league_id));
    const extrasMatches = allMatches
      .filter((m) => !seenIds.has(m.league_id))
      .map((m) => ({ id: m.league_id, name: m.league_name || 'Unknown league' }));
    const extrasAwaiting = allAwaiting
      .filter((a) => !seenIds.has(a.league_id))
      .map((a) => ({ id: a.league_id, name: a.league_name || 'Unknown league' }));
    const cachedChips = leagues.map((l) => ({ id: l.league_id, name: l.name }));
    // Dedupe extras by id
    const seenExtra = new Set<string>();
    const uniqueExtras = [...extrasMatches, ...extrasAwaiting].filter((e) => {
      if (seenExtra.has(e.id)) return false;
      seenExtra.add(e.id);
      return true;
    });
    return [{ id: 'all' as const, name: 'All' }, ...cachedChips, ...uniqueExtras];
  }, [leagues, allMatches, allAwaiting]);

  const filteredLeagueName =
    filterLeagueId === 'all'
      ? null
      : leagues.find((l) => l.league_id === filterLeagueId)?.name
        || allMatches.find((m) => m.league_id === filterLeagueId)?.league_name
        || allAwaiting.find((a) => a.league_id === filterLeagueId)?.league_name
        || 'this league';

  // #229/#234 — compact-module inputs for the mutual empty state. Rendered
  // only for the active league's view ('All' or its own filter chip) and
  // only once BOTH league reads have confirmed data (no fabricated counts).
  const matchesSummary = leagueSummaryQuery.data;
  const matchesCoverage = leagueCoverageQuery.data;
  const emptyModule =
    (filterLeagueId === 'all' || filterLeagueId === activeLeagueId)
    && matchesSummary
    && matchesCoverage
      ? {
          rankedMates: matchesCoverage.ranked || 0,
          totalTeams:
            matchesSummary.total_teams
            || (matchesSummary.leaguemates_total || 0) + 1,
        }
      : null;

  const activeQuery =
    segment === 'mutual'
      ? matchesQuery
      : segment === 'awaiting'
        ? awaitingQuery
        : standingQuery;
  const isLoading = activeQuery.isLoading;
  const isError   = activeQuery.isError;
  const isFetching = activeQuery.isFetching && !activeQuery.isLoading;
  const onRefresh = () => {
    activeQuery.refetch();
  };

  // ── P1-5 (audit A-14) — invite on the mutual-empty state ─────────────
  // The screen that TELLS a user they need more leaguemates had no way to
  // get more leaguemates. Counts come from the same ['league-summary',
  // activeLeagueId] query key League Home uses, so the two surfaces share
  // one cache entry and can never quote different numbers.
  const inviteTotalMates =
    typeof matchesSummary?.leaguemates_total === 'number' ? matchesSummary.leaguemates_total : 0;
  const inviteJoinedMates =
    typeof matchesSummary?.leaguemates_joined === 'number' ? matchesSummary.leaguemates_joined : 0;
  // `emptyModule` already encodes "active league only" AND "both league
  // reads confirmed", so gating on it stops a per-league count rendering
  // under another league's filter chip.
  const inviteProof = emptyModule ? inviteSocialProof(inviteTotalMates, inviteJoinedMates) : null;
  const invitePlatform =
    leagues.find((lg) => lg.league_id === activeLeagueId)?.platform ?? 'unknown';
  // PR-6 (operator decision D-P1-13) — WHICH ACTION LEADS is conditional on
  // league penetration, not fixed. Under 50% joined, an empty inbox is a
  // population problem and the invite leads (primary, and placed above
  // "Find a trade"). At 50%+ the boards mostly exist, so it is a discovery
  // problem and "Find a trade" keeps the lead. Only ever one primary.
  const invitePenetration = inviteTotalMates > 0 ? inviteJoinedMates / inviteTotalMates : 1;
  const inviteLeads = inviteProof !== null && invitePenetration < 0.5;

  const onInviteFromMatches = () =>
    shareInvite({
      leagueId:   activeLeagueId || '',
      leagueName: matchesSummary?.league_name || activeLeague?.league_name,
      username:   user?.username,
      surface:    'matches_empty',
      notJoined:  inviteTotalMates - inviteJoinedMates,
      totalMates: inviteTotalMates,
      platform:   invitePlatform,
      screen:     'Matches',
    });

  // ⚠ THIS IS A MOUNT COUNTER, NOT AN IMPRESSION COUNTER. Do not read
  // `invite_cta_shown{surface:'matches_empty'}` as an impression rate, and
  // do not compute a tap-through rate from it, until the clipping below is
  // fixed.
  //
  // The mutual-empty branch has NO scroll container anywhere in its
  // ancestry — it is a plain <View style={styles.centered}> (flex: 1 +
  // justifyContent: 'center'); the only ScrollView on this screen is the
  // horizontal filter-chip row. On smaller devices that column is already
  // taller than the viewport, so whatever sits below "Find a trade" is
  // clipped off-screen and unreachable — today that is the progress module,
  // Refresh and the help link. This event therefore counts MOUNTS, and its
  // tap-through will read artificially low for whichever action does not
  // lead (the leading action is placed above the clipping boundary).
  //
  // The operator accepted this knowingly (DECISIONS-p1.md D-P1-04) and will
  // verify on TestFlight; fixing the scroll container is explicitly out of
  // P1-5's scope and belongs with the A-34 layout family. Maestro cannot
  // detect the failure either — off-screen children stay in the hierarchy,
  // so assertVisible passes regardless. The screenshot is the evidence.
  //
  // `invite_cta_shown{surface:'league_home'}` is UNAFFECTED and is a real
  // impression — that surface has a real ScrollView.
  //
  // Do NOT "fix" this by weakening the guard below: making the event fire
  // less often would hide the defect rather than measure around it.
  const inviteShownRef = useRef<string | null>(null);
  useEffect(() => {
    if (segment !== 'mutual' || isLoading || isError) return;
    if (visibleMatches.length !== 0) return;
    if (!activeLeagueId || inviteProof === null) return;
    if (inviteShownRef.current === activeLeagueId) return;
    inviteShownRef.current = activeLeagueId;
    track('invite_cta_shown', {
      surface:     'matches_empty',
      not_joined:  inviteTotalMates - inviteJoinedMates,
      total_mates: inviteTotalMates,
      platform:    invitePlatform,
    }, 'Matches');
  }, [segment, isLoading, isError, visibleMatches.length, activeLeagueId,
      inviteProof, inviteTotalMates, inviteJoinedMates, invitePlatform]);

  // Built once, placed either above or below "Find a trade" depending on
  // which action leads. Two placements, one definition — so the copy and
  // the handler cannot drift between the two orderings.
  const inviteBlock = inviteProof === null ? null : (
    <>
      <Text testID="matches.invite-social-proof" style={styles.inviteProof}>
        {inviteProof}
      </Text>
      <Text style={styles.emptyBody}>{INVITE_RATIONALE}</Text>
      <Button
        testID="matches.invite-cta"
        label="Invite leaguemates"
        variant={inviteLeads ? 'primary' : 'secondary'}
        onPress={onInviteFromMatches}
      />
    </>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.header}>
        <Text style={styles.title}>Matches</Text>
        <Text style={styles.subtitle}>
          {segment === 'mutual'
            ? 'Trades where you and a leaguemate both said yes — across every league.'
            : segment === 'awaiting'
              ? "Trades you've liked — waiting on the other owner to swipe."
              : "Players you've offered around the league, and who can see it."}
        </Text>
        {/* Untouchables affordance hint — long-press is invisible without
            it. Only when the flag is on and there's something to press. */}
        {untouchablesEnabled
          && segment !== 'standing'
          && (segment === 'mutual' ? visibleMatches.length > 0 : visibleAwaiting.length > 0) ? (
          // S2 PRD-04 ride-along (visual.chalkline_cleanup): content-carrying
          // hint promotes chalk-faint → chalk-dim. S3 PRD-02: with the menu
          // live, the hold gesture opens the shared menu — say so.
          <Text style={[styles.hint, cleanupOn && styles.hintDim]}>
            {menuOn
              ? 'Hold a player for options — info and untouchable.'
              : "Hold a player you'd send to mark them untouchable."}
          </Text>
        ) : null}
      </View>

      {/* Segment toggle. Two-pill control to flip between mutual matches
          (default) and one-sided likes waiting on the counterparty. */}
      <View style={styles.segmentRow}>
        <SegmentBtn
          label="Mutual matches"
          count={mutualPillCount}
          active={segment === 'mutual'}
          onPress={() => setSegment('mutual')}
          testID="matches.segment.mutual"
        />
        <SegmentBtn
          label="Awaiting them"
          count={awaitingPillCount}
          active={segment === 'awaiting'}
          onPress={() => {
            // A hand-tapped segment is a `tab` view even on a route that
            // still carries N6.1's `guidedArrival` param.
            awaitingSourceRef.current = 'tab';
            setSegment('awaiting');
          }}
          testID="matches.segment.awaiting"
        />
        {/* #362 — the manage surface. Placed here, not in Settings: this is
            content, not configuration. Every broadcast needs a revoke, or it
            becomes a thing users are afraid to use. */}
        {standingOffersOn ? (
          <SegmentBtn
            label="Standing offers"
            count={standingPillCount}
            active={segment === 'standing'}
            onPress={() => setSegment('standing')}
            testID="matches.segment.standing"
          />
        ) : null}
      </View>

      {/* League filter chip row. Horizontally scrollable so 5+ leagues
          don't cramp the viewport. Defaults to "All". flexGrow:0 keeps the
          row sized to its content even when the body below renders an
          empty-state View with flex:1. */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="always"
        style={styles.chipScroll}
        contentContainerStyle={styles.chipRow}
      >
        {filterChips.map((c) => {
          const isActive = c.id === filterLeagueId;
          // #335 (R-8/R-10) — chips count the active segment; null (list
          // unresolved) renders no count, a missing league honestly reads 0.
          const chipCount =
            c.id === 'all'
              ? segmentChipTotal
              : segmentChipCounts === null
                ? null
                : segmentChipCounts[c.id] ?? 0;
          return (
            <Pressable
              key={c.id}
              // #307 frozen §4.3 — asserted by the LeagueHome group's Maestro
              // flow; selection stays asserted via accessibilityState below.
              testID={c.id === 'all' ? 'matches.league-chip.all' : `matches.league-chip.${c.id}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
              accessibilityLabel={
                typeof chipCount === 'number'
                  ? `Filter: ${c.name}, ${chipCount} ${chipCount === 1 ? 'trade' : 'trades'}`
                  : `Filter: ${c.name}`
              }
              onPress={() => setFilterLeagueId(c.id)}
              hitSlop={{ top: 6, bottom: 6 }}
              style={({ pressed }) => [
                styles.chip,
                isActive && styles.chipActive,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <View style={styles.chipInner}>
                {/* Long names truncate the NAME, never the count. */}
                <Text
                  style={[styles.chipText, isActive && styles.chipTextActive]}
                  numberOfLines={1}
                >
                  {c.name}
                </Text>
                {typeof chipCount === 'number' ? (
                  <Text style={[styles.chipCount, isActive && styles.chipCountActive]}>
                    {chipCount}
                  </Text>
                ) : null}
              </View>
            </Pressable>
          );
        })}
      </ScrollView>

      {activeQuery.data === undefined && activeQuery.isLoading ? (
        <View style={styles.list}>
          {[0, 1, 2].map((i) => (
            <View key={i} style={{ gap: space.xs, marginBottom: space.lg }}>
              <View style={styles.matchHeader}>
                <View style={styles.skeletonLabel} />
                <View style={styles.skeletonTime} />
              </View>
              <View style={styles.skeletonCard} />
            </View>
          ))}
        </View>
      ) : isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>
            {readErrorCopy(
              activeQuery.error,
              segment === 'mutual'
                ? 'Could not load matches.'
                : segment === 'awaiting'
                  ? 'Could not load pending trades.'
                  : 'Could not load your standing offers.',
            )}
          </Text>
        </View>
      ) : segment === 'mutual' ? (
        visibleMatches.length === 0 ? (
          // #229/#234 (approved mock empty-states-progress-v3.html, ships
          // live): the empty inbox explains the mechanic, points at the
          // action that works today, and repeats League home's unlock
          // module so the two surfaces never tell different stories.
          <View style={styles.centered}>
            <Text testID="matches.empty-text" style={styles.emptyTitle}>
              {filterLeagueId === 'all'
                ? 'No mutual matches yet'
                : `No matches in ${filteredLeagueName} yet`}
            </Text>
            <Text style={styles.emptyBody}>
              A match needs two boards — yours and a leaguemate's. You can
              find trade ideas right now; matches appear when a leaguemate
              likes the same trade.
            </Text>
            {/* "Find a trade" → the Trades hub. Supersedes the S4 PRD-05
                flag-gated "Go to Trades" on THIS state only (same
                destination, now always on); testID kept so existing flows
                keep passing. Refresh stays as the quiet ghost — the empty
                state is a plain View, so pull-to-refresh can't cover it
                (documented deviation from the mock's "Refresh is dropped").
                P1-5 / PR-6: this is no longer unconditionally the primary —
                under 50% of leaguemates joined the invite leads and sits
                above it, and "Find a trade" drops to secondary. At 50%+ it
                keeps the lead, as here. See `inviteLeads` above. */}
            {inviteLeads ? inviteBlock : null}
            <Button
              testID="matches.go-to-trades"
              label="Find a trade"
              variant={inviteLeads ? 'secondary' : 'primary'}
              onPress={() => navigation.navigate('Trades', { screen: 'TradesHome' })}
            />
            {inviteLeads ? null : inviteBlock}
            {/* Compact unlock module — ACTIVE league only (its counts are
                league-scoped; hidden while a different league's filter is
                selected or the league data hasn't arrived). */}
            {emptyModule ? (
              <LeagueProgressModule
                testID="matches.progress-module"
                compact
                positionsRanked={null}
                rankedMates={emptyModule.rankedMates}
                totalTeams={emptyModule.totalTeams}
                style={styles.progressModule}
              />
            ) : null}
            <Button label="Refresh" variant="ghost" compact onPress={onRefresh} />
            {/* S4 PRD-01 (ux.help_surface): answer "how does matching work?"
                at the moment the empty inbox raises it. */}
            {helpOn ? (
              <Pressable
                testID="matches.matching-help"
                onPress={() => {
                  track('help_opened', { topic: 'matching' }, 'Matches');
                  setMatchingHelpOpen(true);
                }}
                accessibilityRole="button"
                accessibilityLabel="How matching works"
                hitSlop={8}
                style={styles.helpLink}
              >
                {({ pressed }) => (
                  <Text style={[styles.helpLinkText, pressed && { color: chalk.base }]}>
                    How matching works
                  </Text>
                )}
              </Pressable>
            ) : null}
          </View>
        ) : (
          <FlatList
            ref={matchesListRef}
            contentContainerStyle={styles.list}
            data={visibleMatches}
            keyExtractor={(m) => m.match_id}
            refreshControl={
              <RefreshControl
                refreshing={isFetching}
                onRefresh={onRefresh}
                tintColor={ice.base}
              />
            }
            renderItem={({ item }) => (
              <View style={{ gap: space.xs }}>
                {/* League badge — only shown in the "All" view; redundant
                    when a single-league filter is active. */}
                {filterLeagueId === 'all' && item.league_name ? (
                  <View style={styles.leagueBadgeRow}>
                    <Badge label={item.league_name} />
                  </View>
                ) : null}
                <View style={styles.matchHeader}>
                  <View style={styles.matchLabelRow}>
                    <Icon name="match" size={16} color={semantic.pos} />
                    <Text style={styles.matchLabel}>
                      New match with @{item.counterparty_username}
                    </Text>
                  </View>
                  <Text style={[styles.matchTime, cleanupOn && styles.matchTimeDim]}>{relativeTime(item.created_at)}</Text>
                </View>
                <TradeCardComp
                  variant="match"
                  data={matchToTradeCardShape(item, activeLeague?.league_id)}
                  // audit P0-6 — names the league in the copy-trade fallback's
                  // first line; optional all the way down, so a legacy
                  // response without league_name degrades to "Trade proposal".
                  leagueName={item.league_name}
                  onDismiss={() => handleDismiss(item)}
                  acting={dismissMutation.isPending}
                  showSend
                  // #249 — no lock button on this screen (operator call);
                  // untouchables stay reachable via long-press menu.
                  hideLockButton
                  untouchableIds={
                    untouchablesEnabled
                      ? untouchablesByLeague.get(item.league_id)
                      : undefined
                  }
                  onToggleUntouchable={
                    untouchablesEnabled
                      ? (p) => handleToggleUntouchable(item.league_id, p)
                      : undefined
                  }
                  onPlayerMenu={
                    menuOn
                      ? (p, side) => {
                          haptics.selection();
                          track(
                            'player_menu_opened',
                            { surface: 'matches', side },
                            'Matches',
                          );
                          setMenuTarget({ leagueId: item.league_id, player: p, side });
                        }
                      : undefined
                  }
                  // #319 — expandable value disclosure + open-in-calc, under
                  // the send button (TradeCard's final block).
                  footer={
                    <MatchValueSection
                      matchKey={item.match_id}
                      matchId={item.match_id}
                      leagueId={item.league_id}
                      giveIds={item.my_side_player_ids}
                      receiveIds={item.their_side_player_ids}
                      opponentUsername={item.counterparty_username}
                      opponentUserId={item.counterparty_user_id}
                      isActiveLeague={item.league_id === activeLeagueId}
                      onOpenInCalc={() => handleOpenInCalc(item)}
                    />
                  }
                />
              </View>
            )}
            ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
          />
        )
      ) : segment === 'awaiting' ? (
        // Awaiting-them segment
        visibleAwaiting.length === 0 ? (
          <View style={styles.centered}>
            <Text style={styles.emptyTitle}>No pending trades.</Text>
            <Text style={styles.emptyBody}>
              Swipe more in the Acquire tab.
            </Text>
            {/* S4 PRD-05 — same rule as the mutual empty state. */}
            {emptyCtasOn ? (
              <>
                <Button
                  testID="matches.go-to-trades"
                  label="Go to Trades"
                  variant="primary"
                  onPress={() => navigation.navigate('Trades')}
                />
                <Button label="Refresh" variant="ghost" compact onPress={onRefresh} />
              </>
            ) : (
              <Button label="Refresh" variant="secondary" compact onPress={onRefresh} />
            )}
          </View>
        ) : (
          <FlatList
            ref={awaitingListRef}
            contentContainerStyle={styles.list}
            data={visibleAwaiting}
            keyExtractor={(a) => `${a.league_id}:${a.trade_id}`}
            refreshControl={
              <RefreshControl
                refreshing={isFetching}
                onRefresh={onRefresh}
                tintColor={ice.base}
              />
            }
            renderItem={({ item }) => (
              <View style={{ gap: space.xs }}>
                {filterLeagueId === 'all' && item.league_name ? (
                  <View style={styles.leagueBadgeRow}>
                    <Badge label={item.league_name} />
                  </View>
                ) : null}
                <View style={styles.matchHeader}>
                  <Text style={styles.awaitingLabel}>
                    Waiting on @{item.counterparty_username}
                  </Text>
                  <Text style={[styles.matchTime, cleanupOn && styles.matchTimeDim]}>{relativeTime(item.liked_at)}</Text>
                </View>
                {/* Reuse swipe variant — no Accept/Decline buttons because
                    the user has already swiped accept. They're just waiting
                    on the other owner. */}
                <TradeCardComp
                  variant="swipe"
                  data={awaitingToTradeCardShape(item, activeLeague?.league_id)}
                  // audit P0-6 — same as the mutual segment above: both mounts
                  // render a SendInSleeperButton, so both name their league.
                  leagueName={item.league_name}
                  showSend
                  // #249 — same call as the mutual list: no lock button
                  // anywhere on the Matches screen.
                  hideLockButton
                  untouchableIds={
                    untouchablesEnabled
                      ? untouchablesByLeague.get(item.league_id)
                      : undefined
                  }
                  onToggleUntouchable={
                    untouchablesEnabled
                      ? (p) => handleToggleUntouchable(item.league_id, p)
                      : undefined
                  }
                  onPlayerMenu={
                    menuOn
                      ? (p, side) => {
                          haptics.selection();
                          track(
                            'player_menu_opened',
                            { surface: 'matches_awaiting', side },
                            'Matches',
                          );
                          setMenuTarget({ leagueId: item.league_id, player: p, side });
                        }
                      : undefined
                  }
                  // #318 + #319 — the awaiting card's footer carries BOTH the
                  // Dismiss affordance and the value disclosure. Dismiss sits
                  // first, directly under the send button (TradeCard itself
                  // is out of this wave's footprint beyond the footer prop —
                  // wave-trades owns its internals, S-2/S-6 pin that). The
                  // deck never passes a footer, so it renders exactly as
                  // before.
                  footer={
                    <View style={styles.awaitingFooter}>
                      <Button
                        testID="matches.awaiting-dismiss"
                        variant="pass"
                        label="Dismiss"
                        onPress={() => handleDismissAwaiting(item)}
                        disabled={dismissAwaitingMutation.isPending}
                      />
                      <MatchValueSection
                        matchKey={`${item.league_id}:${item.trade_id}`}
                        leagueId={item.league_id}
                        giveIds={item.my_side_player_ids}
                        receiveIds={item.their_side_player_ids}
                        opponentUsername={item.counterparty_username}
                        opponentUserId={item.counterparty_user_id}
                        isActiveLeague={item.league_id === activeLeagueId}
                        onOpenInCalc={() => handleOpenInCalc(item)}
                      />
                    </View>
                  }
                />
              </View>
            )}
            ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
          />
        )
      ) : (
        // #362 — Standing offers. Active first, then Expired (read-only).
        // Revoke is the ONLY action: mockup §5's Edit and Repost are out of
        // v1, because revoke-then-repost already covers both and the
        // writer's one-live-offer-per-(player, round) rule makes that
        // sequence safe. No FeedbackFAB here — the RootNav tab-stack mount
        // already covers this screen (CLAUDE.md #188).
        standingRows.live.length + standingRows.dead.length === 0 ? (
          <View style={styles.centered}>
            <Text testID="matches.standing-empty" style={styles.emptyTitle}>
              No standing offers
            </Text>
            <Text style={styles.emptyBody}>
              Like a one-for-one where you get a first, and we'll ask which
              other teams and years you'd take one from.
            </Text>
            <Button label="Refresh" variant="ghost" compact onPress={onRefresh} />
          </View>
        ) : (
          <ScrollView
            contentContainerStyle={styles.list}
            refreshControl={
              <RefreshControl
                refreshing={isFetching}
                onRefresh={onRefresh}
                tintColor={ice.base}
              />
            }
          >
            {standingRows.live.length > 0 ? (
              <Text style={styles.standingGroupHdr}>
                Active · {standingRows.live.length}
              </Text>
            ) : null}
            {standingRows.live.map((o) => (
              <View key={o.offer_id} style={styles.standingRow}>
                <View style={styles.standingRowMain}>
                  {/* The server omits league_name for rows outside the
                      session league; we render the badge only when it is
                      actually there rather than guessing a name. */}
                  {filterLeagueId === 'all' && o.league_name ? (
                    <View style={styles.leagueBadgeRow}>
                      <Badge label={o.league_name} />
                    </View>
                  ) : null}
                  <Text style={styles.standingTitle} numberOfLines={1}>
                    {o.player_name} → any {roundWordFor(o.round)}
                  </Text>
                  <Text style={styles.standingMeta}>
                    {o.seasons.map((s) => `'${String(s).slice(-2)}`).join(' ')}
                    {' · '}
                    {o.team_count} {o.team_count === 1 ? 'team' : 'teams'}
                    {' · '}
                    {o.days_left} {o.days_left === 1 ? 'day' : 'days'} left
                  </Text>
                </View>
                <Button
                  testID={`matches.standing-revoke.${o.offer_id}`}
                  variant="pass"
                  compact
                  label="Revoke"
                  disabled={revokeMutation.isPending}
                  onPress={() => {
                    haptics.selection();
                    revokeMutation.mutate(o);
                  }}
                />
              </View>
            ))}
            {standingRows.dead.length > 0 ? (
              <Text style={styles.standingGroupHdr}>
                Expired · {standingRows.dead.length}
              </Text>
            ) : null}
            {standingRows.dead.map((o) => (
              <View key={o.offer_id} style={[styles.standingRow, styles.standingRowDead]}>
                <View style={styles.standingRowMain}>
                  {filterLeagueId === 'all' && o.league_name ? (
                    <View style={styles.leagueBadgeRow}>
                      <Badge label={o.league_name} />
                    </View>
                  ) : null}
                  <Text style={[styles.standingTitle, styles.standingTitleDead]} numberOfLines={1}>
                    {o.player_name} → any {roundWordFor(o.round)}
                  </Text>
                  <Text style={styles.standingMeta}>
                    {o.seasons.map((s) => `'${String(s).slice(-2)}`).join(' ')}
                    {' · '}
                    {o.team_count} {o.team_count === 1 ? 'team' : 'teams'}
                    {' · '}
                    {/* `stale` is only ever TRUE when the server actually
                        checked (session league); a false value means "not
                        checked here", so it never renders as a claim. */}
                    {o.stale ? 'no longer on your roster' : 'expired'}
                  </Text>
                </View>
              </View>
            ))}
          </ScrollView>
        )
      )}

      {/* S3 PRD-02 (ux.player_context_menu) — shared long-press menu.
          menuTarget is only ever set while the flag is on. */}
      <PlayerContextMenu
        visible={!!menuTarget}
        player={menuTarget?.player ?? null}
        actions={menuTarget ? menuActionsFor(menuTarget) : []}
        onClose={() => setMenuTarget(null)}
      />

      {/* S4 PRD-01 (ux.help_surface) — "How matching works" in place. */}
      {helpOn ? (
        <HelpSheet
          visible={matchingHelpOpen}
          title="How matching works"
          body={
            'When you like a trade, we quietly show its mirror to the other ' +
            'owner in their own deck. If they like it too, it becomes a ' +
            'mutual match and lands here — neither side sees a one-way ' +
            'like, so there is no pressure until you both said yes.'
          }
          readMoreUrl={`${getBaseUrl()}/faq.html`}
          topic="matching"
          onClose={() => setMatchingHelpOpen(false)}
        />
      ) : null}
    </SafeAreaView>
  );

  // S3 PRD-02 — per-surface commands for the shared player context menu.
  function menuActionsFor(target: {
    leagueId: string;
    player: Player;
    side: 'give' | 'receive';
  }): PlayerMenuAction[] {
    const { leagueId, player, side } = target;
    const actions: PlayerMenuAction[] = [];
    if (side === 'give' && untouchablesEnabled) {
      const marked = untouchablesByLeague.get(leagueId)?.has(player.id) ?? false;
      actions.push({
        key: marked ? 'untouchable-remove' : 'untouchable-add',
        label: marked ? 'Remove untouchable' : 'Mark untouchable',
        hint: marked
          ? 'Allow this player in trade ideas again'
          : 'Never offered from your roster in trade ideas',
        onPress: () => {
          setMenuTarget(null);
          handleToggleUntouchable(leagueId, player);
        },
      });
    }
    return actions;
  }
}

function SegmentBtn({
  label,
  active,
  onPress,
  testID,
  count,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID?: string;
  // #335 (R-11) — inline Plex Mono count after the label. Omitted or null
  // (list not yet resolved — R-10) renders exactly as before.
  count?: number | null;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={
        typeof count === 'number'
          ? `${label}, ${count} ${count === 1 ? 'trade' : 'trades'}`
          : label
      }
      style={({ pressed }) => [
        styles.segmentBtn,
        active && styles.segmentBtnActive,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <View style={styles.segmentInner}>
        <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
          {label}
        </Text>
        {typeof count === 'number' ? (
          <Text style={[styles.segmentCount, active && styles.segmentCountActive]}>
            {count}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

// TradeMatch and TradeCard have overlapping but not identical shapes.
// Cross-league enrichment (server.py: /api/trades/matches/all) provides
// names + teams + positions as parallel arrays — use those when present.
// Falls back to ID-as-name / "FA" / "FLX" (legacy behavior, only happens
// when the backend hasn't been redeployed with the enrichment yet).
function matchToTradeCardShape(m: TradeMatch, fallbackLeague: string | undefined) {
  const POS_UNKNOWN = 'FLX' as any;
  const give = m.my_side_player_ids.map((id, i): Player => ({
    id,
    name:     m.my_side_player_names?.[i]     || id,
    position: m.my_side_player_positions?.[i] || POS_UNKNOWN,
    team:     m.my_side_player_teams?.[i]     || '',
  }));
  const recv = m.their_side_player_ids.map((id, i): Player => ({
    id,
    name:     m.their_side_player_names?.[i]     || id,
    position: m.their_side_player_positions?.[i] || POS_UNKNOWN,
    team:     m.their_side_player_teams?.[i]     || '',
  }));
  return {
    trade_id:           m.match_id,
    league_id:          m.league_id || fallbackLeague || '',
    give_player_ids:    m.my_side_player_ids,
    receive_player_ids: m.their_side_player_ids,
    give_players:       give,
    receive_players:    recv,
    opponent_user_id:   m.counterparty_user_id,
    opponent_username:  m.counterparty_username,
    match_score:        100,
    fairness:           1,
    // Propose-label spine: server-recovered originating impression —
    // TradeCard forwards it into the send button so a propose from this
    // tile appends the `propose` deck outcome.
    impression_id:      m.impression_id,
  };
}

// Same adapter pattern for awaiting trades — parallel TradeMatch shape so
// we don't pay for a second TradeCard variant. Match score is unknown for
// historical likes (the in-memory card may not still be around), so we
// show 100 to keep the strength bar consistent with mutual matches.
function awaitingToTradeCardShape(a: AwaitingTrade, fallbackLeague: string | undefined) {
  const POS_UNKNOWN = 'FLX' as any;
  const give = a.my_side_player_ids.map((id, i): Player => ({
    id,
    name:     a.my_side_player_names?.[i] || id,
    position: POS_UNKNOWN,
    team:     '',
  }));
  const recv = a.their_side_player_ids.map((id, i): Player => ({
    id,
    name:     a.their_side_player_names?.[i] || id,
    position: POS_UNKNOWN,
    team:     '',
  }));
  return {
    trade_id:           a.trade_id,
    league_id:          a.league_id || fallbackLeague || '',
    give_player_ids:    a.my_side_player_ids,
    receive_player_ids: a.their_side_player_ids,
    give_players:       give,
    receive_players:    recv,
    opponent_user_id:   a.counterparty_user_id,
    opponent_username:  a.counterparty_username,
    match_score:        100,
    fairness:           1,
    // Propose-label spine — same threading as matchToTradeCardShape.
    impression_id:      a.impression_id,
  };
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: { paddingHorizontal: space.lg, paddingVertical: space.md },
  title: { ...type.display },
  subtitle: { ...type.bodySm, marginTop: space.xs },
  hint: { ...type.bodySm, color: chalk.faint, marginTop: space.xs },
  // S2 PRD-04 ride-along (visual.chalkline_cleanup): content-carrying text
  // never sits at chalk-faint (3.4:1) — promote to chalk-dim.
  hintDim: { color: chalk.dim },
  matchTimeDim: { color: chalk.dim },
  // S4 PRD-01 — quiet "How matching works" link on the empty state.
  helpLink: {
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  helpLinkText: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },

  // flexGrow:0 prevents the horizontal ScrollView from stretching to fill
  // remaining vertical space when the body below is an empty-state View.
  chipScroll: { flexGrow: 0, flexShrink: 0 },

  // Segmented group per PositionTabs spec: 1px hairline group at radii.sm;
  // active segment = ink3 fill + 2px ice underline (ice use: active state).
  segmentRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginBottom: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segmentBtn: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  segmentBtnActive: {
    backgroundColor: ink.ink3,
    borderBottomColor: ice.base,
  },
  segmentText: { ...type.label },
  segmentTextActive: { color: chalk.base },
  // #335 (R-11) — label + inline mono count on one row, space.xs apart.
  segmentInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  // Bare Plex Mono inline numeral (ScorePill/tier-header mono-count
  // convention — no box, no CountBadge). 11 = the type floor.
  segmentCount: {
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
    color: chalk.dim,
  },
  segmentCountActive: { color: chalk.base },

  chipRow: {
    paddingHorizontal: space.lg,
    paddingBottom: space.sm,
    gap: space.xs,
    alignItems: 'center',
  },
  // Chalkline badge construction, sized up for touch: 1px border in the
  // encode color + chalk text on ink. Active = ice border (active state).
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 32,
    justifyContent: 'center',
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
  },
  chipActive: {
    borderColor: ice.base,
  },
  // #335 (R-11) — same construction as segmentInner: the NAME shrinks and
  // truncates under any future width cap; the count never does.
  chipInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  chipText: { ...type.label, flexShrink: 1 },
  chipTextActive: { color: chalk.base },
  chipCount: {
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
    color: chalk.dim,
    flexShrink: 0,
  },
  chipCountActive: { color: chalk.base },

  list: { padding: space.lg, paddingBottom: 96 },
  leagueBadgeRow: { flexDirection: 'row', paddingHorizontal: space.xs },
  matchHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xs,
  },
  matchLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    flexShrink: 1,
  },
  matchLabel: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: semantic.pos,
    flexShrink: 1,
  },
  awaitingLabel: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    flexShrink: 1,
  },
  // Timestamps are data — Plex Mono, chalk-faint (ActivityRow convention).
  matchTime: { ...type.data, color: chalk.faint },
  // #318/#319 — the awaiting card's footer stack: Dismiss row above the
  // value disclosure, spaced on the card's inner rhythm.
  awaitingFooter: { gap: space.sm },
  // #362 — standing-offer manage rows.
  standingGroupHdr: {
    fontFamily: fonts.uiSemi,
    fontSize: 12,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    color: chalk.dim,
    marginTop: space.lg,
    marginBottom: space.sm,
  },
  standingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    padding: space.md,
    marginBottom: space.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  standingRowDead: { opacity: 0.6 },
  standingRowMain: { flex: 1, gap: space.xs },
  standingTitle: {
    fontFamily: fonts.uiSemi,
    fontSize: 15,
    color: chalk.base,
  },
  standingTitleDead: { color: chalk.dim },
  standingMeta: {
    fontFamily: fonts.data,
    fontSize: 12,
    color: chalk.dim,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
  errorText: { ...type.bodySm, color: semantic.neg },

  // Skeleton tiles — same outer dimensions as a real TradeCard match
  // tile (ink-1 surface, hairline, radii.md) so the page shape is stable
  // on first paint. Static — no shimmer/animation library introduced.
  skeletonCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    height: 220,
  },
  skeletonLabel: {
    width: 180,
    height: 12,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  skeletonTime: {
    width: 48,
    height: 10,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  emptyTitle: { ...type.heading, textAlign: 'center' },
  // #229/#234 — the compact unlock module stretches to the empty state's
  // full width (its own copy is left-aligned inside the card).
  progressModule: { alignSelf: 'stretch' },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
    maxWidth: 340,
  },
  // P1-5 — the social-proof count carries the weight of the ask, so it is
  // semibold chalk against the dim body copy beside it.
  inviteProof: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
    textAlign: 'center',
    maxWidth: 340,
  },
});
