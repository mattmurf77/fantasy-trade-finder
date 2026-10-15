# Trade model vs KTC: eval plan (joint)

> **Purpose:** the joint eval plan for the operator's 2026-10-15 trade-modeling ask. It compares the three Calibration models against KTC's trade-driven values (or a lawful stand-in) and tests whether league-specific valuation makes sense. The research behind it is in [research-memo.md](research-memo.md).
>
> **Owners:** `models-lead` owns the strategy half: §1–§3 (metrics, bars, decision rules, hypothesis verdicts). `trades-pm` owns the product half (§4), the data notes, the run tiers (§5), and the merged decisions and handoffs (§6–§7). **models-lead sections pasted verbatim from draft 2.1 (2026-10-15); models-lead reviews this branch read-only and records sign-off in its own report.**
>
> **Status:** planning, 2026-10-15. Nothing has been run. Building anything, D-W5 included, needs its own scope block ([`docs/templates/feature-scope.md`](../../templates/feature-scope.md)).
>
> **Public repo:** no KTC values, rankings or page content appear here. See the research memo's sourcing rules.

## Contents

- [Reading this file](#reading-this-file)
- [1. 5.1 Comparison plan, strategy half \[models-lead\]](#1-51-comparison-plan-strategy-half-models-lead)
- [2. O1: draft restatement of graduation criterion 2 \[models-lead\]](#2-o1-draft-restatement-of-graduation-criterion-2-models-lead-draft-for-operator-ratification)
- [3. 5.2 League-specific valuation as testable hypotheses \[models-lead\]](#3-52-league-specific-valuation-as-testable-hypotheses-models-lead)
- [4. Product half \[trades-pm\]](#4-product-half-trades-pm)
- [5. Run tiers and blockers \[trades-pm\]](#5-run-tiers-and-blockers-trades-pm)
- [6. Decisions needed](#6-decisions-needed)
- [7. Handoffs](#7-handoffs)

## Reading this file

- **Ownership.** The three H2 sections marked `[models-lead]` are models-lead's draft 2.1, §1–§3, pasted verbatim. trades-pm hasn't edited a character of them.
- **Data notes.** Where a models-lead table has a "data needed", "data", "status" or "supported?" column, trades-pm's corpus and terms facts sit **directly under that table** as a separate `[trades-pm] data notes` table. Each block is fenced by `<!-- [trades-pm] data notes: start -->` and `<!-- [trades-pm] data notes: end -->`. Deleting each fenced block, together with the one blank line before it, gives back draft 2.1's §1–§3 byte for byte. The notes state facts only; models-lead keeps the verdicts.
- **Cross-references.** models-lead's text cites the research by its working section numbers. In this folder they map as follows:

| models-lead cites | Here |
|---|---|
| trades-pm §4.1 (what K2 is) | [research-memo §2](research-memo.md#2-what-ktc-launched) |
| trades-pm §4.2, §4.2a–c (KTC terms) | [research-memo §4.1](research-memo.md#41-ktc-terms-and-faq) |
| trades-pm §4.2, "adjacent finding" (Sleeper's API terms) | [research-memo §4.2](research-memo.md#42-sleeper-terms-2026-10-06-and-the-api-docs) |
| trades-pm §4.3 (corpus) | research-memo §3, §4.4 and §7.4 |
| trades-pm §4.4 and §C.2 (trade set, power) | [§4.1 below](#41-the-fixed-trade-set); research-memo §7.1–§7.2 |
| trades-pm §C.1 (dated values) | research-memo §5.2–§5.3 |
| trades-pm's S1, S2 | [§4.1 below](#41-the-fixed-trade-set) |
| "wave-1 D2" (the insult definition) | models-lead's wave-1 working file, outside this repo |
| "task 2" | the parallel DB-storage task. Storage figures are in [research-memo §6](research-memo.md#6-storage-cost-of-a-broader-corpus) |

---

## 1. 5.1 Comparison plan, strategy half [models-lead]

### 1.1 Comparators, by data-rights tier

| Tier | Key | Evaluator | Status |
|---|---|---|---|
| **A: no new KTC data** | E1 | Filtered live engine (`owner_v2_bilateral` + `deck_quality`, D-207) | Runnable (needs D-W4) |
| A | E2 | Value core v4 (D-206) | Runnable |
| A | E3a / E3b | Fit A / fit B | Runnable |
| A | C0 | FTF consensus, as stamped on each card | Runnable. The values derive from K1, so their status **follows the operator's D-W1 call on the scrape** |
| A | C1 | DP only: dated DP boards, or `ktc_blend_weight = 0` | Runnable. DP is FTF's own sanctioned spine |
| **B: needs KTC permission** | K1 | KTC crowd values | **Blocked: D-W1** |
| B | K2 | KTC Tradesourced values and calculator | **Blocked: D-W1** |
| **C: substitute** | F2 | A trade-driven source whose terms allow evaluation (e.g. FantasyCalc, if its terms check out) | **Blocked: D-W6** (the terms check, and the operator accepting a substitute for "KTC") |

<!-- [trades-pm] data notes: start -->

**[trades-pm] data notes** on §1.1. These are facts on data and terms; models-lead keeps the verdicts.

| Key | Data note |
|---|---|
| E1, E2, E3a, E3b | Each card stores the served trade with every asset's C0 value (`grading_cards.trade_json`) and its arms (`arms_json`; a shared card carries several) (`docs/data-dictionary.md:1957-1958`). Rescoring a card under an engine means rebuilding its league from prod, as `backend/eval/fit_scorecard_test.py` does, so it needs D-W4 |
| C0 | The values stamped on cards come from `player_value_history` (`docs/data-dictionary.md:1958`). Those rows carry the KTC blend only from 2026-07-17 (`:1263`). Every Calibration card postdates that, so every card value embeds K1. Rescoring C0 needs no new KTC data. The scrape's terms status is in research-memo §4.1 (TP-1) |
| C1 | `ktc_blend_weight = 0` is byte-identical to DP-only and skips the KTC fetch (`docs/runbook.md:967`). The 24 committed DP boards stop at 2025-12-11 (`backend/tests/fixtures/dp-values-history/`). Boards for October 2026 grading dates come from DP's git history (`backend/dp_values_history.py`, G-025). DP data is CC-BY, with an attribution obligation (`backend/dp_values_history.py:20`) |
| K1 | KTC has no API, export or dated history. FTF keeps only an in-memory 24-hour copy (`backend/data_loader.py:188`). The only dated copy is the 2026-07-17 fixture set committed to this public repo (TP-1) |
| K2 | History runs from 2026-05-01, with earlier dates backfilled from crowd values. It exists only as on-site charts: no export, and no Wayback captures of the rankings. Values assume 12 teams and 0.5 PPR. KTC's published terms prohibit capturing it without written permission (research-memo §4.1b–c) |
| F2 | FantasyCalc is trade-derived and per-format (`docs/reviews/trade-engine-external-research.md:13-15`). Its terms are **unverified**: its site is JS-rendered and returned no content (research-memo §3.3) |

<!-- [trades-pm] data notes: end -->

### 1.2 Questions and metrics

| # | Question | Metric | Tier |
|---|---|---|---|
| **Q-K (new, primary while B is blocked)** | Does the KTC blend in our consensus make our verdicts better? This is the model evidence for keeping, killing or licensing the scrape | (i) **Paired AUC, C0 vs C1** on the same unique graded cards. (ii) **Executed-trade fair rate:** the share of real trades inside each board's fairness band, using the **same relative band** for both and only trades dated after `player_value_history` began. This is positive-only and free of anchoring | A |
| **Q-B** | Do KTC's (or a substitute's) trade-driven values predict human verdicts better than FTF's board? | Paired AUC on unique graded cards. **Primary contrast, fixed now: K2 (or F2) vs C1.** Draft 1 used C0; the anchoring bias means **C1 is the clean contrast now.** Secondary: K2 vs C0; K2 vs K1; K2 vs E1, E2 and E3a. Plus the executed-trade fair rate | B or C |
| **Q-C** | Do the round-3 arms differ on would-send? (the go-live read) | Would-send rate per arm on its own served cards (`report?since=2026-10-15`) | A |
| Q-A | Where do the boards diverge? (descriptive only) | Spearman ρ by format × position (× tier band only where cells have ≥ 60 players), C0 vs C1 now, and K2 or F2 once unblocked. Picks reported separately | A now; B or C later |
| Q-D | Do engines serve trades the trade-driven market calls unfair, and do graders reject them? | For each arm: the share of cards outside the comparator's band, and would-send on fair vs unfair cards. **The band is fixed now: the comparator's own default** (KTC about 5% of combined adjusted value) | B or C |

### 1.3 Pre-registered biases and how each changes what a result means

| # | Bias | Effect | How the plan handles it |
|---|---|---|---|
| 1 | **Anchoring.** Graders see C0 values and totals on every card (`GradingCard.tsx:53,68`) | Q-B and Q-K grades tilt toward C0 | **Read asymmetrically.** A non-C0 board that **beats** C0 is conservative, so the result stands. C0 **beating or tying** another board is **not** evidence against it. The executed-trade fair rate, which has no anchoring, breaks the tie. **For future rounds that judge value boards:** grade with values hidden (D-W5) |
| 2 | **Range restriction.** Every arm already filters to C0-fair trades (the value-core band; fit's hard rules) | All AUCs are compressed; other boards can only discriminate inside C0's band | Report AUC *within the band*. Treat the executed-trade fair rate as the unrestricted evidence |
| 3 | **Shared cards.** One card can come from several arms | It inflates n | Count unique cards once in Q-B and Q-K. In Q-C, attribute by `arms_json`, and run a sensitivity check without shared cards |
| 4 | **Engine versions differ by round** (round 2 unfiltered v2/v3; round 3 filtered v4) | Pooling mixes engines | Engine scorers are compared **within round only**. Board contrasts (Q-K, Q-B) may pool, stratified by round |
| 5 | **Two grade scales** (legacy 1–5 and Yes/No) | Labels aren't identical | Legacy counts as Yes at ≥ 4, and **legacy 3 counts as No** (`share_ge_4`, D-208; the same label as Q-C and §2). Two sensitivity checks: Yes/No-only cards, and legacy 3s dropped (the `fit_scorecard_test.py:37` convention behind D-200's numbers). A conclusion stands only if all three agree in direction. `analytics-lead` confirms the definition |

On top of these: grader-stratified AUC, a **leave-one-grader-out** direction check, skipped cards excluded, and no tuning on the evaluation set.

### 1.4 Minimum n and detectable effect

**Which graded cards each question uses**
- **Board contrasts (Q-K, Q-B).**
  - Primary: rounds 1–3, stratified by grader and by round.
  - Round 1 (operator only, 120 cards, value-core-1) is a valid board test. Every card is stamped with post-2026-07-17 C0 values, and a board contrast doesn't depend on engine version.
  - Sensitivity: rounds 2–3 only (trades-pm's S1). A conclusion needs both sets to agree in direction.
- **Engine scorers and Q-C:** within round only. Round 3 is primary, round 2 secondary, round 1 excluded.
- **Without round 1,** n is about 258 answers today, and the detectable gap is about 0.09–0.10 until round 3 adds cards.

**Q-B and Q-K, paired AUC difference.** Pooled about 160 Yes / 190 No. AUC about 0.65 (trades-pm §C.2, Hanley–McNeil).

| Score correlation r | Detectable ΔAUC (80% power, before grader clustering) |
|---|---|
| 0.7 | about 0.065 |
| 0.5 | about 0.085 |

- **The 0.07 threshold sits at the edge of detectability.** At today's n a **null result is uninformative**, so every read reports the CI, not just pass/fail.
- Round 3 adds cards. A board contrast becomes decisive at roughly 250 Yes and 250 No.

**Q-C, would-send difference between arms (unpaired, p ≈ 0.5, 80% power):**

| Cards per arm | Detectable difference |
|---|---|
| 100 | ±20 pp |
| 175 | **±15 pp** |
| 400 | ±10 pp |

- The ±14 pp figure in my wave-1 file was the 95% significance line, which is only 50% power.
- **Cap: 3 arms in round 3 (E1, E2, E3a; drop fit B).** Target 175 graded cards per arm.
- **Horizon:** 175 per arm or **2026-11-05**, whichever comes first. A read at the horizon without n is **inconclusive**, and the go-live call doesn't change. No interim reads.

**Executed-trade fair rate:**
- Proportions on about 555 trades carry roughly ±4 pp (trades-pm §C.2).
- **The C0-vs-C1 comparison only uses trades dated after `player_value_history` began.** That n is unknown, so `models-eng` reports it before the read. If it is under 100, this check is descriptive only.

### 1.5 Pre-registered decision rules

**A. The production KTC blend (Q-K). This feeds the operator's D-W1 call. It doesn't make it.**

| If… | Then the model-side recommendation is… |
|---|---|
| **K-1.** C1 is **non-inferior** to C0 (lower 95% bound of AUC(C1) − AUC(C0) above −0.05), **and** C1's executed-trade fair rate is ≥ C0's − 4 pp | **Dropping the blend costs no measurable verdict quality.** I'd sign off on `ktc_blend_weight = 0` (a prod `model_config` write, done by `release-lead` on the operator's go), with a before/after Calibration readout, pre-registered as no drop of 15 pp or more in would-send. Thanks to anchoring (bias 1), this outcome is conservative |
| **K-2.** C0 beats C1 by ≥ 0.07 AUC with a CI excluding 0, **and** the executed-trade fair rate agrees (C0 ≥ C1 + 4 pp) | The blend carries real signal beyond the anchoring. **A KTC license has model value.** Recommend the operator ask KTC (D-W1b). If KTC declines, look for a lawful trade-driven substitute (F2) before dropping the blend |
| **K-3.** Anything else | **Inconclusive on the grades.** The terms decision stands on its own merits. If the operator kills the scrape, I sign off conditionally, with the same before/after readout as K-1 |

**When the executed-trade window is small.** Stored C0 equals C1 before 2026-07-17, so the C0-vs-C1 executed-trade window holds only later trades, likely fewer than 100. If that n is under 100, the fair-rate clauses in K-1 and K-2 are **reported but not binding**:
- **K-1** rests on AUC non-inferiority alone. That is still conservative, because anchoring favors C0.
- **K-2** can't be told apart from anchoring without an unanchored check. A C0 win therefore reads as **K-3** until hidden-value cards (D-W5) reach 150 Yes / 150 No and confirm it.

**B. The go-live call (NEXT 1b).** The baseline is the 2026-10-14 recommendation, part of which D-207 has carried out: today's engine stays the default (now filtered), the challengers run as live arms, and promotion happens only on live outcomes.

| If… | Then the go-live call… |
|---|---|
| **R1.** No challenger beats E1 by ≥ 15 pp (CI excludes 0), or the win fails leave-one-grader-out | **Is unchanged** |
| **R2.** A challenger beats E1 by ≥ 15 pp (CI excludes 0), its direction holds for every grader with ≥ 20 cards, and it passes the bench guardrails and insult bar | **Shifts toward that challenger:** it becomes the lead live arm. It becomes the default **only** under the live outcome promotion rule. Grades alone never promote |
| **R3** (tier B or C). K2 or F2 beats **C1** by ≥ 0.07 AUC (CI excludes 0), surviving leave-one-grader-out, **and** its executed-trade fair rate is ≥ C1's + 4 pp | **Pauses promotions.** The shared board is the weak point, so I write a spec for all arms: a licensed or substitute trade-driven input to consensus, or a fairness guardrail. The round is then re-run. **On shown cards R3 is provisional.** The pause applies, since it is reversible. The spec waits for confirmation on hidden-value cards (D-W5, ≥ 150 Yes / 150 No), or on an executed-trade check where the comparator has dated history. The reason: both C1 (DP) and K2 (correlated with K1) share part of C0, so the direction anchoring pushes in K2 vs C1 is unknown |
| **R4** (tier B or C). Q-D: comparator-unfair cards have would-send ≥ 15 pp below comparator-fair cards (n ≥ 100 in each group) | **Add a comparator fairness filter** to `deck_quality`, alongside R1 or R2. Licensed or permitted data only |
| **R5.** An arm breaks the insult bar (the canonical definition is pending, wave-1 D2) or fails the bench guardrails | **The arm is excluded** from live arms |
| **R6** (tier B or C). K2 or F2 is within ±0.07 of C1 | **No change.** It stays a monitoring comparator. Read it as uninformative at today's n, not as "KTC adds nothing" |
| Always | Graduation is judged only against the restated criterion 2 (§2). Graduation and the go-live call are separate decisions |

### 1.6 Eval route (`models-eng`, requested `head-bizops` → `head-eng`)

| Run | What | Builds on | Data | Blocked on |
|---|---|---|---|---|
| **E-1a** | Q-K: C0 vs C1 paired AUC, plus engine scorers E1/E2/E3, with every §1.3 handling | Extend `eval/fit_scorecard_test.py` | Prod read-only graded cards; dated DP boards | D-W4 |
| **E-1b** | Executed-trade fair rate, C0 vs C1 (report how many trades fall in the window first) | New offline script | `sleeper_trades`, `player_value_history`, DP history | D-W4 |
| **E-3** | Q-C round-3 arms | The existing `GET /api/admin/grading/report?since=2026-10-15` | Prod read-only | D-W4 |
| **E-2** | Q-A: C0 vs C1 board agreement | New offline script | Repo plus DP history | none |
| **E-4** | Q-B and Q-D with K2 or F2 | E-1a plus the comparator | Licensed or permitted data only | D-W1 or D-W6 |

<!-- [trades-pm] data notes: start -->

**[trades-pm] data notes** on §1.6. These are facts on data and terms; models-lead keeps the verdicts.

| Run | Data note |
|---|---|
| E-1a | **Labels.** `fit_scorecard_test.py:37` sets `WOULD_SEND, WOULD_NOT = 4, 2`, so today it drops legacy grade-3 answers from AUC. That is bias 5's sensitivity convention; the primary rule (legacy 3 counts as No, as `share_ge_4` does) has to be added when the script is extended. Round 2 starts at `ROUND2_SINCE` (`:36`). Format per card comes from `grading_sessions.source_json.scoring_format` (`docs/data-dictionary.md:1942`) |
| E-1b | **Stored C0 equals C1 before 2026-07-17**, when the blend started (`docs/data-dictionary.md:1263`). So the effective window is trades after 2026-07-17, not trades after `player_value_history` began (the §1.5A small-window rule). The 2026 seasons held 26 trades on 2026-08-16 (`docs/business/analytics/2026-08-16-organic-trade-corpus.md:23`), plus whatever has been captured since. The committed DP boards cover September to December only |
| E-3 | `GET /api/admin/grading/report` filters `since` on session `created_at`, and counts only completed sessions unless `include_open=1` (`docs/api-reference.md:965`). Auth is `X-Cron-Secret` |
| E-2 | C0 is in the repo only through the 2026-07-17 KTC fixtures (TP-1). Stored C0 is in prod `player_value_history`, which needs D-W4. A fresh pool build runs the KTC scrape. **So in practice E-2 needs D-W4, or it inherits TP-1** |
| E-4 | **K2:** no export, API or archive exists, and KTC's published terms prohibit capture without written permission. **F2:** terms unverified. Q-D's 5% band is a third-party measurement (likely, research-memo §2.5) |

<!-- [trades-pm] data notes: end -->

---

## 2. O1: draft restatement of graduation criterion 2 [models-lead], *draft for operator ratification*

Unchanged from draft 1.

**Today's text** (`docs/plans/value-core-engine/scope.md:33`): "The operator's blind grade averages **≥ 4.0**."

**Why it must be restated.** Under D-208, Yes is sent as 5 and No as 1, so a mean grade equals 1 + 4·p(Yes). "≥ 4.0" is therefore exactly **would-send ≥ 75%**. The bar moved from a grade scale to a rate without anyone choosing it. The operator gave 1 or 5 on 95% of cards (D-208's context), so the literal translation is faithful.

**Draft (option A, recommended):**
> **2. On at least 40 cards from the candidate engine graded by the operator (Yes/No, or legacy 1–5 counted as Yes at ≥ 4), the operator's would-send rate is ≥ 75%.**

- At n = 40 and 75%, the 90% CI is about 61–83%.

**Companion: restate criterion 3, also a draft.**
> A higher would-send rate than the incumbent's cards in the same round, with the direction holding for every grader with ≥ 20 cards of each.

**Option B (not recommended):** a 75% bar on the pooled panel. The best pooled arm in round 2 reached 55%, and grader severity differs widely, so a pooled absolute bar would mostly measure who graded.

**New caveat from bias 1.** Criterion 2 is graded with C0 values on screen. That is acceptable for *engine* graduation, because every arm is graded under the same display. It is not acceptable for comparing *value boards* (§1.3).

**Data point I can't read myself:** the operator's own round-2 would-send rate per arm (an `analytics-lead` query).

---

## 3. 5.2 League-specific valuation as testable hypotheses [models-lead]

### 3.1 How much lift justifies how much complexity (pre-registered)

Every lift must clear the detectable gap in §1.4, hold **out of time**, and not regress other segments.

| Cost tier | Example | Lift that justifies it |
|---|---|---|
| Parameter only | H-L1, H-L1a (H-L1a also widens the `scoring_format` enum, a schema/API change that needs a scope block) | AUC +0.05 in the segment, or real-trade recall@10 +5 pp |
| New sub-model | H-L2, H-L3a, H-L3b | AUC +0.07 or would-send +15 pp in the segment, **and** the segment holds ≥ 15% of active leagues (an `analytics-lead` query) |
| Per-league learned state | H-L4 | Recall@10 +5 pp on a held-out season in ≥ 3 of 5 franchises after shrinkage, **and** a storage footprint that task 2 accepts |

### 3.2 Hypotheses

Updated for the terms findings.

| # | Hypothesis | Data needed | Eval route (`models-eng`) | Supported by data FTF may lawfully use? |
|---|---|---|---|---|
| **H-L1a** (strong prior) | **FTF's format key is binary:** Superflex **or** TE premium maps to `sf_tep` (`_detect_scoring_format_from_meta`, `backend/server.py:750-786` at `678834ab`). So **1QB leagues with TE premium price QBs at superflex values**, and SF leagues without TE premium get the ×1.18 TE uplift. A 4-bucket key (1QB/SF × TEP off/on) would fix both. This is a likely mis-pricing, not a speculative idea | The format census of corpus franchises and graders' leagues; per-card `scoring_format`; DP's 1QB and SF boards | E-1a restricted to the affected cells; S2 balance error for trades in affected leagues; recall@10 | **Depends on the census.** If any affected league has ≥ 30 graded cards or ≥ 30 executed trades, it's testable now. If not, and `analytics-lead`'s active-league mix shows ≥ 5% of leagues affected, I'd write the spec on prior grounds, with a before/after readout |
| **H-L1** | Format handling (SF vs 1QB, TE premium) improves verdicts within SF and TEP leagues | FTF's own format machinery (separate SF/1QB boards, D-054, `tep_te_uplift` 1.18, the v4 superflex QB slot) against a format-blind control. **KTC's per-format values are blocked (D-W1)** | E-1a by format; `value_core_recall` by format | **Partly.** The graders span 1QB and SF; TEP is thin. It can show a direction |
| **H-L2** | Re-pricing by league scoring (PPR variants, 6-point passing TDs, IDP) improves verdicts in non-standard leagues | League scoring settings; points forecasts (`season_forecasts.py`). Note that KTC's values are fixed to 0.5 PPR, so KTC can't serve as the reference here | A points-based re-pricing backtest on recall; E-1a by scoring class | **No.** The corpus's scoring mix is narrow, and a broader corpus is gated (D-W7) |
| **H-L3a** | A **global** consolidation premium (2-for-1, 3-for-1), not a league-specific one, improves verdicts on uneven trades. KTC's Value Adjustment is unpublished and terms-blocked, so the premium is modelled from FTF's own data | Card shape (from `trade_json`); executed-trade shapes | E-1a on uneven graded cards; S2 balance error by shape | **Yes.** Uneven trades are plentiful (2-for-1 is 27% of the corpus, 3+ on a side 31%), so trade supply isn't the limit |
| **H-L3b** | That premium should vary with roster settings and team count | League settings across many leagues | E-1a split by shape × roster settings | **No.** All corpus leagues have 12 teams, and roster depth varies across only two franchises. Needs a broader corpus (D-W7) |
| **H-L4** | A league's own trade market differs measurably from the global one | Per-league trade history over several seasons; dated DP values (no KTC needed) | **Step 1:** a variance-components test on the 555 trades using DP history. **Step 2, only if step 1 finds an effect:** out-of-time recall with and without offsets | **Step 1 only.** The 555 trades across 5 franchises can show whether league effects exist, not support deployment |

<!-- [trades-pm] data notes: start -->

**[trades-pm] data notes** on §3.2. These are facts on data and terms; models-lead keeps the verdicts.

| # | Data note |
|---|---|
| H-L1a, H-L1 | The corpus has one known SF franchise (Lakeview: full PPR, 0.5 TEP) and one known 1QB franchise (FFv3: half-PPR, IDP). **Neither is in an H-L1a cell:** Lakeview is SF with TEP, and FFv3's committed league objects carry no `bonus_rec_te` (`backend/tests/fixtures/outlook-calibration/{ffv3,lakeview}-2025.json`). So H-L1a's test rests on La Resistance, Bush League, SFO and the graders' leagues, all unknown until the format census. Each card's format is in `grading_sessions.source_json.scoring_format` (`docs/data-dictionary.md:1942`); the stored value is already the binary bucket, so the census needs the league's own `roster_positions` and `scoring_settings` |
| H-L2 | Scoring settings are public on Sleeper's league object but **not stored**: `leagues` keeps only `default_scoring` and `total_rosters` (`backend/database.py:521-531`). Visible scoring variety is half vs full PPR only, with no 6-point passing TD. No dated projections exist for 2022–2025. A broader corpus faces Sleeper Terms §11.1 and §11.3 and the API's commercial-use clause (research-memo §4.2; OQ-1) |
| H-L3a | Card shape comes from `grading_cards.trade_json` (`docs/data-dictionary.md:1958`). Uneven executed trades are plentiful: 2-for-1 27%, 3+ on a side 31% (`docs/business/analytics/2026-08-16-organic-trade-corpus.md:58-60`). Executed trades are positive-only, so they enter through balance error by shape, not AUC |
| H-L3b | All 22 league-seasons are 12-team (`docs/business/analytics/2026-08-16-organic-trade-corpus.md:21`). Roster depth varies across only two franchises (15 starters and 39-man rosters vs 10 and 31). The limit is the franchise count, not trade supply |
| H-L4 | **Step 1 runs in consent scope:** 555 trades, 5 franchises, with the operator in all five, so cluster by franchise. Committed fixtures cover FFv3 2022–2025 and Lakeview 2024–2025 (214 trades). The other three franchises' trades are in prod only. Offseason DP boards come first: 47% of trades fall in May–August. Exclude FTF-recommended trades through `suggestion_trade_links` (`backend/database.py:1131-1146`), so step 2 never learns FTF's own prices |

<!-- [trades-pm] data notes: end -->

### 3.3 Verdict on data support

- Lawful data today supports **H-L1 as a direction**, **H-L3a** and **H-L4 step 1**.
- **H-L1a** waits on the format census, which needs only consent-scope reads.
- **H-L2 and H-L3b face two gates:** a broader corpus, *and* Sleeper's commercial-use terms for crawling it (D-W7).
- KTC's claimed 232,050 leagues behind its Trade DB show that such a corpus is possible. They don't make it lawful for FTF.

---

## 4. Product half [trades-pm]

### 4.1 The fixed trade set

The set is pre-registered now, before any read. It has four subsets, and they are **never pooled into one metric**. It is frozen at each read date: no cards are added after a read, and nothing is tuned on it.

| Subset | What it is | Label | Can answer | Can't answer |
|---|---|---|---|---|
| **S0. Calibration graded cards, rounds 1–3** | S1 plus round 1: the operator only, 120 cards, value-core-1 decks, no fit arms (D-199, D-200). Every card carries post-2026-07-17 C0 values | Would-send (Yes/No), plus optional tags | **Board contrasts (Q-K, Q-B): the primary set,** stratified by grader and by round | Engine contrasts: round 1 is excluded from them |
| **S1. Calibration graded cards, rounds 2 and 3** | <ul><li>Every answered, non-skipped card in sessions from round 2 (`ROUND2_SINCE`, `backend/eval/fit_scorecard_test.py:36`) through the round-3 horizon (175 cards per arm or 2026-11-05, D-W3).</li><li>Grades are in `grading_cards.grade`: Yes/No since D-208 (sent as 5/1), with legacy 1–5 grades counted as Yes at ≥ 4. **Skipped cards are excluded.**</li><li>Shared cards count once in board contrasts and are attributed by `arms_json` in arm contrasts (models-lead bias 3).</li></ul> | Would-send (Yes/No), plus optional tags | <ul><li>Q-K (i) and Q-B: the sensitivity set for board contrasts.</li><li>Engine scorers and Q-C: within round only (round 3 primary, round 2 secondary).</li><li>Q-D: fair vs unfair cards.</li><li>Per-grader direction.</li></ul> | <ul><li>Market truth outside C0's band (bias 2).</li><li>Anything free of anchoring (bias 1), until D-W5.</li><li>Formats the graders don't play.</li><li>K1 or K2 scoring without D-W1.</li></ul> |
| **S2. FTF's 555 executed trades** | <ul><li>22 league-seasons, 5 franchises, 2022–2026.</li><li>Priced at trade time, offline, from committed fixtures plus dated DP boards, in the `backend/eval/value_core_recall.py` shape.</li></ul> | None (positive-only) | <ul><li>Executed-trade fair rate per board.</li><li>Balance error and recall@10.</li><li>H-L1 direction.</li><li>H-L4 step 1 (do league effects exist?).</li></ul> | <ul><li>Acceptance or AUC: there are no negatives.</li><li>10- or 14-team leagues, 6-point passing TDs, scoring variants: zero franchises.</li><li>C0 vs C1 before 2026-07-17: stored C0 equals C1 then.</li><li>**Offseason trades (47%), until offseason DP boards exist.** The 24 committed boards are all September–December.</li><li>La Resistance, Bush League and SFO, until their fixtures exist.</li></ul> |
| **S3 (optional). 2026 executed trades in captured leagues** | `sleeper_trades` rows from the 2026 season dated after 2026-07-17 | None | Q-K (ii). These are the only executed trades whose stored C0 includes the KTC blend, so they are the whole C0-vs-C1 executed-trade window | Anything beyond description below n = 100. 26 trades existed on 2026-08-16 |

**Which subset each question uses** follows models-lead's ruling in §1.4:
- **Board contrasts (Q-K, Q-B):** S0 is primary, stratified by grader and by round. S1 is the sensitivity check, and a conclusion needs both to agree in direction.
- **Engine contrasts (engine scorers, Q-C):** within round only. Round 3 is primary, round 2 secondary, and round 1 is excluded.
- Without round 1, n is about **258 answers** today (378 minus 120; estimate) until round 3 adds cards.

**S2 prerequisites** (tier A, §5):
- Offseason DP boards from DP's git history.
- Fixtures for La Resistance, Bush League and SFO. These are consent-scope data, already in prod `sleeper_trades`. Whether new fixtures are committed to this public repo or kept private is `head-eng`'s call.

### 4.2 Human ground truth

- **Primary label: would-send,** the share of non-skipped grades ≥ 4 (`share_ge_4`), per D-208. Yes is sent as 5 and No as 1. Legacy 1–5 answers count as Yes at ≥ 4, so a legacy 3 counts as No.
- **Tags are diagnostic, never a primary label.** There are seven optional tags (`docs/cross-client-invariants.md` § Calibration tags and scale). gdubs10 tagged only 10% of low cards (D-208), so a tag share mostly measures who tags. Report tags per grader.
- **Grader stratification in every read.**
  - There are three graders with very different styles: the operator gives 1 or 5 on 95% of cards, and jonbonjourvi gives 1–2 on 73% (D-208).
  - Report per grader (`by_grader[]` in `GET /api/admin/grading/report`, `docs/api-reference.md:965`), with leave-one-grader-out direction checks.
  - Report the operator's own would-send per arm separately. That is an `analytics-lead` query (models-lead §2).
- **Definitions to confirm before the read.** `analytics-lead` owns metric definitions.
  1. **Legacy grade 3: settled by models-lead (§1.3, bias 5).** It counts as No in the primary analysis, as `share_ge_4` does. A sensitivity check drops it, which is the convention `fit_scorecard_test.py:37` already uses. `analytics-lead` confirms the definition.
  2. **Tag vocabulary.** The CSV tool's tags (`backend/eval/blind_grade.py:30`) differ from the app's (`backend/blind_grading.py:33`). Any tag analysis uses the app's.
  3. **Session filter.** `report?since=` filters on session `created_at` and counts completed sessions only unless `include_open=1`. The round-3 read states both settings.
- **Ownership and change control.**
  - trades-pm owns grading content: arms per round, cards per session, the prompt, the tags, and the intro copy.
  - A change to the grade scale, the tags or the arms also needs `models-lead`'s review (comparability) and `analytics-lead`'s (metric definitions).
  - The neutral card shape is pinned in `docs/cross-client-invariants.md` § Calibration tags and scale. A field added on either side is a blinding change, and it goes through the blind-grading plan's change control.
- **Grading-content changes land only at round boundaries.** Nothing changes inside round 3 (D-W3). D-W5, and D-208's not-adopted "require a reason on No", go to round 4 together, if at all.

### 4.3 D-W5: the hidden-values grading variant

**The problem.** The Calibration card shows FTF's numbers next to the trade:

- `mobile/src/components/GradingCard.tsx:53` renders each asset's value, or "—" when it is null.
- `:67-68` renders the "TOTAL" label and each side's sum, computed by `sumValues` at `:33-34`.
- The values are C0, written by `blind_grading.neutral_trade` (`docs/data-dictionary.md:1958`).

Graders judge FTF's numbers as much as the trade. That anchors Q-B and Q-K toward C0 (models-lead bias 1): C0 beating or tying another board tells us nothing.

**Options**

| Option | What graders see | Labels free of anchoring | Comparable with rounds 1–3 | Measures the anchoring itself | Grader effort |
|---|---|---|---|---|---|
| **A. Hide on a randomized share** | Values and totals hidden on a random ~50% of cards in each session, balanced by arm | Half the cards | Yes, on the shown half | **Yes:** hidden vs shown would-send, same arms, same graders | Higher on hidden cards only |
| **B. Hide for all** | No values or totals on any card | Every card | **No.** Would-send is measured under a different display, and criterion 2's 75% bar (§2) was set with values shown | No | Higher on every card |
| **C. Keep them; pre-register the bias** | As today | None | Yes | No | Unchanged |

**Recommendation: A, a randomized 50% hidden share, from round 4, in rounds used to judge value boards.**

- A is the only option that keeps engine rounds comparable to rounds 1–3 **and** measures how big the anchoring is.
  - If hidden and shown would-send match, the bias is small, and the pooled rounds 1–3 grades regain weight for board contrasts.
- C leaves every board comparison one-sided for good.
- B buys clean n at the cost of breaking the graduation series (D-W2).

**models-lead agrees** with option A from round 4 and sets four read thresholds for it (its D-W5 review, §4.2 of its wave-2 working file, outside this repo). It also asks to start in round 4 even before D-W1 or D-W6 settle, because Q-K is itself sensitive to anchoring. Its §1.5A and §1.5B use the hidden-value cards to confirm a K-2 or R3 result.

**Costs**

- **Clean n accrues at half speed.**
  - models-lead reads board contrasts on hidden cards at 150 Yes and 150 No. At about 50% would-send, that is about 300 hidden cards: about 600 graded cards under A, and about 300 under B. A fully decisive 250 / 250 doubles both.
  - Rounds 1–2 produced about 378 answers between the Calibration launch (2026-10-07, `living-memory/CHANGELOG.md:103`) and 2026-10-14, roughly 47 a day (estimate). At that pace, the 150 / 150 read point is roughly **13 grading days under A**, against 6–7 under B.
- **Grader effort.**
  - On a hidden card the grader has to value each player. Expect slower cards and more skips.
  - Skipped cards are excluded, so **uneven skipping would bias the hidden half.** Pre-register a check: hidden vs shown skip rate per grader, flagged at a gap of 10 pp or more.
- **Comparability.**
  - Would-send per arm is reported by display condition.
  - Round-4 numbers compare with rounds 1–3 only on shown cards.
  - Criterion 2 (§2) is read on shown cards only.
- **Tags shift meaning on hidden cards.** "Overpay" becomes the grader's own valuation, not a reaction to FTF's numbers. Report tags by condition.

**Product requirements.** These are for the scope block; nothing is built here.

1. **Hide in the display only.** The card keeps its stored C0 values for scoring. A hidden card hides the per-asset values **and** both totals.
   - Sending `value: null` alone isn't enough: the card would show "—" per asset and a total that silently sums nulls as 0 (`GradingCard.tsx:33-34,53`).
2. **Record the hidden flag per card,** as hidden provenance that never reveals the arm.
3. **Randomize per card** from the session seed, balanced across arms.
4. **No copy suggests which condition is "right".** Whether to add one neutral intro line (for example, "Some cards show values, some don't.") is a question for `design-lead` and `ux-lead`.
5. **Treat it as a blinding change** under the blind-grading plan's change control. `mobile/tests/check-blind-grading.js` pins `GradingCard`'s imports and scans it for tokens that would reveal an engine.

**Gate**

- It's a UI and data-collection change to the Calibration screen (`mobile/src/screens/CalibrationScreen.tsx:433` mounts `GradingCard`). That is Rankings' code, so `rankings-eng` builds it.
- It needs:
  - a scope block (`docs/templates/feature-scope.md`);
  - reviews from `design-lead` and `ux-lead` (layout and copy), `models-lead` (comparability and bias handling) and `analytics-lead` (metric definitions and the provenance field).
- D-W5's decision owner is `head-product`.

### 4.4 User-facing framing if a KTC-informed or substitute fairness filter ever ships

This covers models-lead's R3 (a trade-driven input to consensus, or a fairness guardrail) and R4 (a comparator fairness filter in `deck_quality`).

- **No KTC data, values, verdicts or branding on any user surface** without a written KTC license that covers production use. An evaluation license (TP-3) doesn't cover shipping.
- **Today no KTC value is labelled anywhere in the apps.**
  - The one user-facing mention is a comparison sentence in `web/faq.html:185`, which carries no data.
  - If the blend is killed (TP-1), trades-pm re-checks that sentence for accuracy. That is a content check, not a terms one.
- **A filter is plumbing, not a claim.**
  - R4 would drop cards before they are served. No card copy says a third party judged the trade.
  - Card copy stays FTF's own (`backend/trade_narrative.py` templates). Any fairness wording refers to Fleeced's values, never to KTC or an unnamed "market".
- **A substitute comparator (F2) needs its own terms check (D-W6), with two separate answers:** evaluation use, and production use. Passing the first doesn't cover the second.
  - If its license requires attribution, as DP's CC-BY does, the credit goes where FTF already credits data sources, not on trade cards.
- **Calibration never shows graders a third-party verdict.**

### 4.5 What would change the product

This maps models-lead's pre-registered outcomes (§1.5, §3.1) to product actions. Nothing here pre-empts the operator's calls.

| Outcome | Deck behavior | Card copy | Calibration content |
|---|---|---|---|
| **K-1** (dropping the blend costs nothing), and the operator kills the scrape or doesn't license it | `ktc_blend_weight = 0`: a prod `model_config` write by `release-lead` on the operator's go. Seeds go DP-only on the next pool build, so card values, tiers and ranking seeds shift for every user | None. Re-check `web/faq.html:185`. A one-line release note is `release-lead`'s call | A before/after readout (K-1's bar: no drop of 15 pp or more in would-send). Card values change between rounds; note it in the round log |
| **K-2** (the blend carries signal) | No change until a license or an F2 exists | None | None |
| **K-3** (inconclusive) | Follows the terms decision alone. If the scrape is killed, as K-1 | As K-1 | As K-1 |
| **R1** (no challenger wins) | Unchanged: the filtered live engine stays the default | Unchanged | The next round keeps or retires arms (trades-pm proposes, models-lead reviews) |
| **R2** (a challenger wins by ≥ 15 pp) | The challenger becomes the lead live arm. It becomes the default only under the live-outcome promotion rule | Review the challenger's card copy before it reaches more users | The next round centers on the challenger vs the default |
| **R3** (a trade-driven board beats C1) | Promotions pause. A spec follows for a licensed or substitute board input, or a guardrail, across all arms | None until the spec | The round is re-run after the spec ships |
| **R4** (comparator-unfair cards graded ≥ 15 pp lower) | A comparator fairness filter in `deck_quality`, on licensed or permitted data only. Decks get smaller | No new copy (§4.4) | The next round measures the effect on deck size and would-send |
| **R5** (an arm breaks the insult bar or the bench guardrails) | The arm leaves the live arms | — | The arm leaves Calibration |
| **R6** (within ±0.07 of C1) | None | None | Kept as a monitoring comparator, if licensed |
| **H-L1a** clears its bar, or the census triggers models-lead's prior-grounds spec (§3.2) | A 4-bucket format key (1QB/SF × TEP off/on) replaces today's binary one. Users in 1QB+TEP and SF-without-TEP leagues see different values. The `scoring_format` enum widens: a schema and API change, so it needs a scope block | Any copy naming a league's format must match the new buckets | Sessions carry the new format |
| **H-L4** step 1 finds league effects | Step 2 only. Any league-offset copy ("your league pays up for X") ships only for leagues above a data floor, at league level and never per manager (`docs/plans/trade-relevance-engine/prds/prd-p2-market-and-history.md` non-goals) | Gated as stated | None |
| **H-L3a** clears its bar | A global consolidation term in trade pricing. Deck composition shifts on uneven trades | No new copy | The next round measures the effect on uneven cards |
| **H-L2, H-L3b** | Parked until OQ-1 and D-W7 clear, or until organic growth fills the cells | — | — |

---

## 5. Run tiers and blockers [trades-pm]

| Tier | Run or item | What it answers | Blocked on | When |
|---|---|---|---|---|
| **A** | E-1a: Q-K paired AUC, C0 vs C1, plus the engine scorers, on S1 | What dropping the blend costs (K-1, K-2 or K-3). H-L1 direction, by format | D-W4 | Once D-W4 is granted |
| A | E-1b: executed-trade fair rate, C0 vs C1, on S3 | Q-K (ii) | D-W4. The window n is reported first; expect fewer than 100. Below 100, the executed-trade clauses in K-1 and K-2 are reported but **not binding** (§1.5A) | Once D-W4 is granted |
| A | E-3: Q-C, the round-3 arms | The go-live read (R1, R2, R5) | D-W4, D-W3 | At the horizon: 175 per arm or 2026-11-05 |
| A | E-2: Q-A board agreement, C0 vs C1 | Where the boards diverge | D-W4 in practice (see the §1.6 data notes) | Once D-W4 is granted |
| A | Format census (`models-eng`) of the five corpus franchises: format, scoring, team count | The corpus mix; H-L1 and LS-1 cells | Existing read authority only (consent scope) | Now |
| A | `analytics-lead`: format mix of active leagues; the operator's round-2 would-send per arm | The ≥ 15% reach bar (§3.1); context for criterion 2 | None | Now |
| A | S2 prerequisites: offseason DP boards; fixtures for three franchises | H-L4 step 1; LS-1 sanity check; measured σ and ρ for the balance-error metric | Fixtures need D-W4 or the existing backfill script. Committing them is `head-eng`'s call | Now |
| A | H-L4 step 1: variance components on the 555 trades | Do league effects exist? | The S2 prerequisites | After them |
| A | **H-L1a:** 1QB leagues with TE premium priced at superflex QB values, and superflex leagues without it given the TE uplift (`backend/server.py:750-786`) | Is the binary format key mis-pricing real leagues? | **The format census.** Testable if an affected league has ≥ 30 graded cards or ≥ 30 executed trades; otherwise models-lead's prior-grounds rule applies (§3.2) | After the census |
| A | **H-L3a:** a global consolidation premium; E-1a on uneven cards, S2 balance error by shape | Does a consolidation term improve verdicts on uneven trades? | D-W4; the S2 prerequisites | Once D-W4 is granted |
| **B** | E-4 with K2 (Q-B, Q-D, the KTC variants of R3 and R4), and any K1 use beyond the existing scrape | The operator's ask 1, against KTC itself | **D-W1** (KTC's written permission), after TP-1 and TP-3. **R3 is provisional on shown cards:** the promotion pause applies, but the spec waits for hidden-value cards or a dated executed-trade check (§1.5B) | Waits |
| **C** | E-4 with F2 | Ask 1, against a substitute | **D-W6** (a terms check, and the operator accepting a substitute) | Waits |
| Clean labels | Q-B and Q-K on hidden-value cards | A board contrast free of anchoring | **D-W5** (scope block, build, round 4). Read at 150 Yes / 150 No | Waits |
| Graduation | The criterion 2 read | Engine graduation | **D-W2** (ratify O1) | At the horizon |
| Corpus | Any corpus beyond consent scope: H-L2, H-L3b, LS-3 to LS-5, a census of non-member leagues | League-specific adjustments beyond format | **OQ-1** (TP-2, TP-3) and **D-W7** | Waits |

---

## 6. Decisions needed

This merges models-lead's D-W1 to D-W7 (its IDs, owners and recommendations, condensed) with trades-pm's TP-1 to TP-3.

| # | Decision | Who decides | Recommendation | Unblocks |
|---|---|---|---|---|
| **D-W1** | **KTC data rights.** (a) Keep, kill or license the production scrape, and the KTC fixtures in this public repo. (b) Ask KTC for an evaluation license: a dated Tradesourced snapshot plus calculator access for about 500 trades. (c) The grey-area hand sample | Operator. Any KTC contact is outbound | **models-lead:** (a) the terms case is trades-pm's, and the model evidence is Q-K, read by §1.5A. (b) Ask if Q-K lands on K-2. (c) Don't use the hand sample as decision evidence. **trades-pm:** (a) is TP-1; for (b), see TP-3 | Tier B |
| **D-W2** | **Ratify O1:** option A plus the criterion 3 restatement (§2) | Operator, via `head-bizops` | **models-lead:** option A, before the round-3 read (2026-11-05 at the latest) | The graduation read |
| **D-W3** | **Round-3 shape:** 3 arms, 175 cards per arm or 3 weeks, no interim reads | Operator. Arm composition is `models-eng`'s config | **models-lead:** yes. **trades-pm:** yes, and no grading-content changes inside round 3 | E-3 |
| **D-W4** | **Prod-read authority for `models-eng`** to run E-1a, E-1b and E-3 | Operator, in `models-eng`'s session | **models-lead:** grant it read-only, under W3's terms (W3 is a models-lead org reference, outside this repo) | All tier-A prod reads |
| **D-W5** | **A hidden-values Calibration variant** for rounds that judge value boards | `head-product` (`trades-pm` owns grading content), with models-lead's review | **models-lead:** yes, trades-pm's option A from round 4, with four read thresholds (its D-W5 review, §4.2), started even before D-W1 or D-W6 settle. **trades-pm:** option A, a randomized 50% hidden share from round 4 (§4.3) | Clean labels |
| **D-W6** | **Accept a substitute trade-driven comparator** (for example FantasyCalc, after a terms check) if KTC declines or doesn't answer | Operator, because the ask named KTC | **models-lead:** yes, if its terms permit evaluation use. **trades-pm:** yes, with the two-part terms check in §4.4 | Tier C |
| **D-W7** | **Sleeper's commercial-use terms** for a broader trade crawl. FTF's existing reads may carry the same exposure | Operator, or `head-bizops` | **models-lead:** flagged only; it gates H-L2 and H-L3b. **trades-pm:** decide it together with OQ-1 (TP-2, TP-3) | The corpus tier |
| **TP-1** (= D-W1a) | **The production KTC scrape: keep, kill or license,** plus the KTC fixtures in this public repo | Operator. **Escalated to `head-product` on 2026-10-15** | **trades-pm:** decide before any KTC contact. The published terms prohibit the scrape without written permission whichever way Q-K lands. The fixtures are a `head-eng` clean-up either way | Tier B; TP-3 |
| **TP-2** | **Log OQ-1** in `living-memory/OPEN_QUESTIONS.md`: re-opened, extended to model building and non-member leagues, noting the 2026-10-06 Terms revision | `head-product` → the scribe. trades-pm doesn't edit living-memory | **trades-pm:** yes. The next free ID at `origin/main` is Q-040; the scribe re-greps first | The record |
| **TP-3** | **Outbound contact:** does the operator contact Sleeper, KTC, or both? | Operator only | **trades-pm:** Sleeper, yes, now: OQ-1 affects every session init, not just this plan. KTC: after TP-1; request an evaluation license if the operator wants ask 1 answered against KTC itself. models-lead would condition the KTC ask on K-2 (D-W1b); the operator picks the timing | The corpus tier; tier B |

---

## 7. Handoffs

Through org boxes only.

| From → to | What |
|---|---|
| `head-product` → operator | The decisions: D-W1 to D-W7, TP-1 and TP-3 |
| `head-bizops` → `head-eng` → `models-eng` | <ul><li>Evals E-1a, E-1b, E-2 and E-3 (§1.6), and the format census.</li><li>Freeze the round-3 arms (D-W3).</li><li>Report when `player_value_history` starts, and how many executed trades postdate 2026-07-17.</li><li>Offseason DP boards and fixtures for the three franchises.</li></ul> |
| `head-product` → `platforms-pm` | The 2026-10-06 Sleeper Terms revision and OQ-1 (research-memo §4.2–§4.3) |
| `head-product` → `analytics-lead` | <ul><li>The format mix of active leagues.</li><li>The operator's round-2 would-send per arm.</li><li>The definitional gaps in §4.2.</li></ul> |
| `head-eng` | The KTC fixtures and the review-doc KTC numbers in this public repo (research-memo §4.1a). Removing the fixtures touches `test_ktc_blend.py` and `test_mock_draft.py` |
| `head-product` → `monetization-pm` | Sleeper's API commercial-use clause (research-memo §4.2) |
| Task 2 (DB storage) | The storage table (research-memo §6) |
| `head-product` → `rankings-eng`, `design-lead`, `ux-lead`, `models-lead`, `analytics-lead` | The D-W5 scope block, once the operator approves it |
| `models-lead` | A read-only review of this branch; sign-off goes in its own report |
