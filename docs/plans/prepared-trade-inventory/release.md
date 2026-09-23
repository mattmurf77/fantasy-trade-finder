# Prepared inventory release — 2026-09-22

## Tested release identity

Owner authorized plan first, build/deploy and initial all-user linked-team sweep.
Plan/scope preceded implementation. Three Astra Ultra lanes, parent integration,
independent cross-review and privacy hardening completed.

- PR305 merged21:57:52UTC: https://github.com/mattmurf77/fantasy-trade-finder/pull/305.
- Final tested head `1804513950bdc5648fe6e12eb285119ee7e4cb09`;
  merge `4903d2054f90967cfdec3abc99f843445d6a76bc` has the identical tree.
- Hosted CI35788148359: four gates green; backend **7,144 passed /1 skipped**,817.12s.
- Earlier local full7132/1skip; final privacy/replenishment groups131+39 and independent10 passed.
- Render `dep-dapfjrhsrm7s73famjtg` became live22:07:49UTC; read back22:08:59UTC.
- Backend only; no TestFlight required. One existing Standard instance; no paid infrastructure change.

## Initial activation and failed canary

Capability `trade.prepared_inventory=true`, numeric rollout0 verified22:09:18UTC.
All-user dry-run resolved7 targets across18 saved2026 leagues and6 eligible app
actors. Discovery was **incomplete**: source_invalid4, source_unavailable1,
source_unmapped_players1; other skips included missing_platform_binding2,
no_current_team_binding1, no_known_linked_team1, opponent_only_actor2,
superseded_account_alias1 and unverified_actor13. These reasons mix actor/league
grain and must not be summed as a team denominator.

Independent aggregate-only diagnostic: saved leagues are16 Sleeper/1 ESPN/1 MFL,
all marked2026, no unsupported format. Both missing-binding cases belong to the
MFL league: saved native team exists but retained importer membership is missing.
One Sleeper row has both a nonnumeric ID and a fixture-name hint. Exact provider
invalid/unavailable causes were not established. The unmapped-player case points
to ESPN by elimination, not by a fresh provider verification. Do not guess either
MFL actor's team or silently discard an unmapped asset to increase cache coverage.

Audited rollout0→1 at22:10:04UTC; all other model/config knobs unchanged.
Scoped canary `10e5d888d5f54d588ca930fb21e0dfbc` resolved one team, began22:10:13,
and failed22:11:20 before saving any artifact. Diagnostic:
`prepared_payload:snapshot_conflict`, surfaced as `prepared_evidence_unavailable`.
Numeric rollout1→0 read back22:11:56UTC. Full-cohort preparation has **not** run.
Ordinary exclusive Bilateral2 generation and all offer/fairness settings remain unchanged.

Production counters before/after canary: swipes6635, trade_decisions1686,
deck_impressions123570, sessions6, all unchanged; user activity/ranking fingerprint
unchanged. user_events count changed during the window and is not claimed invariant
(ongoing operational traffic/retention exists). No fake session/adoption test was made.
Private operator receipts: `/private/tmp/prepared-release-20260922.S7GrYs` and
`/private/tmp/bilateral-release-20260922.SSUU5o`. No credentials here.

## Remaining release gates

Reproduce and fix the cross-batch capture conflict without weakening evidence
integrity; rerun focused/full/hosted gates, merge and deploy exact tested fix;
reactivate through audited knob; run a fresh-key canary then all-user sweep.
Record ready/empty/reused/error states separately from unresolved discovery.
No successful production cache or three-second first-action claim yet.

Corrective diagnosis: diagnostic snapshot IDs hash expanded scoped content, but
the same subtree can be inline in one batch and referenced in another. Comparing
packed bytes rejected equivalent evidence. The actual64-card worker reproduced
the exact live failure. Capture repair validates both scoped graph representations
and merges atomically, retaining the first node/time. Independent91-case group
passed; malformed graph/scope/timestamp and partial-state negative controls remain.
An actual512-card varied-diagnostic stress then exposed the same assumption in
SQL adoption after the first30. Store repair now preserves the exact original
diagnostic graph and timestamps while keeping strict impression/candidate identity.
Final independent108-case store group passed. Independent partition/restart controls cover
closure per committed batch and retry after a crash before progress checkpoint.

Corrected actual512-offer varied-diagnostic stress passed end to end: first30 SQL
commit2.031s, full adoption5.516s, full preparation4.645s; six capture batches cost
1.348s total (largest0.479s). Logical envelope15,430,124B, stored480,867B,
peak process RSS352,485,376B. Synthetic32-opponent/local SQLite, provider/full
receipt mocked; not live traffic or device timing. No offers truncated or repriced.
Final full/hosted tests, corrective merge/deploy and production retry remain pending.
Parent combined prepared-cache regression321passed41.43s; web195/195 and
test-ID lint pass. Corrective branch `codex/prepared-capture-fix-20260922`.

[Timing evidence](read-guard-evidence.md):64/512 actual local synthetic offers,
first30 durable0.493/3.034s, full0.730/8.518s. Not provider/network/device latency.
Artifacts retain original card expiry and at most24h; adopted jobs at most30min.
64MiB decoded/2MiB stored bounds reject oversize artifacts without truncating offers.

## Historical update — second canary and implementation hold

This section supersedes the earlier pending-correction statements above.
PR306 final headbc76702e passed local7183/1skip407.39s and hosted
CI35792813386 backend7183/1skip770.45s, all four gates green. It merged22:45:43UTC
as `2cff90c748d4bf7046579b18401c495de79551cb`, identical tested tree.
Render `dep-dapgadlbedkc738p5k7g` became live22:47:29UTC, read back22:48:07.
Cache0→1 at22:48:38 with all other knobs unchanged. Fresh canary
`0ae2dca1223e427c82227609dba32bd1` failed22:50:58 with `InvalidArtifact`, zero
artifacts. Its exact cause is unknown because the phase/reason was not logged.
Cache1→0 read back22:51:40 and23:03:19. No full-cohort sweep has run.

Through23:03, swipes6635/decisions1686/impressions123570/sessions6 and the
user activity/ranking fingerprint stayed unchanged. Operational user_events
varied; no blanket no-write claim. No simulated production adoption/session.

Safe allowlisted diagnostics passed132 independent tests. A separate actual
12-team/24-player dense synthetic constructor produced13728 offers,
461530265 logical bytes /15083835 compressed-text bytes and2325421 JSON nodes.
It failed the unchanged1000000-node whole-copy guard before saving; native proof
strings matched and0artifacts/exposures. Uninstrumented82.51s/994459648B peakRSS;
instrumented89.13s/1345142784B peakRSS includes8.335s streaming size measurement.
This is a capacity finding, not proof of the production failure cause. Suggestion
telemetry was disabled; candidate singleton capacity is not covered.

[Chunked-storage plan](chunked-storage-plan.md) was written/reviewed before code.
Safety review rejected creation of the new persistent store module as requiring
more specific approval. No retry, split patch or indirect workaround was attempted.
All three agents stopped. Accepted schema, codec/runtime and test drafts are
preserved in the isolated worktree but are **not runnable/releasable**: the store
module is absent. Three codec tests failed at fixture scope; telemetry integration
could not import the absent store. No v2 qualification result is claimed.
Legacy capture/snapshot tests14passed3.46s. Temporary synthetic PostgreSQL was
initialized locally without TCP and stopped; no v2 PostgreSQL tests ran.

Resume requires explicit approval of the persistent-storage/lifecycle subsystem,
then completion, independent review, actual dense end-to-end qualification and
full/hosted release gates. Do not deploy the partial branch. Current ordinary
exclusive Bilateral2 generation remains unchanged; production caching is OFF.

## Resumed implementation — explicit approval, 2026-09-23

The owner explicitly approved the persistent-storage/lease/deletion subsystem;
the earlier authorization hold is cleared. The v2 store was created under that
approval, not a workaround. Initial codec/legacy114, runtime/capture40,
SQLite storage/lifecycle23 and independent telemetry/privacy/recovery8 tests
passed. Author16 + independent7 controls also passed on a disposable local
PostgreSQL database, never production. These precede the admission revision.

An actual936-offer three-team synthetic preparation/adoption passed exact native
proof/order/terms parity: prepare22.36s, worker10.05s, seal12.24s, admission
preflight12.45s, first30durable17.06s, full adoption37.84s, peakRSS270221312B,
maxSQLbind998110B. Telemetry was off. This exposed unacceptable admission overhead;
it is not a speed success or a controlled ordinary-generation timing comparison.

The dense actual12-team/24-player constructor preserved and sealed13728 offers:
prepare348.85s, worker160.60s, seal188.03s, maxSQLbind114252B, peakRSS1412857856B.
Parent intentionally stopped the superseded repeated-full-preflight admission
at389.39s before the first card. It is a successful preparation measurement, NOT
an end-to-end adoption pass. Telemetry was off; candidate singleton capacity is
not established. The local background cleanup logged an isolated SQLite retention
error during that run; no production connection or simulated user action occurred.

[Revised plan](chunked-storage-plan.md#measured-admission-revision--2026-09-23-before-implementation)
and [ADR-023](../../adr/adr-023-attested-prepared-inventories.md) now move invariant
full semantic validation to a pinned-root seal, with complete authenticated compact
disposition admission and exact per-batch publication validation. This explicitly
permits only an earlier valid prefix if a later stored page is corrupt. Independent
review requires a store-minted attestation and rejects caller-controlled validation.
Qualification and rollout gates remain open; no v2 commit/deployment yet.

Production cache flag readback2026-09-23T02:03:21UTC is0.0, capabilitytrue. Only
aggregate production candidate capacity was queried this turn: latest100 rows,
largest425045UTF8bytes/max2541members; suggestion.telemetry=true. It fits the
planned singleton write bound but is not evidence of dense telemetry capacity.

### Attested-admission and recovery qualification

The revised actual936-offer run with suggestion telemetry ON preserved every
native term/proof/order: prepare23.79s, first30durable1.081s, fulladoption22.15s,
candidate133496B/936members, maxSQLbind995984B, peakRSS274726912B. The actual
13728-offer telemetry-OFF run also completed exact full parity: prepare361.35s,
first30durable3.855s, fulladoption338.64s, maxSQLbind999044B, peakRSS1492434944B.
These are local backend/SQLite measurements, not device or production latency.
Background maintenance was parked only in the isolated pressure harness.

The dense result exposed a duplicate compact-index scan; it was replaced by a
bounded disposition callback in the same authenticated scan. Separate real
Flask like/pass tests reproduced cancellation of the remaining inventory after
the first30 cards. Active adoption now retains explicit/source inputs while
projecting current exact passes, source interest and awaiting/matched packages.
Admission still compares the complete original receipt. Damaged exact-root
inventories retire without deleting their earlier valid exposure history;
transient SQL failures remain retryable. Hourly privacy pruning now precedes
the active-sweep early return.

Revised codec/legacy153 tests passed; store+attestation+retirement59 passed each
on SQLite and isolated Unix-socket PostgreSQL. Parent diagnostics/runtime40
passed. Final speed remeasurement, full/hosted CI and fresh production canary
remain required. There is no v2 commit/deployment or all-user cache coverage yet.
