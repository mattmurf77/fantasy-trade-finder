# Handoff — Fantasy Trade Finder

> **Purpose:** current implementation handoff; release history lives in CHANGELOG.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

---

## Table of Contents
- [Current State — 2026-09-05](#current-state--2026-09-05)

## Current State — 2026-09-05

**Active request:** user explicitly accepts exploratory historical evidence and authorizes shipping the Win Now, season-projection and championship-estimate beta. Release is in progress in `/private/tmp/ftf-win-now-20260904`, branch `codex/win-now-20260904`; original dirty checkout is preserved. Latest main `0a8093fe` is being merged before release checks. No deployment is claimed yet.

**Implementation:** source forecasts feed league-specific legal lineups and full-season simulations; Win Now searches optimize season benefit while bounding dynasty cost and requiring credible partner benefit. Both clients label estimates experimental/uncalibrated. The release normalizes unused K/team-defense defaults and explicitly discloses omitted rare player bonuses. Canonical freshness revision is being verified after that normalization.

**Evaluation accepted:** four Lakeview 2024 origins (after 3/6/9/12 weeks), 10,000 draws each; one independent champion. Final-win MAE 2.60→0.76. This is exploratory revised-input evidence, not calibration. See [results](../docs/plans/win-now/EXPLORATORY-RESULTS.md) and [release log](../docs/business/ops/release-log.md).

**Next:** parent review of Astra release fixes; final backend/client checks; exact-head CI; merge and Render verification; iOS 1.17.0 production build and TestFlight submission; record actual outcomes and recovery ledger before worktree cleanup. Physical TestFlight check remains an operator follow-up, never claimed from structural tests.

**Other main work preserved:** request-scoring isolation (#277) and collection-only whole-team policy rollout (#278) are integrated; this release changes only the three Win Now flags. Enforcement switches from those initiatives retain main's settings. Their plans and CHANGELOG carry their detailed history.

**Do not repeat:** no invented forecasts, backdated revised inputs, championship calibration claim, dynasty Elo updates from Win Now decisions, Maestro/native simulator (D-056), or removal of the original dirty checkout. No recurring source capture configured.
