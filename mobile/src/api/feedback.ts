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
