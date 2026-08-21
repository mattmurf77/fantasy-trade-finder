# PLAN — Receipts

**Date:** 2026-08-21 · **Kind:** planning only (no code) · **Branch:** `plan/receipts`
**Process:** dual-agent doc review (Author/Feasibility × Adversary/Risk), drafts + cross-review; reconciliation log in [README.md](README.md).
**Operator brief:** close the loop on trade suggestions by scoring them against subsequent
value movement; user-facing league track record + internal per-shape accuracy; the serve-time
card snapshot is the immutable prediction ("preregistration").

---

## Table of Contents
- [1. Objective & definition of done](#1-objective--definition-of-done)
- [2. Scope](#2-scope)
- [3. Measurement honesty rules](#3-measurement-honesty-rules)
- [4. Workstreams & milestones](#4-workstreams--milestones)
- [5. Sequencing & dependencies](#5-sequencing--dependencies)
- [6. Risks & abort criteria](#6-risks--abort-criteria)
- [7. Reconciliation contract (three-plan batch)](#7-reconciliation-contract-three-plan-batch)
- [8. Open questions & operator decisions needed](#8-open-questions--operator-decisions-needed)

---

## 1. Objective & definition of done

A recurring job grades past suggestion cards (`deck_impressions`, `backend/database.py:500`,
features frozen at serve per the table contract at `backend/database.py:490-499`) against
subsequent **consensus** value movement (`player_value_history`, `backend/database.py:1298`)
at 14/28/56-day windows, writing append-only `receipts_grades` rows. Two consumers:

1. **User surface:** mobile `ReceiptsScreen` — the viewer's own suggestion track record in a
   league, both sides of every trade, wins and losses rendered identically.
2. **Internal:** per-taxonomy-cell accuracy readouts (shape × basis × arm × ghost × window)
   — the productization of trade-engine-accuracy PLAN Phase 1.2 ("read the ghost holdout —
   nobody has looked", [docs/plans/trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md)).

This is a **measurement** feature under that plan's philosophy: it changes zero engine
behavior and creates the evidence a future engine change could be judged against.

**Done (v1) =** grading job live and idempotent in prod; backfill of the telemetry-era cohort
drained; internal readout reviewed by the operator; `ReceiptsScreen` shipped behind
`receipts.screen` and graduated per §6 A-2; all four feature gates satisfied (scope block,
D-056 evidence, docs table, TEST_LEDGER).

## 2. Scope

**In v1:** grading job + `receipts_grades`/`receipts_grade_runs` tables; launch-day backfill
(telemetry-era rows only); `POST /api/cron/receipts-grade`; `GET /api/league/<id>/receipts`;
`GET /api/admin/receipts/metrics`; `ReceiptsScreen` (root-stack push); three analytics
events; flags `receipts.grading` + `receipts.screen`; shared trade-shape taxonomy adoption.

**Out of v1 (explicit non-goals, each a seam someone will push on):**

| # | Non-goal | Why written down |
|---|---|---|
| NG-1 | Feedback into generation/ordering — nothing in the engine reads `receipts_*` | Goodhart (PRD §7 HL-1); change-control rule (accuracy PLAN Phase 0.4). Boundary artifact defined in §7.3 |
| NG-2 | Executed-trade claims — that is `suggestion_trade_links` (`backend/database.py:657`, `backend/suggestion_telemetry.py`) | "Did they do it?" ≠ "was it right?"; conflation is the fastest route to a debunkable claim |
| NG-3 | Cross-user receipts — a user sees only impressions served to their `user_id` | Other managers' decks/swipes are private; league-wide aggregate deferred (open question Q-2) |
| NG-4 | Grading against personal boards (`elo_history`, `backend/database.py:1274`) | Endogeneity: swipes prompted by our own suggestion move the yardstick (PRD HL-2) |
| NG-5 | Web/extension surface, push notifications, Wrapped tie-in | Trust-risk blast radius before the numbers are understood |
| NG-6 | Pick-value modeling — picks are Δ=0, never modeled | Pick prices are code events (`GENERIC_PICK_SEEDS`, `backend/pick_values.py:24`; D-084 repriced round 2 on 2026-08-19) — grading them grades our own commits |
| NG-7 | Backfilling pre-telemetry impressions | The 7,740 arm-`(none)` rows have no `assets_json` (telemetry columns landed 2026-08-16, commit `1ba148c`, "no backfill") and `trade_hash` is not invertible. Reconstructing assets at grade time would mint a new prediction — the exact move preregistration forbids |
| NG-8 | Negative-results memory (sibling plan) | Out of scope here; §7.4 records the schema choices made so it is NOT foreclosed |

## 3. Measurement honesty rules

Binding on every surface, user-facing and internal:

1. **Preregistration.** The prediction is the serve-time `deck_impressions` row —
   `assets_json` (asset ids + direction) plus frozen slice keys. The grader never recomputes
   serve-time values, never reads engine-current values, never reconstructs assets. Full
   enforcement rules in PRD §5.3 / LLD §4.
2. **The headline metric is swap edge, not acquire-side %.** `edge = receive-side consensus
   delta − give-side consensus delta`, both endpoints from `player_value_history` — the give
   side is the control arm, so market drift cancels to first order. A standalone
   "acquire side +X%" is on the banned-phrasing list (PRD §4.4).
3. **All three windows (14/28/56d), always.** One API payload carries all windows; no
   surface may select the best-looking one. Headline window is 28d, fixed in advance.
4. **Small-n discipline.** Total engagement history is tiny (~845 like/pass outcomes
   all-time at 2026-08-19 — verified in the negative-results session's memo,
   `docs/plans/negative-results-memory/research-verification.md` §8, citing
   TEST_LEDGER; the gradeable impression cohort starts 2026-08-16). Per-taxonomy-cell
   counts will be single digits for months. Therefore: every internal per-cell readout
   reports n and a **Wilson 95% interval** on win share (or empirical-Bayes shrinkage
   toward the global mean where a point estimate is needed); the user surface renders a
   headline only at `n ≥ receipts_min_n` (default 10) and always displays n
   ("12 of 19 suggestions"). No bare percentages anywhere.
5. **The ghost cohort is a fixed historical population.** `is_ghost=1` rows
   (suggested-but-never-shown; 273 of 1,371 bake-off-era impressions) are graded
   identically as the natural control for serving/selection effects — internal only.
   The holdout was closed when the operator zeroed `ghost_holdout_one_in`
   (ordered 2026-08-20, commit `024b030` message; effective end
   **2026-08-21T00:43Z** per the coordinating session's prod `model_config_changes`
   read — repo-unverifiable, re-verify at build, same as the breaker plan's A-1).
   Design treats ghosts as a **bounded backtest cohort, not an ongoing stream**; if the
   knob ever comes back, new rows extend the cohort without design change.
6. **Selection disclosure is structural.** Gradeable share (graded / touched) is computed
   from the grades table itself and reported next to every aggregate; internal cells with
   gradeable share < 70% are flagged. Losses render identically to wins; best-call is never
   shown without worst-call.

## 4. Workstreams & milestones

| Phase | Deliverable | Done bar |
|---|---|---|
| **P0 — pre-build data gate** | Read-only prod counts (LLD §8 queries): gradeable impressions, per-league histogram, ghost share + end date, pick-involvement share, snapshot gap rate | Numbers in this plan's directory; A-1 evaluated |
| **P1 — grader dark** | `backend/receipts_service.py` + tables via `_migrate_db` + `POST /api/cron/receipts-grade` (202 + daemon) + daily-tick guard + flag `receipts.grading` + knobs + pytest suite + `scripts/receipts_backfill.py` | CI green; job runs in prod dark; backfill drained; `receipts_grade_runs` ledger populating |
| **P2 — internal readout** | `GET /api/admin/receipts/metrics` (X-Cron-Secret) with served-vs-ghost split + Wilson intervals | Operator reviews first real numbers (the A-2 checkpoint); accuracy-PLAN Phase 1.2 delivered |
| **P3 — user surface dark** | `GET /api/league/<id>/receipts` + `ReceiptsScreen` + RootNav root-stack registration + FeedbackFAB + analytics events (same commit as taxonomy/queries registration) + `mobile/tests/check-receipts.js` | CI green incl. structural check; screen behind `receipts.screen` (off) |
| **P4 — graduate** | TestFlight checklist run by operator; flip `receipts.screen` | Graduation criteria of PRD §8 met |
| **Follow-ons (not v1)** | feedback-into-scoring PRD (must answer HL-1's holdout objection); pick value history; league-wide aggregate (Q-2); shuffle baseline (`baseline_edge` reserved column) | own docs, own gates |

## 5. Sequencing & dependencies

**Critical path:** P0 → P1 → P2 → (operator checkpoint) → P3 → P4. P3's mobile work can
draft in parallel with P2 but must not merge before the P2 checkpoint (the checkpoint can
change copy — framing, never cohort/metric — see A-2).

Dependencies:
- **Value-snapshot supply** (existing): `/api/cron/value-snapshot` (`backend/server.py:19493`)
  + the hourly-tick fallback guard (`backend/server.py:19166`). No provisioned Render cron
  exists for it (a claimed one was reverted, commit `1e50d3e`) — the fallback is the
  operative writer and has kept daily coverage since 2026-07-26 (commit `5b2dc5f`).
- **Cron trigger for grading:** dedicated endpoint + a daily-tick internal guard calling the
  same function (the `roster_history` three-trigger pattern, `backend/database.py:1320-1336`)
  so grading runs even if no blueprint change ships. A 4th render.yaml cron service is
  optional hardening, deliberately NOT on the critical path (blueprint sync burned before).
- **Shared taxonomy:** `docs/plans/shared/trade-shape-taxonomy.md` (already seeded, v1.0.0)
  — P1 stamps its version string on every grade row.
- **Sibling reconciliation** (§7) before any of the three efforts merges schema.
- **Operator approvals:** A-1 evaluation after P0; A-2 checkpoint after P2; `receipts.screen`
  flip at P4. All logged in §8's register.

## 6. Risks & abort criteria

| ID | Risk / trigger | Response |
|---|---|---|
| A-1 | P0 counts show < ~300 gradeable impressions across ≥3 leagues | Build P1 dark anyway (grading is cheap and starts the clock); **defer P3/P4** until the cohort supports a screen whose median league is not n=3 |
| A-2 | First real readout looks bad | **Framing, not filtering** — pre-committed here: a bad number changes copy ("how suggestions tracked the market, both directions"), never the cohort, window, or metric. Publish or abort the screen; never publish a flattering subset |
| A-3 | Rollback | Both flags default false; flag-off = cron no-ops + route 404 + screen entry hidden; tables additive, no drop; deploy-free via `POST /api/feature-flags/reload` |
| A-4 | Grader bug confirmed | No row edits ever — `grader_version` bump + regrade, old rows retained (LLD §3). Two bumps inside a month = stop and re-review the grader design |
| A-5 | Value-snapshot supply gap > 7 consecutive days | Pause grading (grades would silently degrade to tolerance-edge matches); fix supply first. Gap rate measured at P0 |
| R-1 | Survivorship via pool churn (busts leave the snapshot pool) | Pool-floor imputation, flagged per asset — losses stay in the sample (LLD §4.3) |
| R-2 | Trust damage from tiny-n or debunkable claims | min-n gate; both-sides row format is the only row format; banned-phrasing list (PRD §4.4) |
| R-3 | Single prod worker blocked by grading | 202 + daemon thread + single-flight + batch cap (LLD §5.1); precedent `cron_players_refresh` (`backend/server.py:19512`) |

## 7. Reconciliation contract (three-plan batch)

Receipts × negative-results memory × counterparty breaker reconcile before operator
delivery. Counterpart text: breaker PLAN §8 (`docs/plans/counterparty-breaker/PLAN.md`, that
session's branch) and the negmem memo
(`docs/plans/negative-results-memory/research-verification.md`). This section is the
Receipts side; the breaker's assumption A-2 awaits exactly this text.

### 7.1 One shared taxonomy
**Artifact of record: [docs/plans/shared/trade-shape-taxonomy.md](../shared/trade-shape-taxonomy.md)**
(seeded v1.0.0 by this session; every dimension carries a file:line citation). All three
plans adopt it verbatim; changes only by PR touching the shared file, version-bumped, with
per-consumer impact notes. The 1.1.0 objection-vocabulary section (anchored on
`trade_pass_reasons` codes, per-code producer column; `roster_crunch` → breaker,
`shape_aversion` → negmem) is reserved in the file and authored by the breaker session.
**Recommendation carried from draft A (proposed 1.2.0 direction, needs three-way sign-off,
not a v1 fact):** a Python mirror module of the taxonomy would make the producer-column
boundary test-enforceable; v1 instead ships a receipts-local `TAXONOMY_VERSION` constant
mirroring the doc version, stamped on every grade row — no shared module required.

### 7.2 Table ownership
- Receipts **writes only** `receipts_`-prefixed tables: `receipts_grades`,
  `receipts_grade_runs` (reserved, unbuilt: `receipts_pick_history`). Sibling prefixes per
  breaker PLAN §8: `negmem_` (memory) · `breaker_` (breaker, unused v1).
- Receipts **reads, never writes:** `deck_impressions`, `player_value_history`, `leagues` /
  league-scoring lookup (`set_league_scoring`, `backend/database.py:6897`), session/auth
  tables, `model_config`. **Not even read in v1:** `deck_outcomes`, `elo_history`,
  `trade_matches`, `suggestion_trade_links`, `member_rankings`. Enforced by pytest (LLD §7).

### 7.3 Generation-pipeline seams — zero footprint, seams RESERVED
- Receipts adds **no line** to `trade_service.py`, `trade_optimizer.py`,
  `bakeoff_runner.py`, `trade_gen_fit.py`; the grader imports no engine module
  (test-enforced, LLD §7).
- **RESERVED seam — feedback-into-scoring (follow-on only):** the boundary artifact is the
  per-cell accuracy read keyed `(taxonomy cell, taxonomy_version, policy_version,
  window_days)` served by `/api/admin/receipts/metrics`. If a future PRD consumes it, the
  natural hook is the ordering/presentation multiplier stack where per-card priors already
  compose (the propensity/Thompson layer stamping `deck_impressions.propensity`,
  `backend/database.py:506-514`) — never the generation path. That PRD must also answer
  PRD HL-1's holdout objection. Nothing in v1 builds any of this.
- **Breaker adjacency (recorded for the reconciliation):** the counterparty breaker's
  generation-side hook is the fit arm's partner-side lens
  (`backend/trade_gen_fit.py:5-14` raw-board dual lenses; `_combine` `:673`), which is
  import-isolated by design. Receipts neither uses nor blocks it; per breaker PLAN §8 the
  seams are disjoint by construction (negmem = generation-time prior · breaker =
  post-ranking evaluate+stamp · Receipts = offline cron + read routes).

### 7.4 Not foreclosing negative-results memory
Three deliberate schema choices: (1) grades keyed by `impression_id` with league / taxonomy
slice keys denormalized → per-league priors are one GROUP BY, no `features_json` parsing;
(2) ghosts graded identically → no served-only assumption baked in; (3) per-asset deltas
kept in `assets_detail_json` → asset-level priors remain possible. Rejected alternatives
that WOULD have foreclosed it: grading only served+swiped rows; storing only package-level
aggregates.

## 8. Open questions & operator decisions needed

| # | Question | Default if unanswered |
|---|---|---|
| Q-1 | A-1 threshold ruling after P0 counts: ship the screen on the maturity/"preregistration ledger" state (recommended — the ledger IS the trust story), or wait for the first mature league? | Ship the ledger state |
| Q-2 | League-wide (all-manager) aggregate: allowed later, given reverse-engineerability at n≈5 leagues? | Out until leagues are bigger; viewer-scoped only |
| Q-3 | `receipts_min_n` default (10) and 28d headline window — cheap to change (model_config) but the first published values anchor expectations | 10 / 28d |
| Q-4 | Render cron 4th service vs daily-tick-guard-only | Guard-only; blueprint change deferred |
| Q-5 | Ghost-cohort end timestamp + interleave state verified against prod `model_config_changes` at build (breaker A-1 twin) | Treat as closed 2026-08-21T00:43Z |
| Q-6 | Confirm sibling prefix claims + taxonomy 1.1.0 sign-off at reconciliation | Per §7 as written |
