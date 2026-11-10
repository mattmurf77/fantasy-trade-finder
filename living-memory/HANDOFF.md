# HANDOFF — Fantasy Trade Finder

> **Purpose:** launch release handoff after the #629/#628 deploy.
> **Read at:** session start. **Write at:** checkpoint/session end.
> Companion files: [CHANGELOG.md](CHANGELOG.md), [NEXT.md](NEXT.md), [TEST_LEDGER.md](TEST_LEDGER.md).

---

## Table of Contents

- [Current State 2026-11-09](#current-state-2026-11-09)

---

## Current State 2026-11-09

**Where I stopped**
- `main` and the live Render deploy are both `b1440b7b` (#629 give-all fix with pipeline 14, #628 iPhone timing tags), deployed 2026-11-10T02:53Z before the Nov 10 freeze. That SHA is the frozen candidate for the Nov 10 check.
- Calibration `outlook-v2-v3-1` was rebuilt once on that revision: 10 ready, 1 started (its 3 answers kept), 5 known provider failures.
- Work moved to a new MacBook with `gh` (mattmurf77), Python 3.12, Node 20 (via `~/.zprofile`) and `eas-cli`. `prototype/p1-reviewed-integration` (`447a9e27`) and `prototype/p1-atomic-ready` (`85a75ddb`) were recovered from zips; they stay offline by decision and are not on GitHub.

**In flight**
- The instrumented internal TestFlight build from `b1440b7b` hasn't started. `eas` must be logged in as mattmurf77; matthewkmurphy1 has no access to the project.

**Blocked on**
- The 200 ms gate needs real physical-iPhone samples from that build (`qa/instant-trade-acceptance.md`, `--require-physical-iphone --client-build <n>`).

**Don't repeat**
- No simulator or Maestro (D-056). Production runs a single worker: a Calibration rebuild takes about 4–5 min per pair and starves admin reads, so run them off-peak.
