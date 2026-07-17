import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Button, Card, PositionBadge } from '../components/chalkline';
import TierBadge from '../components/TierBadge';
import {
  getAnchorPool,
  saveAnchor,
  type AnchorKey,
  type AnchorSaveResponse,
} from '../api/rankings';
import { useSession } from '../state/useSession';
import { useRecoverOnResume } from '../hooks/useRecoverOnResume';
import { tierForElo, TIER_LABEL } from '../utils/tierBands';
import { chalk, ice, ink, position, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { Position, Tier } from '../shared/types';

// Pick Anchor wizard — one player at a time, answered in the fungible
// dynasty unit everyone already prices: draft picks. Each answer pins the
// player's value via POST /api/anchor/save (position-uniform by design —
// the pick ladder drives uniform valuation and tier assignment across
// position groups; the tier falls out of the pinned value server-side).
// Progress persists per format in AsyncStorage so the wizard resumes.

const ANCHOR_ROWS: { key: AnchorKey; label: string }[][] = [
  [
    { key: '4_firsts', label: '4 1sts' },
    { key: '3_firsts', label: '3 1sts' },
    { key: '2_firsts', label: '2 1sts' },
    { key: '1_first', label: '1 1st' },
  ],
  [
    { key: '1_second', label: '1 2nd' },
    { key: '1_third', label: '1 3rd' },
    { key: '1_fourth', label: '1 4th' },
    { key: 'no_value', label: 'No value' },
  ],
];

const POSITIONS: readonly string[] = ['QB', 'RB', 'WR', 'TE'];

// #133 — scope selector: anchor all positions (one value-descending queue,
// the original behavior) or a single position group. Session-only by
// design: the module-level mirror survives screen remounts within a
// launch but intentionally resets on the next app start.
type AnchorScope = Position | 'ALL';
const SCOPES: readonly AnchorScope[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];
let _sessionScope: AnchorScope = 'ALL';

// Active-segment underline per PositionTabs spec: position color, ice for ALL.
function scopeUnderline(s: AnchorScope): string {
  switch (s) {
    case 'QB': return position.qb;
    case 'RB': return position.rb;
    case 'WR': return position.wr;
    case 'TE': return position.te;
    default:   return ice.base;
  }
}

const doneKey = (fmt: string) => `ftf_anchor_done_v1_${fmt}`;

interface QueueRow {
  id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  elo: number;
}

export default function PickAnchorScreen() {
  const queryClient = useQueryClient();
  // Session format may be unset pre-init — the backend treats 1qb_ppr as
  // the default, so mirror that here for storage keys + band walks.
  const activeFormat = useSession((s) => s.activeFormat) ?? '1qb_ppr';

  // Snapshot the pool once (staleTime: Infinity) — anchoring re-sorts the
  // server-side rankings, and a mid-wizard refetch would shuffle the queue
  // under the user's thumbs. getAnchorPool sends X-Scoring-Format (#112)
  // so the queue is ordered by the same format's board the saves write to.
  const poolQuery = useQuery({
    queryKey: ['anchor-pool', activeFormat],
    queryFn: getAnchorPool,
    staleTime: Infinity,
  });

  // #121/#125 — the pool fetch can race app-resume session revalidation:
  // it fires with the orphaned pre-deploy token, 401s, and (staleTime:
  // Infinity + always-mounted stack screen) nothing ever refetches, so the
  // screen sticks on its error state. This refetches the errored query as
  // soon as revalidateSession mints a fresh token (or on plain foreground
  // resume for non-auth failures).
  useRecoverOnResume(poolQuery);

  // #133 — anchor scope (All positions | QB | RB | WR | TE).
  const [scope, setScopeState] = useState<AnchorScope>(_sessionScope);
  const setScope = (s: AnchorScope) => {
    _sessionScope = s;
    setScopeState(s);
  };

  // Pick-value scale (#111) UI removed per feedback #134 ("remove the top
  // tier asset question for now"). The backend plumbing stays intact —
  // GET/POST /api/anchor/scale + getAnchorScale/setAnchorScale in
  // api/rankings.ts — and any previously stored per-user scales keep
  // applying server-side; new users simply stay on the default (4 firsts,
  // the #117 consensus rung). Restore the pill row from git history if the
  // control comes back.

  // Answered/skipped ids for this format (resume support).
  const [done, setDone] = useState<Set<string> | null>(null);
  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(doneKey(activeFormat))
      .then((raw) => {
        if (!alive) return;
        try {
          setDone(new Set(raw ? (JSON.parse(raw) as string[]) : []));
        } catch {
          setDone(new Set());
        }
      })
      .catch(() => alive && setDone(new Set()));
    return () => {
      alive = false;
    };
  }, [activeFormat]);

  const persistDone = (next: Set<string>) => {
    setDone(next);
    AsyncStorage.setItem(doneKey(activeFormat), JSON.stringify([...next])).catch(
      () => {/* non-fatal — worst case the wizard re-asks after restart */},
    );
  };

  // Anchors change rankings/tiers everywhere — refresh consumers when the
  // user leaves the wizard (not per answer; the queue must stay stable).
  const savedAnythingRef = useRef(false);
  useEffect(() => {
    return () => {
      if (!savedAnythingRef.current) return;
      for (const key of ['rankings', 'progress', 'trio', 'tiers-status', 'trends']) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    };
  }, [queryClient]);

  // Real players only, best-first — generic picks ARE the ladder, so they
  // are never asked about.
  const queue: QueueRow[] = useMemo(() => {
    const rows = (poolQuery.data?.rankings ?? []) as QueueRow[];
    return rows
      .filter((r) => r.team !== 'PICK' && POSITIONS.includes(r.position))
      .sort((a, b) => b.elo - a.elo);
  }, [poolQuery.data]);

  // #133 — the wizard serves the scoped queue (still value-descending);
  // 'ALL' preserves the original single cross-position queue.
  const scopedQueue = useMemo(
    () => (scope === 'ALL' ? queue : queue.filter((r) => r.position === scope)),
    [queue, scope],
  );

  const remaining = useMemo(
    () => (done ? scopedQueue.filter((r) => !done.has(r.id)) : []),
    [scopedQueue, done],
  );
  const current = remaining[0] ?? null;
  const answered = scopedQueue.length - remaining.length;

  const [lastPlaced, setLastPlaced] = useState<{
    name: string;
    res: AnchorSaveResponse;
  } | null>(null);

  const mutation = useMutation({
    mutationFn: ({ playerId, anchor }: { playerId: string; anchor: AnchorKey }) =>
      saveAnchor(playerId, anchor),
    onSuccess: (res, vars) => {
      savedAnythingRef.current = true;
      if (current && current.id === vars.playerId) {
        setLastPlaced({ name: current.name, res });
      }
      if (done) persistDone(new Set(done).add(vars.playerId));
      haptics.selection();
    },
  });

  const onSkip = () => {
    if (!current || !done) return;
    persistDone(new Set(done).add(current.id));
  };

  const onStartOver = () => {
    setLastPlaced(null);
    if (!done) return;
    if (scope === 'ALL') {
      persistDone(new Set());
      return;
    }
    // Scoped start-over only re-opens the current position group — nuking
    // other positions' progress from an RB-only pass would be surprising.
    const scopedIds = new Set(scopedQueue.map((r) => r.id));
    persistDone(new Set([...done].filter((id) => !scopedIds.has(id))));
  };

  if (poolQuery.isLoading || done === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }

  if (poolQuery.isError || queue.length === 0) {
    // #128 — the old error state was a plain View ("pull back and retry")
    // with nothing to pull and nothing to tap. Real recovery affordances:
    // pull-to-refresh (a ScrollView so the gesture exists) + a Retry button.
    return (
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.centerContent}
        refreshControl={
          <RefreshControl
            refreshing={poolQuery.isFetching}
            onRefresh={() => poolQuery.refetch()}
            tintColor={ice.base}
          />
        }
      >
        <Text style={[type.body, styles.centerText]}>
          {poolQuery.isError
            ? "Couldn't load your players. Pull down to refresh, or tap Retry."
            : 'No players to anchor yet.'}
        </Text>
        {poolQuery.isError ? (
          <Button
            label="Retry"
            compact
            disabled={poolQuery.isFetching}
            onPress={() => poolQuery.refetch()}
            style={styles.retryBtn}
          />
        ) : null}
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* #133 — scope pills, PositionTabs construction (components.md):
          hairline segmented group, active = ink-3 fill + 2px underline in
          the position's color (ice for ALL — action, not a data encoding). */}
      <View style={styles.scopeRow}>
        {SCOPES.map((s) => {
          const active = s === scope;
          return (
            <Pressable
              key={s}
              testID={`anchors.scope-${s.toLowerCase()}`}
              accessibilityRole="button"
              accessibilityLabel={s === 'ALL' ? 'All positions' : `${s} only`}
              onPress={() => setScope(s)}
              style={({ pressed }) => [
                styles.scopeSegment,
                active && [
                  styles.scopeSegmentActive,
                  { borderBottomColor: scopeUnderline(s) },
                ],
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.scopeText, active && styles.scopeTextActive]}>
                {s}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.progress}>
        {answered} / {scopedQueue.length} anchored
        {scope !== 'ALL' ? ` · ${scope}` : ''}
        {' · '}{activeFormat === 'sf_tep' ? 'SF TEP' : '1QB PPR'}
      </Text>

      {current ? (
        <>
          <Card>
            <View style={styles.tile}>
              <Text style={[type.title, styles.name]}>{current.name}</Text>
              <View style={styles.metaRow}>
                <PositionBadge pos={current.position as Position} />
                <Text style={styles.meta}>
                  {current.team ?? 'FA'}
                  {current.age ? ` · ${current.age}` : ''}
                </Text>
                <TierBadge
                  tier={tierForElo(current.elo, current.position as Position, activeFormat) as Tier | null}
                  size="sm"
                />
              </View>
            </View>
          </Card>

          <Text style={styles.question}>Worth how much in draft capital?</Text>

          {ANCHOR_ROWS.map((row, i) => (
            <View key={i} style={styles.buttonRow}>
              {row.map(({ key, label }) => (
                <Button
                  key={key}
                  label={label}
                  compact
                  disabled={mutation.isPending}
                  onPress={() => mutation.mutate({ playerId: current.id, anchor: key })}
                  style={styles.anchorBtn}
                />
              ))}
            </View>
          ))}

          <Button
            label="Skip — not sure"
            variant="ghost"
            compact
            disabled={mutation.isPending}
            onPress={onSkip}
            style={styles.skipBtn}
          />
          {mutation.isError ? (
            <Text style={styles.error}>Save failed — check your connection and tap again.</Text>
          ) : null}
        </>
      ) : (
        <Card>
          <View style={styles.tile}>
            <Text style={[type.title, styles.name]}>All anchored</Text>
            <Text style={styles.meta}>
              {scope === 'ALL'
                ? 'Every player in your pool has a pick anchor. Your tiers and trade values now speak the same language: firsts.'
                : `Every ${scope} in your pool has a pick anchor. Switch positions above to keep going.`}
            </Text>
            <Button label="Start over" variant="ghost" compact onPress={onStartOver} />
          </View>
        </Card>
      )}

      {lastPlaced ? (
        <Text style={styles.consequence}>
          {lastPlaced.name} →{' '}
          {lastPlaced.res.tier
            ? TIER_LABEL[lastPlaced.res.tier as Tier] ?? lastPlaced.res.tier
            : 'No value'}
          {' · '}≈ {Math.round(lastPlaced.res.value).toLocaleString()}
        </Text>
      ) : (
        <Text style={styles.hint}>
          Anchors are pick-denominated on purpose: a 1st means the same thing
          on every team, so tiers mean the same thing for everyone.
        </Text>
      )}

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: ink.ink0 },
  content: { padding: space.lg, gap: space.md },
  center: {
    flex: 1,
    backgroundColor: ink.ink0,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.lg,
  },
  // #128 — error/empty state lives in a ScrollView (pull-to-refresh needs
  // the gesture surface); flexGrow keeps the content centered like before.
  centerContent: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.lg,
    gap: space.md,
  },
  centerText: { textAlign: 'center' },
  retryBtn: { alignSelf: 'center' },
  // #133 — PositionTabs spec: 1px hairline group at radii.sm; active
  // segment = ink3 fill + 2px underline (position color / ice for ALL).
  scopeRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  scopeSegment: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  scopeSegmentActive: { backgroundColor: ink.ink3 },
  scopeText: { ...type.label },
  scopeTextActive: { color: chalk.base },
  progress: { ...type.label, textAlign: 'center', color: chalk.dim },
  tile: { gap: space.sm },
  name: { textAlign: 'center' },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  meta: { ...type.bodySm, color: chalk.dim },
  question: { ...type.label, textAlign: 'center', marginTop: space.sm },
  buttonRow: { flexDirection: 'row', gap: space.sm },
  anchorBtn: { flex: 1 },
  skipBtn: { alignSelf: 'center', marginTop: space.xs },
  error: { ...type.bodySm, textAlign: 'center', color: chalk.dim },
  consequence: { ...type.data, textAlign: 'center', color: ice.base },
  hint: { ...type.bodySm, textAlign: 'center', color: chalk.dim },
});
