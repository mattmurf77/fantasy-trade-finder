# #258 — MFL team names show HTML entities (reopened as #282: markup, not entities)

**Covered feedback IDs:** #258 (2026-08-06), #282 (2026-08-09, reopens #258)
**Branch:** worktree-agent (from `origin/main` @ ef9bbaa) · **Date:** 2026-08-09
**Status:** #258's entity-decode fix shipped but did not resolve the operator's
complaint — root cause was franchise name color/formatting markup, not HTML
entities. #282 extends the cleaner to strip that markup too. Regression tests
verified failing-first; full backend suite green.

## The bug (operator, verbatim)

#258 original report:

> "Some of the mfl teams have weird characters in the team name. I believe it's
> html. We should strip that from team names."

#282 reopen, after #258 shipped:

> "Still have the nonsensical characters in the team names. It's not &amp;
> that's an issue.. it's code that is in the names to add color to their
> names on MFL."

## Root cause (#282)

#258 correctly identified that `mfl_service._clean_text` needed to run over
already-stored MFL rows (the backfill), but **misdiagnosed the junk itself**
as HTML entities. The operator confirmed entities were never the problem:
**MFL lets franchise owners style their team name**, and the raw name string
MFL serves carries that styling as inline markup — not just plain text.

Queried prod (`DATABASE_URL_PROD`, read-only) for `league_members` /
`leagues.name` where `platform = 'mfl'` (league 62846, "The Dependables
League") and found the real dirty strings still sitting in the DB after
#258's entity-decode backfill had already run:

- franchise f0001 (`league_members.username` / `display_name`, plus every
  `draft_picks.owner_username` / `original_username` snapshot for that
  franchise):
  ```
  <b><font color = Green>Eir</font color><font color = White>e Reb</font color><font color = Orange>els</font color></b>
  ```
  → should render as `Eire Rebels`.
- franchise f0012:
  ```
  <b><font color= Green>North London Rams</b>
  ```
  → should render as `North London Rams` (note: malformed markup — no
  closing `</font>`, only a trailing `</b>`).

No `&amp;`/`&#NNN;` entities were present in either row — #258's fix had
nothing to decode here, which is exactly why the operator still saw junk
after it shipped. The markup itself arrives **entity-encoded on the wire**
(`&lt;font color = Green&gt;...`), which is why #258's entity-decode step
still matters — it's what turns the encoded markup into the literal
`<font...>` tags seen above; #258 just never went the extra step of
stripping the tags themselves.

## Fix — extend `mfl_service._clean_text` to strip the markup too

`backend/mfl_service.py`:

- added `_MARKUP_TAG` — a regex matching `<`/`</` + one of MFL/HTML's
  formatting tags (`b`, `i`, `u`, `strong`, `em`, `font`) + any attributes,
  case-insensitive, including malformed closing tags that carry an attribute
  (`</font color>`, seen in the raw f0001 string before #258's decode step
  normalizes it);
- `_clean_text` now runs, in order: (1) entity-unescape until stable — must
  come first because the markup itself arrives entity-encoded, (2) strip
  `_MARKUP_TAG` matches, (3) collapse whitespace runs. Getting the order
  right matters: stripping tags before unescaping would miss markup that's
  still `&lt;font...&gt;` at that point;
- scoped to a known tag allowlist (not a blanket `<[^>]*>` strip) so a
  legitimate literal `<` or `>` in a team name is never mangled — the only
  tags MFL's styling feature and the captured samples actually use.

Because every MFL ingest path (`parse_bundle`, `fetch_my_leagues`) and the
#258 backfill (`database._backfill_mfl_name_entities`) both call
`mfl_service._clean_text`, this one change re-cleans both new imports and
already-stored rows — no separate migration needed. Verified: the backfill's
`_cleaned()` helper only rewrites a row when `_clean_text(value) != value`,
and both captured dirty strings satisfy that with the new cleaner (they did
not with the old one, since neither contains entities).

## Regression tests

`backend/tests/test_mfl_service.py` — new
`test_clean_text_strips_mfl_franchise_color_markup` using the real captured
f0001/f0012 strings (both the entity-encoded wire form and the
already-literal stored form), plus a malformed-markup case and a
plain-name-untouched case. Verified failing-first: fails against pre-#282
`_clean_text` (asserts the literal markup string was passed straight
through), passes post-fix.

`backend/tests/test_mfl_name_backfill.py` — extended `_seed()` with the real
f0012 markup-only dirty row (no entities) and added assertions to
`test_backfill_decodes_stored_mfl_names` that the backfill cleans it via the
improved `_clean_text`. Verified failing-first against pre-#282
`mfl_service.py` (`AssertionError: '<b><font col...ndon Rams</b>' ==
'North London Rams'`), passes post-fix. Existing entity-decode coverage
(named/numeric entities, Sleeper-row exclusion, idempotency, `_migrate_db`
wiring) is untouched and still green.

## Verification

- New/extended tests fail against pre-#282 code, pass post-fix (both files,
  confirmed individually via `git stash`).
- Full suite: `python3 -m pytest backend/tests -q` → **2054 passed, 1
  skipped** (baseline 2053 + 1 new test function), exit 0.
- No mobile changes for this item.
- Prod effect: first Render boot after merge re-runs
  `_backfill_mfl_name_entities()`, which now rewrites the markup-bearing rows
  (nothing else changes — non-MFL and already-clean rows are untouched).
