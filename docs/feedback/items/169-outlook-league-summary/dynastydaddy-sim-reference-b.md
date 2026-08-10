# DynastyDaddy simulator — source-level method reference (lens B)

**Purpose:** independent source-code dive into how DynastyDaddy computes playoff/championship odds and team strength, as a method reference for `backend/outlook/` (FB #169). Second, independent lens — written without reading any parallel agent's output. Every claim below is cited to a specific file/line in a specific repo/commit; anything not directly verified in source is marked **[unverified]**.
**Author:** research task, 2026-08-09.

---

## 0. Which repo is actually canonical — this matters a lot

Our own prior research doc (`docs/feedback/items/169-outlook-league-summary/projection-source-research.md`) cites `G-Sher/dynasty-daddy` as *the* DynastyDaddy repo, sourced from the README/site copy. That citation is **stale and materially misleading** for a source-code dive:

- **`G-Sher/dynasty-daddy`** — last pushed **2021-09-10** (commit `32dce516`), 4 stars, **no LICENSE file** (GitHub API `license: null`). Its own README lists *"Team Elo ranking like Chess"* under **Future Improvements** — i.e. **this snapshot never implemented Elo at all.** Verified via `GET /repos/G-Sher/dynasty-daddy` and `GET /repos/G-Sher/dynasty-daddy/commits`.
- **`Leondoff/dynasty-daddy`** — a separate, non-fork repo (`fork: false`), last pushed **2024-02-22**, **MIT-licensed**, README opens with *"This project is currently in Beta and is deployed to https://dynasty-daddy.com"* and lists the full current feature set (5 platforms, Elo-adjusted forecast, median-win leagues, mock draft, etc.) that matches the live site. Both READMEs credit the same person, **Jeremy Timperio**, as creator. This is the repo that actually contains the Elo/simulator code our internal doc described from the marketing site.

**I treated `Leondoff/dynasty-daddy` @ `main` as canonical for all findings below** — it is the only public repo whose contents match the live product's described behavior. The `G-Sher` snapshot is cited separately in §5 (license) because it's the repo our own prior doc pointed at, and its licensing posture is different and worse.

I could not find an official announcement explaining the two-account split **[unverified]** — flagging this so it can be corroborated (or refuted) against the other lens's findings.

---

## 1. Team strength

**There is no single "historical Elo" model — there are two selectable forecast models, and Elo is the non-default, Beta one.**

`front-end/fantasy-app/src/app/components/services/playoff-calculator.service.ts:47-48`:
```ts
forecastModel: ForecastTypes = ForecastTypes.ADP_STARTER;
```
`playoff-calculator.service.ts:1055-1058`:
```ts
enum ForecastTypes {
  ADP_STARTER = 0,
  ELO_ADJUSTED = 1,
}
```
Confirmed in the UI copy itself, `front-end/fantasy-app/src/app/components/playoff-calculator/playoff-calculator.component.html:15-16`: the ADP model is labeled *"Show our traditional starters by ADP forecast"* (default); the Elo model is labeled *"Show our elo adjusted starters by ADP forecast"* with an explicit **`Beta`** badge next to it.

**Model A — `ADP_STARTER` (default, always available, no games required):**
- `power-rankings.service.ts:296-377` (`calculateADPValue`): for each team, fill starting-lineup slots (QB/RB/WR/TE/FLEX/SUPERFLEX) greedily by each player's **average draft position** (`selectedRankings`, default `'avg_adp'` — a market ADP field, not KTC dynasty trade value), sum the slot values, then invert/rescale: `adpValueStarter = (worstTeamStarterValue * 2) - team.adpValueStarter + 500` (`power-rankings.service.ts:372-375`) so higher = better. This is a **static, preseason-computable, per-league-relative rating** — it needs zero game results and is what powers the odds surface before Week 1.
- This rating **never updates from this league's own results** in ADP_STARTER mode — it's fixed for the season (modulo the underlying ADP data source refreshing globally).

**Model B — `ELO_ADJUSTED` (opt-in, Beta):**
- Initialized from the *same* `adpValueStarter` as day-0 rating (`power-rankings.service.ts:374`, `399`), then updated **per completed real matchup** using textbook logistic Elo:
  - `stat.service.ts:16-20` — `eloProbability(r1, r2) = 1 / (1 + 10^((r1-r2)/400))` (standard 400-point Elo scale).
  - `stat.service.ts:22-37` (`eloRating`) — standard win/loss update: `newRating = rating + K * (actual - expected)`.
  - **K-factor is dynamic, not fixed**: `power-rankings.service.ts:436` — `kValue = clamp(round(abs(team1Points - team2Points)), 10, 40)`, i.e. **K = that week's margin of victory in fantasy points, floored at 10 and capped at 40.** Blowouts move rating more than close games.
  - Update loop: `power-rankings.service.ts:429-462` (`initializeEloADPValueStarterHistory`) walks every completed week of `matchupService.leagueMatchUpUI`, applies the Elo update per matchup, and pushes into a cached `eloADPValueStarterHistory[]` array (one entry per week) so it's computed once and memoized (`calculateEloAdjustedADPValue`, `power-rankings.service.ts:392-420`).
  - Bye weeks (playoff byes, or weeks with no matchup) carry the rating forward unchanged (`power-rankings.service.ts:454-460`).

**Preseason / no-games behavior:** `power-rankings.service.ts:396-403` — if `endWeek <= startWeek - 1` (no completed weeks), `eloAdpValueStarter` is just set equal to `adpValueStarter` with `eloAdpValueChange = 0`. So in the Elo model too, week-0 team strength **is** the ADP-based starting-lineup rating — Elo only starts diverging from it once real results exist. There is no roster/KTC-value blending step distinct from this ADP-derived seed; **no dynasty trade value (KTC) is used anywhere in the playoff-calculator's rating pipeline** — that surprised me, since KTC trade value is DynastyDaddy's headline data source for *other* pages (power rankings' `tradeValueOverall`/`sfTradeValueOverall`), but the playoff-odds rating specifically uses **ADP**, a separate field (`power-rankings.service.ts:308-363`, `sortPlayersByADP` sorts by `selectedRankings`, not by `trade_value`).

---

## 2. Weekly score model

**DynastyDaddy never simulates a point score. It simulates win/loss coin flips from a fixed win probability, and that's it — no Normal(μ,σ) draw, no score distribution, no schedule-luck/home-away concept.**

- Team rating → win probability is **not** the Elo logistic formula. It's a two-step transform done once per `calculateGamesWithProbability()` call (not re-derived per simulation trial):
  1. z-score the chosen rating (`adpValueStarter` or `eloAdpValueStarter`) against the **whole league's mean and stdev of that same rating** — `playoff-calculator.service.ts:63-69` (uses `simple-statistics`' `mean`/`standardDeviation`/`zScore`).
  2. Convert to a **cumulative standard-normal probability** — `playoff-calculator.service.ts:74-75` (`cumulativeStdNormalProbability(teamZ)`), stored per roster ID in `teamRatingsPValues`.
  3. Per matchup, win probability is a **linear average of each team's independent percentile**, not the pairwise Elo formula: `playoff-calculator.service.ts:135-137` — `team1Prob = 0.5 + (P(team1) - P(team2)) / 2`. This is mathematically distinct from Elo's `1/(1+10^(-Δ/400))` — it's bounded but not derived from the rating *difference* directly, it's derived from each team's standing in the *league-wide distribution*. (Only the Elo-rating **update** step, §1, uses the real Elo formula; the win-probability-for-simulation step does not.)
- Each simulated regular-season game is then a **single Bernoulli draw**: `playoff-calculator.service.ts:399,418` — `getRandomInt(100) < team1WinsOdds` (an unseeded `Math.random()`-based `getRandomInt`, `playoff-calculator.service.ts:950-952`). No score is drawn or stored — the simulator produces **win counts only**, never simulated point totals.
- **No home/away.** No explicit "schedule luck" adjustment beyond whatever the real remaining-schedule pairings impose. No median-game/robust-mean handling in the statistical sense — but there **is** a first-class **median-scoring-league** feature (a league format where each week you also get a win/loss against the league median): `playoff-calculator.service.ts:167-226` (`totalMedianWins`), `968-980` (`getMedianPointsForWeek` — computes the actual median of that week's real point totals, not a simulated one), `988-1026` (`generateMedianProbabilities` — builds a synthetic win probability against "the median team" the same z-score/CDF way, ranking teams by rating and taking the two middle teams). This is a real, config-flag-gated (`leagueService.selectedLeague.medianWins`) simulation feature, not the "central tendency" concept our internal doc's Monte-Carlo write-up implied.

**Contrast with our engine:** `backend/outlook/simulator.py:92-104` draws `gauss(mu[a], sig[a])` and `gauss(mu[b], sig[b])` **independently per team per game, every simulation trial**, and compares the drawn scores — score margin decides the winner *and* accumulates into `points_for`, which then feeds the tiebreak (`playoff_format.py` sorts by `(-wins, -points_for, roster_id)`). DynastyDaddy's tiebreak for **simulated** (not-yet-played) ties instead re-runs the same rating-based coin flip: `playoff-calculator.service.ts:883-890` (`calculateTieBreaker`) — there is no simulated point total to break ties with, because none was ever generated.

---

## 3. Sim mechanics

- **N = 10,000**, hard-coded default: `playoff-calculator.service.ts:45` (`NUMBER_OF_SIMULATIONS = 10000`), confirmed to the user in copy: `playoff-calculator.component.html:89` — *"Our forecast uses 10,000 simulations of the season and updates after every week."* (A secondary "mock trade impact" preview path uses only 1,000 sims — `playoff-calculator.service.ts:109` — presumably for interactive-latency reasons on the trade-what-if UI.)
- **Not seeded / not deterministic.** `getRandomInt` (`playoff-calculator.service.ts:950-952`) calls plain `Math.random()`. Re-running the same league's odds twice will not reproduce identical results. No stable/process-independent seed of any kind — contrast with our repo's explicit determinism rule (`backend/outlook/simulator.py:7-14`, SHA-256-derived `stable_hash(league_id) ^ config_seed`).
- **Regular season**: `simulateRegularSeason` (`playoff-calculator.service.ts:387-449`) walks each remaining week's real scheduled matchups (from `matchUpsWithProb`, which mirrors the platform's actual schedule — no synthetic/random-pairing fallback logic was found, unlike our `_random_pairing` fallback in `simulator.py:145-148`), flips a coin per game per the fixed win probability, and tallies `projWins` per team (double-counted with a synthetic median-win coin flip if the league uses median scoring).
- **Standings / seeding**: division winners get priority seeding and byes when `divisions.length > 1` (`simulateDivisionWinners`, `playoff-calculator.service.ts:456-487`); otherwise the top N teams by simulated win total get byes (`simulateOneSeason`, `playoff-calculator.service.ts:777-853`). Ties in simulated win count are broken by another rating-based coin flip (`calculateTieBreaker`), **not** by any points-for metric — because, per §2, no points-for total exists for simulated weeks.
- **Byes**: bye count is a **derived heuristic, not an explicit config value** — `simulateOneSeason`, `playoff-calculator.service.ts:799-800`: `numOfByeWeeks = playoffTeams % 2 === 0 ? playoffTeams % 4 : playoffTeams % 2`. E.g. 6 playoff teams → 2 byes; 8 → 0 byes; 5 or 7 → 1 bye. This is a parity-based guess at bracket shape, not a value read from the platform's actual declared bracket settings — it will silently misjudge any bracket shape whose bye count doesn't follow that formula (e.g. a 10-team single-bye bracket would get `10 % 4 = 2` byes here, which is wrong for that shape). **[my inference — I did not find this heuristic validated against real Sleeper `settings.playoff_teams`/bracket-shape data; flagging as a likely latent bug rather than a deliberate design choice.]**
- **Playoff rounds**: `simulateRoundOfPlayoffs` (`playoff-calculator.service.ts:494-541`) pairs `playoffTeams[i]` vs `playoffTeams[length-1-i]` and pushes winners in that same index order into the next round. Because winners are appended in ascending-`i` order, the **bracket stays fixed/static across rounds** (standard single-elimination pairing, `0v7→a`, `1v6→b`, `2v5→c`, `3v4→d`, then round 2 pairs `a` vs `d`, `b` vs `c`) — it is **not** dynamically reseeded by remaining strength each round the way our `_reseed()` (`backend/outlook/playoff_format.py:79-83,101-103`) explicitly re-sorts survivors by original overall seed every round ("higher seed always plays the lowest surviving seed"). Same underlying model (win prob from rating) is reused for every playoff round — no separate/adjusted model for the postseason.
- **2-game playoff rounds**: supported (`playoffRoundType === 2`, `playoff-calculator.service.ts:497,516-538`) — plays the coin flip twice, ties broken by real season points-to-date (`team.roster.teamMetrics.fpts`) rather than another coin flip, an inconsistency worth noting (regular-season/1-game-round ties use the rating coin flip; 2-game-round ties use real cumulative fpts).

---

## 4. Outputs + presentation

- Six output counters per team, all reported as **rounded whole percentages** (`Math.round(count / (N/100))`, `playoff-calculator.service.ts:927-940`): `timesMakingPlayoffs`, `timesWinningDivision`, `timesWithBye`, `timesMakeConfRd`, `timesMakeChampionship`, `timesWinChampionship`. Plus non-probability aux stats: `timesTeamWonOut` (times a team went undefeated the rest of the way), `timesWithWorstRecord`, `timesWithBestRecord`, and a cached `winsAtStartDate`.
- No confidence intervals, no smoothing beyond integer rounding, no explicit numeric floor/ceiling clamp on the reported percentages that I found.
- **Early-season-uncertainty labeling exists but is about the *model choice*, not the *odds' reliability*.** The only in-product caveat I found is the `Beta` badge on the Elo-adjusted toggle (`playoff-calculator.component.html:16`) and the plain-language explainer block (`playoff-calculator.component.html:89-90`): *"Our forecast uses 10,000 simulations of the season and updates after every week. Our traditional ADP model uses the team's starters based on ADP to determine team rating. Our elo adjusted ADP model takes the traditional ADP model and runs elo head to heads for each week to update the team values as the season progresses. Our forecast currently doesn't take in to consideration bye weeks."* There is **no** explicit "small sample size" or "preseason, treat with caution" warning surfaced anywhere in the strings I fetched — the product ships preseason odds as plainly as in-season odds, just off the ADP-only static model by default. This directly contradicts the assumption in our own prior research doc that DynastyDaddy visibly flags preseason uncertainty; **I found no evidence of that** — it appears to just show numbers.

---

## 5. License check

Two different verdicts depending on which repo you mean — say precisely which one before reusing anything:

| Repo | License file | Verdict |
|---|---|---|
| **`Leondoff/dynasty-daddy`** (canonical/current source, §0) | **MIT License**, verbatim: `"MIT License\n\nCopyright (c) 2022 Jeremy Timperio\n\nPermission is hereby granted, free of charge, to any person obtaining a copy..."` — fetched directly from `LICENSE` at repo root, `main` branch. | Permissive; code reuse with attribution is licensed. |
| **`G-Sher/dynasty-daddy`** (the repo our own prior doc cited, §0) | **No LICENSE file present** — `GET /repos/G-Sher/dynasty-daddy` returns `"license": null`, and the repo root listing has no `LICENSE`/`LICENSE.md` entry. | All-rights-reserved by default; not licensed for reuse. |

Per this session's explicit instructions, **this doesn't authorize copying their code regardless** — MIT would permit it, but the operator still needs to clear it, and in any case the guidance here is to spec ideas in prose, not port code.

---

## 6. Deltas vs our engine (`backend/outlook/`)

Read: `backend/outlook/simulator.py`, `strength.py`, `playoff_format.py`, `league_state.py`, `config.py`, `pipeline.py` @ HEAD of this worktree (branch reset to `origin/main`, commit `ed0c453`).

| Dimension | DynastyDaddy (`Leondoff/dynasty-daddy`) | Our engine (`backend/outlook/`) |
|---|---|---|
| Preseason team-strength source | Starting-lineup **ADP** rank sum, inverted/rescaled (`power-rankings.service.ts:296-377`) | Starting-lineup **dynasty trade value** z-score → points-scale μ, fixed σ (`strength.py` `RosterValueStrength`, `:145-169`) |
| In-season strength update | **Two mutually-exclusive modes**, user-toggled: (a) default static ADP forever, or (b) opt-in Beta classic-Elo state machine seeded by ADP, K = clamp(margin, 10, 40) (`power-rankings.service.ts:392-462`, `stat.service.ts:16-37`) | Continuous, automatic three-way blend by elapsed-week fraction: roster-value → blended → trailing-scores, no user toggle, no Elo anywhere (`strength.py` `resolve_strength_source`, `:261-273`, `BlendedStrength`, `:198-226`) |
| What gets simulated per game | **Nothing scored** — a single Bernoulli win/loss draw from a precomputed, per-week-fixed win probability (`playoff-calculator.service.ts:399,418`) | A **real score draw** `Normal(μ,σ)` per team per game, every trial, margin decides winner (`simulator.py:100-112`) |
| Win-probability formula | Non-Elo: average of each team's independent z-score/normal-CDF percentile vs the league (`playoff-calculator.service.ts:63-75,135-137`) | Implicit — falls out of comparing two independent Gaussian draws (no closed-form win-prob formula needed or computed) |
| Points-for / tiebreak | **No simulated points-for exists**; ties broken by another rating-based coin flip (1-game rounds) or real season-to-date fpts (2-game rounds) — inconsistent between the two (`playoff-calculator.service.ts:883-890` vs `:527-532`) | Points-for is a real byproduct of every simulated game and is the primary tiebreak, consistently, everywhere (`playoff_format.py:65`, `simulator.py:104-105,114`) |
| Playoff bracket reseeding | **Static bracket** — winners keep their round-1 array position, so pairing looks like a fixed tournament tree, not dynamic reseeding (`playoff-calculator.service.ts:494-541`) | **Dynamic reseeding every round** — survivors re-sorted by original overall seed before each round (`playoff_format.py:79-83,101-103`) |
| Bye count | **Derived heuristic** from playoff-field parity (`playoffTeams % 4` or `% 2`) — can misjudge non-standard bracket shapes (§3) | **Explicit config value** (`num_byes` passed into `PlayoffFormat`, `playoff_format.py:40-43`) — no guessing |
| Division-winner seeding | Supported, division winners get seeding priority + first crack at byes (`playoff-calculator.service.ts:456-487`) | Supported, same concept (`playoff_format.py:47-63`, `num_divisions` priority ordering) |
| Median-scoring-league format | **First-class supported** — real median computed per completed week, synthetic median-opponent win-prob for future weeks (`playoff-calculator.service.ts:167-226,968-1026`) | **Not implemented** — no median-format concept anywhere in `outlook/` |
| Determinism | **None** — plain unseeded `Math.random()` (`playoff-calculator.service.ts:950-952`) | **Enforced by design** — SHA-256-derived stable seed, single `random.Random` instance, byte-identical repeat runs (`simulator.py:7-33`) |
| N sims | 10,000 default (1,000 for the interactive trade-preview path) | 10,000 default (`simulator.py:28`), config-overridable (`config.py:33-35`) |
| Remaining-schedule fallback | Uses the real declared schedule only; no fallback path found for missing future pairings | Explicit fallback to a random round-robin pairing when the platform doesn't expose future weeks (`simulator.py:131-148`) |
| Uncertainty labeling to the user | A `Beta` badge on the Elo toggle + one explainer paragraph; **no explicit preseason/small-sample caution string found** | Not yet built (Phase 3/4 scope is simulation math only) — flagged separately in our own `projection-source-research.md` §5 as needing a "projected/beta" label before ship |

---

## Recommendations for our engine, ranked by likely calibration impact

1. **High impact, low risk — add a real season-long Elo strength provider (`SleeperResultsEloStrength` or similar), but keep our score-draw architecture, don't copy their Bernoulli approach.** DynastyDaddy's core insight worth stealing is the *update rule*, not the *simulation mechanic*: seed each team's rating from the same z-scored preseason value we already compute in `RosterValueStrength`, then update it weekly off real result margins with **margin-scaled K** (`clamp(round(|margin|), K_min, K_max)` — their `10..40` bounds are a reasonable starting point, tune against our own backtest harness). Feed the resulting rating into our *existing* μ/σ machinery (affine-map rating → points-scale μ, as we already do for roster value) rather than replacing our Gaussian-score-draw simulator with their coin-flip approach — we get their in-season learning signal without losing points-for-based tiebreaks, which their own inconsistent-tiebreak handling (§3, §6) shows is a real weakness of the no-scores design.
2. **Medium impact, near-zero risk — implement median-scoring-league support if any FTF-connected leagues use it.** This is a completely separate structural feature (each week doubles as a match vs the league median), not a calibration tweak. Worth a quick audit of whether any current FTF leagues have `median_wins`-equivalent settings before investing; if none do, skip.
3. **Medium impact — do NOT adopt their static/non-reseeded bracket.** Confirms our dynamic reseeding (`playoff_format.py`) is the more correct choice; no change needed, just noting it as validated-by-contrast rather than a gap.
4. **Low impact, easy win — treat their bye-count heuristic as a cautionary example, not a model.** Our explicit `num_byes` config value (driven from actual platform bracket settings) is strictly better than DynastyDaddy's `playoffTeams % 4`/`% 2` guess; no action needed beyond confirming our pipeline always populates `num_byes` from real platform data rather than ever falling back to a similar guess.
5. **Low impact, worth a product decision — DynastyDaddy does not appear to gate or caveat preseason odds beyond a `Beta` badge on the alternate model.** Our own prior research doc's Recommendation 5 (gate the odds surface until real scoring data exists, or label preseason numbers "projected/beta") is **not something DynastyDaddy actually does in the way the internal doc implied** — I found no explicit "small sample size" warning in their UI copy. This doesn't mean our caution is wrong, but the "DynastyDaddy already does this" framing (if it exists in the parallel agent's or planning docs) should be corrected — it's inferred from careful reading of the marketing site, not confirmed in the product's actual strings.
6. **Determinism and points-for-first tiebreaks are already correct in our design; both are real weaknesses in DynastyDaddy's implementation (§3 tiebreak inconsistency, §3 non-determinism) worth calling out if this ever comes up as "should we simplify to match a competitor."** Don't simplify away from either.

---

## Notes on confidence / method

- All file/line citations are against `Leondoff/dynasty-daddy` @ `main` as fetched via `raw.githubusercontent.com` and the GitHub REST API on 2026-08-09 (commit not pinned by SHA at fetch time — branch HEAD; re-fetch to confirm if this doc is read much later and lines may have shifted).
- I did not run the DynastyDaddy app locally or inspect network calls against the live site — all findings are from static reading of the front-end TypeScript source. The back-end (`back-end/express-api`) was only checked for the gamelog-scoring pipeline (§1 note) and was not otherwise load-bearing to the playoff-calculator findings, which live entirely in the Angular front-end service layer.
- I did not attempt to independently verify the "same person, two repos" hypothesis (§0) beyond both READMEs' credits line — flagged `[unverified]` and worth reconciling against the parallel lens if it investigated differently.
