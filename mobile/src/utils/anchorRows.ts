// The pick-anchor rung grid — the ONE vocabulary for "worth how much in
// draft capital?".
//
// Extracted from PickAnchorScreen by draft-extensions W1 (lld §4.1.4) the
// moment a SECOND surface (the Draft Room's anchor sheet) started asking the
// same question. Copying the table would let a rung diverge between the
// wizard and the sheet, and the keys are a cross-client enum shared with the
// backend (`VALID_ANCHORS` in backend/server.py — see
// docs/cross-client-invariants.md), so a divergence would be a silent
// mis-valuation, not a layout bug.
//
// Two rows of four, top-of-board first. Order is presentational; the keys
// are the contract.

import type { AnchorKey } from '../api/rankings';

export interface AnchorRung {
  key: AnchorKey;
  label: string;
}

export const ANCHOR_ROWS: readonly AnchorRung[][] = [
  [
    { key: '4_firsts', label: '4 1sts' },
    { key: '3_firsts', label: '3 1sts' },
    { key: '2_firsts', label: '2 1sts' },
    { key: '1_first', label: '1 1st' },
  ],
  [
    { key: '1_second', label: '1 2nd' },
    { key: '1_third', label: '1 3rd' },
    { key: '1_fourth', label: '1 4th' },
    { key: 'no_value', label: 'No value' },
  ],
];
