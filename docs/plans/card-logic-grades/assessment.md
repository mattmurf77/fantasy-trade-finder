# Card-logic grades: feasibility assessment

> Assessment and design only, 2026-11-11. Code baseline: `origin/main` at `8b5f076a`. Nothing
> here is built. Every claim about current behaviour cites `file:line` on that baseline. Numbers
> are either **measured** (offline, on `backend/eval/synthetic_league.py`; no production data,
> no network) or **inferred** (reasoning from code), and are marked. No user, league or roster
> data appears here.

The operator's idea (2026-11-11): show a 1–10 grade per evaluation parameter (team outlook,
market value, user rankings, …) behind a "how did we generate this card" tooltip, leaving the
card itself as it is. The question is which of three things that would be:

- **(A) Feasible as-is:** the grades fall out of how cards are generated and scored today.
- **(B) Change generation:** score each input independently and rank by a weighted average
  (later: user-set weights).
- **(C) Appearance only:** grades computed for display, not tied to the engine.

**Short answer.** Mostly (A). The served engine already scores each card as a weighted sum of
three separately computed numbers per side, and freezes them in the card's proof. Three honest
grades can be shown today: your rankings, market value and team plan. Two catches make a naive
version misleading:

1. **Most of what decides a card is not a grade.** Eligibility is a set of pass/fail rules,
   and order is set by whichever side gains less. That side is the other manager on about 60%
   of the top 30 cards (measured), and their numbers are private. So the tooltip needs checks
   as well as grades, and it must not imply your grades produced the rank.
2. **"Match strength" on today's cards is not a strength measure.** On the served path it is
   the card's position counted from the bottom of the deck. It reads 100 on about 90% of
   served cards (measured).

**Recommended:** a middle path. Show the gates as checks and the three real components as
grades on fixed scales, composed by the server from the frozen proof. Do not restructure
generation for this. User-set weights stay a later and small step, but should wait for the
acceptance-model work (R5) that may replace the hand weights altogether.

## Contents

- [1. How a card is scored and ordered today (reference)](#1-how-a-card-is-scored-and-ordered-today-reference)
- [2. Which of the operator's parameters exist per card](#2-which-of-the-operators-parameters-exist-per-card)
- [3. Measured: grades on generated cards](#3-measured-grades-on-generated-cards)
- [4. Option A: grades from today's engine](#4-option-a-grades-from-todays-engine)
- [5. Option B: independent inputs and a weighted average](#5-option-b-independent-inputs-and-a-weighted-average)
- [6. Option C: appearance only](#6-option-c-appearance-only)
- [7. Middle path (recommended)](#7-middle-path-recommended)
- [8. The tooltip](#8-the-tooltip)
- [9. Sequencing with rules-first and win-now](#9-sequencing-with-rules-first-and-win-now)
- [10. Risks](#10-risks)
- [11. Open decisions for the operator](#11-open-decisions-for-the-operator)
- [Appendix: how the measurements were run](#appendix-how-the-measurements-were-run)

---

## 1. How a card is scored and ordered today (reference)

### 1.1 Which generator serves

- Organic Find a Trade on the owner path routes through `bakeoff_runner.owner_generator`
  (`backend/bakeoff_runner.py:318-333`). The DB knob `owner_bilateral_enabled` picks bilateral,
  and `owner_bilateral_revision_enabled` = 1 picks revision 2 (`owner-v2-bilateral-2`,
  `backend/trade_gen_bilateral_candidate.py:20`). Both knobs default to 0 in code
  (`backend/database.py:3865-3866`).
- Production values could not be read. **Revision 2 is inferred**: the owner authorised its
  production activation (`docs/plans/bilateral-model-revision/release-decision.md`, superseding
  decision 2026-09-22), and the 247-request production replay ran revision 2
  (`living-memory/TEST_LEDGER.md:9772`).
- When the owner arm serves, `bakeoff_fixed_order` is true (`backend/server.py:13233-13234`,
  `owner_serve` at `:13124`). This **bypasses** every post-generation reranker: exploration
  (`:13238-13243`), fatigue multipliers (`:13602`), taste (`:13641`), the value model
  (`:13664`) and Thompson/diversity ordering (`:13688`). The flags are on in
  `config/features.json:227-235`, but they do not touch owner decks.
- The fast deck is off (`config/features.json:10`, D-232), so the full solve serves.

### 1.2 Eligibility: what decides that a card exists

These are gates. A card passes or it does not, and no score can buy its way past one.

| Gate | Where | Rule |
|---|---|---|
| Shape, ownership, avoided positions, prior dispositions, tier direction | `backend/trade_gen_owner.py:470-512` | Organic shapes 1×1 / 1×2 / 2×1 only |
| **Market floor** | `trade_gen_owner.py:524-525` | Consensus package ratio ≥ the user's fairness floor (max of setting and `market_floor_absolute`, `:215`) |
| **Overpay ceiling** | `trade_gen_owner.py:526-527` | `trade_service.overpay_ok` |
| **Each side's support > 0.35** | `trade_gen_bilateral.py:244` (`utility = support − .35`), checked at `trade_gen_owner.py:535-537` | `viewer_no_benefit` / `counterparty_no_benefit`. In practice this is a floor on the *weighted sum* |
| Untouchables | `trade_gen_owner.py:538-547` | Either side's tagged players |
| **Viewer intent** | `trade_gen_bilateral.py:196-201`, applied at `:271-272` | One of: explicit selection; `personal_board` (the focal swap's board lean ≥ 0.025 *and* the package's net lean ≥ −0.025); `declared_intent` (target, trade block, wanted position, or a **declared** outlook with plan gain ≥ 0.10); `missing_board` (no board, and some plan or market gain). Otherwise `viewer_intent_unfulfilled` |
| Known preference harm | `trade_gen_bilateral.py:279-280` | Either side's net lean < −0.15 with plan gain < 0.20 |
| Tanking rules | `trade_gen_bilateral.py:281-302` | Own next first, RBs without an exception, favoured young assets |
| Unnecessary compensation | `trade_gen_bilateral.py:308-338` | A strictly simpler eligible package dominates |
| Quality filters (`deck.quality_filters`, on) | `backend/deck_quality.py:83-112`, applied at `server.py:14214` | Breakup, filler, redundant QB/TE: dropped. Repeat cap (`REPEAT_CAP = 3` in the first 30, `deck_quality.py:31`): deferred |
| Decline-window suppression (`deck.fatigue`) | `server.py:13588-13597` | Removes near-duplicates of declined cards (the removal still runs on owner decks) |

Rules-first (`fast-deck-v2-design.md` §5.1) moves the quality rules and significance ahead of
ranking. They stay gates; only their position moves.

### 1.3 Ranking: the score among eligible cards

Per side (viewer and counterparty, each from their own board and team), computed in
`trade_gen_bilateral._Search._owner` (`trade_gen_bilateral.py:171-247`):

| Component | Weight (`:23-24`) | Input | Formula (`:205-207`) | Range |
|---|---:|---|---|---|
| `preference_fulfillment` | 0.45 | Market-weighted sum over the package of the side's per-player **direction**: personal vs market tier position and percentile, `clip(.7·Δtier/3 + .3·Δpercentile)` (`:90-91`), signed + for received (`:179-180`) | `clip(.5 + net, 0, 1)` | 0–1, 0.5 = no lean |
| `market_acceptability` | 0.35 | Consensus package gain `(in − out)/max(in, out)` (`:178`) | `clip(.5 + .5·gain/tol, 0, 1)`, `tol = max(1 − floor, .05)` (`:204`) | 0–1, 0.5 = even. The two sides are exact mirrors |
| `team_plan` | 0.20 | `plan_gain = clip(plan_shift + need)` (`:195`). `plan_shift` = market-weighted `_plan_asset`: age and position by outlook (`:124-145`; revision 2 changes the rebuild branch, `trade_gen_bilateral_candidate.py:29-53`). `need = clip(4·need_utility)`, from the dynasty-value lineup proxy (`trade_gen_owner.py:270-275, 339-363`) | `clip(.5 + .5·plan_gain, 0, 1)` | 0–1, 0.5 = neutral |

- `support = Σ weight × component` (`trade_gen_bilateral.py:208`). It is additive, and each term
  is clipped and monotone in its input.
- Each support also carries an uncertainty range (`:209-213`), recorded but never used to rank.
- **The deck is ranked by the two sides jointly, not by the viewer.** The quality tuple is:
  1. `weaker_support = min(viewer, counterparty)`;
  2. then `total_support`;
  3. then the summed net preference;
  4. then size and ids.

  This is a lexicographic order, built at `trade_gen_bilateral.py:264-268` and sorted at
  `:426-429`. A 32-card lookahead may then swap cards within 0.025 (0.05 on the total) for
  asset/partner variety (`:432-454`).
- **Revision 2** adds same-family price precedence: a cheaper sibling with no less personal,
  plan or position benefit must come first (`trade_gen_bilateral_candidate.py:306-357`,
  `_rank :360-377`). It also records per-card diagnostics: `decomposition` (`:90-94`),
  `market_terms`, `consideration_profile` and `term_efficiency` (`:176-185`).
- **Lane** = `window` if the viewer's plan gain > 0.01, else `value`
  (`trade_gen_bilateral.py:507`). It is a slot class, not a score.
- **After generation**, the bilateral presentment permutes survivors within the same
  `(basis, lane)` class. Swaps are allowed only when both managers' supports stay within 0.025
  (`backend/trade_bilateral_presentment.py:142-235`, tolerance `:15`), and term precedence is
  never crossed. Then the quality filters run and the repeat cap defers (above).
- **The card's numbers.** `mismatch_score = composite_score = len(emitted) − index`
  (`trade_gen_bilateral.py:527`; page search: `trade_first_page.py:1134`). That is a position
  counted from the bottom, not a score.

### 1.4 Fallback paths

If the owner arm forfeits (for example a pool timeout, `server.py:4719`), or for decks outside
the owner path, the legacy pipeline serves. It ranks by a multiplicative stack:

- `W_MIS · mismatch` (capped) `· damp + W_FAIR · fairness`, × tier multiplier
  (`trade_service.py:7152-7162`, weights `:6896-6900`);
- then partner fit, need fit, lane, outlook and negmem multipliers (`trade_service.py:6615-6790`);
- then Thompson draws, diversity, fatigue and taste (`server.py:13586-13700`).

These are not separable into per-factor grades. **Grades should exist only for owner-bilateral
cards whose proof matches the card.** Other cards get no tooltip grades.

### 1.5 Where each number lives

| Quantity | Computed | On the served card payload? | Frozen in evidence? |
|---|---|---|---|
| Viewer's 3 components, support, range, weights | `trade_gen_bilateral.py:205-213, 229-230` | **No.** `trade_card_to_dict` exposes only identity and selection (`server.py:21177-21197`) | Yes: the whole proof is `deck_impressions.valuation_json` (`server.py:10669-10679`) |
| Counterparty's components, board-derived lean, benefits | same | No, and must never be (`test_fit_block_v3.py:659-661`) | Yes, private |
| Intent path, focal lean, net lean, plan gain, need, market gain | `:196-201, 231-241` | No (benefits only, in `match_context`, `:514-517`) | Yes |
| Rank-key numbers (`weaker_support`, `total_support`) | `:264-268` | No | Yes |
| Fit block (plan/need lead, outlook tags, rank moves) | `trade_narrative.py:706-775` | Yes, `fit_block` (`server.py:21187-21196`) | Its inputs are |
| Dynasty value swing | `server.py:21198-21212` | Yes | Yes |
| "Match strength" | client: `mismatch_score / 300 × 100` (`mobile/src/api/trades.ts:131-134`), shown by `TradeCard.tsx:791-792` | Yes (as `mismatch_score`) | Yes |

**Every grade can be composed at serialization time** from `card.owner_evaluation` (already
used there for the fit block). No new engine output is needed for the first version.

### 1.6 Claims from the window research, checked

| Claim (`window-asset-identification/README.md`) | Verdict |
|---|---|
| "Preferences carry 45% of the card score against 20% for your team plan" | **True of the nominal weights** (`trade_gen_bilateral.py:23-24`). **Misleading about influence.** Measured on the served inventory, weight × spread is: market **0.094–0.100**, preference **0.024–0.026**, plan **0.012–0.031** (§3.2). The preference component barely varies, because the clip at 0.5 ± net and the market-weighting keep it near 0.5. Preference's real power is the **intent gate**: 26–28 of the top 30 cards qualify by `personal_board` |
| "A card can qualify purely because the user's own board rates a player about 15% above market" | **True, and 15% is conservative.** The gate is a focal direction ≥ 0.025 in tier-coordinate units (`:196`), not a percentage. Measured share of the viewer's players whose lean qualifies: lift 5–10% → 60%; 10–15% → 80%; 15–25% → 96%. Tier position decides at small lifts |
| Line numbers for weights, gate, rank and lane | Match the current file |

---

## 2. Which of the operator's parameters exist per card

| Operator's parameter | Real, separable per-card quantity? | Notes |
|---|---|---|
| **User rankings** | **Yes:** the viewer's `preference_fulfillment` (net lean), plus the gate input `focal_preference` | Two different numbers: the gate looks at the headline player; the score looks at the whole package |
| **Market value** | **Yes:** the viewer's `market_acceptability` (from consensus gain) | The card already shows it as the Dynasty value swing. Scaled by the user's own fairness floor (`tol`) |
| **Team outlook / plan fit** | **Yes:** the viewer's `team_plan`, which **mixes** age-by-outlook (`plan_shift`) with the lineup proxy (`need`) | `plan_shift` is not stored on its own (only `team_plan_gain` and `need_utility`, `trade_gen_bilateral_candidate.py:90-94`). "Plan" is age and position only today (research G2/G8) |
| **Positional need / lineup** | **Partly:** `need_utility`, a dynasty-value lineup proxy, not points (`trade_gen_owner.py:340-341`) | Folded into team plan. Weight 0.25 contending, 0.05 rebuilding, 0 tanking (`:273-275`) |
| **Partner fit / likelihood they accept** | **No acceptance quantity exists.** The counterparty's support is "interpretable support, not probability" (`:264`) and contains their **private** board | Within-user AUC of `weaker_support` vs the viewer's likes is 0.28–0.39, and there are < 5 counterparty responses ever (`docs/plans/realtime-trade-engine/acceptance-eval.md:14-30`). Can only be a check ("their side gains too"), never a grade |
| **Roster evaluation** (legality) | Gate only (`trade.roster_evaluation` off, `config/features.json:293`) | — |
| **Pick preferences** | Inside plan (`_plan_asset("PICK")`) and preference | No separate number |
| **Declared targets / blocks / positions** | Gate path `declared_intent` plus `preference_priority` (`trade_gen_owner.py:548-558`) | `preference_priority` is recorded but **not used in the rank tuple** |
| Price efficiency | Revision 2 `term_efficiency` | Ordering precedence, not a score |
| Variety | Lookahead and presentment | Ordering only |

---

## 3. Measured: grades on generated cards

Synthetic 12-team leagues (seeds 7 and 11), revision 2 generator, then presentment and quality
filters in served order. See the appendix for method. These are synthetic players; the shape
generalises, the levels do not.

### 3.1 Mock grades, first 8 served cards

Mapping used (justified in §4.2):
- **Your rankings** = `1 + 9·(net lean + 0.20)/0.40`, clipped 1–10.
- **Market value** = `1 + 9·market_acceptability`.
- **Team plan** = `1 + 9·team_plan`.

All rounded. Raw driver in brackets.

**Viewer declared All-in (seed 7):**

| # | Shape | Why it qualified (gate) | Your rankings | Market value | Team plan | Order set by | Lane | Match strength today |
|---|---|---|---|---|---|---|---|---|
| 1 | 1×1 | you rank the player above market | 8 (+0.095) | 5 (−0.051) | 8 (+0.558) | them | window | 100 |
| 2 | 1×2 | you rank the player above market | 6 (+0.028) | 7 (+0.086) | 9 (+0.715) | them | window | 100 |
| 3 | 1×1 | you rank the player above market | 8 (+0.132) | 7 (+0.081) | 6 (+0.187) | them | window | 100 |
| 4 | 2×1 | you rank the player above market | 6 (+0.029) | 5 (−0.017) | 8 (+0.499) | them | window | 100 |
| 5 | 1×1 | you rank the player above market | 6 (+0.002) | 6 (+0.017) | 8 (+0.454) | **you** | window | 100 |
| 6 | 1×2 | you rank the player above market | 7 (+0.073) | 5 (−0.025) | 6 (+0.136) | **you** | window | 100 |
| 7 | 1×1 | matches a declared target / plan | **3** (−0.112) | 6 (+0.041) | 9 (+0.803) | them | window | 100 |
| 8 | 1×1 | you rank the player above market | 8 (+0.117) | 6 (+0.029) | **4** (−0.256) | them | value | 100 |

**Viewer "not sure" (seed 11):** Team plan is roster fit only (window weight 0).

| # | Shape | Gate | Your rankings | Market value | Team plan | Order set by |
|---|---|---|---|---|---|---|
| 1 | 2×1 | board | 9 (+0.152) | 5 (−0.011) | 5 (−0.015) | them |
| 2 | 1×1 | board | 6 (+0.042) | 6 (+0.032) | 7 (+0.283) | them |
| 3 | 2×1 | board | 8 (+0.093) | 6 (+0.025) | 6 (+0.117) | them |
| 4 | 2×1 | board | 8 (+0.122) | 5 (−0.047) | 6 (+0.101) | you |
| 5 | 2×1 | board | 8 (+0.099) | 6 (+0.018) | 5 (−0.013) | them |

Reading:
- **Card 8 (All-in)** is the operator's mystery card in miniature. It is plan-negative (4/10)
  and served because the user's rankings like it. An honest tooltip shows that conflict; today
  nothing does.
- **Card 7** qualifies through a declared target while the user's own board mildly dislikes
  the package (3/10). A grade alone looks contradictory, so the tooltip needs the gate shown as
  a check.
- **Card 5** has a net rankings lean of zero (6/10) yet qualified on the board. The headline
  player is liked, and the companion offsets him. Again, the check explains it.
- In **6 of 8** All-in cards the other side's support set the position. Your three grades
  cannot explain where those cards sit.

### 3.2 Inventory statistics (all served cards, per run)

| Run | Served (of emitted) | Weight × SD: pref / market / plan | Viewer is weaker side, top 30 | Path `personal_board`, top 30 | Match strength = 100 |
|---|---|---|---|---|---|
| All-in, seed 7 | 572 of 3,979 | 0.025 / 0.099 / 0.031 | 13 | 26 | 92.8% |
| Contending, seed 7 | 510 of 3,923 | 0.026 / 0.100 / 0.024 | 12 | 26 | 92.5% |
| Rebuilding, seed 11 | 729 of 4,232 | 0.024 / 0.094 / 0.026 | 13 | 26 | 91.1% |
| Not sure, seed 11 | 664 of 3,767 | 0.025 / 0.096 / 0.012 | 11 | 28 | 89.2% |

Grade spread with the plain `1 + 9·component` mapping, all served cards, All-in run:
- **Preference:** grades 4–7 only (553 of 572 are 5 or 6).
- **Market:** the whole 1–10.
- **Plan:** 3–9.

This is why §4.2 rescales preference.

---

## 4. Option A: grades from today's engine

### 4.1 What it is

Compose grades at serialization from the frozen proof, for the viewer's side only. Show the
gates that let the card in as checks.

### 4.2 Per factor

| Factor | Underlying number | Mapping (fixed; same meaning on every card) | Available at serve time | Can it contradict the card? |
|---|---|---|---|---|
| **Your rankings** | `viewer.intent.net_preference` (the package's market-weighted lean) | Fixed linear scale, ±0.20 net lean → 1–10, 5.5 = no lean. The engine's own component has the same order but uses only 4–7 of the scale (§3.2) | Yes, in the proof | **Yes**, unless the gate is shown: a card admitted because you like the headline player can grade 6 or lower (§3.1 cards 5, 7). Fix: show the gate as a check naming the player |
| **Market value** | `viewer.support.components.market_acceptability` | `1 + 9·c`. Exactly the score input. 5.5 = even; 1 = at your fairness floor; 10 = you gain ≥ `tol` | Yes | Rarely. It agrees with the value bar's direction. It depends on the user's fairness setting through `tol`, so the same trade grades differently at a 0.50 floor than at 0.75. That is true to the engine, and the copy says "for your fairness setting" |
| **Team plan** | `viewer.support.components.team_plan` | `1 + 9·c`. 5.5 = neutral | Yes | **Yes, by design.** It can be low on a served card (§3.1 card 8). That is the plan conflict the win-now plan will surface. It is also age-based today, so a high grade can rest on an older backup (research G8). The text must say what it measures |

**Why fixed scales, not percentiles.** A percentile within the deck makes "7" mean "better
than 70% of this deck". It would shift when the deck refreshes and when another user looks,
and it would invent spread where the engine sees none. Fixed scales are anchored to the engine's
neutral point (no lean, even value, no plan change), so a grade means the same on every card
and every deck. The preference rescale is still a fixed, monotone transform of the exact score
input, so it preserves the engine's order between cards.

### 4.3 What it costs

- **Server:** one pure composer in `trade_narrative.py` (beside `fit_block`), a payload key,
  a flag, the prepared-payload whitelist (`backend/prepared_trade_payload.py:42-47`
  `PUBLIC_FIELDS`), a `DECK_PIPELINE_VERSION` bump (`server.py:4584`, pins `:4710-4732`) and
  tests.
- **Mobile:** normalizer, type, sheet, structural check, TestFlight checklist.
- **One app build.**
- `trade_narrative.py` is in `_ENGINE_CODE_MODULES` (`server.py:4739-4757`). Deploying it
  re-stamps `engine_version`, so stored pages and prepared inventories regenerate once. The
  fit block had the same cost.
- **Inferred:** about one build session for the server and one for mobile.

### 4.4 Risks

- Users read the grades as the reason for rank, but the other side's private support sets
  order for about 60% of top cards.
- The preference grade alone looks lukewarm on cards it admitted.
- Team plan claims "win-now" from age.

All three are copy and structure problems, solved by §7.

### 4.5 Verdict

**Feasible for three viewer-side factors. Not feasible for "partner fit / likely to accept"**:
no such number exists, and the nearest one is private. On its own it would mislead. With
checks and an ordering note (§7), it is truthful.

---

## 5. Option B: independent inputs and a weighted average

### 5.1 How close today's score already is

**Per side, it is already exactly that.** Three separately computed components, explicit
weights, an additive sum (`trade_gen_bilateral.py:205-208`). The weights are recorded on every
proof (`:230`) and in every generation report (`:469`).

What a single weighted average **cannot** express:

1. **Gates** (§1.2): the market floor, overpay ceiling, intent, untouchables, preference harm,
   tanking, dominance, quality rules and the per-side support floor of 0.35. As soft terms they
   would let a lopsided or nobody-wants-it trade outrank a fair, wanted one whenever the other
   terms were high enough.
2. **Two-sided max-min:** order is by the *weaker* side's support. A weighted average of the
   viewer's inputs alone would stop protecting the other manager. That protection is the whole
   point of the bilateral engine (`recommendation.md` §1 step 3).
3. **Clips and couplings:** each component is clipped; plan includes need; the two market terms
   are exact mirrors; preference is market-weighted.
4. **Precedence and variety:** revision 2's family precedence and the 0.025 diversity
   tolerance are order constraints, not weights.

### 5.2 Gained and lost in trade quality

- **Gained:** nothing for the tooltip. The decomposition already exists.
- **Lost, if gates became weighted terms:** the floor, intent and harm rules exist because the
  Calibration grades and tester reports found exactly the cards they block
  (`deck_quality.py:1-19`; release decision §"What the comparison established").
- **Unknown either way:** there is no outcome evidence for the current weights or any others
  (acceptance-eval: within-user AUC 0.28–0.39; the only consistent signal is the viewer's
  market gain).

### 5.3 Page-first search (ADR-028): what its bounds assume

Read from `trade_first_page.py:26-56, 238-387`:

- (a) Per side, score = Σ `w_k · clip(affine(x_k))` with every `w_k ≥ 0` and each term monotone
  in its input. Weights are read once from `trade_gen_bilateral._WEIGHTS` (`:249-252`), **one
  set for both sides**.
- (b) Preference and plan inputs are **sums of per-asset rows**, market-weighted and signed
  (`_Bounds.rows`, `:328-337`). This is what allows a bound before pricing.
- (c) The two market gains are **exact negatives**. The pre-pricing bound splits `w_market`
  across sides on that basis (`pre`, `:355-363`).
- (d) Need is bounded by a matroid argument on the lineup assignment (`:31-41`), valid while
  lineup value is a fixed per-asset number.
- (e) The search proves a stop on the **leading rank key only**, `weaker_support`; the tie keys
  follow from the k + 31 prefix (`:5-13`).

Consequences:

- **Changing the weights** (any nonnegative values): admissible if `_Bounds` reads the same
  weights as the evaluator. Per-user weights need per-side weights in `_Bounds`, since the
  counterparty would keep the defaults. Small change. Exactness tests must re-run
  (`backend/tests/test_trade_first_page.py`).
- **A new additive component** (for example a season term): admissible only if it is
  per-asset decomposable, like (b), or has its own monotone upper bound. Season value inside
  the lineup proxy keeps (d) valid if each asset's season value is fixed per request.
- **A lexicographic demotion** (for example "plan conflicts sort after everything aligned")
  **breaks (e)**: the leading key changes, so the search needs a class bound and a class-aware
  stop. A **subtractive penalty** on the viewer's support stays admissible with no proof
  change, because the unpenalised bound is still an upper bound, just looser.
- **Turning gates into weighted terms** removes the pruning the page search relies on. The
  envelope floor rejects about 8k of about 16k screened candidates before pricing (`:58-63`).

### 5.4 Other things it touches

- **Engine hash and pipeline digest.** Any change to `trade_gen_*.py` or `trade_first_page.py`
  changes `engine_version` (`server.py:4739-4757`) and invalidates stored pages. A request-input
  change (user weights) bumps `DECK_PIPELINE_VERSION` and must enter the request hash, so
  prepared inventories built under other weights are not adopted.
- **Calibration.**
  - A weight change is a new engine and needs its own paired round (the adapter compares fixed
    versions, `backend/outlook_calibration_adapter.py:15-19`).
  - User-set weights make graders' decks non-comparable; Calibration must pin default weights.
  - Any backend edit changes `code_revision` (`:20-28`). That is harmless, but it is recorded.
- **Win-now inputs.** The season value and labels enter through plan/need, which (a)–(d) can
  carry. The "moves against your plan" rule should be a penalty, not a sort class (above).
- **R5.** The engine roadmap plans to **replace** hand weights with two fitted heads,
  P(viewer likes) × P(counterparty accepts) (`recommendation.md:184-200`). User-set weights
  would build a user-facing feature on the part the roadmap expects to retire.

### 5.5 User-set weights would need

- Per-user, per-league storage: `league_preferences` columns or a small table, plus a route,
  a data-dictionary entry and API reference.
- A place in the request capture and hash; prepared-inventory and stored-page invalidation.
- Bounds, for example each weight in [0.10, 0.70] with a sum of 1.
- A rule that the **support > 0.35 gate keeps default weights**. Otherwise a user could widen
  their own eligibility (for example 0.70 on market admits "I win at market" trades with no
  intent).
- **Viewer side only.** The counterparty keeps defaults, because their weights are their
  business and unknown.
- **The effect would be muted.** The viewer is the weaker side, and so sets the order, on only
  about 40% of top cards (measured), so a weight change moves less than users expect.

### 5.6 Size and verdict

- **Size (inferred):**
  - restructure into a new engine revision with per-side weights, bounds, parity suites, a
    replay of the 247 recorded requests and a Calibration round: 3–5 sessions;
  - user weights on top (schema, route, settings UI, cache invalidation): another 2–3.
- **Verdict: not needed for the tooltip, and not now for user weights.** The decomposition B
  wants already exists. What B would add is the claim that the deck *is* a weighted average,
  which would remove the gates and the two-sided protection. User weights are a later, viewer-
  side, bounded step, best decided after R5 shows whether hand weights survive.

---

## 6. Option C: appearance only

### 6.1 What it would be

Grades computed for display from inputs that look plausible, separate from the engine:
- "Team outlook" from player ages against the declared outlook;
- "Rankings" from the board-vs-market gap of the players on the card;
- "Market" from the value bar;
- "Partner fit" from roster need.

### 6.2 Where it would mislead

- **Contradicts order.** A 9/10/9 card shown below a 6/6/6 card, with no way to explain why.
  Order is set by the other side's private support on about 60% of top cards.
- **Contradicts eligibility.** A display-only "Rankings 3/10" on a card admitted *because* of
  your rankings: the headline-player gate versus the package lean.
- **"Partner fit / likely to accept"** would be invented. The engine has no acceptance model,
  and the code says so (`"interpretable_support_not_probability"`, `trade_gen_bilateral.py:264`).
  Calling it acceptance breaks the established copy rule (§10).
- **Drifts.** Two definitions of "plan" (display versus `_plan_asset`) diverge the first time
  the win-now plan changes the engine's.
- **Cheaper but not by much.** The composer is the same size either way.

### 6.3 Verdict

**Reject.** It costs about what A costs and is untruthful by construction.

---

## 7. Middle path (recommended)

### 7.1 What it is

Keep generation unchanged. Make the tooltip **truthful by construction**: every line is read
from the card's own frozen proof and the same predicates the engine used.

1. **Checks, not grades, for gates:** why the card was allowed, shown as pass lines with the
   specific reason (the gate path, the fairness floor, "their side gains too", the deck rules).
2. **Grades for the three real viewer-side ranking components**, on the fixed scales of §4.2.
3. **One ordering sentence** that says order depends on both sides, without saying which side
   set it. Naming the side would reveal the direction of the other manager's private lean.
4. **A conflict line** when a declared plan scores clearly negative. It uses one shared
   predicate, owned with the win-now demotion rule (§9).
5. **Fix "Match strength"** on owner cards. Today it is a deck position; see decision 2.

The engine side of this is a refactor that changes no bytes: the grade composer reads
`proof["viewer"]["support"]["components"]`, `intent` and `team_plan_gain`. **No proof field,
weight or order changes.**

When the win-now revision lands, it should record `plan_shift` and the season term as separate
proof fields. The tooltip then gets a fourth row, "This season", and "Team plan" stops mixing
age and lineup. That is the only engine change the grades ask for, and it rides a revision that
is happening anyway.

### 7.2 What it costs

As in §4.3 (about two sessions and one app build), plus the Match-strength change.

User-set weights later become a small step:
- per-side weights in `_Bounds`;
- a bounded settings control;
- the request hash.

That is about two sessions once R5 settles whether hand weights stay.

### 7.3 Verdict

**Recommended.** It is real (not appearance), cheap, and leaves generation alone.

### 7.4 First shippable slice

Server-only, dark:
- `card_logic` composer plus flag `trade.card_logic` (default off).
- Serialized on owner-bilateral cards whose proof matches the card. Edited cards get none.
- Tests:
  - the grade mapping is pinned;
  - every check maps to a real gate path;
  - privacy: the block is byte-identical under any change to the counterparty's board,
    benefits, intent or declared outlook (the `test_fit_block_v3.py:447-470` pattern);
  - none of the banned private fields appear in the payload;
  - prepared and page payloads carry it.

The mobile sheet follows in the next build.

---

## 8. The tooltip

### 8.1 Placement

- On owner-bilateral cards, the row that holds **Match strength today**
  (`TradeCard.tsx:791-792`) becomes one quiet row: the `label` "HOW THIS CARD WAS BUILT" plus
  an info glyph.
- Use the existing `InfoButton` (`mobile/src/components/HelpSheet.tsx:84-110`): a 44pt hit
  target, chalk-dim glyph, never ice. It is a disclosure, the same treatment as Home's playoff
  info toggle (`HomePlayoffBanner.tsx:67-69`).
- Tapping opens a **bottom sheet** in the `HelpSheet` style, not an inline expansion. The deck
  card is a swipe target with a fixed stack height, and the sheet already handles Reduce Motion.
- The card header stays untouched, as the operator wants.
- No emoji, no gradients, radius ≤ 8, flare not used.

### 8.2 Content and order

1. **Why you're seeing it** (checks; chalk check glyph, `body-sm`):
   - The gate path:
     - `personal_board` → "You rank {headline player} above his market value."
     - `declared_intent` → "Matches your {target list / trade block / wanted position / declared {plan}}."
     - `explicit_selection` → "Built around the players you picked."
     - `missing_board` → "You haven't ranked these players; built from market value and team fit."
   - "Within your fairness setting ({floor}%)."
   - "Their side gains too, by market value and roster." (Always true for a served card; never
     a number.)
   - When rules-first or `deck.quality_filters` is on: "Passes the deck checks: keeps your best
     player, no filler, no extra QB/TE."
2. **Your side** (three grade rows, in this order):

   | Row | Shown | One-line explanation (server text) |
   |---|---|---|
   | Your rankings | n/10 | "How much more you value what you get than what you send, by your board." |
   | Market value | n/10 | "Consensus dynasty value, for your fairness setting. 5–6 is about even." |
   | Team plan | n/10 | Declared plan: "Fit with your {All-in} plan, by age and position, plus starting depth." No plan: label "Roster fit", text "No plan set — starting depth only." |

3. **Ordering sentence:** "Cards are ordered so the side that gains less still gains. These
   grades are your side only."
4. **Conflict line** (when it applies): "Moves away from your {All-in} plan — your rankings
   like it."
5. **Footer:** "Estimates from consensus values and your rankings, not a prediction."

### 8.3 Edge cases

- **Factor not applicable:**
  - Tanking: need weight 0, so the row is plan only and says so.
  - "Not sure": the row is relabelled "Roster fit".
  - A grade is never shown as a fake 5.
- **Incomplete data:**
  - Missing ages (`team_plan_evidence.missing_age_ids`) → "Some players have no age; plan
    grade is partial."
  - Viewer preference state `unknown`/`partial` (`preference_evidence.state`) → "Based on the
    players you've ranked."
- **Counterparty unknown board:** keep today's reason line (`trade_gen_bilateral.py:511-512`);
  the sheet adds nothing about them.
- **Non-owner, edited or protected cards** (likes-you, standing offers, revised offers without
  a matching proof): no glyph.

### 8.4 Accessibility

- The glyph's label: "How this card was built".
- In the sheet, each grade row reads as one element: "Your rankings, 8 out of 10. How much
  more you value …".
- Meters get `accessibilityRole="progressbar"` (as `StrengthBar.tsx:44-49` does). Values are
  never colour-only.
- Grade meters use a neutral chalk fill with a tick at neutral, not pos/warn/neg. Grades
  describe; they are not verdicts.

### 8.5 Server payload

The server composes everything, so web and app cannot disagree:

```json
"card_logic": {
  "v": "logic-1",
  "checks": [
    {"code": "gate.personal_board", "text": "You rank J. Doe above his market value."},
    {"code": "gate.fairness", "text": "Within your fairness setting (75%)."},
    {"code": "gate.their_side", "text": "Their side gains too, by market value and roster."}
  ],
  "grades": [
    {"code": "rankings", "label": "Your rankings", "grade": 8, "text": "…"},
    {"code": "market", "label": "Market value", "grade": 5, "text": "…"},
    {"code": "plan", "label": "Team plan", "grade": 4, "text": "…"}
  ],
  "conflict": {"code": "plan_conflict", "text": "Moves away from your All-in plan — your rankings like it."},
  "order_note": "Cards are ordered so the side that gains less still gains. These grades are your side only."
}
```

- **Version.** The normalizer accepts the block only when `v === "logic-1"`, as it does for
  `fit-2` (`mobile/src/api/trades.ts:190-212`). Installed TestFlight builds drop the unknown
  key, so the server can ship first. A shape change needs a new `v`.
- **Prepared and stored pages.** `card_logic` joins `PUBLIC_FIELDS`
  (`prepared_trade_payload.py:42-47`).
- **Calibration.** Never shown there: `blind_grading.neutral_trade` (`backend/blind_grading.py:634`)
  stays neutral, or grades would bias the blind grade.

### 8.6 Text mock (All-in, card 8 of §3.1)

```
┌ HOW THIS CARD WAS BUILT ───────────────────────────────┐
│ Why you're seeing it                                    │
│  ✓ You rank [Player A] above his market value.          │
│  ✓ Within your fairness setting (75%).                  │
│  ✓ Their side gains too, by market value and roster.    │
│  ✓ Passes the deck checks.                              │
│                                                         │
│ Your side                                               │
│  Your rankings   ████████░░  8/10                       │
│   You value what you get more than what you send.       │
│  Market value    ██████░░░░  6/10                       │
│   Slightly in your favour at consensus value.           │
│  Team plan       ████░░░░░░  4/10                       │
│   Fit with your All-in plan, by age and position.       │
│                                                         │
│  ! Moves away from your All-in plan — your rankings     │
│    like it.                                             │
│                                                         │
│ Cards are ordered so the side that gains less still     │
│ gains. These grades are your side only.                 │
│ Estimates from consensus values and your rankings,      │
│ not a prediction.                                       │
└─────────────────────────────────────────────────────────┘
```

The "!" stands for a chalk warning glyph from the Chalkline set, not an emoji.

### 8.7 Analytics

- **Reuse** `help_opened` with `topic: "card_logic"`. `topic` is the HelpSheet key, documented
  as an enum ("matching | trade_pricing today", `backend/analytics_taxonomy.py:1710-1711`).
  Adding a value is an enum widening, with precedent at `:1699-1703` (`prompt_shown`). Record the widening in a
  short tracking-plan addendum, as the taxonomy asks.
- Joining an open to the card (which grades were seen) would need an `impression_id` prop.
  That is a new prop and needs the full addendum, plus `NON_INTENT_EVENTS` classification in
  the same commit (root `CLAUDE.md`).
- Defer it to the second slice.

---

## 9. Sequencing with rules-first and win-now

The win-now plan folder (`docs/plans/win-now-season-signal/` in the `win-now-plan` worktree)
did not exist at the time of writing. This section uses the operator's summary of it:
- a per-player season value over the receiving team's replacement;
- outlook-specific labels;
- plan-conflict cards pushed down, with the card saying so.

| Work | Order | Must not break |
|---|---|---|
| **Rules-first deck** | Independent; can land before or after. Grades are composed at serialization and never touch eligibility or order | Served-deck parity and "`admit=None` byte-identical" (`fast-deck-v2-design.md` §5.3). The "passes the deck checks" line is true by construction once rules-first is on; when neither rules-first nor quality filters are on, omit it |
| **Match strength fix** | Before or with rules-first. Under rules-first the deck is the whole admitted inventory (median 196), so `mismatch_score / 300` shows about 65 on the first card and turns red below about card 80 (**inferred** from `trade_gen_bilateral.py:527` and the 300 divisor). Today's fast deck would show 50 → 0 over 150 cards (`trade_first_page.py:1134`) | Web reads the raw number (`web/js/app.js:4152`); keep web unchanged or hide it there too |
| **Grades slice 1** (server, dark) | Can be built **in parallel now**, on revision 2 | Engine hash bump: one-time page and prepared regeneration. Pipeline version bump. Privacy tests |
| **Win-now season signal** | Independent of slice 1. **Its plan-conflict predicate must be one function**, recorded in the proof, that the demotion and the tooltip's conflict line both read. Implement the demotion as a subtractive penalty on viewer support (bounds stay admissible), not a sort class (breaks the page search's leading key, §5.3) | Page-search exactness (`test_trade_first_page.py`), served-deck parity, and Calibration pairing of the new revision |
| **Grades slice 2** (mobile sheet + conflict line + "This season" row) | After the win-now revision is selected, so the plan row's wording names what the engine actually uses. Until then the plan row says "by age and position" | `fit-2` and `logic-1` versioning. The composer keys its wording on `generator_version` so revision 2 cards keep the age wording |
| **User weights** | After R5's evidence | §5.5 |

---

## 10. Risks

- **Over-reading.** Users will average the three grades or treat them as acceptance odds.
  - Mitigations: the ordering sentence, "not a prediction", no overall grade, no colour
    verdicts.
  - Do **not** show the weights. The nominal 45/35/20 is not the realised influence (§1.6), so
    showing it would be its own inaccuracy.
- **Gaming.** The only lever is your own board, and moving it is the intended input. Inflating
  a player to see "10/10" changes your deck and teaches nothing to anyone else. Low risk.
- **Counterparty privacy.** Never show:
  - their preference component, support or uncertainty;
  - `weaker_support` / `total_support`, or which side set the order (it reveals the direction
    of their private lean);
  - their benefits or intent;
  - their declared outlook. The fit block's rule is the other team's roster read only
    (`docs/cross-client-invariants.md:637`).

  The their-side check must be the same text on every served card. Extend
  `test_fit_block_v3.py`'s privacy tests (`:447-470`, `:659-661`) to `card_logic`.
- **Copy and legal:**
  - **Pass / Like** vocabulary only. Never "accept/decline" (`cross-client-invariants.md:561-566`)
    and never "likely to accept".
  - Describe the trade, not people. No win/lose language (`docs/design/components.md:98`,
    legal R28.24).
  - Never describe a sell as "players you rate highly" (`cross-client-invariants.md:557-559`).
  - Templates are deterministic server copy with a pinned table, like `FIT_TEMPLATES`
    (`trade_narrative.py:410-421`). Marketing and legal review the strings before the
    sheet ships.
- **Truth drift.** The "Team plan" wording becomes false the day the win-now revision changes
  what plan means. Mitigation: key the wording on `generator_version`, and pin it in a test.
- **Analytics.** A new prop or event without an addendum is dropped silently at ingest
  (`cross-client-invariants.md:981`).

---

## 11. Open decisions for the operator

1. **Path:** the middle path (checks + three real grades, generation unchanged), A on its own,
   or B? *Recommendation: middle path.*
2. **Match strength on engine-built cards:** replace it with the "How this card was built" row,
   or keep the bar and feed it a real number? *Recommendation: replace.* The only real
   candidate number is the two-sided support, which leaks the other side's lean; today's bar is
   a deck position.
3. **Rankings scale:** use the rescaled preference grade (§4.2), or the engine's own component
   on 1–10 (honest, but nearly every card reads 5–6)? *Recommendation: the rescale, documented.*
4. **Plan conflict:** show the conflict line on the card's tooltip from the first slice
   (age-based plan), or only once the win-now revision lands? *Recommendation: with the win-now
   revision, using its one shared predicate.*
5. **User-set weights:** park until R5 shows whether hand weights survive, or schedule now?
   *Recommendation: park.*

---

## Appendix: how the measurements were run

- **Script.** Throwaway, outside the repository. It ran from this worktree with Python 3.12.
- **League.** `backend/eval/synthetic_league.build(seed, viewer_outlook=…)`:
  - 12 teams of 20 synthetic players plus 4 picks;
  - the viewer and 4 opponents carry noisy boards (lognormal 0.3 / 0.25);
  - fairness threshold 0.75;
  - viewer outlook passed in, so it reads as **declared** (`trade_gen_owner.py:297-298`).
- **Generation.** `trade_gen_bilateral_candidate.generate_bilateral_trades(**kwargs)`
  (revision 2), code-default knobs, then `trade_bilateral_presentment.present(cards)`, then
  `deck_quality.filter_deck` (assumed slots: QB, RB×2, WR×3, TE, FLEX).
- **Read.** Per served card, from `card.owner_evaluation.as_dict()`:
  - viewer components, support and intent;
  - counterparty support;
  - `mismatch_score`, and Match strength as the client computes it.
- **Board-lift check.** For every viewer player with a personal value, the ratio of personal to
  market value against whether `direction ≥ 0.025` (the gate threshold). Seed 7, 240 players.
- **Runtime.** About 7 s per run. Four runs: All-in and Contending on seed 7; Rebuilding and
  Not sure on seed 11.
