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
- **Operator ruling relayed batch-wide (2026-08-21): NO ghost cards, full stop.**
  `ghost_holdout_one_in` = 0 in prod, made durable in Receipts' next ship. Breaker impact:
  none material — every measurement design was served-cards-only already; the HLD's
  ghost-stamp robustness clause reworded to a non-dependency, and the ruling recorded as
  binding in PLAN §7 and HLD §2.3.

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

### Round 4 — sign-off run
- **A: SIGN-OFF yes.** All round-2 blockers verified resolved against re-checked `server.py`
  citations; three non-blocking wording items (coverage covered-iff-scored, ghost-stamp
  acknowledgment, one line-cite drift) — all folded.
- **B: one NEW blocker found in the sign-off check, then resolved and diff-verified:** §3.6
  served the top objection `{code, severity}` to the client whenever `trade.breaker` was on —
  ungated by class privacy and live during the dark-stamp window, shipping private-state-derived
  codes as structured data to the negotiation adversary (the copy whitelist governed prose only).
  Fix: the payload is **narration-gated** — the dark window serves no `breaker` key; serialization
  restricted by construction to graduated, whitelist-clean, above-floor classes; payload guard
  test added. B's non-blocking refinements also folded: no-getattr-default stamp sketch, shadow
  marker discipline (incl. rung-5), board-basis `value_giving` narration-ineligible outright,
  named R-6 monitor. **B re-verified the diff: SIGN-OFF yes.**

### Post-convergence constraint fold
The batch-wide operator no-ghost ruling arrived after B's verify; the ghost-stamp clause was
reworded to a non-dependency and the ruling recorded as binding (PLAN §7, HLD §2.3). No
measurement design changed — all were served-cards-only.

### Unresolved disagreements (HLD)
None — both lenses signed off (A round 4; B round 4 + diff re-verify).

---

## LLD loop

### Round 1 — independent drafts
- **A (implementer)** delivered the full implementable surface: verbatim seam block, payload/
  marker schemas, per-class predicate math with severity formulas from existing helpers,
  25-knob table with the five-registration checklist, mobile element + testIDs, complete test
  plan, calibration-readout skeleton. Contestable calls it flagged: `fit_outlook` on the
  unweighted shared lean scalar (provable coherence over value-weighting); co-owner union
  unimplementable at the seam (owner-id-only + `identity_src` marker); seam-owned republish;
  split `value_giving` floors by basis; atomic pass-2 discard; pinned (not knobbed) severity
  curve constants.
- **B (reviewer)** verified the hazards: **all eight snapshot publish sites are conditional —
  with `deck.signal_v2` off there is NO post-mutation publish**, so narrated sentences would
  ship dark without a breaker-owned republish (the HLD's deferred republish question, answered
  with a contract + flag-matrix test); the HLD §3.3 no-default impression copy **crashes a
  whole deck's impressions on a mid-job flag flip** (no per-row try/except in
  `_log_deck_signal_impressions`); cost basis is **60 cards** (`bakeoff_deck_limit` 30→60 at
  the A-1 boundary), not 30; partner `asset_preferences`/declared outlooks are NOT loaded by
  the job (two bulk readers needed); stud-tax thread-local unpinned at the seam; hot
  `reload_config` mid-job breaks intra-deck determinism (per-job knob snapshot); argmax
  tie-break unspecified; small fixtures test the wrong tier mode (`_POS_TIER_MIN_POOL=40`,
  the #366 lesson).

### Round 2 — orchestrator merge (rulings M-1…M-12)
B's safety findings win where they conflict with A and with the HLD's literal text: attribute-
gated impression copy with a synthetic `flag_flip_or_unstamped` marker (never bare null, never
a crash — invariant lives in tests); 60-card cost basis; bulk readers; per-job knob snapshot;
`stud_tax_override("market")` pinned with rationale. A's surface stands elsewhere (25 knobs,
co-owner degrade-and-mark, atomic pass-2 discard, pinned curve constants). Three **HLD errata**
recorded for post-convergence amendment (impression-copy sketch, cost claim, "already loaded"
data claim). `fit_outlook` scalar choice left flagged for cross-review adjudication.

### Round 3 — cross-review (both lenses on candidate v1)

**Raised by BOTH lenses (independent convergence — the strongest signal in the whole loop):**
- §3.10's fit_outlook cell excluded picks from the lean mean, contradicting the §3.3
  byte-parallel definition (picks ride at −0.25 via `_now_lean`'s PICK short-circuit) and
  making the parity test and the "contender receiving picks fires" row unsatisfiable —
  merge-introduced, fixed by restoring pick inclusion.
- `cfg["waiver_slot_cost"]` KeyError under the frozen knob snapshot (engine knob, not among
  the 25 registered breaker keys) — fixed via `_SHARED_ENGINE_KNOB_KEYS` union.
- The Monday `fix/package-benchmark-sweetener` ship was absent from the LLD: §3.4 now reads as
  post-fix semantics with the dead-in-'market'-mode params annotated; §8 gains the Monday
  merge as a NAMED code-ship boundary (invisible to `model_config_changes` — the M1 rail
  cannot censor it) plus the 11:48Z QB seam and the sweetened-key cut; sequencing vs the
  golden re-capture pinned.
- E-14's per-class containment narrowing promoted to declared HLD erratum E-D (the errata
  registry claimed exactly three; silent narrowing would have left the HLD misleading).

**Lens B additionally:** the §1.2 rung-5 failure handler itself crashed — it called
`trade_service._c(...)` where `trade_service` is the per-format **instance** (no `_c`), a live
knob read inside the one path that must never fail; fixed to stamp both markers
unconditionally with no knob read. And predicate crashes stamped an unattributable
`not_applicable` — now a durable `predicate_error` skip mark counted in degraded share.

**Adjudications (both lenses agreed):** M-8 CONFIRMED — unweighted `_give_side_now_lean`,
conditional on the picks fix; the provable XOR coherence with `_opponent_frame` outweighs
value-weighting, and the failure mode under-fires (a missed hesitation, never a wrong
sentence). T-2 BreakerReport raises-nothing posture confirmed; T-4 evidence enums confirmed
with `tier_basis` restored; T-5 3dp confirmed.

**T-1 split, orchestrator-ruled:** A wanted the demo skip required; B called it a product
question. Ruling: both skips ship in v1 (`league_demo` for consistency with every neighboring
layer; `_job_superseded` as cheap compute avoidance); the "narrate on demo decks as demo
material" option is recorded as a PRD open question — a deliberate product lift, not a default.

### Round 4 — revision + sign-off
All six blocking fixes, the T-1 ruling, and ten accepted refinements applied (one honest
deviation: the literal "min_severity ≥ every floor" test pin would be FALSE at shipped
defaults — 0.75 consensus floor > 0.60 bar — so the test pins the effective `max()` ordering
with the consensus floor excepted). **Both lenses verified the revision against the diff and
live code and signed off:**
- **A: yes** — picks-in-mean cell now byte-provable against `_now_lean`; snapshot union
  contradiction-free; Monday-delta text matches the `package_value_v2` docstring verbatim;
  E-D declared. Accepted the test-pin deviation as "the honest testable half".
- **B: yes** — rung-5 handler now constructible with zero breaker state (the removed
  `trade_service._c` call would itself have raised: the local is the per-format instance,
  `_c` is module-level); `predicate_error` durably visible in the §8 arithmetic; all six
  non-blocking items landed; the T-1/Q-10 closure records B's position accurately.

Sign-off-round polish (four non-blocking items, applied post-convergence): the
`is_pick_asset(players.get(p))` sketch fix (called on a pid, takes a player object — B);
rung-5 decorrelation acceptance note (B); honesty note extended to engine-internal KNOB reads
(`package_discount_cap`/`elo_value_*` read live inside `ts` helpers — A); card-side pick shape
clause (`position == "PICK"`; generic-pool `team == "PICK"` picks don't reach the seam — A).

### Unresolved disagreements (LLD)
None — both lenses signed off. M-8 (`fit_outlook` scalar) was confirmed by both with the same
reasoning: provable XOR coherence with `_opponent_frame` beats value-weighting, and the
failure mode under-fires (a missed hesitation, never a wrong sentence). A value-weighted
variant is a v2 conversation gated on a replacement coherence proof.

---

## PRD loop

### Round 1 — independent drafts
- **A (product)**: evidence-grounded problem framing, 20 traced R-rows, five user stories
  (incl. counterparty protection), 13-row observable-states table, worked copy per class with
  six binding tone rules, 12-step TestFlight checklist, 17-item consolidated register.
  Contestable calls flagged: v2 seam (a) recommended; first graduated class =
  `fit_new_weakness` (safety-first); user-invisible suppression; fixed lead-in label;
  deck-level like-rate guardrail.
- **B (feasibility)**: expected-n table with KEEP/DEMOTE/KILL verdicts — counterparty-seat
  calibration (n≈0–2/month at the 3.7% mirror rate) and like→propose (funnel fired zero times
  ever) DEMOTED to counted-never-gated; graduation realism (only `fit_outlook` + consensus
  `value_giving` reach min-n inside v1; `roster_crunch` has no filed-reason anchor —
  reported-never-gated by plan); FR-3.x undefined-user-states block (absence-is-silence: no
  "no red flags" variant); 14-step checklist; 15-item scope-tripwire list; 18-item register.

### Round 2 — orchestrator merge (rulings M-1…M-10)
B's metric honesty and states-block adopted wholesale; A's voice, copy, and guardrail
rationale kept. The one direct A/B conflict — first graduated class — resolved by B's
realism data: the mechanism stays evidence-bars-per-class, default = first class to clear its
preregistered bar, with A's safety argument and B's throughput argument both recorded in the
register item. Both drafts independently recommended v2 seam (a) and keeping the demo skip —
adopted. Registers consolidated into one table.

*(cross-review and sign-off appended below)*

---

## Errata

### Errata E-1 (2026-08-21) — shared taxonomy landed as v1.1.1

Taxonomy **v1.1.1 landed at commit `5572604` on `plan/receipts` (three-way signed)**,
superseding all pending-v1.1.0-PR language in this suite (PLAN §8 taxonomy bullet, PLAN §9
items 7a/7b, HLD §5.7). The breaker build **cherry-picks the seed + taxonomy through
`5572604` at landing**. The shared file (`docs/plans/shared/trade-shape-taxonomy.md`) is not
present in this worktree — it lives on the sibling branch until the cherry-pick. Stale spots
carry one-line bracketed pointers to this entry; no body rewrites, no renumbering. Register
items 7a/7b status: landed, three-way signed; operator ratifies with PRD approval.
