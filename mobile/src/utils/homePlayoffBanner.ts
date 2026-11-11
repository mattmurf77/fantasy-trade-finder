import type { ProjectionOutlook, ProjectionView } from '../api/leagueProjections';

export interface PlayoffRecommendation {
  outlook: ProjectionOutlook;
  /** The unrounded probability the server classified. */
  probability: number;
  suggestion: string | null;
}

/**
 * Presentation only, over the saved forecast. The outlook recommendation is
 * the server's: this passes it through or withholds it, and never classifies
 * a probability itself.
 */
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
  // A run saved by an older model is last saved, never current. An older
  // server sends no `model_current`, which reads as current.
  const oldModel = data?.model_current === false;
  const current = hasEstimate && !readFailed && !oldModel && data?.state === 'current' && Number.isFinite(due) && now < due;
  const status = readFailed ? 'Update unavailable'
    : data?.state === 'queued' || data?.state === 'running' ? 'Update pending'
    : data?.state === 'refresh_failed' || data?.state === 'failed' ? 'Update failed'
    : data?.state === 'incomplete_projections' ? 'League data incomplete'
    : data?.state === 'unsupported_policy' ? 'League rules unsupported'
    : !hasEstimate ? 'First forecast pending'
    : oldModel ? 'From an earlier forecast model'
    : !current ? 'Update due' : '';
  const rec = data?.outlook_recommendation;
  const available = current && rec?.status === 'available';
  const recProbability = rec?.playoff_probability;
  const recommendation: PlayoffRecommendation | null = available && rec.differs && rec.recommended_outlook
    ? { outlook: rec.recommended_outlook,
        probability: typeof recProbability === 'number' && Number.isFinite(recProbability) ? recProbability : probability!,
        suggestion: rec.suggestion }
    : null;
  // The server's sentence explains the suggestion, or why there is none. It
  // is withheld when it would explain a suggestion this client is not showing.
  const explanation = rec?.explanation && (available || rec.status === 'unavailable') ? rec.explanation : null;
  return { probability: hasEstimate ? probability : null, capturedAt: hasEstimate ? result!.captured_at : null,
    current, status, incomplete: hasEstimate && result!.coverage?.estimate_status === 'incomplete',
    recommendation, explanation };
}
