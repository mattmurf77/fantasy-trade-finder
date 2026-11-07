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
  const question = sides.length === 2 ? 'Want to buy or sell a player?'
    : sides[0] === 'buy' ? 'Want to buy a player for a playoff push?'
    : sides[0] === 'sell' ? 'Want to sell a player for future value?' : null;
  const status = readFailed ? 'Could not check the latest update.'
    : data?.state === 'queued' || data?.state === 'running' ? 'The weekly update is being prepared.'
    : data?.state === 'refresh_failed' || data?.state === 'failed' ? 'The latest update could not finish.'
    : hasEstimate && !current ? 'A current weekly forecast is not available yet.'
    : !hasEstimate ? 'Your playoff estimate will appear after a completed weekly update.' : 'Updates weekly.';
  return { probability: hasEstimate ? probability : null, capturedAt: hasEstimate ? result!.captured_at : null,
    current, sides, question, status, partial: !!result?.coverage?.estimated };
}
