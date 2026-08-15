# Feature Scope — Trade-card narrative: positional claims must name a player who plays that position

**Date:** 2026-08-15
**Entry point:** direct ask (bug found by running the real engine against the operator's four Sleeper leagues)
**Builder:** session `peaceful-lumiere-e2a25b`
**Operator sign-off on waivers:** pending — §3 Maestro delta is waived (reason below)

---

## Problem

`backend/trade_narrative.py` paired a position taken from the roster analysis
(`match_context.user_needs` / `opponent_surplus`) with a player taken from the card
(`_top_received_name`, highest dynasty value, **no position filter**). Nothing linked
the two, so a QB-thin manager receiving a TE got:

> "Adds Brock Bowers to address your thin QB group."

Observed rate: 23 of 32 cards across the operator's four real leagues carried a
position-inaccurate sentence (the operator reads QB-thin in all four, so `needs[0]`
was almost always QB while the headline received asset was a RB/WR/TE).
`build_narrative` runs on both live paths (`trade_service.py:2358`, `:3225`), so this
shipped on every card.

## Fix

Each positional branch now resolves the player and the position **together** via
`_top_received(card, players, positions)` — the highest dynasty-value received player
whose own position is in the candidate set — and names that player's own position.
When nothing received fills a need, the branch falls through to the neutral
`"<player> comes back in a <fairness> package."` sentence rather than inventing a
benefit. The `fit_premium` branch's `needs[0]` fallback (same hazard) is gone: no
premium position → fall through.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** no new user action, surface, or
  state; this is a correctness fix to a string already carried on an existing card
  field. No event fires on narrative render today and this change does not create a
  reason for one.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none** — a correctness fix, not a behavior toggle. A
  flag here would mean shipping a knob that turns inaccurate copy back on.
- New env vars / `model_config` keys: **none**

## 3. Test scope (mobile test platform)

- [x] **WAIVED because:** no mobile code, no new/renamed `testID`, no navigation or
  layout change. The card already renders `narrative`; only the generated string's
  content changes, and its content is data-derived (depends on the live league's
  rosters), so a Maestro assertion could not distinguish correct from incorrect copy
  on a seeded run. Correctness is asserted in pytest instead (below).
- `testID`s added/renamed: none
- **Capture delta:** none — no visual change (same field, same layout).
- Smoke-suite impact: flows that open the deck render `narrative` as opaque text; no
  flow asserts its content. Unaffected.
- Backend: `backend/tests/test_trade_narrative.py` — 7 tests added:
  - TE-only return for a QB-thin user never names QB (the reported repro)
  - names the position the received player actually plays when it isn't `needs[0]`
  - overlap branch names the received player's position, not `overlap[0]`
  - a pick-only return fills no positional need
  - `fit_premium` names the premium position
  - `fit_premium` with no position does not borrow `needs[0]`
  - invariant sweep over every needs × received-position combination: a position
    token in the output must belong to a received player
  5 of the 7 fail against pre-fix `trade_narrative.py` (verified by stashing the fix).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added/renamed/removed; `narrative` field type and presence unchanged |
| `living-memory/LLD.md` | n/a | No schema/route/invariant convention shifted |
| `docs/architecture.md` | updated | Module table row for `trade_narrative.py` — line count + the position-honesty rule |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or color changed; narrative is server-rendered text |
| `docs/glossary.md` | n/a | No new domain term |
| ADR / `DECISIONS.md` | updated | `DECISIONS.md` — which received player a positional sentence names, and falling through instead of inventing a benefit |

## 5. Ship gate declaration

- **Simulator-gate tier:** **4** (backend-only; no route, schema, or mobile change) →
  no sim run; pytest is the gate. Full backend suite green: 2769 passed, 1 skipped.
- Evidence: `living-memory/TEST_LEDGER.md` entry for 2026-08-15. No
  `qa/sim-runs/last-sim-run.json` — Tier 4 requires no sim run.
- Operator deviation from the matrix: none.
