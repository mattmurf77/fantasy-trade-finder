# Architect review — round 2: reconciliation with an-data-architect

> **Reviewer:** eng-architect. **Date:** 2026-08-13.
> **Reconciling:** my `architect-r1.md` with `analytics-r1.md`.
> **Verified against:** `origin/main` @ `60fccc7`. Every claim of theirs that I adopt below,
> I re-verified myself; every claim of mine that I withdraw, I withdraw on evidence.
> **Operator rulings YR-1…YR-7 remain binding.** Nothing here reopens them.
> **Design only. No source file touched.**

## Contents

- [0. The reconciled design in one page](#0-the-reconciled-design-in-one-page)
- [1. AGREED](#1-agreed)
- [2. RESOLVED](#2-resolved)
- [3. STILL DISPUTED](#3-still-disputed)
- [4. The P0 build sequence](#4-the-p0-build-sequence)
- [5. Two findings neither review had](#5-two-findings-neither-review-had)

---

## 0. The reconciled design in one page

**The coordinator's sharpened question is the right one, and it has a clean answer: the two
mechanisms we each proposed are not alternatives, they are the two halves of a design that
degrades correctly under both answers.**

- **Writer A — on-sync (mine).** At the two `league_members` writers. Fires when a human opens
  a league. **Zero cron dependency.**
- **Writer B — weekly (theirs).** Inside `daily-tick` behind a `>=` weekday gate, per
  `_run_weekly_replenishment` (`server.py:16231-16243`). Fires when `daily-tick` fires. **Adds
  no Render resource**, so it sidesteps blueprint sync entirely.

Both write the **same table**, keyed on the **same `period_key`**, upserting against the **same
constraint**. They cannot double-count and they cannot conflict.

| If the declared crons fire | If they do not |
|---|---|
| Active leagues captured on sync; dormant leagues captured by the weekly gate. **Full weekly grid — YR-1 satisfied.** | Active leagues still captured on sync. Dormant leagues show **holes**. Degraded, honest, and not silent. |

**And the design answers the open question by itself.** The `source` column
(`'sync' | 'weekly' | 'backfill'`) is a **cron liveness detector**. One week after ship:

```sql
SELECT source, count(*) FROM league_roster_history GROUP BY 1;
```

Zero `'weekly'` rows ⇒ `daily-tick` is not firing. No `infra/render-cron-migration` merge is
required to *learn* this, and none is required to *ship*. That retires my R1 position that the
cron migration is a hard P0 dependency — the coordinator was right that it would eat the
window, and I was wrong to gate on it.

**The single check that settles it before build** is in §2(a). It costs one query and it is
already 18 days into running itself.

---

## 1. AGREED

Stated once, concretely. These are positions we now share and neither of us should re-argue.

1. **`docs/architecture.md:230` is factually false** and contradicts `docs/runbook.md:295`.
   Fixing it is part of this work regardless of what else ships. (Both R1s, independently.)
2. **The plan's §5.2 cost claim is false for the weekly path.** Rosters at
   `/api/session/init` are client-supplied (`server.py:14683-14687`); the server never fetches
   them there. A weekly job must call `_fetch_league_rosters` (`server.py:10564`) — verified,
   it is the public unauthenticated `/v1/league/<id>/rosters`, one call per league.
3. **`league_members` cannot satisfy YR-6 (every team).** `server.py:15228-15230` states it
   outright: *"clients drop ownerless rosters from `opponent_rosters` and stale rows linger
   after a manager leaves."* Verified. A server-side `/rosters` fetch is the only path to
   every-team coverage on Sleeper.
4. **The plan's `UNIQUE (league_id, user_id, snapshot_at)` enforces nothing.** `snapshot_at` is
   an instant; two runs make two rows. It must be a bucket label, per `uq_value_snapshot`
   (`database.py:1003-1005`).
5. **`roster_hash` must not suppress the weekly write.** Their B4 is right and it is a
   correction to the plan I did not make: `team_value` moves weekly even when the roster
   doesn't, so a hash-suppressed grid puts holes in exactly the quiet weeks — the opposite of
   what YR-2 exists to guarantee. The hash's jobs are `changed_from_prev` and suppressing
   *extra* on-sync writes.
6. **JSON arrays, not a row-per-player child table.** Their precedent list is unanimous and
   their dialect argument is the one I would have made.
7. **Pick ownership (C3) folds into the roster row, not a second table.** Same grain; `pick_id`
   is already self-describing (`database.py:731-733`); `pick_source` per ADR-010 is
   load-bearing so the recap can decline to make claims on a user-typed grid.
8. **`ix_pvh_format_date` is missing and should be added** to the idempotent list in
   `_migrate_db`. Free now, a full scan on a ~0.5M-row table later.
9. **`wrapped_viewed` stays server-fired**, and every NON_INTENT recap event lands in
   `NON_INTENT_EVENTS` in the same commit that registers it. Their B13 catches a real trap I
   did not look for; the December-DAU-spike reasoning is correct.
10. **Never write `team_value = 0` when the value lookup finds nothing. Write NULL.** A gap is
    honest; a zero renders as a roster wipe.
11. **P0 is not one week.** Their B15 asks me for the estimate; §4 gives it.
12. **This is not express-lane eligible** (schema + data collection). Both R1s said so.

---

## 2. RESOLVED

### (a) Scheduling — **their mechanism, my topology. Both writers ship in P0.**

**I withdraw** "new dedicated cron, gated on the migration merging." Their find is decisive and
I verified it: `_run_weekly_replenishment` (`server.py:16231-16243`) already runs weekly work
inside `daily-tick` (called at `server.py:16676`) behind `if now.weekday() < weekday_gate:
return`, with the comment stating the design intent exactly — *">= (not ==) keeps the rest of
the week eligible so one missed cron run doesn't skip the week — the per-week marker still caps
everything at once."* Idempotency via `deck_replenish_log`'s per-week unique constraint. That is
the house pattern for weekly work, it provisions nothing, and it is strictly better than a true
weekly cron, where one missed firing is a permanent hole.

**They should adopt** on-sync as a **co-primary writer, not the optional YR-1 extra.** Their
A4.3 treats it as a nice-to-have. It is the entire failure mode coverage: it is the only writer
that works if `daily-tick` never fires, and the open question is precisely whether it fires.

**Resolution.** Two writers, one table, one constraint. The **table** is the contract, not
either writer. This satisfies YR-1's "the weekly job is the contract and the thing that must not
be allowed to miss" more robustly than either of our R1 designs, because the thing that must not
miss now has two independent feeders.

**The single check that settles the open question, before build.** Neither of us named the
cheapest one, and it is already running:

```sql
SELECT snapshot_date, count(*) FROM player_value_history
GROUP BY 1 ORDER BY 1 DESC LIMIT 30;
```

**`player_value_history` has been an unintentional cron-liveness canary since 2026-07-26 and
nobody has read it.** The logic is airtight because the writer set is closed: the dedicated
`/api/cron/value-snapshot` is not provisioned (verified — `render.yaml` has three crons, none of
them it), so `_write_daily_value_snapshots` has exactly one scheduled caller, the `hourly-tick`
fallback guard (`server.py:16446-16460`). Therefore:

| Result | Conclusion |
|---|---|
| Dense daily rows since 2026-07-26 (~1,369/day) | **`hourly-tick` fires.** The blueprint crons work; `daily-tick` almost certainly fires too (same blueprint, same mechanism). Their weekday gate is sound. C4 is real. |
| Sparse or absent | **No cron fires.** The scheduled half is dead, on-sync is the only capture — *and C4 itself is gappy*, which is a bigger problem than roster history, because §3's join thesis makes the recap chart depend on it. |

One query, two of the largest open questions in both reviews. It also **retires my R1 evidence
weighting**: the coordinator is right that `origin/infra/render-cron-migration`'s claim that the
notif ticks never ran is an assertion on an unmerged branch, not established fact. This query is
established fact. Run it first.

**What P0 does in the meantime:** everything. Neither writer is blocked on the answer. If the
query says the crons are dead, merging the migration becomes urgent *for C4's sake* and can
proceed in parallel — but the roster capture ships either way, and its `source` column will
independently confirm the verdict a week later.

### (b) Server-side fetch — **they are right, and it splits my seam rather than replacing it**

Their B2 is correct and I verified every element. It does **not** overturn my seam analysis; it
partitions it, and their analysis was incomplete in one way that matters.

**Where they were incomplete.** They state `upsert_league_members` has one production caller.
True. But that is one of **two** writers of `league_members`. The other,
`replace_espn_league_members` (`database.py:10087`), has **three** callers — ESPN
(`server.py:19788`), MFL (`server.py:21395`), Fleaflicker (`server.py:22940`) — despite its
name. That matters for (c) and for their B11.

**The resolution — the seam is per-writer:**

| Writer | Source of rosters | Seam | Honest? |
|---|---|---|---|
| **On-sync** | The payload already in hand at the two `league_members` writers | `upsert_league_members` + `replace_espn_league_members`, own transaction, after theirs commits | **Yes** — a human just refreshed it, so stamping the current `period_key` is a real observation |
| **Weekly** | `_fetch_league_rosters(league_id)` — server-side, authoritative, every team | The `daily-tick` weekday gate | **Yes** — and reading `league_members` here would be fabrication, exactly as they say |

So their fetch requirement and my seam are both right, for different writers. What must be
written down is the **conflict rule**, which their A4.3 gets wrong — see below.

**Does it survive `--workers 1 --timeout 120`? Not with their answer alone.** They propose
bounded stalest-first rotation (`_DRAFT_STATUS_SWEEP_BUDGET = 50`) and explicitly reject the
daemon thread: *"rotation self-heals and needs no thread."* That conflates two orthogonal
problems. **Rotation solves completeness. The thread solves availability.** `--workers 1` with
the sync worker class means one request at a time: a bounded 50-league sweep at ~500 ms/fetch
blocks the *only* worker for ~25 s, during which every user gets nothing. Bounding the work does
not unblock the worker.

**Resolution: both, and the precedent for both is already inside `daily-tick`.** The
players-refresh guard in that same handler *"starts a DAEMON (never blocks the tick)"*
(`server.py:16717-16731`, calling `_refresh_players_cache_async`). So: weekday gate → start a
daemon → return immediately → daemon does a budgeted, stalest-first sweep. No new pattern is
invented; both halves are lifted from the handler this code will live in.

At FTF's actual scale this is academic today — but daily-tick is already a fat tick (replenish,
F8 eval, value-model refit, players-refresh guard, class-load monitor) and adding N network
fetches inline is a different order of thing from adding DB work.

### (c) `team_key` — **neither of our answers was right. Here is the one that is.**

Their `'r:<roster_id>' | 'u:<owner_user_id>'` is better than the plan's bare polymorphic key —
the prefix makes the discriminator explicit. And on **Sleeper it does not fragment at all**:
`/rosters` always returns `roster_id`, so every Sleeper team is `r:<roster_id>`, always. My R1
objection was too broad and I withdraw it for Sleeper.

**On ESPN and MFL it fragments three ways, and I can now show the exact code.**

`_espn_member_id` (`server.py:19167-19171`):

```python
def _espn_member_id(league_id: str, team) -> str:
    """Deterministic synthetic user_id for a non-FTF ESPN manager."""
    if team.owner_swid:
        return f"espn:{team.owner_swid}"
    return f"espn:{league_id}.t{team.team_id}"
```

and at the write site (`server.py:19770`):

```python
mid = user_id if t.team_id == my_team_id else _espn_member_id(league_id, t)
```

Three independent ways the same physical ESPN team changes key:

1. **The my-team swap.** When a second FTF user links the league, their team flips from
   `espn:…` to their real FTF id, and the first user's flips the other way.
2. **SWID presence.** `owner_swid` populated vs not switches the key between
   `espn:<swid>` and `espn:<lid>.t<tid>` — two different shapes for one team.
3. **SWID rotation.** Documented in-tree as a real, observed cause of orphaned ownership:
   `database.py:7911` lists an orphan as *"a SWID rotation on re-import, or a manager who
   left."*

MFL is the identical pattern (`_mfl_member_id`, `mid = user_id if fid == my_team else …`,
`server.py:21382-21386`).

**Resolution: `team_key` is ALWAYS platform-native, never an FTF user id. The `u:` branch is
deleted, not defaulted to.**

| Platform | `team_key` | Native id available at the write site? |
|---|---|---|
| Sleeper | `s:<roster_id>` | Yes — `/rosters` |
| ESPN | `e:<league_id>.t<team_id>` | **Yes — `t.team_id`, `server.py:19771`. It is being discarded today.** |
| MFL | `m:<league_id>.f<franchise_id>` | **Yes — `fid`, `server.py:21382`. Discarded today.** |
| Fleaflicker | `f:<league_id>.t<team_id>` | Yes, same shape |

Note what this shows: **every platform already exposes a stable native team id at the exact line
where we write membership, and every one of them throws it away.** `league_members` has no
`roster_id`/`team_id` column at all (`database.py:321-331`). That is the actual root cause of
this whole identity mess, and capturing it into `team_key` fixes it at the source.

`owner_user_id` becomes a pure **nullable, re-stampable attribute** — which is exactly what my
R1 B3 needed for the late-joiner reconciliation (§5.3's growth claim), and what their `NULL for
orphan teams` needed for YR-6. Both requirements are satisfied by the same column once it stops
being the key.

**Verdict on the question as posed — one chart or three?** With their scheme: one on Sleeper,
three on ESPN. With this: **one everywhere.**

**Bonus: this partially dissolves their B11.** They concluded ESPN/MFL get no row at all,
because `_fetch_league_rosters` is Sleeper-only. True of the *weekly* writer. But the *on-sync*
writer covers ESPN/MFL/Fleaflicker for free (three callers of
`replace_espn_league_members`), correctly keyed. So ESPN/MFL get on-sync rows and no weekly
rows — a legible pattern in the `source` column, not a blank table. §7's platform-agnostic claim
survives in weakened, honest form: **ESPN/MFL coverage is app-open-driven, Sleeper coverage is
guaranteed weekly.** That should be stated in the plan rather than struck.

### (d) C5/C6 — **I concede entirely; my point was adjacent, not opposed**

Their `league_board_history` does **not** fork `wrapped_events`. I checked what
`wrapped_collector` actually stores: `VALID_EVENT_TYPES = {swipe, trade_match, trade_accepted,
trade_declined, tier_save, ranking_reorder, league_sync}` — behavioural events, never boards. It
was never a candidate for C5/C6. My R1 raised `wrapped_events` as a **read-path** hazard, and
conflating that with a storage proposal would have been my error, not theirs.

Their storage case is verified and stands on its own:
- `elo_history` (`database.py:971-979`) — I re-read the table definition: **no `UniqueConstraint`
  of any kind.** Their B5 is correct, and the plan's §5.4 "cheap fix: append a personal-Elo
  snapshot on the same trigger" is **not idempotent** — a double run silently doubles every
  board.
- Changed-only writes mean it structurally cannot rebuild a complete board at date D.
- 1.6M rows at 100 leagues row-per-player vs ~6,000 JSON-per-board.

**Adopted as specced.** Their `board_updated_at` column is the sharpest thing in either
document: it is what stops "Your calls" from reporting one observation five times.

**What I still hold, separately:** the recap's read path crosses the `wrapped_events` →
`user_events` cutover (`database.py:1026` frozen; epoch in `model_config` at `:2083-2097`;
reader `:3494`; union-read already implemented at `:6022-6071`). That is a P3 read concern and
an ADR consequence. It is not a storage argument and I withdraw any implication that it was.

### (e) `league_state.py` — **my find, and I was half wrong about it**

Stress-testing my own R1 position: **the Protocol is the right pattern to copy; the
`LeagueState` object is the wrong thing to construct.**

What is genuinely valuable:
- `LeagueStateProvider` + `LEAGUE_STATE_PROVIDERS` keyed by platform, with `mfl`/`fleaflicker`/
  `espn` as **registered stubs that raise `NotImplementedError`** — the header says the intent
  plainly: *"so the seam is real and the gap is explicit."*
- The `/rosters` parse at `league_state.py:176` (`roster_id`, `owner_id`, `players[]`,
  `starters[]`) and the `_BENCH_SLOTS = {"BN","IR","TAXI"}` starters split.

**The baggage, which disqualifies consuming it directly.** It is the outlook pipeline
(feedback #169). Building a `LeagueState` pulls standings, the full pairing schedule and
matchups — the header documents a weekly `/matchups/{week}` fan-out across the season. That
turns a **1-call** weekly roster job into a **15+-call** one. Unacceptable for a sweep on one
worker.

**Resolution.** Do not construct `LeagueState`. Register a narrow
`ROSTER_SNAPSHOT_PROVIDERS`-style map keyed by platform — Sleeper implemented via
`_fetch_league_rosters`, ESPN/MFL/Fleaflicker as explicit raising stubs. The value being
imported is **the convention, not the code**: a platform gap must be a registered stub that
raises, never a silently-empty result. That convention is precisely what keeps their B11 honest
— an unsupported platform produces a *legible* hole instead of a quietly missing row. Lift the
`/rosters` parse and the `_BENCH_SLOTS` split; leave the rest.

### (f) K/DEF — **they are right, and it is worse and better than they say**

I did not address it in R1; their B7 is a real correctness bug in the headline number. Verified:
`_write_daily_value_snapshots` (`server.py:16810-16828`) iterates the DP-seeded universal pool
only, so K/DEF and deep-bench bodies have no `player_value_history` row, ever — while
`league_members` deliberately stores *"the RAW client-sent ids"* including off-pool players
(#151, `server.py:15258-15265`).

**Adopted:** `valued_player_count` beside `player_count`, and NULL-not-zero.

**But this is not a new decision — the codebase already made it, and the recap must not make a
second one.** See §5.1: `backend/power_rankings.py` already computes summed roster value and
already documents this exact case: *"out-of-pool players (no seed, no board entry — K/DEF, deep
stashes) contribute 0.0: they have no market value in the shared value space, and a 1500-Elo
default would hand every deep bench ~1000 phantom points."* So the resolution is stronger than
theirs: **inherit the existing decision** (contribute 0.0 to the sum) **and add their coverage
counter** (make the gap legible). Their instinct was right; the codebase had already reasoned it
through.

### (g) Flagging — **stands, and it composes with their two-writer design**

They did not address it; there is no conflict. Confirmed:

- **One flag, `market.roster_history`, default ON at merge**, gating **both** writers. Same
  shape as the three sibling capture blocks in the same daemon: `market.trade_capture`
  (`features.json:51`), `sleeper.trade_block` (`:47`), `picks.owned_sync` (`:49`).
- D-P1-07 does not bar it. Its reasoning (`DECISIONS-p1.md:139-145`) is specific to *read routes
  with external references* — flipping `growth.share_landing` off *"would break every link
  already shared."* A capture flag gates a write with no external references.
- **Fine-grained lever without a second flag:** their `FTF_ROSTER_SNAPSHOT_WEEKDAY` env knob set
  to `7` disables only the sweep (`now.weekday()` is 0–6, so the gate can never pass) while
  leaving on-sync capture running. Kills the worker-blocking half without killing capture, no
  deploy. That is a better composition than two flags.
- **One flag, one direction.** When P3 adds `GET /api/wrapped/<season>`, it gets its own flag.
  The capture flag must never come to gate a read surface — that is the mistake D-P1-07 exists
  to prevent.
- Standing caveat: NEXT.md 0c notes a malformed `FTF_FLAGS` currently fails silently to `{}`,
  patch drafted and unapplied. Pre-existing sharp edge on the lever. Not a blocker.

### (h) ADR — **confirmed yes; their decisions expand it, and one collapses a second ADR into it**

Still ADR-worthy, for the R1 reasons (reverses the snapshot-semantics posture of every
league-state table; cross-cutting; third lineage). Their work changes the content in four ways:

1. **Two tables, not one** — `league_roster_history` + `league_board_history`, with the
   don't-fork guardrail explicitly traded against a 6,750× row multiplier. That trade is exactly
   what an ADR is for; record it with their volume numbers.
2. **`team_key` is the load-bearing line** (§2c), the way "containment is the read default, not
   a table split" was ADR-010's. Say so.
3. **Retention/downsample belongs in this ADR, not a second one.** They flag ~470 MB at 1,000
   leagues on `basic-256mb`, and `data-dictionary.md:659` already carries a deferred
   downsample note for `player_value_history`. **One policy covers all three tables.** Writing a
   separate ADR later means writing it three times.
4. **Consequence to add:** `team_value` is defined by `compute_power_rankings` (§5.1), so the
   recap chart and the Power Rankings screen are contractually the same number.

---

## 3. STILL DISPUTED

Genuinely short. We converged on almost everything.

**D1. Whether the daemon thread is needed for the weekly sweep.**
- **Them (A4.2):** bounded stalest-first rotation is sufficient; *"prefer this over the
  `players-refresh` daemon-thread-plus-202 pattern — rotation self-heals and needs no thread."*
- **Me:** rotation bounds *completeness*; only the thread protects *availability*. `--workers 1`
  means a 25 s sweep is 25 s of total app unavailability, and `daily-tick` already starts a
  daemon for exactly this reason (`server.py:16717-16731`).
- **Falsifiable:** time one `_fetch_league_rosters` call against a real league. If p95 × budget
  stays under ~2 s, they are right and the thread is ceremony. If it is tens of seconds, I am.
  **Measure before choosing.** Low stakes either way at current scale; it matters at 50+ leagues.

**D2. On-sync writer's status.** They spec it as the YR-1 "free addition" (A4.3); I make it a
co-primary, because it is the only writer that survives the crons being dead. I think this is a
framing difference that the two-writer table dissolves, but I am flagging it rather than
declaring their agreement.

**D3. Whether §7's platform-agnostic growth claim should be struck.** They say scope
per-platform fetchers into P0 or strike the claim (B11). I say neither: with the `team_key` fix
(§2c) ESPN/MFL get correct on-sync rows, so the claim survives **restated** as "ESPN/MFL
coverage is app-open-driven, Sleeper is guaranteed weekly." Restating is not striking. Operator
call if they disagree.

**D4. `pick_ids` on the roster row for ESPN.** They fold pick ownership in with a
`pick_source` stamp. Correct for Sleeper/MFL. For ESPN, ADR-010 is structural — *"no platform
draft object to read, not now and not ever"* — so ESPN pick rows are user-asserted and can be
**contested** (two users asserting different owners) or **orphaned** (`database.py:7902-7920`).
`pick_source='user'` records that they are assertions but not that they may be *contradictory*.
Minor; I would have the snapshot skip contested slots rather than record a coin-flip. Their
call — it is their table.

---

## 4. The P0 build sequence

Ships inside four weeks. Dependencies stated honestly.

**Gate 0 — before any code (½ day, operator).**
Run the `player_value_history` query in §2(a). It settles both the cron question and whether C4
exists. **Nothing below is blocked on the answer** — it changes priorities, not the build.
Also: feature-scope block per `docs/templates/feature-scope.md` (mandatory; schema + data
collection, not express-eligible).

**Week 1 — schema + on-sync writer. No cron dependency at all.**
1. `league_roster_history` per their A1 DDL, with `team_key` per §2(c) — always platform-native,
   `u:` branch deleted, `owner_user_id` nullable.
2. Flag `market.roster_history`, default ON.
3. On-sync writer at **both** `league_members` writers (`upsert_league_members` :5526 and
   `replace_espn_league_members` :10087) — **own transaction, after theirs commits**, wrapped
   with the house `log.warning("… (continuing): %s")`. Never inside `replace_espn_league_members`'s
   `engine.begin()` block: a snapshot failure there rolls back the delete+insert and leaves the
   league with **zero members**. Test that explicitly.
4. `team_value` via `compute_power_rankings` consensus basis (§5.1), not a new summation.
   `valued_player_count`, NULL-not-zero.
5. **Ships value on day one**: every app-open now records history, on all four platforms.

**Week 2 — weekly writer.**
6. `_write_weekly_roster_snapshots(now)` — server-side `_fetch_league_rosters`, one
   `engine.begin()` **per league**, budgeted stalest-first, in a daemon (D1 pending
   measurement).
7. `daily-tick` weekday gate (`FTF_ROSTER_SNAPSHOT_WEEKDAY`, default 1), failure-isolated,
   mirroring `_run_weekly_replenishment`.
8. **The precedence rule — a correction to their A4.3.** Both writers hit the same `period_key`,
   and their spec is last-write-wins. That is wrong: a Friday app-open (client-posted, partial,
   **drops ownerless rosters**) would overwrite Tuesday's authoritative server-fetched row and
   silently delete that week's orphan teams — breaking YR-6 for the week, invisibly. Resolve by
   **precedence, not recency**: `source='weekly'` outranks `source='sync'`. The weekly writer
   does a full `DO UPDATE`; the on-sync writer does `DO NOTHING` when a `'weekly'` row already
   exists for that period. Within-bucket freshness is not the goal; completeness and
   comparability are. Mid-week resolution is `period_kind='day'`, which their DDL already
   accommodates.
9. `ix_pvh_format_date` into `_migrate_db`.

**Week 3 — C5/C6 + hardening.**
10. `league_board_history` per their A3 (reads `member_rankings`, no platform call), with the
    league-scoped caller-identity assertion their privacy note specifies.
11. Value-basis resolution: nearest pvh `snapshot_date ≤ target`, recorded in
    `value_basis_date`, per `load_value_snapshot_baseline`'s existing idiom
    (`database.py:9425`).
12. Backend tests: idempotency (double run), precedence (sync-after-weekly), orphan teams,
    zero-coverage → NULL, the ESPN-transaction-isolation test from step 3.

**Week 4 — docs, ADR, verification.**
13. ADR-011 per §2(h), including retention.
14. Doc sync: **`architecture.md:230` correction first**, then data-dictionary, config-reference,
    runbook monitoring paragraph, api-reference (if the cron route ships).
15. **The liveness read**: `SELECT source, count(*) FROM league_roster_history GROUP BY 1`.
    Zero `'weekly'` ⇒ crons dead ⇒ escalate `infra/render-cron-migration`.
16. TEST_LEDGER entry. Sim gate: server-only change, no client surface, no Maestro delta
    (waiver reason recorded in the scope block).

**Honest dependencies.**
- **Hard:** none. Nothing in weeks 1–4 requires `infra/render-cron-migration`.
- **Soft:** if Gate 0 says the crons are dead, week 2's value drops to near zero until the
  migration merges — but weeks 1, 3, 4 are unaffected, and week 2's code is what makes the
  migration worth merging.
- **Sequencing constraint:** C3 pick-ownership must not start until the mock-draft branches
  (`origin/closeout-mock-draft`, `origin/mock-draft-fix`) land — they are actively moving
  `draft_picks`. Rosters (C1) are clear; picks are not. This is why `pick_ids` is nullable in
  the DDL from day one.
- **Baseline is red:** 6 `test_rookie_scope.py` failures live on `origin/main`, unowned. The
  builder must not attribute them to this work.

**Not in P0, deliberately:** ESPN/MFL weekly fetchers, the P2 replay verifier, recap routes,
any UI.

---

## 5. Two findings neither review had

### 5.1 `team_value` must be `compute_power_rankings`, or the app will contradict itself

**`backend/power_rankings.py` already computes summed roster value, and it ships today** at
`GET /api/league/power-rankings` (`server.py:19997`, calling `compute_power_rankings` at
`power_rankings.py:134`). Its docstring: *"League power rankings (#142/#144) — rank every team
in a league by summed roster value."*

If the recap computes `team_value` with a fresh summation, **the Power Rankings screen and the
Wrapped chart will show different values for the same team in the same app.** That is the
cross-client-consistency class of defect I own, and it would surface in December in front of the
one audience that will screenshot it.

It is also strictly less work to reuse, because `power_rankings.py` already solved four things
the recap needs:
- **K/DEF / out-of-pool handling**, with the reasoning written down (§2f).
- **`consensus` and `personal` bases** — `personal` is a ready-made "your board's view of your
  team" recap stat.
- **A correct starters split.** `_fill_starter_slots` + `LINEUP_SLOT_ELIGIBILITY` derive the
  optimal lineup from the league's actual `roster_positions`. This is **better than the
  platform's `starters[]` array** for `starter_ids`, because it reflects what the roster *could*
  start, not what a manager happened to set. Their A1 `starter_ids` and my R1 `_BENCH_SLOTS`
  suggestion are both inferior to this.
- **Picks handled separately** (`server.py:19860-19884`) — which independently validates their
  `team_value` / `team_value_picks` split.

It is *"pure computation, no DB access"*, explicitly so it is unit-testable. Reusing it is a
function call.

**Position: `team_value` is defined as `compute_power_rankings`'s consensus-basis team total.
Any divergence is a recorded decision in the ADR, not an accident.**

### 5.2 `league_members` discards a stable native team id at every write site

Surfaced while resolving (c), but it is bigger than `team_key`. All four platforms hand us a
stable native team identifier at the exact line where membership is written — Sleeper
`roster_id`, ESPN `t.team_id` (`server.py:19771`), MFL `fid` (`server.py:21382`), Fleaflicker the
same — and `league_members` has no column for any of them (`database.py:321-331`; unique key is
`(league_id, user_id)`). Every one is thrown away, and a synthetic id is derived from an
*owner* instead.

That single omission is the root cause of: the ESPN identity churn in `_espn_member_id`, the
orphaned-pick class at `database.py:7911`, the my-team swap, and the fragmentation risk in both
of our `team_key` proposals.

**This is out of scope for P0** — I am not proposing to migrate `league_members`. But
`league_roster_history` should be the first table in this codebase that stores the native team
id, and the ADR should note that `league_members` carries the same latent defect. If a future
session fixes it there, `team_key` is already the model.

---

**Nothing above reopens YR-1…YR-7.** YR-1 (weekly) is delivered by the daily-tick gate with an
on-sync writer that makes it robust to the crons being dead. YR-2 (both) is delivered by
`team_value` + `player_ids`, with the value defined by `compute_power_rankings`. YR-3 is
delivered with the league-scoped read assertion. YR-6 (every team) is delivered by the
server-side fetch and the platform-native `team_key` — and is the specific thing the precedence
rule in step 8 exists to protect.

---

## Round 3 — final

> Written after reading `analytics-r2.md`. We reconciled in parallel, so R2s crossed. This
> closes the remainder. **Result: no disagreements remain.**

### Closures confirmed (no argument)

- **My D2 — on-sync primary.** Closed. Their R2 §2(a) makes it primary, and their reasoning is
  better than mine was: *"the on-sync write is the only mechanism whose correctness is
  independent of the open question."* They are right that my R1 framing ("there is no working
  scheduler") rested on an open question and could not settle a design. Their version of my
  conclusion is the one that should go in the ADR.
- **My D4 — contested ESPN picks.** Closed on the fold-in. Their ordering find is real and
  neither of us had it: `draft_picks` is written by a **sibling block in the same daemon**
  (owned-pick sync, `server.py:15300-15343`), so a snapshot reading it must be appended
  **last**, after trade-capture (`:15355`). A snapshot that races the sync populating
  `draft_picks` yields a quietly short `pick_ids` array — invisible until December. Endorsed.
  Contested-slot handling is theirs to rule on; my preference (skip contested slots rather than
  record a coin-flip) is on the record and I do not hold it as a dispute.
- **Their key — `(league_id, team_key, scoring_format, period_key)`. Accepted.** They are right
  and I was sloppy: I carried the plan's `snapshot_at` shape forward while arguing only about
  the *team* component, and in doing so reinstated the instant-in-key defect their own R1 B3
  had correctly killed. A bucket label is required for idempotency, per `uq_value_snapshot`
  (`database.py:1003-1005`) and `deck_replenish_log.iso_week` (`:586-591`). Their diagnosis
  acceptance + my team-key fix + their period mechanism is the right composite. Also accepted:
  their `leagues.espn_my_team_id` / `platform_my_team` re-stamp hook (`database.py:262`, `:273`)
  makes my §5.3 late-joiner fix concrete on ESPN and MFL without a mapping table.

---

### 1. Backstop location — **I concede. The hourly guard ships, with one condition.**

**I withdraw "never."** I was reading half a sentence, and the coordinator is right to press it.

`docs/architecture.md:230` — the line I built the objection on — does not forbid this. Read
whole, it *documents this exact combination as the design*: "Kept separate from `daily-tick` so
a push-scan failure can't stop history collection… **`hourly-tick` additionally carries an
idempotent fallback guard** that writes today's snapshot if missing (shared
`_write_daily_value_snapshots`), so a missed run self-heals within the hour." The clause I cited
justifies **the dedicated route existing**. It says nothing against a second, idempotent caller.

And it is not one instance. There are **two, deliberate, and the second names the first as its
model**: `daily-tick`'s players-refresh guard is commented *"Mirrors the hourly-tick
value-snapshot fallback guard"* (`server.py:16717-16731`). `runbook.md:295` then blesses the
pattern outright — *"the operative mechanism is the `hourly-tick` idempotent fallback guard…
cadence is guaranteed by the existing hourly cron alone."* A twice-instantiated, twice-documented
house pattern is the precedent. My "stated in the doc, violated in practice" reading in R1 had it
backwards.

**The condition — the guard must be a guard, not a sweep.** This is the only real content left
in the disagreement, and it is what makes their "a few lines that never execute" claim true
rather than aspirational. The value-snapshot guard is safe because its check is *cheap*:
`value_snapshot_formats_for(today)` is one indexed query, and work happens only on a miss
(`server.py:16456-16458`). A roster guard that fans out across leagues **every hour** would be
retention riding the push tick in the way the precedent does care about — and 24× the load, on
one worker.

So: one indexed `COUNT` against the current `period_key`; complete → return immediately (the
case in ~167 of 168 hours a week); incomplete → top up **at most a small budget** (5–10 leagues)
inside the daemon, never the full 50-league sweep. The dedicated route keeps the full budget.

**One precision worth recording, because it is easy to over-claim:** trigger 3 does **not**
insure against the scheduler question — if `hourly-tick` does not fire, neither does the guard.
It insures against *the dedicated cron never being provisioned*, which is this repo's documented
history twice over (`1e50d3e`; players-refresh left as "provision by hand"). That is a real and
different risk, and it justifies the guard. **Trigger 1 remains the only thing that survives the
scheduler being dead.**

### 2. D1 daemon thread — converted to a decision rule

**Default shipping in P0: the daemon thread, always.** Not "measure first."

| | |
|---|---|
| **Why this default** | It is ~5 lines and it is already the pattern in both ticks (`_refresh_players_cache_async`, `server.py:16717-16731`; the 202-immediately route, `:16776-16793`). The error costs are wildly asymmetric: a thread we did not need costs nothing; inline blocking costs **total app unavailability** on `--workers 1`. That is the same asymmetry argument the analytics reviewer used to justify trigger 3, so applying it here is consistent, not special pleading. |
| **What retires the question** | Emit one `log.info` per league with elapsed fetch ms from day one, then read a week of it. **If p95(fetch) × budget < 2 s, the thread is ceremony and can be deleted.** Self-measuring, same trick as the `source` column — no separate measurement project, and nothing blocks on prod access from a sandbox. |
| **When it starts to matter** | Inline is unnoticeable to ~4 leagues (~2 s at 500 ms each) and unacceptable by ~20 (~10 s). FTF is at a handful today, so **today either choice is defensible** — which is exactly why we ship the cheap safe one and stop spending on it. |
| **Coupling to flag** | The two decisions are linked: their budget of 50 sits *well above* the ~20 where inline becomes unacceptable. So **if anyone later drops the daemon, they must drop the budget to ~10 in the same change.** Keeping the daemon lets the budget stay at 50. Record this pairing, or a future session will tune one and break the other. |

### 3. Both late finds — confirmed in the final design

**(a) `compute_power_rankings` — confirmed, and it is currently missing from their final DDL.**
`team_value` is defined as `compute_power_rankings`'s consensus-basis team total
(`backend/power_rankings.py:134`, shipping at `GET /api/league/power-rankings`,
`server.py:19997`), not a fresh summation. Otherwise the Wrapped chart and the Power Rankings
screen show different numbers for the same team, in the same app, in the month that guarantees
screenshots. Their §5 DDL comment on `team_value` explains the *denormalisation* but never says
what computes it — **that line needs adding**, because a builder reading the DDL alone will
write a new sum. It also carries the K/DEF decision the codebase already made and documented
(*"out-of-pool players… contribute 0.0… a 1500-Elo default would hand every deep bench ~1000
phantom points"*), which their `valued_player_count` / `value_basis_date` machinery then makes
*legible* — the two are complementary, and both ship.

**In the ADR: yes.** As a consequence, in these words: *the recap chart and the Power Rankings
screen are contractually the same number; any divergence is a recorded decision, not an
accident.* This is a cross-client-consistency invariant, which is my lane, and it is why the ADR
matters more than the table does.

*One amendment to their `starter_ids`.* They spec it "from `TeamState.starters`" — the
platform's actually-set lineup. Keep that: it is the historical **fact**, and it is free.
Do **not** store `_fill_starter_slots`' optimal lineup, even though power_rankings has it —
that is an **analysis**, it is a pure function, and it is derivable at read time. This is the
plan's own §3 principle ("capture inputs, compute outputs") applied one level down.

**(b) Precedence-not-recency — confirmed, restated in their final vocabulary.** Their DDL uses
`source ∈ {'sync','cron','backfill'}`, so the rule is: **`cron` outranks `sync`.** The cron row
is server-fetched (authoritative, every team, orphans included); the sync row is client-posted
and **drops ownerless rosters** (`server.py:15228-15230`). Last-write-wins lets a Friday
app-open silently delete Tuesday's orphan teams, breaking YR-6 for that week with no error.

Mechanically, two rules, no predicate gymnastics:
- cron writers (triggers 2 and 3) → full `DO UPDATE`;
- the on-sync writer → `DO NOTHING` when a `source='cron'` row already exists for that
  `period_key`.

Note the scope honestly: with on-sync primary, an active league may never get a cron row, so the
conflict only arises for a league dormant enough to be swept and then opened later in the same
week. Narrow, real, and the rule is two lines. And "primary" means *fires most often*, not
*higher fidelity* — which is precisely why precedence runs the other way from primacy here.

Within-bucket freshness is not the goal; one complete, comparable observation per week is.
Mid-week resolution is `period_kind='day'`, which their DDL already accommodates.

---

### Standing after round 3

**No disputes remain between the two reviewers.** Items 1 and 2 above are concessions or
decision rules, not open questions. What is still outstanding is owned elsewhere and neither of
us should spend more on it: the **contested-slot rendering ruling** (theirs), the
**platform-agnostic wording** in §7 (operator), the **P0a cost range** (pm-technical), and
**Gate 0's `player_value_history` query** (operator) — which changes priorities, not the
design.
