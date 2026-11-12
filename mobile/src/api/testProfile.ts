// Onboarding test profile — wire client for /api/test-profile/* (backend
// test_profile.py; docs/plans/onboarding-test-profile/). Operator-only: the
// server answers 404 to everyone not allow-listed, and every route derives the
// account from the session token alone. No request here carries a target user
// id — pinned by tests/check-test-profile.js.

import { api, ApiError } from './client';

export interface TestProfileStatus {
  available: boolean;
  active: boolean;
  user_id?: string;
  display_name?: string;
}

export interface TestProfileSession {
  session_token: string;
  user_id: string;
  username: string;
  display_name: string;
}

/** GET /api/test-profile — null when the account may not use it (404). */
export async function getTestProfileStatus(): Promise<TestProfileStatus | null> {
  try {
    return await api.get<TestProfileStatus>('/api/test-profile', { quietStatuses: [404] });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** POST /api/test-profile/enter — from the REAL session; returns the test
 *  profile's own session. The real token is untouched server-side. */
export function enterTestProfileRemote(): Promise<TestProfileSession> {
  return api.post<TestProfileSession>('/api/test-profile/enter', {});
}

/** POST /api/test-profile/exit — ends the test session (best-effort). */
export function exitTestProfileRemote(): Promise<{ ok: boolean }> {
  return api.post<{ ok: boolean }>('/api/test-profile/exit', {});
}

/** POST /api/test-profile/reset — wipes the test profile's rows; returns a
 *  fresh test session. */
export function resetTestProfileRemote(): Promise<TestProfileSession> {
  return api.post<TestProfileSession>('/api/test-profile/reset', {});
}
