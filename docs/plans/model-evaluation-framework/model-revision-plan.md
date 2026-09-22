# Model revision plan — evidence-led bilateral discovery

Implementation follow-through (2026-09-22): the owner approved this plan and
requested parent-written specs, subagent implementation, independent evaluation
and conditional release. See [revision status](../bilateral-model-revision/status.md),
[model card](../bilateral-model-revision/model-card.md) and
[evaluation evidence](../bilateral-model-revision/evaluation-evidence.md).
The proposal below records the original full scope; that work must not be
mistaken for completed representative grading, projection ingestion or live rollout.

September 22, 2026. **Proposal, not implemented or deployed.** Uses the [three-model comparison](comparison-2026-09-22.md) and the [reviewed evaluation framework](scorecard-spec.md). The offline evaluator is built; representative grading, threshold ratification and production measurement are unfinished work, not completed gates.

## 1. Recommendation and decision rule

Revise **`owner_v2_bilateral` first**, with `owner_v1` and `fit` retained as frozen comparators. Bilateral currently has the strongest observed combination of owner-player direction, tanking RB sales and small packages. That is a provisional development choice from one frozen context, **not** a finding that it maximizes two-sided acceptance.

Do not merge all three formulas or pick a winner from a single composite score. Expand the benchmark before committing to one architecture. If another constructor produces better independently acceptable, preference-aligned opportunities on the locked corpus at comparable cost, revise that constructor instead. Preserve a Pareto set of candidates until mandatory safety/coverage gates and the six-dimensional report make the trade-offs explicit.

The primary objective remains: **both managers willingly execute the exact package**. Personal rankings identify assets to acquire or move, jointly with outlook and needs. Market references determine reasonable consideration. Meaningful-package and stud-compensation requirements sit around that process; none can compensate for a bad trade for one participant.

## 2. Change the right layer

| Layer | Revision responsibility | Must not do |
|---|---|---|
| Inputs / evidence | Exact offer-time boards, market sources, roster/league facts, pick identity, actual rules/projections, user authority | Fill missing preference or starter evidence with asserted facts |
| Generator / model | Joint intent discovery, small package construction, price-efficient terms, bilateral contextual support | Charge more simply because a player is liked; grade itself as the independent evaluator |
| Live presentation policy | Validity/significance checks, survivor ordering, repetition/history handling, accurate exceptions | Hide construction defects, cap available offers to improve percentages, silently remove explicit selections |
| Delivery | Prepared inventory, durable first batch, stable identities and fresh invalidation | Show unactionable placeholder cards as a three-second success |
| Independent evaluator | Frozen rubrics, two-manager/four-side judgments, outcomes, uncertainty, recall/coverage and policy attribution | Become a new runtime veto without a separately reviewed policy change |

Keep these as modules in the existing application. This plan does not require new infrastructure or microservices.

## 3. Evidence gate before tuning a winner

**E0 — expand and freeze the benchmark. Owner: evaluation lead + data/backend.**

1. Export fresh, read-only frozen requests covering all four outlooks, 1QB/superflex, league sizes/start counts, Sleeper/ESPN/MFL, full/sparse/no counterpart boards, selected/organic entry points, cold/warm conditions, and zero/error requests. Sampling units are independent manager-league/time contexts; deduplicate overlapping leagues/rosters across splits.
2. Freeze a common input, time-correct market reference and configuration for every constructor. Compare native budgets and a separately documented matched-compute probe; preserve full output. Store constructor and source hashes, input dependency versions and the actual search budget used.
3. Capture enough before/after evidence for actual league-legal starter changes, including projection horizon, FLEX/Superflex, availability, cuts and capacity. Keep unavailable-platform coverage explicit. No fabricated roster rules.
4. Build an independent exact-package review set with manager A and B judged separately, including blind positive, negative and unknown cases. Include archetypes from the owner's interview and difficult conflicts, not just attractive cards. Adjudicate reviewer disagreement and freeze the rubric before challenger tuning.
5. Separate development, calibration and locked test sets by league/account and time. Reserve counterfactual board/outlook perturbations as sensitivity tests, not additional observed users. Refresh stale test windows by a versioned protocol, never silently.
6. Establish outcome capture and observation completeness: generated → committed → delivered → actually viewed → decision → overlapping mutual interest → verified exact completion. Preserve actual expiry and withdrawals. Define the fixed eligible manager-league window before assignment so no-request/empty/error windows remain in the primary denominator.

**Exit:** signed data card and evaluator baseline, interpretable coverage by critical segment, blinded annotation agreement, and ratified metric targets/margins. If evidence is too sparse, authorize only an explicitly scoped experiment—not a universal acceptance claim. Do not choose sample size from raw card count; set minimum independent clusters/mature events through a preregistered power/MDE analysis.

## 4. Model work packages

### M1 — price-efficient terms and independently justified stud compensation

**Priority P0. Modeling + evaluation; implementation starts after E0's grading freeze.**

Observation: bilateral's first 30 post-significance cards have a mean raw-reference return of −24.8%, despite the native inventory averaging −3.4%. This is an investigation trigger, not proof of overpayment: neither number incorporates independent consolidation compensation.

- For each focal target/sell intent, enumerate a local family of legal small consideration packages. Retain both managers' outlook/needs/preference support and compare feasible alternatives at the same target and benefit level.
- Identify **dominated consideration**: avoid offering an extra pick or a more valuable outgoing player when a cheaper exact package offers comparable evidence of B's willingness and preserves A's goal. Keep materially different counterpart benefits as separate alternatives; do not optimize A's cost by making B's trade unattractive.
- Decompose raw price, concentration/stud compensation, usable lineup/roster effect and intentional goal-driven sacrifice. One concern receives one adjustment, not a crown uplift plus the same penalty again under a different name.
- Record best asset under market and both personal tiers, ties, first-round exemptions and the chosen convention. Independently estimate/review compensation bands by shape, headliner, league depth, format and pick content; do not decree a universal 2-for-1 tax.
- Respect the account-wide fairness tolerance as bounded permission for outlook, strong conviction or need-driven cost. Preference changes target priority; it does not automatically increase the asking package. Removing the user's ability to disable stud tax remains consistent with interview intent; this plan does not introduce a new toggle.

**Tests:** mirror and asset-order invariance; tax counted once; first-round exemption audit; filler cannot cheaply buy a stud; improving consideration cannot make B's terms worse; stronger liking alone never forces higher cost; explicit expensive selection remains explorable and honestly evaluated.

**Measure:** independently unacceptable A/B cost, dominated-overpay frequency, seller undercompensation, excessive buyer premium, acceptable opportunity yield and retained personal fulfillment. Raw value equality is not a release objective.

### M2 — joint personal intent and outlook, with coherent pick-oriented tanking

**Priority P0. Modeling. Can prototype independently of M1; compare separately and together.**

- Form target/sell candidates using **personal rankings + outlook + needs together**, then solve market-consistent consideration. Do not choose using personal value alone and append outlook as a cosmetic final filter.
- Tanking: prioritize RB sell opportunities and returns consisting of draft capital or personally favored, horizon-appropriate WR/TE/QB assets. Protect favored young players from gratuitous sales and the user's own next-draft picks from ordinary discovery. Long-term discounted RB prospects and genuinely personally elite RBs remain explicit, priced exceptions—not a blanket ban.
- Rebuilding: retain one-to-two-year flexibility; do not copy tanking intensity or indiscriminately sell a young useful asset. Contending/all-in: prioritize usable in-season starter improvement, with justified depth separately labeled and different willingness to spend future value.
- Acquisition/shopping preferences raise or lower priority without erasing all other ideas. Resolve conflicts through the selected outlook and explicit package intent; record why an RB acquisition for a tanker is justified or merely a weak candidate. Saved tags remain soft preferences and exploratory selections do not permanently rewrite them.
- Picks: preserve and audit the later recorded D-079/D-161 distinction: **firsts hold similar value across years; later rounds may decline**. The September22 implementation audit found existing first-round ladder and market-floor protections, with the captured live knobs enabled; the earlier generic no-discount gap was too broad. See [pick-year audit](../bilateral-model-revision/pick-year-audit.md). Investigate concrete offer-time/source/fallback failures before changing pricing, not an assumed missing blanket rule. Use projected slots only for the next draft and only with an as-of model snapshot. Do not use eventual known slots in historical evaluation. Validate ownership/year/expiry; no 2026 drafted picks reintroduced.
- Search explicit simple player-for-pick and player-plus-pick alternatives early. Audit feasible incoming-first opportunities against independently constructed probes, rather than imposing a fixed share of pick cards or claiming exhaustive impossibility after a limited search.

**Tests:** selected outlook overrides inference; counterparty keeps its own outlook; tanking/contending context flip changes priority in the intended direction; known favored young assets are not sacrificed just to maximize aggregate score; explicit pins survive; missing boards remain missing; interaction updates cannot move user-set tiers.

**Measure:** each manager's give/receive portfolio progress, justified/unjustified RB receipt, own-next-draft protection, known favored-asset sacrifice, incoming-first opportunity coverage, focal preference hits and coverage by value. Improve these without blanket class quotas or artificial offer limits.

### M3 — actual marginal starter benefit for both rosters

**Priority P1; required before promoting a starter-improvement claim. Backend data + modeling.**

- Connect the actual league scoring/slot and fresh projection evidence to an independent legal before/after assignment. Account for the starter lost, the starter displaced, FLEX/Superflex, availability and required cuts.
- Distinguish true starter improvement, contingency depth, portfolio improvement and dynasty-value proxies. A third starting-caliber RB can be useful in one league and unused in another. A WR upgrade must not hide a larger QB hole.
- For tankers, immediate starter gain is not the goal; preserve roster legality and the intentional production reduction. Missing lineup data uses a labeled lower-confidence path, not fabricated point gains or an automatic pass.
- Reuse precomputed roster/slot evidence per dependency-versioned request; do not rerun expensive preparation for every card or invalidate the first-action latency work.

**Tests/measure:** independently solved slot fixtures, 8- versus 16-team replacement cases, cuts, injury/taxi/IR uncertainty, no duplicate FLEX use, severe new holes on either side, net projected starter delta and coverage. Production claims must agree with the evidence actually consumed.

## 5. Presentation work package — diverse survivors, no deck cap

**P1. Serving-policy owner, tested separately from M1–M3.**

Bilateral's headliner repetition worsens from 11/30 to 17/30 after the independent significance projection. Re-rank **after** validity/significance removal; constructor-only diversification is insufficient.

- Cluster near-duplicates by both focal assets, counterpart, direction and package purpose. Offer the strongest acceptable representative early, then reveal materially different alternatives; preserve the remaining valid inventory for continued exploration.
- Use bounded novelty/coverage bonuses within a quality tolerance, not a hard headliner quota or removal of every similar trade. Distinguish organic discovery from explicitly shopping one player, where repetition is expected.
- Apply significance to candidate-search priority as well as final policy where safe, while preserving explicit/inbound/manual exceptions. Do not prune low-value sweeteners needed to price a meaningful trade. Audit opportunity loss with probes.
- Report first 1/5/10/30 and full inventory, separately before and after each live policy boundary. Log removal/reorder reasons so a good model is not blamed for policy losses or vice versa.
- Preserve history suppression, original interest terms and valid return journeys; changing models must not rewrite an already-liked package. No inventory cap, no minimum forced deck size, no padding with bad offers.

**Exit:** better independent meaningful/acceptable distinct opportunity coverage and less avoidable repetition, with no material loss of bilateral quality, explicit-selection fidelity or total useful opportunity yield. Thresholds come from E0, not the observed 17/30 alone.

## 6. What to take from the other models

| Model | Retain / investigate | Do not inherit without evidence |
|---|---|---|
| Bilateral | Joint focal construction, bounded preference signals, two-manager support decomposition, small package search | Current weight choices, uncertainty ranges or support floor as calibrated probabilities; early negative raw returns as inherently justified |
| Owner-v1 | Simple package coverage; comparator for market-term ranking; many native RB sales | Its observed early RB-acquisition concentration for this tanking case; the assumption that closer raw market totals mean better acceptance |
| Fit | Search probes for pick-return opportunities missed by small-package constructors; coherent subpackage extraction | Early 3-for-3 preference, bulk asset addition, or high pick frequency as automatic outlook success |

Only adopt a component if its ablation improves independently measured outcomes/quality. A contextual router or ensemble is a later option, requiring enough segment evidence to beat one coherent engine and a stable versioned routing policy. Do not reactivate all arms merely to gather more cards.

## 7. KTC, DP, Sleeper and app outcomes

- Use DP and KTC tradesourced references as **alternative independent price diagnostics**, with time/format/source snapshots and crosswalk coverage. Evaluate blend weight on development/calibration only; lock it before test. They are not two independent ground truths if they share inputs.
- Dynasty-only Sleeper completions inform feasible shape, concentration and exchange distributions. Separate redraft/keeper/unknown classification, multi-party trades, draft timing, picks and league settings. Hold out leagues/time, deduplicate transactions, and avoid valuing an old trade with future rankings or known future slots.
- Completed-only public trades lack rejected alternatives and exposure denominators. They can inform a prior/reference band, not identify acceptance probabilities by themselves. They also need not reflect this app's users.
- Owner review Yes/No labels are one participant's opinions; use them for personalized error analysis. App verified views, likes, active-interest overlap, withdrawal and exact supported completions supply distinct labels. Do not turn nonresponse into dislike or a loose pick-round match into exact completion.
- Initially retain interpretable support scoring with honest uncertainty. Fit an acceptance model only after enough properly exposed/mature data exist. Name its target precisely; calibrate each manager's response and the joint event without assuming independent decisions. Benchmark any learned model against the interpretable incumbent.

## 8. Experiment matrix and release gates

Freeze E0 before tuning. Minimum variants: incumbent unchanged; M1 only; M2 only; M1+M2; survivor ordering only; M3 on sufficiently covered leagues; best coherent combination. Use the same requested contexts and record failed/empty requests. Add market-only, shuffled-board, outlook-flipped, removed-stud-adjustment and removed-significance **offline ablations** to test whether intended inputs actually matter. These are diagnostic experiments, not recommendations to remove safety rules in production.

Each variant needs a development brief, immutable experiment manifest, six-dimensional scorecard, model card and policy card when relevant. The release decision must show:

1. No identity/ownership/time-leakage/explicit-intent critical failure; synthetic and adversarial tests identify planted defects.
2. Independent both-manager grades and coverage for all six dimensions, plus worst-side/critical-segment results. Unknown/N/A never count as passing. No aggregate gain hides a harmed manager.
3. Acceptable unique-opportunity yield and search/policy recall within the audited universe, including no-offer/error denominator. No unexplained regression in feasible options.
4. Fixed-cohort valid mutual-interest yield when mature, with post-milestone reversal/confirmation and exact-completion support. Historical mutual interest is preserved after withdrawal; retention and validity attrition remain visible.
5. Experiment design accounts for shared leagues/counterparties and duplicate concepts. Predeclare exposure units, assignment, carry-in, cross-arm attribution and cluster analysis; do not count the same matched concept as a win for multiple arms.
6. Physical-device **tap-to-first-actionable-card** evidence against the three-second target, tail/error/empty rates and load. A first durable batch of roughly 20–30 is a delivery tactic, not a reduced search space. Reuse dependency-valid preparation and continue full search/inventory access.
7. Signed threshold/coverage decision, hosted exact-head CI, rollback artifact/config snapshot, model/policy provenance and a concrete TestFlight checklist if client changes are necessary.

Do not set empirical pass rates after observing which candidate they favor. If a confidence interval is too broad, report insufficient evidence, not a win. If effects differ by segment, narrow the claim/rollout and explain it.

## 9. Sequencing and completion definition

| Stage | Deliverable | Responsible role | Exit |
|---|---|---|---|
| E0 | Representative frozen benchmark, annotation set, input/outcome coverage audit and ratified metrics | Independent evaluation + data + product | Rubric and splits frozen before challenger tuning |
| M1/M2 | Price-efficient and outlook-aware bilateral prototypes; separate ablations | Modeling | Independent scorecards show which component improves which dimension |
| M3 / policy | Actual starter evidence and post-filter diversity, versioned separately | Backend/data + serving owner | Coverage-specific benefit; no hidden veto/cap or opportunity loss |
| Offline decision | Locked three-model comparison and challenger report | Evaluation + product | Select best supported candidate; explicit remaining Unknowns |
| Shadow | Full production-path observation without changing visible offers | Backend + analytics | Parity, latency overhead and attribution validated |
| Limited live test | Preregistered, reversible rollout after release approval | Product + release owner | Mature fixed-cohort results and reversal/coverage guardrails |
| Graduation | Model card, policy card, production scorecard and rollback record | Product + independent evaluation | Documented acceptance/personalization improvement within ratified constraints |

The current task implements the **offline evaluation foundation and initial three-model diagnostic**, and writes this revision plan. It does not finish representative calibration, production instrumentation, model revisions or rollout. Those are explicit subsequent work packages; nothing is turned on by this document.

Success is not “the evaluator emits a green number.” Success is more meaningful, personally appropriate trades that **both managers actually want**, found quickly, with enough evidence to know which model and which presentation decisions caused the improvement.
