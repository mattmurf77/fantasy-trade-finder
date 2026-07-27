import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
  FlatList,
  Linking,
  Modal,
  RefreshControl,
  ScrollView,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  position,
  space,
  radii,
  scrim,
  shadowSheet,
  type,
} from '../theme/chalkline';
import { Button, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import PlayerCard from '../components/PlayerCard';
import PositionChip from '../components/PositionChip';
import {
  getFreeAgents,
  type FreeAgentDropCandidates,
  type FreeAgentRow,
  type FreeAgentRosterCapacity,
  type FreeAgentWaivers,
} from '../api/league';
import { ApiError } from '../api/client';
import { isEspnLeague } from '../api/espn';
import { isMflLeague, isFleaflickerLeague } from '../api/platformLink';
import { readErrorCopy } from '../utils/verification';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Position } from '../shared/types';

type PositionFilter = Position | 'ALL';
const FILTERS: PositionFilter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

// #179 — where an "Add" can actually be executed. Sleeper publishes no
// write API for roster moves, so the honest Sleeper flow is the claim-
// preparation sheet (ClaimSheet below): FAAB bid + budget, drop selection,
// then a deep-link into the league's players page in the Sleeper app/site
// (same pragmatic pattern as the trade-propose deep-link in TradesScreen).
// Platform-linked leagues (ESPN / MFL / Fleaflicker) are read-only imports
// today — no write path, so the Add affordance renders dimmed and explains
// why on tap. 'local' covers demo/local leagues that exist nowhere outside
// FTF.
type AddPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker' | 'local';

function resolveAddPlatform(leagueId: string | undefined, isDemo: boolean): AddPlatform {
  if (!leagueId || isDemo) return 'local';
  if (isEspnLeague(leagueId)) return 'espn';
  if (isMflLeague(leagueId)) return 'mfl';
  if (isFleaflickerLeague(leagueId)) return 'fleaflicker';
  // Real Sleeper league ids are numeric; anything else is a local league.
  return /^\d+$/.test(leagueId) ? 'sleeper' : 'local';
}

const NO_ADD_REASON: Record<Exclude<AddPlatform, 'sleeper'>, { title: string; body: string }> = {
  espn: {
    title: "Can't add in ESPN leagues yet",
    body:
      'This league is imported from ESPN with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open the ' +
      'ESPN Fantasy app to add this player.',
  },
  mfl: {
    title: "Can't add in MFL leagues yet",
    body:
      'This league is linked to MyFantasyLeague with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open MFL ' +
      'to add this player.',
  },
  fleaflicker: {
    title: "Can't add in Fleaflicker leagues yet",
    body:
      'This league is linked to Fleaflicker with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open ' +
      'Fleaflicker to add this player.',
  },
  local: {
    title: "Can't add in this league",
    body:
      'This league isn’t connected to a fantasy platform, so there’s ' +
      'no roster to add this player to.',
  },
};

// #179 — non-Sleeper Add handling: honest "why not" alert (read-only
// platform imports / local leagues). Sleeper leagues open the claim sheet
// instead (ClaimSheet below).
function explainNoAdd(addPlatform: Exclude<AddPlatform, 'sleeper'>) {
  const reason = NO_ADD_REASON[addPlatform];
  Alert.alert(reason.title, reason.body);
}

// Free-agent finder (#143) — League-stack route 'FreeAgents' (entered from
// the League tab's "Free agents" row). Best available players in the
// league, ranked by the CALLER'S board values (consensus fallback for
// anyone they haven't ranked), with position filter pills and a
// "Drop: <player> (+delta)" subline whenever the backend found a lower-
// valued same-position player on the user's roster to cut for the FA.
export default function FreeAgentsScreen() {
  const navigation = useNavigation<any>();
  const [filter, setFilter] = useState<PositionFilter>('ALL');
  const leagueId = useSession((s) => s.league?.league_id);
  const isDemo = useSession((s) => s.isDemo);
  // S4 PRD-05 (ux.empty_state_ctas): the no-league state gets the action
  // its copy describes. Flag off: copy-only, as before.
  const emptyCtasOn = useFlag('ux.empty_state_ctas');

  const query = useQuery({
    // Position is part of the key: the backend caps each response at ~50
    // rows AFTER filtering, so each position gets its own full page.
    queryKey: ['free-agents', leagueId, filter],
    queryFn: () => getFreeAgents(leagueId as string, filter),
    enabled: !!leagueId,
    staleTime: 60_000,
  });

  const onRefresh = useCallback(() => {
    query.refetch();
  }, [query]);

  const rows = query.data?.free_agents ?? [];
  const consensusOnly = !!query.data && !query.data.user_has_rankings;
  // #179 — Add affordance context (platform + Sleeper claim-sheet data).
  const addPlatform = resolveAddPlatform(leagueId, isDemo);
  // Sleeper leagues: Add opens the claim-preparation sheet for this row.
  const [claimTarget, setClaimTarget] = useState<FreeAgentRow | null>(null);
  const onAdd = useCallback(
    (row: FreeAgentRow) => {
      if (!leagueId) return;
      if (addPlatform === 'sleeper') setClaimTarget(row);
      else explainNoAdd(addPlatform);
    },
    [leagueId, addPlatform],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {/* PositionTabs spec: segmented hairline group; active segment = ink3
          fill + 2px underline in that position's color (ALL = ice). */}
      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              testID={`free-agents.pos-tab.${f.toLowerCase()}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={f === 'ALL' ? 'All positions' : f}
              onPress={() => setFilter(f)}
              style={({ pressed }) => [
                styles.filterSegment,
                active && [
                  styles.filterSegmentActive,
                  { borderBottomColor: underlineColor(f) },
                ],
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.filterText, active && styles.filterTextActive]}>
                {f}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {!leagueId ? (
        <View style={styles.centerFill}>
          <Text testID="free-agents.empty-text" style={styles.emptyBody}>
            Connect a league to see its free agents.
          </Text>
          {emptyCtasOn ? (
            <Button
              testID="free-agents.pick-league"
              label="Pick a league"
              variant="primary"
              onPress={() => navigation.navigate('LeaguePicker')}
            />
          ) : null}
        </View>
      ) : query.isLoading ? (
        <View style={styles.centerFill}>
          <ActivityIndicator color={ice.base} />
        </View>
      ) : query.isError ? (
        <View style={styles.centerFill}>
          <Text style={styles.errorText}>
            {/* #178 — the backend refuses to serve (503 rosters_unavailable)
                rather than list rostered players as FAs; surface its honest
                message instead of the generic copy. */}
            {query.error instanceof ApiError &&
            (query.error.body as any)?.error === 'rosters_unavailable'
              ? query.error.message
              : readErrorCopy(query.error, "Couldn't load free agents.")}
          </Text>
          <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
        </View>
      ) : (
        <FlatList
          testID="free-agents.list"
          data={rows}
          keyExtractor={(r) => r.player_id}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={query.isFetching && !query.isLoading}
              onRefresh={onRefresh}
              tintColor={ice.base}
            />
          }
          ListHeaderComponent={
            <View>
              <Text style={styles.explainer}>
                Best available players in your league, ranked by your values.
                Drop lines show the weakest same-position player on your
                roster worth less than the free agent.
              </Text>
              {consensusOnly ? (
                <Text style={styles.consensusNote}>
                  You haven't ranked anyone yet, so this list uses consensus
                  values. Rank players to make it yours.
                </Text>
              ) : null}
            </View>
          }
          ListEmptyComponent={
            <View style={styles.centerFill}>
              <Text testID="free-agents.empty-text" style={styles.emptyBody}>
                {filter === 'ALL'
                  ? 'No free agents found — every valued player is rostered.'
                  : `No ${filter} free agents found.`}
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <FreeAgentRowCard row={item} addPlatform={addPlatform} onAdd={onAdd} />
          )}
        />
      )}
      {/* #179 claim sheet — keyed by player so bid/drop state resets per
          claim. Only ever mounted for Sleeper leagues (onAdd gates). */}
      {claimTarget && leagueId ? (
        <ClaimSheet
          key={claimTarget.player_id}
          row={claimTarget}
          leagueId={leagueId}
          capacity={query.data?.roster_capacity}
          waivers={query.data?.waivers}
          dropCandidates={query.data?.drop_candidates}
          onClose={() => setClaimTarget(null)}
        />
      ) : null}
      {/* #188 — root-stack push covers RootNav's FAB mount; carry our own.
          No tab bar under this screen → aboveTabBar={false}. */}
      <FeedbackFAB activeScreen="FreeAgents" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// #179 claim-preparation sheet (DynastyDealer-style, honest about write
// limits). Sleeper publishes NO write API, so FTF PREPARES the claim —
// FAAB bid sizing against the caller's live budget, drop selection from
// the value-ascending candidate list when the roster is full — and the CTA
// hands off to Sleeper's players page (same deep-link target as the old
// alert flow) where the user executes it.
function ClaimSheet({
  row,
  leagueId,
  capacity,
  waivers,
  dropCandidates,
  onClose,
}: {
  row: FreeAgentRow;
  leagueId: string;
  capacity: FreeAgentRosterCapacity | null | undefined;
  waivers: FreeAgentWaivers | null | undefined;
  dropCandidates: FreeAgentDropCandidates | null | undefined;
  onClose: () => void;
}) {
  const [bid, setBid] = useState('');
  const [dropId, setDropId] = useState<string | null>(null);

  const faab = waivers?.type === 'faab' ? waivers.faab : null;
  const remaining = faab?.remaining ?? null;
  const bidNum = bid === '' ? null : Number(bid);
  const bidTooHigh = bidNum != null && remaining != null && bidNum > remaining;

  const openSlots = capacity?.open_slots ?? null;
  const candidates = dropCandidates?.players ?? [];
  const untouchablesExcluded = dropCandidates?.untouchables_excluded ?? 0;
  // Open slots known and > 0 ⇒ no drop needed; 0 (or unknown, when we have
  // candidates) ⇒ show the least-valuable-first drop list.
  const showDropList = openSlots !== null ? openSlots === 0 : candidates.length > 0;

  const openSleeper = () => {
    // Lands on the league's Players (available players) surface — Sleeper
    // has no public write API, so the claim itself happens in Sleeper.
    Linking.openURL(`https://sleeper.com/leagues/${leagueId}/players`).catch(() => {});
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable
        style={sheetStyles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={sheetStyles.sheet} testID="fa-claim.sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={sheetStyles.grabber} />
          <ScrollView
            contentContainerStyle={sheetStyles.content}
            keyboardShouldPersistTaps="handled"
          >
            {/* Player header */}
            <View style={sheetStyles.header}>
              <View style={sheetStyles.headerText}>
                <Text style={type.heading} numberOfLines={1} accessibilityRole="header">
                  Claim {row.name}
                </Text>
                <View style={sheetStyles.headerMeta}>
                  <PositionChip position={row.position} size="sm" />
                  <Text style={type.bodySm}>
                    {row.team ?? 'FA'} · FA {row.position}
                    {row.pos_rank}
                  </Text>
                  <Text style={sheetStyles.headerValue}>
                    {Math.round(row.value).toLocaleString('en-US')}
                  </Text>
                </View>
              </View>
              <Button label="Cancel" variant="ghost" compact onPress={onClose} />
            </View>

            {/* FAAB bid — only for FAAB leagues; priority-waiver leagues get
                the honest one-liner instead. */}
            {faab ? (
              <View style={sheetStyles.section}>
                <TickLabel>FAAB BID</TickLabel>
                <View style={sheetStyles.bidRow}>
                  <Text style={sheetStyles.bidCurrency}>$</Text>
                  <TextInput
                    testID="fa-claim.bid"
                    value={bid}
                    onChangeText={(t) => setBid(t.replace(/[^0-9]/g, ''))}
                    keyboardType="number-pad"
                    accessibilityLabel="FAAB bid amount"
                    style={[
                      sheetStyles.bidInput,
                      bidTooHigh && sheetStyles.bidInputInvalid,
                    ]}
                    placeholder="0"
                    placeholderTextColor={chalk.faint}
                    maxLength={4}
                  />
                  {remaining != null ? (
                    <Text style={type.bodySm}>
                      Budget: ${remaining.toLocaleString('en-US')} remaining
                    </Text>
                  ) : null}
                </View>
                {bidTooHigh ? (
                  <Text style={sheetStyles.bidError}>
                    That's more than your ${remaining!.toLocaleString('en-US')}{' '}
                    remaining — lower the bid.
                  </Text>
                ) : null}
              </View>
            ) : waivers?.type === 'rolling' || waivers?.type === 'reverse_standings' ? (
              <View style={sheetStyles.section}>
                <Text style={type.bodySm}>
                  This is a waiver priority league — no FAAB bid needed.
                </Text>
              </View>
            ) : null}

            {/* Drop selection — least valuable first (or the open-slots
                all-clear when no drop is needed). */}
            <View style={sheetStyles.section}>
              {!showDropList ? (
                openSlots !== null ? (
                  <Text style={type.bodySm}>
                    You have {openSlots} open roster{' '}
                    {openSlots === 1 ? 'slot' : 'slots'} — no drop needed.
                  </Text>
                ) : null
              ) : (
                <>
                  <TickLabel>SELECT A PLAYER TO DROP</TickLabel>
                  <Text style={sheetStyles.sectionHint}>
                    {openSlots === 0
                      ? 'Your roster is full — least valuable first.'
                      : 'If your roster is full, pick a drop — least valuable first.'}
                  </Text>
                  {candidates.map((c) => {
                    const selected = c.id === dropId;
                    return (
                      <Pressable
                        key={c.id}
                        testID={`fa-claim.drop.${c.id}`}
                        accessibilityRole="radio"
                        accessibilityState={{ selected }}
                        accessibilityLabel={`Drop ${c.name}`}
                        onPress={() => setDropId(selected ? null : c.id)}
                        style={({ pressed }) => [
                          sheetStyles.dropRow,
                          selected && sheetStyles.dropRowSelected,
                          pressed && { backgroundColor: ink.ink3 },
                        ]}
                      >
                        <View style={[sheetStyles.radio, selected && sheetStyles.radioSelected]}>
                          {selected ? <View style={sheetStyles.radioDot} /> : null}
                        </View>
                        <PositionChip position={c.position} size="sm" />
                        <Text style={sheetStyles.dropName} numberOfLines={1}>
                          {c.name}
                        </Text>
                        <Text style={type.data}>
                          {Math.round(c.value).toLocaleString('en-US')}
                        </Text>
                      </Pressable>
                    );
                  })}
                  {candidates.length === 0 ? (
                    <Text style={type.bodySm}>
                      No droppable players found on your roster.
                    </Text>
                  ) : null}
                  {untouchablesExcluded > 0 ? (
                    <Text style={sheetStyles.untouchableNote}>
                      {untouchablesExcluded === 1
                        ? '1 untouchable player was'
                        : `${untouchablesExcluded} untouchable players were`}{' '}
                      left out of the drop suggestions.
                    </Text>
                  ) : null}
                </>
              )}
            </View>

            <Button
              testID="fa-claim.open-sleeper"
              label="Open in Sleeper to claim"
              variant="primary"
              disabled={bidTooHigh}
              onPress={openSleeper}
            />
            <Text style={sheetStyles.footer}>
              Sleeper doesn't allow apps to submit claims — finish in Sleeper.
            </Text>
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

// One FA row: dense PlayerCard (60px two-line) — line 2 carries the drop
// suggestion; right cluster = positional FA rank over the caller-board value.
// #179: rightSlot carries the Add affordance — secondary for Sleeper leagues
// (deep-link hand-off), ghost/dim for platforms with no write path (tap
// explains why).
function FreeAgentRowCard({
  row,
  addPlatform,
  onAdd,
}: {
  row: FreeAgentRow;
  addPlatform: AddPlatform;
  onAdd: (row: FreeAgentRow) => void;
}) {
  const drop = row.drop_suggestion;
  // S2 PRD-04 ride-along (visual.chalkline_cleanup): "No drop worth making"
  // is content, not a placeholder — faint → dim.
  const cleanupOn = useFlag('visual.chalkline_cleanup');
  const canDeepLink = addPlatform === 'sleeper';
  return (
    <View style={styles.rowWrap}>
      <PlayerCard
        testID={`free-agents.row.${row.player_id}`}
        dense
        player={{
          id: row.player_id,
          name: row.name,
          position: row.position,
          team: row.team,
          age: row.age,
        }}
        posRank={`${row.position}${row.pos_rank}`}
        value={row.value}
        rightSlot={
          <Button
            testID={`free-agents.add.${row.player_id}`}
            label="Add"
            variant={canDeepLink ? 'secondary' : 'ghost'}
            compact
            onPress={() => onAdd(row)}
          />
        }
        statsSlot={
          drop ? (
            <Text style={styles.dropLine} numberOfLines={1}>
              Drop: {drop.name}{' '}
              <Text style={styles.dropDelta}>
                (+{Math.round(drop.delta).toLocaleString('en-US')})
              </Text>
            </Text>
          ) : (
            <Text
              style={[styles.noDropLine, cleanupOn && { color: chalk.dim }]}
              numberOfLines={1}
            >
              No drop worth making
            </Text>
          )
        }
      />
    </View>
  );
}

// Active-tab underline per PositionTabs spec: position color, ice for ALL.
function underlineColor(f: PositionFilter): string {
  switch (f) {
    case 'QB': return position.qb;
    case 'RB': return position.rb;
    case 'WR': return position.wr;
    case 'TE': return position.te;
    default:   return ice.base;
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },

  filterRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.md,
    marginBottom: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  filterSegment: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  filterSegmentActive: {
    backgroundColor: ink.ink3,
  },
  filterText: { ...type.label },
  filterTextActive: { color: chalk.base },

  listContent: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
  },
  explainer: {
    ...type.bodySm,
    color: chalk.dim,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  consensusNote: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    marginBottom: space.sm,
  },
  rowWrap: {},

  dropLine: {
    ...type.data,
    fontSize: 11,
    color: chalk.dim,
    flexShrink: 1,
  },
  dropDelta: {
    color: semantic.pos,
  },
  noDropLine: {
    ...type.data,
    fontSize: 11,
    color: chalk.faint,
  },

  centerFill: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xl,
    paddingHorizontal: space.lg,
    gap: space.sm,
  },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
  errorText: { ...type.bodySm, color: semantic.neg },
});

// #179 claim sheet — construction mirrors SwapPlayerSheet (components.md →
// Sheets, modals, menus): ink-2 surface, top radius, grabber, sheet shadow.
const sheetStyles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  content: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    gap: space.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.md,
    paddingTop: space.sm,
  },
  headerText: { flex: 1, gap: space.xs },
  headerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  headerValue: { ...type.data, color: chalk.base },

  section: { gap: space.sm },
  sectionHint: { ...type.bodySm, color: chalk.dim },

  bidRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  bidCurrency: { ...type.data, color: chalk.dim },
  bidInput: {
    ...type.data,
    fontSize: 16,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minWidth: 72,
    textAlign: 'right',
  },
  bidInputInvalid: { borderColor: semantic.neg },
  bidError: { ...type.bodySm, color: semantic.neg },

  dropRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: 'transparent',
    borderRadius: radii.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  dropRowSelected: {
    borderColor: ice.base,
    borderBottomWidth: 1,
    borderBottomColor: ice.base,
    backgroundColor: ink.ink3,
  },
  dropName: { ...type.title, flex: 1 },
  // Selection tick — square per the radius rule (no radius >8px outside
  // specced pills); radio semantics live in accessibilityRole/state.
  radio: {
    width: 18,
    height: 18,
    borderRadius: radii.xs,
    borderWidth: 1.5,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: ice.base },
  radioDot: {
    width: 8,
    height: 8,
    borderRadius: 1,
    backgroundColor: ice.base,
  },
  untouchableNote: { ...type.bodySm, color: chalk.dim },
  footer: {
    ...type.bodySm,
    color: chalk.dim,
    textAlign: 'center',
  },
});
