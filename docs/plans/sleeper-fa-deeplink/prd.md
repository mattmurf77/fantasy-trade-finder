# Sleeper FA hand-off: open the Sleeper app directly — PRD (2026-10-15)

> The spec slice for the operator's top priority of 2026-10-15. It covers the "Add in Sleeper" hand-off from the claim sheet (Free Agents and Usage Trends) and the Send-in-Sleeper no-target hand-off. Today both go through Safari and land on Sleeper's home screen. The evidence base is [feasibility.md](feasibility.md); the feature gates are in [scope.md](scope.md). Line numbers are verified against `origin/main` @ `678834ab`. This document specifies behavior. It changes no code. The build starts only after device tests 1–12 are recorded and D2 is decided.

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

**Root cause** (verified; [feasibility.md § Why the operator sees what they see](feasibility.md#why-the-operator-sees-what-they-see), F1 and F3):
- Sleeper's AASA claims only chat paths, so `https://sleeper.com/leagues/<id>/players` opens Safari.
- On an iPhone user agent, sleeper.com then `302`s to the generic Branch link `go.slpr.link/sleeper`. That link drops the league, the page and every parameter, and it opens the app on its home screen (or the App Store if Sleeper isn't installed).

**What this fixes and what it doesn't.**
- **Fixed: "web first."** The app opens directly through `sleeper://`, with no Safari hop.
- **Not fixed: "player prefilled, along with the drop."** No verifiable route prefills an add or an add/drop in Sleeper (feasibility, Short answer). This PRD ships the honest stand-in: the free agent's name is copied, and the sheet spells out the steps, naming the add and the drop. The only way to fully meet the literal ask is for FTF to execute the add/drop itself. That is decision D1, and it is not part of this build.

## 2. Strategy owner and hypothesis

- **Owner:** `platforms-pm` (operator top priority, 2026-10-15). Spec by the platforms-pm spec worker under `/pm-technical`.
- **Hypothesis:** if "Add in Sleeper" opens the Sleeper app directly, at the deepest screen Sleeper honors, with the player's name on the clipboard and the add/drop named on the sheet, then a user can finish the claim in Sleeper with one search and a paste. Today they get a Safari flash and a home screen with no context.
- **How we'll know:**
  - TestFlight steps 13–16 pass on a device (the only runtime evidence under D-056).
  - If `analytics-lead` grants the event, `sleeper_handoff_resolved.outcome` shows `app` for testers who have Sleeper installed. Population is the operator plus about 2 testers, so this is a smoke signal, not a metric.

## 3. Surfaces in scope

| # | Surface | Call site (`origin/main` @ `678834ab`) | Today | Change |
|---|---|---|---|---|
| 1 | **Claim sheet CTA** "Open in Sleeper to claim" | `mobile/src/components/ClaimSheet.tsx:141-145` (`openSleeper`), button `:307-313` (testID `fa-claim.open-sleeper`), footer `:315` | `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`)`, rejection swallowed (`.catch(() => {})`) | Call the shared helper. Add the steps block (§4.2). |
| 1a | ↳ host: **Free Agents** | `mobile/src/screens/FreeAgentsScreen.tsx:81-88` (`onAdd`, Sleeper-gated), `:208-219` (ClaimSheet mount) | No `Linking` call of its own since the 2026-10-10 ClaimSheet extraction (`ClaimSheet.tsx:38-43`). The `FreeAgentsScreen.tsx:320` reference in `docs/integrations/sleeper.md:79` and in the brief is stale; `:320` is now a stylesheet. | Logic unchanged; it gets the fix through ClaimSheet. Passes `leagueName` (§4.2), and `surface="free_agents"` if the §1 event is granted. Guard S1 keeps this file free of direct Sleeper URLs. |
| 1b | ↳ host: **Usage Trends** | `mobile/src/screens/UsageTrendsScreen.tsx:270-280` (`doAdd`: switches to the claim league first), `:665-673` (ClaimSheet mount) | Same CTA | Same as 1a. Passes `leagueName` (session `league_name`, `:94`, which is the claim league after `switchTo`), and `surface="usage_trends"` if granted. |
| 2 | **Send-in-Sleeper hand-off** | `mobile/src/components/SendInSleeperButton.tsx:208-212` (`openInSleeper`), reached from `onPress` `:405-408` when `!leagueId \|\| !theirUserId` | `https://sleeper.com/leagues/${leagueId}` (numeric id) or `https://sleeper.com`. Same Safari → home symptom (feasibility F3). | `openInSleeper` becomes a one-line call to the helper (league rung if proven, else bare). The send path, the copy affordance and `sleeper_send_attempted` are untouched. |

**Not in scope; handed to `trades-pm`:** the trade-queue link.
- Built by `buildSleeperUrl` (`mobile/src/screens/TradesScreen.tsx:9589-9600`, used at `:6502`) and opened by `useTradeQueue.sendAll` (`mobile/src/state/useTradeQueue.ts:128-133`).
- Web has the same link in `_buildSleeperTradeUrl` (`web/js/app.js:4281-4295`).
- The brief's `TradesScreen.tsx` ~L5171/5186 references are stale.
- Feasibility F3/F5 shows the link is very likely broken on both platforms. On iPhone the redirect drops every param. On desktop there's no `/leagues/:league/trade` route, and nothing reads `add_receiver_id`.
- The helper below can serve it. One caveat: `sendAll` pre-checks with `Linking.canOpenURL`, which **rejects** for `sleeper://` without an `LSApplicationQueriesSchemes` entry (F8). Adopting the helper there means dropping that pre-check, or else a plist key plus a native build.

### 3.1 The shared helper

One module, so that all three surfaces behave the same way: **`mobile/src/utils/sleeperHandoff.ts`** (new).

```ts
// Rungs proven on a device (device-results.md), highest first. 'bare' is always last.
// Ships as ['bare'] unless device tests 4–9 prove a deeper rung.
export const SLEEPER_PROVEN_RUNGS: readonly SleeperRung[];

// Pure. Returns the highest proven rung URL that the inputs support. Never https.
export function sleeperAppUrl(t: { leagueId?: string; playerId?: string }): string;

// Copy (optional) → open the scheme → on rejection, run the D2 fallback.
export function openInSleeperApp(t: {
  leagueId?: string;
  playerId?: string;
  clipboardText?: string;   // claim sheet: the FA's name
  surface?: 'free_agents' | 'usage_trends' | 'send_button'; // only if the §1 event is granted
  hasDrop?: boolean;        // ditto
}): Promise<'app' | 'not_installed'>;
```

Behavior, in order:
1. If `clipboardText` is set, call `copyText(clipboardText)` (`mobile/src/utils/clipboard.ts`, the app's one clipboard seam, JS-only) **before** opening. Once Sleeper is in the foreground, FTF's JS may be suspended, so the copy cannot wait until after the open.
2. Build the URL with `sleeperAppUrl`. A missing or non-numeric `leagueId` gives a league-free rung, which is bare `sleeper://` unless `add` is proven. Sleeper league ids are numeric (`ClaimSheet.tsx:63-64`, `SendInSleeperButton.tsx:209`).
3. `await Linking.openURL(url)`:
   - **Resolves:** outcome `app`.
   - **Rejects:** outcome `not_installed`, then the D2 fallback (§4.3). Rejection is never swallowed silently.
4. If granted, emit `sleeper_handoff_resolved` once (scope §1).
5. **Never:** call `Linking.canOpenURL` (it rejects without the plist key, F8), pass an `https://sleeper.com/...` URL as the primary target, or touch native config.

The file is impure: it uses react-native `Linking` and `Alert`, `./clipboard`, and `../api/events` if the event is granted. The guard executes it under node with stubs (§7.1). Add its entry to `mobile/src/utils/CLAUDE.md` and `README.md`.

## 4. Expected behavior

The user taps the claim sheet's CTA. Sleeper opens **directly**: no Safari, no "Open in Sleeper?" prompt (assumption A4; that prompt is a Safari behavior). It opens on the deepest screen device tests proved. The free agent's name is already on the clipboard, and the sheet listed the steps, including the drop the user picked.

### 4.1 The target ladder

Device tests 1–12 **fix the rung before build** (§7.3). If nothing deeper proves out, the build ships bare `sleeper://`. Ranked from best to floor (from feasibility § Ranked options):

| Rank | Rung id | Target | URL pattern | Needs | Status today | Proven by |
|---|---|---|---|---|---|---|
| (a) | — | Add/drop screen, add **and** drop prefilled | **no known route** | — | unknown; no evidence any route exists | test 9 (probe only). A pass is a major finding: escalate to `platforms-pm` before build. |
| (b) | `add` | Add screen, add prefilled | `sleeper://players/<P>` (speculative) | `playerId` | unknown | test 8 shows an **add** sheet for P |
| (c) | `player` | Player card in league context | `sleeper://leagues/<L>/players/<P>` (speculative) | `leagueId` + `playerId` | unknown | test 7 lands on P **in L** |
| (d) | `players_tab` | League **Players** tab | `sleeper://leagues/<L>/players` | `leagueId` | unknown (C2: league paths may be ignored) | test 6 lands on L's Players tab |
| (e) | `league` | League home | `sleeper://leagues/<L>` or `sleeper://league/<L>` (whichever form passed) | `leagueId` | unknown for L; likely the last-viewed league | test 4 or 5 lands on **L, not M** |
| (e′) | `bare` | App open, no Safari hop | `sleeper://` | — | **likely** (C1, C2; FTF web already uses it at `app.js:6200`) | test 3. **This is the floor and the default.** |

Rules:
- **A rung counts as proven** only if its test lands on the stated screen **in league L**, after league M was opened last, **both** cold and warm (test 10). Landing on M means Sleeper reopened the last league. That is a fail for every league rung.
- The constant `SLEEPER_PROVEN_RUNGS` lists exactly the rungs marked PASS in `docs/plans/sleeper-fa-deeplink/device-results.md`, with `bare` last. Guard S10 cross-checks the two.
- Each call uses the **highest proven rung its inputs support**. The claim sheet has `leagueId` and `playerId`. The Send-in-Sleeper hand-off has at most `leagueId` and never a player.
- **If test 3 fails** (Safari says the address is invalid), the scheme approach is dead. The build does not start. The spec returns to `platforms-pm` with D3 (desktop-web WebView) or a copy-only flow.

### 4.2 The honest stand-in for prefill: clipboard + on-sheet steps

Prefill isn't available, so the claim sheet does two things:

1. **Copies the free agent's name** (`row.name`) when the CTA is tapped, before the open (§3.1 step 1). The sheet says this up front, so the clipboard is never overwritten without notice.
2. **Shows the steps** in a block (testID `fa-claim.steps`) between the drop section and the CTA. The block updates live as the user picks a drop. Its content requirements:

| Must show | When | Source |
|---|---|---|
| The add: the free agent's name | always | `row.name` |
| The drop: the selected player's name | when a drop is selected (`dropId != null`) | `candidates.find(c => c.id === dropId)?.name` (`ClaimSheet.tsx:127,135`) |
| The league, by name | when the shipped rung doesn't guarantee the league (`bare`, or a rung that never landed on L) | new optional `leagueName` prop from the hosts. Without a league name the user may add the FA in **the wrong league**, because the bare scheme reopens the last-viewed league (C2). |
| The bid | FAAB league with a bid entered | `bid` (`:126`). design-lead may drop it if it crowds the block |
| That the name was copied | always | static copy |

The steps' starting point depends on the rung, because each rung lands somewhere different. Draft copy below; **wording, layout and placement belong to `design-lead` and `ux-lead`**:
- `bare` / `league`: "In Sleeper: open **{League}** → Players → search **{Name}** → Add → drop **{Drop}**"
- `players_tab`: "In Sleeper: search **{Name}** → Add → drop **{Drop}**"
- `player` / `add`: "In Sleeper: Add → drop **{Drop}**"
- Clipboard line: "We'll copy {Name} so you can paste it into search."
- Without a drop, the "→ drop {Drop}" segment is omitted. When the drop list shows but nothing is picked, design-lead decides whether to prompt.
- We haven't verified Sleeper's in-app labels ("Add", "Claim", "Drop"). The pre-build device session records them (§7.3 setup), so the copy uses Sleeper's real words.

Chalkline constraints:
- Existing type tokens only: `TickLabel`, `type.bodySm`, `chalk.dim`, as in the sheet's other sections.
- Ice only for the existing primary CTA.
- No emoji or emoji-as-icon. The arrows are text and design-lead may replace them with numbered steps.
- No new colors, gradients or blur.
- The existing footer (`:315`) and the CTA label are design-lead's to keep or revise. The CTA **testID stays `fa-claim.open-sleeper`**.

The Send-in-Sleeper hand-off gets no steps and no clipboard, because it has no player context. It only opens the app.

### 4.3 When Sleeper isn't installed (decision D2)

`Linking.openURL('sleeper://…')` rejects when no app handles the scheme (F8). The helper then runs one fallback, the same on every surface. The options:

| Option | What the user sees | Cost | Notes |
|---|---|---|---|
| (i) Open `https://sleeper.com/leagues/<L>/players` | Safari flash, then Sleeper's Branch redirect, then the **App Store** listing (F3, test 12b) | zero UI | This is exactly the Safari hop the operator complained about, just ending at the App Store. Every tap also counts as a click in Sleeper's Branch attribution, the same objection as D4. |
| **(ii) In-app message with an App Store button (recommended)** | Alert: "Sleeper isn't installed" / "Get the Sleeper app to finish this in your league." / buttons **Cancel**, **Get Sleeper** → `https://apps.apple.com/app/id987367543` (the id is verified, F6) | one `Alert` | No Safari, no Branch click, and honest about what's wrong. Same pattern as `explainNoAdd` (`ClaimSheet.tsx:100-103`). Test 12c checks that the App Store link opens the App Store app directly. Copy is design-lead's. |
| (iii) Desktop-web Players tab in a WebView (W) | Sleeper's desktop web page for L inside FTF | user-agent spoof; phone-width layout untested | This is D3. Not recommended as the not-installed fallback. |

**Recommendation: (ii).** It never fails silently: if the App Store open also rejects, the alert has already told the user what to do (TestFlight step 16).

### 4.4 What doesn't change

- ESPN, MFL, Fleaflicker and local leagues keep the existing `NO_ADD_REASON` alerts byte-for-byte (`ClaimSheet.tsx:67-95`; `explainNoAdd` `:100-103`; `resolveAddPlatform` `:58-65`). The claim sheet still mounts only for Sleeper leagues (`FreeAgentsScreen.tsx:84`, `UsageTrendsScreen.tsx:274-277`).
- Claim preparation stays as it is: the FAAB bid, the over-budget disable (`:311`), drop selection and the untouchables note.
- Send-in-Sleeper's real send (`doPropose`), its connect flow, the copy-trade affordance (`send-in-sleeper.copy`) and `sleeper_send_attempted` are unchanged.
- The trade queue, the web app and the extension are unchanged.

## 5. Out of scope

- **D1, executing the add/drop from FTF** through Sleeper's private API. This is the only path to the operator's literal end state. It is a **new platform write surface**: Sleeper's only FTF write today is `propose_trade`, behind `trade.send_in_sleeper`. Under the platform risk register (PR #345, `.claude/skills/pm-partnerships/references/platform-risk-register.md`), that makes it an **operator yes/no through `head-product`**, and it clears the register's write-feature gate first. Escalation E2 is also open: Sleeper's Terms revised 2026-10-06, §11.1 and §11.3. If the answer is yes, it's a separate capture spike for `platforms-eng` (precedent: `docs/plans/sleeper-write-capture-runbook.md`). It is never folded into this build.
- **D3, a desktop-UA WebView** of Sleeper's Players tab.
- **D4, Sleeper's Branch link** (`https://go.slpr.link/sleeper`) as a target.
- **The trade-queue and web trade links.** These go to `trades-pm` (§3, §11).
- **An ESPN waiver-screen universal link** (community evidence C3; not verified). A possible later item for `platforms-pm`.
- **`LSApplicationQueriesSchemes` / `canOpenURL`**, and any native or `app.json` change.
- **Android.** iOS is the only shipped client.
- Changes to FAAB, drop-candidate or roster-capacity logic, or to backend payloads.

## 6. Acceptance criteria

Each criterion can be checked pass/fail by a guard, a test, a diff check, or a checklist step.

| AC | Criterion | Verified by |
|---|---|---|
| AC-1 | No `sleeper.com/leagues` URL is passed to `Linking.openURL` from `ClaimSheet.tsx`, `FreeAgentsScreen.tsx`, `UsageTrendsScreen.tsx` or `SendInSleeperButton.tsx`. None of those files contains a direct `Linking.openURL` to any Sleeper host. | guard S1 |
| AC-2 | The claim-sheet CTA and `SendInSleeperButton.openInSleeper` both call `openInSleeperApp`, imported from `../utils/sleeperHandoff`. There is no second implementation. | guard S2 |
| AC-3 | The helper's first (and, on success, only) `openURL` argument starts with `sleeper://`. | guard S3 (executed) |
| AC-4 | When the scheme open rejects, the D2 fallback runs (as decided), and the helper resolves `not_installed`. It never resolves with nothing opened and nothing shown. | guard S4 (executed); TestFlight 16 |
| AC-5 | The helper never calls `Linking.canOpenURL`. The PR changes no native config: no `Info.plist` key, no entitlement, no `LSApplicationQueriesSchemes`, and no `app.json` / `eas.json` setting other than the routine release version/build-number bump. | guard S5 (executed); `git diff --stat` in the PR |
| AC-6 | With `clipboardText`, `copyText` is called with it **before** `openURL`. | guard S6 (executed, call-order log) |
| AC-7 | `sleeperAppUrl` returns the highest proven rung the inputs support. A non-numeric or missing `leagueId` never yields a league rung. It never returns `https://`. `bare` is the floor. | guard S7 (executed) |
| AC-8 | `SLEEPER_PROVEN_RUNGS` matches the PASS rows in `device-results.md`. It is `['bare']` if only test 3 passed. | guard S10; code-walk |
| AC-9 | The claim sheet renders `fa-claim.steps` with the FA's name, the selected drop's name when a drop is picked, and the league name at a rung that doesn't guarantee the league. | guard S8 (wiring); TestFlight 13, 15 |
| AC-10 | ESPN / MFL / Fleaflicker / local paths are unchanged. The eight `NO_ADD_REASON` strings, `explainNoAdd` and `resolveAddPlatform` are byte-identical to `678834ab`. | guard S9; diff check |
| AC-11 | `fa-claim.open-sleeper` keeps its testID. `fa-claim.steps` is added. `testid-lint.sh` is green. | CI `maestro-testid-lint` |
| AC-12 | `buildSleeperUrl`, `useTradeQueue.ts` and `web/js/app.js` are not modified by this build. | PR diff check |
| AC-13 | If the §1 event is granted, `sleeper_handoff_resolved` is registered and classified **in the same commit** as its emitter and fires once per hand-off. | backend pytest; guard S3/S4 stubs count `track` calls |
| AC-14 | On device: Sleeper opens with no Safari flash at the proven rung. The name pastes into Sleeper search. Not-installed reaches the fallback. | TestFlight 13–16 |
| AC-15 | `docs/integrations/sleeper.md:77-79` and the #179 status claim are corrected (scope §4). | docs review in the PR |

## 7. Evidence plan (D-056)

No Maestro, no simulator, no captures. The evidence is a structural guard (partly executed), a code-walk, a pre-build device gate and a post-ship TestFlight checklist.

### 7.1 Structural guard: `mobile/tests/check-sleeper-handoff.js`

- It is dependency-free apart from the project's `typescript` (the `check-offer-prefill-330-unit.js` idiom). It transpiles `src/utils/sleeperHandoff.ts` and runs it with a `require` shim:
  - `react-native`: a `Linking` stub that records calls and resolves or rejects as each test needs, and an `Alert` stub that records calls.
  - `./clipboard` and `../api/events`: recorders.
- It is live in CI as soon as it exists (`ci.yml:47`). Add `npm run test:sleeper-handoff`.
- Every sabotage below is applied and reverted during the build, and logged in TEST_LEDGER.
- Honest label (G-035): S1, S2, S8 and S9 prove that exact wirings are present, not behavior. S3–S7 execute the real helper.

| Id | Assertion | Kind | Named sabotage (must turn it red) |
|---|---|---|---|
| S1 | The four surface files contain no `sleeper.com/leagues` literal and no direct `Linking.openURL(` to a Sleeper host | text | Restore `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`)` in `ClaimSheet.openSleeper` |
| S2 | `ClaimSheet.tsx` and `SendInSleeperButton.tsx` import `openInSleeperApp` from `../utils/sleeperHandoff` and call it from the CTA handler and `openInSleeper` respectively | text | Inline a local `Linking.openURL('sleeper://')` in `SendInSleeperButton.openInSleeper` |
| S3 | With `openURL` resolving: exactly one `openURL` call, its URL starts with `sleeper://`, outcome `app`, no `Alert` | executed | Reorder the helper to try `https://sleeper.com/leagues/<id>/players` first |
| S4 | With `openURL` rejecting for `sleeper:`: the D2 fallback fires (the `Alert` stub is called with a "Get Sleeper" button whose handler opens `apps.apple.com/app/id987367543`, or the https open for option (i)), and outcome is `not_installed` | executed | Change the helper's rejection handling to `.catch(() => {})` |
| S5 | The `Linking` stub's `canOpenURL` throws if called, and every S3/S4/S6/S7 run completes without hitting it | executed | Add an `await Linking.canOpenURL(url)` pre-check |
| S6 | With `clipboardText: 'Name'`, the call log shows `copyText('Name')` **before** `openURL` | executed | Move `copyText` after the `await Linking.openURL` |
| S7 | `sleeperAppUrl` over a table: numeric league + player, numeric league only, `'espn_123'`, `undefined`. Each gives the expected rung URL for the shipped `SLEEPER_PROVEN_RUNGS` (and for a test-local override list `['players_tab','bare']`). Never `https`, never a league rung for a non-numeric id | executed | Drop the `/^\d+$/` check, so `'espn_123'` yields `sleeper://leagues/espn_123/...` |
| S8 | `ClaimSheet.tsx` renders `testID="fa-claim.steps"`. The block's text expression references `row.name`, the selected drop's name (derived from `dropId` and `candidates`), and `leagueName`. The CTA `onPress` passes `clipboardText: row.name` | text | Remove the drop-name interpolation from the steps block |
| S9 | The eight `NO_ADD_REASON` title/body strings, pinned verbatim; `explainNoAdd` still `Alert.alert(reason.title, reason.body)`; `resolveAddPlatform`'s body unchanged | text | Change one character of `NO_ADD_REASON.espn.body` |
| S10 | `SLEEPER_PROVEN_RUNGS` is a single exported declaration; every member is in the closed rung enum; `bare` is last. Every non-`bare` member has a `PASS` row for that rung in the repo's `docs/plans/sleeper-fa-deeplink/device-results.md` (read from `mobile/tests/` as `../../docs/...`) | text + file read | Add `'players_tab'` to the constant without a PASS row in device-results.md |

Existing guards that must stay green: `check-usage-trends.js` (§2i/2j pin the shared ClaimSheet in both hosts) and `check-send-button-platform.js` (send-platform routing).

### 7.2 Code-walk proof skeleton

The builder fills this in, with current line numbers after the change, in `docs/plans/sleeper-fa-deeplink/code-walk.md`.

**A. Free Agents → Add → claim sheet → CTA**
1. `FreeAgentsScreen.tsx:~81-88`: `onAdd` opens the sheet only when `addPlatform === 'sleeper'`; otherwise `explainNoAdd`.
2. `FreeAgentsScreen.tsx:~208-219`: `<ClaimSheet leagueId={leagueId} leagueName=… [surface="free_agents"] />`.
3. `ClaimSheet.tsx`: the steps block renders the name, drop and league (cite the lines).
4. `ClaimSheet.tsx`: CTA `onPress` → `openInSleeperApp({ leagueId, playerId: row.player_id, clipboardText: row.name, [surface, hasDrop: dropId != null] })`.
5. `sleeperHandoff.ts`: `copyText`, then `sleeperAppUrl` (the rung chosen and why), then `Linking.openURL`.
6. RN `RCTLinkingManager.mm:90-115` (v0.81.5): `openURL:options:completionHandler:` resolves `true`, or rejects "Unable to open URL" (F8). Then `app` or `not_installed` → D2 fallback (cite the lines).

**B. Usage Trends → Add → claim sheet → CTA**
1. `UsageTrendsScreen.tsx:~270-280`: `doAdd` → `trackAction('add')` (unchanged) → `resolveAddPlatform` → non-Sleeper `explainNoAdd` → `switchTo(lgId)` → `setClaim`.
2. `UsageTrendsScreen.tsx:~665-673`: `<ClaimSheet … leagueName=… [surface="usage_trends"] />`. The session `league_name` is the claim league because of `switchTo`.
3. From there, steps A3–A6.

**C. Send-in-Sleeper no-target hand-off**
1. `SendInSleeperButton.tsx:~381-408`: `onPress` → `sleeper_send_attempted {has_target:false}` (unchanged) → `!leagueId || !theirUserId` → `openInSleeper()`.
2. `openInSleeper` → `openInSleeperApp({ leagueId, [surface: 'send_button'] })`. No clipboard. League rung if proven and numeric, else bare.
3. Then A5–A6.

**D. Non-Sleeper invariance:** `ClaimSheet.tsx:58-103` (diff empty); `FreeAgentsScreen.tsx:85`; `UsageTrendsScreen.tsx:274-276`; `SendInSleeperButton` non-Sleeper branches (diff empty).

**E. Not touched:** `TradesScreen.tsx:9589-9600`, `useTradeQueue.ts:128-133`, `web/js/app.js` (diff empty).

### 7.3 Device checklist

**Setup** (from feasibility § Device tests):
- An iPhone on current iOS (Sleeper's App Store minimum is 16.4), with **Sleeper v156+ installed and signed in** unless a step says otherwise.
- **L**: a Sleeper league the tester is in.
- **M**: a *different* league the tester is in.
- **P**: the Sleeper player id of a free agent in L.
- **D**: the id of a player on the tester's roster in L.
- Before each scheme test (4–9), open league **M** in Sleeper, then swipe Sleeper away.
- How to open links:
  - **Scheme URLs:** type them into **Safari's address bar** and tap *Open* on the prompt.
  - **https URLs:** tap them from **Notes**. Typing a universal link into Safari's address bar never triggers it.
- **Label capture:** while in Sleeper's Players tab and add flow, note the exact button labels ("Add", "Claim", "Drop", or whatever they are) in `device-results.md`, so design-lead's step copy matches.

**Pre-build gate.** The operator or app-manager runs these and records each result, with the actual landing screen, in `docs/plans/sleeper-fa-deeplink/device-results.md`. The results fix `SLEEPER_PROVEN_RUNGS`. **No build starts before tests 1–12 are recorded.**

| # | Sleeper | Exact link | Opened from | Expected landing | Record |
|---|---|---|---|---|---|
| 1 | installed, signed in | `https://sleeper.com/leagues/L/players` | Notes tap | Safari flashes, then Sleeper on **home or last league**, not L's Players tab | landing screen; confirms F3 + A1 (the baseline repro) |
| 2 | installed; **signed in to sleeper.com in Safari** first | `https://sleeper.com/leagues/L/players` | Notes tap | Unknown: the web league page, or the same redirect as test 1 | which one (A5, the C2 conflict) |
| 3 | installed | `sleeper://` | Safari address bar | "Open in Sleeper?" prompt, then the Sleeper app | landing screen. **Go/no-go:** "address is invalid" = scheme not registered → stop, spec returns to `platforms-pm` |
| 4 | installed; M opened last, app swiped away | `sleeper://leagues/L` | Safari address bar | Unknown | lands on **L** or **M** (rung `league`, plural form) |
| 5 | as 4 | `sleeper://league/L` | Safari address bar | Unknown | L or M (rung `league`, singular form) |
| 6 | as 4 | `sleeper://leagues/L/players` | Safari address bar | Unknown | is it L's **Players** tab? (rung `players_tab`) |
| 7 | as 4 | `sleeper://leagues/L/players/P` | Safari address bar | Unknown | player card for P? in which league? (rung `player`) |
| 8 | as 4 | `sleeper://players/P` | Safari address bar | Unknown | player card, or an **add** sheet, for P? (rung `add`) |
| 9 | as 4 | `sleeper://leagues/L/players?add_player_id=P&drop_player_id=D` | Safari address bar | No prefill | any add/drop UI showing P or D is a **major finding**: escalate to `platforms-pm` before build |
| 10 | installed | the best-routing URL from 4–8 | Safari address bar, run twice: Sleeper **force-quit** (cold), then **backgrounded** (warm) | the same landing both times | cold vs warm results; a rung counts as proven only if both pass |
| 11 | installed | `https://go.slpr.link/sleeper` | Notes tap | Sleeper opens directly, no Safari | informational only (confirms A1); not a candidate target (D4) |
| 12a | **not installed** (offload or delete, or a second phone) | `sleeper://leagues/L/players` | Safari address bar | "Safari cannot open the page because the address is invalid" | confirms the rejection path the helper relies on |
| 12b | not installed | `https://sleeper.com/leagues/L/players` | Notes tap | Safari, then the **App Store** Sleeper listing | confirms D2 option (i)'s landing |
| 12c | not installed | `https://apps.apple.com/app/id987367543` | Notes tap | The **App Store app** opens on the Sleeper listing, with no Safari | confirms D2 option (ii)'s target (added to the memo's list) |

**Post-ship TestFlight checklist** (the operator runs these on the TestFlight build carrying the change; outcome logged in TEST_LEDGER):

| # | Sleeper | Steps in FTF | Expected |
|---|---|---|---|
| 13 | installed, signed in | Sleeper league with open roster slots → League → Free agents → **Add** on a player → claim sheet → **Open in Sleeper to claim** (or the label design-lead picks) | The steps block named the player, and the league if the rung needs it. Sleeper opens with **no Safari flash** and **no "Open in Sleeper?" prompt**, on the screen `SLEEPER_PROVEN_RUNGS` claims. Long-press → Paste in Sleeper's search pastes the player's name. |
| 14 | installed, signed in | Same, starting from **Usage Trends** → a free agent → Add (including Add in a league other than the focused one, which switches leagues first) | Same as 13. The steps and the landing are for the league the Add targeted. |
| 15 | installed, signed in | Sleeper league with a **full roster** → Free agents → Add → pick a drop → CTA | Before the hand-off, the steps block showed **both** the add and the drop names, and it updated when the drop selection changed. The hand-off behaves as in 13. |
| 16 | **not installed** | Free agents → Add → CTA | The D2 fallback appears (recommended: the "Sleeper isn't installed" alert, then **Get Sleeper** opens the App Store listing). **Never a silent no-op.** Cancel returns to the sheet. |

- **No ESPN, MFL or Fleaflicker step is needed.** Those paths don't change, and S9 pins their copy byte for byte.
- **No step for the Send-in-Sleeper hand-off.** By code-walk, it is reached only on a Sleeper mount whose card lacks `leagueId` or `opponent_user_id`. No deterministic UI trigger was found. The calculator mount requires `opponentId` (`InLeagueCalculator.tsx:1486`). It is covered by S2 plus the executed helper tests S3–S7, and code-walk C. If the builder finds a reliable trigger, add a step 17.

## 8. Reviews needed

| Reviewer | What | Through |
|---|---|---|
| `design-lead` | Steps-block copy, layout and placement on the claim sheet; CTA label and footer; the not-installed alert copy. Chalkline rules (`docs/design/design-system.md`, `components.md` § Sheets, modals, menus): no emoji icons, existing tokens only | `platforms-pm` |
| `ux-lead` | The hand-off flow end to end: copy-before-open disclosure, the wrong-league risk at the `bare` rung, the D2 fallback choice, and the full-roster-without-a-drop state | `platforms-pm` |
| `league-pm` | **Consulted** on the Free Agents surface (it owns the League tab's FA finder) | `head-product` |
| `trades-pm` | **Informed**: `SendInSleeperButton.openInSleeper` changes, a surface they share. Also receives the trade-link handoff (§11) | `platforms-pm` |
| `analytics-lead` | Grant, change or refuse `sleeper_handoff_resolved` (scope §1) | `platforms-pm` |

## 9. Sequencing and dependencies

1. **This PR** is reviewed by `platforms-pm`, then `head-product`.
2. **Device tests 1–12** (operator or app-manager) go into `device-results.md`. Test 3 is go/no-go. This gates the build.
3. **Operator decisions** on D2 (needed before build) and D4 (confirm). D1 and D3 don't block this build.
4. **`analytics-lead` grant** (or refusal) on the §1 event. This decides whether the `surface` and `hasDrop` params exist.
5. **`design-lead` / `ux-lead`** settle the copy and placement.
6. **Build** (`platforms-eng` / `eng-mobile`, from a fresh `origin/main`):
   - the helper;
   - two call-site changes, plus the `leagueName` (and maybe `surface`) prop on the two hosts;
   - the steps block;
   - the guard;
   - the event registration if granted;
   - the docs rows in scope §4.
7. CI green, TEST_LEDGER entry, merge, EAS build, TestFlight. The operator runs steps 13–16.

Dependencies outside this item: none. The D1 write spike would be independent, and it waits on E2.

## 10. Decisions needed

- **D1: deep-link ceiling vs. a write path** (operator, through `head-product`). No link can prefill the add or the drop. Executing the add/drop from FTF is the only way to fully meet the literal ask. It is a **new Sleeper write surface**, so under the platform risk register it is an operator yes/no, and E2 (Sleeper Terms §11, 2026-10-06) is open against it. **Recommendation:** ship this fix now and decide D1 separately. If yes, it's a `platforms-eng` capture spike.
- **D2: when Sleeper isn't installed** (operator). (i) the https link, ending at the App Store via Safari and Branch; **(ii) an in-app alert with a Get Sleeper button (recommended)**; (iii) the WebView. See §4.3.
- **D3: desktop-UA WebView (W)** (operator). **Recommendation: no**, unless test 3 fails and the scheme approach is dead. Even then it comes back as its own spec, because it means a user-agent spoof, an untested phone-width layout, and unknown sign-in state.
- **D4: Sleeper's Branch link** (operator). **Recommendation: no.** It lands on the same home screen as bare `sleeper://`, and every FTF tap would count in Sleeper's Branch attribution. Please confirm.
- **Confirm: no feature flag** (operator). Scope §2 gives the reasons. The cost is that, with no OTA, rollback means a new EAS build.

## 11. Handoffs

- **Operator / app-manager:** run device tests 1–12 and record them in `docs/plans/sleeper-fa-deeplink/device-results.md`, including the label capture. Decide D2 and D4, and confirm no flag.
- **`head-product`:** D1 goes to the operator, with E2 in view. Route the `league-pm` consult.
- **`analytics-lead`:** grant, change or refuse `sleeper_handoff_resolved` (scope §1). If granted, write the dated addendum in `docs/business/analytics/`.
- **`design-lead` / `ux-lead`:** steps block, CTA label, footer and not-installed copy (§4.2, §4.3).
- **`platforms-eng` / `eng-mobile` (build):** §3.1, §4, §6 and §7.1, after the gates above. Write the D-entry and the docs rows in scope §4.
- **`trades-pm`:**
  - The trade-queue link (`TradesScreen.tsx:9589-9600` → `useTradeQueue.ts:128-133`) and web `_buildSleeperTradeUrl` (`app.js:4281-4295`) are very likely dead weight on iPhone and on desktop (F3, F5). The code comment "even if the params are ignored" understates it.
  - `utils/sleeperHandoff` can open the app for the queue. Drop `canOpenURL` if it's adopted.
  - `SendInSleeperButton.openInSleeper` changes in this build (FYI).
- **`platforms-pm`:**
  - The risk register's Sleeper "Pre-planned response" names that same trade deep link as the fallback that stays if writes are switched off. It doesn't work on iPhone. Update the register (PR #345).
  - Possible later item: the ESPN waiver-screen universal link (C3, unverified).
- **Docs (by the build):** `docs/integrations/sleeper.md:77-79` (stale call sites; record F1/F3); `docs/feedback/items/179-fa-add-button/status.md:35-36` (the "app or web via universal link" claim is false on iPhone).
