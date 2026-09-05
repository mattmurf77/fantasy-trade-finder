# Owner contracts — parent review and remaining work

**Date:** 2026-09-05. **Baseline:** `origin/main` at `5cf34182`.
**Status:** implementation reviewed and final local verification passed; code committed locally as `86128700`. Publication is blocked pending explicit owner approval for this public GitHub destination. No push or PR was created; hosted CI is unrun. Not merged or deployed. Physical TestFlight is unrun.

## What this patch changes

- Mobile carries explicit SEND/GET selections through calculator → finder, preserves the searched request on Retry/Find More and model regeneration after ranking, carries fairness/shape to the pushed results, restores the builder on Back, and clears temporary context on league change. Later explicit partner changes supersede old snapshots while retaining SEND and clearing incompatible GET. Anchored searches distinguish pending, failed and completed-empty states.
- The existing final trade-intent filter uses the user's personal tiers, falling back to consensus only for an absent entry. Same value's tier-membership lookup also uses the user's tier. Market companion pricing and the existing generator profiles/gates are unchanged.
- Indirect trade/disposition feedback cannot move a player across the tier shown by the one-decimal ranking API, including cumulative feedback and saved-history replay. Deliberate ranking actions retain their existing behavior. No new feedback weights/actions are introduced.
- The existing dark policy gives known explicit ranking methods equal authority. A per-player provenance map is read from existing columns; a seeded majority cannot erase a deliberate entry. Copy publication marks only actually copied, tiered entries, consistently with later ordinary publication and the viewer's placement map. No historical valuation snapshot or production row is rewritten.
- Public serialization now omits exact counterparty own-board gain and MESO recipient-value percentage from copied response dictionaries. The requesting user's own values, qualitative fits and package identities remain; internal generator math and audit data are unchanged. Endpoint and serializer regressions cover both known fields.

This is a bounded first implementation, **not the entire owner handoff**. No fairness-loss limit, experiment allocation, generator profile, default flag or stud-tax setting changed.

## Parent and independent review

Implementation was split into isolated Astra Ultra mobile/policy worktrees; the parent owns the integration branch and has not modified the owner's dirty shared checkout. An independent Astra Ultra agent reviewed the parent ranking/provenance code and then the mobile diff. The parent read the integrated diffs, examined changed historical assertions, and rejected broad source changes that broke the control arm.

The remote repository is public. Raw interview answers and the local interview/UX source documents are deliberately excluded from the public commit history. They remain in the original project folder; this branch publishes only scoped implementation, tests and focused engineering documentation. Unpublished parent commits were consolidated before the first push so excluded source files are not reachable through earlier pushed commits.

| Finding | Disposition / evidence |
|---|---|
| Raw-float tier bounds still rounded into a different visible tier | Fixed: derive membership at the API's one-decimal precision; use a representable unranked ceiling widened to retain the initial value. Public ranking tests cover below-floor and just-below-next-tier values. Independent 320-case sweep found zero visible tier changes. |
| Searched partner B masked a later explicit partner C / Any | Fixed: distinguish the searched snapshot's own scope synchronization from a later external change. Independent execution of the actual component confirmed partner changes, SEND edits and league reset. |
| Returning from rankings discarded a consumed receive-only canvas request | Fixed: forced model regeneration repeats the saved request. The new guard executes the actual AST-extracted mutation function, not just source-string assertions. |
| Global removal of the live confidence blend changed historical arm-A outputs | Held: restored only the subagent's live-helper/test edits. No profile or golden recapture. Dark-policy authority remains separately implementable. |
| Proposed whole-generator missing-entry overlays changed the candidate universe | Held: safety review rejected the broad patch. No rejected fallback or implicit-position expansion was integrated. |
| Copy-to-below-tier provenance disagreed between viewer, partner and next publish | Fixed conservatively: existing no-tier markers remain absent authority in all three paths. Durable distinction between intentional below-tier copies and historic demotion markers remains unfinished. |
| Browse All Undo restores a card but retains its already-submitted feedback | **P1 unfinished**, not fixed by bounded replay. `TradeBrowseAllScreen` dispatches pass immediately and restores locally. The replay unit test proves reconstruction from retained rows, not a production causal Undo endpoint. |

Evidence detail: [mobile code walk](mobile-code-walk.md), [policy code walk](policy-code-walk.md), [manual TestFlight checklist](mobile-testflight.md), and the central [test ledger](../../../living-memory/TEST_LEDGER.md).

## Timing / data capture: existing coverage versus missing work

This was a **read-only source/test audit**, not a new production database investigation. Checked-in `deck.signal_v2` and `suggestion.telemetry` are on; `trade.valuation_telemetry`, `trade.personal_market_policy_v1` and the roster enforcement/shadow flags are off. Do not conflate code coverage with production collection.

- Existing impression/outcome paths record served time, linked viewed/action times, exact assets and generator/policy attribution (`server._run_trade_job`/event ingest, `database.save_deck_impressions`).
- Dark valuation snapshots preserve per-asset market and both raw/effective personal values. Match attribution can retain **two separate impression IDs and like times** plus a third current match snapshot; provider-confirmed proposals can retain the final sent package/value snapshot. Existing tests cover null legacy attribution and idempotent proposal records. These paths do not overwrite the original impression valuation.
- **Original display is not yet guaranteed:** mirror-like injection reuses exact assets but recalculates current prices; it does not render the original stored valuation snapshot. Preserving a private snapshot is not equivalent to preserving what manager B sees.
- **Full input context is incomplete:** tier placements/provenance, market-feed version/as-of, declared outlook, saved goals/tags, rosters and league rules are not uniformly frozen at every offer/exposure/action. Existing valuation-centric snapshots are not a complete reconstruction of all levers.
- **Expiry is not owner-aligned:** current card TTL, old-like eligibility, standing-offer duration and attribution lookback are separate clocks (7/90/30/30 days in the inspected defaults/paths). A package concept hash is not a durable expiring offer instance. No single ≤14-day interest contract has been implemented here.
- Mutual matching adds no new manager-A revalidation gate, but the legacy post-match disposition flow still requires both acceptances for accepted status. End-to-end “no reconfirmation” cannot be claimed yet.

The next data-model scope should explicitly distinguish immutable offer-instance terms/value, manager-specific exposures/actions, and later diagnostic snapshots. It must resolve clock start, renewal/withdrawal and standing-offer semantics with the owner; do not silently substitute current values or invent new reapproval gates.

## Next implementation slices, in priority order

1. **Causal committed-action Undo:** retain a stable decision-to-learning-row identity; reverse only the undone action, rebuild from retained signals, and cover duplicate Undo, unrelated signals and restart. Do not delete rows based merely on player pairs or apply opposite Elo deltas to invert a clamp.
2. **Complete offer-instance / exposure snapshots and original presentation:** preserve the original package/valuation for the later viewer while retaining separate current context internally. Implement the ≤14-day lifecycle only once ambiguous clock/standing-offer rules are settled.
3. **Arm-safe personal-authority treatment and missing-entry candidate fallback:** preserve the selected control, scope how the treatment applies to all relevant generators and post-generation paths, and measure supply plus accepted/passed outcomes. Do not mutate the historical golden to conceal a changed control. Existing live shrinkage and 1500-placeholder/pool-intersection paths remain.
4. **Finish user-driven trade-shape and soft preferences:** asset-ideas Upgrade/Downgrade still use market-band conditions, implicit position restrictions remain, and Untouchable is still a hard exclusion. Build an explicit proposal for above-market return plus outlook/need/replacement benefit before replacing those exclusions; no arbitrary premium was selected by the owner.
5. **Clarify remaining UX/product choices:** what “both options” means for partial selections and minimum coverage; More Offers initial package/partner keep-release defaults; precise account-wide fairness storage; legacy stud-tax Off handling. No durable tags were deleted and no substitute target or fallback group invented.
6. **League/pick contextual work:** no new next-year-only slot projection, trade-sensitive draft-position forecast or league-depth/bench utility model was implemented. Audit existing decay/market-slot behavior against the owner's no-later-year-discount direction before changing it.

## Verification / release boundary

Final parent integration on Python **3.12.14**: `python -m pytest backend/tests -q --tb=short` — **5,455 passed / 1 skipped in 566.99 s**, exit 0. The final four new owner/privacy suites also passed together: **102 passed in 19.49 s**. Mobile: **all 93 `check-*.js` guards**, `tsc --noEmit` and test-ID lint passed. Web structural guard: **190/190 passed**. Local Node is **24.14.1**; hosted CI uses Node 20 and remains a separate gate. Staged whitespace validation passed. Policy lane and the final full suite include unchanged historical arm-A/challenger and all three generator regressions. Hosted exact-head CI is pending publication; no native-runtime result is implied by these checks.

Only a reviewed feature-branch push is contemplated after local gates. The publication safety review rejected the push/PR command before execution because the repository is public and explicit destination-specific approval is required. Do not retry through another account or tool without that approval. Local read-only history checks confirmed all five raw source files remain on disk and are absent from new commit history; config, fixtures, lockfile and secrets are unchanged. No merge to main, Render deployment, EAS build/submission or production migration is included. Manual TestFlight remains a release follow-up, not a claimed pass. All worktrees are retained for review; no cleanup/deletion is part of this coding change.
