# HANDOFF — Fantasy Trade Finder

> **Purpose:** current release work and delivery checks; prior history lives in CHANGELOG and feature records.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

## Table of Contents
- [Current State — 2026-09-05](#current-state--2026-09-05)

## Current State — 2026-09-05

**Active request:** operator accepts exploratory historical evidence and authorizes shipping Win Now, season projections and championship estimates as an uncalibrated beta. Worktree `/private/tmp/ftf-win-now-20260904`, branch `codex/win-now-20260904`; original dirty checkout preserved. [Release record](../docs/business/ops/2026-09-05-win-now.md).

**Integration:** PR #280 opened at `ee4f37a8`; main advanced to account-security release `a927e3a7` (#279) during CI. Its ownership/data-lifecycle changes are now being merged and reviewed by three Astra agents plus parent before new exact-head CI. Preserve all protections from #277–#279. The release changes only the three Win Now flags; dynasty policy switches retain main's values.

**Evidence so far:** before #279 integration, Python 3.12 full suite 5,248 passed / 1 skipped (7m44s), final focused scoring/job lifecycle suite 144 passed; 93 client commands and 185 web checks passed. Original CI head is superseded. Public Lakeview source smoke explicitly refused `unknown_starter_availability:1:1`; no availability assumption was relaxed. Historical accepted replay: Lakeview 2024, four checkpoints, one independent champion; not calibration.

**Mobile:** 1.17.0 intended. EAS build 146 (`c8104c6e-ed72-42e6-86e4-7ccc78002c85`) was canceled before submission because it lacked concurrently landed security changes. Rebuild from reviewed merged revision. Existing security build 145 / 1.16.16 belongs to #279; do not submit it as this release.

**Next:** finish merge/review; required CI on final head; merge PR #280; verify Render actual commit, flags, web and auth behavior; build and submit correct iOS binary to TestFlight; record actual outcomes and recovery ledger before worktree cleanup. Physical iPhone proof remains an operator checklist.

**Security follow-ups retained:** [security deployment record](../docs/plans/security-data-hardening/deployment.md), [review](../docs/plans/security-data-hardening/review.md) and [physical checklist](../docs/plans/security-data-hardening/mobile-evidence.md). Historical production token cleanup/revocation and membership resync are separate maintenance work. Deletion work leases assume the existing single-worker service; no scaling change is part of Win Now.

**Do not repeat:** no invented forecasts or backdating, calibration claim, dynasty Elo updates from Win Now decisions, native simulator/Maestro (D-056), production synthetic maintenance, or deletion of the original dirty checkout. No recurring forecast capture configured. Running jobs are never stolen by another startup; queued jobs resume, expired jobs cannot be revived.
