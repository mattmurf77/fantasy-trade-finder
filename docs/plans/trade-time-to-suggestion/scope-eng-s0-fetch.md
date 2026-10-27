# Feature Scope — S0, fetch side: background roster refresh, Sleeper 429 backoff, roster-state stamp

**Date:** 2026-10-20. Stage A (design) at `92513bc1`; Stage B (PR-A build) on the same branch, §3 and §5.
**Entry point:** direct operator ask, 2026-10-20, relayed by the coordinator: "Yes building should resume on the
200 ms path." Brief: `docs/plans/org-bringup/briefs/build-platforms-eng-s0-sleeper.md` (head-eng), Piece 1.
Plan of record: `docs/plans/org-bringup/launch-readiness-eng.md` §3a, row S0.
**Builder:** platforms-eng (lead), `eng-backend` worker. Branch `build/s0-roster-refresh`, cut from `origin/main`
`678834ab` (2026-10-14 21:31 -0400). §A–§C cite that sha. §3's code-walk, §5 and R9/R10 cite the branch HEAD
after PR-A.
**Companion:** trades-eng's `scope-eng-200ms.md` (v1, 2026-10-20) owns the serve side: `roster_snapshot`, `vsn1`,
job and page freshness, the I-1 serve filter, and the `on_roster_change` handler. This file is the standalone
fetch-side block the brief allows ("write `scope-eng-s0-fetch.md` beside it"). §C below is the contract text to
mirror into trades-eng's §6.1.
**Supersedes and cites:** PR #339 (`prd.md`, `scope.md`; trades-pm's, read at `65b7d52f`, not edited here) set
250 ms. **200 ms supersedes it.** Its §5.1 bounds, §5.3 invariants and platforms-pm R7 (no scheduled or headless
Sleeper roster reads beyond today's pattern) stand. Product's AC-L3 ("no live Sleeper or platform call on the tap
path") is the acceptance for this piece.
**Operator sign-off on waivers:** not needed yet. §1 answers (b); nothing else is waived. Open items are in §Q.

---

## A. Today's tap path, from code

"Tap path" = the tap on Find a trade → `POST /api/trades/generate` → (hit | join | kickoff → worker) → `/status`
polls → first card. Under the checked-in flags (`config/features.json`):

| # | Live Sleeper call | Where | Count | When |
|---|---|---|---|---|
| 1 | — | `/api/trades/generate` request thread, `server.py:14619-14817` | **0** | Verified: no `_sleeper_get`, `_fetch_*`, lineup or meta helper in the handler |
| 2 | — | `/api/trades/status`, `server.py:15788-15806` | **0** | Same check |
| 3 | `GET /league/<id>` (10 s timeout) | Worker, `deck_quality` → `_league_lineup_slots` `server.py:8891` → `_sleeper_lineup_slots` `:29130-29151` → `_fetch_sleeper_league_meta` `:29147` → `:743` | **0–1** | On a job miss when the in-process meta cache (`_FA_LEAGUE_META_CACHE`, 15-min TTL, `:30350-30351`) is cold. `deck.quality_filters` is on (`features.json:218`). The session-init pre-gen job warms it, so a tap more than 15 min after the last job pays it |
| **Total, checked-in flags** | | | **0–1 per tap** | Plus the queueing in row 8 |

Dormant today, live the moment a flag or knob flips:

| # | Live Sleeper call | Where | Count | Gate |
|---|---|---|---|---|
| 4 | `GET /league/<id>/rosters` (+ row 3's meta via `:5837`) | `_build_trade_roster_context` `server.py:5846-5847`, unless `sess["prepared_roster_snapshot"]` is set. Called from the worker (`:8561`) and from the **synchronous** `/api/trades/fair-packages` (`:15547` → `:15698` → `:15451`) and `/api/trades/asset-ideas` (`:14818` → `:15069`) | 1 (+0–1) | `trade.roster_protection`, `trade.mutual_benefit_v1`, `trade.roster_evaluation` (all false, `features.json:272-274`); the sync routes also need an owner arm |
| 5 | `GET /league/<id>`, `/rosters`, `/users` (+ `/matchups/<w>`, cached) | Value core: `_value_core_standings` `server.py:7478-7490` → `outlook.build_league_state` (`backend/outlook/league_state.py:161,176-177,260`) through `_outlook_sleeper_fetch` (`server.py:30163-30215`, "stay live on purpose"); plus `_league_lineup_slots` `:7513` and `_sleeper_roster_limit` `:7517` (meta cache) | 3 + 0–N | `trade.value_core` false (`features.json:276`) |
| 6 | `/league/<id>`, `/rosters`, `/users`, `/traded_picks`, `/drafts` | Prepared adoption: `server.py:9361` → `prepared_trade_runtime.try_adopt` → `refresh_target` → `read_source` (`prepared_trade_runtime.py:153`) → `prepared_trade_cohort.py:296-299` | 5 | `model_config.prepared_trade_inventory_enabled` = 0 (`prepared_trade_read_guard.py:63-65`); Option 3 stays dark |
| 7 | (send path, not first card) `/rosters`, `/traded_picks`, meta | `/api/trades/propose` `server.py:19529-19569` | — | **Out of scope by design:** I-2 requires a live read at send |

Indirect, every flag state:

| # | Effect | Where |
|---|---|---|
| 8 | **A tap queues behind session-init's live reads.** `resolve_session_input` makes 3 GETs on the request thread (`session_input.py:56-59`, 15 s timeout each via `server.py:583`) at app open and foreground, on the single sync worker (`render.yaml:16`, `--workers 1`, no threads) | E1 (threads) fixes the queueing; S0 does not change the 3 request-thread reads, it makes them the *only* roster/meta reads per init |

**Where rosters live today.**
- `league_members` (`database.py:625-633`): one row per (league, team) with `roster_data` = JSON player ids. The tap
  path's jobs do **not** read it; they deep-copy the session's in-memory `League` and `user_roster` built at session
  init (`server.py:22240-22268`, `:22481-22483`). Headless builds read it (G-075).
- `leagues.roster_data` / `opponent_data` (`database.py:526-527`): last writer's view, written by `upsert_league`
  (`server.py:22605-22612`).
- `league_roster_history` (`database.py:1924-1987`): weekly ADR-011 snapshot, not a serving source.
- In process: `_FA_LEAGUE_META_CACHE` (meta, 15 min), the outlook week caches, and the session dict. Nothing stores
  a fetch time, a failure, or a fingerprint per league.

## B. Design

### B.1 Trigger: reuse session init; no new route, no mobile change

- **App open:** `mobile/App.tsx:115-117` calls `useSession.revalidateSession()` after boot.
- **Foreground:** `mobile/App.tsx:199-210`, `AppState` → `'active'` calls `revalidateSession()` (on any return to
  active, including from `'inactive'`).
- **Throttle:** 60 s (`useSession.ts:65`, passed at `:369`, enforced in `leagueSession.ts:81`). A failed
  revalidate keeps the cached token and never signs the user out (`useSession.ts:357-378`).
- `revalidateSession` → `initializeLeagueSession` → `POST /api/session/init`. **So a foreground trigger already
  exists, and session init already re-reads Sleeper rosters on it.** S0 makes that read the refresh: no new route,
  no new binary.
- **Mid-session top-up — BUILT (Stage D, 2026-10-24; Product's P41, the non-blocking floor kick):**
  `roster_refresh.maybe_refresh_async(league_id, max_age_s, *, retry_after_s=60.0) -> bool`
  (`backend/roster_refresh.py:123-165`).
  - **Caller:** trades-eng calls it from `/generate` after the response is built, never under a lock, with
    model_config `trade_roster_bound_s` (default 300) as `max_age_s`. It is user-triggered (R7-compliant) and
    never awaited, so it's not on the tap path (AC-L3).
  - **Returns at once,** True only if it started a refresh.
  - **No-ops (False, no thread):**
    - a linked platform league (`db.is_linked_platform_league`), or an id that isn't a Sleeper league id
      (demo/sentinel; `:143`);
    - the 429 circuit is open (`:145`);
    - `league_roster_state.refreshed_at` is within `max_age_s` (`_within_bound`, `:102-107`). No row, NULL, an
      unparseable stamp or a future stamp counts as past the bound;
    - **retry cooldown (follow-up commit):** the last attempt failed (`status == 'stale'`) and its `updated_at`
      (stamped by `mark_league_roster_failed`) is younger than `retry_after_s`, default 60 s (`_cooling_down`,
      `:110-120`). It is read from the same single `get_league_roster_state` call as the bound (`:147-148`).
      An unparseable or future stamp never blocks, and a `fresh`-but-past-bound league ignores the cooldown;
    - a refresh for this league is already in flight (`:153-156`).
  - **Single-flight:** the module `_inflight_lock` (`:32`) guards only the in-flight set's check-and-add (`:153-156`)
    and remove (`:161-162`, and the thread's `finally` at `:175-176`). No Sleeper call and no DB write runs under
    it. Its two pre-checks are small DB reads, outside the lock.
  - **The thread** (`daemon=True`) runs `_run_refresh` → `_refresh_league(league_id, started)` (`:179-244`), which
    never raises and always leaves the in-flight set:
    1. rosters + users via the circuit-guarded `server._sleeper_get` (lazy `from . import server`; a read
       exception → `record_failure`, `:198`);
    2. members in session init's row shape, `player_ids` with nulls dropped (G-004), written by
       `db.replace_league_members_snapshot` (`:210`), which refuses an empty snapshot;
    3. behind `picks.owned_sync`: meta from `_FA_LEAGUE_META_CACHE` when younger than `_FA_LEAGUE_META_TTL`
       (15 min, the same rule every other reader of that cache uses; QA P3 on #378), else one
       `_fetch_sleeper_league_meta` read that re-warms the cache (`:225-234`); scoring from
       `db.get_league_scoring`; then
       `_sync_sleeper_owned_picks(…, rosters=, meta=)` (`:237`), where `None` means picks failed (R10);
    4. `record_outcome(league_id, started, members_ok=, picks_ok=)` (`:244`).
  - **PR-B seam (BUILT 2026-10-27, B.3 step 7):** the stamp hangs off `record_outcome`, which both this kick
    (`_refresh_league`) and the session-init daemon call, so both refreshes stamp and hook on their own threads.
  - **Repeated failures:** closed by the retry cooldown above. A league whose reads keep failing (5xx, timeouts; the
    circuit only catches 429s) is kicked at most once per `retry_after_s`, instead of on every tap past the bound.

### B.2 What is stored, and where (schema granted by head-eng, 2026-10-20)

The rows are the existing fp inputs: `league_members`, `draft_picks`, `leagues.draft_status`. The refresh record is
a new table:

```
league_roster_state
  league_id        String  PK        -- platform-native id, same semantics as leagues.sleeper_league_id
  roster_fp        String  NULL      -- "rfp1:…" from roster_snapshot(...).fp after the last committed refresh
  refreshed_at     String  NULL      -- ISO UTC: start time of the fetch whose rows are committed
  status           String  NOT NULL  -- 'fresh' | 'stale' only (contract v0.3 §3; "missing" is derived)
  last_error_code  String  NULL      -- see below; NULL after a success
  updated_at       String  NOT NULL
```

- **`status`** describes the last attempt, not the PRD bound. `fresh` = the last attempt committed members and
  picks. `stale` = the last attempt failed, and the last good rows are kept.
  - **Contract v0.3 §3 (2026-10-23): the row never stores `missing`.** A never-refreshed league that fails is
    `stale` with `refreshed_at` NULL.
  - "Missing" (strict: no cards) is derived by trades-eng's `roster_snapshot` only from absent `league_members`
    rows. No state row (or no table) reads as `unknown`.
  - That way, rows arriving by another path (an import, an operator refresh) can't be blanked by a stored verdict.
  - The ≤ 5 min bound is trades-eng's, computed from `refreshed_at` (§Q2).
- **`last_error_code`** (closed set): `rate_limited` (429 or circuit open), `blocked` (403, incl. Cloudflare 1010),
  `http_4xx`, `http_5xx`, `timeout`, `network`, `invalid_payload`, `picks_unavailable` (owned-pick sync skipped on a
  failed read, `server.py:14267-14290`), `write_failed`.
- **Not stored:** the raw Sleeper payload. So the `reserve`/`taxi` split is not persisted (see B.4, row 4).
- **Size:** one row per league, < 200 bytes. No G-072 paging concern. A **new table, not columns on `leagues`**: the
  prepared read guard hashes every `leagues` column except three (`prepared_trade_read_guard.py:71-73`), so
  `refreshed_at` on `leagues` would fail that guard on every refresh.
- Postgres: one indexed PK; written with dialect-aware insert … on conflict (the `upsert_platform_league` pattern,
  `database.py:13790-13830`).

### B.3 The refresh, in contract §4 order (Sleeper)

**Request thread** (`/api/session/init`):
1. `resolve_session_input` reads rosters, users and meta (`session_input.py:56-59`), unchanged in count. Changes:
   - It also returns the raw `rosters` list and `meta` dict, **not merged into the request body**, for the daemon
     (B.5).
   - Player ids are filtered for `None`/`""` **before** `str()`. Today `[str(p) for p in (r.get("players") or [])]`
     (`:72`) turns a G-004 null into the string `"None"`, which then lands in `league_members.roster_data`. The
     same fix applies at `server.py:27249`.
   - The fetch start time is captured as `fetch_started_at`.
2. Seed `_FA_LEAGUE_META_CACHE[league_id] = (now, meta)` from that payload, at zero calls. Every server restart
   kills sessions, so the next tap always follows a session init that reseeds it.
3. **On a read failure:** classify it (`last_error_code`), upsert `league_roster_state` to `status='stale'` (rows
   untouched, `roster_fp` and `refreshed_at` kept; always `stale` since v0.3), then return today's
   503 `league_data_unavailable`. Session-init behavior is otherwise unchanged in v1. The mobile client keeps its
   token and its live server session, so taps keep working from stored state (§Q-ONB for the restart case).

**Daemon** (`_session_init_background_writes_impl`, `server.py:22552-22973`); order otherwise unchanged:

4. **Members:** write the authoritative members with **replace semantics** for Sleeper: delete then insert in one
   transaction (`replace_espn_league_members`, `database.py:13708-13738`, is already platform-agnostic), only when
   the payload is a valid non-empty list (G-015). It replaces the `upsert_league_members` call at `server.py:22804`,
   for Sleeper leagues only. **As built (PR-A):** only `league_roster_state.refreshed_at` is monotonic
   (`mark_league_roster_fresh` never rewinds it). The members write itself is last-writer-wins. Two inits for one
   league whose Sleeper reads straddle a roster change can leave the older rows; the next init corrects them.
   Making the members write conditional needs it in the same transaction as the state row (`SELECT … FOR UPDATE`
   on Postgres). That's deferred as residual R9, not built.
5. **Picks:** `_sync_sleeper_owned_picks(rosters=…, meta=…)` (`:22893`), now handed the request-thread payloads.
   It still makes its own `traded_picks` + `drafts` reads (D-178 pinned).
6. **Draft state:** `_refresh_league_draft_status` (`:22909`), TTL-gated, unchanged.
7. **Stamp, then hook** (new, right after step 6 and before the trade capture at `:22917`):
   ```
   with engine.begin() as conn:
       new = roster_snapshot(conn, league_id).fp             # trades-eng's pure function
       old = SELECT roster_fp FROM league_roster_state WHERE league_id = :lid
       if no row:   INSERT … ON CONFLICT DO NOTHING            -> won = rowcount == 1, old = None
       elif new == old: UPDATE refreshed_at, status, last_error_code=NULL   -> no hook
       else:        UPDATE … SET roster_fp=:new, refreshed_at, status, last_error_code, updated_at
                    WHERE league_id=:lid AND roster_fp IS NOT DISTINCT FROM :old   -> won = rowcount == 1
       if not won:  re-read once; if stored == new -> another writer already hooked; else retry the CAS once
   after commit, if won: on_roster_change(league_id, old, new)   # in try/except; never raises into the daemon
   ```
   - `status='fresh'` only if steps 4 and 5 both committed. If step 5 skipped on a failed read, write
     `status='stale'`, `last_error_code='picks_unavailable'`, and leave `refreshed_at` unchanged (§Q2).
   - **Concurrency:** session init and foreground (or two league members) can run two daemons at once. The CAS
     makes the stored fp single-valued. A double hook call is possible and accepted (trades-eng debounces).
   - The first-ever stamp calls the hook with `old_fp=None` (§Q1).
   - **As built (PR-B, 2026-10-27).** Simpler than the sketch above, same contract:
     - **Where:** `roster_refresh.record_outcome` calls `stamp(league_id)` right after `mark_league_roster_fresh`
       commits (`roster_refresh.py:83`). Both refreshes reach it: the session-init daemon (`server.py:27046`,
       after members, picks and draft status) and the P41 kick (`_refresh_league`). A `stale` outcome (a failed
       read, `write_failed`, `picks_unavailable`) or a failed state write never stamps.
     - **`stamp`** (`roster_refresh.py:95-132`): read the stored `roster_fp` (`old`); compute `new` =
       `roster_snapshot.roster_snapshot(conn, lid, pick_source=server._pick_read_source()).fp` (`:118`), the
       serve's function and pick source (lazy `server` import, the `_refresh_league` pattern); `new == old` → no
       write, no hook (`:119`); else `database.cas_league_roster_fp(lid, old, new)` (`:121`, `database.py:9302`):
       one `UPDATE … SET roster_fp=:new WHERE league_id=:lid AND roster_fp = :old` (`IS NULL` for the first
       stamp), committed before it returns, touching no other column.
     - **Lost CAS:** no hook and no retry. The winner stamped the rows it read and fired its own hook; the
       serve recomputes from rows either way.
     - **No state row:** the UPDATE matches nothing, so no stamp. `record_outcome` always writes the row first.
     - **Hook** (`:129`): `roster_snapshot.on_roster_change(lid, old, new)` after the CAS transaction has committed
       and returned its connection. `roster_refresh` holds no lock there (`_inflight_lock` guards only the
       in-flight set), and `on_roster_change` releases its registry lock before calling handlers (A3). Wrapped:
       an exception is logged (`on_roster_change failed`) and never reaches the refresh.
     - **Fingerprint failure** (a read error, the pick-source call, the CAS write): logged as
       `roster fp stamp failed`, `roster_fp` left as stored, no hook, and the recorded outcome stays `fresh`.
     - **Non-Sleeper leagues:** never stamped by this PR. `maybe_refresh_async` no-ops on
       `is_linked_platform_league` and the session-init daemon calls `record_outcome` only when
       `not _platform_linked`. The B.6 stamps on the other writers are **not in PR-B** (a follow-up; the serve
       recomputes the fp from rows, so correctness holds).
     - **Thread:** `record_outcome` runs only on the session-init daemon (`session-init-bg-writes`) and the kick
       thread (`roster-refresh-<id>`). The request thread calls only `record_failure`, which never stamps.

**Platform guard.** Steps 1–7's Sleeper path runs only when `not is_linked_platform_league(league_id)`.
`session_input.py:42` already branches on it before the `isdigit()` Sleeper branch (`:53`). Never infer platform
from id shape (G-014, G-030). For ESPN/MFL/Fleaflicker, session init makes no network read and does **not** advance
`refreshed_at`; their import routes stamp instead (B.6).

### B.4 Tap-path reads: what switches from live to stored

| Call (A) | Switch | Owner |
|---|---|---|
| 3. `_league_lineup_slots` meta on the trade paths | Seeded by B.3 step 2. Add a no-fetch read for the trade paths (`allow_fetch=False`: a cached entry of any age within the PRD's 24 h league-settings bound, else `None` → AC-9a's "unknown lineup → fresh path", never a silent skip) | trades-eng's call sites (`:5837`, `:7513`, `:8891`); platforms-eng supplies the accessor (§Q7) |
| 4. `_build_trade_roster_context` `/rosters` GET | Pass `raw_rosters=None` and let `trade_roster_adapter.build_context` fall back to the session's member rosters (`trade_roster_adapter.py:32-43`). The adapter then marks availability unknown, because reserve/taxi aren't stored. Zero calls. | trades-eng's region (`server.py:5827-5870`), §Q7 |
| 5. Value-core standings | **Not switched in S0.** Standings come from roster `settings` (W/L/PF), which the store doesn't hold. Risk R5; §Q10 | models-eng / trades-eng |
| 6. Prepared adoption | Stays dark. If it's ever enabled, it breaks AC-L3 as built | trades-eng |
| 8. Session-init reads | Unchanged count; they *are* the refresh. Optional: cut their timeout from 15 s to 5 s (Risk R3) | platforms-eng + onboarding-eng review |

**After S0 and trades-eng's S0-serve, the organic tap path makes 0 live Sleeper calls** (AC-L3), under every flag
state except value core and prepared adoption, which carry the open items above.

### B.5 Budget vs D-178 (per Sleeper session init, in season)

| Endpoint | Today (pinned, `test_session_init_sleeper_calls.py:211-220`) | After S0 |
|---|---|---|
| `/league/<id>/rosters` | 2 (`session_input.py:57` + daemon `server.py:22833`) | **1** (daemon handed the payload) |
| `/league/<id>` (meta) | 2 (`session_input.py:59` + daemon `server.py:22579`) | **1** (handed; `_league_meta()` returns it) |
| `/league/<id>/users` | 1 | 1 |
| `/traded_picks`, `/drafts` | 1 + 1 | 1 + 1 |
| `/transactions/<w>` | ≤ 2 | ≤ 2 |
| GraphQL `league_players` (trade block) | 1 | 1 |
| **Total** | **≤ 10** | **≤ 8 (net −2)** |
| **Tap path** | 0–1 (+ dormant 1–5) | **0** |

**The P41 kick (B.1, built):** at most **4 Sleeper reads per kick** (rosters, users, traded_picks, drafts), **5 on a
meta-cache miss**. It fires only past the bound (`trade_roster_bound_s`, default 300 s), only on user action (a
`/generate` call), one in flight per league, and never while the 429 circuit is open. A league refreshed by session
init within the bound costs 0. **Worst case for a league whose reads keep failing:** ≤ 4–5 reads per
`retry_after_s` (default 60 s), because of the cooldown on the last failed attempt's `updated_at`.

### B.6 Non-Sleeper writers of fp inputs (open item for trades-eng)

`roster_snapshot` recomputes the fp from rows at serve, so a writer that doesn't stamp is still **caught at serve**.
It just doesn't fire `on_roster_change`, so no proactive invalidation or page rebuild happens. Today's writers:

| Input | Writer | Where | Stamps after S0? |
|---|---|---|---|
| `league_members` | Session-init daemon (all platforms) | `server.py:22804` | Yes (Sleeper). Platform leagues re-upsert the DB snapshot; a no-op stamp is harmless but must not advance `refreshed_at` |
| `league_members` | `_refresh_sleeper_members` (operator, Calibration pre-gen) | `server.py:27237-27255` | Proposed yes (same helper) |
| `league_members` | ESPN/MFL/Fleaflicker link and import, via `replace_espn_league_members` | `server.py:28748, 28968, 31397, 31542, 31649, 33326, 33438` | Proposed yes: platforms-eng's routes, one call each after commit |
| `draft_picks` | Sleeper owned-pick sync → `sync_draft_picks` | `server.py:14360` (via `:22893`) | Yes (inside B.3) |
| `draft_picks` | MFL normalize → `replace_draft_picks` | `server.py:14188, 14247` (via `:22875`, `:19213`, `:31412`, `:31555`, `:31659`) | Proposed yes |
| `draft_picks` | User-asserted picks (ADR-010): `assign_draft_pick`, `seed_pick_grid`, `record_draft_picks` | `server.py:17787, 17902, 17993` | **trades-eng / draft owner's call** (§Q11) |
| `leagues.draft_status` | `_refresh_league_draft_status`: session init `:22909` and the **hourly tick** `:24573` (headless, today's pattern) | `server.py:19179-19201` | Proposed yes (no new reads; stamp only) |

A single helper does it: `roster_refresh.stamp(league_id, *, refreshed_at=None, status=None)`, i.e. B.3 step 7.

### B.7 Sleeper 429 backoff: one per-process circuit

There is no 429 or backoff handling on any Sleeper path today. `_sleeper_get` retries only on an SSL failure
(`server.py:619-633`). 429s are already recorded with their status by `observe_call`
(`api_observability.py:278-291`).

- **Module:** `backend/sleeper_http.py` (platforms-eng's Sleeper module, pure, injectable clock and random):
  `check()` raises `SleeperRateLimited` while the circuit is open, **before any network call**;
  `record_429(retry_after)`; `record_success()`; `reset()` for tests.
- **Delay on the n-th consecutive 429:** `max(retry_after_s, uniform(b/2, b))` with `b = min(600, 2·2^(n−1))` s
  (equal jitter, never near zero), hard ceiling 3,600 s. `Retry-After` accepts delta-seconds or an HTTP date; an
  unparseable value counts as absent. Any success resets `n`.
- **One strike per throttling episode (QA P2 on #378, fixed 2026-10-25).** `record_429` adds a strike only if the
  circuit was closed when that 429 arrived (`now >= _open_until`, checked inside the lock).
  - A 429 from a read already in flight when it opened adds no strike and draws no new jittered delay. Those
    reads are the session-init request thread plus its daemons, or four gthread workers after E1.
  - It only extends the window when its own `Retry-After` ends later: `_open_until = max(_open_until, now +
    min(3600, Retry-After))`.
  - Before the fix, one burst of 3–4 throttled reads counted as 3–4 strikes. After 2–3 episodes the window sat at
    the 600 s cap, and every Sleeper session init, sign-in and league list 503'd while sends were blocked.
  - The 2/4/8 s progression still applies across separate episodes.
  - Pinned by `test_concurrent_429s_while_open_are_one_strike` (8 barrier-released 429s → 1 strike, the 1-strike
    window), `test_next_429_after_the_window_closed_is_strike_two` and
    `test_larger_retry_after_while_open_extends_without_a_strike`. Sabotage: the unconditional strike turns all
    three red (`assert 8 == 1`).
- **No in-line retries or sleeps.** A 429 on the request thread fails fast into B.3 step 3 (stale), because a sleep
  would hold the single worker. The daemon logs and stops its Sleeper segment for that init.
- **Per-process fan-out stop:** wired into `_sleeper_get` (`server.py:583`), so every caller inherits it, including
  the outlook fetch, the send path's live roster read, and the cron sweeps. The three modules that drive urllib
  directly call `check()` / `record_429()` too: `trade_block_service.py:65,99`, `sleeper_trades_service.py:62`,
  `suggestion_telemetry.py:289`. One process today (`--workers 1`); with gthread (E1) the state is shared under a
  lock.
- **Circuit open on the send path:** the I-2 live roster read fails fast, and the send is blocked with "couldn't
  confirm rosters" (PRD R3). It is never sent unchecked.
- **Scope:** reads only. `sleeper_write.py` (GraphQL writes) is untouched.
- **Fixture mode** (`_SLEEPER_FIXTURES_DIR`) goes **through** the circuit (as built), so tests exercise the real
  path. A cassette may carry `"__headers__": {"Retry-After": "30"}` next to `"__http_error__": 429`
  (`server.py:611-612`). No checked-in cassette holds a 429, so the UI-test worlds are unaffected.
- **Never a clobber amplifier** (added in the build). `_fetch_sleeper_traded_picks` returns `None` on any failure,
  the open circuit included (R10, below), so `_sync_sleeper_owned_picks` keeps the prior snapshot instead of
  replace-syncing on a skipped read. `_refresh_league_draft_status` keeps the cached verdict while the circuit is
  open (`server.py:19224-19229` at `9d998886`). `_fetch_sleeper_drafts` keeps its documented D-089 fail-soft `[]`.
- **R10, fixed in PR-A (head-eng ruling, 2026-10-23).** It was a data-loss bug on `main`: a failed `traded_picks`
  read returned `[]`, and the owned-pick REPLACE-sync wrote that as "every traded pick is back with its original
  team".
  - Contract: the fetcher returns `None` on ANY failure (HTTP error, timeout, unparseable or non-list body, the
    open circuit, a non-Sleeper id), distinct from a successful `[]`.
  - Every caller treats `None` as an error. **The callers (all three):**
    - `server.py:14315` (`_sync_sleeper_owned_picks`): skips, keeping the stored picks.
    - `server.py:19601` (`_sleeper_propose_core`): used by `/api/trades/propose` **and** the overhaul send
      (`sleeper_propose=_sleeper_propose_core`, `server.py:33628`). A pick-bearing send refuses before any provider
      call.
    - `server.py:32080` (`/api/trades/validate`): returns nothing checked.
  - Other `traded_picks` readers don't use this fetcher, and none feeds a replace or a send on `[]`:
    - `overhaul_api.py:153` (`live_pick_owners`) is already `None` on failure;
    - `prepared_trade_cohort.py:299` raises `SourceUnavailable`;
    - `draft_board_service.py:309` is Draft Room display only.
- Only Sleeper-side status codes are logged (league ids are safe to log). No token is involved: these are public
  endpoints.

## C. Fingerprint contract

**Contract: `rfp1` per trades-eng v0 (head-eng accepted 2026-10-20).** It is not restated here. Source: trades-eng's
`trades-eng-roster-fingerprint-contract-draft.md` (v0), mirrored in `scope-eng-200ms.md` §6.1. In short:
`"rfp1:" + sha256(canonical)[:32]` over stored `league_members` (user_id → sorted player ids), `draft_picks`
(`pick_id`, `season`, `round`, `original_roster_id`, `owner_user_id`) and a `draft` object. It is computed only by
trades-eng's pure `roster_snapshot(conn, league_id)` in `backend/roster_snapshot.py`. **platforms-eng imports it
and never writes it.** The refresh provides contract §4: commit rows → compute → CAS-compare → hook (B.3 step 7).
Lineup/starters are excluded by construction (`league_members` holds `players`, never `starters`).

### C.1 platforms-eng's answer for the `draft` object (§2 "Open")

`"draft": {"drafted": leagues.draft_status == "drafted"}`, and nothing else.
- `DraftStatus.drafted` is `status == DRAFTED` (`backend/draft_status.py:150-152`), and confidence is unused.
- `sleeper_pick_window` consults the cached verdict only when `/drafts` is empty (`draft_status.py:190-219`).
- The live `/drafts` effect already reaches stored rows: the owned-pick sync excludes completed-draft seasons from
  `draft_picks` (D-189; `server.py:14336-14345`).
- **Excluded:** `draft_status_confidence`, `draft_status_checked_at`, `draft_slot_order`,
  `pick_assignment_settings`. They are labels and values, not tradability.

### C.2 Verified facts the contract relies on

| Question | Answer | Evidence |
|---|---|---|
| Does `league_members.roster_data` include reserve/IR and taxi players? | **Yes, for Sleeper.** It is Sleeper's roster `players` array, which is the full roster; `reserve` and `taxi` are subsets of it | `session_input.py:72` builds `player_ids` from `r["players"]`; the daemon writes them (`server.py:22792`, `:22799`); `_refresh_sleeper_members` docs it: "player_ids = every rostered id incl. taxi/IR" (`server.py:27238-27241`); the prepared reader keeps `players` and `reserve`/`taxi` side by side (`prepared_trade_cohort.py:308-310`). Read from code; not re-verified against live Sleeper (no network in this stage) |
| Does `league_members` include the caller's own row? | **Yes.** The daemon writes the caller's row first, keyed on the league identity `league_user_id`, then the opponents. Contrast G-063: `sess["league"].members` excludes the caller | `server.py:22772-22803`; table comment `database.py:623`; `session_input.py:88-90` drops the owner from `opponent_rosters`, which builds `sess["league"].members` (`server.py:22240-22256`) |
| Co-owners | **One row per roster**, keyed on the canonical `owner_id` (ADR-012), not two rows. Contract §2's "co-owners appear as two rows with the same roster" doesn't match current code; legacy pre-ADR-012 rows keyed on a co-owner's own id can survive as ghosts | `server.py:22782`; `sleeper_roster.py:12-25` |
| Ghost rows | Sleeper writes are **upsert-only**, so departed managers' rows persist (G-075). `asset_owner` can then map one player to two owners | `database.py:8345-8399` (no delete). Fixed by B.3 step 4's replace semantics |
| `"None"` strings | A G-004 null in `players` is stored as the string `"None"` | `session_input.py:72`, `server.py:27249`. Fixed at the writer (B.3 step 1) |
| Pick column types | `season` and `round` are `Integer` (`database.py:1566-1567`) | The canonical form must `str()` them, as the contract's "every id as a string" implies (§Q3) |

### C.3 Worked examples (canonical form as v0 specifies, with B.3's null filter; for test fixtures only)

```
members  = U_A: [4046, 6794, 8150], U_B: [9509, 4984]
picks    = [L1_2027_1_1, 2027, 1, "1", U_A], [L1_2027_1_2, 2027, 1, "2", U_B];  draft = {"drafted": false}
canonical: {"draft":{"drafted":false},"members":[["U_A",["4046","6794","8150"]],["U_B",["4984","9509"]]],
            "picks":[["L1_2027_1_1","2027","1","1","U_A"],["L1_2027_1_2","2027","1","2","U_B"]],"v":1}
```

| Case | rfp1 |
|---|---|
| Base | `rfp1:4eb70a85df1cdb51822e08714edadd93` |
| Same rows, members and player ids in a different order | `rfp1:4eb70a85df1cdb51822e08714edadd93` (same) |
| A null entry in U_A's players (filtered) | `rfp1:4eb70a85df1cdb51822e08714edadd93` (same) |
| U_A drops 8150, adds 11632 | `rfp1:fdaba6f4dba4e33a9de8a7ffbf6aa7d7` (differs) |
| Draft flips to drafted | `rfp1:340dd2cf95924f1ddd1442e49f04c14d` (differs) |
| Hazard: the null stored as `"None"` (today's writer) | `rfp1:28ceeea96e004c1a961020490051de4c` (spurious change) |
| Hazard: `season`/`round` left as ints | `rfp1:4ad0372ce41b0688d08e948b328ccc5a` (differs from the base: types must be pinned) |

A starters-only change (a lineup move) never reaches `league_members`, so it can't change `rfp1`.

## 1. Analytics scope

- [x] **(b) Existing signals cover it.** Every Sleeper GET, including 429s with their status, is already an
  `api_events` row via `observe_call` (`api_observability.py:254-291`). A circuit-open skip makes no call, so it
  writes no row; it logs one warning per open period. The refresh outcome is durable in `league_roster_state`. No
  new events, so no analytics-lead grant is needed.

## 2. Schema and flag scope

- **New table:** `league_roster_state` (B.2). **Granted** by head-eng, 2026-10-20. Same PR: `docs/data-dictionary.md`.
  Created by `metadata.create_all`, so it's additive. Account deletion: not user-scoped (league-keyed, no
  `user_id`), so no `accounts.py` registration.
- **Behavior change, no schema:** Sleeper `league_members` writes move from upsert to replace (B.3 step 4). It is
  user-visible: departed managers drop out of member lists. It needs head-eng's sign-off as the fix for G-075's
  ghosts (§Q6).
- **Flags:** none. Rollback is a code revert. The circuit's constants are module constants, not `model_config`
  knobs (simplicity first). If head-eng wants a deploy-free lever, the candidate is one knob for the 600 s soft cap.
- **Env vars:** none.

## 3. Evidence scope (D-056)

- [x] **Structural guard:** none. No mobile change.
- [x] **Backend pytest, PR-A (built).** 34 + 14 new tests, 5 in the updated budget file. The new files use the
  shipped `FTF_SLEEPER_FIXTURES_DIR` cassette seam, fake openers and an injected clock. No network.

  | File | Tests | Pins |
  |---|---|---|
  | `backend/tests/test_sleeper_backoff.py` (new, 37; +3 for QA P2: `test_concurrent_429s_while_open_are_one_strike`, `test_next_429_after_the_window_closed_is_strike_two`, `test_larger_retry_after_while_open_extends_without_a_strike`) | `test_429_with_retry_after_seconds_opens_for_at_least_that`, `test_429_with_http_date_retry_after`, `test_unusable_retry_after_falls_back_to_backoff[×4]`, `test_429_without_retry_after_backs_off_exponentially`, `test_jitter_stays_inside_equal_jitter_bounds`, `test_soft_cap_and_hard_ceiling`, `test_fail_fast_while_open_and_recovery`, `test_rate_limited_is_a_urlerror`, `test_classify[×10]`, `test_sleeper_get_429_cassette_opens_the_shared_circuit`, `test_sleeper_get_success_resets_strikes`, `test_direct_fetchers_fail_fast_while_open[×4]`, `test_direct_fetchers_open_the_circuit_on_429[×4]`, `test_owned_pick_sync_keeps_prior_snapshot_while_open`, `test_owned_pick_sync_429_on_traded_picks_itself_is_not_written`, `test_draft_status_not_written_while_open` | The rule: Retry-After as seconds or HTTP date; 2, 4, 8 … s; equal-jitter bounds over 14 strike levels; 600 s soft cap; 3,600 s ceiling; fail fast with **zero reads** (not even a fixture read); recovery resets strikes. Shared by `_sleeper_get` and all four urllib-direct readers. The pick replace-sync and the draft-status write skip while open |
  | `backend/tests/test_roster_refresh_state.py` (new, 14) | `test_success_marks_fresh_and_never_stores_none_ids`, `test_failure_with_no_prior_rows_is_stale_never_missing`, `test_failure_after_success_keeps_rows_and_marks_stale`, `test_failure_with_pre_s0_rows_is_stale`, `test_429_marks_rate_limited_and_the_next_init_makes_no_read`, `test_recovery_after_failure_clears_the_error`, `test_throttled_pick_read_marks_picks_unavailable`, `test_membership_refusal_is_not_a_refresh_failure`, `test_refreshed_at_only_moves_forward`, `test_failure_keeps_fp_and_refreshed_at`, `test_failure_on_a_never_seen_league_is_stale`; replace commit: `test_session_init_replaces_sleeper_members_dropping_ghosts`, `test_replace_refuses_an_empty_snapshot`, `test_platform_league_rows_are_not_replaced_by_session_init` | Success → `fresh`. Failure → rows byte-identical; `stale` / `missing` + the classified code (`http_5xx`, `invalid_payload`, `rate_limited`, `picks_unavailable`). The 503 body is unchanged. A 403 membership refusal writes nothing. G-004: a null slot is never stored as `"None"`. Meta-cache seed. `refreshed_at` never rewinds and `roster_fp` is never touched. Replace drops a ghost and refuses an empty snapshot (G-015); platform leagues are untouched |
  | `backend/tests/test_session_init_sleeper_calls.py` (updated, 5) | `test_daemon_makes_one_rosters_and_one_meta_call` (now rosters 1, meta 1, users 1, traded_picks 1, drafts 1, transactions ≤ 2, GraphQL 1, **sum ≤ 8**, state `fresh`); `test_numeric_mfl_league_makes_no_sleeper_calls_on_s0_paths` (new) | The D-178 budget after S0. A numeric MFL id makes no rosters/users/meta/picks/GraphQL call and gets no state row. Its `transactions` read is the pre-existing trade-capture `isdigit()` leak (R8), asserted as the only allowed key so a later fix still passes |
  | `backend/tests/test_co_owner_rosters.py` (updated in the replace commit) | The capture also intercepts `replace_league_members_snapshot` | One row per roster, still keyed on the primary owner |

  | `backend/tests/test_traded_picks_unavailable.py` (new, 11; R10) | `test_fetcher_none_on_failure_and_list_on_success`, `test_drafts_fetcher_keeps_its_fail_soft_empty_list`, `test_owned_pick_sync_failure_keeps_existing_picks[5xx\|timeout\|circuit_open]`, `test_successful_empty_traded_picks_still_replace_syncs`, `test_session_init_traded_picks_5xx_keeps_picks_and_marks_stale`, `test_propose_with_picks_and_failed_fetch_refuses_before_graphql`, `test_propose_without_picks_is_unaffected`, `test_validate_with_picks_and_failed_fetch_reports_nothing_checked`, `test_validate_without_picks_is_unaffected` | A failure keeps `draft_picks` byte-identical: a 5xx, a timeout and an open circuit, directly and through session init (state `stale` / `picks_unavailable`). A successful `[]` still replace-syncs (the traded pick returns to its original team). Propose with picks → 502 `sleeper_write_failed` / `kind: "network"`, `detail == message`, **GraphQL propose never called**. Validate → `{"ok": true, "checked": false, "warnings": []}`, never a false `pick_moved`. Sends and validates without picks never make the read. `drafts` stays fail-soft `[]`. **Sabotage-proven:** with the three `None` guards disabled, 6 of the 11 fail |

  **R10 code-walk (the `None` path, file:line at the R10 commit):**
  1. `_fetch_sleeper_traded_picks` (`server.py:17149-17173`) returns `None` for a non-Sleeper id (`:17166-17167`),
     any exception from `_sleeper_get` (an HTTP error, a timeout, or `SleeperRateLimited` while the circuit is
     open; `:17168-17172`, logging the exception type only) and a non-list body (`:17173`).
  2. **Owned-pick sync:** `_tp` (`:14315`) → `if _tp is None` (`:14323-14329`) returns `None` before `/drafts`,
     the slot-order write or `sync_draft_picks`, so `draft_picks` is untouched. In session init that sets
     `_s0_picks_ok = False` (`:22962`) → `record_outcome` → `stale` / `picks_unavailable`.
  3. **Propose / overhaul send:** in `_sleeper_propose_core`, only on a pick-bearing send (`:19595`), `traded`
     (`:19601`) → `if traded is None` (`:19602-19609`) returns the existing 502 body before the window reads and
     before `_sleeper_write.propose_trade`. The overhaul send reaches the same lines through
     `sleeper_propose=_sleeper_propose_core` (`:33628`).
  4. **Validate:** `traded` (`:32080`) → `if traded is None` (`:32081-32085`) returns the existing unreachable outcome
     (`checked: false`), the same body the route already returns when meta/rosters can't be read.
  - **Docs:** `docs/integrations/sleeper.md` §4 gains the `traded_picks` row; §4.1 is reworded.
  - **Owed to `docs/api-reference.md`** (head-eng reviews; not edited here), on the propose 502 row, append: "Also
    returned, before any provider call, when a pick-bearing send's live `traded_picks` read fails (`kind:
    "network"`, nothing sent; S0/R10)." On the validate row, append to "`checked:false` = platform data
    unreachable": "including a pick-bearing validate whose `traded_picks` read fails."

  | `backend/tests/test_roster_refresh_async.py` (new, 19; Stage D / P41 + retry cooldown + meta TTL) | `test_concurrent_callers_start_exactly_one_refresh`, `test_fresh_enough_league_starts_none`, `test_no_row_starts_one`, `test_null_refreshed_at_starts_one`, `test_stale_past_the_bound_starts_one`, `test_linked_platform_league_starts_none`, `test_open_circuit_starts_none`, `test_success_writes_fresh_and_advances_refreshed_at`, `test_picks_failure_writes_stale_picks_unavailable`, `test_read_exception_writes_stale_and_thread_does_not_raise`, `test_unexpected_crash_never_escapes_and_clears_inflight`, `test_league_leaves_inflight_after_success_and_failure`, cooldown: `test_stale_league_inside_retry_cooldown_starts_none` (10 s ago → none), `test_stale_league_past_retry_cooldown_starts_one` (61 s ago → one), `test_fresh_but_past_bound_league_ignores_the_cooldown`, `test_unparseable_updated_at_never_blocks`, `test_no_sleeper_read_or_write_under_the_module_lock`, `test_reads_per_kick_meta_cached_vs_miss`, `test_stale_meta_cache_entry_is_refetched_once_fresh_one_is_not` | Single-flight: 8 barrier-released callers → `sum(returns) == 1` and one refresh. The no-op set (fresh, platform, demo id, open circuit, in flight); NULL or no row starts one. `fresh` advances `refreshed_at`, with G-004-filtered rows. `stale`/`picks_unavailable`; `stale`/`http_5xx` with no thread exception (excepthook captured). The in-flight set always empties. No Sleeper stub runs while the module lock is held by the calling thread (owner-tracking lock). 1+1(+0/1 meta) reads per kick plus the pick sync's 2. **Sabotage:** with the in-flight check removed, `test_concurrent_callers_start_exactly_one_refresh` fails `assert 8 == 1`; restored byte-identical. Five repeat runs: 14/14 each |

  **Moved out of PR-A:**
  - `test_tap_path_no_sleeper.py` (the AC-L3 guard) needs B.4's switches, which are trades-eng's S0-serve (§Q7).
  - The fingerprint and hook cases go to PR-B.

  **PR-B (built 2026-10-27, branch `feat/s0-roster-fp-stamp`):**

  | File | Tests | Pins |
  |---|---|---|
  | `backend/tests/test_roster_fp_stamp.py` (new, 17) | `test_first_stamp_writes_rfp1_and_calls_the_hook_with_old_none`, `test_changed_roster_calls_the_hook_with_old_and_new`, `test_unchanged_roster_stamps_nothing_and_makes_no_call`, `test_lost_cas_makes_no_hook_call[first_stamp\|restamp]`, `test_stamp_without_a_state_row_writes_nothing`, `test_handler_exception_is_swallowed_and_logged`, `test_hook_raising_never_escapes_the_refresh`, `test_failed_refresh_does_not_stamp[members\|picks]`, `test_failed_read_and_failed_state_write_do_not_stamp`, `test_failed_kick_read_does_not_stamp`, `test_fp_error_keeps_the_stored_fp_and_the_fresh_outcome[fingerprint\|pick_source]`, `test_linked_platform_league_is_never_refreshed_so_never_stamped`, `test_a3_hook_runs_unlocked_outside_any_transaction_on_the_kick_thread`, `test_session_init_stamps_and_hooks_on_its_daemon_thread` | The first stamp is `rfp1:` + 32 hex, equal to the serve's `_trade_roster_snapshot(lid).fp`, computed with `server._pick_read_source()`; hook `(lid, None, fp)`. A change hooks `(old, new)`; no change makes no CAS and no `on_roster_change` call at all. A rival stamp between the read and the CAS keeps the rival's value, and no hook fires. Handler and hook exceptions are logged and the outcome stays `fresh`. A failed refresh, a failed state write, an fp error and a linked-platform league never stamp. **A3**, on a file-backed SQLite (QueuePool), inside the handler: `pool.checkedout() == 0`, `_inflight_lock` and `roster_snapshot._lock` both acquire non-blocking, and a second connection inserts and commits. The thread is `roster-refresh-<id>` (kick) or `session-init-bg-writes` (session init, a real thread the request joins), never the request thread |
  | `backend/tests/test_roster_refresh_state.py` (1 assertion) | `test_success_marks_fresh_and_never_stores_none_ids` | `roster_fp` is now `rfp1:…` after a session-init success (it was pinned NULL until PR-B) |

  **Sabotage, each red then restored byte-identical:**
  1. The hook inside the CAS transaction (CAS inlined in `stamp`, hook before commit) → the A3 test fails on
     `checked_out: 1` and on the second connection's write (`OperationalError`, database locked).
  2. The hook under `_inflight_lock` → the A3 test fails on `inflight_lock: False`.
  3. The CAS condition dropped (`WHERE league_id` only) → both `test_lost_cas_makes_no_hook_call` cases fail:
     the rival's value is overwritten.
  4. The `new == old` early return dropped → `test_unchanged_roster_stamps_nothing_and_makes_no_call` fails: one
     `on_roster_change` call. (The spy replaces `on_roster_change` itself, because that function drops equal fps
     before any handler, so a handler-level spy would stay green.)

  **PR-B suites:** the targeted set (the new file plus `test_roster_refresh_state`, `test_roster_refresh_async`,
  `test_roster_snapshot`, `test_trade_freshness_roster`, `test_traded_picks_unavailable`,
  `test_session_init_sleeper_calls`, `test_trade_roster_floor_kick`, `test_server_module_shape`,
  `test_co_owner_rosters`, `test_i1_serve_filter`, `test_trade_page_store`, `test_trade_pages_p2`,
  `test_trade_fingerprint_reads_unlocked`, `test_sleeper_backoff`): **493 passed**. Full suite
  (`python3 -m pytest backend/tests -q`, local Python 3.14): **9208 passed, 2 skipped, 0 failed**, exit 0, 35m37s.
- [x] **Full suite:** `python3 -m pytest backend/tests -q` on `build/s0-roster-refresh`. Local Python 3.14.4 (CI is
  3.12.3). After the circuit + state commits: **7763 passed, 1 skipped**, exit 0, 882 s. After the replace commit
  (`9d998886`): **7766 passed, 1 skipped**, exit 0, 691 s. Stage C, after R10 (`2a05ca80`) and fresh|stale-only
  (`6a281855`): **7777 passed, 1 skipped**, exit 0, 636 s (+11 R10 tests). The targeted suites (owned picks,
  propose, validate, pick tradability, overhaul API/service, pick assignment, MFL propose, session-init calls,
  S0) gave 271 passed before the v0.3 change; the four S0 files gave 64 passed after it. The SQLite "no such table" lines in the log are
  pre-existing fail-soft logging from other tests' in-memory engines, not failures.
- [x] **Code-walk proof** (file:line at `build/s0-roster-refresh` HEAD):
  1. **Trigger:** cold launch `mobile/App.tsx:115-117` and foreground `:199-210` → `useSession.revalidateSession`
     (`useSession.ts:357-378`, throttle `:65` / `leagueSession.ts:81`) → `POST /api/session/init`.
  2. **Request thread:** `server.session_init` creates `_s0_raw` (`server.py:22198`) and calls
     `resolve_session_input(…, raw=_s0_raw)` (`:22200`).
     - Platform leagues branch first on `db.is_linked_platform_league` (`session_input.py:48`) and never reach Sleeper.
     - Sleeper: `fetch_started_at()` is captured (`session_input.py:61-62`), then 3 reads, each through
       `_sleeper_get` → `sleeper_http.guard` (`server.py:585-594`; guard `sleeper_http.py:150-163`).
  3. **Success:** members are built with nulls dropped (`session_input.py:76-83`), and the raw rosters/meta/start
     time are handed back (`:87-88`).
     - The meta seeds `_FA_LEAGUE_META_CACHE` (`server.py:22204-22207`).
     - The daemon reuses meta (`:22613`) and rosters (`:22877`) instead of re-reading.
     - It writes members: Sleeper `replace_league_members_snapshot` (`:22839-22844`, `database.py:8523`); platform
       leagues upsert (`:22845-22847`). Then picks (`:22895-22946`, sets `_s0_picks_ok`) and draft status
       (`:22956`).
     - Then `roster_refresh.record_outcome` (`server.py:22960-22964` → `roster_refresh.py:48-67`) →
       `mark_league_roster_fresh` (`database.py:8467`): `status='fresh'`, `refreshed_at` = fetch start, error
       cleared.
  4. **Failure → stale:** any non-membership exception in the read (`session_input.py:91`) →
     `record_failure(lid, exc)` (`:92` → `roster_refresh.py:41-55`) → `sleeper_http.classify` →
     `mark_league_roster_failed` (`database.py:8500`).
     - That always writes `status='stale'` + `last_error_code`, keeping `roster_fp` and `refreshed_at` (contract
       v0.3: the state row holds `fresh` | `stale` only). "Missing" is derived by `roster_snapshot` from absent
       `league_members` rows, never stored.
     - The response is the unchanged `503 league_data_unavailable` (`session_input.py:93`).
     - `league_members` and `draft_picks` are never written on this path: the daemon doesn't start
       (`server.session_init` returns at `:22201-22202`).
  5. **Never refreshed:** since v0.3 the same path on a league with no state row and no `league_members` rows
     still writes `status='stale'` (`mark_league_roster_failed`, `database.py`), with `refreshed_at` NULL. "Missing"
     is derived by the reader from the absent member rows.
     - A daemon whose members write or pick sync failed writes `stale` with `write_failed` or
       `picks_unavailable` (`roster_refresh.py:56-59`). `refreshed_at` does not move.
  6. **Circuit open:** a Sleeper 429 anywhere → `guard` → `record_429` (`sleeper_http.py:118-129`) opens the
     window.
     - Every later read in the process raises `SleeperRateLimited` from `check()` (`sleeper_http.py:80-86`)
       before any I/O.
     - In session init that lands at step 4 with `last_error_code='rate_limited'`. In the daemon it reaches the
       pick sync, whose `traded_picks` read returns `None` (`server.py:14323`) → `picks_unavailable`, and draft status keeps its
       verdict (`server.py:19224-19229`).
     - The urllib-direct readers share it: `trade_block_service.py:87,111`, `sleeper_trades_service.py:80`,
       `suggestion_telemetry.py:300`.
- [ ] **Manual TestFlight checklist** (operator; in an operator-named test league only, because steps 2–3 change a
  real roster):
  1. Cold-open the app on a Sleeper league, tap Find a trade → a card shows. Note one player on your roster.
  2. In the Sleeper app, drop that player (your own action). Background FTF for 70 s (past the 60 s throttle),
     then foreground. Within about 10 s, tap Find a trade → **no card offers the dropped player**. A card already
     showing it is withdrawn in place with a reason.
  3. Have a leaguemate (or the commissioner) move one of their players. Background for 70 s, foreground, tap →
     no card asks for that player.
  4. Turn on Airplane Mode, foreground, tap → cards from stored rosters with the refresh-failed state. Nothing
     crashes, and nothing is sent.
  5. Open an MFL or ESPN league, tap Find a trade → a card shows; no Sleeper error anywhere.
  6. Switch leagues and back. Each league's deck shows only its own rosters.
  - Expected for each: the result as stated. Any card containing a moved asset is a fail.
- testIDs: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a in v1** | No route added and no contract changed. The 503 is unchanged. If C (the device page) needs `roster_fp` on the session-init response, that's a proposed additive field (§Q9) and gets a row then |
| `docs/data-dictionary.md` | **Updated (PR-A, PR-B)** | New `league_roster_state` section + TOC row; the `league_members.roster_data` note (reserve/IR + taxi included, nulls dropped). The replace commit adds the "Sleeper leagues are replace-synced" sentence to the `league_members` intro. PR-B: the `roster_fp` row says it is stamped (`rfp1`, CAS) and the section intro names `cas_league_roster_fp` |
| `docs/integrations/sleeper.md` | **Updated (PR-A)** | §4: the G-004 row and a new 429 row; new §4.1 (the circuit: rule, fail fast, no retries, never a clobber amplifier, fixture `__headers__`, log line); §5.2 hand-down and the **≤ 8 / ≤ 7** per-init budget; §6.1 safe-to-log (window, strikes, league id, status 429; `league_roster_state` enums) |
| `docs/runbook.md` | **Updated (PR-A)** | New "Sleeper 429 / circuit open (S0, 2026-10-20)" + TOC row |
| `docs/architecture.md` | **Updated (PR-B)**: the "Roster refresh and fingerprint stamp (S0)" paragraph under Data flow, which carries the PR-A text below plus the stamp → CAS → hook flow. Was: **Owed (head-eng owns; not edited per the Stage B rules)** | Exact text to add under the session-init data flow: "**Roster refresh (S0).** Session init's authoritative Sleeper read (rosters, users, league meta; `session_input.resolve_session_input`) is the league's roster refresh. Its rosters and meta are handed to the background daemon (no second read) and the meta seeds `_FA_LEAGUE_META_CACHE`. The daemon replace-syncs Sleeper `league_members`, syncs owned picks and draft state, then `roster_refresh.record_outcome` writes `league_roster_state` (`fresh`). A failed read writes `stale` + `last_error_code` and never touches the rows: the state row holds only `fresh` \| `stale`, and "missing" (no cards) is derived by trades-eng's `roster_snapshot` from absent `league_members` rows (fingerprint contract v0.3 §3). `roster_refresh.maybe_refresh_async` re-runs the same Sleeper segment as a single-flight background kick when a league is past the roster bound (P41). Every server-side Sleeper read passes one per-process 429 circuit (`backend/sleeper_http.py`): one strike per throttling episode, fail fast while open, no in-line retries." |
| `living-memory/LLD.md` | **Owed (living-memory is not edited here)** | Exact invariants to add: "(1) Every server-side Sleeper read goes through `sleeper_http.guard` (directly or via `_sleeper_get`); no in-line retries or sleeps. (2) A replace-style writer fed by a fail-soft Sleeper read skips while `sleeper_http.is_open()`. (3) Session init reads Sleeper rosters and meta once; daemon consumers take the handed payload. (4) `league_roster_state` is written only via `roster_refresh`; a failure never writes `league_members` or `draft_picks`. (5) `league_members` writers drop null/empty player ids (G-004). (6) Sleeper `league_members` is replace-synced from the authoritative snapshot; an empty snapshot is refused (G-015)." |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` | **Owed at merge (release-lead's scribe)** | CHANGELOG: "S0 PR-A: Sleeper 429 circuit; `league_roster_state`; per-init Sleeper budget ≤ 10 → ≤ 8; Sleeper `league_members` replace-synced." TEST_LEDGER: the §3 tests and the full-suite counts |
| `living-memory/HLD.md` | n/a | No new client, service or major flow. The refresh rides session init |
| `docs/cross-client-invariants.md` | n/a | Server-only; no shared constant |
| `docs/glossary.md` | n/a here | trades-eng adds "roster fingerprint"; "Sleeper circuit" goes in `integrations/sleeper.md` |
| `docs/runbook.md` | **Yes** | "Sleeper 429 / circuit open": the symptom, the log line, what clears it, and that sends block meanwhile |
| ADR / `DECISIONS.md` | **Owed (head-eng)** | One D-entry. Title: "Sleeper reads share one per-process 429 circuit; session init's Sleeper read is the roster refresh, recorded in `league_roster_state`; Sleeper `league_members` is replace-synced". Alternatives considered: in-line retries (rejected: they hold the single worker), a per-endpoint circuit (rejected: the limit is per IP), upsert with ghost cleanup by age (rejected: the authoritative snapshot is complete) |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (with the `check-*.js` suites), `maestro-testid-lint`.
- **Evidence:** the §3 tests and the code-walk, logged in `living-memory/TEST_LEDGER.md` at merge (release-lead's
  scribe). The checklist is run by the operator on the launch binary. S0-fetch needs no new binary; the
  checklist exercises it through the server.
- **Express lane:** no.
- **Landing order (recommended): sequential, not one coordinated PR.** `roster_snapshot.py` and the hook registry
  don't exist on `main`, and trades-eng's snapshot reads `league_roster_state` (contract §3, `refreshed_at` and
  `status`). So:
  1. **PR-A (platforms-eng, no dependency): BUILT** on `build/s0-roster-refresh`, not pushed. Three commits:
     - the `sleeper_http` circuit (plus the two clobber guards);
     - `league_roster_state` + the hand-down (budget ≤ 10 → ≤ 8) + the meta-cache seed + null filtering +
       `fresh`/`stale` writes (no stored `missing` since contract v0.3);
     - **replace semantics, its own commit**, droppable with one `git revert` pending head-eng's sign-off.
     - The session-init diff is ~25 lines in `server.py` (`:22198-22207`, `:22613`, `:22805`, `:22839-22847`,
       `:22877`, `:22944-22946`, `:22958-22964`). engagement-eng (O8) edits the same region.
  2. **S0-serve (trades-eng):** `roster_snapshot`, the hook registry, freshness, I-1, and the B.4 switches.
  3. **PR-B (platforms-eng, small): BUILT 2026-10-27** on `feat/s0-roster-fp-stamp`, cut from `origin/main`
     after S0-serve landed. Step 7: compute fp → CAS → `on_roster_change` (B.3, "As built"), tests in the new
     `test_roster_fp_stamp.py`. **Not in it:** the B.6 stamps on the other platforms-eng-owned writers (a
     follow-up, scoped out by platforms-eng's brief). No API, schema, flag or analytics change.
  - All three are built in parallel. PR-B is rebased on S0-serve right before merge. One coordinated PR would
    double the review surface in `server.py`'s session-init region, which engagement-eng (O8) is also editing.

## R. Risks

- **R1, Sleeper Terms (E2, still open with legal-lead):** S0 adds no scheduled or headless read. Every refresh is
  triggered by app open, foreground or a tap (R7). The per-init budget falls by 2. The hourly draft-status tick
  (`server.py:24573`) is today's pattern and unchanged.
- **R2, replace semantics are visible:** departed managers vanish from member lists, `league_member_joined` peer
  lookups (`server.py:22686`) and League Summary. That's correct, but it's a change. The non-empty guard prevents
  G-015's wipe.
- **R3, the single worker:** the request thread's 3 reads (15 s timeout each) still run at app open and
  foreground, and a tap queues behind them until E1. Cutting their timeout to 5 s is cheap now that failure is
  handled (it needs onboarding-eng's review).
- **R4, circuit blast radius:** while the circuit is open, every Sleeper read fails fast, sends included (blocked
  with "couldn't confirm rosters"). Session init 503s, so the client keeps its token and existing session.
- **R5, value-core standings fan-out:** 3 live GETs per value-core job (`server.py:7478-7490`). If P1 builds on the
  value core and `on_roster_change` rebuilds every member's pages, a 12-team league could make ~36 GETs per roster
  change. That breaks "net calls must not rise" unless standings come from a cache or store (§Q10).
- **R6, the daemon lag window:** a tap in the 1–3 s between the session-init response and the stamp reads the
  previous rows. The snapshot is consistent and I-1 holds against what's stored; the hook then withdraws in place
  (U2).
- **R7, a stale meta cache on restart:** it's empty until the next session init, and every restart forces one,
  because sessions are in-memory. A background build for another league member with a cold cache still fetches
  meta, off the tap path.
- **R9, members-write race (residual, PR-A):** two concurrent inits for one league can commit their
  `league_members` snapshots out of fetch order. Only `refreshed_at` is monotonic. The next init corrects it
  (B.3 step 4). onboarding-eng's advisory A2 (2026-10-24) covers the same case for two different members' inits:
  last write wins, and it's harmless because both are authoritative reads seconds apart. F5's single-flight (#355)
  is per token, so it doesn't serialize across members. Accepted; no lock added.
- **R11, the meta-cache seed is a bare dict write** (onboarding-eng advisory A1, 2026-10-24): `_FA_LEAGUE_META_CACHE`
  has no lock. Its other writers (`server.py:29222`, `:30437` on this branch) are bare `dict` assignments too, which
  are atomic under the GIL, so the S0 seed (`:22225`) matches the cache's existing pattern. No change.
- **R10, a pick clobber on non-429 flakes: FIXED in PR-A** (2026-10-23, B.7). The validate side uses the existing
  `checked: false` outcome rather than a blocking warning, because no existing validate warning code says "pick
  ownership couldn't be confirmed" (`pick_moved` would be a false claim). A blocking warning needs a new code,
  which is an API contract change, so it's left to the coordinator / head-eng. The send itself is hard-refused by
  propose either way.
- **R8, an existing G-030 trap, observed and not fixed here:** the trade-capture gate at `server.py:22918` uses a
  bare `isdigit()`, so an MFL numeric id reaches the Sleeper transactions sweep. It's out of S0 scope; flagged to
  head-eng.

## Q. Open questions

> **Status 2026-10-24:** trades-eng answered all of these on 2026-10-23, and they're folded into fingerprint contract
> v0.3 (head-eng's notes folder). The landing order is E2 → S0-serve → PR-A (the snapshot tolerates an absent
> table). Q7's trade-path fetches stay in background jobs for launch, and switching them goes to models-eng.
> Q9 (C) needs no session-init field. Q10 is moot while `trade.value_core` is off. onboarding-eng approved the
> session-init diff on 2026-10-24 (A1/A2 → R9, R11; A3 is a positional rebase only).

**For trades-eng:**

1. **Hook registry:** where does `on_roster_change` register (in `roster_snapshot.py`?), and is a synchronous call
   from the session-init daemon thread acceptable, given you debounce? Is `old_fp=None` on the first-ever stamp
   acceptable?
2. **Status semantics:** `fresh` = the last attempt committed members **and** picks; the ≤ 5 min bound is yours,
   from `refreshed_at`. Agreed? Should a picks-only read failure mark the league `stale` (my draft), or should
   `refreshed_at` track members alone?
3. **Pin the types in the canonical form:** `str()` on all five pick fields (`season` and `round` are `Integer`,
   `database.py:1566-1567`). Also drop `None` / `""` / `"None"` player ids inside `roster_snapshot` as defense in
   depth. C.3 shows both hazards change the fp.
4. **The `draft_picks` row set:** all sources (platform and ADR-010 user-asserted), or `_pick_read_source()` only?
   It must be exactly the set the I-1 filter reads.
5. **Contract §2's co-owner line:** current code writes one row per roster (`server.py:22782`), not two. OK to
   correct the text?
6. **Replace semantics** for Sleeper `league_members` (B.3 step 4): do you agree they're required, so that
   `asset_owner` is single-valued (ghosts, G-075)? head-eng signs off on the visible change.
7. **`_build_trade_roster_context`'s live `/rosters` GET** (`server.py:5846-5847`) and the lineup-meta fetch on the
   trade paths (`:5837`, `:7513`, `:8891`) sit in your region. Do you switch them in S0-serve (B.4), or does
   head-eng grant me those lines? I'll supply the no-fetch meta accessor either way.
8. **PRD §5.2 exception 1** (viewer roster past the 5-min bound → refetch before display) conflicts with AC-L3.
   Will you use `maybe_refresh_async` (B.1) with withdraw-in-place, and take the PRD amendment to trades-pm?
9. **Does C (the device page) need `roster_fp` on the session-init response?** If yes, I'll propose the additive
   field (an API change, so a head-eng grant).
10. **Value-core standings reads** (R5): who makes them cached or stored before P1 builds on the value core?
11. **Non-Sleeper writers** (B.6): I'll stamp the ESPN/MFL/Fleaflicker import routes, the MFL pick normalizer, the
    draft-status refresh and `_refresh_sleeper_members`. The ADR-010 pick-assignment and recorded-picks routes
    (`server.py:17787, 17902, 17993`) are yours or the draft owner's. Do you want them stamping?
12. **Landing order:** PR-A → S0-serve → PR-B (§5). OK?

**For head-eng and onboarding-eng:**

- **Q-ONB, never block the tap across a restart:** today a Sleeper failure at session init returns 503
  (`session_input.py:79-80`). If the server restarted, the client has no live session, so the tap fails. A fallback
  would accept stored membership on **transient** failures only: the caller's canonical row exists, the league's
  last `fresh` stamp is under N days old, and the caller is a sole owner (co-owners can't be verified without
  `co_owners`, so they still get 503). That widens the authoritative-membership rule, so it's not in v1 unless
  onboarding-eng and head-eng say so.
- **Q-ORDER:** `session_input.py` (returning the raw payloads, null filtering) is onboarding-eng's review area.
  Please route the PR-A review to them.
