# Feature Scope — Fairness formula (deck admission formula behind a flag)

> **Status (2026-11-15): measured, not adopted, code not merged.** No arm passed the rule, so the engine change (flag `trade.fairness_formula_v2`, `backend/fairness_formula.py`, the replay tool and its tests) was left out of `main`. It is kept on branch `feat/fairness-formula` (head 1ac1b027) for reference. Only this record is on `main` (D-267).

**Date:** 2026-11-15
**Entry point:** direct ask (operator-approved spec, [spec.md](spec.md))
**Builder:** builder subagent on `feat/fairness-formula`
**Operator sign-off on waivers:** needed for the §1 waiver (surfaced in the PR)

---

## 1. Analytics scope

- [x] **(c) WAIVED, no new events needed because:** the flag ships off and no knob changes. A deck built on a non-default formula is recorded in each card's frozen proof (`market.formula`, with the knobs), and the served ratio is already recorded per card, so decks can be told apart without a new event.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: `trade.fairness_formula_v2`, default **false** in `backend/feature_flags.py`, `config/features.json` and the three flag fixtures (`release`, `onboarding-v2`, `profiles-on`). Not in `FTF_FLAGS`. Graduation criterion: an arm passes the spec's rule on the research sample, is confirmed once on the held-back trades, the serving-policy question in the spec's technical design is decided, and the operator turns the flag on with that arm's knobs.
- New `model_config` keys (defaults = today's math): `fairness_formula_package_math` 1.0, `fairness_formula_exponent` 1.0, `fairness_formula_raw` 0.0, `fairness_formula_threshold_power` 1.0. Rollback lever: flag off + `POST /api/feature-flags/reload`, or the knobs back to their defaults. No deploy either way.

## 3. Evidence scope

- [x] **Structural guard:** n/a — no mobile, web or extension change.
- [x] **Unit tests:** `backend/tests/test_fairness_formula.py`: registration (code, config, three fixtures, knob seeds), knob validation, flag off never reads the knobs, each arm's side value and ratio on hand-computed numbers, the floor, flag-off decks byte-identical to `main` (golden digests of owner, r1, r2 and r4 decks computed on `main` before the change) with the knobs at every arm's values, flag on with default knobs byte-identical, a non-default formula changes a deck and its proofs revalidate, the replay tool on a synthetic fixture and the decision rule. Every new test was sabotage-checked (TEST_LEDGER).
- [x] **Code-walk proof** (flag off = today): `trade_gen_owner._Search.__init__` sets `self.formula = fairness_formula.active(self.config)`, which returns `None` before reading any knob when the flag is off (and when every knob is at its default). `_Search.evaluate` takes the formula branch only when `self.formula is not None`; otherwise the original lines run unchanged. The knobs' prefix `fairness_formula_` is not in any report's config filter (`owner_`, `package_`, `crown_`, `age_pref_`, `elo_value_`, `max_overpay_`), so report bytes do not change when the seeds are present.
- [x] **Manual TestFlight checklist:** none while the flag is off. If the operator turns it on with an arm's knobs: (1) open Trades with Balanced trades on; the deck loads; (2) no card shows a fairness under the arm's floor; (3) flag off + reload, cold start: the deck matches pre-flag behaviour.
- testIDs added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a because | no route, request or response shape changes (`fairness_score` keeps its meaning: the ratio the deck admitted on) |
| `living-memory/LLD.md` | n/a because | no schema, route or convention shift |
| `docs/architecture.md` | n/a because | one helper module read by the existing generator base class |
| `living-memory/HLD.md` | n/a because | no architecture shift |
| `docs/cross-client-invariants.md` | n/a because | no client constant changes; the 0.75 "balanced" bar is untouched |
| `docs/glossary.md` | updated | "Fairness formula" |
| ADR or `DECISIONS.md` | updated | D-267 |
| `docs/config-reference.md` | updated | flag row + four knob rows |

## 5. Ship gate declaration

- **CI green:** backend-tests, mobile-typecheck, testid-lint, on the pushed sha (main session).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-15 fairness-formula entry.
- **TestFlight verification:** only after the flag is turned on (checklist above).
- Express lane declared by the operator? no.
