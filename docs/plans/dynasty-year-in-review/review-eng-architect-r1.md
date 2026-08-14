# Architect review — Dynasty Year in Review capture plan (round 1)

> **Reviewer:** eng-architect. **Date:** 2026-08-13.
> **Plan under review:** `docs/business/product/2026-08-13-dynasty-year-in-review-plan.md`
> **Verified against:** `origin/main` @ `60fccc7` (the plan's stated base `4a4b671` is an
> ancestor; line numbers in the `database.py` 950–1000 region have since shifted +14, but
> every citation the plan makes was **correct as of its stated base**. I checked. No credit
> withheld there.)
> **Operator rulings YR-1…YR-7 are treated as binding.** Nothing below reopens them. Where I
> disagree, I disagree with the *plan's implementation of a ruling*, never the ruling.
> **Design only. No source file was edited.**

---

## Contents

- [0. The one-paragraph version](#0-the-one-paragraph-version)
- [A. Design positions](#a-design-positions)
  - [A1. Where the capture hooks in](#a1-where-the-capture-hooks-in)
  - [A2. Cron and scheduling](#a2-cron-and-scheduling)
  - [A3. Multi-platform](#a3-multi-platform)
  - [A4. Is this ADR-worthy?](#a4-is-this-adr-worthy)
  - [A5. Blast radius and rollback](#a5-blast-radius-and-rollback)
  - [A6. Interaction with in-flight work](#a6-interaction-with-in-flight-work)
- [B. Disagreements and corrections](#b-disagreements-and-corrections)
- [C. Open questions for the other reviewer](#c-open-questions-for-the-other-reviewer)
- [D. Doc-sync list](#d-doc-sync-list)

---

## 0. The one-paragraph version

The plan's diagnosis is right: roster history is genuinely being overwritten, the join-not-a-
number principle in §3 is correct, and the four-weeks-to-weekly argument is sound. Two things
are wrong and one is load-bearing. **The load-bearing one: there is no working scheduler in
production.** `render.yaml` at `origin/main` declares three cron services that — per the repo's
own commit record — never ran, the `value-snapshot-daily` cron was added and reverted the same
day, and the GitHub Actions replacement is sitting unmerged on `origin/infra/render-cron-migration`.
So the plan's "already running, scheduled, self-healing" backbone (§1) is unverified and
probably has gaps, and YR-1's weekly cron would be scheduled by a mechanism that does not
exist. **The second: §5.2's cost argument ("no extra API calls — sync already fetches
rosters") is true of the sync path and false of the weekly job**, because `/api/session/init`
receives rosters in the *request body*, not from a server-side fetch. A weekly grid needs a new
per-platform server-side fetch layer, which is where ESPN breaks. My recommendation is not to
slow the work down — it is to **reorder it**: merge the cron migration first, verify
`player_value_history` against prod, then ship the sync-driven capture at the two
`league_members` writers (genuinely cheap, genuinely a week), and let the weekly backstop land
on a scheduler that works.

---

## A. Design positions

### A1. Where the capture hooks in

**Position: hook it inside the two `league_members` writers in `database.py`, not at the four
route-level call sites in `server.py`.**

The plan says "on league sync" as if that is one place. It is four:

| Path | Route | Writes membership via |
|---|---|---|
| Sleeper | `POST /api/session/init` (`server.py:14655`), inside the background daemon | `upsert_league_members` (`server.py:15276`) |
| ESPN | `POST /api/espn/import` (`server.py:19715`) | `replace_espn_league_members` |
| MFL | `POST /api/mfl/import` (`server.py:21338`), `POST /api/mfl/auth-import` (`:21656`) | `replace_espn_league_members` |
| Fleaflicker | `POST /api/fleaflicker/import` (`server.py:22932`) | `replace_espn_league_members` |

All four converge on **one table**. `database.py:5526 upsert_league_members` (dialect-aware
upsert) and `database.py:10087 replace_espn_league_members` (delete-then-insert; the name is a
lie — MFL and Fleaflicker both call it, `server.py:21346`, `:21789`, `:22940`) are the complete
set of writers. `git grep` for mutations of `league_members_table` returns exactly four sites
(`database.py:2462` an unrelated single-column update, `:5572`, `:10112`, `:10116`).

Two functions is the whole seam. Four route hooks is four chances to miss one, and the plan's
own §5.3 (YR-6: every team) makes completeness the point.

**Failure-isolation posture — and one rule that is not negotiable.**

The house pattern is visible in the session-init daemon: every capture block is individually
wrapped with `try/except` + `log.warning("… failed (continuing): %s", e)` — trade-block sync
(`server.py:15286-15296`), owned-pick sync (`:15300-15343`), trade capture (`:15355-15367`) —
inside an outer daemon-level `except` that `log.exception`s rather than dying silently
(`server.py:15370-15372`, docstring at `:15059-15065` citing
`docs/reviews/2026-05-22-silent-bugs.md`). Match it exactly.

**The rule:** the snapshot write must happen in its **own transaction, after the membership
transaction commits** — never inside it. `replace_espn_league_members` does its `delete` +
`insert` inside a single `with engine.begin() as conn:` (`database.py:10110-10116`). Appending
a snapshot insert inside that block means **a snapshot bug rolls back the delete+insert and
leaves the league with zero members**, on every ESPN/MFL/Fleaflicker import. That is a
total-league-data-loss path introduced by a retention feature. Also note `G-040` — `begin_nested`
silently commits on the main-engine SQLite path (`living-memory/GOTCHAS.md`, commit `1090b2d`) —
so "just use a savepoint" is not the escape hatch it looks like. Separate transaction, after
commit, wrapped, logged.

**On the plan's "on-sync change-detect write may be added if it is genuinely free" (§5.2).** It
is genuinely free, and it should be the *primary* mechanism rather than the optional extra —
see A2. The payload is already in hand at both writers; a `roster_hash` comparison plus a
conditional insert costs one indexed read and one write.

---

### A2. Cron and scheduling

**Position: (a) do not build a new dedicated cron yet, because there is nothing to schedule it
with; (b) ship sync-driven capture now; (c) the weekly backstop is a follow-on gated on
`infra/render-cron-migration` merging; (d) do not fold it into `daily-tick` or `hourly-tick`.**

**The finding that changes the plan.** `render.yaml` at `origin/main` declares exactly three
cron services: `notif-realtime-tick`, `notif-hourly-tick`, `notif-daily-tick`. There is **no**
`value-snapshot-daily`. The history:

- `1e50d3e` (2026-07-26) — *"fix(render): remove value-snapshot-daily cron — broke blueprint
  sync"*: new blueprint cron services are billable resources requiring account approval; the
  sync failed on the operator's account.
- `57300ae` (2026-08-09, **unmerged**, `origin/infra/render-cron-migration`) — *"move cron
  scheduling off Render blueprint to GitHub Actions"*. Its message states, as established fact:
  blueprint cron *"breaks blueprint sync outright rather than degrading gracefully — **this is
  why the notif-\*-tick jobs never actually ran**, why value-snapshot-daily was reverted
  same-day on 2026-07-26, and why players-refresh was left as 'provision by hand in the
  dashboard.'"* It adds `.github/workflows/render-cron.yml` scheduling all five endpoints
  externally, mirroring the working `keep-warm.yml` pattern.
- Corroborated in `living-memory/GOTCHAS.md:179`: *"new blueprint **cron services are billable
  and need account approval**, so blueprint sync fails (`1e50d3e`)."*

**Consequence 1 — the plan's headline evidence is unverified.** §1 says
`player_value_history` has written daily *"unflagged, scheduled in `render.yaml` at 06:00 UTC,
with an hourly self-healing fallback (`docs/architecture.md:230`)."* The `render.yaml` half is
false. The fallback half depends on `hourly-tick` firing — and `hourly-tick` was scheduled by
the same blueprint that `57300ae` says never synced. **`player_value_history` may have
substantial gaps or may be near-empty.** I attempted to settle this directly
(`SELECT snapshot_date, scoring_format, count(*) FROM player_value_history GROUP BY 1,2 ORDER
BY 1 DESC LIMIT 45;` against `DATABASE_URL_PROD`) and the sandbox blocked the call. **This is
the single highest-value thing to check before any of this is built**, because §3's entire
thesis is that team value is a *join* — a roster history joined to a gappy value history
produces a gappy chart, and the recap's headline stat is that chart.

**Consequence 2 — priority inversion.** If C4 has gaps, then merging
`origin/infra/render-cron-migration` is **more urgent than the roster snapshot**. It is a
79-line workflow file plus a `render.yaml` trim, it is already written and reviewed, and it
un-breaks five endpoints at once — including the one this whole plan is built on top of. The
plan's §8 does not mention it. It should be P0 item zero.

**Where the weekly job should live, once there is a scheduler.** A new dedicated
`POST /api/cron/roster-snapshot`, not a slot in an existing tick. `docs/architecture.md:230`
makes the argument for `value-snapshot` verbatim and it transfers without modification:
*"Kept separate from `daily-tick` so a push-scan failure can't stop history collection."* The
same reasoning covers roster retention. I'll note the irony the plan should have caught: that
precedent is stated in the doc and **violated in practice** — the *operative* mechanism for
value snapshots is the `hourly-tick` fallback guard (`server.py:16446-16460`), i.e. retention
is riding the push-scan tick today, exactly what the precedent forbids. Honour the precedent
structurally rather than repeating the workaround.

**The runtime constraint the plan does not mention.** `render.yaml` startCommand:
`gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`. **One worker.** A weekly
all-league fan-out executed inline inside the cron handler blocks the only worker — the app is
down for the duration — and blows the 120s timeout at modest league counts. The established
answer is `POST /api/cron/players-refresh` (`server.py:16776-16793`): *"Render 'cron' is an HTTP
POST into the single-worker web service, so this handler must NEVER do the ~45 s fetch inline.
It starts a daemon thread and returns **202 immediately**."* Plus a per-tick budget, as the
draft-status sweep does (`_DRAFT_STATUS_SWEEP_BUDGET`, `server.py:16472-16480`, stalest-first so
it rotates rather than starves). Both patterns are mandatory for the roster job, not optional.

**Restating the cadence recommendation inside YR-1.** The operator ruled weekly, and weekly is
what should be delivered. My disagreement is only about *which mechanism carries the contract*.
The plan makes the scheduled job the contract and the on-sync write the optional extra. Given
that (a) the scheduler does not currently exist, (b) the on-sync write is free and the
scheduled one is not, and (c) an on-sync write on an active league produces resolution *finer*
than weekly — I'd invert it: **on-sync change-detect is the primary writer, the weekly cron is
the backstop for dormant leagues.** That delivers weekly-or-better coverage, which satisfies
YR-1's contract, and it ships this month instead of after an infra merge. The plan's §5.2
already contains the reasoning for this ("It degrades gracefully. Active leagues get
near-perfect resolution for free; dormant leagues fall back to the weekly job") — it just
assigned the roles the other way round.

---

### A3. Multi-platform

**Position: the sync-driven write sits BELOW the platform abstraction (free, universal); the
scheduled write sits ABOVE it (per-platform, and this is where ESPN breaks).**

**Below — why the sync path is platform-agnostic for free.** By the time either
`league_members` writer is called, every platform has already normalised into Sleeper
player-id space. ESPN: `mapped["rosters"]` after the crosswalk (`server.py:19776`). MFL:
same (`server.py:21387`). Fleaflicker: same (`server.py:22989`). Sleeper: raw client ids
(`server.py:15267`). One hook, four platforms, zero platform code. This is the strongest
argument for A1's seam choice and it is the half of the plan that really is a week of work.

**Above — the scheduled job, and the plan's central cost error.** §5.2 asserts *"**No extra API
calls.** Sync already fetches rosters. Snapshotting is a hash comparison and an occasional
insert on data already in memory."* Verify `/api/session/init`'s docstring
(`server.py:14657-14671`) and body parse (`:14683-14687`):

```
user_player_ids   = [str(x) for x in body.get("user_player_ids",  [])]
opponent_rosters  = body.get("opponent_rosters", [])
```

**The rosters arrive in the request body. The server does not fetch them.** So "data already in
memory" is true only while a client is driving the request. A weekly cron has no client and no
in-memory rosters; it must fetch, per league, per platform. That is a new subsystem, not a hash
comparison, and it is the difference between the plan's "~1 week" and reality.

(Two secondary consequences of client-supplied rosters worth stating: the snapshot's integrity
is bounded by client correctness and client version, and a *history of record* sourced from an
untrusted client is a weaker artifact than one the server fetched. `#151` already shows this
surface moving — `server.py:15258-15266` switched to storing raw client ids.)

**What breaks per platform for a scheduled fetch:**

| Platform | Server-side roster fetch | Verdict |
|---|---|---|
| **Sleeper** | Public, unauthenticated. Already done in-repo at `server.py:14424`, `:10567`, `trade_block_service.py:102`, `outlook/league_state.py:176` | **Works.** Two calls per league (`/rosters` + `/users`) |
| **MFL** | Public leagues fine; private needs stored credentials (`MFL_USERNAME`/`MFL_PASSWORD` class) | Workable, unproven unattended |
| **Fleaflicker** | Link/import path exists | Unproven unattended |
| **ESPN** | Private leagues need the user's Fernet-encrypted `espn_s2` + `SWID` (`database.py:1322-1350`), which **expire** (`expires_hint_at`) and return `403 espn_auth_required` requiring a user reconnect (`server.py:19722-19727`) | **Breaks silently.** An unattended weekly ESPN snapshot goes dark whenever cookies lapse — and goes dark precisely when nobody is watching, which is the exact failure a weekly grid exists to prevent |

**The ESPN identity problem, which is worse than the fetch problem.** `replace_espn_league_members`
docstring (`database.py:10087-10096`): *"user_id is the linking user's real FTF id for their own
team and a synthetic `espn:` id for counterparties."* And `database.py:7911` documents the churn
directly — an orphaned pick-owner is *"a SWID rotation on re-import, or a manager who left."*
**ESPN member identity is not stable across re-imports.** Two consequences:

1. A roster-history table keyed on `user_id` will **fragment** on ESPN: the same physical team
   accumulates rows under `espn:<x>`, then a real FTF id when that manager links, then a
   different synthetic id after a SWID rotation. The season chart for that team silently splits
   into three partial charts. See disagreement **B4** for the fix.
2. §5.3's growth claim — *"when a leaguemate joins in November, they get a full season of value
   history on day one"* — **works on Sleeper and does not work on ESPN or MFL** without an
   explicit identity-reconciliation step that the plan does not spec. On Sleeper the key is the
   real Sleeper `user_id`, so the join is free. On ESPN/MFL the joining user's FTF id has no
   relationship to the `espn:`/`mfl:` synthetic id their history accrued under.

**C3 (pick ownership) on ESPN is not a data-capture problem, it is a category problem.** ADR-010
is unambiguous: *"ESPN has no rookie-draft concept (operator ruling, 2026-08-06)… there is **no
platform draft object to read, not now and not ever**."* ESPN pick ownership is user-*asserted*
(`draft_picks.source='user'`, `assigned_by`, `assigned_at`), and ADR-010 §"Decision" adds that
assertions can be **contested** (two users, two different owners) or **orphaned**
(`database.py:7902-7920`). So a "pick ownership over time" history on ESPN is a history of
*claims*, not of ownership, and some of those claims are mutually contradictory by design. The
recap must not render "what your first became" for an ESPN league as though it were fact. The
plan's C3 row (§4.1) and §11's eng-backend handoff treat pick history as uniform across
platforms. It isn't.

**The abstraction the plan misses entirely.** `backend/outlook/league_state.py` already defines
the exact seam this needs:

- `LeagueStateProvider` — a `runtime_checkable` Protocol, described in its own header as the
  *"Swap seam… Concrete providers register into `LEAGUE_STATE_PROVIDERS` keyed by platform
  string. Only Sleeper is implemented; `mfl`/`fleaflicker`/`espn` are registered stubs that
  raise `NotImplementedError` so the seam is real and the gap is explicit."*
- `TeamState(roster_id, user_id, username, …)` — and it already splits starters from bench via
  `_BENCH_SLOTS = {"BN", "IR", "TAXI"}`, which supplies the plan's proposed `starters_json`
  field for free.
- Its Sleeper provider already calls `GET /league/{id}/rosters` (`league_state.py:176`) and
  parses `roster_id`, `owner_id`, `players[]`, `starters[]`.

A scheduled snapshot should implement against `LeagueStateProvider` and register a provider per
platform. Building a second parallel platform-fetch layer beside it is the duplication I exist
to prevent, and the registered-stub design means the ESPN gap stays *explicit* rather than
becoming a silently-empty snapshot.

---

### A4. Is this ADR-worthy?

**Yes. Unambiguously.** Four reasons, in order of weight:

1. **It reverses a documented storage posture.** `league_members` is *designed* as snapshot
   semantics — the plan itself catalogues the family: `league_members` overwritten on sync
   (`database.py:327`), `trade_block` *"Replaced atomically on every sync (delete + insert,
   snapshot semantics like `member_rankings`)"* (`database.py:333-339`), `member_rankings`
   delete+insert (`:379`). Introducing an append-only history of league state changes the class
   of thing this system stores. ADR-010 was written for precisely this kind of change and says
   so: *"That combination is what makes this decision recordable rather than obvious: it
   reverses two documented positions at once."*
2. **It is cross-cutting.** Two DB writers shared by four platform import paths, a new cron
   surface, a scheduler dependency, and a platform-provider seam. That is the definition of my
   lane.
3. **It creates a third history lineage, and the plan does not know about the second one.**
   `backend/wrapped_collector.py` and the `wrapped_events` table already exist and are
   ***FROZEN* (analytics P0 cutover)** (`database.py:1026`, `:1040`), with the cutover boundary
   stored as an epoch in `model_config` (`database.py:2083-2097`, reader at `:3494`) and a
   union-read already implemented — *"`wrapped_events.created_at < cutover ∪
   user_events.occurred_at`"* (`database.py:6037-6071`). So a December recap reading "the 2026
   season" crosses a lineage seam mid-year, and will now cross a *third* store. Whoever builds
   P3 in November will not rediscover this from the code. It has to be written down, and an ADR
   is where.
4. **Precedent.** ADR-001 (query-cache persistence) is the same genus — a storage-posture
   decision with no user-visible surface.

**ADR sketch — `adr-011-league-state-history-is-append-only`:**

- **Context.** Every league-state table is snapshot semantics; four platform import paths
  converge on two writers; consensus value history already exists (`player_value_history`,
  `#57`) but is unjoinable without roster history; the recap (#46), the movers digest (#33) and
  player profiles (#17) all need the join; operator rulings YR-1…YR-7 (2026-08-13) set weekly
  cadence, both-roster-and-value storage, and all-teams scope.
- **Decision.** One new append-only table written from inside the two `league_members` writers,
  in its own transaction after theirs commits, keyed on a **platform-native stable team key**
  with `user_id` as a nullable re-resolvable attribute; change-detected by `roster_hash`;
  gated by a write-only flag; a dedicated cron backstop added once an external scheduler
  exists. Denormalise `team_value` alongside the roster ids, following the
  `player_value_history` precedent (`database.py:992-993`).
- **Alternatives rejected.** (i) *Hook the four routes* — four chances to miss one, and YR-6
  makes completeness the point. (ii) *Fold into `daily-tick`* — violates the retention-off-the-
  push-tick precedent (`architecture.md:230`). (iii) *Version `league_members` in place*
  (soft-delete / valid-from) — turns every existing read of a hot table into a temporal query;
  `load_league_members` (`database.py:5585`) has many callers. (iv) *End-of-season transaction
  replay only* — the plan's own §2.3 correctly kills this as fragile and Sleeper-only, and I
  agree. (v) *Reuse the frozen `wrapped_events`* — frozen by the analytics P0 cutover; unfreezing
  it re-opens a settled decision.
- **Consequences.** New retention obligation; the first append-only league-state store, which
  sets the pattern the `member_rankings` history (C6) will follow; a third lineage the recap
  must union across; ESPN identity fragmentation must be solved at the key, not papered over
  downstream; on ESPN, C3 records assertions rather than facts.

---

### A5. Blast radius and rollback

**Blast radius is genuinely small — conditional on one rule.**

What makes it small:
- **New table, no ALTER.** New tables come free and idempotently from
  `metadata.create_all(engine)` (`database.py:2726`); the fragile path is the additive-column
  `ALTER TABLE` loop (`database.py:1998-2053`) and this change does not need it.
- **No read-path change.** Nothing existing queries the new table.
- **No client contract change.** Nothing in `docs/cross-client-invariants.md` moves. Mobile,
  web and extension are untouched — which also means no Maestro delta and no sim-gate tier
  beyond the backend default (the feature-gate matrix in `docs/runbook.md` should still be
  consulted, but this is a server-only change).
- **Additive to a daemon that already tolerates failure.** The session-init daemon already runs
  four best-effort capture blocks; a fifth is the established shape.

**The one way it becomes large — and it is a data-loss path, not a bug.** Writing the snapshot
inside `replace_espn_league_members`'s single `engine.begin()` block
(`database.py:10110-10116`) makes a snapshot failure roll back the delete+insert, leaving the
league with **zero members**, on ESPN/MFL/Fleaflicker, on every import. This is easy to do by
accident — the conn is right there and it looks like the tidy thing to do. It must be an
explicit "never" in the PRD, with a test. Related trap: `G-040` (`begin_nested` silently commits
on main-engine SQLite) means a savepoint is not a safe middle ground.

Second-order risk: write amplification on one worker. Sleeper syncs already sweep 18
transaction legs per session-init (`sleeper_trades_service.py` `WEEKS = range(1, 19)`). Adding
a hash + conditional insert is negligible. Adding a *fetch* to that daemon is not.

**Rollback — and where I disagree with the framing of D-P1-07.**

The operator's standing view is that feature flags gating server routes are not usable rollback
levers. **That is correct and it does not apply here.** Read what D-P1-07 actually says
(`docs/plans/audit-p1-remediation/DECISIONS-p1.md:139-145`): `growth.share_landing` gates
*server routes* that **already-shared external links point at**, so flipping it off *"would
break every link already shared, including ones sitting in other people's message threads. The
flag is therefore not a usable rollback lever."* The disqualifying property is **external
references to a gated read surface**, not flags in general.

A capture flag gates a **write with no external references**. Flipping it off stops new rows
and changes nothing any client can observe. This is exactly the pattern already in production
for the three sibling capture blocks in the same daemon: `market.trade_capture`
(`config/features.json:51`, `server.py:15363`), `sleeper.trade_block` (`:47`, `server.py:15292`),
`picks.owned_sync` (`:49`, `server.py:15318`).

**Recommendation:**
- `market.roster_history`, **default ON at merge** — capture that ships dark is capture that
  did not happen, and the whole urgency argument is about days. ON is the resting state.
- The flag is the **stop** lever (instant, no deploy, via `FTF_FLAGS` or `config/features.json`).
- A revert commit is the **fix** lever.
- **One flag, one direction.** When P3 adds recap *read* routes, they get their own flag. Do not
  let a single flag come to gate both the write and a read surface — that is the precise
  mistake D-P1-07 was written about.
- Data rollback is clean *because* the table is append-only and carries the plan's `source`
  column: `DELETE … WHERE source = 'sync' AND snapshot_at > '<bad-deploy>'`. Keep `source`. It
  is the cheapest thing in the schema and the only thing that makes a bad week undoable.

One honest caveat on `FTF_FLAGS` as the lever: NEXT.md item 0c flags that a malformed
`FTF_FLAGS` currently fails *silently* to `{}` and the hardening patch is drafted-and-unapplied.
That is a pre-existing sharp edge on the kill switch this design leans on. Worth the operator
knowing; not a blocker.

---

### A6. Interaction with in-flight work

Checked `living-memory/HANDOFF.md`, `NEXT.md`, and every remote branch unmerged into
`origin/main`, sorted by recency.

1. **`origin/infra/render-cron-migration` (`57300ae`, 2026-08-09) — hard dependency.** Already
   covered in A2. This is the collision that matters. It also **touches `render.yaml`**, so if
   the recap work adds a cron there, the two conflict directly. Merge order: cron migration
   first, always.

2. **`NEXT.md` item 5 (2026-08-13) is the same work, unrecognised.** *"**Roster-diff feasibility
   check for a re-rank prompt.** (eng-backend, blocks GD-6) Does league sync expose a usable
   roster diff?"* The plan's `roster_hash` + append-only history **is** that feasibility answer,
   and a roster diff falls out of two consecutive snapshot rows for free. Sequence them together
   or the diff gets specced twice by two sessions. Neither document references the other.

3. **Mock-draft branches (`origin/closeout-mock-draft`, `origin/mock-draft-fix`, 2026-08-13 —
   the most recent unmerged work in the repo) collide with C3, not with C1.** C1 (rosters)
   touches `league_members` and is clear. C3 (pick-ownership history) touches `draft_picks`,
   which is the table ADR-010 just extended with `source` / `assigned_by` / `assigned_at` plus
   the contested/orphaned derivation (`database.py:7902-7960`) — and which the mock-draft work
   is actively moving. **C3 should not start until those land.** The plan already schedules C3
   into P1 (Sept–Oct), which happens to be right; the reason should be recorded so nobody pulls
   it forward.

4. **Send-in-MFL / Send-in-ESPN are already merged and live** (`trade.send_in_mfl: true`,
   `config/features.json:46`; HANDOFF 2026-08-12). Not a collision — but they are why
   `replace_espn_league_members` now has three platform callers instead of one, which is what
   makes A1's seam argument work.

5. **The baseline is not green.** HANDOFF (2026-08-13) and NEXT item 6: *"6 failing
   `test_rookie_scope.py` tests live on `origin/main`, verified by stashing. Nobody is tracking
   them."* Whoever builds P0 lands on a red suite and must not be allowed to attribute those
   six to their own change — or, worse, to treat red-as-normal.

6. **CI gates less than it appears to.** HANDOFF: seven `check-*.js` structural suites are
   `npm run`-only and none gates anything (NEXT item 1, *"noted in the ledger for three sessions
   running"*). Relevant here only as calibration: "CI is green" is weaker evidence in this repo
   than it sounds, and the feature-gate contract leans on it.

No unmerged branch modifies `upsert_league_members` or `replace_espn_league_members`. The seam
in A1 is currently uncontested.

---

## B. Disagreements and corrections

Ordered by how much they change the plan.

**B1. §1 / §2.1 — "scheduled in `render.yaml` at 06:00 UTC, with an hourly self-healing
fallback" is false, and the value backbone is unverified.**
*Evidence:* `render.yaml` at `origin/main` declares three cron services and no
`value-snapshot-daily`. `1e50d3e` (2026-07-26) removed it same-day — *"broke blueprint sync…
new blueprint cron = new billable resource needing approval."* `57300ae` (unmerged) states the
`notif-*-tick` jobs **never ran** for the same reason, which puts the `hourly-tick` fallback
guard (`server.py:16446-16460`) — the plan's stated safety net — on the same broken scheduler.
`living-memory/GOTCHAS.md:179` corroborates.
*Why it matters:* §1's "half of what the operator asked for is already running" is the load-
bearing premise of the whole document, and §3's join thesis means a gappy C4 makes C1
unjoinable. **Required before build:**
`SELECT snapshot_date, count(*) FROM player_value_history GROUP BY 1 ORDER BY 1 DESC LIMIT 30;`
against prod. I attempted it; the sandbox blocked the call.
*Fix:* add "merge `infra/render-cron-migration`" as P0 item zero, ahead of the roster table.

**B2. §5.2 — "No extra API calls. Sync already fetches rosters… data already in memory" is
false for the weekly job, which is the mechanism YR-1 made the contract.**
*Evidence:* `/api/session/init` takes `user_player_ids` and `opponent_rosters` from the
**request body** (`server.py:14661-14667` docstring, `:14683-14687` parse). The server performs
no roster fetch on this path.
*Why it matters:* it is the plan's entire cost justification for weekly-over-four-weekly, and
the ~1-week estimate in §8 rests on it. A weekly cron needs a per-platform server-side fetch
layer, a 202-immediately daemon (single worker, 120s gunicorn timeout), and a per-tick budget.
*Fix:* either re-cost P0, or (my recommendation, A2) make the on-sync write the primary
contract and the cron the dormant-league backstop — which satisfies YR-1's weekly-or-better
guarantee, keeps the cost claim true, and ships now.

**B3. §5.3 — the late-joiner growth claim is Sleeper-only as specced.**
*Evidence:* on ESPN/MFL/Fleaflicker, counterparty teams are stored under synthetic `espn:` ids
(`database.py:10087-10096`), and `database.py:7911` documents SWID rotation on re-import
orphaning owner ids. A joining user's FTF id has no relationship to the synthetic id their
history accrued under.
*Why it matters:* §7 calls this *"the strongest invite this product will ever have"* and §9
makes it the mitigation for the 3–5-user sample-size risk. Both claims silently assume Sleeper.
*Fix:* spec an identity-reconciliation step (match on platform team key at link time,
re-stamping `user_id` forward), or state the claim as Sleeper-only.

**B4. §5.1 — the schema sketch's key, `user_id (or roster_id for non-FTF teams)`, is the bug.**
*Evidence:* the "or" is a polymorphic key. Combined with B3's identity churn, the same physical
ESPN team accumulates rows under `espn:<x>` → real FTF id → `espn:<y>` after a rotation, and the
season chart splits into three partial charts with no error anywhere.
*Fix:* key on `(league_id, platform_team_key, snapshot_at)` where `platform_team_key` is the
platform-native stable id (Sleeper `roster_id` or `owner_id`, ESPN `team_id`, MFL franchise id),
with `user_id` a **nullable, re-resolvable attribute column**. Note the hidden cost the plan
does not carry: **`league_members` has no such column today** (`database.py:321-331`; unique key
is `(league_id, user_id)`), so this needs either a column added there or the mapping derived at
snapshot time. Flagging it as work, not as a blocker.

**B5. §2 omits `wrapped_events` / `wrapped_collector.py` entirely.**
*Evidence:* `backend/wrapped_collector.py` exists (70 lines, `record_event` with seven valid
event types); `wrapped_events_table` at `database.py:1040`, marked ***FROZEN* (analytics P0
cutover)** at `:1026`; the cutover epoch lives in `model_config` (`:2083-2097`, reader `:3494`);
the union-read across the boundary is already implemented at `:6022-6071`.
*Why it matters:* §2 is titled "what is banked" and this is banked Wrapped data the recap will
have to read across a mid-2026 lineage seam. §11's an-data-architect handoff mentions
`wrapped_viewed` but not the frozen store.
*Fix:* add a row to §2.1 and a line to the P3 notes.

**B6. §8 — "~1 week of work" is right for the sync half and wrong for the whole.**
*Evidence:* aggregating B2 and B4. Sync-driven capture at two writers with a hash and a
conditional insert is genuinely ~a week. Adding: a fetch layer per platform, ESPN credential
handling for unattended runs, a 202 daemon with a rotation budget, a `platform_team_key`
mapping, and a cron that has no scheduler — is not.
*Fix:* split P0 into **P0a (sync-driven, ~1 week, ship now)** and **P0b (scheduled backstop,
gated on the cron migration)**. This also makes the §8 claim *"P0 is worth doing even if the
recap slips a year"* true of a thing that can actually ship before Week 1.

**B7. §4.1 C3 and §11 treat pick-ownership history as uniform across platforms. On ESPN it
records assertions, not ownership.**
*Evidence:* ADR-010 — *"ESPN has no rookie-draft concept (operator ruling, 2026-08-06)… there is
**no platform draft object to read, not now and not ever**"*; ESPN pick rows are
`source='user'`, and can be **contested** (two users asserting different owners) or **orphaned**
(`database.py:7902-7920`).
*Fix:* mark C3 Sleeper/MFL-authoritative, ESPN-asserted. The recap must not render "what your
first became" for an ESPN league as fact.

**B8. §5.1 and §11 miss the platform seam that already exists.**
*Evidence:* `backend/outlook/league_state.py` — `LeagueStateProvider` Protocol +
`LEAGUE_STATE_PROVIDERS` registry keyed by platform, `TeamState(roster_id, user_id, username)`,
starters/bench split via `_BENCH_SLOTS`, Sleeper implemented and the other three registered as
explicit `NotImplementedError` stubs.
*Why it matters:* it is the correct home for a scheduled fetch, and its `starters[]` handling
supplies the plan's optional `starters_json` for free. Building a parallel fetch layer beside it
is avoidable duplication.

**B9. §9's privacy row is stale in one direction — the D-P1-12 takedown already shipped.**
*Evidence:* both routes are now gated — `server.py:17178` `/og/tiers/<pos>/<username>.png` and
`:17285` `/s/tiers/<pos>/<username>`, behind `growth.tier_board_share`, which is `false` in
`config/features.json:131` with an explicit comment: *"OFF is the resting state, not a dark
launch: do not flip without an explicit operator reversal of D-P1-12."*
*Why it matters:* minor, but §9 and the YR-3 clarification read as though the takedown is
outstanding. It is done, and YR-3's line — public URL exposure prohibited, in-app league-context
display permitted — is cleanly enforceable today by leaving that flag alone. Worth stating
positively so nobody re-does it.

**B10. `docs/architecture.md:230` is drifted and contradicts `docs/runbook.md`.**
*Evidence:* `architecture.md:230` claims value-snapshot is *"Provisioned in `render.yaml`
(`value-snapshot-daily`, 06:00 UTC) since 2026-07-26."* `runbook.md:295` correctly records that
*"the endpoint was never provisioned in `render.yaml`… added but **broke Render blueprint
sync**… and was removed same-day."* Two reference docs, opposite facts. The plan cited the wrong
one — reasonably, since it reads as the authoritative summary.
*Fix:* `architecture.md:230` must be corrected as part of this work (my standing guardrail: a
design review that finds drift files the fix). It is also the direct cause of B1 — this plan is
the first casualty of that drifted line, and it will not be the last.

**B11. Minor — §2.3's "semi-recoverable" is slightly generous on one axis and correctly harsh
on the others.** Sleeper transaction replay is real (`sleeper_trades` already sweeps all 18 legs
per sync, `sleeper_trades_service.py` `WEEKS = range(1, 19)`, idempotent on `transaction_id`),
so for Sleeper leagues **already synced with `market.trade_capture` on** the raw material is
banked *today*, not merely fetchable later. That makes the Sleeper backfill somewhat stronger
than §2.3 implies. Every other caveat §2.3 raises stands, and the conclusion — snapshot rather
than salvage — is right. I raise it only because the urgency argument is stated as absolute
("every day of delay is unrecoverable") when for the Sleeper majority it is closer to "every day
of delay costs a reconstruction of decreasing fidelity." That is still a good reason to hurry.
It is not a reason to skip B1's verification first.

---

## C. Open questions for the other reviewer (an-data-architect)

1. **Volume under the corrected key.** B4 changes the grain from `(league_id, user_id)` to
   `(league_id, platform_team_key)`. Does that move your row estimates, and does the
   `roster_hash` change-detect meaningfully cut the 240-rows-per-league-season figure in
   practice, or is roster churn high enough that nearly every weekly slot writes anyway?
2. **`user_id` as a nullable attribute.** I want the identity column re-stampable when an
   ESPN/MFL manager later links (B3). Does that break any query shape you have in mind, and
   would you rather see the reconciliation as a mutation of history rows or as a separate
   identity-mapping table?
3. **Third lineage (B5).** Given `wrapped_events` is frozen with a `model_config` cutover epoch
   and `user_events` carries everything after, does adding a third store change your taxonomy
   recommendation — and should the recap read a single union view rather than three stores?
4. **C6 (`member_rankings` history) grain.** YR-3 put it in scope. `member_rankings` is
   delete+insert on submit, and `elo_history` (`database.py:971`) already logs per-player Elo
   *only for players whose Elo changed*. Is C6 genuinely a new table, or is it `elo_history`
   with the cadence backstop from §5.4 and a leaguemate-scoped read? I lean toward the latter —
   one fewer table — but the query shape is your call.
5. **`team_value` denormalisation and format.** YR-2 says store both. Team value is
   format-dependent (`1qb_ppr` / `sf_tep`). Two value columns per row, a `scoring_format`
   column in the key, or one row per format? I'd take a `scoring_format` column in the key for
   consistency with `player_value_history` (`database.py:995-1008`), but it doubles the rows.
6. **If B1 confirms `player_value_history` has gaps** — does that change your view of what the
   recap can honestly render, and should the capture spec include a `values_complete` marker per
   snapshot so a December chart can grey out unjoinable weeks rather than interpolating?

---

## D. Doc-sync list

For whoever builds this (`pm-technical` writes the PRD; `eng-backend` builds):

| Doc | Why |
|---|---|
| `docs/architecture.md:230` | **Correct the drift now** (B10) — it claims a `render.yaml` cron that does not exist and contradicts `runbook.md:295` |
| `docs/architecture.md` § Cron ticks | New `/api/cron/roster-snapshot` row, once P0b lands |
| `docs/data-dictionary.md` | New table (`backend/database.py` schema trigger) |
| `docs/api-reference.md` | New cron route, once P0b lands |
| `docs/config-reference.md` | `market.roster_history` flag |
| `docs/adr/adr-011-*.md` | Per A4 |
| `living-memory/HLD.md` / `LLD.md` | Append-only league state is a convention shift |
| `living-memory/DECISIONS.md` | The A2 inversion (on-sync primary, cron backstop) if adopted — it is a deviation from the plan's reading of YR-1 and needs the operator's eye |
| `docs/cross-client-invariants.md` | **n/a** — server-only, no client contract moves |
| `mobile/.maestro/` | **n/a** — no user-visible mobile change in P0 |
| `docs/templates/feature-scope.md` | Required: this is schema + data collection, explicitly **not** express-lane eligible (root `CLAUDE.md` bright line). The plan says so at §11 and is right |
