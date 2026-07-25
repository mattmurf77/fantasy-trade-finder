# #178 — Free agents STILL not filtering out owned players — status

**State:** fixed (2026-07-25, worktree branch off `teardown-remediation`).
**Owner ask (mattmurf77, v1.11.0, priority 1):** "Free agents view is still
not filtering out owned players. All players are showing." Filed AFTER the
#151 fix shipped and was live in prod.

## Root cause (re-derived from scratch, verified against real data)

The #151 fix unioned the raw `league_members` snapshot into the FA
exclusion set — but **both** exclusion sources (the in-session league
rosters AND that snapshot) descend from the same CLIENT-built
`/api/session/init` payload, and the mobile/web clients drop rosters with
no owner when building it (`initLeagueSession`:
`.filter((r) => r.owner_id && r.owner_id !== user.user_id)`). A roster
whose manager left the league has `owner_id: null` on Sleeper, so its
players never reach ANY exclusion source.

Verified against the operator's real league (`1312140920132497408`,
public Sleeper API, 2026 season, 12 rosters): **roster_id 6 has
`owner_id: null` and 39 players, including Ja'Marr Chase, Bijan Robinson,
Jayden Daniels, Joe Burrow, Amon-Ra St. Brown, Sam LaPorta, Bucky
Irving.** Ranked by value, those players occupy the TOP of the FA list —
to the user the list reads as "not filtered at all". This is why #151
(which fixed the off-default-pool leak, a different and real hole) did
not help his league: the leak he sees is owner-shaped, not pool-shaped.

Secondary finding from the same audit (the "exclusion set EMPTY" class):
when the requested `league_id` doesn't match the session league and its
`league_members` snapshot was never synced, the pre-fix route built an
empty exclusion set and served the ENTIRE universal pool as free agents —
silently. Reachable for any league whose snapshot write hasn't happened
(new-season league ids, the INIT-08 background-init window, a wiped DB).

## Fix (backend/server.py — `league_free_agents_route`)

Exclusion set is now the union of every reachable roster source:

1. In-session league rosters (as before, when `league_id` matches).
2. Raw `league_members` snapshot (#151; now unioned on BOTH league_id
   paths, with a logged warning instead of a bare `except: pass`).
3. **NEW — Sleeper leagues only** (numeric id, not a linked platform
   league): a **live Sleeper `/v1/league/<id>/rosters` read**, which is
   roster-shaped rather than owner-shaped — every rostered player is
   excluded, ownerless rosters included. Failure degrades to sources
   1+2 with a logged warning.

Platform-imported leagues (ESPN/MFL/Fleaflicker) need no live read:
their `league_members` snapshot is written SERVER-side at link/import
time from the platform's own team list (every team, no owner filter), so
it is already authoritative.

**Fail loud on empty:** if after all sources the exclusion set has no
rostered player at all (and no caller roster), the route returns
**503 `{error: "rosters_unavailable"}`** with honest copy instead of
listing the whole pool. Showing rostered stars as free agents silently is
the worst outcome; the mobile screen surfaces the server message
(`FreeAgentsScreen` error branch).

Contract deltas (docs/api-reference.md updated): 503 `rosters_unavailable`
+ the `roster_capacity` block added for #179.

Cost note: one extra Sleeper GET per FA request (client caches per
position for 60s, so a screen visit is ≤5 reads/min/user). League meta
(for #179's capacity) is TTL-cached 15 min in-process.

## Tests (`backend/tests/test_free_agents_route.py`, +7)

Verified failing pre-fix via `git stash push backend/server.py`:

- `test_ownerless_roster_players_are_excluded_for_sleeper_league` — the
  exact operator shape: player on an `owner_id: null` roster, absent from
  session AND snapshot, must not appear (pre-fix: appears).
- `test_empty_exclusion_fails_loud_for_sleeper_league` — session on a
  different league + empty snapshot + Sleeper down ⇒ 503, never a
  full-pool 200 (pre-fix: 200 listing everything).
- `test_empty_exclusion_fails_loud_for_platform_league` — ESPN-shaped
  league (numeric platform-native id) with an unsynced snapshot ⇒ 503;
  also asserts the live Sleeper API is never called for platform leagues.
- `test_platform_league_serves_from_snapshot_without_live_read` — ESPN
  league with a good snapshot serves correctly, zero Sleeper calls.
- `test_live_read_failure_falls_back_to_snapshot` — Sleeper flake with a
  non-empty snapshot stays a 200 (degraded, logged).
- `test_roster_capacity_for_sleeper_league` /
  `test_roster_capacity_null_for_non_sleeper_league` — #179 block.

Full backend suite: 1052 passed, 1 skipped (baseline 1045 + 7 new).

## Files changed

- `backend/server.py` — exclusion-set rewrite (live Sleeper union,
  fail-loud 503), `_sleeper_roster_limit` + meta TTL cache, docstring.
- `backend/tests/test_free_agents_route.py` — +7 tests.
- `mobile/src/screens/FreeAgentsScreen.tsx` — surfaces the 503's message.
- `docs/api-reference.md` — FA route contract.

## Residual (client-side, not blocking)

`initLeagueSession` still drops ownerless rosters from the session
payload, so surfaces that price off the session snapshot (e.g. power
rankings' team list) simply omit the orphaned team — cosmetically fine
(it isn't a competing team) but worth a look if an "unowned assets" view
is ever wanted.
