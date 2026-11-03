# Feature Scope — B5 launch copy, trades-eng's items (1, 3, 4)

**Date:** 2026-10-28
**Entry point:** direct ask. Marketing-lead's copy ledger, §6 addendum 10 ("the 11-06 binary copy batch"), routed to head-eng on 10-28, items 1, 3 and 4. It comes from Product's pre-launch review B5. Due in release-lead's queue by ~11-03, under the rule that a late string is removed, not shipped.
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. There are no waivers; analytics and evidence are answered below.

**The strings (final, word for word):**

| # | Surface | Was | Now |
|---|---|---|---|
| 1 | Win Now receipt, uncalibrated branch: mobile `utils/winNow.ts`, web `js/win-now.js` | `Uncalibrated beta` | `Uncalibrated estimate` |
| 3 | In-league calculator note (`InLeagueCalculator.tsx`) | `Draft picks aren't available for ESPN leagues.` | `No draft picks are set up for this ESPN league yet.`, plus the link `Set up picks →` (opens PickAssignment) |
| 4 | ShopAsset primary button (`ShopOffersBody.tsx`, `shop.like-btn`) | `Send this offer` | `Show it to @{name}`; VoiceOver: `Show this offer to @{name} in their Fleeced deck` |
| 4 | Queue toasts (`utils/queueCalcTrade.ts`) | `Queued for @{name} — it'll show in their suggestions.` / `Already queued for @{name}.` | `It's waiting in @{name}'s Fleeced deck.` / `It's already in @{name}'s Fleeced deck.` |

**Item 3's gates** (draft-eng's answer, 10-28, plus marketing's eng condition, "only when the league has no picks recorded"):
- **When the new note shows:** only while **both** `picks.assign` (the grid) and `picks.assign_tradeable` are on.
  - Then `/api/league/picks` makes `picks_supported` a data test (`server.py`, `get_league_picks`: `supported = has_assigned_picks(league_id)` for ESPN). So the note shows on `!picksSupported`, which means an ESPN league with no assigned pick, and never after setup.
  - Both hooks are called on every render.
- **Either flag off:** today's line stays (`Draft picks aren't available for ESPN leagues.`). Then picks can't be set up or traded, so it's true. Both flags are on today.
- **The link:** shown with the new note when there's a league id. It pushes `PickAssignment` (`{ leagueId }`, no season) on the root stack through `navigationRef`, as MemberEnteredMarker's correction link does.
  - None of the calculator's three hosts (FeaturedTradeWindow, TradeBuildCanvas, TradeCalculatorScreen) renders inside a `Modal`, so there's nothing to close first.

**Saving picks refreshes the calculator (#531 QA P1-1):** `PickAssignmentScreen`'s assign and seed `onSuccess` handlers invalidate `['league-picks', leagueId]`, beside the `['pick-assignments']` invalidation they already make. Without that, the calculator's picks query (5-minute `staleTime`) kept the "none set up" note and missed the new picks after a save. It's draft-eng's screen, and they were told.

**The toasts' reach:** `queueCalcTrade` serves both of its hosts, the shop and the calculator's ✓. Both queue the trade into @{name}'s Fleeced deck as a "likes you" card, so the new lines are true for both.

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - Copy and a navigation link only. `calc_trade_queued` and the shop's events are unchanged.
  - The link adds no event: marketing's row asks for none, and PickAssignment's own screen view already records arrivals.

## 2. Schema & flag scope

- **Tables, columns, routes:** none.
- **Flags:** none new. The new note and its link read `picks.assign` and `picks.assign_tradeable`; both already exist and are on.

## 3. Evidence scope

- [x] **Structural suite:** `mobile/tests/check-b5-copy.js` (`npm run test:b5-copy`), 12 checks.
  - every final string word for word, and each replaced string gone (item 3's old line stays only on its flag-off branch);
  - item 3's gates: both flags, with each hook called on every render; the data-test condition, with the server's `has_assigned_picks` line pinned too; today's line with either flag off; the root-stack navigation;
  - no component-level early return before the pick-flag hooks;
  - saving picks (assign and seed `onSuccess`, `PickAssignmentScreen.tsx`) invalidates the calculator's `['league-picks', leagueId]` (#531 QA P1-1);
  - item 4's button keeps its `testID`, each toast sits on its own `already_queued` branch, and the shop name's normalizer (`?? ''`) is pinned;
  - no banned word (beta, read-only, failed, error) in the shipped strings, read from the source.
- [x] **Sabotages:** 20 of 20 mutations turn it red. They cover each string and each gate, a short-circuited hook call, the navigation target, the swapped toasts, the dropped normalizer, an early return, each missing or misplaced invalidation, and a banned word.
- [x] **Existing suites:** `check-win-now.js`'s two pins moved to the new string. Its executable web test renders the receipt, so the web string is exercised. All 23 suites that read the edited files pass, and `tsc --noEmit` is clean.
- [x] **Manual TestFlight checklist** (operator, on the 11-06 binary).
  - **Read this first:** steps 3 and 5–7 write real data.
    - Step 3 saves the league's pick board, which can't be undone in the app.
    - Steps 5–7 put a real "likes you" card in a leaguemate's Fleeced deck.
    - Use a league and leaguemates where that's fine.
  1. **Precondition:** an ESPN league whose pick board has never been saved. Open the calculator on the Trades landing canvas (`calc.inline_home`). Expect `No draft picks are set up for this ESPN league yet.` and `Set up picks →`.
  2. Tap `Set up picks →`. Expect the pick assignment screen for that league, at its setup step, because the board is unsaved.
  3. Save the board, then go back to the calculator. Expect, immediately (no wait, no pull-to-refresh), no note, and the league's picks in the calculator's pickers. (#531 QA P1-1: saving now refreshes the calculator's picks.)
  4. In a Sleeper league, open the calculator. Expect no note.
  4b. **Not run:** the flag-off line (`Draft picks aren't available for ESPN leagues.`) needs a pick flag turned off in prod, which isn't done for a check. `check-b5-copy.js` covers it.
  5. Trades → Find a trade → on a deck card, the give side's **More offers**. Expect the primary button `Show it to @{their name}`; a long name wraps rather than clipping. Tap it. Expect the toast `It's waiting in @{name}'s Fleeced deck.`
  6. Tap it again on the same offer, if it's still shown. Expect `It's already in @{name}'s Fleeced deck.`
  7. In the calculator, build a trade and tap ✓ (queue). Expect the same "waiting" toast.
  8. With VoiceOver on, focus the shop button. Expect `Show this offer to @{name} in their Fleeced deck`. (VoiceOver reads the link's "→" as "right arrow", like the app's other `… →` links.)
  9. On Win Now with an uncalibrated model, expect the receipt to start `Uncalibrated estimate ·` in the app. **The web half goes live when this merges** (Render), not with the binary.
- **Known edge, accepted:** a client that cached both pick flags on keeps showing "none set up" for an ESPN league until its next flag refresh, if `picks.assign_tradeable` is later turned off. The kill switch is for emergencies, and the flag refresh corrects it.
- `testID`s: one new, `calc.picks-setup-link`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no convention change |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | n/a | the Win Now label is the same in both clients, but it's copy, not a shared constant |
| `docs/glossary.md` | n/a | no new term |
| `docs/design/*` | n/a | the link uses Chalkline tokens (`type.bodySm`, `ice.base` for an action) |
| `mobile/tests/README.md` | n/a | the suite runs through its npm script, like its neighbours |
| `docs/plans/README.md` | updated | this file's row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** the 9 steps above, on the 11-06 binary.
- **Express lane:** no; full gates.
