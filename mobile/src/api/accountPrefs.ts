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

// ── M6b — draft-pick pricing mode (flag `trade.slot_pricing`; 404 while the
// flag is dark, which the Settings section treats as "hide the control").
// 'tier_ladder' (DEFAULT — today's shipped pick ladder) | 'market_slots'
// (DynastyProcess per-slot market curve). Note the default differs from
// #215's: the market mode here is opt-in, not the shipped behaviour.
export type PickPricingMode = 'tier_ladder' | 'market_slots';

export async function getPickPricingMode(): Promise<{ mode: PickPricingMode }> {
  return api.get<{ mode: PickPricingMode }>('/api/settings/pick-pricing');
}

export async function setPickPricingMode(
  mode: PickPricingMode,
): Promise<{ ok: boolean; mode: PickPricingMode }> {
  return api.put<{ ok: boolean; mode: PickPricingMode }>(
    '/api/settings/pick-pricing',
    { mode },
  );
}
