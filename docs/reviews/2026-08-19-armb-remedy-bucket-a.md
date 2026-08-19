# Arm-B remediation review — Bucket A ("dualize this overlay")

**Date:** 2026-08-19
**Scope:** validation only. No engine code, flag, or knob was changed by this work. Every remedy below was measured by monkeypatching inside a throwaway process; `backend/` on this branch is byte-identical to `origin/main`.
**Baseline commit:** `origin/main` = `50e0451`. Line numbers are on that commit. Round 1 cited `16d277f`, which is `50e0451`'s parent; the only delta between them is `config/features.json` + three test flag fixtures flipping `account.settings_hub`, so **every engine line number from round 1 still resolves unchanged**.
**Empirical basis:** READ-ONLY prod (`SET TRANSACTION READ ONLY`, SELECT only) for blast radius, plus offline replay of six real prod boards through the real `TradeService._generate_trades_impl` with live prod `model_config` and live `config/features.json`.

---

## 0. Verdict summary

| # | Row | Premise | Remedy (dualize) | Remedy (delete) |
|---|---|---|---|---|
| 1 | #108 1-for-1 raw-board gain | **CONFIRMED** | **WOULD MAKE IT WORSE** (86.9 → 90.1 %) | **SOUND WITH CAVEATS** but ~cosmetic (86.9 → 85.7 %) |
| 2 | Elo shrink + placement clamp | **PARTIALLY** — clamp half is wrong | **SOUND WITH CAVEATS**, near-cosmetic on 1-for-1s, expensive | **SOUND** — the single biggest lever (86.9 → 63.2 %) |
| 3 | Filler | **REFUTED** | **WOULD NOT WORK** (86.9 → 87.1 %) | **WOULD MAKE IT WORSE** (86.9 → 100 %) |
| 4 | Need (R5) | **CONFIRMED** | **SOUND** — the one row that is both right and effective (96.3 → 88.7 %) | n/a (not an either/or row) |
| 5 | Outlook ranking | **REFUTED as stated** | **WOULD NOT WORK** for asymmetry (measured *identical* to base) | n/a |
| 6 | `fit_premium` | **CONFIRMED on numbers, REFUTED on framing** | **CATEGORY ERROR** standalone; only coherent stacked on row 1 | **WOULD MAKE IT WORSE** (86.9 → 88.5 %) |

**Two rows are built on false premises: row 3 and row 5.** Row 6's arithmetic is right but its placement in a bucket titled "these manufacture partner-overpay" is backwards — `fit_premium` is the overlay that lets the *user* pay, and deleting it makes the asymmetry worse.

**Only two rows actually move the number: row 2 (by deleting, not twinning) and row 4.** Stacked, they take the live untargeted deck from **96.3 % → 73.3 %** one-orientation-only (all-shapes: 96.6 % → 60.8 %). Everything else in bucket A is cosmetic or harmful.

---

## 1. Method, and what the number means

The harness replays six real prod boards (league `1312140920132497408`, 625 players each, real `comparison_counts` and real `placement_bands`) through the real `_generate_trades_impl`, once per ordered pair. For each unordered pair it compares the card set generated when A opens the deck against the mirrored card set when C opens it.

**one-sided % = |symmetric difference| / |union|.** 100 % means no trade shape is ever proposed to both parties; 0 % means the engine is orientation-independent.

Two shape scopes are reported throughout:

* **1for1** — the round-1 metric, single-player-for-single-player only.
* **ALL** — every emitted shape, as `(frozenset(give), frozenset(recv))`. Included because three of the six overlays (filler, need, outlook) act mostly or entirely on multi-asset packages, where the 1-for-1 metric is blind by construction.

Round 1's headline reproduced exactly on this fixture before any remedy was applied — 86.9 % / 63.2 % / 95.3 % — so the measurements below are on the same footing as round 1's.

### 1.1 Two baselines, not one — and round 1 measured the smaller surface

Round 1 ran with `bypass_need_gate=True`. Per `trade_service.py:4113-4114`, `_r5_active = not bypass_need_gate`, and `server.py:5202` derives that flag server-side: **`True` only for targeted jobs.** With `trade.presentment_rules: true` (`config/features.json`) and prod `need_gate_min_value = 500.0`, the R5 need gate is **live on every untargeted discovery deck** — the default surface.

So there are two real prod configurations, and they are far apart:

| Baseline | 1for1 | ALL |
|---|---|---|
| **Targeted** job (`bypass_need_gate=True`) — round 1's basis | 86.9 % (53/61) | 91.1 % (133/146) |
| **Untargeted** discovery deck (R5 live) — the prod default | **96.3 %** (103/107) | **96.6 %** (171/177) |

This does not contradict round 1; it scopes it. Round 1 measured the targeted path and said so. But the number the product actually ships is **96.3 %**, and the R5 need gate — row 4 — is by itself responsible for +9.4 pp of it.

### 1.2 An implementation trap that produced a false reading, and will again

`trade_optimizer.py:62-63` and `trade_gen_v2.py:118-121` do `from .trade_service import filler_ok, fit_premium_1for1, _shrink_user_elo, …`. These are **import-time value bindings**. Rebinding `trade_service.filler_ok` does not change what the v3 optimizer calls.

My first pass at row 1 patched `trade_service` only and reported a perfect no-op (86.9 → 86.9 %, identical union and agreement counts). That reading was wrong: the gate was firing 1,174,492 times and vetoing 548 candidates, but on a path that did not produce the served deck. Re-run with all three modules rebound, the same remedy moves the number to 90.1 %.

**Consequence for whoever builds any of these:** every bucket-A remedy must be changed at the definition in `trade_service.py`, never wrapped or monkeypatched, or the v3 path silently keeps old behaviour — and your A/B will report "no effect."

### 1.3 What the metric cannot see

The mirror metric measures **existence** of a shape in each orientation, not its rank. `max_per_opponent=500` in the harness, so nothing is cut by ranking. Any overlay that is a pure composite multiplier — row 5 is exactly this — **cannot move this number by construction**. That is a property of the measurement, not evidence the overlay is inert; it is stated explicitly under row 5 rather than being allowed to masquerade as a verdict.

### 1.4 Confound, stated

12.8 % of historical served cards carried phantom draft picks (D-091, fixed 2026-08-19) and were passed at roughly double their like rate. **No acceptance-rate or preference inference is drawn anywhere in this memo.** All figures are either compositional (shape/basis counts from `trade_impressions`) or replay-based (generated fresh against current code), both of which are unaffected by that defect.

### 1.5 Resolution limit

Six boards, 15 unordered pairs, 30 ordered generations per variant. Unions run 30–241 cards. Deltas of ≥5 pp reproduce as large structural shifts in union and agreement counts simultaneously and are trustworthy directionally. **Deltas under ~3 pp (rows 1, 5, 6 in isolation) are at or below the resolution of this fixture** and should be read as "did not move it," not as a signed effect.

---

## 2. Blast radius, measured

From prod `trade_impressions`, n = 10,993 (all-time):

| Slice | n | share |
|---|---|---|
| `basis = consensus` | 9,647 | **87.8 %** |
| `basis = divergence` | 1,346 | **12.2 %** |
| 1-for-1 shapes (all bases) | 9,023 | **82.1 %** |
| multi-asset shapes (all bases) | 1,970 | **17.9 %** |
| **divergence AND 1-for-1** | **91** | **0.83 %** |
| divergence AND multi-asset | 1,255 | 11.4 % |

Mapping overlays onto that:

| Row | Where it fires | Served-card surface |
|---|---|---|
| 1 — #108 | 1-for-1 only, both bases (`:5002` consensus, `:4657` + `trade_optimizer.py:535` divergence), and only when the user's raw board holds *both* pids | ≤ 82.1 % by shape, far less in practice |
| 6 — `fit_premium` escape | 1-for-1, **divergence/optimizer paths only** — the consensus path at `:5002` calls the bare gate with no escape hatch | **0.83 %** |
| 3 — filler | sides with 2+ assets only | 17.9 % |
| 2 — Elo shrink | the divergence pair loop (`user_value`); the consensus path prices on `seed_value` | 12.2 % |
| 4 — R5 need gate | every untargeted deck, **both bases** (`_presentment_ok` is threaded to all three generators at `:4191`, `:4226`, `:4252`) | largest of the six |

**Row 6 is an argument about 0.83 % of what users see.** Row 4 governs the largest surface of the six and is also the only row whose remedy is both correctly diagnosed and measurably effective.

---

## 3. Row-by-row

### Row 1 — #108 1-for-1 raw-board gain

> *Today:* never send someone you rank above the return. *Proposed:* same test on the partner's raw board, or delete both and let surplus be the test.

**Premise: CONFIRMED.** `user_gain_ok_1for1`, `trade_service.py:1486-1510`. Returns `True` for any non-1-for-1 shape and for any pid missing from the raw board (`:1503-1507`); otherwise requires `elo_to_value(recv) − elo_to_value(give) ≥ user_gain_epsilon` (`:1509-1510`). It reads `raw_user_elo` and nothing else — there is no partner term. Live knob: `user_gain_epsilon` is **absent from prod `model_config`**, so it falls through to the `_DEFAULT_CFG` value **0.0** (`trade_service.py:220`).

**Remedy — dualize: WOULD MAKE IT WORSE.**

| | 1for1 | ALL |
|---|---|---|
| BASE | 86.9 % (53/61) | 91.1 % (133/146) |
| **#108 dualized on partner's raw board** | **90.1 %** (64/71) | **93.0 %** (160/172) |

Mechanism, and it is not intuitive. These gates are **construction-time kills, not post-filters** — the comment at `trade_service.py:4671-4673` says so explicitly ("construction-time kill so the heap refills with sane candidates"). Adding a veto therefore does not prune the deck; it makes the enumerator backfill with *different* candidates. Union rises 61 → 71 and agreement *falls* 8 → 7: the partner-side veto removes shapes that happened to survive in both orientations and replaces them with substitutes that survive in only one.

The veto is not idle — of 78 served 1-for-1 cards where both pids sit on the partner's raw board, **50 have the partner losing raw value** (median margin −6.3, p10 −75.9, min −253.8). A partner-side #108 would kill two-thirds of them. It still makes orientation-dependence worse, because of the backfill.

**Remedy — delete both: SOUND WITH CAVEATS, but ~cosmetic.** 86.9 → **85.7 %** (60/70); ALL 91.1 → 90.1 %. A −1.2 pp move, below this fixture's resolution. The reviewer's reasoning ("let surplus be the test") is sound in principle — the partner side already *has* a surplus test — but deleting #108 does not measurably change orientation-dependence, because #108 was never what produced it.

**Pick: neither, standalone.** The only #108 variant that improves anything is dualize **plus** the row-6 partner-side escape hatch (84.9 %, §Row 6) — and that is a −2.0 pp move for a two-part change touching three modules. Not worth it against row 2 and row 4.

---

### Row 2 — Elo shrink + placement clamp

> *Today:* your board pulled to seed; theirs raw. *Proposed:* same shrink on `opp_elo` using their comparison counts, or shrink neither before surplus.

**Premise: PARTIALLY CONFIRMED.**

The asymmetry half is exactly right. `_shrink_user_elo` (`trade_service.py:1231-1277`) blends the user's board toward the consensus seed with `w = n/(n+shrink_pseudocount)`, `shrink_pseudocount = 4.0` in prod; it is called at `:4021-4022` and the result becomes `user_value` at `:4023`. The partner's accessor `_vo` (`:4499-4515`) reads `opp_elo` **raw** — no shrink, no clamp, no confidence input anywhere in its path.

The clamp half is **wrong, and round 1 already measured it wrong**: `placement_tier_clamp` at 1.0 → 86.9 % one-sided; at 0.0 → **95.3 %**. D-085's clamp *reduces* orientation-dependence by about 8 pp. Bundling it with the shrink as though both were the bias inverts the sign of a measured effect. Live value: absent from prod `model_config`, falls through to **1.0** (`trade_service.py:750`).

**Remedy — shrink both: SOUND WITH CAVEATS. Near-cosmetic on 1-for-1s, genuinely useful on packages, and expensive.**

| | 1for1 | ALL |
|---|---|---|
| BASE (targeted) | 86.9 % | 91.1 % |
| shrink both (partner shrunk with own counts) | **85.5 %** | **72.6 %** |
| BASE (untargeted, live) | 96.3 % | 96.6 % |
| shrink both (untargeted) | **95.1 %** | **86.6 %** |

−1.2 pp on 1-for-1s, but −18.5 pp on all shapes untargeted. The 1-for-1 result is the honest headline for the reviewer's own framing, and it is nearly nothing.

**Cost, priced honestly — round 1 understated it.** Round 1 correctly noted `LeagueMember` (`trade_service.py:2821-2829`: `user_id`, `username`, `roster`, `elo_ratings`, `has_rankings`) has no confidence field. It is worse than that. The `member_rankings` table (`database.py:398-406`) stores **only `elo`** — there is no comparison-count column — so `load_member_rankings` (`database.py:7522-7542`, which returns `{user_id: {username, elo_ratings}}`) structurally cannot supply counts.

Comparison counts come from `RankingService.comparison_counts()` (`ranking_service.py:1122+`), which is only meaningful after `replay_from_db` (`ranking_service.py:1185+`) has replayed that user's `swipe_decisions` rows. So dualizing the shrink requires **a full swipe replay per ranked league member, per deck generation**. For the six audited members that is 4,249 swipe rows, one of them alone carrying 2,000. This is a hot-path change with real latency cost, not a new dataclass field.

**Remedy — shrink neither: SOUND. The single biggest lever in bucket A.**

| | 1for1 | ALL |
|---|---|---|
| BASE (targeted) | 86.9 % | 91.1 % |
| **shrink neither** | **63.2 %** | **56.4 %** |
| BASE (untargeted, live) | 96.3 % | 96.6 % |
| **shrink neither (untargeted)** | **89.4 %** | **75.7 %** |

−23.7 pp targeted, −6.9 pp untargeted on 1-for-1s, −20.9 pp untargeted on all shapes. Nothing else in bucket A comes close.

**Pick: DELETE, decisively.** Deleting is 20× the effect of twinning on 1-for-1s, is free rather than costing a per-member replay, and needs no new plumbing. The counter-argument is that shrinkage exists for a reason — it damps fake divergence from lightly-sampled players, which is precisely what `user_gain_ok_1for1`'s own docstring (`:1494-1497`) cites as its motivation. Deleting it is a real product decision with a real downside, not a free win; it should go to the operator as a decision, not be shipped as a bug fix. But if the goal stated at the top of this bucket — reduce manufactured partner-overpay — is the goal, this is the row that achieves it.

---

### Row 3 — Filler

> *Today:* `max(you, them)` — giver can bless junk. *Proposed:* gate on the receiver's board only.

**Premise: REFUTED.** This row is built on a false description of the code, and round 1 already rated it refuted as a lever.

`filler_ok` (`trade_service.py:1513-1546`) loops `for side in (give_ids, recv_ids)` at `:1538` and applies **the identical metric to both sides** at `:1541-1542`: `max(user_val(p), opp_val(p))`. There is no giver privilege and no receiver privilege. A piece the *user* thinks is junk survives on the receive side exactly as readily as a piece the partner thinks is junk survives on the give side. The docstring says so in as many words at `:1519-1521`.

**A real defect found while checking this row — but not the one the reviewer describes.** The docstring at `:1526-1527` states "user_val / opp_val are RAW board-value accessors (pid → value), never marginal values", and the v3 callsite comment at `:4666-4667` says the gate runs "on the MAX of the two raw boards". **On the divergence/v3 path this is false.** The accessor passed as `user_val` at `:4669` is `_uv` (`:4521-4522`), which reads `user_value` — and `user_value` is built from `shrunk_elo` at `:4023`, then optionally outlook-blended at `:4033-4035`.

Proven directly: of 200 sampled `user_val(pid)` returns for pids where shrunk ≠ raw (595 of 625 pids on the sampled board), **200 matched the shrunk board and 0 matched the raw board.**

The consensus path is not affected — `:5010` passes `_uval_raw`, a genuinely raw accessor. So the two paths disagree with each other, and one of them contradicts its own documentation. This is a docs/provenance bug worth a separate ticket; it is not what the reviewer claimed, and it is not an asymmetry.

**Remedy — receiver's board only: WOULD NOT WORK.** 86.9 → **87.1 %**; ALL 91.1 → **90.9 %**. Zero, in both directions, as expected: it is a symmetric change to a gate that was already symmetric.

**Remedy — delete: WOULD MAKE IT WORSE, badly.**

| | 1for1 | ALL |
|---|---|---|
| BASE | 86.9 % (53/61) | 91.1 % (133/146) |
| **filler deleted** (`filler_min_frac = 0`) | **100.0 %** (17/17) | **97.5 %** (235/241) |

With the junk-filler bar removed, padded multi-asset packages flood the enumeration (ALL union 146 → 241) and crowd 1-for-1s out of the emitted deck entirely (1-for-1 union 61 → 17), with **zero** surviving two-orientation agreement. This is the worst outcome measured anywhere in bucket A.

**Pick: neither.** Change nothing here. File the `_uv`-provenance bug separately.

---

### Row 4 — Need (R5)

> *Today:* R5 hard-kills lateral receives for your window. *Proposed:* soft dual need — boost if it fills either hole; don't kill a dual-surplus card because it's lateral for you.

**Premise: CONFIRMED**, and round 1 confirmed it independently.

`need_gate_ok` (`trade_service.py:1735-1798`) takes `give_ids, recv_ids, seed_value, players, user_pos_values, outlook, position_needs, position_surplus, scoring_format`. **No opponent argument of any kind.** It judges the single highest-consensus-value received player (`:1764-1772`), and if that player neither fills a starting hole (`:1790-1791`) nor beats the incumbent by `need_gate_upgrade_margin` (`:1792-1793`), it returns `False` for `championship`/`contender` at `:1794-1795`. Live: `trade.presentment_rules: true`, `need_gate_min_value = 500.0`, `need_gate_upgrade_margin = 0.0`.

**New measurement: this gate is the largest single amplifier of orientation-dependence in the engine.**

| | 1for1 | ALL |
|---|---|---|
| need gate bypassed (targeted) | 86.9 % | 91.1 % |
| **need gate live (untargeted — prod default)** | **96.3 %** | **96.6 %** |

Turning R5 on costs **+9.4 pp** of one-sidedness and drops two-orientation agreement from 8 cards to 4.

**Remedy — soft dual need: SOUND. The only bucket-A remedy that is both correctly diagnosed and measurably effective on its own row.**

Implemented as the reviewer specifies: keep the existing gate, but rescue a killed shape when any non-pick asset the *partner* receives fills one of the partner's `position_needs` (from `analyze_roster_strengths` on their roster).

| | 1for1 | ALL |
|---|---|---|
| need gate live | 96.3 % (103/107) | 96.6 % (171/177) |
| **+ dual-need soft rescue** | **88.7 %** (47/53) | **92.4 %** (109/118) |

**−7.6 pp**, and the union nearly halves (107 → 53) — the rescue is not backfilling noise, it is restoring shapes that genuinely exist in both orientations while the enumerator stops thrashing.

This aligns with round 1's finding that across 30 ordered pairs, **61 killed shapes had dual `need_fit ≥ 0.75`**, the clearest being a surplus RB sent to a manager whose stated need is literally `['RB']`. Round 1 established the gate kills real dual-need trades; this round measures what fixing it is worth.

**Pick: implement.** This row is not an either/or, and it should not be turned into one — deleting R5 outright would give back the presentment behaviour it was built for (G6 feedback wave #304). The soft rescue keeps the gate and buys most of the asymmetry back.

---

### Row 5 — Outlook ranking

> *Today:* boosts "you extract the vet". *Proposed:* boost complementary windows (contender ↔ rebuilder), penalize same-window extraction.

**Premise: REFUTED as stated**, exactly as round 1 found.

`outlook_direction_mult` (`trade_service.py:2331-2333`) has signature `(give_ids, recv_ids, players, outlook, value_of)`. **The partner's window is structurally absent.** The body (`:2360-2409`) reads only `outlook`, `players`, and `value_of`; it is a pure function of the card's own shape and the *user's* window. Contender↔contender and contender↔rebuilder therefore receive an identical multiplier — round 1 measured ×1.1325 for both.

The reviewer's stated problem — that it "boosts you extracting the vet **over the complementary deal**" — is mechanically impossible. The function cannot see the complementary deal. It cannot prefer one to the other because it cannot distinguish them.

Their *remedy*, however, addresses a genuine structural gap: the partner's window really is missing from the ranking. **These two things must be kept separate**, and the reviewer's own framing conflates them.

**Remedy — complementary-window boost: WOULD NOT WORK for asymmetry.** Implemented as ×1.25 for complementary windows, ×0.80 for same-window:

| | 1for1 | ALL |
|---|---|---|
| BASE | 86.9 % (53/61, agree 8) | 91.1 % (133/146, agree 13) |
| **complementary-window aware** | **86.9 %** (53/61, agree 8) | **91.1 %** (133/146, agree 13) |

**Byte-identical.** Not approximately — the same union, the same agreement count, the same card sets. As flagged in §1.3, this is expected and is a property of the overlay, not a fluke: `outlook_direction_mult` is a composite *ranking* multiplier, and the mirror metric measures which shapes exist, not what order they appear in. Re-weighting survivors cannot create or destroy a one-sided card.

For calibration, deleting outlook entirely moves 86.9 → **86.2 %** / 91.1 → **91.0 %** — so the overlay has a small existence effect (union 61 → 58, presumably via the age-gap penalty at `:2394-2409` interacting with downstream thresholds), and the reviewer's remedy captures none of it.

**Pick: do it, but do not count it as an asymmetry fix.** Making the ranking partner-aware is defensible on its own merits — it would change which card a user sees *first*, which is a real UX lever. It belongs in a ranking/ordering workstream, not in a bucket titled "these manufacture partner-overpay," because re-ordering a deck manufactures nothing.

---

### Row 6 — `fit_premium`

> *Today:* you may pay 300 for your fit. *Proposed:* partner may pay 300 for their fit, or drop it.

**Premise: CONFIRMED on the numbers, REFUTED on the framing.**

The arithmetic is right. `fit_premium_1for1` (`trade_service.py:2422-2455`) lets a 1-for-1 that fails #108 through when the received position is in `user_needs` and the given position is not (`:2448-2449`), provided the raw-board loss is within `fit_premium_max_loss` (`:2452-2453`). Prod value **300.0** (also the `_DEFAULT_CFG` value at `:440`), flag `trade.fit_premium: true` (`config/features.json:43`).

The framing is backwards. This bucket is introduced as "the ones that currently manufacture partner-overpay." `fit_premium` is the one overlay in the list that lets the **user** pay — it is an escape hatch *from* the user-protective #108 gate, flagged on the card with the price paid (`:2455`, surfaced at `server.py:10721-10723`). Removing it does not remove partner-overpay; it removes user-overpay, and the asymmetry gets worse:

| | 1for1 | ALL |
|---|---|---|
| BASE | 86.9 % (53/61) | 91.1 % (133/146) |
| **`fit_premium` OFF** | **88.5 %** (54/61) | **91.8 %** (134/146) |

**Remedy — partner may pay 300 for their fit: CATEGORY ERROR standalone.** `fit_premium` is defined as an *exception to #108* — its first line is `if user_gain_ok_1for1(...): return True, None` (`:2439-2440`). There is no partner-side #108 to be an exception to. A partner-side `fit_premium` has nothing to attach to and, applied to today's engine, is a no-op by construction.

It becomes coherent only if row 1's dualize lands first — at which point its function is to **repair the damage row 1 does**:

| | 1for1 | ALL |
|---|---|---|
| BASE | 86.9 % | 91.1 % |
| #108 dualized (row 1 alone) | 90.1 % | 93.0 % |
| **#108 dualized + partner `fit_premium`** | **84.9 %** (45/53) | **90.8 %** (128/141) |

A −2.0 pp net move for a coupled two-row change across three modules — and at the resolution limit of this fixture.

**Remedy — drop it: WOULD MAKE IT WORSE** (88.5 %), and it would also remove a user-visible explanation string (`trade_narrative.py:126`) and an API field emitted at four `server.py` callsites.

**Pick: keep it as-is.** Build the partner half only if row 1's dualize is adopted, and row 1's dualize should not be adopted alone.

---

## 4. What actually moves the number

Ordered by measured effect on the live untargeted deck where available, targeted otherwise.

| Rank | Change | Δ 1for1 | Δ ALL | Verdict |
|---|---|---|---|---|
| 1 | **Row 2 — delete the shrink entirely** | 96.3 → **89.4 %** (−6.9) | 96.6 → **75.7 %** (−20.9) | real, and free |
| 2 | **Row 4 — soft dual-need rescue** | 96.3 → **88.7 %** (−7.6) | 96.6 → **92.4 %** (−4.2) | real, and correctly diagnosed |
| — | **Rows 2 + 4 stacked** | 96.3 → **73.3 %** (−23.0) | 96.6 → **60.8 %** (−35.8) | **the whole available win** |
| 3 | Row 1 dualize + Row 6 partner half | 86.9 → 84.9 % (−2.0) | 91.1 → 90.8 % (−0.3) | at resolution limit; coupled; 3 modules |
| 4 | Row 2 — shrink both instead of neither | 96.3 → 95.1 % (−1.2) | 96.6 → 86.6 % (−10.0) | cosmetic on 1-for-1s; costs a per-member swipe replay |
| 5 | Row 5 — delete outlook | 86.9 → 86.2 % (−0.7) | 91.1 → 91.0 % (−0.1) | noise |
| 6 | Row 3 — filler on receiver only | 86.9 → 87.1 % (+0.2) | 91.1 → 90.9 % (−0.2) | zero |
| 7 | Row 5 — complementary-window boost | 86.9 → **86.9 %** (0.0) | 91.1 → **91.1 %** (0.0) | exactly zero, by construction |

**Actively harmful — do not build:**

| Change | Δ 1for1 | Verdict |
|---|---|---|
| Row 3 — delete filler | 86.9 → **100.0 %** (+13.1) | worst outcome measured |
| Row 1 — dualize #108 alone | 86.9 → **90.1 %** (+3.2) | backfill makes it worse |
| Row 6 — drop `fit_premium` | 86.9 → **88.5 %** (+1.6) | removes user protection, not partner-overpay |

### The one-line answer

Of six proposed dualizations, **one should be built as proposed** (row 4's soft dual need), **one should be built as its delete-option rather than its dualize-option** (row 2), **two are built on false premises** (rows 3 and 5), **one is backwards about which side it protects** (row 6), and **one makes the problem worse in both of its offered forms unless coupled to another row** (row 1).

The bucket's organizing thesis — "dualize the overlays and the asymmetry goes away" — does not survive measurement. Twinning is the weaker option nearly everywhere it was offered: on row 2, deleting beats twinning by 20× on 1-for-1s; on row 1, twinning is actively harmful while deleting is merely inert; on row 3, both options are worse than doing nothing. The two changes that work are a **deletion** and a **partner-aware relaxation of a hard kill** — neither of which is a symmetric twin of an existing test.

---

## 5. Follow-ups this audit surfaced (not part of bucket A)

1. **`filler_ok` board-provenance bug.** On the divergence/v3 path the gate judges the user side on the **shrunk** board while its docstring (`trade_service.py:1526-1527`) and callsite comment (`:4666-4667`) both claim raw; the consensus path (`:5010`) genuinely does pass raw. Proven 200/200. Either the code or the docs is wrong, and the two generation paths disagree with each other.
2. **Import-time binding hazard.** `trade_optimizer.py:62-63` and `trade_gen_v2.py:118-121` bind `filler_ok` / `fit_premium_1for1` / `_shrink_user_elo` by value. Any future experiment that wraps these in `trade_service` alone will silently measure nothing. Worth a comment at the definitions.
3. **`fit_premium` has no consensus-path equivalent.** `:5002` calls the bare `user_gain_ok_1for1` with no escape hatch, while `:4657` and `trade_optimizer.py:535` get the flagged exception. Whether that asymmetry between paths is intended is not recorded anywhere I could find.
4. **The prod-default one-sidedness figure is 96.3 %, not 86.9 %.** Any future work quoting round 1's headline should state which path it refers to.
