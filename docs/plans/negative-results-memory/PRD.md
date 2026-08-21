# PRD: Negative-results memory

**Version:** FINAL — dual sign-off, round 4 of 4 (reconciliation log: [reconciliation-log.md](reconciliation-log.md))
**Date:** 2026-08-21 · **Home:** docs/plans/negative-results-memory/ · Facts: [research-verification.md](research-verification.md) ("memo") · Gates: [scope.md](scope.md) · Drafts: [PRD-draft-A.md](PRD-draft-A.md), [PRD-draft-B.md](PRD-draft-B.md)

---

## 1. Summary

Rejected trade suggestions currently teach the engine almost nothing: the swipe lands in
append-only logs, exact repeats are windowed out for 14 days, and the next generation
run starts from roughly the same place. This feature gives each league a **memory of
reasoned rejections** — keyed by league-mate and rejection-reason family, decayed and
shrunk, with context tags read from the card's serve-time-frozen features — consulted by
every generation arm as a **soft, clamped, stamped down-weight** (M1), plus the
**feeding of gen_v2's already-ratified but unfed per-manager acceptance prior** (M2,
memo §2f). It is deliberately NOT a fourth suppression mechanism: it is soft (never
excludes), reason-aware (consumes `trade_pass_reasons`, which no existing learner
reads), league-scoped, generation-time, and fully auditable — every influence stamped at
serve, every absence reconstructable as-of any timestamp.

## 2. Problem & Context

### 2.1 The user problem

Testers are asked to decide ≥40 cards/week each; the base is budgeted at **~400
decided cards/week** across ~10 testers, with a recent peak of ~200 decisions across
4 days from 5 testers (memo §8; `docs/plans/trade-engine-accuracy/PLAN.md` appendix). When they
pass, they file reasons: **208 coded rows in the first days — 40% `value_giving`, 33%
`fit_outlook`** (`trade-engine-accuracy/PLAN.md` appendix; CHANGELOG 2026-08-20). Their
strongest complaint class after value/fit is déjà vu: cousins of dead trades keep coming
back — same partner, same objection, one asset swapped. Every existing defense is either
exact-pair (D-067 cooldown), exposure-based (F3 fatigue — needs the card to have been
*served*), or reason-blind (F5 taste). Nothing in the system can express "this manager
has now told us three times, with reasons, why this *kind* of trade doesn't work for
them."

### 2.2 Data reality (hard constraint on everything below)

Reason capture (`trade_pass_reasons`) went live 2026-08-17 — *inside* the D-091
contamination window (2026-08-16→08-19) — so **clean reason-carrying data starts
~2026-08-20** (the "clean epoch"). Volumes (memo §8): ~845 lifetime like/pass outcomes;
~400 decided cards/week; and — a **derived estimate**, not a memo fact — roughly ~120
clean reason rows/week for an active league (400 × ~60% pass × ~50% reason-attach).
Cell arithmetic for candidate M1 keys (12-team league: 11 partners; 9 shapes; layer-2 ≈
10 codes; layer-1 = 3 families of which **2 are admitted to M1** — see R2):

| Key | Cells | Verdict |
|---|---:|---|
| partner × shape × layer-2 | 990 | permanently sparse — never |
| partner × shape × layer-1 | 297 | months-to-never |
| **partner × admitted reason-family** | **22** (11 × {value, fit}) | **usable within weeks — the v1 key** |

**Therefore M1 v1 keys on `(partner_league_id, reason_family)` with
`reason_family ∈ {value, fit}` and nothing finer.** `shape_bucket` (shared-taxonomy
§2.1) is *recorded* on every evidence row so finer keys are a data-gated knob change
later (§6 P2), not a redesign.

### 2.3 The two layers, and which is v1

1. **Layer 1 — user-side memory (v1, M1):** what THIS user rejects, with reasons, per
   league-mate. The engine respects it.
2. **Layer 2 — league-mate tendency modeling (v1 = seed only, M2):** inferred
   acceptance patterns of other managers. v1 feeds the existing `acceptance_prior` stub
   with aggregate response stats; full per-shape/per-reason tendency modeling is
   deferred (§8.1 D2).

### 2.4 Sibling boundaries (contract text quoted verbatim; commentary outside quotes)

**Receipts** (session `trade-suggestions-review-69c9eb-f4`) — from the constraints of
record (README.md): the two features are halves of one loop —

> "Receipts grades what we suggested; this remembers what died so it isn't
> re-generated."

This feature never grades suggestions against value movement; that is Receipts'
territory (NG3).

**Counterparty breaker** (session `trading-engine-eval-8ab7bc-31`) — boundary text as
recorded and mirrored in both plans:

> "breaker = deterministic present-state analysis; this feature = historical behavioral
> prior from observed rejections. Potentially feeding each other later; separate
> mechanisms, separate owners now."

Commentary (not part of the quoted contract): this feature's context tags are read from
the card's serve-time-frozen features and never recomputed — nothing here evaluates
present state (that is the breaker's side). The future coupling ("does this objection
still apply today" = memory→breaker query) is documented in both plans and built in
neither v1. Per breaker decision 7b, `shape_aversion` enters the shared taxonomy with
**producer = negmem**; the breaker cites it only via the future coupling.

**Namespace reservation (three-way):** `negmem_` is this feature's reserved table/knob
prefix; `receipts_` is the sibling's; the breaker has reserved `breaker_` (v1 may use
none). v1 of this feature creates **no tables** (NG6) — the prefix is reserved, not yet
spent.

**Shared taxonomy:** `docs/plans/shared/trade-shape-taxonomy.md` v1.0.0 adopted
verbatim; this PRD proposes the v1.1.0 additive section (rejection/objection vocabulary
anchored on shipped `trade_pass_reasons` codes + PRODUCER column).

## 3. Goals & Non-Goals

### Goals
- **G1:** Reasoned rejections change the next generation run: a candidate toward a
  partner whose (partner, reason-family) cell holds sufficient decayed evidence is
  down-weighted at generation time, in every arm, softly.
- **G2:** gen_v2's `acceptance_prior` is fed real per-league-mate response stats at both
  call sites; the stub debt is retired with parity-tested math.
- **G3:** Every influence is observable: stamped at serve; the prior map reconstructable
  as-of any timestamp (on admission and netting-event timestamps — see R6); dumpable on
  demand. No silent effects.
- **G4:** Flag off / strength 0 is byte-identical to today (golden). D-067's principle
  honored structurally: soft, clamped, floored, decaying — never an exclusion.
- **G5:** A clean-epoch pipeline such that every refinement (shape key, layer-2
  tendencies) is a knob/key change on the same builder.

### Non-Goals (scope-creep defenses)
- **NG1:** No hard suppression, ever, at any evidence level (D-067).
- **NG2:** No present-state counterparty evaluation (breaker's territory).
- **NG3:** No grading of suggestions against value movement (Receipts' territory).
- **NG4:** No per-shape or per-reason league-mate tendency model in v1 (D2).
- **NG5:** No user-facing UI (explainer/retest surfaces are separate features with
  their own gates; scope §3 waiver).
- **NG6:** No new tables in v1 — derive-on-read; materialization only if the LLD's
  latency gate is measured as failing (memo §DC-2).
- **NG7:** No Elo/value consequences — the memory changes which candidates lead, never
  how assets are priced.
- **NG8:** No consumption of *unacted served* impressions as negative evidence (D-067
  put impression-readback out of scope; see R1's closed admission list).
- **NG9:** No modification of any neighboring mechanism's semantics — F3 fatigue,
  D-067 cooldown, F5 taste, R4 exclusion, Thompson — in this build. Composing with
  them is in scope; "improving" them is not.

## 4. Success Metrics

All metrics computable from existing instrumentation; no new events. All windows
exclude D-091 (2026-08-16→08-19); "never shown" analyses respect the ghost boundary
2026-08-21T00:43Z.

### 4.1 Correctness set (gates — must be green to ship at all)
| # | Metric | Target | Source |
|---|---|---|---|
| C1 | Flag-off / strength-0: byte-identical decks on EVERY generation path, incl. arm C with the M2 feed disabled (flag off ⇒ `acceptance_stats` not passed) | exact | pytest goldens (serving path + arm-C) |
| C2 | Clamp invariants: mult ∈ [`negmem_floor`, 1.0]; sink-never-rise; no gated-card rescue; likes-you injections exempt | zero violations | unit + stamp-audit SQL |
| C3 | Stamp coverage: 100% of influenced served cards carry `features_json.negmem` | 100% | spine SQL |
| C4 | M2 parity: feed reproduces the documented E-B math at both call sites | exact | unit |
| C5 | Map-builder determinism: same (user, league, as_of) → same map | exact | unit |

### 4.2 Primary directional metric — Repeat-family pass share (RFPS)
Among *viewed* pass/not_interested outcomes, the share whose card's
`(partner, reason_family)` already held ≥ `negmem_min_evidence` decayed rejections at
`served_at`. Family membership reconstructed from frozen `features_json` +
`trade_pass_reasons` — the baseline is computable retroactively and **pre-registered
before any code ships**. Pre-registered numerator rule: a viewed rejection WITHOUT an
admitted reason row (e.g. a bare `not_interested`) counts in the numerator iff ANY
admitted `(partner, ✱)` cell held ≥ `negmem_min_evidence` at `served_at` — the rule is
fixed here so the metric cannot be defined two ways after the fact. Read per bake-off arm (negmem knobs snapshotted in
`bakeoff_runs.config_json`). Id hygiene: the spine's `partner_user_id` is a global
platform id (memo §2e) while the map keys league identity (R9) — the readout SQL
documents the mapping so the metric join cannot silently violate R9. The exact
promotion rule lives in §8.3.

### 4.3 Secondary / verification
| # | Metric | Note | Source |
|---|---|---|---|
| S1 | Viewed like-rate per arm | hold or rise | spine SQL |
| S2 | Propose rate per arm | must not degrade | spine SQL |
| S3 | Stamp magnitude distribution | alive, clamped, not floor-saturated | stamp-audit SQL |
| S4 | Acceptance-prior spread (M2) | **expected null until match-decision volume exists** (the decline route has essentially never fired — memo §2c/§8); a uniform read is not a bug | aggregation-query output + config snapshot |
| S5 | Weekly clean-reason-row accrual | feeds the P2 re-entry gate | SQL |
| S6 | Map-build p95 latency | the derive-vs-materialize gate input | timing log |

### 4.4 Guardrails
- **GR1** deck supply: median cards/job within 10% of negmem-OFF arms.
- **GR2** not-interested rate must not rise.
- **GR3** no re-ranker/bake-off contamination: generation-time only; flag/knob flips
  align to bake-off ROUND BOUNDARIES (a mid-round flip censors the window — ADR-014).
- **GR4** multiplier-compounding tripwire: the JOINT product of soft layers
  (negmem × taste × fatigue × Thompson propensity) is audited from stamps; if its p5
  drops below 0.15, floors are raised — four soft layers must never compound into a
  de-facto exclusion.

## 5. Requirements

### 5.1 User stories
- As a manager, when I pass on a trade *and say why*, the app should stop showing me
  cousins of that trade for that partner — without ever hiding a genuinely new idea
  forever.
- As the operator, I can see exactly what the memory believes for any league at any
  point in time, and turn it off (or to zero) with byte-identical results.
- As a league-mate (possibly not an app user), no per-person dossier is exposed to
  anyone; anything learned about my responses only shapes which suggestions others see.

### 5.2 Functional requirements (numbered, testable)
- **R1 — Evidence admission (closed list; ALL criteria, one place).** A qualifying M1
  negative-evidence event is a `deck_outcomes` pass/`not_interested` row that is:
  (a) **viewed-gated** (fronted card, F1 join);
  (b) **reason-carrying** — joined to a `trade_pass_reasons` row keyed
      `key_source='impression'` whose layer-1 family is **admitted** (R2);
  (c) **not a ghost** (`is_ghost` ≠ 1);
  (d) **not retracted** — the underlying decision has `retracted_at IS NULL` and no
      paired `undo` outcome negates it (LLD note: `deck_outcomes` rows and
      `trade_decisions` rows share no direct key — the join path must be specified;
      and `retracted_at` is in practice set only on like-side rows via
      awaiting-dismiss, so the pass-side retraction signal is the paired `undo` —
      the dual check is correct but asymmetric);
  (e) **inside the clean epoch** — `served_at` ≥ 2026-08-20 and outside D-091.
  Each admitted event yields an in-memory evidence row
  `(league_id, user_id, partner_league_id, reason_family, shape_bucket, context_tags,
  ts)` — derived on read, never stored (NG6). `trade_matches` declines are **not** M1
  evidence (they are reason-less; they feed M2 via R5 only).
- **R2 — Reason-gating is constitutive; the admitted family set is {value, fit}.**
  The `other` family — including `other_player_keep`/`other_player_avoid` (47% of the
  first burst, memo §1.4) — accrues **no** M1 evidence: an unroutable reason must not
  down-weight a partner, and player-level objections do not belong in a partner-keyed
  prior (they are a future input to untouchables/not-interested suggestion flows — a
  separate feature). Unknown future layer-2 codes map to their layer-1 family; if that
  family is not admitted, they are excluded. `value_*` reasons on cards with
  `user_value_basis='personal'` are tagged as board-fit evidence, not market-value
  evidence (taxonomy §2.6). If reason-gating is ever removed, M1 collapses into
  F5-taste territory and the correct action is cutting M1 to M2-only (§5.5).
- **R3 — The map.** One bulk read per (user, league) job builds
  `{(partner_league_id, reason_family): {n_raw, n_decayed, mult}}` with exponential
  decay (`negmem_halflife_days`), shrinkage floor (`negmem_min_evidence` — cells below
  it are identity), and clamp `mult ∈ [negmem_floor, 1.0]`. Defaults (LLD finalizes):
  floor 0.6, min-evidence 3, half-life 45d. Builder takes `as_of` (R6).
- **R4 — Consultation.** The map multiplies candidate scores inside the per-opponent
  loops of every arm (v1/v3, gen_v2, fit — seams per memo §2h), AFTER all gates:
  membership is never affected; order is. Likes-you injections are exempt (partner
  already signaled intent).
- **R5 — M2 feed (flag-gated with M1).** An aggregation over `trade_matches` responses
  + declines per league-mate (lookback window applied **in the query**, default 180d —
  the ratified E-B formula itself is untouched; LLD finalizes) supplies
  `acceptance_stats` to gen_v2's two call sites when `trade.negmem` is ON; flag OFF ⇒
  the kwarg is not passed and arm C is byte-identical (C1). Existing seeded knobs
  govern strength; parity test per C4.
- **R6 — As-of reproducibility (with the upsert caveat).** The builder is a pure
  function of (user, league, as_of) over admission timestamps AND like-netting event
  timestamps (§5.3 — positive evidence moves the map and is part of the same as-of
  domain); the full map — including
  families whose candidates were never served — is reconstructable for any past job
  time. Caveat stated honestly: `trade_pass_reasons` is an upsert that keeps one
  `switched_from` hop, so a reason row is evaluated at its current state; perfect
  historical replay of switched reasons is not claimed.
- **R7 — Stamps.** Every served card whose score was multiplied carries
  `features_json.negmem = {m, keys, ev, ver}`; never absent on influenced rows
  (executemany discipline).
- **R8 — Readout.** `negmem_readout(user, league, as_of)` dumps every cell (raw and
  decayed counts, multiplier, floored?) for scripts/pytest; companion SQL joins stamp
  rates per arm into the existing readout pack, including the GR4 joint-multiplier
  audit and the §4.2 id-mapping. The operator TestFlight checklist is built on it.
- **R9 — Identity.** All partner keys are LEAGUE identities (`_league_user_id`
  contract); account ids never enter the map (memo §DC-8).
- **R10 — Knobs.** `negmem_strength` (0 = byte-identical disable), `negmem_floor`,
  `negmem_min_evidence`, `negmem_halflife_days` — each with `_MODEL_CONFIG_DEFAULTS`
  seed row, `_PINNED_KNOBS` entry, arm-A disposition sentence, and
  `bakeoff_runs.config_json` snapshot coverage.
- **R11 — Context tags (v1: recorded, not consulted).** `context_tags` on an evidence
  row are read at admission time from serve-time-frozen card state: `lane` and
  `user_value_basis` from `features_json`; `trade_intent` from the
  `deck_impressions.trade_intent` COLUMN (it is not a `features_json` key — it is
  NULL unless the card's own arm ran under an intent lens — non-bake-off rows always,
  and bake-off rows whose arm had no intent; the readout annotates rather than treats
  NULL as a bug). Nothing is recomputed and nothing is
  written at rejection time (NG6-consistent). v1 semantics: recorded in
  evidence rows and surfaced in the readout **only**; no behavioral use. They exist so
  the P2 refinements and the breaker coupling have context to condition on without a
  redesign ("regime-tagged" in earlier docs = these tags).

### 5.3 States & edge cases
Empty league / no evidence → identity map, zero stamps. New league-mate → identity
until min-evidence. **Evidence lock-in prevention:** decay + floor + min-evidence mean
a floored family still serves (soft ≠ hidden), and — **like-netting:** a *viewed like*
on a card toward partner P nets against **every (P, ✱) family cell** (a like carries no
reason code, so it cannot target one family; netting magnitude and decrement-vs-reset
are LLD decisions — the PRD requires only that positive evidence nets and that the
mechanism is stamped in the readout). Mid-week taxonomy extension (v1.1.0) → unknown
codes map to their layer-1 family per R2. Co-owned rosters → league identity per
ADR-012. Deleted user data → derive-on-read means deletion of source rows is deletion
of memory (no orphaned aggregates) — a stated reason for NG6.

### 5.4 Non-functional
Latency: map build inside the existing job budget — p95 measured (S6), materialization
only on measured failure (NG6). Privacy: §8.1 D3 — recommended posture (c)
aggregate-only, engine-internal, derive-on-read; no per-person surface anywhere;
symmetric for app and non-app league-mates; nothing persisted per-person beyond the
already-existing spine. Bake-off citizenship: GR3. Analytics: no new events (scope §1);
the stamp is a data-dictionary row.

### 5.5 Why this is not a fourth mechanism — MERGE GATE (stated honestly)

| vs | Card-level difference | Honest assessment |
|---|---|---|
| **F3 fatigue** | F3 keys on *exposure* of served cards (trade_hash/centerpiece), post-generation. Negmem down-weights a candidate family **never yet served in that composition** — F3 structurally cannot (no impression exists). Conversely a served-but-unacted card fatigues under F3 and contributes nothing to negmem (NG8). | Real. |
| **D-067 cooldown** | Exact-pair, hard, windowed. Negmem: family-level, soft, decaying — dampens the *cousin* the cooldown has never seen; removes nothing, ever. | Real — and precisely the territory D-067 rejected *as a hard filter*, hence soft-only + the §8.1 D1 ruling. |
| **F5 taste** | **Thin, and we say so.** Taste already covers reason-blind partner/shape aversions (user-scoped, post-gen, can *boost* up to 1.4×). Negmem's defensible deltas: (1) consumes `trade_pass_reasons` — taste never reads it — distinguishing "passed for value" from "passed for fit" incl. the personal-basis tag; (2) league-scoped (aversion to partner P in league L doesn't follow the user to L2; taste smears); (3) sink-never-rise. Delta (3) alone would NOT justify the feature. **Deltas (1)+(2) are the feature — hence R2 is constitutive.** | Thin but real, conditional on R2. |

If a difference above cannot be defended at review time, the feature (or the failing
mechanism) does not ship. Occupied niche: league-scoped · generation-time ·
family-level · reason-aware · soft · auditable — no existing mechanism has more than
two of the six (memo §2).

## 6. Scope & Phasing

- **P0 — M2 + harness:** aggregation feed, two call sites, parity tests, arm-C stamp
  verification. **Severable = independent of the operator rulings D1–D3** (uncontested
  territory, memo §DC-10) — but still behind `trade.negmem` (R5), so "ships regardless
  of rulings" never means "live regardless of the flag."
- **P1 — M1 coarse prior:** builder + seams + stamps + readout + knobs + goldens +
  code-walk + TestFlight checklist + docs. Gated on operator ruling D1.
- **P2 — deferred behind numeric re-entry gates:**
  - **Shape dimension in the key** — enters when ≥20 (partner × shape × admitted-family)
    cells for the operator's league hold decayed evidence ≥ `negmem_min_evidence` over
    a trailing 30d (an achievable count threshold; the earlier "median ≥5 across all
    cells" formulation was unsatisfiable by §2.2's own table and is retired).
  - Layer-2 tendency modeling (D2 — recommend defer) · explainer UI ·
    `sleeper_trades` cold-start priors · `other_player_*` → untouchables/not-interested
    suggestion flow.

## 7. Dependencies & Risks

Dependencies: shared taxonomy v1.0.0 must LAND ON MAIN (today it exists only on the
Receipts session's unmerged branch — a builder starting from origin/main cannot read
it; land or vendor before build) and v1.1.0 (three-way sign-off; authorship of the
additive section to be reconciled — this PRD and the breaker's plan both propose
overlapping text with converged content); serving rounds running (ADR-014) for
arm-attributed measurement; Receipts' contract (namespace + seam registry); no code
dependency on breaker.

| Risk | Handling |
|---|---|
| M1/F5 overlap in practice | R2 constitutive; merge-gate honesty row; if stripped → cut to M2-only |
| Evidence lock-in (prior starves its own counter-evidence) | soft floor (family still serves) + decay + like-netting (§5.3) + min-evidence |
| Soft-layer compounding into de-facto exclusion | GR4 joint-multiplier tripwire with a numeric bar |
| Bake-off contamination | GR3: round-boundary flips, snapshotted knobs — else the running rounds become the next D-091 |
| Small-n false learning | shrinkage mandatory; coarse key; admitted-family restriction; §8.3's exact rule |
| Privacy of modeling non-users | D3 options to operator; recommended (c) keeps everything aggregate + derive-on-read |
| Cold start (weeks of near-identity maps) | honest: v1 accrues from the clean epoch; RFPS baseline pre-registered; no fabricated day-one claims |

## 8. Rollout & Measurement

### 8.1 The three operator decisions (present before build — scope §6)
1. **D1 — D-067 family-level ruling.** Recommendation: **YES to soft family
   down-weighting** — floor-clamped (0.6 default), min-evidence 3, decaying, stamped,
   deploy-free-revertible. D-067's line targeted hard exclusion and unacted
   impressions; both are honored (NG1, NG8). The floor value is the operator's to
   move. **If the ruling is NO:** P0/M2 ships alone; M1 is shelved with the builder
   design retained (the readout and evidence definitions survive as analysis tooling).
2. **D2 — Layer-2 v1 boundary.** Recommendation: **v1 = M2 stub feed only** (aggregate
   acceptance stats; ratified math; zero schema). Full tendency modeling deferred —
   cells would be empty at current n anyway (§2.2).
3. **D3 — Privacy.** Options: (a) full layer 2 · (b) app-users only · (c)
   **aggregate-only, engine-internal, derive-on-read (recommended)** · (d) defer
   layer 2 entirely. (c) yields M2's full value, persists nothing per-person, treats
   app and non-app league-mates symmetrically, and makes data deletion structural
   (derive-on-read: deleting source rows deletes the memory).

### 8.2 Rollout
Dark (flag off, goldens green) → operator flips `trade.negmem` **at a bake-off round
boundary** — flags are global (`config/features.json`), so league scoping uses the
established allowlist pattern (`config/tester_allowlist.json` precedent; exact
mechanism is an LLD decision) → ≥4-week arm-attributed read → graduation per §8.3.

### 8.3 Graduation (the exact pre-registered rule)
Ship gates: C1–C5 green for the whole window. Promotion decision on RFPS, evaluated
once at window close (never mid-window; knobs frozen for the window):
- **Promote:** 95% CI of the relative reduction excludes zero **AND** the point
  estimate is ≥ 25%.
- **Hold + explicit operator call:** CI excludes zero in the IMPROVING direction but
  the point estimate is < 25% (the operator branch is reserved for weak-positive
  results).
- **Shelve (worsening):** CI excludes zero in the worsening direction — regardless of
  magnitude.
- **Shelve:** CI includes zero at adequate n (pre-registered power: the n at which a
  25% true reduction would be detected with 80% power — computed in the LLD from the
  pre-registered baseline).
- **Extend the window:** n inadequate for the above — extend, never fabricate; the LLD
  sets a max-extension review trigger (operator review at 2× the planned window, in
  the D-099 review-trigger style) so an underpowered window cannot extend silently
  forever.
Any guardrail breach at any time → `negmem_strength = 0` (deploy-free), window
censored at the flip timestamp.
