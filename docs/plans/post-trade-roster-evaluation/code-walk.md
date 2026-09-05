# Full-roster evaluator and balance-policy review

Built on `claude/fleeced-trade-engine-balance-c0c75d` at the user's request. Main base: `606e512c`; the preceding agent's changes are preserved and revised on this branch. All four new switches remain false.

## Final behavior

`backend/trade_roster.py:51` uses exact maximum-occupancy, then maximum-value assignment. Dedicated and shared slots draw from one pool; no player fills two slots. `:101` evaluates legal and usable coverage across actual unions of slot eligibility. The starter-quality predicate is the existing `trade_service._startable_ok_fn`, evaluated once for the player pool. Dynasty values are proxies, not point projections.

`:144` removes the outgoing package, adds incoming assets, applies explicitly supplied existing-player cuts, then evaluates the whole roster again. It protects each group's existing starter coverage and up to one usable replacement. This includes FLEX groups. Existing deficits may remain but cannot worsen. Picks never occupy an active slot. Receiving a player only to discard them is not an allowed implicit repair. The leaf supports explicit cuts; the serving path supplies none and therefore withholds capacity-overflow suggestions.

`:208` evaluates both managers symmetrically. Unresolved assets, ownership inconsistencies, missing capacity, estimated slots or unavailable availability data cannot pass enforcement. `safe` means the supported checks passed; `schedule_coverage: unknown` remains explicit without supplied weekly scenarios. Outlook weights starter-value change versus whole-roster dynasty-value change (contender .75/.25, balanced .5/.5, rebuilder .25/.75). Championship maps to contender; jets maps to rebuilder. Structural protection is identical for every outlook.

`backend/trade_roster_adapter.py:7` consumes resolved provider inputs without I/O. `backend/server.py:5167` loads one final snapshot for the job: observed Sleeper slots, raw roster ownership, reserve/taxi and player status. Player availability older than 48 hours is incomplete. Non-Sleeper lineups currently come from estimated templates and cannot pass enforcement. Unsupported starting slots are kept visible rather than silently filtered out. Known picks outside the capped generation pool are included in the full holdings/value calculation. The canonical league owner identity is used for a co-owned viewer roster. Session `League.members` normally contains only opponents: the adapter adds the viewer independently from the provider roster, with a session fallback that remains uncertain. A regression fixture excludes the viewer from members and includes a co-owner login (G-063). Null provider roster placeholders are ignored; unresolved actual IDs remain unknown.

`backend/server.py:7474` runs after all package mutation layers and before market composition. Unknown/unsafe cards are withheld only with `trade.roster_protection`; shadow evaluation preserves the deck. The same frozen evidence goes into impression features (`:7769`); bounded rejection reasons go into `trade_policy_shadow`, including arm provenance (`:5243`). `:5213` orders safe cards by the weaker manager's outlook utility. With market policy also on, personal opportunity remains primary; roster utility breaks ties before market distance and drives no-board fallback ordering (`:5451`). It is not an acceptance probability.

## Review corrections to the first agent

- **Streaming bypass:** `_make_progress_cb` (`server.py:3025`) still updates progress but holds provisional cards while either enforcing gate is pending. Every intermediate worker publication is guarded. One final publication also covers empty decks and runs when impression logging is disabled. A structural AST regression guard pins all pre-gate publication sites.
- **Unavailable evaluation:** enforced policy/context failures produce an empty deck and a diagnostic; shadow failures preserve the original result. The job freezes enforcement and changes in the safety switches invalidate completed cached decks (`server.py:2991`).
- **Confidence/value asymmetry:** partial persisted weights no longer erase other assets' comparison counts (`trade_policy.py:190`). Malformed weights degrade to zero. Explicit viewer placements carry explicit confidence. The v2/v3 pair policy now reconstructs the viewer from raw Elo/confidence using the same policy shrinker as the partner and final gate (`:783`), instead of consuming legacy outlook/marginal transforms.
- **Composition:** zero and small deck limits are honored; Conviction cannot jump an incomplete Core lead block or exceed its share of the realized deck (`trade_policy.py:1026`). No-board Fallback remains available when no Core supply exists.
- **Attribution:** an impression must belong to the same user and league. A swipe also requires the same final package hash (`server.py:5043`); edited proposals may retain an origin from the same league. Proposal event IDs are request-local ledger IDs, not cross-request send idempotency; misleading comments were corrected.
- **Existing weaknesses:** with full protection enforcing, the optimizer's cheap count prefilter permits an existing deficit to remain unchanged. The final evaluator owns actual slots/quality and prevents new or worsened deficits.

## Coverage and rollout limits

This is a dark implementation and HTML review artifact, not a production rollout. No flags, production DB migrations or experiment allocations were changed remotely. It does not prove higher acceptance rates. Current data supports offline/shadow testing before cohort activation.

The server has no weekly schedule feed; byes and future injury risk remain unverified. Non-Sleeper settings must be imported before enforcement there. K/DEF/IDP and multi-team exchanges are not supported by this evaluator. Missing required inputs reduce supply rather than manufacture a safe result. Existing Q-038 (raw personal gain versus marginal utility) and Q-039 (account-versus-owner policy concept identity) from the first agent remain open. Cross-format confidence provenance still needs a requesting-user round-trip audit before enforcement: live viewer counts/placements and persisted partner weights travel through different storage paths. No uncalibrated probability or claimed acceptance uplift is exposed.

## Validation

Pure tests include a brute-force oracle for overlapping eligibility, full-roster mirror symmetry, unusable bodies, FLEX/Superflex, existing deficits, backup preservation, roster capacity/cuts, picks, unknown sources, bye scenarios, outlook and adapter ownership. Worker tests cover shadow/enforce, frozen evidence, intermediate publication, context errors, cache changes, attribution and final package rechecks. Exact commands and outcomes are in `living-memory/TEST_LEDGER.md` and this folder's `validation.md`.

## Mockup

`mockups/post-trade-roster-check/index.html` adds one expandable disclosure to the existing lineup evidence, with both-team controls, replacement chains, bench detail and three hypothetical scenarios. Its README inventories current source behavior and the dated actual capture. This is additional detail for existing explanations, not a new explanation feature or a shipped mobile component.
