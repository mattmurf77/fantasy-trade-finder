# FB-210 — Éire Rebels team name renders with HTML-entity garbage (MFL)

- **Type:** bug · **Status:** fixed 2026-08-01 (branch `teardown-remediation` worktree)
- **Surface:** anywhere MFL member/team names render (league rankings, trade
  cards, switcher) for MFL leagues — the operator's Dependables league
  (id 62846) showed `&#201;ire Rebels` instead of `Éire Rebels`.

## Root cause

MFL's export API serves display strings with HTML entities — numeric
(`&#201;`), named (`&amp;`), occasionally double-escaped (`&amp;#201;`) —
plus stray/non-breaking whitespace. `mfl_service.parse_bundle` passed
franchise names through raw (`f.get("name")`), and `server.py`'s
link/import paths write those names verbatim into `league_members`
(`username`/`display_name`), so the entity text became the stored,
rendered member name. League names (`parse_bundle`, `fetch_my_leagues`)
and player names (`_flip_name`) had the same exposure.

## Fix (parse-time, `backend/mfl_service.py`)

New `_clean_text()` helper: `html.unescape` applied until stable (max 2
passes — covers the double-escaped case) + whitespace runs collapsed to
single spaces + strip. Applied to every MFL-sourced display string:

- `parse_bundle`: franchise names (`fr_name`) + the league name
- `_flip_name`: player names (before the "Last, First" flip)
- `fetch_my_leagues`: league `name` + `franchise_name`

## Healing already-stored names

Verified: the re-sync path (`POST /api/mfl/import`) re-runs
`parse_bundle` and calls `replace_espn_league_members` with the fresh
names — **one manual re-sync of the league rewrites the stored member
names** (same pattern as the #201 format-detection fix-up). The link and
auth-import paths get clean names on all future imports.

## Tests

- `backend/tests/test_mfl_service.py::test_clean_text_unescapes_entities_and_normalises_whitespace`
- `backend/tests/test_mfl_service.py::test_parse_bundle_cleans_entity_laden_names`
  (entity-laden fixture: `&#201;ire  Rebels`, `Smash &amp; Grab`,
  `The Dependables &amp; Friends`, `O&#8217;Connell, Kirby`)

Full backend suite: 1367 passed, 1 skipped.
