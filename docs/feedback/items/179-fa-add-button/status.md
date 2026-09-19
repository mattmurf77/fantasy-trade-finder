# #179 — Add button on free agents — status

**State:** shipped v1 (2026-07-25, worktree branch off `teardown-remediation`).
**Owner ask:** "Users should have the ability to hit 'add' from the free
agents tab and have the players added automatically. The feature should
also return errors for why the addition can't be made (such as roster
limits or other errors)."

## Platform reality check (governs the whole design)

- **Sleeper has NO public write API.** There is no endpoint any
  third-party app can call to execute a waiver claim or free-agent add.
  "Added automatically" is impossible without credential-scraping we will
  not do. The honest v1 — same pattern as the existing trade-propose
  deep-link (`buildSleeperUrl` in TradesScreen; Sleeper publishes no
  programmatic trade endpoint either) — is a per-row **Add** button that
  hands off into Sleeper: `https://sleeper.com/leagues/<id>/players`
  (the league's available-players surface), after a short explainer.
- **ESPN**: FTF's ESPN link is a read-only import (public or cookie
  read). No write path; adds must happen in the ESPN app.
- **MFL** does have an authed transaction API, but FTF's MFL links are
  currently zero-auth public reads — execute-add is out of scope until
  MFL auth lands (#177, separate work). Same for **Fleaflicker**.
- **No execute path is fabricated anywhere.**

## What shipped

**Per-FA-row Add affordance** (`FreeAgentsScreen`, PlayerCard `rightSlot`,
testID `free-agents.add.<player_id>`), behavior per platform
(`resolveAddPlatform`: cached league-list platform via `isEspnLeague` /
`isMflLeague` / `isFleaflickerLeague`, numeric id ⇒ Sleeper, else local):

- **Sleeper** (secondary button): confirm alert — "Sleeper doesn't let
  other apps make roster moves, so we'll open your league in Sleeper to
  finish the add there" → opens the league's players page (app or web
  via universal link). **Roster-limit pre-check:** when the backend's
  `roster_capacity` says `my_count >= limit`, the alert instead warns
  "You're at N/N players, so Sleeper will block this add until you drop
  someone" before offering Open Sleeper — the requested
  "errors for why the addition can't be made", delivered before the
  hand-off since there is no execute step to return them from.
- **ESPN / MFL / Fleaflicker** (ghost/dim button = disabled affordance
  that can still explain itself): tap shows the honest reason — league
  is a read-only import, add in the platform's own app. No dead-end
  silent disabled state.
- **Demo/local leagues**: "This league isn't connected to a fantasy
  platform, so there's no roster to add this player to."

**Backend support** (`GET /api/league/free-agents`): additive
`roster_capacity: {my_count, limit} | null` — Sleeper leagues only.
`my_count` comes from the live rosters read the route already performs
for #178 (fallbacks: raw snapshot row, then session roster); `limit` =
`len(roster_positions) + reserve_slots + taxi_slots` from league meta
(`_sleeper_roster_limit`, 15-min in-process TTL cache). Both fields
nullable; clients skip the pre-check when data is missing. Old clients
ignore the new key; old servers omit it and the client typing marks it
optional.

## Tests

- Backend: `test_roster_capacity_for_sleeper_league`,
  `test_roster_capacity_null_for_non_sleeper_league`
  (`backend/tests/test_free_agents_route.py`).
- Mobile: `npx tsc --noEmit` clean. No mobile unit-test harness exists
  for screens; Maestro coverage would target
  `free-agents.add.<player_id>` (registered in the testID registry).

## Files changed

- `backend/server.py` — `roster_capacity` in the FA response,
  `_sleeper_roster_limit` + `_FA_LEAGUE_META_CACHE`.
- `mobile/src/api/league.ts` — `FreeAgentRosterCapacity`, response type.
- `mobile/src/screens/FreeAgentsScreen.tsx` — Add button, per-platform
  handling, roster-full pre-check.
- `mobile/src/components/CLAUDE.md` — testID registry.
- `docs/api-reference.md` — FA route contract.

## Future (out of scope here)

- MFL execute-add once authed MFL linking (#177) lands.
- A `add_player_id` query param on the Sleeper deep-link if Sleeper ever
  documents one (today only the players-surface path is known-good).

---

## v2 — claim-preparation sheet (2026-07-26, teardown-remediation worktree)

**Driver:** DynastyDealer teardown (League Hub → Waivers,
`docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`) +
operator priority: "Waiver claim, FAAB support, budget remaining, and
value sorted drop candidates is a big one… value sorted drop candidates
by least valuable is perfect."

The Sleeper Add flow upgraded from alert → **claim sheet** (testID
`fa-claim.sheet`). Still zero fabricated write paths: FTF PREPARES the
claim, the user executes it in Sleeper — the sheet's footer says so
verbatim ("Sleeper doesn't allow apps to submit claims — finish in
Sleeper") and the CTA (`fa-claim.open-sleeper`) deep-links to the same
league players page as v1.

**Backend (additive on `GET /api/league/free-agents` — no companion
endpoint; the route already held every input, so one payload keeps the
sheet a single fetch):** Sleeper leagues now also get

- `waivers: {type, faab}` — `type` maps Sleeper `settings.waiver_type`
  (2→`faab`, 0→`rolling`, 1→`reverse_standings`, unknown→null); `faab` =
  the caller's `{budget, used, remaining}` (league `settings.waiver_budget`
  / their live roster's `settings.waiver_budget_used`), null for
  priority-waiver leagues. No new Sleeper calls: settings ride the cached
  league-meta fetch (`_fa_league_meta`, split out of
  `_sleeper_roster_limit`), spend rides the existing rosters read.
- `drop_candidates: {players, untouchables_excluded}` — caller's roster
  priced on their board (consensus fallback, same valuation as the FA
  list), value-**ascending**, capped at 8
  (`compute_drop_candidates` in `free_agent_service.py`); untouchables
  (asset_prefs) never suggested, count reported so the sheet can say so.
- `roster_capacity.open_slots` — max(limit − my_count, 0), null when
  either side is unknown.

All three keys null for platform/demo leagues; old clients ignore them.

**Client sheet per league type (Sleeper only — platform-linked/local keep
the v1 dimmed/explainer alerts):**

- FAAB league: numeric bid input (`fa-claim.bid`, number-pad) with
  "Budget: $N remaining"; bid > remaining shows an inline error and
  disables the CTA until lowered.
- Priority-waiver league: "This is a waiver priority league — no FAAB bid
  needed." — no bid input.
- Open slots: "You have N open roster slots — no drop needed." Full (or
  capacity unknown): "Select a player to drop", radio-select rows
  (`fa-claim.drop.<id>`) least-valuable-first, plus a note when
  untouchables were withheld.

**MFL execute-add feasibility (follow-up, NOT built):** unlike Sleeper,
MFL's authed API has a real write endpoint — `import.cgi` with
`TYPE=fcfsWaiver` / `TYPE=waiver` (`ADD=`/`DROP=` player ids, FAAB `BID=`)
against the league host, authenticated by the same `MFL_USER_ID` cookie
`mfl_auth_link` (#177) already captures. Feasible now that authed linking
exists, with three cautions: (1) cookie freshness — the stored cookie can
expire or be invalidated by a password change, so an execute path needs a
re-auth prompt on 401-shaped responses; (2) league-host routing — writes
must hit the league's assigned host (`wwwNN.myfantasyleague.com`), not the
apex; (3) blast radius — this would be FTF's FIRST real roster write
anywhere, so it wants an explicit confirm step, a feature flag, and
transaction-result surfacing (MFL returns XML errors like "roster full")
before any rollout. Sized as its own item, not part of this change.

## Files changed (v2)

- `backend/server.py` — `_fa_league_meta` + `_sleeper_waivers`
  (`_SLEEPER_WAIVER_TYPES`), route additions above.
- `backend/free_agent_service.py` — `compute_drop_candidates`
  (+ `DROP_CANDIDATE_LIMIT = 8`).
- `backend/tests/test_free_agents_route.py` — claim-sheet coverage (see
  Tests v2).
- `mobile/src/api/league.ts` — `FreeAgentWaivers`,
  `FreeAgentDropCandidate(s)`, `open_slots`, response keys.
- `mobile/src/screens/FreeAgentsScreen.tsx` — `ClaimSheet` (replaces the
  Sleeper alert step), `explainNoAdd` for the rest.
- `mobile/src/components/CLAUDE.md` — testID registry tranche.
- `docs/api-reference.md` — FA route contract.

## Tests (v2)

- `test_faab_block_for_faab_league` — budget/used/remaining wiring.
- `test_faab_null_for_priority_waiver_league` — type served, faab null.
- `test_open_slots_zero_when_roster_full` + updated
  `test_roster_capacity_for_sleeper_league` — open-slot math.
- `test_drop_candidates_ascending_untouchables_excluded_capped` —
  least-valuable-first order, untouchable withheld + counted, cap 8.
- `test_roster_capacity_null_for_non_sleeper_league` extended — waivers +
  drop_candidates null off-Sleeper.
- Mobile: `npx tsc --noEmit` clean; Maestro targets `fa-claim.sheet` /
  `fa-claim.bid` / `fa-claim.drop.<id>` / `fa-claim.open-sleeper`
  (registered in the testID registry).
