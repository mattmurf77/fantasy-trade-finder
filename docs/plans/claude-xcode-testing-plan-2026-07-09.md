# Claude-Driven Mobile App Testing — Plan (SUPERSEDED)

> **Superseded 2026-07-10 by the mobile-testing doc suite: [docs/plans/mobile-testing/](mobile-testing/)** — `plan.md` (rev 3), `prd.md`, `hld.md`, `lld.md`, `test-cases.md`, grounded in `app-inventory-2026-07-10.md`.
>
> Rev 3 corrections that invalidate this rev 2 document:
> - Rev 2 assumed the app made "Sleeper public reads" directly. Wrong: **all** Sleeper traffic proxies through the FTF backend, which live-calls `api.sleeper.app` (including sign-in). Hermetic testing is achieved server-side via a fail-closed fixture seam in `_sleeper_get` — see HLD ADR-1.
> - Rev 2's fixture story ("seeded SQLite profiles") could not boot a session on its own.
> - Rev 2 sized the app at 9 flows / ~40–60 testIDs; the 2026-07-10 inventory establishes 19 screens / 82 features / 13 feature flags → ~30 flows / ~90 IDs / ~190 test cases.
> - Layer 3 must run on a dedicated QA Sleeper account (the TestFlight binary writes to prod) — see HLD ADR-8.
>
> The three-layer architecture (Maestro simulator matrix → release-build gate → TestFlight via iPhone Mirroring), the safety rails, and the Maestro-over-XCUITest decision carry forward unchanged.
