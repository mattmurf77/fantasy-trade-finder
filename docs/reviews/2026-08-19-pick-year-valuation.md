# How draft-pick value decays with distance — investigation and fix

**Date:** 2026-08-19
**Decision:** [D-079](../../living-memory/DECISIONS.md)
**Open question raised:** [Q-018](../../living-memory/OPEN_QUESTIONS.md)
**Trigger:** two tester decline reasons from the operator (`trade_pass_reasons`, prod), plus a third from two days earlier

---

## Table of contents

- [The short version](#the-short-version)
- [What triggered this](#what-triggered-this)
- [What the code did before this change](#what-the-code-did-before-this-change)
- [The measured defect, against the live corpus](#the-measured-defect-against-the-live-corpus)
- [External calibration — and where it disagrees with us](#external-calibration--and-where-it-disagrees-with-us)
- [What I changed](#what-i-changed)
- [Before / after](#before--after)
- [Evidence](#evidence)
- [What I could not determine](#what-i-could-not-determine)

---

## The short version

The app priced every draft pick with one rule: lose 15 % of your value for each season the pick is in the future. Applied to a first-round pick that is aggressive — after three years a 2029 1st was worth only 61 % of a 2026 1st. Two bad things followed, and the operator reported both:

1. **A far-out 1st got cheap enough to buy with a mid-tier player.** The deck literally served "give Davante Adams, get a 2029 1st" as an even trade.
2. **Two 1sts of different years became different-priced copies of the same thing**, which is free money to a value optimizer. About 1 in 20 served cards was a 1st-for-a-different-year-1st swap.

The fix: the decay rate is now **per round**, and **round 1 is flat** — a 2029 1st is worth exactly a 2026 1st. Rounds 2–4 keep the 0.85/yr they always had. The rates are `model_config` knobs, so setting all four back to 0.85 reverts everything without a deploy.

**One thing the operator should know before this ships:** the flat-firsts rule is a product decision that the outside market does *not* support. Every public valuation source discounts future firsts, and three of the four discount firsts *harder* than later rounds — the opposite of the model we just built. That does not make the fix wrong (it does close the reported defect, cleanly), but it means we are now deliberately pricing firsts above the market. Details in [the calibration section](#external-calibration--and-where-it-disagrees-with-us); logged as Q-018.

---

## What triggered this

Verbatim, from `trade_pass_reasons` in production (user `313560442465169408`, league `1312140920132497408`):

> **2026-08-19T03:48:53Z** — "I think 2029 1st values are the issue. Adams is rated as a 3rd for me. Offering him for a 1st is nonsense so it must be how value is assigned for a pick so far out."

> **2026-08-19T03:46:12Z** — "Still seeing pick swaps and davante Adams rated too high"

The same tester had already said it two days earlier, which the trigger report did not include and which materially strengthens the case:

> **2026-08-17T23:43:06Z** — "I just don't think the trade logic is doing what it's supposed to.. 1. why am I giving up both my QBs for a QB I rate as worse? 2. **1st round picks seem undervalued.** QBs for 1sts is nonsense in 1QB"

> **2026-08-17T23:48:46Z** — "Another example of a random 1st swap. Shouldn't happen"

> **2026-08-17T23:38:50Z** — "No need for there to be a first on both sides of the trade (new rule to incorporate.. don't add future 1st swaps). Bad value even after that."

So: three independent sessions, two distinct symptoms — **far-out firsts priced too low**, and **first-for-first swaps**. Both fall out of the same constant.

**Operator direction (a decision, not a hypothesis):**

> "firsts should hold similar value YOY. Other picks can degrade the longer away they are."

---

## What the code did before this change

### The ladder

`backend/pick_values.py:26–39` — `GENERIC_PICK_SEEDS` seeds twelve Early/Mid/Late rungs for rounds 1–4 in Elo space. `(1, "Mid")` = 1650 is the base first.

`backend/trade_service.py:712` — `elo_to_value(elo) = elo_value_base · exp(elo_value_k · (elo − elo_value_ref))`, with the live prod `model_config` values `1000 / 0.0050 / 1500`. So a Mid 1st is `1000 · e^(0.005·150)` = **2117.0** in engine value space.

### The year discount — one constant, every round

`backend/pick_values.py:41–44` (pre-change):

```python
YEAR_DISCOUNT = 0.85   # 15 % off per year out
```

Three pricing sites consumed it, all with the same flat rate and none of them round-aware:

| Site (pre-change) | What it priced |
|---|---|
| `pick_values.pick_pool_value` — `base_val * (YEAR_DISCOUNT ** years_out)` | `draft_picks.pool_value`, the engine value of an owned league pick |
| `pick_values.discount_pick_value` — `_e2v(elo) * (YEAR_DISCOUNT ** years_out)` | the #207 year-explicit generic rungs served on `/api/rankings` |
| `database.compute_pick_value` (`_PICK_YEAR_DISCOUNT = 0.85`) | the legacy 0–100 `draft_picks.pick_value` column |
| `pick_values.market_pick_pool_value` | the tail past DynastyProcess's published horizon |

`backend/server.py:1945` pins `_CURRENT_SEASON = 2026`, so a 2029 pick is `years_out = 3`.

### So, exactly, before the change

| Round | 2026 (y=0) | 2027 (y=1) | 2028 (y=2) | 2029 (y=3) |
|---|---|---|---|---|
| **1st** | 2117.0 | 1799.5 | 1529.5 | **1300.1** |
| 2nd | 818.7 | 695.9 | 591.5 | 502.8 |
| 3rd | 406.6 | 345.6 | 293.7 | 249.7 |
| 4th | 272.5 | 231.7 | 196.9 | 167.4 |

**A 2029 1st was worth 72.2 % of a 2027 1st, and 61.4 % of a 2026 1st.**

### And against Davante Adams, specifically

Two different numbers matter here and they are easy to confuse:

- **The operator's own board:** `member_rankings` row for player `2133` in league `1312140920132497408`, `1qb_ppr`, Elo **1341.3**. On the generic ladder, `(3, "Mid")` seeds at 1320 — so the operator's "Adams is rated as a 3rd for me" is exactly right, and is a statement about *his personal board*. In value space that is 452.3.
- **The consensus board the engine gates on:** `player_value_history` for player `2133`, `1qb_ppr`, 2026-08-19 → **1138.8**.

The engine's presentment gates run on the consensus sums (`trade_service.overpay_ok`, `backend/trade_service.py:1502–1521` — "raw consensus sums (players AND picks)"). So the comparison that decided whether the card shipped was **1138.8 (Adams) vs 1300.1 (2029 1st)** — a 161.3 gap, 12 % of the larger side.

`max_overpay_min_value` is 500 and `max_overpay_frac` is 0.25. A 161.3 gap clears both floors comfortably. **The card was served because the 2029 1st had been discounted down into Adams's neighbourhood.**

---

## The measured defect, against the live corpus

Read-only queries against prod (`DATABASE_URL_PROD`, `SET TRANSACTION READ ONLY`, SELECT only). `deck_impressions` rows carrying `assets_json`: **2048**.

### Picks are not an edge case — they are most of the deck

| Measure | Count | Share of 2048 cards |
|---|---|---|
| Cards containing ≥ 1 draft pick | 1199 | **58.5 %** |
| Cards with picks on **both** sides | 122 | 6.0 % |
| Cards with a **1st** on both sides | 118 | 5.8 % |
| …of those, **different years** on each side (pure year arbitrage) | **99** | **4.8 %** |
| Pure pick-for-pick (no players at all) | 0 | — |

Pick mentions by round: **1st = 1482**, 2nd = 279, 3rd = 2. Firsts are 84 % of all pick mentions, so anything wrong with first-round pricing is wrong with most of what the deck does.

Pick mentions by season: 2026 = 480, 2027 = 510, 2028 = 401, **2029 = 372**. Far-out picks are a fifth of pick traffic, not a tail.

### The 99 cross-year first-for-first swaps are the arbitrage, directly

With firsts decaying, a 2026 1st (2117.0) and a 2028 1st (1529.5) are *different-priced instances of the same asset*. An optimizer maximising value delta will happily generate "give your 2026 1st, get a 2028 1st + a 2029 1st" (that exact give/receive year shape appears in the corpus) because it books +942 of value for what a human reads as shuffling firsts around. Sampled give→receive year pairs from the corpus: `['2026'] → ['2028','2029']`, `['2026'] → ['2028']`, repeatedly.

Under flat firsts the value gradient between any two first-round picks is **exactly zero**, so this class of card cannot be generated by a value-seeking search at all. That is a structural fix, not a filter.

### The exact card the operator complained about

Impression `c67c2fd1e97cb6bf`, served 2026-08-19T03:42:09Z and again at 02:47:05Z:

```
GIVE:    Davante Adams                     give_value    1138.8
RECEIVE: 1312140920132497408_2029_1_9      receive_value 1300.1
```

`1300.1` is `pick_pool_value(1, 3)` to the tenth — the discount, on the wire. Sibling cards from the same deck show the same shape at other horizons: `02c5f56b1d040225` gives Adams for a **2028** 1st at `receive_value 1529.5` = `pick_pool_value(1, 2)`.

---

## External calibration — and where it disagrees with us

I pulled real numbers from four sources. **The headline is that the operator's model is not what the market does.**

### DynastyProcess — the only source with a published *rule*

Their methodology page states the rule outright: future picks are priced at 80 % of the current year's value, credited to "DFT". Data pulled live from `values.csv` (`scrape_date` 2026-08-14), the same file `backend/data_loader.PICK_VALUES_URL` already fetches:

| Rung | 2027 (1QB) | 2028 (1QB) | ratio |
|---|---|---|---|
| 1st | 1874 | 1499 | **0.7999** |
| 2nd | 206 | 165 | **0.8010** |
| 3rd | 36 | 29 | 0.8056 |
| 4th | 10 | 8 | **0.8000** |
| 5th | 4 | 3 | 0.750 |

**Flat 0.80/yr for every round.** Rounds 3–5 deviate only through integer rounding on single-digit values. DP publishes no 2029 rows, so only one year-over-year step is observable.

### KeepTradeCut — crowd-sourced, 2026–2028

Scraped from the server-rendered `playersArray` on their dynasty-rankings page (the same parse `data_loader.parse_ktc_players` uses). Round means of the Early/Mid/Late 2027→2028 ratios:

| Round | 1QB | Superflex |
|---|---|---|
| 1st | **0.830** | 0.803 |
| 2nd | **0.860** | 0.883 |
| 3rd | **0.860** | 0.881 |
| 4th | **0.856** | 0.858 |

Firsts decay *more*, though the gap is only ~3 points. KTC's board stops at 2028 — no 2029 picks.

### FantasyCalc — the only source with 2029

`api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1`:

| Round | 2026 | 2027 | 2028 | 2029 | CAGR 2027→2029 |
|---|---|---|---|---|---|
| 1st | 2874 | 2750 | 1962 | 1763 | **0.8007** |
| 2nd | 1484 | 1450 | 1274 | 1199 | **0.9093** |
| 3rd | 1000 | 995 | 893 | 895 | **0.9484** |
| 4th | 754 | 784 | 743 | 746 | **0.9755** |

Superflex is nearly identical (1st 0.8006, 2nd 0.9096, 3rd 0.9483, 4th 0.9753). **Directly on our question: FantasyCalc's 2029 1st is 64 % of its 2027 1st.** Their far-out 4ths barely decay at all.

### DynastyCalc

Mid rungs, 2027 → 2028 → 2029: 1st 5008 / 4659 / 4530 (0.930, 0.972); 2nd 2983 / 2898 / 2814 (0.972, 0.971); 3rd 1899 / 1875 / 1828 (0.987, 0.975). Same direction — firsts decay most. Their Mid 4th row is non-monotonic and almost certainly a bad extraction; discarded.

### Two caveats that matter before anyone cites the above

**Ratios only mean something on a zero-anchored scale.** DP is near-zero-anchored (a 2027 Late 4th is 7 against an Early 1st of 4240). KTC is heavily compressed (its lowest real asset sits ~170–280). An offset fit — find `c` such that `(V₂₀₂₈ − c)/(V₂₀₂₇ − c)` is equal across rounds — collapses KTC's apparent round-dependence completely at `c ≈ 555` (flat 0.834, spread 0.011), meaning **KTC's round gradient is largely a scale artifact**. FantasyCalc's does *not* flatten under any offset (spread 0.153), so FC genuinely prices far-out 3rds and 4ths as non-decaying.

**The 2027 class is hyped**, which inflates every 2027 number and makes any 2027→2028 step overstate pure time discount. The cleanest unknown-vs-unknown step available anywhere is FantasyCalc's 2028→2029: 1st 0.899, 2nd 0.941, 3rd 1.002, 4th 1.004.

A related oddity worth logging: **KTC prices 2026 picks BELOW 2027 picks at every rung** (Mid 1st 5336 vs 6152), which is backwards for a pure discount model and suggests class quality dominates time discount in crowd pricing.

### What this means for the change

| Question | Answer from the evidence |
|---|---|
| Do firsts hold value YoY? | **No.** Every source discounts them: DP 0.80, FantasyCalc 0.80, KTC 0.83, DynastyCalc 0.93. |
| Do later rounds decay *more* than firsts? | **No source says so.** DP says identical; KTC, FantasyCalc and DynastyCalc all say firsts decay *harder*. |
| Is 0.85 defensible for rounds 2–4? | **Yes, and it is the best-corroborated number available.** KTC's 1QB round means are 0.860 / 0.860 / 0.856. DP (0.80) and FantasyCalc (0.91–0.98) bracket it either side. |

So: **the round-1 flat rule is the operator's product call and is contradicted by the market; the rounds-2–4 rate is market-corroborated and is left alone.** I implemented the direction as given — it does close the reported defect, and pricing your own recommendations above market for an asset class you want the user to hold is a coherent product stance — but the divergence is logged (Q-018) and is one config write to walk back.

A middle option, if the operator wants market alignment later without re-opening the swap defect: put **all four rounds on one rate** (DP's 0.80, or the incumbent 0.85). That still kills the pure year arbitrage between two 1sts only if the rate is 1.0, so it does *not* fix symptom 2 — which is the honest argument for flat firsts on product grounds regardless of what the market says.

---

## What I changed

Nothing about `GENERIC_PICK_SEEDS`, the tier bands, or the twelve rungs' Elo. The change is confined to the year rate.

### 1. `backend/pick_values.py` — the rate becomes per-round and config-driven

New `PICK_YEAR_DECAY_DEFAULTS = {1: 1.00, 2: 0.85, 3: 0.85, 4: 0.85}`, and:

```python
def year_decay(round_: int) -> float:
    key = year_decay_key(round_)          # clamps rounds outside 1..4
    try:
        from .trade_service import _c
        rate = float(_c(key))
    except Exception:
        rate = PICK_YEAR_DECAY_DEFAULTS[int(key.rsplit("_r", 1)[1])]
    return max(0.0, min(1.0, rate))       # >1 would invert the arbitrage
```

`_c` is the same live-config accessor every other engine knob uses, so `PUT /api/admin/config/<key>` → `trade_service.reload_config()` reprices picks with no deploy. The import is lazy, preserving the module's import-safety property (`database.py` imports `pick_values`, and must never pull in `trade_service` at module load).

`YEAR_DISCOUNT = 0.85` is kept as the rounds-2–4 default and marked superseded as a *rate*.

### 2. Every pricing site now asks for the round's rate

- `pick_pool_value(round_, years_out, fmt)` → `base_val * year_decay(round_) ** years_out`
- `discount_pick_value(pick_value, years_out, round_=1)` → takes the round; returns the input unchanged when the rate is 1.0
- `market_pick_pool_value` → the past-horizon extrapolation rides `year_decay(round_)`. **Inside** DP's published window nothing changed: DP's own year-over-year price *is* the market's discount and is not re-discounted.
- `database.compute_pick_value` → `base * scale * (year_decay(round_) ** years_out)`, replacing the local `_PICK_YEAR_DISCOUNT`. Both value scales now run off one clock, which is the reason the ladder lives in `pick_values` at all.
- `server._apply_pick_rung_year_labels` → passes `rnd` (already parsed out of the rung id) into `discount_pick_value`.

### 3. Config

Four keys, in `trade_service._DEFAULT_CFG` (live) and `database._MODEL_CONFIG_DEFAULTS` (DB-seeded, `INSERT … ON CONFLICT DO NOTHING`, so an operator-tuned row survives redeploys): `pick_year_decay_r1` = 1.00, `_r2`/`_r3`/`_r4` = 0.85.

### 4. Bake-off arm A

The knob-inventory guard (`test_bakeoff_arm_a_golden.py`) demands a written decision for any new `_DEFAULT_CFG` key. Recorded in `docs/plans/three-model-bakeoff/scope-phase2.md` § Excluded: these four are **asset valuation, not generation logic**, and are deliberately live for all three arms. Pinning arm A to the old rate would make a 2029 1st worth 1300.1 to arm A and 2117.0 to arms B/C, so any deck difference would confound generation policy with a repricing — the same reasoning PLAN.md §3.4 already applies to the board itself. Same class as `elo_value_k` / `ktc_k` / `ktc_blend_weight`, which are likewise unpinned. Arm A's golden re-ran green.

### 5. Docs

`docs/cross-client-invariants.md` (new section — pick values are consumed by five surfaces), `docs/config-reference.md` (the four keys + TOC), `docs/plans/three-model-bakeoff/scope-phase2.md` (the exclusion), `living-memory/DECISIONS.md` (D-079), `living-memory/OPEN_QUESTIONS.md` (Q-018), `living-memory/TEST_LEDGER.md`, `living-memory/CHANGELOG.md`.

---

## Before / after

Engine value space, `current_season = 2026`:

| Asset | Before | After | Δ |
|---|---|---|---|
| 2026 1st | 2117.0 | 2117.0 | — |
| **2027 1st** | 1799.5 | **2117.0** | +17.6 % |
| 2028 1st | 1529.5 | 2117.0 | +38.4 % |
| **2029 1st** | **1300.1** | **2117.0** | **+62.8 %** |
| 2027 2nd | 695.9 | 695.9 | — |
| 2029 2nd | 502.8 | 502.8 | — |
| 2029 3rd | 249.7 | 249.7 | — |
| 2029 4th | 167.4 | 167.4 | — |
| Davante Adams (consensus, 1qb_ppr, 2026-08-19) | 1138.8 | 1138.8 | — |

**2029 1st vs 2027 1st:** was 0.722 of it; now exactly equal.
**2029 1st vs Davante Adams:** was 1.14× Adams; now **1.86×** Adams.

**And the gate's verdict flips**, which is the thing that actually changes what a tester sees. `trade_service.overpay_ok` (`backend/trade_service.py:1502`) kills a card when `gap ≥ max_overpay_min_value (500)` **and** `gap / max(side) ≥ max_overpay_frac (0.25)`:

| | gap | gap / max(side) | ≥ 500? | ≥ 0.25? | Verdict |
|---|---|---|---|---|---|
| Before (1300.1 vs 1138.8) | 161.3 | 0.124 | no | no | **served** |
| After (2117.0 vs 1138.8) | 978.2 | 0.462 | yes | yes | **killed** |

Pinned as a test, asserting the gate's boolean rather than the number: `test_pick_year_decay.py::test_adams_no_longer_clears_the_overpay_gate_against_a_2029_first`.

On the operator's own board, where Adams is 452.3, the gap is larger still — so the card is dead on either basis.

**Second-order, deliberate:** a far-out 1st now badges `first_1` instead of `second` on `GET /api/league/picks`. D-320-2's *rule* (the badge reflects today's value, not the pick's name) is unchanged; the value it reflects moved, and the old badge was itself a symptom the operator was reporting.

---

## Evidence

Per D-056, no Maestro and no simulator captures. What was run instead:

**Unit tests — `backend/tests/test_pick_year_decay.py`, 12 new cases:** the default rates; deep-round clamping; live config reads; the `[0,1]` clamp; the all-four-at-0.85 revert reproducing the old ladder exactly on both scales; a 2029 1st equalling a 2027 1st; later rounds still decaying and round ordering surviving at every horizon; zero value gradient between any two 1sts; the Adams overpay-gate flip; `compute_pick_value` on the same clock; round-aware rung relabelling; and a no-config fallback so a DB outage cannot take pricing down.

**Seven existing tests retargeted, each deliberately** — every one of them was asserting the old round-1 discount, and each was rewritten to assert the new intent *plus* a still-decaying round so "someone flattened every round" fails loudly:
`test_owned_picks.py`, `test_dynasty_value_pick_scale.py`, `test_league_picks_tier.py`, `test_pick_value_scaling.py`, `test_pick_pricing_m6b.py`, `test_pick_rung_year_labels.py`, `test_pick_values_in_suggestions.py`. In the last of these the fixture's "Ward ≈ a 2029 1st" seed Elo was **derived from `pick_pool_value` instead of hard-coded**, because a literal 1552.0 would have silently turned the test into "a mid player vs a 1st" after the repricing.

**Bake-off knob guard** re-run green after recording the exclusion decision.

**Code-walk proof** of the served-card behaviour, in [Before / after](#before--after) above: the `overpay_ok` predicate at `backend/trade_service.py:1502–1521`, evaluated on the real consensus numbers from impression `c67c2fd1e97cb6bf`, flips from pass to kill.

**Full suite:** `python3 -m pytest backend/tests -q` — see `living-memory/TEST_LEDGER.md` for the recorded counts.

**Manual TestFlight checklist for the operator** (this is now the only runtime evidence mobile gets):

1. Open the deck in league `1312140920132497408`. Confirm no card offers a mid-tier veteran straight up for a 2028 or 2029 1st.
2. Swipe ~30 cards. Confirm no card has a 1st on both sides with different years on each side.
3. Open **League → Picks**. Confirm a 2029 1st shows the **1st-round** tier badge, not "second", and that its value matches the 2026 1st.
4. Open the trade calculator, add a 2029 1st and a 2026 1st to opposite sides. Confirm the verdict is exactly even.
5. Confirm a 2029 **2nd** still shows visibly less value than a 2026 2nd — rounds 2–4 must still decay.

---

## What I could not determine

- **No source publishes 2029 first-round values except FantasyCalc and DynastyCalc.** KTC's board runs 2026–2028; DynastyProcess's file stops at 2028. Nothing at all beyond 2029. So the three-years-out horizon that the operator's complaint is actually about has the thinnest external evidence of any horizon.
- **Whether the operator wants the flat rule to hold past 2029.** As implemented it holds forever (a 2035 1st prices like a 2026 1st). Nothing in the corpus reaches past 2029, so it is untested in practice.
- **Whether the round-2–4 gradient should exist at all.** The operator said "other picks can degrade", not "later rounds should degrade faster". I left all three at one rate because no source supports a gradient among them; FantasyCalc is the only source that shows one, and it runs the *opposite* way from intuition (its far-out 4ths decay least).
- **Whether the 99 cross-year first swaps were harming acceptance or merely annoying.** `swipe_decisions` was not joined against them; the operator's verbal reports are the only signal on impact, and they are unambiguous but n=1.
- **DynastyProcess's "80 %" provenance.** Their page credits the rule to "DFT" (likely Dynasty Football Toolbox); the primary derivation was not traced.
- **Paywalled sources** returned nothing usable: Footballguys' Trade Value Chart Plus, DynastyLeagueFootball's calculator, Dynasty Nerds' app.
