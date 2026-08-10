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
// ── No analytics yet, deliberately ──────────────────────────────────────
// `backend/analytics_taxonomy.py` is DEFAULT-DENY and carries no mock
// events; this wave owns mobile/ only, so any track() call here would be
// dropped server-side while reading like working instrumentation. Register
// the events first, then wire the calls.

import React, { useCallback, useLayoutEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
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
import { MockRail } from '../components/draft/MockChrome';
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
  type MockPick,
} from '../api/mockDraft';
import { setAssetPref } from '../api/league';
import { readErrorCopy } from '../utils/verification';
import { haptics } from '../utils/haptics';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Player } from '../shared/types';

/** How many recent picks the ticker shows. Enough to see the run that
 *  happened while you were away, short enough not to become the page. */
const TICKER_DEPTH = 8;

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

  const pickMutation = useMutation({
    mutationFn: (row: UndraftedRow) =>
      pickInMockDraft(state?.mock_id as number, row.player_id),
    onSuccess: (next) => {
      haptics.selection();
      setSelected(null);
      applyResponse(next);
    },
    onError: (err) => {
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
  }, [state?.mock_id, state?.status, navigation, queryClient, leagueId]);

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

  const clockName = useMemo(() => {
    if (!state || !onClock?.roster_id) return null;
    const slot = state.order.find((o) => o.owner_user_id === onClock.roster_id);
    return ownerNameOf(slot?.owner_username, onClock.roster_id);
  }, [state, onClock?.roster_id]);

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
              who={clockName}
              persona={personaLine}
              total={state.order.length}
              made={state.picks.length}
            />

            <PickTicker picks={state.picks} newest={sinceUserPick} userOwnerId={userOwnerId} />

            {myPickSlots.length ? (
              <View style={styles.section}>
                <TickLabel>Your picks</TickLabel>
                <View style={styles.myPicksRow}>
                  {myPickSlots.map(({ slot, pick, isTraded }) => (
                    <View key={slot.pick_no} style={styles.myPickChip}>
                      <Text style={styles.myPickLabel}>{pickLabelOf(slot)}</Text>
                      <Text style={styles.myPickFrom} numberOfLines={1}>
                        {pick
                          ? lastName(pick.name || pick.player_id)
                          : slot.pick_no === onClock?.pick_no
                            ? 'on the clock'
                            : isTraded
                              ? `from ${slot.original_username ?? 'another team'}`
                              : ''}
                      </Text>
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
              {state.undrafted.length === 0 ? (
                <Text testID="mock-draft.undrafted-empty" style={styles.emptyBody}>
                  Every rookie is off the board.
                </Text>
              ) : (
                state.undrafted.map((r) => (
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
              {onClock ? ` · your pick ${onClock.round}.${String(onClock.slot).padStart(2, '0')}` : ''}
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
  who,
  persona,
  total,
  made,
}: {
  onClock: MockDraftState['on_the_clock'];
  isUser: boolean;
  who: string | null;
  persona: string | null;
  total: number;
  made: number;
}) {
  if (!onClock) return null;
  return (
    <View testID="mock-draft.on-the-clock" style={styles.clockCard}>
      <View style={styles.clockLine}>
        <Text style={styles.clockPick}>
          {onClock.round}.{String(onClock.slot).padStart(2, '0')}
        </Text>
        <Text style={[styles.clockWho, !isUser && { color: chalk.base }]} numberOfLines={1}>
          {isUser ? 'You’re on the clock' : `${who ?? 'A computer drafter'} is on the clock`}
        </Text>
      </View>
      <Text style={styles.clockMeta}>
        round {onClock.round} · pick {onClock.pick_no} of {total} · {made} picks made
        {persona && !isUser ? ` · ${persona}` : ''}
      </Text>
      {/* #291 — "You're on the clock" said WHOSE turn it was and never HOW to
          act. One instruction line, inside the existing card, no new testID. */}
      {isUser ? (
        <Text style={styles.clockHow}>Tap a rookie below, then confirm.</Text>
      ) : null}
    </View>
  );
}

// ── the ticker ───────────────────────────────────────────────────────────

function PickTicker({
  picks,
  newest,
  userOwnerId,
}: {
  picks: MockPick[];
  newest: number;
  userOwnerId: string | null;
}) {
  const recent = useMemo(() => [...picks].reverse().slice(0, TICKER_DEPTH), [picks]);
  if (!recent.length) return null;
  return (
    <View style={styles.section}>
      <TickLabel>{newest > 0 ? 'Since your last pick' : 'Just picked'}</TickLabel>
      {recent.map((p, i) => {
        const mine = userOwnerId != null && String(p.picked_by_user_id) === userOwnerId;
        return (
          <View
            key={p.pick_no}
            testID={`mock-draft.ticker-row.${p.pick_no}`}
            style={[
              styles.tickerRow,
              mine && styles.tickerRowMine,
              !mine && i < newest && styles.tickerRowNew,
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
              {mine ? 'You' : p.by === 'cpu' ? 'CPU' : '—'}
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

/** The session user's owner id, read off the payload rather than the
 *  session: `settings_echo` does not echo `user_owner_id`, but the engine
 *  advances the CPU until the user is on the clock, so an ACTIVE mock
 *  always identifies them — and a complete one has their picks. */
function resolveUserOwnerId(state: MockDraftState | null): string | null {
  if (!state) return null;
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
  myPickChip: {
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  myPickLabel: { ...type.data, color: chalk.base },
  myPickFrom: { ...type.bodySm, fontSize: 11, color: chalk.faint },

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
