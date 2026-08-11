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
/** P0-7 F1 — flag-key → the experiment overlay it came from.
 *  Rebuilt on every successful fetch and never persisted: it describes the
 *  CURRENT assignment, and a stale one would attribute an exposure to an
 *  experiment the unit is no longer in. Module-level, deliberately not in
 *  the store — it must not cause a re-render. */
export type FlagProvenance = Record<string, { experiment: string; variant: string }>;
let _provenance: FlagProvenance = {};
export function flagProvenance(): FlagProvenance { return _provenance; }

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
    const res = await api.get<{
      flags: FlagMap;
      experiments?: Record<string, string>;
      configs?: Record<string, { flags?: FlagMap } & Record<string, unknown>>;
    }>('/api/feature-flags', headers ? { headers } : undefined);
    const base = res?.flags || {};
    // Experiment overlays (FR-35): a running experiment variant may carry
    // client_config.flags — per-unit flag values resolved server-side (e.g.
    // the onboarding rollout turning onboarding.* on for targeted units
    // only). Overlay wins over the global map. The flag store caches the
    // MERGED map, so an assigned unit keeps its variant flags across
    // offline boots; assignment changes reconcile on the next fetch.
    const configs = res?.configs || {};
    const exps = res?.experiments || {};
    const provenance: FlagProvenance = {};
    let merged = base;
    for (const key of Object.keys(configs)) {
      const overlay = configs[key]?.flags;
      if (overlay && typeof overlay === 'object' && !Array.isArray(overlay)) {
        merged = { ...merged, ...overlay };
        // P0-7 F1 — remember WHICH experiment/variant supplied each key so
        // useFeatureFlags can emit an exposure on first consumption. Last
        // writer wins, exactly like the merge above, so provenance can
        // never disagree with the value the app is actually using.
        for (const fk of Object.keys(overlay)) {
          provenance[fk] = { experiment: key, variant: exps[key] ?? 'unknown' };
        }
      }
    }
    // Success path only: a failed fetch leaves the previous map intact,
    // matching revalidateFlags' "keep cached flags" contract.
    _provenance = provenance;
    return merged;
  } catch (err) {
    if (opts.throwOnError) throw err;
    return {};
  }
}
