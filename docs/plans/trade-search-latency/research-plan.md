# Trade generation latency: full-pipeline research plan

Prepared: 2026-09-20. Revised: 2026-09-21. Status: owner authorized execution of research and isolated experiments; no production release or paid infrastructure changes in this phase.

Execution update, September 21: the first three-agent research wave and parent review are complete. See [consolidated results and remaining gates](execution-20260921/README.md). Thirty-one research tests pass; the three-second goal, production-shaped integration and device/load qualification remain unproven. The full plan below remains the qualification backlog, not a claim that every experiment has run.

Source baseline: freshly fetched `origin/main`, `4913ad0c68af5e75f864c46cff692ca5f9bf842b` (PR #302). Research branch: `codex/trade-latency-research-plan`; a matching copy of this plan is saved in the canonical project for access. Preserve unrelated work in the canonical checkout. Earlier [latency investigation](https://github.com/mattmurf77/fantasy-trade-finder/blob/4913ad0c68af5e75f864c46cff692ca5f9bf842b/docs/plans/trade-search-latency/README.md) provides historical evidence, not current deployment status.

## 1. Objective and recommendation

Make finding an actionable trade feel fast without considering fewer possibilities, reducing eligible offer access, changing personal rankings, or weakening bilateral suitability and safety checks. Prioritize improvements to existing Python, data representations, search algorithms, persistence, and cache reuse. Investigate infrastructure changes as controlled comparisons, not as the assumed answer.

The leading hypothesis is that generation does too much repeated work and fully materializes too much data before the user can act. The likely solution is a combination of cheaper evaluation, versioned reusable inputs, incremental recomputation, and a faster publication path—not merely a faster generator or a larger server. This is a hypothesis to test, not a completed diagnosis of the latest search.

First investigate these options in order:

1. Measure the complete path, including failed and abandoned jobs.
2. Prototype safe early publication of 20–30 cards and responsive delivery alongside profiling; do not postpone first-action work until total-worker optimization is finished.
3. Eliminate repeated CPU work, database reads, serialization, and writes; compare full compact ranking followed by early page hydration with progressive construction while retaining complete search coverage.
4. Make existing app-open preparation and cached results reliable; add event-driven incremental refresh and targeted nightly preparation where they save real work.
5. If needed, isolate generation from API traffic using workers on Render and shared job state.
6. Consider another platform only if a measured requirement remains unmet.

No production/configuration changes, new paid infrastructure, scheduled jobs, or deployment are part of writing this plan. Implementation experiments must use isolated data and go through the repository scope/evidence/release workflow.

## 2. What we know—and do not know

Production was checked read-only on September 20 at approximately 23:02 UTC. Render reported PR #302's commit live. Since the bilateral activation, the query found one recorded engine run using `owner_v2_bilateral` and one corresponding-time completed interactive worker event:

| Measurement | Observation | Interpretation |
| --- | --- | --- |
| Completed worker, `trades_generated.props.gen_ms` | 66.316 seconds | Server worker duration, not tap-to-card latency |
| Engine/composition, `bakeoff_runs.total_ms` | 13.932 seconds | Narrower engine timer |
| Final offers reported | 1,974 | Output cardinality, not number of candidates examined |
| Arithmetic difference | 52.384 seconds | Unallocated worker time outside that engine timer; not proven database time |

The records were associated by timing in the bounded aggregate check, not a shared end-to-end trace ID. Confirm exact job correlation before treating the subtraction as an authoritative stage breakdown. Input preparation, postprocessing, persistence, contention, and scheduling may all contribute. One completion is not a median, p95, throughput test, or proof that every request takes a minute.

### Incorporated findings from “Fix slow trade generation”

The sibling plan `docs/plans/trade-generation-performance/research-plan.md` reports a more detailed September 20 log inspection. Treat these as attributed historical observations until original receipts or fresh observations corroborate them, not new measurements performed by this plan:

- Session-init began the job at 17:34:21 UTC; Find a Trade joined it at 17:34:25; the first large response was at 17:35:31. Warming/reuse worked for that request but did not make it ready quickly enough. Audit reliability without presuming pregen is broken.
- Generation took about 13.9 seconds and produced 2,390 candidate cards. Approximately 17.5 seconds then elapsed to final presentment and 33.5 seconds from presentment to storage completion. Those intervals include mixed work, not SQL alone.
- Approximately four seconds elapsed from worker completion to the next result response; the access log reported about 3.2 MB. Prioritize delivery/polling and response-size experiments together with early publication. Distinguish logged response size, compressed wire bytes, parse time and render time.
- Render inspection reported one Standard web instance and Basic 256 MB Postgres in Oregon, with one Gunicorn worker and a 120-second timeout. The Free blueprint is not evidence of live free-tier sleeping. Verify live topology before any capacity recommendation.

If generation itself still takes about 14 seconds, storage optimization alone cannot meet three-second fresh first-action latency. A qualifying solution must accelerate construction, reuse current precomputed work, publish safe partial results, or combine these.

Historical September 12–19 data showed 18 interactive completions at 18.14–75.44 seconds, median 43.06 seconds, under earlier code/models. A frozen local construction-only replay measured the new model at 5.911 seconds for 53,172 evaluations and 2,843 candidates. Neither historical production timing nor local construction timing is a current end-to-end SLA.

Code already contains:

- App/session-init pre-generation using the same saved fairness preference as Find a Trade (`mobile/src/api/auth.ts:sessionInit`, `mobile/src/api/tradePregen.ts`). Verify actual hit rates, not just code presence.
- Process-local jobs and cache dictionaries in `backend/server.py`, with a 30-minute pregen window. Selected assets/partners bypass the shared organic cache.
- Thread-based generation via `_kickoff_trade_job`; `_run_trade_job` does substantial work after construction.
- Owner publication dependent on final checks and successful durable impression recording. Bypassing this requirement is not an acceptable optimization.
- Paged, transactional writes and shared diagnostic snapshots in `backend/database.py:save_deck_impressions` and `backend/deck_diagnostics.py`. Do not propose batching or normalization as if neither exists.
- Flag-gated weekly replenishment through `_run_weekly_replenishment` and `_replenish_deck_for`, processing user-leagues synchronously inside the tick path. Presence in code does not establish that the flag, schedule, or useful cache reuse is active.
- A `_JOB_HARD_TIMEOUT` constant of 60 seconds. Trace its enforcement against a 66-second completion, polling, supersession, and cleanup; the constant alone does not prove a timeout occurred.

The repository Render blueprint specifies one Gunicorn worker and resource plans, but these may differ from the live dashboard. Verify actual plan, CPU, RAM, regions, database limits, start command, networking, and deployment settings. The release check found auto-deploy disabled despite documentation suggesting otherwise; do not deploy by assumption.

## 3. Non-negotiable behavior

- No lower candidate pools, per-pair budgets, total search budgets, narrower team coverage, or new card caps disguised as performance wins. Record current limits and whether they are exhausted. Uncapped output is not exhaustive combinatorial search today.
- Preserve personal-preference-led targeting and selling, outlook/needs, market terms, both-manager support, significance, diversity, selected-asset intent, roster legality, pick ownership, and all disposition/authorization checks.
- Start with exact behavioral parity. Any algorithm change that changes coverage, order, or acceptance rules is a separate model experiment, even if faster.
- A smaller network page is permitted only if the complete eligible inventory remains accessible and the search still completes. Pagination is not a search cap.
- Freshly generated alternatives never rewrite historical liked/matched offer terms or their valuation-at-offer evidence. Revalidate current eligibility before new actions while retaining historical context.
- Precompute must not create likes, matches, sends, fabricated views, notifications, or implicit user consent. Do not expose another manager's private ranking board.
- No fake users, benchmark traffic, destructive SQL, or synthetic trade generation against production. Production observation is bounded/read-only unless separately approved.

## 4. Success criteria: speed to first action is the primary KPI

Owner clarification: **three seconds from tapping Find a Trade to seeing the first actionable offer tile is the product goal and one of the app's most important KPIs.** The prior experience returned an initial group of cards before the rest of generation completed. Investigate that implementation and what removed or prevented it. Aim to make an initial batch of 20–30 cards available so the user can keep deciding while work continues. This is a delivery batch, not a cap on candidates or offers.

The three-second goal is owner-set; p95 is the proposed engineering qualification percentile, not an owner-approved allowance for slow requests. Report the percentage of all valid taps meeting three seconds, p50/p95/p99, and failure/abandonment counts. Cold, warm and selected searches must be reported separately; a high warm-cache hit rate must not hide a slow fresh search. Other targets below remain proposed, not delivery promises.

| Experience | Initial target |
| --- | --- |
| Valid cached search to first actionable rendered card | p95 ≤ 1 second |
| Find a Trade tap to first actionable rendered tile | Owner goal ≤ 3 seconds; proposed qualification p95 ≤ 3 seconds |
| Initial working inventory | Aim for 20–30 actionable cards; never delay the first tile solely to fill the batch |
| Fresh selected-asset/More Offers search | p95 ≤ 3 seconds |
| Complete fresh organic inventory ready | p95 ≤ 10 seconds, initial stretch target |
| Eligible candidate/card coverage for parity changes | Identical IDs/terms; identical ordering unless explicitly approved |
| Safety, authority, attribution, evidence reconstruction | No regression |

Also measure error/timeout/abandonment rate, API responsiveness during searches, peak memory, CPU-seconds, database statements/bytes, fresh cache-hit rate, precompute utilization, stale-result rejection, and cost per useful completed search. Set concurrency qualification from real peak demand plus headroom; probe 1, 5, 10, and 25 simultaneous isolated searches to locate the saturation point rather than claiming those levels are all production requirements.

Measure two separate client events: tap → first actionable tile (the speed KPI), and tap → first actual Yes/No decision (a behavioral KPI that also includes human deliberation). A spinner, skeleton, unvalidated placeholder, backend-ready event, or disabled card does not count as a visible actionable tile. Record tap → initial batch ready, first → next-page wait and the frequency/duration of running out of ready cards. A fast first card followed by a long stall is not a successful experience.

## 5. Workstream A — reconstruct the actual end-to-end lifecycle

Trace mobile entry → request → authorization/session → source freshness → job deduplication → input capture → candidate construction → scoring → final policies → ordering/diversity → public card assembly → durable evidence → publication/poll → network decode → first visible actionable card.

Map every entry point: organic Find a Trade, selected send/get canvas, specific partner, trade-chip More Offers, league buy/sell, app-open pregen, weekly replenishment, and Team Overhaul where it shares the constructor. Identify shared functions versus separate caches, policy/order layers, and transport contracts. Do not optimize one path while breaking the others.

Deliver a code-cited execution map and input dependency table. For every stage record ownership, call count, repeat work, caching scope, data freshness, side effects, failure handling, locks, and whether it blocks the first usable offer. Distinguish serial critical-path work from overlapping tasks.

Required checks:

- Follow `_trade_job_is_fresh`, model/presentation/significance checks, supersession, polling and cleanup. Identify every invalidation and miss reason, including saved fairness/intent mismatch, selected scope, logout, league switch and deployment.
- Trace ESPN/Sleeper roster, player and pick sync: which provider requests run during launch/search, when snapshots are reused, and whether a slow provider blocks all generation.
- Identify all database calls, repeated loads, per-card queries, connection waits, row locks, transaction scope and payload assembly.
- Identify duplicate ownership/significance/valuation checks. Reuse a verified result only when exact package, input versions and policy version are identical; never simply remove a serve-time freshness check.
- Audit process-local sessions/jobs/caches before proposing more Gunicorn workers or replicas. Polling must find the job on any instance; a deploy must not silently lose prepared inventory.
- Trace whether an abandoned mobile request cancels useful generation or leaves duplicate work running. Separate cancellation of UI waiting from cancellation of shared work.
- Inspect Git history for the previous early-card response/progress callback, then compare it with the current owner path. Identify which requirements caused full-deck withholding and how to meet those same requirements per published batch. Preserve the reason for the guard rather than restoring an unsafe callback wholesale.

## 6. Workstream B — instrument and establish a reproducible baseline

Use one correlated trace/job identity across backend stages and client timings. Register any new telemetry under the existing analytics taxonomy and distinguish generation, availability, display, and user decisions.

Capture monotonic elapsed time and CPU time for: queue wait; source fetch/sync; DB checkout/query; input assembly; each opposing-team search; scoring components; duplicate elimination; final policies; sort/diversity; card annotations; snapshot freezing; JSON encoding; compression/hashing; snapshot/impression SQL; commit; ready publication; polling delay; transfer/decode; rendering. Record counts and bytes at each stage, plus cache miss reason, model/config/schema versions and input version IDs. Do not log raw credentials or private boards.

Instrument phases before concluding that the unexplained 52 seconds is storage. Use sampling/allocation profilers in an isolated production-like environment, including wall time versus CPU, memory allocation/GC, lock waits and SQL round trips. Collect PostgreSQL execution plans on the replica/fixture; avoid expensive production `EXPLAIN ANALYZE` and global profiling changes.

Build replay fixtures with captured immutable inputs, private storage, fixed seeds, deterministic tie-breaking, pinned Python/dependencies, deployed model/config and production-sized resource limits. Keep current source truth separate from historical reconstruction limitations.

Benchmark matrix:

- FFv3 and Newtown/ESPN, then representative 8/12/16-team leagues, different lineup/scoring formats, sparse/complete personal boards, every outlook, picks and large rosters.
- Small, typical and high-output decks; selected multi-asset packages; no-result searches; dismissed and repeated offers; expired/inbound interests.
- Cold after deploy, warmed inputs, completed cache, concurrent same-key callers, simultaneous different users, changed roster/rank/outlook/market/config, slow provider, DB pressure and worker restart.
- At least 30 repeated isolated runs per key benchmark cell where feasible; separate cold/warm measurements and avoid claiming p99 reliability from a tiny sample. Use larger repeated stress cohorts for tail analysis.

Randomize before/after run order and avoid overlapping CPU-heavy benchmarks on the same host. Gate on accounting for at least 95% of end-to-end wall time, handling overlapping spans and clock differences correctly, and identify the three largest contributors. Calculate the remaining serial critical-path lower bound; parallelizing other work cannot eliminate it.

Output: stage waterfall, flamegraph, SQL/byte budget, cache funnel, failure funnel, saturation curve, and reproducible baseline manifest. Include unsuccessful/superseded jobs instead of survivorship-biasing toward completions. Mark the 95% gate unfulfilled when client/network or other spans are unmeasured rather than treating local timings as full coverage.

## 7. Workstream C — code and model experiments first

Run each experiment independently against the same fixture/config/hardware, then measure combinations. Rank by measured critical-path savings, exact parity, complexity, memory and operating cost—not intuition.

### C1. Compute immutable facts once

Profile opportunities remaining after PR #300: format-specific market coordinates, personal tiers/ordinal preferences, age and availability, team outlook/needs, lineup baseline, draft-pick prices, tag/rule lookups, per-player asset features and pair compatibility. Cache within an immutable search context first; then test versioned cross-request reuse.

Compare incremental lineup impact evaluation with full lineup reconstruction. Validate edge cases in flex/superflex, position eligibility, cuts, depth, picks and selected packages. Avoid incorrectly making package-dependent stud tax or bilateral utility additive.

### C2. Search exactly, but evaluate expensive components less often

Use canonical asset/package identities to avoid constructing/evaluating the same exact trade through multiple paths. Precompute reusable pair/companion terms, cheap necessary-condition bounds, indexed market ranges and incremental package deltas. Reject early only where a proven bound implies the full evaluator would reject; never add a heuristic filter that quietly removes plausible offers.

Compare vectorized numeric arrays/batched evaluation with Python object-heavy loops. Preserve threshold behavior and deterministic ties; floating-point differences near fairness/support cutoffs need explicit tests. Consider a compiled hot kernel only if profiling shows a stable, dominant numeric hotspot and simpler changes are insufficient.

Consider search-order and branch-and-bound improvements, but with care: with existing finite budgets, changing traversal can change which candidates are reached. Exact-parity experiments must hold the candidate universe fixed. Broader exploration or learned ordering is a separately measured model-quality experiment; no learned pruning or beam-width reduction as a latency shortcut.

### C3. Compact ranked candidates; defer presentation work

Test keeping compact IDs, score components and evidence references for the full search instead of eagerly building thousands of rich public cards. Complete the same global scoring/ranking and diversity selection, then hydrate and durably publish an initial page; continue the rest in the background or on page demand without reducing accessibility.

This primarily reduces time to first action, not necessarily total compute. Benchmark both. Global diversity and ordering may require a complete ranking pass: do not show the first completed opposing team's mediocre offer as the globally best one. An earlier anytime search needs a defensible quality-bound/stable-prefix design or an explicit product contract change.

Use stable cursors and versioned inventory so newly prepared cards do not reshuffle what the user is deciding on. Exact liked/declined identities survive paging, retries, back navigation and another device. Do not send an ever-growing full JSON deck on every poll if a compact status plus incremental page suffices.

**First-class experiment: initial 20–30-card response.** Compare (a) a valid prepared inventory with fast serve-time checks, (b) full compact scoring followed by early batch hydration/persistence, and (c) progressive construction with safe batch publication while all remaining search work continues. Instrument time to first tile and batch depletion for all three. Each published card must already pass the full required eligibility/valuation checks and have durable exact-offer evidence; remaining unpublished inventory may finish later. Persist each publishable batch atomically with retry-safe identities and explicit ready/computing/complete/error state.

For progressive construction, distribute initial work across partners and high-quality personal targets rather than allowing the fastest opponent or easiest package to dominate. Measure initial-batch quality, preference fulfillment, diversity and overlap with the completed search's best offers. Provisional ordering may differ from the final global order; label that as a presentation/model-contract decision requiring review, not exact-parity optimization. Keep displayed cards stable, expose the remaining qualified inventory as it becomes ready, and never cancel the remaining search just because the first batch is full. If fewer than 20 valid cards exist, return those promptly and explain completion; never weaken rules to fill the batch.

### C4. Shrink evidence work without losing evidence

Measure the existing normalized snapshot design before changing it. Test capturing immutable request/board/roster/model context once per job, reusing content-addressed references across all cards, reducing repeated deep copies/JSON round trips/hashing and storing compact per-card deltas.

Benchmark current paged inserts against tuned batch sizes, fewer lookups/upserts, conflict overhead, transaction length and, only if useful, a staging/COPY approach. Include memory peaks and failure atomicity; huge writes previously caused database memory problems.

Separate generation inventory, offer availability and actual exposure in the data model if adopting lazy materialization. Every actionable card still needs a durable identity, exact terms, both-side valuation context, attribution and required policy proof before publication. Optional enrichment may move off-path only behind a durable, idempotent outbox/snapshot that preserves reconstructability through crashes. Never replace required evidence with an untracked fire-and-forget task.

### C5. Remove redundant I/O and transport work

Batch reads; reuse captured preferences; inspect indexing and connection pooling; shorten transactions; avoid holding a connection during CPU work. Compare serialized bytes, compression cost, pagination, polling interval and status endpoint work. Test adaptive polling and supported push/streaming delivery alongside C3: a roughly four-second delivery gap would consume the entire first-action budget even after fast server readiness. Include background/resume, reconnection, cancellation and battery/request load. A transport rewrite alone cannot fix a minute-long worker.

## 8. Workstream D — do useful preparation before the tap

Prefer a layered cache over indiscriminately generating a complete deck for every account nightly.

| Reusable layer | Preparation trigger | Invalidation/freshness basis |
| --- | --- | --- |
| Shared player/market/format facts | Source refresh; scheduled refresh | Source edition, scoring rules, model version |
| League rosters, ownership, lineup baselines | Provider sync; relevant league change | Authoritative roster/pick/settings versions |
| Per-manager preferences and team plan | Rankings/outlook/tags/needs change | User/format/league preference versions |
| Team-pair evaluation substrate | Either relevant team changes | Both teams plus market/policy dependencies |
| Complete ranked inventory | App open, measured high-use windows, explicit search | Exact full request fingerprint |
| Public page and exposure record | Serve/display boundary | Current authorization, disposition and ownership checks |

Define the fingerprint explicitly: account and league scope, both relevant rosters/ownership, scoring/lineup rules, market edition, personal ranking/tiers (both sides if available), outlook/needs/tags, fairness, intent, selected assets/mode, partner, model/config/policy/significance versions, and relevant rejection history. Determine which inputs alter construction versus only serve-time filtering. Time-based TTL is a fallback bound, not proof of correctness. No private cache sharing across accounts.

Investigate four complementary approaches:

1. **App-open preparation:** audit existing triggers and utilization first. Start after minimum authenticated current league data is available, use exactly the saved search settings, join in-flight work, and prioritize the active league. Debounce rapid rank edits/league switches; do not delay home content or player interactions. Measure time from app open to trade tap and the fraction of warmed work actually reused.
2. **Event-driven incremental rebuild:** dirty only affected team pairs when a ranking, outlook or roster changes. Reuse unchanged pairs, then rerun required global ranking/diversity. A market-wide update may invalidate everything; pick projections can create nonlocal dependencies. Prove dependency closure, not just TTL freshness.
3. **Nightly/periodic batches:** refresh shared facts and league substrates first; prepare full inventories for recently active user-leagues if reuse/cost data supports it. Stagger starts, checkpoint, retry idempotently and pause speculative work under interactive pressure. Schedule after source refresh, not at an arbitrary midnight with stale rosters. Forecast job volume × measured CPU/DB cost and unused-precompute waste. Do not generate unsolicited notifications.
4. **Persistent prepared inventory:** reuse across process restarts/devices with explicit versions and expiry. Revalidate current ownership, picks, dispositions and authority before presenting/actioning. A stale deck is not silently actionable: reuse unchanged components and rebuild affected results, or present a clear refresh state.

Cross-viewer reuse is optional and limited: symmetric market/roster facts may be shared, but viewer-oriented preferences, fairness, suppression, attribution and ordering cannot be swapped blindly. Offline jobs must use established scoped server authority, not forged user sessions or copied tokens. Account deletion must stop work and remove derived private data.

Deliver a cache-hit/miss audit, invalidation test matrix, nightly capacity estimate, and comparison of app-open-only, incremental-only and hybrid strategies. Precomputation shifts latency and may raise cost; report total work as well as perceived responsiveness.

## 9. Workstream E — concurrency, Render and alternative platforms

Do not increase web workers/replicas before resolving process-local job discovery and cache correctness. More instances generally improve throughput, not the serial time of one search. Python threads should not be assumed to parallelize CPU-heavy Python; benchmark process/native execution and serialization overhead.

First verify live Render topology through read-only operations: compute size/CPU behavior, memory and throttling, cold starts, instance count/start command, Postgres size/storage/connections, service/DB region, internal versus external DB URL, pool settings, background workloads and connection pressure. Never output credentials. Correlate these metrics with traces.

| Option | What to test | Cost/risk and adoption gate |
| --- | --- | --- |
| Current Render, code-only | C1–C5 plus safe caches | Preferred if latency/concurrency targets are met |
| Render vertical scaling | Same workload on larger web/DB tiers separately | Adopt only measured resource benefit; not a substitute for wasted work |
| Render dedicated worker + shared job store | Interactive priority, bounded parallel opponents, durable retries, API isolation | Extra service/queue operations; resolves shared-state correctness before scaling |
| Render scheduled jobs | Periodic substrate refresh and targeted batches outside request handlers | Budget, freshness and actual reuse must justify it |
| Managed task/workflow service | Compare Render Workflows or another durable job system if retries/orchestration dominate complexity | Validate limits, availability, data handling, lock-in and cost; not automatically faster scoring |
| Separate container compute elsewhere | Keep app/API/database architecture where possible; benchmark worker near data | Cross-region latency/egress, operations and migration must produce clear net benefit |
| AWS Lambda-style on-demand compute | Burst economics, start latency, package/runtime limits, DB fan-out, execution/state persistence | Compare provisioned capacity cost and cold-path behavior; not the default for this workload |
| Temporal-style orchestration | Durable multi-step jobs if recovery requirements warrant it | Reliability tooling, not a numeric engine accelerator; avoid unnecessary complexity |

A worker queue needs deduplication/single-flight by fingerprint, leases, retry-safe persistence, stale-job fences, cancellation, bounded concurrency, fairness between users, interactive priority over speculative work, queue-wait telemetry and restart recovery. PostgreSQL-backed jobs versus a managed Redis-compatible queue should be compared, not assumed. Workers must not import web modules that inadvertently start cleanup/refresh threads.

Bounded opponent parallelism must preserve deterministic global budget allocation and ordering. Scheduling the fastest teams first must not starve others or change which budget-limited candidates are evaluated. Include IPC/memory duplication and DB connection multiplication in the benchmark.

Platform facts consulted September 20, 2026: Render supports [background workers and queue integration](https://render.com/docs/background-workers), [vertical/horizontal scaling](https://render.com/docs/scaling), [scheduled jobs](https://render.com/docs/cronjobs), [private networking](https://render.com/docs/private-network) and [Postgres pooling](https://render.com/docs/postgresql-connection-pooling). Verify plan eligibility and current pricing during experiments. AWS documents [provisioned concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html); [Temporal documentation](https://docs.temporal.io/) describes durable execution. These capabilities justify investigation, not a platform recommendation or a performance guarantee.

## 10. Quality, correctness and rollout gates

Use frozen differential tests comparing candidate identities, both-side exact terms, accept/reject reasons, scores, complete eligible inventory, deterministic ordering and expanded evidence. For parity changes require equality; explain every difference before proceeding. Test near-threshold numerical cases and final global diversity, not just first-page count.

Retain the owner's labeled reviews, actual app mutual matches/completions and the dynasty-only Sleeper corpus as quality regression checks where applicable. KTC/DP market benchmarks can detect pricing drift; they do not establish bilateral acceptance probability. Do not mix retrospective current-price comparisons with true valuation-at-offer ground truth. Optimization must not reduce personal target/sell fulfillment or skew against particular outlooks, positions, team sizes or ranking coverage.

Failure tests: timeout/poll cleanup, duplicate requests, worker death before/after commit, failed evidence write, stale cache, deploy/model flip mid-job, rank/roster change mid-generation, action arriving during publication, expired/sold pick, league switch, logout/account deletion and multiple devices. Confirm no duplicate like/send side effects, privacy leakage or stale actionability.

For each implementation: scope document, relevant canonical architecture/API/data/analytics references, unit/integration/property and fixture tests, current CI, then shadow comparison before staged rollout. Keep unrelated arms/settings unchanged. Observe p95, errors, stale-result blocks, coverage and costs; stop/rollback on a safety regression, unexplained candidate loss or material tail-latency/error worsening. Rollback must restore compatible job/cache schemas and invalidate incompatible prepared results—not just change a flag. Mobile behavior changes require a concrete physical TestFlight checklist; no simulator/Maestro work.

## 11. Execution sequence and deliverables

1. **Map and baseline:** code-cited lifecycle, historical early-batch implementation, fresh configuration/topology inventory, correlated backend and tap-to-tile timings, benchmark fixtures, cache/failure analysis. Exit when the measured stages account for worker time and first-action delay; otherwise instrumentation is incomplete.
2. **Code-only experiments:** separately measure C1–C5, report parity and resource results, combine winners. Exit with a ranked optimization table: observed saving, confidence/sample count, coverage, memory/cost, complexity and remaining bottleneck.
3. **Preparation experiments:** instrument existing warmup/replenishment, test dependency-scoped reuse, app-open timing and staged nightly preparation in isolation. Exit with freshness proofs, hit-rate and capacity/cost estimates.
4. **Infrastructure comparison only as needed:** same fixtures on actual-size versus alternative Render sizes/worker layouts; investigate external options if requirements remain unmet. Exit with measured reasons to stay or move, not a generic vendor list.
5. **Decision package:** recommended architecture and implementation-sized milestones, evidence against the owner's three-second tap-to-tile goal, 20–30-card initial-batch findings, expected costs, risks, canonical-doc changes, rollout/rollback plan and unresolved questions. Clearly separate faster first action from faster total computation. Prioritize the shortest safe path to the first-action goal over improving total completion time alone.

### Execution assignments — September 21

The owner authorized revising this plan and dispatching subagents to execute it. First wave is isolated research, reproducible measurements and local prototypes, not production deployment. Use three bounded subagents: (1) lifecycle/measurement harness, (2) early delivery/mobile/history experiments, (3) compute/evidence-storage profiling and parity experiments. Parent owns fresh production topology observation, cache/precompute analysis, integration and independent review. Coordinate CPU benchmark windows so concurrent profiling does not contaminate timings; agents may inspect code and write independent artifacts in parallel.

Report outcomes under `docs/plans/trade-search-latency/execution-20260921/`. Local tools/prototypes may be added with tests; changes to live application contracts require a scoped implementation decision. No agent may deploy, toggle arms, purchase resources, change production data or contact users in this phase.

The decision package must include three concrete options: smallest safe improvement, credible path to the three-second first-tile goal with a 20–30-card working batch, and longer-term concurrency/recovery architecture. Each includes measured evidence/limits, effort, rollback and total operating cost at current, 10× and 100× demand (burst concurrency separately). Include queue/cache/worker, storage/egress and observability costs; do not invent current demand or pricing. Cost scenarios can remain formula-based where usage is unknown. Evaluate AWS ECS/Fargate or Cloud Run container workers as targeted alternatives if Render is insufficient, not a default migration. Do not gate a safe code-only first-action improvement on completing every vendor experiment.

Do not promise an overall percentage improvement before the stage breakdown is available. The first decision is whether eliminating repeated work and decoupling full-inventory materialization from first-page publication meets the target on Render. If it does, keep the platform. If it does not, the evidence should identify precisely what infrastructure capability is missing.
