# Max PF moves: app evidence (v1)

> The app builder's evidence for the Max PF moves section (D-056: structural suite, a file:line
> code-walk and a manual TestFlight checklist; no simulator, no Maestro). Built 2026-11-12 on
> `feat/max-pf-moves-app` from `feat/max-pf-moves` `de4902ed`, against [contract.md](contract.md)
> before the backend existed. Line numbers are on that branch.

- [1. What was built](#1-what-was-built)
- [2. Code-walk](#2-code-walk)
- [3. The TradesScreen give pin (contract §12): it does NOT hold](#3-the-tradesscreen-give-pin-contract-12-it-does-not-hold)
- [4. Tests and sabotage](#4-tests-and-sabotage)
- [5. Manual TestFlight checklist](#5-manual-testflight-checklist)
- [6. Contract questions](#6-contract-questions)
- [7. Not verified](#7-not-verified)

## 1. What was built

| File | Role |
|---|---|
| `mobile/src/api/leagueProjections.ts` | Block types (§3) beside the forecast types; `ProjectionView.max_pf_moves?` (absent = flag off / older server) |
| `mobile/src/api/draftOrderRule.ts` (new) | `setDraftOrderRule(leagueId, rule)` → `POST /api/leagues/<id>/draft-order-rule` |
| `mobile/src/utils/maxPfMovesCopy.ts` (new) | Every §10 string, verbatim, keyed by contract id |
| `mobile/src/utils/maxPfMoves.ts` (new) | All derivation, formatting, event props, request shape, hand-off (pure) |
| `mobile/src/state/maxPfMovesPrompts.ts` (new) | The two §6.4 device keys over AsyncStorage |
| `mobile/src/components/MaxPfMovesSection.tsx` (new) | `MaxPfMovesBody`: thin renderer + taps |
| `mobile/src/components/LeagueProjectionDetail.tsx` | `Disclosure` gains `initialOpen`; fourth disclosure on the own card |
| `mobile/src/screens/StandingsScreen.tsx` | Flag read, live roster ids, props to the detail |
| `mobile/tests/check-max-pf-moves.js` (new) + `npm run test:max-pf-moves` | The structural suite |
| `mobile/tests/check-standings-table.js` | B4g widened to accept the new `maxPf` prop (one regex) |

## 2. Code-walk

**Data in.** One query, unchanged: `StandingsScreen.tsx:106-111`, key
`['league-projection-batch', userId, leagueId]`, `getLeagueProjectionBatch`
(`leagueProjections.ts:95-96`), which now types `max_pf_moves?: MaxPfMoves` (`:93`). The flag is
read the app's way, `useFlag('league.max_pf_moves')` (`StandingsScreen.tsx:80`; flags come from
`/api/flags` via `state/useFeatureFlags.ts:252-255`). The live roster for §6.3 is a `useMemo`
over the page's existing `['league-rosters', leagueId]` query (`:92-97`, `:122-125`) through
`findMyRoster(...).players`; null until loaded. No new query, no effect (B7b still holds).

**Into the open card.** `StandingsScreen.tsx:271-273` passes `{block: data?.max_pf_moves, flagOn,
isSleeper, liveRosterIds, leagueId, userId}` to `ProjectionTeamDetail`. In
`LeagueProjectionDetail.tsx:45-49` the section is built only when `sectionMounts`
(`maxPfMoves.ts:102-105`: block present, flag on, Sleeper, own card, `version === 1`, known
state) with `ownCard = isOwnCard(team.roster_id, result.viewer_roster_id, block)`
(`maxPfMoves.ts:106-109`). Any other team's card computes `moves = null` and renders exactly the
three old disclosures. The fourth `Disclosure` follows "Draft pick odds" (`:58` then `:71-73`),
starting open per `initialOpen` (`maxPfMoves.ts:123-125`: list state, default-open, not gated).

**Per state** (the body is `MaxPfMovesSection.tsx`; the model is `deriveSection`,
`maxPfMoves.ts:325-352`):

| State | Path |
|---|---|
| `unavailable` (+ every reason) | `stateLine` → `unavailableLine` (`maxPfMoves.ts:163-177`), open set → `C-U-other`; rendered at `MaxPfMovesSection.tsx:126`; `orderLine` null so no link |
| `season_over`, `after_trade_deadline` | `stateLine` one line, no link |
| `draft_order_not_maxpf` | one line + "Change answer" (`orderLine`, `maxPfMoves.ts:179-185`; rendered `:150-156`) |
| `no_miss` | C-NO-MISS + the order line + Change; the question if unanswered (`questionEligible`, `:154-157`) |
| `ready` / `no_moves`, collapsed | outer disclosure starts closed; body shows C-COLLAPSED + Show moves (`MaxPfMovesSection.tsx:69`, `:128-133`) |
| `ready` / `no_moves`, pick owned elsewhere | gate before collapse: C-OWNER + Show anyway (`:69`, `:129`) |
| `ready`, open | baseline (`baselineLine`, `maxPfMoves.ts:186-199`), C-RULES once (`:71-74`, `:137`), C-ROSTER (`:138`), C-HEAD, first 5 passing rows then Show all (`visibleRows`, `maxPfMoves.ts:144-149`; `:140-148`), C-FOOT, order line |
| `no_moves`, open | baseline + C-NO-MOVES + order line (`noMovesLine`, `maxPfMoves.ts:347`) |
| roster changed | `rosterChanged` / `listedRows` (`maxPfMoves.ts:127-143`) drop rows off the live roster; every passing row gone ⇒ C-ROSTER only |
| a row opened | `MoveRow` (`MaxPfMovesSection.tsx:160-192`): `rowDetail` (`maxPfMoves.ts:285-303`) lines, then Find trades (`:187`) or C-KEEP-NOTE (`:189`) |

**Question and POST.** Device keys read once per mount (`MaxPfMovesSection.tsx:59-66`); auto-shown
when `questionAutoShown` (`:76-77`). `answer` (`:80-96`): `setDraftOrderRule` → on 200
`markDraftOrderAsked`, `draft_order_rule_answered {answer, source}`, invalidate the forecast key
(refetch) → on failure C-Q-ERR (`:123`). "Change" opens it with `source: 'change'` (`:153`).

**Events.** `maxpf_moves_viewed` on body mount, guarded by the card-owned ref
(`MaxPfMovesSection.tsx:51-56`, `LeagueProjectionDetail.tsx:44`); `maxpf_move_expanded` on open
only (`:108-112`); `draft_order_rule_answered` after the POST (`:87`); `finder_target_pinned` in
`handOffToFinder` (`maxPfMoves.ts:380-387`). Standings' own single emitter is untouched.

**Hand-off.** `MaxPfMovesSection.tsx:98-106` → `handOffToFinder`: `setSide('give', [player])`,
`setSide('receive', [])`, `finder_target_pinned {side:'give', source:'maxpf_moves'}`, then
`navigation.popTo('Main', {screen:'Trades', params:{screen:'TradesHome'}})`. See §3 for what the
deck then does with the pin.

## 3. The TradesScreen give pin (contract §12): it does NOT hold

Contract §12 asks the app builder to confirm that TradesScreen shows a give pin set from outside
the screen and that its next Find a Trade sends it. **On the current flag set it does neither.**
I did not patch TradesScreen (brief: stop and report).

- `TradesHome` is registered with `initialParams {mode: 'guided'}` when `trades.finder_hub` is on
  (`navigation/TabNav.tsx:460-464`; `config/features.json`: `trades.finder_hub` true).
- With `calc.inline_home` on (true in `config/features.json`), guided TradesHome is the canvas host:
  `canvasHost = 'flag'` (`TradesScreen.tsx:7578-7587`).
- The pin board that renders `pinnedGive` is inside `finderMode === 'player'` branches only
  (`TradesScreen.tsx:8903`, `:9206`). `TradingWithStrip` (`:8536-8543`) shows league and partner,
  not pins (its "Players" pill is an unbuilt seam, `components/TradingWithStrip.tsx:15-28`). So the
  pin is **not shown** on the landing.
- Find a Trade on that landing is the canvas action row → `handleInlineFindATrade`
  (`TradesScreen.tsx:4102-4142`) → `forkCanvasSearch(opts)` (`utils/canvasSearch.ts:50-60`), which
  takes the canvas's own give/receive and never reads `useFinderTargets`; the pushed deck carries
  `canvasSelection: {giveIds: fork.giveIds, ...}` (`TradesScreen.tsx:4133`). Both page-level
  `trades.find-btn` bars step aside for the canvas (screens/CLAUDE.md, merged-view trim T-2). So
  the pin is **not sent**.
- Pins are read by `modelRequest` (`TradesScreen.tsx:2329-2337`) and by the consumed `FinderHandoff`
  path (`:3806-3810`). League rankings' Offer works because it also calls `setHandoff` (auto-run),
  which contract §12 rules out for v1.

What the user would see today: Find trades lands on the canvas with an empty give side; the pin
sits invisibly in the store and is ignored. Options for the operator (none built):
(a) hand off through the existing `canvasPrefill` route param MatchesScreen uses
(`TradesScreen.tsx:1362-1368`: `{give: [player_id], receive: []}` loads the canvas; Find a Trade
then runs the fair sweep anchored on him) — no TradesScreen change, but a different search than a
pinned model search; (b) `setHandoff` with `autoRun` (needs a new R1 `source`, contract §12);
(c) make the canvas seed from store pins (a TradesScreen change). The hand-off as built follows the
contract to the letter so it is one function to change (`maxPfMoves.ts:380-387` plus the
`navigate` dep at `MaxPfMovesSection.tsx:105`). **Do not light the flag until this is decided.**

## 4. Tests and sabotage

Run from `mobile/` on this branch:

| Check | Result |
|---|---|
| `node tests/check-max-pf-moves.js` | 112 assertions pass (groups A–N) |
| all `tests/check-*.js` (CI's loop) | 185 / 185 suites pass (184 before + the new one) |
| `npx tsc --noEmit` | clean |
| `bash scripts/testid-lint.sh` | OK |

The suite parses the four §5 example payloads straight out of `contract.md` and executes the util
against them and their variants, and compares the copy module with the §10 table in both
directions (45 rows; the one worked example, `An empty spot starts instead (1 week).`, is checked
as an output instead).

**Sabotage: 41 of 41 caught across all 14 groups (A–N).** Each break was applied to the source,
the suite run (non-zero exit with the named assertion failing), then restored; file checksums
were identical before and after, and the suite was green afterwards. Breaks included: a copy edit
(A1), "tank" in a comment (A3), an inline literal (A6), every-reason → generic (B3), wrong state
line (B1), lost "Change answer" (B6), `<=` → `<` at 0.45 (C1), dropping `jets` (C3), owner gate
inverted (D1) and ignored in the body (D4), roster drop disabled (E2), null roster checked (E1),
C-NO-MOVES under a roster drop (E4), threshold ignored (F1), 6 before Show all (F3), Keep row
gets a button (G1) or a hand-off (G3), `<1%` cut (H4), hyphen for U+2212 (H1), no `+` (H6),
singular week (H15), no-label sentence (H10), final week (H22), flag ignored (I2), flag forced in
Standings (I4), own-card check removed (I5), receive not cleared (J1), `navigate` instead of
`popTo` (J2), `n_moves` from all rows (K1), a name in `maxpf_move_expanded` (K4), expanded on close
(K7), viewed every opening (K8), wrong POST path (L1), question with a stored answer (L3), no
refetch after the POST (L8), wrong device key (L5), a `fetch` on open (M1), 40pt row (M5), hex
colour (M7), untruncated name (M6), value shown when not priced (N1).

## 5. Manual TestFlight checklist

Setup: a Sleeper league with `league.projections` and `league.max_pf_moves` on and a weekly
forecast saved after the backend lands. Open Home → Standings, tap your own row (the "You" badge).

1. **Own team with a list.** Your card shows Final record odds, Weekly projections, Draft pick
   odds, then **Max PF moves**. If your playoff chance is ≤ 45% or your saved outlook is
   Rebuilding / Tanking, it is already open. Expect: a "Your 2027 1st today: …" line ending in
   "Value N." (or no Value sentence in a league where picks are not priced), the first time on
   this phone "Check your league's rules on trades made for draft position.", "Max PF change over
   the remaining N weeks", rows like `R. Sato  RB  −31` / `Pick if you miss 3.7 → 3.4 · Value +169`,
   at most 5 rows then "Show all", the footer and "Estimates assume regular-season Max PF draft
   order. Change". Minus signs are the long dash, not a hyphen. Close and reopen the card: the
   rules sentence does not come back.
2. **Another team's card.** Open any other row: only the three old disclosures, no Max PF moves.
3. **Collapsed.** In a league where your playoff chance is above 45% and your outlook is not
   Rebuilding / Tanking: the section starts closed; opening it shows "Your team makes the playoffs
   in N% of simulations. Moving these players lowers that." and **Show moves**; tapping it shows
   the list.
4. **Pick owned elsewhere.** In a league where another team holds your next 1st: the section starts
   closed even if you would be default-open; opening shows "<Team> owns your 2027 1st, so lowering
   your max PF improves their pick." and **Show anyway**; tapping shows the list.
5. **Draft-order question, each way.** In a league nobody has answered: the question "How does
   your league set next year's draft order for non-playoff teams?" with four buttons appears at the
   top of the section. (a) Tap **Reverse standings** (or **Lottery or other**): the section becomes
   "Your league doesn't set its draft order by max PF, so these moves wouldn't change your pick.
   Change answer". Reopen the card, the question does not return; a second phone in the same league
   sees the same line and no question. (b) In another league tap **Lowest max PF**: the list stays
   and the line becomes "Your league orders the draft by lowest max PF. Change". (c) In a third
   league tap **Not sure**: the list stays with the assumption line; the question does not come
   back on this phone, but a second phone in that league still gets it. (d) With airplane mode on,
   tap an answer: "Couldn't save your answer. Try again." and the question stays. (e) Tap
   **Change** / **Change answer**: the question opens again.
6. **Roster changed.** Trade or drop a listed player in Sleeper, then reopen Standings before the
   next weekly forecast: "Your roster changed after this forecast. The list updates with the next
   weekly forecast." above the list, and that player's row is gone; the other rows' numbers are
   unchanged. If he was the only listed player, only that notice shows.
7. **Keep player.** Mark a listed player Keep (Roster setup or a trade card). His row shows a "Keep"
   tag; opening it shows "You marked <name> Keep, so Find trades is off for this player." and no
   button.
8. **Find trades hand-off.** Open a non-Keep row: Top-3 chance, Playoff chance, Projected pick,
   "<name> starts instead …", the week list, and **Find trades for <name>**. Tap it: the app goes to
   the Trades tab. **Expected failure on today's flags (§3):** the player is not shown on the give
   side and Find a Trade does not use him. Record what you see; this item is the open decision.
9. **Non-Sleeper league.** Switch to an ESPN or MFL league: Standings shows its unavailable card and
   nothing about Max PF moves.
10. **Flag off.** Turn `league.max_pf_moves` off (reload flags): your card shows the three old
    disclosures only, nothing else on the page changes, and no request to `draft-order-rule` is
    made.
11. **Large text.** At the largest accessibility text size, rows wrap their second line, long names
    truncate with "…", and nothing overlaps; every row and link is comfortably tappable.

## 6. Contract questions

1. **§12 hand-off does not work on the shipped flag set** (§3 above). Blocking for flag-on.
2. **§12 navigation.** The contract's `navigation.navigate('Trades', {screen: 'TradesHome'})` is
   unhandled from Standings, a root-stack push over `Main` (React Navigation 7; the same reason
   `LeagueSummaryScreen.tsx:601-609` uses `popTo('Main', …)` on its root push). Built as
   `popTo('Main', {screen: 'Trades', params: {screen: 'TradesHome'}})`.
3. **§7.2 client location.** The contract puts `setDraftOrderRule` in `leagueProjections.ts`, but
   two existing guards pin that module read-only (`check-league-projections.js:36`,
   `check-standings-table.js` B6d). Put in a new `api/draftOrderRule.ts` instead; the forecast
   client stays GET-only.
4. **§8 "the app does not read the flag"** vs the brief ("flag on AND block present"). Built both:
   `useFlag('league.max_pf_moves')` AND the block. If `/api/flags` does not serve the key, the
   section never shows; the backend must add it to `config/features.json` (contract §8 says it
   will).
5. **Unknown `state`.** §3.1 makes `reason` an open set and an unknown `version` render nothing,
   but says nothing about an unknown `state`. Built: render nothing.
6. **Value change of 0.** §11 says "leading + or −"; 0 renders `+0`.
7. **Replacement names.** §10 C-REPL uses `{name}`; built with the full `name` (rows use
   `short_name`). C-WEEK's `{names}` is joined "a, b and c".
8. **C-RULES "under the baseline".** Shown only where a baseline shows (ready / no_moves, body
   open past any gate); the device key is written the first time it renders there.
9. **Order line in `no_miss`.** §10 places C-ORDER-* "under C-FOOT", which only `ready` has. Also
   shown in `no_moves` and `no_miss` so "Change" works there (§3.1: "the Change link works
   everywhere").
10. **The question in `no_miss` and behind gates** shows at the top of the body, before the
    collapsed / owner line.

## 7. Not verified

- Nothing ran on a device or simulator (D-056); runtime behaviour is the checklist above.
- No real server: built against §5's payloads only. The backend's real block may differ.
- React Navigation `popTo` into the nested Trades tab is proven only by the identical
  League-rankings call; not run.
- AsyncStorage persistence of the two device keys, the refetch after the POST and the
  `invalidateQueries` timing are read, not run.
- That the backend registers `maxpf_moves_viewed`, `maxpf_move_expanded`,
  `draft_order_rule_answered` and the `maxpf_moves` source value (contract §9) is the backend
  builder's; `track()` drops nothing client-side, but an unregistered event is rejected server-side.
