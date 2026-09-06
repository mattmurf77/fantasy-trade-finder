# Mobile trade experience review

Reviewed 2026-09-04 against `origin/main` commit **606e512cd87f692eced3b92ccadb4f0192ea3449** (2026-09-03). This is a presentment, navigation, and interaction review, not a review of trade valuation or search quality.

September 5 scope update: [the owner-decisions engineering handoff](../decisions.md) supersedes unapproved presentation recommendations here. Preserve the historical continuity findings for verification, but do not implement proposed extra receipts, selection controls, inference explanations or card panels wholesale. The owner wants the existing trade-chip tags and brief no-match notice for partial alternatives, existing tier/draft-pick language, and the same selection promise across entrances.

## Assessment

The app has the components of a coherent trade experience, but its entrances still teach different contracts. The builder treats the send side as fixed and the receive side as a preference; League rankings treats an Offer/Target selection as a pin; More offers starts a new single-player search. The screen transitions do not consistently explain these differences. A user can reasonably believe they are continuing the same trade while the selected asset, search scope, or meaning of an action changes.

The most urgent changes are behavioral clarity and continuity: preserve a hand-built draft on return, carry receive-side intent, keep Retry within the original search, render real pending/empty states for anchored results, and stop calling an in-app suggestion a sent offer. These need attention before visual consolidation. A common header, card vocabulary, context receipt, and back contract can then make the different entrances feel like one product.

## Evidence and boundaries

- Every source line reference in this report refers to the fixed commit above. Linked source references are immutable GitHub commit links. The shared working checkout was at `05e87d8` from August 15 with extensive unrelated modifications; it was preserved. Source was inspected from an isolated archive of the reviewed commit.
- This is **code-walk evidence**. No TestFlight device session, simulator, Maestro run, screenshot capture, or visual measurement was performed. A deterministic source path establishes what is wired; it does not establish actual animation, touch, scroll, VoiceOver, or frame behavior on an iPhone.
- P1 means a core task can change meaning, lose context, or produce a materially misleading outcome. P2 means a significant consistency, discoverability, recovery, or presentation problem. P3 means polish. No P0 finding is claimed.
- “Confirmed wiring” below means directly present in source. “Runtime verification” identifies the remaining device-dependent proof, rather than suggesting a device failure was observed.
- The repository's D-056 rules retire simulator/Maestro validation. The manual TestFlight checklist below is the required next source of runtime evidence. This review changes only this document.

### Configuration used to interpret reachability

The reviewed `config/features.json` sets the following defaults. Server or per-user overrides were not queried.

| Active | Inactive |
|---|---|
| `calc.merged_layout`, `calc.inline_home`, `calc.results_push` | `calc.canvas_results` |
| `trades.finder_hub`, `trades.edit_full_sheet`, `trades.sheet_targeting` | `trades.presentation_v2` |
| `trade.shop_asset`, `trades.player_offers_calc` | `trade.outlook_direction` |
| `league.pos_candidates`, `feedback.decline_reasons`, `nav.trades_landing` | — |

The `trades_home_inline.strip` / `.canvas` experiment can still alter the utility chrome. Its assigned variant was not observed. Accordingly, references to the utility row are conditional. Team/Player mode chips are normally hidden by the active sheet-targeting/full-sheet conjunction; they should not be mistaken for the normal current landing. The old in-canvas result pager and Today presentation are dormant, not the current UX.

### Current journey, as wired

| Entrance | What actually searches | Result and return |
|---|---|---|
| Acquire, empty builder → Find a Trade | Model search. The untouched auto-selected partner does not scope it; an explicitly selected partner does. Existing finder pins can still participate. | Pushes `TradeDeck`, header “Trade ideas.” Back pops to the builder. |
| Builder, send assets → Find a Trade | Fair-package sweep. Exactly the send assets are anchored. Receive selections are preferences, not required returns. | Same pushed deck, with “Built around…” for the send assets. Change pops back; Clear starts a different, unanchored model search. |
| Builder, receive assets only → Find a Trade | Model search scoped to the chosen owner. The builder's receive IDs are not transferred as targets. | Same pushed deck; it need not acquire the selected player. |
| League rankings, position view → Offer / Target | Writes one give/receive pin and opponent to the finder, then auto-runs a model search. | Switches to Acquire; the landing forwards to a pushed deck. Its ordinary Back is the Acquire builder, not the League team view. |
| Result send-side More offers | Single selected send asset; multiple send assets first open “Shop which player?” All-league asset-ideas search; default mode is Tier up. | Root-stack “Shopping [player]” page, no bottom tabs. Explicit Back returns to the originating deck. |
| Result receive-side Keep · more offers | Pins the receive side and regenerates the model in the same deck instance. | Different interaction from the adjacent send-side chip; can move into the older featured-trade/pinned presentation. |
| Result Edit in calculator | Pops to the builder with the complete result package and partner. | The original results route is removed; a subsequent Find a Trade starts a fresh results instance. |
| Real values / Manual calc utility | Opens the league-free calculator. | Header says “Calculator”; the live In-league tab is absent. Its Find-a-trade link pops to the builder without transferring this separate draft. |

Key routing evidence: [TabNav.tsx:428](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/navigation/TabNav.tsx#L428), `TradesScreen.tsx:2957–3195`, `canvasSearch.ts:41–79`, `LeagueSummaryScreen.tsx:1168–1204`, `TradesScreen.tsx:3431–3466`, `RootNav.tsx:857–884`.

## Prioritized findings

### UX-01 · P1 · Selecting someone to receive does not mean the search will acquire them

**Scenario:** I want a specific WR. In the builder I select his team and add him to You receive, leaving You send empty because I want the app to find the price. I tap Find a Trade. I can receive suggestions for different players on that team. If I first add a player to You send, my selected WR is still only a preferred result. By contrast, Target on that WR in League rankings writes a receive pin.

**Confirmed wiring:** [canvasSearch.ts:49](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/utils/canvasSearch.ts#L49) sets `fair` solely from give count and returns `anchor: null` on a receive-only build. `TradesScreen.tsx:3186–3194` transfers only that anchor and partner; it does not transfer `fork.receiveIds` separately. The model request reads receive pins from `useFinderTargets`, not the calculator (`TradesScreen.tsx:1852–1881`). The fair API contract explicitly calls receive assets a preference (`api/trades.ts:438–441`). League Target writes the player to the receive-pin store (`LeagueSummaryScreen.tsx:1183–1185`).

**Impact:** The same apparent “trade for this player” intent produces different guarantees depending on where it began. The symmetric You send / You receive layout reinforces a stronger promise than the search honors.

**Recommended outcome:** Give each selected asset a clear contract: required or optional. A receive-only build should carry “Get [player]” intent. A result that relaxes that intent must be presented as an alternative, with an explicit explanation. If the existing fairness-only sweep is retained unchanged, show its scope before the tap: “Keep this send package; explore returns,” and present desired receives separately as preferences. This is a product-contract choice, not a request to change engine math silently.

**Acceptance:** Starting from the same player through League Target and through the builder produces the same visible required-player contract, or the difference is explained before search and in the result receipt.

### UX-02 · P1 · A first scoped search can erase the hand-built draft on the return trip

**Scenario:** Starting with a fresh builder, I add both sides of a trade, or explicitly choose a team and add a send package. I search, inspect a result, then press Back or the anchor receipt's Change. I expect the exact draft I just searched from.

**Confirmed wiring and high-confidence state inference:** Search calls `setSheetOpponent(fork.opponent)` immediately before pushing (`TradesScreen.tsx:3185`). That parent scope is passed to the canvas at `:7599`. [TradeBuildCanvas.tsx:168](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/components/TradeBuildCanvas.tsx#L168) derives its opponent from prefill or that parent scope, then uses it in the calculator's React key at `:184`. The change from no parent opponent to the calculator's selected opponent remounts the calculator. The initial sides come only from `prefill?.give/receive` (`:188–189`), which are absent for a manually built draft. The sides are otherwise local state (`InLeagueCalculator.tsx:393–394`); their change callback is not wired on the active builder (`TradesScreen.tsx:7615` is browse-session-only). Back and Change perform a plain pop (`TradesScreen.tsx:3324–3338`, `:3577–3585`).

**Impact:** The advertised build → results → tweak loop can lose the user's work precisely when they ask to change it. The result request can be correct while the builder underneath has already reset.

**Recommended outcome:** Preserve a draft snapshot independently of the result route. Selecting or synchronizing a partner must not remount the send side. A deliberate partner change may clear incompatible receive assets, with a visible explanation. Back restores the original draft; Edit result intentionally replaces it with that result.

**Runtime verification:** Test a first scoped search from a never-prefilled builder, an unscoped search, and a search after Edit-in-calculator. The failure is path-dependent; checking only the prefilled case can miss it.

### UX-03 · P1 · Result-page search and Retry silently abandon the anchored search

**Scenario:** I search around two players I want to sell. On the results page I tap Find a Trade / Find more trades, or the original search fails and I tap Try again. I expect more results for the same package or a retry of the failed request. The next request is a model search without that fair-package anchor.

**Confirmed wiring:** [TradesScreen.tsx:7390](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/TradesScreen.tsx#L7390) mounts a primary search bar whenever the canvas is absent, including the pushed result page. It calls `handleFindTrades`, which explicitly clears `fairDeck` and dispatches the model (`:1097–1112`). The error card's Try again does the same (`:8645–8650`). Neither path replays `resultsPush.fairAnchor`.

The anchor receipt also labels its unanchored model search simply **Clear** (`:7719–7733`), although the builder's Clear empties only its sides (`InLeagueCalculator.tsx:860–865`). On a fair deck `job` is set to null (`TradesScreen.tsx:3551`), so the top bar can continue saying Find a Trade rather than Find more trades even while results exist.

**Impact:** Several controls that read as continuation or cleanup actually change the question. The anchor disappearing afterward does not substitute for explaining the change before the tap.

**Recommended outcome:** Retry replays the same complete search request. “Find more” retains the same constraints. An explicit **Search without this package** action can broaden the search. Rename the receipt's Clear to that action, or make Clear only remove the constraint and wait for a deliberate search.

**Acceptance:** The asset/package/team receipt stays unchanged across Retry and Find more. Broadening is a separately named action and makes the changed receipt visible.

### UX-04 · P1 · Anchored results lack a true pending state and a true zero-results state

**Scenario:** I submit a difficult send package on a slow connection. The page can look like I have not started searching. If the sweep returns zero ideas, a returning user can see “Hit Find a Trade to start.” A first-run user can instead remain on the first-run skeleton because no completed job exists.

**Confirmed wiring:** [TradesScreen.tsx:3519](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/TradesScreen.tsx#L3519) is a plain async fair request; it sets no pending flag or running job. On success it stores ideas, sets job null, and sets `fairDeck` true (`:3549–3552`). The classic deck waits on `generateMutation.isPending` or a running job (`:8443`), has no fair-zero branch, and falls through to idle (`:8681–8687`). The first-run skeleton condition at `:8423–8442` also lacks a fair-completed guard. The explicit fair-zero UI at `:7833–7843` is inside the dormant `canvasResultsLive` rendering branch.

The fair API provides `reason` and `relaxed` (`api/trades.ts:456–460`), but the shown fair-response handler does not retain them. That prevents the result UI from distinguishing a blocked asset, missing partner, and a completed search without offers.

**Impact:** The interface contradicts a completed user action, invites extra searches, and cannot give a useful recovery. This is a regression risk from reusing the classic result tree for a synchronous search source.

**Recommended outcome:** Both result sources expose the same lifecycle: searching, results, zero results, exhausted, and failed. Preserve the search receipt throughout. A zero-result state should name the fixed package and team scope and offer Change search plus an explicit broadening action. First-run rendering must honor a completed zero-result search.

**Acceptance:** Pending, zero, and failure never render the never-searched prompt. The page shows one running search and disables duplicate submission. Error Retry retains the original scope.

### UX-05 · P1 · “Send this offer” actually queues a suggestion inside Fleeced

**Scenario:** In More offers, I find a package and tap Send this offer. I believe it was proposed in Sleeper, ESPN, or MFL. The success toast instead says it will show in the other manager's suggestions.

**Confirmed wiring:** [ShopOffersBody.tsx:1032](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/components/ShopOffersBody.tsx#L1032) uses label “Send this offer.” Its handler at `:696–714` calls `queueCalcTrade`, not the platform send router. `queueCalcTrade.ts:70–75` calls the in-app queue route; `:96–98` returns the suggestions-only success copy. The builder exposes the same action as an unlabeled checkmark with accessible name “Queue this trade for the other manager” (`InLeagueCalculator.tsx:1383–1409`). The classic deck calls its checkmark Like (`TradeCard.tsx:823–831`).

**Impact:** Three surfaces express related interest actions with three different levels of implied commitment. The shop's strongest wording is unsupported. The short toast is the only correction after the tap, and the card's CTA returns to “Send this offer” after success.

**Recommended outcome:** Reserve **Send in [platform]** for an actual platform proposal with the existing confirmation/auth flow. Use a consistent, visible **Like** or **Suggest in Fleeced** label for the in-app action, with concise explanatory copy wherever its visibility to another manager matters. The exact word should match the retained backend semantics; a queue action must not be called a private save. After success, show a persistent Liked / Suggested state and an appropriate destination.

**Acceptance:** A tester can explain before tapping whether the action stays in Fleeced or proposes a league trade. Success, duplicate, refusal, and network failure are visibly distinct; success persists beyond the toast.

### UX-06 · P1 · Draft, finder pins, and league scope do not have one reset contract

**Scenario A:** I enter from League Target, return to the builder, clear the visible trade, and search again. The older receive pin can still affect the search. **Scenario B:** I build a trade in League A, switch to League B, and encounter leftover selected assets or a partner from A.

**Confirmed wiring:** League entry writes finder pins (`LeagueSummaryScreen.tsx:1183–1185`); the model always reads them (`TradesScreen.tsx:1852–1874`). Builder Clear only clears local give/receive IDs (`InLeagueCalculator.tsx:860–865`). It does not clear finder targets. The separate pin-summary clear at `TradesScreen.tsx:3477–3505` owns that reset instead.

For league changes, [TradesScreen.tsx:2165](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/TradesScreen.tsx#L2165) resets deck, pins, and browse state, but not `sheetOpponent`, `canvasPrefill`, or the mounted calculator's local sides. The canvas key at `TradeBuildCanvas.tsx:184` contains no league ID. Calculator sides initialize once (`InLeagueCalculator.tsx:393–394`), and its asset resolver includes the full player value list (`:547–564`). Changing league data alone therefore does not remove every old selection. Whether a navigation/session branch incidentally remounts the whole screen on a particular device path needs verification; the canvas itself has no complete league-reset contract.

**Impact:** “What I can see in this builder” is not the complete search state. The converse also occurs: valid assets may disappear on a partner synchronization even though invalid cross-league context can survive a league change.

**Recommended outcome:** Make one league-scoped trade draft the source of truth for asset selections and team scope. Distinguish saved preferences from this search's requirements. Show every active requirement near the builder/result; Clear build and Clear search have explicit, different meanings. A league switch atomically resets or restores only that league's draft, never carries foreign roster IDs or a foreign partner.

**Acceptance:** Clearing all visible requirements yields an unanchored, unpinned search. Switching between two leagues cannot leave a player selected merely because the same player exists in the global value catalog. Test both normal builder changes and a prior result prefill.

### UX-07 · P2 · More offers silently changes scope, package, browsing behavior, and available actions

**Scenario:** I am evaluating a two-for-two trade with one specific manager. More offers asks me to pick just one outgoing player, then shows Tier up ideas from other teams. I can page sideways without liking or passing, but cannot edit an interesting alternative into the same builder from this page.

**Confirmed wiring:** `TradesScreen.tsx:3423–3428` reduces a multi-player send side through a chooser. [TradesScreen.tsx:1592](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/TradesScreen.tsx#L1592) passes only the selected asset and league to `ShopAsset`; no opponent, whole package, or search settings travel. `ShopOffersBody.tsx:299` initializes Tier up, and `:383–409` requests asset ideas without opponent/fairness parameters. Its full result-tile action row (`:1016–1047`) offers dismiss and queue, but no edit-in-builder or platform-send bridge. Its horizontal pager is browse-only (`:962–979`); the originating deck's swipe hint says right to like / left to pass (`TradesScreen.tsx:8372–8374`).

**Impact:** A continuation label opens a different task. The chooser usefully explains “one player at a time,” but it does not explain the change from one manager to all teams. Identical sideways gestures stop meaning the same thing across adjacent result surfaces.

**Recommended outcome:** Keep this as an intentional alternative-results page, but state the context before and after entry: **More offers for [player] · All teams**. If dropping a fixed package or team is required, make that scope change explicit. Carry supported constraints; visibly disclose unsupported ones. Use the common result card and add Edit trade. Keep browse paging and disposition visually separate, with an explicit swipe hint and accessible Next/Previous controls.

**Acceptance:** Entering More offers never silently promises to preserve a package/team that it discards. Header Back returns to the exact original card and any in-card edits. Editing a shop alternative opens that exact package in the same builder.

### UX-08 · P2 · The paired trade-side chips look parallel but have different navigation and history

**Scenario:** On one card I see More offers beneath what I send and Keep · more offers beneath what I receive. I expect the same exploration in opposite directions. One opens a new page; the other replaces the current deck and writes persistent finder pins.

**Confirmed wiring:** Both use the same button construction in [TradeCard.tsx:437](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/components/TradeCard.tsx#L437). `TradesScreen.tsx:3442–3448` routes the send side to shopping; the receive side falls through to `setSide`, reset, and model generation at `:3461–3466`. The special back snapshot is captured only from a clean, unpinned deck (`:3456–3458`), so nested exploration does not have general history semantics. A multi-asset send chip's accessible label says “around the players you send” even though the chooser keeps only one.

**Recommended outcome:** Name the actual intents: **Other returns for [send package]** and **Other ways to get [receive package]**, or shorten them consistently with an adjacent context label. Both should open an explicitly scoped alternative-results step and preserve their origin. If their mechanics remain different, the label and navigation affordance must make that difference apparent.

### UX-09 · P2 · The builder hides search controls that reappear after the search, and the result instance loses local settings

**Scenario:** I try to set fairness or a trade shape before searching. The landing's Outlook → Change opens a reduced editor. The pushed result page's Change opens a fuller editor with fairness, intent, and targets. If I choose Tier up there, return to the builder, and run again, the new result instance starts with a null local trade intent.

**Confirmed wiring:** The builder mounts `TradeDnaSheet` without `full` at [InLeagueCalculator.tsx:1569](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/components/InLeagueCalculator.tsx#L1569). Its host's full-sheet entry stands aside when `canvasHost === 'flag'` (`TradesScreen.tsx:6515`). Pushed results have no canvas and regain the full sheet at `:6275–6321`. `tradeIntent` and `laneFilter` are screen-local state initialized to null (`:537–543`), and are absent from the pushed request contract at `:837–844` / `:3186–3194`. Fairness is separately hydrated asynchronously from storage (`:1077–1092`); the fair-package request does not pass the supported fairness parameter (`:3530–3537`, `api/trades.ts:468`).

With the reviewed `trade.outlook_direction: false`, the calculator's fallback says “Outlook · Not set” (`InLeagueCalculator.tsx:929–931`) rather than distinguishing an unavailable effect from a saved choice. This makes the reduced entry even less descriptive.

**Impact:** The most useful moment to set a search condition is before search; the current interface exposes some conditions mainly afterward. Similar-looking receipts do not expose the same controls or guarantee the same persistence.

**Recommended outcome:** One Search settings sheet, available from both builder and results, with a shared request snapshot and consistent terminology. Saved league preferences and temporary search filters should be visibly distinct. If an anchored search intentionally ignores a setting, explain that setting's applicability. Do not present a disabled feature as proof the user has never set an outlook.

**Acceptance:** A setting chosen in results is either retained for the next search or clearly marked as applying only to this results session. The active request, its receipt, and every retry use one resolved set of conditions.

### UX-10 · P2 · League's buyer/seller flow changes tab and loses its return destination

**Scenario:** I filter League rankings to WR, inspect a seller, and tap Target on a player. Results open in Acquire. Back returns to a builder I did not intentionally visit; I must know to retap League to regain the original comparison.

**Confirmed wiring:** [LeagueSummaryScreen.tsx:1168](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/LeagueSummaryScreen.tsx#L1168) records pin and opponent, then navigates to `TradesHome` at `:1204`. That landing forwards to `TradeDeck` (`TradesScreen.tsx:2968–2988`). The payload includes no source route, focused team, or return action. The results header is generically Trade ideas with a TradesHome fallback (`TabNav.tsx:458–464`).

The visible League verbs are **Offer** and **Target**, not Buy/Sell (`LeagueSummaryScreen.tsx:2121–2123`). Buyer/Seller labels are positional rank bands (`:1016–1030`), not evidence a manager has declared trading intent. They appear only for a specific combination: one core position, no Picks, All roster subset (`:858–863`). A roster row that looks like a player item is also the entire search-launch button (`:2101–2109`).

**Recommended outcome:** Keep the beneficial direct search, but carry an origin and show a receipt such as “Get [player] from [team].” The result's Back should return to the League team/position context, while Edit search deliberately opens the builder. Explain Buyer/Seller as inferred positional supply/need, or label them “Likely WR seller/buyer.” Offer should read “Find offers” where space permits, since tapping it does not propose a trade. Ensure a visible instruction explains how to enter the positional candidate view when the current filter is ineligible.

**Acceptance:** Returning from the result restores the selected team, position, subset, and scroll location. Player details remain discoverable without accidentally launching a search. Changing to Starters, Bench, multiple positions, or Picks has an understandable effect on the candidate controls.

### UX-11 · P2 · “See liked” opens player ownership instead of liked trades

**Scenario:** I finish liking several results and tap See liked. With one league, I see a prompt to connect a second league. With multiple leagues, I see player exposure.

**Confirmed wiring:** [TradesScreen.tsx:8538](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/mobile/src/screens/TradesScreen.tsx#L8538) navigates See liked to Portfolio. `PortfolioScreen.tsx:24–27` defines that screen as cross-league ownership; `:53–60` gates it on two leagues. Matches already distinguishes mutual matches and liked trades awaiting the other manager (`MatchesScreen.tsx:92–94`, `:206–214`).

**Recommended outcome:** Route See liked to the actual liked/awaiting inventory, with the relevant league selected and a stable way to return to the result session. Preserve a separate entry for Portfolio under its actual name. Verify whether matched and already-proposed trades belong in the same inventory or a neighboring segment; do not hide a successfully liked idea solely because its status changed.

### UX-12 · P2 · Shared result vocabulary and hierarchy are incomplete

**Scenario:** I move from Fully Guided / Build a trade to Trade ideas, then Shopping [player], then Calculator. Each screen looks related, but I have to infer whether I am building, searching, browsing, or proposing. The shopping card shows an unexplained signed number where the deck and calculator provide a richer value comparison.

**Confirmed construction:** `TradeFinderModeBar.tsx:24–47`, `:145–164`, and `:180–183` mixes the Guided selection with destination chips including Real values and Free agents. Under the experiment, the same calculator destination is labeled Manual calc (`TradeHomeUtilityRow.tsx:102–114`). Its navigator title remains Calculator (`TabNav.tsx:499–505`). The builder is separately labeled Build a trade (`TradeBuildCanvas.tsx:182`). Pushed results reuse the mode/utility region (`TradesScreen.tsx:6391–6462`), Team review (`:6653–6662`), and primary search bar (`:7390–7402`) above the results, rather than presenting a reduced results-only hierarchy.

The deck uses the shared `TradeValueBar` (`TradeCard.tsx:918`); the builder uses it in `LeagueVerdict` (`InLeagueCalculator.tsx:1807`). The shop instead renders a bare rounded `item.difference` with sign/color (`ShopOffersBody.tsx:997–1013`) and compact name-only asset rows. Its display does not name the number's unit or basis there. The shop has useful count-bearing modes, but “Same value” means tier membership (`:190–192`), so it can still show a nonzero difference.

**Recommended outcome:** Use one sequence of screen identities: Find a Trade → Trade ideas → More offers for [asset]; use Edit trade for the return to the builder. Label the separate utility by what differs, such as League-free calculator, rather than Real values. Use one result card contract across result sources: partner and league, both sides, a shared value summary, essential rationale when available, and the same action meanings. Explain missing evidence rather than fabricating it. Mode chips should switch a local result view; navigation utilities should read as destinations.

**Visual verification:** The source order supports a hierarchy concern, not a measured claim that controls are below the fold. Validate compact iPhones, long names, two-to-three assets per side, Dynamic Type, and safe-area/tab-bar treatment before specifying dimensions.

## What is already worth preserving

- The current builder-to-results push is a sound separation. Keep a focused preparation screen and a dedicated results screen; fixing continuity does not require resurrecting the dormant canvas pager.
- More offers preserves the originating deck by opening a separate screen. The explicit header Back is deliberate (`RootNav.tsx:873–880`). Keep that property while improving scope and action wording.
- Shop mode counts and position-aware empty states are useful. Explicit position selections persist across mode changes (`ShopOffersBody.tsx:749–756`), and same-value automatic broadening has a visible notice (`:942–948`). These are good patterns for the shared results contract.
- Queue refusals already explain specific conditions (`queueCalcTrade.ts:37–55`); Match-value disclosure and the main calculator already reuse the public evaluation path. Build on these existing shared pieces.
- Matches' cross-league Edit flow switches league through the real session handshake before loading a package, and reports a missing or failed league switch (`MatchesScreen.tsx:577–607`). Preserve that ordering while adding a clear return contract.

## Proposed coherent navigation and presentation contract

This is a proposed product contract for review. Some recommendations revisit recorded per-feature decisions; they are not claims that those previous changes violated their individual specifications. No app implementation or flag change is included here.

### One user request, several entrances

Each entrance should construct the same visible request:

| Field | Meaning shown to the user |
|---|---|
| League and format | The roster universe and value context |
| Team scope | All teams or one named team |
| Required send assets | What must leave my roster; whether a package stays together |
| Required receive assets | What I am trying to acquire |
| Optional preferences | Positions, trade shape, or desired additions that may be relaxed |
| Value/settings basis | Which saved preferences and fairness conditions apply |
| Origin and return context | Where Back returns: builder draft, League comparison, Matches row, or parent result |

The user does not need to see internal endpoint or model names. They do need to see whether an asset is required, what can vary, and whether the scope has broadened. Different search implementations may remain behind this contract.

### Screen and action roles

| Surface | Primary purpose | Primary action | Secondary continuation | Back |
|---|---|---|---|---|
| Find a Trade landing | Browse from scratch or describe a trade | Find trade ideas | Edit settings; clear draft with undo | Tab root |
| Trade ideas | Evaluate results for the stated request | Like / suggest, with its actual visibility explained | Edit trade; More offers; change search | Exact source context |
| More offers for [asset/package] | Explore alternatives under explicit constraints | Same interest action as other results | Edit trade; change team/position scope | Exact originating result |
| Builder entered from a result | Modify a concrete package | Evaluate / find ideas for this draft, clearly named | Like/suggest; platform proposal when complete | Explicit return to original ideas or source |
| Matches / liked inventory | Revisit outcomes and continue negotiation | Send in [platform], when available | Edit trade | Prior tab/session |
| League-free calculator | Compare assets without a roster constraint | Evaluate comparison | Deliberate Use in my league bridge, or clearly labeled return without transfer | Prior screen |

The interest action's final label should be settled once. Until its backend outcomes are fully aligned across surfaces, use accurate labels for the existing actions rather than masking different commitments behind one icon. The non-negotiable rule is that **Send in [platform] means a platform proposal**.

### Minimum results hierarchy

1. One screen title and an explicit Back destination.
2. A compact request receipt: “Get [player] from [team]” or “Offers for [package] · All teams,” with Change search.
3. Search status/count, with durable empty/failure/recovery states.
4. One primary trade card: both sides, partner, value basis and verdict, then interest/edit/alternative actions.
5. Secondary detail and a destination for liked/suggested trades.

The utility navigation, Team review, and acquisition-adjacent destinations should not compete with the first result. They can remain discoverable on the landing or in clearly subordinate navigation.

### State and recovery rules

- Back is non-destructive to the caller's draft and origin context. Edit trade is the deliberate action that replaces a draft with a result package.
- A partner change preserves outgoing assets and removes only incompatible incoming selections, with feedback. A league change never reuses another league's draft implicitly.
- Retry replays the identical request. Find more extends or reruns that request. Broaden search explicitly changes requirements and immediately updates the receipt.
- Clear draft, remove target, pass on idea, and close overlay are four different actions. Avoid using the same unlabeled cross or the single word Clear for multiple commitments.
- An idea can be pending, liked/suggested, declined, or proposed. Persist the useful status on the card or in the destination inventory; do not make a disappearing toast its only proof.
- The fixed anchor and the displayed result are different objects. In-card edits, further exploration, and suggestion actions must make clear which one they act on.
- Source-independent result states include searching, partial results, completed results, zero results, exhausted, failed, and obsolete because the league/request changed.

## Manual TestFlight checklist

Record app build, active flags/experiment variant, device size, league/platform, and whether the account is first-run. Use a controlled tester league for any actual platform-send verification; the ordinary review of labels and navigation does not require sending a trade. Capture a short observation for each case rather than marking a generic “trade flow passed.”

| ID | Steps | Expected evidence |
|---|---|---|
| TF-01 | Fresh Acquire visit; make no selections; tap Find a Trade. | One result page and one search. Receipt says All teams. The auto-displayed partner is not incorrectly presented as the search scope. |
| TF-02 | Select a receive-only player; search. Repeat using League → Target on the same player. | The visible required-player contract agrees across entrances. If alternatives are permitted, that is stated before results omit the player. |
| TF-03 | Fresh, never-prefilled builder: choose team, add both sides, search, then header Back. Repeat using receipt Change. | Both sides and team are restored exactly. This specifically exercises the parent-opponent/remount path. |
| TF-04 | Open a result in the builder, edit its sides, search, and return. Also search an unscoped send-only draft. | Draft restoration works for prefilled and manual paths; passing one does not stand in for the others. |
| TF-05 | From an anchored result, tap the top Find a Trade/Find more control. | Required send package/team remain in the new request and receipt. An explicit broadening action is the only path that drops them. |
| TF-06 | Cause an anchored search failure using connectivity interruption, restore connectivity, and tap Try again. | Same package/team retried; no unrelated model search. Error and pending state replace the failure honestly. |
| TF-07 | Search an anchored package known to return no ideas, on first-run and returning accounts. | Completed zero-result explanation; no never-searched prompt and no permanent first-run skeleton. Change search and broaden paths are actionable. |
| TF-08 | Slow an anchored search, tap once, then try to tap again/back immediately. | A visible pending state, duplicate-submission protection, and coherent navigation. No stack of duplicate result pages. |
| TF-09 | League Target a player, return to builder, clear visible draft/requirements, and search again. | No leftover finder pin affects an apparently cleared request. Any retained requirement remains visible and removable. |
| TF-10 | Build in League A, switch to League B from the builder, then switch back. Repeat after a result prefill and with a shared NFL player in both leagues. | Only the correct league's draft/partner is shown. No foreign IDs or incompatible selections survive. |
| TF-11 | Enter results from a League WR seller and from an RB buyer; go Back. | Team focus, position, subset, and scroll return intact. Offer/Target reads as search, not a sent proposal. |
| TF-12 | Open More offers from a one-player send and from a multi-player send package scoped to one manager. | The kept asset/package and All teams versus named team scope are explicit. Canceling the chooser leaves the original result untouched. |
| TF-13 | Browse More offers, switch Tier up/Tier down/Same value and positions; use Back. | Counts match visible cards; selected positions persist; broadening is disclosed; original deck card, edits, and position remain. |
| TF-14 | Swipe a classic result, then browse sideways in More offers; use VoiceOver instead of swiping. | Disposition versus paging is understandable. Accessible Next/Previous and Like/Pass alternatives exist with correct labels. |
| TF-15 | Use the interest action on builder, deck, and More offers. Exercise success, repeat, refusal, and offline failure. | Labels accurately describe in-app visibility. Persistent state agrees with outcome. No label falsely claims a platform trade was sent. |
| TF-16 | Like results, exhaust the deck, tap See liked, with one league and multiple leagues. | Opens the actual liked/awaiting inventory with those results, never the Portfolio gate. |
| TF-17 | Set search shape/fairness from results; return and search again. Open settings from builder and results. | Same relevant controls, explicit persistence rules, and receipt reflecting the actual request. Retry retains resolved settings. |
| TF-18 | Select one position in League, then add Picks, select two positions, change to Starters/Bench, and return to All. | Candidate controls appearing/disappearing is explained; no misleading buyer/seller declaration or accidental search from a details tap. |
| TF-19 | Open a Matches row for another league in the builder; fail then succeed the league switch. | Failure stays recoverable; success loads the exact package in its real league; the way back to Matches is evident. |
| TF-20 | Compare a trade in the league-free calculator, then use its Find-a-trade link. | The user can tell whether the comparison transfers. If it does not, the link is explicitly navigation rather than a search on the displayed package. |
| TF-21 | Small iPhone, largest supported text sizes, long team/player names, 3×3 trades, open keyboard and decline sheet. | Header, receipt, both sides, action labels, value meaning, and close/back controls remain legible and reachable; no reliance on color or glyphs alone. |
| TF-22 | Interrupt a pass-reason overlay before and after choosing a reason; navigate into More offers and back; repeat quickly. | Closing before a decision keeps the idea. Committed passes advance once. No duplicate pass, trapped overlay, or stale Undo promise. |

## Suggested implementation order

1. Fix request/draft continuity and source-aware pending/empty/retry behavior: UX-01 through UX-04 and UX-06. Validate the corresponding state transitions with focused tests, then TF-01 through TF-10.
2. Correct misleading commitments and destinations immediately: UX-05 and UX-11. These have small presentation changes with clear acceptance criteria.
3. Unify search settings, alternative-result context, and origin/back behavior: UX-07 through UX-10. Agree on the shared request and return contract before changing individual screens.
4. Consolidate labels, result-card presentation, and hierarchy: UX-12, followed by the device/accessibility pass. Keep dormant flag branches out of the normal product specification; validate any intended kill-switch behavior separately.

No mobile tests, typecheck, production requests, or manual device checks were run for this document-only review. Existing structural guards are useful implementation evidence, but they do not establish the cross-screen expectations evaluated here.
