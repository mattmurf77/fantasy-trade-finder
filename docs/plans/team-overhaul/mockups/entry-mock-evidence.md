# Team overhaul entry mock — proposal and evidence

Created 2026-09-06. This is an additive entry-placement proposal for review, not an approved production change. The current local source and configuration ground the surrounding navigation; they do not verify the deployed build.

## Proposed placement and states

- Place a full-width **Team overhaul** entry immediately after the existing Team review entry and before the merged trade builder on the **Acquire** landing.
- With no saved overhaul, **Start overhaul** opens the separate overhaul outlook confirmation.
- With a saved plan, this same location shows **Resume overhaul**, the plan outlook, and a compact response summary. It returns to the saved plan, where the user can inspect package alternatives and choose the next offer.
- The sample assumes the user already completed Team review, so that existing entry is in its current collapsed “Team review · done” state. The new card does not change the regular finder’s outlook; the screenshot intentionally retains “Outlook · Not set” below it.
- The new placement and launch/resume card treatment remain proposals. The owner has approved separate overhaul settings, a saved return surface, and manual execution of fallback offers.

## Current code evidence

Links below are relative to the canonical `docs/plans/team-overhaul/mockups/` directory in the Fleeced repository.

| Evidence | Source |
| --- | --- |
| The `Trades` route is visibly labeled **Acquire**, including its accessibility label. | [TabNav.tsx:749](../../../../mobile/src/navigation/TabNav.tsx#L749) |
| `TradesHome` mounts `TradesScreen`; the earlier launcher hub is explicitly unrouted. | [TabNav.tsx:431](../../../../mobile/src/navigation/TabNav.tsx#L431) |
| The existing Team review entry is deliberately outside the horizontally scrolled mode strip, and opens a separate route. This is the local precedent for the proposed visible card placement. | [TradesScreen.tsx:6954](../../../../mobile/src/screens/TradesScreen.tsx#L6954) |
| A completed Team review collapses to “Team review · done”; an incomplete collapsed state reads “Team review.” | [TeamReviewEntryCard.tsx:115](../../../../mobile/src/components/TeamReviewEntryCard.tsx#L115) |
| With team/player targeting moved into the sheet, the strip omits those chips. Draft can lead it; the calculator label becomes “Real values” when the inline calculator is enabled. | [TradeFinderModeBar.tsx:128](../../../../mobile/src/components/TradeFinderModeBar.tsx#L128) |
| The merged calculator displays its own outlook row followed by League and Team dropdowns. `Anyone` is the real league-wide team-scope label. | [InLeagueCalculator.tsx:920](../../../../mobile/src/components/InLeagueCalculator.tsx#L920) |
| The builder retains its Find a Trade / Clear / confirm action row, with a 50/30/20 layout. | [InLeagueCalculator.tsx:1270](../../../../mobile/src/components/InLeagueCalculator.tsx#L1270) |
| Local configuration enables the inline and merged calculator, pushed results, Team review, and the seasonal Draft tab; suggestion-presentation v2 is off. This grounds the sample’s five-tab bar and absence of Today. | [features.json](../../../../config/features.json) — `trades.team_review`, `calc.merged_layout`, `calc.inline_home`, `calc.results_push`, `draft.tab`, `trades.presentation_v2` |

## Artifacts

- `entry-mock.html` — standalone, offline HTML; four font files embedded from the repository’s installed `@expo-google-fonts` packages. No network requests or backend calls are required.
- `screenshots/entry-launch.png` — first-use entry in context.
- `screenshots/entry-resume.png` — saved-roadmap entry in the same location.
- `entry-capture.cjs` — optional portable capture and interaction checks; requires `playwright` and its Chromium browser. Set `FLEECED_CHROME_PATH` to use another local Chrome executable. No tooling is needed to open the HTML or screenshots.

The primary entry buttons open local previews, and Back returns to the corresponding Acquire state. These previews are navigation illustrations; the main overhaul review contains the full flow.

## Validation

Chrome rendered embedded fonts without network access. Launch and resume previews, two outlook choices, saved-package preview, and Back were checked. Both captures have no horizontal overflow and preserve the five current navigation labels with Acquire active. No browser page errors occurred. Both PNGs were visually reviewed at full size.
