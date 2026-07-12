# QA round 1 — orchestrator adjudication (2026-07-12)

Basis: agent A full report (qa-round-1-agent-A.md) + agent B's completed
non-simulator half (pytest pins 20/20, suite 558, #131 mechanical checks all
pass; sim half still queued at adjudication time). Operator re-sequenced the
pipeline: ship the built batch first, resolution loop second (waiver on file).

| Finding | Classification | Disposition |
|---|---|---|
| F-1..F-3 legacy smoke selectors (01–06 stale matchers) | Brittle tests, NOT app bugs — behavior re-proven green via ad-hoc equivalents | Phase 4 resolution: repair matchers/testIDs (never loosen) |
| F-4 flow 11 Part 2 blocked by OS Apple-Account alert | Simulator environment ([SIM-ENV-SUSPECT] as pre-tagged); device artifact is ground truth (R-8 at ship) | No action; R-8 codesign check runs on the EAS artifact |
| F-5 version carriers 1.7.2 | Expected — R-6 bump is orchestrator-owned at ship | Done in the ship commit (1.7.3) |
| F-6 #126 PRD §4.1–4.5 pins not individually materialized | Test-mapping documentation gap; build agent mapped pins 1–5 onto pre-existing tests (verified passing) | Phase 4: materialize named pins or annotate mapping in the PRD |
| F-7 ESPN sheet content hidden while keyboard open (Continue unreachable until return) | REAL app bug — equals unselected feedback #129; pre-existing in 1.7.2, NOT a regression of this batch | Phase 4 resolution as #129; does not block this ship |

Verdict: no ship-blocking defects in the batch's built code. All seven built
items verified working by agent A on-simulator. Ship proceeds; Phase 4 covers
F-1..F-3, F-6, F-7(#129), followed by a fresh dual-agent QA round.
