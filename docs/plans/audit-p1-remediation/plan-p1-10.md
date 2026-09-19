# P1-10 — Sleeper Connect analytics (audit A-19)

> **Status:** plan only — no code written. Re-verified line-by-line against worktree
> `ftf-p1-remediation` @ `ab9368f` (branch `p1-remediation-2026-08-11`, == `origin/main`).
> **Source:** audit `04-priority-backlog.md` §P1 row P1-10; `06-resolutions.md:104` (A-19).
> **Upstream dependency:** `ftf-p0-remediation/docs/plans/audit-p0-remediation/plan-p0-7.md`
> owns the analytics taxonomy and **merges to `main` before this item builds**. Every rule
> below is P0-7's; this item lives entirely inside them.
> **Gate posture:** full gates. Root `CLAUDE.md` bright line — *"a change touching schema,
> API contracts, feature-flag surfaces, or **analytics events** is not a quick fix."*
> Analytics events *are* this item. Scope block: [`scope-p1-10.md`](scope-p1-10.md).

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. Design](#2-design)
- [3. Exact change list](#3-exact-change-list)
- [4. Surface changes](#4-surface-changes)
- [5. Maestro delta](#5-maestro-delta)
- [6. Docs impact table](#6-docs-impact-table)
- [7. Test plan](#7-test-plan)
- [8. Risks and cross-item collisions](#8-risks-and-cross-item-collisions)
- [9. Operator checkpoints](#9-operator-checkpoints)

---

## 1. Verified current state

### 1.1 The finding holds — `SleeperConnectScreen.tsx` fires nothing

`mobile/src/screens/SleeperConnectScreen.tsx` is **195 lines**. It contains **zero
`track()` calls and does not import `track` at all** — verified by reading the whole file
and by `grep -rn "track(" mobile/src/screens/SleeperConnectScreen.tsx` returning nothing.
Its full import list (`:1-7`) is React, RN primitives, `WebView`, `useNavigation`, the
Chalkline theme, `linkSleeperToken`/`persistSleeperToken`, `useSession`. No analytics.

The flow, with current line numbers:

| Step | Line(s) | Detail |
|---|---|---|
| Mount | `:48` | **No `useEffect` exists anywhere in the file.** There is no mount hook and no unmount cleanup to hang an abandon signal on — both must be added. |
| WebView login | `:138-147` | `SLEEPER_LOGIN_URL = 'https://sleeper.com/login'` (`:22`). `INJECTED_POLLER` (`:27-46`) polls `localStorage['token']` every 800 ms and `postMessage`s the JWT once. |
| Token arrives | `:54-65` | `onMessage` parses, rejects non-`token` payloads (`:63`), then sets `capturedRef.current = true` (`:65`). |
| Server link | `:66-68` | `setPhase('linking')`, `await linkSleeperToken(token)` → `POST /api/sleeper/link`. |
| Success | `:78-95` | `isVerified = res?.verified === true` (`:78`); Keychain persist (`:76`, `.catch(()=>{})` so it can never throw into the catch); optional `setVerification` (`:80-91`); `setPhase('done')` (`:94`); `setTimeout(goBack, 1200)` (`:95`). |
| Failure | `:96-102` | `capturedRef.current = false` (`:100`) — **the retry enabler**; `setPhase('error')` (`:101`). |
| Rendered states | `:107-168` | Banner + consent copy (`:109-136`), error copy (`:130-135`), `linking` overlay (`:149-154`), `done` overlay (`:156-167`). |

**Route registration:** `RootNav.tsx:702-711`, `presentation: 'modal'`, `headerShown: true`,
title "Connect Sleeper". Param type `SleeperConnect: undefined` at `RootNav.tsx:58`.
Unlike `EspnConnect` (`:721-744`) it has **no custom `headerLeft` and no back-button
`testID`** — dismissal is the native modal chevron or a swipe-down, both of which unmount
the screen, so a cleanup-based abandon signal is sound.

**Exactly four navigation call sites** (full `grep -rn "SleeperConnect" mobile/src`; no
deep-link route, no programmatic route in `deepLinks.ts`, and `useSession.ts:495` is a
*comment* about the banner, not a navigate):

| # | Site | Context | Proposed `source` |
|---|---|---|---|
| 1 | `SendInSleeperButton.tsx:114` (`goConnect`, `:112-115`) | Send blocked on an unlinked/expired account | `send_button` |
| 2 | `RootNav.tsx:437` | `VerifyAccountBanner` "Verify" over the authed tabs | `verify_banner` |
| 3 | `SettingsScreen.tsx:1261` | Settings → "Verify account" row | `settings_row` |
| 4 | `SettingsScreen.tsx:488` | `promptVerifyStepUp` alert → "Verify now" | `settings_stepup` |

`navigateFromSettings(route, params?)` (`SettingsScreen.tsx:220-227`) **already accepts a
params argument**, so sites 3 and 4 need no helper change.

### 1.2 The ESPN twin — exact events and property shapes

`mobile/src/screens/EspnConnectScreen.tsx` imports `track` at `:10` and fires **four**
events, each with `screen` = `'EspnConnect'`:

| # | Exact call site | Exact call |
|---|---|---|
| 1 | `:199` (inside a mount `useEffect`, `:198-209`) | `track('espn_connect_opened', { source: 'link_sheet' }, 'EspnConnect')` |
| 2 | `:245` (inside `onMessage`, guarded by `!sawOtpRef.current`) | `track('espn_connect_otp_step', {}, 'EspnConnect')` |
| 3 | `:187` (inside `tryCapture`, after the post-await re-guard) | `track('espn_connect_captured', { saw_otp: sawOtpRef.current }, 'EspnConnect')` |
| 4 | `:204` (the same effect's **cleanup**, guarded by `!capturedRef.current`) | `track('espn_connect_abandoned', { saw_otp: sawOtpRef.current }, 'EspnConnect')` |

Server registration, verified:

- `backend/analytics_taxonomy.py:97-98` — the four names in `ALLOWED_CLIENT_EVENTS`
  (comment block `:90-96`; the frozenset closes at `:99`).
- `backend/analytics_taxonomy.py:251-254` — the prop rows (comment `:247-250`;
  `CLIENT_EVENT_PROPS` closes at `:255`):
  ```python
  "espn_connect_opened":    frozenset({"source"}),
  "espn_connect_otp_step":  frozenset(),
  "espn_connect_captured":  frozenset({"saw_otp"}),
  "espn_connect_abandoned": frozenset({"saw_otp"}),
  ```
- `docs/business/analytics/2026-07-17-tracking-plan-v2.md:146-156` — "Addendum 2026-08-08
  — ESPN Connect WebView", an **in-file addendum section**, with the four-row event table.

**The naming pattern, stated precisely:** `<platform>_connect_<past-tense-outcome>`,
snake_case, one `opened`, one terminal success (`captured`), one terminal failure
(`abandoned`), and one **platform-specific hard-step marker** (`otp_step`) whose occurrence
is echoed as a boolean prop (`saw_otp`) on *both* terminals so either terminal can be split
by "did the hard step gate this?". This plan mirrors that pattern, not the literal strings.

**"Abandoned" mechanically, in the twin:** it is a **React effect cleanup on unmount**
(`:200-208`), not a back-press listener and not a timeout. It fires on header back, swipe
dismissal, and any other unmount, and is suppressed only by `capturedRef.current === true`.
`EspnConnectScreen` also sets `unmountedRef` (`:131`, `:201`) so an in-flight async cookie
read cannot fire `captured` *after* `abandoned`. **The detection method transfers to the
Sleeper screen unchanged** — the screen unmounts on modal dismissal exactly the same way.
The only thing missing there is the `useEffect` itself.

### 1.3 The OTP step does **not** map 1:1 — the load-bearing verification

ESPN's `espn_connect_otp_step` is fired by an injected `MutationObserver`
(`EspnConnectScreen.tsx:88-113`) matching **Disney-SSO-specific selectors**
(`:95-97`): `input[autocomplete="one-time-code"], input[name="otp"],
input[data-testid="OneTimePasscode"]`.

Sleeper's login **does have** an OTP/2FA leg, but it is entirely Sleeper's:

- `docs/plans/sleeper-write-capture-runbook.md:128` — *"it opens Sleeper's own login page in
  a webview, lets Sleeper handle password / OTP / passkey / 2FA, then reads
  `localStorage['token']`."*
- `:129`, `:134` — the JWT carries a `valid_2fa` claim; *"2FA is fully resolved on Sleeper's
  side during the webview login."*

Three facts follow, all verified:

1. `INJECTED_POLLER` (`SleeperConnectScreen.tsx:27-46`) has **no DOM observation at all** —
   it reads one `localStorage` key. There is no OTP detector to extend.
2. This repo holds **no verified selector** for Sleeper's OTP input. The ESPN selectors were
   derived from Disney's DOM; nothing equivalent exists for `sleeper.com/login` in
   `docs/references/`, `docs/integrations/sleeper.md`, or the capture runbook.
3. Shipping a DOM-sniffing `sleeper_connect_otp_step` against an unverified third-party DOM
   yields an event that is **permanently zero and indistinguishable from "no user ever hit
   OTP"**. That is the A-33 failure class exactly — an artifact asserting something runtime
   does not do — and it is unfalsifiable without a live TestFlight session on an OTP-gated
   Sleeper account.

**Sleeper's real hard step is the server-side link rejection.** The capture is not the end
of the flow the way it is for ESPN: ESPN's screen hands cookies to a sheet with no server
round-trip, whereas Sleeper's screen posts the JWT to `POST /api/sleeper/link`, which can
reject it. The screen's own error copy (`:130-135`) names the dominant case: *"make sure you
log in to the same Sleeper account you use here"* (i.e. `token_user_mismatch`). That is the
drop-off curve the audit is asking for, and it is fully observable client-side today.

Closed error enum for `POST /api/sleeper/link` (`backend/server.py:12163-12290`, read in
full): `feature_disabled` (404) · `no_user` (401) · `sleeper_unconfigured` (503) ·
`invalid_token` (400) · `token_expired` (400) · `token_user_mismatch` (403) ·
`token_rejected` (403) · `store_failed` (500). Plus three client-synthetic values
(`timeout`, `network`, `unknown`) = **11 values, bounded forever**.

### 1.4 Reserved names — checked, and the answer is nuanced

`backend/analytics_queries.py` was read at `:45-105`. **No `sleeper_connect_*` name is
reserved anywhere in it.** `WAT_LIVE`/`WAT_DARK` (`:51-53`) reserve only the three
`sleeper_send_*` names (P0-7's item, not this one); `FUNNEL_STAGES` (`:69-80`) and
`FEATURE_VERTICALS` (`:83-96`) contain no connect-flow stage. A repo-wide grep for
`sleeper_connect` returns **exactly one hit**, and it is prose, not a registry:

> `docs/integrations/sleeper.md:408` — *"Worth a client event (`sleeper_connect.abandoned`
> or similar) if funnel visibility into this step matters."*

That is a soft suggestion, and its **dotted spelling violates the taxonomy convention**
(every registered name is snake_case with no dots — see `analytics_taxonomy.py:38-99`).
Adopting the *idea* while correcting the *string* to `sleeper_connect_abandoned` is the
right move, and the doc line must be fixed so a future builder does not copy the illegal
form into `track()` and get it silently dropped.

### 1.5 Drift from audit

| Audit claim (`04-priority-backlog.md` P1-10 / `06-resolutions.md:104`) | Verified reality |
|---|---|
| "Sleeper Connect has **zero** analytics" | **Overstated, and the correction matters.** Screen-authored analytics are zero — true. But `RootNav.tsx:352` (boot) and `:376` (`onStateChange`) fire `screen_viewed` for **every** route including this modal (`navigationRef.getCurrentRoute()` resolves to `SleeperConnect` when the modal is presented), and `:366` fires `screen_left` with a real `dwell_ms`. So mount count and dwell already exist today; **what is missing is every in-flow outcome** — logged in or not, linked or rejected, verified or inconclusive. Framing the fix as "the screen is dark" would lead a builder to duplicate `screen_viewed`. |
| "Mirror the four events its ESPN twin fires — opened, captured, abandoned, **OTP step**" | Three of four mirror cleanly. **`otp_step` does not** — see §1.3. Sleeper has an OTP leg but no detectable signal and no verified selector; its structural counterpart is the link rejection. |
| "Effort S" | Holds. ~40 lines of client change, 8 registry lines, 4 one-line call-site edits, one route-param type. |
| "This flow gates Send-in-Sleeper and verification" | Confirmed and stronger than stated: `/api/trades/propose` hard-gates on `sess["verified"]` with **no grace period** (`server.py:12321-12329`), and the *only* way a Sleeper-keyed session becomes verified is `POST /api/sleeper/link` — i.e. this screen. It also gates every account-data action behind `promptVerifyStepUp`. |
| A-19 typed "Bug" | Agreed — instrumentation absence, no user-visible behaviour change. |

---

## 2. Design

Four events, mirroring the ESPN naming pattern exactly: `sleeper_connect_<past-tense>`,
snake_case, `screen` = `'SleeperConnect'` on every call. Slot 4 is Sleeper's hard-step
marker in place of ESPN's `otp_step`, and its occurrence is echoed as `saw_error` on both
terminals — the structural role `saw_otp` plays in the twin.

### 2.1 The four events

| # | Event | Props (type · values) | Trigger moment (file:line today) | Intent? |
|---|---|---|---|---|
| 1 | `sleeper_connect_opened` | `source` str ∈ `send_button \| verify_banner \| settings_row \| settings_stepup \| unknown` | New mount `useEffect` body, first statement. Mirrors `EspnConnectScreen.tsx:199`. Inserted at `SleeperConnectScreen.tsx:~53` | **INTENT** |
| 2 | `sleeper_connect_failed` | `reason` str (closed 11-value enum, §1.3); `status` int\|null; `attempt` int (1-based token-capture index this mount) | First statement of the existing `catch` block, `:96` — **before** `capturedRef.current = false` (`:100`) so the retry reset cannot race the read | **INTENT** |
| 3 | `sleeper_connect_captured` | `verified` bool (`res?.verified === true`); `saw_error` bool (a `failed` fired earlier this mount); `attempts` int | Success path, immediately after `isVerified` is computed (`:78`) and before `setPhase('done')` (`:94`) | **INTENT** |
| 4 | `sleeper_connect_abandoned` | `phase` str ∈ `browsing \| linking \| error`; `saw_error` bool; `attempts` int | The mount effect's **cleanup**, guarded by `!linkedRef.current`. Mirrors `EspnConnectScreen.tsx:204` | **INTENT** |

**Property-shape mirror, row by row:** `source` is ESPN's `source`, same name, widened from
one value to four because Sleeper genuinely has four entry points (§1.1) where ESPN has one.
`saw_error` occupies `saw_otp`'s slot on both terminals — same boolean-marker role, honest
name for a different hard step. `attempts` / `attempt` and `phase` / `verified` / `reason` /
`status` are net-new because Sleeper's flow has a server leg and a retry loop that ESPN's
does not; each is justified in §2.3.

### 2.2 Intent classification — all four INTENT, deliberately

`analytics_queries.py:65` — `INTENT_EVENTS = (SERVER_FIRED | ALLOWED_CLIENT) −
NON_INTENT_EVENTS`. INTENT is a **deny-list**: new names are intent by default, and only an
explicit `NON_INTENT_EVENTS` addition removes them from DAU / WAU / MAU / churn / retention.

`NON_INTENT_EVENTS` today (`:60-63`) is exactly:
`app_opened, app_backgrounded, app_open, screen_viewed, push_sent, client_error, api_call,
api_request`. **None of the four `espn_connect_*` events is in it** — the twin ships all four
as INTENT. This plan mirrors that.

**Decision, stated per event: `sleeper_connect_opened`, `_failed`, `_captured`, `_abandoned`
are all INTENT. `analytics_queries.py` gets NO edit.**

Justification, because "no edit" must be a decision rather than an oversight:

- None of the four is impression-class. Every one is downstream of a deliberate tap on
  Connect / Verify at one of the four entry points in §1.1 — there is no passive path onto
  this screen (no deep link, no auto-navigate; `useSession.ts:498-514` only sets banner
  state, it does not navigate).
- The DAU/WAU exposure is bounded and correct. The only net-new active user this creates is
  someone who opens the app, taps Verify, and does nothing else — which is a genuinely
  active session and *should* count.
- `screen_viewed` for this route already fires and is already NON_INTENT (`:61`), so mount
  volume is not what these events add.
- Mirroring the twin keeps `espn_connect_*` and `sleeper_connect_*` comparable in every
  metric. Splitting their intent classification would make the two platforms' connect
  funnels un-diffable, which is the one comparison this data exists to support.

### 2.3 Design decisions that are not free, and why

**(a) `captured` fires on link SUCCESS, not on token arrival — a stated deviation.**
`espn_connect_captured` fires the instant the credential is in hand, because on that screen
that *is* the terminal (`EspnConnectScreen.tsx:187-193`: track, deliver, `goBack`). On the
Sleeper screen the credential in hand is the *middle*. Firing `captured` at token arrival
(`:65`) would make `opened → captured` mean "logged in to Sleeper", not "connected", and
would double-count on retry (`capturedRef` is reset to `false` at `:100`).

Firing it at success instead yields a partition that is **mutually exclusive and
exhaustive** per mount:

```
sleeper_connect_opened            × 1
  sleeper_connect_failed          × 0..n      (each rejected link attempt)
  then exactly ONE of:
    sleeper_connect_captured      (linked; verified true or false)
    sleeper_connect_abandoned     (phase = browsing | linking | error)
```

"Did they ever log in to Sleeper?" is not lost — it is `attempts ≥ 1` on whichever terminal
fires. Connect success rate is a clean `captured / opened`.

**(b) `phase` on `abandoned` closes a hole the twin does not have.** If the guard were
`capturedRef` (the literal ESPN mirror), a user who logs in and backs out while
`linkSleeperToken` is still in flight would fire **neither** terminal — `capturedRef` is
already `true` at `:65`, so no abandon; and the awaited continuation never reaches
`captured`. The mount would vanish. Guarding on a **new `linkedRef`** (set only on the
success path) makes that case fire `abandoned` with `phase: 'linking'`. `phase: 'error'`
separates "rejected then gave up" from `phase: 'browsing'` = "never logged in".

**(c) The cleanup must read refs, not state.** A `useEffect(..., [])` cleanup closes over
the render in which it was created; reading `phase` (a `useState` at `:50`) there would
always yield `'browsing'`. `phaseRef` / `sawErrorRef` / `attemptsRef` / `linkedRef` are
required for correctness, not style. `EspnConnectScreen` uses the same pattern
(`sawOtpRef` `:130`, `capturedRef` `:129`).

**(d) `reason` derivation** — mirrors P0-7 §2 Addition 3's `error_code` shape verbatim:

```ts
const reason = e instanceof ApiError
  ? (e.isTimeout ? 'timeout' : ((e.body as any)?.error ?? 'unknown'))
  : 'network';
const status = e instanceof ApiError ? e.status : null;
```
`ApiError` carries `status`, `body`, `isTimeout` (`mobile/src/api/client.ts:162-175`);
`linkSleeperToken` goes through `api.post` (`sendInSleeper.ts:46-48`, `client.ts:618-622`),
so it throws `ApiError`. Cardinality is closed at 11 (§1.3).

**(e) `source` is validated, not trusted.** The screen reads
`useRoute().params?.source` and coerces anything outside the four-value allowlist to
`'unknown'`, so a future caller that forgets the param cannot open the prop's cardinality.
`unknown` is a real, expected value — not a bug marker.

**(f) The device-`platform` vs league-`platform` trap — explicitly avoided.**
**None of these four events carries a `platform` prop of any kind.** Device platform is a
**server-derived column** on `user_events`, stamped in `analytics_ingest.py` from the
`X-Device` headers that `events.ts:283-290` spreads into every `POST /api/events` — that is
the fix for the pre-2026-08-05 NULL-`platform` incident cited in the taxonomy's own comment
(`analytics_taxonomy.py:256-260`). Where a *league* platform prop is legitimate the name
`platform` means Sleeper/ESPN/MFL/Fleaflicker (the `league_selected` precedent,
`analytics_taxonomy.py:185`). **Neither applies here:** the league platform of a
`sleeper_connect_*` event is a tautology (it is always Sleeper — that is what the event name
says), and the device platform arrives as a column for free. Adding either prop would be
redundant at best and would re-create the ambiguity that caused the incident at worst.
§7.2 asserts the column is `'ios'` and not NULL as a direct regression check.

**(g) Nothing about the credential is ever a prop.** No JWT, no fragment, no length, no
`sleeper_user_id`, no `valid_2fa` claim. The token goes to `POST /api/sleeper/link` and
nowhere else — the same invariant the ESPN registry comment states for its cookies
(`analytics_taxonomy.py:249-250`). `_scrub_pii` runs server-side on client props anyway, but
this is a design rule, not a reliance on the scrubber.

---

## 3. Exact change list

Ordered. **Commit 1 is the taxonomy registration and it merges before a single `track()`
call exists in the client.** This is not stylistic sequencing: `analytics_ingest.py`
`_health_bump("dropped_unknown_type")`-and-returns-200 on any `event_type` not in
`ALLOWED_CLIENT_EVENTS`. There is no error signal on either side. Client-first means events
that vanish behind a success response — the exact prior art P0-7 was written about.

### Commit 1 — registration (server + tracking plan + test). MUST LAND FIRST.

| # | File | Change |
|---|---|---|
| 1.1 | `backend/analytics_taxonomy.py` — `ALLOWED_CLIENT_EVENTS`, insert after the ESPN block at `:98`, before the `})` at `:99` | Add a commented block + the four names: `"sleeper_connect_opened", "sleeper_connect_failed",` / `"sleeper_connect_captured", "sleeper_connect_abandoned",`. Comment must record: (a) mirrors the ESPN Connect four; (b) **no OTP-step event** and why (§1.3 — no verified selector; a permanently-zero event is worse than none); (c) no credential/JWT prop exists or may be added; (d) all four are INTENT by decision, not omission. |
| 1.2 | `backend/analytics_taxonomy.py` — `CLIENT_EVENT_PROPS`, insert after the ESPN rows at `:254`, before the `}` at `:255` | Four rows. **A missing row raises `ValueError` at import (`:327-332`) and the app will not boot** — 1.1 and 1.2 ship together or not at all: <br>`"sleeper_connect_opened":    frozenset({"source"}),`<br>`"sleeper_connect_failed":    frozenset({"reason", "status", "attempt"}),`<br>`"sleeper_connect_captured":  frozenset({"verified", "saw_error", "attempts"}),`<br>`"sleeper_connect_abandoned": frozenset({"phase", "saw_error", "attempts"}),` |
| 1.3 | `backend/analytics_queries.py` | **NO EDIT — decision, not oversight.** All four are INTENT (§2.2). Recorded here, in the addendum, and in `DECISIONS.md` so a later reader does not "fix" it. |
| 1.4 | `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | New section **"Addendum 2026-08-11 — Sleeper Connect (A-19 / P1-10)"** placed directly after the ESPN addendum (`:146-156`), in the identical shape: four-row event table, the no-credential-prop rule, and a **"What is deliberately NOT here"** paragraph naming the OTP step, `valid_2fa`, the confirm/cancel beats, and the Keychain silent-replay path. **In-file addendum, not a new file** — that is the ESPN Connect precedent for a connect-flow addendum, and P1-10 mirrors its twin. (P0-7 creates a standalone addendum file for a much larger, cross-surface batch; the two conventions coexist.) |
| 1.5 | `backend/tests/test_events_api.py` | New `test_sleeper_connect_events_accepted` — §7.1. |
| 1.6 | `backend/tests/test_analytics_p0.py` | Extend `test_live_taxonomy_is_disjoint`'s membership assertion with the four names. |

**Disjointness pre-verified.** None of the four names appears in `SERVER_FIRED_EVENTS`
(`analytics_taxonomy.py:105-136`), `database._EVENT_TO_USER_COL`, or `_RANK_STREAK_EVENTS`.
`_assert_namespaces_disjoint` (`:298-322`) will pass. No name collides with P0-7's
`sleeper_send_*` set. `FUNNEL_CRITICAL` is **not** touched — the twin is not in it either.

### Commit 2 — client wiring (only after commit 1 is on `main`)

| # | File → line | Change |
|---|---|---|
| 2.1 | `mobile/src/navigation/RootNav.tsx:58` | `SleeperConnect: undefined;` → `SleeperConnect: { source?: 'send_button' \| 'verify_banner' \| 'settings_row' \| 'settings_stepup' } \| undefined;` (mirror the comment style used for `EspnConnect` at `:59-65`). |
| 2.2 | `mobile/src/navigation/RootNav.tsx:437` | `navigation.navigate('SleeperConnect')` → `navigation.navigate('SleeperConnect', { source: 'verify_banner' })` |
| 2.3 | `mobile/src/components/SendInSleeperButton.tsx:114` | → `navigation.navigate('SleeperConnect', { source: 'send_button' })` |
| 2.4 | `mobile/src/screens/SettingsScreen.tsx:488` | → `navigateFromSettings('SleeperConnect', { source: 'settings_stepup' })` |
| 2.5 | `mobile/src/screens/SettingsScreen.tsx:1261` | → `navigateFromSettings('SleeperConnect', { source: 'settings_row' })` |
| 2.6 | `mobile/src/screens/SleeperConnectScreen.tsx` | The whole client change, detailed below. |

**2.6 broken out** (all line refs are current positions):

- **`:1`** — add `useEffect` to the React import; **`:4`** — add `useRoute` to the
  `@react-navigation/native` import; new import `import { track } from '../api/events';`
  and `import { ApiError } from '../api/client';`.
- **`:52`, after `capturedRef`** — four refs: `linkedRef` (bool, drives the abandon guard),
  `sawErrorRef` (bool), `attemptsRef` (number), `phaseRef` (`'browsing'`).
- **`:53`** — resolve `source`: read `useRoute().params?.source`, coerce to `'unknown'` when
  not in the four-value allowlist.
- **new, after `:53`** — the mount effect, mirroring `EspnConnectScreen.tsx:198-209`:
  `track('sleeper_connect_opened', { source }, 'SleeperConnect')`; cleanup fires
  `sleeper_connect_abandoned` with `{ phase: phaseRef.current, saw_error: sawErrorRef.current,
  attempts: attemptsRef.current }` **when `!linkedRef.current`**. Dependency array `[]`
  (mount-once; `source` is captured at mount and cannot change) with the lint suppression
  the repo already uses for this pattern.
- **`:65-66`** — after `capturedRef.current = true`: `attemptsRef.current += 1;`
  `phaseRef.current = 'linking';`.
- **`:78-79`** — after `isVerified` is computed: `linkedRef.current = true;`
  `phaseRef.current = 'done';` `track('sleeper_connect_captured', { verified: isVerified,
  saw_error: sawErrorRef.current, attempts: attemptsRef.current }, 'SleeperConnect')`.
  Placed before the `setVerification` block so a throw there cannot swallow the success
  signal.
- **`:96-97`** — first statements of the `catch (e)` (the block must take the error binding;
  it is currently a bare `catch {`): derive `reason`/`status` per §2.3(d), set
  `sawErrorRef.current = true;` `phaseRef.current = 'error';`, then
  `track('sleeper_connect_failed', { reason, status, attempt: attemptsRef.current },
  'SleeperConnect')` — **above** the existing `capturedRef.current = false` at `:100`.

**No render-tree change. No copy change. No new state. No behaviour change** — `track()` is
synchronous, returns `void`, and swallows every error by contract (`events.ts:186-215`).

### Commit 3 — docs (may ride with commit 2)

| # | File | Change |
|---|---|---|
| 3.1 | `docs/integrations/sleeper.md:408` | Replace the illegal dotted `sleeper_connect.abandoned` with the shipped snake_case names and link the addendum. The dotted string would be silently dropped if copied into `track()`. |
| 3.2 | `docs/cross-client-invariants.md:268` §"Client analytics event contract" | Add a "Platform connect flows" bullet naming all four `sleeper_connect_*` (and, since they are also absent, the four `espn_connect_*`) to the "Allowed client event names" list, with the addendum link. Note explicitly that `web/js/events.js` and `extension/background.js` fire **none** of them, so the omission reads as deliberate. |
| 3.3 | `living-memory/DECISIONS.md` | New entry (next free ID; `D-011` per root `CLAUDE.md`, **re-check at build time** — P0-7 also claims `D-011`). Records: (i) no `sleeper_connect_otp_step`, and why an unverifiable detector is worse than no event; (ii) `captured` = link success, not token arrival; (iii) all four INTENT. |
| 3.4 | `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | On ship, per root `CLAUDE.md` §Session memory. TEST_LEDGER carries the sim-gate tier **and** §7.2's row-landed evidence. |

---

## 4. Surface changes

Enumerated against the four bright lines in root `CLAUDE.md`.

**Analytics events: YES — this is the item.** Complete enumeration, no other name is added:

*Client-fired (4) — `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`:*

1. `sleeper_connect_opened` — props `{source}`
2. `sleeper_connect_failed` — props `{reason, status, attempt}`
3. `sleeper_connect_captured` — props `{verified, saw_error, attempts}`
4. `sleeper_connect_abandoned` — props `{phase, saw_error, attempts}`

*Server-fired: **none**.* `SERVER_FIRED_EVENTS` is not edited. Every signal here is
client-side by nature — the server cannot see a login that never happened
(`docs/integrations/sleeper.md:400-409` states exactly this).

*Metric-set membership:* `NON_INTENT_EVENTS` — **no addition** (all four INTENT, §2.2).
`WAT_LIVE`/`WAT_DARK`, `FUNNEL_STAGES`, `FEATURE_VERTICALS`, `FUNNEL_CRITICAL` — **no edit**;
no connect-flow stage exists in any of them and this item does not create one.

**API routes: NO.** Nothing added, renamed, removed, or contract-changed.
`POST /api/events` accepts the four names purely by registry membership; its request and
response shapes are untouched. `POST /api/sleeper/link` is **read only** — its error enum is
consumed as the `reason` vocabulary and not modified.

**Schema: NO.** `user_events` already stores every one of these. No migration, no column, no
index.

**Feature flags: NO.** No flag added. Emission rides the existing
`analytics.client_events` (client, `events.ts:52`) + `analytics.ingest` (server) pair, both
currently `true` in `config/features.json`. **No new flag is warranted** — root `CLAUDE.md`
says a flag is for user-visible behaviour, and there is none here; the two existing analytics
gates are already the kill switch.

**Env vars / `model_config`: NO. UI: NO** (unless Checkpoint C is taken, which adds
`testID`s only — no rendered change).

---

## 5. Maestro delta

**Grep result, stated first:** `grep -rn "sleeperconnect\|SleeperConnect\|sleeper-connect"
mobile/.maestro/` returns **zero hits**. **No existing flow asserts this surface**, so there
is no flow to update as part of the fix. (The twin *does* have one —
`mobile/.maestro/flows/espn-connect-capture.yaml`, 94 lines.) The only related hits are
`capture/matches@espn.yaml:118,154` asserting the *Send in Sleeper* button label, which this
item does not touch.

**Mandatory delta: WAIVED, with reasoning** (root `CLAUDE.md` §Conventions permits a written
waiver; this is the same waiver P0-7 §7 takes for the same class of change).

This change is **not user-visible**: no rendered element, copy, layout, colour, timing, or
navigation behaviour changes. Every insertion is a `track()` call (fire-and-forget, `void`,
swallows all errors — `events.ts:186-215`), a ref mutation, or a route param. Maestro asserts
on rendered UI and has no visibility into the analytics queue or a `POST /api/events` batch —
a flow here would assert the *absence* of a regression, which the existing suite already
does. Verification moves to the backend and a simulator observation (§7).

Two conditions keep the waiver honest:

1. The existing smoke suite must pass **unchanged**. Any diff to a flow invalidates the
   waiver.
2. `mobile/scripts/testid-lint.sh` is unaffected — **no `testID` is added or renamed** under
   the waiver.

**Sim-gate tier: 2** (`docs/runbook.md:97` — *"Mobile logic touched, no UI change → feature's
flow + affected smoke subset + `screen-freshness.sh`; re-capture only what it flags"*;
expected: nothing). Affected subset: the settings/verification and trades-deck flows that
cross `SettingsScreen`, `SendInSleeperButton`, and the `RootNav` root. Log in
`TEST_LEDGER.md`; write `qa/sim-runs/last-sim-run.json`.

### Optional flow — recommended, and the only automated exercise of the abandon path

See **Checkpoint C**. A `mobile/.maestro/flows/sleeper-connect-capture.yaml` mirroring
`espn-connect-capture.yaml` (sign in → Settings → "Verify account" → assert the connect
screen mounts → back out → assert Settings restored) would drive `opened` and the
`phase: 'browsing'` abandon leg end-to-end. It also closes half of audit finding **A-31**
(Settings has no flow at all).

**`testID`s it would require** — the screen currently has exactly one, `sleeperconnect.done`
(`SleeperConnectScreen.tsx:157`), which **no flow references**:

| testID | Where | Note |
|---|---|---|
| `sleeper-connect.banner` | `SleeperConnectScreen.tsx:109` (banner `View`) | consent copy asserted by id — Maestro text selectors are full-match regexes, per the ESPN flow's own header note |
| `sleeper-connect.webview` | `:138` (`WebView`) | mirrors `espn-connect.webview` |
| `sleeper-connect.back-btn` | `RootNav.tsx:702-711` — requires adding `headerBackVisible: false` + a `HeaderBack` `headerLeft`, exactly as `EspnConnect` does at `:730-743` (the #151 iOS-26 pattern) | **This is the one real cost** — it changes the modal's header chrome, which pushes the change class to sim-gate **tier 1**. |
| `settings.verify-account-row` | `SettingsScreen.tsx:1259` | entry point for the flow |

Naming follows the twin's `<screen>-connect.<part>` convention. The existing
`sleeperconnect.done` is inconsistent with it and has zero flow references, so it can be
renamed to `sleeper-connect.done` in the same commit at zero risk — or left alone.
All IDs are static string literals, so `testid-lint.sh`'s grep-based check passes with no
`testid-lint-allow.txt` entry.

---

## 6. Docs impact table

One row per `docs/CLAUDE.md` trigger. Every row is answered.

| Doc (trigger) | Updated? | Section / reason n/a |
|---|---|---|
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` — **the load-bearing row** | **YES (mandatory)** | New "Addendum 2026-08-11 — Sleeper Connect" after the ESPN addendum (`:146-156`). `analytics_taxonomy.py:9-10` and `cross-client-invariants.md:268` both state the addendum is a **precondition** of registration, not a follow-up. |
| `docs/cross-client-invariants.md` (shared enum strings across clients) | **YES** | §"Client analytics event contract" (`:268`) — add the four names to "Allowed client event names" + addendum link; note web/extension fire none. |
| `docs/integrations/sleeper.md` (external-API reference) | **YES** | `:408` — correct the illegal dotted `sleeper_connect.abandoned` and mark the funnel gap closed. |
| `living-memory/DECISIONS.md` (non-obvious choice) | **YES** | Three decisions: no OTP-step event; `captured` = link success; all four INTENT. ID re-checked at build (P0-7 also claims `D-011`). |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **YES, on ship** | Root `CLAUDE.md` §Session memory. TEST_LEDGER carries tier + §7.2 evidence. |
| `docs/api-reference.md` (route added/renamed/removed/contract-changed) | **n/a** | No route touched. `POST /api/events` accepts new names by registry membership alone — shape unchanged. `POST /api/sleeper/link` is read-only reference for the `reason` enum. |
| `docs/data-dictionary.md` (table/column in `database.py`) | **n/a** | No schema change. Verified precedent: **no** client event name appears in this file — neither `espn_connect_*` nor `draft_room_*`. Client events are documented via the taxonomy + tracking-plan addendum; the file's `event_type` rule applies to **server-fired** types, and this item adds none. |
| `living-memory/LLD.md` (schema/route/invariant *conventions*) | **n/a** | No convention shifts. "Register before wiring" is P0-7's existing convention, obeyed here, not invented here. |
| `docs/architecture.md` (module wiring / data flow) | **n/a** | No new module or path. `track()` → existing queue → existing `POST /api/events`. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No architectural shift. |
| `docs/glossary.md` (new domain term) | **n/a** | No new domain term. "connect", "capture", "verified session" are all in use. |
| `docs/config-reference.md` (env var / flag / `model_config`) | **n/a** | None added. |
| `docs/adr/` (non-obvious architectural choice) | **n/a** | Instrumentation inside an existing pipeline; `DECISIONS.md` is the right weight. D-021 already covers the connect-capture architecture. |
| `docs/runbook.md` (operational issue) | **n/a** unless §7.2 surprises | Conditional. |
| `docs/design/` (any UI change) | **n/a** as planned | Becomes **YES** only if Checkpoint C's `HeaderBack` is added — and even then it reuses the `EspnConnect` header pattern verbatim, adding no new visual token. |
| `docs/templates/feature-scope.md` (copy, don't edit) | **YES** | Copied and filled: [`scope-p1-10.md`](scope-p1-10.md). |
| `living-memory/GOTCHAS.md` · `MISTAKES.md` · `OPEN_QUESTIONS.md` | **Conditional** | Only if §7 surprises. G-017 (paired analytics gates fail silently) already covers the known trap. |

---

## 7. Test plan

The wall is default-deny and silent — a 200 response proves **nothing**. Every check below
verifies at the destination.

### 7.1 Backend — allowlist acceptance (the actual failure mode)

Precedent: `backend/tests/test_events_api.py:335` `test_new_observability_events_accepted`
and `:366` `test_guide_events_accepted`. Add `test_sleeper_connect_events_accepted` in the
same shape, in **commit 1**:

```
POST /api/events with one envelope per new event, each carrying its FULL prop set:
  assert body["accepted"] == 4 and body["dropped"] == 0
  _assert_invariant(body, 4)
  assert set(by_type) == {"sleeper_connect_opened", "sleeper_connect_failed",
                          "sleeper_connect_captured", "sleeper_connect_abandoned"}
  assert json.loads(by_type["sleeper_connect_failed"]["props"])["reason"] == "token_user_mismatch"
  assert json.loads(by_type["sleeper_connect_abandoned"]["props"])["phase"] == "linking"
  assert json.loads(by_type["sleeper_connect_captured"]["props"])["verified"] is False
```

`dropped == 0` **and** the exact `set(by_type)` are the two assertions a silent default-deny
allowlist can fail — `accepted == 4` alone passes even when all four are dropped, because
dropped events are *counted as accepted* (`analytics_ingest.py:379-383`).

**Negative control** (mirrors `:246` `test_unknown_type_dropped`): post a deliberately
misspelled `sleeper_connect_captured` → **`sleeper_connect_capturd`** and assert it is
counted-and-dropped. This proves the guard is still armed rather than that the test is
tautological.

**Prop-stripping control**, pinning §2.3(f): post `sleeper_connect_opened` with a bogus
`platform` prop; assert the event lands and the prop is **gone**. This is the regression test
for the NULL-`platform` incident's root cause and for the decision that no connect event
carries a platform prop of either meaning.

**Import-time invariants are self-enforcing and loud.** A missing `CLIENT_EVENT_PROPS` row
raises `ValueError` at import (`analytics_taxonomy.py:327-332`) and a namespace collision
raises in `_assert_namespaces_disjoint` (`:298-322`) — either one makes **the entire test
suite fail to import**. That is the intended failure mode: it cannot ship half-registered.

### 7.2 End-to-end — prove a row at the destination (G-017's rule, verbatim)

Simulator against a dev backend with both `analytics.client_events` and `analytics.ingest`
on. Drive all four legs:

| Leg | How to produce it | Expected rows |
|---|---|---|
| `opened` + `abandoned{phase:'browsing', attempts:0}` | Settings → Verify account → dismiss without logging in | 1 + 1 |
| `opened` + `failed{reason:'token_user_mismatch'}` + `abandoned{phase:'error', saw_error:true, attempts:1}` | Log in on the WebView as a **different** Sleeper account than the session, then dismiss | 1 + 1 + 1 |
| `opened` + `captured{verified:true, attempts:1}` | Log in as the session's own Sleeper account | 1 + 1 |
| `source` coverage | Repeat once from each of the four entry points | 4 distinct `source` values |

Then:

1. Wait ≥10 s (`FLUSH_INTERVAL_MS`, `events.ts:58`) or background the app to force a flush.
2. Query the destination — **the row is the proof, not the 200**:
   `SELECT event_type, COUNT(*), platform FROM user_events
    WHERE event_type LIKE 'sleeper_connect_%' GROUP BY 1,3;`
3. **Assert `platform` is `'ios'`, not NULL** — the direct regression check for the incident
   in §2.3(f).
4. Check `GET /api/analytics/health` for `dropped_unknown_type` / `dropped_unknown_prop`
   staying **flat** across the session. A non-zero bump is the silent-drop signature and is
   the only way to see one.
5. Assert the partition holds: for each `session_id`, `captured + abandoned == opened` and
   never both terminals in one mount. This is the automated proof of §2.3(a)/(b).

Note the `token_rejected` and `timeout` legs are not reachable on the simulator without
forging a JWT or stalling the backend; they share one code path with `token_user_mismatch`
and are covered by the §7.1 unit assertion on `reason`.

### 7.3 Mobile static checks

`cd mobile && npx tsc --noEmit`. The route-param union (change 2.1) makes any mistyped
`source` at the four call sites a **compile error**, which is exactly the enforcement wanted
— the taxonomy cannot see a bad prop *value*, only a bad prop *key*.

`mobile/scripts/testid-lint.sh` — expected clean (no `testID` change under the waiver).

### 7.4 Post-ship read

Within 7 days of first real traffic, confirm on the analytics dashboard: (a) `opened` rows
exist with a `source` distribution across all four entry points; (b) `captured / opened` is a
plausible connect success rate; (c) the `reason` histogram is dominated by
`token_user_mismatch` if the screen's error copy is describing the real failure. **A flat
zero on any of the four is the silent-drop signature** — re-run §7.2 step 4 before assuming
users simply are not connecting.

---

## 8. Risks and cross-item collisions

### 8.1 Cross-item collisions — for the orchestrator

| File | This item needs | Also claimed by | Resolution |
|---|---|---|---|
| **`backend/analytics_taxonomy.py`** | 4 names in `ALLOWED_CLIENT_EVENTS` (`:98`), 4 rows in `CLIENT_EVENT_PROPS` (`:254`) | **P1-5** (invite promotion — the audit itself calls the invite page *"unmeasured"*, so it will register invite events) · **P0-7** (already merged before P1 starts: 8 client names + 1 server name) | **Coordinate with P1-5: land ONE shared "P1 taxonomy registration" commit containing both items' names, before either item's client wiring.** Two competing single-item registration commits in the same two frozensets conflict textually on adjacent lines and, worse, invite a merge that keeps one name set and silently drops the other — producing exactly the counted-and-dropped-behind-200 failure this plan exists to prevent. If they must ship separately, **P1-10's registration goes first** (it is Effort S and fully specced) and P1-5 rebases. Either way, neither item's client commit merges before its own name is on `main`. |
| **`backend/analytics_queries.py`** | **no edit** (all four INTENT) | **P1-5** may need a `NON_INTENT_EVENTS` addition if any invite event is impression-class (e.g. an invite-banner *shown* event) | No textual conflict — this item does not touch the file. Flagged so the shared-commit owner does not assume "no analytics_queries edit" applies to both items. |
| **`docs/business/analytics/2026-07-17-tracking-plan-v2.md`** | new addendum section after `:156` | **P1-5** (its own addendum) | Both append. Sequence them; trivial rebase. |
| **`mobile/src/screens/SettingsScreen.tsx`** `:488`, `:1261` | one line each | none found in the P1 set | Clean. Verify at build. |
| **`mobile/src/components/SendInSleeperButton.tsx`** `:114` | one line | **P0-6** rewrites this component's render path (ESPN fallback) and **P0-7** inserts `track()` into `onPress`/`catch` — **both merge before P1 starts** | Rebase onto post-P0 `main` and re-locate `goConnect` before editing. The audit's own P0-7 plan (§10.1) hands this file to P0-6, so its line numbers **will** have moved. |
| **`mobile/src/navigation/RootNav.tsx`** `:58`, `:437` | param type + one arg | **P0-5** edits `:398` (`account_only` routing) — merges before P1 | Different regions; trivial. |
| `mobile/src/screens/SleeperConnectScreen.tsx` | the whole client change | none found | **Clean — sole owner.** |

### 8.2 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Client wired before the taxonomy commit is on `main`** → all four events counted-and-dropped behind 200s, a dashboard that renders empty, and no error anywhere. Prior art in this repo. | **High** | §3's two-commit split with commit 1 merging first. §7.1's `dropped == 0` + exact-set assertions are the automated guard; §7.2 step 4's health counters are the manual one. |
| **P1-5 and P1-10 race on the same two frozensets** and a merge keeps one name set — same silent-drop outcome, arrived at by a different route. | **High** | The shared registration commit in §8.1. If separate, §7.1's *exact-set* assertion in each item's test fails loudly on a bad merge. |
| **A DOM-sniffing `otp_step` against an unverified Sleeper selector** would ship a permanently-zero event indistinguishable from a real zero. | **High if built** | Not built. §1.3 + Checkpoint A; the decision is recorded in `DECISIONS.md` so it is not "fixed" later by someone reading the ESPN twin. |
| **Missing `CLIENT_EVENT_PROPS` row** → `ValueError` at import → the app does not boot. | High but loud | Fails instantly in CI. A "don't ship half of commit 1" risk, not a production risk. |
| **Cleanup reads `phase` state instead of `phaseRef`** → every `abandoned` reports `phase: 'browsing'`, and the metric looks plausible while being wrong. | **Medium — the subtlest bug here** | §2.3(c) specifies refs. §7.2's second leg asserts `phase: 'error'` explicitly, which is the only check that catches it. |
| **`linkedRef` vs `capturedRef` confusion** → guarding the abandon on `capturedRef` (the literal ESPN mirror) silently loses every in-flight-dismissal session. | Medium | §2.3(b); §7.2 step 5's `captured + abandoned == opened` partition assertion. |
| Retry loop double-counts. A user retrying 3× fires 3 `failed` and 1 terminal. | Low — intended | `attempt` / `attempts` disambiguate. Analysts count sessions via `session_id`, not raw rows; documented in the addendum. |
| `abandoned` fires on an OS-initiated unmount (memory pressure, backgrounding that tears the modal down) and reads as a user decision. | Low | Same exposure the ESPN twin already carries; `screen_left`'s `reason: 'background'` (`RootNav.tsx:182-193`) is available to cross-check. Recorded, not engineered around. |
| The stray `setTimeout(goBack, 1200)` at `:95` is never cleared on unmount — a pre-existing latent warning that the new cleanup sits next to. | Low | **Deliberately not fixed** (surgical-change rule). Named here so a reader sees it was considered. Candidate for its own ticket. |
| Volume: 4 events × a rare flow. | Negligible | Far inside the 500-item queue cap; none is `FUNNEL_CRITICAL`, so `trimQueue` degrades gracefully. |

### 8.3 Deliberately NOT instrumented

Named so a future session sees these were considered, not overlooked: the confirm/cancel
beats around `goConnect`; the Keychain silent-replay path (`sendInSleeper.ts:160-190` — a
background re-verification with no screen, and a separate funnel); `persistSleeperToken`'s
outcome (`:76`, already swallowed); the WebView's own load/redirect events; the JWT's
`valid_2fa` claim (server-side, and a property of the *account*, not of *this capture*);
and `POST /api/sleeper/link`'s `DELETE` (disconnect) leg.

---

## 9. Operator checkpoints

**A. The fourth event: `sleeper_connect_failed` (recommended) or `sleeper_connect_otp_step`
(the literal wording of `06-resolutions.md:104`)?**
This is the one decision that changes what the work measures.
*Option 1 — `sleeper_connect_failed`* (**recommended**): mirrors the ESPN *pattern* — four
events, one hard-step marker echoed as a boolean on both terminals — while measuring
Sleeper's actual hard step, the link rejection. Fully observable today, bounded 11-value
enum, and it names the exact failure the screen's own error copy describes.
*Option 2 — `sleeper_connect_otp_step`*: mirrors the literal string, requires a new injected
MutationObserver against an **unverified** Sleeper DOM (§1.3), and most likely ships a
permanently-zero event that no one can distinguish from a real zero without a live
OTP-gated TestFlight session.
*Option 3 — both (5 events):* possible, and the honest way to do Option 2 — but it exceeds
"Effort S" and still carries the silent-zero risk.
**Recommendation: Option 1.** It deviates from the resolutions doc's wording, and it
deviates *toward* a verified signal, not away from one.

**B. `captured` fires on link success (recommended) or on token arrival (the literal ESPN
mirror)?** §2.3(a). Success makes `captured / opened` a clean connect-success rate and gives
a mutually-exclusive partition; token arrival is the more literal mirror but double-counts on
retry and makes the curve mean "logged in", not "connected". Either way `attempts` preserves
the other measurement. **Recommendation: link success**, with the deviation stated in the
addendum so the two platforms' `captured` curves are never naively compared.

**C. Ship the optional Maestro flow?** §5.
*In:* the abandon path gets automated coverage, and half of audit **A-31** (Settings has no
flow) closes. Cost: 4 `testID`s **and** a custom `headerLeft`/`HeaderBack` on the
`SleeperConnect` route — a header-chrome change that moves the sim gate from **tier 2 to
tier 1** (full smoke suite + screen captures).
*Out:* stays a clean tier-2 analytics-only change with a defensible waiver.
**Recommendation: out for this item; spin the flow off as its own ticket under A-31.**
Bundling a header change into an instrumentation fix is exactly the drive-by the coding
guidelines forbid, and it triples the ship cost of an Effort-S item.

**D. Coordinate the taxonomy registration with P1-5 into one commit?** §8.1.
**Recommendation: yes.** Two competing edits to the same two frozensets is the single highest
-probability way to reproduce the silent-drop failure this item exists to prevent. If the
orchestrator prefers separate commits, P1-10's goes first (fully specced, Effort S) and
P1-5 rebases.

**E. Also rename `sleeperconnect.done` → `sleeper-connect.done`?** It is the screen's only
`testID` (`:157`), inconsistent with the twin's convention, and **referenced by zero flows**
(verified) — so the rename is free. Out of scope as written.
**Recommendation: only if Checkpoint C is taken**, so all the screen's IDs land in one
convention at once.
