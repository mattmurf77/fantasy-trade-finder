# Code-walk — the Shop tile's send, on each platform (D-056 evidence)

Traced at `ab9879bd` (branch `fix/trades-531-shop-platform-send`). File:line references are mobile-relative (`mobile/src/…`) unless they say `backend/`.

## The entry: the Shop tile

- `components/ShopOffersBody.tsx:1046`: the tile's primary action is `<SendInSleeperButton>`, with:
  - `leagueId` (the window's league);
  - `theirUserId = item.counterparty_user_id`;
  - `give/receivePlayerIds = item.give/receive_player_ids`;
  - the names from `item.give/receive`;
  - `opponentUsername`;
  - `surface="shop"` and `compact`.
- The ✕ dismiss beside it is unchanged (`handleDismiss` → the held `swipeTrade(..., 'pass', ..., 'shop')`).
- **Nothing in the body calls `queueCalcTrade` or names `/api/trades/queue`** (`tests/check-shop-send.js`). So no deck queue, no likes-you card for @name, and no Elo signal.

## The router: `components/SendInSleeperButton.tsx`

- **`:165`:** `platform = resolveSendPlatform(leagueId, leagues)` (`utils/tradeText.ts:28`) decides by the league's platform in the session cache.
- **`:490`:** MFL with `trade.send_in_mfl` on → `<SendInMflButton>`, with the same ids, `surface` and `sendPreCheck`.
- **`:511`:** ESPN with `espn.send` on → `<SendInEspnButton>`, likewise.
- **`:533`:** `trade.send_in_sleeper` off → nothing renders, on every platform but MFL (that flag is the whole component's kill switch, as on every other mount).
- **`:541`:** a platform that can't send (e.g. Fleaflicker, or ESPN with its flag off) → `send-in-sleeper.unavailable`: the `NO_SEND_REASON` line and a "Copy trade" button. Nothing is sent.
- **Today:** `config/features.json` has `trade.send_in_sleeper`, `trade.send_in_mfl` and `espn.send` all `true`.

## Sleeper

1. **The tap** → `confirmSend` (`:382`): the link check, then the `/api/trades/validate` pre-flight (#180). Warnings show "This trade will likely fail" / "Heads up before sending" with Send anyway or Cancel. Then the "Send this trade?" alert (`:406`).
   - `track('sleeper_send_attempted', {surface: 'shop', …})` fires at `:429`.
2. **Send** → `doPropose` (`:254`) → `proposeTradeToSleeper` (`:257`, `api/sendInSleeper.ts:203`) → `POST /api/trades/propose` (`backend/server.py:24892`), the GraphQL propose. It encodes league picks server-side (D-176).
3. **Success** → "Trade sent / Check your Sleeper app for the pending offer." (`:277`).
4. **Failure** → `track('sleeper_send_failed', {surface: 'shop', error_code, …})` (`:289`), then the existing per-code alerts:
   - not linked / expired → "Connect Sleeper first";
   - `verification_required`;
   - `sleeper_rejected`;
   - the roster and pick codes (`sleeper_pick_unmapped`, `_untradable`, `_not_owned`);
   - otherwise "Couldn't send".
   - **There's no outcome-unknown state on Sleeper:** a timeout shows the generic "Couldn't send", as on the deck, Matches and calculator mounts.

## MFL (`components/SendInMflButton.tsx`)

1. **The tap** → its `confirmSend` (`:213`): the shared validate pre-flight, then "Send this trade?" (`:257`).
2. **Send** → `proposeTradeToMfl` (`:124`, `api/sendInMfl.ts:78`) → `POST /api/trades/propose-mfl` (`backend/server.py:38472`). Picks ride along.
3. **Outcomes:**
   - "Trade sent / Check MFL for the pending offer." (`:141`);
   - a timeout, no answer, or the server's `mfl_outcome_unknown` → the outcome-unknown alert (`:145` / `:153`, `SEND_OUTCOME_UNKNOWN_TITLE`, #513 / #527 / #539), with the per-trade state in `api/sendRegistry.ts`, so a second tap can't double-send;
   - otherwise the per-code alerts (re-link, unmapped asset).
4. **Analytics:** it takes `surface` but fires no events of its own today, as on every mount.

## ESPN (`components/SendInEspnButton.tsx`)

1. **The tap** → its confirm: the pre-flight, then "Send this trade?" (`:304`).
2. **Send** → `proposeTradeToEspn` (`:165`, `api/sendInEspn.ts:87`) → `POST /api/trades/propose-espn` (`backend/server.py:39080`). Players only.
3. **Outcomes:**
   - "Trade sent / Check ESPN for the pending offer." (`:182`);
   - outcome unknown → `:194`, as for MFL;
   - **any pick in the trade → 422 `espn_pick_unsupported`** (`:216`): the existing "can't send picks" alert, and nothing partial is sent;
   - a crosswalk miss → `espn_asset_unmapped`.
4. **Analytics:** no events of its own today, as on every mount.

## What changed vs main

- **Before:** the Shop tile's button "Show it to @name" called `queueCalcTrade` → `POST /api/trades/queue`. That queued the trade into @name's Fleeced deck as a likes-you card, moved the Elo board (Ruling A), and fired `calc_trade_queued` (screen `ShopAsset`) and, server-side, `trade_proposed` (source `calculator`). Nothing reached the platform.
- **After:** the platform paths above. Analytics: only the Sleeper send events carry a `surface`, now `shop` from this mount.
