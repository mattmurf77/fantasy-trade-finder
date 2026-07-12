// #53/#54 — 0–10k display value for a player row / header aggregate. The
// rankings payload carries no raw DynastyProcess value, so invert the
// DOCUMENTED seed-scale mapping instead (docs/cross-client-invariants.md,
// banding rule — since 2026-07-12 #117 the value-affine map in
// backend/data_loader.seed_elo_for_value: DP maps affinely onto the trade
// value scale, `v = V0 + dp/10000 × (V4 − V0)` with V0 = value(Elo 1200)
// and V4 = 4 × value(Mid 1st, Elo 1650), through the exponential curve
// `value(elo) = 1000·e^(0.005·(elo − 1500))`), clamped to the 0–10k scale.
// Note the input is the user's CURRENT Elo (consensus-seeded, then
// personalized by trios / tier saves / anchors), so this reads as the
// player's value on the USER'S board; a pure consensus value would need the
// #53/#54 backend payload work — do not build that here.
const V0 = 1000 * Math.exp(0.005 * (1200 - 1500)); // ≈ 223.1 (DP 0)
const V4 = 4 * 1000 * Math.exp(0.005 * (1650 - 1500)); // ≈ 8468 (DP 10000)

export function valueForElo(elo: number | null | undefined): number | null {
  if (elo == null) return null;
  const value = 1000 * Math.exp(0.005 * (elo - 1500));
  const dp = ((value - V0) / (V4 - V0)) * 10_000;
  return Math.max(0, Math.min(10_000, Math.round(dp)));
}
