# #169 Outlook Odds — Dated Value Boards and the Preseason-Source Revalidation

**Date:** 2026-08-09 · **Author:** worktree build+validation agent · **Branch:** `outlook-dated-values`
**Subject:** (1) a dated DynastyProcess value-board fetcher, (2) the first real backtest of the preseason `roster_value` strength source, (3) a re-test of pick-capital hypothesis 1b with period-correct values.
**Scope guard:** nothing under `backend/outlook/` changed, no feature flag changed, `config/features.json` untouched. `outlook.odds` stays dark. Everything below is evidence for an operator decision, not a decision.

> **Three lines:**
> 1. The blocker all three prior #169 analyses named — *"no dated historical dynasty-value board exists"* — **was false**. DynastyProcess keeps the full git history of `values-players.csv`; 24 dated boards (2022–2025) are now committed fixtures.
> 2. **Preseason playoff odds have real but weak skill** — Brier 0.1959 vs climatology 0.2500 (**+21.6 %**, 90 % CI **[+4.1 %, +38.3 %]**, excludes 0), statistically indistinguishable from the already-validated week-3 model, but **over-confident at the extremes** and beaten by climatology in 2 of 6 league-seasons. **Preseason title odds have no demonstrated skill** (+3.1 %, CI [−17.7 %, +24.9 %]).
> 3. **Hypothesis 1b is WEAKENED, not overturned.** Its Δ-roster-value sub-test flips from r = −0.11 to **r = +0.076 with a CI spanning zero** once values are period-correct. The behavioural buy:sell gradient (2.4 : 1 → 0.7 : 1 → 0.6 : 1) is bit-identical, because it never depended on values.

---

## Table of contents

- [1. The correction — a dated board does exist](#1-the-correction--a-dated-board-does-exist)
- [2. The fetcher — design, fixtures, coverage](#2-the-fetcher--design-fixtures-coverage)
- [3. Backtesting the preseason `roster_value` source](#3-backtesting-the-preseason-roster_value-source)
- [4. Ship / no-ship on rendering preseason odds](#4-ship--no-ship-on-rendering-preseason-odds)
- [5. How BUG-1 interacts with these measurements](#5-how-bug-1-interacts-with-these-measurements)
- [6. Hypothesis 1b, re-tested with period-correct values](#6-hypothesis-1b-re-tested-with-period-correct-values)
- [7. What this evidence does not support](#7-what-this-evidence-does-not-support)
- [8. Corrections issued to the three prior documents](#8-corrections-issued-to-the-three-prior-documents)
- [9. Reproducing this report](#9-reproducing-this-report)

---

## 1. The correction — a dated board does exist

Three documents, written independently on 2026-08-09, reached the same wrong conclusion:

| Document | What it said |
|---|---|
| `calibration-report-2026-08-09.md` §1 | "`RosterValueStrength` — **NO — not backtestable** … Sleeper exposes no historical rosters and FTF has no dated value snapshots, so there is no honest way to score the preseason default." |
| `hypothesis-pick-capital-2026-08-09.md` §2.2 | "there is no historical, dated dynasty-value board … Pricing a 2022 roster with today's live values would price it with hindsight." |
| `phase-2-plan.md` | "Both agents independently hit the same blocker — **no dated historical dynasty-value board exists** … Building/finding one is the prerequisite for re-testing 1b honestly." |

**All three are wrong, and in the same way: they treated the file as a live endpoint rather than as a file in a git repository.** `github.com/dynastyprocess/data` publishes `files/values-players.csv` and keeps every revision of it:

- Commit history for that path runs back to ~2020-09 on a roughly weekly cadence (verified via `api.github.com/repos/dynastyprocess/data/commits?path=files/values-players.csv`).
- Any revision is a plain GET at `raw.githubusercontent.com/dynastyprocess/data/<sha>/files/values-players.csv` (a `User-Agent` header is required — a bare `curl` gets a redirect stub).
- The column shape is stable across the whole 2022–2025 window: `player, pos, team, age, draft_year, ecr_1qb, ecr_2qb, ecr_pos, value_1qb, value_2qb, scrape_date, fp_id`. Every snapshot carries its own `scrape_date`, so a board can be dated from its contents, not just from its commit timestamp.

This is the **same source, same license (CC-BY), same trust boundary** as the live file FTF already depends on for Elo seeding — no new vendor, no new attribution obligation beyond the one `docs/integrations/dynastyprocess.md` already records.

The practical consequence is large: the calibration report's P9 pass-criterion ("preseason default source validated") was marked **FAIL — untestable**. It is testable, and §3 tests it.

---

## 2. The fetcher — design, fixtures, coverage

### 2.1 Module

`backend/dp_values_history.py`. It is a **research data source** — no route, no flag, and nothing under `backend/outlook/` imports it. The shipped product still reads the live board through `data_loader.py`.

| Function | Role |
|---|---|
| `week_boundary(season, week)` | NFL calendar anchor. `week=0` is week-1 kickoff day — "the last board published before a single game was played". |
| `resolve_commit(date)` | Nearest `values-players.csv` commit **at or before** `date`, via one `per_page=1&until=…` GitHub call. **Network.** |
| `fetch_values_csv(sha)` | That revision's raw CSV. **Network.** |
| `slim_csv(raw)` | Reduce to `player, pos, value_1qb, value_2qb, scrape_date`; drop rows with no value in either column. ~8× smaller than raw. |
| `build_value_map(rows, scoring=…)` | `{sleeper_id: value}` + a `JoinReport`. |
| `values_as_of(key, …)` | The headline call. **Offline by default** — reads a committed snapshot; a date with no snapshot **raises** rather than silently substituting a neighbouring board. `allow_network=True` opts into the live path. |

Both network calls are wrapped in `observe_call("dynastyprocess", "values_history", …)` per the observability conventions, distinguished by a `phase` prop (`commits` / `raw`). Passing the `_opener` test seam sets `active=False`, so tests never write analytics rows.

### 2.2 Committed fixtures

`backend/tests/fixtures/dp-values-history/` — **24 snapshots, 484 KB total**, plus `index.json` carrying per-snapshot `{season, week, sha, committed_at, scrape_date, rows, raw_bytes, slim_bytes}`. Grid: seasons 2022–2025 × weeks {0, 3, 6, 9, 12, 14}. Minted once by `scripts/dp_values_history_capture.py`; **every analysis in this report runs offline against them.**

The four preseason boards:

| Season | Key date (kickoff) | Resolved sha | Board `scrape_date` | Rows |
|---|---|---|---|---|
| 2022 | 2022-09-08 | `beb24c54f6` | 2022-09-02 | 553 |
| 2023 | 2023-09-07 | `5308c3c41d` | 2023-09-01 | 576 |
| 2024 | 2024-09-05 | `ce5e9ba021` | 2024-08-30 | 534 |
| 2025 | 2025-09-04 | `10dde2b393` | 2025-08-29 | 546 |

DP commits weekly, so a resolved board is **up to 7 days stale** relative to its key date. That lag is always in the safe direction — a board can never contain information from after the date it is used to price — and is pinned by a permanent test (`test_every_indexed_snapshot_exists_and_carries_no_look_ahead`, asserting `scrape_date <= key` for all 24).

### 2.3 The name → Sleeper-id join, and its unmatched rate

`values-players.csv` is name-keyed; everything downstream is Sleeper-id keyed. The join **reuses the shipped crosswalk** rather than inventing one, in three tiers, all position-strict (#127):

1. **Tier 1** — `espn_service` DP crosswalk (`db_playerids.csv`) with `data_loader.DP_TO_SLEEPER_NAME` applied. This is byte-for-byte the join the live Elo-seed pipeline performs.
2. **Tier 2** — same crosswalk, generational suffixes (`jr/sr/ii/iii/iv/v`) stripped from both sides. Pure name drift: DP wrote "Allen Robinson II" in 2022 and "Allen Robinson" later.
3. **Tier 3** — an optional caller-supplied index. The analyses here build it from the Sleeper players dump restricted to the 1,078 ids actually rostered in the 6 league-seasons. Needed because `db_playerids.csv` is a *current* file that has dropped some long-retired players.

The crosswalk itself is served from the **bundled snapshot** (`backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv`), not a live fetch. Verified 2026-08-09: on all four preseason boards the bundled snapshot resolves exactly as many rows as the live file, so offline costs nothing in coverage.

**Unmatched DP rows per preseason board:**

| Season | tier 1 | tier 2 | tier 3 | unmatched, tiers 1–2 only | unmatched, all tiers |
|---|---|---|---|---|---|
| 2022 | 510 | 27 | 6 | 16 (2.9 %) | **10 (1.8 %)** |
| 2023 | 542 | 21 | 6 | 13 (2.3 %) | **7 (1.2 %)** |
| 2024 | 517 | 11 | 5 | 6 (1.1 %) | **1 (0.2 %)** |
| 2025 | 533 | 5 | 7 | 8 (1.5 %) | **1 (0.2 %)** |

**Unmatched rows are dropped, never guessed** — the same rule the ESPN import follows.

The row count is the wrong denominator on its own, because most unresolved rows are deep-bench players nobody rosters. The load-bearing numbers are roster-side:

| league-season | scoring column | board | roster coverage | starting-slot coverage |
|---|---|---|---|---|
| lakeview-2025 | `value_2qb` (SF/TEP) | 2025-09-04 | 98.9 % | **100.0 %** |
| lakeview-2024 | `value_2qb` | 2024-09-05 | 96.8 % | **100.0 %** |
| ffv3-2025 | `value_1qb` (1QB IDP) | 2025-09-04 | 99.3 % | **100.0 %** |
| ffv3-2024 | `value_1qb` | 2024-09-05 | 97.0 % | **100.0 %** |
| ffv3-2023 | `value_1qb` | 2023-09-07 | 98.3 % | **100.0 %** |
| ffv3-2022 | `value_1qb` | 2022-09-08 | 98.3 % | **100.0 %** |

*(roster coverage = share of rostered QB/RB/WR/TE with a value on that dated board; starting-slot coverage = share of the greedily-**selected** starting lineup's skill slots that carry a price)*

**The one disclosure that matters.** An unmatched player is not merely unpriced — he is priced at 0.0, so `select_starting_lineup` will never start him. That is only harmful if an unmatched player was actually good. Ranking each board's unmatched rows by value:

| Season | best-ranked unmatched player | DP rank | value |
|---|---|---|---|
| 2022 | **Ken Walker III** (RB) | **61 / 553** | 2434 |
| 2023 | Malik Cunningham (QB) | 453 / 576 | 2 |
| 2024 | Drew Ogletree (TE) | 463 / 534 | 2 |
| 2025 | Drew Ogletree (TE) | 504 / 546 | 2 |

Three of four boards drop nothing above rank 450 — irrelevant. **The 2022 board drops one genuinely rostered, genuinely valuable player** (DP wrote "Ken Walker III"; Sleeper has "Kenneth Walker", and no suffix rule bridges "Ken" → "Kenneth"). Starting-slot coverage for `ffv3-2022` is still 100 %, so no starting slot went unpriced, but a FLEX slot in that league-season may have been filled by the wrong player. Treat `ffv3-2022`'s preseason numbers as marginally the least trustworthy of the six.

The one-line fix — adding `"ken walker iii": "kenneth walker"` to `DP_TO_SLEEPER_NAME` — was **deliberately not made here**, because that table is on the *shipped* Elo-seed join and this branch ships no behaviour change.

### 2.4 Tests

`backend/tests/test_dp_values_history.py` — 15 tests: commit resolution (`until=`/`path=` query shape, empty-result `LookupError`), raw-URL sha pinning, `slim_csv` column/row filtering, all three join tiers plus position-strictness, scoring-column selection, the offline path with an opener that **raises on any network call**, refusal-not-substitution for an uncaptured date, index integrity, the no-look-ahead invariant, four-distinct-boards, and a loose unmatched-rate regression bar (< 12 %) that catches crosswalk rot without failing on drift.

---

## 3. Backtesting the preseason `roster_value` source

### 3.1 What is rewound

The calibration harness rewinds standings but explicitly **not rosters** — its own docstring says *"Team `player_ids` are NOT rewound … which is exactly why this backtest only scores the `trailing_scores` source."* Harmless there (trailing scores never read a roster), fatal here (roster value reads nothing else). So this backtest rewinds all three inputs:

| Input | How |
|---|---|
| standings | `backtest.as_of(full, 0)` — 0-0-0, no weekly scores, `completed_weeks = 0`. |
| **rosters** | each team's **actual week-1 roster** from Sleeper `/matchups/1`, which serves the complete roster (starters + bench) for that exact week. |
| **values** | the DP board as of kickoff day (§2.2). |

Nothing the simulator then reads postdates kickoff except the remaining-week pairing schedule, which Sleeper publishes in full before week 1 (calibration report BUG-2) and which is worth ~5 % of playoff Brier either way.

The shipped resolver is used unchanged: `source_override="auto"` at `completed_weeks == 0` resolves to `roster_value`, and the run asserts it did. `n_sims = 10,000`, the shipped default, seeded.

### 3.2 Baselines and references

**Only B1 climatology is a baseline.** The calibration report's B2/B3 standings extrapolations are *degenerate at week 0* — every team is 0-0-0 with 0 points-for, so they reduce to "the first `playoff_slots` roster ids", an arbitrary ordering. Reporting them as beaten would be dishonest. Two *references* are reported instead:

- **R-wk3** — the already-validated week-3 `trailing_scores` model on the same league-seasons. This is the real decision: the alternative to showing preseason odds is showing nothing until week 3.
- **R-today** — the identical preseason pipeline priced with **today's** (2026-08-09) board. Not a legitimate predictor; it exists to size the hindsight bias the three prior documents feared.

### 3.3 Headline — n = 72 team-seasons

| predictor | playoff Brier | skill vs climatology | title Brier | skill vs climatology |
|---|---|---|---|---|
| **preseason `roster_value`, period-correct board** | **0.1959** | **+21.6 %** | **0.0740** | **+3.1 %** |
| B1 climatology | 0.2500 | — | 0.0764 | — |
| R-wk3 `trailing_scores` (reference) | 0.1972 | +21.1 % | 0.0953 | −24.8 % |
| R-today, 2026 board (hindsight control) | 0.2073 | +17.1 % | 0.0800 | −4.7 % |

Log-loss: playoff 0.5768, title 0.2549.

**Cluster bootstrap over the 6 league-seasons, 90 % interval** (same resampling unit and same "read it as wide, not precise" caveat as the parent report):

| Quantity | Point | 90 % CI | Reading |
|---|---|---|---|
| Preseason **playoff** skill vs climatology | **+21.6 %** | **[+4.1 %, +38.3 %]** | **excludes 0 — real, but weak** |
| Preseason **title** skill vs climatology | +3.1 % | **[−17.7 %, +24.9 %]** | **includes 0 — no demonstrated skill** |
| Preseason − week-3, playoff Brier delta | −0.0013 | [−0.0573, +0.0470] | **indistinguishable** |
| Preseason − week-3, title Brier delta | −0.0213 | [−0.0416, +0.0087] | indistinguishable |
| Period-correct − today's board, playoff | −0.0114 | [−0.0693, +0.0403] | indistinguishable |
| Period-correct − today's board, title | −0.0060 | [−0.0237, +0.0092] | indistinguishable |

Three things in that table are worth stating out loud.

1. **The preseason source is statistically indistinguishable from the already-approved week-3 source on playoff Brier** (0.1959 vs 0.1972). The calibration report's standing recommendation to gate the surface at `completed_weeks >= 3` therefore **does not buy accuracy at week 3** — its value is entirely in weeks 6/9/12, where the in-season engine pulls away (0.073, 0.055).
2. **Preseason title odds fail the same way week-3 title odds did**, and by a similar margin. The parent report's P5/P6 findings extend backwards to week 0 unchanged.
3. **The hindsight fear was directionally wrong.** Using today's board on a 2022 roster made the prediction *worse* (0.2073 vs 0.1959), not better. A stale board is simply a bad board; it does not smuggle in a free win. The delta's CI includes 0, so this is a null, not a demonstrated penalty — but it means the three prior documents' methodological caution, while correct in principle, was protecting against an effect this sample cannot detect.

### 3.4 Calibration — the finding that governs the ship decision

**Preseason playoff odds:**

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 11 | 0.040 | 0.182 | **+0.142** |
| 0.1–0.2 | 6 | 0.116 | 0.000 | −0.116 |
| 0.2–0.3 | 3 | 0.238 | 0.333 | +0.095 |
| 0.3–0.4 | 7 | 0.368 | 0.571 | +0.204 |
| 0.4–0.5 | 8 | 0.442 | 0.375 | −0.067 |
| 0.5–0.6 | 8 | 0.548 | 0.625 | +0.077 |
| 0.6–0.7 | 7 | 0.644 | 0.571 | −0.073 |
| 0.7–0.8 | 4 | 0.778 | 0.750 | −0.028 |
| 0.8–0.9 | 10 | 0.844 | 0.800 | −0.044 |
| 0.9–1.0 | 8 | 0.949 | 0.750 | **−0.199** |

This is the opposite shape from the in-season engine's. The calibration report found the two large buckets slightly **under**-confident — "the safe direction". Preseason is **over**-confident at both ends: a team told **95 %** makes the playoffs **75 %** of the time (n = 8), and a team told **4 %** makes them **18 %** of the time (n = 11). No bucket holds more than 11 observations, so no individual gap is strong evidence — but the *sign pattern at both extremes simultaneously* is the expected consequence of a preseason model that knows only roster value: it has no way to represent "we do not yet know how good this team is".

**Preseason title odds:** 50 of 72 predictions fall in the 0.0–0.1 bucket (0.024 predicted, 0.040 realized). Above 0.3 there are **4 observations, 0 champions**. Nothing above 0.3 supports an inference.

### 3.5 Ordering, per-league detail, and where it breaks

| league-season | Spearman(mu, actual wins) | playoff-field overlap | preseason playoff Brier | wk-3 playoff Brier | median match |
|---|---|---|---|---|---|
| lakeview-2025 | +0.555 | 4/6 | 0.1806 | 0.0948 | yes |
| lakeview-2024 | +0.441 | 3/6 | **0.2789** | 0.3030 | yes |
| ffv3-2025 | +0.637 | 4/6 | 0.1528 | 0.3088 | no |
| ffv3-2024 | **+0.022** | 4/6 | **0.2812** | 0.2860 | no |
| ffv3-2023 | +0.544 | 5/6 | 0.1372 | 0.0889 | no |
| ffv3-2022 | +0.761 | 5/6 | 0.1446 | 0.1016 | no |
| **pooled** | — | **25/36 (69 %)** | 0.1959 | 0.1972 | — |

**Preseason playoff Brier beats climatology in 4 of 6 league-seasons.** The two failures are large (0.2789 and 0.2812 against 0.2500), and one of them — `ffv3-2024` — has a preseason ordering correlation of **+0.022**, i.e. that season's preseason board carried essentially zero information about who would win games. The in-season engine had no comparable failure past week 3.

Shrinking toward climatology (`p' = λp + (1−λ)·clim`) is the standard fix for the over-confidence in §3.4. **In-sample only, not a tuned parameter:**

| λ | playoff Brier | title Brier |
|---|---|---|
| 1.00 (as shipped) | 0.1959 | 0.0740 |
| 0.90 | 0.1927 | 0.0731 |
| **0.75** | **0.1915** | **0.0723** |
| 0.50 | 0.1990 | 0.0721 |
| 0.00 (climatology) | 0.2500 | 0.0764 |

The best in-sample shrink buys **2.2 % of Brier**. That is small, it is fit on the same 6 seasons it is scored on, and it is not a recommendation — it is reported so the operator can see that *tuning does not rescue this number*. The over-confidence is real but the model is not so miscalibrated that a scalar fixes it.

---

## 4. Ship / no-ship on rendering preseason odds

The bar below mirrors the calibration report's, applied to as-of week 0.

| # | Criterion | Bar | Measured | Result |
|---|---|---|---|---|
| PS1 | Preseason playoff odds beat climatology | skill > 0, bootstrap CI excludes 0 | +21.6 %, CI [+4.1, +38.3] | **PASS** |
| PS2 | …by a margin comparable to the in-season engine | > +40 % (in-season was +55.5 %) | +21.6 % | **FAIL** |
| PS3 | Beats climatology in most league-seasons | ≥ 5 / 6 | **4 / 6** | **FAIL** |
| PS4 | Calibration sane in populated buckets | \|gap\| < 0.10 where n ≥ 8 | −0.199 at 0.9–1.0 (n = 8); +0.204 at 0.3–0.4 (n = 7) | **FAIL** |
| PS5 | Not worse than the source it would be replaced by | Brier ≤ week-3 model | 0.1959 vs 0.1972 | **PASS** |
| PS6 | Preseason title odds beat climatology | skill > 0, CI excludes 0 | +3.1 %, CI [−17.7, +24.9] | **FAIL** |
| PS7 | Board coverage sufficient to trust the input | starting-slot coverage > 95 % | **100 %** on all six | **PASS** |
| PS8 | No severe unfixed correctness bug on a real operator league | zero | **BUG-1** still unfixed (see §5) | **FAIL** |

### Recommendation to the operator

**Preseason title / championship odds: DO NOT RENDER.** No demonstrated skill at week 0, exactly as at week 3. Four observations above a 0.3 predicted probability, zero of them champions. This is the same verdict the calibration report reached, now extended backwards through the whole season. It is a clean, defensible no.

**Preseason playoff odds: CONDITIONAL GO — but not as a precise percentage.** The number is not noise: it has statistically significant skill, its lower confidence bound is above zero, it orders teams sensibly in 5 of 6 seasons, and it is *as accurate as the week-3 model the operator has already been advised to ship*. But three findings say it must not be rendered as a bold "95 %":

1. The lower CI bound is **+4.1 %** — at the pessimistic end of a 6-cluster bootstrap it is barely better than a constant 50 %.
2. It is **over-confident at exactly the values a user reads as certainty**: 95 % → 75 % realized, 4 % → 18 % realized.
3. It **loses to climatology outright in 2 of 6 league-seasons**, one of them with near-zero ordering information.

Concretely, if the operator lights the preseason surface:
- render **playoff odds only**, title odds withheld;
- present the number at a granularity the evidence supports — **banded** ("likely / toss-up / unlikely"), or rounded to 5 % — rather than as a two-significant-figure probability. The model can distinguish the top of the league from the bottom; it cannot distinguish 95 % from 75 %;
- keep the existing **"Projected · beta"** preseason label (the serializer already emits it — the calibration/productionization wave verified both sides);
- **fix BUG-1 first** for median-match leagues (§5), on the same non-negotiable terms the parent report set.

**And one correction to the standing plan.** The calibration report recommended gating the surface at `completed_weeks >= 3` on the grounds that `trailing_scores` — "the source that was actually validated" — takes over there. That reasoning no longer holds at week 3 specifically: the preseason source is *statistically indistinguishable* from the week-3 model, so the gate buys no measured accuracy at the moment it fires. If the operator wants a `completed_weeks` gate, the honest justification is **weeks 6+**, where the in-season engine genuinely pulls away (0.073 at week 9, 0.055 at week 12) — not week 3.

---

## 5. How BUG-1 interacts with these measurements

BUG-1 (`league_average_match` / median scoring ignored, G-024, still unfixed) has two halves, and the preseason backtest separates them cleanly for the first time.

**The ingestion half is inert at week 0.** `SleeperLeagueState.load()` copies `wins/losses/ties` off `/rosters`; at as-of week 0 those are all zero, so there is nothing for the median game to double. **This backtest is the one measurement in the whole #169 program that BUG-1 cannot contaminate on the input side** — the parent report had to caveat its headline numbers as "Phases 2–5 fed with clean, correctly-rewound standings"; here the state is genuinely zero, not rewound around a bug.

**The simulation half is live and does affect these numbers.** `simulate()` awards exactly one win per remaining week and never scores the median game. For Lakeview 2024/2025 that means the simulator generates a 14-decision H2H season while the real seasons were decided over **28 decisions**. A median game compares a team to the league median as well as to one opponent, which *reduces* the luck in a season — so real median-league outcomes are less random than the simulator assumes, and the model should be systematically mis-shaped there. Measured:

| Split | n | preseason playoff Brier | climatology | week-3 model |
|---|---|---|---|---|
| median-match leagues (Lakeview 2024/2025) | 24 | **0.2298** | 0.2500 | 0.1989 |
| H2H-only leagues (FFv3 2022–2025) | 48 | **0.1789** | 0.2500 | 0.1963 |

The preseason source is **much weaker on the median-match league** — barely better than climatology (0.2298 vs 0.2500) versus a clear win on the H2H leagues (0.1789). Two league-seasons cannot prove the median game is the cause, and the confound is total (the median leagues are also the only superflex/TEP leagues, whose talent spread is ~35 % wider per the parent report §8). But the direction is what an unmodelled second decision per week predicts, and it lands on **the operator's own live league**.

Third, unchanged from the parent report: `projected_wins` for a median league still renders on a nonsense scale — 14 from the H2H simulation against a record the league will report out of 28. That is user-visible the moment the surface lights, preseason included.

**Conclusion for the ship decision:** the preseason recommendation in §4 is conditional on BUG-1 exactly as the in-season one is, and the median-league split is an additional reason to fix it before any surface lights.

---

## 6. Hypothesis 1b, re-tested with period-correct values

`hypothesis-pick-capital-2026-08-09.md` could not price rosters in dynasty-value terms and substituted own-season points-per-game, disclosing this as a deviation blocked on "the same historical-value-board gap". That gap is closed, so sub-test (i) — *does pick capital predict a roster getting weaker during the season?* — is re-run three ways on the identical rosters:

| variant | pricing |
|---|---|
| **V0** | own-season points-per-game, fixed price list — **the published method, rerun verbatim as a control** |
| **V1** | week-1 roster @ the kickoff board, week-14 roster @ the week-14 board — **headline**; each roster priced by the market that existed when it was held |
| **V2** | **both** rosters @ the kickoff board — isolates roster construction from market movement (the dynasty-value analogue of V0's fixed list) |

Board unmatched rates for the week-14 boards: 1.5 % (2022), 1.7 % (2023), 0.4 % (2024), 0.0 % (2025).

### 6.1 Sub-test (i) — capital vs Δ starting-lineup value

| pricing | capital measure | Pearson r | Spearman ρ | 90 % CI (cluster bootstrap) | reading |
|---|---|---|---|---|---|
| V0 own-season PPG (published) | raw count | −0.113 | +0.012 | [−0.240, −0.001] | excludes 0, grazes it |
| V0 own-season PPG (published) | value-weighted | −0.108 | −0.004 | [−0.237, −0.036] | excludes 0, weak |
| **V1 contemporaneous boards** | raw count | **+0.076** | +0.167 | **[−0.085, +0.260]** | **includes 0** |
| **V1 contemporaneous boards** | value-weighted | **+0.074** | +0.168 | **[−0.061, +0.224]** | **includes 0** |
| V2 kickoff board, both ends | raw count | +0.065 | +0.096 | [−0.110, +0.280] | includes 0 |
| V2 kickoff board, both ends | value-weighted | +0.085 | +0.098 | [−0.118, +0.301] | includes 0 |

**The sign flips and the significance evaporates.** V0's weak negative (1b's predicted direction, CI barely excluding zero) becomes a weak *positive* with a CI comfortably spanning zero — and it does so under both dated variants, so this is not an artefact of mixing roster change with market movement.

### 6.2 The confound check gets stronger

| pricing | capital measure | Pearson r vs week-1 lineup strength | 90 % CI |
|---|---|---|---|
| V0 (published) | raw count | −0.278 | [−0.486, −0.070] |
| V0 (published) | value-weighted | −0.349 | [−0.528, −0.173] |
| **V1/V2 (dated boards)** | raw count | **−0.411** | [−0.610, −0.219] |
| **V1/V2 (dated boards)** | value-weighted | **−0.415** | [−0.592, −0.251] |

Priced in dynasty value rather than points, the self-selection the published report flagged is **larger, not smaller**: teams entering a season with more future picks already hold materially weaker starting lineups before a game is played.

### 6.3 Tercile means

| tercile | n | mean capital | mean Δ V0 (PPG) | mean Δ V1 (dated) | mean Δ V2 (kickoff board) | mean win residual | playoff rate |
|---|---|---|---|---|---|---|---|
| low | 24 | 5,697.5 | +3.83 | −561 | −82 | +0.89 | 62 % |
| mid | 24 | 7,771.1 | −1.23 | −2,514 | −1,348 | −0.13 | 46 % |
| high | 24 | 10,244.3 | +2.85 | **+1,132** | **+523** | −0.76 | 42 % |

Non-monotonic, like V0's. But the sign on the high tercile is the interesting part: **the most pick-rich teams' rosters gained dynasty value during the season while under-performing on wins.**

### 6.4 What did NOT change — and why that matters

Everything in the published report that never depended on a value board is **bit-identical**:

| Result | Published | Re-run |
|---|---|---|
| (ii) win outperformance, raw count | r = −0.254, ρ = −0.172, CI [−0.403, −0.139] | **identical** |
| (ii) win outperformance, value-weighted | r = −0.197, ρ = −0.159, CI [−0.394, −0.024] | **identical** |
| (iii) playoff berth, raw count | r = −0.210, mean 11.5 vs 12.5 | **identical** |
| (iii) playoff berth, value-weighted | r = −0.251, mean 7,265 vs 8,543 | **identical** |
| §6.2 buy:sell by capital tercile | 2.4 : 1 → 0.7 : 1 → 0.6 : 1 | **identical** |

This was predicted in the brief and it holds exactly: the strongest evidence for 1b — the behavioural buy/sell gradient — never touched a value board and is untouched by the correction.

### 6.5 Re-verdict — WEAKENED

**The correction weakens 1b. It does not overturn it, and it does not rehabilitate 1a.**

| Sub-test | Published verdict | Re-verdict |
|---|---|---|
| (i) Δ roster strength | "weak/noisy, CI grazes 0" — counted as *partial* 1b support | **Clean null, point estimate mildly the WRONG sign for 1b** |
| (ii) win outperformance | moderate, CI excludes 0 | unchanged |
| (iii) playoff berth | consistent negative | unchanged |
| §6.2 trade mechanism | clean, monotonic, predicted direction | unchanged |

The published headline — *"real signal on 3 of 4 sub-tests, weakest on the roster-value delta specifically"* — should now read **"real signal on 2 of 4 outcome sub-tests plus the behavioural mechanism; NO signal on roster composition."** 1b's status drops from **"weakly-to-moderately supported"** to **"supported on outcomes and behaviour; its stated roster-composition mechanism is not observed in dynasty-value terms."**

**A refinement worth recording, because it changes what a future re-test should do.** §6.3 shows high-capital rosters *gaining* dynasty value while losing games relative to form. That is exactly what a competent rebuild looks like: trade present production for future value. So **Δ dynasty value is a structurally poor instrument for 1b** — a successful "sheds producers" rebuild moves it the *opposite* way from 1b's framing, because what is shed is present output and what is acquired is value. The published report treated the missing dated board as the reason sub-test (i) was weak; the real reason is that the metric measures the wrong thing. **Recommend retiring sub-test (i) rather than re-running it on more seasons** — the published report's own "revisit if/when a historical, dated dynasty-value board exists" prerequisite is now satisfied and answered, and the answer is that this particular test cannot separate the hypotheses.

**Recommendation unchanged, and better supported: do not spec a pick-capital adjustment term.** The only remaining candidate home for one was `RosterValueStrength`, and §3 shows that source is itself weak and over-confident — an adjustment fitted on 72 team-seasons stacked onto a marginal preseason source is exactly the "double unvalidated-on-unvalidated" the published report warned about.

---

## 7. What this evidence does not support

- **The sample is smaller than the parent report's, not larger.** One prediction per team-season, so **72 playoff predictions, 6 champion events, 6 clusters** — versus 288 team-week predictions in the parent report. Every CI here is a 6-cluster bootstrap; read them as wide.
- **Two leagues, two formats, one shape.** All six league-seasons are 12-team, 6-slot, 14-week dynasty leagues. Nothing here says anything about 8-team, 10-team, divisional, or non-dynasty leagues, and §5 shows the two formats behave quite differently.
- **No claim about preseason title odds beyond "not demonstrated".** Six champion events. A model emitting 1/12 for everyone would be indistinguishable.
- **No per-bucket calibration claim.** The largest preseason playoff bucket holds 11 observations. The −0.199 gap at 0.9–1.0 is 2 teams out of 8.
- **The shrinkage table is in-sample.** λ was scored on the same six seasons. It is a diagnostic, not a fitted parameter, and must not be shipped as one.
- **R-today is a crude hindsight control.** A 2026 board has no entry for players who retired before 2026 and prices 2023–2025 rookies who could not have been on a 2022 roster. It bounds the direction of the bias, not its magnitude.
- **The 2022 board drops Ken Walker III** (§2.3). `ffv3-2022` is the least trustworthy of the six league-seasons for that reason.
- **BUG-1's simulation half is inside every number in §3**, for the two Lakeview seasons. The split in §5 is a signal, not a controlled measurement.
- **Nothing here validates the in-season `roster_value` path**, because `auto` never selects it in-season. Weeks 3/6/9/12 boards were captured anyway, so a future analysis can.

---

## 8. Corrections issued to the three prior documents

Dated inline correction notes were added on 2026-08-09 to:

| Document | Correction |
|---|---|
| [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md) | §1 row for `RosterValueStrength` ("NOT backtestable"), §4's "any claim about the preseason `roster_value` source at all", §8's "without a historical value board the correlation cannot be measured", and §9's P9 **FAIL — untestable**. All four now carry a pointer here. |
| [`hypothesis-pick-capital-2026-08-09.md`](hypothesis-pick-capital-2026-08-09.md) | §2.2's "there is no historical, dated dynasty-value board", §7's "revisit if/when a historical, dated dynasty-value board exists", and §8's honesty note about the deviation. The 1b verdict is annotated as superseded by §6 here. |
| [`phase-2-plan.md`](phase-2-plan.md) | The prerequisite line ("no dated historical dynasty-value board exists … Building/finding one is the prerequisite") is corrected — the prerequisite is met, and the 1b verdict row is annotated. |

The corrections are **inline annotations, not rewrites**: the original text stays so the reasoning trail is intact, and each is marked with the date and a link here. `docs/integrations/dynastyprocess.md` gains the `values-players.csv` **history** as a documented fetch surface.

---

## 9. Reproducing this report

```bash
# Task 1 — refresh/extend the dated-board fixtures (NETWORK; already run)
python3 scripts/dp_values_history_capture.py --dry-run     # resolve only
python3 scripts/dp_values_history_capture.py

# Task 2 — preseason roster_value backtest (offline, ~12 min at 10k sims)
python3 scripts/outlook_preseason_backtest.py --sims 10000

# Task 3 — hypothesis 1b with period-correct values (offline)
python3 scripts/outlook_pick_capital_dated_values.py

# Permanent tests
python3 -m pytest backend/tests/test_dp_values_history.py \
                  backend/tests/test_outlook_preseason_source.py -q
```

| Artefact | Path |
|---|---|
| Dated-board module | `backend/dp_values_history.py` |
| Committed dated boards (24 snapshots + index) | `backend/tests/fixtures/dp-values-history/` |
| Capture script (network, run once) | `scripts/dp_values_history_capture.py` |
| Preseason backtest | `scripts/outlook_preseason_backtest.py` |
| Per-team preseason records (committed, drives the fast tests) | `backend/tests/fixtures/outlook-hypotheses/preseason-backtest-records.json` |
| 1b re-test | `scripts/outlook_pick_capital_dated_values.py` |
| Tests | `backend/tests/test_dp_values_history.py`, `backend/tests/test_outlook_preseason_source.py` |
| Reused unmodified | `scripts/outlook_calibration_backtest.py` (fixtures, `as_of`, `truth`, Brier/calibration), `scripts/outlook_pick_capital_hypothesis.py` (pick replay, mechanism tags, bootstrap), `backend/outlook/*` (entire pipeline), `backend/espn_service.py` (crosswalk), `backend/data_loader.py` (name normalisation) |
| Parent reports | [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md), [`hypothesis-pick-capital-2026-08-09.md`](hypothesis-pick-capital-2026-08-09.md), [`phase-2-plan.md`](phase-2-plan.md) |

Test posture: backend suite **2194 passed / 1 skipped / 1 xfailed** before this work (fresh `origin/main` at `ea19d4b`) → **2217 passed / 1 skipped / 1 xfailed** after, exit 0. No mobile changes. `config/features.json` untouched; `outlook.odds` remains dark.
