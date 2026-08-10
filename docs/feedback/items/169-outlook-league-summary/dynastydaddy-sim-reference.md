# DynastyDaddy simulator — source-level method reference

**Purpose:** a method reference for calibrating FTF's own dark odds engine (`backend/outlook/`, feedback #169). Everything below is read directly from DynastyDaddy's public source (front-end TypeScript — the simulation runs client-side, not on their Node/Express API), with file/line citations. Nothing is copied; this is prose description only, per the operator's standing rule (no code reuse until cleared, regardless of license).
**Author:** research task, 2026-08-09, worktree `worktree-agent-adf883cf6fe9ad0f2`. **[unverified]** marks claims the source doesn't settle.
**Supersedes/corrects:** [projection-source-research.md](projection-source-research.md)'s DynastyDaddy section — see "Corrections to the parent research doc" below. The parent doc's characterization ("10,000-season Monte Carlo off schedule, historical Elo score, and starting line-up, no projections feed") is directionally right but the mechanism is materially different from a standard points-based Monte Carlo, and the "starting line-up value" is **not** the KTC dynasty value the rest of the app uses.

---

## 0. Which repo, and why

The research doc cited `G-Sher/dynasty-daddy`. That repo is real but is a **stale September 2021 snapshot** (Angular 11, no `back-end/database`), last pushed 2021-09-10, and carries **no LICENSE file**. The live app's own README credits creator **Jeremy Timperio** and links badges to `github.com/jmtimper/dynasty-daddy` — but that repo now returns **404** (private or deleted; confirmed via `gh api repos/jmtimper/dynasty-daddy` → `Not Found`, and `gh api users/jmtimper/repos` lists no `dynasty-daddy` repo, only a `dynasty-daddy-sleeper-mini`).

The only public copy that matches the **current** live app (Angular 14, the full feature set from the README's platform-support table, the Elo-adjusted playoff model, `documentation/` JSON help text matching the in-app help panel) is **`Leondoff/dynasty-daddy`** (default branch `main`, commit `6efac02` as fetched 2026-08-09). It is not a GitHub-flagged fork (`fork: false`) of jmtimper's repo — it appears to be a manual mirror/backup taken while jmtimper's repo was still public — but its `README.md` (creator credit, Twitter/Discord/BuyMeACoffee links, architecture description) and `LICENSE` (below) are internally consistent with the real project, and its file layout/behavior matches the live site's documented feature list. All citations below are against **`Leondoff/dynasty-daddy`** unless noted. Provenance of this specific mirror can't be independently confirmed via GitHub's fork graph — flagged **[unverified: mirror authenticity]** — but it is by far the best available source, all the code and docs are self-consistent, and it superseded `G-Sher`'s repo in every observable way (feature completeness, recency, matches live site).

---

## 1. Team strength

**Not KTC dynasty value.** This is the single biggest correction to the parent research doc, which said DynastyDaddy's values come from "a daily scrape of KeepTradeCut." That's true for the app's *trade-value/power-rankings* tool generally, but the **playoff calculator uses a completely separate metric**: redraft-season **ADP** consensus, not dynasty trade value at all. Per the app's own in-product help text (`front-end/fantasy-app/src/assets/documentation/playoff_calculator.json`):

> "Starter Value - Calculated by selecting the best possible roster based on average ADP. To calculate this value, we use current season (redraft) positional ADPs from multiple sources (Fantasy Pros, BestBall10s, Real Time Fantasy Sports, Underdog Fantasy, and Drafters Fantasy Sports)."

**Two selectable rating models** (`front-end/fantasy-app/src/app/components/services/playoff-calculator.service.ts:47-48`, `ForecastTypes` enum at the file's bottom, lines 1055-1058), user-picked via a UI radio group — **not** auto-switched by how much of the season has elapsed the way FTF's `resolve_strength_source('auto', ...)` is (`backend/outlook/strength.py:261-273`):

- **`ADP_STARTER`** (default) — pure redraft-ADP starter value, ignoring all game results, always available.
- **`ELO_ADJUSTED`** — starts from the same ADP starter value, then drifts weekly from actual results (see below).

**"Starter value" computation** (`power-rankings.service.ts:296-377`, `calculateADPValue`): for each team, greedily fill each starting slot (QB/RB/WR/TE/FLEX/SUPERFLEX) with the best-by-ADP eligible unused player (injury-excluded: PUP/IR/Sus/COV, line 505), sum the selected ADPs, then invert/rescale across the league: `adpValueStarter = (worstTeamStarterValue * 2) − team.adpValueStarter + 500` (line 373) — i.e. lower ADP (better player) → higher final "starter value," rescaled so the *worst* team anchors the bottom of the range. This is architecturally the same shape as FTF's `starting_lineup_value()` greedy-best-lineup fill (`backend/outlook/strength.py:91-132`), but the underlying per-player number is **redraft ADP rank**, not a dynasty trade-value number, and the league-wide rescaling is a linear invert-around-worst-team formula rather than a z-score (FTF's `RosterValueStrength` uses `mean + pts_per_sd * z`, `strength.py:161-168`).

**"Historical Elo" — initial rating, K, what updates it.** This is the standout methodological finding, and it directly answers the parent doc's open question about "what exactly is their historical Elo":

- **Initial rating = the ADP starter value itself**, not a fixed baseline like 1500 (`calculateEloAdjustedADPValue`, `power-rankings.service.ts:392-420`; the "handles 0 case" branch at lines 396-403 sets `eloAdpValueStarter = adpValueStarter` when `endWeek <= startWeek - 1`, i.e. preseason). There is no seed-rating constant anywhere in the codebase — the Elo ladder *is* the ADP-derived roster-strength number, just made to move.
- **K-factor is dynamic, not fixed**: `kValue = Math.max(10, Math.min(40, Math.round(Math.abs(team1Points − team2Points))))` (`power-rankings.service.ts:436`) — the **margin of victory in fantasy points, clamped to [10, 40]**, becomes that week's K. A 3-point nailbiter moves ratings by K=10; a 45-point blowout is capped at K=40. This is a real, deliberate design choice (margin-of-victory-scaled K is a known Elo variant, used e.g. in 538's NFL Elo) and is worth weighing against FTF's fixed-`sigma` scoring model, which has no analogous concept.
- **Update rule is textbook Elo**, base-400 logistic, via `StatService.eloRating`/`eloProbability` (`front-end/fantasy-app/src/app/services/utilities/stat.service.ts:17-38`): `eloProbability(r1, r2) = 1 / (1 + 10^((r1−r2)/400))`, then `newRating = rating + K * (actual − expected)` where `actual ∈ {0, 1}` from that week's real win/loss. **Important nuance:** this logistic Elo-update formula is used **only** to move the rating week-to-week — it is **not** the formula used to generate the simulator's matchup win probabilities (see §2). Two different probability models coexist in the same codebase for two different purposes.
- **History is retained per week** (`eloADPValueStarterHistory`, populated in `initializeEloADPValueStarterHistory`, `power-rankings.service.ts:429-462`) so the simulator can be re-run "as of" any past week (the "Forecast From" dropdown in the UI).

**Blend with starting-lineup value:** there is **no blend**. It's binary — either you're on `ADP_STARTER` (100% roster value, 0% results) or `ELO_ADJUSTED` (rating that *started* at 100% roster value in week 1 and has since been overwritten entirely by the Elo random-walk off real results — the original ADP value has no persistent weight once games start). This differs from FTF's `BlendedStrength`, which explicitly weighted-averages roster-value and trailing-scores `mu`/`sigma` by `completed_weeks / K` (`backend/outlook/strength.py:198-226`) — a real blend that decays the prior smoothly, versus DynastyDaddy's discrete switch-then-drift.

**Preseason/early-season behavior:** `ADP_STARTER` works identically at week 0 and week 10 (it never looks at results) — same posture as FTF's `RosterValueStrength`. `ELO_ADJUSTED` explicitly no-ops back to the ADP value before any games exist (lines 396-403), which is functionally identical to FTF's `resolve_strength_source` picking `roster_value` when `completed_weeks == 0`, except DynastyDaddy makes the user choose the model rather than auto-selecting it.

---

## 2. Weekly score model

**This is the largest structural delta from FTF's engine, and from the parent research doc's characterization.** DynastyDaddy does **not** draw a continuous point score per team per week. There is no `Normal(mu, sigma)`, no points-variance, no schedule-luck-via-point-differential, and (as a direct consequence) **no points-for value is ever produced by the simulator** — it literally cannot exist since no points are ever simulated.

Instead, every matchup is resolved as a **single weighted coin flip**:

1. Compute each team's **z-score** of its rating (whichever model — `adpValueStarter` or `eloAdpValueStarter`) against the **league-wide mean and standard deviation** of all teams' ratings that week (`calculateGamesWithProbability`, `playoff-calculator.service.ts:61-82`, using `simple-statistics`' `zScore`).
2. Convert each z-score to a **cumulative standard-normal probability** (`cumulativeStdNormalProbability`) — call these `p1`, `p2`.
3. **Win probability is linear, not the Elo logistic curve**: `team1Prob = 0.5 + (p1 − p2) / 2` (`getProbabilityForGame`, `playoff-calculator.service.ts:135-143`). This is a genuinely different formula from the `1/(1+10^(-Δ/400))` logistic used for the Elo *rating update* in §1 — DynastyDaddy runs two distinct probability models side by side for two different jobs (rating drift vs. matchup outcome) and they do not agree with each other at the same input ratings.
4. Each simulated matchup is then decided by `getRandomInt(100) < team1WinsOdds` (`simulateRegularSeason`, `playoff-calculator.service.ts:399,418`) — a **Bernoulli draw**, not a score comparison.

**No home/away** (fantasy has none). **No explicit schedule-luck modeling beyond whatever the real schedule pairing implies** — see §3 for where the pairings come from. **No median-game/"beat the league median" handling in the simulator itself**, but there is a related, separate median-win-probability calculation (`generateMedianProbabilities`, `playoff-calculator.service.ts:988-1014`) used only for leagues with a median-scoring ruleset, added as an extra coin-flip-against-the-median-team when `selectedLeague.medianWins` is true (lines 402, 421).

**Consequence worth flagging for FTF's calibration:** because DynastyDaddy never generates a point score, it has no `points_for` to use as a playoff tiebreaker — see §3.

---

## 3. Sim mechanics

**N = 10,000** for the season-long playoff calculator (`NUMBER_OF_SIMULATIONS = 10000`, `playoff-calculator.service.ts:45`), confirming the parent doc's number. A separate "what-if this trade happened" quick-simulation path (`mockSimulationOfASeason`, lines 87-110, used by the trade-impact tool) drops to **N = 1,000** for speed (line 109) — a detail the parent doc didn't have. This maps to FTF's default `DEFAULT_SIMS = 10000` (`backend/outlook/simulator.py:28`) exactly for the main path.

**Schedule source — no random-pairing fallback.** Future-week matchups come from `selectedLeague.leagueMatchUps[week]`, populated by `calculateLeagueMatchUps` (`matchup.service.ts:169-192`) directly from whatever the platform API already returned for that league. **If a week is `undefined` in that map, it is silently skipped from the simulation array — there is no fallback to a random or generated pairing.** This is informative for FTF's own open question (`league_state.py:26-30`, flagged "NOT... validated against live 2025 data") about whether Sleeper exposes full-season future `matchup_id` pairings: DynastyDaddy's code has zero fallback machinery for missing future pairings, which is consistent with the assumption that Sleeper (and the other supported platforms) **does** publish the full regular-season schedule upfront for standard (non-reseeding) formats — otherwise DynastyDaddy's playoff calculator would silently truncate the season for most leagues, which would have been a loud, obvious bug report long ago given the app's user base. Treat as **circumstantial evidence, not proof** — [unverified] against a live 2025 Sleeper league directly.

**Standings/tiebreakers:** wins accumulate as **fractional** win probabilities during the *projected-record* display path (`getProjectedRecord`, `playoff-calculator.service.ts:148-229`, e.g. `totalWins += matchUp.team1Prob`) but as **discrete simulated wins** during the actual Monte Carlo (`simulateRegularSeason`, lines 387-449). Playoff seeding picks the best remaining team by **simulated win total only** (`determineBestTeamFromArray`, lines 862-876); **ties in simulated win total are broken by yet another coin flip** using the same team-rating win-probability formula (`calculateTieBreaker`, lines 883-890) — **not** by points-for, current-standings points-for, or head-to-head, because (per §2) no points values exist anywhere in the simulation to break a tie with. This is a direct, structural consequence of the win/loss-only scoring model, not an independent design choice — worth noting because it means DynastyDaddy's simulated tiebreaks don't mirror how real fantasy leagues (including the leagues FTF serves) actually break ties.

**Divisions:** if the league has >1 division, division winners are determined first (`simulateDivisionWinners`, lines 456-487) using the same win-count-then-coin-flip-tiebreak logic, then byes/wildcards are assigned from the division winners plus best remaining teams (`simulateOneSeason`, lines 777-854).

**Byes:** `numOfByeWeeks` teams (division winners or best-overall, depending on divisions) get direct byes into `teamsLeft` before round 1 is simulated (lines 799-842).

**Bracket:** single-elimination, **reseeding within each round** (best surviving seed always faces the worst surviving seed) — `simulateRoundOfPlayoffs` pairs `playoffTeams[i]` against `playoffTeams[length-1-i]` (lines 500-503), same "high seed vs. low seed, reseed each round" shape as FTF's `_play_round`/`_reseed` in `playoff_format.py:86-103`. DynastyDaddy additionally supports a **2-game-per-round (aggregate) playoff format** (`gamesPerRound === 2`, lines 516-538, decided by total wins across two Bernoulli draws, tie broken by a third coin flip) — FTF's `StandardFormat` has no analogous multi-leg-round option.

**Same model for regular season and playoffs:** yes — playoff games use the identical win-probability formula and Bernoulli draw as regular-season games, just re-run each round on the surviving pool (`simulateRoundOfPlayoffs`, called repeatedly from `simulatePlayoffs`, lines 725-771). No separate "playoff intensity" or variance adjustment.

**Mid-playoff conditioning:** once real playoff games start actually completing, DynastyDaddy switches to `updatePlayoffOdds` (lines 575-716) which reads the *actual* bracket results already known (`leagueService.playoffMatchUps`) and only simulates the *remaining* undecided rounds — a real "condition on known results, simulate the rest" approach. FTF's simulator has no playoff-in-progress path yet (it always simulates the full remaining regular season + full bracket from the current state); this is a gap worth a future look, not urgent while `outlook.odds` stays dark preseason.

---

## 4. Outputs + presentation

**Aggregate metrics per team** (`generatePlayoffOdds`, `playoff-calculator.service.ts:897-944`): `timesMakingPlayoffs`, `timesWinningDivision`, `timesWithBye`, `timesMakeConfRd`, `timesMakeChampionship`, `timesWinChampionship`, `timesTeamWonOut`, `timesWithWorstRecord`, `timesWithBestRecord` — a noticeably richer output surface than FTF's `SimResult` (`made_playoffs`/`byes`/`titles`/`sum_wins`/`sum_seed`, `simulator.py:41-45`). Notably DynastyDaddy also surfaces **"times with worst record"** and **"times with best record"** (a Vegas-style superlative-odds pair) and **"times won out"** (ran the table) that FTF doesn't compute at all.

**Smoothing/rounding:** every per-matchup win probability is rounded to a **whole percent** immediately (`getPercent`, line 300-302: `Math.round(num * 100)`), and every final aggregate odds figure is rounded to the **nearest whole percent** again at the end (`Math.round(count / divisor)`, lines 930-940, where `divisor = numberOfSimulations / 100`). No decimal precision is ever surfaced to the user; FTF's `SimResult.playoff_pct()`/`title_pct()` return raw floats (`made_playoffs.get(rid,0)/n_sims`, `simulator.py:47-54`) and rounding is left to the serializer/UI layer — functionally similar end result, different layer of responsibility.

**Preseason/uncertainty labeling — DynastyDaddy does *not* hedge.** This is a meaningful contrast with FTF's design. The in-app documentation JSON (`playoff_calculator.json`) describes the tool matter-of-factly ("will update weekly... to give the most accurate results") with no beta/uncertainty framing, and the "Forecast From" week-selector simply offers **"Preseason"** as one plain dropdown option among the weeks (`playoff-calculator.component.ts:152`) — not a distinct, flagged, lower-confidence mode. There is no ribbon, badge, or caption in the reviewed source analogous to FTF's `meta.is_preseason`/`meta.beta` → "Projected · preseason · beta" treatment (`serialize.py`, `LeagueSummaryScreen.tsx` per `status.md`). DynastyDaddy shows the same numeric confidence (a bare "86%") whether it's week 1 or week 14. **This is explicitly the opposite of what the parent research doc recommended for FTF** ("Do not ship a hard '86% playoff odds' preseason") — worth the calibration agent knowing DynastyDaddy, a widely-used incumbent, made the opposite call and appears to have shipped fine with it, without implying FTF should follow suit.

---

## 5. License check

**Verdict: MIT, with a provenance caveat.**

`Leondoff/dynasty-daddy/LICENSE` (fetched 2026-08-09, commit `6efac02`), verbatim key lines:

```
MIT License

Copyright (c) 2022 Jeremy Timperio

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, ...
```

This resolves the parent doc's open unknown ("Repo license **[unverified]** — README shows no license in the fetched content") for the `G-Sher/dynasty-daddy` snapshot the parent doc actually looked at — that snapshot genuinely has **no LICENSE file at all** (confirmed via `gh api repos/G-Sher/dynasty-daddy/contents/`), so the parent doc's caution stands for that specific repo: no license there means all rights reserved, not reusable.

But the repo that actually matches the live app and that this entire reference is sourced from — `Leondoff/dynasty-daddy` — **does** carry an MIT license, correctly crediting the real creator (Jeremy Timperio) with a copyright year (2022) that predates this mirror's push date (2024), which is internally consistent with "this is a faithful copy of what jmtimper's real repo said at the time." **Caveat [unverified: mirror authenticity]:** because `jmtimper/dynasty-daddy` is now 404 and `Leondoff/dynasty-daddy` isn't a GitHub-recorded fork of it, there's no way to cryptographically or structurally verify this LICENSE file wasn't altered or fabricated by whoever pushed the mirror. It is the best evidence available and internally consistent, but not independently provable.

**Practical bottom line for FTF, unchanged either way:** per `CLAUDE.md`, no code copying regardless of license until the operator explicitly clears it. If MIT does hold (likely), the only practical unlock is that a future direct reuse of code (with attribution) would be *permitted* by the license once cleared — it does not change anything about this reference doc, which contains no copied code.

---

## 6. Deltas vs. our engine — comparison table

| Dimension | DynastyDaddy (Leondoff mirror, `playoff-calculator.service.ts` / `power-rankings.service.ts`) | FTF (`backend/outlook/`) | Assessment |
|---|---|---|---|
| **Team-strength input** | Redraft-season **ADP consensus** (5 ADP sources), greedy best-lineup fill | Dynasty/personal-board **player value** (KTC-style), greedy best-lineup fill (`strength.py:91-132`) | Different value bases, same lineup-fill algorithm shape. FTF's dynasty-value choice is *more* correct for a dynasty-first app — no change recommended. |
| **Rating→score mapping** | Linear invert-around-worst-team: `(worst*2) − v + 500` | Z-score affine: `mean_pts + pts_per_sd * z` (`strength.py:161-168`) | FTF's z-score approach is more standard/interpretable and easier to calibrate empirically. No change recommended. |
| **In-season model selection** | User picks `ADP_STARTER` vs `ELO_ADJUSTED` manually (radio group) | `auto` config picks `roster_value`→`blended`→`trailing_scores` by `completed_weeks` (`strength.py:261-273`) | FTF's auto-blend is a real improvement over DynastyDaddy's binary user toggle — **keep**. |
| **Blend mechanics** | None — binary switch; `ELO_ADJUSTED` fully overwrites the roster-value prior after week 1 | `BlendedStrength` weighted-averages `mu`/`sigma` by `completed_weeks/K` (`strength.py:198-226`) | FTF's smooth decay is more principled than DynastyDaddy's discrete cutover. **Keep.** |
| **"Elo" semantics** | Real Elo: initial rating = roster-value number, logistic base-400 update, **margin-of-victory-scaled K ∈ [10,40]** (`stat.service.ts:17-38`, `power-rankings.service.ts:436`) | No Elo at all — `TrailingScoresStrength` just averages/stdevs raw weekly scores (`strength.py:172-195`) | **Candidate idea worth evaluating** — see recommendations below. |
| **Weekly outcome model** | **Win-probability coin flip** (`0.5 + (p1−p2)/2` from normal-CDF of z-scores), Bernoulli draw — **no point scores generated at all** | **Point-score draw**: `gauss(mu, sigma)` per team per week, compare scores (`simulator.py:102-105`) | Structurally different paradigms. FTF's is strictly more informative (yields real point totals, a real `points_for` tiebreak, and margin-aware playoff scoring) — **this is a genuine strength of FTF's design, not a gap.** No change recommended; if anything, flag internally that DynastyDaddy's simpler approach is a *lower bar*, not a model to match. |
| **Win-probability formula (if adopting a probability-only fallback anywhere)** | Linear normal-CDF-difference (not the Elo logistic curve, even though Elo *rating updates* use the logistic curve elsewhere in the same codebase) | N/A (FTF never needs a standalone win-probability formula — score comparison IS the win probability) | Worth remembering FTF already gets a *more correct*, continuously-varying implicit win probability for free from its Gaussian draw; don't regress toward a hand-fit linear formula. |
| **Tiebreakers** | Simulated win-total ties broken by **another coin flip** (forced, because no points-for exists) (`playoff-calculator.service.ts:883-890`) | `points_for` deterministic tiebreak, from the same Gaussian draw (`simulator.py:114`, `playoff_format.py:65`) | FTF's is more realistic (matches how real leagues break ties) — **keep, no change.** |
| **N sims (main path)** | 10,000 | 10,000 (`DEFAULT_SIMS`, `simulator.py:28`) | Match. |
| **N sims (fast/what-if path)** | 1,000 for the trade-impact quick-sim (`playoff-calculator.service.ts:109`) | No fast-path variant exists yet | **Candidate idea** for a future "what does this trade do to our odds" feature — lower N for interactive latency. Not urgent for #169. |
| **Future-schedule fallback** | **None** — silently skips weeks the platform doesn't expose | Falls back to random round-robin pairing when Sleeper doesn't expose future pairings (`simulator.py:131-142`, flagged uncertain) | DynastyDaddy's total absence of a fallback is circumstantial evidence Sleeper *does* expose full-season pairings for standard formats, which would mean FTF's fallback path may rarely/never fire in practice — worth validating against a live 2025 Sleeper league per the existing open flag in `league_state.py:26-30`, not urgent to change code now. |
| **Playoff bracket shape** | Reseeding single-elim; optional 2-game aggregate rounds | Reseeding single-elim only (`playoff_format.py:68-98`) | 2-game rounds is a real format some leagues use — **candidate idea**, low priority (niche format). |
| **Divisions** | Division-winner priority seeding, byes drawn from winners first | Division-winner priority option exists (`playoff_format.py:39-66`, gated by `num_divisions > 1`) | Comparable coverage already. |
| **Mid-playoff conditioning** | Conditions on already-decided real playoff results, simulates only remaining rounds (`updatePlayoffOdds`) | Not implemented — always simulates full remaining season + full bracket from current LeagueState | **Gap, but out of scope while dark/preseason.** Note for whenever `outlook.odds` flips on mid-playoffs. |
| **Output surface** | 9 counters incl. best/worst-record odds, "won out" odds | 5 counters (playoff/bye/title/wins/seed) | DynastyDaddy's "times with best/worst record" is a fun, cheap addition — **candidate idea**, cosmetic/low-priority. |
| **Rounding/precision** | Rounds to whole percent twice (per-matchup, then aggregate) | Raw floats out of `SimResult`; rounding deferred to serializer/UI | Equivalent net UX; FTF's later-rounding is arguably cleaner (keeps precision available to the payload/serializer if ever needed). No change. |
| **Preseason/uncertainty labeling** | **None** — same bare percentage at week 1 as week 14 | Explicit `is_preseason`/`beta` flags → "Projected · preseason · beta" ribbon (`status.md`) | FTF's approach is more responsible/honest and matches the parent research doc's explicit recommendation. **Keep — do not remove the beta framing to "match" DynastyDaddy.** |
| **Determinism** | Uses `Math.random()` directly (`getRandomInt`, line 950-952) — **not seeded, not reproducible** | Explicitly seeded via `stable_hash(league_id) ^ config_seed` (`simulator.py:31-33,72-73`), repo rule: deterministic & resumable | FTF's determinism is a deliberate, stated project requirement DynastyDaddy doesn't share or need (it's a live client-side tool, not a backend contract). **Keep — do not change.** |

---

## Recommendations for our engine, ranked by likely calibration impact

1. **Highest impact — margin-of-victory-scaled K, as an idea for `TrailingScoresStrength`/a future Elo-flavored provider, not a literal port.** DynastyDaddy's `K = clamp(round(|marginOfVictory|), 10, 40)` is a cheap, well-precedented (538 NFL Elo uses the same family of idea) way to make a team's rating react faster to blowouts and slower to nailbiters. FTF currently has **no Elo-style rating provider at all** — `TrailingScoresStrength` just takes the raw mean/stdev of trailing scores, which is memoryless (doesn't compound game-to-game) and treats every week equally regardless of margin. If FTF ever builds an `OwnModelStrength` or a genuine week-over-week rating provider, a margin-scaled-K Elo update (seeded from `RosterValueStrength`'s preseason prior, exactly as DynastyDaddy seeds Elo from ADP value) is a proven, cheap pattern worth prototyping against the offline backtest scaffold (`tests/test_outlook_odds.py`) before the operator commits engineering time to it.

2. **Medium impact — validate the Sleeper future-schedule assumption, informed but not settled by this research.** DynastyDaddy's complete absence of a random-pairing fallback (§3) is suggestive that Sleeper reliably exposes full-season `matchup_id` pairings up front for non-reseeding formats, which would mean FTF's `_random_pairing` fallback (`simulator.py:131-148`) is dead code in the common case — good news if true (less noise in the sim), but this is circumstantial, not proof. The existing flag in `league_state.py:26-30` calling for live-2025-data validation stands; this doesn't replace that validation, it just raises confidence it'll come back "Sleeper does expose it."

3. **Low impact, cheap if wanted — a fast/low-N "what-if this trade happened" simulation path.** DynastyDaddy drops N from 10,000 to 1,000 specifically for its interactive trade-impact tool (`mockSimulationOfASeason`). If/when FTF's trade engine wants a "how does this trade move our playoff odds" feature, reusing `simulate()` with a smaller `n_sims` for interactive latency (accepting more Monte Carlo noise) is a pattern already proven at scale by an incumbent. Not relevant to the current dark #169 scope.

4. **Do not adopt — DynastyDaddy's win-probability-only (no point scores) simulation model.** Explicitly flagging this as a *rejected* idea, not an oversight: FTF's Gaussian point-score draw is strictly richer (yields real point totals, a real points-for tiebreak instead of DynastyDaddy's forced coin-flip tiebreak, and margin-aware everything). Don't let "DynastyDaddy does it differently" read as "DynastyDaddy does it better" here — the opposite is true on this specific axis.

5. **Do not adopt — DynastyDaddy's lack of preseason/beta labeling.** FTF's `is_preseason`/`beta` ribbon is more responsible and matches the parent research doc's own recommendation. DynastyDaddy shipping bare percentages at week 1 is evidence an incumbent *can* get away with it, not evidence FTF should.

---

## Corrections to the parent research doc

- **"Player values come from a daily scrape of KeepTradeCut... tied to Sleeper's public APIs"** — true for DynastyDaddy's trade-value/power-rankings surface in general, but the **playoff calculator specifically runs on redraft ADP consensus, not KTC dynasty value**. Worth knowing if anyone reuses "DynastyDaddy uses KTC" as a blanket statement elsewhere in FTF's docs.
- **"10,000-season Monte Carlo off schedule, historical Elo score, and starting line-up"** — accurate at a high level, but undersells how different the mechanism is: it's a discrete win/loss coin-flip simulation with no simulated point scores, not a points-based Monte Carlo. The "historical Elo" is real Elo (logistic, margin-of-victory K) but coexists with, and is not the same formula as, the matchup win-probability calculation.
- **License** — resolved for the specific repo the parent doc cited (`G-Sher/dynasty-daddy`: genuinely no LICENSE, confirmed) and for the repo that actually matches the live app (`Leondoff/dynasty-daddy`: MIT, with the provenance caveat in §5).

---

## Sources

- `Leondoff/dynasty-daddy`, commit `6efac02e3d12f931e5b47969ccdf9e0c8821c5a7`, fetched 2026-08-09 via `gh api`:
  - `front-end/fantasy-app/src/app/components/services/playoff-calculator.service.ts`
  - `front-end/fantasy-app/src/app/components/services/power-rankings.service.ts`
  - `front-end/fantasy-app/src/app/services/utilities/stat.service.ts`
  - `front-end/fantasy-app/src/app/components/services/matchup.service.ts`
  - `front-end/fantasy-app/src/app/components/model/playoffCalculator.ts`
  - `front-end/fantasy-app/src/app/components/playoff-calculator/playoff-calculator.component.ts`
  - `front-end/fantasy-app/src/assets/documentation/playoff_calculator.json`
  - `README.md`, `LICENSE`
- `G-Sher/dynasty-daddy` (parent doc's originally cited repo — confirmed stale/2021, no LICENSE): `README.md`, repo contents listing.
- `jmtimper/dynasty-daddy` — confirmed 404 (not publicly accessible) via GitHub API, 2026-08-09.
- FTF's own engine: `backend/outlook/{simulator,strength,playoff_format,league_state,pipeline,config}.py`, `docs/feedback/items/169-outlook-league-summary/{projection-source-research.md,odds-pipeline-lld.md,status.md}`.
