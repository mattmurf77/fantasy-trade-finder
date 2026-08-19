# PRD — Landability challenger (bake-off arm D)

**Date:** 2026-08-19
**Status:** active, not built — operator directed: *treat the overhaul as a new challenger first*
**Parent:** [three-model bake-off](../three-model-bakeoff/PLAN.md)
**Owner (product):** operator. **Owner (delivery):** EM, tasking the tickets in [README.md](README.md)
**Scope:** [scope.md](scope.md)

This is the document an EM hands to engineering. The review thread is closed. If a line here disagrees with a Slack message, this file wins until the operator amends it.

---

## 1. One-page brief (read this first)

Today the live finder is:

> a market-even engine that only shows the side where the viewer wins, then ranks that side by the biggest name.

That is a product choice, not a bug. KTC and Dynasty Daddy print both sides of an even trade. We print the steal. 96% of 1-for-1s exist in only one direction. 84.5% of cards never see a partner board at all.

**We are not changing that for users yet.** The operator wants the alternative built as a **bake-off challenger**, generated and logged in the dark, served only when interleaved serving is later lit. Live `current` (arm B) stays what users see.

The challenger asks a different question of the same engine:

> show trades two sides could both take — even on consensus, dual-surplus on boarded pairs — and stop ranking the most lopsided star deal first.

Call the new arm **`challenger`** (arm D). Do **not** reuse or edit historical arm A (`baseline`, `MODEL_A_PROFILE`, golden at SHA `92c31d5`). D-075 is load-bearing: arm A is a pinned constant. Replacing it makes the bake-off unfalsifiable.

Two tracks run in parallel:

| Track | What | Serves to users? |
|---|---|---|
| **A — Challenger** | generation + ranking overhaul, overlay on the live engine | No. Dark. `bakeoff_serve_interleaved` stays `0` |
| **B — Hygiene** | likes-you you-pay pin; “balanced” copy on unfair cards | Yes, if the EM promotes them. They are bugs under *both* products |

Track B is optional in this PRD’s first sprint. Track A is the ask.

---

## 2. Problem

Measured on the live engine (`trade_engine.v2` + `trade_engine.v3` ON, `trade_gen.v2` OFF):

| Fact | Number | Why it matters |
|---|---:|---|
| Cards with no partner board (consensus path) | 84.5% | Dual-surplus never runs for most of the deck |
| 1-for-1s that exist in only one direction | 96.3% | Viewer-wins identity, not a dual finder |
| Consensus cards with user receiving more than they give | 86.3% | Hard `rv ≥ gv` at [`trade_service.py` ~5028](../../../backend/trade_service.py) |
| Boarded-pair cards with the same one-sidedness | 86.9% | User Elo is shrunk toward seed; partner board is raw |
| Elite-band surplus vs fairness span | 4.57× vs 2.00× | `_tier_mult_v2` outranks the fairness term, so the biggest name wins |
| Likes-you cards with viewer delta < 0 | 44 of 45 | Injector floor is `likes_you_min_user_delta = -500`; `boost_score = max(composite)+1` pins them at deck slots 1–3 |
| One likes-you card’s user delta | −6,019 | Not buried. First thing some users saw |
| Cards offering a pick that did not exist in the league | 12.8% | Fixed 2026-08-19 (D-091). Pre-fix like-rates are contaminated; compositional findings still hold |

Copy currently labels some of those cards “balanced.” The engine’s own fairness number disagrees.

KTC’s public calculator is dual-sided by construction (one market, even band, both directions). Dynasty Daddy’s finder is roster-aware and even-first. FTF’s live path is viewer-first on a market-even substrate. The challenger is how we find out whether moving toward KTC/DD on the 84.5% (and toward honest dual-surplus on the 15.5%) is a better product, without betting the live deck on it.

---

## 3. Goals and non-goals

### Goals

- **G1.** A fourth bake-off arm, `challenger`, runs the live v1/v3 engine under a named profile (`MODEL_CHALLENGER_PROFILE`) on every organic bake-off job.
- **G2.** That arm produces both `consensus` and `divergence` groups (it is an engine arm, not a `gen_v2` clone).
- **G3.** On consensus: both directions of an even trade can emit, at a **0.75 fairness floor**, including 1-for-2 as the sibling of 2-for-1.
- **G4.** On boarded pairs: surplus is computed on the user’s **raw** board vs the partner’s raw board. Shrink-neither. (Shrink-both is a schema change and is out of this PRD.)
- **G5.** Ranking no longer lets elite-band `_tier_mult` dominate fairness (compress the ladder so fairness can compete).
- **G6.** R5 (user-need kill) is off on the challenger. Partner need is not newly gated.
- **G7.** Dark serving is unchanged: users still see arm `current`. Interleaved serving stays off until the operator lights it.
- **G8.** Historical arm A is byte-identical. The knob-inventory golden still passes without editing `MODEL_A_PROFILE`.

### Non-goals (rejection rules in review)

- **N1.** Do not edit `MODEL_A_PROFILE`, `model_a()`, or `test_bakeoff_arm_a_golden.py`’s captured deck. New knobs are **excluded** from the profile with a written reason in [scope-phase2.md](../three-model-bakeoff/scope-phase2.md).
- **N2.** Do not change live `_DEFAULT_CFG` generation behavior. New knobs default to the live identity. The challenger is an overlay.
- **N3.** Do not set `bakeoff_serve_interleaved = 1` in this work.
- **N4.** Do not dualize user-only *ranking overlays* (`aggression`, outlook-direction rank, `fit_premium`, `need_fit` rank, `block_boost`). Those stay user-only. The bake-off is about gates and the two knobs that decide *which cards exist*, plus the one ranker that currently crushes fairness (`_tier_mult`).
- **N5.** Do not delete `filler_ok`. It does not apply to 1-for-1s.
- **N6.** Do not treat the 0.75-after-five-votes overlap escape as a general user-facing rule. It is divergence-only (15.5%).
- **N7.** Do not ship `trade_gen_v2.py` changes. Arm C is out of scope. A knob may *drop* arm C from the roster so the head-to-head is `current` vs `challenger`; that is composition, not a gen-v2 change.
- **N8.** Do not add comparison_counts to `member_rankings`. Shrink-both is a later PRD.
- **N9.** Do not retune live like-rate models on 2026-08-16…08-19 data. 12.8% of that window’s cards were phantom picks (D-091).

---

## 4. What the challenger changes (and what it does not)

Same engine, thread-local overlay. Invocation:

```text
with model_challenger():          # _cfg_override(MODEL_CHALLENGER_PROFILE)
    cards = generate_trades(...)  # live v1/v3 path
```

No R4 bypass. G6 presentment stays on except R5, which the profile disables by knob.

| Lever | Live (`current`) | Challenger | Why |
|---|---|---|---|
| `user_elo_shrink` | 1.0 (blend toward seed) | **0.0** (raw board) | P2. Shrink is user-only; it is the boarded-pair one-sidedness. `shrink_pseudocount = 0` is not a substitute (`n/(n+0)` is NaN at `n=0`) |
| `need_gate_min_value` | 200 | **0** (R5 off) | P2. Rank-not-kill approximated as disable. A partner-need ranker is not in this profile |
| `tier_mult_elite` … `_bench` | 1.60 / 1.25 / 1.00 / 0.55 / 0.35 | **1.15 / 1.08 / 1.00 / 0.90 / 0.80** | P1. Live span 4.57× vs fairness span 2.00×. Challenger span 1.44× vs fairness-at-0.75 span 1.33×. Elite only beats a perfectly-even solid at fairness > 0.870 |
| `consensus_both_ways` | 0 | **1** | P3. Drop the `rv ≥ gv` one-way sign. Enumerate 1-for-2 as well as 1-for-1 / 2-for-1 |
| `consensus_fairness_floor` | 0 (client toggle, often 0.50) | **0.75** | P3. Opening both directions on the live 0.50 floor is a 2:1 user-pays flood. Floor is `max(requested, 0.75)` on the consensus path only |
| Dual-surplus + harmonic mean | unchanged | unchanged | Already the mutually-acceptable core on boarded pairs. Do not restub it |
| `user_gain_ok_1for1` | live | live | Stays. It is a 1-for-1 raw-board overlay; with shrink off it agrees with surplus |
| Likes-you injector | live −500 floor, no R1, pin to slot 1–3 | **not in the arm** | Serving layer, `model_arm = NULL`. Track B if the EM wants it live |
| Narrative “balanced” | live | **not in the arm** | Client copy. Track B |

---

## 5. Tickets (this is what the EM assigns)

Each ticket is independently mergeable. A1 is the only hard prerequisite. Estimate is calendar days for one backend engineer who already knows this repo.

### Track A — challenger (backend, dark)

#### A1 — Arm plumbing
**Who:** backend. **Est:** 1d. **Depends:** none.

- Add `ARM_CHALLENGER = "challenger"` in [`backend/bakeoff_runner.py`](../../../backend/bakeoff_runner.py).
- Keep `ARMS` as the historical three `(baseline, current, gen_v2)` so Phase 3 tests that pin `bo.ARMS` stay byte-identical.
- Add `challenger` to `ENGINE_ARMS` and `GENERATION_ORDER` (after `current`, before `baseline`).
- `arm_roster()`: `current` always; `challenger` if `bakeoff_include_challenger ≥ 1` (default **1**); `gen_v2` if `bakeoff_include_gen_v2 ≥ 1` (default **1**); `baseline` still behind `bakeoff_include_baseline` (default 0).
- `run_bakeoff`: `elif arm == ARM_CHALLENGER: with model_challenger(): generate(...)`.
- Snapshot config **inside** the overlay, same as arm A.
- Phase 3 kill-value tests must pin `bakeoff_include_challenger = 0` so they keep restoring the original three-arm draft.

**Done when:** default roster is `(current, challenger, gen_v2)`; flipping the knob to 0 restores `(current, gen_v2)`; dark serving still serves `current`; `groups_for` yields `challenger_divergence` and `challenger_consensus`.

#### A2 — Generation knobs
**Who:** backend. **Est:** 1d. **Depends:** A1 (profile must exist; knobs can land first if sequenced carefully).

New keys in `trade_service._DEFAULT_CFG`, all defaulting to the **live identity**:

| Key | Default | Challenger | Site |
|---|---:|---:|---|
| `user_elo_shrink` | 1.0 | 0.0 | `_shrink_user_elo` — early return of `dict(user_elo)` |
| `consensus_both_ways` | 0.0 | 1.0 | `_generate_consensus_for_pair._emit` skips `rv ≥ gv` when ≥ 1; 1-for-2 loop after 2-for-1 |
| `consensus_fairness_floor` | 0.0 | 0.75 | same `_emit`: `_thr = max(requested, floor)` when floor > 0 |

Do **not** put these in `MODEL_A_PROFILE`. Their defaults *are* the pre-challenger engine. Pinning the kill value would make arm A skip shrink / emit both directions, which the pre-wave engine never did. Record the exclusion in [scope-phase2.md](../three-model-bakeoff/scope-phase2.md) and add the keys to `_PINNED_KNOBS` in `test_bakeoff_arm_a_golden.py`.

**Done when:** with the overlay off, `test_user_gain_gate.py` still passes (Maye-for-Dart stays dark). With the overlay on, a consensus 1-for-1 inside 0.75 emits the user-pays direction, and a 0.40-fairness 2:1 is still dead even if the client sent 0.50.

#### A3 — Ranking knobs (profile-only, no new keys)
**Who:** backend. **Est:** 0.5d. **Depends:** A1.

`MODEL_CHALLENGER_PROFILE` sets:

```
need_gate_min_value     0.0
tier_mult_elite         1.15
tier_mult_starter       1.08
tier_mult_solid         1.00
tier_mult_depth         0.90
tier_mult_bench         0.80
```

No new `_DEFAULT_CFG` keys. Live values stay 200 / 1.60 / 1.25 / 1.00 / 0.55 / 0.35.

**Done when:** a fixture where an elite-band card at fairness 0.70 used to outrank a solid card at fairness 1.00 now ranks the even solid first under the overlay, and ranks the elite first under live defaults.

#### A4 — Tests, inventory, dark validation
**Who:** backend. **Est:** 1d. **Depends:** A1–A3.

Minimum tests (file `backend/tests/test_bakeoff_challenger.py` plus the two existing goldens):

1. Profile does not collide with `MODEL_A_PROFILE` except the coincidental `need_gate_min_value = 0`.
2. `model_challenger()` does **not** set `r4_bypassed()`.
3. `model_a()` still sees `user_elo_shrink = 1` and `consensus_both_ways = 0`.
4. Fan-out enters the overlay only on the challenger call.
5. `_shrink_user_elo` at `n=0` returns seed live, raw Elo under the overlay.
6. Consensus both-ways + floor, as in A2.
7. Knob inventory: no unpinned `_DEFAULT_CFG` keys.
8. Default roster / kill-value restore, as in A1.

Dark-mode proof: with `trade.bakeoff` ON and `bakeoff_serve_interleaved = 0`, a bake-off job writes `challenger` into `bakeoff_runs.arms_json` and `groups_json`, and `served_arm` is still `current`. No user-visible deck change.

**Done when:** `pytest backend/tests/test_bakeoff_challenger.py backend/tests/test_bakeoff_arm_a_golden.py backend/tests/test_bakeoff_composition.py backend/tests/test_bakeoff_runner.py backend/tests/test_user_gain_gate.py` green, plus a TEST_LEDGER line.

---

### Track B — live hygiene (optional, EM call)

These are bugs under *both* product choices. They are not the challenger. They *can* ship to live without a bake-off. Do not bury them in the arm: likes-you is applied **after** merge (`server._inject_likes_you_cards`), stamped `model_arm = NULL`, and `boost_score = max(composite)+1` pins the card at slots 1–3. A profile overlay never reaches it.

#### B1 — Likes-you: floor 0 + run R1
**Who:** backend. **Est:** 0.5d. **Depends:** none.

- Raise `likes_you_min_user_delta` from −500 to **0** (viewer must not lose on consensus).
- After the existing floor, run `overpay_ok` (G6 R1) on the mirrored package so a you-pay card cannot skip the overpay ceiling the generator itself uses.
- Leave the pin-to-top behavior for cards that *pass*. A partner-liked even trade sitting at slot 1 is the feature.

**Done when:** a mirrored like with `user_delta = −6019` is not injected; a mirrored like with `user_delta ≥ 0` that also passes R1 still lands at the top.

#### B2 — Copy: don’t say “balanced” unless it is
**Who:** mobile + web. **Est:** 0.5d. **Depends:** none.

- `trade_narrative` / client fairness copy: “balanced” (and synonyms) only when `fairness ≥ 0.75`.
- Below that: “leans your way” / “leans theirs” / “lopsided”, matching the engine’s own number.
- No new flag required if this is treated as a copy bug. If the EM wants a rollback, add `copy.honest_fairness` default ON.

**Done when:** a card at fairness 0.58 never renders the word “balanced” on mobile or web.

---

### Track C — measurement (do this even if A slips)

#### C1 — Offline 3-cell count (P3 gate)
**Who:** analytics / backend eval. **Est:** 0.5d. **Depends:** none. **Can run today, on a replay of the 7,094-card window, post D-091 pick-horizon.**

The operator’s product call is gated on one number nobody has: *how many cards survive at 0.75 with both directions open?*

Replay consensus `_emit` over a post-fix candidate pool (or the 7,094 with phantom-pick cards dropped) under four cells. Report **surviving card count** and **share with receive < give**.

| Floor | Direction | What it is |
|---|---|---|
| 0.50 | one-way | ships today (7,094 in the audited window) |
| 0.75 | one-way | tighter viewer-wins; identity unchanged |
| 0.75 | both-ways | **this is the challenger** |
| 0.85 | both-ways | fallback if 0.75 both-ways still looks like a fleece deck |

**Done when:** a one-page note in this folder (`measurement.md`) with the four counts. If both-ways at 0.75 collapses the deck, A2’s 1-for-2 + both-ways is still built (the bake-off is how we confirm), but the operator should not light interleaved serving.

#### C2 — After interleaved is lit (not this PRD)
Operator-only. Out of scope until C1 is yellow or green and A4 is merged. Success metrics:

- like-rate `challenger` vs `current`, **split by `basis`** (consensus vs divergence). Do not pool them — 84.5 / 15.5.
- one-sidedness rate (share of 1-for-1s with `receive ≥ give`) per arm, per basis.
- deck size / `groups_json.short` (leave-short is the finding, D-078).
- discard any ranking-quality inference that uses 2026-08-16…08-19 outcomes.

---

## 6. Sequencing

```text
C1  (offline count)          ─┐
A1  (plumbing)               ─┤ can start in parallel
B1 / B2 (hygiene, optional)  ─┘
        │
        ▼
A2 + A3 (knobs + profile)
        │
        ▼
A4  (tests + dark validation)
        │
        ▼
merge, still dark
        │
        ▼
operator reads C1 + a few dark bakeoff_runs rows
        │
        ▼
light bakeoff_serve_interleaved  (separate decision, not this PRD)
```

Do not block A on C1. Do not light interleaved without C1.

---

## 7. Product call this bake-off is for

After we have C1 counts and (if lit) C2 like-rates, the operator picks one:

| Call | What ships to live | What happens to the challenger |
|---|---|---|
| **Stay viewer-first** | maybe B1/B2; maybe compress `_tier_mult` on live if C2 says it helped | keep or drop the arm |
| **Switch to both-willing** | promote the challenger profile to live defaults; keep `current` as a rollback overlay | arm D becomes the new B |
| **Blend** | both-ways + 0.75 on consensus only; keep viewer-wins ranking; leave shrink as-is | partial promotion, new PRD |

P3 (both-ways at 0.75) is the only lever that changes the 84.5% identity. P2 shrink-neither is required *in addition* if the call is “both-willing finder,” because otherwise boarded pairs keep running shrunk-user vs raw-partner. Do not let “P3 is the product lever” bury P2 under the wrong reading.

P0 likes-you (B1) is required under **both** calls. A viewer-first product that leads with a −6k you-pay card is incoherent.

---

## 8. Risks

| Risk | Why | Mitigation |
|---|---|---|
| Challenger under-produces | both-ways at 0.75 may be a smaller pool than one-way at 0.50 | C1 before lighting interleaved; leave-short is data (D-078) |
| Challenger over-produces junk | 1-for-2 + both-ways at a loose floor | floor is 0.75, not 0.50; consolidation_raw_loss_frac still applies to 2-for-1 |
| Job cost | one extra full `generate_trades` per organic job | same class as adding arm A; `bakeoff_include_challenger = 0` is the kill; sequential on the existing thread |
| Arm A golden breaks | new knobs silently change baseline | N1: exclude from `MODEL_A_PROFILE`, pin in `_PINNED_KNOBS` with a written reason |
| Analysis contamination | D-091 phantom picks, likes-you `model_arm = NULL`, position confound if rerankers run | interleaved still bypasses rerankers (D-077); don’t use pre-fix outcomes; likes-you stays a constant shift if B1 hasn’t shipped |
| Naming collision | “new Arm A” in conversation vs historical `baseline` | code name is `challenger`. Docs may say “arm D.” Never `baseline` |

---

## 9. Acceptance (initiative)

The initiative is accepted when:

1. Organic bake-off jobs (flag on, interleaved off) generate `challenger` cards, attribute them, and still **serve `current`**.
2. `MODEL_A_PROFILE` and its golden are unchanged in behavior.
3. Live users not in a bake-off job are byte-identical to today.
4. C1’s four-cell table exists as `measurement.md`.
5. TEST_LEDGER records the pytest files in A4.

It is **not** accepted when a user can see a both-ways card. That is a later operator flip of `bakeoff_serve_interleaved`.

---

## 10. References

- Live path: `TradeService._generate_trades_impl` → `_generate_trades_v2` ([`backend/trade_service.py`](../../../backend/trade_service.py)).
- Consensus emit (the 84.5%): `_generate_consensus_for_pair`.
- Dual-surplus core (the 15.5%): harmonic mean ~4717; do not restub.
- Bake-off: [`docs/plans/three-model-bakeoff/PLAN.md`](../three-model-bakeoff/PLAN.md), D-075, D-077, D-078, D-086, D-087.
- Phantom picks: D-091. Do not analyse 2026-08-16…08-19 like-rates as ranking quality.
- Competitors: KTC even-band both-ways; Dynasty Daddy even-first roster-aware finder. FTF live is viewer-first on a market-even substrate.
