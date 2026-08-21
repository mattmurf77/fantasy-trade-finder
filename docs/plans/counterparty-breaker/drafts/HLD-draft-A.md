# HLD — Counterparty breaker (Draft A: Architecture-Coherence lens)

**Date:** 2026-08-21 · **Status:** DRAFT A for dual-agent cross-critique.
**Binds under:** [PLAN.md](../PLAN.md) + [scope.md](../scope.md); the LLD binds tighter than this doc.
**Author lens:** coherent, minimal, shippable. Every seam below reuses an existing precedent or
names the precedent it deliberately departs from. Line numbers cite this worktree
(`claude/trading-engine-eval` base, 2026-08-21) and are re-cite-at-build per PLAN A-3.

---

## 1. Context & Goals

### 1.1 What v1 is

A deterministic **evaluation layer** — `backend/trade_breaker.py` — that runs after ranking and
before impression logging, predicts the counterparty's most likely decline reason for every served
card, stamps it (`features_json.breaker`), and (second flag) renders the top objection as one
deterministic sentence on the card. The organizing idea, verbatim from the PLAN: **the breaker
predicts the counterparty's decline reason, in the vocabulary the app already uses to record
decline reasons** (`trade_pass_reasons` layer-2 codes, `backend/database.py:5579-5583`).

v1 is *measurement plus copy*. It kills nothing, reorders nothing, filters nothing.

### 1.2 Goals

| # | Goal | How this HLD delivers it |
|---|---|---|
| G-A | Every served card carries a coded, evidenced objection prediction | §3 stamp, M3-rail precedent |
| G-B | Calibration is a join, not new instrumentation | objection codes ≡ pass-reason codes (§4 D-A1) |
| G-C | The card can tell the user what to preempt in their pitch | hesitation line via `trade_narrative` templates (§2.4) |
| G-D | The v2 filter decision is made from data, not taste | §6.4-of-PLAN counterfactual computable from stamps alone |
| G-E | Sibling coherence | taxonomy §2.1 mirroring, §2.8 magnitude rule, `breaker_` prefix reserved-unused |

### 1.3 Non-functional requirements (binding)

- **NFR-1 — zero ordering effect in v1.** Deck order and deck composition are byte-identical with
  `trade.breaker` on vs off, on organic and bake-off decks alike. Mechanism, not policy: the
  breaker runs *after* the served deck is fixed and mutates only a new card attribute plus (flag 2)
  the `narrative` string. Enforced by a `test_fit_diag_inert`-pattern test (delete the attribute,
  assert served deck identical) plus an order-capture test on interleaved decks
  (`bakeoff_runner.bypass_rerankers` discipline).
- **NFR-2 — per-deck ms budget.** The trade job has a 60s hard timeout; the breaker must be noise
  inside it. Budget: `breaker_ms_budget` (model_config, proposed default **250 ms per deck**,
  p95 target well under; §5.4 shows the expected cost is ~1–2 orders of magnitude below the
  budget). On budget breach: stop evaluating remaining cards, stamp `null` for the unevaluated
  tail, log a warning, never fail the job. Fail-open everywhere: any per-card exception stamps
  `null` for that card (fit_diag per-card try/except precedent, `trade_gen_fit.stamp_fit_diag`).
- **NFR-3 — flag-off byte identity.** `trade.breaker` off ⇒ the module is never imported
  (lazy import at the stamp site; `test_organic_never_imports_fit` precedent) and
  `features_json` carries no `breaker` key at all.
- **NFR-4 — determinism.** Same inputs ⇒ same objections, severities, sentence. No LLM, no RNG,
  no wall-clock dependence beyond player age already baked into inputs.
- **NFR-5 — no new tables, no new routes, no new client code** in v1 (scope.md §2; the
  `breaker_` table prefix stays reserved and unused).

### 1.4 Explicit non-goals (v1)

Filtering/demoting/reordering (v2, own scope block) · learning anything (negmem's tense) ·
retrospective scoring (Receipts' tense) · reading `negmem_*` tables · any client rendering change
beyond the existing server-composed `narrative` string · touching G6 (stays user-seat, D-062).

---

## 2. Architecture Overview

### 2.1 Where the breaker sits

```
generator arms (current / challenger / gen_v2 / fit  — or organic generate_trades)
        │
        ▼
ranking + (bake-off) interleaved draft            ← untouched
        │
        ▼  served deck is now FIXED
┌─────────────────────────────────────────────┐
│  EVALUATION LAYER (new, this feature)       │
│  trade_breaker.evaluate_deck(...)           │   flag trade.breaker
│    → card.breaker attribute (per card)      │   attribute-only, fail-open
│  trade_narrative.hesitation_line(...)       │   flag trade.breaker_narrative
│    → one sentence appended to card.narrative│   text-only, order untouched
└─────────────────────────────────────────────┘
        │
        ▼
_log_deck_signal_impressions  (server.py:4020)    ← copies card.breaker into
        │                                            features_json.breaker (uniform keys)
        ▼
serving (trade_card_to_dict → client)             ← additive `breaker` object, clients
                                                     ignore unknown keys
```

This is the PLAN's "checker node" translation made literal: a validation/evaluation stage between
parallel producers and downstream consumption, with the v1 twist that it *annotates* instead of
*vetoing* (the veto is v2's separately-gated question).

### 2.2 Component responsibilities

| Component | Responsibility | Explicitly NOT its job |
|---|---|---|
| `backend/trade_breaker.py` (new, ~leaf) | Build per-partner context once per job; evaluate each served card from the partner's seat; return `{ver, top, objections, ms}`; expose `stamp_breaker(cards, ...)` mirroring `stamp_fit_diag`'s shape | Ordering, filtering, DB writes, HTTP, importing `server.py` or `trade_gen_fit` |
| `backend/trade_narrative.py` (edit) | New pure template function `hesitation_line(objection, players) -> str \| None` — deterministic, D-053-honest (renders only fields present in `objection["evidence"]`) | Deciding *whether* to render (threshold + flag live at the callsite); LLM anything |
| `server.py _run_trade_job` (edit) | One guarded block after the served deck is fixed: lazy-import, call `stamp_breaker`, and (flag 2) append the hesitation line | Any breaker math |
| `server.py _log_deck_signal_impressions` (edit) | One unconditional-when-flag-on line: `features["breaker"] = getattr(card, "breaker", None)` inside the flag guard | Recomputing anything at log time |
| `server.py trade_card_to_dict` (edit) | Additive optional `breaker` object (code, severity, sentence) — fit precedent (`d["fit"]`) | — |
| `trade_service.py` / `database.py` (edit) | Knob registrations only (five-registration rule) | Any behavior change |

**Import discipline.** `trade_breaker` imports `trade_service as ts` (module import, T1 discipline
from `trade_gen_fit.py:35`) for value helpers (`elo_to_value`, `package_value_v2`, `_c`,
`is_pick_asset`, `analyze_roster_strengths`, `infer_team_outlook`), and `trade_optimizer as topt`
for lineup feasibility. It **never** imports `trade_gen_fit` — that module's organic-isolation
contract ("imported by exactly one production caller, `bakeoff_runner.gen_fit_cards`",
`trade_gen_fit.py:22-23`) stays intact; where the breaker wants the them-lens number it *reads the
`fit_diag` stamp* already on the card (§4 D-A2) rather than importing the scorer.
`trade_service` never imports `trade_breaker` (mirror of the fit rule); the only production caller
is the `server.py` stamp site.

### 2.3 The hook in `server._run_trade_job`

Insertion point: **immediately after the fit M3 stamp block** (`server.py:5702-5717` in this
worktree — after the bake-off if/else closes and `stamp_fit_diag` has run, before the F7
exploration block). Rationale for this exact seam:

1. The served deck is fixed here — post-ranking by construction (fit-challenger LLD §3.2
   established this as the post-ranking evaluation site; the breaker is the second tenant of the
   same rail).
2. `fit_diag` is already stamped when the deck is a bake-off deck, so the breaker can read it
   (D-A2) instead of rescoring.
3. Everything the breaker reads is in scope: `g_league` (members, rosters, boards),
   `players_dict`, `seed_map`, `active_format`, the served card list.

One structural difference from the fit stamp: `stamp_fit_diag` is inside
`if bakeoff_run is not None:` — the breaker block is guarded by **`flags.trade_breaker`** instead,
because the PLAN requires stamps on organic AND bake-off decks (calibration cut 6.2b needs organic
coverage). Second difference: the breaker evaluates the **served deck only** (the cards that will
reach `_log_deck_signal_impressions`), not every arm's full candidate list — see §4 D-A6 for why.

Sketch (LLD owns the exact code):

```python
# breaker (v1) — evaluate + stamp + (flag 2) narrate. Post-ranking,
# attribute/text-only, fail-open, zero ordering effect (test-enforced).
if flags.trade_breaker:
    try:
        from backend.trade_breaker import stamp_breaker   # lazy — flag-off
        stamp_breaker(final_cards, league=g_league,        # never imports
                      players=players_dict, seed_elo=seed_map,
                      scoring_format=active_format)
        if flags.trade_breaker_narrative:
            from backend.trade_narrative import hesitation_line
            for c in final_cards:
                line = _breaker_line(c, players_dict)      # threshold check + compose
                if line:
                    c.narrative = f"{c.narrative} {line}".strip()
    except Exception as bk_err:
        log.warning("breaker stamp failed (non-fatal): %s", bk_err)
```

(`final_cards` here stands for whichever list feeds impression logging on the executed path —
organic `generate_trades` output or the interleaved served deck; the LLD pins the exact variable
per path, PLAN A-3.)

### 2.4 The narrative hook

`trade_narrative.py` is 168 lines of pure template functions and stays that way. It gains
`hesitation_line(objection: dict, players: dict) -> str | None`: a per-code template table keyed by
objection code, rendering **only** values present in `objection["evidence"]` (player names,
positions, ages, counts). Returns `None` for codes with no template or missing evidence — silence
over invention, the D-053 rule `build_narrative` already follows (see its comment block at
`trade_narrative.py:120-126`).

`build_narrative` itself is **not** modified. Reasons this is the coherent call, since the scaffold
question is real (the PLAN says "narrative hook in `trade_narrative.build_narrative`"):

- `build_narrative` runs at **generation time** inside each generator
  (`trade_service.py:4143`, `:5199`) — before ranking, before the draft, on thousands of
  candidates that will never be served. The breaker result does not exist yet at that point, and
  producing it there would drag the evaluation layer into generation (violating the layer boundary
  and the cost budget) or force a re-narration pass anyway.
- Appending one sentence post-ranking to the ~30 served cards is the minimal change that keeps the
  PLAN's default ("inside the existing `narrative` string, zero client change") true.
- The *templates* still live in `trade_narrative.py`, so all narrative copy has one home, one
  snapshot-test suite, one honesty rule.

The composed card therefore reads: `build_narrative`'s ≤2 sentences + at most 1 hesitation
sentence (≤3 total). The hesitation sentence renders only when `trade.breaker_narrative` is on AND
`top.severity ≥ breaker_min_severity` AND the code has a template.

**Coherence guard (LLD must pin):** `build_narrative`'s sentence 2 can already be
`_opponent_frame` — "They're rebuilding — the youth going back fits their timeline"
(`trade_narrative.py:86-100`). That fires only when the give-side lean *fits* the partner window;
breaker `fit_outlook` fires only when the package *pushes against* it. Same outlook input, opposite
lean thresholds — they cannot both fire truthfully, but the LLD owes a test that the pair is
mutually exclusive under one shared lean computation, so the card never says "fits their timeline"
and "against their window" in the same breath.

### 2.5 What the breaker reads (all existing; PLAN §5 restated as interfaces)

Per partner, built **once per job** into a `PartnerContext` (dataclass, cached by
`target_user_id`):

| Input | Source | Notes |
|---|---|---|
| Roster ids | `g_league.members[*].roster` | |
| Board | `LeagueMember.elo_ratings` | RAW, never shrunk — fit-challenger T3 provenance rule binds (`trade_gen_fit.py:5-11`) |
| Depth profile | `ts.analyze_roster_strengths(...)` (`trade_service.py:2211`) | `position_needs` / `position_surplus` / `tier_depth`, partner seat |
| Window | declared `league_preferences` outlook, else `ts.infer_team_outlook(...)` (`trade_service.py:3084`) | inherits whatever the engine serves (INV-372b: legacy vector today) |
| Asset prefs | `asset_preferences`, partner side | untouchable / not-interested |
| Lineup feasibility | `topt._feasible_after` shape | mirrored R5 |
| Depth chart | `depth_chart_order` (#366) | evidence only |
| League settings | format, starter slots, roster size | |

Explicitly NOT read: LLM, new feeds, `negmem_*`, ghost rows (PLAN §5).

---

## 3. Data Model & Flow

### 3.1 The breaker result (rides the card, then `features_json`)

```jsonc
// card.breaker — set by stamp_breaker; None when unscorable
{
  "ver": "breaker-1",                    // BREAKER_VERSION; SCORER_VERSION precedent:
                                         // bump on any predicate/severity/template change;
                                         // readouts refuse to mix versions
  "top": {                               // argmax severity above its per-class floor;
    "code": "fit_outlook",               // null when nothing clears a floor
    "severity": 0.82,
    "evidence": {"outlook": "rebuilder", "asset": "p_4046", "age": 29, "pos": "RB"}
  },
  "objections": [                        // ALL v1 classes, evaluated + scored, sorted
    {"code": "fit_outlook",   "severity": 0.82, "evidence": {...}},
    {"code": "roster_crunch", "severity": 0.31, "evidence": {...}},
    ...                                  // classes below floor still listed (severity
  ],                                     // recorded) — the counterfactual needs the
                                         // full vector, not just the winner
  "them": 41.3,                          // §2.8 magnitude: fit_diag them-score when the
                                         // stamp exists on this card, else null in v1
                                         // (never a rescored parallel number — D-A2)
  "narrated": false,                     // true iff a hesitation line was appended
  "ms": 4.1                              // per-card evaluation ms
}
```

Shape rules:

- **Codes are a closed set**: the 9 shipped `trade_pass_reasons` layer-2 codes
  (`database.py:5579-5583`) plus taxonomy-registered extensions (`shape_aversion`,
  `roster_crunch`). A vocabulary-closure test asserts every emitted code ∈ the shared taxonomy
  set (scope.md §3).
- **Evidence keys are per-code and enumerated in the LLD**; `hesitation_line` may render only
  those keys (D-053 mechanically).
- **Severity is per-class 0–1** from existing margins (their-board deltas, surplus/needs margins,
  outlook score margin, feasibility slack) — no new value model, no cross-class aggregate
  (§4 D-A5).

### 3.2 Stamp into `features_json.breaker` — uniform keys

In `_log_deck_signal_impressions` (`server.py:4020`), inside the features assembly, one line
guarded by the flag:

```python
if flags.trade_breaker:
    features["breaker"] = getattr(card, "breaker", None)   # null when unscored —
                                                           # key on EVERY row, absence
                                                           # impossible (M4 pattern)
```

- Rides **inside** `features_json` (one column), so the `save_deck_impressions` executemany
  first-row-keys trap (`database.py:5503`; row dicts must share keys or non-first-row keys are
  silently dropped) *cannot* bite — exactly the fit-challenger §3.3 reasoning. The uniform-keys
  rule still applies at the JSON level: key present (possibly null) on every row of a flag-on
  deck, extending `test_impressions_uniform_columns`.
- Flag off ⇒ no key ⇒ rows byte-identical to today (NFR-3).
- No new columns, no new tables. If v2 ever needs queryable columns or `breaker_` tables, that is
  v2's scope block.

### 3.3 Serialization to clients

`trade_card_to_dict` gains an additive optional block (fit precedent, fit-challenger LLD §3.4):

```python
_bk = getattr(card, "breaker", None)
if _bk is not None and _bk.get("top"):
    d["breaker"] = {"code": ..., "severity": ..., "sentence": ...}   # additive; clients
                                                                     # ignore unknown keys
```

Serve the *distilled* object (top code + severity + composed sentence), not the full objection
vector — clients need nothing more in v1, and the full vector stays server-side in
`features_json` for measurement. The hesitation sentence also already rides inside `narrative`
(zero-client-change default); the structured key exists so a future client element (operator
decision #3) needs no server change. `docs/api-reference.md` row per scope.md §4.

### 3.4 End-to-end flow (one job)

1. Job starts (`_run_trade_job`, `server.py:5412`); generation + ranking (+ bake-off draft) run
   exactly as today.
2. Served deck fixed. Fit M3 stamp runs (bake-off decks).
3. `trade.breaker` on → `stamp_breaker`: build ≤(N−1) `PartnerContext`s lazily (only partners
   actually appearing in the deck), evaluate each card from the partner seat (taxonomy §2.1
   mirroring: swap give/receive; the user's `2x1` is the partner's `1x2` — no new labels), set
   `card.breaker`.
4. `trade.breaker_narrative` on → threshold check per card → `hesitation_line` → append to
   `card.narrative`, set `breaker.narrated = true`.
5. `_log_deck_signal_impressions` freezes `features_json.breaker` per row.
6. `trade_card_to_dict` serves the additive object.
7. Outcomes accrue in `deck_outcomes` / `trade_pass_reasons` exactly as today; every PLAN §6
   readout is a SQL join over stamps + outcomes. No breaker-specific write path exists.

---

## 4. Key Design Decisions (mini-ADRs)

### D-A1 — Objection vocabulary = `trade_pass_reasons` anchor + registered extensions

**Decision.** Objection codes are the shipped layer-2 pass-reason codes, extended only by
`shape_aversion` and `roster_crunch`, registered in the shared taxonomy
(`docs/plans/shared/trade-shape-taxonomy.md`, objection-vocabulary section contributed by this
plan; changes only by PR to that file, pending operator decision #7).

**Why.** (1) Calibration becomes a join against ~200+ existing coded rows — G-B with zero new
instrumentation. (2) One vocabulary, two tenses, with negmem (their hard constraint: extensions
extend the shipped taxonomy, never parallel it). (3) The codes are already product-validated as
"reasons managers actually give."

**Alternative rejected.** A bespoke objection ontology (richer, e.g. "age curve", "positional
scarcity") — unfalsifiable against filed reasons, a third vocabulary for siblings to reconcile,
and a standing invitation to drift.

**Consequence.** Some real objections compress into coarse codes (e.g. "hates 3-for-1s" →
`shape_aversion`). Accepted: coarse-but-joinable beats rich-but-orphaned; v2 can subdivide with
data in hand.

### D-A2 — Reuse the fit them-lens; never rescore where a stamp exists

**Decision.** For value-class objections (`value_giving`) and the overall magnitude, the breaker
reads `card.fit_diag` (them score + lenses, stamped on every bake-off card by
`stamp_fit_diag`, `trade_gen_fit.py:~857`) when present. Only on cards without the stamp (organic
decks) does the breaker compute the partner-seat consensus surplus itself — via `ts` helpers
(`elo_to_value`, `package_value_v2` — the live-formula path `trade_service.py:~4780`), never by
importing `trade_gen_fit`.

**Why.** (1) Taxonomy §2.8 is explicit: extend the them-score, don't mint a parallel
partner-liking scale. (2) Two scorers of "how much they like it" *will* disagree eventually, and
the discrepancy would be an unfalsifiable bug farm. (3) Preserves `trade_gen_fit`'s
one-production-caller organic-isolation contract untouched.

**Consequence.** `breaker.them` is null on organic decks in v1 (the value-objection *severity*
still computes from the breaker's own consensus-surplus margin — a per-class number, not a
0–100 liking score). If organic them-scores become load-bearing, the right move is promoting the
fit stamp to organic decks (a fit-challenger scope question), not duplicating the scorer here.

### D-A3 — v1 is stamp + narrative only; zero ordering effect (interleave discipline)

**Decision.** No filter, no demote, no reorder, anywhere, under any flag this plan ships.
Mechanically: the breaker runs after the served deck is fixed and is attribute/text-only;
inertness is test-enforced both ways (attribute deleted ⇒ deck identical; flag off ⇒ rows
byte-identical).

**Why.** The interleaved bake-off is live; `bypass_rerankers` is the standing rule (matchmaking
HANDOVER trap 5) — a post-generation filter would make the bake-off measure deck position, not
model quality. And D-067 (*accuracy, not volume*): the filter must first earn its existence from
the §6.4 counterfactual readout, which the stamp alone can compute.

**Alternative rejected.** Per-arm pre-draft screening (v2 option (a)) — clean w.r.t. the
interleaver but touches every generator arm and changes deck composition, which is the bright
line requiring its own scope block. Deliberately deferred, not designed here.

### D-A4 — Deterministic templates, no LLM

**Decision.** `hesitation_line` is a per-code template table in `trade_narrative.py`, same
zero-cost/snapshot-testable regime as the module's docstring promises (`trade_narrative.py:1-7`).
LLM involvement is an explicit operator decision that does not exist in this plan.

**Why.** Operator constraint (PLAN §0, §7); D-053 honesty is mechanically checkable for
templates (render-only-evidence rule) and not for generated prose; per-card LLM cost at deck
scale is unjustifiable for one sentence.

### D-A5 — Severity is per-class; overall magnitude stays the fit them-score

**Decision.** Each objection class scores 0–1 from its own existing margins. There is **no**
breaker-owned aggregate "acceptance score"; the only whole-card partner-liking magnitude the
system carries is the fit arm's them-score (surfaced as `breaker.them` when stamped). `top` is
argmax over per-class severities above per-class floors — a selection, not a sum.

**Why.** Taxonomy §2.8 (binding). Cross-class severities are not commensurable ("0.8 outlook
clash" vs "0.8 overpay" claim different things); summing them would be a second acceptance model
competing with both the fit them-score and `acceptance_prior` (`trade_gen_v2.py:283`) — three
partner-propensity numbers with three semantics is precisely the incoherence this feature's
sibling contract exists to prevent.

**Consequence.** Cross-class argmax does compare severities ordinally at the floor boundary. The
LLD owes per-class floor knobs (`breaker_floor_*` family) so calibration can re-level classes
without code changes; the calibration readout (predicted-top vs filed-reason match rate, per
class) is the empirical check on the ordinal comparison.

### D-A6 — Evaluate the served deck only, not every arm's candidate list

**Decision.** `stamp_breaker` runs over the cards headed to impression logging (~deck size,
~30), not over each arm's full ranked list (fit M3 stamps every card of every arm's list).

**Why.** (1) Every PLAN §6 readout — coverage, calibration, narrative A/B, filter counterfactual
— joins stamps to *outcomes*, and outcomes exist only for served cards; served rows already carry
`model_arm`, so the per-arm counterfactual cut works from served stamps. (2) Cost: full-list
stamping multiplies work by arms × list length for rows with no outcome to join. (3) The narrative
consumer only exists for served cards.

**Alternative rejected.** Full-list stamping "for symmetry with M3" — M3's job is bucket-matching
arm B against fit *within the candidate pool*; the breaker has no within-pool question in v1.

**Consequence.** If v2 elects per-arm pre-draft screening, it will need in-generation evaluation
anyway (different seam, its own scope) — nothing in v1 is thrown away.

### D-A7 — Per-seat mirroring per taxonomy §2.1; no partner-side labels

**Decision.** The breaker evaluates from the partner seat by swapping give/receive on the
existing card. Shape stays the user-frame label (`2x1`); the breaker mirrors at evaluation time
and never mints partner-frame taxonomy values.

**Why.** Taxonomy §2.1 (binding): "do not mint a separate partner-side label." Aggregations
stay in one frame; mirroring is a view, not data.

---

## 5. Cross-Cutting Concerns

### 5.1 Flag topology

| Flag | Default | Gates | Graduation (scope.md §2) |
|---|---|---|---|
| `trade.breaker` | false | import + evaluate + stamp (and the shadow viewer-seat run, operator decision #5) | stamp coverage ≥99% of served cards, no p95 job-time regression, calibration readout run once |
| `trade.breaker_narrative` | false | hesitation line append + `narrated` bit; **requires** `trade.breaker` (checked at the callsite; narrative flag alone does nothing) | operator TestFlight pass + A/B readout |

Both in `config/features.json` + `FLAG_KEYS`/`DEFAULT_FLAGS` + release-fixture mirror +
`docs/config-reference.md`. Serving-affecting flips (`breaker_narrative` on) obey
one-engine-change-per-tester-week and go through logged change control.

### 5.2 Knobs (`model_config`, family sketch — exact list is LLD territory)

`breaker_min_severity` (narrative bar; the only user-visible-effect knob in v1) ·
`breaker_ms_budget` · `breaker_floor_<class>` per objection class. Every key: all five
registrations in the consumer's commit (`trade_service._DEFAULT_CFG`,
`database._MODEL_CONFIG_DEFAULTS`, golden-test pin, scope disposition sentence,
`docs/config-reference.md` — fit-challenger LLD §4 rule), each with a documented disable value
(floors/severity → 1.1 disables a class or the line; budget → 0 disables evaluation).

### 5.3 Rollback ladder (deploy-free, outermost first)

1. `trade.breaker_narrative → false` (hot reload) — user-visible surface gone; stamps continue.
2. `breaker_min_severity → 1.1` (PUT /api/admin/config) — line silenced without a flag flip.
3. `trade.breaker → false` — compute gone, module unimported, `features_json` key gone; rows
   byte-identical to pre-feature.
4. Revert commit — nothing persisted needs migration (no tables, no columns).

### 5.4 Cost model (NFR-2 backing)

Worst normal case: 12-team league, ~30 served cards, multi-format session ⇒ N parallel jobs
(cost is per job; jobs already own the 60s budget individually).

- **PartnerContext build:** ≤11 partners/job, but only partners present in the deck are built
  (typically ≤ deck size, often ~5–10). Each = `analyze_roster_strengths` (O(roster) ≈ 30
  players) + `infer_team_outlook` (O(roster + picks)) + dict handles to board/prefs. Both are
  pure in-memory Python over data already loaded by the job — sub-ms each; call it ≤1 ms/partner,
  ≤11 ms/deck.
- **Per-card evaluation:** 7 predicates over prebuilt context + package values via cached
  accessors (the `stamp_fit_diag` per-partner accessor-cache pattern). Dominated by
  `package_value_v2` and `_feasible_after` calls — single-digit ms worst case; `fit_diag` reuse
  (D-A2) removes the value-scoring cost entirely on bake-off decks. ~30 cards ⇒ ~10–100 ms/deck
  envelope.
- **Shadow viewer-seat run (decision #5):** ≤2× the per-card cost (same contexts, user seat).
  Fits the same 250 ms budget; if the operator declines, nothing else changes.

Total expected: **well under 150 ms/deck p95 vs a 250 ms budget vs a 60,000 ms timeout.** The
budget guard exists for pathological leagues (deep rosters, huge decks), not the norm.

### 5.5 Observability

- `breaker.ms` per card + `narrated` bit in every stamp ⇒ coverage, cost p95, and A/B exposure
  are SQL over `features_json` — no new telemetry.
- `ver` pinning (BREAKER_VERSION) ⇒ readouts refuse cross-version mixing (M2 precedent).
- Failures: warning log per deck (never per card at error level), null stamps visible in the
  coverage metric — a silent breaker outage shows up as coverage < 99%, which is the graduation
  gate, so the failure mode is self-surfacing.
- Measurement windows censored by `model_config_changes` (M1 rail) and the PLAN §6 data
  boundaries (ghost-row end date, D-091 window).

### 5.6 Docs & evidence deltas (scope.md §3/§4 restated as owners)

`docs/api-reference.md` (`trade_card_to_dict` additive object) · `docs/architecture.md` +
`living-memory/HLD.md` (evaluation-layer row/line) · `living-memory/LLD.md` (vocabulary
convention) · `docs/glossary.md` ("breaker", "objection", "hesitation line") ·
`docs/config-reference.md` (flags + knobs) · DECISIONS.md entry (D-A1 + D-A3) ·
`docs/cross-client-invariants.md` row filled "n/a in v1" unless a client ever switches on codes.
Evidence: `backend/tests/test_trade_breaker.py` per scope.md §3 (determinism, vocabulary closure,
per-class predicates, flag-off byte-identity, interleave inertness, stamp uniformity, narrative
honesty) + code-walk proof of both seams at build time + TestFlight checklist before the
narrative flag lights.

---

## 6. Risks & Open Questions

### 6.1 Risks

| # | Risk | Exposure | Mitigation |
|---|---|---|---|
| R-1 | **Outlook inference quality caps `fit_outlook` accuracy.** INV-372b means the legacy age/pick vector scores partners today; a mislabeled window makes the headline objection class confidently wrong — in user-facing copy | High (fit_outlook is 33% of filed reasons) | Severity discounts inferred vs declared windows (LLD knob); calibration readout cuts by declared/inferred; the breaker inherits the composite automatically when #372 graduates |
| R-2 | **Unboarded partners weaken `value_giving`.** 84.5% of served cards never consult a partner board; consensus-optics fallback is a weaker claim | High frequency, medium harm | Evidence records `basis: consensus_optics`; template hedges accordingly (D-053: say what you know); calibration cut boarded vs unboarded |
| R-3 | **Wrong hesitation line erodes trust faster than no line** — the scout that cries wolf | Medium | `breaker_min_severity` set from the calibration readout, not shipped-guessed (operator decision #4 default); TestFlight gate on the narrative flag; rollback rungs 1–2 are knob/flag-hot |
| R-4 | **Narrative changes behavior asymmetrically across arms?** The line is applied uniformly post-draft, but arm outputs differ in objection mix, so like-rates could shift per arm while the bake-off runs | Low-medium | It's outcome-shift, not order/composition — outside `bypass_rerankers`' letter; flag the readout: narrative A/B windows annotated per arm; if the operator wants purity, light `breaker_narrative` only after the current bake-off window closes (operator call, logged) |
| R-5 | **Contradiction with `_opponent_frame`** (§2.4) | Low | Shared-lean exclusivity test in the LLD |
| R-6 | **Severity floors are guesses until data exists** — chicken/egg | Certain, by design | v1's whole posture: stamp dark, calibrate, then set the narrative bar; floors are knobs, not code |
| R-7 | **Sibling drift** (A-2: Receipts contract text pending) | Open | Reconciliation pass before operator delivery; taxonomy change rule (PR + per-consumer note) |

### 6.2 Open questions (deferred to LLD unless marked operator)

1. **Exact predicate signatures + evidence-key enums per class** — LLD, with fixture rosters
   per class.
2. **Per-class severity formulas** (which margin, which normalization) — LLD; constraint from
   D-A5: existing quantities only.
3. **`shape_aversion` v1 basis** — without negmem history, what's the deterministic present-state
   predicate (roster-spot math via `waiver_slot_cost` mirroring, thin-roster 3-for-1 test)? LLD;
   the honest fallback is shipping it floor-disabled until negmem's history exists.
4. **Does the shadow viewer-seat run stamp into the same `breaker` key or a `breaker_shadow`
   sibling key?** LLD (uniform-keys rule applies either way). Operator decision #5 gates whether
   it runs at all.
5. **Hesitation line placement** — inside `narrative` (default, zero client change) vs distinct
   card element (client change + structural guard + Chalkline pass) — **operator decision #3**;
   the structured `d["breaker"]` object (§3.3) makes the server indifferent.
6. **Should `pick_gap_ok` / `overpay_ok` shapes be mirrored as breaker evidence** for
   `value_giving` on unboarded partners (G6 predicate shapes, partner seat, evidence-only)? LLD
   cost/benefit; G6 itself stays untouched regardless (D-062).
7. **A-1 verification** (interleave live, ghost end-date) via `model_config_changes` before any
   measurement window is defined — build-time task, PLAN §10.

---

*End of Draft A. Cross-critique target seams: D-A2 (them-null on organic), D-A6 (served-deck-only
stamping), §2.4 (append vs build_narrative integration), R-4 (arm-asymmetric outcome shift).*
