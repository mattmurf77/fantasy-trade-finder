# Feature Scope — S0, fetch side: background roster refresh, Sleeper 429 backoff, roster-state stamp

**Date:** 2026-10-20 (Stage A draft: branch, read, design. No product code.)
**Entry point:** direct operator ask, 2026-10-20, relayed by the coordinator: "Yes building should resume on the
200 ms path." Brief: `docs/plans/org-bringup/briefs/build-platforms-eng-s0-sleeper.md` (head-eng), Piece 1.
Plan of record: `docs/plans/org-bringup/launch-readiness-eng.md` §3a, row S0.
**Builder:** platforms-eng (lead), `eng-backend` worker. Branch `build/s0-roster-refresh`, cut from `origin/main`
`678834ab` (2026-10-14 21:31 -0400). All file:line cites are at that sha.
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
- **Mid-session top-up (proposed hook for trades-eng, §Q8):** `roster_refresh.maybe_refresh_async(league_id,
  max_age_s=300)`. When the stored `refreshed_at` is older than the PRD's 5-min viewer bound, it starts one
  single-flight daemon refresh (rosters + owned-pick reads; meta from cache) and returns at once. trades-eng may call
  it from `/generate` or the page serve. It is user-triggered (R7-compliant), never awaited, so not on the tap path
  (AC-L3).

### B.2 What is stored, and where (schema granted by head-eng, 2026-10-20)

The rows are the existing fp inputs: `league_members`, `draft_picks`, `leagues.draft_status`. The refresh record is
a new table:

```
league_roster_state
  league_id        String  PK        -- platform-native id, same semantics as leagues.sleeper_league_id
  roster_fp        String  NULL      -- "rfp1:…" from roster_snapshot(...).fp after the last committed refresh
  refreshed_at     String  NULL      -- ISO UTC: start time of the fetch whose rows are committed
  status           String  NOT NULL  -- 'fresh' | 'stale' | 'missing'
  last_error_code  String  NULL      -- see below; NULL after a success
  updated_at       String  NOT NULL
```

- **`status`** describes the last attempt, not the PRD bound. `fresh` = the last attempt committed members and
  picks. `stale` = the last attempt failed, and the last good rows are kept. `missing` = never refreshed under S0
  (no row, or no success yet). The ≤ 5 min bound is trades-eng's, computed from `refreshed_at` (§Q2).
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
   untouched, `roster_fp` and `refreshed_at` kept, `missing` if there was no prior success), then return today's
   503 `league_data_unavailable`. Session-init behavior is otherwise unchanged in v1. The mobile client keeps its
   token and its live server session, so taps keep working from stored state (§Q-ONB for the restart case).

**Daemon** (`_session_init_background_writes_impl`, `server.py:22552-22973`); order otherwise unchanged:

4. **Members:** write the authoritative members with **replace semantics** for Sleeper: delete then insert in one
   transaction (`replace_espn_league_members`, `database.py:13708-13738`, is already platform-agnostic), only when
   the payload is a valid non-empty list (G-015). It replaces the `upsert_league_members` call at `server.py:22804`,
   for Sleeper leagues only. **Monotonic guard:** skip the write when `league_roster_state.refreshed_at` is newer
   than this fetch's `fetch_started_at`, so a slow, older init can't overwrite a newer one.
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

The optional top-up (B.1) costs at most rosters + traded_picks + drafts (3) per league per 5 min, single-flight, and
only on user action.

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
- **Fixture mode** (`_SLEEPER_FIXTURES_DIR`, `server.py:586-598`) bypasses the circuit unless a test arms it.
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

- [ ] **Structural guard:** none. No mobile change.
- [ ] **Backend pytest:**

  | File | Pins |
  |---|---|
  | `test_sleeper_backoff.py` (new) | 429 with `Retry-After: 30` → circuit open ≥ 30 s and zero network calls while open (counting fake opener); HTTP-date `Retry-After`; no header → 2, 4, 8 … s within the equal-jitter bounds (seeded random, injected clock); 600 s soft cap, 3,600 s ceiling; success resets; a second caller during an open circuit makes zero calls; the three direct-urllib fetchers honor it; fixture mode bypasses it |
  | `test_roster_refresh_state.py` (new) | Success → `fresh`, `refreshed_at` = fetch start, `roster_fp` == `roster_snapshot(...).fp`. 429 / 5xx / timeout / invalid payload → `league_members` and `draft_picks` byte-identical, `stale` + the right `last_error_code`, `missing` with no prior success. Recovery clears the error. Unchanged fp → no hook. Changed fp → exactly one hook. Two racing stamps → final row consistent, ≥ 1 and ≤ 2 hook calls. A hook exception never escapes the daemon. Picks read failure → `stale` / `picks_unavailable`. The monotonic guard: an older fetch never overwrites a newer one. Replace semantics drop a ghost row and refuse an empty payload (G-015). A G-004 null is never stored as `"None"`. MFL numeric id → zero Sleeper calls, no Sleeper writer (G-014/G-030), and `refreshed_at` not advanced |
  | `test_session_init_sleeper_calls.py` (update) | `rosters == 1`, `meta == 1` (from 2 and 2); users, traded_picks, drafts, transactions unchanged; non-Sleeper still `{}`. New: a 429 on the request-thread rosters read → 503, `stale` state, and no further Sleeper call in that init |
  | `test_tap_path_no_sleeper.py` (new; AC-L3 guard, shared with trades-eng) | With `_sleeper_get` and the direct fetchers replaced by a raising fake: `/generate` (hit, join, kickoff + inline worker), `/status`, `fair-packages`, `asset-ideas`, with the roster flags **on**, make zero Sleeper calls once B.4's switches land. Meta is served from the seeded cache |
  | fp behavior through the refresh | Add/drop → fp changes; pick-only trade (a `traded_picks` change) → changes; starters-only change → unchanged; display-name change → unchanged. trades-eng's `test_roster_snapshot.py` owns the canonical-form tests |
- [ ] **Code-walk proof** (written in the build): app open / foreground (`App.tsx:115-117`, `:199-210`) →
  `revalidateSession` → `/api/session/init` → `resolve_session_input` (3 reads, circuit-guarded) → daemon members
  replace → picks → draft state → stamp/CAS → `on_roster_change`. Then the tap → `/generate` → worker →
  `deck_quality` meta from cache → zero Sleeper calls (AC-L3), file:line at the build sha.
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
| `docs/data-dictionary.md` | **Yes** | `league_roster_state`; the `league_members` note becomes "Sleeper: replace-synced per refresh" |
| `docs/integrations/sleeper.md` | **Yes** | The 429 circuit (delay rule, ceiling, fail-fast, no retries); the per-init call budget (≤ 8); safe-to-log (league id, status) / must-redact (none: public reads) |
| `docs/architecture.md` | **Yes** (head-eng reviews) | Session-init data flow: request-thread read → daemon members/picks/draft → stamp → `on_roster_change`; `sleeper_http` circuit |
| `living-memory/LLD.md` | **Yes** | Invariants: the tap path makes no Sleeper calls; fp inputs are committed, then stamped; Sleeper `league_members` is replace-synced; ids are filtered for nulls at the writer |
| `living-memory/HLD.md` | n/a | No new client, service or major flow. The refresh rides session init |
| `docs/cross-client-invariants.md` | n/a | Server-only; no shared constant |
| `docs/glossary.md` | n/a here | trades-eng adds "roster fingerprint"; "Sleeper circuit" goes in `integrations/sleeper.md` |
| `docs/runbook.md` | **Yes** | "Sleeper 429 / circuit open": the symptom, the log line, what clears it, and that sends block meanwhile |
| ADR / `DECISIONS.md` | **Yes** | One D-entry: the Sleeper 429 circuit plus replace-synced `league_members` (head-eng) |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (with the `check-*.js` suites), `maestro-testid-lint`.
- **Evidence:** the §3 tests and the code-walk, logged in `living-memory/TEST_LEDGER.md` at merge (release-lead's
  scribe). The checklist is run by the operator on the launch binary. S0-fetch needs no new binary; the
  checklist exercises it through the server.
- **Express lane:** no.
- **Landing order (recommended): sequential, not one coordinated PR.** `roster_snapshot.py` and the hook registry
  don't exist on `main`, and trades-eng's snapshot reads `league_roster_state` (contract §3, `refreshed_at` and
  `status`). So:
  1. **PR-A (platforms-eng, no dependency):** the `league_roster_state` table and data-dictionary row; the
     `sleeper_http` circuit; payload hand-down (budget 10 → 8); the meta-cache seed; null filtering; replace
     semantics; `stale`/`missing` + `last_error_code` writes. It can merge first.
  2. **S0-serve (trades-eng):** `roster_snapshot`, the hook registry, freshness, I-1, and the B.4 switches.
  3. **PR-B (platforms-eng, small):** step 7: compute fp → CAS → `on_roster_change`; the B.6 stamps on the
     platforms-eng-owned writers; `test_roster_refresh_state.py`'s hook cases.
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
- **R8, an existing G-030 trap, observed and not fixed here:** the trade-capture gate at `server.py:22918` uses a
  bare `isdigit()`, so an MFL numeric id reaches the Sleeper transactions sweep. It's out of S0 scope; flagged to
  head-eng.

## Q. Open questions

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
