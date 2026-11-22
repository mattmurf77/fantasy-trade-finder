# Feature Scope — Home's next move (one player, one action)

**Date:** 2026-11-21
**Entry point:** direct ask (operator, 2026-11-21, through the main session): "suggest 1 player to buy or sell that improves their team outlook driven priority the best (so either reduce max PF or increases playoff odds)", using "the playoff probability and Max PF moves and the currently set team outlook".
**Builder:** builder subagent on `feat/home-next-move` (D-278)
**Operator sign-off on waivers:** GIVEN 2026-11-21. The operator answered "Yes, sign off" to the main session's question naming the one analytics waiver (§1 (c), no impression event), before the merge of PR #710. Recorded after the merge so the PR's checks did not restart.

---

## What the user sees

New server flag **`league.next_move`** (code default false, shipped true). With it on, Home shows one row directly under the playoff card when, and only when, there is a move to suggest:

| Card's direction (`team_direction.primary`) | Row | Tap |
|---|---|---|
| Draft pick | "Next move" / "Sell R. Sato (WR): projected pick 1.06 → 1.04" / "Find trades ›" | Find a Trade with R. Sato on the give side, exactly as his row's "Find trades" on Improve Draft Pick |
| Playoffs | "Next move" / "Buy D. Ortega (RB) from Sellers FC: playoff chance 55% → 63%" / "Find trades ›" | Find a Trade with D. Ortega on the receive side and his team as the partner, exactly as his row's "Find trades" on Improve Playoff Chances |
| Neither, or no move to suggest | nothing (no placeholder, no error text) | — |

The direction is the card's own: the server's `team_direction.primary`, which follows the saved team outlook and the playoff chance (D-270's 45% lean, Rebuilding / Tanking saved outlooks lean to the draft pick). There is no second way to pick it.

With the flag off: no block on any read and Home exactly as before. League rankings, the card's other host, never shows the row.

## The rule: when it suggests, and when it does not

The block names the **first row** of the list the direction opens, and only when that list would show that row first, with its "Find trades" button, with nothing in front of it, right now. It never falls back to the second row on its own (one exception, below).

Checked on the server (`backend/league_projections/next_move.py`), in this order; the first that applies gives `state: "none"` with that `reason`:

| Reason | When |
|---|---|
| `direction_off` | no `team_direction` block on the read (`league.direction_card` off) |
| `unavailable` | `team_direction.state` is not `ready`: no forecast, update pending, stale, refresh failed, older model, incomplete, team not found, a non-Sleeper league (`unsupported`) |
| `no_direction` | `primary` is null (neither direction offered) |
| `not_offered` | the primary direction is not offered (defensive; `primary` is always an offered one) |
| **Draft pick (sell)** | |
| `no_moves` | no `max_pf_moves` block, its state is not `ready`, or it has no rows |
| `pick_owned_elsewhere` | another team owns the pick (the list sits behind "Show anyway") |
| `collapsed` | the list starts behind "Show moves": playoff chance over 45% with no saved Rebuilding / Tanking outlook. Happens when the card leads with the draft pick only because the playoffs are not offered |
| `settled` | the team has clinched (a sell cannot matter) |
| `keep` | the first row is a player marked Keep (no "Find trades" on that row) |
| `below_threshold` | the first row does not move the pick by a visible amount (`passes_threshold` false) |
| **Playoffs (buy)** | |
| `no_targets` | no `playoff_targets` block, its state is not `ready` (this covers `clinched`, `eliminated`, `near_certain`, `no_sellers`, `after_trade_deadline`, `season_over`), or no rows |
| `settled` | clinched or eliminated (defensive; the block's state already says so) |
| `below_threshold` | the first row does not raise the chance by a visible amount |
| `read_failed` | composing the block raised (the forecast and the other blocks are still served) |

The draft-order question does not hide anything: the Max PF list shows it above its rows, and the card still shows the projected pick, so an unanswered question still gets a suggestion. Answered `reverse_standings` or `lottery_or_other`: `max_pf_moves` is `draft_order_not_maxpf` with no rows, `team_direction` does not offer the draft pick (reason `draft_order_not_maxpf`) and serves no projected pick, so the primary is the playoffs if offered (a buy) or null (`no_direction`); a sell, and with it a projected-pick line, cannot occur.

The one exception to "never the second row": the read already drops the Playoff targets rows of a team that is no longer selling, so the served list can start at saved rank 2. That is the list's own first row, so it is the move.

Checked in the app (`mobile/src/utils/homeNextMove.ts`), because the forecast read never fetches live rosters; the lists make the same checks with the same `['league-rosters', leagueId]` query:

- **Sell:** the viewer's live roster must be loaded and the suggested player must still be on it (the list drops a row whose player left). Other adds and drops do not matter.
- **Buy:** the rosters must be loaded, the player must still be on the seller's live roster, and that team must have a live owner (the list row has no "Find trades" without one).

When an app check fails the row shows nothing. It never shows the second row instead (the client decides nothing about ranking).

## 1. Analytics scope

- [x] **(b) Existing events cover it, with one new `tile` value:**
  - `home_tile_tapped {tile: 'next_move'}`, screen Home, fired on the tap before anything else. `next_move` is a new value in the documented closed `tile` vocabulary (`backend/analytics_taxonomy.py`); no new prop, so the ingest allowlist is unchanged. It is counted apart from every other tile.
  - The hand-off that follows is the list row's own `finder_target_pinned` (sell: `side: give, source: maxpf_moves`; buy: `side: receive, source: playoff_targets`), with screen **Home** (the lists log it under Standings or the Improve page's route). Buy vs sell is read from it.
  - Questions answered: how often the suggestion is taken (taps), which action, and whether it led to a trade search (`finder_target_pinned` → the finder's own events).
- [x] **(c) WAIVED, operator sign-off 2026-11-21 ("Yes, sign off"): no impression event.** Nothing records that the row was shown, so a tap-through rate cannot be computed (taps are countable; the denominator is not). `direction_card_shown` fires for the card but does not say whether a move was shown. Adding a prop to it, or a new `next_move_shown` event, is a small follow-up if the operator wants the rate.

## 2. Schema & flag scope

- New/changed tables or columns: none. Nothing is saved; the weekly job is unchanged.
- New feature flag: **`league.next_move`**. Code default False (`backend/feature_flags.py` `FLAG_KEYS`); shipped **true** in `config/features.json` (with `_comment_league_next_move`) and mirrored in the three flag fixtures (`release`, `onboarding-v2`, `profiles-on`) and the mobile compiled defaults (`state/useFeatureFlags.ts`), the pattern `nav.home_return_unified` used. Read by the forecast read (`api.py`, the only `is_enabled("league.next_move")`) and by the app. Requires `league.direction_card` (without its block the answer is `direction_off`). Not added to `FTF_FLAGS`.
- Rollback: `league.next_move` false + `POST /api/feature-flags/reload`; no build needed. Graduation: after one TestFlight cycle with the §9 checklist passed.
- New env vars / `model_config` keys: none. No setting in `config/league_projections.json` changed.

## 3. The `next_move` block (contract)

Served on `GET /api/leagues/<id>/projection-runs/latest` as `next_move` while the flag is on. Composed after `team_direction`, from the three blocks the same read serves; pure, no I/O. The same keys in every state.

```json
{
  "version": 1,
  "state": "ready",                     // "ready" | "none"
  "reason": null,                       // null when ready; a reason from the table above when none (an open set)
  "direction": "draft_pick",            // "draft_pick" | "playoffs" | null (null before a direction is known)
  "action": "sell",                     // "sell" | "buy" | null
  "player": {"player_id": "101", "name": "Rhett Sato", "short_name": "R. Sato", "position": "WR"},
  "rank": 1,                            // the chosen row's saved rank
  "seller": null,                       // buy: {"roster_id": 4, "name": "<the targets block's seller.name>"}
  "captured_at": "2026-11-17T14:00:00Z",
  "playoff_probability": {"now": 0.30, "after": 0.22},          // the chosen row's
  "playoff_proof": {"playoff_clinched": false, "playoff_eliminated": false},  // the block baseline's (D-262)
  "pick": {"now": "1.06", "after": "1.04"},                      // sell: the row's projected pick (`label`); buy: null
  "most_likely_pick": {"now": {...}, "after": {...}},            // sell: the row's D-263 pair when present; else null
  "top3_probability": {"now": 0.20, "after": 0.31}               // sell: the row's; buy: null
}
```

When `state` is `none`, every field after `direction` is null.

## 4. Where it renders, and what a tap does

- `mobile/src/components/home/HomeNextMove.tsx`, mounted by `HomeHub` directly under `HomePlayoffBanner` (Home only). Card construction (ink-1, hairline, radius md), one `Pressable` row ≥ 44pt: the label "Next move", the one line, and `RowAction` "Find trades ›". testIDs `home.next-move`, `home.next-move.line`. It reads the card's cached forecast (same key, fetcher and staleTime) and HomeHub's shared rosters query: no new request.
- Tap (`HomeHub.onNextMove`): `track('home_tile_tapped', {tile: 'next_move'}, 'Home')` → `armReturn('next_move')` (the "‹ Home" bar on Trades, as the "Find a trade" tile; `navContinuity.homeReturnTabFor`) → `utils/homeNextMove.nextMoveTap`, which runs the list row's own hand-off (`maxPfMoves.handOffToFinder` / `playoffTargets.handOffToFinder`): the same finder pins, the same `finder_target_pinned`, and the same params (`finderNavParams`: Trades › TradesHome, `canvasPrefill`, `pop: true`). The pages are root-stack pushes and reach the tab with `popTo('Main', params)`; Home is inside the tabs, so it calls `navigation.navigate(params.screen, params.params)`: the same destination and params.
- No second link to the full list: the card's "View ›" already opens the half sheet whose rows open both Improve pages.

## 5. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-home-next-move.js` (`npm run test:home-next-move`) EXECUTES `utils/homeNextMove` with the real list utils and RENDERS `HomeNextMove` against stubs: which block is honoured; the sell line and its three wordings; the live-roster check (the named player still on your roster); the buy line, the seller's roster and owner; nothing for every `none` reason, flag off, rosters not loaded, a non-Sleeper league; the tap's pins / event / params equal the Improve page row's hand-off (screen Home); track → arm (Trades) → navigate in `HomeHub`; mounted once directly under the card; League rankings and the card itself unchanged; the copy table equals §7 both ways; the flag's mirrors. `check-home-hub.js` (tile vocabulary) and `check-nav-continuity.js` (the tap arms Trades) gain `next_move`.
- [x] **Unit tests:** `backend/tests/test_next_move.py` (the pure composer: both directions, every `none` state, the saved outlook, never a player the list would not show first, the real fixture blocks), `backend/tests/test_next_move_read.py` (flag off byte-identical, the block on the read equals the composer over the served blocks, gates on the read, `read_failed`, the flag's registration / shipping / client default / single reader), `backend/tests/test_next_move_analytics.py` (the tile documented, props unchanged, the tap and the hand-off land with screen Home).
- [x] **Code-walk proof:** the read composes after the direction block (`backend/league_projections/api.py:249-250`, `next_move_block` at `:160-170`, never raises); the composer's order (`backend/league_projections/next_move.py:105-122`, sell gates `:51-83`, buy gates `:86-102`); the app's checks (`mobile/src/utils/homeNextMove.ts:41-53` block, `:57-65` sell roster, `:69-73` buy owner, `:107-131` view); the tap (`mobile/src/components/home/HomeHub.tsx:214-224`), the mount (`:439-441`).
- [x] **Manual TestFlight checklist:** §9.
- `testID`s added: `home.next-move`, `home.next-move.line`.

## 6. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | the forecast read's `next_move` block |
| `docs/config-reference.md` | updated | the flag table and the league projections flag paragraph |
| `living-memory/LLD.md` | n/a | no convention shift: a composed read block behind a flag, the `team_direction` pattern |
| `docs/architecture.md` | updated | a paragraph after the `team_direction` one: the `next_move` composer and the Home row |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant; the web app does not read the forecast blocks |
| `docs/glossary.md` | n/a | "next move" here is plain words, not a new domain term (the unrelated `trade.next_move` offer revision is a different feature) |
| `DECISIONS.md` | updated | D-278 |
| `CLAUDE.md` index files | updated | `mobile/src/components/CLAUDE.md` (`HomeNextMove`), `mobile/src/utils/CLAUDE.md` (`homeNextMove`), `mobile/tests/README.md` (`check-home-next-move`); `backend/` has no per-module index for `league_projections` |

## 6a. Ship gate declaration

- CI green: `backend-tests`, `mobile-typecheck`, testid-lint, on the pushed sha.
- Evidence recorded in `living-memory/TEST_LEDGER.md` (2026-11-21 entry).
- TestFlight verification: the §9 checklist, by the operator.
- Express lane: no.

## 7. Every new string

All user-facing; source `mobile/src/utils/homeNextMoveCopy.ts`. `{…}` are fills: `{short_name}` and `{position}` from the block; `{team}` the seller's name as the targets list shows it; pick labels as sent; percentages through the lists' formatters (`playoffOddsText` whole percent, `formatPct`).

| Id | String |
|---|---|
| `NM-LABEL` | Next move |
| `NM-SELL.pick` | Sell {short_name} ({position}): projected pick {now} → {after} |
| `NM-SELL.top3` | Sell {short_name} ({position}): top-3 pick chance {now} → {after} |
| `NM-SELL.playoff` | Sell {short_name} ({position}): playoff chance {now} → {after} |
| `NM-BUY` | Buy {short_name} ({position}) from {team}: playoff chance {now} → {after} |
| `NM-ACTION` | Find trades |
| `NM-A11Y` | Next move. {line}. Find trades for {short_name}. |

A sell uses `NM-SELL.pick` when the projected pick changes, else `NM-SELL.top3` when the top-3 chance changes at whole percents, else `NM-SELL.playoff`. "Find trades for {short_name}" is the lists' own button wording.

## 8. What is not built

| Item | Why |
|---|---|
| A web version | The web app has no Home playoff card and does not read `team_direction`, `max_pf_moves` or `playoff_targets`; it ignores the new key. Not affected |
| The row on League rankings (the card's other host) | The ask is Home |
| Falling to the second row when the first is not usable | The brief: only when the list itself would show it first (the read's seller filter is that case); otherwise nothing |
| An impression event | Waived, signed off 2026-11-21 (§1) |
| A second link to the full list | The card's "View ›" already reaches both Improve pages through the half sheet |
| A combined ("top 2 together") suggestion | One player, one action |
| Any new computation, saved data or weekly-job work | Composed from what the read already serves |

## 9. Manual TestFlight checklist

Needs the app build with this change and the server deployed. Use a Sleeper league with a current forecast.

Flag on (`league.next_move` true, the shipped value):

1. Team leaning to the playoffs (playoff chance over 45%, outlook not Rebuilding or Tanking), Improve Playoff Chances showing a list: Home shows one row under the playoff card, "Next move", "Buy <first player on that page> (<pos>) from <his team>: playoff chance X% → Y%", and "Find trades ›". X and Y match that player's row on the page.
2. Tap it: Find a Trade opens with that player on the receive side and his team as the trade partner (as the page row's "Find trades"); "‹ Home" shows under the top bar and returns to Home.
3. Save a Rebuilding outlook (or use a team at 45% or lower) with your own pick and the draft-order question unanswered or answered "Lowest max PF": after the card refreshes, the row reads "Sell <first player on Improve Draft Pick> (<pos>): projected pick A → B" with A → B matching that row's "Projected pick" when opened.
4. Tap it: Find a Trade opens with that player on the give side; "‹ Home" shows.
5. Mark that player Keep: the row disappears (it does not move to the next player).
6. Answer the draft-order question "Reverse standings" (or "Lottery or other"), or have another team own your pick: no sell row (the card shows no projected pick for the first; Improve Draft Pick has no rows). Answer "Lowest max PF" again: the row returns.
7. Add or drop a player other than the suggested one on Sleeper, then pull to refresh Home: the sell row stays. Trade away the suggested player: the row disappears (it does not move to the next player).
8. A clinched or eliminated team, or "playoff chance already 99% or higher": no row.
9. An ESPN or MFL league: no row, no error.
10. League rankings' playoff card: no row there.

Flag off (`league.next_move` false + reload):

11. Home is exactly as before: the playoff card, then the status rows; no row, no gap.
