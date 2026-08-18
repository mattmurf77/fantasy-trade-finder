# mobile/src/utils/

25 helpers. **No React.** The annotated map — including which values are cross-client contracts and which must stay in lockstep with backend code — is [CLAUDE.md](CLAUDE.md).

| File | One line |
|---|---|
| `anchorRows.ts` | Pick-anchor rung grid; keys are a cross-client enum shared with `backend/server.py:VALID_ANCHORS` |
| `applyJobResult.ts` | #330 generation-epoch guard — a stale in-flight trade search can never overwrite a scoped run |
| `clipboard.ts` | Copy-to-clipboard helper |
| `deepLinks.ts` | The nested route table for `linking`, `handleDeepLink` (cold start, called from `App.tsx`), and `resolveNotificationTarget` (push taps) |
| `espnCookies.ts` | `pickEspnCookies()` — selects the first native cookie bag carrying both `espn_s2` and `SWID` |
| `espnNavPolicy.ts` | `allowEspnNavigation()` — the ESPN WebView's mid-login Safari-escape gate |
| `feedbackBadge.ts` | FeedbackFAB badge math (#184) |
| `firstSessionMoment.ts` | F9 adaptation-moment trigger math (flag `deck.first_session`) |
| `haptics.ts` | Haptic feedback wrappers |
| `inviteSocialProof.ts` | The one formatter deciding whether an invite CTA renders and what it says |
| `leagueUnlocks.ts` | Mutual-match unlock threshold (#265) + the contrarian fold-line copy (#308) |
| `matchesDerive.ts` | #334/#335 — render-layer dismiss suppression + segment/chip counts for Matches |
| `mockPool.ts` | #326/#327 — mock-draft pool filter-then-search composition |
| `playerValue.ts` | 0–10k display value from Elo — inverse of `backend/data_loader.seed_elo_for_value` |
| `rankPresets.ts` | Premium rank-set CSV presets (D-058) — tolerant reader, anchor-column source detection, order-only extraction |
| `ratingPrompt.ts` | App Store rating-prompt eligibility (flag `growth.rating_prompt`) |
| `relativeTime.ts` | "2h ago"-style formatting |
| `sessionRerank.ts` | F4 session re-rank math (flag `deck.session_rerank`) |
| `shareLinks.ts` | Share-package URLs for a built trade |
| `testRouteEntry.ts` | Launch-argument test-route entry (`FTFTestRoute`), used by the operator QA path |
| `tickerWindow.ts` | #322/#325 — the mock-draft ticker's ascending last-`depth` window |
| `tierBands.ts` | Elo/value → tier key + label (8-tier pick ladder, #117); holds the server tier-config cache |
| `tradeCalcMath.ts` | Client-side calculator math for demo mode |
| `tradeText.ts` | Copy-trade text + send-platform resolution (P0-6) |
| `verification.ts` | Account-verification state helpers |

## Rules

- **No React, ever.** No hooks, no components, no `useState`.
- **Two tiers of import discipline, and the file header tells you which one you're in.**
  - *Node-testable* (16) — no runtime import outside `utils/`, so `../../tests/check-*.js` can transpile and run the file under plain `node`: `applyJobResult`, `espnNavPolicy`, `feedbackBadge`, `inviteSocialProof`, `leagueUnlocks`, `matchesDerive`, `mockPool`, `playerValue`, `rankPresets`, `relativeTime`, `sessionRerank`, `tickerWindow`, `tierBands`, `tradeText`, plus `anchorRows` and `firstSessionMoment` (which import only a sibling in this folder). Adding an import from `../api/`, `react-native`, or a package **breaks that file's guard**. Type-only imports are always fine.
  - *Everything else* (9) pulls in `../api/`, `../data/`, or a native module — `clipboard`, `deepLinks`, `espnCookies`, `haptics`, `ratingPrompt`, `shareLinks`, `testRouteEntry`, `tradeCalcMath`, `verification` — and is not node-testable.
- **A cross-client value is a contract.** `anchorRows`'s keys, `tierBands`'s bands, `playerValue`'s curve, and the notification-type glyph set each have a counterpart in `backend/` or in the web/extension clients, listed in [docs/cross-client-invariants.md](../../../docs/cross-client-invariants.md). A copied table here is a silent mis-valuation, not a layout bug — which is exactly why `anchorRows.ts` was extracted the moment a second surface asked the same question.

## Adding a helper

If it is pure math that could regress silently, write it with zero runtime imports and add a matching `../../tests/check-*.js` guard plus an `npm run test:<name>` script. Since D-056 (2026-08-15) those guards are the primary automated evidence for mobile — there is no Maestro or simulator run behind them.
