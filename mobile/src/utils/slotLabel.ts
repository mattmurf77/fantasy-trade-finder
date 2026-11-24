// slotLabel.ts — the ONE short-name table for a lineup slot label.
//
// The server names starter slots with Sleeper's roster_positions vocabulary
// (QB, RB2, FLEX, SUPER_FLEX, WRRB_FLEX, REC_FLEX, numbered when repeated).
// The calculator's before/after lineup table shortened three of them inline;
// the deck card's impact block (CardImpactBlock) printed the raw name with
// "_" turned into a space, in a 34 pt column, so a Release pass at 402 pt
// width read "SU…" for SUPER_FLEX and "FL…" for FLEX (2026-11-22). Both
// surfaces now read this table. Pure, no imports: the structural guard
// transpiles and runs it.

const SLOT_SHORT: ReadonlyArray<readonly [string, string]> = [
  ['SUPER_FLEX', 'SF'],
  ['WRRB_FLEX', 'W/R'],
  ['REC_FLEX', 'W/T'],
  // After the three above, so only a bare FLEX / FLEX2 reaches it.
  ['FLEX', 'FLX'],
];

/** Short display name for a lineup slot. Numbered variants shorten too
 *  (SUPER_FLEX2 → SF2); anything not in the table is returned unchanged. */
export function slotShortLabel(slot: string): string {
  for (const [long, short] of SLOT_SHORT) {
    if (slot.startsWith(long)) return short + slot.slice(long.length);
  }
  return slot;
}
