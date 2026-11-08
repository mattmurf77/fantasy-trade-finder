import type { ProjectionView } from '../api/leagueProjections';

export type PlayoffTradeSide = 'buy' | 'sell';

/** Presentation only: matches existing outlook bands, never assigns strategy. */
export function homePlayoffBanner(
  data: ProjectionView | undefined,
  rosterId: number | null,
  readFailed: boolean,
  now = Date.now(),
) {
  const result = data?.run?.status === 'complete' ? data.run.result : null;
  const team = rosterId == null ? undefined : result?.teams.find(t => t.roster_id === rosterId);
  const value = team?.playoff_probability;
  const probability = typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
  const captured = result ? Date.parse(result.captured_at) : NaN;
  const due = data?.next_attempt_not_before ? Date.parse(data.next_attempt_not_before) : NaN;
  const hasEstimate = probability != null && Number.isFinite(captured) && captured <= now;
  const current = hasEstimate && !readFailed && data?.state === 'current' && Number.isFinite(due) && now < due;
  const sides: PlayoffTradeSide[] = !current ? [] : probability! >= .65 ? ['buy'] : probability! < .35 ? ['sell'] : ['buy', 'sell'];
  const status = readFailed ? 'Update unavailable'
    : data?.state === 'queued' || data?.state === 'running' ? 'Update pending'
    : data?.state === 'refresh_failed' || data?.state === 'failed' ? 'Update failed'
    : data?.state === 'incomplete_projections' ? 'League data incomplete'
    : data?.state === 'unsupported_policy' ? 'League rules unsupported'
    : hasEstimate && !current ? 'Last saved'
    : !hasEstimate ? 'First weekly forecast pending' : 'Weekly';
  return { probability: hasEstimate ? probability : null, capturedAt: hasEstimate ? result!.captured_at : null,
    current, sides, status, partial: !!result?.coverage?.estimated };
}
