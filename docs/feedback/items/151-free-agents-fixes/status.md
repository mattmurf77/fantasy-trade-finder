# #151 — Free agents: rostered players in the list + broken back button — status

**State:** fixed (2026-07-25, worktree branch off `teardown-remediation`).
**Owner ask (mattmurf77, League, v1.9.1):** "Free agents list isn't right. It
should be non rostered players only (currently showing rostered players).
Additionally the back button on the free agents page is broken."

## (a) Rostered players in the FA list — root cause

`GET /api/league/free-agents` builds its exclusion set from the IN-SESSION
league rosters, but `/api/session/init` filters every roster against the
DEFAULT (`1qb_ppr`) pool (`opp_ids = [... if str(x) in players_dict]`,
`backend/server.py` session-init). The FA pool, however, is the **active
format's** universal pool (`_get_universal_pool(_active_format(sess))`).
Any player who exists only in the active format's pool — classically low-end
QBs with an SF value but a zero 1QB DynastyProcess value, in an `sf_tep`
league — was silently dropped from every in-session roster at init, so he
was missing from the exclusion set and surfaced as a "free agent" while
rostered. The caller's own persisted `league_members` row had the same
filtered ids (opponent rows were already stored raw).

### Fix (backend/server.py)

1. `league_free_agents_route` now UNIONs the raw `league_members` snapshot
   (client-sent, unfiltered ids) into the exclusion set for the session
   league, with `str()` coercion on every id. Best-effort: a missing or
   failing snapshot leaves the session-derived set (pre-fix behavior), never
   errors the route.
2. Session init's `league_members` upsert stores the caller's own row RAW
   (`user_player_ids` instead of the pool-filtered `new_user_roster`),
   matching the opponent rows. Consumers that need pool membership already
   filter on read (init's DB-member merge, `compute_free_agents`,
   `compute_power_rankings` prices off-pool ids at 0 exactly as it already
   did for the raw opponent rows).

Route contract unchanged — no `docs/api-reference.md` delta.

### Tests

`backend/tests/test_free_agents_route.py` (new):
- `test_rostered_player_outside_default_pool_is_excluded` — regression: a
  rostered player absent from the in-session (default-pool-filtered) roster
  but present in the raw snapshot must NOT appear (fails pre-fix).
- `test_missing_snapshot_falls_back_to_session_rosters`
- `test_snapshot_failure_never_errors_the_route`

Pure ranking rules stay pinned by `backend/tests/test_free_agents.py` (18
tests, untouched).

## (b) Broken back button — root cause

`FreeAgents` is a root-stack push whose PREVIOUS screen (the Main tabs) runs
with `headerShown: false`. On iOS 26, react-native-screens 4.16.0 (the app's
exact version) has a known bug where the native header back button becomes
unresponsive in exactly this configuration:
[react-native-screens#3294](https://github.com/software-mansion/react-native-screens/issues/3294)
("[iOS 26] Back Button disables if headerShown: false or custom header
used"). Only the swipe-back gesture worked. Not reproducible in this repo's
tooling (no iOS 26 rebuild available locally — CocoaPods/Ruby 4 breakage),
diagnosis is from the exact version + configuration match with the upstream
issue.

### Fix (mobile/src/navigation/RootNav.tsx)

`headerBackVisible: false` + an explicit JS `HeaderBack` control
(`headerLeft`, testID `free-agents.back-btn`, Icon Button construction per
components.md — mirrors the #130 `HeaderClose` precedent) wired straight to
`navigation.goBack()`, with a `canGoBack()` guard falling back to
`navigate('Main')` for the cold-start deep-link case.

**Parity note:** `LeagueSummary`, `Profile`, and `TestStages` are standard
pushes with the same headerShown-false predecessor and are presumably
affected by the same RNS bug; only Free Agents was reported, so only it was
changed here (surgical rule). Recommend applying `HeaderBack` to those three
when confirmed.

## Files changed

- `backend/server.py` — FA-route exclusion union; raw user row in the
  league_members upsert.
- `backend/tests/test_free_agents_route.py` — NEW (3 tests).
- `mobile/src/navigation/RootNav.tsx` — `HeaderBack` + FreeAgents options.
- `mobile/src/components/CLAUDE.md` — testID registry (`free-agents.back-btn`).
