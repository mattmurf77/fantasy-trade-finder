# PRD — Counterparty breaker (draft B: engineering / feasibility lens)

**Date:** 2026-08-21 · **Status:** INDEPENDENT DRAFT for orchestrator merge (not a critique of
draft A; written blind to it).
**Binds under:** [PLAN.md](../PLAN.md) (AMENDED) → [HLD.md](../HLD.md) (CONVERGED) →
[LLD.md](../LLD.md) (CONVERGED) → this PRD. Requirements below TRACE to those docs; anything
not traceable is marked NEW and lands in the decision register.
**Standing fact:** the operator has already authorized building after PRD convergence. The §9
register is **post-build tuning**, not a build blocker — defaults ship; the operator re-levels
knobs and TBD cells afterward.
**This draft's job** (assigned lens): unspecified requirements, undefined user states,
unmeasurable metrics, and scope creep. Where a claimed metric cannot reach minimum n at
current tester volume, this draft kills it in writing rather than letting it die quietly at
readout time.

---

## 1. Summary

v1 ships a deterministic evaluation layer (`backend/trade_breaker.py`) that predicts the
counterparty's most likely decline reason for every served card, in the shipped
`trade_pass_reasons` layer-2 vocabulary plus one extension (`roster_crunch`), stamps the full
objection vector dark into `deck_impressions.features_json`, and — behind a second flag and a
per-class maturity ladder — renders the single top objection as one hedged, template-composed
"their likely hesitation" sentence in a new element on the mobile trade card. It kills
nothing, reorders nothing, filters nothing (NFR-1); the filter/demote outcome is v2, earned
or refused by the §6.4 counterfactual computed from v1's stamps.

Two flags: `trade.breaker` (stamp) and `trade.breaker_narrative` (sentence), both default
false. 25 knobs (LLD §4). No new tables, routes, or migrations. One mobile element, one
structural guard, one TestFlight checklist (§8.3 — written in full here).

## 2. Problem

The engine argues exactly one side: 96.3% of 1-for-1 cards exist in one direction, 84.5% of
served cards never consult a partner board, the consensus-path viewer receives more on 86.3%
of cards (arm-B audit). `deck_outcomes.action='propose'` has fired **zero times ever** —
every suggestion the app has ever made has died before a send, and users' filed pass reasons
(40% `value_giving`, 33% `fit_outlook`, n=208) say the cards ignore exactly the question a
real trader asks first: *why would the other manager say no?* The card today is a calculator.
The breaker's product claim is: name the other seat's strongest objection before the user
walks into it, and the card becomes a scout.

The dominant failure mode is not a crash — it is being **confidently wrong about a named,
real human, in copy their league-mate can screenshot** (HLD governing stance). Every
requirement in §5 that looks like paranoia traces to that sentence.

## 3. Goals & Non-Goals

### Goals (v1)

| # | Goal | Measured by |
|---|---|---|
| G-A | Every served card on a flag-on deck carries a coded, evidenced objection prediction | scored coverage ≥99% of served impressions; degraded share (rungs 1–3) < 5% (HLD NFR-6) |
| G-B | Calibration is a join, not new instrumentation | §7 M2 readout runs against the preregistered LLD §8 spec |
| G-C | The card can tell the user what to preempt — without asserting private state or mental state | §5.4 copy requirements + D-6 whitelist; zero private-state leaks (structurally impossible, test-enforced) |
| G-D | The v2 filter decision is made from data | §6.4 counterfactual computable from stamps alone within the v1 window |
| G-E | Wrongness is bounded, attributable, cheap to retract | provenance markers; 4-rung rollback ladder rehearsed in the TestFlight checklist (§8.3 steps 11–12) |

### Non-Goals (v1) — the scope-creep tripwire list, explicit

Each item below has been *proposed or gestured at* somewhere in this initiative's history and
is **out**. A build diff touching one of these is a scope defect, not an improvement:

1. **Filtering, demoting, reordering, or draft changes** on any deck under any flag this plan
   ships (v2, own scope block — PLAN §3 bright line; D-11 seam-creep guard test).
2. **LLM anywhere** — copy, class selection, severity (operator constraint; deterministic
   templates only; a future LLM variant is a separate explicit operator decision).
3. **Web or extension rendering** of the payload key (mobile-only surface; HLD §2.4).
4. **Negmem coupling** — reading `negmem_*` tables, emitting `shape_aversion`, feeding
   `acceptance_prior` (D-2; producer-column closure test).
5. **Organic them-score** — promoting the fit stamp to organic decks is a fit-challenger
   scope question (register item 13); `breaker.them` stays null on organic decks.
6. **Taxonomy mirror module** — no breaker-local copy of the shared taxonomy; codes
   cross-check against `database.PASS_REASON_LAYER2` by import; vocabulary changes only via
   PR to `docs/plans/shared/trade-shape-taxonomy.md` (v1.1.0 bump).
7. **New tables/columns/routes/env vars**; `breaker_` prefix reserved-unused
   (`test_no_breaker_tables`).
8. **Client switching on objection codes** — server-composed sentence only;
   cross-client-invariants row "n/a in v1".
9. **Any counterparty-side output** — no notification, no cross-user surfacing, ever in v1.
10. **Demo-deck narration** (T-1 skip ships; register item 15 carries the product lift).
11. **Co-owner union resolution** (M-7: owner-id only + `identity_src` marker; union is a
    named v1.1 candidate needing a data-path change, Q-3).
12. **Board staleness handling** (Q-2/A-6 open; `board_auth` does not encode staleness).
13. **Bench-size / forced-drop modeling** for `roster_crunch` (Q-4: omitted, not
    approximated).
14. **Full-candidate-pool stamping** (D-9; register item 12, a v2 study option).
15. **Value-weighted `fit_outlook` lean** (M-8 confirmed unweighted; a weighted variant is a
    v2 conversation gated on a replacement coherence proof).

## 4. Success Metrics — with the honest n

**Context every number below lives in:** single-digit active testers (recent peak ~200
decided cards across 4 days from 5 users; the trade-engine-accuracy tester protocol targets
~400 decided/week at 10 testers), 208 coded pass reasons **all-time**, `propose` = 0
all-time, and the mirrored-card serve rate ~3.7% (A-5, unverified). Metrics that cannot
reach minimum n in a 6-week v1 window are **killed or demoted to "counted, never gated"**
here, in writing, so the readout can't quietly redefine success.

### 4.1 Metric table

| ID | Metric | Gate? | Expected n per readout cell (realistic window) | Verdict |
|---|---|---|---|---|
| M1 | **Coverage & cost**: scored-stamp coverage of served impressions; degraded share by rung; `ms` p50/p95 vs `breaker_ms_budget`; p95 job time unregressed | YES — graduation gate for `trade.breaker` (HLD §5.1) | every served impression (~1,300 accrued in days at current volume) — n is not a constraint | **KEEP.** Attributable within one week of dark-stamp |
| M2 | **Calibration (primary)**: per-class precision of `breaker_shadow.top` vs the viewer's filed layer-2 code, vs TWO baselines — majority-class (predict `value_giving` always ⇒ ~40% aggregate match, n=208; re-derive at readout) and stratified-random (draw from the filed-reason distribution) — with per-class min-n gates, stratified `outlook_src` × board basis | YES — per-class narration graduation (D-6) | Coded reasons ≈ 75–150/week under the tester protocol (passes ≈ 60–80% of decisions; ~90% file a coded reason; minus ~10% `other_text`, excluded by construction). Per class/week: `value_giving` ~30–60 · `fit_outlook` ~25–50 · `fit_new_weakness` ~5–10 · `value_getting` ~4 · everything else ≤3 | **KEEP with per-class realism:** at the proposed min-n = 50/class (§9 item 16), `fit_outlook` and `value_giving` reach gate n in **1–2 weeks**; `fit_new_weakness` in **5–8 weeks**; `fit_duplicate` likely not inside v1; `roster_crunch` has **no filed-reason anchor at all** (extension code — no manager has ever been offered it as a pass reason) and `other_player_keep` is a permanently-dark class: both rows are **calibration-reported, never graduation-gated in v1** (LLD §8 already says roster_crunch "may remain unpassable — stated, not hidden"; this PRD makes that the plan, not a caveat) |
| M3 | **Counterparty-seat calibration** (PLAN §6.2a): mirrored card served to the counterparty + their filed reason vs the breaker's prediction | NO | 3.7% mirrored-serve rate × both-seats-decided × reason-filed ⇒ **n≈0–2/month**. | **KILLED as a v1 readout.** Long-horizon accumulator only; never cited in any graduation or v2 argument until its cell prints n ≥ 30 (which v1 will not see). Anyone quoting this cut before then is doing calibration theater (R-3) |
| M4 | **Narration lift**: like-on-viewed delta on narrated vs non-narrated cards; pass-reason-mix shift | DIRECTIONAL only | 10pp lift at ~20% base needs ≈300 decided/arm; narration applies to a *subset* of cards (one class graduated, floors, suppression) — realistic narrated-card decisions ≈ 30–80/week across all testers | **DEMOTED: directional, never a gate.** Reported with cell n; no significance claim below n=130/side (the 15pp bar from the accuracy PLAN's power note). The A/B keys on (`ver`, `tmpl_ver`) and censors at every §7.2 boundary |
| M5 | **Like→propose conversion** | — | `propose` = 0 all-time; the funnel bottom does not exist yet (G1 gate: ≥3 real sends, owned by trade-engine-accuracy) | **KILLED.** Not a breaker metric in any form. Proposes are *counted* on narrated cards (free join) and reported as raw counts; the breaker never claims credit or blame for a funnel that has never fired. If G1 is passed during the v1 window, a propose-mix cut may be added to the readout — as counts, still not a gate |
| M6 | **Filter counterfactual** (§6.4): outcome delta, would-kill cohort (top severity ≥ candidate bar) vs rest, per arm from stamps | YES — the v2 earn-in | Decided **stamped** cards ≈ 150–400/week (all decided cards on flag-on decks). Cohorts fill pooled-across-arms in **2–3 weeks**; per-arm cells at interleaved thirds need ~6–9 weeks for the same resolution | **KEEP.** The v2 decision reads the pooled cut first, per-arm as confirmation; both reported with cell n; D-091/QB-seam/sweetener-merge censoring per LLD §8 |
| M7 | **Anti-wallpaper monitors**: class-entropy of `top.code` weekly; narrated/suppressed/no-objection three-cell split; mirrored-serve narration-divergence count (R-6) | Red-line before narration graduation (entropy); others reported | diagnostics-derived, no n constraint | **KEEP** |

### 4.2 What this section commits the readout to

- Every reported precision/lift **carries its cell n**; cells below min-n print
  "insufficient", never pool silently (LLD §8, restated as a product requirement).
- The §8 TBD cells get **proposed defaults in this PRD** (§9 item 16) so the operator
  confirms numbers rather than inventing them at readout time: min n = 50 per class
  (primary stratum `consensus` basis × `legacy` outlook_src), required margin ≥ +10 points
  over BOTH baselines, per class.
- The **calibration cohort starts at/after the `fix/package-benchmark-sweetener` Monday
  merge** (LLD §3.4/§8 — a code-ship boundary the M1 rail cannot see); nothing pools across
  it.

## 5. Requirements

Numbered; each cites its source. AC = acceptance criteria. "MUST" is test-or-checklist
enforced.

### 5.1 Evaluation & stamp (FR-1x — trace: HLD §2, LLD §1–§3)

- **FR-1.1** `stamp_breaker` runs at the post-mutation-stack, pre-ghost-split seam on every
  non-demo, non-superseded job with `trade.breaker` on; evaluates the served deck only
  (D-9); sets `card.breaker` (+ `card.breaker_shadow` when `breaker_shadow_run ≥ 1`) on
  **every** card — scored payload or labeled marker; absence impossible on a flag-on row.
  AC: `test_breaker_zero_ordering_effect`, `test_impressions_breaker_uniform_keys`,
  `test_midjob_flag_flip_no_crash`.
- **FR-1.2** Objection codes are the closed set: 9 coded `PASS_REASON_LAYER2` codes minus
  `other_text`, restricted to the 6 evaluated classes, plus `roster_crunch`
  (`producer=breaker`). `shape_aversion` never appears in any field. Evidence keys ⊆ the
  LLD §2.4 enums. AC: `test_breaker_vocabulary_closure`.
- **FR-1.3** Determinism: same inputs ⇒ same payload, byte-for-byte (3-dp severity, 1-dp ms,
  `TIEBREAK_PRIORITY`, frozen per-job knob snapshot, pinned `'market'` stud-tax).
  AC: `test_breaker_deterministic`, `test_knob_snapshot_frozen_within_job`,
  `test_stud_tax_pinned_market`.
- **FR-1.4** Degradation is a labeled ladder (LLD §5.1); rank-correlated missingness is
  stamped (`rung 3`) so readouts exclude it; per-class predicate crashes stamp
  `predicate_error` durably. AC: `test_budget_ladder_labeling`,
  `test_per_class_exception_contained`, `test_exception_rungs`.
- **FR-1.5** Flag-off byte identity: no import, no attribute, no `features_json` key, no
  payload key, no publish-count change. AC: the four `test_flag_off_*` tests.
- **FR-1.6** Pre-flag-on dry run: the operator receives a measured ms number on 60-card
  decks (fit W0 precedent) **before** `trade.breaker` lights. NEW-but-traced (HLD NFR-2);
  logged in TEST_LEDGER.

### 5.2 Narration (FR-2x — trace: HLD D-5/D-6/D-7, LLD §1.6/§3.8)

- **FR-2.1** The sentence is composed server-side by `compose_narration` →
  `trade_narrative.hesitation_line`; the client renders `data.breaker.sentence` verbatim in
  a distinct element and never switches on `code`. AC: structural guard §7.5 items 2–3.
- **FR-2.2** Narration eligibility chain exactly as LLD §3.8 (switch → whitelist/basis →
  envelope → floors + `breaker_min_severity` → outlook margin/agreement → repetition
  suppression). All six switches default 0: **first light renders nothing by design**;
  graduation is a logged `set_knob` flip per class.
- **FR-2.3** The serialized payload is **narration-gated**: dark window ⇒ no `breaker` key
  at all; `breaker_shadow` never serializes. AC:
  `test_breaker_payload_absent_during_dark_window`,
  `test_breaker_shadow_never_serialized`.
- **FR-2.4** The seam owns a republish iff narrated_count > 0, so the sentence reaches the
  client on every flag combination including `deck.signal_v2` off. AC:
  `test_narrated_payload_reaches_snapshot_all_flag_combos`.

### 5.3 Undefined user states — defined (FR-3x; the lens assignment)

Every state below is currently implied by the HLD/LLD mechanics but **not stated as a
product experience**. This section states them so QA and the operator judge intent, not
accident.

- **FR-3.1 — No objection clears the bar: absence is silence, not endorsement.** A card
  whose objections all sit below floors renders no element, no gap artifact, and **no
  affirmative variant** ("no red flags", "clean trade") in v1. Rationale: the analysis
  supports "we found no objection above the bar", which is a much weaker claim than "they
  have no objection" — rendering absence as endorsement is a confidently-wrong claim in the
  other direction, with the same screenshot risk. NEW (traced to D-053 honesty). AC:
  structural guard item 2 (conditional render only); TestFlight step 7. Register item 17
  carries a v2 "positive signal" variant as an explicit product decision.
- **FR-3.2 — Repetition suppression is visible inconsistency, accepted.** The same
  (partner, code) hesitation renders on at most the top-severity card of a deck
  (`breaker_max_repeat_frac`); other cards with the *same true objection* show nothing.
  A user comparing card 3 and card 7 sees an inconsistency. Accepted behavior (HLD register
  item 10, default yes): the alternative — wallpapering every card — destroys the signal
  (banner blindness, R-4). No "see earlier card" cross-reference copy in v1 (it would
  require deck-position knowledge the card payload doesn't carry, and it advertises the
  suppression machinery). `suppressed: "repetition"` is stamped so the A/B readout
  distinguishes muted from absent. AC: `test_repetition_suppression`; TestFlight step 6.
- **FR-3.3 — The hesitation is wrong and the counterparty accepts happily.** Expected and
  acceptable; the design bound is that the sentence was **hedged, roster-grounded, and
  evidence-cited** — a wrong *prediction*, never a wrong *fact*. No retraction mechanism, no
  celebration/correction copy in v1 (that is Receipts' tense: retrospective accuracy
  accounting). The user's recourse is the existing FeedbackFAB; the system's learning
  channel is the calibration join. NEW (states the residual of R-2/R-6 as product intent).
- **FR-3.4 — Mid-session flag flip.** Server: LLD E-8 (one coherent flag read per job;
  synthetic marker at log time). Client: a card already rendered from a narrated payload
  keeps its sentence until the deck regenerates (the client holds the payload; no cache
  invalidation is built); the next deck reflects the new flag state. Accepted: stale-by-one
  -deck is the same behavior every payload-gated element has. AC: TestFlight step 10.
- **FR-3.5 — Co-owned counterparty team.** Sentences about a co-owned roster are legal
  because every narratable claim is a claim about the **shared roster or public state**,
  never about a person's intent ("their roster leans rebuild", not "Mike is rebuilding") —
  the §5.4 mental-state ban does the work here. Known limitation, stamped
  (`identity_src: "owner_id"`): prefs under a co-owner's account id are not read, so
  `other_player_keep` may under-fire for co-owned teams — a dark class, so the miss is
  invisible in v1 copy. AC: `test_co_owner_prefs_not_read`.
- **FR-3.6 — Demo decks: the T-1 skip ships; recommendation = KEEP the skip (weighed).**
  The lift option ("narrate demo decks as demo material") was preserved as a PRD question
  (LLD Q-10). Weighing it:
  *For narrating demo:* the demo deck is the first-run sales surface; a hesitation line
  there demos the scout persona at the exact moment the user forms their model of the app.
  *Against:* (a) demo partners are synthetic — training users on fabricated hesitations
  about fake managers teaches that the line is decorative flavor, the opposite of the trust
  the feature must earn; (b) demo rows never join outcomes, so demo narration produces zero
  calibration value at the cost of its own fixture set, template-honesty audit, and
  TestFlight steps; (c) the demo league builder constructs `members` without the viewer
  (LLD Q-1) — PartnerContext math there exercises an input shape production never sees;
  (d) narration first light is weeks post-launch anyway (dark window + graduation), so the
  demo audience wouldn't see it in the window where demo matters most.
  **Recommendation: keep the skip in v1; revisit as a deliberate demo-material product lift
  only after ≥1 class has graduated on real-league copy** (register item 15).
- **FR-3.7 — Cross-seat mismatch (league-mate comparison) is accepted product behavior,
  with wording as the load-bearing defense.** Two users comparing screens may see: A's card
  hedging about B while B's own mirrored card carries no hesitation (or enthusiasm). This
  is bounded, not eliminated (HLD R-6): every sentence opens with **"Their likely
  hesitation:"** — an explicitly seat-relative *prediction*, not a fact claim — and every
  claim after the colon is a roster/public fact both screens agree on. Two hedged
  perspective claims from two seats read as two scouting reports; a contradiction of *fact*
  is what the §2.7 mirrored-predicate coherence test forbids. Monitor: the R-6
  narration-divergence count rides diagnostics from day one of narration. AC:
  `test_opponent_frame_breaker_coherence`, `test_mirrored_card_cross_seat_coherence`.

### 5.4 Copy requirements — testable, not stylistic (FR-4x — trace: HLD §5.2, LLD §1.6)

The v1 sentences, verbatim from LLD §1.6 (PRD polish would bump `tmpl_ver`; this draft
proposes **no wording changes** — the templates already pass every rule below):

| Class | v1 sentence |
|---|---|
| `fit_outlook` (rebuild side) | "Their likely hesitation: their roster leans rebuild, and this sends them {name}, a {age}-year-old {pos}." |
| `fit_outlook` (win-now side) | "Their likely hesitation: they look win-now, and this asks them to take back future capital." |
| `fit_new_weakness` | "Their likely hesitation: giving up {name} may leave them thin at {pos}." |
| `fit_duplicate` | "Their likely hesitation: they're already deep at {pos}, so {name} may not move their lineup." |
| `value_giving` (consensus basis only) | "Their likely hesitation: by consensus value they'd likely see this as giving up more than they get." |
| `roster_crunch` | "Their likely hesitation: taking back {extra} more players than they send is a roster squeeze." |
| `other_player_keep` | — never renders (permanently dark, D-6) |

The tone rules as MUST requirements, each with its enforcement:

- **FR-4.1** A sentence MUST NOT name a source the evidence lacks: every interpolated
  name/age/position/number resolves from `objection["evidence"]` ids; missing or null
  evidence in a rendered key ⇒ the sentence does not render (None, honest silence — never a
  fallback guess, never "None-year-old"). AC: `test_hesitation_line_honesty`.
- **FR-4.2** Hedged modality is contract, not style: every template carries "likely"/"may";
  the snapshot test pins the strings, so de-hedging is a `tmpl_ver` bump that the A/B
  readout keys on. AC: `test_hesitation_templates_snapshot`.
- **FR-4.3** No mind-reading verbs, no mental states: claims are about rosters, lineups,
  and public values ("their roster leans rebuild"), never beliefs ("they don't rate your
  RB", "they want", "they think"). AC: honesty test asserts no template contains an
  unhedged mental-state verb (enumerated deny-list in the test).
- **FR-4.4** No surveillance framing: "FTF" (and any "our data shows" construction) is
  banned from templates even where true — it advertises inside knowledge to the one
  audience guaranteed to include the subject. AC: honesty test string ban.
- **FR-4.5** No private-state derivation in copy, structurally: `other_player_keep` and
  board-basis `value_giving` are narration-ineligible outright regardless of switches
  (whitelist + basis rule), and the payload is narration-gated, so neither prose NOR
  structured data can leak a board delta or a list membership. AC:
  `test_narration_whitelist_dark_classes`, `test_breaker_payload_absent_during_dark_window`.
- **FR-4.6** Length budget: every template with maximal interpolation (longest plausible
  name, 2-digit age) fits two lines of `type.bodySm` at the card's content width on the
  smallest supported device; no truncation, no scroll. NEW (physical-fit requirement,
  §5.5). AC: snapshot test asserts template+worst-case interpolation ≤ 120 chars;
  TestFlight step 9 verifies wrap.

### 5.5 Mobile surface (FR-5x — trace: LLD §1.8; verified against `TradeCard.tsx` this checkout)

- **FR-5.1** The element mounts in `mobile/src/components/TradeCard.tsx` between the FB-47
  partner-fit row (`:452–458`) and the consensus-note block (`:460–478`) — the card's
  muted, hint-tier band. Physical budget verified: the region already stacks
  fitLine → consensus note → StrengthBar above the player split; the element adds one
  ≤2-line `bodySm` row (~20–36pt) in the scrollable card body, below the wildcard chip and
  header, above the value bar and disposition row — no pinned bottom bar on this surface,
  no interaction with `setPinnedBottomBarHeight`, no FeedbackFAB change (no new screen).
- **FR-5.2** Render is conditional on `data.breaker?.sentence` — payload presence IS the
  client gate (server serializes only narrated cards); no client-side flag read, which
  would add a second gate that can only disagree (fit precedent). AC: structural guard
  item 2.
- **FR-5.3** Chalkline: flare dot (informational accent, ADR-005), token-only colors,
  radius ≤ 8, `chalkline/Text`-compatible type tokens; testIDs
  `trade-card.breaker-hesitation` / `.body` (dot idiom, Q-8), passing `testid-lint.sh`.
  AC: structural guard items 1, 4, 7.
- **FR-5.4** The element ships **dark in the next regular release train** — payload-gated,
  it renders nothing until the server serves a sentence — so narration graduation is
  decoupled from EAS/TestFlight build cadence. The build containing the element MUST be the
  installed build before TestFlight checklist steps 3+ can run; step 0 pins this. NEW
  (sequencing consequence, traced to HLD §5.1 launch sequence).
- **FR-5.5** TS payload type gains optional `breaker?: {code; severity; sentence}` in
  `src/shared/types.ts`; no minimum-version gate (older builds ignore unknown keys).
  AC: structural guard item 5; `tsc --noEmit`.

### 5.6 Measurement plumbing (FR-6x — trace: LLD §8)

- **FR-6.1** The calibration-readout spec (LLD §8) is committed with its TBD cells filled
  (operator-confirmed §9 item 16) **before `trade.breaker` first lights**; the graduation
  SQL ships as a reviewed `scripts/` artifact.
- **FR-6.2** Readouts censor at: ghost boundary (no ghost rows ever, M-12), D-091 window,
  both 1QB QB repricing seams (04:46Z and 11:48Z), every `model_config_changes` timestamp,
  AND the named `fix/package-benchmark-sweetener` deploy timestamp (invisible to the M1
  rail — recorded manually in the spec).
- **FR-6.3** Cross-version pooling refuses: calibration keys on `ver`; narration A/B on
  (`ver`, `tmpl_ver`).

## 6. Scope & Phasing

| Phase | Contents | Exit criterion |
|---|---|---|
| **P0 — build** | Module + seams + templates + mobile element (dark) + all §7 tests + docs deltas (scope.md §4 table) + taxonomy v1.1.0 PR + readout spec cells confirmed | CI green (pytest, tsc, testid-lint, check-breaker-card.js); code-walk proof of both seams at the build sha; TEST_LEDGER entry; `FTF_SKIP_SIM_GATE=1` posture noted |
| **P1 — dark stamp** | `trade.breaker` on after the dry-run ms number and after the sweetener Monday merge | M1 gate: scored coverage ≥99%, degraded <5%, p95 job time unregressed — one week of data |
| **P2 — calibration** | M2 readout vs the preregistered spec; entropy monitor read | ≥1 class beats both baselines at min-n (realistically `fit_outlook` and/or consensus `value_giving`, weeks 2–4) |
| **P3 — narration, operator-only** | Graduate the class (`set_knob`), `trade.breaker_narrative` on under operator-only exposure (tester-allowlist precedent); TestFlight checklist §8.3 run in full | Checklist passed and logged; register item 9 honored (dark until the current bake-off serving round reaches its verdict, unless the operator accepts an annotated readout) |
| **P4 — general narration** | Allowlist widened; M4/M7 monitored | operator call |
| **v2 — filter/demote** | OWN scope block, own flags, own evidence | M6 counterfactual verdict (§6.4) + the seam election (§9 item 18) |

**Timing collisions this phasing must respect:** one-engine-change-per-tester-week is a
calendar shared with two sibling plans and the Phase-3 engine queue (one operator, many
eager flags — reconciliation-log risk); `trade.breaker` (dark) is serving-invisible and can
light off-cadence, but `trade.breaker_narrative` and every graduation flip are
user-visible-behavior changes that take a calendar slot.

### 6.1 The v1/v2 sequencing argument (assigned: argue it, don't just assert it)

Outcome 1 (filter/demote) is the operator's original ask-shaped outcome; outcome 2
(narrative scout) ships first. The order is forced, not preferred:

1. **D-067 (accuracy, not volume) cuts against an uncalibrated filter.** A filter built
   today would kill cards on a predictor whose per-class precision is *unknown* — the
   marquee class (`fit_outlook`) inherits a window signal that labels ~65% of teams
   rebuilders (A-4). Filtering on that is removing volume with unmeasured accuracy: the
   exact anti-pattern D-067 names. The stamp window measures the predictor before it is
   allowed to delete anything.
2. **Interleave discipline makes a v1 filter unmeasurable or dishonest.** The bake-off is
   live; `bypass_rerankers` is the standing rule. A post-generation filter either corrupts
   the arm comparison (filters interleaved decks) or is bypassed on exactly the decks being
   measured (ships unmeasured). Both are worse than not shipping it.
3. **The §6.4 counterfactual is the earn-in, and it is free.** Stamps alone answer "would
   the cards the breaker wanted to kill have underperformed?" — no serving change, no risk.
   The filter ships if and only if that readout says the kills are good kills.

**What evidence unlocks v2 (proposed, register item 18):** M6 pooled cut at n ≥ 200 decided
stamped cards per cohort showing the would-kill cohort's like-on-viewed materially below the
keep cohort (proposed bar: ≤½ the keep cohort's rate, CI-separated), AND M2 per-class
precision above both baselines for every class whose severity contributes to the kill bar,
AND the per-arm cut directionally consistent (no arm where kills outperform keeps).

**Seam recommendation TODAY, if the counterfactual supports killing: option (a) — per-arm,
in-generation, pre-draft screening.** Reasoning against the alternatives: (b)
serving-layer demote bypassed on interleaved decks means the bake-off never measures the
filter — a permanent measurement hole in the layer we just spent a plan instrumenting; (c)
stamp-only user-side sort/badge doesn't remove bad cards, it outsources the filter to the
user and leaves deck composition untouched (the complaint is *which trades exist*). Option
(a) keeps the interleaver byte-untouched (each arm's list is screened before the draft, so
the bake-off measures screened arms — a fair fight), attributes the filter's effect per arm,
and honors D-067's family-suppression ruling by screening per card, never per player-space.
Its cost — touching every generator — is bounded by making the screen ONE shared
predicate call (`trade_breaker.would_kill(card, pctx, cfg)`) applied identically in each
arm, behind per-arm flags. That is v2's scope block to write; v1 pre-commits nothing beyond
this recommendation.

## 7. Dependencies & Risks

| # | Dependency / risk | Disposition |
|---|---|---|
| D-1 | `fix/package-benchmark-sweetener` Monday merge — moves `value_giving` semantics; invisible to the M1 rail | P1 starts at/after it; deploy timestamp recorded in the readout spec (FR-6.2); golden re-capture sequencing per PLAN A-1(c) |
| D-2 | Taxonomy v1.1.0 PR (`roster_crunch` + producer column) — three-way signed; the shared file does not exist in this worktree yet (Receipts seeds it) | P0 deliverable; R-12 if it pends while negmem records |
| D-3 | Live bake-off window vs narration first light | Register item 9 default: dark until the serving round's verdict |
| D-4 | A-4 (legacy-outlook skew) and A-5 (mirrored-serve rate) re-derived at build | haircut and M3-kill numbers re-checked before P2 |
| D-5 | Sibling change-control calendar (three plans, one tester-week budget) | §6 phasing note; flips via `set_knob` only |
| D-6 | Mobile release train — element must be in the installed build before P3 | FR-5.4, checklist step 0 |
| R-a | **Metric backslide at readout time** — the pressure to cite M3 (n≈0) or claim M4 significance will be real when the honest cells print "insufficient" | This PRD's §4 verdicts are binding; changing a KILLED metric's status requires an operator decision logged in the register, not a readout footnote |
| R-b | **Register-as-backlog creep** — 18 register items, operator authorized build; risk is items silently becoming build blockers or, worse, silently becoming built | Register header states: defaults ship; items are post-build tuning. Anything requiring code beyond the defaults (e.g. item 15's demo narration, item 17's positive-signal variant) is v1.1+ with its own scope |
| R-c | HLD/LLD risk register R-1..R-13 | carried as-is; the PRD adds no new mitigation surface beyond §5.3's state definitions |

## 8. Rollout & Measurement

### 8.1 Launch sequence (trace: HLD §5.1)

(1) dry-run ms → (2) `trade.breaker` on (dark) → (3) M1 gate → (4) M2 readout → (5) operator
graduates ≥1 class via `set_knob` → (6) `trade.breaker_narrative` on, operator-only → (7)
TestFlight checklist → (8) general lighting. Rollback ladder (deploy-free, rehearsed at
step 7): narrative flag off → `breaker_min_severity` 1.1 / per-class switch 0 → `trade.breaker`
off → revert commit.

### 8.2 Exposure & readout predicates

Exposure := `narrated != null` AND platform = mobile. Narration readout is three-cell:
narrated / suppressed (reason-enumerated) / no-objection. All joins served-cards-only,
`is_ghost = 0`, `ver`-filtered.

### 8.3 Manual TestFlight checklist (run at P3, operator-only exposure; log verbatim in TEST_LEDGER)

Preconditions — step 0: installed build contains the hesitation element (build number
recorded); operator device on the narration allowlist; `trade.breaker` ON ≥1 week (P1
passed); exactly one class graduated (assume `fit_outlook` below; substitute the actual
class); backend reachable for the two payload checks (`curl` against the operator's session,
or the web debug console — the payload checks are OPTIONAL if infeasible, because pytest
guards pin the same fact; the UI checks are NOT optional).

| # | Step | Expected result |
|---|---|---|
| 1 | **Dark-window check** (before flipping `trade.breaker_narrative`): generate a fresh deck; swipe through every card | NO hesitation element on any card (`trade-card.breaker-hesitation` absent everywhere); cards byte-identical in layout to the previous build |
| 2 | Dark-window payload check (optional): fetch the deck payload; search for `"breaker"` | Key absent from every card object — the dark window serves nothing (FR-2.3) |
| 3 | Dark-window regression: like one card, pass one card with a layer-2 decline reason | Both flows unchanged; DeclineReasonPanel files normally |
| 4 | **Graduation step**: operator flips `trade.breaker_narrative` ON (hot reload; logged), confirms `breaker_narrate_fit_outlook = 1` via `set_knob` log; regenerate the deck | ≥1 card shows the hesitation element: flare dot + one sentence beginning "Their likely hesitation:", matching a `fit_outlook` template; styling matches Chalkline (no new colors, no emoji, radius ≤ 8) |
| 5 | Class restriction: inspect every narrated card's sentence on the deck | Every sentence is from the graduated class's template family only — no `value_giving`/duplicate/weakness/crunch sentence appears; NO sentence ever mentions untouchables, "their board", or their rankings (dark classes structurally excluded) |
| 6 | **Suppression state**: find (or induce, by re-rolling decks) a deck with 3+ cards against the same partner where the same hesitation would apply | At most the top card for that (partner, objection) narrates; the other cards show NO element and no blank-space artifact; nothing in the UI references the hidden repeats |
| 7 | No-objection card: find a card with no narrated sentence | Element entirely absent (not empty, not placeholder) — absence is silence, per FR-3.1 |
| 8 | **Null-evidence template**: find a card sending picks/future capital to a win-now partner | Sentence reads "…they look win-now, and this asks them to take back future capital." — no player name, no age, no position interpolated (the null-evidence branch renders its evidence-free template, never "None") |
| 9 | Layout: view a narrated card with the longest player name available; rotate through a card that also shows fitLine + consensus note + strength bar | Sentence wraps ≤2 lines, no truncation/ellipsis, no clipping of TradeValueBar or the disposition row; element sits between the partner-fit line and the consensus note |
| 10 | Mid-session flip: with a narrated deck open, operator flips `trade.breaker_narrative` OFF (hot reload); do not regenerate; then regenerate | Open deck's already-rendered sentence persists (payload already held — FR-3.4); the regenerated deck shows no element anywhere |
| 11 | **Rollback rehearsal, rung 1** (already exercised by step 10's flip): confirm from step 10 that the narrative flag alone removes the surface on the next deck, with `trade.breaker` still ON | User-visible surface gone deck-over-deck; stamps continue (backend diagnostics still count stamped cards) |
| 12 | **Rollback rehearsal, rung 2**: flip `trade.breaker_narrative` back ON; set `breaker_min_severity = 1.1` via `set_knob`; regenerate | No sentence on any card while both flags are ON — the knob alone silences the line (HLD §5.3 rung 2); restore `breaker_min_severity` to its prior value and confirm sentences return |
| 13 | Decline-reason interplay: pass a NARRATED card and file a reason | Panel works normally; the filed reason lands (this is the calibration join's right-hand side — verify a row exists if DB access is handy) |
| 14 | Record: build number, flag/knob states per step, screenshots of steps 4, 6, 8, 9 | TEST_LEDGER entry naming every step's pass/fail |

Steps 1–3 constitute the dark-window sub-checklist and MAY be run earlier, at P1, on the
first build containing the element.

## 9. Consolidated operator decision register

Items 1–7b (PLAN §9) and 8–14 (HLD §6.3) restated one-line with status; 15–18 are new in
this PRD. **Header rule (R-b):** the operator authorized building after PRD convergence —
every item ships its default; register answers re-tune knobs/copy/readouts post-build.
Items whose non-default answer requires new code are marked [v1.1+].

| # | Decision | Default shipping | Status |
|---|---|---|---|
| 1 | v1 = stamp + narrative only; filter/demote deferred | yes | settled (PLAN) |
| 2 | Deterministic templates; LLM is a separate explicit decision | deterministic | settled (operator constraint) |
| 3 | Hesitation surface = distinct card element (nothing renders `narrative` today) | distinct element | settled (F-1 verified) |
| 4 | `breaker_min_severity` initial bar | 0.60 shipped; re-leveled from calibration readout | open, post-build |
| 5 | Viewer-seat shadow run (compute ~2×/card, primary calibration population) | on (`breaker_shadow_run=1`) | default stands |
| 6 | v2 seam election | none until §6.4 readout | open (see item 18) |
| 7a | `roster_crunch` into shared taxonomy, `producer=breaker` | sibling-agreed | pending operator yes |
| 7b | `shape_aversion` as `producer=negmem`; producer column added | sibling-agreed | pending operator yes |
| 8 | Private state stamps dark, never renders; generic form ("unlikely to move him") also does not render | dark-only, no generic form | default stands |
| 9 | Narrative-flip timing vs live bake-off window | DARK until the serving round's verdict; mid-window lighting requires operator accepting an annotated readout | open, operator calendar call |
| 10 | Per-deck repetition suppression (same card, different decks, different narration) | yes, `suppressed` stamped | default stands (FR-3.2 states the UX) |
| 11 | Inferred-window `fit_outlook` narration: wait for composite vs high-margin bar | high-margin bar (`breaker_outlook_narrate_margin`); declared raises confidence only on agreement | default stands |
| 12 | `breaker_stamp_scope` full-candidate-pool stamping | served-deck only | v2 study option [v1.1+] |
| 13 | Organic them-score via promoting fit stamp to organic decks | `them` null on organic | registered for fit-challenger, not this plan |
| 14 | Declared-outlook disclosure in narration | never in v1 | default stands |
| **15** | **Demo-deck narration** (T-1 lift option) | **skip ships; this PRD recommends keeping it** (FR-3.6 weighing: synthetic-partner trust cost + zero calibration value + Q-1 input-shape mismatch vs a first-run demo moment narration can't reach in its dark-window timeline) | recommendation: keep skip; revisit after first class graduates [v1.1+] |
| **16** | **Calibration TBD cells** (LLD §8): this PRD proposes min n = 50 per class (primary stratum consensus × legacy), margin ≥ +10 points over BOTH baselines, per class; `roster_crunch` and `other_player_keep` rows reported-never-gated in v1 (M2 verdicts, §4.1) | proposed numbers above | operator confirms before `trade.breaker` lights (FR-6.1) |
| **17** | **Positive-signal variant** ("no objection found" affirmative copy) — FR-3.1 bans it in v1 as an over-claim | absent | explicit product decision if ever wanted [v1.1+] |
| **18** | **v2 evidence bar + seam pre-registration**: this PRD proposes the §6.1 unlock evidence (M6 pooled n ≥ 200/cohort, kill cohort ≤ ½ keep-cohort like rate, M2 precision passed for contributing classes) and recommends seam (a) per-arm in-generation screening | none built | operator ratifies bar + seam preference now or at the M6 readout |

---

*Draft B ends. Files this draft binds to at merge: PLAN.md · HLD.md · LLD.md ·
scope.md §3–§5 (evidence + docs + ship gates) · LLD §8 (readout spec cells → register
item 16).*
