import React, { useEffect, useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, PositionBadge } from '../components/chalkline';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { ApiError } from '../api/client';
import {
  generateOffers, getOverhaul, updateOverhaulSettings,
  type OverhaulView, type ShortfallReason,
} from '../api/overhaul';

// Team overhaul step 3 (BUILD-CONTRACT §9, PRODUCT-SPEC R4) — optional return
// preferences. Positions are a PREFERENCE across the roadmap, never a per-offer
// filter (R4.2), so nothing is pre-ticked unless the user saved something. The
// Continue here also runs the first `/generate` (synchronous, ~20 s budget)
// and lands on review — or on an honest shortfall when nothing came back.
//
// Trades-stack screen → no local feedback FAB (RootNav's global mount, #188).

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;
type Pos = (typeof POSITIONS)[number];
const POS_NAME: Record<Pos, string> = { QB: 'Quarterback', RB: 'Running back', WR: 'Wide receiver', TE: 'Tight end' };

export const SHORTFALL_COPY: Record<ShortfallReason, string> = {
  insufficient_likes: 'Not enough liked offers to build independent packages.',
  overlapping_sells: 'The offers we found reuse the same outgoing assets, so they can’t run side by side.',
  competing_incoming: 'Several offers bring back the same asset; only one could complete.',
  no_return_supply: 'No league mate can send back what this plan is asking for.',
  recovery_unresolved: 'We couldn’t find an offer that recovers your own first yet.',
  roster_limitation: 'The combined trades would leave your roster over capacity or without a legal lineup.',
  stale_ownership: 'Rosters changed since your pool was set. Reload and check your pool.',
  budget_restriction: 'Your pick budget is too tight for the packages we found.',
  search_exhausted: 'We searched every combination in your pool and found nothing new.',
};

function errorCopy(e: unknown): string {
  if (e instanceof ApiError) {
    const code = (e.body as any)?.error;
    if (code === 'feature_disabled') return 'Team overhaul isn’t available right now.';
    if (code === 'stale_revision') return 'This plan changed elsewhere. Reload and try again.';
    if (code === 'not_found') return 'This overhaul no longer exists.';
    if (e.isTimeout) return 'Finding trade ideas took too long. Try again — the search picks up where it stopped.';
    if (typeof code === 'string') return `Couldn’t continue (${code}).`;
  }
  return 'Couldn’t continue. Check your connection and try again.';
}

export default function OverhaulTargetsScreen({ navigation, route }: any) {
  const overhaulId: string = route?.params?.overhaulId ?? '';
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || '';
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ['overhaul', overhaulId],
    queryFn: () => getOverhaul(overhaulId),
    enabled: !!overhaulId,
  });
  const view = q.data;
  const outlook = view?.settings.outlook ?? null;

  const [picked, setPicked] = useState<Set<Pos> | null>(null);
  const [phase, setPhase] = useState<'idle' | 'saving' | 'generating'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [shortfall, setShortfall] = useState<ShortfallReason | null>(null);

  useEffect(() => {
    if (!view || picked !== null) return;
    const saved = view.settings.preferred_positions.filter((p): p is Pos => (POSITIONS as readonly string[]).includes(p));
    setPicked(new Set(saved));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const toggle = (p: Pos) => {
    setPicked((prev) => {
      const next = new Set(prev ?? []);
      if (next.has(p)) next.delete(p); else next.add(p);
      return next;
    });
  };

  const hint = outlook === 'push_all_in'
    ? 'Recommended: RB and WR — the positions that most often move a contender this season.'
    : outlook === 'blow_it_up'
      ? 'Recommended: no position preference. Your return mix already asks for picks and youth.'
      : null;

  const onContinue = async () => {
    if (!view || !picked || phase !== 'idle') return;
    setError(null);
    setShortfall(null);
    const settings = { preferred_positions: [...picked] };
    const put = (revision: number) => updateOverhaulSettings(overhaulId, { revision, settings });
    try {
      setPhase('saving');
      let next: OverhaulView;
      try {
        next = await put(view.revision);
      } catch (e) {
        if (e instanceof ApiError && (e.body as any)?.error === 'stale_revision') {
          const fresh = await getOverhaul(overhaulId);
          next = await put(fresh.revision);
        } else {
          throw e;
        }
      }
      qc.setQueryData(['overhaul', overhaulId], next);

      setPhase('generating');
      const gen = await generateOffers(overhaulId, { revision: next.revision });
      qc.invalidateQueries({ queryKey: ['overhaul', overhaulId] });
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
      if (gen.offers.length === 0) {
        setShortfall(gen.generation.shortfall_reason ?? 'search_exhausted');
        return;
      }
      navigation.navigate('OverhaulReview' as never, { overhaulId } as never);
    } catch (e) {
      setError(errorCopy(e));
    } finally {
      setPhase('idle');
    }
  };

  if (q.isLoading || !view || !picked) {
    return (
      <View style={[styles.screen, styles.center]}>
        {q.isError
          ? <ChalkText style={styles.error}>{errorCopy(q.error)}</ChalkText>
          : <ActivityIndicator color={ice.base} />}
      </View>
    );
  }

  const busy = phase !== 'idle';

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <ChalkText style={styles.kicker}>Team overhaul · 03</ChalkText>
        <ChalkText variant="heading" style={styles.h1}>What do you want back?</ChalkText>
        <ChalkText style={styles.lede}>
          Optional. Choose where to focus your returns, or leave it open.
        </ChalkText>

        {hint ? (
          <View style={styles.hintBox}>
            <ChalkText style={styles.hintKicker}>Suggested direction</ChalkText>
            <ChalkText style={styles.hintBody}>{hint}</ChalkText>
          </View>
        ) : null}

        <View style={styles.grid}>
          {POSITIONS.map((p) => {
            const on = picked.has(p);
            return (
              <Pressable
                key={p}
                testID={`overhaul.target.${p}`}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={POS_NAME[p]}
                onPress={() => toggle(p)}
                style={({ pressed }) => [styles.chip, on && styles.chipOn, pressed && { backgroundColor: ink.ink3 }]}
              >
                <View style={styles.chipTop}>
                  <PositionBadge pos={p} />
                  <View style={[styles.tick, on && styles.tickOn]} />
                </View>
                <ChalkText style={styles.chipName}>{POS_NAME[p]}</ChalkText>
              </Pressable>
            );
          })}
        </View>

        <ChalkText style={styles.note}>
          Preferences guide the roadmap; strong offers at other positions can still appear.
        </ChalkText>
        {picked.size === 0 ? (
          <ChalkText style={styles.note}>
            <ChalkText style={styles.noteStrong}>No position preference. </ChalkText>
            We’ll use your outlook and team needs to suggest returns.
          </ChalkText>
        ) : null}

        {view.recovery.applicable && view.recovery.state === 'missing_with_known_holder' ? (
          <View style={styles.recovery}>
            <ChalkText style={styles.recoveryTitle}>
              {`Priority 1: your ${view.recovery.season ?? 'next-season'} first.`}
            </ChalkText>
            <ChalkText style={styles.recoveryBody}>
              {`We’ll look for a recovery offer with ${view.recovery.holder_username ?? 'its holder'}, whatever you choose here.`}
            </ChalkText>
          </View>
        ) : null}

        {phase === 'generating' ? (
          <View style={styles.progress}>
            <ActivityIndicator color={ice.base} />
            <ChalkText style={styles.progressText}>Finding trade ideas… this can take about 20 seconds.</ChalkText>
          </View>
        ) : null}

        {shortfall ? (
          <View style={styles.shortfall}>
            <ChalkText style={styles.shortfallTitle}>No trade ideas yet</ChalkText>
            <ChalkText style={styles.shortfallBody}>{SHORTFALL_COPY[shortfall]}</ChalkText>
            <Button
              label="Change my pool"
              variant="secondary"
              onPress={() => navigation.navigate('OverhaulAssets' as never, { overhaulId } as never)}
            />
          </View>
        ) : null}

        {error ? <ChalkText style={styles.error}>{error}</ChalkText> : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          testID="overhaul.continue"
          label={phase === 'generating' ? 'Finding trade ideas…' : 'Continue'}
          onPress={onContinue}
          disabled={busy}
          loading={phase === 'saving'}
        />
        <Pressable
          accessibilityRole="button"
          onPress={() => picked.size > 0 && setPicked(new Set())}
          disabled={busy || picked.size === 0}
          style={styles.clear}
        >
          <ChalkText style={[styles.clearText, picked.size === 0 && { color: chalk.faint }]}>Clear preferences</ChalkText>
        </Pressable>
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
  hintBox: {
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.line, borderRadius: radii.md,
    padding: space.md, gap: space.xs,
  },
  hintKicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  hintBody: { ...type.bodySm, color: chalk.base },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    flexBasis: '47%', flexGrow: 1, backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.lineStrongA11y,
    borderRadius: radii.md, padding: space.md, gap: space.sm, minHeight: 72,
  },
  chipOn: { borderColor: ice.base },
  chipTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  chipName: { ...type.bodySm, color: chalk.dim },
  tick: { width: 20, height: 20, borderRadius: radii.xs, borderWidth: 1, borderColor: ink.lineStrongA11y },
  tickOn: { backgroundColor: ice.base, borderColor: ice.base },
  note: { ...type.bodySm, color: chalk.dim },
  noteStrong: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  recovery: { borderLeftWidth: 3, borderLeftColor: ink.lineStrongA11y, paddingLeft: space.md, gap: 2 },
  recoveryTitle: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  recoveryBody: { ...type.bodySm, color: chalk.dim },
  progress: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  progressText: { ...type.bodySm, color: chalk.base, flex: 1 },
  shortfall: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.md, padding: space.md, gap: space.sm,
    backgroundColor: ink.ink1,
  },
  shortfallTitle: { ...type.title, color: chalk.base },
  shortfallBody: { ...type.bodySm, color: chalk.dim },
  error: { ...type.bodySm, color: semantic.neg },
  footer: {
    padding: space.lg, borderTopWidth: 1, borderTopColor: ink.line, backgroundColor: ink.ink0, gap: space.sm,
  },
  clear: { alignItems: 'center', paddingVertical: space.sm },
  clearText: { ...type.bodySm, color: ice.base },
});
