import React, { useEffect, useMemo, useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, Badge, PositionBadge } from '../components/chalkline';
import { ink, chalk, ice, flare, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { ApiError } from '../api/client';
import {
  getOverhaul, updateOverhaulSettings,
  type AssetView, type OverhaulSettings, type OverhaulView, type RebuildReturn,
  type RecoveryRequirement,
} from '../api/overhaul';

// Team overhaul step 2 (BUILD-CONTRACT §9, PRODUCT-SPEC R2/R3) — the eligible
// pool. The whole roster by position plus owned picks; the user's selection is
// PERMISSION to move, not a commitment (R2.3/R2.5). Push all in adds a pick
// budget; Blow it up adds the return mix and the own-first recovery banner,
// whose copy never claims a draft slot (D2).
//
// Trades-stack screen → no local feedback FAB (RootNav's global mount, #188).

const POS_GROUPS = ['QB', 'RB', 'WR', 'TE'] as const;
type PosKey = (typeof POS_GROUPS)[number];
const isPos = (p: string): p is PosKey => (POS_GROUPS as readonly string[]).includes(p);

const RETURN_MIX: { key: RebuildReturn; label: string }[] = [
  { key: 'picks', label: 'Picks' },
  { key: 'young_players', label: 'Young players' },
  { key: 'mixed', label: 'Mixed' },
];

/** Season of an owned pick: from its label ("2027 1st") or its FTF id
 *  (`{league}_{season}_{round}_{roster}`). Null when neither carries one. */
function pickSeason(a: AssetView): number | null {
  const fromLabel = a.label?.match(/\b(20\d{2})\b/);
  if (fromLabel) return Number(fromLabel[1]);
  const fromId = a.id.split('_').find((t) => /^20\d{2}$/.test(t));
  return fromId ? Number(fromId) : null;
}

function recoveryCopy(r: RecoveryRequirement): { tone: 'info' | 'warn' | 'neutral'; title: string; body: string; extra?: string } | null {
  if (!r.applicable) return null;
  const season = r.season ?? 'next-season';
  switch (r.state) {
    case 'owned':
      return {
        tone: 'info',
        title: `You own your ${season} first`,
        body: `Moving production can improve the draft position of your own ${season} first (depends on your league's draft-order rules).`,
      };
    case 'missing_with_known_holder':
      return {
        tone: 'warn',
        title: `Your ${season} first is elsewhere`,
        body: `You don't own your ${season} first — ${r.holder_username ?? 'another team'} has it. Reducing production won't improve a pick you don't own.`,
        extra: 'We’ll include an offer to recover that exact pick, marked Priority 1.',
      };
    case 'not_yet_available':
      return {
        tone: 'neutral',
        title: `${season} picks not published yet`,
        body: `Your league hasn't published ${season} picks, so we can't tell who holds your first. Recovery guidance will appear once they exist.`,
      };
    case 'unsupported':
      return {
        tone: 'neutral',
        title: 'Pick ownership unavailable',
        body: 'This league platform doesn’t expose pick ownership here, so we can’t check your first.',
      };
    default:
      return {
        tone: 'neutral',
        title: `Can’t confirm your ${season} first`,
        body: 'We couldn’t read who holds your first. Reducing production only helps a pick you own.',
      };
  }
}

function errorCopy(e: unknown): string {
  if (e instanceof ApiError) {
    const code = (e.body as any)?.error;
    if (code === 'asset_not_owned') return 'One of the selected assets is no longer on your roster. Reload and try again.';
    if (code === 'generic_pick_not_allowed') return 'Only picks you own can be in the pool.';
    if (code === 'stale_revision') return 'This plan changed elsewhere. Reload and try again.';
    if (code === 'not_found') return 'This overhaul no longer exists.';
    if (typeof code === 'string') return `Couldn’t save your pool (${code}).`;
  }
  return 'Couldn’t save your pool. Check your connection and try again.';
}

export default function OverhaulAssetsScreen({ navigation, route }: any) {
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

  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [maxPicks, setMaxPicks] = useState(3);
  const [maxRound, setMaxRound] = useState(2);
  const [returnMix, setReturnMix] = useState<RebuildReturn>('mixed');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seed local state ONCE from the loaded view (saved pool, else the
  // recommendations). Later refetches never clobber an in-progress edit.
  useEffect(() => {
    if (!view || selected !== null) return;
    const saved = view.settings.eligible_asset_ids;
    const init = saved.length > 0
      ? saved
      : view.eligible_assets.filter((a) => a.recommended).map((a) => a.id);
    setSelected(new Set(init));
    if (view.settings.pick_budget) {
      setMaxPicks(view.settings.pick_budget.max_picks);
      setMaxRound(view.settings.pick_budget.max_round);
    }
    if (view.settings.rebuild_return) setReturnMix(view.settings.rebuild_return);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const groups = useMemo(() => {
    const byPos: Record<PosKey | 'other', AssetView[]> = { QB: [], RB: [], WR: [], TE: [], other: [] };
    const picks: AssetView[] = [];
    for (const a of view?.eligible_assets ?? []) {
      if (a.kind === 'pick') picks.push(a);
      else if (isPos(a.position)) byPos[a.position].push(a);
      else byPos.other.push(a);
    }
    return { byPos, picks };
  }, [view]);

  const pickSeasons = useMemo(() => {
    const s = new Set<number>();
    for (const p of groups.picks) { const y = pickSeason(p); if (y) s.add(y); }
    return [...s].sort((a, b) => a - b);
  }, [groups.picks]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev ?? []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const restore = () => {
    if (!view) return;
    setSelected(new Set(view.eligible_assets.filter((a) => a.recommended).map((a) => a.id)));
  };

  const onContinue = async () => {
    if (!view || !selected || busy) return;
    setBusy(true);
    setError(null);
    const settings: Partial<OverhaulSettings> = { eligible_asset_ids: [...selected] };
    if (outlook === 'push_all_in') {
      settings.pick_budget = { max_picks: maxPicks, max_round: maxRound, seasons: pickSeasons };
    } else if (outlook === 'blow_it_up') {
      settings.rebuild_return = returnMix;
    }
    const put = (revision: number) => updateOverhaulSettings(overhaulId, { revision, settings });
    try {
      let next: OverhaulView;
      try {
        next = await put(view.revision);
      } catch (e) {
        // One retry on a revision race: refetch the row, PUT against its revision.
        if (e instanceof ApiError && (e.body as any)?.error === 'stale_revision') {
          const fresh = await getOverhaul(overhaulId);
          next = await put(fresh.revision);
        } else {
          throw e;
        }
      }
      qc.setQueryData(['overhaul', overhaulId], next);
      qc.invalidateQueries({ queryKey: ['overhaul', leagueId] });
      navigation.navigate('OverhaulTargets' as never, { overhaulId } as never);
    } catch (e) {
      setError(errorCopy(e));
    } finally {
      setBusy(false);
    }
  };

  if (q.isLoading || !view || !selected) {
    return (
      <View style={[styles.screen, styles.center]}>
        {q.isError
          ? <ChalkText style={styles.error}>{errorCopy(q.error)}</ChalkText>
          : <ActivityIndicator color={ice.base} />}
      </View>
    );
  }

  const recovery = outlook === 'blow_it_up' ? recoveryCopy(view.recovery) : null;
  const count = selected.size;

  const renderAsset = (a: AssetView) => {
    const on = selected.has(a.id);
    const isPick = a.kind === 'pick';
    const meta = isPick
      ? (a.reason ?? '')
      : [a.team, a.age != null ? `${a.age}y` : null, `value ${Math.round(a.value)}`].filter(Boolean).join(' · ');
    return (
      <Pressable
        key={a.id}
        testID={`overhaul.asset.${a.id}`}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: on }}
        accessibilityLabel={isPick ? (a.label ?? a.name) : a.name}
        onPress={() => toggle(a.id)}
        style={({ pressed }) => [styles.row, on && styles.rowOn, pressed && { backgroundColor: ink.ink3 }]}
      >
        {isPick
          ? <Badge label="PICK" />
          : isPos(a.position) ? <PositionBadge pos={a.position} /> : <Badge label={a.position} />}
        <View style={styles.rowText}>
          <ChalkText style={styles.rowName}>{isPick ? (a.label ?? a.name) : a.name}</ChalkText>
          {meta ? <ChalkText style={styles.rowMeta}>{meta}</ChalkText> : null}
          {a.recommended ? (
            <ChalkText style={styles.rowRec}>
              {`Recommended${!isPick && a.reason ? ` · ${a.reason}` : ''}`}
            </ChalkText>
          ) : null}
        </View>
        <View style={[styles.tick, on && styles.tickOn]} />
      </Pressable>
    );
  };

  const section = (title: string, items: AssetView[]) => items.length === 0 ? null : (
    <View key={title} style={styles.section}>
      <View style={styles.sectionHdr}>
        <View style={styles.sectionRail} />
        <ChalkText style={styles.sectionTitle}>{title}</ChalkText>
        <ChalkText style={styles.sectionCount}>{items.length}</ChalkText>
      </View>
      {items.map(renderAsset)}
    </View>
  );

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <ChalkText style={styles.kicker}>Team overhaul · 02</ChalkText>
        <ChalkText variant="heading" style={styles.h1}>Build your trade pool</ChalkText>
        <ChalkText style={styles.lede}>
          Selected assets are eligible to move — not all of them have to.
        </ChalkText>

        <View style={styles.countBox}>
          <ChalkText style={styles.countNum}>{`${count} ${count === 1 ? 'asset' : 'assets'} available to trade`}</ChalkText>
          <ChalkText style={styles.countSub}>Your final plan may use only part of this pool.</ChalkText>
        </View>

        {recovery ? (
          <View style={[styles.banner, recovery.tone === 'warn' && styles.bannerWarn]}>
            <ChalkText style={[styles.bannerKicker, recovery.tone === 'warn' && { color: flare.base }]}>
              {recovery.title}
            </ChalkText>
            <ChalkText style={styles.bannerBody}>{recovery.body}</ChalkText>
            {recovery.extra ? (
              <ChalkText style={styles.bannerBody}>
                <ChalkText style={styles.bannerStrong}>Priority 1: Recover your first. </ChalkText>
                {recovery.extra}
              </ChalkText>
            ) : null}
          </View>
        ) : null}

        {outlook === 'push_all_in' ? (
          <View style={styles.control}>
            <ChalkText style={styles.controlHdr}>Pick budget</ChalkText>
            <Stepper label="Max picks to spend" value={maxPicks} min={1} max={6} onChange={setMaxPicks} />
            <Stepper label="Latest round" value={maxRound} min={1} max={3} onChange={setMaxRound} />
            <ChalkText style={styles.controlNote}>
              {pickSeasons.length > 0
                ? `Seasons: ${pickSeasons.join(', ')}. Only picks you select below can move.`
                : 'No owned picks found for this league.'}
            </ChalkText>
          </View>
        ) : null}

        {outlook === 'blow_it_up' ? (
          <View style={styles.control}>
            <ChalkText style={styles.controlHdr}>Return mix</ChalkText>
            <View style={styles.segment}>
              {RETURN_MIX.map((m) => {
                const on = returnMix === m.key;
                return (
                  <Pressable
                    key={m.key}
                    testID={`overhaul.return-mix.${m.key}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on, checked: on }}
                    onPress={() => setReturnMix(m.key)}
                    style={[styles.segBtn, on && styles.segBtnOn]}
                  >
                    <ChalkText style={[styles.segText, on && { color: ice.base }]}>{m.label}</ChalkText>
                  </Pressable>
                );
              })}
            </View>
            <ChalkText style={styles.controlNote}>A trade can return picks only.</ChalkText>
          </View>
        ) : null}

        <View style={styles.actions}>
          <Button label="Restore suggestions" variant="secondary" compact onPress={restore} style={styles.half} />
          <Button label="Clear selection" variant="secondary" compact onPress={() => setSelected(new Set())} style={styles.half} />
        </View>

        {POS_GROUPS.map((p) => section(p, groups.byPos[p]))}
        {section('Other', groups.byPos.other)}
        {section('Draft picks', groups.picks)}

        {error ? <ChalkText style={styles.error}>{error}</ChalkText> : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          testID="overhaul.continue"
          label="Continue"
          onPress={onContinue}
          disabled={count === 0}
          loading={busy}
        />
      </View>
    </View>
  );
}

function Stepper({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void;
}) {
  return (
    <View style={styles.stepper}>
      <ChalkText style={styles.stepperLabel}>{label}</ChalkText>
      <View style={styles.stepperCtl}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Decrease ${label}`}
          disabled={value <= min}
          onPress={() => onChange(Math.max(min, value - 1))}
          style={[styles.stepBtn, value <= min && styles.stepBtnOff]}
        >
          <ChalkText style={styles.stepBtnText}>−</ChalkText>
        </Pressable>
        <ChalkText style={styles.stepVal}>{value}</ChalkText>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Increase ${label}`}
          disabled={value >= max}
          onPress={() => onChange(Math.min(max, value + 1))}
          style={[styles.stepBtn, value >= max && styles.stepBtnOff]}
        >
          <ChalkText style={styles.stepBtnText}>+</ChalkText>
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
  countBox: {
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.line, borderRadius: radii.md,
    padding: space.md, gap: 2,
  },
  countNum: { ...type.title, color: chalk.base },
  countSub: { ...type.bodySm, color: chalk.dim },
  banner: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.md, padding: space.md, gap: space.xs,
    backgroundColor: ink.ink1,
  },
  bannerWarn: { borderColor: flare.base },
  bannerKicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  bannerBody: { ...type.bodySm, color: chalk.base },
  bannerStrong: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  control: {
    borderWidth: 1, borderColor: ink.line, borderRadius: radii.md, padding: space.md, gap: space.sm,
    backgroundColor: ink.ink1,
  },
  controlHdr: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  controlNote: { ...type.bodySm, color: chalk.faint },
  stepper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepperLabel: { ...type.bodySm, color: chalk.base },
  stepperCtl: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  stepBtn: {
    width: 36, height: 36, borderRadius: radii.sm, borderWidth: 1, borderColor: ink.lineStrongA11y,
    alignItems: 'center', justifyContent: 'center',
  },
  stepBtnOff: { opacity: 0.4 },
  stepBtnText: { ...type.title, color: chalk.base },
  stepVal: { ...type.title, color: chalk.base, fontFamily: fonts.data, minWidth: 24, textAlign: 'center' },
  segment: { flexDirection: 'row', gap: space.xs },
  segBtn: {
    flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: radii.sm,
    borderWidth: 1, borderColor: ink.lineStrongA11y,
  },
  segBtnOn: { borderColor: ice.base, backgroundColor: ink.ink2 },
  segText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  actions: { flexDirection: 'row', gap: space.sm },
  half: { flex: 1 },
  section: { gap: space.xs },
  sectionHdr: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: space.xs },
  sectionRail: { width: 3, height: 14, backgroundColor: ice.base },
  sectionTitle: { ...type.label, color: chalk.base, flex: 1, letterSpacing: 1, textTransform: 'uppercase' },
  sectionCount: { ...type.label, color: chalk.dim, fontFamily: fonts.data },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.line, borderRadius: radii.md,
    padding: space.md, minHeight: 56,
  },
  rowOn: { borderColor: ice.base },
  rowText: { flex: 1, gap: 1 },
  rowName: { ...type.body, color: chalk.base, fontFamily: fonts.uiSemi },
  rowMeta: { ...type.bodySm, color: chalk.dim },
  // Not flare: flare is reserved for the Priority-1 recovery highlight above.
  rowRec: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi, fontSize: 11, lineHeight: 15 },
  tick: { width: 20, height: 20, borderRadius: radii.xs, borderWidth: 1, borderColor: ink.lineStrongA11y },
  tickOn: { backgroundColor: ice.base, borderColor: ice.base },
  error: { ...type.bodySm, color: semantic.neg },
  footer: { padding: space.lg, borderTopWidth: 1, borderTopColor: ink.line, backgroundColor: ink.ink0 },
});
