# PRD — Counterparty breaker

**Date:** 2026-08-21 · **Status:** MERGED CANDIDATE (synthesis of drafts A + B under the
orchestrator's merge rulings M-1..M-10; awaiting cross-review).
**Binds under:** [PLAN.md](PLAN.md) (AMENDED — authoritative) → [HLD.md](HLD.md) (converged) →
[LLD.md](LLD.md) (converged) → this PRD (binds tightest on product surface, copy, rollout, and
the decision register; it may not contradict the LLD's mechanics — where it wants to, it says
so and flags for cross-review). Scope block: [scope.md](scope.md). Drafts preserved at
[drafts/PRD-draft-A.md](drafts/PRD-draft-A.md) / [drafts/PRD-draft-B.md](drafts/PRD-draft-B.md).
**Rule of restraint:** this PRD cites the HLD/LLD by section rather than restating mechanics.
Anything mechanical stated here that disagrees with the LLD is a defect in this document.
**Standing fact:** the operator has already authorized building after PRD convergence. The §9
register is **post-build tuning**, not a build blocker — defaults ship; the operator re-levels
knobs, copy, and readout cells afterward.

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
sentence, mobile-only in v1). Both default false. 25 knobs (LLD §4). No new tables, routes, or
migrations. Deterministic end to end; **no LLM anywhere in v1** — any LLM involvement is a
separate, explicit operator decision (register item 2). One mobile element, one structural
guard, one TestFlight checklist (§8.3 — merged and written in full here).

## 2. Problem & Context

**The user brief** (trade-engine-accuracy PLAN, 2026-08-20): *"Trade suggestions aren't
getting much better with every iteration… I need a clear plan for how we actually get this
model in a better spot before I can launch."*

**What the evidence says the problem is** — the suggestions are one-sided, users can tell,
and nobody sends them:

| Evidence | Number | Source |
|---|---|---|
| 1-for-1 cards existing in only one direction | **96.3%** | arm-B audit, [docs/reviews/2026-08-19-armb-audit-consolidated.md](../../reviews/2026-08-19-armb-audit-consolidated.md) |
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

And why the feature is dangerous (HLD governing stance): its dominant failure mode is not a
crash — it is being **confidently wrong about a named, real human, in copy their league-mate
can screenshot**. Every requirement in §5 that looks like paranoia traces to that sentence.

## 3. Goals & Non-Goals

### Goals (v1)

| # | Goal | Measured by |
|---|---|---|
| P-G1 | Every served card carries a coded, evidenced prediction of the counterparty's decline reason | coverage ≥99% scored, degraded share < 5% (HLD NFR-6); §4 M1 |
| P-G2 | The prediction is calibrated before it is ever shown — per class, against preregistered baselines | §4 M2 vs the LLD §8 readout spec |
| P-G3 | The card tells the user what to pre-empt, without being confidently wrong about a named human and without leaking anyone's private state | §5 requirements R-8..R-12 + FR-4.x; HLD D-6 |
| P-G4 | Move the launch gates the narration can plausibly move: G1 (≥3 real sends), G3 (`value_giving` ≤25% of pass reasons), G2 non-degradation | §4 M4/M5 (directional/counted — stated honestly) |
| P-G5 | Produce the data that decides v2 (filter/demote) — the §6.4 counterfactual from stamps alone | §4 M6; PLAN §6.4 |
| P-G6 | Wrongness is bounded, attributable, and cheap to retract | provenance markers; 4-rung rollback ladder, rehearsed in §8.3 |

### Non-Goals (v1) — the scope-creep tripwire list

Each item below has been *proposed or gestured at* somewhere in this initiative's history and
is **out**. A build diff touching one of these is a scope defect, not an improvement
(HLD §1.4 by reference; merged tripwire list from both drafts):

1. **Filtering, demoting, reordering, or draft changes** on any deck under any flag this plan
   ships (v2, own scope block — PLAN §3 bright line; D-11 seam-creep guard test).
2. **LLM anywhere** — copy, class selection, severity (operator constraint; deterministic
   templates only; a future LLM variant is a separate explicit operator decision, register 2).
3. **Web or extension rendering** of the payload key (mobile-only surface; HLD §2.4).
4. **Negmem coupling** — reading `negmem_*` tables, emitting `shape_aversion`, feeding
   `acceptance_prior` (D-2; producer-column closure test).
5. **Retrospective scoring** (Receipts' tense) — the breaker never re-grades past suggestions.
6. **Organic them-score** — promoting the fit stamp to organic decks is a fit-challenger
   scope question (register item 13); `breaker.them` stays null on organic decks.
7. **Taxonomy mirror module** — no breaker-local copy of the shared taxonomy; codes
   cross-check against `database.PASS_REASON_LAYER2` by import; vocabulary changes only via
   PR to `docs/plans/shared/trade-shape-taxonomy.md`.
8. **New tables/columns/routes/env vars/analytics events**; `breaker_` prefix reserved-unused
   (`test_no_breaker_tables`).
9. **Client switching on objection codes** — server-composed sentence only;
   cross-client-invariants row "n/a in v1".
10. **Any counterparty-side output** — no notification, no cross-user surfacing, ever in v1.
11. **Rendering any private counterparty state** (`asset_preferences`, board contents,
    declared outlook) — dark stamps only (R-10; HLD D-6).
12. **Demo-deck narration** (T-1 skip ships; register item 15).
13. **A tappable/expandable hesitation element** — deferred; it adds an analytics-taxonomy
    row (scope.md §1) and an interaction pattern the card doesn't have (R-13).
14. **Touching `build_narrative` or `_opponent_frame`** (HLD D-5/§2.4).
15. **Co-owner union resolution** (LLD §2.3: owner-id only + `identity_src` marker; union is
    a named v1.1 candidate needing a data-path change, Q-3).
16. **Board staleness handling** (Q-2/A-6 open; `board_auth` does not encode staleness).
17. **Bench-size / forced-drop modeling** for `roster_crunch` (Q-4: omitted, not
    approximated).
18. **Full-candidate-pool stamping** (D-9; register item 12, a v2 study option).
19. **Value-weighted `fit_outlook` lean** (LLD M-8 confirmed unweighted; a weighted variant
    is a v2 conversation gated on a replacement coherence proof).

## 4. Success Metrics — with the honest n

**The measurement contract is LLD §8** — populations, joins, censoring boundaries, per-class
gate table, stratification. All readouts filter `is_ghost = 0`, censor at
`model_config_changes` timestamps (M1 rail), exclude the D-091 window, respect both 1QB
QB-repricing seams (04:46Z and 11:48Z), and censor at the `fix/package-benchmark-sweetener`
deploy timestamp — a code-ship boundary the M1 rail cannot see, named explicitly in §8.

**Context every number below lives in:** single-digit active testers (recent peak ~200
decided cards across 4 days from 5 users; the trade-engine-accuracy tester protocol targets
~400 decided/week at 10 testers), 208 coded pass reasons **all-time**, `propose` = 0
all-time, and the mirrored-card serve rate ~3.7% (A-5, unverified). Metrics that cannot reach
minimum n in a realistic v1 window are **demoted to "counted, never gated"** here, in
writing, so the readout can't quietly redefine success. **Restoring any demoted metric to a
gate, graduation argument, or v2 argument requires a logged operator decision in the §9
register — never a readout footnote** (ruling M-1).

### 4.1 Metric table (verdicts binding)

| ID | Metric | Gate? | Expected n per readout cell (realistic window) | Verdict |
|---|---|---|---|---|
| M1 | **Coverage & cost**: scored-stamp coverage of served impressions; degraded share by rung; `ms` p50/p95 vs `breaker_ms_budget` (250 ms default, 60-card basis, LLD E-B); p95 job time unregressed; pre-flag-on dry-run ms number delivered to the operator first | YES — graduation gate for `trade.breaker` (HLD §5.1) | every served impression (~1,300 accrued in days at current volume) — n is not a constraint | **KEEP.** Attributable within one week of dark-stamp |
| M2 | **Calibration (primary; the headline)**: per-class precision of `breaker_shadow.top` vs the viewer's filed layer-2 code, vs TWO baselines — majority-class (predict `value_giving` always ⇒ ~40% aggregate match, n=208; re-derive at readout) and stratified-random (draw from the filed-reason distribution) — with per-class min-n gates, stratified `outlook_src` × board basis. *"Always predict value_giving" scores 40% aggregate match — so aggregate match-rate is banned as a success claim; per-class rows only* (HLD D-6, R-3) | YES — per-class narration graduation (D-6) | Coded reasons ≈ 75–150/week under the tester protocol (passes ≈ 60–80% of decisions; ~90% file a coded reason; minus ~10% `other_text`, excluded by construction). Per class/week: `value_giving` ~30–60 · `fit_outlook` ~25–50 · `fit_new_weakness` ~5–10 · `value_getting` ~4 · everything else ≤3 | **KEEP with per-class realism:** at the proposed min-n = 50/class (§9 item 16), `fit_outlook` and `value_giving` reach gate n in **1–2 weeks**; `fit_new_weakness` in **5–8 weeks**; `fit_duplicate` likely not inside v1; `roster_crunch` has **no filed-reason anchor at all** (extension code — no manager has ever been offered it as a pass reason) and `other_player_keep` is a permanently-dark class: both rows are **calibration-reported, never graduation-gated in v1** (LLD §8 already says roster_crunch "may remain unpassable — stated, not hidden"; this PRD makes that the plan, not a caveat) |
| M3 | **Counterparty-seat calibration** (PLAN §6.2a): mirrored card served to the counterparty + their filed reason vs the breaker's prediction | NO — never in v1 | 3.7% mirrored-serve rate × both-seats-decided × reason-filed ⇒ **n≈0–2/month** | **DEMOTED: counted, never gated.** Long-horizon accumulator only; never cited in any graduation or v2 argument until its cell prints n ≥ 30 (which v1 will not see). Anyone quoting this cut before then is doing calibration theater (R-3). Resurrection to any gate = logged operator decision (register intro) |
| M4 | **Narration lift**: pass-reason mix shift and like-on-viewed delta on narrated vs non-narrated mobile cards, keyed on the (`ver`, `tmpl_ver`) pair | DIRECTIONAL only | 10pp lift at ~20% base needs ≈300 decided/arm; narration applies to a *subset* of cards (one class graduated, floors, suppression) — realistic narrated-card decisions ≈ 30–80/week across all testers | **DEMOTED: directional, never a gate.** Reported with cell n; no significance claim below n=130/side (the 15pp bar from the accuracy PLAN's power note). Censors at every §4-intro boundary. Directional support for **G3** (`value_giving` share falling toward ≤25%): a user told *why the other side hesitates* files different reasons than one guessing |
| M5 | **Like→propose conversion / G1 contribution** | NO — never in v1 | `propose` = 0 all-time; the funnel bottom does not exist yet (G1 gate: ≥3 real sends, owned by trade-engine-accuracy) | **DEMOTED: counted, never gated.** Proposes are *counted* on narrated cards (free join) and reported as raw counts; the breaker never claims credit or blame for a funnel that has never fired. Stated honestly: any non-zero movement is signal and no per-feature attribution will be clean. If G1 passes during the v1 window, a propose-mix cut may be added to the readout — as counts, still not a gate. Resurrection to any gate = logged operator decision |
| M6 | **Filter counterfactual** (§6.4): outcome delta, would-kill cohort (top severity ≥ candidate bar) vs rest, per arm, from stamps alone | YES — the v2 earn-in | Decided **stamped** cards ≈ 150–400/week (all decided cards on flag-on decks). Cohorts fill pooled-across-arms in **2–3 weeks**; per-arm cells at interleaved thirds need ~6–9 weeks for the same resolution | **KEEP.** The v2 decision reads the pooled cut first, per-arm as confirmation; both reported with cell n; §4-intro censoring per LLD §8 |
| M7 | **Anti-wallpaper monitors**: class-entropy of `top.code` weekly; narrated/suppressed/no-objection three-cell split; mirrored-serve narration-divergence count (R-6) | Entropy = red line before narration graduation; others reported | diagnostics-derived, no n constraint | **KEEP** |

### 4.2 Guardrails (A's set stands; ruling M-1)

- **M-G1 — Coverage & degradation** (graduation criteria, HLD NFR-6): scored coverage ≥99% of
  served impressions AND rung-1..3 share < `breaker_degraded_share_max` (0.05).
- **M-G2 — Performance** (ties to launch gate G4): p95 job time no regression with
  `trade.breaker` on; breaker `ms` p95 within `breaker_ms_budget`; dry-run number first.
- **M-G3 — Zero ordering effect**: not a metric — a test-enforced invariant
  (`test_breaker_zero_ordering_effect`, both draft paths + organic).
- **M-G4 — Anti-wallpaper** (HLD D-7): weekly class-entropy over `top.code` stays above the
  red line before any narration graduation; narrated share of deck and per-(partner, code)
  repetition tracked via the three-cell readout.
- **M-G5 — Deck-level engagement non-degradation**: overall like-on-viewed and G2 top-of-deck
  like rate (positions 0–4, baseline ~17%, target ≥30%) do not degrade on narrated decks.
  **Deliberately deck-level, never per-card**: a correct hesitation *should* depress likes on
  genuinely flawed cards — a per-card like-rate guardrail would punish the feature for
  working. Expected-n honesty applies here too (M4's row): narrated-cell n is small; the
  guardrail is read at deck level with its cell n printed, and no degradation *claim* is made
  below the same n=130/side bar that binds M4's lift claims. **Enforcement definition
  (binding):** below cell n=130/side M-G5 is REPORT-ONLY — printed with cell n; it can neither
  confirm nor clear degradation; it never blocks — blocking would deadlock, since n only
  accrues by widening. One non-statistical tripwire applies from n≥30/side: narrated-deck
  like-on-viewed < ½ the concurrent non-narrated rate triggers an operator review + a logged
  HOLD on allowlist widening (not an auto-rollback, not a "degradation" finding), resolved at
  the n=130 read. M-G5 becomes a blocking gate on FURTHER WIDENING only after either side
  reaches 130. Below that, the blocking protections remain M-G4's entropy red line and M1
  coverage/perf. Tripwire numbers registered as §9 item 20.
- **M-G6 — Cross-seat divergence** (R-6 monitor): mirrored-serve narration-divergence count
  rides per-job diagnostics; re-read at the A-5 cadence.

### 4.3 What this section commits the readout to

- Every reported precision/lift **carries its cell n**; cells below min-n print
  "insufficient", never pool silently (LLD §8, restated as a product requirement).
- The LLD §8 TBD cells get **proposed defaults in this PRD** (§9 item 16) so the operator
  confirms numbers rather than inventing them at readout time: min n = 50 per class (primary
  stratum `consensus` basis × `legacy` outlook_src), required margin ≥ +10 points over BOTH
  baselines, per class.
- The **calibration cohort starts at/after the `fix/package-benchmark-sweetener` Monday
  merge** (LLD §3.4/§8); nothing pools across it.
- Cross-version pooling refuses: calibration keys on `ver`; narration A/B on
  (`ver`, `tmpl_ver`).

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
- **R-2b — Flag-off is byte-identical, MUST.** With `trade.breaker` off, the system MUST be
  indistinguishable from today at every observable layer: the breaker module is never imported
  (`backend.trade_breaker` absent from `sys.modules` across a full job), `features_json` carries
  no breaker key and impression rows are byte-identical, the client payload carries no breaker
  key and `trade_card_to_dict` output is byte-identical, and the publish stream adds zero
  publishes with snapshots byte-identical to flag-off. Acceptance: LLD §7's
  `test_flag_off_features_json_byte_identical`, `test_flag_off_payload_byte_identical`,
  `test_flag_off_never_imports_breaker`, plus the publish-count assertion in
  `test_narrated_payload_reaches_snapshot_all_flag_combos` (dark/zero-narrated decks add zero
  publishes).
- **R-3** Objection codes MUST be the closed set: the 9 coded `PASS_REASON_LAYER2` codes +
  `roster_crunch` (`producer=breaker`); `shape_aversion` never appears in any field; evidence
  keys are exactly the LLD §2.4 enums — ids, numbers, enum strings, no free text, no names.
  (`test_breaker_vocabulary_closure`.)
- **R-4** Same inputs ⇒ same objections, severities, sentence — no RNG, no LLM, no wall-clock
  in any verdict; frozen per-job knob snapshot; pinned `'market'` stud-tax. (HLD NFR-4;
  `test_breaker_deterministic`, `test_knob_snapshot_frozen_within_job`,
  `test_stud_tax_pinned_market`.)
- **R-5** The viewer-seat shadow (`breaker_shadow_run`, default on — register item 5) MUST
  stamp with the same marker discipline and MUST never serialize to any client.
  (LLD §2.5; `test_breaker_shadow_never_serialized`.)
- **R-6** All degradation MUST be labeled and self-surfacing (rung ladder, LLD §5.1);
  rank-correlated missingness is stamped (rung 3) so readouts exclude it; per-class predicate
  crashes stamp `predicate_error` durably; a silent breaker outage presents as a failed
  coverage criterion, not a discovered mystery. (`test_budget_ladder_labeling`,
  `test_per_class_exception_contained`, `test_exception_rungs`.)

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
  Nothing derived from another user's private in-app state ever renders — as prose OR as
  structured payload data (R-7 closes the payload half). (HLD D-6, D-7, D-8; register items
  8/14; `test_narration_whitelist_dark_classes`.)
- **R-11 — Cold start renders nothing, by design.** All six `breaker_narrate_<class>`
  switches ship at 0; flipping `trade.breaker_narrative` with zero classes graduated renders
  nothing anywhere. Graduation is an operator `set_knob` flip per class, logged.
  (`test_narration_switch_ladder`.)
- **R-12 — Template refusal is honest silence.** A missing or null evidence value in a
  rendered key ⇒ no sentence (never "None-year-old"); unknown code ⇒ no sentence; any internal
  error ⇒ no sentence, stamped `template_error`, never a crash. (LLD §1.6;
  `test_hesitation_line_honesty`.)
- **R-12b — Narrated payload reaches the client on every flag combination**, `deck.signal_v2`
  off included — the seam owns a republish iff narrated_count > 0.
  (LLD §1.3; `test_narrated_payload_reaches_snapshot_all_flag_combos`.)

### 5.3 The hesitation element (mobile UX)

- **R-13 — Placement & anatomy.** One non-interactive row in
  `mobile/src/components/TradeCard.tsx`, mounted in the muted hint-tier band: after the
  FB-47 partner-fit line row (`:452–458`), before the consensus-note block (`:460–478`) —
  the band where the card already speaks quietly about the other seat (LLD §1.8). Anatomy
  mirrors the fit row: small informational dot on `flare.base` (informational accent per
  ADR-005 — ice stays reserved for actions) + one `type.bodySm` sentence. **No tap target,
  no expansion, no icon-as-emoji, no new colors** — tokens by reference to
  [docs/design/design-system.md](../../design/design-system.md) and
  [components.md](../../design/components.md); the structural guard greps for hex literals
  and radius >8. A tappable "why they'd hesitate" variant is explicitly deferred (non-goal
  13). Physical budget verified against `TradeCard.tsx` this checkout: the element adds one
  ≤2-line `bodySm` row (~20–36pt) in the scrollable card body; no pinned bottom bar on this
  surface, no `setPinnedBottomBarHeight` interaction, no FeedbackFAB change (no new screen,
  PLAN §7).
- **R-14 — Gate = payload presence.** The element renders iff `data.breaker?.sentence` is
  present; the server serializes `breaker` only for narrated cards, so payload presence IS the
  flag gate — no second client-side flag check to disagree (fit precedent). (LLD §1.8.)
- **R-15 — testIDs & types.** testIDs follow the repo dot idiom: `trade-card.breaker-hesitation`
  and `trade-card.breaker-hesitation.body` (LLD Q-8 ruling; scope.md's hyphen example is
  superseded); `mobile/scripts/testid-lint.sh` passes; the TS payload type gains optional
  `breaker?: {code; severity; sentence}` (`tsc --noEmit`); structural guard
  `mobile/tests/check-breaker-card.js` pins all seven LLD §7.5 assertions.
- **R-16 — Blast radius zero elsewhere.** Web and extension ignore the key; old mobile builds
  ignore unknown keys, no minimum-version gate. Demo-league and superseded decks are skipped
  (LLD T-1; register item 15). The element ships **dark in the next regular release train** —
  payload-gated, it renders nothing until the server serves a sentence — so narration
  graduation is decoupled from EAS/TestFlight build cadence; the build containing the element
  MUST be the installed build before §8.3 steps 5+ can run (checklist preconditions).

### 5.4 Copy: templates, examples, tone (the voice of the feature)

Exact v1 wording is the LLD §1.6 template table — this PRD proposes **no wording changes**
(the templates already pass every rule below); any PRD-driven polish bumps
`HESITATION_TMPL_VERSION` and re-keys the A/B readout. Worked examples in house voice (names
shown are resolved from evidence ids at render time — the template never contains a name):

| Class (basis/branch) | Example sentence as rendered |
|---|---|
| `fit_outlook` (rebuilder) | *Their likely hesitation: their roster leans rebuild, and this sends them Aaron Jones, a 31-year-old RB.* |
| `fit_outlook` (win-now) | *Their likely hesitation: they look win-now, and this asks them to take back future capital.* |
| `fit_new_weakness` | *Their likely hesitation: giving up Trey McBride may leave them thin at TE.* |
| `fit_duplicate` | *Their likely hesitation: they're already deep at WR, so Jordan Addison may not move their lineup.* |
| `value_giving` (consensus only) | *Their likely hesitation: by consensus value they'd likely see this as giving up more than they get.* |
| `roster_crunch` | *Their likely hesitation: taking back 2 more players than they send is a roster squeeze.* |
| `other_player_keep` | — never renders (R-10). |

Tone rules — **binding MUST requirements, each mapped to its enforcement** (ruling M-6):

1. **Fixed lead-in** "Their likely hesitation:" — a label, not prose, so the user learns the
   element's meaning once and scans it thereafter (consensus-note precedent: label + body).
   Ships as the v1 default; the wallpaper risk a repeated label carries is owned by the D-7
   entropy monitor and repetition suppression, not by varying the label; a label-variation
   alternative is recorded in register item 19. *Enforced:* `test_hesitation_templates_snapshot`
   pins every template string.
2. **Hedged modality is part of the contract** — "likely," "may," "look," "leans." Never a
   flat assertion about what a person will do; de-hedging is a `tmpl_ver` bump the A/B readout
   keys on. *Enforced:* template snapshot + honesty test.
3. **Roster facts and observable state only, never mind-reading.** "Their roster leans
   rebuild" — never "they don't rate your RB," "they won't want," "they're not interested."
   The sentence describes the roster; the manager's mind is theirs. *Enforced:*
   `test_hesitation_line_honesty` asserts no template contains an unhedged mental-state verb
   (enumerated deny-list in the test).
4. **D-053 honesty, mechanically:** every name, age, position, and number resolves from the
   objection's own evidence ids; missing or null evidence in a rendered key ⇒ no sentence.
   The sentence can never claim what the analysis didn't produce. *Enforced:*
   `test_hesitation_line_honesty` (R-12).
5. **No surveillance framing.** "FTF data shows Mike…" is banned even where true — it
   advertises inside knowledge to the one audience guaranteed to include Mike (HLD §5.2).
   *Enforced:* honesty-test string ban ("FTF", "our data shows" constructions).
6. **One sentence, always.** The element never stacks objections; `top` only. The full vector
   stays server-side. *Enforced:* structural guard (single sentence interpolation) +
   `compose_narration` contract (LLD §3.8).
7. **Length budget.** Every template with maximal interpolation (longest plausible name,
   2-digit age) fits two lines of `type.bodySm` at the card's content width on the smallest
   supported device; no truncation, no scroll. *Enforced:* snapshot test asserts
   template+worst-case interpolation ≤ 120 chars; §8.3 step 11 verifies wrap.

### 5.5 User-observable states — including the undefined ones, defined

Every state a user can observe, plus the states the HLD/LLD mechanics imply but never stated
as a *product experience* — stated here so QA and the operator judge intent, not accident
(ruling M-4: draft B's FR-3.x block adopted as requirements; draft A's observable-states
table merged in, deduped).

**The states table:**

| State | What the user sees | Why / governing req |
|---|---|---|
| `trade.breaker` off (today) | Nothing; payloads byte-identical | NFR-3 |
| Dark-stamp window (`breaker` on, narrative off) | **Nothing, on every card** — no payload key exists to inspect | R-7; measurement-only phase |
| Narrative on, zero classes graduated | Nothing — by design; cold start renders silence, not noise | R-11 |
| Narrated card | One muted hesitation row, one sentence | R-13 |
| No objection clears the bar | Nothing — and **no affirmative variant** | R-17 below |
| Objection exists but suppressed (below floor / class not graduated / repetition / format gap / template error) | Nothing on that card — deliberately indistinguishable from "no objection" to the user; the *stamp* records the reason | R-9; an "objection withheld" hint would be a dark-pattern tease — the data still sees it |
| Repetition case: several same-partner cards, same objection | The single highest-severity card carries the line; the rest are silent | R-18 below; anti-wallpaper (D-7); register item 10 |
| Cross-deck repetition: the same card narrated yesterday, silent today | Suppression is per-deck, so the same (partner, objection) may narrate on one deck and not the next — intent, not a bug; QA judges it as such | register item 10 (per-deck suppression accepted, `suppressed` stamped); R-18 |
| 14-team / IDP / non-Sleeper league | Fewer named hesitations, never wrong ones — depth-based classes are envelope-gapped | HLD §3.5 |
| Unboarded counterparty (84.5% case) | Only consensus-basis or roster-structure hesitations, behind a deliberately high floor | D-7 near-tautology guard |
| Counterparty's own app | **Never any output caused by the breaker** — no notification, no surface, nothing | HLD §1.4, §5.6 |
| Demo deck (`league_demo`) | No hesitation lines | R-16; register item 15 |
| Web / extension / old mobile builds | Unchanged | R-16 |
| Two league-mates compare screens on a mirrored trade | Both sides hedged and roster-fact-grounded — two perspectives, never a contradiction of fact | R-22 below; HLD R-6 + §2.7 coherence test |
| Mid-session flag flip | Already-rendered sentence persists until the deck regenerates; the next deck reflects the new state | R-20 below |

**The requirements those rows rest on** (adopted from draft B's FR-3.x, renumbered; NEW where
marked — all NEW items trace to D-053 honesty or are register-carried):

- **R-17 — No objection clears the bar: absence is silence, not endorsement (MUST).** A card
  whose objections all sit below floors renders no element, no gap artifact, and **no
  affirmative variant** ("no red flags", "clean trade") in v1. The analysis supports "we found
  no objection above the bar" — a much weaker claim than "they have no objection"; rendering
  absence as endorsement is a confidently-wrong claim in the *opposite direction*, with the
  same screenshot risk. NEW (traced to D-053). AC: structural guard item 2 (conditional
  render only); §8.3 step 8. Register item 18 carries a v2 "positive signal" variant as an
  explicit product decision.
- **R-18 — Repetition suppression is visible inconsistency, accepted.** The same
  (partner, code) hesitation renders on at most the top-severity card of a deck
  (`breaker_max_repeat_frac`); other cards with the *same true objection* show nothing. A
  user comparing card 3 and card 7 sees an inconsistency. Accepted (register item 10, default
  yes): the alternative — wallpapering every card — destroys the signal (banner blindness,
  R-4). No "see earlier card" cross-reference copy in v1 (it would require deck-position
  knowledge the card payload doesn't carry, and it advertises the suppression machinery).
  `suppressed: "repetition"` is stamped so the A/B readout distinguishes muted from absent.
  AC: `test_repetition_suppression`; §8.3 step 9.
- **R-19 — The hesitation is wrong and the counterparty accepts happily.** Expected and
  acceptable; the design bound is that the sentence was **hedged, roster-grounded, and
  evidence-cited** — a wrong *prediction*, never a wrong *fact*. No retraction mechanism, no
  celebration/correction copy in v1 (that is Receipts' tense). The user's recourse is the
  existing FeedbackFAB; the system's learning channel is the calibration join. NEW (states
  the residual of R-2/R-6 as product intent).
- **R-20 — Mid-session flag flip.** Server: LLD E-8 (one coherent flag read per job;
  synthetic marker at log time). Client: a card already rendered from a narrated payload
  keeps its sentence until the deck regenerates (the client holds the payload; no cache
  invalidation is built); the next deck reflects the new flag state. Accepted:
  stale-by-one-deck is the same behavior every payload-gated element has. AC: §8.3 step 15.
- **R-21 — Co-owned counterparty team.** Sentences about a co-owned roster are legal because
  every narratable claim is a claim about the **shared roster or public state**, never about
  a person's intent ("their roster leans rebuild", not "Mike is rebuilding") — the §5.4
  mental-state ban does the work. Known limitation, stamped (`identity_src: "owner_id"`):
  prefs under a co-owner's account id are not read, so `other_player_keep` may under-fire for
  co-owned teams — a dark class, so the miss is invisible in v1 copy. AC:
  `test_co_owner_prefs_not_read`.
- **R-22 — Cross-seat mismatch (league-mate comparison) is accepted product behavior, with
  wording as the load-bearing defense.** Two users comparing screens may see: A's card
  hedging about B while B's own mirrored card carries no hesitation (or enthusiasm). This is
  bounded, not eliminated (HLD R-6): every sentence opens with **"Their likely hesitation:"**
  — an explicitly seat-relative *prediction*, not a fact claim — and every claim after the
  colon is a roster/public fact both screens agree on. Two hedged perspective claims from two
  seats read as two scouting reports; a contradiction of *fact* is what the §2.7
  mirrored-predicate coherence test forbids. Monitor: the R-6 narration-divergence count
  rides diagnostics from day one of narration. AC: `test_opponent_frame_breaker_coherence`,
  `test_mirrored_card_cross_seat_coherence`.

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
user decides. This PRD commits v1 to outcome 2 and defers outcome 1 to v2. The order is
forced, not preferred — and the reasons are product reasons, not just mechanics:

1. **Interleave discipline makes a v1 filter unmeasurable or dishonest.** The bake-off is
   live; `bypass_rerankers` is the standing rule (PLAN §3). A post-generation filter either
   corrupts the arm comparison (filters interleaved decks) or is bypassed on exactly the
   decks being measured (ships unmeasured). Both are worse than not shipping it.
2. **Outcome 1 on day one would kill cards on an unvalidated predictor.** The breaker's
   marquee input is a window signal known to skew ~65% rebuilder (HLD R-2, A-4). Filtering on
   that is removing volume with unmeasured accuracy — the exact anti-pattern D-067 (*accuracy,
   not volume*) names. Filtering silently shrinks decks with correlated, invisible wrongness;
   outcome 2's failure mode is one hedged sentence that's occasionally wrong and visibly
   attributable. The stamp window measures the predictor before it is allowed to delete
   anything.
3. **The user's actual blocker is trust, not deck size.** Propose has fired zero times ever
   while users file "I'd give too much" 40% of the time — they don't need fewer cards, they
   need a reason to believe a card survives contact with the other manager. A named, honest
   hesitation is that reason; a silent filter is not user-visible progress at all. And the
   §6.4 counterfactual — the filter's earn-in — is free: stamps alone answer "would the cards
   the breaker wanted to kill have underperformed?", with no serving change and no risk.

### 6.2 v1 (this plan, committed)

| Phase | Contents | Exit criterion |
|---|---|---|
| **P0 — Build & merge, flags off** | Module + seams + templates + mobile element (dark) + all LLD §7 tests + docs deltas (scope.md §4 table) + readout-spec cells confirmed (register item 16). Lands AFTER the Monday `fix/package-benchmark-sweetener` merge (§7.1); golden re-captured upstream; no behavior change | CI green (pytest, tsc, testid-lint, check-breaker-card.js); code-walk proof of both seams at the build sha; TEST_LEDGER entry; `FTF_SKIP_SIM_GATE=1` posture noted |
| **P1 — Dark stamp** | `trade.breaker` on, after the dry-run ms number is delivered (fit W0 precedent) and the LLD §8 spec is frozen (graduation SQL committed as a reviewed `scripts/` artifact). Nothing user-visible; `features_json` grows two keys | M1 gate: scored coverage ≥99%, degraded <5%, p95 job time unregressed — one week of data |
| **P2 — Calibration & per-class graduation** | M2 readout vs the preregistered spec; entropy monitor read; the operator graduates classes individually via `set_knob` (logged, auto-censoring). Which class first is register item 17 — default: the first class to clear its preregistered bar (realistically `fit_outlook` and/or consensus `value_giving`, weeks 1–2 at min-n 50) | ≥1 class beats both baselines at min-n |
| **P3 — Narration first light, operator-only** | Graduate the class, `trade.breaker_narrative` on under the tester-allowlist/experiment precedent (`onboarding_v2_rollout`); the §8.3 checklist runs in full against the graduated class | Checklist passed and logged; register item 9 honored (dark until the current bake-off serving round reaches its verdict, unless the operator accepts an annotated readout) |
| **P4 — General narration + A/B readout** | Allowlist widened; M4/M7 monitored, keyed on (`ver`, `tmpl_ver`) | operator call |
| **v2 — filter/demote** | OWN scope block, own flags, own evidence | M6 counterfactual verdict (§6.4) + the seam election (register item 6) |

**Timing collisions this phasing must respect:** one-engine-change-per-tester-week is a
calendar shared with two sibling plans and the engine queue (one operator, many eager flags);
`trade.breaker` (dark) is serving-invisible and can light off-cadence, but
`trade.breaker_narrative` and every graduation flip are user-visible-behavior changes that
take a calendar slot.

### 6.3 v2 (weighed, NOT committed — own scope block, own gates, decided by the §6.4 readout)

Bright line (PLAN §3): anything changing deck composition is a new feature with its own scope
block, evidence, and TestFlight pass; **D-067's family-suppression ruling binds any demotion
below visibility** ("one swipe must not silence a player's whole trade space" — screening is
per card, never per player-space). The three options, weighed:

| Option | What it is | For | Against |
|---|---|---|---|
| (a) Per-arm pre-draft screening | Each generator arm's candidate list is breaker-screened INSIDE generation, before the interleaved draft | The deck actually improves; screening becomes part of each arm, so the bake-off measures screened arms — a fair fight; attributes the filter's effect per arm; attacks the root (one-sided generation) | Touches every generator; needs an in-generation evaluation seam v1 doesn't build; removed cards are invisible (family-suppression ruling applies) |
| (b) Serving-layer demote, bypassed on interleaved decks | A re-ranker like every other, disabled during bake-offs | Smallest seam | **Unmeasured by construction**: the bake-off never measures the thing we'd be shipping — a permanent measurement hole in the layer this initiative just spent a plan instrumenting; two products in one flag |
| (c) User-side filter/badge | Sort or filter the deck by objection severity; user-controlled | User agency; zero server-side composition change; interleave-safe; cheapest | **Not a filter**: it doesn't remove bad cards, it outsources the filter to the user and leaves deck composition untouched (the complaint is *which trades exist*); requires serializing codes/severity beyond narrated cards, colliding with the round-4 privacy gate — usable only over graduated, whitelist-clean classes |

**Recommendation (adopted, ruling M-3): (a) per-arm in-generation screening — earned in, not
pre-committed.** The earn-in condition is A's: **the §6.4 counterfactual must support
killing** — high-severity-objection cards materially underperform (pass rate, pass-reason
match) before any screen ships. B's elimination reasoning stands as the argument against the
alternatives: (b) ships permanently-unevaluated behavior — shipping behavior the measurement
system is structurally blind to is how this codebase got a 40% value complaint in the first
place; (c) is not a filter at all, though it remains the complement worth considering
alongside (a), restricted to graduated classes, if users ask for control before (a) earns its
evidence. Option (a)'s cost — touching every generator — is bounded by making the screen ONE
shared predicate call (`trade_breaker.would_kill(card, pctx, cfg)`) applied identically in
each arm, behind per-arm flags. That is v2's scope block to write; v1 pre-commits nothing
beyond this recommendation. Proposed evidence bar in register item 6.

**LLM stance:** v1 is deterministic templates end to end. An LLM-phrased hesitation line is
not proposed here and would be a separate explicit operator decision (register item 2) with
its own honesty-enforcement story; the D-053 mechanical guarantee (the sentence cannot claim
what the analysis didn't produce) is currently *provable only because* the templates are
deterministic.

## 7. Dependencies & Risks

### 7.1 Ship sequencing (hard dependency — current facts)

The operator-approved **Monday `fix/package-benchmark-sweetener` merge** (held for the window
boundary) precedes the breaker build (PLAN A-1 pending-ship block):

1. The package depth-discount re-benchmark changes `value_giving` severity semantics — the
   breaker's severity math is written against **post-fix** semantics (LLD §3.4), and the
   calibration cohort starts at/after that merge; pre/post severities are never pooled.
2. It is a **code deploy invisible to `model_config_changes`** — the M1 rail cannot censor
   it; the LLD §8 spec names its deploy timestamp as an explicit boundary, recorded manually.
3. Auto-sweetened cards are ordinary cards to the breaker (LLD E-23); the readout gains an
   optional cut on the sweetener's `features_json` key.
4. The arm-A golden is re-captured at that ship; nothing here cites the old golden SHA.

### 7.2 Sibling coordination (one operator batch, three plans — current facts)

- **Shared taxonomy: CLOSED.** The objection-vocabulary contribution (anchor codes +
  `roster_crunch` `producer=breaker` + the producer column, `shape_aversion` ceded to negmem)
  landed as **taxonomy v1.1.1** (commit `5572604` on `plan/receipts`, three-way signed); the
  breaker build **cherry-picks the seed + taxonomy through `5572604` at landing**. See
  **reconciliation-log Errata E-1 (2026-08-21)**, which supersedes the pending-v1.1.0-PR
  language in PLAN §8/HLD §5.7 (drift-risk R-12 is thereby retired). Register items 7a/7b:
  landed, three-way signed; operator ratifies with PRD approval.
- **Bulk readers** (LLD §2.2): negmem may want equivalents; whichever plan builds first owns
  them, the other reuses (Q-11).
- **Receipts contract** (A-2): CLOSED — disjoint seams dual-signed; Receipts touches zero
  generation code.
- **Mobile release train:** the hesitation element must be in the installed build before P3
  (R-16; §8.3 preconditions).
- **Change control:** serving-affecting flips share the one-engine-change-per-tester-week
  calendar across all three siblings — one operator, three eager plans (HLD §5.1).
  **Worst-case calendar arithmetic:** narration first light lands ≈ **4–5 weeks after P1
  flag-on** in the worst case — a class clears its bar just after a serving round starts
  (≤1-week round wait) and both siblings hold the next two one-change-per-week slots. Sibling
  contention is the only unbounded term, and it is operator-arbitrated. Two escape valves:
  the mobile element ships dark on the regular release train (no calendar slot consumed), and
  the annotated-readout option (register item 9) buys back the ≤1-week round wait.
- **Re-derivations at build:** A-4 (legacy-outlook skew ~65%) and A-5 (mirrored-serve rate
  ~3.7%) re-checked before P2 — the `fit_outlook` haircut and the M3 demotion numbers depend
  on them.

### 7.3 Risks

The authoritative register is **HLD §6.1 (R-1..R-13), by reference.** The product-lens top
four, in one line each: **R-1** private-preference leak — designed away in v1 by the D-6
whitelist (the one requirement this PRD marks non-negotiable, R-10); **R-2** systematically
wrong window objections from the skewed legacy vector — haircut + margin bar + graduation
gate; **R-3** calibration theater — preregistered per-class baselines, min-n, no aggregate
match-rate claims; **R-4/R-6** wallpaper and cross-seat story mismatch — anti-wallpaper
controls + hedged two-perspective copy + the divergence monitor.

Two PRD-level risks this document adds (from draft B, kept binding):

- **R-a — Metric backslide at readout time.** The pressure to cite M3 (n≈0) or claim M4
  significance will be real when the honest cells print "insufficient". This PRD's §4
  verdicts are binding; changing a DEMOTED metric's status requires an operator decision
  logged in the register, not a readout footnote.
- **R-b — Register-as-backlog creep.** 19 register items, operator authorized build; the risk
  is items silently becoming build blockers or, worse, silently becoming built. The register
  header states: defaults ship; items are post-build tuning. Anything requiring code beyond
  the defaults (e.g. item 15's demo narration, item 18's positive-signal variant) is v1.1+
  with its own scope.

## 8. Rollout & Measurement

### 8.1 Flag/knob launch sequence

**HLD §5.1 is verbatim-by-reference the launch sequence**, including the flag table,
graduation criteria, and rollback ladder (§5.3). In brief: (1) dry-run ms number →
(2) `trade.breaker` on → dark-stamp window; (3) M1 gate; (4) shadow-based per-class
calibration readout against the preregistered spec; (5) operator graduates ≥1 class via
`set_knob`; (6) `trade.breaker_narrative` first light under **operator-only exposure**
(tester-allowlist/experiment precedent) + the §8.3 checklist; (7) general lighting.
Preconditions to step 2: readout spec frozen + dry-run ms number. If no class is graduated
when the narrative flag lights, nothing renders — by design.

Rollback, deploy-free, outermost first: narrative flag off (hot) → `breaker_min_severity`
1.1 or per-class switch to 0 → `trade.breaker` off (module unimported, key gone, rows
byte-identical) → revert commit; nothing persisted needs migration. Rungs 1–2 are rehearsed
in §8.3 (steps 16–17; step 15 feeds 16), not just documented.

### 8.2 First exposure & readout predicates

Operator-only via the device-unit allowlist/experiment mechanism (`onboarding_v2_rollout`
precedent; allowlist ships via `config/tester_allowlist.json` — Render ignores `render.yaml`
envVars). No tester sees a hesitation line before the operator has run §8.3 on their own
device. Narration-flip timing vs the live bake-off window: register item 9 — default dark
until the current serving round reaches its verdict.

Exposure := `narrated != null` AND platform = mobile. The narration readout is three-cell:
narrated / suppressed (reason-enumerated) / no-objection. All joins served-cards-only,
`is_ghost = 0`, `ver`-filtered.

### 8.3 Manual TestFlight checklist (per D-056: the ONLY runtime evidence this feature gets)

Merged checklist (ruling M-7 — one numbered list, deduped by step intent). Run by the
operator at P3, on the operator-allowlisted build, against a league where a class has been
graduated and at least one served card is known-narrated (the per-job diagnostics narrated
count identifies one). Log the pass verbatim in `living-memory/TEST_LEDGER.md`.

**Preconditions (step 0):** the installed build contains the hesitation element (build number
recorded); operator device on the narration allowlist; `trade.breaker` ON ≥1 week (P1
passed); exactly one class graduated (steps that name a class substitute the actual graduated
class); backend reachable for the payload checks (`curl` against the operator's session, or
the web debug console) — **the payload checks are OPTIONAL if infeasible, because pytest
guards pin the same facts; the UI checks are NOT optional.** Steps 1–4 constitute the
dark-window sub-checklist and MAY be run earlier, at P1, on the first build containing the
element.

| # | Step | Expected result |
|---|---|---|
| 1 | Confirm flag/knob state before starting: `trade.breaker` on, `trade.breaker_narrative` off, the intended class's `breaker_narrate_<class>` flip staged. Note: the class switch MAY already be 1 during steps 1–4 — the narrative flag alone holds the dark window (R-7, R-11) | `GET /api/feature-flags` + config show exactly this state; `model_config_changes` has the logged flips |
| 2 | **Dark-window UI check**: generate a fresh deck; swipe through every card | NO hesitation element on any card (`trade-card.breaker-hesitation` absent everywhere); cards identical in layout to the previous build |
| 3 | Dark-window payload check (optional): fetch the deck payload; search for `"breaker"` | Key absent from every card object — the dark window serves nothing (R-7) |
| 4 | Dark-window regression: like one card; pass one card and file a layer-2 decline reason | Both flows unchanged; DeclineReasonPanel files normally |
| 5 | **Graduation step**: flip `trade.breaker_narrative` ON (hot reload; logged); confirm the class switch = 1 via the `set_knob` log; regenerate the deck; find the known-narrated card | ≥1 card shows the element: a single muted row between the partner-fit line and the consensus note — small flare dot + one sentence beginning "Their likely hesitation:", matching the graduated class's LLD §1.6 template |
| 6 | Read the sentence against the card's assets | Every name/age/position it mentions is actually in the trade, on the correct side; hedged ("may"/"likely"); one sentence only |
| 7 | Class restriction: inspect every narrated card's sentence on the deck; cross-check a card whose top objection is a non-graduated or dark class (diagnostics identify one) | Every sentence is from the graduated class's template family only; the non-graduated/dark-class card shows no hesitation row — and nothing else on the card hints at the withheld objection; NO sentence ever mentions untouchables, "their board", or their rankings |
| 8 | Check every OTHER card in the deck (no-objection and below-floor cards) | Cards without a narrated objection show no hesitation row at all — no empty row, no placeholder, no "no red flags" variant, no layout shift vs a pre-feature build (R-17) |
| 9 | **Suppression state**: find (or induce, by re-rolling decks) a deck with 3+ cards against the same partner where the same hesitation would apply | At most the top-severity card for that (partner, objection) narrates; the rest show NO element and no blank-space artifact; nothing in the UI references the hidden repeats (R-18) |
| 10 | **Lowest-evidence template branch**: exercise the graduated class's lowest-evidence template branch (its LLD §1.6 row) — find/induce a card on that branch (e.g. for `fit_outlook`, a card sending picks/future capital to a win-now partner) | No null interpolation, never "None"; the sentence matches the template. If the graduated class's row has no reduced-evidence branch, record n/a naming the class and row IN THE TEST_LEDGER ENTRY, and step 10 becomes a standing obligation re-run when `fit_outlook` graduates |
| 11 | Layout: view a narrated card with the longest player name available; include a card that also shows fitLine + consensus note + strength bar | Sentence wraps ≤2 lines, no truncation/ellipsis, no clipping of TradeValueBar or the disposition row; element sits between the partner-fit line and the consensus note |
| 12 | Visual pass against the Chalkline reference (`web/style-guide.html` + design-system tokens) | Dot is flare (informational), not ice; typography matches the fit-line row; no new colors, no emoji, radius within spec; dark/light both correct |
| 13 | Pass a NARRATED card and file a decline reason | The pass-reason sheet flows exactly as before — same codes, no new step, no reference to the hesitation; the filed reason lands (this is the calibration join's right-hand side — verify a row exists if DB access is handy) |
| 14 | Open the same league on web; and, if available, pull a fresh deck in a known format-gap league (14-team or IDP) | No hesitation surface anywhere on web (mobile-only v1); format-gap cards render normally with no depth-based hesitation line |
| 15 | Mid-session flip: with a narrated deck open, flip `trade.breaker_narrative` OFF (hot reload); do not regenerate; then regenerate | The open deck's already-rendered sentence persists (payload already held — R-20); the regenerated deck shows no element anywhere |
| 16 | **Rollback rehearsal, rung 1** (confirmed from step 15): narrative flag alone removes the surface deck-over-deck, with `trade.breaker` still ON | User-visible surface gone on the next deck; stamps continue (backend diagnostics still count stamped cards) |
| 17 | **Rollback rehearsal, rung 2**: flip `trade.breaker_narrative` back ON; set `breaker_min_severity = 1.1` via `set_knob`; regenerate | No sentence on any card while both flags are ON — the knob alone silences the line (HLD §5.3 rung 2); restore the knob's prior value and confirm sentences return on a fresh deck |
| 18 | Regression sweep: like, pass, undo, propose-flow entry on narrated and non-narrated cards | All actions behave identically to the pre-feature build |
| 19 | Record: build number, the (`ver`, `tmpl_ver`) pair (the A/B join key), flag/knob states per step, screenshots of steps 5, 9, 10, 11 | TEST_LEDGER entry naming every step's pass/fail |

A failure on any step blocks general lighting (launch step 7) until fixed and re-run.

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
hand, and the "where flagged" column says where the full argument lives. Anything whose
non-default answer requires new code is marked **[v1.1+]**. Sources merged and renumbered
transparently: items 1–15 keep the PLAN §9 / HLD §6.3 numbering both drafts used (the `src`
column maps to draft A / draft B item numbers); 16–20 are PRD additions.

| # | Question | Default shipped | Status | Where flagged | src |
|---|---|---|---|---|---|
| 1 | v1 = stamp + narrative only; filter/demote deferred to v2 with its own gates | stamp + narrative only | **ruled** (PLAN; restated §6.1) | PLAN §3/§9; this PRD §6.1 | A1/B1 |
| 2 | Narrative stays deterministic templates; LLM = separate explicit decision | deterministic, no LLM | **ruled** (operator constraint, PLAN §0) | PLAN §0/§7; PRD §6.3 | A2/B2 |
| 3 | Hesitation-line surface. ~~Original default: append inside the existing narrative string~~ — superseded 2026-08-21: verified NO client renders `TradeCard.narrative` (the append option ships an invisible feature) | distinct card element, mobile-only, muted hint band | **ruled by convergence** (HLD M-3; operator may still override with the "make `narrative` render first" precondition ticket) | PLAN §9 #3; HLD §2.4; LLD §1.8 | A3/B3 |
| 4 | `breaker_min_severity` initial bar (with the per-class switches, the only user-visible-effect knobs in v1) | 0.60 ships; re-leveled from the calibration readout, never guessed | open — post-readout tuning | PLAN §9 #4; LLD §4 | A4/B4 |
| 5 | Viewer-seat shadow run — acceptable compute for the PRIMARY calibration population? (~2×/card, same ms budget; turning it off starves M2) | on (`breaker_shadow_run` = 1.0) at `trade.breaker` first light | open (default ships; **confirm the compute posture at Phase-1 flag-on** — on the flag-on checklist) | PLAN §9 #5; LLD §2.5/§4 | A5+A16/B5 |
| 6 | v2 seam election + evidence bar: (a) per-arm pre-draft · (b) bypassed-on-interleave demote · (c) user-side filter. PRD recommends **(a)**, advises against (b) (unmeasured by construction) and notes (c) is not a filter (§6.3); earn-in = the §6.4 counterfactual supports killing. Proposed unlock bar: M6 pooled cut at n ≥ 200 decided stamped cards per cohort, would-kill cohort like-on-viewed ≤ ½ the keep cohort's (CI-separated), M2 precision passed for every class contributing to the kill bar, per-arm cut directionally consistent. D-067 family-suppression binds any demotion below visibility | none built — decided after the §6.4 readout | open — operator ratifies bar + seam preference now or at the M6 readout | PLAN §9 #6; this PRD §6.3 | A6/B6+B18 |
| 7a | `roster_crunch` extension code in the shared taxonomy (`producer=breaker`) | in taxonomy v1.1.1 | **landed, three-way signed; operator ratifies with PRD approval** (taxonomy v1.1.1 at `5572604`; build cherry-picks through it — reconciliation-log E-1) | PRD §7.2; PLAN §9 #7a; HLD D-1 | A7a/B7a |
| 7b | `shape_aversion` as `producer=negmem` (breaker may cite it only via the future memory→breaker coupling); producer column | in taxonomy v1.1.1 | **landed, three-way signed; operator ratifies with PRD approval** (same landing) | PRD §7.2; PLAN §9 #7b; HLD D-2 | A7b/B7b |
| 8 | Evidence whitelist: private counterparty state stamps dark, never renders — accepted? And may even a generic form ("unlikely to move him") ever render? | dark-only; generic form does NOT render | open (default ships; PRD marks it non-negotiable in v1 — R-10) | HLD §6.3 #8, D-6, §5.6 | A8/B8 |
| 9 | Narration-flip timing vs the live interleaved bake-off window. **Middle rung (adopted):** operator-only first light on ONE allowlisted device, with that device-unit EXCLUDED from arm readouts, does not count as "lighting mid-window" — one device cannot meaningfully contaminate the arm comparison, and the exclusion makes it exact. P4 (general narration) keeps default-dark-until-verdict with the annotated-readout escape | `trade.breaker_narrative` stays DARK until the current serving round's verdict (operator-only single-device first light excepted, readout-excluded); mid-window general lighting requires accepting an annotated readout | open — operator calendar call | HLD §6.3 #9 | A9/B9 |
| 10 | Per-deck repetition suppression: same card, different decks, different narration — acceptable? | yes, with `suppressed` stamped | open (default ships; R-18 states the UX) | HLD §6.3 #10, D-7 | A10/B10 |
| 11 | Inferred-window `fit_outlook` narration: wait for the composite's engine-wide graduation, or ship behind the high-margin bar? | high-margin bar (`breaker_outlook_narrate_margin`); declared outlook is confidence-only on agreement | open | HLD §6.3 #11, D-8 | A11/B11 |
| 12 | `breaker_stamp_scope`: full-candidate-pool stamping | served-deck-only; not built | open — v2 study option [v1.1+] | HLD §6.3 #12, D-9 | A12/B12 |
| 13 | Organic them-score coverage by promoting the fit stamp to organic decks — a fit-challenger scope question, registered here for visibility | `breaker.them` null on organic decks | open (belongs to fit-challenger) | HLD §6.3 #13, D-3 | A13/B13 |
| 14 | Declared-outlook disclosure: is narrating from a privately declared `team_outlook` ever acceptable? | never in v1 — confidence-only on public-inferred agreement; disagreement mutes the class; stamp records both | open (default ships) | HLD §6.3 #14, D-8 | A14/B14 |
| 15 | Demo-deck narration as demo material (T-1 lift option). Weighed (draft B, adopted): *for* — the demo deck is the first-run sales surface, a hesitation line there demos the scout persona at the moment the user forms their model of the app; *against* — (a) demo partners are synthetic: training users on fabricated hesitations about fake managers teaches that the line is decorative flavor, the opposite of the trust the feature must earn; (b) demo rows never join outcomes ⇒ zero calibration value at the cost of its own fixture set, honesty audit, and TestFlight steps; (c) the demo builder constructs `members` without the viewer (Q-1) — an input shape production never sees; (d) narration first light is weeks post-launch anyway, past the window where demo matters most | demo decks skipped, no narration | **RECOMMENDED-CLOSED pending operator veto**: keep the skip; revisit as a deliberate demo-material product lift only after ≥1 class has graduated on real-league copy [v1.1+] | LLD §9 Q-10 (T-1 ruling); PRD R-16 | A15/B15 |
| 16 | Calibration TBD cells (LLD §8): proposed min n = 50 per class (primary stratum `consensus` basis × `legacy` outlook_src), required margin ≥ +10 points over BOTH baselines, per class; `roster_crunch` and `other_player_keep` rows reported-never-gated in v1 (M2 verdict, §4.1). **Consequence note:** at n=50 a +10-pt margin is ≈1–1.4 SE — graduation is PROVISIONAL, paired with a re-read at n≈100 (rung-2 reversible). Horizons scale ~linearly with min-n: n=100 ⇒ `fit_outlook`/`value_giving` in 2–4 wks, `fit_new_weakness` 10–16 wks = out of v1. Any min-n change lands BEFORE `trade.breaker` lights (P1 precondition); a later change keeps the accrued cohort, with the gate read only at the new n. Min-n does NOT move the n=130/side claim bar (different population, different question). The §4.1 realism column and register 17's throughput argument are FUNCTIONS OF this item — recompute both if it moves | proposed numbers above | open — **operator confirms before `trade.breaker` lights** (P1 precondition) | LLD §8; PRD §4.3 | —/B16 |
| 17 | **First class to graduate** — which class gets the first `breaker_narrate_<class>` flip? **Default: the first class to clear its preregistered bar.** Realism at min-n 50 (§4.1 M2): only `fit_outlook` and consensus `value_giving` can graduate inside v1's 1–2-week horizon; `fit_new_weakness` needs 5–8 weeks; `roster_crunch` is reported-never-gated (no filed-reason anchor). Two positions, both recorded: **safety (draft A)** — graduate the low-risk class first: `fit_new_weakness` mirrors a live viewer-seat predicate, renders only public lineup math, and its failure mode is a checkable roster fact, where `fit_outlook` inherits the skewed legacy window (R-2); **throughput (draft B)** — the low-risk class can't reach n inside v1's horizon, so waiting for it idles narration for 5–8 weeks; `fit_outlook` carries the haircut + margin bar + graduation gate precisely so it can go first. The operator holds the flip either way — graduation is a logged per-class `set_knob` decision against the class's own readout row | first class to clear its preregistered bar | open — decided at P2 from the per-class readout rows | this PRD §4.1/§6.2; HLD D-6/D-8/§2.7 | A17/— |
| 18 | Positive-signal variant ("no objection found" affirmative copy) — R-17 bans it in v1 as an over-claim in the opposite direction | absent | open — explicit product decision if ever wanted [v1.1+] | PRD R-17 | —/B17 |
| 19 | Lead-in label: fixed "Their likely hesitation:" vs varied phrasing. Fixed label ships (§5.4 rule 1 — learn once, scan thereafter); the repeated-label wallpaper risk is owned by the D-7 entropy monitor + repetition suppression, not by label variation; label variation would fragment the element's scannability and the template-snapshot discipline for a risk another mechanism already owns | fixed label | open (default ships; any change is a `tmpl_ver` bump) [v1.1+] | PRD §5.4; HLD D-7 | — (M-6) |
| 20 | M-G5 tripwire numbers (§4.2 enforcement definition): report-only below n=130/side; non-statistical tripwire from n≥30/side — narrated-deck like-on-viewed < ½ the concurrent non-narrated rate ⇒ operator review + logged HOLD on allowlist widening (no auto-rollback, no "degradation" finding), resolved at the n=130 read; M-G5 blocks FURTHER WIDENING only once either side reaches 130 | numbers above | open (defaults ship; re-leveled with data) | PRD §4.2 M-G5 | — (BF-3) |

---

*End of merged PRD candidate. Provenance: scaffold, product voice, guardrail set, worked
examples, and observable-states table from draft A; expected-n metric verdicts, non-goal
tripwire list, undefined-user-states requirements, copy-rule test mapping, checklist rigor
steps, and the R-a/R-b risks from draft B — merged under orchestrator rulings M-1..M-10.
Contestable calls for cross-review: §6.1's outcome weighing, §6.3's (a)-over-(c)
recommendation with its earn-in, register 17's default (first-to-clear-bar) with both
positions, §5.5's suppression-invisible decision, and §5.4's fixed lead-in. Mechanics are
cited from the converged LLD; any divergence found in review is a defect here, not there.*
