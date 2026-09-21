# Worker lifecycle, measurement and cache risks

Executed September 21, 2026 against `4913ad0c68af5e75f864c46cff692ca5f9bf842b`. This work follows the [research plan](../research-plan.md) and [scope](scope.md). It changes only an offline measurement script, tests and research evidence. Application behavior is unchanged.

The measured local worker takes about 13 seconds before publishing any durable cards. Construction, complete owner revalidation and evidence assembly/storage/publication consume approximately 91% of this reconstructed worker. Faster database execution alone cannot produce a three-second fresh first card: construction alone is about 5.9 seconds on this machine. These are local, incomplete-fixture measurements, not production estimates or an achieved target.

## Actual lifecycle at the baseline

Line citations refer to unchanged baseline application code.

| Boundary | Current behavior and publication consequence | Source |
| --- | --- | --- |
| Session initialization | Validates saved fairness, looks up a process-local job, reuses suitable running work or starts pre-generation. No durable prepared inventory is loaded. | `backend/server.py:22145–22197` |
| Generate request | Resolves current preferences/outlook, request shape, fairness and presentation settings; copies a reusable job or starts one. Pinned assets/partner scope bypass the organic pointer. | `backend/server.py:13862–14061` |
| Registration and scheduling | `_kickoff_trade_job` always creates a fresh job; callers own deduplication. It captures the account-data lease, deep-copies the league, shares the selected ranking service/card store, then starts a daemon thread. There is no queue-wait metric. | `backend/server.py:7077–7121`, `8606–8747` |
| Input preparation | Reads viewer rankings, opponent boards, preferences, exclusions, outlooks, tags, confidence and picks. Captures owner model/config/safety settings. `final_checks_pending` blocks interim publication. | `backend/server.py:7124–7574` |
| Owner context and construction | Builds frozen owner inputs, computes assignment, runs the captured owner generator through bakeoff (or targeted generation), and stores candidates in the service. Complete generation precedes subsequent checks. | `backend/server.py:7575–7674`, `14379–14468` |
| Mutation/presentation layers | Fit diagnostics, likes-you insertion, standing offers, fatigue and optional ordering/exploration/first-session logic run before final validation. Some loops still serialize full snapshots even when the pending-check barrier prevents publishing them. | `backend/server.py:7676–8024` |
| Required final evaluation | Re-evaluates all owner cards against captured input, performs roster checks, legacy market checks where applicable, merges owner survivors and applies significance. Owner proof/package matching is explicit. | `backend/server.py:8026–8220`, `14471–14490` |
| Final dispositions | Rechecks exact passes and resolved source interest before freezing impressions. Public responses independently project current dispositions. | `backend/server.py:8324–8347`, `3070–3129` |
| Durable owner publication | Logs legacy impressions, assembles F1 evidence, writes all pages transactionally, verifies every served owner card has an impression ID, then publishes the full snapshot and marks owner cards published. Any owner evidence failure withholds the deck. | `backend/server.py:8388–8479`, `4806–5254`; `backend/database.py:6551–6602` |
| Completion | Saves run evidence, sets terminal status, records analytics. `trades_generated.gen_ms` starts at job registration; bakeoff timing covers a narrower region. | `backend/server.py:8482–8571` |
| Poll/response | Copies the entire job under lock, verifies caller ownership, filters live dispositions, JSON-encodes the whole snapshot. There is no page cursor here. | `backend/server.py:3025–3069`, `15000–15020` |
| Cleanup | Every five minutes, marks jobs running longer than 60 seconds as errors; retains finished jobs for four hours. Process restarts discard jobs and cache pointers. | `backend/server.py:2259–2264`, `2700–2776` |

The old opponent callback constructs a snapshot before checking the publication barrier (`backend/server.py:3297–3331`). Removing that barrier is unsafe. Owner serving deliberately waits for all required gates and durable evidence; a new early-page boundary must satisfy those obligations for every released card.

The existing job-local draft-pick memo is incomplete for owner serving: `_owner_generation_context` independently calls `load_draft_picks` at `backend/server.py:14429`, beyond `_job_draft_picks` at `7227`. Existing legacy read-amplification tests do not establish one-read behavior for the owner path.

## Reproducible measurement

[`scripts/research_trade_pipeline.py`](../../../../scripts/research_trade_pipeline.py) injects 15 coarse checkpoints into an in-memory AST copy of the real worker. Removing those calls must recover the original AST exactly. This leaves hot evaluation loops unprofiled and preserves worker statements and ordering. Actual registry writes record first nonempty/durable publication. SQL observers retain only statement operation/count/time, never parameters.

Safety: fresh-process requirement; a newly created private output directory; `DATABASE_URL` overwritten with its SQLite file before backend import; all socket connection entry points blocked; import-time/background thread starts suppressed; checked-in startup player/pick curves; private caches redirected. The inherited LLM key is removed from this offline process. Output directory mode is `0700`, files `0600`. No production credentials are read or needed.

The frozen request has 580 players, 13 member records and a 31-asset viewer roster. Its original capture is September 19; the separate config/flag readback is September 20 at 23:02 UTC. Snapshot and configuration hashes, source hash, actual runtime, run values and limitations are recorded in [pipeline-results.json](pipeline-results.json). The constructor output is 2,843 cards in all three success runs, matching the historical bilateral constructor replay. Current captured significance reduces it to 2,354; all 2,354 receive durable impressions and are published in the reconstruction. This is not parity with a fresh production deck: provider, histories and full pick metadata are missing.

```sh
PYTHONHASHSEED=0 python3 -m scripts.research_trade_pipeline \
  --snapshot /private/tmp/trade-latency-private-config.json \
  --config /private/tmp/owner-v2-latency-live-check.json \
  --output /private/tmp/NEW-PRIVATE-PIPELINE-RUN

python3 -m pytest backend/tests/test_research_trade_pipeline.py -q
```

The historical snapshot filename contains “config” but actually holds `owner_request.input`; `--config` requires the separate readback containing `config` and `flags`. The harness does not fetch either. Use a fresh output name each time. `--export-private-impressions` additionally saves raw rows and the public response **off Git** for related experiments. `--fail-evidence-write` injects failure at the real saver seam.

Three uncontended success runs, in separate processes: 13.015 / 13.063 / 13.200 seconds wall; 12.840 / 12.888 / 13.002 seconds CPU. CPU windows were coordinated with the compute agent. Actual runtime is macOS arm64 Python 3.14.4; the repository pins 3.12.3 and no 3.12 executable was available. These runs do not satisfy the planned production-runtime/resource or 30-run benchmark requirements.

| Stage | Median wall ms | Median CPU ms | Interpretation |
| --- | ---: | ---: | --- |
| Construction/bakeoff | 5,910.343 | 5,846.351 | Complete frozen candidate construction |
| Owner revalidation | 2,144.195 | 2,125.904 | Re-evaluates 2,843 complete packages |
| Evidence and publication | 3,858.487 | 3,780.177 | Row assembly, compaction, inserts/commit and final serialization |
| Post-construction layers | 522.869 | 516.182 | Includes diagnostics, optional mutations and blocked snapshot preparation |
| Snapshot + legacy impressions | 389.266 | 385.849 | Full public card construction before F1 persistence |
| Roster checks | 162.511 | 160.107 | Missing provider metadata remains unknown; captured enforcement is off, shadow is on |
| Significance | 52.444 | 52.034 | 489 cards removed; no fill quota |
| Preparation/context | 7.443 | 7.423 | **Incomplete**: frozen owner-context adapter and board getter substituted |
| Other measured spans | About 15 | About 15 | Dispositions, market check, presentation, run ledger, completion/analytics |

Stage medians do not sum exactly to median total. The raw first run partitions its entire measured worker interval; that does **not** fulfill 95% tap-to-tile accounting. Unmeasured: session/route preparation, authoritative owner capture, scheduling, network, polling delay, client parse/render, contention, provider synchronization and current source freshness.

First durable publication occurred at 13.006 / 13.055 / 13.192 seconds, essentially at completion. The actual full JSON response is 3,218,422 UTF-8 bytes. Local snapshot-copy/current-disposition projection costs 33.8–35.7 ms; local serialization costs 25.9–26.3 ms. These are neither compressed network bytes nor mobile parse/render timings; the delivery workstream owns those comparisons.

The first run executed 18 SELECTs, 75 INSERT statements and one UPDATE during the worker; the public projection added one SELECT. In its 3.841-second evidence stage, SQL cursor execution took only 90.4 ms with 72 INSERT statements. SQLite cursor timings exclude commit, Python work and connection acquisition and must not be used to label production time as database wait. Existing persistence already uses 100-row pages in one transaction and stores losslessly reconstructable diagnostic references (`backend/database.py:6551–6602`, `backend/deck_diagnostics.py:26–110`).

Whole-process peak RSS was 410 MB without raw export. Export runs retained private assembled rows and reached 549–596 MB; that retention is a research artifact. The separate exported raw impression file is about 84 MB before diagnostic normalization. These are process high-water marks, including import/setup, not incremental worker allocations or a production capacity measurement.

The injected saver failure completed the experiment in 11.121 seconds with `status=error`, `error=owner_impression_unavailable`, zero published cards, zero F1 impressions and no first-card timestamp. This confirms the existing fail-closed owner boundary for a failure **before** the transaction; it does not test a crash after commit or midway through paged inserts.

## Cache and concurrency findings

Seven tests passed in [`backend/tests/test_research_trade_pipeline.py`](../../../../backend/tests/test_research_trade_pipeline.py). Four check instrumentation/privacy/timing mechanics. Three execute extracted, unchanged baseline function bodies with bounded stubs to reproduce control-flow risks; they do not claim an HTTP integration or production incident.

| Priority | Finding / reproducible evidence | Required design implication |
| --- | --- | --- |
| P1 | Two simultaneous cold `/generate` calls both pass lookup, then each reaches kickoff. Lookup lock ends before registration; `_kickoff_trade_job` explicitly always creates a new job. The deterministic barrier test produces two IDs and one pointer. (`server.py:13990–14060`, `8625–8628`, `8710–8714`) | Atomically claim one job for an exact request fingerprint; durable shared claim before multi-process scaling. |
| P1 | `_invalidate_trade_jobs` removes only completed/error pointers. A changed outlook while generation runs still returns the old running job because running-match predicates omit outlook. Test reproduces it. (`server.py:8574–8603`, `14010–14022`) | Mark changed dependencies dirty immediately; distinguish reusable work from work that may publish. |
| P1 | A ranking edit during a running job leaves no dirty/version marker. When that job completes with the same outlook/fairness, `_trade_job_is_fresh` accepts it; the third test reproduces this. (`server.py:3266–3294`, `8574–8603`, `9434`) | Preserve dependency versions at capture and publication; stale completion must not become a fresh cache hit. |
| P1 | Freshness checks include owner/safety/significance/presentation, TTL, fairness, outlook and intent, but no complete board/roster/market/config version. Process-local pointers do not establish durable cache correctness. (`server.py:2972`, `3150–3192`, `3262–3294`) | Define construction versus serve-only dependencies before persistent precomputation. TTL alone is insufficient. |
| P1 | A five-minute sweep may error a worker after 60 seconds. `_job_live` then suppresses publication, but the worker's completion block unconditionally sets `status=complete`, leaving the existing error. (`server.py:2750–2763`, `2997–3004`, `8519–8527`) | Use explicit terminal-state/fencing semantics and measured timeout budgets. No timeout incidence is asserted here. |
| P2 | Forced regeneration leaves the superseded CPU worker running. Publication/durable checks are best-effort fences and the source explicitly notes a check-to-write window. (`server.py:2994–3014`, `14020–14037`, `8414–8429`) | Cooperative cancellation plus transaction/lease fences; continue complete candidate search for the live job. |
| P2 | Session warmup does not call the complete freshness function: running fairness/intent is deliberately preserved, complete handling does not compare all safety/dependency inputs. (`server.py:22162–22181`) | Unify exact request identity and explicit warmup/interactive priority rules. |

Required invalidation matrix for follow-on implementation: own and opposing rankings/tiers/tags/outlook, either roster and pick ownership/expiry, league format/lineup settings, market refresh, model/config/significance version, exact dispositions, selection/partner/fairness/intent, account deletion, restart and two devices. Existing positive checks for fairness, model, significance and explicit force are useful; none establish closure over all dependencies. Parent owns broader precompute/replenishment findings and operating-cost recommendations.

## Decisions supported by this evidence

1. Optimize package evaluation and evidence preparation first, with exact candidate/proof parity. Revalidation reuse needs an immutable input-and-package proof, not removal of the final check. The compute workstream measures this opportunity independently.
2. Move full-inventory public serialization and evidence materialization off the first-page critical path only after complete ordering/eligibility obligations are defined. Publish 20–30 cards once their exact evidence is durable; retain all remaining eligible inventory and stable identities. Do not infer that simply slicing the final response speeds this worker.
3. Correct invalidation and atomic job admission before relying on aggressive preparation or adding workers. A warm result can meet a first-action target only if its current inputs and serve-time authority are provable.
4. Keep production end-to-end tracing and physical-device timing as an unmet gate. The local reconstruction exposes substantial CPU outside the narrow engine timer; it does not allocate the entire historical production worker/engine difference or establish the three-second goal.

Not executed here: production mutation, deployment, cron creation, paid changes, vendor sizing trials, live provider/DB replay, 30-run/multi-league cohorts, full crash/retry/supersession matrix, p95/p99, mobile/TestFlight checks, saturation curve. One import-only startup attempt failed before timing because the deliberately absent DP player fixture was required by server's demo initialization; the harness now uses the checked-in fixture. That failure is not included among worker runs.
