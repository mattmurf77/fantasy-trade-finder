# First actionable trade: delivery investigation

Research date: 2026-09-21. Source: `4913ad0c68af5e75f864c46cff692ca5f9bf842b`. Scope: read-only code/history inspection, isolated protocol experiment and deterministic transport simulations. No application edits, production generation, release, new services or real device measurements.

## Result and recommended first implementation

The mobile app can already render and act on cards from a running job. The owner path has deliberately stopped publishing those cards until the whole final inventory has passed policy checks and durable evidence recording. Restore early availability by making publication an atomic operation over a **fully checked, durably recorded prefix of the final ordered inventory**. Keep the full inventory and current global ordering. Deliver the first ready card immediately, build toward 20–30, and continue materializing remaining offers.

That is a credible first improvement, but it does **not** demonstrate a fresh search within three seconds. The current bilateral constructor computes a global ordered inventory after its candidate sweep. Exact-order publication cannot precede that barrier without a proven stable-prefix method. If the attributed production constructor time of 13.932 seconds persists, even instant publication after ranking misses the goal. Useful preparation, faster computation, or an explicitly reviewed progressive-order model is still necessary.

The smallest backend-only release can publish validated committed prefixes in the existing cumulative snapshot shape and preserve old clients. The full delivery improvement adds capability-negotiated page responses, a compact status read, a quicker first-card poll schedule, and corresponding mobile cursor/state handling. Do not return only 30 cards to an old client with `status=complete`: it would stop requesting and silently lose access to the rest.

## Where streaming changed

| Source/history | Finding |
| --- | --- |
| `f1be8525` (2026-04-26), Find-a-Trade streaming/pre-generation | Introduced background jobs, `/api/trades/status`, and `_make_progress_cb`; each completed opponent replaced `job.cards` with the currently sorted snapshot. Historical commit prose contains performance claims; no historical phone timings were reproduced here. |
| `0a8093fe`, PR #278 (2026-09-04) | Added `final_checks_pending` so intermediate snapshots could not bypass final balance and whole-team checks. |
| `0e3d6b70`, PR #285 (2026-09-06) | Extended withholding to owner generation, requiring an impression ID for every served owner card before publication; evidence failures withhold the trial. |
| `b33b4da9`, PR #297 (2026-09-17) | Extended withholding and cache/serve enforcement to the shared significance policy. |
| Current `backend/server.py:3297–3323`, `7395–7415` | The historical callback remains, but only updates cards when final checks are not pending. Progress counts can still update if a generator invokes it. |
| Current `backend/bakeoff_runner.py:1607–1655`, `backend/server.py:7600–7609` | Only the current comparison arm streams. Owner generation is quiet, and `_gen_owner` ignores callback overrides. Removing the withholding guard alone would not make the bilateral owner constructor stream. |
| Current `backend/trade_gen_bilateral.py:459–519` | Candidates are already visited round-robin across partners. Accepted survivors receive random trade IDs, then `_rank(survivors)` orders the entire set and applies diversity through a 32-card lookahead (`416–448`). Scores also depend on final rank/count. There is no implemented safe global prefix certificate. |

Restoring the April callback wholesale would reintroduce offers before today's policy/evidence requirements and change initial order. The root cause is broader than one removed callback.

## Current first-card path and publication requirements

1. `POST /api/trades/generate` joins a reusable job or launches a worker and returns its snapshot (`backend/server.py:13860–13883`, `14037–14061`). The API's documented snapshot permits cards while running.
2. The worker completes construction and postprocessing. Final disposition checks run before evidence freezing (`8323–8334`). Owner cards receive `preserve_server_order` but do not enter the public job snapshot at this point (`8358–8372`).
3. `_log_deck_signal_impressions` records every `served_final` card; the owner path rejects incomplete ID coverage, then rebuilds and publishes the full public snapshot (`8428–8468`). Failure clears cards and raises `owner_impression_unavailable` (`8469–8478`, `8513–8514`). The all-inventory evidence call is a first-card barrier.
4. The logger currently enumerates each invocation from zero for `card_index`, generates a new UUID per card, and calls `save_deck_impressions(rows)` once (`4924–4927`, `5101–5119`, `5253`). **Calling it repeatedly with slices is not a safe batching implementation.** Stable impression allocation, global ordinals, retry-safe writes and the shared diagnostic/evaluation context must be preserved across batches. Existing database batching is not the same thing as committing and publishing each actionable batch.
5. Status deep-copies the entire job under the process lock and then builds the public view (`14999–15017`). The public view checks current model/significance and projects current dispositions over all cards (`3016–3079`). Its mobile comment describing a cheap dictionary lookup is incomplete: there is deep copy, a batched disposition/source-interest read, JSON encoding and transfer. A small page should avoid doing those operations for the full deck on every request.
6. Mobile normalizes every returned card (`mobile/src/api/trades.ts:235–299`), then appends unseen `trade_id`s to the deck even while running (`TradesScreen.tsx:2282–2315`). It does not wait for 20 or 30 cards. Server order is preserved for owner/browse cards (`4071–4089`). The browse pager and searching row explicitly coexist (`7933–8007`); the classic top-card branch precedes the running placeholder (`8642`, `8859`).
7. Canvas actions require complete sides, a resolved opponent, a host handler and no active queue request, but not job completion or completion of calculator evaluation (`InLeagueCalculator.tsx:1400–1421`). Opponent resolution depends on the league-coverage query (`427–430`, `599–601`, `649`); cold query/roster/value/prefill work remains a client latency uncertainty. Code inspection supports rendering capability, not measured time to an enabled tile.

Public batches must include existing exact terms, `trade_id`, durable `impression_id`, partner, scoring/presentation fields and `preserve_server_order`. They must not include private ranking boards or raw evaluator diagnostics. Every batch needs the same current authorization, ownership/pick, policy, significance and disposition checks as the final path. A later write failure cannot retroactively make already committed offers lose their historical terms or identity; failed/unwritten cards remain unavailable. Policy invalidation is distinct from a storage failure and may require withdrawing previously ready actionability.

## Polling and first-action measurement

The current poll effect starts after 800 ms; absent opponent progress it multiplies the interval by 1.5 up to 4,000 ms and adds ±10% jitter. Requests are sequential and each next timer starts after the prior response (`TradesScreen.tsx:2170–2237`). The quiet owner path makes the no-progress case particularly relevant. A scheduled idle interval alone can reach **4.4 seconds**, before network, status read, parse, normalization and render work. The attributed four-second production gap is consistent with this code, but was not remeasured here.

The isolated script compares this schedule with a proposal: every 250 ms for the first 3 seconds, every 500 ms through 10 seconds, then every second while no actionable inventory is buffered. The experiment assumes POST already returned at t=0, zero RTT, no jitter, and instantaneous parsing/rendering. The columns below are simulated first responses, not tap-to-tile results.

| Server card ready | Current response / polls | Proposed response / polls |
| --- | --- | --- |
| 1.000 s | 2.000 s / 2 | 1.000 s / 4 |
| 2.100 s | 3.800 s / 3 | 2.250 s / 9 |
| 3.000 s | 3.800 s / 3 | 3.000 s / 12 |
| 13.932 s | 14.500 s / 6 | 14.000 s / 30 |
| 66.316 s | 66.500 s / 19 | 67.000 s / 83 |

Quicker cadence does not win every phase alignment, and raises request load. An equally weighted readiness sweep from 10–70 seconds at 10 ms increments (6,001 artificial phases) gives current median/p95/max detection delays of 1,990/3,790/3,990 ms; the proposal gives 490/940/990 ms. These are properties of simulated schedules, **not** production percentiles. Even a 3.000-second server-ready time leaves no time for actual network/rendering under the owner goal.

Implement fast polls only while the app is focused/foreground and inventory is empty or near depletion. Reset on committed `ready_count`/revision changes as well as generation progress. Once a useful batch is buffered, slow status checks and fetch more when remaining inventory falls below a measured prefetch threshold (start by testing 10 cards). Resume with an immediate lightweight request; cancel timers and stale response application on scope/account/epoch changes. Preserve the server's independent search when the user hides results. A page endpoint should return ready rows promptly and should not wait to fill 30.

Do not introduce long polling by sleeping inside the current web request handler before testing worker/thread availability; it can occupy scarce API capacity. Streaming/push needs deployment/React Native/proxy recovery tests. Faster lightweight polling is the first bounded experiment, with request/CPU/battery costs measured before rollout.

Existing `deck_card_viewed` is unsuitable as the exact first-action endpoint: the exposure clock intentionally requires 500 ms continuous visible time (`mobile/src/utils/offerExposure.ts:4`, `71–83`), sampled every 250 ms (`hooks/useSelectedOfferSignals.ts:27–43`). Add separately registered telemetry carrying one request/job/inventory trace from the Find a Trade tap through response decode to a visible exact card with enabled decision controls. Retain existing exposure semantics. Record blocked coverage resolution, background/foreground, wrong/stale epochs, errors, no-result completion and abandonment; don't count a skeleton or delayed viewed event as the first rendered tile.

## Initial inventory must last until refill

Thirty cards are a working buffer, not a solution to an arbitrary tail. In the synthetic scenario where the first 30 are ready at 3 seconds and no further card arrives until 66 seconds:

| Assumed consumption | Buffer lasts | Resulting empty wait |
| --- | --- | --- |
| 0.5 cards/second | 60 s | 3 s |
| 1 card/second | 30 s | 33 s |
| 2 cards/second | 15 s | 48 s |

These are scenario assumptions, not observed user rates. Continue search/materialization immediately after the first commit, prioritize replenishing this active inventory, and measure first-batch availability, next-page wait and empty-buffer time. For an early first card, the first 20–30 must follow quickly enough to avoid repeated starvation. If the search has fewer valid offers, return all of them and mark completion honestly.

## Proposed transport contract and migration

This is a concrete design for review, not a shipped API.

- New clients explicitly request a versioned paged capability. `generate` may return the first available page immediately. The server retains the entire final eligible inventory under a stable, scoped inventory ID and immutable order; ordinary page size 30 affects delivery only.
- Page responses include inventory ID, worker/materialization status, publication revision, current eligibility revision, ready/total counts, cards, an opaque versioned next cursor, `has_more_ready`, `inventory_complete` and error state. A server-issued cursor counts examined positions, including filtered-out cards, rather than merely returned cards. Bound it to account/league/format/job/version, and validate it server-side.
- Worker completion and client exhaustion are separate conditions. A complete inventory can still have many unfetched pages. The mobile app fetches until the cursor reaches EOF, independent of whether status polling has stopped.
- Mobile normalizers/types must preserve the new fields. Current normalizers discard unknown fields (`api/trades.ts:271–282`), and the poll/deck guards compare `cards.length`, status and opponent counts rather than revision/cursor (`TradesScreen.tsx:2189–2196`, `2286–2315`). Two different 30-card pages must both be applied. Deduplicate retries by immutable action identity, persist the cursor only after successful application, and preserve the currently fronted card through appends/reconnects.
- Explicitly model removals/eligibility revisions and errors after a partial result. Current append-only deck maintenance cannot remove an old local card just because the server no longer returns it. New-client reconciliation must keep exact historical likes/passes while stopping new actions on revoked offers. Do not rewrite an already displayed offer's package under its old impression ID.
- Unnegotiated clients retain the existing cumulative `cards` snapshot and `running/complete/error` values, with no 30-card cap. They can benefit from earlier committed prefixes, but keep the full-response transfer cost. Old mobile's failure surface can be obscured by retained cards (`TradesScreen.tsx:9052–9056`), so explicit partial-error/refill behavior needs new-client handling and tests.
- Allocate impression IDs once per immutable inventory offer and persist them with global served ordinal, exact terms and private proof references before publication. Commit the batch and availability checkpoint atomically; a retry or crash after commit must return the same IDs. Use the existing database/evidence adapter rather than introducing independent unreviewed storage. State publication must be fenced against supersession and model/policy changes.

Protocol rollout order: server capability support with legacy fallback; new mobile that can consume both shapes; canary per negotiated capability; expand after exact-inventory/identity and device checks. Rollback stops assigning new paged inventories and serves compatible existing inventories or a truthful retry state; do not downgrade a paged client to an ambiguous truncated complete snapshot or mint replacement action IDs.

## Isolated experiment and verification

Added only:

- `scripts/research_trade_delivery.py`: standard-library SQLite transaction model, immutable final-order manifest, incremental committed publication, deterministic impression identity, scoped cursors, read-only action identity checks, legacy snapshots, polling/depletion simulations and optional private public-response byte summarization.
- `backend/tests/test_research_trade_delivery.py`: **17 passing tests** via `python3 -m unittest backend.tests.test_research_trade_delivery -v` (latest run: 2026-09-21, 0.454 seconds; test duration is not a performance benchmark).

Tests retain all 1,974 **synthetic** offers in the exact input order over first-1/next-29/subsequent-30 commits, without duplicates or dropped delivery records. They verify current-page retries, short/empty/exact-multiple decks, same-identity recovery after a post-commit crash, whole-batch rollback on injected write failure, retention of previously committed cards, retry continuation, missing proof/failed-check refusal, scope/cursor rejection, exact-term action validation, serve-time failure without unchecked fallback, disposition-aware cursor advancement, detached returned payloads, and full legacy inventory accessibility. Separate tests exercise polling phase/RTT assumptions, depletion arithmetic and deterministic byte aggregation.

The model requires `ranking_complete=True`; it deliberately rejects progressive generation-order publication. Synthetic `checks_passed`/`proof_ref` assertions are inputs to the protocol model, **not implementations of real trade validation or evidence reconstruction**. SQLite is in-memory, single-writer and exercises transaction semantics only. Process-local error status, current eligibility hooks and the open connection used for crash reconstruction are not a complete persistent queue/recovery design. Production leases, concurrent writers, auth sessions, job timeout/supersession and policy epochs remain integration work. This is not an end-to-end app fixture replay and does not establish engine candidate parity, real Postgres performance or a three-second phone result.

`python3 scripts/research_trade_delivery.py` reproduced the tables above. `git diff --check` passed. No application code or UI behavior was changed, so mobile typecheck/build and full application suites were not run for these isolated additions.

The pipeline agent subsequently exported a private final worker response from its isolated frozen-fixture reconstruction: 2,843 constructor offers became 2,354 after significance checks and all 2,354 received durable impressions. This is an actual reconstructed worker response, not a production capture, and its cardinality differs from the earlier 1,974-offer production observation. The constructor fixture alone was not treated as a public-response fixture. Byte analysis ran after the compute agent released its timing window; no raw card IDs, names or private proofs were emitted.

| Reconstructed response representation | Full 2,354 cards | First 30 cards |
| --- | --- | --- |
| Exact exported Flask response, source bytes | 3,218,422 | Not separately exported |
| Exact source compressed with gzip level 6 locally | 259,015 | Not separately exported |
| Consistent compact JSON, UTF-8, sorted keys, `ensure_ascii=False` | 2,980,527 | 37,348 |
| Same compact JSON, gzip level 6 locally | 252,540 | 4,075 |

With matched compact encoding, the first-30 body is 98.75% smaller uncompressed and 98.39% smaller compressed. This comparison keeps the original response envelope and slices only `cards`; a real cursor/page envelope adds small unmeasured overhead. It demonstrates a payload opportunity on the reconstructed final cards, not a first-action latency saving. Raw-source SHA-256: `b405079ba575acd1e59ed737a32d28fa60103694e4092daaaf6b82f2c5a591bb`. The private export remains outside Git at `/private/tmp/latency-pipeline-20260921-public/private-public-snapshot.json`.

Reproduce with `python3 scripts/research_trade_delivery.py --public-response /absolute/private/response.json`; output includes only counts, source/compact byte sizes, deterministic gzip-level-6 sizes and digests. The gzip figures do not establish actual wire compression. Production byte reduction, server serialization CPU, mobile decoding and rendering still need direct measurement. The separate ~3.2 MB production response and ~4-second delivery gap remain attributed observations from the sibling investigation, not verified production measurements by this experiment.

## Implementation-sized follow-ups and acceptance

1. **Committed prefix, existing shape:** Extract the finalized inventory/evidence context; preserve all checks, final order and exact terms; refactor evidence allocation/writes for stable global IDs/ordinals; publish committed prefixes through existing running snapshots. Instrument first commit and all-commit timing. Rollback returns to full-deck publication. This mainly shortens post-construction waiting and needs no new mobile binary for basic visibility, but cannot by itself solve a constructor slower than three seconds.
2. **Negotiated pages and first-action delivery:** Add compact status/page reads and mobile revision/cursor application, adaptive foreground polling, depletion prefetch and partial-error states. Include actual visibility/actionability timing, new taxonomy registration and scoped epoch tests. Rollback preserves legacy snapshots and existing action identity. This needs backend API/architecture/data/analytics documentation plus mobile release evidence before rollout.
3. **Fresh-search goal:** Combine exact compact ranking, compute reductions and version-valid prepared inventory. If fresh global ranking still exceeds the budget, compare a proved stable-prefix algorithm with an explicitly reviewed progressive presentation contract. Progressive construction must finish the same candidate universe and preserve displayed cards while documenting initial quality/diversity versus the final best inventory. This research supplies no certificate or measurements qualifying either alternative.

Before any release, run full affected backend/mobile/web CI and differential tests over real frozen final inventories, then execute a physical TestFlight checklist (unrun here): warm cached search; cold organic search; selected multi-asset search; fewer-than-20/zero results; first card while job still running; pages 1–3 with equal card counts; action during batch commit; background/resume and duplicate response; scope/account switch; pass/like from another device; roster/pick/model invalidation; failed first write versus failed later write; buffer exhaustion then refill; superseded/timeout job; old binary's access to every final offer. Verify the fronted card, exact impression/terms and enabled controls stay correct, and record tap-to-tile, tap-to-30, refill waits, total completion, failure/abandonment and byte counts separately.
