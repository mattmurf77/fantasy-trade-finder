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

import React, { useCallback, useMemo, useState } from 'react';
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
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  chalk,
  flare,
  ice,
  ink,
  position as positionColor,
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
import Toast from '../components/Toast';
import {
  DraftSchemaError,
  getDraftBoard,
  type DraftBasis,
  type DraftBoard,
  type DraftOrderSlot,
  type DraftPick,
  type UndraftedRow,
} from '../api/draft';
import { setAssetPref } from '../api/league';
import { track } from '../api/events';
import { readErrorCopy } from '../utils/verification';
import { haptics } from '../utils/haptics';
import { useAppActive } from '../hooks/useAppActive';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Player } from '../shared/types';

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

  // ── W1 row actions ────────────────────────────────────────────────────
  // menuTarget is only ever set while `draft.rank_inline` is on, so both
  // sheets are unreachable with the flag off.
  const [menuTarget, setMenuTarget] = useState<UndraftedRow | null>(null);
  const [anchorTarget, setAnchorTarget] = useState<AnchorTarget | null>(null);
  const [toast, setToast] = useState<
    { msg: string; tone?: 'success' | 'warn' } | null
  >(null);

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
      refreshing={query.isFetching && !query.isLoading}
      onRefresh={onRefresh}
      inTabs={inTabs}
    >
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
        />
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
    </Shell>
  );
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
}: {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  /** True when rendered inside the seasonal Draft TAB (option A′), where
   *  RootNav's global FAB already covers the screen — mounting our own
   *  would double it (#196/#197). The root-stack push passes nothing. */
  inTabs?: boolean;
}) {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
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
}: {
  board: DraftBoard;
  showLastYear: boolean;
  onToggleLastYear: () => void;
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
              : (board.notice?.message ?? '');
  if (!copy) return null;
  return (
    <View testID={`draft-room.notice.${code}`} style={styles.notice}>
      <Text style={styles.noticeText}>{copy}</Text>
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
          <PickRow key={`${p.round}-${p.pick_no}`} pick={p} label={pickLabel(p)} />
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
            style={styles.orderRow}
          >
            <Text style={styles.slotCell}>{slotLabel(slot)}</Text>
            <View style={styles.orderMain}>
              <Text style={styles.ownerText} numberOfLines={1}>
                {slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'}
                {slot.is_traded ? (
                  <Text style={styles.tradedTag}>
                    {'  '}from {slot.original_username ?? '—'}
                  </Text>
                ) : null}
              </Text>
              {pick ? (
                <Text style={styles.pickedText} numberOfLines={1}>
                  <Text style={{ color: positionOf(pick.position) }}>
                    {pick.position || '—'}
                  </Text>{' '}
                  {pick.name || pick.player_id}
                  {pick.team ? ` · ${pick.team}` : ''}
                </Text>
              ) : (
                <Text style={styles.onTheClock}>Not made yet</Text>
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
    <View testID={`draft-room.pick-row.${pick.pick_no}`} style={styles.orderRow}>
      <Text style={styles.slotCell}>{label}</Text>
      <View style={styles.orderMain}>
        <Text style={styles.pickedText} numberOfLines={1}>
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
      <View style={styles.basisRow}>
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
      {/* FreeAgents-style fallback notice — say which numbers these are. */}
      {basis === 'my_board' ? (
        <Text style={styles.fallbackNote}>
          Ordered by your board. Anyone you haven’t ranked falls back to the
          consensus value.
        </Text>
      ) : null}
      {anyUnvalued ? (
        <Text style={styles.fallbackNote}>
          Some rookies have no consensus value yet. They’re listed last rather
          than hidden — a prospect with no price is still on the board.
        </Text>
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

function UndraftedRowView({
  row,
  onMenu,
}: {
  row: UndraftedRow;
  onMenu?: (row: UndraftedRow) => void;
}) {
  // Per-player testID (D0). The shipped id was shared across every row,
  // which is why this flow was untestable; the qualifier is the stable
  // domain id per mobile/src/components/CLAUDE.md — never a list index.
  const testID = `draft-room.undrafted-row.${row.player_id}`;
  const body = (
    <>
      <Text style={styles.rankCell}>{row.rank}</Text>
      <View style={styles.orderMain}>
        <Text style={styles.playerName} numberOfLines={1}>
          {row.name || row.player_id}
        </Text>
        <Text style={styles.playerMeta} numberOfLines={1}>
          <Text style={{ color: positionOf(row.position) }}>
            {row.position || '—'}
          </Text>
          {row.team ? ` · ${row.team}` : ''}
        </Text>
      </View>
      <Text style={row.valued ? styles.valueCell : styles.noValueCell}>
        {row.valued ? Math.round(row.value as number) : 'No value'}
      </Text>
    </>
  );

  // Flag off ⇒ the exact inert View this row shipped as.
  if (!onMenu) {
    return (
      <View testID={testID} style={styles.undraftedRow}>
        {body}
      </View>
    );
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
      accessibilityHint="Hold for player options"
      accessibilityActions={[{ name: 'menu', label: 'Player options' }]}
      onAccessibilityAction={(e) => {
        if (e.nativeEvent.actionName === 'menu') onMenu(row);
      }}
      onLongPress={() => onMenu(row)}
      style={({ pressed }) => [
        styles.undraftedRow,
        pressed && { backgroundColor: ink.ink1 },
      ]}
    >
      {body}
    </Pressable>
  );
}

function BasisChip({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [
        styles.basisChip,
        active && styles.basisChipActive,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <Text style={[type.label, active ? styles.basisChipTextActive : null]}>
        {label}
      </Text>
    </Pressable>
  );
}

// ── helpers ──────────────────────────────────────────────────────────────

function slotLabel(slot: DraftOrderSlot): string {
  if (slot.slot == null) return `R${slot.round}`;
  return `${slot.round}.${String(slot.slot).padStart(2, '0')}`;
}

function pickLabel(pick: DraftPick): string {
  if (pick.slot == null) return `R${pick.round}`;
  return `${pick.round}.${String(pick.slot).padStart(2, '0')}`;
}

function positionOf(pos: string): string {
  switch ((pos || '').toUpperCase()) {
    case 'QB': return positionColor.qb;
    case 'RB': return positionColor.rb;
    case 'WR': return positionColor.wr;
    case 'TE': return positionColor.te;
    default:   return chalk.dim;
  }
}

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

  orderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.sm,
  },
  slotCell: { ...type.data, color: chalk.dim, width: 48 },
  orderMain: { flex: 1, gap: 2 },
  ownerText: { ...type.bodySm, color: chalk.base },
  tradedTag: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  pickedText: { ...type.bodySm, color: chalk.dim },
  onTheClock: { ...type.bodySm, color: chalk.faint },

  basisRow: { flexDirection: 'row', gap: space.sm },
  basisChip: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  basisChipActive: { backgroundColor: ink.ink3, borderColor: ice.base },
  basisChipTextActive: { color: chalk.base },
  fallbackNote: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },

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

  undraftedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.sm,
  },
  rankCell: { ...type.data, color: chalk.faint, width: 28 },
  playerName: { ...type.bodySm, color: chalk.base },
  playerMeta: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  valueCell: { ...type.data, color: chalk.base },
  noValueCell: { ...type.bodySm, fontSize: 11, color: chalk.faint },

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
