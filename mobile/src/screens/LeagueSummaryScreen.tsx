import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  RefreshControl,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  space,
  radii,
  type,
  position as positionColors,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { Badge, Icon } from '../components/chalkline';
import PlayerCard from '../components/PlayerCard';
import {
  getPowerRankings,
  type PowerRankedPlayer,
  type PowerRankedTeam,
} from '../api/league';
import { useSession } from '../state/useSession';

// League rankings ("power rankings", #142/#144) — every team in the league
// ranked by summed roster value, from GET /api/league/power-rankings.
// Basis toggle: Consensus (universal-pool values) | My board (the caller's
// own values, consensus fallback for unranked players). Redraft is a
// disabled "(soon)" chip — the backend reserves basis=redraft but answers
// 501 not_available (FTF's value source is dynasty-only today), so the
// client never requests it.
// Tapping a team opens its roster grouped by position, sorted by value
// within each group (#144), rendered with dense PlayerCard rows.
// Entered from the League tab's "League rankings" row (root-stack route
// 'LeagueSummary').

type UiBasis = 'consensus' | 'personal';

const CORE_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

// Compact 0–10k value for the per-position mini-summary (fits one line).
function fmtK(v: number): string {
  if (v >= 1000) return `${(Math.round(v / 100) / 10).toFixed(1)}k`;
  return String(Math.round(v));
}

export default function LeagueSummaryScreen() {
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const [basis, setBasis] = useState<UiBasis>('consensus');
  // Store the selected team's id (not the object) so a basis switch while
  // the roster overlay is open re-derives the team from fresh data.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['league-power-rankings', leagueId, basis],
    queryFn: () => getPowerRankings(leagueId!, basis),
    enabled: !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const teams = query.data?.teams ?? [];
  const selected = selectedId
    ? teams.find((t) => t.user_id === selectedId) ?? null
    : null;

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
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={query.isFetching && !!query.data}
            onRefresh={() => query.refetch()}
            tintColor={ice.base}
          />
        }
      >
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
        <Text style={[type.bodySm, styles.basisHint]}>
          {basis === 'consensus'
            ? 'Teams ranked by total roster value on community consensus.'
            : 'Teams ranked by total roster value on YOUR board — players you haven’t ranked use consensus.'}
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
        ) : (
          teams.map((t) => (
            <TeamRow
              key={t.user_id}
              team={t}
              onPress={() => setSelectedId(t.user_id)}
            />
          ))
        )}
      </ScrollView>

      {/* #144 — team drill-in: roster grouped by position, value-desc within
          each group. Overlay-card pattern shared with LeagueScreen's member
          roster (ink-2 card, solid scrim, X close). */}
      <Modal
        visible={!!selected}
        transparent
        animationType="fade"
        onRequestClose={() => setSelectedId(null)}
      >
        <Pressable style={styles.overlayBackdrop} onPress={() => setSelectedId(null)} />
        {selected ? (
          <View style={styles.overlayCard}>
            <View style={styles.overlayHead}>
              <Text style={type.heading} numberOfLines={1}>
                {selected.display_name || selected.username || selected.user_id}
              </Text>
              <Pressable
                testID="league-summary.roster-close"
                onPress={() => setSelectedId(null)}
                hitSlop={12}
                accessibilityRole="button"
                accessibilityLabel="Close roster overlay"
                style={({ pressed }) => [styles.overlayClose, pressed && styles.overlayClosePressed]}
              >
                <Icon name="x" size={20} color={chalk.dim} />
              </Pressable>
            </View>
            <Text style={[type.data, styles.overlaySub]}>
              {`#${selected.rank} · ${Math.round(selected.total_value).toLocaleString('en-US')} total value`}
            </Text>
            <ScrollView style={styles.overlayList} contentContainerStyle={{ gap: space.xs }}>
              {groupRoster(selected).map((g) => (
                <View key={g.pos}>
                  <View style={styles.groupHead}>
                    <Text
                      style={[
                        styles.groupLabel,
                        { color: positionColors[g.pos.toLowerCase() as keyof typeof positionColors] ?? chalk.dim },
                      ]}
                    >
                      {g.pos}
                    </Text>
                    <Text style={[type.data, styles.groupMeta]}>
                      {`${g.rows.length} · ${fmtK(g.value)}`}
                    </Text>
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
                      />
                    </View>
                  ))}
                </View>
              ))}
            </ScrollView>
          </View>
        ) : null}
      </Modal>
    </SafeAreaView>
  );
}

// Bucket a team's (already server-ordered) roster into position sections for
// the drill-in headers. Rows keep their value-desc order within each group.
function groupRoster(team: PowerRankedTeam): Array<{
  pos: string;
  rows: PowerRankedPlayer[];
  value: number;
}> {
  const buckets = new Map<string, PowerRankedPlayer[]>();
  for (const r of team.roster) {
    const key = (CORE_POSITIONS as readonly string[]).includes(r.position) ? r.position : 'Other';
    const arr = buckets.get(key);
    if (arr) arr.push(r);
    else buckets.set(key, [r]);
  }
  return [...CORE_POSITIONS, 'Other']
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

// One ranked team — LeagueRow construction (hairline-separated list row):
// rank numeral, name + You badge, per-position value mini-summary, total
// value + chevron on the right.
function TeamRow({ team, onPress }: { team: PowerRankedTeam; onPress: () => void }) {
  const minis = useMemo(
    () =>
      CORE_POSITIONS.map((pos) => ({
        pos,
        value: team.positions?.[pos]?.value ?? 0,
      })),
    [team],
  );
  return (
    <Pressable
      testID={`league-summary.team.${team.user_id}`}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`View ${team.display_name || team.username} roster`}
      style={({ pressed }) => [styles.teamRow, pressed && { backgroundColor: ink.ink3 }]}
    >
      <Text style={styles.teamRank}>{team.rank}</Text>
      <View style={styles.teamMain}>
        <View style={styles.teamNameRow}>
          <Text style={[type.title, styles.teamName]} numberOfLines={1}>
            {team.display_name || team.username || team.user_id}
          </Text>
          {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
        </View>
        <View style={styles.teamMinis}>
          {minis.map((m) => (
            <View key={m.pos} style={styles.miniPair}>
              <Text
                style={[
                  styles.miniPos,
                  { color: positionColors[m.pos.toLowerCase() as keyof typeof positionColors] ?? chalk.dim },
                ]}
              >
                {m.pos}
              </Text>
              <Text style={styles.miniVal}>{fmtK(m.value)}</Text>
            </View>
          ))}
        </View>
      </View>
      <View style={styles.teamRight}>
        <Text style={type.data}>{Math.round(team.total_value).toLocaleString('en-US')}</Text>
        <Icon name="chevron-right" size={14} color={chalk.dim} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl },

  basisRow: { flexDirection: 'row', gap: space.sm },
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
  basisHint: { marginTop: space.sm, marginBottom: space.md },

  teamRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  teamRank: {
    ...type.dataLg,
    width: 32,
    textAlign: 'center',
    color: chalk.dim,
  },
  teamMain: { flex: 1, gap: 3 },
  teamNameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  teamName: { flexShrink: 1 },
  teamMinis: { flexDirection: 'row', gap: space.md, flexWrap: 'wrap' },
  miniPair: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
  miniPos: { ...type.label, fontSize: 10 },
  miniVal: { ...type.data, fontSize: 11, color: chalk.dim },
  teamRight: { flexDirection: 'row', alignItems: 'center', gap: space.xs },

  overlayBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  overlayCard: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    top: '10%',
    maxHeight: '80%',
    backgroundColor: ink.ink2,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
    ...shadowSheet,
  },
  overlayHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  overlayClose: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overlayClosePressed: { backgroundColor: ink.ink3 },
  overlaySub: { color: chalk.dim },
  overlayList: { marginTop: space.xs },

  groupHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
  },
  groupLabel: { ...type.label },
  groupMeta: { color: chalk.dim },
  rosterRow: { marginBottom: space.xs },

  center: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.sm,
  },
  centerBody: { textAlign: 'center' },
});
