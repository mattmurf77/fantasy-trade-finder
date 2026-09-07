import React, { useCallback, useMemo, useState } from 'react';
import { View, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigation, useRoute } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { Button, Card, TickLabel } from '../components/chalkline';
import Toast from '../components/Toast';
import { haptics } from '../utils/haptics';
import { ink, chalk, ice, flare, semantic, space, radii, type } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';
import { ApiError } from '../api/client';
import {
  getOverhaul,
  refreshOverhaul,
  assertAttemptStatus,
  ATTEMPT_STATE_LABEL,
  LIVE_ATTEMPT_STATES,
  type OverhaulView,
  type Offer,
  type Package,
  type AttemptView,
  type AttemptState,
  type PackageStatus,
} from '../api/overhaul';

// Team overhaul — step 8, the saved roadmap (BUILD-CONTRACT §7 refresh /
// attempts status, PRODUCT-SPEC R9). This is the resume surface: per-package
// status, every attempt with its honest state, and the MANUAL next step.
//
// Nothing here sends. "Send next tier" hands that tier's offer ids to the
// summary, which re-prepares and re-validates them (R9.4). A decline never
// triggers a new offer (invariant 9). Refresh reconciles from ownership
// changes only (D8) and is rate-limited server-side (429 → toast).
//
// State labels come from ATTEMPT_STATE_LABEL in api/overhaul.ts — the plan
// screen must render every AttemptState and check-team-overhaul.js pins
// that the map and the union stay in step.
//
// Tab-stack screen: NO FeedbackFAB.

const OUTLOOK_LABEL = { push_all_in: 'Push all in', blow_it_up: 'Blow it up' } as const;

const STATUS_LABEL: Record<PackageStatus, string> = {
  open: 'Ready',
  pending: 'Awaiting responses',
  complete: 'Done',
  blocked: 'Blocked',
};

const STATUS_COLOR: Record<PackageStatus, string> = {
  open: chalk.dim,
  pending: semantic.warn,
  complete: semantic.pos,
  blocked: semantic.neg,
};

function stateColor(s: AttemptState): string {
  switch (s) {
    case 'accepted': return semantic.pos;
    case 'queued': case 'sending': case 'proposed': case 'outcome_unknown': return semantic.warn;
    case 'send_failed': case 'declined': case 'stale': return semantic.neg;
    default: return chalk.dim;
  }
}

function sourceHint(a: AttemptView): string | null {
  if (a.state_source === 'user_reported') return 'you reported';
  if (a.state_source === 'ownership_refresh') return 'from a roster change';
  return null;
}

function assetName(view: OverhaulView, id: string): string {
  const a = view.eligible_assets.find((x) => x.id === id);
  if (!a) return id;
  return a.kind === 'pick' ? a.label || a.name : a.name;
}

function receiveLine(offer: Offer | undefined): string {
  return offer?.card.receive_players.map((p) => p.name).join(' + ') || '—';
}

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function errorCode(e: unknown): string | null {
  if (e instanceof ApiError && typeof e.body === 'object' && e.body) {
    return (e.body as { error?: string }).error ?? null;
  }
  return null;
}

/** The lowest tier none of whose offers has ever been attempted. */
function nextTier(pkg: Package, attempts: AttemptView[]): { tier: number; offer_ids: string[] } | null {
  const tried = new Set(attempts.map((a) => a.offer_id));
  const sorted = [...pkg.tiers].sort((a, b) => a.tier - b.tier);
  const t = sorted.find((x) => x.offer_ids.length > 0 && x.offer_ids.every((id) => !tried.has(id)));
  return t ? { tier: t.tier, offer_ids: t.offer_ids } : null;
}

export default function OverhaulPlanScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { overhaulId } = route.params ?? {};
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['overhaul', overhaulId],
    queryFn: ({ signal }) => getOverhaul(overhaulId, signal),
    enabled: !!overhaulId,
  });
  const view = query.data;
  const roadmap = useMemo(
    () => view?.roadmaps.find((r) => r.roadmap_id === view.selected_roadmap_id) ?? null,
    [view],
  );

  const [toast, setToast] = useState<{ msg: string; tone: 'warn' | 'error' | 'success' } | null>(null);

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
    if (leagueId) void queryClient.invalidateQueries({ queryKey: ['overhaul', leagueId] });
  }, [queryClient, overhaulId, leagueId]);

  const refreshMutation = useMutation({
    mutationFn: () => refreshOverhaul(overhaulId),
    onSuccess: () => { invalidate(); setToast({ msg: 'Checked the league for replies', tone: 'success' }); },
    onError: (e) => {
      haptics.warning();
      setToast({
        msg: e instanceof ApiError && e.status === 429
          ? 'Just checked — try again in a moment'
          : 'Couldn’t check the league right now',
        tone: 'warn',
      });
    },
  });

  const assertMutation = useMutation({
    mutationFn: ({ attemptId, state }: { attemptId: string; state: 'declined' | 'withdrawn' }) =>
      assertAttemptStatus(overhaulId, attemptId, { state }),
    onSuccess: invalidate,
    onError: () => { haptics.warning(); setToast({ msg: 'Couldn’t record that — try again', tone: 'error' }); },
  });

  const onSendNext = useCallback(
    (pkg: Package, tier: { tier: number; offer_ids: string[] }) => {
      if (!roadmap) return;
      track('overhaul_fallback_requested', {
        overhaul_id: overhaulId,
        package_id: pkg.package_id,
        tier: tier.tier,
        offer_count: tier.offer_ids.length,
      });
      navigation.navigate('OverhaulSummary', {
        overhaulId,
        roadmapId: roadmap.roadmap_id,
        offerIds: tier.offer_ids,
      });
    },
    [roadmap, overhaulId, navigation],
  );

  if (query.isLoading || !view) {
    return (
      <View style={styles.center}>
        {query.isError ? (
          <Button label="Try again" variant="secondary" onPress={() => query.refetch()} />
        ) : (
          <ActivityIndicator color={chalk.dim} />
        )}
      </View>
    );
  }

  const liveAttempts = view.attempts.filter((a) => LIVE_ATTEMPT_STATES.has(a.state));
  const recovery = view.recovery;
  const completeCount = roadmap?.packages.filter((p) => p.status === 'complete').length ?? 0;

  const onStartNew = () => {
    if (liveAttempts.length) {
      setToast({
        msg: `${liveAttempts.length} offer${liveAttempts.length === 1 ? ' is' : 's are'} still live — mark them declined or withdrawn before starting over`,
        tone: 'warn',
      });
      return;
    }
    navigation.navigate('OverhaulOutlook', {});
  };

  return (
    <View style={styles.wrap}>
      <ScrollView contentContainerStyle={styles.body}>
        <ChalkText variant="display">Your roadmap, in progress</ChalkText>
        <View style={styles.rowBetween}>
          <View style={styles.flex}>
            <ChalkText variant="title">
              {`${view.settings.outlook ? OUTLOOK_LABEL[view.settings.outlook] : 'Overhaul'} · ${view.status}`}
            </ChalkText>
            <ChalkText variant="bodySm" style={styles.dim}>{`Last checked ${fmtWhen(view.snapshot.captured_at)}`}</ChalkText>
          </View>
          <Button
            label="Refresh"
            variant="secondary"
            compact
            icon="reload"
            loading={refreshMutation.isPending}
            onPress={() => refreshMutation.mutate()}
            testID="overhaul.plan.refresh"
          />
        </View>

        {roadmap ? (
          <Card>
            <View style={styles.rowBetween}>
              <TickLabel>Progress</TickLabel>
              <ChalkText variant="data">{`${completeCount} / ${roadmap.packages.length} complete`}</ChalkText>
            </View>
            <View style={styles.progress}>
              {roadmap.packages.map((p) => (
                <View key={p.package_id} style={[styles.tick, p.status === 'complete' && styles.tickOn]} />
              ))}
            </View>
            <ChalkText variant="bodySm" style={styles.dim}>
              {liveAttempts.length
                ? `${liveAttempts.length} offer${liveAttempts.length === 1 ? '' : 's'} awaiting a reply. Refresh reads the league; nothing is sent on its own.`
                : 'No offers are out right now.'}
            </ChalkText>
          </Card>
        ) : (
          <Card rail={semantic.warn}>
            <ChalkText variant="body">No roadmap chosen yet.</ChalkText>
            <Button label="Choose a roadmap" variant="secondary" compact style={styles.mt}
              onPress={() => navigation.navigate('OverhaulRoadmaps', { overhaulId })} />
          </Card>
        )}

        {recovery.applicable && !recovery.resolved ? (
          <Card rail={flare.base} padding={space.md}>
            <ChalkText style={[type.label, styles.flare]}>PRIORITY 1: RECOVER YOUR FIRST</ChalkText>
            <ChalkText variant="bodySm">
              {`Your own ${recovery.season ?? ''} 1st is still out there${recovery.holder_username ? ` with ${recovery.holder_username}` : ''}.`}
            </ChalkText>
          </Card>
        ) : null}

        {roadmap?.packages.map((pkg, i) => {
          const attempts = view.attempts
            .filter((a) => a.package_id === pkg.package_id)
            .sort((a, b) => (a.tier - b.tier) || a.created_at.localeCompare(b.created_at));
          const live = attempts.filter((a) => LIVE_ATTEMPT_STATES.has(a.state));
          const next = pkg.status === 'complete' ? null : nextTier(pkg, attempts);
          const stale = pkg.tiers.flatMap((t) => t.offer_ids).filter((id) => roadmap.offers[id]?.availability === 'stale');
          return (
            <Card key={pkg.package_id}>
              <View style={styles.rowBetween}>
                <TickLabel>{`Package ${i + 1}`}</TickLabel>
                <Pill label={STATUS_LABEL[pkg.status]} color={STATUS_COLOR[pkg.status]} />
              </View>
              <ChalkText variant="title">{pkg.give_ids.map((id) => assetName(view, id)).join(' + ')}</ChalkText>
              {pkg.reason === 'recover_own_first' ? (
                <ChalkText style={[type.label, styles.flare]}>PRIORITY 1 · RECOVER YOUR FIRST</ChalkText>
              ) : null}

              {attempts.map((a) => {
                const offer = roadmap.offers[a.offer_id];
                const hint = sourceHint(a);
                const isLive = a.state === 'proposed' || a.state === 'outcome_unknown';
                return (
                  <View key={a.attempt_id} style={styles.attempt}>
                    <View style={styles.rowBetween}>
                      <View style={styles.flex}>
                        <ChalkText variant="body">{offer?.counterparty_username ?? a.offer_id}</ChalkText>
                        <ChalkText variant="bodySm" style={styles.dim}>{`${receiveLine(offer)} · Priority ${a.tier}`}</ChalkText>
                      </View>
                      <Pill label={ATTEMPT_STATE_LABEL[a.state]} color={stateColor(a.state)} />
                    </View>
                    {hint ? <ChalkText variant="bodySm" style={styles.faint}>{hint}</ChalkText> : null}
                    {a.state === 'send_failed' && a.error?.message ? (
                      <ChalkText variant="bodySm" style={styles.neg}>{a.error.message}</ChalkText>
                    ) : null}
                    {a.state === 'stale' ? (
                      <ChalkText variant="bodySm" style={styles.warn}>Needs refresh — an asset in this offer moved.</ChalkText>
                    ) : null}
                    {isLive ? (
                      <View style={styles.btnRow}>
                        <Button label="Mark declined" variant="secondary" compact style={styles.flex}
                          disabled={assertMutation.isPending}
                          onPress={() => assertMutation.mutate({ attemptId: a.attempt_id, state: 'declined' })} />
                        <Button label="Mark withdrawn" variant="ghost" compact style={styles.flex}
                          disabled={assertMutation.isPending}
                          onPress={() => assertMutation.mutate({ attemptId: a.attempt_id, state: 'withdrawn' })} />
                      </View>
                    ) : null}
                  </View>
                );
              })}

              {pkg.status === 'complete' ? (
                <ChalkText variant="bodySm" style={styles.pos}>
                  Done — these assets are committed; the other alternatives here can’t be sent.
                </ChalkText>
              ) : live.length ? (
                <ChalkText variant="bodySm" style={styles.dim}>
                  {`${live.length} offer${live.length === 1 ? '' : 's'} out. Later tiers wait until you record a reply.`}
                </ChalkText>
              ) : next ? (
                <View style={styles.next}>
                  <ChalkText variant="bodySm" style={styles.dim}>
                    {`Next: Priority ${next.tier} · ${next.offer_ids.map((id) => roadmap.offers[id]?.counterparty_username ?? id).join(', ')}`}
                  </ChalkText>
                  <Button
                    label={`Send next tier${next.offer_ids.length > 1 ? ` (${next.offer_ids.length} offers)` : ''}`}
                    variant="secondary"
                    compact
                    onPress={() => onSendNext(pkg, next)}
                    testID="overhaul.plan.send-next"
                  />
                </View>
              ) : pkg.status === 'blocked' ? (
                <ChalkText variant="bodySm" style={styles.neg}>Blocked — refresh to see what changed.</ChalkText>
              ) : (
                <ChalkText variant="bodySm" style={styles.dim}>No tiers left to try for this package.</ChalkText>
              )}
              {stale.length && pkg.status !== 'complete' ? (
                <ChalkText variant="bodySm" style={styles.warn}>
                  {`${stale.length} alternative${stale.length === 1 ? '' : 's'} need a refresh before they can be sent.`}
                </ChalkText>
              ) : null}
            </Card>
          );
        })}

        <Button label="Start a new overhaul" variant="secondary" onPress={onStartNew} />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
    </View>
  );
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.pill, { borderColor: color }]}>
      <ChalkText scale="dense" style={[type.label, { color }]}>{label.toUpperCase()}</ChalkText>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: ink.ink0 },
  center: {
    flex: 1, backgroundColor: ink.ink0, alignItems: 'center', justifyContent: 'center',
    padding: space.xl, gap: space.md,
  },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  flex: { flex: 1 },
  mt: { marginTop: space.sm },
  dim: { color: chalk.dim },
  faint: { color: chalk.faint },
  warn: { color: semantic.warn },
  neg: { color: semantic.neg },
  pos: { color: semantic.pos },
  flare: { color: flare.base },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm },
  progress: { flexDirection: 'row', gap: 3, marginVertical: space.sm },
  tick: { flex: 1, height: 2, backgroundColor: ink.ink3, borderRadius: radii.xs },
  tickOn: { backgroundColor: ice.base },
  pill: {
    borderWidth: 1, borderRadius: radii.xs, paddingHorizontal: space.sm, paddingVertical: 2,
  },
  attempt: { borderTopWidth: 1, borderTopColor: ink.line, paddingTop: space.md, marginTop: space.md, gap: space.xs },
  next: { marginTop: space.md, gap: space.sm },
  btnRow: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
});
