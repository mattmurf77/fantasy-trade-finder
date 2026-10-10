# Home engagement: research synthesis

> **Purpose:** what each competitor and reference does on its home or landing to drive engagement, what Fleeced's Home should steal, and what it should avoid. The question is narrow: how should Home surface trade opponents so returning users get pulled into League Summary's position buyers/sellers split (flag `league.pos_candidates`)?
>
> **Status:** research for a design-only phase, 2026-10-10. Nothing here binds until the operator picks a direction. Mockup: [`mockups/home-engagement/index.html`](../../../mockups/home-engagement/index.html). Scope for the recommended direction: [`scope.md`](scope.md).

## Table of contents

- [Sources read](#sources-read)
- [1. FumbleAI (primary reference)](#1-fumbleai-primary-reference)
- [2. Dynasty Nerds / DynastyGM](#2-dynasty-nerds--dynastygm)
- [3. DynastyDealer](#3-dynastydealer)
- [4. Dynasty Trade Factory](#4-dynasty-trade-factory)
- [5. Dynasty Daddy, FPTrack, Dynasty Dealmaker](#5-dynasty-daddy-fptrack-dynasty-dealmaker)
- [6. KeepTradeCut](#6-keeptradecut)
- [7. TI-CALC](#7-ti-calc)
- [8. Landing concepts (our own, April)](#8-landing-concepts-our-own-april)
- [9. Internal research and backlog](#9-internal-research-and-backlog)
- [10. Constraints Home must respect](#10-constraints-home-must-respect)
- [Synthesis: what we carried over](#synthesis-what-we-carried-over)
- [FumbleAI vs Chalkline: every conflict](#fumbleai-vs-chalkline-every-conflict)
- [What we deliberately did not take](#what-we-deliberately-did-not-take)

---

## Sources read

| Source | Location | How it was read |
|---|---|---|
| FumbleAI Home hub (SwiftUI) | `…/Claude/Projects/FumbleAI/HomeApp/App/Features/Home/{HomeHubView,HomeHubCatalog,HomeHubModel,MainTabView}.swift` | Read in full (read-only, iCloud) |
| FumbleAI canvas mockup | `…/FumbleAI/docs/homeowner-app/mockups/index.html` + `seven-views.md` | Rendered from a scratch copy in a browser at 440pt; CSS tokens extracted |
| Dynasty Nerds (DynastyGM web app) | `…/Fleeced/_local/research/competitors/dynasty-nerds-app/` (32 PNGs + `index.md`) | Viewed `01-home-leagues.png`, `03-analyzer.png`, `05d-player-detail-stats-leagues.png`, `06-shares.png`, `10-trades-browser.png`, `11b-team-calculator-filled.png`; the other 26 via `index.md` |
| In-repo teardowns | `docs/competitor-teardown-{dynastydealer,dynastygm,ti-calc,web-tools}.md`, `docs/business/product/2026-07-26-{dynastydealer-dtf-teardowns,dynastygm-app-teardown}.md`, `docs/competitor-research-trade-quality-2026-09-04.md` | Read in full |
| Backlog | `docs/plans/competitor-feature-backlog-2026-06-11.md`, `docs/plans/competitor-top20/` (#1, #8, #9, #13, #14, #15, #18 in full; the rest skimmed) | Read |
| April reference files | `…/Fantasy Trade Finder Reference Files/{dynasty-daddy-review-2026-04-16.md, keep-trade-cut-review-2026-04-16.md, landing-concepts.html}` | Read in full (read-only, iCloud) |
| Internal | `docs/plans/home-tab/{plan,scope}.md`, `living-memory/{BRAND,DECISIONS}.md` (D-198, D-044, D-155), `mobile/src/screens/LeagueSummaryScreen.tsx`, `backend/server.py` power-rankings route | Read |

The iCloud folders were treated as read-only. The Dynasty Nerds PNGs are "dataless" iCloud placeholders that `cp` could not materialise (G-074's eviction behaviour), so they were viewed in place and never copied. Caveat from the April reviews themselves: both were reconstructed from search results and docs, not live walkthroughs (`dynasty-daddy-review-2026-04-16.md:7`, `keep-trade-cut-review-2026-04-16.md:7`).

---

## 1. FumbleAI (primary reference)

The operator confirmed this is the intended reference and likes its home design: big tappable tiles, not tight text links. There are two "homes" in that project, and they differ.

**(a) The shipped SwiftUI Home tab, `HomeHubView`: the one the operator means.** It was added after the HTML mockup was drawn, so the mockup doesn't show it (`gap-analysis-2026-10-02.md:5,148`). Top to bottom (`HomeHubView.swift:45-126`, `HomeHubCatalog.swift:185-242`):

- **Header.** A subtitle naming the user's own property (13pt semibold), a settings circle, then the title **"What would you like to do?"** (28pt bold). That is our Home's exact question.
- **Live summary capsule** under the title, ordered by urgency with an all-clear fallback: "1 chore due today · 1 overdue · $3.6k planned · 2 running low", or "Nothing due this week" (`HomeHubCatalog.swift:314-325`). It is never empty.
- **"YOUR HOME":** two full-width cards (min 84pt, 52pt icon tile, title + detail + badge + chevron): Floor plan and Yard & Exterior. The Yard card turns into a setup prompt ("Add") when there is no yard (`:201-208`).
- **"GET THINGS DONE":** a 2×2 grid of half-width cards (min 132pt). Each has an icon tile, a count badge, a 16pt title and a 13pt detail. It collapses to one column at accessibility text sizes (`HomeHubView.swift:20`).
- **Badge ladder.** Attention (overdue) beats today, which beats this week, which beats the total. A zero renders nothing: "nothing for zero so empty cards stay quiet" (`HomeHubCatalog.swift:210-239, 337-338`).
- **Navigation.** Every card is one tap from its destination. Cards that open the Plan tab preset its lens and floor through a shared store (`env.selectedLens`, `env.pendingLevelID`), never through route params (`MainTabView.swift:85-96`).
- **Live counts.** The model subscribes to eight data streams, so numbers are current on every return (`HomeHubModel.swift`). The To-Dos *tab* badge mirrors the urgent count (`MainTabView.swift:24,44`).

**(b) The HTML mockup's "Home canvas"** (`index.html` screen 01; `seven-views.md`). It shows a floor plan with a **view dropdown** (lens), **floor pills**, rooms as big tappable blocks carrying a live chip ("5 due", "$3.5k"; a red inner edge when overdue), a **bottom strip** with totals and a named **"Next: Do the dishes · Sam · today"** line (`index.html:106, 547-556`), and a half-height **room sheet** that keeps the room highlighted above it. Rooms with nothing relevant **fade to grey** so the ones that matter stand out (`seven-views.md:34-36`).

**Steal:**
- The hub's skeleton, almost line for line: question title → live line → "your X" full-width section → 2×2 task grid with live badges. This is Direction A.
- The urgency-ordered live line with an all-clear fallback.
- Badges that hide at zero.
- The setup-prompt card for missing data, which becomes our "Link a league" and "Not enough rosters yet" states.
- Store-based lens presets for cross-tab handoff, which matches this repo's own rule that "route params stay dead" (`LeagueSummaryScreen.tsx:1139-1144`).
- From the canvas: lens + pills + rooms + quiet-room fading + a named "Next:" line. This is Direction B.

**Avoid:** every visual device that conflicts with Chalkline (table below), plus the "sparkles" icon on the summary, which reads as an AI cliché. The hub has no streaks and no dark patterns; nothing to avoid on that front.

---

## 2. Dynasty Nerds / DynastyGM

**Home** is "Your Leagues": one row per league with a color-coded **rank chip** (`1 / 14` green, `5 / 12` orange, `10 / 12` red), a format subtitle and an "Updated:" timestamp with refresh (`01-home-leagues.png`; `docs/competitor-teardown-dynastygm.md:84-86`). The teardown names it the hook: rank chips on Home "create daily-open habit loops cheaply" (`dynastygm.md:164`; `2026-07-26-dynastygm-app-teardown.md:19-22`).

Other screens that bear on opponent discovery:
- **`03-analyzer.png`.** Position pills over a league-wide stacked bar chart. **Your team keeps its color and every other bar goes grayscale**, which the teardown calls "the strongest visual idea in the app" (`dynastygm-app-teardown.md:39-42`). Position group headers carry **value plus positional rank**: "Runningbacks (7) — 5,606 (7/12)".
- **`05d-player-detail-stats-leagues.png`.** A cross-league "Trade target · 5 leagues" panel: league name, the owning team, "RB 1" and a "TRADE ›" link per league. This is opponent discovery framed as a list of one-tap trade entries.
- **`06-shares.png`.** Exposure across your own rosters, "4 (80%)": portfolio framing, no opponent angle.
- **`10-trades-browser.png`.** Real completed trades across many Sleeper leagues with league-setting chips. A market feed, not your league.
- **`11b-team-calculator-filled.png`.** One plain-language verdict banner: "mattmurf77 wins the trade by 3,608 points."

**Steal:**
- The **focus treatment** (you in color, the league grey) for Direction A's median bar strip.
- **Per-position rank "(7/12)"** for A's position tiles.
- The 05d **list of named trade entries with a verb** ("TRADE ›") for Direction C's rails.
- One-sentence verdict copy.

**Avoid:**
- A passive Home. The chip is a wealth readout with no action attached; DynastyGM "has no find-me-a-trade" (`dynastygm-app-teardown.md:94-95`).
- Red/orange/green rank encodings. They imply a seller is "good" and a buyer is "bad", which League Summary explicitly refuses (`LeagueSummaryScreen.tsx:2591-2595`).
- Six-tab sprawl. Our bar already has six tabs (`home-tab/plan.md:50`).

---

## 3. DynastyDealer

**Home** has a Dynasty/Redraft toggle, two quick actions (Trade Calc, Rankings), a **Free-vs-Premium plan card** with an upgrade CTA, and a Command Center below the fold (`docs/competitor-teardown-dynastydealer.md:16-21`). Its real engagement engines live off Home:
- Vote Hub streaks, called "a daily-open habit" (`:170`).
- **Recon**, "scouting tool that works on any Sleeper username" (`:144-145`).
- Market Hub risers/fallers with one-line evidence ("above market price in 83% of trades", `2026-07-26-dynastydealer-dtf-teardowns.md:35-37`).

**Steal:**
- The **opposition-research framing**: Home should feel like scouting your leaguemates.
- One-line evidence on every claim. Our version is "You're 2nd of 12: ≈5.5 firsts against a league median of ≈2.5 firsts".

**Avoid:**
- A plan or paywall card on Home. Backlog #63 calls degraded free tiers the cautionary tale (`competitor-feature-backlog-2026-06-11.md:313`).
- Stock-market cosmetics and mass-send, both PASS (`:358-359`, `:364-365`).
- Risers/fallers on Home: the operator ruled "not now" (`dtf-teardowns.md:126-128`). `market.movers` is lit, but its home is the Market pulse strip, not this screen.

---

## 4. Dynasty Trade Factory

**Landing** is a username import plus four tool cards, hub-and-spoke with no tab bar (`dtf-teardowns.md:55-57`). It is structurally today's four-row Home, and it is the shape to leave behind. Its best ideas sit one level down:
- **Partner picker rows with an inline, color-coded positional shape:** "bkey5 · QB 930 | RB 2225 | WR 2948 | TE 856", so "you see a team's shape before you even open the trade" (`:59-62`).
- **Team Analysis:** strongest and weakest position, then per-counterparty trades with "Why this trade works" (`:82-86`).
- **League Analyzer:** a "What to do with it" block, "surplus teams = trade partners", over charts with a **League Average dashed line** (`:88-92`).

**Steal:**
- "Surplus teams = trade partners" is literally the buyers/sellers thesis. It becomes A's hero headline.
- The league-average line is the visual twin of our shipped median divider; A's bar strip draws it.
- The partner shape line powers C's team tiles and B's team sheet. Fleeced already ships it as `PartnerSummaryLine` in the in-league calculator.

**Avoid:** the static tool-card menu.

---

## 5. Dynasty Daddy, FPTrack, Dynasty Dealmaker

- **Dynasty Daddy.**
  - Its landing is a value proposition, social-proof counters and **7 equal tool tiles**. The review calls that its main conversion weakness: "the user has to pick between 7 tools without guidance" (`dynasty-daddy-review-2026-04-16.md:70, 86-89`). Its own fix is to put the trade finder at the top (`:101`), plus a smart-start CTA chosen from league state (`:147`).
  - Power Rankings frame teams as "contenders/frauds/trade partners" and show who is over- or under-weight at each position (`:35, :103-106`), with week-over-week change on every team card (`:106`).
  - Trade-finder cards show the partner's tier and roster needs (`competitor-research-trade-quality-2026-09-04.md:22`).
- **FPTrack.** Push-first retention. Power rankings and trade suggestions are Pro features (`competitor-teardown-web-tools.md:163-168`).
- **Dynasty Dealmaker.** Flow is "sync league → identify targets → execute trade", with rebuild/contend detection and per-team positional needs (`web-tools.md:177-181`).

**Steal:**
- **Equal tiles are not enough.** A tile grid needs one tile that is clearly first, chosen from the league's state. This is why every direction has a hero, and why A's hero picks *your* most lopsided position.
- The "over/under-weight by position" framing.
- Sync → targets → execute as Home's top-to-bottom order.

**Avoid:**
- Ad-loaded free tiers.
- Games decoupled from the product, a PASS in backlog #76 (`backlog:355-356`). The teardown's own conclusion is that our trio ranking is the native loop: "gamify it" (`web-tools.md:214`).

---

## 6. KeepTradeCut

**Home is the product.** The Keep/Trade/Cut vote happens in the hero, no login required, followed by a **community-comparison reveal** ("you said Keep, 62% said Cut") (`keep-trade-cut-review-2026-04-16.md:27-40, 176, 203`). League sync adds a League Overview: stacked teams, pick hoarders (`:83-85`).

**Steal:**
- Put a real slice of the split on Home, not just a link to it. A's hero shows the actual distribution (bars, median, brackets) and a reveal ("4 teams are short at RB, you're 2nd") before the tap.
- Pre-select from league state. KTC auto-detects settings (`:214`); we pre-pick the position.

**Avoid:**
- Value with no counterparty. KTC never names leaguemates (`:185`), and naming them is our whole edge.
- Tables that scroll sideways on phones (`:143`).
- Emoji in toast copy (`:235`).

---

## 7. TI-CALC

There is no home: three pages (`competitor-teardown-ti-calc.md:9`). It does have two useful patterns:
- **Pick-anchored language as UX** ("worth X firsts", `:35`). Our medians already carry a server pick label (`server.py:889-914`), so "median ≈2.5 firsts" costs nothing.
- **"High on / low on" top-5 outlier lists** (`:52`).

**Avoid:** stale static data (`:58`) and a gated editor "with no preview" (`:61`). Home modules must render something even when data is thin.

---

## 8. Landing concepts (our own, April)

There are three tabs: Story Scroll, Split Hero and Card Stack (`landing-concepts.html:1227-1583`). Only **B's** "Your Rankings + Their Rankings = Trades That Actually Work" (`:1378-1380`) and its DM-pain line (`:1385`) gesture at opponents, and only generically. None names a counterparty or frames positional need versus surplus.

**Steal:** the "you + them" structure made concrete: "puntgods is 12th at RB. You're 2nd."

**Avoid:**
- The whole visual layer, which predates Chalkline: Roboto/system stack (`:28`), `#4f7cff` (`:16`), gradients (`:140, 328, 372, 573`), 10–20px radii, and emoji icons (`:1308, 1324, 1340, 1396`).
- The "data stays on device" claim (`:1309, 1443, 1579`). It is no longer true.
- Sleeper-only copy, since ESPN and MFL are live.

---

## 9. Internal research and backlog

| Item | What it says | Shipped? | Use on Home |
|---|---|---|---|
| Backlog #21 Home rank chips (`competitor-feature-backlog-2026-06-11.md:142-145`) | "Earns the daily open with one glance" | Chip API shipped (`/api/league/rank-chip`, `server.py:29803`); rendered on LeaguePicker/LeagueScreen only | A's subtitle + League tile ("5th") |
| Backlog #22 needs/surplus surfacing (`:147-150`) | "Your needs: RB depth · Surplus: WR" | `position_needs`/`position_surplus` on `/api/league/preferences` | C's "your shape" tile; A uses League Summary's bands instead so the two never disagree |
| Backlog #38 Trade of the day (`:227-230`) | A card "on the home screen and in push" | Presentation v2 hero exists, dark (`trades.presentation_v2` false) | Not on Home v1; a natural later tile |
| #1 Opponent outlook classifier (`competitor-top20/01-…md`) | Explain *why* a team is a good partner | Labels shipped (`trade.outlook_infer` on; `trade_service.py:3999`), stamped on cards only (`:6495`); **no mobile chip renders it**; not on power-rankings | C's window chip is a **backend gap** |
| #9 Community-diff angles | Buy-low/sell-high as "a visible, repeatable reason to open the app" | **Not shipped** (`tiers.community_diff` false) | Not on Home v1 |
| #13 Ranking gamification (`13-ranking-gamification.md:36-39`) | "12 matchups refines your RB curve"; reward the output | Skeleton only (streak, leaderboard, progress); goal loop not built | A's Rank tile names the unranked position; never a streak flame (emoji) |
| #14 League power rankings (`14-league-power-rankings.md:8, 32, 47`) | "A divergence instrument, not a leaderboard"; "never fabricate" a team chip; target ≥10% drill-down → trade CTA | **Shipped on mobile** (League tab root); `medians` + bands live (#300) | The whole centrepiece. Home is the missing entry point |
| #18 Trade push (`18-trade-push-notifications.md`) | Discovery dies if it only happens on app-open | Plumbing exists | Out of scope; a later push could carry the same "4 teams short at RB" line |
| Trade-quality research (`competitor-research-trade-quality-2026-09-04.md:22, 101, 141`) | Show the partner's reason to participate; "a missing opponent board should produce an estimated fit, not a claim" | n/a | Copy rule: "short at RB", never "wants RB" or "is shopping" |

---

## 10. Constraints Home must respect

- **D-198** (`living-memory/DECISIONS.md:17-27`).
  - Home is the launch tab for returning users.
  - First-run users (`onboarding.trades_first`, no swipe yet) still land on Acquire, so the analyst guide is untouched.
  - `nav.home_tab` is read once at mount and is the rollback.
  - "No new analytics events": that was true for the static Home. This redesign needs two, specced in `scope.md`.
- **`docs/plans/home-tab/plan.md`.**
  - "No data fetching, no new state" (`:59`). The redesign breaks this on purpose, behind its own flag, so `nav.home_tab` keeps its meaning.
  - No local `FeedbackFAB` (`:58`).
  - The four labels/targets/testIDs are pinned by `check-home-tab.js` (`:80`), which must be extended with a flag-off byte-identical clause, not loosened.
- **D-044.** A position filter means that position; picks are never auto-added. Home's numbers must therefore be positions-only, which they are (`teams[].positions[P].value`).
- **#300 decisions.**
  - Buyer/Seller badges are neutral and "drive no behaviour" (`LeagueSummaryScreen.tsx:1018-1026, 2591-2595`).
  - The median divider renders only on the All subset, under exactly one core position (`:860-866`).
  - Home's claims must use the same arithmetic, so the count on Home equals the badges the user then sees.
- **BRAND.md voice.**
  - Dynasty-fluent peer.
  - Cite a value ("≈5.5 firsts"), no hype, no exclamation points.
  - Empty states say what to do. Errors say what failed and what to try.
  - The ram mascot belongs in "guide bubble, Team Review, empty states, celebration": an optional empty-state illustration, never inline with data.

---

## Synthesis: what we carried over

Ranked by how directly each pulls a user into the buyers/sellers split:

1. **One hero, chosen from the league's state, above a grid of equal tiles.** Sources: FumbleAI's "Your home" section over "Get things done"; Dynasty Daddy's "7 tools without guidance" failure (`dynasty-daddy-review:86-89`). The hero is the split at *your* most lopsided position.
2. **Show a slice of the split, then tap into it pre-filtered.** Sources: KTC's "the CTA is the product"; FumbleAI's lens preset via store (`MainTabView.swift:85-96`). Home draws the bars, median and brackets, then opens League rankings with RB already applied.
3. **Name the opponents and the reason.** Sources: DTF "surplus teams = trade partners" (`dtf-teardowns:89`); Dynasty Nerds' named trade-target rows (`05d`); FumbleAI's "Next:" line. The hero ends with the four shortest RB rooms by name.
4. **Your rank per position, in the league's own terms.** Source: Dynasty Nerds Analyzer "(7/12)" (`03-analyzer.png`). This becomes the four position tiles, each a door into its own split.
5. **Focus treatment.** You keep your color and the league goes grey (`dynastygm-app-teardown:39-42`), drawn on DTF's league-average dashed line (`dtf-teardowns:90-92`). This is the hero's bar strip.
6. **Live line ordered by urgency, never empty; badges quiet at zero.** Source: FumbleAI (`HomeHubCatalog.swift:314-325, 337-338`).
7. **Missing data turns the card into a setup prompt.** Source: FumbleAI's Yard card (`:201-208`). This becomes the no-league and thin-league states.

---

## FumbleAI vs Chalkline: every conflict

Rule applied (operator): keep FumbleAI's tile structure, render it in Chalkline tokens.

| FumbleAI (value · source) | Chalkline rule (`docs/design/design-system.md`) | Rendered as |
|---|---|---|
| Card radius 14; icon-tile radius 10.8/14 (`HomeHubView.swift:311-313, 349-355, 372`) | #5 radius ≤8 except specced pills | Cards 8, icon well 4, badges 2 |
| Pill badges, summary capsule (`:390`, `:91`) | Pills only for count badges / specced chips | 2px Badge construction; capsule → Banner (ink-2, hairline, ice tick) |
| SF Pro everywhere; mockup `--ui: -apple-system,"SF Pro Text","Inter",system-ui` (`index.html:12`) | #4 no Inter / system stack | Barlow Condensed (title, hero headline), Archivo (UI), IBM Plex Mono (every number) |
| Accent `#1E5AA8`; accent-soft `rgba(30,90,168,.11)` icon tiles and capsule (`index.html:17-18`) | #6/#9 ice for actions, flare for highlights, no new hues; components.md kills the `rgba(color,.15)` tint pattern | Ink-2 icon wells, chalk-dim glyphs; ice only on the hero CTA, the YOU marker and the active tab (≤3 rule) |
| Attention badge: danger `#C23A2E` on danger-soft (`:377-392`) | `--neg` = pass/error only; flare = count emphasis | Flare-bordered mono count (Matches "2") |
| Blueprint-grid paper texture, page + wide cards (`:58, :404-420`) | Solid ink surfaces; no decorative chrome texture | Dropped; the hero's bar strip carries the "this is your league" identity |
| Pressed: scale 0.98 + opacity 0.85 (`:394-401`) | #7 no lift; state change by surface/border | Pressed fill ink-3 |
| "sparkles" SF Symbol on the summary (`:82`) | #1 Chalkline icon set only | The Banner's ice tick |
| Shadows on strip/menu/sheet (`index.html:106, 154, 160`) | #8 one shadow, sheets/menus/toasts only | Tiles hairline-only; B's team sheet may use `--shadow-sheet` |
| Stock iOS tab bar (system blur material, `MainTabView.swift:27`) | #3 no blur | Our existing solid tab bar, unchanged |
| Light-first theme (`--page:#E8EAED`) | Dark-only | Ink steps throughout |
| Gradient legend swatch, repeating-gradient hatch (`index.html:225, 286`) | #2 no gradients | B's quiet rooms use a dashed border, not a hatch; loading skeletons are static, no shimmer |
| Red inner edge on overdue rooms | Flare never the primary affordance on an actionable control | B marks the relevant teams with a 6px flare square (the NotificationRow unread-dot construction), not a colored edge |

---

## What we deliberately did not take

- **Streaks, flames and confetti** (DynastyDealer, the #13 doc's 🔥 chip). Emoji are banned, and the rank loop is reached through the Rank tile, not decorated on Home.
- **Risers/fallers on Home.** The operator ruled "not now" for this surface (`dtf-teardowns:126-128`). Market pulse already has a home.
- **Paywall or plan cards.** `monetize.paywall` is dark; Home is not an upsell surface.
- **Playoff odds on Home.** `/api/league/outlook` is a Sleeper-only Monte-Carlo run. Home stays at one new request, and the band lives one tap away on League.
- **Opponent intent claims.** "Buying" means *short at the position by value*, a fact about rosters. Copy never says a team "wants" or "is shopping" anything (trade-quality research `:101`).
- **Colored rank chips (green/amber/red).** League Summary deliberately renders Buyer/Seller as neutral badges. Home follows it.
