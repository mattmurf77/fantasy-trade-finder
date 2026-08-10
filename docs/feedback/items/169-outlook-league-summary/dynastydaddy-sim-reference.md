# DynastyDaddy simulator — source-level method reference (converged)

**Purpose:** a method reference for calibrating FTF's own dark odds engine (`backend/outlook/`, feedback #169). Everything below is read directly from DynastyDaddy's public source (front-end TypeScript — the simulation runs client-side, not on their Node/Express API). Nothing is copied; this is prose description only, per the operator's standing rule (no code reuse until cleared, regardless of license).
**Provenance:** dual-lens reconciliation of two independent source dives (`dynastydaddy-sim-reference.md` lens A and `dynastydaddy-sim-reference-b.md` lens B, both 2026-08-09), converged and **byte-level re-verified against source** by a third pass (2026-08-09, worktree `worktree-agent-a16b8c9e20f110454`) that fetched every cited file directly (`raw.githubusercontent.com` + `gh api`) and grepped/read the exact lines rather than trusting either lens's transcription. Every claim below is either independently confirmed at the cited line, or flagged where a lens's claim did not hold up. **[unverified]** marks claims the source doesn't settle.
**Supersedes:** both prior lens docs (deleted, content merged here) and corrects `projection-source-research.md`'s DynastyDaddy section — see "Corrections to the parent research doc."

---

## 0. Which repo, and why

The parent research doc cited `G-Sher/dynasty-daddy`. Confirmed via `gh api repos/G-Sher/dynasty-daddy`: last pushed **2021-09-10**, `license: null` (no LICENSE file), `fork: false`. Its own README lists *"Team Elo ranking like Chess"* under **Future Improvements** — this snapshot never implemented Elo at all, and it predates Angular 14 / the current feature set.

The live app's own README credits creator **Jeremy Timperio**, historically linked to `github.com/jmtimper/dynasty-daddy` — confirmed **404** (`gh api repos/jmtimper/dynasty-daddy` → `Not Found`; `gh api users/jmtimper/repos` lists 19 repos, none named `dynasty-daddy` — only `dynasty-daddy-sleeper-mini`).

The only public copy matching the **current** live app is **`Leondoff/dynasty-daddy`** — confirmed via `gh api repos/Leondoff/dynasty-daddy`: `fork: false`, `default_branch: main`, `license: MIT`, last pushed **2024-02-22**. Current `main` HEAD commit is `6efac02e3d12f931e5b47969ccdf9e0c8821c5a7` (confirmed live via `gh api repos/Leondoff/dynasty-daddy/commits/main` at time of this reconciliation — matches lens A's originally cited SHA, which was therefore a correctly pinned, reproducible citation; lens B cited "branch HEAD, not pinned by SHA" and turned out to be citing the same commit, just without pinning it explicitly). Its `README.md` (creator credit, Twitter/Discord/BuyMeACoffee links) and `LICENSE` are internally consistent with the real project, and it is not a GitHub-recorded fork of jmtimper's repo (`fork: false` — it appears to be a manual mirror/backup taken while jmtimper's repo was still public). All citations below are against **`Leondoff/dynasty-daddy` @ `6efac02`** unless noted. Provenance of this specific mirror can't be cryptographically verified against the vanished original — flagged **[unverified: mirror authenticity]** — but it is by far the best available source, is internally self-consistent, and matches the live site's documented feature list in every observable way.

---

## 1. Team strength

**Not KTC dynasty value.** The single biggest correction to the parent research doc, which said DynastyDaddy's values come from "a daily scrape of KeepTradeCut." True for the app's trade-value/power-rankings surface generally, but the **playoff calculator runs on a separate metric: redraft-season ADP consensus, not dynasty trade value at all.** Confirmed in the app's own in-product help text, `front-end/fantasy-app/src/assets/documentation/playoff_calculator.json` (fetched verbatim, minor typo in source preserved):

> "Starter Value - Calculated by selecting the best possible roster based on average ADP. To calculate this value, we use current season (redraft) positional ADPs from multiple sources (Fantasy Pros, BestBall10s, Real Time Fantasy Sports, Underdog Fantasy, and Drafters Fantasy Sports)."

**Two selectable rating models, and the Elo one carries an explicit Beta badge in the UI.** `playoff-calculator.service.ts:48` sets the default: `forecastModel: ForecastTypes = ForecastTypes.ADP_STARTER;`. The enum (`:1055-1058`): `ADP_STARTER = 0, ELO_ADJUSTED = 1`. This is user-picked via a radio group — **not** auto-switched by elapsed season the way FTF's `resolve_strength_source('auto', ...)` is (`backend/outlook/strength.py:261-273`). Confirmed directly in `playoff-calculator.component.html:15-16`:
```html
<mat-radio-button ... [value]="0">... Show our traditional starters by ADP forecast</mat-radio-button>
<mat-radio-button ... [value]="1">... Show our elo adjusted starters by ADP forecast <span class="warning__alert small-text__light">Beta</span></mat-radio-button>
```
The Elo-adjusted option is labeled **`Beta`** in the live UI, right next to the radio button — a real, verified fact that one lens (A) missed entirely; the other (B) found and cited it correctly at the right lines. This is a UI signal about the **model's** maturity (an alternate, experimental rating mode), and is a **conceptually distinct** thing from a preseason-data-uncertainty caveat on the odds themselves — see §4, where the two lenses' claims looked contradictory but are actually about two different UI elements.

- **`ADP_STARTER`** (default) — pure redraft-ADP starter value, ignoring all game results, always available, requires zero completed weeks.
- **`ELO_ADJUSTED`** (Beta) — starts from the same ADP starter value, then drifts weekly from actual results.

**"Starter value" computation** (`power-rankings.service.ts:296-377`, `calculateADPValue`): for each team, greedily fill each starting slot (QB/RB/WR/TE/FLEX/SUPERFLEX) with the best-by-ADP eligible unused player (injury-excluded: PUP/IR/Sus/COV), sum the selected ADPs, then invert/rescale across the league — confirmed verbatim at `power-rankings.service.ts:373`:
```ts
team.adpValueStarter = (worstTeamStarterValue * 2) - team.adpValueStarter + 500;
```
i.e. lower ADP (better player) → higher final "starter value," rescaled so the worst team anchors the bottom of the range. Architecturally the same shape as FTF's `starting_lineup_value()` greedy-best-lineup fill (`backend/outlook/strength.py:91-132`), but the underlying per-player number is **redraft ADP rank**, not dynasty trade value, and the rescaling is a linear invert-around-worst-team formula rather than FTF's z-score (`RosterValueStrength` uses `mean + pts_per_sd * z`, `strength.py:161-168`).

**Additional finding neither lens reported (verified in this pass):** the ADP field used isn't static all season even in `ADP_STARTER` mode. `power-rankings.service.ts:648`: `this.selectedRankings = isPreseason ? 'avg_adp' : 'avg_ros';` — DynastyDaddy switches from preseason average-ADP to **rest-of-season ADP** once the season starts, and `calculateADPValue` reads whichever field `selectedRankings` currently points to (`power-rankings.service.ts:104-109` etc.). So "ADP_STARTER never updates from this league's own results" (true — it never looks at wins/losses/scores) is correct, but the underlying **market data** it draws from does shift over the season via the ADP-field swap, which is a real update path distinct from Elo. Lens B's parenthetical ("fixed for the season, modulo the underlying ADP data source refreshing globally") anticipated this without citing it; this confirms that caveat was correct and gives it a citation.

**"Historical Elo" — initial rating, K, what updates it.**
- **Initial rating = the ADP starter value itself**, not a fixed baseline like 1500. Confirmed at `power-rankings.service.ts:396-403` (`calculateEloAdjustedADPValue`, "handles 0 case" branch): if `endWeek <= startWeek - 1` (preseason, no completed weeks), `team.eloAdpValueStarter = team.adpValueStarter; team.eloAdpValueChange = 0;`. There is no seed-rating constant anywhere in the codebase.
- **K-factor is dynamic, not fixed.** Confirmed verbatim at `power-rankings.service.ts:436`:
  ```ts
  const kValue = Math.max(10, Math.min(40, Math.round(Math.abs(matchUp.team1Points - matchUp.team2Points))));
  ```
  Margin of victory in fantasy points, clamped to `[10, 40]`, becomes that week's K. A real, deliberate design choice (margin-of-victory-scaled K is a known Elo variant, e.g. 538's NFL Elo) worth weighing against FTF's fixed-`sigma` scoring model, which has no analogous concept.
- **Update rule is textbook Elo, base-400 logistic.** Confirmed verbatim, `stat.service.ts:17` (`eloProbability`): `(1.0) / (1 + Math.pow(10, (rating1-rating2)/400))`; `stat.service.ts:28-37` (`eloRating`): `newRating = rating + kValue * (actual - expected)`. **Important nuance, confirmed:** this logistic update formula moves the rating week-to-week only — it is **not** the formula used for the simulator's matchup win probabilities (see §2). Two different probability models genuinely coexist in the same codebase for two different purposes.
- **History is retained per week** (`eloADPValueStarterHistory`, populated in `initializeEloADPValueStarterHistory`, `power-rankings.service.ts:426-462`) so the simulator can be re-run "as of" any past week (the "Forecast From" dropdown).

**Blend with starting-lineup value: there is no blend.** Binary — either `ADP_STARTER` (100% roster value, 0% results) or `ELO_ADJUSTED` (rating that started at 100% roster value and has since been overwritten entirely by the Elo random-walk off real results). This differs from FTF's `BlendedStrength`, which explicitly weighted-averages roster-value and trailing-scores `mu`/`sigma` by `completed_weeks / K` (`backend/outlook/strength.py:198-226`) — a real, smooth-decay blend versus DynastyDaddy's discrete switch-then-drift.

**Preseason/early-season behavior:** `ADP_STARTER` works identically at week 0 and week 10 (never looks at results, modulo the ADP-field swap noted above) — same posture as FTF's `RosterValueStrength`. `ELO_ADJUSTED` explicitly no-ops back to the ADP value before any games exist, functionally identical to FTF's `resolve_strength_source` picking `roster_value` when `completed_weeks == 0`, except DynastyDaddy makes the user choose the model rather than auto-selecting it.

---

## 2. Weekly score model

**This is the largest structural delta from FTF's engine, and from the parent research doc's characterization.** DynastyDaddy does **not** draw a continuous point score per team per week. There is no `Normal(mu, sigma)`, no points-variance, and — as a direct consequence — **no points-for value is ever produced by the simulator.**

Confirmed mechanism, `calculateGamesWithProbability` (`playoff-calculator.service.ts:61-81`):
1. Compute each team's **z-score** of its rating (`adpValueStarter` or `eloAdpValueStarter`) against the **league-wide mean and standard deviation** of all teams' ratings that week (uses `simple-statistics`' `zScore`).
2. Convert to a **cumulative standard-normal probability** (`cumulativeStdNormalProbability`) — call these `p1`, `p2`, stored per roster ID in `teamRatingsPValues`.
3. **Win probability is a linear average of independent percentiles, not the Elo logistic curve.** Confirmed verbatim, `getProbabilityForGame`, `playoff-calculator.service.ts:135-137`:
   ```ts
   const team1Prob = 0.5 + (teamRatingsPValues[matchup.team1RosterId] - teamRatingsPValues[matchup.team2RosterId]) / 2;
   ```
   Mathematically distinct from Elo's `1/(1+10^(-Δ/400))` — DynastyDaddy runs two different probability models side by side for two different jobs (rating drift vs. matchup outcome) and they don't agree at the same input ratings.
4. Each simulated matchup is a **Bernoulli draw**: `simulateRegularSeason`, `playoff-calculator.service.ts:399,418`: `getRandomInt(100) < matchUp.team1Prob` — not a score comparison.

**No home/away.** **No explicit schedule-luck modeling beyond whatever the real schedule pairing implies.** **Median-scoring-league support is real and first-class**, not a "central tendency" statistical concept: `generateMedianProbabilities` (`:988-1026`) builds a synthetic win-probability against a computed median team, gated by `leagueService.selectedLeague.medianWins`, added as an extra coin flip in `simulateRegularSeason` (`:402,421`) alongside the regular matchup coin flip.

**Consequence for FTF's calibration:** because DynastyDaddy never generates a point score, it has no `points_for` to use as a playoff tiebreaker — see §3.

---

## 3. Sim mechanics

**N = 10,000** for the season-long playoff calculator — confirmed verbatim, `playoff-calculator.service.ts:45`: `NUMBER_OF_SIMULATIONS = 10000;`. Confirmed in user-facing copy too, `playoff-calculator.component.html:89`: *"Our forecast uses 10,000 simulations of the season and updates after every week."* Matches FTF's `DEFAULT_SIMS = 10000` (`backend/outlook/simulator.py:28`) exactly.

A separate "what-if this trade happened" quick-simulation path (`mockSimulationOfASeason`, `:87-110`) drops to **N = 1,000** — confirmed verbatim at the call site, `:109`: `this.generatePlayoffOdds(week, teamPValues, matchups, 1000)`.

**Schedule source — no random-pairing fallback.** Future-week matchups come from `selectedLeague.leagueMatchUps[week]`, guarded by `!== undefined` checks throughout `matchup.service.ts` (`:126,173`), populated by `calculateLeagueMatchUps` directly from whatever the platform API already returned. No fallback to a random or generated pairing was found anywhere in the reviewed source. This is circumstantial evidence (not proof) that Sleeper publishes the full regular-season schedule upfront for standard formats — informative for FTF's own open question (`league_state.py:26-30`, flagged as unvalidated against live 2025 data), but **[unverified: Sleeper schedule completeness]** either way.

**Standings/tiebreakers, and where the two independent lenses actually disagreed (resolved here):**
- Wins accumulate as fractional win probabilities during the *projected-record* display path but as discrete simulated wins during the Monte Carlo itself (`simulateOneSeason`, `:777-853`).
- Simulated-win-total ties for seeding are broken by another rating-based coin flip: `calculateTieBreaker`, confirmed verbatim at `:883-889`:
  ```ts
  const team1Prob = this.getPercent(0.5 + (teamRatingsPValues[tiedTeams[0]...] - teamRatingsPValues[tiedTeams[1]...]) / 2);
  if (this.getRandomInt(100) < team1Prob) { return tiedTeams[0]; } return tiedTeams[1];
  ```
  No `points_for` exists to break ties with, because none was ever generated (§2).
- **2-game (aggregate) playoff-round ties: verified to also use the same rating-based coin flip, NOT real season fpts.** One lens (A) said "tie broken by a third coin flip"; the other (B) said "ties broken by real season-to-date fpts (`team.roster.teamMetrics.fpts`) — an inconsistency worth noting." **Lens A was right; lens B's `fpts` claim is incorrect and is retracted here.** Confirmed by direct code trace, `simulateRoundOfPlayoffs`, `:527-531`:
  ```ts
  if (team1Wins === team2Wins) {
    if (this.getRandomInt(100) < team1WinsOdds) { advancingTeams.push(team1); } else { advancingTeams.push(team2); }
  }
  ```
  `team.roster.teamMetrics.fpts` does exist in the codebase, but only in `simulateDivisionWinners` (`:316-330`), where it's a tertiary sort key for the **actual current-standings** division-rank calculation (rank → wins → fpts) — a completely different function serving a different purpose (real division standings, not simulated-tie resolution). There is no inconsistency in DynastyDaddy's tiebreak mechanism between 1-game and 2-game playoff rounds: both use the coin flip.

**Divisions:** if the league has >1 division, division winners are determined first (`simulateDivisionWinners`, `:456-487`) using the same win-count-then-coin-flip-tiebreak logic, then byes/wildcards are assigned from the division winners plus best remaining teams (`simulateOneSeason`, `:777-854`).

**Byes — a heuristic, not a config value, verified real and worth flagging as a latent bug.** Confirmed verbatim, `simulateOneSeason`, `:799-800`:
```ts
const numOfByeWeeks = this.leagueService.selectedLeague.playoffTeams % 2 === 0 ?
  this.leagueService.selectedLeague.playoffTeams % 4 : this.leagueService.selectedLeague.playoffTeams % 2;
```
A parity-based guess at bracket shape (6 playoff teams → 2 byes; 8 → 0; 5 or 7 → 1), **not** read from the platform's actual declared bracket settings. It will misjudge non-standard bracket shapes — e.g. a 10-team single-bye bracket gets `10 % 4 = 2` byes here, which is wrong for that shape. This was found by only one lens (B) and is confirmed true and unmodified by the other lens's review — a genuine, verified one-lens-only catch, not an inference. Contrast with FTF's `num_byes`, which is an **explicit config value** (`playoff_format.py:40-43`) — no guessing.

**Bracket — verified STATIC/fixed, NOT dynamically reseeded each round. This is the most consequential correction in this reconciliation and reverses one lens's conclusion.** Both lenses correctly identified the same code (`simulateRoundOfPlayoffs`, `:494-537`: pairs `playoffTeams[i]` vs `playoffTeams[length-1-i]`, pushes each round's winner into `advancingTeams` in ascending-`i` order) — but drew **opposite conclusions** from it. Lens A called this "reseeding within each round (best surviving seed always faces worst surviving seed)... same shape as FTF's `_reseed()`." Lens B said the bracket "stays fixed/static across rounds... it is NOT dynamically reseeded."

**Verified by tracing the caller, `simulatePlayoffs` (`:725-770`):**
```ts
let teamsLeft = playoffTeams
while (teamsLeft.length > 1) {
  if (teamsLeft.length === playoffTeams.length) {
    teamsLeft = playoffTeams.slice(0, numOfBye).concat(this.simulateRoundOfPlayoffs(teamsLeft.slice(numOfBye), teamRatingsPValues))
  } else {
    teamsLeft = this.simulateRoundOfPlayoffs(teamsLeft)
  }
  rounds.push(teamsLeft)
}
```
There is **no re-sort-by-seed step** between rounds anywhere in this loop or in `simulateRoundOfPlayoffs` itself. Round-1 winners are appended to `teamsLeft` purely in bracket-slot order (winner of slot 0 stays at index 0, winner of slot 1 stays at index 1, etc.), so round 2 pairs `teamsLeft[0]` (winner of the original 1-vs-8 game) against `teamsLeft[length-1]` (winner of the original 4-vs-5 game) — a **fixed tournament-tree bracket**, exactly like a standard single-elimination bracket seeded once at the start, **not** a dynamic reseed that re-sorts *all* surviving teams by original overall seed before every round.

**Lens B is correct; lens A is wrong on this specific point, and the error matters:** FTF's `_reseed()` (`backend/outlook/playoff_format.py:79-83,101-103`) explicitly re-sorts survivors by original overall seed before each round — the textbook definition of reseeding. DynastyDaddy does not do this. The two systems are **not** the same shape — FTF's bracket logic is a genuine, real design difference (arguably an improvement: dynamic reseeding is the fairer/more standard approach for a competitive bracket), not an equivalent implementation as lens A's comparison table stated. **This changes the "no change recommended, comparable" verdict lens A gave into "FTF is doing something meaningfully different and arguably better here — validated by contrast, no change needed, but don't describe it as 'the same shape.'"**

DynastyDaddy additionally supports a **2-game-per-round (aggregate) playoff format** (`playoffRoundType === 2`, `:497,516-538`) — FTF's `StandardFormat` has no analogous multi-leg-round option.

**Same model for regular season and playoffs:** yes — playoff games use the identical win-probability formula and Bernoulli draw as regular-season games, re-run each round on the surviving pool. No separate "playoff intensity" or variance adjustment.

**Mid-playoff conditioning:** once real playoff games start completing, DynastyDaddy switches to `updatePlayoffOdds` (`:575-716`), which reads the already-known actual bracket results and only simulates the remaining undecided rounds. FTF's simulator has no playoff-in-progress path yet (always simulates the full remaining regular season + full bracket from the current state) — a gap worth a future look, not urgent while `outlook.odds` stays dark preseason.

---

## 4. Outputs + presentation

**Nine aggregate counters per team**, confirmed verbatim at the initialization block, `generatePlayoffOdds`, `:901-911`: `timesMakingPlayoffs`, `timesWinningDivision`, `timesWithBye`, `timesMakeConfRd`, `timesMakeChampionship`, `timesWinChampionship`, `timesTeamWonOut`, `timesWithWorstRecord`, `timesWithBestRecord` — a noticeably richer output surface than FTF's `SimResult` (`made_playoffs`/`byes`/`titles`/`sum_wins`/`sum_seed`, `simulator.py:41-45`). Notably DynastyDaddy also surfaces **"times with worst/best record"** (a Vegas-style superlative-odds pair) and **"times won out"** that FTF doesn't compute at all.

**Smoothing/rounding:** confirmed verbatim — every per-matchup win probability rounds to a whole percent immediately (`getPercent`, `:300-302`: `Math.round(num * 100)`), and every final aggregate figure rounds to the nearest whole percent again at the end (`Math.round(count / divisor)`, `:927-940`, `divisor = numberOfSimulations / 100`). No decimal precision is ever surfaced to the user; FTF's `SimResult.playoff_pct()`/`title_pct()` return raw floats and rounding is deferred to the serializer/UI layer — functionally similar end result, different layer of responsibility.

**Preseason/uncertainty labeling — DynastyDaddy does *not* hedge on the odds themselves, and this is where the two lenses' claims looked contradictory but are not, once the two distinct UI elements are told apart.** There are exactly two "Beta/uncertainty" signals findable in the reviewed source, and neither is a preseason-data-quality caveat on the numbers:
1. The **`Beta` badge on the Elo-adjusted model radio button** (§1, `component.html:16`) — this flags the alternate *rating model* as experimental, not the odds' reliability at any given week.
2. The **"Forecast From" week selector offering "Preseason" as one plain dropdown option** among the weeks (`playoff-calculator.component.ts:152`, confirmed verbatim: `this.selectableWeeks.push({ week: ..., value: 'Preseason' });`) — a plain label, not a warning.

The in-app documentation JSON (`playoff_calculator.json`, quoted in full in §1) describes the tool matter-of-factly with no small-sample or low-confidence language anywhere in its four sections. There is **no ribbon, badge, or caption anywhere in the reviewed source** analogous to FTF's `meta.is_preseason`/`meta.beta` → "Projected · preseason · beta" treatment (`serialize.py`, `LeagueSummaryScreen.tsx` per `status.md`). DynastyDaddy shows the same numeric confidence (a bare percentage) whether it's week 1 or week 14. **Both lenses independently reached this same conclusion on the substantive question** ("does DynastyDaddy warn users the preseason numbers are low-signal?" — no) even though their prose framed it as if disagreeing; this reconciliation confirms it as a single, doubly-verified finding, not a divergence. See "Corrections to the parent research doc" for what this settles about `projection-source-research.md`.

---

## 5. License check

**Verdict: MIT, with a provenance caveat.** Confirmed via direct fetch of `Leondoff/dynasty-daddy/LICENSE` @ `6efac02` (byte-identical to both lenses' quoted excerpts):

```
MIT License

Copyright (c) 2022 Jeremy Timperio

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: ...
```

This resolves the parent doc's open unknown for the `G-Sher/dynasty-daddy` snapshot the parent doc actually cited — confirmed via `gh api repos/G-Sher/dynasty-daddy` → `license: null`. No LICENSE file there at all: all rights reserved, not reusable.

`Leondoff/dynasty-daddy` — the repo this entire reference is sourced from — **does** carry an MIT license, correctly crediting the real creator (Jeremy Timperio) with a copyright year (2022) predating this mirror's last push (2024), internally consistent with "faithful copy of what jmtimper's real repo said at the time." **Caveat [unverified: mirror authenticity]:** because `jmtimper/dynasty-daddy` is now 404 and `Leondoff/dynasty-daddy` isn't a GitHub-recorded fork of it, there's no cryptographic or structural way to verify this LICENSE file wasn't altered by whoever pushed the mirror. It is the best evidence available and internally consistent, but not independently provable.

**Practical bottom line for FTF, unchanged either way:** per `CLAUDE.md`, no code copying regardless of license until the operator explicitly clears it. If MIT does hold (likely, and re-confirmed live in this pass), the only practical unlock is that a future direct reuse of code (with attribution) would be *permitted* by the license once cleared — it does not change anything about this reference doc, which contains no copied code.

---

## 6. Deltas vs. our engine — comparison table

| Dimension | DynastyDaddy (`Leondoff/dynasty-daddy` @ `6efac02`) | FTF (`backend/outlook/`) | Assessment |
|---|---|---|---|
| **Team-strength input** | Redraft-season **ADP consensus** (5 sources; preseason avg-ADP swapped for rest-of-season ADP once the season starts, `power-rankings.service.ts:648`), greedy best-lineup fill | Dynasty/personal-board **player value** (KTC-style), greedy best-lineup fill (`strength.py:91-132`) | Different value bases, same lineup-fill algorithm shape. FTF's dynasty-value choice is more correct for a dynasty-first app — no change recommended. |
| **Rating→score mapping** | Linear invert-around-worst-team: `(worst*2) − v + 500` (`power-rankings.service.ts:373`) | Z-score affine: `mean_pts + pts_per_sd * z` (`strength.py:161-168`) | FTF's z-score approach is more standard/interpretable and easier to calibrate empirically. No change recommended. |
| **In-season model selection** | User picks `ADP_STARTER` vs `ELO_ADJUSTED` manually, radio group; Elo option carries a `Beta` UI badge (`component.html:16`) | `auto` config picks `roster_value`→`blended`→`trailing_scores` by `completed_weeks` (`strength.py:261-273`) | FTF's auto-blend is a real improvement over DynastyDaddy's binary user toggle — **keep**. |
| **Blend mechanics** | None — binary switch; `ELO_ADJUSTED` fully overwrites the roster-value prior after week 1 | `BlendedStrength` weighted-averages `mu`/`sigma` by `completed_weeks/K` (`strength.py:198-226`) | FTF's smooth decay is more principled than DynastyDaddy's discrete cutover. **Keep.** |
| **"Elo" semantics** | Real Elo: initial rating = ADP roster-value number, logistic base-400 update, margin-of-victory-scaled K ∈ [10,40] (`stat.service.ts:17-37`, `power-rankings.service.ts:436`) | No Elo at all — `TrailingScoresStrength` just averages/stdevs raw weekly scores (`strength.py:172-195`) | **Candidate idea worth evaluating** — see recommendations below. |
| **Weekly outcome model** | **Win-probability coin flip** (`0.5 + (p1−p2)/2` from normal-CDF of z-scores, `:135-137`), Bernoulli draw — **no point scores generated at all** | **Point-score draw**: `gauss(mu, sigma)` per team per week, compare scores (`simulator.py:102-105`) | Structurally different paradigms. FTF's is strictly more informative (real point totals, real `points_for` tiebreak, margin-aware playoff scoring) — genuine strength of FTF's design. No change recommended. |
| **Win-probability formula** | Linear normal-CDF-difference, not the Elo logistic curve (which is only used for the rating *update*, §1) | N/A — score comparison IS the win probability | FTF already gets a more correct, continuously-varying implicit win probability for free from its Gaussian draw. |
| **Tiebreakers (simulated ties)** | Simulated win-total ties, both 1-game and 2-game playoff rounds, broken by a rating-based coin flip (`calculateTieBreaker`, `:883-889`; `:527-531`) — **confirmed identical mechanism in both round formats; no inconsistency exists** | `points_for` deterministic tiebreak, from the same Gaussian draw (`simulator.py:114`, `playoff_format.py:65`) | FTF's is more realistic (matches how real leagues break ties) — **keep, no change.** |
| **N sims (main path)** | 10,000 (`:45`) | 10,000 (`DEFAULT_SIMS`, `simulator.py:28`) | Match. |
| **N sims (fast/what-if path)** | 1,000 for the trade-impact quick-sim (`:109`) | No fast-path variant exists yet | **Candidate idea** for a future "what does this trade do to our odds" feature. Not urgent for #169. |
| **Future-schedule fallback** | **None found** — guarded by `!== undefined` checks, silently skips undefined weeks (`matchup.service.ts:126,173`) | Falls back to random round-robin pairing when Sleeper doesn't expose future pairings (`simulator.py:131-142`, flagged uncertain) | Circumstantial evidence Sleeper exposes full-season pairings for standard formats — worth validating against live 2025 data per the existing flag in `league_state.py:26-30`, not urgent to change code now. |
| **Playoff bracket shape** | **Static/fixed single-elim bracket** — winners keep round-1 array position; **NOT dynamically reseeded** between rounds (verified by tracing `simulatePlayoffs`, no re-sort-by-seed step exists, `:725-770`). Optional 2-game aggregate rounds (`:497,516-538`) | **Dynamic reseeding every round** — survivors explicitly re-sorted by original overall seed before each round (`playoff_format.py:79-83,101-103`) | **Genuine, verified structural difference — not "the same shape" as one lens's initial read claimed.** FTF's dynamic reseeding is the fairer/more standard bracket mechanic; DynastyDaddy's fixed tournament tree is simpler but can seat mismatched strength in later rounds. No change recommended for FTF — validated-by-contrast as the better design, worth being precise about the difference rather than describing it as equivalent. 2-game aggregate rounds remain a real, low-priority candidate idea (niche format). |
| **Bye count** | **Derived heuristic** from playoff-field parity: `playoffTeams % 4` or `% 2` (`:799-800`) — can misjudge non-standard bracket shapes (e.g. 10-team single-bye → wrongly computes 2 byes) | **Explicit config value** (`num_byes` passed into `PlayoffFormat`, `playoff_format.py:40-43`) — no guessing | Confirmed real (verified in this pass). FTF's explicit config is strictly better — **no action needed beyond confirming FTF's pipeline always populates `num_byes` from real platform data.** |
| **Divisions** | Division-winner priority seeding, byes drawn from winners first (`:456-487`) | Division-winner priority option exists (`playoff_format.py:47-63`, gated by `num_divisions > 1`) | Comparable coverage already. |
| **Median-scoring-league format** | **First-class supported** — real median computed per completed week, synthetic median-opponent win-prob for future weeks (`:167-226,988-1026`) | **Not implemented** — no median-format concept anywhere in `outlook/` | Separate structural feature, not a calibration tweak. Worth a quick audit of whether any FTF-connected leagues use median scoring before investing; skip if none do. |
| **Mid-playoff conditioning** | Conditions on already-decided real playoff results, simulates only remaining rounds (`updatePlayoffOdds`, `:575-716`) | Not implemented — always simulates full remaining season + full bracket from current state | **Gap, but out of scope while dark/preseason.** Note for whenever `outlook.odds` flips on mid-playoffs. |
| **Output surface** | 9 counters incl. best/worst-record odds, "won out" odds (confirmed verbatim, `:901-911`) | 5 counters (playoff/bye/title/wins/seed) | DynastyDaddy's "times with best/worst record" is a fun, cheap addition — candidate idea, cosmetic/low-priority. |
| **Rounding/precision** | Rounds to whole percent twice — per-matchup (`getPercent`, `:300-302`) then aggregate (`:927-940`) | Raw floats out of `SimResult`; rounding deferred to serializer/UI | Equivalent net UX; FTF's later-rounding is arguably cleaner. No change. |
| **Preseason/uncertainty labeling on the odds themselves** | **None** — the only Beta/uncertainty signal anywhere is the Elo-*model* toggle badge (§1, §4), which is unrelated to preseason-data-quality; same bare percentage shown at week 1 as week 14 | Explicit `is_preseason`/`beta` flags → "Projected · preseason · beta" ribbon (`status.md`) | FTF's approach is more responsible/honest and matches the parent research doc's recommendation. **Keep — do not remove the beta framing to "match" DynastyDaddy;** DynastyDaddy shipping bare percentages preseason is evidence an incumbent *can* get away with it, not evidence FTF should. |
| **Determinism** | Uses `Math.random()` directly (`getRandomInt`, `:950-952`) — **not seeded, not reproducible** | Explicitly seeded via `stable_hash(league_id) ^ config_seed` (`simulator.py:31-33,72-73`), repo rule: deterministic & resumable | FTF's determinism is a deliberate, stated project requirement DynastyDaddy doesn't share or need (live client-side tool, not a backend contract). **Keep — do not change.** |

---

## Recommendations for our engine, ranked by likely calibration impact

1. **Highest impact — margin-of-victory-scaled K, as an idea for a future Elo-flavored strength provider, not a literal port.** DynastyDaddy's `K = clamp(round(|marginOfVictory|), 10, 40)` (confirmed, `power-rankings.service.ts:436`) is a cheap, well-precedented (538 NFL Elo uses the same family of idea) way to make a team's rating react faster to blowouts and slower to nailbiters. FTF currently has **no Elo-style rating provider at all** — `TrailingScoresStrength` just takes the raw mean/stdev of trailing scores, memoryless, treating every week equally regardless of margin. If FTF ever builds a genuine week-over-week rating provider, a margin-scaled-K Elo update (seeded from `RosterValueStrength`'s preseason prior, exactly as DynastyDaddy seeds Elo from ADP value) is a proven, cheap pattern worth prototyping against the offline backtest scaffold (`tests/test_outlook_odds.py`) before committing engineering time. **Feed the resulting rating into FTF's existing μ/σ machinery rather than replacing the Gaussian-score-draw simulator with DynastyDaddy's coin-flip approach** — steal the update rule, not the simulation mechanic; DynastyDaddy's own inconsistent-tiebreak-adjacent design (no `points_for` at all, forced coin-flip tiebreaks everywhere) is a real weakness of the no-scores model that FTF should not import.

2. **Medium impact — validate the Sleeper future-schedule assumption.** DynastyDaddy's complete absence of a random-pairing fallback (§3) is suggestive that Sleeper reliably exposes full-season `matchup_id` pairings up front for non-reseeding formats — circumstantial, not proof. The existing flag in `league_state.py:26-30` calling for live-2025-data validation stands.

3. **Medium impact, near-zero risk — implement median-scoring-league support if any FTF-connected leagues use it.** A completely separate structural feature, not a calibration tweak. Worth a quick audit of whether any current FTF leagues have a median-wins-equivalent setting before investing; skip if none do.

4. **Low impact, cheap if wanted — a fast/low-N "what-if this trade happened" simulation path.** DynastyDaddy drops N from 10,000 to 1,000 specifically for its interactive trade-impact tool. If FTF's trade engine wants a "how does this trade move our playoff odds" feature, reusing `simulate()` with a smaller `n_sims` for interactive latency is a pattern already proven at scale by an incumbent. Not relevant to the current dark #169 scope.

5. **Do not adopt — DynastyDaddy's static/fixed playoff bracket.** **This recommendation changed under re-verification** (see Reconciliation log): one of the two source lenses initially described DynastyDaddy's bracket as "reseeding, same shape as FTF" — confirmed false by tracing `simulatePlayoffs`/`simulateRoundOfPlayoffs`; DynastyDaddy's bracket is a fixed tournament tree with no re-sort-by-seed step between rounds. FTF's actual dynamic reseeding (`playoff_format.py:79-83,101-103`) is the more standard, fairer bracket mechanic and should be described as a **genuine, validated difference**, not an equivalent implementation. No code change needed — this is a correction to how the comparison should be talked about, not a new gap.

6. **Do not adopt — DynastyDaddy's bye-count parity heuristic.** Confirmed real and a latent bug for non-standard bracket shapes (`playoffTeams % 4`/`% 2`, `:799-800`). FTF's explicit `num_byes` config value is strictly better; no action needed beyond confirming the pipeline always populates it from real platform data rather than ever falling back to a similar guess.

7. **Do not adopt — DynastyDaddy's win-probability-only (no point scores) simulation model.** Explicitly a *rejected* idea, not an oversight: FTF's Gaussian point-score draw is strictly richer (real point totals, a real points-for tiebreak instead of DynastyDaddy's forced coin-flip tiebreak — confirmed to apply uniformly across 1-game and 2-game playoff rounds with no inconsistency, see §3 — and margin-aware everything). Don't let "DynastyDaddy does it differently" read as "DynastyDaddy does it better" here.

8. **Do not adopt — DynastyDaddy's lack of preseason/beta labeling on the odds themselves.** FTF's `is_preseason`/`beta` ribbon is more responsible and matches the parent research doc's own recommendation. DynastyDaddy shipping bare percentages at week 1 (confirmed: no preseason-uncertainty caveat exists anywhere in the reviewed source, distinct from the unrelated Elo-model Beta badge) is evidence an incumbent *can* get away with it, not evidence FTF should.

**Net effect of this reconciliation on the ranking:** the calibration priority order is materially **unchanged** from both source lenses' independent conclusions — margin-scaled-K Elo remains the top actionable idea, and every "do not adopt" verdict from both lenses survives re-verification (with recommendation 5's *reasoning* corrected, not its conclusion — DynastyDaddy's bracket was never worth copying, it just wasn't for the reason originally stated). **No recommendation flips from "adopt" to "reject" or vice versa** as a result of this reconciliation; the practical guidance for the calibration agent is the same as either lens alone would have given, now with the bracket-mechanics claim and the tiebreak-consistency claim corrected to match source ground truth.

---

## Corrections to the parent research doc

- **"Player values come from a daily scrape of KeepTradeCut... tied to Sleeper's public APIs"** — true for DynastyDaddy's trade-value/power-rankings surface in general, but the **playoff calculator specifically runs on redraft ADP consensus, not KTC dynasty value**. Worth knowing if "DynastyDaddy uses KTC" is ever repeated as a blanket statement elsewhere in FTF's docs.
- **"10,000-season Monte Carlo off schedule, historical Elo score, and starting line-up"** — accurate at a high level, but undersells how different the mechanism is: it's a discrete win/loss coin-flip simulation with no simulated point scores, not a points-based Monte Carlo. The "historical Elo" is real Elo (logistic, margin-of-victory K) but coexists with, and is not the same formula as, the matchup win-probability calculation, and is an **opt-in Beta-badged alternative to the default ADP model**, not DynastyDaddy's single/primary rating method.
- **License** — resolved for the specific repo the parent doc cited (`G-Sher/dynasty-daddy`: genuinely no LICENSE, confirmed via `gh api`) and for the repo that actually matches the live app (`Leondoff/dynasty-daddy`: MIT, with the provenance caveat in §5).
- **Recommendation #5's "Do not ship a hard '86% playoff odds' preseason" framing** — the parent doc did not explicitly claim DynastyDaddy hedges its preseason numbers, but the "86%" example reads as though contrasting FTF's planned caution against a competitor's practice. **Re-verified directly against DynastyDaddy's source and UI copy: DynastyDaddy does not hedge preseason odds at all** — no small-sample or low-confidence warning exists anywhere in the reviewed `playoff_calculator.json` documentation, component templates, or explainer copy. FTF's `is_preseason`/`beta` ribbon is a deliberate point of differentiation from this incumbent's actual behavior, not a parity feature — the recommendation to ship the beta framing stands and is, if anything, more justified now that DynastyDaddy's silence on this point is confirmed rather than assumed.
- **A dated correction note has been added inline to `projection-source-research.md`** pointing here for the full detail (see that file's §"What RosterAudit and DynastyDaddy actually use").

---

## Reconciliation log

Two independent research agents ("lens A" and "lens B") source-dove `Leondoff/dynasty-daddy` on the same brief without reading each other's work. Both converged on the correct canonical repo, license, N=10,000/1,000 sim counts, the ADP-based (not KTC) team-strength input, the no-point-score/Bernoulli-coin-flip weekly model, the CDF-linear (not Elo-logistic) win-probability formula, the margin-scaled-K Elo update rule, and the absence of any preseason-uncertainty caveat in DynastyDaddy's UI. This reconciliation pass fetched every cited source file directly (`raw.githubusercontent.com` + `gh api`, pinned to commit `6efac02`) and re-derived every disputed or single-lens claim from the actual code/markup rather than trusting either transcription.

**What lens A got right that lens B under-cited:** the pinned, reproducible commit SHA (`6efac02...`, confirmed as current `main` HEAD at reconciliation time) rather than an unpinned branch-HEAD reference. The 2-game-playoff-round tiebreak mechanism (coin flip, same as everywhere else) — lens B's claim that these ties use real season fpts was traced and found incorrect; the `fpts` field it cited exists in the codebase but powers a different function (`simulateDivisionWinners`'s real-standings sort), not simulated-tie resolution.

**What lens A got wrong or missed:** did not report the explicit `Beta` UI badge on the Elo-adjusted model toggle (`component.html:16`) — a real, verifiable, present-in-source UI element lens B found and cited correctly. More consequentially, lens A characterized DynastyDaddy's playoff bracket as "reseeding within each round... same shape as FTF's `_reseed()`" — **verified false** by tracing `simulatePlayoffs`/`simulateRoundOfPlayoffs`: DynastyDaddy's bracket has no re-sort-by-seed step between rounds and is a static/fixed tournament tree, structurally different from FTF's genuine dynamic reseeding. This was the single most consequential error resolved in this pass, because it inverted a comparison-table verdict (from "equivalent, no change" to "genuinely different, FTF's approach validated by contrast").

**What lens B got right that lens A missed:** the `Beta` UI badge (above); the bye-count parity heuristic (`playoffTeams % 4`/`% 2`, `:799-800`) as a real, verified latent bug in DynastyDaddy's bracket-sizing logic, entirely uncited by lens A; the correct bracket-staticness call (above). Lens B's framing of "static vs. dynamically reseeded" was the more rigorous read of the same code both lenses cited — it explained *why* (no resort step) rather than asserting the conclusion.

**What lens B got wrong:** the 2-game-playoff-round tiebreak claim (real fpts vs. coin flip) — retracted above, confirmed to use the identical coin-flip mechanism as every other simulated tie in the codebase.

**What neither lens caught, found in this pass:** DynastyDaddy swaps its underlying ADP field from preseason average-ADP to rest-of-season ADP once the season starts (`power-rankings.service.ts:648`, `selectedRankings = isPreseason ? 'avg_adp' : 'avg_ros'`) — meaning `ADP_STARTER` mode isn't fully static all season the way both lenses' prose implied, even though it's correct that it never reacts to *this league's own results*. This nuance doesn't change any recommendation but sharpens the "static" claim in §1.

**Net effect on recommendations for the calibration agent:** unchanged in priority order and adopt/reject verdicts (see "Net effect of this reconciliation on the ranking" above) — the corrections are about *why* certain DynastyDaddy design choices should or shouldn't be copied (bracket mechanics, tiebreak consistency), not about *whether*. The margin-scaled-K Elo idea remains the single highest-value takeaway; every "do not adopt" verdict from both lenses survives, with tighter, source-verified reasoning behind each.

---

## Sources

- `Leondoff/dynasty-daddy`, commit `6efac02e3d12f931e5b47969ccdf9e0c8821c5a7` (confirmed current `main` HEAD at reconciliation time via `gh api repos/Leondoff/dynasty-daddy/commits/main`), fetched via `raw.githubusercontent.com` and `gh api`, 2026-08-09:
  - `front-end/fantasy-app/src/app/components/services/playoff-calculator.service.ts` (1058 lines, fetched and grepped in full)
  - `front-end/fantasy-app/src/app/components/services/power-rankings.service.ts` (704 lines, fetched and grepped in full)
  - `front-end/fantasy-app/src/app/services/utilities/stat.service.ts` (114 lines, fetched in full)
  - `front-end/fantasy-app/src/app/components/services/matchup.service.ts` (300 lines, fetched and grepped in full)
  - `front-end/fantasy-app/src/app/components/playoff-calculator/playoff-calculator.component.ts` (353 lines, fetched and grepped in full)
  - `front-end/fantasy-app/src/app/components/playoff-calculator/playoff-calculator.component.html` (108 lines, fetched in full)
  - `front-end/fantasy-app/src/assets/documentation/playoff_calculator.json` (fetched and quoted in full)
  - `README.md`, `LICENSE` (fetched in full)
- `gh api repos/G-Sher/dynasty-daddy`, `gh api repos/Leondoff/dynasty-daddy`, `gh api repos/jmtimper/dynasty-daddy`, `gh api users/jmtimper/repos`, `gh api repos/Leondoff/dynasty-daddy/commits/main` — all queried live during this reconciliation, 2026-08-09.
- FTF's own engine: `backend/outlook/{simulator,strength,playoff_format,league_state,pipeline,config}.py`, `docs/feedback/items/169-outlook-league-summary/{projection-source-research.md,odds-pipeline-lld.md,status.md}`.
- Prior lens docs (superseded, deleted): `dynastydaddy-sim-reference.md` (lens A, 2026-08-09, worktree `worktree-agent-adf883cf6fe9ad0f2`), `dynastydaddy-sim-reference-b.md` (lens B, 2026-08-09).
