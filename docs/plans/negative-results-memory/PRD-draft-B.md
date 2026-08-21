# PRD — Negative-results memory (Draft B: engineering/feasibility lens)

**Date:** 2026-08-21 · **Author:** Agent B (dual-agent-doc-review, adversary draft)
**Status:** DRAFT for cross-review — not the reconciled PRD
**Parents:** [README.md](README.md) · [research-verification.md](research-verification.md) (cited as "memo"; its facts are hard constraints) · [scope.md](scope.md) · [PLAN.md](PLAN.md)
**Taxonomy:** `docs/plans/shared/trade-shape-taxonomy.md` v1.0.0, terms verbatim; v1.1.0 rejection-vocabulary addition proposed at reconciliation

This draft is written by the engineer who has to build it and be blamed if it misses. Its
bias is against optimism: every claim of learning is checked against the actual row
counts, every "measurable effect" is checked against whether anyone could actually
measure it, and the places where this feature is thinner than its pitch are said out
loud. It is still a buildable PRD — the skepticism narrows the scope, it does not
zero it.

---

## 1. Summary

Two mechanisms, sized to the data that actually exists:

- **M2 (build first, smallest, most certain):** feed gen_v2's ratified-but-unfed
  `acceptance_prior` stub (memo §2f) with per-league-mate (accepts, responses)
  aggregated on read from `trade_matches` decisions. Zero schema, zero new math, two
  call sites. Retires a standing piece of debt: a documented prior that has returned a
  uniform 0.5 since it shipped.
- **M1 (the actual feature, deliberately coarse):** a per-(user, league) soft prior,
  derived on read at job start, keyed **(partner_league_id × reason_family)** — NOT
  the full (partner × shape × reason) cross the brief imagines — consuming **only
  reason-carrying rejection records** (`trade_pass_reasons` rows with
  `key_source='impression'`, joined to serve-time-frozen features). Applied as a
  clamped, floored, decayed multiplier inside the per-opponent generation loops of
  every arm. Sink-never-rise; stamped on every influenced card; byte-identical when
  disabled.

What is explicitly NOT in v1: the shape dimension in M1's key (data-gated, §6),
layer-2 per-shape/per-reason tendency modeling (deferred entirely, §7.2), any UI, any
new table, any new route, any hard exclusion.

**The honest one-liner:** v1 is correct plumbing plus a small, auditable prior over a
data stream that is days old. Its value compounds as reason-carrying rejections
accrue; its v1 success criteria are therefore correctness, auditability, and
data-accrual — not engagement lift, which is unmeasurable at this n (§4.1).

## 2. Problem

### 2.1 The stated problem (real)

A rejected proposal today produces: an exact-pair cooldown (14d, D-067), a taste-vector
nudge (F5, user-scoped, reason-blind), possibly a fatigue signal (F3, exposure-keyed) —
and a `trade_pass_reasons` row that **no generation path ever reads**. The one record
that says *why* a card died routes an Elo consequence (D-066) and then sits. Meanwhile
the engine re-enumerates near-identical candidates against the same partner because
exact-pair keys don't generalize: pass on `A→X for B`, and `A→X for B'` regenerates
untouched.

### 2.2 The problem under the problem (the part an optimist skips)

Three mechanisms already learn from rejections. The design risk the memo exists to
kill is a **fourth overlapping suppression system** — and for layer-1 user-side
aversions the overlap with F5 taste is genuinely thin territory: taste already carries
`partner:{user_id}`, `shape:{G}x{R}`, position, band, and age attributes, already
down-weights on every pass (−0.5, decayed), and already follows the user. **An
un-gated "user passes on shape S / partner P" prior would be F5 re-implemented at a
different seam.** This PRD's answer is structural, not rhetorical: M1 consumes only
the reason-carrying record, which F5 does not and cannot see (taste updates from
`deck_outcomes` actions only; it never reads `trade_pass_reasons` — memo §2e, §1.4).
If that structural gate is removed in review, the correct response is to shrink M1
further, not to ship the overlap.

### 2.3 Data reality (hard constraint on everything below)

Committed-doc numbers only (memo §8, §1.5):

| Fact | Value |
|---|---|
| Like/pass outcomes, ALL users, 2026-08-19 | ~845 |
| Trade decisions, 2026-08-17 | 810 (496 pass / 314 like) |
| Reason capture live since | 2026-08-17T22:22:56Z |
| D-091 contamination window | 2026-08-16 → 2026-08-19 |
| `deck_suppressions` (decline route) rows, 2026-08-17 | 0 |
| Tester decision supply | ~400 decided cards/week |

Two of these compound viciously: **reason capture went live inside the contamination
window.** Clean, reason-carrying, feature-joinable rejection records — the only rows
M1 v1 consumes — effectively exist from **2026-08-20 onward**. At planning time that
is on the order of *days* of data. Any PRD claiming v1 "learns league dynamics" from
this is describing a feature that does not exist yet. What v1 honestly does is (a)
stand up the consultation seam correctly and (b) start compounding from a clean epoch.

**Cell-count math** (per user-league; ~11 opponents, 9 legal shape buckets, 10 layer-2
codes, 3 layer-1 families):

| Key | Cells | Clean reason rows needed for n≥5/cell | Verdict |
|---|---:|---:|---|
| partner × shape × layer-2 | 990 | ~5,000 | Never at current supply; almost all cells permanently empty |
| partner × shape × layer-1 | 297 | ~1,500 | Months-to-never |
| **partner × layer-1 family** | **33** | ~165 | **Weeks, for an active league — viable** |
| shape × layer-1 family (partner-agnostic) | 27 | ~135 | Viable later; overlaps F5's shape attrs unless reason-gated — deferred (§6) |

At ~400 decided cards/week, ~60% passes, and optimistically ~50% reason attach, an
active league produces ~120 reason rows/week. Only the coarsest key reaches usable
evidence within the feature's first month. **Therefore M1 v1 keys on (partner ×
reason_family) and nothing finer.** Finer keys are a data-gated follow-on (§6), not a
v1 stretch goal.

## 3. Goals & Non-Goals

### 3.1 Goals

- **G1:** Reason-carrying rejections influence the next generation run: candidates
  toward a partner whose (partner, reason_family) cell carries sufficient decayed
  evidence are score-down-weighted at generation time, in every arm, softly.
- **G2:** gen_v2's `acceptance_prior` is fed real per-league-mate response stats at
  both call sites; the stub debt is retired.
- **G3:** Every influence is observable: stamped at serve, reconstructable as-of any
  timestamp from append-only inputs, dumpable on demand (§4.2). No silent effects.
- **G4:** Flag off / strength 0 is byte-identical to today (golden-tested). D-067's
  operator principle is honored structurally: soft, clamped, floored, decaying —
  never an exclusion.
- **G5:** A clean-epoch data pipeline exists so that every future refinement (shape
  dimension, layer-2 tendencies) is a knob-and-key change, not a redesign.

### 3.2 Non-goals (each one is a live scope-creep vector; naming it here is the defense)

- **N1: No hard filtering.** No candidate is removed by this feature, ever, in any
  arm. Hard semantics stay with R4/D-067/untouchables/not-interested. (A "soft prior"
  that multiplies by 0.0 is a hard filter wearing a costume — hence the floor knob.)
- **N2: No shape dimension in v1's key.** §2.3 math. Re-enters via §6 gate.
- **N3: No layer-2 tendency modeling** (per-shape/per-reason partner models). M2's
  aggregate feed is the entire layer-2 surface in v1. See operator decision §7.2.
- **N4: No UI, no explainer, no notification.** "Why am I not seeing X" is a real
  future surface; it re-enters gates on its own with a mobile scope block. v1's
  observability is operator/engineer-facing (readout + stamps).
- **N5: No new tables, no new routes, no new analytics events.** Derive-on-read (memo
  §DC-2); materialization only via the latency-measured LLD gate already in scope §2.
- **N6: No silence-as-signal.** An unanswered proposal is not a decline (M2 counts
  recorded accept/decline decisions only). An unacted impression is not a rejection
  (D-067 put impression-readback out of scope by operator ruling; we cite it, we
  don't relitigate it).
- **N7: No consumption of `other_player_keep` / `other_player_avoid` in v1.** These
  are player-level preferences; the authoritative surface for player-level avoidance
  is #163 not-interested/untouchables. Routing them into a partner-keyed prior
  smuggles a player filter into a partner signal. Follow-on: a separate proposal to
  suggest not-interested additions from repeated `other_player_avoid` free-text —
  different feature, different consent surface.
- **N8: No mining of `sleeper_trades`** (whole-league executed trades, non-users
  included) in v1 — tempting for M2 cold-start, but it changes the data subject and
  the privacy answer (§7.3) and belongs to the layer-2 decision, not the stub feed.
- **N9: No cross-league memory.** League-scoped throughout (memo §DC-8); taste
  remains the user-scoped layer.
- **N10: No modification of F3, F5, D-067, R4, or Thompson semantics.** This feature
  adds one multiplier and one kwarg feed; it edits no existing mechanism.

## 4. Success Metrics

### 4.1 What we refuse to claim

At ~845 lifetime outcomes across all users, an engagement-level metric (pass-rate
delta, acceptance-rate delta, retention) cannot separate this feature from noise in
any v1 window. A single-user league at ~400 decisions/week needs multi-week windows to
detect even a 5-point pass-rate shift, and the serving stack has four other learning
layers moving simultaneously. **Any PRD that gates v1 graduation on an engagement
lift is unfalsifiable theater.** We do not. Engagement effects become claimable only
via bake-off arm attribution over accumulated rounds, later.

### 4.2 Observability of a correctly-working ABSENCE (first-class requirement)

The feature's success state is a deck that *lacks* things. Absences are invisible in
impressions. Three properties make the absence observable anyway:

1. **Reproducibility:** every input (`trade_pass_reasons`, `trade_decisions`,
   `deck_impressions ⨝ deck_outcomes`, `trade_matches`) is append-only or
   timestamped-upsert. The map builder is a pure function of (user, league, as_of).
   Therefore the full prior map — including families down-weighted on candidates that
   were never served — is reconstructable for any past job time. The map IS the
   record of absence. This is a requirement (R6), not an accident: the builder takes
   `as_of` as a parameter from day one.
2. **Stamps on presence:** every SERVED card whose score was multiplied carries
   `features_json.negmem = {m, keys, ev, ver}` (R7). Cards ranked out entirely leave
   no impression — by design; the readout covers them.
3. **Readout on demand:** `negmem_readout(user_id, league_id, as_of=None)` — same
   builder, human-readable dump: every keyed cell, raw and decayed evidence counts,
   resulting multiplier, and which cells are floored (R8). Invocable via script/pytest
   fixture; companion SQL for stamp rates documented alongside the existing readout
   SQL set. The manual TestFlight checklist is built on it: operator runs readout,
   flips flag, regenerates, confirms the named families moved down and *nothing else
   changed*.

### 4.3 v1 metrics (all measurable at current n)

| # | Metric | Target | Source |
|---|---|---|---|
| S1 | Flag-off / strength-0 golden: byte-identical deck output | exact | pytest golden |
| S2 | Clamp invariants: mult ∈ [floor, 1.0]; no gated-card rescue; likes_you exempt | zero violations | unit + stamp audit SQL |
| S3 | Stamp coverage: influenced served cards carrying `negmem` stamp | 100% | spine SQL |
| S4 | M2 parity: aggregation feed reproduces documented E-B math at both call sites | exact | unit |
| S5 | **Dead-family re-serve rate** (primary directional metric): fraction of served cards whose (partner, reason_family) had ≥ `negmem_min_evidence` decayed prior passes at serve time | reported pre/post flag; directional decline expected; NOT a gate | readout SQL, defined in LLD |
| S6 | Deck fill non-regression: cards per completed job | no decline vs trailing baseline | spine SQL |
| S7 | Data accrual: clean reason-carrying joinable rows/week | reported weekly; feeds the §6 gate | SQL |
| S8 | Latency: map build p95 per job | < the LLD-set budget (derive-vs-materialize gate) | timing log |

S5 is the only behavioral metric and it is deliberately a *report*, not a gate: at
current n it will be noisy, and gating graduation on it would invite knob-tuning to a
noise floor. Graduation criteria are in §9.

## 5. Requirements

### 5.1 M1 — generation-time soft prior

- **R1 (key):** map key = `(partner_league_id, reason_family)`; `reason_family` ∈
  {`value`, `fit`} derived from `trade_pass_reasons.reason`, with the taxonomy §2.6
  recode: a `value`-reason pass on a card whose frozen `user_value_basis` is personal
  is **fit evidence, not value evidence** (board-priced, not market-priced). `other`
  layer-1 rows and `other_*` layer-2 rows are excluded in v1 (N7): at 47% "Neither"
  share in the first burst this discards real volume, and we accept that — an
  unroutable reason down-weighting a partner is exactly the false-certainty this lens
  exists to block.
- **R2 (evidence admission):** a rejection record counts iff ALL of: `key_source =
  'impression'` (joinable to frozen features); outcome viewed-gated per the spine
  contract; not ghost (`is_ghost` rows excluded; population ends 2026-08-21T00:43Z);
  serve timestamp outside the D-091 window 2026-08-16T00:00Z → 2026-08-19T23:59Z
  (exclusion by timestamp, both bounds in the LLD as named constants); underlying
  decision not retracted (`trade_decisions.retracted_at IS NULL`); no paired `undo`
  outcome (undo appends alongside — the pair cancels, mirroring F3's `lifted_at` ⇒
  permanently-inert precedent).
- **R3 (math):** per-cell decayed count `w = Σ exp(−Δt/τ)` over admitted records,
  τ from `negmem_halflife_days` (default 45; LLD finalizes). Multiplier
  `m = 1 − s·(w_shrunk / (w_shrunk + k))` clamped to `[negmem_floor, 1.0]`, with
  `s = negmem_strength` (0 ⇒ byte-identical disable), shrinkage constant `k =
  negmem_min_evidence` (cells below meaningful evidence stay ≈ 1.0). Exact functional
  form is an LLD decision; the PRD-level invariants are: monotone in evidence, → 1.0
  as evidence decays to 0, never < floor, never > 1.0, disable value byte-identical
  (memo §DC-9).
- **R4 (application):** one bulk read per (user, league) job builds the map (memo
  §DC-1 — no per-candidate DB reads); consulted in-memory in the per-opponent loops:
  v1/v3 (`trade_service.py:4563` seam), gen_v2 (score multiplier alongside
  `accept_prior`), fit arm (rank score, not the hard step-5 filter — a soft prior in
  a filter stage would be N1 by the back door). Ordering/score only: **candidate
  membership is never changed** (memo §DC-3).
- **R5 (exemptions):** `likes_you` cards are never down-weighted (fresh, explicit
  contradicting evidence from a real human outranks a decayed prior; mirrors F3's
  rule at `server.py:4621`). Cards already carrying a suppression/exclusion are
  simply absent upstream — no interaction.
- **R6/R7/R8 (observability):** as §4.2 — `as_of`-parameterized builder,
  `features_json.negmem` stamp on every influenced served card, readout function +
  documented SQL.
- **R9 (evidence lock-in prevention — the feedback-loop requirement):** the loop
  "prior suppresses family → family never served → no contradicting evidence →
  permanent hole" is broken structurally, three ways, all mandatory:
  (a) **decay is on evidence age, not on refresh** — with no new rejections the cell's
  weight decays toward 0 and the multiplier returns to 1.0 on its own; suppression
  can never sustain itself; (b) **floor** — even at max evidence the family still
  competes at `negmem_floor` (recommended 0.6 in v1 — deliberately higher than F3's
  0.25, because F3 has a retest mechanic and v1 negmem does not); (c) **soft-only**
  — the family keeps being enumerated and scored, so a genuinely good candidate in a
  down-weighted family can still win on merit. A retest/exploration mechanic (F3-style
  one-card low-exposure probe) is explicitly deferred: decay makes it non-essential
  at these half-lives, and it is the single biggest complexity multiplier in F3's
  implementation.
- **R10 (bake-off citizenship):** the prior is part of the model under test.
  `negmem_*` knob values snapshot into `bakeoff_runs.config_json` (memo §DC-7); the
  flag must not flip mid-round for bake-off-channel jobs — flips align to round
  boundaries, stated in the rollout plan (§9). Otherwise arm comparisons spanning the
  flip are contaminated, and we would be manufacturing the next D-091.

### 5.2 M2 — feed the acceptance stub

- **R11:** an aggregation query (derive-on-read, lookback-windowed — recommended
  180d, applied in the query, NOT by modifying the ratified stub math) produces
  `acceptance_stats: {partner_league_id: (accepts, responses)}` where `responses` =
  `trade_matches` rows in this league where that partner recorded an explicit accept
  or decline decision, `accepts` = the accepted subset. Dismissals, expirations, and
  silence count as nothing (N6).
- **R12:** passed at both existing call sites (`trade_service.py:4001`,
  `bakeoff_runner.py:1212`). No knob changes: `gen2_accept_prior_strength` /
  `gen2_accept_global_prior` are already seeded and stay authoritative.
- **R13 (honest effect statement, load-bearing):** with m=10, p0=0.5: 0 responses →
  0.500 (unchanged); 1 decline → 0.455; 3 declines → 0.385; 1 accept → 0.545. And
  the memo's strongest volume datum — `deck_suppressions` = 0 rows at 2026-08-17,
  written on every match decline — implies the decline route had essentially never
  fired league-wide. **Therefore M2's production output is ≈ uniform 0.5 on day one
  and its serving-path effect is ≈ zero until match decisions accrue** — and even
  then, `trade_gen.v2` is OFF; gen_v2 runs only as dark bake-off arm C. M2 is a
  correctness deliverable (S4) measured by parity tests and arm-C stamped values in
  bake-off records, not a user-visible change. Any draft that books user-visible
  impact from M2 in v1 is wrong on the facts.
- **R14:** identity hygiene — league user ids end-to-end (memo §DC-8); a unit test
  asserts no account-id (`acct_`) ever enters the map or the stats dict.

### 5.3 Positioning vs the three existing learners (merge gate, stated honestly)

The PLAN makes this a no-ship gate: a named card-level behavioral difference vs each
of F3, D-067-cooldown, F5 — or no ship. Here they are, including the thin one:

| vs | Card-level difference | Honest assessment |
|---|---|---|
| **F3 fatigue** | F3 keys on *exposure* (views/declines of served cards; trade_hash/centerpiece/archetype) and acts POST-generation on the generated deck. Negmem keys on *reasoned rejection* and acts at generation: a candidate family that has never been served in this composition, toward a partner with accrued reason-evidence, is down-weighted before the deck exists — F3 structurally cannot do this (it needs impressions). | Real difference. |
| **D-067 cooldown** | Exact-pair, hard, windowed (14d). Negmem is family-level, soft, decaying. Pass `A→X for B` yesterday: cooldown blocks exactly that pair; negmem additionally dampens `A→X for B'` — but only once the (partner, family) cell has ≥ min-evidence, and never to zero. | Real difference — and exactly the territory D-067's alternatives rejected *as a hard filter*, which is why v1 is soft-only and why §7.1 asks the operator before build. |
| **F5 taste** | **Thin, and we say so.** For reason-blind pass behavior, taste already covers partner and shape aversions (post-gen, user-scoped, cosine over shared attrs). Negmem's only defensible deltas are: (1) it consumes `trade_pass_reasons` — a table taste never reads — so it distinguishes "passed for value" from "passed for fit" and applies the §2.6 personal-basis recode, which cosine-over-attrs cannot express; (2) league scope (a user's aversion to partner P in league L does not follow them to league L2; taste smears it); (3) generation-time placement. Delta (3) alone would NOT justify the feature (a score multiplier at gen vs a re-rank multiplier post-gen converge to similar served decks when candidate supply exceeds deck size). Deltas (1)+(2) are the feature. If cross-review strips the reason-gating (R1/R2), the correct verdict is that M1 duplicates F5 and should be cut to M2-only. | Thin but real, *conditional on reason-gating staying mandatory*. |

## 6. Scope & Phasing

- **P0 — M2 + harness (0.5d + shared harness):** aggregation query, two call sites,
  parity tests, arm-C stamp verification. Ships regardless of §7 rulings (it is the
  memo's §DC-10 "feed the existing hook first" and touches no contested territory).
- **P1 — M1 coarse prior (≈2.5d):** builder (R1–R3, R6), consultation seams (R4, R5),
  stamps + readout (R7, R8), knobs + dispositions + seed rows, goldens, code-walk,
  TestFlight checklist, docs per scope §4. Gated on operator ruling §7.1.
- **P2 — DEFERRED, each behind a stated re-entry gate:**
  - Shape dimension in the key: enters when S7 accrual shows ≥ `n≥5` median evidence
    across (partner × shape × family) cells for the operator's league over a trailing
    30d — a readable number, not a vibe. Additive knob/key change on the P1 builder.
  - Layer-2 tendency modeling: §7.2 — recommendation is defer entirely.
  - Explainer UI, retest mechanic, `other_player_*` → not-interested suggestion flow,
    `sleeper_trades` cold-start: separate features, separate gates.

Estimates match PLAN §3 (W1–W5 ≈ 5d total); P0 is severable and could land alone.

## 7. The three operator decisions — presented with this draft's recommendations

### 7.1 D-067 family-level ruling

**Question:** does "accuracy over volume; one swipe must not silence a player's whole
trade space" permit *soft* family down-weighting, and at what floor?
**Recommendation:** yes, with the structural guarantees of R9 (age-decay, floor 0.6,
soft-only, likes_you exempt) and min-evidence ≥ 3 decayed passes before any cell
leaves 1.0 — so no single swipe moves anything, which honors the ruling's literal
text. **If the operator says no:** the feature ships as M2-only (P0); M1 is shelved
with the builder design retained. That degraded outcome is acceptable and should be
said now, not discovered later.

### 7.2 Layer-2 v1 boundary

**Recommendation (more conservative than the memo's optimistic reading): v1 layer-2 =
M2's aggregate feed, full stop — and defer per-shape/per-reason tendency modeling
entirely, with no scheduled follow-on.** Reasons: (a) R13's math — even the aggregate
signal is ≈ uniform today; a finer partition of ≈ zero data is exactly zero data with
more code; (b) the counterparty-breaker sibling already owns "why would THIS manager
say no" via deterministic present-state analysis, which at current volumes will beat
any behavioral model we can fit — revisit only if/when the breaker's deterministic
answer and accrued response data start disagreeing measurably; (c) it keeps the §7.3
privacy surface at its minimum. Widening this boundary requires a new scope block,
not a knob.

### 7.3 Privacy — modeling league-mates who never installed the app

**Facts (memo §7):** the system already stores every league-mate's roster, username,
and executed trades regardless of installation; `user_taste` already carries
per-partner affinity attrs; gen_v2's interface is explicitly per-manager. The new
step layer 2 would take: **inferred behavioral tendencies of a person who never
consented to be modeled** — their platform's public league data is one thing; a
derived profile of their negotiation behavior is a different data subject
relationship, and `accounts.delete_user_data` has no path for rows keyed by a
*partner's* id because no such rows have ever existed.

**Options, stated honestly:**
- (a) Full layer 2 (per-shape/reason tendencies, stored): maximum signal, creates the
  first dedicated inferred-profile records of non-consenting non-users; needs a
  deletion-path answer on day one.
- (b) App-users only: consent-cleaner, but partners are pseudonymous league ids —
  distinguishing "app user" partners adds an identity join and shrinks the already
  tiny n further; mostly theater at current scale.
- (c) **Aggregate-only, engine-internal, derive-on-read (recommended):** M2's
  (accepts, responses) counts — computed transiently per job from `trade_matches`
  rows that already exist, never stored per-person, never surfaced in any UI, never
  phrased as a claim about the person ("P rarely accepts") anywhere user-visible.
  No new data at rest ⇒ no new deletion surface ⇒ the consent posture is unchanged
  from what shipped with `trade_matches` itself. M1 is unaffected: its records are
  the *app user's own* stated reasons — the partner id is context, not subject.
- (d) Defer layer 2 entirely: strictly safest; but (c) is materially equivalent at
  rest and retires the stub debt.

**Recommendation: (c), with (d) as the fallback if the operator is uncomfortable —
and a standing rule either way: no inferred-tendency claim about a named league-mate
ever appears in a user-facing surface without a fresh operator ruling.** (Trade
narrative copy is deterministic templates today — `trade_narrative.py` — keep it
that way on this axis.)

## 8. Dependencies & Risks

**Dependencies:** shared taxonomy v1.0.0 (adopted; v1.1.0 additive at three-way
reconciliation — rejection vocabulary anchored on shipped `trade_pass_reasons`
codes); Receipts contract (`receipts_` namespace theirs, `negmem_` reserved-unused);
breaker boundary (behavioral-historical vs deterministic-present, already drawn);
operator rulings §7.1–§7.3; bake-off round calendar (R10); `server.py`/`database.py`
line numbers re-verified at build (memo header warning).

| Risk | Likelihood | Handling |
|---|---|---|
| v1 learns ~nothing for weeks (clean reason data starts 2026-08-20) | Certain | Framed honestly in §4; success = correctness + accrual (S7); no engagement claims; the feature is priced at ~5d partly BECAUSE its near-term effect is small |
| F5 overlap in practice (thin-delta layer) | Medium | Structural reason-gating (R1/R2) is a merge gate; if stripped, cut M1 to M2-only (§5.3) |
| Evidence lock-in / permanent holes | Medium | R9: age-decay (self-healing), floor 0.6, soft-only, likes_you exempt; retest deferred deliberately |
| Multiplier compounding (negmem × taste × fatigue × Thompson stacks) | Medium | Negmem floored at 0.6 and gen-time (different stage); S2 stamp audit reports the joint multiplier distribution; if p5 of joint mult < 0.15, raise floors — a numeric tripwire, not a hope |
| Small-n false certainty (1–2 passes condemn a partner) | High without guards | `negmem_min_evidence` ≥ 3 decayed; shrinkage form in R3; unit-tested |
| M2 self-fulfilling prior (low prior → fewer proposals → fewer responses) | Low at m=10 | Shrinkage keeps floor ≈ 0.45 at small n; 180d lookback window; monitor via arm-C stamps |
| Training-data contamination recurs | Medium | R2's admission list is closed and constant-encoded; D-091 window excluded by timestamp; ghost boundary respected; contamination handling is unit-tested, not convention |
| Bake-off contamination from mid-round flips | Medium | R10: round-boundary flips + config_json snapshot |
| Operator rules "no" on §7.1 | Possible | P0 severable; M1 shelved cleanly — stated up front, not a failure mode |
| Latency of derive-on-read at future volumes | Low now | S8 measured budget; materialization gate stays in LLD as designed (scope §2) |
| Reconciliation drift across three sibling plans | Medium | Contract-level reconcile only (namespaces, taxonomy semver, seam registry); prose is not binding |

## 9. Rollout & Measurement

1. **Dark:** merge with `trade.negmem` false + `negmem_strength` 0. Goldens prove
   byte-identity. M2 feed live but output ≈ uniform (R13) — parity tests + arm-C
   stamps are the evidence.
2. **Operator league:** flag on for the operator's device/league at a bake-off round
   boundary (R10). TestFlight checklist: run `negmem_readout` before/after, verify
   named cells only, verify deck fill (S6), verify stamps (S3).
3. **Hold:** ≥ 2 weeks accruing clean reason data; weekly S5/S6/S7 readout — reported,
   not gated.
4. **Graduation to default-on:** ALL of — zero S2 invariant violations; S3 = 100%;
   S6 non-regression; S8 within budget; operator sanity sign-off; AND S7 shows the
   operator's league crossed min-evidence on ≥ 5 (partner, family) cells — i.e. the
   prior is demonstrably *doing* something before we turn it on for people who can't
   read the stamps. Engagement claims remain bake-off-attributed and later.
5. **Rollback:** flag off (full), or `negmem_strength = 0` (deploy-free, byte-identical
   — memo §DC-9). Both golden-tested.
6. **Ledger:** TEST_LEDGER rows for goldens, parity, latency; CHANGELOG on merge;
   knob dispositions per the arm-A inventory guard; docs per scope §4 table.

---

*Cross-review note for Agent A: the three places this draft expects to fight are (1)
the key coarsened to partner × reason-family with shape deferred behind a numeric
gate, (2) M2 booked as a correctness deliverable with ≈ zero day-one serving effect,
and (3) layer-2 tendency modeling deferred with no scheduled follow-on. Each is
argued from the memo's own numbers; bring different numbers, not different vibes.*
