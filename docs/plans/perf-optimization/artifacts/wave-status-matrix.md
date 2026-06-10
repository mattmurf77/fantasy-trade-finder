# Wave status matrix — all 16 initiatives

State as of 2026-06-07. Spec for each: `docs/code-audit/perf-optimization/design/requirements/init-0X-*.md`.
Scope: [M] mobile · [W] web · [B] backend · [X] cross.

| INIT | Title | Wave | Scope | Status | Autonomous? | Notes |
|------|-------|:----:|:-----:|--------|:-----------:|-------|
| 01 | Splash decouple | 1 | M | ✅ shipped (PR #66) | — | RICE-P 16.0 |
| 02 | Cold-cache bake + parallelize | 1 | B | ✅ shipped | — | build.sh bake; possible fetch-only refinement (primary's call) |
| 03 | ELO memo + golden tests | 1 | B | ✅ shipped | — | keyed (_version, pool-fingerprint) |
| 04 | Nav prefetch | 1 | M | ✅ shipped | — | flat keys; Trends skipped |
| 05 | focusManager | 1 | M | ✅ shipped | — | onlineManager TODO (no NetInfo) |
| 06 | touch_user_activity throttle | 1 | B | ✅ shipped | — | 60 s |
| 12a | Timeout + warm dedup | 1 | M | ✅ shipped | — | GET retry split to 12b |
| 14a | players.position index | 1 | B | ✅ shipped | — | data-dictionary update still pending |
| 11a | Render memo wins | 2 | M | ⬜ TODO | ✅ yes | memo cards, getItemLayout, edit-row, invalidation scope, setJob guard |
| 13 | Poll backoff | 2 | M | ⬜ TODO | ✅ yes | 800 ms→4 s + jitter |
| 12b | GET retry | 2 | M | ⬜ TODO | ✅ yes | GET-only; never POST |
| 14b | DB hygiene | 2 | B | ⬜ TODO | ✅ yes | check_for_match, community-ELO cache, bulk upsert |
| 09 | Trade-gen prune | 2 | B | ⬜ TODO | ✅ yes (build top-K equiv test) | preserve fairness/KTC |
| 07 | Persisted cache + key scoping | 2 | M | ⬜ TODO | ✅ yes (AsyncStorage default) | scope keys FIRST; MMKV is an optional upgrade (Q6); ADR candidate |
| 08-client | Optimistic session_init shell | 2 | M | ⬜ TODO | ✅ yes | client half only |
| 08-backend | session_init split | 2/3 | B | ⬜ blocked | ❌ needs profiling (Q4) | `#64` already parallelized — diff first |
| 10 | Web player payload | 2 | W | ⬜ deprioritize? | ⚠ needs Q5 | rebind route → slim 53→17 → ETag; web-only |
| 15 | Compression/encoding docs | 3 | M/B | ⬜ TODO | ✅ yes | runbook entry |
| 11b | Tiers virtualization | 3 | M | ⬜ deferred | ⚠ higher risk | preserve PR #60 coord fix |
| 08-OptB | Snapshot-replay ELO | 3 | B | ⬜ deferred | ⚠ golden test | touches ELO math |
| 16 | League activity double-fetch | defer | M | ⬜ deferred | ✅ yes (low value) | RICE-P 0.8 |

## Overlap with already-merged work (verified 2026-06-07, pre-flight for Wave 2)

- `#64` "parallelize /api/session/init ranking rebuild + defer writes" —
  INIT-08 backend: `session_init` already parallelizes per-format rebuild in
  a 2-worker ThreadPoolExecutor (server.py) and defers upsert writes. The
  remaining backend split (defer trade-service build) still needs profiling
  (Q4 in questions-for-user.md). **INIT-08-client half is still TODO.**
- `#62` "Trios skeleton + prefetch + setQueryData; gcTime + placeholderData" —
  `gcTime: 30min` already set (queryClient.ts). placeholderData already on Trios,
  Tiers, Trades screen queries. TabNav already prefetches ['trio', 'QB'] before
  Trios navigate. **INIT-07 key scoping + persister still TODO.**
- `#63` "status='pending' writer + hot-path indexes + cache hygiene" — added
  composite indexes on swipe_decisions, trade_decisions, member_rankings,
  elo_history (all 4 hot tables). `ix_players_position` was a separate INIT-14a
  (Wave 1, PR #66) — **already shipped**. `load_league_member_unlock_states`
  already cached (60s TTL). **INIT-14b (check_for_match narrow, community-ELO
  cache, bulk upsert_league_members) is still TODO** — the bulk upsert comment
  in #64 notes it's "already off the request path now" but the N+1 loop itself
  was not replaced.

## Definition of done for the thread
All autonomous Wave 2 items shipped + verified + merged; Wave 3 + user-input
items tracked; `status.md` → Phase: done with an `## Outcome` section; promote
schema/route/invariant changes per CLAUDE.md table; ADR for the persistence choice.
