# REQ — INIT-02: Bake + parallelize the Sleeper player cache

- **Initiative / Wave / Scope:** INIT-02 · Wave 1 · [B]
- **Source observations:** OBS-NET-01 (RICE-P 9.6), OBS-DB-04 (RICE-P 0.75)
- **Peak RICE-P:** 9.6

## Problem statement

On a cold Render container, the first `session/init` request triggers a synchronous 5 MB fetch from `api.sleeper.app` (up to 45 s timeout), followed by two sequential DynastyProcess CSV fetches and two universal-pool builds — all on the single gunicorn worker, on the requesting user's critical path. The cache file is gitignored and there is no persistent disk on the free tier, so every dyno cold start re-pays this cost from scratch.

## User stories

- As a dynasty manager who is the first to open the app after the dyno sleeps, I want `session/init` to return without waiting for a multi-MB upstream fetch, so that my league load time is bounded by the dyno wake and not also by an additional network round-trip to Sleeper.
- As an operator, I want the deployed container to have a valid player cache pre-loaded at start-up, so that a cold-start user is never blocked by the upstream Sleeper fetch on the critical path.
- As a developer, I want the two per-format DynastyProcess CSV fetches to run concurrently, so that the build phase that follows a cache warm is as fast as possible.

## Functional requirements

- FR-1: A recent `data/.sleeper_players_cache.json` must be present in the deploy image. Either `build.sh` fetches it at build time (a single `GET api.sleeper.app/v1/players/nfl` saved to `data/.sleeper_players_cache.json`), or a snapshot is committed directly. The choice must be documented in `build.sh`.
- FR-2: On cold-container startup, `_load_sleeper_cache` (`server.py:336–349`) must find the baked file on disk and return within milliseconds — the upstream network fetch path (`_ensure_sleeper_cache_populated`, `server.py:4350–4355`) must not be invoked during normal cold start when the baked file is present.
- FR-3: A nightly refresh mechanism must remain in place so the baked cache is a *floor*, not the sole source of truth. The existing refresh path (`sync_players`) must not be removed.
- FR-4: The two per-format `load_consensus_values` and `load_consensus_elo` fetches (`server.py:758–766`) must be executed concurrently (thread pool or `concurrent.futures.ThreadPoolExecutor`) rather than sequentially in a `for fmt` loop. Both results must be available before `build_universal_pool` is called for either format.
- FR-5: `build_universal_pool` must receive the already-loaded `all_db_players` list once and reuse it across both format builds, eliminating the per-build call to `load_players(position=None)` (`server.py:629`) that currently issues a full players-table scan for each format.
- FR-6: A DynastyProcess CSV fetch failure must not block boot or raise an unhandled exception; the existing graceful fallback (`data_loader.py:197–199`) must be preserved for both the sequential and the parallel execution paths.
- FR-7: The baked cache file must contain only the QB/RB/WR/TE-filtered shape that the runtime path writes (`server.py:4360–4365`); it must not contain fields stripped at runtime, to ensure the in-memory `_sleeper_cache` shape is identical whether loaded from the baked file or from a runtime refresh.

## Acceptance criteria

- [ ] AC-1 — Given a freshly deployed container (baked cache in place), when the first `session/init` request arrives, then the boot-time log shows `_load_sleeper_cache` completing in under 500 ms with no upstream Sleeper network call.
- [ ] AC-2 — Given the baked `data/.sleeper_players_cache.json` is present, when `_ensure_sleeper_cache_populated` is called, then it returns immediately using the on-disk cache without calling `urlopen`.
- [ ] AC-3 — Given both format CSV fetches are dispatched concurrently, when both complete, then `g_universal_by_format` contains correctly built pools for both formats (verified by an integration test that checks pool sizes and spot-checks a known player's presence in each format pool).
- [ ] AC-4 — Given one of the two format CSV fetches fails (simulated timeout or HTTP error), when the pool build completes, then the failing format's pool falls back gracefully (using whatever the existing `data_loader.py:197–199` fallback provides) and the other format's pool is unaffected.
- [ ] AC-5 — Given both format pools are built from the same `all_db_players` list, then `load_players(position=None)` is called at most once per pool-build cycle (verified by a log counter or unit test mock).
- [ ] AC-6 — After deploying with the baked cache, `git ls-files data/.sleeper_players_cache.json` returns the file (or `build.sh` shows a `curl`/`wget` step that fetches it at build time and the Render build log confirms it).
- [ ] AC-7 — The nightly `sync_players` refresh continues to run on schedule and overwrites the baked cache with fresh data; the next cold start after a refresh uses the refreshed file.

## Related components

- `build.sh` — to be extended with a cache-fetch step at build time
- `render.yaml` — no `disk:` mount; ephemeral filesystem confirmed; no change needed here, but must be noted as the reason the file must be baked
- `backend/server.py:336–349` — `_load_sleeper_cache` (the fast path, must be the cold-start entry point)
- `backend/server.py:4337` — `_ensure_sleeper_cache_populated` decorator / function (upstream fetch path; must not fire on cold start when baked file present)
- `backend/server.py:4350–4355` — synchronous `urlopen(..., timeout=45)` for the ~5 MB payload
- `backend/server.py:758–766` — serial `for fmt` loop over DynastyProcess CSV fetches (to be parallelized)
- `backend/server.py:629` — per-build `load_players(position=None)` call inside `build_universal_pool` (to be hoisted and reused)
- `backend/server.py:4360–4365` — QB/RB/WR/TE filter applied when writing the cache; baked file must match this shape
- `backend/data_loader.py:197–199` — graceful fallback on DP CSV fetch failure (must be preserved)
- `.gitignore:8` — `data/` is ignored; if baked via `build.sh` fetch rather than commit, this is fine; if committing the snapshot, `data/.sleeper_players_cache.json` must be explicitly un-ignored

## Prerequisite components / dependencies

None for the baked-cache (FR-1 through FR-3). The parallelization (FR-4) and player-list reuse (FR-5) are independent of each other and of the bake step, but all three are in this initiative's scope. INIT-08 (session_init optimization) and INIT-12 (warm dedup) benefit from this landing first, but this initiative does not depend on them.

## Non-functional requirements & invariants

- **Performance target:** on a cold container with the baked cache, `session/init` must not wait on an upstream Sleeper network call; the cache load contribution to `session/init` latency must be under 500 ms.
- **Cache shape invariant:** the baked `data/.sleeper_players_cache.json` must be structurally identical to the file produced by the runtime `_ensure_sleeper_cache_populated` + filter path (`server.py:4360–4365`). Any deviation (extra fields, missing position filter) can cause `session/init` to silently serve wrong player data. This must be validated in CI or a build-time assertion.
- **Per-format independence:** the two universal pools built from the parallelized CSV fetches must remain fully independent (separate dict keys). The parallelization must not share mutable state between the two format builds.
- **No ELO / tier-band invariants touched:** this initiative builds and caches player metadata only. Ranking math, K-factors, ELO_INITIAL, and tier bands are not affected.
- **Staleness window:** the baked cache can lag behind newly-added rookies by up to one deploy cycle. This is an accepted trade-off documented in `build.sh`. The nightly refresh (FR-3) bounds the staleness to at most one day during active operation.
- **Rollback:** removing the `build.sh` fetch step and reverting the `for fmt` parallelization restores the original behavior with no DB migration.

## Out of scope

- Persistent Render disk (`disk:` mount in `render.yaml`) — a paid-tier infra change; not included.
- Caching the DynastyProcess CSV files to disk with a TTL (OBS-DB-04 Option B) — deferred; the baked Sleeper cache and parallelized fetches cover the critical path.
- INIT-08 Option B (session_init replay-from-snapshot) — separate initiative requiring golden-ELO tests.
- Any mobile or web client changes.
- The `--workers 1` single-worker contention on Render — an infra decision documented in the optimization plan §6, outside code-change scope.
