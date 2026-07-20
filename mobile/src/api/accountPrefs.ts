// Account preference + data-rights endpoints (teardown wave W2C).
// All session-authed via the shared client; errors surface as ApiError.
//
// - Profile visibility (flag `profiles.user_toggle`): per-user opt-in for
//   the public /u/<username> page. 404 while the flag is dark.
// - Data export (flag `account.data_export`): full JSON archive of every
//   user-keyed row — same table matrix as account deletion. 403
//   `verification_required` when a verified user's session hasn't stepped
//   up (callers route that into SleeperConnect).

import { api } from './client';

export interface ProfileVisibility {
  public: boolean;
}

// GET — the session user's stored public-profile opt-in (default false).
export async function getProfileVisibility(): Promise<ProfileVisibility> {
  return api.get<ProfileVisibility>('/api/profile/visibility');
}

// PUT — persist the opt-in. Verified-write gated server-side.
export async function setProfileVisibility(
  isPublic: boolean,
): Promise<ProfileVisibility> {
  return api.put<ProfileVisibility>('/api/profile/visibility', {
    public: isPublic,
  });
}

// GET — the export archive. Shape is backend-defined ({export_version,
// exported_at, user_id, tables:{...}}); the client treats it as opaque
// JSON to serialize into a shareable file.
export async function exportAccountData(): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>('/api/account/export');
}
