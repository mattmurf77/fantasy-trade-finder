import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
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
  getRankings,
  saveAnchor,
  type AnchorKey,
  type AnchorSaveResponse,
} from '../api/rankings';
import { useSession } from '../state/useSession';
import { tierForElo, TIER_LABEL } from '../utils/tierBands';
import { chalk, ice, ink, space, type } from '../theme/chalkline';
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
  // under the user's thumbs.
  const poolQuery = useQuery({
    queryKey: ['anchor-pool', activeFormat],
    queryFn: () => getRankings(null),
    staleTime: Infinity,
  });

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

  const remaining = useMemo(
    () => (done ? queue.filter((r) => !done.has(r.id)) : []),
    [queue, done],
  );
  const current = remaining[0] ?? null;
  const answered = queue.length - remaining.length;

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
    persistDone(new Set());
  };

  if (poolQuery.isLoading || done === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }

  if (poolQuery.isError || queue.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={type.body}>
          {poolQuery.isError
            ? 'Could not load your player pool. Pull back and retry.'
            : 'No players to anchor yet.'}
        </Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.progress}>
        {answered} / {queue.length} anchored · {activeFormat === 'sf_tep' ? 'SF TEP' : '1QB PPR'}
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
              Every player in your pool has a pick anchor. Your tiers and trade
              values now speak the same language: firsts.
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
