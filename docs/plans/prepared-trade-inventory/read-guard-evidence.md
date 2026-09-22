# Adopted read guard and bounded adoption evidence

September 22, 2026. Lane C; no production access or deployment. Parent owns runtime/server integration and release.

## Read contract

`prepared_trade_read_guard.capture(server, scope, *, expires_at, now=None)` captures strict detached JSON with schema, exact scope, capture/expiry clocks, hashed safety components and an integrity checksum. Expiry is no later than the supplied artifact/card bound or thirty minutes after capture. `valid(server, guard, *, scope=None, now=None)` fails closed; `filter_cards(server, cards, *, now=None)` preserves ordinary cards and order, while validating trusted runtime `_prepared_guard` attributes once per distinct guard per call. Guard JSON is not client authority and never enters public card output.

The local receipt binds full trade/ranking configurations and flags, deployment/model version, current global player attributes and market seed, available player-evidence metadata, raw injury/position availability and its 48-hour freshness class, cached league metadata, and semantic league/member/draft-pick/recorded-pick SQL contents. Harmless surrogate IDs, refresh timestamps and JSON whitespace do not invalidate unchanged sources. Missing required local inputs are a cache miss, not permission to fetch or silently repair them.

Explicit rank/outlook edits still require the existing epoch fence. Ordinary trade swipes/likes/rank training are deliberately absent from this local receipt; current dispositions remove their affected offers instead of discarding the entire inventory. Account lifecycle authority remains in the existing deletion/write fences.

No external provider is fetched per poll. Provider state is refreshed at admission; the guard detects subsequently observed local changes, not an unobserved remote transaction. The thirty-minute interactive bound is not a claim of real-time upstream freshness. Parent integration checks jobs before/after serialization and cache reuse, and trusted runtime cards on pending projection. Guard attributes must be attached after a yielded batch commits, never before the codec's unchanged-card verification.

## Verification

- 32 focused guard tests passed; peer B independently ran all 32. They cover config/market/player/pick/roster/template changes, unchanged sync, disabled/expired/malformed sources, wrong scope, SELECT-only/no-fetch behavior, ordinary-action noninvalidation and per-read deduplication.
- 21 real runtime integration tests passed in the final Lane C combined run. This included full 64-offer adoption, original IDs/proof/fit metadata, actual restart-style swipe ignoring forged client terms, empty inventory, claim-window market swap, late-prefix invalidation, and a pure later writer outage preserving only the already-durable 30.
- 180 combined guard/runtime/payload/capture/cohort tests passed in 23.23s. Parent subsequently added further route regressions; its final exact-head run owns those counts.
- Named negative control: an isolated test-process override making `valid()` always true caused `test_local_market_change_rejects_adopted_status_and_pending_without_erasing_evidence` to fail at stale job acceptance. Normal source passed. No file was changed for this sabotage.
- Independent compressed-store review passed all 80 store tests in 11.92s at source `2bdc7dce3f48ea1337231c7430b30d5b08faaa03cdbde20c3ea1bdeb0fa39a85`. Fixed zlib/base64 decoding bounds output before parsing and rejects incomplete/trailing streams; logical checksums and retry identities remain unchanged. Byte-limit failure preserves prior artifacts and never truncates offers.

Frozen guard source: `9ca92c9e767215a2f6aa84d76c1b89eca03e49e14002d0a52a28d66c2d99c7d0`. Guard tests: `660ecac8f0044a873251d67cd7eee40ecfaa8bb0d9d9baa0e848827995b8c46e`. Payload source remains `13e9b8548695c8dcd0935f5f45770c51a5f5e6e0094c78ddc57b7d173b3078f5`.

## Local bounded measurements, not product latency

Private reproducible harnesses: `/private/tmp/prepared-adoption-benchmark.FaKu2s/test_measurement.py` and `test_large_measurement.py`. Both use actual constructor output, payload codec, SQLite durable adoption and complete uncapped inventory. Providers and the full admission receipt are mocked; the new local read guard is real. App import and background preparation precede the adoption clock. CPU was shared with other validation. First-30 timing measures transaction completion before publication, not HTTP receipt or a device's first actionable tile.

| Actual emitted/adopted offers | First30 evidence commit | Full adoption | Logical envelope bytes | Stored SQL bytes | Process peak RSS |
|---:|---:|---:|---:|---:|---:|
|64|0.493s|0.730s|1,875,028|77,855|179,896,320B|
|512|3.034s|8.518s|15,360,913|475,911|374,702,080B|

Logical inventory bundles were 1,873,529B and 15,354,229B respectively. RSS includes application import and construction, not incremental cache cost and not a Render footprint prediction. Exact original identities/order/counts survived; each first commit occurred with zero pending cards. The 512 case published 30/100/100/100/100/82.

The 512 case uses 32 synthetic opposing teams with 16 unique assets each and one outgoing asset. It is a bounded stress fixture, not a typical league distribution. A first attempted four-team, 256-assets-per-team fixture honestly emitted only 64 because the unchanged constructor pool selected 16 per opponent. No pool/budget/model setting was increased, no proof was cloned, and no offers were truncated.

Source implementation identities over measured adoption were `383260220084bfe0531c8cd2fda4cc62c8819984095bcd03ffcd2cc6ea92909c` for 64 and `47e1c9c89591e6f5e5302cd5aa9c9e137229ebef37ccd07cd209dba879c72b8f` for 512; each remained stable within its run. Later safety fixes require final-head validation separately.

The 512 case already exceeds three seconds before provider/network/device costs. These measurements do **not** establish the product KPI or the largest real-inventory memory envelope. Compression protects SQL transport but does not eliminate expanded JSON/proof allocations. Current limits are 64MiB decoded and 2MiB stored; oversize inventories fail visibly rather than becoming partial decks.

Reproduction uses `/private/tmp/ktc-benchmark-venv/bin/python`, scratch `DATABASE_URL=sqlite:////private/tmp/prepared-read-guard-tests.sqlite`, local `FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv` and `FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, from the shared prepared-offers worktree. The private benchmark invokes `python -m pytest -p backend.tests.conftest <private-test-path> -q -s`. No production source or credentials are loaded.
