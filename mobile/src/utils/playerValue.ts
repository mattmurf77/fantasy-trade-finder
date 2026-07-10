// #53/#54 — 0–10k display value for a player row / header aggregate. The
// rankings payload carries no raw DynastyProcess value, so invert the
// DOCUMENTED seed-scale mapping instead (docs/cross-client-invariants.md,
// banding rule: `elo = 1200 + value/10000 × 600`), clamped to the 0–10k
// scale. Note the input is the user's CURRENT Elo (consensus-seeded, then
// personalized by trios / tier saves / anchors), so this reads as the
// player's value on the USER'S board; a pure consensus value would need the
// #53/#54 backend payload work — do not build that here.
export function valueForElo(elo: number | null | undefined): number | null {
  if (elo == null) return null;
  return Math.max(0, Math.min(10_000, Math.round(((elo - 1200) / 600) * 10_000)));
}
