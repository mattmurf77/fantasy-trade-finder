# PRD — Counterparty breaker (DRAFT A — Product/User lens)

**Date:** 2026-08-21 · **Status:** DRAFT for dual-agent cross-review (lens A of the PRD loop).
**Binds under:** [PLAN.md](../PLAN.md) (authoritative) → [HLD.md](../HLD.md) (converged) →
[LLD.md](../LLD.md) (converged) → this PRD (binds tightest on product surface, copy, rollout,
and the decision register; it may not contradict the LLD's mechanics — where it wants to, it
says so and flags for cross-review). Scope block: [scope.md](../scope.md).
**Rule of restraint:** this PRD cites the HLD/LLD by section rather than restating mechanics.
Anything mechanical stated here that disagrees with the LLD is a defect in this document.

---

## 1. Summary

The trade engine argues exactly one side of every trade. The breaker is a deterministic
evaluation layer that, for every served trade card, predicts **the counterparty's most likely
reason to say no** — in the exact vocabulary the app already uses to record decline reasons —
stamps it for measurement, and (behind a second flag, per-class graduation, and an operator
TestFlight pass) renders the top objection as **one hedged, roster-fact-grounded sentence** on
the card:

> *Their likely hesitation: their roster leans rebuild, and this sends them a 31-year-old RB.*

v1 kills nothing, reorders nothing, filters nothing (HLD NFR-1). It turns the card from a
calculator into a scout: the user learns what to pre-empt in their pitch, and the app finally
argues the other seat. Deck composition changes (filter/demote) are v2, weighed in §6 but
explicitly not committed — they must earn their existence from v1's calibration data.

Two flags: `trade.breaker` (dark stamp, measurement only) and `trade.breaker_narrative` (the
sentence, mobile-only in v1). Both default false. Deterministic end to end; **no LLM anywhere
in v1** — any LLM involvement is a separate, explicit operator decision (register item 2).

## 2. Problem & Context

**The user brief** (trade-engine-accuracy PLAN, 2026-08-20): *"Trade suggestions aren't
getting much better with every iteration… I need a clear plan for how we actually get this
model in a better spot before I can launch."*

**What the evidence says the problem is** — the suggestions are one-sided, users can tell,
and nobody sends them:

| Evidence | Number | Source |
|---|---|---|
| 1-for-1 cards existing in only one direction | **96.3%** | arm-B audit, [docs/reviews/2026-08-19-armb-audit-consolidated.md](../../../reviews/2026-08-19-armb-audit-consolidated.md) |
| Served cards that never consult a partner board | 84.5% | arm-B audit |
| Consensus-path cards where the viewer receives more than they give | 86.3% | arm-B audit |
| Real trades ever sent through the app (`deck_outcomes.action='propose'`) | **0, all-time** | trade-engine-accuracy PLAN §G1 |
| Filed pass reasons: `value_giving` / `fit_outlook` | 40% / 33% (n=208) | trade-engine-accuracy PLAN §G3 baseline |

Users already decline for exactly the reasons a counterparty would: the two dominant filed
pass reasons — "I'd give too much" and "doesn't fit the window" — are the mirror image of the
objections the other manager would raise. The engine computes none of this from the other
seat: the fit arm's them-score is a dark number with no reason attached; `acceptance_prior`
is an unfed stub returning 0.5 uniformly (negmem research memo); G6's R5 asks whether the
*user* needs what they receive, never whether the counterparty does (PLAN §1).

So a card can clear every live gate while being an obvious "no" from the other seat, the user
never proposes it (propose = 0 ever is the whole G1 funnel gate), and the app reads as a
calculator, not a scout. The breaker attacks the trust gap directly: **name the strongest
reason the other manager kills it, before the user embarrasses themselves.**

Why the vocabulary matters (PLAN §2): objection codes anchor on the shipped
`trade_pass_reasons` layer-2 codes, so "predicted objection" vs "actual filed reason" is a SQL
join against ~200+ existing coded rows — calibration with zero new instrumentation, one
vocabulary shared with the sibling plans (two tenses: negmem = history, breaker = present).

## 3. Goals & Non-Goals

### Goals (v1)

| # | Goal | Measured by |
|---|---|---|
| P-G1 | Every served card carries a coded, evidenced prediction of the counterparty's decline reason | coverage ≥99% scored (HLD NFR-6) |
| P-G2 | The prediction is calibrated before it is ever shown — per class, against preregistered baselines | LLD §8 readout spec |
| P-G3 | The card tells the user what to pre-empt, without being confidently wrong about a named human and without leaking anyone's private state | §5 requirements R-8..R-12; HLD D-6 |
| P-G4 | Move the launch gates the narration can plausibly move: G1 (≥3 real sends), G3 (`value_giving` ≤25% of pass reasons), G2 non-degradation | §4 metrics |
| P-G5 | Produce the data that decides v2 (filter/demote) — the §6.4 counterfactual from stamps alone | PLAN §6.4 |

### Non-Goals (v1) — HLD §1.4 by reference, restated at product level

No filtering, demoting, reordering, or deck-composition change on any deck under any v1 flag ·
no learning/persistence (negmem's tense) · no retrospective scoring (Receipts' tense) · no
counterparty notification and no output in the counterparty's own app, ever · no rendering of
any private counterparty state (`asset_preferences`, board contents, declared outlook — dark
stamps only) · no LLM · no new tables/routes/events · no web or extension surface (mobile
only) · no tappable/expandable hesitation element (a tap target adds an analytics-taxonomy
row — deferred, see R-13) · `build_narrative` and `_opponent_frame` untouched.

## 4. Success Metrics

**The measurement contract is LLD §8** — populations, joins, censoring boundaries, per-class
gate table, stratification. Every metric below names its readout there. All readouts filter
`is_ghost = 0`, censor at `model_config_changes` timestamps (M1 rail), exclude the D-091
window, respect both QB-repricing seams, and censor at the `fix/package-benchmark-sweetener`
deploy timestamp — a code-ship boundary the M1 rail cannot see, named explicitly in §8.

### Primary

- **M-P1 — Calibration precision (gates narration; the headline).** Per class: precision of
  the predicted top objection against the viewer's own filed layer-2 pass reason, on the
  viewer-seat shadow population (`features_json.breaker_shadow.top` ⨝ `trade_pass_reasons`),
  must beat BOTH the majority-class baseline (40% `value_giving`, n=208 — re-derived at
  readout) and a stratified-random baseline, at operator-pinned minimum n, stratified by
  `outlook_src` × board basis. *"Always predict value_giving" scores 40% aggregate match — so
  aggregate match-rate is banned as a success claim; per-class rows only* (HLD D-6, R-3).
  Counterparty-seat matches (mirrored card served both ways) are a long-horizon accumulator,
  reported but never a gate (n≈0 today; A-5).
- **M-P2 — Narration effect (after `trade.breaker_narrative` lights).** On mobile-served
  cards, keyed on the (`ver`, `tmpl_ver`) pair: (a) pass-reason mix shift on narrated vs
  non-narrated cards — the honest v1 readout; (b) contribution to **G1: ≥3 real proposes by
  ≥2 testers** — the north-star product claim, stated honestly: propose has fired zero times
  ever, so any non-zero movement is signal and no per-feature attribution will be clean;
  (c) directional support for **G3** (`value_giving` share of pass reasons falling toward
  ≤25%): a user told *why the other side hesitates* files different reasons than one guessing.

### Guardrails

- **M-G1 — Coverage & degradation** (graduation criteria, HLD NFR-6): scored coverage ≥99% of
  served impressions AND rung-1..3 share < `breaker_degraded_share_max` (0.05).
- **M-G2 — Performance** (ties to launch gate G4): p95 job time no regression with
  `trade.breaker` on; breaker `ms` p95 within `breaker_ms_budget` (250 ms default, 60-card
  basis, LLD E-B); pre-flag-on dry-run number delivered to the operator first.
- **M-G3 — Zero ordering effect**: not a metric — a test-enforced invariant
  (`test_breaker_zero_ordering_effect`, both draft paths + organic).
- **M-G4 — Anti-wallpaper** (HLD D-7): weekly class-entropy over `top.code` stays above the
  red line before any narration graduation; narrated share of deck and per-(partner, code)
  repetition tracked via the three-cell readout (narrated / suppressed-with-reason /
  no-objection).
- **M-G5 — Deck-level engagement non-degradation**: overall like-on-viewed and G2 top-of-deck
  like rate (positions 0–4, baseline ~17%, target ≥30%) do not degrade on narrated decks.
  Deliberately deck-level: a correct hesitation *should* depress likes on genuinely flawed
  cards — a per-card like-rate guardrail would punish the feature for working.
- **M-G6 — Cross-seat divergence** (R-6 monitor): mirrored-serve narration-divergence count
  rides per-job diagnostics; re-read at the A-5 cadence.

## 5. Requirements

Numbered, testable; test names in LLD §7 are the verification spec. "MUST" rows are v1
acceptance criteria.

### 5.1 Evaluation & stamp (invisible to users; the measurement substrate)

- **R-1** With `trade.breaker` on, every card that reaches impression logging — organic and
  bake-off decks, both draft paths, likes-you-injected cards included — MUST carry a breaker
  stamp in `features_json`: a scored 6-class objection vector or a labeled degradation marker,
  never a bare null; the key is absent only when the flag is off. (LLD §1.4, §2.1;
  `test_impressions_breaker_uniform_keys`, `test_midjob_flag_flip_no_crash`.)
- **R-2** Deck order and composition MUST be byte-identical with `trade.breaker` on vs off,
  on organic and interleaved decks alike; nothing in generation may read breaker stamps.
  (HLD NFR-1, D-11; `test_breaker_zero_ordering_effect`, `test_breaker_inert_seam_creep_guard`.)
- **R-3** Objection codes MUST be the closed set: the 9 coded `PASS_REASON_LAYER2` codes +
  `roster_crunch` (`producer=breaker`); `shape_aversion` never appears in any field; evidence
  keys are exactly the LLD §2.4 enums — ids, numbers, enum strings, no free text, no names.
  (`test_breaker_vocabulary_closure`.)
- **R-4** Same inputs ⇒ same objections, severities, sentence — no RNG, no LLM, no wall-clock
  in any verdict. (HLD NFR-4; `test_breaker_deterministic`.)
- **R-5** The viewer-seat shadow (`breaker_shadow_run`, default on — register item 5) MUST
  stamp with the same marker discipline and MUST never serialize to any client.
  (LLD §2.5; `test_breaker_shadow_never_serialized`.)
- **R-6** All degradation MUST be labeled and self-surfacing (rung ladder, LLD §5.1); a silent
  breaker outage presents as a failed coverage criterion, not a discovered mystery.

### 5.2 Narration & privacy (the user-visible half)

- **R-7 — Dark window is truly dark.** With `trade.breaker` on and `trade.breaker_narrative`
  off, the client payload carries **no `breaker` key at all** — no code, no severity, nothing
  inspectable. (LLD §1.5; `test_breaker_payload_absent_during_dark_window`.)
- **R-8 — Server-composed copy only.** The sentence is composed server-side by
  `compose_narration` → `trade_narrative.hesitation_line`; the client renders it verbatim and
  never switches on `code`, never carries a string-literal sentence. (LLD §1.6, §1.8.)
- **R-9 — Eligibility chain** per LLD §3.8, in order: per-class graduation switch → privacy
  whitelist → format envelope → floors (`max(class floor, breaker_min_severity)`) → outlook
  narration margin (legacy source) → per-(partner, code) repetition suppression. Every
  suppression stamps its enumerated reason so the A/B readout distinguishes "no objection"
  from "objection muted."
- **R-10 — Privacy whitelist (MUST, non-negotiable in v1).** `other_player_keep` never
  narrates under any switch state; board-basis `value_giving` is narration-ineligible
  outright; a declared outlook never supplies the narrated claim — it may only raise
  confidence when the public-inferred window agrees, and disagreement mutes the class.
  Nothing derived from another user's private in-app state ever renders. (HLD D-6, D-7, D-8;
  register items 8/14; `test_narration_whitelist_dark_classes`.)
- **R-11 — Cold start renders nothing, by design.** All six `breaker_narrate_<class>`
  switches ship at 0; flipping `trade.breaker_narrative` with zero classes graduated renders
  nothing anywhere. Graduation is an operator `set_knob` flip per class, logged.
  (`test_narration_switch_ladder`.)
- **R-12 — Template refusal is honest silence.** A missing or null evidence value in a
  rendered key ⇒ no sentence (never "None-year-old"); unknown code ⇒ no sentence; any internal
  error ⇒ no sentence, stamped `template_error`, never a crash. (LLD §1.6;
  `test_hesitation_line_honesty`.)

### 5.3 The hesitation element (mobile UX)

- **R-13 — Placement & anatomy.** One non-interactive row in
  `mobile/src/components/TradeCard.tsx`, mounted in the muted hint-tier band: after the
  FB-47 partner-fit line row, before the consensus-note block (LLD §1.8 — the band where the
  card already speaks quietly about the other seat). Anatomy mirrors the fit row: small
  informational dot on `flare.base` (informational accent per ADR-005 — ice stays reserved
  for actions) + one `type.bodySm` sentence. **No tap target, no expansion, no icon-as-emoji,
  no new colors** — tokens by reference to
  [docs/design/design-system.md](../../../design/design-system.md) and
  [components.md](../../../design/components.md); the structural guard greps for hex literals
  and radius >8. A tappable "why they'd hesitate" variant is explicitly deferred (it adds an
  analytics-taxonomy row per scope.md §1 and an interaction pattern the card doesn't have).
- **R-14 — Gate = payload presence.** The element renders iff `data.breaker?.sentence` is
  present; the server serializes `breaker` only for narrated cards, so payload presence IS the
  flag gate — no second client-side flag check to disagree. (LLD §1.8.)
- **R-15 — testIDs** follow the repo dot idiom: `trade-card.breaker-hesitation` and
  `trade-card.breaker-hesitation.body` (LLD Q-8 ruling; scope.md's hyphen example is
  superseded); `mobile/scripts/testid-lint.sh` passes; structural guard
  `mobile/tests/check-breaker-card.js` pins all seven LLD §7.5 assertions.
- **R-16 — Blast radius zero elsewhere.** Web and extension ignore the key; old mobile builds
  ignore unknown keys, no minimum-version gate; no FeedbackFAB change (no new screen, PLAN §7);
  demo-league and superseded decks are skipped (LLD T-1 — a hesitation about a synthetic demo
  partner is a product absurdity; but see register item 15).

### 5.4 Copy: templates, examples, tone (the voice of the feature)

Exact v1 wording is the LLD §1.6 template table; any PRD-driven polish bumps
`HESITATION_TMPL_VERSION`. Worked examples in house voice (names shown are resolved from
evidence ids at render time — the template never contains a name):

| Class (basis/branch) | Example sentence as rendered |
|---|---|
| `fit_outlook` (rebuilder) | *Their likely hesitation: their roster leans rebuild, and this sends them Aaron Jones, a 31-year-old RB.* |
| `fit_outlook` (win-now) | *Their likely hesitation: they look win-now, and this asks them to take back future capital.* |
| `fit_new_weakness` | *Their likely hesitation: giving up Trey McBride may leave them thin at TE.* |
| `fit_duplicate` | *Their likely hesitation: they're already deep at WR, so Jordan Addison may not move their lineup.* |
| `value_giving` (consensus only) | *Their likely hesitation: by consensus value they'd likely see this as giving up more than they get.* |
| `roster_crunch` | *Their likely hesitation: taking back 2 more players than they send is a roster squeeze.* |
| `other_player_keep` | — never renders (R-10). |

Tone rules (binding; enforced by `test_hesitation_line_honesty` + the template snapshot):

1. **Fixed lead-in** "Their likely hesitation:" — a label, not prose, so the user learns the
   element's meaning once and scans it thereafter (consensus-note precedent: label + body).
2. **Hedged modality is part of the contract** — "likely," "may," "look," "leans." Never a
   flat assertion about what a person will do.
3. **Roster facts and observable state only, never mind-reading.** "Their roster leans
   rebuild" — never "they don't rate your RB," "they won't want," "they're not interested."
   The sentence describes the roster; the manager's mind is theirs.
4. **D-053 honesty, mechanically:** every name, age, position, and number resolves from the
   objection's own evidence ids; the sentence can never claim what the analysis didn't produce.
5. **No surveillance framing.** "FTF data shows Mike…" is banned even where true — it
   advertises inside knowledge to the one audience guaranteed to include Mike (HLD §5.2).
6. **One sentence, always.** The element never stacks objections; `top` only. The full vector
   stays server-side.

### 5.5 States & edge cases the user can observe

| State | What the user sees | Why |
|---|---|---|
| `trade.breaker` off (today) | Nothing; payloads byte-identical | NFR-3 |
| Dark-stamp window (`breaker` on, narrative off) | **Nothing, on every card** — no payload key exists to inspect | R-7; measurement-only phase |
| Narrative on, zero classes graduated | Nothing — by design; cold start renders silence, not noise | R-11 |
| Narrated card | One muted hesitation row, one sentence | R-13 |
| Objection exists but suppressed (below floor / class not graduated / repetition / format gap / template error) | Nothing on that card — deliberately indistinguishable from "no objection" to the user; the *stamp* records the reason | An "objection withheld" hint would be a dark-pattern tease; the data still sees it (R-9) |
| Repetition case: 5 cards, same partner, same objection | The single highest-severity card carries the line; the rest are silent | Anti-wallpaper (D-7); register item 10 |
| 14-team / IDP / non-Sleeper league | Fewer named hesitations, never wrong ones — depth-based classes are envelope-gapped | HLD §3.5 |
| Unboarded counterparty (84.5% case) | Only consensus-basis or roster-structure hesitations, behind a deliberately high floor | D-7 near-tautology guard |
| Counterparty's own app | **Never any output caused by the breaker** — no notification, no surface, nothing | HLD §1.4, §5.6 |
| Demo deck (`league_demo`) | No hesitation lines | R-16; register item 15 |
| Web / extension / old mobile builds | Unchanged | R-16 |
| Two league-mates compare screens on a mirrored trade | Both sides hedged and roster-fact-grounded — two perspectives, never a contradiction of fact | HLD R-6 + §2.7 coherence test |

### 5.6 User stories

- **U-1 (viewer/value):** As a manager browsing suggested trades, I see the strongest reason
  my partner would hesitate, so I can pick trades that will actually land — and open my pitch
  by pre-empting the objection.
- **U-2 (viewer/trust):** As a manager burned by one-sided suggestions, I see the app argue
  the other side against its own card — which is exactly what makes me trust it enough to hit
  propose. (G1 is the metric form of this story.)
- **U-3 (counterparty/protection):** As a league-mate who marked players untouchable and keeps
  a personal board, nothing I entered privately ever appears on another manager's screen — not
  named, not paraphrased, not implied. (R-10 is this story's contract.)
- **U-4 (operator):** As the operator, I graduate narration class-by-class from a preregistered
  calibration readout, and I can silence the line, a class, or the whole feature without a
  deploy. (R-11, rollback ladder.)
- **U-5 (unsupported-league user):** As a manager in a 14-team IDP league, I get fewer named
  hesitations rather than confidently wrong ones. (HLD §3.5.)

## 6. Scope & Phasing

### 6.1 The two product outcomes, weighed (the assignment's explicit question)

The origin brief names two outcomes: **(1) filter/demote** — the checker kills or buries cards
the counterparty would refuse — and **(2) narrate** — the card names the hesitation and the
user decides. This PRD commits v1 to outcome 2 and defers outcome 1 to v2, for three reasons
that are product reasons, not just mechanics:

1. **The binding constraint is real but secondary.** Interleaved bake-off serving is live;
   nothing may reorder or filter the interleaver's output without the bake-off measuring deck
   position instead of model quality (PLAN §3). That alone forces stamp-first — but it is not
   the main argument.
2. **Outcome 1 on day one would kill cards on an unvalidated predictor.** The breaker's
   marquee input is a window signal known to skew ~65% rebuilder (HLD R-2). Filtering on that
   silently shrinks decks with correlated, invisible wrongness — the user sees fewer cards and
   never knows why. Outcome 2's failure mode is one hedged sentence that's occasionally wrong
   and visibly attributable. D-067 (*accuracy, not volume*) cuts the same way: the filter must
   earn its existence from the §6.4 counterfactual, which the stamp itself produces.
3. **The user's actual blocker is trust, not deck size.** Propose has fired zero times ever
   while users file "I'd give too much" 40% of the time — they don't need fewer cards, they
   need a reason to believe a card survives contact with the other manager. A named, honest
   hesitation is that reason; a silent filter is not user-visible progress at all.

### 6.2 v1 (this plan, committed)

- **Phase 0 — Build & merge, flags off.** Lands AFTER the Monday `fix/package-benchmark-
  sweetener` merge (§7.1); CI green; golden re-captured upstream; no behavior change.
- **Phase 1 — Dark stamp.** Preconditions: calibration-readout spec TBD cells filled and
  frozen (LLD §8; the graduation SQL committed as a reviewed `scripts/` artifact) + the
  60-card dry-run ms number delivered (fit W0 precedent). Then `trade.breaker` on. Nothing is
  user-visible; `features_json` grows two keys.
- **Phase 2 — Calibration & per-class graduation.** Readout per LLD §8; the operator
  graduates classes individually via `set_knob` (logged, auto-censoring). Recommendation
  (register item 16): graduate **`fit_new_weakness` first** — it mirrors a live viewer-seat
  predicate (HLD §2.7), renders only public lineup math, and its failure mode is a checkable
  roster fact; hold `fit_outlook` (the demand-heavy class, 33% of pass reasons) until its
  legacy-window haircut + margin bar prove out in the readout, per R-2's risk.
- **Phase 3 — Narration first light, operator-only.** `trade.breaker_narrative` on under the
  tester-allowlist/experiment precedent (`onboarding_v2_rollout`); the §8.3 TestFlight
  checklist runs against the graduated class; timing vs the live bake-off window per register
  item 9 (default: dark until the serving round's verdict).
- **Phase 4 — General lighting + A/B readout** (M-P2), keyed on (`ver`, `tmpl_ver`).

### 6.3 v2 (weighed, NOT committed — own scope block, own gates, decided by the §6.4 readout)

Bright line (PLAN §3): anything changing deck composition is a new feature with its own scope
block, evidence, and TestFlight pass; D-067's family-suppression ruling binds any demotion
below visibility. The three options, weighed from the product seat:

| Option | What it is | For | Against |
|---|---|---|---|
| (a) Per-arm pre-draft screening | Each generator arm's candidate list is breaker-screened INSIDE generation, before the interleaved draft | The deck actually improves; screening becomes part of each arm, so the bake-off measures it fairly; attacks the root (one-sided generation) | Touches every generator; needs an in-generation evaluation seam v1 doesn't build; removed cards are invisible (family-suppression ruling applies) |
| (b) Serving-layer demote, bypassed on interleaved decks | A re-ranker like every other, disabled during bake-offs | Smallest seam | The bake-off never measures the thing we'd be shipping — permanently unevaluated behavior; two products in one flag |
| (c) User-side filter/badge | Sort or filter the deck by objection severity; user-controlled | User agency; zero server-side composition change; interleave-safe; cheapest | Pushes work onto the user; requires serializing codes/severity beyond narrated cards, colliding with the round-4 privacy gate — usable only over graduated, whitelist-clean classes; doesn't fix generation |

**Recommendation (not a commitment): (a), gated on the §6.4 counterfactual** showing
high-severity-objection cards materially underperform (pass rate, pass-reason match) — the
only option that both improves what users see and stays honestly measured. (c) is the
complement worth considering alongside it, restricted to graduated classes, if users ask for
control before (a) earns its evidence. (b) is recommended against: shipping behavior the
measurement system is structurally blind to is how this codebase got a 40% value complaint in
the first place. Operator register item 6 holds the election.

**LLM stance:** v1 is deterministic templates end to end. An LLM-phrased hesitation line is
not proposed here and would be a separate explicit operator decision (register item 2) with
its own honesty-enforcement story; the D-053 mechanical guarantee (the sentence cannot claim
what the analysis didn't produce) is currently *provable only because* the templates are
deterministic.

## 7. Dependencies & Risks

### 7.1 Ship sequencing (hard dependency)

The operator-approved **Monday `fix/package-benchmark-sweetener` merge** (held for the window
boundary) precedes the breaker build (PLAN A-1 pending-ship block):

1. The package depth-discount re-benchmark changes `value_giving` severity semantics — the
   breaker's severity math is written against **post-fix** semantics (LLD §3.4), and the
   calibration cohort starts at/after that merge; pre/post severities are never pooled.
2. It is a **code deploy invisible to `model_config_changes`** — the M1 rail cannot censor
   it; the LLD §8 spec names its deploy timestamp as an explicit boundary.
3. Auto-sweetened cards are ordinary cards to the breaker (LLD E-23); the readout gains an
   optional cut on the sweetener's `features_json` key.
4. The arm-A golden is re-captured at that ship; nothing here cites the old golden SHA.

### 7.2 Sibling coordination (one operator batch, three plans)

- **Shared taxonomy v1.1.0 PR** (objection vocabulary: anchor codes + `roster_crunch`
  `producer=breaker` + the producer column, `shape_aversion` ceded to negmem) is a deliverable
  of THIS thread before operator delivery — until it lands, R-12 (sibling drift) stays open.
- **Bulk readers** (LLD §2.2): negmem may want equivalents; whichever plan builds first owns
  them (Q-11).
- **Receipts contract** (A-2): CLOSED — disjoint seams dual-signed; Receipts touches zero
  generation code.
- **Change control:** serving-affecting flips share the one-engine-change-per-tester-week
  calendar across all three siblings — one operator, three eager plans (HLD §5.1).

### 7.3 Risks

The authoritative register is **HLD §6.1 (R-1..R-13), by reference.** The product-lens top
four, in one line each: **R-1** private-preference leak — designed away in v1 by the D-6
whitelist (the one requirement this PRD marks non-negotiable, R-10); **R-2** systematically
wrong window objections from the skewed legacy vector — haircut + margin bar + graduation
gate, and the reason `fit_outlook` is not the recommended first class; **R-3** calibration
theater — preregistered per-class baselines, min-n, no aggregate match-rate claims; **R-4/R-6**
wallpaper and cross-seat story mismatch — anti-wallpaper controls + hedged two-perspective
copy + the divergence monitor. Assumptions A-3..A-6 (line drift, outlook skew re-derivation,
mirrored-serve rate, board staleness) re-verify at build per HLD §6.2.

## 8. Rollout & Measurement

### 8.1 Flag/knob launch sequence

**HLD §5.1 is verbatim-by-reference the launch sequence**, including the flag table,
graduation criteria, and rollback ladder (§5.3). In brief — (1) `trade.breaker` on →
dark-stamp window; (2) shadow-based per-class calibration readout against the preregistered
spec; (3) operator graduates ≥1 class via `set_knob`; (4) `trade.breaker_narrative` first
light under **operator-only exposure** (tester-allowlist/experiment precedent) + the §8.3
checklist; (5) general lighting. Preconditions to step 1: readout spec frozen + dry-run ms
number. If no class is graduated when the narrative flag lights, nothing renders — by design.

Rollback, deploy-free, outermost first: narrative flag off (hot) → `breaker_min_severity`
1.1 or per-class switch to 0 → `trade.breaker` off (module unimported, key gone, rows
byte-identical) → revert commit; nothing persisted needs migration.

### 8.2 First exposure

Operator-only via the device-unit allowlist/experiment mechanism (`onboarding_v2_rollout`
precedent; allowlist ships via `config/tester_allowlist.json` — Render ignores
`render.yaml` envVars). No tester sees a hesitation line before the operator has run §8.3 on
their own device. Narration-flip timing vs the live bake-off window: register item 9 —
default dark until the current serving round reaches its verdict.

### 8.3 Manual TestFlight checklist (per D-056: the ONLY runtime evidence this feature gets)

Run by the operator on the operator-allowlisted build, against a league where a class has
been graduated and at least one served card is known-narrated (the per-job diagnostics
narrated count identifies one). Log the pass in `living-memory/TEST_LEDGER.md`.

| # | Step | Expected result |
|---|---|---|
| 1 | Before the build: confirm flags — `trade.breaker` on, `trade.breaker_narrative` on, exactly one class switch ≥1 (e.g. `breaker_narrate_fit_new_weakness`) | `GET /api/feature-flags` + config show exactly this state; `model_config_changes` has the logged flips |
| 2 | Open the trade deck; find the known-narrated card | A single muted row sits between the partner-fit line and the consensus note: small dot + one sentence beginning "Their likely hesitation:" |
| 3 | Read the sentence against the card's assets | Every name/age/position it mentions is actually in the trade, on the correct side; wording matches the LLD §1.6 template for the graduated class; hedged ("may"/"likely"); one sentence only |
| 4 | Check every OTHER card in the deck | Cards without a narrated objection show no hesitation row at all — no empty row, no placeholder, no layout shift vs a pre-feature build |
| 5 | Cross-check a card whose top objection is a non-graduated or dark class (diagnostics identify one) | No hesitation row — and nothing else on the card hints at the withheld objection |
| 6 | Deck with several same-partner cards (repetition case) | At most the expected share carries the line for that (partner, objection); the rest are silent |
| 7 | Visual pass against the Chalkline reference (`web/style-guide.html` + design-system tokens) | Dot is flare (informational), not ice; typography matches the fit-line row; no new colors, no emoji, radius within spec; dark/light both correct |
| 8 | Pass on a narrated card and file a decline reason | The pass-reason sheet flows exactly as before — same codes, no new step, no reference to the hesitation |
| 9 | Open the same league on web | No hesitation surface anywhere (mobile-only v1) |
| 10 | Ask for a fresh deck in a league in a known format gap (14-team or IDP), if available | Cards render normally; no depth-based hesitation line appears |
| 11 | Rollback drill: flip `trade.breaker_narrative` off (hot reload), pull a fresh deck | No hesitation row on any card; deck otherwise unchanged; flip back on restores it on newly served decks |
| 12 | Regression sweep: like, pass, undo, propose-flow entry on narrated and non-narrated cards | All actions behave identically to the pre-feature build |

A failure on any step blocks general lighting (step 5 of the launch sequence) until fixed and
re-run.

### 8.4 Docs & evidence owed at ship

Scope.md §3/§4 and HLD §5.8 by reference: api-reference row (additive `breaker` payload
object) · config-reference (2 flags + 25 knobs, five-registration rule) · architecture +
living-memory HLD/LLD rows · glossary ("breaker", "objection", "hesitation line") ·
DECISIONS.md entry (vocabulary + stamp-only + v2 bright line) · cross-client-invariants row
filled "n/a in v1" · data-dictionary rows for the two `features_json` keys · TEST_LEDGER
entries at each merge and at the TestFlight pass.

## 9. Consolidated operator decision register

**How to read this table:** the operator has already authorized building once this PRD
converges — **open items do not block the build; their listed defaults ship.** This register
is the post-build tuning worklist: each row is a call the operator can revisit with data in
hand, and the "where flagged" column says where the full argument lives. Sources merged:
PLAN §9 (items 1–7b, superseded states preserved), HLD §6.3 (items 8–14), and the LLD's open
product questions (items 15–16 map Q-10 and the shadow default; item 17 is this PRD's one
addition).

| # | Question | Default shipped | Status | Where flagged |
|---|---|---|---|---|
| 1 | v1 = stamp + narrative only; filter/demote deferred to v2 with its own gates | stamp + narrative only | open (default ships) | PLAN §3/§9; this PRD §6.1 |
| 2 | Narrative stays deterministic templates; LLM = separate explicit decision | deterministic, no LLM | **ruled** (operator constraint, PLAN §0) | PLAN §0/§7; PRD §6.3 |
| 3 | Hesitation-line surface. ~~Original default: append inside the existing narrative string~~ — **superseded 2026-08-21**: verified NO client renders `TradeCard.narrative` (the append option ships an invisible feature) | distinct card element, mobile-only, muted hint band | **ruled by convergence** (M-3; operator may still override with the "make `narrative` render first" precondition ticket) | PLAN §9 #3; HLD §2.4; LLD §1.8 |
| 4 | `breaker_min_severity` initial bar (with the per-class switches, the only user-visible-effect knobs in v1) | 0.60 ships; tuned from the calibration readout, never guessed | open — post-readout tuning | PLAN §9 #4; LLD §4 |
| 5 | Viewer-seat shadow run — acceptable compute for the primary calibration population? | on (`breaker_shadow_run` = 1.0, inside the same ms budget; ≤2× per-card cost) | open (default ships) | PLAN §9 #5; LLD §2.5/§9 Q-9 |
| 6 | v2 seam election: (a) per-arm pre-draft · (b) bypassed-on-interleave demote · (c) user-side filter | none — decided after the §6.4 counterfactual readout; PRD recommends (a), advises against (b) | open | PLAN §9 #6; this PRD §6.3 |
| 7a | `roster_crunch` extension code accepted into the shared taxonomy (`producer=breaker`) | sibling-agreed 2026-08-21; ships in the taxonomy v1.1.0 PR | open — pending operator yes | PLAN §9 #7a; HLD D-1 |
| 7b | `shape_aversion` enters the taxonomy as `producer=negmem` (breaker may cite it only via the future memory→breaker coupling); producer column added | sibling-agreed 2026-08-21 | open — pending operator yes | PLAN §9 #7b; HLD D-2 |
| 8 | Evidence whitelist: private counterparty state stamps dark, never renders — accepted? And may even a generic form ("unlikely to move him") ever render? | dark-only; generic form does NOT render | open (default ships; PRD marks it non-negotiable in v1 — R-10) | HLD §6.3 #8, D-6, §5.6 |
| 9 | Narration-flip timing vs the live interleaved bake-off window | `trade.breaker_narrative` stays DARK until the current serving round's verdict; mid-window lighting requires accepting an annotated readout | open | HLD §6.3 #9 (M-6) |
| 10 | Per-deck repetition suppression: same card, different decks, different narration — acceptable? | yes, with `suppressed` stamped | open (default ships) | HLD §6.3 #10, D-7 |
| 11 | Inferred-window `fit_outlook` narration: wait for the composite's engine-wide graduation, or ship behind the high-margin bar? | high-margin bar (`breaker_outlook_narrate_margin`); declared outlook is confidence-only on agreement | open | HLD §6.3 #11, D-8 |
| 12 | `breaker_stamp_scope`: full-candidate-pool stamping (v2 study option) | served-deck-only; not built | open | HLD §6.3 #12, D-9 |
| 13 | Organic them-score coverage by promoting the fit stamp to organic decks — a fit-challenger scope question, registered here for visibility | `breaker.them` null on organic decks | open (belongs to fit-challenger) | HLD §6.3 #13, D-3 |
| 14 | Declared-outlook disclosure: is narrating from a privately declared `team_outlook` ever acceptable? | never in v1 — confidence-only on public-inferred agreement; disagreement mutes the class; stamp records both | open (default ships) | HLD §6.3 #14, D-8 |
| 15 | Demo-deck narration as demo material: v1 skips `league_demo` decks entirely; narrating on demo decks is a deliberate product lift (new-user first impression) requiring demo-safe copy review | demo decks skipped, no narration | open — named product lift, not a default | LLD §9 Q-10 (T-1 ruling); PRD R-16 |
| 16 | Shadow-run default at flag-on (the LLD ships it enabled — confirm the compute posture before the dark window opens, since the shadow is the PRIMARY calibration population and turning it off starves M-P1) | `breaker_shadow_run` = 1.0 at `trade.breaker` first light | open — confirm at Phase-1 flag-on | LLD §4/§2.5; PLAN §9 #5 (same lever as item 5, listed for the flag-on checklist) |
| 17 | **PRD addition — first class to graduate.** Which class gets the first `breaker_narrate_<class>` flip? PRD recommends `fit_new_weakness` (live mirrored predicate, public lineup math, checkable failure mode) over the demand-heavier but risk-heavier `fit_outlook` | none graduated at first light (all switches 0) | open — decided at Phase 2 from the per-class readout rows | this PRD §6.2; HLD §2.7/D-6 |

---

*End of PRD draft A (Product/User lens). For cross-review: the contestable product calls are
§6.1's outcome weighing, §6.3's (a)-over-(c) recommendation, §6.2's first-class-to-graduate
recommendation (item 17), §5.5's decision to make suppression user-invisible, and §5.4's
fixed lead-in label. Mechanics are cited from the converged LLD; any divergence found in
review is a defect here, not there.*
