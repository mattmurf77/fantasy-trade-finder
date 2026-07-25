# Status — #149 ESPN league: trade-away button dead, positional pages empty

**2026-07-25 — fixed on worktree branch `worktree-agent-ae33eec5a00d24264` (worktree agent).**

Verbatim: "Hitting the trade away button on espn league doesn't work. All the
positional pages are empty" (TradesHome, v1.9.0).

## Root cause

`TradesScreen`'s FB-47 target picker builds its pool from `rosterByOwner`,
fed by `GET /api/sleeper/rosters/<league_id>`. That proxy routes on
`league_id.isdigit()`: non-numeric → DB (local leagues), numeric → Sleeper.
ESPN leagues are stored under their NUMERIC platform-native id
(`leagues.platform='espn'`, rosters in `league_members`), so the proxy sent
them to Sleeper, which 404s → `rosterByOwner` empty → every positional page
of the picker empty and the flow felt dead. Same misroute hit
`/api/sleeper/league_users` (@owner badges).

## Fix

Backend only — the data was already in the DB; mobile unchanged.

- `backend/database.py`: new `is_linked_platform_league(league_id)` — True
  when a leagues row exists with a non-Sleeper `platform` (ESPN/MFL/
  Fleaflicker; all use the same storage seam, so all three are fixed).
- `backend/server.py`: `/api/sleeper/rosters/<id>` and
  `/api/sleeper/league_users/<id>` serve the DB `league_members` snapshot
  when `not isdigit() OR is_linked_platform_league(id)`.

Same root cause as #150 (swap sheet reads the same `rosterByOwner`) — one
fix covers both. See `../150-replace-player/status.md`.

## Verification

- `backend/tests/test_espn_link_route.py`: 3 new tests — imported ESPN
  league served from DB for both proxies (Sleeper patched to assert it is
  never called), plus a guard that unlinked numeric ids still proxy Sleeper.
- `python3 -m pytest backend/tests -q` — **1016 passed, 1 skipped**
  (baseline 1013 + 3 new).
- `mobile: npx tsc --noEmit` — clean (no mobile code change beyond #153).
- Docs: `docs/api-reference.md` Sleeper-passthrough rows updated.
