# Post-trade roster evidence

Internal HTML prototype, 2026-09-04. Open [index.html](index.html) directly, or serve this folder with a static HTTP server. CSS, JavaScript, capture, and fonts are local; no framework, build step, account, API call, or external asset request is needed.

**Question:** after the existing lineup/positional comparison, what additional evidence explains an outgoing starter’s replacement and the depth left on both rosters?

**Integration:** authored by the HTML subagent in its isolated folder, then reviewed and copied intact onto `claude/fleeced-trade-engine-balance-c0c75d`. No production client mount, simulator or hosting. Backend implementation and its stronger availability/capacity checks are documented separately in `docs/plans/post-trade-roster-evaluation/`; this sample is a presentation fixture, not live backend output.

## Current UI inventory — inspected before design

Inspected revision: `606e512cd87f692eced3b92ccadb4f0192ea3449` (worktree HEAD and origin/main, 2026-09-03). Relevant mobile sources are identical to local main `1d0152fc8f70868000c96e53544e680287e9ced8`. The user's primary checkout is on a different historical branch; its filesystem was used only for the specifically requested, updated `mockups/CLAUDE.md`. It was not treated as current mobile behavior.

| Existing surface | Verified current behavior and source |
|---|---|
| Classic trade card | `mobile/src/components/TradeCard.tsx:517`: counterparty header and optional standing-offer/partner-fit/hesitation/consensus context; `:693` send/get columns; `:773` disposition controls; `:894` Edit in calculator; `:917` TradeValueBar; `:935` CardImpactBlock; `:964` optional human-readable reasons. These are existing content, not proposals in this lab. |
| Card lineup impact | `mobile/src/components/CardImpactBlock.tsx:44,112,128`: filter changed caller slots, show up to three, show a `+N more` tail, render before/after names and positional ranks when supplied. Optional projected playoff-band movement follows. Loading, unavailable, and no-content conditions exist. |
| Current full-detail/edit path | No `TradeDetail` component or route was found in the inspected main trees. `TradesScreen.tsx:3667` handles Edit in calculator: inline-home mode loads the package into the existing builder; `:3344`/`:3332` returns a pushed result deck to TradesHome with the package; the fallback navigates to a prefilled TradeCalculator. This prototype does not introduce or reconstruct a nonexistent trade-detail modal. |
| Existing modal/sheet flow | In-place player changes use swap/picker sheets. The card's decline-reason overlay is a `Modal` at `TradeCard.tsx:843`. The host has manager/queue/reason overlays, including the manager picker at `TradesScreen.tsx:8880`; the calculator also has a team-picker Modal. These are specific editing/disposition/selection flows, not a general TradeDetail screen. |
| Full lineup / positional breakdown | `InLeagueCalculator.tsx:1859,1953`: caller's full before/after lineup table, changed tier/rank pairs when supplied, numeric fallback otherwise, unchanged slots, and starting-lineup value total. `:1750` onward contains the two-board verdict; `:236`/`:245` shares the partner’s QB/RB/WR/TE and pick-value summary across layouts. Existing positional totals/ranks are not backup-coverage proof. |
| Existing rationale for both sides | Classic card: partner fit, their likely hesitation, and supplied reasons. `backend/trade_narrative.py:105` describes user fit plus counterparty-window framing. The additive presentation-v2 hero has “Why it works for you” and a counterparty confidence statement at `EndorsedTradeCard.tsx:135,155`; `config/features.json` currently defaults `trades.presentation_v2` to false. This lab does not portray that alternate surface as the classic default or copy its explanations into the new block. |
| Data basis | `backend/server.py:1172` `_starter_impact` derives both teams’ lineup-value deltas and the caller's slot breakdown. `backend/power_rankings.py:53,99,122,136` selects eligible players by dynasty value and aligns interchangeable slots to minimize visible changes. These are not fantasy-point projections or weekly lineup recommendations. |
| Estimated lineup settings | `backend/server.py:25510` `_league_lineup_slots`: ESPN/MFL/Fleaflicker currently use the standard template, plus a SUPER_FLEX slot for the relevant format. They are not observed actual league settings. Sleeper uses the metadata helper. A slot list's presence alone does not justify confirmed roster coverage. |

Line references identify the inspected revision, not the concurrently edited backend branch. No claim is made that the additional backend evidence or client mount already exists.

## Precise additions

One disclosure, **Roster after trade**, proposed immediately after the card's existing impact block, or after the calculator's existing lineup table. It is open for review; collapsing it shows the proposed resting size. Existing value, rationale, trade actions, and playoff presentation are not duplicated or moved.

Inside the disclosure:

1. A two-team summary, followed by **Your team / @northside** controls. Selecting a team changes the replacement, counts, bench names, and limitations together.
2. One expandable outgoing-starter receipt: outgoing player → replacement, replacement's previous location, and any subsequent FLEX replacement. This adds the origin/cascade missing from the concise existing slot comparison.
3. A compact QB/RB/WR/TE table with dedicated-slot fill, a dynasty-value quality warning where relevant, and remaining bench count before → after. A lower-value player can fill a slot without making the starting position equally strong.
4. Disclosures for FLEX occupancy, bench names, and source/settings limitations. Bench counts exclude **all** starters, including FLEX occupants. Each player is selected once.

The disclosure footer always states that injuries, byes, and weekly availability are not checked. No certainty about simultaneous injuries, bye cover, legal roster limits, IR/taxi eligibility, or excluded K/DEF/IDP slots is implied. No opponent private board is shown. The server integration has no weekly schedule input: pure-evaluator support for bye scenarios must not be presented as verified bye coverage. The prototype therefore makes no bye-safe claim. Shadows remain off.

## Three hypothetical scenarios

All player names, roster membership, settings, snapshot time, ranks, and values in the reconstructions/proposal are **sample data**, not current NFL or user-account facts. No live feed is connected. The historical screenshot is separately labeled actual captured evidence.

| Scenario | Your team | @northside |
|---|---|---|
| Covered roster | All 8 supported slots fill. Higgins's dedicated WR place goes to Downs from FLEX; Mooney comes off the bench into FLEX. QB/RB/WR/TE backups: 1/1/1/2. The WR replacement is lower by sample dynasty value. | All 8 supported slots fill. Schultz replaces outgoing Warren at TE, with lower sample dynasty value. Backups: 1/2/2/1. |
| New weakness | Robinson is absent from this sample. All 8 slots still fill, but WR backups decrease **1 → 0**. | Schultz and Fant are absent from this sample. Warren was the only TE; the trade leaves **7/8** filled and **0/1 TE**, with no TE replacement. |
| Incomplete data | The slot template is estimated; Robinson's position/value are unresolved. The known-player preview fills the 8 assumed slots, but coverage is **unconfirmed** and the WR bench result is **Unknown**. | Same estimated template; Schultz's position/value are unresolved. Fant is a provisional TE replacement, but the actual coverage and TE bench count remain **unconfirmed/Unknown**. |

The complete examples assume observed Sleeper slot settings **for the hypothetical league**. The incomplete example represents a non-Sleeper league with estimated settings. This is not a claim that the current backend already returns provenance. The incomplete example withholds a green coverage indicator for both teams even though its estimated slots fill. Its positive bench counts say “listed” and “Total unconfirmed”; they are not claimed as lower bounds under unknown actual settings. Missing entries are excluded from the provisional calculation, never valued at zero.

### Why the existing excerpt and new replacement receipt name different slots

The existing card consumes the server's aligned comparison. With the covered fixture, the main-source alignment produces only **TE: Freiermuth → Warren** and **FLEX2: Higgins → Mooney**. It legally rearranges the before-side WR/FLEX occupants to minimize changes. The source reconstruction runs that exact scan order; it does not invent a three-row current presentation.

The new receipt asks a different, narrower question: who fills the outgoing player's **dedicated position in the value-based allocation**? It keeps dedicated roles visible and stabilizes only repeated slots of the same type, so it exposes **Higgins at WR2 → Downs from FLEX1 → Mooney from the bench**. The chosen starter set and total value are identical; no extra starter or fantasy-point estimate is introduced. The browser shows a design-side explanation of this distinction. Production should consume explicit source evidence, not guess a lineage from only the aligned display rows.

## Capture and design provenance

- Actual before: `screens/mobile/trades/populated.png`, manifest timestamp **2026-08-10T23:42:47+00:00**, copied byte-for-byte into `assets/trades-populated-2026-08-10.png`. SHA-256 for both files: `60007b7ab66fecbe2291c240fa3610772cd6d2e8be4ccb5e385db881623cc8de`.
- `screens/` froze on 2026-08-11 under D-056. No simulator, capture script, or refresh was used. The screenshot is explicitly historical, not mislabeled current.
- Source files moved since capture: latest inspected `TradeCard.tsx` change `1f87ec16` (2026-08-29); `TradesScreen.tsx` `046fa378` (2026-08-31); `CardImpactBlock.tsx` `fa945925` (2026-08-24); `InLeagueCalculator.tsx` `2491d2c7` (2026-08-30). All drawn frames are labeled reconstructions/proposals, not captures.
- Read `docs/design/design-system.md`, `docs/design/components.md`, and `web/style-guide.html`. Reused Archivo, Barlow Condensed, IBM Plex Mono; graphite surface steps; ice ticks/selection; existing semantic and position colors; 1px rules; 2/4/8px radii. No gradients, glass, emoji, decorative shadows, or new UI system.
- Read historical `polish-lab-2026-08/README.md` and `lineup-before-after.html` for the already-shipped #238/#169 lineage, and newer `standing-offer-362`, `more-offers-shop-402`, and `trade-suggestion-redesign` examples for real-capture/reconstruction framing. Those labs were not used as evidence of current app behavior.
- Bundled fonts downloaded from the Google Fonts CSS service and `fonts.gstatic.com`. The three original SIL Open Font License notices, fetched from `google/fonts`'s `ofl/archivo`, `ofl/barlowcondensed`, and `ofl/ibmplexmono` folders, are included in assets. The screenshot and fonts are the only binary assets. License text is unchanged; line endings and trailing whitespace were normalized during integration.

## Verification

Verified 2026-09-04:

- Actual browser inspection in the Codex in-app browser at **1440×1100**, **768×1024**, **390×844**, and **320×740**; source capture renders and the frame has no horizontal overflow at 768px or 320px. Temporary viewport overrides were reset.
- Exercised **all six scenario/team combinations**, including expandable outgoing replacement details. Covered example shows Downs's FLEX origin and Mooney's bench cascade; opponent shows Schultz. New weakness shows WR bench **1 → 0** and the opponent's unfilled TE. Incomplete settings never show the green “Slots filled” state and show unresolved counts as Unknown.
- Verified visible unknown-setting copy and the expanded source/settings disclosure. Checked each team's revised roster evidence rather than only changing tab styling.
- Expanded FLEX occupancy and bench-name lists; verified that listed FLEX players are absent from bench counts. Enter collapses/reopens the main disclosure and correctly hides/shows its contents. Rendered buttons, selects, and summaries met the 44px height floor in the tablet pass.
- Compared every fixture's selected starter IDs and the existing-card before/after alignment against the actual pure functions extracted from `backend/power_rankings.py`: all six combinations matched; selected starter IDs are unique. This validates the illustrative arithmetic, not an API integration.
- Browser console: no errors or warnings during the scenario/interaction pass. Server responses confirmed the local capture and all five font files loaded successfully; the capture hash matches the original. Local links and inline JS parse were checked. No production tests, APIs, accounts, or backend state were exercised.

This is a reviewable presentation prototype. Backend contract, live-data provenance, API wiring, native accessibility, and production behavior remain outside this folder's scope.
