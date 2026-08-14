# ADR-011 — League state gets an append-only history, written beside the snapshot tables it shadows

**Date:** 2026-08-14
**Status:** Accepted
**Author:** eng-manager session (from the reconciled `an-data-architect` × `eng-architect`
reviews in [`../plans/dynasty-year-in-review/`](../plans/dynasty-year-in-review/); operator
decisions YR-1…YR-8 binding)

## Context

Every league-state table in this codebase had **snapshot semantics**: `league_members.roster_data`
is replaced on every sync, `member_rankings` is delete+insert on every submit, `trade_block` is
replaced per sync, `draft_picks.owner_user_id` mutates in place. Meanwhile `player_value_history`
has logged the **market** side daily since 2026-07-26. A team's value is *roster × values* — we
were keeping one factor and overwriting the other, and every attribution stat in the planned
season recap (#46 Wrapped) is a join between a table that existed and a table that did not.
Roster churn peaks between camp cuts and Week 1, which is what made capture time-critical
(plan §1) and why P0 ships on its own justification (YR-7): the data cannot be created
retroactively, and it also feeds #33 and #17.

## Decision

Two append-only tables extend the `player_value_history` state-snapshot family:

- **`league_roster_history`** — one row per `(league_id, team_key, scoring_format, period_key)`.
- **`league_board_history`** — one complete board per `(user_id, league_id, scoring_format,
  period_key)`.

Three write triggers, one idempotent writer each (`backend/roster_history.py`), flag
`market.roster_history` (default ON) gating writes only:

| | Trigger | Scheduler dependency |
|---|---|---|
| A | On-sync, beside the two `league_members` writers — own transaction, **after** theirs commits | **None** |
| B | `daily-tick` weekday `>=` gate → daemon thread → budgeted stalest-first sweep, server-side fetch on **all four platforms** (YR-8) | `daily-tick` firing |
| C | `POST /api/cron/roster-snapshot` — manual/external lever, no weekday gate | None (nothing schedules it) |

### The load-bearing lines

1. **`team_key` is always the platform-native team slot** (`sleeper:<lid>.r<id>`,
   `espn:<lid>.t<id>`, `mfl:<lid>.f<id>`, `fleaflicker:<lid>.t<id>`), never derived from a
   user id. ESPN's synthetic member id is SWID-first and SWID rotates on re-import, so a
   user-derived key splits one team's season into partial charts with no error anywhere.
   Root cause noted for the record: **all four platforms hand us this id at the exact line
   where membership is written, and `league_members` discards every one** — that omission is
   behind the ESPN identity churn, the orphaned-pick class, and the my-team swap. This is the
   first table to keep it; if `league_members` is ever fixed, `team_key` is the model.
2. **`owner_user_id` is a nullable, re-stampable attribute** — resolved forward at link time
   via `leagues.espn_my_team_id` / `platform_my_team` (`restamp_roster_history_owner`). The
   re-stamp does **not** violate append-only: the fact ("team T held roster R in period P")
   never changes; only our knowledge of who was behind T does. It is also what makes the
   late-joiner claim (plan §5.3) true on every platform.
3. **`period_key` is a bucket label in the ISO week-numbering year**, never an instant — an
   instant in the key enforces nothing (two runs, two rows). Correction recorded here: the
   review's boundary example ("2026-12-31 is 2027-W01") was wrong — 2026 is a 53-week ISO
   year and that date is `2026-W53`; the real crossing is 2025-12-29 ⇒ `2026-W01`. The
   principle stands and is pinned in `test_roster_history.py`.
4. **Precedence, not recency, on upsert:** `weekly` (server-fetched, every team, orphans
   included) outranks `sync` (client-posted, ownerless rosters already dropped). The on-sync
   writer does nothing when a weekly row holds the period; the weekly writer always updates
   and is **never hash-suppressed** (`team_value` moves weekly even when the roster does not).
   Recency would let a Friday app-open silently delete the week's orphan teams (YR-6).
5. **The value contract:** `team_value` is `compute_power_rankings`' consensus-basis players
   total, priced through the same `_power_picks_by_owner` as the Power Rankings screen — the
   recap chart and that screen are **contractually the same number**; any divergence is a
   recorded decision, not an accident. This inherits the codebase's written-down K/DEF rule
   (out-of-pool players contribute 0.0), which `valued_player_count` + `value_basis_date`
   then make legible.
6. **NULL, never 0, when nothing prices**, and the rendering rule for every consumer: grey
   any week where `team_value IS NULL` or `valued_player_count < 0.8 × player_count`, and
   **never interpolate**. `starter_ids` stores the platform-set lineup (the historical fact);
   the optimal lineup is an analysis, derivable at read time — inputs are captured, outputs
   computed.
7. **Contested/orphaned ESPN pick slots are skipped AND counted** (`pick_ids_excluded`,
   per-owner). A snapshot must never record a coin-flip, and silently skipping is the same
   defect as `team_value = 0` — an absence rendered as a fact. Non-empty exclusions ⇒ the
   recap suppresses pick flow for that league entirely; `pick_source='user'` rows are never
   rendered as fact (ADR-010). The pick fold runs **last** in the session-init daemon, after
   the owned-pick sibling block settles `draft_picks`.
8. **`league_board_history` is deliberately not a fork of `elo_history`**, which stays
   untouched as the event log: changed-only writes cannot rebuild a complete board, it has no
   uniqueness constraint (a weekly append would not be idempotent), and row-per-player weekly
   is ~270× the rows of JSON-per-board. Different grain, different question.
9. **Credential scope extension (YR-8), recorded explicitly:** the weekly sweep uses the
   linking user's stored, Fernet-encrypted `espn_s2`+SWID to read their **private league's
   rosters in the background** — an extension of the credential's existing server-side
   league-read purpose from request-time to scheduled use, operator-approved. An expired or
   undecryptable cookie degrades to on-sync capture **plus** an `espn_reconnect` bell row
   (once per expiry episode, keyed on `verified_at`) — never a silent gap.

## Consequences

- **The `source` column is double-duty:** the rollback lever
  (`DELETE … WHERE source='sync' AND snapshot_at > '<bad-deploy>'`) and the cron liveness
  detector — `SELECT source, count(*) FROM league_roster_history GROUP BY 1` one week
  post-ship answers whether `daily-tick` fires at all (runbook § roster-snapshot monitoring
  has the retirement rule). Gate 0 (the `player_value_history` density query) changes the
  urgency of any cron migration, never this design.
- **On-sync rows are bounded by client correctness** — rosters at `/api/session/init` are
  client-supplied. That is a real cost, accepted because a human just refreshed the league
  (stamping the current period is a genuine observation) and because the weekly writer
  outranks it wherever both exist.
- **Sleeper's on-sync team keys ride the shared v1 rosters fetch** (previously fetched by
  `trade_block_service` and discarded). If the fetch fails, keys degrade to
  `team_key_quality='weak'` and the recap **declines to chart** those teams rather than
  fragmenting them silently — weak keys are visible and countable.
- **The daemon thread and the sweep budget are a pair:** the budget (50) sits well above the
  ~20 leagues where an inline sweep becomes unacceptable on `--workers 1`. Anyone removing
  the daemon must drop the budget to ~10 in the same change. Per-league fetch-ms is logged
  from day one; the measurement tunes the budget, not the thread.
- **P3's behavioral reads cross the `wrapped_events` → `user_events` cutover seam** — the
  recap must read through one accessor that hides it (`load_league_activity` is the shape).
  `wrapped_events` itself stays frozen: it is an event stream and stores no state.
- **Retention is this family's, not this table's:** ~240 rows/league-season here (~47 MB at
  100 leagues, ~470 MB at 1,000 — where `basic-256mb` needs a policy). One
  retention/downsample policy covers `player_value_history`, `league_roster_history` and
  `league_board_history` together; writing it later means writing it once, not three times.
- **YR-3's line holds:** in-app, authenticated, league-scoped display of one manager's
  valuations to leaguemates is permitted; every P3 read accessor takes a caller identity and
  asserts league membership. Public-URL exposure stays prohibited (`growth.tier_board_share`
  stays false) — that is the half of D-P1-12 still standing.

## Alternatives considered

- **Write the snapshot inside the dispatcher/membership transactions** — rejected: a snapshot
  failure inside `replace_espn_league_members`' `engine.begin()` rolls back the delete+insert
  and leaves the league with **zero members** (and G-040 rules out `begin_nested` on
  main-engine SQLite).
- **A cron that reads `league_members` and stamps the current period** — rejected as
  fabrication: it would stamp possibly-months-old client data with this week's label,
  violating the runbook's "a gap stays a gap" rule.
- **An `hourly-tick` fallback guard as a third scheduled trigger** — dropped in the final
  reconciliation: `notif-hourly-tick` and `notif-daily-tick` are the same blueprint,
  provisioned by the same mechanism, perfectly correlated — the guard buys zero additional
  failure coverage. The manual route covers the "dedicated cron never provisioned" risk
  (this repo's documented history, twice).
- **Storing a team-value number without the roster** (the original ask) — rejected:
  attribution is unanswerable from a total, and a model change would rewrite history. Both
  are stored (YR-2), for the same reason `player_value_history` denormalises
  `consensus_value`.
