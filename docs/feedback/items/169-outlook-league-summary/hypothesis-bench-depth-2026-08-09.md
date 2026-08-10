# #169 Outlook Odds — Hypothesis 1c: Bench Depth vs Season-Long Fragility

**Date:** 2026-08-09 · **Author:** hypothesis-validation agent · **Branch:** `teardown-remediation` (worktree)
**Subject:** operator hypothesis 1c against the dark playoff/championship-odds engine's preseason default (`RosterValueStrength`, `backend/outlook/strength.py`)
**Purpose:** decide whether "positional bench depth" should ever enter the outlook model as a variance-reduction term. Empirical validation only — no product code, no flag, no `backend/outlook/` change.

> **Verdict in one line:** **NOT SUPPORTED at this sample size.** The one
> statistically distinguishable effect (positional next-man-up value vs
> playoff berth, controlled r = +0.17) does not survive the mechanism test —
> it is not concentrated in team-seasons that actually suffered
> absences/injuries — and the metric the operator explicitly said mattered
> most (position-specific depth, not raw bench total) shows the **weakest**
> signal of the three tested. **Do not spec a depth-based σ adjustment on this
> evidence.**

---

## Table of contents

- [1. What was tested](#1-what-was-tested)
- [2. Method](#2-method)
- [3. Results — raw and controlled](#3-results--raw-and-controlled)
- [4. Mechanism test — does the effect track absences?](#4-mechanism-test--does-the-effect-track-absences)
- [5. Sample size and power](#5-sample-size-and-power)
- [6. Data limitations (read before trusting any number above)](#6-data-limitations-read-before-trusting-any-number-above)
- [7. Verdict and recommendation](#7-verdict-and-recommendation)
- [8. Reproducing this report](#8-reproducing-this-report)

---

## 1. What was tested

**Operator hypothesis 1c:** "Strong replacements on the bench per position
suggest less injury fragility and stronger season-long results." Prediction:
teams whose bench holds high-value players **at the positions they start**
(positional depth, not raw bench total) outperform their
starting-lineup-value-implied expectation over a full season, because
injuries/byes cost them less.

Three depth metrics were computed for every team-season and tested against
four outcomes, raw and controlled for total roster quality, plus a direct
test of the injury/absence mechanism the hypothesis claims drives the effect.

| Depth metric | Definition |
|---|---|
| `bench_raw_sum` | Sum of dynasty value of every non-starting player on the roster |
| `next_man_up_total` | Sum, over QB/RB/WR/TE, of the value of the best **non-starting** eligible player at that position — the operator's actual framing |
| `dropoff_ratio_avg` | Mean, over QB/RB/WR/TE, of (next-man-up value ÷ the weakest starter's value at that position) |

| Outcome | Definition |
|---|---|
| `win_residual` | Actual regular-season wins − preseason-model-implied wins |
| `points_residual` | Actual total regular-season points − preseason-model-implied points |
| `playoff_actual` | 1 if the team made the real playoff field, else 0 |
| `scoring_var` | Population variance of the team's 14 weekly scores — **the most direct test of the fragility claim**: deeper teams should show *lower* variance |

## 2. Method

### Data and reuse

Same 6 completed league-seasons as the #169 calibration backtest
(`docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`):
`lakeview-2025`, `lakeview-2024`, `ffv3-2025`, `ffv3-2024`, `ffv3-2023`,
`ffv3-2022` — 12 teams each, 72 team-seasons, all offline from
`backend/tests/fixtures/outlook-calibration/`.

This script **imports, not reimplements**, the app's own logic:

- `backend.outlook.strength.starting_lineup_value` and `_FLEX_ELIGIBLE` — the
  greedy best-lineup assignment and position-eligibility table. A local
  slot-by-slot decomposition (needed to read off *which* player fills each
  slot and what's left in the pool, which the aggregate function doesn't
  expose) replicates the exact same dedicated-then-flex order and tie-break
  rule, and its own summed output is **asserted equal** to
  `starting_lineup_value()`'s return value for all 72 team-seasons — the
  decomposition never diverges from the shipped algorithm.
- `backend.outlook.pipeline.run_outlook` — run at `completed_weeks = 0`
  (preseason) to get the model's implied wins/points/playoff odds, through
  the exact same `RosterValueStrength` path the shipped preseason default
  uses (`payload["meta"]["strength_source"] == "roster_value"` is asserted).
- `backend.data_loader.load_consensus_maps` (DynastyProcess CSV → Elo, via
  the `FTF_DP_VALUES_FILE` hermetic seam) and
  `backend.trade_service.elo_to_value` — the exact two-step affine pipeline
  `RosterValueStrength` is fed in production.
- `scripts/outlook_calibration_backtest.py`'s `as_of()`, `truth()`,
  `load_fixture()`, `offline_fetch()`, `build_full_state()` — the
  already-validated as-of rewind and ground-truth extraction.

### New fixtures (offline, committed)

- `backend/tests/fixtures/outlook-hypotheses/players-slim.json` — Sleeper
  `player_id → {full_name, position}` for the 870 unique player ids rostered
  across the 6 seasons, sliced from a fresh capture of the public
  `/v1/players/nfl` bulk endpoint (2026-08-09; the older on-disk dev cache
  covered only 68% of these ids — mostly retired/inactive players from the
  2022–2024 seasons — so a fresh pull was necessary for full coverage).
- `backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv`
  — a fresh capture of DynastyProcess's `values-players.csv` (677 rows,
  scrape_date 2026-08-07), the same file `data_loader._fetch_dynasty_process`
  fetches live in production.
- `backend/tests/fixtures/outlook-hypotheses/hypothesis-1c-raw-results.json`
  — the 72 per-team-season rows backing every number in this report.

### Value board coverage (read this before trusting any value number)

The DP CSV prices **only QB/RB/WR/TE** (by design — same as production).
Matched 474/592 (80%) of the 6 seasons' skill-position players by normalized
name; 0/278 IDP/K players (Lakeview has none; FFv3 — "1QB + IDP" — starts 8
IDP/K slots that the app's own value model prices at exactly 0, same as it
would in production for the same league). Unmatched skill players (mostly
retired-since-then reserves/waiver churn) default to value 0.0 via
`starting_lineup_value()`'s own `.get(pid, 0.0)` fallback — identical
behavior to how the shipped pool treats an unranked player. Per-position depth
metrics are reported for QB/RB/WR/TE only; IDP/K slots contribute 0 to both
numerator and denominator by construction and are excluded from the ratio.

### Absence/injury proxy

Per the brief: a rostered **starter** scoring exactly 0.0 points in a week it
started, from Sleeper's per-player weekly `players_points` + `starters`
(committed in the existing calibration fixtures — no new fetch needed).
Counted per roster across the 14 regular-season weeks. Range across the 72
team-seasons: 0–23 events, median 5. **This proxy is acknowledged as
imprecise** — a legitimately bad game (a kicker missing every kick, a TE shut
out) also produces a 0, and it cannot distinguish "genuinely absent" from
"played and scored nothing" — the brief calls it a "usable" proxy, not a
clean one, and §6 elaborates on the consequence.

### Statistics

Pure Python (matches the calibration backtest's zero-dependency convention;
no numpy/scipy in the shipped script). Pearson r with a Fisher-z 90% CI
treating team-seasons as independent (an approximation — team-seasons inside
one league share context), a cluster bootstrap 90% CI resampling by
league-season (6 clusters — wide, not precise, same caveat as the calibration
report's bootstrap), a partial correlation controlling for `starter_total`
(`starting_lineup_value()`'s own output — the direct measure of "total roster
quality"), and a permutation test on the difference in r between
high-absence and low-absence team-season subgroups (median split, 5000
resamples) for the mechanism test.

## 3. Results — raw and controlled

n = 72 team-seasons for every cell (36 playoff positives, 6 title positives —
title odds are not tested here; the calibration report already showed 6
champion events supports no inference at all).

### `bench_raw_sum` (total bench value, position-agnostic)

| outcome | raw r | raw 90% CI (Fisher / cluster-boot) | controlled r (partial on starter value) | controlled 90% CI (cluster-boot) |
|---|---|---|---|---|
| win_residual | −0.026 | [−0.220, +0.170] / [−0.259, +0.218] | +0.056 | [−0.148, +0.247] |
| points_residual | −0.180 | [−0.362, +0.016] / [−0.344, −0.019] | −0.123 | [−0.291, +0.062] |
| playoff_actual | **+0.274** | [+0.082, +0.445] / [+0.080, +0.456] | +0.023 | [−0.117, +0.193] |
| **scoring_var** | −0.040 | [−0.234, +0.156] / [−0.179, +0.136] | **−0.252** | **[−0.428, −0.023]** |

### `next_man_up_total` (the operator's actual framing — position-specific)

| outcome | raw r | raw 90% CI (Fisher / cluster-boot) | controlled r | controlled 90% CI (cluster-boot) |
|---|---|---|---|---|
| win_residual | +0.056 | [−0.141, +0.249] / [−0.183, +0.295] | +0.124 | [−0.096, +0.330] |
| points_residual | −0.123 | [−0.311, +0.074] / [−0.270, +0.070] | −0.070 | [−0.216, +0.144] |
| playoff_actual | **+0.333** | [+0.147, +0.496] / [+0.157, +0.492] | **+0.168** | **[+0.026, +0.339]** |
| **scoring_var** | −0.081 | [−0.272, +0.117] / [−0.187, +0.106] | −0.237 | [−0.414, +0.010] |

### `dropoff_ratio_avg` (next-man-up ÷ weakest starter, per position, averaged)

| outcome | raw r | raw 90% CI (Fisher / cluster-boot) | controlled r | controlled 90% CI (cluster-boot) |
|---|---|---|---|---|
| win_residual | −0.035 | [−0.229, +0.161] / [−0.229, +0.220] | −0.101 | [−0.374, +0.261] |
| points_residual | +0.034 | [−0.163, +0.228] / [−0.105, +0.213] | −0.029 | [−0.299, +0.247] |
| playoff_actual | −0.205 | [−0.385, −0.010] / [−0.369, −0.019] | −0.008 | [−0.230, +0.328] |
| scoring_var | −0.121 | [−0.309, +0.077] / [−0.335, +0.113] | +0.005 | [−0.216, +0.215] |

**Reading these together:**

1. **The raw `playoff_actual` correlations (+0.27 to +0.33) collapse toward
   zero once you control for `starter_total`** — the classic "good teams have
   good benches" confound the brief specifically warned about. `bench_raw_sum`
   goes from +0.274 (raw) to +0.023 (controlled), essentially fully explained
   by team quality.
2. **`next_man_up_total` vs `playoff_actual` is the one cell that survives
   controlling** (+0.168, CI [+0.026, +0.339] excludes 0) — modest evidence of
   a positional-depth effect on playoff berth beyond raw team strength.
   §4 shows this does **not** trace to the injury mechanism.
3. **`scoring_var` — the most direct test of the fragility claim — has raw
   correlations indistinguishable from 0 for all three metrics.** Controlling
   for team quality moves `bench_raw_sum` (−0.252, CI marginally excludes 0)
   and `next_man_up_total` (−0.237, CI marginally includes 0) in the
   hypothesis-consistent direction (more depth → lower variance), but
   **`dropoff_ratio_avg` — arguably the metric closest to the operator's
   stated mental model — shows no effect at all (+0.005 controlled)**, and
   even the two metrics with a hint of signal don't cleanly clear their
   interval.
4. **The operator explicitly said "positional depth, not raw bench total" is
   what should matter.** On `scoring_var` — the outcome that most directly
   tests the claim — `bench_raw_sum` (the metric they said *shouldn't* matter)
   shows a *stronger* controlled effect than `next_man_up_total` or
   `dropoff_ratio_avg` (the metrics they said *should*). That is backwards
   from the hypothesis as stated.

## 4. Mechanism test — does the effect track absences?

If depth matters because of injuries, the effect should concentrate in
team-seasons that actually suffered absences. Median split on `absence_events`
(32 high, 40 low), permutation test (5000 resamples) on the difference between
the two subgroups' correlation with each outcome:

| depth metric | outcome | r (high-absence, n=32) | r (low-absence, n=40) | diff | permutation p |
|---|---|---|---|---|---|
| bench_raw_sum | win_residual | −0.071 | −0.042 | −0.029 | 0.899 |
| bench_raw_sum | scoring_var | +0.041 | −0.091 | +0.131 | 0.565 |
| next_man_up_total | win_residual | +0.010 | +0.036 | −0.026 | 0.908 |
| next_man_up_total | scoring_var | +0.055 | −0.156 | +0.211 | 0.306 |
| dropoff_ratio_avg | win_residual | −0.252 | +0.220 | −0.472 | **0.065** |
| dropoff_ratio_avg | scoring_var | −0.260 | −0.026 | −0.234 | 0.313 |

**No cell shows a significant, hypothesis-consistent interaction.** If the
mechanism were real, depth should help *more* (a more positive/less negative
r) in the high-absence group; instead every diff is either near-zero-and-flat
or points the wrong way. The closest to conventional significance
(`dropoff_ratio_avg` vs `win_residual`, p = 0.065) is **backwards**: teams
with more absences got a *worse* payoff from a good drop-off ratio than teams
with fewer absences (r = −0.252 vs +0.220). At n = 32/40 per group this is not
strong evidence of anything — but it is certainly not corroboration.

This directly answers the brief's diagnostic question: **"a depth effect with
no absence interaction is suspicious (probably just 'good teams have good
benches')"** — that is exactly what §3's controlled-vs-raw collapse already
suggested, and §4 confirms it independently. The one surviving controlled
effect (`next_man_up_total` vs `playoff_actual`, +0.168) has no absence
interaction to lean on either (diff −0.026, p = 0.908 on win_residual; the
scoring_var read is directionally hypothesis-consistent but p = 0.306, not
distinguishable from noise).

## 5. Sample size and power

72 team-seasons across 6 league-seasons (2 leagues) is the entire available
sample — this analysis cannot be scaled up without more captured Sleeper
dynasty league history. What it can and cannot support:

- **Can detect:** a raw Pearson r of roughly ±0.23 or larger at conventional
  90% confidence (the narrowest CIs above, e.g. `next_man_up_total` vs
  `playoff_actual`, span about ±0.17 around the point estimate). Effects
  smaller than that are indistinguishable from 0 at this n.
- **Cannot detect:** anything that requires disaggregating by league format
  (2 formats, 36 team-seasons each — already the whole sample split in half),
  or the title/championship question (6 positive events, already shown
  uninformative in the calibration report).
- **The cluster-bootstrap CIs are the honest ones.** With only 6
  league-season clusters, both the Fisher-z and cluster-bootstrap intervals
  are reported side by side; where they disagree materially (they mostly
  don't here) the cluster-bootstrap should be trusted, since team-seasons
  inside one league are not independent draws.
- **Absence-events median split (32/40) is smaller still.** The permutation
  test in §4 has limited power to detect anything short of a large
  interaction — a small-to-moderate true interaction could exist and not
  reach p<0.10 here. The honest reading is "no evidence for," not "proof
  against."

## 6. Data limitations (read before trusting any number above)

1. **Roster snapshot is end-of-season, not preseason.** Sleeper exposes no
   historical rosters — the calibration report already flagged this for
   `RosterValueStrength` generally ("not backtestable... FTF has no dated
   value snapshots"). This script inherits that limitation rather than
   working around it: every depth metric here is computed on the **final**
   roster Sleeper still reports for each closed league instance, which
   includes every in-season waiver add/drop. The planned mitigation — a
   low-transaction subsample using `total_moves` — turned out to be
   **unusable**: Sleeper reports `total_moves = 0` for all 72 team-seasons
   (the field is evidently not retained for completed past-season league
   instances). There is no way, from this data, to tell which team-seasons'
   captured roster is close to what it looked like at kickoff.
   - This cuts both ways for the mechanism test specifically: a team that
     suffered real injuries would often stream waiver replacements, so its
     captured "bench" partly reflects reactive roster management *in
     response to* absences rather than a preseason depth choice — the reverse
     of the causal direction the hypothesis claims. This is a plausible
     contributor to why §4 found no clean interaction.
2. **Player values are current (2026-08-09), not point-in-time.** The DP
   value board prices players as of today, applied retroactively to 2022–2025
   rosters. A player who retired since is worth 0 in this analysis regardless
   of what they were actually worth that season; a since-broken-out player is
   worth more than they were at the time. This is the same limitation the
   calibration report documented for the preseason `roster_value` source
   generally (§5b of that report: a current value board and a same-season
   projection feed already disagree with each other on the superflex league).
3. **The absence proxy is noisy** (§2) — a legitimate zero-point game is
   indistinguishable from an actual absence in this data. IDP positions in
   particular (FFv3's DL/LB/DB/K slots) routinely post literal 0s in normal
   variance, not just injury; those slots are correctly excluded from the
   *depth* metrics (§2, "Value board coverage") but they are **not** excluded
   from the *absence* count, since the brief's absence proxy is about
   starters generally, not skill-position starters specifically. This likely
   adds noise (not a directional bias toward or away from the hypothesis) to
   §4's counts, which may partly explain why no clean interaction emerged.
4. **Two leagues, two formats.** Everything here is Lakeview (SF/TEP) and
   FFv3 (1QB + IDP) — the same generalization caveat as the calibration
   report applies unchanged.

## 7. Verdict and recommendation

**NOT SUPPORTED, at this sample size, with this data.**

- The raw, uncontrolled correlations for `playoff_actual` looked promising
  (+0.27 to +0.33) but are substantially explained by `starter_total` — teams
  with strong starting lineups also tend to have strong benches, and
  controlling for that erases most of the raw signal.
- The one cell that survives controlling — `next_man_up_total` vs
  `playoff_actual` (+0.168, CI excludes 0) — does not trace to the claimed
  injury/absence mechanism (§4): it is not larger in team-seasons that
  actually suffered more absences. It more plausibly reflects a residual
  "well-managed rosters are well-managed everywhere" effect not fully
  captured by `starter_total` alone, not injury protection specifically.
- The metric the operator explicitly said should matter most —
  position-specific depth (`next_man_up_total`, `dropoff_ratio_avg`) rather
  than raw bench total — shows the **weakest**, not the strongest, evidence
  on `scoring_var`, the outcome that most directly tests the fragility claim.
- The mechanism test (§4) provides no corroboration anywhere, and one cell
  trends opposite to the predicted direction (not statistically decisive at
  p = 0.065, but not supportive either).

**Recommendation: do not spec a bench-depth σ (or μ) adjustment into the
outlook model from this evidence.** Implementing it would mean tuning a new
knob against noise the mechanism test could not distinguish from zero, on a
metric (positional depth) that performed worse than the naive alternative
(raw bench sum) it was supposed to beat. If the operator wants to keep this
alive, the two things that would most change the picture, in order of
leverage:

1. **A genuine preseason roster snapshot.** Nothing here would need to change
   methodologically — swap the "final roster" input for a week-1 (or
   pre-draft) roster capture the moment FTF starts recording dated dynasty
   snapshots (already an open gap per the calibration report), and re-run
   this exact script.
2. **A real injury signal instead of the 0-point proxy.** Sleeper's player
   metadata carries `injury_status`; if a historical weekly snapshot of that
   field were ever captured, it would directly answer "was this player
   actually out" instead of inferring it from a zero score, which §6 shows is
   the analysis's weakest link.

Absent those, more league-seasons (the same lever the calibration report
recommends for the title-odds question) would tighten the confidence
intervals here too, but would not fix the roster-snapshot or absence-proxy
problems, which are data-availability limits, not sample-size limits.

## 8. Reproducing this report

```bash
python3 scripts/outlook_hypothesis_bench_depth.py
```

Fully offline — reads only committed fixtures. No network, no DB writes, no
change to `backend/outlook/` or any feature flag.

| Artefact | Path |
|---|---|
| Analysis script | `scripts/outlook_hypothesis_bench_depth.py` |
| Sleeper player id → name/position (slim, 870 ids) | `backend/tests/fixtures/outlook-hypotheses/players-slim.json` |
| DynastyProcess values snapshot (2026-08-09 capture) | `backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv` |
| Raw per-team-season results (72 rows) backing every table above | `backend/tests/fixtures/outlook-hypotheses/hypothesis-1c-raw-results.json` |
| League-season fixtures (reused, not modified) | `backend/tests/fixtures/outlook-calibration/` |
| Governing calibration report | `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md` |

Test posture: backend suite unaffected — this is a new, standalone script
plus new fixtures under `backend/tests/fixtures/outlook-hypotheses/`; no
existing test, route, schema, or flag was touched. Full suite re-run before
commit: see `living-memory/TEST_LEDGER.md`.
