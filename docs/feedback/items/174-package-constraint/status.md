# #174 — Trade-away package constraint · status

**State:** SHIPPED (2026-07-25, branch `teardown-remediation`, #156 finish batch).

**Feedback:** "if I select multiple players I want to trade away it will
only include at least one, rather than me saying I want to trade this
package away."

## What shipped

New additive generate param **`pinned_give_mode: 'all' | 'any'`**:

- `'any'` (default, absent, or junk) — historical semantics: each card's
  give side must include **≥1** pinned give player. Byte-identical to the
  pre-#174 engine when unset.
- `'all'` — every generated card's give side must include **EVERY**
  pinned give player ("trade this package away"). Give sides may still
  carry extra pieces on top of the package.

**Threading** (mirrors the existing pinned params): `/api/trades/generate`
body → `_kickoff_trade_job` → worker thread → `_run_trade_job` →
`TradeService.generate_trades` → `_generate_trades_v2` → all three
generators. Enforced in:

- `backend/trade_optimizer.py::generate_pair_trades_v3` (live path,
  `trade_engine.v3` on) — give-subset filter `pinned_set <= set(give_ids)`;
  pinned players were already always kept in the candidate pool.
- `backend/trade_service.py::_generate_for_pair_v2` — same filter in
  `_consider`, plus an `'all'`-gated force-include of pinned players into
  `give_candidates` (the divergence prune could otherwise drop one, making
  the full package unreachable; gated so `'any'` decks stay byte-identical).
- `backend/trade_service.py::_generate_consensus_for_pair` — `_emit` gate
  (1-for-1 shapes drop out with 2+ pins in `'all'`).
- Legacy (pre-v2) engine **ignores** the param, matching the
  `pinned_receive_players` precedent (`trade_engine.v2` is on in prod).

**Shape ceiling (honest limit):** generators enumerate at most 3 give
pieces (v3: 1–3 with |give|−|receive| ≤ 1; consensus: 2-for-1). Pinning
**4+** players with `'all'` therefore yields zero cards — surfaced by the
deck's existing "No trades found" empty state.

## Client

`TradesScreen` — "Trade as one package" toggle (`PackageToggle`, testID
`trades.package-toggle`, Chalkline binary-slider construction) renders
whenever 2+ give players are pinned, in BOTH the new two-column player
board and the classic single-column targeting section. **Default ON** per
the operator spec (state in `useFinderTargets.packageMode`, session-only).
Toggling resets the deck like any target change; generation sends
`pinned_give_mode:'all'` only when targeting is on, the toggle is ON, and
2+ give players are pinned (`mobile/src/api/trades.ts` GenerateBody).

The #186 "keep the send side" card action composes with this: it pins the
whole give side, so packageMode (default ON) holds it together.

## Tests

`backend/tests/test_finder_targeting.py` section 5:
- `test_pinned_give_mode_all_v2_pair_generator` — 'any' yields ≥1-pinned
  cards incl. at least one WITHOUT the full package; 'all' ⇒ every card's
  give ⊇ {uA, uB}.
- `test_pinned_give_mode_all_v3_optimizer` — same through the v3 path.
- `test_pinned_give_mode_all_consensus_generator` — unranked-opponent
  fallback honors 'all'.

Suite: 1086 passed, 1 skipped. `tsc --noEmit` clean.

## Docs

`docs/api-reference.md` (generate route row) updated.
