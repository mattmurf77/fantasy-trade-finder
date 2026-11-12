import { api, ApiError, type RequestOptions } from './client';
import type { FounderLabel, FounderRow, QbScope, ReviewPosition } from '../utils/founderReview';

// Founders' review (docs/plans/founder-review/design.md §5). Every route 404s
// unless the SERVER says this session is a founder's (flag `founder.review`,
// env FOUNDER_ACCOUNTS, a verified session). The app reads no flag and keeps no
// list: the capability answer is the only gate.

export interface FounderCorrection { from: FounderLabel; to: FounderLabel; count: number; }

export interface FounderSummary {
  positions: Record<ReviewPosition, { moved: number; corrections: FounderCorrection[] }>;
  overrides_total: number;
  overrides_here: number;
}

export interface FounderPage {
  schema: 'founder-label-review-1';
  labels: FounderLabel[];
  bands: string[];
  qb_scope: QbScope | null;
  evidence: { state: string | null; reason: string | null; weeks: number[]; captured_at: string | null };
  line: Partial<Record<ReviewPosition, number | null>>;
  players: FounderRow[];
  summary: FounderSummary;
}

export interface FounderSaveBody { league_id: string; set: Record<string, FounderLabel>; clear: string[]; }
export interface FounderSaveResult { set: number; cleared: number; overrides_total: number; }

type Opts = Pick<RequestOptions, 'signal'>;

/** True only when the server answers 200; a 404 (not a founder, or off) is false. */
export async function getFounderCapability(options?: Opts): Promise<boolean> {
  try {
    const r = await api.get<{ founder_review?: boolean }>('/api/founder/capability', {
      ...options, quietStatuses: [404],
    });
    return r?.founder_review === true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return false;
    throw e;
  }
}

export function getFounderLabels(leagueId: string, options?: Opts): Promise<FounderPage> {
  return api.get<FounderPage>(`/api/founder/labels?league_id=${encodeURIComponent(leagueId)}`, options);
}

export function saveFounderLabels(body: FounderSaveBody): Promise<FounderSaveResult> {
  return api.post<FounderSaveResult>('/api/founder/labels', body);
}
