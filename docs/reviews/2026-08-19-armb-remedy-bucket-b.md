# ARMB Remedy Bucket B — validation memo

> Validation (not implementation) of the external reviewer's **Bucket B**: four overlays they
> argue must be *deleted or inverted* rather than given a partner twin, on the grounds that a
> twin would make them worse. Their framing: *"These are the ones that pretend to be fairness
> and are actually 'you win.'"* Each row is judged on premise (is today's behaviour described
> correctly?) and remedy (is "drop or invert" right, **and is their reason right?**).

**Date:** 2026-08-19
**Scope:** read-only audit. No engine code, flag, or knob was changed.
**Code baseline:** `origin/main` @ `50e0451`. Engine code is byte-identical to the brief's
`16d277f` — `git diff 16d277f..origin/main -- backend/ config/` touches only
`config/features.json` (`account.settings_hub`) and three flag fixtures. Every `file:line`
citation below resolves on both shas.
**Prod data:** `deck_impressions` ⨝ `deck_outcomes` ⨝ `bakeoff_runs`, read-only
(`SET TRANSACTION READ ONLY`, SELECT only), 2026-08-19.

## Contents

- [Verdict summary](#verdict-summary)
- [Measurement basis](#measurement-basis)
- [Row 1 — Consensus `rv ≥ gv`](#row-1--consensus-rv--gv)
- [Row 2 — Aggression `"light"`](#row-2--aggression-light)
- [Row 3 — #189 relaxes surplus, never #108](#row-3--189-relaxes-surplus-never-108)
- [Row 4 — Range-overlap on your comparison counts](#row-4--range-overlap-on-your-comparison-counts)
- [The thing Bucket B missed](#the-thing-bucket-b-missed)
- [What I would action first](#what-i-would-action-first)
- [Confounds and limits](#confounds-and-limits)

## Verdict summary

| # | Overlay | Premise | Remedy | Blast radius (own-deck, n=7,721) |
|---|---|---|---|---|
| 1 | Consensus `rv ≥ gv` | **CONFIRMED** (with a scope correction they missed) | **WOULD MAKE IT WORSE** — impossibility argument is right, disposal is wrong | Gate binds 6,340 cards; deleting it exposes **2,877 (45.4% of consensus)** |
| 2 | Aggression `"light"` | **CONFIRMED** — but they are proposing a variant that already ships | **SOUND WITH CAVEATS** — right answer, wrong category ("drop or invert" is not what this needs) | Reorder only, ±20% on composite; 0 cards admitted or blocked |
| 3 | #189 relaxes surplus, never #108 | **CONFIRMED** | **WOULD NOT WORK** — "relax both the same" is arithmetically incoherent here | **1 card**, entire corpus |
| 4 | Range-overlap on your counts | **PARTIALLY** (Round 1 was right; reviewer has the mechanism wrong) | **WOULD NOT WORK** — the conclusion is right, the proposed repair fixes nothing | 5 cards at the live 0.50; would be far larger at 0.75 |

One-line takeaway: **the reviewer is correct that these four should not be dualized, and correct
about why on Row 1's logic — but three of the four remedies would not deliver what they think,
and the surface that genuinely "pretends to be fairness and is actually 'you lose'" is not in
their table at all** (see [The thing Bucket B missed](#the-thing-bucket-b-missed)).

## Measurement basis

**Live knob values** — prod `model_config` (158 rows), read 2026-08-19:

| Key | Prod value | Notes |
|---|---|---|
| `user_gain_epsilon` | *absent* | code default **0.0** governs — `trade_service.py:220` |
| `fairness_floor_divergence` | 0.55 | |
| `relaxed_fairness_threshold` | 0.55 | **above** the live caller threshold — see Row 3 |
| `relaxed_surplus_floor` | 0.0 | |
| `min_side_surplus` / `min_side_surplus_marginal` | 150.0 / **60.0** | marginal arm is live (`trade.marginal_value: true`) |
| `aggression_weight` | 0.20 | |
| `range_base` | 0.35 | drives Row 4 entirely |
| `max_overpay_frac` / `max_overpay_min_value` | 0.25 / 500.0 | R1 #340 |
| `consolidation_raw_loss_frac` | 0.15 | |

**Live fairness threshold is 0.50, not 0.75.** `FAIRNESS_ON_THRESHOLD = 0.75`,
`FAIRNESS_OFF_THRESHOLD = 0.5` (`mobile/src/api/tradePregen.ts:25-26`); unset resolves to OFF
per the 2026-08-17 default (`mobile/src/screens/TradesScreen.tsx:883-884`). Server defaults
match (`backend/server.py:11009` = 0.50 for the pinned wide net; `:5919`/`:9289` retain 0.75 for
legacy callers). Minimum served consensus `fairness_score` in prod is **0.501**. Round 1's
correction stands: the reviewer's Row-1 argument understates the permitted band by 2×.

**Corpus.** `deck_impressions` holds 8,630 rows (2026-07-27 → 2026-08-19). Splitting on
`deck_job_id ∈ bakeoff_runs`: **7,721 own-deck** / 909 bakeoff. Five distinct users. Basis split
on own-deck: **consensus 6,509 (84.30%)** / divergence 1,212 (15.70%) — consistent with Round 1's
84.5%.

## Row 1 — Consensus `rv ≥ gv`

> *"Dualizing = 'both must be ahead on consensus,' which is impossible. This is one-sided
> market-even. **Delete it.** Fairness (min/max ≥ 0.75) is the dual form. Also generate 1-for-2,
> not only 2-for-1."*

### Premise: CONFIRMED, with a scope correction they missed

The gate is real and one-sided:

```
backend/trade_service.py:4983-4988
            # #108 — on a consensus card the user's board IS consensus:
            # the user's side must come out ahead (receive − give ≥ ε).
            # Fairness alone allowed the user to be the side paying up to
            # (1 − threshold) more consensus value (TC-CFG-001 gap).
            if rv - gv < _c("user_gain_epsilon"):
                return
```

ε = 0.0 (`trade_service.py:220`), absent from prod `model_config`, so the code default governs.
There is no partner-side counterpart anywhere on this path. Measured on 6,340 non-likes-you
own-deck consensus cards: **0 with `receive_value < give_value`**, minimum user gain exactly
`0.0`, mean `+407.2`, median `+16.1%` of the give side. **401 cards sit within 1% of the floor** —
the gate is actively binding, not decorative.

**Scope correction.** The gate governs only what `_generate_consensus_for_pair` emits. A second
path also ships `basis="consensus"` cards and runs *none* of it: the likes-you injector at
`backend/server.py:3053-3093`. 169 such cards served; **101 (59.8%) have the user paying.**
"Consensus cards always favour the user" is true of the generator and false of the deck. Detail
in [The thing Bucket B missed](#the-thing-bucket-b-missed).

### Is dualizing `rv ≥ gv` genuinely impossible? **Yes — and they are right for the right reason**

On this path both packages are priced by the *same* `seed_value` through the *same* functional:

```
backend/trade_service.py:4976-4980
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                  other_values=rvals)
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                                  other_values=gvals)
```

`gv` already *is* "what the partner receives"; `rv` is "what the user receives". User surplus
`= rv − gv`; partner surplus `= gv − rv`. Exact negatives. A symmetric ε > 0 is unsatisfiable; a
symmetric ε = 0 forces `rv == gv` exactly and would admit ≈ 0 cards. The waiver-slot cost
(`:4713-4717`) only makes the sum *more* negative on unbalanced shapes; it never lets both sides
be ahead.

The contrast proves the mechanism is board-count, not gate-shape. The **divergence** path is
already fully dualized because it has two boards:

```
backend/trade_service.py:4718-4720
            user_surplus = recv_val_user - give_val_user
            opp_surplus  = give_val_opp - recv_val_opp
            # True mutual gain (Change 3): BOTH sides must clear the bar.
            if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE:
```

Two boards → both can gain. One board → they cannot. **The reviewer has this exactly right.**

### Is fairness the dual form? PARTIALLY

Structurally yes: `min(gv, rv) / max(gv, rv)` (`:5017`) is symmetric in its arguments, so it is a
genuine two-sided constraint. But it is **direction-blind and scale-relative** where ε is
**pure direction**. Swapping one for the other trades "the user never pays" for "nobody pays more
than (1 − t)". Those are different guarantees, and at t = 0.50 the second is weak: fairness alone
permits the user to be the paying side by up to 50% of the larger package.

### What deleting the gate would admit at the live 0.50 — measured

Removing ε leaves shape-dependent residuals:

| Shape / condition | Residual protection | Effect of deleting ε |
|---|---|---|
| `2x1` (446 own-deck cards) | `consolidation_raw_loss_frac` = 0.15 — `trade_service.py:4995-4999`, applies when `len(give) > len(recv)` | bounded at 15% raw loss; **little change** |
| `1x1`, user has raw ratings for **both** assets | `user_gain_ok_1for1` — `:5000-5003` → `:1486-1513`, same ε on the raw board | **no change** |
| `1x1`, either asset off the raw board | **ε is the only direction gate.** `user_gain_ok_1for1` returns `True` unconditionally at `:1503` (`not raw_user_elo`) and `:1512-1513` (`give_e is None or recv_e is None`) | falls back to fairness 0.50, tightened to **0.25 by R1 `overpay_ok`** (`:1654-1673`) once the raw gap ≥ 500 |

**Size of the ε-only slice: 2,877 of 6,340 non-likes-you consensus cards = 45.4%** — 1,871
pick-involving `1x1` cards plus 1,143 served with `user_value_basis = 'consensus'` (no personal
board at all). So deleting the gate flips roughly **45% of the consensus deck** from "the user
never pays" to "the user may pay up to 25% on large packages (R1-bound) or up to 50% where the
raw gap is under 500 (fairness-bound)".

### The 1-for-2 point: premise CONFIRMED, remedy would not work as stated

The consensus enumeration is genuinely one-sided in shape:

```
backend/trade_service.py:5045-5060
        # 1-for-1 first (most acceptable shape), then 2-for-1.
        for recv_id in recv_pool:
            ...
                _emit([give_id], [recv_id])
        if len(cards) < max_cards:
            for recv_id in recv_pool:
                ...
                for g1, g2 in combinations(give_pool, 2):
                    ...
                    _emit([g1, g2], [recv_id])
```

There is no `combinations(recv_pool, 2)`. **Every other generator has one** — divergence at
`:4814-4823` (a stage literally commented `# 1-for-2 (user gives 1, receives 2)`), legacy at
`:5347`/`:5392`, v3 optimizer at `trade_optimizer.py:505-507`. The consensus generator is the only
one that cannot offer the user the de-consolidating side, and consolidation is where
`package_value_v2`'s crown premium pays.

**Cost of adding it, naively.** With `r = |recv_pool|`, `g = |give_pool|`, today's candidate space
is `r·g + r·C(g,2)`; a 1-for-2 stage adds `g·C(r,2)`. At `r = g ≈ 28` that is **+10,584 on 11,368
= +93% enumeration** — bounded in practice by `max_candidates` = 30 (`:116`) and
`max_per_opponent` = 5 (`:3114`).

**But the naive version would be near-dead code, and this is the part the reviewer will mislead an
implementer on.** Both existing stages break at `len(cards) >= max_cards` (`:5047-5051`), and stage
2 runs only `if len(cards) < max_cards` (`:5053`). With `max_cards = 5` against ~784 one-for-one
candidates, stage 1 usually fills the deck: prod shows **6,001 `1x1` vs 448 `2x1`** — the existing
second stage produced just **6.9%** of consensus cards. A third stage appended after it would fire
strictly less often. To actually get 1-for-2 into decks you must **interleave shapes into one
scored candidate pool** — which the divergence path already does with its bounded top-K heap
(`:4611-4613`) — not append a loop.

**Name the conflation.** The shape gap is a *separate defect from ε*. On a 1-for-2,
`len(give) < len(recv)`, so `consolidation_raw_loss_frac` never applies and `rv − gv ≥ 0` is
*easier* to satisfy, not harder. **The ε gate is not what suppresses 1-for-2 — absence of
enumeration is.** Bundling both under one table row invites the reader to think deleting ε unlocks
the shape. It does not.

### Remedy verdict: WOULD MAKE IT WORSE

Their diagnosis is right and their impossibility argument is right, but "delete it" is the wrong
disposal: it removes the only direction gate on 45.4% of the consensus deck and replaces it with a
symmetric band sitting at 0.50, not the 0.75 they assumed. **Two-sided-ness comes from having two
boards, not from deleting the one-board gate** — and the two-board implementation already exists in
the tree, dark:

```
backend/trade_gen_v2.py:628-638
                # Gate b — dual-board ε-gain, each side on its OWN board,
                # consolidation discount on every multi-asset side.
                user_gain = side_gain(recv_ids, give_ids, uval)
                if user_gain < epsilon:
                    ...
                opp_gain = side_gain(give_ids, recv_ids, oval)
                if opp_gain < epsilon:
```

behind `trade_gen.v2: false`. The correct remedy for this row is "get the partner a board", not
"delete the user's gate".

## Row 2 — Aggression `"light"`

> *"Dual `"light"` is `"generous"` for the partner, which is a different product. Use `"fair"`
> (penalize `abs(tilt)`)."*

### Premise: CONFIRMED — but they are describing a variant that already ships

```
backend/trade_service.py:2413-2419
def aggression_variant(user_id: str) -> str:
    ...
    h = int(hashlib.md5(user_id.encode("utf-8")).hexdigest(), 16)
    return ("light", "fair", "generous")[h % 3]
```

Equal thirds by construction; `light` and `generous` are exact mirrors. Applied at
`:4395-4404`:

```
                    tilt = ((rv - gv) / max(gv, rv)) if max(gv, rv) > 0 else 0.0
                    if _variant == "light":
                        mult = 1.0 + w_ab * tilt
                    elif _variant == "generous":
                        mult = 1.0 - w_ab * tilt
                    else:   # fair — prefer balanced offers
                        mult = 1.0 - w_ab * abs(tilt)
```

**Line 4401 is, verbatim, the reviewer's proposal.** "Use `fair` (penalize `abs(tilt)`)" is not a
remedy — it is a description of an existing arm that one of five prod users is already assigned to.
Say this plainly to whoever implements: there is nothing to build.

Two further facts bound the row. First, this runs **after every gate** — `:4359-4360`, *"Bounded
reorder AFTER all gates — the fairness veto still bounds |tilt| at 1 − floor."* `light` cannot admit
a card the gates rejected; it can only float user-favourable cards up a deck that already passed.
Second, `aggression_weight` = 0.20 in prod, so the composite swing is at most ±20%.

### Why prod is ~83% `light` against a designed ⅓ — answered

I recomputed `("light","fair","generous")[int(md5(uid),16) % 3]` for all five prod user ids and
compared to the recorded `aggression_variant`. **All five match. There is no bucketing bug.**

| user | md5 bucket | recorded | own-deck cards |
|---|---|---|---|
| 313560442465169408 | light | light | **5,304 (68.7%)** |
| 479505639769370624 | generous | generous | 1,182 |
| 867830050538598400 | light | light | 977 |
| 867831697150996480 | light | light | 160 |
| 867866820202364928 | fair | fair | 98 |

The skew is **small-N plus volume concentration**: with n = 5 users, 3 landing in one bucket is
unremarkable, and the single heaviest user — 68.7% of all served cards on his own — happens to hash
to `light`. Light-bucket users hold 6,349 of 7,552 variant-stamped cards (84.1%). **The gap between
the designed ⅓ and the observed 84% is not a design defect and will regress toward ⅓ as the user
base grows.** It is, however, a reason to read nothing from the A/B: the `fair` arm has one user and
98 cards.

### Remedy verdict: SOUND WITH CAVEATS

The conclusion ("don't dualize; use `fair`") is right. The reasoning is right too — a dual of
`light` genuinely is `generous`, and the mirror structure at `:4396-4399` proves it. The caveats:

1. **Wrong category.** This is not "drop or invert". It is a bucket-assignment/config change —
   pin everyone to `fair`, or retire `trade.aggression_ab`. Presenting it as code to delete will
   send an implementer looking for a gate that does not exist.
2. **Not a fairness defect at all.** It reorders a deck that already passed every gate. Filing it
   under "pretends to be fairness and is actually 'you win'" overstates it by an order of
   magnitude relative to Rows 1 and 4.
3. **Not express-lane.** `trade.aggression_ab` is a feature-flag *and* analytics surface
   (`aggression_variant` is stamped on cards and joined in events — `server.py:10724-10727`,
   `:11390-11391`, `:11733`). Per CLAUDE.md's bright line, a change here is not a quick fix.

## Row 3 — #189 relaxes surplus, never #108

> *"Dualizing the exception list just freezes user-protection. If you relax, relax both boards the
> same, or don't relax."*

### Premise: CONFIRMED

```
backend/trade_service.py:3492-3497
        NEVER relaxed: the #108 user-board gates (user_gain_epsilon,
        fit_premium_1for1 / user_gain_ok_1for1), untouchable_ids, and the
        G6 presentment rules ...
```

and the stage ladder at `:3511-3520` does exactly what they say — stage 2 sets
`min_side_surplus` and `min_side_surplus_marginal` to `relaxed_surplus_floor` (prod **0.0**) while
`user_gain_epsilon` is never overlaid. Confirmed at the two read sites that matter: `:3671` and
`:5002` both re-read `_c("user_gain_epsilon")` with no thread-local override.

### Remedy verdict: WOULD NOT WORK — the reasoning is arithmetically incoherent

**The two gates are not on the same footing and cannot be "relaxed the same".**

- `min_side_surplus` is a **positive floor**, live at **60.0** (marginal arm on, `:4481-4482`),
  applied to **both** sides at `:4720`. Relaxing 60 → 0 moves it to *"that side's gain ≥ 0"*.
- `user_gain_epsilon` is **already 0.0**. It is not a positive floor being held while its twin
  is dropped — it is already sitting at the exact value the relaxation lowers the other one *to*.

So after stage 2 both gates read "gain ≥ 0" on their respective boards. **The #189 relaxation
equalises the two sides; it does not tilt toward the user.** The reviewer's premise sentence is
true and their inference from it is backwards.

Their second error is calling #108 an "exception list" that "freezes user-protection".
`user_gain_ok_1for1` is a **raw-board ordering test with no threshold to move**:

```
backend/trade_service.py:1514-1515
    return (elo_to_value(recv_e) - elo_to_value(give_e)
            >= _c("user_gain_epsilon"))
```

With ε = 0 that is *"the player you get outranks the player you give, on the board you built."*
There is no relaxation of that which is not "let the user lose". "Relax both the same" would
require setting ε **negative** — deliberately serving user-losing cards under a *"Stretch idea"*
label. Strictly worse than today.

**What their instinct does correctly point at, though they did not find it:**
`relaxed_fairness_threshold` = 0.55 is *above* the live caller threshold of 0.50, and both read
sites take a `min`: `relaxed_thr = min(v2_kwargs["fairness_threshold"], _c("relaxed_fairness_threshold"))`
(`:3511-3512`; same at `:3647`). At the live default that is `min(0.50, 0.55) = 0.50` — **stage 1
is a no-op.** The whole relaxation ladder was calibrated against the 0.75 world and has been
half-inert since the 2026-08-17 default flip.

**Blast radius: 1 card.** Exactly one `relaxed = true` card exists in the 7,721-card own-deck
corpus (basis `consensus`). This row is real and inert.

## Row 4 — Range-overlap on your comparison counts

> *"Dualize the *inputs* (both confidences), don't add a second user-steal loophole."*

### Premise: PARTIALLY — Round 1's rating stands; the reviewer has the mechanism wrong

**The input is one-sided.** `confidence` is the *requesting user's* map only:

```
backend/server.py:5273-5276
        # Per-player comparison counts for the requesting user — feeds the
        # v2 confidence-shrinkage step (Tier 1, Change 4). None when the
        # session has no ranking service for this format.
        confidence_counts = service.comparison_counts() if service else None
```

(`ranking_service.py:1122-1131` — *"Per-player count of unique opponents whose comparison actually
MOVED that player's Elo"*.) Threaded to the generators at `:4210`/`:4244`.

**The term is symmetric**, exactly as Round 1 rated it:

```
backend/trade_service.py:4601-4607
            g_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(gvals, give_ids)) / sum(gvals))
            r_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(rvals, recv_ids)) / sum(rvals))
            overlap = (gv * (1 + g_unc) >= rv * (1 - r_unc)
                       and rv * (1 + r_unc) >= gv * (1 - g_unc))
            if not overlap and fairness < fairness_threshold:
                return None
```

Widening either interval loosens both inequalities. **PARTIALLY** is the right premise verdict.

**Scope correction the reviewer missed: this does not touch 84% of the deck.** The consensus
generator's fairness check is a bare point ratio with no overlap disjunct
(`:5017-5019`). Range-overlap lives only in the divergence path's `_fairness` (`:4580-4609`) —
1,212 of 7,721 own-deck cards.

### It is not a "loophole" — it is a confidence-scaled floor, and it is exactly computable

`_value_uncertainty` (`:1281-1303`) returns `range_base / sqrt(1 + n)`, with `range_base = 0.35` in
prod. Let `u` be the value-weighted mean uncertainty. The overlap disjunct admits any ratio
≥ `(1 − u)/(1 + u)`. That makes the *effective* floor a function of how much the user has voted:

| live comparisons `n` | `u` | effective fairness floor |
|---|---|---|
| 0 | 0.3500 | **0.4815** |
| 1 | 0.2475 | 0.6032 |
| 2 | 0.2021 | 0.6638 |
| 5 | 0.1429 | **0.7500** |
| 10 | 0.1055 | 0.8091 |

**Prediction: no served divergence card can sit below 0.4815. Measured minimum across all 1,212
own-deck divergence cards: 0.483, with zero cards below 0.4815.** The model reproduces the observed
floor to three decimals.

**Consequence at the live 0.50 threshold:** the disjunct binds only when `u > 1/3`, i.e. **n = 0
only**. Measured: 5 divergence cards below 0.50 (min 0.483) — **0.41% of divergence, 0.065% of the
served deck.** All five are **user-favourable** (adjusted deltas of +2,259.3 and +352.8 to the
user), so the reviewer's directional worry is borne out on the observed sample, with the caveat
that N = 5.

**Consequence at 0.75 (fairness ON, now the non-default):** the disjunct binds for every asset with
n ≤ 4. **A user who turns the fairness toggle ON gets 0.75 honoured only for players they have
personally voted on five or more times; everything else silently drops to as low as 0.48.** That is
the real defect in this row and the reviewer did not find it.

### Remedy verdict: WOULD NOT WORK

The conclusion ("don't add a second loophole") is right. The proposed repair — "dualize the inputs
(both confidences)" — fixes nothing, for a reason that also explains the misdiagnosis:

**The uncertainty is applied to *consensus* values while being sourced from one *private* swipe
history.** `gvals`/`rvals` at `:4593-4600` are `seed_value(p)` — the consensus seed. How often *any*
FTF user swiped a player says nothing about how precisely the *market* prices him. Averaging in a
second user's swipe history averages two irrelevant quantities. It would also change the numbers
without changing the semantics, since the divergence path only runs when the partner has a board
anyway.

Defensible repairs, neither of which is theirs:

1. Source `_value_uncertainty` from the **consensus pool's own sample size** rather than the
   requesting user's counts (`ranking_service` already computes pool stats).
2. **Floor `u`** so the effective threshold can never fall more than a stated margin below the
   configured one — which is the property a user toggling "fairness ON" believes they are buying.

Worth flagging for whoever picks this up: `_value_uncertainty`'s own docstring already reasons
carefully about *not* making the half-width placement-aware, precisely because *"this half-width is
read by a GATE ... and gates judge the real package"* (`:1286-1292`, D-085). The same argument
applies with full force to sourcing it from a private board, and the file does not notice.

## The thing Bucket B missed

The single largest "pretends to be fairness" surface in prod is **not in the reviewer's table**, and
it is the mirror image of what they went looking for: not *you win*, but *you lose*.

**The likes-you injector** (`backend/server.py:3053-3093`) synthesises cards stamped
`basis = "consensus"` that run **none** of the consensus generator's gate block — no
`user_gain_epsilon`, no `user_gain_ok_1for1`, no `filler_ok`, no `consolidation_raw_loss_frac`, no
`pick_swap_ok`, no `presentment_ok_fn` (so **no R1 overpay ceiling**), and **no fairness threshold
at all**. Its only user-side floor is D-055's `likes_you_min_user_delta` = **−500.0** — a floor that
*explicitly permits the user to lose*.

Measured, own-deck:

| slice | n | user pays (`rv < gv`) |
|---|---|---|
| consensus, **not** likes-you | 6,340 | **0 (0.00%)** |
| consensus, **likes-you** | 169 | **101 (59.8%)** |

Worst adjusted deltas by shape: `2x3` −6,019.4 (avg −4,253.1), `2x2` −4,903.8, `1x2` −1,991.0.
Every consensus card in prod with a shape outside `{1x1, 2x1}` — 60 of them — comes from here,
because the generator can only emit those two shapes.

**Two concrete defects, both citable:**

1. **The floor and the display are in different value spaces.** `_likes_you_user_delta`
   (`server.py:2913-2925`) sums **raw** `elo_to_value` per player. The `give_value`/`receive_value`
   the user sees on the TradeValueBar are **package-adjusted** via `_consensus_packages`
   (`server.py:3070-3075`). On a `2x3`, gamma depth-discounting on the three received pieces makes
   adjusted `rv` far smaller than the raw sum — so a card clears a −500 raw floor and then renders
   the user down 6,019.
2. **The R1 non-firing Round 1 flagged is a recorded decision, not a bug.** D-055 sub-decision (5)
   / Q-G6-1 (`living-memory/DECISIONS.md`): *"likes-you gets exactly R4 dedup, none of the quality
   rules ... the D-055 floor stays its quality gate."* So Round 1's anomaly — R1 failing to fire on
   served cards — has a documented cause: the injector never calls `_presentment_ok`, by design.
   That reframes the finding from "investigate a leak" to "revisit a decision", and it means R1's
   protection is real for generator cards and structurally absent for injected ones.

Directional outcome signal (**D-091 caveat: acceptance-rate inference over this window is not
reliable** — 12.8% of historical served cards carried phantom draft picks and passed at roughly
double their like rate; treat as a prompt to look, not as evidence):

| slice | likes | passes |
|---|---|---|
| likes-you, user gains | 8 | 2 |
| likes-you, **user pays** | 3 | 23 |
| consensus, not likes-you | 61 | 120 |

## What I would action first

1. **The likes-you injector** — not on the reviewer's list, and the only surface here where a
   *majority* of served cards have the user paying. Cheapest honest fix is to move
   `_likes_you_user_delta` onto the same package-adjusted values the card displays, so the −500
   floor bounds what the user actually sees. Needs an operator call, because loosening
   D-055 sub-decision (5) reverses a recorded decision.
2. **Row 4's real defect** — the fairness toggle silently degrading to ~0.48 for thinly-voted
   assets. Only 5 cards today because the default is OFF, but it makes a user-facing control not
   mean what it says, and it gets much larger the moment anyone turns fairness ON. Fix by flooring
   `u`, not by dualizing inputs.
3. **Row 1's shape gap (1-for-2)** — real, and the only Bucket B row where the reviewer identified
   a genuine missing capability. Implement by interleaving shapes into the scored pool, **not** by
   appending a third loop, which prod says would fire on well under 6.9% of pairs.
4. **Row 2** — pin to `fair` or retire the A/B. Cheap, but it is a flag + analytics surface, so it
   runs the full gate set, not express.

**Row 3 needs no action** beyond recording that stage 1 of the #189 ladder is inert at the live
0.50 threshold.

**Do not action Row 1 as written.** Deleting `rv ≥ gv` is the one change in this bucket that would
measurably degrade the product.

## Confounds and limits

- **D-091 phantom picks.** 12.8% of historical served cards carried phantom draft picks (fixed
  2026-08-19) and passed at roughly double their like rate. Compositional measures in this memo
  (shape mix, basis mix, gate-pass counts, value deltas) are unaffected. The one outcome table is
  labelled directional and nothing in the verdicts rests on it.
- **Adjusted vs raw value space.** `deck_impressions.features_json` stores
  `give_value`/`receive_value` in **package-adjusted** space (`package_value_v2`), whereas
  `overpay_ok` and `_likes_you_user_delta` operate on **raw** consensus sums. Any "R1 violation"
  count computed from `features_json` is therefore a loose proxy and is not comparable to Round 1's
  properly-computed 22-card figure; I have deliberately not restated a violation count from it. The
  raw-vs-adjusted divergence is itself a finding — see defect (1) above.
- **N = 5 users.** Every per-user statement in this memo (notably the Row 2 aggression split and
  the five range-overlap escapes) rests on five accounts and one dominant contributor. Treat
  directional, not estimated.
- **Threshold not stored per job.** `deck_impressions` records no `fairness_threshold`, so the
  sub-0.50 divergence cards are identified against the code-derived floor rather than each job's
  own requested threshold. The 0.4815 theoretical bound matching the 0.483 observed minimum is what
  makes that attribution safe.
