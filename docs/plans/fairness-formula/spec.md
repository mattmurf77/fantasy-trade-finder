# Fairness formula — spec

> **Status (2026-11-15): measured, not adopted, code not merged.** No arm passed the rule, so the engine change (flag `trade.fairness_formula_v2`, `backend/fairness_formula.py`, the replay tool and its tests) was left out of `main`. It is kept on branch `feat/fairness-formula` (head 1ac1b027) for reference. Only this record is on `main` (D-267).

Date: 2026-11-15. Owner: operator. Status: approved to build and measure behind a flag.

## Problem

The trade deck admits a card when the smaller side's package value is at least a threshold share
of the larger side's. "Package value" today is the app's market package math: per-asset values on
the app's scale, a discount on the lesser pieces of a multi-asset side, and an elite credit
(`backend/trade_service.py`, `_package_value` in `market` mode).

Two results lead here:

1. **Widening the window did not help** (`docs/plans/fairness-window/results.md`, D-266). At any
   threshold from 0.75 to 0.65 a trade close to the real one is in the first 30 cards for about
   7% of real in-season trades and anywhere in the deck for about 42–45%.
2. **A different formula separated real trades from made-up ones better** in the Sleeper
   trade-universe research (aggregates only). Scoring each side as a plain sum of each asset's
   value raised to the power 0.7, with no package discount, told real trades from matched
   alternatives better than the app's scale (held-back data: 0.634 against 0.607, where 0.5 is a
   coin flip; the compression alone was worth +0.012, range 0.009–0.014). Known cost in that
   research: 1-for-1 trades involving a pick passed 0.75 only 30% of the time against 50% today,
   because the app's current scale pads low pick values.

That research scored trades that already happened. It did not show that the generator, using
the formula, puts a trade like the real one on the first page more often. This spec makes the
build answer that before anything changes for users.

## Goal

Find out, by the replay measurement, whether swapping the deck's admission formula for a
compressed sum surfaces trades close to the ones managers really made more often in the first
30 cards, without slowing the deck or losing pick trades.

## What to build

1. **A selectable fairness formula in the generator.** Behind flag `trade.fairness_formula_v2`
   (match the repo's naming if a convention differs). Off: every surface is byte-identical to
   `main`. On: the deck generator's admission ratio uses the configured formula. Default False in
   `backend/feature_flags.py`, false in `config/features.json` and in the three flag fixtures.
   Do not add it to `FTF_FLAGS`. The operator turns it on.
   - Formula knobs live in model config with defaults that reproduce today's math.
   - Scope is the deck generator's admission and ordering inputs that read the package ratio.
     Out of scope: calculator and evaluate verdicts, the consensus "balanced" note, the swap
     sheet, the fatigue and win-now paths, `market_floor_absolute` (stays 0.65 and is applied to
     the ratio of whichever formula is active).
   - The existing stud-tax mode `off` already returns a plain sum; reuse what exists before
     adding a parallel path.
2. **Arms in the replay tool.** Extend `backend/eval/fairness_window_replay.py` (or add a
   sibling that shares its code) so one run scores several formula-and-threshold arms on the same
   trades, each paired against today's arm.
3. **Decide by a rule fixed in advance** (below). Write the exact definition of every arm into
   this spec's technical design section **before** running anything on real data.

## Arms (fixed)

`v` is an asset's value on the app's current per-asset scale (the 50% KeepTradeCut blend the app
already uses, tight-end uplift included). "Raw" means before the app's linear map adds its
constant.

| Arm | Side value | Threshold | What it isolates |
|---|---|---|---|
| T (today) | market package math | 0.75 | baseline |
| A | Σ v^0.7 | 0.75 | the research formula on the app's values |
| B | Σ v^0.7 | 0.817 (= 0.75^0.7) | same window as today for 1-for-1 trades, so only package treatment differs |
| C | Σ v (plain sum, no discount) | 0.75 | dropping the package discount without compression |
| D | Σ raw^0.7 | 0.75 | the research formula as tested (no padding of low values) |

If the code shows an arm cannot be built as written (for example the generator never sees raw
values), say so in the technical design, build the nearest faithful version, and name the
difference. Do not add arms after seeing results; anything extra is exploratory and labelled so.

## Measurement

Same method as the fairness-window replay unless stated:

- Sample: research `analysis.sqlite`, split `train`, folds 0–2, `season_phase = in_season`,
  unflagged, the same population rule. **1,200 trades**, seed 20261115. Never the held-back file.
- Primary measure: share of trades with a close match in the first 30 cards. "Close" = same
  partner and matched value ÷ union value ≥ 0.5, **scored on one fixed value scale for every
  arm** (the one the fairness-window replay used), so an arm cannot win by changing how matches
  are counted.
- Gain over arm T is paired per trade; 95% interval by percentile bootstrap over whole lineages,
  2,000 draws, seed 20261115.
- Also report per arm: close match anywhere in the deck, exact match in first 30, deck size,
  share of first-30 cards under 0.75 on today's formula, median build-time ratio against T, and
  the primary measure split into trades that involve a pick and trades that do not.

## Rule

An arm **passes** only if all hold:

1. Gain over T on the primary measure has a 95% interval that excludes zero on the positive side.
2. Median build-time ratio ≤ 1.10.
3. On trades involving a pick, its gain over T does not have an interval entirely below zero.

Among passing arms, the highest primary estimate is the one recorded as the configured formula;
equal estimates go to the arm closest to today (order T, C, B, A, D). If none passes, the knobs
stay at today's math, the flag ships off with no behaviour change available, and the PR says so
plainly.

Passing here is not a decision to turn the flag on. A passing arm is then confirmed once on the
held-back trades by the main session (the builder leaves a command that takes the database path
as an argument and never runs it on the held-back file).

## Acceptance

- Flag off: byte-for-byte the same decks as `main` on the existing deck fixtures (a test proves
  it), with the knobs at any value.
- Flag on with default knobs: byte-identical to flag off.
- Each arm's side-value function has a direct unit test with hand-computed numbers.
- The replay table for all arms is in the PR and in `docs/plans/fairness-formula/results.md`
  (aggregates only: no league, roster, transaction or owner ids; no cell under 20 trades or 10
  leagues).
- New tests are sabotage-checked. Repo feature gates and living-memory write-back are complete.
- `docs/plans/fairness-window/scope.md`: record that the operator signed off the §1 analytics
  waiver on 2026-11-15 (PR #691 was merged on that sign-off).

## Data rules (binding)

`data/sleeper-universe/` is local, git-ignored research data. Read
`data/sleeper-universe/analysis/RULES.md` "Hard limits" and follow them: no network, never open
`holdout.sqlite` or `holdout-results/`, aggregates only in anything committed, scripts that read
the data stay under `data/sleeper-universe/analysis/fairness-formula/`.

## Not in this change

- Changing the KeepTradeCut weight (the research found no reliable gain from it).
- A production adjustment (more for current production), per-segment weights, deck re-ordering.
- Changing `market_floor_absolute`.
- Turning the flag on.

## Technical design

Builder, 2026-11-15. Written before any code change and before any real-data run.

### Where the deck admits a card today

- Every deck generator (`trade_gen_owner`, bilateral r1 `trade_gen_bilateral`, r2
  `trade_gen_bilateral_candidate`, outlook evidence, r4 `trade_gen_bilateral_r4`, r5
  `trade_gen_bilateral_season`) inherits `trade_gen_owner._Search`. Its `evaluate` prices the
  pair once with `_package(give, receive, self.market)` → `trade_service.price_consensus_package`
  (market stud-tax mode) and refuses the card when `ratio < self.floor`, where
  `self.floor = max(requested threshold, market_floor_absolute)`.
- The proof's `market` block (`give`, `receive`, `ratio`) becomes `card.give_value`,
  `card.receive_value`, `card.fairness_score`, and `OwnerDecisionContext.matches` re-checks those
  three numbers at every serving stage.
- Ordering inputs that read the ratio: `card.fairness_score` (the plain owner generator's sort
  key, and the number the card shows). The bilateral support components read package side values,
  not the ratio, and their tolerance reads `self.floor`; they are not changed (see Scope).
- `self.market[pid]` is `age_pref_value(elo_to_value(seed_elo[pid]))`. In production the seed is
  `seed_elo_for_value(blended value)` (50% KeepTradeCut blend, TE uplift in sf_tep), and with the
  default curve `elo_to_value(seed)` = `SEED_VALUE_FLOOR + value × (CEIL − FLOOR) / 10000`. The
  linear map's constant is `data_loader.SEED_VALUE_FLOOR` (≈ 223 value points).

### The change

- New module `backend/fairness_formula.py` (house pattern of `fairness_window.py`). Flag
  `trade.fairness_formula_v2`: default False in `feature_flags.py`, false in `config/features.json`
  and the three fixtures, not in `FTF_FLAGS`.
- Four model_config knobs, seeded in `database._MODEL_CONFIG_DEFAULTS`, defaults = today's math:

  | Knob | Default | Meaning |
  |---|---|---|
  | `fairness_formula_package_math` | 1.0 | 1 = today's market package math (other knobs except the threshold power are ignored); 0 = plain per-asset sum |
  | `fairness_formula_exponent` | 1.0 | each asset's value is raised to this power before summing; allowed (0, 1] |
  | `fairness_formula_raw` | 0.0 | 1 = use the raw value (the linear map's constant removed), 0 = the app's value |
  | `fairness_formula_threshold_power` | 1.0 | the requested threshold is raised to this power; allowed (0, 1] |

  Any missing, non-finite, out-of-range or boolean value falls back to its default.
- `_Search.__init__` resolves `self.formula = fairness_formula.active(self.config)`: `None` when
  the flag is off (the knobs are not read) or every knob is at its default. `self.formula is None`
  ⇒ the code path is exactly today's.
- When a formula is active, `evaluate` keeps today's pricing call (for the overpay gate and the
  shown side values) and adds:
  - side value `S(ids)`: package math ⇒ today's package value; otherwise
    `Σ f(pid) ** exponent`, with `f = self.market[pid]`, or, with `raw = 1`,
    `f = age_pref_value(max(elo_to_value(seed) − SEED_VALUE_FLOOR, 0), player)` (the app's own
    per-asset value without the map's constant, the age preference kept);
  - `ratio = min(S_give, S_recv) / max(S_give, S_recv)`; a side at 0 ⇒ `invalid_market_value`;
  - admission floor `max(requested ** threshold_power, market_floor_absolute)` (0.65 unchanged and
    applied to the active formula's ratio);
  - the proof's `market.ratio` (hence `card.fairness_score`) is the formula ratio; `market.give` /
    `market.receive` stay today's package values; a `market.formula` block records the knobs, both
    formula side values, the formula floor and today's package ratio.
- A thread-local `fairness_formula.override(knobs)` pins a formula for offline tools (the replay)
  regardless of the flag, like `stud_tax_override`. Production never calls it.
- Scope kept out, as the spec says: calculator / evaluate verdicts, the consensus note, swap sheet,
  fatigue and win-now paths, `market_floor_absolute`. Also unchanged: the overpay ceiling
  (`overpay_ok`, an absolute gap on today's math), the bilateral support components and their
  tolerance, and the serving policy layer (`trade_policy.evaluate_trade_policy`), which prices on
  today's math. **Before the flag is turned on**, someone must decide whether that serving layer
  follows the formula; otherwise a card admitted on the formula but under the policy floor on
  today's math is dropped there. The replay reports how many first-30 cards are under 0.75 on
  today's math, which bounds this.

### Arm definitions (fixed before any real-data run)

| Arm | Knobs (package_math, exponent, raw, threshold_power) | Requested threshold | Effective floor |
|---|---|---|---|
| T | flag path off (`override(None)`) | 0.75 | max(0.75, 0.65) |
| A | (0, 0.7, 0, 1) | 0.75 | 0.75 |
| B | (0, 0.7, 0, 0.7) | 0.75 | 0.75 ** 0.7 = 0.8176 |
| C | (0, 1.0, 0, 1) | 0.75 | 0.75 |
| D | (0, 0.7, 1, 1) | 0.75 | 0.75 |

Differences from the spec's wording, named:

- **v in the replay is DynastyProcess-only.** The research cases carry dated DynastyProcess values,
  not the app's live KeepTradeCut blend, and no league is TE-premium, so the TE uplift never
  applies. This is the same limit the fairness-window replay had. In production the knobs act on
  the blended value.
- **v includes the app's age preference** (×1.10 under 23, capped +500; ×0.90 at 30+), because
  that is the generator's per-asset value. Arm D keeps the age preference and removes only the
  linear map's constant.
- **"Raw" is recovered, not read.** The generator sees only a seed Elo per asset; the raw value is
  `elo_to_value(seed) − SEED_VALUE_FLOOR`, exact under the default curve constants (the replay's
  case) and proportional to the input value scale.

### Replay (fixed before any real-data run)

- New sibling `backend/eval/fairness_formula_replay.py`, sharing the case format, `_inputs`,
  `match_card`, `_boot` and `load_engine` of `fairness_window_replay.py`. Per case, all five arms
  are built in the same process in the order T, A, B, C, D with `generate_bilateral_trades` (r4,
  as before), each arm inside `fairness_formula.override(...)`.
- Matching uses the case's own values (the fairness-window scale) for every arm.
- Per arm: close-match rank, exact-match rank, deck size, build seconds, first-30 count, and
  first-30 cards whose ratio on **today's** math (`min(give_value, receive_value) / max(...)`,
  the unchanged market side values) is under 0.75.
- "Involves a pick" = the real trade moves at least one pick (a token starting `P:`).
- Summary per arm: close in first 30 (primary), paired gain vs T, close anywhere, exact in first
  30, median deck size, share of first-30 under 0.75 on today's math (ratio of sums), median
  build-time ratio vs T (median over trades of arm seconds ÷ T seconds), and the primary measure and
  its paired gain on pick and no-pick trades. Intervals: percentile bootstrap over whole lineages,
  2,000 draws, seed 20261115.
- Rule (`select`): pass ⇔ gain 95% lower bound > 0 **and** median time ratio ≤ 1.10 **and** the
  pick-trade gain's 95% upper bound ≥ 0. Highest primary estimate wins; ties go to the first in
  order C, B, A, D. None ⇒ knobs stay at today's math.
- Sample: `analysis.sqlite`, split `train`, folds 0–2, `season_phase = in_season`, `any_flag = 0`,
  the M2 population rule (`rosterlib.eligible`), 1,200 drawn with seed 20261115, built by the same
  extractor as the fairness-window replay (rosters and dated values read read-only from the
  research store and values file, exactly as that extractor did). Never the held-back file.
- Confirmation command for the main session (never run by the builder on the held-back file):
  documented in results.md; it takes the database path as an argument.
