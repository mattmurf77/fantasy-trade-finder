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
