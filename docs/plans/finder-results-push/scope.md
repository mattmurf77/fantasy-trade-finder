# Feature Scope — Finder results push (the pushed results deck)

**Date:** 2026-08-31
**Entry point:** direct operator ask — five verbatim rulings, 2026-08-31 (recorded as [D-171](../../../living-memory/DECISIONS.md))
**Builder:** Claude agent session, worktree `claude/finder-results-push`
**Operator sign-off on waivers:** not needed (no waivers)

---

## 0. The five operator rulings (2026-08-31 — the requirements, verbatim decisions)

1. **Landing = builder only.** The merged Trades landing keeps the inline trade-builder canvas, but the in-canvas results browsing (#402 `calc.canvas_results` behavior — the pager/browse-session presentation inside the canvas) turns OFF. Find a Trade is the only road to results.
2. **The D-153 fork is preserved.** Empty canvas ⇒ full model deck (async `POST /api/trades/generate` job); canvas with a give side ⇒ fairness-anchored ideas (`POST /api/trades/fair-packages`) built around it. Both now land on a PUSHED full-screen deck page. The anchor receipt ("Built around X · Change") lives at the top of the pushed deck.
3. **"Edit in calculator" on a deck card pops BACK to the landing with the trade pre-filled** — the existing prefill bridge. Loop: build → results → tweak → results. popTo semantics, never navigate (G-056).
4. **✓ and ✕ on the pushed deck behave exactly like the classic deck:** ✓ records the like via the existing swipe path and advances with the success toast; ✕ runs the existing decline-reasons capture and advances. The user stays in the deck until backing out; end-of-deck shows the classic exits/tally including "Back to calculator" (which pops to the landing).
5. **Ship LIT for all users in the same build.** The operator **explicitly overrode the dark-flag recommendation** (ruling 5b): `calc.results_push` exists as a kill switch but ships default TRUE.

This change also closes gap-analysis items **C1, C4, C10** ([2026-08-31 gap analysis](../../reviews/2026-08-31-find-a-trade-gap-analysis.md)): restoring `TradeCard` as the results surface restores the likes-you "They're interested" pill (C1 — the P0), the `trade_card_viewed` session-definition analytics (C4), and the end-of-deck tally + "See liked" exits (C10).

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new events, taxonomy untouched (default-deny respected):
  - `calc_find_a_trade_tapped {path, give_count, receive_count, has_partner}` — still emitted exactly once per tap, by the shared `forkCanvasSearch` (called BEFORE the push fork, so both postures report identically).
  - `find_trades_tapped {source: 'calculator'|'league_offer', mode}` — fired by the pushed instance's choke point / fair sweep, same as any calculator arrival.
  - `trade_card_viewed`, `deck_card_viewed`, swipe/queue/decline events — the classic deck's own emitters, restored to the main flow because the classic deck renders (this is gap C4 closing, not a new event).
  - `deck_back_to_calculator {pin_count}` — the existing exit event, now also covering the pop.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags:
  - **`calc.results_push` — NEW, default TRUE** (ruling 5; the operator explicitly overrode the dark-ship recommendation). Kill switch: set false + `POST /api/feature-flags/reload` → the landing consumes searches in place again. Registered in all four flag files (G-062) + `FLAG_KEYS` + `LAUNCHED_FLAG_DEFAULTS` (baked true, #115 paint-flip rule). Graduation: it IS the shipped posture; the flag exists only as the deploy-free rollback lever.
  - **`calc.canvas_results` — flipped TRUE → FALSE** (ruling 1) in all four flag files + the baked default. Code stays intact and flag-dormant. Full in-canvas restore = `calc.results_push:false` **+** `calc.canvas_results:true` + reload (documented in `config/features.json` and `docs/config-reference.md`).
- New env vars / `model_config` keys: **none**. Rollback lever = the flag pair above; no deploy needed.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-results-push.js` (+ `npm run test:results-push`) — pins: the push carries the D-153 fork verdict/anchor/scope/origin/label; the landing mounts no browse session and dispatches nothing (choke-point guard + auto-start refusal); the pushed instance mounts no canvas (param-driven `canvasHost` null arm) and consumes the param once into the single choke point (no new dispatch site — mutate census unchanged at 1 raw / 9 routed); Edit-in-calculator pops with the `canvasPrefill` bridge and Back-to-calculator pops WITHOUT a prefill; popTo never navigate (G-056); receipt tops the pushed deck with Change=pop / Clear=search-all; the kill-switch fallback (in-place arm + `canvasResultsLive` derivation) survives verbatim; flag registration in all four files + FLAG_KEYS + baked default; no new analytics.
  **Sabotage-tested (5/5 red, restore green):** S1 canvas remounts on the pushed instance → §4 red; S2 popTo→navigate → §5a/5b red; S3 Back-to-calculator carries the canvas-clearing empty prefill → §5e red; S4 push payload drops `fairAnchor` → §3d red; S5 flag flipped dark → §1 red.
- [x] **Re-pinned guards** (each with in-file notes citing the 2026-08-31 rulings): `check-canvas-results.js` (§1 dark pins, §2 `landingDeckRetired` gates, §8d Change three-way fork, §11a/11k/11l G22 gates, §12o2 baked default), `check-inline-home.js` (§2b0 pushed-arm suppression, §7a push fork re-key, §8b/§8d receipt re-pins), `check-calc-merged-behavior.js` (§10b2 plain-pop arm).
- [x] **Unit tests:** no backend behavior changed (client-only flag work); the existing `pytest backend/tests` fixture-mirror chain (G-062) validates the four-file flip. Full suite run green — see TEST_LEDGER.
- [x] **Code-walk proof:** §6 below.
- [x] **Manual TestFlight checklist:** §7 below.
- `testID`s added/renamed: **none** (the pushed deck reuses every classic-deck testID; the header back control is the shared `stack.back-btn`). `testid-lint` green.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/changed — both search routes consumed as-is |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted; the navigation convention (popTo per G-056) already recorded |
| `docs/architecture.md` | n/a | no module wiring change — same screens, same stores, same choke point |
| `living-memory/HLD.md` | n/a | no architecture shift — a route param + render gates |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors touched |
| `docs/glossary.md` | n/a | no new domain term |
| `docs/config-reference.md` | updated | `calc.results_push` row added; `calc.canvas_results` row re-stated false with the restore pair |
| `mobile/src/screens/CLAUDE.md` | updated | TradesScreen row — D-171 posture paragraph |
| `mobile/src/components/CLAUDE.md` | updated | InLeagueCalculator row — middle cell back to labeled Clear (browseDecline dormant) |
| `DECISIONS.md` D-171 | updated | all five rulings, incl. 5b's explicit dark-ship override |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `pytest backend/tests` · `tsc --noEmit` · testid-lint (all three checks watched on the PR before squash-merge).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-08-31 entry (suite counts + sabotage results).
- **TestFlight verification:** checklist §7 below, run by the operator on v1.16.14.
- Express lane declared by the operator? **No — full gates.**

---

## 6. Code-walk proof (file:line, verified against the built tree)

**The push hand-off (ruling 1+2).** `InLeagueCalculator`'s Find a Trade cell calls `onFindATrade({give, receive, opponent})` (`mobile/src/components/InLeagueCalculator.tsx:72-84`, invoked ~:1301). The flag-hosted landing wires that to `handleInlineFindATrade` (`mobile/src/screens/TradesScreen.tsx` — mount at the `<TradeBuildCanvas … onFindATrade={canvasHost === 'flag' ? handleInlineFindATrade : undefined}` site). The handler first runs the shared D-153 fork `forkCanvasSearch(opts, 'Trades')` (`mobile/src/utils/canvasSearch.ts:41-69` — verdict `fair` iff `giveIds.length > 0`, one `calc_find_a_trade_tapped` row), then under `resultsPushLive` (= `useFlag('calc.results_push') && canvasHost === 'flag'`) pushes `TradeDeck` with `resultsPush: {seq, opponent: fork.opponent, origin:'calculator', fairAnchor: fork.anchor, anchorLabel}` and **returns** — the landing consumes nothing. `TradeDeck` mounts `TradesScreen` (`mobile/src/navigation/TabNav.tsx` TradesStack, with a D-171 options fork giving the pushed instance the Chalkline header + always-on back control).

**The pushed instance renders deck-first (ruling 2).** `canvasHost`'s first arm is `isResultsPushed ? null` (TradesScreen, the `const canvasHost:` resolution), so the pushed guided instance mounts no `TradeBuildCanvas`; `canvasResultsLive`, `resultsPushLive` and `landingDeckRetired` are all false there, so the classic deck tree renders exactly as on team/player modes. The consumption effect (declared AFTER the #330 choke effect, seq-guarded on `resultsPush.seq`) sets `sheetOpponent`, `deckOrigin`, `inlineAnchor`, arms `fairAnchorRef`/`autoRunPendingRef`/`autoRunOriginRef` and bumps `canvasRunSeq`. The choke effect (deps `[finderMode, scopedOpponent, autoRunSeq, canvasRunSeq]`) re-fires once with the refs armed and takes the **existing D-153 fork**: `fairAnchorRef.current` set ⇒ `runFairPackages(anchor)` (synchronous `POST /api/trades/fair-packages`, sets `fairDeck`); not set ⇒ `dispatchGenerate({})` (the model job). Ordering note: arming inside the mount commit would double-dispatch (mount choke run fires the fair sweep, then the `setSheetOpponent` re-render resets it and fires the model) — the after-choke declaration is what guarantees exactly one re-fire, the same shape a store-handoff consumption has always had.

**The anchor receipt on the pushed deck (ruling 2).** `inlineAnchorShown = (canvasHost === 'flag' || isResultsPushed) && fairDeck && !!inlineAnchor`; `inlineAnchor` is seeded from the param's `anchorLabel`. Change forks `canvasResultsLive ? handleBrowseAnchorChange : isResultsPushed ? handlePushedAnchorChange : handleAnchorChange` — the pushed arm pops (below). Clear keeps `handleSearchAllTrades` (drop the anchor, model-search the same partner, in place on the pushed deck — `fairDeck` cleared by that path as ever).

**Edit in calculator pops with prefill (ruling 3).** The deck card's edit action `handleEditInCalculator` → `if (inlineHomeOn) loadCanvasPrefill({opponentId, give, receive})`; `loadCanvasPrefill`'s FIRST statement forks `if (isResultsPushed) { popToLanding(p); return; }`. `popToLanding` calls `navigation?.popTo?.('TradesHome', {canvasPrefill: p, canvasPrefillSeq: Date.now()})` — **popTo, never navigate**: `@react-navigation/routers` 7.5.3 `StackRouter` `NAVIGATE` reuses an existing route only when current/`pop`/`getId` (G-056, cited from `node_modules/@react-navigation/routers/lib/module/StackRouter.js`), while `POP_TO` (same file :349-421) walks down to the existing `TradesHome` and rebuilds its params from `routeParamList` (initialParams `{mode:'guided'}` survive) + the payload. The landing's existing bridge consumer (`useEffect` on `route?.params?.canvasPrefillSeq` → `loadCanvasPrefill(p)` + param clear — the MatchesScreen B1 bridge) seeds the canvas and scrolls to it. Loop closed: build → push → tweak → the next Find a Trade pushes a fresh deck (`navigation.push`, always a new instance).

**✓/✕ classic on the pushed deck (ruling 4).** With the deck tree live, ✓/✕/swipe route through `SwipableTopCard`/`advance()` exactly as on any deck; `deckOrigin === 'calculator'` (from the param) keeps `reasonsAsOverlay` and the calculator-first exits; end-of-deck renders the classic `trades.deck-summary` tally (`N passed · N liked · N proposed`, "See liked", "Done") and both "Back to calculator" buttons call `handleBackToCalculator`, whose D-171 arm is a plain `popToLanding()` — no prefill, because a fair deck has no pins and the pin-derived prefill would clear the landing's canvas.

**The landing is the builder only (ruling 1).** Under `resultsPushLive`: the choke point returns (refs cleared) before any dispatch; the first-run auto-start refuses (`resultsPushLive || isResultsPushed`); a consumed store handoff (league-rankings Offer) forwards into the push; and `landingDeckRetired` nulls the deck tree, lane pills, both progress strips, the featured window and the alternates panel. The landing ✓ keeps its full current behavior: `utils/queueCalcTrade` → `POST /api/trades/queue` (ungated per D-170) + the G22 like moments (`recordCanvasQueueLike`, gate widened to `landingDeckRetired`).

**Kill switch (ruling 5).** `calc.results_push:false` ⇒ `resultsPushLive` constant-false ⇒ every push/retire/forward/refusal branch dead; `handleInlineFindATrade` falls through to the in-place arm and `landingDeckRetired` degrades to `canvasResultsLive` — with `calc.canvas_results:true` that is the #402 browse session byte-for-byte, with it false the v1.16.10 deck-below-canvas page. A pushed instance alive across the flip stays a coherent deck page (suppression keys off the param, not the flag).

## 7. Manual TestFlight checklist (v1.16.14 — the only runtime evidence, D-056)

1. **Push + back round trip:** Trades landing → add nothing → tap Find a Trade. Expect: a NEW page pushes ("Trade ideas" header, Back control), model search narrates, classic swipe cards appear. Tap Back → the landing returns with an empty canvas, no deck below it.
2. **Fair fork:** on the landing add 1–2 give-side players (optionally pick a partner) → Find a Trade. Expect: pushed page shows "Built around <player>." receipt on top and fairness-anchored cards; every card's give side carries the anchor.
3. **Receipt Change / Clear:** on that pushed deck tap **Change** → expect a pop back to the landing with the canvas still holding the build. Find a Trade again; on the new deck tap **Clear** → expect the receipt to disappear and a model search to run in place for the same partner.
4. **Edit in calculator prefill pop:** on any pushed card tap its edit-in-calculator action. Expect: pop to the landing with the card's exact give/receive (and partner) loaded in the canvas. Tweak one asset → Find a Trade → a fresh deck built around the tweak.
5. **✓ like + advance:** on a pushed card tap ✓. Expect: success toast, deck advances to the next card. (Mirror check, if a second account is feasible: the counterparty's deck shows that trade pinned top with the flare "They're interested" pill — this is gap C1 closing.)
6. **✕ decline capture:** tap ✕ on a card. Expect: the decline-reasons overlay (calculator-origin presentation), tiles work, completing or dismissing after layer 1 advances the deck.
7. **End-of-deck:** swipe/decline through a short deck (a scoped fair deck is quickest). Expect: the classic tally card ("Deck done — x passed · y liked · z proposed"), "See liked", and "Back to calculator" → pops to the landing with the canvas intact.
8. **Kill switch:** operator flips `calc.results_push` to false (+ `calc.canvas_results` true) in Render env config, `POST /api/feature-flags/reload`, force-quit + relaunch the app. Expect: Find a Trade browses results inside the canvas again (pager `1 / X`), no push. Flip back afterwards.
