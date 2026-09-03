# PRD — G-414 (#414): a lopsided 1-for-1 is balanced from the richer side, proportionally

> Build spec for the backend build agent. Plan: [plan-g414.md](plan-g414.md) · exact code contract:
> [lld-delta.md](lld-delta.md) · scope block: [scope.md](scope.md). **6 numbered requirements,
> 12 pytest items + 1 regression item, 5 code-walk targets, 5-step TestFlight checklist.**
> Every file:line was re-verified on 2026-09-02 against worktree HEAD `48f40de5`; the two
> plan cites that did not survive (the swapped v2/consensus labels, a few off-by-one lines)
> are corrected in lld-delta.md §0 and the corrected lines are used here.
> **Round 2 (2026-09-02):** the Planner's [review-round-1.md](review-round-1.md) is incorporated
> in full — see [reconciliation-log.md](reconciliation-log.md). Both blocking fixes landed:
> the acceptance fixture's X1 is **1550** with three validity pre-asserts (§4), and the
> TestFlight lever is the admin PUT route (§6.4 step 4).
> **Mini-round (2026-09-02, build-time gaps — [reconciliation-log.md §6](reconciliation-log.md)):**
> the helper's accept is now **two-tier** (R-A.3, lld-delta §3) — the round-2 single rule made
> the pass do less than D-143 on wide-gap cards; two helper tests added (T-11, T-12; now
> **21 functions / 26 node ids / 14 sabotages**); arm-A bookkeeping (`_PINNED_KNOBS` token +
> scope-phase2 exclusion row) and one declared test re-spec (arm C's `10 ** 9` leg) recorded in
> R-D and T-10. Decision label is **D-173 (unshipped parallel build; see D-175)** (G-413 took D-176).
>
> **Backend only.** No mobile, web or extension change. No schema, no flag, no route, no
> new analytics event. One new `model_config` key.

## Table of contents

- [1. The report and what ships](#1-the-report-and-what-ships)
- [2. Requirements](#2-requirements)
- [3. Guardrails (testable, therefore requirements)](#3-guardrails-testable-therefore-requirements)
- [4. Success criteria — the London/Lamb acceptance fixture](#4-success-criteria--the-londonlamb-acceptance-fixture)
- [5. Known limits](#5-known-limits)
- [6. Test plan (D-056)](#6-test-plan-d-056)
- [7. Docs and living-memory owed at ship](#7-docs-and-living-memory-owed-at-ship)
- [8. Out of scope](#8-out-of-scope)
- [9. The D-173 (unshipped parallel build; see D-175) entry, draft](#9-the-d-172-entry-draft)
- [Appendix A — follow-up item: streamed-then-trimmed cards carry no impression](#appendix-a--follow-up-item-streamed-then-trimmed-cards-carry-no-impression)
- [15. QA round 1 resolution](#15-qa-round-1-resolution-2026-09-02-test-coverage-only--no-production-code-changed)

---

## 1. The report and what ships

**Report (mattmurf77, 2026-08-31, v1.16.13):** *"Why is there a trade offer of Drake London for
ceedee straight up when there are other players I can add to make the trade more fair?"*

**What actually happened (plan §0–§1, prod evidence):** an ordinary model-deck card
(`match_swiped {source: "deck", trade_id: "f912a777"}`, `calc_find_a_trade_tapped {path: "model"}`)
gave London (consensus **5989.5**) for Lamb (**6862.0**) — a gap of **872.5** in the viewer's
favour, fairness 0.873. Every served arm calls that "fair enough to serve bare": R1 kills only at
≥ 25 % (`max_overpay_frac`, `trade_service.py:782`), the band floors are 0.50/0.55/0.85, and the
only mechanism that adds a viewer-side piece — the D-143 gap auto-sweetener — has an **absolute**
trigger of 1539 (`sweetener_gap_threshold`, `trade_service.py:516`; trigger at
`trade_optimizer.py:891`). 872.5 < 1539, so it never fired. The operator's bar is proportional;
the engine's was not.

**Fix, in one sentence:** a new `model_config` knob `sweetener_gap_frac` (default 0.10) tightens
the existing gap pass on every served arm to `min(1539, 0.10 × the card's larger side)`; when the
balanced sibling already exists the bare card yields to it; and a gap-sweetened card now also
carries the `sweetener` marker so the shipped "+ X added to balance the deal" line renders.
`sweetener_gap_frac ≤ 0` is byte-identical to today. Deploy-free either way.

| Item | Value |
|---|---|
| Knob | `sweetener_gap_frac` — default **0.10** — `model_config`, seeded `backend/database.py` after `:2445`, code default `backend/trade_service.py` after `:516` |
| Helper | **NEW** `trade_optimizer.gap_close_target(gv, rv, gap_threshold, gap_frac=0.0) -> float` |
| Pass | `trade_optimizer.close_value_gap(..., gap_frac=0.0)` — one new keyword |
| Arms | v3 (`trade_optimizer.py:710-772`), v2 divergence (`trade_service.py:6905-6983`), consensus (`trade_service.py:7101-7234`), gen_v2 / arm C (`trade_gen_v2.py:589`, `:737-794`) |
| Payload | `server.py trade_card_to_dict` after `:11820` |
| Rollback | `sweetener_gap_frac = 0` (this feature) · `sweetener_gap_threshold = 0` (the whole pass, D-143 pair rule unchanged) |

Default rationale (plan §2): 10 % is the codebase's existing near-equivalent band
(`min_package_band` 0.10 `trade_service.py:874`; `fatigue_decline_value_band` 0.10
`server.py:5021`), sits under R1's 0.25 kill so the sweetener only acts on cards R1 admits, and
clears the C1 fixture by **0.48 pp**: `_pick_fixture` (`test_engine_quality.py:188`) serves the
bare `uA→oB` at 1648.7 / 1822.1 = 0.9048 — a gap of **9.52 %** of max — so at 0.10 the pass does
not fire on it (`:247-266`). **Tuning gotcha (record in the config-reference row and D-173 (unshipped parallel build; see D-175)):** any
`sweetener_gap_frac` **below 0.0952** fires on that fixture — under `_ORTHOGONAL_GATES_OPEN`
(`:219-231`, `filler_min_frac 0` ⇒ `filler_ok` returns True at `trade_service.py:2030-2031`) the
287-value pick `PKu` is an eligible equalizer, the bare sweetens into the organic padded sibling,
R-A2 drops the bare, `_find(on, ["uA"], ["oB"])` is `None` and
`test_adding_a_pick_to_a_fair_package_does_not_raise_composite` goes red. Retune that fixture
**before** lowering the knob past 0.0952.

---

## 2. Requirements

### R-A — Proportional trigger on every served arm

1. New `model_config` key **`sweetener_gap_frac`**, float, default **0.10**. Present in **both**
   `_DEFAULT_CFG` (`trade_service.py`, after `:516`) and `_MODEL_CONFIG_DEFAULTS`
   (`database.py`, after `:2445`), equal. Read only via `_c("sweetener_gap_frac")`
   (`trade_service.py:1239-1245`).
2. **NEW** `backend/trade_optimizer.gap_close_target(gv, rv, gap_threshold, gap_frac=0.0)`
   returns `gap_threshold` when `gap_frac ≤ 0`, else `min(gap_threshold, gap_frac × max(gv, rv))`.
   Never returns more than `gap_threshold`. Pure — no config read.
3. `close_value_gap` gains keyword `gap_frac: float = 0.0` (after `recv_candidates=None`,
   `trade_optimizer.py:844`). Inside, **`eff = gap_close_target(gv, rv, gap_threshold, gap_frac)`
   is computed once from the ORIGINAL card's `gv, rv`** (`:890`). The trigger (`:891`) becomes
   `abs(gv − rv) > eff`. **The accept is two-tier** (lld-delta §3): walking candidates
   cheapest-first, the **first** gate-clearing candidate whose residual `abs(n_gv − n_rv) ≤ eff`
   is returned immediately (**tier 1**); if none reaches `eff`, the first gate-clearing candidate
   whose residual `≤ gap_threshold` is returned after the walk (**tier 2 = D-143**); a residual
   above `gap_threshold` is rejected outright (`:918`, unchanged); else `None`. Every gate
   (`:920-930`), the cheapest-first order and the return tuple are unchanged. At `gap_frac ≤ 0`
   the tiers coincide and the walk is byte-identical to today. **Consequences:** the pass never
   widens a served gap relative to D-143; a tier-2 result may carry `gap_after > eff` (still
   ≤ 1539) and is annotated and R-C-marked exactly like a tier-1 result; on the London fixture
   X1 is returned regardless of the tier-2 candidate (X2) walked ahead of it.
4. All four callers pass `gap_frac=_c("sweetener_gap_frac")`; the two that pre-check the gap
   before calling (consensus `trade_service.py:7204`, gen_v2 `trade_gen_v2.py:739`) pre-check
   against `gap_close_target(gv, rv, _GAP_THR, _GAP_FRAC)` so early-out and helper agree
   (both price with `_consensus_packages`/the same `package_value_v2` call — lld-delta §3).
5. **Shape-agnostic**, like the absolute trigger: the pass applies to any card whose gap exceeds
   `eff`, not only 1-for-1s. (Shape drift is watched, not gated — §5.)
6. At `sweetener_gap_frac ≤ 0` every arm and every helper call is **byte-identical** to
   2026-08-31 (`origin/main` `ce3f443c`).

### R-A2 — The balanced sibling beats the bare card

7. When `sweetener_gap_frac > 0` and a card's sweetened key **collides** with a card the same
   arm already emitted for this pair, the **bare card is dropped** and the balanced sibling is
   kept. Per arm (lld-delta §4):
   - v3 `trade_optimizer.py:741` — collect the bare card's `trade_id`; filter `cards` once
     **after** the loop, before `return cards` (`:772`); also discard its key from `card_keys`.
     **The pair serves one card fewer per collision — no backfill** (Planner ruling 2): the
     next-best candidate lives in `scored` above the diversity walk (`:647-657`) and re-entering
     it after the 3.4 rescue and the gap pass is not worth it — the served deck is
     over-generated and globally ranked in `_dedup_and_sort` (`trade_service.py:6449`), so a
     per-pair count is a generation budget, never a deck cap (D-154). Recorded in D-173 (unshipped parallel build; see D-175).
   - v2 divergence `trade_service.py:6940` — new `else:` branch → `continue` (the bare
     `TradeCard` at `:6960` is never built or appended at `:6983`).
   - consensus `trade_service.py:7228` — new `else:` branch → `return` from `_emit`.
     **Outcome-level invariant (Planner ruling 1), which T-7-style assertions must state at the
     key level only:** *after `_emit` enumeration, at most one card carries the balanced key and
     no bare card survives whose balanced key is present.* Both enumeration orders satisfy it —
     bare-first sweetens in place (`:7228-7234`) and the later organic sibling dies at
     `:7138-7139`; sibling-first hits the new `else: return`. Because 1×1s enumerate before 2×1s
     (`:7265-7279`), the only *reachable* sibling-first case is two bares sweetening to the
     **same** combo (`A→R` closed with `B`, then `B→R` closed with `A`). Do **not** pre-populate
     `seen` to make the site order-independent. The survivor's annotation differs by path
     (in-place carries `gap_sweetener` + the R-C line; an organic sibling carries neither) —
     accepted.
   - gen_v2 — **no collision rule** (Planner ruling 3): arm C sweetens at enumeration
     (`trade_gen_v2.py:737-802`, `s_give, s_recv` rebound at `:802`) *before* `_dedup_batch`
     (`:857-882`), so a closable bare never reaches dedup as bare; the exact-key duplicate with
     an organic sibling collapses at `:865-867`, differing only in annotation. An unclosable bare
     with an organic balanced sibling cannot occur (the sibling passed the same gates with X1,
     so `_gap_gates_ok` `:591-628` accepts X1 too — unless a cheaper asset closed first, which is
     a *different* balanced sibling at Jaccard 0.5, both kept). **T-4a (arm C) asserts the
     outcome:** no surviving card for R is bare with gap > eff.
8. At `sweetener_gap_frac ≤ 0` the collision paths are byte-identical to today: bare kept
   unsweetened, sibling kept, C1's "fewer pieces wins" tie-break
   (`test_engine_quality.py:270-281`) still orders them.

### R-C — The balanced card says so on the wire

9. `trade_card_to_dict` (`server.py:11755`; block `:11810-11820`) additionally serialises
   `out["sweetener"] = {"player_id": gap_sweetener["player_id"], "side": gap_sweetener["side"]}`
   **iff** the card has `gap_sweetener` and **no** Tier-3 `sweetener`. Precedence: Tier-3 wins
   when both are set. `gap_sweetener` is always serialised in full beside it (unchanged). Cards
   with neither are byte-identical. Exactly two keys in the mirrored dict — never `gap_before`/
   `gap_after`. No client change: `mobile/src/api/trades.ts:86-95` → `TradeCard.tsx:235-240`,
   `:734`/`:766`; `web/js/app.js:3655-3665`.

### R-D — Master switch outranks the fraction (arm A pin)

10. `sweetener_gap_threshold ≤ 0` disables the pass entirely regardless of
    `sweetener_gap_frac`, on every arm — the `_GAP_THR > 0` guard (`trade_optimizer.py:711`,
    `trade_service.py:6926`, `:7204` left operand, `trade_gen_v2.py:737`) precedes every
    frac-dependent branch. `bakeoff_profiles.MODEL_A_PROFILE` (`:98-105`) is **not edited** and
    does not list the new key. **Arm A bookkeeping (mini-round, Gap 3):**
    `test_bakeoff_arm_a_golden.py::test_no_generation_knob_was_added_without_an_arm_a_decision`
    (`:724-727`) fails on any `_DEFAULT_CFG` key absent from `_PINNED_KNOBS` (`:527`), so the
    builder adds the token `sweetener_gap_frac` there **and** an exclusion row to
    `docs/plans/three-model-bakeoff/scope-phase2.md` on the `package_floor_cross` "inert
    companion" precedent (`:122`): inert while `sweetener_gap_threshold ≤ 0`, which
    `MODEL_A_PROFILE` pins. The golden capture is untouched. **Retired invariant (Gap 2):** "a
    huge absolute threshold ≡ off" no longer holds — `≤ 0` is the master switch; the one test
    that pinned it is the declared re-spec in T-10.

### R-E — Seed/default parity

11. `_DEFAULT_CFG["sweetener_gap_frac"] == dict(_MODEL_CONFIG_DEFAULTS)["sweetener_gap_frac"]`.

### R-F — Docs and decision record (see §7)

12. `docs/config-reference.md` new row + the stale arm-C sentence at `:996` fixed;
    `docs/api-reference.md:299` card-shape comment amended and `gap_sweetener` documented;
    `docs/plans/three-model-bakeoff/scope-phase2.md` exclusion row for `sweetener_gap_frac`;
    `living-memory/DECISIONS.md` gains **D-173 (unshipped parallel build; see D-175)** (§9) + index row. Same PR as the code.

---

## 3. Guardrails (testable, therefore requirements)

| # | Guardrail | Mechanism (unchanged code the tests re-prove) |
|---|---|---|
| G-1 | Untouchables are never a give-side equalizer; not-interested players are never a receive-side equalizer — for the proportional trigger exactly as for the absolute one | `trade_optimizer.py:905-908` |
| G-2 | The pass never empties a deck and **never widens a served gap relative to D-143**: it replaces in place (tier 1 to `eff`, else tier 2 to the D-143 line — every card D-143 closed is still closed at least as far), or drops a bare card **only** when its balanced sibling is in the same emitted set; a card with no gate-clearing candidate under 1539 is served bare | `close_value_gap` two-tier accept (lld-delta §3); `None` → `continue`/fall-through; R-A2 per-arm rule |
| G-3 | Every arm's gate stack is re-earned on the sweetened combo (filler floor, pick-swap, presentment, surplus/Elo-gap, `user_gain_epsilon` + raw-loss + `user_gain_ok_1for1` on consensus, arm C's `consolidated_value` band) | `_gap_extra_ok` `trade_optimizer.py:715-725`, `trade_service.py:6907-6918`; `_gap_gates_ok` `:7104-7129`, `trade_gen_v2.py:591-…` |
| G-4 | The equalizer clears the junk-filler floor: ≥ max(0.25 × headliner, 450) — so for a ~6k headliner the smallest sufficient piece is ≥ ~1.5k | `filler_ok` `trade_service.py:2008-2042`, knobs `database.py:2466`, `:2468` |
| G-5 | Past-decision and R4 exclusion keys are re-applied to the **sweetened** key | v2/v3: `_dedup_and_sort` `trade_service.py:4902-4926`; gen_v2: `trade_gen_v2.py:594-595` |
| G-6 | `gap_sweetener` payload shape `{player_id, side, gap_before, gap_after}` unchanged; `features_json.gap_sweetener` impression stamp unchanged | `trade_optimizer.py:765-769`; `server.py:4519-4524` |
| G-7 | Card ids are unchanged — a sweetened card keeps the id it minted | `trade_optimizer.py:617`, `trade_service.py:6961`, `:7244`, `trade_gen_v2.py:1193` |

---

## 4. Success criteria — the London/Lamb acceptance fixture

**Fixture (literal values, `_isolate`-style `_cfg` snapshot/restore as `test_gap_sweetener.py:55-66`):**
user gives **G = 5989.5** (London), receives **R = 6862.0** (Lamb); the user's roster also holds
**X1 = 1550** and **X2 = 600** plus the 200-value fill bodies; all WR; opponent roster `[R]` + bodies.
Consensus values are the `_mini_league` / `_consensus_league` pattern with the four numbers swapped
(`test_gap_sweetener.py:94-110`, `:191-215`).

**Why 1550, not 1600 (Planner objection 1, blocking).** The legal X1 window flags-off is
**[1497.4, ≈1606]**: the filler bar `0.25 × 5989.5` at the bottom (`filler_ok`,
`trade_service.py:2029-2042`) and the consensus `user_gain_epsilon` edge `rv − gv ≥ 0` at the top
(`:7114`; X1 = 1600 lands 5.2 units under it, X1 = 1610 is −3.2 over). 1550 sits mid-window on
both edges and closes in **both** flag regimes below.

**Three fixture-validity pre-asserts** (in the fixture helper, before any behavioural assert —
a failure here means the shipped math drifted, and the fix is to move X1/X2 inside the window,
never to move `eff`):

- (a) `[G, X2]` leaves residual `abs(gv − rv) > eff` **and** `≤ gap_threshold` — X2 is a
  **tier-2 candidate** at the helper level (762.2: over the proportional target, under the D-143
  line), so it cannot reach `eff` but would be D-143's answer if nothing better existed;
- (b) `X1 ≥ 0.25 × G` **and** `X1 ≥ asset_floor_abs` (450) — X1 clears the filler bar 1497.4;
- (c) `[G, X1]` has `gv < rv` — the consensus epsilon edge holds.

Arithmetic the fixture rests on (market package math, `_package_value_market`
`trade_service.py:1675-1700`; `package_adj_gamma_market` 0.5, `package_floor_cross` 0.40,
`package_discount_cap` 0.35 — `trade_service.py:97-99`, `:115`). **Two regimes:** the test truth is
**flags OFF** (`_isolate` uses `DEFAULT_FLAGS`, `test_gap_sweetener.py:58`); prod has
`trade.crown_asset: true` (`config/features.json:43`), so the single-asset receive side earns a
crown credit (`crown_rate_market` 0.08 × phase, `trade_service.py:1689-1700`; R = 6862 ≥
`crown_elite_value` 6000, G = 5989.5 does **not**). Acceptance holds in both.

| Card | give pkg (both regimes) | receive pkg — flags OFF | gap · vs `eff` = min(1539, 0.10 × 6862) = **686.2** | receive pkg — prod (crown ON) | gap · vs `eff` = min(1539, 0.10 × 7251.0) = **725.1** |
|---|---|---|---|---|---|
| `[G] → [R]` (bare) | 5989.5 (single asset, undiscounted) | 6862.0 | **872.5** > 686.2 ⇒ **fires** (≤ 1539 ⇒ at frac 0 it does **not**) | 7251.0 | **1261.5** > 725.1 ⇒ fires (≤ 1539 ⇒ at frac 0 it does not) |
| `[G, X2] → [R]` | 5753.3 + 346.5 = 6099.8 | 6862.0 | 762.2 > 686.2 but ≤ 1539 ⇒ X2 is a **tier-2 candidate** at the helper level (walked first, remembered, not returned because X1 reaches tier 1); in the served arms 600 < the 1497.4 filler bar removes it before either tier | 7365.5 | 1265.7 > 725.1, ≤ 1539 ⇒ tier-2 candidate likewise |
| `[G, X1] → [R]`, X1 = 1550 | 5753.3 + 1062.0 = **6815.3** | 6862.0 | **46.7** ≤ 686.2 ⇒ X1 closes at **tier 1**; ratio 0.993; `gv < rv` ⇒ viewer still ≥ even | 7302.5 | 487.2 ≤ 725.1 ⇒ tier 1 |
| `[G, X1'] → [R]`, X1' = 1700 (T-4a-ov only) | 5753.3 + 1187.7 = **6941.0** | 6862.0 | 79.0 ≤ 686.2 — helper accepts, but `gv > rv` ⇒ consensus `_gap_gates_ok` **rejects** (viewer would pay) | 7278.5 | 337.5 — in prod the crown credit keeps `gv < rv`, so the overshoot case is a flags-off test, not a prod observation |

(Give side is cross-benchmarked against `v_max` = 6862 because it lacks the trade's best asset:
contribution = v·(0.40 + 0.60·√(v/6862)). Prod column: `naive_skew` = |naive_give − 6862| /
min(naive_give, 6862), phase = 1 − skew / 0.5, credit = 6862 × 0.08 × phase. Hand-computed;
the Planner's tool run agrees to ±0.1 for the `[G, 1550]` / `[G, 600]` rows. Note the prod bare
gap is 1261.5 — 17.4 % of max — which is what the served card actually showed; the plan's 872.5 /
12.7 % is the raw-value gap.)

**Accept iff, on this fixture:**

1. **Defaults** (`sweetener_gap_threshold` 1539, `sweetener_gap_frac` 0.10): the served card for
   R is `[G, X1] → [R]`, `gap_sweetener == {"player_id": "X1", "side": "give", "gap_before": 872.5,
   "gap_after": ≤ 686.2}`, `abs(give_value − receive_value) ≤ 686.2`, and the serialised payload
   carries `"sweetener": {"player_id": "X1", "side": "give"}` — on the helper, on v3, on v2
   divergence, on consensus and on arm C. **X1 regardless of walk order:** at the helper level
   X2 is walked first as a tier-2 candidate and X1 still wins (tier 1) — a helper that returned
   the first tier-2 hit would answer X2 (T-12).
2. **`sweetener_gap_frac = 0`**: the bare `[G] → [R]` is served unsweetened, `gap_sweetener is None`,
   gap 872.5 intact, no `sweetener` key — byte-identical to today.
3. **`sweetener_gap_threshold = 0`, `sweetener_gap_frac = 0.10`**: nothing fires on any arm
   (`gap_sweetener is None` everywhere).
4. **Sibling rule (key-level facts only):** on a fixture where the arm already emits
   `[G, X1] → [R]` organically, frac 0.10 ⇒ no card with key `[G] → [R]` survives, exactly one card
   with key `[G, X1] → [R]` survives, deck size exactly one smaller; frac 0 ⇒ both keys present,
   bare first. (Annotation on the survivor is path-dependent — not asserted.)
5. **Consensus epsilon window (T-4a-ov):** with the equalizer at 1700 instead of 1550, the
   consensus arm serves the card **bare** (`gap_sweetener is None`, deck for R non-empty) even
   though the helper alone would accept it — the viewer never pays to balance a card they were
   already winning.
6. **Tier-2 fallback (T-11):** on `_mini_league` (G 5400 / R 7000 / X1 1500 / X2 600) with
   `gap_frac=0.10` (eff = 700), the helper returns X1 with residual 977.7 — over `eff`, under
   1539 — rather than `None`; the four legacy assertions at `test_gap_sweetener.py:235`, `:330`,
   `:368`, `:431` stay green **unedited**.
7. **Regression:** `pytest backend/tests` fully green, with `test_gap_sweetener.py`,
   `test_engine_quality.py:247-281`, `test_knockout_refine.py`, `test_shape_knob.py`,
   `test_bakeoff_challenger.py` **unedited**; `test_bakeoff_arm_a_golden.py` edited only by the
   `_PINNED_KNOBS` token; `test_gap_sweetener_arm_c.py` edited only by the declared re-spec at
   `:239` (T-10).
8. **Prod replay** (`scripts/deck_eval.py`, see §6.2) recorded in TEST_LEDGER at frac 0 vs 0.10,
   with the 3×1 tripwire evaluated.

---

## 5. Known limits

- **Shape drift.** A 2-for-1 above the trigger becomes a 3-for-1 (`close_value_gap` has no shape
  check; prod `v3_shape_max_delta` is 2.0 while the code default is 1.0, `database.py:2545`). This
  already happens under the absolute trigger; it will be more frequent. Watched via the deck_eval
  readout (§6.2). If the 3-for-1 share jumps, the follow-up is a knob restricting the frac trigger
  to `len(richer side) == 1` — **not built now**.
- **Latency.** v3/v2/consensus run the pass per served card (≤ `max_per_opponent`); gen_v2 runs it
  per passing combo (`trade_gen_v2.py:738`) and will fire far more often. Watch `gen_ms` p90 against
  the D-154 budget in the deck_eval readout. Each candidate costs one `package_value_v2`.
- **Honest emptiness.** A roster with nothing between the filler floor (~0.25 × headliner) and the
  overshoot bound serves the card bare; on a consensus card the equalizer also may not push the
  viewer below even (`trade_service.py:7114`) — for the London fixture that window is X1 ∈
  [1497.4, ≈1606] flags-off (wider in prod, where the crown credit lifts `rv`). Expected — the
  pass narrows gaps, it never invents pieces. Pinned by T-4a-ov.
- **Presentation only marks; it does not explain the number.** The mobile card shows "+ X added to
  balance the deal" but not the gap it closed (`gap_before/gap_after` stay server-side and in
  `features_json`). Adequate for #414; not a promise of a value-bar annotation.
- **A tier-2 card is "balanced" only to the D-143 line.** When no equalizer reaches `eff`, the pass
  returns the D-143 result (residual ≤ 1539 but > 10 %), annotates and marks it like any other
  sweetened card, and the value bar may still read a visible lean. That is strictly better than
  the bare card and identical to what shipped on 2026-08-22; `features_json.gap_sweetener.gap_after`
  distinguishes the tiers after the fact.

---

## 6. Test plan (D-056)

Maestro and the simulator are retired ([D-056](../../../../living-memory/DECISIONS.md)); no flows,
no captures, `FTF_SKIP_SIM_GATE=1` is the standing pre-push posture. No `mobile/tests/check-*.js`
suite is added or edited — no mobile file changes (scope.md §3 says why).

### 6.1 pytest — `backend/tests/test_gap_sweetener_frac.py` (NEW)

Literal fixtures; `_cfg` and flags snapshot-restored exactly like `test_gap_sweetener.py:55-66`
(copy the `_isolate` autouse fixture, `_elo_for_value`, `_bodies`). Each test names the
requirement it proves and a **sabotage** — a plausible wrong implementation that must go RED, not
the textual negation of the assertion.

| # | Test | Proves | Named sabotage (must go RED) |
|---|---|---|---|
| **T-1** | `test_helper_frac_trigger_closes_a_proportional_gap` — London fixture (X1 = **1550**, X2 = 600) through `close_value_gap(["G"], ["R"], gap_threshold=1539.0, gap_frac=0.10, fairness_threshold=0.75, …)` ⇒ returns `("X1", "give", …)`, `abs(n_gv − n_rv) ≤ 686.2`, `n_gv < n_rv`; the fixture helper runs the **three validity pre-asserts** of §4 first ((a) `[G, X2]` residual > eff **and** ≤ 1539 — a tier-2 candidate, (b) X1 ≥ filler bar 1497.4, (c) `[G, X1]` gv < rv); then the **same call with `gap_frac=0`** ⇒ `None` (872.5 < 1539) | R-A.2, R-A.3, §4-1/2 (helper level) | **S-1 "additive frac":** implement `eff = gap_threshold + frac × …` or compare `abs(gv−rv) > gap_frac × max` only when it exceeds `gap_threshold` — the trigger never tightens; the frac-0.10 call returns `None`. |
| **T-2** | `test_helper_frac_never_loosens_the_absolute_target` — `gap_close_target(20000, 16000, 1539.0, 0.10) == 1539.0`; `gap_close_target(5989.5, 6862.0, 1539.0, 0.10) == pytest.approx(686.2)`; and through `close_value_gap` on a 20k/16k package a candidate whose **residual gap is in `(1539, 2000]`** — over the absolute target but under `0.10 × 20000` — is rejected in **both** tiers (`:918` is the D-143 line for tier 2 as well). **Expected values under two-tier: unchanged** — on a 20k/16k package `eff == gap_threshold`, so tier 1 ≡ tier 2 and the only residual that separates the correct `min` from the sabotage is that band | R-A.2 "never loosens" | **S-2 "frac replaces threshold":** `eff = frac × max(gv, rv)` with no `min` — a 20k package tolerates a 2000 gap and that candidate is accepted at tier 1. |
| **T-3** | `test_helper_frac_default_kwarg_is_byte_identical` — parametrised over `test_gap_sweetener.py`'s five helper cases (`:112-178`) and the pools case (`:391-403`), each called with an **explicit** `gap_frac=0.0` and asserting the **literal** expected result, not equality with the default call: `_mini_league` ⇒ `("X1", "give", ["G","X1"], ["R"], …)` with gap ≤ 1539 (977.7); the gap-500 case (`values2`, `:149-153`) ⇒ `None`; the unclosable roster ⇒ `None`; untouchable X1 ⇒ `None`; `extra_ok_fn=lambda g, r: False` ⇒ `None`; `give_candidates=["X2"]` ⇒ `None` and full roster ⇒ `"X1"`. **Expected values under two-tier: unchanged** — at `gap_frac=0.0`, `eff == gap_threshold` and tier 1 ≡ tier 2 ≡ today's single rule | R-A.6 | **S-3 "zero means zero tolerance":** treat `gap_frac == 0` as "close to exactly even" (`eff = 0`) — the gap-500 case returns a sweetener instead of `None`. (A tuple-equality-with-default-call form would pass under S-3 too, because both calls resolve to the same `eff`; the literal form is what goes red.) |
| **T-11** | `test_helper_tier2_fallback_narrows_when_no_candidate_reaches_eff` — `_mini_league` (G 5400 / R 7000 / X1 1500 / X2 600; `:94-110`) with `gap_frac=0.10` ⇒ eff = 700.0; X2 residual 1649 > 1539 (rejected), X1 residual **977.7** (> eff, ≤ 1539) ⇒ returns `("X1", "give", ["G","X1"], ["R"], …)` with `700 < abs(n_gv − n_rv) ≤ 1539`; and the same through v3 via `_v3_cards` (`:298-324`, gap 2908.7 → 1336.5) ⇒ served card has `gap_sweetener` with `gap_after` in `(eff, 1539]` | R-A.3 tier 2, G-2 "never widens vs D-143", §4-6 | **S-11 "drop tier 2":** keep only the `≤ eff` accept — the helper returns `None`, the card is served bare with its full 1600 gap, and `test_gap_sweetener.py:235/:330/:368/:431` go red alongside T-11. |
| **T-12** | `test_helper_tier1_beats_tier2_regardless_of_order` — London fixture (X1 1550, X2 600) with `gap_frac=0.10`: the cheapest-first walk meets X2 first (tier 2, residual 762.2) and X1 second (tier 1, 46.7) ⇒ returns **X1** with residual ≤ 686.2; additionally, with X1 removed from the roster ⇒ returns **X2** (tier 2 is what remains) | R-A.3 tier 1 precedence, §4-1 "X1 regardless of walk order" | **S-12 "first tier-2 hit wins":** `return` on the first candidate with residual ≤ `gap_threshold` (i.e. keep today's early return) — answers X2 and leaves a 762 gap when a 47 gap was available. |
| **T-4a** | `test_<arm>_frac_card_is_sweetened_at_default` × 4 — v2 divergence (`_v2_cards` pattern `:350-358`), consensus (`_consensus_league` `:191-224` with London/Lamb elos, X1 at **1550**), v3 (`_v3_league`/`generate_pair_trades_v3` `:261-324`, values rescaled so the served card's gap is 0.10–0.22 × max: > `eff`, < 1539), arm C (`test_gap_sweetener_arm_c._league` `:124-160` pattern, seed board rescaled likewise) ⇒ served card carries `gap_sweetener.side == "give"`, `gap_after ≤ eff`, `abs(give_value − receive_value) ≤ eff`. **Arm C additionally asserts the outcome invariant of R-A2.7:** no surviving card for R is bare with gap > eff (the dedup collapse, not a collision rule, is what guarantees it) | R-A.4 (all four callers), §4-1; R-A2.7 (arm C) | **S-4a "one caller missed":** wire three arms and forget one (the consensus site is the likeliest — its pre-check at `:7204` must change **and** the kwarg must be passed). The forgotten arm's test stays bare. |
| **T-4b** | `test_<arm>_sabotage_frac_zero_brings_the_bare_card_back` × 4 — `ts._cfg["sweetener_gap_frac"] = 0.0` on the same fixtures ⇒ `gap_sweetener is None` on every card and the full gap is back | R-A.6, §4-2 (the rollback lever, proven live per arm) | **S-4b "frac read outside `_c`":** read `_DEFAULT_CFG["sweetener_gap_frac"]` or a module constant instead of `_c(...)` — the `_cfg` override is ignored and the card stays sweetened. |
| **T-4a-ov** | `test_consensus_epsilon_window_serves_the_overshoot_bare` — the consensus fixture with the equalizer at **1700** (flags-off `[G, X1']` gv 6941.0 > rv 6862.0): the helper alone accepts it (gap 79 ≤ eff, ratio 0.989) — asserted directly — but the served consensus card for R is **bare**, `gap_sweetener is None`, deck for R non-empty. Proves the viewer never pays to balance a card they were winning (§4-5; Planner ruling 5) | G-2, G-3 (the `_gap_gates_ok` epsilon at `trade_service.py:7114`) | **S-ov "helper gates are enough":** pass `extra_ok_fn=None` at the consensus site, or drop the `user_gain_epsilon` line from `_gap_gates_ok` — the card sweetens with the viewer paying 79. |
| **T-5** | `test_master_switch_beats_frac` — `sweetener_gap_threshold = 0.0`, `sweetener_gap_frac = 0.10` ⇒ no `gap_sweetener` on any of the four arms; plus `assert "sweetener_gap_frac" not in MODEL_A_PROFILE` | R-D, §4-3 | **S-5′ "threshold ≤ 0 means unset":** `gap_close_target` returns `gap_frac × max(gv, rv)` when `gap_threshold <= 0`, **and** a caller guard of `if GAP_THR > 0 or GAP_FRAC > 0` — that implementation sweetens under arm A's pin and T-5 goes red. (The earlier S-5 "`or` instead of `and`" alone is wrong-but-inert: it reaches the helper with `gap_threshold = 0` ⇒ `eff = min(0, …) = 0` ⇒ nothing ever closes ⇒ T-5 still passes. Retired.) |
| **T-6** | `test_untouchable_never_balances_a_frac_card` — London fixture, `untouchable_ids={"X1"}` on the helper **and** on one served arm ⇒ the card is served **bare** (X2 too small), `gap_sweetener is None`, and the deck for R is non-empty | G-1, G-2 | **S-6 "drop the unclosable":** on `closed is None` with frac > 0, drop the card ("it's over the line") instead of serving it bare — the deck for R comes back empty. |
| **T-7** | `test_sibling_wins_over_bare_when_frac_on` — **v3** via the `_v3_cards` pattern with `max_cards=2` (the 3.4 rescue at `trade_optimizer.py:662-702` appends `[G1, G2, X1] → [R]` with `card.sweetener`, and the gap pass on the organic `[G1, G2] → [R]` then collides at `:740-741` — the comment at `test_gap_sweetener.py:314-318` documents it), **extended with a second organic card after the bare in `cards`** — e.g. a second opponent asset `R2` whose own 1×1 sits in the frac window and is closable by an X2-sized piece — and the test asserts **that card is sweetened too**; and **v2 divergence** via a `max_per_opponent ≥ 2` fixture where `[G, X1] → [R]` is enumerated organically. **Assertions are key-level only:** frac 0.10 ⇒ no card with the bare key, exactly one with the balanced key, `len(cards)` exactly one less than at frac 0; frac 0 ⇒ both keys present and the bare first (C1 tie-break) | R-A2.7, R-A2.8 | **S-7a "keep both":** on collision, leave the bare card in (today's `continue`) — deck size unchanged, bare still first. **S-7b "mutate mid-loop" (v3):** `cards.remove(card)` inside `for card in cards` — the element after the bare shifts into its slot and is skipped, so the second closable card comes back **unsweetened**. (At plain `max_cards=2` with `[bare, sibling]` the skipped element is the sibling, which needs no processing — S-7b would *not* go red; the second card is what makes it red.) |
| **T-8** | `test_payload_mirrors_gap_sweetener_into_sweetener` — `trade_card_to_dict` on three `TradeCard`s: gap only ⇒ `out["sweetener"] == {"player_id": "X1", "side": "give"}` **and** `set(out["sweetener"]) == {"player_id", "side"}` and `out["gap_sweetener"]` is the full 4-key dict; both set ⇒ `out["sweetener"]` is the Tier-3 dict; neither ⇒ `"sweetener" not in out and "gap_sweetener" not in out` | R-C.9 | **S-8a "gap wins":** `if gap_sweetener: out["sweetener"] = …` unconditionally — overwrites a Tier-3 marker. **S-8b "whole dict":** `out["sweetener"] = gap_sweetener` — leaks `gap_before/gap_after` into a key clients validate as `{player_id, side}` (still renders, but the contract at `api-reference.md:299` is broken). |
| **T-9** | `test_default_and_seed_agree` — `ts._DEFAULT_CFG["sweetener_gap_frac"] == dict(db._MODEL_CONFIG_DEFAULTS)["sweetener_gap_frac"] == 0.10` | R-A.1, R-E | **S-9 "one home":** add the key to `_DEFAULT_CFG` only — prod (which reads `model_config` rows into `_cfg`) never sees it seeded, and the admin lever does not exist. |
| **T-10** | Regression — full `pytest backend/tests` green. **Unedited** (`git diff --stat` empty): `test_gap_sweetener.py` (its four legacy asserts `:235`, `:330`, `:368`, `:431` are kept green by tier 2, not by editing), `test_engine_quality.py` (C1 at `:247-266`, tie-break `:270-281`), `test_knockout_refine.py`, `test_shape_knob.py`, `test_bakeoff_challenger.py`. **Edited, by declaration only:** (1) `test_bakeoff_arm_a_golden.py` — the single token `sweetener_gap_frac` added to `_PINNED_KNOBS` (`:527`) so `test_no_generation_knob_was_added_without_an_arm_a_decision` (`:724-727`) passes; the golden capture is untouched. (2) **The one declared re-spec:** `test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op` — its `assert deck(10 ** 9) == off` leg (`:239`) pins *"a huge absolute threshold ≡ off"*, an invariant this item **retires** (`≤ 0` is the master switch; at frac 0.10 `eff = min(1e9, 0.10 × max)` fires, which is the feature working). The builder pins `ts._cfg["sweetener_gap_frac"] = 0.0` for that leg only, with a dated `# D-173 (unshipped parallel build; see D-175) (2026-09-02)` comment giving this reason; the `deck(0.0)` and `deck(-1.0)` legs (`:235`, `:238`) and the literal pre-sweetener asserts are unchanged. Named in TEST_LEDGER. **Run the suite at the new default BEFORE writing the new tests.** Known-safe: `test_shape_knob.py` pins `sweetener_gap_threshold = 0` (`:137-138`); the arm-C fixture gap is 1600 > 1539 (absolute trigger). **Residual risk:** `test_bakeoff_challenger.py` (`MODEL_CHALLENGER_PROFILE` does not pin the sweetener — `bakeoff_profiles.py` names it only in `MODEL_A_PROFILE:105`) and `_v2_cards(max_per_opponent=3)` in `test_gap_sweetener.py` may contain 1×1s in the 10–22 % window. A red there is a **spec signal to report**, not a test to edit. | R-A.6, R-D, "the 9.52 % fixture is untouched" | **S-10 "fix the golden":** a builder who edits `test_engine_quality.py`, the arm-A golden capture, or any leg of the arm-C kill test other than the declared `10 ** 9` one to make them pass has changed behaviour the default was chosen not to change. |

Every requirement above maps to ≥ 1 test: R-A → T-1…T-4b, T-11 (tier 2), T-12 (tier-1
precedence); R-A2 → T-7 (v3, v2), T-4a arm-C outcome assertion; R-C → T-8; R-D → T-5 and the
`_PINNED_KNOBS` guard in T-10; R-E → T-9; G-1/G-2 → T-6, T-4a-ov, T-11 (never widens vs D-143);
G-3 → T-4a-ov (consensus epsilon) and the untouched suites; G-4…G-7 are re-proven by the
untouched existing suites (T-10) plus T-4a's `gap_after ≤ eff` and T-8's shape assertions.

**Expected test delta (mini-round recount):** one new file, **21 test functions** — T-1, T-2, T-3
(one function, parametrised over 6 cases ⇒ 6 node ids), T-4a × 4, T-4b × 4, T-4a-ov, T-5, T-6,
T-7 × 2 (v3, v2), T-8, T-9, **T-11, T-12** — i.e. **26 pytest node ids**; plus one token in
`test_bakeoff_arm_a_golden.py` and the one declared re-spec in `test_gap_sweetener_arm_c.py`
(T-10; baseline 4483 passed / 1 skipped per TEST_LEDGER 2026-08-31). Sabotages: **14 named**
(S-1, S-2, S-3, S-4a, S-4b, S-ov, S-5′, S-6, S-7a, S-7b, S-8a/S-8b, S-9, S-10, S-11, S-12 — S-8
counts as one), each proven RED before its assertion is accepted.

### 6.2 deck_eval golden note (record in TEST_LEDGER)

Run `scripts/deck_eval.py` on the prod-boards replay (the same league set used for the D-143
prod-replay addendum) twice — `sweetener_gap_frac = 0` and `= 0.10` — and record, per arm:
over-line share (gap > 1539), **sweetened share**, 1×1 / 2×1 / 3×1 shape mix, mean deck size,
`gen_ms` p90. The TEST_LEDGER entry names both runs, the league ids, and the deltas.

**One pre-registered tripwire (Planner ruling 4), no auto-block:** if the prod replay's **3×1
share rises by more than +5 pp absolute** at frac 0.10 vs 0, the builder **reports before merge**
and the operator decides; nothing else is a gate. A shape gate inside the helper is deliberately
not built — it would contradict a shipped pin (`test_gap_sweetener.py:326-337` asserts a 3×1
produced under `v3_shape_max_delta` 1). `test_shape_knob.py` cannot detect this drift (it pins
the pass off at `:137-138`), which is why the replay carries the tripwire.

### 6.3 Code-walk proof targets (`code-walk.md`, owed by the builder)

| Target | What the trace must show, file:line-cited |
|---|---|
| (a) | All four callers read `sweetener_gap_frac` through `_c` and reach `close_value_gap` with `gap_frac=`, and the two pre-checks (`trade_service.py:7204`, `trade_gen_v2.py:739`) compute the **same `eff`** the helper computes (both via `_consensus_packages` / the identical `package_value_v2` call). |
| (b) | Arm A guard order: on every arm, no frac-dependent branch is reachable while `_GAP_THR ≤ 0` (`trade_optimizer.py:711`, `trade_service.py:6926`, `:7204`, `trade_gen_v2.py:737`); `MODEL_A_PROFILE` unchanged. |
| (c) | The collision branch per arm (v3 `:741` + post-loop filter; v2 `:6940` `else: continue`; consensus `:7228` `else: return`), and why gen_v2 needs none (`_dedup_batch :857-880`). |
| (d) | `_dedup_and_sort` (`trade_service.py:4902-4926`) runs after sweetening for v2 and v3 cards, filtering `_past_decision_keys` on the sweetened key; gen_v2's re-test at `trade_gen_v2.py:594-595`. |
| (e) | R-C serialisation precedence in `trade_card_to_dict` (`:11812-11820` + the new block), and the client path that consumes it unchanged (`trades.ts:86-95`, `TradeCard.tsx:235-240`, `:734`/`:766`). |

### 6.4 Operator TestFlight checklist (real league, balancing pref OFF — the prod default, `tradePregen.ts:26-47`)

Runtime proof matters here because the change is server-side but the *visible* result is a card
the operator judged wrong. No mobile build is required — the current TestFlight build against
the deployed backend is the test surface.

| # | Where | Steps | Expected |
|---|---|---|---|
| 1 | Trades landing, empty canvas | Tap **Find a Trade** | The pushed model deck renders (D-171). |
| 2 | Deck | Find a 1-for-1 whose value bar shows **you ahead by roughly 8–15 %** (or build London-for-Lamb in the calculator, note the bar, then find the deck card for that pair) | The served card's **give** side carries a **second asset of yours**, the line **"+ {player} added to balance the deal"** shows under the give column, and the bar reads near even. No card in the deck shows you ahead by more than ~10 % of its larger side without such a line — unless your roster has nothing between ~25 % of the headliner and even. |
| 3 | Same card | Check the added asset against your **Untouchables** list; then ✕ (pick a reason), ✓, and **edit in calculator** on a balanced card | The added asset is **not** untouchable. All three actions work on the sweetened card exactly as on any other (the id is the card's own). |
| 4 | Admin API | `PUT /api/admin/config/sweetener_gap_frac` with header `X-Cron-Secret: $CRON_SECRET` (from `secrets.local.env`; `_require_cron_auth`, `server.py:20943`) and body `{"value": 0, "source": "testflight-414"}` — the route (`server.py:18577-18601`) calls `set_config` **and reloads `trade_service._cfg` inline** (`:18600`), so the change is live on the running dyno immediately; it also appends a `model_config_changes` row (M1 knob log). Then force-regenerate the deck. **Do not** write the `model_config` row directly — `_cfg` is loaded only at process start (`:449`) and by this route, so a raw `UPDATE` changes nothing until a restart and would report a false negative on the lever. | The **same pair** comes back **bare** with its full gap and no "added to balance" line. `PUT` again with `{"value": 0.10, "source": "testflight-414"}`, regenerate → balanced again. (Deploy-free lever proven both directions; two `model_config_changes` rows attributed to `testflight-414`.) |
| 5 | DB read-only | `SELECT features_json->'gap_sweetener' FROM deck_impressions WHERE trade_id = '<card id from step 2>'`, then join `match_swiped`/`trade_pass_layer1` on `impression_id` | The impression row carries `{player_id, side, gap_before, gap_after}` with `gap_after ≤ 0.10 × max(side)`; the swipe row joins to it. If the swipe row has `impression_id: 'none'`, that is the Appendix A gap, not this change. |

Outcome logged in `living-memory/TEST_LEDGER.md`.

---

## 7. Docs and living-memory owed at ship

| Doc | Change |
|---|---|
| `docs/config-reference.md` | New `sweetener_gap_frac` row **after** `:996`: default 0.10; `eff = min(threshold, frac × max(give, receive))`; trigger and close both use `eff`; `≤ 0` = absolute trigger only; inert while `sweetener_gap_threshold ≤ 0`; not part of the D-143 pair rule (a third, tightening-only lever); live-changed via `PUT /api/admin/config/sweetener_gap_frac` (reloads inline); DB-seeded. **Tuning gotcha, verbatim in the row:** *"values below 0.0952 turn `test_engine_quality.py::test_adding_a_pick_to_a_fair_package_does_not_raise_composite` red (the C1 fixture's bare card sits at a 9.52 % gap and its pick becomes an eligible equalizer under `_ORTHOGONAL_GATES_OPEN`) — retune that fixture first."* **Fix** the stale sentence in the `sweetener_gap_threshold` row at `:996` — "Arm C (`trade_gen_v2`) and the fit arm do NOT run the pass in v1" → arm C runs it (`trade_gen_v2.py:740`, `docs/plans/package-benchmark-sweetener/scope.md:59`); the fit arm still does not. |
| `docs/api-reference.md` | `:299` `sweetener` comment: "OPTIONAL — Tier 3 (trade_engine.v3) rescue **or, since #414, the gap auto-sweetener**: `{player_id, side}` of the asset added to balance". Add a `gap_sweetener` line after `:300`: `{ "player_id", "side", "gap_before": float, "gap_after": float }` — OPTIONAL, present only on gap-sweetened cards (served since 2026-08-22, undocumented until now). No route change. |
| `living-memory/DECISIONS.md` | **D-173 (unshipped parallel build; see D-175)** (§9) inserted **directly above `## D-171` at `:1046`** — the entry block is newest-first (D-171 `:1046`, D-170 `:1065`, D-169 `:1079` … D-153 `:1471`), not id-ascending — plus a row in the Decision index **after `:522`** (the D-171 row). |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **New exclusion row** for `sweetener_gap_frac` in the knob-disposition table, directly after the `sweetener_gap_threshold` row (`:123`), on the `package_floor_cross` "inert companion" precedent (`:122`): inert while `sweetener_gap_threshold ≤ 0`, which `MODEL_A_PROFILE` pins; every caller reads it only behind the `> 0` guard; pinning it would imply it matters to arm A. Required by `test_bakeoff_arm_a_golden.py:724-727`. |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md`, this folder's `status.md` | At ship, per CLAUDE.md. TEST_LEDGER additionally names the one declared re-spec (`test_gap_sweetener_arm_c.py:239`, reason: "huge threshold ≡ off" retired) and the `_PINNED_KNOBS` token. |
| `docs/cross-client-invariants.md`, `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md`, `docs/glossary.md`, `docs/data-dictionary.md` | **n/a** — reasons in scope.md §4. |

---

## 8. Out of scope

| Item | Why not here |
|---|---|
| **H1 — fair fork / D-153 amendment** | Not the surface: `calc_find_a_trade_tapped {path: "model"}` + an 8-hex engine id, not `fairpk_` (`server.py:12398`). D-153's anchor exactness stands; `test_fair_packages.py:197` untouched. |
| **H2 — fair-fork band 0.50 → 0.75; H5 — age-pref parity on the fair fork** | Cheap but separable and unrelated to the reported surface. NEXT.md candidates. |
| **H3 — tier same-value path; H6 — bakeoff interleave fallback (`bakeoff_runner.py:247`)** | Independent hygiene. |
| **Likes-you injector** | No like / standing-offer row for the pair; D-096/D-170 untouched. |
| **Balancing-pref default (OFF ⇒ 0.50 requested, `tradePregen.ts:26`, `:45-47`)** | Product decision, separate item. |
| **Shape guard on the frac trigger (`len(richer side) == 1`)** | Only if the deck_eval readout shows 3-for-1 share jumping (§5). |
| **R-B — streaming-snapshot telemetry** | Real, confirmed in code, touches `TradesScreen.tsx` (outside G-414). Carried verbatim as **Appendix A** for its own feedback-pipeline item. |

---

## 9. The D-173 (unshipped parallel build; see D-175) entry, draft

Next id verified 2026-09-02: `## D-171` is the max in `living-memory/DECISIONS.md` (`:1046`; index
`:522`). **Placement:** the entry block is newest-first, so D-173 (unshipped parallel build; see D-175) goes **directly above `## D-171`
at `:1046`**; its index row goes after `:522`. Title and body below are the planner's draft with
the id filled in and a **Consequences** line added per the round-1 rulings; the builder pastes it
verbatim.

> ## D-173 (unshipped parallel build; see D-175) — The Gap Sweetener Gains a Proportional Trigger; Above It the Balanced Sibling Beats the Bare Card (amends D-143)
>
> **Date:** 2026-09-02 · **Origin:** #414 (operator, London-for-Lamb served bare at a 12.7 % consensus gap) · **Status:** decided pending build
>
> D-143's trigger is absolute (one late 1st), so a 1-for-1 on a ~6k asset could favour the viewer by 12.7 % and pass every gate — R1 kills at 25 %, the ratio band at 0.5/0.75, the sweetener at 1539. `model_config` `sweetener_gap_frac` (0.10) tightens the pass on every served arm to `min(1539, 0.10 × the card's larger side)`; the sweetener is drawn as before from the richer side's roster (the viewer's, when the viewer gains), re-earning each arm's gates, untouchables and not-interested; when the balanced sibling already exists the bare card yields to it (the C1 tie-break ran the other way). Gap-sweetened cards now also carry the `sweetener` marker so the shipped "+ X added to balance the deal" line renders. `sweetener_gap_threshold ≤ 0` remains the master switch and D-143's pair-rollback rule stands; `sweetener_gap_frac ≤ 0` restores 2026-08-31 behaviour byte-identically. Not changed: D-153 (the fair fork was not the surface), R1's 0.25, the balancing-pref default.
>
> **Consequences:** (1) on v3 a collision drops the bare card and the pair serves one card fewer — **no backfill**; a per-pair count is a generation budget, not a deck cap (D-154), and the deck is globally ranked in `_dedup_and_sort` afterwards. (2) The consensus site is order-dependent by design: bare-first sweetens in place and the later organic sibling dies as a duplicate; sibling-first (reachable only when two bares close to the same combo) returns without the bare. The invariant is outcome-level — at most one card per balanced key, no bare surviving beside its balanced key — and the survivor's annotation differs by path. (3) Arm C has no collision rule; `_dedup_batch` collapses the pair. (4) **Tuning floor:** the C1 fixture (`test_engine_quality.py:247-266`) sits at a 9.52 % gap, so `sweetener_gap_frac` below 0.0952 fires on it and turns that test red — retune the fixture before lowering the knob. (5) Shape drift (more 3×1s) is watched via the prod replay with a pre-registered +5 pp tripwire, not gated in the helper. (6) **The accept is two-tier:** the first equalizer that reaches the proportional target wins; failing that, the first that reaches D-143's absolute line is used — so the pass never widens a served gap relative to D-143, and a tier-2 card is marked "added to balance" even though its bar may still lean. (7) **Retired invariant:** "a huge `sweetener_gap_threshold` ≡ off" no longer holds — `≤ 0` is the only master switch; the arm-C kill test's `10 ** 9` leg is re-specced to pin the frac at 0. (8) `sweetener_gap_frac` is listed in the arm-A golden's `_PINNED_KNOBS` as an **excluded, inert companion** of the threshold pin (scope-phase2 row), not added to `MODEL_A_PROFILE`.

---

## Appendix A — follow-up item: streamed-then-trimmed cards carry no impression

Carried verbatim from plan-g414.md §12 (R-B). **Not built in G-414.** Proposed as its own
feedback-pipeline item; it touches `mobile/src/screens/TradesScreen.tsx`.

> **R-B telemetry follow-up (real, one paragraph):** streaming snapshots publish each arm's cards as partners finish (`_make_progress_cb`, `server.py:3004-3030`, wired at `:6047/:6183`) *before* the final mutation stack removes cards — F7 `_split_exploration_pool` (`:5226`, ~`:6252`), F3 `_apply_deck_suppression` (`:4993`, ~`:6339`; a 30-day decline-window near-duplicate of the 08-17 pass would match here), F9 `_apply_first_session_shaping` (`:5656`, ~`:6541`), ghost split (~`:6661`) — and impressions are logged once on `served_final` at `:6728`. The client's deck merge is append-only by `trade_id` and never refreshes a held card object (`mobile/src/screens/TradesScreen.tsx:2137-2143`), so a streamed-then-trimmed card stays swipeable with `impression_id: 'none'` (`:5292`, `:5586`) — exactly the observed row — and even kept cards only carry `impression_id` if first seen in a completed snapshot. Smallest fix is client-side: on `status === 'complete'`, copy `impression_id` by `trade_id` into held cards and drop held cards beyond the fronted one that are absent from the final snapshot. Server-side alternative (apply F3/F7 per streamed snapshot) is heavier and still leaves the F9/ghost passes. Size it first: share of `match_swiped {source: deck}` with `impression_id: 'none'`. Proposed as its own feedback-pipeline item; it touches `TradesScreen.tsx`, outside G-414.

## 14. Build-time addendum 2 (2026-09-02, orchestrator ruling — full-suite reds at the new default)

The build's first full-suite run at `sweetener_gap_frac = 0.10` produced six reds outside §6.1's seven named files. Rulings, binding on the build and on QA:

- **G-8 (new guardrail, REAL defect fixed):** the gap pass re-earns #360 **avoid positions** for every RECEIVE-side equalizer on every arm — `_gap_extra_ok` on v3 (`trade_optimizer.py` ~:723-732) and v2 (`trade_service.py` ~:6917-6927) gained `avoid_ok(...)`, matching the 3.4 rescue (`:678`, `:824`); consensus/gen_v2 either filter at pool construction (cited in `code-walk.md` (f)) or gained the same check. Give-side equalizers are the viewer's own players, so avoid does not apply. Proof: `backend/tests/test_avoid_positions.py:391` goes green by the code fix alone (untouched), and RED when the check is removed. The proportional trigger merely made this pre-existing gap reachable at the default.
- **Declared re-specs (five, by name — TEST_LEDGER carries them):** `test_engine_quality_golden.py` `_KILL_ALL` gains `sweetener_gap_frac: 0.0` (registry-style, as `_PINNED_KNOBS`); `test_filler_threshold.py:235`, `test_trade_gen_v2.py:1062` + `:1098`, `test_trade_optimizer.py:348` pin `sweetener_gap_frac = 0` in their config overlays (they test filler mechanics / g6 pick-band shapes / feasibility, and their organic cards sit in the 10–22 % window). Fixtures are not rescaled.
- **Expected full suite:** 4483 baseline + 26 (`test_gap_sweetener_frac.py`, incl. the two tier tests) = **4509 passed / 1 skipped** (actuals recorded by the build; any drift is reported, not absorbed).

## 15. QA round 1 resolution (2026-09-02, test coverage only — no production code changed)

Both QA agents passed the code (`qa-round-1-agent-A.md`, `qa-round-1-agent-B.md`). Their findings were
coverage gaps: behaviours the contract states that no test pinned, plus one precision defect in two test
helpers. This round closes them in `backend/tests/test_gap_sweetener_frac.py` alone — every new test names
its sabotage, and each sabotage was applied, turned the named test RED on the recorded assertion, and was
reverted with `git checkout --` before the next.

| Finding | Test (all in `test_gap_sweetener_frac.py`) | Fixture | Sabotage → RED assertion |
|---|---|---|---|
| A F-2 / B F-3 — v3 G-8 avoid re-earn unpinned | `test_v3_gap_pass_never_uses_an_avoided_position_as_equalizer` | London/Lamb **mirrored** on a boarded pair (user gives G 6862 for R 5989.5, opponent richer by 872.5); the only sufficient opponent-side piece is E = 2100, an **RB**; leans G (−60/+30), R (+60/−60) cap both surpluses so the C1 rank tie hands the pick to the bare 1×1 by enumeration order. Control (no avoid): the gap pass adds E on the receive side, `{E, receive, 872.5, 428.3}`. With `avoid_positions=["RB"]`: served bare at the full 872.5, no card carries E | delete the two `avoid_ok` lines in v3 `_gap_extra_ok` (`trade_optimizer.py:736-737`) → `AssertionError: assert ({'gap_after': 428.3, 'gap_before': 872.5, 'player_id': 'E', 'side': 'receive'} is None or 'E' != 'E')` |
| A F-5 / B O-7 — tier 2 returns the *first* fallback | `test_helper_tier2_returns_the_first_admissible_fallback` | London with a second tier-2 piece Y = 650 (residuals: X2 762.3, Y 728.7 — both in (686.2, 1539]); `give_candidates=["X2","Y"]` and the reversed order | `if fallback is None: fallback = hit` → `fallback = hit` (last wins) → `tier 2 did not return the first fallback: Y` / `assert 'Y' == 'X2'` |
| A F-6 — helper precision (`eff` from post-close values) | `_assert_sweetened_to_eff(card, equalizer, eff=EFF)` now takes the fixture **literal** (686.2; arm C passes `_ARM_C_EFF` = 1120); `_eff_of` asserts it is only ever called on a **bare** card, whose sides are the original ones by construction | — | no sabotage (precision fix); T-4a × 4 re-run green after the change |
| A F-4 / B F-2 — consensus `else: return` collision branch untested | `test_consensus_two_bares_closing_to_the_same_combo_keep_one_card` | Consensus pair A = 3900, B = 3800 vs R = 6862 at `fairness_threshold=0.5`; both 1×1s are over the absolute line and each closes with the other onto `{A,B}→{R}` (6540.8 vs 6862, residual 321). At frac 0.10 exactly one card (the balanced key) and no bare; at frac 0 the second bare `[B]→[R]` falls through beside it (D-143 behaviour, R-A2.8 on consensus) | `else: if _GAP_FRAC > 0: return` → `pass` (`trade_service.py:7274-7275`) → `a bare card survived beside its balanced sibling: [({A,B},{R}), ({B},{R})]` |
| A F-3 — R-A2.8 byte-identity on the v3 collision path at frac ≤ 0 | `test_v3_collision_at_frac_zero_keeps_both_cards` | T-7's deck with G lowered to 5250 (`_V_T7_ABS`): bare gap 1612 > 1539, so the absolute pass fires at frac 0 and its cheapest-first close lands on C2's key `[G,Y]` (helper-proven on the same value space) — already picked. Frac 0: `[bare, C2, sibling]` all unsweetened (both survive); frac 0.10: bare gone, sibling once, deck one shorter | v3 collision `if GAP_FRAC > 0:` → `if True:` (`trade_optimizer.py:757`) → `bare card dropped at frac 0 — not byte-identical to D-143: [({G,Y},{R}), ({G,X1},{R})]` |

Node-id count in `test_gap_sweetener_frac.py`: 25 → **29** (24 functions). Findings not closed here, on purpose: A F-1 / B F-5 (docs drift — PRD/LLD/log copies vs the rulings) belong to the docs owner, not this file; A F-7 (X1 = 1750 on the boarded arms) is already explained inline at the fixture; B F-1 (per-candidate `eff` recompute) and B F-4 (frac read inside the guard) were judged contract-only by both agents and are left as is.
