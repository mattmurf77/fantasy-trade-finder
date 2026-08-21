# PLAN — Counterparty breaker

**Date:** 2026-08-21 · **Status:** DRAFT for three-way sibling reconciliation, then operator review.
**Branch:** `claude/counterparty-breaker-plan` (docs only — planning stops before any build).
**Doc order (later binds tighter):** this PLAN → HLD → LLD → PRD. Scope block: [scope.md](scope.md).
**Siblings (one operator batch, three plans):** Receipts (`plan/receipts`, retrospective suggestion
re-scoring + track record) · Negative-results memory (`negmem_`, historical rejection prior) · this.

---

## 0. Origin and operator brief

From the operator's product-gap review of outside material. Two borrowed ideas, translated:

- **The breaker agent** (self-improving trading loops): a separate pass whose only job is to find
  the conditions where a strategy dies — run it against the worst case, not the average case.
  Translated: before a trade card ships, find the strongest reason the OTHER manager kills it.
- **The checker node** (graph engineering): a validation node between parallel producers and the
  synthesis step, so bad outputs don't poison downstream. Translated: an evaluation layer between
  the generator arms and presentment/serving.

Operator constraints as assigned: full gates, not express; planning only (plan + HLD + LLD + PRD
via dual-agent review); deterministic v1 — any LLM involvement is an explicit operator decision,
never an assumption; do not overturn fit-challenger operator rulings; coordinate with both sibling
sessions — one taxonomy, non-overlapping tables, agreed seams.

## 1. Problem

The engine argues exactly one side. The arm-B audit measured it: **96.3% of 1-for-1 cards exist in
only one direction**, 84.5% of served cards never consult a partner board, and on the consensus
path the viewer receives more than they give on 86.3% of cards
([docs/reviews/2026-08-19-armb-audit-consolidated.md](../../reviews/2026-08-19-armb-audit-consolidated.md)).
Meanwhile `deck_outcomes.action = 'propose'` has fired **zero times ever** — no suggested trade has
been sent through the app ([trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md) §G1).

What exists today on the "their side" question:

- The **fit arm** (`backend/trade_gen_fit.py`, dark) scores both seats 0–100 and stamps
  `fit_diag` (including the them-lens breakdown) on every bake-off card — but it produces a
  *number*, not a *named reason*, and nothing user-facing consumes it.
- **`trade_gen_v2.acceptance_prior`** (`backend/trade_gen_v2.py:283`, dark) shrinks toward a
  per-manager historical accept rate — a scalar propensity with no reason and no present-state
  awareness (its own docstring expects a learned model to replace it).
- **G6 R5** (`need_gate_ok`) asks whether the *user* needs what they receive; nobody asks whether
  the *counterparty* needs what they'd receive.

So a card can clear every live gate while being an obvious "no" from the other seat — the
counterparty is rebuilding and the card sends them a 29-year-old; the card takes their only
startable TE; the package asks them to consolidate when their roster can't absorb the roster-spot
loss. The user proposes (or more realistically, never does), nothing lands, and the app's
suggestions read as a calculator, not a scout.

## 2. Concept

A deterministic evaluator — working name `backend/trade_breaker.py` — that takes a candidate card
plus the counterparty's present state (roster, board if any, inferred/declared window, depth chart,
league settings) and returns a ranked objection list:

```
breaker = {
  "ver": BREAKER_VERSION,
  "top": {"code": "fit_outlook", "severity": 0.82, "evidence": {...}},
  "objections": [ {code, severity, evidence}, ... ],   # all classes evaluated, scored
  "ms": 4.1
}
```

**The organizing idea: the breaker predicts the counterparty's decline reason.** Objection codes
are not a new vocabulary — they anchor on the SHIPPED `trade_pass_reasons` layer-1/layer-2 codes
(`value_giving | value_getting | value_other | fit_outlook | fit_new_weakness | fit_duplicate |
fit_other | other_player_keep | other_player_avoid`, `backend/database.py:5580-5582`), extended
only where those codes lack a needed concept (one candidate: `roster_crunch`) via the shared
taxonomy file. **Boundary enforcement (reconciled 2026-08-21):** `shape_aversion` — a manager's
*learned* resistance to a package shape — is a real concept but belongs to negative-results
memory (behavioral/historical, its layer); the shared taxonomy's vocabulary section gains a
**producer column** (`producer: breaker | negmem`), and any code with `producer=negmem`
appearing in a breaker output is a reviewable defect. The breaker may cite shape-aversion only
via the future memory→breaker coupling. This buys three things at once:

1. **Falsifiability.** When the counterparty is also an FTF user and later passes on the mirrored
   card, their filed pass reason either matches the breaker's prediction or it doesn't — direct
   calibration, no new instrumentation (~200+ coded rows exist already).
2. **Sibling coherence.** Negative-results memory stores *historical* rejections coded in the same
   vocabulary; the breaker predicts *present-state* rejections in it. One vocabulary, two tenses.
3. **Narrative honesty.** Every card sentence traces to a coded objection with evidence, in the
   D-053 tradition — the copy can never claim a hesitation the analysis didn't produce.

Objection classes for v1 (each a deterministic predicate over present state, detailed in the LLD):

| Code (anchored/extended) | The counterparty's case |
|---|---|
| `fit_outlook` | card pushes against their window (rebuilder asked to take aging vets; contender asked to take picks/prospects) — mirrors `outlook_alpha`/`infer_team_outlook` from their seat |
| `fit_new_weakness` | card opens a starting hole they can't fill (mirrored R5/lineup-feasibility, their seat) |
| `fit_duplicate` | card stacks a position they're already deep at (their `position_surplus`) |
| `value_giving` | from their seat they overpay on their own board (if boarded) or vs consensus optics (unboarded) — reuses the fit arm's them-lens inputs, raw boards only |
| `other_player_keep` | card asks for their pinned/untouchable/franchise-tagged player (asset_preferences, their side) |
| `roster_crunch` (ext.) | accepting is structurally costly from their seat: forced drop of a player they demonstrably value, lineup slot math (`waiver_slot_cost` from their seat), positional pile-up from a consolidation ask |

Severity is 0–1 per class from the underlying margins (not a new value model — reuses existing
quantities: their-board deltas, `position_needs`/`position_surplus`, `infer_team_outlook` score
margins, lineup-feasibility results). `top` = argmax severity above a per-class floor.

## 3. The two product outcomes — and the v1/v2 split the bake-off forces

The assignment names two outcomes. They have very different blast radii, and tonight's serving
change decides the split:

**Interleave discipline (binding constraint).** Interleaved bake-off serving is live (arms
`current`/`challenger`/`gen_v2` with per-card `model_arm` attribution — sibling-reported, verify
at build: Assumption A-1). The standing rule (matchmaking HANDOVER trap 5, enforced by
`bakeoff_runner.bypass_rerankers`) is that nothing may reorder or filter the interleaver's output,
or the bake-off measures deck position instead of model quality. A post-generation filter/demote
is exactly that class.

Therefore:

- **v1 — evaluate + stamp + narrate. Zero ordering effect.**
  - `trade.breaker` (dark): compute objections post-ranking, stamp on the card and into
    `features_json.breaker` (uniform keys on every row — executemany trap, `database.py:5427`),
    on organic AND bake-off decks. Pure measurement; deck order byte-identical.
  - `trade.breaker_narrative`: the top objection above `breaker_min_severity` renders as one
    deterministic sentence on the card — *"Their likely hesitation: they're rebuilding, and this
    sends them a 29-year-old RB."* Composed in `trade_narrative.py` templates (no LLM — operator
    decision required to ever change that). Turns the card from calculator into scout and tells
    the user what to preempt in their pitch. No reordering, no filtering — bake-off-safe by
    construction.
- **v2 — filter/demote (own scope block, operator election later).** Options the PRD will weigh
  but NOT commit: (a) run per-arm INSIDE generation before the draft (each arm's list is breaker-
  screened, interleaver untouched — clean but touches every generator); (b) serving-layer demote
  that is bypassed on interleaved decks like every other re-ranker (honest but means the bake-off
  never measures it); (c) stay stamp-only and let the *user* filter (sort/badge by objection).
  Bright line: v2 changes deck composition → new scope block, own evidence, own TestFlight pass.

This split also honors D-067's principle (*accuracy, not volume*) without pre-empting the
measurement: before the breaker is allowed to kill cards, the stamp data will show whether
high-severity-objection cards actually underperform (pass rate, pass-reason match) — the
filter earns its existence from the calibration readout, or it doesn't ship.

## 4. Prior-art positioning (the overlap the operator will probe)

| Mechanism | What it is | Why the breaker is not it |
|---|---|---|
| Fit arm them-score (`trade_gen_fit`, D-098) | 0–100 "how much they should like it," three lenses, fit-arm candidates ranked by aggregate; `fit_diag` stamped on every bake-off card | A magnitude, not a reason. The breaker names the objection CLASS with evidence, covers non-value objections (shape, crunch, untouchables), runs on EVERY arm's cards including organic decks, and feeds user-facing copy. Where the them-lens already computes the needed quantity, the breaker READS the stamp rather than rescoring (LLD hook; Receipts contract cites this adjacency) |
| `trade_gen_v2.acceptance_prior` (`trade_gen_v2.py:283-308`, multiplied into every gen_v2 score at `:655`) | EB-shrunk per-manager historical accept-rate multiplier — **an unfed stub today**: no caller passes `acceptance_stats`, so it returns 0.5 uniformly (memo: `docs/plans/negative-results-memory/research-verification.md`, vigilant-spence branch) | Scalar propensity, historical, reasonless — and unfed (negmem IS the planned feed). Breaker is present-state, per-card, reasoned. Memo §2 also catalogs every existing rejection-consumer (F3 fatigue, D-067 cooldown, F5 taste incl. `partner:{user_id}`) — cited wholesale rather than re-derived |
| Negative-results memory (sibling, planning) | Historical behavioral prior: rejections recorded per league-mate/shape/reason, regime-tagged at rejection time, consulted at GENERATION time | Different tense, agreed boundary (recorded in their README): memory = history, breaker = present state. Future coupling (neither v1): memory confirms/weights breaker objections; breaker answers "does this objection still apply today" for memory |
| Receipts (sibling, planning) | Retrospective: re-scores PAST suggestions against subsequent value movement; user-facing track record | Backward-looking accuracy accounting vs. forward-looking pre-serve evaluation. Shared: taxonomy + measurement vocabulary only |
| `taste_service` (F5, live) | Viewer-side learned preference vectors from swipes/board (has `partner:{user_id}` attr — learns the VIEWER's taste about a partner) | Learns the viewer, from the viewer's behavior. Breaker reasons about the COUNTERPARTY from their state, no learning in v1 |
| Deck fatigue / `deck_suppressions` (F3, D-067) | User-side repetition memory and hard dismiss windows | Suppresses what the viewer already rejected; breaker anticipates what the partner would reject |
| G6 presentment rules (D-062, live) | Construction-quality kill rules from the USER's seat (R1 overpay, R2 balance, R3 pick-gap, R5 need) | Same layer of the pipeline, opposite seat. The LLD will reuse G6's predicate SHAPES (e.g. mirrored R5) without touching G6 itself; v1 breaker KILLS nothing |

## 5. What the breaker reads (all existing, no new ingestion)

Counterparty roster + `LeagueMember.elo_ratings` (board, when ranked — raw, never shrunk: the
fit-challenger provenance rule binds here too) · `analyze_roster_strengths` outputs
(`position_needs`/`position_surplus`, position-tier bins) · `infer_team_outlook` (and, when
`trade.outlook_composite` graduates, the composite — the breaker inherits whichever the engine
serves; INV-372b means legacy today) · declared `league_preferences` outlooks + asset_preferences
(untouchable/target/not-interested, their side) · lineup feasibility (`trade_optimizer`
`_feasible_after` shape) · Sleeper depth chart (`depth_chart_order`, live since #366) ·
league format/starter slots. Explicitly NOT read in v1: any LLM, any new external feed,
`negmem_*` tables (future coupling), ghost/counterfactual rows.

**Data-quality caveat (F-3, reconciled):** `LeagueMember.elo_ratings` authenticity is suspect in
places — prod boards for 5 of 6 members of the one boarded league are near-uniform ~644-646 rows,
likely bulk-seeded (trade-engine-accuracy PLAN appendix). An objection inferred from a
consensus-clone board just re-derives consensus while claiming to speak for the manager. The LLD
includes a cheap authenticity heuristic (board-vs-seed divergence count) that discounts
board-based severity confidence on clone boards; the them-board lens falls back to
consensus-optics with the confidence discount stamped.

## 6. Measurement plan

Stamp-first, exactly like the fit arm's M3 rail:

1. **Coverage & cost:** share of served cards stamped; `breaker.ms` p95 within `breaker_ms_budget`
   against the 60s job hard timeout.
2. **Calibration (the headline):** among passed cards where the pass reason was filed, does the
   filed layer-2 code match the breaker's predicted top objection *for the passing seat*? Two
   cuts, **weighted honestly:** (a) counterparty-seat validation where both managers use FTF and
   the mirrored card was served — expected-n is TINY on current data (96.3% of 1-for-1s exist in
   one orientation only; the both-ways fit arm would fix this but is not serving), so (a) is a
   long-run check, never the v1 verdict; (b) viewer-seat shadow (breaker run on the VIEWER's
   seat) is the **primary calibration population** — viewers file reasons today. Baseline
   exists: pass reasons are 40% `value_giving` / 33% `fit_outlook` (n=208).
3. **Lift (needs `trade.breaker_narrative` A/B):** like→propose conversion and pass-reason mix on
   cards WITH the hesitation line vs without. Honest note: `propose` base rate is zero all-time,
   so v1's realistic readout is like-rate + pass-reason shift + the G1 funnel gate
   (≥3 real sends) from trade-engine-accuracy/PLAN.md.
4. **Filter counterfactual (decides v2):** outcome delta between cards the breaker WOULD have
   killed (severity ≥ bar) and the rest, per arm — computed from stamps, no serving change.

**Data boundaries:** **operator ruling (2026-08-21, batch-wide, relayed via the coordination
channel): NO ghost cards, full stop** — `ghost_holdout_one_in` = 0 in prod since 00:43Z, made
durable in Receipts' next ship. Every §6 design above is served-cards-only by construction and
none uses ghost impressions, backward- or forward-looking; the historical `is_ghost=1` rows
(ended at the boundary) are excluded from every breaker readout. D-091 phantom-pick window
(2026-08-16→08-19) excluded from any baseline; `model_config_changes` timestamps censor
measurement windows (M1 rail, live since PR-M).

## 7. Rulings that bind this plan (not re-litigated)

Fit-challenger operator register (PRD-build §4) — all stand, incl. K1 widened, ms bar, serving
windows operator-owned · D-056 evidence regime (no Maestro; structural + code-walk + TestFlight) ·
D-053 narrative honesty · D-062/G6 stays user-seat and untouched · D-067 accuracy-over-volume ·
Chalkline for any UI (no new screen expected ⇒ no FeedbackFAB question in v1; revisit if the PRD
lands a tappable element) · one-engine-change-per-tester-week change control · five-registration
rule per knob · deterministic templates in `trade_narrative.py`, LLM = explicit operator decision ·
D-067's family-suppression ruling ("one swipe must not silence a player's whole trade space") —
does not bind v1 (the breaker evaluates, never suppresses), but binds any future v2 demotion
below visibility · **no ghost cards, full stop** (operator, 2026-08-21, batch-wide): no breaker
design or measurement may create or consume ghost impressions.

## 8. Reconciliation contract (three-plan batch)

- **One taxonomy:** `docs/plans/shared/trade-shape-taxonomy.md`, seeded by the Receipts session
  (first mover), adopted verbatim by all three plans; known-fixed dimensions: `shape_bucket`
  "NxM", `basis`, `lane`, `model_arm`, `involves_pick`, value bands, fit buckets. **This plan
  contributes the objection-vocabulary section**: `trade_pass_reasons` codes as the anchor set +
  breaker extension `roster_crunch`, plus the **producer column** (`breaker | negmem`) that
  mechanically enforces the present-state/historical boundary (`shape_aversion` lands with
  `producer=negmem`) — per the negmem session's hard constraint, extensions extend the shipped
  taxonomy, never parallel it. Changes only by PR touching the shared file (targets v1.1.0
  minor bump, three-way signed).
- **Table ownership:** `receipts_` (Receipts) · `negmem_` (memory) · `breaker_` (this, reserved,
  UNUSED in v1).
- **Seams, disjoint by construction:** negmem = generation-time prior (inside candidate
  scoring/pruning, before presentment) · breaker = post-ranking evaluate+stamp (M3-site
  precedent), narrative at composition, NO ordering effect in v1 · Receipts = offline cron +
  read routes; generation-pipeline touchpoints it marked RESERVED to be confirmed against its
  contract text (Assumption A-2, text pending — forwarded when their PLAN.md lands).
- **Cross-references owed in final docs:** breaker PRD cites negmem's acceptance-prior memo
  (path pending) and the Receipts contract section; both siblings receive this draft for
  reconciliation before operator delivery.

## 9. Operator decision register (accumulating; finalized in the PRD)

| # | Decision | Default if unanswered |
|---|---|---|
| 1 | v1 = stamp + narrative only; filter/demote deferred to v2 with its own gates | stamp+narrative only |
| 2 | Narrative stays deterministic templates (LLM = separate explicit decision) | deterministic |
| 3 | Hesitation line surface. **Finding (verified 2026-08-21): NO client renders `TradeCard.narrative` today** — only a code comment in `mobile/src/components/TradeCard.tsx:437` mentions it (arm-B audit "Refuted" section, re-verified by grep across mobile/web/extension). The "inside the existing narrative string" option therefore ships an invisible feature. Default flips to: **distinct card element** (mobile client change + Chalkline + structural guard + testIDs + TestFlight). Alternative the operator may prefer: a precondition ticket that makes `narrative` render at all, then ride it | distinct card element |
| 4 | `breaker_min_severity` initial bar (only knob with user-visible effect in v1) | set from calibration readout, not shipped-guessed |
| 5 | Shadow same-seat run (viewer-seat breaker for calibration §6.2b) — acceptable compute? | yes, behind `trade.breaker` |
| 6 | v2 seam election (per-arm pre-draft vs bypassed-on-interleave vs user-side filter) | none — decided after §6.4 readout |
| 7a | Extension code `roster_crunch` (broadened: forced drop / lineup slot math / positional pile-up) accepted into the shared taxonomy as `producer=breaker` | sibling-agreed 2026-08-21, pending operator yes |
| 7b | `shape_aversion` enters the taxonomy as `producer=negmem` (breaker may cite it only via future memory→breaker coupling); producer column added to the shared file | sibling-agreed 2026-08-21, pending operator yes |

## 10. Assumptions to verify at build (not trusted from this session)

- **A-1: CLOSED 2026-08-21** (evidence via Receipts session's prod read of
  `model_config_changes`, source=operator rows): `ghost_holdout_one_in` 10→0 @00:43:32Z,
  `bakeoff_group_size` 10→0 @00:43:33Z, `bakeoff_deck_limit` 30→60 @00:43:33Z,
  `bakeoff_serve_interleaved` 0→1 @00:43:34Z. Ghost rows END at that boundary; interleaved
  decks (arm mix challenger/current/gen_v2, zero ghosts) are live. Also logged same table:
  `qb_1qb_cap_elo` 1785→1644 and `qb_1qb_cap_knee_elo` 1580→1200 @04:46Z — 1QB QB prices drop
  sharply at the next value refresh; value-optics objections must not treat pre-boundary QB
  values as comparable. Retrospective studies additionally inherit Receipts' verified
  boundaries: the gradeable cohort starts 2026-08-16 (`assets_json` landed with telemetry, no
  backfill — ~7.7k earlier impressions permanently ungradeable) and picks carry NO value
  history (static code seeds). Prospective breaker calibration (post-ship stamps ⨝ pass
  reasons) is unaffected by either.
- **A-2: CLOSED 2026-08-21** — Receipts' Reconciliation contract landed
  (`docs/plans/receipts/PLAN.md` §7, dual-signed): Receipts touches zero generation code
  (writes only `receipts_grades`/`receipts_grade_runs`; explicit reads-never-writes list); its
  RESERVED feedback-into-scoring seam is the ordering/presentation multiplier stack
  (propensity/Thompson layer), never the generation path — disjoint from both my post-ranking
  stamp seam and negmem's generation-time prior; my fit-them-lens adjacency is cross-referenced
  as agreed; taxonomy §5 is reserved for the 1.1.0 objection vocabulary with the producer
  column exactly as reconciled (7a/7b).
- **A-3:** exact current line numbers for the M3 stamp site / `_log_deck_signal_impressions`
  features block (drift expected; re-cite at LLD-build time).

## 11. Deliverables of this planning thread

[scope.md](scope.md) (done) → this PLAN → [HLD.md](HLD.md) + [LLD.md](LLD.md) + [PRD.md](PRD.md)
via dual-agent draft/cross-critique with [reconciliation-log.md](reconciliation-log.md) → sibling
reconciliation folded in → `docs/plans/README.md` row → living-memory write-back → operator review.
**No implementation in this thread.**
