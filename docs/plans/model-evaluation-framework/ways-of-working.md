# Ways of working: model development and production evaluation

Proposed operating framework. Applies to heuristic constructors, trained models, market-reference blends, parameter-only revisions, arms, and runtime presentation-policy changes. A new algorithm is not required to trigger evaluation.

## 1. Ownership and independence

| Role | Accountable for | Cannot approve alone |
|---|---|---|
| Product/model owner | Product priorities, explicit exceptions, meaningful-effect thresholds, final promotion trade-offs | Statistical validity or correctness of their own labels |
| Modeling lead | Hypothesis, implementation, model card, experiments/ablations, failure analysis | Final evaluation of their own candidate |
| Evaluation lead | Metric registry, independent evaluator, locked benchmarks, reproducibility and scorecard | Unilateral changes to user preference/meaningfulness contracts |
| Data/analytics lead | As-of datasets, lineage, privacy, attribution, missingness, outcome reducer, statistical analysis | Treating unknown outcomes as labels to improve sample size |
| Backend/mobile leads | Correct input capture, serving policy, instrumentation, reliability and deployment | Claiming model acceptance improvement from passing code tests |
| Domain reviewers | Independent A/B ratings, explanations and adjudication | Assuming the other manager's unobserved willingness |
| Release owner | Exact release identity, CI, canary, rollback and effective-state verification | Broad promotion despite unresolved critical evidence failures |

People may hold multiple roles in a small team, but the model's author must have another reviewer for evaluation and release sign-off. The product owner need not personally label every trade; their interview becomes a testable contract and calibration set for additional reviewers.

Evaluate the team's work on evidence quality, reproducibility, sound experiments and production learning—not on always reporting a winning model. A well-documented negative experiment is useful. Test-set fishing and unsupported positive claims are not.

## 2. Documents to establish

These are required **document types** with templates to create in implementation; the plan does not claim those templates or a live dashboard already exist. Keep one canonical metric definition, referenced by all model-specific artifacts.

| Document / proposed eventual home | When / owner | Required content |
|---|---|---|
| Evaluation charter, `docs/model-evaluation/charter.md` | Once, versioned; product + evaluation | North-star, six dimensions, both-manager contract, priority/exception hierarchy, scope, evidence levels, non-goals |
| Metric registry, `docs/model-evaluation/metrics.md` plus machine-readable definitions | Before experiments; evaluation + analytics | IDs, formulas, units, direction, numerator/denominator, applicability, maturity, source joins, missingness, normalization, critical slices, thresholds and rationale |
| Rubric/threshold ratification record, `docs/model-evaluation/ratification/<version>.md` | After minimum incumbent baseline, before challenger tuning; product + independent evaluation/analytics | Baseline manifest, adjudicated anchors/fixtures, empirical base rates, margins/coverage/MDE rationale, unresolved evidence, approved exception scope, sign-off and effective version |
| Component/arm registry, `docs/model-evaluation/registry.md` | Before baseline and each revision; backend/modeling | Model versus gate versus delivery, exact versions/config/code/artifact hashes, environment, surface coverage, active/shadow/retired state, owner and effective interval |
| Evidence and label contract, `docs/model-evaluation/evidence-contract.md` | Before telemetry/query changes; data/backend | Entity/episode identity, side orientation, fixed origin/assignment/cohort, overlapping-interest milestone versus current state, maturity/observation rules, duplicate/shared/carry-in attribution, mutation/undo/expiry rules, propensity semantics, retention/privacy/deletion, schema mapping |
| Benchmark/data card, `benchmarks/<version>/data-card.md` with private manifest location | Before training/tuning; data/evaluation | Population, dynasty filters, time range, source rights, missingness, sampling, dedup, overlap, as-of evidence, train/tune/test groups, frozen hashes and allowed uses |
| Model development brief, `models/<model>/<version>/development.md` | Before coding/tuning; modeling | Problem and falsifiable hypothesis; expected effect by each manager/dimension; baselines; features; alternatives; test/power plan; compute limits; failure risks; predeclared gates |
| Experiment log, `models/<model>/<version>/experiments.md` | During development; modeling | All variants/parameters/seeds/data/evaluator versions, ablations, successes and failures, hidden-test access count, rationale for selection |
| Model card, `models/<model>/<version>/model-card.md` | Before release; modeling + independent reviewer | Intended use, constructor and utility details, input/provenance needs, side-specific results, benchmark/date, limits, no-probability disclaimer if applicable, drift risks and ownership |
| Presentation-policy card, `policies/<version>/policy-card.md` | Before any rule/reranking change; backend/product | Each rule and enforcement mode, rationale, exceptions, severity, input dependencies, full interaction matrix, independently measured precision/recall/yield and rollback |
| Pre-release evaluation/release decision, `releases/<id>/pre-release.md` | Before rollout; independent evaluation + release owner | Reproduction manifest, six-dimensional A/B/raw/post-policy results, critical segments, blind examples, CI, paired comparison, uncertainty, threshold outcomes, dissent/waivers, exact version and rollback |
| Online experiment specification, `experiments/<id>/design.md` | Before first assignment; analytics/product | Assignment unit/spillover, fixed pre-assignment eligible manager-league population and lookback, primary yield and attribution rule, exposure definition, carry-in/dedup/new-episode rules, origin and follow-up windows, control/challenger versions, power/MDE, stopping/multiplicity plan, canary and rollback criteria |
| Production scorecard, `reports/<window>/<model-policy>.md` or generated equivalent | Daily health / weekly mature quality; analytics/evaluation | Same metric IDs as pre-release, stage and outcome funnel, both-party grades, confidence/coverage, segment/benchmark deltas, latency/repetition, anomalies and action owner |
| Incident / error-analysis and decision log | On regressions and monthly review; component owner | Evidence-linked failure taxonomy, root cause by layer, counterexample, fix, added regression, recovery, graduation/rollback/retraining decision and follow-up |

These paths are proposed homes, not existing files. After ratification, promote stable contracts into `docs/model-evaluation/` and link them from architecture/API/schema/config/analytics references as appropriate; do not maintain divergent copies in every initiative. Private snapshots/identifiers stay in authorized storage, not committed Markdown. Generated reports can refer to hashes/access-controlled evidence.

### Model-card minimum form

Identity and owner; hypothesis/intended surfaces; exact model/arm/config/artifact; features and provenance; training or heuristic calibration procedure; dataset/split versions; independent six-dimension results for both managers; stage-specific impact; critical low-performing segments; probability-calibration status; runtime/coverage frontier; known exceptions/missing-data fallback; release status; monitoring and rollback owner.

### Scorecard/report minimum form

Version tuple and as-of window; cohort selection and sample sizes; maturity and data-quality verdict; construction/policy/exposed sections; six-row A-give/A-receive/A-package/B-give/B-receive/B-package matrix; worst-side and both-pass rates; numerator/denominator/CI; unknown/N/A; baseline deltas; outcome funnel; slice outliers; example IDs; latency/search/diversity/cost; interpretation and decision. Never replace results with prose saying “looks better.”

## 3. Pre-release: model development lifecycle

These gates apply to a candidate model **after** the one-time framework bootstrap: draft invariants/anchors -> evidence audit -> minimum incumbent-only baseline -> signed threshold/rubric freeze ([build packages 0–2b](plan.md#6-build-sequence-and-acceptance-criteria)). Measuring the incumbent does not require thresholds learned from that measurement. Empirical promotion margins do. Do not start challenger tuning or consult the locked test before that freeze; unresolved acceptance evidence permits only an explicitly scoped learning experiment, not a retrospective declaration that the incumbent or challenger passed.

### Gate 0 — Frame and preregister

Write the development brief before tuning. Specify the problem in both-manager terms and name which dimensions should change. Example: better tanking first-round-pick/young-WR returns without increasing the contender's starter damage or market overpay. State whether the change is construction, pricing, outlook/needs inference, runtime gating, composition or delivery.

Freeze metric/rubric versions, benchmark split, baseline, noninferiority margins, practical effect size and analysis plan. Define thresholds using historical base rates and product impact before seeing challenger holdout results. Distinguish a hypothesis about inputs from a promise about real-world acceptance.

### Gate 1 — Validate data and label semantics

Complete the data card and verify ownership, league format, timestamp consistency, as-of ranks/values, pick identity, input freshness and strict dynasty corpus inclusion. Quarantine unsupported leagues or incomplete events rather than guess; disclose excluded/unknown counts without removing them from already-frozen experiment populations. Assign label evidence tiers: verified exact provider completion; valid historical mutual-interest milestone; one-party expressed willingness; blinded expert judgment; reference-price plausibility; model proxy. They are not interchangeable training labels. Later withdrawal affects a separate current-status/attrition measure, not the truth of a prior valid milestone.

Test the outcome reducer against duplicate taps, pass-reason plus swipe double emission, undo followed by another action, amended packages, source-like links, delayed exposure, declined/archived match, provider send failure, expiry and model change between the two occurrences. Preserve original actions and derive states; do not overwrite history to simplify queries.

### Gate 2 — Develop against known tests, not the locked holdout

Keep a simple baseline and record all experiments. Reuse current code and data plumbing. Run component tests, both-party synthetic scenarios, model-versus-policy comparisons, input ablations and market-reference sensitivities. Inspect rejected and empty searches, not only cherry-picked top cards.

For learned models, also document feature availability at prediction time, fitting/tuning/calibration splits, objective, hyperparameters, convergence, training reproducibility and training/serving skew. For hand-coded models, document coefficients, thresholds, rationale and sensitivity. Both types need model cards and real outcome validation.

Do not reuse a rank update generated by a trade decision as an input for predicting that same decision. Freeze pre-decision boards and label the feedback policy/version. Respect personal tier boundaries when learning from interactions.

### Gate 3 — Independent offline qualification

The evaluation owner runs a locked version on withheld contexts and outcome labels. The modeling team can see the rubric and development failures, not continuously query the final holdout to optimize it. A failed final test returns to development; further attempts are logged and require a fresh or explicitly spent holdout strategy.

Compare against the incumbent with paired requests and cluster-aware uncertainty, at raw-construction, shared-policy and final-presentment stages. Pre-release human assessments inspect both managers' contexts without model/arm branding. Counterparty profiles/tiers are visible only to authorized internal reviewers, not exposed publicly or to unrelated league managers.

Use separate reviewers for A and B where practical; double-label a stratified calibration sample and difficult exceptions. Measure ordinal agreement and binary acceptability disagreement; adjudicate inconsistencies into the rubric, retain disagreement rather than pretending certainty. Automated/LLM judges may assist triage only after validation against adjudicated human cases; never make them the sole release authority or let model-written explanations anchor their ratings.

### Gate 4 — Reproducibility and serving qualification

Require exact-head repository CI plus evaluator tests; reproduce the same result from its manifest; validate source/config routing, data capture, model artifact loading, invalidation and fallback. Verify offer identity and grade invariance for performance-only changes. Confirm no new budget/output truncation hidden in an optimization.

For a policy change, require removal-reason accounting, good-offer false-reject measurement and false-accept measurement on a common corpus. For a model change, hold downstream policy fixed initially. If both change, complete the factorial comparison before claiming a causal source of improvement.

### Gate 5 — Controlled rollout approval

Pre-release document must carry one of: **qualified for limited experiment**, **qualified for promotion**, **failed**, or **insufficient evidence**. Offline/expert/market-proxy success without real mutual evidence normally qualifies only for a monitored experiment, not a claim of improved acceptance.

Do not deploy an untested arm simply to fill its scorecard. Start offline, then separately authorized shadow where useful, then a canary limited by exposure/risk rather than an artificial offer-count limit. Retained disabled arms stay disabled unless specifically approved. Model routing and presentation policies receive independent versioned controls through the existing configuration workflow, not ad-hoc flags added by analysts.

## 4. Release gates and how the team is graded

### Nonnegotiable correctness gates

- No known critical ownership/identity, wrong-league/format, expired-asset, private-rank disclosure or action-attribution defect. Tests must include both orientations and zero-tolerance fixtures.
- Every new scored occurrence has valid model/policy identity and an asset-bound immutable snapshot, or is explicitly quarantined/marked unknown; no forged backfill.
- Personal selected tiers are not crossed by bounded interaction adjustments; explicit outlook authority and selection direction are honored under the declared contract.
- Required evidence is committed before actionable publication; undo, delayed counterparties and failed/superseded jobs remain truthful.
- Exact-head CI, independent review, data access controls and a verified rollback path.

The presence of the most valuable asset does not waive these gates. A valid manual/explicit-selection exception must be documented and shown in its own cohort; it is not a generic bypass.

### Quality promotion gates

Use paired baseline changes and predetermined critical-segment thresholds across the six dimensions. No unexplained material regression in either manager's acceptance, preference fulfillment or relevant outlook/needs; no quality gain achieved only by blocking useful opportunities or amplifying repetition. A deliberate trade-off requires product/evaluation sign-off recorded **before** broad promotion, not a retroactive change to the score.

Provisional ordinal “acceptable” is 2/4, but population pass-rate targets, noninferiority margins and unknown-coverage limits are set in **work package 2b**, after the minimum incumbent baseline and before challenger tuning/locked-test access. Record source data and sign-off in the ratification record. Do not invent a universal 80/100 or choose sample size after looking at significance. Statistical nonsignificance is not proof of no harm; insufficient precision means evidence-limited. Follow the scorecard's missingness/authority table: an unknown counterparty board limits personalization claims, not all experimentation, and a poor grade is not itself a new production veto on user-selected exploration.

For experiments, preregister the primary promotion outcome as **distinct valid mutual-interest concepts per fixed eligible manager-league observation window**, using the scorecard's frozen eligibility/origin/attribution contract. Do not substitute arm-generated episode counts or post-treatment active-user counts as the primary denominator. Include no-request members and failed/empty searches; co-report request yield, episode conversion, exposure and request frequency. Track confirmed completions as a stronger, often slower secondary outcome, with support/observation coverage. Report effect size and cluster-aware uncertainty; control multiple comparisons and repeated peeking using a declared schedule or valid sequential method. Define MDE/power at the actual assignment unit using observed event rates; 100 reviewed cards are not automatically enough for promotion. Shared/carry-in/unknown attribution and incomplete telemetry must remain visible; strong proxy grades cannot erase these limits.

Post-milestone withdrawal, explicit match rejection/cancellation and supported match confirmation are **promotion guardrails, not merely diagnostic charts**. Freeze their tolerated deterioration, follow-up horizon, observation coverage and remaining-validity treatment before assignment. Co-report non-reversed historical concepts per original eligible cohort. A higher initial mutual-interest yield does not justify broad promotion or a claim of improved willingness to execute if reversals breach limits or essential follow-up is immature/unreliable. Mark failed or evidence-limited and require approval for any continued limited learning. Do not erase valid historical milestones to solve this; preserve the event and grade the subsequent outcome separately. Provider-confirmed completion remains a stronger secondary measure with explicit support limits, not a requirement that every platform must expose completion before any scoped model can graduate.

Latency target is proposed p95 <=3 seconds from tap to first actionable tile, with request failure rate and coverage. Existing production is not retroactively declared compliant. A quality-only canary before that service objective is met needs an explicit performance-exception record and no unacceptable regression against the incumbent. A “latency fix” is not successful because its unit tests pass; it needs actual boundary measurements. No quality gate is waived silently to meet speed.

## 5. Post-release: model evaluation lifecycle

### At deployment

Capture exact code/model/config/policy/client versions, experiment assignment settings, deployment timestamp and rollback target. Read back actual live state. Separate generation configuration from later exposure configuration. Verify one safe trace through each changed surface and the telemetry contract, without production seeding or fabricated users.

### Early health window

Check error/timeout/empty rates, first-action latency, generated/committed/viewed counts, input staleness, unexpected arm attribution, budget exhaustion, illegal assets, retention, snapshot parse rates and action joins. Inspect controlled canary examples with both managers' evidence. Do not claim acceptance uplift from a few early likes or an unmatured denominator.

### Weekly mature scorecard

Use the same metric IDs/rubric as pre-release. Publish the label cutoff, maturity window and which cohorts have not matured. Compare observed outcomes against preregistered expectations and predicted calibration, retaining both platform-wide and important segment results. Join or mark unknown for actual completions rather than upgrading provider sends into successful trades.

Investigate whether a change in the aggregate came from the model, input mix, gate acceptance rate, display rank, counterparty exposure, response lag, app build or season/news. Report exceptions, orphan evidence and inter-arm/package overlap. Review a reproducible error sample each week and a rotating sample of high-scoring offers to catch evaluator gaming.

### Monthly error review and maintenance

Maintain a failure taxonomy: bad target, wrong sell, wrong outlook, starter hole, excessive cost, insufficient stud compensation, trivial package, repetitive deck, bad source data, stale state, invalid pick, unwanted filter exclusion, misleading explanation, or missing exposure. Assign component owners and turn verified examples into development regressions. Preserve a new prospective holdout rather than absorbing every future observation into tuning.

Monitor changes in input distributions **and** actual quality/calibration: drift alone is not proof of poor performance, and stable distributions are not proof of quality. Retraining/reweighting starts a new version and repeats pre-release gates. Evaluation/rubric changes likewise receive a new version and a dual-run bridge report on the incumbent before becoming the new grading standard.

### Rollback and graduation

Immediate containment for a confirmed critical integrity/privacy/ownership defect; pause expansion for broken telemetry, sample-ratio mismatch or untrustworthy attribution; investigate/revert a qualified harmful quality or reliability change according to preregistered limits. Sparse data results in continued observation or a limited experiment, not an unsupported automatic rollback or promotion.

Prefer isolating the responsible component: input adapter, constructor, gate, reranker or delivery layer. Record exact configuration before/after, deployed artifact and verification. Preserve all historical evidence. Graduation requires the predeclared evidence threshold, independent approval and updated registry/model/policy cards. Do not retire the comparator or delete branches/data as an automatic consequence of a winning chart.

## 6. Validate the evaluator itself

The grading system is production-quality software even if it runs offline:

- Mirror invariance: swap viewer/counterparty and preserve canonical side grades; no accidental dependence on which actor was named A.
- Asset-order invariance; exact-package binding; duplicate-asset and wrong-owner rejection; consistent pick parsing and units.
- Independent small-roster brute-force lineup oracle to check the optimized assignment; verify FLEX/Superflex, unavailable starters, required cuts and depth.
- Known-signed cases for buying liked/selling disliked assets, wrong-direction trades, tanking RB exceptions, own next-draft picks and disproportionate filler.
- Temporal tests for separate original/late/match snapshots, out-of-order ingestion, duplicate/replayed actions, undo and expiry.
- Historical-milestone tests: overlapping likes followed by withdrawal remain one mutual milestone plus attrition; nonoverlapping likes remain zero; redisplay never extends the deadline; carry-in and late outcomes retain their original attribution.
- Missingness tests: unknown counterparty ranks, stale projections or an unlinked completion never become high-confidence passes or definite failures.
- Holdout independence, deterministic rerun hashes, input immutability and schema/metric version migration tests.
- Deliberate sabotage: turn off stud tax, swap A/B boards, use dynasty value as points, count generated cards as views, erase pass labels or rank with the evaluated answer. The relevant tests/scorecard must fail, then recover when the defect is removed.
- Independent formula checks on a small manually computed dataset; denominator reconciliation and cluster/maturity test fixtures for aggregate reports.
- Denominator/source attacks: fewer generated episodes cannot inflate fixed-cohort yield; nonresponse cannot calibrate unobserved willingness; two constructors plus an inbound delivery cannot create three product wins. Use the concrete fixtures in the [adversarial review record](adversarial-review.md).

Shared canonical parsers/identity utilities are appropriate. Reusing the model's own acceptance/utility decision as the evaluation answer is not. Keep production scoring and evaluation implementations separately reviewable; common helper bugs require external/golden controls.

## 7. Best practices and antipatterns

| Use this practice | Avoid this antipattern |
|---|---|
| Freeze hypotheses, grading rules, cohorts and holdouts before experiments | Tune the rubric or choose favorable slices after results |
| Independent four-side + two-package review | Viewer-only grading or one high mean hiding a losing counterparty |
| Price realism plus actual mutual outcomes | “KTC agrees, therefore both managers accept” |
| Separate source, model, policy, display and outcome versions | Blame the constructor for every decline or credit it for a delivery speedup |
| Report candidate recall/yield as well as retained precision | Improve percentages by filtering almost everything |
| Preserve zero-offer requests, unknowns and timeouts | Drop difficult requests from the denominator |
| Grade focal assets and marginal starter impact | Add trivial preferred pieces or bench value to manufacture fit |
| Explicit context-specific exceptions | Hard-code every preference as an absolute prohibition |
| Group concepts, managers and league histories; split by time | Leak mirrored/repeated trades or future rankings/slots across splits |
| Actual exposure, historical milestones, current state and mature windows as separate facts | Treat silence as refusal, erase an earlier valid match after withdrawal, or count nonoverlapping likes as mutual |
| Fixed pre-assignment eligibility and origin credit; report request/episode funnel diagnostics too | Improve the primary rate by shrinking the offer population or crediting duplicate arms/injections |
| Name the probability target and its observed label population literally | Calibrate only on responders and claim willingness for everyone exposed |
| Valid assignment probabilities and overlap before counterfactual estimates | Treat ordering weights as causal propensities or compare current/excluded arms as an A/B test |
| Track calibration and reliability separately | Rename a heuristic score “80% acceptance” |
| Interpret age/outlook/roster utility distinctly from private price | Double-discount the same concern and erase explicit user tiers |
| Blind/dual review with disagreement retained | Let one owner's preferences or an LLM judge stand in for every manager |
| Incremental batch delivery with full inventory/quality checks | Meet latency by silently shrinking search or returning unactionable placeholders |
| Publish negative experiments and unknown limits | Hide failed trials, claim significance from repeated peeking, or imply code tests prove product fit |

## 8. Framework adoption and initial deliverable

Before the first modeling sprint, hold a short rubric calibration with product, modeling, evaluation and data owners using a small mixed sample: tanking/contending, two complete boards, missing counterparty board, stud tier-down, first-round-pick return, starter hole and delayed counterparty exposure. Grade each side independently, resolve wording and freeze v1. This is calibration of reviewers, not a statistically representative model score.

The first production report for the current model should be published even if it reads “not enough bilateral outcome evidence.” It must contain a complete component/version registry, the six-dimensional baseline with unknown coverage, both-party example audit, stage-removal analysis, label/data-quality gaps and a prioritized improvement backlog. Only then should the team optimize a new model against the framework.

A lightweight recurring review agenda: what changed; which manager/segment benefited or lost; whether enough outcomes matured; whether a gate hid useful offers; whether data or evaluator problems explain results; and the next controlled experiment. Every action has a named owner and evidence deadline. This plan creates no automation or production toggles by itself.
