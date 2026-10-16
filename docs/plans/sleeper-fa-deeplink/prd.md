# Sleeper hand-off: open the Sleeper app directly — PRD (2026-10-15)

> The spec slice for the operator's top priority of 2026-10-15. It covers every place FTF hands the user to Sleeper:
> - the claim sheet's "Add in Sleeper" (Free Agents and Usage Trends);
> - the send-a-trade feature's links: the Send-in-Sleeper hand-off and the trade queue's Send All. The send-a-trade path is the one the operator actually reproduced (scope change, same day).
>
> Today each of these goes through Safari and lands on Sleeper's home screen. The evidence base is [feasibility.md](feasibility.md). The feature gates are in [scope.md](scope.md). Line numbers are verified against `origin/main` @ `678834ab`. This document specifies behavior and changes no code. The build starts only after the pre-build device tests are recorded and D2 is decided.

## Contents

- [1. Problem and operator words](#1-problem-and-operator-words)
- [2. Strategy owner and hypothesis](#2-strategy-owner-and-hypothesis)
- [3. Surfaces in scope](#3-surfaces-in-scope)
- [4. Expected behavior](#4-expected-behavior)
- [5. Out of scope](#5-out-of-scope)
- [6. Acceptance criteria](#6-acceptance-criteria)
- [7. Evidence plan (D-056)](#7-evidence-plan-d-056)
- [8. Reviews needed](#8-reviews-needed)
- [9. Sequencing and dependencies](#9-sequencing-and-dependencies)
- [10. Decisions needed](#10-decisions-needed)
- [11. Handoffs](#11-handoffs)

## 1. Problem and operator words

The operator, 2026-10-15, verbatim:

> "Primary priority is to fix links that direct users to add FAs in sleeper from the app. Right now they go to the web first, and then open the sleeper up on the home screen rather than the add player screen with the player prefilled (along with the player the user is dropping)"

The operator's clarification the same day, verbatim (relayed by `head-product`):

> "It opens from the send a trade feature. That's the one we tested it on. Have an eng research all external links to compare differences to ensure a consistent experience"

So the send-a-trade links are in scope alongside the claim sheet, and they are the path the operator reproduced. A separate `head-eng` inventory covers every other external link (§8, Pending).

**Root cause** (verified; [feasibility.md § Why the operator sees what they see](feasibility.md#why-the-operator-sees-what-they-see), F1, F3, F5):
- Sleeper's AASA claims only chat paths. Every `https://sleeper.com/leagues/...` URL FTF opens therefore lands in Safari. On an iPhone user agent, Sleeper then `302`s to the generic Branch link `go.slpr.link/sleeper`, which drops the league, the page and every parameter (including FTF's `/trade?add_receiver_id=…`). That link opens the app on its home screen, or the App Store if Sleeper isn't installed.
- Sleeper's desktop web app has no `/leagues/:league/trade` route and reads none of those parameters (F5).

**What this fixes and what it doesn't.**
- **Fixed: "web first."** The app opens directly through `sleeper://`, with no Safari hop.
- **Not fixed: "prefilled".** No verifiable route prefills an add, an add/drop, or a trade proposal in Sleeper (feasibility, Short answer, F5). This PRD ships an honest stand-in on each path instead:
  - the relevant names (the free agent, or the trade summary) go on the clipboard;
  - FTF spells out the steps to take in Sleeper.
- The only way to fully meet the literal add/drop ask is for FTF to execute the add/drop itself. That is D1, not this build. For trades, FTF already executes the proposal through Send in Sleeper (`propose_trade`) when the account is linked. The hand-off covered here is the fallback.

## 2. Strategy owner and hypothesis

- **Owner:** `platforms-pm` (operator top priority, 2026-10-15). Spec by the platforms-pm spec worker under `/pm-technical`.
- **Hypothesis:** every Sleeper hand-off should open the Sleeper app directly, at the deepest screen Sleeper honors, with the right names on the clipboard and the remaining steps named in FTF. If it does, a user can finish an add or a trade proposal in Sleeper with one search and a paste. Today they get a Safari flash and a home screen with no context.
- **How we'll know:**
  - TestFlight steps 13–20 pass on a device. Under D-056, that is the only runtime evidence.
  - If `analytics-lead` grants the event, `sleeper_handoff_resolved.outcome` shows `app` for testers who have Sleeper installed. With the operator plus about 2 testers, that is a smoke signal, not a metric.

## 3. Surfaces in scope

| # | Surface | Call site (`origin/main` @ `678834ab`) | Today | Change |
|---|---|---|---|---|
| 1 | **Claim sheet CTA** "Open in Sleeper to claim" | `mobile/src/components/ClaimSheet.tsx:141-145` (`openSleeper`); button `:307-313` (testID `fa-claim.open-sleeper`); footer `:315` | `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`)`; rejection swallowed | Call the shared helper with `target: 'add'`. Add the steps block (§4.2). |
| 1a | ↳ host: **Free Agents** | `mobile/src/screens/FreeAgentsScreen.tsx:81-88` (`onAdd`, Sleeper-gated); `:208-219` (ClaimSheet mount) | Has had no `Linking` call of its own since the 2026-10-10 ClaimSheet extraction (`ClaimSheet.tsx:38-43`). The `:320` reference (`docs/integrations/sleeper.md:79`, and the brief) is stale; it now points at a stylesheet. | Logic unchanged; the fix arrives through ClaimSheet. Passes `leagueName`, plus `surface="free_agents"` if the §1 event is granted. Guard S1 keeps this file free of direct Sleeper URLs. |
| 1b | ↳ host: **Usage Trends** | `mobile/src/screens/UsageTrendsScreen.tsx:270-280` (`doAdd` switches to the claim league first); `:665-673` (ClaimSheet mount) | Same CTA | Same as 1a. `leagueName` comes from the session `league_name` (`:94`), which is the claim league after `switchTo`. |
| 2 | **Send-in-Sleeper hand-off** (send a trade) | `mobile/src/components/SendInSleeperButton.tsx:208-212` (`openInSleeper`), reached from `onPress` `:405-408` | `https://sleeper.com/leagues/${leagueId}` (numeric id) or `https://sleeper.com`; rejection swallowed | `openInSleeper` calls the helper with `target: 'trade'` and the trade summary for the clipboard, after a steps confirm (§4.3). The real send, connect flow, copy affordance and `sleeper_send_attempted` are untouched. |
| 3 | **Trade queue Send All** (send a trade; flag `trades.queue_2k`) | URL built by `buildSleeperUrl` (`mobile/src/screens/TradesScreen.tsx:9589-9600`) and snapshotted at enqueue (`:6502`). Opened by `useTradeQueue.sendAll` (`mobile/src/state/useTradeQueue.ts:123-151`): `canOpenURL` `:130`, `openURL` `:132`, alert `:137`. | One `https://sleeper.com/leagues/<id>/trade?add_receiver_id=…&give_player_id=…&add_player_id=…` per queued trade, 500 ms apart. On iPhone each one goes Safari → Sleeper home and every param is lost (F3); desktop has no such route (F5). | `sendAll` makes **one** hand-off through the helper (`target: 'trade'`), with every queued trade summary on the clipboard. `canOpenURL` is dropped. `buildSleeperUrl` and the `sleeper_url` snapshot go away. Persisted queues may still carry `sleeper_url` and it is never opened (§4.3). |

**Still out of scope:** web `_buildSleeperTradeUrl` (`web/js/app.js:4281-4295`, Send All at `:4298-4320`). It sits behind the same dark flag and is a browser surface with different mechanics. It goes to the `head-eng` all-external-links inventory (§8, Pending).

### 3.1 Send-a-trade code-walk: every Sleeper link, and the state that reaches it

This covers every way the send-a-trade feature (`SendInSleeperButton` on the deck, Matches and the calculator, plus the trade queue) can leave FTF for Sleeper, and the UI state that reaches each one.

| # | Link / opener | file:line | URL opened | UI state that reaches it | Live on `main`? |
|---|---|---|---|---|---|
| A | `openInSleeper` | `SendInSleeperButton.tsx:208-212`, called at `:405-407` | `https://sleeper.com/leagues/<id>`; `https://sleeper.com` when the id isn't numeric or is empty | The flag is on, the league resolves to Sleeper (fail-open for an uncached id), and the mount has an **empty `leagueId` or `theirUserId`**. Mounts: deck `TradesScreen.tsx:8766-8770` (`topCard`); Matches `TradeCard.tsx:983-986` (match) and `:1005-1008` (awaiting), fed by `matchToTradeCardShape` / `awaitingToTradeCardShape` (`MatchesScreen.tsx:1644-1674`, `:1680-1708`). The calculator never reaches it, because it renders only with `opponentId` (`InLeagueCalculator.tsx:1486`). | **Yes**, through an edge state. The client normalizers turn a missing id into `''` (`api/trades.ts:162,167`; `:688`, `:759` for `partner_id`), but the server payloads populate those ids (`server.py:14420,14424`; `database.py:9855,10069`). **No deterministic UI trigger was found.** |
| B | Trade queue Send All | `TradesScreen.tsx:6511-6516` → `useTradeQueue.ts:123-151` | `https://sleeper.com/leagues/<id>/trade?…`, once per queued trade | `trades.queue_2k` on: Queue button (`TradesScreen.tsx:8726-8729`) → ≥1 queued → Send All (`:9244` chip, `:9299` sheet) | **No.** `trades.queue_2k` has been `false` in `config/features.json:14` since 2026-04-19, and it isn't in `LAUNCHED_FLAG_DEFAULTS` (`useFeatureFlags.ts:45`), so the Queue and Send All controls don't render |
| C | Connect / reconnect / verify | Alerts `SendInSleeperButton.tsx:427-436` (not linked), `:271-280` (`sleeper_not_linked` / `sleeper_expired`), `:284-292` (`verification_required`) → `goConnect` `:215-218` → `SleeperConnect` → `SleeperLoginCapture.tsx:48-56` | **In-app WebView** at `https://sleeper.com/login` (`:6`). There is no `Linking.openURL`; `originWhitelist={['https://*']}` keeps https inside the WebView | Not linked, token expired, or session unverified, then tapping Send in Sleeper | **Yes.** It is common for testers, but by code nothing here opens the Sleeper app or Safari |
| D | Flag off | `:487` returns `null` | none | `trade.send_in_sleeper` false (it is `true`, `features.json:52`) | — |
| E | Non-Sleeper league | `:493-508` reason + **Copy trade** | none (MFL/ESPN twins open `myfantasyleague.com` / `fantasy.espn.com`, `SendInMflButton.tsx:86`, `SendInEspnButton.tsx:89`, which go to the `head-eng` inventory) | ESPN/MFL with their send flags off, or Fleaflicker | — |
| F | After a successful send | `:243` alert "Trade sent" / "Check your Sleeper app for the pending offer." (OK only) | **none** — there is no "view in Sleeper" link | A linked send that succeeds | — |
| G | Failed send | `:270-339` error alerts | none (the two reconnect branches route to C) | Any send error | — |

**Most likely operator path: A, `openInSleeper` (`SendInSleeperButton.tsx:208-212`, via `:405-407`). Likely, not proven.**
- It is the only live send-a-trade call that hands a `sleeper.com/leagues` URL to `Linking.openURL`. Its verified result (F3) is exactly the reported symptom: Safari first, then the Sleeper app on its home screen.
- B gives the identical symptom but is dark on `main`.
- C shows Sleeper's *web* login inside FTF. That could read as "the web first", but no FTF code path from it opens the Sleeper app.
- **What doesn't fit:** A needs a card whose league or opponent id came through empty, and the code-walk found no deterministic way to produce one. So either some payload reaches the client without those ids, or the operator's build or state differs from `main`. Pre-build step **R0** settles it (§7.3).
- This also corrects the earlier note: A still has no deterministic trigger, and C is deterministic but never calls `Linking`.

### 3.2 The shared helper

One module, so every surface behaves the same: **`mobile/src/utils/sleeperHandoff.ts`** (new). The shape is kept open for the `head-eng` inventory: if that recommends one cross-platform pattern (for example `openPlatformApp(platform, target)`), this becomes its Sleeper implementation with no call-site change beyond the import.

```ts
export type SleeperTarget = 'add' | 'trade' | 'league';

// Rungs proven on a device (device-results.md), per target, highest first.
// 'bare' is always last. Ships as { add: ['bare'], trade: ['bare'], league: ['bare'] }
// unless device tests prove deeper rungs.
export const SLEEPER_PROVEN_RUNGS: Readonly<Record<SleeperTarget, readonly SleeperRung[]>>;

// Pure. Returns the highest proven rung URL for the target that the inputs support. Never https.
export function sleeperAppUrl(t: { target: SleeperTarget; leagueId?: string; playerId?: string }): string;

// Copy (optional) → open the scheme → on rejection, run the D2 fallback.
export function openInSleeperApp(t: {
  target: SleeperTarget;
  leagueId?: string;
  playerId?: string;        // add target only
  clipboardText?: string;   // the FA's name, or the trade summary
  surface?: 'free_agents' | 'usage_trends' | 'send_button' | 'trade_queue'; // only if the §1 event is granted
  hasDrop?: boolean;        // ditto; add target only
}): Promise<'app' | 'not_installed'>;
```

Behavior, in order:
1. If `clipboardText` is set, call `copyText(clipboardText)` (`mobile/src/utils/clipboard.ts`, JS-only) **before** opening. Once Sleeper is in the foreground, FTF's JS may be suspended, so the copy can't wait.
2. Build the URL with `sleeperAppUrl`. A missing or non-numeric `leagueId` never yields a league rung.
3. `await Linking.openURL(url)`. If it resolves, the outcome is `app`. If it rejects, the outcome is `not_installed` and the D2 fallback runs (§4.4). The rejection is never swallowed.
4. If the event is granted, emit `sleeper_handoff_resolved` once (scope §1).
5. **Never** call `Linking.canOpenURL` (it rejects without the plist key, F8), pass an `https://sleeper.com/...` URL as the primary target, or touch native config.

The module is impure: it uses react-native `Linking` and `Alert`, `./clipboard`, and `../api/events` if the event is granted. The guard executes it under node with stubs (§7.1). Add its entry to `mobile/src/utils/CLAUDE.md` and `README.md`.

## 4. Expected behavior

The user taps a Sleeper hand-off: the claim sheet's CTA, or a send-a-trade link. Sleeper opens **directly**: no Safari, no "Open in Sleeper?" prompt (A4; that prompt is a Safari behavior). It lands on the deepest screen device tests proved for that target. The relevant names are already on the clipboard, and FTF has already listed the steps.

### 4.1 The target ladder

Device tests **fix each target's rung before build** (§7.3). Where nothing deeper proves out, the build ships bare `sleeper://`. Ranked from best to floor:

**Add target** (claim sheet; from feasibility § Ranked options):

| Rank | Rung id | Target | URL pattern | Needs | Status today | Proven by |
|---|---|---|---|---|---|---|
| (a) | — | Add/drop screen, add **and** drop prefilled | **no known route** | — | unknown; no evidence any route exists | test 9 (probe only). A pass is a major finding: escalate to `platforms-pm` before build |
| (b) | `add` | Add screen, add prefilled | `sleeper://players/<P>` (speculative) | `playerId` | unknown | test 8 shows an **add** sheet for P |
| (c) | `player` | Player card in league context | `sleeper://leagues/<L>/players/<P>` (speculative) | `leagueId` + `playerId` | unknown | test 7 lands on P **in L** |
| (d) | `players_tab` | League **Players** tab | `sleeper://leagues/<L>/players` | `leagueId` | unknown (C2: league paths may be ignored) | test 6 |

**Trade target** (send-a-trade; the memo has no trade-specific candidate beyond F5's web routes, so these mirror the web routes and FTF's current path):

| Rank | Rung id | Target | URL pattern | Needs | Status today | Proven by |
|---|---|---|---|---|---|---|
| (t-a) | — | Propose-trade screen, opponent and assets prefilled | **no known route**. Sleeper's web app reads none of FTF's params (F5) | — | unknown; no evidence | T3 (probe only). A pass is a major finding: escalate before build |
| (t-b) | `trade` | A propose-trade screen in L | `sleeper://leagues/<L>/trade` (FTF's current path, as a scheme; speculative) | `leagueId` | unknown; the web has no such route (F5) | T2 |
| (t-c) | `trades_tab` | League **Trades** tab | `sleeper://leagues/<L>/trades` (mirrors the web route `/leagues/:league/trades`, F5) | `leagueId` | unknown | T1 |
| — | — | Opponent's user or roster page | **no candidate in the memo**, so none is invented | — | — | — |

**Shared floor** (every target):

| Rank | Rung id | Target | URL pattern | Needs | Status today | Proven by |
|---|---|---|---|---|---|---|
| (e) | `league` | League home | `sleeper://leagues/<L>` or `sleeper://league/<L>` (whichever form passed) | `leagueId` | unknown for L; likely the last-viewed league | test 4 or 5 lands on **L, not M** |
| (e′) | `bare` | App open, no Safari hop | `sleeper://` | — | **likely** (C1, C2; FTF web already uses it at `app.js:6200`) | test 3. **The floor and the default.** |

Rules:
- A rung counts as **proven** only if its test lands on the stated screen **in league L**, after league M was opened last, **both** cold and warm (test 10, which covers trade rungs too). Landing on M means Sleeper reopened the last league, which is a fail for every league rung.
- `SLEEPER_PROVEN_RUNGS` lists exactly the PASS rows in `docs/plans/sleeper-fa-deeplink/device-results.md`, per target, with `league` (if proven) and `bare` last. Guard S10 cross-checks the two.
- Each call uses the highest proven rung for its target that its inputs support.
  - The claim sheet has `leagueId` and `playerId`.
  - Send-in-Sleeper has at most `leagueId`; in state A it may have none.
  - Send All has the queue's `leagueId`.
- **If test 3 fails** (Safari says the address is invalid), the scheme approach is dead for every target. The build does not start, and the spec returns to `platforms-pm` (D3 or a copy-only flow).

### 4.2 Claim-sheet stand-in for prefill: clipboard + on-sheet steps

1. The CTA **copies the free agent's name** (`row.name`) before the open (§3.2 step 1). The sheet says so up front.
2. A **steps block** (testID `fa-claim.steps`) sits between the drop section and the CTA, and updates live:

| Must show | When | Source |
|---|---|---|
| The add: the free agent's name | always | `row.name` |
| The drop: the selected player's name | a drop is selected (`dropId != null`) | `candidates.find(c => c.id === dropId)?.name` (`ClaimSheet.tsx:127,135`) |
| The league, by name | the shipped rung doesn't guarantee the league (`bare`, or a rung that never landed on L) | new optional `leagueName` prop from the hosts. Without it, the user may add in **the wrong league**: the bare scheme reopens the last-viewed league (C2). |
| The bid | FAAB league with a bid entered | `bid` (`:126`); design-lead may drop it |
| That the name was copied | always | static |

Draft copy (**wording, layout and placement belong to `design-lead` and `ux-lead`**):
- `bare` / `league`: "In Sleeper: open **{League}** → Players → search **{Name}** → Add → drop **{Drop}**"
- `players_tab`: "In Sleeper: search **{Name}** → Add → drop **{Drop}**"
- `player` / `add`: "In Sleeper: Add → drop **{Drop}**"
- Clipboard line: "We'll copy {Name} so you can paste it into search."
- With no drop, the "→ drop" segment is omitted.

Sleeper's real button labels ("Add" / "Claim" / "Drop") are captured in the device session (§7.3), so the copy matches the app.

### 4.3 Send-a-trade stand-in: clipboard + steps before the open

No verified route prefills a trade (F5), so the trade hand-offs get the same treatment as the claim sheet.

**Send-in-Sleeper hand-off (surface 2).** `openInSleeper` currently fires straight from the button tap, and there is no sheet to put steps on. So:
1. **First, a steps confirm.** It uses an `Alert`, the component's existing pattern (`SendInSleeperButton.tsx:427-436`). For example: title "Finish in Sleeper"; body "We'll copy this trade. In Sleeper: open **{League}** → **@{Opponent}**'s team → Propose trade → add **{Give}** for **{Get}**."; buttons **Cancel** / **Open Sleeper**.
2. **Open Sleeper** calls `openInSleeperApp({ target: 'trade', leagueId, clipboardText })`.
3. `clipboardText` reuses the existing formatter, `formatTradeForClipboard({ giveNames, giveIds, receiveNames, receiveIds, opponentUsername, leagueName })` (`mobile/src/utils/tradeText.ts:87-108`, already pinned by `check-trade-text.js`): "Trade proposal — League / To: @opponent / I send: … / I get: …". There's no new formatter.
4. In state A the opponent or league may be the very thing that's missing. The formatter already drops empty lines, and the steps must degrade the same way: "open your league → the leaguemate's team…". design-lead owns the wording.

**Trade queue Send All (surface 3; dark today).** Opening N Sleeper links 500 ms apart makes no sense once each open is an app switch: after the first, FTF is backgrounded and its JS may stop. So:
1. Send All becomes **one** hand-off. A steps confirm (same pattern) lists the N trades. The clipboard holds every queued summary, joined.
2. Then `openInSleeperApp({ target: 'trade', leagueId })`, and the queue clears as it does today (`useTradeQueue.ts:150`).
3. `QueuedTrade` gains an optional `opponent_username` at enqueue, so summaries can name the opponent. It loses `sleeper_url`, and `buildSleeperUrl` is deleted. Queues persisted under `ftf_trade_queue_<user_id>` may still carry `sleeper_url`; `sendAll` must ignore it and **never open it**.
4. `canOpenURL` is dropped (guard S12).

`trades-pm` reviews this queue behavior (§8). Lighting `trades.queue_2k` stays their call and is not part of this build.

### 4.4 When Sleeper isn't installed (decision D2)

`Linking.openURL('sleeper://…')` rejects when no app handles the scheme (F8). The helper then runs one fallback, the same on every surface and target:

| Option | What the user sees | Cost | Notes |
|---|---|---|---|
| (i) Open the https league link | Safari flash → Sleeper's Branch redirect → **App Store** listing (F3, test 12b) | zero UI | This is the very Safari hop the operator complained about, just ending at the App Store. It also counts as a Branch click in Sleeper's attribution (the D4 objection). |
| **(ii) In-app message with an App Store button (recommended)** | Alert "Sleeper isn't installed" / "Get the Sleeper app to finish this in your league." / **Cancel** · **Get Sleeper** → `https://apps.apple.com/app/id987367543` (id verified, F6). The clipboard copy has already happened. | one `Alert` | No Safari and no Branch click, and it's honest. It follows the `explainNoAdd` pattern. Test 12c verifies the target. Copy is design-lead's. |
| (iii) Desktop-web WebView (W) | Sleeper's desktop web page inside FTF | UA spoof; untested at phone width | This is D3. Not recommended. |

**Recommendation: (ii).** It never fails silently (TestFlight 16, 20).

### 4.5 What doesn't change

- ESPN, MFL, Fleaflicker and local leagues on the claim sheet keep `NO_ADD_REASON` byte for byte (`ClaimSheet.tsx:67-95`), along with `explainNoAdd` (`:100-103`) and `resolveAddPlatform` (`:58-65`).
- Claim preparation is unchanged: bid, over-budget disable (`:311`), drop selection, untouchables note.
- **The real trade send is unchanged.** That covers status check → confirm → `validateTradeSend` → `doPropose` (`SendInSleeperButton.tsx:381-438`, `:220-342`, `:348-379`), plus the connect/verify WebView (row C), every error alert (row G), and the success alert (row F). None of it opens a link today and none will.
- `SendInMflButton` / `SendInEspnButton`, the non-Sleeper copy affordance, and `sleeper_send_attempted` are unchanged.
- Web and the extension are unchanged.

## 5. Out of scope

- **D1, executing the add/drop from FTF** through Sleeper's private API. This is the only route to the operator's literal add/drop end state. It is a **new Sleeper write surface** (Sleeper's only FTF write today is `propose_trade`, behind `trade.send_in_sleeper`). Under the platform risk register (PR #345, `.claude/skills/pm-partnerships/references/platform-risk-register.md`), that makes it an **operator yes/no through `head-product`**, and it must clear the register's write-feature gate. Escalation E2 is open (Sleeper Terms revised 2026-10-06, §11.1 and §11.3). If the answer is yes, it becomes a separate `platforms-eng` capture spike (precedent: `docs/plans/sleeper-write-capture-runbook.md`) and is never folded into this build.
- **D3, a desktop-UA WebView**, and **D4, Sleeper's Branch link** as a target.
- **Web `_buildSleeperTradeUrl` and web Send All** (`web/js/app.js:4281-4320`): these go to the `head-eng` inventory.
- **Every non-Sleeper external link** (ESPN/MFL sends, Settings/legal links, the draft room's `deep_link`, and so on): these also go to the `head-eng` inventory (§8, Pending).
- **Lighting `trades.queue_2k`**: that is `trades-pm`'s call.
- **An ESPN waiver-screen universal link** (C3, unverified).
- **`LSApplicationQueriesSchemes` / `canOpenURL`**, or any native or `app.json` setting change.
- **Android**: iOS is the only shipped client.
- **FAAB, drop-candidate, roster-capacity, trade-generation or backend payload changes.**

## 6. Acceptance criteria

Each criterion can be answered pass/fail by a guard, a test, a diff check or a checklist step.

| AC | Criterion | Verified by |
|---|---|---|
| AC-1 | No `sleeper.com/leagues` URL is passed to `Linking.openURL` from `ClaimSheet.tsx`, `FreeAgentsScreen.tsx`, `UsageTrendsScreen.tsx`, `SendInSleeperButton.tsx`, `TradesScreen.tsx` or `useTradeQueue.ts`. None of them contains a direct `Linking.openURL` to a Sleeper host. | guard S1, S11 |
| AC-2 | The claim-sheet CTA, `SendInSleeperButton.openInSleeper` and `useTradeQueue.sendAll` all call `openInSleeperApp` from `utils/sleeperHandoff`. There is no second implementation. | guard S2, S11 |
| AC-3 | The helper's first (and, on success, only) `openURL` argument starts with `sleeper://`. | guard S3 (executed) |
| AC-4 | When the scheme open rejects, the D2 fallback runs and the helper resolves `not_installed`. It never resolves with nothing opened and nothing shown. | guard S4 (executed); TestFlight 16, 20 |
| AC-5 | No `Linking.canOpenURL` in the helper or in `useTradeQueue.ts`. No native config change: no `Info.plist` key, no entitlement, no `LSApplicationQueriesSchemes`, and no `app.json`/`eas.json` setting beyond the routine version bump. | guard S5, S12; PR diff |
| AC-6 | With `clipboardText`, `copyText` is called with it **before** `openURL`. | guard S6 (executed) |
| AC-7 | `sleeperAppUrl` returns the highest proven rung for the target that the inputs support. A non-numeric or missing `leagueId` never yields a league rung. `'trade'` never resolves to an add rung, and vice versa. It never returns `https://`. `bare` is the floor. | guard S7, S13 (executed) |
| AC-8 | `SLEEPER_PROVEN_RUNGS` matches the PASS rows in `device-results.md` for each target. | guard S10; code-walk |
| AC-9 | The claim sheet renders `fa-claim.steps` with the FA's name, the drop name when picked, and the league name at a rung that doesn't guarantee the league. | guard S8; TestFlight 13, 15 |
| AC-10 | The ESPN/MFL/Fleaflicker/local claim paths are byte-identical to `678834ab`. | guard S9; diff check |
| AC-11 | `fa-claim.open-sleeper`, `trades.send-sleeper-btn`, `send-in-sleeper.copy` and `send-in-sleeper.unavailable` keep their testIDs. `fa-claim.steps` is added. `testid-lint.sh` is green. | CI |
| AC-12 | `web/js/app.js` is not modified by this build. | PR diff |
| AC-13 | If the §1 event is granted, it is registered and classified **in the same commit** as its emitter, and fires once per hand-off. | backend pytest; guard S3/S4 stubs count `track` calls |
| AC-14 | On device, Sleeper opens with no Safari flash at the proven rung, the copied text pastes, and not-installed reaches the fallback. | TestFlight 13–16, 19–20 |
| AC-15 | `docs/integrations/sleeper.md:77-79` and the #179 status claim are corrected (scope §4). | docs review |
| AC-16 | Send-in-Sleeper's hand-off shows the steps confirm, then copies `formatTradeForClipboard(...)` output before opening with `target: 'trade'`. Cancel opens nothing. | guard S14; TestFlight 19 |
| AC-17 | `sendAll` makes exactly **one** `openURL` call regardless of queue length. It never opens a persisted `sleeper_url`. It still clears the queue afterwards. | guard S11 (text) + S15 (executed) |
| AC-18 | The linked send path (`doPropose`), the connect/verify WebView and the success/error alerts contain no `Linking` call, before or after. | guard S16; TestFlight 17, 18 |

## 7. Evidence plan (D-056)

No Maestro, no simulator, no captures. The evidence is a structural guard (partly executed), a code-walk, a pre-build device gate and a post-ship TestFlight checklist.

### 7.1 Structural guard: `mobile/tests/check-sleeper-handoff.js`

- The guard has no dependencies beyond the project's `typescript`. It follows the `check-offer-prefill-330-unit.js` idiom: transpile `src/utils/sleeperHandoff.ts` (and, for S15, `src/state/useTradeQueue.ts`), then run them with a `require` shim:
  - `react-native`: a `Linking` stub that records calls and resolves or rejects per test (its `canOpenURL` throws), plus an `Alert` stub that records calls and can press a named button;
  - `./clipboard`, `../api/events`: recorders;
  - `zustand` and `AsyncStorage`: real or stubbed, as `check-offer-prefill-330-unit.js` does.
- The guard is live in CI as soon as it exists (`ci.yml:47`). Add `npm run test:sleeper-handoff`.
- Every sabotage below is applied and reverted during the build, and logged in TEST_LEDGER.
- Honest label (G-035): S1, S2, S8, S9, S11, S12, S14 and S16 prove that exact wirings are present, not behavior. S3–S7, S13 and S15 execute real code.

| Id | Assertion | Kind | Named sabotage (must turn it red) |
|---|---|---|---|
| S1 | `ClaimSheet.tsx`, `FreeAgentsScreen.tsx` and `UsageTrendsScreen.tsx` contain no `sleeper.com/leagues` literal and no direct `Linking.openURL(` to a Sleeper host | text | Restore `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`)` in `ClaimSheet.openSleeper` |
| S2 | `ClaimSheet.tsx` and `SendInSleeperButton.tsx` import `openInSleeperApp` from `../utils/sleeperHandoff`, and call it from the CTA handler and from `openInSleeper` respectively | text | Inline a local `Linking.openURL('sleeper://')` in `SendInSleeperButton.openInSleeper` |
| S3 | `openURL` resolves: exactly one `openURL` call, URL starts with `sleeper://`, outcome `app`, no `Alert` | executed | Reorder the helper to try `https://sleeper.com/leagues/<id>/players` first |
| S4 | `openURL` rejects for `sleeper:`: the D2 fallback fires (`Alert` with a "Get Sleeper" button that opens `apps.apple.com/app/id987367543`, or the https open for option (i)), and outcome is `not_installed` | executed | Change the rejection handler to `.catch(() => {})` |
| S5 | The stub's `canOpenURL` throws if called, and every executed run completes without touching it | executed | Add `await Linking.canOpenURL(url)` to the helper |
| S6 | With `clipboardText`, the call log shows `copyText` **before** `openURL` | executed | Move `copyText` after `await Linking.openURL` |
| S7 | `sleeperAppUrl` over an input table for `target: 'add'` (numeric league + player; league only; `'espn_123'`; `undefined`), with the shipped rungs and a test-local `['players_tab','bare']`. Never `https`, and never a league rung for a non-numeric id | executed | Drop the `/^\d+$/` check, so `'espn_123'` yields `sleeper://leagues/espn_123/...` |
| S8 | `ClaimSheet.tsx` renders `testID="fa-claim.steps"`. Its text references `row.name`, the selected drop's name (from `dropId` and `candidates`) and `leagueName`. The CTA passes `clipboardText: row.name` | text | Remove the drop-name interpolation |
| S9 | The eight `NO_ADD_REASON` strings verbatim; `explainNoAdd` still `Alert.alert(reason.title, reason.body)`; `resolveAddPlatform`'s body unchanged | text | Change one character of `NO_ADD_REASON.espn.body` |
| S10 | `SLEEPER_PROVEN_RUNGS` is one exported declaration. Every member is in the closed rung enum for its target, and `bare` is last. Every non-`bare` member has a `PASS` row for that rung in the repo's `docs/plans/sleeper-fa-deeplink/device-results.md` (read as `../../docs/...`) | text + file read | Add `'trades_tab'` to `trade` with no PASS row in device-results.md |
| **S11** | `TradesScreen.tsx` and `useTradeQueue.ts` contain no `sleeper.com/leagues` literal, no `buildSleeperUrl`, and no `Linking.openURL(` whose argument is a `sleeper_url` or a Sleeper host. `sendAll` calls `openInSleeperApp` | text | Restore `buildSleeperUrl` returning `https://sleeper.com/leagues/${card.league_id}/trade?…` and have `sendAll` open `queue[i].sleeper_url` |
| **S12** | `useTradeQueue.ts` contains no `canOpenURL` | text | Re-add `const can = await Linking.canOpenURL(url);` before the open in `sendAll` |
| **S13** | `sleeperAppUrl({target:'trade'})` with a test-local `trade: ['trades_tab','bare']` → `sleeper://leagues/<L>/trades` for a numeric L, and `sleeper://` for a missing or non-numeric L. It never yields an add-ladder path (`/players`) | executed | Map the `'trade'` target onto the add ladder (so it returns `sleeper://leagues/<L>/players`) |
| **S14** | `SendInSleeperButton.openInSleeper` shows an `Alert` whose confirm button calls `openInSleeperApp` with `target: 'trade'` and `clipboardText: formatTradeForClipboard(…)`. Cancel opens nothing | text | Drop `clipboardText` from the `openInSleeperApp` call in `openInSleeper` |
| **S15** | With a 3-trade queue (one entry carrying a legacy `sleeper_url`), `sendAll` → exactly **one** `openURL` (`sleeper://…`); `copyText` holds all three summaries; the queue is empty afterwards; the legacy URL is never opened | executed | Keep the per-trade loop, so three `openURL` calls go out |
| **S16** | Inside `SendInSleeperButton.tsx`, the bodies of `doPropose`, `confirmSend` and `goConnect` contain no `Linking` reference, and `Linking` appears in the file only through `openInSleeperApp` (or not at all) | text | Add `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}\`)` to the success branch of `doPropose` |

Existing guards that must stay green:
- `check-usage-trends.js` §2i/2j (the shared ClaimSheet);
- `check-send-button-platform.js` (send-platform routing);
- `check-trade-text.js` (`formatTradeForClipboard`, reused unchanged).

### 7.2 Code-walk proof skeleton

The builder fills this in at current line numbers, in `docs/plans/sleeper-fa-deeplink/code-walk.md`.

**A. Free Agents → Add → claim sheet → CTA**
1. `FreeAgentsScreen.tsx:~81-88`: `onAdd` opens the sheet only when `addPlatform === 'sleeper'`; otherwise `explainNoAdd`.
2. `FreeAgentsScreen.tsx:~208-219`: `<ClaimSheet leagueId leagueName [surface] />`.
3. `ClaimSheet.tsx`: the steps block (name / drop / league).
4. CTA → `openInSleeperApp({ target:'add', leagueId, playerId: row.player_id, clipboardText: row.name, [surface, hasDrop] })`.
5. `sleeperHandoff.ts`: `copyText` → `sleeperAppUrl` (which rung, and why) → `Linking.openURL`.
6. RN `RCTLinkingManager.mm:90-115` (v0.81.5) resolves or rejects (F8) → `app` / `not_installed` → D2.

**B. Usage Trends → Add → claim sheet → CTA**
1. `UsageTrendsScreen.tsx:~270-280`: `doAdd` → `trackAction('add')` → `resolveAddPlatform` → non-Sleeper `explainNoAdd` → `switchTo` → `setClaim`.
2. `:~665-673` mount.
3. Then A3–A6.

**C. Send-in-Sleeper hand-off (send a trade, state A)**
1. `SendInSleeperButton.tsx:~381-408`: `onPress` → `sleeper_send_attempted {has_target:false}` (unchanged) → `!leagueId || !theirUserId` → `openInSleeper()`.
2. The steps confirm `Alert` → **Open Sleeper** → `openInSleeperApp({ target:'trade', leagueId, clipboardText: formatTradeForClipboard(...) })`.
3. Then A5–A6.

**D. Trade queue Send All (dark)**
1. `TradesScreen.tsx` Queue (`~8726`) → `handleQueue` enqueue, with `opponent_username` and no `sleeper_url`.
2. Send All (`~9244` / `~9299`) → `handleSendAll` → the steps confirm → `useTradeQueue.sendAll` → one `openInSleeperApp({ target:'trade', leagueId, clipboardText: <all summaries> })` → `clear(leagueId)`.

**E. The send path opens nothing, before and after**
- `doPropose`, `confirmSend`, the connect/verify alerts → `goConnect` → `SleeperLoginCapture` (an in-app WebView; `originWhitelist` https only).
- The success alert (`~243`) and the error ladder (`~270-339`) contain no `Linking`.

**F. Non-Sleeper invariance**
- `ClaimSheet.tsx:58-103` (empty diff).
- The `SendInSleeperButton` MFL/ESPN/copy branches (empty diff).
- `web/js/app.js` (empty diff).

### 7.3 Device checklist

**Setup** (from feasibility § Device tests, plus trade inputs):
- An iPhone on current iOS (Sleeper requires 16.4+), with **Sleeper v156+ installed and signed in** unless a step says otherwise.
- Test inputs:
  - **L**: a Sleeper league the tester is in.
  - **M**: a different league the tester is in.
  - **P**: a free agent's Sleeper player id in L.
  - **D**: a player id on the tester's roster in L.
  - **O**: a leaguemate's Sleeper user id in L.
  - **G**: a player id on the tester's roster.
  - **R**: a player id on O's roster.
- Before each scheme test (4–9, T1–T3), open league **M** in Sleeper and swipe Sleeper away.
- How to open each link:
  - **Scheme URLs:** type into **Safari's address bar** and tap *Open*.
  - **https URLs:** tap from **Notes**. Typing a universal link into Safari's address bar never triggers it.
- **Label capture:** record Sleeper's exact labels on the Players tab, the add flow, the Trades tab and the propose-trade flow ("Add", "Claim", "Drop", "Propose trade", …) in `device-results.md`, so design-lead's copy matches.

**Pre-build gate.** The operator or app-manager runs these and records each result, with the actual landing screen, in `docs/plans/sleeper-fa-deeplink/device-results.md`. The results fix `SLEEPER_PROVEN_RUNGS`. **No build starts before R0, 1–12 and T1–T4 are recorded.**

| # | Sleeper | Exact link / action | Opened from | Expected landing | Record |
|---|---|---|---|---|---|
| **R0** | as the operator had it | **Repeat the exact send-a-trade tap the operator tested.** Note the FTF build number (Settings → About → Version), the screen (deck / Matches / calculator), and whether the Sleeper account was connected | FTF | Unknown; this is what the step finds out | (1) Did an FTF alert come first ("Connect Sleeper first" / "Verify your account" / something else)? (2) Did **Safari** open (Safari's address bar and chrome, outside FTF), or did a Sleeper login page appear **inside FTF** (FTF's header)? (3) Did the Sleeper **app** then open, and on which screen? Safari then app = row A or B (§3.1); in-FTF login = row C. Record the card's opponent (if any) |
| 1 | installed, signed in | `https://sleeper.com/leagues/L/players` | Notes tap | Safari flashes, then Sleeper on **home or last league**, not L's Players tab | landing; confirms F3 + A1 |
| 2 | installed; **signed in to sleeper.com in Safari** first | `https://sleeper.com/leagues/L/players` | Notes tap | Unknown: the web league page, or the same redirect | which (A5, the C2 conflict) |
| 3 | installed | `sleeper://` | Safari bar | "Open in Sleeper?" prompt, then Sleeper | landing. **Go/no-go:** "address is invalid" = not registered → stop |
| 4 | installed; M opened last, then swiped away | `sleeper://leagues/L` | Safari bar | Unknown | **L** or **M** (rung `league`, plural form) |
| 5 | as 4 | `sleeper://league/L` | Safari bar | Unknown | L or M (rung `league`, singular form) |
| 6 | as 4 | `sleeper://leagues/L/players` | Safari bar | Unknown | L's **Players** tab? (`players_tab`) |
| 7 | as 4 | `sleeper://leagues/L/players/P` | Safari bar | Unknown | P's card, and in which league? (`player`) |
| 8 | as 4 | `sleeper://players/P` | Safari bar | Unknown | a card, or an **add** sheet? (`add`) |
| 9 | as 4 | `sleeper://leagues/L/players?add_player_id=P&drop_player_id=D` | Safari bar | No prefill | any add/drop UI showing P/D is a **major finding** → escalate before build |
| **T1** | as 4 | `sleeper://leagues/L/trades` | Safari bar | Unknown | L's **Trades** tab, L's home, or M? (`trades_tab`) |
| **T2** | as 4 | `sleeper://leagues/L/trade` | Safari bar | Unknown | a propose-trade screen in L, the Trades tab, or nothing? (`trade`) |
| **T3** | as 4 | `sleeper://leagues/L/trade?add_receiver_id=O&give_player_id=G&add_player_id=R` | Safari bar | No prefill | any propose screen showing O, G or R is a **major finding** → escalate before build |
| **T4** | installed, signed in | `https://sleeper.com/leagues/L/trade?add_receiver_id=O&give_player_id=G&add_player_id=R` (FTF's current queue URL) | Notes tap | Safari flashes, then Sleeper on **home**; params gone (F3) | landing; the baseline repro for the trade link |
| 10 | installed | the best-routing URL from 4–8 **and** from T1–T2 | Safari bar, twice each: Sleeper **force-quit** (cold), then **backgrounded** (warm) | same landing both times | cold vs warm per URL; a rung is proven only if both pass |
| 11 | installed | `https://go.slpr.link/sleeper` | Notes tap | Sleeper opens directly | informational (A1); not a target (D4) |
| 12a | **not installed** (offloaded/deleted, or a second phone) | `sleeper://leagues/L/players` | Safari bar | "address is invalid" | confirms the rejection path |
| 12b | not installed | `https://sleeper.com/leagues/L/players` | Notes tap | Safari → the **App Store** listing | D2 option (i)'s landing |
| 12c | not installed | `https://apps.apple.com/app/id987367543` | Notes tap | The **App Store app**, Sleeper listing, no Safari | D2 option (ii)'s target |

**Post-ship TestFlight checklist.** The operator runs these on the TestFlight build that carries the change; outcomes are logged in TEST_LEDGER.

| # | Sleeper | Steps in FTF | Expected |
|---|---|---|---|
| 13 | installed, signed in | A Sleeper league with open slots → Free agents → **Add** → claim sheet → CTA | The steps block named the player (plus the league if the rung needs it). Sleeper opens with **no Safari flash** and **no "Open in Sleeper?" prompt**, on the rung's screen. Long-press → Paste in Sleeper search pastes the name. |
| 14 | installed, signed in | Same, from **Usage Trends** → Add, including Add in a non-focused league | Same as 13, for the league the Add targeted |
| 15 | installed, signed in | A **full roster** → Free agents → Add → pick a drop → CTA | Before the hand-off, the steps showed **both** the add and the drop, and updated when the drop selection changed. Hand-off as in 13. |
| 16 | **not installed** | Free agents → Add → CTA | The D2 fallback appears (recommended: the alert → **Get Sleeper** → App Store). **Never a silent no-op.** Cancel returns to the sheet. |
| 17 | installed, **connected** | Deck → **Send in Sleeper** → Send | Unchanged: the "Trade sent" alert, **no Safari, no app switch**, and the offer is pending in Sleeper. A regression check that the helper didn't leak into the send path (AC-18). |
| 18 | installed, **not connected** (Settings → disconnect Sleeper, or a fresh install) | Deck → Send in Sleeper → **Connect** | Unchanged: Sleeper's login appears inside FTF; after login, the "Sleeper connected" alert. Nothing opens Safari or the Sleeper app. If something does, **record it**: that is R0's row-C alternative, and it goes back to `platforms-pm`. |
| 19 | installed | **The path R0 recorded**, repeated on the new build | If R0 reached row A or B: the steps confirm appears → **Open Sleeper** → Sleeper opens directly, no Safari, at the proven trade rung (or bare). Paste gives the "Trade proposal — …" summary. If R0's path can't be reproduced on demand (row A has no deterministic trigger), mark the step **n/a, with the reason**; guard S2, S11–S16 and code-walk C/D then carry it. |
| 20 | **not installed** | Same as 19 | The D2 fallback; **never silent**. |

- **No ESPN, MFL or Fleaflicker step.** Those paths don't change, and S9 plus the existing `check-send-button-platform.js` pin them.
- **No queue step while `trades.queue_2k` is dark.** S11, S12 and S15 cover it. If `trades-pm` lights the flag, their scope adds a step: two queued trades → Send All → one hand-off.

## 8. Reviews needed

| Reviewer | Role | What | Through |
|---|---|---|---|
| `design-lead` | review | The claim-sheet steps block; the send-a-trade steps confirm; CTA and footer copy; the not-installed alert. Chalkline rules (`docs/design/design-system.md`, `components.md` § Sheets, modals, menus): no emoji icons, existing tokens only | `platforms-pm` |
| `ux-lead` | review | Hand-off flows end to end: the copy-before-open disclosure, the wrong-league risk at `bare`, the extra confirm on Send-in-Sleeper's hand-off, Send All as one hand-off, and D2 | `platforms-pm` |
| `trades-pm` | **review** | Their screens: `TradesScreen` (deck, queue), `Matches`, `TradeCalculator` / `InLeagueCalculator`. Surfaces 2 and 3, the §3.1 code-walk, the steps confirm, the Send All change, the `QueuedTrade` shape change, and TestFlight 17–20 | `platforms-pm` |
| `league-pm` | consulted | The Free Agents surface | `head-product` |
| `analytics-lead` | grant | `sleeper_handoff_resolved` (scope §1), whose `surface` now includes `send_button` and `trade_queue` | `platforms-pm` |

**Pending: `head-eng` all-external-links inventory.** Per the operator's clarification, `head-eng` has an engineer inventorying **every** external link in the app and recommending one consistent pattern. When that recommendation lands, it folds into this PR through `head-product`. §3.2 keeps the helper's shape open for it: a target-keyed API, one module, no call-site logic. Known inputs for that inventory, out of scope here:
- web `_buildSleeperTradeUrl` / Send All (`app.js:4281-4320`);
- `SendInMflButton.tsx:86`;
- `SendInEspnButton.tsx:89`;
- `DraftRoomScreen.tsx:827` (`board.deep_link`, which the backend may set to `https://sleeper.com/draft/nfl/<id>`, `draft_board_service.py:1062`, likely the same Safari path);
- Settings/legal links;
- `PaywallScreen.tsx:259`;
- `HelpSheet.tsx:71`.

## 9. Sequencing and dependencies

1. **This PR** is reviewed: `platforms-pm`, then `head-product`; `trades-pm` reviews the send-a-trade surfaces.
2. **R0**, then **device tests 1–12 and T1–T4** (operator or app-manager), recorded in `device-results.md`. R0 confirms which send-a-trade path the operator hit. Test 3 is go/no-go. This step gates the build.
3. **The `head-eng` inventory recommendation**, if it lands before build, folds in through `head-product` (§8 Pending). If it hasn't landed, the build proceeds on §3.2 as written.
4. **Operator decisions:** D2 (needed before build) and D4 (confirm). D1 and D3 don't block.
5. **`analytics-lead`** grants or refuses the event.
6. **`design-lead` / `ux-lead`** settle the copy and placement.
7. **Build** (`platforms-eng` / `eng-mobile`, from a fresh `origin/main`):
   - the helper;
   - the three surface changes;
   - the `leagueName` (and maybe `surface`) prop on the two claim hosts;
   - the claim-sheet steps block and the send-a-trade steps confirm;
   - `QueuedTrade` / `sendAll`;
   - the guard;
   - the event registration, if granted;
   - the docs rows in scope §4.
8. CI green, the TEST_LEDGER entry, merge, EAS build, TestFlight. The operator runs 13–20.

Outside dependencies: none. The D1 write spike is independent and waits on E2.

## 10. Decisions needed

- **D1: the deep-link ceiling vs. a write path** (operator, through `head-product`). No link prefills an add, a drop or a trade. Executing the add/drop from FTF is the only way to meet the literal add/drop ask. It is a **new Sleeper write surface**: an operator yes/no under the risk register, with E2 open. **Recommendation:** ship this fix now; decide D1 separately.
- **D2: when Sleeper isn't installed** (operator). The options are (i) the https link, (ii) an in-app alert with Get Sleeper, or (iii) the WebView. **Recommend (ii).** See §4.4.
- **D3: desktop-UA WebView** (operator). **Recommend no**, unless test 3 fails, and even then only as its own spec.
- **D4: Sleeper's Branch link** (operator). **Recommend no.** Confirm.
- **Confirm: no feature flag** (operator). See scope §2. With no OTA, rollback means an EAS build.

## 11. Handoffs

- **Operator / app-manager:** R0, device tests 1–12 and T1–T4 (with the label capture), recorded in `device-results.md`. Also D2, D4 and the no-flag confirmation.
- **`head-product`:** D1 to the operator, with E2 in view; route the `league-pm` consult; carry the `head-eng` inventory recommendation into this PR when it lands.
- **`head-eng`:** the all-external-links inventory (operator ask). This PR's §3.1 table and §8 list are inputs to it.
- **`analytics-lead`:** the event grant, and the addendum if granted.
- **`design-lead` / `ux-lead`:** the copy and flows in §4.2–§4.4.
- **`trades-pm`:** review surfaces 2 and 3 (§8). Lighting `trades.queue_2k` stays their call. Web trade links go to `head-eng`'s inventory.
- **`platforms-eng` / `eng-mobile` (build):** §3.2, §4, §6 and §7.1, after the gates in §9. Write the D-entry and the scope §4 docs rows.
- **`platforms-pm`:** update the risk register (PR #345). Its Sleeper "Pre-planned response" names the trade deep link as the fallback that remains if writes go off, and that link doesn't work on iPhone. After this build it no longer exists in mobile. Possible later item: the ESPN waiver-screen universal link (C3).
