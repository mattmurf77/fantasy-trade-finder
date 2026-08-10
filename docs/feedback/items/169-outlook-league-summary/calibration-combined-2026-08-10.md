# #169 Outlook Odds — Combined Post-Fix Calibration

**Date:** 2026-08-10 · **Author:** combined re-measurement agent · **Branch:** `outlook-combined-calibration`
**Subject:** the definitive calibration picture for `backend/outlook/` after the BUG-1 / BUG-2 / BUG-3 / BUG-5 fix wave, with both offline harnesses finally wired to the settings the engine now models.
**Scope guard:** `outlook.odds` is untouched and still dark. No flag, no `config/features.json`, no `model_config`, no UI or behaviour change anywhere.

> **Why this document exists.** Four bugs were fixed on 2026-08-09/10 by three
> parallel agents. Each measured its own delta against its own branch, and each
> flagged that a combined re-measurement was needed. Two wiring gaps also had to
> close before any combined number could be trusted:
> **(1)** `scripts/outlook_calibration_backtest.py` never passed
> `playoff_seed_type` into the brackets it built, so it kept scoring the four
> FFv3 seasons — every one of them a `playoff_seed_type: 0` FIXED bracket —
> under the reseeding rule that league does not use; **(2)** `lineup_pricing()`
> existed but nothing consumed it, so an IDP league's payload carried an
> unqualified whole-lineup number. Both are closed. Everything below is a
> single, seed-type-aware, median-match-aware, IDP-labelled run.

> **The answer in one line:** the wave bought a **large, real improvement in
> playoff odds** (Brier 0.1113 → 0.0997 pooled; 0.0548 → 0.0372 at week 12) and
> **nothing at all on title odds** (0.0725 → 0.0732, skill CI still spans zero).
> The over-confidence that blocked showing a raw percentage **survived the
> fixes** — and the preseason lower confidence bound got *worse*, not better
> (+4.1 % → **+2.9 %**). **Bands, not percentages, stands. Gate at week 6 for
> numbers, week 0 for bands, never week 3.**

---

## Table of contents

- [1. What changed, and what the change was worth](#1-what-changed-and-what-the-change-was-worth)
- [2. Method — what is different from the two prior reports](#2-method--what-is-different-from-the-two-prior-reports)
- [3. In-season results (as-of weeks 3/6/9/12)](#3-in-season-results-as-of-weeks-36912)
- [4. Preseason results (as-of week 0)](#4-preseason-results-as-of-week-0)
- [5. Calibration tables — did the over-confidence survive?](#5-calibration-tables--did-the-over-confidence-survive)
- [6. Before/after against the published pre-fix numbers](#6-beforeafter-against-the-published-pre-fix-numbers)
- [7. Decision 1 — bands vs percentages](#7-decision-1--bands-vs-percentages)
- [8. Decision 2 — the gate: week 0, 3, or 6?](#8-decision-2--the-gate-week-0-3-or-6)
- [9. What remains unvalidated](#9-what-remains-unvalidated)
- [10. Corrections issued to prior documents](#10-corrections-issued-to-prior-documents)
- [11. Reproducing this report](#11-reproducing-this-report)

---

## 1. What changed, and what the change was worth

Five changes separate this measurement from the published calibration report.
Two are engine fixes with measurable effects, one is an engine fix that is
provably inert in this harness, and two are the wiring gaps closed here.

| # | Change | Effect on this measurement |
|---|---|---|
| BUG-1 | median-match (`league_average_match`) ingested + simulated | **Large.** Pooled playoff Brier 0.1113 → 0.0997 (−10.5 %); the two Lakeview seasons 0.1017 → 0.0666 (−34.5 %); the four FFv3 seasons **bit-identical** (max \|Δ\| = 0.000000, asserted in-run) |
| BUG-2 | future pairings / `pre_draft` short-circuit | **None here.** All six captured seasons are `complete` and carry a full pairing graph, so no code path differs. Its measured cost is still the diagnostic below (§3) |
| BUG-3 | `playoff_seed_type` modelled — **plus the harness wiring closed here** | **Near-zero, and now measured rather than assumed.** Pooled title Brier 0.0733 → **0.0732**; the four fixed-bracket seasons 0.0817 → 0.0815; playoff Brier **bit-identical** (max \|Δ\| = 0.000000) |
| BUG-5 | IDP slot eligibility + `lineup_pricing()` — **plus the payload wiring closed here** | **None on any number.** The in-season harness scores `trailing_scores`, which never reads the board; the eligibility fix moved 0 of 72 preseason predictions. The wiring adds `meta.priced_slot_coverage`, a measurement |
| — | `meta.beta` de-aliased from `is_preseason` | None on any number (a label, not a prediction) |

**The BUG-3 wiring is the headline non-event of this pass.** The bracket rule
was modelled wrong for four of six league-seasons — 67 % of the sample — and
correcting it moved the pooled title Brier by **0.0001**. The cluster bootstrap
calls that delta *nominally* significant (−0.0001, 90 % CI [−0.0003, −0.0000])
purely because the effect is confined to four leagues and is the same sign in
all of them; a 0.0001 Brier improvement is not a product fact. The right read
is: **the title number was not wrong because of the bracket, and fixing the
bracket does not rescue it.** That is a null, and it is reported as one.

Two structural invariants held exactly, both asserted by the harness rather
than argued:

- **Playoff odds are seed-type-independent** — max \|Δ\| = 0.000000 across all
  288 predictions. The playoff field is settled before the bracket is played,
  so only `title_pct` and `bye_pct` can move. This is the reason the wiring gap
  never contaminated the playoff numbers anyone has quoted.
- **`playoff_seed_type: 1` leagues are bit-identical to the pre-wiring engine**
  — max \|Δ\| = 0.000000. Value `1` maps to `reseed`, which *is* the old
  unconditional behaviour, so Lakeview could not move. (See §9: this confirms
  the mapping is behaviour-preserving; it does **not** prove `1` means reseed.)

---

## 2. Method — what is different from the two prior reports

Same fixtures, same as-of semantics, same ground truth, same resampling unit as
[`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md) §2 and
[`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md) §3.1.
Nothing about the experimental design changed. What changed:

1. **`seed_type(fx)`** reads `settings.playoff_seed_type` off each captured
   league and is threaded into every `run_outlook` / `get_playoff_format` call
   in **both** harnesses. FFv3 2022/2023/2024/2025 are `0`; Lakeview 2024/2025
   are `1`.
2. A **BUG-3 A/B block** was added to the calibration harness, mirroring the
   existing BUG-1 A/B: each league-week is additionally scored with
   `playoff_seed_type=None` (exactly what the harness did before today), so the
   wiring's effect is isolated in-process rather than inferred across documents.
3. An **AST guard** (`test_backtest_scripts_pass_seed_type_into_every_bracket_they_build`)
   fails the suite if any future `run_outlook` / `get_playoff_format` call in
   either script omits the setting. The defect that produced this document
   cannot recur silently.
4. `meta.priced_slot_coverage` now ships on every payload. It is a measurement
   and changes no prediction — pinned by
   `test_coverage_measurement_changes_no_prediction`, which asserts the odds
   are identical to a run serialized without it.

**Sample, unchanged and still small:** 6 league-seasons, 2 distinct leagues,
72 independent team-seasons, **6 champion events**, 288 in-season team-week
predictions. Cluster bootstrap resamples **league-seasons** (the 12 team-seasons
inside a league are mechanically dependent). Six clusters is a very small
bootstrap; read every interval as *wide*, not precise.

---

## 3. In-season results (as-of weeks 3/6/9/12)

### Headline — pooled, n = 288 team-week predictions

| Predictor | Playoff Brier | Skill vs climatology | Title Brier | Skill vs climatology |
|---|---|---|---|---|
| **Outlook engine (all fixes + both wirings)** | **0.0997** | **+60.1 %** | **0.0732** | **+4.2 %** |
| B1 climatology | 0.2500 | — | 0.0764 | — |
| B2 standings-hard | 0.1458 | +31.7 % | 0.1389 | +47.3 % |
| B3 standings-shrunk | 0.1354 | +26.4 % | 0.0885 | +17.3 % |
| *(diagnostic)* no future schedule → random re-pairing | 0.1070 | — | 0.0731 | — |

Log-loss: playoff 0.4027, title 0.2592. The random-re-pairing fallback still
costs ~7 % of playoff Brier and nothing on title — a platform that does not
publish future pairings still gets usable playoff odds.

### Confidence — cluster bootstrap over 6 league-seasons, 90 % interval

| Quantity | Point | 90 % CI | Reading |
|---|---|---|---|
| Playoff skill vs climatology | **+60.1 %** | **[+47.6 %, +72.2 %]** | **excludes 0 — real skill** |
| Title skill vs climatology | +4.2 % | **[−13.1 %, +20.0 %]** | **includes 0 — still no demonstrated skill** |

### Per as-of week (n = 72 each)

| as-of week | Model playoff | B1 | B2 | B3 | Model title | B1 | B2 | B3 |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.2012 | 0.2500 | 0.2500 | 0.1875 | **0.0958** | **0.0764** | 0.1667 | 0.1024 |
| 6 | 0.1065 | 0.2500 | 0.1667 | 0.1458 | 0.0693 | 0.0764 | 0.1389 | 0.0885 |
| 9 | 0.0538 | 0.2500 | 0.1111 | 0.1181 | 0.0643 | 0.0764 | 0.1111 | 0.0747 |
| 12 | 0.0372 | 0.2500 | 0.0556 | 0.0903 | 0.0633 | 0.0764 | 0.1389 | 0.0885 |

Three facts survive the wave unchanged in shape and sharpen in degree:

1. **Playoff odds improve monotonically** — 0.2012 → 0.1065 → 0.0538 → 0.0372.
   The back half of the season is now *dramatically* better than before the
   wave (week 12: 0.0548 → 0.0372).
2. **Week 3 is the weakest in-season point, and it got worse**, not better
   (0.1972 → 0.2012). At week 3 the model is beaten by B3 standings-shrunk
   (0.1875). This is the BUG-1 mechanism the operator already knows: two
   decisions per week is genuinely less random than one, so the engine is more
   confident, which costs Brier wherever the strength estimate is still weak.
3. **Title odds at week 3 remain worse than a constant 1/12** (0.0958 vs
   0.0764) and never pull meaningfully ahead of it at any week.

### Split by league (pooled over weeks 3/6/9/12, n = 48 per league-season)

| league-season | median match | seed type | Playoff Brier | Title Brier | beats climatology (0.2500 / 0.0764)? |
|---|---|---|---|---|---|
| lakeview-2025 | yes | 1 | **0.0395** | 0.0530 | both |
| lakeview-2024 | yes | 1 | **0.0938** | 0.0601 | both |
| ffv3-2025 | no | 0 | 0.1713 | **0.0959** | playoff only |
| ffv3-2024 | no | 0 | 0.1433 | **0.0805** | playoff only |
| ffv3-2023 | no | 0 | 0.0928 | **0.0965** | playoff only |
| ffv3-2022 | no | 0 | 0.0574 | 0.0531 | both |
| **pooled** | — | — | **0.0997** | **0.0732** | playoff yes, title marginal |

**Every league-season beats climatology on playoff odds. Three of six lose to
climatology on title odds.** The title number is not merely unproven in
aggregate — it is actively worse than a constant on half the sample.

Grouped by format, pooled per week:

| as-of week | Lakeview (median match) playoff | FFv3 (H2H, IDP) playoff | Lakeview title | FFv3 title |
|---|---|---|---|---|
| 3 | 0.2109 | 0.1963 | 0.0819 | 0.1028 |
| 6 | 0.0474 | 0.1360 | 0.0469 | 0.0805 |
| 9 | 0.0080 | 0.0767 | 0.0471 | 0.0729 |
| 12 | 0.0001 | 0.0557 | 0.0503 | 0.0698 |

The median-match leagues are now the engine's *best* case from week 6 onward
(0.0474 → 0.0001) — the exact reversal BUG-1 predicted, since a median game
removes luck and the engine now models that. They remain its *worst* case at
week 3, for the same reason.

---

## 4. Preseason results (as-of week 0)

Rosters rewound to each season's real week-1 roster; values from the
period-correct DynastyProcess kickoff board; `auto` resolves to `roster_value`.

| predictor | playoff Brier | skill vs climatology | title Brier | skill vs climatology |
|---|---|---|---|---|
| **preseason `roster_value`, period-correct board** | **0.1968** | **+21.3 %** | **0.0746** | **+2.3 %** |
| B1 climatology | 0.2500 | — | 0.0764 | — |
| R-wk3 `trailing_scores` (the alternative) | 0.2012 | +19.5 % | 0.0958 | −25.5 % |
| R-today, 2026 board (hindsight control) | 0.2076 | +17.0 % | 0.0799 | −4.5 % |

Log-loss: playoff 0.5841, title 0.2571.

| Quantity | Point | 90 % CI | Reading |
|---|---|---|---|
| Preseason **playoff** skill vs climatology | **+21.3 %** | **[+2.9 %, +39.1 %]** | excludes 0 — real, but weak, **and weaker than published** |
| Preseason **title** skill vs climatology | +2.3 % | [−18.9 %, +24.5 %] | includes 0 — no skill |
| Preseason − week-3 playoff Brier delta | **−0.0043** | [−0.0603, +0.0401] | **indistinguishable — preseason nominally BETTER** |
| Preseason − week-3 title Brier delta | −0.0212 | [−0.0409, +0.0077] | indistinguishable |
| Period-correct − today's board, playoff | −0.0107 | [−0.0688, +0.0422] | indistinguishable (hindsight fear still not detectable) |

### Split by league

| league-season | preseason playoff | wk-3 playoff | climatology | preseason title | Spearman(mu, wins) | field overlap |
|---|---|---|---|---|---|---|
| lakeview-2025 | 0.1730 | 0.1103 | 0.2500 | 0.1091 | +0.636 | 4/6 |
| lakeview-2024 | **0.2923** | 0.3115 | 0.2500 | 0.0691 | +0.490 | 3/6 |
| ffv3-2025 | 0.1528 | 0.3088 | 0.2500 | 0.0843 | +0.637 | 4/6 |
| ffv3-2024 | **0.2812** | 0.2860 | 0.2500 | 0.0662 | **+0.022** | 4/6 |
| ffv3-2023 | 0.1372 | 0.0889 | 0.2500 | 0.0889 | +0.544 | 5/6 |
| ffv3-2022 | 0.1446 | 0.1016 | 0.2500 | 0.0302 | +0.761 | 5/6 |
| **pooled** | **0.1968** | 0.2012 | 0.2500 | 0.0746 | — | **25/36 (69 %)** |

**Preseason playoff Brier still beats climatology in only 4 of 6
league-seasons**, and both failures are large. `ffv3-2024`'s preseason board
still carries essentially zero ordering information (+0.022) — the single worst
result anywhere in this program, and the wave did not touch it.

By format: median-match leagues **0.2326** (barely beats climatology 0.2500),
H2H leagues **0.1789** (comfortably beats it). The BUG-1 fix moved the median
half from 0.2298 to 0.2326 — **worse**, as the BUG-1 agent flagged. It is
confirmed here on the combined engine.

---

## 5. Calibration tables — did the over-confidence survive?

**Short answer: yes for the preseason source, which is where the finding
originated and where the surface would first light. The in-season engine's
populated buckets remain well behaved.**

### In-season playoff odds, pooled (n = 288)

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 99 | 0.012 | 0.051 | +0.039 |
| 0.1–0.2 | 17 | 0.156 | 0.235 | +0.079 |
| 0.2–0.3 | 13 | 0.254 | 0.385 | +0.131 |
| 0.3–0.4 | 6 | 0.345 | 0.500 | +0.155 |
| 0.4–0.5 | 10 | 0.449 | 0.200 | −0.249 |
| 0.5–0.6 | 6 | 0.559 | 0.667 | +0.107 |
| 0.6–0.7 | 11 | 0.658 | 0.545 | −0.112 |
| 0.7–0.8 | 13 | 0.756 | 0.769 | +0.013 |
| 0.8–0.9 | 13 | 0.858 | 0.846 | −0.012 |
| **0.9–1.0** | **100** | **0.988** | **0.940** | **−0.048** |

The two large buckets (n = 99, n = 100) hold 69 % of all predictions and both
sit inside ±0.05. A 1 % in-season call realizes 5 %; a 99 % in-season call
realizes 94 %. Every bucket with n ≤ 17 swings by 0.08–0.25, which is what
8–17 observations do — the −0.249 at 0.4–0.5 is **2 berths out of 10**.

### In-season title odds, pooled (n = 288)

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 205 | 0.016 | 0.039 | +0.023 |
| 0.1–0.2 | 35 | 0.143 | 0.114 | −0.029 |
| 0.2–0.3 | 21 | 0.235 | 0.190 | −0.045 |
| 0.3–0.4 | 19 | 0.352 | 0.368 | +0.016 |
| 0.4–0.5 | 5 | 0.419 | 0.200 | −0.219 |
| 0.5–0.6 | 2 | 0.565 | 0.000 | −0.565 |
| 0.7–0.8 | 1 | 0.788 | 0.000 | −0.788 |

Above 0.4 there are **eight observations in total, containing exactly one
champion** (the lone hit is in the 0.4–0.5 bucket). The −0.565 and −0.788 gaps
are two teams and one team. They support no inference and are printed only so
the table is not silently truncated.

### Preseason title odds (n = 72)

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 50 | 0.024 | 0.040 | +0.016 |
| 0.1–0.2 | 13 | 0.141 | 0.231 | +0.090 |
| 0.2–0.3 | 5 | 0.242 | 0.000 | −0.242 |
| 0.3–0.4 | 1 | 0.322 | 0.000 | −0.322 |
| 0.4–0.5 | 2 | 0.466 | 0.500 | +0.034 |
| 0.5–0.6 | 1 | 0.501 | 0.000 | −0.501 |
| 0.6–1.0 | 0 | — | — | — |

Sixty-nine per cent of preseason title predictions land in the bottom bucket and
are roughly right there. Above 0.3 there are **four observations and one
champion**. This table is included for completeness; it is not evidence.

### Preseason playoff odds (n = 72) — the finding that governs the decision

| bucket | n | mean predicted | realized | gap | published pre-fix |
|---|---|---|---|---|---|
| 0.0–0.1 | 12 | 0.034 | 0.167 | **+0.132** | +0.142 (n = 11) |
| 0.1–0.2 | 5 | 0.120 | 0.000 | −0.120 | −0.116 |
| 0.2–0.3 | 3 | 0.238 | 0.333 | +0.095 | +0.095 |
| 0.3–0.4 | 8 | 0.358 | 0.500 | +0.142 | +0.204 |
| 0.4–0.5 | 7 | 0.452 | 0.429 | −0.023 | −0.067 |
| 0.5–0.6 | 8 | 0.558 | 0.625 | +0.067 | +0.077 |
| 0.6–0.7 | 6 | 0.646 | 0.667 | +0.021 | −0.073 |
| 0.7–0.8 | 5 | 0.763 | 0.600 | **−0.163** | −0.028 |
| 0.8–0.9 | 9 | 0.842 | 0.778 | −0.064 | −0.044 |
| **0.9–1.0** | **9** | **0.947** | **0.778** | **−0.169** | **−0.199 (n = 8)** |

**The over-confidence survived.** The headline number moves from *"a team told
95 % makes the playoffs 75 % of the time"* to *"a team told **95 %** makes the
playoffs **78 %** of the time"* — a 17-point miss instead of a 20-point one, on
nine observations instead of eight. At the bottom, a team told **3 %** makes them
**17 %** of the time. The 0.7–0.8 bucket got materially worse (−0.028 → −0.163).
**The sign pattern at both extremes simultaneously is intact**, which is the
part that was ever evidence: a preseason model that knows only roster value has
no way to represent "we do not yet know how good this team is".

The in-sample shrink sweep is likewise unchanged in shape — the best λ (0.75)
buys 0.1968 → 0.1916, about **2.6 % of Brier**. Tuning still does not rescue
the number. (In-sample on the same 6 seasons; not a fitted recommendation.)

---

## 6. Before/after against the published pre-fix numbers

### In-season, pooled (n = 288)

| Quantity | Published pre-wave (report §3) | Published post-BUG-1 (report §7) | **Combined post-fix (this run)** | Net vs pre-wave |
|---|---|---|---|---|
| Playoff Brier | 0.1113 | 0.0997 | **0.0997** | **−10.4 %** |
| Playoff skill vs climatology | +55.5 % [+44.5, +65.9] | +60.1 % [+47.6, +72.2] | **+60.1 % [+47.6, +72.2]** | **+4.6 pp** |
| Title Brier | 0.0725 | 0.0733 | **0.0732** | **+1.0 % (worse)** |
| Title skill vs climatology | +5.1 % [−13.2, +22.3] | — | **+4.2 % [−13.1, +20.0]** | still spans 0 |
| Playoff log-loss | 0.4131 | — | **0.4027** | better |
| Title log-loss | 0.2578 | — | **0.2592** | slightly worse |

### In-season, per as-of week

| week | Playoff pre-wave | **Playoff post-fix** | Title pre-wave | **Title post-fix** |
|---|---|---|---|---|
| 3 | 0.1972 | **0.2012** *(worse)* | 0.0953 | **0.0958** *(worse)* |
| 6 | 0.1204 | **0.1065** | 0.0694 | **0.0693** |
| 9 | 0.0729 | **0.0538** | 0.0628 | **0.0643** *(worse)* |
| 12 | 0.0548 | **0.0372** | 0.0626 | **0.0633** *(worse)* |

**The wave bought weeks 6–12 and cost week 3.** On title odds it bought nothing
and cost a little at three of four weeks — all inside the noise of a 6-cluster
sample, and all in the same direction, which is consistent with the BUG-1
mechanism rather than with a defect.

### Isolating the two wirings closed here

| Engine arm | seed-type-blind (as published) | seed-type-wired (this run) | Δ from the BUG-3 wiring |
|---|---|---|---|
| Median-blind (pre-BUG-1), title | 0.0725 | 0.0724 | **−0.0001** |
| Median-aware (post-BUG-1), title | 0.0733 | 0.0732 | **−0.0001** |
| Either arm, playoff | — | — | **0.0000 (bit-identical)** |
| Fixed-bracket leagues only (FFv3, n = 192), title | 0.0817 | 0.0815 | **−0.0002** |

The IDP coverage wiring has **no** row here by construction: the in-season
harness scores `trailing_scores`, which never reads the value board, and the
BUG-5 eligibility fix moved 0 of 72 preseason predictions. Its contribution is
a payload field, not a number.

### Preseason (n = 72)

| Quantity | Published (revalidation §3.3) | **Combined post-fix** | Reading |
|---|---|---|---|
| Playoff Brier | 0.1959 | **0.1968** | marginally worse |
| Playoff skill | +21.6 % **[+4.1, +38.3]** | **+21.3 % [+2.9, +39.1]** | **lower bound got worse** |
| Title Brier | 0.0740 | **0.0746** | worse |
| Title skill | +3.1 % [−17.7, +24.9] | **+2.3 % [−18.9, +24.5]** | still spans 0 |
| Preseason − wk3 playoff Δ | −0.0013 [−0.0573, +0.0470] | **−0.0043 [−0.0603, +0.0401]** | still indistinguishable |
| wk-3 reference playoff Brier | 0.1972 | **0.2012** | worse |
| Median-match leagues | 0.2298 | **0.2326** | **worse — the BUG-1 cost, confirmed** |
| H2H leagues | 0.1789 | **0.1789** | bit-identical |
| League-seasons beating climatology | 4 / 6 | **4 / 6** | unchanged |
| Playoff-field overlap | 25 / 36 | **25 / 36** | unchanged |
| Best in-sample shrink (λ = 0.75) | 0.1915 | **0.1916** | unchanged |

Per-league movement is entirely inside the two median-match seasons, as
expected: lakeview-2025 0.1806 → **0.1730** (better), lakeview-2024 0.2789 →
**0.2923** (worse), all four FFv3 seasons unchanged to four decimals.

### Also re-confirmed in the same run (no change)

- **Bye-week μ multiplier: still NO-SHIP.** Playoff Brier delta **+0.0031**,
  90 % CI [−0.0054, +0.0125] — a null, nominally worse. The mechanism check is
  the real evidence: the OLS slope of actual score deviation against fraction of
  starting slots on bye is **−0.218** (90 % CI [−0.310, −0.123]) against the
  naive multiplier's implied −1.000. Managers absorb byes with bench swaps.
- **Empirical knob evidence unchanged:** pooled league mean 130.6 pts,
  within-team σ 22.1, noise-corrected between-team SD 14.1 — against shipped
  defaults of 110 / 25 / 12. The mean-points default remains ~20 points low
  for both of these leagues; it cancels in the cross-team z-score, so it is a
  cosmetic rather than a predictive defect, but it is still wrong.

---

## 7. Decision 1 — bands vs percentages

**Recommendation: the "bands only, never a bold percentage" verdict STANDS, and
the fixed engine strengthens rather than weakens the case for it.**

The prior verdict rested on two numbers. Both were re-measured:

| Reason the prior verdict gave | Pre-fix | **Post-fix** | Direction |
|---|---|---|---|
| Preseason over-confidence at the extremes | 95 % → 75 % realized (n = 8) | **95 % → 78 % realized (n = 9)**; 3 % → 17 % at the bottom; 0.7–0.8 bucket −0.163 | **survived** |
| Preseason skill lower CI bound | **+4.1 %** | **+2.9 %** | **got worse** |

Neither pillar moved in the direction that would license a percentage. The
lower bound in particular is the number that matters for a bold figure: at the
pessimistic end of a 6-cluster bootstrap the preseason model is **+2.9 %**
better than a constant "6 of 12 make it" — a rounding error away from showing
the user a number with no information in it.

Three further facts from this run point the same way:

1. **The wave made the earliest weeks worse, not better.** Week 3 playoff Brier
   went 0.1972 → 0.2012 and the median-league preseason went 0.2298 → 0.2326.
   The surface's *first impression* is the part the fixes did not help.
2. **Two of six league-seasons still lose to climatology outright** in the
   preseason (0.2923, 0.2812), one of them with an ordering correlation of
   +0.022. A user in that league would be shown confident, ordered, wrong
   percentages all season.
3. **A single scalar shrink does not fix it** — the best in-sample λ buys 2.6 %
   of Brier, fit on the same six seasons it is scored on.

**Where a percentage *is* defensible, stated precisely so the operator has the
option:** the **in-season** engine's populated calibration buckets are inside
±0.05 (0.0–0.1: +0.039 at n = 99; 0.9–1.0: −0.048 at n = 100), its skill CI is
[+47.6 %, +72.2 %], and its Brier at weeks 9/12 is 0.054/0.037. On that
evidence a **playoff** percentage **rounded to the nearest 5 %, from week 6
onward, playoff odds only** would not be dishonest.

But that option carries a caveat this document cannot remove: **the in-season
calibration table above is pooled across weeks 3/6/9/12 and is not stratified
by week**, so "the extremes are well calibrated at week 9" is an inference, not
a measurement. Producing per-week calibration tables needs a per-team record
dump the calibration harness does not currently write. Until that exists, the
defensible default is:

> **Bands everywhere. If the operator wants a number, it may appear only from
> week 6, only for playoff odds, and only rounded to 5 % — and that is an
> operator's risk call on pooled evidence, not a validated result.**

**Title / championship odds must not be rendered as a percentage at any week.**
That is not a calibration judgement, it is an absence of skill: +4.2 %, CI
[−13.1 %, +20.0 %], worse than a constant 1/12 at week 3, worse than
climatology in three of six league-seasons, and eight observations above a 0.4
predicted probability containing a single champion between them.

---

## 8. Decision 2 — the gate: week 0, 3, or 6?

**Recommendation: gate NUMBERS at week 6. Allow BANDS from week 0. Never gate
at week 3.**

The three candidates, on this run's evidence:

| Gate | Playoff Brier at the moment it fires | Skill vs climatology | What it buys | What it costs |
|---|---|---|---|---|
| **Week 0** | 0.1968 | +21.3 %, CI [+2.9, +39.1] | the whole preseason, when league interest peaks | over-confident extremes; loses to climatology in 2 of 6 seasons |
| **Week 3** | 0.2012 | +19.5 % | **nothing measurable** | the entire preseason, for a number that is *nominally worse* |
| **Week 6** | 0.1065 | +57.4 % | the first point the engine is unambiguously good | five weeks of surface |

**Week 3 is dominated and should be dropped from consideration.** The preseason
model is statistically indistinguishable from the week-3 model (paired Brier
delta −0.0043, CI [−0.0603, +0.0401]) and *nominally better* — the gap widened
in preseason's favour after the fixes (it was −0.0013). A week-3 gate therefore
withholds the surface for three weeks and then lights it at the single worst
in-season point in the season, the only week where the model loses to B3
standings-shrunk (0.2012 vs 0.1875) **and** where title odds are worse than a
constant (0.0958 vs 0.0764). The calibration report's original justification for
week 3 — "that's where `trailing_scores`, the validated source, takes over" —
was superseded by the revalidation and is superseded again here.

**The BUG-1 finding argues FOR week 6, not against week 0.** The operator's
complication is real: removing luck made the preseason median-league number
slightly worse (0.2298 → 0.2326), because a more honest model is more confident,
and confidence costs Brier when the prior is weak. But note what that diagnoses.
It is not a defect in the fix — the same fix is worth −34.5 % of playoff Brier
on those leagues in-season. It says **the roster-value prior is the weak link,
and it stays weak until real games replace it.** The point where the prior stops
being the binding constraint is measurable, and it is week 6:

| | week 0 | week 3 | **week 6** | week 9 | week 12 |
|---|---|---|---|---|---|
| Playoff Brier | 0.1968 | 0.2012 | **0.1065** | 0.0538 | 0.0372 |
| Skill vs climatology | +21.3 % | +19.5 % | **+57.4 %** | +78.5 % | +85.1 % |

The step from week 3 to week 6 nearly halves the Brier. Nothing else in the
season does that. Week 6 is also already the threshold encoded in
`serialize.py::_BETA_UNTIL_COMPLETED_WEEKS`, chosen on the same evidence — so
this recommendation costs no new concept: **`meta.beta` clearing is the gate.**

**Concretely:**

- `completed_weeks >= 6` → playoff odds may be shown as a number (rounded to
  5 %, per §7); `beta` is false; title odds still withheld.
- `completed_weeks 0–5` → **bands only** ("likely / toss-up / unlikely"),
  playoff only, `beta` true, "Projected · beta" label retained. Justified
  because preseason skill excludes zero (+21.3 %, CI [+2.9, +39.1]) and is no
  worse than week 3 — showing *something* ordered is better than showing
  nothing for six weeks, provided its granularity matches its evidence.
- `status == "pre_draft"` → nothing, unchanged (no schedule, and the random
  re-pairing fallback costs ~7 % of playoff Brier).
- **Never `completed_weeks >= 3`.** It is the one option with no measured
  benefit over either neighbour.

**One honest caveat on the week-0 half.** Lakeview 2024 (preseason Brier 0.2923)
and FFv3 2024 (0.2812) both lose to climatology, and a band is not immune to
being wrong — it is only immune to being *precisely* wrong. If the operator
prefers a single, simple rule over a two-tier one, **`completed_weeks >= 6` for
everything** is fully supported by this evidence and is the conservative choice.
The two-tier version trades a little accuracy risk for five weeks of surface.

---

## 9. What remains unvalidated

Stated plainly, because several of these are load-bearing for any decision made
on this document.

1. **Title / championship odds — still unvalidated, and now measured twice.**
   Pooled skill +4.2 %, 90 % CI [−13.1 %, +20.0 %]. Six champion events across
   six league-seasons. Three of six league-seasons score *worse* than
   climatology. Eight predictions above 0.4, zero champions among them. The
   BUG-3 bracket fix — the one mechanism anyone expected to matter here — moved
   the number by 0.0001. Eight predictions above 0.4 contain one champion.
   **Nothing in this wave brought title odds closer to shippable, and no
   further engine fix is likely to; the constraint is six events, and only more
   leagues can lift it.**
2. **IDP pricing — instrumented, not solved.** `meta.priced_slot_coverage` now
   tells a client that FFv3 prices 7 of 15 starting slots (`fraction 0.4667`),
   which makes the honest caption possible. It does **not** price the other
   eight. No license-clean dynasty IDP value board exists (DynastyProcess,
   nflverse, FantasyCalc, KTC, Sleeper `search_rank` all checked and rejected),
   and both candidate workarounds lost their backtest. **In an IDP league every
   preseason number in this document is an offensive-core estimate.** The
   coverage field is also completely unexercised by any client — it has never
   been rendered.
3. **`playoff_seed_type: 1` semantics — doc-corroborated, not fixture-proven.**
   Value `0` (fixed bracket) is proven: three independent divergent instances
   across the four completed FFv3 seasons, all matching the fixed-bracket
   prediction, none matching reseed. Value `1` rests on Sleeper's support
   documentation plus the absence of contradicting evidence — neither Lakeview
   season contains a divergent upset pattern. This run adds one fact and it is
   *not* a proof: the `1` leagues are bit-identical before and after the wiring,
   which confirms the mapping preserves today's behaviour and confirms nothing
   about whether today's behaviour is right. **If `1` does not mean reseed, both
   the old engine and the new one are wrong in exactly the same way, and this
   sample cannot tell.**
4. **Two leagues, six league-seasons, one shape each.** Both leagues are
   12-team / 6-slot / 2-bye. Every median-match observation is Lakeview; every
   IDP observation is FFv3. 4-, 8- and 10-team formats, divisional leagues,
   two-week championship rounds and consolation brackets are entirely untested
   against reality. The BUG-1 improvement rests on **two** median-match
   league-seasons; its paired bootstrap CI is [−0.0234, +0.0000] — the
   direction is right, the significance is not established.
5. **Per-week calibration is not measured.** §5's tables pool weeks 3/6/9/12.
   Any statement of the form "the extremes are well calibrated at week N" is an
   inference. This is the specific gap that keeps §7's percentage option an
   operator risk call rather than a result. Closing it needs the calibration
   harness to dump per-team records the way the preseason harness already does.
6. **Rosters are not rewound in the in-season harness.** `player_ids` stay at
   the 2026 Sleeper snapshot, which is harmless for `trailing_scores` (it never
   reads rosters) and is why the in-season numbers score that source only. The
   preseason harness does rewind them.
7. **`points_for` is not exactly reconstructible** from weekly scores on one
   Sleeper roster (BUG-4, ~1.1 % on lakeview-2024 roster 10) — external, still
   unactionable, still the reason the rewind test allows 2 %.
8. **The calibration knobs are still un-fit.** `outlook_mean_points = 110`
   against a pooled empirical 130.6; `outlook_points_per_value_sd = 12` against
   a noise-corrected between-team SD of 14.1; `outlook_sigma_default = 25`
   against a within-team σ of 22.1. They cancel in the z-score, so nothing above
   changes if they are corrected — but no one has fit them.

---

## 10. Corrections issued to prior documents

Following the house pattern: the original text is left intact and annotated
inline with a dated note.

| Document | Correction |
|---|---|
| [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md) §7 BUG-3 | The "Not done — the script still calls `get_playoff_format` without passing `playoff_seed_type`" note is struck and replaced with the measured result (title 0.0733 → 0.0732; playoff bit-identical) |
| [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md) §7 BUG-5 | "wiring it into `meta` is the open follow-up" is struck — it is wired, with the shipped field shape recorded |
| [`idp-pricing-2026-08-09.md`](idp-pricing-2026-08-09.md) §6 | The "Follow-up, explicitly not done here" block is annotated DONE with the shipped field shape and the neutrality test that pins it |
| [`status.md`](status.md) §BUG-3 fix | "Not done: `scripts/outlook_calibration_backtest.py` was not updated…" struck, pointing here |
| [`status.md`](status.md) §Calibration verdict | The BUG-5 "open follow-up before lighting the flag for any IDP league" struck — the coverage field ships |

**Numbers superseded by this run** (the prior documents' figures remain correct
*as of their own dates and engines*; this document is the current picture):

| Claim | Where published | Superseded value |
|---|---|---|
| post-BUG-1 pooled title Brier 0.0733 | calibration report §7 | **0.0732** (seed-type-aware) |
| preseason playoff Brier 0.1959, skill +21.6 % CI [+4.1, +38.3] | revalidation §3.3 | **0.1968, +21.3 % CI [+2.9, +39.1]** |
| preseason title Brier 0.0740, skill +3.1 % | revalidation §3.3 | **0.0746, +2.3 %** |
| preseason 0.9–1.0 bucket: 0.949 → 0.750 (n = 8) | revalidation §3.4 | **0.947 → 0.778 (n = 9)** |
| preseason per-league: lakeview-2025 0.1806, lakeview-2024 0.2789 | revalidation §3.5 | **0.1730, 0.2923** |
| week-3 reference Brier 0.1972 | revalidation §3.3 / report §3 | **0.2012** |
| IDP backtest V0 Lakeview baseline 0.2298 | idp-pricing §5.2 | **0.2326** (BUG-1 fixed; FFv3's 0.1789 is unchanged) |

The IDP report's **relative** verdicts are unaffected: V1 is still bit-identical
to V0 and the two pricing workarounds still lose. Its absolute V0 figures were
measured on the pre-BUG-1 engine and shift for the Lakeview half only.

---

## 11. Reproducing this report

```bash
# In-season — as-of weeks 3/6/9/12, BUG-1 and BUG-3 A/Bs, calibration tables,
# bye-multiplier variant, mechanism check. Offline, ~7 min.
python3 scripts/outlook_calibration_backtest.py --sims 10000

# Preseason — as-of week 0, period-correct DP boards, real week-1 rosters.
# Offline, ~4 min. Rewrites backend/tests/fixtures/outlook-hypotheses/
# preseason-backtest-records.json, which four permanent guards re-score.
python3 scripts/outlook_preseason_backtest.py --sims 10000

# Permanent guards (no sims)
python3 -m pytest backend/tests/test_outlook_calibration.py \
                  backend/tests/test_outlook_playoff_seed_type.py \
                  backend/tests/test_outlook_preseason_source.py \
                  backend/tests/test_outlook_idp_pricing.py \
                  backend/tests/test_outlook_odds.py -q
```

Neither script touches the network or the database. Both are deterministic:
every simulator seed is `stable_hash(league_id) ^ outlook_seed`, so re-running
reproduces every figure above to four decimals.
