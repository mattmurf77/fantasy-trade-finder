# Team overhaul — implementation plan

Owner-approved core mockups, 2026-09-06. This is an engineering handoff; implementation has not started. See [status](status.md), [product requirements](PRODUCT-SPEC.md), and [engineering design](ENGINEERING-SPEC.md).

## Outcome

A manager chooses an aggressive direction, selects an eligible trade pool, reviews offers, and selects a roadmap of four or five independent sell-asset packages. They rank each package's alternatives, send the chosen offers, and return as responses arrive. The target is four or five alternative roadmaps. Tied alternatives compete for the same assets and are explicitly disclosed as first come, first served.

## Delivery sequence

| Work item | Deliverable | Depends on | Exit condition |
|---|---|---|---|
| 1. Confirm implementation boundaries | Platform capability map, final API/data contract, launch surface and configuration decision | Specs and source inspection | Document which integrations can submit, withdraw, and observe offers; resolve release-critical proposals in the product spec |
| 2. Persist an overhaul draft | League-scoped draft, settings, eligible assets, pick identities, versions and resume routing | 1 | Saving/reopening preserves choices; regular finder preferences stay unchanged |
| 3. Build setup and entry | Proposed Acquire entry/resume card (finalize D9), outlook, full positional roster, pick budget, return mix and optional positions | 2 | Both outlooks complete setup; no mock-only ownership control; Continue CTAs; exact missing first explanation |
| 4. Generate and review candidates | Existing trade-chip interaction with candidate provenance and selected-pool enforcement | 2 | Unselected assets never enter outgoing offers, including sweeteners; picks-only shapes work; complete-review default covers every chip (D3 remains open) |
| 5. Assemble alternative roadmaps | Bounded compatible-set search, coverage explanation, regeneration loop, persisted alternatives | 4 | Four or five independent packages per roadmap; target four or five materially distinct roadmaps; inadequate likes return to more review |
| 6. Rank alternatives | One package per page, drag/drop tiers, accessible movement, per-package Back/Continue | 5 | Ranks survive navigation/relaunch; tie counts and next-tier behavior are correct; asset groups remain stable within a chosen roadmap |
| 7. Preview and send | Summary, first-pick execution priority, exact simultaneous-offer disclosure, preflight and batch results | 1, 5, 6 | Double taps/retries do not duplicate offers; partial success is shown; no unconfirmed platform send is called successful |
| 8. Track and resume | Per-offer response state, accepted-package locks, manual fallback, counteroffer revalidation | 7 | User can negotiate or send the next valid tier; external changes cannot silently spend reserved assets |
| 9. Validate and release | Meaningful engine/execution tests, client checks, device checklist, docs and rollout evidence | 3–8 | [Acceptance plan](QA.md) satisfied on the relevant build; normal repository release gates met |

Backend work on 2/4/5 can overlap client work on 3/6 against an agreed contract. Platform research in 1 must precede promises about bulk sending, withdrawal, or response freshness. Work item 7 must use the established platform/authentication boundary.

## Build order and ownership

- Product/design owns the confirmed-versus-proposed boundary, entry placement, return mix and pick-budget controls, and empty/error-state copy.
- Backend owns eligible-pool enforcement, exact asset identities, compatible roadmap construction, persistence/version checks, preflight and offer attempt history.
- Mobile owns the Acquire entry, reuse of existing chips/Tiers gestures, draft restoration, accessible ordering, review and execution screens.
- Integration engineering owns capability verification and truthful mapping of submission and provider response states. A network timeout must not become a safe-to-retry assumption.
- QA owns conflict/race fixtures and real-device acceptance, including stale league state and partially submitted batches.

No fixed schedule is assumed. Estimate these work items after platform and engine spike results; do not treat the standalone mock's fixed sample data as a working solver.

## Requirements that must survive implementation

1. Selection means eligible, not mandatory. No automatically added outgoing sweeteners outside that pool.
2. Alternative roadmaps may regroup assets. Within the selected roadmap, each package has a fixed outgoing set and ranked candidate alternatives.
3. A rebuild missing its exact next-season first includes a recovery offer and highlights it as overall execution Priority 1. This is advisory, distinct from offer tiers within a package.
4. User controls pick spending and the rebuild's picks-versus-young-players preference. Positions are soft preferences; roadmap settings stay separate.
5. Ordinary packages use disjoint outgoing assets; offer ties inside one package are the disclosed exception. Total offer count can exceed package count when there are ties.
6. Insufficient compatible likes trigger more generation/review and a prompt to revisit the asset pool. Do not quietly ship a smaller-plan fallback.
7. Next-tier execution waits for the user. A decline may lead to negotiation; automatic progression is future scope.

## Release boundaries

Keep launch platform coverage and provider capabilities explicit. Enable the smallest validated surface first only after the launch choice is resolved; iOS/Sleeper is a proposal, not a recorded owner decision. Register any new shared flag and analytics in the existing systems. A proposed disabled-by-default entry/generation gate must not strand already-sent offers or erase tracking access.

Update current API/schema/configuration/product references when their behavior is implemented. Keep this folder as the initiative and evidence home. Do not overwrite canonical references with proposed routes or unbuilt behavior now.

## Separate future feature

**First come, first served — single sell asset:** let a user like trade chips for one asset, then send one liked offer per opposing team simultaneously. This was separately requested for the next queue and is not an extra roadmap deliverable. Reuse execution safeguards later, but estimate and release it separately. The existing queue entry is [NEXT item 7](../../../living-memory/NEXT.md).
