# Build plan: a permanent bilateral trade-engine scorecard

## 1. Decision and product objective

Build **one versioned evaluation framework**, used before release and after release, for every candidate generator, model arm, market-value reference, and presentation-policy revision. Start with `owner_v2_bilateral`; backfill historical arms only where evidence supports comparison.

The objective is: **find packages both managers would willingly execute, using personal rankings to choose targets and sell candidates, while respecting each manager's outlook and roster context.** Meaningful assets and stud tax are additional quality requirements, not substitutes for two-sided acceptance and personalization. In this plan, “fairness” means trade acceptability, not demographic fairness and not mere equality of consensus totals.

Deliver three related report cards:

1. **Construction/model scorecard:** what the model can find before shared downstream filtering and presentation; includes its own internal rejections and search coverage.
2. **Presentation-policy scorecard:** what is kept, rejected, reordered, suppressed or injected; quality gained and good opportunities lost.
3. **End-to-end product scorecard:** what users actually see, like, mutually match and complete, together with time-to-first-action, coverage and repetition.

Do not combine these into a single weighted “model quality” number. A high-value centerpiece cannot compensate for an unacceptable counterparty deal. See the [metric contract](scorecard-spec.md) for the six-dimensional, two-manager grading structure.

## 2. Verified starting point and terminology

Read-only production check **2026-09-22 01:36:44 UTC / September 21 9:36 p.m. Eastern**: Render service `srv-d7g37ftckfvc73a32gvg` was live at `73bfa41e358e8780b823f652cf8388ae209b977d`. Fresh `origin/main` matched. Source review used the retained clean release worktree with the same tree as that merge, not the older dirty canonical checkout's app source.

Current effective settings: `trade.bakeoff=true`; owner include/serve/only all 1; `owner_bilateral_enabled=1`; baseline/challenger/gen_v2/fit include flags 0; fit serving 0. Therefore **`owner_v2_bilateral` is the sole configured serving constructor in the exclusive owner path**, not a concurrent seven-arm experiment. Verify route-specific exceptions and observed attribution during the implementation audit; a configured roster alone does not prove every surface used it.

| Identity | Current disposition | How to evaluate it |
|---|---|---|
| `owner_v2_bilateral`, version `owner-v2-bilateral-1` | Selected owner constructor | First full baseline, both-side behavior and post-release monitoring |
| `owner_v1` | Retained previous owner constructor; not selected | Frozen offline comparator and historical evidence where joinable |
| `current` | Mandatory only in the nonexclusive comparison path, bypassed by owner-only mode | Offline comparator; do not label it live solely because the constant exists |
| `baseline`, `challenger`, `gen_v2`, `fit` | Retained implementations, excluded from current owner roster | Register separately; offline/common-corpus replay; no fabricated live rates |
| First-30 durable delivery release, `73bfa41e` | Backend delivery revision | Performance/identity/evidence parity evaluation, **not a new trade model** |

The live model uses interpretable support weights (personal preference .45, market acceptability .35, team plan .20). Its source explicitly says these are **not acceptance probabilities**. It prices against captured existing consensus; the module explicitly records `new_blend_applied=False`. Do not describe this as a newly deployed DP/KTC blend without separate evidence.

The owner model has bounded candidate search (live pool 16, per-pair budget 4,096, total budget 60,000) even though the returned deck is uncapped. Measure budget exhaustion and recoverable opportunity loss; “no offer cap” is not proof of exhaustive search. Evaluation samples/top-K cuts are measurements, never new production limits.

## 3. Segment the full engine by responsibility

These are **logical components**, not a proposal to create microservices. Keep pure evaluators and an offline runner in the existing repository initially.

```text
Provider + market + personal-board + league/roster state
                         |
          Frozen request and input preparation
                         |
   MODEL: target/sell selection -> package construction
          -> internal eligibility/utility -> native ranking
                         |
   LIVE PRESENTATION POLICY (“eval engine” in the request)
     revalidation -> roster/market/significance gates
     -> composition/diversity/history suppression/injections
                         |
       Durable offers -> API/batches -> rendered cards
                         |
     Views -> decisions -> mutual match -> provider outcome

Independent OFFLINE/ANALYTICS evaluator reads frozen inputs,
each boundary and outcomes; it grades BOTH the model and policy.
It is not the production gate grading itself.
```

| Segment / service | Responsibility and current source anchors | What its own report must expose |
|---|---|---|
| Provider/asset identity | Platform adapters, `sleeper_roster.py`, `pick_values.py`, `pick_slots.py`, roster history | Freshness, unresolved identities, pick ownership/year/slot provenance, dynasty/format classification |
| Market and personal valuations | `ranking_service.py`, `trade_service.py::price_consensus_package`, `trade_policy.py` | DP/KTC/reference versions and blend if any; raw vs effective values; explicit vs consensus-filled personal entries; package adjustment |
| Outlook/needs context | `_owner_generation_context` and worker input preparation in `server.py`; `trade_outlook_utility.py`; `outlook/`; `trade_roster_adapter.py` | Selected versus inferred outlook, inference age/source, exact slots, availability and projection coverage; missing-data behavior |
| Model constructors | `trade_gen_owner.py`, `trade_gen_bilateral.py`, `trade_gen_v2.py`, `trade_gen_fit.py`; legacy profiles via `bakeoff_runner.py` | Candidate coverage, focal choices, consideration, internal vetoes, per-manager utility, arm-native order and cost |
| Routing/experiments | `bakeoff_runner.py`, selected-search/owner route wiring | Exact model and arm/version, include versus serve status, experiment assignment, shared-candidate provenance, fallback or no-result path |
| Runtime offer validation | Owner exact-package revalidation, `trade_roster.py`, `trade_policy.py`, `trade_significance.py`, `trade_breaker.py` in `_run_trade_job` | Input correctness, two-sided checks, reasons, bypasses/exceptions and whether rules observe, reject or merely explain |
| Composition/presentation | `small_trade_presentment.py`, bakeoff composition, disposition/history suppression and inbound/likes-you handling | Order changes, diversity, repetition, removed opportunities, injected offers, selection fidelity |
| Delivery/persistence | Job admission/revocation, `_log_deck_signal_impressions`, `database.py`, `deck_diagnostics.py`, native job polling | Commit-before-publication, stale-job protection, first durable/first rendered timing, complete inventory and failed suffixes |
| Decisions/matches/completions | Existing outcome/decision/match/proposal tables, provider transaction collection | Verified exposures, effective actions after undo, exact two-sided joins, time gaps, provider send versus completion |
| Independent evaluation | **Proposed**, not yet built | Independently calculated metrics, blinded annotations, holdouts, uncertainty, comparison and release decision |

For each route, trace which components actually execute. Cover organic Find a Trade, selected give/get canvas, More Offers/tier changes, league buy/sell, Team Review/Overhaul, inbound/likes-you, manual calculator/provider send, app-open preparation and replenishment. A hand-built or inbound offer is not a constructor win; grade its presentation and outcome separately. Team Overhaul has plan/sequence-level goals in addition to these card-level contracts; do not quietly pool its results with single-trade discovery.

Some checks are inside the constructor and again in the worker. Label their stages independently. A “pre-policy” sample consisting only of model survivors cannot diagnose its internal false rejections; log internal stage counts plus reproducibly sampled rejects and run common candidate probes.

Register upstream predictive components too: outlook inference, projections, market-value estimation/blends, rank-learning updates and any future acceptance predictor. Each gets an input/output contract and its own direct metric (for example, projection error in actual point units or calibrated outlook probabilities where genuinely predicted), plus ablation/propagation analysis on the bilateral scorecard. Not every component directly constructs cards, and historical game outcomes cannot by themselves grade a manager's chosen intent. This makes the framework extensible to new models without misattributing the whole engine's outcomes to every component.

## 4. Architecture of the evaluation framework

### 4.1 Version everything needed to explain a result

An evaluation run references immutable identifiers for:

- Model family, constructor/arm and generator version, code commit, trained artifact hash if applicable, parameter/config snapshot and routing flags.
- Input snapshot: provider/roster/pick state; selected and inferred outlook; personal board values, tiers, order, provenance and timestamps; market source/format/date; injuries/projections/league rules and their timestamps.
- Serving-policy version, individual gate versions/config, native order, post-policy order, delivery/client versions, request/surface and explicit selections.
- Evaluation rubric/code version, benchmark/split manifest, annotation version, label cutoff/maturity window, random seeds and resource environment.

Treat a parameter-only change as a model/policy revision. The same arm name with different parameters is not one homogeneous cohort. Resolve feature flags at generation and exposure; retain the captured original configuration rather than joining today's settings.

### 4.2 Data products to build, not assumed existing tables

| Logical dataset | Grain / contents | Existing evidence to reuse; gaps to close |
|---|---|---|
| Model/arm/policy registry | Version + effective interval + environment + surface | Config/flags, source constants, deployment receipts; add durable version and owner registry |
| Input snapshot manifest | Immutable capture shared by a job/manager/league | Existing valuation/owner/roster diagnostics; audit full provenance and as-of reconstruction coverage |
| Candidate stage trace | Job, candidate, stage, result, reason(s), ranks and lineage | `bakeoff_runs` counts and existing diagnostics; add internal/post-rule survival accounting, before/after mutation hashes |
| Offer occurrence | One exact package presented to one manager at one time | `deck_impressions`, `assets_json`, `valuation_json`, `model_arm`, `arm_rank`, `trade_concept_id`, source-like link |
| Exposure/action ledger | Actual rendered view and effective decision sequence | `deck_outcomes`, view events, `trade_pass_reasons`, decisions; dedupe/replay undo; legacy/orphan classification |
| Bilateral episode and cohort attribution | Exact concept, frozen origin/assignment/window, linked A/B occurrences, interest intervals, historical milestones and later reversals | `trade_matches` and original impression IDs; add fixed eligible-cohort membership, carry-in/shared/unknown attribution and maturity/observability fields |
| Provider outcome link | Proposal or exact episode -> confirmed transaction, provenance/confidence | `trade_proposals` proves send, not completion; match to completed provider transactions only when verifiable |
| Evaluation run/result | Dimension x manager x side x stage x segment, numerator/denominator/CI | New offline/analytics product; immutable manifest and evidence drill-through |

Physical schema design comes after a column-level audit. Do not create parallel stores duplicating immutable diagnostics unnecessarily. Reuse diagnostic compaction/shared hashes; keep retained raw research and private ranks out of public reports and Git. Set role-based access, retention/expiry, approved use of scraped data and deletion propagation before persisting more data.

Log lightweight total counters at every stage. For potentially large rejected populations, store a deterministic stratified sample with sampling probabilities and reasons, alongside complete counts. Evaluation sampling must not truncate actual generation or block first cards. Weighted sample estimates must display uncertainty. Preserve the minimal frozen evidence needed before current diagnostic retention expires; purged history is “unreconstructable,” not silently filled with today's data.

### 4.3 Time and identity are first-class

Use stable participant IDs to define A/B. A's give is B's receive, but each manager values those assets under their own context. Do not infer chronological order from legacy `user_a`/`user_b` names: existing match documentation has inconsistent descriptions of which user liked first. Confirm writers with fixtures and sort actor-stamped events by time.

Retain generation, durable commit, actual view, like/pass/undo, mirror eligibility/view, mutual match, provider send and completion times separately. Preserve three valuations when available: original A occurrence, later B occurrence, and match-time reassessment. New market/board/roster state is an explanatory delta, never a replacement for old evidence.

Use the owner's two-week interest horizon as the **proposed evaluation episode window**, aligned to actual stored offer expiry once verified. Freeze the origin, deadline, exact terms, originating experiment assignment and input versions. Redisplay, likes-you injection, a later deployment or repeated requests do not restart the clock or transfer historical credit. Changed terms start a different exact concept; genuine post-expiry opportunities require the predeclared new-episode rule, not reopening an old episode. Evaluation must not extend production expiry or introduce a user reconfirmation requirement.

Reduce actor-stamped actions to validity/interest intervals. A historical mutual-interest milestone occurs only when both interests overlap while the exact package is valid. Preserve that milestone after a later withdrawal, cancellation or expiry; report those later events separately. Two nonoverlapping likes never count as mutual. Distinguish terminal state, elapsed follow-up maturity and complete observation: early failure remains in the fixed cohort; missing telemetry is not a preference rejection. Use the explicit lifecycle, cohort and attribution contract in [scorecard §2](scorecard-spec.md#2-fairness-probability-of-willing-execution-by-both-parties).

Keep the complete generating-arm set, actual selected delivery source, episode origin, later presentation sources and randomized assignment separately. A product event is counted once; several constructors may receive offline discovery credit for the same concept, but not several causal outcome wins. Carry-in episodes predating assignment and shared/unknown origins remain distinct cohorts. Primary online yield uses an eligible manager-league population fixed before assignment, not the number of offers an arm elects to create. No-request members, failed/empty searches and outcomes arriving after an arm switch cannot silently disappear from that population.

## 5. Benchmark portfolio and development experiments

Use complementary sets, not a single “ground truth” dump:

1. **Owner interview contract suite:** formal synthetic cases encoding selected-outlook authority, tanking RB exceptions, favored young assets, own next-draft first, selected packages, fairness tolerance, stud consolidation, limited benches and within-tier learning. These are known development cases, not a hidden test set.
2. **Blinded domain-reviewed set:** real or carefully reconstructed frozen contexts, both managers assessed independently. The owner's FFv3/Newtown yes/no exercises are valuable but one manager's labels; never relabel them as the counterparty's acceptance. Keep newer untouched reviews as a prospective holdout.
3. **App outcome set:** verified views, effective decisions, actual mutual matches and confirmed completions; tier by evidence quality and maturity. Report old/unknown model attribution rather than inventing it.
4. **Sleeper dynasty completed-trade corpus:** use the collected corpus after revalidating its manifest, dynasty-only metadata, duplicates, league-season completeness and reserved holdout. Prior research counts are historical, not a fresh inventory. It supports exchange shapes and relative market plausibility; positive-only completed trades do not supply refusal labels or private personal ranks.
5. **KTC tradesourced / DP / blended reference snapshots:** separately versioned comparators in common pick-equivalent or normalized units. Compare disagreement and residuals, not equality of incompatible raw points. If testing blends, tune weights on development data only and freeze before final evaluation. The current bilateral constructor is not proof that this blend is already live.
6. **Stress and missing-data set:** ESPN/MFL/Sleeper, sparse boards, expired picks, late exposure, stale injury information, unusual slots, tiny/deep leagues, explicit larger packages, concurrent invalidation and resource limits.

Split by time and whole league lineage where possible; group cross-league managers and exact/mirrored concepts to prevent contamination. Track connected components where a manager spans leagues. Keep development, tuning/calibration and locked test sets separate. Evaluate with contemporaneous values/expected pick slots; no eventual slot, future results or today's rank history in past predictions. Where historical KTC vintages or rosters are absent, label the exercise cross-sectional—not a historical acceptance backtest. KTC tradesourced data may overlap collected Sleeper trades; deduplicate known overlaps and disclose unmeasurable source overlap. It is not an independent holdout just because it came from another website.

### Controlled comparison matrix

| Experiment | Hold fixed | Change | Question |
|---|---|---|---|
| Constructor comparison | Inputs, market reference, resource reporting, downstream policy | Constructor/arm | Which model finds better opportunities? |
| Market reference comparison | Candidate packages, personal ranks, outlook, evaluator | DP, KTC tradesourced, predeclared blends | Which pricing reference explains terms better? |
| Presentation comparison | Identical candidate corpus with native ranks retained | Gate/filter/order version | What improves or damages what users see? |
| Factorial confirmation | Same frozen context and evaluation version | Model x presentation policy | Is the gain an interaction rather than model quality? |
| Input ablation | Same contexts/model/policy | Personal board, outlook or needs removed/shuffled individually | Does the intended input materially and correctly influence choices? |
| Resource frontier | Same model/context and thresholds | Documented compute allocation | How much quality/coverage is lost to budget exhaustion? |

Run every model on the same requests, report its own generated-candidate quality, and evaluate a union/common probe corpus for validation behavior. Compare matched budgets **and** quality/latency frontiers; different algorithms may spend an identical budget differently. Do not demand arbitrary historical trade reproduction as the only success condition: several packages can satisfy the same intent. Use target/partner/shape coverage and blinded relevance in addition to exact recall. Recall/feasibility claims are relative to the declared audited or probe universe and budget; use “none found within this search,” not proof no possible trade exists, unless a small exhaustive oracle actually establishes that.

### Presentation-policy evaluation

Measure independent good/bad labels at each boundary:

- Precision among retained/presented offers; removal rate of independently bad offers.
- Recall of independently good offers from the auditable candidate universe; false-reject rate, with denominators and sampling weights.
- Net opportunity yield per eligible request: distinct independently acceptable concepts reaching the display, not just an improved percentage after aggressive filtering.
- Rank quality at positions 1, 5, 10, 30 and the full returned inventory, plus actual exposure-weighted results. Report availability when a request has fewer than K cards.
- Drop counts, exclusive first-failure attribution and overlapping rule failures separately. Apply all rules in diagnostic mode to a bounded sample to reveal order dependence. A drop by the first rule does not prove later rules would pass.
- Diversity, repeat headliners/partners, selected-asset retention, fallback/partial-label correctness, inbound exceptions and time-to-first-action.

A policy change and a constructor change must be independently versioned and benchmarked. Internal model support cannot be the reference label for either.

## 6. Build sequence and acceptance criteria

Ownership is by role; assign named people before work begins. Existing code/tests and collected data are reused, not replaced wholesale.

| Work package | Accountable / dependencies | Deliverables | Exit criteria |
|---|---|---|---|
| 0. Initial charter and invariants | Product owner + evaluation lead | Draft six-dimension anchors, current arm/surface registry, named owners, fixed-cohort/outcome definitions, correctness invariants and baseline sampling plan | All six dimensions defined for A/B outgoing/incoming; unknown/N/A distinguished; no empirical promotion thresholds claimed before measurement |
| 1. Evidence/data audit | Data engineer + backend lead; after 0 | Column-level existing/new map, identity/time reconciliation, lifecycle reducer, immutable replay schema, coverage query set, privacy/retention plan | Sample episodes trace from occurrence to both actions; duplicate/undo/mirror/late/expired cases pass; unjoinable data is quantified, not repaired by guesswork |
| 2a. Minimum evaluator, corpus and incumbent baseline | Evaluation lead + domain reviewers; after 0/1 | Independently tested dimensional evaluators, stage adapters, calibrated human rubric, benchmark cards/splits and minimal incumbent-only replay/report | Orientation/mutation/property and deliberate-bug tests pass; human disagreement documented; baseline manifests reproduce grades, base rates and evidence gaps without a full dashboard |
| 2b. Freeze grading/release contract | Product + independent evaluation/analytics; after 2a, before challenger tuning or locked-test access | Signed threshold decision record: metric/rubric version, justified margins, critical slices, minimum coverage, power assumptions, exceptions and monitoring limits | Thresholds informed by incumbent data, not selected to favor a challenger; unsupported targets remain unratified/evidence-limited, never assumed passed |
| 3. Full pre-release runner and report | Modeling lead + evaluation lead; after 2a/2b | All registered arm adapters, raw/policy/end-to-end comparison, ablations, versioned scorecard outputs and model-card templates | New bilateral + available legacy models replay without production toggles; grader identifies planted defects; CI smoke and larger offline suite produce comparable artifacts |
| 4. Production reporting | Analytics + backend/mobile; health work after 1, quality after 2a | Daily data-quality monitoring, mature weekly quality scorecard, outcome joins, latency and repetition dashboard, model/policy drill-down | Numerators/denominators reconcile to sampled evidence; delivered/viewed/acted are distinct; no provider-send-as-completion; sparse slices visibly ungraded |
| 5. Controlled improvement cycle | Product + modeling + independent reviewer; after 3/4 | Preregistered experiment, staged rollout criteria, final report, promotion/rollback decision | Correct assignment/exposure checked; mature yield plus post-milestone attrition/confirmation guardrails evaluated; adequate power or an explicit inconclusive outcome; no automatic promotion from proxy or transient-interest uplift |

First implementation milestone is an **honest baseline for the current model**, even if several cells are unknown. Do not wait for an elaborate dashboard or acceptance predictor before exposing obvious wrong-direction trades and telemetry gaps. Start with reproducible JSON plus Markdown/HTML readouts; introduce a dashboard only after metric semantics are stable.

The one-time framework bootstrap above precedes the per-model release gates in the playbook. It does not retroactively certify the already-live model. An unresolved behavioral threshold may allow a specifically approved evidence-collection experiment under correctness/quality guardrails; it cannot justify broad promotion or a calibrated acceptance claim. Optional paired-manager stated-intent research is not a prerequisite for the initial baseline.

The first `owner_v2_bilateral` report must specifically inspect: weakest-manager support versus actual responses; personal targeting at fair market terms; tanking RB exception false positives; favored young asset sells; own next-draft pick protection on both sides; first-round pick priority; contender starter gaps; missing-board fallback; minimal 1x1/2x1 packages; repeated headliners; significance exceptions; and what each downstream rule removes. Compare `owner_v1` offline without turning it back on. Separately compare pre/post `73bfa41e` delivery metrics under the same model; do not credit delivery speed to a new constructor.

## 7. Production reporting and statistical safeguards

Default report cadence: near-real-time integrity/availability alerts where already supported; daily telemetry/freshness/latency checks; weekly mature quality report; monthly error review and model-card update; explicit preregistered checkpoints for experiments. Cadence is a design proposal, not a newly scheduled automation.

Slice every metric by model/version/arm, serving policy, surface, source/inbound versus organic, platform, league size, QB format, TEP, starting slots/bench depth, outlook pair, declared/inferred/conflicting outlook, board coverage, value tier, package shape, pick year/type, best-player side, exposure position, generation/cache mode, time lag and calendar phase. Show role-balanced A/B results and the weaker manager, not just the initiator average. Avoid an unreadable full cross-product: declare critical slices and drill into low performers with sample sizes.

Use request/manager and league-cluster summaries so prolific accounts or a huge generated inventory do not dominate. Display micro and macro rates and cluster-aware confidence intervals. Repeated packages and both perspectives of one concept are correlated, not independent observations. Bootstrap entire league lineages/connected groups where appropriate. Record zero-offer and failed requests in request-level denominators.

For prospective causal comparisons, randomize at league or a suitably analyzed connected cluster to reduce interference between counterparties. Multi-league manager spillover remains a limitation. Record assignment separately from exposure and validate balance/sample-ratio mismatch. With few clusters or sparse mutual outcomes, the result may be inconclusive. Pre/post rollout charts are descriptive; season/news, roster changes, exposure and latency can confound them. A two-week episode means time-switch experiments need explicit washout/carryover handling.

Do not use `deck_impressions.propensity` as an experiment probability: current server comments identify it as an ordering multiplier. Off-policy estimators require genuine known logging probabilities and overlapping action support. Deterministic logs and never-presented candidates cannot establish counterfactual acceptance. Add safe randomization only under a separately approved experiment; never relax critical safety constraints to collect labels.

## 8. What success looks like

- A modeling engineer knows the exact rubric, hidden-test rules and release contract **before** tuning.
- Every model/arm can be evaluated independently, with common inputs and explicit policy/configuration versions.
- Every reported offer shows A outgoing, A incoming, B outgoing, B incoming, both package-level judgments, confidence/coverage and evidence links.
- A stronger viewer result cannot hide a harmed counterparty; no giant weighted average conceals a failed dimension.
- We can distinguish bad construction, bad pricing, missing/stale inputs, overaggressive filtering, repetition, delivery failure and lack of counterparty exposure.
- Pre-release gains are verified on locked data and validated after release on real, mature outcomes without moving the grading rules mid-experiment.
- No claim of both-party acceptance probability is made until calibrated and validated; no claim of completion without provider evidence.
- The three-second first-tile objective is measured on a device/production path without quietly reducing candidate coverage or forcing only trivial trades.

## 9. Proposed defaults and remaining ratification

Proceed with a rubric, not an invented universal score cutoff. Proposed defaults are a 14-day episode horizon, 95% uncertainty intervals, first-30 quality reporting, and a future **p95 tap-to-first-action target of three seconds**. The owner specified three seconds; choosing p95 is an additional proposed service-level definition, not an already achieved target. Also report p50/p90/p99, warm/cold and failures.

Before use as a promotion gate, evaluation/product owners must freeze in work package 2b: maximum tolerated loss by critical dimension/segment, required sample size based on observed base rates and meaningful effect size, treatment of legitimate explicit-selection exceptions, fixed eligibility/origin/follow-up rules, fresh-data tolerances per source and retention duration. They must choose these **before challenger tuning and locked-test access**. Until then, historical/current scorecards can be descriptive or “insufficient evidence,” not green by default.

This task has not extracted new user decisions or produced model performance grades. It defines how to build that capability. Current live config was read only to establish the evaluation baseline; private receipt is `/private/tmp/trade-model-scorecard-live-baseline.json`, not a public artifact.

## 10. Source evidence and methodological grounding

Current code references are pinned to the verified deployed revision; they establish implementation, not model effectiveness:

- [Arm registry/routing](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/bakeoff_runner.py#L279), [bilateral construction and support](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/trade_gen_bilateral.py#L1), [shared owner pricing and roster proxy](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/trade_gen_owner.py#L264).
- [Runtime worker/publication](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/server.py), [significance](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/trade_significance.py#L42), [roster adapter coverage](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/backend/trade_roster_adapter.py#L7), [evidence tables](https://github.com/mattmurf77/fantasy-trade-finder/blob/73bfa41e358e8780b823f652cf8388ae209b977d/docs/data-dictionary.md).

The framework adapts established practices; the football rubric and thresholds are our product design, not claims made by these papers:

- Use **Model Cards** to publish intended use, evaluation conditions and limitations for each revision. [Mitchell et al., Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993).
- Use **Datasheets** to document source populations, collection, missingness and allowed use of each benchmark. [Gebru et al., Datasheets for Datasets](https://arxiv.org/abs/1803.09010).
- Use **ML Test Score** as the engineering-readiness checklist: data, model, pipeline and monitoring checks belong alongside accuracy. Adapt to heuristic models too; do not turn its checklist into an acceptance metric. [Breck et al.](https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/).
- Keep measurable objectives, simple baselines, reproducible pipelines and training/serving consistency before introducing more sophisticated models. [Google, Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml).
- Separate ranking quality from probability calibration; test calibrated probabilities on held-out labels rather than relabeling a utility score. No particular neural calibration method is mandated here. [Guo et al., On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599).
- Account for network interference and the power cost of cluster randomization when testing a two-sided product. [Ugander et al., Design and Analysis of Experiments in Networks](https://arxiv.org/abs/1404.7530), [Microsoft Research on tenant-randomized experiments](https://www.microsoft.com/en-us/research/articles/why-tenant-randomized-a-b-test-is-challenging-and-tenant-pairing-may-not-work/).
