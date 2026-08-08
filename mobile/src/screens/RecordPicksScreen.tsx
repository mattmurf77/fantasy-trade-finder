// Record picks — live offline pick recording (draft-extensions W3 M-D, flag
// `draft.manual_picks`, ships OFF).
//
// ── Why this screen exists ──────────────────────────────────────────────
// ESPN hosts no rookie drafts, so once a league's picks are assigned
// (M-A), the ONLY way FTF ever learns who was actually taken is a member
// typing it in during the real off-platform draft. This screen is that
// input surface — nothing else writes `recorded_picks`.
//
// ── The interaction (the three details that decide whether this works in
//    a real draft room, per the task brief) ─────────────────────────────
//   1. ONE TAP PER PICK. Tap the player from the undrafted list; the team
//      comes from the M-A assignment grid's owner for the cursor's slot
//      (recording is "confirm, not select"), and the cursor auto-advances
//      to the next unrecorded slot.
//   2. THE CURSOR IS MOVABLE. Tap any row in the order list to re-anchor
//      recording there — the highest-risk detail in the wave, per the
//      brief: without it, one missed pick collapses auto-advance and the
//      whole session gets abandoned.
//   3. OFF-BY-ONE RECOVERY IS MANUAL-CURSOR-ONLY, NO AUTO-SHIFT. A missed
//      pick is fixed by tapping the correct slot (#2) and recording there
//      directly — there is no "insert a skipped pick and shift everything
//      after" mode. `overall` is the offline queue's idempotency key
//      (plan §6.5); a shift operation would rewrite many rows' `overall`
//      values mid-replay, which the idempotency contract cannot tolerate.
//      This is the documented, binding choice between the two options the
//      brief named.
//
// ── Offline-first rendering ──────────────────────────────────────────────
// `recordPick()` (api/recordedPicks.ts) is fire-and-forget into an
// AsyncStorage-backed offline queue — copying `events.ts`'s battle-tested
// contract verbatim (see that module's header). This screen never awaits
// it: the UI updates from a LOCAL optimistic overlay the instant a tap
// lands, and reconciles against the server board once the queue flushes
// and a refetch confirms it. An airplane-mode session works exactly the
// same as an online one; the only difference is how long the optimistic
// overlay persists before the server catches up.
//
// ── Team is editable only when the grid was wrong ────────────────────────
// The on-the-clock team defaults from the assignment grid (`order[]`'s
// `owner_user_id` for the cursor's slot); "Change team" opens an inline
// picker built from the grid's own owner list, so it can never offer a
// team that isn't a real slot owner.
//
// Registered on the root stack UNCONDITIONALLY (the `PickAssignment`/
// `DraftRoom` precedent) — the flag gates the entry POINT, not the route,
// so a stale deep link renders the honest unavailable state below rather
// than a dead path.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { chalk, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import { Button, Icon, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import Toast from '../components/Toast';
import {
  getDraftBoard,
  type DraftBoard,
  type DraftOrderSlot,
  type UndraftedRow,
} from '../api/draft';
import { recordPick, voidRecordedPick } from '../api/recordedPicks';
import { readErrorCopy } from '../utils/verification';
import { haptics } from '../utils/haptics';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';

/** `1.03`, or `R1` when the platform has not published an order — mirrors
 *  `components/draft/DraftRows.slotLabel` (not imported: that module's
 *  `UndraftedRow`/order shapes are the room's own, and this screen's
 *  merged local+server rows are a distinct local type). */
function slotLabel(o: { slot: number | null; round: number }): string {
  if (o.slot == null) return `R${o.round}`;
  return `${o.round}.${String(o.slot).padStart(2, '0')}`;
}

interface MergedPick {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  /** True while this row is a local optimistic entry not yet confirmed by
   *  a server refetch — used only for the small "sending…" affordance. */
  pending: boolean;
}

export default function RecordPicksScreen({ route, navigation }: any = {}) {
  const paramLeagueId: string | undefined = route?.params?.leagueId;
  const sessionLeagueId = useSession((s) => s.league?.league_id);
  const leagueId = paramLeagueId ?? sessionLeagueId ?? null;
  const manualPicksOn = useFlag('draft.manual_picks');

  const query = useQuery({
    queryKey: ['draft-board', leagueId, 'consensus'],
    queryFn: () => getDraftBoard(leagueId as string, 'consensus'),
    enabled: !!leagueId,
    staleTime: 5_000,
    // Picks up a leaguemate's recordings and confirms this device's own
    // queued writes once they flush — a live draft room, not a static page.
    refetchInterval: 15_000,
  });
  const board = query.data;

  // ── Local optimistic overlay ─────────────────────────────────────────
  // Keyed by `overall` (== order[].pick_no). A pending write shows here
  // immediately; it is dropped the moment the SAME pick_no appears in the
  // server's `board.picks` (the refetch effect below), and a pending void
  // is dropped once the server no longer carries that pick_no at all.
  const [localPicks, setLocalPicks] = useState<Map<number, MergedPick>>(new Map());
  const [localVoided, setLocalVoided] = useState<Set<number>>(new Set());
  const [cursor, setCursor] = useState<number | null>(null);
  const [teamOverride, setTeamOverride] = useState<Map<number, string>>(new Map());
  const [pickingTeam, setPickingTeam] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  const order = useMemo(
    () => (board?.order ?? []).slice().sort((a, b) => (a.pick_no ?? 0) - (b.pick_no ?? 0)),
    [board],
  );
  const serverPickByNo = useMemo(() => {
    const m = new Map<number, DraftBoard['picks'][number]>();
    for (const p of board?.picks ?? []) m.set(p.pick_no, p);
    return m;
  }, [board]);

  // Reconcile the local overlay against server truth on every refetch.
  useEffect(() => {
    if (!board) return;
    setLocalPicks((prev) => {
      if (prev.size === 0) return prev;
      let changed = false;
      const next = new Map(prev);
      for (const pickNo of prev.keys()) {
        if (serverPickByNo.has(pickNo)) { next.delete(pickNo); changed = true; }
      }
      return changed ? next : prev;
    });
    setLocalVoided((prev) => {
      if (prev.size === 0) return prev;
      let changed = false;
      const next = new Set(prev);
      for (const pickNo of prev) {
        if (!serverPickByNo.has(pickNo)) { next.delete(pickNo); changed = true; }
      }
      return changed ? next : prev;
    });
  }, [serverPickByNo, board]);

  const pickAt = useCallback(
    (pickNo: number): MergedPick | null => {
      if (localVoided.has(pickNo)) return null;
      const local = localPicks.get(pickNo);
      if (local) return local;
      const server = serverPickByNo.get(pickNo);
      if (!server) return null;
      return {
        player_id: server.player_id, name: server.name || server.player_id,
        position: server.position, team: server.team, pending: false,
      };
    },
    [localPicks, localVoided, serverPickByNo],
  );

  // Cursor default: the first order slot with nothing recorded.
  useEffect(() => {
    if (cursor != null || order.length === 0) return;
    const next = order.find((o) => o.pick_no != null && !pickAt(o.pick_no));
    if (next?.pick_no != null) setCursor(next.pick_no);
  }, [order, cursor, pickAt]);

  const cursorSlot: DraftOrderSlot | null = useMemo(
    () => order.find((o) => o.pick_no === cursor) ?? null,
    [order, cursor],
  );
  const cursorTeamId = cursor != null
    ? (teamOverride.get(cursor) ?? cursorSlot?.owner_user_id ?? null)
    : null;
  const cursorTeamName = useMemo(() => {
    if (!cursorTeamId) return 'Unassigned';
    const own = order.find((o) => o.owner_user_id === cursorTeamId);
    return own?.owner_username ?? cursorTeamId;
  }, [cursorTeamId, order]);

  // The grid's own owner list — the ONLY source for the team picker, so it
  // can never offer a team that isn't a real slot owner.
  const teams = useMemo(() => {
    const seen = new Map<string, string>();
    for (const o of order) {
      if (o.owner_user_id && !seen.has(o.owner_user_id)) {
        seen.set(o.owner_user_id, o.owner_username ?? o.owner_user_id);
      }
    }
    return Array.from(seen, ([user_id, name]) => ({ user_id, name }));
  }, [order]);

  const recordedCount = useMemo(
    () => order.filter((o) => o.pick_no != null && pickAt(o.pick_no)).length,
    [order, pickAt],
  );

  const undraftedRows = useMemo(() => {
    if (!board) return [] as UndraftedRow[];
    const takenLocally = new Set(
      Array.from(localPicks.values()).map((p) => p.player_id),
    );
    return board.undrafted.filter((r) => !takenLocally.has(r.player_id));
  }, [board, localPicks]);

  const advanceCursor = useCallback(
    (fromPickNo: number) => {
      const idx = order.findIndex((o) => o.pick_no === fromPickNo);
      for (let i = idx + 1; i < order.length; i++) {
        const o = order[i];
        if (o.pick_no != null && !pickAt(o.pick_no)) { setCursor(o.pick_no); return; }
      }
      setCursor(null);   // every slot recorded
    },
    [order, pickAt],
  );

  const onRecord = useCallback(
    (row: UndraftedRow) => {
      if (!leagueId || !board || !cursorSlot || cursorSlot.pick_no == null) return;
      const pickNo = cursorSlot.pick_no;
      haptics.selection();
      setLocalPicks((prev) => {
        const next = new Map(prev);
        next.set(pickNo, {
          player_id: row.player_id, name: row.name || row.player_id,
          position: row.position, team: row.team, pending: true,
        });
        return next;
      });
      setLocalVoided((prev) => {
        if (!prev.has(pickNo)) return prev;
        const next = new Set(prev); next.delete(pickNo); return next;
      });
      recordPick({
        leagueId, season: board.season, overall: pickNo,
        round: cursorSlot.round, slot: cursorSlot.slot ?? pickNo,
        pickingTeamId: cursorTeamId, playerId: row.player_id,
      });
      setToast({ msg: `${slotLabel(cursorSlot)} — ${row.name || row.player_id}`,
                tone: 'success' });
      advanceCursor(pickNo);
    },
    [leagueId, board, cursorSlot, cursorTeamId, advanceCursor],
  );

  const onUndo = useCallback(
    (pickNo: number) => {
      if (!leagueId || !board) return;
      haptics.warning();
      setLocalVoided((prev) => new Set(prev).add(pickNo));
      setLocalPicks((prev) => {
        if (!prev.has(pickNo)) return prev;
        const next = new Map(prev); next.delete(pickNo); return next;
      });
      voidRecordedPick({ leagueId, season: board.season, overall: pickNo }).catch(() => {
        // The pick is still live server-side — undo the optimistic void.
        setLocalVoided((prev) => {
          const next = new Set(prev); next.delete(pickNo); return next;
        });
        setToast({ msg: "Couldn't undo that pick", tone: 'warn' });
      });
      setCursor(pickNo);   // re-anchor to the freed slot
    },
    [leagueId, board],
  );

  const onSelectSlot = useCallback((o: DraftOrderSlot) => {
    if (o.pick_no == null) return;
    haptics.selection();
    setPickingTeam(false);
    setCursor(o.pick_no);
  }, []);

  // ── Honest states ────────────────────────────────────────────────────

  if (!leagueId) {
    return (
      <Shell>
        <View style={styles.centerFill}>
          <Text testID="record-picks.no-league" style={styles.emptyBody}>
            Connect a league to record its draft.
          </Text>
        </View>
      </Shell>
    );
  }

  if (!manualPicksOn) {
    return (
      <Shell>
        <View style={styles.centerFill}>
          <Text testID="record-picks.unavailable" style={styles.emptyBody}>
            Live pick recording isn't available yet.
          </Text>
        </View>
      </Shell>
    );
  }

  if (query.isLoading) {
    return (
      <Shell>
        <View style={styles.centerFill}>
          <ActivityIndicator color={ice.base} />
        </View>
      </Shell>
    );
  }

  if (query.isError || !board) {
    return (
      <Shell>
        <View style={styles.centerFill}>
          <Text testID="record-picks.error" style={styles.errorText}>
            {readErrorCopy(query.error, "Couldn't load the draft board.")}
          </Text>
          <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
        </View>
      </Shell>
    );
  }

  if (board.order_confidence !== 'assigned' || order.length === 0) {
    return (
      <Shell>
        <View style={styles.centerFill}>
          <Text testID="record-picks.not-assigned" style={styles.emptyBody}>
            Assign this league's draft picks before recording live — the
            recorder needs to know whose pick is on the clock.
          </Text>
        </View>
      </Shell>
    );
  }

  const done = cursor == null;

  return (
    <Shell
      refreshing={query.isFetching && !query.isLoading}
      onRefresh={() => query.refetch()}
    >
      <Text testID="record-picks.progress" style={styles.progressText}>
        {recordedCount} of {order.length} recorded
      </Text>

      {done ? (
        <View style={styles.doneCard}>
          <Text style={styles.doneTitle}>Every slot is recorded.</Text>
          <Text style={styles.doneBody}>
            Tap any pick below to correct it, or undo one to re-open its slot.
          </Text>
        </View>
      ) : (
        <View testID="record-picks.on-the-clock" style={styles.clockCard}>
          <Text style={styles.clockSlot}>{cursorSlot ? slotLabel(cursorSlot) : ''}</Text>
          <View style={styles.clockTeamRow}>
            <Text style={styles.clockTeam} numberOfLines={1}>{cursorTeamName}</Text>
            <Pressable
              testID="record-picks.change-team"
              onPress={() => setPickingTeam((v) => !v)}
              hitSlop={8}
            >
              <Text style={styles.changeTeamLink}>Change team</Text>
            </Pressable>
          </View>
          {pickingTeam ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
                       style={styles.teamPickerRow}>
              {teams.map((t) => (
                <Pressable
                  key={t.user_id}
                  testID={`record-picks.team.${t.user_id}`}
                  onPress={() => {
                    if (cursor == null) return;
                    setTeamOverride((prev) => new Map(prev).set(cursor, t.user_id));
                    setPickingTeam(false);
                  }}
                  style={({ pressed }) => [
                    styles.teamChip,
                    t.user_id === cursorTeamId && styles.teamChipActive,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Text style={type.label}>{t.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          ) : null}
        </View>
      )}

      <View style={styles.section}>
        <TickLabel>Order — tap to re-anchor</TickLabel>
        {order.map((o, i) => {
          if (o.pick_no == null) return null;
          const pick = pickAt(o.pick_no);
          const isCursor = o.pick_no === cursor;
          return (
            <Pressable
              key={`${o.round}-${o.slot ?? i}`}
              testID={`record-picks.order-row.${o.pick_no}`}
              onPress={() => onSelectSlot(o)}
              style={({ pressed }) => [
                rowStyles.row,
                isCursor && rowStyles.rowCursor,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={rowStyles.slotCell}>{slotLabel(o)}</Text>
              <View style={rowStyles.main}>
                <Text style={rowStyles.owner} numberOfLines={1}>
                  {o.owner_username ?? o.owner_user_id ?? 'Unassigned'}
                </Text>
                {pick ? (
                  <Text style={rowStyles.picked} numberOfLines={1}>
                    {pick.name}{pick.pending ? ' · sending…' : ''}
                  </Text>
                ) : (
                  <Text style={rowStyles.notMade}>
                    {isCursor ? 'On the clock' : 'Not made yet'}
                  </Text>
                )}
              </View>
              {pick ? (
                <Pressable
                  testID={`record-picks.undo.${o.pick_no}`}
                  onPress={() => onUndo(o.pick_no as number)}
                  hitSlop={8}
                >
                  <Text style={rowStyles.undo}>Undo</Text>
                </Pressable>
              ) : null}
            </Pressable>
          );
        })}
      </View>

      {!done ? (
        <View style={styles.section}>
          <TickLabel>Undrafted — tap to record</TickLabel>
          {undraftedRows.length === 0 ? (
            <Text style={styles.emptyBody}>No undrafted players on the board.</Text>
          ) : (
            undraftedRows.map((r) => (
              <Pressable
                key={r.player_id}
                testID={`record-picks.undrafted-row.${r.player_id}`}
                onPress={() => onRecord(r)}
                style={({ pressed }) => [
                  rowStyles.row,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <Text style={rowStyles.rankCell}>{r.rank}</Text>
                <View style={rowStyles.main}>
                  <Text style={rowStyles.owner} numberOfLines={1}>
                    {r.name || r.player_id}
                  </Text>
                  <Text style={rowStyles.notMade}>
                    {r.position}{r.team ? ` · ${r.team}` : ''}
                  </Text>
                </View>
                <Icon name="chevron-right" size={16} color={chalk.dim} />
              </Pressable>
            ))
          )}
        </View>
      ) : null}

      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
    </Shell>
  );
}

function Shell({
  children,
  refreshing,
  onRefresh,
}: {
  children?: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
}) {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        testID="record-picks.scroll"
        contentContainerStyle={styles.scrollContent}
        refreshControl={onRefresh ? (
          <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} />
        ) : undefined}
      >
        {children}
      </ScrollView>
      <FeedbackFAB activeScreen="RecordPicks" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scrollContent: { padding: space.md, paddingBottom: space.xl * 2, gap: space.md },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg, gap: space.sm },
  emptyBody: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },
  errorText: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
  progressText: { ...type.bodySm, color: chalk.dim },
  clockCard: {
    borderWidth: 1, borderColor: ice.base, borderRadius: radii.sm,
    backgroundColor: ink.ink1, padding: space.md, gap: space.xs,
  },
  clockSlot: { ...type.heading, color: chalk.base },
  clockTeamRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  clockTeam: { ...type.bodySm, color: chalk.base, flexShrink: 1 },
  changeTeamLink: { ...type.label, color: ice.base },
  teamPickerRow: { marginTop: space.xs },
  teamChip: {
    borderWidth: 1, borderColor: ink.lineStrong, borderRadius: radii.sm,
    paddingHorizontal: space.md, paddingVertical: space.sm, marginRight: space.sm,
  },
  teamChipActive: { backgroundColor: ink.ink3, borderColor: ice.base },
  doneCard: {
    borderWidth: 1, borderColor: ink.line, borderRadius: radii.sm,
    backgroundColor: ink.ink1, padding: space.md, gap: space.xs,
  },
  doneTitle: { ...type.bodySm, color: chalk.base },
  doneBody: { ...type.bodySm, color: chalk.faint },
  section: { gap: 0 },
});

const rowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    borderBottomWidth: 1, borderBottomColor: ink.line, paddingVertical: space.sm,
  },
  rowCursor: { backgroundColor: ink.ink1 },
  slotCell: { ...type.data, color: chalk.dim, width: 48 },
  rankCell: { ...type.data, color: chalk.faint, width: 28 },
  main: { flex: 1, gap: 2 },
  owner: { ...type.bodySm, color: chalk.base },
  picked: { ...type.bodySm, color: chalk.dim },
  notMade: { ...type.bodySm, color: chalk.faint },
  undo: { ...type.label, color: semantic.neg },
});
