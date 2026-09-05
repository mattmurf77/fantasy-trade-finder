# HANDOFF — Fantasy Trade Finder

> **Purpose:** current release state and remaining follow-up.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

## Table of Contents
- [Current State — 2026-09-05](#current-state--2026-09-05)

## Current State — 2026-09-05

**In flight, not deployed:** owner-contract first wave on `codex/owner-contracts-20260905`, code commit `86128700`, isolated integration worktree `/private/tmp/ftf-owner-contracts-e8bWFV/integration`, based on `5cf34182`. Astra Ultra mobile/policy builders and independent review completed; parent fixed review findings and passed final local gates: **5,455 backend passed / 1 skipped**, **93 mobile guards**, TypeScript, test-ID lint and **190 web checks**. Publication safety review blocked the push/PR before execution: explicit owner approval is needed to publish the reviewed code and focused engineering notes to the public `mattmurf77/fantasy-trade-finder` repository. No push/PR or hosted CI occurred. Do not retry through another tool/account without approval. No main merge, deployment, experiment activation or device verification is authorized by this patch. All three generator arms remain intact. [Review / remaining work](../docs/plans/owner-contracts/review.md), [unrun TestFlight checklist](../docs/plans/owner-contracts/mobile-testflight.md). Raw owner interview/source documents remain local, excluded from public history; preserve the dirty original checkout and task worktrees.

**Shipped:** Win Now experimental beta, PR #280, `main` release `c28ec6d8`, Render live 05:07:28 UTC. Season projections, Win Now search/evaluation and championship flags all verified true. Dynasty fairness/partner evidence and season-only decisions remain separate from dynasty Elo. User explicitly accepts exploratory evidence; this is not a calibration claim. [Release record](../docs/business/ops/2026-09-05-win-now.md).

**Verified:** exact-head CI 5,353 pass / 1 skip, all four jobs green; parent merged integration 220 pass; 92 client guards/typecheck/testID, 190 web checks, 23 auth checks and Chromium/MV3 runtime. Public live JS/CSS match the release; new endpoints reject unauthenticated access. Actual live landing renders without captured warn/error messages. No authenticated production forecast result is claimed.

**iOS:** 1.17.0 (147) build and App Store Connect upload complete. EAS build `69b53400-1d8d-42ec-ad7a-5d0e3c756059`; submission `6184a831-a685-497b-8e97-734ed30fa4b9`. Apple's processing/tester availability and physical iPhone QA are not verified. Build146 was canceled and never submitted; security build 145 belongs to #279.

**Known limit:** current Lakeview source check refuses `unknown_starter_availability:1:1`. Data-quality guards remain active. Follow [manual checklist](../docs/plans/win-now/EVIDENCE.md) and seek independent/prospective forecast evidence; no recurring capture was configured.

**Security release preserved:** #279 verified ownership/data lifecycle remains intact, with Win Now workers admitted through its deletion leases and alias-aware data removal/export. Keep one Gunicorn worker until distributed fencing exists. Historical production token cleanup/revocation and membership resync remain separate work; [security evidence](../docs/plans/security-data-hardening/deployment.md).

**Win Now recovery:** original dirty checkout preserved. Release branch/worktree tip and publication/content checks are recorded in [recovery ledger](../docs/recovery/2026-09-05-win-now-release.md). No Win Now release implementation or deployment work remains; the owner-contract follow-up above is separate and incomplete. Win Now rollback: three flags false; prior Render code `a927e3a7`.
