// Draft Room (rookie-draft M4 — plan §M4, lld §4.5). Flag `draft.room`.
//
// Read-only. Three sections over ONE payload: the board (slot · owner ·
// pick), your picks, and the undrafted rookies with a Consensus | My-board
// toggle. The terminal CTA is a deep link into the platform's own draft
// room — FTF never writes a pick (D9).
//
// The states below are DESIGNED renders, not spinners. Each says what is
// true and what the user can do about it:
//
//   order_not_set        the platform has not published an order yet, so we
//                        show round-level ownership and say so. NEVER an
//                        invented order (a pre-draft Sleeper draft returns
//                        an identity slot map that reads like a real one).
//   class_not_loaded     Feb–Apr is structurally empty: Sleeper carries no
//                        rows for a class until ~late April. Offer last
//                        year's class rather than an empty list.
//   startup_draft        labelled, with the rookie list suppressed — a
//                        startup rendered as a rookie draft is a lie.
//   platform_unsupported honest "not here yet" (MFL lands with M5).
//   stale                `as_of` is ALWAYS visible; stale adds the reason.
//   unavailable          no usable source; Refresh is still offered.
//
// Live polling (flag `draft.live_poll`) is this app's FIRST recurring
// fetch. Three gates, all required, and a hard ZERO requests when blurred
// or backgrounded — see the refetchInterval below.
//
// ── draft-extensions W1 (flag `draft.rank_inline`, lands OFF) ───────────
// The room shipped with inert undrafted rows and ZERO track() calls, so
// the one job it cannot do today is the one you have on the clock: "this
// guy isn't priced and I have 90 seconds." W1 adds, flag-gated:
//   · long-press + an `accessibilityActions` custom action on an undrafted
//     row (the shipped TradeCard vocabulary — there is NO "⋯" glyph
//     anywhere in this app, and adding one would need a components.md spec
//     under ADR-004/005) opening the shared PlayerContextMenu;
//   · Set my value  → the new AnchorSheet on the SHIPPED /api/anchor/save
//     lane. THE ANCHOR LANE ONLY: nothing here may reach /api/tiers/save,
//     save_tiers_position or the merged-band path (pinned by AST + runtime
//     tests in backend/tests/test_draft_extensions_w1.py);
//   · Rank the rookies → the existing bridge, now two-way (it passes a
//     return route so RookieRanks can come back here);
//   · Add to targets → the shipped per-user-per-league asset-pref write;
//   · the coverage nudge, read off `undrafted[].valued`.
// Flag OFF ⇒ rows are the inert Views they are today: no long-press, no
// a11y action, no menu, no sheet, no nudge. The per-player testIDs ship
// UNFLAGGED — they are inert, and they are what makes the flag testable.
//
// ── draft-extensions W2 (flag `draft.mock`, lands OFF) ──────────────────
// Placement option C, chosen by the operator over the design pass's
// recommendation: a `Real draft | Mock` segmented control at the top of the
// room. C's real advantage is that `state_payload()` returns the board's
// entry shapes verbatim, so the Mock side reuses the SAME row components
// (now shared, `components/draft/DraftRows`) instead of a parallel set.
//
// C's real risk is the one the design pass named: this screen PRINTS the
// no-platform-writes guarantee on itself, and a mode switch above that
// sentence could make it read as a promise about a board that takes picks.
// Three obligations answer it, and they are load-bearing, not polish:
//
//   1. In Mock mode the pinned `MockRail` sits above the scroll, so the
//      word MOCK is on screen at every scroll position.
//   2. In Mock mode the platform deep link AND its "never drafts for you"
//      note are NOT RENDERED — along with the status bar and Refresh, which
//      describe the REAL draft and would be lies over a simulation.
//   3. The mock's session lives on a pushed `MockDraftScreen`, which
//      carries the same rail. Only the ENTRY is in the room.
//
// Flag off ⇒ no toggle, no query, no mock state at all: this file renders
// byte-identically to what shipped.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useIsFocused } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  chalk,
  flare,
  ice,
  ink,
  radii,
  semantic,
  space,
  type,
} from '../theme/chalkline';
import { Button, Icon, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import PlayerContextMenu, {
  type PlayerMenuAction,
} from '../components/PlayerContextMenu';
import AnchorSheet, { type AnchorTarget } from '../components/AnchorSheet';
import TierBadge from '../components/TierBadge';
import Toast from '../components/Toast';
import {
  BasisChip,
  MY_BOARD_FALLBACK_COPY,
  NO_CONSENSUS_VALUE_COPY,
  draftRow,
  positionOf,
  slotLabel,
} from '../components/draft/DraftRows';
import { DraftModeToggle, MockRail, type DraftMode } from '../components/draft/MockChrome';
import MockEntryPanel, {
  MOCK_MIN_TEAMS,
  type MockBlock,
} from '../components/draft/MockEntryPanel';
import MockSetupSheet, { type MockSetupResult } from '../components/draft/MockSetupSheet';
import {
  DraftSchemaError,
  getDraftBoard,
  type DraftBasis,
  type DraftBoard,
  type DraftOrderSlot,
  type DraftPick,
  type UndraftedRow,
} from '../api/draft';
import {
  createMockDraft,
  getMockDraft,
  isMockEmpty,
  type MockDraftState,
} from '../api/mockDraft';
import { setAssetPref } from '../api/league';
import { getPickAssignments, pickAssignmentSubline } from '../api/pickAssignment';
import { track } from '../api/events';
import { readErrorCopy } from '../utils/verification';
import { haptics } from '../utils/haptics';
import { TIER_LABEL, tierForElo } from '../utils/tierBands';
import { useAppActive } from '../hooks/useAppActive';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Player, Position } from '../shared/types';

const POLL_INTERVAL_MS = 15_000;

// The coverage nudge's window: the top N of the (rank-ordered) undrafted
// list. Fixed on purpose — "N of the top 25 have no value on your board"
// is a claim the user can check, and a window that moved with list length
// would not be.
const COVERAGE_WINDOW = 25;

export default function DraftRoomScreen({ route, navigation }: any = {}) {
  // rookie-draft placement — the seasonal Draft tab's multi-league rule
  // lands on a SPECIFIC league's room, which may not be the session's
  // active one (switching the active league would reset rankings, the deck
  // and the format; reading one league's board must not cost that). The
  // param is an override only: every pre-existing entry point (the League
  // tile, the Acquire chip, the deep link) passes nothing and keeps reading
  // the active league exactly as before.
  const paramLeagueId: string | undefined = route?.params?.leagueId;
  const sessionLeagueId = useSession((s) => s.league?.league_id);
  const sessionLeagueName = useSession((s) => s.league?.league_name);
  const sessionUsername = useSession((s) => s.user?.display_name || s.user?.username);
  const leagueId = paramLeagueId ?? sessionLeagueId;
  // Set only by the seasonal Draft tab's registration — see Shell.
  const inTabs: boolean = !!route?.params?.inTabs;
  const [basis, setBasis] = useState<DraftBasis>('consensus');
  // The pre-class-load toggle. Session-only by design (#133 precedent):
  // it answers "what am I looking at right now", not a stored preference.
  const [showLastYear, setShowLastYear] = useState(false);

  const queryClient = useQueryClient();
  const livePollEnabled = useFlag('draft.live_poll');
  // W1 — per-player row actions. Off ⇒ the rows stay inert Views.
  const rowActionsOn = useFlag('draft.rank_inline');
  // Mock finding #2 (operator decision 2026-08-06): without this, a draft
  // SURFACE teaches users that rookie ranking and rookie drafting are
  // unrelated features. Gated on the rookie-scope flag — the destination
  // renders its own "not available yet" state when it's off, and an entry
  // point into that state would be a dead end.
  const rookieScopeOn = useFlag('ranks.rookie_subset');
  // W2 — the `Real draft | Mock` switch. Off ⇒ no toggle, no query, and
  // every mock branch below is unreachable.
  const mockOn = useFlag('draft.mock');
  // W3 M-A/M-B (operator, 2026-08-08). ESPN publishes no draft object, so
  // this room's only path to a real board is a member typing the pick grid
  // in. The shipped flow told the user to go do that on the League tab —
  // directions to another tab to unblock the screen they are already on.
  // With the flag on, the room OWNS the action: the notice's CTA pushes the
  // assignment grid, and the League-tab section survives as a second entry.
  const pickAssignOn = useFlag('picks.assign');
  // W3 M-D (2026-08-08). Live offline pick recording — reachable once the
  // league's picks are assigned, since that is what lets recording stay
  // "confirm, not select" (the app already knows whose pick 1.03 is).
  const manualPicksOn = useFlag('draft.manual_picks');
  const [mode, setMode] = useState<DraftMode>('real');
  const mockMode = mockOn && mode === 'mock';
  const [setupOpen, setSetupOpen] = useState(false);
  // The POST-only refusal (gap G2). GET can't tell us in advance, so we
  // remember what the create route said and stop offering the button.
  const [postRefusal, setPostRefusal] = useState<string | null>(null);
  const isFocused = useIsFocused();
  const appActive = useAppActive();

  const query = useQuery({
    queryKey: ['draft-board', leagueId, basis],
    queryFn: () => getDraftBoard(leagueId as string, basis),
    enabled: !!leagueId,
    staleTime: 10_000,
    // ── The polling contract (plan §M4, lld [RV-8]) ──────────────────────
    // FOUR conditions, every one required, and `false` (not a number) is
    // what actually stops the timer:
    //   1. the flag — polling ships dark until the live test passes;
    //   2. isFocused — another screen on top means zero requests;
    //   3. appActive — backgrounded means zero requests. The app-wide
    //      default is refetchOnWindowFocus:false, so nothing sneaks a
    //      resume fetch in either;
    //   4. state === 'live' — a complete or upcoming draft has nothing to
    //      poll for, and Sleeper CDN-caches a complete draft ~24 h anyway.
    // The QA pass threshold for blurred/backgrounded is literally ZERO.
    refetchInterval: (q) =>
      livePollEnabled &&
      isFocused &&
      appActive &&
      (q.state.data as DraftBoard | undefined)?.state === 'live'
        ? POLL_INTERVAL_MS
        : false,
    refetchIntervalInBackground: false, // explicit; the default is already false
  });

  const board = query.data;
  const onRefresh = useCallback(() => {
    query.refetch();
  }, [query]);

  // ── The assignment grid's progress (operator, 2026-08-08) ─────────────
  // Read ONLY for a board the grid itself produced (`order_confidence:
  // 'assigned'` is emitted by the ESPN branch and by nothing else), and
  // only with `picks.assign` on. Every other league — every Sleeper and MFL
  // room, and an ESPN room before anyone assigns — issues no request and is
  // byte-identical. Shares its key with the League tab and the grid screen,
  // so a save there updates this line without a fetch.
  const assignQuery = useQuery({
    queryKey: ['pick-assignments', leagueId],
    queryFn: () => getPickAssignments(leagueId as string),
    enabled: !!leagueId && pickAssignOn && board?.order_confidence === 'assigned',
    staleTime: 5 * 60_000,
  });
  const assignProgress = useMemo(() => {
    const d = assignQuery.data;
    if (!d?.seeded) return null;
    const p = d.progress;
    const partial = p.assigned < p.total;
    return {
      // ONE formatter behind the League tab's sub-line, the grid's progress
      // line and this row, so the three cannot disagree.
      line: pickAssignmentSubline(p, d.seeded),
      action: partial ? 'Continue assigning' : 'Edit the draft picks',
    };
  }, [assignQuery.data]);

  // ── W2 mock entry ─────────────────────────────────────────────────────
  // Fetched ONLY while the Mock side is selected: with the flag on but the
  // user in Real mode this screen makes exactly the requests it always did.
  // No polling — a mock changes only when its owner acts.
  const mockQuery = useQuery({
    queryKey: ['mock-draft', leagueId, 'consensus'],
    queryFn: () => getMockDraft(leagueId as string, 'consensus'),
    enabled: !!leagueId && mockMode,
    staleTime: Infinity,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
  const mockRes = mockQuery.data;
  const activeMock: MockDraftState | null =
    mockRes && !isMockEmpty(mockRes) ? (mockRes as MockDraftState) : null;
  // #295 R9 — the GET typed-empty's `capability` ride-along, consumed. With
  // no row on file the probe already ran the refusal ladder, so the entry
  // card can render disabled BEFORE any POST (the HLD §3.3 promise the
  // shipped client never implemented). Only a `no_active_mock` empty
  // carries a probe worth reading.
  const probeReason =
    mockRes && isMockEmpty(mockRes) && mockRes.reason === 'no_active_mock'
      ? mockRes.capability?.reason ?? null
      : null;

  const createMock = useMutation({
    mutationFn: (setup: MockSetupResult) =>
      createMockDraft({
        leagueId: leagueId as string,
        rounds: setup.rounds,
        type: setup.type,
        mode: setup.mode,
      }),
    onSuccess: (res) => {
      // LEAGUE platform, from the same cached list league_view reads —
      // never the device platform, never inferred from the id's shape
      // (the InLeagueCalculator convention verbatim).
      const platform =
        useSession.getState().leagues.find((lg) => lg.league_id === leagueId)
          ?.platform ?? 'unknown';
      if (isMockEmpty(res)) {
        // A typed-empty refusal is not an error — it is the honest state
        // arriving late (gap G2). Close the sheet and mute the card.
        track('mock_create_refused', { platform, reason: res.reason }, 'DraftRoom');
        setPostRefusal(res.reason);
        setSetupOpen(false);
        queryClient.setQueryData(['mock-draft', leagueId, 'consensus'], res);
        return;
      }
      // Props read off the server's RESOLVED settings_echo, never the
      // sheet's request values — a clamped `rounds` or degraded
      // `order_source` must report as resolved.
      track(
        'mock_started',
        {
          platform,
          teams: res.settings_echo?.teams ?? null,
          rounds: res.settings_echo?.rounds ?? null,
          type: res.settings_echo?.type ?? null,
          order_source: res.settings_echo?.order_source ?? null,
          mode: res.settings_echo?.mode ?? null,
        },
        'DraftRoom',
      );
      setSetupOpen(false);
      queryClient.setQueryData(['mock-draft', leagueId, 'consensus'], res);
      navigation?.navigate?.('MockDraft', { leagueId });
    },
  });

  // Which refusal (if any) the card must state instead of offering Start.
  // Order matters: the server's own answer wins over anything derived.
  const mockBlock: MockBlock | null = useMemo(() => {
    if (!board) return null;
    if (postRefusal === 'cpu_model_unvalidated') {
      return {
        testID: 'mock-entry.blocked.cpu_model_unvalidated',
        title: 'Mock draft',
        body: "Not ready yet. Our computer drafters don't pick closely enough to real drafters, and we'd rather ship nothing than ship bots we can't stand behind.",
        cta: 'Not available yet',
      };
    }
    if (postRefusal === 'class_not_loaded' || board.notice?.code === 'class_not_loaded') {
      // The room's "Show last year's class" toggle deliberately does NOT
      // arm this card: the mock pool has no season override (gap G7), so an
      // armed button would fail on tap.
      return {
        testID: 'mock-entry.blocked.class_not_loaded',
        title: 'Mock draft',
        body: `The ${board.season} rookie class loads after the NFL draft (late April). There's nobody to draft yet.`,
        cta: 'Available in late April',
      };
    }
    if (postRefusal === 'user_not_in_draft' || probeReason === 'user_not_in_draft') {
      // #295 — the fourth ladder rung: the session user could not be placed
      // in the resolved draft. One arm serves both triggers: `postRefusal`
      // after a POST, `probeReason` pre-POST from the GET `capability` —
      // the "disabled entry state" is this same card rendered before the
      // user ever taps. A fact, no false remedy: the only reachable trigger
      // is a state the user cannot act on.
      return {
        testID: 'mock-entry.blocked.user_not_in_draft',
        title: 'Mock draft',
        body: "We couldn't find your team in this league's draft, so there's no seat for you to draft from.",
        cta: "Your team isn't in this draft",
      };
    }
    if (board.kind === 'startup') {
      return {
        testID: 'mock-entry.blocked.startup_draft',
        title: 'Mock draft',
        body: "This looks like a startup draft, not a rookie draft — mocks only cover rookie classes.",
        cta: 'Rookie drafts only',
      };
    }
    if (board.teams != null && board.teams < MOCK_MIN_TEAMS) {
      return {
        testID: 'mock-entry.blocked.league_too_small',
        title: 'Mock draft',
        body: `This league has ${board.teams} teams. A mock needs at least ${MOCK_MIN_TEAMS} for the computer drafters to tell you anything useful — with fewer, you'd see almost the whole class.`,
        cta: `Needs ${MOCK_MIN_TEAMS}+ teams`,
      };
    }
    if (board.state === 'live') {
      // Correctness, not taste: the pool is snapshotted at creation and
      // INV-10 forbids any later platform read, so a mock started mid-draft
      // offers players who were taken twenty minutes ago and never catches up.
      return {
        testID: 'mock-entry.blocked.live',
        title: 'Mock draft',
        body: "Your real draft is running. A mock started now would keep offering players your league has already taken, so we don't offer one mid-draft.",
        cta: 'Not during a live draft',
      };
    }
    if (board.state === 'complete') {
      return {
        testID: 'mock-entry.blocked.complete',
        title: 'Mock draft',
        body: 'This class has already been drafted — everyone is on a roster, so there is nothing left to mock.',
        cta: 'This class is drafted',
      };
    }
    return null;
  }, [board, postRefusal, probeReason]);

  const mockMeta = useMemo(() => {
    if (!board) return null;
    return [
      `${board.rounds ?? 4} rounds`,
      board.teams != null ? `${board.teams} teams` : null,
      'linear',
      board.order_confidence === 'assigned' ? 'your league’s order' : 'order randomized',
    ]
      .filter(Boolean)
      .join(' · ');
  }, [board]);

  // Read-only on purpose: `user_owner_id` IS the session user and drafting
  // for another team is out of v1 (the engine has no such call).
  const mockTeamLabel = useMemo(
    () => [sessionUsername, sessionLeagueName].filter(Boolean).join(' — ') || 'Your team',
    [sessionUsername, sessionLeagueName],
  );

  // ── W1 row actions ────────────────────────────────────────────────────
  // menuTarget is only ever set while `draft.rank_inline` is on, so both
  // sheets are unreachable with the flag off.
  const [menuTarget, setMenuTarget] = useState<UndraftedRow | null>(null);
  const [anchorTarget, setAnchorTarget] = useState<AnchorTarget | null>(null);
  const [toast, setToast] = useState<
    { msg: string; tone?: 'success' | 'warn' } | null
  >(null);

  // ── Assign the picks from HERE (operator, 2026-08-08) ─────────────────
  // Pushed, not presented as a sheet: the grid is a full working surface
  // (four season tabs, collapsible rounds, a drag-order setup step and two
  // of its own sheets — the owner picker and the CAS-conflict sheet), and
  // stacking sheets inside a sheet is the exact iOS constraint that forced
  // TradeDnaSheet to nest its second layer inside one Modal. A push also
  // gets the shipped `pick-assignment.back-btn` and the #151 iOS-26 header
  // workaround for free, so back is guaranteed live.
  //
  // The room re-reads its board whenever it regains focus AFTER such a push
  // (never on an ordinary focus — the room already polls under its own
  // flag, and an unconditional refetch-on-focus would be a behaviour change
  // for every league). The user who just typed a grid must not come back to
  // the "not assigned" notice they left.
  const cameFromAssignRef = useRef(false);
  const goToAssignPicks = useCallback(() => {
    cameFromAssignRef.current = true;
    navigation?.navigate?.('PickAssignment', { leagueId });
  }, [navigation, leagueId]);

  // W3 M-D — same push-return-invalidate rule as the assignment push above:
  // the room re-reads its board only after returning from a screen that can
  // have changed it, never on an ordinary focus.
  const cameFromRecordRef = useRef(false);
  const goToRecordPicks = useCallback(() => {
    cameFromRecordRef.current = true;
    navigation?.navigate?.('RecordPicks', { leagueId });
  }, [navigation, leagueId]);

  useEffect(() => {
    if (!isFocused) return;
    if (cameFromAssignRef.current) {
      cameFromAssignRef.current = false;
      queryClient.invalidateQueries({ queryKey: ['draft-board', leagueId] });
    }
    if (cameFromRecordRef.current) {
      cameFromRecordRef.current = false;
      queryClient.invalidateQueries({ queryKey: ['draft-board', leagueId] });
    }
  }, [isFocused, queryClient, leagueId]);

  const goToRookieRanks = useCallback(() => {
    // The bridge is two-way as of W1: RookieRanks gets a return route, so
    // acting on a rookie from the board no longer costs your place.
    navigation?.navigate?.('Main', {
      screen: 'Rank',
      params: {
        screen: 'RookieRanks',
        params: { returnTo: 'DraftRoom', returnLeagueId: leagueId },
      },
    });
  }, [navigation, leagueId]);

  const onSaveAnchored = useCallback(
    (playerId: string, res: { value: number }) => {
      // Re-price the row from the SERVER's authoritative answer rather than
      // guessing it client-side: the anchor→value mapping depends on the
      // user's stored pick-value scale (#111) and lives in one place, the
      // backend. Duplicating it here to shave a round-trip would fork a
      // cross-client invariant.
      queryClient.setQueryData<DraftBoard>(
        ['draft-board', leagueId, basis],
        (prev) =>
          prev
            ? {
                ...prev,
                undrafted: prev.undrafted.map((r) =>
                  r.player_id === playerId
                    ? { ...r, value: res.value, valued: true }
                    : r,
                ),
              }
            : prev,
      );
      // The anchor moved the board everywhere, not just here.
      for (const key of ['rankings', 'progress', 'trio', 'tiers-status', 'trends']) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
      queryClient.invalidateQueries({ queryKey: ['draft-board', leagueId] });
    },
    [queryClient, leagueId, basis],
  );

  const addTarget = useCallback(
    (row: UndraftedRow) => {
      if (!leagueId) return;
      setAssetPref(leagueId, row.player_id, 'target')
        .then(() => {
          // The shared key every other targets surface reads.
          queryClient.invalidateQueries({
            queryKey: ['asset-prefs', leagueId],
          });
          setToast({ msg: `${row.name} added to targets`, tone: 'success' });
        })
        .catch(() =>
          setToast({ msg: "Couldn't add to targets", tone: 'warn' }),
        );
    },
    [leagueId, queryClient],
  );

  const menuActionsFor = useCallback(
    (row: UndraftedRow): PlayerMenuAction[] => [
      {
        key: 'set-value',
        label: 'Set my value',
        hint: 'Anchor this rookie on your board',
        testID: 'draft-room.action.set-value',
        onPress: () => {
          track('draft_room_action_taken', {
            action: 'set_value',
            player_id: row.player_id,
            valued: row.valued,
          }, 'DraftRoom');
          setMenuTarget(null);
          setAnchorTarget({
            player_id: row.player_id,
            name: row.name || row.player_id,
            position: row.position,
            team: row.team,
            value: row.value,
            valued: row.valued,
          });
        },
      },
      {
        key: 'rank-rookies',
        label: 'Rank the rookies',
        hint: 'Order the whole class on your own board',
        testID: 'draft-room.action.rank-rookies',
        onPress: () => {
          track('draft_room_action_taken', {
            action: 'rank_rookies',
            player_id: row.player_id,
            valued: row.valued,
          }, 'DraftRoom');
          setMenuTarget(null);
          goToRookieRanks();
        },
      },
      {
        key: 'add-target',
        label: 'Add to targets',
        hint: 'Steer trade ideas toward acquiring him',
        testID: 'draft-room.action.add-target',
        onPress: () => {
          track('draft_room_action_taken', {
            action: 'add_target',
            player_id: row.player_id,
            valued: row.valued,
          }, 'DraftRoom');
          setMenuTarget(null);
          addTarget(row);
        },
      },
    ],
    [goToRookieRanks, addTarget],
  );

  const onRowMenu = useCallback((row: UndraftedRow) => {
    haptics.selection();
    track('draft_room_row_menu_opened', {
      surface: 'draft_room',
      player_id: row.player_id,
      valued: row.valued,
      rank: row.rank,
    }, 'DraftRoom');
    setMenuTarget(row);
  }, []);

  if (!leagueId) {
    return (
      <Shell inTabs={inTabs}>
        <View style={styles.centerFill}>
          <Text testID="draft-room.empty-text" style={styles.emptyBody}>
            Connect a league to see its rookie draft.
          </Text>
        </View>
      </Shell>
    );
  }

  if (query.isLoading) {
    return (
      <Shell inTabs={inTabs}>
        <View style={styles.centerFill}>
          <ActivityIndicator color={ice.base} />
        </View>
      </Shell>
    );
  }

  if (query.isError || !board) {
    const schemaTooNew = query.error instanceof DraftSchemaError;
    return (
      <Shell inTabs={inTabs}>
        <View style={styles.centerFill}>
          <Text testID="draft-room.error-text" style={styles.errorText}>
            {schemaTooNew
              ? 'This draft board needs a newer version of the app.'
              : readErrorCopy(query.error, "Couldn't load the draft room.")}
          </Text>
          {schemaTooNew ? null : (
            <Button label="Try again" variant="ghost" compact onPress={onRefresh} />
          )}
        </View>
      </Shell>
    );
  }

  return (
    <Shell
      // In Mock mode there is nothing to pull-to-refresh: the mock is not a
      // read of the platform, and offering Refresh over it would suggest it
      // was.
      refreshing={!mockMode && query.isFetching && !query.isLoading}
      onRefresh={mockMode ? undefined : onRefresh}
      inTabs={inTabs}
      header={
        mockOn ? (
          <>
            {/* The mock-draft event family (#295/#296/#305) is now
                REGISTERED in `backend/analytics_taxonomy.py` (registration
                commit precedes the emitters) and this screen fires
                `mock_started` / `mock_create_refused` from the create
                mutation. `draft_room_mode_switched` remains unregistered,
                so the toggle itself still deliberately emits nothing. */}
            {/* #292 dead-end 3 — `postRefusal` was never cleared, so ONE
                transient refusal muted the card for the rest of the session.
                Re-entering Mock mode is the user asking again; the card must
                be allowed to answer again. */}
            <DraftModeToggle
              mode={mode}
              onMode={(m) => {
                if (m === 'mock') setPostRefusal(null);
                setMode(m);
              }}
            />
            {/* Pinned, so the marker survives every scroll position. */}
            {mockMode ? (
              <View style={styles.mockRailWrap}>
                <MockRail />
              </View>
            ) : null}
          </>
        ) : null
      }
    >
      {mockMode ? (
        <MockEntryPanel
          loading={mockQuery.isLoading}
          errorText={
            mockQuery.isError
              ? readErrorCopy(mockQuery.error, "Couldn't check for a mock draft.")
              : createMock.isError
                ? readErrorCopy(createMock.error, "Couldn't start a mock draft.")
                : null
          }
          block={mockBlock}
          meta={mockMeta}
          // #292 dead-end 2 — one failed create left a BUTTONLESS card:
          // react-query holds `isError` until the next `mutate`/`reset`, and
          // the error branch rendered no control at all. `reset()` clears the
          // create half, `refetch()` re-answers the query half, and both feed
          // the one `errorText` above — so one control clears both.
          retry={{
            label: 'Try again',
            testID: 'mock-entry.retry',
            onPress: () => {
              createMock.reset();
              mockQuery.refetch();
            },
          }}
          {...mockEntryContent({
            activeMock,
            onStart: () => {
              // Opening the setup sheet is the user asking again. A stale
              // refusal or a stale create error must not survive the ask.
              setPostRefusal(null);
              createMock.reset();
              setSetupOpen(true);
            },
            onResume: () => navigation?.navigate?.('MockDraft', { leagueId }),
          })}
        />
      ) : (
        <>
        <StatusBar board={board} onRefresh={onRefresh} busy={query.isFetching} />
        {rookieScopeOn ? (
          <RankRookiesRow
            onPress={() => {
              // D0 — the bridge row shipped emitting NOTHING. This is the
              // first analytics the Draft Room has ever had.
              track(
                'draft_room_rank_rookies_tapped',
                { state: board.state, from: 'draft_room' },
                'DraftRoom',
              );
              goToRookieRanks();
            }}
          />
        ) : null}
        {board.notice ? (
          <Notice
            board={board}
            showLastYear={showLastYear}
            onToggleLastYear={() => setShowLastYear((v) => !v)}
            onAssignPicks={pickAssignOn ? goToAssignPicks : undefined}
          />
        ) : null}

        {/* The other half of the same operator note: once SOME picks are
            assigned the room renders a real board, and a partly-typed grid
            would otherwise be a silent dead end — a board missing rounds
            with nothing on screen saying so or offering the fix. Renders
            only for a league that actually has an assignment grid. */}
        {assignProgress ? (
          <Pressable
            testID="draft-room.assign-progress"
            onPress={goToAssignPicks}
            accessibilityRole="button"
            accessibilityLabel={`${assignProgress.line}. ${assignProgress.action}`}
            style={({ pressed }) => [styles.assignRow, pressed && { backgroundColor: ink.ink3 }]}
          >
            <View style={styles.assignRowBody}>
              <Text style={styles.assignRowLine}>{assignProgress.line}</Text>
              <Text style={styles.linkText}>{assignProgress.action}</Text>
            </View>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ) : null}

        {/* W3 M-D — the actual draft is happening right now (or is about
            to), and the app can already tell whose pick 1.03 is. Renders
            once the grid is assigned, regardless of how much of it is
            filled in — recording and assigning are independent progress
            bars, and a partly-assigned grid still lets someone start
            recording the slots that ARE owned. */}
        {manualPicksOn && board.platform === 'espn'
          && board.order_confidence === 'assigned' ? (
          <Pressable
            testID="draft-room.record-picks"
            onPress={goToRecordPicks}
            accessibilityRole="button"
            accessibilityLabel="Record picks live"
            style={({ pressed }) => [styles.assignRow, pressed && { backgroundColor: ink.ink3 }]}
          >
            <View style={styles.assignRowBody}>
              <Text style={styles.assignRowLine}>
                {board.picks.length} of {board.order.length} picks recorded
              </Text>
              <Text style={styles.linkText}>Record picks live</Text>
            </View>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ) : null}

        {board.state === 'unavailable' ? (
          <View style={styles.centerFill}>
            <Text testID="draft-room.unavailable-text" style={styles.emptyBody}>
              {board.notice
                ? 'Nothing to show here yet.'
                : "We couldn't reach this league's draft. Pull to refresh."}
            </Text>
          </View>
        ) : (
          <>
            <MyPicksSection board={board} />
            <BoardSection board={board} />
            <UndraftedSection
              board={board}
              basis={basis}
              onBasis={setBasis}
              showLastYear={showLastYear}
              onRowMenu={rowActionsOn ? onRowMenu : undefined}
            />
          </>
        )}

        {/* The platform deep link and the D9 guarantee below it render ONLY
            in Real mode. Printing "Fantasy Trade Finder never drafts for you"
            on a surface that is currently taking mock picks is the exact
            ambiguity the design pass warned option C could create. */}
        {board.deep_link ? (
          <View style={styles.ctaWrap}>
            <Button
              testID="draft-room.deep-link"
              label="Open the draft room"
              variant="primary"
              onPress={() => Linking.openURL(board.deep_link as string)}
            />
            <Text style={styles.ctaNote}>
              Picks are made on the platform — Fantasy Trade Finder never drafts
              for you.
            </Text>
          </View>
        ) : null}
        </>
      )}

      {/* W1 — both sheets are unreachable with `draft.rank_inline` off:
          their targets are only ever set by the flag-gated row handler. */}
      <PlayerContextMenu
        visible={!!menuTarget}
        player={menuTarget ? rowAsPlayer(menuTarget) : null}
        actions={menuTarget ? menuActionsFor(menuTarget) : []}
        onClose={() => setMenuTarget(null)}
      />
      <AnchorSheet
        visible={!!anchorTarget}
        target={anchorTarget}
        via="draft_room"
        onClose={() => setAnchorTarget(null)}
        onSaved={onSaveAnchored}
      />
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      {mockOn ? (
        <MockSetupSheet
          visible={setupOpen}
          teamLabel={mockTeamLabel}
          teams={board.teams}
          defaultRounds={board.rounds}
          orderAssigned={board.order_confidence === 'assigned'}
          busy={createMock.isPending}
          error={
            createMock.isError
              ? readErrorCopy(createMock.error, "Couldn't start a mock draft.")
              : null
          }
          onClose={() => setSetupOpen(false)}
          onStart={(setup) => createMock.mutate(setup)}
        />
      ) : null}
    </Shell>
  );
}

/** The Mock card's words for each reachable state. Split out so the render
 *  stays a single expression and the copy is greppable. */
function mockEntryContent({
  activeMock,
  onStart,
  onResume,
}: {
  activeMock: MockDraftState | null;
  onStart: () => void;
  onResume: () => void;
}) {
  if (activeMock?.status === 'active') {
    const clock = activeMock.on_the_clock;
    const at = clock
      ? `${clock.round}.${String(clock.slot).padStart(2, '0')}`
      : '—';
    return {
      headline: 'Mock in progress',
      body: `You're on the clock at ${at} — ${activeMock.picks.length} of ${activeMock.order.length} picks made.`,
      primary: { label: 'Resume', onPress: onResume, testID: 'mock-entry.resume' },
      // "Start over" is one POST: the create route abandons any prior
      // active row for this user + league in the same transaction, so
      // there is no separate discard call to get wrong.
      secondary: { label: 'Start over', onPress: onStart, testID: 'mock-entry.start-over' },
    };
  }
  if (activeMock?.status === 'complete') {
    return {
      headline: 'Mock complete',
      body: `${activeMock.picks.length} picks. Your league was never touched.`,
      // #292 — the way ONWARD is the primary. Shipped, "View recap" was the
      // primary and starting another was the recessive ghost, so the room
      // read as a terminus. The testIDs stay bound to the ACTION, not the
      // position: `mock-entry.run-it-back` is still start-another and
      // `mock-entry.recap` is still the recap, so no id is added, renamed or
      // orphaned and `testid-lint` is unaffected.
      primary: { label: 'Start a new mock', onPress: onStart, testID: 'mock-entry.run-it-back' },
      secondary: { label: 'View recap', onPress: onResume, testID: 'mock-entry.recap' },
    };
  }
  return {
    headline: 'No mock running',
    body: 'Start one and computer versions of your leaguemates draft against you. They pick for their own rosters — you pick for yours, and nothing is written to your league.',
    primary: { label: 'Start a mock', onPress: onStart, testID: 'mock-entry.start' },
  };
}

/** UndraftedRow → the shared menu's Player shape (header disclosure only). */
function rowAsPlayer(row: UndraftedRow): Player {
  return {
    id: row.player_id,
    name: row.name || row.player_id,
    position: row.position,
    team: row.team,
  };
}

// ── Shell ────────────────────────────────────────────────────────────────

function Shell({
  children,
  refreshing,
  onRefresh,
  inTabs = false,
  header,
}: {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  /** True when rendered inside the seasonal Draft TAB (option A′), where
   *  RootNav's global FAB already covers the screen — mounting our own
   *  would double it (#196/#197). The root-stack push passes nothing. */
  inTabs?: boolean;
  /** W2 — PINNED above the scroll. The mode switch and, in Mock mode, the
   *  mode marker: both have to stay on screen at every scroll position,
   *  which is the whole reason they are not `children`. */
  header?: React.ReactNode;
}) {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {header}
      <ScrollView
        testID="draft-room.scroll"
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          onRefresh ? (
            <RefreshControl
              refreshing={!!refreshing}
              onRefresh={onRefresh}
              tintColor={ice.base}
            />
          ) : undefined
        }
      >
        {children}
      </ScrollView>
      {/* #188 — root-stack push covers RootNav's FAB mount; carry our own.
          No tab bar under this screen → aboveTabBar={false}. Inside the
          seasonal Draft tab the global mount already covers us. */}
      {inTabs ? null : (
        <FeedbackFAB activeScreen="DraftRoom" aboveTabBar={false} />
      )}
    </SafeAreaView>
  );
}

// ── Status bar: state + as_of + manual refresh ───────────────────────────

const STATE_LABEL: Record<DraftBoard['state'], string> = {
  upcoming: 'Not started',
  live: 'Drafting now',
  complete: 'Complete',
  unavailable: 'Unavailable',
};

const DEGRADED_COPY: Record<string, string> = {
  upstream_error: "Couldn't reach the platform",
  breaker_open: 'Pausing updates after repeated failures',
  budget_exceeded: 'Slowing down updates',
  auth_expired: 'Reconnect the league to refresh',
};

function StatusBar({
  board,
  onRefresh,
  busy,
}: {
  board: DraftBoard;
  onRefresh: () => void;
  busy: boolean;
}) {
  const stateColor =
    board.state === 'live'
      ? semantic.pos
      : board.state === 'unavailable'
        ? chalk.faint
        : chalk.dim;
  return (
    <View style={styles.statusBar}>
      <View style={styles.statusMain}>
        <Text testID="draft-room.state" style={[styles.stateLabel, { color: stateColor }]}>
          {STATE_LABEL[board.state]}
        </Text>
        {/* as_of is ALWAYS visible — a board that can't say how old it is
            is a board you can't trust. */}
        <Text testID="draft-room.as-of" style={styles.asOf}>
          {board.stale ? 'Last updated ' : 'Updated '}
          {formatAsOf(board.as_of)}
          {board.degraded ? ` · ${DEGRADED_COPY[board.degraded.reason] ?? 'Degraded'}` : ''}
        </Text>
      </View>
      {/* Manual refresh is present whether or not `draft.live_poll` is on —
          the room must be fully usable with polling dark. */}
      <Pressable
        testID="draft-room.refresh"
        onPress={onRefresh}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel="Refresh the draft board"
        style={({ pressed }) => [
          styles.refreshBtn,
          pressed && { backgroundColor: ink.ink3 },
          busy && { opacity: 0.5 },
        ]}
      >
        <Text style={styles.refreshText}>Refresh</Text>
      </Pressable>
    </View>
  );
}

// ── "Rank the rookies" — the bridge back into RookieRanks ────────────────
// Required by the approved placement mock's finding #2: a draft surface
// that does not lead back to rookie RANKING teaches users the two are
// unrelated features, when in fact the undrafted list below can be ordered
// by exactly the board that link edits. Renders in every board state
// (including `unavailable`) — pre-draft prep is when it matters most, and
// that is precisely when the board has the least to show.

function RankRookiesRow({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      testID="draft-room.rank-rookies"
      accessibilityRole="button"
      accessibilityLabel="Rank the rookies"
      accessibilityHint="Opens your consolidated rookie ranking board"
      onPress={onPress}
      style={({ pressed }) => [
        styles.rankRookiesRow,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <View style={styles.rankRookiesText}>
        <Text style={styles.rankRookiesTitle}>Rank the rookies</Text>
        <Text style={styles.rankRookiesSub}>
          Order this class on your own board — the undrafted list can read
          from it.
        </Text>
      </View>
      <Icon name="chevron-right" size={16} color={chalk.dim} />
    </Pressable>
  );
}

// ── Designed notices ─────────────────────────────────────────────────────

function Notice({
  board,
  showLastYear,
  onToggleLastYear,
  onAssignPicks,
}: {
  board: DraftBoard;
  showLastYear: boolean;
  onToggleLastYear: () => void;
  /** W3 M-B/operator 2026-08-08 — set only for `picks_not_assigned`, and
   *  only while `picks.assign` is on. Its presence IS what turns the notice
   *  from a set of directions into the action itself. */
  onAssignPicks?: () => void;
}) {
  const code = board.notice?.code;
  // Copy lives here, not on the server: the server states the CONDITION,
  // the client says what it means on this screen.
  const copy =
    code === 'order_not_set'
      ? "The draft order isn't set yet, so we're showing who owns each round instead of exact picks."
      : code === 'startup_draft'
        ? "This looks like a startup draft, not a rookie draft — we're not guessing at a rookie list for it."
        : code === 'platform_unsupported'
          ? "Draft rooms aren't available for this platform yet."
          : code === 'class_not_loaded'
            ? `The ${board.season} rookie class loads after the NFL draft (late April).`
            : code === 'mfl_reconnect'
              ? 'Reconnect MyFantasyLeague to refresh this draft.'
              : code === 'picks_not_assigned' && onAssignPicks
                ? // ESPN hosts no rookie draft, so nobody has told FTF who
                  // owns which pick yet. Operator, 2026-08-08: the shipped
                  // server sentence sends the user to the League tab, and
                  // sending someone to another tab to unblock the screen
                  // they are already on is the wrong flow. So the copy
                  // OFFERS the job (the button below does it here) instead
                  // of giving directions, and — per M-B — it must read as
                  // unconfigured, never as an error. If the CTA is NOT
                  // available (a client whose flag cache is behind the
                  // server's), the chain falls through to the server's own
                  // sentence, which still names a working path — never a
                  // dead end that describes a fix it cannot offer.
                  "Nobody has set this league's draft picks yet. Set them here and the board fills in."
                : (board.notice?.message ?? '');
  if (!copy) return null;
  return (
    <View testID={`draft-room.notice.${code}`} style={styles.notice}>
      <Text style={styles.noticeText}>{copy}</Text>
      {code === 'picks_not_assigned' && onAssignPicks ? (
        <Button
          testID="draft-room.assign-picks"
          label="Set the draft picks"
          variant="primary"
          onPress={onAssignPicks}
          style={styles.noticeCta}
        />
      ) : null}
      {code === 'class_not_loaded' ? (
        <Pressable
          testID="draft-room.last-year-toggle"
          onPress={onToggleLastYear}
          accessibilityRole="button"
          accessibilityState={{ selected: showLastYear }}
          style={({ pressed }) => [
            styles.linkBtn,
            pressed && { backgroundColor: ink.ink3 },
          ]}
        >
          <Text style={styles.linkText}>
            {showLastYear ? 'Hide last year’s class' : 'Show last year’s class'}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// ── Your picks ───────────────────────────────────────────────────────────

function MyPicksSection({ board }: { board: DraftBoard }) {
  if (!board.my_picks.length) return null;
  return (
    <View style={styles.section}>
      <TickLabel>Your picks</TickLabel>
      <View style={styles.myPicksRow}>
        {board.my_picks.map((slot, i) => (
          <View key={`${slot.round}-${slot.slot ?? i}`} style={styles.myPickChip}>
            <Text style={styles.myPickLabel}>{slotLabel(slot)}</Text>
            {slot.is_traded ? (
              <Text style={styles.myPickFrom} numberOfLines={1}>
                from {slot.original_username ?? 'another team'}
              </Text>
            ) : null}
          </View>
        ))}
      </View>
    </View>
  );
}

// ── The board ────────────────────────────────────────────────────────────

function BoardSection({ board }: { board: DraftBoard }) {
  // One row per slot, with the pick that landed on it (when one has).
  const pickBySlot = useMemo(() => {
    const m = new Map<string, DraftPick>();
    for (const p of board.picks) {
      m.set(`${p.round}:${p.slot ?? p.pick_no}`, p);
    }
    return m;
  }, [board.picks]);

  if (!board.order.length) {
    // A complete draft with no order still has its picks — show those.
    if (!board.picks.length) return null;
    return (
      <View style={styles.section}>
        <TickLabel>Picks</TickLabel>
        {board.picks.map((p) => (
          <PickRow key={`${p.round}-${p.pick_no}`} pick={p} label={slotLabel(p)} />
        ))}
      </View>
    );
  }

  return (
    <View style={styles.section}>
      <TickLabel>
        {board.order_confidence === 'unset' ? 'Round ownership' : 'Board'}
      </TickLabel>
      {board.order.map((slot, i) => {
        const pick = pickBySlot.get(`${slot.round}:${slot.slot ?? slot.pick_no}`);
        return (
          <View
            key={`${slot.round}-${slot.slot ?? i}`}
            // D0 — the shipped id was shared across every row. The
            // qualifier is the SLOT (round + slot, or `r` when the platform
            // has not published an order), a stable domain id — never `i`.
            testID={`draft-room.order-row.${slot.round}-${slot.slot ?? 'r'}`}
            style={draftRow.orderRow}
          >
            <Text style={draftRow.slotCell}>{slotLabel(slot)}</Text>
            <View style={draftRow.orderMain}>
              <Text style={draftRow.ownerText} numberOfLines={1}>
                {slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'}
                {slot.is_traded ? (
                  <Text style={draftRow.tradedTag}>
                    {'  '}from {slot.original_username ?? '—'}
                  </Text>
                ) : null}
              </Text>
              {pick ? (
                <Text style={draftRow.pickedText} numberOfLines={1}>
                  <Text style={{ color: positionOf(pick.position) }}>
                    {pick.position || '—'}
                  </Text>{' '}
                  {pick.name || pick.player_id}
                  {pick.team ? ` · ${pick.team}` : ''}
                </Text>
              ) : (
                <Text style={draftRow.onTheClock}>Not made yet</Text>
              )}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function PickRow({ pick, label }: { pick: DraftPick; label: string }) {
  return (
    // D0 — `pick_no` is unique within a draft and stable across refetches.
    <View testID={`draft-room.pick-row.${pick.pick_no}`} style={draftRow.orderRow}>
      <Text style={draftRow.slotCell}>{label}</Text>
      <View style={draftRow.orderMain}>
        <Text style={draftRow.pickedText} numberOfLines={1}>
          <Text style={{ color: positionOf(pick.position) }}>
            {pick.position || '—'}
          </Text>{' '}
          {pick.name || pick.player_id}
          {pick.team ? ` · ${pick.team}` : ''}
        </Text>
      </View>
    </View>
  );
}

// ── Undrafted ────────────────────────────────────────────────────────────

function UndraftedSection({
  board,
  basis,
  onBasis,
  showLastYear,
  onRowMenu,
}: {
  board: DraftBoard;
  basis: DraftBasis;
  onBasis: (b: DraftBasis) => void;
  showLastYear: boolean;
  /** W1 — undefined with `draft.rank_inline` off, which is what keeps the
   *  rows inert Views exactly as they shipped. */
  onRowMenu?: (row: UndraftedRow) => void;
}) {
  const suppressedForClass = board.notice?.code === 'class_not_loaded';
  const hidden =
    board.undrafted_suppressed && !(suppressedForClass && showLastYear);
  const rows = board.undrafted;

  // Coverage nudge (W1) — how much of the top of the board you have not
  // priced yet. Source is the payload's own `valued` field; the window is
  // the first COVERAGE_WINDOW entries, and `undrafted[]` is already
  // rank-ordered server-side. `hidden` is part of the condition, not just
  // the render: a startup-draft board suppresses this whole section, and
  // an exposure event for something nobody saw is worse than no event.
  const unvaluedTop = useMemo(
    () => rows.slice(0, COVERAGE_WINDOW).filter((r) => !r.valued).length,
    [rows],
  );
  const nudgeOn = !hidden && !!onRowMenu && unvaluedTop > 0;
  React.useEffect(() => {
    if (!nudgeOn) return;
    track(
      'draft_room_coverage_nudge_shown',
      { unvalued_count: unvaluedTop, window: COVERAGE_WINDOW },
      'DraftRoom',
    );
  }, [nudgeOn, unvaluedTop]);

  if (hidden) return null;
  const anyUnvalued = rows.some((r) => !r.valued);

  return (
    <View style={styles.section}>
      <TickLabel>Still on the board</TickLabel>
      <View style={draftRow.basisRow}>
        <BasisChip
          testID="draft-room.basis.consensus"
          label="Consensus"
          active={basis === 'consensus'}
          onPress={() => onBasis('consensus')}
        />
        <BasisChip
          testID="draft-room.basis.my-board"
          label="My board"
          active={basis === 'my_board'}
          onPress={() => onBasis('my_board')}
        />
      </View>
      {/* FreeAgents-style fallback notice — say which numbers these are.
          The strings live in DraftRows so the mock says the same thing. */}
      {basis === 'my_board' ? (
        <Text style={draftRow.fallbackNote}>{MY_BOARD_FALLBACK_COPY}</Text>
      ) : null}
      {anyUnvalued ? (
        <Text style={draftRow.fallbackNote}>{NO_CONSENSUS_VALUE_COPY}</Text>
      ) : null}
      {nudgeOn ? (
        <Text testID="draft-room.coverage-nudge" style={styles.coverageNudge}>
          {unvaluedTop} of the top {COVERAGE_WINDOW} have no value on your
          board. Hold a row to set one.
        </Text>
      ) : null}
      {rows.length === 0 ? (
        <Text testID="draft-room.undrafted-empty" style={styles.emptyBody}>
          Every rookie is off the board.
        </Text>
      ) : (
        rows.map((r) => (
          <UndraftedRowView key={r.player_id} row={r} onMenu={onRowMenu} />
        ))
      )}
    </View>
  );
}

/** The undrafted rookie row — W1's row, EXPORTED in W2.
 *
 *  It stays in this file on purpose. `backend/tests/test_draft_extensions_w1.py`
 *  pins W1's client-side kill switch and its per-player testID to THIS
 *  source file, and this wave owns `mobile/` only, so the tidier home
 *  (`components/draft/DraftRows`, where the styles and basis chips did go)
 *  would have broken a green backend test it may not edit. The mock imports
 *  this component rather than copying it, so there is still exactly one
 *  undrafted row in the app — which is the property that actually matters.
 */
export function UndraftedRowView({
  row,
  onMenu,
  onPress,
  selected = false,
  actionLabel,
  testID: testIDOverride,
}: {
  row: UndraftedRow;
  /** W1 (`draft.rank_inline`) — undefined keeps the row inert. */
  onMenu?: (row: UndraftedRow) => void;
  /** W2, mock only — selects the row for the confirm bar. */
  onPress?: (row: UndraftedRow) => void;
  selected?: boolean;
  /** W2, mock only — the trailing affordance on the selected row. */
  actionLabel?: string;
  /** W2, mock only — the mock surface namespaces its own rows
   *  (`mock-draft.undrafted-row.<player_id>`). The room never passes it,
   *  so the room's id is the literal default below. */
  testID?: string;
}) {
  // Per-player testID (D0). The shipped id was shared across every row,
  // which is why this flow was untestable; the qualifier is the stable
  // domain id per mobile/src/components/CLAUDE.md — never a list index.
  const testID = testIDOverride ?? `draft-room.undrafted-row.${row.player_id}`;
  // #277 — the tier walk is format-scoped; the room prices in the
  // session's active format (same map the board's Elo values came from).
  const rowFormat = useSession((s) => s.activeFormat);
  const body = (
    <>
      <Text style={draftRow.rankCell}>{row.rank}</Text>
      <View style={draftRow.orderMain}>
        <Text style={draftRow.playerName} numberOfLines={1}>
          {row.name || row.player_id}
        </Text>
        <Text style={draftRow.playerMeta} numberOfLines={1}>
          <Text style={{ color: positionOf(row.position) }}>
            {row.position || '—'}
          </Text>
          {row.team ? ` · ${row.team}` : ''}
          {/* #291 — when the action label takes the trailing slot, whatever
              that slot was showing is RELOCATED here, never deleted: #277's
              tier badge for a valued row, and D7's honest "No value" for a
              row the board has no price for. The trailing slot holds one
              thing at a time; the meta line already carries the row's
              secondary facts and has the width for one more. */}
          {!actionLabel
            ? ''
            : row.valued
              ? ` · ${TIER_LABEL[tierForElo(
                  row.value as number,
                  row.position as Position,
                  rowFormat ?? '1qb_ppr',
                )]}`
              : ' · No value'}
        </Text>
      </View>
      {/* #291 — the affordance is visible BEFORE the tap. The shipped gate
          was `actionLabel && selected`, which made a mock row pixel-identical
          to the read-only room row until after it had been tapped: the
          capability was announced to VoiceOver (`accessibilityHint`, below)
          and to nobody else. `actionLabel` is itself gated on the user's turn
          by the caller, so the CPU-turn render is byte-identical to today. */}
      {actionLabel ? (
        <Text style={draftRow.rowAction}>{actionLabel}</Text>
      ) : row.valued ? (
        // #277 — the board's raw-Elo `value` renders as its pick-tier
        // label (client tierForElo walk — the payload's value IS on the
        // raw Elo scale, both bases). Unvalued rows keep the honest text.
        <View style={draftRow.tierSlot}>
          <TierBadge
            tier={tierForElo(
              row.value as number,
              row.position as Position,
              rowFormat ?? '1qb_ppr',
            )}
            size="sm"
          />
        </View>
      ) : (
        <Text style={draftRow.noValueCell}>No value</Text>
      )}
    </>
  );

  // Flag off ⇒ the exact inert View this row shipped as.
  if (!onMenu) {
    // W2 keeps that guard verbatim and nests its own: a mock row is the
    // only OTHER thing that can make a row live, and it never reaches the
    // room (which passes no `onPress`).
    if (!onPress) {
      return (
        <View testID={testID} style={draftRow.undraftedRow}>
          {body}
        </View>
      );
    }
  }

  // Long-press + an `accessibilityActions` custom action — the shipped
  // TradeCard vocabulary (RB-12). The custom action is not optional
  // garnish: a long-press-only control is unreachable to assistive tech,
  // and a VISIBLE overflow glyph would be net-new to the Chalkline system
  // and needs a components.md spec first.
  return (
    <Pressable
      testID={testID}
      accessible
      accessibilityRole="button"
      accessibilityLabel={`${row.name || row.player_id}, ${row.position || ''}${
        row.valued ? '' : ', no value on your board'
      }`}
      accessibilityHint={
        onPress ? 'Select this rookie, then confirm the pick' : 'Hold for player options'
      }
      accessibilityState={onPress ? { selected } : undefined}
      accessibilityActions={onMenu ? [{ name: 'menu', label: 'Player options' }] : undefined}
      onAccessibilityAction={(e) => {
        if (e.nativeEvent.actionName === 'menu' && onMenu) onMenu(row);
      }}
      onPress={onPress ? () => onPress(row) : undefined}
      onLongPress={onMenu ? () => onMenu(row) : undefined}
      style={({ pressed }) => [
        draftRow.undraftedRow,
        selected && draftRow.undraftedRowSelected,
        pressed && { backgroundColor: ink.ink1 },
      ]}
    >
      {body}
    </Pressable>
  );
}

// ── helpers ──────────────────────────────────────────────────────────────
// `BasisChip`, `positionOf`, `slotLabel`, the row styles and the fallback
// copy moved to `components/draft/DraftRows` in W2 — unchanged, but now
// shared with the mock surface so the two lists cannot drift apart.

/** Relative age, so a stale board reads as stale at a glance. */
function formatAsOf(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'just now';
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return 'just now';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xxxl,
    gap: space.md,
  },

  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    marginTop: space.md,
  },
  statusMain: { flex: 1, gap: 2 },
  stateLabel: { ...type.label },
  asOf: { ...type.bodySm, color: chalk.faint },
  refreshBtn: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  refreshText: { ...type.label, color: ice.base },

  rankRookiesRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 44,
  },
  rankRookiesText: { flex: 1, gap: 2 },
  rankRookiesTitle: { ...type.label, color: ice.base },
  rankRookiesSub: { ...type.bodySm, color: chalk.faint },

  noticeCta: { marginTop: space.sm, alignSelf: 'flex-start' },
  assignRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 48,
    paddingHorizontal: space.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  assignRowBody: { flex: 1, gap: 2 },
  assignRowLine: { ...type.bodySm, color: chalk.base },
  notice: {
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    gap: space.sm,
  },
  noticeText: { ...type.bodySm, color: chalk.base },
  linkBtn: {
    alignSelf: 'flex-start',
    borderRadius: radii.sm,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  linkText: { ...type.label, color: ice.base },

  section: { gap: space.sm },

  myPicksRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  myPickChip: {
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  myPickLabel: { ...type.data, color: chalk.base },
  myPickFrom: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  // The row / basis-chip styles moved to components/draft/DraftRows.

  // W1 coverage nudge — flare is the informational-highlight accent
  // (ADR-005); ice stays reserved for actions.
  coverageNudge: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderColor: flare.base,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },

  // W2 — the pinned mode marker sits between the toggle and the scroll.
  mockRailWrap: { marginTop: space.md },

  ctaWrap: { gap: space.sm, marginTop: space.md },
  ctaNote: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },

  centerFill: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xl,
    gap: space.sm,
  },
  emptyBody: { ...type.bodySm, textAlign: 'center' },
  errorText: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
});
