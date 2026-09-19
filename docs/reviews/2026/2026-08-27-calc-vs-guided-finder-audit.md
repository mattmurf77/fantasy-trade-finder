# Feature-parity audit — the manual calculator vs. the guided trade finder

**Date:** 2026-08-27 · **Type:** audit only, no code or flags changed · **Tree:** `claude/new-feedback-71436e` at `6e94ff71` (the brief cited `origin/main` `30070f36`; this worktree is one commit ahead of it with a docs-only commit, and no file cited below differs)

**Question asked:** *"the manual calc has most, if not all features of the guided calc… I want to deprecate guided in favor of the singular, manual calc as the primary. Ensure we don't lose or miss any features before making the change."*

**Surfaces compared**

| Name used here | Code | Flag |
|---|---|---|
| **guided finder** | `mobile/src/screens/TradesScreen.tsx` (8,758 lines), route `TradesHome` with `initialParams {mode:'guided'}` | `trades.finder_hub` = **true** (`config/features.json:11`) |
| **manual calc (in-league)** | `mobile/src/components/InLeagueCalculator.tsx` (1,987 lines) | `calc.merged_layout` = **true** (`config/features.json:86`) |
| pushed calculator page | `mobile/src/screens/TradeCalculatorScreen.tsx` — hosts the manual calc in its `In league` tab and a league-free `Real values` mode | — |

---

## 1 · Bottom line up front

**The belief does not hold, and the plan as stated would break the manual calculator itself.**

In plain terms: the manual calculator is a **price-checker**, not a **trade-finder**. It is very good at the thing it does — you pick a leaguemate, drag assets onto two sides, and it tells you what the trade is worth on both boards. On that job it actually beats the guided page. But almost nothing that *finds* a trade for you lives in the calculator. The swipe deck, the pass-reason capture, the "keep this player and show me more offers" loop, the fairness and lane filters, the targeting board, the "they're interested" signal, the end-of-deck recovery paths — all of that is guided-page code and has no equivalent in the calculator.

The sharpest fact: **the calculator's own biggest button doesn't work without the guided page.** Tapping *Find a Trade* on the calculator does not render results in the calculator. It writes a hand-off and navigates to the guided deck — `TradeCalculatorScreen.tsx:868` calls `navigation.popTo('TradesHome')`, and `TradesScreen` is what turns the response into cards. Delete the guided page and the calculator's primary action has nowhere to land.

There is a second, more important thing to know. **Someone has already built this merge — and built it the other way round.** Flag `calc.inline_home` (`config/features.json:88`, shipping **dark**) makes the guided landing *host* the calculator inline, so build-a-trade and find-a-trade are one screen. Under that flag the calculator canvas moves onto the guided page, the *pushed* calculator page is trimmed to league-free `Real values` only, and the deck stays underneath as the results surface. That is the same "one surface" outcome you're after, arrived at by keeping the guided container and absorbing the calculator into it — rather than keeping the calculator container and deleting the deck. It is built, merged, and reversible with one config key. Its only blocker is the guided tour (details in §4), and that blocker is **real and unresolved** — Wave B, the tour rebuild, has not been built (`living-memory/NEXT.md:53`).

So the honest answer to "do we lose anything?" is:

- Judged as *"is the calculator missing features the guided page has?"* — **yes, a lot**: 24 capabilities are guided-only and 5 more are only partly present (§2, §3).
- Judged as *"can we get to one surface without losing anything?"* — **yes**, and the shortest path is not deprecating the guided page. It is lighting `calc.inline_home` after Wave B, which merges the two surfaces while keeping every guided capability mounted (§4).

My recommendation: **treat this as a hosting decision, not a deprecation.** Light `calc.inline_home` (after the tour work) so the calculator becomes the top of the guided page. Then decide separately, with real usage data, whether the swipe deck below it should shrink or go. That sequencing costs nothing and preserves an exit.

---

## 2 · Side-by-side feature table

Legend: **parity** = both surfaces do it · **calc only** · **guided only** · **partial** = present in both but materially reduced on one side.

Line numbers are from this tree. `IL` = `mobile/src/components/InLeagueCalculator.tsx`, `TS` = `mobile/src/screens/TradesScreen.tsx`, `TC` = `mobile/src/screens/TradeCalculatorScreen.tsx`.

### 2.1 Generating trades

| # | Capability | Guided finder | Manual calc (in-league) | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | Model deck generation (async job, streams cards) | Yes — `Find a Trade` button dispatches `generateMutation` through the single #330 choke point | No. The calc *asks* for one; it cannot render one | **guided only** | `TS:6453-6462` (button), `TS:6277` (`find_trades_tapped`), `IL:1096-1127` (calc hands off) |
| 2 | Search progress + partial results + Hide | Progress strip: `n/m opponents`, live card count, `Meter`, Hide | None | **guided only** | `TS:6467-6494` |
| 3 | Synchronous fairness sweep (`POST /api/trades/fair-packages`, D-153) | `runFairPackages` converts ideas → deck cards via `ideaToCard` | Triggers it, does not render it | **guided only (render); shared trigger** | `TS:2942-2986`; `backend/server.py:12236,12287` |
| 4 | The fair/model fork decision itself | Consumes the fork | Owns the canvas the fork reads | **parity (shared module)** | `mobile/src/utils/canvasSearch.ts:43-68`, both hosts call it |
| 5 | Auto-generate on first run (skeleton deck) | Yes, first-run pregen + `SkeletonTradeCard` | No | **guided only** | `TS:7113-7134`, `TS:472` (`autoGenRef`) |
| 6 | Scoped-to-one-team search | `scopedOpponent` from the full sheet feeds `generateMutation` | Team dropdown scopes the hand-off | **parity** | `TS:789-804`; `IL:1111-1117` (opponent rides along) |

### 2.2 Reviewing and acting on a trade

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 7 | Swipe-to-like / swipe-to-pass on a card stack | `SwipableTopCard` + peek card, `advance('like'/'pass')` | No card stack at all | **guided only** | `TS:6942-6987`, `TS:7061` ("Swipe right to like…") |
| 8 | Decline-reason capture (layer 1 tiles → layer 2 detail → free text) | Full two-layer flow, POSTs `postDeclineReason` | None | **guided only** | `TS:5044-5150`, flag `feedback.decline_reasons` (`TS:596`) |
| 9 | Pass reasons as an **overlay** (calculator-origin decks only) | Yes, when `deckOrigin==='calculator'` | n/a — the presentation is a property of the deck | **guided only** | `TS:5150` (`reasonsAsOverlay = calcMergedOn && deckOrigin === 'calculator'`) |
| 10 | Swipe undo (5s snapshot toast) | Yes (`ux.swipe_undo`) on passes | Yes, but only on **Clear trade** in the pushed page's Real-values mode | **partial** | `TS:560`; `TC:1090-1104` |
| 11 | "Keep · more offers" → pin a side and re-search | `handleKeepSide` pins the side, snapshots the deck (#288), regenerates | No | **guided only** | `TS:2880-2899`; `mobile/src/components/TradeCard.tsx:431-443` |
| 12 | Pin summary row (Edit / Clear) + snapshot restore on clear | Yes — `handleClearPin` restores the pre-pin deck when one was snapshotted | No | **guided only** | `TS:5840-5905`, `TS:2903-2929` |
| 13 | Featured-trade window (single-pin lead card) | Yes, with ‹ Previous history and edit-in-calculator | Renders *inside* the featured window as the editor | **guided only (the window)** | `TS:6607-6620`; `mobile/src/components/FeaturedTradeWindow.tsx:82` mounts `InLeagueCalculator` |
| 14 | Asset-ideas rail — **Upgrade / Lateral / Downgrade** (tier up/down) | `AssetIdeasPanel`, one instance, two mount points | No | **guided only** | `TS:5324-5344`, `TS:7386` |
| 15 | Per-asset swap suggestions (server-priced replacements) | Long-press → `SwapSuggestSheet` | No — but the calc has *eveners*, a different mechanism | **partial** | `TS:5281-5292`, `TS:7608`; calc equivalent `IL:1190-1215` |
| 16 | Swap a player manually inside a card | `SwapPlayerSheet` | Remove + re-add via picker | **partial** | `TS:7581`; `IL:1050-1070` |
| 17 | Remove one asset from the trade | On-card ✕ + long-press menu | ✕ on each `TradeSide` row | **parity** | `TS:5306-5315`; `IL:1046,1067` |
| 18 | Mark a player untouchable | Long-press menu, `untouchable_toggled` | Only via the DNA sheet's Manage layer, which the calc *can* open | **partial** | `TS:5265-5278`, `TS:1326`; `IL:1322` mounts `TradeDnaSheet` |
| 19 | Player context menu (long-press) | Yes (`ux.player_context_menu`) | No | **guided only** | `TS:7726-7732`, `TS:561` |
| 20 | "Bad trade?" engine-quality flag | Yes | No | **guided only** | `TS:7077-7090`, `TS:5176-5195` |
| 21 | Queue a card for "Send All" (dark) | Yes (`trades.queue_2k` = false) | Its ✓ is a *different* queue (`/api/trades/queue`, D-152) | **guided only (this one)** | `TS:6975-7016`, `TS:7421-7502` |

### 2.3 Pricing, verdicts and evidence — the calculator's home ground

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 22 | Two-board divergence verdict (your board vs. theirs, win–win detection) | Card-level meter + fit line only | Full `LeagueVerdict` — headline, `TradeValueBar`, both deltas | **calc only** | `IL:1454-1500+`; card side `mobile/src/components/TradeCard.tsx` |
| 23 | Partner ranked-status honesty (R / R\* / NR + conversion note) | No | Yes, with per-state copy | **calc only** | `IL:126-152`, `IL:812-822`, `IL:1000-1010` |
| 24 | Partner positional shape summary (QB/RB/WR/TE + picks, pick-equivalent labels) | No | Yes — but **only in the non-merged layout**; the merged team dropdown/sheet shows handle + R-badge only | **calc only, and degraded under `calc.merged_layout`** | `IL:934-982` (rich chips; the `!merged` branch opens at `IL:895`); merged sheet `IL:1349-1380` |
| 25 | Eveners / "Recommended to even it" / "Trade options" for a half-built trade | No | Yes | **calc only** | `IL:1189-1215` |
| 26 | Balance suggestions ("To balance — add from your roster") | No | Yes | **calc only** | `IL:1287-1305` |
| 27 | Lineup impact before/after + honest-empty row (`lineup_impact_unavailable`) | Card impact block only | Yes, full | **calc only** | `IL:1490-1510` |
| 28 | Scoring-format override chips (#166/#167) + #191 conversion note | Session format only, no in-page chips | Yes, both layouts | **calc only** | `IL:795-826`; merged variant `IL:794-822` |
| 29 | Draft picks as tradeable assets (owned-pick pool, ESPN honesty note) | Via `trade.picks_in_pool` in generated cards | Explicit pool + "Draft picks aren't available for ESPN leagues" | **parity (calc more explicit)** | `IL:1013-1015`, `IL:265-275` (`picksQ`) |
| 30 | Adjustments disclosure | No | Imported and rendered in the verdict | **calc only** | `IL:27` (`AdjustmentsDisclosure`) |
| 31 | League-free pricing with no account | No | Yes — but on the **pushed page's `Real values` mode**, not in-league | **neither, strictly** | `TC:70-77`, `TC:1000-1060` |

### 2.4 Conditions, filters and intent

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 32 | Outlook receipt + Change → DNA sheet | Yes, plus an always-available minimized "Outlook & filters" fallback row | Yes, plus its own `calc.outlook-fallback` twin | **parity** | `TS:5581-5650`; `IL:755-790` |
| 33 | **Full** edit sheet: fairness toggle, lane filter, targeting, intents, team+league targeting | Yes — `TradeDnaSheet` mounted **with `full={…}`** | **No** — mounts `TradeDnaSheet` with no `full` prop, so the sheet renders outlook/chasing/shopping/untouchables only | **guided only** | `TS:5380-5427` (full block) vs. `IL:1320-1326` (bare mount); prop contract `mobile/src/components/TradeDnaSheet.tsx:221-233` |
| 34 | Trade fairness toggle + "How trades are priced" help sheet | Yes | No | **guided only** | `TS:5941-5990`, `TS:7735-7748` |
| 35 | Lane filter pills (Team-fit moves / Value moves) | Yes, when the deck carries lanes | No | **guided only** | `TS:6005-6037`, `TS:3189-3197` |
| 36 | Player targeting board (TRADE AWAY / TRADE FOR columns) | Yes | The canvas *is* an anchor, but it is not a persistent target list and writes no pins (D-153) | **partial** | `TS:6047-6150`; `TC:848-856` (comment: "the canvas no longer touches the PIN STORE at all") |
| 37 | "Trade as one package" toggle | Yes | No | **guided only** | `TS:6146`, `TS:7802-7830` |
| 38 | Trade intent modes chip row (#172) | Yes, in the full sheet | No | **guided only** | `TS:5411-5413`, `TS:649` |
| 39 | Avoid-positions (#360/#361) | Row gated in the DNA sheet — reachable from both | Reachable (same sheet) | **parity** | `TS:657`; `IL:1322` |
| 40 | "Preferences changed — refresh" nudge strip | Yes | No | **guided only** | `TS:5661-5680`, `TS:844-858` |
| 41 | League switcher | Global TopBar + sheet from the full sheet | Own `LeagueSwitcherSheet` from the League dropdown | **parity** | `TS:5575`; `IL:826-843`, `IL:1328` |
| 42 | Team picker | Modal from mode bar / sheet | Own team sheet from the Team dropdown | **parity** | `TS:7509-7568`; `IL:1332-1385` |

### 2.5 Social / cross-user signals

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 43 | **"They're interested"** likes-you pill on a card | Yes | No — a hand-built trade carries no such marker | **guided only** | `mobile/src/components/TradeCard.tsx:503-507` |
| 44 | Likes-you cards **pinned to the top of the deck** | Yes (when fairness sort is off) | No deck to sort | **guided only** | `TS:3189-3197` |
| 45 | Standing-offer prompt after a like (#362) | Yes — `StandingOfferSheet` with real seasons/members | No | **guided only** | `TS:7680-7722`, `TS:663-666` |
| 46 | Liked-count line ("N liked trades awaiting their swipe") | Yes | No | **guided only** | `TS:6496-6500` |
| 47 | Queue a hand-built package for a leaguemate (`POST /api/trades/queue`, D-152) | No | Yes — the ✓ cell | **calc only** | `IL:1157-1186`; `TC:817-826`; `backend/server.py:13027` |
| 48 | New-partners alert banner / invite-leaguemates banner / identity-confirm strip | Yes | No | **guided only** | `TS:5702-5735` |

### 2.6 Sending and sharing

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 49 | Send in Sleeper / ESPN / MFL (platform-matched) | Yes, on the top card | Yes, above the verdict | **parity** | `TS:7034-7059`; `IL:1247-1268` |
| 50 | Share trade as image (PNG + text fallback, pick-asset guard) | Share the last **liked** trade (`onboarding.share_sheet`, dark) | Yes, always, both calc modes | **partial (calc stronger)** | `TS:7096-7110`; `IL:1290-1315`; `TC:1035-1060` |

### 2.7 End states, empty states, degraded states

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 51 | Deck-done summary (passed/liked/proposed tally, weekly-refresh copy) | Yes | n/a | **guided only** | `TS:7150-7248` |
| 52 | End-of-deck exit: **Back to calculator** | Yes | n/a | **guided only** | `TS:7181-7189`, handler `TS:2996-3026` |
| 53 | End-of-deck exit: **Search without the pinned players** | Yes | n/a | **guided only** | `TS:7197-7205`, `TS:3028-3042` |
| 54 | End-of-deck exit: **Search all trades** (fair decks) | Yes | n/a | **guided only** | `TS:7214-7221`, `TS:3050-3057` |
| 55 | "That's all for now" exhausted card (+ trio ramp under `onboarding.rank_routing`) | Yes | n/a | **guided only** | `TS:7250-7322` |
| 56 | Search-failed card with Try again (network/timeout-specific copy) | Yes | Calc shows a generic evaluate spinner only; no search-failure card | **guided only** | `TS:7324-7340`, `TS:337-364` |
| 57 | Scoped-empty card ("even after stretching the fairness band") + back to league rankings | Yes | No | **guided only** | `TS:7345-7364` |
| 58 | Never-searched empty state ("Hit *Find a Trade* to start") | Yes | Calc's own empties are "Loading your league…" / "No leaguemates found" | **partial** | `TS:7366-7375`; `IL:706-722` |
| 59 | Decline-suppression note + Undo (`deck.fatigue`) | Yes | No | **guided only** | `TS:6802-6840`, `TS:3060-3080` |
| 60 | Board-refresh note / redraft "Dynasty values shown" label | Yes | Only the ESPN-picks note | **guided only** | `TS:6706-6790`; `IL:1013` |
| 61 | Single-format gate (`FormatGate`) | Yes | Format chips instead | **partial** | `TS:5813` |
| 62 | League-switch blocking overlay | Yes | No (component-level query reload) | **guided only** | `TS:5438-5447` |

### 2.8 Onboarding, coaching and the guided tour

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 63 | Tour beats **n19–n24** (pass control, swap, package toggle, card meter, send, sign-off) target guided-page nodes | Yes — `trades.pass-btn`, `trades.swap-first`, `trades.package-toggle`, `trades.card-meter`, `trades.send-btn` | n/a | **guided only** | `mobile/src/components/analystScript.ts:550,564,574,598,633,644,658` |
| 64 | Tour beats **n10–n18** target calculator nodes | Deck half only | Yes — `calc.mode-tab.league`, `calc.outlook-row`, `calc.trade-columns`, `calc.action.*`, `calc.league-give-add` | **calc only** | `analystScript.ts:456,469,484,494,504,525,535`; registrations `IL:206-226`, `TC:135-140` |
| 65 | Onboarding spine beats `s2.*`, `n1`, `n2a/b`, `n4`, `n6.1` target the guided page | Yes | n/a | **guided only** | `analystScript.ts:167,173,186,196,289,302,320,334,359` |
| 66 | "Show me around" tour re-entry | No | Yes (top-right of the merged calc) | **calc only** | `IL:735-751`; `TC:790-800` |
| 67 | Coach marks — swipe hint, provenance chip | Yes | No | **guided only** | `TS:3444-3470`, `TS:6766-6779` |
| 68 | Quick-Set prompt card in the deck slot | Yes | No | **guided only** | `TS:6884-6890`, `TS:3755-3790` |
| 69 | Adaptation moment ("Noticed you're liking…") | Yes | No | **guided only** | `TS:6890-6920` |
| 70 | Apple save-moment sheet + session-2 banner | Yes | No | **guided only** | `TS:6738-6762`, `TS:7671-7676` |
| 71 | Provenance chip ("where these prices come from") | Yes | No | **guided only** | `TS:6711-6724` |
| 72 | Demo bridge link | Yes (`onboarding.demo_bridge`, dark) | Removed from the calc in #384 | **guided only** | `TS:6683-6702`; `TC:76-80` |

### 2.9 Navigation and adjacent surfaces reached from the page

| # | Capability | Guided | Calc | Verdict | Evidence |
|---|---|---|---|---|---|
| 73 | Utility row: Free agents · Manual calc · Draft · Today's trade · Track record | Yes (inline-home variants) / `TradeFinderModeBar` otherwise | **Explicitly none** — operator ruling 6 on #384 | **guided only** | `TS:5506-5532`, `TS:5535-5575`; ruling `docs/feedback/items/384-calc-finder-merge/status.md` (ruling 6) |
| 74 | Subnav pills Trades / Portfolio / Calculator | Yes (classic, non-finder-mode) | **None** — operator ruling 7 | **guided only** | `TS:5773-5804` |
| 75 | Explore → Free agents row | Yes | No | **guided only** | `TS:7393-7412` |
| 76 | Team Review entry card | Yes (`trades.team_review`) | No | **guided only** | `TS:5745-5758` |
| 77 | Retap-active-tab → scroll to top | Yes (`ux.retap_active_tab`) | Inherits the host page's | **guided only** | `TS:623-640` |

---

## 3 · Guided-only capabilities — the deprecation risk list

Counting distinct **guided only** rows above: **24 clusters.** (Rows 1/2/5 collapse to one "deck generation and its progress"; 51–55 collapse to "end-of-deck"; 63/65/67–72 collapse to "onboarding + tour"; 43–46 collapse to "likes-you".) The five **partial** rows follow.

Each entry: what is lost · who it affects · cheapest preservation.

**G1 · The deck itself — model generation, progress, streaming cards** (`TS:6453`, `TS:6467`, `TS:2942`)
Lost: every path to a *suggested* trade. Affects: 100% of users, including the calculator's own users, because `Find a Trade` renders here.
Cheapest preservation: **do not remove it.** The calculator cannot host results without re-implementing card render, disposition, swipe, flag, queue and edit paths — the entire `TS` render tree from `:6860` to `:7380`. If the goal is one screen, `calc.inline_home` already does this by moving the *calculator* onto the deck page instead.

**G2 · Swipe-to-like / swipe-to-pass** (`TS:6942`, `TS:7061`)
Lost: the disposition signal that trains the engine and creates mutual matches. Affects: every user; also the ranking model, since `trade_card_viewed` and swipe outcomes are the deck's learning loop (`TS:565` `deck.signal_v2`, `TS:583` `deck.session_rerank`).
Preservation: same as G1 — this only exists on cards, and cards only exist in a deck.

**G3 · Decline-reason capture, two layers plus free text** (`TS:5044-5150`)
Lost: the only structured "why not" the product collects. Affects: product/analytics more than users.
Preservation: none cheap. It is bound to a card's pass. Note the irony: the **overlay** presentation of this flow was built specifically *for* calculator-origin decks (`TS:5150`) — deprecating guided deletes a feature that exists to serve the calculator.

**G4 · "Keep · more offers" pin loop + pin summary + snapshot restore** (`TS:2880`, `TS:2903`, `TS:5840`, `TradeCard.tsx:443`)
Lost: the one-tap "I like this player, show me other trades for him" motion, and the #288 undo that restores the original deck.
Preservation: the calculator's canvas is a *weaker* substitute — it anchors a search but stores no pins (`TC:848`), so there is no pin summary, no restore, and no `trade_pin_cleared`. Preserving it means porting `useFinderTargets` into the calculator, which is real work, not a copy.

**G5 · Featured-trade window + Upgrade/Lateral/Downgrade asset ideas** (`TS:5324`, `TS:6607`)
Lost: the tier up/down comparison rail — the closest thing the app has to a competitor-style "who's worth about this much".
Affects: users with one pinned asset; this is the #216/#298 single-pin surface.
Preservation: `AssetIdeasPanel` is prop-driven and could be mounted under the calculator canvas. **This is the cheapest real port on the list** — one component, data from `assetIdeasQuery`. Worth doing regardless of the merge decision.

**G6 · The full edit sheet — fairness, lanes, targeting, intents, team/league targeting** (`TS:5380-5427` vs. `IL:1320`)
Lost: *all* trade conditions. The calculator mounts the same sheet without the `full` prop (`TradeDnaSheet.tsx:226`), so from the calculator a user can set outlook/chasing/shopping/untouchables and nothing else.
Affects: anyone who wants to constrain the search.
Preservation: **cheap and high-value — pass `full={…}` from the calculator's host.** The sheet already supports it. The wiring is real (the props are all `TradesScreen` state today), but this is the single highest-leverage gap to close and it should be closed *before* any deprecation, not as part of one.

**G7 · Fairness toggle + "How trades are priced" help** (`TS:5941`, `TS:7735`)
Lost: the user's control over how strict the engine is, and the only in-app explanation of pricing.
Preservation: rides on G6 for the toggle; the `HelpSheet` mount is a two-line addition.

**G8 · Lane filter (Team-fit / Value)** (`TS:6005`)
Lost: post-hoc filtering of a deck. Only meaningful with a deck (G1).

**G9 · "Trade as one package" toggle** (`TS:6146`, `TS:7802`)
Lost: the multi-asset packaging instruction to the engine. Rides on G6.

**G10 · Trade intent modes** (`TS:5411`) — same, rides on G6.

**G11 · Likes-you: the pill, the deck pinning, the liked-count line** (`TradeCard.tsx:503`, `TS:3192`, `TS:6496`)
Lost: the mutual-interest signal — arguably the product's differentiator.
Affects: every user in a league with ≥1 other active user.
Preservation: the *pill* could render on a calculator verdict if the backend echoed `likes_you` for a hand-built package — but the **pinning** (surfacing the interested trade unprompted) has no analogue in a surface where the user chooses the players. This is a genuine capability loss with no cheap fix.

**G12 · Standing-offer prompt after a like** (`TS:7680`)
Lost: the #362 post-like conversion moment, which fires off a swipe.
Preservation: could be triggered from the calculator's ✓ queue instead. Moderate work; the sheet is prop-driven.

**G13 · Player context menu (long-press) + swap suggestions + untouchable toggle from a card** (`TS:5260-5320`, `TS:7608`, `TS:7726`)
Lost: three actions collapse to the calculator's remove+re-add. Swap suggestions in particular are server-priced replacements — the calculator's eveners are a different question ("what closes the gap") than "what replaces this player at the same price".
Preservation: `SwapSuggestSheet` is prop-driven and could hang off a calculator row's long-press. Moderate.

**G14 · "Bad trade?" quality flag** (`TS:7077`)
Lost: the operator-review channel for engine mistakes. Affects: the operator.
Preservation: n/a on a hand-built trade — the user built it, so there is nothing to flag. **Argue this should not be preserved.**

**G15 · Trade queue / Send All (`trades.queue_2k`, dark)** (`TS:6975`, `TS:7421`)
Lost: a dark feature. **Argue this should not be preserved** — decide its fate independently.

**G16 · The five end-of-deck states and their exits** (`TS:7150`, `TS:7250`, `TS:7324`, `TS:7345`, `TS:7366`)
Lost: including two exits built *for the calculator* — "Back to calculator" (`TS:7181`) and "Search without the pinned players" (`TS:7197`) — plus the fair deck's "Search all trades" (`TS:7214`). Also lost: the search-failed card (`TS:7324`), which is the **only** place the app says a search failed, and the scoped-empty card (`TS:7345`) with its honest "even after stretching the fairness band" copy.
Preservation: if the deck goes, these go with it. If the deck stays but is hosted differently, they survive verbatim — which is exactly what `calc.inline_home` does (and it already re-homes the fair deck's exit into the anchor receipt's Clear, `TS:6575-6588`).

**G17 · Decline-suppression note + Undo** (`TS:6802`, `TS:3060`) — deck-bound, no cheap port.

**G18 · Board-refresh note, redraft label, invite/new-partner/identity strips** (`TS:5702-5735`, `TS:6706-6790`) — informational banners; each is a small port if wanted, but they read as deck chrome.

**G19 · Onboarding spine beats on the Trades screen** (`analystScript.ts:167-196,289-380`)
Lost: `s2.wait`, `s2.1`, `s2.2`, `n1`, `n2a/b`, `n4`, `n6.1` all declare `screen: 'Trades'`. A new user's first ten seconds are scripted against this surface.
Preservation: these must be re-targeted, not deleted. This is precisely the work Wave B was scoped to do — see §4.

**G20 · Tour beats n19–n24** (`analystScript.ts:550-660`) — the deck half of the #384 calculator tour. Targets `trades.pass-btn`, `trades.swap-first`, `trades.package-toggle`, `trades.card-meter`, `trades.send-btn`. All five nodes are guided-only. **Deprecating guided breaks the calculator's own tour at its halfway point.**

**G21 · Coach marks (swipe hint, provenance)** (`TS:3444`, `TS:6766`) — deck-bound teaching.

**G22 · Quick-Set prompt card + adaptation moment + Apple save moment/banner** (`TS:6884`, `TS:6890`, `TS:6738`, `TS:7671`)
Lost: three separate conversion/activation moments that fire off deck behaviour (swipe counts, first like).
Preservation: each would need a new trigger. The Apple save moment in particular is the account-creation ask — **this is a revenue-adjacent loss**, not a cosmetic one.

**G23 · Utility row + subnav + Explore/Free agents + Team Review entry** (`TS:5506`, `TS:5773`, `TS:7393`, `TS:5745`)
Lost: the navigation hub. Note the calculator has **none of these by operator ruling** on #384 (rulings 6 and 7, `docs/feedback/items/384-calc-finder-merge/status.md`) — the calculator was deliberately built *without* navigation because it was a pushed sub-page. Making it the primary surface reverses that ruling and requires re-adding a nav row.

**G24 · Progress/loading affordances: skeleton first-run deck, running-job placeholder, league-switch overlay, format gate** (`TS:7113`, `TS:7136`, `TS:5438`, `TS:5813`)
Lost: honest loading states for slow (Render free-tier) paths.

### The five `partial` rows, briefly

| Row | Gap if the calculator becomes primary |
|---|---|
| 10 — swipe undo | Undo exists only on `Clear trade` in the pushed Real-values mode (`TC:1090`); the merged calc's `Clear` (`IL:1128-1146` → `clear()` at `IL:698-704`) has **no undo**. Destructive, one tap, unrecoverable. Worth fixing on its own. |
| 15/16 — swaps | Eveners answer "what closes the gap"; swap suggestions answer "what replaces this asset". Losing the latter loses a distinct question. |
| 18 — untouchables | Still reachable via the DNA sheet's Manage layer, but not from the asset itself. |
| 24 — partner shape summary | Already regressed: the rich per-partner QB/RB/WR/TE + picks chips render only in the `!merged` branch (`IL:895`, chips at `IL:934-982`). The merged Team dropdown and team sheet show handle + R-badge only (`IL:1349-1380`). **This is a live, shipped regression today**, independent of the merge question. |
| 36 — targeting | The canvas anchors one search; it is not a persistent pin store (`TC:848`). |
| 58 — empty states | The calculator has no "no results" state because it never produces results. |

---

## 4 · What the dark `calc.inline_home` work already gives you

**Read `config/features.json:87` in full — it is the spec.** Summary, verified against code:

| Piece | Where it is built | Verified |
|---|---|---|
| The guided landing mounts the calculator canvas as its layout | `TS:6525-6552` (`canvasHost === 'flag'`), `mobile/src/components/TradeBuildCanvas.tsx:147` | ✅ mounts `InLeagueCalculator` verbatim |
| Precedence over the #270 experiment so the canvas mounts once | `TS:5152-5167` (`canvasHost` resolves `'flag' | 'experiment' | null`) | ✅ |
| Find a Trade runs **in place** — no navigation, no handoff | `handleInlineFindATrade` → `forkCanvasSearch` → `canvasRunSeq` bump into the one #330 choke point (`TS:754-772` comments, `TS:100` import) | ✅ |
| Anchored deck shows a filter receipt "Built around X · Change / Clear" | `TS:6554-6592`, `inlineAnchorShown` at `TS:5170` | ✅ |
| Deck's three edit-in-calculator hand-offs load the inline canvas instead of pushing | `TS:3082-3105` (`handleEditInCalculator`), `TS:3007-3016` (`handleBackToCalculator`), `TS:668-680` (`canvasPrefill` from `MatchesScreen`) | ✅ |
| Pushed `TradeCalculatorScreen` trims to `Real values` only; mode chip relabels | `TC:126-136`, `TC:190-196` | ✅ |
| No new events, no schema change, no route change | `canvasSearch.ts:24-26`, `utils/queueCalcTrade.ts` shared by both hosts | ✅ |
| Kill switch is this one key, config-only | `TS:697` single `useFlag('calc.inline_home')` read | ✅ |

**Direction, stated plainly.** `calc.inline_home` merges the two surfaces by **keeping the guided page as the container and pulling the calculator into it**. The operator's proposal is the mirror: **keep the calculator as the container and delete the guided page**. Both end at "one surface where you build a trade and find a trade". They differ in what survives underneath:

| | `calc.inline_home` (built, dark) | Operator's stated direction |
|---|---|---|
| Host screen | `TradesHome` (guided) | The calculator |
| Calculator canvas | Top of the page, inline | The page |
| Swipe deck | **Stays**, below the canvas, as the results surface | Removed (implied by "deprecate guided") |
| The 24 guided-only capabilities | **All preserved** — they are still mounted on the same screen | 24 losses to adjudicate (§3) |
| Pushed calculator page | Survives as league-free `Real values` (#310) | Becomes the primary |
| Reversibility | One config key, no deploy | A build |

**Verdict: `calc.inline_home` is a step toward the goal, not a conflicting design — and it is a *more complete* answer than the stated plan.** It delivers the user-visible outcome ("build and find are one surface") while leaving every guided capability mounted, and it is reversible without a build. The stated plan reaches a smaller surface at the cost of 24 capabilities and a broken tour.

**The blocker is real and unresolved.** The flag's comment says the tour is disabled under it because beat n10 targets `calc.mode-tab.league`, a node the flag deletes (`TC:135-140` registers it; `analystScript.ts:456-457` targets it). Verified in code: `TC:790-800` suppresses the "Show me around" re-entry when `inlineHomeOn`, and the inline canvas mount (`TS:6530-6544`) deliberately passes no `onShowMeAround` — stated verbatim in the comment at `TS:6518-6522`.

**Did Wave B happen? No.** `living-memory/NEXT.md:52-55`: *"Wave A / Wave B0 SHIPPED 2026-08-24 (PRs #197/#199, EAS 1.16.4 build 130; B0 dark behind `calc.inline_home`). **Next build: Wave B, the tour merge** — required BEFORE the flag lights."* `git log` confirms `14a4ce47` (Wave B0) and `74526509` (Wave A) landed on 2026-08-24 and nothing since touches the tour merge. `onboarding.guide_v2` is `true` (`config/features.json:116`), so the tour **is** running for all users today — meaning lighting `calc.inline_home` now would visibly break a live tour, not a dark one.

Also note `TS:5594` and the `TradesScreen` CLAUDE.md both mark the "Outlook & filters" fallback row as **deliberately mortal** — it is scheduled to retire when `calc.inline_home` lights and the anchor receipt takes over. So the dark work already carries a small planned deletion of its own.

---

## 5 · Decisions needed from the operator

**D1 — Which direction is the merge?**
This is the fork everything else hangs off.
- (a) **Light `calc.inline_home` after Wave B.** The guided page hosts the calculator; the deck stays as the results surface. Zero capability loss, one config key to revert.
- (b) **Deprecate the guided page and make the calculator primary.** Requires adjudicating all 24 guided-only clusters, re-homing the deck or deleting it, re-adding navigation the calculator was deliberately built without (#384 rulings 6/7), and rewriting both tours.
- (c) Something in between — calculator primary, deck retained as a secondary "Suggestions" tab.

**Recommendation: (a).** It reaches your stated user outcome ("one surface, build or find"), it is already built and merged, and it is the only option with a no-deploy revert. If after living with (a) the deck feels vestigial, deleting it later is a strictly smaller decision than deleting it now — and you will have usage data for it. My read of your ask is that you want *one surface*, not specifically *the calculator's container* — (a) gives you the first.

**D2 — Does Wave B (the tour rebuild) get built before anything lights?**
`onboarding.guide_v2` is live for everyone, so both tours are running in production today. Under `calc.inline_home` the calculator half (n10–n18) has no host and is suppressed.
- (a) Build Wave B first — re-target n10–n18 at the inline module, re-thread the park signals (`calcTourInLeagueReady` / `onOutlookClosed`, `TC:801-812`), then light.
- (b) Light now and accept a tour-free calculator until Wave B.
- (c) Turn `onboarding.guide_v2` off, light `calc.inline_home`, rebuild both tours together.

**Recommendation: (a).** The flag comment's own instruction, and the cheapest. (b) ships a regression to new users, who are exactly the population the tour exists for.

**D3 — Do trade *conditions* move to the calculator regardless of D1?**
Today the calculator's outlook sheet has no fairness toggle, no lanes, no targeting, no intents (`IL:1320` vs. `TS:5380`). Under D1(a) this resolves itself (the host still owns the full sheet). Under D1(b) or (c) it must be built.
- (a) Pass `full={…}` from whichever host owns the canvas — small, and closes G6/G7/G9/G10 at once.
- (b) Leave the calculator conditions-light on purpose (it is a price-checker; conditions belong to search).

**Recommendation: (a) if the calculator ever becomes primary; (b) is defensible only under D1(a),** where the guided host still carries them.

**D4 — Does the likes-you signal survive a calculator-primary world?** (G11)
There is no mechanism for "a trade someone else is interested in" to reach a user who builds every trade by hand. Options: keep the deck as the delivery vehicle (D1(a)/(c)); or move likes-you delivery entirely to Matches and accept it never appears on the trade surface; or build a new "offers for you" strip on the calculator.

**Recommendation: keep the deck.** This is the differentiator; a strip is a worse version of the deck.

**D5 — The three activation moments that fire off deck behaviour** (Apple save-moment, Quick-Set prompt, adaptation moment; G22).
Under D1(b) each needs a new trigger, or is lost. The Apple save-moment is the account-creation ask.
- (a) Re-trigger them off calculator events (`calc_asset_added`, `calc_trade_queued`).
- (b) Accept the loss.

**Recommendation: (a) if D1(b) wins — and treat it as a launch blocker, not a follow-up.**

**D6 — Fix the shipped partner-shape regression now, independent of the merge?** (row 24)
The QB/RB/WR/TE + picks partner summary renders only in the pre-#384 layout (`IL:895`, chips `IL:934-982`). Under `calc.merged_layout` (live today) users see handle + R-badge only.
- (a) Port the summary line into the merged Team dropdown/sheet.
- (b) Leave it — the operator chose dropdowns over chips deliberately in #333.

**Recommendation: (a).** #306 built those pick-equivalent labels specifically so partner shape was legible at the moment of choosing a partner; the merged layout dropped the payload, not the decision. Small fix.

**D7 — Does the merged calculator's `Clear` get an undo?** (row 10)
`IL:1128-1146` clears both sides with one tap, no snapshot, no toast. The Real-values mode has one (`TC:1090`). D-157 already relabelled ✕ → **Clear** because a tester destroyed his canvas mid-tour.
- (a) Reuse the `ux.swipe_undo` snapshot pattern.
- (b) Leave it.

**Recommendation: (a).** The relabel treated the misread; the destructiveness is untreated.

---

## 6 · Open questions

| # | Question | Why I could not resolve it | Evidence that would settle it |
|---|---|---|---|
| Q1 | Does anyone actually use the pushed calculator's `Real values` (league-free) mode? | It is the #310 promise and the flag comment protects it, but usage is a data question. | `screen_viewed{screen:'TradeCalculator'}` split by `calc_mode_switched.mode` (`analytics_taxonomy.py:1475`) over the last 30 days. |
| Q2 | How often does a user reach the deck **from** the calculator vs. tapping Find a Trade on the guided page? | Both emit `find_trades_tapped`; only the calculator path carries `source:'calculator'` (`TS:2951`), and `calc_find_a_trade_tapped` carries the fork (`canvasSearch.ts:52`). | Ratio of `calc_find_a_trade_tapped` to `find_trades_tapped{source: null}`, plus the `path` split (fair vs. model). |
| Q3 | Is the `trades_home_inline` experiment (#270) still assigning units, and would lighting `calc.inline_home` change what its assigned users see? | The code resolves precedence (`TS:5152`), but I did not verify the experiment's live assignment state. | The experiment's row in the experiments table / `docs/feedback/items/270-inline-trades-home/status.md` current status. |
| Q4 | Has the Wave B0 TestFlight checklist ever been run? | `docs/plans/onboarding-tour-merge/scope-wave-b0.md:192` says written and **unrun**; I found no later ledger entry. | `living-memory/TEST_LEDGER.md` grep for "Wave B0" / build 130+. |
| Q5 | Would `POST /api/trades/fair-packages` returning zero ideas produce a usable empty state under `calc.inline_home`? | `runFairPackages` sets the deck to `[]` on success with no ideas (`TS:2976`) and does **not** set `scopedEmpty`, so the page falls through to the "Hit *Find a Trade* to start" card (`TS:7366`) — which would be wrong copy after a search that ran. I could not confirm the server never returns an empty `ideas` array. | A `fair-packages` response with `ideas: []` from a real league, or a read of `backend/server.py:12287-12400`'s zero-result branch. Flagged as a **likely latent bug** either way. |
| Q6 | Do the guided-only banners (invite, new-partners, identity-confirm) earn their place, or are they dead weight? | Pure product judgement; several sit behind dark flags. | Impression counts per banner. |

**UNVERIFIED claims I am flagging rather than asserting:**
- I did not run the app. Every behavioural statement above is a code read. `screens/` captures are frozen at 2026-08-11 (per repo `CLAUDE.md`) and predate `calc.merged_layout` shipping on 2026-08-22, so they cannot be used as current truth and I did not use them.
- I did not verify Q5's zero-result path against a live server.
- Whether `trades.queue_2k`'s Send-All is intended to ship at all is unknown to me.

---

## 7 · Design alignment needed

Chalkline rules that constrain the answers: `docs/design/design-system.md:11-24` (prohibitions), `:50-67` (ice = actions, flare = information — *"flare never appears on a button"*), `:144-155` (44pt hit targets, 4.5:1 text contrast, ≥3:1 interactive boundaries), and `docs/design/components.md:141-145` (the OutlookBiasReceipt two-row spec and the deck-done rules).

| # | Where the two surfaces disagree | What the merged surface should do | Constrained by | Needs your taste? |
|---|---|---|---|---|
| 1 | **Filter/condition entry point.** Guided has the minimized "Outlook & filters" row (`TS:5607-5650`) *and* a Change link on the receipt; calc has its own `calc.outlook-fallback` twin (`IL:766-790`). Both render if both mount. | One receipt wrapper, one Change link. The `TradesScreen` CLAUDE.md already marks its fallback row **mortal** on `calc.inline_home` — honour that and let the calc's row be the survivor. | `components.md:141` — ≤2 rows, team/players never in row 2. | No — rule decides. |
| 2 | **The anchor receipt vs. the end-of-deck exits.** `TS:7214` and `TS:7308` already step aside for `inlineAnchorShown`. | Keep exactly one "drop the anchor" control: the receipt's **Clear**. | One destructive action, one control (the same principle `IL:1310` cites for Clear). | No. |
| 3 | **Two "Find a Trade" buttons on one screen.** The calc's action-row primary (`IL:1096`) and the guided page's `trades.find-btn` (`TS:6453`) would both be ice-filled primaries in one frame. | One primary. Under `calc.inline_home` the canvas button should be it; the page-level button either disappears or demotes to secondary ("Find more trades" already relabels at `TS:6456`). | `design-system.md:50-57` — ice is **rationed**; two ice fills in one viewport spends the budget twice. | **Yes** — whether the page-level button demotes or disappears is a judgement about how a user re-searches without touching the canvas. |
| 4 | **Action-row proportions.** D-157 set Find a Trade 50 / Clear 30 / ✓ 20 (`IL:1080-1094` comment). The flag comment at `config/features.json:87` still describes the older 70/15/15 split. | The code is right; the flag comment is stale. Ship 50/30/20 and correct the comment when the flag next changes. | 44pt floor; 11pt label floor (`IL:1090` note). | No. |
| 5 | **Pass control iconography.** The deck's ✕ (pass) and the calc's `Clear` sat adjacent enough that a tester conflated them (D-157, `docs/plans/onboarding-tour-merge/plan.md` v2 note 15). On one merged screen they are genuinely adjacent. | Keep the calc's `Clear` **labelled**; keep the deck's pass control icon-only inside the card. Never place them in the same horizontal band. | `design-system.md:1` — no emoji; Chalkline icon set only. | **Yes** — vertical separation is a layout call. |
| 6 | **Chip label vocabulary.** Guided: "Team-fit moves / Value moves" (`TS:6011`, deliberately not the engine's `window`/`value`). Calc: "1QB PPR / SF TEP" format chips (`IL:794-820`). Two chip rows, two vocabularies, potentially stacked. | Group them: format chips belong with the canvas header; lane pills belong with the results. Never one undifferentiated chip wall. | `components.md:23-39` (badges & chips); `docs/cross-client-invariants.md` owns the `window`/`value` enum — display labels may differ, the enum may not. | No. |
| 7 | **Empty states.** Guided has five distinct ones (`TS:7150/7250/7324/7345/7366`); calc has two ("Loading your league…", "No leaguemates found", `IL:706-722`). A merged page must not show "Hit *Find a Trade* to start" beneath a canvas the user has already filled. | Pick the state from what actually happened: canvas-filled + no search → prompt to search; search ran + zero results → the honest zero copy; search failed → the failure card. See Q5 — the zero-result fair path currently lands on the wrong card. | `components.md:104-113` (feedback & status). | No — but Q5 needs fixing. |
| 8 | **"Show me around" placement.** Calc renders it top-right (`IL:733-751`); the guided page has no equivalent. Under `calc.inline_home` it is deliberately not passed (`TS:6530-6544`, comment `TS:6518-6522`). | Wave B decides. Whatever it becomes, it is a text link in `chalk.dim`, not an ice button — it is not the page's primary action. | `design-system.md:50` — ice rationed to primary CTAs. | **Yes** — whether the re-entry lives on the page or in a menu. |
| 9 | **Vertical order on the merged page.** Today's inline order is: utility row → outlook receipt → strips/banners → canvas → anchor receipt → featured window → deck (`TS:5497-6870`). That is a lot above the fold before the user sees a trade. | Decide the first screenful deliberately. My read: canvas + action row must fit one frame together — that was the #384 report's explicit ask, and `IL:1078` cites it. | `design-system.md:111-115` (spacing scale). | **Yes** — this is the taste call that most determines whether the merge feels like one surface or two stacked ones. |
| 10 | **Flare usage.** The likes-you pill is flare (`TradeCard.tsx:1030-1041`) and the anchor receipt uses a flare tick (`TS:6558`). Both on one screen is fine; a flare *button* would not be. | Keep flare informational only, wherever these land. | `design-system.md:58-66` — explicit. | No. |

---

## 8 · Analytics and flag impact

### 8.1 Events that would stop firing or change meaning

Under **D1(b)** (deprecate the guided page). Registration lines are `backend/analytics_taxonomy.py`.

**Would stop firing entirely** — every one is emitted only from `TradesScreen.tsx`:

| Event | Class | Emitter |
|---|---|---|
| `trade_card_viewed` | **INTENT** (`:51`) | `TS:3374` |
| `find_trades_tapped` (both `source` values) | **INTENT** (`:51`) | `TS:1033`, `TS:2951`, `TS:6277` |
| `trade_flagged` | **INTENT** (`:51`) | `TS:5182` |
| `trade_keep_side_tapped`, `trade_pin_cleared` | INTENT | `TS:2896`, `TS:2928` |
| `deck_back_to_calculator`, `deck_unpin_retry`, `deck_search_all_tapped` | INTENT (`:633`) | `TS:3002`, `TS:3032`, `TS:3055` |
| `trade_pass_layer1`, `trade_pass_layer2` | INTENT | `TS:5048`, `TS:5063`, `TS:5085` |
| `trade_pass_overlay_opened`, `trade_pass_overlay_dismissed` | **NON_INTENT** (`:652`) | `TS:5129`, `TS:5133` |
| `deck_exhausted_viewed`, `deck_summary_viewed` | NON_INTENT | `TS:4095`, `TS:4126` |
| `coach_mark_shown` / `_dismissed` | NON_INTENT | `TS:3444-3470`, `TS:4039` |
| `quickset_prompt_shown` / `_accepted` / `_snoozed` | mixed | `TS:3755`, `TS:3898`, `TS:3780` |
| `apple_prompt_shown` / `_accepted` / `_declined`, `apple_banner_dismissed` | mixed | `TS:4209`, `TS:4332`, `TS:4336`, `TS:4349` |
| `celebration_shown` | NON_INTENT | `TS:3977`, `TS:4264` |
| `standing_offer_skipped` | — | `TS:3893` |
| `suppression_undo_tapped` | NON_INTENT (`:339`) | `TS:3068` |
| `trade_swap_suggest_opened`, `trade_asset_removed` | — | `TS:4585`, `TS:4606` |
| `trade_edit_in_calculator_tapped` | — | `TS:3088` |
| `player_menu_opened`, `untouchable_toggled` | — | `TS:6975`, `TS:1326` |
| `trio_entry_tapped`, `team_review_opened`, `help_opened`, `demo_bridge_tapped` | — | `TS:7269`, `TS:5749`, `TS:5957`, `TS:6688` |

**The blast radius that matters:** `trade_card_viewed` is an **INTENT** event (`analytics_taxonomy.py:51`; `INTENT_EVENTS = (SERVER_FIRED | ALLOWED_CLIENT) - NON_INTENT`, `analytics_queries.py:335`). The taxonomy comment at `:497` says the session is *"defined by `trade_card_viewed`, which is INTENT and fires on every card."* Removing the deck removes the app's densest intent signal — **every activation, engagement and retention metric built on intent user-days would break at the seam and not be comparable across the change.**

**Would change meaning rather than stop:**
- `calc_find_a_trade_tapped` (`:607`) — its `path` prop (`fair`/`model`) currently distinguishes two destinations. With no model deck, `path:'model'` becomes meaningless. Props pinned at `:1491`.
- `calc_mode_switched` (`:596`, `:1475`, enum `live | league`) — dies the moment the pushed page loses its tabs. That happens under **`calc.inline_home` too**, not only under D1(b). Its `mode` enum would have exactly one live value.
- `calc_cleared.mode` (`:1477`) shares the same `live | league` vocabulary and has the same problem.
- `calc_tour_started` / `_ended` / `_beat_missing` (`:584`, `:1470-1474`) — the tour spans both surfaces (n10–n18 calc, n19–n24 deck). `beats_shown` would fall by roughly half with no code change, purely because half the beats have no host. **A silent metric shift, not an outage** — the dangerous kind.
- `calc_trade_shared.surface` (`:1174`, enum `calc_live | calc_in_league | trades_liked`) — `trades_liked` dies with the deck.
- `deck_back_to_calculator` already changes meaning under `calc.inline_home`: `TS:3007-3016` makes it a scroll rather than a navigation, with the same event and payload. Documented, intentional, and worth remembering when reading the series across the flip.

**Nothing new is registered by `calc.inline_home`** — verified: `canvasSearch.ts:24-26` states it and both hosts call the same helper with only the `screen` label differing.

### 8.2 The flag sequence for a safe rollout

Prerequisite chain, verified in `config/features.json`:

```
onboarding.v2 (true, master)
  └─ onboarding.guided_avatar (true)
       └─ onboarding.guide_v2 (true)   ← lit 2026-08-22 with calc.merged_layout
calc.merged_layout (true)              ← gates /api/trades/queue AND /api/trades/fair-packages
  └─ calc.inline_home (FALSE, dark)    ← requires calc.merged_layout; 404s both routes without it
ux.prompt_arbiter                      ← the tour-long interstitial hold
trade.outlook_direction (false)        ← OutlookBiasReceipt; both surfaces fall back honestly
```

**Recommended sequence for D1(a) — the direction I recommend:**

1. **Build Wave B** (the tour merge). Re-target n10–n18 at the inline module; re-thread `calcTourInLeagueReady` / `calcTourInLeagueGone` / `calcTourOutlookClosed` (`TC:801-812`) through `TradeBuildCanvas`; restore an `onShowMeAround` path (`TS:6530-6544` omits it deliberately, stated at `TS:6518-6522`). Nothing lights during this step.
2. **Fix Q5** (the fair-sweep zero-result empty state) and **D7** (Clear undo) — both are small, both are pre-existing, both get more visible on a merged page.
3. **Run the Wave B0 TestFlight checklist** (`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`, Wave B0 section) — written and **unrun** per `scope-wave-b0.md:192`. Under D-056 this is the only runtime evidence mobile gets.
4. **Baseline capture, ≥7 days before the flip:** `trade_card_viewed`, `find_trades_tapped` (by `source`), `calc_find_a_trade_tapped` (by `path`), `calc_tour_ended.beats_shown`, `calc_mode_switched`. These are the five series that shift at the seam.
5. **Light `calc.inline_home`** via `POST /api/feature-flags/reload` — no deploy, no client build. The flag's own comment confirms this is the kill switch and that off is byte-identical.
6. **Watch 48h**, then close the `trades_home_inline` (#270) experiment, which the flag's precedence rule already supersedes (`TS:5152-5167`).
7. **Retire the `trades.outlook-fallback` row** (`TS:5607`), marked mortal for exactly this moment.
8. **Only then** open the separate question of whether the deck shrinks — with data from steps 4–6.

**If D1(b) wins instead**, the sequence is materially different and I would not run it as a flag flip. It needs: a new flag (`calc.primary_surface` or similar, default off), the 24 clusters adjudicated one by one, a rewritten tour spine covering both `s*` and `n*` beats, re-added navigation reversing #384 rulings 6/7, and an explicit analytics seam note in `living-memory/` because `trade_card_viewed` intent-days will not be comparable across it. That is a build wave, not a config change.

---

## Appendix — sources

Code: `mobile/src/screens/TradesScreen.tsx`, `mobile/src/components/InLeagueCalculator.tsx`, `mobile/src/screens/TradeCalculatorScreen.tsx`, `mobile/src/components/TradeBuildCanvas.tsx`, `mobile/src/components/TradeDnaSheet.tsx`, `mobile/src/components/TradeCard.tsx`, `mobile/src/components/TradeHomeUtilityRow.tsx`, `mobile/src/components/FeaturedTradeWindow.tsx`, `mobile/src/components/analystScript.ts`, `mobile/src/utils/canvasSearch.ts`, `mobile/src/navigation/TabNav.tsx`, `backend/server.py`, `backend/analytics_taxonomy.py`, `backend/analytics_queries.py`, `config/features.json`.

Docs: `docs/feedback/items/384-calc-finder-merge/status.md`, `docs/plans/onboarding-tour-merge/plan.md`, `docs/plans/onboarding-tour-merge/scope-wave-b0.md`, `living-memory/NEXT.md`, `living-memory/CHANGELOG.md`, `living-memory/DECISIONS.md` (D-152, D-153, D-157, D-158), `docs/design/design-system.md`, `docs/design/components.md`.

Deliberately **not** used as evidence of current behaviour: `mockups/` (never shipped code) and `screens/` (frozen 2026-08-11, predates `calc.merged_layout` shipping on 2026-08-22).
