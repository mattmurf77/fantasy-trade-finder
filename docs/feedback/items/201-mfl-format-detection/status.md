# #201 — MFL scoring format wrong (Dependables is SF TEP, shown as 1QB)

**Status:** fixed (2026-07-27, branch `teardown-remediation`, worktree agent batch).

## Root cause

MFL format detection **did not exist**. No MFL code path ever wrote
`leagues.default_scoring`: `upsert_platform_league` doesn't touch the column,
and the session-init auto-detect only knows how to read **Sleeper** league
meta (`_fetch_sleeper_league_meta` on an MFL id finds nothing → "detect
deferred" forever). So `get_league_scoring` fell to `DEFAULT_SCORING =
'1qb_ppr'` for every linked MFL league — the operator's SF TEP Dependables
league rendered (and traded) as 1QB.

## Detection rules (`mfl_service.detect_scoring_format`)

Sources are two MFL exports, both now part of the league bundle:

- **Superflex** — the `league` export's starting-lineup config
  (`league.starters.position`): the QB entry's `limit` string ("1", "2",
  "1-2"); **max startable QBs ≥ 2 → superflex**. (MFL has no named superflex
  slot — SF is expressed as a flexible QB limit.)
- **TE Premium** — the `rules` export's scoring rules: per-reception points
  (event `CC` = every reception caught) for **TE strictly greater than WR**
  → TEP. Handles MFL's JSON quirks: `{"$t": …}` text-node wrapping,
  single-member collections as bare dicts, `1.5*` "each"-suffixed points,
  multi-position rule groups (`"WR|TE"`).

**Collapse (mirrors the Sleeper convention** in
`server._detect_scoring_format_from_meta`, documented in
`docs/cross-client-invariants.md`): **SF or TEP → `sf_tep`; otherwise
`1qb_ppr`**. SF-without-TEP and TEP-without-SF both land in `sf_tep` — same
two-bucket rationale as Sleeper (QB scarcity dominates; TEP distorts TE value
toward the sf_tep board).

Degradation: `rules` fetch is best-effort (like `players`) — on failure TEP
is undetectable and detection falls back to the lineup signal alone; a
missing/trimmed `league.starters` yields no SF signal → honest `1qb_ppr`.

## Where it's set

- **Link time** — `POST /api/mfl/link` (import branch)
- **Re-sync** — `POST /api/mfl/import` (re-detects every time; also the
  manual fix-up path)
- **Auth import** — `POST /api/mfl/auth-import` (per league, via
  `_mfl_import_league_authed`)

All via the shared `server._mfl_store_scoring_format` (best-effort, runs
after `upsert_platform_league` since `set_league_scoring` is an UPDATE;
never fails the import).

## Fix-up for ALREADY-linked leagues

Options considered: (a) ask users to re-link (honest but manual — the mobile
app has no MFL re-sync button), (b) offline migration (impossible — the
format lives in MFL's API, not our DB), (c) lazy backfill. Shipped **(c)**:
`GET /api/mfl/leagues` — hit whenever the mobile league picker refreshes
(pull-to-refresh / empty cache; #199's new switcher entry point leads there
too) — checks each row and, when `default_scoring` is **NULL** (pre-#201
rows only), fetches just the two exports detection needs
(`fetch_scoring_inputs`: `league` + `rules`, ≥1s spacing, stored cookie for
`auth='cookie'` leagues) and stores the result. Bounded: at most one attempt
per league per process (`_mfl_scoring_backfill_attempted`); failures log and
leave the default. Re-linking / re-sync also heals, immediately.

Operator action for Dependables: open the league picker (or pull-to-refresh
it) once after deploy — or simply re-run the MFL sign-in import.

## Files

- `backend/mfl_service.py` — `detect_scoring_format` + helpers (`_txt`,
  `_max_qb_starters`, `_reception_points`); bundle gains best-effort `rules`;
  new `fetch_scoring_inputs`
- `backend/server.py` (MFL region only) — `_mfl_store_scoring_format`,
  calls in `mfl_link` / `mfl_import` / `_mfl_import_league_authed`,
  backfill in `mfl_leagues`
- Docs: `docs/api-reference.md` (MFL section),
  `docs/cross-client-invariants.md` (detection collapse convention)

## Tests

`backend/tests/test_mfl_service.py`:
`test_detect_sf_tep_league` (the Dependables case) ·
`test_detect_plain_1qb_ppr_league` ·
`test_detect_superflex_without_tep_collapses_to_sf_tep` ·
`test_detect_tep_without_superflex_collapses_to_sf_tep` ·
`test_detect_degrades_without_rules_export` ·
`test_detect_defaults_1qb_on_empty_bundle` ·
`test_fetch_bundle_includes_rules_and_degrades_on_rules_error` ·
`test_fetch_scoring_inputs_league_and_rules_only`

`backend/tests/test_mfl_link_route.py`:
`test_link_import_stores_sf_tep_format` ·
`test_link_import_stores_1qb_when_no_signals` ·
`test_import_resync_redetects_format` ·
`test_leagues_list_backfills_missing_format` ·
`test_leagues_list_skips_backfill_when_format_present`

## Verification

- `python3 -m pytest backend/tests -q` → **1359 passed, 1 skipped** (was
  1346 passed, 1 skipped before the 13 new tests)
