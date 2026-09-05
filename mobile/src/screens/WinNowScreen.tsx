import React, { useEffect, useRef, useState } from 'react';
import { View, ScrollView, Pressable, TextInput, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useIsFocused } from '@react-navigation/native';
import Text from '../components/chalkline/Text';
import FeedbackFAB from '../components/FeedbackFAB';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { getSeasonProjections, searchWinNow, getWinNowJob, evaluateWinNow, decideWinNow } from '../api/winNow';
import type { SeasonProjection, SeasonTeam, WinNowAsset, WinNowScenario, WinNowObjective, WinNowEvaluation, SeasonMeta } from '../shared/types';
import { probability, numeric, impact, nextThree, sourceReceipt, seasonStale, projectedStandings, samplingEvidence } from '../utils/winNow';
import { ink, chalk, ice, space, radii, type } from '../theme/chalkline';

function Action({label, onPress, disabled = false, selected = false, primary = false, id}: {
  label: string; onPress: () => void; disabled?: boolean; selected?: boolean; primary?: boolean; id: string;
}) {
  return <Pressable testID={id} accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{disabled, selected}} disabled={disabled} onPress={onPress}
    style={[s.button, selected && s.selected, primary && s.primary, disabled && s.disabled]}>
    <Text style={[s.buttonText, selected && s.selectedText, primary && s.primaryText]}>{label}</Text>
  </Pressable>;
}
function Metrics({before, after, title}: {before: SeasonTeam; after: SeasonTeam; title: boolean}) {
  return <View style={s.metrics}>
    <Text style={s.body}>Next matchup: {probability(before.next_matchup_win_probability)} → {probability(after.next_matchup_win_probability)} ({impact(before.next_matchup_win_probability, after.next_matchup_win_probability, true)})</Text>
    <Text style={s.body}>Next 3 weeks: {numeric(nextThree(before))} → {numeric(nextThree(after))} wins ({impact(nextThree(before), nextThree(after))})</Text>
    <Text style={s.body}>Remaining wins: {numeric(before.expected_remaining_wins)} → {numeric(after.expected_remaining_wins)} ({impact(before.expected_remaining_wins, after.expected_remaining_wins)})</Text>
    <Text style={s.body}>Final wins: {numeric(before.expected_wins)} → {numeric(after.expected_wins)} ({impact(before.expected_wins, after.expected_wins)})</Text>
    <Text style={s.body}>Make playoffs: {probability(before.playoff_probability)} → {probability(after.playoff_probability)} ({impact(before.playoff_probability, after.playoff_probability, true)})</Text>
    <Text style={s.body}>Bye: {probability(before.bye_probability)} → {probability(after.bye_probability)} ({impact(before.bye_probability, after.bye_probability, true)})</Text>
    {title && <Text style={s.body}>Championship: {probability(before.championship_probability)} → {probability(after.championship_probability)} ({impact(before.championship_probability, after.championship_probability, true)})</Text>}
  </View>;
}
function Evidence({trade, title, objective}: {trade: WinNowScenario; title: boolean; objective: WinNowObjective}) {
  const v = trade.valuation;
  return <>
    {(objective !== 'championship' || title) && <Text style={s.body}>{samplingEvidence(trade, objective)}</Text>}
    <Text variant="label">Your team · before → after</Text><Metrics before={trade.buyer.before} after={trade.buyer.after} title={title} />
    <Text variant="label">{trade.partner_username || 'Partner'} · before → after</Text><Metrics before={trade.partner.before} after={trade.partner.after} title={title} />
    <Text style={s.body}>Dynasty cost {numeric(v.buyer_dynasty_cost)} / budget {numeric(v.buyer_budget)}. Give-package loss {probability(v.buyer_package_loss_fraction)}.</Text>
    <Text style={s.body}>Market balance {probability(v.market_ratio)} · Partner dynasty gain {probability(v.partner_gain_fraction)}</Text>
    <Text style={s.body}>Partner evidence: {v.partner_basis?.replace(/_/g, ' ') || 'Market-based estimate'} · Confidence {probability(v.partner_confidence)} · Board coverage {probability(v.partner_coverage)}</Text>
    <Text style={s.body}>Partner intent: {trade.partner_intent || v.partner_intent || 'Unknown; no rebuild intent assumed'}</Text>
    {(trade.reasons || []).map((reason, i) => <Text key={i} style={s.body}>{reason}</Text>)}
  </>;
}
function errorCopy(error: unknown): string {
  const err = error as {message?: string; body?: {message?: string; reason?: string}};
  return err?.body?.message || err?.body?.reason?.replace(/_/g, ' ') || err?.message || 'Could not load Win Now. Please retry.';
}

export default function WinNowScreen() {
  const leagueId = useSession(state => state.league?.league_id);
  const userId = useSession(state => state.user?.user_id);
  return <WinNowContent key={`${userId}:${leagueId}`} leagueId={leagueId} />;
}
function WinNowContent({leagueId}: {leagueId?: string}) {
  const seasonOn = useFlag('outlook.season_projections');
  const searchOn = useFlag('trades.win_now');
  const titleFlag = useFlag('outlook.championship_probabilities');
  const focused = useIsFocused();
  const [baseline, setBaseline] = useState<SeasonProjection | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [objective, setObjective] = useState<WinNowObjective>('wins');
  const [budget, setBudget] = useState('3');
  const [fairness, setFairness] = useState('90');
  const [protectedIds, setProtectedIds] = useState<string[]>([]);
  const [trades, setTrades] = useState<WinNowScenario[] | null>(null);
  const [resultMeta, setResultMeta] = useState<SeasonMeta>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<WinNowScenario | null>(null);
  const [giveIds, setGiveIds] = useState<string[]>([]);
  const [receiveIds, setReceiveIds] = useState<string[]>([]);
  const [evaluation, setEvaluation] = useState<WinNowEvaluation | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const scroll = useRef<ScrollView>(null);
  const revealEditor = useRef(false);
  const epoch = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = () => {
    epoch.current += 1;
    controller.current?.abort();
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => {
    const request = new AbortController();
    let active = true;
    setBaseline(null); setLoadError(''); setLoading(false);
    if (seasonOn && leagueId && focused) {
      setLoading(true);
      getSeasonProjections(leagueId, request.signal).then(data => {
        if (active) setBaseline(data);
      }).catch(error => { if (active) setLoadError(errorCopy(error)); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; request.abort(); };
  }, [leagueId, seasonOn, focused, refresh]);
  // All asynchronous results are request-scoped. No shared dynasty cache.
  useEffect(() => {
    cancel(); setTrades(null); setResultMeta(undefined); setMessage(''); setBusy(false); setEditor(null); setEvaluation(null);
    return cancel;
  }, [leagueId, objective, budget, fairness, protectedIds, seasonOn, searchOn, titleFlag, focused, refresh]);
  const titleAvailable = titleFlag && baseline?.meta?.championship_available === true;
  useEffect(() => { if (!titleAvailable && objective === 'championship') setObjective('wins'); }, [titleAvailable, objective]);
  const stale = seasonStale(baseline?.meta) || seasonStale(resultMeta);
  // Expiring visible snapshots stop being current even without another tap.
  useEffect(() => {
    const now = Date.now();
    const future = [baseline?.meta?.expires_at, resultMeta?.expires_at, evaluation?.meta?.expires_at]
      .map(value => value ? Date.parse(value) : NaN).filter(value => Number.isFinite(value) && value > now);
    if (!focused || !future.length) return;
    const expiry = setTimeout(() => {
      cancel(); setBusy(false); setMessage('These projections are stale. Refresh season projections before continuing.');
    }, Math.min(Math.min(...future) - now + 10, 2_147_483_647));
    return () => clearTimeout(expiry);
  }, [baseline?.meta?.expires_at, resultMeta?.expires_at, evaluation?.meta?.expires_at, focused]);
  const available = seasonOn && baseline?.status === 'available' && !stale;
  const validBudget = budget.trim() !== '' && Number.isFinite(Number(budget)) && Number(budget) >= 0 && Number(budget) <= 10;
  const validFairness = fairness.trim() !== '' && Number.isFinite(Number(fairness)) && Number(fairness) >= 75 && Number(fairness) <= 100;
  const canSearch = available && searchOn && !!leagueId && validBudget && validFairness && (objective !== 'championship' || titleAvailable);
  const params = {league_id: leagueId || '', objective, max_dynasty_spend_pct: Number(budget), min_fairness: Number(fairness) / 100, protected_ids: protectedIds};
  const begin = () => { cancel(); controller.current = new AbortController(); setBusy(true); setMessage(''); return {id: epoch.current, signal: controller.current.signal}; };
  const current = (id: number) => id === epoch.current;
  const search = async () => {
    if (!canSearch || busy || seasonStale(baseline?.meta)) return;
    const request = begin(); setTrades(null); setEditor(null); setEvaluation(null);
    const startedAt = Date.now();
    const apply = async (job: Awaited<ReturnType<typeof searchWinNow>>): Promise<void> => {
      if (!current(request.id)) return;
      if (job.status === 'complete' && job.result) {
        setResultMeta(job.result.meta); setBusy(false);
        if (seasonStale(job.result.meta)) { setMessage('These projections are stale. Refresh season projections before searching.'); return; }
        setTrades(job.result.trades); return; // Preserve server ordering.
      }
      if (job.status === 'failed' || job.status === 'unavailable') {
        setBusy(false); setMessage(job.message || job.reason?.replace(/_/g, ' ') || 'Search unavailable. Please retry.'); return;
      }
      if (!job.job_id || Date.now() - startedAt >= 90_000) {
        setBusy(false); setMessage('Search has not finished. Try again when you are ready.'); return;
      }
      timer.current = setTimeout(async () => {
        if (!current(request.id)) return;
        try { await apply(await getWinNowJob(job.job_id!, request.signal)); }
        catch (error) { if (current(request.id)) { setBusy(false); setMessage(errorCopy(error)); } }
      }, 1500);
    };
    try { await apply(await searchWinNow(params, request.signal)); }
    catch (error) { if (current(request.id)) { setBusy(false); setMessage(errorCopy(error)); } }
  };
  const edit = (trade: WinNowScenario) => {
    revealEditor.current = true;
    cancel(); setBusy(false); setMessage(''); setEvaluation(null); setEditor(trade);
    setGiveIds(trade.give.map(asset => asset.id)); setReceiveIds(trade.receive.map(asset => asset.id));
  };
  const toggleAsset = (id: string, side: 'give' | 'receive') => {
    cancel(); setBusy(false); setEvaluation(null); setMessage('');
    const update = (ids: string[]) => ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id];
    if (side === 'give') setGiveIds(update); else setReceiveIds(update);
  };
  const evaluate = async () => {
    if (!editor || !canSearch || busy || !giveIds.length || !receiveIds.length || seasonStale(baseline?.meta)) return;
    const request = begin(); setEvaluation(null);
    try {
      const result = await evaluateWinNow({...params, partner_roster_id: editor.partner_roster_id, give_ids: giveIds, receive_ids: receiveIds}, request.signal);
      if (current(request.id)) { setEvaluation(result); setBusy(false); }
    } catch (error) { if (current(request.id)) { setBusy(false); setMessage(errorCopy(error)); } }
  };
  const decide = async (trade: WinNowScenario, decision: 'like' | 'pass') => {
    if (busy || !canSearch || seasonStale(resultMeta) || seasonStale(baseline?.meta)) return;
    const request = begin();
    try {
      const response = await decideWinNow(trade.scenario_id, decision, request.signal);
      if (current(request.id)) { setBusy(false); if (response.ok) setDecisions(prev => ({...prev, [trade.scenario_id]: decision})); else setMessage(response.message || response.reason?.replace(/_/g, ' ') || 'Decision was not saved. Please retry.'); }
    } catch (error) { if (current(request.id)) { setBusy(false); setMessage(errorCopy(error)); } }
  };
  const assets = baseline?.assets || [];
  const buyerAssets = assets.filter(asset => asset.owner_roster_id === baseline?.buyer_roster_id);
  const assetLabel = (asset: WinNowAsset) => `${asset.name} · ${asset.is_pick ? 'PICK' : asset.position || 'Player'}`;
  return <SafeAreaView style={s.safe} edges={['bottom']}>
    <ScrollView ref={scroll} contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled" onContentSizeChange={() => { if (revealEditor.current) { revealEditor.current = false; scroll.current?.scrollToEnd({animated: true}); } }}>
      <Text variant="heading">Season projections & Win Now</Text>
      <Text style={s.body}>Improve this season while keeping dynasty sacrifice within your limit. Forecasts are estimates, not guarantees.</Text>
      {!seasonOn || !leagueId ? <Text testID="win-now.disabled" style={s.body}>Season projections are not available for this league yet.</Text> : <>
        <Action id="win-now.refresh" label={loading ? 'Loading season projections…' : 'Refresh season projections'} onPress={() => setRefresh(n => n + 1)} disabled={loading} />
        {!!loadError && <Text accessibilityRole="alert" style={s.body}>{loadError}</Text>}
        {baseline && <Text testID="win-now.source" style={s.caption}>{sourceReceipt(baseline.meta)}</Text>}
        {baseline?.status === 'unavailable' && <Text testID="win-now.unavailable" style={s.body}>{baseline.message || baseline.reason?.replace(/_/g, ' ') || 'This league format or forecast source is not supported yet.'}</Text>}
        {stale && <Text testID="win-now.stale" style={s.body}>These projections are stale. Refresh to get a supported snapshot before searching or evaluating.</Text>}
        {available && <>
          <View style={s.card}>
            <Text variant="heading">Projected standings</Text>
            {projectedStandings(baseline?.teams || []).map(team => <View key={team.roster_id} style={s.standing}>
              <Text style={s.label}>Avg finish {numeric(team.projected_seed)} {team.username || `Team ${team.roster_id}`}{team.roster_id === baseline?.buyer_roster_id ? ' · You' : ''}</Text>
              <Text style={s.body}>W–L–T {numeric(team.expected_wins)}–{numeric(team.expected_losses)}–{numeric(team.expected_ties)} · Playoffs {probability(team.playoff_probability)} · Bye {probability(team.bye_probability)}</Text>
              {!!team.finish_distribution && <Text style={s.caption}>Finish: {Object.entries(team.finish_distribution).map(([seed, chance]) => `#${seed} ${probability(chance)}`).join(' · ')}</Text>}
              {titleAvailable && <Text style={s.body}>Championship {probability(team.championship_probability)}</Text>}
            </View>)}
          </View>
          {!searchOn ? <Text style={s.body}>Win Now trade search is not available yet.</Text> : <>
            <Text variant="heading">Choose your priority</Text>
            <View style={s.row}>{(['wins', 'playoffs', ...(titleAvailable ? ['championship'] : [])] as WinNowObjective[]).map(value => <Action key={value} id={`win-now.objective.${value}`} label={{wins: 'Next 3 weeks', playoffs: 'Make playoffs', championship: 'Championship'}[value]} selected={objective === value} onPress={() => setObjective(value)} />)}</View>
            {!titleAvailable && <Text style={s.caption}>Championship priority is unavailable until the title model is validated.</Text>}
            <Text style={s.label}>Maximum dynasty sacrifice (0–10%)</Text>
            <TextInput testID="win-now.budget" accessibilityLabel="Maximum dynasty sacrifice percent" value={budget} onChangeText={setBudget} keyboardType="decimal-pad" style={s.input} />
            <Text style={s.caption}>Percent of your fixed baseline roster value. The denominator stays the same for every offer; this is not percent of the outgoing package.</Text>
            <Text style={s.label}>Minimum market balance (75–100%)</Text>
            <TextInput testID="win-now.fairness" accessibilityLabel="Minimum market balance percent" value={fairness} onChangeText={setFairness} keyboardType="decimal-pad" style={s.input} />
            <Text style={s.caption}>The server's policy floor also applies. Search never relaxes either limit.</Text>
            {(!validBudget || !validFairness) && <Text accessibilityRole="alert" style={s.body}>Enter a dynasty sacrifice from 0 to 10% and market balance from 75 to 100%.</Text>}
            {!!buyerAssets.length && <View style={s.card}><Text variant="label">Protect assets · never offer these</Text><View style={s.row}>{buyerAssets.map(asset => <Action key={asset.id} id={`win-now.protect.${asset.id}`} label={assetLabel(asset)} selected={protectedIds.includes(asset.id)} onPress={() => setProtectedIds(ids => ids.includes(asset.id) ? ids.filter(id => id !== asset.id) : [...ids, asset.id])} />)}</View></View>}
            <Action id="win-now.search" primary label={busy ? 'Working…' : 'Find Win Now trades'} onPress={search} disabled={busy || !canSearch} />
            {busy && <Action id="win-now.cancel" label="Cancel" onPress={() => { cancel(); setBusy(false); setMessage('Search cancelled. Change your limits or try again.'); }} />}
          </>}
        </>}
        {!!message && <Text testID="win-now.message" accessibilityRole="alert" style={s.body}>{message}</Text>}
        {trades?.length === 0 && <Text testID="win-now.empty" style={s.body}>No trades met your season gain, dynasty budget, fairness and partner-fit requirements. Change your limits or retry after projections update.</Text>}
        {available && searchOn && trades?.map((trade, i) => <View key={trade.scenario_id} style={s.card} testID={`win-now.trade.${i}`}>
          <Text variant="heading">{i + 1}. Trade with {trade.partner_username || `Team ${trade.partner_roster_id}`}</Text>
          <Text style={s.label}>You give: {trade.give.map(asset => asset.name).join(' + ')}</Text>
          <Text style={s.label}>You receive: {trade.receive.map(asset => asset.name).join(' + ')}</Text>
          <Evidence trade={trade} objective={objective} title={titleAvailable && resultMeta?.championship_available === true} />
          <Text style={s.caption}>{sourceReceipt(resultMeta)}</Text>
          <View style={s.row}>
            <Action id={`win-now.edit.${i}`} label="Edit & evaluate" onPress={() => edit(trade)} disabled={busy} />
            <Action id={`win-now.like.${i}`} label={decisions[trade.scenario_id] === 'like' ? 'Liked' : 'Like'} onPress={() => decide(trade, 'like')} disabled={busy || !!decisions[trade.scenario_id]} />
            <Action id={`win-now.pass.${i}`} label={decisions[trade.scenario_id] === 'pass' ? 'Passed' : 'Pass'} onPress={() => decide(trade, 'pass')} disabled={busy || !!decisions[trade.scenario_id]} />
          </View>
        </View>)}
        {editor && available && searchOn && <View testID="win-now.editor" style={s.card}>
          <Text variant="heading">Evaluate with {editor.partner_username || 'partner'}</Text>
          <Text style={s.body}>Choose up to 3 assets on each side from the snapshot. Every edit requires a fresh evaluation.</Text>
          {(['give', 'receive'] as const).map(side => <View key={side}><Text variant="label">You {side}</Text><View style={s.row}>
            {(assets.length ? assets.filter(asset => asset.owner_roster_id === (side === 'give' ? baseline?.buyer_roster_id : editor.partner_roster_id)) : editor[side]).map(asset => <Action key={asset.id} id={`win-now.editor.${side}.${asset.id}`} label={assetLabel(asset)} selected={(side === 'give' ? giveIds : receiveIds).includes(asset.id)} disabled={asset.tradable === false || (side === 'give' && protectedIds.includes(asset.id)) || ((side === 'give' ? giveIds : receiveIds).length >= 3 && !(side === 'give' ? giveIds : receiveIds).includes(asset.id))} onPress={() => toggleAsset(asset.id, side)} />)}
          </View></View>)}
          <Action id="win-now.evaluate" primary label="Evaluate edited trade" onPress={evaluate} disabled={busy || !canSearch || !giveIds.length || !receiveIds.length} />
          {evaluation && <><Text style={s.label}>{evaluation.status === 'unavailable' || seasonStale(evaluation.meta) ? evaluation.message || 'Evaluation unavailable. Refresh projections.' : evaluation.eligible ? 'Meets Win Now requirements' : 'Does not meet Win Now requirements'}</Text>
            {(evaluation.rejection_reasons || []).map((reason, i) => <Text key={i} style={s.body}>{reason.replace(/_/g, ' ')}</Text>)}
            {evaluation.status === 'available' && !seasonStale(evaluation.meta) && evaluation.scenario && <Evidence trade={evaluation.scenario} objective={objective} title={titleAvailable && evaluation.meta?.championship_available === true} />}
            <Text style={s.caption}>{sourceReceipt(evaluation.meta)}</Text></>}
        </View>}
      </>}
    </ScrollView>
    <FeedbackFAB activeScreen="WinNow" aboveTabBar={false} />
  </SafeAreaView>;
}
const s = StyleSheet.create({
  safe: {flex: 1, backgroundColor: ink.ink0},
  scroll: {padding: space.lg, paddingBottom: 100, gap: space.md},
  card: {padding: space.lg, gap: space.md, backgroundColor: ink.ink1, borderColor: ink.line, borderWidth: 1, borderRadius: radii.md},
  row: {flexDirection: 'row', flexWrap: 'wrap', gap: space.sm},
  body: {...type.body, color: chalk.dim},
  caption: {...type.bodySm, color: chalk.dim},
  label: {...type.body, color: chalk.base},
  metrics: {gap: space.xs},
  standing: {gap: space.xs, borderBottomWidth: 1, borderBottomColor: ink.line, paddingBottom: space.sm},
  button: {minHeight: 44, justifyContent: 'center', paddingHorizontal: space.md, paddingVertical: space.sm, borderColor: ink.lineStrongA11y, borderWidth: 1, borderRadius: radii.sm},
  buttonText: {...type.bodySm, color: chalk.base},
  selected: {borderColor: ice.base, backgroundColor: ink.ink3},
  selectedText: {color: ice.base},
  primary: {backgroundColor: ice.base, borderColor: ice.base},
  primaryText: {color: ice.on},
  disabled: {opacity: 0.5},
  input: {...type.body, color: chalk.base, minHeight: 44, padding: space.md, borderColor: ink.lineStrongA11y, borderWidth: 1, borderRadius: radii.sm, backgroundColor: ink.ink2},
});
