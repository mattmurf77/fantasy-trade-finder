// Tier band thresholds mirroring backend/ranking_service.py.
//
// Backend source of truth:
//   UNIFORM_ELO_TIER_THRESHOLDS     — RB/WR in every format, all positions in SF TEP
//   QB_TE_1QB_ELO_TIER_THRESHOLDS   — QB/TE only, in 1QB PPR (compressed bands)
//
// Keeping these numbers in sync with the backend is critical — if they
// drift, the mobile app would auto-bucket players differently than the
// server re-buckets on save, producing a jarring "my tiers changed!"
// reload. If you change this table, also update:
//   backend/ranking_service.py (UNIFORM_TIER_ELO_BANDS + QB_TE_1QB_TIER_ELO_BANDS)
//   web/positional-tiers.html  (ELO_TIER_THRESHOLDS block near line 1316)

import type { Position, ScoringFormat, Tier } from '../shared/types';

export const TIERS: readonly Tier[] = ['elite', 'starter', 'solid', 'depth', 'bench'] as const;

export const TIER_LABEL: Record<Tier, string> = {
  elite:   'Elite',
  starter: 'Starter',
  solid:   'Solid',
  depth:   'Depth',
  bench:   'Bench',
};

/** Inclusive ELO lower bounds per tier (everything below `depth` falls into `bench`). */
interface Thresholds {
  elite: number;
  starter: number;
  solid: number;
  depth: number;
}

const UNIFORM: Thresholds = {
  elite:   1700,
  starter: 1580,
  solid:   1460,
  depth:   1350,
};

const QB_TE_1QB: Thresholds = {
  elite:   1580,
  starter: 1460,
  solid:   1350,
  depth:   1190,
};

export function thresholdsFor(
  position: Position,
  scoringFormat: ScoringFormat = '1qb_ppr',
): Thresholds {
  if (scoringFormat === '1qb_ppr' && (position === 'QB' || position === 'TE')) {
    return QB_TE_1QB;
  }
  return UNIFORM;
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
