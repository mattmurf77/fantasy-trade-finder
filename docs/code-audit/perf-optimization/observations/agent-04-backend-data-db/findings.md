# Agent 04 — Backend Data Layer + DB + Services — Performance Findings

## Scope & method

**Scope (per brief):** `backend/database.py` (SQLAlchemy Core schema, helpers,
indexes), `backend/ranking_service.py`, `backend/trade_service.py`,
`backend/trends_service.py`, and the in-memory player cache (which lives in
`backend/server.py` — `_load_sleeper_cache`, `_ensure_universal_pools`,
`build_universal_pool`). Focus: what makes player + trade data slow to
**produce** on the backend.

**Method:**
- Static read of every in-scope file end-to-end, plus the hot call sites in
  `backend/server.py` (`session_init` at `server.py:4431`, the extension auth
  path at `server.py:6141`, demo at `server.py:6789`, and the trade-generation
  worker at `server.py:2691`) to see how the data-layer functions are invoked
  per request.
- Enumerated every declared `Index(...)` and every `CREATE INDEX IF NOT EXISTS`
  in `_migrate_db()` (`database.py:183–731`) and cross-checked each against the
  WHERE/ORDER BY columns of the hot readers.
- Read-only timed `curl` against the live Render backend
  (`https://fantasy-trade-finder.onrender.com`) to establish the warm baseline:
  - `/api/tier-config` → HTTP 200, **0.217 s**, 1440 B
  - `/api/session/ping` → HTTP 401, **0.261 s**, 13 B
  - (`/api/health` is 404 — no such route.)
  These confirm the dyno was **warm** at audit time; the cold-start figures
  below are reasoned from code, not measured (Confidence set accordingly). I
  did not exercise authed POST paths (`/api/session/init`, `/api/trades/*`) —
  the brief forbids mutating requests, and those require a real Sleeper session.

**Evidence-type legend:** most findings are `static-analysis` (clear code path
+ known anti-pattern with file:line). Cold-start magnitudes are `hypothesis`
where I could not measure the cold dyno.

**Index landscape (baseline for several findings).** Declared/created indexes:
`trade_matches(user_a_id,league_id)`, `trade_matches(user_b_id,league_id)`,
`app_feedback(created_at)`, `app_feedback(user_id)`,
`user_events(user_id,occurred_at)`, `user_events(event_type,occurred_at)`,
`notification_events_log(user_id,kind,sent_at)`,
`swipe_decisions(user_id,scoring_format)`,
`trade_decisions(user_id,league_id,decision)`,
`member_rankings(league_id,scoring_format,user_id)`,
`elo_history(user_id,scoring_format,snapshot_at)`, plus single-column
`index=True` on `user_events.user_id`, `device_tokens.user_id`,
`notification_queue.user_id`. **No index on `players.position`**,
`players.search_rank`, `league_members.league_id`, or
`league_preferences(user_id,league_id)` — all read on hot paths.

---

## OBS-DB-01 — `players.position` / `league_members.league_id` unindexed; hit on every session_init

- **Area:** DB
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`load_players(position=...)` filters `WHERE players.position = ?`
(`database.py:3505–3506`) and `load_rookies()` filters
`players.position IN (...)` + `years_exp` (`database.py:3558–3565`). The
`players` table (`database.py:202–223`) declares **no index on `position`** —
its only index is the `player_id` primary key. Likewise `league_members`
(`database.py:130–139`) is queried by `WHERE league_id = ?` in
`load_league_members` (`database.py:2031–2034`), `load_member_rankings`
(`database.py:2608–2612`), `get_ranking_coverage` (`database.py:2665–2670`),
and `_resolve_league_user_ids` (`database.py:1144–1146`) — but the table has
**only** the `UniqueConstraint("league_id","user_id")` (`database.py:138`) and
the autoincrement PK; there is no standalone `league_id` index. On SQLite the
composite unique index *can* serve a `league_id`-only prefix lookup, so
`league_members` is the weaker of the two; `players.position` is the real gap.

### Why it's slow / costly
Missing index → **full table scan**. `players` is ~2 k rows (comment at
`database.py:198–200`, `sync_players` "~2 k-row reference table" at
`database.py:3486`). `build_universal_pool` calls `load_players(position=None)`
once per pool build (`server.py:629`) — that one is a full scan by design
(no filter), but every positional trio/board/rookie request issues a
`position`-filtered scan that re-reads all ~2 k rows to return ~200–500. At 2 k
rows the per-query cost is small in absolute terms (single-digit ms on SQLite,
more on Postgres cold pages), but it is paid on a Reach-8 surface (any
positional view) and grows linearly if the reference table expands.

### Evidence
- Schema: `players` table block `database.py:202–223` — no `Index(...)`,
  `position` is a plain `Column`.
- Hot reader: `database.py:3504–3512` (`select(players_table).where(position=...)`).
- `load_rookies` `database.py:3556–3570`.
- Contrast: every *other* hot table got a composite index in the "Hot-cold-start
  indexes" block (`database.py:714–731`); `players.position` was not included.

### Recommendation(s)
- **Option A (preferred):** add `CREATE INDEX IF NOT EXISTS ix_players_position
  ON players(position)` to the `_hot_path_indexes` list in `_migrate_db()`
  (`database.py:714–723`), matching the existing idempotent pattern. One line,
  works on both SQLite and Postgres, covers `load_players(position=...)` and the
  prefix of `load_rookies`'s `IN`. Trivially safe.
- **Option B:** composite `players(position, search_rank)` — also covers the
  `ORDER BY search_rank` so the positional list is index-ordered, avoiding a
  filesort. Slightly larger index; only worth it if the positional sort shows
  up in a query plan as a sort step.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 0.25 | 80% | 0.5 | **3.2** |

- **Estimated latency delta:** −2–8 ms per positional read on Postgres (cold
  pages worse); negligible on warm SQLite. Small per-call, but on a common
  surface and effectively free to add.
- **Confidence note:** 80% — the missing index is certain; the magnitude is
  modest because the table is only ~2 k rows. Would rise to 100% with an
  `EXPLAIN QUERY PLAN` showing `SCAN players`.

### Related components
`database.load_players`, `load_rookies`, `build_universal_pool` (`server.py:629`),
any positional board/trio/rookie endpoint.

### Prerequisites / dependencies
None.

### Regression risk
None — additive index. No invariant touched.

---

## OBS-DB-02 — Per-opponent trade generation is combinatorial (1-for-2 / 2-for-1 / 3-for-2) and rebuilt from scratch each run

- **Area:** services (trade generation)
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`TradeService.generate_trades` loops every eligible opponent
(`trade_service.py:827`) and calls `_generate_for_pair`
(`trade_service.py:922`), which enumerates 1-for-1
(`trade_service.py:1033–1064`), 2-for-1 (`combinations(user_roster, 2)`,
`trade_service.py:1078`), 1-for-2 (`combinations(opp_roster, 2)`,
`trade_service.py:1134`), and 3-for-2 (`combinations(opp_roster,2) ×
combinations(user_roster,3)`, `trade_service.py:1179–1188`). For a typical
~25-player dynasty roster on each side, the 3-for-2 section alone is
`C(25,2) × C(25,3) ≈ 300 × 2300 ≈ 690 k` iterations per opponent before the
guards fire. Two guards bound it: a **1-second wall-clock deadline** per
opponent (`_deadline = time.monotonic() + 1.0`, `trade_service.py:948`,
checked at `:1072, :1127, :1180`) and a **200 k-iteration budget** (`_iter_budget`,
`trade_service.py:949`, `:1080, :1136, :1190`). So worst case is ~1 s/opponent ×
N opponents, and an 11-opponent league can burn up to ~11 s of CPU.

### Why it's slow / costly
This is the single most expensive **data-production** path in the backend. The
guards cap wall time but don't make the work cheap — they make it *truncate*,
which means deep leagues silently leave opponents/combinations unsampled (the
`global_target` early-exit at `trade_service.py:825,865` and the per-opponent
deadline are both "give up" mechanisms, not speedups). On a free Render dyno
with one worker, this CPU also contends with everything else. The cost is
inherent to the brute-force combination enumeration: there is no pruning of the
give/recv candidate sets *before* the nested loops — every roster player is a
candidate on every side every time.

### Evidence
- Opponent loop: `trade_service.py:827–866`.
- 3-for-2 nested combinations: `trade_service.py:1179–1188`.
- Deadline + iteration budget: `trade_service.py:948–950`, enforced
  `:1072, :1080, :1127, :1136, :1180, :1190`.
- The code comments themselves document the pain: "11 opponents × 1s worst case
  ≈ 11s total wall clock, vs the 33s we were burning before"
  (`trade_service.py:943–947`).
- `_dv` memoization (`trade_service.py:960–971`) and the cheap KTC pre-filter
  (`_ktc_ok` before ELO math, `trade_service.py:1043, :1089–1090`) already exist
  — confirming the hot inner cost is real and partly mitigated, but the
  combination *count* is not reduced.

### Recommendation(s)
- **Option A (preferred):** pre-prune candidate sets per opponent before the
  combination loops. Restrict the user's give-side to the ~8–12 roster players
  whose user-ELO is *below* the opponent's ELO for them (the only players that
  can produce `opp_surplus > 0` in `_mismatch_score`, `trade_service.py:1341`),
  and symmetrically restrict the recv-side. Cutting each side from ~25 to ~12
  shrinks `C(25,3)` (2300) to `C(12,3)` (220) — a ~10× reduction in the
  dominant 3-for-2 term, removing the need to rely on the truncating deadline.
  Backend-only, behaviour-preserving (it only drops candidates that the existing
  `if recv_user <= combined_give_user*0.95: continue` guards would reject
  anyway). Medium effort; needs a careful equivalence test that the pruned set
  yields the same top-K cards.
- **Option B:** cap multi-player combinations by dynasty-value bucket — only
  pair players within ±1 KTC tier so wildly-unbalanced packages are never
  enumerated. Cheaper to implement than A but a coarser filter; risks dropping a
  legitimately lopsided-but-fair package (e.g. depth-for-star).
- **Option C (smallest):** lower `_iter_budget` and tighten `max_candidates`
  (`model_config`, `database.py:542`) — reduces worst-case CPU with zero code,
  but trades away card coverage on deep leagues. Defer unless A/B slip.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 2 | 80% | 3 | **4.3** |

- **Estimated latency delta:** Trades deck is generated in a background worker
  (`server.py:2691`), so this is not first-paint latency — but it governs how
  fast cards *fill* and how much the single dyno worker is saturated.
  Pre-pruning (Option A) cuts the dominant term ~10×, taking the worst-case
  11-opponent sweep from ~11 s toward ~2–3 s of CPU and letting deep leagues
  finish a full sweep instead of truncating. Estimated −5 to −8 s of
  generation/contention time on a deep-league cold run.
- **Confidence note:** 80% — the combinatorics and guards are unambiguous in
  code; the exact speedup depends on real roster ELO distributions, hence
  Impact 2 not 3 and Effort 3 (needs equivalence testing).

### Related components
`trade_service._generate_for_pair`, `generate_trades`, `_mismatch_score`,
`_ktc_ok`, `model_config` keys `max_candidates` / `trade_elo_gap_max`
(`database.py:542, :559`), the `/api/trades/generate` worker (`server.py:2691`).

### Prerequisites / dependencies
None code-wise. An equivalence test harness (same top-K cards before/after) is
strongly advised before shipping.

### Regression risk
Medium. Pruning could change which cards surface if the heuristic is too
aggressive — must verify the top-of-deck cards are identical on a sample of real
rosters. Touches trade-fairness output, which is a user-visible invariant; do
not alter `_fairness_score` / KTC math, only the candidate set fed into them.

---

## OBS-DB-03 — Full ELO replay + O(N) recompute on every session_init, and re-recomputed on every trio/ranking read

- **Area:** services (ranking) / data-production
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
On `session_init` (and the extension/demo equivalents), for **each** of the two
scoring formats, the backend builds a fresh `RankingService` over the full
~500-player universal pool and replays the user's entire swipe history from the
DB: `load_swipe_decisions(user_id, fmt)` (`server.py:4598`, `database.py:1888`)
→ `svc.replay_from_db(historical)` (`ranking_service.py:382`). A heavy ranker
accumulates thousands of pairwise rows (every 3-player trio writes 3 rows —
`save_ranking_swipes`, `database.py:1827–1837`), and the replay reconstructs
interaction counts by iterating all of them (`ranking_service.py:418–427`).

Worse, the ELO **values** are not cached after replay. `_compute_elo`
(`ranking_service.py:613–664`) re-iterates the *entire* `_swipes` +
`_trade_swipes` history over the pool on **every** call, and it is called
repeatedly: `get_rankings` calls it once (`ranking_service.py:341`),
`_algorithmic_trio` calls it again (`ranking_service.py:685`), `_tiered_pool`
calls `_compute_stats` which is a second full-history pass
(`ranking_service.py:523, :563`), and `apply_reorder` calls `_compute_elo`
again (`ranking_service.py:840`). A single `/api/trio` request can walk the full
swipe history 3–4 times.

### Why it's slow / costly
Replay cost is `O(swipes)` and recompute is `O(swipes × pool_filter)` per call,
both rebuilt from raw rows with no memoization. For a power user this is the
dominant CPU on the rank surfaces. The anti-pattern is **"recompute derived
state from the event log on every read instead of caching it."** The persisted
`member_rankings` table already holds the *resolved* ELO snapshot
(`upsert_member_rankings`, `database.py:2528`), yet session_init rebuilds it
from swipes rather than loading the snapshot — so the same numbers are computed
twice (once to save, once to replay).

### Evidence
- Per-format rebuild + replay: `server.py:4569–4606` (loop builds a service per
  format, each replaying full history).
- `_compute_elo` full-history loops: `ranking_service.py:640–664` (no cache;
  recomputed every call).
- Multiple recompute call sites within one request: `ranking_service.py:341`
  (`get_rankings`), `:685` (`_algorithmic_trio`), `:523/:563/:594` (`_compute_stats`
  inside `_tiered_pool`/`_tier_info`), `:840` (`apply_reorder`).
- Replay reconstructs interaction counts by full iteration:
  `ranking_service.py:418–427`.
- A resolved snapshot already exists in `member_rankings` (`database.py:144–152`,
  written by `upsert_member_rankings` `database.py:2528`).

### Recommendation(s)
- **Option A (preferred):** memoize `_compute_elo` / `_compute_stats` results on
  the `RankingService` instance, keyed by `self._version` (already bumped on
  every mutation — `ranking_service.py:230, :265, :294, :448, :828, :859`).
  Invalidate when `_version` changes. Collapses the 3–4 recomputes-per-request
  to one, with no behavioural change. Small, self-contained, low risk.
- **Option B:** at session_init, seed the in-memory ELO from the persisted
  `member_rankings` snapshot (or `tier_overrides`) instead of replaying raw
  swipes, and only replay swipes that postdate the snapshot's `updated_at`.
  Eliminates the full-history replay on warm restarts. Larger change — must
  guarantee replay-from-snapshot produces identical ELO to replay-from-zero
  (the override-anchoring logic at `ranking_service.py:623–662` is subtle), so
  needs a golden-value test. Higher payoff for power users.
- **Option C:** cap/compact `swipe_decisions` history (the file already muses
  about compacting `elo_history` older than 90 days — `database.py:355–358`);
  apply the same to swipe rows so replay length is bounded.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 1 | 80% | 1 | **6.4** |

- **Estimated latency delta:** Option A: −30–60 % CPU on every `/api/trio` and
  rankings read for users with substantial history (multiple full-history passes
  → one). On a power user with thousands of swipes that is tens to low-hundreds
  of ms per rank request; near-zero for new users. Option B additionally trims
  session_init replay time on warm restarts.
- **Confidence note:** 80% — the redundant recompute is certain in code; the
  absolute saving scales with per-user history length, which I could not measure
  without an authed session, so Impact is held at 1.

### Related components
`ranking_service.RankingService` (`_compute_elo`, `_compute_stats`,
`get_rankings`, `_algorithmic_trio`, `_tiered_pool`, `replay_from_db`),
`database.load_swipe_decisions`, `upsert_member_rankings`, `session_init`
(`server.py:4569`).

### Prerequisites / dependencies
Option A: none. Option B: depends on a golden-value equivalence test and on the
override/anchoring semantics staying fixed.

### Regression risk
Option A: low (pure memoization keyed on the existing version counter; must
ensure every mutator bumps `_version` — verified above). Option B: medium —
touches ELO math, a hard cross-client invariant (K-factors, ELO_INITIAL=1500,
tier bands). Any divergence shifts tier placement; requires byte-for-byte ELO
parity testing.

---

## OBS-DB-04 — Cold-dyno player cache: first request after restart pays full Sleeper parse + dual DP fetch + dual pool build

- **Area:** services (in-memory player cache) / cold-start
- **Severity:** P1
- **Status:** observed
- **Evidence type:** hypothesis (cold path not directly measurable read-only)

### What happens today
The in-memory player cache is `_sleeper_cache` (`server.py:333`), lazily loaded
from a disk JSON (`_load_sleeper_cache`, `server.py:336–349`). The universal
pools (`g_universal_by_format`) are built lazily by `_ensure_universal_pools`
(`server.py:743–783`), which on a cold process: (1) reads the Sleeper cache from
disk and `json.loads` the full ~5–10 MB player blob, (2) for **each** of two
formats calls `load_consensus_values` and `load_consensus_elo`
(`server.py:763–766`) — each an HTTP fetch of the DynastyProcess CSV over the
network (`data_loader.py:191–195`, 10 s timeout), and (3) for each format runs
`build_universal_pool` which loops every Sleeper player and, inside, calls
`load_players(position=None)` (`server.py:629`) — a full `players` table read.
This entire chain runs **inside the first `/api/session/init` request** after a
restart (`server.py:4478`), on the request thread.

### Why it's slow / costly
Classic **cold-start-on-critical-path**: the first user after a Render free-tier
spin-down pays the full cache warm — disk JSON parse + **two** sequential
network CSV fetches (the two formats are not fetched in parallel;
`server.py:759` is a serial `for fmt` loop) + two full-pool builds + a full
players-table scan — before their session can return. The disk parse and CSV
fetches are the long poles (each CSV fetch is a cross-internet GET with up to a
10 s timeout). Subsequent requests are warm because `g_universal_by_format` is
memoized (`server.py:751`) and `_sleeper_cache` is process-global
(`server.py:339`), so the cost is paid once per dyno lifetime — but that once is
on a real user's first interaction.

### Evidence
- Lazy disk load + parse: `server.py:336–349`.
- Serial per-format DP fetches inside the build: `server.py:758–766`; each
  resolves to a network `urlopen` of the DP CSV (`data_loader.py:191–195`).
- `build_universal_pool` re-reads the full players table per build:
  `server.py:629` (`load_players(position=None)`).
- Triggered on the request path: `server.py:4478` (`_ensure_universal_pools()`
  is the first thing `session_init` does after auth).
- Recent commit `71ba9b1` ("lightweight player-cache warm endpoint + boot ping")
  shows the team is already attacking this — confirms it's a known hot spot; the
  remaining gap is the *serial* dual-format CSV fetch and the redundant
  full-table read.

### Recommendation(s)
- **Option A (preferred):** warm `_ensure_universal_pools()` at process startup
  (alongside `_maybe_sync_players()` at `server.py:6859`) rather than on the
  first request, and parallelize the two per-format DP CSV fetches (they are
  independent network calls). Moves the entire cost off the user's critical path
  and roughly halves the network portion. Pairs naturally with the existing warm
  endpoint from `71ba9b1`. Low-medium effort, backend-only.
- **Option B:** cache the DynastyProcess CSV to disk with a TTL (it changes
  ~daily) so cold builds read it locally instead of over the internet,
  eliminating the two network round-trips entirely on most cold starts. Medium
  effort; adds a small staleness window.
- **Option C:** pass the already-loaded `all_db_players` into `build_universal_pool`
  once and reuse across both formats instead of calling `load_players(position=None)`
  inside each build (`server.py:629`) — removes one redundant full-table scan per
  build. Small, complementary.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 1 | 3 | 50% | 2 | **0.75** |

- **Estimated latency delta:** on a cold dyno, removes a multi-second stall
  (disk parse + 2× network CSV fetch, each up to several seconds) from the first
  `session_init`. Reach is low (1) because only the *first* request per dyno
  lifetime pays it, but Impact is Massive (3) for that unlucky user — it can be
  the difference between a sub-second and a 5–15 s first load. Warm requests
  unaffected.
- **Confidence note:** 50% — I could not measure the cold path read-only (the
  dyno was warm; `session_init` needs an authed POST). The code path is certain;
  the *magnitude* depends on DP CSV fetch latency and dyno disk speed, hence the
  hypothesis tag and 50%. A boot-time timer log would raise this to 100%.

### Related components
`server._load_sleeper_cache`, `_ensure_universal_pools`, `build_universal_pool`,
`data_loader.load_consensus_values/elo`, `_maybe_sync_players`, `session_init`.

### Prerequisites / dependencies
Option A interacts with the warm endpoint from commit `71ba9b1` — coordinate so
they don't both warm redundantly. Option B needs a writable disk path on Render
(the data dir at `server.py:331` is already used for the Sleeper cache).

### Regression risk
Low–medium. Parallelizing the two CSV fetches must keep per-format pools
independent (they already are — separate dict keys, `server.py:759–773`).
Startup warming adds boot time but off the request path. Must not let a DP fetch
failure block boot — keep the existing graceful fallback (`data_loader.py:197–199`).

---

## OBS-DB-05 — `check_for_match` loads ALL of a user's "like" rows and set-compares in Python on every trade swipe

- **Area:** DB / services
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
On every trade "like" swipe, `check_for_match` (`database.py:2700`) runs
`SELECT * FROM trade_decisions WHERE user_id = ? AND league_id = ? AND decision
= 'like'` (`database.py:2721–2729`), pulls **every** matching row into Python,
JSON-decodes `give_player_ids` / `receive_player_ids` for each
(`database.py:2733–2734`), and does set comparisons in a Python loop
(`database.py:2731–2739`) to find a mirrored trade. The `(user_id, league_id,
decision)` index (`database.py:716–717`) makes the *fetch* selective, but the
result set is unbounded — it returns the counterparty's entire like-history for
that league and re-parses all of it on each swipe.

### Why it's slow / costly
This is `SELECT *` (wide rows incl. two JSON Text columns) + per-row
`json.loads` + Python-side set comparison, repeated on a Reach-6 action (trade
swipes happen many times per session). The matching is fundamentally a
membership test that SQL cannot do directly because the player IDs are stored as
JSON arrays (`trade_decisions` columns `give_player_ids` / `receive_player_ids`
are `Text` JSON, `database.py:122–123`) — so the work *must* come back to
Python, but it doesn't have to be *all* rows every time. For an active league
trader this set grows unbounded over a season.

### Evidence
- Unbounded fetch of all like-rows: `database.py:2720–2729`.
- Per-row JSON decode + set compare in Python: `database.py:2731–2739`.
- `SELECT *` pulls both JSON Text columns plus `trade_id`, timestamps, etc.,
  even though only the two ID arrays are needed.

### Recommendation(s)
- **Option A (preferred):** narrow the SELECT to just
  `give_player_ids, receive_player_ids` (drop the wide columns) and add a
  recency bound (e.g. only the last N days of likes, mirroring the `since_days`
  param `load_trade_decisions` already supports at `database.py:1946,1960–1962`).
  A mirror match is almost always against a recent like; an unbounded scan of a
  season's history is wasteful. Small, low risk.
- **Option B:** store a normalized, order-independent match key
  (`sorted(give)+"|"+sorted(receive)` and its mirror) as an indexed column on
  `trade_decisions` at write time, then `check_for_match` becomes a single
  indexed equality lookup instead of a fetch-all-and-compare. Eliminates the
  Python loop entirely. Requires a schema column + backfill (`_migrate_db`
  already has the idempotent ALTER pattern, `database.py:628–633`), so higher
  effort but turns an O(likes) scan into O(1).

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 1 | **2.4** |

- **Estimated latency delta:** Option A: −tens of ms per swipe for an active
  trader (fewer rows, fewer JSON parses, narrower rows); negligible for a light
  user. Option B: makes it constant-time regardless of history — best for
  end-of-season heavy leagues.
- **Confidence note:** 80% — the unbounded `SELECT *` + Python loop is clear in
  code; absolute saving depends on per-user like-count, which I couldn't measure.

### Related components
`database.check_for_match`, `match_already_exists` (`database.py:2744`, same
fetch-all-and-compare shape — see CROSS-REF), the trade-swipe handler in
`server.py` (calls `check_for_match` on each like).

### Prerequisites / dependencies
Option A: none. Option B: schema column + backfill + dual-write at every
`save_trade_decision` (`database.py:1922`).

### Regression risk
Low for A (must keep the recency window generous enough not to miss a slightly
older mirrored like). Medium for B (the normalized key must exactly mirror the
set-comparison semantics, including pick pseudo-IDs).

---

## OBS-DB-06 — `member_rankings` / `league_members` for the whole league re-read per request, no caching; community-ELO mean recomputed in Python each Trends call

- **Area:** DB / services (trends)
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`load_member_rankings` (`database.py:2585`) reads **all** league-member rows
(`SELECT * FROM league_members WHERE league_id = ?`, `database.py:2608–2612`)
**plus all** `member_rankings` rows for the league/format
(`database.py:2621–2634`) and assembles a nested `{user_id: {elo_ratings:{...}}}`
dict in Python. This runs on session_init (`server.py:1097`, `:6645`), the
contrarian/consensus Trends endpoints (via
`load_community_elo_for_league` → `load_member_rankings`,
`database.py:4200–4216`), and the ranking-coverage views (`server.py:4033, :4112,
:4120`). Then `trends_service.compute_contrarian_score` /
`compute_consensus_gap` recompute the **community mean ELO per player** by
looping every member's every rating in Python on each call
(`trends_service.py:99–113` and `:225–238` — the identical mean-computation
block appears twice). For a 12-team league each with ~500 ranked players that's
~6 k rating rows summed in Python per Trends request, with no memoization across
the two endpoints that both need the same mean.

### Why it's slow / costly
The aggregation (`SUM(elo) / COUNT(*) GROUP BY player_id`) is exactly what SQL
does efficiently with the existing `member_rankings(league_id, scoring_format,
user_id)` index, but it's pulled into Python and recomputed per request and per
endpoint. The anti-patterns: **(a)** `SELECT *` returning wide rows when only
`user_id, player_id, elo` are needed; **(b)** **aggregation in Python that SQL
could do**; **(c)** **identical read re-run within and across requests** with no
cache — contrarian and consensus-gap endpoints each independently rebuild the
same community-mean map. Community rankings change only when a leaguemate
submits a new ranking, so the mean is highly cacheable.

### Evidence
- Full league member + ranking reads: `database.py:2606–2634`.
- Community-mean recompute, duplicated: `trends_service.py:99–113` and
  `:224–238` (byte-identical loop).
- Both Trends endpoints depend on `load_member_rankings` via
  `load_community_elo_for_league` (`database.py:4200–4216`).
- `member_rankings` carries the index that could serve a SQL `GROUP BY`
  (`database.py:719–720`).

### Recommendation(s)
- **Option A (preferred):** push the community-mean aggregation into SQL — a
  `SELECT player_id, AVG(elo) ... WHERE league_id=? AND scoring_format=? AND
  user_id != ? GROUP BY player_id` returns the per-player mean directly, served
  by the existing index, replacing the Python sum/loop in both Trends functions.
  Also narrow `load_member_rankings`'s SELECT to `(user_id, player_id, elo)`.
  Medium effort; the contrarian "above/below" lists still need per-user deltas,
  so keep the raw read where individual user ELOs are required but use the SQL
  mean for the consensus baseline.
- **Option B:** server-side cache the assembled community-ranking map per
  `(league_id, scoring_format)` with a short TTL (the leaderboard endpoints
  already use a 5-min server cache per `database.py:1126–1127`), invalidated on
  `upsert_member_rankings`. Cheaper to build than A and helps every consumer
  (session_init, both Trends endpoints, coverage). Defer A if B alone gets the
  win.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 0.5 | 80% | 2 | **0.8** |

- **Estimated latency delta:** −50–150 ms per Trends request on a populated
  12-team league (Python aggregation over ~6 k rows → indexed SQL GROUP BY or a
  cache hit). Smaller on sparse leagues. Trends is an occasional surface
  (Reach 4), so the win is real but secondary.
- **Confidence note:** 80% — the redundant Python aggregation and `SELECT *` are
  clear; magnitude depends on league population, which I couldn't measure.

### Related components
`database.load_member_rankings`, `load_community_elo_for_league`,
`get_ranking_coverage`, `trends_service.compute_contrarian_score` /
`compute_consensus_gap`, the `/api/trends/*` endpoints.

### Prerequisites / dependencies
Option B benefits from an explicit cache-invalidation hook in
`upsert_member_rankings` (`database.py:2528`).

### Regression risk
Low. The contrarian/consensus scores are derived display values, not a hard
cross-client invariant — but verify the SQL `AVG` matches the Python mean
(NULL/zero handling) so scores don't shift.

---

## OBS-DB-07 — `upsert_league_members` does N select-then-insert/update round-trips inside one transaction

- **Area:** DB
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`upsert_league_members` (`database.py:1978`) loops each member and, per member,
issues a `SELECT` to check existence (`database.py:1996–2001`) then a separate
`UPDATE` or `INSERT` (`database.py:2003–2025`). For a 12-team league that's up
to **24 statements** (12 selects + 12 writes) per call. This runs on session_init
to record league membership.

### Why it's slow / costly
Classic **N+1 write pattern** — one existence probe per row instead of a single
bulk upsert. The table already has the `UniqueConstraint("league_id","user_id")`
(`database.py:138`) that a native upsert (`INSERT ... ON CONFLICT DO UPDATE` on
Postgres / `INSERT OR REPLACE` on SQLite) could key on, collapsing 24 statements
to 1–2. Within a single transaction the round-trips are cheap on local SQLite
but add up on Postgres (network RTT per statement).

### Evidence
- Per-member select-then-write loop: `database.py:1990–2025`.
- Unique constraint that enables a native upsert: `database.py:138`.
- `_migrate_db` already branches SQLite vs Postgres upsert syntax for
  `model_config` (`database.py:749–759`) — the same dialect-aware pattern applies
  here.

### Recommendation(s)
- **Option A (preferred):** replace the loop with a single dialect-aware bulk
  upsert keyed on `uq_league_member` — `ON CONFLICT (league_id, user_id) DO
  UPDATE` on Postgres, `INSERT OR REPLACE` (or `ON CONFLICT`) on SQLite, reusing
  the branch pattern already at `database.py:749–759`. Cuts ~24 statements to 1.
  Small, well-scoped.
- **Option B:** keep the loop but batch the existence check into one
  `SELECT user_id WHERE league_id=? AND user_id IN (...)` up front, then split
  into one bulk INSERT + one bulk UPDATE. Less elegant than A but avoids native
  upsert dialect differences if those are a concern.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 0.25 | 80% | 1 | **0.8** |

- **Estimated latency delta:** −10–40 ms on session_init for a full league on
  Postgres (24 round-trips → 1–2); negligible on SQLite. Session_init is
  Reach-8, but this write is a small slice of it, hence Impact 0.25.
- **Confidence note:** 80% — the N+1 is certain; Postgres RTT savings depend on
  DB locality, which I couldn't measure.

### Related components
`database.upsert_league_members`, `session_init` (`server.py` membership write).

### Prerequisites / dependencies
None.

### Regression risk
Low. Must preserve the "newest snapshot wins" semantics (REPLACE/UPDATE must set
all columns incl. `updated_at`). No invariant touched.

---

## Top 3 by RICE-P

1. **OBS-DB-03 — cache/memoize ELO recompute (score 6.4, P1).** Highest-value,
   lowest-effort: a `_version`-keyed memo on `_compute_elo`/`_compute_stats`
   collapses 3–4 full-history passes per rank request to one, on a Reach-8
   surface, with ~1 person-day and low risk.
2. **OBS-DB-02 — prune trade-generation candidate sets (score 4.3, P1).** The
   most expensive data-production path; pre-pruning the combination inputs cuts
   the dominant 3-for-2 term ~10× and removes reliance on the truncating
   per-opponent deadline. Higher effort (3 d) but large CPU/contention win.
3. **OBS-DB-01 — add `ix_players_position` (score 3.2, P2).** A one-line,
   essentially free idempotent index closing the only missing hot-column index,
   on a Reach-8 positional surface.

---

## CROSS-REF

- **`match_already_exists` (`database.py:2744`)** has the same fetch-rows-then-
  compare-in-Python shape as OBS-DB-05's `check_for_match`; if Option B (indexed
  normalized match key) is pursued, apply it here too.
- **(Agent 03 — backend routes)** The Trades deck is produced by a background
  worker polled by the client (`server.py:2691`, generation thread). The poll
  cadence / streaming behaviour is route-layer, not data-layer.
- **(Agent 06 — cold-start)** OBS-DB-04's dyno cold-start cost overlaps the
  network/cold-start agent's remit (Render free-tier spin-down); the
  *data-layer* portion (serial dual-format DP CSV fetch + redundant full-table
  read in `build_universal_pool`) is captured here, but the dyno wake itself is
  Agent 06.
- **`save_elo_history` (`database.py` ~4129–4164)** writes a snapshot row per
  changed player on every ranking submit (`server.py:1593`). The append is bulk
  (single insert), so it is not a per-row N+1 — noted as healthy, not a finding.
  The table has no pruning yet (`database.py:355–358` acknowledges this); a
  future compaction job is the right home, not this audit.
