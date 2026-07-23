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
import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
  position as positionColors,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { Badge, Icon, TickLabel } from '../components/chalkline';
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

// League rankings ("power rankings", #142/#144/#169) — every team in the league
// as a stacked bar in a value-ranked chart, from GET /api/league/power-rankings.
//
// #169 redesign (mockups/outlook-odds/league-summary.html): the ranked list is
// now a vertical stacked bar chart. Each team is a bar segmented by position
// (QB/RB/WR/TE, position hexes) and the bars sort most→least total value.
//   - Position filter (single OR multi, "All" default): on change the bars
//     RE-VALUE to the selected position(s) only and RE-SORT teams by that
//     filtered value — a pure client-side transform over the per-position
//     values the payload already carries (positions[pos].value per team), no
//     refetch.
//   - Basis toggle: Consensus (universal-pool values) | My board (the caller's
//     own values, consensus fallback for unranked players). Redraft is a
//     disabled "(soon)" chip — the backend reserves basis=redraft but answers
//     501 not_available (FTF's value source is dynasty-only today), so the
//     client never requests it.
// Tapping a team's bar opens its roster grouped by position, sorted by value
// within each group (#144), itself position-filterable.
// Entered from the League tab's "League rankings" row (root-stack route
// 'LeagueSummary').
//
// #169 OUTLOOK ODDS layer (flag `outlook.odds`, DARK): the playoff/title-odds
// view lives between the basis toggle and the dynasty chart. It is a SEPARATE
// gated section — when `outlook.odds` is off (the default; the flag is absent
// from LAUNCHED_FLAG_DEFAULTS) the section does NOT render and GET
// /api/league/outlook is NOT called (it 404s while the modeling backend is
// dark). Only when on do we fetch + render. Every odds figure is a projection:
// the section carries a "Projected · preseason · beta" ribbon + a strength-
// source caption so no percentage ever reads as authoritative (see
// mockups/outlook-odds/outlook-card.html — the amber "Season outlook" block).
// The basis toggle governs BOTH the odds fetch and the dynasty chart.

type UiBasis = 'consensus' | 'personal';
type CorePos = 'QB' | 'RB' | 'WR' | 'TE';

const CORE_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const satisfies readonly CorePos[];

// Compact 0–10k value for chart bar labels + the per-group mini-summary.
function fmtK(v: number): string {
  if (v >= 1000) return `${(Math.round(v / 100) / 10).toFixed(1)}k`;
  return String(Math.round(v));
}

function posColor(pos: string): string {
  return positionColors[pos.toLowerCase() as keyof typeof positionColors] ?? chalk.dim;
}

// The value a team contributes under the active position filter. Empty filter
// ("All") = the team's authoritative total roster value (matches the backend
// rank). A non-empty filter = the summed value of just the selected positions.
function filteredTotal(team: PowerRankedTeam, filter: Set<CorePos>): number {
  if (filter.size === 0) return team.total_value;
  let sum = 0;
  filter.forEach((p) => {
    sum += team.positions?.[p]?.value ?? 0;
  });
  return sum;
}

export default function LeagueSummaryScreen() {
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const [basis, setBasis] = useState<UiBasis>('consensus');
  // Empty set = "All" (unfiltered). Non-empty = single/multi position select.
  const [posFilter, setPosFilter] = useState<Set<CorePos>>(new Set());
  // Store the selected team's id (not the object) so a basis switch while
  // the roster overlay is open re-derives the team from fresh data.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Drill-in overlay's own position filter (independent of the chart filter).
  const [drillPos, setDrillPos] = useState<Set<CorePos>>(new Set());

  const query = useQuery({
    queryKey: ['league-power-rankings', leagueId, basis],
    queryFn: () => getPowerRankings(leagueId!, basis),
    enabled: !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // #169 outlook odds — DARK behind `outlook.odds`. `enabled` is false unless
  // the flag is on AND a league is selected, so GET /api/league/outlook never
  // fires while the layer is dark (the endpoint 404s). Shares the `basis` state
  // with the dynasty chart. Off by default: the flag is absent from
  // LAUNCHED_FLAG_DEFAULTS, so `useFlag` returns false until a live map turns
  // it on.
  const oddsEnabled = useFlag('outlook.odds');
  const outlookQuery = useQuery({
    queryKey: ['league-outlook', leagueId, basis],
    queryFn: () => getOutlook(leagueId!, basis),
    enabled: oddsEnabled && !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const teams = query.data?.teams ?? [];
  const selected = selectedId
    ? teams.find((t) => t.user_id === selectedId) ?? null
    : null;

  // Client-side re-value + re-sort for the active position filter. Teams tie
  // -break on user_id asc so the order is deterministic (mirrors the backend).
  const ranked = useMemo(() => {
    const rows = teams.map((t) => ({ team: t, active: filteredTotal(t, posFilter) }));
    rows.sort((a, b) =>
      b.active - a.active || (a.team.user_id < b.team.user_id ? -1 : 1),
    );
    return rows;
  }, [teams, posFilter]);

  const maxActive = useMemo(
    () => Math.max(1, ...ranked.map((r) => r.active)),
    [ranked],
  );

  const togglePos = (setter: React.Dispatch<React.SetStateAction<Set<CorePos>>>) =>
    (pos: CorePos | 'ALL') => {
      setter((prev) => {
        if (pos === 'ALL') return new Set();
        const next = new Set(prev);
        if (next.has(pos)) next.delete(pos);
        else next.add(pos);
        return next;
      });
    };

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

        {/* #169 outlook-odds layer — gated on `outlook.odds` (dark). Rendered
            only when the flag is on; the fetch is likewise gated so nothing
            fires while dark. Basis-driven (shares the toggle above). */}
        {oddsEnabled ? <OddsSection query={outlookQuery} /> : null}

        {/* Position filter — single or multi select; "All" clears. Reorders +
            rescales the chart live over the already-returned per-position
            values (no refetch). */}
        <PosFilterPills
          idPrefix="league-summary.posfilter"
          filter={posFilter}
          onToggle={togglePos(setPosFilter)}
        />
        <Text style={[type.bodySm, styles.hint]}>
          {posFilter.size === 0
            ? basis === 'consensus'
              ? 'Ranked by total roster value on community consensus.'
              : 'Ranked by total roster value on YOUR board — unranked players use consensus.'
            : `Ranked by ${[...posFilter].join(' + ')} value only — chart reordered.`}
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
            <View style={styles.chart}>
              {ranked.map((r, idx) => (
                <BarRow
                  key={r.team.user_id}
                  team={r.team}
                  rank={idx + 1}
                  active={r.active}
                  maxActive={maxActive}
                  filter={posFilter}
                  onPress={() => {
                    setDrillPos(new Set());
                    setSelectedId(r.team.user_id);
                  }}
                />
              ))}
            </View>
            {/* Position legend — the stack encoding. */}
            <View style={styles.legend}>
              {CORE_POSITIONS.map((p) => (
                <View key={p} style={styles.legendItem}>
                  <View style={[styles.legendSwatch, { backgroundColor: posColor(p) }]} />
                  <Text style={styles.legendLabel}>{p}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </ScrollView>

      {/* #144/#169 — team drill-in: roster grouped by position, value-desc
          within each group, position-filterable. Overlay-card pattern shared
          with LeagueScreen's member roster (ink-2 card, solid scrim, X). */}
      <Modal
        visible={!!selected}
        transparent
        animationType="fade"
        onRequestClose={() => setSelectedId(null)}
      >
        <Pressable
          style={styles.overlayBackdrop}
          onPress={() => setSelectedId(null)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        {selected ? (
          <View style={styles.overlayCard}>
            <View style={styles.overlayHead}>
              <Text style={type.heading} numberOfLines={1} accessibilityRole="header">
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
            <PosFilterPills
              idPrefix="league-summary.roster-posfilter"
              filter={drillPos}
              onToggle={togglePos(setDrillPos)}
              style={styles.drillFilter}
            />
            <ScrollView style={styles.overlayList} contentContainerStyle={{ gap: space.xs }}>
              {groupRoster(selected, drillPos).map((g) => (
                <View key={g.pos}>
                  <View style={styles.groupHead}>
                    <Text style={[styles.groupLabel, { color: posColor(g.pos) }]}>
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
// A non-empty `filter` limits the sections to the selected core positions
// (the "Other" bucket only ever appears in the unfiltered "All" view).
function groupRoster(
  team: PowerRankedTeam,
  filter: Set<CorePos>,
): Array<{ pos: string; rows: PowerRankedPlayer[]; value: number }> {
  const buckets = new Map<string, PowerRankedPlayer[]>();
  for (const r of team.roster) {
    const key = (CORE_POSITIONS as readonly string[]).includes(r.position) ? r.position : 'Other';
    const arr = buckets.get(key);
    if (arr) arr.push(r);
    else buckets.set(key, [r]);
  }
  const order: string[] = filter.size > 0 ? [...filter] : [...CORE_POSITIONS, 'Other'];
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

// Shared position-filter pill row (chart + drill-in). "All" pill clears the
// set; each position pill is a color-dotted toggle. Multi-select.
function PosFilterPills({ idPrefix, filter, onToggle, style }: {
  idPrefix: string;
  filter: Set<CorePos>;
  onToggle: (pos: CorePos | 'ALL') => void;
  style?: any;
}) {
  const allOn = filter.size === 0;
  return (
    <View style={[styles.posFilter, style]}>
      <Pressable
        testID={`${idPrefix}.all`}
        onPress={() => onToggle('ALL')}
        accessibilityRole="button"
        accessibilityState={{ selected: allOn }}
        style={[styles.pill, allOn && styles.pillAllOn]}
      >
        <Text style={[styles.pillText, allOn && styles.pillTextAllOn]}>All</Text>
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
            style={[styles.pill, on && { borderColor: posColor(p), backgroundColor: ink.ink3 }]}
          >
            <View style={[styles.pillDot, { backgroundColor: posColor(p) }]} />
            <Text style={[styles.pillText, on && { color: posColor(p) }]}>{p}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// One team as a stacked bar: rank numeral, name + You badge, a position-stacked
// track scaled to the league max, and the active value + chevron on the right.
function BarRow({ team, rank, active, maxActive, filter, onPress }: {
  team: PowerRankedTeam;
  rank: number;
  active: number;
  maxActive: number;
  filter: Set<CorePos>;
  onPress: () => void;
}) {
  const shown: CorePos[] = filter.size > 0 ? [...filter] : [...CORE_POSITIONS];
  // Segment denominator = the same value the bar length encodes, so segments
  // always fill the track exactly (for "All" this is the sum of the four core
  // positions, which equals total roster value in the shared value space).
  const segSum = shown.reduce((s, p) => s + (team.positions?.[p]?.value ?? 0), 0);
  const fillPct = active > 0 ? Math.max((active / maxActive) * 100, 4) : 0;

  return (
    <Pressable
      testID={`league-summary.team.${team.user_id}`}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`View ${team.display_name || team.username} roster`}
      style={({ pressed }) => [styles.barRow, pressed && { backgroundColor: ink.ink1 }]}
    >
      <Text style={[styles.barRank, team.is_you && { color: ice.base }]}>{rank}</Text>
      <View style={styles.barMid}>
        <View style={styles.barNameRow}>
          <Text style={[type.title, styles.barName]} numberOfLines={1}>
            {team.display_name || team.username || team.user_id}
          </Text>
          {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
        </View>
        <View style={styles.track}>
          {fillPct > 0 ? (
            <View style={[styles.fill, { width: `${fillPct}%` }]}>
              {segSum > 0
                ? shown.map((p) => {
                    const v = team.positions?.[p]?.value ?? 0;
                    if (v <= 0) return null;
                    return (
                      <View
                        key={p}
                        style={{ width: `${(v / segSum) * 100}%`, backgroundColor: posColor(p) }}
                      />
                    );
                  })
                : null}
            </View>
          ) : null}
        </View>
      </View>
      <View style={styles.barRight}>
        <Text style={type.data}>{active > 0 ? Math.round(active).toLocaleString('en-US') : '—'}</Text>
        <Icon name="chevron-right" size={14} color={chalk.dim} />
      </View>
    </Pressable>
  );
}

// ── #169 outlook odds ────────────────────────────────────────────────────
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

// The load-bearing honesty label. `meta.beta`/`meta.is_preseason` are true
// today (July, zero games), so this reads "Projected · preseason · beta" —
// never a bare authoritative percentage.
function betaRibbonLabel(meta: OutlookMeta): string {
  const parts = ['Projected'];
  if (meta.is_preseason) parts.push('preseason');
  if (meta.beta) parts.push('beta');
  return parts.join(' · ');
}

// 0..1 fraction → whole-percent string. Preseason values are 0.0 → "0%".
function pct(frac: number): string {
  return `${Math.round((frac ?? 0) * 100)}%`;
}

function record(t: OutlookTeam): string {
  const base = `${t.wins}-${t.losses}`;
  return t.ties > 0 ? `${base}-${t.ties}` : base;
}

// The playoff/title-odds section. Rendered only when `outlook.odds` is on;
// degrades quietly (renders nothing) while the endpoint is dark/404s so the
// screen never shows a broken projection block.
function OddsSection({ query }: { query: UseQueryResult<LeagueOutlookResponse> }) {
  const data = query.data;

  if (query.isLoading && !data) {
    return (
      <View style={styles.oddsSection} testID="league-summary.odds.section">
        <TickLabel color={semantic.warn}>Playoff picture</TickLabel>
        <View style={styles.oddsLoading}>
          <ActivityIndicator color={semantic.warn} />
        </View>
      </View>
    );
  }

  // No data (dark endpoint / error / empty league) → render nothing. Better a
  // missing section than a fabricated or broken one.
  if (!data || data.teams.length === 0) return null;

  const { meta, teams } = data;

  return (
    <View style={styles.oddsSection} testID="league-summary.odds.section">
      <View style={styles.oddsHead}>
        <TickLabel color={semantic.warn}>Playoff picture</TickLabel>
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
        {`${sourceCaption(meta.strength_source)} · ${meta.sims.toLocaleString('en-US')} sims · top ${meta.playoff_slots} make the playoffs`}
      </Text>

      <View style={styles.oddsList}>
        {teams.map((t, idx) => (
          <OddsRow key={t.roster_id} team={t} rank={idx + 1} />
        ))}
      </View>
    </View>
  );
}

// One team's projected odds: order numeral (payload is pre-sorted by
// playoff_pct desc), name + You badge, record + projected seed, then the two
// headline odds (playoff / title) as figure + thin warn meter.
function OddsRow({ team, rank }: { team: OutlookTeam; rank: number }) {
  return (
    <View
      style={styles.oddsRow}
      testID={`league-summary.odds.row.${team.roster_id}`}
    >
      <Text style={[styles.oddsRank, team.is_you && { color: ice.base }]}>{rank}</Text>
      <View style={styles.oddsMid}>
        <View style={styles.oddsNameRow}>
          <Text style={[type.title, styles.oddsName]} numberOfLines={1}>
            {team.display_name || team.username || String(team.roster_id)}
          </Text>
          {team.is_you ? <Badge label="You" color={ice.base} colorText /> : null}
        </View>
        <Text style={[type.data, styles.oddsSub]}>
          {`${record(team)} · proj seed ${team.odds.projected_seed.toFixed(1)}`}
        </Text>
        <View style={styles.oddsStats}>
          <OddStat label="Playoff" frac={team.odds.playoff_pct} />
          <OddStat label="Title" frac={team.odds.title_pct} />
        </View>
      </View>
    </View>
  );
}

// A single projected-odds figure with a thin warn meter. Warn (amber) is the
// "this is projected, not settled" signal — matches the mockup's amber block.
function OddStat({ label, frac }: { label: string; frac: number }) {
  const fillPct = Math.max(0, Math.min(1, frac ?? 0)) * 100;
  return (
    <View style={styles.oddStat}>
      <Text style={styles.oddStatLabel}>{label}</Text>
      <Text style={[type.data, styles.oddStatValue]}>{pct(frac)}</Text>
      <View style={styles.oddStatTrack}>
        {fillPct > 0 ? (
          <View style={[styles.oddStatFill, { width: `${fillPct}%` }]} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl },

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

  posFilter: { flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: ink.line,
  },
  pillAllOn: { borderColor: ice.base, backgroundColor: ink.ink3 },
  pillDot: { width: 7, height: 7, borderRadius: radii.pill },
  pillText: { ...type.label, letterSpacing: 0.5, color: chalk.dim },
  pillTextAllOn: { color: ice.base },

  hint: { marginTop: space.sm, marginBottom: space.md },

  // #169 outlook odds section — sits between the basis toggle and the chart,
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

  oddsList: { marginTop: space.md, gap: 2 },
  oddsRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  oddsRank: {
    ...type.data,
    width: 22,
    textAlign: 'center',
    color: chalk.dim,
    marginTop: 2,
  },
  oddsMid: { flex: 1, gap: 5 },
  oddsNameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  oddsName: { flexShrink: 1 },
  oddsSub: { color: chalk.dim },
  oddsStats: { flexDirection: 'row', gap: space.md, marginTop: 2 },
  oddStat: { flex: 1, gap: 4 },
  oddStatLabel: { ...type.label, color: chalk.faint },
  oddStatValue: { color: chalk.base },
  oddStatTrack: {
    height: 5,
    backgroundColor: ink.ink3,
    borderRadius: 3,
    overflow: 'hidden',
  },
  oddStatFill: { height: '100%', backgroundColor: semantic.warn, borderRadius: 3 },

  chart: { gap: 2 },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  barRank: {
    ...type.data,
    width: 22,
    textAlign: 'center',
    color: chalk.dim,
  },
  barMid: { flex: 1, gap: 5 },
  barNameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  barName: { flexShrink: 1 },
  track: {
    height: 16,
    backgroundColor: ink.ink2,
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: { flexDirection: 'row', height: '100%' },
  barRight: { flexDirection: 'row', alignItems: 'center', gap: space.xs },

  legend: { flexDirection: 'row', gap: space.lg, flexWrap: 'wrap', marginTop: space.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendSwatch: { width: 9, height: 9, borderRadius: radii.xs },
  legendLabel: { ...type.bodySm, color: chalk.dim },

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
  drillFilter: { marginTop: space.xs },
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
