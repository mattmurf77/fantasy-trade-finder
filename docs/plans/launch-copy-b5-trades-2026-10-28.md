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

**Item 3's gates:**
- **When the note shows:** marketing's eng condition is "only when the league has no picks recorded".
  - `/api/league/picks` already makes `picks_supported` a data test while `picks.assign_tradeable` is on (`server.py`, `get_league_picks`: `supported = has_assigned_picks(league_id)` for ESPN). So the note shows on `!picksSupported && picks.assign_tradeable`, which means an ESPN league with no assigned pick.
  - With that flag off, `picks_supported` is false for every ESPN league and recorded picks aren't returned, so nothing can be checked. The note is hidden rather than make a claim that may be false.
  - Both flags are on today.
- **When the link shows:** it also needs `picks.assign` (the grid) and a league id. It pushes `PickAssignment` on the root stack through `navigationRef`, as MemberEnteredMarker's correction link does.
  - None of the calculator's three hosts (FeaturedTradeWindow, TradeBuildCanvas, TradeCalculatorScreen) renders inside a `Modal`, so the push is never hidden behind one.

**The toasts' reach:** `queueCalcTrade` serves both of its hosts, the shop and the calculator's ✓. Both queue the trade into @{name}'s Fleeced deck as a "likes you" card, so the new lines are true for both.

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - Copy and a navigation link only. `calc_trade_queued` and the shop's events are unchanged.
  - The link adds no event: marketing's row asks for none, and PickAssignment's own screen view already records arrivals.

## 2. Schema & flag scope

- **Tables, columns, routes:** none.
- **Flags:** none new. The note reads `picks.assign_tradeable` and the link reads `picks.assign`; both already exist and are on.

## 3. Evidence scope

- [x] **Structural suite:** `mobile/tests/check-b5-copy.js` (`npm run test:b5-copy`), 7 checks.
  - every final string word for word, and each old string gone;
  - item 3's gates: the data-test condition, with the server's `has_assigned_picks` line pinned too; the link's `picks.assign` gate; the root-stack navigation;
  - item 4's button keeps its `testID`;
  - no banned word (beta, read-only, failed, error) in the new strings.
- [x] **Sabotages:** 10 of 10 mutations turn it red (each string, each gate, the navigation target).
- [x] **Existing suites:** `check-win-now.js`'s two pins moved to the new string. Its executable web test renders the receipt, so the web string is exercised. All 23 suites that read the edited files pass, and `tsc --noEmit` is clean.
- [x] **Manual TestFlight checklist** (operator, on the 11-06 binary):
  1. In an ESPN league with no picks assigned, open the calculator. Expect `No draft picks are set up for this ESPN league yet.` and `Set up picks →`.
  2. Tap the link. Expect the pick assignment grid for that league.
  3. Assign one pick and go back to the calculator. Expect no note.
  4. In a Sleeper league, open the calculator. Expect no note.
  5. In Shop, expect the primary button to read `Show it to @{their name}`. Tap it. Expect the toast `It's waiting in @{name}'s Fleeced deck.`
  6. Tap it again on the same offer, if it's still shown. Expect `It's already in @{name}'s Fleeced deck.`
  7. In the calculator, build a trade and tap ✓ (queue). Expect the same "waiting" toast.
  8. With VoiceOver on, focus the shop button. Expect `Show this offer to @{name} in their Fleeced deck`.
  9. On Win Now with an uncalibrated model, expect the receipt to start `Uncalibrated estimate ·`, in the app and on the web.
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
