# Feature Scope — Dynasty Year in Review P0: roster-history capture

**Date:** 2026-08-14
**Entry point:** direct ask — pm-growth build brief #2, off
[`../../business/product/2026-08-13-dynasty-year-in-review-plan.md`](../../business/product/2026-08-13-dynasty-year-in-review-plan.md)
(operator decisions **YR-1…YR-8**, binding) and the two reconciled reviews in this folder
([`review-data-architect-final.md`](review-data-architect-final.md) = build spec,
[`review-eng-architect-final.md`](review-eng-architect-final.md) = systems design).
**Builder:** eng-manager session, branch `feat/roster-history` (worktree)
**Base:** `origin/main` @ `5dcf29f` (the reviews cite `60fccc7`/`4a4b671`; drift re-verified —
see §6)
**Gates:** **FULL.** Schema + data collection — explicitly not express-eligible (root
`CLAUDE.md` bright line, restated in both reviews and the brief).
**Operator sign-off on waivers:** yes — D-P1-08 (no Maestro / no simulator) restated in the
brief; all other sections answered.

---

## 1. Analytics scope

**(b) Existing events cover it.** P0 is capture-only: no client surface, no user-facing
behavior, and therefore **no new analytics events**. What P0 emits is operator telemetry
(tick counters, per-league fetch-ms logs), which is logging, not analytics.

Named for the record:

- `wrapped_viewed` is already reserved in `SERVER_FIRED_EVENTS` and has never fired — it
  belongs to **P3**, with the nine recap events, registered via a
  `docs/business/analytics/` addendum before any emitter (the M10 discipline).
- The `source` column on `league_roster_history` is the **liveness instrument** for the
  scheduled path (zero `'weekly'` rows one week post-ship ⇒ `daily-tick` is not firing) —
  a schema-borne measurement, not an event.

## 2. Schema & flag scope

- **New tables (2):**
  - `league_roster_history` — append-only ownership-side snapshots, key
    `(league_id, team_key, scoring_format, period_key)`; `team_key` is always the
    platform-native team slot; `period_key` is an ISO-week bucket label using the ISO
    week-numbering year. Full DDL: [`review-data-architect-final.md`](review-data-architect-final.md) §5
    + the two R3 amendments (`pick_ids_excluded`; `source ∈ 'sync'|'weekly'|'backfill'`).
  - `league_board_history` — weekly complete board snapshots (C5/C6, YR-3), key
    `(user_id, league_id, scoring_format, period_key)`. `elo_history` stays untouched as
    the event log.
- **New indexes:** 3 on `league_roster_history`, 2 on `league_board_history`, plus
  `ix_pvh_format_date` on the existing `player_value_history` (added to the idempotent
  index list in `_migrate_db`).
- **Tables are created unconditionally** (`metadata.create_all`); the flag gates writes at
  call sites only, so flipping it mid-season is a behavior change, never a schema surprise.
- **New feature flag:** `market.roster_history`, **default ON at merge** — matching the
  three sibling capture flags in the same daemon (`market.trade_capture`,
  `sleeper.trade_block`, `picks.owned_sync`). D-P1-07 does not bar it: that decision is
  about read routes with external references; this gates a write with none. One flag, one
  direction — P3's read routes get their own.
- **New env var:** `FTF_ROSTER_SNAPSHOT_WEEKDAY` (default 1) — the `daily-tick` weekday
  `>=` gate; setting `7` disables only the sweep while on-sync capture keeps running (the
  deploy-free kill lever for the worker-blocking half). → `docs/config-reference.md`.
- **New notification type (1):** `espn_reconnect` — the YR-8 "reconnect ESPN" nudge when a
  private-league sweep hits an expired stored cookie. Cross-client enum obligations apply
  (both glyph maps, both tap routers, `check-notif-glyphs.js`,
  `docs/cross-client-invariants.md`) — this is the one part of P0 that is not server-only.

## 3. Test scope

- **Maestro: WAIVED** — D-P1-08 (standing operator policy, restated in the brief). P0 has
  no mobile-visible surface beyond one notification row type, which renders through the
  already-tested bell pipeline.
- **Simulator gate: WAIVED** — same decision; `FTF_SKIP_SIM_GATE=1` on push with the
  TEST_LEDGER note.
- **Backend pytest:** `backend/tests/test_roster_history.py` (new) — idempotency (double
  run, one row), **precedence not recency** (`weekly` outranks `sync`; sync-after-weekly is
  a no-op; sync-after-sync updates), the **ESPN transaction-isolation** rule (a snapshot
  failure must never roll back the membership delete+insert), orphan-team retention,
  zero-coverage ⇒ `team_value` NULL never 0, the ISO week-numbering-year boundary
  (2026-12-31 ⇒ `2027-W01`), hash-never-suppresses-the-weekly-write, board-snapshot
  idempotency + `board_updated_at` semantics, contested ESPN picks ⇒ `pick_ids_excluded`.
- **Mobile:** `check-notif-glyphs.js` extended for `espn_reconnect` (the suite reads all
  four client tables).
- **testID delta:** none.
- **Capture delta:** none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/architecture.md` | **updated** | **fix the `:230` drift FIRST** (claims a `value-snapshot-daily` cron reverted same-day in `1e50d3e`; `runbook.md` has the truth) + Cron-ticks row for `/api/cron/roster-snapshot` |
| `docs/api-reference.md` | **updated** | `POST /api/cron/roster-snapshot`; `daily-tick` response gains `roster_snapshot` counters |
| `docs/data-dictionary.md` | **updated** | two new tables + `ix_pvh_format_date` |
| `docs/config-reference.md` | **updated** | `market.roster_history` + `FTF_ROSTER_SNAPSHOT_WEEKDAY` |
| `docs/runbook.md` | **updated** | roster-snapshot monitoring: the `source`-column liveness read + the retirement rule |
| `docs/cross-client-invariants.md` | **updated** | `espn_reconnect` joins the notification-type enum |
| `docs/adr/adr-011-league-state-history-is-append-only.md` | **new** | decision + consequences: re-stamp-is-not-a-mutation, grey-don't-interpolate rendering rule, the `wrapped_events`→`user_events` cutover seam (P3), the ESPN-credential scope extension (YR-8), the power-rankings value contract, the daemon/budget pairing, retention policy for the snapshot family |
| `living-memory/HLD.md` / `LLD.md` | **updated** | append-only league state is a convention shift |
| `DECISIONS.md` | **updated** | the scheduling inversion (on-sync co-primary) — a deviation from the plan's reading of YR-1, already operator-blessed via the brief |
| `docs/glossary.md` | **updated** | "period key", "team key", "capture vs fetch" |

## 5. Ship gate declaration

- **Simulator-gate tier:** **4 — none, CI only** (D-P1-08; server-only change plus one
  notification row type). Evidence: TEST_LEDGER entry naming the waiver; no
  `qa/sim-runs/last-sim-run.json` (no run to record).
- CI green before merge; secrets rules and the recovery ledger apply.

## 6. Premise checks — drift since the reviews (verified at `5dcf29f`)

1. **`replace_espn_league_members` has SEVEN callers now, not three** — ESPN link + import,
   MFL link + import + auth-import, Fleaflicker link + import. All seven build `members`
   in loops where the platform-native team id is in scope, so the team-key threading is
   mechanical at every site. The isolation rule (own transaction, after theirs commits)
   is unchanged and applies to all seven.
2. **Every line number in the reviews has shifted** (`upsert_league_members` :5541,
   `replace_espn_league_members` :10168, `_fetch_league_rosters` :10569, daemon blocks
   ~:15330-15460, `_run_weekly_replenishment` :16231→ moved, etc.). Verified by content;
   nothing structural changed.
3. **The crossed R3s disagree on the hourly guard** (data-architect dropped it on the
   perfectly-correlated-blueprint argument; eng-architect accepted it with a
   guard-not-sweep condition). The coordinator's brief states the final topology —
   **three triggers, no hourly guard** — and that is what ships: on-sync (Writer A),
   `daily-tick` weekday gate (Writer B), `POST /api/cron/roster-snapshot` (Writer C,
   manual/external lever).
4. **YR-8 post-dates both reviews** and overrides their "ESPN/MFL weekly fetchers not in
   P0" deferral: the weekly sweep fetches server-side on all four platforms, reusing the
   existing fetch/parse/map helpers the import routes already call. The eng review's
   platform-parity restatement (D3) is superseded by the operator's ruling.
