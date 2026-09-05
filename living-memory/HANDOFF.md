# Handoff — Fantasy Trade Finder

> **Purpose:** current implementation handoff; release history lives in CHANGELOG.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

---

## Table of Contents
- [Current State — 2026-09-04](#current-state--2026-09-04)

---

## Current State — 2026-09-04

**Where stopped:** Win Now beta plus historical/exploratory evaluation in `/private/tmp/ftf-win-now-20260904`, branch `codex/win-now-20260904`; initial beta `ad3c5346`, history tooling `87304dbe`. Original dirty checkout preserved. No push/merge/deploy/flag activation.

**Latest request completed:** user accepted revised historical inputs and requested evaluator run. Four actual scored origins (after 3/6/9/12 weeks), Lakeview 2024, 10,000 draws each. Final-win MAE 2.60→0.76 (median wins included). Lakeview 2025 excluded for source lineup gap; four FFv3 seasons for K/IDP. [Numeric results/assumptions](../docs/plans/win-now/EXPLORATORY-RESULTS.md). One independent champion; no calibration/generalization claim.

**Evidence:** 144 affected tests pass; direct evaluator and cached replay groups identical; strict control rejects modern revised inputs. Raw replay files `/private/tmp/ftf-win-now-diagnostic-final-20260904`; source cache `/private/tmp/ftf-revised-weekly-cache`. Parent reviewed Astra changes and local replay adapter.

**Outstanding:** production calibration/format coverage and hosted Python 3.12 CI/physical TestFlight before release. All 3 flags false; experimental diagnostic does not alter serving. No authentic pregame full-horizon archive yet.

**Do not repeat:** no silent backdating, future-score standings leakage, fabricated player forecasts, or dynasty Elo updates from Win Now decisions. No Maestro/native simulator (D-056). No recurring capture configured.
