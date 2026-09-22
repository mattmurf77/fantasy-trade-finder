# Scorecard contract — proposal v1

This specifies the framework to build, not existing scores or already-ratified thresholds. Parent [build plan](plan.md); process and document ownership in [ways-of-working](ways-of-working.md).

## 1. Unit of evaluation: two managers, four asset-side assessments

For every exact package and evaluation stage, create:

| Perspective | Outgoing/give assessment | Incoming/receive assessment | Whole-package judgment |
|---|---|---|---|
| Manager A | Are these sensible assets for A to move, and is their loss/cost acceptable? | Are these desirable and usable assets for A to acquire? | Is A's complete exchange acceptable in A's context? |
| Manager B | A's receive assets, evaluated as **B's outgoing assets** | A's give assets, evaluated as **B's incoming assets** | Is B's complete exchange acceptable in B's context? |

Repeat this structure for **all six dimensions**. The asset directions mirror; valuations, outlook, roster impact and confidence do not. Do not copy A's grade to B or infer B's agreement from A's like. Reversing the viewing perspective must preserve the canonical two-manager result.

Each assessment contains: raw features/deltas; grade and reason codes; input sources/timestamps; applicability; evidence level; exception/override; evaluator version; and links to exact assets/occurrences. Inferred counterparty preferences remain inferred, not user declarations.

Use five anchored human/rule grades for *appropriateness*, not predicted probability:

- **0 — unacceptable:** clear contradiction or material unjustified harm.
- **1 — weak:** marginal benefit or poorly justified cost; unlikely to meet the stated objective.
- **2 — acceptable:** coherent, defensible trade-off for this manager; not every dimension must improve.
- **3 — strong:** clear benefit with an appropriate cost.
- **4 — excellent:** compelling benefit and well-supported terms, without creating a serious offsetting problem.
- **Unknown** means necessary evidence is absent. **N/A** means the dimension legitimately does not apply. Neither becomes a 2 or 4; report their shares.

Outgoing/incoming assessments are judged in the context of the full exchange. A contender can appropriately give a valuable young player to improve its starting lineup; a rebuilder can appropriately lose immediate production. The independent grades must explain that sacrifice rather than demand that every outgoing player be bad.

For dimension d, show `grade_A,d`, `grade_B,d`, and `weaker_d = min(grade_A,d, grade_B,d)` when both are known and applicable, alongside all four side assessments. A **bilateral dimension pass** provisionally requires both whole-package grades >=2, no unapproved unacceptable side assessment, and any dimension-specific hard gate. Missing evidence prevents “verified bilateral pass”; show an evidence-limited assessment instead. N/A is excluded explicitly with an applicability mask, never averaged away silently.

Do not average away an unacceptable participant or gate. Summaries show six dimensions, bilateral pass rates, worst-side distribution, critical violations and evidence coverage. Raw metrics remain authoritative; grades organize review. Calibration against human judgments is required before automated grades become release gates.

### 1.1 Missing evidence, user authority and decision eligibility

| Situation | What can be graded | What cannot be claimed / effect on release |
|---|---|---|
| B has no personal board, or an unranked centerpiece | A's known preferences; B's market/roster/outlook evidence independently | B personal-rank fulfillment is Unknown for unsupported assets, not N/A or a consensus-based pass. A documented sparse-board cohort may qualify for a limited experiment; no verified two-board personalization claim |
| Selected and inferred outlook disagree | Recommendation fit against the selection; inference disagreement separately | Inference does not veto the user's intent; do not score obeying the user as failure merely for disagreeing with the predictor |
| Current projections or necessary lineup rules are missing | Known roster facts and explicitly named dynasty-value fit proxy | Projection-backed starter gain is Unknown, not zero or positive projected points. Broad promotion of a starter-improvement claim needs its predeclared coverage; a scoped proxy experiment must disclose the limitation |
| One manager has not viewed/responded | Independent six-dimension evidence/proxy grades where inputs suffice | No behavioral bilateral preference label. A fully observed mature nonconversion remains operational zero, not a rejection label |
| Ownership, exact terms or event identity are unreliable | Data-integrity failure and affected population size | Quarantine unreliable labels; do not pass correctness or infer a winner. Production's existing legality/integrity protections remain distinct from evaluation |
| A user deliberately selects an otherwise disfavored player/package | Same honest grades, selected-search purpose and explicit exception reason | Evaluation does not introduce a new recommendation veto or permanently rewrite saved preferences. A justified exception is not a violation; an objectively costly choice need not receive a good grade merely because selected |
| Immediate starter improvement conflicts with tanking | Applicable portfolio/roster-integrity assessments | Immediate starter gain is N/A, not Unknown or an automatic overall needs pass |

Unknown cells prevent a verified pass **for the affected claim**, not all learning or a current behavior's automatic shutdown. Preregister tolerable coverage and the permitted experiment population; report all excluded/unknown shares. Never obtain promotion by silently dropping sparse or difficult cohorts. This scorecard observes and grades; changing live rejection behavior requires a separate policy proposal and authorization.

### 1.2 Dimension-specific anchor minimums

Apply these anchors independently to each directional assessment in the context of the exchange and then to the manager's package. Grades 1 and 3 interpolate between adjacent anchors; evidence absence stays Unknown, not 1. Final adjudicated examples and raw-feature thresholds are frozen during framework bootstrap before challenger tuning.

| Dimension | 0 — unacceptable | 2 — acceptable | 4 — excellent |
|---|---|---|---|
| Fairness, expert proxy | Material uncompensated cost or clearly dominated overpay without a valid justification | Plausible terms within the declared tolerance, with coherent benefit and compensated sacrifice | Compelling personal/team benefit at independently well-supported terms, with no identified dominated alternative in the audited comparison set; still not an acceptance probability |
| Outlook | Portfolio moves against selected intent without an approved rationale | Coherent progress or defensible sacrifice for that manager's plan | Strong plan progress without sacrificing protected/favored assets unnecessarily; exceptions supported by facts, not just flags |
| Team needs | Severe new relevant starter hole, unusable return or hidden required-cut harm | Usable improvement or justified depth/portfolio benefit, without material unaddressed damage | Large, projection-supported marginal improvement at actual starting slots, or exceptional applicable roster benefit; never invent starter points for a tanker |
| Personal ranks | Focal assets systematically move against known preferences without justification | Known preferences are respected or neutral consideration supports a justified objective | Meaningful focal buy/sell preference gaps fulfilled with no unnecessary favored-asset sacrifice; not rescued by a liked throw-in |
| Meaningful packages | Ordinary-discovery trivial/filler-only trade with no approved exception or meaningful benefit | A qualifying focal purpose and useful return relative to what this manager surrenders | High-impact, bilaterally suitable exchange with little filler; large raw totals alone cannot earn 4 |
| Stud tax | Best-asset seller materially undercompensated, or buyer charged unjustified/double premium | Compensation fits independently justified consolidation/fit bands and relevant exemption | Compelling compensation/upgrade for this manager within defensible terms on both sides; larger premium alone cannot earn 4 |

Fairness's human grade is a proxy distinct from observed outcomes and calibrated predictions. Gate status, magnitude and confidence are separate fields. Domain reviewers must explain both the give-side opportunity cost and receive-side usefulness; a valid favorable package can score well even when the outgoing asset itself is excellent.

## 2. Fairness: probability of willing execution by both parties

### What it measures

Both managers would willingly execute the **exact package**, at the presented terms, in their respective contexts and within the defined episode. Community price proximity is an explanatory feature/guardrail, not the label. Like, mutual match, provider send and completed trade are distinct milestones.

### Independent side checks

- **Give:** raw market and personal value surrendered, package-adjusted cost, best asset lost, opportunity cost and approved willingness to pay for a goal.
- **Receive:** raw/adjusted market and personal value obtained, plausible willingness to acquire, replacement adequacy and whether filler is doing spurious pricing work.
- **Whole package per manager:** market loss/gain and range; personal desirability; outlook/needs justification; account fairness setting; dominated-overpay check. Personal enthusiasm is not permission to charge more when a cheaper, equally suitable package exists.
- **Pair:** both approvals, weaker-side judgment and dependence between the decisions. A low-price bargain for A may be unacceptable to B.

### 2.1 Frozen episode, historical milestone and maturity

An episode links unchanged exact terms, stable participants and all occurrences in one validity window. Proposed start is the first verified view; a validated user action can establish exposure only under a documented fallback evidence class. Capture any earlier creation time and actual expiry too. The deadline is the earlier of original stored expiry and start +14 days; never manufacture a later expiry. Missing start/expiry evidence makes temporal attribution evidence-limited.

Freeze origin request/search-intent ID, originating manager-league, origin window, assignment/version and deadline. Redisplay, repeated requests, a day-13 counterpart view, a new deployment or likes-you injection cannot restart the horizon. After an episode expires, a new independently initiated search may create a new episode only under a preregistered rule requiring fresh ownership/validity checks and a new origin record. It cannot reopen prior interest. This is an analytics identity rule, not a new production reconfirmation requirement. Changed terms are a new exact concept, linked separately as a negotiation family.

Reconstruct each manager's active-interest intervals from like, undo/withdrawal, expiry and invalidation events. A **valid mutual-interest milestone** is the first instant both interests overlap while the package is valid. Store it immutably as a historical event. Later withdrawal, match rejection, invalidation or expiry changes current status and produces a separate attrition/cancellation metric; it does not erase a previously valid milestone. Correcting a proven logging/identity error is a versioned data correction, not behavioral attrition. If A withdraws before B likes, there is no milestone.

Keep three independent fields: lifecycle state (open/closed and why), elapsed follow-up maturity, and observation completeness. Early failures/expiry stay in their original denominator, rather than accelerating only favorable cohorts into the report. A cohort is mature after its last possible episode deadline plus a preregistered ingestion lag; completion has its own longer follow-up window. Missing telemetry after elapsed time is unknown observation, not a negative preference label. Report observed lower-bound yields and missing-evidence bounds/coverage; do not claim a fully observed comparison or promote on a material instrumentation gap.

### 2.2 Product yield, funnel diagnostics and attribution

**Primary online promotion outcome: distinct valid mutual-interest concepts per fixed eligible manager-league observation window.** Before assignment, freeze the eligibility rule, cohort membership and origin window. Use pre-period activity/linked-league/measurement-support criteria with a declared lookback—not future request counts, generated offers or eventual responses. A recommended initial origin window is 14 days, followed until every originating episode has completed follow-up. No-request members, empty/error searches and later inactivity remain in the denominator. Platforms or accounts lacking measurement support must be identified at enrollment; subsequent outages are reported, not grounds for favorable exclusions.

Count each exact concept at most once in the primary numerator for an experiment cohort, even if repeated episodes or both managers produce occurrences. Credit it to one frozen originating manager-league/window. Randomized assignment at league/connected-cluster level determines intent-to-treat comparison; it is not reassigned to whichever arm or screen appeared last. Report league-macro and manager-league-weighted results, cohort size, cluster-aware uncertainty, delivery/exposure coverage and no-request rate. The metric is realized mutual-interest **yield**, not a probability that a random proposed trade is fair. A documented change to the primary metric requires a new preregistration, not choosing a more flattering denominator after results.

Preserve the complete generating-arm set, actual selected serving source, original assignment and subsequent exposure sources. Descriptive arm tables credit the frozen selected origin source once; when it cannot be uniquely established, use shared/unknown rather than guessed fractional or duplicated credit. Offline discovery reports may credit every constructor that independently found the concept, clearly marked as overlapping construction coverage. A likes-you injection is downstream delivery, not another constructor win. Carry-in episodes whose first view predates assignment are separate; late outcomes after switching/deploying remain with the original cohort. A first view after assignment of a pre-assignment generated candidate is flagged as pre-generated inventory and handled by the preregistered carry-in rule, not mislabeled as new-arm construction.

Mandatory secondary diagnostics, each with numerator, denominator, evidence class, cutoff and uncertainty:

1. **Request yield:** unique mutual concepts credited to their originating search intents / all eligible user-initiated search intents. Retries, polling, background precomputation and replenishment are not new intents. Freeze how changed selections/new explicit searches create an intent; failures and zero-offer intents remain. Also report request frequency per fixed eligible member. This cannot replace the primary denominator if treatment changes search behavior.
2. **Episode conversion:** episodes attaining a valid historical milestone / all eligible mature episodes, including terminal failures. It describes conversion efficiency; an arm cannot win promotion merely by offering fewer easy packages.
3. **Responder-conditional like share:** last non-undone explicit like decisions / last non-undone explicit like-or-pass decisions at the fixed deadline, among exposure-qualified manager-episodes. Withdrawal/no remaining decision and nonresponse are separate. Show response coverage; this is not exposed-population willingness.
4. **Exposed by-horizon conversion:** per-manager valid expressed-interest milestone / mature exposure-qualified manager-episodes with complete observation; joint milestones / mature dual-exposed episodes. Nonresponse is operational nonconversion, not preference rejection. Missing observation is separate. Report organic discovery versus injection and the two-explicit-responder subset; these selected funnel cohorts are not causal primary populations.
5. **Counterparty conversion after first interest:** valid historical mutual milestones / mature first-interest episodes with verified second-party exposure. Stratify by lag and whether first interest was still active at exposure. Never count a late nonoverlapping like as a match.
6. **Post-milestone attrition and confirmation:** later withdrawal, match-stage rejection/cancellation, expiry without completion and explicit both-party match confirmation, each against the corresponding mature historical-milestone cohort. Show event timing and avoid summing overlapping reasons. A historical mutual like is not necessarily still actionable today.
7. **Provider-confirmed exact completion:** verified exact completed concepts per fixed eligible manager-league window, with separate proposal-to-completion and milestone-to-completion diagnostics. Freeze provider observation support and completion horizon; absent platform coverage is unknown, not failure. Amended-package completions are separate. A send alone is not completion.

**Promotion guardrail: durable intent, not just transient interest.** Preregister maximum tolerated deterioration in post-milestone withdrawal, explicit match rejection/cancellation, and match confirmation where supported. Freeze a separate post-milestone follow-up horizon, ingestion lag and minimum observation coverage in the ratification/experiment records. Report remaining offer validity and time at risk so a late match with little validity left is not treated as having the same opportunity as an early match. This follow-up does not extend the production offer's life. Keep expiry without confirmed outcome distinct from explicit withdrawal/rejection; it is not automatically a refusal.

Co-report non-reversed historical mutual concepts at the fixed follow-up cutoff per **original fixed eligible cohort**, alongside conditional attrition/confirmation rates. “Non-reversed” is a historical follow-up status, not proof an expired offer remains actionable or completed. Incomplete follow-up stays unknown, with coverage/bounds; it cannot be counted as retained intent. Improved primary yield alone cannot establish improved willingness to execute or justify broad promotion when reversals breach the predeclared limits, confirmations deteriorate materially under the declared guardrail, or essential follow-up has not matured/is unreliable. Such a result is failed or evidence-limited; any further monitored learning experiment requires explicit approval. Sparse/unsupported provider completion remains a separate limitation, not an impossible universal prerequisite for promotion.

### 2.3 Probability evaluation, once justified

The owner-defined product meaning of like/queue/send is **expressed willingness to execute the shown package**. Preserve that contract. Empirically, these are observable expressions, not proof that the trade completed or a calibrated estimate of every exposed manager's unobserved willingness.

Every predictor names its literal event, population, time horizon and observation assumptions. Examples: `P(like decision at deadline | exposed, explicit resolved responder, context)` for responder-only labels; `P(valid like milestone by deadline | exposed, context)` for fully observed operational conversion; and `P(valid mutual milestone by deadline | episode, defined exposure process, context)` for a joint operational model. The fixed-cohort primary above is a yield/count target, not the same episode-level probability. Provider-confirmed execution is a different, coverage-qualified label.

Compute Brier/log loss/reliability only on held-out labels from the **population the predictor actually names**, with cluster-aware uncertainty and response/observation coverage. Responder-only calibration cannot establish `P(willing | exposure, context)`; listing selection bias as a footnote does not fix that estimand. For example, 10 likes and 90 silent exposed managers can give 100% responder-like share and 10% observed like conversion, but exposed-population willingness remains unknown. Blinded expert acceptability stays a proxy. A broader willingness claim needs a defensible identification/label-collection design and sensitivity analysis; otherwise label it “not established.” Optional randomized paired-manager intent elicitation can supply **stated-intent** research labels, not proof of execution, and is not required for the initial baseline.

Calibrate separately from training and the locked final test; report A, B and joint predictions separately. Do **not** multiply unconditional marginal probabilities and assume independence. Use validated conditional funnel factors with their actual risk sets, or a validated joint model. Until justified, show ordinal support instead of a probability. The current bilateral support score and hand-set uncertainty range are neither probabilities nor statistical confidence intervals.

**Antipatterns:** treating KTC agreement as acceptance; using accepted Sleeper trades as negatives/positives sufficient for probability fitting; assigning a pass to an unviewed card; reward-maximizing A by overpaying B; grading a model using its own utility threshold.

## 3. Outlook alignment

### Intent authority and inference quality are different tests

The manager's selected outlook governs recommendation intent. Preserve inferred outlook as a separate diagnostic and evaluate whether inference is useful/fresh where no choice exists. Disagreement does not authorize overwriting the user's choice. Measure selected-outlook fidelity, inferred-only coverage, override rate and blinded inference agreement separately; an override is not automatically an inference failure.

Map UI labels explicitly to stored values: All-in/Win Now (`championship`), Contending (`contender`), Rebuilding (`rebuilder`), Tanking (`jets`); retain balanced/not-sure behavior and verify alias handling per route. A and B can legitimately have opposite plans.

| Outlook | Outgoing-side intent | Incoming-side intent | Do not over-enforce |
|---|---|---|---|
| Tanking | Prefer selling RB production/veterans; strongly protect personally favored young WR/TE/QB and own next-draft pick unless deliberately selected | Future firsts/picks, personally favored young WR/TE/QB; occasionally a discounted long-term RB prospect or personally elite RB under the owner's approved exception | Filling current starting holes is not a benefit by itself; do not require every tanking trade to avoid all RBs |
| Rebuilding | Trade aging production when the return advances the rebuild; preserve valuable future assets | Picks and younger useful assets appropriate to a roughly 1–2 year trajectory; more flexibility than tanking | Do not treat rebuilding as automatic liquidation of every productive player |
| Contending | Spend surplus/picks selectively without needless dynasty-value loss or new starter holes | Prioritize meaningful starter upgrades and current-year usefulness while retaining future flexibility | A healthy bench addition is not necessarily a starter upgrade |
| All-in/Win Now | Willingness to spend some future value for current production while accounting for the loss of starting/depth assets | Strong current-season starters, impactful RBs, useful contingency depth where justified | Do not assume every RB is an upgrade or any dynasty overpay is acceptable |

Record incoming/outgoing pick count **and value share**, next-draft versus later picks, original owner, young WR/TE/QB share, RB share, production gained/lost, personally favored assets sold, and exceptions. Projections must identify units/horizon; unknown age is not youth. Avoid a universal age-only classifier: position, personal conviction, injury/recovery and horizon matter.

Specific tanking measures: justified RB acquisition share; unjustified RB acquisition violation rate; RB sell opportunities surfaced; favored-young-asset sell harm; own-next-draft-pick violations; inbound first-round-pick opportunity coverage within the audited candidate/probe universe. Report “no feasible pick return found within the audited search and budget” instead of manufacturing a quota or claiming exhaustive impossibility.

Grade whether the **change in portfolio** supports the plan, not whether the incoming player happens to be young. Selling a favored young WR for a less useful young WR can still fail. The user's “2+ / 3+ first” personal tier exception must use product tier definitions, not an invented Elo threshold or an undocumented age band. Grade the exception rationale and price, not just the presence of an exception flag.

**Antipatterns:** both sides inherit the viewer outlook; maximizing starts for a tanker; classifying picks by display text; valuing a future pick with its eventual known slot; discounting age/injury twice after it is already reflected in rankings without a separately justified utility effect.

## 4. Team needs and starter improvement

For **each roster**, construct an independent before/after legal best-lineup assignment under actual league scoring, starting slots, FLEX/Superflex eligibility, availability and roster limits. No player can fill two slots. Account for required cuts, lost depth, and whether incoming players displace anyone. Where reserve/taxi rules or capacities are unknown, report the limitation rather than assume legality or zero cost.

- **Give assessment:** expected starter production/availability removed; depth/contingency exposure created; whether the asset was genuine surplus; new critical holes.
- **Receive assessment:** improvement over the displaced starter, usable extra starts, positional gap closed, availability in the relevant weeks; discount unusable bench volume as a needs claim.
- **Net per manager:** total legal starting-lineup delta and positional deltas, worst new gap, roster/cut cost, and depth separately. A WR improvement cannot obscure a larger QB hole.
- **Pair:** A's offered surplus should address B's relevant needs and vice versa, considering B's own outlook rather than selling to whichever roster merely looks weak at a position.

Primary needs metrics for contenders/all-in: share of offers with a material net starter improvement; displacement-adjusted projected point delta; severe-new-hole rate; correct identified-need rate versus independent roster review; and needs-aligned acceptable opportunities surfaced per request. Define “material” in the metric registry using league-specific replacement/uncertainty, not one cross-format raw-point cutoff.

For rebuilding/tanking, score roster integrity and plan usefulness but mark **immediate starter improvement N/A** when contrary to their outlook. Do not auto-pass overall needs evidence: identify what is applicable. Preserve legitimate all-in depth trades as a separately labeled benefit, not a failed starter-upgrade claim or a fabricated point gain.

Current owner diagnostics include `market_usable_depth_v1`; `trade_roster.py` explicitly uses dynasty-value proxies, not projected fantasy points. Thus initial scorecards must distinguish **proxy-based roster fit** from **projection-backed starter impact**. Existing projection/outlook services may supply better evidence after coverage and wiring are audited; merely having an enabled projection flag does not prove the constructor used it. Non-Sleeper adapter coverage is also explicitly less complete in current code.

**Antipatterns:** team-position value sum as starter gain; reusing FLEX starters twice; grading injury-stale estimates as facts; treating an 8-team WR36 like a 16-team WR36; using the incoming package alone without subtracting outgoing starters.

## 5. Personal rank-set fulfillment

Evaluate raw user-set tiers/order and provenance at the offer time, separately from effective values adjusted for age/outlook/behavior. Consensus-filled entries do not establish personal conviction. Across league formats, compare like-for-like boards and market snapshots. All deliberate ranking actions express real preference; do not arbitrarily give one UI ranking method a weaker conviction label. Keep bounded within-tier behavioral adjustments distinguishable from explicit rankings.

Build an independently specified signed preference gap `d(manager, asset)` from personal versus market tiers and within-tier order on a comparable universe. Positive means personally preferred; negative means personally disfavored. Freeze the coordinate/normalization definition in the metric registry; do not simply reuse the bilateral constructor's .7/.3 scoring formula as the grader.

Report, per manager:

- **Incoming target hit rate:** share of focal incoming assets with known positive personal gap; value-weighted and unweighted variants.
- **Outgoing sell hit rate:** share of focal outgoing assets with known negative personal gap; value-weighted and unweighted variants.
- Incoming preference gain and outgoing preference relief separately, with explicit negative contributions retained. Net fulfillment is a diagnostic, not permission to conceal a highly favored asset unnecessarily sold.
- Personally favored asset sacrifice rate and whether it is justified by explicit selection, outlook, needs or unusually favorable terms.
- Known-personal coverage by asset count **and market-value mass**, on both sides. A fully ranked throw-in does not make an unranked centerpiece well understood.
- Feasible desired-target/sell opportunity coverage across requests, partner diversity and rank at which the opportunity first appears.

Use focal/centerpiece and full-package results together so tossing in a tiny liked asset cannot rescue a poor focal trade. Permit personally neutral pieces as fair consideration and consensus-only proposals as evidence-limited—not fake personal successes. Do not require every asset in a valid trade to be a buy-low/sell-high personal gap.

Pre-release sensitivity tests: increase preference for a target with all market inputs fixed and verify it becomes more likely to be targeted, **not more expensive solely because it is liked**. Lower preference for a roster player and verify its sell opportunity priority behaves appropriately. Shuffle/replace boards to establish whether the model meaningfully uses them. Pin a personal tier and verify interaction-derived updates do not cross it; undo must reverse the corresponding effective change.

**Antipatterns:** raw Elo as user-facing value; grading effective outlook-adjusted values as original preference; inferring dislike from nonresponse; backtesting with rankings learned from the very decision being predicted; showing a counterparty's private tiers in a public report.

## 6. Valuable / meaningful packages

The owner-defined reference is an individual player worth a second-round pick or better; higher-impact opportunities are preferred **within otherwise suitable, acceptable trades**. Value is not an instruction to maximize total package size or sacrifice feasibility.

Current live significance policy accepts an individual player meeting the second-tier threshold on personal **or** consensus evidence, or a valid first-round pick; it does not let a sum of small assets create a centerpiece. It can qualify using an asset on either side and exempts specified explicit/inbound/manual contexts. Actual second-round picks are not the same as “a player in the second-round-value tier” under that current rule. Record this distinction and any future policy choice; do not silently change live eligibility through the scorecard.

For A outgoing/incoming and B outgoing/incoming, report:

- Highest individual value tier under personal and market references, and the source that supports significance.
- Presence of a meaningful focal asset; marginal utility of what is acquired and opportunity cost of what is surrendered.
- Total value for context, number of assets/players/picks, low-impact share and filler dependence.
- Package purpose: focal swap, tier-up, tier-down, pick conversion, starter improvement or selected-package search.

Whole-package adequacy need not require a qualifying individual asset on all four sides: a justified tier-down or explicit trade can have a different composition. However, neither manager earns a meaningfully beneficial grade **merely because the other side contains a stud**. Report centerpiece presence and participant benefit as separate facts.

Metrics: ordinary-discovery no-meaningful-centerpiece rate; strongest-asset tier distribution; meaningful-and-bilaterally-acceptable opportunities per request; first-30 low-impact share; 1x1/2x1/1x2 versus larger package distribution; explicit-search exception rate and validity. Grade increasing impact only within quality/fit/fairness constraints. A seasonally useful cheap starter can be a legitimate exception needing explanation, not proof the significance rule should always be bypassed.

**Antipatterns:** summing bench scraps over the threshold; ranking a 4x4 blockbuster above a clean 1x1 merely for gross value; deleting all hard-to-please requests to raise meaningful percentage; counting explicit/manual exceptions as ordinary-discovery policy violations.

## 7. Stud tax / consolidation premium

Assess whether the manager surrendering the most valuable asset receives appropriate compensation for concentrating value elsewhere, and whether the manager acquiring it is charged a reasonable—not inflated—premium. Determine the best asset under market reference and under each manager's personal tiers; record disagreement and ties. The market pricing convention and private desirability play different roles.

Per outgoing/incoming side, retain raw additive totals, adjusted package totals, adjustment amount and attribution, best asset identity, second-best gap, asset counts, usable starting slots, surplus depth and exempt pick amounts. State whether premium is represented as a crown uplift, discount to the multi-asset side or another equivalent convention; do not add both as two independent charges.

Core measures:

- Undercompensated best-player seller rate; excessive-premium buyer rate; signed adjustment residual versus independent reviewed/reference bands.
- Residual by headliner tier, 1x1/2x1/larger shape, position, format, roster depth and pick composition.
- Filler attack tests: numerous low-impact assets must not cheaply buy an elite asset through raw addition alone.
- Mirror/asset-order invariance, monotonicity when real consideration improves, near-equal-headliner behavior, and no inappropriate tax in genuinely equivalent 1x1 trades.
- First-round-pick exemption correctness: current `stud_tax_exempt_first_round=1` is part of the live policy. Audit both its implementation and empirical suitability; policy compliance alone does not establish ideal compensation.

Use observed dynasty exchange distributions and KTC/DP disagreement as independent diagnostics, controlling for league and time. Real accepted trades can be lopsided; neither their median nor KTC's adjustment is a universal mandated tax. Separate the raw-price effect, consolidation effect and roster-fit effect to avoid counting one concern twice.

**Antipatterns:** applying the tax to the side giving more assets regardless of who gives the best player; a universal premium for every 2x1; charging both a crown uplift and the same lost-utility adjustment again; using raw sums as the sole “fairness” test.

## 8. Additional product and evaluation guardrails

These supplement—not dilute—the six requested grades:

| Guardrail | Required measurements |
|---|---|
| Exposure integrity | Generated -> committed -> delivered -> verified viewed -> responded -> dual viewed -> mutual -> confirmed completion, with coverage at each transition |
| Latency/reliability | Tap to first **rendered actionable** tile, first durable batch, full inventory, p50/p90/p95/p99, timeout/error/empty rates; warm/cold, selected/organic, platform and load slices. Proposed p95 first-tile target: <=3s |
| Search opportunity | Budget exhaustion, eligible targets/partners considered, acceptable unique concepts per request, no-offer rate, candidate and post-policy recall; no artificial offer cap |
| Repetition/diversity | Exact-concept duplicates and near-duplicate headliners/partners in first30 and rolling sessions; discovery novelty; repeated passed concepts; explicit-user repeated search separated |
| Input/authority | Invalid ownership, expired picks, wrong format, stale/outdated boards/rosters, override fidelity, selection retained on intended side, correctly labeled partial alternatives |
| Cost | CPU, memory, DB/serialization cost per request and per useful unique offer; evaluation overhead must not undermine first action |
| Evidence sufficiency | Unknown/N/A share, orphan actions, both-board coverage, freshness and provenance; missingness by platform/model/segment |
| Explanation accuracy | Card claims match actual context and evidence; no inferred preference portrayed as declaration; no dynasty proxy portrayed as projected points |

Failures and true zero-offer requests stay in reliability/yield denominators. Do not “meet” a three-second metric by rendering a placeholder or a tile that cannot yet be acted on. Do not divide latency only over successful fast requests; report deadline success rate over all eligible attempts.

## 9. Required report layout

Header: model/arm/version, serving-policy version, evaluator/benchmark versions, date window, pre-release/post-release status, sample frame, mature episode count, known limitations and promotion disposition.

Six dimension rows, each with: A give / A receive / A package; B give / B receive / B package; weakest side; both-pass rate; denominator; CI; coverage; comparator delta; critical segments; representative good/bad/unknown examples. Supply construction, post-policy and exposed tabs/sections. Keep raw and standardized/cohort-adjusted results distinct.

Add separate funnel, latency, diversity, coverage, rule-removal and data-quality panels. Grading states: **pass, fail, evidence-limited, not applicable, not yet mature**. “Evidence-limited” is not a passing release result.

### Worked rubric fixtures — illustrative, not model results

**Fixture A: useful opposite objectives.** A is tanking and personally below market on its 27-year-old RB. B is contending, personally above market on that RB, and has an independently verified RB starter gap. A receives a 23-year-old WR it favors plus a next-draft first owned by B. B is below market on that WR; its departure causes no lost starts or material depth problem. There are no cuts or ownership concerns. Synthetic frozen reference values are RB =2.4 first-equivalents and WR + first =2.6; an independent fixture annotation deems the full return acceptable after consolidation/first-round exemption review. These are illustrative inputs, **not a universal premium formula**. Legal lineup analysis shows B improves by 3 projected weekly points with no new hole. Both boards, selected outlooks and current projections are available.

| Dimension | A give | A receive | A package | B give | B receive | B package | Decisive reason |
|---|---:|---:|---:|---:|---:|---:|---|
| Fairness proxy | 3 | 3 | 3 | 3 | 3 | 3 | Compensated RB sale and independently plausible current-production purchase |
| Outlook | 3 | 3 | 3 | 3 | 3 | 3 | Tanker sheds production for future assets; contender spends future surplus for a starter |
| Needs, applicable benefit | 2 | 2 | 2 | 3 | 3 | 3 | A portfolio/integrity is defensible; A immediate starter submetric is N/A. B gains actual starts |
| Personal ranks | 3 | 3 | 3 | 3 | 3 | 3 | Each moves its lower-conviction focal player and acquires its preferred one |
| Meaningful | 3 | 3 | 3 | 3 | 3 | 3 | Both managers exchange consequential assets; clean 1x2 shape |
| Stud tax | 2 | 2 | 2 | 2 | 2 | 2 | Best-asset seller compensation and buyer cost are defensible; exemption compliance alone earns no extra grade |

No actual actions occurred in this synthetic fixture, so behavioral mutual acceptance and probability calibration are **Unknown**, despite favorable proxy grades. Anchor calibration may revise the exact ordinal grades before freezing the rubric; the directional facts and prohibition on fabricated outcomes remain invariant.

**Fixture B: same terms, incomplete evidence.** Remove B's personal board and usable projections. Preserve A's four-side-context inputs where known. B's give/receive/package **personal-rank grades become Unknown**; consensus does not earn a 2. B's projection-backed needs grades become Unknown, with any dynasty-fit proxy in a separate labeled field. B's selected outlook and valid market facts can still be assessed, but cannot establish its personal enthusiasm or projected starter gain. No verified bilateral pass for the unsupported claims; an appropriately scoped limited experiment may still be permissible under §1.1.

**Fixture C: one manager harmed.** Restore the complete evidence, but make B surrender its only startable QB as additional consideration and establish that no replacement exists. B give/whole-package needs grade =0 even if A benefits and raw market totals balance; B receive can still grade well for the RB itself. The bilateral needs result fails. An explicitly selected exploration may remain visible under its own policy contract, but neither an exception tag nor the high incoming grade hides the harm.
