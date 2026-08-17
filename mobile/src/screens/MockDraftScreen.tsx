// Mock Draft session (draft-extensions W2, flag `draft.mock`, ships OFF).
//
// The room's `Real draft | Mock` switch (placement option C) is the ENTRY;
// this pushed screen is the SESSION — the only surface in this app where a
// pick can be made, and therefore the only one that has to prove, at every
// scroll position and in every sub-state, that the pick is a simulation.
//
// ── The mode-marking contract ───────────────────────────────────────────
// `MockRail` renders OUTSIDE the ScrollView, above every branch below —
// loading, error, each typed-empty refusal, the live board, the confirm
// step and the recap. There is exactly ONE `return` in this component and
// the rail is above the branch, which is what makes "in every sub-state"
// structural rather than a promise; `mobile/tests/check-mock-mode-marker.js`
// fails the build if a mock branch escapes it.
//
// The corollary is a SUBTRACTION: the platform deep link and the room's
// "Picks are made on the platform — Fantasy Trade Finder never drafts for
// you" note are not rendered here at all. That sentence is true of the real
// room and the mock does not contradict it — but printed above a board that
// accepts taps it would read as a guarantee about THIS board, which is the
// exact ambiguity the design pass warned option C could create.
//
// ── No polling ──────────────────────────────────────────────────────────
// A mock only changes when the user acts, so this screen never touches the
// room's RV-8 refetchInterval machinery: `staleTime: Infinity`, no
// interval, no refetch-on-focus. Every state transition arrives as a
// MUTATION RESPONSE — one request per user pick, with the whole CPU tail
// already resolved in it.
//
// ── Reused verbatim ─────────────────────────────────────────────────────
// `UndraftedRowView`, `BasisChip` + the my-board fallback copy, the order
// row styles (`components/draft/DraftRows`), `TickLabel`, `Toast`,
// `Button`, `PlayerContextMenu` + W1's `AnchorSheet` on long-press. The
// row-action lane stays behind W1's own flag (`draft.rank_inline`) — this
// screen must not ship W1 behavior unflagged.
//
// ── Analytics (#295/#296/#305) ──────────────────────────────────────────
// The five mock events are REGISTERED in `backend/analytics_taxonomy.py`
// (the registration commit precedes the emitters — DEFAULT-DENY silently
// drops unregistered names behind a 200). This screen fires the three
// session-side events: `mock_pick_made` (slot captured in `onMutate` — the
// response's `on_the_clock` is the NEXT slot), `mock_completed`
// (NON_INTENT, fired only on the active→complete transition, never from a
// GET) and `mock_abandoned`. `DraftRoomScreen` fires the create-side pair.

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, flare, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import { Button, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import PlayerContextMenu, { type PlayerMenuAction } from '../components/PlayerContextMenu';
import AnchorSheet, { type AnchorTarget } from '../components/AnchorSheet';
import Toast from '../components/Toast';
import TierBadge from '../components/TierBadge';
import { MockRail } from '../components/draft/MockChrome';
import MockTeamSheet from '../components/draft/MockTeamSheet';
import {
  BasisChip,
  MY_BOARD_FALLBACK_COPY,
  NO_CONSENSUS_VALUE_COPY,
  draftRow,
  positionOf,
} from '../components/draft/DraftRows';
// The undrafted row itself is imported from the ROOM, not copied: W1's
// source tests pin it to that file (see the note in DraftRows), and one row
// shared beats two rows that agree today.
import { UndraftedRowView } from './DraftRoomScreen';
import {
  DraftSchemaError,
  type DraftBasis,
  type UndraftedRow,
} from '../api/draft';
import {
  abandonMockDraft,
  getMockDraft,
  isMockEmpty,
  pickInMockDraft,
  type MockDraftResponse,
  type MockDraftState,
  type MockOwnershipSource,
  type MockPick,
} from '../api/mockDraft';
import { setAssetPref } from '../api/league';
import { track } from '../api/events';
import { readErrorCopy } from '../utils/verification';
import { haptics } from '../utils/haptics';
import { tickerWindow } from '../utils/tickerWindow';
import {
  filterPool,
  POOL_POSITIONS,
  type PoolPositionFilter,
} from '../utils/mockPool';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Player } from '../shared/types';

/** How many recent picks the ticker shows. Enough to see the run that
 *  happened while you were away, short enough not to become the page. */
const TICKER_DEPTH = 8;

/** #328 — the ownership-provenance disclosure, ONE caption for ONE fact,
 *  rendered from `settings_echo.ownership_source` only. `partial`
 *  deliberately drops the platform-vs-user provenance suffix; null /
 *  undefined / any unknown future value renders nothing (a pre-#328 row is
 *  UNKNOWN, never "none"). Exported for the structural check. */
export function ownershipCaption(src: MockOwnershipSource | null | undefined): string | null {
  if (src === 'platform') return 'Real pick ownership applied';
  if (src === 'user') return 'Real pick ownership applied · entered by your league';
  if (src === 'partial') return 'Some real pick ownership applied — other slots use draft order';
  if (src === 'none') return 'Traded picks unavailable — each team drafts its own slot';
  return null; // null / undefined / unknown future value → render nothing
}

/** Plain-words persona labels. The engine's outlook enum is shared with the
 *  trade side (`league_preferences.team_outlook`); this is the same
 *  vocabulary the Hub shows, not a second one. */
const OUTLOOK_LABEL: Record<string, string> = {
  championship: 'all-in',
  contender: 'contending',
  not_sure: 'no clear lean',
  rebuilder: 'rebuilding',
  jets: 'tanking',
};

export default function MockDraftScreen({ route, navigation }: any = {}) {
  const paramLeagueId: string | undefined = route?.params?.leagueId;
  const sessionLeagueId = useSession((s) => s.league?.league_id);
  const leagueId = paramLeagueId ?? sessionLeagueId;

  const [basis, setBasis] = useState<DraftBasis>('consensus');
  const [selected, setSelected] = useState<UndraftedRow | null>(null);
  const [menuTarget, setMenuTarget] = useState<UndraftedRow | null>(null);
  const [anchorTarget, setAnchorTarget] = useState<AnchorTarget | null>(null);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  // #326/#327 — pool controls + the team sheet.
  const [posFilter, setPosFilter] = useState<PoolPositionFilter>('ALL');
  const [poolQuery, setPoolQuery] = useState('');
  const [teamSheetOpen, setTeamSheetOpen] = useState(false);
  // mock_pool_searched fires at most ONCE per turn (scope.md §1) — never per
  // keystroke. Reset alongside the controls on every clock advance.
  const searchedTurnRef = useRef(false);

  const queryClient = useQueryClient();
  const rowActionsOn = useFlag('draft.rank_inline');

  const query = useQuery({
    queryKey: ['mock-draft', leagueId, basis],
    queryFn: () => getMockDraft(leagueId as string, basis),
    enabled: !!leagueId,
    // The no-polling guarantee, stated rather than assumed: a mock changes
    // only when the user acts, and every act returns the new state.
    staleTime: Infinity,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });

  const res = query.data;
  const state: MockDraftState | null =
    res && !isMockEmpty(res) ? (res as MockDraftState) : null;
  const emptyReason = res && isMockEmpty(res) ? res.reason : null;

  const onClock = state?.on_the_clock ?? null;
  const isUserTurn = state?.status === 'active' && !!onClock?.is_user;
  const userOwnerId = useMemo(() => resolveUserOwnerId(state), [state]);
  // #305 — whether the slot on the clock belongs to the USER'S OWN team.
  // In cpu mode this is always true on the user's turn; in manual mode it
  // distinguishes "your pick" from "you're picking for {team}". Keys off
  // `user_owner_id`, never off `by` (HLD §4.3).
  const forOwnTeam =
    !onClock?.roster_id || !userOwnerId || String(onClock.roster_id) === userOwnerId;

  // #326/#327 R-12 (operator decision) — when the clock advances, the
  // filter goes back to All AND the search clears, in BOTH modes: a stale
  // narrow view silently hiding the pool on a new turn is the trap this
  // kills. Also re-arms the once-per-turn search event.
  useEffect(() => {
    setPosFilter('ALL');
    setPoolQuery('');
    searchedTurnRef.current = false;
  }, [state?.on_the_clock?.pick_no]);

  // LEAGUE platform from the session league cache — never the device
  // platform (the screen's standing convention for the mock family).
  const leaguePlatform = useCallback(
    () =>
      useSession.getState().leagues.find((lg) => lg.league_id === leagueId)
        ?.platform ?? 'unknown',
    [leagueId],
  );

  // #326 — the "Your team" sheet. A modal over the live draft, never
  // navigation: the screen (and the clock) never unmounts.
  const openTeamSheet = useCallback(() => {
    setTeamSheetOpen(true);
    track(
      'mock_team_sheet_opened',
      {
        platform: leaguePlatform(),
        mode: state?.settings_echo?.mode ?? null,
        round: onClock?.round ?? null,
        pick_no: onClock?.pick_no ?? null,
      },
      'MockDraft',
    );
  }, [leaguePlatform, state?.settings_echo?.mode, onClock?.round, onClock?.pick_no]);

  // #326 — a non-All chip is the tracked decision; the All chip is the
  // reset and fires nothing.
  const onSelectFilter = useCallback(
    (f: PoolPositionFilter) => {
      setPosFilter(f);
      if (f !== 'ALL') {
        track(
          'mock_pool_filtered',
          {
            platform: leaguePlatform(),
            mode: state?.settings_echo?.mode ?? null,
            position: f,
          },
          'MockDraft',
        );
      }
    },
    [leaguePlatform, state?.settings_echo?.mode],
  );

  // #327 — once per turn, on the first non-empty query. The query string
  // itself is never sent.
  const onPoolQuery = useCallback(
    (text: string) => {
      setPoolQuery(text);
      if (text.trim() && !searchedTurnRef.current) {
        searchedTurnRef.current = true;
        track(
          'mock_pool_searched',
          {
            platform: leaguePlatform(),
            mode: state?.settings_echo?.mode ?? null,
            filter_position: posFilter,
          },
          'MockDraft',
        );
      }
    },
    [leaguePlatform, state?.settings_echo?.mode, posFilter],
  );

  // ── mutations ─────────────────────────────────────────────────────────

  const applyResponse = useCallback(
    (next: MockDraftResponse) => {
      // The pick route answers with the CONSENSUS ordering; writing that
      // into a my_board cache key would silently relabel the list. Seed the
      // key it actually is, invalidate the rest.
      queryClient.setQueryData(['mock-draft', leagueId, 'consensus'], next);
      queryClient.invalidateQueries({ queryKey: ['mock-draft', leagueId] });
    },
    [queryClient, leagueId],
  );

  // The slot the user is about to fill, captured BEFORE the mutation: the
  // response's `on_the_clock` is the NEXT slot and must not be read for the
  // pick event's round/pick_no.
  const pickedSlotRef = useRef<{
    round: number;
    pick_no: number;
    roster_id: string | null;
    prevStatus: string | null;
  } | null>(null);

  const pickMutation = useMutation({
    mutationFn: (row: UndraftedRow) =>
      pickInMockDraft(state?.mock_id as number, row.player_id),
    onMutate: () => {
      pickedSlotRef.current = onClock
        ? {
            round: onClock.round,
            pick_no: onClock.pick_no,
            roster_id: onClock.roster_id,
            prevStatus: state?.status ?? null,
          }
        : null;
    },
    onSuccess: (next) => {
      haptics.selection();
      setSelected(null);
      const picked = pickedSlotRef.current;
      pickedSlotRef.current = null;
      if (next && !isMockEmpty(next)) {
        const ns = next as MockDraftState;
        const echo = ns.settings_echo;
        // LEAGUE platform from the session league cache — never the device
        // platform, never inferred from the id's shape.
        const platform =
          useSession.getState().leagues.find((lg) => lg.league_id === leagueId)
            ?.platform ?? 'unknown';
        if (picked) {
          track(
            'mock_pick_made',
            {
              platform,
              mode: echo?.mode ?? null,
              round: picked.round,
              pick_no: picked.pick_no,
              // "My team" is user_owner_id vs the slot's owner — NEVER `by`
              // (in manual mode every pick is `by: "user"`). Always true in
              // cpu mode.
              for_own_team:
                picked.roster_id != null && echo?.user_owner_id
                  ? String(picked.roster_id) === String(echo.user_owner_id)
                  : true,
            },
            'MockDraft',
          );
          // NON_INTENT outcome, fired only on the active → complete
          // transition — a resumed recap render is structurally unable to
          // re-emit because a GET never runs this handler.
          if (picked.prevStatus === 'active' && ns.status === 'complete') {
            track(
              'mock_completed',
              {
                platform,
                mode: echo?.mode ?? null,
                rounds: echo?.rounds ?? null,
                teams: echo?.teams ?? null,
                // The user's TEAM's picks — never a `by === "user"` count,
                // which would be every pick in manual mode.
                user_picks: ns.my_picks.length,
              },
              'MockDraft',
            );
          }
        }
      }
      applyResponse(next);
    },
    onError: (err) => {
      pickedSlotRef.current = null;
      setSelected(null);
      setToast({ msg: readErrorCopy(err, "Couldn't make that pick."), tone: 'warn' });
    },
  });

  const endMock = useCallback(() => {
    const mockId = state?.mock_id;
    if (mockId == null) {
      navigation?.goBack?.();
      return;
    }
    // #292 dead-end 1 — a completed mock stayed "current" forever, and the
    // only dismissal control was hidden once it completed. The same control
    // now clears a recap; only the words change, because "End this mock?"
    // over a finished board describes something that already happened.
    //
    // The backend's abandon route clears the caller's WHOLE completed backlog
    // for this league, not just this row (`abandon_completed_mock_drafts`) —
    // completed rows accumulate one per finished mock and only the newest is
    // reachable, so a per-row dismissal merely paginated the dead end. The
    // copy promises what the route now actually does: one clear, and the room
    // is free. Nothing observable is destroyed — the older rows had no UI.
    const done = state?.status === 'complete';
    Alert.alert(
      done ? 'Clear this recap?' : 'End this mock?',
      done
        ? 'The recap is discarded. You can start a new mock any time — your league was never touched.'
        : 'The board and your picks are discarded. Your league is untouched — nothing here was ever written to it.',
      [
        { text: done ? 'Keep it' : 'Keep drafting', style: 'cancel' },
        {
          text: done ? 'Clear' : 'End mock',
          style: 'destructive',
          onPress: () => {
            // INTENT — the tap is the decision; the network result is not.
            // Fired BEFORE the abandon promise on purpose.
            track(
              'mock_abandoned',
              {
                platform:
                  useSession.getState().leagues.find((lg) => lg.league_id === leagueId)
                    ?.platform ?? 'unknown',
                mode: state?.settings_echo?.mode ?? null,
                picks_made: state?.picks.length ?? 0,
              },
              'MockDraft',
            );
            abandonMockDraft(mockId)
              .catch(() => undefined)
              .finally(() => {
                queryClient.invalidateQueries({ queryKey: ['mock-draft', leagueId] });
                navigation?.goBack?.();
              });
          },
        },
      ],
    );
  }, [state, navigation, queryClient, leagueId]);

  useLayoutEffect(() => {
    const done = state?.status === 'complete';
    navigation?.setOptions?.({
      // `headerRight` is a `useLayoutEffect` callback, OUTSIDE the component's
      // single return — adding the `complete` case cannot introduce a second
      // top-level return or escape the mode rail.
      headerRight: () =>
        state?.status === 'active' || done ? (
          <Pressable
            testID="mock-draft.end"
            onPress={endMock}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={done ? 'Clear this mock draft recap' : 'End this mock draft'}
          >
            <Text style={styles.headerAction}>{done ? 'Clear' : 'End'}</Text>
          </Pressable>
        ) : null,
    });
  }, [navigation, state?.status, endMock]);

  // ── W1 row actions (behind `draft.rank_inline`, as in the room) ───────

  const addTarget = useCallback(
    (row: UndraftedRow) => {
      if (!leagueId) return;
      setAssetPref(leagueId, row.player_id, 'target')
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
          setToast({ msg: `${row.name} added to targets`, tone: 'success' });
        })
        .catch(() => setToast({ msg: "Couldn't add to targets", tone: 'warn' }));
    },
    [leagueId, queryClient],
  );

  const menuActionsFor = useCallback(
    (row: UndraftedRow): PlayerMenuAction[] => [
      {
        key: 'set-value',
        label: 'Set my value',
        hint: 'Anchor this rookie on your board',
        testID: 'mock-draft.action.set-value',
        onPress: () => {
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
        key: 'add-target',
        label: 'Add to targets',
        hint: 'Steer trade ideas toward acquiring him',
        testID: 'mock-draft.action.add-target',
        onPress: () => {
          setMenuTarget(null);
          addTarget(row);
        },
      },
    ],
    [addTarget],
  );

  const onRowMenu = useCallback((row: UndraftedRow) => {
    haptics.selection();
    setMenuTarget(row);
  }, []);

  // ── derived view models ───────────────────────────────────────────────

  const personaLine = useMemo(() => {
    if (!state || !onClock?.roster_id) return null;
    // gap G4 — `on_the_clock` carries no name and no persona, so both are
    // client-side joins: roster_id → order[] for the username, and →
    // settings_echo.personas for the outlook that explains the pick.
    const persona = state.settings_echo?.personas?.[String(onClock.roster_id)];
    if (!persona) return null;
    const label = OUTLOOK_LABEL[persona.outlook] ?? persona.outlook;
    return persona.source === 'default' ? label : `${label} · ${persona.source}`;
  }, [state, onClock?.roster_id]);

  // ONE owner-name map for every active-board render site (clock card,
  // ticker who-column) — same D-16 ladder the recap rail applies. A map
  // miss is an owner the order cannot name, and every consumer falls back
  // to its own honest placeholder rather than a raw id.
  const ownerNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of state?.order ?? []) {
      if (o.owner_user_id) m.set(o.owner_user_id, ownerNameOf(o.owner_username, o.owner_user_id));
    }
    return m;
  }, [state?.order]);

  const clockName = onClock?.roster_id
    ? ownerNames.get(String(onClock.roster_id)) ?? null
    : null;

  /** Picks that landed since the user's last one — the run they missed. */
  const sinceUserPick = useMemo(() => {
    if (!state) return 0;
    const lastUser = [...state.picks].reverse().find((p) => p.by === 'user');
    if (!lastUser) return 0;
    return state.picks.filter((p) => p.pick_no > lastUser.pick_no).length;
  }, [state]);

  const myPickSlots = useMemo(() => {
    if (!state || !userOwnerId) return [];
    const madeByNo = new Map(state.picks.map((p) => [p.pick_no, p]));
    return state.order
      .filter((o) => o.owner_user_id === userOwnerId)
      .map((o) => ({ slot: o, pick: madeByNo.get(o.pick_no) ?? null, isTraded: o.is_traded }));
  }, [state, userOwnerId]);

  // #326/#327 — the undrafted list's ONE render source: position filter
  // first, then search scoped to that subset, composed inside the tested
  // helper (`utils/mockPool`) — never inline in JSX (PRD R-11/R-13).
  const visiblePool = useMemo(
    () => filterPool(state?.undrafted ?? [], posFilter, poolQuery),
    [state?.undrafted, posFilter, poolQuery],
  );

  const railStatus =
    state?.status === 'complete'
      ? `complete · ${state.picks.length} picks`
      : state?.status === 'active'
        ? `pick ${onClock?.pick_no ?? '—'} of ${state.order.length}`
        : undefined;

  // ── one return; the rail is ABOVE the branch, by construction ─────────

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <MockRail status={railStatus} testID="mock-draft.rail" />
      <ScrollView
        testID="mock-draft.scroll"
        contentContainerStyle={styles.scrollContent}
        // #327 R-14 — a row tap while the keyboard is up drafts in ONE tap.
        keyboardShouldPersistTaps="handled"
      >
        {!leagueId ? (
          <Text testID="mock-draft.empty-text" style={styles.emptyBody}>
            Connect a league to run a mock draft.
          </Text>
        ) : query.isLoading ? (
          <View style={styles.centerFill}>
            <ActivityIndicator color={ice.base} />
          </View>
        ) : query.isError ? (
          <View style={styles.centerFill}>
            <Text testID="mock-draft.error-text" style={styles.errorText}>
              {query.error instanceof DraftSchemaError
                ? 'This mock draft needs a newer version of the app.'
                : readErrorCopy(query.error, "Couldn't load the mock draft.")}
            </Text>
            <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
          </View>
        ) : !state ? (
          <View style={styles.centerFill}>
            <Text testID={`mock-draft.empty.${emptyReason ?? 'unknown'}`} style={styles.emptyBody}>
              {emptyCopy(emptyReason)}
            </Text>
            <Button
              label="Back to the draft room"
              variant="ghost"
              compact
              onPress={() => navigation?.goBack?.()}
            />
          </View>
        ) : state.status === 'complete' ? (
          <Recap state={state} userOwnerId={userOwnerId} />
        ) : (
          <>
            <OnTheClockCard
              onClock={onClock}
              isUser={isUserTurn}
              forOwnTeam={forOwnTeam}
              who={clockName}
              persona={personaLine}
              total={state.order.length}
              made={state.picks.length}
              ownershipSource={state.settings_echo?.ownership_source ?? null}
              onViewTeam={openTeamSheet}
            />

            <PickTicker
              picks={state.picks}
              newest={sinceUserPick}
              userOwnerId={userOwnerId}
              nameOf={ownerNames}
            />

            {myPickSlots.length ? (
              <View style={styles.section}>
                <TickLabel>Your picks</TickLabel>
                {/* #323/#324 — equal-width three-across grid; wrap, NEVER an
                    inner scroll (a nested scrollable is the gesture-capture
                    class that broke TestFlight builds #11/#12). A made
                    pick's chip: slot numeral, meta line of position + tier
                    (server-computed `pick.tier` through TierBadge — never
                    client-derived, #263/#277/#278), then the surname. */}
                <View style={styles.myPicksRow}>
                  {myPickSlots.map(({ slot, pick, isTraded }) => (
                    <View key={slot.pick_no} style={styles.myPickChip}>
                      <Text style={styles.myPickLabel}>{pickLabelOf(slot)}</Text>
                      {pick ? (
                        <>
                          <View style={styles.myPickMeta}>
                            <Text
                              style={[styles.myPickPos, { color: positionOf(pick.position) }]}
                              numberOfLines={1}
                            >
                              {pick.position || '—'}
                            </Text>
                            <TierBadge tier={pick.tier ?? null} size="sm" />
                          </View>
                          <Text style={styles.myPickFrom} numberOfLines={1}>
                            {lastName(pick.name || pick.player_id)}
                          </Text>
                        </>
                      ) : (
                        <Text style={styles.myPickFrom} numberOfLines={1}>
                          {slot.pick_no === onClock?.pick_no
                            ? 'on the clock'
                            : isTraded
                              ? `from ${slot.original_username ?? 'another team'}`
                              : ''}
                        </Text>
                      )}
                    </View>
                  ))}
                </View>
              </View>
            ) : null}

            <View style={styles.section}>
              {/* #291 — the section header states the affordance while the
                  user is on the clock. Maestro cannot assert on a style and
                  can assert on text, so this string is the flow's acceptance
                  for "visible before tap". Deliberately NOT the room's
                  platform-guarantee copy: this board really does take taps. */}
              <TickLabel>{isUserTurn ? 'Tap to draft' : 'Still on the board'}</TickLabel>
              <View style={draftRow.basisRow}>
                <BasisChip
                  testID="mock-draft.basis.consensus"
                  label="Consensus"
                  active={basis === 'consensus'}
                  onPress={() => setBasis('consensus')}
                />
                <BasisChip
                  testID="mock-draft.basis.my-board"
                  label="My board"
                  active={basis === 'my_board'}
                  onPress={() => setBasis('my_board')}
                />
              </View>
              {basis === 'my_board' ? (
                <Text style={draftRow.fallbackNote}>{MY_BOARD_FALLBACK_COPY}</Text>
              ) : null}
              {state.undrafted.some((r) => !r.valued) ? (
                <Text style={draftRow.fallbackNote}>{NO_CONSENSUS_VALUE_COPY}</Text>
              ) : null}
              {/* The CPU drafters always ranked against CONSENSUS. Saying so
                  under a my-board list stops "why did he go there?" from
                  becoming a bug report. */}
              {basis === 'my_board' ? (
                <Text style={styles.cpuBasisNote}>
                  The computer drafters use consensus values, not your board.
                </Text>
              ) : null}
              {/* #326 R-11 — position filter, the PositionTabs construction
                  (hairline group; active segment = ink3 well + underline in
                  the position's color, ice for All). */}
              <View style={styles.posFilterRow}>
                {(['ALL', ...POOL_POSITIONS] as const).map((f) => {
                  const active = posFilter === f;
                  return (
                    <Pressable
                      key={f}
                      testID={`mock-draft.pos-filter.${f.toLowerCase()}`}
                      accessibilityRole="tab"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={f === 'ALL' ? 'All positions' : f}
                      onPress={() => onSelectFilter(f)}
                      style={({ pressed }) => [
                        styles.posFilterSegment,
                        active && [
                          styles.posFilterSegmentActive,
                          {
                            borderBottomColor:
                              f === 'ALL' ? ice.base : positionOf(f),
                          },
                        ],
                        pressed && { backgroundColor: ink.ink3 },
                      ]}
                    >
                      <Text
                        style={[styles.posFilterText, active && styles.posFilterTextActive]}
                      >
                        {f}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              {/* #327 R-13 — search scopes to the active filter subset
                  (composition lives in `filterPool`, not here). */}
              <View style={styles.poolSearchWrap}>
                <TextInput
                  testID="mock-draft.pool-search"
                  style={styles.poolSearch}
                  placeholder="Search the board…"
                  placeholderTextColor={chalk.faint}
                  value={poolQuery}
                  onChangeText={onPoolQuery}
                  autoCorrect={false}
                  autoCapitalize="none"
                />
                {poolQuery.length > 0 ? (
                  <Pressable
                    testID="mock-draft.pool-search.clear"
                    onPress={() => setPoolQuery('')}
                    hitSlop={8}
                    accessibilityRole="button"
                    accessibilityLabel="Clear search"
                    style={styles.poolSearchClear}
                  >
                    <Text style={styles.poolSearchClearText}>×</Text>
                  </Pressable>
                ) : null}
              </View>
              {state.undrafted.length === 0 ? (
                <Text testID="mock-draft.undrafted-empty" style={styles.emptyBody}>
                  Every rookie is off the board.
                </Text>
              ) : visiblePool.length === 0 ? (
                // Honest zero-match line; the All chip above stays present
                // to clear the narrow view (R-11).
                <Text testID="mock-draft.pool-empty" style={styles.emptyBody}>
                  {poolQuery.trim()
                    ? posFilter === 'ALL'
                      ? `No players match “${poolQuery.trim()}”.`
                      : `No ${posFilter}s match “${poolQuery.trim()}” — try All.`
                    : `No ${posFilter}s left on the board.`}
                </Text>
              ) : (
                visiblePool.map((r) => (
                  <UndraftedRowView
                    key={r.player_id}
                    row={r}
                    testID={`mock-draft.undrafted-row.${r.player_id}`}
                    onMenu={rowActionsOn ? onRowMenu : undefined}
                    onPress={isUserTurn ? setSelected : undefined}
                    selected={selected?.player_id === r.player_id}
                    // #291 — the label's PRESENCE is now the turn. The row
                    // renders it before any tap, so gating it here is what
                    // keeps the CPU-turn render byte-identical to the
                    // read-only room row.
                    actionLabel={isUserTurn ? 'Pick' : undefined}
                  />
                ))
              )}
            </View>
          </>
        )}
      </ScrollView>

      {/* Confirm bar — a bar, not a menu: one commitment with one
          alternative. It exists because the CPU tail resolves instantly and
          there is no undo in v1 (plan O-M3; restart is the escape hatch). */}
      {selected && isUserTurn ? (
        <View testID="mock-draft.confirm" style={styles.confirmBar}>
          <View>
            <Text style={styles.confirmTitle} numberOfLines={1}>
              Draft {selected.name || selected.player_id}
            </Text>
            <Text style={styles.confirmMeta} numberOfLines={1}>
              <Text style={{ color: positionOf(selected.position) }}>
                {selected.position || '—'}
              </Text>
              {selected.team ? ` · ${selected.team}` : ''}
              {` · consensus #${selected.rank}`}
              {/* #305 — "your pick" only when the slot is the user's OWN
                  team's; picking for another team names that team. */}
              {onClock
                ? forOwnTeam
                  ? ` · your pick ${onClock.round}.${String(onClock.slot).padStart(2, '0')}`
                  : clockName
                    ? ` · ${clockName}’s pick ${onClock.round}.${String(onClock.slot).padStart(2, '0')}`
                    : ` · pick ${onClock.round}.${String(onClock.slot).padStart(2, '0')}`
                : ''}
            </Text>
          </View>
          <View style={styles.confirmBtns}>
            <View style={styles.confirmCell}>
              <Button
                testID="mock-draft.confirm.cancel"
                label="Cancel"
                variant="ghost"
                disabled={pickMutation.isPending}
                onPress={() => setSelected(null)}
              />
            </View>
            <View style={styles.confirmCell}>
              <Button
                testID="mock-draft.confirm.draft"
                label="Draft him"
                variant="primary"
                loading={pickMutation.isPending}
                onPress={() => pickMutation.mutate(selected)}
              />
            </View>
          </View>
        </View>
      ) : null}

      {/* #326 — "Your team" as a modal sibling (never navigation): the
          screen and its clock state stay mounted underneath. */}
      <MockTeamSheet
        visible={teamSheetOpen}
        leagueId={leagueId}
        myPicks={state?.my_picks ?? []}
        onClose={() => setTeamSheetOpen(false)}
      />
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
        onSaved={() => {
          // The anchor moved the user's board everywhere. It does NOT move
          // the mock's CPU decisions — those were made against consensus at
          // pick time and are already recorded — so only the my_board view
          // of this list can change.
          queryClient.invalidateQueries({ queryKey: ['mock-draft', leagueId] });
          for (const key of ['rankings', 'progress', 'trio', 'tiers-status', 'trends']) {
            queryClient.invalidateQueries({ queryKey: [key] });
          }
        }}
      />
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      {/* #188 — root-stack push, no tab bar underneath. */}
      <FeedbackFAB activeScreen="MockDraft" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// ── on the clock ─────────────────────────────────────────────────────────

function OnTheClockCard({
  onClock,
  isUser,
  forOwnTeam,
  who,
  persona,
  total,
  made,
  ownershipSource,
  onViewTeam,
}: {
  onClock: MockDraftState['on_the_clock'];
  isUser: boolean;
  /** #305 — false only in manual mode, on another team's slot. */
  forOwnTeam: boolean;
  who: string | null;
  persona: string | null;
  total: number;
  made: number;
  /** #328 — threaded off `settings_echo.ownership_source`. */
  ownershipSource: MockOwnershipSource | null;
  /** #326 — opens the "Your team" sheet; the link renders on every active
   *  turn (the card only exists while a slot is on the clock). */
  onViewTeam: () => void;
}) {
  if (!onClock) return null;
  return (
    <View testID="mock-draft.on-the-clock" style={styles.clockCard}>
      <View style={styles.clockLine}>
        <Text style={styles.clockPick}>
          {onClock.round}.{String(onClock.slot).padStart(2, '0')}
        </Text>
        {/* Flare stays reserved for the user's OWN turn; an on-behalf turn
            reads in chalk like a CPU turn's headline (approved frame). */}
        <Text
          style={[styles.clockWho, (!isUser || !forOwnTeam) && { color: chalk.base }]}
          numberOfLines={1}
        >
          {isUser
            ? forOwnTeam
              ? 'You’re on the clock'
              : who
                ? `You’re picking for ${who}`
                : 'You’re picking for this team'
            : `${who ?? 'A computer drafter'} is on the clock`}
        </Text>
      </View>
      <Text style={styles.clockMeta}>
        round {onClock.round} · pick {onClock.pick_no} of {total} · {made} picks made
        {persona && !isUser ? ` · ${persona}` : ''}
      </Text>
      {/* #328 — the ownership-provenance disclosure, DURING the draft (the
          moment "why is Jake picking twice?" arises). Plain informational
          text; flare stays reserved for the user's own turn. */}
      {ownershipCaption(ownershipSource) ? (
        <Text testID="mock-draft.ownership-caption" style={styles.clockHow}>
          {ownershipCaption(ownershipSource)}
        </Text>
      ) : null}
      {/* #305 — the reminder, at the moment of confusion ("why am I picking
          for Jake?"), that drafting every team was the user's own choice. */}
      {isUser && !forOwnTeam ? (
        <Text testID="mock-draft.clock.picking-for" style={styles.clockHow}>
          You chose to pick for every team in this mock.
        </Text>
      ) : null}
      {/* #291 — "You're on the clock" said WHOSE turn it was and never HOW to
          act. One instruction line, inside the existing card, no new testID. */}
      {isUser ? (
        <Text style={styles.clockHow}>Tap a rookie below, then confirm.</Text>
      ) : null}
      {/* #326 — the team-sheet entry, on EVERY active turn (ice = action,
          per ADR-005; the sheet is a modal, the room never unmounts). */}
      <Pressable
        testID="mock-draft.view-team"
        onPress={onViewTeam}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="View your team"
      >
        <Text style={styles.viewTeamLink}>Your team</Text>
      </Pressable>
    </View>
  );
}

// ── the ticker ───────────────────────────────────────────────────────────

function PickTicker({
  picks,
  newest,
  userOwnerId,
  nameOf,
}: {
  picks: MockPick[];
  newest: number;
  userOwnerId: string | null;
  /** #305 — owner id → display name (the shared D-16 map). Without it the
   *  manual-mode who-column would render "—" for every non-own pick: all
   *  manual picks are `by: "user"`, so the shipped `by`-keyed fallback
   *  never says whose team a pick landed on. */
  nameOf?: Map<string, string>;
}) {
  // #322/#325 — ONE fixed-height ascending window: earliest visible pick at
  // the top (1.01 from pick one), newest at the bottom; grows to
  // TICKER_DEPTH rows and then the earliest falls off the top. Ordering and
  // the highlight boundary both come out of the pure helper — the screen
  // holds no reverse, no slice, no inline off-by-one.
  const { rows, firstNewIndex } = useMemo(
    () => tickerWindow(picks, TICKER_DEPTH, newest),
    [picks, newest],
  );
  if (!rows.length) return null;
  return (
    <View style={styles.section}>
      <TickLabel>{newest > 0 ? 'Since your last pick' : 'Just picked'}</TickLabel>
      {rows.map((p, i) => {
        const mine = userOwnerId != null && String(p.picked_by_user_id) === userOwnerId;
        return (
          <View
            key={p.pick_no}
            testID={`mock-draft.ticker-row.${p.pick_no}`}
            style={[
              styles.tickerRow,
              mine && styles.tickerRowMine,
              !mine && i >= firstNewIndex && styles.tickerRowNew,
            ]}
          >
            <Text style={styles.tickerPick}>
              {p.round}.{String(p.slot).padStart(2, '0')}
            </Text>
            <Text style={styles.tickerName} numberOfLines={1}>
              <Text style={{ color: positionOf(p.position) }}>{p.position || '—'}</Text>{' '}
              {p.name || p.player_id}
              {p.team ? ` · ${p.team}` : ''}
            </Text>
            <Text style={styles.tickerWho} numberOfLines={1}>
              {/* "You" keys on the user's TEAM (`picked_by_user_id`), never
                  on `by`; a manual-mode pick for another team names that
                  team. "—" survives only for an owner nobody can name. */}
              {mine
                ? 'You'
                : p.by === 'cpu'
                  ? 'CPU'
                  : (p.picked_by_user_id != null
                      ? nameOf?.get(String(p.picked_by_user_id))
                      : undefined) ?? '—'}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// ── recap ────────────────────────────────────────────────────────────────

function Recap({
  state,
  userOwnerId,
}: {
  state: MockDraftState;
  userOwnerId: string | null;
}) {
  const mine = useMemo(
    () =>
      state.picks.filter(
        (p) => userOwnerId != null && String(p.picked_by_user_id) === userOwnerId,
      ),
    [state.picks, userOwnerId],
  );
  const byRound = useMemo(() => {
    const m = new Map<number, MockPick[]>();
    for (const p of state.picks) {
      const list = m.get(p.round) ?? [];
      list.push(p);
      m.set(p.round, list);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [state.picks]);
  const nameOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of state.order) {
      // Same ladder as the on-the-clock card (D-16). The recap's rail is the
      // second site: fixing only the clock would leave a finished MFL mock
      // still printing raw franchise ids down every round.
      if (o.owner_user_id) m.set(o.owner_user_id, ownerNameOf(o.owner_username, o.owner_user_id));
    }
    return m;
  }, [state.order]);

  return (
    <>
      <View testID="mock-draft.recap" style={styles.clockCard}>
        <View style={styles.clockLine}>
          <Text style={styles.clockPick}>{mine.length}</Text>
          <Text style={[styles.clockWho, { color: chalk.base }]} numberOfLines={1}>
            picks
            {mine.length ? ` · ${mine.map((p) => p.position || '—').join(', ')}` : ''}
          </Text>
        </View>
        <Text style={styles.clockMeta}>
          {state.picks.length} picks · {state.settings_echo?.rounds ?? '—'} rounds ·{' '}
          {state.settings_echo?.teams ?? '—'} teams
        </Text>
        {/* #328 — same disclosure on the recap; the two mounts never
            co-render (status active vs complete). */}
        {ownershipCaption(state.settings_echo?.ownership_source ?? null) ? (
          <Text testID="mock-draft.recap.ownership-caption" style={styles.clockHow}>
            {ownershipCaption(state.settings_echo?.ownership_source ?? null)}
          </Text>
        ) : null}
      </View>

      {/* NOTE (contract gap G3): the design's "+3 / −1 vs consensus" column
          is NOT rendered, because it cannot be computed. `picks[]` carries
          no rank/value, and the drafted players are gone from `undrafted[]`
          before the first render, so any delta shown here would be
          invented. Honest omission beats a fabricated number — this comes
          back when `state_payload()` adds `consensus_rank` to picks[]. */}
      {mine.length ? (
        <View style={styles.section}>
          <TickLabel>Your draft</TickLabel>
          {mine.map((p) => (
            <View
              key={p.pick_no}
              testID={`mock-draft.recap-row.${p.pick_no}`}
              style={[draftRow.orderRow, styles.recapMine]}
            >
              <Text style={draftRow.slotCell}>
                {p.round}.{String(p.slot).padStart(2, '0')}
              </Text>
              <View style={draftRow.orderMain}>
                <Text style={draftRow.ownerText} numberOfLines={1}>
                  <Text style={{ color: positionOf(p.position) }}>{p.position || '—'}</Text>{' '}
                  {p.name || p.player_id}
                  {p.team ? ` · ${p.team}` : ''}
                </Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}

      {byRound.map(([round, picks]) => (
        <View key={round} style={styles.section}>
          <TickLabel>{`Round ${round}`}</TickLabel>
          {picks.map((p) => (
            <View key={p.pick_no} style={draftRow.orderRow}>
              <Text style={draftRow.slotCell}>
                {p.round}.{String(p.slot).padStart(2, '0')}
              </Text>
              <View style={draftRow.orderMain}>
                <Text style={draftRow.ownerText} numberOfLines={1}>
                  {(p.picked_by_user_id && nameOf.get(p.picked_by_user_id)) ?? 'Unassigned'}
                </Text>
                <Text style={draftRow.pickedText} numberOfLines={1}>
                  <Text style={{ color: positionOf(p.position) }}>{p.position || '—'}</Text>{' '}
                  {p.name || p.player_id}
                  {p.team ? ` · ${p.team}` : ''}
                </Text>
              </View>
            </View>
          ))}
        </View>
      ))}
    </>
  );
}

// ── helpers ──────────────────────────────────────────────────────────────

/** The session user's owner id — the join key for every "my team" render.
 *
 *  #305: `settings_echo.user_owner_id` is read FIRST and is the only source
 *  that is sound in manual mode, where `is_user` is true on EVERY owned
 *  slot (the roster_id on the clock is whichever team is up) and
 *  `my_picks` is empty until the user's own team has picked. The shipped
 *  inference survives below as the old-server fallback only — sound there
 *  because cpu is the only mode an old server can produce. */
function resolveUserOwnerId(state: MockDraftState | null): string | null {
  if (!state) return null;
  const echoed = state.settings_echo?.user_owner_id;
  if (echoed != null && echoed !== '') return String(echoed);
  if (state.on_the_clock?.is_user && state.on_the_clock.roster_id) {
    return String(state.on_the_clock.roster_id);
  }
  const own = state.my_picks?.[0]?.picked_by_user_id;
  return own != null ? String(own) : null;
}

/** `mfl:<league>.f<franchise>` — the synthetic member id the backend mints
 *  for every MFL franchise that is not the linked user
 *  (`server.py:_MOCK_MFL_MEMBER_RE`). Kept in step with that regex, not
 *  broadened: a name is only invented for an id whose shape says what it is. */
const MFL_MEMBER_RE = /^mfl:.*\.f(\w+)$/;

/** An owner's display name, never a machine id (D-16).
 *
 *  The backend now resolves this through `league_members`
 *  (`username → display_name → session username → "Team <fid>"`,
 *  `server.py:_mock_owner_name`) and OMITS the key rather than emitting an
 *  empty string, so `owner_username` is a real name on almost every row and
 *  this fallback rarely fires. It still exists because the last resort it
 *  replaces was `String(roster_id)`, which on an MFL league renders
 *  `mfl:62846.f0003` — a raw synthetic id printed at the top of the board.
 *
 *  The `Team <fid>` string is the SAME convention the backend's last rung and
 *  G1's Draft Room hydration use (`draft_board_service._hydrate_mfl_picks`
 *  tier 3, `f"Player {mfl_pid}"`, is that convention for the *player* half).
 *  Two adjacent surfaces naming one franchise two ways is the whole defect —
 *  so this is the shipped convention re-used, not a second one invented.
 *
 *  Non-MFL ids fall through to the shipped behaviour: a Sleeper roster id is
 *  a number the user has at least seen before, and inventing a name for it
 *  would be a change to the Sleeper path that D-16 does not authorise. */
function ownerNameOf(username: string | null | undefined, ownerId: unknown): string {
  const name = String(username ?? '').trim();
  if (name && !name.includes('mfl:')) return name;
  const id = String(ownerId ?? '');
  const match = MFL_MEMBER_RE.exec(id);
  // The fid exactly as it appears in the id, zero-padding intact — the
  // backend pads the same way, so the two cannot render "Team 3" vs "Team 0003".
  if (match) return `Team ${match[1]}`;
  return id;
}

function emptyCopy(reason: string | null): string {
  switch (reason) {
    case 'no_active_mock':
      return 'This mock is over. Start another one from the draft room.';
    case 'class_not_loaded':
      return 'There’s no rookie class loaded yet, so there’s nobody to draft.';
    case 'cpu_model_unvalidated':
      return 'The computer drafters aren’t ready yet.';
    case 'user_not_in_draft':
      return 'We couldn’t find your team in this league’s draft, so there’s no seat for you to draft from.';
    default:
      return 'This mock draft isn’t available right now.';
  }
}

function pickLabelOf(slot: { round: number; slot: number }): string {
  return `${slot.round}.${String(slot.slot).padStart(2, '0')}`;
}

function lastName(full: string): string {
  const parts = full.trim().split(/\s+/);
  return parts.length > 1 ? parts.slice(1).join(' ') : full;
}

function rowAsPlayer(row: UndraftedRow): Player {
  return {
    id: row.player_id,
    name: row.name || row.player_id,
    position: row.position,
    team: row.team,
  };
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xxxl,
    paddingTop: space.md,
    gap: space.md,
  },
  headerAction: { ...type.label, color: ice.base },

  section: { gap: space.sm },

  clockCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    gap: 3,
  },
  clockLine: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  clockPick: { ...type.data, fontSize: 19, color: chalk.base },
  clockWho: { ...type.bodySm, color: flare.base, flex: 1 },
  clockMeta: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  // #291 — the instruction, not a decoration: full body size (13, well clear
  // of the 11px floor) and chalk.dim, so it reads as guidance rather than
  // sinking into the meta line above it. Ice is reserved for the action
  // itself (the row's "Pick" label and the confirm bar).
  clockHow: { ...type.bodySm, color: chalk.dim },

  tickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.xs,
  },
  tickerRowMine: { backgroundColor: 'rgba(240,80,140,0.07)' },
  tickerRowNew: { backgroundColor: 'rgba(86,217,236,0.06)' },
  tickerPick: { ...type.data, fontSize: 12, color: chalk.faint, width: 40 },
  tickerName: { ...type.bodySm, color: chalk.base, flex: 1 },
  tickerWho: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  myPicksRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  // #324 — fixed 3-per-row equal-width grid (flexBasis-based): rows of
  // three grow equally to fill the line; a short last row is capped so its
  // chips stay the same width as their siblings. minHeight 44 is vertical
  // rhythm / two-line headroom only — the chips are non-interactive, so
  // this is NOT a touch-target rule (PRD R-8). Flare border: the chips are
  // the user's OWN picks — flare is the informational accent (ADR-005).
  myPickChip: {
    flexBasis: '30%',
    flexGrow: 1,
    maxWidth: '32.5%',
    minHeight: 44,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    gap: 2,
  },
  myPickLabel: { ...type.data, color: chalk.base },
  // Meta line at bodySm (13) — position color is the data encoding;
  // TierBadge's internal label is 11, the design-system floor.
  myPickMeta: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  myPickPos: { ...type.bodySm },
  myPickFrom: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  // #326 — PositionTabs construction (FreeAgentsScreen precedent).
  posFilterRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  posFilterSegment: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  posFilterSegmentActive: { backgroundColor: ink.ink3 },
  posFilterText: { ...type.label },
  posFilterTextActive: { color: chalk.base },

  // #327 — the PlayerPickerModal search construction, ink1 fill (the
  // screen's sections sit on ink0).
  poolSearchWrap: { justifyContent: 'center' },
  poolSearch: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink1,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: space.md,
    paddingRight: space.xxl,
    color: chalk.base,
  },
  poolSearchClear: {
    position: 'absolute',
    right: 0,
    height: 44,
    width: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  poolSearchClearText: { ...type.body, fontSize: 18, color: chalk.dim },

  // #326 — team-sheet entry link (ice = action, ADR-005).
  viewTeamLink: { ...type.label, color: ice.base, paddingTop: 2 },

  cpuBasisNote: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  recapMine: { backgroundColor: 'rgba(240,80,140,0.06)' },

  confirmBar: {
    backgroundColor: ink.ink1,
    borderTopWidth: 1,
    borderTopColor: ice.base,
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.lg,
    gap: space.sm,
  },
  confirmTitle: { ...type.title, fontSize: 15, color: chalk.base },
  confirmMeta: { ...type.bodySm, fontSize: 11, color: chalk.dim },
  confirmBtns: { flexDirection: 'row', gap: space.sm },
  confirmCell: { flex: 1 },

  centerFill: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xl,
    gap: space.sm,
  },
  emptyBody: { ...type.bodySm, textAlign: 'center' },
  errorText: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
});
