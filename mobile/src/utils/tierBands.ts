// Tier band thresholds. Single source of truth lives in
//   backend/tier_config.json
// and is fetched at boot via api/rankings.getTierConfig() →
// setTierConfigCache() below. While the cache is empty (e.g. very first
// app launch before the network call resolves, or offline mode) the
// hardcoded fallback bands keep the UI usable; they mirror the 2026-07-10
// consensus recalibration of backend/tier_config.json (FB #60/#69) —
// per-(format, position) lower bounds anchored to the DynastyProcess
// seed scale so Elite holds ~top-5 per position, Starter to ~rank 15,
// Solid to ~rank 30.
//
// If you ever change either side without the other, mobile will silently
// drift from server until the user re-launches and the network fetch
// updates the cache. The fallback exists strictly to handle the
// pre-network window — production behavior reads the live cache.

import type { Position, ScoringFormat, Tier } from '../shared/types';
import type { TierConfigResponse, TierBand } from '../api/rankings';

export const TIERS: readonly Tier[] = ['elite', 'starter', 'solid', 'depth', 'bench'] as const;

export const TIER_LABEL: Record<Tier, string> = {
  elite:   'Elite',
  starter: 'Starter',
  solid:   'Solid',
  depth:   'Depth',
  bench:   'Bench',
};

/** Inclusive ELO lower bounds per tier — fallback only. Live values come
 *  from the cached backend config (TierConfigResponse.config).  */
interface Thresholds {
  elite: number;
  starter: number;
  solid: number;
  depth: number;
}

const FALLBACK: Record<ScoringFormat, Record<Position, Thresholds>> = {
  '1qb_ppr': {
    QB: { elite: 1445, starter: 1330, solid: 1260, depth: 1206 },
    RB: { elite: 1600, starter: 1450, solid: 1330, depth: 1215 },
    WR: { elite: 1700, starter: 1505, solid: 1360, depth: 1220 },
    TE: { elite: 1400, starter: 1280, solid: 1225, depth: 1204 },
  },
  sf_tep: {
    QB: { elite: 1650, starter: 1460, solid: 1320, depth: 1210 },
    RB: { elite: 1500, starter: 1380, solid: 1270, depth: 1210 },
    WR: { elite: 1600, starter: 1450, solid: 1340, depth: 1215 },
    TE: { elite: 1330, starter: 1260, solid: 1220, depth: 1203 },
  },
};

// ── Cache, populated from /api/tier-config ─────────────────────────────
// Module-level mutable so any tier-related render path picks up the
// latest config without prop-drilling. App.tsx sets this once at boot;
// TiersScreen also re-sets on every successful fetch in case the cache
// was wiped (e.g. on a forced logout/login cycle).
let _cache: TierConfigResponse | null = null;

export function setTierConfigCache(cfg: TierConfigResponse | null): void {
  _cache = cfg;
}
export function getTierConfigCache(): TierConfigResponse | null {
  return _cache;
}

/** Read the per-(format, position) thresholds. Prefers the cached
 *  backend config; falls back to the seeded constants when the cache is
 *  empty. Bench is implicit (everything below `depth`). */
export function thresholdsFor(
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Thresholds {
  const liveBands = _cache?.config?.[scoringFormat]?.[position];
  if (liveBands) {
    // Convert the live {min, max} table to the lower-bound walk shape.
    // We only consult `min` for bucketing (`max` is used by the backend
    // for ELO-spread within a tier; not needed in the frontend walk).
    const lb = (t: Tier): number => liveBands[t]?.min ?? 0;
    return {
      elite:   lb('elite'),
      starter: lb('starter'),
      solid:   lb('solid'),
      depth:   lb('depth'),
    };
  }
  return FALLBACK[scoringFormat]?.[position] ?? FALLBACK['1qb_ppr'].RB;
}

/** Map a raw ELO to its tier for the given position + scoring format. */
export function tierForElo(
  elo: number,
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Tier {
  const t = thresholdsFor(position, scoringFormat);
  if (elo >= t.elite)   return 'elite';
  if (elo >= t.starter) return 'starter';
  if (elo >= t.solid)   return 'solid';
  if (elo >= t.depth)   return 'depth';
  return 'bench';
}

/** Auto-bucket a sorted-by-ELO list into the five tier buckets. */
export function autoBucket<T extends { id: string; elo: number }>(
  players: T[],
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Record<Tier, T[]> {
  const buckets: Record<Tier, T[]> = {
    elite: [], starter: [], solid: [], depth: [], bench: [],
  };
  for (const p of players) {
    const t = tierForElo(p.elo, position, scoringFormat);
    buckets[t].push(p);
  }
  return buckets;
}

/** Re-export for screens that want raw band info (min + max). */
export type { TierBand, TierConfigResponse };
