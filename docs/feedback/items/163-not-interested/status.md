# #163 — "Not interested in this player" flag — status

**Status: built (backend + client plumbing; menu mount by screen owners)** · 2026-07-25 · branch `teardown-remediation` worktree

Tester: "Add a not interested in this player flag? Eg I don't want Tyler Warren."

## Design

Third `asset_preferences` list (FB-95 pattern, same `trade.preference_lists` flag): `list_type='not_interested'` — players the engine must **never offer TO the user** (receive-side hard exclusion). The give side is untouched: the user can still trade the player away. Single membership per (user, league) player, `'none'` removes — identical semantics to untouchable/target.

## Backend

- `backend/database.py` — `ASSET_PREF_LISTS += ("not_interested",)`; `load_asset_preferences` returns the third list (`{"untouchables": [], "targets": [], "not_interested": []}`).
- `backend/server.py` — asset-prefs GET/POST accept/return the list (validation comes free from `ASSET_PREF_LISTS`; docstrings updated); `_run_trade_job` loads `not_interested_ids` and threads them into `generate_trades` and `_inject_likes_you_cards` (a counterparty like whose give side intersects the list is skipped — their give IS the user's receive).
- `backend/trade_service.py` — `not_interested_ids` threaded `generate_trades` → `_generate_trades_v2` → both pair generators; receive pools filtered **at the source** (`_known_opp` in the divergence generator; `_opp_pool` in the consensus generator), so the pinned-receive/target re-add loops (which iterate the filtered lists) can never re-admit an excluded player — exclusion always wins, even over a conflicting `target`/pin.
- `backend/trade_optimizer.py` — v3 `known_opp` filtered the same way; `_try_sweeten` never picks a receive-side sweetener from the list (mirrors the give-side untouchable rule).
- Legacy (flag-off) engine ignores it, exactly like untouchables/targets (#2 is v2-only).

## Mobile

- `mobile/src/api/league.ts` — `AssetPrefs.not_interested?: string[]` (optional: absent on pre-#163 servers, treat as `[]`), `AssetPrefList` union gains `'not_interested'`, `setAssetPref` typed accordingly.
- `mobile/src/components/PlayerContextMenu.tsx` — exported `notInterestedAction({leagueId, playerId, isNotInterested, onDone?, onError?})` factory: the canonical "Not interested" / "Remove not interested" `PlayerMenuAction` (copy + hint + API call + testID keys `player-menu.not-interested-add|remove`, matching the registry grammar). The menu's actions are caller-supplied by design, and the mounting screens (TradesScreen / Matches tiles — other-roster players) are owned by other agents: they mount the factory + own refresh/toasts. tsc clean.

## Docs

`docs/api-reference.md` (asset-prefs rows), `docs/cross-client-invariants.md` (list-type enum), `docs/glossary.md` ("Not interested").

## Tests

`backend/tests/test_not_interested.py` (9): storage round-trip + single membership + unknown-list rejection; receive-side exclusion on v2 divergence AND v3 (parametrized, with a baseline proving the player IS offered untagged); give side untouched; consensus-path exclusion; exclusion beats a conflicting target re-add; likes-you injection respects the list; route enum/GET shape. Existing `test_asset_preferences.py` exact-shape assertion updated for the third key (intended contract change).

Full backend suite: **1105 passed, 1 skipped** · `cd mobile && npx tsc --noEmit` clean.
