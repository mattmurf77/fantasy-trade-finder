# Feature Scope — Placement tier clamp (D-085)

**Date:** 2026-08-19
**Entry point:** direct ask (operator-selected from three options)
**Builder:** agent session `feat/placement-tier-clamp`
**Operator sign-off on waivers:** not needed (no waivers; two items raised for the operator in §6)

---

## 0. The change in one paragraph

`_shrink_user_elo` blends a personal Elo toward the consensus seed with
`w = n/(n + shrink_pseudocount)`, where `n` counts COMPARISONS. A manual tier
placement is an *assertion* of value, not a sample, and `w` cannot see
assertions — so a deliberately placed player with few head-to-head votes is
priced wherever consensus wants him, up to a full tier away from where the user
put him. This clamps the shrunk result to the Elo band of the tier the user
placed the player in (`RankingService.placement_bands()` → `tier_config.json`).
Consensus may still re-price him *inside* that band; it may never carry him out
of it. This is the already-shipped `pin_tier_bounded` voting rule applied one
layer further out, to how the engine PRICES the result.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this changes no user-visible
  surface, emits no new client interaction, and adds no data collection. It
  changes a number inside the existing valuation path. The existing
  `trade_impressions.basis` column already records the divergence/consensus
  split this is meant to move, so the effect is measurable with events that
  already exist — see (b) below.
- [x] **(b) Existing events cover it** — `trade_impressions` (`basis`,
  `mismatch_score`, `composite_score`) answers "did the share of
  `basis='divergence'` cards rise after this shipped?", which is the question
  the operator actually asked. Baseline captured in §3 evidence.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. The bands are derived at compute time
  from the pinned value the board already stores (`users.tier_overrides`), so
  every pre-existing placement is covered with no migration and no backfill.
- New/changed feature flags: **none** (no `config/features.json` entry; this is
  a `model_config` knob, not a client-visible flag).
- New `model_config` keys: **`placement_tier_clamp`** (default `1.0`).
  → `docs/config-reference.md` updated. **Ship-the-knob:** setting it to `0` via
  `PUT /api/admin/config` restores the pre-D-085 blend byte-for-byte with no
  deploy, and `_pin_cfg_key` is not involved, so it takes effect on the next
  generation. Pinned by `test_knob_at_zero_is_byte_identical`.

## 3. Evidence scope

- [x] **Structural guard:** WAIVED — backend-only change, no mobile surface. No
  `mobile/tests/check-*.js` applies.
- [x] **Unit tests:** `backend/tests/test_placement_tier_clamp.py` — 22 tests,
  new. Covers: the defect stated as a test; the clamp lowering AND lifting;
  consensus still re-pricing inside the band (monotone, edge-bounded); the bite
  decaying to exactly zero as `n` rises; re-placement as the correction path;
  unplaced players untouched; below-lowest-band pins untouched; gap-pin band
  widening; per-position band lookup; `_value_uncertainty` left alone;
  kill-switch identity; arm-A pinning; `confidence=None` early-out;
  `placement_bands()` agreeing with `_pin_bounds`, independent of
  `pin_tier_bounded`, dropping F2-released pins, empty on a swipe-only board.
  Updated: `test_analytics_p0.py` (`_FakeService.placement_bands`),
  `test_bakeoff_arm_a_golden.py` (knob added to the arm-A key list).

  **Band constants are read live** from `RankingService.tier_bands_for()` rather
  than hardcoded. D-084 moved `second`.min 1400→1370 and `third`.max 1395→1365
  mid-build; an earlier draft of this work hardcoded the old numbers and would
  have asserted the wrong thing silently. `test_band_constants_match_the_shipped_config`
  guards the guard.

- [x] **Code-walk proof:** `docs/plans/placement-tier-clamp/code-walk.md`
  (file:line-cited trace of the whole path, plus the gate-isolation argument).

- [x] **Manual TestFlight checklist:** WAIVED — backend-only, and the effect is
  a number inside the valuation path that no screen displays directly. The
  runtime question that *does* matter (does the divergence share move?) is
  answered by the `trade_impressions.basis` query in the code-walk doc, not by
  a human tapping through the app.

- `testID`s added/renamed: **none**.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. `POST /api/trades/generate` request and response shapes are byte-identical; the change is internal to the job worker. |
| `living-memory/LLD.md` | **updated** | Valuation-path note: `placement_bands()` is the single definition of "the tier the user placed him in", shared by the voting clamp and the pricing clamp. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. One existing call site (`server._run_trade_job`) reads one more map off the `RankingService` it already holds. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | n/a | **Verified, not assumed:** `backend/tier_config.json` is untouched (`git diff --name-only` does not list it). The bands are *read*, never redefined, so the five-client mirror is unaffected. The clamp is server-side only and no client is taught about it. |
| `docs/glossary.md` | **updated** | New term: **placement** (an Elo override written by a tier save or drag-reorder, as distinct from a comparison). |
| ADR or `DECISIONS.md` entry | **updated** | **D-085** — reserved for this work by the operator; not computed as max+1. |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — 3463 passed, 1 skipped (baseline on
  `a130dfc` was 3441 passed, 1 skipped; +22 is exactly this file). `tsc --noEmit`
  and `testid-lint` are unaffected — no TypeScript and no mobile files changed.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** n/a (no checklist written — see §3).
- Express lane declared by the operator? **no** — full gates.

## 6. Raised for the operator (NOT built)

Two things this change deliberately does not do:

1. **Gates still price on consensus.** The scope boundary in `trade_service.py`
   ("A GATE judges the real package") is respected: the clamp touches only the
   personal-valuation path. If the operator wants the fairness/surplus gates to
   respect placements too, that is a separate, larger decision — raised, not
   built.
2. **The bake-off does not exercise this knob.** `bakeoff_runner.gen_v2_cards`
   never passes `placements`, so the clamp is inert on every arm including the
   control. `MODEL_A_PROFILE` pins it to `0.0` anyway (belt and braces).
   Plumbing it through the runner was skipped on purpose: two sibling agents
   were editing `bakeoff_runner.py` concurrently. Consequence: the bake-off
   cannot currently measure this feature. Follow-up, not a defect.
