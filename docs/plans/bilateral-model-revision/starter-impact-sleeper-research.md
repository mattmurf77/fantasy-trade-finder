# Starter-impact research — Sleeper projection lane

2026-09-22. Research only under `spec-starter-impact-research.md`; no runtime,
test, configuration, production-data or release changes. Repository source read
at local HEAD `2ed93a929c19dc1cddca06e9d521576243d04d77`. Public endpoint observations
below were captured **2026-09-22 12:03:04–12:03:06 UTC**. They are observations,
not a guaranteed API contract or historical pregame archive.

## Recommendation

Sleeper is a credible **experimental weekly stat-vector source**, with existing
local adapter infrastructure. Current public responses include useful forecasts
for both the upcoming week 3 and distant week 17. This is more encouraging than
assuming all future weeks are placeholders, but does not establish complete
remaining-season coverage for any actual league.

Use verified player-week vectors, league scoring and a separately validated
schedule to evaluate each manager's best legal lineup before/after a trade.
Aggregate only the explicitly covered remaining fantasy weeks. Keep the
season-aggregate feed as a separately labelled research source until its horizon
is confirmed: **neither divide it by 17 nor subtract actuals and call the result
ROS**. Current payloads do not establish whether it represents a refreshed
full-season estimate, actual-plus-future totals, or some other convention.

## Documented versus observable

The [official API documentation](https://docs.sleeper.com/) describes read-only,
tokenless access, with commercial use subject to contacting Sleeper about
licensing. It advises staying below 1,000 calls/minute and caching the player
directory rather than fetching it more than daily. Documented league responses
include `scoring_settings` and `roster_positions`; player records provide Sleeper
IDs, position/team and injury-related metadata. `/v1/state/nfl` distinguishes
season and week fields. The current documentation contains no projection API
section, ROS definition, projection refresh SLA or documented NFL game-schedule
contract. Do not mistake `/league/{id}/matchups/{week}`—fantasy-team matchups—for
an NFL schedule.

The projection URLs below are **observable, undocumented endpoints** on Sleeper's
own service. All enriched projection rows sampled reported `company=rotowire`;
this proves the returned provenance label, not an independent provider agreement,
forecast methodology or rights to redistribute it. Confirm that existing owner
permissions cover this projection data, retention and derivative use; no new
license or purchase was obtained. An ensemble including direct RotoWire cannot
be presumed independent of this source.

Sleeper's official [NFL SZN Picks rules](https://support.sleeper.com/en/articles/11526251-sleeper-player-picks-nfl-szn-rules)
describe an entire-season contest product. They do **not** document the semantics
of the fantasy-league projection API. Its wording must not be used to certify
these endpoints as full-season or ROS.

## Bounded public probe

Eight unauthenticated GET requests, at most two concurrent, no league/user IDs,
no credentials, no application imports, no generated trades. Sandbox DNS failed
first; that failure was retained separately. Approved public-network access then
returned seven HTTP 200 responses and one HTTP 404. The web browsing tool could
not open the JSON endpoints; direct public HTTP supplied the evidence.

In this table, **basic-stat row** means a row containing at least one of
`pass_yd`, `rush_yd`, `rec_yd`, `rec`, `pass_td`, `rush_td`, `rec_td`. This is a
counting definition, not proof of scoring completeness, health or eligibility.

| Primary endpoint | Observed response | Interpretation limit |
|---|---|---|
| [State](https://api.sleeper.app/v1/state/nfl) | `season=2026`, `season_type=regular`, `week=3`, `display_week=2`, `season_has_scores=true` | Different week fields coexist; neither supplies a game's exact kickoff or sufficient live-week eligibility rule. |
| [2026 season map](https://api.sleeper.app/v1/projections/nfl/regular/2026) | 9,421 ID-keyed stat objects; 559 basic-stat rows | The large row count is not 9,421 useful player forecasts. This shape lacks per-row source timestamps and player metadata. |
| [2025 season map](https://api.sleeper.app/v1/projections/nfl/regular/2025) | 9,297 objects; 553 basic-stat rows | Historical accessibility is not proof of an archived pregame version. |
| [2026 enriched season](https://api.sleeper.app/projections/nfl/2026?season_type=regular&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE&order_by=pts_ppr) | 3,116 rows; 559 basic-stat rows; `category=proj`, `week=null`, `game_id=season`, no opponent/date | All 559 had `gp=18.0`, including after the first two weeks. `gp` is therefore not a validated count of remaining player games. All 3,116 enriched stat objects matched their corresponding current-season map objects by parsed JSON value. |
| [2026 week 3](https://api.sleeper.app/projections/nfl/2026/3?season_type=regular&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE&order_by=pts_ppr) | 3,116 rows; 406 basic-stat rows with game/opponent; 2,705 ADP-only rows | Dates September 24–28. One basic-stat row had all seven counted stats zero. This is distinct from ADP-only/missing data. |
| [2026 week 17](https://api.sleeper.app/projections/nfl/2026/17?season_type=regular&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE&order_by=pts_ppr) | 3,116 rows; 442 basic-stat rows with game/opponent; 2,670 ADP-only rows | Dates December 31–January 4. Future-week forecasts exist today, but only this one distant week was sampled. |
| [2025 week 1](https://api.sleeper.app/projections/nfl/2025/1?season_type=regular&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE&order_by=pts_ppr) | 3,116 rows; 356 basic-stat rows | All 356 dated stat rows had source updates after their game dates; these are not certified pregame forecasts. |
| [Attempted NFL schedule path](https://api.sleeper.app/schedule/nfl/regular/2026/3) | HTTP 404 | This was an exploratory path, not a documented endpoint. One failed path does not prove Sleeper has no schedule API. No alternative schedule route was guessed or probed further. |

Concrete season example: Josh Allen (`4984`) had `pass_yd=3650`, `pass_td=27`,
`rush_yd=535`, `pts_ppr=361.5`, `gp=18.0`, with source update
`2026-09-22T07:51:16.249Z`. The row has no remaining-week start, forecast cutoff,
actual/projected split or return-to-play probability. These values establish a
season-scoped aggregate, **not its full-season-versus-ROS interpretation**.

## Weekly data and league scoring

Observed enriched fields include `player_id`, `season`, `season_type`, `week`,
`category`, `company`, `team`, `opponent`, `game_id`, `date`, `updated_at`,
`last_modified`, `stats`, and nested player position/injury metadata. Player IDs
are strings and join directly to Sleeper rosters. Fantasy-position eligibility
and primary position are separate fields; preserve both. There was no exact
kickoff timestamp or explicit participation probability in the sampled schema.

Weekly stat keys included passing attempts/completions/yards/TD/interceptions,
rushing and receiving events, first downs, reception-distance buckets, fumbles,
returns and some position bonus counts. The filtered probe covered QB/RB/WR/TE,
not complete K/DEF/IDP projection support. Presence of isolated IDP keys on an
offensive player's row does not establish an IDP forecasting product. `adp_*`
and `pts_std`/`pts_half_ppr`/`pts_ppr` are not substitutes for the required event
vectors or the league's own rules.

Sleeper documents customizable scoring, overlapping event categories and
non-stacking distance/milestone ranges. A league-specific scorer must implement
those actual rules; a threshold bonus generally cannot be evaluated by applying
the threshold to a mean yardage forecast. It needs the expected bonus event or
a justified outcome distribution. Unsupported enabled categories must be explicit.
[Official scoring categories](https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available).

Position reception bonuses stack with base PPR and use the player's primary
position, not the slot in which they start. Thus a TE in FLEX retains TE reception
premium; a multi-position player does not receive both premiums. SF/2QB changes
legal lineup slots, not a player's points by itself.
[Official reception-bonus semantics](https://support.sleeper.com/en/articles/3652730-how-are-reception-bonuses-calculated).

**Unresolved provider semantics:** no official projection specification found
defines whether omitted stat keys imply zero, or whether projected events are
conditional on playing versus already adjusted for expected availability. Do
not multiply by an invented availability probability, or silently zero an
enabled scoring category, without resolving that contract. Current injury
labels do not provide a week-specific return schedule: week 17's basic-stat rows
included 18 `IR`, 43 `Out` and 15 `Questionable` labels alongside projected stats.
Missing injury metadata is not positive evidence of certain participation.

## Schedule, byes and horizon

The projection payload's team/opponent/game/date can corroborate a scheduled
game, but missing rows/opponents do not independently establish a bye. The
existing `backend/outlook/bye_weeks.py:74` derives byes from regular-season
schedule coverage using [nflverse's primary schedule data](https://github.com/nflverse/nfldata/blob/master/data/games.csv),
with `LA`→`LAR` normalization. Its general cache has last-good/bundled fallbacks
(`:130`); a new evidence-bearing starter-impact pipeline must require a verified
current-season schedule and explicit freshness/completeness, rather than treating
a fallback's existence or a missing game as certification. No live nflverse CSV
was fetched in this lane, and no new schedule accuracy claim is made.

A verified bye means that player cannot contribute that week, **not that the
team's starter slot must score zero**. Reoptimize from eligible bench players,
including FLEX/SF assignments, before computing the bilateral delta. Distinguish
confirmed bye/inactive, projected numerical zero, missing player-week, unsupported
scoring and unknown health. The horizon must follow the league's actual remaining
regular-season/playoff scoring weeks and exclude completed/live-ineligible games.
Do not subtract an extra bye after summing schedule-aware weekly lineups.

No ROS-specific Sleeper endpoint or documented ROS contract was verified. A
defensible Sleeper-derived ROS estimate is therefore the sum of complete,
as-of-frozen future weekly lineup evaluations, labelled as that derivation—not
a claim that Sleeper supplied a separate ROS forecast. This probe did not fetch
all weeks 3–18, check any live league's roster coverage, or validate accuracy.

## Freshness, failure and historical use

Observed HTTP headers are cache hints, not projection SLAs. Current season/weekly
responses used shared-cache `s-maxage=600`; enriched responses also allowed
600-second stale-while-revalidate and stale-if-error periods. The historical
weekly response used `s-maxage=3600`. An ETag and HTTP Date identify transport
state, not when the forecast first became knowable. `updated_at` and
`last_modified` matched in inspected examples; preserve them separately from
our actual fetch-completion time and raw content hash.

Week 3's source revisions were near `2026-09-22T12:01:03Z`, while week 17's were
near `2026-09-21T23:45:58Z`. A single fetch does not prove cadence or a refresh SLA.
The historical week-1 example was revised on October 6, 2025, after September
games, consistent with the previously retained local
`docs/plans/win-now/historical-source-probe-2026-09-04.json`. Use historical URLs
for schema/reconciliation only unless an independently captured pregame snapshot
exists. Provider update dates must never backdate our evidence.

Transport/schema failures, unexpected horizons, duplicate player-week identities,
absent source timestamps and required missing projections should produce explicit
unsupported/stale evidence. Proposed refresh work should cache globally by
provider/season/week/schema, then derive league-scored snapshots separately;
avoid per-card or per-manager network requests. Bounded retries/backoff and
last-good storage are reasonable, but an expired last-good response must not be
silently relabelled current. No 429 behavior, outage fallback or rate-limit
boundary was stress-tested, and no numerical timeout/TTL is validated here.

## Reuse and one next implementation boundary

The existing `backend/season_forecasts.py:212` already uses the observed enriched
weekly URL; it rejects mismatched horizons and ADP-only placeholders, retains
source provenance and allows independently certified bye rows. The normalized
import at `:110` and scorer at `:302` are useful seams; fixtures in
`backend/tests/test_season_forecasts.py` already cover missing-week versus bye,
unsupported scoring and historical-as-of honesty. No tests were run in this lane.

Two existing assumptions need an explicit source-contract decision before reuse:
`:276` treats no injury string as availability `1.0`, and the scorer uses
`stats.get(key, 0.0)` for permitted categories. Also, `:288` stores the latest row
update as snapshot `published_at`; that is not proof every row is equally fresh
or that this whole snapshot existed at that time. Preserve per-row age and
capture time when defining acceptance.

The smallest next step is a **prospective, read-only coverage-and-scoring
snapshot job**, reusing the provider-neutral importer. For one explicitly chosen
season/remaining horizon, freeze source bytes, source/capture timestamps, schedule
version, player identities, stat support and league-scoring version; then report
coverage/unknowns for both pre/post-trade rosters before enabling ranking effects.
Acceptance needs complete contributor coverage, legal bench replacement, exact
league scoring, bye/injury/missing controls and genuine pregame retention.
Dynasty market value and picks remain separate future-value evidence, never
fabricated weekly points. Parent's combined plan owns implementation scope,
rights confirmation, accuracy evaluation and rollout.

## Reproducible private evidence

Artifacts are local research captures, not repository fixtures or public
redistribution: `/private/tmp/starter-sleeper-research-20260922.BslPr2/`.
`probe.py` makes the eight allowlisted GETs and records each exact URL, status,
completion timestamp, raw-body SHA256, cache headers and summary; `analyze.py`
performs only local JSON analysis. Successful raw responses are retained as
`*.response.json`; the initial DNS failures are in `sandbox-network-failure.json`.

- Probe script SHA256: `ce3846a0f9086356bf6cc93722d8fdacf5c6cdfdfd20ba85a9bc7c5fbddc948e`.
- Complete manifest SHA256: `2bf5a4f14ad31f0a3028e63ddc2d38417445918432bdf290c05d4edfcbe8c1b8`.
- Local analysis SHA256: `8deff743ce6d858974f37be0a5e10a99e2becdf396d25d2e76946b55c32f6655`.
- Current season enriched raw SHA256: `51eb50167944eec3ebd7b8495cff0a7e90a6caa345346446be7cc36f7a237ccc`.
- Week 3 raw SHA256: `b64023b8f19d6b62d6349f89a5d461dcb3cbd42f75dfbc818a7f5f1bcb8518f2`.
- Week 17 raw SHA256: `8789fcb71f08c66df7ae9379c5e739a3545c1264906fe68039548ac3a1a90422`.
- Historical week 1 raw SHA256: `2d719a474b26b8b1d6884624aabc1a6ba5acf3e632ba9f7edd68a14995472f29`.

Only this research Markdown was added to the worktree by this lane. All other
worktree changes belong to their respective agents/release owner.
