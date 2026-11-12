# Per-user binding for linked ESPN / MFL / Fleaflicker leagues

**Date:** 2026-11-11 · **Branch:** `fix/platform-league-user-binding` · **Status:** built, unmerged
**Scope block:** [scope.md](scope.md) · **Tests:** `backend/tests/test_platform_league_binding.py`

- [1. The bug, as a user sees it](#1-the-bug-as-a-user-sees-it)
- [2. What was keyed by league and what by user](#2-what-was-keyed-by-league-and-what-by-user)
- [3. The model](#3-the-model)
- [4. Writers](#4-writers)
- [5. Readers](#5-readers)
- [6. Existing production data and the backfill](#6-existing-production-data-and-the-backfill)
- [7. Counting the damage (read-only, Postgres)](#7-counting-the-damage-read-only-postgres)
- [8. Sleeper is unaffected](#8-sleeper-is-unaffected)
- [9. Not switched, and known limits](#9-not-switched-and-known-limits)

## 1. The bug, as a user sees it

Two managers in the same ESPN (or MFL, or the dark Fleaflicker) league both link it in
Fleeced. That is the intended, common case: the app's value is league-mates using it
together, and the platform-sign-in flow links the league as part of signing in.

On `main` (`679658b4`) the second link, by B, silently takes the league away from the
first linker, A:

| A does… | …after B linked | What A sees |
|---|---|---|
| opens the league picker | `GET /api/espn/leagues` / `/api/mfl/leagues` no longer list it | the league is gone; the app says "link it again" |
| re-syncs (cached league) | `POST /api/espn/import` binds **A** to **B's team** (and, for a cookie league, holds A's SWID to B's team: 403 `wrong_account`, A's `verified_at` nulled) | A's roster is B's; or A is told they signed in with the wrong ESPN account and their sign-in is un-verified |
| sends a trade | the send is built with **B's team** and **A's cookie** (`my_team_id` from the shared row); ESPN `"You can't send a trade to your own team"` when the target is A's real team, or an offer from B's team | wrong team, or a refusal |
| — | the weekly roster sweep holds A's credential to B's team (#321 R9) | an inbox "Reconnect ESPN — wrong account signed in" nudge |

B, the second linker, sees the league as theirs but **cannot send at all**: every send,
MFL respond and MFL pending-trades route checked `leagues.user_id` (the first linker)
and answered 404 `*_not_linked`. Any third user who called `/api/*/import` with the id
was bound to the last linker's team (no binding check at all).

If A later re-links, B loses the league the same way: last writer wins, forever.

## 2. What was keyed by league and what by user

| Fact | Where it lived | Keyed by |
|---|---|---|
| league name, season, auth mode, total teams, host, future picks | `leagues` row (PK = platform league id) | league |
| who created the row | `leagues.user_id` — insert only, never updated | league (first linker) |
| "my team" | `leagues.espn_my_team_id` / `platform_my_team` — overwritten by every link | league (**last** linker) |
| every team's roster | `league_members`, delete-then-insert by every link/import | league |
| which team is whose | the ONE `league_members` row carrying a real app id = the writer's own team; every other team got a synthetic `espn:{SWID}` / `mfl:{L}.f{F}` / `flea:{L}.t{T}` id | league (**last writer**) |
| credentials | `espn_credentials` / `mfl_credentials` | user ✔ |

So "my team" was a league-level fact. A non-app manager's id is synthetic; an app
user's team carried their real id only if they were the last writer.

Readers (all on `main`): `load_espn_leagues_for_user` / `load_platform_leagues_for_user`
(league list, `my_team_id`, client "mine" = member with my id), `espn_import`,
`mfl_import`, `fleaflicker_import`, `_espn_verify_credential` (#321 membership),
`_espn_propose_core`, `_mfl_propose_core`, `_validate_espn_trade`, `_validate_mfl_trade`,
the MFL respond / pending-trades routes, `_overhaul_platform_rosters` (team overhaul's
fresh rosters), `_sync_mfl_owned_picks` (pick owner ids), `_mfl_board_binding` (draft
board `my_picks`), `_espn_suggested_order` (draft order), `_sweep_fetch_teams` (weekly
roster history + #321 R9 nudge), `load_history_sweep_leagues`, prepared-trade discovery
(`prepared_trade_runtime.cohort_rows` / `sync_source_picks`) and the founders-only
calibration capture.

## 3. The model

**One new additive table, `platform_league_bindings`, PK `(user_id, league_id)`**:
`platform`, `team_id` (native id as text), `source` (`link` | `backfill`), `created_at`,
`updated_at`. The leagues row and `league_members` stay one shared copy per league.

Rules:

1. A user's binding is written **only** by that user's own link (`upsert_espn_league` /
   `upsert_platform_league`, which every link route already calls with the session user
   and the chosen team), and by the backfill. Re-sync rewrites the caller's own row with
   the same value. Another user's link or import never touches it.
2. **Every reader of "my team" uses `database.get_platform_binding(user_id, league_id,
   platform)`.** No binding → fail closed: the league is not listed, re-sync / send /
   pending-trades answer the existing `*_not_linked` 404, the overhaul gets no fresh
   rosters. Never a fallback to the leagues row.
3. League-wide readers that need "which app user is on team T" use
   `platform_bound_teams(league_id)`; each bound team is labelled by its **earliest
   binder** (created_at, then user_id).
4. The shared `league_members` snapshot labels every bound team with that label, whoever
   writes it (`_label_bound_teams` inside `replace_espn_league_members`' transaction). So
   in A's view B's team carries B's real id and vice versa — they can match, and the send
   resolvers map a real counterparty id through that user's binding.
5. Two app accounts on the same team (one person with two accounts, or co-managers) share
   one member row (the earliest binder's id); each one's league list relabels that row to
   them (`_members_as_seen_by`). No phantom 13th team.
6. The legacy columns `espn_my_team_id` / `platform_my_team` are still **written** (so a
   rollback to old code keeps working, with the old bug) and are **read only by the
   backfill**. The seam test pins that.

### Alternatives rejected

| Alternative | Why not |
|---|---|
| Store the team on the credential row (`espn_credentials.team_id`) | one credential per user, many leagues; MFL public links have no credential; ESPN public links have none either |
| A `team_key` column on `league_members` + `user_id` = binder | overloads the shared snapshot with per-user facts; a co-owned team would need two rows (phantom team, ADR-012); every existing reader of `league_members.user_id` would see duplicates |
| Make `leagues` PK `(league_id, user_id)` | destructive migration of a 30-column shared table used by every Sleeper path; duplicates league facts per user |
| Keep the row binding, refuse a second linker | the product premise is league-mates using the app together |

## 4. Writers

| Writer | Change |
|---|---|
| `upsert_espn_league`, `upsert_platform_league` | + one line: `_upsert_platform_binding(conn, user_id, league_id, platform, team)` in the same transaction as the row upsert |
| `replace_espn_league_members` | + one line: `_label_bound_teams(conn, …)` after the DELETE, before the INSERT; a no-op unless the members carry an `espn:`/`mfl:`/`fleaflicker:` team_key (Sleeper's `replace_league_members_snapshot` passes none) |
| `espn_link`, `mfl_link`, `_mfl_import_league_authed`, `fleaflicker_link` | **no change** — they already pass the session user and the chosen team to the two upserts |
| `espn_import`, `mfl_import`, `fleaflicker_import` | binding required (else 404 `*_not_linked`); `my_team` = the caller's binding; the upsert passes `user_id=user_id` (was the row's linker) |
| `upsert_league_members`, `write_session_init_members` | **no change** (session init only updates existing platform rows by id) |
| account deletion (`accounts.delete_user_data`) | the user's bindings are deleted (`_ADDITIONAL_PRIVATE_TABLES`, so exported too); a platform `leagues` row they created that a surviving league-mate is bound to is **handed to that league-mate** (`user_id` updated) instead of deleted; when no other binder remains the row is deleted as before |

Credential disconnect (`DELETE /api/espn/link`, `DELETE /api/mfl/auth-link`) is unchanged:
it removes only the caller's credential and leaves every binding (the league stays the
caller's, readable publicly). There is no "unlink a league" route.

Concurrency: the binding commits before the member transaction. Two links racing on
Postgres: the second member transaction's DELETE waits on the first's row locks, then
reads bindings after the first committed, so the last snapshot labels both. If a label is
ever stale, "my team" is still correct (it comes from the binding) and the next
link/re-sync relabels.

## 5. Readers

Switched to `get_platform_binding` (my team) or `platform_bound_teams` (every bound team):
`load_espn_leagues_for_user`, `load_platform_leagues_for_user`, `espn_import`,
`mfl_import`, `fleaflicker_import`, `_espn_propose_core`, `_mfl_propose_core`,
`_validate_espn_trade`, `_validate_mfl_trade`, MFL respond + pending-trades,
`_mfl_franchise_from_member_id` / `_espn_team_id_from_member_id` (a real counterparty id →
that user's binding, still checked against the live team list), `_overhaul_platform_rosters`,
`_sync_mfl_owned_picks`, `_mfl_board_binding`, `_espn_suggested_order`,
`_sweep_fetch_teams` (labels; R9 holds the credential owner to **their own** binding, and
skips the nudge when they have none), `load_history_sweep_leagues` (stops selecting the
legacy columns), `prepared_trade_runtime.cohort_rows` (passes every binding as an explicit
`verified_import` binding and replaces the row's legacy fields with the row user's own
binding) and `sync_source_picks`, `calibration_provider_capture.validate_owned_picks`
(mirrors `_sync_mfl_owned_picks`). `_espn_verify_credential` (#321) is switched through
`load_espn_leagues_for_user`: the membership assertion now holds the pair to the caller's
own team in each league.

Free-agent moves are Sleeper-only (`server._FA_MOVE_FLAGS`); a test fails if an ESPN/MFL
move is added without the sender's binding.

The #321 checks are unchanged except one condition: `espn_import`'s R3b used to assert
only when the caller was the row's first linker ("zero false rejects if another user ever
re-syncs") because a non-linker's re-sync carried the linker's team. The team is now
always the caller's own, so R3b asserts for every re-syncer. Its error, message and
`verified_at` handling are untouched.

## 6. Existing production data and the backfill

What the bug left in production, per linked league:

* the `leagues` row: `user_id` = first linker, legacy team column = **last linker's** team;
* `league_members`: at most one real app id = the **last writer**, on that same team (every
  legacy writer set both in one request);
* each user's credential is intact (per user), but a cookie-league first linker whose
  re-sync hit the R3b check after a second link had `verified_at` nulled (they re-sign in);
* nothing else records which team an earlier linker chose. ESPN SWIDs in synthetic member
  ids name the owners of OTHER teams only; roster-history `owner_user_id` is flag-gated and
  re-stampable, not a binding. So **a first linker whose binding was overwritten cannot be
  recovered** — they must re-link (pick their team again; ESPN sign-in re-proves it).

`backfill_platform_league_bindings()` runs from `_migrate_db` on every boot (idempotent):

| Rule | Why |
|---|---|
| only leagues with **no** binding row yet | anything the new code touched is already right; makes every later boot a no-op |
| exactly one app-user member R and a non-null legacy team T → bind (R, T, `backfill`) | that pair is the last link's own (caller, chosen team) |
| zero or several app-user members → nothing | the earlier linker's binding is gone; never guessed |
| ESPN: R's stored SWID labels a different team (`espn:{SWID}` member) → nothing | proof the pair is wrong |
| `INSERT … ON CONFLICT DO NOTHING` | never overwrites a binding a link wrote in the deploy overlap (old instance still serving) |
| no leagues / league_members writes | additive only |

Trust: the derived pair is exactly what today's code shows the last linker, so the
backfill never makes anyone's view worse. Residual: a stale client that re-synced a league
it no longer had listed (after someone else's link) on a **public** league left itself as
the member on the other user's team; the backfill reproduces that (wrong) pair, i.e. what
that user sees today. A re-link fixes it. Unbound users get the existing "link it again"
copy (`espn_not_linked` / `mfl_not_linked`, and the client's "ESPN league not linked —
link it again from the league picker").

A link that happens on the old instance after the new instance's boot backfill (deploy
overlap) leaves no binding row; the next boot's backfill derives it if the league has no
binding yet, otherwise that user re-links. Render deploys are one worker; the window is
the health-check overlap.

## 7. Counting the damage (read-only, Postgres)

Not run. Aggregates only. Run against production as a read-only session
(`backend/tools/prod_analytics.py` forces `default_transaction_read_only`), **before**
deploying (after deploy, also count `platform_league_bindings` by `source`).

```sql
-- Linked platform leagues by the state the pre-fix writers left them in.
WITH lg AS (
  SELECT l.sleeper_league_id AS league_id, l.platform, l.user_id AS first_linker,
         CASE WHEN l.platform = 'espn' THEN CAST(l.espn_my_team_id AS TEXT)
              ELSE l.platform_my_team END AS legacy_team
  FROM leagues l
  WHERE l.platform IN ('espn', 'mfl', 'fleaflicker')
),
app_members AS (            -- members that are app users (not synthetic ids)
  SELECT m.league_id, COUNT(*) AS n, MIN(m.user_id) AS only_member
  FROM league_members m
  WHERE m.user_id NOT LIKE 'espn:%' AND m.user_id NOT LIKE 'mfl:%'
    AND m.user_id NOT LIKE 'flea:%' AND m.user_id NOT LIKE 'fleaflicker:%'
  GROUP BY m.league_id
),
deck_users AS (             -- distinct app users who ever got a deck in the league
  SELECT t.league_id, COUNT(DISTINCT t.user_id) AS n
  FROM trade_impressions t
  WHERE t.league_id IN (SELECT league_id FROM lg)
  GROUP BY t.league_id
)
SELECT lg.platform,
  COUNT(*)                                                         AS linked_leagues,
  COUNT(*) FILTER (WHERE am.n = 1 AND am.only_member = lg.first_linker)  AS last_writer_is_first_linker,
  COUNT(*) FILTER (WHERE am.n = 1 AND am.only_member <> lg.first_linker) AS first_linker_overwritten,
  COUNT(*) FILTER (WHERE am.n IS NULL)                              AS no_app_member,
  COUNT(*) FILTER (WHERE am.n > 1)                                  AS several_app_members,
  COUNT(*) FILTER (WHERE lg.legacy_team IS NULL)                    AS no_team,
  COUNT(*) FILTER (WHERE du.n > 1)                                  AS leagues_used_by_2plus_app_users,
  COUNT(DISTINCT lg.first_linker) FILTER (
      WHERE am.n = 1 AND am.only_member <> lg.first_linker)         AS users_who_lost_a_league
FROM lg
LEFT JOIN app_members am ON am.league_id = lg.league_id
LEFT JOIN deck_users  du ON du.league_id = lg.league_id
GROUP BY lg.platform
ORDER BY lg.platform;
```

`first_linker_overwritten` + `no_app_member` are the leagues where at least one user's
binding is already lost; `users_who_lost_a_league` lower-bounds the affected users (a
first linker who re-linked after a second user is counted as intact, and the second user
is then the one who lost it — `leagues_used_by_2plus_app_users` is the upper signal).

## 8. Sleeper is unaffected

Sleeper's league identity is the Sleeper user id itself: a Sleeper league row is
`platform` NULL/`'sleeper'`, its members are written by `write_session_init_members` /
`replace_league_members_snapshot` / `upsert_league_members` keyed by each roster's
`owner_id` (`backend/database.py` `write_session_init_members`, `roster_refresh.py:270`,
`server._refresh_sleeper_members`), and "my roster" is
`sleeper_roster.owns_roster(roster, user_id)` (ADR-012) — none of it reads
`espn_my_team_id` / `platform_my_team` or the new table. The only shared code path is
`replace_espn_league_members`, called by `replace_league_members_snapshot`: Sleeper member
dicts carry no `team_key`, so `_label_bound_teams` returns before any query
(`test_sleeper_member_snapshot_is_never_relabelled`, sabotage S13). The sweep's Sleeper
branch and every Sleeper send path are untouched (diff), and the full suite is green.

## 9. Not switched, and known limits

* **Founders-only calibration capture** (`calibration_provider_capture.binding_identity` /
  `capture_linked`) still reads the legacy columns for its provenance keys. It re-verifies
  against the live provider (ESPN SWID owner, MFL myleagues) and fails with
  `league_seat_changed`, except an ESPN public league read with no stored SWID. Founders'
  accounts only, no serving or writes. Allowlisted in the seam test; follow-up: route it
  through `get_platform_binding` (its 5 test files seed raw legacy rows).
* `prepared_trade_cohort.py` still names the legacy keys, but only on dicts that
  `cohort_rows` fills from the bindings.
* `leagues.espn_auth` / `platform_auth` stay league facts: an MFL league linked by A via
  sign-in (`cookie`) and then by B via the public link is relabelled `public` (pre-existing;
  a private MFL league fails B's public link anyway).
* Public ESPN/MFL links remain unproven claims (any user may claim any team) — unchanged;
  now a false claim binds only the claimant.
