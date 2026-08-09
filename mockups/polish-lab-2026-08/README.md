# Polish Lab — 2026-08

Current-vs-proposed design mockups for the August polish batch (operator
feedback #206–#234). Each page: faithful recreation of today's screen (left)
beside the proposed redesign (right) in 390px phone frames, rationale below.
Chalkline tokens throughout; all assets inline. Master viewer: `index.html`
(one tab per item).

| Page | Feedback | What it shows |
|---|---|---|
| [`header-league-switcher.html`](header-league-switcher.html) | #223/#224 | League name built into the global TopBar (ice chevron = switchable) + the opened LeagueSwitcherSheet (with #199 Add-a-league); replaces the League-hero / per-screen-pill switching |
| [`hub-fit-to-screen.html`](hub-fit-to-screen.html) | #218/#219 | Trade-Finding Hub density pass — annotated margin/padding reductions (~120pt reclaimed) that put the whole hub above the fold (no content removed) |
| [`notifications-dechalk.html`](notifications-dechalk.html) | #225 | Emoji-free notifications: fact-first push titles + Chalkline inbox rows with stroke glyphs (current strings verbatim from the backend templates) |
| [`trade-dna-outlook.html`](trade-dna-outlook.html) | #212/#231/#206 | Tappable outlook cards with plain-words bias, explicit Edit button, STARTER NEED vs DEPTH two-tier need chips, bias receipt line on the deck |
| [`trade-dna-outlook-v2.html`](trade-dna-outlook-v2.html) | #212/#231/#206 (v2) | Iteration on operator review: compact 111px collapsed DNA card on entry (−69% vs v1's 355px panel), Edit expands in place to all-positions toggle rows (solid position-color fill = selected, passive NEED/DEPTH hint tags, chase/shop mutual exclusion); deck bias receipt kept unchanged |
| [`trade-dna-outlook-v3.html`](trade-dna-outlook-v3.html) | #212/#231/#206 (v3) | Operator confirm pass: multi-select made explicit in both states (collapsed lists Chasing WR·TE — Shopping QB·RB; editor shows two filled toggles per row + in-UI "multi-select" caption) and the collapsed untouchables count becomes player mini-card chips (6px position-color dot + name, 3 shown + "+N", collapsed-only); panel 140px |
| [`asset-ideas-layout.html`](asset-ideas-layout.html) | #216/#209 | Best suggested trade leads (value bar visible), give-left/get-right everywhere (fixes the pin board's reversed columns), Upgrade/Lateral/Downgrade behind "More options →" |
| [`asset-ideas-layout-v2.html`](asset-ideas-layout-v2.html) | #216/#209 v2 | Operator iteration: Dynasty Value Swing verdict kept, "More trades" list open by default, idea rows are tappable cards that load into the featured window (live demo), default ‹ Previous-trade chip |
| [`asset-ideas-layout-v3.html`](asset-ideas-layout-v3.html) | #216/#209 v3 | Operator iteration on v2: header de-named to just "Featured trade"; ‹ Previous-trade chip moved top-left, drafted both ways — Variant A own row above the header (recommended, iOS back convention; live demo) vs Variant B in the header row (denser, static) |
| [`empty-states-progress.html`](empty-states-progress.html) | #229/#230/#234 | Solo-value-first empty states, one unified progress module (position ring + leaguemate meter + honest unlock line), zero-rows collapsed until they have data |
| [`empty-states-progress-v2.html`](empty-states-progress-v2.html) | #229/#230/#234 | v2 after operator review: Explore-first order, real TradeValueBar on the example card, terse CTAs — Variant A (buttons in place) vs Variant B (side-by-side action row under the League card) |
| [`empty-states-progress-v3.html`](empty-states-progress-v3.html) | #229/#230/#234 (v3) | Operator iteration folding v2's A+B: side-by-side action row under the League card (sides switched — Rank players left secondary, Find a trade right ice primary) AND the in-section buttons restored, so both CTAs appear twice; v2 frames kept as a superseded reference strip |
| [`rank-method-consolidation.html`](rank-method-consolidation.html) | #232/#233 | One chooser: Fastest / Most precise / Most control; Quick rank demoted to a follow-on; the rest behind "More ways to rank"; empty-tier CTA reworded "Continue — no QBs this high" |
| [`rank-method-consolidation-v2.html`](rank-method-consolidation-v2.html) | #232/#233 (v2) | Operator iteration: Most control = the Tiers drag board (overall list demoted to the disclosure) + small "Have rankings already? Import them" entry opening a "Bring your rankings" sheet (CSV / XLSX / paste a table) with the match-review state shown |
| [`rank-method-consolidation-v3.html`](rank-method-consolidation-v3.html) | #232/#233 (v3) | Chooser header row only: import entry fitted to the RIGHT of "Build your board" in three variants — (A, recommended) "Have rankings already?" text link with wrap treatment, (B) compact solid-ice "Import Rankings" button, (C) ice-outlined "Import" chip — all with the corrected UPLOAD glyph (v2's pointed down); sheet/match-review unchanged from v2 (reference frame) |

## Round 2 — 2026-08-02 (scroll audit #243 + movers + lineup #238)

Master viewer: `index-round2.html` (one tab per page, srcdoc-embedded).

| Page | Feedback | What it shows |
|---|---|---|
| [`pin-mode-collapsed-controls.html`](pin-mode-collapsed-controls.html) | #243 audit #1 | Single-pin mode: full Controls Card (286pt) collapses to "Pinned: X · Edit" one-liner (V1, ~246pt saved, recommended) vs pin context merged into the featured-window header (V2) |
| [`tradevaluebar-density.html`](tradevaluebar-density.html) | #243 audit | TradeValueBar 248pt → V1 192pt (verdict paragraph behind "Why? ›", heading step-down; recommended) vs V2 174pt composite headline; both fix the fontSize:9 violation |
| [`league-home-fold.html`](league-home-fold.html) | #243 audit | Low-activity League home: V1 divider-bug fix + Explore 3-across tiles (module fits, 55pt spare; recommended) vs V2 pure reorder (module promoted, 110pt spare, bug unfixed) |
| [`trios-three-up.html`](trios-three-up.html) | #243 audit | Trios matchup: 3 stacked 108pt cards → V1 side-by-side mini-cards (−196pt, recommended) vs V2 compact rows (−148pt) vs V3 = V1 + winner tap-state; MHJ name-truncation stress case |
| [`drilldown-filter-dedup.html`](drilldown-filter-dedup.html) | #243 audit (respects #237) | League-summary drill-in: while focused, chart card collapses to slim strip so one control set shows (V1, 171pt recovered, recommended) vs sticky drill controls + hidden home row (V2, 79pt); #237 shared always-match state untouched |
| [`risers-fallers-cards.html`](risers-fallers-cards.html) | DynastyGM teardown | Movers UI on FTF snapshot history: V1 two-column "Movers this week" card (recommended) + V3 compact Market-pulse strip (near-free) vs V2 swipe cards (hold); honest "FTF community value" labeling + missing-endpoint notes |
| [`lineup-before-after.html`](lineup-before-after.html) | #238 | Starting-lineup impact on the trade summary: V1 changed-slots delta strip, V2 full 7-slot before/after table (calculator only), V3 collapsed one-liner expanding in place; data notes (slot-level backend work needed, deck cards lack starter data) |
| [`acquire-landing-guided-first.html`](acquire-landing-guided-first.html) | #246 (Opus) | Should the hub exist? 9 frames: current Acquire hub vs V1 guided-first landing + chip strip (recommended, FA as tail section), V2 hub-as-sheet, V3 smart last-used landing (with honest state-requirements panel) |
| [`combined-rank-bars.html`](combined-rank-bars.html) | #248 | One graph for consensus + my board: V1 paired bars, V2 ghost-tick + delta arrows (recommended), V3 delta chip only; "color per team" rendered but argued against (breaks position-color invariant) |

## Round 3 — 2026-08-08 (#211 player-first trades)

| Page | Feedback | What it shows |
|---|---|---|
| [`trades-player-first.html`](trades-player-first.html) | #211 (operator note, mockup-only) | Should the specific-player pin board lead over the guided deck? Current-state reference (3 frames: guided deck, empty player board, shipped single-pin convergence) + 3 directions: (a) player mode as default landing, deck demoted (b) hybrid — existing flat target section promoted above the deck, no mode switch (c, recommended) full merge — the two-column board sits permanently above the deck, pins progressively narrow it. Routes Outlook/Fairness through a generic "Edit trade setup" stand-in per #257 (controls card → edit sheet, in flight, not yet on `origin/main`). Companion doc: `docs/feedback/items/211-player-first-trades/status.md` |

## Round 4 — 2026-08-09 (#270/#272/#279 inline trades home)

| Page | Feedback | What it shows |
|---|---|---|
| [`trades-home-inline.html`](trades-home-inline.html) | #270 (core ask) / #272 / #279 | How much of the `TradeDnaSheet` full-sheet (#257) should live directly on the TradesHome page instead of behind "Change"? Current (2 frames: shipped landing + the shipped sheet opened) + a baseline assuming #269 (mode tabs removed, League/Team fold into the sheet) and #277 (tier labels app-wide) both landed, + 4 variants on one spectrum — how much of the sheet's inputs move onto the page: (a) minimal — League+Team pulled to a compact strip, players still via sheet; (b) calculator-style — the page becomes a real add/remove two-column build canvas fed by deck suggestions, League+Team inline, prefs stay in a shorter sheet; (c) maximal — every input (Outlook/Positions/Trade idea/Specific players/Fairness/Lanes/League/Team) always-visible on the page, sheet retired entirely; (d) accordion — same full content as (c) but collapsed to one-line summaries by default, each expanding in place (no modal, no permanent always-on wall). Every frame also carries #272 (Draft/Trade/Free-agents icons 22→28pt, Free Agents borrows the `search` glyph since no dedicated icon exists, Manual-calc-as-button with no league/player refs) and #277 (`TierBadge` chips replacing numeric player values). Closes with a dedicated #279 frame — team/positional aggregate totals on `LeagueSummaryScreen` as pick-equivalent labels ("≈14 firsts") instead of raw numbers, with an explicit caveat that this is NOT the same 8-tier per-asset ladder and what binning work aggregate tiers would still need. Companion doc: `docs/feedback/items/270-inline-trades-home/status.md` |

## Round 5 — 2026-08-09 (#169 position-impact framing, revised)

| Page | Feedback | What it shows |
|---|---|---|
| [`trade-position-impact.html`](trade-position-impact.html) | #169 | Should the trade summary narrate a starting slot's improvement ("your TE goes from X to Y")? Current (shipped #238 `LineupImpactTable` reference frame) + a required fold-in into that same table mocked in two framings the operator asked for head-to-head after rejecting the first pass's raw dynasty-value sentence — A1a positional-rank ("TE21 → TE4") vs A1b tier (real 8-tier ladder labels, "4th → 1 1st", **recommended**) — plus the same two framings on the swipe-deck's one-line hook (C1a/C1b, both explicitly illustrative-only — `starter_impact` doesn't reach the deck at all yet). The standalone "Why this trade" strip variant from the first pass (B1) was abandoned per operator direction and removed. Data-availability audit confirms both framings are buildable from data the app already computes (no new data source), with tier being the cheaper of the two since it reuses an existing call pattern (#277's evener-tier lookup) verbatim; points-per-game framing from the operator's original literal ask remains not computable anywhere in the codebase. Companion doc: `docs/feedback/items/169-position-impact/status.md` |
