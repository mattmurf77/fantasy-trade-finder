// Playoff odds display rule (D-262; docs/cross-client-invariants.md
// § "Playoff odds: 100% and 0% need a proof"). ZERO runtime imports, so
// tests/check-playoff-odds-display.js can transpile and execute it.
//
// A chance that would print as 100% at a surface's precision prints 100%
// only when the server has PROVEN the team clinched (`playoff_clinched`);
// otherwise it prints ">99.9%" (one decimal), ">99%" (whole) or ">95%"
// (5-point steps). The mirror for 0% needs `playoff_eliminated`: "<0.1%",
// "<1%", "<5%". Every other value prints exactly as the surface printed it
// before. Absent flags (an older server or a run saved before D-262) are
// "not proven". Mirrors web/js/playoff-odds.js and
// backend/league_projections/clinch.py `odds_text`.

/** The server's proof, on a forecast team, the Max PF baseline, the outlook
 *  recommendation and Team Review's `playoff_chance`. */
export interface PlayoffProof {
  playoff_clinched?: boolean | null;
  playoff_eliminated?: boolean | null;
}

/** The surface's precision in percentage points: 0.1 = one decimal, 1 = whole percents, 5 = 5-point steps. */
export type OddsStep = 0.1 | 1 | 5;

const BELOW: Record<OddsStep, string> = { 0.1: '<0.1%', 1: '<1%', 5: '<5%' };
const ABOVE: Record<OddsStep, string> = { 0.1: '>99.9%', 1: '>99%', 5: '>95%' };

/** The number as the surface printed it before D-262 (no % sign). */
function printed(p: number, step: OddsStep): string {
  if (step === 0.1) return (p * 100).toFixed(1);
  if (step === 1) return String(Math.floor(p * 100 + 0.5 + 1e-9));
  return String(Math.round((p * 100) / 5) * 5);
}

/** A probability (0..1) of MAKING the playoffs, as text. */
export function playoffOddsText(probability: number, proof: PlayoffProof | null | undefined, step: OddsStep): string {
  const p = Math.max(0, Math.min(1, Number.isFinite(probability) ? probability : 0));
  const text = printed(p, step);
  const value = Number(text);
  if (value >= 100 && proof?.playoff_clinched !== true) return ABOVE[step];
  if (value <= 0 && proof?.playoff_eliminated !== true) return BELOW[step];
  return `${text}%`;
}

/** A probability of MISSING the playoffs: 0% needs a clinch, 100% an elimination. */
export function missOddsText(probability: number, proof: PlayoffProof | null | undefined, step: OddsStep): string {
  return playoffOddsText(probability, {
    playoff_clinched: proof?.playoff_eliminated, playoff_eliminated: proof?.playoff_clinched,
  }, step);
}

/**
 * Sort key for a playoff chance: the probability, then the proof. At an equal
 * probability a proven clinch sorts above an unproven ">99.9%", and a proven
 * elimination below an unproven "<0.1%"; otherwise equal stays equal.
 */
export function playoffSortKey(probability: number, proof: PlayoffProof | null | undefined): [number, number] {
  return [probability, proof?.playoff_clinched === true ? 1 : proof?.playoff_eliminated === true ? -1 : 0];
}
