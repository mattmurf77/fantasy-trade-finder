# HANDOFF — Fantasy Trade Finder

> **Purpose:** mobile passive preparation candidate and release handoff.
> **Read at:** session start. **Write at:** checkpoint/session end.
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [scope](../docs/plans/mobile-context-preparation/scope.md).

---

## Table of Contents

- [Current State 2026-11-07](#current-state-2026-11-07)

---

## Current State 2026-11-07

**Where I stopped**
- Branch `perf/mobile-exact-context-switches`, base `7e52047e`. Fresh passive preparation overlaps preference/session readiness and does not await disk hydration. Every poll binds captured format/revision; focus/foreground cleanup rejects obsolete responses.
- Serialized disk barriers, per-key hydration fences and disk-only invalidation prevent discarded page revival. Format eviction remains; pending-write fence includes the local mirrors.
- No backend changes: Calibration source revision, scheduled projections and all search/quality budgets stay intact. Exact selected-model/fair handoffs and preview gates are unchanged.

**In flight**
- Local TypeScript, all 165 mobile CI-glob scripts and test-ID lint pass. Independent review: 26 JS plus four external backend controls; no blocker. Root owns final-head CI, merge and TestFlight178; no production action by this worker.

**Blocked on**
- Physical tap-to-visible acceptance remains open. Node lifecycle tests cannot establish 200 ms. Fresh changed-input computation can still take seconds.
- Existing scoring application queue is not account/league-generation bound; this patch protects passive pages, not all format request races.

**Don't repeat**
- No simulator/Maestro, stale-page speedups, selected-request filtering, preview bypass, proof reuse or fast-decoder activation.
