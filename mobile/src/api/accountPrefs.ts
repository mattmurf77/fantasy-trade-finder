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
import type { StudTaxMode } from './calc';

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

// ── #215 — stud-tax mode ('market' retuned default | 'heavy' legacy |
// 'off'). Consumed by /api/trade/evaluate and deck generation server-side.
export async function getStudTaxMode(): Promise<{ mode: StudTaxMode }> {
  return api.get<{ mode: StudTaxMode }>('/api/settings/stud-tax');
}

export async function setStudTaxMode(
  mode: StudTaxMode,
): Promise<{ ok: boolean; mode: StudTaxMode }> {
  return api.put<{ ok: boolean; mode: StudTaxMode }>('/api/settings/stud-tax', {
    mode,
  });
}

// ── Draft-pick pricing mode — CLIENT REMOVED 2026-08-21 (D-144) ──────────
// Operator ruling: "Market slots should be default and not an opt-in or even
// an option to flip." There is no per-user pick-pricing mode any more, so
// `PickPricingMode`, `getPickPricingMode` and `setPickPricingMode` are gone
// along with the Settings control that was their only caller.
//
// `/api/settings/pick-pricing` still exists for builds already in the field:
// GET serves the fixed `{mode: "market_slots", retired: true}`, PUT is 410
// Gone. Do not re-add a client for it — add nothing here unless a per-user
// pricing axis is authorised again.
