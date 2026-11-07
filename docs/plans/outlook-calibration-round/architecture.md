# Frozen outlook calibration round

Status: implemented locally; default off pending independent review, CI and operator activation. Normal serving remains owner-v2-bilateral-2. This exercise compares opinions, not predictive accuracy, and cannot promote a model automatically.

## Identity and scope

`outlook-v2-v3-1` compares exact versions `owner-v2-bilateral-2` and `owner-v2-bilateral-3`. `grading.outlook_prepare` enables admin preparation without public exposure; `grading.outlook_round` chooses the new exercise on start/current and admin pregeneration. `grading.blind` remains the public app audience switch. Existing legacy sessions have null `round_id`, retain all answers, and remain in the legacy report; they never gain new-round attribution. New sessions never receive fit_a/fit_b arms.

`current` and `value_core` remain *wire aliases* for installed clients. In this round the latter means the candidate owner model, not the historical value-core engine. Private provenance and aggregate reporting use exact model versions. Completed results add round/version metadata. Before completion, public projections contain neutral asset rows, progress, and captured date only.

## One capture, two complete generations

`outlook_calibration_adapter.capture` resolves one authorized user's connected league and actual roster seat. A previously unobserved coowner seat is resolved from provider ownership, never guessed from account identity. Explicitly supplied known seats must agree. Rankings/preferences remain the account's, while package ownership is the resolved league seat's.

The adapter captures players and market seeds, real personal boards and provenance, preferences and exclusions, format, slots, raw provider rosters/availability, owned picks and draft context, configuration, significance settings, fatigue suppression/pass state, and code revision. It records the full JSON-safe input, strict v3 evidence, roster context, settings and hashes privately. The two `run_arm` calls differ only in the owner-outlook selector; v2 omits the v3-only argument while binding the same captured facts. Configuration is scoped through the existing thread-local override, never changed globally. Execution order is randomized and recorded independently of presentation order.

Both full inventories pass the actual owner evaluator, captured suppression, strict full-roster structural safety, significance, exact-pass, versioned presentment and configured deck-quality rules. Unknown safety is rejected. No unfiltered fallback, quota-based relaxation or silent alternative arm. The required structural roster gate applies to both comparison arms even if an organic serving flag is off; this stricter comparison policy is recorded. Captured provider refresh may update existing owned-pick cache through the existing authorized path; feedback never updates trades, organic impressions, rankings or learning exposure.

Current complete provider roster coverage supports Sleeper. ESPN/MFL/Fleaflicker remain explicit `provider_roster_coverage_unavailable` cases. Missing lineups, stale availability, unavailable picks/rosters, changed ownership, and moving capture inputs fail honestly. There is no external league discovery and no invented evidence.

## Selection, memory and denominators

Generation and final quality evaluation use their full existing budgets. All surviving occurrences and unique package keys are counted. Only the first20 unique candidates per arm expand and retain proof dictionaries; the first native deck is released before the second full generation. This bounds retained review evidence without truncating model search or quality evaluation.

Choose `n=min(20, unique_A, unique_B)`. If either arm has zero survivors, save both denominators and fail `comparison_too_few`. Otherwise both contribute exactly n. Samples below10 per arm are explicitly `limited`; larger samples are still `descriptive_only`, never a statistical model-quality verdict. Shared selected packages display once and credit both arms. Shared inventory and selected shared counts are distinct. Duplicate occurrences and unsampled unique inventory remain in private denominators. No old deck/fit/value-core backfill.

Unique-arm cards alternate in randomized pairs; shared cards enter randomized slots. Every prefix differs by at most one exclusive-arm observation. Seed/order remain frozen. A shared answer is one observation with two credits, not two independent responses.

## Persistence, retries and rollout

`grading_sessions.first_exposed_at` atomically pins the snapshot on its first card read. `grading_sessions.round_id` is nullable; no historical backfill. `active_round_key` is a unique hash of account/league/round, retained on completion so even racing starts cannot create duplicate completed cohorts. Failure/stale retirement clears it. Two concurrent starts converge on one session. Old-round lookup/fold/report helpers filter null round identity.

One durable `grading_build_leases` row serializes the round across processes. A worker processes at most100 jobs and15 minutes per invocation, checking the round switch between builds. One job retains its full model budget. Lease expiry is one hour, renewed every30seconds; snapshot, completion and failure writes are fenced by the current token and expiry. After a bounded batch, a durable pending recheck starts the next serial batch. A foreign lease never triggers a retry spin. Pending sessions survive restarts and another current/start/admin request can recover the queue after a process crash and lease expiry. A crash after capture preserves that snapshot and fails the interrupted exercise instead of recapturing under the old session. Retry creates a new failed-history-preserving session.

First feedback is immutable. Identical retries, including a lost final response after completion, ACK without changing timestamps or answers. A conflicting retry is409 `answer_conflict`. A queued/failed new-round `next` is409 `comparison_not_ready`, never false completion. Session/card ownership checks and verified gates remain.

Disabling `grading.outlook_round` stops new public round starts and first exposure. Disable both `grading.outlook_prepare` and `grading.outlook_round` to stop new queue generation. First exposure of an unexposed ready cohort is blocked. Already exposed owned sessions and answers/results still resolve from persisted round identity; rollback never relabels them. `grading.blind` remains the outer public kill switch.

## Readiness and known changes

Pregenerate every recorded connected verified account/league pair, not only deck users. Connection evidence comes from the importing account, trusted server `league_synced` events, saved own preferences/rankings, overhaul ownership or grading history; imported opponent membership alone is excluded. The provider rechecks current membership and supported inputs. Account-only users without any connection remain counted, with no cards fabricated.

Admin batches use bounded `offset`/`limit` (maximum100), return aggregate status/coverage and next offset, and can be repeated idempotently. Explicit targets must belong to that known connection set; caller-supplied seat overrides are ignored. Workers are sequential; no per-user thread flood or normal trade-job refresh. User activation does not require opening Acquire.

An unstarted ready exercise is a durable **as-of** snapshot, not a current trade offer. There is no arbitrary age TTL. Known persisted/cache changes to consumed inputs or code invalidate only unexposed, unanswered ready sessions and enqueue a replacement. Exposed/started/completed exercises retain their exact frozen context and answers. Unexpected provider changes not yet observed locally cannot be claimed known. In particular, combined-holdings persistence does not independently detect changed reserve/taxi placement at open; the full captured inactive/rule evidence remains in the snapshot. This is an as-of exercise, not a live actionable trade. A new connection, changed inputs or failed/unsupported provider may still require building or remain unavailable; pregeneration is not a universal zero-wait guarantee.

## Privacy and reporting

Every new-round enqueue, private snapshot write and final publication locks the live verified owner and captured registered participants in account-deletion order. Captured creation revisions reject deleted/recreated identities; unregistered provider opponents are not fabricated app accounts. Deletion during enumeration/capture/generation cannot recreate private evidence. Full selected proofs live only in `source_json.proofs`, keyed by card and alias; per-card `arms_json` holds version/rank/proof hash. Next-card formatting is an allowlist. Account export retains the user's neutral trades/answers but withholds new-round arm answer keys, private diagnostics and mixed-manager snapshot/proofs. On participant deletion, existing scrub authorization overrides replay immutability: private snapshot/proofs are removed and marked invalidated; a building session is failed so it cannot later publish redacted material. Existing retention/deletion applies to the same grading tables. Lease rows contain no personal identifiers.

`GET /api/admin/grading/report?round_id=outlook-v2-v3-1` is aggregate-only: exact versions, code revision groups, connected coverage, queued/ready/started/completed/failed states, errors, full/unique/duplicate/selected inventory, shared counts and separate completed/partial responses (`include_open=1`). Readiness uses only the latest attempt per currently connected pair, including not_queued; historical failed/retried attempts stay separately labeled in status counts. Partial responses exclude unexposed ready decks. Distinct graders require an answer/skip; an exposed account without feedback is a participant, not a grader. Selected-card counts describe deck inventory, not measured card-view impressions. Legacy report defaults remain isolated. No inference from pooled means alone establishes superiority; shared observations, unequal user/league contributions, skips and limited samples must be considered.

## Mobile and operational verification

Existing binaries can start/resume/grade the new round and view immediate generic results via aliases. The client update adds explicit snapshot date, unsupported/changed-data guidance, small-sample context and reopening completed results. Old binaries do not reopen a completed exercise through Start; they do not generate duplicate feedback. There is no model identity on a card.

Operator sequence after exact-head CI: verify defaults/normal arm, enable admin preparation, enqueue bounded connected batches to exhaustion, inspect aggregate readiness/errors/platform coverage, enable public round exposure and turn preparation off, then requeue observed-changed unanswered inputs as needed. Retain exact deployed code/settings and report captures privately. Stop on memory/capacity errors; no parallel fan-out. No production activation/pregeneration was performed by the implementation agent.

## Code-walk anchors

- [start/resume and first exposure](../../../backend/outlook_calibration.py#L47): cohort uniqueness, known-change handling and atomic visible-snapshot pin.
- [one captured build](../../../backend/outlook_calibration.py#L171): two complete inventories, bounded selected proofs, equal selection and frozen private persistence.
- [leased serial worker](../../../backend/outlook_calibration.py#L311): bounded continuation, heartbeat and lease ownership.
- [input freshness](../../../backend/outlook_calibration_adapter.py#L93), [both-arm gates](../../../backend/outlook_calibration_adapter.py#L145), [authorized capture](../../../backend/outlook_calibration_adapter.py#L201): account/seat separation and provider uncertainty.
- [fenced publish](../../../backend/database.py#L18495), [immutable answer transaction](../../../backend/database.py#L18674): session-before-card locking and identical final-response retry.
- [aggregate report](../../../backend/outlook_calibration.py#L388), [all connected batch](../../../backend/outlook_calibration.py#L486): exact versions, distinct graders/leagues, denominators and authorization-bounded cohort.
- [public start](../../../backend/server.py#L35810), [admin preparation](../../../backend/server.py#L35979): separate preparation/exposure gates, no normal trade-job delegation.
