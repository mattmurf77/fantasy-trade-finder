# #264 — Manual calc trade options

**Report (app v1.11.0, screen TradeCalculator, severity bug):** "The manual
calc should still show the different trade options."

**Status: built 2026-08-08 (branch `teardown-remediation`, isolated worktree).**
Client-only — no backend change, no feature flag (the server branch this
consumes shipped 2026-07-27 behind SwapSuggestSheet).

## What "trade options" resolved to

The one-tap alternative-asset rows the calculator offers beside the verdict
(`EvenerRows` "Recommended to even it" + the `SuggestionCard` balance/package
lists). Full reasoning + evidence in `prd.md` §1.

The concrete hole: **In-league mode renders NOTHING while a trade is
half-built.** `favors`/`gap` are only computed when both sides are non-empty
(`backend/server.py`, `if give and recv:`), and both the evener block and
`balancePlan` are gated on that gap. Live ("Real values") mode escapes it only
because its package suggestions are ranked client-side over the consensus pool.
So the manual calculator shows options in one mode and not the other.

## What shipped

- `mobile/src/api/calc.ts` — `evaluateTradeInLeague` gained an optional
  trailing `oneSidedEveners` flag that adds `one_sided_eveners: true` to the
  Mode B body (the exact key `evaluateForSwapSuggestions` already sends). Omit
  it ⇒ byte-identical request. `CalcEvaluation.eveners` doc comment corrected.
- `mobile/src/components/InLeagueCalculator.tsx`
  - the verdict query passes `true`, so a one-sided read comes back with
    candidate assets for the EMPTY side (that side's owner's real roster +
    owned picks, sized against the filled side's package value);
  - `oneSidedAddTo` / `evenerAddTo` derive the target side from the RESPONSE
    (`ev.per_player` side counts), not from local state — rows, `+` handler and
    payload can never disagree while a newer evaluate is in flight behind
    `placeholderData`;
  - the ONE existing `EvenerRows` mount (the #251 slot, unchanged position)
    now covers both states, switching only its label: "Trade options — from
    your roster" / "— from @x's roster" when half-built, the verbatim
    "Recommended to even it — …" copy when two-sided and uneven.

Consolidated, not appended (#205): no new card, no new section, no new
component, no new testID. `EvenerRows`, `ConsensusVerdictCard`, live mode,
demo mode, the balance suggestions and the verdict card are untouched.

## Not built (stated, not faked)

Whole alternative **packages** in Mode B (live mode's "Fair returns"). Mode B
has no client-side package search, and inventing one next to a
server-authoritative verdict breaks the #78 confirm-every-suggestion rule; a
real one is a server sweep, i.e. `/api/trades/asset-ideas` — the finder, which
this screen already links to (#213). See `prd.md` §5.

## Verification (static only — batch QA owns runtime)

- `mobile && tsc --noEmit` → **clean, exit 0** (worktree has no `node_modules`;
  run via a temporary symlink to the main checkout's, removed afterwards).
- `python3 -m pytest backend/tests/test_trade_evaluate.py -q` → **41 passed**.
  No backend change; run as evidence for the contract this build depends on —
  the file already pins `one_sided_eveners` behavior:
  `..._opt_in_for_emptied_give_side` (caller's roster, window/cap/order, gap is
  still `None`), `..._from_opponent_for_emptied_receive_side` (opponent's
  roster), `..._absent_without_param`, and
  `..._param_ignored_on_two_sided_read` (two-sided responses byte-identical).
- Grep proofs: `one_sided_eveners` now reachable from
  `api/calc.ts:276` via `evaluateTradeInLeague`; the single `EvenerRows` mount
  in `InLeagueCalculator.tsx` is gated on `evenerAddTo` (not `ev.gap.add_to`).

## QA checklist (for the batch round)

1. In-league, add 1+ players to **You send** only → "Trade options — from
   @x's roster" rows appear under the trade window, above the verdict card;
   verdict still reads "Add a player to each side for a verdict."
2. Tap a row's `+` → the asset lands on **You receive**, the read goes
   two-sided, the label flips to "Recommended to even it — …" (or the rows
   clear if the trade came out even).
3. Mirror case: fill only **You receive** → "Trade options — from your
   roster"; `+` adds to **You send**.
4. Two-sided uneven trade → copy and rows identical to pre-#264.
5. Even two-sided trade → no rows (unchanged).
6. Partner switch while one-sided → receive side clears, rows re-derive for
   the new partner.
7. Untouchables are never offered (server-side, both directions).
8. ESPN league (no owned picks) → player-only rows, no pick labels, no error.
9. Live + Demo modes → unchanged in every state.
10. Maestro: `264-calc-one-sided-options` flow per `prd.md` §7.
