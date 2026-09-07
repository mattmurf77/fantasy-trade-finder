# Team overhaul — engineering specification

See [initiative status](status.md). This is a proposed implementation contract for the approved discovery direction. No product code, API, database migration, provider integration, or release is established by this document.

## 1. Evidence baseline and scope

Read on 2026-09-06: repository `AGENTS.md`, `README.md`, the generated session brief, `docs/agent-workflow.md`, the local owner decision record, and the code/reference surfaces cited below. Checked-out code: `801e00ea6ee33f7a5ae12d8c7474a9b48cc0c8f3` on `codex/team-overhaul-discovery`. At inspection, the checkout had the earlier task’s modification to `living-memory/NEXT.md`; this code-map review did not alter source.

The refreshed remote is newer in an important area: `origin/main` at `0e3d6b70`, **Construct owner-led trades before market terms (#285)**. Its owner constructor, route integration, and mobile attribution changes were inspected with `git show` / `git diff`, without changing the checkout. Implementation must start from refreshed main and reconcile these newer seams. The inspected checkout is a discovery baseline, not a claim about current deployed behavior. Source line numbers below refer to the checkout unless explicitly marked **remote main**.

The feature owns a durable plan that starts with an eligible outgoing asset pool, gathers likes on concrete offers, assembles alternative overhauls, lets the user rank fallbacks within each sell group, sends a selected round of offers, and survives platform responses and app restarts. It must preserve the regular finder's preferences, rankings, routing, and attribution behavior.

## 2. Inspected integration map

| Concern | Inspected current surface | Reuse boundary / required addition |
|---|---|---|
| Entry and navigation | [TabNav.tsx](../../../mobile/src/navigation/TabNav.tsx), L429–496 and L749–755: Acquire is the Trades tab; `TradesHome` mounts `TradesScreen`; `TeamReview` is in that stack. `TradeFinderHubScreen` is explicitly unrouted. | Add the proposed entry to the current Acquire landing near Team Review (placement to confirm) and a resumable plan entry. Do not revive the old hub. Use existing explicit back controls. |
| Guided outlook and position UI | [TradeDnaSheet.tsx](../../../mobile/src/components/TradeDnaSheet.tsx), L84–99: four outlook cards; L397–439 reads/writes league preferences. [server.py](../../../backend/server.py), L19198–19245 persists the session user's league outlook and positions. | Reuse visual primitives and wording patterns, with exactly two overhaul choices. Build a plan-scoped controller; mounting the existing saving sheet unchanged would overwrite regular finder settings. |
| Team assessment | [team_review.py](../../../backend/team_review.py), `build_team_review` at L522; [trade_service.py](../../../backend/trade_service.py), `infer_team_outlook` at L3887. The latter deliberately never infers extreme outlooks. | Read explanatory signals, depth and position needs to suggest assets/targets. User explicitly confirms the extreme outlook. Do not infer consent to an all-in or blow-up plan. |
| More Offers | [ShopAssetScreen.tsx](../../../mobile/src/screens/ShopAssetScreen.tsx) mounts [ShopOffersBody.tsx](../../../mobile/src/components/ShopOffersBody.tsx); [trades.ts](../../../mobile/src/api/trades.ts), L292–425 describes `POST /api/trades/asset-ideas`. | Reuse card presentation, offer paging, position controls and actual-view handling. This endpoint is a single pinned-asset, consensus-oriented grouped search on the checkout; its position filter can be a hard candidate constraint. An overhaul's soft position preference and eligible pool require a separate search context. |
| Fixed give-side search | [trade_service.py](../../../backend/trade_service.py), L5926 onward: `generate_fair_packages`, with exact `give_player_ids`, shared `eval_consensus_package`, and 1–3 receive assets from one partner. | Useful exact-sell-group search seam. Do not confuse an exact give anchor with the full eligible pool. Preserve common valuation units and rules. |
| New owner-led construction | **Remote main** `backend/trade_gen_owner.py`: `_Search`, `generate_owner_trades`, `evaluate_owner_trades`; `backend/server.py` L14094 / L14168 / L14289: `_owner_generation_context`, `_owner_cards_valid`, `_owner_selected_ideas`. ADR-019 describes owner interests choosing assets before market pricing. | Integrate against this newer constructor/context where appropriate, preserving historical controls. It accepts explicit outlook, manager preferences, pins, and `exact_give`; it does not establish a durable overhaul, arbitrary eligible-pool contract, or whole-plan assembly. Never simulate eligibility by deleting non-selected players from full-roster context. |
| Trade chips and signals | [TradeCard.tsx](../../../mobile/src/components/TradeCard.tsx), [FeaturedTradeWindow.tsx](../../../mobile/src/components/FeaturedTradeWindow.tsx), [shared/types.ts](../../../mobile/src/shared/types.ts) L158 onward. **Remote main** adds `model_arm`, `generator_version`, `preserve_server_order`, selection coverage and recommendation rank, plus `useSelectedOfferSignals.ts` and `offerExposure.ts`. | Preserve exact offer identity and private evidence boundaries through review, swap, priority and send. User priority is execution order, not a mutation of experimental recommendation order. A modified offer cannot borrow an original impression. |
| Priority drag/drop | [TiersScreen.tsx](../../../mobile/src/screens/TiersScreen.tsx), L695–720, L810–872, L1004–1022, L1387 onward: one `DraggableFlatList`, header-defined zones, empty drop targets, long-press, haptics and accessibility move actions. | Reuse the interaction pattern for one sell-group page at a time. Create a priority model independent of player tiers and `/api/tiers/save`; equal priority is a deliberate tier membership, not a tie in visual row order. |
| Roster safety | [trade_roster.py](../../../backend/trade_roster.py), `assign` L51, `_team_result` L144, `evaluate` L208; [trade_roster_adapter.py](../../../backend/trade_roster_adapter.py), `build_context` L7. Two-sided, full-roster assignment; FLEX cannot reuse a player; picks cost no active roster slots. Unknown data remains unknown. | Extend or compose a plan evaluator over all affected teams and possible execution subsets. Existing one-trade checks do not prove an entire overhaul. Current safety policy also protects usable depth; do not remove it globally to produce more rebuild offers. |
| Outlook utility | [trade_outlook_utility.py](../../../backend/trade_outlook_utility.py), L19 and L61. Explicit outlook and provenance are separate from eligibility; dynasty value is not projected fantasy production. | Evaluate combined before/after rosters with the plan's explicit outlook. Rebuild-return preference needs its own declared, versioned objective input; do not fake projected points from market value. |
| Generation isolation | [server.py](../../../backend/server.py), `_TradeExecutionContext` L6886 / `_capture_trade_execution` L6905. This is explicitly an in-process, non-durable seam. | Capture immutable, serializable plan inputs; bind all asynchronous work to plan revision, account, league and format. Never resolve a completed job from whichever league happens to be active later. |
| Pick identity and ownership | [database.py](../../../backend/database.py), L1316–1360: concrete `pick_id`, league, season, round, original roster/user, current owner and `source`; [server.py](../../../backend/server.py), `/api/league/picks` L12257. | Preserve concrete identity and ownership provenance. Pricing availability or a user-asserted row does not prove the platform can send a pick. Own-first recovery is an identity lookup, not a valuation-tier lookup. |
| Actual sends | [server.py](../../../backend/server.py), `/api/trades/propose` L17667; `/api/trades/propose-mfl` L29797; `/api/trades/propose-espn` L30269. Existing mobile send helpers and buttons supply authentication/reconnect flows. | Reuse provider write functions below route level after shared validation. Add a durable batch coordinator; do not loop UI buttons or make server requests to its own routes. Retain verification and server-authoritative team/platform binding. |
| Pre-send validation | [server.py](../../../backend/server.py), `/api/trades/validate` L29324: Sleeper/MFL data checks and warnings. [sendInSleeper.ts](../../../mobile/src/api/sendInSleeper.ts), L227 catches failures and returns `checked:false`. | A best-effort advisory cannot certify all-compatible bulk sending. A new prepare operation must distinguish fresh validated, blocked, and unknown; unknown must not display a green guarantee. |
| Existing send ledger | [database.py](../../../backend/database.py), `trade_proposals` L553–608 and `save_trade_proposal` L6469 onward; [server.py](../../../backend/server.py), `_record_trade_proposal` L5665. Confirmed sends persist their exact final terms. | Link execution attempts to the existing confirmed-proposal record. It is not an intent/outbox table or a cross-request provider-send lock. Sleeper's route explicitly mints a fresh event ID per client retry at L17792 onward. |
| Existing local queue | [useTradeQueue.ts](../../../mobile/src/state/useTradeQueue.ts): per-user AsyncStorage; `sendAll` opens each Sleeper URL with a 500 ms stagger and then clears the queue. | Do not use this as the overhaul executor or durable status ledger. Opening a platform URL does not prove an offer was sent. |
| Platform status | [sleeper_trades_service.py](../../../backend/sleeper_trades_service.py), L1–20 captures completed public transactions only. [server.py](../../../backend/server.py), `/api/mfl/pending-trades` L30141 and `/api/trades/respond-mfl` L30020 provide MFL pending and response/revoke routes. | Add a capability-aware reconciliation layer. Sleeper's `reject_trade` exists in [sleeper_write.py](../../../backend/sleeper_write.py) L405, but the inspected route inventory does not expose a supported full pending/revoke lifecycle. A feasibility memo is not an implemented adapter. |
| Misleading status names | [server.py](../../../backend/server.py), `/api/trades/status` L14115 polls generation jobs; [trade_service.py](../../../backend/trade_service.py), `get_pending_trades` L7678 means undecided cards. | Neither is a remote pending-offer feed. Keep candidate review states separate from provider execution states. |

## 3. Product rules encoded as domain rules

1. **Overhaul** is the user's durable planning session. **Roadmap** is one alternative full plan. **Sell group** is an exact outgoing asset set within that roadmap. **Offer** names both teams and exact outgoing/incoming assets. Alternative roadmaps may partition the eligible pool differently; alternatives within a sell group keep its outgoing set fixed.
2. A selected asset is available to use, not required to leave. Give-side candidates must be nonempty subsets of the plan's selected pool, including every filler or sweetener. The search cannot add an unselected player or pick to finish a deal.
3. The user chooses `push_all_in` or `blow_it_up`. The internal evaluator may map these to existing `championship` / `jets` utility semantics through a versioned adapter. No regular league preference is written. Existing rankings remain valuation inputs, not a plan-setting persistence target.
4. Position targets are soft preferences. Rebuild pick-versus-youth preference and all-in pick budget are explicit user inputs, not hidden age or draft-horizon defaults. Use concrete selected pick IDs plus any displayed user-set year/round/count limits; every generated plan must stay within them. No pick outside the selected pool is spendable.
5. Pick-only outgoing offers are supported for all-in, and pick-only incoming offers for blow-it-up. Both sides must still be nonempty and represent concrete owned assets. FAAB, cash, conditional assets and multi-team trades are outside this contract.
6. Aim for 4–5 compatible sell groups per roadmap and 4–5 meaningfully different roadmap choices. These are targets, not a license to duplicate offers, fake supply or claim feasibility. Insufficient compatible likes returns to generated review and an asset-pool reconsideration prompt. Do not default to a smaller recommended overhaul.
7. If the manager lacks their own following-season first, recover that exact original-franchise pick in every complete recommended roadmap when a compatible liked recovery offer exists. Prominently label its group **Priority 1: Recover your first**. This is advisory ordering across the overhaul; it does not block other sends. It is separate from priority tiers of competing offers for a sell group.
8. When recovery is unavailable, disliked, untradeable, stale or otherwise unresolved, show that honestly and regenerate appropriate candidates. Do not substitute someone else's first, manufacture an offer, or silently mark the requirement satisfied. An explicit decision to proceed with other selected offers remains possible; the roadmap continues to disclose recovery as unresolved.
9. Priority tiers are integer ranks, with rank 1 before rank 2. Offers in the same tier may be dispatched together for the same sell assets. They are **mutually exclusive alternatives**: one winner per group. The summary must state which offers race, how many real offers will send, and the first come, first served behavior.
10. After a decline, expiry or counteroffer, never automatically dispatch the next tier. Show the remaining options and allow negotiation. Optional automatic fallback is future work. Refreshing status also never sends an offer.

## 4. Proposed typed contracts and persistence

Everything in this section is new engineering design, not an inventory of existing database tables or endpoints. Use SQLAlchemy Core and the repository's established migration process. The exact table decomposition can change while these contracts remain intact.

```ts
type AssetRef = {
  key: string;                 // server canonical identity, never a display label
  kind: 'player' | 'pick';
  platform: string;
  leagueId: string;
  playerId?: string;
  pick?: { pickId: string; season: number; round: number;
           originalRosterId: string; source: 'platform' | 'user' };
};

type OverhaulSettings = {
  outlook: 'push_all_in' | 'blow_it_up';
  eligibleGive: AssetRef[];
  preferredReceivePositions: string[];
  rebuildReturnPreference: { kind: 'picks' | 'young_players' | 'mixed' } | null;
  pickBudget: { eligiblePickKeys: string[]; limits?: UserChosenPickLimits } | null;
  targetTradeCount: 4 | 5;
};

type Offer = {
  offerId: string;
  exactPackageHash: string;    // platform+league+both roster identities+sorted sides
  sellerRosterKey: string;
  counterpartyRosterKey: string;
  give: AssetRef[];
  receive: AssetRef[];
  generationRevision: number;
  snapshotId: string;
  presentation: PublicTradeCard;
  provenance: { generatorVersion: string; modelArm?: string;
                impressionId?: string; basis: string };
};

type SellGroup = {
  groupId: string;             // scoped to a roadmap revision
  giveKeys: string[];
  priorities: { rank: number; offerIds: string[] }[];
  advisoryExecutionRank: number;
  reason: 'recover_own_first' | 'outlook_move';
};

type RoadmapVersion = {
  roadmapId: string;
  version: number;
  overhaulId: string;
  settingsRevision: number;
  snapshotId: string;
  groups: SellGroup[];
  combinedImpact: ImpactWithSourceAndUnknowns;
  compatibility: ValidationReceipt;
  recovery: RecoveryRequirement;
};
```

`PublicTradeCard`, `UserChosenPickLimits`, `ImpactWithSourceAndUnknowns`, `ValidationReceipt`, and `RecoveryRequirement` are proposed supporting types, not existing exports. Define and version them in implementation; the API must not expose private counterparty rankings or frozen generator evidence.

Suggested durable records:

| Record | Minimum durable fields and integrity |
|---|---|
| `overhauls` | Owner account/user, platform, league, controlled roster/franchise identity, lifecycle, active settings revision, selected roadmap version, created/updated times. Authorize every read/write from the session; never accept an owner ID as proof. |
| `overhaul_revisions` | Immutable settings JSON and schema version, full league/roster/ownership snapshot reference, source/freshness metadata, scoring format, generator/config versions and input hash. Revision comparison on edits prevents stale clients overwriting new choices. |
| `overhaul_generation_runs` | Revision-bound queued/running/completed/failed state, deterministic seed, bounded-search limits, batch/cursor, exclusion/decision revision, supply diagnostics and errors. Durable results do not depend on the existing in-memory deck cache. |
| `overhaul_offers` and `overhaul_decisions` | Exact package identity, public display snapshot, private generation evidence reference, like/pass/undo events with stable idempotency IDs and revision. Decision identity includes partner and both sides; repeated generation must not resurrect a passed exact offer or lose a like. |
| `overhaul_roadmap_versions` | Immutable grouping, chosen alternative ordering/tiers, incoming/outgoing identity unions, recovery requirement, combined roster assessment and validation revision. Edits create a new version; sent offers stay attached to their original version. |
| `overhaul_batches` / `overhaul_attempts` | Explicit confirmed offer list and summary hash, intent idempotency key, exact request hash, actor, prepare snapshot, per-offer lifecycle, provider transaction handle if known, transport outcome, confirmed proposal foreign key, timestamps and reason codes. |
| `overhaul_reservations` | Platform+league+seller-roster+asset key bound to the active execution group and its shared race ID. Claim every outgoing key transactionally, in stable order; uniqueness applies across devices and all active overhauls. No active ownership lock is inferred from a UI state. |
| `overhaul_execution_events` | Append-only history of provider observations and manual status assertions with provenance, previous/new state, observed/event times and confidence. Materialized status may update, but history must remain available for repair. |

Persist settings, current page/group, reviewed-offer position and draft priority edits so the user can resume. Server state is authoritative; local cache improves responsiveness only. Sign-out and league-switch clear visible plan state and cancel or detach requests; they must not corrupt or move background results into another account or league. Expired authentication returns a recoverable reconnect state. Season rollover must show the old league/season explicitly and must not silently retarget pending offers to a new league.

## 5. Recommendation and assembly pipeline

### Capture and selection

Capture one full-roster context with rules, ownership, current league season, format, values, availability, declared/inferred counterpart intent and provenance. Keep the entire roster available for post-trade evaluation while separately applying `eligibleGive` to every outgoing candidate. Reading existing shopping/untouchable preferences can inform initial recommendations, but must not cause hidden writes to regular finder settings. Any conflict between an explicit plan selection and a saved preference must be resolved visibly and only within the plan.

For own-first recovery, resolve the season from the league's football-season context, normally `league_season + 1`, not from the device's calendar year or a rendered label. Resolve the user's controlled original roster/franchise including co-ownership; then match exact league, original roster, target season, round 1 and current holder. Keep `owned`, `missing_with_known_holder`, `unknown`, `unsupported`, and `not_yet_available` distinct. An empty or failed sync is not proof that the user traded their first away. User-asserted ownership may inform a labelled planning view but is not platform-send authority.

Recommend productive players to move for a blow-up, with copy explaining the potential draft-position benefit when their own first is held. The benefit depends on league draft-order rules (for example standings versus potential points); do not claim a specific future slot or guaranteed benefit. Attach the known rule or state that it is unknown. This does not alter lineup-setting behavior.

### Candidate generation and review

Generate a bounded mixture of outgoing subsets, partners and return profiles. Include an explicit targeted recovery search against the actual first's holder. Reuse shared pricing and the refreshed owner's constructor, preserving the user's full-roster and explicit plan context. Do not pass the complete selected pool as `exact_give`, force every selected pin into a deal, or mutate cached session outlook to impersonate the plan.

Honor existing package fairness, asset validity, source, counterparty ownership and model-evidence rules. Audit legacy positional/roster gates against the approved overhaul behavior: productive sell-offs may reduce starter value, but legal lineup eligibility, ownership and true platform constraints stay enforced. Quality/backup preferences must not silently become a new hard rule that makes an intentional rebuild impossible; any plan-scoped change to existing protection policy needs a documented ADR and independent cases. Never disable global engine guards for this feature.

Each displayed candidate has an exact package hash, provenance and a stable decision key. Likes are plan-specific assembly input; they are not remote sends. Route signal attribution through the existing validated exact-package machinery, with a new registered source where necessary. Explicitly determine whether roadmap pass/like updates personal ranking signals under existing policy; do not accidentally trigger ordinary swipe learning merely because the same visual chip is reused. Preserve real viewed versus prefetched distinctions and true Undo semantics.

### Compatibility search

Build the roadmap from liked, current, eligible offers, partitioned by exact outgoing-set identity. Use a bounded search (beam search or integer/set-packing solver with deterministic ties) over groups and alternatives. Performance caps, diversity penalties and objective weights are versioned configuration; no arbitrary acceptance probability should be inferred from a match score.

For independent groups `g != h`, require all of the following:

- `give(g) ∩ give(h) = ∅`; all give assets are owned at the captured baseline and included in the eligible pool. No offer depends on first receiving an asset from another offer.
- For any alternatives that can be chosen across the two groups, incoming sets do not collide, both counterparties own their outgoing assets, and no asset is asked to move twice. It is insufficient to check only outgoing duplicates or the currently fronted cards.
- Every group alternative uses exactly the group's give set. Different give sets require a changed roadmap/grouping version and a fresh whole-plan check, not an in-place fallback swap.
- Evaluate the combined before/after roster for the user and each affected counterparty, including multiple offers to one counterparty. Reject self-trades, duplicate identities, hidden extra assets, and both-side overlap.
- Validate intermediate execution as well as the final union: for 4–5 groups, enumerate acceptance subsets and bounded combinations of alternatives, or prove equivalent conservative constraints. No arbitrary acceptance order may require an unacknowledged prior trade, drop, unavailable reserve slot, or asset transfer. Share/cap alternative sets so this Cartesian search remains bounded; never skip constraints because the budget ran out.
- At send time, include already active offers from this and other plans in the collision check. A reservation protects only offers routed through this system; fresh provider ownership/status checks are still necessary for external actions.

Current `trade_roster.evaluate` is two-sided and includes quality/depth rules alongside legality, so a new whole-plan adapter must explicitly separate platform legality, known coverage, soft outlook utility and unresolved observations. Picks never consume player roster slots. Unknown rules/availability cannot be relabelled safe. If a platform permits a temporary roster overflow, distinguish “proposal allowed” from “roster ready to use”; list explicit user-owned follow-up cuts and their timing rather than silently dropping players. An overhaul advertised as independently executable must pass the applicable intermediate/final constraints or visibly require prerequisites.

Rank complete feasible plans by combined outlook benefit, stated return/position preference, reasonable terms and meaningful diversity. Alternative roadmaps must differ materially in outgoing grouping and/or desired returns; avoid presenting five permutations as five plans. A swap is a whole-plan compatibility action and reports why a candidate cannot fit the other groups.

If no set of 4–5 compatible groups exists, return structured supply reasons (insufficient reviewed likes, overlapping sells, competing incoming assets, no return supply, first recovery unresolved, roster limitation, stale ownership, budget restriction). Generate another bounded batch and prompt the user to re-review their eligible asset pool. Exhausted search should be explicit and actionable, never an endless spinner or silent smaller-plan fallback.

## 6. Proposed API surface

These paths are **new proposals**. They are not current endpoints, and no clients should call them before implementation. Path names can follow the final repository convention without changing behavior.

| Proposed route | Request / behavior |
|---|---|
| `POST /api/overhauls` | Create a plan scoped server-side to the authenticated controlled team; return plan ID, revision and capability/ownership context. Client creation idempotency key prevents duplicates. |
| `GET /api/overhauls?league_id=…` and `GET /api/overhauls/{id}` | List/resume only authorized plans. Return selected version, review/prioritization progress, execution events, outstanding actions and source timestamps. |
| `PATCH /api/overhauls/{id}/settings` | Require expected revision; persist a new revision, invalidate incompatible pending generation/assembly, preserve history. Never overwrite sent requests. |
| `POST /api/overhauls/{id}/generate` | Revision-bound, idempotent asynchronous generation with previous exact decisions/exclusions and structured reason for more supply. Return durable generation run ID. |
| `GET /api/overhauls/{id}/generation/{runId}` | Authorized progress and paged candidate results; label superseded revision and partial search coverage. |
| `POST /api/overhauls/{id}/decisions` | Idempotent like/pass/undo event against the exact candidate and generation revision; respond with current review progress. |
| `POST /api/overhauls/{id}/assemble` | Produce 4–5 alternative roadmap versions or structured insufficient-supply response; no provider writes. |
| `PUT /api/overhauls/{id}/roadmaps/{roadmapId}/priorities` | Expected version plus ordered tier memberships for a sell group. Validate offer IDs, exact group assets, unique membership, race compatibility and whole-plan consequences. Return a new immutable version. |
| `POST /api/overhauls/{id}/roadmaps/{roadmapId}/prepare-send` | User selects exact offer IDs from the current tiers. Validate current ownership, authentication/capabilities, group conflicts, roster constraints and external active status where available. Return short-lived prepare token, exact summary hash, warnings, counts and prerequisite actions. No provider writes. |
| `POST /api/overhauls/{id}/send` | Require confirmed prepare token, summary hash, expected version and stable idempotency key. Atomically create intent/attempts and reservations; return batch ID and per-offer receipt states. |
| `POST /api/overhauls/{id}/refresh` | Read/reconcile supported platform data; rate-limited and idempotent. Never sends fallback offers. |
| `POST /api/overhauls/{id}/attempts/{attemptId}/status` | Explicit manual assertion when needed, with source recorded as user-reported. A user assertion cannot bypass fresh ownership checks or prove provider cancellation. |
| `POST /api/overhauls/{id}/attempts/{attemptId}/withdraw` | Capability-gated explicit withdrawal of an owned attempt; unsupported routes return a platform handoff and retain uncertainty. This is not trade acceptance. |

Use stable structured errors (`revision_conflict`, `offer_stale`, `asset_reserved`, `ownership_unknown`, `capability_unavailable`, `reconnect_required`, `supply_exhausted`, `outcome_unknown`) with per-offer detail. Never silently drop unsupported assets from a request. Every request verifies account, league, platform and roster control; a guessed plan/offer ID is not access. Add body/count/search limits, rate limits and private-data redaction.

## 7. Execution, equal-priority races and failure recovery

### Prepare and commit

The send summary is the concrete approval surface. Show all actual recipients and exact asset sets, selected roadmap version, group-by-group offer counts, advisory first-pick recovery rank, priority-tier races, known warnings and expected platform handoffs. Four independent sell groups can legitimately mean six outgoing offers if two groups each contain tied alternatives; do not call that “four offers.”

Preparation binds to current ownership/rules/capability observations and expires when any relevant revision changes. A confirmation cannot authorize later regenerated or swapped terms. The commit transaction validates the prepare token, claims every outgoing asset for its group/race, and creates a durable outbox of exact attempts before any network write. Same idempotency key plus same request returns the existing batch; the same key with changed contents fails. Competing devices or plan versions cannot both acquire the same reservation. Claim a batch's local reservations atomically, or report no new batch accepted; a partially dispatched external batch can never be rolled back as if it had not happened.

Workers use bounded concurrency and a durable claim/lease with compare-and-swap transitions. Keep remote calls outside database locks. Revalidate authoritative ownership immediately before each provider call and bind the provider user/league from server context, never a mutable foreground session. Persist the sending intent and a stable event ID before dispatch; link only confirmed success to `trade_proposals`, using the actual final terms. Do not directly invoke existing routes in a loop because their per-request event IDs do not prevent duplicate remote sends.

### Attempt lifecycle

Use distinct states such as `prepared`, `queued`, `sending`, `proposed`, `send_failed`, `outcome_unknown`, `declined`, `expired`, `countered`, `withdraw_requested`, `withdrawn`, `accepted`, `invalidated`, and `resolved_elsewhere`. Store status source and observation time separately. A `proposed` receipt is not an acceptance; a browser handoff is not a proposed receipt; absence from a pending list is not automatically a decline. Terminal states require provider evidence or visibly labelled manual status. Reconcile out-of-order observations without regressing accepted/withdrawn states on a stale poll.

On timeouts after a request may have reached the provider, persist `outcome_unknown`. Do not automatically repeat a non-idempotent write or let an expired worker lease authorize a duplicate. Reconcile via provider ID/status where supported; otherwise require explicit platform inspection/user resolution. Network errors before proven submission and explicit provider refusals may be classified differently only with adapter evidence. Server-level deduplication guarantees one accepted local intent, not exactly-once execution inside a provider that offers no idempotency contract.

### Equal-priority offers

Outgoing overlap is permitted only inside the deliberately confirmed race for one exact sell group. Other groups remain independent. Multiple tied alternatives to the same opposing team should not be bulk-dispatched without a defined provider-compatible rule; proposed default is one offer per opponent within a group tier, with other offers ranked in lower tiers. Surface this constraint in priority editing rather than silently omit a tied choice.

The backend dispatches a tied tier in one user-authorized batch with bounded concurrency; “at the same time” means one action, not atomic simultaneous acceptance at the provider. The summary must say the offers share assets and that the first accepted eligible offer determines the group's outcome. Confirm the platform's conflicting-asset acceptance behavior before enabling the race capability. If that behavior is unknown, do not claim a guaranteed first-come winner through a cosmetic warning alone.

On confirmed acceptance, settle the group, invalidate alternatives using its outgoing assets, reconcile fresh rosters and pick ownership, and revalidate all remaining groups. Stop any not-yet-dispatched conflicting attempts. Attempt withdrawal of already pending alternatives only when the adapter supports and proves it; otherwise show exactly which offers still need action in the platform. Never show them as withdrawn merely because a local group closed. External negotiations or trades may invalidate more than one group; preserve the original history and propose a refreshed remaining plan.

### Reservations and manual fallbacks

Retain reservations while any offer is pending or its remote outcome is unknown. A timer alone must not free assets that may still be promised remotely. Distinguish short-lived local worker leases from remote-offer reservations. After all offers in a tier resolve with no winner, surface the next tier as available and wait for the user's decision. The user may negotiate, edit or select another roadmap; every new send runs preparation again. Do not keep unselected alternative roadmaps reserved, but prevent switching plans from duplicating an active sale.

## 8. Platform capability contract and known gaps

Proposed per-plan capability response: `canProposePlayers`, `canProposeConcretePicks`, `canReadPending`, `canReadTerminalStatus`, `canWithdrawOwnOffer`, `supportsConflictingOfferRace`, `providerIdempotency`, `ownershipSource`, `rulesCoverage`, `authState`, and `checkedAt`, each with explicit unknown/unsupported distinction where relevant. Resolve from server-side platform adapters and current evidence, not numeric league-ID guesses or static client assumptions.

| Platform | Inspected code capability | Required boundary for overhaul |
|---|---|---|
| Sleeper | Verified-session propose route; server-side concrete pick encoding with live holder checks. Completed public trade capture. `reject_trade` helper exists; no inspected routed pending/revoke lifecycle. | Establish reliable sent-offer status/reconciliation and test race behavior before advertising automatic status or withdrawal. Keep manual status/platform inspection available. Generic pick tiers and user-asserted pick rows cannot be sent as real Sleeper picks. |
| MFL | Propose with player crosswalk and concrete owned-pick mapping; authenticated pending export; respond accepts/rejects/revokes. Current propose result has `status`/`mfl_status`, not a provider transaction ID. | Safely correlate a sent exact offer with pending export IDs; ambiguous matches stay unresolved. Verify fresh ownership, full rules and accepted/declined semantics; absence from pending is not terminal proof. Reuse existing response gates without turning this feature into an auto-accept client. |
| ESPN | A players-only propose route exists behind `espn.send`; comments and config describe it as default-off/absent from shared feature config pending validation. Every pick send is refused. User-assigned planning picks may exist. | No automatic bulk-send or pick lifecycle promise from code existence. Capability-gate planning versus executable offers. Pick-dependent all-in/rebuild payoff remains unavailable for direct sending unless an independently validated integration changes that. |
| Other/unavailable | No generic equivalent is established by these reads. | Offer an honest planning/handoff mode or supported-platform entry gating. Never label external link opening “sent all.” |

Default flag values are repository configuration, not a live deployment audit. External capability feasibility notes and captured schemas do not prove implementation or current provider behavior. Provider work and acceptance testing must use the existing integration and release workflow; this document adds no credential handling or service changes.

## 9. Required engineering checks before implementation/enablement

- Rebase/integrate the implementation branch onto current main and re-read ADR-019, owner generation routes, selected-offer metadata and exact-package signal helpers. Preserve existing arm assignment, default-off trial knobs and private owner evidence. Decide the overhaul generation profile explicitly; it must not accidentally turn on an existing experiment globally.
- Prove the eligible-pool constraint at construction and final validation, including filler assets, exact anchors, pick-only sides and independent full-roster context. Evaluate search supply and bounded runtime on realistic large dynasty rosters without calling production.
- Exercise identity across co-owned teams, traded original firsts, season rollover, unknown/stale ownership, generic versus concrete picks, and user-asserted versus platform rows. First recovery must target the original franchise's exact next-season first and remain advisory.
- Demonstrate disjoint outgoing **and incoming** assets, all affected counterparties, multiple offers to the same partner, final roster assignment, intermediate subsets, tied-tier alternatives, unknown rules and explicit prerequisite handling. Include a fixture where all single trades pass but their union fails.
- Prove plan preferences never mutate regular finder outlook/positions or player tiers. Test priority tie membership, within-tier order, drag/scroll behavior, empty tiers, accessibility actions and persistence on one sell-group page at a time.
- Prove concurrent sends from two devices/plans, duplicate client retries, same-key/different-payload rejection, stale prepare tokens, worker crash before/after provider response, unknown transport outcomes, partial batch success, reconnect and conflicting external trades. These require transactional tests with fake provider adapters, not source-string checks alone.
- Verify remote status capabilities and unknown outcomes independently per platform. Test proposed versus accepted, pending disappearance, declined versus expired, counters, manual assertions, acceptance while another send is in flight, and incomplete withdrawal. Provider writes must remain fake in automated tests.
- Set a deliberate policy for roadmap review signals, register any new analytics names/source enums in the taxonomy and `NON_INTENT_EVENTS` classification, and link views/decisions/proposals to exact offers and plan versions. Never count prefetch, assembly or preparing a send as user viewing, liking or proposing.
- Add shared flags and source references through the canonical update table: database, API, architecture, config, cross-client invariants, glossary, integrations and design. Capture ADRs for execution reservation scope, race capability and any plan-specific roster policy. No live flags, deployment or credentials are changed by the handoff.
- Runtime acceptance must use a concrete manual TestFlight checklist tied to a build, plus appropriate backend/mobile/web CI. Maestro and simulator work are retired. The root handoff's implementation plan and QA checklist own phase ordering, pass/fail evidence and release gates.

Evidence in this document is read-only code inspection. No automated test, device check, provider call, migration, build, deployment or feature activation was performed for this specification.
