# PLAN — Negative-results memory (planning-stage delivery plan)

**Date:** 2026-08-21 · **Status:** planning only — build gated on operator review of the
full suite · Parent: [README.md](README.md) · Facts: [research-verification.md](research-verification.md)
(cited as "memo") · Gates: [scope.md](scope.md)

---

## 1. Objective

Close the "memory" half of the suggestion loop: rejected proposals stop being log rows
and become a per-league prior the engine consults BEFORE generating — so dead trade
families are down-weighted at the source, and the already-ratified per-manager
acceptance prior in gen_v2 finally gets fed. Sibling features close the other halves:
Receipts (post-mortem grading), Counterparty breaker (present-state objection). One
loop, three owners, one shared vocabulary.

**Success criteria for the PLANNING phase (this document's own bar):**
PRD/HLD/LLD authored via dual-agent review, each internally signed off; three-way
reconciliation completed against Receipts' contract; the three operator decisions
(scope §6) presented with recommendations; zero code built.

## 2. Design skeleton the doc suite elaborates (from the memo's constraints)

- **Two mechanisms, one memory:**
  - **M1 — generation-time soft prior (layers 1+2).** One bulk read per (user, league)
    job → in-memory map keyed `(partner_league_id, shape_bucket, reason_family)` with
    regime tags and decayed, shrunk counts → clamped multiplier consulted inside the
    per-opponent loops of every arm (v1/v3 `trade_service.py:4563`, gen_v2
    `:939-975`, fit's step-5 seam; memo §2h). Sink-never-rise; no gated-card rescue;
    stamped on `features_json.negmem`.
  - **M2 — feed the stub (layer 2 seed).** Aggregate per-league-mate response stats
    (proposals seen / accepted / declined, from `trade_matches` + decline records) into
    `acceptance_stats` at gen_v2's two call sites (memo §2f, §DC-10). Zero schema, zero
    new math, knobs already seeded.
- **Not a fourth filter.** Positioning section in the PRD against F3 fatigue (durable
  exact-pair promises), D-067 cooldown (windowed exact-key dedup), F5 taste (user-scoped
  post-generation re-ranking): this feature is league-scoped, generation-time,
  family-level, SOFT, and auditable (every effect stamped + explainable from stored
  reason codes). If the PRD cannot state a card-level behavior difference from each of
  those three, the feature doesn't ship.
- **Data hygiene baked in:** viewed-gating, ghost exclusion (population ends
  2026-08-21T00:43Z), D-091 window (2026-08-16→08-19) excluded by timestamp, shrinkage
  mandatory at n≈845, `user_value_basis` respected when coding value-reason rejections
  (a pass on personally-priced cards is board-fit evidence, not market evidence).
- **Identity:** league ids throughout (memo §DC-8).
- **Bake-off citizenship:** the prior is part of the model under test — knobs
  snapshotted in `bakeoff_runs.config_json`; measurable per arm from day one.

## 3. Workstreams (for the eventual build — estimated, not scheduled)

| WS | Content | Est |
|---|---|---:|
| W1 | Map builder: bulk read + shrinkage + decay + regime tags + hygiene windows; pytest | 1.5d |
| W2 | Consultation seams: v1/v3 + gen_v2 + fit, clamp semantics, `features_json.negmem` stamp; flag + knobs + dispositions + seed rows | 1.5d |
| W3 | M2 stub feed: aggregation query + the two call sites; parity test vs documented E-B math | 0.5d |
| W4 | Evidence: goldens (flag-off byte-identical), code-walk, readout SQL additions (negmem stamp rates per arm), TestFlight checklist | 1d |
| W5 | Docs + living-memory + taxonomy v1.1.0 section (three-way) | 0.5d |

Rollout: dark (flag off) → operator flips for their league → bake-off-measured (the
serving rounds already running make the prior's effect readable per arm).

## 4. Doc pipeline (this phase)

1. **PRD** — dual-agent-doc-review. Owns: the two-layer boundary, the three operator
   decisions with recommendations, positioning-vs-existing-mechanisms section, privacy
   options, graduation criteria, the D-067 argument.
2. **HLD** — dual-agent-doc-review. Owns: the shared consultation seam (or per-path
   seams), map schema, regime-tag design, M1/M2 composition, bake-off interaction,
   derive-vs-materialize gate.
3. **LLD** — dual-agent-doc-review. Owns: signatures, the bulk query, clamp math, knob
   table with disposition sentences, test plan, exact stamps.
4. **Reconciliation** — three-way, against Receipts' published contract: taxonomy
   v1.1.0 (rejection/objection vocabulary + PRODUCER column), table-namespace
   confirmation (`negmem_` reserved, none used in v1), seam registry (mine
   generation-time; breaker post-ranking; receipts offline cron).
5. Living-memory write-back + hand the suite to the operator. **Stop.**

## 5. Risks

| Risk | Handling |
|---|---|
| Fourth-mechanism overlap in practice | The PRD's positioning section is a merge gate: named behavioral difference vs F3/D-067/F5 or no-ship |
| n too small for family-level inference | `negmem_min_evidence` floor + shrinkage; layer 2 v1 restricted to the stub feed (aggregate, not per-shape) |
| D-067 principle violated in spirit | Soft-only, clamped, floor knob, stamped, operator ruling requested before build |
| Privacy of modeling non-users | Decision 3 in scope §6 — operator rules; PRD presents options only |
| Taxonomy drift across three plans | Shared file v1.1.0 with PRODUCER column; semver change rule already agreed |
