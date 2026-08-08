# #258 — MFL team names show HTML entities

**Covered feedback IDs:** #258 (2026-08-06)
**Branch:** worktree-agent (from `origin/main` @ 6c30dd2) · **Date:** 2026-08-08
**Status:** built; regression tests verify-failing-first (4 fail pre-fix →
4 pass post-fix); full backend suite green.

## The bug (operator, verbatim)

> "Some of the mfl teams have weird characters in the team name. I believe it's
> html. We should strip that from team names."

## Root cause

`mfl_service._clean_text` (#210, shipped ~2026-08-01) already entity-decodes
**every MFL ingest path** — `parse_bundle` (franchise + league names, player
names via `_flip_name`) and `fetch_my_leagues` (auth league list) all pass
through it, and all four member-writing routes (`/api/mfl/link`, `/api/mfl/import`,
`/api/mfl/auth-link`, `/api/mfl/auth-import`) consume only `parse_bundle`
output. So no *current* import can store a dirty name.

The names the operator sees are **stored rows from leagues linked before #210**:
`league_members.username/display_name` (the authoritative member store —
session_init member payloads and trade-deck counterparty names flow from it),
`leagues.name`, and the denormalized `draft_picks.owner_username /
original_username` snapshots that `_sync_mfl_owned_picks` copied from the
then-dirty members. MFL leagues have **no automatic re-import** (unlike the
ESPN re-sync row), so those rows never self-heal — the entities keep surfacing
on TradesHome and everywhere else stored members render.

## Fix — clean the stored rows once (chosen over read/serialize-time decoding)

`backend/database.py` — new `_backfill_mfl_name_entities()`, called from
`_migrate_db()` (runs at every startup, like `_backfill_dual_format`):

- entity-decodes, via the same `mfl_service._clean_text` the import paths use
  (deferred import, no cycle), the three MFL name stores:
  1. `league_members.username` / `display_name` for leagues with
     `platform = 'mfl'`,
  2. `leagues.name` where `platform = 'mfl'`,
  3. `draft_picks.owner_username` / `original_username` where
     `platform = 'mfl'`;
- **scoped strictly to MFL rows** — Sleeper names are user-typed strings that
  Sleeper itself renders verbatim, so a literal `&amp;` there is intended
  display and is never rewritten;
- idempotent and free on a clean DB: rows that decode to themselves are never
  written, a second pass is a no-op, an empty DB early-returns.

Why not read/serialize time: the dirty copies live in three tables consumed by
many serializers (trades generate, matches, power rankings, pick labels,
platform-league payloads) — decoding per-read means finding every serializer
forever; fixing the stored data once covers them all, and the already-clean
write paths keep it fixed. Why not re-import-time only: MFL leagues re-import
rarely (manual re-link only), so the operator's leagues would have stayed dirty
indefinitely.

Downstream copies self-heal from the fixed stores: session_init rebuilds member
snapshots from the (now clean) platform-league payload on every league open,
and trade decks regenerate from live member reads.

## Regression tests

`backend/tests/test_mfl_name_backfill.py` (verified failing-first — all 4 fail
against pre-fix `database.py`):

- decodes named (`&amp;`), numeric (`&#201;`) entities + whitespace runs across
  all three stores; clean rows untouched;
- Sleeper-league rows (members, league name, picks) are **never** rewritten;
- idempotent + safe on an empty DB;
- `_migrate_db()` actually runs the backfill (pins the boot path).

## Verification

- Pre-fix: `4 failed`; post-fix: `4 passed`.
- Full suite: `python3 -m pytest backend/tests -q` → **2041 passed, 1 skipped**
  (baseline 2037 + these 4), exit 0.
- `cd mobile && npx tsc --noEmit` — clean (no mobile changes for this item).
- Prod effect: first Render boot after merge runs the backfill; the operator's
  MFL team names decode without any re-link.
