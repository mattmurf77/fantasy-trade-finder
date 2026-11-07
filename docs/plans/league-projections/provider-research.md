# Sleeper projection normalization research

Research captured **2026-11-07 UTC / November 6 Eastern**. Scope: the new scheduled playoff/Max PF projection capability in `/private/tmp/fleeced-projection-capability`. No application code, production settings, or architecture-plan files were changed. Public provider requests were read-only. Only aggregate results are saved; no fantasy roster, owner names, rankings, or preferences are persisted here.

## Result and immediate integration guidance

**There is a usable provider-native source for exact scheduled kickoff and observed game status.** The draft adapter should stop requiring nonexistent `kickoff_at`, `availability`, and `supported_scoring_keys` fields in raw projection rows. Derive timing from Sleeper's scores endpoint; represent availability assumptions and scoring coverage explicitly in the adapter. This fixes the source-contract mismatch without pretending that every custom scoring rule has a complete forecast.

**The reference league's full custom-scoring projection is not yet validated.** Raw IDP forecasts exist, but several required event forecasts are missing, and kicker distance bands are not a complete partition of supplied totals. The parent directed that absent required events remain explicit incomplete/unsupported states. A historical-rate fallback is a separately proposed model extension, not enabled or verified provider data.

The latest product instruction is **scheduled weekly batching, Tuesday 09:30 America/New_York by default/configuration**, feeding existing projected standings. Opening the screen or changing rosters must not trigger a new forecast. A scheduled result is an **as-of snapshot**, not a promise of current live NFL state. Keep the last successful result and its timestamp when a batch fails or is incomplete.

Deliverables:

- [Aggregate provider coverage](aggregate-provider-coverage.json): observed counts and reconciliation, without raw customer records.
- [Read-only aggregate probe](provider-coverage-probe.py): reproducible requests; raw league responses stay in memory.
- [Timing/bye reference functions](../../../backend/league_projections/timing.py): pure research reference for builder integration, not application code.
- [Six offline seam tests](../../../backend/tests/test_league_projection_timing.py): passing; cover exact timestamps, game joins, incomplete schedules, byes, null opponent, and non-pregame states. They do not establish application integration or forecast quality.

The independent evaluator also passed seven additional synthetic timing controls in `/private/tmp/fleeced-projection-eval/test_timing_contract.py`. This is evidence for the timing seam only.

## 1. Source status and observed coverage

Sleeper's [official API documentation](https://docs.sleeper.com/) documents NFL state, league settings, rosters, weekly matchups, player metadata, and traded picks. It does **not** document the projection, stat, schedule, or scores routes used below. These are directly observed provider responses, not guaranteed public API contracts or a claim about commercial rights.

| Provider route | Observed contents | What it can establish |
|---|---|---|
| [`/schedule/nfl/regular/2026`](https://api.sleeper.app/schedule/nfl/regular/2026) | 272 unique games, 32 NFL teams, 17 games per team, one game per team/week | Full-season team/week schedule and scheduled byes after completeness checks |
| [`/scores/nfl/regular/2026/9`](https://api.sleeper.app/scores/nfl/regular/2026/9) | 15 games; `start_time` in epoch milliseconds; offset-bearing `metadata.date_time`; `has_started`, `is_in_progress`, `is_over`, `canceled`, `closed`; top-level status | Exact **scheduled** kickoff and observed game phase, joined by `game_id` |
| [`/projections/nfl/2026/10?season_type=regular`](https://api.sleeper.app/projections/nfl/2026/10?season_type=regular) | 9,418 rows, including 4,357 rows with DL/LB/DB fantasy eligibility in the initial probe; `company=rotowire`; sparse `stats`; date-only `date`; null top-level status | Supplied weekly projected stat values and their provenance; not exact kickoff or verified participation |
| [`/stats/nfl/2026/8?season_type=regular`](https://api.sleeper.app/stats/nfl/2026/8?season_type=regular) | 2,080 rows, including 970 IDP-eligible rows in the initial probe; `company=sportradar`; sparse actual event stats | Observed actual event vectors, subject to feed coverage and stat corrections |

The saved probe verified score/schedule game-ID set equality and exact timestamp consistency for weeks **8–14**. Week 8 contained 14 completed games; week 9 contained one completed game and 14 pregame games. Weeks 10–14 were all pregame, with 14/13/16/14/15 games respectively. Those are facts at capture, not permanent fixtures.

The season schedule and projection `date` fields are `YYYY-MM-DD`. **Do not turn them into midnight and call it kickoff.** The scores route solves that gap without a third-party team/date join. `metadata.date_time` and `start_time` agreed for every inspected game.

## 2. Normalization contract for timing and byes

1. Fetch the season schedule once per batch and validate coverage. The reference functions make modern-NFL shape expectations explicit arguments: 272 games, 32 teams, 17 appearances per team across 18 weeks. They reject duplicate game IDs, duplicate team/week games, and partial schedules. These are not universal constants for every historical season or exceptional schedule.
2. Fetch `/scores/nfl/regular/{season}/{week}` for each requested week. Validate sport, season, season type, week, game-ID set equality, and home/away agreement with the season schedule.
3. Convert `start_time` **as milliseconds**, not magnitude-guessed seconds. Reconcile `metadata.date_time` if supplied; reject conflicting exact timestamps. Preserve source update time and fetched/captured time separately.
4. Join projection rows on `game_id` and NFL team. Derive opponent from the matched game if raw opponent is null; reject a supplied contradictory opponent. The probe found many unpopulated projection rows with valid game ID/team but null opponent, `gp`, and points. Joining their schedule does not create a valid stat forecast.
5. Classify a game as pregame only with a future scheduled kickoff, `pre_game`/`scheduled` status, and explicit false start/in-progress/over/canceled flags. Classify completed only with `complete`, started/over true, in-progress false, and a kickoff already passed. Preserve `closed` as additional source evidence; completion is still subject to later stat corrections.
6. Canceled, postponed/unknown, delayed-after-scheduled-kickoff, or started-unfinished games do not become pregame or zero-point games. A conservative initial engine can reject a current live week while retaining the last successful Tuesday batch.
7. A **scheduled bye** requires a known NFL team and absence from a validated complete week/season schedule. A missing player row, no NFL team, missing projection, canceled game, and unknown team mapping are separate states. Never infer bye from zero points or no projection.

If ingestion crosses kickoff or a game phase changes during capture, restart or fail the new batch; do not publish a pregame optimization built partly after locks took effect. Freeze source hashes/times with the result. Local persistence cannot turn asynchronous provider reads into an atomic upstream transaction.

`/v1/state/nfl` documents current week, leg, and display-week concepts, **not settled fantasy standings**. Especially at a Tuesday cadence, do not use `state.week - 1` alone as proof of completed scoring weeks. Reconcile the league's W-L-T totals, all completed matchup weeks, NFL game states, and aggregate PF/PA/Max PF boundaries. A rollover mismatch is a batch coverage state, not permission to double-count the current week.

## 3. Pregame, completed, and live semantics

Pregame-only weekly batching is meaningful: it can publish before the next week's games and remain a visibly dated baseline. It does not establish that today's November 6 mixed current week can be fully simulated by the draft provider, which presently rejects every kickoff at or before capture.

To support a mixed completed/pregame week later, retain actual locked starters in their original slots, exclude already-played bench players from actual lineup substitutions, and use official `players_points`/`starters_points` for completed contributions. Max PF uses a different eligible pool and can consider completed bench outcomes. Never replace a partial live score with a final score, or add actuals while retaining their full historical/projection share and variance. A completed NFL game alone does not prove the fantasy week's aggregate standings already include that game.

Sleeper's [AutoSubs documentation](https://support.sleeper.com/en/articles/9731991-how-does-player-autosubs-work) also shows that lineup locks can depend on paired-player rules. Unsupported AutoSubs/commissioner lock semantics need detection or an explicitly limited model; scheduled kickoff alone does not reconstruct every fantasy lineup rule.

## 4. Actual sparse stats: strong evidence, bounded conclusion

The authorized reference league's weeks 1–8 supplied **3,663 official player-week point entries**. Of these, **3,214 had a matching raw actual-stat row**. All 3,214 reproduced official points exactly, to the probe's six-decimal comparison, using `sum(coefficient * stats.get(key, 0))` across the league scoring settings. The remaining **449 lacked raw stat rows and all had official zero points**. Every nonzero reference scoring key appeared somewhere in the eight-week actual-stat corpus.

This supports a **versioned sparse-zero decoder for these observed completed actual-stat vectors**, after feed and horizon validation. It is not a universal provider schema guarantee. Missing entire rows remain different from missing fields; use official completed player points where available instead of inventing participation from absent stats. The probe did not reconstruct historical Max PF, historical reserve/taxi eligibility, or original roster ownership, and makes no claim of exact Max PF replication. Preserve official aggregate Max PF as the authoritative starting total.

## 5. Projected stats: supported keys, missingness, and derivations

The adapter should own a versioned field registry containing domain (individual/team defense), statistic meaning, direct/derived support, and evidence. `supported_scoring_keys` is normalized metadata supplied by that adapter; it is not a raw Sleeper field. Neither a prefix nor the union of keys seen somewhere proves that an absent value is zero for a specific player/week.

- Directly supplied numeric expected event counts/yardage can be scored linearly with league coefficients. Preserve negative values and avoid generic `pts_ppr`/`pts_half_ppr`, which do not represent arbitrary custom IDP rules.
- Missingness is not confined to rare IDP events. Requiring every league coefficient on every player while setting `inapplicable_keys=[]` also rejects ordinary QB/RB/WR combinations: RB rows omit passing fields; QB rows omit receiving fields. A position mask is not universally true because of trick plays, special teams, and dual eligibility. A practical decoder needs an explicitly versioned sparse-forecast convention or modeled applicability policy, with exceptions and validation. It must distinguish this assumption from physically impossible events and from globally unsupported fields.
- Only finite enumerated **team-defense-only** coefficients can be inapplicable when no team-defense slot exists. Existing `backend/season_forecasts.py` has explicit `TEAM_DEFENSE_SCORING_KEYS` and `KICKER_SCORING_KEYS`; use them as a reviewed starting point, not a blanket `def_*`/`idp_*` filter. Individual special-teams/fumble events can apply to offensive players and dual-eligible players.
- Sleeper's [scoring-options guide](https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available) distinguishes individual, team-defense, kick-distance, and threshold categories. Its [special-teams guide](https://support.sleeper.com/en/articles/3278982-special-teams-scoring-options) explains individual/team ownership of those events. Its [tackle guide](https://support.sleeper.com/en/articles/4056297-how-are-tackles-calculated) confirms intentional stacking; do not deduplicate tackle, tackle-for-loss, and sack coefficients to “correct” the user's rules.
- `fgmiss = fga - fgm` is a possible **declared derived expectation** if both inputs use consistent event definitions and are valid; expectation is linear. Do not clamp negative discrepancies into zero. Do not silently infer every absent distance band from totals: the observed projection vectors are not internally complete partitions.
- Week 10 had 28 kicking rows with both `fga` and `fgm`, but only one supplied `fgm_0_19`. Some supplied `fgm` totals exceeded the sum of supplied distance bands by about 0.45; `fga - fgm` differed from summed supplied miss bands by up to 0.18. Missing projected distance fields therefore cannot be casually labeled structural zeros. These observations need provider/model investigation, not an invented alias.
- Across all inspected weeks 9–14, required individual keys `idp_blk_kick`, `idp_def_td`, `st_ff`, `st_fum_rec`, and `fum_rec_td` were absent from the entire forecast feed. Generic `def_td` appeared on team defenses in the week-10 check, so aliasing it to individual IDP touchdowns is not justified. The aggregate file lists additional absent team-defense/default keys separately from this interpretation.
- Milestone bonuses require an expected indicator/distribution, not applying a threshold to expected yards. Direct expected counts for event categories are different from unsupported nonlinear transformations. Unknown required coefficients remain unsupported; missing applicable values remain incomplete.

Consequently, common IDP stat presence does not establish complete support for the reference league. The new adapter can now report the **actual missing scoring keys**, rather than an impossible raw-attestation error.

An additional exploratory check reconstructed provider PPR totals from common offensive and return-event fields with missing values treated as zero. Among 374 QB/RB/WR/TE rows, 362 differed by at most 0.1 points and 12 exceeded that tolerance (maximum 0.452). This suggests a sparse convention and rounding/other event differences, but it is **not an exact field-completeness proof** or sufficient admission evidence for a general decoder. The formula and standard-score semantics would need fuller reconciliation before using that check as a contract. No zero-fill policy was enabled from it.

## 6. Availability, reserve, taxi, and native eligibility

Week-10 rows with `gp=1` included **109 IR-labeled, 51 Out-labeled, and 10 PUP-labeled players** in the full public feed. This disproves interpreting `gp=1` as confirmed future health. Current injury labels also do not supply a return calendar. Sleeper's [injury-status guide](https://support.sleeper.com/en/articles/3570017-injury-statuses-and-ir-eligibility) explains that an Out designation is week-specific and can reset after the week; [IR rules](https://support.sleeper.com/en/articles/1983643-how-does-injured-reserve-ir-work) depend partly on league settings.

A usable **proposed scenario** is to consume the provider's supplied weekly stat forecast without a second invented health multiplier, retain injury labels and coverage warnings, and explicitly state that future participation is uncertain. This must be named/versioned as a model assumption; a compatibility value of `availability=1` must never be presented as provider-attested playing probability. If the core cannot represent this distinction, change the normalized field semantics or keep that case incomplete. Do not assign a numeric Questionable probability merely because a support article uses colloquial language.

Native `fantasy_positions` determines positional eligibility, including dual positions; primary position alone is insufficient. Sleeper [documents that eligibility may change](https://support.sleeper.com/en/articles/4298804-which-players-are-dual-eligible-on-sleeper), so freeze the metadata source/version with the batch. Do not blanket-zero IDP events on every offense-eligible player.

Actual forecast pool policy may exclude current reserve/taxi players, but this is a model choice about promotions, not a universal rule that they cannot ever play. Sleeper permits [taxi promotion](https://support.sleeper.com/en/articles/3640482-how-do-taxi-squads-work); its [Max PF guidance](https://support.sleeper.com/en/articles/4028606-do-taxi-players-count-toward-max-pf) explicitly includes taxi players. This search did not establish an equally explicit official IR/Max PF rule. Keep IR inclusion/exclusion visibly configured and do not call it exact provider replication. Distinguish fantasy reserve membership from real-NFL injury status.

## 7. Separately proposed historical-rate extension — NOT enabled

For a required linear event absent from the provider forecast, a future model could estimate a per-player rate from completed actual-event history and use a declared small/no-history prior. This would be a **derived projection source**, not provider data or a verified zero. It would require:

- A denominator based on confirmed active/played games appropriate to the forecast's participation assumption; missing rows or zero points do not prove participation.
- Observed zero events included for confirmed covered games; validated stat semantics, positions, and horizon; no current-roster reconstruction of historical availability.
- A predeclared small-sample/no-history rule and uncertainty reporting, with imputed fields and source timestamps in the manifest.
- Held-out rolling forecasts comparing missing-event error and total lineup/Max PF error with simple baselines; no future data in historical snapshots.
- Separate model/version approval and tests for interaction with the existing 60/40 historical/team blend, rather than silently double-counting or changing its meaning.

Historical direction was document-only. Subsequent user authorization permitted local experiments; the tested rare-event estimator did not improve MSE over zero and was not promoted. The bounded offense decoder is now implemented behind inactive gates; see decoder-evidence.md. Required missing rare forecasts remain explicit incomplete states.

## 8. Existing-source inspection and prototype search

Relevant existing code: `backend/season_forecasts.py` already consumes raw weekly projections, preserves date-only boundaries as dates, maintains a finite scoring registry, and maps injury-tagged players to unknown availability. `docs/feedback/items/422-win-now-ffv3-unavailable/investigation.md` documents how older offense-only restrictions and unknown-starter availability caused real refusals. This is precedent for avoiding a permanently unusable source contract, not evidence that the new model is validated. `backend/outlook/bye_weeks.py` contains an existing nflverse schedule ingestion path, but provider-native scores now supplies the needed exact timing without adding that dependency. Do not inherit its old “schedule is static” comment as a guarantee against postponements.

No original November 6 playoff-prototype package was found in the bounded search of the known visualization subtree, `/private/tmp` non-repository artifacts, or `/private/tmp/fleeced-calibration-release`. The parent has no additional exact path. The original spec exists at `/private/tmp/fleeced-calibration-release/projection-capability-original-spec.txt`; it itself says draft-order inputs were unavailable. The August/September implementations above are not relabeled as that prototype. **No original-prototype regression is claimed.**

All primary URLs above were accessed November 7, 2026 UTC. Support-page displayed dates: scoring options September 19; tackles September 21; injury statuses September 22; IR and taxi rules September 15; taxi Max PF September 23; dual eligibility September 21; AutoSubs September 15, 2026. The undocumented API observations have capture timestamps in the aggregate artifact. Commercial use rights remain unresolved and gate activation of this **new** capability only; this research makes no licensing determination or change to existing Sleeper integrations.

## New capability permission evidence

The [official API introduction](https://docs.sleeper.com/) was checked directly on November7,2026 UTC. Exact excerpt (13 words): “For commercial use of the Sleeper API, please reach out to us directly”. The same paragraph asks to discuss licensing. No agreement or permission evidence covering this new app capability’s projection/stat/schedule/scores consumption was located in this work. This is an unresolved activation gate for the new sidecar only, not a conclusion about existing app rights. No outreach occurred.
