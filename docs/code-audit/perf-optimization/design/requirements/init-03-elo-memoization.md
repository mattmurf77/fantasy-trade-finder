# REQ — INIT-03: Memoize ELO/stats recompute

- **Initiative / Wave / Scope:** INIT-03 · Wave 1 · [B]
- **Source observations:** OBS-DB-03 (RICE-P 6.4)
- **Peak RICE-P:** 6.4

## Problem statement

`RankingService._compute_elo` and `_compute_stats` re-iterate the full swipe history on every invocation, and are called 3–4 times per rank request (from `get_rankings`, `_algorithmic_trio`, `_tiered_pool`, and `apply_reorder`). For power users with thousands of swipes this is the dominant CPU cost on every trio and ranking read, yet the inputs change only when a mutation fires — which is already tracked by the existing `_version` counter.

## User stories

- As a dynasty manager with an extensive swipe history, I want trio and ranking reads to respond faster, so that the board and trio deck feel snappy rather than lagging with my history length.
- As a developer, I want ELO and stats computation to run at most once per request per service instance, so that future callers can freely invoke `_compute_elo` / `_compute_stats` without worrying about cascading re-computation cost.
- As an operator, I want per-request backend CPU usage to be reduced on the shared single worker, so that ranking reads do not starve other concurrent requests.

## Functional requirements

- FR-1: `RankingService` must maintain two instance-level cache fields: `_elo_cache` / `_elo_cache_version` and `_stats_cache` / `_stats_cache_version`, both initialized to `None` / `0` in `__init__`.
- FR-2: At the start of `_compute_elo`, if `self._elo_cache_version == self._version`, the method must return `self._elo_cache` immediately without re-running the computation.
- FR-3: At the start of `_compute_stats`, if `self._stats_cache_version == self._version`, the method must return `self._stats_cache` immediately without re-running the computation.
- FR-4: When `_compute_elo` runs the full computation, it must store the result in `self._elo_cache` and set `self._elo_cache_version = self._version` before returning.
- FR-5: When `_compute_stats` runs the full computation, it must store the result in `self._stats_cache` and set `self._stats_cache_version = self._version` before returning.
- FR-6: Every method that mutates ranking state must increment `self._version` before returning. The following mutation sites must be audited and confirmed to bump `_version`: `ranking_service.py:230`, `:265`, `:294`, `:448`, `:828`, `:859`. No new mutator may be added without also incrementing `_version`.
- FR-7: The memoized result must be semantically identical to the un-memoized result for the same `_version`. The memo must be a pure pass-through: no rounding, no field omission, no copy-by-reference that could allow the cache to be mutated by the caller.
- FR-8: A golden-value test must be added (or extended) that: (a) constructs a `RankingService` with a fixture swipe history, (b) calls the full computation path once (un-memoized reference output), (c) calls it again and asserts the memoized path returns byte-for-byte identical output, and (d) mutates the service (e.g. adds a swipe), asserts `_version` incremented, then asserts the next call re-runs the full computation and returns the new correct value.
- FR-9: A counter or log statement must confirm `<full compute>` runs at most once per request for the common trio/ranking surfaces, verifiable in the test added under FR-8.

## Acceptance criteria

- [ ] AC-1 — Given a `RankingService` instance with a non-empty swipe history, when `_compute_elo` is called twice in succession without any intervening mutation, then the second call returns the same object as the first and the full-compute body executes exactly once (verified by the FR-8 golden test).
- [ ] AC-2 — Given a `RankingService` instance, when any mutation method is called (swipe record, tier override, reorder), then `self._version` is strictly greater after the call than before, and the next call to `_compute_elo` or `_compute_stats` re-runs the full computation.
- [ ] AC-3 — Given the golden-value test fixture, when the memoized output is compared to the reference output, then all ELO ratings, tier assignments, and ranking positions are byte-for-byte identical.
- [ ] AC-4 — Given a `/api/trio` request on a warm service instance, when the request is traced, then `_compute_elo` full-compute body executes at most once during that request (not 3–4 times); this is verifiable via the log counter added under FR-9 or a unit test mock-count assertion.
- [ ] AC-5 — Given a `RankingService` instance whose `_elo_cache` is populated, when a new swipe is recorded (mutation), then the `_elo_cache_version` no longer equals `_version` and the next `_compute_elo` call re-computes and updates the cache.
- [ ] AC-6 — Given concurrent requests sharing the same `RankingService` instance (if applicable), then the memo fields do not cause data races; if the service is not thread-safe by design, document this and confirm the existing request-scoping model prevents concurrent mutation.

## Related components

- `backend/ranking_service.py:613–664` — `_compute_elo`: full-history iteration to be memoized
- `backend/ranking_service.py:523` — `_compute_stats` call inside `_tiered_pool`
- `backend/ranking_service.py:563` — `_compute_stats` call inside `_tier_info`
- `backend/ranking_service.py:594` — additional `_compute_stats` call site
- `backend/ranking_service.py:341` — `get_rankings` call site for `_compute_elo`
- `backend/ranking_service.py:685` — `_algorithmic_trio` call site for `_compute_elo`
- `backend/ranking_service.py:840` — `apply_reorder` call site for `_compute_elo`
- `backend/ranking_service.py:230` — `_version` bump (mutation site 1)
- `backend/ranking_service.py:265` — `_version` bump (mutation site 2)
- `backend/ranking_service.py:294` — `_version` bump (mutation site 3)
- `backend/ranking_service.py:448` — `_version` bump (mutation site 4, replay)
- `backend/ranking_service.py:828` — `_version` bump (mutation site 5)
- `backend/ranking_service.py:859` — `_version` bump (mutation site 6)
- `backend/ranking_service.py:382` — `replay_from_db` entry point (calls mutation methods; `_version` bumped via them)
- `backend/ranking_service.py:623–662` — override/anchoring logic inside `_compute_elo` (subtle; golden test must cover this path)

## Prerequisite components / dependencies

**Golden-ELO test harness must exist before this initiative ships.** The cross-initiative sequencing note in `lld.md` explicitly states: `golden ELO test harness ──before──► INIT-03`. A passing golden test is the definition of "no behavioral change" for this initiative. If no such harness exists, creating it is the first task of this initiative.

## Non-functional requirements & invariants

- **ELO math is a hard cross-client invariant.** ELO ratings, K-factors (`ELO_K`), `ELO_INITIAL` (1500), and tier-band thresholds are shared across mobile, web, and extension clients (`docs/cross-client-invariants.md`). The memo must be a pure pass-through. Any discrepancy in ELO output — however small — changes tier placement and trade recommendations visible to the user. The golden test (FR-8) is the gating requirement.
- **Override/anchoring path coverage:** `ranking_service.py:623–662` contains the tier-override anchoring logic that is described as "subtle" in the LLD. The golden test fixture must include at least one scenario with tier overrides applied to confirm the memo path handles this edge case identically.
- **No external state change:** the memo must not be stored outside the `RankingService` instance (no module-level cache, no DB write, no shared dict). Each service instance's cache is private to that instance.
- **Performance target:** for a user with 1 000+ swipes, `_compute_elo` full-compute must execute at most once per request on all ranking and trio surfaces; CPU contribution from redundant ELO passes must be eliminated (−30–60% CPU on ranking reads for power users, per OBS-DB-03 estimate).
- **Rollback:** the cache fields can be removed and the `if self._elo_cache_version == self._version:` guards deleted, restoring the original call-through behavior with no DB migration and no client change.

## Out of scope

- INIT-03 Option B (seed ELO from persisted `member_rankings` snapshot / replay-from-snapshot) — deferred to Wave 3 (INIT-08 Option B) because it touches ELO math directly and requires a separate byte-for-byte equivalence test beyond the memo golden test.
- `_compute_stats` caching of derived tier/stats structures beyond the memo described here — any deeper refactor of the stats computation is out of scope.
- Swipe-history compaction (`database.py:355–358` acknowledges a future compaction job) — separate initiative.
- Any mobile or web client changes.
- INIT-08 (session_init slim / optimistic shell) — separate initiative that also benefits from faster ELO, but is not a prerequisite here.
