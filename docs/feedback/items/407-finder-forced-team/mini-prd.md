# Mini-PRD — FB-407: Find a Trade forces the calculator's (auto-defaulted) team

**Date:** 2026-08-30 · **Reporter:** mattmurf77, v1.16.11, screen `TradesHome` · **Class:** fast-track bug
**Report:** "The find a trade feature is incorrectly forcing a team from the calculator screen below it"

## The decision, in plain words

The calculator on the Trades front door silently picks the first leaguemate as its
trade partner the moment it loads. Tapping **Find a Trade** hands that partner to the
finder as a hard search scope, so a user who never touched the Team dropdown gets a
search of exactly one team instead of the whole league. The fix: only pass the
partner to the search when the user actually chose one (tapped a team, or built a
trade that includes that team's players). One production file changes.

## Repro (as the tester sees it, v1.16.11 with today's flag state)

1. Open the app. It lands on **Trades** (`nav.trades_landing` true) — the merged
   build-or-find page, calculator canvas below the header.
2. Don't touch anything. The calculator's **Team** dropdown already shows a manager
   (the first leaguemate) — the user never picked them.
3. Tap **Find a Trade** (the canvas action row — since the 2026-08-28 merged-view
   trim it is the page's ONLY search button) with the canvas empty.
4. **Observed:** the search runs against only that one team — the progress line
   counts 1 opponent, every found idea is with that manager, and the canvas's Team
   dropdown now shows them pinned ("forcing a team from the calculator screen").
5. **Expected:** an empty canvas with no deliberately chosen partner searches **all**
   teams, exactly as the pre-merge Find a Trade always did.

## Root cause (file:line, all cited against origin/main tip e89eebb0)

Four pieces interact; none is individually wrong:

1. **The calculator auto-defaults a partner.**
   `mobile/src/components/InLeagueCalculator.tsx:538-541` — "Default to the first
   opponent once the list loads": `if (!opponentId && opponents.length)
   setOpponentId(opponents[0].user_id)`. This default exists for the calculator's own
   evaluate UX (it needs a roster to browse) and re-fires whenever `opponentId` goes
   null — **the merged canvas can never be partnerless.**
2. **Find a Trade passes that partner unconditionally.**
   `mobile/src/components/InLeagueCalculator.tsx:1205-1227` — the
   `calc.action.find-a-trade` onPress builds the payload with
   `opponent: opponent ? { userId, name } : null` (:1214-1217), with no distinction
   between "user chose this team" and "the default effect chose it".
   `mobile/src/utils/canvasSearch.ts:60-70` (`forkCanvasSearch`) passes it straight
   through on both forks (fair and model).
3. **The finder adopts it as its search scope.**
   `mobile/src/screens/TradesScreen.tsx:3046-3073` (`handleInlineFindATrade`) —
   `setSheetOpponent(fork.opponent)` at **:3055** ("The canvas's Team dropdown is the
   search scope"). That feeds `scopedOpponent` (:832-835, `trades.sheet_targeting`
   true), and the one dispatch choke point sends it to the server:
   model path `opponent_user_id: scopedOpponent || undefined`
   (**TradesScreen.tsx:1850**, in `generateMutation`); fair path
   `...(scopedOpponent ? { opponent_user_id: scopedOpponent } : {})`
   (**TradesScreen.tsx:3353**, in `runFairPackages`). The backend honours it — a
   non-null `opponent_user_id` makes the job a targeted single-team sweep
   (`backend/server.py:5854`, `:5962`, `:6163`).
4. **The scope loops back and pins the dropdown.**
   `mobile/src/components/TradeBuildCanvas.tsx:152` —
   `effectiveOpponentId = prefill?.opponentId ?? opponentUserId ?? undefined`, where
   `opponentUserId={scopedOpponent ?? null}` (`TradesScreen.tsx:7431`). After the
   first forced search the canvas **remounts** (key at TradeBuildCanvas.tsx:168)
   with `initialOpponentId` = the forced team (:172) — which is what makes the bug
   read as the finder "forcing a team" into/from the calculator.

**Why it surfaced now:** the scope-adoption is not new to PR #237 — but until the
2026-08-28 merged-view trim (T-2, docs/feedback/items/402-more-offers-shop/
merged-view-trim-2026-08-28.md) the page kept unscoped page-level Find-a-Trade bars,
and until `nav.trades_landing` (v1.16.11) the merged surface wasn't every session's
front door. #237 made the canvas's button the only search entry on the landing tab
and put the results inside the canvas (`calc.canvas_results`), where the single
forced team is unmissable. The tester filed hours after that ship.

**Design-intent check:** scoping to a deliberately chosen partner is intentional —
docs/feedback/items/384-calc-finder-merge/testflight-checklist.md:191-193, item 23:
"Pick a specific manager in the Team dropdown … the modeled deck is scoped to them
too." The defect is that the **auto-default** is indistinguishable from a pick, and
the default effect (:538-541) makes clearing impossible.

## Does it reproduce on current code?

**Yes.** Every cited line above is present at the origin/main tip (e89eebb0). Only
two commits touched `TradesScreen.tsx` since 21989cda — 293b5f80 (decline-pass dwell
signal) and 1f87ec16 (propose-label impression_id) — neither touches opponent
scoping; `InLeagueCalculator.tsx`, `TradeBuildCanvas.tsx`, and
`utils/canvasSearch.ts` are untouched since 21989cda (`git log 21989cda..HEAD` on
those paths is empty). All gating flags are true in `config/features.json` today:
`trades.finder_hub` (:11), `calc.inline_home` (:90), `calc.canvas_results` (:92),
`nav.trades_landing` (:94), `trades.sheet_targeting` (:227).

## Fix approach (surgical — 1 production file + 1 test file)

Teach the payload the difference between a chosen partner and the default. All in
`mobile/src/components/InLeagueCalculator.tsx`:

1. Add `const opponentChosenRef = useRef(!!initialOpponentId);` beside the
   `opponentId` state (:344). `initialOpponentId` counts as chosen because — after
   this fix — every source of it is deliberate: an idea prefill
   (`TradeBuildCanvas.tsx:152` `prefill?.opponentId`, always from a tapped
   idea/card) or `scopedOpponent`, which post-fix only becomes non-null via an
   explicit pick, a LeagueSummary Offer/Target handoff, or legacy team-mode params.
2. Set `opponentChosenRef.current = true` in the two user-tap sites:
   the partner chip row (:1066-1068) and the team-picker sheet row (:1470-1472).
   The auto-default effect (:538-541) does **not** set it.
3. Gate the Find a Trade payload (:1214-1217):
   `opponent: opponent && (opponentChosenRef.current || receiveIds.length > 0)
   ? { userId: opponent.user_id, name: opponent.username } : null`.
   The `receiveIds.length > 0` clause: receive-side assets are drawn from that
   partner's roster picker, so a canvas containing them is materially a trade *with*
   that team even if the dropdown was never tapped — and the fair sweep's receive
   preference stays coherent.

No `TradesScreen.tsx` change needed: `handleInlineFindATrade` already handles a null
opponent correctly — `setSheetOpponent(null)` clears the scope, and the model
auto-run fires partnerless for calculator-origin arrivals by design
(TradesScreen.tsx:2997-3001, "#384 review #3/#9 — a calculator hand-off must
generate even with no partner chosen"). The pushed `TradeCalculatorScreen` host uses
the same component and payload, so it is fixed identically (flag-off parity: the
same bug is fixed there, nothing else changes). Analytics: `has_partner` on
`calc_find_a_trade_tapped` (canvasSearch.ts:59) becomes *more* honest — false when
the partner was only the default. No new events.

**Behavior preserved (the #384 checklist-23 contract):** an explicitly picked
partner still scopes both forks; an idea prefill still addresses its counterparty;
the ✓ queue cell and the evaluate query still use the calculator's internal
`opponent` untouched (they need one and are disabled without both sides).

## Regression guard (D-056: structural, never sim/Maestro)

Extend `mobile/tests/check-calc-merged-behavior.js` — the suite that already pins
`onFindATrade` contract points for this surface (see
docs/feedback/items/384-calc-finder-merge/scope.md:123) — with a FB-407 section
asserting, against the `InLeagueCalculator.tsx` source:

- the default-opponent effect body (`opponents[0].user_id`) does **not** contain a
  `opponentChosenRef` write (the default is never a choice);
- both user-tap `setOpponentId(o.user_id)` sites are paired with
  `opponentChosenRef.current = true`;
- the find-a-trade payload's `opponent:` expression contains the
  `opponentChosenRef.current || receiveIds.length > 0` gate (a build that reverts to
  the unconditional pass-through goes red).

Sabotage-verify each assertion (revert the gate → suite red → restore → green),
per the suite's existing convention. No backend change → no new pytest.

## Code-walk proof outline (for TEST_LEDGER)

Trace the tap end-to-end at the fixed sha, citing file:line for each hop:

1. Fresh mount, no user pick → default effect fires (InLeagueCalculator.tsx:538-541),
   `opponentChosenRef.current === false`.
2. Find a Trade tap, empty canvas → payload `opponent: null` (gated expression).
3. `forkCanvasSearch` → `path:'model'`, `opponent:null`, `has_partner:false`
   (canvasSearch.ts:52-70).
4. `handleInlineFindATrade` → `setSheetOpponent(null)` (TradesScreen.tsx:3055) →
   `scopedOpponent === undefined` (:832-835).
5. Choke point → `dispatchGenerate({})` with `opponent_user_id: undefined`
   (:1850) → server runs the all-teams sweep (server.py:6093/6261 cache-eligible
   untargeted path).
6. Counter-case: chip tap (:1067) → ref true → payload carries the partner →
   scoped exactly as #384 checklist item 23 requires.
7. Loop check: with `scopedOpponent` null, `TradeBuildCanvas` mounts with
   `initialOpponentId: undefined` (TradeBuildCanvas.tsx:152/172) — no pin-back.

## Manual TestFlight checklist (operator; the only runtime evidence)

1. **Fresh scoped-search check:** kill and relaunch the app (lands on Trades).
   Without touching the Team dropdown, tap **Find a Trade** on the empty canvas.
   *Expect:* the progress line counts ALL leaguemates (e.g. "0/11 opponents"), and
   the browsed ideas span multiple different managers — not one repeated handle.
2. **Dropdown not hijacked:** after step 1's results land, check the calculator's
   Team dropdown. *Expect:* it still shows the default partner but browsing ideas
   shows each idea's own counterparty; no single team is pinned across all ideas.
3. **Explicit pick still scopes:** tap the Team dropdown, pick a specific manager,
   tap **Find a Trade** (canvas still empty). *Expect:* the search is scoped to
   exactly that manager (progress "…/1", all ideas with them) — #384 checklist-23
   behavior intact.
4. **Built trade still addressed:** clear, add one of the default partner's players
   to the receive side via "their roster", tap **Find a Trade**. *Expect:* the fair
   sweep addresses that partner (their name on the ideas).
5. **Regression sentinel:** repeat step 1 once more after step 3-4 (relaunch first).
   *Expect:* all-teams again — the earlier explicit pick did not stick to a fresh
   session.
