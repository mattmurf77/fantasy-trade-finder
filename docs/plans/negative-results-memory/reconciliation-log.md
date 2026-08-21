# Reconciliation log — Negative-results memory PRD

**Document type:** PRD **Rounds run:** 4 (the cap) **Converged:** yes — dual sign-off in round 4
**Process:** dual-agent-doc-review — Agent A (Product/User lens), Agent B
(Engineering/Feasibility adversary), independent round-1 drafts
([PRD-draft-A.md](PRD-draft-A.md), [PRD-draft-B.md](PRD-draft-B.md)), orchestrator
synthesis, two cross-review rounds, final verification round.

---

## Round 1 → synthesis (candidate v1)

Independent drafts diverged on four points; the synthesis ruled:
- **M1 key granularity:** B's cell arithmetic (990/297/33 at then-3-families) beat A's
  implicit full key — coarse key adopted; `shape_bucket` recorded-not-keyed.
- **`negmem_floor`:** B's 0.6 (no retest mechanic, unlike F3) over A's 0.5.
- **M2 expectations:** demoted per B (gen_v2 is a dark arm; correctness deliverable,
  no day-one user-impact claims) while keeping A's S4 verification metric.
- **RFPS as promotion decider:** middle position — A's target retained, B's
  report-not-gate concern answered with pre-registration + hold/extend (contested into
  rounds 2–3; resolved round 3).
Convergent from both drafts: privacy recommendation (c) aggregate-only derive-on-read;
D-067 soft-family recommendation; merge-gate positioning with B's honesty column.

## Round 2 (candidate v1 → v2): 9 blocking objections, all applied

**A raised (2):**
1. §2.4 labeled "verbatim" but paraphrased → restored exact README quotes, commentary
   moved outside quotes, namespace reservation restored.
2. Evidence admission lost two rules from the parent drafts → retraction/undo exclusion
   restored; `other`-family disposition made explicit.

**B raised (7):**
1. `reason_family` set undefined; `trade_matches` declines contradicted R2 → admitted
   set enumerated {value, fit}; declines moved to M2-only; `other_player_*` excluded
   with rationale; cell table reconciled to 22.
2. R1 admission criteria scattered/incomplete → rebuilt as a closed 5-clause list.
3. Like-netting cell-targeting unspecified → nets against every (P, ✱) cell; magnitude
   and decrement-vs-reset delegated to LLD.
4. `regime_tag` had no source or consumer → replaced by R11 context tags read from
   serve-time-frozen card state, recorded-not-consulted in v1.
5. M2 gating contradicted C1 → M2 flag-gated under `trade.negmem`; C1 scoped to cover
   arm C via kwarg-absent-when-off.
6. Promotion rule ambiguous → §8.3 exact multi-branch rule (B's conditional acceptance
   of RFPS-as-decider was predicated on this fix).
7. §2.1 statistic fabricated ("40–280 decisions/week") → replaced with sourced figures.

Non-blocking folded in: source columns on metric tables; GR4 joint-multiplier
compounding tripwire (raised independently by both lenses); D1 no-consequence stated
in-place; R5 lookback-in-query note; NG9 (no neighboring-mechanism edits); dangling
DH-1 reference fixed; R6 upsert caveat; P2 shape-key gate restated as an achievable
count threshold; per-league flag mechanism named; S4 expected-null annotation; RFPS
id-mapping note; ~120 rows/week labeled a derived estimate.

## Round 3 (candidate v2 → v3): A signed off; B found 2 of the fixes wrong as implemented

- **B-blocking 1:** R11 claimed `trade_intent` is a `features_json` key — it is a
  `deck_impressions` COLUMN, stamped only on bake-off-attributed rows → R11 rewritten
  with correct sourcing and expected-NULL annotation.
- **B-blocking 2:** §2.1 "single-tester peaks around 200 in 4 days" misquoted the
  source (~200 across 4 days **from 5 users**) → corrected verbatim.
- A's suggestions applied: ellipsis removed from the breaker quote (over-claimed an
  omission); session id restored to `-31`; RFPS numerator rule for reason-less
  rejections pre-registered; R6 purity extended to netting-event timestamps.
- B's suggestions applied: §8.3 explicit Shelve-on-worsening branch; R1(d)
  join-path/asymmetric-retraction LLD note; §7 dependency flags (taxonomy must land on
  main; v1.1.0 authorship reconcile owed at three-way sign-off).

## Round 4 (candidate v3 → FINAL): dual sign-off

- A: yes — all four round-3 items verified landed; B's edits verified non-damaging.
- B: yes — both round-3 fixes re-verified against code (`server.py:4140/:4159/:4277`,
  `database.py:607`, `bakeoff_runner.py:1021-1027`); §8.3 verified total and
  unambiguous; no new contradictions.
- Cosmetic nits applied at finalization: G3 parenthetical aligned with R6's domain;
  R11 NULL-semantics precision (NULL also on intent-less bake-off arms); §2.1
  "is budgeted at"; §8.3 max-extension review trigger (2× planned window).

## Unresolved disagreements

None — both lenses signed off. Two items are *deliberately deferred to named owners*
rather than unresolved: like-netting magnitude/mechanism (LLD), and shared-taxonomy
v1.1.0 authorship (three-way reconciliation).
