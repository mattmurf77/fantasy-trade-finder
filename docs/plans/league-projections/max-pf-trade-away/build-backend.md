# Max PF moves: backend build and code-walk (v1)

> Backend half of v1 on `feat/max-pf-moves`, 2026-11-12, commits B1–B8 of [plan.md](plan.md),
> against [contract.md](contract.md). Line numbers are on this branch. The app half is
> [app-evidence.md](app-evidence.md) (branch `feat/max-pf-moves-app`). Test and sabotage record:
> `living-memory/TEST_LEDGER.md`, 2026-11-12 Max PF moves.

- [1. Commits](#1-commits)
- [2. Code-walk: capture to the app](#2-code-walk-capture-to-the-app)
- [3. How the trade deadline reaches the block](#3-how-the-trade-deadline-reaches-the-block)
- [4. Flag off](#4-flag-off)
- [5. Verified by running, verified by reading](#5-verified-by-running-verified-by-reading)
- [6. Left out](#6-left-out)

## 1. Commits

| Step | Commit | What |
|---|---|---|
| B1 | `9d17b918` | Flag `league.max_pf_moves` (off everywhere); `max_pf_moves` settings |
| B3 | `1a21d5db` | Capture side channel (made before B2: B2's parity test needs it) |
| B2 | `715ea135` | The pure calculation module |
| B4 | `e0e35250` | Weekly-job hook |
| B5 | `22fa9c86` | `leagues.draft_order_rule` + the POST route |
| B6 | `4dc3de54` | The forecast read composes `max_pf_moves` |
| B7 | `935b1b34` | Analytics registration + tracking-plan addendum + flags-endpoint test |
| — | `a0e3f757`, `9eb5742f`, `29a8e6cc` | CONTRACT CHANGE commits (text only) |
| fix | `8f5cb3f1` | Route classified FREE in `paywall_gate.ROUTES` and capped at 8 KB (found by the full suite) |
| B8 | this commit | Docs, living memory, this file |

## 2. Code-walk: capture to the app

1. **Dispatch → worker.** Unchanged: the weekly batch queues a baseline run; `service._run`
   claims it. `service.py:124-126` decides `moves` (flag on, `kind == "baseline"`, a fresh
   capture) and makes `sidecar = {}` only then.
2. **Capture.** `service.py:140-143` passes `sidecar=` only when `moves` (otherwise the call is
   exactly main's). In `provider.capture` (`provider.py:219`) the sidecar collects, per week,
   the most open slots of any team in either lane (`:540-541`), then keeps the best
   `open + SIDECAR_EXTRA_SLOTS` (`:216`) free agents per slot type from the list capture already
   built (`:628-637`); after the weeks it records the trade deadline and names (`:659-664`).
   Nothing is written to the snapshot.
3. **Forecast.** `simulate` (or a reused `prior`) as before; then `service.py:157` →
   `_attach_moves` (`:64-92`): settings, a reused block kept when its settings hash matches
   (`:73-75`), a stop at min(60 s, job start + 480 s) (`:77`, `MOVES_DEADLINE_SECONDS` `:17`)
   checked by the simulation's own checkpoint together with the job's lease and foreground
   yield (`:79-83`), then `maxpf_moves.compute` (`:84`). Any exception, the stop included,
   returns the result without a block (`:88-91`). With the flag off a block reused from an
   earlier flag-on run is dropped (`:158-160`).
4. **The calculation** (`maxpf_moves.py`). `_Context.lineups` (`:123-159`) rebuilds a
   team-week's lineup and max PF pools from `season_points.player_points` and runs
   `optimize` → `free_agent_fill` → `idp_bye_fill` / `optimize(hindsight)` → `free_agent_fill`
   exactly as capture does (`provider.py:519-545`). `parity` (`:162`) proves it on every
   team-week. `resolve` (`:192`) removes each roster player in turn. `compute` (`:315`) takes the
   top 8 drops, runs one shared 5,000-run "before" and one "after" per candidate on
   `_lowered` (`:248`), anchors "after" to the saved 250,000 figures (`_after_teams`, `:287`),
   ranks labels with `pick_projection.slot_ranks` (`_labels`, `:308`) and applies
   `passes_threshold` (`:268`). The block is saved at `result_json["max_pf_moves"]` by
   `store.finish`.
5. **Read.** `GET /api/leagues/<id>/projection-runs/latest` (`api.py` `league_projection_latest`)
   decodes the saved result once (`api.py:175`); `public()` (`:50-60`) strips the raw block from
   `run` and `attempt`. With the flag on (`:189-190`), `moves_block` (`:94-101`, never raises)
   reads the league's draft-order row (`database.py:13911`), the saved outlook, the Keep list,
   and builds a pricer (`:62-92`) from the injected `_league_pick_projection` / `_active_format`
   (`server.py:46484-46485`); `maxpf_moves.compose` (`:424`) decides the state in contract
   §4.1 order and adds pick values (the league's projection with this run's distribution for
   the viewer, priced by `pick_values.priced_pool_value`).
6. **Write.** `POST /api/leagues/<id>/draft-order-rule` (`api.py:193-215`) →
   `database.set_league_draft_order_rule` (`database.py:13923`); the next read carries it.
7. **App.** Reads the flag from `/api/feature-flags` (`flags_dict()`, every `FLAG_KEYS` key) and
   the block from the same forecast query it already makes; app-evidence.md §2.

## 3. How the trade deadline reaches the block

Sleeper league `settings.trade_deadline` → `provider.capture` (the league object it already
fetched, `provider.py:232`) → `sidecar["trade_deadline"]`, an integer in 1..98 or None (0, 99,
absent or a non-integer mean no deadline, `provider.py:660-661`) → `service._attach_moves` passes
it to `compute(trade_deadline=...)` (`service.py:84-86`) → saved in the block as
`trade_deadline` → at read `compose` returns `after_trade_deadline` when
`saved.completed_weeks >= trade_deadline` (`maxpf_moves.py:463-465`), after the
unavailable / season-over checks and before the draft-order check. It is re-read every weekly
run, so a commissioner's change lands with the next forecast.

## 4. Flag off

- Job: `moves` is false, capture is called without `sidecar` (the exact main call), no settings
  read, no compute; `test_maxpf_moves_job.py::test_flag_off_saves_exactly_what_main_saves`
  pins `result_json` (byte-equal to `store.dumps(simulate(...) + the two keys _run adds)`),
  `snapshot_json` (equal to a sidecar-free capture) and that capture saw only `viewer_user_id`.
- Read: no key added; `public()` stripping is a no-op for any run saved without a block (every
  run on main). `test_maxpf_moves_read.py::test_flag_off_read_is_unchanged_with_or_without_a_saved_block`
  pins byte identity between a run saved with and without a block. A scratch run against
  `origin/main`'s own `api.py` (loaded from `git show`) gave byte-identical `/latest`,
  `/projection-runs/<id>` and `/teams` responses for a run without a block.
- Route: 404 `feature_disabled`.

## 5. Verified by running, verified by reading

**Running (local, Python 3.12, synthetic fixtures only):** every test named in the ledger entry;
the sabotages; the cost (about 6.5 s and 37 KB for the 14-week, 12-team fixture with 8
candidates); the flag-off comparison with main's `api.py`; the migration on an existing SQLite
database.

**Reading only:** Postgres for the two new columns (they go through the same `_migrate_db`
`ALTER TABLE ... ADD COLUMN` path as `median_game`, `database.py:4489-4492`, which runs on
Postgres in production); production run times; real league data; the app on a device.

## 6. Left out

- The leave-one-out backtest (separate validation agent; the flag stays off until it is written
  up).
- D-240 pick pricing for leagues answering `reverse_standings` / `lottery_or_other`.
- Auto-run of the trade search from "Find trades", and the `calc.inline_home`-off limitation.
- A website version.
