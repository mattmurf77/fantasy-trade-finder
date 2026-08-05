import AsyncStorage from '@react-native-async-storage/async-storage';
import { getTiersStatus } from '../api/rankings';
import { getOnboardingState } from './useOnboardingState';
import { useSession } from './useSession';

// #244 — per-position quick-tiers completion, for Rank-tab launch routing.
//
// The Rank stack's initialRouteName is decided synchronously at first mount
// (same contract as rankingMethodPref), so the completion signal must be
// readable without a network round-trip. Two sources, union'd:
//
//   • getOnboardingState().quicksetCompletedPositions — the persisted
//     "finished a Quick Set walk for this position" record (written by
//     QuickSetTiersScreen on every walk finish since onboarding item 7).
//     Updates the instant a walk completes, so on-device progress routes
//     correctly on the very next launch with zero lag.
//   • This module's AsyncStorage cache of GET /api/tiers/status `saved`
//     (positions with saved tiers for the active format) — the server
//     truth, covering reinstalls / second devices / tiers saved via the
//     Tiers board. Hydrated in the App.tsx boot gate (local read, ms-fast)
//     and refreshed fire-and-forget after the session revalidates, so a
//     stale cache converges on the NEXT launch — never a mid-session
//     navigation.replace, never a wrong-screen flash.
//
// The server cache is format-tagged: /api/tiers/status answers for the
// session's active format, so a cached answer for another format is
// ignored rather than misapplied. Like rankingMethodPref (RM_KEY), the
// cache is device-scoped and intentionally survives sign-out; a different
// user signing in converges after one launch's refresh.

const KEY = 'ftf_tiers_saved_cache_v1';

/** Quick Set ladder order — mirrors QuickSetTiersScreen's POSITIONS and the
 *  backend's all_done set (server.py tiers_status_route). */
export const QUICKSET_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;
export type QuicksetPosition = (typeof QUICKSET_POSITIONS)[number];

let cachedSaved: string[] = [];
let cachedFormat: string | null = null;

/** Boot-gate leg (App.tsx): restore the cached tiers-status snapshot from
 *  AsyncStorage so nextQuicksetPosition() is answerable pre-mount. */
export async function hydrateQuicksetProgress(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.saved)) {
      cachedSaved = parsed.saved.filter((p: unknown): p is string => typeof p === 'string');
      cachedFormat = typeof parsed.format === 'string' ? parsed.format : null;
    }
  } catch {
    /* non-fatal — the cache is optimistic; defaults route like a fresh user */
  }
}

/** Detached refresh (after revalidateSession): pull the live tiers-status
 *  and persist it for the next launch's routing decision. Never throws —
 *  offline / no session keeps the previous cache. */
export async function refreshQuicksetProgress(): Promise<void> {
  try {
    const res = await getTiersStatus();
    cachedSaved = Array.isArray(res.saved) ? res.saved : [];
    cachedFormat = res.scoring_format ?? null;
    await AsyncStorage.setItem(
      KEY,
      JSON.stringify({ saved: cachedSaved, format: cachedFormat }),
    );
  } catch {
    /* offline or unauthenticated — keep the previous snapshot */
  }
}

/** The next position (ladder order) WITHOUT quick-tiers completion, or null
 *  when all four are covered. Sync read over hydrated state — safe for
 *  initialRouteName / initialParams decisions at first mount. */
export function nextQuicksetPosition(): QuicksetPosition | null {
  const done = new Set<string>(getOnboardingState().quicksetCompletedPositions);
  // Only trust the server snapshot when it answers for the current format
  // (either side null = unknown → treat as matching; the server defaults
  // unset sessions the same way).
  const fmt = useSession.getState().activeFormat;
  if (cachedFormat == null || fmt == null || cachedFormat === fmt) {
    for (const p of cachedSaved) done.add(p);
  }
  return QUICKSET_POSITIONS.find((p) => !done.has(p)) ?? null;
}
