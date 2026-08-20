# Fit challenger + serving re-light — delivery plan, draft B (risk-and-measurement-first)

**Date:** 2026-08-20
**Stance:** this draft optimizes for the test being READABLE and the blast radius being
contained. Where it disagrees with a build-first draft, the disagreement is called out and
quantified. Nothing in here reopens PRD §3 (knockouts are operator-CLOSED); `fit_r5_mode`
pre-wiring (default = kill) is the only K-adjacent addition, and it changes no K math.

**Combined scope (operator-approved 2026-08-20):**
1. Build bake-off arm `fit` per [PRD.md](PRD.md) / [PLAN.md](PLAN.md) / [scope.md](scope.md).
2. Re-light interleaved serving to tester leagues so arms produce per-arm USER DECISIONS
   (today `bakeoff_serve_interleaved = 0`; no arm but `current` has ever been seen by a user).
3. The measurement prerequisites that make the answer readable: knob-change logging, a
   bucketed metric readout, weekly tester cadence per
   [trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md) Phase 2.

**Binding constraints honored throughout:** organic serving stays arm B; no
`_generate_trades_impl` routing change; `trade_gen.v2` stays false; every new `_DEFAULT_CFG`
knob gets an arm-A disposition sentence (the knob-inventory guard in
`backend/tests/test_bakeoff_arm_a_golden.py` fails by name otherwise); backend-only v1;
CI green (pytest, tsc, testid-lint).

---

## Table of contents

1. [Objective and falsifiable stage criteria](#1-objective-and-falsifiable-stage-criteria)
2. [Measurement design (first, because it constrains the build)](#2-measurement-design)
3. [Build workstream](#3-build-workstream)
4. [Staged rollout — exact knob values, entry/exit, evidence](#4-staged-rollout)
5. [C1–C7 / T1–T4 coverage table](#5-c1c7--t1t4-coverage-table)
6. [Failure-mode table — silent failures, detection, tripwires](#6-failure-mode-table)
7. [Evidence plan per D-056](#7-evidence-plan-per-d-056)
8. [Docs and living-memory updates owed](#8-docs-and-living-memory-updates-owed)
9. [What this draft cuts or defers from a build-first version, and why](#9-cuts-and-defers)

---

## 1. Objective and falsifiable stage criteria

**Objective.** By end of week 7, produce one written, pre-registered answer to: *does the
fit generator's thin-knockout + dual-score design produce trades testers like better than
live arm B, on the cards where both scores say it should (`both_high` + `mixed`), without
worsening the `value_giving` complaint or the deck the tester holds?* — with enough decided
cards per arm that the answer is statistics, not anecdote, and with every knob move dated.

The plan runs five stages. Each has a falsifiable success criterion and an abort criterion;
a stage that cannot state what evidence would kill it is not a stage, it is hope.

| Stage | What happens | Success (falsifiable) | Abort / iterate trigger |
|---|---|---|---|
| **S0** (W0) | Measurement prerequisites land (M1–M4 §3); fit F1–F6 built; offline dry run on the replay boards + fixture league | Dry-run diagnostics complete (every field in §2.6); fixture arm-ms recorded; CI green; **fit produces ≥ 2× arm B's distinct legal ideas on the same boards** (the PRD's core volume bet, tested before any serving) | If fit ≤ 1.2× arm B ideas at `fit_max_packages_per_pair = 20000`, the volume thesis is false — stop, report, do not roster. Cost of falsification: ~7 eng-days, zero user exposure |
| **S1** = round R0 (W1–W2) | Re-light interleaved serving, arms `current` vs `challenger`, lane quotas OFF (`bakeoff_group_size = 0`) | Median served deck ≥ 20 cards; ≥ 290 decided cards/arm by end W2 (≈300 = the 10pp bar, accuracy PLAN Phase 2); zero discarded runs; position balance holds (§6 row 7) | Median deck < 15 on two consecutive days → `bakeoff_serve_interleaved = 0` same day (the 2026-08-18 playbook, now written down); GOTCHAS entry |
| **S2** (W3) | R0 readout + decision; fit joins the roster **dark** (`bakeoff_include_fit = 1`, `bakeoff_serve_fit = 0`); serving continues B vs D unchanged | ≥ 3 days of prod dark diagnostics; p95 `bakeoff_runs.total_ms` ≤ 30 s; fit median cards/run ≥ 15 on the boarded league; `killed[K7]` reported; top-quartile pick/junk shares within bars (§2.6) | p95 total_ms > 45 s → halve `fit_max_packages_per_pair` and re-soak; still over → `bakeoff_include_fit = 0` (relief valve, no deploy). Fit cards/run < 5 → enumerator supply bug, do not serve |
| **S3** = round R1 (W4–W6) | `bakeoff_serve_fit = 1`, `bakeoff_include_challenger = 0`: serving is B vs fit | ≥ 100 decided fit cards **in `both_high`+`mixed`** by end W6 (≈130 = the 15pp bar cited from accuracy PLAN Phase 2); weekly readouts filed | Same deck-shrink tripwire as S1; additionally: fit pooled like-rate < 5% for a full week with n ≥ 100 → testers are being served noise, pause and inspect top-of-deck cards by hand |
| **S4** (W7) | Decision per pre-registered rules (§2.5) | One of three written verdicts: promote / iterate-one-knob / kill — each names its next action | No abort; the decision itself is the exit |

**One number to hold onto:** ~10 testers × ~40 decided cards/week ≈ **400 decided
cards/week total** (accuracy PLAN Phase 2 — cited, not re-derived). Every design choice
below is downstream of that budget.

---

## 2. Measurement design

### 2.1 How many arms can this tester base support? (the power math)

Cited constants (accuracy PLAN Phase 2, appendix — do not re-derive): base like-rate ≈ 20%
on decided cards; detecting a **10pp** lift needs **≈300 decided cards per arm**; **15pp**
needs **≈130**. Supply: **≈400 decided cards/week** across all served arms.

With `k` simultaneously-served arms, per-arm supply is `400/k` decided/week. Two additional
haircuts apply to the fit arm specifically:

- **Bucket restriction (C3).** The co-primary metric counts only `both_high` + `mixed`
  cards. The dry run measures the real bucket mix; planning assumption **f ≈ 0.5** (half of
  fit's served cards land in the co-primary buckets — the arm deliberately serves tilt
  cards too). Effective co-primary supply ≈ `0.5 × 400/k` per week.
- **Contamination ceiling.** The longer a round runs, the higher the probability a knob
  wave lands inside it — the historical rate is five knob waves + two repricing waves in a
  single 5-day window (accuracy PLAN Part 2), and D-091 already cost one measurement window
  outright. Rounds longer than **3 weeks** are presumed contaminated at this shop's change
  velocity.

Time-to-answer table (weeks to reach the n for each effect size, co-primary buckets):

| Served arms k | per-arm/wk (all) | per-arm/wk (bucketed, f=0.5) | 15pp (130) | 10pp (300) |
|---:|---:|---:|---:|---:|
| 2 | 200 | 100 | **1.3 wk** | **3.0 wk** |
| 3 | 133 | 67 | 1.9 wk | 4.5 wk |
| 4 | 100 | 50 | 2.6 wk | 6.0 wk |

**Ruling: maximum 2 simultaneously-served arms.** k=2 is the only row where a 10pp read
fits inside the 3-week contamination ceiling. k=3 answers only 15pp+ effects before the
window rots; k=4 answers nothing. Interleaving is within-subject (every tester sees both
arms in every deck), which buys some variance reduction over the independent-samples
numbers above — treat that as margin, not as license for a third arm.

**What happens to the arms that don't fit: pairwise rounds, arm B always seated.**

- Arm B (`current`) is in every round: it is the incumbent control, the dark-mode fallback
  (`DARK_SERVED_ARM`), and the common comparator that keeps rounds comparable to each other.
- **Round R0 = B vs D (`challenger`)**, weeks 1–2, *while fit is being built*. D is
  already built, already out-generates B on the boarded league (18.3 vs 15.0 cards/run,
  2.0 s vs 2.6 s — accuracy PLAN appendix), and it carries the two measured arm-B levers
  (`user_elo_shrink`, tier compression) as its P1/P2. Serving it first converts idle build
  time into the accuracy plan's own Phase 1.1, and reads those levers *before* anyone
  commits them to arm B.
- **Round R1 = B vs fit**, weeks 4–6, after fit's dark soak.
- **Arm C (`gen_v2`) is benched from serving indefinitely**: it produced zero cards in 12
  of 18 runs on non-boarded leagues (supply, per D-087), and real tester leagues are mostly
  boardless (board supply: one league with ≥3 boards). Serving it spends decision budget on
  an arm that structurally cannot fill decks for most testers. It re-enters only when
  tester onboarding (accuracy PLAN Phase 2) has produced ≥2 leagues with 3+ boards — that
  is a falsifiable re-entry condition, not a shelving.
- **Arm A (`baseline`) stays off the roster** (operator decision 2026-08-18, unchanged).

### 2.2 Metric definitions (pre-registered, so the readout can't be argued after the fact)

All denominators exclude ghosts (`deck_impressions.is_ghost = 1`) and all windows start no
earlier than 2026-08-19 (D-091 phantom-pick contamination discipline — any baseline drawn
from before that date is invalid; armb-audit "Warnings" section).

| Metric | Definition | Role |
|---|---|---|
| **Co-primary 1: bucketed like-rate** | `likes / (likes + passes)` on decided, non-ghost impressions, per `model_arm`, restricted to cards whose fit bucket ∈ {`both_high`, `mixed`} | The verdict metric for R1. Arm B's cards get buckets from the diagnostic fit-score stamp (M3, §3) so the comparison is bucket-matched, not fit-only |
| **Co-primary 2: decline-reason mix** | share of `trade_pass_reasons.reason/detail` = `value_giving` among passes, per arm | The complaint the dual score exists to fix (40% today, accuracy PLAN appendix). Detecting 40%→25% needs ≈150 passes/arm — about one week at k=2 |
| **Guardrail: pooled like-rate** | same numerator/denominator, no bucket restriction | Reported, never the verdict (C3): the arm deliberately serves tilt cards and would lose a pooled comparison by construction. Tripwire only: fit pooled < 5% for a week → pause |
| **Guardrail: deck integrity** | median `bakeoff_runs.deck_size` per day; per-arm mean `card_index` | The 2026-08-18 failure was deck shrink, not bad cards. Bars in §6 |
| **Guardrail: job time** | p95 `bakeoff_runs.total_ms`; per-arm ms from `arms_json` | C6 / HANDOVER §5.2; `_JOB_HARD_TIMEOUT = 60` (`server.py:2218`) marks a slow job **error** — a starved job yields no deck at all |
| **Diagnostic: `you_tilt` like-rate** | like-rate on fit cards bucketed `you_tilt` | PRD §7's warning light. Not gated in v1; informs whether `fit_min_them` ever turns on |
| **Diagnostic: propose count** | `deck_outcomes.action = 'propose'` per arm | 0 all-time; the tester protocol's ≥1 send attempt/week exercises it (launch gate G1) |
| **Secondary: like-on-viewed** | likes / viewed | Reported for continuity with prior readouts; decided is the primary denominator because testers are instructed to decide ≥40 cards, which controls the denominator at small n |

**Small-n honesty rules:** every reported rate carries a Wilson 95% interval; deltas < 3pp
read as "did not move" (the audit corpus's own resolution caveat, adopted verbatim);
nothing is called before its pre-registered n is reached.

### 2.3 Contamination rules (D-091 discipline, made operational)

1. **One engine-affecting change per measurement window** (accuracy PLAN 0.4). A window =
   one tester week (Mon–Fri readout). **A roster change — adding, removing, or flipping
   the serve bit on an arm — IS an engine-affecting change** and consumes that week's slot.
   The schedule in §4 is built so every roster move lands on a Monday window boundary and
   nothing else engine-affecting lands that week. In particular: the accuracy plan's queued
   `trade.outlook_direction` flip (its experiment #1) does **not** run during R0 or R1; if
   the operator wants it, its slot is the W3 boundary between rounds, where it shifts arm B
   identically in both directions of no comparison.
2. **Knob freeze verification is mechanical, not promised.** `bakeoff_runs.config_json`
   already snapshots the effective config per run. The weekly readout diffs every run's
   snapshot against the round-start snapshot; any engine-affecting key differing →
   **the window is discarded, not caveated** (HANDOVER trap 5's rule, extended from
   re-rankers to knobs). The M1 knob-change log gives the same answer from the write side.
3. **Re-ranker discipline:** any interleaved deck served with re-rankers live is discarded
   (HANDOVER trap 5). `bypass_rerankers()` is the single predicate; M4 adds a per-run
   assertion to the readout (bakeoff run with `served_arm IS NULL` must have the bypass
   marker in `arms_json`).
4. **Board-teaching freeze:** `elo_freeze_mult()` already zeroes trade-swipe K during
   bake-off runs, severing the arm→board→arm loop. No change; the readout verifies
   `swipe_decisions.k_factor = 0` on bake-off-era trade swipes as a spot check.
5. **No cross-era baselines.** R1's arm-B numbers come from R1's weeks only; R0's arm-B
   numbers are not reused (the outlook flip or any W3 change would sit between them).

### 2.4 Readout queries (SQL sources, run under the `prod_analytics` read-only posture)

Checked into `scripts/bakeoff_readout.sql` (M2) so Friday is a 30-minute execution, not an
authoring session. Core queries:

```sql
-- 1. Co-primary 1: decided like-rate by arm × fit bucket (Postgres)
SELECT i.model_arm,
       COALESCE(i.features_json::json->'fit'->>'bucket',
                i.features_json::json->'fit_diag'->>'bucket') AS bucket,
       COUNT(*) FILTER (WHERE o.action = 'like') AS likes,
       COUNT(*) FILTER (WHERE o.action = 'pass') AS passes
FROM deck_impressions i
JOIN deck_outcomes o ON o.impression_id = i.impression_id
WHERE i.served_at >= :window_start
  AND COALESCE(i.is_ghost, 0) = 0
  AND o.action IN ('like', 'pass')
GROUP BY 1, 2;

-- 2. Co-primary 2: decline-reason mix by arm
SELECT i.model_arm, r.reason, r.detail, COUNT(*)
FROM trade_pass_reasons r
JOIN deck_impressions i ON i.impression_id = r.impression_id
WHERE i.served_at >= :window_start
GROUP BY 1, 2, 3 ORDER BY 4 DESC;

-- 3. Deck-integrity tripwire (daily, not just Friday)
SELECT SUBSTRING(created_at, 1, 10) AS d,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deck_size) AS median_deck,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_ms
FROM bakeoff_runs
WHERE served_arm IS NULL          -- interleaved decks only
GROUP BY 1 ORDER BY 1;

-- 4. Position balance: mean served position per arm (interleaver health)
SELECT model_arm, AVG(card_index), COUNT(*)
FROM deck_impressions
WHERE served_at >= :window_start AND model_arm IS NOT NULL
GROUP BY 1;

-- 5. Fit generation diagnostics (dark soak + serving): per-run arms_json fields
--    enumerated / scored / killed[K0..K7] / one_sided_pct / bucket mix /
--    top_q_pick_share / top_q_junk_share / ms  — extracted from
--    bakeoff_runs.arms_json->'fit'->'diagnostics'.
```

The fit bucket is **stamped at generation time** into `features_json.fit.bucket` (F3) so
query 1 never re-derives thresholds in SQL — a threshold re-derived in two places will
eventually disagree in one of them.

### 2.5 Pre-registered decision rules for R1 (written before any serving)

- **Promote** (fit earns a follow-up round and F7/`fit_min_them` tuning): bucketed
  like-rate (co-primary 1) Δ ≥ +10pp vs arm B bucket-matched, 95% CI excluding 0, **and**
  `value_giving` share of fit passes < arm B's, **and** all guardrails held all round.
- **Iterate**: co-primary 1 within ±10pp but `you_tilt` like-rate materially drags the
  pooled number, or bucket mix f < 0.35 (too few co-primary cards) → one knob change
  (candidates, in order: `fit_min_them`, `fit_w_*` weights, `fit_r5_mode`) and one more
  2-week window. One knob. Not a wave.
- **Kill** (fit leaves the roster, findings feed arm-B queue): bucketed like-rate ≤ arm B
  −5pp with CI excluding 0, or the deck-integrity guardrail trips twice.

### 2.6 Dry-run / dark-soak diagnostic contract (what S0/S2 must report)

Required fields on `bakeoff_runs.arms_json['fit'].diagnostics` (PRD §7 plus the review's
C2/C5 additions): `enumerated`, `scored`, `killed{K0..K7}` (**K7 reported first-class**,
per C2), `one_sided_pct` (compare against the 96.3% arm-B headline), `both_high_pct`,
`mixed_pct`, `you_tilt_pct`, `median_aggregate`, `ms`, and — new, C5 — `top_q_pick_share`
and `top_q_junk_share` (share of top-quartile-aggregate cards containing a pick / an asset
below `asset_floor_abs = 450` consensus). Bars for S2 exit: `top_q_junk_share ≤ 0.10`;
`top_q_pick_share` ≤ arm B's served pick share + 10pp (baseline from the HANDOVER §9
pick-share query). Junk/pick over bars → the lens-3-tanks-junk assertion is falsified →
turn on the PRD §10 filler knob (default-off) *as the S3 iterate action*, not silently.

---

## 3. Build workstream

Two lanes: **M-tickets (measurement)** and **F-tickets (fit build, per PRD §8)**. M1–M2
land before any serving because a knob moved before the log exists is a knob moved never.

| ID | Title | Est | Depends | Notes |
|---|---|---:|---|---|
| **M1** | Knob-change log: new table `model_config_changes` (`key, old_value, new_value, changed_at, source`) + `updated_at` on `model_config`; written by `PUT /api/admin/config/<key>` (`server.py:16652`) and any bulk-set path | 0.5d | — | Accuracy PLAN 0.2. Schema change → bright-line: **not express**; own scope block (§7). `docs/data-dictionary.md` row |
| **M2** | Readout pack: `scripts/bakeoff_readout.sql` (queries §2.4) + a one-page runbook line for the Friday cadence; includes the config-snapshot diff check (§2.3.2) | 0.5d | — | Read-only; no route |
| **M3** | Diagnostic fit-score stamp on non-fit arms: after generation, score every bake-off card with the fit scorer, stamp `features_json.fit_diag = {you, them, bucket, ver}` | 0.5d | F3 | Enables bucket-matched comparison (C3). **Diagnostic only**: stamped post-ranking, wrapped in try/except, never read by any ranking path — enforced by test (§6 row 5). Scorer version pinned in the payload |
| **M4** | Tripwire additions to readout: deck-size daily query, position-balance query, re-ranker-bypass assertion, per-arm error/forfeit counts | 0.25d | M2 | Queries only |
| **F1** | Knockout module wrapping live K1–K7 + `fit_r5_mode` pre-wire (1 = kill, default; 0 = score into viewer lens) | 1d | — | **T1:** import the module, never the names — `from . import trade_service as ts; ts.overpay_ok(...)`. K3 (`_feasible_after`) evaluated **last** in the K-order despite its name (C6: it is the expensive predicate) |
| **F2** | Enumerator: union pool, 1-for-1 then expand, `fit_max_packages_per_pair` enforced, diagnostics counters | 2d | F1 | Counters are the §2.6 contract, built in — not bolted on |
| **F3** | Dual 0–100 scorer + `fit` payload incl. **`bucket`** + aggregate sort; unranked-pair tie-break by consensus fairness (C7c); tanh comment corrected, curve pinned by value table (C7a) | 1.5d | F2 | **T3:** provenance pinned in module docstring + test: all three lenses read **raw** member boards and raw seed via `elo_to_value`/`package_value_v2` — never `shrunk_elo` (the audit's bug-3 split must not get a third variant) |
| **F4** | Post-score preference filters + R4 + C4 caps | 0.5d | F3 | Per PRD §6 |
| **F5** | Bake-off arm `fit`: roster entry behind `bakeoff_include_fit` (default 0), diagnostics into `arms_json`, `GENERATION_ORDER` appends fit **last** (arm B still first — dark fallback unchanged) | 1d | F3 | |
| **F5b** | Serve-bit split: `bakeoff_serve_fit` (default 0) — fit generates + logs but is excluded from draft participants until the bit flips | 0.5d | F5 | This is what makes S2's dark soak possible while B vs D keeps serving. Deliberately fit-only, not a general serving-roster mechanism (§9.5) |
| **F6** | Tests (list in §7) | 1d | F1–F5b | Includes the sabotage-style binding test (T1) and the uniform-columns test (T2) |
| **S-serve** | Serving re-light itself | 0d code | M1, M2 | **Knob flips only** — §4 stage table. The lane-quota fix is `bakeoff_group_size = 0`, no code change |

Total: ≈ 9.25 eng-days, one backend engineer, fits W0 with the dry run. The critical path
is F1→F2→F3→F5→F5b; M1/M2 are parallel and must merge first.

**T4 discharge (binding):** every new `model_config` key — `bakeoff_include_fit`,
`bakeoff_serve_fit`, `fit_score_scale`, `fit_w_board`, `fit_w_div`, `fit_w_cons`,
`fit_pool_consensus`, `fit_pool_div_seed`, `fit_pool_div_opp`, `fit_pool_cap`,
`fit_max_packages_per_pair`, `fit_expand_from`, `fit_min_them`, `fit_min_aggregate`,
`fit_r5_mode` — is registered in `trade_service._DEFAULT_CFG` (so `snapshot_config()`
captures it in `config_json`, which §2.3.2 depends on) **and** gets its arm-A disposition
sentence in the knob-inventory guard, of the form: *"generation knob for `trade_gen_fit`,
a module arm A never imports; no effect on MODEL_A_PROFILE output."* F5 does not merge
until `test_bakeoff_arm_a_golden.py` passes with all fifteen sentences present.

---

## 4. Staged rollout

Every value below is a `model_config` key set via `PUT /api/admin/config/<key>` — and
therefore **logged by M1**, which is why M1 lands first. Week boundaries are Mondays;
readouts are Fridays, filed to `docs/plans/fit-challenger/readouts/2026-Wnn.md`.

### W0 — S0: build + offline dry run (no serving change, no engine change)

| Knob | Value |
|---|---|
| everything serving-related | **unchanged** (`bakeoff_serve_interleaved = 0` stays) |

- Merge M1, M2, M4; then F1–F6 per the PR cuts in [PLAN.md](PLAN.md).
- Dry run: replay boards (league `1312140920132497408`, the armb-audit harness) + the
  fixture league, `fit_max_packages_per_pair = 20000`, all other fit knobs at PRD §9
  defaults. Produce the full §2.6 diagnostic set; record fixture ms.
- **Exit:** S0 success criteria (§1). Operator sets the ms fail bar from the recorded
  number (scope.md §6 open item — closes here).

### W1 — S1 entry: re-light, round R0 (this week's one engine-affecting change)

| Knob | Value | Why |
|---|---|---|
| `trade.bakeoff` | true | already the bake-off gate |
| `bakeoff_serve_interleaved` | **1** | the re-light |
| `bakeoff_group_size` | **0** | kills the composition layer entirely — the 2026-08-18 deck shrink was lane quotas leaving slots empty; `group_size = 0` reverts to the plain per-arm team draft with no quotas to under-fill. Chosen over `bakeoff_group_value_slots = bakeoff_group_size` because it removes the whole mechanism rather than one of its holes (D-086's reallocation half-fix recovered 13.8→16.0 cards; the plain draft has no holes to recover) |
| `bakeoff_deck_limit` | 30 | default, unchanged |
| `bakeoff_include_challenger` | 1 | arm D serves |
| `bakeoff_include_gen_v2` | **0** | benched (§2.1) — removes its 12-of-18 zero-card runs from the draft and its ms from the job |
| `bakeoff_include_baseline` | 0 | unchanged |
| `bakeoff_include_fit` | 0 | fit not built into prod yet |

- Tester scoping: the app is **TestFlight-only (v1.13.2)** — the entire user base is the
  tester base, so the global flag *is* tester scoping. No league allowlist is built (§9.6).
  `bakeoff_active()` already excludes pinned/targeted decks and `league_demo`.
- Tester brief goes out (accuracy PLAN Phase 2 protocol): decide ≥40 cards/week, always
  pick a decline reason, attempt ≥1 real send when close.
- **Daily** (not weekly) during W1: query 3 from §2.4. The deck-shrink tripwire (§6 row 1)
  is armed from hour one, with the revert being one knob (`bakeoff_serve_interleaved = 0`).

### W2 — R0 continues (no engine-affecting change)

- Friday: first full readout. B vs D on pooled + basis-split like-rate, decline mix,
  position balance, p95 ms.

### W3 — S2: R0 readout/decision + fit dark soak (this week's change: roster add, dark)

| Knob | Value |
|---|---|
| `bakeoff_include_fit` | **1** |
| `bakeoff_serve_fit` | **0** (dark: generates, logs, forfeits from draft) |
| `fit_*` knobs | PRD §9 defaults, except `fit_max_packages_per_pair` = the value the W0 dry run showed holds fixture arm-ms ≤ 8 s (start 20000; halve until true) |
| `fit_r5_mode` | 1 (kill — operator ruling stands) |

- Serving remains B vs D all week — the dark add changes job time, not deck content; p95
  is watched daily (§6 row 4).
- R0 verdict filed: whatever D's numbers say about `user_elo_shrink`/tier compression goes
  into the accuracy plan's Phase 3 queue **as evidence**, not as a mid-plan arm-B change.
- If the operator takes the `trade.outlook_direction` flip, this Monday is its only
  legal slot before W7 (§2.3.1).
- **Exit:** S2 success criteria (§1) — three clean dark days, ms and junk/pick bars.

### W4 — S3 entry: round R1, B vs fit (this week's change: serve swap)

| Knob | Value |
|---|---|
| `bakeoff_serve_fit` | **1** |
| `bakeoff_include_challenger` | **0** (D leaves the roster: keeps k = 2 and returns its ~2 s to the job budget; its round is done) |

### W5–W6 — R1 continues (no engine-affecting change)

- Friday readouts; running Wilson intervals on co-primary 1; no peeking-based stops except
  the pre-registered abort tripwires.

### W7 — S4: decision

- Apply §2.5 rules. File verdict + full readout. If **iterate**: the one knob change lands
  the following Monday and buys one 2-week window. If **kill**: `bakeoff_serve_fit = 0`,
  `bakeoff_include_fit = 0`, findings memo. If **promote**: next plan (F7 dual-R5 knob
  flip with the `killed[K7]` evidence in hand, `fit_min_them` tuning, and only then any
  conversation about the organic path).

**Rollback at every stage is a knob, never a deploy:** `bakeoff_serve_interleaved = 0`
restores dark mode (arm B through the normal stack); `bakeoff_serve_fit = 0` un-serves fit;
`bakeoff_include_fit = 0` un-rosters it; organic serving never touched any of this.

---

## 5. C1–C7 / T1–T4 coverage table

| ID | Concern/trap | Where this plan handles it |
|---|---|---|
| C1 | Unserved arms produce diagnostics, not accuracy | The plan's core structure: serving re-light is S1, *before* fit exists in prod; fit cannot reach W4 without the serving lane already carrying decisions. Lane-quota fix = `bakeoff_group_size = 0` (§4 W1) with the shrink tripwire armed daily (§6 row 1) |
| C2 | K7 contradicts the thesis; data against it | `fit_r5_mode` pre-wired in F1 (default 1 = kill, per the operator ruling and the mandate); `killed[K7]` is a first-class dry-run/dark field (§2.6); the F7 decision at S4 is a knob flip with evidence, not a build |
| C3 | Pooled like-rate misreads the arm | Co-primary = bucketed like-rate (`both_high`+`mixed`) + `value_giving` decline share; pooled is guardrail-only (§2.2); M3 stamps buckets on arm-B cards so the comparison is bucket-matched |
| C4 | `basis` overloaded | Ruled here for the LLD: `TradeCard.basis` keeps the PRD stamping (clients render it), but **no readout query ever splits fit by `basis`** — fit's data-availability lives in `features_json.fit.boards ∈ {both, viewer, none}` (added to the F3 payload) and analysis keys on that. `scripts/bakeoff_readout.sql` carries the comment |
| C5 | Junk/pick flooding returns through the open door | `top_q_pick_share` / `top_q_junk_share` in the §2.6 contract with numeric S2 exit bars; failure path is the PRD §10 default-off filler knob as a named iterate action, never a silent kill |
| C6 | Job budget | K3 runs last in the K-order (F1); `fit_max_packages_per_pair` staged from dry-run evidence (§4 W3); p95 bars at S2 (30 s) with `_JOB_HARD_TIMEOUT = 60` headroom; relief valve is the include knob; gen_v2 and challenger leave the roster when not being read, returning their ms |
| C7a | tanh comment wrong (score(400) ≈ 88, not 84) | F3 fixes the comment, keeps `fit_score_scale = 400`, and pins the curve with a value-table test (`test_fit_score_curve_pinned`: 0→50, ±200→73.1/26.9, ±400→88.4/11.6) |
| C7b | `composite_score` 0–200 must never be compared cross-arm as magnitude | Draft is rank-based (verified in `bakeoff_runner.py` draft path); F6 adds `test_draft_rank_only` (sabotage-style: double one arm's composite scale, assert identical draft); readout SQL never selects `composite_score` cross-arm |
| C7c | Unranked-pair aggregate ≈ 100 mirror | F3 tie-breaks unranked-pair cards by consensus fairness; documented in the module docstring; `test_unranked_pair_aggregate_mirror` asserts the mirror and the tie-break |
| T1 | Import-time binding no-op | F1 imports the module, not the names (`ts.overpay_ok(...)`); F6's `test_fit_gate_binding_sabotage` monkeypatches `trade_service.overpay_ok` to always-kill and asserts fit output collapses — proving the live binding, per HANDOVER trap 8's "sabotage-verify" standard |
| T2 | `executemany` first-row column drop | No new `deck_impressions` columns (fit rides `features_json`, which every row already writes); M3 writes `fit_diag` on **every** bake-off row (null-valued where scoring failed, never absent); F6's `test_impressions_uniform_columns` asserts identical key sets across a mixed-arm save batch |
| T3 | Provenance (raw vs shrunk) | F3 pins in writing + test: all lenses read raw member boards and raw seed; `test_fit_lens_provenance_raw` feeds a fixture where raw and shrunk diverge and asserts the raw number |
| T4 | Knob-inventory guard fails by name | §3's T4 discharge: all 15 keys registered in `_DEFAULT_CFG` with disposition sentences; F5 blocked on the guard passing. Side benefit: registration puts every fit knob into `snapshot_config()` → `config_json`, which the contamination diff (§2.3.2) requires |

---

## 6. Failure-mode table

| # | Silent failure | Detection signal | Tripwire (numeric, pre-armed) |
|---|---|---|---|
| 1 | **Deck-shrink recurrence** (the 2026-08-18 revert cause): quota holes or arm forfeits shrink served decks and testers quietly see 10-card decks | Daily query 3 (§2.4): median `deck_size` on interleaved runs | median < 20 → investigate same day; median < 15 on 2 consecutive days → `bakeoff_serve_interleaved = 0` same day, GOTCHAS entry. Baseline: arm-B-only median 26.5 |
| 2 | **`executemany` column drop**: a per-card key stamped on some rows silently vanishes for the whole deck (HANDOVER trap 3) | `test_impressions_uniform_columns` in CI; readout query 1 returning NULL bucket for > 5% of fit-arm rows | any NULL `fit.bucket` on a `model_arm='fit'` row → data bug, window suspect until explained |
| 3 | **Import-binding no-op** (T1): fit "calls" live predicates but bound-by-value copies run; knob changes and D-096-style fixes silently don't propagate | `test_fit_gate_binding_sabotage` (CI, permanent); dark-soak cross-check: `killed[K4]` must move when `max_overpay_frac` is test-bumped on the fixture | sabotage test red = merge blocked; it is the tripwire |
| 4 | **Timeout starving an arm**: fit runs long, job crosses `_JOB_HARD_TIMEOUT = 60` and is marked **error** — the tester gets *no deck*, which looks like an app bug, not a bake-off bug | daily p95 `total_ms`; `_trade_jobs` error count; per-arm ms in `arms_json` | p95 > 30 s at S2 → halve `fit_max_packages_per_pair`; p95 > 45 s or any timeout-error rate > 2% of runs → `bakeoff_include_fit = 0` (dark) / `bakeoff_serve_interleaved = 0` (served) same day |
| 5 | **Score-scale leakage into cross-arm comparisons**: fit's 0–200 composite or its 0–100 stamps get read as magnitudes against arm B's composite, or `fit_diag` influences a ranking path | `test_draft_rank_only` (C7b); `test_fit_diag_inert` (M3): delete `fit_diag` from every card, assert served deck identical; readout SQL review — no query selects composite cross-arm | either test red = merge blocked; any new readout query touching `composite_score` across arms is rejected in review by the M2 runbook rule |
| 6 | **Re-ranker touches an interleaved deck**: position balance destroyed silently; you measure deck position, not model quality (HANDOVER trap 5) | M4 assertion: interleaved runs must carry the bypass marker; position-balance query 4 | any interleaved run without bypass → **discard the run, not caveat it**; recurring → stop serving |
| 7 | **Interleaver position imbalance** (subtler than #6: draft order bug rather than re-ranker) | query 4: per-arm mean `card_index` within window | abs(Δ mean position) > 2 between served arms → interleaver bug; window suspect |
| 8 | **Knob drift mid-window** (five waves in 5 days is the historical base rate) | M1 log + §2.3.2 config-snapshot diff every Friday | any engine-affecting key changed mid-window → window discarded; the readout says so in its header |
| 9 | **Ghost rows polluting rates** | all denominators filter `is_ghost` (§2.2); readout sanity row reports ghost share | ghost share deviating > 5pp from its configured rate → holdout logic suspect |
| 10 | **Tester supply collapse** (n never arrives; the round silently becomes anecdote) | weekly decided-cards count per arm in the readout header | < 250 total decided in a week → extend the round 1 week (once) and tell the operator; do not call results at partial n |
| 11 | **`fit` scorer version skew** (M3 stamps computed by an older scorer than the serving arm after an iterate-knob change) | `fit_diag.ver` / `fit.ver` compared in query 1 | mixed versions inside one window → bucket comparison invalid for that window; readout falls back to pooled + flags it |

---

## 7. Evidence plan per D-056

No simulator, no Maestro. Three evidence classes:

**1. Structural/unit (CI, `backend/tests/test_trade_gen_fit.py` + friends):**
- `test_k1_shapes` — legal/illegal package shapes incl. 3-for-1 live, 4-any dead.
- `test_k2_matches_live_c3` — shared fixture: 2026-1st↔2027-1st dead; two late 2nds for a
  1st alive (scope.md list).
- `test_k3_both_rosters_all_paths` — 0-RB aftermath killed on either side.
- `test_negative_surplus_scores` — them < 50, card survives.
- `test_unranked_partner_l3_only` — `lenses.them.board = null`.
- `test_prefs_filter_not_kill` — untouchable id present in `enumerated`, absent from output.
- `test_pool_cap_respected` — `enumerated ≤ fit_max_packages_per_pair`.
- `test_fit_score_curve_pinned` (C7a), `test_unranked_pair_aggregate_mirror` (C7c),
  `test_draft_rank_only` (C7b), `test_fit_gate_binding_sabotage` (T1),
  `test_impressions_uniform_columns` (T2), `test_fit_lens_provenance_raw` (T3),
  `test_fit_diag_inert` (M3/leakage), `test_serve_fit_bit_excludes_from_draft` (F5b),
  `test_fit_r5_mode_knob` (C2: mode 0 scores instead of kills, default 1 kills).
- Knob-inventory guard green with 15 new disposition sentences (T4).

**2. Code-walk proofs (file:line-cited, filed with the PRs):**
- Organic isolation: `_generate_trades_impl` contains no reference to `trade_gen_fit`;
  a grep-based test asserts the forbidden import on the organic branch (scope.md §3), plus
  a fixture generate with `trade.bakeoff` off shown byte-identical.
- The serving path trace for `bakeoff_serve_fit`: fan-out includes fit, draft participants
  exclude it, `arms_json` records it — three cited lines.
- M3 stamp site shown to run after ranking and inside try/except.

**3. Runtime evidence (the only kind mobile gets now):**
- W0 dry-run TEST_LEDGER entry: fixture ms, enumerated vs arm-B prune size,
  `one_sided_pct`, bucket mix, junk/pick shares (scope.md §3's dry-run row).
- S2 dark-soak TEST_LEDGER entry: 3 days of prod diagnostics, p95 ms.
- Manual TestFlight checklist for the operator at S1 re-light (specific enough to catch a
  regression): open a tester league → generate an untargeted deck → deck has ≥ 20 cards →
  cards show mixed arms in the first 10 (visible via the readout, not the UI) → decide 5
  cards with reasons → verify 5 `deck_outcomes` rows with non-null `model_arm` → pin a
  player and confirm the pinned deck is NOT interleaved (`bakeoff_active` exclusion) →
  toggle nothing else.
- Weekly readout files are themselves the standing runtime evidence for S3.

**Gates posture:** full gates, no express (scope.md §5 already says so; this scope touches
schema (M1), config surface, and analytics — triple bright-line). Scope blocks: fit's
exists ([scope.md](scope.md)); two new ones owed — `scope-measurement.md` (M1–M4: schema +
readout) and `scope-serving.md` (the re-light: user-visible serving change, knob values,
revert playbook). CI green (pytest, `tsc --noEmit`, testid-lint) before every merge;
`FTF_SKIP_SIM_GATE=1` standing posture with evidence noted, per D-056.

---

## 8. Docs and living-memory updates owed

| Artifact | Update |
|---|---|
| `docs/config-reference.md` | 15 fit/bakeoff keys (F5/F5b), M1 behavior of `PUT /api/admin/config` |
| `docs/data-dictionary.md` | `model_config_changes` table, `model_config.updated_at`, `arms_json['fit'].diagnostics` keys, `features_json.fit` / `.fit_diag` |
| `docs/api-reference.md` | additive `fit` object on TradeCard (bake-off only); admin-config route now logs |
| `docs/plans/three-model-bakeoff/PLAN.md` | addendum: arm `fit`, serve-bit, `group_size = 0` serving posture |
| `docs/cross-client-invariants.md` | n/a — no client-facing enum/color/threshold changes in v1 (fit payload is additive and unrendered) |
| `docs/adr/` | D-095-proposed ADR per scope.md ("fit-challenger is a generator, not a profile") + one new ADR: "pairwise rounds, max two served arms, arm B always seated" (the §2.1 ruling is architecture for every future arm) |
| `living-memory/DECISIONS.md` | D-entries (grep max+1 immediately before writing — HANDOVER trap 9): the k=2 ruling; `bakeoff_group_size = 0` as the serving posture; C4 basis ruling; gen_v2 bench condition |
| `living-memory/LLD.md` | conventions: preferences filter after score (scope.md); fit analysis keys on `fit.boards` never `basis`; every fit knob registered in `_DEFAULT_CFG` |
| `living-memory/CHANGELOG.md` | dated H2 per merged PR and per stage transition |
| `living-memory/TEST_LEDGER.md` | W0 dry run, S2 soak, each Friday readout pointer |
| `living-memory/NEXT.md` | R0/R1 schedule, gen_v2 re-entry condition, F7 decision point at S4 |
| `living-memory/HANDOFF.md` | overwritten at each session end mid-build |
| `docs/plans/fit-challenger/readouts/` | new directory, one file per readout week |
| Accuracy plan reconciliation | `trade-engine-accuracy/PLAN.md` gets a one-line addendum mapping this plan's W1 = its Phase 1.1, W1–W6 = its Phase 2 loop, and noting its Phase-3 queue is frozen during rounds except the W3 slot |

---

## 9. Cuts and defers

What this draft explicitly cuts or defers relative to the natural build-first version of
the same scope, and the reasoning — this is where the cross-critique should engage.

1. **CUT: serving three or four arms at once.** Build-first instinct is "everything is
   built, roster it all and let the data sort it out." The §2.1 table says k=3 pushes a
   10pp answer to 4.5 weeks — past the 3-week contamination ceiling this repo's own
   history sets — and k=4 answers nothing. Four arms served = four diagnostics streams and
   zero verdicts. Two arms, pairwise rounds, B always seated.
2. **DEFER: gen_v2 serving, indefinitely with a condition.** It zero-carded 12 of 18 runs
   off the boarded league; serving it to boardless testers spends decision budget proving
   a supply fact we already have from dark diagnostics. Re-entry condition is written
   (≥2 leagues with 3+ boards) so this is a gate, not a burial.
3. **DEFER: every arm-B engine change during rounds** (`user_elo_shrink = 0`, soft R5,
   tier compression, the three uncalibrated floors). Build-first would ship the two
   measured levers now — they're "known wins" (96.3→63.2%). But they are known to move a
   *replay statistic on six boards from one league*, not like-rate; arm D exists precisely
   to read them on users first, and shipping them mid-round destroys both the round and
   the lever's own attribution. They queue behind R0's verdict, per accuracy PLAN 0.4.
4. **DEFER: `trade.outlook_direction` flip** to the W3 boundary at earliest (§2.3.1). One
   engine-affecting change per window; the re-light and roster moves consume the slots.
5. **CUT: a general serving-roster mechanism.** F5b is a single fit-only bit
   (`bakeoff_serve_fit`), not a `bakeoff_serve_arms` framework. Build-first would
   generalize; the general mechanism is more serving-path code on the exact line that
   failed on 2026-08-18, for a need only one arm currently has. Generalize on the second
   consumer, not the first.
6. **CUT: tester-league allowlist for serving.** The app is TestFlight-only; the user base
   *is* the tester base. An allowlist adds a config surface and a failure mode (empty
   allowlist = silent dark) for zero current scoping value. Revisit only when a public
   release date exists — it becomes launch-blocking then, and NEXT.md carries that note.
7. **DEFER: raising `_JOB_HARD_TIMEOUT`.** Build-first pads the budget up front. Padding
   hides cost growth; the dark soak measures it instead, and the relief valves (package
   cap, include knobs) act on the cause. The timeout moves only if S2's measured p95 says
   the work is legitimate and near the line (HANDOVER §5.2 anticipated exactly this).
8. **DEFER: `fit_min_them`, filler knob, F7 dual-R5, weight retuning** — all pre-wired or
   default-off, none turned on until the dry run / R1 produces the number that justifies
   each (`you_tilt` like-rate, junk shares, `killed[K7]`). The PRD already leans this way;
   this plan makes each one's activating evidence explicit in §2.5/§2.6.
9. **CUT: any client rendering of fit scores in v1** (card meters, bucket badges).
   Backend-only is a binding constraint, but the deeper reason is measurement: R1 must
   compare *generators*, and changing the card surface for one arm's cards would confound
   presentation with generation — the exact layer confusion the accuracy plan says has
   gone unmeasured. Card-evidence work re-enters after S4 on its own plan.
10. **CUT: composite/aggregate cross-arm dashboards.** Any readout artifact that puts
    fit's 0–200 next to arm B's composite as magnitudes is banned by the M2 runbook rule
    (C7b); rankings and rates only.

---

*Draft B ends. Rival draft (build-first) should be critiqued against §2.1 (arm count),
§4 (knob staging and the W-boundary change control), and §6 (whether each of its serving
changes has a pre-armed tripwire or only a post-hoc explanation).*
