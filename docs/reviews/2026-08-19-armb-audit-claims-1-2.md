# Arm-B engine audit — external-review claims 1 and 2

> **Purpose:** adjudicate two claims from an external review of the arm-B trade
> engine. Verification only — no engine behaviour was changed by this memo.
> Every mechanism asserted here is cited `file:line` against `origin/main` at
> **`16d277f`** (2026-08-19). Live knob values were read from prod
> `model_config` read-only; the empirical section was measured on prod
> `deck_impressions` (SELECT only, `SET TRANSACTION READ ONLY`).

**Date:** 2026-08-19
**Scope:** claim 1 ("consensus cards force the user to win"), claim 2 ("raw
1-for-1 gain gate is user-only"). Both rated *hard* by the reviewer.
**Reference SHA:** `16d277f5c12a8d1c36b36534b74ac1cabe0df0a3`
**Prod window measured:** `deck_impressions`, 8,617 rows,
2026-07-27T01:15Z → 2026-08-19T18:15Z.

## Contents

- [Verdict summary](#verdict-summary)
- [Live knob and flag state](#live-knob-and-flag-state)
- [Claim 1 — consensus cards force the user to win](#claim-1--consensus-cards-force-the-user-to-win)
- [Claim 2 — raw 1-for-1 gain gate is user-only](#claim-2--raw-1-for-1-gain-gate-is-user-only)
- [Empirical asymmetry on served cards](#empirical-asymmetry-on-served-cards)
- [What the reviewer missed](#what-the-reviewer-missed)
- [Open anomaly — R1 did not fire on 5 of 118 post-G6 jobs](#open-anomaly--r1-did-not-fire-on-5-of-118-post-g6-jobs)
- [Relationship to D-079 … D-091](#relationship-to-d-079--d-091)
- [Method and limits](#method-and-limits)

## Verdict summary

| # | Sub-claim | Verdict |
|---|---|---|
| 1a | One-sided `rv - gv` test on the consensus path | **CONFIRMED** |
| 1b | `user_gain_epsilon = 0`, path always live | **CONFIRMED** |
| 1c | Fairness leaves a band that is *entirely* partner-overpay | **PARTIALLY CONFIRMED** — the band is real and *wider* than stated (0.50, not 0.75), but it is not the only bound: R1 `overpay_ok` is a symmetric absolute ceiling the reviewer did not account for |
| 1d | `trade.divergence_fallback` routes boarded-but-zero-divergence members here | **CONFIRMED** |
| 1e | Consensus enumerates only 1-for-1 then 2-for-1 (user gives 2) | **CONFIRMED** — 7,094 served consensus cards are 100 % `1x1` or `2x1`, zero `1x2` |
| 2a | `user_gain_ok_1for1` exists and is wired at the three named sites | **PARTIALLY CONFIRMED** — wired at *four* sites; the reviewer's list of three is right but incomplete, and one of the three is indirect |
| 2b | No partner-side equivalent anywhere | **CONFIRMED** (in the live engine; a symmetric design exists in dark code) |
| 2c | Partner's only test is `opp_surplus >= MIN_SIDE` on marginal values | **CONFIRMED** for boarded partners; **REFUTED** for consensus cards, where the partner has no surplus test at all |
| 2d | #189 relaxation drops the surplus floor to 0.0, gates intact | **CONFIRMED** |
| 2e | `fit_premium` live, max loss 300, no partner analogue | **CONFIRMED** |

Net: the reviewer is directionally correct on both claims and is right about
the specific code. Where they are wrong is in the *completeness* of their model
of the gate stack — they treat the min/max fairness ratio as the partner's only
protection, and it is not; and they understate the size of the live fairness
band by 2×.

## Live knob and flag state

Read from prod `model_config` (read-only). Where a key is absent from
`model_config`, `_c()` falls through to `_DEFAULT_CFG`
(`backend/trade_service.py:804-810`).

| Knob | Live value | Source |
|---|---|---|
| `user_gain_epsilon` | **0.0** | **not present in prod `model_config`** → `_DEFAULT_CFG` (`backend/trade_service.py:220`). Also absent from the `database.py` seed list, so no admin has ever set it. |
| `min_side_surplus` | 150.0 | prod `model_config`; default `backend/trade_service.py:146` |
| `min_side_surplus_marginal` | 60.0 | prod `model_config`; default `backend/trade_service.py:210` |
| `relaxed_surplus_floor` | 0.0 | prod `model_config`; seed `backend/database.py:2303` |
| `relaxed_fairness_threshold` | 0.55 | prod `model_config`; seed `backend/database.py:2302` |
| `fairness_floor_divergence` | 0.55 | prod `model_config`; seed `backend/database.py:2300` |
| `fit_premium_max_loss` | 300.0 | prod `model_config`; seed `backend/database.py:2315` |
| `consolidation_raw_loss_frac` | 0.15 | prod `model_config` |
| `filler_min_frac` | 0.25 | prod `model_config` |
| `max_overpay_frac` (R1) | 0.25 | prod `model_config`; default `backend/trade_service.py:637` (`max_overpay_frac`) |
| `max_overpay_min_value` (R1) | 500.0 | prod `model_config`; default `backend/trade_service.py:638` |

Flags (`config/features.json` on `16d277f`):

| Flag | State | Line |
|---|---|---|
| `trade.divergence_fallback` | **true** | `config/features.json:63` |
| `trade.presentment_rules` (R1–R5) | **true** | `config/features.json:67` |
| `trade.fit_premium` | **true** | `config/features.json:43` |
| `trade_engine.v3` | **true** | `config/features.json:34` |
| `trade.marginal_value` | **true** | `config/features.json:28` |
| `trade_gen.v2` | **false** (dark) | `config/features.json:62` |

Fairness threshold — **the reviewer's 0.75 is not the live default**:

- Server default is `0.50` for pinned/opponent-scoped jobs, `0.75` otherwise
  (`backend/server.py:10838-10839`).
- The mobile client *always sends an explicit value*, and its default
  preference has been **OFF since 2026-08-17** (commit `00b2a2c`), which sends
  `FAIRNESS_OFF_THRESHOLD = 0.5` — `mobile/src/api/tradePregen.ts:25-26`,
  `:31-33`, `:45-47`, `:52-54`. An unset preference means the wide net; only an explicit
  `'on'` sends 0.75.
- Prod confirms it: the minimum `fairness_score` on a served consensus card is
  **0.501**, and the `fairness_threshold` column (added 2026-08-18) shows
  `0.75` × 568, `0.5` × 204, `0.55` × 105.

So the live band is `min/max ≥ 0.50`, i.e. the heavier side may be up to **2×**
the lighter side, not 1.33×.

## Claim 1 — consensus cards force the user to win

### 1a — the one-sided test exists. CONFIRMED.

`backend/trade_service.py:4983-4987`, inside `_generate_consensus_for_pair`'s
inner `_emit`, is verbatim what the reviewer quoted:

```python
# #108 — on a consensus card the user's board IS consensus:
#        the user's side must come out ahead (receive − give ≥ ε).
#        Fairness alone allowed the user to be the side paying up to
#        (1 − threshold) more consensus value (TC-CFG-001 gap).
if rv - gv < _c("user_gain_epsilon"):
    return
```

There is no `gv - rv` counterpart anywhere in the function
(`backend/trade_service.py:4874-5062`). The only other consolidation bound,
`consolidation_raw_loss_frac` (`:4993-4999`), is *also* user-protective: it
caps how much raw consensus value the **user** may lose on a give-side
consolidation. Nothing bounds the partner's loss on this path except R1 (below)
and the fairness ratio.

The same one-sided test is duplicated in the asset-ideas surface at
`backend/trade_service.py:3671` — the reviewer did not mention this second
instance.

### 1b — ε is 0 and the path is live. CONFIRMED, with one wording correction.

`user_gain_epsilon` default `0.0` at `backend/trade_service.py:220`; **absent
from prod `model_config`**, so `_c()` returns the default
(`backend/trade_service.py:804-810`). No flag guards the gate itself — it is
unconditional inside `_emit`.

Correction on "live always": the *gate* is unconditional, but the *path* is
reached in exactly two situations
(`backend/trade_service.py:4194`, `:4264-4267`):

1. `else:` — the opponent has no board (`not member.has_rankings` or no
   `elo_ratings`) → `_generate_consensus_for_pair` (`:4267`);
2. the boarded member's divergence path returned zero cards **and**
   `FLAGS.trade_divergence_fallback` → same generator (`:4264-4265`).

That is not "always", but it is the overwhelming majority of what ships:
**7,094 of 8,419 own-deck served cards (84.3 %) carry `basis: "consensus"`.**

### 1c — "the entire 25 % band is partner-overpay". PARTIALLY CONFIRMED.

Two errors, one in each direction.

**Understated.** The live threshold is 0.50, not 0.75 (see the knob table). The
one-sided band is therefore twice as wide as the reviewer claims.

**Overstated.** Fairness is *not* the partner's only protection. R1 `overpay_ok`
— shipped 2026-08-16 (`b280b24`, G6 wave), flag `trade.presentment_rules: true`
— is an explicitly **both-sides**, threshold-independent absolute ceiling:

```python
def overpay_ok(give_ids, recv_ids, seed_value) -> bool:
    """R1 #340 — absolute overpay ceiling, BOTH sides. ...
    Deliberately NEVER reads fairness_threshold — the mobile fairness
    toggle cannot relax it; this is the operative absolute bound on both
    settings."""
```
`backend/trade_service.py:1654-1673`

It kills when `gap >= 500` **and** `gap / max(g, r) >= 0.25` on raw summed
`seed_value` — in either direction. It is threaded into the consensus generator
via `presentment_ok_fn` (`backend/trade_service.py:4170-4191` builds `_consensus_kw`
with it; `:5014-5016` calls it inside `_emit`; the predicate itself is
`:4129-4149`, R1 at `:4131-4133`). It is also on the v2 path (`:4675-4677`) and
the v3 path (`backend/trade_optimizer.py:553-555`).

So the reviewer's sentence "fairness was their only protection, and it is now
one-sided" is **wrong as of 2026-08-16**. The correct statement is: the partner
is protected by a *relative-and-absolute* ceiling that permits any overpay under
500 raw consensus value or under 25 % relative — while the user is protected by
an *unconditional* ε = 0. The asymmetry is real; it is one of degree, not of
existence.

Caveat: R1 is not firing on every job. See
[Open anomaly](#open-anomaly--r1-did-not-fire-on-5-of-118-post-g6-jobs).

### 1d — `trade.divergence_fallback` routes boarded members here. CONFIRMED.

`backend/trade_service.py:4264-4265`:

```python
if not cards and FLAGS.trade_divergence_fallback:
    cards = self._generate_consensus_for_pair(**_consensus_kw)
```

Flag is `true` (`config/features.json:63`). The flag's own comment already
records this as an accepted consequence: "a member with `has_rankings=true` can
now carry `basis:'consensus'` cards" (`config/features.json:61`). The reviewer's
description is exact.

### 1e — enumeration is 1-for-1 then 2-for-1 (user gives 2). CONFIRMED.

`backend/trade_service.py:5045-5060`: the outer loop emits `[give_id], [recv_id]`,
then the second pass emits `[g1, g2], [recv_id]` over
`combinations(give_pool, 2)`. `recv_ids` is a one-element list at every call
site. There is no `1x2` shape in this generator.

Prod agrees exactly: of 7,094 served consensus cards, **6,635 are `1x1` and 459
are `2x1`. Zero are `1x2` or anything else.**

The reviewer's follow-on ("would fail `rv ≥ gv` if it were") is a counterfactual
I cannot test, but it is directionally sound: on a user-receives-two shape
`package_value_v2` depth-discounts the received pair
(`backend/trade_service.py:1098-1177`, `_package_value_market` at `:1178-1219`)
while the given single asset is undiscounted, so `rv - gv` would sit negative at
raw parity. Note the mirror-image protection that *would* be needed —
`consolidation_raw_loss_frac` — exists only for the give-side direction
(`:4993-4999`), which is consistent with the enumeration never producing the
other one.

## Claim 2 — raw 1-for-1 gain gate is user-only

### 2a — exists, and is wired. PARTIALLY CONFIRMED (four sites, not three).

`user_gain_ok_1for1` is at `backend/trade_service.py:1486-1510`; the docstring
the reviewer quoted is verbatim `:1492-1503`. Direct callers:

| Site | Line | Note |
|---|---|---|
| `fit_premium_1for1` | `backend/trade_service.py:2439` | the wrapper — this is how v2 and v3 reach the gate |
| `_generate_asset_ideas_impl._eval` | `backend/trade_service.py:3678` | **reviewer missed this one** |
| `_generate_consensus_for_pair._emit` | `backend/trade_service.py:5002` | reviewer's "consensus `_emit`" ✓ |

Indirect, via `fit_premium_1for1`:

| Site | Line |
|---|---|
| v2 `_generate_for_pair_v2._consider` | `backend/trade_service.py:4657-4660` |
| v3 `generate_pair_trades_v3` main loop | `backend/trade_optimizer.py:535-538` |

So the reviewer's "wired in `_consider`, consensus `_emit`, and live v3 via
`fit_premium_1for1`" is accurate but names three of four surfaces, and slightly
mis-frames `_consider` (which reaches the gate *through* `fit_premium_1for1`,
not directly).

### 2b — no partner-side equivalent. CONFIRMED.

`user_gain_ok_1for1` takes `raw_user_elo` only (`:1486-1489`); `fit_premium_1for1`
takes `raw_user_elo` and `user_needs` only (`:2422-2427`). Neither has an
opponent parameter. Grepping every `*_ok(` gate function in the module
(`filler_ok :1513`, `pick_swap_ok :1597`, `overpay_ok :1654`, `pos_net_ok :1676`,
`pick_gap_ok :1701`, `need_gate_ok :1735`) finds none that reads the opponent's
board in an ordering sense: `filler_ok` uses a max-of-boards *magnitude* rule,
and R1/R2/R3/R5 are consensus- or roster-shaped, not partner-board-ordered.

One genuinely symmetric design exists and is **dark**: `backend/trade_gen_v2.py`
gates `user_gain < epsilon` **and** `opp_gain < epsilon` on each side's own
board (`:632-638`, `gen2_epsilon = 100.0` at `backend/trade_service.py:559`).
Flag `trade_gen.v2` is `false` (`config/features.json:65`), so it ships nothing.

### 2c — the partner's only test is `opp_surplus >= MIN_SIDE`. CONFIRMED for divergence, REFUTED for consensus.

For **boarded** partners (divergence cards) the reviewer is exactly right:

- v3: `backend/trade_optimizer.py:559-561` —
  `if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE: continue`, with
  `MIN_SIDE = min_side_surplus_marginal (60) if MARGINAL else min_side_surplus (150)`
  at `:261-262`. `trade.marginal_value` is on, so the live floor is **60**.
- v2 (dark under v3, kept live as fallback): `backend/trade_service.py:4718-4721`,
  `MIN_SIDE` at `:4481-4482`.
- `_surpluses` (`backend/trade_optimizer.py:455-480`) is a package-aggregate on
  `package_value_v2`, not an asset-ordering test.

For **consensus** cards the claim understates the problem: the partner has **no
surplus test at all**. `_generate_consensus_for_pair` never computes an opponent
value — by construction it has no opponent board
(`backend/trade_service.py:4874-4906`, `:4917-4921`). The partner's entire
protection on 84 % of served cards is the fairness ratio plus R1.

One correction that *weakens* the reviewer's fairness argument: the stated
rationale for the user gate is that shrinkage can invert the user's ordering
(`:1493-1498`). That distortion does not exist on the partner side —
`_shrink_user_elo` is applied only to the requesting user
(`backend/trade_service.py:4021`), and `_vo` reads `opponent.elo_ratings` raw
(`backend/trade_service.py:4499-4514`, `backend/trade_optimizer.py:292-306`). The
gate is a correction for a user-side-only artefact, not a favour the partner was
denied. The reviewer's framing ("partner has no twin") is factually right and
rhetorically loaded.

### 2d — #189 drops the surplus floor to 0.0, gates intact. CONFIRMED.

`_relaxed_targeted_pass` (`backend/trade_service.py:3479-3533`):

- stage 2 sets `min_side_surplus` and `min_side_surplus_marginal` to
  `relaxed_surplus_floor` (`:3509-3521`), live value **0.0** (prod
  `model_config`; `backend/database.py:2303`) — "0 still requires non-negative
  surplus both sides".
- the docstring is explicit that the #108 gates are never relaxed
  (`:3492-3496`): "NEVER relaxed: the #108 user-board gates
  (`user_gain_epsilon`, `fit_premium_1for1` / `user_gain_ok_1for1`),
  `untouchable_ids`, and the G6 presentment rules".

Scope correction: this pass fires only after a **targeted** job returns zero
cards, not on ordinary decks. Prod shows **1** served card carrying
`relaxed: true` across the whole 8,617-row window, so its practical weight today
is nil.

### 2e — `fit_premium` live, cap 300, no partner analogue. CONFIRMED.

`trade.fit_premium: true` (`config/features.json:43`); `fit_premium_max_loss`
`300.0` in prod `model_config` (default `backend/trade_service.py:440`, seed
`backend/database.py:2315`). The function is user-only (`:2422-2454`): it
requires `recv_pos in user_needs and give_pos not in user_needs`
(`:2447-2449`) and prices the loss purely on `raw_user_elo` (`:2450-2453`).
No opponent-side counterpart exists.

Prod scale: **4** served cards carry `fit_premium: true` in the whole window.
The mechanism is real; its live blast radius is negligible.

## Empirical asymmetry on served cards

Source: prod `deck_impressions.features_json` (`basis`, `give_value`,
`receive_value`, `fairness_score`, `shape`, `likes_you`). 8,617 rows,
2026-07-27 → 2026-08-19. `give_value` / `receive_value` are written straight off
the card (`backend/server.py:3843-3856`), so they are the same numbers the gates
ran on.

**Likes-you cards must be excluded.** 188 served cards carry `likes_you: true` —
these are another user's card mirrored onto this user, so the #108 gate ran in
the *other* direction. 117 of them show `rv < gv`. Every single negative-delta
"consensus" card in the corpus is one of these. Once they are removed:

| Population | n | user pays | exactly 0 | partner pays 0–25 % | partner pays > 25 % |
|---|---:|---:|---:|---:|---:|
| **consensus, own deck** | 7,094 | **0 (0.00 %)** | 226 (3.19 %) | 6,116 (86.21 %) | 752 (10.60 %) |
| divergence, own deck | 1,325 | 347 (26.19 %) | 0 | 484 (36.53 %) | 494 (37.28 %) |
| consensus, likes-you (mirror) | 188 | 117 (62.23 %) | 0 | 11 (5.85 %) | 60 (31.91 %) |

("user pays" = `receive_value < give_value`; bands are
`(rv − gv) / max(gv, rv)`.)

**This is as one-sided as a distribution gets.** Across 7,094 served consensus
cards there is not one where the user is the side paying consensus value.
Median relative delta `+0.143`, mean `+0.152`. The alleged partner-overpay band
is not hypothetical: **752 cards (10.6 %) ask the partner to hand over more than
25 % more consensus value than they get back**, median absolute gap 498, and 374
of those exceed a 500-point gap. The mirror population is the control: on
likes-you cards, where the gate ran for someone else, 62 % have the user paying.

The divergence population is the useful contrast and partly *defends* the
engine: 26 % of divergence cards do have the user paying on consensus value —
including 43 of 102 1-for-1s — because there the user's gate is on their own
raw board, not on consensus. The absolutism is specific to the consensus path.

Shape check for claim 1e: consensus cards are `1x1` × 6,635 and `2x1` × 459.
Zero `1x2`. Divergence, by contrast, spans `3x2` (396), `3x3` (273), `2x1` (202),
`2x2` (139), `1x1` (102), `2x3` (95).

### The D-091 phantom-pick confound

[D-091](../../living-memory/DECISIONS.md) fixed a phantom 2029 draft class today
and warns that 2026-08-16 → 08-19 like/pass data is contaminated (339 of 2,651
served cards, 12.8 %, carried a phantom pick).

Effect on this memo: **the confound is real but does not touch the finding.**

- `assets_json` is only populated from 2026-08-16T23:15Z, so I can measure the
  phantom rate on 2,881 of 8,617 rows: **431 (15.0 %)** mention a `_2029_` pick;
  189 of 2,070 consensus cards (9.1 %).
- The fix merged at 2026-08-19T18:25Z; the last impression in the corpus is
  18:15Z. **The entire window is pre-fix.**
- But the claim under test is a sign test, not a magnitude test. A phantom pick
  changes *which* assets get packaged, not *which direction* the ε gate points.
  Dropping the 189 identifiable phantom consensus cards leaves the "user pays"
  count at 0, unchanged.
- It does move the partner-overpay tail slightly: of the 258 partner-pays-25 %+
  consensus cards inside the assets window, 39 (15 %) involve a 2029 pick. Call
  the 10.6 % band figure accurate to roughly ±1.5 pp until a clean post-fix
  window exists.

## What the reviewer missed

**Strengthens their case:**

1. The live fairness threshold is **0.50**, not 0.75
   (`mobile/src/api/tradePregen.ts:25-26`, `:45-47`; confirmed by a 0.501
   minimum served `fairness_score`). The one-sided band is twice as wide as
   they argued.
2. The identical one-sided `rv - gv` test also governs the **asset-ideas**
   surface (`backend/trade_service.py:3671`), which they did not cite. Same
   reasoning, second surface.
3. On the consensus path the partner has **no surplus floor at all** — not just
   no ordering gate. Claim 2c is truer than stated.
4. The `likes_you` mirror population is a natural experiment confirming the
   gate's directionality: 62 % of mirrored cards have the user paying vs 0 % of
   own-deck consensus cards.

**Weakens their case:**

1. **R1 `overpay_ok` exists and is symmetric** (`backend/trade_service.py:1654-1673`,
   wired at `:4131`, `:5014`). "Fairness was their only protection" is false as
   of 2026-08-16. This is the single largest error in claim 1.
2. The shrinkage rationale for the user gate (`:1493-1498`) does not apply to
   the partner, because only the user's Elo is shrunk
   (`backend/trade_service.py:4021`; `_vo` reads raw at `:4499-4514`). A twin
   gate for the partner would be correcting a distortion the partner does not
   suffer.
3. `#189` relaxation and `fit_premium` are both live but empirically ~nil: 1 and
   4 served cards respectively across 8,617.
4. `trade_gen_v2` already implements the symmetric two-sided epsilon the
   reviewer implicitly asks for (`backend/trade_gen_v2.py:632-638`); it is dark
   (`trade_gen.v2: false`), which makes this a shipping decision rather than a
   design gap.

## Open anomaly — R1 did not fire on 5 of 118 post-G6 jobs

Found while testing claim 1c; **not** part of either claim, and not resolved
here.

R1 should kill any card where the raw consensus gap is ≥ 500 **and** ≥ 25 % of
the larger side. For a `1x1` card whose assets are both below
`crown_elite_value` (6,000), `package_value_v2` in `market` mode is the identity
(`backend/trade_service.py:1098,1149` → `_package_value_market:1178-1219`;
single-asset sides are never depth-discounted and earn no crown credit), so the
stored `give_value` / `receive_value` **are** the raw sums R1 reads.

Among cards served after the G6 merge (`b280b24`, 2026-08-16T00:29Z), 22 such
cards were served that R1 should have killed — 20 consensus, 2 divergence. They
cluster in **5 deck jobs out of 118**, including jobs first served
2026-08-19T17:13Z and 17:16Z, three days after the flag went live. Example
(impression `1e5292a8026e44aa9ab36db00d3fda41`, job
`21ced9898e4346d5a158933a7a3271ff`): give a 2026 1st at 2,117.0, receive player
`9224` at 4,012.8 — gap 1,895.8, ratio 0.472, both far past the R1 bar.

The affected cards span both bases, so this is not a consensus-path-specific
hole. Candidate explanations, none verified: a per-job `_cfg_override` leaking
G6 disable values (the bake-off arm-A profile disables exactly these knobs —
[D-083]/`bakeoff_profiles.MODEL_A_PROFILE`); an `FTF_FLAGS` env override on
Render turning `trade.presentment_rules` off for some requests
(`backend/feature_flags.py:901-927` — env beats `config/features.json`); or
impression rows written by a generator path that does not receive
`presentment_ok_fn`. Worth its own investigation; it materially affects how much
credit R1 deserves in verdict 1c.

## Method and limits

- Worktree cut from a freshly fetched `origin/main` at `16d277f`; branch
  `audit/armb-claims-1-2`. No engine file was modified.
- Prod access was read-only: `psycopg2` with `set_session(readonly=True)` plus an
  explicit `SET TRANSACTION READ ONLY`; SELECT statements only. The DSN was read
  from the gitignored `secrets.local.env` and scrubbed from every error path.
- `deck_impressions` is *served* cards, so it cannot show what the gates
  rejected. Statements about killed candidates are code-derived, not measured.
  `presentment_kill_counts` (`backend/trade_service.py:3466-3470`) is in-process
  only and is not persisted.
- `assets_json` exists only from 2026-08-16, so phantom-pick attribution covers
  2,881 of 8,617 rows.
- No D-/G-/M-/Q- id is allocated by this memo.
