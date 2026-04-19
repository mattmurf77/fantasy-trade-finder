import { api } from './client';
import type { FlagMap } from '../shared/types';

// GET /api/feature-flags — one fetch at boot. Mirrors the web's
// window.FTF_FLAGS pattern. Values default to false on network failure.
export async function loadFeatureFlags(): Promise<FlagMap> {
  try {
    const res = await api.get<{ flags: FlagMap }>('/api/feature-flags');
    return res?.flags || {};
  } catch {
    return {};
  }
}
