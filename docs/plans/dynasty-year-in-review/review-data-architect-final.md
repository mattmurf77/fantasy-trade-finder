# Round 2 — reconciliation (an-data-architect × eng-architect)

> **Reviewer:** an-data-architect. **Date:** 2026-08-13.
> **Reconciling:** `analytics-r1.md` (mine) × `architect-r1.md` (eng-architect), against
> `docs/business/product/2026-08-13-dynasty-year-in-review-plan.md`.
> **Verified against:** `origin/main` @ `60fccc7`.
> **Operator rulings YR-1…YR-7 remain binding.** Nothing below reopens them.
> **Design only. No source file edited.**

**Headline:** we converge on one design. The architect's inversion (on-sync primary) wins,
but for a sharper reason than either of us gave in R1 — **the on-sync path is the only
mechanism whose correctness does not depend on the open scheduler question.** Their
`team_key` diagnosis is right and I concede it; their proposed key is not, and I hold mine.
Their "third lineage" objection to `league_board_history` is category-confused and I hold
that table. Two things neither R1 caught: the Sleeper sync path **cannot** produce a stable
team key today without reusing a fetch that is already happening and being discarded, and
the pick-snapshot must be the **last** capture block in the daemon.

## Contents

- [1. AGREED](#1-agreed)
- [2. RESOLVED](#2-resolved)
  - [(a) Scheduling](#a-scheduling--reconcilable-their-inversion-wins)
  - [(b) Write seam](#b-write-seam--accepted-with-one-amendment-they-could-not-have-made)
  - [(c) `team_key`](#c-team_key--i-concede-the-diagnosis-amend-the-fix-reject-their-key)
  - [(d) C5/C6 storage](#d-c5c6-storage--i-hold-league_board_history)
  - [(e) `league_state.py`](#e-league_statepy--accepted-with-a-scope-limit)
  - [(f) K/DEF coverage](#f-kdef-coverage--carried-with-the-mitigation)
  - [(g) Flagging](#g-flagging--agreed-with-one-addition)
  - [(h) Pick ownership](#h-pick-ownership-c3--fold-in-survives-with-an-ordering-constraint)
- [3. STILL DISPUTED](#3-still-disputed)
- [4. The single check that settles the open question](#4-the-single-check-that-settles-the-open-question)
- [5. Final DDL](#5-final-ddl)

---

## 1. AGREED

Stated once, concretely. These are joint positions; neither of us needs to be cited for them.

1. **§1's `render.yaml` claim is false, and `docs/architecture.md:230` is drifted.** Found
   independently by both reviewers, confirmed by the coordinator (`1e50d3e`, removed
   same-day). `runbook.md:295` is the correct record. **Fixing `architecture.md:230` is part
   of this work**, not a follow-up — this plan is the first casualty of that line.
2. **§5.2's "no extra API calls… data already in memory" is false for the weekly job.**
   `/api/session/init` takes rosters from the **request body** (`server.py:14664-14670`,
   `:14686-14690`). Same finding, same evidence, independently.
3. **Rosters at the sync seam are client-supplied**, which bounds snapshot integrity by
   client correctness and client version. A history *of record* sourced from an untrusted
   client is a weaker artifact than a fetched one. Both flagged it; it is a real cost of the
   on-sync design and must be stated in the ADR rather than buried.
4. **A cron must never read `league_members` and stamp it with the current period.** That
   fabricates history and violates `runbook.md:295`'s standing rule ("*a gap stays a gap —
   do not fabricate history*"). The scheduled path **fetches or writes nothing.**
5. **`player_value_history` completeness must be verified before build.** Their B1 and my
   A6 gap-defense converge: §3's join thesis means a gappy C4 makes C1 unjoinable, and the
   failure mode is a chart that renders a coverage gap as a roster wipe. See §4.
6. **Weekly cadence (YR-1) stands.** Neither of us disputes the ruling; the disagreement was
   only ever about which mechanism carries the contract.
7. **`source` stays in the schema.** Append-only + `source` is what makes a bad deploy
   undoable (`DELETE … WHERE source='sync' AND snapshot_at > '<bad-deploy>'`). Cheapest
   column in the table.
8. **This is ADR-worthy — `adr-011-league-state-history-is-append-only`.** It reverses a
   documented snapshot-semantics posture across a table family (`league_members`,
   `trade_block`, `member_rankings`), it is cross-cutting, and the recap's read path crosses
   an analytics cutover seam that nobody will rediscover from code in November.
9. **`roster_hash` change-detection is right**, with my R1 refinement they did not contradict:
   **the hash must never suppress the weekly write.** `team_value` moves weekly even when the
   roster does not, so a hash-suppressed series puts holes in exactly the chart YR-2 exists
   to stabilize. The hash's jobs are `changed_from_prev` and suppressing *extra* intra-week
   on-sync writes.
10. **Their B9 — the D-P1-12 takedown already shipped.** `growth.tier_board_share` is `false`
    in `config/features.json` with an explicit do-not-flip comment; both `/og/tiers/…` and
    `/s/tiers/…` are gated. I missed this. §9's privacy row and the YR-3 clarification read
    as though the takedown is outstanding; it is done, and YR-3's line is enforceable today
    by leaving that flag alone.
11. **Their B7 — C3 on ESPN records *assertions*, not ownership** (ADR-010: no platform draft
    object "not now and not ever"; rows are `source='user'` and can be contested or orphaned).
    Accepted, and it upgrades my `pick_source` column from metadata into a **rendering rule**.
12. **Their B11 / my A7+B10 converge:** for Sleeper leagues already synced with
    `market.trade_capture` on, the replay raw material is banked *today*. Both of us
    independently concluded the urgency argument is real but should not be stated as absolute.
13. **The plan's §3 principle (store inputs, join at read) and the four-weeks→weekly argument
    are correct.** Neither reviewer disputes them.

---

## 2. RESOLVED

### (a) Scheduling — reconcilable; their inversion wins

**These positions are reconcilable, and the architect's is right.** I withdraw
`daily-tick + weekday gate` as the *primary* mechanism.

**Not for their stated reason.** Their argument was "there is no working scheduler," which
the coordinator has correctly downgraded: three cron services **are** declared on
`origin/main`, and whether they fire is open (their supporting evidence is an unmerged
branch's assertion, not established fact). An argument resting on an open question cannot
settle a design.

**The reason that does hold, and it is decisive:** *the on-sync write is the only mechanism
whose correctness is independent of the open question.* It needs no scheduler at all. Every
other candidate — my daily-tick gate, their dedicated cron, the hourly guard — is a bet on
the same unverified thing. Under genuine uncertainty you make the load-bearing path the one
that does not branch on the unknown.

My own R1 finding reinforces this from the other side, as the coordinator noted: a cron that
reads `league_members` stamps client-supplied, possibly months-old rosters with this week's
period key. So the sync path must be involved *whatever* the scheduler answer turns out to
be. Both roads lead to on-sync primary.

**Converged design — three independent triggers, one shared writer:**

| Trigger | Mechanism | Needs a scheduler? | Role |
|---|---|---|---|
| **1. On-sync** | Hook inside the two `league_members` writers (§b), change-detect, own transaction after theirs commits | **No** | **Primary.** Active leagues get weekly-or-better resolution for free. Satisfies YR-1's contract |
| **2. Dedicated route** | `POST /api/cron/roster-snapshot`, X-Cron-Secret, 202-immediately daemon + per-tick budget | Yes | Backstop for dormant leagues. Works the moment *any* scheduler exists (GH Actions migration, or hand-provisioned dashboard cron) |
| **3. Tick guard** | A guarded slot in `hourly-tick`, calling the same shared writer when a league's current period is missing | Yes (a *different* one) | Self-heal. Free if hourly-tick fires; dead code costing nothing if it doesn't |

All three call **one** `_write_roster_snapshots(...)`, idempotent on `uq_roster_snapshot` —
the exact `_write_daily_value_snapshots` shape (`server.py:16795-16831`: one writer, two
callers, "the two callers can never duplicate rows").

**Where I still amend them.** They say *"do not fold it into `daily-tick` or `hourly-tick`"*
on the `architecture.md:230` precedent ("kept separate so a push-scan failure can't stop
history collection"). I keep trigger 3, and I think the precedent survives intact, because
they themselves note the precedent is **violated in practice today** — the *operative*
value-snapshot mechanism IS the hourly-tick guard. The precedent's intent is *"a push-scan
bug must not be able to stop retention."* That intent is satisfied by trigger 2 existing.
Trigger 3 is not retention *riding* the push tick; it is a redundant caller of a writer that
has its own dedicated route. Under a scheduler whose firing is unverified, redundancy beats
purity. Cost of being wrong: a few lines that never execute. Cost of omitting it if the
dedicated cron never gets provisioned (which is the documented history of this repo, twice):
dormant leagues silently capture nothing. See §3.1 — this is the one open disagreement, and
it is low-stakes.

**Retained from their A2, unamended:** the single-worker `--timeout 120` constraint is real;
the scheduled fan-out must use the `players-refresh` 202-immediately daemon pattern
(`server.py:16776-16793`) **plus** a stalest-first per-tick budget
(`_DRAFT_STATUS_SWEEP_BUDGET`, `server.py:16472-16480`). Both mandatory, as they said. My R1
preferred budget-rotation *over* the daemon; on a single worker with an unbounded league
count they are complements, not alternatives, and they are right.

---

### (b) Write seam — accepted, with one amendment they could not have made

**Their non-negotiable rule is correct and I endorse it without qualification.** Verified:
`replace_espn_league_members` (`database.py:10086-10116`) does `delete` + `insert` inside a
single `with engine.begin() as conn:`. A snapshot insert appended inside that block means a
snapshot bug **rolls back the delete+insert and leaves the league with zero members** — on
every ESPN/MFL/Fleaflicker import. The name is a lie (MFL and Fleaflicker both call it), so
that is three platforms, not one. Their `G-040` note (`begin_nested` silently commits on
main-engine SQLite) correctly closes the savepoint escape hatch.

**Rule, as it should appear in the PRD verbatim:** the snapshot write happens in its **own
`engine.begin()`, after the membership transaction has committed**, wrapped in
`try/except` + `log.warning("… failed (continuing): %s", e)`, matching the four sibling
capture blocks in the session-init daemon (`server.py:15286-15367`). With a test.

**The amendment — and it is the thing that decides whether their "free" claim holds.**

Their seam is right for the *write*. It cannot supply the *team key*. Both writers receive
member dicts of exactly `{user_id, username, display_name, player_ids}`
(`database.py:5545-5553`, `:10098-10108`) — **no `roster_id`, no `team_id`, no franchise
id.** And for Sleeper the callers do not have one either: `opponent_rosters` arrives from the
client as `{user_id, username, player_ids}` (`server.py:14664-14670`). So as specced, the
sync path has nothing to build a stable `team_key` from — which is (c).

Per platform, at the sync seam:

| Platform | Stable native id available at the seam? | Fix |
|---|---|---|
| **Sleeper** | **No.** Client sends no `roster_id` | **Reuse a fetch that already happens.** `trade_block_service._fetch_rosters` (`:99-115`) already fetches `roster_id → owner_id` **server-side, in the same daemon**, behind `sleeper.trade_block` (`true` in `config/features.json`). The mapping is fetched and thrown away today. Thread it through. **Zero new API calls** |
| **ESPN** | **Yes, and it is already computed** — `server.py:19171` `f"espn:{league_id}.t{team.team_id}"`, currently only the *fallback* branch of `_espn_member_id`. Promote it to always-computed, alongside the SWID-based `user_id` | Zero new calls |
| **MFL** | **Yes, already stable** — the member id *is* `f"mfl:{league_id}.f{franchise_id}"` (`server.py:21145`) | Free today |
| **Fleaflicker** | No synthetic-id helper found in `backend/server.py` | Needs one; scope it |

**What this does to their cost claim.** Their A3 says the sync hook is "one hook, four
platforms, zero platform code." That is true of the roster *payload* (all four normalise into
Sleeper player-id space before the writers — `server.py:19776`, `:21387`, `:22989`, `:15267`
— and I verified it). It is **not** true of the team key: that is four callers of plumbing
plus one Fleaflicker helper. The write is two functions; the key is threaded from four sites.
Still far better than four route hooks, so the seam choice stands — the estimate moves, not
the design.

**Residual coupling to flag.** Reusing the trade-block fetch couples Sleeper team-key
stability to `sleeper.trade_block` being on. Mitigation, in the schema: if the map is
unavailable, fall back to a `user_id`-derived key and stamp `team_key_quality='weak'`. The
recap then **declines to chart that team** rather than fragmenting it silently. Weak keys are
visible and countable; silent fragmentation is neither.

---

### (c) `team_key` — I concede the diagnosis, amend the fix, reject their key

**Concede, fully.** My `'r:<roster_id>' | 'u:<owner_user_id>'` fallback is a bug, and the
evidence is worse than they stated. `_espn_member_id` (`server.py:19168-19171`):

```python
def _espn_member_id(league_id: str, team) -> str:
    """Deterministic synthetic user_id for a non-FTF ESPN manager."""
    if team.owner_swid:
        return f"espn:{team.owner_swid}"
    return f"espn:{league_id}.t{team.team_id}"
```

**The rotating id is the primary branch; the stable id is the fallback.** So on ESPN my key
would resolve through `u:<user_id>` to a SWID-derived string almost every time, and
`database.py:7911` documents SWID rotation on re-import as a live phenomenon. Same physical
team → `espn:<swid-A>` → real FTF id on link → `espn:<swid-B>` after rotation. Three partial
charts, no error anywhere. They are right, and it is squarely my lane.

**Amend the fix — `team_key` is never polymorphic and never derived from `user_id`.** It is
always the platform-native team *slot*:

| Platform | `team_key` | Status |
|---|---|---|
| Sleeper | `sleeper:<league_id>.r<roster_id>` | needs the trade-block map (§b) |
| ESPN | `espn:<league_id>.t<team_id>` | **already computed** at `server.py:19171` — promote from fallback |
| MFL | `mfl:<league_id>.f<franchise_id>` | free — already the member id |
| Fleaflicker | `fleaflicker:<league_id>.t<team_id>` | needs a helper |

Stable across SWID rotation, across a manager linking, and across a team changing hands —
which is correct: a team that changes managers mid-season is **one team** in a season chart,
and the manager change is an attribute of a period, not a new series.

**Reject their key.** They propose `(league_id, platform_team_key, snapshot_at)`. That
reintroduces the exact defect my R1 B3 identified: `snapshot_at` is an *instant*, so it
enforces nothing — two runs in the same week produce two rows and "value at week W" has two
answers. Idempotency requires a **bucket label**, which is why `uq_value_snapshot` keys on
`"YYYY-MM-DD"` and not a timestamp (`database.py:1003-1005`), and why
`deck_replenish_log.iso_week` keys on `"2026-W30"` (`database.py:586-591`). Their diagnosis,
my mechanism.

**Final key: `UNIQUE (league_id, team_key, scoring_format, period_key)`.**

**Accepted in full: `owner_user_id` is a nullable, re-stampable attribute, never part of the
key.** Answering their open question 2 — **re-stamp the history rows; do not build a mapping
table.** The reconciliation hook already exists: `leagues.espn_my_team_id` (Integer, *"the
linking user's ESPN team id (binding)"*, `database.py:262`) and `leagues.platform_my_team`
(String, `:273`). At link time you know the joining user's native team id → construct
`team_key` → one indexed `UPDATE league_roster_history SET owner_user_id = ? WHERE league_id
= ? AND team_key = ?`. Idempotent, no new table, no second thing to keep in sync.

This makes their B3 fix concrete: **§5.3's late-joiner growth claim becomes true on ESPN and
MFL too**, via that UPDATE. Without it, it is Sleeper-only exactly as they said.

**On "append-only" vs. re-stamping.** Mutating `owner_user_id` does not violate the ADR's
append-only headline. The historical *fact* is "team T held roster R in period P" — that
never changes. `owner_user_id` is a late-resolving pointer to who we now know was behind team
T. Worth stating explicitly in the ADR, because "append-only" plus "we UPDATE a column" reads
like a contradiction to the next reader.

---

### (d) C5/C6 storage — I hold `league_board_history`

**Their documentation catch is valid; their "third lineage" inference is category-confused.**

What `wrapped_events` actually is, verified: an **event stream** of seven types
(`swipe | trade_match | trade_accepted | trade_declined | tier_save | ranking_reorder |
league_sync`), FROZEN at the analytics P0 cutover with **zero writers** and an explicit *"Do
not add writers"* (`database.py:1026-1046`), read by `load_league_activity` to render a
human-readable **activity feed** (`database.py:6022-6071`). It stores **no rosters, no Elo
values, no team values.**

So the correct count is:

- **One behavioral-event lineage**, split at a cutover: `wrapped_events` (< cutover) ∪
  `user_events` (≥ cutover), with the union-read already implemented.
- **A state-snapshot family**: `player_value_history`, `elo_history` — and now
  `league_roster_history`, `league_board_history`.

Adding a state-snapshot table does not create a third *event* lineage. It extends the family
`player_value_history` established, which is precisely what the plan intends and precisely
what `database.py:986-991` says that table exists for ("*so value-history charts, the movers
digest (#33), and Wrapped (#46) have history to draw on*").

**What I accept from them:** §2 "what is banked" omits `wrapped_events` and should list it;
and P3's behavioral stats **will** cross the cutover seam mid-2026. Both belong in the ADR
consequences. Answering their open question 3: this does **not** change my taxonomy
recommendation, and yes — the recap should read behavioral history through **one accessor
that hides the cutover**, but that accessor already exists in shape
(`load_league_activity`), so P3 extends that pattern rather than inventing a union view.

**Answering their open question 4 (is C6 just `elo_history` + a cadence backstop?).** No, and
the numbers are decisive:

1. `elo_history` writes **only players whose Elo changed** in a submission
   (`database.py:965-966`). It structurally cannot rebuild a *complete* board at date D
   without folding forward from row one — and a lost submit corrupts every later fold.
2. It has **no uniqueness constraint of any kind** (`:971-979`), so their proposed weekly
   append is not idempotent: a double run silently doubles every board.
3. Volume: row-per-player weekly at 100 leagues × 3 FTF users × ~270 players × 20 weeks =
   **1.6M rows**; 16M at 1,000 leagues. JSON-per-board is **6,000 rows** at 100 leagues.
   A **270× row factor.**

Their "one fewer table" instinct is right in general and wrong here by that factor.
`elo_history` stays exactly as it is — the event-driven "what moved when" log.
`league_board_history` answers the different question "what was the whole board on date D."
Different grain, different question, not a fork. **C5 and C6 remain one build item.**

---

### (e) `league_state.py` — accepted, with a scope limit

**They found the right seam and I should sit on it.** Verified: `LeagueStateProvider` is a
`runtime_checkable` Protocol; `LEAGUE_STATE_PROVIDERS` maps `sleeper|mfl|fleaflicker|espn` →
factories with Sleeper implemented and three `_NotImplementedLeagueState` stubs that raise
(`league_state.py:294-332`); `TeamState` carries `roster_id: int` as its **first field**, plus
`user_id`, `username`, `player_ids`, `starters` (`:60-80`); bench split via
`_BENCH_SLOTS = {"BN","IR","TAXI"}` (`:57`). The Sleeper provider already calls
`GET /league/{id}/rosters`.

That solves three of my problems at once on the fetch path: **`roster_id` natively** (so
`team_key` needs no plumbing there), `starters` for free, and the registered-stub design keeps
the ESPN gap *explicit* rather than silently empty.

**Scope limit — the sync writer must NOT go through it.** At the sync seam the roster payload
is already in hand in Sleeper-id space; routing it through a Protocol whose only
implementation makes 3–4 HTTP calls converts a free write into a fetch. **`LeagueStateProvider`
is the fetch path (trigger 2/3) only; trigger 1 writes directly.**

**One thing they missed that makes this better.** `LeagueState` carries `completed_weeks` and
`status` (`league_state.py:98-107`, `:112-114`). That gives the scheduled job a free, correct
answer to *"is this league in-season?"* — and therefore whether a missing week is an alarming
gap or a legitimate off-season no-op. Wire it: it is the difference between a monitoring
signal and monitoring noise, and it is already computed.

**One caution.** The outlook pipeline is a *read* pipeline for #169 with its own caching
(`_outlook_sleeper_fetch`, completed weeks never refetch). Retention riding it inherits those
cache semantics. Harmless for `/rosters` (never cached) — worth a note so nobody later adds
roster caching there and silently freezes the snapshot.

---

### (f) K/DEF coverage — carried, with the mitigation

They did not address it. Carrying it, and it answers their open question 6 in the affirmative.

**Root cause (structural, not a bug).** `_write_daily_value_snapshots` iterates `pool["seed"]`
— the DP-seeded universal pool, skill positions only (`server.py:16810-16828`). Meanwhile
`league_members` deliberately stores *"the RAW client-sent ids"* including off-pool players
(#151, `server.py:15258-15265`). So kickers, defenses and deep-bench camp bodies have **no
`player_value_history` row, ever.**

**Mitigation — three columns and one rendering rule:**

| Field | Meaning |
|---|---|
| `player_count` | every id on the roster |
| `valued_player_count` | ids that resolved to a `player_value_history` row at `value_basis_date` |
| `value_basis_date` | the pvh `snapshot_date` actually used — nearest ≤ target, the `load_value_snapshot_baseline` idiom (`database.py:9425`) |

- **`team_value` is `NULL`, never `0`, when nothing prices.** A zero renders as a roster wipe
  and is indistinguishable from a real one. A NULL renders as a gap.
- **Rendering rule (ADR consequence):** the season chart greys any week where
  `team_value IS NULL` **or** `valued_player_count < 0.8 × player_count`, and **never
  interpolates.**

**Answering their open question 6 directly:** yes — and this *is* the `values_complete`
marker they intuited, expressed as two integers and a date rather than a boolean, so the
December chart can grey out unjoinable weeks with a reason instead of a flag. If §4's check
shows `player_value_history` has gaps, this is exactly the machinery that lets the recap
render honestly rather than lie or refuse to ship.

---

### (g) Flagging — agreed, with one addition

**Their D-P1-07 reading is correct and I verified it.** `DECISIONS-p1.md:139-145`: the
disqualifying property is that `growth.share_landing` gates **server routes that
already-shared external links point at**, so flipping it off *"would break every link already
shared."* **External references to a gated read surface** — not flags in general. A capture
flag gates a write with no external references.

Agreed: **`market.roster_history`, default ON at merge**, matching the three sibling capture
flags in the same daemon (`market.trade_capture: true`, `sleeper.trade_block: true`,
`picks.owned_sync: true` — all verified in `config/features.json`). Capture that ships dark is
capture that did not happen, and the whole urgency argument is about days. Their "one flag,
one direction — P3's read routes get their own" rule is exactly right.

**My addition:** the flag must gate the **write at the call site** (mirroring
`server.py:15292` / `:15318` / `:15363`), **not** the table's creation. `metadata.create_all`
must still create the table when the flag is off, so flipping it on mid-season is a behaviour
change and not a schema surprise on a live single-worker instance.

Noting their honest caveat: NEXT.md 0c records that a malformed `FTF_FLAGS` currently fails
*silently* to `{}`. That is a pre-existing sharp edge on the kill switch this design leans on.
Operator should know; not a blocker.

---

### (h) Pick ownership (C3) — fold-in survives, with an ordering constraint

They did not rule on it. It survives their seam analysis, with one change neither R1 caught.

**It survives** because `pick_ids` rides the roster row at identical grain (league, team,
period), `pick_id` is already self-describing
(`"{league_id}_{season}_{round}_{original_roster_id}"`, `database.py:731-733`), and the
marginal row cost is zero.

**The change — ordering.** Their seam is the `league_members` writers; `draft_picks` is
written by a **different** block in the same daemon (owned-pick sync, `server.py:15300-15343`).
So a roster snapshot that reads `draft_picks` at write time is reading a table a sibling block
is concurrently writing. Daemon order today: trade-block (`:15286`) → owned-picks (`:15300`) →
trade-capture (`:15355`). **The snapshot block must be appended LAST**, after owned-picks has
settled `draft_picks` for that league. Otherwise the pick half of the snapshot races the sync
that populates it, and the failure is a quietly short `pick_ids` array — invisible until
December.

**Their B7 folds in as a rendering rule.** `pick_source ∈ {'platform','user','mixed'}`; where
`'user'`, the recap must **not** render "what your first became" as fact. ADR-010's contested
and orphaned states (`database.py:7902-7920`) mean some ESPN assertions are mutually
contradictory by design.

**Their A6.3 gives C3's deferral a recorded reason.** `origin/closeout-mock-draft` and
`origin/mock-draft-fix` are actively moving `draft_picks`. C3 stays in P1 — which the plan
already schedules correctly, now for a stated reason so nobody pulls it forward. **C1/C2
(rosters) are unaffected** and can proceed now: nothing unmerged touches
`upsert_league_members` or `replace_espn_league_members`.

---

## 3. STILL DISPUTED

**3.1 May the backstop live in an existing tick?** *(low stakes; operator call)*
- **Them:** no. `architecture.md:230`'s precedent — retention must not ride the push tick.
  Dedicated `POST /api/cron/roster-snapshot` only, gated on the cron migration merging.
- **Me:** dedicated route **and** an `hourly-tick` guard, both calling one shared writer.
  The precedent's *intent* ("a push-scan bug must not stop retention") is satisfied by the
  dedicated route existing. They themselves note the precedent is violated in practice today
  and the hourly guard IS the operative value-snapshot mechanism. This repo's documented
  history is that dedicated crons get reverted or never provisioned — twice. Redundancy beats
  purity while the scheduler question is open.
- **Stakes:** if the GH Actions migration lands and fires, my guard is a few never-executed
  lines. If it does not, their design captures nothing for dormant leagues. Asymmetric, which
  is why I hold it — but I would not block on it.

**3.2 Is the sync-driven capture "free"?** *(minor; a conditional on their headline claim)*
- **Them:** yes — payload in hand, a hash and a conditional insert.
- **Me:** yes for the roster *payload*, verified. **No** for the *team key*: Sleeper needs the
  `roster_id → owner_id` map, which is free **only** by reusing `trade_block_service._fetch_rosters`
  and **only while** `sleeper.trade_block` is on. Plus four callers of plumbing and a
  Fleaflicker helper. Conditional, not unconditional.

**3.3 P0a costing.** *(not a design dispute)*
- **Them:** ~1 week for the sync half.
- **Me:** 1.5–2 weeks, adding team-key threading at four callers, the trade-block map reuse,
  the ESPN `team_id` promotion, the daemon ordering constraint, and the coverage columns.
  Flagging for `pm-technical`'s estimate, not for resolution here.

**3.4 "No working scheduler in production."** Resolved by the coordinator, not by us — three
cron services are declared; firing is open. Neither reviewer's design now depends on the
answer. Both defer to §4.

---

## 4. The single check that settles the open question

**The design does not branch on the answer.** Only the urgency of merging
`origin/infra/render-cron-migration` does. That is the point of the three-trigger structure
in (a).

**Primary check — one query against prod:**

```sql
SELECT snapshot_date, count(*)
FROM   player_value_history
GROUP  BY 1 ORDER BY 1 DESC LIMIT 40;
```

`player_value_history` has exactly two writers — `POST /api/cron/value-snapshot` and the
`hourly-tick` fallback guard (`server.py:16446-16460`). Neither runs at boot or on any user
path. **So this table is a clean scheduler oracle.**

| Result | Meaning | Consequence |
|---|---|---|
| Contiguous daily rows since 2026-07-26, ~1,369/day | `hourly-tick` fires | Scheduler works. Trigger 3 is a real backstop; the cron migration is a hygiene item, not a blocker. Recap chart is fully joinable |
| Sparse or absent after 2026-07-26 | The ticks do not fire | **Trigger 1 is the only live capture mechanism.** The cron migration becomes P0 item zero, as the architect argues. And `team_value` will have unjoinable weeks — §(f)'s `valued_player_count` / `value_basis_date` / grey-don't-interpolate machinery becomes load-bearing, not defensive |

**Sandbox-safe fallback, if the prod DB stays blocked** (neither R1 proposed this):
`GET /api/rankings` renders consensus positional-rank **trend glyphs** computed from
`load_value_snapshot_baseline(..., days=30)` — the oldest prior-day snapshot in the trailing
30 days (`server.py:1998`; `analytics_queries.py:1375` notes "run the value-snapshot cron
before comparing"). **If trend arrows render in prod, `player_value_history` holds ≥2 distinct
dates within 30 days, so the scheduler fires.** No DB access, no new endpoint. It is a weaker
signal than the query — it proves *some* cadence, not daily completeness — but it converts an
"operator must run a blocked query" into an "operator opens the app."

---

## 5. Final DDL

Incorporating everything above. Follows `player_value_history_table`
(`database.py:995-1006`) as the precedent.

```python
# ---------------------------------------------------------------------------
# league_roster_history — append-only league-state snapshots (#46 Wrapped)
# ---------------------------------------------------------------------------
# ADR-011. player_value_history logs the MARKET side daily; this logs the
# OWNERSHIP side. A team's value is roster x values — this is the half that
# league_members.roster_data (:327) was overwriting on every sync.
#
# WRITTEN FROM: (1) inside the two league_members writers, in its OWN
# transaction AFTER theirs commits — NEVER inside replace_espn_league_members'
# engine.begin() block (:10110-10116), where a snapshot failure would roll back
# the delete+insert and leave the league with ZERO members. G-040 rules out
# begin_nested as a middle ground. (2) POST /api/cron/roster-snapshot.
# (3) An hourly-tick guard. All three call one idempotent writer.
#
# team_key is the platform-native TEAM SLOT, never derived from user_id:
# ESPN's synthetic member id is SWID-first (server.py:19168-19171) and SWID
# rotates on re-import (:7911), so a user_id-derived key splits one team's
# season into several partial charts with no error anywhere. owner_user_id is
# a nullable, RE-STAMPABLE attribute — resolved forward via leagues.
# espn_my_team_id / platform_my_team when a manager later links. That re-stamp
# is not a violation of append-only: the fact ("team T held roster R in period
# P") never changes; only our knowledge of who was behind T does.
#
# team_value is denormalised alongside the roster ids for the reason
# player_value_history denormalises consensus_value (:1001): a later model
# change must not rewrite the shape of a season chart already shown to a user.
# ---------------------------------------------------------------------------

league_roster_history_table = Table("league_roster_history", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("league_id",          String,  nullable=False),
    # 'sleeper:<lid>.r<roster_id>' | 'espn:<lid>.t<team_id>'
    # | 'mfl:<lid>.f<franchise_id>' | 'fleaflicker:<lid>.t<team_id>'
    Column("team_key",           String,  nullable=False),
    # 'strong' = platform-native slot id. 'weak' = user_id-derived fallback
    # (Sleeper with sleeper.trade_block off). The recap DECLINES to chart weak
    # teams rather than fragmenting them silently. Weak keys are countable.
    Column("team_key_quality",   String,  nullable=False),   # 'strong'|'weak'
    Column("platform",           String,  nullable=False),   # sleeper|espn|mfl|fleaflicker
    Column("owner_user_id",      String),   # NULLABLE ATTRIBUTE, never a key
    Column("scoring_format",     String,  nullable=False),   # '1qb_ppr'|'sf_tep'
    # BUCKET LABEL, not an instant. '2026-W33' from now.isocalendar(), the
    # deck_replenish_log.iso_week shape (:586, server.py:16244). Uses the ISO
    # week-numbering YEAR, never .year: 2026-12-31 is 2027-W01 and a %Y key
    # would sort and dedupe wrong at the boundary. An instant in the key (the
    # plan's snapshot_at sketch) enforces NOTHING — two runs, two rows.
    Column("period_key",         String,  nullable=False),
    Column("period_kind",        String,  nullable=False),   # 'week' today; 'day' later
    Column("snapshot_date",      String,  nullable=False),   # 'YYYY-MM-DD' — the pvh join key
    Column("snapshot_at",        String,  nullable=False),   # ISO UTC instant of the write
    Column("player_ids",         Text,    nullable=False),   # JSON array, SORTED
    Column("starter_ids",        Text),                      # from TeamState.starters
    Column("pick_ids",           Text),                      # JSON array of draft_picks.pick_id
    Column("pick_source",        String),   # 'platform'|'user'|'mixed' — ADR-010.
                                            # 'user' => recap must NOT render pick
                                            # flow as fact (ESPN assertions can be
                                            # contested/orphaned, :7902-7920)
    # sha256(",".join(sorted(str(p) for p in player_ids))).hexdigest()[:16].
    # SORTED = set semantics. NEVER suppresses the weekly write: team_value
    # moves weekly even when the roster does not, and a sparse series puts
    # holes in the exact chart YR-2 exists to stabilise. It populates
    # changed_from_prev and suppresses EXTRA intra-week on-sync writes.
    Column("roster_hash",        String,  nullable=False),
    Column("changed_from_prev",  Integer),                   # 0|1|NULL(first)
    Column("player_count",       Integer, nullable=False),
    # Of player_count, how many resolved to a player_value_history row. The
    # universal pool is DP-seeded skill positions only (server.py:16810-16828)
    # while league_members stores RAW client ids including K/DEF (#151,
    # server.py:15258-15265), so a roster is never fully priced.
    Column("valued_player_count",Integer, nullable=False),
    # NULL, never 0, when nothing prices — a zero renders as a roster wipe and
    # is indistinguishable from a real one. Chart greys any week where this is
    # NULL or valued_player_count < 0.8 * player_count. NEVER interpolates.
    Column("team_value",         Float),
    Column("team_value_picks",   Float),   # SEPARATE: draft_picks.pool_value is a
                                           # different pipeline than player consensus
    Column("value_basis_date",   String),  # the pvh snapshot_date actually used
                                           # (nearest <= target, the
                                           # load_value_snapshot_baseline idiom :9425)
    Column("in_season",          Integer), # from LeagueState.completed_weeks/status —
                                           # distinguishes an alarming gap from an
                                           # off-season no-op
    Column("source",             String,  nullable=False),  # 'sync'|'cron'|'backfill'
                                           # the rollback lever: DELETE ... WHERE
                                           # source='sync' AND snapshot_at > '<deploy>'
    UniqueConstraint("league_id", "team_key", "scoring_format", "period_key",
                     name="uq_roster_snapshot"),
)

Index("ix_lrh_team_period",   league_roster_history_table.c.league_id,
                              league_roster_history_table.c.team_key,
                              league_roster_history_table.c.period_key)
Index("ix_lrh_league_period", league_roster_history_table.c.league_id,
                              league_roster_history_table.c.period_key)
Index("ix_lrh_owner_period",  league_roster_history_table.c.owner_user_id,
                              league_roster_history_table.c.period_key)


# ---------------------------------------------------------------------------
# league_board_history — weekly COMPLETE board snapshots (C5 + C6, YR-3)
# ---------------------------------------------------------------------------
# NOT a fork of elo_history (:971), which stays exactly as it is: the
# event-driven "what moved when" log. It writes only players whose Elo CHANGED
# (:965-966), so it cannot rebuild a complete board at date D; it has no
# uniqueness constraint, so a weekly append to it is not idempotent; and
# row-per-player weekly is 1.6M rows at 100 leagues vs 6,000 here (270x).
# Different grain, different question.
#
# NOT related to wrapped_events (:1040), which is a FROZEN behavioural EVENT
# stream feeding load_league_activity (:6022-6071) and stores no valuations.
#
# YR-3 permits in-app, authenticated, league-context display of one manager's
# valuations to another. Every read accessor takes league_id AND a caller
# identity and asserts league membership, as load_member_rankings does. There
# is no public-URL read path — that is the half of D-P1-12 still standing, and
# growth.tier_board_share stays false.
# ---------------------------------------------------------------------------

league_board_history_table = Table("league_board_history", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("user_id",          String,  nullable=False),
    Column("league_id",        String,  nullable=False),
    Column("scoring_format",   String,  nullable=False),
    Column("period_key",       String,  nullable=False),   # '2026-W33'
    Column("snapshot_date",    String,  nullable=False),   # 'YYYY-MM-DD'
    Column("snapshot_at",      String,  nullable=False),   # ISO UTC
    Column("elos",             Text,    nullable=False),   # JSON {player_id: round(elo,1)}
    Column("player_count",     Integer, nullable=False),
    # member_rankings.updated_at at capture. Distinguishes "re-ranked this
    # week" from "we re-snapshotted an unchanged board" — without it, one
    # observation repeated five times reads as five observations, and
    # "Your calls" is built on exactly that distinction.
    Column("board_updated_at", String),
    Column("source",           String,  nullable=False),   # 'sync'|'cron'|'backfill'
    UniqueConstraint("user_id", "league_id", "scoring_format", "period_key",
                     name="uq_board_snapshot"),
)
Index("ix_lbh_league_period", league_board_history_table.c.league_id,
                              league_board_history_table.c.period_key)
Index("ix_lbh_user_period",   league_board_history_table.c.user_id,
                              league_board_history_table.c.period_key)
```

**Plus one index on an existing table**, added to the idempotent
`CREATE INDEX IF NOT EXISTS` list in `_migrate_db` (`database.py:2160-2185`):

```python
("ix_pvh_format_date", "player_value_history", "scoring_format, snapshot_date")
```

`player_value_history` has exactly one index today — the `uq_value_snapshot` constraint,
which leads with `player_id`. The league-wide recap query
(`WHERE scoring_format = ? AND snapshot_date IN (...)`) has no leading-column match and
full-scans a table projected at ~0.5M rows/yr (`data-dictionary.md:659`). Free now.

**Volume under the corrected key** (answering their open question 1): the key change from
`(league_id, user_id)` to `(league_id, team_key)` **does not move the row estimates** — it is
the same grain, one row per team per week, just keyed on a stable identifier. It *removes*
rows that the old key would have double-counted through identity churn. And no, the hash does
not cut the 240/league-season figure: the grid is deliberately **dense** (§1.9), so every
weekly slot writes regardless of churn. Totals stand: ~240 rows / ~240 KB per league-season;
~47 MB combined at 100 leagues; ~470 MB at 1,000, which is where a retention policy is needed
on `basic-256mb`.

**Answering their open question 5** (`team_value` and format): `scoring_format` **in the key**,
as they lean toward, and it does **not** double the rows today — exactly one format is written
per league (`leagues.default_scoring`, `:253`). It costs nothing now and makes a later
"recompute this season under SF" an insert rather than a migration.

---

### Doc-sync — merged from both reviews

Their table, plus my additions (marked †):

| Doc | Why |
|---|---|
| `docs/architecture.md:230` | **Correct the drift now** — claims a `render.yaml` cron that does not exist; contradicts `runbook.md:295` |
| `docs/architecture.md` § Cron ticks | New `/api/cron/roster-snapshot` row |
| `docs/data-dictionary.md` | Two new tables + `ix_pvh_format_date` (`backend/database.py` schema trigger) |
| `docs/api-reference.md` | New cron route; `GET /api/wrapped/<season>` at P3 |
| `docs/config-reference.md` | `market.roster_history` flag |
| `docs/adr/adr-011-league-state-history-is-append-only.md` | Per their A4, plus: the re-stamp-is-not-a-mutation note (c), the coverage rendering rule (f), the cutover-seam note (d) |
| `living-memory/HLD.md` / `LLD.md` | Append-only league state is a convention shift |
| `living-memory/DECISIONS.md` | The (a) inversion — a deviation from the plan's reading of YR-1, needs the operator's eye |
| † `docs/business/analytics/2026-1X-XX-wrapped-addendum.md` | The nine recap events, before any emitter — `analytics_taxonomy.py:16-18` requires the addendum first |
| † `backend/database.py:1060-1066` + `docs/data-dictionary.md:727` | `user_events` taxonomy comment, when the recap events register |
| † `docs/runbook.md` | Roster-snapshot monitoring, mirroring the value-snapshot paragraph at `:295` |
| `docs/cross-client-invariants.md` | **n/a** — server-only in P0 |
| `mobile/.maestro/` | **n/a** in P0; **required** at P3 |
| `docs/templates/feature-scope.md` | Required — schema + data collection, explicitly not express-lane eligible |

---

## Round 3 — final

> Written after reading `architect-r2.md`. Their R2 moved a long way; three items left.
> **Closing without re-argument, per the coordinator:** their **D2** (on-sync writer status) —
> my R2 already makes on-sync **co-primary**, not the YR-1 "free addition". We agree. Closed.
> Their **(d)** — they withdrew the `wrapped_events` objection entirely and adopted
> `league_board_history` as specced, including `board_updated_at`. Their read-path catch (the
> recap crosses the `wrapped_events` → `user_events` cutover) is correct and goes in the ADR as
> a P3 consequence. Accepted. Closed.
>
> Also adopting from their R2 without argument, because they are right and I verified them:
> **§5.1** — `team_value` must be `compute_power_rankings`'s consensus-basis total, or the
> Wrapped chart and the Power Rankings screen show different numbers for the same team; and its
> `_fill_starter_slots` / `LINEUP_SLOT_ELIGIBILITY` derivation is a better `starter_ids` than
> either the platform's `starters[]` or my `_BENCH_SLOTS` suggestion. **§4 step 8** — the
> precedence rule (`source='weekly'` outranks `source='sync'`; on-sync does `DO NOTHING` when a
> weekly row exists) is a genuine correction to my last-write-wins spec: a Friday app-open
> posts client data that **drops ownerless rosters**, so recency would silently delete that
> week's orphan teams and break YR-6 invisibly. Adopted. **§5.2** — `league_members` discarding
> a stable native team id at all four write sites is the root cause; noting it in the ADR.

### R3-1. Backstop location — **resolved; one answer. I drop the hourly guard.**

**Their R1 objection is already withdrawn by their own R2.** They now put Writer B *inside
`daily-tick`* (§2a: *"I withdraw 'new dedicated cron, gated on the migration merging'"*). That
is my mechanism, and it also settles the precedent question against their R1 position: the
`architecture.md` precedent is "keep retention off the push-scan tick," and `daily-tick` **is**
the push-scan tick (the re-engagement scan). They cannot hold "never in a tick" while shipping
Writer B in one, and to their credit they did not try to.

**Where I was wrong, and I concede it cleanly.** My R2 argued for an `hourly-tick` guard *on
top of* the daily gate, on redundancy grounds — "a different scheduler." **That premise is
false.** `notif-hourly-tick` and `notif-daily-tick` are both `type: cron` services in the *same*
`render.yaml` blueprint, provisioned by the *same* mechanism. They are perfectly correlated: if
`daily-tick` does not fire, `hourly-tick` does not either. The guard buys **zero** additional
failure coverage. **Dropped.**

**Final answer — two writers, three callers, no hourly guard:**

| | Mechanism | Depends on a scheduler? |
|---|---|---|
| **Writer A** | On-sync, at both `league_members` writers, own transaction after theirs commits | **No** |
| **Writer B** | `_write_weekly_roster_snapshots(now)`, shared | — |
| ↳ caller 1 | `daily-tick` weekday gate (`>=`, `FTF_ROSTER_SNAPSHOT_WEEKDAY`, default 1) | Yes |
| ↳ caller 2 | `POST /api/cron/roster-snapshot`, `X-Cron-Secret` | No — **manual/external entry point** |

**Keep the dedicated route, reframed.** It is not a third scheduled trigger — nothing schedules
it. It is ~6 lines (`_require_cron_auth()` → shared writer → `jsonify`) and it buys three things
the gate cannot: the operator can force a snapshot **by hand** the week something goes wrong;
when `infra/render-cron-migration` lands it is a one-line workflow addition rather than a code
change; and it is the retention path that exists independently of the push tick, which is what
the `architecture.md:230` precedent is actually asking for. Their R1 wanted this route; their R2
dropped it along with the gating. I am keeping it, and I do not think they will object now that
it is decoupled from the migration.

**The retirement rule the coordinator asked for — and it needs no new instrument.** Their §0
liveness read is exactly it:

```sql
SELECT source, count(*) FROM league_roster_history GROUP BY 1;
```

| Reading, one week after ship | Action |
|---|---|
| `'weekly'` rows present, covering ≥95% of leagues synced in the window, **two consecutive weeks** | Scheduled path **proven live**. The question is retired. Nothing to remove — there is no redundancy left to retire, only the manual route, which is 6 lines and stays as an operator lever |
| Zero `'weekly'` rows after one week | `daily-tick` does not fire. Escalate `infra/render-cron-migration`; the dedicated route is the operator's manual weekly lever until it merges. Writer A keeps capturing throughout |
| `'weekly'` present but <95% coverage | The sweep budget is too small or the daemon is dying. Raise the budget (see R3-2) |

This survives the §4 check coming back either way, because **no trigger is removed under either
answer.** The check changes the *urgency of the infra merge*, never the build. That was the
coordinator's requirement and it is met.

### R3-2. Daemon thread — **resolved as a decision rule. Their default ships; the measurement sets the budget, not the thread.**

**I concede the analysis.** My R2 said "prefer bounded rotation over the daemon." That conflated
two orthogonal properties, exactly as they say: **rotation bounds completeness; only the thread
protects availability.** With `--workers 1` and a sync worker class, a bounded sweep still blocks
the only worker for its whole duration. Bounding the work does not unblock the worker. Ship
**both** — they are complements, and both patterns are already inside the handler this code will
live in (`_refresh_players_cache_async` daemon, `server.py:16717-16731`;
`_DRAFT_STATUS_SWEEP_BUDGET` rotation, `:16472-16480`).

**The decision rule, so nobody waits on a measurement:**

1. **P0 default: the daemon ships, unconditionally, un-measured.** The choice is asymmetric.
   Cost of a thread that turns out to be unnecessary: ~4 lines and a `started` boolean in the
   response. Cost of omitting one that turns out to be necessary: total app unavailability on a
   free-tier single worker, discovered in production, in December. Take the cheap insurance.
   **This is not a measurement-dependent decision and should not be framed as one.**
2. **What the measurement actually decides: the budget, not the thread.** Time `_fetch_league_rosters`
   — a public, unauthenticated `GET /v1/league/<id>/rosters`. **This does not need prod and does
   not need the sandbox:** it is one `curl -w '%{time_total}'` against any real league id from
   the operator's machine or any dev box. Take p95 over ~20 calls. Set
   `budget = floor(60s / p95)` so a full sweep stays inside a minute of background work, then
   cap it at 50 to match the draft-status precedent.
3. **Where it starts to mattering, in numbers** (serial, at an assumed p95 of ~0.5 s/league):

| Leagues | Serial sweep | Verdict |
|---|---|---|
| ~10 (FTF today — 7 in the dev DB) | ~5 s | Academic. This is why the thread is free to add now |
| ~20 | ~10 s | Starts to matter |
| ~50 | ~25 s | Unacceptable inline — their number, and they are right |
| ~240 | ~120 s | **Hard kill** — gunicorn `--timeout 120` reaps the worker |

The point of the table is the last row: the inline design does not degrade, it **crashes**, and
it crashes at a league count this product would consider a success. Ship the thread while it
costs four lines.

**Net: their default, my framing.** We are not disputing this; I withdraw my preference.

### R3-3. ESPN contested picks — **decided. Neither skip-silently nor coin-flip: skip *and count*.**

They deferred to me. Their instinct — never record a coin-flip — is right, and it is also
already the **default behaviour**, which neither of us noticed: `contested_pick_ids(league_id)`
and `orphaned_pick_ids(league_id)` exist (`database.py:7982-7990`, memoized), and
`load_draft_picks` **already applies the exclusion per-row**. So a snapshot reading
`load_draft_picks` skips contested slots for free, with no new logic.

That makes the real decision narrower than posed: **not whether to skip, but whether to record
what was skipped.** Record it.

**Silently skipping is the same defect we already rejected twice in this review** — it is
`team_value = 0` for an unpriced roster, and it is a roster snapshot with no
`valued_player_count`. In all three cases an *absence* is rendered as a *fact*. An ESPN league
with heavy pick contestation would produce a December recap that states, confidently, "you had
no picks all season." That is a false claim the product makes on its own initiative.

**Decision — one nullable column and one rendering rule:**

| Field | Contents |
|---|---|
| `pick_ids` | **Uncontested, unorphaned** picks only — what `load_draft_picks` already returns. Never a coin-flip |
| `pick_ids_excluded` | JSON array of `pick_id`s excluded at snapshot time — the union of `contested_pick_ids` ∩ this team's assertions and `orphaned_pick_ids`. The honest record: *"these were claimed; we do not know by whom"* |
| `pick_source` | `'platform' \| 'user' \| 'mixed'` — as already specced |

`team_value_picks` sums **`pick_ids` only**, so no contested asset ever reaches the chart.

**Rendering rule (ADR consequence):** for any league where a snapshot carries a non-empty
`pick_ids_excluded`, the recap **suppresses the pick-flow section entirely for that league** —
it does not render it partially. Pick flow is a narrative ("what your first became"), and a
narrative with silent holes is worse than no narrative. A one-line "3 picks were contested in
this league, so pick flow is not scored" is fine; a confident wrong story is not.

Cost: one nullable `Text` column, zero extra rows, zero new computation. It is the cheapest way
to make an ESPN-specific data gap *countable* rather than invisible — and countable is what lets
someone in November decide whether ESPN pick flow is worth building at all.

### Where we stand

**No open disagreements.** R3-1 lands on one design (I dropped the hourly guard on a false-
independence concession; they dropped the never-in-a-tick objection in their own R2). R3-2 I
withdraw in favour of their default, with the measurement re-scoped from the thread to the
budget. R3-3 was theirs to hand me and I have decided it — one column beyond their proposal, in
the same direction they were pointing.

Two items are explicitly **not ours** and are excluded here per the coordinator: their D3
(§7's platform-agnostic wording) is an operator call; the P0a costing range (1 wk vs 1.5–2 wk)
goes to `pm-technical`.

**Two DDL amendments** fall out of the above, against §5's final DDL:

```python
    # R3-3. Contested/orphaned pick slots excluded from pick_ids at snapshot
    # time (database.contested_pick_ids / orphaned_pick_ids, :7982-7990 —
    # load_draft_picks already excludes them per-row). Recorded so an ESPN
    # league with contested assertions is DISTINGUISHABLE from one that owned
    # no picks. Non-empty => the recap suppresses pick flow for this league
    # rather than rendering it partially.
    Column("pick_ids_excluded",  Text),

    # R3-1 / architect R2 §4 step 8. PRECEDENCE, not recency: 'weekly' (server-
    # fetched, every team) outranks 'sync' (client-posted, drops ownerless
    # rosters). The on-sync writer does DO NOTHING when a 'weekly' row already
    # holds this period_key; the weekly writer does a full DO UPDATE. Recency
    # here would silently delete the week's orphan teams and break YR-6.
    Column("source",             String,  nullable=False),  # 'sync'|'weekly'|'backfill'
```

and `team_value` is now defined as **`compute_power_rankings`'s consensus-basis team total**
(architect R2 §5.1), not a fresh summation — with out-of-pool players contributing `0.0` per
that module's existing, written-down reasoning, and `valued_player_count` recording the coverage
so the gap stays legible.
