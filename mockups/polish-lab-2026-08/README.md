# Polish Lab — 2026-08

Design mockups for the August polish batch. Each page is self-contained HTML
(inline CSS/JS, Chalkline tokens from `docs/design/design-system.md`), showing
**CURRENT** (faithful recreation from the real screen code) beside **PROPOSED**
in ~390px iPhone frames, with a rationale block under each page. Proposed
designs are held to the #205 tenets: simple beats complex, too much info is
worse than none, zero-context UX.

| Page | Feedback items | What it shows |
|---|---|---|
| [`trade-dna-outlook.html`](trade-dna-outlook.html) | #212 · #231 · #206 | Trade DNA panel (TradeFinderHubScreen): CURRENT = passive outlook KV row + "Edit prefs" text link + flat need/deep chips. PROPOSED = bordered Edit button, outlook as four directly-tappable cards each naming its bias in plain words ("Leans young + picks"), two-tier needs chips (flare **STARTER NEED** = lineup hole vs dim **DEPTH** = thin bench, never both on one chip), and a one-line bias receipt above the deck ("Leaning young + picks — you're Rebuilding · Change") reusing the shipped quiet-note construction. |
| [`asset-ideas-layout.html`](asset-ideas-layout.html) | #216 · #209 | Find-a-trade-for-player single-pin flow (TradesScreen + AssetIdeasPanel + TradeCard): CURRENT = full Upgrade/Lateral/Downgrade list expanded above the deck, best card + value bar below the fold; pin board TRADE FOR left. PROPOSED = best suggested trade leads (full card, value bar visible), give column left / receive right everywhere, quiet "More options →" under the trade-away column expanding the grouped list in place (collapsed + expanded frames). **Code fact:** today's `TradeCard.tsx` already renders "YOU SEND" left — the #209 swap applies to the pin board, which renders TRADE FOR left and contradicts the card. |
