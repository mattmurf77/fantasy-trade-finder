import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Pressable, ActivityIndicator, StyleSheet, type AccessibilityActionEvent,
} from 'react-native';
import DraggableFlatList, {
  type RenderItemParams,
  type DragEndParams,
} from 'react-native-draggable-flatlist';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigation, useRoute } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { Button, Card, TickLabel, PositionBadge } from '../components/chalkline';
import Toast from '../components/Toast';
import { haptics } from '../utils/haptics';
import {
  ink, chalk, ice, flare, semantic, space, radii, type, DRAG_ACTIVATION_DISTANCE,
} from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { ApiError } from '../api/client';
import {
  getOverhaul,
  savePriorities,
  type OverhaulView,
  type Offer,
  type PriorityTier,
} from '../api/overhaul';

// Team overhaul — step 6, one package per page (BUILD-CONTRACT §9, PRODUCT-SPEC
// R7). The package's outgoing set is FIXED; the user only orders its liked
// alternatives into priority tiers. Same tier = sent together as a race (only
// one can complete); later tiers wait for the user after responses (D5).
//
// Drag recipe is TiersScreen's, verbatim in spirit: one DraggableFlatList
// whose header rows define the zones, an `empty` placeholder keeps an empty
// tier droppable, and there is always one extra empty tier at the bottom so
// an offer can be demoted into a tier that doesn't exist yet. The no-drag path
// is the visible Move control (also the VoiceOver custom-action host).
//
// D4 is enforced here AND on the server: two offers to the same counterparty
// cannot share a tier. A drop that would create one snaps back with a toast.
//
// Tab-stack screen: NO FeedbackFAB. The Back / Continue bar is the list
// footer, not a pinned bar, so nothing here reports a bottom-bar offset.

type Row =
  | { kind: 'header'; tier: number }
  | { kind: 'offer'; tier: number; offer: Offer }
  | { kind: 'empty'; tier: number };

const DRAG_ACTIVATION_MS = 220;

/** Tiers as arrays of offer ids, index 0 = tier 1. Trailing/mid empties are
 *  never stored: the contiguity rule is a property of this shape. */
type TierState = string[][];

function fromWire(tiers: PriorityTier[] | undefined): TierState {
  return [...(tiers ?? [])]
    .sort((a, b) => a.tier - b.tier)
    .map((t) => [...(t.offer_ids ?? [])])
    .filter((ids) => ids.length > 0);
}

function toWire(tiers: TierState): PriorityTier[] {
  return tiers.map((offer_ids, i) => ({ tier: i + 1, offer_ids }));
}

function sameTiers(a: TierState, b: TierState): boolean {
  return a.length === b.length && a.every((ids, i) => ids.join('|') === b[i].join('|'));
}

/** D4 — at most one offer per counterparty inside a tier. Returns the
 *  offending tier number, or null. */
function duplicateCounterpartyTier(tiers: TierState, offers: Record<string, Offer>): number | null {
  for (let i = 0; i < tiers.length; i++) {
    const seen = new Set<string>();
    for (const id of tiers[i]) {
      const cp = offers[id]?.counterparty_user_id ?? id;
      if (seen.has(cp)) return i + 1;
      seen.add(cp);
    }
  }
  return null;
}

// Server data is guarded (`?? []`, `?.`, Number.isFinite) everywhere it is
// read in render: a malformed card must degrade to '—', never throw.
function receiveLine(offer: Offer): string {
  return (offer.card?.receive_players ?? []).map((p) => p?.name).filter(Boolean).join(' + ') || '—';
}

function fairnessLine(offer: Offer): string {
  const f = offer.card?.fairness;
  return Number.isFinite(f) ? `${Math.round(f * 100)}% fair` : '—';
}

export default function OverhaulPrioritiesScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { overhaulId, roadmapId, packageIndex = 0 } = route.params ?? {};
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
    () => view?.roadmaps?.find((r) => r.roadmap_id === roadmapId) ?? null,
    [view, roadmapId],
  );
  const pkg = roadmap?.packages?.[packageIndex] ?? null;
  const offers = roadmap?.offers ?? {};

  // Local tier layout. Re-seeded from the wire only while untouched, so a
  // background refetch (version bump from another package's save) can never
  // wipe an in-progress drag.
  const [tiers, setTiers] = useState<TierState>([]);
  const dirtyRef = useRef(false);
  const seedKey = roadmap && pkg ? `${roadmap.version}:${pkg.package_id}` : null;
  const seededRef = useRef<string | null>(null);
  useEffect(() => {
    if (!pkg || !seedKey || seededRef.current === seedKey || dirtyRef.current) return;
    seededRef.current = seedKey;
    setTiers(fromWire(pkg.tiers));
  }, [pkg, seedKey]);

  const [movingId, setMovingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone: 'warn' | 'error' } | null>(null);

  const commit = useCallback(
    (next: TierState): boolean => {
      const dupTier = duplicateCounterpartyTier(next, offers);
      if (dupTier != null) {
        haptics.warning();
        setToast({ msg: `Two offers to the same team can’t share Priority ${dupTier}`, tone: 'warn' });
        return false;
      }
      dirtyRef.current = true;
      setTiers(next.filter((ids) => ids.length > 0));
      return true;
    },
    [offers],
  );

  /** Move one offer into tier `target` (1-based; tiers.length + 1 = new tier). */
  const moveOffer = useCallback(
    (offerId: string, target: number) => {
      const next = tiers.map((ids) => ids.filter((id) => id !== offerId));
      while (next.length < target) next.push([]);
      next[target - 1].push(offerId);
      if (commit(next)) haptics.swipe();
      setMovingId(null);
    },
    [tiers, commit],
  );

  // ── Flat list derivation (TiersScreen recipe) ─────────────────────────
  const listData: Row[] = useMemo(() => {
    const rows: Row[] = [];
    const zoneCount = tiers.length + 1; // always one extra, empty tier
    for (let t = 1; t <= zoneCount; t++) {
      rows.push({ kind: 'header', tier: t });
      const ids = tiers[t - 1] ?? [];
      if (ids.length === 0) rows.push({ kind: 'empty', tier: t });
      else for (const id of ids) {
        const offer = offers[id];
        if (offer) rows.push({ kind: 'offer', tier: t, offer });
      }
    }
    return rows;
  }, [tiers, offers]);

  const keyExtractor = useCallback((item: Row) => {
    if (item.kind === 'header') return `hdr:${item.tier}`;
    if (item.kind === 'empty') return `empty:${item.tier}`;
    return item.offer.offer_id;
  }, []);

  const a11yActions = useMemo(
    () => [
      ...tiers.map((_, i) => ({ name: `tier:${i + 1}`, label: `Move to Priority ${i + 1}` })),
      { name: `tier:${tiers.length + 1}`, label: 'Move to a new tier' },
    ],
    [tiers],
  );

  const onDragBegin = useCallback(() => haptics.pickup(), []);
  const onDragEnd = useCallback(
    ({ data, from, to }: DragEndParams<Row>) => {
      if (from === to) return;
      // Walk the post-drop order: each header re-anchors the current tier,
      // every offer row that follows lands in it. Rows above the first
      // header belong to tier 1.
      let zone = 0;
      const next: TierState = [];
      for (const r of data) {
        if (r.kind === 'header') zone = r.tier - 1;
        else if (r.kind === 'offer') {
          while (next.length <= zone) next.push([]);
          next[zone].push(r.offer.offer_id);
        }
      }
      if (commit(next)) haptics.swipe();
    },
    [commit],
  );

  const renderItem = useCallback(
    ({ item, drag, isActive }: RenderItemParams<Row>) => {
      if (item.kind === 'header') {
        const count = tiers[item.tier - 1]?.length ?? 0;
        return (
          <View style={styles.tierHeader}>
            <TickLabel color={item.tier === 1 ? ice.base : chalk.faint}>
              {`Priority ${item.tier}`}
            </TickLabel>
            <View style={styles.tierMeta}>
              {count > 1 ? (
                <View style={styles.tiePill}>
                  <ChalkText variant="label">{`${count} together`}</ChalkText>
                </View>
              ) : null}
              <ChalkText variant="bodySm" style={styles.dim}>
                {item.tier === 1 ? `Send first · ${count}` : `Backup · ${count}`}
              </ChalkText>
            </View>
          </View>
        );
      }
      if (item.kind === 'empty') {
        return (
          <View style={styles.emptyZone}>
            <ChalkText variant="bodySm" style={styles.faint}>Drop an offer here</ChalkText>
          </View>
        );
      }
      const { offer } = item;
      const moving = movingId === offer.offer_id;
      return (
        <View style={styles.offerWrap}>
          <View style={[styles.offerRow, isActive && styles.offerActive]}>
            <Pressable
              onLongPress={drag}
              delayLongPress={DRAG_ACTIVATION_MS}
              disabled={isActive}
              style={styles.flex}
              accessibilityLabel={`Offer to ${offer.counterparty_username}, priority ${item.tier}`}
            >
              <View pointerEvents="none" style={styles.offerBody}>
                <View style={styles.handle}>
                  <View style={styles.handleDot} /><View style={styles.handleDot} />
                  <View style={styles.handleDot} /><View style={styles.handleDot} />
                </View>
                <View style={styles.flex}>
                  <ChalkText variant="title">{offer.counterparty_username}</ChalkText>
                  <ChalkText variant="bodySm" style={styles.dim}>{`Get ${receiveLine(offer)}`}</ChalkText>
                  {offer.is_recovery ? (
                    <ChalkText style={[type.label, styles.flare]}>PRIORITY 1 · RECOVER YOUR FIRST</ChalkText>
                  ) : null}
                  {offer.availability === 'stale' ? (
                    <ChalkText variant="bodySm" style={styles.warn}>Needs refresh</ChalkText>
                  ) : null}
                </View>
                <ChalkText variant="data" style={styles.dim}>
                  {fairnessLine(offer)}
                </ChalkText>
              </View>
            </Pressable>
            <Pressable
              testID={`overhaul.priority.move.${offer.offer_id}`}
              accessibilityRole="button"
              accessibilityLabel={`Move offer to ${offer.counterparty_username}`}
              accessibilityHint="Choose a priority tier"
              accessibilityActions={a11yActions}
              onAccessibilityAction={({ nativeEvent }: AccessibilityActionEvent) => {
                const n = nativeEvent.actionName.startsWith('tier:')
                  ? Number(nativeEvent.actionName.slice(5))
                  : NaN;
                if (Number.isFinite(n)) moveOffer(offer.offer_id, n);
              }}
              onPress={() => setMovingId(moving ? null : offer.offer_id)}
              style={styles.moveBtn}
              hitSlop={8}
            >
              <ChalkText variant="body" style={styles.ice}>Move</ChalkText>
            </Pressable>
          </View>
          {moving ? (
            <View style={styles.moveChips}>
              {a11yActions.map((a, i) => {
                const target = i + 1;
                if (target === item.tier) return null;
                return (
                  <Pressable
                    key={a.name}
                    onPress={() => moveOffer(offer.offer_id, target)}
                    accessibilityRole="button"
                    style={styles.chip}
                  >
                    <ChalkText variant="bodySm">
                      {target > tiers.length ? 'New tier' : `Priority ${target}`}
                    </ChalkText>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
        </View>
      );
    },
    [tiers, movingId, a11yActions, moveOffer],
  );

  // ── Save + navigation ─────────────────────────────────────────────────
  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
    if (leagueId) void queryClient.invalidateQueries({ queryKey: ['overhaul', leagueId] });
  }, [queryClient, overhaulId, leagueId]);

  const packageCount = roadmap?.packages?.length ?? 0;
  const isLast = packageIndex >= packageCount - 1;

  const goNext = useCallback(() => {
    if (isLast) navigation.navigate('OverhaulSummary', { overhaulId, roadmapId });
    else navigation.push('OverhaulPriorities', { overhaulId, roadmapId, packageIndex: packageIndex + 1 });
  }, [isLast, navigation, overhaulId, roadmapId, packageIndex]);

  const onContinue = useCallback(async () => {
    if (!roadmap || !pkg) return;
    if (sameTiers(tiers, fromWire(pkg.tiers))) { goNext(); return; }
    setSaving(true);
    const body = { package_id: pkg.package_id, tiers: toWire(tiers) };
    try {
      try {
        await savePriorities(overhaulId, roadmapId, { version: roadmap.version, ...body });
      } catch (e) {
        if (!(e instanceof ApiError) || errorCode(e) !== 'stale_version') throw e;
        // Another write bumped the version — re-read and re-apply once.
        const fresh: OverhaulView = await getOverhaul(overhaulId);
        const rm = (fresh.roadmaps ?? []).find((r) => r.roadmap_id === roadmapId);
        if (!rm) throw e;
        await savePriorities(overhaulId, roadmapId, { version: rm.version, ...body });
      }
      dirtyRef.current = false;
      invalidate();
      goNext();
    } catch (e) {
      haptics.warning();
      setToast({
        msg: errorCode(e) === 'tier_duplicate_counterparty'
          ? 'Two offers to the same team can’t share a tier'
          : 'Couldn’t save these priorities — try again',
        tone: 'error',
      });
    } finally {
      setSaving(false);
    }
  }, [roadmap, pkg, tiers, overhaulId, roadmapId, invalidate, goNext]);

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
  if (!roadmap || !pkg) {
    return (
      <View style={styles.center}>
        <ChalkText variant="body" style={styles.dim}>This roadmap is no longer available.</ChalkText>
        <Button label="Back to roadmaps" variant="secondary" onPress={() => navigation.navigate('OverhaulRoadmaps', { overhaulId })} />
      </View>
    );
  }

  const tied = tiers.map((ids, i) => ({ tier: i + 1, n: ids.length })).filter((t) => t.n > 1);
  const nextPkg = roadmap.packages[packageIndex + 1];
  const nextLabel = nextPkg
    ? `Next: ${(nextPkg.give_ids ?? []).map((id) => assetName(view, id)).join(' + ')}`
    : 'Next: review and send';

  return (
    <View style={styles.wrap}>
      <DraggableFlatList
        data={listData}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        onDragBegin={onDragBegin}
        onDragEnd={onDragEnd}
        activationDistance={DRAG_ACTIVATION_DISTANCE}
        dragItemOverflow
        containerStyle={styles.flex}
        contentContainerStyle={styles.body}
        testID="overhaul.priority.list"
        ListHeaderComponent={
          <View style={styles.header}>
            <ChalkText variant="display">Set offer priorities</ChalkText>
            <View style={styles.rowBetween}>
              <ChalkText variant="title">{`Package ${packageIndex + 1} of ${packageCount}`}</ChalkText>
              <ChalkText variant="bodySm" style={styles.dim}>
                {`${Object.values(tiers).flat().length} liked offers`}
              </ChalkText>
            </View>
            <View style={styles.progress}>
              {roadmap.packages.map((p, i) => (
                <View key={p.package_id} style={[styles.tick, i <= packageIndex && styles.tickOn]} />
              ))}
            </View>
            <TickLabel>This package sends</TickLabel>
            <View style={styles.assets}>
              {(pkg.give_ids ?? []).map((id) => {
                const a = (view.eligible_assets ?? []).find((x) => x.id === id);
                const pos = a?.position;
                return (
                  <View key={id} style={styles.assetRow}>
                    {a?.kind === 'player' && isPos(pos) ? <PositionBadge pos={pos} /> : null}
                    <ChalkText variant="title">{assetName(view, id)}</ChalkText>
                  </View>
                );
              })}
            </View>
            {pkg.reason === 'recover_own_first' ? (
              <Card rail={flare.base} padding={space.md}>
                <ChalkText style={[type.label, styles.flare]}>PRIORITY 1: RECOVER YOUR FIRST</ChalkText>
                <ChalkText variant="bodySm">
                  This package brings back your own first. Worth sending first; the rest can go out either way.
                </ChalkText>
              </Card>
            ) : null}
            <ChalkText variant="body" style={styles.dim}>
              Offers in the same tier go out together — first come, first served. Later tiers wait for you.
            </ChalkText>
            <ChalkText variant="bodySm" style={styles.faint}>
              Hold an offer to drag it, or tap Move to pick a tier.
            </ChalkText>
          </View>
        }
        ListFooterComponent={
          <View style={styles.footer}>
            {tied.map((t) => (
              <Card key={t.tier} rail={semantic.warn} padding={space.md}>
                <ChalkText variant="bodySm">
                  {`${t.n} offers in Priority ${t.tier} go out together. They use the same outgoing assets, so only one can be accepted.`}
                </ChalkText>
              </Card>
            ))}
            <View style={styles.btnRow}>
              <Button label="Back" variant="secondary" onPress={() => navigation.goBack()} style={styles.flex} disabled={saving} />
              <Button
                label={isLast ? 'Review and send' : 'Continue'}
                onPress={() => { void onContinue(); }}
                loading={saving}
                style={styles.flex}
                testID="overhaul.continue"
              />
            </View>
            <ChalkText variant="bodySm" style={styles.faint}>{nextLabel}</ChalkText>
          </View>
        }
      />
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
    </View>
  );
}

function assetName(view: OverhaulView, id: string): string {
  const a = (view.eligible_assets ?? []).find((x) => x.id === id);
  if (!a) return id;
  return a.kind === 'pick' ? a.label || a.name : a.name;
}

function isPos(p: string | undefined): p is 'QB' | 'RB' | 'WR' | 'TE' {
  return p === 'QB' || p === 'RB' || p === 'WR' || p === 'TE';
}

function errorCode(e: unknown): string | null {
  if (e instanceof ApiError && typeof e.body === 'object' && e.body) {
    return (e.body as { error?: string }).error ?? null;
  }
  return null;
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: ink.ink0 },
  center: {
    flex: 1, backgroundColor: ink.ink0, alignItems: 'center', justifyContent: 'center',
    padding: space.xl, gap: space.md,
  },
  flex: { flex: 1 },
  body: { padding: space.lg, paddingBottom: space.xxxl },
  header: { gap: space.md, marginBottom: space.md },
  footer: { gap: space.md, marginTop: space.lg },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  progress: { flexDirection: 'row', gap: 3 },
  tick: { flex: 1, height: 2, backgroundColor: ink.ink3, borderRadius: radii.xs },
  tickOn: { backgroundColor: ice.base },
  assets: { gap: space.xs },
  assetRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dim: { color: chalk.dim },
  faint: { color: chalk.faint },
  warn: { color: semantic.warn },
  flare: { color: flare.base },
  ice: { color: ice.base },

  tierHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingTop: space.lg, paddingBottom: space.sm,
  },
  tierMeta: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  tiePill: {
    backgroundColor: ink.ink3, borderRadius: radii.pill, paddingHorizontal: space.sm,
    paddingVertical: 2,
  },
  emptyZone: {
    borderWidth: 1, borderStyle: 'dashed', borderColor: ink.lineStrong, borderRadius: radii.md,
    padding: space.lg, alignItems: 'center',
  },
  offerWrap: { marginBottom: space.sm },
  offerRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: ink.ink1, borderWidth: 1,
    borderColor: ink.line, borderRadius: radii.md, paddingRight: space.sm,
  },
  offerActive: { borderColor: ice.base },
  offerBody: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md },
  handle: {
    width: 20, flexDirection: 'row', flexWrap: 'wrap', gap: 4, justifyContent: 'center',
  },
  handleDot: { width: 4, height: 4, borderRadius: radii.xs, backgroundColor: chalk.faint },
  moveBtn: { paddingHorizontal: space.md, paddingVertical: space.md },
  moveChips: {
    flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, padding: space.sm,
    backgroundColor: ink.ink2, borderRadius: radii.sm, marginTop: space.xs,
  },
  chip: {
    borderWidth: 1, borderColor: ink.lineStrong, borderRadius: radii.sm,
    paddingHorizontal: space.md, paddingVertical: space.xs,
  },
  btnRow: { flexDirection: 'row', gap: space.sm },
});
