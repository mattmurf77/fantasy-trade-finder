import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigation, useRoute } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { Button, Card, TickLabel } from '../components/chalkline';
import Toast from '../components/Toast';
import { ink, chalk, flare, semantic, space, radii, type } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';
import { ApiError } from '../api/client';
import {
  getOverhaul,
  selectRoadmap,
  savePriorities,
  type OverhaulView,
  type RoadmapView,
  type Package,
  type Offer,
  type PriorityTier,
  type ShortfallReason,
} from '../api/overhaul';
import { SHORTFALL_COPY } from './OverhaulTargetsScreen';

// Team overhaul — step 5, roadmap comparison (BUILD-CONTRACT §9, PRODUCT-SPEC
// R6). Up to five ranked roadmaps; each is 4–5 packages with distinct
// outgoing asset sets. "Set priorities" selects one and starts the per-package
// tier pass. Tab-stack screen: NO FeedbackFAB (covered by RootNav's mount).
// Shortfall copy is the one client table exported by OverhaulTargetsScreen.
//
// Swap (R6.6): tapping a package row inside the expanded roadmap lists that
// package's liked alternatives. Alternatives share the package's outgoing
// assets by construction (R6.7), so "Make this the first offer" only reorders
// tier 1 — it is a priorities write, never a regroup.


const RECOVERY_RIBBON = 'Priority 1: Recover your first';

function nameOf(view: OverhaulView, id: string): string {
  const a = (view.eligible_assets ?? []).find((x) => x.id === id);
  if (!a) return id;
  return a.kind === 'pick' ? a.label || a.name : a.name;
}

// Server data is guarded (`?? []`, `?.`) everywhere it is read in render: a
// malformed card or package must degrade to '—', never throw mid-render.
function receiveNames(offer: Offer | undefined): string {
  if (!offer) return '—';
  return (offer.card?.receive_players ?? []).map((p) => p?.name).filter(Boolean).join(' + ') || '—';
}

function tier1Offer(pkg: Package, rm: RoadmapView): Offer | undefined {
  const tiers = pkg.tiers ?? [];
  const first = tiers.find((t) => t.tier === 1) ?? tiers[0];
  const id = first?.offer_ids?.[0];
  return id ? rm.offers?.[id] : undefined;
}

/** Move `chosen` into a tier of its own at rank 1; every other tier shifts
 *  down. Never merges two offers into one tier, so the D4 rule holds. */
function promoteToTier1(tiers: PriorityTier[], chosen: string): PriorityTier[] {
  const rest = (tiers ?? [])
    .map((t) => (t.offer_ids ?? []).filter((id) => id !== chosen))
    .filter((ids) => ids.length > 0);
  return [[chosen], ...rest].map((offer_ids, i) => ({ tier: i + 1, offer_ids }));
}

export default function OverhaulRoadmapsScreen() {
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

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [swapPackageId, setSwapPackageId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; tone: 'warn' | 'error' | 'success' } | null>(null);

  useEffect(() => {
    if (view && expandedId == null && view.roadmaps?.length) {
      setExpandedId(view.selected_roadmap_id ?? view.roadmaps[0].roadmap_id);
    }
  }, [view, expandedId]);

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
    if (leagueId) void queryClient.invalidateQueries({ queryKey: ['overhaul', leagueId] });
  }, [queryClient, overhaulId, leagueId]);

  const selectMutation = useMutation({
    mutationFn: (rm: RoadmapView) => selectRoadmap(overhaulId, rm.roadmap_id, { version: rm.version }),
    onSuccess: (_data, rm) => {
      invalidate();
      track('overhaul_roadmap_selected', {
        overhaul_id: overhaulId,
        roadmap_id: rm.roadmap_id,
        package_count: (rm.packages ?? []).length,
      });
      navigation.navigate('OverhaulPriorities', {
        overhaulId,
        roadmapId: rm.roadmap_id,
        packageIndex: 0,
      });
    },
    onError: (e) => setToast({ msg: errorLine(e, 'Couldn’t select that roadmap'), tone: 'error' }),
  });

  const swapMutation = useMutation({
    mutationFn: ({ rm, pkg, offerId }: { rm: RoadmapView; pkg: Package; offerId: string }) =>
      savePriorities(overhaulId, rm.roadmap_id, {
        version: rm.version,
        package_id: pkg.package_id,
        tiers: promoteToTier1(pkg.tiers, offerId),
      }),
    onSuccess: () => {
      invalidate();
      setSwapPackageId(null);
      setToast({ msg: 'First offer updated', tone: 'success' });
    },
    onError: (e) => setToast({ msg: errorLine(e, 'Couldn’t swap that offer'), tone: 'error' }),
  });

  const roadmaps = useMemo(
    () => (view ? [...(view.roadmaps ?? [])].sort((a, b) => a.rank - b.rank) : []),
    [view],
  );

  if (query.isLoading || !view) {
    return (
      <View style={styles.center}>
        {query.isError ? (
          <>
            <ChalkText variant="body" style={styles.dim}>Couldn’t load this overhaul.</ChalkText>
            <Button label="Try again" variant="secondary" onPress={() => query.refetch()} />
          </>
        ) : (
          <ActivityIndicator color={chalk.dim} />
        )}
      </View>
    );
  }

  const recovery = view.recovery;
  const showRecovery = !!recovery && recovery.applicable && !recovery.resolved;

  return (
    <View style={styles.wrap}>
      <ScrollView contentContainerStyle={styles.body}>
        <ChalkText variant="display">Your overhaul roadmaps</ChalkText>
        <ChalkText variant="body" style={styles.dim}>
          Each roadmap is a set of packages. Every package sends its own assets, so one offer from
          each can be accepted without reusing anything.
        </ChalkText>

        {showRecovery ? (
          <Card rail={flare.base}>
            <ChalkText style={[type.label, styles.flare, styles.mb]}>{RECOVERY_RIBBON.toUpperCase()}</ChalkText>
            <ChalkText variant="body">
              {recoveryLine(recovery.season, recovery.holder_username, recovery.state)}
            </ChalkText>
          </Card>
        ) : null}

        {roadmaps.length === 0 ? (
          <Shortfall
            reason={view.generation?.shortfall_reason ?? null}
            onMoreIdeas={() => navigation.navigate('OverhaulReview', { overhaulId })}
            onChangePool={() => navigation.navigate('OverhaulAssets', { overhaulId })}
          />
        ) : (
          roadmaps.map((rm, i) => {
            const expanded = rm.roadmap_id === expandedId;
            return (
              <Pressable
                key={rm.roadmap_id}
                testID={`overhaul.roadmap.${rm.roadmap_id}`}
                accessibilityRole="button"
                accessibilityState={{ expanded }}
                onPress={() => {
                  setExpandedId(expanded ? null : rm.roadmap_id);
                  setSwapPackageId(null);
                }}
              >
                <Card selected={expanded}>
                  <View style={styles.stack}>
                  <View style={styles.rowBetween}>
                    <TickLabel>{`Roadmap ${i + 1}`}</TickLabel>
                    <ChalkText variant="data" style={styles.dim}>
                      {`${(rm.packages ?? []).length} packages`}
                    </ChalkText>
                  </View>

                  {(rm.packages ?? []).map((pkg, pi) => {
                    const first = tier1Offer(pkg, rm);
                    const isRecovery = pkg.reason === 'recover_own_first';
                    const alternatives = (pkg.tiers ?? []).flatMap((t) => t.offer_ids ?? []);
                    const swapping = expanded && swapPackageId === pkg.package_id;
                    return (
                      <View key={pkg.package_id} style={styles.pkg}>
                        <Pressable
                          disabled={!expanded}
                          onPress={() => setSwapPackageId(swapping ? null : pkg.package_id)}
                          accessibilityRole="button"
                          accessibilityLabel={`Package ${pi + 1}, ${alternatives.length} liked alternatives`}
                        >
                          {isRecovery ? (
                            <ChalkText style={[type.label, styles.flare]}>
                              {RECOVERY_RIBBON.toUpperCase()}
                            </ChalkText>
                          ) : null}
                          <ChalkText variant="title">
                            {(pkg.give_ids ?? []).map((id) => nameOf(view, id)).join(' + ')}
                          </ChalkText>
                          <ChalkText variant="bodySm" style={styles.dim}>
                            {first
                              ? `To ${first.counterparty_username} · receive ${receiveNames(first)}`
                              : 'No offer in tier 1'}
                          </ChalkText>
                          {expanded ? (
                            <ChalkText variant="bodySm" style={styles.dim}>
                              {`${alternatives.length} liked alternative${alternatives.length === 1 ? '' : 's'} · tap to swap`}
                            </ChalkText>
                          ) : null}
                        </Pressable>

                        {swapping ? (
                          <View style={styles.swap}>
                            <ChalkText variant="bodySm" style={styles.dim}>
                              Alternatives send the same assets as this package. Choosing one makes it
                              the first offer sent.
                            </ChalkText>
                            {alternatives.map((offerId) => {
                              const offer = rm.offers?.[offerId];
                              const isFirst = first?.offer_id === offerId;
                              return (
                                <View key={offerId} style={styles.altRow}>
                                  <View style={styles.flex}>
                                    <ChalkText variant="body">
                                      {offer?.counterparty_username ?? offerId}
                                    </ChalkText>
                                    <ChalkText variant="bodySm" style={styles.dim}>
                                      {`Get ${receiveNames(offer)}`}
                                    </ChalkText>
                                  </View>
                                  {isFirst ? (
                                    <ChalkText variant="label" style={styles.dim}>FIRST</ChalkText>
                                  ) : (
                                    <Button
                                      label="Make first"
                                      variant="ghost"
                                      compact
                                      loading={swapMutation.isPending}
                                      onPress={() => swapMutation.mutate({ rm, pkg, offerId })}
                                    />
                                  )}
                                </View>
                              );
                            })}
                          </View>
                        ) : null}
                      </View>
                    );
                  })}

                  {expanded ? (
                    <>
                      <ChalkText variant="bodySm" style={styles.dim}>
                        {(rm.summary?.unused_eligible_ids ?? []).length
                          ? `Not moving: ${(rm.summary?.unused_eligible_ids ?? []).map((id) => nameOf(view, id)).join(', ')}`
                          : 'Every asset in your pool is in play.'}
                      </ChalkText>
                      {(rm.compat?.warnings ?? []).length ? (
                        <ChalkText variant="bodySm" style={styles.warn}>
                          {`${rm.compat.warnings.length} warning${rm.compat.warnings.length === 1 ? '' : 's'} to review before sending`}
                        </ChalkText>
                      ) : null}
                      <Button
                        label="Set priorities"
                        onPress={() => selectMutation.mutate(rm)}
                        loading={selectMutation.isPending}
                        disabled={swapMutation.isPending}
                      />
                    </>
                  ) : null}
                  </View>
                </Card>
              </Pressable>
            );
          })
        )}
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

function Shortfall({
  reason,
  onMoreIdeas,
  onChangePool,
}: {
  reason: ShortfallReason | null;
  onMoreIdeas: () => void;
  onChangePool: () => void;
}) {
  return (
    <Card rail={semantic.warn}>
      <ChalkText variant="title" style={styles.mb}>Not enough for a full roadmap yet</ChalkText>
      <ChalkText variant="body" style={styles.dim}>
        {reason ? SHORTFALL_COPY[reason] : 'We couldn’t build 4 packages from your liked offers.'}
      </ChalkText>
      <View style={styles.btnRow}>
        <Button label="Get more ideas" onPress={onMoreIdeas} style={styles.flex} />
        <Button label="Change my pool" variant="secondary" onPress={onChangePool} style={styles.flex} />
      </View>
    </Card>
  );
}

function recoveryLine(season: number | null, holder: string | null, state: string): string {
  const yr = season ? `${season} ` : '';
  if (state === 'missing_with_known_holder' && holder) {
    return `Your ${yr}1st is with ${holder}. The offer that returns it is worth sending first — you can still send other offers first.`;
  }
  if (state === 'not_yet_available') {
    return `The league hasn’t published ${yr}picks yet, so your own first can’t be recovered here.`;
  }
  return `Recovering your own ${yr}1st is still open.`;
}

function errorLine(e: unknown, fallback: string): string {
  if (e instanceof ApiError && typeof e.body === 'object' && e.body) {
    const code = (e.body as { error?: string }).error;
    if (code === 'stale_version') return 'This roadmap changed — pull to refresh and try again';
    if (code === 'tier_duplicate_counterparty') return 'Two offers to the same team can’t share a tier';
  }
  return fallback;
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: ink.ink0 },
  center: {
    flex: 1, backgroundColor: ink.ink0, alignItems: 'center', justifyContent: 'center',
    padding: space.xl, gap: space.md,
  },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  dim: { color: chalk.dim },
  warn: { color: semantic.warn },
  flare: { color: flare.base },
  flex: { flex: 1 },
  stack: { gap: space.sm },
  mb: { marginBottom: space.xs },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  pkg: {
    borderTopWidth: 1, borderTopColor: ink.line, paddingTop: space.md, marginTop: space.md,
    gap: space.xs,
  },
  swap: {
    marginTop: space.sm, backgroundColor: ink.ink2, borderRadius: radii.sm, padding: space.md,
    gap: space.sm,
  },
  altRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  btnRow: { flexDirection: 'row', gap: space.sm, marginTop: space.sm },
});
