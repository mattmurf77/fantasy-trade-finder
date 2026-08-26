# PRD (Draft A — Product/User lens) — Negative-Results Memory

**Date:** 2026-08-21 · **Status:** DRAFT A for dual-agent review · **Author:** Agent A (product/user lens)
**Parents:** [README.md](README.md) (constraints of record) · [research-verification.md](research-verification.md) ("the memo" — code-truth; its §Design-constraints and §Corrections are hard facts) · [scope.md](scope.md) (feature gates; §6 operator decisions) · [PLAN.md](PLAN.md) (§2 design skeleton)
**Feature flag:** `trade.negmem` (default OFF) · **Express lane:** no — schema-adjacent, flag surface, engine behavior (bright line)

---

## 1. Summary

Dynasty managers churn through suggested trades, and today the lesson of every rejection
mostly dies in a log row. The engine already refuses to re-serve the *exact* pair a user
passed on (D-067 cooldown, 14 days), but nothing stops it from regenerating the same
*family* of dead trade — same league-mate, same shape, same objection — over and over,
burning deck slots and user trust on proposals that history says are doomed.

Negative-results memory makes rejections a **soft prior at generation time**. One bulk
read per (user, league) job builds an in-memory map of what died — keyed by league-mate,
shared-taxonomy trade shape, and the shipped `trade_pass_reasons` rejection codes,
regime-tagged at rejection time — and every generation arm consults it as a clamped
down-weighting multiplier. In the same release, the already-ratified but **unfed**
per-manager acceptance prior in gen_v2 (`acceptance_prior`, memo §2f — returns a uniform
0.5 today because no caller supplies `acceptance_stats`) is finally fed from real
league-mate response data.

It is explicitly **not** a fourth hard filter: soft, clamped, floor-protected,
byte-identical when disabled, and every influence stamped on the card
(`features_json.negmem`) — none silent.

**Design principle** (operator's product-gap review): *negative results are the most
undervalued asset — keep every failed hypothesis, in the context where it failed, and the
system stops repeating them.*

## 2. Problem & Context

### 2.1 The user problem

The core loop of the app is a swipe deck of suggested trades. Users are dynasty league
managers who evaluate suggestions in bulk — ~400 decided cards/week across the tester
base (memo §8). When a manager passes on a card, they now (since 2026-08-17) tell us
*why*: value, fit, or a player-level objection (`trade_pass_reasons` layer-1/2 codes,
memo §1.4). That reason routes an Elo consequence (D-066) and a 14-day exact-pair
cooldown (D-067) — and then its lesson stops. The next generation run rebuilds its
candidate space from scratch, free to propose the sibling of the trade that just died:
same partner, same 2-for-1 shape, same "you're gutting my WR room" objection, different
third player.

The measurable symptom: the D-067 investigation found one user with 4,003 impressions vs
61 decisions in 14 days, and even after exact-pair exclusion shipped, the G6 presentment
audit measured an 18.4% kill rate — cards generated that presentment rules had to kill
(memo §8). The engine spends generation budget and deck slots re-deriving hypotheses the
user has already falsified.

The operator's recorded principle governs here: **"accuracy, not volume. Bad suggestions
are worse than limited suggestions"** (D-067). A thinner deck of live hypotheses beats a
full deck padded with re-runs of dead ones.

### 2.2 Who this is for

- **Primary: the active swiper** — a manager working the deck weekly, whose passes carry
  reasons. Their reward: decks stop re-litigating settled objections; each session's
  cards are net-new hypotheses.
- **Secondary: the proposer** — a manager who sends real proposals through the app. Their
  reward: suggestions tilt toward league-mates who actually respond and accept
  (layer 2), so proposals stop dying in silence.
- **Not a user of this feature (v1):** league-mates themselves. Layer 2 models them, but
  nothing is shown to them or about them (see §5.4 privacy and operator decision 3).

### 2.3 The two layers, and which is v1

From [README.md](README.md), this feature has two layers; **the PRD decides the v1
boundary, and this draft sets it as follows:**

1. **Layer 1 — user-side memory (v1, in full).** What THIS user rejects — shape
   aversions, board misfits, partner-specific dead ends — becomes a generation-time soft
   prior the engine respects. Evidence: the user's own viewed, reasoned rejections.
2. **Layer 2 — league-mate tendency modeling (v1 = seed only).** Inferred acceptance
   patterns of other managers, so the engine anticipates the counterparty. Novel,
   riskier, and it carries a privacy/fairness question (modeling league-mates who may
   not be app users) that this PRD **surfaces for the operator rather than decides**
   (§8, decision 3). The v1 seed is deliberately minimal: feed the existing gen_v2
   `acceptance_prior` stub with per-league-mate aggregate (accepts, responses) counts —
   ratified math, seeded knobs, zero schema (memo §2f, §DC-10). Full per-shape /
   per-reason tendency modeling is a follow-on, gated on the operator's privacy ruling.

### 2.4 Sibling boundaries (verbatim, binding)

This is one of three features closing the same loop, planned by three sessions. The
boundaries below are carried verbatim from [README.md](README.md) and are contract text
for the three-way reconciliation:

- **Receipts** (post-mortem grading, session `trade-suggestions-review-69c9eb-f4`):
  "the post-mortem half of the same loop: **Receipts grades what we suggested; this
  remembers what died so it isn't re-generated.**" Receipts owns `receipts_`-prefixed
  tables; this feature reserves the `negmem_` prefix (unused in v1).
- **Counterparty breaker** (session `trading-engine-eval-8ab7bc-31`): "an adversarial
  pass arguing the OTHER manager's rejection case from their present roster/window
  state. Boundary both PRDs draw identically: **breaker = deterministic present-state
  analysis; this feature = historical behavioral prior from observed rejections.**
  Potentially feeding each other later; separate mechanisms, separate owners now."
- **One shared trade-shape taxonomy across the sibling features — never two**
  (README constraint of record). See §5.5.

### 2.5 What already exists (and must not be rebuilt)

The memo's §2 inventories every existing suppression/learning mechanism — F3 fatigue,
D-067 cooldown, R4 exclusion, F5 taste, Thompson F2, the gen_v2 stub, fit-arm
post-filters, untouchables. Two facts anchor this PRD:

- **The generation-time prior seam already exists in ratified form**: gen_v2's
  `acceptance_prior` (empirical-Bayes, `p = (accepts + m·p0)/(responses + m)`,
  knobs `gen2_accept_prior_strength`=10 / `gen2_accept_global_prior`=0.5) is multiplied
  into every candidate score — but **no caller ever supplies `acceptance_stats`**, so it
  is a uniform no-op today (memo §2f, Corrections 1).
- **Nothing acts at generation time on *why* trades die.** The only generation-time
  exclusions are exact-pair (D-067) or status-based (R4). The reason taxonomy that
  routes Elo consequences (memo §DC-5) reaches no generation path.

## 3. Goals & Non-Goals

### Goals

- **G1.** Stop regenerating falsified trade families: repeatedly-rejected
  (partner × shape × reason-family) combinations are down-weighted at the source,
  before they consume generation budget and deck slots.
- **G2.** Feed the unfed: gen_v2's `acceptance_prior` receives real per-league-mate
  response aggregates at both call sites (`trade_service.py:4001`,
  `bakeoff_runner.py:1212`), turning a ratified stub into a working prior.
- **G3.** Keep every effect auditable and reversible: each influenced card is stamped
  (`features_json.negmem`), the flag OFF and `negmem_strength=0` are byte-identical to
  today, and no card is ever hard-excluded by this feature.
- **G4.** Honor D-067's spirit under an explicit operator ruling: family-level memory is
  soft, clamped, and floor-protected — "one swipe must not silence a player's whole
  trade space" remains true.
- **G5.** Be a measurable bake-off citizen from day one: the prior is part of the model
  under test, its knobs snapshotted in `bakeoff_runs.config_json`, its effect readable
  per arm (memo §DC-7).

### Non-Goals

- **NG1.** No new hard filter. Exclusion stays owned by D-067 cooldown, R4,
  untouchables/not-interested, and F3 decline suppression — unchanged.
- **NG2.** No suppression of served-but-unacted cards. D-067 Alternatives records
  impression-readback for unacted cards as **out of scope per the operator** (memo
  §2d); this feature consumes only acted, viewed rejection evidence and does not
  re-open that ruling.
- **NG3.** No user-facing UI in v1 — no "why am I not seeing X" explainer, no memory
  management screen. (Any later UI re-enters gates on its own; scope §3 waiver.)
- **NG4.** No full layer-2 per-shape/per-reason tendency modeling of league-mates in v1
  (operator decision 2/3 territory).
- **NG5.** No new tables in v1. Derive-on-read per the house style; a materialized
  `negmem_*` table is admitted only behind a latency-measured LLD gate (scope §2).
- **NG6.** No second trade-shape vocabulary. All family semantics use the shared
  taxonomy verbatim (§5.5).
- **NG7.** No changes to Receipts' or breaker's surfaces; no Elo behavior changes
  (Elo routing stays with D-066's `pass_reason_elo_suppression`).

## 4. Success Metrics

All metrics are computable from **existing instrumentation** — the F1 spine
(`deck_impressions` ⨝ `deck_outcomes`), `trade_pass_reasons`, `trade_matches`,
`trade_decisions`, and bake-off attribution columns (`deck_impressions.model_arm`,
`bakeoff_runs.config_json`). No new events (scope §1). All windows exclude the D-091
contamination window (2026-08-16 → 2026-08-19) and, where "never shown" matters, respect
the ghost boundary 2026-08-21T00:43Z (`deck_impressions.is_ghost`).

### 4.1 Primary — Repeat-family pass share (RFPS)

**Definition:** among *viewed* `pass`/`not_interested` outcomes
(`deck_outcomes.action`, viewed-gated via the F1 join), the share whose card belonged to
a family — `(features_json.partner_user_id, shape_bucket, reason_family)` — that already
had ≥ `negmem_min_evidence` qualifying rejections at that card's `served_at`. Family
membership is reconstructible entirely from serve-time-frozen `features_json` plus
`trade_pass_reasons` rows keyed `key_source='impression'`, so the baseline is computable
**retroactively from the existing spine before any code ships** — the launch readout has
a pre-registered denominator.

**Target:** ≥ 25% relative reduction in RFPS on negmem-ON serving vs negmem-OFF, per
bake-off arm attribution, over the graduation window (§8.3). Chosen as primary because
it is precisely the thing the feature claims to change ("stop repeating falsified
hypotheses"), it is user-visible (fewer déjà-vu cards), and it is measurable per arm
with zero new instrumentation.

### 4.2 Secondary

- **S1 — Viewed like rate per arm** (`deck_outcomes.action='like'` over viewed cards,
  by `model_arm`): should hold or rise; the deck's freed slots should carry live
  hypotheses, not worse ones.
- **S2 — Propose rate** (`deck_outcomes.action='propose'` per viewed card, by arm): the
  north-star-adjacent intent signal; must not degrade.
- **S3 — Stamp coverage & magnitude**: share of served cards carrying
  `features_json.negmem` and the distribution of its `mult` — verifies the prior is
  alive, clamped, and not saturating at the floor.
- **S4 — Acceptance-prior spread (M2)**: with `acceptance_stats` fed, per-league-mate
  priors diverge from the uniform 0.5; verified from the aggregation query's output and
  the `bakeoff_runs.config_json` snapshot (arm C), not from a new event.

### 4.3 Guardrails

- **GR1 — Deck supply:** median cards per completed job (`deck_impressions` count per
  `deck_job_id`) within 10% of the negmem-OFF arm. Deck thinning is an *accepted* cost
  under D-067's principle, but starvation is not; `_DECK_MIN_CARDS`=5 semantics are
  untouched by design (the prior cannot exclude).
- **GR2 — Not-interested rate** must not rise (a rise would mean the prior is pushing
  worse cards up, not dead cards down).
- **GR3 — Flag-off parity:** golden test — `trade.negmem` OFF and `negmem_strength=0`
  are byte-identical to pre-feature generation (memo §DC-9).

**Small-n honesty:** at ~845 lifetime like/pass outcomes and ~400 decided cards/week
(memo §8), arm-level deltas of this size need weeks, not days. Graduation (§8.3) is
therefore time-boxed at ≥ 4 weeks of interleaved serving, and shrinkage
(`negmem_min_evidence`) is a *requirement*, not a tuning nicety.

## 5. Requirements

### 5.1 User stories

- **US1 (active swiper):** As a manager who passed on three "2-for-1 sending my WR2 to
  the same rebuilder" proposals with fit reasons, I want the engine to stop leading my
  deck with a fourth, so my session is spent on trades I haven't already refuted.
- **US2 (active swiper):** As a manager, I want a rejected *family* demoted, not
  banned — if my roster or the market changes, the trade can still resurface — so one
  bad week of swipes doesn't permanently blind the engine.
- **US3 (proposer):** As a manager sending real proposals, I want suggestions weighted
  toward league-mates who actually respond and accept, so fewer of my proposals die in
  silence.
- **US4 (skeptical user):** As a manager, I want every demotion to be explainable from
  my own recorded reasons (auditable stamp + stored reason codes), so the deck never
  feels arbitrarily censored.
- **US5 (operator):** As the operator, I want the whole mechanism reversible without a
  deploy (`negmem_strength=0`) and invisible until I flip it, so it can be trialed on
  my own league first.

### 5.2 Functional requirements

**Layer 1 — M1: generation-time soft prior**

- **FR-1.** The system SHALL build, once per (user, league) generation job, an in-memory
  prior map keyed `(partner_league_id, shape_bucket, reason_family)` from one bulk read
  of `trade_decisions`, `trade_pass_reasons`, and `deck_impressions ⨝ deck_outcomes`.
  No per-candidate DB reads at generation (memo §DC-1). Identity is league-scoped
  (`_league_user_id`) throughout — never account ids (memo §DC-8).
- **FR-2.** Map entries SHALL carry time-decayed (`negmem_halflife_days`), empirical-
  Bayes-shrunk counts and a regime tag frozen from the rejection's serve-time context
  (`features_json`: lane, `user_value_basis`, board-state fields — exact tag set is an
  HLD decision). Entries below `negmem_min_evidence` effective observations SHALL have
  no effect (multiplier 1.0).
- **FR-3.** Every generation path — v1/v3 serving engine (per-opponent loop,
  `trade_service.py:4563`), gen_v2 (`trade_gen_v2.py:939-975`), and the fit arm
  (its scorer / step-5 seam, `trade_gen_fit.py:753`) — SHALL consult the map as a score
  multiplier clamped to `[negmem_floor, 1.0]`. **Sink-never-rise; no gated card is ever
  rescued; candidate membership is never changed by this feature** (memo §DC-3).
- **FR-4.** Every card whose score was touched by the prior SHALL be stamped
  `features_json.negmem = {mult, keys_hit, ver}` (exact shape is an LLD decision; the
  commitment is: **every influence stamped, none silent** — scope §1).
- **FR-5.** Existing hard exclusions (D-067 cooldown, R4, untouchables/not-interested,
  F3 decline suppression) SHALL be unchanged in code and behavior; the prior composes
  with them and never substitutes for them.

**Layer 2 seed — M2: feed the stub**

- **FR-6.** The system SHALL compute, per league-mate in the league (app user or not),
  aggregate `(accepts, responses)` from `trade_matches` decisions and decline records,
  and pass it as `acceptance_stats` to `generate_league_suggestions` at **both**
  existing call sites (`trade_service.py:4001`, `bakeoff_runner.py:1212`). No new math,
  no new knobs: the seeded `gen2_accept_prior_strength` / `gen2_accept_global_prior`
  govern shrinkage (memo §2f, §DC-10). League-mates with zero responses receive exactly
  the global prior (today's behavior for everyone).
- **FR-7.** M2 SHALL be gated by the same `trade.negmem` flag (one flag, one feature);
  with the flag OFF, `acceptance_stats` is not passed and gen_v2 behavior is
  byte-identical to today.

**Control surface**

- **FR-8.** Feature flag `trade.negmem`, default **false**. OFF ⇒ no reads, no stamps,
  byte-identical generation (golden-tested).
- **FR-9.** `model_config` knobs, each with a `_MODEL_CONFIG_DEFAULTS` seed row and an
  arm-A disposition sentence (scope §2): `negmem_strength` (0 = disable,
  byte-identical), `negmem_min_evidence`, `negmem_halflife_days`, `negmem_floor`.
  Every knob's disable value is byte-identical to prior behavior (memo §DC-9).
- **FR-10.** Bake-off citizenship: the generation-time prior is part of the model under
  test. All negmem knob values SHALL be snapshotted in `bakeoff_runs.config_json`;
  per-arm attribution via the existing `deck_impressions.model_arm` column. (Because it
  acts at generation, not re-ranking, it is NOT subject to the `bypass_rerankers()`
  bake-off bypass — it changes arm behavior by design; memo §DC-7.)

**Data-hygiene requirements** (each is a testable requirement, not guidance):

- **DH-1 (viewed-gating).** Only *viewed* rejection outcomes count as evidence: a
  `pass`/`not_interested` row in `deck_outcomes` joined to its impression, where a
  `viewed` outcome exists for that `impression_id` (card fronted ≥500ms). Served-but-
  unacted impressions are never evidence (NG2; D-067 operator ruling).
- **DH-2 (ghost boundary).** Rows with `deck_impressions.is_ghost=1` are excluded from
  all evidence and denominators. The ghost holdout was disabled **2026-08-21T00:43Z**
  (serving re-light); any "rejected vs never saw" distinction ends at that instant and
  the map builder SHALL NOT assume ghost rows exist after it (README constraint).
- **DH-3 (D-091 window).** Evidence timestamped inside **2026-08-16 → 2026-08-19** (the
  phantom-pick contamination window) SHALL be excluded by timestamp — 12.8% of served
  cards in that window offered a nonsense 2029 pick and passes skewed onto them; a
  model trained on it partly learns "picks get passed on" (memo §1.5).
- **DH-4 (shrinkage).** Empirical-Bayes shrinkage toward pooled priors is **mandatory**:
  at ~845 total like/pass outcomes, per-(partner × shape × reason) cells are nearly all
  empty (memo §8), and `negmem_min_evidence` SHALL floor any cell's influence at
  multiplier 1.0 below threshold.
- **DH-5 (`user_value_basis`).** Per shared-taxonomy §2.6: a pass on a personally-priced
  card (`features_json.user_value_basis` = personal board) is **board-fit evidence, not
  market-value evidence**. Value-coded rejections (`reason='value'`) on personally-
  priced cards SHALL be filed under the fit/board reason-family, not the market-value
  family.
- **DH-6 (retractions and undo).** `trade_decisions` rows with `retracted_at` set, and
  `deck_outcomes` rows negated by a subsequent `undo`, are not evidence. Only
  `trade_pass_reasons` rows with `key_source='impression'` join the spine; `'local'`
  surrogate rows contribute reason evidence only at the decision level, never
  feature-joined (memo §1.4).
- **DH-7 (pre-reason era).** Rejections before 2026-08-17T22:22:56Z carry no reason
  code (memo §1.5); they MAY contribute to reason-agnostic (partner × shape) evidence
  with reduced weight, but SHALL never be imputed a reason. (Exact weighting: LLD.)

**Shared taxonomy**

- **FR-11.** All shape/family vocabulary SHALL use
  `docs/plans/shared/trade-shape-taxonomy.md` **v1.0.0 terms verbatim** (adopted
  2026-08-21; authored by the Receipts session, lands in-repo with their merge;
  three-way co-owned, semver'd). The §2.1 partner-mirror convention and §2.6
  `user_value_basis` caveat are load-bearing for the rejection-record design (README).
- **FR-12.** This feature SHALL propose taxonomy **v1.1.0** (additive minor, at
  three-way reconciliation): an objection/rejection vocabulary section anchored on the
  shipped `trade_pass_reasons` layer-1/2 codes, with a **PRODUCER column** identifying
  which sibling emits each term — including the **`shape_aversion` term, producer =
  `negmem`** (this feature is its sole producer; Receipts and breaker are consumers).
  No term ships in code before the three-way sign-off.

### 5.3 States & edge cases

| State | Behavior |
|---|---|
| Cold start (no evidence for this user-league) | All multipliers 1.0; ordering byte-identical to flag-off. |
| Sparse cell (< `negmem_min_evidence`) | Multiplier 1.0 (DH-4). |
| Every candidate in a family floored | Cards still generated and servable at `negmem_floor` weight; deck may thin but membership is untouched — `_DECK_MIN_CARDS` semantics unchanged (GR1). |
| User undoes a pass | The undo appends alongside (append-only spine); that rejection leaves the evidence set on the next job's map build (DH-6). No live re-bind needed — next-job freshness is the contract, matching derive-on-read siblings. |
| Regime change (user's window/board flips) | Regime-tagged evidence from the old regime is down-weighted per the HLD's tag design; the prior must not carry a rebuild-era aversion into a contend-era deck unmodified (FR-2). |
| Partner leaves the league / roster re-sync | Map keys are league-scoped; a departed partner's entries simply stop matching any candidate. No cleanup job needed in v1 (derive-on-read). |
| Flag flipped mid-session | Next generation job reflects it (map is built per job); in-flight decks unchanged — same contract as fatigue/taste. |
| Bake-off deck | Prior applies *within* the arm as part of the model under test (FR-10); never bypassed the way POST re-rankers are, and never contaminates other arms (per-arm knob snapshot). |
| gen_v2 dark (`trade_gen.v2` OFF) | M2 still feeds arm C in the bake-off (`bakeoff_runner.py:1212`); the serving-path call site is wired but inert until v2 serves. |
| Pre-reason-era rejections | Reason-agnostic reduced-weight evidence only (DH-7). |
| `'local'` key-source pass reasons | Decision-level evidence only; never joined to frozen features (DH-6). |

### 5.4 Non-functional requirements

- **NFR-1 (latency).** Map build is one bulk read per job at job start; the derive-on-
  read choice holds unless a measured latency regression forces materialization — that
  measurement is a named LLD/build gate, not an assumption (scope §2, memo §DC-2).
- **NFR-2 (auditability).** Every effect is reconstructible after the fact from the
  stamp (FR-4) plus stored reason codes. `trade_pass_reasons.free_text` is never read
  into the model, never a feature, never an analytics property (memo §1.4, §5).
- **NFR-3 (privacy — layer 1).** Layer-1 memory is the user's own behavior, stored
  where it already lives (no new collection, no new tables). Nothing new to disclose.
- **NFR-4 (privacy — layer 2).** v1's M2 computes per-league-mate aggregates
  **derive-on-read, engine-internal**: no dedicated table of inferred tendencies per
  league-mate, no surface that displays any inference about a named manager to anyone.
  This deliberately stays within the already-shipped precedent (`user_taste`'s
  `partner:{user_id}` attrs; gen_v2's per-manager prior interface — memo §7) and
  defers the step beyond it — a durable per-person tendency record — to operator
  decision 3. **Known gap, recorded:** `accounts.delete_user_data` has no reason today
  to touch rows keyed by a *partner's* id; any future materialized layer-2 table MUST
  add that deletion path before it ships (memo §7).
- **NFR-5 (analytics).** No new client events; no taxonomy change. The one addition is
  the server-stamped `features_json.negmem` field → `docs/data-dictionary.md` row
  (scope §1). Nothing here touches `analytics_taxonomy.py`.
- **NFR-6 (rollback).** Flag off = full revert; `negmem_strength=0` = deploy-free soft
  revert; both golden-tested byte-identical (GR3).

### 5.5 Why this is not a fourth mechanism — **merge gate**

The design risk this feature was researched against is "building a fourth overlapping
suppression system" (memo, preamble). This section is a **merge gate**: for each
existing mechanism, a *card-level* behavioral difference is named — a concrete card that
one mechanism touches and the other cannot. **If a difference cannot be named for each,
the feature does not ship.**

**vs F3 fatigue** (soft exposure decay + hard decline suppression, POST-generation,
memo §2a): F3 keys on what was *served* — trade_hash, centerpiece, archetype of cards
the user has already seen — and demotes or removes near-duplicates of *specific served
cards* after the deck is generated. **Card-level difference:** a candidate the user has
*never been shown* — a brand-new 2-for-1 to partner X whose family (X × 2x1 ×
fit_new_weakness) died three times last month — is invisible to F3 (no impression, no
trade_hash, no suppression row) but is down-weighted by negmem before it ever reaches
the deck. Conversely, a card served five times and never acted on is fatigued by F3 but
contributes nothing to negmem (DH-1: unacted impressions are not evidence).

**vs D-067 cooldown** (hard exact-pair exclusion, 14d pass / 7d like, GEN, memo §2b/2d):
the cooldown removes *the identical give/receive pair* for a window, deliberately
exact-pair — "one swipe must not silence a player's whole trade space." **Card-level
difference:** a *new* exact pair sharing the dead family (same partner, same shape, same
objection, one asset swapped) passes the cooldown untouched — the cooldown has never
seen this pair — while negmem softly demotes it. And the exact passed pair itself is
removed by the cooldown for 14 days regardless of anything negmem says; negmem never
removes anything, ever.

**vs F5 taste** (user-scoped attribute cosine re-ranking, POST-generation, clamped
0.7–1.4 — may *boost*, memo §2e): taste is a cross-league portrait of the manager's
general preferences that reorders gate-passing served candidates and can raise a card
above its base position. **Card-level difference:** taste can *promote* a card (clamp
upper bound 1.4 > 1); negmem is sink-never-rise by requirement (FR-3) and can promote
nothing. And taste follows the manager across leagues by design (`user_taste` is
user-scoped); negmem evidence is (user, league)-scoped and league-mate-keyed — a shape
aversion learned against partner X in league A says nothing in league B, where taste's
`shape:2x1` attr would still apply.

Summary of the occupied niche: **league-scoped · generation-time · family-level ·
reason-aware · soft · auditable.** No existing mechanism has more than two of those six
properties (memo §2 summary table).

## 6. Scope & Phasing

### v1 cut line

**In v1:**

1. **M1** — layer-1 generation-time soft prior: map builder (FR-1/2, DH-1..7),
   consultation in all three generation paths (FR-3), stamping (FR-4), flag + four
   knobs (FR-8/9), bake-off snapshot (FR-10).
2. **M2** — layer-2 seed: `acceptance_stats` aggregation + both gen_v2 call sites
   (FR-6/7), pending operator decisions 2 and 3.
3. Taxonomy v1.0.0 adoption + v1.1.0 proposal at three-way reconciliation (FR-11/12).
4. Evidence per scope §3: pytest (map builder, clamps, goldens, E-B parity, identity
   hygiene), code-walk proof of the seams, operator TestFlight checklist.

**Explicitly out of v1** (each re-enters gates on its own):

- Full layer-2 tendency modeling (per-shape/per-reason per-league-mate) — deferred to a
  follow-on gated on operator decision 3.
- Any user-facing surface (explainers, memory management) — NG3.
- Materialized `negmem_*` tables — admitted only via the latency-measured LLD gate.
- Cross-league memory transfer; breaker/receipts integration (post-reconciliation
  follow-ons per README: "potentially feeding each other later").
- Any change to Elo routing, cooldown windows, R4, F3, F5, Thompson.

### Phasing

- **P0 (this suite):** PRD/HLD/LLD via dual-agent review → three-way reconciliation →
  operator review of the three decisions. **Zero code** (PLAN §1).
- **P1 (build, ~5d est. per PLAN §3):** W1 map builder → W2 seams + control surface →
  W3 M2 feed → W4 evidence → W5 docs/taxonomy.
- **P2 (rollout):** dark → operator's league → bake-off-measured → graduation (§8.3).

## 7. Dependencies & Risks

### Dependencies

| Dependency | State | Consequence if late |
|---|---|---|
| Shared taxonomy v1.0.0 in-repo | Adopted 2026-08-21; **lands with the Receipts merge** — not in this checkout yet | FR-11 blocks build (not planning); v1.1.0 proposal drafted against the adopted seed regardless |
| Three-way reconciliation (Receipts + breaker + this) | Required before the suite reaches the operator (README) | No operator review, no build |
| Operator rulings 1–3 (§8.1) | PENDING (scope §6) | Build does not start; decision 3 alone can defer M2 |
| Fit-challenger merge (PR #154) | **Merged to main** — its post-score filter stage and bake-off arms are live surfaces the hook must compose with (README) | n/a (already true; HLD owns the composition) |
| Bake-off serving rounds running | Live (`trade.bakeoff` ON; serving rounds per PLAN §3) | Graduation unmeasurable; rollout stalls at operator-league stage |
| gen_v2 status | `trade_gen.v2` OFF; module runs only as bake-off arm C | M2's serving-path effect is dark until v2 serves — expected, not a blocker |

### Risks

| Risk | Severity | Handling |
|---|---|---|
| Fourth-mechanism overlap emerges in practice | High | §5.5 is a merge gate: a named card-level difference vs F3, D-067, and F5, or no-ship |
| n too small for family-level inference (~845 outcomes) | High | DH-4 shrinkage mandatory; `negmem_min_evidence` floor; M2 restricted to aggregate counts; graduation time-boxed ≥4 weeks |
| D-067 principle violated in spirit (soft prior ≈ de-facto ban at low floor) | Medium | `negmem_floor` clamp; S3 monitors floor-saturation; explicit operator ruling requested before build (§8.1 D1) |
| Privacy/fairness of modeling non-app-users | Medium | Nothing built until decision 3 is ruled; v1 recommendation is aggregate-only engine-internal (§8.1 D3); delete-path gap recorded (NFR-4) |
| Training on contaminated or phantom data | Medium | DH-2/DH-3 exclusions are unit-tested requirements, not conventions |
| Taxonomy drift across three sibling plans | Medium | One shared semver'd file, PRODUCER column, three-way sign-off (FR-12) |
| Latency regression from job-start bulk read | Low | NFR-1 measured gate; materialization escape hatch pre-authorized in scope §2 |
| Bake-off contamination (prior leaking across arms) | Low | Generation-time = part of the arm's model; per-arm knob snapshot in `bakeoff_runs.config_json` (FR-10); goldens for OFF arms |

## 8. Rollout & Measurement

### 8.1 The three operator decisions (present before build — scope §6)

**D1 — D-067 family-level ruling.** D-067 deliberately kept dismisses exact-pair and put
impression-readback out of scope; this feature IS family-level memory.
*Question:* does "accuracy over volume; one swipe must not silence a trade space" permit
**soft** family down-weighting, and at what floor?
**Recommendation: YES, permit it — as a clamped soft prior with `negmem_floor` default
0.5.** Reasoning: D-067's line was drawn against *hard exclusion* — a swipe erasing a
player's whole trade space. A floor-clamped multiplier preserves the space (every family
member remains generable and servable), is stamped and auditable (FR-4), and is
revertible without a deploy (`negmem_strength=0`). The floor default of 0.5 matches the
most conservative existing soft clamp in the stack (Thompson's 0.5 lower bound; deeper
than taste's 0.7, shallower than fatigue's 0.25 — which the operator already accepted
for *served* cards). It also stays inside D-067's actual out-of-scope ruling: that
ruling covered *unacted* impressions, and negmem consumes only acted, viewed rejections
(NG2, DH-1). The ruling is the operator's; the floor is a knob either way.

**D2 — Layer-2 v1 boundary.** *Question:* confirm or widen "v1 = feed the existing
`acceptance_prior` stub from `trade_matches` responses + decline records; full
per-shape/per-reason tendency modeling = follow-on."
**Recommendation: CONFIRM as scoped (memo §DC-10).** Reasoning: the stub is ratified
math with seeded, documented knobs and a deliberately narrow interface ("a learned
acceptance model replaces this function without touching the pipeline" —
`trade_gen_v2.py:297-299`); feeding it costs zero schema and zero new math, and at
today's volumes richer per-shape cells would be empty anyway (memo §8). Widening now
buys nothing measurable and pre-empts decision D3.

**D3 — Privacy/fairness of modeling league-mates, incl. non-app-users.** Layer 2 models
OTHER managers from their observed responses to proposals; `league_members` and
`sleeper_trades` already cover non-users, and per-manager preference modeling has
shipped precedent (`partner:{user_id}` taste attrs, the per-manager prior interface) —
but a *dedicated record of inferred tendencies per league-mate* is a step beyond, and
the deletion path doesn't cover partner-keyed rows (memo §7). *Options:* (a) full
layer 2 · (b) app-users only · (c) aggregate-only — no per-person records persisted or
shown to anyone, engine-internal · (d) defer layer 2 entirely.
**Recommendation: (c) for v1.** Reasoning: (c) delivers the entire M2 value (the prior
only needs aggregate accepts/responses), stays derive-on-read so no per-person record
ever exists at rest, sidesteps the `delete_user_data` gap by having nothing to delete,
and treats app-users and non-users identically — avoiding the (b) asymmetry where
installing the app makes you *more* modeled than your league-mates. (a) is the
follow-on's question, with the deletion path as a named precondition; (d) forfeits G2
for no privacy gain over (c), since (c) persists nothing. Nothing is built until ruled.

### 8.2 Rollout sequence

1. **Dark:** merge with `trade.negmem` OFF everywhere; goldens prove byte-identity
   (GR3). Baseline RFPS computed retroactively from the existing spine (§4.1) and
   logged in `TEST_LEDGER.md` alongside the map-build latency measurement (NFR-1).
2. **Operator league:** flag ON for the operator's device/league only (the
   `tester_allowlist.json` pattern); operator runs the TestFlight checklist from scope
   §3 — decks materially unchanged except named down-weights; stamps visible in
   readout SQL.
3. **Bake-off:** negmem enters the live bake-off as arm configuration — knobs
   snapshotted per run in `bakeoff_runs.config_json`, effect attributed per
   `deck_impressions.model_arm`. Readout SQL gains negmem stamp-rate columns (PLAN W4).
4. **Graduation decision:** operator reviews §8.3 against the readout; default-ON is a
   separate, explicit flip — never implied by merge.

### 8.3 Graduation criteria (measured through the live bake-off)

Over **≥ 4 consecutive weeks** of interleaved bake-off serving with negmem ON in at
least one arm (per-arm attribution via `deck_impressions.model_arm`; all negmem knobs
snapshotted in `bakeoff_runs.config_json` for every run in the window):

- **G-A (primary):** RFPS (§4.1) reduced ≥ 25% relative, negmem-ON vs negmem-OFF arms.
- **G-B:** viewed like rate (S1) and propose rate (S2) at parity or better (no
  degradation beyond the small-n noise band the readout states explicitly).
- **G-C:** guardrails GR1 (deck supply within 10%) and GR2 (not-interested rate not
  rising) hold.
- **G-D:** S3 shows the prior alive but not saturated (floor-pinned share of stamped
  cards below a threshold the LLD sets), and zero unstamped influence found by audit
  SQL.
- **G-E (M2):** acceptance priors diverge from uniform where response data exists (S4),
  with no arm-C regression on its bake-off metrics.

Failing G-A but holding G-B/C/D after 4 weeks → extend one knob-tuning cycle (new
`bakeoff_runs.config_json` snapshot), then ship-or-shelve; failing G-B or G-C at any
point → `negmem_strength=0` (deploy-free), investigate via stamps.

---

*Draft A ends. Reconciliation hooks for Agent B: floor default (0.5 — argued from the
existing clamp family, but 0.25–0.7 is defensible), DH-7's reduced-weight treatment of
pre-reason-era rejections (could be dropped to zero weight for simplicity), the regime-
tag definition (deliberately left to HLD), and whether M2 should share the `trade.negmem`
flag (FR-7) or take its own — Draft A argues one feature, one flag.*
