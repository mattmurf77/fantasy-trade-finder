# PRD — Fit challenger (dual 0–100 scores, thin knockouts)

**Date:** 2026-08-19
**Status:** active, not built
**Owner (product):** operator. **Owner (delivery):** EM, tickets in [README.md](README.md)
**Scope:** [scope.md](scope.md)
**Bake-off arm:** `fit` — dark, never the live serving path

This is the document an EM hands to engineering. Knockout decisions are §3. If Slack disagrees, this file wins until the operator amends it.

Sisters (do not merge in this arm):
- Live Arm B = `_generate_trades_v2` + v3 + consensus (`rv ≥ gv`)
- [landability-challenger](../landability-challenger/PRD.md) = same live engine, different knobs
- `trade_gen.v2` / arm C = different pipeline, flag stays off
- [card-evidence](../card-evidence/PRD.md) / [ppg-impact](../ppg-impact/PRD.md) = presentment around cards, not this generator

---

## 1. One-page brief

Build a **new generator** whose only hard knockouts are roster physics, package shape, pick-churn, dual startable lineups, and G6 (R1/R2/R3/R5). Everything that is “would they like this?” is a **score**, not a kill.

Each surviving idea gets **two numbers, 0–100** — one per team — from three lenses:

1. Board vs board (when both have rankings)
2. That team’s board vs consensus (when they have rankings)
3. Consensus fairness / surplus (always)

**Present by highest `score_you + score_them`.** Preferences (untouchables, not-interested, pins, intent) run **after** scoring. They hide cards; they do not shrink the search.

**Why this can produce more on the same data:** live consensus (~85% of cards) kills every market-loser for the viewer (`rv ≥ gv`). Dual surplus kills boarded pairs unless both boards clear +60. Divergence prune throws away assets that aren’t “they overrate / you overrate.” This arm scores those ideas instead of deleting them. More survivors is the bet; like-rate vs Arm B is the bake-off.

**Not live.** Flag `trade.bakeoff` already exists. This arm is invoked the same way as `gen_v2`: called directly, `trade_gen.v2` stays false, organic serving stays Arm B.

---

## 2. Problem

Live generation is two-layered in the way the operator described, but layer 2 is not bilateral fit:

- Knockouts include **value floors** (dual surplus, `rv ≥ gv`, #108, fairness 0.75/0.55, Elo gap, filler). Those are “do we like this?” dressed as “must not show.”
- Roster fit is weak and one-sided (R5 = viewer, contender-only).
- Unranked partners never get a partner score.

The operator wants the inverse: **thin category knockouts**, then **independent team scores**, then **aggregate rank**. Preferences are a presentation filter.

---

## 3. Knockouts (construction). Closed.

A candidate that fails any of K0–K7 is dead. Scoring never sees it. **Nothing else is a knockout in this arm.**

| ID | Rule | Spec |
|---|---|---|
| **K0** | Roster physics | An asset may appear on a side only if that team’s roster currently holds it (players + owned picks). Not a named product rule — the enumerator does not invent assets. |
| **K1** | Package size | 1–3 assets per side. Legal shapes: 1-1, 2-1, 1-2, 3-1, 1-3, 3-2, 2-3. Kill 4+ on a side or 3-for-0. **Wider than live v3** (`|n−m| ≤ 1` is gone; 3-for-1 is in). |
| **K2** | Pick-for-pick | **Byte-identical to live C3** (`pick_swap_ok` + `strip_matched_pick_pairs`, `pick_pair_strip_frac = 0.85`). Matched pick pairs stripped regardless of year. Empty side after strip → kill. Literal 1-for-1 pick swap → kill. Consolidation (2 lesser for 1 better) lives. A matched 1st riding inside a player deal dies. |
| **K3** | Both lineups startable | Live `_feasible_after`, **both** rosters, **every** path (today this is v3-only; consensus must gain it). Starter counts: QB 1 / RB 2 / WR 2 / TE 1; SF QB 2. Flex ignored (same as live). |
| **K4** | G6 R1 overpay | Live `overpay_ok`. Kill when raw consensus gap ≥ `max_overpay_min_value` (500) **and** ≥ `max_overpay_frac` (0.25) of the bigger side. Either direction. Independent of the client fairness toggle. |
| **K5** | G6 R2 position net | Live `pos_net_ok`. Net bodies at QB/RB/WR/TE cannot move by more than `pos_net_cap` (1). Picks uncounted. |
| **K6** | G6 R3 pick-is-the-gap | Live `pick_gap_ok`. Unchanged knobs. |
| **K7** | G6 R5 need | **Live as written** for v1 of this arm. Untargeted decks; **viewer roster only**; championship/contender kill unless upgrade or hole-fill or sub-floor; not_sure kills on surplus positions; rebuilder/unresolved pass. Partner not checked. Dualizing R5 is a follow-up (F7), not v1. |

Reuse the live predicates. Do not fork R1–R3/C3 math. Call them from the new module.

### Explicitly not knockouts

| Live rule | This arm |
|---|---|
| Divergence prune (`_vo ≥ 0.97 × user`) | **Gone.** Enumerator uses the bound in §5, not that direction filter. |
| Must have Elo on both boards | **Gone.** Missing board → that team scores lens 3 only. |
| Dual surplus ≥ 60 / 150 | **Score** (lens 1 / 3). Negative surplus is a low score, not a kill. |
| Consensus `rv ≥ gv` | **Score.** This is the volume unlock. |
| Fairness 0.75 / 0.55 hard gate | **Score** (lens 3). Range-overlap is not a pass/fail. |
| #108 1-for-1 user-gain | **Score** (viewer lens 1). Sending a player you rank higher is allowed; it should score badly for you. |
| Filler / `asset_floor_abs` | **Gone** as a kill. Junk adds score badly via lens 3 / package value. |
| Elo gap 250 | **Gone.** |
| Consolidation 15% raw-loss | **Gone.** |
| Untouchables / not-interested / pins / acquire-positions / intent | **Post-score filter** (§6). |
| C4 / C4b headliner caps | Deck assembly after rank (same as live), not a category knockout. |
| Likes-you injector | **Out of this arm.** Do not inject ungated partner-likes. Measure the scorer clean. |

---

## 4. Scoring (0–100 per team)

For package `P` and team `T` (the other team is `U`):

Define, in the v2 value space (`elo_to_value` + `package_value_v2` + waiver slot cost, same as live so numbers are comparable):

- `surplus_board(T)` = receive_T − give_T on **T’s** Elo map, if T has rankings; else `null`
- `surplus_consensus(T)` = receive_T − give_T on **seed** (always)

Map a surplus onto 0–100 with a signed curve, knobs in `model_config`:

```
fit_score_scale   default 400    # surplus that maps to ~84
fit_score_even    default 50     # surplus 0 → this
score(s) = clamp( even + 50 * tanh(s / scale), 0, 100 )
```

Even on that lens → 50. Big win → 100. Big loss → 0. Continuous; no cliff at 0.

**Lens 1 — board vs board.** If T has rankings: `L1(T) = score(surplus_board(T))`. If not: omit. The pairwise “two rank sets” signal **is** both teams having L1. Do not add a third “mismatch” term that double-counts.

**Lens 2 — that team vs consensus.** If T has rankings: `L2(T) = score(surplus_board(T) − surplus_consensus(T))`. Positive = T likes this more than the market (steal on their board). If not boarded: omit.

**Lens 3 — consensus.** Always: `L3(T) = score(surplus_consensus(T))`. Fair market deal → both teams near 50. Viewer-wins lopsided → you high, them low. **This replaces `rv ≥ gv` as information.**

**Combine per team** (knobs; must sum to 1 among the lenses that fired):

| Team state | Formula |
|---|---|
| Boarded | `0.40 L1 + 0.30 L2 + 0.30 L3` |
| Unranked | `1.00 L3` |

Weights: `fit_w_board=0.40`, `fit_w_div=0.30`, `fit_w_cons=0.30`. If a boarded team is missing L2 because all assets are unseeded, renormalize the remaining weights.

**Card payload (always, this arm):**

```json
"fit": {
  "you": 72,
  "them": 61,
  "aggregate": 133,
  "lenses": {
    "you":  {"board": 80, "vs_consensus": 70, "consensus": 55},
    "them": {"board": null, "vs_consensus": null, "consensus": 61}
  }
}
```

`composite_score` for sort = `aggregate` (0–200). Do not run `_tier_mult_v2`, `need_fit` multiplier, `block_boost`, outlook-direction, or aggression on this arm. Those are live rank overlays; this scorer replaces them. `need_fit` may be **stamped** for telemetry, not multiplied.

**Presentment buckets** (copy + `features_json` only; **not kills**):

| Bucket | Rule |
|---|---|
| `both_high` | you ≥ 70 and them ≥ 70 |
| `mixed` | one ≥ 70 and the other in [40, 70) |
| `you_tilt` | you ≥ 70 and them < 40 |
| `them_tilt` | them ≥ 70 and you < 40 |
| `both_ok` | both in [40, 70) |
| `weak` | aggregate otherwise |

v1 **shows all buckets**, ranked by aggregate. A later knob `fit_min_them` (default 0) can hide `you_tilt` without touching knockouts. Do not default it on — that would recreate `rv ≥ gv`.

---

## 5. Enumeration (the volume is not “score 7 million packages”)

Dropping the live divergence prune without a bound is `C(25,3)² ≈ 7e6` combos per pair. **Product intent:** do not *direction-prune*. **Engineering bound:** still cap work.

**Pool (per roster, per pair):** union of

- top `fit_pool_consensus` (8) by consensus value
- top `fit_pool_div_seed` (8) by `|board − seed|` if that team is boarded
- top `fit_pool_div_opp` (8) by `|user_board − opp_board|` if **both** boarded
- always include owned picks that are in the league horizon (K0)

Cap unique ids at `fit_pool_cap` (15). If the union is larger, keep highest on a rank of `max(consensus percentile, |div| percentile)`.

**Then** all combinations of size 1..3 on each side with K1 shapes, run K2–K7, score survivors.

Budget: `C(15,3)=455`, worst `455²` is still large; **enforce `fit_max_packages_per_pair` (default 20_000)** by visiting 1-for-1 first (full pool cartesian), then 2-asset and 3-asset around the top-N 1-for-1 centerpieces (`fit_expand_from` default 25). Leave-short is data: record `enumerated`, `killed_by`, `scored` on the arm diagnostics.

This is how we get **more ideas than live on the same rosters** without a 30s job: we keep assets the live prune would drop (consensus bargains, you-pay-them-gain, unranked-board fills), we do not brute-force the bench.

---

## 6. After scoring (filters, not knockouts)

Applied to the ranked list, per viewer, before the deck is stored:

1. Untouchables — drop if give ∩ untouchable  
2. Not-interested — drop if receive ∩ not_interested  
3. Pinned give / receive / positions / intent — drop non-matches **when the user set them**  
4. G6 R4 + already-swiped — same keys as live  
5. C4 / C4b — same caps as live (2 / 3) unless bake-off wants them off; default **on** so decks stay readable  
6. `max_per_opponent` / global target — same numbers as the job so the bake-off compares quality, not 200-card dumps

Filters 1–3 mean a preference **never deletes the idea from the partner’s universe**; it only hides it from this viewer. That is the operator ruling (preferences ≠ knockouts).

---

## 7. Bake-off wiring

- New module `backend/trade_gen_fit.py` (`generate_league_suggestions(...)` → `list[TradeCard]` + report).
- New arm id `fit` in `bakeoff_runner.py`. **Not** in the default roster until the operator flips `bakeoff_include_fit=1`.
- Invocation: same pattern as `gen_v2` — direct call, independent of any serving flag.
- Do **not** put this behind `trade_gen.v2`. Do not change `_generate_trades_impl` organic routing.
- Cards: `basis` = `divergence` if both boarded else `consensus` (honest about data, not about which live generator ran). Stamp `model_arm=fit`. Stamp `fit` object §4.
- Measurement (must land on `bakeoff_runs.arms_json[fit].diagnostics`):

  | Field | Why |
  |---|---|
  | `enumerated` / `scored` / `killed[K1..K7]` | Did we actually search more? |
  | `one_sided_pct` | share with them < 40 (compare to live 96.3% you-pay-on-consensus) |
  | `both_high_pct` / `mixed_pct` | does the scorer create a middle? |
  | `median_aggregate` | scale check |
  | generation ms | pool cap too high? |

Success is **not** “more cards.” Success is: more *distinct legal* ideas than Arm B on the same job, with a measured like-rate that is not worse on `both_high`+`mixed`. `you_tilt` like-rate is the warning light (live viewer-wins).

---

## 8. Tickets

Independently mergeable. Estimates = one engineer who knows this repo.

| ID | Title | Who | Est | Depends |
|---|---|---|---:|---|
| **F1** | Knockout module: wrap live K2–K7 + K1 shape + K3 on all paths | backend | 1d | — |
| **F2** | Enumerator: union pool + 1-for-1 then expand, diagnostics counters | backend | 2d | F1 |
| **F3** | Dual 0–100 scorer + `fit` payload + aggregate sort | backend | 1.5d | F2 |
| **F4** | Post-score preference filters + R4 + C4 | backend | 0.5d | F3 |
| **F5** | Bake-off arm `fit`, default off the roster, diagnostics | backend | 1d | F3 |
| **F6** | Tests: K1 shapes, K2 byte-identical to live C3, unranked = L3 only, negative surplus lives, prefs don’t kill enumeration | backend | 1d | F1–F4 |
| **F7** | (follow-up, not v1) Dualize R5 — partner need as knockout or as L4 | — | — | operator |

No mobile/web ticket in v1. Bake-off decks already render `TradeCard`. Extra `fit` fields are additive; clients ignore unknown keys. A later card-evidence ticket can show you/them 0–100.

---

## 9. Flags and knobs

| Key | Default | Role |
|---|---|---|
| `bakeoff_include_fit` | 0 | roster the arm |
| `fit_score_scale` | 400 | tanh scale |
| `fit_w_board` / `_div` / `_cons` | 0.40 / 0.30 / 0.30 | boarded mix |
| `fit_pool_consensus` / `_div_seed` / `_div_opp` | 8 / 8 / 8 | pool union |
| `fit_pool_cap` | 15 | unique ids / roster / pair |
| `fit_max_packages_per_pair` | 20000 | hard cap |
| `fit_expand_from` | 25 | 1-for-1 seeds for 2- and 3-asset |
| `fit_min_them` | 0 | optional hide you_tilt; **leave 0** |
| `fit_min_aggregate` | 0 | optional floor; **leave 0** |

No new serving flag. Organic `generate_trades` must not import this module.

Reuse live G6 knobs (R1–R5, C3 frac). Changing them changes **both** Arm B and this arm — if the bake-off needs isolation, snapshot the values into the arm report; do not fork the predicates.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| 7e6 combos | §5 cap is mandatory. Test on a 16-team SF roster before rostering the arm. |
| More cards that are you-tilt | Expected. Measure `you_tilt` like-rate separately. Do not “fix” with `fit_min_them` until we see it. |
| R5 still viewer-only | Documented. F7. |
| Junk fillers return | Scoring should tank them; if they rank, add filler back as a **knob** (default off), not a silent kill. |
| Double-counting L1 and L2 | Weights are the control. Ablate in F6. |
| Confuse with landability-challenger | Different code path. Different arm id. Do not `_cfg_override` this. |

---

## 11. Acceptance

- Organic decks with `trade.bakeoff` off are byte-identical (module never imported).
- A boarded pair produces cards that live Arm B would kill on `rv ≥ gv` or dual surplus, and those cards have `fit.them` populated (possibly < 50).
- An unranked partner produces cards with `lenses.them.board = null` and `L3` only.
- K2: a 1-for-1 2026 1st vs 2027 1st is dead; a 2-for-1 two late 2nds for a 1st lives (same as live C3).
- K1: a 3-for-1 that is startable and not R1/R2 can score.
- Diagnostics show `enumerated` ≫ live prune size on a fixture league, generation ms under the job budget (record the number; operator sets the fail bar after the first dry run).

Not accepted: serving this arm to users, dualizing R5, or putting PPG/impact into the scorer.

---

## 12. Operator rulings already taken

1. Preferences (untouchables, not-interested, pins, positions, intent) = **filters after scoring**, not knockouts. (Later sentence overrode the earlier “untouchables yes.”)
2. Package size widened to 3-for-1 / 1-for-3 / 3-for-2 / 2-for-3.
3. Pick-swap stays live C3, including inside larger packages.
4. Startable + G6 are the only value-adjacent knockouts. Surplus/fairness/#108/filler/prune are scores or gone.
5. Two 0–100 scores, present by combined total.

Open (do not block F1): F7 dual R5; whether C4 stays on for this arm (default on).
