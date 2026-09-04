import type { SeasonMeta, SeasonTeam, WinNowScenario, WinNowObjective } from '../shared/types';
export const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
export const probability = (n: unknown) => finite(n) && n >= 0 && n <= 1 ? `${(100 * n).toFixed(1)}%` : '—';
export const numeric = (n: unknown) => finite(n) ? n.toFixed(2) : '—';
export function impact(before: unknown, after: unknown, points = false): string {
  if (!finite(before) || !finite(after)) return '—';
  const delta = (after - before) * (points ? 100 : 1);
  return `${delta > 0 ? '+' : ''}${delta.toFixed(points ? 1 : 2)}${points ? ' pp' : ''}`;
}
export function nextThree(team: SeasonTeam): number | undefined {
  // Never derive a horizon from object ordering or include finalized weeks.
  return finite(team.next_three_week_expected_wins) ? team.next_three_week_expected_wins : undefined;
}
export function seasonStale(meta?: SeasonMeta, now = Date.now()): boolean {
  return !!meta?.stale || (!!meta?.expires_at && Date.parse(meta.expires_at) <= now);
}
export function sourceReceipt(meta?: SeasonMeta): string {
  const coverage = ` · Coverage ${finite(meta?.coverage) ? probability(meta.coverage) : 'unavailable'}`;
  const time = meta?.as_of && Number.isFinite(Date.parse(meta.as_of)) ? new Date(meta.as_of).toLocaleString() : 'timestamp unavailable';
  const source = meta?.source === 'sleeper_weekly_experimental' ? 'Sleeper weekly projections' : meta?.source || 'Source unavailable';
  return `${meta?.calibrated === true ? 'Calibrated model' : 'Uncalibrated beta'} · Intervals describe Monte Carlo sampling only; projection/model uncertainty is excluded.\n${source} · ${time}${coverage}`;
}

export function projectedStandings(teams: SeasonTeam[]): SeasonTeam[] {
  return [...teams].sort((a, b) => (finite(a.projected_seed) ? a.projected_seed : Infinity)
    - (finite(b.projected_seed) ? b.projected_seed : Infinity) || a.roster_id - b.roster_id);
}
export function samplingEvidence(trade: WinNowScenario, objective: WinNowObjective): string {
  const metric = {wins: 'next_three_week_expected_wins', playoffs: 'playoff_probability', championship: 'championship_probability'}[objective];
  const label = {wins: 'Next 3 weeks', playoffs: 'Make playoffs', championship: 'Championship'}[objective];
  const evidence = trade.buyer.uncertainty?.[metric];
  const format = (value: unknown) => finite(value) ? `${impact(0, value, objective !== 'wins')}${objective === 'wins' ? ' wins' : ''}` : 'unavailable';
  return `${label} · Sampling range ${format(evidence?.lower_bound)} to ${format(evidence?.upper_bound)}. Independent-run change ${format(evidence?.confirmation_delta)}; conservative search gain ${format(trade.conservative_season_gain)}. Sampling error only, not a forecast confidence interval.`;
}
