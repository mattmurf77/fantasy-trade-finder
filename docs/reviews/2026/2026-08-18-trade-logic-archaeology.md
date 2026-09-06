# Trade-logic archaeology — where was the engine when it was good?

**Date:** 2026-08-18
**Scope:** read-only. No branch, no code change, no engine edit. Git reads against `origin/main`; prod reads `SELECT` only under `SET TRANSACTION READ ONLY`.
**Question (operator's words):** *"There was a state of the trade logic (only about a week old) that genuinely did a great job at identifying trade options by just focusing on rank/value diffs between two users."*
**Second operator input:** *"It wasn't a more accurate rank set. My rankings have remained relatively unchanged."*
**Why it matters:** `docs/plans/three-model-bakeoff/PLAN.md` pins arm A to SHA `92c31d5` via `backend/bakeoff_profiles.MODEL_A_PROFILE`. If the remembered state is earlier, arm A is anchored on a version nobody rated highly.

---

## 1. Verdict and recommendation

### Recommendation: **keep arm A pinned at `92c31d5`. Do not re-pin earlier.**

This is a negative result, and it is the honest one. I went looking for an earlier, better SHA, built a specific hypothesis about what changed, and **the production telemetry contradicted it.** Details in §4; the correction is recorded rather than quietly dropped.

**Confidence: medium-high** that re-pinning earlier would achieve nothing useful. **High** that the two candidate flags I would have added to the profile (`trade.pool_calibration`, `trade.divergence_fallback`) should *not* be added — they fixed a real, total defect (see the 0% divergence measurement below), and disabling them would reproduce a bug, not a golden age.

### The single most decisive piece of evidence

**The share of served cards containing a draft pick more than quadrupled across the window, and the rise begins exactly where the operator's "good week" ends.**

| Day | Pick share of served cards |
|---|---|
| 2026-08-08 | **14.3%** |
| through 08-10 | 14–32% |
| 2026-08-11 | **38.3%** |
| 2026-08-15 | **54.7%** |
| 2026-08-17 | 58.4% |
| 2026-08-18 | **64.4%** |

*(n = 7,649 impressions; `deck_impressions.features_json->>'involves_pick'`, populated for every row.)*

This is corroborated independently and blind: the `feat/engine-pick-and-diversity` scope block (`60cbe11`, 2026-08-18) diagnosed the *same* corpus and recorded the operator's own words — **"the random insertion of picks when a trade would be fair without them is by far the most nonsensical behavior"** — measuring 63% pick involvement. Two independent reads of the corpus agree, and the metric moves monotonically in the direction of the complaint, starting in the operator's window.

**Why this matters for the bake-off, and why it argues for keeping the current pin:** the fixes for exactly this defect (`rank_div_min_frac`, `pick_pair_strip_frac`, `min_package_band`) are among the nine knobs `MODEL_A_PROFILE` sets to `0.0`. So **arm A already reproduces the pick-spam state and arm B already carries the fix.** The bake-off as currently pinned measures the right axis. Moving the pin earlier would not improve that and would cost the golden test.

### Three findings, ranked by how much they move the answer

| # | Finding | Confidence |
|---|---|---|
| **1** | **The trade generator was byte-identical for six days, 2026-08-09 → 2026-08-15.** `git diff ee91334 19d4174^ -- backend/trade_service.py backend/trade_optimizer.py` is **empty**. "About a week ago" lands inside a genuine, verifiable plateau — there *is* a real state to point at, and its boundary SHA is `6158e65`. | **High — verified by diff** |
| **2** | **The premise of the question is contradicted by the data.** During the remembered week the engine was **not** "focusing on rank/value diffs between two users." On 2026-08-08 it served **zero** divergence-basis cards (100% consensus); on 08-11, 16.3% divergence. Divergence share then **rose** to 29–36% after 2026-08-15. Meanwhile divergence cards are liked at **13.3%** vs consensus at **33.2%**. The deck moved *toward* two-board divergence as it got worse. | **High on the numbers; medium on interpretation** |
| **3** | **The telemetry cannot adjudicate "which period produced better user response."** Across 2026-08-08 → 08-15 there are **~41 decisive outcomes total over 8 days** (several days zero), against **231 on 2026-08-17 alone**. Five distinct users, six leagues, database-wide. This is operator/internal usage, not user response. | **High — stated as a clean negative** |

### (a) code regression / (b) value drift / (c) both?

**(c) — both, but neither in the shape originally hypothesised, and the value half is now *dated*.**

- **Code/config half:** real, and it is the **pick-pricing wave (2026-08-06 → 08-08)**, not G6 and not the fairness gate. `trade.slot_pricing` ON (08-06), `picks.assign_tradeable` ON (08-08), "asserted picks priced across all seven read sites" (`7150178`, 08-08), "pick value in every view" (`6c304c7`, 08-10). Picks became fully-priced, fully-injected pool assets — and per `60cbe11`'s diagnosis, a pick **carries zero board divergence but still raises the fairness term**, so it is "free fairness" that nothing penalises. Pick share tracks that rollout with a short lag. *(Confidence: medium-high — the correlation is strong and the mechanism is proven in code, but I did not run a counterfactual.)*
- **Value-drift half:** real, and it steps on two specific dates.
  - **2026-08-16 — consensus-seed discontinuity.** Mean |Δ Elo| against the 08-08 baseline for the top-50 `1qb_ppr` players: 0.52 (08-09) → 2.18 (08-12) → 3.76 (08-15) → **14.37 (08-16)**, max |Δ| 119.7, **8 of the top 50 moved more than 5 ranks**. Gentle drift for a week, then a jump.
  - **2026-08-17 — the operator's personal board was rewritten.** **725 ranking comparisons in one day.** Players carrying any personal signal went **53 → 126 (2.4×)**; players where personal value dominates (`w ≥ 0.5`) went **18 → 63 (3.5×)**. All 644 `member_rankings` rows for that user/format carry `updated_at = 2026-08-17`; `elo_history` shows 16,920 rows that day.

**The operator's report that "my rankings have remained relatively unchanged" is true about rank *order* and false about *how much of the board now carries personal signal*.** That is the reconciliation. The mean shrinkage weight barely moved (0.437 → 0.481) — so the *w*-drift mechanism I was asked to test is **weaker than hypothesised**. What actually changed is **coverage**: 2.4× as many players stopped being priced at consensus and started being priced personally, in a single day. Since `mismatch` (70% of the composite) *is* board divergence, that alone reshapes which trades surface — with no code change.

### What to do instead of re-pinning

1. **Keep `MODEL_A_REFERENCE_SHA = 92c31d5`.** The golden test is sound and the profile already isolates the pick-spam axis.
2. **Record `fairness_threshold` on every impression.** It is currently **persisted nowhere** — not a column, not a `features_json` key (all 28 enumerated). Nobody can tell what gate produced any historical deck, which is why §4 below has an unresolvable ambiguity. Fix this before Phase 5, and set it explicitly per arm rather than inheriting whatever the client sent.
3. **Fix `policy_version`.** It is NULL for every row before 2026-08-16 and has exactly **one** non-null value ever (`v3+ts.ts2.div.fat.rr.taste.expl.fs.ghost@r1`). It cannot distinguish engine states today. PLAN.md §5 proposes extending it to encode the arm — that is necessary, not optional.
4. **Chase the basis result, carefully.** Consensus 33.2% like vs divergence 13.3% (n = 217 / 173) is the most interesting number in the corpus and points the opposite way from the engine's design intent. It is confounded (all from 08-16/17, ~4 people) and must not drive an engine change on its own — but it is exactly what a properly-instrumented bake-off can settle.

---

## 2. Timeline — every trade-suggestion change, 2026-08-08 → 2026-08-18

Reversibility: **knob** = deploy-free `PUT /api/admin/config/<key>`; **flag** = `config/features.json`, deploy-free; **client** = ships in the app binary; **hard** = code revert.

| Date | SHA | What changed | Reaches generation? | Reversible? |
|---|---|---|---|---|
| 08-06 | `966ac0f` | `trade.slot_pricing` **ON** — market slot pricing for picks in the trade engine | **Yes — pick prices** | flag |
| 08-08 | `faf015a`, `e2d0e9e`, `7150178` | `picks.assign` + `picks.assign_tradeable` **ON**; asserted picks priced across all seven read sites | **Yes — pick supply into pools** | flag |
| 08-08 | `2d7b41c` | #172 intent modes, flag `trades.intent_modes` **ON** | Post-generation filter, user-selected | flag |
| 08-08 | `f800b7c` | #257 full-height edit sheet | No — UI | flag |
| 08-09 | `b09b96c` / `29a25c0` / `ee91334` | #269/#276 sheet targeting; #169 position-impact fold-in; #286 two-piece sweetener widening (asset-ideas surface, **not the deck**) | Indirect / presentation | flag |
| 08-10 | `6c304c7` | v1.12.0 — "pick value in every view" | Presentation, but completes the pick rollout | client |
| **08-09 → 08-15** | — | **`trade_service.py` and `trade_optimizer.py` byte-identical. The plateau.** | — | — |
| 08-10 | `e9ad9c9` | DP name map for historical board joins | Marginal | hard |
| 08-11 | `3af201a`, `fd170aa`, `204341f` | Send-in-MFL ON; unlock semantics; tier-board route security | No | flag / hard |
| 08-12 | `5139b45` | #300 position-scoped candidates (League screen) | No — separate surface | flag |
| 08-13/14 | `2b63511`, `7057d86`, `e71a654`, `9910ae6` | Notification inbox; feedback wave; mock draft; deck-outcome ownership validation | No / telemetry only | flag / hard |
| **08-15 13:20** | **`6158e65`** | **← last commit carrying the plateau engine** | — | — |
| **08-15 14:20** | **`19d4174`** | **Compressed-board fixes. `trade.pool_calibration` (v3 pool prune rescales the opponent's value space before differencing) + `trade.divergence_fallback` (a boarded member with zero divergence cards falls back to the consensus generator). Both born `true`, by explicit operator instruction.** | **Yes — directly** | **flag** |
| 08-15 19:24 | `34ebd84` | #313 — 1QB QB consensus values compressed so no QB prices above one 1st. Knobs `qb_1qb_cap_elo` (1785) / `qb_1qb_cap_knee_elo` (1580) | **Yes — changes the seed everyone reads** | knob, **process-global** (§5) |
| 08-15 20:35 | `73c78fc` | likes-you injection gains a user-gain floor (`likes_you_min_user_delta` = −500), D-055 | Yes — deck injection | knob, **not thread-local** (§5) |
| 08-15 22:28 | `6f293f4` | Fit-congruence: deck-swipe Elo K scaled by how surprising the swipe is (`fit_k_explained_mult` 0.4) | **Write path** — changes boards going forward | knob; **stored effect irreversible** |
| 08-16 11:27–11:28 | `1ba148c`, `a10c201` | Suggestion telemetry (lit same day, `3c0541c`); `trade_gen_v2.py` behind `trade_gen.v2` = **false**, **dark to this day** | Logging / none | flag |
| **08-16 21:03** | **`92c31d5`** | **← current arm-A reference SHA (docs-only commit; `20b40db^` on first-parent)** | — | — |
| **08-16 (in `20b40db`)** | **`e10f93e`** | **G6 presentment rules R1–R5, flag `trade.presentment_rules` born ON. R1 overpay ceiling, R2 per-position net cap, R3 pick-is-the-gap band, R4 windowless exclusion (no knob), R5 need gate.** | **Yes** | knob ×4 + flag (R4) — **what `MODEL_A_PROFILE` kills** |
| **08-17 18:22** | **`c95a70a`** | Decline-reason capture. Elo suppression: only `value_giving` passes still write pass-Elo. Flag `feedback.decline_reasons` true for all | Yes — changes what swipes teach | knob + flag |
| **08-17 18:23** | **`00b2a2c`** | Mobile: `fairnessOnFromPref` inverted. Unset pref used to mean ON (**0.75**); now means OFF (**0.50**). v1.14.0 build 116 | **In principle yes — but see §4, it appears non-binding for the observed users** | client / per-arm kwarg |
| 08-17 20:57 | `505ca2c`, `f68f860` | Dismiss cooldown — a pass is a hard 14-day exclusion (`pass_cooldown_days` 14.0) + legacy amnesty | Yes — exclusion set | knob |
| 08-18 | `60cbe11` | **Engine quality** — divergence-gated ranking fairness, minimal-package preference, pick-pair strip, per-deck headliner cap, confidence-damped mismatch. Five knobs, default ON | Yes | knob ×5 — **also killed by `MODEL_A_PROFILE`** |
| 08-18 | `e8ae476` | **Phase 0** — pinned players stop accruing comparison weight; newer swipe releases a pin; `force:true` supersedes in-flight jobs | Yes — board computation | knob ×4 |
| 08-18 | `d951e7c` | G-049 — a double-fired swipe applied `trade_k_pass` **twice**; 40 double-writes measured in prod | Yes — board write path | hard (guard) |
| 08-18 | `3760f12` | Bake-off Phase 2 — `MODEL_A_PROFILE`, `r4_bypass()`, golden test | Inert until `model_a()` is entered | — |

Cross-referenced against `living-memory/CHANGELOG.md`, `DECISIONS.md`, `docs/plans/compressed-board-pool/scope.md`, `docs/plans/engine-quality/scope.md`, `docs/plans/three-model-bakeoff/scope-phase0.md` / `scope-phase2.md`. The "Reaches generation?" and "Reversible?" columns were verified against code, not taken from commit messages.

---

## 3. Layer-arrival table

**Headline negative: none of the named `trade.*` / `deck.*` layers flipped on inside the window.** Every one was already ON by 2026-07-26. *(Confidence: high — `git log -S'"<flag>": true' -- config/features.json` over full history; live state re-confirmed against prod, below.)*

| Flag | Turned ON | ON during ~08-11? | ON now? | Flipped inside window? |
|---|---|---|---|---|
| `trade.marginal_value`, `trade.need_fit`, `trade_engine.v3`, `trade.likes_you`, `trade.deck_diversity`, `trade.thompson_deck` | `0e47229` 2026-07-12 | ✅ | ✅ | no |
| `trade.lanes`, `trade.fit_premium`, `trade.aggression_ab`, `trade.crown_asset`, `trade.outlook_seed`, `trade.outlook_infer` | `1ea8d32` 2026-07-17 | ✅ | ✅ | no |
| `trade.outlook_direction` | `0ed4cc5` 2026-07-25 | ✅ | ✅ | no |
| `deck.thompson_v2`, `deck.fatigue` | `a284b62` 2026-07-26 | ✅ | ✅ | no |
| `deck.session_rerank`, `deck.taste_vectors` | `9feb6bd` 2026-07-26 | ✅ | ✅ | no |
| `deck.exploration` | `315e89e` 2026-07-26 | ✅ | ✅ | no |
| **`trade.pool_calibration`** | **`19d4174` 2026-08-15 — ON at birth** | ❌ | ✅ | **YES** |
| **`trade.divergence_fallback`** | **`19d4174` 2026-08-15 — ON at birth** | ❌ | ✅ | **YES** |
| **`trade.presentment_rules`** | **`e10f93e` 2026-08-16 — ON at birth** | ❌ | ✅ | **YES** |
| `trade_gen.v2` | never | ❌ | ❌ | n/a (dark) |

Live prod verified 2026-08-18 via `GET https://fantasy-trade-finder.onrender.com/api/feature-flags` (HTTP 200): resolved state matches `config/features.json` exactly, including `trade.outlook_blend: false` and `trade_gen.v2: false`.

Only two of the three flipped flags predate the arm-A pin — so **arm A already contains `pool_calibration` and `divergence_fallback`**, i.e. it is not the pre-window engine. §4 explains why that turns out to be the right call anyway.

### The gate that is not a flag, not a knob, and not recorded

`fairness_threshold` is a **request parameter**, defaulted client-side:

```
mobile/src/api/tradePregen.ts   FAIRNESS_ON_THRESHOLD  = 0.75
                                FAIRNESS_OFF_THRESHOLD = 0.5

before 00b2a2c (2026-08-17):  raw === 'off' ? OFF : ON   →  unset ⇒ 0.75
after  00b2a2c (2026-08-17):  raw === 'on'               →  unset ⇒ 0.50
```

And the gate is **asymmetric by basis** (`_DEFAULT_CFG` lines 148-154, verbatim): divergence cards use `min(fairness_threshold, fairness_floor_divergence=0.55)`; *"Consensus-basis cards keep the full `fairness_threshold`."*

| | divergence gate | consensus gate |
|---|---|---|
| at 0.75 | `min(0.75, 0.55)` = 0.55 | 0.75 |
| at 0.50 | `min(0.50, 0.55)` = 0.50 | 0.50 |

I predicted this would show up as a consensus-card surge after 2026-08-17. **It did not** — see §4. The mechanism is real in code; its effect on the observed users appears to be nil, because they were evidently already running at 0.50. This remains a genuine hazard for *new* testers who never touch the toggle, and a genuine measurement gap (the threshold is never persisted), but it is not the cause of the operator's complaint.

---

## 4. Empirical check — production telemetry

All queries `SELECT` only, `SET TRANSACTION READ ONLY`, connected via `DATABASE_URL_PROD` from the gitignored `secrets.local.env` with the `postgres://` → `postgresql://` scheme fix. Note: all timestamp columns are `character varying` ISO strings, so day-bucketing uses `substr(col,1,10)`; every offset is `+00:00`, so this is true UTC.

### 4.1 How far back usable data goes — and the honest limit

`deck_impressions`: **7,649 rows**, `served_at` **2026-07-27T01:15:25Z → 2026-08-19T01:26:21Z**. The window is covered.

**But volume is not.** `deck_outcomes.action` observed values: `viewed` (404), `pass` (281), `like` (95), `not_interested` (14). Counting `like + pass + not_interested` as decisive:

| Day | Impr | Users | Lgs | Decisive outcomes | Like % |
|---|---|---|---|---|---|
| 08-08 | 342 | 1 | 1 | **0** | – |
| 08-09 | 481 | 1 | 2 | **0** | – |
| 08-10 | 421 | 1 | 4 | **3** | 33.3 |
| 08-11 | 575 | 2 | 4 | **24** | 4.2 |
| 08-12 | 724 | 3 | 6 | **5** | 20.0 |
| 08-14 | 241 | 2 | 2 | **9** | 55.6 |
| 08-15 | 247 | 2 | 1 | **0** | – |
| 08-16 | 929 | 3 | 2 | **57** | 35.1 |
| 08-17 | 1,274 | 4 | 3 | **231** | 25.5 |
| 08-18 | 777 | 4 | 2 | **38** | 0.0 |

**~41 decisive outcomes across the entire 08-08 → 08-15 window, versus 231 on 08-17 alone. Five distinct users and six leagues database-wide.** Several days have literally zero response.

**Stated plainly: the data does not reach far enough *in volume* to tell which period produced better user response.** It reaches back in *time*, which is not the same thing. Anyone quoting a like-rate difference between 08-11 (4.2%, n=24) and 08-14 (55.6%, n=9) is quoting noise. And the only days with real volume (08-16/17) coincide with three simultaneous events — a consensus-seed discontinuity, a full personal-board rewrite, and a client release — so even that volume is fully confounded.

### 4.2 Two assumptions that had to be corrected

1. **`policy_version` is NULL for every row before 2026-08-16** and has exactly one non-null value ever. It cannot separate engine states.
2. **`assets_json` is NULL before 2026-08-17.** A naive `LIKE '%pick%'` over it returns 0.0% for every early day, which *looks* like a finding and is an artifact. `features_json` is populated for all 7,649 rows and is the trustworthy source. **This also caveats `docs/reviews/2026/2026-08-18-valuation-age-audit.md` §6**, whose blast-radius query filters `served_at >= '2026-08-11' AND assets_json IS NOT NULL` — that query silently covered only 08-17 onward, not the 7 days it claims.

### 4.3 The pick-share series — the decisive result

| Day | Divergence | Consensus | Consensus % | **Pick %** | Avg fairness | Min fairness |
|---|---|---|---|---|---|---|
| 08-08 | 0 | 342 | **100.0** | **14.3** | 0.805 | 0.506 |
| 08-11 | 90 | 461 | 83.7 | **38.3** | 0.851 | 0.503 |
| 08-15 | 73 | 174 | 70.4 | **54.7** | 0.823 | 0.551 |
| 08-16 | 309 | 561 | 64.5 | 49.4 | 0.808 | 0.500 |
| 08-17 | 288 | 737 | 71.9 | **58.4** | 0.854 | 0.501 |
| 08-18 | 263 | 476 | 64.4 | **64.4** | 0.824 | 0.483 |

Pick share **14.3% → 64.4%**, monotone apart from one dip, with the steepest rise inside the operator's remembered week. This is the one metric that moves large, moves monotonically, moves in the direction of a complaint the operator actually made, and is corroborated by an independent diagnosis of the same corpus.

### 4.4 My hypothesis, and how the data killed it

I predicted from code that the 2026-08-17 fairness flip (0.75 → 0.50) would loosen the consensus gate by 33% and produce a **consensus-card surge**. The data says the opposite on both counts:

- **Consensus was already dominant the whole time** — 100% on 08-08, 83.7% on 08-11 — and **divergence share *rose*** from ~0% to 29–36%.
- **`min_fairness` sits at ~0.50 as far back as July**, before the flip. Under the pre-08-17 client code a consensus card required `fairness >= fairness_threshold`, so a 0.75 threshold could not have served a 0.506 card. **The observed users were already running at 0.50** — either with the toggle explicitly set off, or through the `_any_pinned` server default (`server.py:10494`, `0.50 if _any_pinned else 0.75`), which has been unchanged since April.

**So the fairness flip is real in code and appears non-binding in practice for this population.** *(Confidence: medium-high — the `min_fairness` inference is sound, but the threshold is not persisted, so I cannot prove which of the two explanations applies. These are the operator's own accounts and may carry an explicit stored pref.)*

The 0% divergence on 2026-08-08 is itself a strong corroboration of a *different* claim: `19d4174`'s field diagnosis that boarded opponents were producing **zero** divergence cards. The bug was not marginal — divergence generation was effectively dead, and the fix is what brought it to 29–36%.

### 4.5 The result worth pursuing

| Basis | Decisive outcomes | Likes | Like rate |
|---|---|---|---|
| Consensus | 217 | 72 | **33.2%** |
| Divergence | 173 | 23 | **13.3%** |

Pass-reason mix: divergence skews to **fit** (20 fit vs 17 value); consensus skews to **value** (18 value vs 8 fit).

**Users like consensus-basis cards ~2.5× more than divergence-basis cards** — the opposite of the engine's design thesis, which treats board divergence as the signal worth mining. This reframes the operator's memory: if "just focusing on rank/value diffs between two users" means *a straightforward value-balanced swap between two rosters* rather than *mining disagreement between two personal boards*, then what they liked **is** the consensus deck — which was 84–100% of the deck during the remembered week and is now 64%.

*(Confidence: medium. n is adequate but every row comes from 08-16/17 and ~4 people, all internal. Do not act on this without a prospective test — which is exactly what the bake-off is.)*

### 4.6 Value drift — the answer to hypothesis (b)

**Consensus seed, top-50 `1qb_ppr`, drift vs the 2026-08-08 baseline:**

| Date | Mean abs Δ Elo | Max abs Δ Elo | Moved > 5 ranks |
|---|---|---|---|
| 08-09 | 0.52 | 9.1 | 0 |
| 08-12 | 2.18 | 10.1 | 0 |
| 08-15 | 3.76 | 11.2 | 0 |
| **08-16** | **14.37** | **119.7** | **8** |
| 08-18 | 14.21 | 119.0 | 6 |

**Personal board (user `867830050538598400`, `1qb_ppr`), reconstructed `n` and `w = n/(n+4)`:**

| As of | Players with any comparison | Mean n | Mean w | Players w ≥ 0.5 |
|---|---|---|---|---|
| 08-08 | 45 | 4.22 | 0.435 | 15 |
| 08-15 | 53 | 4.15 | 0.437 | 18 |
| **08-17** | **126** | 5.68 | 0.467 | **63** |
| 08-18 | 127 | 6.20 | 0.481 | 64 |

**725 ranking comparisons on 2026-08-17 alone.** All 644 `member_rankings` rows for that user/format carry `updated_at = 2026-08-17`; `elo_history` records 16,920 rows that day. `member_rankings.updated_at` has exactly **two** distinct values ever (2026-07-09 and 2026-08-17), so the board has two states, not a continuum — a per-day divergence series would be a flat line with one step, which is why it was not run.

**The shrinkage-drift mechanism I was asked to test is real but is *not* the dominant channel.** Mean `w` moved only 0.437 → 0.481. What moved is **coverage**: players carrying any personal signal **2.4×'d in a day**, and players where personal value dominates **3.5×'d**. That is a far larger perturbation to `mismatch` (70% of the composite) than the weight drift, and it is entirely consistent with "my rankings have remained relatively unchanged" — the operator re-expressed an existing opinion, and the engine treated it as newly-earned confidence.

### 4.7 `model_config` — prod matches code defaults exactly

`shrink_pseudocount` 4.0 · `elo_value_k` 0.005 · `elo_value_ref` 1500.0 · `elo_value_base` 1000.0 · `mismatch_weight` 0.7 · `fairness_weight` 0.3 · `fairness_floor_divergence` 0.55 · `max_overpay_frac` 0.25 · `max_overpay_min_value` 500.0 · `pos_net_cap` 1.0 · `pick_gap_frac` 0.8 · `pick_gap_min_value` 300.0 · `need_gate_min_value` 500.0 · `pin_exclude_comparisons` 1.0. **No rows exist for `rank_div_min_frac`, `min_package_band`, `pick_pair_strip_frac`, `deck_headliner_cap`, `mismatch_confidence_damp`** — the 2026-08-18 engine-quality knobs are running on their code defaults, not DB-seeded values.

**`model_config` has only three columns (`key`, `value`, `description`) — no `updated_at`.** When any knob last changed is unknowable from the database. Worth fixing.

### 4.8 Local DB

`data/trade_finder.db` is **not a usable fallback**: `deck_impressions` / `deck_outcomes` have 0 rows; `deck_candidate_sets`, `trade_pass_reasons`, `suggestion_trade_links` do not exist; `swipe_decisions` ends 2026-04-16. April fixture data, not traffic.

### 4.9 Queries used

```sql
-- Range / volume
SELECT COUNT(*) AS n, MIN(served_at), MAX(served_at),
       COUNT(DISTINCT user_id) AS users, COUNT(DISTINCT league_id) AS leagues
FROM deck_impressions;

-- Per-day impressions + outcomes
SELECT substr(i.served_at,1,10) AS day_utc,
       COUNT(*) AS impressions,
       COUNT(DISTINCT i.user_id) AS users,
       COUNT(DISTINCT i.league_id) AS leagues,
       COUNT(o.impression_id) AS outcomes,
       SUM(CASE WHEN o.action='like'           THEN 1 ELSE 0 END) AS likes,
       SUM(CASE WHEN o.action='pass'           THEN 1 ELSE 0 END) AS passes,
       SUM(CASE WHEN o.action='viewed'         THEN 1 ELSE 0 END) AS viewed,
       SUM(CASE WHEN o.action='not_interested' THEN 1 ELSE 0 END) AS not_int
FROM deck_impressions i
LEFT JOIN deck_outcomes o ON o.impression_id = i.impression_id
GROUP BY 1 ORDER BY 1;

-- Basis mix, pick share, fairness (features_json is TEXT -> cast to jsonb)
SELECT substr(served_at,1,10) AS day_utc,
       COUNT(*) AS impressions,
       SUM(CASE WHEN features_json::jsonb->>'basis'='divergence' THEN 1 ELSE 0 END) AS divergence,
       SUM(CASE WHEN features_json::jsonb->>'basis'='consensus'  THEN 1 ELSE 0 END) AS consensus,
       SUM(CASE WHEN features_json::jsonb->>'basis' IS NULL      THEN 1 ELSE 0 END) AS basis_absent,
       ROUND(100.0*SUM(CASE WHEN (features_json::jsonb->>'involves_pick')='true' THEN 1 ELSE 0 END)/COUNT(*),1) AS pick_pct,
       ROUND(AVG((features_json::jsonb->>'fairness_score')::numeric),3) AS avg_fairness,
       ROUND(MIN((features_json::jsonb->>'fairness_score')::numeric),3) AS min_fairness
FROM deck_impressions GROUP BY 1 ORDER BY 1;

-- Like rate by basis
SELECT i.features_json::jsonb->>'basis' AS basis,
       COUNT(*) AS decisive,
       SUM(CASE WHEN o.action='like' THEN 1 ELSE 0 END) AS likes,
       ROUND(100.0*SUM(CASE WHEN o.action='like' THEN 1 ELSE 0 END)/COUNT(*),1) AS like_pct
FROM deck_impressions i JOIN deck_outcomes o ON o.impression_id=i.impression_id
WHERE o.action IN ('like','pass','not_interested')
GROUP BY 1 ORDER BY 1;

-- Ranking activity per day per user
SELECT substr(created_at,1,10) AS day_utc, user_id, COUNT(*) AS comparisons
FROM swipe_decisions
WHERE substr(created_at,1,10) BETWEEN '2026-07-25' AND '2026-08-18'
GROUP BY 1,2 ORDER BY 1,3 DESC;

-- Shrinkage weight w = n/(n+4), n = unique opponents as of :cut
WITH pairs AS (
  SELECT winner_player_id AS p, loser_player_id AS opp, substr(created_at,1,10) AS d
  FROM swipe_decisions WHERE user_id=:u AND scoring_format=:f
  UNION ALL
  SELECT loser_player_id AS p, winner_player_id AS opp, substr(created_at,1,10) AS d
  FROM swipe_decisions WHERE user_id=:u AND scoring_format=:f
)
SELECT :cut AS as_of, COUNT(DISTINCT p) AS players_with_any_comparison,
       ROUND(AVG(n),2) AS mean_n, ROUND(AVG(n/(n+4.0)),4) AS mean_w,
       SUM(CASE WHEN n>=4 THEN 1 ELSE 0 END) AS players_w_ge_half
FROM (SELECT p, COUNT(DISTINCT opp)*1.0 AS n FROM pairs WHERE d <= :cut GROUP BY p) t;

-- Consensus drift vs 08-08 baseline, top-50, 1qb_ppr
WITH base AS (
  SELECT player_id, consensus_elo,
         ROW_NUMBER() OVER (ORDER BY consensus_elo DESC) AS rk
  FROM player_value_history
  WHERE snapshot_date='2026-08-08' AND scoring_format='1qb_ppr'
), top50 AS (SELECT * FROM base WHERE rk<=50),
d AS (
  SELECT h.snapshot_date, ABS(h.consensus_elo - t.consensus_elo) AS abs_delta,
         ROW_NUMBER() OVER (PARTITION BY h.snapshot_date ORDER BY h.consensus_elo DESC) AS rk_day,
         t.rk AS rk_base
  FROM player_value_history h JOIN top50 t ON t.player_id=h.player_id
  WHERE h.scoring_format='1qb_ppr' AND h.snapshot_date BETWEEN '2026-08-08' AND '2026-08-19'
)
SELECT snapshot_date, COUNT(*) AS players,
       ROUND(AVG(abs_delta)::numeric,3) AS mean_abs_elo_delta,
       ROUND(MAX(abs_delta)::numeric,3) AS max_abs_elo_delta,
       SUM(CASE WHEN ABS(rk_day-rk_base)>5 THEN 1 ELSE 0 END) AS moved_gt5_ranks
FROM d GROUP BY 1 ORDER BY 1;
```

---

## 5. Reproducibility per candidate state

### Candidate A — the plateau, 2026-08-09 `ee91334` → 2026-08-15 `6158e65`

The state that literally matches "about a week ago". Generator byte-identical throughout.

**Verdict: mostly reproducible as a profile — but §4 says it should not be reproduced.** Reconstructing it would restore the 0%-divergence defect. Recorded here so the option is documented, not so it is taken.

| Difference from today | Type | Per-arm reproducible? | How |
|---|---|---|---|
| G6 R1/R2/R3/R5 | knob ×4 | ✅ already | `MODEL_A_PROFILE` |
| G6 R4 | flag, no knob | ✅ already | `r4_bypass()` |
| Engine-quality C1–C5 | knob ×5 | ✅ already | `MODEL_A_PROFILE` |
| `fairness_threshold` | request kwarg | ✅ trivial | already a per-call parameter (`trade_service.py:2912`) — pass it explicitly per arm |
| `trade.pool_calibration` | flag, no knob | ⚠️ ~10 lines | thread-local bypass copying `r4_bypass()`; one read site, `trade_optimizer.py:383`. **Not recommended** — restores the zero-divergence defect |
| `trade.divergence_fallback` | flag, no knob | ⚠️ ~10 lines | same; one read site, `trade_service.py:4022`. **Not recommended** |
| `likes_you_min_user_delta` | knob | ❌ | `server._likes_you_min_user_delta()` reads `trade_service._cfg` — the **process** dict, not `_c()`. `_cfg_override` cannot reach it, and it runs in the injector outside the generator |
| `qb_1qb_cap_elo` / `_knee_elo` | knob | ❌ | `data_loader._qb_cap_config()` reads `database.get_config()` at **seed-build** time. Process-global, shared by all arms |
| `fit_k_explained_mult` / `_defying_mult` | knob | ❌ not retroactively | write-path only — it scaled deck-swipe Elo K from 2026-08-15. The boards have absorbed it; no read-side setting undoes stored Elo |

The three ❌ rows are **input-value** changes, not generation logic. They affect every arm equally, so they do not bias the comparison — but **no arm can be a byte-faithful 2026-08-11 engine.** Say that plainly rather than claiming a perfect reconstruction.

### Candidate B — `92c31d5`, the current pin

**Verdict: already reproduced, correctly, with a golden test — and it is the right choice.** `backend/tests/test_bakeoff_arm_a_golden.py` is strong work: 10 tests including per-rule non-vacuity and a `_DEFAULT_CFG` inventory drift alarm.

Its one structural blind spot is worth naming: the Phase-2 audit method was `git diff 92c31d5..origin/main`, which by construction can only find knobs added *after* the reference SHA. It could not have found the fairness-threshold flip (TypeScript, and a request parameter rather than a knob) or the pick-pricing rollout (a flag wave two weeks earlier). Neither turns out to change the recommendation, but the method's boundary should be understood.

**One concrete gap to close before Phase 5:** `fairness_threshold` is currently inherited from whatever the client sent and is not recorded anywhere. All three arms would silently run at the caller's threshold, and no post-hoc analysis could tell which. Set it explicitly per arm and persist it.

### Candidate C — "the good behaviour was never a single code state"

**Verdict: substantially true, and §4.6 dates it.** Three board-side mechanisms degraded inputs with no code change:

1. **Every deck swipe writes Elo** — `trade_k_like` 8.0, `trade_k_pass` 4.0 (`ranking_service.py:558`). Board drift is a monotone function of app usage.
2. **Votes on pinned players inflated confidence without moving Elo** — `_compute_elo` skips the update for override-pinned players while `_shrink_user_elo` weights by comparison **count**. Fixed only 2026-08-18 (`e8ae476`). Measured at +12.5% on one player in the valuation audit.
3. **A double-fired swipe applied `trade_k_pass` twice** — 40 double-writes in prod. Fixed only 2026-08-18 (`d951e7c`).

**Reproducibility: none.** Board state is not versioned. `users.tier_overrides` is a wholesale-overwritten blob with no history (`backend/database.py:3915`); `member_rankings` stores current Elo only (and has exactly two distinct `updated_at` values ever). There is no way to rewind a board to 2026-08-11 and re-run against it.

---

## 6. What I could not determine, and why

| Open item | Why | What would close it |
|---|---|---|
| **Which period actually produced better user response** | ~41 decisive outcomes across 8 days vs 231 on one day; 5 users total; `policy_version` has one value and only from 08-16; the only high-volume days coincide with three simultaneous confounds. **This is the mission's question 3, and the answer is a clean negative.** | Nothing retrospective. A prospective instrumented run — i.e. the bake-off. |
| **Whether the fairness flip ever bound for anyone** | `fairness_threshold` is persisted nowhere — not a column, not one of the 28 `features_json` keys. `min_fairness ≈ 0.50` in July implies these users were already at 0.50, but I cannot distinguish "toggle explicitly off" from "`_any_pinned` server default". | Persist the threshold on every impression (recommendation 2). |
| **Whether pick-share caused the quality drop, or merely tracks it** | The correlation is strong (14.3% → 64.4%), the mechanism is proven in code (`60cbe11`: a pick adds fairness and zero divergence), and the operator named it independently — but I ran no counterfactual. | Re-run the corpus query after `60cbe11` has been live a week; the scope block already names this as the measurement. |
| **Which TestFlight build the operator was on during the good week** | Backend deploys on every push, but the fairness default ships in the binary. v1.13.0 (08-11) → v1.13.4 build 111 (08-14) carry 0.75; v1.14.0 build 116 (08-17) carries 0.50. Install times are not in the repo. | Analytics `app_version` per session, or ask the operator. |
| **Whether the operator's board was overwritten by a rankings import** | The 2026-08-16 DynastyNerds import was backed up and **restored byte-exact, md5-verified** (CHANGELOG 2026-08-16), clearing that run. The 08-17 board rewrite is 725 manual comparisons, not an import — `swipe_decisions` accounts for it. | Considered closed. |
| **Effective (shrunk) values at deck-generation time** | Never persisted. `features_json` carries *consensus* `give_value`/`receive_value` by design so the card matches the manual calculator; the personal shrunk values that drove selection are not stored. | Log shrunk values alongside consensus ones, at least for bake-off decks. |
| **Whether the pre-08-15 engine was *better* or merely *different*** | The 2026-08-15 fixes were genuine bug fixes — §4.3 confirms divergence generation was at **0%** on 08-08. Reverting `pool_calibration` restores a defect. "The operator liked it" and "it was correct" are different claims and I cannot rank them from the data. | Operator judgement on side-by-side decks. |
| **When any `model_config` knob last changed** | The table has only `key`, `value`, `description`. No `updated_at`. | Add the column. |

### Method note — verified vs inferred

- **Verified by diff or code read:** the 08-09 → 08-15 plateau (`git diff` empty); every flag's introduction and flip date (`git log -S` over full history); the fairness-threshold inversion (`00b2a2c`); the divergence-vs-consensus gate asymmetry (`_DEFAULT_CFG` + `trade_service.py:3469`); knob reachability through `_c()` vs `_cfg` vs `get_config()`; live prod flag state (`GET /api/feature-flags`, HTTP 200, 2026-08-18).
- **Verified in prod data:** every number in §4, `SELECT` only, queries reproduced verbatim in §4.9.
- **Inferred from commit messages / CHANGELOG:** the *intent* behind each change; the "net-subtractive" characterisation of the G6 + engine-quality waves (asserted by `test_current_defaults_differ_from_the_golden` on one fixture, not on the live corpus).
- **Taken from a prior report:** the +12.5% Adams figure and the 67.8% inert-comparison figure, from `docs/reviews/2026/2026-08-18-valuation-age-audit.md`, which itself flags the former as reconstructed arithmetic rather than an instrumented run.
- **Predicted and then falsified:** the consensus-surge hypothesis in §3. Recorded in §4.4 rather than removed.
