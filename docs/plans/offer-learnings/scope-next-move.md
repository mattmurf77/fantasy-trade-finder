# Feature Scope — The next move (R2, WS5): mockup and revision generator

**Date:** 2026-11-10
**Entry point:** direct operator ask, via the offer-learnings plan (`plan.md` §1 row R2, §3 WS5)
**Builder:** WS5 builder session, branch `feat/next-move`
**Operator sign-off on waivers:** not yet. Two waivers below (analytics, TestFlight checklist) are
surfaced in the WS5 report; both follow from "no app UI this round".

The operator's words: "Mock it up, build it, control it via its own dedicated capability flag
(I'm skeptical with this one, I think it has the risk to just invite haggling and ruin the
value prop)." This round delivers a mockup in `mockups/next-move/` and a backend revision
generator behind `trade.next_move` (default off). Nothing is built in the mobile app, nothing
is wired into the deck (`_run_trade_job`) and no route is added: the operator picks a
treatment from the mockup first.

---

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED — no analytics needed because:** nothing user-facing ships. The generator
  has no caller outside its tests, so nothing can fire. Events are specced with the app UI,
  after the operator picks a treatment. For that round, the candidates are: a revision shown,
  sent, dismissed, and its provider outcome (which needs WS2's `trade.outcome_tracking`).

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **`trade.next_move`**, default **false**. Registered in
  `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json`, the release-mirroring flag
  fixtures (`release.json`, `onboarding-v2.json`, `profiles-on.json`, same key set) and
  `docs/config-reference.md`. Off: `trade_next_move.propose_revision` returns `None` before
  any evaluation; no other code path reads the module (structural test). Graduation: the
  operator picks a treatment from the mockup, the app UI is built behind this same flag, and
  its acceptance and haggling measures (sent revisions per thread, acceptance after a
  revision) are agreed before it is turned on.
- New env vars / `model_config` keys: **none**. The step bounds (10% and 20% of the trade's
  market value) are module constants with keyword overrides. Making them deploy-free knobs is
  deferred until there is a caller; the rollback lever is the flag.

## 3. Evidence scope

- [ ] Structural guard (`mobile/tests/check-*.js`): **n/a**, no mobile change.
- [x] **Unit tests:** `backend/tests/test_trade_next_move.py`: valid, bounded, keeps the core
  assets, at most one, absent when no valid revision exists, sender's side keeps passing the
  viewer checks, the evaluator in force is the one used (owner-v1, bilateral 1 and 2), flag off
  does no work, and no production module imports the generator. Every behavioural test is
  proven red against a named sabotage, listed in TEST_LEDGER.
- [x] **Code-walk proof:** the rule and its use of the evaluator are traced in the module
  docstring and in the D-NEXT decision entry; the measurement on synthetic leagues built from
  the real player-pool fixture is `measure_next_move.py` in this folder.
- **Measured:** on eight synthetic 12-team leagues built from the real player fixture, with the
  first ten deck cards of each treated as sent offers, a revision is found for 50/80 offers under
  owner-v1, 5/80 under bilateral 1, **17/80 under bilateral 2 (live)** and 13/80 under
  bilateral 3. The median step is about 12%. Under bilateral 2 most revisions remove an
  asked-for piece, because adding a fourth asset to a 2-for-1 is not an organic shape.
- [ ] **Manual TestFlight checklist:** **WAIVED** because there is no app surface this round.
- testIDs added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added. The smallest surface is a pure function; a route waits for the app UI |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention changes |
| `docs/architecture.md` | n/a | The module has no caller and is not part of any data flow yet |
| `living-memory/HLD.md` | n/a | Same |
| `docs/cross-client-invariants.md` | n/a | No value shared between clients |
| `docs/glossary.md` | updated | "Next move" entry |
| ADR or `DECISIONS.md` entry | updated | `D-217` — the revision rule and the no-route surface |
| `docs/config-reference.md` | updated | `trade.next_move` row |
| `mockups/CLAUDE.md` | updated | Index row for `next-move/` |

## 5. Ship gate declaration

- **CI green:** full backend suite run once at the end on this branch (result in TEST_LEDGER).
  `test_deck_pipeline_digest` is untouched: neither `_run_trade_job` nor any
  `DECK_PIPELINE_FUNCTIONS` member changes.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry with the test counts and
  sabotage names.
- **TestFlight verification:** none (no app change).
- Express lane declared by the operator? **No.**
