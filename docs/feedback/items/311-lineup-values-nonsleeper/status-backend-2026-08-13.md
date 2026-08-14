# Backend wave status — #311 + #318 (backend half) — 2026-08-13

> Build agent deliverable, branch `wave-backend`, base `origin/main` @
> `60fccc7` (plan commit `3155322` on top). **#313 was NOT built** — it
> awaits the operator's value-side vs label-side decision, per the brief.

## What shipped (commits, oldest first)

| Commit | Content |
|---|---|
| `188eafd` | #311: `_league_lineup_slots` + `_starter_impact` call-site swap + 7 tests |
| `34b440f` | #318 backend: `retracted_at` column, migration, 3 query filters, `retract_awaiting_likes`, route |
| `2c7a250` | #318 analytics: `awaiting_trade_dismissed` registration (registration-only, additive) |
| `79e2e50` | #318 tests: `test_awaiting_dismiss.py` (14) + 2 receiver-side filter tests |
| (this) | scope block + this status doc |

## Changes at file:line (final tree)

**#311**
- `backend/server.py:20025` — new `_league_lineup_slots(league_id)`:
  leagues-row lookup (platform, default_scoring); `espn|mfl|fleaflicker` →
  `_MOCK_DEFAULT_LINEUP` (+ `SUPER_FLEX` when `default_scoring='sf_tep'`,
  NULL reads `1qb_ppr`); `sleeper`/NULL platform → `_sleeper_lineup_slots`
  byte-identical; no leagues row or other platform → None.
- `backend/server.py:1163` — `_starter_impact` template resolution switched
  to `_league_lineup_slots`. **Only** call site switched: mock draft
  (`server.py`, `_MOCK_DEFAULT_LINEUP` fallback) and power rankings
  untouched — the plan's two scope calls landed as briefed (fleaflicker
  **included**; power-rankings call site **deferred**). Phase-2 real-template
  extraction not built (plan follow-up).
- `backend/tests/test_trade_evaluate.py` — `_install_starter_world` and the
  RB-tie test re-seamed from `_sleeper_lineup_slots` to the new helper;
  7 new tests (plan tests 1-6 + a fleaflicker variant).

**#318 backend**
- `backend/database.py:324` — `trade_decisions.retracted_at` (String,
  nullable; NULL = live) with in-schema comment.
- `backend/database.py:2008` — additive boot-migration row
  (`VARCHAR`, existing rows backfill as NULL = live).
- `backend/database.py:4468` — `load_recent_league_likes` filter (receiver's
  likes-you deck injection). `:6617` — `check_for_match` filter (match
  maturation). `:6909` — `load_awaiting_trades` filter (dismisser's list).
- `backend/database.py:7028` — `retract_awaiting_likes(user_id, league_id,
  give, receive) -> int`: selects the caller's live like rows in the league,
  compares frozensets in Python (JSON ordering makes SQL set-equality
  impossible), updates all matching ids in one statement inside
  `engine.begin()`.
- `backend/server.py:13098` — `POST /api/trades/awaiting/dismiss`
  (`@_gate_unverified_write`, beside `dismiss_trade_match`): frozen contract
  verbatim; partner-deck `_invalidate_trade_jobs(user_id=partner,
  league_id=league)`; event fired only when `dismissed_likes >= 1`.
- `backend/server.py:111` — `retract_awaiting_likes` import.
- `backend/analytics_taxonomy.py:341-354` — `awaiting_trade_dismissed`
  registered in `SERVER_FIRED_EVENTS` (strictly additive; props documented
  in place; NOT in `NON_INTENT_EVENTS` → INTENT by the existing formula).
- `_past_decision_keys` deliberately unchanged (`load_trade_decisions` still
  returns retracted rows) — sabotage T9 proves a filter there fails a test.

## Real response bytes (from the live route under test harness)

```
200 first  : {"dismissed_likes":1,"status":"ok"}
200 repeat : {"dismissed_likes":0,"status":"ok"}
400 missing: {"error":"league_id, my_give, my_receive, partner_id are required"}
400 no user: {"error":"session not initialised"}
```

(Flask serializes keys alphabetically; field set and values match the frozen
contract exactly. 0 is ok — never a 404; verified idempotent.)

## Pytest — baseline vs final (actual output)

- Baseline, base tree before any change:
  `2714 passed, 1 skipped in 337.46s (0:05:37)`
- Final, full suite on the finished tree:
  `2737 passed, 1 skipped in 267.56s (0:04:27)`
- New tests added: 7 (#311, `test_trade_evaluate.py`) + 14
  (`test_awaiting_dismiss.py`) + 2 (`test_trade_match_flow.py`) = **23**;
  2714 + 23 = 2737 — no pre-existing test lost or newly skipped.

## Sabotage matrix (every behavioural test proven RED, then reverted CLEAN)

Guard: after each mutation run, `git checkout` + `git diff --quiet` verified
(printed CLEAN on all 16 runs).

| # | Named sabotage (plan) | Mutation applied | Test | Result |
|---|---|---|---|---|
| 311-1 | Revert call site to `_sleeper_lineup_slots` | `server.py` call-site swap back | `test_espn_league_gets_standard_1qb_template` | `1 failed` → revert CLEAN |
| 311-2 | Hardcode 1QB template regardless of scoring | sf_tep comparison neutered | `test_espn_sf_tep_league_appends_super_flex_and_seats_second_qb` | `1 failed` → CLEAN |
| 311-3 | Branch on `platform == 'espn'` only | tuple → `("espn",)` | `test_mfl_league_gets_standard_1qb_template` | `1 failed` → CLEAN |
| 311-3b | (same mutation, fleaflicker read) | tuple → `("espn",)` | `test_fleaflicker_league_gets_standard_1qb_template` | `1 failed` → CLEAN |
| 311-4 | Standard template for every platform incl. Sleeper | sleeper branch returns standard | `test_sleeper_league_template_still_meta_derived` | `1 failed` → CLEAN |
| 311-5 | Default template when no leagues row | `row is None` returns standard | `test_no_leagues_row_still_omits_starter_impact` | `1 failed` → CLEAN |
| 311-6 | `isdigit()` probe ahead of platform lookup | digit-first Sleeper probe inserted | `test_numeric_espn_id_never_fetches_sleeper_meta` | `1 failed` → CLEAN |
| 318-1 | Update only the first matching row | `break` after first append | `test_dismiss_marks_every_duplicate_like_row` | `1 failed` → CLEAN |
| 318-2 | Omit filter in `load_recent_league_likes` | filter line removed | `test_retracted_like_excluded_from_recent_league_likes` | `1 failed` → CLEAN |
| 318-3 | Omit filter in `check_for_match` | filter line removed | `test_retracted_like_never_matures_into_match` | `1 failed` → CLEAN |
| 318-4 | 404 when no rows update | `dismissed == 0 → 404` | `test_repeat_dismiss_is_idempotent_200_zero` | `1 failed` → CLEAN |
| 318-5 | Key-based dismissals-table semantics | atomic composite: SQL filter removed + key-level suppression in the loop (blocks the revived row; dismiss itself still works — paired test 1 stayed green) | `test_relike_after_dismiss_revives_awaiting` | `1 failed, 1 passed` → CLEAN |
| 318-6 | Route dismiss through the pass path | `.values(..., decision="pass")` | `test_dismiss_writes_no_swipes_and_keeps_decision` | `1 failed` → CLEAN |
| 318-7 | Forget the `user_id` predicate | predicate removed from retract select | `test_dismiss_never_marks_partners_own_rows` | `1 failed` → CLEAN |
| 318-8 | Invalidate the caller's deck instead | `partner_id` → `g_user_id` | `test_dismiss_invalidates_partners_deck_job` | `1 failed` → CLEAN |
| 318-9 | Filter retracted rows out of past-decisions load | `.where(retracted_at IS NULL)` added to `load_trade_decisions` | `test_past_decisions_load_still_sees_retracted_rows` | `1 failed` → CLEAN |

Process note: the first attempt at 318-5 mis-sequenced the two-part
mutation (second edit applied after the first was auto-reverted), producing
a false `1 passed`; it was caught and re-run as one atomic composite. This
is exactly the false-pass class the RED-first discipline exists for.

## Migration / fixture findings (G-034 check)

- Old-schema SQLite DB (no `retracted_at`), migration loop applied: column
  added, pre-existing row reads `retracted_at IS NULL` (= live, the correct
  backfill), second application idempotent (try/except per-column, matching
  `_migrate_db`'s per-statement transaction pattern — Postgres-safe).
- `backend/tests/fixtures/seed_ui_test_db.py`: **seeds no `trade_decisions`
  rows** (grep of `backend/tests/fixtures/` for `trade_decisions` is empty),
  so no fixture is in the migration's cohort and no seeder/capture edit is
  required. Fresh DBs get the column from `metadata.create_all`; seeded
  UI-test DBs gain it harmlessly at Flask boot via the additive ALTER.
  No G-034-style coupled edits needed.

## Proposed doc rows (orchestrator applies — shared docs untouched by this group)

**`docs/api-reference.md`** — new route block (place beside
`POST /api/trades/matches/<id>/dismiss`):

```
POST /api/trades/awaiting/dismiss                                    (#318)
Auth: session token; @_gate_unverified_write (same gate as
      /api/trades/matches/<id>/dismiss)
Body (JSON, all fields required):
  { "league_id": "<string>", "my_give": ["<player_id>", ...],
    "my_receive": ["<player_id>", ...], "partner_id": "<string>" }
Marks EVERY trade_decisions row of the CALLER with decision='like', the
same league_id, and set-equal give/receive (order-insensitive, frozenset —
load_awaiting_trades' dedup key) as retracted_at=<now ISO UTC>. No Elo
signal, no swipe row, no effect on trade_matches. partner_id is used ONLY
to invalidate that user's cached trade-deck job (best-effort, in-process).
200 {"status": "ok", "dismissed_likes": <int >= 0>}   — 0 is still ok
    (idempotent repeat, or key already matured/absent — never a 404)
400 {"error": "league_id, my_give, my_receive, partner_id are required"}
400 {"error": "session not initialised"}
A like re-swiped AFTER a dismissal writes a fresh live row and the trade
legitimately reappears in Awaiting.
```

Plus, on the trade-evaluate `starter_impact` field, the existing sentence
"…via `power_rankings.optimal_starters` over the league's Sleeper slot
template (same `_sleeper_lineup_slots` path as `/api/league/power-rankings`;
derived value-optimal lineup, NO per-week data)" becomes: "…via
`power_rankings.optimal_starters` over the league's slot template
(`_league_lineup_slots`, #311: Sleeper leagues use live `roster_positions`
via the `_sleeper_lineup_slots` path; ESPN/MFL/Fleaflicker platform leagues
use the standard scoring-format template — QB/2RB/3WR/TE/FLEX, +
SUPER_FLEX for sf_tep; no leagues row/demo → field omitted. Power-rankings
keeps the Sleeper-only path; derived value-optimal lineup, NO per-week
data)".

**`docs/data-dictionary.md`** — `trade_decisions` table (its `| Column |
Type | Notes |` format), new row after `created_at`:

```
| `retracted_at` | str, nullable | ISO UTC; NULL = live like (#318 awaiting-dismiss). Set (never cleared) by `POST /api/trades/awaiting/dismiss` on every like row sharing the dismissed trade's `(league_id, give-set, receive-set)` key. Retracted rows are invisible to `load_awaiting_trades` / `load_recent_league_likes` / `check_for_match`, but stay visible to swipe-Elo history, impressions joins and the past-decisions deck suppression (deliberate). A re-like writes a fresh NULL row — the revive path. Additive boot migration; existing rows correctly backfill as NULL. |
```

**`docs/glossary.md`** — two terms:
- *Standard lineup template* — the scoring-format-keyed fallback starting
  lineup (QB/2RB/3WR/TE/FLEX; sf_tep appends SUPER_FLEX) used for platform
  leagues (ESPN/MFL/Fleaflicker) that expose no `roster_positions`
  equivalent; slot filling stays value-optimal (#311).
- *Retracted like* — a like the user dismissed from "Awaiting them";
  invisible to the counterparty's deck injection and to match maturation;
  a fresh like revives the trade (#318).

**Tracking-plan addendum** (placement orchestrator-owned):
`awaiting_trade_dismissed` — server-fired, INTENT, props
`{partner_id, dismissed_likes}`, fires only when ≥1 row newly marked;
`league_id` on the envelope column. Client fires nothing.

## Known residuals (per plan, accepted)

- Receiver's client-held deck shows the card until their next generate
  (same staleness class as untouchables); server cache handled by the
  invalidation touch point.
- Already-sent push/inbox notifications for the like are not retracted.
- The like's original Elo signal is not undone (dismiss ≠ decline,
  `dismiss_match` doctrine).

## Plan defects found

None blocking. One reconciliation worth recording: the plan's step-4 "no
leagues row → None" required re-seaming two existing monkeypatches in
`test_trade_evaluate.py` from `_sleeper_lineup_slots` to the new helper
(their fake league ids have no leagues row); the tests' asserted behavior
is unchanged. The plan did not mention this test-seam consequence but it is
mechanical, not a design gap.
