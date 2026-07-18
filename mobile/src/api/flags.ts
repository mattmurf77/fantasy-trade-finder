import { api, getDeviceId } from './client';
import type { FlagMap } from '../shared/types';

// GET /api/feature-flags — fetched at boot and on the ≥30-min foreground
// refetch (analytics-platform §4.6b). Mirrors the web's window.FTF_FLAGS
// pattern. The response is additive: {flags, experiments, configs} — this
// module still returns just the flag map (experiments are read via the P3
// experiment store); `.flags` tolerates the added keys.
//
// X-Device-Id is attached so the server can resolve per-unit experiment
// assignments (FR-35). The device id is best-effort — a failure to mint it
// must not block the flag fetch.
//
// Default behaviour: swallow network failures and return `{}` (preserves
// the pre-existing contract for any caller that just wants a map).
//
// With `{ throwOnError: true }`: re-raise so callers (the flag store's
// `load()`) can distinguish "fetch failed — keep cached flags" from
// "fetch succeeded — replace flags". Without this, a failure looked
// identical to a successful empty-flag-set response, which silently hid
// every gated feature on net error.
export async function loadFeatureFlags(
  opts: { throwOnError?: boolean } = {},
): Promise<FlagMap> {
  try {
    let headers: Record<string, string> | undefined;
    try {
      headers = { 'X-Device-Id': await getDeviceId() };
    } catch {
      /* device id unavailable — fetch flags without per-unit resolution */
    }
    const res = await api.get<{ flags: FlagMap }>('/api/feature-flags',
                                                  headers ? { headers } : undefined);
    return res?.flags || {};
  } catch (err) {
    if (opts.throwOnError) throw err;
    return {};
  }
}
