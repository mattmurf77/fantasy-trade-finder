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
