import React, { useEffect, useRef, useState } from 'react';
import { View, ScrollView, Pressable, StyleSheet } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button } from '../components/chalkline';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { ApiError } from '../api/client';
import { uuidv4 } from '../api/_queue';
import {
  createOverhaul, getOverhaul, updateOverhaulSettings, type OverhaulOutlook,
} from '../api/overhaul';

// Team overhaul step 1 (BUILD-CONTRACT §9, PRODUCT-SPEC R1) — the outlook.
// Exactly two decisive directions; no intermediate outlook. The choice lives
// on the OVERHAUL row, never on league_preferences: this screen imports no
// preference writer, by contract (tests/check-team-overhaul.js).
//
// Trades-stack screen → no local feedback FAB (RootNav's global mount, #188).

const OUTLOOK_CARDS: { key: OverhaulOutlook; title: string; bias: string; body: string }[] = [
  {
    key: 'push_all_in',
    title: 'Push all in',
    body: 'Turn picks and future upside into a stronger team for this season.',
    bias: 'Spend picks and depth to win now',
  },
  {
    key: 'blow_it_up',
    title: 'Blow it up',
    body: 'Move production for younger building blocks and draft capital.',
    bias: 'Sell production for picks and youth',
  },
];

const STEPS = [
  'Choose the assets you’re open to moving.',
  'Like or pass on trade ideas.',
  'Choose a plan with 4–5 independent trades.',
  'Rank alternatives and track your offers.',
];

function errorCopy(e: unknown): string {
  if (e instanceof ApiError) {
    const code = (e.body as any)?.error;
    if (code === 'feature_disabled') return 'Team overhaul isn’t available right now.';
    if (code === 'active_sends_exist') return 'You already have offers out in an active overhaul. Resume that one instead.';
    if (code === 'not_found') return 'This overhaul no longer exists.';
    if (typeof code === 'string') return `Couldn’t save your outlook (${code}).`;
  }
  return 'Couldn’t save your outlook. Check your connection and try again.';
}

export default function OverhaulOutlookScreen({ navigation, route }: any) {
  const existingId: string | undefined = route?.params?.overhaulId;
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || '';
  const qc = useQueryClient();

  // Idempotency: one client_key per screen mount, so a retry after a dropped
  // response lands on the same overhaul rather than minting a second one.
  const clientKey = useRef(uuidv4());

  const existingQ = useQuery({
    queryKey: ['overhaul', existingId],
    queryFn: () => getOverhaul(existingId!),
    enabled: !!existingId,
  });

  const [outlook, setOutlook] = useState<OverhaulOutlook | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeId, setResumeId] = useState<string | null>(null);

  useEffect(() => {
    const saved = existingQ.data?.settings.outlook;
    if (saved && outlook === null) setOutlook(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingQ.data]);

  const onContinue = async () => {
    if (!outlook || busy) return;
    setBusy(true);
    setError(null);
    setResumeId(null);
    try {
      let id = existingId;
      let revision = existingQ.data?.revision ?? 1;
      if (!id) {
        const created = await createOverhaul({ league_id: leagueId, client_key: clientKey.current });
        id = created.overhaul_id;
        revision = created.revision;
      }
      const view = await updateOverhaulSettings(id, { revision, settings: { outlook } });
      qc.setQueryData(['overhaul', id], view);
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
      navigation.navigate('OverhaulAssets' as never, { overhaulId: id } as never);
    } catch (e) {
      setError(errorCopy(e));
      if (e instanceof ApiError && (e.body as any)?.error === 'active_sends_exist') {
        const other = (e.body as any)?.overhaul_id;
        if (typeof other === 'string') setResumeId(other);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <ChalkText style={styles.kicker}>Team overhaul · 01</ChalkText>
        <ChalkText variant="heading" style={styles.h1}>What are you trying to do?</ChalkText>
        <ChalkText style={styles.lede}>Choose a direction for a major roster reset.</ChalkText>

        <View style={styles.cards}>
          {OUTLOOK_CARDS.map((o) => {
            const sel = outlook === o.key;
            return (
              <Pressable
                key={o.key}
                testID={`overhaul.outlook.${o.key}`}
                accessibilityRole="radio"
                accessibilityState={{ selected: sel, checked: sel }}
                accessibilityLabel={o.title}
                accessibilityHint={o.bias}
                onPress={() => setOutlook(o.key)}
                style={({ pressed }) => [
                  styles.outCard,
                  sel && styles.outCardSel,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <View style={styles.outCardTop}>
                  <ChalkText style={styles.outCardTitle}>{o.title}</ChalkText>
                  <View style={[styles.tick, sel && styles.tickOn]} />
                </View>
                <ChalkText style={[styles.outCardBody, sel && { color: chalk.base }]}>{o.body}</ChalkText>
                <ChalkText style={styles.outCardBias}>{o.bias}</ChalkText>
              </Pressable>
            );
          })}
        </View>

        <ChalkText style={styles.isolation}>
          Separate from your regular trade-finder settings.
        </ChalkText>

        <View style={styles.plan}>
          <ChalkText style={styles.planHdr}>How your plan comes together</ChalkText>
          {STEPS.map((s, i) => (
            <View key={s} style={styles.planRow}>
              <ChalkText style={styles.planNum}>{`0${i + 1}`}</ChalkText>
              <ChalkText style={styles.planText}>{s}</ChalkText>
            </View>
          ))}
        </View>

        {error ? <ChalkText style={styles.error}>{error}</ChalkText> : null}
        {resumeId ? (
          <Button
            label="Resume that overhaul"
            variant="secondary"
            onPress={() => navigation.navigate('OverhaulPlan' as never, { overhaulId: resumeId } as never)}
          />
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          testID="overhaul.continue"
          label="Choose my trade pool"
          onPress={onContinue}
          disabled={!outlook || !leagueId}
          loading={busy}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: ink.ink0 },
  content: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },
  kicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  h1: { color: chalk.base },
  lede: { ...type.body, color: chalk.dim },
  cards: { gap: space.sm, marginTop: space.xs },
  outCard: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.md,
    backgroundColor: ink.ink1, padding: space.lg, gap: space.xs,
  },
  outCardSel: { borderColor: ice.base },
  outCardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  outCardTitle: { ...type.title, color: chalk.base, fontFamily: fonts.displayBold, textTransform: 'uppercase' },
  tick: { width: 18, height: 18, borderRadius: radii.xs, borderWidth: 1, borderColor: ink.lineStrongA11y },
  tickOn: { backgroundColor: ice.base, borderColor: ice.base },
  outCardBody: { ...type.bodySm, color: chalk.dim },
  outCardBias: { ...type.bodySm, color: chalk.dim, fontFamily: fonts.data, marginTop: 2 },
  isolation: { ...type.bodySm, color: chalk.faint },
  plan: {
    borderWidth: 1, borderColor: ink.line, borderRadius: radii.md, padding: space.md, gap: space.sm,
  },
  planHdr: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  planRow: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  planNum: { ...type.bodySm, color: chalk.base, fontFamily: fonts.data, width: 24 },
  planText: { ...type.bodySm, color: chalk.dim, flex: 1 },
  error: { ...type.bodySm, color: semantic.neg },
  footer: { padding: space.lg, borderTopWidth: 1, borderTopColor: ink.line, backgroundColor: ink.ink0 },
});
