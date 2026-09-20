# Independent bilateral validation

September 20, 2026. Implementation baseline: fresh-main `659a6332`, isolated `codex/owner-v2-bilateral` worktree. This record reports local implementation checks. It does not establish a deployment, device acceptance, or actual two-manager acceptance.

## Result

**76 focused checks passed in 2.97 seconds:** 38 independent bilateral contracts, seven model-transition overhaul contracts, and 31 existing overhaul API/store checks. `git diff --check` passed. The parent owns the broader suite, exact-head CI, production verification and release ledger.

The independent contracts use synthetic boards and rosters and the public `generate_bilateral_trades` / `evaluate_bilateral_trades` entry points. They do not replace the scoring implementation with mocks. Overhaul transition tests reuse the existing Flask route harness, an in-memory SQLite database and a synthetic generator to isolate persistence, request identity and historical evidence behavior.

| Contract | Evidence | Result |
|---|---|---|
| Weaker side outranks viewer-only windfall | `test_bilateral_contracts.py:69`: equal market prices; a large viewer gain with almost no counterparty preference support loses to the balanced alternative | Pass |
| Personal intent remains a primary requirement | Board flip changes focal candidates; a neutral real board has no organic offer; an explicit request remains eligible | Pass |
| Intent does not increase the price | Increasing personal target value leaves the exact package's market prices unchanged; extreme overpay is rejected | Pass |
| Deliberate rankings retain authority | Explicit, votes, cross-format and legacy sources produce the same packages/support; seed rows do not fabricate preference | Pass |
| Tiers remain personal | A personal tier-up survives despite downward market-price direction; the raw board is not mutated | Pass |
| Missing counterparty evidence remains honest | Cold-start counterpart remains eligible; private evidence says unknown with consensus fallback; scores explicitly say not probabilities | Pass |
| Request/ownership authority | Full selected terms first, honestly labeled partial alternatives, authenticated partial proof, own-send untouchable override without changing saved tags, invalid owner selections rejected | Pass |
| Minimal sufficient consideration | Adding a gift to the already stronger manager is omitted when the simpler exact deal is sufficient | Pass |
| No total-output cap or diversity deletion | All 121 feasible distinct one-for-one pairs survive an 11-by-11 case, including `max_cards=1` | Pass |
| Tanking/pick rules | Verified own-next-draft pick protected organically; own send selection overrides; viewer GET does not authorize the opponent's sale; expired selected pick rejected | Pass |
| RB exceptions | Favored young RB requires a genuine signed market discount; old or unknown-age prospects fail; configured two/three/four-plus-first personal tiers permit elite exceptions | Pass |
| Frozen proof/privacy | Detached evidence cannot mutate the original; changes in price/terms fail its binding; public card has no private boards or numeric support components | Pass |
| Legacy preservation | Invoking the new engine does not alter old-generator packages, decision evidence, report, inputs or configuration | Pass |
| Invalid tolerance | NaN, infinity, booleans and out-of-range fairness inputs produce no offers | Pass |
| Overhaul selector transition | Old undecided inventory becomes stale, existing decisions remain, exhausted subsets reset, fresh evidence uses new occurrences and original evidence remains unchanged | Pass |
| Overhaul rollback/settings/concurrency | Rollback/reactivation and changed bilateral settings get new occurrences; selector changes during context capture/publication fail closed; stale-ID likes are refused and cannot populate a roadmap | Pass |

Test source: [independent core contracts](../../../backend/tests/test_bilateral_contracts.py), [overhaul transition contracts](../../../backend/tests/test_bilateral_overhaul.py). These are behavior checks, not labeled human responses.

## Source review and resolved findings

The initial trace found a static Team Overhaul generator binding and an owner-only cache signature that did not distinguish the new model. Both needed explicit integration beyond deck generation. The wiring now selects the generator and evaluator from captured configuration (`backend/bakeoff_runner.py:279`), stamps model identity in cached jobs (`backend/server.py:3141`), validates owner proof at final publication (`backend/server.py:14460`) and dynamically dispatches Team Overhaul (`backend/server.py:31968`). These line references are source-review evidence; they are not a production execution trace.

Overhaul now compares persisted card model/version identity before exposing undecided inventory (`backend/overhaul_api.py:396`). Model transitions reset search exhaustion and create a stable cache epoch for the new generation. Exact-package identity remains separately captured as `canonical_package_hash` in private evidence. Prior likes/passes suppress identical terms across versions. A transition never overwrites a historical card or its valuation evidence. Existing store helpers were sufficient; no database schema or `overhaul_store.py` changes were needed.

Parent review additionally identified selector changes during context capture and stale write requests by offer ID. Both are covered: a changed selector returns `409 generation_changed`; an old undecided offer returns `409 stale_offer` before a new decision is persisted. Prior decided offers remain available on their original terms. The service's assembly/prepare checks require a liked, fresh offer; an undecided old ID cannot bypass review by entering a roadmap directly.

The post-generation likes-you/standing-offer path intentionally retains real inbound exact terms and their original source-like attribution. It is not a fallback generator and must not acquire fabricated bilateral evidence or new-arm attribution. Existing structural roster checks remain separate from preference support. User disposition suppression remains a distinct contract from near-tie diversity ordering.

## Sabotage checks

Two named controls were run in isolated Python processes with runtime-only patches; no sabotage was written to repository files:

- **Viewer-only ordering:** replacing the final ranking with descending viewer support caused `test_weaker_side_leads_over_a_larger_viewer_windfall` to fail: `windfall` appeared before `balanced`.
- **Ignored overhaul model identity:** removing the installation callback caused `test_switch_hides_only_undecided_old_inventory_without_mutating_get_history` to fail: four old undecided rows remained in fresh inventory.

The unmodified implementation subsequently passed the complete 76-check focused run above.

## Reproduction

Run from the repository root using an isolated test database and the checked-in market fixtures. The model itself performs no provider/database reads. `FTF_TEST_MODE` prevents missing provider fixtures from falling through to the live service.

```sh
validation_dir=$(mktemp -d /private/tmp/bilateral-validation.XXXXXX)
DATABASE_URL="sqlite:///$validation_dir/test.db" \
FTF_TEST_MODE=1 \
FTF_SLEEPER_FIXTURES_DIR=backend/tests/fixtures/sleeper \
FTF_PLAYERS_CACHE_FILE="$validation_dir/players-cache.json" \
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
python3 -m pytest \
  backend/tests/test_bilateral_contracts.py \
  backend/tests/test_bilateral_overhaul.py \
  backend/tests/test_overhaul_api.py \
  backend/tests/test_overhaul_store.py -q
```

The local runtime was Python 3.14; required CI also validates the repository's configured Python version. Test databases/cache paths are local scratch, never production.

## Limits and remaining runtime checks

- Support weights, thresholds and uncertainty ranges are explicit launch-policy parameters. They were not fitted to 44 owner judgments, completed trades, or paired acceptance outcomes.
- Synthetic verified opponent boards test behavior. They must not be represented as factual opponent rankings in captured owner replays. The available owner snapshots do not establish counterparty personal boards or acceptance.
- This initial model uses the captured existing market reference. No DP/Tradesourced blending winner is selected, and changing a future market reference requires separately frozen personal-board/intent comparisons.
- Computational pools and evaluation budgets remain; an uncapped returned inventory does not mean exhaustive enumeration.
- Physical-device checks remain unexecuted here: switch with an already-open deck then refresh; fresh organic search; selected send/get and partial labels; More Offers; league buy/sell; Team Overhaul reopen/generate after switch; preserve old liked terms; like the same exact package from both real managers and verify attribution/undo/expiry. Verify returned cards carry the new generator while old history keeps its original identity. Actual paired acceptance requires those managers' app interactions.
