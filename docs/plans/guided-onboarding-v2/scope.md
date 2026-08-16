# Feature Scope — Guided Onboarding v2, Phase 0 + Phase 1

**Date:** 2026-08-15
**Entry point:** direct ask (operator: "proceed with building this using opus subagents. you review all code and merge it") — PRD at [PRD.md](PRD.md), post-Phase-A delta at [DELTA-2026-08-15.md](DELTA-2026-08-15.md)
**Builder:** dual-agent-validated PRD → orchestrated Opus build agents, orchestrator reviews all diffs and merges
**Operator sign-off on waivers:** yes — full gates declared by PRD OQ-8; the one scope *deviation* from the validated PRD (FR-E1 descope, below) follows the delta report and is surfaced in the build summary

**Build scope:** PRD Phase 0 (re-scoped per delta) + Phase 1. Phase 2 (N6.2, N3, N5, N7) and Phase 3 wait on Phase-1 exit gates.
**Scope deviation from the PRD, stated:** FR-E1's second-gate rewiring is **descoped** — Phase A flipped all the gating flags on and the tour is live; rewiring live-gating code now buys robustness FTF no longer needs at real regression risk. What remains of FR-E1: the s7.1 cut (still broken live), the reachability table, and the `onboarding.guide_v2` gate for all v2 additions.

---

## 1. Analytics scope

**(a) New events specced** (all mobile client; all land in `user_events`; taxonomy addendum ships **before** emitters, read-back verified per FR-E8 / G-031 / G-036):

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `guide_step_suppressed` | `step`, `blocked_by` | `requestStep` refused (slot busy, eligibility fail, `matched` suppression) — once per deferral episode | mobile |
| `guide_step_shown` (existing) + **new prop `spotlight`** | `spotlight ∈ {'measured','degraded','none'}` | existing emit site in `requestStep` | mobile |
| `outlook_saved` | `source` | first preference write in a `TradeDnaSheet` session | mobile |
| `finder_target_pinned` | `side`, `source` | targeting-board pin recorded | mobile |
| `quickset_started` | `position`, `source` | QuickSetTiers mounted with intent (guide handoff vs organic) | mobile |
| `awaiting_segment_viewed` | `source` | Matches "Awaiting them" segment focused | mobile |

Notes: `guide_step_advanced` gains **no** new rows — `via` is already registered and `'timeout'` is in the union (delta-verified). `quickset_completed` is server-fired; client retirement re-sources to persisted `quicksetCompletedPositions` (delta §CHANGED). `guide_tour_reenabled` already registered post-Phase-A — no work. MFL/ESPN send-attempt rows are **Phase 2**, not built now.
**O-6/O-7 addendum (operator, mid-build):** register **`trio_session_started`** (`position`? props per existing emitter at `RankScreen.tsx:92` — emitter already ships, event currently dropped) for N8's Trios arm; N8/N9/N5 use existing or above events only. Build now additionally includes beats `N8` (import question at ranking-process launch), `N9` (Matches first-visit floor), `N5` (pulled forward with first-visit trigger), first-visit trigger floors per O-7, the guided-trios/import forced-regen return handoff, and `s3.2`'s CTA re-route to RankHome guided entry. New `testID`s additionally: `guide.n8.upload`, `guide.n8.simple`, League position-pill row registration.
→ follow-through: taxonomy addendum in `backend/analytics_taxonomy.py`; `docs/config-reference.md` event rows; no new storage beyond `user_events` (data-dictionary n/a).

## 2. Schema & flag scope

- Tables/columns: **none**
- Feature flags: **`onboarding.guide_v2`** — new, **default `false`**. Gates: the eligibility layer, arbiter membership, all new beats, the copy changes riding the new script fields. Off = byte-identical to pre-build behavior (the rollback lever; deploy-free via flag reload). Graduation: default-on after the operator TestFlight checklist passes and first-cohort diagnostics (M1–M8) are clean. Follow-through: `config/features.json` + `FLAG_KEYS` + **the four flag fixtures / `test_seed_ui_test_db.py:107` mirror assert** (delta §New scope) + `docs/config-reference.md`.
- Env vars / model_config: none

## 3. Test scope

- **Maestro / simulator: RETIRED — not a waiver, the amended convention** (D-056/D-057, operator ruling 2026-08-15; CLAUDE.md §Feature gates items 2 & 4). No flows authored, extended, or run.
- **Automated evidence replacing it:**
  - `mobile/tests/check-guide-script.js` — NEW structural suite on the `check-s51-regen-diff.js` template: every script entry carries retirement (`retireAfter` | justified `'never'`), `maxDisplayCount`, `adoptionEvent`, degrade contract (`degradeLine` | `'suppress'` | non-deictic), copy-class word caps, `autoMs ≥ words/4.17×1000 + 800`, one primary action; plus the s8.1-rewire assertion (`n6.1 || s6.1`) and the s7.1-removed assertion.
  - CI wiring for `mobile/tests/check-*.js` (added scope — no `check-*.js` runs in CI today, delta-verified).
  - Backend: taxonomy round-trip pytest for the six new rows; fixture/mirror updates for `onboarding.guide_v2`.
- **Code-walk proofs** (written, file:line-cited, in the build record): N6.1 onSuccess gate sequencing; s6.2/Apple chain rewrite (consume-only-on-show); interrupt-slot claim ordering.
- **Manual TestFlight checklist for the operator** (runtime proof): fresh-install walk of Act I + N1/N2/N4/N6.1; v1-upgrade install (no re-teach, sign-off reachable); `guideDismissed` install (zero bubbles); flag-off install (byte-identical); redraft league (N1 suppressed, s3.2 alive). Logged in TEST_LEDGER on completion.
- `testID`s added: `trades.deck-summary.pin` (N4 CTA), `guide.n6-1.cta` (N6.1 primary), `guide.n6-1.later`; all pass `mobile/scripts/testid-lint.sh` (still in CI).
- Capture delta: **none** — capture pipeline retired with D-056 (the s5-1 library-gap ruling is open with the operator, out of this build's scope).
- Smoke-suite impact: n/a (suite retired from execution).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed (Phase 3 would add one; not built) |
| `living-memory/LLD.md` | **updated** | `GuideStep` required-fields convention + client-receipt rule (server-fired events never drive client retirement) |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift (server-delivered script is Phase 3) |
| `docs/cross-client-invariants.md` | n/a | guide is mobile-only; no shared constants |
| `docs/glossary.md` | **updated** | "beat", "retirement condition", "degrade line", "ranking ladder" |
| ADR / `DECISIONS.md` | **updated** | new D-entry: FR-E1 descoped post-Phase-A + the guide eligibility layer as the governing convention |
| `docs/config-reference.md` | **updated** | `onboarding.guide_v2`, six event rows |
| `docs/runbook.md` | **updated** | kill-switch reality (one-key: `onboarding.guided_layer` false → guide-off falls back to nothing unless flipped); guide flag-preconditions list |

## 5. Ship gate declaration

- **Simulator-gate tier: retired** (D-056/D-057). `FTF_SKIP_SIM_GATE=1` is the standing posture for the pre-push hook, per amended CLAUDE.md — not an express-lane use.
- Evidence at ship: structural suites green (`check-guide-script.js`, existing `check-*.js`, `testid-lint.sh`), `tsc` clean, backend pytest green, code-walk proofs in the build record, TEST_LEDGER entry; operator TestFlight checklist is the post-merge runtime gate before any default-on graduation.
- Operator deviation: none beyond the documented FR-E1 descope (delta-driven, surfaced above).
