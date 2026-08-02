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
| [`asset-ideas-layout.html`](asset-ideas-layout.html) | #216/#209 | Best suggested trade leads (value bar visible), give-left/get-right everywhere (fixes the pin board's reversed columns), Upgrade/Lateral/Downgrade behind "More options →" |
| [`asset-ideas-layout-v2.html`](asset-ideas-layout-v2.html) | #216/#209 v2 | Operator iteration: Dynasty Value Swing verdict kept, "More trades" list open by default, idea rows are tappable cards that load into the featured window (live demo), default ‹ Previous-trade chip |
| [`empty-states-progress.html`](empty-states-progress.html) | #229/#230/#234 | Solo-value-first empty states, one unified progress module (position ring + leaguemate meter + honest unlock line), zero-rows collapsed until they have data |
| [`rank-method-consolidation.html`](rank-method-consolidation.html) | #232/#233 | One chooser: Fastest / Most precise / Most control; Quick rank demoted to a follow-on; the rest behind "More ways to rank"; empty-tier CTA reworded "Continue — no QBs this high" |
