# Low-Level Design (LLD) — Performance Initiatives

Per-initiative technical design. Each section specifies the mechanism, the
exact touch points (`file:line` from the observations), config values, data
structures, sequencing, and the test that proves it. Companion:
[`hld.md`](./hld.md), [`../plan/optimization-plan.md`](../plan/optimization-plan.md).

Convention: **TP** = touch points, **MECH** = mechanism, **TEST** = verification,
**INV** = invariant to preserve.

---

## INIT-01 — Decouple splash from network boot legs  *(Wave 1, [M])*

**MECH.** Split the boot `Promise.all` into a *gating* set (local I/O only) and
a *detached* set (network, best-effort). Release `setBooted(true)` on the
gating set; let the detached set run in the background.

- **TP:** `mobile/App.tsx:47–54` (the `Promise.all([...]).finally(setBooted)`),
  `useSession.bootstrap` (`useSession.ts:96–113`, local-only), `useFeatureFlags.load`
  (`useFeatureFlags.ts:27–55` — split cache-hydrate from network fetch),
  `RootNav.tsx:96–112` (splash → routing decision needs only `user/league/hasToken`).
- **Design:**
  ```
  await Promise.all([ bootstrap(), loadCachedFlags() ])   // local only
  setBooted(true)
  void fetchTierConfig().catch(()=>{})                     // detached
  void warmPlayerCache().catch(()=>{})                     // detached
  void revalidateFlags().catch(()=>{})                     // detached (network half)
  ```
  `loadFlags()` is refactored to expose a synchronous-ish `loadCachedFlags()`
  (AsyncStorage hydrate) separate from `revalidateFlags()` (network).
- **TEST:** with the network blackholed, the SignIn/LeaguePicker/Main shell
  still paints within local-I/O time; flag-gated UI settles to cached values.
- **INV:** tier-band consumers must tolerate seeded fallback for the brief
  window before `fetchTierConfig` resolves (already the documented failure path,
  `App.tsx:35–42`). Push-priming gate must still fire once `['progress']`
  resolves.

---

## INIT-02 — Cold-start player cache: bake + parallelize  *(Wave 1, [B])*

**MECH.** Remove the upstream 5 MB fetch from the cold critical path by shipping
a cache snapshot in the deploy image, and parallelize the dual-format consensus
fetch.

- **TP:** `build.sh` (currently `pip install` + `mkdir -p data`),
  `server.py:336–349` (`_load_sleeper_cache`), `server.py:4350–4355` (45 s
  `urlopen`), `server.py:758–766` (serial `for fmt` DP CSV fetch),
  `server.py:629` (per-build `load_players(position=None)`), `render.yaml`,
  `.gitignore:8`.
- **Design:**
  1. **Bake:** `build.sh` fetches a fresh `data/.sleeper_players_cache.json` at
     build time (or commit a periodic snapshot). Cold container hits
     `_load_sleeper_cache` (disk, ms) instead of `_ensure_sleeper_cache_populated`
     upstream fetch. Keep the nightly refresh so the baked copy is a floor, not
     the source of truth.
  2. **Parallelize:** run the two per-format `load_consensus_values/elo` fetches
     concurrently (thread pool / `concurrent.futures`) instead of the serial
     `for fmt` loop — independent network calls.
  3. **Reuse:** pass the already-loaded `all_db_players` into `build_universal_pool`
     once and reuse across both formats (drop the per-build `load_players` scan).
- **TEST:** boot timer log on a cold container shows cache load in ms; both
  pools build with one players-table read; DP fetches overlap.
- **INV:** baked cache must match the QB/RB/WR/TE-filtered shape the runtime
  writes (`server.py:4360–4365`). A DP fetch failure must not block boot
  (preserve the graceful fallback `data_loader.py:197–199`).

---

## INIT-03 — Memoize ELO/stats recompute  *(Wave 1, [B])*

**MECH.** Instance-level memo on `RankingService`, keyed by the already-bumped
`_version` counter.

- **TP:** `ranking_service.py:613–664` (`_compute_elo`), `:523/:563/:594`
  (`_compute_stats`/`_tier_info`), call sites `:341/:685/:840`; `_version`
  bumps at `:230/:265/:294/:448/:828/:859`.
- **Design:** wrap `_compute_elo`/`_compute_stats` in a cache:
  ```
  if self._elo_cache_version == self._version: return self._elo_cache
  result = <full compute>
  self._elo_cache, self._elo_cache_version = result, self._version
  return result
  ```
  Collapses 3–4 passes/request to 1; invalidates automatically on any mutation
  (every mutator already bumps `_version` — verified in OBS-DB-03).
- **TEST:** golden test — ELO output identical before/after for a fixture user;
  a counter/log proves `<full compute>` runs once per request, not 3–4×.
- **INV:** **ELO math is a hard cross-client invariant.** Memo must be a pure
  pass-through (same inputs → same bytes). Confirm every mutator bumps `_version`.

---

## INIT-04 — Extend navigation prefetch  *(Wave 1, [M])*

**MECH.** Reuse the proven Trios prefetch-on-nav-intent for the other
destinations.

- **TP:** `TabNav.tsx:169–177` (existing Trios `prefetchQuery`), destination
  keys: Tiers `['rankings','QB']`+`['tiers-status']` (`TiersScreen.tsx:102–114`),
  Overall/Manual `['rankings','all']` (`OverallRanksScreen.tsx:29`,
  `ManualRanksScreen.tsx:59`), Matches `['matches','all']` (`MatchesScreen.tsx:53`),
  Trades `['liked-trades', leagueId]` (`TradesScreen.tsx:341`).
- **Design:** in `RankMenu.go(route)`, prefetch the destination's key; add a
  `tabPress` listener for the Trades/Matches tabs. Prefetch the **scoped** key
  shape (coordinate with INIT-07/CACHE-04). Fire-and-forget.
- **TEST:** navigating to each destination adopts an in-flight/prefetched query
  (no fresh spinner on warm dyno when the transition ≥ round-trip).
- **INV:** prefetch the exact key the destination `useQuery` uses, or the warm
  misses.

---

## INIT-05 — Wire focusManager + onlineManager  *(Wave 1, [M])*

**MECH.** Bridge TanStack's `focusManager` to RN AppState and `onlineManager` to
NetInfo, activating the already-intended `refetchOnWindowFocus`.

- **TP:** reuse the existing AppState listener (`App.tsx:84–94`),
  `queryClient.ts:21,24`, the dead `RootNav.tsx:80` `refetchOnWindowFocus:true`.
- **Design:**
  ```
  focusManager.setEventListener(handleFocus =>
    AppState.addEventListener('change', s => handleFocus(s === 'active')))
  onlineManager.setEventListener(setOnline =>
    NetInfo.addEventListener(s => setOnline(!!s.isConnected)))
  ```
- **TEST:** background >`staleTime`, return → resume-sensitive queries
  (`['progress']`, `['matches','all']`) revalidate; trio deck (`staleTime:0`)
  does **not** reshuffle mid-swipe on resume.
- **INV:** keep per-screen `staleTime` honest so focus-refetch isn't a storm.
  NetInfo dependency check (transitively present?).

---

## INIT-06 — Throttle `touch_user_activity`  *(Wave 1, [B])*

**MECH.** Skip the synchronous `UPDATE users` unless the in-session `last_active`
is older than N seconds.

- **TP:** `server.py:971–995` (`before_request`), in-session `last_active`
  (`server.py:2788`), `database.py:907–937` (the write).
- **Design:** `if now - sess.get('last_active', 0) >= 60: touch_user_activity(...);
  sess['last_active'] = now`. Collapses a poll storm into ≤1 write/min/user.
- **TEST:** a `/api/trades/status` poll burst yields ≤1 `UPDATE users`/min;
  `last_active_at` precision is ~1 min.
- **INV:** confirm no re-engagement/notification query needs sub-minute
  `last_active_at` (discrete actions already write precise `user_events`).

---

## INIT-07 — Persisted query cache + key scoping  *(Wave 2, [M])*

**MECH.** Two coupled changes, **scoping first/with persistence**: (a) add
`format`/`leagueId` to player-data keys; (b) add an AsyncStorage query
persister with a dehydrate allowlist.

- **TP (keys):** `['rankings', position]`→`['rankings', format, position]`
  (`TiersScreen.tsx:103`), `['rankings','all']`→`['rankings', format, 'all']`
  (`OverallRanksScreen.tsx:30`, `ManualRanksScreen.tsx:60`),
  `['progress']`→`['progress', leagueId, format]` (`RootNav.tsx:76`,
  `RankScreen.tsx:83`), `['streak']`, `['tiers-status']`, `['trio', position]`;
  invalidation prefixes (`RankScreen.tsx:145`, `TiersScreen.tsx:145,173`,
  `ManualRanksScreen.tsx:105`) still match the new prefix.
- **TP (persist):** `App.tsx:96–105` (wrap in `PersistQueryClientProvider`),
  `queryClient.ts:17–30`, add `@tanstack/query-async-storage-persister`.
- **Design:** persister `maxAge` ≈ `gcTime` (30 min); `dehydrateOptions.shouldDehydrateQuery`
  allowlist = rankings/progress/matches/tiers-status; **exclude** live
  trade-generation job snapshots and `['trio', …]` deck (must stay fresh).
- **TEST:** cold launch paints last-known rankings/progress/matches instantly,
  then revalidates; a format/league switch swaps cache slots (no bleed); a
  persisted cache from a prior format never renders under the other format.
- **INV:** **must not persist under-scoped keys** (CACHE-04 lands first/with).
  Cache transport only — no ELO/tier invariant touched.

---

## INIT-08 — session_init slim + optimistic shell  *(Wave 2–3, [M]+[B])*

**MECH (client, Wave 2).** Paint an optimistic, skeletoned Main shell on league
pick; stream ranking/trade data in when the token lands.
- **TP:** `auth.ts:101–162` (`initLeagueSession`; `await sessionInit` at `:151`),
  `RootNav.tsx:177`, `useSession.switchLeague`. First-paint queries
  (`RankScreen.tsx:77`, `TabNav.tsx:174`) adopt data on arrival.
- **INV:** gate interactive actions on `hasToken`; handle `session_init` failure
  from inside Main, not the picker.

**MECH (backend, Wave 2).** Defer the trade-service build + 7-day decision load
out of the blocking section (only needed when Trades opens).
- **TP:** `server.py:4683–4690` (trade-svc build), guard with the existing
  job/lock pattern; rankings services + pool stay (trio needs them).

**MECH (backend, Wave 3).** Seed ELO from the persisted `member_rankings`
snapshot; replay only post-snapshot swipes (`OBS-DB-03 Option B`).
- **INV:** golden ELO parity — replay-from-snapshot must equal replay-from-zero
  (the override-anchoring at `ranking_service.py:623–662` is subtle).
- **PREREQ:** profile an authed `session_init` first (the 5–10 s is the
  codebase's own estimate, unmeasured) to confirm where the time goes.

---

## INIT-09 — Prune trade-generation candidates  *(Wave 2, [B])*

**MECH.** Pre-prune give/recv candidate sets per opponent before the combination
loops, so the dominant `C(25,3)` (≈2300) 3-for-2 term shrinks to `C(12,3)` (≈220).

- **TP:** `trade_service.py:827–866` (opp loop), `:1179–1188` (3-for-2 nest),
  `:1341` (`_mismatch_score`), guards `:948–950`.
- **Design:** restrict the user's give-side to roster players whose user-ELO is
  *below* the opponent's ELO for them (only those can yield `opp_surplus>0`);
  symmetric for recv-side. Drops only candidates the existing
  `recv_user <= combined_give_user*0.95` guard would reject anyway.
- **TEST:** **top-K equivalence** — identical top-of-deck cards before/after on a
  sample of real rosters; deep-league sweep completes without hitting the 1 s
  deadline.
- **INV:** do not alter `_fairness_score`/KTC math — only the candidate set fed
  into them. Trade fairness is user-visible.

---

## INIT-10 — Web player payload (rebind + slim + cache)  *(Wave 2, [W])*

**MECH.** Fix the mis-bound route, then slim fields and make the body cacheable.

- **TP:** `server.py:4336–4337` (decorator mis-bound to
  `_ensure_sleeper_cache_populated`; `sleeper_players()` at `:4392` dead),
  `:4360–4365` (cache filter keeps all 53 fields), `:4399–4404` (`jsonify(cached)`,
  no headers), `player_to_dict` (`:1240`, the ~17-field shape), `web/js/app.js`
  (consumer).
- **Design:**
  1. **Rebind** the route to `sleeper_players()` (or delete the dead fn) — do
     this *first* so 2/3 land on the right handler.
  2. **Slim:** project each player through a field allowlist (extend
     `player_to_dict`); est. 4.8 MB → ~1.3 MB origin / ~250 KB compressed.
     Grep `web/js/app.js` for stripped field names before shipping.
  3. **Cache:** strong `ETag` (cache mtime/sync-version) + `Cache-Control:
     public, max-age=<~daily>`; honor `If-None-Match`→304. Lets Cloudflare drop
     the `DYNAMIC` status and edge-cache.
- **TEST:** `cf-cache-status: HIT` post-deploy; a sync bumps the ETag and busts
  the cache; web renders identically with the slim shape.
- **INV:** TTL aligned to the nightly Sleeper refresh so new rookies aren't
  hidden. Display data only — no ranking invariant.

---

## INIT-11 — Render memoization + Tiers virtualization  *(Wave 2–3, [M])*

**MECH (Wave 2, cheap wins).**
- `React.memo` on `PlayerCard` (`PlayerCard.tsx:27`), `TradeCard` (`TradeCard.tsx:23`),
  `OverallRanks` `Row` (`OverallRanksScreen.tsx:103`) + `getItemLayout`;
  hoist `renderPlayerCard` inline arrows (`TiersScreen.tsx:537–560`) so memo bites.
- Extract the ManualRanks edit row so `renderItem` depends on `editingPid`, not
  the per-keystroke `editValue` (`ManualRanksScreen.tsx:231–290`).
- Scope the over-broad `['rankings']` invalidation to `['rankings', position]` +
  `['rankings','all']` (`RankScreen.tsx:145` et al.).
- Shallow-equal `setJob` guard so no-change poll ticks don't re-render
  (`TradesScreen.tsx:243`).

**MECH (Wave 3, structural).** Tiers: collapse non-active tiers to counts +
expander so only the edited tier mounts `DraggableRow`s
(`TiersScreen.tsx:722–756`).
- **INV:** preserve the PR #60 screen-Y drop-coordinate model; dropping into a
  collapsed tier must auto-expand or append. Do not touch `autoBucket`/tier
  bands (cross-client invariant).

---

## INIT-12 — API client resilience  *(Wave 1 timeout+dedup, Wave 2 retry, [M])*

**MECH.** Default timeout + GET-only retry in the one wrapper; de-dupe warm.
- **TP:** `client.ts:149–178` (single `fetch`, no timeout/retry), `auth.ts`
  un-signalled callers (`:25/:151/:201/:230`), `sleeper.ts:47`/`App.tsx:51`/
  `auth.ts:117` (double warm).
- **Design:**
  - Timeout: internal `AbortController` composed with caller `signal`; 15 s GET
    default, ≥30 s for `session/init` + `trades/generate`. On timeout throw a
    typed `ApiError` → "Server is waking up — retry."
  - Retry: GET-only, 2 attempts, 400 ms→1.2 s + jitter, on 502/503/504/network.
    **Never** retry `session/init`/swipes/saves.
  - Warm dedup: module-level "warmed-once-this-launch" flag in `sleeper.ts`;
    `initLeagueSession` skips the second warm unless a `session_init` "not
    cached" error resets it.
- **TEST:** wedged-dyno fetch bounded to the deadline + retry, not a 60–120 s
  hang; a cold-start 5xx GET recovers transparently; no duplicate `session_init`.
- **INV:** retry strictly idempotent (GET) — no double-mutation.

---

## INIT-13 — Trade-status poll backoff  *(Wave 2, [M])*

**MECH.** Exponential backoff + jitter on the status poll; shallow-equal render
guard.
- **TP:** `TradesScreen.tsx:256` (`setInterval(1500)`), `:243` (`setJob`),
  `trades.ts:84–96` (re-normalize on each tick).
- **Design:** start 800 ms, ×1.5 per *unchanged* tick (detect via
  `opponents_done` not advancing), cap 4 s, reset to 800 ms on progress. Pair
  with the `setJob` shallow-equal guard (INIT-11).
- **TEST:** multi-opponent job fills to completion; `running→complete` still
  fires; ~60–75% fewer status requests; final card not delayed past the cap.

---

## INIT-14 — DB hygiene  *(Wave 1 index, Wave 2 rest, [B])*

- **Index (W1):** `CREATE INDEX IF NOT EXISTS ix_players_position ON players(position)`
  in the `_hot_path_indexes` list (`database.py:714–723`). Additive, both
  dialects.
- **check_for_match (W2):** narrow `SELECT` to the two ID arrays + add a recency
  bound (reuse `since_days`, `database.py:1946`) (`database.py:2720–2739`).
- **Community-ELO (W2):** server-cache the assembled map per
  `(league_id, scoring_format)` with a short TTL, invalidated on
  `upsert_member_rankings` (mirror the 5-min leaderboard cache); or push the
  mean to SQL `AVG(...) GROUP BY player_id` (`trends_service.py:99–113,224–238`).
- **upsert_league_members (W2):** single dialect-aware bulk upsert on
  `uq_league_member` (`database.py:1990–2025`), reusing the branch pattern at
  `:749–759`.
- **INV:** bulk upsert preserves "newest snapshot wins"; SQL `AVG` matches the
  Python mean (NULL/zero handling) so Trends scores don't shift.

---

## INIT-15 — Compression/encoding documentation  *(Wave 3, [M]/[B])*

**MECH.** No code on mobile. Add a runbook entry: mobile relies on platform-
default gzip + the 25-byte `/warm` ping; the edge (Cloudflare) compresses the
web payload. A future custom networking layer must not strip the default
`Accept-Encoding`. Records the resolution of OBS-API-02 (measured no-op) and
OBS-NET-02/ROUTE-02.

---

## INIT-16 — League activity double-fetch  *(Defer, [M])*

**MECH.** Have the League screen fetch the activity feed once at limit 50 and
derive both the feed and the new-partners banner client-side
(`league.ts:282–303,287`). Off the player/trade critical path — defer.

---

## Cross-initiative sequencing constraints

```
INIT-10/ROUTE-05 (rebind)  ──before──►  INIT-10 (slim, ETag)
INIT-07/CACHE-04 (key scope) ──with/before──► INIT-07/CACHE-01 (persist)
INIT-02 (baked cache)       ──helps──►  INIT-08 (cold session_init), INIT-12 (warm)
INIT-11 (hoist arrows)      ──before──►  INIT-11 (memo bites)
profile session_init        ──before──►  INIT-08 backend split
golden ELO test harness     ──before──►  INIT-03, INIT-08-OptB, INIT-09
```
