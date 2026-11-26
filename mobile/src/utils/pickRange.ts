// The likely draft pick if a team misses the playoffs: the Standings open
// team's Draft pick odds rows and the Home playoff card's "likely …" note.
// Pure, zero runtime imports, so tests/check-league-projections.js and
// tests/check-home-playoff-banner.js transpile and execute it under node.

/** The range shows only when the team misses the playoffs in at least this
 *  share of simulated seasons (`nonplayoff_probability`). */
export const PICK_RANGE_MIN_MISS = 0.25;

/** "<round>.<two-digit slot>", e.g. pickLabel(1, 2) === '1.02'. */
export function pickLabel(round: number | string, slot: number): string {
  return `${round}.${String(slot).padStart(2, '0')}`;
}

/** The 10th and 90th percentile pick slots (1-based) among simulated seasons
 *  where the team misses the playoffs. `pickProbabilities` are unconditional
 *  per non-playoff slot (index 0 = pick 1), so they are renormalised by their
 *  sum; null when the sum is not positive. */
export function likelyPickSlots(pickProbabilities: number[]): {low: number; high: number} | null {
  const miss = pickProbabilities.reduce((sum, p) => sum + p, 0);
  if (!(miss > 0)) return null;
  let cdf = 0;
  let low: number | null = null;
  let high: number | null = null;
  for (let i = 0; i < pickProbabilities.length; i++) {
    cdf += pickProbabilities[i] / miss;
    if (low == null && cdf >= 0.10 - 1e-9) low = i + 1;
    if (high == null && cdf >= 0.90 - 1e-9) high = i + 1;
  }
  return low != null && high != null ? {low, high} : null;
}

/** "1.01–1.02" (en dash), or a single "1.06" when both ends match. */
export function pickRangeText(round: number | string, range: {low: number; high: number}): string {
  return range.low === range.high ? pickLabel(round, range.low) : `${pickLabel(round, range.low)}–${pickLabel(round, range.high)}`;
}

/** The range text when the team misses in at least PICK_RANGE_MIN_MISS of
 *  seasons and a range exists, else null. */
export function likelyPickText(missProbability: number | null | undefined, pickProbabilities: number[] | null | undefined,
  round: number | string | null | undefined): string | null {
  if (typeof missProbability !== 'number' || !(missProbability >= PICK_RANGE_MIN_MISS) || !pickProbabilities || round == null) return null;
  const range = likelyPickSlots(pickProbabilities);
  return range ? pickRangeText(round, range) : null;
}
