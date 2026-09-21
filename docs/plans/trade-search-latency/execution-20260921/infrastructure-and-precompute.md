# Infrastructure and precompute — executed research

Date: September 21, 2026. Baseline `4913ad0c`. No production writes, generation requests, load tests, deployments or purchases performed. Parent reviewed source while subagents ran isolated experiments.

## Fresh production evidence

Read-only Render API and PostgreSQL observation at 05:19–05:22 UTC confirms the same deployed commit, one Standard web instance in Oregon, one Gunicorn worker with a 120-second timeout, and Basic 256 MB Postgres 18 with 5 GB allocated storage in Oregon. Auto-deploy remains off. Runtime configuration readback at 05:20:38 UTC confirms bilateral owner-only serving, no card/group cap, pool16/pair4096/total60000 computational budgets, and `deck.replenishment=true`. No settings changed. Sanitized receipt: [production-observation.json](production-observation.json).

Render's current [compute-plan mapping](https://render.com/docs/compute-plans) lists Standard as 1 CPU/2 GB web RAM and Basic-256mb as 0.1 CPU/256 MB database RAM. These are plan allocations, not proof of actual CPU saturation or single-thread speed. The blueprint's Free web plan is stale; do not apply it or blame free-tier sleeping.

Seven bilateral engine runs since activation were matched to completed worker events by same account/league and nearest completion within five seconds. Actual timestamp separations were about 20–406 ms, with one match per observed run. This is stronger correlation than matching aggregate counts but still not a first-class job trace; introduce an explicit correlation ID before relying on this method long-term. No account/league identifiers are included below.

| Completion UTC | Engine seconds | Worker seconds | Engine output cards | Final cards |
| --- | ---: | ---: | ---: | ---: |
| Sep20 17:35:27 | 13.932 | 66.316 | 2,390 | 1,974 |
| Sep21 00:04:54 | 13.323 | 61.094 | 2,392 | 1,976 |
| Sep21 02:07:00 | 12.998 | 59.534 | 2,392 | 1,976 |
| Sep21 02:33:57 | 10.321 | 39.742 | 2,136 | 1,822 |
| Sep21 02:49:50 | 12.348 | 75.248 | 2,195 | 1,824 |
| Sep21 02:50:06 | 25.255 | 74.253 | 2,118 | 1,655 |
| Sep21 03:01:08 | 13.342 | 57.087 | 2,301 | 1,764 |

Worker median **61.094 seconds**, observed range **39.742–75.248**; engine median **13.323 seconds**, range **10.321–25.255**. Engine-output cards are not the much larger evaluated-candidate count. The longest runs overlap in time when inferred start is completion minus worker duration, but contention is a hypothesis, not an established cause. All rows are completions; failed/abandoned searches and client render latency are missing. Do not claim a p95/p99 or new-model acceptance change from this small cohort.

Historical 30-second resource samples around the September20 search show web CPU up to0.716 CPU and memory up to475.4 MB; database CPU up to0.049 CPU and memory up to134.7 MB. These coarse samples can conceal brief saturation/waits. They do not establish that either component needs more RAM or that database CPU is the dominant delay. Cumulative database statistics showed no recorded deadlocks, roughly420 MB temporary bytes over an unspecified accumulation interval, and recent autovacuum activity. Those are background context, not per-search diagnosis. Internal-versus-external DB routing, per-statement waits and effective connection-pool settings remain unverified.

Two initial aggregate SQL attempts failed read-only with a ProgrammingError; explicit aliases/casts fixed the query. No partial or failed query result is treated as measured evidence. The final bounded queries used `default_transaction_read_only=on`, confirmed it, and a15-second statement timeout.

## Current preparation: useful components, incomplete lifecycle

| Source | Code finding | Consequence / next experiment |
| --- | --- | --- |
| `backend/server.py:22145–22196` | Session-init starts a job after league setup; stored fairness is passed and matching active work is reused | Already available. Measure useful lead time rather than reimplementing another startup trigger. Prior log timeline reports just4sec lead time before the user's tap. |
| `backend/server.py:2241–2264,3262–3295` | Jobs/results are process-local; completed cache TTL30min; ordinary key user/league/format plus additional freshness comparisons | Nightly generation alone will often expire before morning or disappear at deploy. Persist versioned compact inventory before relying on overnight full-deck warming. |
| `backend/server.py:8574–8603` | Invalidator leaves running jobs alone; in-flight reuse is not based on full input versions | A persistent cache magnifies this correctness gap. Add captured input versions and stale-result fences before extending lifetime. Pipeline report includes isolated reproductions. |
| `backend/server.py:22967–23026` | Replenishment reuses a cached complete job, otherwise invokes synchronous kickoff without an explicit fairness threshold | Kickoff defaults0.75 whereas app default is0.5. Do not assume background inventory will hit the user's next request. Resolve saved search preferences centrally; do not change user's settings. |
| `backend/server.py:22843–22952` | Headless reconstruction starts from1QB pool and labels League platform Sleeper | Audit correct format/platform/ownership metadata for ESPN/MFL and Superflex before expanding scheduled coverage. This is a source risk, not proof of a bad served card. |
| `backend/server.py:23029–23113,23896–23901` | Weekly gate called synchronously inside daily-tick, user-leagues sequentially, with inbox/push behavior attached | Do not turn this into a nightly full-deck loop on the API worker. Separate silent preparation from user notifications and run outside the request-critical worker if scale warrants it. |
| `backend/database.py:6454–6482` | Eligibility includes recent trade decisions OR generated trade impressions | Generation can keep a league eligible without genuine user return. For demand-aware nightly work, base recency on actual human usage/exposure rather than the preparation's own writes. |
| `backend/server.py:2699–2704,2748–2762` | 60sec hard-timeout checked by a5min cleanup loop | Long jobs may survive or be marked error depending on sweep timing. A longer constant is not the speed fix; test state transitions and safe partial-inventory recovery. |

All citation line numbers refer to pinned baseline, not edited prototypes. Production completed events distinguish `deck_source=replenish`, but absence of that marker combines interactive and startup work. Historical September16–19 contains22 completed replenishment jobs. The feature is not merely unimplemented; its reuse effectiveness is unmeasured.

The current eligibility query returned22 distinct active user-league pairs over approximately30days. This is not22 daily searches or22 engaged users, and generated impressions influence it. No reliable useful-cache-hit ratio or monthly traffic projection was derived from that count.

## Preparation design recommendation

1. Make identical concurrent requests join one atomically registered versioned job. Include account/league scope, selected assets/partner/intent/fairness, both relevant boards, outlook/needs, rosters/picks, market/model/policy versions. Maintain separate disposition projection at serve time where safe.
2. Reuse immutable shared facts and per-team/pair results first; recompute only dirty dependencies and rerun global ranking/diversity. Current global iteration budgets make naive pair-level incremental replacement nontrivial: record deterministic allocation and prove candidate parity.
3. Keep the initial20–30 validated candidates and their publication data prepared; hydrate/record later pages without excluding any eligible result. First page must not depend on constructing all rich response objects. Details are in [delivery.md](delivery.md).
4. On app open, resolve current source versions and saved parameters, join matching work, and prioritize the active league without blocking home content. Debounce edits, cancel superseded compute at safe checkpoints, never cancel useful work merely because the first batch filled.
5. Add silent nightly shared-fact refresh only after measuring reuse. Full personalized inventories are opt-in to the scheduler based on expected use, not every registered account. Persist across deploys with explicit invalidation; a longer TTL alone is not acceptable.
6. Historical liked/matched terms remain immutable. Newly serving a prepared suggestion still requires current ownership, available picks, decline/suppression and authorization checks. A stale source cannot silently be presented as current.

## Capacity and cost scenarios—not a purchase recommendation

The22-pair eligibility count gives a transparent batch-size illustration. At the observed median61.094sec per worker job, sequentially refreshing22/220/2,200 pairs would occupy approximately22.4min/3.73h/37.34h. These are extrapolated wall-time workloads with identical assumed job cost—not a load benchmark or CPU-hour estimate. The100× case does not fit one nightly window without less repeated work, selective preparation, parallel capacity or a different schedule. Improving reuse is preferable to multiplying unused generation.

Measure before pricing: useful requests/month `R`; full builds/month `B`; duplicate builds avoided; prepared inventories served `U`; job CPU seconds `C`; GB-seconds `M`; snapshot/response bytes `S`; required concurrency and headroom. Compare code-only, code+prepared results, and code+worker using the same quality/freshness contract.

`Monthly total = web + database + always-on workers + queue/cache + variable compute + storage/egress + orchestration/observability.` Report current,10×,100× demand and `$ per1,000 useful searches`, counting unused precompute in cost but not in useful-result denominator. Do not multiply the66sec worker duration by aCPU rate: it includes waits, and theCPU budget must be measured.

Current public Render pricing page did not expose a complete trustworthy instance-price table through the text retrieval used here. No current monthly invoice or instance quote is invented. Current [Workflows pricing](https://render.com/docs/workflows-limits) explicitly lists flex at$0.20/CPU-hour plus$0.05/GB-hour and task-state retention at$0.25/GB. For a measured task this component would be `(C/3600)*0.20 + (M/3600)*0.05 + (S/1e9)*0.25`, before other service/network costs. This is an evaluation formula, not a quote for this app. Startup delay is not benchmarked; retained task arguments also require privacy/deletion review.

## Platform decision scorecard

| Option | Finding | Decision now |
| --- | --- | --- |
| Existing Render, code-only | Dominant repeated and serialized work remains; current paid web has memory headroom in sampled window | First choice; no migration justified by current evidence |
| Larger Render web or DB separately | More resources may improve constrained phases; no controlled comparison yet | Candidate bounded staging experiment after component profiling, not automatic upgrade |
| Render worker + durable shared state | Separates CPU jobs from API/poll traffic and enables restart-safe background preparation | Strong next architecture if concurrent load/reliability warrants it; no instant single-job speed guarantee |
| Render Workflows | Managed execution/retries may reduce operations; startup/dispatch and task-data retention matter | Benchmark before choosing for3sec interactive path; more naturally relevant to preparation |
| AWS ECS/Fargate workers or Cloud Run | Container worker alternatives, but moving only compute leaves cross-cloud DB traffic | Not selected; require comparable end-to-end measured win and migration/operational cost case |
| Temporal, GPU, vector DB or LLM replacement | No evidence that orchestration or those model types solve the measured hot path | Do not introduce for this latency initiative without a demonstrated need |

Provider capabilities checked against primary documentation: [Render background workers](https://render.com/docs/background-workers), [Render scaling](https://render.com/docs/scaling), [AWS ECS scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html), [Cloud Run services/jobs/worker pools](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run). Render horizontal scaling does not repair process-local job routing; externalize required state first. Cloud Run's scale-to-zero startup requires cold-path testing or minimum warm capacity. None of these platforms was provisioned or benchmarked in this phase.

## Unfulfilled evidence gates

No physical tap-to-tile timings, p95/p99 qualification, real concurrent-load benchmark, controlled paid host comparison, nightly hit-rate experiment, or exact full production replay. Native/display instrumentation is required to satisfy95% of end-to-end elapsed-time attribution. This report executes the read-only infrastructure and source/precompute audit; it does not claim the three-second goal is achieved.
