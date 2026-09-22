# Adversarial review and resolution record

Status: **aligned after three review rounds**, September 21, 2026 (America/New_York). The owner requested an **Astra Ultra** adversarial agent, with iterative parent responses and plan revisions until both reviewers align against the original scorecard request. This record is not model validation or a production release.

## Participants and boundaries

- Parent: plan author, independent goal-to-plan check, resolution/edit owner.
- Reviewer: `/root/scorecard_adversary`, explicitly spawned with `gpt-6-astra`, `ultra` reasoning.
- Reviewer received the original user request verbatim, trade-engine context and instructions to read all six original documents in full. Review is read-only; parent owns changes.
- Scope: whether the plan meets the requested goals and is implementable without misleading grades. No code, runtime configuration, production data or deployment changes.
- Agreement must be explicit after rereading revised text. An unresolved material issue is not closed merely by relabeling it an implementation detail.

## Original requirement checklist

| Owner requirement | Primary coverage | Adversarial acceptance question |
|---|---|---|
| All production/current/future models and arms; prioritize new model | plan §§2–3, 6 | Are active, excluded, historical and upstream model components distinguished without fictitious live results? |
| One pre-release and post-release evaluation framework | plan §§4–7; ways-of-working §§2–5 | Are identities, metric meanings, labels and release standards comparable across lifecycle stages? |
| Modeling team understands how it is graded | scorecard-spec; ways-of-working §§2–4 | Can two implementers/reviewers apply the same rubric and know what blocks promotion? |
| Define documents, best practices and antipatterns | ways-of-working §§2, 7 | Do documents have owners/required contents and a practical build order, rather than paperwork without tests? |
| Model versus presentation/eval engine segmentation | plan §3 and §5 | Can failures be attributed to construction, runtime filters, delivery or the independent evaluator? |
| Fairness: both parties willing to execute | scorecard-spec §2 | Are proxy scores, observations, response selection and true joint probabilities kept distinct? |
| Outlook, needs and personal ranks | scorecard-spec §§3–5 | Are each manager's intent, starter opportunity cost and personal gaps evaluated, including missing data and selected/inferred disagreement? |
| Meaningful packages and stud tax | scorecard-spec §§6–7 | Can filler, one-sided headliners or double-counted premiums game the assessment? |
| Each give and receive side evaluated independently | scorecard-spec §1 and all dimensions | Do all four directional assessments remain visible without requiring every surrendered asset to be undesirable? |
| Additional details necessary to accomplish the goal | plan and playbook safeguards | Do temporal attribution, exposure, coverage, uncertainty, testing and operating gates prevent false conclusions without blocking all useful iteration? |

## Original document identities

SHA-256 before this review's plan edits:

- `plan.md`: `b5aaa1f2640b322e3c51b52dfd71b9174d71a10ee6303b738e47c23f17b72024`
- `scorecard-spec.md`: `30f129a12d64b53e7be0e254004d83ba42ee8af02d87a4e3950e4cfe158f00ae`
- `ways-of-working.md`: `9aeb40ad71353d5be7fb687637c1387c46767c775b064ac49496e8d4ba3d9d2c`

## Round 1 — not yet aligned

The reviewer found the core scope strong: all six dimensions, four directional assessments, model/policy separation, source limits and pre/post-release workflows were present. It rejected sign-off because the following measurement and operating gaps could still reward the wrong model.

| Finding | Parent response and revision | Verification location |
|---|---|---|
| High: primary denominator allowed initiated episodes, which the arm itself controls | Accepted. Primary yield now uses a fixed pre-assignment eligible manager-league population; no-request members and failed/empty searches remain. Episode conversion and request yield are diagnostics, not interchangeable primary choices | scorecard §2.2; playbook §4 |
| High: effective likes at cutoff could erase a historical valid match or join nonoverlapping interests | Accepted. Added actor-specific active intervals, immutable valid-overlap milestone, separate later attrition, and distinct lifecycle/maturity/observation fields | plan §4.3; scorecard §2.1 |
| High: responder-only labels could be used to claim exposed-population willingness calibration | Accepted with the owner's semantics preserved: like/queue/send expresses willingness to execute, but observed expressions do not identify every silent manager's willingness or prove execution. Literal target/population/horizon now required | scorecard §2.3 |
| Medium: empirical thresholds required at a stage before their baseline existed | Accepted. Bootstrap now separates charter/invariants, evidence audit, minimal incumbent baseline, and threshold freeze before challenger tuning/holdout access | plan work packages 0–2b; playbook §§2–4 |
| Medium: shared-arm and later-surface outcome credit lacked a decision rule | Accepted. One frozen origin, distinct construction/delivery/assignment provenance, one product count, shared/unknown cohorts and separate carry-in. Later deployment/injection does not steal credit | scorecard §2.2; plan §4.3 |
| Clarification: missingness could block all learning or become a new veto on user authority | Added an explicit decision table: affected claims remain Unknown; scoped learning can proceed with coverage disclosure; evaluation does not change live selection policy | scorecard §1.1 |
| Clarification: bounded search cannot prove no feasible package exists | Limited recall/feasibility claims to the audited universe/budget, with exhaustive-oracle exception | plan §5; scorecard §3 |
| Clarification: generic 0–4 labels were insufficient calibration guidance | Added six dimension-specific 0/2/4 anchors and complete four-side worked cases, including missing evidence and one-manager harm | scorecard §§1.2, 9 |

The reviewer challenged the proposed fixes before editing. Its additional cautions were incorporated: freeze eligibility before assignment, isolate carry-in/pre-generated inventory, retain origin through arm changes, define genuine post-expiry episodes without resetting old clocks, and keep optional intent-elicitation research out of the critical path. It agreed the proposed approach addressed the findings but explicitly withheld alignment pending the exact-text reread.

## Adversarial acceptance fixtures to implement

These are specifications, not claims tests have been coded or run:

| Attack | Required result |
|---|---|
| Each arm has 100 fixed eligible manager-league windows; X makes 1 episode/1 mutual concept, Y makes 10/2 | Y primary yield =2/100 versus X =1/100. X's 100% versus Y's 20% episode conversion does not reverse the primary conclusion; quality/repetition guardrails still apply |
| A likes day 1, B day 3, A withdraws day 5; terms valid through day 3 | Historical mutual =1, later withdrawal =1, currently actionable mutual interest =0 |
| A likes day 1, withdraws day 2; B first likes day 3 | Historical mutual =0; two separate likes cannot create overlap |
| Start day 0, counterpart sees day 13, redisplay day 14 | Original deadline is unchanged; no additional 14-day horizon |
| 10 exposed managers like and 90 remain silent through complete follow-up | Responder-like share =100%; observed like conversion =10%; general exposed willingness remains unidentified |
| Identical package independently generated by X/Y, then delivered via likes-you | One product outcome, preserved overlapping construction provenance; no third constructor win from injection |
| Episode originates before assignment or converts after deployment/arm switch | Carry-in cohort or frozen originating cohort retains attribution; new arm does not inherit historical construction credit |
| Early invalidation or an outage affects a hard cohort | Original denominator remains; invalidation and incomplete observation are distinguished; no silent removal to improve yield |
| B has no personal rankings or usable projections | B personalization/projected-needs claims are Unknown; consensus/proxy evidence is labeled; no fake pass and no automatic ban on scoped learning |
| Tanker has no pick return within a bounded run | “None found within audited search/budget,” not proof no possible acceptable pick trade exists |
| A user selects a costly trade; independent assessment finds a serious B starter hole | Honest B give/package needs failure, explicit-selection context retained; scorecard does not itself create a new UI prohibition |
| X produces 3 mutual concepts, all later withdrawn/rejected; Y produces 2, neither reversed and one completed | Historical primary remains 3 versus 2, but X cannot claim better willingness or automatically win promotion. Apply predeclared reversal/confirmation guardrails and follow-up coverage; show retained-concept yield and support-qualified completion separately |

## Round 2 — original findings resolved; one additional guardrail required

After a full reread, the reviewer explicitly confirmed the five original findings and three clarifications were resolved. It endorsed the worked four-side sacrifice/unknown/harm fixtures, but identified a residual promotion risk: post-match attrition was a diagnostic rather than an explicit release guardrail. More initial mutual likes followed by widespread withdrawals could still look like a winning model.

The parent accepted this finding. Scorecard §2.2 and playbook §4 now require preregistered attrition/confirmation limits, a separate follow-up horizon, remaining-validity/coverage reporting, and non-reversed concept yield against the original fixed cohort. Higher historical interest alone cannot justify improved-willingness claims or broad promotion when reversals breach limits or essential follow-up is immature/unreliable. Provider completion remains a stronger, coverage-qualified secondary outcome, not a universal impossible gate. Build package 5 explicitly includes this review.

## Round 3 — final wording review

Reviewer verdict after the exact-text reread:

> ALIGNED with the original request. The third-round wording resolves the remaining promotion risk; no material plan blockers remain.

The reviewer confirmed current/future model coverage, all six dimensions independently across both managers' give/receive/package assessments, construction/presentation/independent-evaluation separation, pre/post-release operating documents, scoring anchors/examples and safeguards against misleading gains. It explicitly found the final mature attrition/confirmation guardrails sufficient and the worked examples consistent with reasonable sacrifice versus counterparty harm.

**Parent verdict: aligned.** I independently checked the original requirement matrix, accepted and corrected the substantive findings, and agree that the resulting plan meets the owner's stated goals without treating implementation choices as evidence of model success.

Exact SHA-256 identities independently reported by both parent and reviewer:

- `plan.md`: `610d0ca75b02260e24a020d8033ec799d8b2f665109730bf986d32af5518dd9d`
- `scorecard-spec.md`: `408874252fd94392777a4d1400dfa0cda8a2b5e9313e008c6597391489a80781`
- `ways-of-working.md`: `1282d31e6b7aef75a84525b4305848e12c22b3bd573c06cf05e8004c07ff1546`

## Remaining implementation work, not unresolved plan findings

Implement the evidence/schema audit, executable evaluator and adversarial fixtures, empirical incumbent baseline, calibrated annotations, baseline-derived threshold/power ratification, reporting and approved experiments in the documented order. Physical schemas and numerical promotion limits are deliberately not invented before evidence exists. No tests in the fixture table have been represented as executed software tests; no model has earned a performance grade from this review.

Documentation checks: local links/anchors, Markdown fences/tables, status JSON and whitespace validated; project indexes and session-memory checks recorded in the test ledger. No app code, production data/configuration, deployment or TestFlight release changed.
