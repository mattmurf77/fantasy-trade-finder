import { api, getDeviceId } from './client';

// Calibration — in-app blind grading, value-core Gate 2.
// Contract: docs/plans/blind-grading/specs.md §3.2. Every /api/grading/* call
// 404s unless grading.blind resolves true for this caller AND the caller is on
// the tester allowlist. X-Device-Id rides every call so the server can resolve a
// device-unit flag overlay exactly as /api/feature-flags does (api/flags.ts).

export type GradingTag =
  | 'overpay' | 'they_wont_accept' | 'junk_filler' | 'too_small'
  | 'wrong_for_my_window' | 'wrong_for_their_window' | 'same_guy_again';

export const GRADING_TAGS: readonly GradingTag[] = [
  'overpay', 'they_wont_accept', 'junk_filler', 'too_small',
  'wrong_for_my_window', 'wrong_for_their_window', 'same_guy_again',
];

export const GRADING_TAG_LABELS: Record<GradingTag, string> = {
  overpay: 'Overpay',
  they_wont_accept: "They won't accept",
  junk_filler: 'Junk filler',
  too_small: 'Too small',
  wrong_for_my_window: 'Wrong for my window',
  wrong_for_their_window: 'Wrong for their window',
  same_guy_again: 'Same guy again',
};

export interface GradingProgress { answered: number; total: number; }

export interface GradingSession {
  session_id: string;
  league_id: string;
  status: 'building' | 'open' | 'completed' | 'failed';
  created_at: string;
  completed_at: string | null;
  progress: GradingProgress;
  error: { code: 'value_core_too_few' | 'value_core_failed'; [k: string]: unknown } | null;
}

export interface GradingAsset {
  id: string;
  name: string;
  position: string;            // 'QB' | 'RB' | 'WR' | 'TE' | 'PICK'
  nfl_team: string | null;
  age: number | null;
  value: number | null;
}

export interface GradingTrade {
  partner_name: string;
  give: GradingAsset[];
  receive: GradingAsset[];
}

export interface GradingCard {
  card_id: string;
  position: number;            // 1-based
  trade: GradingTrade;
}

export type GradingNext =
  | { done: false; session_id: string; progress: GradingProgress; card: GradingCard }
  | { done: true; session_id: string; progress: GradingProgress };

export type GradingAnswer =
  | { grade: 1 | 2 | 3 | 4 | 5; tags: GradingTag[] }
  | { skip: true };

export interface GradingAnswerResult {
  card_id: string;
  session_id: string;
  session_status: 'open' | 'completed';
  progress: GradingProgress;
}

export interface GradingArmSummary {
  cards: number;
  n: number;
  skipped: number;
  mean: number | null;
  share_ge_4: number | null;
  tag_counts: Partial<Record<GradingTag, number>>;
}

export interface GradingResults {
  session_id: string;
  league_id: string;
  completed_at: string;
  total: number;
  shared: number;
  target_mean: number;
  arms: { current: GradingArmSummary; value_core: GradingArmSummary };
}

async function deviceHeaders(): Promise<{ headers: Record<string, string> } | undefined> {
  try {
    return { headers: { 'X-Device-Id': await getDeviceId() } };
  } catch {
    return undefined;   // best effort, exactly as api/flags.ts
  }
}

export async function getCurrentGradingSession(
  leagueId: string,
): Promise<{ session: GradingSession | null }> {
  return api.get<{ session: GradingSession | null }>(
    `/api/grading/sessions/current?league_id=${encodeURIComponent(leagueId)}`,
    await deviceHeaders(),
  );
}

export async function startGradingSession(
  leagueId: string,
): Promise<{ session: GradingSession; resumed: boolean }> {
  return api.post<{ session: GradingSession; resumed: boolean }>(
    '/api/grading/sessions', { league_id: leagueId }, await deviceHeaders(),
  );
}

export async function getNextGradingCard(sessionId: string): Promise<GradingNext> {
  return api.get<GradingNext>(
    `/api/grading/sessions/${encodeURIComponent(sessionId)}/next`, await deviceHeaders(),
  );
}

export async function answerGradingCard(
  cardId: string, answer: GradingAnswer,
): Promise<GradingAnswerResult> {
  return api.post<GradingAnswerResult>(
    `/api/grading/cards/${encodeURIComponent(cardId)}`, answer, await deviceHeaders(),
  );
}

export async function getGradingResults(sessionId: string): Promise<GradingResults> {
  return api.get<GradingResults>(
    `/api/grading/sessions/${encodeURIComponent(sessionId)}/results`, await deviceHeaders(),
  );
}
