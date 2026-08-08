// Draft picks — ESPN pick assignment (draft-extensions W3 M-A, flag
// `picks.assign`, ships OFF).
//
// ── Why this screen exists ──────────────────────────────────────────────
// ESPN hosts no rookie drafts. An ESPN dynasty league's rookie draft
// happens off-platform, so there is no platform object to read and FTF
// becomes the league's system of record for pick OWNERSHIP. The user says
// who owns what. Nothing else.
//
// ── No value entry, anywhere (D13) ──────────────────────────────────────
// There is no price input on this screen and there must never be one.
// Every price is a server-side function of (round, years_out, format), so
// a wrong assignment can REDISTRIBUTE value inside a league but can never
// CREATE it (plan §6.2). Prices are not even shown here — this surface is
// about ownership, and mixing a number into it invites someone to edit it.
//
// ── The 192-slot problem, and the three things that answer it ───────────
// Operator decision 3 puts four seasons on the board (current + 3): a
// 12-team, 4-round league is ~192 slots. Three defaults, in the priority
// order the plan sets, are what make that tolerable:
//
//   1. THE PRISTINE GRID IS THE DEFAULT. The seeder gives every team its
//      own picks, so a league with 3 trades leaves 189 slots untouched.
//      The user records DEVIATIONS, not the board. This is why entry
//      correctness matters more than conflict resolution (HLD RB-3) and
//      why nothing here is a giant dirty form.
//   2. ORDER IS SET ONCE, NOT PER SLOT. One drag-to-reorder list of the
//      league's teams for round 1 plus a linear/snake toggle covers the
//      numbering of all 192. The toggle changes NUMBERING ONLY, never
//      ownership, so it is safe at any time and can never conflict.
//   3. EDIT ONLY THE TRADED ONES. Rounds are collapsible, a slot that
//      differs from pristine gets a marker, and every such slot floats
//      into the "Traded picks" summary at the top — across all four
//      seasons — so the review path is "read 3 rows", not "scroll 192".
//
// On top of those: the screen DEFAULTS to the current season with the
// other three behind season tabs, and the confirm-the-board review step is
// PER SEASON (KD-5). One 192-row scroll is the failure mode this design
// exists to avoid, so there is deliberately no "review everything" view.
//
// ── Concurrency ─────────────────────────────────────────────────────────
// Every save is one slot and carries the `assigned_at` this client read.
// A 409 `stale_assignment` opens the conflict prompt with the other
// person's answer already in hand (the 409 body carries the whole current
// row). Keep theirs / use yours — never a silent overwrite.
//
// ── Provenance ──────────────────────────────────────────────────────────
// ESPN will never contradict a wrong grid, so every assigned slot is
// labelled member-entered wherever it appears (rows, summary, conflict
// prompt) and the correction path is one action: tap the row.
//
// Registered on the root stack UNCONDITIONALLY — the flag gates the League
// tab's entry section, not the route, so an in-flight push survives a flag
// revalidation instead of unmounting under the user (the `DraftRoom`
// precedent). Reaching it with the flag off renders the honest unavailable
// state.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import DraggableFlatList, {
  type DragEndParams,
  type RenderItemParams,
} from 'react-native-draggable-flatlist';
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
  fonts,
  scrim,
  shadowSheet,
  DRAG_ACTIVATION_DISTANCE,
} from '../theme/chalkline';
import { Button, Icon, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import Toast from '../components/Toast';
import {
  PICK_ROUNDS_DEFAULT,
  PICK_ROUNDS_MAX,
  PICK_ROUNDS_MIN,
  assignPick,
  getPickAssignments,
  pickAssignmentErrorCode,
  pickAssignmentSubline,
  seedPickGrid,
  staleAssignment,
  type PickAssignments,
  type PickOrderType,
  type PickSlot,
} from '../api/pickAssignment';
import { getLeagueMembers } from '../api/league';
import { relativeTime } from '../utils/relativeTime';
import { haptics } from '../utils/haptics';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';

/** Per-season "I've checked this board" marks. Client-side by design:
 *  there is no server field for a review step, and inventing one would put
 *  a second writer on `draft_picks`. The mark is a reading aid, never an
 *  input to pricing — a confirmed season and an unconfirmed one are the
 *  same rows to the engine. */
const CONFIRM_KEY = 'ftf_pick_board_confirmed_v1';
type ConfirmMap = Record<string, Record<string, string>>;

/** Rounds beyond the first start collapsed. Round 1 is where nearly every
 *  real trade lives, so it is the one worth paying screen height for. */
const OPEN_ROUNDS_BY_DEFAULT = 1;

/** How many rows the traded summary shows before it needs a "show all".
 *  Small on purpose — the summary is a glance, not a second grid. */
const TRADED_SUMMARY_PREVIEW = 6;

/** A team, as the picker and the setup list need it. */
interface TeamRef {
  user_id: string;
  name: string;
}

// ── Numbering ───────────────────────────────────────────────────────────
// Slot numbering is a pure function of (round-1 order, order_type) and is
// computed HERE rather than stored: the server's grain is
// (league, season, round, original_roster) and cannot express a slot, and
// `overall` must never leak onto a draft_picks row (D18). Renumbering is
// therefore free and never touches an owner.

function orderIndex(slot: PickSlot, order: string[]): number {
  const i = order.indexOf(slot.original_user_id);
  if (i >= 0) return i;
  // Orphaned or unknown original owner — fall back to the opaque roster
  // label, which the seeder assigns as str(index + 1).
  const n = parseInt(slot.original_roster_id, 10);
  return Number.isFinite(n) && n > 0 ? n - 1 : 0;
}

function draftPosition(
  slot: PickSlot,
  order: string[],
  orderType: PickOrderType,
  teams: number,
): number {
  const base = orderIndex(slot, order) + 1;
  // Snake reverses the EVEN rounds. Numbering only — the slot's original
  // team, and therefore its pristine owner, is unchanged either way.
  return orderType === 'snake' && slot.round % 2 === 0 ? teams + 1 - base : base;
}

function slotLabel(round: number, position: number): string {
  return `${round}.${position < 10 ? `0${position}` : position}`;
}

/** True when the slot deviates from the pristine seed. Trusts the server's
 *  `is_traded` and falls back to the ids so a payload that forgets the
 *  flag still marks the row rather than hiding a deviation. */
function isDeviation(slot: PickSlot): boolean {
  return slot.is_traded || slot.owner_user_id !== slot.original_user_id;
}

export default function PickAssignmentScreen({ route, navigation }: any = {}) {
  const paramLeagueId: string | undefined = route?.params?.leagueId;
  const sessionLeagueId = useSession((s) => s.league?.league_id);
  const leagueId = paramLeagueId ?? sessionLeagueId ?? null;
  /** M-C's one-action correction deep link lands here with the slot to fix. */
  const focusPickId: string | undefined = route?.params?.focusPickId;

  const enabled = useFlag('picks.assign');
  const queryClient = useQueryClient();

  const [activeSeason, setActiveSeason] = useState<number | null>(null);
  const [openRounds, setOpenRounds] = useState<Record<number, boolean>>({});
  const [showAllTraded, setShowAllTraded] = useState(false);
  const [picking, setPicking] = useState<PickSlot | null>(null);
  const [conflict, setConflict] = useState<{ attempted: PickSlot; current: PickSlot } | null>(null);
  const [pendingOwner, setPendingOwner] = useState<string | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  const assignmentsKey = useMemo(() => ['pick-assignments', leagueId], [leagueId]);
  const query = useQuery({
    queryKey: assignmentsKey,
    queryFn: () => getPickAssignments(leagueId as string),
    enabled: !!leagueId && enabled,
    // The board only changes when a member edits it, and every edit this
    // client makes patches the cache from the mutation response. A poll
    // would spend 40 KB to learn nothing on nearly every tick.
    staleTime: 5 * 60_000,
  });
  const data = query.data;

  // Round-1 order needs NAMES, and an unseeded board has no slots to read
  // them off (`settings.order` is ids only). The members route is the
  // shipped source for that mapping, so the setup step reads it and the
  // grid does not.
  const membersQuery = useQuery({
    queryKey: ['league-members', leagueId],
    queryFn: () => getLeagueMembers(leagueId as string),
    enabled: !!leagueId && enabled && (setupOpen || data?.seeded === false),
    staleTime: 10 * 60_000,
  });

  // ── Per-season confirmation marks ────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!leagueId) return;
      try {
        const raw = await AsyncStorage.getItem(CONFIRM_KEY);
        if (cancelled || !raw) return;
        const parsed = JSON.parse(raw) as ConfirmMap;
        if (parsed && typeof parsed === 'object') setConfirmed(parsed[leagueId] ?? {});
      } catch {
        /* non-fatal — an unreadable mark just shows the season unconfirmed */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [leagueId]);

  const markSeasonConfirmed = useCallback(
    async (season: number) => {
      if (!leagueId) return;
      const next = { ...confirmed, [String(season)]: new Date().toISOString() };
      setConfirmed(next);
      haptics.success();
      setToast({ msg: `${season} board confirmed`, tone: 'success' });
      try {
        const raw = await AsyncStorage.getItem(CONFIRM_KEY);
        const parsed: ConfirmMap = raw ? (JSON.parse(raw) as ConfirmMap) : {};
        parsed[leagueId] = next;
        await AsyncStorage.setItem(CONFIRM_KEY, JSON.stringify(parsed));
      } catch {
        /* non-fatal — the mark stays for this session */
      }
    },
    [confirmed, leagueId],
  );

  // ── Season selection ─────────────────────────────────────────────────
  // Default to the CURRENT season (the payload's first, ascending) with
  // the other three collapsed behind tabs. A correction deep link wins,
  // because it names the exact slot the user came here to fix.
  useEffect(() => {
    if (!data || data.seasons.length === 0) return;
    setActiveSeason((prev) => {
      if (prev !== null && data.seasons.some((s) => s.season === prev)) return prev;
      if (focusPickId) {
        const hit = data.seasons.find((s) => s.slots.some((sl) => sl.pick_id === focusPickId));
        if (hit) return hit.season;
      }
      return data.seasons[0].season;
    });
  }, [data, focusPickId]);

  // A correction link also opens the round its slot lives in — landing on
  // a collapsed accordion is landing on nothing.
  useEffect(() => {
    if (!data || !focusPickId) return;
    for (const s of data.seasons) {
      const hit = s.slots.find((sl) => sl.pick_id === focusPickId);
      if (hit) {
        setOpenRounds((prev) => ({ ...prev, [hit.round]: true }));
        return;
      }
    }
  }, [data, focusPickId]);

  const season = useMemo(
    () => data?.seasons.find((s) => s.season === activeSeason) ?? data?.seasons[0] ?? null,
    [data, activeSeason],
  );

  /** The league's teams, in round-1 order. Derived from the grid's own
   *  original-team pairs, which IS the set the server seeded — so the
   *  picker can never offer an owner the PUT would reject with
   *  `owner_not_in_league`. */
  const teams: TeamRef[] = useMemo(() => {
    if (!data || !season) return [];
    const seen = new Map<string, string>();
    for (const slot of season.slots) {
      if (!seen.has(slot.original_user_id)) seen.set(slot.original_user_id, slot.original_username);
    }
    const order = data.settings.order ?? [];
    return [...seen.entries()]
      .map(([user_id, name]) => ({ user_id, name }))
      .sort((a, b) => {
        const ia = order.indexOf(a.user_id);
        const ib = order.indexOf(b.user_id);
        return (ia < 0 ? Number.MAX_SAFE_INTEGER : ia) - (ib < 0 ? Number.MAX_SAFE_INTEGER : ib);
      });
  }, [data, season]);

  const teamNameOf = useCallback(
    (userId: string | null): string | null => {
      if (!userId) return null;
      return teams.find((t) => t.user_id === userId)?.name ?? null;
    },
    [teams],
  );

  /** Every deviation across ALL four seasons — the review summary. The
   *  cross-season scope is the point: a 2029 first that changed hands is
   *  exactly the slot nobody would scroll to. Contested and orphaned rows
   *  join it because both are open questions the engine has withheld a
   *  price from. */
  const tradedSlots = useMemo(() => {
    if (!data) return [];
    const out: PickSlot[] = [];
    for (const s of data.seasons) {
      for (const slot of s.slots) {
        if (isDeviation(slot) || slot.contested || slot.orphaned) out.push(slot);
      }
    }
    return out.sort((a, b) => a.season - b.season || a.round - b.round);
  }, [data]);

  // ── Mutations ────────────────────────────────────────────────────────
  const applySlot = useCallback(
    (updated: PickSlot, progress: PickAssignments['progress']) => {
      queryClient.setQueryData<PickAssignments>(assignmentsKey, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          progress,
          seasons: prev.seasons.map((s) =>
            s.season === updated.season
              ? { ...s, slots: s.slots.map((sl) => (sl.pick_id === updated.pick_id ? updated : sl)) }
              : s,
          ),
        };
      });
    },
    [assignmentsKey, queryClient],
  );

  const assignMutation = useMutation({
    mutationFn: (args: { slot: PickSlot; ownerUserId: string; ifAssignedAt: string | null }) =>
      assignPick({
        leagueId: leagueId as string,
        pickId: args.slot.pick_id,
        ownerUserId: args.ownerUserId,
        ifAssignedAt: args.ifAssignedAt,
      }),
    onSuccess: (res) => {
      applySlot(res.slot, res.progress);
      setPicking(null);
      setConflict(null);
      setPendingOwner(null);
      haptics.success();
      setToast({ msg: 'Pick updated', tone: 'success' });
    },
    onError: (err, vars) => {
      // The CAS conflict is the ONE failure with a real choice behind it,
      // so it gets a prompt rather than a toast — and the 409 body already
      // carries the other person's row, so no second request is needed.
      const current = staleAssignment(err);
      if (current) {
        setPicking(null);
        setPendingOwner(vars.ownerUserId);
        setConflict({ attempted: vars.slot, current });
        applySlot(current, data?.progress ?? { assigned: 0, total: 0, traded: 0, contested: 0, orphaned: 0 });
        haptics.warning();
        return;
      }
      const code = pickAssignmentErrorCode(err);
      setToast({
        msg:
          code === 'owner_not_in_league'
            ? "That team is no longer in the league — pick someone else."
            : code === 'pick_not_found'
              ? 'That pick is no longer on this board. Pull to refresh.'
              : code === 'feature_disabled'
                ? 'Draft picks are not available for this league right now.'
                : "Couldn't save that pick. Try again.",
        tone: 'warn',
      });
    },
  });

  const seedMutation = useMutation({
    mutationFn: (args: { rounds: number; orderType: PickOrderType; order: string[] }) =>
      seedPickGrid({
        leagueId: leagueId as string,
        rounds: args.rounds,
        orderType: args.orderType,
        order: args.order,
        // Never true from this screen: `reseed` overwrites entered rows,
        // and there is no gesture here worth pointing at that.
        reseed: false,
      }),
    onSuccess: () => {
      setSetupOpen(false);
      haptics.success();
      setToast({ msg: 'Board saved', tone: 'success' });
      void queryClient.invalidateQueries({ queryKey: assignmentsKey });
    },
    onError: (err) => {
      const code = pickAssignmentErrorCode(err);
      setToast({
        msg:
          code === 'rounds_out_of_range'
            ? `Rounds must be between ${PICK_ROUNDS_MIN} and ${PICK_ROUNDS_MAX}.`
            : code === 'bad_order'
              ? "That order doesn't match this league's teams. Pull to refresh."
              : code === 'bad_order_type'
                ? 'Pick either linear or snake.'
                : "Couldn't save the board. Try again.",
        tone: 'warn',
      });
    },
  });

  const commitOwner = useCallback(
    (slot: PickSlot, ownerUserId: string) => {
      assignMutation.mutate({ slot, ownerUserId, ifAssignedAt: slot.assigned_at });
    },
    [assignMutation],
  );

  // ── Branches ─────────────────────────────────────────────────────────

  if (!enabled) {
    return (
      <Shell testID="pick-assignment.unavailable">
        <Text style={type.heading}>Draft picks aren&apos;t available yet</Text>
        <Text style={styles.bodyDim}>
          Assigning who owns each rookie pick isn&apos;t switched on for your account.
        </Text>
      </Shell>
    );
  }

  if (!leagueId) {
    return (
      <Shell testID="pick-assignment.no-league">
        <Text style={type.heading}>No league selected</Text>
        <Text style={styles.bodyDim}>Pick a league first, then come back here.</Text>
      </Shell>
    );
  }

  if (query.isLoading) {
    return (
      <Shell testID="pick-assignment.loading">
        <ActivityIndicator color={ice.base} />
      </Shell>
    );
  }

  if (query.isError || !data) {
    return (
      <Shell testID="pick-assignment.error">
        <Text style={type.heading}>Couldn&apos;t load the picks</Text>
        <Text style={styles.bodyDim}>
          {pickAssignmentErrorCode(query.error) === 'feature_disabled'
            ? 'Draft picks are not available for this league.'
            : 'Something went wrong reaching the server.'}
        </Text>
        <Button
          testID="pick-assignment.retry"
          label="Try again"
          onPress={() => query.refetch()}
          style={{ marginTop: space.lg }}
        />
      </Shell>
    );
  }

  // Setup: the board has never been written, OR the user reopened order
  // and rounds. Same view either way — order is set ONCE for all 192
  // slots, so there is exactly one place it is edited.
  if (!data.seeded || setupOpen) {
    return (
      <SetupView
        seeded={data.seeded}
        settings={data.settings}
        members={
          membersQuery.data?.members?.map((m) => ({
            user_id: m.user_id,
            name: m.display_name || m.username || m.user_id,
          })) ?? teams
        }
        loadingMembers={membersQuery.isLoading}
        saving={seedMutation.isPending}
        onCancel={data.seeded ? () => setSetupOpen(false) : undefined}
        onSave={(rounds, orderType, order) => seedMutation.mutate({ rounds, orderType, order })}
        toast={toast}
        onToastDismiss={() => setToast(null)}
      />
    );
  }

  const orderIds = data.settings.order ?? [];
  const teamCount = teams.length || orderIds.length || 1;
  const rounds = Array.from({ length: Math.max(1, data.settings.rounds) }, (_, i) => i + 1);
  const activeSeasonKey = season ? String(season.season) : '';
  const seasonConfirmedAt = confirmed[activeSeasonKey];
  const visibleTraded = showAllTraded ? tradedSlots : tradedSlots.slice(0, TRADED_SUMMARY_PREVIEW);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="pick-assignment.screen">
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Progress + provenance. The sub-line is the SAME formatter the
            League tab's section renders, so the two can't disagree. */}
        <View style={styles.progressCard} testID="pick-assignment.progress">
          <Text style={styles.progressLine}>
            {pickAssignmentSubline(data.progress, data.seeded)}
          </Text>
          <Text style={styles.bodyDim}>
            Every team starts owning its own picks. You only need to record the ones that were
            traded.
          </Text>
          <MemberEnteredTag testID="pick-assignment.provenance" />
          <Text style={styles.provenanceNote}>
            These picks were entered by you or a leaguemate — ESPN never confirms them. Tap any pick
            to correct it.
          </Text>
          {data.progress.contested > 0 || data.progress.orphaned > 0 ? (
            <Text style={styles.warnLine} testID="pick-assignment.open-questions">
              {data.progress.contested > 0
                ? `${data.progress.contested} pick${data.progress.contested === 1 ? '' : 's'} two people disagree about`
                : ''}
              {data.progress.contested > 0 && data.progress.orphaned > 0 ? ' · ' : ''}
              {data.progress.orphaned > 0
                ? `${data.progress.orphaned} owned by someone who left`
                : ''}
              {' — priced as unknown until someone settles them.'}
            </Text>
          ) : null}
          <Pressable
            testID="pick-assignment.edit-order"
            onPress={() => setSetupOpen(true)}
            accessibilityRole="button"
            accessibilityLabel="Edit draft order and rounds"
            style={({ pressed }) => [styles.inlineLink, pressed && { opacity: 0.6 }]}
          >
            <Text style={styles.inlineLinkText}>
              {data.settings.rounds} rounds · {data.settings.order_type === 'snake' ? 'Snake' : 'Linear'} order — change
            </Text>
          </Pressable>
        </View>

        {/* The review summary. Cross-season on purpose: a traded 2029 first
            is exactly the slot nobody would ever scroll to. */}
        <View style={styles.divider} />
        <TickLabel>Traded picks</TickLabel>
        {tradedSlots.length === 0 ? (
          <Text style={styles.bodyDim} testID="pick-assignment.traded-empty">
            Nothing yet — every team still owns its own picks. Tap a pick below to record a trade.
          </Text>
        ) : (
          <View testID="pick-assignment.traded-summary">
            {visibleTraded.map((slot) => (
              <SlotRow
                key={`sum-${slot.pick_id}`}
                slot={slot}
                label={`${slot.season} ${slotLabel(slot.round, draftPosition(slot, orderIds, data.settings.order_type, teamCount))}`}
                testID={`pick-assignment.traded-row.${slot.pick_id}`}
                highlighted={slot.pick_id === focusPickId}
                onPress={() => setPicking(slot)}
              />
            ))}
            {tradedSlots.length > TRADED_SUMMARY_PREVIEW ? (
              <Pressable
                testID="pick-assignment.traded-toggle"
                onPress={() => setShowAllTraded((v) => !v)}
                accessibilityRole="button"
                style={({ pressed }) => [styles.inlineLink, pressed && { opacity: 0.6 }]}
              >
                <Text style={styles.inlineLinkText}>
                  {showAllTraded ? 'Show fewer' : `Show all ${tradedSlots.length}`}
                </Text>
              </Pressable>
            ) : null}
          </View>
        )}

        {/* Season tabs — current season first and selected; the other three
            stay collapsed behind their tab (KD-5). */}
        <View style={styles.divider} />
        <View style={styles.seasonTabs} testID="pick-assignment.season-tabs">
          {data.seasons.map((s) => {
            const active = s.season === season?.season;
            return (
              <Pressable
                key={s.season}
                testID={`pick-assignment.season-tab.${s.season}`}
                onPress={() => {
                  setActiveSeason(s.season);
                  setOpenRounds({});
                  haptics.selection();
                }}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                accessibilityLabel={`${s.season} picks`}
                style={({ pressed }) => [
                  styles.seasonTab,
                  active && styles.seasonTabActive,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <Text style={[styles.seasonTabText, active && styles.seasonTabTextActive]}>
                  {s.season}
                </Text>
                {confirmed[String(s.season)] ? (
                  <Icon name="check" size={12} color={semantic.pos} />
                ) : null}
              </Pressable>
            );
          })}
        </View>

        {/* Rounds, collapsible. Round 1 open, the rest closed — the pristine
            default means most rounds hold nothing worth reading. */}
        {season
          ? rounds.map((round) => {
              const roundSlots = season.slots
                .filter((s) => s.round === round)
                .sort(
                  (a, b) =>
                    draftPosition(a, orderIds, data.settings.order_type, teamCount) -
                    draftPosition(b, orderIds, data.settings.order_type, teamCount),
                );
              const deviations = roundSlots.filter(
                (s) => isDeviation(s) || s.contested || s.orphaned,
              ).length;
              const open = openRounds[round] ?? round <= OPEN_ROUNDS_BY_DEFAULT;
              return (
                <View key={round}>
                  <Pressable
                    testID={`pick-assignment.round-toggle.${round}`}
                    onPress={() => {
                      setOpenRounds((prev) => ({ ...prev, [round]: !open }));
                      haptics.selection();
                    }}
                    accessibilityRole="button"
                    accessibilityState={{ expanded: open }}
                    accessibilityLabel={`Round ${round}, ${deviations} traded`}
                    style={({ pressed }) => [
                      styles.roundHeader,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                  >
                    <Text style={styles.roundTitle}>Round {round}</Text>
                    <Text style={styles.roundMeta}>
                      {deviations > 0 ? `${deviations} traded` : 'All original'}
                    </Text>
                    <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.dim} />
                  </Pressable>
                  {open
                    ? roundSlots.map((slot) => (
                        <SlotRow
                          key={slot.pick_id}
                          slot={slot}
                          label={slotLabel(
                            slot.round,
                            draftPosition(slot, orderIds, data.settings.order_type, teamCount),
                          )}
                          testID={`pick-assignment.slot.${slot.pick_id}`}
                          highlighted={slot.pick_id === focusPickId}
                          onPress={() => setPicking(slot)}
                        />
                      ))
                    : null}
                </View>
              );
            })
          : null}

        {/* Confirm-the-board — PER SEASON, never one 192-row scroll. */}
        {season ? (
          <View style={styles.confirmBlock}>
            {seasonConfirmedAt ? (
              <Text style={styles.confirmedLine} testID="pick-assignment.season-confirmed">
                {season.season} board confirmed {relativeTime(seasonConfirmedAt)}. Tap any pick to
                change it.
              </Text>
            ) : (
              <>
                <Text style={styles.bodyDim}>
                  Checked the {season.season} picks? Confirming is just a note to yourself —
                  it doesn&apos;t lock anything.
                </Text>
                <Button
                  testID={`pick-assignment.confirm-season.${season.season}`}
                  label={`Confirm ${season.season} board`}
                  variant="secondary"
                  onPress={() => markSeasonConfirmed(season.season)}
                  style={{ marginTop: space.sm }}
                />
              </>
            )}
          </View>
        ) : null}
      </ScrollView>

      {/* Owner picker — the same manager-sheet construction the Acquire
          surfaces use, scoped to this league's teams. */}
      <Modal
        visible={!!picking}
        transparent
        animationType="slide"
        onRequestClose={() => setPicking(null)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setPicking(null)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet} testID="pick-assignment.owner-sheet">
          <View style={styles.grabber} />
          {picking ? (
            <>
              <Text style={type.heading} accessibilityRole="header">
                Who owns{' '}
                {slotLabel(
                  picking.round,
                  draftPosition(picking, orderIds, data.settings.order_type, teamCount),
                )}
                ?
              </Text>
              <Text style={styles.bodyDim}>
                {picking.season} · originally {picking.original_username}
              </Text>
              {picking.contested ? (
                <Text style={styles.warnLine}>
                  Two people have given this pick different owners, so it isn&apos;t priced right
                  now. Setting it here settles it.
                </Text>
              ) : null}
              <ScrollView style={styles.sheetScroll}>
                {teams.map((t) => {
                  const isOwner = t.user_id === picking.owner_user_id;
                  const isOriginal = t.user_id === picking.original_user_id;
                  return (
                    <Pressable
                      key={t.user_id}
                      testID={`pick-assignment.owner-option.${t.user_id}`}
                      accessibilityRole="button"
                      accessibilityState={{ selected: isOwner }}
                      accessibilityLabel={t.name}
                      disabled={assignMutation.isPending}
                      onPress={() => commitOwner(picking, t.user_id)}
                      style={({ pressed }) => [
                        styles.pickerRow,
                        pressed && { backgroundColor: ink.ink3 },
                      ]}
                    >
                      <Text style={[styles.pickerName, isOwner && styles.pickerNameActive]}>
                        {t.name}
                      </Text>
                      {isOriginal ? <Text style={styles.pickerMeta}>original</Text> : null}
                      {isOwner ? <Icon name="check" size={16} color={ice.base} /> : null}
                    </Pressable>
                  );
                })}
              </ScrollView>
            </>
          ) : null}
        </View>
      </Modal>

      {/* CAS conflict. Never a silent overwrite — the other person's answer
          is rendered next to yours and you choose. */}
      <Modal
        visible={!!conflict}
        transparent
        animationType="fade"
        onRequestClose={() => setConflict(null)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setConflict(null)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet} testID="pick-assignment.conflict-sheet">
          <View style={styles.grabber} />
          {conflict ? (
            <>
              <Text style={type.heading} accessibilityRole="header">
                {teamNameOf(conflict.current.assigned_by) ?? 'A leaguemate'} changed this pick{' '}
                {relativeTime(conflict.current.assigned_at) || 'just now'} — keep theirs, or use
                yours?
              </Text>
              <View style={styles.conflictRow} testID="pick-assignment.conflict-current">
                <Text style={styles.slotLabel}>
                  {slotLabel(
                    conflict.current.round,
                    draftPosition(conflict.current, orderIds, data.settings.order_type, teamCount),
                  )}
                </Text>
                <View style={styles.slotBody}>
                  <Text style={styles.slotOwner}>Theirs: {conflict.current.owner_username}</Text>
                  <Text style={styles.slotSub}>
                    Yours: {teamNameOf(pendingOwner) ?? 'your choice'}
                  </Text>
                </View>
              </View>
              <MemberEnteredTag testID="pick-assignment.conflict-provenance" />
              <View style={styles.conflictActions}>
                <Button
                  testID="pick-assignment.conflict.keep-theirs"
                  label="Keep theirs"
                  variant="secondary"
                  onPress={() => {
                    setConflict(null);
                    setPendingOwner(null);
                  }}
                  style={{ flex: 1 }}
                />
                <Button
                  testID="pick-assignment.conflict.use-mine"
                  label="Use mine"
                  loading={assignMutation.isPending}
                  onPress={() => {
                    if (!pendingOwner) return;
                    // Re-issue against the row we were just shown, so the
                    // override is still a compare-and-swap and a THIRD
                    // editor in between conflicts again rather than losing.
                    assignMutation.mutate({
                      slot: conflict.current,
                      ownerUserId: pendingOwner,
                      ifAssignedAt: conflict.current.assigned_at,
                    });
                  }}
                  style={{ flex: 1 }}
                />
              </View>
            </>
          ) : null}
        </View>
      </Modal>

      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="PickAssignment" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// ── Setup: order + rounds, set ONCE for all 192 slots ───────────────────

function SetupView({
  seeded,
  settings,
  members,
  loadingMembers,
  saving,
  onCancel,
  onSave,
  toast,
  onToastDismiss,
}: {
  seeded: boolean;
  settings: PickAssignments['settings'];
  members: TeamRef[];
  loadingMembers: boolean;
  saving: boolean;
  onCancel?: () => void;
  onSave: (rounds: number, orderType: PickOrderType, order: string[]) => void;
  toast: { msg: string; tone?: 'success' | 'warn' } | null;
  onToastDismiss: () => void;
}) {
  const [rounds, setRounds] = useState(settings.rounds || PICK_ROUNDS_DEFAULT);
  const [orderType, setOrderType] = useState<PickOrderType>(settings.order_type || 'linear');
  const [order, setOrder] = useState<TeamRef[]>([]);

  // Seed the drag list from the stored order when there is one, otherwise
  // from the members list. Only fills an EMPTY list, so a drag in progress
  // is never rewritten by a background refetch.
  useEffect(() => {
    if (members.length === 0) return;
    setOrder((prev) => {
      if (prev.length > 0) return prev;
      const byId = new Map(members.map((m) => [m.user_id, m]));
      const stored = (settings.order ?? [])
        .map((id) => byId.get(id))
        .filter((m): m is TeamRef => !!m);
      const rest = members.filter((m) => !stored.some((s) => s.user_id === m.user_id));
      return [...stored, ...rest];
    });
  }, [members, settings.order]);

  const renderItem = useCallback(
    ({ item, drag, isActive, getIndex }: RenderItemParams<TeamRef>) => {
      const idx = getIndex();
      return (
        <Pressable
          testID={`pick-assignment.order-row.${item.user_id}`}
          onLongPress={() => {
            haptics.pickup();
            drag();
          }}
          delayLongPress={180}
          accessibilityRole="button"
          accessibilityLabel={`${item.name}, pick ${(idx ?? 0) + 1}. Hold to reorder.`}
          style={[styles.orderRow, isActive && styles.orderRowActive]}
        >
          <Text style={styles.slotLabel}>{(idx ?? 0) + 1}</Text>
          <Text style={styles.orderName} numberOfLines={1}>
            {item.name}
          </Text>
          <Icon name="swap" size={16} color={chalk.faint} />
        </Pressable>
      );
    },
    [],
  );

  const onDragEnd = useCallback(({ data }: DragEndParams<TeamRef>) => {
    haptics.swipe();
    setOrder(data);
  }, []);

  const header = (
    <View>
      <Text style={type.heading} accessibilityRole="header">
        {seeded ? 'Draft order & rounds' : 'Set up your draft picks'}
      </Text>
      <Text style={styles.bodyDim}>
        ESPN doesn&apos;t run rookie drafts, so Fantasy Trade Finder keeps this league&apos;s pick
        ownership. Set the order once — every team starts owning its own picks, and you only record
        the ones that were traded.
      </Text>

      <View style={styles.divider} />
      <TickLabel>Rounds</TickLabel>
      <View style={styles.stepper} testID="pick-assignment.rounds-stepper">
        <Pressable
          testID="pick-assignment.rounds-minus"
          accessibilityRole="button"
          accessibilityLabel="One fewer round"
          disabled={rounds <= PICK_ROUNDS_MIN}
          onPress={() => setRounds((r) => Math.max(PICK_ROUNDS_MIN, r - 1))}
          style={({ pressed }) => [
            styles.stepperBtn,
            rounds <= PICK_ROUNDS_MIN && styles.stepperBtnOff,
            pressed && { backgroundColor: ink.ink3 },
          ]}
        >
          <Text style={styles.stepperGlyph}>−</Text>
        </Pressable>
        <Text style={styles.stepperValue} testID="pick-assignment.rounds-value">
          {rounds}
        </Text>
        <Pressable
          testID="pick-assignment.rounds-plus"
          accessibilityRole="button"
          accessibilityLabel="One more round"
          disabled={rounds >= PICK_ROUNDS_MAX}
          onPress={() => setRounds((r) => Math.min(PICK_ROUNDS_MAX, r + 1))}
          style={({ pressed }) => [
            styles.stepperBtn,
            rounds >= PICK_ROUNDS_MAX && styles.stepperBtnOff,
            pressed && { backgroundColor: ink.ink3 },
          ]}
        >
          <Text style={styles.stepperGlyph}>+</Text>
        </Pressable>
      </View>

      <View style={styles.divider} />
      <TickLabel>Order type</TickLabel>
      <View style={styles.segmented} testID="pick-assignment.order-type">
        {(['linear', 'snake'] as const).map((t) => {
          const active = orderType === t;
          return (
            <Pressable
              key={t}
              testID={`pick-assignment.order-type.${t}`}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={t === 'linear' ? 'Linear order' : 'Snake order'}
              onPress={() => {
                setOrderType(t);
                haptics.selection();
              }}
              style={({ pressed }) => [
                styles.segment,
                active && styles.segmentActive,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
                {t === 'linear' ? 'Linear' : 'Snake'}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.bodyDim}>
        This changes how picks are NUMBERED, never who owns them — switching it later is safe.
      </Text>

      <View style={styles.divider} />
      <TickLabel>Round 1 order</TickLabel>
      <Text style={styles.bodyDim}>Hold a team to drag it. Later rounds follow this order.</Text>
    </View>
  );

  const footer = (
    <View style={styles.setupFooter}>
      <Button
        testID="pick-assignment.setup-save"
        label={seeded ? 'Save order' : 'Create the board'}
        loading={saving}
        disabled={order.length === 0}
        onPress={() => onSave(rounds, orderType, order.map((t) => t.user_id))}
      />
      {onCancel ? (
        <Button
          testID="pick-assignment.setup-cancel"
          label="Cancel"
          variant="ghost"
          onPress={onCancel}
          style={{ marginTop: space.sm }}
        />
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="pick-assignment.setup">
      {loadingMembers && order.length === 0 ? (
        <View style={styles.center}>
          <ActivityIndicator color={ice.base} />
        </View>
      ) : (
        <DraggableFlatList
          testID="pick-assignment.order-list"
          data={order}
          keyExtractor={(t) => t.user_id}
          renderItem={renderItem}
          onDragEnd={onDragEnd}
          // 18, the value every other drag surface in this app landed on:
          // 5 lets an ordinary vertical scroll cross the threshold and
          // steal the touch into a drag.
          activationDistance={DRAG_ACTIVATION_DISTANCE}
          ListHeaderComponent={header}
          ListFooterComponent={footer}
          contentContainerStyle={styles.scroll}
        />
      )}
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={onToastDismiss}
      />
      <FeedbackFAB activeScreen="PickAssignment" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// ── Rows & chrome ───────────────────────────────────────────────────────

function SlotRow({
  slot,
  label,
  testID,
  highlighted,
  onPress,
}: {
  slot: PickSlot;
  label: string;
  testID: string;
  highlighted?: boolean;
  onPress: () => void;
}) {
  const deviates = isDeviation(slot);
  const flagged = slot.contested || slot.orphaned;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={
        deviates
          ? `${label}, originally ${slot.original_username}, now owned by ${slot.owner_username}. Tap to change.`
          : `${label}, ${slot.original_username}. Tap to change.`
      }
      style={({ pressed }) => [
        styles.slotRow,
        highlighted && styles.slotRowHighlighted,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      {/* Deviation marker — a flare tick, the informational-highlight
          accent, never an action color (ADR-005). */}
      <View style={[styles.slotTick, deviates && styles.slotTickOn, flagged && styles.slotTickWarn]} />
      <Text style={styles.slotLabel}>{label}</Text>
      <View style={styles.slotBody}>
        <Text style={styles.slotOwner} numberOfLines={1}>
          {slot.owner_username}
        </Text>
        {deviates ? (
          <Text style={styles.slotSub} numberOfLines={1}>
            from {slot.original_username}
          </Text>
        ) : null}
        {slot.contested ? (
          <Text style={styles.slotWarn}>Two answers — not priced</Text>
        ) : slot.orphaned ? (
          <Text style={styles.slotWarn}>Owner left the league — not priced</Text>
        ) : null}
      </View>
      {slot.source === 'user' ? <MemberEnteredTag compact /> : null}
      <Icon name="chevron-right" size={16} color={chalk.faint} />
    </Pressable>
  );
}

/** D17 — provenance is inescapable. A member-entered pick says so wherever
 *  it is displayed; ESPN will never contradict a wrong grid, so the label
 *  is the only signal that this is an assertion rather than a fact. */
function MemberEnteredTag({ compact, testID }: { compact?: boolean; testID?: string }) {
  return (
    <View style={[styles.provTag, compact && styles.provTagCompact]} testID={testID}>
      <View style={styles.provTick} />
      <Text style={styles.provText}>{compact ? 'ENTERED' : 'MEMBER-ENTERED'}</Text>
    </View>
  );
}

function Shell({ children, testID }: { children: React.ReactNode; testID: string }) {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID={testID}>
      <View style={styles.center}>{children}</View>
      <FeedbackFAB activeScreen="PickAssignment" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg, gap: space.sm },

  bodyDim: { ...type.bodySm, color: chalk.dim },
  warnLine: { ...type.bodySm, color: semantic.warn },

  divider: { height: 1, backgroundColor: ink.line },

  progressCard: {
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    padding: space.md,
    gap: space.xs,
  },
  progressLine: { ...type.title, color: chalk.base },
  provenanceNote: { ...type.bodySm, color: chalk.dim },

  inlineLink: { alignSelf: 'flex-start', minHeight: 32, justifyContent: 'center' },
  inlineLinkText: {
    ...type.bodySm,
    color: ice.base,
    textDecorationLine: 'underline',
  },

  // ── Season tabs ──────────────────────────────────────────────────────
  seasonTabs: { flexDirection: 'row', gap: space.xs },
  seasonTab: {
    flex: 1,
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
  },
  seasonTabActive: { borderColor: ice.base, backgroundColor: ink.ink2 },
  seasonTabText: { fontFamily: fonts.dataSemi, fontSize: 13, color: chalk.dim },
  seasonTabTextActive: { color: chalk.base },

  // ── Rounds ───────────────────────────────────────────────────────────
  roundHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  roundTitle: { ...type.title, color: chalk.base, flex: 1 },
  roundMeta: { ...type.label, color: chalk.dim },

  // ── Slot rows ────────────────────────────────────────────────────────
  slotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  slotRowHighlighted: { backgroundColor: ink.ink2 },
  slotTick: { width: 3, height: 20, backgroundColor: 'transparent' },
  slotTickOn: { backgroundColor: flare.base },
  slotTickWarn: { backgroundColor: semantic.warn },
  slotLabel: {
    fontFamily: fonts.dataSemi,
    fontSize: 13,
    color: chalk.dim,
    minWidth: 52,
  },
  slotBody: { flex: 1, minWidth: 0 },
  slotOwner: { ...type.bodySm, color: chalk.base },
  slotSub: { ...type.label, color: chalk.faint },
  slotWarn: { ...type.label, color: semantic.warn },

  // ── Provenance tag ───────────────────────────────────────────────────
  provTag: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    alignSelf: 'flex-start',
    minHeight: 22,
    paddingHorizontal: space.xs,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  provTagCompact: { minHeight: 20 },
  provTick: { width: 3, height: 9, backgroundColor: flare.base },
  provText: { fontFamily: fonts.dataSemi, fontSize: 9, letterSpacing: 0.5, color: chalk.dim },

  // ── Confirm ──────────────────────────────────────────────────────────
  confirmBlock: { marginTop: space.lg, gap: space.xs },
  confirmedLine: { ...type.bodySm, color: semantic.pos },

  // ── Setup ────────────────────────────────────────────────────────────
  stepper: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  stepperBtn: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
  },
  stepperBtnOff: { opacity: 0.4 },
  stepperGlyph: { fontFamily: fonts.dataSemi, fontSize: 20, color: chalk.base },
  stepperValue: { fontFamily: fonts.dataSemi, fontSize: 22, color: chalk.base, minWidth: 32, textAlign: 'center' },

  segmented: { flexDirection: 'row', gap: space.xs },
  segment: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
  },
  segmentActive: { borderColor: ice.base, backgroundColor: ink.ink2 },
  segmentText: { ...type.bodySm, color: chalk.dim },
  segmentTextActive: { color: chalk.base },

  orderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 48,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    backgroundColor: ink.ink0,
  },
  orderRowActive: { backgroundColor: ink.ink2 },
  orderName: { ...type.body, color: chalk.base, flex: 1, minWidth: 0 },
  setupFooter: { marginTop: space.lg },

  // ── Sheets ───────────────────────────────────────────────────────────
  backdrop: { flex: 1, backgroundColor: scrim },
  sheet: {
    backgroundColor: ink.ink1,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.line,
    marginBottom: space.sm,
  },
  sheetScroll: { maxHeight: 320, marginTop: space.sm },
  pickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 48,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  pickerName: { ...type.body, color: chalk.base, flex: 1, minWidth: 0 },
  pickerNameActive: { color: ice.base },
  pickerMeta: { ...type.label, color: chalk.faint },

  conflictRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 48,
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2,
  },
  conflictActions: { flexDirection: 'row', gap: space.sm, marginTop: space.sm },
});
