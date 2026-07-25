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
