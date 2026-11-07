# Calibration coverage evidence and limits

## Implementation contract

`calibration_fixed_lineup.prepare` preserves original slot names, fixed holdings, current conservative assignment and availability uncertainty. The exact bipartite assignment is independent of player prices. A fixed asset has empty offensive eligibility and an internal zero capacity sentinel, never an observed zero market price. Full team holdings remain in the common context; all active fixed holdings count toward its unchanged capacity, and observed IR/taxi stays excluded. Missing fixed metadata remains an unresolved asset. Cross-domain eligibility and contradictory/duplicate fixed ownership are rejected.

Only the offensive slot projection is passed to the existing roster checker after the disjointness proof. `validate_legs` refuses any fixed/non-offensive trade leg or future cut plan. No fixed asset joins the rank pool. Both original owner generators, market values, candidate budgets, significance, roster depth and quality gates are unchanged. Each selected card's private proof includes both the original slots and the fixed-block interpretation; it does not claim the whole lineup is filled or every provider rule has been validated.

ESPN distinguishes native position IDs from lineup slot IDs: native9/10 are defensive linemen and native11 is linebacker; slot10 is LB and slot11 is DL. Each player's actual eligibleSlots must agree with all declared group/offense slots. Nontradeable provider-native IDs are private stable holdings, with no player crosswalk or price asserted. Their raw eligibility/availability evidence stays in the frozen source. Native fixed IDs must be canonical integer scalars (negative DEF IDs allowed); booleans, compounds and nonfinite values fail. Native position/slot enums reject boolean numeric aliases. Existing position maxima on offensive trades remain unsupported; immutable fixed-position totals cannot change a fixed-position maximum. Individual DE/DT/CB/S lineup slots are not promoted by this repair.

The linked reader validates the importing account binding before provider access and uses only that account's credentials. Its fresh native seat check can recover a missing flat cached member row. The current global import-binding design cannot represent a different account’s authenticated seat in the same linked league; this remains an engineering gap rather than proof that the account is unauthorized. A non-importing binding is still denied without borrowing the importer’s identity; a fresh Sleeper membership denial remains a denial. MFL's nonrepresentable offense/defense minimum/maximum systems remain an engineering gap, never approximated by extra superflex slots.

## Source currentness and privacy

All consumed local eligibility/active/injury metadata is already in captured_metadata_ids and before/after/current input fingerprints. The new helper joins the backend source digest, so older unexposed comparisons must be reprepared after deployment. Native provider facts remain an explicitly frozen as-of snapshot; open does not refetch a provider or independently detect unobserved changes. Answered/exposed cohorts are never rewritten. No new provider writes, session tokens, organic impressions, rank learning, account impersonation or private exports.

Unavailable rules now fail capture explicitly, before both model inventories. Mobile distinguishes unsupported rules, account-specific binding support, expired/current-membership reconnection and actual too-few surviving candidates. Polling a failed session is read-only; an explicit Start or authorized admin retry remains available.

## Reproducible checks

- `test_calibration_fixed_lineup.py`: exact overlapping-group matching, 15-slot/36-capacity and DEF/19-capacity shapes, active/IR capacity, null price/no offensive depth, unknown and cross-domain metadata, duplicated ownership, both offer sides, cuts and real paired generation.
- `test_calibration_provider_parsers.py`: finite native ESPN mapping, native eligibility contradiction, retained private unmapped fixed holdings, original unsupported settings/limits.
- `test_calibration_linked_capture_real_arms.py`: absent own flat member row with valid binding, real raw ESPN/MFL normalization and both full engines; ESPN mixed fixed slots with complete private proofs.
- `test_outlook_calibration_routes.py`: repeated failed current reads do not build, enqueue or mutate; existing freshness, exposure and rollback cases remain covered.
- `check-calibration-failure-copy.js` executes the actual mobile copy function for unsupported, reconnection, too-few and unknown errors. Existing blind-grading guard covers neutral UI and no arm leak.

Aggregate-only authorized readback identified five Sleeper pairs with K/DL/LB/DB/IDP slots and one with DEF, plus one ESPN mixed-slot configuration. No customer rosters, identities or credentials are committed. These categories informed synthetic fixtures; passing them is not evidence that every live comparison has enough surviving candidates. Parent must deploy, reprepare unexposed snapshots, verify actual readiness/failure readback and then activate.

## Manual TestFlight checklist

1. Open a ready supported league: a frozen as-of comparison appears, without entering Acquire or sending a trade.
2. Open an unsupported constraint league: see a rules/eligibility explanation, with no suggestion that switching to Sleeper necessarily solves it.
3. Open a failed account-binding league: see an account-specific team-link limitation; no promise that reconnecting alone fixes the global-binding design and no other account is selected automatically.
4. Reopen a partially graded comparison: existing answers/order/as-of remain unchanged. Poll a failed screen: no repeated rebuild loop.

No simulator or device runtime result is claimed by these source/unit checks. Exact-head CI and production readback remain release gates owned by the parent agent.

Follow-up engineering: a verified second account can hold the same MFL franchise as the global importing account. Supporting that account requires an explicit account-versus-canonical-seat mapping with unchanged pick ownership and private-board isolation; it is not resolved by borrowing the importer’s credential. Native MFL range constraints remain a separate limitation even after such identity support.
