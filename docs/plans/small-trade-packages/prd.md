# Small-player-package presentation — PRD

Date: 2026-09-06. **Original planner approved author `07d98473`; root approved revised `5171f13a` and its #419 integration condition. Build underway from reviewed backend integration `741710c1`; final QA and activation pending.**

Inputs: [plan](plan.md) at `ea5cc2b5`, [research](../../research/2026-09-06-trade-package-shapes.md), [scope](scope.md), [reconciliation](reconciliation-log.md). Line citations identify audited runtime `4026ebc8`; §3.3 and §4 additionally reconcile #419 `cf8cc2cc`'s final disposition filter. Parent must reconcile current integration changes before build.

## 1. Outcome and bounded exception

Prefer easier-to-read **player** packages locally among already selected, eligible generated ideas, retaining all larger packages and every valuation/eligibility decision. The selected owner-view sample supports a small readability preference, not a hard cap, causation, an arm winner or an acceptance-rate target. Picks must not be counted as extra players.

This is an **explicit narrow exception** to bakeoff's fixed post-generation/within-arm order (`backend/bakeoff_runner.py:397`). It changes which same-arm card is exposed earlier, not source-arm allocation, drafting credit, generator output or ranking math. Preserve the actual **final post-policy** slot-class vector, not a reconstruction of pre-policy interleaving. Historical generator goldens remain unchanged; exposure comparisons must slice by serving-presentation version. No fourth arm or claim of experiment-neutral outcomes.

## 2. Requirements

| ID | Contract | Tests |
|---|---|---|
| R1 | Only new organic generated jobs with captured mode 1 and successful **live** market/mutual final policy evaluation are eligible. No explicit give/receive pins or named opponent. Exempt demo, active ghost withholding, shadow-only/dark policy, and bakeoff dark/single-arm validation (`served_arm != None`). | T1, T3 |
| R2 | Apply one stable permutation within disjoint six-absolute-position windows and identical slot classes, maximum five absolute slots moved. Preserve objects/multiset/assets/values/eligibility, every class at its original position, protected special positions and equal-complexity order. These permutation invariants precede later authoritative disposition removals; their compaction is not a second reorder. | T1, T2 |
| R3 | Classify real players separately from generic/owned picks. Mixed packages may move; pick counts do not break ties. Pure-pick and unknown/malformed packages remain fixed. Missing required source/policy metadata locks the card; no fabricated attribution. | T2, T3 |
| R4 | Capture mode/version once for the logical generation decision; use it through kickoff, worker, all reuse checks and frozen provenance. Mid-job knob changes do not re-sort, relabel or resurrect old jobs. | T4, T5 |
| R5 | Reorder exactly once after final policy composition and before first evaluated publication. Every subsequent publication, serialization and impression writer consumes that order or its order-preserving disposition-filtered survivors; no `/status`, cached-dict or client re-sort. | T1, T4, T6 |
| R6 | Existing-column provenance retains pre-presentation original positions and remaps surviving occurrence metadata before freezing final positions from actual writer enumeration, equal to F1 `card_index`. Preserve source/group ranks and actual draw propensity; version serving separately from valuation policy. Off/exempt jobs retain baseline order/payload/features. | T5, T6 |
| R7 | One default-off knob, no other runtime policy/config change. Existing safety failures and #419 current-disposition filtering remain authoritative; never refill removed cards or rerun the preference over their survivors. | T3, T7, T8 |

### Scope exclusions

No calculator edit/evaluate/queue/propose, `/api/trades/fair-packages`, `/api/trades/asset-ideas`, Win Now, matches/Awaiting, manually assembled/shared offer, or mobile browse-session sibling ordering changes. An empty organic canvas reaching the ordinary generator is in scope; any supplied explicit player/opponent selection is not. A private raw-receive exemption preserves this exclusion even when the existing targeting flag ignores receive pins: mode-on requests bypass organic cache reuse/seeding without changing generator normalization or default fairness. Normal/forced generation, Find More, session-init pregeneration and headless/synchronous replenishment share the same worker and eligibility rule. Saved preferences and trade-intent semantics are unchanged.

## 3. Algorithm and exact worker placement

### 3.1 Pure stable permutation

Input is the final policy-survivor sequence and its existing card/object-keyed metadata. Never regenerate, deduplicate, truncate, add a candidate, call valuation, or modify a package. Produce a reordered list containing the **same object occurrences**, plus per-occurrence presentation records whose original indices/counts are retained and whose final indices freeze at the writer boundary (§4). Do not mutate input lists or source attribution; original ranks travel with their card, not their new slot.

Partition indices as `[0,6)`, `[6,12)`, etc., using the input sequence's absolute positions; final short window is allowed. Lock exact positions carrying truthy `likes_you`, `standing_offer_reason`, `wildcard`, `fatigue_retest`, legacy `retest`, or another existing explicit fixed-slot marker. The actual fatigue field is `fatigue_retest` (`backend/server.py:5928`), not only `retest`. Also lock malformed/unknown assets, pure-pick-only cards, missing actual per-card policy results, and unresolvable required source attribution. Locked cards neither move nor create a compacted/sliding window.

For every other card use slot class:

`(credited arm, group_key, lane_slot, card.lane, card.basis, policy_result.lane)`.

Preserve actual nullable `card.lane` values; null is not an inferred Core/Value label. Within each window and identical class, stable-sort by `(max(give_player_count, receive_player_count), give_player_count + receive_player_count)` and return those cards to **that class's original absolute slots**. Pick count is absent from the key. This is one disjoint-window pass, not repeated neighboring swaps; reapplying to its full output is idempotent. Every movement is at most five absolute positions, including around locked cards. Equal keys retain input order. A large-only deck stays fully available; equal/locked/sparse-class supply may correctly make no moves.

Classification uses existing `pick_values.parse_generic_pick_id` and owned-pick identity/schema (`database.make_pick_id`; server's `_parse_owned_pick_id` at `:3189`) plus resolved player metadata. Do not treat any underscore-containing ID as a pick, any unresolved ID as a player, or missing data as zero. A resolved actual player contributes one; a recognized pick contributes zero. Conflicting/malformed classification locks the whole card. Pure-pick means zero **known** players across both sides, not merely a side paid entirely in picks; a player-for-pick package remains mixed. Do not drop duplicates/assets to obtain a lower complexity score.

### 3.2 Source metadata rules

| Job/card context | Handling |
|---|---|
| Interleaved bakeoff, actual attribution present | Credited arm comes from `BakeoffRun.attribution_for(card)`, never a re-derived score/hash winner. Preserve `arm_rank`, `also_proposed_by` and original group rank. |
| Interleaved bakeoff with grouping active | Require real `group_for(card)` metadata; unexpected absence/malformed attribution locks that card. |
| Interleaved bakeoff with captured `bakeoff_group_size == 0` | `group_for` legitimately returns None; use `(group_key=None, lane_slot=None)` without inventing a group. Arm attribution is still required. |
| Bakeoff dark/single-arm validation (`served_arm != None`) | Whole job exempt. Root approved this conservative exclusion; its legitimate missing group metadata is not repurposed into permission to reorder a validation deck. |
| Genuinely non-bakeoff organic job | Explicit worker execution provenance establishes no bakeoff was requested; use one internal organic source class with absent group metadata. Never stamp it as `model_arm` or a fourth arm. |
| Bakeoff expected but run/attribution unavailable | No fallback to “organic”; lock affected cards (whole deck if provenance is unavailable). |

Each movable card needs the actual eligible `policy_results[id(card)]` and lane, preserving Core/Conviction/Fallback slots. Do not include `arm_rank`, `group_rank` or an index in the class; that would make every card unique and silently disable the intended effect. A legitimate no-op remains versioned when the eligible enabled rule was evaluated, so it can be measured rather than confused with off.

### 3.3 Publication choke point

`_evaluate_deck_policy` filters/orders and invokes policy composition (`backend/server.py:5451`, `:5538`; `trade_policy.py:1035`). In `_run_trade_job`, the final call is at `server.py:7676`; the market/roster failure handling ends before the **first evaluated publication at `:7727`**. Insert the single helper at this boundary, after final safety/policy survivors are known and before constructing that snapshot. Never place it inside an individual arm, before group drafting, only at impression time, or after `final_checks_pending` is released.

`final_checks_pending` is set for live policy at `server.py:7074`, protecting earlier provisional publication. Keep that guard. Policy failure still produces its current safe empty/error result; the presentation helper cannot admit unchecked cards. Breaker annotation (`:7742`) changes attributes only. Later ghost split, legacy impressions (`:7861`), F1 writer (`:7895`) and final republish must retain the helper's order; active ghost jobs are exempt from this feature. Run the same tests with signal logging on and off: first publication cannot depend on impression logging being enabled.

**Accepted #419 integration condition (`cf8cc2cc`):** `_run_trade_job` subsequently calls `_project_trade_dispositions(final_cards, ...)` after that first evaluated publication and before the final filtered snapshot and impression writers. Preserve this authoritative pass/source-interest removal. Carry the original occurrence records through its surviving subsequence, then assign final indices from the actual surviving writer enumeration. Never zip the shortened cards with stale parallel records, recreate original indices from the shortened list, or run the helper again. The ≤5 displacement, six-slot windows and class-vector invariants apply to the helper's **pre-removal permutation**; later disposition compaction can exceed that displacement without violating the presentation contract. Final snapshots and writers retain survivor relative order even when logging is disabled.

## 4. Configuration, caches and frozen provenance

### Captured mode and cache compatibility

New Float `model_config.simple_player_presentment` defaults to `0.0` in both existing default maps; exactly finite numeric `1.0` selects **`simple-player-v1`**, all unsupported/missing/invalid values select off. Booleans or malformed test inputs must not accidentally enable it. Window size **6** is fixed versioned code. Read outside per-arm config overrides; no generator or arm profile consumes it. Update the existing golden-test knob census to classify this post-generator key explicitly; do not add a fake arm-profile pin or change captured generator-output expectations.

Use one immutable `(mode, version)` capture for each logical request's reuse decision and kickoff; pass it to `_kickoff_trade_job` and the worker. Direct pregen/replenishment/internal kickoffs capture once at their entry. If a caller captures before reuse checks, kickoff must accept that same capture rather than reread the knob. Store it on the private job, not the client payload. A job started under 0 stays 0 even if the knob becomes 1 before policy publication; the reverse is equally true. Any final applicability information needed by the writer comes from that job/helper execution, not a flag/knob reread at impression time.

Compare mode/version at **all** entry reuse sites: `_trade_job_is_fresh` (`server.py:3037`), the separate running-job branch (`:13374`), session-init pregen probe (`:21051`), and replenishment cached-deck probe (`:21874`). Missing capture on a pre-feature job is compatible only with off. A mode mismatch cannot be returned as a fresh/new-request hit, including a running job; create compatible generation using the existing lifecycle without modifying old snapshots or impressions. Preserve all existing freshness/safety/fairness/outlook/intent checks. Parent reconciles existing force/supersession rules; a mode change must not mutate an old explicit-ID response into the new order.

Old-ID polls and retained client screens retain their captured order; no backfill. Distinguish the worker's **pre-freeze** #419 filter (§3.3), which determines the impression batch and final indices, from subsequent **post-freeze** poll/cache safety filtering. The latter may remove cards while preserving remaining relative order, but frozen indices still describe the batch actually written, not the later compressed response. Do not rebuild windows or rewrite impressions after removal. Rollback affects compatible fresh generation, not an already viewed deck.

### Frozen existing-column record

For enabled eligible jobs, every served occurrence receives the following record inside existing `deck_impressions.features_json.presentation`, including unmoved/locked cards:

```json
{"version":"simple-player-v1","window_size":6,"original_index":0,"final_index":0,"give_player_count":1,"receive_player_count":1}
```

`original_index` is the zero-based position in the **post-policy/pre-presentation input** and never changes after removal. Retain each surviving occurrence's record through the final #419 filter; at the actual writer boundary, `final_index` is its enumerated position in `served_final`, exactly equal to that F1 row's `card_index`. Counts are nonnegative integers when classification is known; use null for an unknown side, never a guessed zero. Removed occurrences get no new impression row. Distinct objects with identical package shapes must not collapse by trade hash. Repeated occurrences of the same object must also retain their separate occurrence records in stable order rather than collapse in a single `id(card)` record; internal identity-plus-occurrence tracking is permitted, with no new impression-ID, wire-identity or schema redesign. Never align survivors by zipping against an unfiltered metadata list. Once written, neither old-ID polling nor later filtering rewrites these indices. No additional raw player IDs or private values are introduced. Off/exempt jobs have no new presentation feature. Existing JSON-column use avoids a migration but requires data-dictionary review.

Capture the existing base serving version with the job; for applied v1 append `/pp:simple-player-v1`, then let the existing `policy_version_for_arm` append `/bo:<arm>`. Thus the whole job has one presentation version while `model_arm`, original `arm_rank`, `group_key`, original `group_rank`, `lane_slot`, actual draw propensity and the separate valuation `policy_variant` remain unchanged. Known non-bakeoff rows do not gain arm attribution. Preserve writer column uniformity across the batch (`server.py:4884`, `:4911`); when F1 logging is on but suggestion telemetry is off, version the existing serving-policy column without enabling ghost/candidate logging. In particular, the current writer derives `telemetry_on` from its existing `policy_version` argument: pass captured presentation metadata separately rather than turning that gate on just to write this suffix. No F1 flag change or synthetic impression/event when logging is off. Legacy impression order also matches, though its schema gains nothing.

These data distinguish original model rank from served exposure. They do not invent a new randomized propensity or permit unversioned before/after outcome comparisons.

## 5. Test contract — prospective, no tests run

Use `backend/tests/test_small_trade_presentment.py` plus narrow extensions to existing `test_trade_policy_wiring.py`, bakeoff serving/cache and standing-offer harnesses. Run real worker/publication/writer code with synthetic deterministic upstream outputs; do not stub the helper's expected output. Every new behavior must fail against baseline or its named sabotage, then pass after restoration. No real-user generation, external calls, repository DB, changed historical generator outputs or relaxed invariant assertions.

| Test | Mechanical acceptance | RED target |
|---|---|---|
| T1 — meaningful three-arm movement | Six final eligible Core/Value fixtures A,B,C,A,B,C have player shapes `3x3,1x4,2x3,1x1,1x2,1x1`, with valid same-arm metadata. Actual worker serves `1x1,1x2,1x1,3x3,1x4,2x3`; first-three player total falls **16→7**, arm sequence/counts unchanged, each moved card travels three slots. Final policy and helper placement are exercised. Also run group-size-zero interleaving and a real grouped fixture. | Original worker without helper; remove/move helper after publication; including original rank in class (no-op regression). |
| T2 — permutation properties | Before subsequent disposition removal: same object-occurrence multiset, packages/values/results unchanged; class vector identical at every index; max displacement ≤5; no cross-window movement; locks exact; equal keys stable; idempotence. Include >12 cards, holes/locked positions, final short window, duplicate-shaped cards, equal and all-large supply. Core lead/share and Conviction/Fallback allocation remain unchanged by the helper. | Global/sliding sort, compact-before-window, cross-class swap, dedup/drop, repeated pass. |
| T3 — classification/exclusions | Picks contribute zero, not a tie-break penalty; mixed player-for-pick can move; pure-pick/unknown/malformed/special cards cannot. Exact give/receive/opponent exclusions, demo, ghost, shadow-only, bakeoff dark validation, expected-bakeoff missing attribution/group, and genuine organic paths behave as §3.2. Explicit/manual/Win Now endpoints never invoke helper. | Count all assets, infer unknown zero/organic, omit actual fatigue marker, bypass an exclusion. |
| T4 — one first publication | Normal/forced, both formats, pregen and headless replenishment use one helper before evaluated publication. Poll at that boundary with logging on/off; absent new dispositions, first evaluated/final/cached order agrees. Hold the worker after that publication, record a pass, then release through the real final #419 filter: the passed package disappears, survivors keep order, final filtered publication works without F1, and helper call count stays one. | Impression-only reorder, early snapshot leak, separate pregen order, status-time rerank/refill, skipping final disposition cut. |
| T5 — capture/reuse/rollback | 0→1 and 1→0 invalidate completed, running, pregen and replenishment hits; unchanged mode reuses valid cache. Hold worker before publication and change knob: it keeps captured order/version. Old-ID/retained snapshots never re-sort. Missing/invalid/default-off and lookalike values are no-op. | Mid-job reread, TTL-only side cache, running-hit bypass, recapture at kickoff. |
| T6 — frozen provenance | Actual legacy/F1 writers agree with served indices; original arm/group rank, attribution/agreement, valuation variant and true propensity unchanged. Extend T4's held-worker pass/drop fixture with duplicate-shaped distinct objects and repeated same-object occurrences among survivors: each keeps its original index/count record, each written `final_index` equals F1 `card_index`, dropped occurrences have no row, and post-freeze poll removal never changes stored indices. Include locked/unattributed first row, null unknown counts, logging combinations and mid-job knob flip. No impression-ID redesign is required. | Stale parallel zip, hash/identity record collapse, rebuild original indices, second sort after filtering, post-freeze index rewrite, first-row-key omission, current-knob stamp, fabricated arm/propensity. |
| T7 — unchanged supply/goldens | Mode 0 and each exemption preserve baseline cards/order/payload/features; baseline generator/arm goldens and bakeoff drafting/accounting remain unchanged. Larger eligible packages remain reachable; zero/sparse safe supply stays honest. | Hard cap, generator profile consumption, pre-draft sort, threshold relaxation. |
| T8 — integrated regression | #419 exact current-disposition filtering, standing offers, full worker/cache/serving and policy/roster suites pass; account/league lifecycle and safety guards remain. Parent runs full backend, mobile guards/typecheck and testID lint. | Reinsert passed card to fill a slot; remove safety/policy checks. |

Record moved count, first-three/first-six player load, displacement, slot invariance and no-op rate on synthetic fixed-output decks and safely available recorded **served** snapshots. The exact T1 movement is required so a universally no-op implementation cannot pass. A real sparse-class corpus may make few moves; report that without silently widening the window or lowering locks. Neither the small research cohort nor this structural improvement is an acceptance-rate target.

## 6. Manual TestFlight and handoff

Required operator checklist, **not executed**; use an authorized synthetic/staging deck with known fixture order and record backend SHA, mode/version and actual binary:

1. Fresh organic Find a Trade produces the checked early order from T1; scroll beyond the first three and confirm the larger packages still exist unchanged. Repeat both formats.
2. Check a pick-heavy mixed fixture: picks do not make it “player heavy”; pure-pick/special cards retain their positions. No new card panel, badge or value display.
3. Repeat with explicit SEND, explicit GET, named partner, calculator edit and More Offers: original explicit packages/order remain unaffected by this helper.
4. Pass a card, use lane navigation/Find More and return Back; #419 suppression holds and no reordered/refilled old package returns merely to fill a window. New organic generation may receive its own single application.
5. Retain a deck while the operator changes the staging knob, then poll/return to that old result: captured order remains. A fresh compatible generation takes the new mode; repeat rollback to 0. No production flag/config mutation is part of the test itself.

Parent sequences the backend helper and narrow `server.py` publication/cache/writer changes after #419. `trade_service.py` and `database.py` edits are neutral default registration only, not generator logic. A leaf helper is allowed; no new service/client/route/schema, fourth arm or extra knob. Scope assigns shared config/API/data/architecture/LLD/decision/index/ledger updates to the integrator. Original planner approved `07d98473` without baseline blockers; root approved revised `5171f13a` with the accepted `cf8cc2cc` integration condition. Existing batch release authorization is conditional on QA; default-off code and later activation are separate recorded facts.
