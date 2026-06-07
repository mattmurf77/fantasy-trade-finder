# High-Level Design (HLD) — Performance-Optimized Data Fetch & Load

**Status:** proposed (audit output). **Scope:** the player + trade data fetch
and load path across mobile client, backend, and infra, updated to incorporate
the 16 optimization initiatives in [`../plan/optimization-plan.md`](../plan/optimization-plan.md).
This HLD describes the *target* architecture; per-initiative detail is in
[`lld.md`](./lld.md) and [`requirements/`](./requirements/).

---

## 1. System context

```
        ┌──────────────────────────────────────────────────────────────┐
        │                        Mobile App (RN/Expo)                   │
        │                                                              │
        │  Boot ──► RootNav gate ──► Tabs (Rank / Trades / Matches /   │
        │   │                         League / Tiers / Overall)        │
        │   │                                                          │
        │   ├─ Zustand stores (session, flags, …)  ◄─ AsyncStorage     │
        │   ├─ TanStack Query cache  ◄─ AsyncStorage persister  [NEW]  │
        │   └─ api/* wrapper (timeout, retry, prefetch)        [NEW]   │
        └───────────────┬──────────────────────────────────────────────┘
                        │ HTTPS (HTTP/2, gzip auto)
                        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │              Cloudflare edge (compression, caching)           │
        │       gzip/br  •  edge-cache players w/ ETag  [NEW]           │
        └───────────────┬──────────────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────────────────────────────┐
        │        Render web dyno — Flask + gunicorn (--workers 1*)      │
        │                                                              │
        │  before_request (throttled touch)  [CHANGED]                 │
        │  routes: session_init, trio, rankings, trades, sleeper/*     │
        │  in-mem caches: _sleeper_cache, universal pools, ELO memo [NEW]│
        │  services: RankingService (memoized), TradeService (pruned)  │
        └───────┬───────────────────────────────┬──────────────────────┘
                │                                │
                ▼                                ▼
        ┌───────────────┐              ┌──────────────────────┐
        │ Postgres (prod)│              │ Disk: baked Sleeper  │
        │  + indexes [NEW]│             │ player cache  [NEW]  │
        └───────────────┘              └──────────────────────┘
        external: api.sleeper.app (roster/users/players),
                  DynastyProcess CSVs (consensus values/ELO)

        * `--workers 2` under evaluation (infra decision, §6)
```

`[NEW]`/`[CHANGED]` mark what the optimization work adds or alters.

---

## 2. Design goals & non-goals

**Goals**
- G1: **First meaningful paint is never gated on a network call** the current
  screen doesn't need. (INIT-01)
- G2: **Cold-start cost is off the user's critical path** — baked cache,
  background warm, optimistic shell. (INIT-02, INIT-08)
- G3: **Cached data paints instantly** on cold launch and tab navigation.
  (INIT-04, INIT-07)
- G4: **Backend produces player/trade data with bounded, non-redundant work** —
  memoized ELO, pruned trade generation, indexed reads. (INIT-03, INIT-09,
  INIT-14)
- G5: **Failures are bounded and recoverable** — request timeouts, GET retry,
  honest "waking up" UX. (INIT-12, INIT-08)

**Non-goals**
- Eliminating the Render free-tier cold start in software (impossible — §6).
- Re-architecting the ranking/trade *algorithms* or their outputs (ELO math and
  trade fairness are cross-client invariants; we change *how fast* they're
  produced, not *what* they produce).
- Web client work beyond the shared-origin payload (INIT-10).

---

## 3. The four architectural pillars

### Pillar A — Boot & cold-start path (G1, G2)
The boot gate is split into **local-state** (must complete before paint) and
**network side-effects** (must not block paint):

```
App boot
 ├─ AWAIT  bootstrap() [AsyncStorage/SecureStore]  ─┐
 ├─ AWAIT  cached-flag hydrate                      ├─► setBooted(true) ─► paint shell
 ├─ detach fetchTierConfig()  (fallback bands)      │
 └─ detach warmPlayerCache()  (warms dyno)        ──┘   (continue in background)
```
Cold-start cost moves left-to-right *out* of the gate: the dyno warms behind a
painted shell; the player cache is **baked into the deploy image** so a cold
container reads it from disk in ms instead of a 5 MB upstream fetch.

### Pillar B — Client cache & fetch architecture (G3, G5)
Three cooperating layers, each with a defined responsibility:

| Layer | Holds | Lifetime | Change |
|-------|-------|----------|--------|
| Zustand + AsyncStorage | session, league, flags | persisted | unchanged |
| **TanStack Query + persister** | rankings, progress, trios, matches, trades | persisted (allowlist) | **NEW** (INIT-07) |
| In-flight prefetch | next-screen data warmed on nav intent | request-scoped | **extended** (INIT-04) |

Query keys gain `format`/`leagueId` dimensions so a league/format switch swaps
cache slots instead of bleeding (INIT-07/CACHE-04). `focusManager`/`onlineManager`
are wired to AppState/NetInfo so resume-revalidation works as intended (INIT-05).
The `api/*` wrapper gains a default timeout + GET-only retry (INIT-12).

### Pillar C — Backend data production (G4)
- **RankingService**: ELO/stats memoized on the instance, keyed by the existing
  `_version` counter — one full-history pass per request instead of 3–4
  (INIT-03). `session_init` defers the trade-service build off the critical
  path and (Wave 3) seeds ELO from the persisted `member_rankings` snapshot
  instead of replaying all swipes (INIT-08).
- **TradeService**: candidate sets pre-pruned before the combination loops
  (~10× fewer 3-for-2 enumerations), so deep leagues finish a full sweep rather
  than truncating on the 1 s deadline (INIT-09).
- **DB**: `ix_players_position`, bulk `upsert_league_members`, narrowed
  `check_for_match`, SQL-side community-ELO aggregation (INIT-14).
- **Request middleware**: `touch_user_activity` throttled to ≤1 write/min/user
  (INIT-06).

### Pillar D — Network & edge (G2, web payload)
- Mobile relies on platform-default gzip + the 25-byte `/warm` ping (documented
  invariant, INIT-15).
- The **web** player payload is slimmed (53→~17 fields) and made cacheable
  (ETag + `Cache-Control`, edge-cache instead of `DYNAMIC`), freeing origin CPU
  on the shared worker (INIT-10).
- The mis-bound `/api/sleeper/players` route is rebound to the intended handler
  first (INIT-10/ROUTE-05).

---

## 4. Target data-flow sequences

### 4.1 Cold launch (returning user, cold dyno) — target
```
t0  App boot: local session restore completes (ms)         ──► paint shell
t0+ persisted query cache rehydrates ──► last-known board/matches paint (stale)
t0+ (background) warm ping wakes dyno; reads BAKED cache from disk (ms, not 5 MB fetch)
t1  user taps a league ──► optimistic Main shell paints immediately
t1+ session_init runs (deferred trade-svc); rankings/trios stream in on arrival
t2  focusManager/staleness triggers background revalidation; UI swaps stale→fresh
```
Contrast with today: the user waits on a spinner through the entire dyno wake +
5 MB fetch + session_init before *anything* paints.

### 4.2 In-session tab navigation — target
```
row/tab press ──► prefetchQuery(destination key)   (overlaps transition)
screen mounts ──► useQuery adopts the in-flight/prefetched result ──► instant paint
```

### 4.3 Rank/trio request — target
```
GET /api/trio ──► RankingService.get_rankings
                   └─ _compute_elo (MEMOIZED on _version) — 1 pass, not 3–4
```

---

## 5. Component impact map (what each initiative touches)

| Area | Components | Initiatives |
|------|-----------|-------------|
| Mobile boot | `App.tsx`, `RootNav.tsx`, `useSession`, `useFeatureFlags` | INIT-01, INIT-05 |
| Mobile cache | `queryClient.ts`, query-key call sites, `TabNav.tsx` (prefetch) | INIT-04, INIT-07 |
| Mobile api | `api/client.ts`, `api/auth.ts`, `api/sleeper.ts`, `api/trades.ts` | INIT-12, INIT-13 |
| Mobile render | `TiersScreen`, `OverallRanksScreen`, `ManualRanksScreen`, `PlayerCard`, `TradeCard`, `StrengthBar` | INIT-11 |
| Backend routes | `server.py` (`session_init`, `sleeper_players`, `before_request`) | INIT-06, INIT-08, INIT-10 |
| Backend services | `ranking_service.py`, `trade_service.py`, `trends_service.py` | INIT-03, INIT-08, INIT-09, INIT-14 |
| Backend data | `database.py` (indexes, upserts, match), `data_loader.py` | INIT-02, INIT-14 |
| Infra | `render.yaml`, `build.sh`, Cloudflare edge | INIT-02, INIT-10, §6 |

---

## 6. Infra decision (escalated)

The Render free-tier dyno (sleeps after ~15 min; 30–60 s wake; `--workers 1`)
is the irreducible latency floor. The HLD assumes one of:
- **Baseline (chosen for code work):** keep free tier; mask with a warm-ping
  cron + the boot/cold-start initiatives. Residual: gap-session cold starts.
- **Recommended infra change:** Render Starter ($7/mo, always-on) + `--workers 2`.
  The only complete removal of the cold-start floor.

All software initiatives are designed to be correct under *either* choice; the
optimistic-shell and baked-cache work specifically make the free-tier residual
tolerable.

---

## 7. Risks & invariants

- **Cross-client invariants** (`docs/cross-client-invariants.md`): ELO math,
  K-factors, `ELO_INITIAL`, tier bands/colors, per-format independence. Any
  initiative touching ranking/trade production (INIT-03, INIT-08, INIT-09) must
  ship behind a byte-for-byte golden-value test.
- **Cache correctness**: persisting under-scoped keys would show another
  league's/format's data — INIT-07 sequences key-scoping *before/with* the
  persister.
- **Drag-coordinate invariant**: INIT-11's Tiers virtualization must preserve
  the PR #60 screen-Y drop-coordinate model.
- **Idempotent retry**: INIT-12 retry is GET-only; `session_init`/swipes/saves
  are never auto-retried.
