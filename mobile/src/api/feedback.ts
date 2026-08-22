// POST /api/feedback — uploads a single feedback note captured on-device.
//
// The mobile feedback store (state/useFeedback.ts) owns the local AsyncStorage
// copy. This module just shapes the wire payload and POSTs it. The base
// `api.post` already attaches X-Session-Token (when present) + X-Device /
// X-OS-Version / X-App-Version headers, so anonymous and signed-in tester
// flows both work without extra plumbing here.
//
// Backend contract (locked) lives in docs/plans/feedback-backend-sync.md.

import { api } from './client';
import type { FeedbackSeverity } from '../state/useFeedback';

// Maximum characters accepted in a feedback note's `text`.
//
// MIRROR of `FEEDBACK_TEXT_MAX` in backend/server.py (same name, same value),
// which `POST /api/feedback` enforces by rejecting a longer body with
// `400 {"error": "text_too_long", "limit": <that number>}`. Keep the two
// identical: a client cap ABOVE the server's turns every long note into a
// failed submit, and a cap BELOW it silently shortens what testers can say.
// The compose sheet (components/FeedbackSheet.tsx) reads this for both its
// live character counter and its Save gate, so there is exactly one number to
// change on the client side when the server's moves.
export const FEEDBACK_TEXT_MAX = 8000;

export interface FeedbackSubmitPayload {
  client_id: string;
  screen: string;
  severity: FeedbackSeverity;
  text: string;
  client_created_at: string; // ISO 8601
}

export interface FeedbackSubmitResponse {
  ok: boolean;
  server_id: number;
  created_at: string;
  duplicate?: boolean;
}

export async function submitFeedback(
  payload: FeedbackSubmitPayload,
): Promise<FeedbackSubmitResponse> {
  return api.post<FeedbackSubmitResponse>('/api/feedback', payload);
}

// ── Status readback ──────────────────────────────────────────────────
// GET /api/feedback/mine — the signed-in user's own notes with their
// operator-set lifecycle status. Vocabulary mirrors the backend's
// FEEDBACK_STATUSES (docs/cross-client-invariants.md).
export type FeedbackStatus =
  | 'new'
  | 'planned'
  | 'in_progress'
  | 'fixed'
  | 'shipped'
  | 'declined';

// Terminal statuses hidden from the user's inbox. Mirrors the backend's
// FEEDBACK_CLOSED_STATUSES (backend/database.py) — /api/feedback/mine
// stops returning these rows; this client-side copy hides locally-persisted
// notes whose last-merged status is already terminal. 'fixed' stays visible
// ("Fixed — in next update") until the operator flips it to 'shipped'.
export const CLOSED_FEEDBACK_STATUSES: readonly FeedbackStatus[] = ['shipped', 'declined'];
// The FAB badge additionally excludes 'fixed' — see the pure module
// utils/feedbackBadge.ts (RESOLVED_FEEDBACK_STATUSES, #184).

export interface MyFeedbackItem {
  server_id: number;
  client_id: string;
  screen: string;
  severity: FeedbackSeverity;
  text: string;
  created_at: string;
  status: FeedbackStatus;
  status_updated_at: string | null;
}

export async function getMyFeedback(): Promise<{ items: MyFeedbackItem[] }> {
  return api.get<{ items: MyFeedbackItem[] }>('/api/feedback/mine');
}
