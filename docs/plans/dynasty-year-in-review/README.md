# Dynasty Year in Review (#46 "Wrapped") — initiative thread

> **Status:** design reconciled 2026-08-13. **Not built.** P0 capture is time-critical.
> **Product plan (owner doc):** [`../../business/product/2026-08-13-dynasty-year-in-review-plan.md`](../../business/product/2026-08-13-dynasty-year-in-review-plan.md)
> **Base:** `origin/main` @ `4a4b671`.

## What this is

Capture dynasty roster/value history in-season so a year-end recap can exist. The recap is a
growth artifact; **the capture is the time-critical part** and stands on its own justification
(operator ruling YR-7) because it also feeds #33 value-movers and #17 player profiles.

**The core finding:** a team's value is `roster × values`. `player_value_history` has logged the
values side daily since 2026-07-26. `league_members.roster_data` (`backend/database.py:327`) is
**overwritten on every sync**, so the ownership side has zero history. Every attribution stat in
the recap is a join between a table that exists and a table that does not.

## Documents

| Doc | What it is |
|---|---|
| [`../../business/product/2026-08-13-dynasty-year-in-review-plan.md`](../../business/product/2026-08-13-dynasty-year-in-review-plan.md) | **The owner doc.** Product framing, in-year vs end-of-season capture split, recap content tiers, growth analysis, operator decisions YR-1…YR-7 |
| [`review-data-architect-final.md`](review-data-architect-final.md) | **The build spec.** Final DDL for `league_roster_history` + `league_board_history`, write path, idempotency, volume, query shape, backfill, event taxonomy |
| [`review-eng-architect-final.md`](review-eng-architect-final.md) | **The systems design.** Write seam, transaction isolation, scheduling topology, platform abstraction, flagging, rollback, ADR sketch, P0 sequence |
| [`review-data-architect-r1.md`](review-data-architect-r1.md) · [`review-eng-architect-r1.md`](review-eng-architect-r1.md) | First-pass independent reviews, retained for the reasoning trail |

Both reviewers ran three rounds against each other. **No disagreements remain.** Where they
converged by one conceding, the reasoning is preserved in the final docs rather than rewritten.

## The design in one paragraph

One append-only table, **three write triggers, one idempotent writer**, keyed
`(league_id, team_key, scoring_format, period_key)` where `period_key` is an ISO-week bucket
label, never an instant. **Trigger 1 (on-sync)** hangs off the two `league_members` writers, in
its own transaction *after* theirs commits, and depends on no scheduler. **Trigger 2** is the
`daily-tick` weekday gate — the `_run_weekly_replenishment` house pattern. **Trigger 3** is
`POST /api/cron/roster-snapshot`, a manual/external lever. `team_key` is **always the
platform-native team slot, never derived from a user id**. Behind `market.roster_history`,
default ON.

## Three things a builder must not get wrong

1. **Never write the snapshot inside `replace_espn_league_members`' `engine.begin()` block**
   (`database.py:10110-10116`). It does delete+insert; a snapshot failure there rolls back the
   membership write and leaves the league with **zero members**.
2. **`team_value` is `compute_power_rankings`' consensus-basis total, not a fresh summation.**
   That function already ships and already solves K/DEF pricing, basis choice and the starters
   split. A fresh sum makes the Wrapped chart and the Power Rankings screen disagree about the
   same team, with no way for a user to tell which is right.
3. **Precedence, not recency, on upsert.** `cron` outranks `sync`. A client-driven app-open
   posts rosters with ownerless teams already dropped, so last-write-wins lets a Friday sync
   silently delete a swept week's orphan teams — breaking operator ruling YR-6 invisibly.

## Open, and owned elsewhere

| Item | Owner |
|---|---|
| **Gate 0** — is anything on the Render blueprint actually firing? `SELECT snapshot_date, count(*) FROM player_value_history GROUP BY 1 ORDER BY 1 DESC LIMIT 30;` Changes priorities, not the design | Operator |
| ~~§7's platform-agnostic growth claim — restate or strike~~ **RESOLVED 2026-08-14, operator ruling YR-8: make it TRUE.** The weekly sweep fetches server-side on **all four platforms** — Sleeper (public), MFL (`rosters` export is public, `mfl_service.py:432` accepts `cookie=None`; only `pendingTrades` is owner-restricted), Fleaflicker (public API, zero auth, `fleaflicker_service.py:15`), ESPN (public leagues cookie-free; private leagues via the linking user's stored `espn_credentials` — Fernet-encrypted `espn_s2`+SWID, `database.py:1355`, `expires_hint_at` tracked). The reviewers' shared premise that ESPN/MFL capture was structurally app-open-driven was a fact about the *current sync path*, not the platforms. **Consequences for the build spec:** (1) the Writer-B weekly sweep gains per-platform fetch adapters in **P0** — thin wrappers over `fetch_league` / `fetch_rosters` / `fetch_league_bundle`, which already exist; (2) an expired ESPN-private cookie degrades to on-sync capture **plus a "reconnect ESPN" nudge** — visible re-auth ask, never a silent gap (`team_key` is unaffected: it is the platform slot, not the credential holder); (3) background use of a stored user credential in a scheduled job is a modest scope extension of that credential's existing server-side league-read purpose — record it in the ADR's consequences; (4) the D1 daemon-thread default and the per-league fetch budget now cover four platforms' calls, reinforcing the thread-by-default ruling | **Closed** |
| P0a cost, 1–2 weeks | pm-technical |
| `docs/architecture.md:230` is **drifted and false** — claims a `value-snapshot-daily` cron provisioned at 06:00 UTC; it was added and reverted same-day (`1e50d3e`). Contradicts `runbook.md:295` | Fix as part of P0 |
