// Tier band thresholds. Single source of truth lives in
//   backend/tier_config.json
// and is fetched at boot via api/rankings.getTierConfig() →
// setTierConfigCache() below. While the cache is empty (e.g. very first
// app launch before the network call resolves, or offline mode) the
// hardcoded fallback bands keep the UI usable; they mirror the 2026-07-12
// 8-tier pick-value ladder (#117) in backend/tier_config.json — tiers read
// directly in draft-pick terms, each floor a rung of the anchor/pick Elo
// ladder (firsts_4plus ≥ 1927 ≈ 4 mid 1sts, firsts_3 ≥ 1869 ≈ 3 mid 1sts,
// firsts_2 ≥ 1788 ≈ 2 mid 1sts, first_1 ≥ 1580 = Late 1st, second ≥
// 1400 = Late 2nd, third ≥ 1280 = Late 3rd, fourth ≥ 1220 = Late 4th,
// waivers below that). Pick value is position-uniform by design, so the
// bands are identical across positions and scoring formats; occupancy
// differs because the seed Elos do.
//
// If you ever change either side without the other, mobile will silently
// drift from server until the user re-launches and the network fetch
// updates the cache. The fallback exists strictly to handle the
// pre-network window — production behavior reads the live cache.

import type { Position, ScoringFormat, Tier } from '../shared/types';
import type { TierConfigResponse, TierBand } from '../api/rankings';

export const TIERS: readonly Tier[] = [
  'firsts_4plus',
  'firsts_3',
  'firsts_2',
  'first_1',
  'second',
  'third',
  'fourth',
  'waivers',
] as const;

// Labels ARE pick terms (operator directive, supersedes the #103
// sublabels): a tier name says what a player in it is worth in the Pick
// Anchor wizard's vocabulary. FA = below 4th-round value (display label
// renamed from "Waivers" 2026-07-17; the key stays `waivers`).
export const TIER_LABEL: Record<Tier, string> = {
  firsts_4plus: '4+ 1sts',
  firsts_3:     '3 1sts',
  firsts_2:     '2 1sts',
  first_1:      '1 1st',
  second:       '2nd',
  third:        '3rd',
  fourth:       '4th',
  waivers:      'FA',
};

/** Inclusive ELO lower bounds per tier — fallback only. Live values come
 *  from the cached backend config (TierConfigResponse.config). `waivers` is
 *  implicit (everything below `fourth`). */
interface Thresholds {
  firsts_4plus: number;
  firsts_3: number;
  firsts_2: number;
  first_1: number;
  second: number;
  third: number;
  fourth: number;
}

// Uniform across positions AND formats (pick value is position-uniform);
// kept as a single constant rather than a per-(format, position) table.
const FALLBACK: Thresholds = {
  firsts_4plus: 1927,
  firsts_3:     1869,
  firsts_2:     1788,
  first_1:      1580,
  second:       1400,
  third:        1280,
  fourth:       1220,
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
 *  empty. Bench is implicit (everything below `fourth`). */
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
      firsts_4plus: lb('firsts_4plus'),
      firsts_3:     lb('firsts_3'),
      firsts_2:     lb('firsts_2'),
      first_1:      lb('first_1'),
      second:       lb('second'),
      third:        lb('third'),
      fourth:       lb('fourth'),
    };
  }
  return FALLBACK;
}

/** Map a raw ELO to its tier for the given position + scoring format. */
export function tierForElo(
  elo: number,
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Tier {
  const t = thresholdsFor(position, scoringFormat);
  if (elo >= t.firsts_4plus) return 'firsts_4plus';
  if (elo >= t.firsts_3)     return 'firsts_3';
  if (elo >= t.firsts_2)     return 'firsts_2';
  if (elo >= t.first_1)      return 'first_1';
  if (elo >= t.second)       return 'second';
  if (elo >= t.third)        return 'third';
  if (elo >= t.fourth)       return 'fourth';
  return 'waivers';
}

/** Auto-bucket a sorted-by-ELO list into the eight tier buckets. */
export function autoBucket<T extends { id: string; elo: number }>(
  players: T[],
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Record<Tier, T[]> {
  const buckets: Record<Tier, T[]> = {
    firsts_4plus: [], firsts_3: [], firsts_2: [], first_1: [],
    second: [], third: [], fourth: [], waivers: [],
  };
  for (const p of players) {
    const t = tierForElo(p.elo, position, scoringFormat);
    buckets[t].push(p);
  }
  return buckets;
}

/** #132 All-players board — bucket a MIXED-position list into the eight
 *  tier buckets, judging each player by ITS OWN position's thresholds.
 *  Bands are position-uniform by design, so today this matches a
 *  single-position walk; routing through each player's position keeps the
 *  merged board honest if per-position bands ever diverge. */
export function autoBucketMixed<T extends { id: string; elo: number; position: Position | string }>(
  players: T[],
  scoringFormat: ScoringFormat = '1qb_ppr',
): Record<Tier, T[]> {
  const buckets: Record<Tier, T[]> = {
    firsts_4plus: [], firsts_3: [], firsts_2: [], first_1: [],
    second: [], third: [], fourth: [], waivers: [],
  };
  for (const p of players) {
    // Player.position is `Position | string` in shared/types; an unknown
    // value simply misses the live-band lookup and walks the uniform
    // fallback thresholds — same bands, so bucketing stays correct.
    buckets[tierForElo(p.elo, p.position as Position, scoringFormat)].push(p);
  }
  return buckets;
}

/** Re-export for screens that want raw band info (min + max). */
export type { TierBand, TierConfigResponse };
