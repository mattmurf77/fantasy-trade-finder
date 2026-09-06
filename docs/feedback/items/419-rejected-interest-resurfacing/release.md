# Feedback 419–421 and small-package presentation — release record

## Authority and current state

The owner explicitly authorized unattended merge, GitHub publication, live delivery and TestFlight where needed for this selected batch. This does not waive review, CI or privacy checks and does not authorize unrelated backlog fixes/closures. The original dirty checkout and private files remain untouched.

**Not released.** Round-1 source `aa4637899a9233a4afffca22f3f90847fca76a62` has a confirmed reason-episode defect under repair. The previous production source remains `4026ebc81eaae50b345b42421641125c5b8d413e`; existing EAS build remains 1.17.0 (148). Native 1.17.1 is prepared, with no new build number assigned or uploaded. Selected feedback records remain `in_progress`.

## Intended delivery

- **419:** exact rejection resolves stale interest across server reads and locally observed mobile actions, while deliberate new source interest remains possible. Discovery cooldown and source consent are separate.
- **420/421:** bounded native Win Now initialization/recovery, stale-session protection and neutral timeout wording. This does not fix synchronous backend throughput or remotely update installed mobile code.
- **Smaller packages:** one bounded presentation preference for eligible organic results, retaining all three arms, all offers, explicit selections and valuation rules. Default-off `simple_player_presentment` becomes 1 only in a separately verified post-deploy activation. Picks do not count as players. No claim of improved acceptance rate.

[Research and limitations](../../../research/2026-09-06-trade-package-shapes.md), [all-45 read-only audit](open-backlog-audit.md), [batch plan](plan.md).

## Verification gates

1. Resolve confirmed QA findings through the owning builder; root reviews the whole increment. Any runtime change requires a new complete two-agent independent QA round, not fixed-case-only review.
2. Both reviewers pass the full approved test plan; root records tests and line-cited code walks in the test ledger. Consolidate their physical-device checklist without claiming it was run.
3. Fetch main and re-diff all owned paths; preserve concurrent work. Push the reviewed branch through the normal PR workflow. All four CI jobs must succeed on the exact final head before merge; verify the fetched merge tree matches the tested head.
4. Verify Render created a deployment for the merged source, reaches live, and serves new content. Recheck public/operator health and anonymous access refusal. Preserve all prior 207 effective flags, 258 existing config values, tiers and experiments.
5. Activate only `simple_player_presentment=1` using the existing audited admin-config command, then verify the single-key delta. Rollback is that key to 0 for new compatible generation; retained old job IDs keep their captured order.
6. Build from a clean, tracked-only checkout of the reviewed final source. Recheck EAS version race, all native version fields, effective production config, archive privacy and mobile byte identity. Submit the exact resulting build ID once; verify submission status before any retry.
7. After verified delivery, mark only 419, 420 and 421 `fixed` through the existing admin API and read each back. Do not set `shipped` or close any unrelated audit item.

Build completion, App Store Connect upload, Apple tester availability and a physical-device pass are separate facts. The last two remain unverified until evidence exists. No simulator/Maestro/captures under D-056.

## Read-only preflight

2026-09-06 15:53 UTC: Render `srv-d7g37ftckfvc73a32gvg`, live deployment `dep-dae3oseq1p3s73fs3m50` on `4026ebc8`, not suspended. Public/operator checks passed; unauthenticated trade/admin reads refused with 401. The complete 207-flag/258-config snapshot matched the earlier snapshot, as did tier and experiment hashes. The new presentation key was absent. No production mutation occurred.

Archive-only inspection of `aa463789`: 2,677 files, all 631 tracked mobile files byte-identical; only EAS-created one-commit shallow Git metadata is untracked. No local credentials/env files, raw interview notes, dependency trees or local databases. Effective config: version 1.17.1, production API, test mode false and existing project/bundle/owner identity. Inspection is not an upload; final source must be revalidated after QA repair.

## Recovery and remaining evidence

Batch worktrees remain under `/private/tmp/ftf-feedback-419-421-f1uMyt`; no branch/worktree cleanup has occurred. Capture exact tips and content-containment evidence in `docs/recovery/` before any eventual cleanup. Do not use the original dirty checkout for EAS or make private scratch research part of the release archive.

Pending: final QA reports, consolidated operator checklist, exact-head CI/PR/merge, source-specific Render deployment, single-key activation, EAS build/submission IDs, selected status readback, Apple availability and physical-device results.
