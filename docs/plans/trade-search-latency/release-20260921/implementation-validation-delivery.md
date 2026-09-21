# Committed owner prefixes: implementation and validation

Date: 2026-09-21. Scope: backend implementation authorized by the owner and bounded by [scope.md](scope.md). This record covers the delivery agent's worker edits and focused tests. Deployment, full CI and combined replay results belong to the parent release record; nothing here independently establishes a release or device latency result.

## Implemented behavior

The worker completes the existing constructor, global ranking, owner revalidation, final policy/roster/significance/presentation and disposition checks before making any owner offer available. It then calls `_log_deck_signal_impressions` once with the compute agent's streaming interface: `structured_features=True`, `initial_publication_batch_size=30`, `publication_batch_size=100`, a committed-batch callback and a liveness predicate.

The logger retains one full-job attribution/context preparation and global `card_index` enumeration. Its database writes commit a first batch of up to 30, then batches of up to 100. Only after each successful write does `_run_trade_job` serialize those committed cards, stamp their durable impression IDs, and append them to a cumulative job snapshot. Every offer keeps its original trade ID, exact terms, final order and one persisted impression identity; no output/search cap, paging contract or client API field was introduced. Non-owner logging/publication uses its existing full-deck path.

Owner cards no longer undergo an unused full-deck public conversion before evidence recording, followed by another full conversion after recording. They are converted once per successfully committed publication batch. The callback validates exact contiguous order against the finalized inventory and rejects missing impression IDs. It marks only those committed card objects `owner_published=True`, preserving the pending-trade safety gate.

Each cumulative snapshot is a detached list, so building the next prefix cannot mutate a list already copied by a poll. Its assignment, `owner_published` markings and `final_checks_pending=False` occur under the job lock. The flag is cleared on the first safe prefix, or on a successful empty inventory; no unchecked generator callback is restored. A first-publication application log records job elapsed time and card count. It is a server timing, not tap-to-tile telemetry.

The batch predicate and callback check job liveness plus current owner model/significance versions. These version reads access in-memory config/constants, not the database or all cards. Input invalidation, model/significance drift, supersession or an already terminal timeout prevents further publication, including a change between commit and callback. Such a late commit may leave durable evidence that never became actionable; its card objects are not marked published. The cache agent's `_finish_trade_job` replaces unconditional terminal mutation: a late worker cannot change an existing error into success or emit `trades_generated` for that success.

A failed first write publishes zero cards. A failed later write retains only the earlier committed snapshots and their identities, then returns the existing terminal `error` status with `owner_impression_unavailable`; it never publishes the unwritten suffix or substitutes unchecked cards. Existing successfully published terms/evidence remain available for historical attribution. Significance diagnostics and the targeted-search run ledger record the retained published prefix on a storage failure, rather than incorrectly reporting zero or the entire unwritten inventory. Explicit revocation clears current availability through the cache agent's fence without deleting durable evidence or rewriting historical offers.

The current 60-second hard-timeout constant and five-minute cleanup cadence are unchanged. The release now honors an error already applied by cleanup rather than allowing a late worker to revive it. A slow job may therefore truthfully stop with a partial committed inventory and an error; that is an incomplete failed search, not a successful 30-card cap. The first-batch result does not establish the owner's three-second fresh-search goal. Existing old-client cumulative polls can still transfer large final responses and can still back off to roughly four seconds.

## Executed focused checks

Command, using local Python 3.14 and an isolated database URL:

```sh
DATABASE_URL=sqlite:///:memory: python3 -m pytest backend/tests/test_owner_batch_publication.py -q
```

**19 passed in 2.95 seconds** after independent review and the targeted-run ledger correction. Test duration is not a performance benchmark. These tests exercise the actual worker, real owner constructors, real impression logger and isolated SQLite, rather than the research protocol model.

- Both owner v1 and bilateral generate the real synthetic 64-card fixture: the real `/api/trades/status` returns 30 durable actionable identities with `status=running`, followed by all 64 in exactly the finalized order. Every first-prefix row is already queryable with its true global ordinal before the publication callback.
- Real synthetic inventories of 0, 1, 19, 30 and 160 offers finish honestly. The 160-offer inventory publishes `[30, 100, 30]`, keeps all offers and persists global indices `0..159`; no per-batch ordinal restart or output cap.
- A null logger result fails closed. Injected failure on the first or second write exposes respectively zero or 30 cards for both organic and targeted searches; the failed/unwritten suffix has no published identities. Prior snapshots/IDs remain unchanged, and targeted run-ledger `deck_size` agrees with the retained prefix.
- Input invalidation, timeout, supersession, owner-model switch and significance-policy change immediately after the first batch stop the tail. Existing terminal errors/timestamps survive; no successful `trades_generated` event is emitted.
- An invalidation between the first database commit and callback leaves 30 durable evidence rows but zero public cards and zero `owner_published` markings.
- An explicit real `/api/trades/swipe` pass during the first running batch joins its durable impression, before remaining materialization completes. Publication alone creates no decisions or outcomes; only that explicit action creates one pass outcome. Subsequent batches retain the earlier public terms/identity.

Four pre-existing focused checks also passed before the new suite: the 64-card exclusive/ghost/presentation path, owner publication before evidence, and both raise/incomplete first-write failure cases. The compute agent separately owns logger-level transaction/compaction equivalence tests; the cache agent owns admission/invalidation tests. Parent-owned full-suite CI and pinned production-like replay must pass before release. Python 3.12 CI remains the supported-version gate.

Named sabotage evidence required by `backend/tests/CLAUDE.md`: **`publish-before-evidence-commit`**. A temporary pytest plugin recompiles `_log_deck_signal_impressions` only inside the test subprocess, moving `on_batch_committed(...)` before `save_deck_impressions(rows)`. The two parametrized real-worker first-prefix tests went **RED: 2 failed in 0.40 seconds**, because their callback could not find the supposedly actionable impression in the database; both workers correctly surfaced an error rather than completing. The ordinary subprocess without the plugin then went **GREEN: all 19 passed in 2.95 seconds**. Shared application source was never sabotaged or reverted during concurrent work. The isolated plugin is retained at `/private/tmp/fleeced-publication-sabotage.w8cDpn/publication_sabotage_plugin.py`; the red command uses `PYTHONPATH` to that directory and `-p publication_sabotage_plugin`, targeting `test_first_30_are_durable_running_and_full_inventory_keeps_order`.

## Existing-TestFlight manual checklist

All physical checks below are **unrun** by this agent. No new mobile binary is required for the existing cumulative snapshot contract; record the installed TestFlight build/device/network for any results.

1. Start a cold organic search with at least 31 eligible offers. Confirm a real decision-enabled card appears while the search remains running, then inventory grows. Record tap-to-first-enabled-visible-card, first 30, first refill and total completion separately; do not substitute the server log or delayed viewed event.
2. Like or pass the first card before generation finishes. Confirm its decision succeeds once and subsequent appends do not replace the fronted card, alter terms or undo the disposition. Navigate back to the offer and verify original attribution.
3. Exercise a search with more than 130 results and reach the last offer. Confirm all eligible results remain accessible after completion and no 30/100 cap is applied. Repeat with fewer than 30 and zero eligible offers for honest completion.
4. Repeat for selected send/get assets and a scoped partner. Verify original scope, final ordering and policy behavior remain intact.
5. Open the search on a second device or return from background after the first batch; confirm cumulative results catch up and retain IDs without duplicate decisions. Verify cold league-coverage loading does not leave an apparently ready canvas action disabled without being accounted for in timing.
6. Change rankings/outlook or force a replacement search during work. Confirm the superseded inventory stops growing, new work uses current inputs, and historical likes retain their terms.
7. Under an isolated fault-injection environment, fail the first evidence batch, then a later one. Confirm no uncommitted card is visible; earlier committed cards survive a later storage failure with truthful terminal error/retry behavior. Observe the existing binary's failure copy after its partial deck is exhausted; the backend error must not be reported as successful full completion.
8. Under an isolated timeout/invalidation scenario, verify that a late worker never restarts delivery or changes the terminal error to success. Check model/significance-version changes and an invalidation racing the first commit.

Do not inject failures or synthetic offers into production to execute this checklist. Real bounded deployment health/identity observations are separate from these isolated failure tests.
