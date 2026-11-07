# HANDOFF — Fantasy Trade Finder

> **Purpose:** selected running-job join candidate and release handoff.
> **Read at:** session start. **Write at:** checkpoint/session end.
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [scope](../docs/plans/selected-running-single-flight/scope.md).

---

## Table of Contents

- [Current State 2026-11-07](#current-state-2026-11-07)

---

## Current State 2026-11-07

**Where I stopped**
- Branch `perf/selected-exact-request-reuse`, base `57b8d7c3`. Strict identical pin/opponent requests can join one live worker. Exact ordered selectors, original source identities, nonmissing signatures/fingerprints, participant epochs and account lifetime are required.
- Force and different selections remain independent; intent-only keeps organic semantics. Completed/failed/stale work is never joined. Normal authorization, preview, currentness, disposition and full quality/publication gates remain.
- Pointer index capped at 128; source refs cleared at terminal/revocation. This is neither a global admission bound nor a complete immutable-input certificate.

**In flight**
- 598 affected and 83 final focused tests pass (overlapping); independent 41 controls pass. Actual 783-card native/final/public/durable parity and duplicate admission counts retained externally. Root owns final-head CI, merge/deploy and Calibration refresh; no push/production action by this worker.

**Blocked on**
- First cold computation and changed selectors still take seconds; no device or universal 200 ms result. Completed proof reuse needs broader input/currentness ownership beyond PR617 pricing.

**Don't repeat**
- No simulator/Maestro, selected-result filtering, preview bypass, quality/budget reduction or fast-decoder activation. Build 178/mobile and scheduled projections remain intact.
