# Sleeper FA hand-off: deep-link feasibility (2026-10-15)

> Read-only feasibility memo for the operator's top priority (2026-10-15): the in-app "add free agent in Sleeper" links go to the web first, then open the Sleeper app on its home screen instead of the add-player screen with the add and the drop prefilled. This memo answers what the Sleeper iOS app actually accepts and what the best reachable target is. It changes no code. The spec writer continues on branch `plan/sleeper-fa-deeplink`. Every external fact below was read on **2026-10-15**.

## Contents

- [Question](#question)
- [Short answer](#short-answer)
- [Current behavior in FTF](#current-behavior-in-ftf)
- [Evidence](#evidence)
- [Why the operator sees what they see](#why-the-operator-sees-what-they-see)
- [Ranked options](#ranked-options)
- [Recommendation](#recommendation)
- [Device tests](#device-tests)
- [Decisions needed](#decisions-needed)
- [Handoffs](#handoffs)
- [Sources](#sources)

## Question

From the #179 claim sheet (Free Agents and Usage Trends), what is the most specific Sleeper iOS destination FTF can open directly, with no Safari hop? The ideal is Sleeper's add/drop screen with both the FA being added and the player being dropped prefilled. This memo covers:

1. Universal links: which domains and paths Sleeper's AASA claims.
2. Custom URL scheme: whether there is a `sleeper://` scheme and which routes it accepts.
3. Prefill: whether any route or parameter opens add or add/drop with players filled in.
4. The iOS and React Native facts that decide how the fix ships (OTA or a native build).

## Short answer

- **Prefill is not possible through any route we can verify.** No universal link, web route, query parameter, or community tool opens Sleeper's add or add/drop screen with a player filled in. Sleeper's web app does not even read the parameters on FTF's own trade link (F5). The answer is **no for anything verifiable, and unknown for guesses** that only device tests 6–9 could reveal.
- **Root cause, verified (F1, F3):** Sleeper's AASA claims only chat paths (`/topics/*`, `/channels/*`, `/topic/*`, `/message/*`), not `/leagues/*`. So `https://sleeper.com/leagues/<id>/players` opens Safari. For an iPhone user agent, sleeper.com then sends a `302` to a generic Branch link, `https://go.slpr.link/sleeper`. That redirect drops the league id, the path and any query string. The Branch domain *is* claimed by the Sleeper app, so the app opens with no destination, on its home screen. Without the app installed, the same chain ends at the App Store.
- **Best target we can reach:** open the Sleeper app directly with its custom scheme, `sleeper://`. The scheme's existence is **likely** (several independent developers use it, one of them in a native iOS app that checks whether the open succeeded). The **screen it lands on is unknown**. One community note says a `sleeper://leagues/<id>` path is ignored and the app opens on the last-viewed league. This change is **JS-only and OTA-eligible**: `Linking.openURL` with a custom scheme needs no `LSApplicationQueriesSchemes` entry (F7, F8).

## Current behavior in FTF

Verified on `origin/main` @ `678834ab`. Some line numbers in the brief and in `docs/integrations/sleeper.md` are stale. Current locations:

| Surface | Call site | URL opened | What happens on iPhone (per F3) |
|---|---|---|---|
| Claim sheet CTA "Open in Sleeper to claim" (Free Agents + Usage Trends) | `mobile/src/components/ClaimSheet.tsx:141-145` (`openSleeper`), button at `:307-313`, footer copy `:315` | `https://sleeper.com/leagues/${leagueId}/players` | Safari opens → 302 to `go.slpr.link/sleeper` → Sleeper app on its **home screen** (or the App Store if Sleeper isn't installed) |
| Claim sheet hosts | `mobile/src/screens/FreeAgentsScreen.tsx:210`, `mobile/src/screens/UsageTrendsScreen.tsx:665` | (via ClaimSheet) | same |
| Send-in-Sleeper "Open in Sleeper" | `mobile/src/components/SendInSleeperButton.tsx:207-212` (`openInSleeper`) | `https://sleeper.com/leagues/${leagueId}` | same redirect → app home |
| Trade queue deep link | `mobile/src/screens/TradesScreen.tsx:9583-9600` (`buildSleeperUrl`), used at `:6502` | `https://sleeper.com/leagues/<id>/trade?add_receiver_id=…&give_player_id=…&add_player_id=…` | same redirect; **all params dropped**. On desktop there is also no `/trade` route (F5) |
| Web trade link (desktop) | `web/js/app.js:4281-4295` (`_buildSleeperTradeUrl`) | same trade URL | desktop web app has `/leagues/:league/trades` (plural), not `/trade`, and never reads the params (F5) |
| Web share nudge | `web/js/app.js:6189-6205` | bare `sleeper://` | FTF already relies on the bare scheme as a best-effort nudge |

What the claim sheet already knows when the user taps the CTA:
- `row.player_id`: a Sleeper player id, because FTF keys everything on Sleeper ids.
- `row.name`.
- `dropId`: the selected drop, chosen from `dropCandidates.players[].id` and `.name` (`ClaimSheet.tsx:127,253-261`).
- `bid`: the FAAB amount.

None of these reach Sleeper today.

Native config (bare workflow: `mobile/ios/` is the source of truth and `app.json` iOS keys are ignored; see `docs/runbook.md:781-783`):
- `mobile/ios/DTFDynastyTradeFinder/Info.plist:25-34` registers FTF's own schemes (`dtf`, `com.fantasytradefinder.app`). There is **no `LSApplicationQueriesSchemes`** key.
- `DTFDynastyTradeFinder.entitlements` lists only `applinks:fantasy-trade-finder.onrender.com`. That entitlement is for FTF's own links and has no bearing on opening Sleeper.

## Evidence

### Facts we verified (2026-10-15)

**F1 — Sleeper's AASA claims chat paths only.**
- The four origin URLs `https://sleeper.com/.well-known/apple-app-site-association`, `https://www.sleeper.com/…` (301 to the apex), `https://sleeper.app/…` and `https://www.sleeper.app/…` all return the same file (sha256 `b3857c85…2e27fe`, 1315 bytes, `Last-Modified: Tue, 13 Oct 2026`).
- The root variants `/apple-app-site-association` return 404.
- `applinks.details[0].appIDs` = `K258NNHCUC.com.blitzstudios.sleeperbot` and `….sleeperbot.lite`.
- `components`, in order:
  1. Exclude anything with the fragment `#no_universal_links`.
  2. `/topics/*`
  3. `/channels/*`
  4. `/topic/*`
  5. `/message/*`
- There is no legacy `paths` key, and nothing matches `/leagues/*`, `/players/*` or `/`.
- The file also lists `webcredentials` for the same two apps.

**F2 — Apple's CDN serves the same file.** `https://app-site-association.cdn-apple.com/a/v1/sleeper.com` and `…/sleeper.app` are byte-identical to the origin copy (same sha256). So there is no stale-CDN explanation.

**F3 — On an iPhone, sleeper.com league URLs redirect to a generic Branch link.** The chain was traced with curl using an iPhone Safari user agent, and separately the default WKWebView user agent. Neither carried cookies.

```
https://sleeper.com/leagues/<id>/players        → 302  https://go.slpr.link/sleeper
https://go.slpr.link/sleeper                    → 307  https://sleeperbot.app.link/esEa7TDlJN?_p=…
https://sleeperbot.app.link/esEa7TDlJN?_p=…     → 307  https://apps.apple.com/app/sleeper-app/id987367543?_branch_match_id=…
```

- Every other `/leagues…` URL tried redirects the same way: `/leagues`, `/leagues/<id>`, `/leagues/<id>/trades` and `/leagues/<id>/trade?add_receiver_id=…&add_player_id=…`. So do `sleeper.app/leagues/<id>/players` and the WKWebView user agent.
- The redirect target is fixed. **League id, path and query are all discarded.**
- With a desktop Chrome user agent, `/leagues/<id>/players` returns `200` (the web app).
- `https://sleeper.com/players/nfl/4866` and `/topics/123` return `200` on iPhone with no redirect.
- `/login` returns `308` to `/?login=`.

**F4 — Sleeper's Branch domains are universal links for every path.** The AASA at `go.slpr.link`, `sleeperbot.app.link` and `sleeperbot-alternate.app.link` (origin and Apple CDN) claims `"/": "*"` and `"/": "/"` for the same two Sleeper app IDs. It excludes only `$web_only=true` and `/e/*`.

**F5 — Sleeper's desktop web app router.** This comes from the public static bundle `sleepercdn.com/js/bundle-cf8c2e01….js`, which the `/leagues/<id>/players` page loads on desktop.
- It has 46 routes, including `/leagues/:league/players` (`selectedTab:"PLAYERS"`) and `/leagues/:league/trades` (plural).
- It has **no `/leagues/:league/trade` route.**
- The strings `add_receiver`, `receiver_id`, `add_player_id`, `sleeper://`, `deeplink` and `apple-itunes` each occur **0 times**. No route reads a player id from the query string.
- So nothing on Sleeper's web side would prefill a player, and FTF's trade link parameters are almost certainly ignored on desktop as well.
- One caveat: we didn't search lazy-loaded chunks. The bundle is a single 12 MB file, and react-router v3 routes are declared in it.

**F6 — The App Store listing.** iTunes lookup for id `987367543`:
- Bundle id: `com.blitzstudios.sleeperbot`
- Version: 156.0
- Released: 2026-10-15
- Minimum iOS: 16.4
- Seller: Blitz Studios, Inc.

This confirms that the AASA app ID is the shipping app.

**F7 — Apple's documented behavior.** From the Apple Developer docs JSON, read 2026-10-15:
- `canOpenURL(_:)`: an app has to declare the schemes it queries in `LSApplicationQueriesSchemes`. Undeclared schemes always return false. iOS 15+ allows 50 entries, iOS 27+ allows 25. And: *"Unlike this method, the [open] method isn't constrained by the `LSApplicationQueriesSchemes` requirement."*
- Universal links: if no installed app handles one, iOS routes it to the default browser. Other apps can open a universal link with `open(_:options:)` and the target app launches directly.
- The `universalLinksOnly` open option only opens the URL when it is a valid universal link and an app is installed to handle it. Otherwise the open fails.
- Tapping a link to the *same* domain while browsing in Safari stays in Safari. A link to a *different* domain opens the app. That is why the cross-domain hop from sleeper.com to `go.slpr.link` can launch Sleeper.
- Since iOS 14, AASA files are fetched through Apple's CDN.

**F8 — React Native 0.81.5 (FTF's version, `mobile/package.json:149`).**
- In `RCTLinkingManager.mm:90-115`, `openURL` calls `UIApplication openURL:options:completionHandler:`. It resolves `true` on success and **rejects** with "Unable to open URL" when the device can't open the URL. There is no `canOpenURL` pre-check.
- So `Linking.openURL('sleeper://…').catch(fallback)` detects "Sleeper not installed" with **no Info.plist change**.
- `canOpenURL` (`:117-145`) rejects for custom schemes missing from `LSApplicationQueriesSchemes`.

**F9 — Tools already in FTF's binary.**
- `react-native-webview` 13.15.0 (`mobile/package.json:159`), already used by `SleeperConnectScreen`.
- A JS-only clipboard seam, `mobile/src/utils/clipboard.ts`, used by `SendInSleeperButton`.

Neither needs a native build.

### Community evidence (not verified by us; GitHub, read 2026-10-15)

- **C1 — AustinWinstanley/sleeper-companion**, a native iOS widget app.
  - `App/SleeperHandoff.swift` (last commit 2026-09-10) opens bare `sleeper://` via `UIApplication.shared.open` and falls back to `https://sleeper.com/leagues/<id>/matchup` only when `opened == false`.
  - `CLAUDE.md` (2026-10-02) says Sleeper's universal links only cover chat and that the bare scheme "opens the app".
  - This is the strongest evidence that the scheme is registered, because the completion handler would report false otherwise.
- **C2 — tfak23/two-minute-drill** `index.html:1111-1115` (2026-09-13) states that the `sleeper://` scheme "ignores any league path" and drops you on whichever league the app had open last. For that reason it defaults to web links and offers `sleeper://leagues/<id>` as an opt-in.
  - **Conflict:** the same comment says sleeper.com "lands on the exact league every time". F3 contradicts that for a cookieless iPhone user agent. Device test 2 settles it.
- **C3 — TheCiege23/allfantasy-v2-main** `lib/core-app/nativeApp.ts` (2026-10-04) measured Sleeper's AASA on 2026-09-06 with the same result as F1. It deliberately uses no custom scheme because no provider documents one. For contrast, it records that ESPN's AASA claims `/*/players/add`, so ESPN's waiver screen *is* reachable by universal link.
- **C4 — dillonmannion/quantasy.ai** `src/components/waiver/add-to-claims-button.tsx` (2026-02-16), an "Add to Claims" button, uses `sleeper://players/<id>` with a 500 ms web fallback. There is no evidence it lands anywhere specific.
- **C5 — spickworth1991/TradeCalc** (2025-07-29) and **eduardocasati/arquivo-pandeliga** (2026-07-21) use `sleeper://league/<id>` (singular) for "Open in App". Neither says what it lands on.
- **C6 — The help center, Reddit and web search** turned up no Sleeper-published scheme, route list or prefill parameter. No dynasty tool we found (Dynasty Daddy, KTC-style calculators, companion apps) prefills an add in Sleeper. Those that send trades do it by writing through Sleeper's private API, not by deep link.

### Assumptions (unverified; the device tests cover them)

- **A1:** The Sleeper app's associated-domains entitlement includes `go.slpr.link`. We can't read the binary. This is inferred from F4 plus the operator's observed symptom (the app opens after Safari).
- **A2:** `sleeper://` is registered in Sleeper's `CFBundleURLTypes`. Likely, per C1.
- **A3:** The routes the scheme honors are unknown. C2 suggests league paths are ignored.
- **A4:** When FTF calls `UIApplication.open` with a custom scheme, iOS shows no "Open in Sleeper?" confirmation. That prompt is a Safari behavior.
- **A5:** The F3 redirect doesn't depend on being logged in to sleeper.com in Safari.

## Why the operator sees what they see

1. FTF calls `Linking.openURL('https://sleeper.com/leagues/<id>/players')`.
2. `/leagues/*` isn't in Sleeper's AASA (F1), so iOS opens **Safari**. That is the "goes to the web first" step.
3. Sleeper's server sees an iPhone user agent and returns `302` to the generic `https://go.slpr.link/sleeper` (F3). The league, the `players` path and any parameters are discarded at this hop.
4. `go.slpr.link` is a cross-domain universal link claimed by the Sleeper app (F4, F7), so iOS hands it to **the Sleeper app**. The app gets a generic Branch link with no destination, so it opens on its **home screen**.
5. If Sleeper isn't installed, Branch forwards to the **App Store** listing instead.

The same chain breaks `SendInSleeperButton.openInSleeper` and the trade-queue link: the trade link's `add_receiver_id` / `give_player_id` / `add_player_id` never reach the app.

## Ranked options

Status key:
- **verified:** observed directly today.
- **likely:** consistent independent evidence, not yet device-tested.
- **unknown:** no evidence either way, or a guess.

| Rank | Target | Exact URL / pattern | Status | Evidence | What it needs |
|---|---|---|---|---|---|
| (a) | Add/drop screen, add + drop prefilled | **No known route.** Only a speculative guess (device test 9) | **unknown** (no evidence any route exists) | F1 (no league claim), F5 (no web query reads), C1–C6 (no tool does it) | Nothing to build against. The only way to get this result is a write (see Decisions D1), not a link |
| (b) | Add screen, add prefilled | Speculative: `sleeper://players/<player_id>` | **unknown** | C4 uses it with no landing evidence | Device test 8; JS only |
| (c) | Player page in league context | Speculative: `sleeper://leagues/<league_id>/players/<player_id>` | **unknown** | none | Device test 7; JS only |
| (d) | League Players tab, in app | `sleeper://leagues/<league_id>/players` | **unknown** (C2 says league paths are ignored) | C2 | Device test 6; JS only |
| (e) | League home, in app | `sleeper://leagues/<league_id>` or `sleeper://league/<league_id>` | **unknown** for the league; **likely** the app opens on its last-viewed league | C2, C5 | Device tests 4–5; JS only |
| (e′) | **App open, no Safari hop** | `sleeper://` (bare) | **likely** | C1 (native, success-checked), C2, FTF web `app.js:6200`; F7/F8 show no plist entry needed | JS only, OTA-eligible. If Sleeper isn't installed, `openURL` rejects (F8) → fall back |
| (e″) | App open through Sleeper's own Branch link | `https://go.slpr.link/sleeper` | **likely** (it's the link Sleeper's own redirect uses; app home, or the App Store if not installed) | F3, F4, A1 | JS only. **Not recommended:** every FTF tap would count as a click in Sleeper's Branch attribution, and it lands on the same home screen as (e′) |
| (W) | Sleeper's *desktop web* Players tab inside an FTF WebView | `https://sleeper.com/leagues/<league_id>/players` loaded in `react-native-webview` with a desktop user agent | **likely** to load the right league's Players tab; **unknown** whether it's usable at phone width and whether the user is signed in | F3 (desktop UA → 200), F5 (route exists), F9 (WebView already in the binary) | JS only, but it spoofs the user agent. `sleeper-ios-reachability-probe-result-2026-08-12.md` argues against spoofing for API traffic; this case is a visible UI page, but it's still a posture call. The user searches for the player there; no prefill |
| (f) | Today's web hop | `https://sleeper.com/leagues/<league_id>/players` via `Linking.openURL` | **verified broken** on iPhone: Safari → app home (or App Store) | F1, F3 | — |

Any of (b)–(e′) can be paired with a clipboard copy of the player name (F9) and on-sheet instructions such as "In Sleeper: Players → search *Name* → Add → drop *DropName*". This is the honest stand-in for prefill. It's JS-only.

## Recommendation

**Best target: open the Sleeper app directly via `sleeper://`, using the most specific path the device tests prove (status: likely).**

1. **Primary:** `Linking.openURL(<best proven sleeper:// URL>)`. If tests 4–9 show none of the paths route anywhere, use bare `sleeper://`, which still removes the Safari flash.
2. **Not installed (`openURL` rejects, F8):** open `https://sleeper.com/leagues/<id>/players`. On iPhone, Sleeper's redirect sends that to the App Store, which is the correct "get Sleeper" outcome. Alternatively show an explicit "Sleeper isn't installed" message (Decision D2).
3. **Always, before the hand-off:** copy the FA's name to the clipboard and show the add and drop names in the sheet. The sheet already has `row.name` and the selected drop, so the user can finish in about two taps of search.
4. **No `LSApplicationQueriesSchemes` change and no native build** is needed for this chain. Don't call `Linking.canOpenURL('sleeper://')`: without the plist key it rejects (F8). If the spec ever wants `canOpenURL`, add the key to `mobile/ios/DTFDynastyTradeFinder/Info.plist`, not `app.json` (bare workflow), and plan an EAS build.

Be candid with the operator: **unless a device test turns up an undocumented route, this fixes "web first" but not "home screen instead of add screen."** On its own, no deep link can deliver the requested "add + drop prefilled" result. Only a write path can (D1).

## Device tests

The operator or app-manager runs these before the spec is finalized; the results pick the URL in the Recommendation. Record each result in this folder (`device-results.md`), including the actual landing screen.

Setup:
- iPhone on current iOS, with Sleeper v156+ installed and signed in.
- **L** = a Sleeper league id the tester is in.
- **M** = a *different* league the tester is in.
- **P** = the Sleeper player id of a free agent in L.
- **D** = the id of a player on the tester's roster in L.
- Before each scheme test, open league **M** in Sleeper, then swipe Sleeper away. This separates "routed to L" from "reopened the last league."

Two rules for how to open the links:
- **Scheme URLs:** type them into **Safari's address bar** and tap *Open* on the prompt.
- **https URLs:** tap them from **Notes**. Typing a universal link into Safari's address bar never triggers it.

1. **Baseline repro.** Tap `https://sleeper.com/leagues/L/players` in Notes.
   - Expected: Safari flashes, then the Sleeper app opens on home or last league, not L's Players tab.
   - Confirms F3 and A1 on a real device.
2. **Logged-in web.** Sign in to sleeper.com in Safari, then repeat test 1.
   - Record whether Safari now shows the web league page or still redirects. Tests A5 and the C2 conflict.
3. **Scheme exists.** `sleeper://`
   - Expected: the "Open in Sleeper?" prompt appears, then Sleeper opens. Record the screen.
   - If Safari says the address is invalid, the scheme is **not** registered and the Recommendation falls back to (W) or the copy-only flow.
4. `sleeper://leagues/L`: record whether you land on L or on M.
5. `sleeper://league/L`: same check, singular form.
6. `sleeper://leagues/L/players`: record whether L's Players tab opens.
7. `sleeper://leagues/L/players/P`: record whether a player card opens, and in which league context.
8. `sleeper://players/P`: record whether a player card or add sheet opens.
9. **Speculative prefill probe.** `sleeper://leagues/L/players?add_player_id=P&drop_player_id=D`
   - Expected: no prefill.
   - Any add/drop UI with P or D shown would be a major finding.
10. **Cold vs warm.** Repeat whichever of tests 4–8 routed best: once with Sleeper force-quit, once with it backgrounded. Record whether the results differ.
11. **Branch domain.** Tap `https://go.slpr.link/sleeper` in Notes.
    - Expected: Sleeper opens directly with no Safari. Confirms A1. This is informational only, not a candidate target.
12. **Not installed.** Offload or delete Sleeper, or use a second phone without it.
    - (a) Safari address bar `sleeper://leagues/L/players`. Expected: an "address is invalid" error.
    - (b) Notes tap `https://sleeper.com/leagues/L/players`. Expected: the App Store listing.

After the fix ships to TestFlight, add these to the release checklist:

13. With Sleeper installed: Free Agents → Add → claim sheet → **Open in Sleeper to claim**.
    - Expected: Sleeper opens with **no Safari flash**, on the screen tests 4–9 proved.
    - The player's name is on the clipboard (paste it into Sleeper search).
14. Same as test 13, starting from Usage Trends → Add.
15. Roster full: choose a drop in the sheet, tap the CTA. Expected: the sheet showed both the add and drop names before hand-off, and the hand-off still works.
16. With Sleeper not installed: the CTA reaches the chosen fallback (App Store or message per D2). It must never be a silent no-op.

## Decisions needed

- **D1 — The deep-link ceiling vs. a write path.** No verifiable link prefills an add or a drop. The operator's literal ask ("add player screen with the player prefilled, along with the player the user is dropping") can only be met by **executing** the add/drop from FTF. That would mean capturing Sleeper's add/drop or waiver-claim mutation the same way `propose_trade` was captured (`docs/plans/sleeper-write-capture-runbook.md`), behind the same user-token and ToS posture as `trade.send_in_sleeper` (currently `true` in `config/features.json:52`). That is a separate spike with a different risk class. The choice: ship the app-open + clipboard fix now and decide on the write path separately, or wait for the write path.
- **D2 — When Sleeper isn't installed.** Options: let Sleeper's redirect take the user to the App Store (zero code), show an FTF message, or load the desktop web Players tab in a WebView (W, which needs a user-agent spoof).
- **D3 — The (W) desktop-web WebView.** Adopt it as a fallback or not. It lands on the right league's Players tab today, without device tests, but it requires a desktop user-agent spoof and the layout is untested at phone width.
- **D4 — The Branch link (e″).** Recommend **no**; confirm.

## Handoffs

- **Spec writer (this branch):**
  - Spec the JS-only chain from the Recommendation for `ClaimSheet.openSleeper` (`ClaimSheet.tsx:141-145`).
  - Decide whether `SendInSleeperButton.openInSleeper` (`:207-212`) and the trade-queue `buildSleeperUrl` (`TradesScreen.tsx:9583-9600`) adopt the same scheme-first opener. They have the same breakage.
  - Fill the feature scope block (CLAUDE.md gates: this changes user-visible behavior). Include whether the CTA tap gets an analytics event; `ClaimSheet.tsx` emits none today.
  - Leave the target URL as a constant chosen from the device-test results.
- **App-manager / operator:** run device tests 1–12 and record them in `docs/plans/sleeper-fa-deeplink/device-results.md`. Test 3 is the go/no-go for the scheme approach.
- **Trades owner:** FTF's trade deep link (`TradesScreen.tsx:9583-9600`, `web/js/app.js:4281-4295`) is very likely dead weight on **both** platforms.
  - Mobile: the redirect drops everything (F3).
  - Desktop: there is no `/leagues/:league/trade` route, only `/trades`, and nothing reads `add_receiver_id` (F5).
  - The code comment "even if the params are ignored" understates it.
- **Docs:**
  - `docs/integrations/sleeper.md:77-79` has stale call sites (`TradesScreen.tsx:5171,5186`, `SendInSleeperButton.tsx:107-108`, `FreeAgentsScreen.tsx:320`; current locations are above). It should record F1/F3.
  - `docs/feedback/items/179-fa-add-button/status.md` says the hand-off "opens the league's players page (app or web via universal link)". On iPhone that is false.
- **platforms-pm:** if D1 goes to a write path, that's a new capture spike. Don't fold it into this fix.

## Sources

All read 2026-10-15.

- Sleeper AASA (origin): https://sleeper.com/.well-known/apple-app-site-association · https://sleeper.app/.well-known/apple-app-site-association · https://www.sleeper.com/.well-known/apple-app-site-association · https://www.sleeper.app/.well-known/apple-app-site-association
- Sleeper AASA (Apple CDN): https://app-site-association.cdn-apple.com/a/v1/sleeper.com · https://app-site-association.cdn-apple.com/a/v1/sleeper.app
- Branch domains' AASA: https://go.slpr.link/.well-known/apple-app-site-association · https://sleeperbot.app.link/.well-known/apple-app-site-association · https://sleeperbot-alternate.app.link/.well-known/apple-app-site-association
- Redirect traces: `curl -sI -A "<iPhone Safari UA>" https://sleeper.com/leagues/<id>/players` and the follow-on hops in F3
- Sleeper web bundle: https://sleepercdn.com/js/bundle-cf8c2e018e710f218a70cd18b154a1b4.js
- App Store: https://apps.apple.com/us/app/sleeper-fantasy-sports/id987367543 · https://itunes.apple.com/lookup?id=987367543
- Apple docs: https://developer.apple.com/documentation/uikit/uiapplication/canopenurl(_:) · https://developer.apple.com/documentation/uikit/uiapplication/openexternalurloptionskey/universallinksonly · https://developer.apple.com/documentation/xcode/allowing-apps-and-websites-to-link-to-your-content · https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.associated-domains
- React Native 0.81.5 `RCTLinkingManager.mm`: https://github.com/facebook/react-native/blob/v0.81.5/packages/react-native/Libraries/LinkingIOS/RCTLinkingManager.mm
- Community: https://github.com/AustinWinstanley/sleeper-companion (`App/SleeperHandoff.swift`, `CLAUDE.md`) · https://github.com/tfak23/two-minute-drill (`index.html`) · https://github.com/TheCiege23/allfantasy-v2-main (`lib/core-app/nativeApp.ts`) · https://github.com/dillonmannion/quantasy.ai (`src/components/waiver/add-to-claims-button.tsx`) · https://github.com/spickworth1991/TradeCalc · https://github.com/eduardocasati/arquivo-pandeliga
- Prior FTF research: `docs/plans/competitor-top20/12-send-to-sleeper-share.md` (the FR1 spike it called for was never filed; this memo covers the navigation half) · `docs/feedback/items/179-fa-add-button/status.md` · `docs/plans/sleeper-write-capture-runbook.md` · `docs/plans/auth-multiplatform-plan-2026-06-11.md` Part C · `docs/feedback/items/239-invite-universal-links/status.md` · `docs/runbook.md:781-795`
