# #246 — Guided-first Acquire landing (V1)

**Status:** built, tsc-clean, committed on the worktree branch (2026-08-05).
**Operator decision:** approved **V1 (guided-first)** from the Opus lab (`mockups/polish-lab-2026-08/acquire-landing-guided-first.html`) — "delete the hub and land the tab in the guided deck", chip strip as the persistent mode switcher, Trade DNA as a sheet over the deck. **Mid-build operator override:** Free Agency is a **fifth chip at the top of the page** (the "fifth chip" fix the mock itself flagged for the 711pt below-fold problem), NOT the mock's tail section — the FREE AGENCY tail section was dropped entirely.

## What changed

### 1. Route swap, not a rewrite (`mobile/src/navigation/TabNav.tsx`)
With flag `trades.finder_hub` on, the Trades-stack root **`TradesHome` now renders `TradesScreen` with `initialParams {mode:'guided'}`** — the tab lands in the guided deck. `TradeFinderHubScreen` is no longer registered (or imported) anywhere. Flag off is byte-identical to pre-hub behavior (TradesScreen standalone, no mode param, `TradeDeck` unregistered).

`TradeDeck` **stays registered** (same component) so the `ux.deeplink_router_v2` path `app/trades/finder` still resolves — a link there pushes a second deck instance over the landing; back returns to the landing. No route 404s.

**Call sites verified — kept working unchanged (land on trades now):**
- `LeagueScreen.tsx:328` — `league.action.find` → `navigate('Trades', {screen:'TradesHome'})`
- `MatchesScreen.tsx:547` — `matches.go-to-trades` → same
- `TradeCalculatorScreen.tsx:577` — `calc.find-a-trade` (#213) → `navigate('TradesHome')`
- `utils/deepLinks.ts:122` — `TradesHome: ''` (base path `app/trades`); deep-link params merge over `initialParams`, so a bare link still lands in guided mode
- `MatchesScreen.tsx:669`, `QuickSetTiersScreen.tsx:204` — `navigate('Trades')` (tab-level) → initial route TradesHome → deck

**The mock's three re-points, done:**
1. `OutlookBiasReceipt` — Change no longer navigates to `TradesHome {editDna:true}`; it fires an `onChange` callback and TradesScreen opens the DNA sheet (below). The component dropped its `navigation` prop.
2. `TradeFinderModeBar` — the `onHub` prop + "‹ Hub" chevron deleted (`trades.finder-mode.hub` testID retired).
3. `TradesScreen` F10 deck-done summary (`handleSummaryDone`, was :2355) — the finder-mode branch navigated back to the hub; it now settles into the exhausted state in every mode (the deck IS the landing).

### 2. Chip strip (`mobile/src/components/TradeFinderModeBar.tsx`)
Today's mode bar minus the "‹ Hub" chevron and minus the always-on hint line; the mode title stays. Chips: **Guided · Team · Player · Calc · Free agents**.
- Guided/Team/Player switch in place (`setParams`, pins persist); Team opens the in-screen manager picker as before.
- **Free agents is a navigation chip** → root-stack `FreeAgents` (`onFreeAgents`; testID `trades.finder-mode.free-agents`). Styled identically to the other chips — the Calc chip already set the push-chip precedent, so there is deliberately no visual distinction (the operator asked for "subtle" if any).
- **Hint line is now conditional** (`showHint` prop): TradesScreen passes `deck.length === 0`, so the one-line mode description shows in the cold start (mock B2 — "the one place V1 spends a conditional") and drops once a deck exists (mock B1).
- Kept order Guided · Team · Player · Calc (the shipped bar's + mock B1's order) with Free agents appended; the brief's enumeration ("Guided / Player / Team / Calculator") was read as a list, not a reorder — flag if the operator wanted Player second.

### 3. Trade DNA → sheet over the deck (`mobile/src/components/TradeDnaSheet.tsx`, new)
The hub's #212 DNA editor body **lifted verbatim** into a bottom sheet hosted by the deck (mock B3): four outlook cards + Chasing/Shopping multi-select rows + untouchables count/Manage line, with the **#236 autosave machinery unchanged** (every tap POSTs the full payload, one request in flight with trailing coalesce, failure reverts drafts + inline error) — so **Done / scrim-tap is a pure dismiss; there is no Save button**. Saves invalidate the shared `['league-prefs', leagueId]` cache, so the receipt line and Controls-Card outlook update behind the sheet.

- Opened by: the receipt's Change (`trades.outlook-receipt.change`) and the **legacy `editDna:true` route param** on TradesHome (old stored routes/deep links) — TradesScreen consumes the param and opens the sheet, so nothing that set it breaks.
- **Untouchables management stays reachable:** the sheet's Manage link (`finder-hub.dna.untouchables`, id kept) opens the #173 list+remove sheet, rendered as a second layer INSIDE the same Modal (iOS won't present sibling Modals). Row/remove testIDs kept.
- testIDs change host, keep ids: `dna.outlook.*`, `dna.chase.*`, `dna.shop.*`, `dna.done`, `finder-hub.dna.untouchables`, `finder-hub.untouchables.row/remove.*`. Dormant (lived on the hub's collapsed panel): `dna.edit`, `dna.untouchable.<id>`.
- Implementation note: the editor code is duplicated between the sheet and the unrouted hub file rather than shared — the hub is scheduled for deletion, and threading a shared component through a dead screen bought nothing. The cleanup pass that removes `TradeFinderHubScreen.tsx` erases the duplication.

### 4. Free Agency
Per the operator override: **no tail section** — the Free agents chip in the strip is the deck's FA entry (above the fold, no scroll; strictly better than the mock's measured 711pt tail). The deck's old `trades.explore.free-agents` Explore row was `!finderMode`-gated and therefore never renders on the landing (it survives on the classic flag-off home). Other FA entry points untouched: League tab Explore tile, unrouted hub's #245 row.

### 5. Hub disposition
`TradeFinderHubScreen.tsx` **stays in the tree, unrouted** — no navigator registration, no imports (TabNav's import removed). Registry rows in `mobile/src/screens/CLAUDE.md` carry the "UNROUTED as of #246" marker; removal is a later cleanup (with it goes the duplicated DNA editor code and the `finder-hub.card.*` / `finder-hub.team-picker.*` ids).

### 6. First-run (verified by code path, mock B2 "needs no new design")
`TradesScreen`'s first-run latch (`onboarding.trades_first` + `!firstSwipeDone`, latched at mount) is **independent of `finderMode`** — it now fires on the landing itself: collapsed chrome, identity-confirm strip, skeleton deck + auto-generation (the `firstRun && leagueId` effect), OutlookSheet first-visit force-open (unchanged, non-first-run only). This actually FIXES a pre-#246 gap: with the hub routed, `onboarding.trades_first` users landed on the hub and the deck's first-run never ran until they tapped a mode card. The mode strip renders in first-run with the hint line (cold start ⇒ `deck.length === 0`), matching mock B2 exactly. The non-onboarding cold start keeps the classic "Hit Find a Trade to start" empty card.

## Nothing 404s — reference sweep
- `navigate('TradesHome')` × 5 call sites — all land on the deck (list above).
- `navigate('TradeDeck', …)` — only the unrouted hub navigates there in-app; the route stays registered for the `app/trades/finder` deep link.
- `editDna` param — only ever set by the receipt (now callback-based); the param is still honored on TradesHome for stored routes.
- `trades.finder-mode.hub` — retired with the chevron; no Maestro flow in `mobile/.maestro/` references it (checked).
- Docs: `mobile/src/navigation/CLAUDE.md` (TradesHome semantics — the significant change), `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` (+ #246 testID tranche), `docs/glossary.md` (Acquire tab entry).

## Verification
- `cd mobile && npx tsc --noEmit` — clean.
- Not visually verified (no simulator run in this worktree session); every piece is a re-composition of shipped surfaces — the deck, the mode bar, the #236 autosave editor — re-hosted, not rebuilt.
- Watch items for QA: (a) the DNA sheet's inner untouchables layer on Android hardware-back (onRequestClose closes the inner layer first); (b) a deep link to `app/trades/finder` now stacks a second deck instance — works, but back-gesture semantics are worth one manual pass; (c) Maestro flows that navigated Hub → mode card (`finder-hub.card.*`) need re-pointing to the chip strip.
