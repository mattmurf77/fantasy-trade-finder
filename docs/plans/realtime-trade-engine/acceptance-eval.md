# Acceptance evaluation of the bilateral support score (R5 pre-work)

**Date:** 2026-11-10 · **Tool:** `backend/eval/acceptance_eval.py` (`acceptance-eval-1`) ·
**Data:** production, read-only, every labelled impression up to 2026-11-10 ·
**Question owner:** [recommendation.md](recommendation.md) §4 R5

R5 proposes replacing the hand-weighted support score (0.45 preference fulfilment + 0.35
market acceptability + 0.20 team plan per side, ordered by the weaker side) with a fitted
P(viewer likes) × P(counterparty accepts). This document asks whether the outcomes already
logged can support that. All figures are aggregates. Cells under 5 observations are shown as
`<5`.

## Verdict

- **Neither head is estimable.** Every labelled bilateral card comes from **3 people**
  (2 once the tester allowlist is excluded). Grouped cross-validation over 2–3 users cannot
  say whether anything generalises to the next user. Both heads are `insufficient_data`.
- **There is no counterparty data.** Fewer than 5 counterparty responses exist across all
  bilateral cards, all time. The partner answered the same concept on 0.3–0.5% of cards. A counterparty
  head is not a modelling problem yet. It is a logging and product problem.
- **The support score does not predict the viewer's like within a user.** The pooled AUC of
  `weaker_support` looks useful at 0.68 with the tester included. Within each user it is
  **0.39**, and 0.28 without the tester. The pooled number comes from differences between
  users, not from ranking skill.
- **One consistent signal:** the viewer's own market gain. Within-user AUC is 0.58–0.61, and
  the group-bootstrap interval stays above 0.57 in both runs. Viewers like trades that favour
  them at market.
- **This is not evidence against the weaker-side ordering.** That ordering exists to trade
  some viewer appeal for counterparty acceptance. Viewer likes alone cannot score a mutual
  objective, and there are no counterparty labels to score the other half.
- **Recommendation: no shadow model now.** Start logging what is missing (§9). Re-run this
  tool once there are at least 10 distinct responding users on the bilateral arm and a real
  counterparty response channel.

## 1. Method

**Extraction** (`acceptance_eval.extract`) is label-first, to stay gentle on production:

1. Read the small label tables in full: `deck_outcomes` (2.3k rows), `trade_decisions`,
   `trade_matches`, `trade_proposals`, `suggestion_trade_links`, `trade_pass_reasons`.
2. Read only the impressions that carry a label from `deck_impressions`, by primary key, 200
   at a time. The proof fields are pulled server-side by JSON path (`valuation_json::jsonb
   #>> '{viewer,support,components,…}'`): about 40 scalars per card instead of the ~12 KB
   proof.
3. Look up any labelled id with no row in `deck_evidence_packs` (ADR-025,
   `"<run_id>:<card_index>"`) and unpack it with `evidence_pack.unpack_run`. A packed card
   carries only the compact block: it counts toward volume but has no support proof.
4. Count served volume in 3-day `COUNT(*)` windows over the `served_at` index.

**Labels.**

| Label | Positive | Negative | Population |
|---|---|---|---|
| `viewer_like` | like (deck outcome or decision) | pass / not interested | responded cards. Undone cards and like+pass conflicts are dropped |
| `viewer_strong` | propose, send, calculator opened, confirmed proposal, match, or exact executed trade | otherwise | responded cards |
| `counterparty` | partner liked their own impression of the same `trade_concept_id`, or decided `like` on it, accepted the match, or the trade executed exactly | partner passed the mirror or declined the match | cards where the partner did either |

**Baselines.** `weaker_support`, `total_support`, the product of the two sides' support, each
side's support, all six per-side components, market balance (−|viewer market-gain fraction|)
and each side's market gain. Each is scored three ways:

- **AUC**, with a 95% interval from a group bootstrap that resamples users (500 draws).
- **Within-user AUC**: only positive/negative pairs from the same user count, weighted by
  pairs.
- **As a probability**: a Platt map is fitted on the training users and applied to the
  held-out user, and the result is compared with the held-out base rate on log-loss and ECE.
  ECE uses `eval/calibration.py`.

**Fitted head.** An L2-regularised logistic regression on standardised features, fitted by
IRLS in pure stdlib (tested against known coefficients and the closed-form log odds ratio).

- **Viewer head features:** net preference, market-gain fraction, team-plan gain and need
  utility; viewer evidence known/partial; counterparty evidence unknown; multi-asset package;
  viewer and counterparty rebuilding outlook; log served position.
- **Counterparty head features:** the same set from the counterparty side.

Evaluation uses grouped cross-validation, by user and by league: leave-one-group-out when
there are 5 or fewer groups, 5 folds otherwise. The fitted head and the Platt-mapped
`weaker_support` are scored on the same held-out rows. Uncertainty comes from three sources:
per-fold spread, a group-bootstrap interval on the AUC difference, and per-fold coefficient
signs.

**Verdict rule.** A head is `insufficient_data` with fewer than 5 users or fewer than 10
minority-class labels. It is `mostly_prior` below 10 events per feature or below 10 users,
and `estimable` otherwise.

## 2. Exclusions

| Rule | Labelled rows removed |
|---|---|
| Demo league (`league_demo`) | 0 |
| `qa_` / `demo_` / `test_` stage users | 0 |
| Tester allowlist (`config/tester_allowlist.json`, 2 entries) | 480, all from 1 account (109 on the bilateral arm) |
| Calibration refresh decks, partner-redacted cards, partial runs, ghosts | 0 |
| Outcomes that join no impression row or pack | 0 |

The app is TestFlight-only, so every user is a tester in some sense. The tester allowlist
holds the operator's account. Excluding it leaves 2 people on the bilateral arm, so both
variants are reported:

- **primary:** allowlist excluded, as the brief specifies;
- **sensitivity:** allowlist kept (`--keep-allowlist`).

## 3. How much data there is (Q3)

**All arms, labelled impressions (primary / sensitivity).**

| | Primary | With tester |
|---|---|---|
| Labelled impressions | 695 | 1,175 |
| `viewer_like` labels (likes) | 645 (189) | 1,023 (340) |
| `viewer_strong` positives | `<5` | 6 |
| `counterparty` labels | `<5` | `<5` |
| Distinct users / leagues | 6 / 4 | 7 / 6 |
| Largest single user's share of like labels | 66% | 42% |

**By arm and version, `viewer_like` labels (with tester).** Arms differ in users and dates, so
these like rates are not comparable as arm quality.

| Arm / version | Labels | Like rate | Users (lower bound where two policy versions were merged) |
|---|---|---|---|
| `owner_v2_bilateral` / `owner-v2-bilateral-1` | 67 | 0.51 | 1 |
| `owner_v2_bilateral` / `owner-v2-bilateral-2` | 237 | 0.27 | 3 |
| `owner_v1` / `owner-only-v1` | 62 | 0.56 | 3 |
| Bake-off `current` (both policy versions) | 128 | 0.30 | ≥4 |
| Bake-off `challenger` (both policy versions) | 104 | 0.41 | ≥6 |
| Bake-off `gen_v2` (both policy versions) | 60 | 0.37 | ≥4 |
| Legacy, no arm stamped | 365 | 0.28 | ≥6 |
| `value_core` | 0 | — | — |

Notes on the volume:

- **Only `owner_v2_bilateral` carries the support proof**, on 330 labelled cards (221 in the
  primary run). The `owner_v1` proof has utilities but no support components. Legacy and
  bake-off rows have no bilateral proof.
- **Without the tester, every bilateral label is `owner-v2-bilateral-2` from October 2026.**
  No `value_core` card has a label.
- **By month (with tester):** 598 like labels in August, 200 in September, 225 in October,
  `<5` in November.
- **No response is the norm per row written, not per card seen.** The bilateral arm wrote
  ~179k non-ghost impression rows (316k with the tester) for 221 (330) viewed cards, because
  an owner job writes rows for its whole inventory. Of the cards actually viewed, 92–95%
  received a like or pass. So the bottleneck is how many cards users look at, not how often
  they answer.
- **Packed evidence:** 795 bilateral cards sit in packs, all on the tester account, with no
  labels. Every labelled card has a full row, because a card's first outcome upgrades it to a
  `viewed` row with its proof. No labelled card was missing a proof field.

**Power** (`analytics_stats.power_n_per_arm`, α .05, power .8; AUC via two independent
Hanley-McNeil SEs at the observed like rate). All figures are for the primary run, where the
like rate is 0.22 and `weaker_support` AUC 0.52.

| To detect | Labels needed | At 37 labels/week since the first one |
|---|---|---|
| A ranking with AUC 0.60 vs chance | ~770 | ~21 weeks |
| +0.05 AUC over the current score | ~3,070 | ~84 weeks |
| +0.10 AUC over the current score | ~770 | ~21 weeks |
| A 5 pp like-rate lift in an A/B, per arm | 1,177 | — |
| A 10 pp like-rate lift in an A/B, per arm | 313 | — |

Two caveats on the power table:

- **These figures assume independent labels.** Labels cluster by user, so the real
  requirement is larger by the design effect 1 + (m − 1)·ICC.
- **The binding constraint is people.** With m in the hundreds of labels per user, even a
  small intra-user correlation multiplies the requirement several times over. A grouped
  estimate needs at least 10 users before its fold spread means anything. Today there are 2–3.

## 4. Does the current score predict outcomes? (Q1)

**Viewer like, bilateral cards** (primary run: 209 labels, 47 likes, 2 users; with tester:
304 labels, 98 likes, 3 users).

| Score | AUC | Within-user AUC | CI95 (user bootstrap) | AUC, with tester | Within-user, with tester |
|---|---|---|---|---|---|
| `weaker_support` (the live key) | 0.52 | **0.28** | 0.26–0.55 | 0.68 | **0.39** |
| product of supports | 0.55 | 0.33 | 0.31–0.59 | 0.70 | 0.44 |
| total support | 0.55 | 0.32 | 0.31–0.60 | 0.70 | 0.44 |
| viewer support | 0.61 | 0.42 | 0.42–0.61 | 0.71 | 0.50 |
| counterparty support | 0.53 | 0.29 | 0.28–0.56 | 0.67 | 0.38 |
| viewer preference component | 0.47 | 0.38 | 0.38–0.47 | 0.57 | 0.38 |
| viewer market component = viewer market gain | **0.68** | **0.58** | 0.57–0.68 | 0.63 | **0.61** |
| viewer team-plan component | 0.51 | 0.56 | 0.51–0.57 | 0.48 | 0.51 |
| market balance (closeness to fair) | 0.33 | 0.40 | 0.33–0.42 | 0.26 | 0.38 |

Reading the table:

- **Each interval spans 2–3 resampled users.** Its endpoints are close to the individual
  users' own AUCs, so the intervals are wide and coarse. Treat them as a range of per-user
  results, not a confidence interval in the usual sense.
- **Calibration.** Mapped to a probability with a Platt fit on held-out users,
  `weaker_support` scores:

  | Run | Held-out log-loss | Base-rate log-loss | ECE |
  |---|---|---|---|
  | Primary | 0.97 | 0.93 | 0.24 |
  | With tester | 0.62 | 0.83 | 0.05 |

  In the primary run the map learned on one user points the wrong way for the other. With
  the tester included, the map is close to a constant at the base rate. Neither run shows a
  usable probability.
- **Stronger viewer signals** (send, propose, calculator, match, executed trade): `<5`
  positives on bilateral cards. Not estimable.
- **Counterparty response:** `<5` labels. Not estimable.

## 5. Would a fitted model do better? (Q2)

Viewer head, grouped by user (leave-one-user-out):

| | Primary (2 folds) | With tester (3 folds) |
|---|---|---|
| Fitted head, pooled held-out AUC / log-loss / ECE | 0.44 / 0.74 / 0.19 | 0.50 / 1.01 / 0.30 |
| Baseline (`weaker_support`, Platt), same rows | 0.20 / 0.97 / 0.24 | 0.62 / 0.62 / 0.05 |
| Fitted head, per-fold AUC (min–max) | 0.50–0.54 | 0.55–0.67 |
| Baseline, per-fold AUC (min–max) | 0.26–0.45 | 0.26–0.64 |
| AUC difference, CI95 (user bootstrap) | +0.09 to +0.24 | −0.15 to +0.16 |

Reading the table:

- **Grouping by league gives the same answer.** In the primary run each user is in one
  league, so the folds are the same. With the tester, the four league folds are worse for
  both models, with the AUC difference spanning −0.29 to +0.24.
- **No evidence either way.** The fitted head generalises to a new user at or near chance.
  In the primary run it beats a baseline that is itself below chance, which is not a win.
- **Calibration of the fitted head is poor** (ECE 0.19–0.30). Its predictions spread wider
  than the outcomes do.

**Coefficients** (standardised, full fit, with the share of folds that agree on the sign):

| Feature | Primary | With tester |
|---|---|---|
| viewer market-gain fraction | **+0.69 (2/2)** | **+0.86 (3/3)** |
| viewer evidence known | +0.26 (2/2) | +0.31 (3/3) |
| counterparty evidence unknown | −0.17 (1/2) | −0.43 (3/3) |
| log served position | −0.27 (2/2) | −0.11 (2/3) |
| multi-asset package | +0.28 (2/2) | +0.14 (2/3) |
| viewer net preference | −0.02 (1/2) | +0.38 (2/3) |
| viewer team-plan gain | −0.35 (1/2) | +0.52 (2/3) |
| viewer need utility | +0.66 (1/2) | +0.13 (2/3) |

Reading the coefficients:

- **Monotonicity holds.** The coefficient on the viewer's own market gain is positive in every
  fold, so acceptance never falls as that side's market gain rises.
- **The preference and team-plan coefficients are unstable.** They flip sign across folds.
- **The counterparty-head monotonicity check could not run**: there are no labels for it.

## 6. The specific proposals (Q4)

- **Endowment, counterparty side: insufficient data.** It needs counterparty responses, and
  there are `<5`.
- **Endowment, viewer side: suggestive only.** Among bilateral passes with a pass reason, all
  but `<5` came from the tester account.
  - In 10 of 10 reasoned passes where the market said the viewer **gains**, the reason was
    "giving too much value" (`value_giving`).
  - Where the viewer pays at market: 28 of 29.

  A manager who rejects a market-favourable trade as overpaying values their own assets above
  market. That is consistent with endowment, but equally with their personal board
  disagreeing with consensus. It is one person's behaviour. It does say the endowment premium
  in R6 would be testable on the viewer side once pass reasons come from more than one
  account.
- **Unknown-board counterparties.** Viewers liked cards against a counterparty with no board
  much less often:

  | Counterparty board | Like rate (primary) | Like rate (with tester) | Cards (primary / with tester) |
  |---|---|---|---|
  | Unknown | 0.17 | 0.23 | 171 / 229 |
  | Known | 0.46 | 0.59 | 24 / 44 |
  | Partial | 0.50 | 0.65 | 14 / 31 |

  The fitted head keeps the sign under user CV with the tester (3/3 folds), but only 1/2 in
  the primary run. Unknown boards are 80% of cards and are spread unevenly across users and
  leagues, so this may be a league effect. How the counterparty responds by board state:
  insufficient data.
- **Ordering keys** (`max(min support)` vs product vs total vs market balance):
  - On viewer likes, within users, none of the support aggregates beats chance. Product and
    total are slightly less bad than the minimum (0.33 and 0.32 vs 0.28 primary; 0.44 vs 0.39
    with tester).
  - Market balance ranks **inversely** (0.26–0.40): balanced trades are liked less than
    trades that favour the viewer.
  - None of this can rank the aggregators for the mutual objective R5 is about, which needs
    the counterparty half.
- **Rank bias.** Like rate falls with served position:

  | Position | 0–4 | 5–9 | 10–29 | 30+ |
  |---|---|---|---|---|
  | Like rate, primary | 0.31 | 0.27 | 0.22 | 0.16 |
  | Like rate, with tester | 0.42 | 0.44 | 0.29 | 0.16 |

  The score does not order likes within users, so at least part of this is position or
  fatigue rather than better cards on top. The log-position coefficient is negative in
  2/2 folds (primary) and 2/3 (with tester).

## 7. Relation to `value_model.py`

`value_model.py` (F6, flag `deck.value_model`, dark) is the existing learned acceptance head:

- **Heads:** P(like) and P(propose | like).
- **Fit:** plain-Python logistic regression with grouped L2 and a Platt map fitted on a
  held-out time slice.
- **Position:** used only at training time, as a debiasing feature.
- **Features:** the compact card block (values, surplus, fairness, shape, positions, taste,
  partner like rate).

Its training gate is 30 like rows with 5 positives, far below anything here. At today's
volume it would train, but it would be "mostly prior" for the same reasons.

R5's viewer head is the same machinery with the bilateral components added as features. The
cheapest route, once the data exists, is to extend `extract_features` and `COMPACT_KEYS`
rather than build a second learner. Its propose head has the same problem as this
`viewer_strong` label: `<5` positives on the bilateral arm.

## 8. Limitations

- **Selection bias, uncorrected.** Users only answered cards the live engine chose to show,
  in the order it chose. On every bilateral row `propensity` is 1.0: the order is
  deterministic and the column is an ordering multiplier, not a probability. There is no
  logged randomisation of which cards were shown or where, so inverse-propensity correction
  is not possible and was not attempted. The ghost holdout randomises withholding for
  executed-trade incrementality, not position or selection for responses.
- **People, not rows.** 2–3 users dominate every estimate. The pooled vs within-user gap in
  §4 shows the pooled statistics are confounded by user. Generator version (bilateral-1 vs
  -2), month and league are also all confounded with user.
- **Viewed is a client event** (`deck.signal_v2`). The response share of viewed cards is
  reliable. "Never responded" per row written is not a meaningful denominator.
- **Positions are `card_index`**, not adjusted for never-delivered withdrawals as
  `eval/data.py` does. On packed decks this could shift a few positions. No labelled card
  came from a packed deck.
- **The mirror lookup reads only the partner's labelled impressions.** A partner who was
  served the concept and never answered is invisible, and was not scanned for: that would
  mean reading a heavy user's whole inventory.
- **Distinct user and league counts are reported exactly.** They fall under the 5-cell rule,
  but every verdict rests on them and a count of people identifies no one.

## 9. Recommendation

1. **No shadow model now.** Neither head is estimable, and a shadow score would be
   unevaluable for the same reason.
2. **Re-run `acceptance_eval` when there are at least 10 distinct responding users on the
   bilateral arm**, ideally 20, each with 30 or more like/pass labels.
   - Below 10 users, grouped CV cannot separate a model from a user.
   - Minority-class labels should reach about 10 per feature: roughly 110 likes for the
     11-feature viewer head. The primary run has 47.
   - A shadow viewer head is warranted when the fitted head beats `weaker_support` on
     **within-user** held-out AUC with a group-bootstrap interval above zero.
3. **Do not plan the counterparty head until a counterparty response channel exists.** Today
   a partner answers the same concept on 0.3–0.5% of cards. At that rate, ~110 counterparty
   positives would need tens of thousands of viewed cards.
4. **Log what is missing**, in this order:
   - **Provider outcomes of sent trades** (accepted / rejected / expired / countered).
     `trade_proposals` has **0 rows** in production, and `sleeper_trades` stores only
     completed trades. This is the only realistic source of counterparty labels.
   - **Counterparty exposure.** When a partner opens the mirror or the likes-you card, log the
     view even with no answer, so "never shown" and "shown and ignored" can be told apart.
   - **Logged exploration.** A small, logged random perturbation of order within the first
     page (with its probability in `propensity` or the owner experiment JSON) would make
     position bias and IPS correction estimable.
   - **The per-side support components in the compact block** (`eval/contract.py`
     COMPACT_KEYS and the pack writer): weaker/total support and the six components. Packed
     unseen cards currently lose them, so the ordering cannot be replayed over a full deck.
   - **Pass reasons from more than one account.** They are the only direct viewer-side
     endowment signal.

## Reproduce

```bash
python -m backend.eval.acceptance_eval --production --secrets <path>/secrets.local.env \
    --until 2026-11-10 [--keep-allowlist] --out report.json --markdown report.md
python -m pytest backend/tests/test_acceptance_eval.py -q
```

The `--extract` row file is refused inside the repository. Group keys in it are salted
hashes.
