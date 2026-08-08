# ESPN auto-derived rookie draft order — feasibility research

> **RESOLVED + BUILT (2026-08-08).** Every open question below is closed and the
> feature shipped. The §6d fork was settled by the operator (inverse
> regular-season standings for non-playoff teams; `rankCalculatedFinal` for
> playoff teams only) — that ruling is recorded verbatim at the end of §6 and
> in [plan.md](plan.md) § "Operator decision — ESPN auto-derived draft order".
> The build, its exact tiebreak chain and its refusal conditions are in
> [build-espn-auto-order.md](build-espn-auto-order.md); the code is
> `espn_service.derive_espn_draft_order`, surfaced as `suggested_order` on
> `GET /api/league/pick-assignments`.
>
> **Two §1.5/§4 recommendations were deliberately NOT followed** (rationale in
> the build doc §5): no new table or route — the suggestion is a transient
> field on the shipped payload, so nothing about "ESPN never writes rows" is
> touched — and no new flag, because this changes a DEFAULT inside the already
> flag-gated `picks.assign` flow rather than adding surface.
>
> This document is kept as the evidence record. Nothing below was edited.

**Date:** 2026-08-08 (updated same day with live probe, §6) · **Status:** research only, no code written · **Author:** research agent (delegated)

**Question:** can FTF automatically derive next season's rookie draft order for
an ESPN league from ESPN's own league-history/standings data — non-playoff
teams in inverse regular-season order (worst picks first), playoff teams
ordered by playoff finish (champion picks last), ties broken by inverse
regular-season standings — well enough to pre-assign rookie draft picks to
teams without the user doing it by hand?

---

## Summary verdict

| Data need | Verdict | Source |
|---|---|---|
| Final regular-season standings (record, points, rank) | **FEASIBLE — live-confirmed** | `mTeam` view → `teams[].record.overall`, `teams[].playoffSeed`, `teams[].rankCalculatedFinal`; verified live 2026-08-08 against real league 11896 (§6) |
| Playoff bracket / final finish (who won it, who finished 2nd, etc.) | **FEASIBLE for playoff teams — live-confirmed champion=1** | `rankCalculatedFinal` matched an independently-reconstructed real bracket exactly for all 6 playoff teams in league 11896 (§6c); no manual bracket-parsing needed in code |
| Non-playoff-team ordering (regular season vs. ESPN's own consolation-ladder finish) | **NEW OPEN DECISION — the two methods disagree** | `rankCalculatedFinal` reflects ESPN's played consolation ladder, not pure inverse regular-season standing, when a league runs one; disagreed on 5 of 8 non-playoff teams in league 11896 (§6d) — FTF must choose and label which definition it uses |
| Traded-pick awareness (so a derived order isn't wrong when picks changed hands) | **NOT FEASIBLE — live-confirmed** | ESPN's v3 API carries no persistent future-draft-pick-ownership model for dynasty leagues (confirmed by our own prior spike, `docs/plans/espn-league-linking-plan-2026-07-11.md` §2, `#158`, and live probe §6e) |

**Bottom line:** the *inputs* to compute a default rookie-draft order (final
record, playoff seed, and — with moderate extra work — playoff bracket
finish) are readable from ESPN's unofficial API for a league we're already
allowed to read (public, or private with the user's `espn_s2`/`SWID`
cookies). **FTF would have to compute the order itself** — ESPN does not
expose a "next season's rookie draft order" field, because ESPN's own game
has no draft-pick-trading ledger for dynasty leagues and treats each
season's draft order as a manually-set league setting, not a derived
value. A derived order is therefore only ever a **default proposal**, and
because FTF has no way to see if picks were traded on ESPN, **any league
that trades picks must get a manual override path** — this is not an edge
case to handle later, it is the normal case for an engaged dynasty league.

Recommended approach: compute the order server-side in `espn_service.py` (or
a new small module) from a live `mTeam` (+ playoff-bracket) read, store it as
a **pre-fill/default** the commissioner/user can freely reorder or override
per-pick, never as ground truth. This mirrors the pattern FTF already uses
for MFL/Fleaflicker gaps (§below) and is consistent with the project's
existing "ESPN carries no future-pick ownership" stance (#158).

---

## 1. Current-state codebase findings

FTF already has a working, flag-gated, read-only ESPN integration. Nothing
in it currently reads standings, playoff results, or draft order — it reads
rosters only.

### 1.1 What we already call

- `backend/espn_service.py:87-91` — `league_url()` builds:
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}?view=mTeam&view=mRoster&view=mSettings`
  — **only `mTeam` + `mRoster` + `mSettings`**. No `mStandings`,
  `mMatchupScore`, `mBoxscore`, or `mDraftDetail` view is requested anywhere
  in the codebase today (`grep` for those tokens across `backend/` and
  `docs/` returns nothing except unverified mentions in planning docs — see
  §1.4).
- `backend/espn_service.py:94-134` — `fetch_league()` is the only live HTTP
  call; auth is a `Cookie: espn_s2=…; SWID=…` header when both cookies are
  supplied, else an unauthenticated request (public leagues). 401/403 →
  `EspnAuthError`; 404 → `EspnError(kind="not_found")`.
- `backend/espn_service.py:157-194` — `parse_league()` currently extracts
  only `id`, `settings.name`, `seasonId`, `settings.size`, and
  `teams[]` → roster entries. It does **not** touch `teams[].record`,
  `teams[].playoffSeed`, `teams[].rankCalculatedFinal`/`rankFinal`, or
  anything schedule-shaped. Adding standings/playoff extraction would extend
  this function (or a sibling), not replace it.
- `backend/espn_service.py:352-404` (`map_rosters`) / `421-470`
  (`map_generic_rosters`) — the DynastyProcess crosswalk that turns ESPN
  `playerId`s into FTF's Sleeper-space `player_id`s. Not relevant to
  standings but relevant context: this is the *only* place ESPN ids get
  translated into FTF's id space today.

### 1.2 Auth model

- `backend/database.py:1213-1246` — `espn_credentials_table`: one row per
  FTF `user_id`, storing `swid` (plaintext — it's an identifier, not a
  secret) and `espn_s2_encrypted` (Fernet ciphertext). Sourced from a manual
  paste of the user's own espn.com session cookies (`docs/plans/espn-league-linking-plan-2026-07-11.md` §4)
  — there is no OAuth, because ESPN's fantasy API has none.
- `backend/database.py:8079-8145` — `upsert_espn_credential` /
  `get_espn_credential` / `delete_espn_credential`.
- Public leagues need no cookies at all; private leagues need **both**
  cookies (`backend/server.py:15481-15499` enforces "both or neither").
  Cookie lifetime is undocumented by ESPN; the existing plan treats `espn_s2`
  as ~1-year-lived and `SWID` as effectively permanent, and handles 401 as
  "reconnect," same posture as the 365-day Sleeper JWT.

### 1.3 What we already store about ESPN leagues

- `backend/database.py:239-251` — `leagues` table gained `platform`,
  `espn_season`, `espn_auth`, `espn_my_team_id` columns (Phase 1, #101).
  **No standings/finish/draft-order columns exist.**
  `espn_season` is the re-sync key (the season the link was imported
  against); it is **not** validated against ESPN's own `seasonId` beyond
  what `parse_league()` returns.
- `backend/database.py:8284-8317` — `replace_espn_league_members` /
  `load_espn_leagues_for_user` — replace the whole roster snapshot on every
  import/re-sync; no historical/per-season row is kept, so there is
  currently no way to look back at "last season's" ESPN standings from our
  own DB — only from a fresh ESPN read against the prior `seasonId`.
- `backend/database.py` — `draft_picks` table: the comment at
  `backend/database.py:716` reads *"#158: 'sleeper' | 'mfl' provenance
  (ESPN never writes rows)"*. `backend/server.py:7776,7780,8485,15772`
  (the `picks_supported = platform != "espn"` guard, repeated at several
  call sites) confirms ESPN leagues are **structurally excluded** from FTF's
  pick-ownership model — there is no ESPN row ever written to
  `draft_picks`, by design, because ESPN's API surfaces no traded-pick
  ledger to sync from.

### 1.4 Where prior FTF research already touched this exact question

Two documents in this repo already did adjacent legwork and are the most
relevant prior art:

- `docs/plans/espn-league-linking-plan-2026-07-11.md` — the original ESPN
  go/no-go. §2's "Feature matrix" already states the pick-ownership gap:
  *"ESPN dynasty/keeper leagues don't expose tradeable future picks the way
  Sleeper's `traded_picks` endpoint does. `draft_picks` stays empty for ESPN
  leagues."* This is the single strongest piece of internal evidence for the
  "traded-pick awareness = NOT FEASIBLE" verdict above — it was already
  concluded, independently, by the original integration spike.
- `docs/feedback/items/207-rookie-draft-detection/research-platforms.md`
  (2026-08-05) — researched a related-but-different question (has THIS
  season's rookie draft already happened, for pick-hiding purposes) and
  flagged `view=mDraftDetail` (`draftDetail: {drafted, inProgress, picks[]}`)
  as **documented but never verified live** — no valid public ESPN league id
  was on hand during that research pass either. It explicitly says "do not
  build on it" until verified. `mDraftDetail` is about the *current* draft's
  completion state, not next season's draft order, but it is the closest
  existing probe to "append one more `view=` token to the read we already
  make," and the verification gap it identified (no real ESPN league to test
  against) applies equally to `mStandings`/`mMatchupScore` for this feature.
- `docs/plans/draft-extensions/plan.md` §0 point 6 — independently names the
  free `mDraftDetail` probe as "the highest-leverage half-day available" —
  i.e. the team has already decided this class of verification spike is
  worth doing, just hasn't done it yet for any ESPN view.

### 1.5 Where draft-order derivation would naturally live

- **Fetch:** extend `espn_service.league_url()`'s `view=` list (adding
  `mStandings` and/or `mMatchupScore`/`mBoxscore` costs no extra HTTP
  request — same lesson as the `mDraftDetail` note above: ESPN's `view=` is
  additive on one GET).
- **Parse:** a new function alongside `parse_league()` in
  `backend/espn_service.py`, e.g. `parse_standings(raw) -> list[dict]`
  returning `{team_id, wins, losses, ties, points_for, playoff_seed,
  rank_calculated_final, made_playoffs}` per team — mirroring how
  `parse_league()` already normalises `mTeam`/`mRoster` into a stable shape
  before anything downstream touches it.
- **Compute:** a small, pure, platform-agnostic ordering function (no ESPN
  types leaking past this boundary) that takes normalized standings +
  playoff results and returns `[team_id, ...]` in draft-pick order —
  this is genuinely platform-agnostic logic (Sleeper/MFL could feed the
  same function from their own standings data later) and belongs in a
  neutral module, not `espn_service.py` itself.
- **Persist / expose:** a new nullable set of columns or a small side table
  (there is no existing "season standings" table — `leagues`/
  `league_members` only carry current snapshots), plus a route under
  `/api/espn/*` (flag-gated behind `espn.link`, same as every other ESPN
  route) that returns the *proposed* order for the commissioner to accept,
  edit, or discard. This should **not** write into `draft_picks` directly
  given that table's "ESPN never writes rows" invariant — either that
  invariant is revisited as part of this feature, or the proposed order
  lands in a separate table that a manual "apply as pick order" action
  copies into whatever pick-tracking surface the rookie-draft feature
  (`docs/plans/rookie-draft/`) ends up using for ESPN (currently: none —
  ESPN has no pick model in FTF at all, per `docs/plans/rookie-draft/plan.md`
  line 35 and `docs/glossary.md`).

---

## 2. External research — ESPN v3 API fields

All of the following is the **unofficial**, community-reverse-engineered v3
API (`lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/...`) — there is no
official ESPN fantasy developer API (retired 2014). Sources cited per row;
none of this was re-verified live against a real ESPN league by this
research pass (no valid ESPN league id/cookies were available in this
session) — same limitation the #207 research doc already flagged for
`mDraftDetail`. Live verification against a real league before relying on
any of it in production code is a hard prerequisite, consistent with the
project's own stated practice ("verify live before trusting it," #207 doc
§6.4).

| Need | View | Field path | Status | Source |
|---|---|---|---|---|
| Final W-L-T record | `mTeam` | `teams[].record.overall.{wins,losses,ties,pointsFor,pointsAgainst}` | Documented, matches our own already-verified `mTeam` usage | [Thomas Wilde — League Info JSON Views](https://thomaswildetech.com/projects/espn/league-info-json-views/); our own live-verified `espn_service.py` calls `mTeam` already |
| Regular-season/pre-playoff seed | `mTeam` | `teams[].playoffSeed` | Documented | Thomas Wilde, same page |
| Final overall rank (post-playoffs) | `mTeam` | `teams[].rankCalculatedFinal` | Documented | Thomas Wilde, same page |
| Pre-final/point-in-time rank | `mTeam` | `teams[].rankFinal`, `teams[].currentProjectedRank` | Documented | Thomas Wilde, same page |
| Draft-day baseline rank (context only) | `mTeam` | `teams[].draftDayProjectedRank` | Documented | Thomas Wilde, same page |
| Season-long projected standings | `mStandings` | `teams[].currentSimulationResults.{divisionWinPct, playoffPct, rank, modeRecord}` | Documented — this is ESPN's *projection*, not the actual final result; use `mTeam.rankCalculatedFinal` for the real final finish, not this | Thomas Wilde, same page |
| Playoff bracket type per matchup | `mMatchupScore` (schedule) | `schedule[].playoffTierType` ∈ `{NONE, WINNERS_BRACKET, LOSERS_CONSOLATION_LADDER, ...}` | Documented (also present in the community Python library's `box_score.py: matchup_type = data.get('playoffTierType', 'NONE')`) | web search results citing the schedule JSON shape; [cwendt94/espn-api `box_score.py`](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/box_score.py) |
| Computed final league standing (post-tiebreakers, post-playoffs) | n/a (library-level, not a raw ESPN field) | `Team.final_standing` in the community Python library, derived by the library from the raw payload, used to sort `league.standings()` | Documented in library source | [cwendt94/espn-api `league.py`](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/league.py) — `standings = sorted(self.teams, key=lambda x: x.final_standing if x.final_standing != 0 else x.standing, ...)` |
| A next-season draft order ESPN itself computed | — | **Does not exist as an API concept.** ESPN's own product treats each season's draft order as a manually-set league setting a commissioner edits (via "Edit Draft Order" in league settings), not a value ESPN derives from prior standings. There is no field to read a "system-derived next-season order." | Not documented anywhere found; consistent with ESPN's redraft/keeper-first design (dynasty rookie drafts are a community convention layered on top, not a native ESPN concept) | ESPN support docs on draft settings; absence of any endpoint/field reference across every source consulted |
| Traded future draft picks (dynasty pick ledger) | `mTransactions2` / `mPendingTransactions` | Exists for **in-season transactions** (adds/drops/trades of *players*, and of the *current* draft's picks pre-draft per ESPN's "Draft Pick Trades" feature) but **no persistent multi-season future-pick ownership object** analogous to Sleeper's `traded_picks` was found for ESPN. This matches our own prior finding. | ESPN support article on Draft Pick Trades describes trading picks **within the current/upcoming draft only** ("until one hour before your draft"), not a standing ledger of e.g. "2027 1st" as a tradeable asset across seasons | [ESPN Support — Draft Pick Trades](https://support.espn.com/hc/en-us/articles/360000141091-Draft-Pick-Trades); [ESPN Support — Trade Draft Picks](https://support.espn.com/hc/en-us/articles/360046052292-Trade-Draft-Picks); corroborated by `docs/plans/espn-league-linking-plan-2026-07-11.md` §2 ("Gap. ESPN dynasty/keeper leagues don't expose tradeable future picks") |
| Prior-season access | `leagueHistory` endpoint | `https://fantasy.espn.com/apis/v3/games/ffl/leagueHistory/{league_id}?seasonId={year}` (pre-2018 seasons) vs the normal `.../seasons/{year}/segments/0/leagues/{id}` path (2018+, works for any past season by substituting `{year}`) | Documented, and **our own repo already probed this** — see next row | [ffscrapr `espn_getendpoint` vignette](https://ffscrapr.ffverse.com/articles/espn_getendpoint.html); [Onyx Mueller blog](https://onyxmueller.net/2022/12/28/accessing-fantasy-football-data-through-espns-api/) |
| Prior-season auth/permission constraints | — | Same cookie model as the current season (public → no auth; private → `espn_s2`+`SWID`); **but ESPN purges old league data.** Our own plan doc's live probes (2026-07-11) found three known historical public test-league ids **all 404 on both the season and `leagueHistory` endpoints** — confirmed empirically, not just documented | `docs/plans/espn-league-linking-plan-2026-07-11.md` §1, "Data purging" row, "Live probes run for this plan" — **our own verified data**, most authoritative source in this table |

---

## 3. Constraints & risks

1. **Authentication / cookie expiry.** Private leagues need `espn_s2` +
   `SWID` pasted from a logged-in espn.com session; no OAuth exists. `espn_s2`
   is community-consensus ~1 year lived, undocumented officially. A
   draft-order derivation that runs once a year (end of season) is exactly
   the cadence most likely to hit a stale/expired cookie — the commissioner
   would need to re-link right when the feature is needed most. FTF already
   handles 401→"reconnect" gracefully for the existing read path; the same
   handling covers this.
2. **Rate limits / ToS.** No published rate limits; unsanctioned scraping of
   a Disney property (zero contractual protection, low practical
   enforcement per our own prior research). Deriving draft order needs at
   most one extra `view=` token on an existing GET — negligible incremental
   load.
3. **Unofficial/undocumented API stability.** The v3 API has already had one
   breaking host migration (`fantasy.espn.com` → `lm-api-reads.fantasy.espn.com`,
   2023→2024) that silently broke every third-party client until they
   chased it. ESPN could rename/remove `playoffTierType`,
   `rankCalculatedFinal`, or the whole standings shape with no notice.
   Any derivation built on this needs the same "kill switch" posture FTF
   already applies to `espn.link` overall (`backend/feature_flags.py:143-147`).
4. **League ID continuity year over year.** Based on the endpoint shape
   (`.../seasons/{year}/segments/0/leagues/{league_id}` — the numeric id is
   NOT year-scoped), an ESPN league keeps the **same** `league_id` across
   seasons, and you swap only the `{year}` segment. This is favorable for
   auto-derivation: FTF can re-query the *same* linked `league_id` at
   `season - 1` to pull last year's final standings, exactly the pattern our
   own `espn_season` re-sync key already assumes. However our own probes
   also show ESPN **purges old leagues outright** (three known historical
   test-league ids all 404, both on the plain season endpoint and
   `leagueHistory`) — so "same id works forever" is not guaranteed; expect
   an unpredictable purge window, not a documented retention policy.
5. **First-season leagues (no history).** A league linked in its inaugural
   ESPN season has no prior `mTeam` standings to read — derivation must fail
   soft (no proposed order, not a crash) and fall back to manual entry,
   same posture as every other "insufficient data" branch in FTF's
   platform-linking code (`EspnError`/`_espn_error_response`).
6. **Non-standard playoff formats.** ESPN itself documents that playoffs
   split into a Winner's Bracket (playoff-teams-count) and a Consolation
   Ladder for everyone else, with byes possible for top seeds and — per
   ESPN's own settings — configurable bracket sizes (4/6/8 teams) and
   optional two-week championship. Reconstructing "who finished where" from
   raw `schedule[]` + `playoffTierType` entries for every one of these
   shapes is real work, not a lookup — this is the single largest
   engineering unknown in this whole feature, bigger than the standings
   piece. `mTeam.rankCalculatedFinal` may already do this reconstruction
   for us (it's described as ESPN's own final computed rank, post-playoffs,
   post-tiebreakers) — if verified accurate, it would sidestep needing to
   parse the bracket ourselves at all. **This is the single most
   important thing to verify live before scoping the feature**, because if
   `rankCalculatedFinal` really is correct, "playoff finish" collapses from
   PARTIAL to FEASIBLE via one field, and if it isn't, bracket
   reconstruction becomes the majority of the build.
7. **Co-owned / orphan teams.** ESPN teams can have multiple owners
   (`owners[]`, not just `primaryOwner`) and can go inactive/orphaned
   mid-season (a team with no active manager). FTF's existing `parse_league()`
   already only reads `primaryOwner`/first `owners[0]` for the current
   roster import — the same simplification would need re-examining for
   "who does this draft slot actually belong to," since an orphaned team's
   draft slot is exactly the case where a league most needs a human,
   not an algorithm, to decide what happens.
8. **A derived order is a default, not a fact, given traded picks are
   invisible.** This is the load-bearing risk of the whole feature: FTF
   cannot see ESPN dynasty pick trades at all (§2 above, and #158). Any
   league that has traded a rookie pick — extremely common in active
   dynasty leagues — will have a *wrong* auto-derived assignment for that
   slot unless a human corrects it. The feature is only honest if every
   slot is user-editable before anything downstream (trade suggestions,
   pick values) treats it as truth.

---

## 4. Recommended approach

1. **Spike first, scope second.** Before writing the ordering algorithm,
   run one live smoke test against a real ESPN league (public if possible,
   else the operator's own private league with cookies from
   `secrets.local.env`) requesting
   `?view=mTeam&view=mStandings&view=mMatchupScore` for a completed season,
   and record: (a) does `rankCalculatedFinal` actually match the league's
   real final standing including playoff results, and (b) what does
   `schedule[]` actually look like for `playoffTierType` across a real
   bracket. This single spike resolves the biggest open unknown in §3 point
   6 and should gate scoping the rest of the feature — same discipline the
   team already applied to the `mDraftDetail` probe (`docs/plans/draft-extensions/plan.md` §0.6, S-1).
2. **If `rankCalculatedFinal` is verified correct:** the whole "final finish"
   computation is one field read per team — dramatically simpler than
   reconstructing the bracket manually. Non-playoff teams still need to be
   separated from playoff teams and inverse-sorted on regular-season record
   (`playoffSeed` or `record.overall`) per the stated rule; playoff teams
   sort by `rankCalculatedFinal` descending-picks-last (champion picks
   last).
3. **If not verified/reliable:** fall back to reconstructing the bracket
   from `schedule[].playoffTierType` + matchup winners — materially more
   engineering, and should be scoped as its own increment, not bundled into
   a first release.
4. **Ship it as a default-with-required-review, never silent truth.** Land
   behind the existing `espn.link` flag (or a child flag), surfaced as "here's
   a proposed pick order based on last season — review before your draft,"
   with every slot manually reassignable. This is consistent with how the
   ESPN integration already treats every gap (pick ownership, mutual
   matching) — degrade to a clearly-labeled manual step rather than guess
   silently.
5. **Do not write into `draft_picks` for ESPN.** Keep the proposed order in
   its own table/response shape so the `platform != "espn"` /
   "ESPN never writes rows" invariant elsewhere in the codebase (#158)
   stays true; whatever picks/rookie-draft UI eventually consumes ESPN pick
   order should read from this new surface explicitly, not assume
   `draft_picks` has ESPN rows.
6. **Handle the no-history and purge cases identically:** both mean "we have
   no data to propose an order from" — fail soft to an empty/manual state,
   never block the user from setting the order by hand.

---

## 5. Open questions

1. Does `mTeam.rankCalculatedFinal` actually reflect the true post-playoff
   final standing, or is it a mid-season-updating projection that happens to
   equal the final result only once the season ends? Unverified — the #1
   blocker to scoping precisely (§3.6, §4.1).
2. What are ESPN's actual `playoffTierType` enum values beyond
   `WINNERS_BRACKET`/`LOSERS_CONSOLATION_LADDER`/`NONE`? Is there a distinct
   value for a two-week championship's two legs, or do both weeks share one
   tier type distinguished only by `matchupPeriodId`?
3. How does ESPN represent byes for top playoff seeds in `schedule[]` —
   a real skipped week, or a synthetic auto-win matchup? This affects
   whether "who advanced" can be read purely from `winner` fields.
4. Confirm whether `league_id` truly never changes year over year for a
   continuously-active league (strongly implied by the URL shape and by our
   own `espn_season` re-sync design, but not independently confirmed against
   a multi-year-old real league in this pass).
5. Does ESPN's `mTransactions2`/`mPendingTransactions` carry *any* signal
   about picks changing hands even informally (e.g. a logged trade
   transaction whose assets include a future pick token), or is that
   entirely absent? If even partially present, it could downgrade "traded
   pick awareness" from NOT FEASIBLE to PARTIAL for leagues that use ESPN's
   own (redraft-scoped) draft-pick-trade feature. Not found in any source
   consulted this pass — worth a targeted live probe alongside the
   `mDraftDetail`/`mStandings` spike in §4.1.
6. Co-owned-team draft-slot assignment policy — out of scope for this
   research, but the eventual PRD needs an explicit rule (e.g. "assign to
   `primaryOwner`, same as roster import does today").

---

## 6. Live probe — league 11896 (2026-08-08)

**Method:** unauthenticated `GET` requests via `curl` against ESPN's public v3
API, no cookies, no FTF code touched, no database queried. League id
supplied directly by the operator (real league, `Newton Dynasty League`, 14
teams, `playoffTeamCount: 6`). Raw responses saved to local scratch files
during the probe and not committed. This closes the verification gap
Open Question #1 (and the whole §4.1 spike) called out above.

### a) Does 2025 data come back?

**OBSERVED — yes, cleanly.**

- `GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leagues/11896?view=mTeam&view=mStandings&view=mSettings`
  → **HTTP 200**, 79 KB JSON body, `seasonId: 2025`, `settings.name: "Newton
  Dynasty League"`, `status.currentMatchupPeriod: 17`,
  `status.finalScoringPeriod: 17` (season complete), `status.previousSeasons:
  [2014..2024]` (11 prior seasons exist and are enumerated by ESPN itself).
- `GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/leagueHistory/11896?seasonId=2025`
  → **HTTP 404** (`"messages":["Not Found"]`). The `leagueHistory` path form
  does **not** work for the current/most-recent season in this league — only
  the plain `seasons/{year}/segments/0/leagues/{id}` form worked for 2025.
  (This is consistent with community docs describing `leagueHistory` as a
  path for *past* seasons relative to the league's current season, not an
  alternate route to the current one — not itself evidence of purging.)

This directly answers the operator's stated need: **2025 season data is
retrievable today, unauthenticated, for league 11896.** Earlier-season
purging risk (§2, `leagueHistory` row) is unresolved either way — not tested
against 2014–2024 for this league in this pass — but is explicitly a
future/nice-to-have per the operator's scoping, not blocking.

### b) Which fields are present and populated (`mTeam` + `mStandings` + `mSettings`)?

**OBSERVED**, all 14 teams, real values:

| Field | Present? | Populated? | Notes |
|---|---|---|---|
| `record.overall.{wins,losses,ties,percentage,pointsFor,pointsAgainst}` | Yes | Yes, all 14 teams | e.g. team 14 "Stinky Fingers": 12-2-0, .857, 2040.65 PF |
| `playoffSeed` | Yes | Yes, all 14 teams, values 1–14, no duplicates | Matches regular-season order derivable from `record.overall` |
| `rankCalculatedFinal` | Yes | Yes, all 14 teams, values 1–14, no duplicates | See (c) — this is the field the memo flagged as the #1 unknown |
| `rankFinal` | Present as a key | **`0` for every team** | Not populated for a completed 2025 season — do not use |
| `currentProjectedRank` | Present as a key | **`0` for every team** | Not populated post-season — do not use |

Real per-team values (id, name, W-L, playoffSeed, rankCalculatedFinal):

| id | Team | W-L | playoffSeed | rankCalculatedFinal |
|---|---|---|---|---|
| 14 | Stinky Fingers | 12-2 | 1 | 3 |
| 5 | The Humongous Melonheads | 11-3 | 2 | 4 |
| 13 | Black Lives Matter | 10-4 | 3 | **1** |
| 6 | Bucky Charms | 9-5 | 4 | 2 |
| 4 | Hail Mary Jane | 8-6 | 5 | 5 |
| 11 | Gandhi's Army | 8-6 | 6 | 6 |
| 7 | Kaleb's Team | 7-7 | 7 | 8 |
| 12 | Team VP | 7-7 | 8 | 11 |
| 1 | Egbukake | 6-8 | 9 | 10 |
| 8 | Sneaky Fingers | 6-8 | 10 | 9 |
| 9 | Conor's Cuddle Muffins | 4-10 | 11 | 7 |
| 2 | Barry McAulkener | 4-10 | 12 | 12 |
| 3 | Chubby Chasers | 4-10 | 13 | 13 |
| 10 | Tyler's unimpressive Team | 2-12 | 14 | 14 |

### c) THE KEY QUESTION — does `rankCalculatedFinal` reflect true post-playoff finish?

**CONFIRMED for playoff teams (top 6 seeds); more nuanced for non-playoff
teams than the memo assumed.**

Reconstructed the real bracket from `schedule[]` (`view=mMatchupScore`),
weeks 15–17, using `playoffTierType` and `winner`:

- **`WINNERS_BRACKET`** (6 teams, top playoffSeeds 1–6; seeds 1 and 2 got
  byes in week 15 per `playoffTeamCount: 6`):
  - Round 1 (wk15): seed4 Bucky Charms d. seed5 Hail Mary Jane
    (147.65–133.41); seed3 Black Lives Matter d. seed6 Gandhi's Army
    (115.85–104.2)
  - Semis (wk16): seed4 Bucky Charms d. seed1 Stinky Fingers (168.25–99.35);
    seed3 Black Lives Matter d. seed2 Melonheads (168.85–133.0)
  - **Final (wk17): Black Lives Matter d. Bucky Charms, 169.25–146.2 →
    champion.**
- **`WINNERS_CONSOLATION_LADDER`** (semifinal/round-1 losers playing for
  3rd–6th, wk16–17): 3rd-place game Stinky Fingers d. Melonheads
  (136.3–87.35); 5th-place game Hail Mary Jane d. Gandhi's Army twice
  (177.8–149.75 wk16, 117.52–113.08 wk17).

Real final playoff order derived independently from the bracket: **1.
Black Lives Matter, 2. Bucky Charms, 3. Stinky Fingers, 4. Melonheads, 5.
Hail Mary Jane, 6. Gandhi's Army.**

`rankCalculatedFinal` for exactly these six teams: 1, 2, 3, 4, 5, 6 —
**identical, team for team, to the independently-reconstructed bracket
result.** Champion (Black Lives Matter) is `rankCalculatedFinal: 1`.
**Confirmed: for playoff teams, `rankCalculatedFinal` is the true
post-playoff finish.**

For the 8 non-playoff teams, ESPN also runs a real 3-round
**`LOSERS_CONSOLATION_LADDER`** bracket in weeks 15–17 (12 scheduled games,
not byes/placeholders) that re-seeds teams by ladder record each round and
produces its own finish order for ranks 7–14. Reconstructing win/loss
records through that ladder gives: 7. Conor's Cuddle Muffins, 8. Kaleb's
Team, 9. Sneaky Fingers, then five teams tied 1–2 in the ladder (Egbukake,
Team VP, Barry McAulkener, Chubby Chasers, Tyler's unimpressive Team)
resolved to ranks 10–14. **`rankCalculatedFinal`'s values for these 8 teams
match the ladder finish, not plain inverse-regular-season order** — e.g.
Conor's Cuddle Muffins (4-10 record, 11th-best regular season) finishes
`rankCalculatedFinal: 7`, better than four teams with better regular-season
records, because it won its consolation ladder.

**Net verdict, more precise than the memo's open question:**
`rankCalculatedFinal` is confirmed correct and champion=1, but it is **not**
"regular-season standings for non-playoff teams" — in a league that runs a
real bottom-bracket ladder (as this one does), it reflects *that bracket's*
finish. A rule that assumes "non-playoff teams ordered by inverse regular
season standing" will disagree with `rankCalculatedFinal` for any league
that runs a consolation ladder, which is common. This matters directly for
(d) below.

### d) Reconstructing from `record.overall` + `playoffSeed` alone — and where it disagrees

Applying FTF's stated rule literally — non-playoff teams in inverse
regular-season order, playoff teams by playoff finish (champion picks
last), ties broken by inverse standings — using only `record.overall` /
`playoffSeed` (i.e. ignoring the consolation ladder ESPN actually played)
produces a **different** order from one derived off `rankCalculatedFinal`
for 5 of the 8 non-playoff teams (picks 4–8), while the two approaches
agree exactly on all 6 playoff teams and the bottom 3 non-playoff teams. No
ties existed in this league's data (all 14 `playoffSeed`/record values are
distinct), so tie-break logic was not exercised.

| Pick # | Rule from `record.overall`+`playoffSeed` only | Rule from `rankCalculatedFinal` | Agree? |
|---|---|---|---|
| 1 | Tyler's unimpressive Team | Tyler's unimpressive Team | yes |
| 2 | Chubby Chasers | Chubby Chasers | yes |
| 3 | Barry McAulkener | Barry McAulkener | yes |
| 4 | Conor's Cuddle Muffins | Team VP | **no** |
| 5 | Sneaky Fingers | Egbukake | **no** |
| 6 | Egbukake | Sneaky Fingers | **no** |
| 7 | Team VP | Kaleb's Team | **no** |
| 8 | Kaleb's Team | Conor's Cuddle Muffins | **no** |
| 9 | Gandhi's Army | Gandhi's Army | yes |
| 10 | Hail Mary Jane | Hail Mary Jane | yes |
| 11 | The Humongous Melonheads | The Humongous Melonheads | yes |
| 12 | Stinky Fingers | Stinky Fingers | yes |
| 13 | Bucky Charms | Bucky Charms | yes |
| 14 (champion) | Black Lives Matter | Black Lives Matter | yes |

No slot required an outright guess (every team has an unambiguous
`record.overall`, `playoffSeed`, and `rankCalculatedFinal`) — the disagreement
in picks 4–8 is a genuine methodological fork, not missing data: which
"finish" should govern non-playoff pick order, the regular season alone or
the consolation-ladder games ESPN actually played after it? This is now a
**product decision FTF must make explicitly**, not an engineering unknown —
recommend surfacing it as a labeled choice ("order by regular-season
record" vs "order by ESPN's own final rank, including consolation games")
rather than silently picking one, since the two produce materially
different pick 4–8 assignments for any league that plays a real bottom
bracket.

### e) Future-pick ownership / traded-pick data

**CONFIRMED absent — matches prior desk research exactly.**

- `view=mDraftDetail` returns `draftDetail.picks[]` with 420 entries (14
  teams × 30 rounds) for the **already-completed 2025 rookie/startup draft**
  — fields are `overallPickNumber`, `roundId`, `roundPickNumber`, `teamId`,
  `playerId`, `keeper`, `tradeLocked`, etc. This is a record of *what
  happened* in this season's draft, not a forward-looking ownership ledger
  for a *future* season's picks. No `season`/`year` field ties a pick to a
  season other than the one being queried.
- `view=mTransactions2` returned 8 transactions for this league, all
  `"type": "ROSTER"` (lineup slot moves) — no `TRADE` transactions present
  in this sample to inspect for pick-asset items. No field anywhere in
  either response resembling a persistent "2027 1st round pick, owned by
  team X" object.

Confirms: ESPN's v3 API surfaces no cross-season future-draft-pick
ownership model for this league, consistent with §2's desk research and
`#158`.

### Updated top-line verdict

The original memo's verdict stands with one important refinement now that
it is live-verified rather than desk-researched:

- Final regular-season standings: **FEASIBLE**, now live-confirmed (not
  just documented).
- Playoff bracket / final finish: **upgraded from PARTIAL to FEASIBLE for
  playoff teams** — `rankCalculatedFinal` is confirmed correct,
  champion-is-1, no bracket reconstruction needed in code.
- Non-playoff team ordering: **new finding, not previously known** —
  `rankCalculatedFinal` reflects ESPN's own consolation-ladder finish where
  one is played, which will disagree with a pure "inverse regular-season
  standing" rule for any league that runs a real bottom bracket (this one
  does, materially, for 5 of 8 non-playoff teams). FTF must pick one
  definition and label it, not treat the two as interchangeable.
- Traded-pick awareness: **NOT FEASIBLE**, now live-confirmed (not just
  documented) — no future-pick ledger exists in the API at all.

### Operator decision — non-playoff ordering (2026-08-08)

The fork raised in §6d is **RESOLVED**. Operator ruling: non-playoff teams
are ordered by **inverse regular-season record** (`record.overall`), the
originally-stated rule. ESPN's `rankCalculatedFinal` is **not** used for
non-playoff teams, because it folds in consolation-ladder games that most
dynasty leagues treat as meaningless for rookie-pick purposes — a 4-10 team
should not pick 8th for winning the bottom bracket.

Implementation consequence: use `rankCalculatedFinal` **only** for the
playoff teams (where §6c confirmed it is exactly the post-playoff finish),
and `record.overall` for everyone else. Do not use `rankCalculatedFinal` as
a single whole-league sort key — for this league that would move 5 of 14
slots.

Unchanged by this ruling: the derived order is still only a **default
proposal**. ESPN exposes no traded-pick data (§6e), so manual override
remains mandatory regardless of which ordering rule is used.

---

## Files referenced

- `backend/espn_service.py` (fetch/parse/crosswalk — all line refs above)
- `backend/server.py:15361-15720` (`/api/espn/*` routes)
- `backend/database.py:239-251, 716, 1213-1246, 8074-8359` (leagues/ESPN
  columns, `espn_credentials`, ESPN league persistence)
- `backend/feature_flags.py:143-147` (`espn.link` flag)
- `docs/plans/espn-league-linking-plan-2026-07-11.md` (original go/no-go —
  most authoritative internal source; contains live-verified probe data)
- `docs/feedback/items/207-rookie-draft-detection/research-platforms.md`
  (adjacent, more recent ESPN-view research; same verification gap noted)
- `docs/plans/draft-extensions/plan.md` (current draft-surface roadmap;
  independently flags the same `mDraftDetail` verification gap)
- `docs/plans/rookie-draft/plan.md`, `docs/glossary.md` (confirm ESPN has no
  pick model in FTF today)
