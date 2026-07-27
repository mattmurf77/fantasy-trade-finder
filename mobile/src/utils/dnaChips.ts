// #193 — Trade DNA chip de-conflict (TradeFinderHubScreen's Chasing/Shopping
// panel). The panel merges the user's EXPLICIT positional prefs
// (acquire_positions / trade_away_positions) with the backend's roster-profile
// RECOMMENDATIONS (position_needs / position_surplus, FB #156). Before this
// module the screen only de-conflicted a recommendation against the SAME-side
// explicit pref, so a user explicitly shopping QB whose roster profile said
// "thin at QB" rendered QB under Chasing (need chip) AND Shopping (explicit
// chip) at once.
//
// Precedence rule (a position appears on at most ONE side):
//   1. Explicit user prefs always win over recommendations, on BOTH sides —
//      a position the user placed anywhere explicitly never gets a
//      recommendation chip.
//   2. Explicit vs explicit (pos in acquire AND shed — the OutlookSheet does
//      not forbid it): acquire wins, the chip renders under Chasing only.
//      Tiebreak rationale: "I want one" is the more specific, actionable
//      instruction for the trade engine than "I'd part with one".
//   3. Recommendation vs recommendation (pos in needs AND surplus — impossible
//      with the current analyze_roster_strengths thresholds, defended against
//      for older/other servers): need wins. A starter shortfall is the more
//      urgent signal than shed-your-depth.
//
// Pure by design (zero runtime imports) so mobile/tests/check-dna-chips.js
// can transpile and run it under plain node — same idiom as sessionRerank.ts.

export type DnaTag = 'need' | 'deep';

export interface DnaChip {
  pos: string;
  /** true = recommendation (dashed) chip; false = explicit user pref. */
  rec: boolean;
  tag?: DnaTag;
}

export interface DnaChipSides {
  chasing: DnaChip[];
  shopping: DnaChip[];
}

/**
 * Split prefs + recommendations into de-conflicted Chasing/Shopping chip
 * lists. Within each side, explicit chips render first, then recommendation
 * chips, each in `posOrder` (the panel's existing visual convention).
 * Invariant: no position appears in both returned sides.
 */
export function splitDnaChips(input: {
  acquire: string[];
  shed: string[];
  needs: string[];
  surplus: string[];
  posOrder: readonly string[];
}): DnaChipSides {
  const acquire = new Set(input.acquire);
  const shed = new Set(input.shed);
  const explicit = new Set([...acquire, ...shed]);
  const needs = new Set(input.needs);

  const chasing: DnaChip[] = [];
  const shopping: DnaChip[] = [];
  for (const pos of input.posOrder) {
    if (acquire.has(pos)) chasing.push({ pos, rec: false });
    else if (shed.has(pos)) shopping.push({ pos, rec: false }); // rule 2: acquire wins
  }
  for (const pos of input.posOrder) {
    if (explicit.has(pos)) continue; // rule 1: explicit wins both sides
    if (needs.has(pos)) chasing.push({ pos, rec: true, tag: 'need' });
    else if (input.surplus.includes(pos)) shopping.push({ pos, rec: true, tag: 'deep' }); // rule 3: need wins
  }
  return { chasing, shopping };
}
