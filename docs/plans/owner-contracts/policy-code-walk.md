# Owner contracts — bounded policy implementation and evidence

2026-09-05. Built on fresh `origin/main` `5cf34182374a80159e13d22ba7989eba1697b6ff`; not pushed, merged or deployed by this subagent. Read alongside [scope](policy-scope.md). The confirmed owner handoff in the shared project root supersedes the historical brief; unresolved rules are not inferred here.

## Implemented

| Contract | Code path | Evidence |
| --- | --- | --- |
| User tier defines the existing intent lens | `backend/trade_service.py:4644` `_best_tier_idx` accepts raw user Elo and falls back to the seed only for the absent ID; `:4671` uses that map without seasonal/outlook transforms. | `test_owner_policy_contracts.py:30` deliberately reverses market/personal direction on a partial board. `:131` checks four outlook choices cannot redefine it. |
| All existing generator entry paths use that direction | `trade_service.py:4956`, `:5023`, `:5121` pass raw `user_elo` into the final intent filter. Direct `gen_v2_cards` / `gen_fit_cards` adapters at `backend/bakeoff_runner.py:1267` and `:1397` pass the same raw argument. | The adapter tests were RED before the two argument-only corrections. No profile, generation math, cap, gate or arm enablement changes. |
| Same value uses personal tier, not market tier | `trade_service.py:5510` tier lookup for `lateral_scope="tier"` uses `raw_user_elo`, with per-entry seed fallback. | `test_owner_policy_contracts.py:86` covers SEND/GET directions, a partial board and different positions explicitly selected through the existing picker. |
| Market still prices the package | The untouched consensus accessor at `trade_service.py:5438` feeds `_price` / `price_consensus_package` at `:5562`. | The Same value tests assert the outgoing market value is 1,000 while incoming market value is 3,490.3, even though personal tiers match. |
| Known deliberate methods have equal authority in the **dark policy** | `backend/trade_policy.py:160` gives explicit/cross-format and positive-count votes full authority; seed/absent evidence gets no fabricated declaration. `:192` accepts per-player `sources` and prioritizes it over majority-source / historic fractional weights. | New method-parity and mixed-provenance tests; existing persistence test now expects equal authority for a compared and a manually placed player. |
| Preserve each side's partial personal board in the policy evaluator | `trade_policy.py:791` binds raw/effective callbacks; `LeagueMember.confidence_sources` at `trade_service.py:4444` supplies row-level provenance. Parent integrates the existing-column database/server read map. | `test_pair_policy_falls_back_per_missing_entry_on_each_board` proves each side retains its own supplied entry, gets actual consensus for the other, retains zero source weight for fallback, and does not mutate either original board. |

No private tier payload fields are added. Existing privileged valuation snapshot and policy/generator attribution remain in place. This slice does not modify loss limits, deck composition, confidence labels or the definition of a winning experimental arm. The dark policy retains its historical numeric rules pending separate owner-aligned pricing design; its module header now identifies those as historical implementation, not current owner-approved policy.

## Preserved and explicitly incomplete

1. **Live method authority is not fully corrected.** `trade_service._shrink_user_elo` remains byte-identical to baseline, including `n/(n+n0)` and its placement clamp. An attempted common-function correction broke arm-A historical `92c31d5` goldens and pin/unpin goldens. Parent required preserving all profiles: only this agent's live-function/test edits were restored via `apply_patch`; no golden was regenerated or weakened. A separately scoped, arm-safe policy treatment is needed. Explicit tiered copy/import entries already reach `placement_bands`; historic below-tier/no-value override provenance is unresolved.
2. **Full generator candidate fallback is not corrected.** v2 (`trade_service.py:7113`), v3 (`trade_optimizer.py:418`) and gen_v2 (`trade_gen_v2.py:544`) still require pool assets on both boards; missing accessor values can use the old 1500 placeholder. The existing policy evaluator's per-entry fallback is verified, but that does not make these candidate-universe restrictions compliant. A proposed multi-generator overlay was rejected by safety review and was not applied; parent explicitly deferred it.
3. **Asset-ideas direction is only partly corrected.** Tier-scope Same value is personal. Upgrade/Downgrade still use existing market-band conditions (`trade_service.py:5735`, `:5765`, `:5850`). The post-generation deck intent filter is personal-tier based. Within-tier upgrade thresholds/close-value bands remain unresolved; none were invented. Implicit same-position constraints remain at `_pos_ok` / `_head_ok` (`:5481`, `:5495`); explicit user-selected position filters remain intact. A combined broader source/position patch was rejected and not applied.
4. **Untouchable is still a hard exclusion.** Existing sites include asset-ideas `trade_service.py:5690`, v2 give pools, v3 `trade_optimizer.py:420`, and gen_v2 `trade_gen_v2.py:548`, plus sweetener exclusions. Existing partner/outlook prioritization (`partner_fit_score`, `outlook_direction_mult`) is retained. No arbitrary untouchable premium, new binary formula or reinterpretation of Not interested was added. The soft-reluctance gate requires a separate precise proposal.
5. **Stud tax is held pending the owner answer.** Service/database already default to Market, allow Heavy/Off, and Off bypasses package adjustments. Recommendation sent to parent/mobile: accept legacy Off as an alias of existing Market on read/write, preserve Heavy and avoid a bulk rewrite. No Off normalization or UI change was made by this slice. Parent owns approved database/route handling if the answer arrives.
6. **Pick scope audited, not invented.** `pick_values.priced_pool_value:683` checks a supplied known slot first (`:736`–`:740`), then market-round value and the existing first-round YoY floor. No new early/mid/late slot projection was found in the inspected policy/service/pick pricing paths, so no next-year-only forecast can be claimed implemented. Existing further-year/round decay and market source rules were preserved; the owner-aligned no-discount/projection contract needs separate review. No database or external data query was run.

Safety-review reasons are recorded rather than bypassed: the first broader patch combined core generation/position changes; the second combined candidate-universe fallback changes with historical placement-test revisions and was assessed as a recommendation/regression-masking risk. The narrower test-only revision was permitted after parent review, then all associated live-function and placement-test edits were restored when unchanged historical goldens exposed the deeper experiment boundary. Neither rejected candidate patch entered the final diff.

## Actual verification

Interpreter: `/private/tmp/ftf-context-venv/bin/python`, Python **3.12.14**. No production database, network, simulator or Maestro use.

- Initial new-contract run before implementation: **8 failed / 3 passed**, exposing the expected source/authority gaps. The ultimately deferred live-shrink assertion was replaced by an independent dark-policy assertion; it is not claimed as live evidence.
- Final retained implementation, before the two adapter-only argument additions: **412 passed in 47.56s** across the 14 files below. This includes untouched arm-A, challenger and pin/unpin golden fixtures.
- Named process-local sabotages: **method hierarchy restored**, **personal intent argument dropped**, **asset-ideas personal board dropped**. The selected tests produced **6 failed / 1 passed / 9 deselected**. Fresh clean process afterward: **16 passed**. No sabotage edited a file.
- Direct-adapter source tests before correction: **2 failed / 16 deselected**. After the two argument-only corrections: **83 passed in 12.80s** across `test_owner_policy_contracts.py` (now 18 tests), `test_trade_intent_modes.py`, `test_bakeoff_arm_a_golden.py` and `test_bakeoff_serving.py`.
- `git diff --check`: passed.

The 14-file passing command used `python -m pytest -q` on:

```text
backend/tests/test_owner_policy_contracts.py
backend/tests/test_placement_tier_clamp.py
backend/tests/test_trade_intent_modes.py
backend/tests/test_trade_policy.py
backend/tests/test_trade_policy_wiring.py
backend/tests/test_trade_engine_v2.py
backend/tests/test_trade_optimizer.py
backend/tests/test_trade_gen_v2.py
backend/tests/test_asset_ideas.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_trade_gen_fit.py
backend/tests/test_bakeoff_challenger.py
backend/tests/test_override_pin_unpin.py
backend/tests/test_pin_tier_bounded.py
```

Parent owns the integrated full backend suite, mobile structural/type checks, test-ID lint, central index/docs and test ledger. Local evidence is not a claim of pushed-SHA CI or a release.

## Focused operator TestFlight checks — unrun

1. Give one owned player a lower personal tier than an incoming target despite the reverse market ordering. Select Tier up: any served card under that intent must follow the personal direction. Repeating with another declared outlook must not turn seasonal utility into the tier classifier.
2. With SEND then GET entry points, select an explicit applicable swap position and two assets sharing a personal tier but differing market tiers. Same value should follow the personal tier; calculator/companion prices should still reflect the unchanged market package calculation. This does not claim implicit position restrictions or Upgrade/Downgrade bands have been corrected.

## Privacy follow-up — known public counterparty values

Parent-approved amendment, 2026-09-05. This follow-up does not implement the separately reported offer-expiry/original-valuation gaps.

- `backend/trade_gen_v2.py:999` retains the exact internal `counterparty.own_board_gain`; `:944` retains `meso_variants[].recipient_value_delta_pct`, computed from the recipient's own-board package values. These values still exist for generator evaluation and internal tests. `:1173`/`:1178` confirm that the current timeline has categorical outlook and declared/inferred source only, not numeric personal ranking values.
- `backend/server.py:13172` copies rationale and its counterparty dictionary, omitting only `own_board_gain`. `:13183` copies MESO dictionaries, omitting only `recipient_value_delta_pct`. The viewer's own number, current qualitative roster-fit/timeline explanation, variant package IDs and shape remain unchanged. No mutation of the underlying card, generator math, telemetry, DB or flags.
- The real `GET /api/trades` handler (`backend/server.py:13936` after this patch) runs pending cards through that shared serializer; background deck publication, liked cards and swipe-card replies already call the same boundary. This change certifies the two identified fields, not every endpoint or possible future payload field.
- Tracked mobile/web/extension search found no consumer or wire type for either structure or numeric key. `mobile/src/api/trades.ts:54` normalizes known card fields without carrying rationale or MESO data. The exact affected public card example in `docs/api-reference.md:354` now describes the redacted shape instead of promising counterparty gains/deltas.

Actual evidence (Python 3.12.14, no network/production DB):

- `backend/tests/test_trade_card_privacy.py` against the original **unredacted-public-counterparty-values** behavior: **4 failed / 1 passed in 4.47s**. Failures individually exposed each field, response/card separation, and the real authenticated GET response; the ordinary no-rationale/variant case already passed.
- After the boundary-only fix: **148 passed in 22.61s** across `test_trade_card_privacy.py`, `test_trade_gen_v2.py`, `test_gap_sweetener_arm_c.py`, `test_bakeoff_arm_a_golden.py`, `test_bakeoff_serving.py`, and `test_trade_policy_wiring.py`. Internal generator assertions and historical goldens were not changed.
- `git diff --check`: passed. Parent owns the integrated test ledger and full-suite rerun; no pushed-SHA CI or release claim.
