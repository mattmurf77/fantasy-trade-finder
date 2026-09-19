# Feature Scope — Per-round draft-pick year decay (D-079)

**Date:** 2026-08-19
**Entry point:** direct ask, from two operator decline reasons in prod `trade_pass_reasons` (2026-08-19T03:48:53Z and 03:46:12Z), plus three more from 2026-08-17
**Builder:** background session, branch `feat/pick-year-decay`
**Operator sign-off on waivers:** **needed — see §6.** Two waivers below (analytics, structural guard) plus one substantive divergence from external market data that the operator should see before this merges.

Full analysis: [docs/reviews/2026-08-19-pick-year-valuation.md](../../reviews/2026-08-19-pick-year-valuation.md)

---

## 0. What changes, in one line

The per-year value discount on a draft pick becomes a function of the pick's **round** instead of one flat 0.85 for everything, and **round 1 becomes flat (1.0)** — so a 2029 1st prices exactly like a 2026 1st. Rounds 2–4 are unchanged at 0.85.

## 1. Analytics scope

- **(c) WAIVED — no new analytics needed because:** this is a repricing of an existing asset class, and every quantity needed to measure it is already captured. `deck_impressions.features_json` already records `give_value` / `receive_value` / `surplus_margin` per served card, and `assets_json` already records pick ids with their season and round — those two fields are exactly what this investigation used to measure the defect (2048 cards, 58.5 % pick-bearing, 99 cross-year first-for-first swaps). The post-change measurement is the same query on later rows; no new event would tell us anything `assets_json` + `features_json` do not.
- **Existing events that answer the follow-up question:** re-run the corpus queries in the review doc's § "The measured defect" against `served_at > <merge date>`. Expected: the cross-year first-for-first swap count falls to **0** (the value gradient between any two 1sts is now exactly zero, so a value-seeking search cannot produce one), and player-for-far-out-1st cards disappear from the `overpay_ok`-gated set.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `draft_picks.pool_value` rows are **not** rewritten — the rate is applied at the existing write path (`sync_draft_picks`) and at read time by the same functions as before; no migration, no backfill.
- **New/changed feature flags:** none. Deliberately: a flag would gate *whether the code path runs*, but the risk here is entirely in the *number*, and a config knob at its old value is a more precise and more reversible kill switch than a flag. See below.
- **New `model_config` keys:** `pick_year_decay_r1` (1.00), `pick_year_decay_r2` / `_r3` / `_r4` (0.85) → documented in [`docs/config-reference.md` § Draft-pick year decay](../../config-reference.md#draft-pick-year-decay-d-079--pick_valuespy-db-seeded). Seeded into `_MODEL_CONFIG_DEFAULTS` with `ON CONFLICT DO NOTHING`, so an operator-tuned row survives redeploys.
- **Ship-the-knob — the deploy-free rollback lever:** set all four keys to `0.85` via `PUT /api/admin/config/<key>` (which calls `trade_service.reload_config`). That reproduces the pre-D-079 ladder byte-for-byte on both value scales, pinned by `test_pick_year_decay.py::test_all_rates_at_the_old_constant_reproduce_the_old_behaviour`. To revert **only** the round-1 product call while keeping the mechanism, set `pick_year_decay_r1 = 0.85` alone.

## 3. Evidence scope

- **Structural guard (`mobile/tests/check-*.js`): WAIVED because** there is no mobile code change. No client hard-codes a year discount — verified by `git grep` for `YEAR_DISCOUNT` and for pick-related `0.85` across `mobile/src`, `web`, `extension`: zero hits. Clients render server-supplied values; a structural check would pin nothing that exists.
- **Unit tests:** `backend/tests/test_pick_year_decay.py` — **12 new cases**: default rates; deep-round clamping onto `_r4`; live config reads; the `[0,1]` clamp (a rate > 1 would invert the arbitrage); the all-four-at-0.85 revert reproducing the old ladder on both scales; a 2029 1st equalling a 2027 1st; later rounds still decaying with round ordering intact at every horizon; **zero value gradient between any two 1sts** (the anti-swap invariant); the Adams overpay-gate flip; `compute_pick_value` on the same clock; round-aware rung relabelling; no-config fallback so a DB outage cannot take pricing down.
  **Seven existing test files retargeted**, each deliberately, each rewritten to assert the new intent *plus* a still-decaying round so "someone flattened every round" fails loudly: `test_owned_picks.py`, `test_dynasty_value_pick_scale.py`, `test_league_picks_tier.py`, `test_pick_value_scaling.py`, `test_pick_pricing_m6b.py`, `test_pick_rung_year_labels.py`, `test_pick_values_in_suggestions.py`.
- **Code-walk proof** (replaces what would once have been a simulator capture): the served-card behaviour changes because `trade_service.overpay_ok` (`backend/trade_service.py:1502–1521`) flips verdict on the operator's actual card, impression `c67c2fd1e97cb6bf`.
  - The gate: kill when `gap >= max_overpay_min_value (500)` **and** `gap / max(g, r) >= max_overpay_frac (0.25)`, over raw consensus sums including picks.
  - Before: Adams 1138.8 vs `pick_pool_value(1, 3)` = 1300.1 → gap **161.3**, ratio **0.124** → both floors missed → **served** (which is what prod did).
  - After: Adams 1138.8 vs 2117.0 → gap **978.2**, ratio **0.462** → both floors cleared → **killed**.
  - Pinned as a boolean assertion, not a numeric one, in `test_adams_no_longer_clears_the_overpay_gate_against_a_2029_first`.
- **Manual TestFlight checklist** (the only runtime evidence mobile now gets) — see [the review doc's Evidence section](../../reviews/2026-08-19-pick-year-valuation.md#evidence) for the numbered five-step version. Summary: no mid-tier veteran offered straight up for a far-out 1st; no 1st-on-both-sides-different-years card in ~30 swipes; a 2029 1st badges `first_1` and matches the 2026 1st's value; calculator says a 2029 1st ↔ 2026 1st is exactly even; a 2029 **2nd** still visibly worth less than a 2026 2nd.
- **`testID`s added/renamed:** none (no client change).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. The affected routes (`/api/league/picks`, `/api/rankings`, `/api/trio`, `/api/trades*`, `/api/trade/evaluate`) keep byte-identical response *shapes*; only numeric values inside existing fields move. |
| `living-memory/LLD.md` | **n/a** | No schema, route or invariant *convention* shifted. The convention that pick pricing has exactly one home (`pick_values`) is unchanged — this change reinforces it by routing `database.compute_pick_value` through the shared helper rather than its own constant. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. `pick_values` already lazily imported `trade_service`; `year_decay` uses the same seam. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated** | New section "Draft-pick year decay is PER ROUND — firsts are flat (D-079, 2026-08-19)". Registered because pick values reach users through five surfaces that must agree, and because a client re-deriving "far-out picks are worth less" would now contradict the server. |
| `docs/config-reference.md` | **updated** | New subsection "Draft-pick year decay (D-079)" + TOC entry: the four keys, their defaults, the corroboration for each, and the deploy-free revert. |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated** | § Excluded — the written decision the `test_bakeoff_arm_a_golden` knob-inventory guard demands: these four are asset valuation, not generation logic, and stay live for all three arms. |
| ADR or `DECISIONS.md` entry | **updated** | `living-memory/DECISIONS.md` **D-079**. Also `living-memory/OPEN_QUESTIONS.md` **Q-018** for the market divergence. No ADR: this is a parameter decision inside an existing architecture, not an architectural one. |
| `docs/glossary.md` | **n/a** | No new domain term ("year discount" / "pick ladder" already in use). |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` run locally and green (counts recorded in `living-memory/TEST_LEDGER.md`). `tsc --noEmit` and `testid-lint` are unaffected — no files under `mobile/` changed — but must still pass on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved.
- **TestFlight verification:** checklist written in §3; **not yet run** — it needs the operator on a build.
- **Express lane declared by the operator?** **No.** Full gates applied. Pick valuation is a cross-client invariant, which CLAUDE.md names as an explicit bright line against express treatment.

## 6. Waivers and divergences the operator must see

1. **Analytics waived** (§1) — existing `deck_impressions` fields already answer the follow-up question.
2. **Structural guard waived** (§3) — no mobile code change; no client hard-codes a discount.
3. **⚠️ The round-1 flat rule contradicts every external source I could read.** This is not a waiver, it is a divergence, and it is the one thing worth a second look before merge. DynastyProcess publishes an explicit rule (80 % of current-year value, applied flat to every round); FantasyCalc's 2027→2029 CAGR for firsts is 0.80; KeepTradeCut's is 0.83; DynastyCalc's is 0.93. **Three of the four discount firsts *harder* than later rounds** — the opposite of the "firsts flat, later rounds decay" model. The operator's direction was explicit and is implemented as given, and it does cleanly close both reported symptoms (a flat rate is the *only* rate that makes first-for-first year arbitrage structurally impossible). But we are now deliberately pricing firsts above market. Logged as Q-018, revertible with one config write. Numbers and sources in the review doc's [calibration section](../../reviews/2026-08-19-pick-year-valuation.md#external-calibration--and-where-it-disagrees-with-us).
