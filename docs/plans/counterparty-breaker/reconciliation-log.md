# Reconciliation log — Counterparty breaker doc suite

**Vehicle:** dual-agent-doc-review (Author/Feasibility lens A vs Adversary/Risk lens B, orchestrator-merged).
**Artifacts covered:** HLD.md · LLD.md · PRD.md (each its own loop; PLAN.md was single-authored and
reconciled with the two sibling sessions instead — see §Sibling reconciliation).
**Drafts and raw lens output:** `drafts/` (kept as the reasoning record, fit-challenger precedent).

---

## Sibling reconciliation (PLAN level, before the dual-agent loops)

Three concurrent planning sessions (Receipts · Negative-results memory · Counterparty breaker)
coordinated live over session messaging; all outcomes committed in `cd5cd64`:

- **Boundary ratified** (negmem session): memory = historical behavioral prior, breaker =
  deterministic present-state; coupling documented both sides, built in neither v1.
- **`shape_aversion` defect** (raised by negmem): my draft's definition mixed behavioral language
  with present-state math. Resolution: breaker keeps ONE extension code (`roster_crunch`,
  broadened); `shape_aversion` enters the shared taxonomy as `producer=negmem`; the taxonomy's
  vocabulary section gains a **producer column** so the boundary is enforced mechanically.
- **F-1** (raised by Receipts, verified independently): NO client renders `TradeCard.narrative`
  (arm-B audit + fresh grep) — the "zero client change" narrative option ships an invisible
  feature. Default flipped to a distinct card element (Chalkline + structural guard + testIDs +
  TestFlight).
- **F-2** (Receipts): mirrored-card calibration cut is starved (96.3% of 1-for-1s one-directional)
  — viewer-seat shadow promoted to primary calibration population.
- **F-3** (Receipts): clone-board hazard (5 of 6 boards in the one boarded league ~uniform row
  counts) — authenticity heuristic added, board-based severity confidence discounted.
- **A-1 closed** (Receipts, prod `model_config_changes` read): interleaved serving live
  2026-08-21T00:43:34Z; ghosts end at that boundary; QB repricing knobs moved 04:46Z
  (comparability note added).
- **Taxonomy:** seed v1.0.0 signed off by this session; objection vocabulary lands as the v1.1.0
  minor bump (`roster_crunch` producer=breaker, `shape_aversion` producer=negmem).
- **Prior art:** `trade_gen_v2.acceptance_prior` cited as an UNFED STUB (returns 0.5 uniformly;
  no caller passes `acceptance_stats`) per the negmem research memo; memo §2 cited wholesale for
  existing rejection-consumers.

---

## HLD loop

**Rounds run:** 3 (parallel independent drafts → orchestrator merge → cross-review → revision).

### Round 1 — independent drafts
- **A (coherence)** pinned the seam mechanics: post-ranking evaluation module, per-partner
  context cache, uniform-keys stamp, additive serialization, `trade_gen_fit` never imported,
  fail-open with self-surfacing nulls.
- **B (risk)** contributed the safety architecture: narrative evidence whitelist (public-observable
  only), per-class maturity ladder, single composition owner, severity haircut by outlook
  provenance, anti-wallpaper controls, budget ladder with labeled missingness, degrade-and-mark
  table for wrong-counterparty-state inputs, seam-creep inertness guard.

### Round 2 — orchestrator merge (rulings M-1…M-8)
Key rulings: A's skeleton + B's risk rows as first-class design; **corrections for two
stale-vs-PLAN items** (shape_aversion removed entirely; narrative is a distinct element in the
`breaker` payload — no string-append, `build_narrative` untouched); served-deck-only stamp scope;
`them` = fit_diag passthrough (null on organic decks — no rescoring, taxonomy §2.8); narrative
flip timing vs the live bake-off window → operator register.

### Round 3 — cross-review (both lenses, candidate v1) → revision
**A raised (2 blocking):**
- **The seam claim was false** — the served deck is not fixed after the M3 stamp site; five
  mutation layers (incl. likes-you INJECTION of new cards) run before impression logging, so
  likes-you cards would log with silently-null stamps (unlabeled missingness on a
  calibration-relevant population). → Seam redefined: post-mutation-stack (post-F9,
  pre-ghost-split), the exact list feeding `_log_deck_signal_impressions`; invariant test added.
- **Maturity-ladder launch circularity** — no eligibility representation; first light could
  render nothing while graduation required a TestFlight pass. → Explicit sequencing + eligibility
  mechanism (see B's sharper variant below).

**B raised (5 blocking):**
- **Privacy regression in the merge:** declared `team_outlook` is private per-user state; the
  merged whitelist routed declared-window narration at the normal bar — re-opening the doc's own
  Critical R-1. → Narration derives from public state alone; a declaration may only raise
  confidence when the public-inferred window agrees; operator register row for ever accepting
  disclosure.
- **Silently dropped risk row** in the count-preserving renumber (cross-seat story mismatch —
  live the day the narrative flag lights, not latent). → Restored as its own High row; R-12 split.
- **Degradation ladder contradicted its labeled-missingness rule** (bare nulls carry no reason);
  coverage gate undefined over degraded stamps. → Marker objects always; coverage = scored-vector
  share (rungs 0–2); degraded-share criterion added; two-pass evaluation kills rank-correlated
  within-class truncation.
- **Shadow-run data path unbuildable as written** (would overwrite the stamp or leak to clients).
  → `card.breaker_shadow` → `features_json.breaker_shadow`, never serialized; guard test named.
- **"Preregistered baselines" not preregisterable** (no stratification vars, margin semantics,
  artifact, or deadline). → Calibration-readout spec committed BEFORE `trade.breaker` first
  lights; stratification ≥ `outlook_src` × board basis; margins over both baselines.

**Convergent tension adjudications (both lenses independently agreed):** `breaker_shadow` sibling
key over a seat field · split `ver`/`tmpl_ver` versioning · 250ms default pending W0-style dry
run · coherence test as characterization with breaker-side-only threshold adjustments · card
layout scoped to the PRD. **Where they differed:** eligibility mechanism — A proposed overloading
per-class floors; B showed floors double as top-selection shape and would distort the stamp
distribution; B's separate `breaker_narrate_<class>` switches adopted.

**Accepted non-blocking:** ten (not nine) layer-2 codes with `other_text` excluded-by-construction
from calibration denominators; stamp line outside the `bakeoff_run` guard; composition owned by
`trade_breaker.compose_narration`; one severity code path for `value_giving` across deck types;
exposure predicate = `narrated != null AND platform = mobile`, three-cell readout; scope.md
executemany citation errata (`database.py:5427` → `:5503`).

### Unresolved disagreements (HLD)
None left blocking after round 3 — round-4 sign-off run confirms (see below).

---

## LLD loop

*(appended after the LLD rounds)*

---

## PRD loop

*(appended after the PRD rounds)*
