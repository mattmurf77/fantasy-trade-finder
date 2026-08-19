# Arm-B audit — Claim 7: "Ranking and copy push the leftover cards toward the user"

**Date:** 2026-08-19
**Audited tree:** `origin/main` @ `16d277f` (`16d277f5c12a8d1c36b36534b74ac1cabe0df0a3`)
**Scope:** validation only. No engine code, flag, or knob was changed by this audit.
**Empirical source:** prod Postgres, read-only (`SET TRANSACTION READ ONLY`, SELECT only), `deck_impressions` — 8,617 served cards, 5 distinct users, 2026-07-27 → 2026-08-19.

---

## Verdict

**PARTIALLY CONFIRMED**, with the two halves of the claim landing very differently.

- **The structural half is right, and understated.** The engine really does have a one-sided user-gain construction rule, and it governs **84.5% of served cards**, not the minority the reviewer implies. On consensus-basis cards the *only* value test is that the user does not come out behind — and **95.3% of served cards where the direction is measurable hand the user more consensus value than they give** (mean +394 consensus points). This survives the D-091 confound (94.1% outside the contaminated window).
- **The reviewer's own framing of that half is wrong.** The table is headed *"Live, after the dual-surplus gate"*. There **is no dual-surplus gate on the consensus path at all** — `_generate_consensus_for_pair` never computes an opponent surplus. The reviewer's premise is factually incorrect in a direction that makes their conclusion *stronger*, not weaker.
- **Three of the six table rows do not survive contact with the code as one-sided levers** (`_tier_mult_v2`, filler `max(user, opp)`, sweeteners). They are real mechanisms, accurately described in isolation, but each is direction-blind or symmetric, so none of them "pushes cards toward the user."
- **The copy allegation — the part the brief calls the most serious — is REFUTED as stated.** `trade_narrative.build_narrative` is computed on every card and serialized to the wire, but **no shipping client renders it.** The `"fits their timeline"` string, and the `"balanced"` / `"uneven on paper"` labels, are dead copy. No user has ever seen them.
- **But a live, user-visible copy defect of the same shape does exist**, on a surface the reviewer did not look at, and it is worse: `TradeCard.tsx:453` prints *"this is a balanced trade by consensus value"* unconditionally on every consensus card, and **11.1% of consensus cards sit below the app's own "league-normal" fairness bar (0.75)** while carrying that sentence. That is the finding the reviewer was reaching for and missed.
- **The synthesis argument is directionally right but mechanically wrong.** `outlook_direction_mult` cannot "boost contender↔contender over contender↔rebuilder", because the partner's window is not an argument to the function. It applies the *identical* multiplier to both pairings. The defect is blindness to the partner, not a preference for the wrong partner.

Every asserted flag state in the reviewer's table is correct, and every asserted weight matches both `_DEFAULT_CFG` and the live prod `model_config`. No row collapses on a wrong flag.

---

## 1. Live flag and knob values — reviewer's assertions vs. reality

Flags read from `config/features.json` on `16d277f`. Knobs read from `backend/trade_service._DEFAULT_CFG`, `backend/database.py` `DEFAULT_MODEL_CONFIG`, **and** the live prod `model_config` table.

| Reviewer asserted | Actual `config/features.json` / knob | Prod `model_config` | Verdict |
|---|---|---|---|
| `trade.outlook_direction: true` | `true` (`config/features.json:60`; `feature_flags.py:454`) | n/a (flag, not knob) | **correct** |
| `trade.aggression_ab: true` | `true` (`config/features.json:44`; `feature_flags.py:111`) | n/a | **correct** |
| aggression weight `0.20` | `aggression_weight = 0.20` (`trade_service.py:443`; `database.py:2316`) | `0.2` | **correct** |
| `trade.preference_lists: true` | `true` (`config/features.json:39`; `feature_flags.py:103`) | n/a | **correct** |
| `target_acquire_bonus 0.20` | `0.20` (`trade_service.py:103`; `database.py:2285`) | `0.2` | **correct** |
| `sweetener_max_cards = 2` | `2.0` (`trade_service.py:392`; `database.py:2270`) | `2.0` | **correct** |
| `trade.outlook_blend` is false | `false` (`config/features.json:29`; `feature_flags.py:88`) | n/a | **correct** |
| `_tier_mult_v2` "always" | no flag; kill switch is the `tier_mult_*` knobs | not overridden → defaults | **correct** |
| filler `max(user, opp)` "always" | no flag; kill switch is `filler_min_frac <= 0`, live `0.25` | `0.25` | **correct** |

Supporting knobs that matter to the argument, all at default in prod:
`pos_multiplier_cap 2.0`, `sweetener_band 0.15`, `asset_floor_abs 450.0`, `fairness_floor_divergence 0.55`, `min_side_surplus_marginal 60.0`, `consensus_score_scale 0.3`, `need_fit_weight 0.15`, `fit_consensus_weight 0.5`, `fit_divergence_weight 0.15`, `outlook_dir_penalty 3.0`, `outlook_dir_boost 1.0`, `outlook_dir_contend_weight 0.5`, `outlook_dir_age_tolerance 1.0`, `outlook_dir_age_gap_mult 0.15`, `outlook_dir_rescue_frac 0.5`.
`user_gain_epsilon` is **not** present in prod `model_config` and therefore runs at its `_DEFAULT_CFG` value of **0.0** (`trade_service.py:220`).

Two contextual flags the reviewer did not state but which decide which code actually runs: `trade_engine.v2: true` and `trade_engine.v3: true` (`config/features.json:27,34`). v3 is the live divergence generator (`trade_service.py:4194-4202` → `trade_optimizer.generate_pair_trades_v3`); `_generate_for_pair_v2` is the fallback. Both were checked; the six levers behave identically in each.

---

## 2. Row-by-row verdicts

The load-bearing question per the brief is not "does it exist" but **"is it genuinely one-sided, or is there a partner-side equivalent the reviewer missed?"**

### Row 1 — Outlook direction · **CONFIRMED as one-sided**

`outlook_direction_mult` (`trade_service.py:2331-2409`), applied at `trade_service.py:4328-4335`.

It takes exactly five arguments: `(give_ids, recv_ids, players, outlook, value_of)`. `outlook` is **the user's resolved window only** — `trade_service.py:4330-4333` passes the loop-level `outlook`, which is the user's. The partner's window is never an argument. There is no partner-side equivalent anywhere: the only other window-aware code paths are (a) `alpha_opp`, which is `None` because `trade.outlook_blend` is false (`trade_service.py:4090`, `4147-4148`), and (b) `_opponent_frame` in the narrative, which is copy and unrendered (§3).

The reviewer's gloss "boosts *you get the vet / they send the vet*" is accurate for contend-side users only. On rebuild-side users the sign flips and the lever boosts "you get the youth". The one-sidedness is real; the phrasing is contender-specific.

### Row 2 — Aggression "light" · **CONFIRMED, and understated in prod**

`aggression_variant` (`trade_service.py:2413-2418`) is `MD5(user_id) % 3 → ("light","fair","generous")`. Applied at `trade_service.py:4361-4396`:

```
tilt = (rv - gv) / max(gv, rv)          # rv, gv on CONSENSUS values (_vs)
light:    mult = 1.0 + w_ab * tilt
generous: mult = 1.0 - w_ab * tilt
fair:     mult = 1.0 - w_ab * abs(tilt)
```

Every detail the reviewer asserts is exact: `1 + w × tilt`, `tilt > 0` = consensus favors the user, weight 0.20, one-third of users **by design**.

**A partner-side equivalent exists and is exact**: `generous` is the perfect mirror of `light`. The reviewer honestly flags this by writing "⅓ of users".

**But the live population is not one-third.** Prod, per distinct user: **light 3, fair 1, generous 1**. Per served card: **light 7,131 (82.8%)**, generous 1,174 (13.6%), fair 124 (1.4%), missing 188 (2.2%). With n=5 users this says nothing about the MD5 hash being biased — it is a small-sample accident — but it does mean that in the deck data anyone would tune on, the "light" tilt is not a third of the corpus, it is nearly all of it. This **strengthens** the reviewer.

One correction to the mechanism: since 2026-07 the bucket can be overridden by a running `trade.aggression` experiment (`trade_service.py:4364-4386`), including `aggression_weight` via a variant `model_overlay`. Prod `model_config` shows 0.2, so nothing is overriding today.

### Row 3 — `_tier_mult_v2` · **REFUTED as a one-sided lever**

`trade_service.py:3940-3953`; the v3 replica is `trade_optimizer.py:82`. Applied at `trade_service.py:4736` and `trade_optimizer.py:495` as `_tier_mult(shrunk_user_elo, give_ids + recv_ids)`, and on the consensus path at `trade_service.py:5025-5026`.

The multiplier is **`max` over the union of both sides**. A card containing an elite player scores ×1.60 whether that player is being acquired or sent. It is completely direction-blind, so it cannot "push a card toward the user" in any sense.

The reviewer's literal description — "biggest name on your shrunk board" — is *factually correct* (it reads `shrunk_user_elo`, the user's board pulled toward consensus, not the opponent's). But whose board supplies the tier is a different property from which side of the trade benefits, and only the latter is what Claim 7 needs. **Real mechanism, wrong column.**

### Row 4 — `target_acquire_bonus 0.20` · **CONFIRMED as one-sided**

`trade_service.py:4737-4742` and `trade_optimizer.py:496-500`:
`n_t = len(set(recv_ids) & _targets)` → `comp *= min(1.0 + 0.20 * n_t, 2.0)`.

Receive side only; `target_ids` are the user's own acquire targets. There is **no give-side or partner-side counterpart** — I checked every adjacent preference mechanism:
- `partner_fit` (FB-47, `trade_service.py:4269-4277`) scores how well the *opponent's roster* fits *the user's* targets — still user-centric.
- `need_fit` (FB-96, `trade_service.py:4285-4297`) **is** genuinely two-sided (it rewards giving from the user's surplus into the opponent's need *and* receiving at the user's need), weight 0.15. This is the closest thing to a partner-side equivalent and the reviewer did not mention it — but it is positional need, not asset preference, so it does not offset the target bonus.
- `block_boost` (FB-147, `trade_service.py:4299-4310`) uses a genuine *partner* signal (players that counterparty flagged on the block) but still boosts the **user's acquire side**.

The bonus is post-gate and reorders only; it never rescues a gated combo. Correctly stated by the reviewer.

### Row 5 — Filler `max(user, opp)` · **REFUTED as a one-sided lever**

`filler_ok` (`trade_service.py:1513-1546`), called at `trade_service.py:4669` (v2), `trade_optimizer.py:547` (v3), `trade_service.py:5010` (consensus).

```python
vals = sorted((max(user_val(p), opp_val(p)) for p in side), reverse=True)
```

`for side in (give_ids, recv_ids)` — the **same** metric on **both** sides. The reviewer's sentence "giver's board can bless a piece the receiver treats as junk" is a true description of `max()`, but the identical statement holds with the sides swapped: a piece the *user* thinks is junk survives on the *receive* side because the opponent's board values it. It is symmetric by construction.

It is also a **gate**, not a ranking term. Loosening a gate admits more candidates on both sides of the ledger; it does not tilt the deck. Nothing about this row supports Claim 7.

(One genuine asymmetry the reviewer did not find: on the consensus path the "opp" arm of the `max` is *consensus itself* (`_uval_raw`, `trade_service.py:4915-4921`), because an unranked opponent has no board. That makes the gate `max(user raw, consensus)` on both sides — still symmetric between sides, so it still does not help the claim.)

### Row 6 — Sweeteners · **REFUTED as a one-sided lever**

`_try_sweeten` (`trade_optimizer.py:677-737`), driven from `trade_optimizer.py:633-673`.

Side selection is `trade_optimizer.py:698-703`:
```python
gv, rv = _consensus_packages(give_ids, recv_ids, seed_value)
if gv < rv: side, roster = "give", user_roster
else:       side, roster = "receive", opp_roster
```

The reviewer's parenthetical is literally correct: the side is chosen on **consensus package value alone**, with no reference to either party's personal surplus. But the consequence runs the *opposite* way to Claim 7:

- If the **user's give side** is consensus-light, the sweetener is a player *the user adds*. The user pays more.
- The sweetened combo must then reach `ratio >= fairness_threshold` (`trade_optimizer.py:727-728`) and re-clear **both** surpluses (`:733-735`), plus `filler_ok`, `presentment_ok`, `pick_swap_ok`, and lineup feasibility.

Net: sweeteners move a near-miss **toward** consensus parity and are re-gated on both sides afterward. They are corrective, symmetric, capped at 2 per pair, and only fire when the pair is short of `max_cards` (`trade_optimizer.py:634`). They are also v3-only, i.e. reachable on the 15.5% of served cards with `basis: divergence`.

---

## 3. The copy layer

### (a) Does `trade_narrative.py` stamp `fairness_score` from consensus? · **CONFIRMED**

`build_narrative` reads `card.fairness_score` at `trade_narrative.py:148` and `:153`. On the consensus path `fairness_score` is `min(gv, rv) / max(gv, rv)` on consensus package values (`trade_service.py:5017`, stamped `:5036`). On v3 it is `_fairness_v3(..., _sv, ...)` — `_sv` is the consensus seed map (`trade_optimizer.py:306-312`). Consensus in both cases. Correct.

### (b) The stated thresholds and wording · **CONFIRMED verbatim**

`trade_narrative.py:53-60`:
```python
def _fairness_label(score: float) -> str:
    if score >= 0.95: return "perfectly balanced"
    if score >= 0.85: return "balanced"
    if score >= 0.70: return "slight tilt"
    return "uneven on paper"
```
0.85 → `"balanced"` (a 15% package gap); 0.56 → `"uneven on paper"`. Both exactly as asserted.

### (c) "Outlook copy claims 'fits their timeline' while `trade.outlook_blend` is false" · **REFUTED as stated**

The three sub-parts:

**The string exists, verbatim.** `trade_narrative.py:96-99`:
```python
if outlook in ("rebuilder", "jets") and lean <= -0.05:
    return "They're rebuilding — the youth going back fits their timeline."
if outlook in ("contender", "championship") and lean >= 0.05:
    return "They're pushing to win now — your proven pieces fit their window."
```

**`trade.outlook_blend` is indeed false, and the code says so in plain English.** `trade_service.py:4083-4091`:

> "The label (declared league preference → inferred from roster shape → not_sure) is resolved whenever the infer flag is on and feeds match_context / narrative framing / lanes — 'their team story'. The VALUE blend (alpha_opp) additionally requires trade.outlook_blend, which the 2026-07-17 interview turned off ('age = tiebreak'): **labels stay, value edits don't**."

So the reviewer's diagnosis is not a discovery — it is the recorded design, self-documented at the site. `alpha_opp` stays `None` (`trade_service.py:4146-4147`), so `_vo` returns the opponent's raw board untouched (`trade_service.py:4499-4514`, `trade_optimizer.py:292-305`).

**But the string never reaches a user.** This is decisive:

- `build_narrative` is called at `trade_service.py:3351` and `:4407`.
- It is serialized at `server.py:10756-10758` (`out["narrative"] = narrative`).
- Every reference to `narrative` in `mobile/`, `web/`, and `extension/` is a **comment or an unrelated feature**: `mobile/src/components/TradeCard.tsx:423` is a comment about the PAYS FOR FIT badge; `web/index.html:813` is the league activity feed ("narrative events"), a different thing. `git grep -rln narrative -- mobile extension web qa` returns three files, none of which render the field.

The `_fairness_label` buckets in (b) are dead for the same reason — they only appear inside `build_narrative`. What the shipping mobile deck actually renders for fairness is `TradeValueBar` plus a match-strength meter; the four-bucket vocabulary the reviewer quotes has no render path. (The `fairnessBand` helper in `mobile/src/utils/tradePresentation.ts:170-186`, which uses a *single* 0.75 threshold and the strings "Within/Outside league-normal range", is behind `trades.presentation_v2`, which is **`false`** in `config/features.json:214`.)

**Verdict on (c): REFUTED.** The allegation that "the product tells the user something untrue about the counterparty" fails at the last mile — the product does not tell the user this at all. The reviewer read the backend and assumed the wire field was rendered.

Two things worth keeping even though the headline is refuted:
1. The sentence is **not fabricated even in principle**. It is gated on a resolved outlook plus the actual now-lean of the give side (`trade_narrative.py:95-99`). What is fair to say is that the outlook may be *inferred* from roster shape (`infer_team_outlook`, `trade_service.py:2457-2523`) rather than declared, and the copy states it flatly with no hedge, even though `match_ctx` carries `{"value": resolved, "source": source}` (`trade_service.py:4148`) and could hedge. If this copy is ever switched on, that is a real defect.
2. **`trades.presentation_v2` contains a worse version of exactly this allegation, also dark.** `counterpartyStatement` (`mobile/src/utils/tradePresentation.ts:260-266`) returns, with *no* gating on any signal:
   > `Based on their roster needs and recent activity, ${who} is likely to be interested in this deal.`

   That is an unconditional claim about the counterparty, unlike the narrative's gated one. It is currently unreachable (flag false), but it is queued to ship.

### (d) The live copy defect the reviewer missed · **new finding**

The shipping deck card does print an unconditional fairness verdict, on the surface the reviewer did not check. `mobile/src/components/TradeCard.tsx:449-456` (string at `:453`):

```jsx
{isConsensus && (
  <Text style={type.label}>Fair-value idea</Text>
  <Text style={type.bodySm}>
    This league-mate hasn't ranked players yet — this is a balanced trade by consensus value.
  </Text>
)}
```

`isConsensus = data.basis === 'consensus'` (`TradeCard.tsx:165`) — **no fairness threshold at all**. The identical string is in `web/js/app.js:3600`.

Against prod:
- Consensus cards are **7,282 of 8,617 served cards (84.5%)**.
- **805 of them (11.1%)** carry a `fairness_score` below the app's own league-normal bar of 0.75.
- **656 of them (9.0%)** fall in the range the (unrendered) narrative would have called *"uneven on paper"* — i.e. below 0.70.
- Mean consensus-card fairness is 0.846, and by construction of `user_gain_epsilon` the gap always favors the user.

So the app tells the user a trade is "balanced" on roughly one in nine consensus cards where it is not balanced by the app's own definition — and the imbalance is always in the user's favor. **This is the substantive version of Claim 7's copy allegation, and it is live.**

---

## 4. The consensus one-sidedness — the strongest part of the claim

The reviewer writes: *"On consensus (the unranked-partner path), the only legal cards are 'you get ahead.' The partner is being asked to overpay by construction."*

**CONFIRMED, and the reviewer undersold it.**

`_generate_consensus_for_pair._emit` (`trade_service.py:4964-5045`; the enclosing function opens at `:4874`) gates, in order: pinned-set, dedupe, `gv/rv > 0`, then

```python
# trade_service.py:4986-4987
if rv - gv < _c("user_gain_epsilon"):
    return
```

with `user_gain_epsilon = 0.0` — so the rule is `rv >= gv`: **the user may never come out behind on consensus value.** Then `consolidation_raw_loss_frac`, `user_gain_ok_1for1` (again user-board only), `pick_swap_ok`, `filler_ok`, presentment rules, and `fairness >= fairness_threshold`.

**There is no opponent-side gate of any kind in this function.** No `opp_surplus`, no `MIN_SIDE`, nothing. The reviewer's table header — *"Live, after the dual-surplus gate"* — is therefore **wrong for 84.5% of served cards**: the dual-surplus gate (`user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE`, `trade_service.py:4720-4721` / `trade_optimizer.py:560-561`) exists only on the divergence paths.

Prod measurement of the consequence (`give_value` / `receive_value` are the stamped consensus package values):

| basis | n | user receives more | user gives more | mean net to user |
|---|---|---|---|---|
| consensus | 7,282 | **6,939 (95.3%)** | 117 (1.6%) | **+394.2** |
| divergence | 1,335 | 981 (73.5%) | 354 (26.5%) | +715.1 |

The 117 consensus exceptions are all `user_value_basis: personal` (110) or `consensus` (7) with `relaxed: false` and no `model_arm` — most likely legacy rows predating the current gate; they are 1.6% and do not change the picture.

### The reviewer's divergence-path argument · **PARTIALLY CONFIRMED**

*"On divergence, dual surplus can still pass a deal the partner loses on their raw board, because partner surplus is shrunk-less, marginal, and has no #108."* Three sub-claims:

- **"shrunk-less" — CONFIRMED.** The user's map is `_shrink_user_elo(user_elo, seed_elo, confidence, placements)` (`trade_service.py:4021-4022`); the opponent's is raw `elo_to_value(opp_elo.get(pid, 1500.0))` (`trade_service.py:4502`, `trade_optimizer.py:295`). The partner's private opinion is credited at full strength while the user's is regularized toward consensus, so the mutual-gain gate clears on the partner's un-shrunk (noisier) board. Genuine asymmetry, and it does run in the reviewer's direction.
- **"marginal" — REFUTED as an asymmetry.** `MARGINAL` applies to **both** sides: `_mu` on the user's roster in the user's space, `_mo` on the opponent's roster in the opponent's space (`trade_service.py:4526-4551`, `trade_optimizer.py:317-360`). Symmetric by construction. Listing it as a partner-side handicap is wrong.
- **"has no #108" — CONFIRMED.** `fit_premium_1for1` / `user_gain_ok_1for1` read `raw_user_elo` only (`trade_service.py:4657-4660`, `trade_optimizer.py:535-538`). There is no opponent-board 1-for-1 ordering gate anywhere. Real, one-sided.

---

## 5. The four-window-pairing demonstration

Run against the real `outlook_direction_mult` with the live `_cfg` (202 keys loaded), two equal-consensus-value assets (`WR` age 29 vs `WR` age 22; `_now_lean` = +0.35 and −0.18 respectively):

| user outlook | user **GETS** the vet | user **SENDS** the vet |
|---|---|---|
| `championship` | **×1.1325** | ×0.8675 |
| `contender` | **×1.1325** | ×0.8675 |
| `rebuilder` | ×0.0308 | **×1.2650** |
| `jets` | ×0.0308 | **×1.2650** |
| `not_sure` / `None` | ×1.0000 | ×1.0000 |

(`rebuilder` "gets the vet" = `max(0.05, 1 − 3.0×0.265) = 0.205`, then `× outlook_dir_age_gap_mult 0.15` = 0.031 — near-exclusion, exactly as documented at `trade_service.py:2345-2350`.)

Now the four pairings. **The partner's window is not an argument** (`co_varnames[:5] == ('give_ids','recv_ids','players','outlook','value_of')`), so each row below is the *same* number as its same-user-window sibling:

| user ↔ partner | card the lever boosts | is that card landable? |
|---|---|---|
| contender ↔ **contender** | user gets the vet, ×1.13 | **No** — the partner is also buying now-value and will refuse |
| contender ↔ **rebuilder** | user gets the vet, ×1.13 | **Yes** — complementary; the rebuilder wants to sell the vet |
| rebuilder ↔ **rebuilder** | user sends the vet, ×1.27 | **No** — the partner does not want the vet either |
| rebuilder ↔ **contender** | user sends the vet, ×1.27 | **Yes** — complementary |

**This corrects the reviewer.** They write that outlook ranking "boosts the deal where you extract the vet — the deal the other contender refuses," implying the lever prefers same-window vet-extraction over the complementary opposite-window deal. It cannot: ×1.1325 in row 1 and ×1.1325 in row 2 are the same multiplier. The lever is **neutral between pairings**, not biased toward the wrong one.

The correct statement of the defect is weaker but still real: the strongest single directional term in the deck (up to ×1.27 boost, down to ×0.031 near-exclusion — far larger than aggression's ±0.20 or need_fit's ±0.075) spends its entire dynamic range on a signal that carries **zero information about whether the partner would accept**. It cannot distinguish the landable half of its own boosted set from the unlandable half.

**The partner-side counterweight the reviewer missed** (and which bounds the damage): on divergence cards the both-sides surplus gate runs on the partner's real board, so if a contender partner's board genuinely overprices the vet, an extraction card fails `opp_surplus < MIN_SIDE` before ranking ever sees it. That counterweight is present on **15.5%** of served cards and absent on the other 84.5%, where the partner has no board and no gate at all.

---

## 6. Empirical summary (prod, read-only)

| Metric | Value |
|---|---|
| Served cards / distinct users | 8,617 / **5** |
| Window | 2026-07-27 → 2026-08-19 |
| `basis: consensus` | 7,282 (84.5%) |
| `basis: divergence` | 1,335 (15.5%) |
| `aggression_variant` per user | light 3, fair 1, generous 1 |
| `aggression_variant` per card | light 7,131 (82.8%), generous 1,174, fair 124, missing 188 |
| Mean `fairness_score` — light / generous / fair | 0.841 / 0.820 / 0.852 |
| Mean `surplus_margin` — light / generous / fair | 244.9 / 894.7 / 353.6 |
| `partner_fit` non-null | **3,922 of 8,617 (45.5%)** — values spread 0.00→1.00, with 2,095 at exactly 1.00 |
| Cards where user receives more consensus value | 7,920 of 8,617 (91.9%); consensus-only **95.3%** |
| Consensus cards below mobile's league-normal 0.75 | 805 (11.1%) |
| `model_arm` stamped | `current` 877; null 7,740 (pre-bake-off) |

**On the reviewer's "⅓ of users" claim:** correct as design (`MD5 % 3`), materially wrong as a description of the live corpus (3 of 5 users, 82.8% of cards). This helps them.

**Does the light cohort's fairness/surplus distribution differ?** Mean fairness 0.841 (light) vs 0.820 (generous) vs 0.852 (fair) — a 2–3 point spread with the light cohort in the middle, which is not evidence of a light-specific tilt. Mean `surplus_margin` differs far more (245 / 895 / 354), but the cohorts are single users with different leagues and boards, so this is confounded beyond use at n=5. **No inference about the aggression lever's effect is supportable from this data.** The compositional facts above (variant assignment, basis mix, direction of value flow) are structural and do not depend on cohort comparison.

### Confound statement (D-091)

[D-091](../../living-memory/DECISIONS.md) records that 339 of 2,651 served cards (12.8%; 23.2% of pick-bearing cards) carried a phantom 2029 pick, and that phantom cards drew 6.7% of likes but 15.8% of passes — a pass rate more than double the like rate. **3,652 of my 8,617 rows (42.4%) sit in the 2026-08-16 → 08-19 contamination window.**

What this does and does not pollute:

- **Does NOT pollute anything I concluded above.** Every number I rely on is *compositional* — which variant a card carried, which basis it had, and the sign of `receive_value − give_value`. None of it reads a like/pass outcome. The direction result is stable when the window is excluded: **4,369 of 4,643 (94.1%)** pre-08-16 consensus cards still favor the user, versus 95.3% overall.
- **Does pollute any ranking-QUALITY inference**, i.e. anything of the form "cards with lever X on get liked more". Under D-091 a systematic slice of the deck was rejected for being nonsensical rather than for being badly ranked, and picks appear in 41.0% of my rows (3,534 of 8,617). **I therefore drew no outcome-based conclusion in this memo, and Claim 7 should not be adjudicated on like/pass data from this window by anyone else either.**

---

## 7. What strengthens and what weakens the reviewer

**Strengthens them (things they did not claim but could have):**
1. There is **no opponent gate whatsoever** on the consensus path — not a weak one, none (`_emit`, `trade_service.py:4964-5045`). Their "after the dual-surplus gate" framing gave the engine credit it does not have.
2. Consensus is **84.5%** of served cards, so the one-sided rule is the dominant regime, not an edge case.
3. **95.3%** of consensus cards measurably hand the user more consensus value, mean +394 points. Robust to the D-091 window.
4. The live population is **82.8% "light"-variant cards**, not the one-third the design implies.
5. `TradeCard.tsx:453` prints *"this is a balanced trade by consensus value"* on every consensus card with **no fairness check**, and 11.1% of those cards are below the app's own league-normal bar — all tilted the user's way. This is the live copy defect their §(c) was groping for.
6. `counterpartyStatement` in the queued `trades.presentation_v2` surface asserts partner interest **unconditionally** — strictly worse than the narrative string they attacked, and it is scheduled to ship.

**Weakens them:**
1. **Three of six rows are not one-sided levers.** `_tier_mult_v2` is a `max` over both sides and is direction-blind. `filler_ok` uses the identical `max(user, opp)` metric on both sides. Sweeteners pad whichever side is consensus-light and then re-gate both surpluses — corrective, not extractive. A six-row table where half the rows do not do what the column header says is a weak table.
2. **The headline copy allegation is refuted at the render layer.** `build_narrative` output — including "fits their timeline" and the entire `_fairness_label` vocabulary — is computed, wired, and dropped. No client renders it. This is the single most serious charge in the claim and it does not survive.
3. **"Marginal" is symmetric**, not a partner handicap. Listing it alongside "shrunk-less" and "no #108" pads a two-item asymmetry into a three-item one.
4. **The synthesis is mechanically impossible as written.** The outlook lever applies the identical multiplier to contender↔contender and contender↔rebuilder because the partner's window is not an input. It cannot prefer the former.
5. `need_fit` (weight 0.15) **is** a genuinely two-sided ranking term — it rewards giving from the user's surplus into the opponent's need. The claim's premise that "every lever is one-sided" is not true.
6. On divergence cards the partner's own board **does** gate acceptance, which is a real partner-side counterweight the table omits. It is absent on consensus, but present on 15.5% of served cards.

---

## 8. Nothing was changed

No file under `backend/`, `mobile/`, `web/`, `config/`, or `living-memory/` was modified. No D-/G-/M-/Q- id was allocated. All prod access was `SET TRANSACTION READ ONLY` + SELECT; probe scripts live in the session scratchpad and are not committed.
