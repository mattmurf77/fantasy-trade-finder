import { api } from './client';
import type { FlagMap } from '../shared/types';

// GET /api/feature-flags — one fetch at boot. Mirrors the web's
// window.FTF_FLAGS pattern.
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
    const res = await api.get<{ flags: FlagMap }>('/api/feature-flags');
    return res?.flags || {};
  } catch (err) {
    if (opts.throwOnError) throw err;
    return {};
  }
}
