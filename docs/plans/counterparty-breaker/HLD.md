# HLD — Counterparty breaker

**Date:** 2026-08-21 · **Status:** MERGED CANDIDATE (synthesis of drafts A + B under the
orchestrator's merge rulings M-1..M-8; awaiting cross-review).
**Binds under:** [PLAN.md](PLAN.md) (AMENDED — authoritative) + [scope.md](scope.md); the LLD
binds tighter than this doc. Drafts preserved at [drafts/HLD-draft-A.md](drafts/HLD-draft-A.md)
and [drafts/HLD-draft-B.md](drafts/HLD-draft-B.md).
**Rule of citation:** every integration claim names a real symbol with file:line against this
checkout (`claude/trading-engine-eval-8ab7bc` worktree, 2026-08-21, re-verified for this
document). Line numbers drift; re-cite at build per PLAN A-3.
**Governing stance (from draft B, adopted):** the breaker's dominant failure mode is not "it
crashes" — it is being confidently wrong about a real, named human, in copy the user's
league-mate can screenshot. The risk architecture in §4–§6 is first-class design, not an
appendix.

---

## 1. Context & Goals

### 1.1 What v1 is

A deterministic **evaluation layer** — `backend/trade_breaker.py` — that runs after ranking and
before impression logging, predicts the counterparty's most likely decline reason for every
served card, stamps it (`features_json.breaker`), and (second flag) composes the top objection
as one deterministic hesitation sentence carried **inside the breaker payload** and rendered by
the client as a **distinct card element**. The organizing idea, verbatim from the PLAN: **the
breaker predicts the counterparty's decline reason, in the vocabulary the app already uses to
record decline reasons** (`trade_pass_reasons` layer-2 codes,
`backend/database.py:5579-5583`).

v1 is *measurement plus one gated sentence*. It kills nothing, reorders nothing, filters
nothing.

Why this is worth building at all: the engine argues one side (96.3% of 1-for-1 cards exist in
one direction; 84.5% of served cards never consult a partner board; the consensus-path viewer
receives more on 86.3% of cards — arm-B audit,
[docs/reviews/2026-08-19-armb-audit-consolidated.md](../../reviews/2026-08-19-armb-audit-consolidated.md)).
And why it is dangerous: the hesitation line claims something about a *third person's judgment*,
rendered to someone who knows that person — a property no existing surface has. Three background
facts make "confidently wrong" the default outcome absent counter-design:

1. **The window signal the breaker inherits is known-skewed.** `trade.outlook_composite` is dark
   for the engine (INV-372b, `backend/trade_service.py:3162-3168`: no caller outside Team Review
   supplies a starter signal, so the LEGACY age/pick vector scores partners) — and the audit
   found that vector labels ~65% of teams rebuilders (verify at build, A-4). `fit_outlook`, the
   class this feeds, is the second-most-filed real pass reason (33% of n=208).
2. **The data to know the counterparty is mostly absent.** 84.5% unboarded means their-seat
   `value_giving` usually degrades to consensus optics — which, on a deck where the viewer
   receives more 86.3% of the time, fires near-tautologically (§6 R-4).
3. **The validation population barely exists.** `deck_outcomes.action='propose'` has fired zero
   times ever; mirrored cards serve in both directions ~3.7% of the time, so the
   counterparty-seat calibration cut starts at n≈0 (§6 R-3).

### 1.2 Goals

| # | Goal | How this HLD delivers it |
|---|---|---|
| G-1 | Every served card carries a coded, evidenced objection prediction | §3 stamp at the post-mutation-stack seam (§2.3; organic decks and likes-you-injected cards included) |
| G-2 | Calibration is a join, not new instrumentation | objection codes ≡ pass-reason codes (§4 D-1) |
| G-3 | The card can tell the user what to preempt — without being confidently wrong about a person | hesitation line via `trade_narrative.hesitation_line` (§2.4), gated by the maturity ladder + evidence whitelist (§4 D-6/D-7) |
| G-4 | The v2 filter decision is made from data, not taste | PLAN §6.4 counterfactual computable from stamps alone |
| G-5 | Wrongness is bounded, attributable, and cheap to retract | provenance markers (§3.2), degradation ladder (§2.6), rollback ladder (§5.3) |
| G-6 | Sibling coherence | shared taxonomy §2.1 mirroring + §2.8 magnitude rule; `breaker_` prefix reserved-unused; producer column enforces the negmem boundary |

### 1.3 Non-functional requirements (binding)

- **NFR-1 — zero ordering effect in v1.** Deck order and composition are byte-identical with
  `trade.breaker` on vs off, on organic and bake-off decks alike. Mechanism, not policy: the
  breaker runs *after* the deck-mutation stack completes (§2.3) and mutates only a new card
  attribute. Enforced
  by a `test_fit_diag_inert`-pattern test (`backend/tests/test_trade_gen_fit.py:681` precedent:
  delete the attribute, assert served output identical) plus an order-capture test on
  interleaved decks under both draft paths (`bakeoff_runner.bypass_rerankers` discipline,
  `backend/bakeoff_runner.py:397`; channel taxonomy at `bakeoff_runner.py:83`).
- **NFR-2 — per-deck ms budget with labeled degradation.** The trade job has a 60s hard timeout;
  the breaker must be noise inside it. Budget: `breaker_ms_budget` (model_config, proposed
  default 250 ms/deck; §5.4 puts expected cost 1–2 orders of magnitude below it). Degradation is
  a *ladder with stamped rungs* (§2.6) — a truncated stamp says so and why; unlabeled
  missingness is a defect, because rank-correlated missingness silently poisons the §6.4
  counterfactual. Fail-open everywhere, but **never a bare null**: any per-card exception stamps
  the minimal marker object for that card, and the outer except handler stamps the minimal
  marker on every card (§2.6 — `{ver, degraded: <rung>, objections: null}`, constructible with
  no breaker state; warning-log precedent `backend/server.py:5715-5716`). An absent `breaker`
  key means flag-off, nothing else. A pre-flag-on dry-run ms number is handed to the operator
  (fit W0 precedent) before `trade.breaker` lights.
- **NFR-3 — flag-off byte identity.** `trade.breaker` off ⇒ the module is never imported (lazy
  import at the stamp site; `test_organic_never_imports_fit` precedent,
  `test_trade_gen_fit.py:883`) and `features_json` carries no `breaker` key at all.
- **NFR-4 — determinism.** Same inputs ⇒ same objections, severities, sentence. No LLM, no RNG,
  no wall-clock dependence beyond ages already baked into inputs.
- **NFR-5 — no new tables, no new routes.** `breaker_` table prefix stays reserved and unused.
  The one client change in v1 is the gated hesitation element (§2.4, operator decision #3
  default): Chalkline-token styling, structural guard `mobile/tests/check-breaker-card.js`,
  testIDs per scope.md §3 — nothing else in any client changes.
- **NFR-6 — fail-open is self-surfacing.** Rung markers are visible in the coverage metric.
  Coverage for the graduation gate = share of served impressions carrying a **scored objections
  vector** — covered **iff the objections vector is scored** (true of rungs 0–2, including
  rung-1/2 rows that ALSO carry a degradation marker; the two properties overlap and are
  tracked independently). Rung-3+ rows (marker, `objections: null`) are never covered. Pinned
  again in the preregistered calibration-readout spec so the gate is not arguable after the
  fact. Two
  criteria, side by side: scored coverage ≥99% of served impressions AND degraded share
  (rungs 1–3) < 5% (`breaker_degraded_share_max`, operator-tunable). A silent breaker outage
  presents as a failed graduation criterion, not a discovered mystery (§5.5).

### 1.4 Explicit non-goals (v1)

Filtering / demoting / reordering / draft changes, on any deck, under any flag this plan ships
(v2, own scope block) · learning or persistence (negmem's tense; `acceptance_prior`
(`backend/trade_gen_v2.py:283`) stays untouched and unfed) · retrospective scoring (Receipts'
tense) · reading `negmem_*` tables · touching G6 (stays user-seat, D-062 — the breaker mirrors
predicate *shapes*, never edits the presentment kill chain) · any counterparty notification or
cross-user surfacing (the breaker never causes output in the counterparty's own app) · any new
ingestion (reads only state the app already holds) · appending to `card.narrative` or modifying
`build_narrative` (§4 D-5) · producing `shape_aversion` in any form (§4 D-2).

---

## 2. Architecture Overview

### 2.1 Where the breaker sits

```
generator arms (current / challenger / gen_v2 / fit — or organic generate_trades)
        │
        ▼
ranking + (bake-off) interleaved draft                ← untouched
        │
        ▼  ranked deck (server.py:5694 bake-off / :5696 organic) — NOT yet final
[M3] fit_diag stamp (bake-off decks, server.py:5698-5716)   ← untouched
        │
        ▼
deck-mutation stack (all untouched; five layers run AFTER the M3 stamp):
  F7 exploration split (server.py:5723-5725) → likes-you injection (:5747 —
  ADDS cards) → F3 suppression (:5794) → _order_deck (:5900) → F7 wildcard
  insert (:5937) → F9 first-deck clamp (:5997)
        │
        ▼  deck-mutation stack complete — this is the exact list that feeds
           _log_deck_signal_impressions
┌────────────────────────────────────────────────────────────┐
│  EVALUATION LAYER (new, this feature) — post-F9,           │
│  pre-ghost-split (§2.3)                                    │
│  trade_breaker.stamp_breaker(...)          flag trade.breaker
│    → card.breaker attribute (per card)     attribute-only, fail-open,
│      incl. provenance markers              degradation ladder §2.6
│  trade_breaker.compose_narration(...)      flag trade.breaker_narrative
│    → sentence INSIDE breaker payload       (breaker.narrated) — never
│      (whitelist + maturity + switches)     appended to card.narrative;
│        via trade_narrative.hesitation_line templates
└────────────────────────────────────────────────────────────┘
        │
        ▼
ghost split (served_final, server.py:6034)
        │
        ▼
_log_deck_signal_impressions (def server.py:4020, call :6101)
        │                                       ← copies card.breaker into
        ▼                                          features_json.breaker
                                                   (uniform keys, §3.3)
trade_card_to_dict (server.py:10976)            ← additive `breaker` object;
        │                                          clients ignore unknown keys
        ▼
client: distinct hesitation element, gated on payload key + trade.breaker_narrative
```

This is the PLAN's "checker node" translation made literal: an evaluation stage between parallel
producers and downstream consumption, with the v1 twist that it *annotates* instead of *vetoing*
(the veto is v2's separately-gated question).

### 2.2 Component responsibilities

| Component | Responsibility | Explicitly NOT its job |
|---|---|---|
| `backend/trade_breaker.py` (new, ~leaf) | Build per-partner context lazily, once per partner per job; evaluate each served card from the partner's seat; return/stamp `{ver, top, objections, them, narrated, provenance, ms}`; expose `stamp_breaker(cards, ...)` mirroring `stamp_fit_diag`'s shape (`backend/trade_gen_fit.py:857`); own the narration eligibility gate + deck-level composition — `compose_narration(cards)` applies the per-class switches, whitelist, floors, format envelope, and repetition suppression, then calls `trade_narrative.hesitation_line` per eligible card | Ordering, filtering, DB writes, HTTP, importing `server.py` or `trade_gen_fit`; template text |
| `backend/trade_narrative.py` (edit) | New **pure** template function `hesitation_line(objection, players) -> str \| None` — deterministic, D-053-honest (renders only fields present in `objection["evidence"]`) | Deciding *whether* to render (switches, whitelist, maturity, floors — all live in `trade_breaker.compose_narration`; the flag check stays at the server callsite); touching `build_narrative`; LLM anything |
| `server.py _run_trade_job` (edit) | One guarded block at the post-mutation-stack seam (§2.3): lazy-import, `stamp_breaker`, and (flag 2) `compose_narration` — the server keeps only the flag check | Any breaker math, eligibility logic, or template text |
| `server.py _log_deck_signal_impressions` (edit) | One flag-guarded block beside — but OUTSIDE the `bakeoff_run` guard around — the `fit_diag` copy (`server.py:4205`, guard `:4193`): `features["breaker"]` + `features["breaker_shadow"]` from the card attributes (§3.3) | Recomputing anything at log time |
| `server.py trade_card_to_dict` (edit) | Additive optional `breaker` object — fit precedent (`out["fit"]`, `server.py:11060`) | Serving the full objection vector |
| `mobile/src/components/TradeCard.tsx` (edit) | The distinct hesitation element: renders `breaker.sentence` iff present; gated on `trade.breaker_narrative`; Chalkline tokens; testIDs | Switching on objection codes (server-composed sentence only in v1) |
| `trade_service.py` / `database.py` (edit) | Knob registrations only (five-registration rule, `trade_service.py:895-916`) | Any behavior change |

**Import discipline.** `trade_breaker` imports `trade_service as ts` and `trade_optimizer as
topt` (T1 MODULE-import discipline, `trade_gen_fit.py:35-36` — binding by name would freeze
predicates against knob changes, and the breaker deliberately reuses live predicate shapes; a
binding-sabotage test monkeypatches a `ts` knob and asserts the breaker verdict moves). It
**never** imports `trade_gen_fit` — that module's organic-isolation contract ("imported by
exactly one production caller, `bakeoff_runner.gen_fit_cards`", `trade_gen_fit.py:23-24`) stays
intact; where the breaker wants the them-lens number it *reads the `fit_diag` stamp* already on
the card (§4 D-3), never rescoring. `trade_service` never imports `trade_breaker`; the only
production caller is the `server.py` stamp site (`test_flag_off_never_imports_breaker`, shaped
on `test_organic_never_imports_fit`).

### 2.3 The hook in `server._run_trade_job` (seam redefined round 3, re-verified this checkout)

**The deck is NOT final after the M3 stamp block.** Round-2 review caught what both drafts and
the merged candidate missed: five mutation layers run between the M3 stamp and impression
logging, and one of them ADDS cards — the F7 exploration split (`server.py:5723-5725`),
likes-you injection (`:5747` — injects cards that never existed at the M3 site), F3
decline-window suppression (`:5794`), `_order_deck` (`:5900`), the F7 wildcard insert
(`:5937`), and the F9 first-deck clamp (`:5997`). A breaker stamped at the M3 site would
evaluate cards that never serve and miss cards that do.

**Seam (redefined):** the breaker block runs **immediately after the deck-mutation stack
completes — post-F9, pre-ghost-split** — after the F9 block ends and before
`served_final = final_cards` (`server.py:6034`), so the list it evaluates is the exact list
that feeds `_log_deck_signal_impressions` (call site `server.py:6101`), likes-you-injected
cards included. Cost is bounded by the **final pre-ghost-split deck size** (post-clamp,
post-injection). **Operator ruling (2026-08-21, batch-wide): NO ghost cards, full stop** —
`ghost_holdout_one_in` = 0 in prod since 00:43Z and the code/seed defaults flip to 0 in
Receipts' next ship, so `final_cards == served_final` in practice and D-9's "served deck only"
means exactly that. The ghost-split code path (`server.py:6034-6046`) still exists; the seam
sits before it as a code location only. Robustness note, not a design dependency: if a ghost
row ever existed again, the stamp is uniform across the pre-split list by construction — but
no breaker measurement may use ghost impressions, backward- or forward-looking, per the
ruling. Rationale:

1. Every card that reaches impression logging is present, and only those cards — the §6
   readouts join stamps to outcomes, which exist only for served cards.
2. `fit_diag` stamped at M3 survives on the card, so the breaker can still read it (D-3)
   instead of rescoring. (Likes-you-injected cards entered after M3 and carry no `fit_diag`;
   their `them` passthrough is null, §3.1.)
3. Everything the breaker reads is still in scope at that line: `g_league`, `players_dict`,
   `seed_map`, `active_format`, `final_cards`.

Two consequences the LLD must handle:

1. **Snapshot republish.** Mutation layers republish the streaming snapshot as they run, and
   the post-impression republish (which re-serializes every card) only runs when
   `deck.signal_v2` is on. The narrated payload must land in the snapshot the client actually
   receives on **every flag combination, `deck.signal_v2` off included** — the breaker block
   republishes (or provably precedes the final publish); exact site re-cited at LLD.
2. **Invariant (test-enforced):** every card reaching impression logging on a flag-on deck
   carries the breaker key — scored or rung-marked (§2.6). An absent key on a flag-on row is
   a defect; absent means flag-off, nothing else (the M4 absence-must-be-impossible pattern
   applied at this seam).

Two structural differences from the fit stamp. First, the guard is **`flags.trade_breaker`**,
not `bakeoff_run is not None` — the PLAN requires stamps on organic AND bake-off decks (the
viewer-seat calibration cut and organic coverage need them). This widens the blast radius of any
latency or exception bug from "bake-off jobs" to "every deck job" — which is why the budget
ladder (§2.6) and the non-fatal envelope are v1 acceptance criteria, not hardening follow-ups.
Second, the breaker evaluates the **served deck only**, not every arm's full candidate list
(§4 D-9).

Sketch (LLD owns the exact code, the exact insertion line, and the republish mechanics):

```python
# breaker (v1) — evaluate + stamp + (flag 2) compose. Post-mutation-stack,
# pre-ghost-split, attribute-only, fail-open, zero ordering effect
# (test-enforced).
if flags.trade_breaker:
    try:
        from .trade_breaker import stamp_breaker, compose_narration  # lazy —
        stamp_breaker(final_cards, league=g_league,    # flag-off never imports
                      players=players_dict, seed_elo=seed_map,
                      scoring_format=active_format)
        if flags.trade_breaker_narrative:
            compose_narration(final_cards, players=players_dict)
            # eligibility (switches/whitelist/floors/envelope) + deck-level
            # repetition suppression live in trade_breaker; templates via
            # trade_narrative.hesitation_line → c.breaker["narrated"]
    except Exception as bk_err:
        log.warning("breaker stamp failed (non-fatal): %s", bk_err)
        # the handler stamps the minimal rung-5 marker on every card (§2.6)
```

### 2.4 The narrative mechanics (M-3 — correction to both drafts)

**Verified (PLAN register #3, re-verified in the arm-B audit): no client renders
`TradeCard.narrative` today** — only a comment at `mobile/src/components/TradeCard.tsx:437`
mentions it. Appending to `card.narrative` would ship an invisible feature. Therefore:

- The hesitation sentence lives **inside the breaker payload** (`breaker.narrated`), composed by
  `trade_breaker.compose_narration` (eligibility + deck-level suppression) calling the new pure
  template function `trade_narrative.hesitation_line` at the breaker seam.
  `build_narrative` (`trade_narrative.py:103`, 2-sentence cap at `:167`) is **untouched in v1**.
- The client renders it as a **distinct card element** behind `trade.breaker_narrative`:
  Chalkline tokens, structural guard `mobile/tests/check-breaker-card.js` (element gated on the
  `breaker` payload key + flag, no render when absent), testIDs (e.g.
  `trade-card-breaker-hesitation`) passing `mobile/scripts/testid-lint.sh` — all per scope.md §3.
  **Mobile-only surface in v1:** the element exists only in
  `mobile/src/components/TradeCard.tsx`; web and extension ignore the payload key.
- The templates live in `trade_narrative.py` so all narrative copy keeps one home, one snapshot
  suite, one honesty rule (the module's positional-honesty comment block,
  `trade_narrative.py:120-126`, is the covenant `hesitation_line` inherits).

**The `_opponent_frame` contradiction hazard is LATENT today** — `_opponent_frame`
(`trade_narrative.py:86-100`) renders "They're rebuilding — the youth going back fits their
timeline" into a string nobody displays. Two defenses anyway, as standing convention (M-3,
adopting draft B's D-B3):

1. **Single-composition-owner rule:** `hesitation_line` owns counterparty-facing copy. Any
   future work that makes `narrative` render must route its they-sentence through the same
   composition site, one they-sentence per card maximum, from one shared input snapshot.
2. **Mirrored-predicate coherence test — scoped as a characterization test:** `_opponent_frame`
   fires only when the give-side lean *fits* the partner window; breaker `fit_outlook` fires
   only when the package *pushes against* it. The LLD owes a test asserting the two window
   claims cannot assert opposite facts **given the current `_opponent_frame` thresholds**
   (`trade_narrative.py:86-100`; fires at |lean| ≥ 0.05, thresholds at `:96-99`) — it
   characterizes today's constants, and any threshold adjustment needed to keep coherence lands
   **breaker-side** (`_opponent_frame` is not this feature's to edit). Precondition the test
   must pin: both writers consume the same outlook **value** — `PartnerContext` resolves
   declared-else-inferred while `_opponent_frame` reads `match_context.opponent_outlook`; if
   those diverge for a card, that divergence is itself the contradiction vector, so the test
   asserts same-value or fails. So the day `narrative` becomes visible, the card cannot say
   "fits their timeline" and "against their window" in the same breath.

### 2.5 Evaluation model — two-phase, per-partner amortized

Naive cost is (cards × classes × predicate cost); the expensive inputs are per-*partner*. So:

- **Phase 1 — `PartnerContext` (dataclass, built lazily, cached by `target_user_id`, only for
  partners actually appearing in the served deck):** roster ids;
  `ts.analyze_roster_strengths(...)` outputs (`trade_service.py:2211` —
  `position_needs`/`position_surplus`/tier bins); window = declared `league_preferences` outlook
  else `ts.infer_team_outlook(...)` (`trade_service.py:3084`) **as the engine serves it**
  (legacy vector today per INV-372b; the breaker records which it got, §3.2, retains BOTH the
  declared and inferred values — D-8's agreement rule and the stamp need the pair — and inherits
  the composite automatically iff/when the engine graduates — §4 D-8); `asset_preferences` (their
  side, resolved per §3.4); board accessor (raw `member.elo_ratings` — T3 provenance rule,
  `trade_gen_fit.py:5-13`: the breaker must never touch `_shrink_user_elo`) + the PLAN F-3
  authenticity heuristic result (§3.2 `board_auth`); starter-slot map; depth-chart reads.
- **Phase 2 — per-card class evaluation, two deck-wide passes:** cheap arithmetic against the
  snapshot, mirroring at evaluation time (taxonomy §2.1: swap give/receive; the user's `2x1` is
  the partner's `1x2`; no partner-frame labels are ever minted — §4 D-10). The cheap classes
  evaluate deck-wide first; the structurally expensive feasibility tier (`roster_crunch`,
  `fit_new_weakness` via the `topt._feasible_after` shape) runs as a **second deck-wide pass**,
  budget-gated at a checkpoint (§2.6) — dropped whole and labeled, never truncated card-by-card.

Every class always emits `{code, severity, evidence}` or an explicit skip/degrade marker —
never silent absence (M4 precedent: absence must be impossible; only null/skipped is
representable).

### 2.6 Budget and degradation ladder (what breaks first, on purpose) — M-4(e)

`breaker_ms_budget` (model_config, five registrations) against the 60s job timeout. Design
principle: **degradation must be attributable and unbiased-or-labeled** — missingness that
correlates with deck rank poisons the §6.4 filter counterfactual unless it is stamped.

**Bare null is never stamped.** Every degraded or exception path stamps the **minimal marker
object** `{ver, degraded: <rung>, objections: null}` — constructible in the except handler with
no breaker state. An absent `breaker` key means flag-off, nothing else.

Evaluation is **two deck-wide passes** (§2.5): pass 1 = cheap classes for every card; then a
budget checkpoint at `breaker_budget_checkpoint_frac` × `breaker_ms_budget` (a named knob, not
a magic fraction); pass 2 = the feasibility tier for every card, run whole or dropped whole.

| Rung | Trigger | Behavior | Stamp records |
|---|---|---|---|
| 0 | normal | both passes, all cards | full objection vector + `ms` |
| 1 | partner snapshot fails | that partner's cards: cheap classes where computable, else the minimal marker | `degraded: "partner_snapshot"` |
| 2 | budget checkpoint trips after pass 1 | feasibility tier dropped WHOLE — no card in the deck gets it (deck-uniform, labeled) | `skipped: ["roster_crunch","fit_new_weakness"], reason: "budget"` on every card |
| 3 | budget exhausted mid-pass | remaining cards get the minimal marker | `degraded: "budget_exhausted"` |
| 4 | exception (card) | that card gets the minimal marker | `degraded: "exception_card"`; logged, counted |
| 5 | exception (outer) | the except handler stamps the minimal marker on EVERY card | `degraded: "exception_outer"` + warning log + diagnostics counter |

Rung 2 drops a *class tier* deck-uniformly rather than truncating within a class by rank — the
round-2 "skip for remaining cards" rule would have produced exactly the rank-correlated
missingness this section forbids. Rung-3 missingness is rank-correlated by construction and
therefore **must be labeled**, so readouts exclude budget-truncated decks instead of silently
absorbing the bias. Per-rung coverage rides job diagnostics (FitReport precedent) — "stamps are
missing" is *known*, not discovered (§5.5).

### 2.7 The consistency spine — breaker predicates are mirrored live predicates

Cross-seat contradiction (user A's card says "B will object: takes their only startable TE"
while the mirrored card serves happily in B's own deck) must be a *bug with a test*, not a vibes
problem. Structural rule: **where an objection class has a live viewer-seat predicate, the
breaker evaluates the SAME predicate shape, module-imported, seat-swapped** —
`fit_new_weakness` mirrors R5/`need_gate_ok` lineup logic; `fit_duplicate` reads the same
`analyze_roster_strengths` the viewer seat uses; `value_giving` computes one severity path on
both deck types via `ts` helpers (D-3 — `fit_diag` feeds only the `them` passthrough, never the
severity). The LLD owes a cross-seat coherence test:
for a mirrored fixture card, high breaker severity from seat B ⟺ B's own viewer-seat gate would
have flagged the mirror. Where no live mirror exists (`roster_crunch` — new logic), the class
gets the conservative maturity treatment (§4 D-6: stamp-only until per-class calibration earns
narration).

---

## 3. Data Model & Flow

### 3.1 The breaker result (rides the card, then `features_json`)

Sketch — exact field types are LLD territory:

```jsonc
// card.breaker — set by stamp_breaker; degraded paths stamp the minimal
// marker object {ver, degraded, objections: null} (§2.6) — never bare null;
// the attribute/key is absent only when the flag is off
{
  "ver": "brk-1",              // BREAKER_VERSION (fit SCORER_VERSION precedent):
                               // predicates, severity math, thresholds,
                               // evidence shapes — trade_breaker.py territory.
  "tmpl_ver": "brt-1",         // template version (trade_narrative.py), stamped
                               // alongside: calibration readouts key on `ver`
                               // alone; narration A/B readouts key on the
                               // (ver, tmpl_ver) pair; a template-snapshot
                               // test pins tmpl_ver.
  "top": {                     // argmax severity above its per-class floor;
    "code": "fit_outlook",     // null when nothing clears a floor
    "severity": 0.82,
    "evidence": {"outlook": "rebuilder", "asset": "p_4046", "age": 29, "pos": "RB"}
  },
  "objections": [              // EVERY v1 class: scored, skipped, or degraded —
    {"code": "fit_outlook",   "severity": 0.82, "evidence": {...}},
    {"code": "roster_crunch", "severity": 0.31, "evidence": {...}},
    ...                        // never absent. Classes below floor still listed:
  ],                           // the §6.4 counterfactual needs the full vector.
  "them": 41.3,                // fit_diag them-score PASSTHROUGH when the stamp
                               // exists (bake-off decks); null on organic decks
                               // AND on cards injected after M3 (likes-you).
                               // Never a rescored parallel number (D-3).
  "narrated": "They're rebuilding — this sends them a 29-year-old RB.",
                               // the hesitation sentence, or null (flag off /
                               // below bar / ineligible / suppressed) — M-3:
                               // lives HERE, never appended to card.narrative
  "suppressed": null,          // enumerated: "repetition" | "below_floor" |
                               // "class_ineligible" | "format_gap" (§4 D-7) —
                               // distinguishes "no objection" from "muted"
  "outlook_src": "legacy",     // "declared" | "legacy" | "composite" — provenance
  "board_auth": "consensus",   // "board" | "board_suspect" (F-3 clone heuristic)
                               //          | "consensus" (unboarded fallback)
  "format_gap": null,          // classes outside the format envelope (§3.5)
  "degraded": null,            // rung marker (§2.6)
  "ms": 4.1
}
```

**Viewer-seat shadow (operator decision 5):** the shadow result rides a **separate attribute
`card.breaker_shadow`** — same shape as `card.breaker`, same uniform-keys rule — and is
**never** serialized by `trade_card_to_dict` (serialization-guard test:
`test_breaker_shadow_never_serialized`).

Shape rules:

- **Codes are a closed set** (M-2): the 9 *coded* `trade_pass_reasons` layer-2 codes — the
  ten-code `PASS_REASON_LAYER2` set (`database.py:5579-5583`) minus **`other_text`**, which is
  free text, not a code: it is excluded from the breaker vocabulary, and calibration joins
  treat filed `other_text` rows as unmatched-by-construction, excluded from per-class precision
  denominators (D-1) — plus exactly one breaker extension, **`roster_crunch`** (broadened:
  forced drop of a player they demonstrably value / lineup slot math / positional pile-up from a
  consolidation ask), registered in the shared taxonomy with `producer=breaker`.
  **`shape_aversion` is NOT a breaker code in any form** — it is ceded to negmem with
  `producer=negmem` (PLAN decisions 7a/7b); a `producer=negmem` code in a breaker output is a
  reviewable defect, enforced by the vocabulary-closure test (scope.md §3).
- **Evidence values are ids + numbers + enum codes only** — no free text, no player names inside
  evidence; names resolve at template time from ids (narrative-honesty rule, §5.2). Evidence
  keys are per-code and enumerated in the LLD; `hesitation_line` may render only those keys
  (D-053 mechanically).
- **Severity is per-class 0–1** from existing margins (their-board deltas, surplus/needs
  margins, outlook score margins, feasibility slack) — no new value model, no cross-class
  aggregate (§4 D-4), with the provenance haircut applied (§4 D-8).

### 3.2 Provenance markers (M-1, M-4(c)/(f) — B's risk architecture as payload)

Every stamp carries the markers that make wrongness attributable:

| Marker | Values | Feeds |
|---|---|---|
| `outlook_src` | `declared` / `legacy` / `composite` | severity haircut (D-8); calibration cut by source; makes the composite's graduation day visible in the data instead of silently shifting calibration |
| `board_auth` | `board` / `board_suspect` / `consensus` | PLAN F-3: prod boards for 5 of 6 members of the one boarded league are near-uniform ~644-646 rows, likely bulk-seeded — a clone board just re-derives consensus while claiming to speak for the manager. The cheap divergence-count heuristic discounts board-based severity confidence on `board_suspect`; unboarded falls to `consensus` with the weaker-claim discount |
| `format_gap` | class list or null | §3.5 envelope; gapped classes are narrative-ineligible |
| `degraded` / `skipped` | rung markers | §2.6; labeled missingness for readout exclusion |

### 3.3 Stamp into `features_json.breaker` — uniform keys

In `_log_deck_signal_impressions` (`server.py:4020`), inside the features assembly beside the
existing `features["fit_diag"] = getattr(card, "fit_diag", None)` at `server.py:4205`, one
flag-guarded block. **Unlike the fit keys, which sit inside the `bakeoff_run is not None` guard
(`server.py:4193`), the breaker lines sit OUTSIDE that guard — organic decks stamp too** (the
PLAN requires it; a breaker key that only appeared on bake-off rows would silently halve the
calibration population):

```python
if flags.trade_breaker:                    # OUTSIDE the bakeoff_run guard
    features["breaker"] = card.breaker     # attribute REQUIRED on every card of a
    # flag-on deck — scored stamp or §2.6 minimal marker, never None (a missing
    # attribute here is a bug; no getattr default that would bless a bare null)
    features["breaker_shadow"] = getattr(card, "breaker_shadow", None)
    # viewer-seat shadow (§3.1): same shape; when the shadow run is ON the same
    # marker discipline applies (incl. a rung-5 shadow marker from the outer
    # handler — unlabeled shadow missingness would undermine R-3 exactly as
    # bare-null breaker missingness would); null permitted only when the shadow
    # run is OFF (operator decision 5). Never serialized to clients.
```

- Rides **inside** `features_json` (one column), so the `save_deck_impressions` executemany
  first-row-keys trap (`database.py:5503`; row dicts must share keys or non-first-row keys are
  silently dropped) cannot bite — fit-challenger LLD §3.3 reasoning. The uniform-keys rule still
  applies at the JSON level: `breaker` carries a scored stamp or a §2.6 minimal marker on every
  row of a flag-on deck (`breaker_shadow` may be null only with the shadow run off), extending
  `test_impressions_uniform_columns` (`backend/tests/test_bakeoff_serving.py:1170`).
- Flag off ⇒ no key ⇒ rows byte-identical to today (NFR-3).
- The stamp is draft-agnostic and must hold under both draft paths (`compose_deck` and
  `team_draft`, `group_size` ∈ {0, N} — fit F-6 trap).
- No new columns, no new tables. If v2 needs queryable columns or `breaker_` tables, that is
  v2's scope block.

### 3.4 Identity: whose preferences, whose board (co-owner trap) — M-4(f)

`card.target_user_id` is a LEAGUE identity (roster `owner_id`); `asset_preferences` and member
boards are ACCOUNT-adjacent. For sole owners the strings coincide; for co-owned rosters
(ADR-012) declared prefs may live under a co-owner's id. Rule: resolve counterparty state over
**`{owner_id} ∪ co_owner_ids(roster)`** via `backend/sleeper_roster.py` — the ONE predicate,
never a hand-rolled comparison. Conflicts: union for `untouchable`/`not_interested` (either
owner's veto is a veto); if two boards exist, the canonical owner's board wins with `board_src`
recorded. Deterministic and documented, not claimed-right — *consistent*, which is what
calibration needs. Co-owner fixture test required (LLD).

### 3.5 Format envelope (v1) — M-4(f)

Fully-scored envelope: Sleeper-format leagues whose starter structure
`analyze_roster_strengths` actually models — `_POS_TIER_CUTS` assumes 12-team
(`trade_service.py:2069-2078`, superflex only via the `sf` QB cuts), and G-026 means IDP/K
assets price 0.0, corrupting depth profiles in those leagues. Outside the envelope the breaker
does not guess: depth-based classes (`fit_new_weakness`, `fit_duplicate`, `roster_crunch`) stamp
with `format_gap` and are **narrative-ineligible**. A 14-team or IDP league gets fewer named
hesitations, not wrong ones. The envelope is enumerated in the LLD; the marker makes its cost
measurable (share of decks with ≥1 gapped class rides diagnostics), which is the case for or
against widening in v2. Wrong-counterparty-state inputs degrade-and-mark, never silently
compute: G-045 (partner pruned from pool) → rung 1; co-owner split → §3.4; stale/clone boards →
`board_auth`; board staleness (is last-ranked-at recoverable?) → open question Q-2.

### 3.6 Serialization to clients

`trade_card_to_dict` (`server.py:10976`) gains an additive optional block (fit precedent —
`out["fit"] = _fit` at `server.py:11060`; fit-challenger LLD §3.4):

```python
_bk = getattr(card, "breaker", None)
if _bk is not None and _bk.get("narrated"):        # narration-gated: dark window serves NOTHING
    d["breaker"] = {"code": ..., "severity": ..., "sentence": _bk["narrated"]}
```

**The client payload is narration-gated, not stamp-gated (round-4 fix).** During the phase-1
dark-stamp window (`trade.breaker` on, `trade.breaker_narrative` off) the payload carries **no
`breaker` key at all** — an earlier draft served `{code, severity}` whenever `top` was non-null,
which would have shipped dark-class, possibly private-state-derived codes
(`other_player_keep`, board-basis `value_giving`) as inspectable structured data to the
counterparty's direct negotiation adversary, hollowing out the D-6 copy whitelist at the
payload layer. Gating on `narrated` restricts the serialized object, by construction, to
classes that are graduated (D-6 switch), whitelist-clean, and above their narration floor —
`compose_narration` populates `narrated` only for those. Payload-side guard joins the §5.8
family: `test_breaker_payload_absent_during_dark_window` (stamped card, narrative flag off ⇒
no `breaker` key in `trade_card_to_dict` output) alongside
`test_breaker_shadow_never_serialized` (§3.1). The full objection vector never serializes —
it stays server-side in `features_json` for measurement. `docs/api-reference.md` row per
scope.md §4.

### 3.7 End-to-end flow (one job)

1. Job starts (`_run_trade_job`, `server.py:5412`); generation + ranking (+ bake-off draft) run
   exactly as today.
2. Ranked deck lands (`server.py:5694/:5696`). Fit M3 stamp runs on bake-off decks
   (`:5698-5716`). The deck-mutation stack then runs — F7 split (`:5723-5725`), likes-you
   injection (`:5747`), F3 suppression (`:5794`), `_order_deck` (`:5900`), F7 wildcard
   (`:5937`), F9 clamp (`:5997`) — all untouched.
3. `trade.breaker` on → **post-F9, pre-ghost-split** (§2.3): `stamp_breaker` builds
   `PartnerContext`s lazily (partners in the deck only), evaluates each card from the partner
   seat, sets `card.breaker` with provenance markers (and `card.breaker_shadow` when the shadow
   run is on).
4. `trade.breaker_narrative` on → `trade_breaker.compose_narration(final_cards)` — deck-level
   eligibility gate (per-class switch `breaker_narrate_<class>` D-6, whitelist D-6, per-class
   floor + `breaker_min_severity`, format envelope, repetition suppression D-7) →
   `trade_narrative.hesitation_line` templates → `card.breaker["narrated"]`; the snapshot
   republish lands the sentence in the client payload on every flag combination (§2.3).
5. Ghost split (`served_final`, `server.py:6034` — inert under the no-ghost ruling:
   `served_final == final_cards`); `_log_deck_signal_impressions` (call `:6101`) freezes
   `features_json.breaker` (+ `breaker_shadow`) per row (uniform keys).
6. `trade_card_to_dict` serves the additive object **only for narrated cards** (§3.6 — the
   dark window serves no `breaker` key); the client's gated element renders the sentence.
7. Outcomes accrue in `deck_outcomes` / `trade_pass_reasons` exactly as today; every PLAN §6
   readout is a SQL join over stamps + outcomes. No breaker-specific write path exists.

---

## 4. Key Design Decisions (mini-ADRs; risk architecture is first-class here)

### D-1 — Objection vocabulary = `trade_pass_reasons` anchor + one registered extension

**Decision.** Objection codes are the shipped *coded* layer-2 pass-reason codes — the ten-code
`PASS_REASON_LAYER2` set (`database.py:5579-5583`) **minus `other_text`**, which is free text,
not a code: it is excluded from the breaker vocabulary, and calibration joins treat filed
`other_text` rows as unmatched-by-construction, excluded from per-class precision denominators
— extended only by `roster_crunch` (`producer=breaker`), registered in
the shared taxonomy (§5.7; changes only by PR to that file, pending operator decision 7a).

**Why.** (1) Calibration becomes a join against ~200+ existing coded rows — G-2 with zero new
instrumentation. (2) One vocabulary, two tenses, with negmem (their hard constraint: extensions
extend the shipped taxonomy, never parallel it); the producer column mechanically enforces the
present-state/historical boundary. (3) The codes are product-validated as reasons managers
actually give.

**Alternative rejected.** A bespoke objection ontology — unfalsifiable against filed reasons, a
third vocabulary for siblings to reconcile, a standing invitation to drift.

**Consequence.** Some real objections compress into coarse codes. Accepted: coarse-but-joinable
beats rich-but-orphaned; v2 can subdivide with data in hand.

### D-2 — `shape_aversion` is not a breaker code (M-2, corrects both drafts)

**Decision.** The breaker never emits `shape_aversion` — not scored, not floor-disabled, not
stamped dark. It enters the shared taxonomy as `producer=negmem` (PLAN 7a/7b); the breaker may
cite shape aversion only via the future memory→breaker coupling (neither v1). The concept both
drafts were reaching for with a present-state "shape" predicate — roster-spot cost of a
consolidation ask, forced drops, lineup slot math — lives in the **broadened `roster_crunch`**.

**Why.** A manager's *learned* resistance to a package shape is behavioral/historical — negmem's
layer. A deterministic present-state predicate pretending to be that concept would blur the one
boundary the producer column exists to enforce.

### D-3 — Reuse the fit them-lens; never rescore where a stamp exists (M-1)

**Decision.** `breaker.them` is a **passthrough** of `card.fit_diag`'s them-score, stamped on
every bake-off card by `stamp_fit_diag` (`trade_gen_fit.py:857`). On organic decks — and on
cards injected after the M3 stamp (likes-you) — no stamp exists and `them` is **null in v1**.
The breaker never imports `trade_gen_fit` and never rescores a parallel partner-liking number
(taxonomy §2.8 purity). The `value_giving` class *severity* computes through **one code path on
both deck types** — the breaker's own margin via `ts` helpers (`elo_to_value`,
`package_value_v2`), board-based when an authentic board exists, consensus-based otherwise,
with the basis recorded in the objection's evidence (`basis: "board" | "consensus"`) — a
per-class 0–1 margin, not a 0–100 liking scale. `fit_diag` feeds the `them` passthrough ONLY,
never the severity: two severity paths forked by deck type would fork calibration by deck type.

**Why.** (1) Taxonomy §2.8: extend the them-score, don't mint a parallel scale. (2) Two scorers
of "how much they like it" will disagree eventually — an unfalsifiable bug farm. (3) Preserves
`trade_gen_fit`'s one-production-caller organic-isolation contract (`trade_gen_fit.py:23-24`).

**Consequence.** If organic them-scores become load-bearing, the right move is promoting the fit
stamp to organic decks — a **fit-challenger scope question**, recorded in the operator register
(§6.3 item 13), never duplicated here.

### D-4 — Severity is per-class; no breaker-owned aggregate

**Decision.** Each class scores 0–1 from its own existing margins. No cross-class sum; `top` is
argmax over per-class severities above per-class floors — a selection, not a score. The only
whole-card partner-liking magnitude the system carries is the fit them-score (D-3).

**Why.** Cross-class severities are not commensurable; a summed "acceptance score" would be a
third partner-propensity number beside the fit them-score and `acceptance_prior`
(`trade_gen_v2.py:283`) — three semantics for one concept is the incoherence the sibling
contract exists to prevent.

**Consequence.** Cross-class argmax compares severities ordinally at the floor boundary; the
per-class calibration readout (D-6) is the empirical check, and per-class floor knobs
(`breaker_floor_<class>`) let calibration re-level classes without code.

### D-5 — Hesitation sentence lives in the payload; `build_narrative` untouched (M-3)

**Decision.** No append to `card.narrative` — nothing renders it (verified, §2.4). The sentence
is composed by `trade_breaker.compose_narration` (eligibility + deck-level suppression) calling
the `trade_narrative.hesitation_line` templates at the breaker seam, into `breaker.narrated`,
served as `d["breaker"].sentence`, rendered by a distinct, flag-gated, structurally-guarded card
element (mobile-only surface in v1, §2.4). Standing conventions adopted: single-composition-owner (`hesitation_line` owns
counterparty-facing copy) and the mirrored-predicate coherence test against `_opponent_frame`
(§2.4).

**Why.** Draft A's append path shipped invisible text and left a latent two-writers
contradiction; the payload path gives the client a real surface, keeps flag-off payloads
byte-identical, and keeps all copy in `trade_narrative.py` under one honesty regime. No LLM
(operator constraint, PLAN §0/§7); templates are snapshot-testable and D-053-checkable, prose is
not.

### D-6 — Evidence whitelist + per-class maturity ladder (M-4(a)/(b) — B wholesale)

**Decision — whitelist.** Only **public-observable** evidence may ever render: roster
composition, lineup math, depth-chart facts, window as *inferred from public state*, consensus
values. Private counterparty state — `asset_preferences` contents, their board contents or
deltas — **stamps dark and never renders in v1**. Whether even a generic form ("unlikely to move
him") may ever render is an operator register question (§6.3 item 8).

**Why.** Rendering "they've marked X untouchable" discloses one user's private in-app list to
their direct negotiation adversary — a trust breach with no retraction, asymmetric (the harmed
party never sees the screen that harmed them). Even indirection leaks: "they demonstrably value
X above consensus" *is* their board. The whitelist makes the leak structurally impossible in
copy while preserving the measurement value of the dark stamp. Full argument in §5.6.

**Decision — maturity ladder via per-class narration switches.** Narration eligibility is a
**per-class switch `breaker_narrate_<class>`** (model_config, default 0/off) — **separate from
the per-class severity floors**. Floors shape top-selection and the stamp distribution;
overloading a floor to 1.1 to silence a class would distort the §6.4 counterfactual. Every
class starts stamp-only (all switches 0). **Graduation is the operator lowering/flipping a
class's switch via `set_knob`** — logged in `model_config_changes`, so measurement windows
censor automatically (M1 rail). A class earns its flip on **per-class calibration precision vs
preregistered baselines with minimum-n gates**: per-class precision/recall must beat the
majority-class baseline (40% `value_giving` on n=208 — "always predict value_giving" scores 40%
match in aggregate, so aggregate match-rate alone is calibration theater) and a
stratified-random baseline, per class, with a preregistered minimum n per cell before any
graduation claim. **Preregistration artifact and deadline (binds R-3):** a **calibration-readout
spec** — an LLD section or a standalone doc in this folder — is committed **before
`trade.breaker` first lights**, pinning per-class minimum n, the required margin over BOTH
baselines (majority-class and stratified-random), and the stratification variables (at minimum
`outlook_src` × board basis). The numbers are LLD territory; the mechanism and the deadline are
HLD commitments. The counterparty-seat cut
(PLAN §6.2a) is a long-horizon accumulator, never a launch gate (n≈0 today); the viewer-seat
shadow (§6.2b) is the primary calibration population and is labeled in the readout as proxy
validation with its selection caveat. The §2.7 cross-seat consistency check is a third,
population-independent validity signal.

### D-7 — Anti-wallpaper: per-class floors + repetition suppression + entropy monitor (M-4(d))

**Decision.** (1) Per-class floors are knobs (`breaker_floor_<class>`), with the
consensus-basis `value_giving` floor set materially higher than board-basis — a single global
floor cannot survive the near-tautological consensus case (viewer receives more on 86.3% of
consensus cards). **Board-basis `value_giving` is narration-INELIGIBLE outright** (not merely
evidence-masked): its `breaker_narrate_value_giving` switch governs the consensus basis only,
so no LLD can word a board-triggered sentence in consensus terms while its very presence
discloses the board delta (round-4 privacy refinement; consistent with D-8's public-state
rule). (2) Repetition suppression: if the same (partner, code) hesitation would
render on more than `breaker_max_repeat_frac` of a deck's cards for that partner, render on the
top-severity card only; the rest stamp `narrated: null, suppressed: "repetition"` so the A/B
readout distinguishes "no objection" from "objection muted". (3) A class-entropy monitor over
weekly `top.code` distribution rides diagnostics, with an explicit red line before narrative
graduation — a distribution collapsing to one class is the wallpaper failure and is invisible in
coverage metrics.

**Why.** A deck where every card says "they'll want more" teaches the user to ignore the line
(banner blindness), kills the feature's information value, and flattens the stamp distribution
that §6.4 depends on. Suppression makes narration deck-context-dependent — surfaced as operator
register item 10.

### D-8 — Severity haircut by outlook provenance; the breaker reads the engine's outlook (M-4(c))

**Decision.** The breaker inherits the window signal the engine serves (legacy vector today,
INV-372b, `trade_service.py:3162-3168`), stamps `outlook_src`, and never calls the composite
directly. Legacy-vector-derived `fit_outlook` severities are **discounted** (haircut knob), and
the **narration margin bar is higher than the stamp bar** — inferred-window `fit_outlook`
narrates only above a high margin. **Declared outlooks are PRIVATE per-user state**
(`set_league_preferences`, `server.py:15795`; no surface shows one member's declared outlook to
another), so narration derives from public state alone (D-6 whitelist): a declared outlook may
**raise confidence only when the public-inferred window agrees**; it never supplies the
narrated claim on its own; disagreement ⇒ the class is not narrated for that card — and the
stamp records BOTH sources, so calibration still sees the divergence. Whether declared-outlook
disclosure is ever acceptable is operator register item 14.

**Why.** Forking the window model would make the breaker disagree with the engine that built the
card (a card generated *because* the legacy vector called them a rebuilder, breaker says
contender — incoherent product). The skew (~65% rebuilder, verify A-4) is real and *correlated*
— the same wrong claim about the same manager, card after card, screenshot-able — so it is
handled by provenance discount + eligibility, not by pretending the input is clean. When the
composite graduates engine-wide, the breaker follows for free and `outlook_src` shows the seam
date in the data.

### D-9 — Evaluate the served deck only (M-5, A's D-A6)

**Decision.** `stamp_breaker` runs over the cards headed to impression logging — the
post-mutation-stack served deck (§2.3; likes-you-injected cards included, ~served-deck size,
~30) — not each arm's full ranked list (fit M3 stamps every arm's cards).

**Why.** (1) Every PLAN §6 readout joins stamps to *outcomes*, and outcomes exist only for
served cards; served rows already carry `model_arm`, so the per-arm §6.4 counterfactual works
from served stamps. (2) Cost: full-list stamping multiplies work by arms × list length for rows
with no outcome to join. (3) The narrative consumer only exists for served cards.

**Consequence.** Full-candidate-pool stamping is a **named v2 study option** — knob
`breaker_stamp_scope` in the operator register (§6.3 item 12) — not built. If v2 elects per-arm
pre-draft screening it needs in-generation evaluation anyway (different seam, own scope);
nothing in v1 is thrown away.

### D-10 — Per-seat mirroring per taxonomy §2.1; no partner-side labels

**Decision.** The breaker evaluates from the partner seat by swapping give/receive on the
existing card at evaluation time. Shape stays the user-frame label (`2x1`); mirroring is a view,
not data.

**Why.** Taxonomy §2.1 (binding): "do not mint a separate partner-side label." Aggregations stay
in one frame.

### D-11 — Seam-creep guard: nothing in generation may read breaker stamps (M-4(g))

**Decision.** An inertness test extending `test_fit_diag_inert`
(`test_trade_gen_fit.py:681`) plus a grep-guard test: no module outside the stamp site and the
two serialization/logging seams reads `card.breaker`. Any generator or reranker consulting the
stamp is silently-become-v2-without-gates — the v2 bright line (deck-composition changes need
their own scope block) is restated in the DECISIONS.md entry.

---

## 5. Cross-Cutting Concerns

### 5.1 Flag topology

| Flag | Default | Gates | Graduation (scope.md §2) |
|---|---|---|---|
| `trade.breaker` | false | import + evaluate + stamp (and the viewer-seat shadow run, operator decision 5) | scored-stamp coverage ≥99% of served impressions (rungs 0–2 objections vector; rung-marked rows reported separately, §2.6) AND degraded share (rungs 1–3) < 5% (`breaker_degraded_share_max` knob), no p95 job-time regression, calibration readout run once against the preregistered spec (D-6) |
| `trade.breaker_narrative` | false | sentence composition into the payload + client element render; **requires** `trade.breaker` (checked at the callsite; alone it does nothing). **With zero classes graduated (all `breaker_narrate_<class>` switches 0), the flag renders NOTHING — by design** (D-6) | operator TestFlight pass + A/B readout; **timing vs the live bake-off window is operator register item 9 (M-6): default DARK until the current serving round reaches its verdict** |

**Launch sequence (explicit):** (1) `trade.breaker` on → dark-stamp window; (2) shadow-based
per-class calibration readout against the preregistered spec (D-6); (3) the operator graduates
≥1 class — flips its `breaker_narrate_<class>` switch via `set_knob`; (4)
`trade.breaker_narrative` first light under **operator-only exposure**
(tester-allowlist/experiment precedent, cf. `onboarding_v2_rollout`), with the TestFlight
checklist run against the graduated class — the element renders on a narrated card; nothing
renders when `narrated` is null or suppressed; styling and testIDs pass; (5) general lighting.
If no class is graduated when the flag lights, nothing renders — by design (flag table above).

Both in `config/features.json` + `FLAG_KEYS`/`DEFAULT_FLAGS` + the release-fixture mirror +
`docs/config-reference.md`. Serving-affecting flips obey one-engine-change-per-tester-week and
go through `scripts/set_knob.py` / logged change control — a calendar shared across the
three-sibling batch (one operator, three eager plans; collision risk named in the
reconciliation log).

### 5.2 Narrative honesty, mechanically

The sentence renders from `breaker.top.evidence` ids through templates in `trade_narrative.py`
— same file, same no-LLM covenant, deterministic per (evidence, template version). Copy rules,
enforced by the honesty test: (1) claims are about the ROSTER or observable facts, never mental
states — "their roster leans rebuild," never "they don't rate your RB"; (2) hedged modality
("likely," "may balk") is part of the template contract, not styling; (3) every named
player/position/number resolves from the objection's own evidence ids (D-053 /
`trade_narrative.py:120-126` positional-honesty precedent — the sentence can never name what
the analysis didn't produce); (4) no template implies FTF has inside knowledge of that manager
("FTF data shows Mike…" is banned even where true — it advertises surveillance to the one
audience guaranteed to include Mike). Template wording is LLD/PRD territory.

### 5.3 Rollback ladder (deploy-free, outermost first — A's ladder, M-7)

1. `trade.breaker_narrative → false` (hot reload) — user-visible surface gone; stamps continue.
2. `breaker_min_severity → 1.1` (PUT /api/admin/config) — line silenced without a flag flip;
   the per-class `breaker_narrate_<class>` switches offer the same lever per class (never the
   floors — those shape top-selection and the stamp distribution, D-6/D-7).
3. `trade.breaker → false` — compute gone, module unimported, `features_json` key gone; rows
   byte-identical to pre-feature.
4. Revert commit — nothing persisted needs migration (no tables, no columns).

### 5.4 Knobs and cost model

**Knobs** (`model_config`, family sketch — exact list and defaults are LLD territory):
`breaker_min_severity` (narrative bar) · `breaker_narrate_<class>` per class (narration
eligibility switch, default 0 — with `breaker_min_severity`, the user-visible-effect knobs in
v1; D-6) · `breaker_ms_budget` · `breaker_budget_checkpoint_frac` (the §2.6 pass-2 checkpoint) ·
`breaker_degraded_share_max` (graduation criterion, default 0.05) · `breaker_floor_<class>` per
class · `breaker_max_repeat_frac` · outlook-provenance haircut. **Every key follows the five-registration rule** — all five
registrations in the consumer's commit (`trade_service._DEFAULT_CFG`,
`database._MODEL_CONFIG_DEFAULTS`, golden-test pin, scope disposition sentence,
`docs/config-reference.md`; discipline documented at `trade_service.py:895-916`), each with a
documented disable value (floors/severity → 1.1 disables a class or the line; budget → 0
disables evaluation).

**Cost** (NFR-2 backing): 12-team league, ~30 served cards. PartnerContext: only partners in
the deck (typically ≤10), each `analyze_roster_strengths` + `infer_team_outlook` over data the
job already loaded — ≤1 ms/partner. Per-card: predicates over prebuilt context; dominated by
`package_value_v2` / `_feasible_after`; `fit_diag` reuse (D-3) removes value-scoring cost on
bake-off decks. Envelope: ~10–100 ms/deck expected vs a 250 ms budget vs a 60,000 ms timeout.
The viewer-seat shadow run (operator decision 5) is ≤2× per-card cost inside the same budget.
The ladder (§2.6) exists for pathological leagues, and the pre-flag dry-run ms number (fit W0
precedent) is the operator's evidence before flag-on.

### 5.5 Observability — knowing the stamps are missing

- Per-job diagnostics block (FitReport precedent): cards seen / stamped / degraded-by-rung /
  narrated / suppressed, class-fire histogram, p50/p95 ms — no new tables.
- **Coverage tripwire** (M4 precedent): share of served impressions WITHOUT a scored objections
  vector (rungs 0–2), cut by rung marker (§2.6 — bare null never exists; absent key = flag-off
  only); alert thresholds = the graduation criteria inverted (scored coverage ≥99%, degraded
  share rungs 1–3 < `breaker_degraded_share_max`). Fail-open is thereby self-surfacing (NFR-6).
- **Class-entropy monitor** (D-7): weekly entropy over `top.code`; the calibration readout
  reports per-class precision *and* fire rate, never aggregate accuracy alone.
- **Exposure predicate and narration readout:** exposure := `narrated != null` AND platform =
  mobile (the v1 element exists only in `mobile/src/components/TradeCard.tsx`; web/extension
  ignore the key). The narration readout has three cells: narrated / suppressed
  (reason-enumerated: `repetition | below_floor | class_ineligible | format_gap`) /
  no-objection.
- Version discipline: calibration readouts filter on `ver` alone; narration A/B readouts on the
  (`ver`, `tmpl_ver`) pair (§3.1); cross-version comparison
  refuses (fit M2 precedent). Knob flips via `set_knob.py` only, so `model_config_changes`
  censors windows (M1 rail).
- Data boundaries restated verbatim from PLAN §6 in the readout spec: ghost rows ended
  2026-08-21 (A-1 CLOSED via the Receipts session's prod read of `model_config_changes`); D-091
  phantom-pick window excluded; and the same table logged `qb_1qb_cap_elo` 1785→1644 /
  `qb_1qb_cap_knee_elo` 1580→1200 @04:46Z — **1QB QB prices drop sharply at the next value
  refresh, so value-optics objections must never treat pre-boundary QB values as comparable
  across that seam.**

### 5.6 Trust boundary and privacy (the section that must survive review)

Two exposures share one property — the harmed party can't see the harm:

- **Private-state disclosure.** `asset_preferences` rows and personal boards are entered by a
  user in their own app with no notice that league-mates might see derived output. The D-6
  whitelist makes the leak structurally impossible in copy while the dark stamp keeps the
  measurement. If the operator wants these classes user-facing in v2, that is a consent/product
  decision (e.g. surfacing only what the counterparty posted to a public trade block via
  `trade_block_service` — genuinely public), never a template edit.
- **Assertions about a person.** The §5.2 copy rules bound tone and claim type; the residual
  cross-seat risk — two users comparing screens see A's card hedge about B while B's mirrored
  card is enthusiastic — is carried as its own HIGH risk-register row (R-6: live the day
  `trade.breaker_narrative` lights), bounded rather than dismissed: both statements are
  roster-fact-grounded and hedged, so they read as two perspectives, not a contradiction of
  fact, and §2.7's mirrored predicates + coherence test keep factual claims consistent.
- The breaker never causes output in the counterparty's app, never notifies, never persists
  per-person conclusions beyond the stamp.

### 5.7 Cross-references (M-8)

- **Shared taxonomy:** `docs/plans/shared/trade-shape-taxonomy.md` — seeded by the Receipts
  session (first mover) in its worktree; **not yet present in this worktree** (verified —
  `docs/plans/shared/` does not exist here). Cited here by its eventual home path; adopted
  verbatim on merge; this plan contributes the objection-vocabulary section (anchor codes +
  `roster_crunch` + producer column) via PR to that file (taxonomy v1.1.0, three-way signed).
- **Fit-challenger precedents:** LLD §3.2 (the M3 stamp site this rail extends), §3.3
  (`_log_deck_signal_impressions` features keys), §3.4 (`trade_card_to_dict` additive
  serialization), §4 (five-registration knob rule) —
  [../fit-challenger/LLD.md](../fit-challenger/LLD.md).
- **Negmem research memo:** `docs/plans/negative-results-memory/research-verification.md`
  (vigilant-spence branch) — the `acceptance_prior`-is-unfed finding and the catalog of every
  existing rejection consumer, cited wholesale rather than re-derived.
- **PLAN data boundaries:** A-1 CLOSED (interleave live, ghosts ended 2026-08-21); QB repricing
  comparability note (§5.5); A-2 (Receipts RESERVED-seams contract text) still pending —
  reconcile before operator delivery.

### 5.8 Docs & evidence deltas (scope.md §3/§4 restated as owners)

`docs/api-reference.md` (`trade_card_to_dict` additive object) · `docs/architecture.md` +
`living-memory/HLD.md` (evaluation-layer row/line) · `living-memory/LLD.md` (vocabulary
convention + uniform-keys stamp) · `docs/glossary.md` ("breaker", "objection", "hesitation
line") · `docs/config-reference.md` (flags + knobs) · DECISIONS.md entry (D-1/D-2 vocabulary +
D-9 stamp-scope + the v2 bright line) · `docs/cross-client-invariants.md` row filled "n/a in v1"
(server-composed sentence; no client switches on codes). Evidence:
`backend/tests/test_trade_breaker.py` per scope.md §3 (determinism, vocabulary closure incl.
producer-column enforcement, per-class predicates on fixture rosters, flag-off byte-identity,
interleave inertness both draft paths, exception sabotage, budget-ladder labeling, co-owner and
format-envelope fixtures, repetition suppression, stamp uniformity, shadow-serialization guard,
narrative honesty + whitelist, cross-seat coherence, binding sabotage) + the structural guard
`mobile/tests/check-breaker-card.js` + code-walk proof of both seams at build time + TestFlight
checklist before the narrative flag lights. Exact test list is LLD territory.

---

## 6. Risks & Open Questions

### 6.1 Risk register (ranked; renumbered clean after the M-2/M-3 rulings, and again in round 3
— the cross-seat story-mismatch row was restored as R-6 and the former R-6..R-12 shifted to
R-7..R-13; no rows were merged to preserve a count)

Severity = product damage × likelihood-as-designed-without-the-mitigation.

| # | Sev | Risk | Mechanism | Disposition |
|---|---|---|---|---|
| R-1 | Critical | **Private-preference leak to a negotiation adversary** | `other_player_keep` / board-basis `value_giving` / `roster_crunch`-forced-drop evidence render another user's private lists/board; no retraction possible | **Designed away in v1** by the D-6 whitelist (stamp dark, never render). Residual = v2 pressure to render the most persuasive objection; operator register item 8 (dark-only acceptance + the generic-form question) |
| R-2 | Critical | **Systematically wrong window objections at scale** | Legacy-vector skew (~65% rebuilder, A-4) feeds the marquee class; wrongness is correlated per manager, screenshot-able | D-8 (inherit + `outlook_src` + haircut + narration margin bar > stamp bar) + D-6 maturity gate + calibration cut by source. Residual = declared-but-stale windows; operator register item 11 |
| R-3 | High | **Calibration theater** | Counterparty-seat cut n≈0 (96.3% one-directional × 84.5% unboarded); 40% majority-class baseline flatters aggregate match-rate | D-6 preregistered per-class baselines + minimum-n gates, pinned in the **calibration-readout spec committed before `trade.breaker` first lights** (D-6 — per-class minimum n, margins over both baselines, `outlook_src` × board-basis stratification); §6.2b labeled as proxy with selection caveat; §2.7 cross-seat check as population-independent third signal |
| R-4 | High | **Dominant-objection collapse / wallpaper** | Consensus-basis `value_giving` fires near-tautologically (86.3% viewer-receives-more) → banner blindness + useless stamp distribution | D-7: per-class floors (consensus floor high), repetition suppression, entropy red line before narrative graduation |
| R-5 | High | **Wrong counterparty state — input-wrongness family** | Co-owner identity split; G-045 pruned partners; G-026 IDP/K zero-values; 12-team `_POS_TIER_CUTS` assumption; stale/clone boards | §3.2/§3.4/§3.5 degrade-and-mark table is normative: every input has a degrade path and a stamp marker; F-3 `board_auth` heuristic; fixtures required. Residual: board staleness recoverability (Q-2) |
| R-6 | High | **Cross-seat story mismatch — LIVE the day `trade.breaker_narrative` lights** | User A's card damns a trade whose mirror user B's app served approvingly (or B's own deck carries the mirror with no hesitation); two league-mates compare screens | §2.7 mirrored predicates + cross-seat coherence test keep factual claims consistent; §5.2 copy rules keep both statements hedged and roster-fact-grounded (two perspectives, not a contradiction of fact); D-6 per-class switches bound exposure per class. Residual accepted; **named monitor**: a mirrored-serve narration-divergence count (cards whose mirror was served to the counterparty within the A-5 window and whose narration verdicts differ) rides the per-job diagnostics (§5.5), re-read at the A-5 re-measure cadence |
| R-7 | Med | **Latency on the widened (organic-included) path** | Per-card feasibility × every deck job can bias stamps by rank if truncated naively | §2.2 amortization + §2.6 labeled ladder (deck-uniform pass-2 drop) + p95 gate as graduation criterion + pre-flag dry-run ms number |
| R-8 | Med | **Ordering/serving contamination** | Accidental reorder (in-place sort in a predicate); conditionally-present key dropped by executemany | Byte-level inertness tests both draft paths; attribute-only stamp; uniform-keys extension (§3.3) |
| R-9 | Med | **Version-skew corruption of the readout** | Predicate/floor/template change mid-window = two experiments summed | `ver` bumps on ANY predicate/threshold/evidence-shape change; `tmpl_ver` on any template change, stamped alongside (§3.1); calibration keys on `ver`, narration A/B on the (`ver`, `tmpl_ver`) pair; readout refuses cross-version; M1 censoring |
| R-10 | Med | **Measurement inheritance traps** | Ghost boundary, D-091 window, QB repricing seam, sibling flip collisions | §5.5 boundaries restated in the readout spec; shared change-control calendar across the three-sibling batch |
| R-11 | Low | **Seam creep: generation reads breaker stamps** | One tempting line silently becomes v2 without gates | D-11 inertness + grep-guard tests; bright line restated in DECISIONS.md |
| R-12 | Low | **Sibling taxonomy drift** | Extension PR pends while negmem records in a divergent private vocabulary | Producer-column convention already reserved; the extension PR is a deliverable of THIS thread (before PRD); A-2 reconciliation before operator delivery |
| R-13 | Low | **Latent `_opponent_frame` contradiction** | A second they-sentence writer exists if `narrative` ever renders (`_opponent_frame`, `trade_narrative.py:86-100` — nothing renders it today) | LATENT — this row covers ONLY the `_opponent_frame` half (the live cross-seat half is R-6); single-composition-owner convention + the §2.4 characterization test |

### 6.2 Assumptions to verify at build (extends PLAN §10)

- **A-3 (updated round 3):** breaker insertion at the post-mutation-stack seam — after the F9
  block, before `served_final = final_cards` at `server.py:6034` (mutation stack this checkout:
  F7 split `:5723-5725`, likes-you `:5747`, F3 `:5794`, `_order_deck` `:5900`, F7 wildcard
  `:5937`, F9 `:5997`); M3 stamp block at `server.py:5698-5716`;
  `_log_deck_signal_impressions` def `server.py:4020` / features site `:4205` (fit-keys guard
  `:4193`) / call site `:6101`; `trade_card_to_dict` at `server.py:10976` / fit block `:11060`;
  snapshot-republish sites per flag combination — re-cite ALL at LLD-build time, drift
  expected.
- **A-4:** the ~65%-rebuilder legacy-outlook skew — re-derive from current data before setting
  `fit_outlook` haircuts.
- **A-5:** mirrored-card served-both-directions rate (~3.7% implied) — measure before promising
  the §6.2a cut a timeline.
- **A-6:** whether board last-ranked-at is recoverable for staleness handling (Q-2).
- **A-2 (inherited, still open):** Receipts RESERVED-seams contract text.

### 6.3 Operator decision register additions (extend PLAN §9 — items 1–7b stand unchanged)

| # | Decision | Default if unanswered |
|---|---|---|
| 8 | Evidence whitelist (D-6): private counterparty state (`asset_preferences`, board contents) stamps dark and never renders in v1 — accepted? And may even a *generic* form ("unlikely to move him") ever render, given it still discloses list membership? | dark-only; generic form does NOT render |
| 9 | Narrative-flip timing vs the live interleaved bake-off window (M-6). Draft A's position: the line is outcome-shift, not order/composition — outside `bypass_rerankers`' letter; light it and annotate the readout per arm. Draft B's position: wait — mid-window narration contaminates arm comparison via objection-mix asymmetry | `trade.breaker_narrative` stays DARK until the current serving round reaches its verdict; lighting mid-window requires the operator to accept an annotated readout |
| 10 | Per-deck repetition suppression (D-7): same card, different decks, different narration — acceptable? | yes, with `suppressed` stamped |
| 11 | Inferred-window `fit_outlook` narration: wait for the composite's engine-wide graduation, or ship behind the high-margin bar (D-8)? | high-margin bar; a declared outlook raises confidence only where the public-inferred window agrees (D-8), never narrates alone |
| 12 | `breaker_stamp_scope` (v2 study option, M-5): full-candidate-pool stamping for within-pool questions | served-deck-only; not built in v1 |
| 13 | Organic them-score coverage via promoting the fit stamp to organic decks (D-3 consequence) — a **fit-challenger plan** scope question, registered here for visibility | `breaker.them` null on organic decks |
| 14 | Declared-outlook disclosure (D-8): `team_outlook` declared via `set_league_preferences` (`server.py:15795`) is PRIVATE per-user state — no surface shows one member's declared outlook to another. Is narrating from it (rather than confidence-raising on public-inferred agreement) ever acceptable? | never in v1 — declared outlook is confidence-only on agreement; disagreement ⇒ class not narrated; the stamp records both sources |

### 6.4 Deferred to the LLD (explicitly)

Exact predicate math per class · the knob list with defaults and disable values · the full test
list (§5.8 names the families) · exact payload field types (§3.1 is a sketch) · hesitation
template wording · evidence-key enums per code · the format-envelope enumeration · the
`PartnerContext` field list and cache keying · the exact `final_cards` binding per execution
path · the snapshot-republish mechanics per flag combination (§2.3) · the calibration-readout
spec's numbers (the spec itself — an LLD section or standalone doc here — is committed before
`trade.breaker` first lights, D-6).

---

*End of merged HLD. Reconciliation provenance: structure and seam mechanics from draft A;
risk architecture (whitelist, maturity ladder, provenance haircuts, anti-wallpaper, degradation
ladder, degrade-and-mark inputs, seam-creep guard) from draft B, folded in as design under
merge rulings M-1..M-8; `shape_aversion` removed everywhere per M-2; narrative mechanics
corrected per M-3.*
