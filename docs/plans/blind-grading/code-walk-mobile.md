# Code-walk — Calibration mobile (P3)

**Date:** 2026-10-02 · **Package:** P3 (specs.md §5.3) · **Branch:** `feat/blind-grading-p3` · Companion: [scope.md §3](scope.md#3-evidence-scope) · [lld.md §10](lld.md#10-mobile) · [specs.md §3.3](specs.md#33-change-control)

This is the file:line-cited trace that replaces a simulator capture under D-056. Line numbers are against the P3 commit on `feat/blind-grading-p3`; the lead re-resolves them after merge. Every claim here is also pinned mechanically by `mobile/tests/check-blind-grading.js` where code shape can carry it; the runtime half is the TestFlight checklist at the end.

## Contents

1. [Tab presence at launch — the four flag combinations](#1-tab-presence-at-launch)
2. [The card loop renders only `GradingCard` fed by `GradingNext.card.trade`](#2-the-card-loop)
3. [A 409 `needs_fresh_deck` leads to the Acquire tab](#3-needs_fresh_deck--acquire)
4. [Resume lands on the first unanswered card](#4-resume-lands-on-the-first-unanswered-card)
5. [The §3.3 flow: building → poll → card → grade → results](#5-the-33-flow)
6. [Blinding — nothing engine-specific renders before results](#6-blinding)
7. [Sabotage log](#7-sabotage-log)
8. [Verification run](#8-verification-run)
9. [Manual TestFlight checklist](#9-manual-testflight-checklist)
10. [Deviations and notes for the lead](#10-deviations-and-notes-for-the-lead)

---

## 1. Tab presence at launch

**The read.** `mobile/src/navigation/TabNav.tsx:745-747`:

```ts
const [showCalibrationTab] = useState(
  () => !!useFeatureFlags.getState().flags['grading.blind'],
);
```

It is a `useState` initializer, so it runs once per `TabNav` mount — the same construction as `showDraftTab` at `:736-738` and `initialTab` at `:709`. It reads the flag store imperatively; there is no `useFlag('grading.blind')` anywhere in the file (guard assertion 6), so a mid-session flag revalidation cannot insert or remove the tab.

**Where the value comes from.** `useFeatureFlags.getState().flags` is the map `api/flags.ts` builds: base flags, then every running experiment's `configs[key].flags` overlay merged on top (`mobile/src/api/flags.ts:53-60`, returned at `:73`). `grading.blind` ships `false` globally and reaches a tester only through the `calibration_rollout` overlay, so at mount the store holds `true` iff the last successful flag fetch (or the cached merged map, `state/useFeatureFlags.ts:118-129`) carried that overlay for this unit.

**The slot.** `TabNav.tsx:871-917`:

```tsx
{showCalibrationTab ? (
  <Tab.Screen name="Calibration" … tabBarButtonTestID: 'tab.calibration' … />   // :873-891
) : showDraftTab ? (
  <Tab.Screen name="Draft" … tabBarButtonTestID: 'tab.draft' … />               // :898-916
) : null}                                                                        // :917
```

The two preceding tabs are `Rank` and `Trades` (`:832`, label `Acquire` at `:839`); the two following are `Matches` and `League`. So the third slot holds at most one of Calibration / Draft, and the bar never exceeds five tabs.

| `grading.blind` (overlay) | `draft.tab` | `showCalibrationTab` | `showDraftTab` | Third slot | Tab bar |
|---|---|---|---|---|---|
| on | **off** (ships off, P2) | true | false | `Calibration` (`:871` true-branch) | Rank · Acquire · **Calibration** · Matches · League |
| off | off | false | false | `null` (`:917`) | Rank · Acquire · Matches · League (4 tabs) |
| on | on | true | true | `Calibration` — the outer ternary is taken first, Draft is never reached | Rank · Acquire · **Calibration** · Matches · League |
| off | on | false | true | `Draft` (`:892` branch) | Rank · Acquire · **Draft** · Matches · League — byte-identical to today's five-tab bar |

The Draft `<Tab.Screen>` at `:898-916` is the pre-P3 element moved into the else-branch unchanged (options, listeners, `initialParams`-free `DraftStackNav`, `'tab.draft'`), so `scripts/testid-lint.sh` still resolves `mobile/.maestro/capture/draft-room@draft.yaml`. `initialRouteName={initialTab}` (`:777`) resolves `'Rank'`/`'Trades'` by name, never by index, so the slot's contents do not shift launch routing.

**The stack behind the tab.** `TabNav.tsx:647-659` — `CalibrationStack` with one screen, `CalibrationHome` → `CalibrationScreen`, `chalklineHeader('Calibration')` (`:655`). `tabIcon('check')` at `:876`; `trackTab('calibration', navigation)` at `:885`, with the shared focused-re-tap `popNestedToTop` under `ux.retap_active_tab`.

**No FeedbackFAB of its own.** `CalibrationScreen.tsx` imports no `FeedbackFAB` (imports at `:1-24`; guard assertion 3). RootNav's single global mount at `mobile/src/navigation/RootNav.tsx:624` (`<FeedbackFAB activeScreen={activeScreen} />`, rendered beside `<TabNav />` at `:610`) covers every tab-stack screen, so the FAB on Calibration files against `CalibrationHome` with exactly one button.

## 2. The card loop

**The only card component is `GradingCard`.** `CalibrationScreen.tsx:9` imports it; `:429-431` is the one mount:

```tsx
<View testID="calibration.card">
  <GradingCard trade={card.trade} />
</View>
```

`card` is `nextQ.data.card` (`:201`), where `nextQ` (`:195-200`) is `getNextGradingCard(sessionId)` → `GET /api/grading/sessions/<id>/next` (`api/grading.ts:120-124`). `GradingNext`'s not-done member is `{done, session_id, progress, card}` and `GradingCard.trade` is a `GradingTrade` = `{partner_name, give, receive}` (`api/grading.ts`; guard assertion 2 pins both key sets). Nothing else from the response reaches the card: the screen reads `card.position` for the progress label (`:421-423`) and `progress.answered/total` for the meter (`:425`), and that is the whole surface.

**What the card renders.** `mobile/src/components/GradingCard.tsx`:
- imports only `react`, `react-native`, `../theme/chalkline`, `./chalkline`, and the type-only `../api/grading` (`:1-5`; guard assertion 1) — never `TradeCard`, `api/trades` or `shared/types`;
- header `TRADE WITH` + `trade.partner_name` (`:78-79`);
- `Column label="You give"` on `trade.give`, a 1-px rule, `Column label="You get"` on `trade.receive` (`:84-86`) — GIVE-LEFT / GET-RIGHT;
- per asset (`AssetRow`, `:36-57`): name, `PositionBadge` for QB/RB/WR/TE else `Badge "PICK"` / the raw position (`:49-50`), team · age (picks show neither), `value ?? '—'` (`:53`);
- per column a `TOTAL` of the non-null values (`:68`).

No meter, no reasons, no lane, no narrative, no likes-you pill, no Send, no colour beyond the position badges. `check-blind-grading.js` assertion 1 scans the comment-stripped source for the engine-identifying token list and the sabotage in §7 proves it fires.

## 3. `needs_fresh_deck` → Acquire

`startM` (`CalibrationScreen.tsx:158-167`) is `startGradingSession(leagueId)` → `POST /api/grading/sessions` (`api/grading.ts:112-118`). A 409 `{"error":"needs_fresh_deck", …}` surfaces as `startM.error`, an `ApiError` whose `body.error` is read by `errorCode` (`:103-106`).

Phase derivation (`:292-302`, first match wins):

```ts
else if (startM.error && errorCode(startM.error) === 'needs_fresh_deck') phase = 'needs-deck';   // :295
```

The `needs-deck` branch (`:317-328`) renders the lld §10.6 copy ("Open Acquire for this league first so there's a fresh deck to compare against, then come back.") and one primary button, `testID="calibration.open-acquire"` (`:322`), whose handler is `handleOpenAcquire` (`:264-267`):

```ts
startM.reset();
navigation.getParent()?.navigate('Trades');
```

`navigation` is the `CalibrationHome` screen's navigation (`useNavigation`, `:126`); its parent is the Tab navigator, and `'Trades'` is the Acquire tab's route name (`TabNav.tsx:832`, label `Acquire` at `:839`). The `startM.reset()` clears the error so that returning to Calibration lands on `intro` → Start rather than the stale message.

## 4. Resume lands on the first unanswered card

The intro's Resume button (`:384-407`) renders iff the server's current session is `open`:

```tsx
const open = serverSession?.status === 'open' ? serverSession : null;      // :385
… label={COPY.resume(open.progress.answered, open.progress.total)}         // :393
    onPress={() => setSessionId(open.session_id)}                           // :395
```

`serverSession` is `currentQ.data.session` (`:146-156`), i.e. `GET /api/grading/sessions/current?league_id=…` (`api/grading.ts:103-110`), fetched with `refetchOnMount: 'always'` and `staleTime: 0`, and the `['grading', …]` keys are not in `App.tsx:61`'s `PERSIST_KEYS`, so after a relaunch the server is the only source.

Setting `sessionId` enables `nextQ` (`:195-200`, `enabled: !!sessionId && !completedId`). The server's `next` route returns the first card without an answer (specs.md §3.2 route 3), so the first render of the `grading` phase shows that card's `position` (`:421-423`). The client holds no cursor of its own: after each answer it invalidates `['grading','next',sessionId]` (`:223`) and asks the server again. On the POST path the same thing happens: a 200 `resumed: true` with status `open` sets `sessionId` directly (`:164`), and a 202 `building` is picked up by the effect in §5.

## 5. The §3.3 flow

specs.md §3.3 (lead change 2026-10-02) wins over lld §10.3 wherever they differ. The screen's state machine:

| Step | Where | What |
|---|---|---|
| Start | `:158-167` | `startM.mutate()` → POST. On success the POST's own `SessionView` is written into the `current` query (`qc.setQueryData`, `:163`) so the poll starts from it; `open` ⇒ `setSessionId` (`:164`), `building` ⇒ fall through to the poll. |
| Poll | `:146-156` | `currentQ.refetchInterval` (`:153-154`) returns `BUILD_POLL_MS` = 1500 (`:67`) while `data.session.status === 'building'` and the cap has not fired; otherwise `false`. TanStack recomputes the interval on every data change and every options change, so the poll starts the moment the 202 lands and stops the moment the status leaves `building`. `refetchIntervalInBackground` is left at its default (`false`), so the poll pauses while the app is backgrounded. |
| Cap | `:188-193` | An effect armed when `buildSince` is set (first `building` observation, `:175-179`) fires `setBuildSlow(true)` at `buildSince + 60_000` (`BUILD_POLL_CAP_MS`, `:68`). `buildSlow` turns the interval off and selects the `build-slow` phase (`:300`), which renders "This is taking longer than usual. Try again." + `calibration.retry` (`:364-375`). Try again (`handleBuildRetry`, `:272-276`) restarts the clock and refetches — POSTing would only return the same `building` session as a resume, so re-reading is the honest action. |
| building → open | `:175-185` | When the polled status leaves `building` while the clock is running: `open` ⇒ `setSessionId(serverSessionId)` (`:181`), which enables `nextQ`; the clock is cleared either way. |
| building → failed | `:299`, `:343-354` | `serverStatus === 'failed'` selects the `failed` phase. Copy per `error.code` via `failedCopy` (`:111-112`): the `…too_few` code ⇒ "The new engine found too few trades for this league right now. Try another league."; anything else ⇒ "Something went wrong building the session. Start over to try again." The button is "Start over" and POSTs again (`startM.mutate()`, `:350`); a failed session is never resumed server-side, so this starts fresh. |
| Card | `:409-507` | §2 above. Grade buttons from the `GRADE_BUTTONS` table (`:48-54`, mapped at `:436`), tag chips from `TAG_CHIPS` (`:55-62`, mapped at `:464`), labels from `GRADING_TAG_LABELS`. `Next` (`calibration.submit`, `:490`) is disabled until a grade is picked; `Skip` (`calibration.skip`, `:498`) posts `{skip: true}`. |
| Answer | `:217-232` | `answerGradingCard(cardId, …)` → `POST /api/grading/cards/<id>` (`api/grading.ts:126-132`). Success clears the selection, then `session_status === 'completed'` ⇒ `setCompletedId` (`:222`), else invalidate `next` (`:223`). `session_completed` 409 ⇒ `setCompletedId` (`:226-229`); any other non-404 failure ⇒ Toast "Couldn't save that grade. Try again." with the selection kept (`:230`). A new `card_id` resets grade and tags (`:212-215`). `nextQ.data.done === true` also completes (`:207-210`). |
| Results | `:234-239`, `:509-530` | `resultsQ` = `getGradingResults(completedId)` → `GET …/results` (`api/grading.ts:134-138`). The `results` phase (`:297`) mounts `<GradingResults results={resultsQ.data} />` exactly once (`:513`) inside `testID="calibration.results"`, and `Done` (`calibration.done`, `:523`) → `handleDone` (`:254-259`): clear both ids, reset the mutation, invalidate `current` → the server now returns `null` → `intro` with Start. |
| League switch | `:244-253` | An effect on `leagueId` clears `sessionId`, `completedId`, the selection, the build clock and the mutation. `currentQ` re-keys on `leagueId` by itself. |
| Tab switch | — | Tab screens stay mounted; no effect depends on focus, so a switch to Matches and back leaves every piece of state where it was. |
| 404 anywhere | `:294` | Any `ApiError` 404 from the five queries/mutations selects `unavailable` ("Not available" / "Calibration isn't turned on for this account."). |
| Timeout | `api/client.ts:254`, `:340` | `/api/grading/sessions` is in `SLOW_POST_PATHS`, so the start POST gets the 30 s cap; the GET polls and the answer POST keep the 15 s default. |

## 6. Blinding

Nothing engine-specific renders before the results phase:

1. **Wire.** `api/grading.ts`'s `GradingNext` members are `{done, session_id, progress, card}` / `{done, session_id, progress}`; `GradingCard` = `{card_id, position, trade}`; `GradingTrade` = `{partner_name, give, receive}`; `GradingAsset` = `{id, name, position, nfl_team, age, value}`. No arm, reason, engine, basis, lane or score key exists on the pre-results types (guard assertion 2). `arms` appears only on `GradingResults`, the type the results route returns.
2. **Card.** `GradingCard.tsx` touches only `trade.partner_name`, `trade.give[]`, `trade.receive[]` and the six asset fields (§2). Its comment-stripped source contains none of `reasons?|arms?|model_arm|value_core|valueCore|engine|basis|lane|narrative|composite|fairness|mismatch|match_context|valuation|impression|trade_id|tradeId|preserve_server_order|likes_you|score` (guard assertion 1).
3. **Screen.** `CalibrationScreen.tsx` holds a card's `trade` and nothing else about it; its comment-stripped source contains no `value_core`, no `arm`/`arms`, no `.arms`, no `reason` (guard assertion 3). The one place the screen must react to the second engine's name — the `failed` session's `error.code`, whose prefix spells it — matches on the suffix instead (`failedCopy`, `:111-112`), precisely so the literal never enters this file.
4. **One reveal.** `value_core` and the labels "Today's engine" / "New engine" exist in exactly two files under `src/`: `api/grading.ts` (the type) and `components/GradingResults.tsx` (`ARM_LABEL`, `:21`; rendered at `:71`), which the screen mounts only in the `results` phase (`:513`). Guard assertion 4 walks all of `src/` for both.
5. **Analytics.** The screen emits no events; the only new analytics value is `tab_selected.tab = 'calibration'` from `TabNav.tsx:885`, a navigation fact that names no arm.

## 7. Sabotage log

Each violation was planted, the guard run, the FAIL line captured, and the file restored byte-identical (`cmp`) before the next. Run 2026-10-02 against the P3 tree.

| # | Planted | Guard output | Restored |
|---|---|---|---|
| 1 | `GradingCard.tsx`: `const leaked = (asset as any).reasons;` inside `AssetRow` | `FAIL  src/components/GradingCard.tsx: no engine-identifying token` — `1 check(s) failed.` | yes (`cmp` clean) |
| 2 | `CalibrationScreen.tsx`: `<FeedbackFAB activeScreen="CalibrationHome" />` beside the `<Toast>` | `FAIL  src/screens/CalibrationScreen.tsx: no FeedbackFAB` — `1 check(s) failed.` | yes |
| 3 | `CalibrationScreen.tsx`: `const leaked = "value_core";` at module scope | `FAIL  src/screens/CalibrationScreen.tsx: no arm-identifying token` **and** `FAIL  src/: value_core confined` — `2 check(s) failed.` | yes |
| 4 | `TabNav.tsx`: `useState(() => !!useFeatureFlags.getState().flags['grading.blind'])` replaced by `useFlag('grading.blind')` | `FAIL  src/navigation/TabNav.tsx: showCalibrationTab` **and** `FAIL  src/navigation/TabNav.tsx: no useFlag('grading.blind')` — `2 check(s) failed.` | yes |

Assertion 0 (the scanner self-test) additionally proves, on every run, that the scan fires on a planted `card.reasons`, stays clean on `card.trade`, ignores a `// card.reasons` comment, and survives a template literal with `${…}` substitutions.

## 8. Verification run

From `mobile/` on the P3 tree, 2026-10-02 (`npm ci` first — `node_modules` is gitignored):

| Command | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `bash scripts/testid-lint.sh` | `testid-lint OK`, exit 0 |
| `node tests/check-blind-grading.js` | 27 PASS, `All blind-grading checks passed.`, exit 0 |
| `npm run test:blind-grading` | same guard via the new script |
| `for f in tests/check-*.js; do node "$f" > /dev/null \|\| echo "FAIL $f"; done` | prints nothing (100 guards incl. `check-settings-nav`, `check-settings-testids`, `check-rank-nav-exit`, `check-dna-side-order`) |

The same three commands were run on the untouched tree first (baseline): also all green, so every result above is attributable to P3's changes alone.

## 9. Manual TestFlight checklist

The runtime half of the evidence (D-056). Operator runs it on a build containing P1–P3; the lead logs the outcome in `living-memory/TEST_LEDGER.md`. This expands scope.md §3's steps with what each one proves about THIS code.

**Prerequisites**
- [ ] Operator's account id is in `config/tester_allowlist.json`.
- [ ] `calibration_rollout` is **running**; `GET /api/feature-flags` with the operator's session (and the device's `X-Device-Id`) shows `configs.calibration_rollout.flags["grading.blind"] = true`.
- [ ] `draft.tab` is `false` in the deployed `config/features.json`, and `POST /api/feature-flags/reload` has run.
- [ ] `trade.value_core` is `false`.
- [ ] Acquire (Trades) was opened for **League A** within the last 7 days as an organic deck (no shop-a-player, no partner scope, no intent).

**Steps**

| # | Do | Expect | Proves |
|---|---|---|---|
| 1 | Force-quit, relaunch. | Tab bar reads **Rank · Acquire · Calibration · Matches · League** (check icon on the third tab). No Draft tab. | §1 row 1 — mount-once read with the overlay on. |
| 2 | League tab › Explore › **Rookie draft** tile. | The Draft Room opens as a pushed page with its own back control. | The Draft code survived; only the tab is gone. |
| 3 | Tap **Calibration**. | Header "Calibration"; an ice-tick "CALIBRATION" label; intro copy naming League A and saying some ideas come from today's engine and some from the new one; one **Start** button. No feedback-FAB doubling (exactly one FAB on screen). | intro phase; global FAB only. |
| 4 | Tap **Start**. | A spinner with "Building your deck…" appears **first** (not the card), then within ~15 s card **1 / N** with 20 ≤ N ≤ 40. | §5 Start → 202 → poll → open. If the card appears with no spinner at all, note it (it means the build finished before the first poll — acceptable, but record the time). |
| 5 | Inspect the card. | "TRADE WITH" + the partner's name; **You give** left, **You get** right; each asset shows name, a position badge (or `PICK`), team · age for players, a value; each column ends in a TOTAL. **No** reason lines, no fairness meter, no lane chips, no "They're interested" pill, no Send button, no engine name anywhere. | §2 + §6. |
| 6 | Tap **4**, tap the **Overpay** chip, tap **Next**. | 4 turns ice-bordered on tap, Overpay turns ice-bordered on tap; after Next: **2 / N**, with no grade and no chip pre-selected. | answer → invalidate → next card; selection reset on new card. |
| 7 | Tap **Skip**. | **3 / N**. Next was disabled before you picked a grade; Skip was not. | skip path; Next gating. |
| 8 | Switch to **Matches**, then back to **Calibration**. | Still on card **3 / N**. | state survives a tab switch (screen stays mounted). |
| 9 | Force-quit, relaunch, tap **Calibration**. | Intro shows **Resume (2 of N answered)**; tapping it lands on card **3 / N**. | §4 — the server is the resume source; the client holds no cursor. |
| 10 | Re-tap the focused **Calibration** tab. | Nothing changes (one-screen stack). No crash. | `popNestedToTop` no-op. |
| 11 | Open **Acquire** for League A, then Matches. | The deck is unchanged by grading; no new likes in Matches; no new passed dispositions. | grading writes only grading tables (P1/P2 guarantee, observed from the client). |
| 12 | Grade the rest (any grades; include at least one more Overpay). | After the last answer the screen shows **Results**: two blocks, "**Today's engine**" and "**New engine**", each with Cards / Graded / Skipped / Average / Would send (4–5) / Top reasons, and "Overpay ×k" appears; a footer line "_k_ trades were suggested by both engines and count for both."; a **Done** button. | §5 Results; §6 item 4 — this is the first and only place an engine is named. |
| 13 | Tap **Done**, then reopen Calibration. | Intro with **Start** (no Resume). | Done → invalidate current → null. |
| 14 | Switch the active league (TopBar) to **League B**, where Acquire was NOT opened in the last 7 days. Tap **Start**. | "Open Acquire for this league first so there's a fresh deck to compare against, then come back." with an **Open Acquire** button; tapping it lands on the **Acquire** tab. Coming back to Calibration shows **Start** again (not the message). | §3 — 409 `needs_fresh_deck` → Trades; `startM.reset()` on the way out. |
| 15 | On League B, tap the feedback button. | Exactly **one** button; the sheet pre-fills screen **CalibrationHome**. | global FAB covers the tab screen. |
| 16 | Lead: `curl -s -H "X-Cron-Secret: $CRON_SECRET" "$API/api/admin/grading/report"`. | The step-12 session is present; its per-arm `n` / `skipped` / `mean` / `share_ge_4` / `tag_counts` match the Results screen's numbers. | the client renders the server's summary verbatim. |
| 17 | Second device, signed in as a **non-allowlisted** account. | 4 tabs: no Calibration, no Draft. | §1 row 2. |
| 18 | **Stop** `calibration_rollout`; wait ≥ 60 s (flag cache TTL); on the tester device tap Start (or Resume). | "**Not available** — Calibration isn't turned on for this account." After a force-quit + relaunch, the Calibration tab is **gone** (4 tabs). | 404 → `unavailable`; mount-once presence re-reads the overlay-less map at the next launch. |
| 19 | *(Optional, if the lead can stall a build — e.g. pause the worker or point the device at a local server that sleeps in `build_session`)* Start on League A. | Spinner for 60 s, then "This is taking longer than usual. Try again." with a **Try again** button; tapping it resumes the spinner. | §5 cap. If no stall is available, record "not exercised" — the cap is otherwise only proven by the code-walk. |
| 20 | *(Optional, needs a league where the value core yields < 10 cards — local dev with no `player_value_history` rows does this)* Start. | Spinner, then "The new engine found too few trades for this league right now. Try another league." with **Start over**. | §5 failed path and the `…too_few` copy. |

Record the N from step 4, the build time from step 4, and any step that deviated.

## 10. Deviations and notes for the lead

1. **Two §3.3 states reuse existing testIDs.** §3.3 added the `failed` ("Start over") and 60-s-cap ("taking longer than usual — try again") states after scope.md §3 fixed the testID set, and the guard (assertion 5) requires the set to match scope §3 exactly. Rather than widen the set unilaterally: **Start over** carries `calibration.start` (it is the same POST), the slow-build **Try again** carries `calibration.retry` (same semantics as the error phase's Try again), and the building spinner carries `calibration.loading`. Only one of each renders at a time. If you would rather have distinct ids (`calibration.failed`, `calibration.build-slow`), that is a one-line change in scope.md §3 + `REQUIRED_IDS` in the guard + the two `testID=` attributes.
2. **The `too_few` match is on the suffix.** `CalibrationScreen.tsx:111-112` uses `error.code.endsWith('too_few')` instead of comparing to the literal code, because the literal's prefix is the arm name the file is pinned never to contain (guard assertion 3 / scope §3 item 3). The alternative — a copy table in `GradingResults.tsx`, the one other file allowed the literal — put failure copy in a results component, which seemed worse.
3. **`mobile/tests/README.md`'s count was already stale.** lld §10.7 said "Count 87 → 88"; I did exactly that. But the directory held 99 `check-*.js` files before P3 (100 after), and every one now has an `npm run` script (the README's "all but one, `check-mascot-ram`" is also out of date). Not touched beyond the specced edit — flagging for whoever next owns that README.
4. **`client.ts` comment wording.** The hld §7 table still describes the pre-§3.3 inline build. The comment I added at `client.ts:247-253` says the POST answers 202 quickly today and explains why the 30 s cap is still worth keeping (cold start + inline arm selection + safe resume), so it does not restate the stale timing.
5. **Not edited, per lld §10.7:** `RootNav.tsx`, `deepLinks.ts`, `shared/types.ts`, `testRouteEntry.ts`, the Settings screens, and every `CLAUDE.md` (lead-only).
6. **`npm ci`** was required in the worktree (`node_modules` absent); it succeeded with no lockfile churn (`git status` shows no `package-lock.json` change).
