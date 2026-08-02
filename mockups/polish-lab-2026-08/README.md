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
