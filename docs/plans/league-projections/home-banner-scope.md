# Home playoff-probability banner

Date: 2026-11-07. Direct operator request: show playoff probability on Home and ask whether the user wants to buy or sell a player. No waivers or express lane.

## Analytics scope

Existing `home_tile_tapped` events cover completed actions: `buy`/`sell` with the selected position and actual consensus position band, and `standings` for the details destination. The intermediate position chooser emits no duplicate action. No new data collection.

## Schema and flags

No schema, environment or model-config changes. Uses the new `league.projections` flag and existing Home hub. Disabling projections removes the banner. The weekly saved-result GET is shared with Standings; mounting never queues a forecast. No league/user preferences or outlook are written.

## UX and decision rules

Use the existing outlook band boundaries: at least 65% asks about buying, below 35% asks about selling, otherwise offer both. These are implementation choices consistent with existing bands, not newly asserted user requirements or model policies. The number is explicitly an estimate, with snapshot date and partial-source label. Zero and one are valid estimates, never claims of elimination or clinching.

Use only the active user's roster in the active league, including co-ownership. Missing identity, malformed probability, no run, queued/running refresh, failed refresh, stale or unreadable results must not drive a directional prompt. Retain a labeled last saved estimate where valid; link to Standings for details. Check the weekly due time locally as well as the response state, so an offline cached `current` response cannot remain current past its next slot.

Buy/sell opens an inline QB/RB/WR/TE choice and then the existing position-specific buying/selling list. Use the actual Home position split handlers and events. If player-market data is unavailable, the prompt remains visible but its trading actions are disabled with an explanation. No automatic trade search, offer, model switch or preference mutation.

## Evidence

Unit/structural tests: finite bounds, thresholds, zero/one, weekly expiry, stale/failed/queued/no-run, missing roster, account/league query scope, no generation endpoint and existing buy/sell handoff. TypeScript and test-ID lint required. Code-walk evidence and exact results added before shipping. No simulator or Maestro under D-056.

Manual TestFlight checks: Home displays the active roster's same probability as Projected standings; switch leagues immediately and verify no prior league estimate or chooser remains; test buy/sell position selection and Back; verify large text/VoiceOver; inspect new-league/no-run, stale, failed and offline states. Device visual checks remain unverified until observed.

## Docs and ship gates

API and schema: unchanged. Architecture/component docs: add the read-only Home consumer. Cross-client constants: reuse existing 0.35/0.65 boundaries; no shared policy change. Glossary/HLD: no new domain or architecture. LLD: preserve stored-read and account/league isolation. Decision recorded here: probability prompts are optional navigation, not team strategy assignments. Full exact-head CI, independent review, release evidence and TestFlight delivery required.

## Code walk and verification

`mobile/src/components/home/HomeHub.tsx:350` mounts the banner above status rows, keys it by account/league, resolves the owned/co-owned roster through `findMyRoster`, and hands actions to its existing `onBuy`/`onSell`/`onStandings`. `mobile/src/components/home/HomePlayoffBanner.tsx:33` reads only `getLeagueProjectionBatch`, with the same scoped query key as Standings, guards session switching/platform, and routes position choices through those callbacks. `mobile/src/utils/homePlayoffBanner.ts:6` checks finite probability, own roster, saved-complete state and local weekly expiry before offering a direction.

`node mobile/tests/check-home-playoff-banner.js` passes boundary/state tests plus execution of the actual component with host/query stubs: buyRB, sellWR, neutral stale/error and switching/logged-out/unsupported cases. Existing Home hub and data-free Home-tab guards pass; TypeScript and test-ID lint pass. No physical-device visual/latency result is claimed.
