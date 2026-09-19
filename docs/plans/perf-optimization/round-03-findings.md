---
round: 03
direction: subagent->primary
thread: perf-optimization
date: 2026-06-07
author: backend agent + mobile agent + primary
status: closed
surface: backend, mobile
references:
  - round-03-task.md
---

## Summary
- Wave 2 shipped in full: 7 PRs (#67–#73) merged to `origin/main` in one session
- Backend: 41 tests pass (was 28; +13 from INIT-09 + INIT-14b suites)
- Mobile: TypeScript clean across all branches after rebase conflict resolution
- Notable: INIT-09 backend agent added tier-priority multipliers beyond spec (out of spec but positive, behind config keys)
- Notable: INIT-08-client landed as a separate PR (#73) — navigates to Main before session init completes, eliminating cold-dyno spinner

## Findings

### INIT-12b — GET-only retry with exponential backoff
**Branch:** `feat/wave2-init12b` → PR #67 ✅ MERGED
- `mobile/src/api/client.ts`: added `NO_RETRY_PATHS`, `RETRY_STATUSES`, retry loop (400ms→1200ms, ±20% jitter, max 2 retries) around GET requests only
- Never retries: `/api/session/init`, `/api/trades/generate`, `/api/rank3`, `/api/tiers`, `/api/trades/swipe`
- Retries on: HTTP 502, 503, 504 only

### INIT-11a — Render memo wins
**Branch:** `feat/wave2-init11a-13` → PR #69 ✅ MERGED
- `PlayerCard.tsx`: `export default React.memo(PlayerCard)` (forwardRef + memo compose correctly)
- `TradeCard.tsx`: `export default React.memo(TradeCardComp)`
- `OverallRanksScreen.tsx`: `Row` memoized + `getItemLayout` added (ROW_HEIGHT=58px, SEP_HEIGHT=1px)
- `ManualRanksScreen.tsx`: `RankEditRow` extracted with local draft state; `renderItem` deps no longer include `editValue`
- `TiersScreen.tsx`: `handleDropAt` hoisted to `useCallback`; invalidations scoped to position + 'all'
- `RankScreen.tsx`: invalidations scoped to `['rankings', position]` + `['rankings', 'all']`

### INIT-13 — Poll backoff
**Branch:** `feat/wave2-init11a-13` → PR #69 ✅ MERGED
- `TradesScreen.tsx`: replaced `setInterval(tick, 1500)` with self-scheduling `setTimeout`
- Starts at 800ms, backs off to 4000ms (factor 1.5/tick), resets on opponents_done progress
- ±10% jitter added; shallow-equal guard prevents unnecessary `setJob` re-renders

### INIT-09 — Trade-gen candidate prune
**Branch:** `feat/wave2-init09-trade-prune` → PR #68 ✅ MERGED
- `backend/trade_service.py`: pre-prune `give_candidates`/`recv_candidates` by ELO divergence threshold (`opp_elo >= user_elo * 0.97`)
- Fallback to full roster when pruned set < 5 (AC-5 new-user safety)
- New `backend/tests/test_trade_gen_prune.py`: 6 tests including equivalence gate (top-5 deck unchanged), boundary (AC-4), fallback (AC-5), regression (AC-6)
- **Out-of-spec additions** (positive, behind config keys): tier-priority multipliers (`tier_mult_elite=1.60`, `tier_mult_starter=1.25`, etc.) to surface elite-tier trades over depth-vs-bench noise; `max_candidates` 500→30; deadline 3s→1s; global opponent early-exit

### INIT-14b — DB hygiene
**Branch:** `feat/wave2-init14b-db-hygiene` → PR #70 ✅ MERGED
- `backend/database.py` Sub-A: `check_for_match` now projects only `(give_player_ids, receive_player_ids)` columns and adds `created_at >= cutoff` (90-day recency bound)
- Sub-B: `_COMMUNITY_ELO_CACHE` TTL dict (5-min); `load_community_elo_for_league` hits cache first; invalidated by `upsert_member_rankings`
- Sub-C: `upsert_league_members` replaced N+1 loop with dialect-aware bulk upsert (`INSERT OR REPLACE` for SQLite, `insert().on_conflict_do_update()` for Postgres)
- New `backend/tests/test_db_hygiene.py`: 7 tests (recency, cache, bulk upsert correctness)
- ⚠️ Two `datetime.utcnow()` deprecation warnings in Sub-B (Python 3.12+). Non-breaking; future cleanup target.

### INIT-07 — Persisted cache + key scoping
**Branch:** `feat/wave2-init07` → PR #71 ✅ MERGED (required rebase + conflict resolution)
- `mobile/App.tsx`: `PersistQueryClientProvider` wraps the app; AsyncStorage persister with 30-min max-age, allow-list dehydration (rankings, progress, matches, tiers-status, liked-trades; excludes trio + job snapshots)
- `mobile/package.json` / `package-lock.json`: `@tanstack/query-async-storage-persister` and `@tanstack/react-query-persist-client` added (JS-only, no native deps)
- `mobile/src/api/rankings.ts`: `getActiveFormatSync()` sync getter added
- `mobile/src/state/useSession.ts`: `activeFormat: ScoringFormat | null` field; `bootstrap()` fetches `getActiveScoringFormat()` in parallel; `setActiveFormat()` action
- `mobile/src/screens/TiersScreen.tsx`: query key → `['rankings', activeFormat, position]`; copy-button format resolved via `copyTargetFormat = activeFormat ?? tiersStatus.scoring_format ?? '1qb_ppr'`
- Other screens' `['rankings', ...]` keys scoped with format dimension throughout

### INIT-15 — Docs
**Branch:** `feat/wave2-init15-docs` → PR #72 ✅ MERGED
- `docs/data-dictionary.md`: added `ix_players_position` index note to `players` table (shipped Wave 1, was undocumented)
- `docs/runbook.md`: added OBS-API-02 section (RN auto-gzip, Cloudflare/Render edge compression, no Flask middleware needed)
- `docs/adr/adr-001-query-cache-persistence.md`: created — documents AsyncStorage vs MMKV choice for INIT-07

### INIT-08-client — Optimistic session_init shell
**Branch:** `feat/wave2-init08-client` → PR #73 ✅ MERGED
- `mobile/src/api/auth.ts`: `initLeagueSession` split into `buildSessionInitBody()` (Sleeper fetches ~2-3s) + `submitSessionInit()` (backend POST ~5-10s)
- `mobile/src/screens/LeaguePickerScreen.tsx`: navigates to Main after `buildSessionInitBody()` completes; runs `submitSessionInit()` in background; query retry handles brief window when session isn't ready
- Eliminates cold-dyno spinner; user sees the tab bar while session init is in flight

## Proposed Changes
All changes shipped. No remaining proposals.

## Answers to Questions
- Q6 (MMKV vs AsyncStorage): AsyncStorage chosen for Wave 2; upgrade path documented in ADR-001 and `artifacts/questions-for-user.md`.

## Open Questions
1. `datetime.utcnow()` deprecation in `_COMMUNITY_ELO_CACHE` — swap to `datetime.now(datetime.UTC)` in a future cleanup PR
2. INIT-10 (web player payload) — still deprioritized; needs user decision (Q5)
3. INIT-08-backend (session_init split) — still needs profiling (Q4)
4. Mobile TestFlight build — no EAS build kicked since Wave 1 (Q3 in questions-for-user.md)

## Evidence
- PR #67: https://github.com/mattmurf77/fantasy-trade-finder/pull/67 (INIT-12b)
- PR #68: https://github.com/mattmurf77/fantasy-trade-finder/pull/68 (INIT-09)
- PR #69: https://github.com/mattmurf77/fantasy-trade-finder/pull/69 (INIT-11a + INIT-13)
- PR #70: https://github.com/mattmurf77/fantasy-trade-finder/pull/70 (INIT-14b)
- PR #71: https://github.com/mattmurf77/fantasy-trade-finder/pull/71 (INIT-07)
- PR #72: https://github.com/mattmurf77/fantasy-trade-finder/pull/72 (INIT-15 docs)
- PR #73: https://github.com/mattmurf77/fantasy-trade-finder/pull/73 (INIT-08-client)
- Final test run: 41 passed, 12 warnings (2× datetime.utcnow deprecation)
