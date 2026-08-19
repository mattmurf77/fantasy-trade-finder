// consensusNote.ts — the consensus-basis sub-line on a trade card.
//
// WHY THIS IS ITS OWN MODULE. Until 2026-08-19 the copy lived as a literal
// inside TradeCard.tsx's JSX, gated on `basis === 'consensus'` and NOTHING
// else, and it said:
//
//     "…this is a balanced trade by consensus value."
//
// The app's own bar for "balanced" is 0.75 (`NORMAL_LOW`, the same number
// as `api/tradePregen.FAIRNESS_ON_THRESHOLD` — the `fairness_threshold` the
// client sends the generator in balanced mode). But the mobile fairness
// default flipped OFF on 2026-08-17, so the live generation floor is 0.50
// and cards ship all the way down to 0.501. Measured read-only against prod
// `deck_impressions` on 2026-08-19: **805 of 7,293 served consensus cards
// (11.0%) carried that sentence while sitting below 0.75** (band [0.501,
// 0.75), p10 0.7302, p50 0.8590). The product was asserting something untrue
// by its own definition.
//
// THE FIX REMOVES THE CLAIM; IT DOES NOT REPLACE IT (operator, 2026-08-19).
// Below the bar the sub-line TRUNCATES to its true half and stops. An earlier
// draft of this module put honest replacement copy there ("priced from public
// values, not an even split"); the operator struck it, correctly — the card
// already renders `TradeValueBar` (TradeCard.tsx, gated on `hasValueVerdict`)
// with `giveValue`/`receiveValue`/`favors`/`gap`, so direction AND magnitude
// are already on screen from the component its own comment calls the
// universal value verdict. Replacement prose would restate the bar.
//
// What survives is the half nothing else on the card says: "this league-mate
// hasn't ranked players yet" explains why this is a fair-value idea rather
// than a divergence card. No other element carries that. So the rule is:
// keep the explanation, drop the verdict, let the bar do the verdict's job.
//
// A pure total function, deliberately: `mobile/tests/check-consensus-balance-claim.js`
// transpiles and RUNS this module, so the gate is proven behaviourally at the
// band edges instead of grepped out of JSX (D-056 — there is no simulator to
// screenshot this on).
//
// Web parity: `web/js/app.js` builds the identical two strings from the
// identical prefix against the identical 0.75 constant, and the structural
// check reconstructs them from web source and compares byte for byte. The
// band is a cross-client encoding — see docs/cross-client-invariants.md
// § "Consensus balance claim".

import { NORMAL_LOW } from './tradePresentation';

/**
 * The app's own bar for calling a package balanced.
 *
 * Re-exported, never re-declared: `NORMAL_LOW` (utils/tradePresentation) and
 * `FAIRNESS_ON_THRESHOLD` (api/tradePregen) are both 0.75 today and the
 * structural check pins all three — plus the web literal — to the same value,
 * so a future edit cannot move one and leave the copy asserting the old band.
 *
 * It is a CONSTANT, not a server knob, on purpose: the two thresholds it
 * mirrors are both hardcoded module constants, and a claim of the form "this
 * is balanced" must be pinned to the definition of balanced, not to whatever
 * net the user happens to be generating at. (The generation floor moves — it
 * is 0.50 today. The definition does not.)
 */
export const CONSENSUS_BALANCED_MIN = NORMAL_LOW;

export interface ConsensusNote {
  /** Section label. Names the PRICING BASIS, not the verdict — always true. */
  label: string;
  /** The sub-line. Carries the balance claim ONLY when `balanced`. */
  body: string;
  /**
   * true only when the card is at or above the app's own balanced bar. The
   * one place the word "balanced" is allowed to appear in the copy.
   */
  balanced: boolean;
}

const LABEL = 'Fair-value idea';
const PREFIX = "This league-mate hasn't ranked players yet";

/**
 * Consensus-basis copy for a trade card.
 *
 * Two strings. The fail-safe direction is DOWN, and here it is STRUCTURAL
 * rather than merely tested: an absent or non-finite score fails the `typeof`
 * /`Number.isFinite` conjunct, so `balanced` is false and the claim cannot be
 * minted. The backend serializes `fairness_score` on every card (server.py
 * `trade_card_to_dict`; 7,293/7,293 non-NULL in prod), but the mobile
 * normalizer keeps a defensive `undefined` path for cached/legacy snapshots,
 * so the unknown case is reachable in principle and must not lie.
 *
 * `Number.isFinite`, not the global `isFinite`: the global coerces, so
 * `isFinite('0.9')` is true and a stringified payload would reach the
 * comparison and compare as a string.
 *
 * @param fairness 0–1 min/max package ratio (`TradeCard.fairness`).
 */
export function consensusNote(fairness: number | undefined | null): ConsensusNote {
  const balanced =
    typeof fairness === 'number'
    && Number.isFinite(fairness)
    && fairness >= CONSENSUS_BALANCED_MIN;
  return {
    label: LABEL,
    body: balanced
      // Unchanged from the pre-fix string, byte for byte: at or above the bar
      // the original claim is true, and 6,488 of 7,293 prod cards are here.
      ? `${PREFIX} — this is a balanced trade by consensus value.`
      // Below the bar (or unknown): the true half, full stop. No clause about
      // value — TradeValueBar already shows direction and magnitude.
      : `${PREFIX}.`,
    balanced,
  };
}
