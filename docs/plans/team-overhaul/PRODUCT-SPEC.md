# Team Overhaul: Product Specification

See [initiative status](status.md). This is an engineering handoff for the approved core direction and mock interactions, not implementation or release evidence.

Date: 2026-09-06

## 1. Purpose and evidence

Team Overhaul helps a dynasty fantasy football manager make a dramatic change through a coordinated set of trades. The user chooses **Push all in** or **Blow it up**, selects an eligible pool of assets, reviews trade ideas, and chooses a roadmap whose independent trades can all be accepted without double-selling assets. Ranked alternatives let the user continue executing the same roadmap as offers receive responses.

This specification consolidates the original owner brief, explicit follow-up answers recorded in [owner-decisions.md](owner-decisions.md), the `ownerDecision` annotations in [prototype discovery questions](mockups/source/questions.js), and the latest approved mock changes. The owner approved the direction and requested a dedicated project and engineering plan/specifications. The owner subsequently requested the missing feature-entry mock; its proposed placement described below has not yet been approved.

Evidence precedence:

1. The latest explicit owner instruction overrides earlier mock behavior and suggested answers.
2. Explicit decisions in [owner-decisions.md](owner-decisions.md) and [prototype discovery questions](mockups/source/questions.js) resolve the associated discovery questions.
3. The original brief supplies the baseline behavior where it has not been changed.
4. Recommendation text, demo data, and implementation conveniences in the mock are not owner-approved requirements.

**Owner-confirmed** below denotes direct scope or accepted follow-up direction. **Proposed default** denotes a concrete starting point for engineering where a discovery choice remains unanswered. Section 8 preserves the nine remaining choices; it does not reopen decisions already made.

## 2. Terms and hierarchy

| Term | Meaning |
|---|---|
| Asset | A rostered player or a specific owned draft pick. Two first-round picks are different assets when their season, original team, or league differs. |
| Eligible pool | The players and picks the user permits this overhaul to trade away. A selected asset may remain unused. |
| Offer / trade chip | One proposed exchange with one opposing team, with explicit outgoing and incoming assets. The user can like or pass on it. |
| Sell-asset package | A fixed set of outgoing assets within one chosen roadmap, plus its liked alternative offers. A package may contain one asset, several players, players and picks, or—when pushing all in—only draft picks. |
| Priority tier | A user-defined execution rank for alternative offers within one package. Offers in the same tier may be sent together; later tiers are fallbacks. |
| Roadmap | A coordinated overhaul containing a target of **4–5 independent sell-asset packages**, with one eventual accepted trade per package. |
| Alternative roadmap | Another compatible combination of liked trades for the same overhaul. The target is **4–5 roadmaps**. Different roadmaps may regroup the eligible assets. |
| Send batch | The exact offers selected to be submitted together. Ties can make the offer count greater than the number of packages or eventual accepted trades. |

Use this hierarchy consistently in product copy, data contracts, and analytics. The original brief used “package” for both the whole plan and its constituent trades; the implementation must make the level clear. The priority screen uses **Package N of M** for a sell-asset package, not for an entire roadmap.

## 3. Owner-confirmed requirements

### R1. Two decisive outlooks

1. The entry screen asks what the user is trying to accomplish and presents exactly **Push all in** and **Blow it up** as the overhaul outlooks.
2. This feature is for substantial roster changes. It does not introduce an intermediate outlook.
3. Outlook and position settings belong to the overhaul and remain separate from regular trade-finder settings. Starting or editing a roadmap must not silently change the regular finder.

### R2. A user-controlled eligible pool

1. Show the entire roster grouped by position, with draft picks available as a separate asset section.
2. Recommend assets to move using the chosen outlook and team context; show the recommendation clearly enough that the user can review it.
3. Allow the user to select or deselect individual assets. The selected assets form an **eligible pool**, not a requirement to move every selection.
4. Generate outgoing packages only from that pool. An unselected asset cannot be silently added as a sweetener by a reused search or More Offers flow.
5. Allow selected assets to remain unused in a roadmap. Make the assets actually committed to the selected roadmap clear.
6. For Push all in, the user chooses the draft-pick budget. Recommendations must respect that choice and the user's individual pick selections.
7. Push all in must support a package whose entire outgoing side consists of draft picks.
8. Use **Continue** for the asset/target setup CTA. Do not expose prototype-only scenario controls on the product screen.

### R3. Rebuild guidance and exact first-round-pick recovery

1. For Blow it up, emphasize that moving productive players can reduce current production and, when applicable, improve the draft position of a pick the user owns. The handling of unknown or incompatible draft-order rules remains open under D2.
2. Read next-season first-round-pick ownership from the connected league state. The user must not be asked to operate a “Review scenario” toggle in the product.
3. If the user does not own their **original next-season first**, prominently warn that reducing production would not improve a pick they currently own.
4. Include an offer to recover that **exact pick**, identifying its current holder. Acquiring someone else's first-round pick does not satisfy this objective.
5. Highlight **Priority 1: Recover your first** across the overall overhaul, including the relevant asset guidance, recovery offer, selected roadmap, and send summary.
6. This is an **advisory overall execution priority**. Other trades are not blocked; the user chooses when to pursue recovery and may send other offers first.
7. Overall recovery priority is distinct from a package's alternative-offer tiers. Do not interpret “Priority 1: Recover your first” as an automatic forced ordering of every package or as permission to override the user's tier assignments.
8. Production must derive “next season” from the league/season context. The mock's 2027 example is not a hard-coded product rule.
9. A recovery offer is still subject to like/pass review. Do not silently insert an unliked recovery trade into the send batch. If the user passes or recovery cannot be found, retain the warning and recovery objective and offer further review/search without treating an incomplete recovery objective as a complete roadmap. The user can still choose to pursue unrelated already-reviewed offers; recovery is not a prerequisite to their execution.

### R4. Return preferences

1. Position preferences are optional. Recommend target positions based on the user's team and chosen direction.
2. Selected positions guide the overall roadmap as preferences, not per-offer hard filters. Strong compatible offers at other positions may still appear.
3. For Blow it up, let the user choose the balance between draft picks and younger players in the return.
4. Rebuild offers may receive only draft picks.
5. Do not adopt suggested defaults such as “picks-first,” a particular draft-year limit, or an optional strict position setting as approved behavior merely because they appeared in the discovery recommendations.

### R5. Review before composition

1. Present generated offers using the recognizable trade-chip / Find a Trade interaction: explicit send and receive assets, opposing team, and like/pass actions.
2. A like makes an offer available for roadmap composition. A pass excludes that offer.
3. Compose roadmaps exclusively from liked offers; do not fill missing packages with offers the user has not liked.
4. The original flow completes the generated like/pass review before showing roadmaps. Whether to permit an earlier transition when enough compatible likes exist remains open under D3.
5. If there are too few compatible likes, **generate more offers for review and prompt the user to reconsider the eligible asset pool**. A smaller-plan recommendation is not the default substitute for the target overhaul.
6. Further generation must retain relevant decisions and explain what gap the additional ideas address. A regeneration must not quietly reclassify passed offers as liked.

### R6. Alternative roadmaps and compatible packages

1. Target **4–5 independent package trades in each roadmap** and **4–5 alternative roadmaps** for comparison.
2. Within a roadmap, each package uses a distinct set of outgoing assets. One accepted offer from every package must be able to complete without an outgoing asset appearing in two packages.
3. Enforce incoming-asset compatibility as well: separate concurrently actionable packages must not depend on acquiring the same player or exact pick.
4. Alternative roadmaps may regroup outgoing assets. For example, one roadmap may package A + B together while another sells A and B separately.
5. Regrouping must preserve the eligible-pool boundary and compatibility rules. A roadmap is not a genuinely different alternative merely because its display order changed.
6. Let the user compare alternative roadmaps and swap a proposed trade for another liked option. Show the outgoing package to which the change applies.
7. Alternatives **within one package** share that package's exact outgoing asset set. Changing the outgoing set changes the package and requires the resulting roadmap to be checked again.
8. Do not claim that arbitrary accepted-trade sequences are executable solely because asset IDs are disjoint. Roster limits and any supported dependencies require validation; the broader dependency policy remains open under D6.

### R7. One-package-at-a-time priority editing

1. Present one sell-asset package per priority page.
2. Show that package's outgoing assets, its liked alternative offers, and its progress within the roadmap, such as **Package 2 of 4**.
3. Use **drag and drop into priority tiers**, consistent with the existing Tiers-page interaction, to set offer order.
4. Moving an offer between tiers changes the order in which the user intends to pursue it. Do not imply that a visual order among offers within the same tier gives them separate execution ranks.
5. Allow several offers in the same tier. Those offers may be sent at the same time for the same outgoing assets.
6. Provide Back and Continue between packages, leading to the final send summary after the last package.
7. Provide a non-drag interaction for accessibility and touch/keyboard reliability. The approved mock's Move control and keyboard movement demonstrate an acceptable approach; the final client must meet its platform accessibility requirements.

### R8. Explicit bulk-send payoff

1. The summary shows the chosen roadmap and the exact offers in the next send batch, including counterparties, outgoing and incoming assets, package membership, and priority tiers.
2. Distinguish **number of offers sent**, **number of packages**, and **maximum number of accepted trades**. Equal-priority alternatives can increase the first number without increasing the latter two.
3. Provide the **Send all offers** payoff for the reviewed batch on supported production integrations.
4. If a package has multiple offers in the tier being sent, explicitly warn that they are going out together on a **first come, first served** basis. The offers reuse that package's outgoing assets, so only one can complete.
5. Highlight exactly which packages contain that race. Do not show only a generic warning disconnected from the affected offers.
6. Preserve the overall “Priority 1: Recover your first” advisory when applicable. The summary must not suggest that recovery blocks the send action.
7. Refresh and validate ownership/availability before submission. A preview is not proof that an asset is still tradable at the moment of sending.
8. The prototype's action remains **Simulate send all** and submits no platform trades. It is not evidence that production bulk sending, withdrawal, or synchronization has been implemented.

### R9. Resume, negotiate, and send fallbacks manually

1. Persist the roadmap so the user can revisit it as the league platform responds to offers.
2. Keep the chosen outgoing packages, liked alternatives, tier priorities, sent offers, and observed outcomes understandable when the user returns.
3. Following a decline, **wait for the user** before sending another offer. The user must have time to negotiate and decide how to proceed.
4. Present the next eligible tier and its offers for review and manual sending. Revalidate them before submission.
5. Automatic fallback progression is a possible future enhancement, not the default and not a committed first-release requirement.
6. When a package's offer is accepted, mark that package complete and prevent its overlapping alternatives from being sent. Clearly distinguish local invalidation from confirmed cancellation of any already-pending platform offers.
7. Show completed work and the remaining packages. Do not imply that accepting one trade completes the entire overhaul.
8. Handling pending offers, counters, external roster changes, and the exact resume entry point remains bounded by the open choices in Section 8.

### R10. Related future feature is separate

The owner also requested a subsequent **First come, first served** feature: for one asset the user wants to sell, collect liked trade chips and send all offers at once, with one liked offer per opposing team. Track that feature separately in the project's next-work memory. It is not a reason to broaden this overhaul implementation into an independent launch of the single-asset feature. Its one-offer-per-team rule does not resolve the separate roadmap counterparty question D4.

## 4. Product flow and screen contracts

| Step | Screen and primary action | Required content / result |
|---|---|---|
| 0 | Feature entry → Team overhaul / Resume overhaul | Proposed placement: a Team overhaul card near Team Review on the current Trades route, whose visible label is **Acquire**. A saved-plan variant resumes an overhaul. The entry mock is requested; this exact placement and resume policy remain proposed. |
| 1 | Outlook → Choose my trade pool | Push all in or Blow it up; isolated roadmap settings; no intermediate outlook. |
| 2 | Eligible assets → Continue | Entire roster by position; pick section; recommendations; individual selection; user-defined all-in pick budget; rebuild return balance; league-derived ownership guidance. |
| 3 | Target preferences → Continue | Recommended positions; optional selection; preferences apply across the roadmap. This can be part of the setup sequence without forcing a position choice. |
| 4 | Trade-chip review → Build roadmaps | Like/pass each generated offer; show progress and compatible-like coverage; request more ideas and pool reconsideration when coverage is insufficient. |
| 5 | Roadmap comparison → Set priorities | Target 4–5 alternative roadmaps, each with 4–5 compatible packages; show committed outgoing assets; allow swaps and regrouped alternatives. |
| 6 | Package priorities → Continue | One package per page; exact outgoing asset set; liked offers moved into tiers; ties visibly mean concurrent offers. Last package proceeds to summary. |
| 7 | Final summary → Send all offers | Exact batch and counts; package compatibility; affected first-come races; recovery advisory; actionable availability problems. |
| 8 | Saved roadmap → Review / Send next | Completed, pending, declined and stale offers; remaining packages and tiers; manual fallback after responses; negotiation remains possible. |

The production flow contains no review-document question panels, sample-like shortcuts, audio notebook, simulated accept/decline controls, or ownership-scenario selector. Those controls exist only to support product discovery and do not form the app requirements.

## 5. Non-negotiable product invariants

1. **Pool integrity:** every outgoing asset in every generated or sent offer is in the user-approved eligible pool and is currently owned/tradable when sent.
2. **Preference isolation:** roadmap settings do not silently mutate regular finder settings.
3. **Like provenance:** each composed offer has an affirmative user like; review shortcuts are not production behavior.
4. **Cross-package compatibility:** outgoing and incoming asset commitments do not overlap across concurrently actionable packages. All tied alternatives in an active tier must be checked against the other packages, not just one featured alternative.
5. **Intentional within-package competition:** equal-priority alternatives may overlap in outgoing assets only because they are competing alternatives within that same package. They are never counted as multiple independently completable trades.
6. **One accepted offer per package:** an accepted offer consumes the package's outgoing assets and invalidates its other alternatives. A second send cannot reuse those assets.
7. **Exact-pick identity:** recovery refers to the user's original next-season first, not a generic first, an acquired first from another team, or a different year.
8. **Advisory recovery:** overall Priority 1 remains visible but does not impose a recovery-before-other-trades gate.
9. **Manual progression:** a decline alone never triggers a new external offer.
10. **Honest counts and readiness:** do not pad a roadmap with incompatible, passed, unreviewed, duplicate, or unavailable offers to reach 4–5 trades or 4–5 alternatives.
11. **No silent state claims:** sent, accepted, declined, withdrawn and cancelled are distinct outcomes. The app must not claim a platform mutation succeeded merely because it updated local state.
12. **Legible execution:** changing a roadmap, regrouping assets, changing tiers, or swapping an offer cannot silently alter already-sent offers. Revalidation and a visible review are required for the changed commitments.

## 6. Product acceptance criteria

| ID | Scenario | Acceptance criterion |
|---|---|---|
| AC1 | Start an overhaul | The user sees the two extreme outlooks. Choosing either affects this roadmap and leaves regular finder settings unchanged. |
| AC2 | Change the pool | A deselected player/pick never appears on an outgoing side. A selected asset may remain unused without invalidating an otherwise complete roadmap. |
| AC3 | Push all in with picks | The user can define their spending allowance, select owned picks, and review a liked candidate whose outgoing side contains picks only. No unselected pick is silently added. |
| AC4 | Blow it up with own first | The app derives ownership from the league and presents productive-player guidance without a product “Review scenario” control. Draft-position language respects the selected rule policy. |
| AC5 | Blow it up without own first | The exact missing pick and holder are identified; a recovery offer is included for review; overall Priority 1 is visible through summary; the user can still send unrelated offers first. |
| AC6 | Pass on the recovery offer | The passed offer is excluded from composition/sending. The recovery objective and warning remain visible, with a route to more recovery ideas. |
| AC7 | Choose return preferences | Rebuild return balance is user-controlled, positions remain optional preferences, and pick-only rebuild returns are supported. |
| AC8 | Insufficient compatible likes | The flow produces additional ideas for review and prompts pool reconsideration. It does not silently use unliked offers or default to presenting a smaller plan as the requested overhaul. |
| AC9 | Complete a roadmap | A target-size roadmap has 4–5 distinct outgoing packages. A choice of one active offer per package has no conflicting outgoing or incoming assets. |
| AC10 | Compare alternative roadmaps | The user can compare 4–5 supported combinations. A valid alternative can combine A + B where another separates them; every combination respects the pool and compatibility checks. |
| AC11 | Rank package alternatives | Only one package is edited per page. Drag/drop and an accessible alternative both move an offer into a tier, persist the tier, and preserve the package's outgoing set. |
| AC12 | Tie two offers | With four packages and a tie of two offers in one package's active tier, the summary shows five offers and at most four accepted trades, and names the two competing offers as first come, first served. |
| AC13 | Send the batch | The exact reviewed valid batch is submitted through supported capabilities. Partial, failed or unconfirmed submissions are represented accurately; the app does not mark the entire batch sent by assumption. |
| AC14 | Receive a decline | No next offer is automatically submitted. The user can review the next eligible tier and manually send after negotiation and availability checks. |
| AC15 | Receive an acceptance | That package is complete, its outgoing assets cannot be reused, and overlapping alternatives become unavailable. Any provider withdrawal/cancellation result is tracked honestly. |
| AC16 | Resume later | The saved roadmap preserves completed work, priorities and offer outcomes and exposes the remaining alternatives. Refresh behavior follows the selected policy in D8. |
| AC17 | Ownership or roster changes | A stale preview cannot send an asset that is no longer available. The user sees which offers or packages need attention before further submission. |
| AC18 | Inspect production UI | Setup uses Continue; the priority flow uses one package per page and tier movement; prototype-only controls and fabricated league/value data are absent. |

These criteria describe required behavior to implement and verify. Passing prototype interaction checks does not establish these production criteria, provider capabilities, or release readiness.

## 7. Proposed engineering defaults pending unresolved choices

The following defaults make an initial implementation plan concrete. They are **proposals**, not additional owner approvals, and should remain identifiable in engineering decisions.

1. Keep the chosen roadmap's package boundaries stable during execution; swaps within a package only select another liked offer with the same outgoing set. Any regrouping after sends requires a separately reviewed revision of the unexecuted work.
2. Use a bounded review batch and retain the original finish-review transition for the first implementation; keep batch size configurable rather than treating the discovery suggestion of 20–30 chips as a fixed requirement.
3. Validate both each offer and the combined active batch, including all tied alternatives, for asset availability and applicable roster limits. Do not introduce trades that rely on assets the user hopes to receive from another still-pending package in the initial batch.
4. While any offer in a package is pending, hold later tiers until the user explicitly resolves or withdraws the earlier offer. Show status and age; do not introduce automatic timeouts or advancement.
5. Preserve completed and pending work when inputs change. Flag affected unexecuted offers as stale and require review before they become sendable again.
6. Use a single executing roadmap per league as an initial simplification while allowing stored alternatives for comparison. This is not a confirmed limit and must remain changeable until D9 is resolved.
7. Reuse established Chalkline components and native platform accessibility patterns. Use drag/drop tiers plus an accessible movement control; do not couple the production feature to the standalone HTML mock's implementation.
8. Put a **Team overhaul** entry card near **Team Review** on **Acquire**, the visible label of the current Trades route and active merged trade-builder surface. Show a **Resume overhaul** variant when the user has a saved active plan. This newly drafted entry is a proposed placement, not a previously approved screen change; it also supplies a concrete proposal for D9.

## 8. Nine unresolved discovery choices

> **Resolved 2026-09-07.** The owner confirmed D2–D9 as proposed and revised D1: sending is offered on Sleeper, MFL and ESPN (ESPN players only). See [owner-decisions.md](owner-decisions.md) § 2026-09-07 and [D-188](../../../living-memory/DECISIONS.md). The table below is retained as the discovery record.

The nine resolved choices are pool semantics, regrouping, own-first recovery ordering, rebuild-return balance, manual fallback, insufficient-like handling, position-preference semantics, user-defined pick budget, and settings isolation. The following nine remain unanswered in the recorded evidence. They are planning decisions to retain, not a new question set for the owner.

| ID / discovery key | Unresolved choice | Proposed default for planning; not owner-confirmed |
|---|---|---|
| D1 `launch_scope` | First-release clients and league platforms; supported send/status capabilities. | Keep the product and data model platform-neutral. Sequence the first end-to-end integration according to verified capabilities; do not state that iOS/Sleeper has been selected solely because it was recommended. |
| D2 `draft_order_rules` | Guidance when league draft-order rules are unknown or do not reward reduced production. | State a draft-position benefit only when supported by known rules; otherwise explain uncertainty while preserving the rebuild and ownership guidance. |
| D3 `review_completion` | Fixed-deck completion, early completion after sufficient compatible likes, or user-controlled batches. | Follow the original complete-review flow with a bounded, configurable batch. Offer additional review when composition lacks coverage. |
| D4 `same_counterparty` | Multiple independent offers to one opposing team versus a one-active-offer limit. | Prefer distinct opposing teams; require combined-fit and roster validation before allowing several concurrent trades with one team. Do not infer this policy from the separate future single-asset feature. |
| D5 `pending_offers` | Hold behavior, user-selected timeouts, and withdrawal/advance behavior for unanswered offers. | Hold later tiers; show age and let the user explicitly wait or withdraw and advance where supported. Never advance silently. |
| D6 `combined_roster` | Strict acceptance-order independence versus clearly staged/dependent trades. | Make the first batch executable without dependencies on earlier acquisitions; validate applicable combined roster constraints. Keep any future staged plan explicit and separate. |
| D7 `counteroffers` | In-roadmap counter review, platform-only negotiation, or a counter becoming a new liked alternative. | Present the counter for user review when retrievable; recheck changed assets against the remaining roadmap before promoting or acting on it. Platform-specific gaps must be visible. |
| D8 `roadmap_refresh` | Refresh affected packages, regenerate all unexecuted work, or retain until an explicit rebuild. | Preserve completed/pending work, flag stale alternatives, and refresh affected unexecuted packages with visible review. |
| D9 `resume_entry` | Trades entry versus dedicated Roadmaps view; one or multiple saved/executing plans. | Team overhaul / Resume overhaul card near Team Review on **Acquire** (the current Trades route), saved alternatives for comparison, and one executing roadmap per league for the initial implementation. This placement is newly proposed. |

## 9. Delivery boundaries and mock limitations

This feature builds on the product concepts of Guided Team Outlook, More Offers and trade-chip review. Their existing behavior and interfaces must be inspected before reuse; the specification does not claim that any existing backend already supports constrained generation, global composition, saved roadmaps, bulk sending, or response synchronization.

The approved HTML is a reviewable interaction reference. It uses a fictional roster and league, a small fixed set of asset groups and offers, browser persistence, and simulated response controls. It does not demonstrate arbitrary asset regrouping, actual trade valuation, a production-compatible 4–5-roadmap optimizer, real ownership synchronization, or provider execution. Those are implementation work, not completed capabilities.

Engineering completion requires implemented and verified generation constraints, composition compatibility, persistence, supported provider actions and state transitions, accessible production UI, and the repository's applicable release checks. This document alone does not authorize treating a prototype, build, or plan as a deployed release.
