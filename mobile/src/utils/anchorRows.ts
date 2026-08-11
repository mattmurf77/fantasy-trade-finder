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
// LABELS ARE DERIVED, NOT AUTHORED HERE (audit A-16 / P1-7, 2026-08-11).
// Every rung's button text comes from TIER_LABEL — the ladder vocabulary
// shared by mobile, web, the extension and the OG renderer
// (docs/cross-client-invariants.md § Tier bands). Before this, the grid
// carried its OWN strings and FIVE of the eight disagreed with the tier the
// answer actually lands in, so a user tapped "1 2nd" and read back "2nd"
// inside a single interaction. Re-typing a label here re-creates that bug;
// mobile/tests/check-anchor-labels.js fails the build if anyone does.
//
// SCOPE OF THE GUARANTEE: exact at the DEFAULT anchor scale. A user who has
// set `users.anchor_scale` to N < 4 re-spaces the three multi-first rungs
// upward (server._anchor_target_elo, γ = log 4 / log N), so at N = 2 their
// "2 1sts" answer pins into firsts_4plus and reads back "4+ 1sts". That is
// by design and predates this change (cross-client-invariants.md § Tier
// labels ARE pick terms). The four single-pick rungs and `no_value` are
// scale-invariant, so any round-trip assertion must use one of those.
//
// Two rows of four, top-of-board first. Order is presentational; the keys
// are the contract.

import type { AnchorKey } from '../api/rankings';
import type { Tier } from '../shared/types';
import { TIER_LABEL } from './tierBands';

export interface AnchorRung {
  key: AnchorKey;
  label: string;
}

/** Which tier each rung's answer lands in at the default anchor scale.
 *  Encodes in CODE the name↔rung invariant that until now lived only in a
 *  doc sentence (cross-client-invariants.md) and a backend test
 *  (test_tier_occupancy.py). `no_value` is null ON PURPOSE — the server pins
 *  it BELOW every band (Elo 1100, under the `waivers` floor of 1150) and
 *  answers `tier: null`. See BELOW_LADDER_LABEL. */
export const ANCHOR_TIER: Record<AnchorKey, Tier | null> = {
  '4_firsts': 'firsts_4plus',
  '3_firsts': 'firsts_3',
  '2_firsts': 'firsts_2',
  '1_first': 'first_1',
  '1_second': 'second',
  '1_third': 'third',
  '1_fourth': 'fourth',
  no_value: null,
};

/** The ONE string for "below the ladder": the `no_value` button label AND the
 *  null-tier fallback both hosts render, so a rung and its confirmation can
 *  never disagree.
 *
 *  It BORROWS the `waivers` label rather than asserting `no_value === waivers`
 *  — the null above keeps the distinction in the type system. The borrow is
 *  deliberate: mobile's `tierForElo` has no lower floor, so a
 *  `no_value`-anchored player badges "FA" on the Tiers board the user looks
 *  at next, and the wizard should agree with the badge. The mobile/backend
 *  banding gap that makes that true is a separate, pre-existing issue, filed
 *  to NEXT.md rather than fixed here. */
export const BELOW_LADDER_LABEL = TIER_LABEL.waivers; // 'FA'

export const anchorLabel = (k: AnchorKey): string => {
  const t = ANCHOR_TIER[k];
  return t ? TIER_LABEL[t] : BELOW_LADDER_LABEL;
};

/** Presentational grid: two rows of four, top-of-board first. */
const ANCHOR_KEY_ROWS: readonly (readonly AnchorKey[])[] = [
  ['4_firsts', '3_firsts', '2_firsts', '1_first'],
  ['1_second', '1_third', '1_fourth', 'no_value'],
];

export const ANCHOR_ROWS: readonly AnchorRung[][] = ANCHOR_KEY_ROWS.map((row) =>
  row.map((key) => ({ key, label: anchorLabel(key) })),
);
