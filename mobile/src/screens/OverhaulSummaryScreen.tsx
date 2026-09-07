import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigation, useRoute } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { Button, Card, TickLabel } from '../components/chalkline';
import Toast from '../components/Toast';
import { haptics } from '../utils/haptics';
import { copyText } from '../utils/clipboard';
import { ink, chalk, flare, semantic, space, radii, type } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';
import { ApiError } from '../api/client';
import { uuidv4 } from '../api/_queue';
import {
  getOverhaul,
  prepareSend,
  sendBatch,
  type OverhaulView,
  type Offer,
  type PrepareView,
  type ValidationItem,
} from '../api/overhaul';

// Team overhaul — step 7, the send summary (BUILD-CONTRACT §7 prepare-send /
// send, PRODUCT-SPEC R8). Mount = one `prepare-send`; the server returns the
// exact batch, its receipt, and the races. Nothing here is a provider write
// until "Send all offers", and every count is the server's, never derived
// client-side (R8.2: offers ≠ packages ≠ max accepted).
//
// Idempotency: ONE uuid per prepare, minted with the prepare result and
// reused on every retry of that batch, so a double tap or a flaky network
// replays the same batch instead of sending twice. A re-prepare (token
// expired) mints a new key because it is a new reviewed batch.
//
// `handoff.mode === 'copy'` platforms never see a send button: the CTA copies
// the server-composed text and the label says "Copied", never "Sent".
//
// Tab-stack screen: NO FeedbackFAB.

const COPIED_MS = 2000;

type Prepared = { view: PrepareView; idempotencyKey: string };

function assetName(view: OverhaulView, id: string): string {
  const a = view.eligible_assets.find((x) => x.id === id);
  if (!a) return id;
  return a.kind === 'pick' ? a.label || a.name : a.name;
}

function receiveLine(offer: Offer | undefined): string {
  return offer?.card.receive_players.map((p) => p.name).join(' + ') || '—';
}

function errorCode(e: unknown): string | null {
  if (e instanceof ApiError && typeof e.body === 'object' && e.body) {
    return (e.body as { error?: string }).error ?? null;
  }
  return null;
}

function errorDetail(e: unknown): string | null {
  if (e instanceof ApiError && typeof e.body === 'object' && e.body) {
    const d = (e.body as { detail?: unknown }).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(', ');
  }
  return null;
}

export default function OverhaulSummaryScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { overhaulId, roadmapId, offerIds } = (route.params ?? {}) as {
    overhaulId: string; roadmapId: string; offerIds?: string[];
  };
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
    () => view?.roadmaps.find((r) => r.roadmap_id === roadmapId) ?? null,
    [view, roadmapId],
  );

  // Default batch = tier 1 of every open package (contract §7 prepare-send).
  const batchOfferIds = useMemo<string[]>(() => {
    if (offerIds?.length) return offerIds;
    if (!roadmap) return [];
    return roadmap.packages
      .filter((p) => p.status === 'open')
      .flatMap((p) => p.tiers.find((t) => t.tier === 1)?.offer_ids ?? []);
  }, [offerIds, roadmap]);

  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone: 'warn' | 'error' | 'success' } | null>(null);
  const sendingRef = useRef(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preparedForRef = useRef<string | null>(null);

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
    if (leagueId) void queryClient.invalidateQueries({ queryKey: ['overhaul', leagueId] });
  }, [queryClient, overhaulId, leagueId]);

  const prepare = useCallback(async () => {
    if (!roadmap) return;
    setPrepareError(null);
    setConflict(null);
    try {
      const pv = await prepareSend(overhaulId, roadmapId, {
        version: roadmap.version,
        offer_ids: batchOfferIds,
      });
      setPrepared({ view: pv, idempotencyKey: uuidv4() });
    } catch (e) {
      setPrepared(null);
      const code = errorCode(e);
      if (code === 'stale_version') { invalidate(); setPrepareError('This roadmap changed. Reloading…'); }
      else setPrepareError(errorDetail(e) ?? 'Couldn’t check these offers right now.');
    }
  }, [roadmap, overhaulId, roadmapId, batchOfferIds, invalidate]);

  // One prepare per (roadmap version, batch). A version bump from the
  // stale_version path above re-runs it with the fresh version.
  const prepareKey = roadmap ? `${roadmap.version}:${batchOfferIds.join(',')}` : null;
  useEffect(() => {
    if (!prepareKey || preparedForRef.current === prepareKey) return;
    preparedForRef.current = prepareKey;
    void prepare();
  }, [prepareKey, prepare]);

  useEffect(() => () => { if (copiedTimer.current) clearTimeout(copiedTimer.current); }, []);

  const onSend = useCallback(async () => {
    if (!prepared || !roadmap || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setConflict(null);
    const pv = prepared.view;
    track('overhaul_batch_requested', {
      overhaul_id: overhaulId,
      package_count: pv.counts.packages,
      offer_count: pv.counts.offers,
      tied_package_count: pv.races.length,
    });
    try {
      await sendBatch(overhaulId, {
        prepare_token: pv.prepare_token,
        summary_hash: pv.summary_hash,
        version: roadmap.version,
        idempotency_key: prepared.idempotencyKey,
      });
      haptics.success();
      invalidate();
      navigation.replace('OverhaulPlan', { overhaulId });
    } catch (e) {
      haptics.warning();
      const code = errorCode(e);
      if (code === 'prepare_expired') {
        setToast({ msg: 'Offers re-checked — review and send again', tone: 'warn' });
        preparedForRef.current = null; // force a fresh prepare + a new key
        await prepare();
      } else if (code === 'asset_reserved') {
        setConflict(errorDetail(e) ?? 'Some of these assets are already tied up in a live offer.');
        invalidate();
      } else if (code === 'capability_unavailable' || code === 'reconnect_required' || code === 'verification_required') {
        setConflict('This league can’t be sent to from the app right now — reconnect Sleeper in Settings.');
      } else {
        setToast({ msg: errorDetail(e) ?? 'Send failed — nothing went out', tone: 'error' });
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [prepared, roadmap, overhaulId, invalidate, navigation, prepare]);

  const onCopy = useCallback(() => {
    const text = prepared?.view.handoff.text;
    if (!text) return;
    copyText(text);
    haptics.success();
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), COPIED_MS);
  }, [prepared]);

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
  if (!roadmap) {
    return (
      <View style={styles.center}>
        <ChalkText variant="body" style={styles.dim}>This roadmap is no longer available.</ChalkText>
        <Button label="Back to roadmaps" variant="secondary" onPress={() => navigation.navigate('OverhaulRoadmaps', { overhaulId })} />
      </View>
    );
  }

  const pv = prepared?.view ?? null;
  const receipt = pv?.receipt ?? null;
  const caps = pv?.capabilities ?? view.capabilities;
  const raceByPackage = new Map((pv?.races ?? []).map((r) => [r.package_id, r]));
  const batchSet = new Set(batchOfferIds);
  const packagesInBatch = roadmap.packages.filter((p) =>
    p.tiers.some((t) => t.offer_ids.some((id) => batchSet.has(id))),
  );
  const recovery = view.recovery;
  const platformLabel = caps.platform ? caps.platform.toUpperCase() : 'your league';
  const linked = caps.auth_state === 'linked';
  const sendBlockedWhy = !receipt
    ? null
    : !receipt.ok
      ? 'Fix the blockers above before sending.'
      : !linked
        ? `Sleeper isn’t linked (${caps.auth_state}). Reconnect in Settings to send.`
        : null;

  return (
    <View style={styles.wrap}>
      <ScrollView contentContainerStyle={styles.body}>
        <ChalkText variant="display">Ready to put it in motion</ChalkText>
        <ChalkText variant="body" style={styles.dim}>
          Review exactly which offers go out now. Ownership is checked again at the moment of sending.
        </ChalkText>

        {pv ? (
          <Card>
            <TickLabel>Current send batch</TickLabel>
            <ChalkText variant="heading" style={styles.counts}>
              {`${pv.counts.offers} offers · ${pv.counts.packages} packages · up to ${pv.counts.max_accepted} trades`}
            </ChalkText>
            <ChalkText variant="bodySm" style={styles.dim}>
              At most one accepted trade per package. Tied offers add to the first number, not the last.
            </ChalkText>
          </Card>
        ) : prepareError ? (
          <Card rail={semantic.neg}>
            <ChalkText variant="body">{prepareError}</ChalkText>
            <Button label="Check again" variant="secondary" compact onPress={() => { preparedForRef.current = null; void prepare(); }} style={styles.mt} />
          </Card>
        ) : (
          <View style={styles.inline}><ActivityIndicator color={chalk.dim} /><ChalkText variant="bodySm" style={styles.dim}>Checking these offers…</ChalkText></View>
        )}

        {recovery.applicable && !recovery.resolved ? (
          <Card rail={flare.base} padding={space.md}>
            <ChalkText style={[type.label, styles.flare]}>PRIORITY 1: RECOVER YOUR FIRST</ChalkText>
            <ChalkText variant="bodySm">
              {`Your own ${recovery.season ?? ''} 1st isn’t recovered by this batch. Sending is still allowed — you can chase it after.`}
            </ChalkText>
          </Card>
        ) : null}

        {receipt?.blockers.length ? (
          <Card rail={semantic.neg} padding={space.md}>
            <ChalkText style={[type.label, styles.neg]}>CAN’T SEND YET</ChalkText>
            {receipt.blockers.map((b, i) => <ReceiptLine key={`b${i}`} item={b} offers={roadmap.offers} />)}
          </Card>
        ) : null}
        {receipt?.warnings.length ? (
          <Card rail={semantic.warn} padding={space.md}>
            <ChalkText style={[type.label, styles.warn]}>WORTH KNOWING</ChalkText>
            {receipt.warnings.map((w, i) => <ReceiptLine key={`w${i}`} item={w} offers={roadmap.offers} />)}
            {receipt.unknowns.includes('capacity_unknown') ? (
              <ChalkText variant="bodySm" style={styles.dim}>Roster size limit unknown for this league — not checked.</ChalkText>
            ) : null}
          </Card>
        ) : null}
        {conflict ? (
          <Card rail={semantic.neg} padding={space.md}>
            <ChalkText style={[type.label, styles.neg]}>NOTHING WAS SENT</ChalkText>
            <ChalkText variant="bodySm">{conflict}</ChalkText>
          </Card>
        ) : null}

        {packagesInBatch.map((pkg, i) => {
          const race = raceByPackage.get(pkg.package_id);
          const inBatch = pkg.tiers.flatMap((t) =>
            t.offer_ids.filter((id) => batchSet.has(id)).map((id) => ({ id, tier: t.tier })),
          );
          return (
            <Card key={pkg.package_id}>
              <View style={styles.rowBetween}>
                <TickLabel>{`Package ${i + 1}`}</TickLabel>
                <ChalkText variant="data" style={styles.dim}>{`Priority ${inBatch[0]?.tier ?? 1}`}</ChalkText>
              </View>
              {pkg.reason === 'recover_own_first' ? (
                <ChalkText style={[type.label, styles.flare]}>PRIORITY 1 · RECOVER YOUR FIRST</ChalkText>
              ) : null}
              {race ? (
                <View style={styles.race}>
                  <ChalkText variant="bodySm">
                    {`These ${race.offer_ids.length} offers share the same outgoing assets and go out together — first come, first served; only one can complete.`}
                  </ChalkText>
                </View>
              ) : null}
              {inBatch.map(({ id }) => {
                const offer = roadmap.offers[id];
                return (
                  <View key={id} style={styles.offer}>
                    <ChalkText variant="title">{`Offer to ${offer?.counterparty_username ?? id}`}</ChalkText>
                    <View style={styles.sides}>
                      <View style={styles.side}>
                        <ChalkText variant="label" style={styles.dim}>YOU SEND</ChalkText>
                        {pkg.give_ids.map((gid) => (
                          <ChalkText key={gid} variant="body">{assetName(view, gid)}</ChalkText>
                        ))}
                      </View>
                      <View style={[styles.side, styles.sideRight]}>
                        <ChalkText variant="label" style={styles.dim}>YOU RECEIVE</ChalkText>
                        <ChalkText variant="body">{receiveLine(offer)}</ChalkText>
                      </View>
                    </View>
                    {offer?.availability === 'stale' ? (
                      <ChalkText variant="bodySm" style={styles.warn}>Needs refresh</ChalkText>
                    ) : null}
                  </View>
                );
              })}
            </Card>
          );
        })}

        <ChalkText variant="bodySm" style={styles.dim}>
          {caps.can_propose
            ? `Sends go through ${platformLabel} · ${linked ? 'linked' : caps.auth_state}. Replies show up on the saved roadmap after a refresh.`
            : `This league’s platform can’t be sent to from the app yet — paste these into ${platformLabel}.`}
        </ChalkText>

        {pv?.handoff.mode === 'copy' ? (
          <Button
            label={copied ? 'Copied' : 'Copy offers'}
            onPress={onCopy}
            disabled={!pv.handoff.text}
            testID="overhaul.summary.copy"
          />
        ) : (
          <>
            <Button
              label="Send all offers"
              onPress={() => { void onSend(); }}
              loading={sending}
              disabled={!pv || !receipt?.ok || !linked}
              testID="overhaul.summary.send-all"
            />
            {sendBlockedWhy ? (
              <ChalkText variant="bodySm" style={styles.warn}>{sendBlockedWhy}</ChalkText>
            ) : null}
          </>
        )}
        <Button
          label="Open saved roadmap"
          variant="secondary"
          onPress={() => navigation.navigate('OverhaulPlan', { overhaulId })}
        />
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

function ReceiptLine({ item, offers }: { item: ValidationItem; offers: Record<string, Offer> }) {
  const who = item.offer_id ? offers[item.offer_id]?.counterparty_username : null;
  const prefix = who ? `${who}: ` : item.package_id ? 'Package: ' : '';
  return <ChalkText variant="bodySm">{`${prefix}${item.message}`}</ChalkText>;
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: ink.ink0 },
  center: {
    flex: 1, backgroundColor: ink.ink0, alignItems: 'center', justifyContent: 'center',
    padding: space.xl, gap: space.md,
  },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  inline: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dim: { color: chalk.dim },
  warn: { color: semantic.warn },
  neg: { color: semantic.neg },
  flare: { color: flare.base },
  mt: { marginTop: space.sm },
  counts: { marginTop: space.xs },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  race: {
    backgroundColor: ink.ink2, borderLeftWidth: 3, borderLeftColor: semantic.warn,
    borderRadius: radii.sm, padding: space.md, marginTop: space.sm,
  },
  offer: { borderTopWidth: 1, borderTopColor: ink.line, paddingTop: space.md, marginTop: space.md, gap: space.xs },
  sides: { flexDirection: 'row', marginTop: space.xs },
  side: { flex: 1, gap: 2 },
  sideRight: { borderLeftWidth: 1, borderLeftColor: ink.line, paddingLeft: space.md },
});
