import { api } from './client';
import type { SeasonProjection, WinNowSearchParams, WinNowJob, WinNowEvaluation } from '../shared/types';

export const getSeasonProjections = (leagueId: string, signal?: AbortSignal) =>
  api.get<SeasonProjection>(`/api/league/season-projections?league_id=${encodeURIComponent(leagueId)}`, {signal});
export const searchWinNow = (params: WinNowSearchParams, signal?: AbortSignal) =>
  api.post<WinNowJob>('/api/win-now/search', params, {signal});
export const getWinNowJob = (jobId: string, signal?: AbortSignal) =>
  api.get<WinNowJob>(`/api/win-now/jobs/${encodeURIComponent(jobId)}`, {signal});
export const evaluateWinNow = (
  params: WinNowSearchParams & {partner_roster_id: number; give_ids: string[]; receive_ids: string[]},
  signal?: AbortSignal,
) => api.post<WinNowEvaluation>('/api/win-now/evaluate', params, {signal});
// Deliberately independent of dynasty swipe/queue learning.
export const decideWinNow = (scenarioId: string, decision: 'like' | 'pass', signal?: AbortSignal) =>
  api.post<{ok?: boolean; status?: 'unavailable'; message?: string; reason?: string}>(`/api/win-now/scenarios/${encodeURIComponent(scenarioId)}/decision`, {decision}, {signal});
