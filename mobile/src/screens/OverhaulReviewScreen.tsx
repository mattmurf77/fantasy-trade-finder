import React, { useEffect, useState } from 'react';
import { View, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button } from '../components/chalkline';
import TradeCard from '../components/TradeCard';
import { ink, chalk, ice, flare, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { ApiError } from '../api/client';
import { uuidv4 } from '../api/_queue';
import {
  assembleRoadmaps, generateOffers, getOffers, getOverhaul, postDecisions,
  type Offer, type OfferDecision, type ReviewProgress, type ShortfallReason,
} from '../api/overhaul';
import type { TradeCard as TradeCardData } from '../shared/types';
import { SHORTFALL_COPY } from './OverhaulTargetsScreen';

// Team overhaul step 4 (BUILD-CONTRACT §9 / D3, PRODUCT-SPEC R5) — like/pass
// review of generated offers. Reuses TradeCard with `disposition` so the offer
// reads exactly like a deck card, but decisions go ONLY to
// `/api/overhauls/{id}/decisions`: no deck swipe/decide helpers, no Elo or
// taste learning of any kind (explicit policy — plan review is not taste).
// "Build roadmaps" unlocks once every offer in the batch has a decision (D3).
//
// Trades-stack screen → no local feedback FAB (RootNav's global mount, #188).

/** The server's `card` is the public trade-card dict as the deck emits it.
 *  Fill the few fields the client normalizer would have defaulted so the
 *  shared TradeCard renders it without a second normalizer. */
function toCardData(offer: Offer): TradeCardData {
  const raw = (offer.card ?? {}) as Partial<TradeCardData> & { target_user_id?: string };
  return {
    ...(raw as TradeCardData),
    trade_id: raw.trade_id ?? offer.offer_id,
    give_player_ids: raw.give_player_ids ?? offer.give_ids,
    receive_player_ids: raw.receive_player_ids ?? offer.receive_ids,
    give_players: raw.give_players ?? [],
    receive_players: raw.receive_players ?? [],
    opponent_user_id: raw.opponent_user_id ?? raw.target_user_id ?? offer.counterparty_user_id,
    opponent_username: raw.opponent_username ?? offer.counterparty_username,
    match_score: raw.match_score ?? 0,
    fairness: raw.fairness ?? 0,
  };
}

function errorCopy(e: unknown, verb: string): string {
  if (e instanceof ApiError) {
    const code = (e.body as any)?.error;
    if (code === 'feature_disabled') return 'Team overhaul isn’t available right now.';
    if (code === 'stale_revision') return 'This plan changed elsewhere. Reload and try again.';
    if (code === 'not_found') return 'This overhaul no longer exists.';
    if (code === 'supply_exhausted') return 'We’ve run out of new ideas for this pool. Try changing your pool.';
    if (e.isTimeout) return `${verb} took too long. Try again.`;
    if (typeof code === 'string') return `${verb} failed (${code}).`;
  }
  return `${verb} failed. Check your connection and try again.`;
}

export default function OverhaulReviewScreen({ navigation, route }: any) {
  const overhaulId: string = route?.params?.overhaulId ?? '';
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || '';
  const qc = useQueryClient();

  const viewQ = useQuery({
    queryKey: ['overhaul', overhaulId],
    queryFn: () => getOverhaul(overhaulId),
    enabled: !!overhaulId,
  });
  const offersQ = useQuery({
    queryKey: ['overhaul', overhaulId, 'offers', 'undecided'],
    queryFn: () => getOffers(overhaulId, 'undecided'),
    enabled: !!overhaulId,
  });

  // Local mirror of the undecided queue + progress so a decision advances the
  // deck immediately; the server is the source of truth on every refetch.
  const [queue, setQueue] = useState<Offer[]>([]);
  const [progress, setProgress] = useState<ReviewProgress>({ decided: 0, total: 0, liked: 0 });
  const [busy, setBusy] = useState<'decide' | 'more' | 'build' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shortfall, setShortfall] = useState<ShortfallReason | null>(null);

  useEffect(() => {
    if (!offersQ.data) return;
    setQueue(offersQ.data.offers);
    setProgress(offersQ.data.progress);
  }, [offersQ.data]);

  const revision = viewQ.data?.revision;
  const top = queue[0];

  const decide = async (decision: OfferDecision) => {
    if (!top || busy || revision == null) return;
    setBusy('decide');
    setError(null);
    const offer = top;
    // Optimistic advance; a failure restores the card at the front.
    setQueue((q) => q.slice(1));
    setProgress((p) => ({ ...p, decided: p.decided + 1, liked: p.liked + (decision === 'like' ? 1 : 0) }));
    try {
      const res = await postDecisions(overhaulId, {
        revision,
        decisions: [{ offer_id: offer.offer_id, decision, client_key: uuidv4() }],
      });
      setProgress(res.progress);
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
    } catch (e) {
      setQueue((q) => [offer, ...q]);
      setProgress((p) => ({ ...p, decided: p.decided - 1, liked: p.liked - (decision === 'like' ? 1 : 0) }));
      setError(errorCopy(e, 'Saving your decision'));
    } finally {
      setBusy(null);
    }
  };

  const moreIdeas = async () => {
    if (busy || revision == null) return;
    setBusy('more');
    setError(null);
    setShortfall(null);
    try {
      const gen = await generateOffers(overhaulId, { revision });
      if (gen.offers.length === 0) setShortfall(gen.generation.shortfall_reason ?? 'search_exhausted');
      await Promise.all([offersQ.refetch(), viewQ.refetch()]);
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
    } catch (e) {
      setError(errorCopy(e, 'Finding more ideas'));
    } finally {
      setBusy(null);
    }
  };

  const build = async () => {
    if (busy || revision == null) return;
    setBusy('build');
    setError(null);
    setShortfall(null);
    try {
      const res = await assembleRoadmaps(overhaulId, { revision });
      qc.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
      if (res.roadmaps.length === 0) {
        setShortfall(res.shortfall?.reason ?? 'insufficient_likes');
        return;
      }
      navigation.navigate('OverhaulRoadmaps' as never, { overhaulId } as never);
    } catch (e) {
      setError(errorCopy(e, 'Building roadmaps'));
    } finally {
      setBusy(null);
    }
  };

  if (viewQ.isLoading || offersQ.isLoading || revision == null) {
    return (
      <View style={[styles.screen, styles.center]}>
        {viewQ.isError || offersQ.isError
          ? <ChalkText style={styles.error}>{errorCopy(viewQ.error ?? offersQ.error, 'Loading offers')}</ChalkText>
          : <ActivityIndicator color={ice.base} />}
      </View>
    );
  }

  const allDecided = progress.total > 0 && progress.decided === progress.total;
  const pct = progress.total > 0 ? Math.min(1, progress.decided / progress.total) : 0;

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <ChalkText style={styles.kicker}>Team overhaul · 04</ChalkText>
        <ChalkText variant="heading" style={styles.h1}>Find the moves you like</ChalkText>
        <ChalkText style={styles.lede}>
          Each card is one offer. Only your likes can become part of a roadmap.
        </ChalkText>

        <View style={styles.progressRow}>
          <ChalkText style={styles.progressText}>
            {`${progress.decided} of ${progress.total} reviewed · ${progress.liked} liked`}
          </ChalkText>
        </View>
        <View style={styles.bar}>
          <View style={[styles.barFill, { flex: pct }]} />
          <View style={{ flex: 1 - pct }} />
        </View>

        {top ? (
          <View style={styles.deck}>
            {top.is_recovery ? (
              <View style={styles.ribbon}>
                <ChalkText style={styles.ribbonText}>Priority 1: Recover your first</ChalkText>
              </View>
            ) : null}
            <TradeCard
              data={toCardData(top)}
              variant="swipe"
              disposition={{ onLike: () => decide('like'), onPass: () => decide('pass'), disabled: !!busy }}
              hideLockButton
              hideMatchStrength={!(top.card && top.card.match_score > 0)}
              showSend={false}
            />
            <View style={styles.decideRow}>
              <Button
                testID="overhaul.review.pass"
                label="Pass"
                variant="pass"
                onPress={() => decide('pass')}
                disabled={!!busy}
                style={styles.half}
              />
              <Button
                testID="overhaul.review.like"
                label="Like"
                variant="like"
                onPress={() => decide('like')}
                disabled={!!busy}
                style={styles.half}
              />
            </View>
            <ChalkText style={styles.counter}>{`${queue.length} left in this batch`}</ChalkText>
          </View>
        ) : (
          <View style={styles.empty}>
            <ChalkText style={styles.emptyTitle}>
              {progress.total === 0 ? 'No offers yet' : 'Batch reviewed'}
            </ChalkText>
            <ChalkText style={styles.emptyBody}>
              {progress.total === 0
                ? 'Ask for ideas to start reviewing.'
                : `${progress.liked} liked. Build roadmaps from your likes, or get more ideas first.`}
            </ChalkText>
          </View>
        )}

        {shortfall ? (
          <View style={styles.shortfall}>
            <ChalkText style={styles.shortfallTitle}>Not enough to build a roadmap</ChalkText>
            <ChalkText style={styles.shortfallBody}>{SHORTFALL_COPY[shortfall]}</ChalkText>
            <View style={styles.decideRow}>
              <Button label="Get more ideas" variant="secondary" compact onPress={moreIdeas} loading={busy === 'more'} style={styles.half} />
              <Button
                label="Change my pool"
                variant="secondary"
                compact
                onPress={() => navigation.navigate('OverhaulAssets' as never, { overhaulId } as never)}
                style={styles.half}
              />
            </View>
          </View>
        ) : null}

        {error ? <ChalkText style={styles.error}>{error}</ChalkText> : null}

        <Button
          label="More ideas"
          variant="secondary"
          onPress={moreIdeas}
          disabled={!!busy}
          loading={busy === 'more'}
        />
      </ScrollView>

      <View style={styles.footer}>
        <Button
          testID="overhaul.review.build"
          label="Build roadmaps"
          onPress={build}
          disabled={!allDecided || !!busy}
          loading={busy === 'build'}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: ink.ink0 },
  center: { alignItems: 'center', justifyContent: 'center', padding: space.lg },
  content: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },
  kicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  h1: { color: chalk.base },
  lede: { ...type.body, color: chalk.dim },
  progressRow: { flexDirection: 'row', justifyContent: 'space-between' },
  progressText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.data },
  bar: { flexDirection: 'row', height: 4, backgroundColor: ink.ink3, borderRadius: radii.xs, overflow: 'hidden' },
  barFill: { backgroundColor: ice.base },
  deck: { gap: space.sm },
  ribbon: {
    borderWidth: 1, borderColor: flare.base, borderRadius: radii.sm, paddingVertical: 6, paddingHorizontal: space.md,
    alignSelf: 'flex-start',
  },
  ribbonText: { ...type.label, color: flare.base, letterSpacing: 1, textTransform: 'uppercase' },
  decideRow: { flexDirection: 'row', gap: space.sm },
  half: { flex: 1 },
  counter: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },
  empty: {
    borderWidth: 1, borderColor: ink.line, borderRadius: radii.md, padding: space.lg, gap: space.xs,
    backgroundColor: ink.ink1,
  },
  emptyTitle: { ...type.title, color: chalk.base },
  emptyBody: { ...type.bodySm, color: chalk.dim },
  shortfall: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.md, padding: space.md, gap: space.sm,
    backgroundColor: ink.ink1,
  },
  shortfallTitle: { ...type.title, color: chalk.base },
  shortfallBody: { ...type.bodySm, color: chalk.dim },
  error: { ...type.bodySm, color: semantic.neg },
  footer: { padding: space.lg, borderTopWidth: 1, borderTopColor: ink.line, backgroundColor: ink.ink0 },
});
