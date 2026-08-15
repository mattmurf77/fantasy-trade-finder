# Feature Scope — Trade Relevance Engine, Phase P0 ("Close the Loops")

**Date:** 2026-08-14
**Entry point:** NEXT.md item 6 (`deck.value_model` graduate-or-kill) → formalized as the
trade-relevance initiative; operator directive "start building" 2026-08-14.
**Builder:** session `744e007c` (orchestrator) + Opus build subagents, worktree
`feat/trade-relevance-p0`.
**Operator sign-off on waivers:** pending — the Maestro waiver (§3) and the tier-4
sim-gate declaration (§5) are the only waivers, both on the "backend-only, zero
user-visible surface" ground stated below.

Binding parents (SIGNED OFF): [hld.md](hld.md) (D1, D2, D11, §2.1, §2.3, §6),
[lld.md](lld.md) (build steps B1–B8, §3.1–3.3, §4.1–4.6, §7),
[prds/prd-p0-close-the-loops.md](prds/prd-p0-close-the-loops.md).

**Scope note — two P0 items landed independently on 2026-08-14 and are OUT of this
build:** R4/P0-1 (register the 27 dropped client events) shipped as PR #116
(`4733f78`); R6 (impression-ownership validation on outcome writes) shipped as
`9910ae6` with its own scope block at `docs/plans/deck-outcome-validation/scope.md`.
Remaining P0 = LLD steps B1, B2, B4, B5 (the *join* half only), B6, B7, B8 + the
admin report and doc hygiene.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** P0 adds **no new client or server events.**
  The phase's observability rides three non-event channels: the `cron_pass_runs`
  ledger, per-job `deck_job_stats` gate counters, and the existing
  `deck_impressions`/`deck_outcomes` spine (which gains four `action` enum values —
  a widening of an existing stream, not a new event).
  - The four new `deck_outcomes.action` values (`accepted`, `declined`,
    `accepted_by_partner`, `declined_by_partner`) answer: "did the trade we served
    actually get accepted or declined, and by which side?" — today unanswerable
    (the labels exist only as `user_events` rows with no impression key).
  - `deck_outcome_rejects` (already shipped with `9910ae6`) answers "are clients
    sending stale/foreign impression ids?"
  - **Seam note:** no historical series exists for the four new actions. Do not
    trend accept/decline-per-impression across 2026-08-14.
- Taxonomy follow-through: `docs/data-dictionary.md` rows for every new table and
  column (§2). No `analytics_taxonomy.py` change — nothing new is client-emitted.

## 2. Schema & flag scope

**New tables** (all additive, `metadata.create_all()`; retention stated):
`cron_pass_runs` (90d, registered in the existing retention endpoint as part of the
B1 diff), `deck_class_stats` (latest `stat_date` live, 30d history), `deck_job_stats`
(per completed deck job).

**New columns** (all nullable or constant-default — SQLite forbids `NOT NULL`
without default, LLD §3.1): `trade_decisions.impression_id`;
`trade_matches.impression_id_a` / `.impression_id_b` / `.join_quality_b`;
`deck_outcomes.join_quality` / `.source_match_id`. Each is paired with its
`Column(...)` in the Table declaration so a fresh `create_all()` DB matches a
migrated one (test T-25).

**Enum widening** is app-level, not DDL: `deck_outcomes.action` has no CHECK
constraint, so the four D2 labels are added via one authoritative
`DECK_OUTCOME_ACTIONS` constant + writer validation + reader whitelists (LLD §3.1,
§6.2). Readers whitelist, never blacklist — audited list in LLD §6.2.

**New feature flags** (`config/features.json` + `FLAG_KEYS` + config-reference, all
default **false**, dark-launchable, byte-identical when off):
- `deck.dedup` — graduation: near-dup rate <1% vs the measured pre-ship baseline,
  p95 deck latency within ±5%, no like-rate regression beyond CI.
- `deck.class_demotion` — graduation: `flag_agg` pass green ≥7 days dark, operator
  review of the demoted-class report, then flip; kill = flag off.

**New `model_config` keys** (Float; deploy-free levers): `class_demotion_floor` 0.5,
`class_demotion_min_views` 200, `dedup_overlap_tau` 0.75.
**Operational valves, deliberately unseeded:** `cron.pass_disabled.<name>` — absent
⇒ the pass runs (inverted polarity fails safe; a typo can never silently stop the
`pushes` pass). These are read by `relevance.config.valve()`, exempt from the D10
resolver so no experiment overlay can resurrect a killed pass.
**Ship-the-knob / rollback levers:** every risky surface has a deploy-free off
switch — `deck.dedup` off, `deck.class_demotion` off, `dedup_overlap_tau=1.0` (soft
dedup off), `cron.pass_disabled.<name>=1` (kill one nightly pass immediately).

## 3. Test scope (mobile test platform)

- [x] **WAIVED — no Maestro delta.** P0 has **zero user-visible mobile surface**:
  no new screens, no copy, no layout change, no new client call. The only
  client-observable deltas are (a) decks contain fewer near-duplicate cards and
  (b) card order shifts — both are existing-surface behavior changes that no
  `testID` or flow assertion covers, and both are flag-gated off at merge.
  The web `impression_id` echo (PRD R7) is invisible plumbing on an existing
  request body.
- `testID`s added/renamed: **none** → `testid-lint.sh` unaffected.
- **Capture delta:** none — no visual change.
- Smoke-suite impact: none of the 11 smoke flows assert deck composition or card
  order; all remain green unchanged (both flags ship off).
- **Backend pytest (this is where the rigor goes):** new files
  `test_p0_schema.py`, `test_relevance_config.py`, `test_relevance_batch.py`,
  `test_pass_ledger.py`, `test_disposition_join.py`, `test_class_demotion.py`,
  `test_deck_dedup.py`, `test_propensity_freeze.py`, `test_gate_counters.py`.
  Every behavioral test is **sabotage-proven** (each states the sabotage that must
  make it fail) per the house convention; the LLD's T-1…T-9, T-23, T-25, T-29
  map onto these files.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `POST /api/cron/daily-tick` response gains `"passes": {name: status}`; new `GET /api/admin/analytics/relevance` |
| `living-memory/LLD.md` | **updated** | New convention: nightly work is a registered *pass* with a ledger row, not an inline tick block; operational valves live in `model_config`, not `features.json` |
| `docs/architecture.md` | **updated** | New `backend/relevance/` package in the module map; the stale "Request lifecycle (trade card — v2 engine)" section corrected (PRD R12) |
| `living-memory/HLD.md` | **updated** | Genuine architecture shift: a batch/derive layer now exists as its own package with a pass registry |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or color crosses clients; the four new `action` values are server-internal (no client reads `deck_outcomes`) |
| `docs/glossary.md` | **updated** | New terms: pass ledger, near-dup dedup, class demotion, propensity freeze, join quality |
| ADR / `DECISIONS.md` | **updated** | D-entry for "nightly passes get a ledger + inverted-polarity valves" (D1) and "gates gate, multipliers reorder — flag aggregation is never a veto" (D11) |
| `docs/data-dictionary.md` | **updated** | 3 tables + 6 columns (§2) |
| `docs/config-reference.md` | **updated** | 2 flags + 3 model_config keys + the valve convention |
| `docs/runbook.md` | **updated** | Red-pass triage from the ledger; the `cron.pass_disabled.*` kill lever |

## 5. Ship gate declaration

- **Simulator-gate tier: 4 (none — CI only).** Justification against the runbook
  matrix: the change class is backend-only with zero user-visible mobile surface
  and both user-affecting flags ship **off**; there is nothing a simulator run
  could execute that CI does not already cover. The gate that actually protects
  this change is the backend suite plus the T-1 tick-equivalence test (the B1
  refactor touches live push-sending code, so equivalence — including an Aug-25
  `season_start` fixture — is a hard merge gate).
- Evidence at ship: TEST_LEDGER entry with suite counts + the T-1 result; no
  `qa/sim-runs/last-sim-run.json` (tier 4). The pre-push hook's sim gate is
  expected to require `FTF_SKIP_SIM_GATE=1` for this reason — recorded here rather
  than decided at push time.
- **Operator deviation from the matrix:** none claimed. Tier 4 IS the matrix
  answer for "no user-visible mobile change"; the Maestro waiver in §3 is the
  only waiver and is stated on the same ground.
- **Bright line:** this change touches schema and flag surfaces, so it is **never
  express** — full gates apply even though the operator's instruction was a terse
  "start building."
