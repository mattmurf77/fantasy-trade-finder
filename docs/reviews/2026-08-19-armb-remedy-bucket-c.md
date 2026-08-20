# ARMB remediation — Bucket C validation ("keep user-only: deck UX, not acceptance")

**Date:** 2026-08-19
**Auditor:** session agent, branch `audit/armb-remedy-bucket-c`
**Code basis:** `origin/main` @ `50e0451`. The task specified `16d277f`; that commit is an
ancestor and `git diff 16d277f origin/main` touches only `config/features.json`, three flag
fixtures and `living-memory/CHANGELOG.md` — **zero engine lines differ**, so every citation
below is valid on both shas.
**Data basis:** prod Postgres, read-only (`SET TRANSACTION READ ONLY`, SELECT only).
`deck_impressions` 8,630 rows, 2026-07-27 → 2026-08-19T19:09Z, 332 decks, 5 distinct users.
**Scope:** validation only. No `backend/*.py` line, flag, or knob was changed. No D-/G-/M-/Q- id
allocated.

---

## 0. Bottom line

The reviewer's bucket C is **conditioned on a precondition that does not hold for 84.5 % of
served cards**, and three of its five members are not ordering overlays at all.

| # | Overlay | Verdict | One-line mechanism |
|---|---|---|---|
| 1 | `target_acquire_bonus` | **PARTIALLY** — post-gate, but a *selection* key, not an ordering key | Multiplies `composite` (`trade_service.py:4743`, `trade_optimizer.py:500`) which is then truncated `ranked[:max_cards]` at `:4848` with `max_cards = 5` |
| 2 | C4b give-headliner cap | **NOT SAFE AS FILED** — post-gate but it **deletes candidates**, 10.1 % by its own measurement | `cap_give_headliners` (`trade_service.py:1456`, applied `:3251` and `:3462`) drops cards and never backfills |
| 3 | Fatigue | **SPLIT: soft = SAFE AS CLAIMED; hard = REMOVAL, not ordering (currently inert)** | Soft multiplier ≤ 1.0 into the sort key (`server.py:3605-3607`); hard `_apply_deck_suppression` (`server.py:4245`) deletes cards. `deck_suppressions` has **0 rows in prod** |
| 4 | Likes-you "pin" | **NOT SAFE AS CLAIMED — it is not a pin and not post-gate** | `_inject_likes_you_cards_impl` (`server.py:2943`) **synthesises new TradeCards** (`:3070-3095`) that pass none of the acceptance gates. It is a card-creation path |
| 5 | First-session shaping | **PARTIALLY — and it is the one overlay pushing the *right* way** | Truncates to 10 (`server.py:4916-4918`) — removal — but its promotion bar demands consensus fairness ≥ **0.85**, far stricter than the live gate of 0.50 |
| — | `_tier_mult_v2` (gray zone) | **Reviewer's mechanism REFUTED (again); reviewer's conclusion CONFIRMED** | Direction-blind, but it selects for *package scale*, and the only anti-lopsidedness term in the consensus score is scale-free. Measured: elite-band cards carry **10.2×** the absolute viewer surplus of depth/bench cards and sit ~10 places higher in the deck |

---

## 1. The precondition fails — say this first

The reviewer's exact wording is:

> Fine to stay viewer-centric **after the dual gate**.

The dual gate exists on exactly one code path.

* **Divergence (v2):** `trade_service.py:4720` — `if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE: return`. Genuinely two-sided; each side priced on its own board.
* **Divergence (v3 optimizer):** `trade_optimizer.py:560` — identical.
* **Consensus:** `trade_service.py:4987` — `if rv - gv < _c("user_gain_epsilon"): return`, with
  `user_gain_epsilon` = **0.0** live (no `model_config` row; code default `trade_service.py:220`),
  plus a fairness floor at `:5018`. **Both terms are computed on one value map — the consensus
  seed — and both are evaluated from the viewer's side only.** `_generate_consensus_for_pair`
  (`trade_service.py:4874`) does not even receive an opponent Elo map; that is the definition of
  the path. There is no opponent-side surplus test anywhere in it.

Prod mix, `deck_impressions.features_json.basis`, all 8,630 rows:

```
consensus   7293   84.5 %
divergence  1337   15.5 %
```

This reproduces round 1's 84.5 % to the decimal.

Worse, the consensus gate is *structurally* the asymmetry generator, not merely silent about it.
With `ε = 0` the gate is `rv ≥ gv` on a shared value map. Mirror the card and the opponent's
surplus is `gv − rv ≤ 0` — it fails their gate by construction for every card with strictly
positive surplus. Round 1 measured 86.9 % of live 1-for-1s existing in only one orientation; on
the consensus path the analytic figure is ~100 % less exact ties. `fairness_score` bounds only
*how far* the tilt can go (live threshold 0.50 ⇒ the viewer may receive up to 2× what he sends);
it does not make the card two-sided.

**Therefore: for 84.5 % of served cards, "after the dual gate" names a stage that does not exist.
Everything bucket C excuses is downstream of a viewer-only test.** Bucket C's safety argument is
not wrong about the overlays so much as it is attached to a stage that is missing. That is the
single most important sentence in this memo.

---

## 2. Pipeline map — where each stage actually sits

Established by reading, not inference. `origin/main` line numbers.

**Generation, per opponent pair** (`trade_service.py`)
1. Construction filters — untouchables, not-interested, pinned, presentment R1/R2/R3/R5.
2. **ACCEPTANCE GATE.** Divergence `:4720` (dual). Consensus `:4987` + `:5018` (viewer-only).
3. `composite` assembled. `_tier_mult_v2` at `:4736` (divergence) and `:5025` (consensus);
   `target_acquire_bonus` at `:4743`. v3 mirror at `trade_optimizer.py:495` / `:500`.
4. Post-generation composite overlays, all flag-live: partner-fit `:4278`, need-fit `:4295`,
   block-boost `:4311`, outlook-direction `:4335`, aggression A/B `:4403`.
5. **Truncation.** Divergence: bounded top-K heap `K = 4 × max_cards` (`:4613`) then
   `ranked[:max_cards]` (`:4848`), `max_per_opponent` default **5** (`:3114`). Consensus: no
   ranking at all — `_emit` appends until `len(cards) >= max_cards` (`:5040-5060`), so within that
   generator `composite` is a *stamp*, never a selector.
6. `_dedup_and_sort` (`:3388`) — global sort by `composite_score` (`:3413`), then **C4** centerpiece
   cap 2 (`:3432-3446`), then **C4b** give-headliner cap 3 (`:3462-3463`). Both drop cards.

**Serving** (`server.py`, `_run_trade_job`)
7. **Likes-you injection** (`:2943`, invoked ~`:5540`) — adds cards.
8. **F3 hard suppression** `_apply_deck_suppression` (`:4245`) — removes cards.
9. `_order_deck` (`:3500`) — Thompson × fatigue (`:3605`) × taste × diversity penalty, likes-you
   boolean first in the sort key (`:3634-3637`), then `_cap_per_target` (`:3644`, def `:3271`) —
   removes cards.
10. F7 exploration wildcard — adds a card.
11. **F9 first-session shaping** (`:4904`) — truncates to 10 and reorders.
12. Impressions written.

Two structural facts fall out immediately:

* **Nothing in bucket C is pre-gate.** The reviewer is right about that, on every item. Round 1's
  finding stands and I am not contradicting it.
* **"Post-gate" and "ordering" are not the same claim, and bucket C conflates them.** Stages 5, 6,
  8, 9 and 11 all *delete* gate-passing candidates; stage 7 *creates* candidates that never faced
  a gate. A user cannot swipe a card that was deleted. Calling that "which of the already-acceptable
  cards you see first" is false in a way that matters: the honest phrasing is "which of the
  already-acceptable cards *exist for you at all*".

---

## 3. Per-item verdicts

Live values below: `target_acquire_bonus` 0.20 and `pos_multiplier_cap` 2.0 from `model_config`;
`consensus_score_scale` 0.30, `fairness_floor_divergence` 0.55, `deck_max_per_target` 3.0,
`diversity_user_cap` 3.0, `diversity_penalty` 0.6, `likes_you_min_user_delta` −500.0 from
`model_config`. Every other knob cited has **no DB row and rides its code default** — I checked
each one rather than assuming.

### 3.1 `target_acquire_bonus` — **PARTIALLY SAFE**

`composite *= min(1.0 + 0.20·n_targets, 2.0)` (`trade_service.py:4743`, `trade_optimizer.py:500`).
Applied strictly after the mutual-gain gate; the in-code comment ("a target never rescues a
non-mutual-gain trade") is accurate. Its ceiling is a hard 2.0× via `pos_multiplier_cap`.

Where the reviewer is right: it cannot admit a card. Where the label breaks: on the divergence
path the value it feeds is the truncation key. With `max_per_opponent = 5` and a heap of `K = 20`,
a 2× composite bump does not reorder five cards — it decides which five of a few hundred
gate-passing candidates ever leave the generator. That is post-gate *selection*.

Mitigating, and worth stating plainly: it is user-declared intent. The viewer typed the target. Of
the five, this is the one where viewer-centrism is the point rather than an oversight, and the 2.0
cap bounds it. **Verdict: keep it viewer-centric; fix the label, not the code.**

### 3.2 C4b give-headliner cap — **NOT SAFE AS FILED**

`cap_give_headliners` (`trade_service.py:1456`) keys on `deck_give_headliner` (`:1421`) and keeps
at most `deck_give_headliner_cap` cards per give-side headliner. Live value **3.0** (code default
`:715`; confirmed no `model_config` row). Applied at `:3462` on the v1/v3 path and at `:3251` on the
gen-v2 branch; `bakeoff_runner.py:1202` repeats it for arm C. Ships D-082
(`living-memory/DECISIONS.md:925`) — note the commit message `a53b142` says "D-080", which is a
different decision (player-preference decline codes); a stale id in a commit subject, not a code
defect.

**It drops candidates.** Its own scope block
(`docs/plans/deck-give-headliner-cap/scope.md` §0.2) measures 194 / 1,925 = **10.1 %** of served
cards lost at the shipped default, 23.8 % at a cap of 2.

I verified the cap fires as specced, from impressions. Give headliner is exact and seed-map-free
for single-give-asset cards, so I restricted to those, per deck job, decks with ≥8 such cards.
Split at the deploy boundary (a53b142 authored 05:20Z, merged into `ship/four-fixes` at 14:28Z):

```
PRE  2026-08-19T14:30   91 decks   median worst give-headliner repeat 4   max 14
                        dist {2:5, 3:38, 4:8, 5:12, 6:13, 7:2, 8:4, 9:5, 10:2, 11:1, 14:1}
POST 2026-08-19T14:30   14 decks   median 3   max 3   dist {3:14}
```

Every post-deploy deck lands at exactly 3. Clean confirmation; the four post-01:20Z decks that
still showed 6/8/9/14 were served 05:33–06:40Z, i.e. before the merge, not a cap failure.

Observed deck size, all decks: median **29 → 20** across the same boundary (n = 15 post). That is
−31 %, roughly 3× the projected 10.1 %. **Do not read that as the cap's cost**: only 15 post-deploy
decks exist, and three other engine changes landed the same day (D-079 pick decay, D-085 placement
tier clamp, D-086 lane reallocation). It is a flag to re-measure in a week, not a finding.

**Judgement asked for: does a candidate-dropping cap belong on a "deck UX, not acceptance" list?**

No — but the fix is the taxonomy, not the cap. Three reasons, in order of weight:

1. **A deleted card is not a reordered card.** The bucket's stated warrant is "these decide which
   of the mutually-acceptable cards you see first". C4b decides which ones you see *at all*, at a
   measured 10.1 %. Filing it under an ordering warrant means the next reviewer inherits a false
   premise about what the overlay does.
2. **Its author already refused the "harmless" framing.** Leave-short-never-backfill
   (`trade_service.py:1462-1468`) and the deliberate placement upstream of
   `bakeoff_runner.compose_group` exist precisely so the shortfall surfaces in
   `groups_json.short`. Bucket C's label re-buries what that placement was chosen to expose.
3. **But it is not a bias source, and dualising it would be wrong.** The cap counts what the viewer
   is asked to *send*. In the viewer's own deck, the receive side is already capped at 3 by
   `_cap_per_target` (`server.py:3271`, `deck_max_per_target` 3.0, live). So the give and receive
   sides carry the same per-asset cap. A give-side cap is *inherently* about the viewer's
   experience of repetition — there is no counterparty deck for it to be asymmetric against — and
   the `_DECK_MIN_CARDS = 5` floor downstream (`server.py:3124`) bounds the damage.

**Verdict: NOT SAFE AS CLAIMED, on the grounds that it is a filter and the bucket's warrant is
ordering. Keep the knob at 3. Move the row out of bucket C into a "post-gate supply reduction —
measure, don't dualise" line, so its 10.1 % is carried alongside it.**

### 3.3 Fatigue / decline suppression — **SPLIT VERDICT**

Two layers, documented as such at `server.py:4080-4101`, and they belong in different buckets.

**Soft fatigue — SAFE AS CLAIMED.** `_deck_fatigue_multipliers` (`server.py:4183`) produces
`m ≤ 1.0` folded into the sort key at `:3605-3607` via `key[id(c)] *= min(1.0, …)`. The `min(1.0, …)`
clamp is load-bearing: a fatigued card can sink and can never rise, so nothing is rescued. Floored
at `fatigue_floor` 0.25 × `fatigue_session_demotion` 0.2 (code defaults). This is genuinely ordering
and genuinely viewer-personal. The reviewer is right about this layer.

**Hard suppression — REMOVAL, not ordering.** `_apply_deck_suppression` (`server.py:4245`) matches
each card against active windows and `continue`s past it (`:4326-4330`) — the card is deleted from
the deck. `_DECK_MIN_CARDS` restoration at `:4353` bounds starvation but does not make it ordering.

**Is the suppression symmetric in any meaningful sense?** Three separate answers, and they do not
agree:

* **The key is direction-blind, like `_tier_mult_v2`.** `_fatigue_centerpiece` (`server.py:4106`)
  delegates to `trade_service.deck_centerpiece` (`:1406`), which maxes over `give_ids + recv_ids`
  combined. So declining a card centred on player X suppresses every near-duplicate containing X on
  *either* side. Symmetric across sides of one card — but that is not counterparty symmetry, it is
  key-construction symmetry.
* **The state is entirely the viewer's own.** Rows are per `(user_id, league_id)`. Nothing about the
  counterparty's history enters. Viewer-centric, unambiguously.
* **One genuine two-sided write exists, and the reviewer did not know about it.** At
  `server.py:15050-15065`, a decline that kills a proposal the partner had **accepted** writes a
  *second* suppression row for the partner with give/receive mirrored
  (`result.get("user_receive")`, `result.get("user_give")` swapped). That is the only place in the
  whole of bucket C where the engine acts on the counterparty's behalf. Credit where due.

**And it is inert in production.** `deck_suppressions`: **0 rows**. `deck_fatigue_resets`: 0 rows.
The write fires only from the match-decision route, and `trade_matches` holds 14 rows lifetime.
Meanwhile `deck_outcomes` holds 361 passes — swipe passes feed the *soft* layer only and open no
window. So the removal layer has never removed a card in prod.

**Verdict: soft layer SAFE AS CLAIMED. Hard layer NOT SAFE AS CLAIMED — it is removal, not
ordering — but currently zero-impact, so it is a documentation defect today and a latent one if
match volume ever grows.**

### 3.4 Likes-you "pin" — **NOT SAFE AS CLAIMED (mislabelled, but the bias runs the other way)**

The reviewer calls this a pin. It is not. `_inject_likes_you_cards_impl` (`server.py:2943`):

* If a matching card already exists in the deck: set `likes_you = True` and overwrite
  `composite_score` with `max(all) + 1.0` (`:2988`, `:3060-3061`). That part *is* a pin.
* **Otherwise it constructs a brand-new `TradeCard`** (`:3070-3095`), registers it in
  `trade_service._trade_cards`, and returns `sorted(new_cards + cards, …)` (`:3098`). Up to
  `_LIKES_YOU_CAP = 3` per deck (`:2928`).

A synthesised card runs through **no** acceptance gate. Not `user_gain_epsilon`, not the dual
surplus gate, not `fairness_threshold`, not #108 `user_gain_ok_1for1`, not #227 `pick_swap_ok`, not
#141 `filler_ok`. Its `fairness_score` is computed *for display* at `:3067` after the fact. Its only
gate is `likes_you_min_user_delta`, live **−500.0**, which permits the viewer to be 500 value points
down. It then lands at deck position 1–3, and it is exempted from every downstream cap:
`_cap_per_target` skips it (`:3285`), suppression skips it (`:4318-4321`), first-session shaping
locks its slot (`:4924-4928`).

So this row is misfiled twice over. It is not ordering — it is the one path in bucket C that
decides which cards *exist*, and the reviewer put it on the list whose warrant is that nothing here
touches existence.

**But — and this is the honest half — its one-sidedness points the opposite way from the audit's
concern.** The card exists because the *counterparty already liked its mirror*. That is revealed
two-sided consent, stronger evidence than any surplus gate in the codebase. The `−500` floor is the
*viewer's* protection, added by D-055 after the 2026-08-15 Phase A gate found all eight "insulting"
first-deck cards were likes-you injections. The gate bypass is therefore asymmetric in the safe
direction: counterparty consent proven, viewer consent floor-checked.

**Verdict: NOT SAFE AS CLAIMED as filed — it is a gate-bypassing card-creation path, not deck UX.
No change needed on the ARMB axis; it is the least viewer-centric thing in the engine. File it as
"pre-gate by construction, justified by revealed counterparty consent" and stop calling it a pin.**

### 3.5 First-session shaping — **PARTIALLY, and it is anti-fleece**

`_apply_first_session_shaping` (`server.py:4904`), first decks only, live behind `deck.first_session`.

* **Size clamp** `:4916-4918`: `cards[:first_session_deck_max]`, default **10**. Truncation — removal.
  It is the *tail* of an already best-first list, so it removes the least-preferred cards, but it is
  removal.
* **Confidence partition** `:4923-4951`: promotes cards passing `_first_session_confidence_ok`
  (`:4867`) into the first `first_session_top_k` = 5 unlocked slots. Pure reordering, stable, and it
  respects locked slots (wildcard / likes-you / retest).

The promotion bar is the interesting part. `:4899`: a **consensus-basis** card is promoted only if
`fairness_score ≥ first_session_min_fairness` = **0.85**. On the consensus path
`fairness = gv/rv`, so 0.85 caps the viewer's tilt at ~17.6 % — against a live serving gate of
**0.50**, which permits 100 %. Shape is also capped at ≤2 per side / ≤3 total (`:4886-4887`) and the
top asset must be seeded ≥1250 (`:4892`).

So the *only* overlay in bucket C that applies a stricter fairness bar than the gate is this one,
and it applies it exactly where it matters most — a new user's first five cards.

**Verdict: PARTIALLY — the clamp is removal, so the bucket's warrant is again imprecise; but the
substance is fine and the direction is correct. Leave it alone. If anything, `0.85` is the number
the rest of the deck should be arguing about.**

---

## 4. The gray zone — `_tier_mult_v2`

### 4.1 Their mechanism is wrong. Again. Here is the line.

```
trade_service.py:4736   composite *= self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
trade_service.py:5025   composite = (fairness * self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
                                     * _c("consensus_score_scale"))
trade_optimizer.py:495  comp *= _tier_mult(shrunk_user_elo, all_ids)
```

`give_ids + recv_ids` is list concatenation, and `_tier_mult_v2` (`:3940-3953`) takes a `max` over
the concatenation. **It is direction-blind.** "Ranking by the biggest name on your board" is
half-right and the half that is wrong is the half their remedy is built on. Round 1 rated this
REFUTED as a one-sided lever; that stands.

### 4.2 Their conclusion — "how fleeces float" — is nonetheless correct

Direction-blind is not harmless, for a reason neither round has stated yet.

**The analytic argument.** Live band values (code defaults `trade_service.py:131-135`; no DB rows):
elite 1.60, starter 1.25, solid 1.00, depth 0.55, bench 0.35. On the consensus path — 84.5 % of
served cards — the whole score is

```
composite = fairness × tier_mult × 0.30
```

and the gate guarantees `rv ≥ gv`, so `fairness = gv/rv` and **`1 − fairness` *is* the viewer's
consensus surplus fraction**. `fairness` is therefore the sole anti-lopsidedness term in the score.

Compare dynamic ranges. `fairness ∈ [0.50, 1.00]` — a 2.0× span, hard-bounded by the live gate.
`tier_mult ∈ [0.35, 1.60]` — a **4.57×** span. The star term has more than twice the authority of
the only term that penalises taking more than you give. Concretely: an elite-containing card
outranks a *perfectly balanced* solid-tier card whenever its fairness ≥ 1/1.6 = **0.625** — that is,
while the viewer is taking up to **60 % more consensus value than he sends**. Against a
perfectly balanced depth-tier card the elite card wins at any fairness ≥ 0.34, i.e. at *any* tilt
the gate permits.

**Direction-blindness compounds rather than cancels.** Because the max runs over both sides, the
star boost applies whether the viewer is acquiring the star or shipping him. But the *gate* keeps
the surplus pointed one way regardless. So the boost has two surfaces — "buy the star cheap" and
"sell the star for an overpay" — and both are viewer-favourable by construction. Symmetry in the
multiplier does not buy symmetry in the outcome when the gate underneath is asymmetric.

**The measured argument.** On consensus cards, `base_score` is exactly `composite_score`
(`server.py:3796`), so `tier_mult = base_score / (fairness_score × 0.30)` recovers the live band
algebraically wherever the post-generation overlays (need-fit, block-boost, outlook-direction,
aggression) happened to net to unity. 2,401 of 7,293 consensus impressions snap to a band within
5 %; the rest carry an overlay product I cannot invert from stored features. That subsample is
selected on overlay-neutrality, not on fairness or value, so it is usable for band comparison:

| recovered band | n | mean card_index | mean fairness | **mean absolute viewer surplus (rv − gv)** | median |
|---|---:|---:|---:|---:|---:|
| elite | 911 | **10.05** | 0.850 | **790** | 700 |
| starter | 558 | 12.57 | 0.889 | 203 | 104 |
| solid | 262 | 18.20 | 0.871 | 230 | 204 |
| depth | 331 | 20.88 | 0.808 | 116 | 114 |
| bench | 339 | 19.00 | 0.877 | 41 | 35 |

Elite-band cards carry **10.2×** the absolute viewer surplus of depth+bench cards (790 vs 78) and
sit roughly **10 positions higher** in the deck.

Now the part that makes the mechanism precise. Across *all* 7,293 consensus impressions, by served
position:

| card_index | n | mean fairness | mean tilt % | **mean abs. viewer surplus** | mean max(gv,rv) |
|---|---:|---:|---:|---:|---:|
| 0–2 | 761 | 0.866 | 17.9 | **496** | 4,584 |
| 3–5 | 730 | 0.838 | 22.1 | 473 | 3,052 |
| 6–9 | 948 | 0.854 | 19.0 | 522 | 3,585 |
| 10–14 | 1,227 | 0.848 | 20.4 | 496 | 3,016 |
| 15–24 | 2,435 | 0.846 | 20.5 | 345 | 1,900 |
| 25+ | 1,192 | 0.844 | 20.6 | 172 | 877 |

**Relative tilt is flat.** The top of the deck is not proportionally more lopsided than the tail —
if anything marginally less. **Package scale is not flat: 4,584 at the top vs 877 at the tail, 5.2×.**
Absolute viewer surplus, top-3 vs index ≥ 15: **496 vs 288, 1.72×** on the mean and roughly 3× on
the median (352 vs ~118).

That is the finding:

> `_tier_mult_v2` does not make the top of the deck *more lopsided*. It makes it lopsided **at
> several times the stakes.** `fairness` is a ratio and therefore scale-free — it cannot tell a
> 20 % tilt on an 880-point package from a 20 % tilt on a 4,600-point package. `tier_mult` is
> precisely the term that selects for scale. So the score's only brake is blind to exactly the
> dimension its partner term amplifies.

A 20 % tilt on a bench-tier swap is noise. A 20 % tilt on an elite package is the trade the
counterparty declines and remembers. **The reviewer's phrase "how fleeces float" is right. Their
stated mechanism is wrong and the correct one is worse, because it is invisible to the term
everyone assumes is guarding it.**

Two contextual notes, both outside bucket C but load-bearing for anyone reading this row:

* The **aggression A/B** overlay (`trade_service.py:4403`) applies `mult = 1.0 + w_ab × tilt` on the
  `light` variant, where `tilt = (rv−gv)/max(gv,rv) ≥ 0` on every consensus card. Every sampled
  impression carries `aggression_variant: "light"`. That is an *explicit*, unhidden boost to viewer
  surplus sitting in the same product as `tier_mult`. It belongs to a sibling bucket; flagging it
  here only so the two are not assessed independently.
* On the divergence path the position/surplus relation **inverts** (top-3 mean abs surplus 225,
  index ≥ 25 mean 1,628), because there the composite carries a real mismatch term and a
  `rank_fairness` term. The problem is a consensus-path problem.

### 4.3 Is `min(your_tier_mult, their_tier_mult)` even well-defined?

**No, not on the path that matters.**

* **Divergence (15.5 %): well-defined.** `opp_elo = opponent.elo_ratings` is in scope at
  `trade_service.py:4462` and `trade_optimizer.py:251`, and `_tier_mult_v2` already takes its
  Elo map as a parameter — `self._tier_mult_v2(opp_elo, give_ids + recv_ids)` compiles today.
* **Consensus (84.5 %): undefined.** `_generate_consensus_for_pair` (`trade_service.py:4874`)
  receives `seed_value` and `shrunk_user_elo` and **no opponent Elo map at all**. That is not an
  oversight — the consensus path *is* the path taken when the opponent has no board. There is no
  "their tier map" to take a min against. The only available substitute is the consensus seed, which
  is the same public data `fairness` is already computed from, so `min(yours, consensus)` adds
  nothing the score does not already have.

And on the 15.5 % where it *is* definable, it is actively counterproductive. The bands are absolute
Elo cutoffs (1700 / 1580 / 1460 / 1350). Two boards will usually agree on who is elite; `min()`
bites exactly where they *disagree* — which is the divergence the divergence path exists to find.
Dualising `tier_mult` there systematically suppresses the highest-divergence cards, i.e. it damps
the engine's actual signal to fix a problem that lives on the other path.

**Verdict on the remedy: `min(your_tier_mult, their_tier_mult)` is undefined for 84.5 % of served
cards and harmful on the remaining 15.5 %. Reject it as written.**

The reviewer's *alternative* — "or drop it" — is the closer call, and I am not recommending a
change here (this is a validation memo), but the honest framing for whoever takes it: the defect is
that `composite = fairness × tier_mult` pairs a **scale-free** brake with a **scale-selecting**
accelerator. Anything that fixes that — an absolute-surplus term the ratio cannot hide, or dropping
`tier_mult` from the *consensus* composite only (where it is the sole non-fairness term) — attacks
the real mechanism. Dualising the multiplier does not.

---

## 5. What bucket C's safety claim reduces to

Stripped of the parts that do not survive:

1. **The bucket's warrant is void for 84.5 % of traffic.** "Fine to stay viewer-centric after the
   dual gate" is conditioned on a dual gate that exists only on the divergence path. On the
   consensus path the gate is `rv ≥ gv` at ε = 0 on a single value map, evaluated from one side —
   which is not a weak dual gate, it is the mechanism that *produces* the one-orientation
   asymmetry round 1 measured. Every bucket C overlay therefore operates downstream of a
   viewer-only test, not downstream of a mutual one.
2. **Three of the five are not ordering.** C4b deletes 10.1 % of candidates. Hard fatigue deletes
   (currently zero, latently unbounded). Likes-you *creates* cards that face no gate. Only soft
   fatigue is purely ordering, and first-session is half clamp / half reorder.
3. **What genuinely survives:** *none of these five overlays admits a card that the gate rejected,
   and none of them is a bias source in its own right.* On that narrower claim the reviewer is
   correct on all five, and it is worth stating as plainly as the criticisms — the round-1
   instruction not to manufacture bias where there is none applies here. `placement_tier_clamp`
   reducing asymmetry (86.9 % at 1.0 vs 95.3 % at 0.0) is the standing example of why that
   discipline matters.
4. **But "does not admit a bad card" is not "harmless".** Four of the five change which
   gate-passing cards a user can reach; the fifth reaches around the gate entirely. And the row the
   reviewer themselves flagged as gray — `_tier_mult_v2` — turns out to be the one that decides
   *at what stakes* the consensus path's structural one-sidedness gets served.

**So bucket C reduces to: "these five overlays are not where the bias is created."** That is true,
and useful. It is not the same statement as "these are fine to leave alone", and it cannot be,
because the sentence it is conditioned on — *after the dual gate* — describes 15.5 % of what the
app serves.

---

## 6. Confounds and limits

* **Phantom picks (D-091).** 12.8 % of historical served cards carried phantom draft picks, fixed
  today, and passed at ~2× their like rate. Every figure in this memo is **compositional** —
  fairness, package value, surplus, card position, headliner repeats. **No acceptance-rate or
  like-rate inference is drawn anywhere**, deliberately.
* **Tier-band recovery covers 2,401 of 7,293 consensus impressions** (33 %). The residual carries a
  non-invertible product of need-fit / block-boost / outlook-direction / aggression multipliers.
  The subsample is selected on overlay-neutrality, which is not obviously correlated with fairness
  or package scale, but it is not a random sample and the band table should be read as indicative.
  The all-rows position table (7,293 rows, no recovery needed) is the load-bearing evidence and it
  tells the same story.
* **Post-C4b window is 15 decks over ~5 hours**, sharing the day with D-079, D-085 and D-086. The
  repeat-cap confirmation is robust (it is a hard invariant: every deck at exactly 3). The −31 %
  deck-size observation is **not** attributable to C4b and should be re-measured.
* **5 distinct users** in `deck_impressions` lifetime. Everything here is TestFlight-scale.
* `bakeoff_serve_interleaved` = **0.0** (code default `trade_service.py:508`), so the bake-off runs
  dark and the presentation stack described above is live for every served deck. Had it been 1, the
  ordering layer, fatigue multipliers and first-session shaping would all be bypassed and half this
  memo would describe dead code.
* `deck.value_model` is **off**, so the F6 base-key swap (`server.py:3558-3563`) is not in play.
  `trade_gen.v2` is **off**, so the `:3251` cap site is unreached in prod.

---

## 7. Citation index

| Claim | Location |
|---|---|
| Dual surplus gate (divergence v2 / v3) | `backend/trade_service.py:4720`, `backend/trade_optimizer.py:560` |
| Consensus viewer-only gate + fairness | `backend/trade_service.py:4987`, `:5018` |
| Consensus generator takes no opponent Elo | `backend/trade_service.py:4874-4897` |
| `_tier_mult_v2` definition / direction-blind `max` | `backend/trade_service.py:3940-3953` |
| `_tier_mult_v2` applied — divergence / consensus / v3 | `:4736`, `:5025`, `backend/trade_optimizer.py:495` |
| Tier band values 1.60 / 1.25 / 1.00 / 0.55 / 0.35 | `backend/trade_service.py:131-135` |
| `target_acquire_bonus` applied | `backend/trade_service.py:4743`, `backend/trade_optimizer.py:500` |
| Per-opponent truncation (heap K, `ranked[:max_cards]`, default 5) | `:4613`, `:4848`, `:3114` |
| Consensus emit-until-full (composite is a stamp, not a selector) | `:5046-5060` |
| `_dedup_and_sort`, sort, C4, C4b | `:3388`, `:3413`, `:3432-3446`, `:3462-3463` |
| `deck_give_headliner` / `cap_give_headliners` | `:1421`, `:1456` |
| `deck_centerpiece` (shared key, give+recv max) | `:1406` |
| C4b measured cost 10.1 % | `docs/plans/deck-give-headliner-cap/scope.md` §0.2 |
| Likes-you injection + synthesis + D-055 floor | `backend/server.py:2943`, `:3070-3095`, `:3055`, `:2928` |
| Soft fatigue multiplier fold (`min(1.0, …)`) | `backend/server.py:3605-3607` |
| Hard suppression removal / floor | `backend/server.py:4245`, `:4326-4330`, `:4353` |
| Mirrored partner suppression write | `backend/server.py:15050-15065` |
| `_order_deck`, likes-you sort key, `_cap_per_target` | `backend/server.py:3500`, `:3634-3637`, `:3644`, `:3271` |
| First-session clamp / top-k / fairness bar 0.85 | `backend/server.py:4916-4918`, `:4923`, `:4899` |
| `_DECK_MIN_CARDS = 5` | `backend/server.py:3124` |
| D-082 (give-headliner cap) | `living-memory/DECISIONS.md:925` |
