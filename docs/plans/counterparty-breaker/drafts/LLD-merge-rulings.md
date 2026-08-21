# LLD merge rulings (orchestrator, FINAL) — execute to produce LLD.md

> The dual-agent LLD loop stopped mid-merge on a session usage limit (2026-08-21). Drafts A and
> B are complete in this directory. These rulings are the orchestrator's final adjudication of
> every A/B conflict — the next session executes them to write `../LLD.md` (A's draft is the
> skeleton; B's edge-case/error/concurrency material merges as first-class sections), then runs
> the cross-review round (both lenses on the candidate), then sign-off. Verify every carried
> line number against the checkout.

- **M-1. Seam + republish:** A's verbatim seam block (after F9 end `server.py:6029`, before
  `served_final` `:6034`) + the converged republish contract: the breaker block republishes iff
  `narrated_count > 0` (`_job_live`-guarded, standard decoration, `_served_cards` path per B
  §2.3); the conditional `:6115` signal_v2 republish re-serializes and preserves it when on.
  Include B's T-13 flag-matrix test (sentence reaches the final payload under every
  `deck.signal_v2` × streaming × breaker-flag combination).
- **M-2. Impression copy:** B wins over A and over the HLD's literal text — ATTRIBUTE-GATED
  copy with synthetic degradation-marker fallback `{ver: null, degraded:
  "flag_flip_or_unstamped", objections: null}` when the flag reads on at log time but a card
  lacks the attribute (mid-job hot-reload flip, injected-card race). Never a bare null, never a
  crash (no per-row try/except in `_log_deck_signal_impressions` `:4122-4233`). Never-bare-null
  invariant lives in tests (B's T-10). Record as **HLD §3.3 ERRATUM** in LLD §1 errata list.
- **M-3. Cost basis 60 cards** (`bakeoff_deck_limit` 30→60 at the A-1 boundary) for all ms
  budgets, checkpoint math, dry-run contract. Second **HLD erratum** (§5.4 cost claim).
- **M-4. Data loading:** B's two bulk readers (partner `asset_preferences`, declared
  `league_preferences`) — read-only helpers, batch per league, no schema change;
  `PartnerContext` uses them. Third **HLD erratum** ("job already loaded" claim).
- **M-5. Knobs:** A's 25-knob table stands (incl. 7 floors — `value_giving` split by basis per
  D-7) PLUS B's per-job knob snapshot (knobs read once per `stamp_breaker` call; hot
  `reload_config` mid-job cannot split a deck) and B's verified note that
  `_cfg_override`/arm profiles are exited at the seam. Stud-tax pinned explicitly via
  `stud_tax_override("market")` around breaker value calls, stamped in provenance; rationale
  (partner's mode unknowable; determinism wins) recorded as a design decision.
- **M-6. Determinism:** B's argmax tie-break class-priority constant (pinned under `ver`); A's
  version-pinned (not knobbed) severity-curve constants.
- **M-7. Degenerate contracts:** B's per-class degenerate-input table (all-picks sides, empty
  roster, missing LeagueMember, K/DEF/IDP zero-values, partner==user guard, formats) merges
  into Core Logic/Edge Cases; A's co-owner ruling stands (owner-id-only + `identity_src`
  marker; raw co_owners unavailable at the seam `server.py:16972-16975`) — satisfies HLD §3.4
  degrade-and-mark; union variant an explicit non-goal pending a data-path change.
- **M-8. `fit_outlook` scalar:** A's unweighted `_give_side_now_lean` stands (provable XOR
  coherence with `_opponent_frame` on one shared scalar); ignored-value-weighting tradeoff
  documented inline; **flagged for cross-review adjudication (NOT settled).**
- **M-9. Two-pass budget:** A's algorithm + B's atomic pass-2 discard on mid-pass exhaustion
  (deck-uniform missingness).
- **M-10. Fixtures:** B's realism preconditions are part of the test-plan spec — every
  depth/tier predicate test asserts `tier_basis == "positional"` on a ≥40-per-position fixture
  (the #366 lesson); name the shared fixture module.
- **M-11. Test plan:** union of both drafts' lists (A has every HLD-named test; B adds
  T-10/T-13 and edge-case rows); dedupe by name; names are the spec.
- **M-12. No ghosts anywhere** (operator ruling). A's calibration-readout skeleton stands with
  TBD-operator cells.

**After LLD convergence:** apply the three HLD errata (M-2/M-3/M-4) to HLD.md; then the PRD
loop (references/prd.md lenses; PRD weighs the two product outcomes, owns the TestFlight
checklist, decision register consolidation, and copy/tone); then taxonomy 1.1.0
objection-vocabulary section authoring (producer column; roster_crunch=breaker,
shape_aversion=negmem); then final three-way sibling reconciliation (Receipts session runs the
batch check) and operator delivery.
