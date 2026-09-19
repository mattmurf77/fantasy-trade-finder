# LLD — P1-10 · Sleeper Connect in-flow analytics (audit A-19)

> **Status:** design only. **No source file is edited by this document.**
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at authoring time).
> **Every `file:line` below is verified at `ab9368f` and WILL MOVE after the P0 merge.**
> Re-locate by content, never by line — see [§H](#h-re-verify-after-p0-merge).
>
> **Binding inputs, in precedence order:** `DECISIONS-p1.md` → `HLD-p1.md` (merge order,
> wave/file ownership, commit T1) → `plan-p1-10.md` + `scope-p1-10.md`. Where this LLD
> departs from `plan-p1-10.md` it is because the plan is wrong against the code or because
> the HLD superseded it; every such departure is listed in
> [§I Corrections to the plan](#i-corrections-to-the-plan).
>
> **Wave:** A, agent **A2** (`HLD-p1.md` §B). **Merge position:** step 2, after **T1**
> (`HLD-p1.md` §C). **Gate posture:** full gates — analytics events are a bright line.

## Contents

- [A. What ships, in one paragraph](#a-what-ships-in-one-paragraph)
- [B. The event set — finalised, with the OTP non-mapping](#b-the-event-set--finalised-with-the-otp-non-mapping)
- [C. Property shapes — types, value domains, derivation](#c-property-shapes--types-value-domains-derivation)
- [D. This item's exact contribution to commit T1](#d-this-items-exact-contribution-to-commit-t1)
- [E. Client diff sites — current → intended](#e-client-diff-sites--current--intended)
- [F. Trigger moments — code location and condition, per event](#f-trigger-moments--code-location-and-condition-per-event)
- [G. Proof of landing — the probe procedure](#g-proof-of-landing--the-probe-procedure)
- [H. Re-verify after P0 merge](#h-re-verify-after-p0-merge)
- [I. Corrections to the plan](#i-corrections-to-the-plan)
- [J. Deliberately not instrumented](#j-deliberately-not-instrumented)
- [K. Operator gates — unresolved](#k-operator-gates--unresolved)

---

## A. What ships, in one paragraph

Four client-fired analytics events on `SleeperConnectScreen`, registered server-side in the
shared **T1** commit and wired in the client only after T1 is deployed and probed. Four
navigation call sites gain a `source` param; one route-param type widens. **No rendered
element, copy string, layout, colour, timing, navigation behaviour, route, schema, feature
flag, env var, or API contract changes.** Total client surface: one `useEffect`, four
`useRef`s, one `useRoute()` read, four `track()` calls, one `catch {` → `catch (e)`, and
four one-argument navigate edits.

---

## B. The event set — finalised, with the OTP non-mapping

### B.1 The four events

| # | Event | Props | Terminal? | Intent class |
|---|---|---|---|---|
| 1 | `sleeper_connect_opened` | `source` | no (exactly 1 per mount) | **INTENT** |
| 2 | `sleeper_connect_failed` | `reason`, `status`, `attempt` | no (0..n per mount) | **INTENT** |
| 3 | `sleeper_connect_captured` | `verified`, `saw_error`, `attempts` | **yes** (success) | **INTENT** |
| 4 | `sleeper_connect_abandoned` | `phase`, `saw_error`, `attempts` | **yes** (non-success) | **INTENT** |

`screen` (envelope field, not a prop) is the literal `'SleeperConnect'` on all four calls —
the third positional argument of `track()` (`mobile/src/api/events.ts:188-191`).

### B.2 The OTP step does not map, and must not be made to map

**Restated compactly so no implementer "improves" it back into a detector.**

ESPN's `espn_connect_otp_step` is fired by an injected `MutationObserver`
(`mobile/src/screens/EspnConnectScreen.tsx:87-111`) matching three **Disney-SSO-specific**
selectors — `input[autocomplete="one-time-code"]`, `input[name="otp"]`,
`input[data-testid="OneTimePasscode"]` (`:95-97`) — and posts a bare presence signal handled
at `:240-246`.

Sleeper has an OTP/2FA leg, but it is **inside Sleeper's own page**:

1. `docs/plans/sleeper-write-capture-runbook.md:128` — the app "lets Sleeper handle password
   / OTP / passkey / 2FA" and then reads `localStorage['token']`; `:129`, `:134` — 2FA is
   *fully resolved on Sleeper's side* and survives only as a `valid_2fa` JWT claim.
2. `SleeperConnectScreen.tsx:27-46` (`INJECTED_POLLER`) performs **no DOM observation at
   all** — it polls one `localStorage` key every 800 ms and posts once. There is no observer
   to extend.
3. **This repo holds no verified selector** for `sleeper.com/login`'s OTP input. The ESPN
   selectors were derived from Disney's DOM; nothing equivalent exists in
   `docs/references/`, `docs/integrations/sleeper.md`, or the capture runbook.

Therefore a `sleeper_connect_otp_step` built today would be a **permanently-zero event that
is indistinguishable from a real zero** — nobody could tell "no user hit OTP" from "the
selector never matched" without a live TestFlight session on an OTP-gated Sleeper account.
That is the **A-33 failure class** (`HLD-p1.md` §F **R-5**): an artifact asserting something
the runtime does not do. **Do not build it. Do not add it later "for symmetry with ESPN."**

**Sleeper's actual hard step is the server-side link rejection.** ESPN's screen hands cookies
to a sheet with no server round-trip; Sleeper's screen POSTs the JWT to
`POST /api/sleeper/link` (`backend/server.py:12163`), which can reject it — and the screen's
own error copy names the dominant case: *"make sure you log in to the same Sleeper account
you use here"* (`SleeperConnectScreen.tsx:130-135`), i.e. `token_user_mismatch`. That
rejection is fully observable client-side today, with a closed enum. It occupies slot 4.

**`saw_error` occupies `saw_otp`'s structural slot** — the same boolean-marker role, echoed
on both terminals so either terminal can be split by "did the hard step gate this?".

### B.3 Intent classification — a decision, not an omission

`backend/analytics_queries.py:65`:
`INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`.
INTENT is a **deny-list**; a new name is intent by default and only an explicit
`NON_INTENT_EVENTS` addition removes it from DAU/WAU/MAU/churn/retention.

`NON_INTENT_EVENTS` at `ab9368f` (`analytics_queries.py:60-63`) is exactly
`{app_opened, app_backgrounded, app_open, screen_viewed, push_sent, client_error, api_call,
api_request}`. **None of the four `espn_connect_*` names is in it** — the twin ships all four
as INTENT.

**Decision: all four `sleeper_connect_*` events are INTENT. `backend/analytics_queries.py`
receives NO edit from this item.** This is a positive decision, recorded here, in the T1
addendum, and in `living-memory/DECISIONS.md` — not an oversight to be "fixed" later.

Justification:
- None is impression-class. Every one is downstream of a deliberate tap at one of the four
  entry points in [§E.2](#e2-the-four-navigation-call-sites); there is no passive path onto
  this modal (no deep link, no auto-navigate — `mobile/src/state/useSession.ts` only sets
  banner state).
- `screen_viewed` for this route already fires and is already NON_INTENT
  (`analytics_queries.py:61`), so mount volume is not what these events add.
- Splitting intent classification from the ESPN twin would make the two platforms' connect
  funnels un-diffable — the one comparison this data exists to support.

> **T1 boundary note.** `analytics_queries.py` **is** edited in T1 — by P1-5, adding
> `invite_cta_shown` to `NON_INTENT_EVENTS` (`HLD-p1.md` T1.3). "P1-10 adds nothing there" is
> a statement about this item's rows only, and must not be read as "T1 does not touch the
> file."

---

## C. Property shapes — types, value domains, derivation

`source` — **string, closed 5-value domain.**

| Value | Emitted from |
|---|---|
| `send_button` | `SendInSleeperButton.tsx` `goConnect` |
| `verify_banner` | `RootNav.tsx` `VerifyAccountBanner onVerify` |
| `settings_row` | `SettingsScreen.tsx` "Verify account" row |
| `settings_stepup` | `SettingsScreen.tsx` `promptVerifyStepUp` alert → "Verify now" |
| `unknown` | route param absent or outside the allowlist — **a real, expected value, not a bug marker** |

Validated **at read time in the screen**, not trusted from the caller:

```ts
const SOURCES = ['send_button', 'verify_banner', 'settings_row', 'settings_stepup'] as const;
const raw = (useRoute().params as any)?.source;
const source = SOURCES.includes(raw) ? raw : 'unknown';
```

This coercion is load-bearing, **not belt-and-braces** — see correction
[I-3](#i-corrections-to-the-plan): three of the four call sites are untyped, so the compiler
does not police the vocabulary.

`reason` — **string, closed 11-value domain.** Eight are the complete server enum of
`POST /api/sleeper/link`, each verified at its `return`:

| `reason` | HTTP | `backend/server.py` |
|---|---|---|
| `feature_disabled` | 404 | `:12181` |
| `no_user` | 401 | `:12185` |
| `sleeper_unconfigured` | 503 | `:12213` **and** `:12254` (two paths, one code) |
| `invalid_token` | 400 | `:12217` |
| `token_expired` | 400 | `:12219` |
| `token_user_mismatch` | 403 | `:12228` |
| `token_rejected` | **403** | `:12243` |
| `store_failed` | 500 | `:12257` |

Plus three client-synthetic values: `timeout`, `network`, `unknown`. **Bounded at 11
forever** — the client never invents a value; anything unrecognised collapses to `unknown`.

`status` — **integer or null.**
- Server rejection → the HTTP status from `ApiError.status` (`mobile/src/api/client.ts:162`,
  thrown at `:553` with `status`, parsed `body`, message).
- **Timeout → `0`, not null.** The timeout `ApiError` is constructed
  `new ApiError(0, null, TIMEOUT_MESSAGE, true)` (`client.ts:484`, `:604`). Document `0` as a
  legal value; an analyst filtering `status > 0` would silently drop timeouts.
- Non-`ApiError` throw (network `TypeError`, caller abort) → `null`.

Derivation, verbatim (mirrors P0-7's `error_code` shape):

```ts
const reason = e instanceof ApiError
  ? (e.isTimeout ? 'timeout' : ((e.body as any)?.error ?? 'unknown'))
  : 'network';
const status = e instanceof ApiError ? e.status : null;
```

> **`e.body` may be a bare string.** `client.ts:518-524` sets `parsed = text` when the body is
> not JSON, so `(e.body as any)?.error` is `undefined` on an HTML error page →
> `reason: 'unknown'`. That is the correct outcome; it is stated so nobody "fixes" the
> optional chain into a crash.

`attempt` / `attempts` — **integer ≥ 0.** `attemptsRef` counts **token-capture attempts this
mount** (increments once per accepted `{type:'token'}` message, i.e. per link POST).
`attempt` on `_failed` is the 1-based index of the attempt that failed (`attemptsRef.current`
at the moment of the catch — already incremented). `attempts` on the terminals is the total
for the mount. `attempts: 0` on `_abandoned` means **the user never logged in to Sleeper**.

`verified` — **boolean.** Exactly `res?.verified === true` (`SleeperConnectScreen.tsx:78`).
`false` covers the "inconclusive oracle" branch (link stored, verification not proven —
`server.py:12245-12248`). It is a real, common value, not an error.

`saw_error` — **boolean.** True iff at least one `sleeper_connect_failed` fired earlier in
this mount. Read from `sawErrorRef`, never from state.

`phase` — **string, closed 3-value domain** on `_abandoned` only:

| Value | Meaning |
|---|---|
| `browsing` | never got a token — abandoned inside Sleeper's login |
| `linking` | token captured, link POST still in flight at unmount |
| `error` | at least one rejection, then gave up |

`'done'` is set on the success path but can never appear on `_abandoned` — the cleanup is
suppressed by `linkedRef` in exactly that case. It is written to `phaseRef` anyway so the ref
is always truthful.

### C.1 No `platform` prop, of either meaning — explicit

**None of the four events carries a `platform` prop.** Two distinct traps, both avoided:

1. **Device platform** is a **server-derived column**. `analytics_ingest.py:363-366` computes
   `platform` from `g.device_info["device_type"]`, which comes from the `X-Device*` headers
   that `events.ts:280-286` spreads into every `POST /api/events` — the fix for the
   pre-2026-08-05 NULL-`platform` incident that `analytics_taxonomy.py:256-260` cites as the
   reason prop specs exist at all. The mobile request body is `{events: batch}` only
   (`events.ts:299`), so nothing client-side sets the column.
2. **League platform** — where a `platform` prop is legitimate it means
   Sleeper/ESPN/MFL/Fleaflicker (the `league_selected` precedent,
   `analytics_taxonomy.py:185`). On a `sleeper_connect_*` event that is a tautology: the
   event name already says Sleeper.

Adding either would be redundant at best and would re-create the exact ambiguity that caused
the incident at worst. [§G](#g-proof-of-landing--the-probe-procedure) pins both halves: a
bogus `platform` **prop** must be stripped, and the `platform` **column** must read `'ios'`.

### C.2 No credential is ever a property

No JWT, no fragment, no length, no `sleeper_user_id`, no `valid_2fa` claim, no
`transaction_id`. The token goes to `POST /api/sleeper/link` and nowhere else — the same
invariant the ESPN registry comment states for its cookies
(`analytics_taxonomy.py:247-250`). `_scrub_pii` runs server-side on client props regardless,
but this is a **design rule**, not a reliance on the scrubber.

---

## D. This item's exact contribution to commit T1

**P1-10 does not propose a registration commit.** `HLD-p1.md` §A.2 adopted P1-10's
shared-commit recommendation and **widened it to three items** (P1-10, P1-5, P1-1/2). T1 has
**one owner, one commit**, is the **first P1 commit after the P0 merge**, and is **merged,
deployed and probed before any P1 client `track()` exists** (`HLD-p1.md` §C step 1).

**After T1 merges, `analytics_taxonomy.py` and `analytics_queries.py` are frozen for the rest
of the round** (`HLD-p1.md` §B). A2 must not touch either file.

Below is **P1-10's slice of T1** and nothing else. The T1 owner assembles it alongside P1-5's
and P1-1/2's slices.

### D.1 → T1.1 · `backend/analytics_taxonomy.py` · `ALLOWED_CLIENT_EVENTS`

Insert **after** the ESPN block (`:90-98`), **before** the closing `})` at `:99`:

```python
    # Sleeper Connect WebView capture (SleeperConnectScreen; audit A-19 /
    # P1-10). Mirrors the ESPN Connect FOUR-EVENT PATTERN, not its literal
    # strings.
    #   * There is deliberately NO `sleeper_connect_otp_step`. Sleeper resolves
    #     password/OTP/passkey/2FA inside its OWN page
    #     (docs/plans/sleeper-write-capture-runbook.md:128,134); the injected
    #     script only polls localStorage['token'] and observes no DOM. This repo
    #     holds no verified selector for Sleeper's OTP input, so a detector would
    #     ship a PERMANENTLY-ZERO event indistinguishable from a real zero. Do
    #     not add one.
    #   * Slot 4 is `sleeper_connect_failed` — the server-side link rejection,
    #     which is Sleeper's actual hard step (POST /api/sleeper/link, 8-value
    #     closed error enum). `saw_error` occupies `saw_otp`'s structural slot.
    #   * No JWT, token fragment, sleeper_user_id or valid_2fa claim exists or
    #     may be added as a property — the token goes to POST /api/sleeper/link
    #     and nowhere else.
    #   * All four are INTENT **by decision** (analytics_queries.py is
    #     deliberately not edited for them) — see DECISIONS.md and the tracking-
    #     plan addendum.
    "sleeper_connect_opened", "sleeper_connect_failed",
    "sleeper_connect_captured", "sleeper_connect_abandoned",
```

### D.2 → T1.2 · `backend/analytics_taxonomy.py` · `CLIENT_EVENT_PROPS`

Insert **after** the ESPN rows (`:251-254`), **before** the closing `}` at `:255`:

```python
    # Sleeper Connect (A-19 / P1-10) — `source` is the entry point (4 values +
    # 'unknown'); `reason` is the closed POST /api/sleeper/link error enum plus
    # timeout|network|unknown; `status` is the HTTP status (0 on a client
    # timeout, absent/None on a non-HTTP failure); `saw_error` records whether a
    # link rejection preceded the outcome; `attempts`/`attempt` count token
    # captures this mount; `phase` is where an abandon happened. NO `platform`
    # prop of EITHER meaning: device platform is a server-derived column
    # (X-Device* headers), league platform is tautological here. No
    # credential/JWT prop exists or may be added.
    "sleeper_connect_opened":    frozenset({"source"}),
    "sleeper_connect_failed":    frozenset({"reason", "status", "attempt"}),
    "sleeper_connect_captured":  frozenset({"verified", "saw_error", "attempts"}),
    "sleeper_connect_abandoned": frozenset({"phase", "saw_error", "attempts"}),
```

**D.1 and D.2 ship together or not at all.** A name in `ALLOWED_CLIENT_EVENTS` with no
`CLIENT_EVENT_PROPS` row raises `ValueError` at **import**
(`analytics_taxonomy.py:326-332`) — the app does not boot and the whole test suite fails to
import. That is the intended failure mode: it cannot ship half-registered.

### D.3 → T1.3 · `backend/analytics_queries.py`

**No P1-10 rows.** All four INTENT ([§B.3](#b3-intent-classification--a-decision-not-an-omission)).

### D.4 → T1.4 · `backend/tests/test_events_api.py`

New `test_sleeper_connect_events_accepted`, in the shape of
`test_new_observability_events_accepted` (`:335-352`) and `test_guide_events_accepted`
(`:366+`):

```
POST /api/events — one envelope per event, each with its FULL prop set:
  _assert_invariant(body, 4)
  assert body["accepted"] == 4 and body["dropped"] == 0
  assert set(by_type) == {"sleeper_connect_opened", "sleeper_connect_failed",
                          "sleeper_connect_captured", "sleeper_connect_abandoned"}
  assert json.loads(by_type["sleeper_connect_opened"]["props"])["source"] == "settings_row"
  assert json.loads(by_type["sleeper_connect_failed"]["props"])["reason"] == "token_user_mismatch"
  assert json.loads(by_type["sleeper_connect_failed"]["props"])["status"] == 403
  assert json.loads(by_type["sleeper_connect_captured"]["props"])["verified"] is False
  assert json.loads(by_type["sleeper_connect_abandoned"]["props"])["phase"] == "linking"
```

`dropped == 0` **and** the exact `set(by_type)` are the two assertions the silent wall can
fail. `accepted == 4` alone passes even when all four are dropped —
`analytics_ingest.py:379-384` increments **both** `accepted` and `dropped` and `continue`s.

Two controls, both required:

- **Negative control** (mirrors `test_unknown_type_dropped`, `:246`): post a misspelled
  `sleeper_connect_capturd`; assert it is counted-and-dropped. Proves the guard is armed
  rather than the test tautological.
- **Prop-stripping control** (pins [§C.1](#c1-no-platform-prop-of-either-meaning--explicit)):
  post `sleeper_connect_opened` with a bogus `platform` prop; assert the event lands and the
  prop is **absent** from the stored row (`analytics_ingest.py:385-390`).

### D.5 → T1.6 · `backend/tests/test_analytics_p0.py`

The four names are folded into **T1's single** extension of
`test_live_taxonomy_is_disjoint`'s membership assertion. **One edit covering all nine T1
names** — three separate edits to one assertion is a guaranteed conflict (`HLD-p1.md` T1.6).

### D.6 → T1.7 · tracking-plan addendum

P1-10's rows go into T1's **single** appended section — "Addendum 2026-08-11 — P1 round" —
placed after the ESPN addendum, which begins at
`docs/business/analytics/2026-07-17-tracking-plan-v2.md:145` and ends at `:156`. Required
P1-10 content, mirroring the ESPN addendum's shape (`:145-156`):

1. Four-row event table (event · fires · key props).
2. The no-credential-prop rule, stated as a rule.
3. **"What is deliberately NOT here"** — the OTP step and why (a permanently-zero event is
   worse than none), `valid_2fa`, the confirm/cancel beats around `goConnect`, the Keychain
   silent-replay path, the WebView's own load/redirect events, and the `DELETE` disconnect
   leg.
4. **The `captured` deviation, stated plainly:** `sleeper_connect_captured` fires on **link
   success**, `espn_connect_captured` fires on **credential arrival**. *The two platforms'
   `captured` curves must never be naively compared.*
5. All four are INTENT, by decision.
6. The DAU/WAU seam date (first emission), so a later analyst sees a discontinuity rather
   than discovering it in a chart (`HLD-p1.md` §F R-9).

### D.7 → T1 · `docs/cross-client-invariants.md`

The `:268` §"Client analytics event contract" bullet is **T1's edit, not A2's**
(`HLD-p1.md` §A.5 — three P1 items target `:268`, so they fold into one). P1-10's content
for the T1 owner: add the four `sleeper_connect_*` names to the "Allowed client event names"
list at `:285-292` and note that `web/js/events.js` and `extension/background.js` fire
**none** of them, so the omission reads as deliberate.

*Observed, out of scope:* that list is already stale — it is missing `espn_connect_*`,
`draft_room_*`, `guide_*`, `screen_left`, `api_request_failed`. Adding the four ESPN names
alongside is cheap; a full reconciliation is its own ticket.

### D.8 T1's gate — the precondition on every line in §E

`HLD-p1.md` §C step 1: T1 merges → **Render deploys** → a hand-rolled `POST /api/events`
carries one envelope per new name with its **full** prop set → **`dropped == 0` and every
prop echoed back**, or **no P1 client wave starts.** A2 writes no `track()` call before that
result is in hand. Procedure in [§G.1](#g1-t1-gate-probe-before-any-client-wiring).

---

## E. Client diff sites — current → intended

All line numbers are `ab9368f`. **A2 owns every file in this section exclusively for Wave A**
(`HLD-p1.md` §B): `SleeperConnectScreen.tsx`, `RootNav.tsx`, `SendInSleeperButton.tsx`,
`SettingsScreen.tsx`, `docs/integrations/sleeper.md`.

### E.1 `mobile/src/screens/SleeperConnectScreen.tsx` — the whole client change

Sole owner; P0 does not touch this file (`HLD-p1.md` §A.3). 195 lines, **zero `track()` calls
and no `track` import** today; **no `useEffect` anywhere in the file**.

| # | Line(s) | Current | Intended |
|---|---|---|---|
| E1.1 | `:1` | `import React, { useCallback, useRef, useState } from 'react';` | add `useEffect` |
| E1.2 | `:4` | `import { useNavigation } from '@react-navigation/native';` | add `useRoute` |
| E1.3 | after `:7` | *(no analytics import)* | `import { track } from '../api/events';` and `import { ApiError } from '../api/client';` |
| E1.4 | after `:52` (`const capturedRef = useRef(false);`) | one ref | **four new refs**, each with a one-line comment: `linkedRef` (bool — the abandon guard, set only on the success path), `sawErrorRef` (bool), `attemptsRef` (number, 0), `phaseRef` (`'browsing' \| 'linking' \| 'done' \| 'error'`, init `'browsing'`) |
| E1.5 | after E1.4 | — | `source` resolution per [§C](#c-property-shapes--types-value-domains-derivation) — `useRoute()` read + allowlist coercion |
| E1.6 | after E1.5, **before** `onMessage` at `:54` | *(no effect exists)* | the mount effect — `sleeper_connect_opened` in the body, `sleeper_connect_abandoned` in the cleanup. Full spec: [§F.4](#f4-sleeper_connect_abandoned--the-unmount-cleanup-guard) |
| E1.7 | `:65-66` | `capturedRef.current = true;` / `setPhase('linking');` | append `attemptsRef.current += 1;` and `phaseRef.current = 'linking';` |
| E1.8 | `:78-79` | `const isVerified = res?.verified === true;` / `setVerified(isVerified);` | insert immediately after `:78`: `linkedRef.current = true;`, `phaseRef.current = 'done';`, then the `sleeper_connect_captured` call — **before** the `if (isVerified)` block at `:80-91` |
| E1.9 | `:96` | `} catch {` | `} catch (e) {` — **the block must take the error binding**; it is bare today |
| E1.10 | `:96-99`, above `:100` | comment block, then `capturedRef.current = false;` at `:100` | insert the `reason`/`status` derivation, `sawErrorRef.current = true;`, `phaseRef.current = 'error';`, then the `sleeper_connect_failed` call — **all above `:100`**, so the retry reset cannot race the read |

**Not changed:** the render tree (`:107-168`), every copy string, `INJECTED_POLLER`
(`:27-46`), `SLEEPER_LOGIN_URL` (`:22`), the `phase`/`verified` `useState`s (`:50-51`), the
`onMessage` dependency array (`:104`), and the `sleeperconnect.done` testID (`:157`).

**No behaviour change.** `track()` is synchronous, returns `void`, and swallows every error
by contract (`events.ts:186-215`); it is a no-op when `analytics.client_events` is off
(`events.ts:52`, `:112-114`).

### E.2 The four navigation call sites

| # | File → line @ `ab9368f` | Current | Intended | Post-P0 re-location |
|---|---|---|---|---|
| E2.1 | `mobile/src/navigation/RootNav.tsx:58` | `SleeperConnect: undefined;` (in `type AuthStack`, declared `:50`, used by `createNativeStackNavigator<AuthStack>()` `:101` and `navigationRef` `:102`) | `SleeperConnect: { source?: 'send_button' \| 'verify_banner' \| 'settings_row' \| 'settings_stepup' } \| undefined;` + a short comment in the style of `EspnConnect`'s (`:59-65`) | re-grep `SleeperConnect:` inside `type AuthStack` |
| E2.2 | `mobile/src/navigation/RootNav.tsx:437` | `onVerify={() => navigation.navigate('SleeperConnect')}` | `…navigate('SleeperConnect', { source: 'verify_banner' })` | re-grep `VerifyAccountBanner` |
| E2.3 | `mobile/src/components/SendInSleeperButton.tsx:114` (inside `goConnect`, `:112-115`) | `navigation.navigate('SleeperConnect');` | `navigation.navigate('SleeperConnect', { source: 'send_button' });` | **will have moved** — P0-6 rewrites the gate and render tail, P0-7 inserts into `onPress`. **Re-grep `goConnect`** |
| E2.4 | `mobile/src/screens/SettingsScreen.tsx:488` (`promptVerifyStepUp` alert, "Verify now") | `onPress: () => navigateFromSettings('SleeperConnect'),` | `…('SleeperConnect', { source: 'settings_stepup' })` | **will have moved** — P0-5 extracted the inline Sleeper form into `LinkSleeperSheet`. Re-grep `navigateFromSettings('SleeperConnect')` |
| E2.5 | `mobile/src/screens/SettingsScreen.tsx:1261` ("Verify account" row, `Pressable` at `:1259`) | `onPress={() => navigateFromSettings('SleeperConnect')}` | `…('SleeperConnect', { source: 'settings_row' })` | as above |

`navigateFromSettings(route: string, params?: object)` (`SettingsScreen.tsx:220-227`)
**already accepts a params argument** and forwards it on both branches (`:222-223` v2,
`:225` legacy) — E2.4/E2.5 need no helper change.

**These four are the complete set.** A full `grep -rn "SleeperConnect" mobile/src` at
`ab9368f` returns only: the import and route registration (`RootNav.tsx:20`, `:701-712`), the
param-list entry (`:58`), the comment at `:435`, and these four navigate calls. There is no
deep-link route and no programmatic entry in `deepLinks.ts`.

### E.3 `docs/integrations/sleeper.md:408` — the doc bug, corrected

Current (`:405-409`, prose in the "Server CANNOT see" list):

> "Worth a client event (`sleeper_connect.abandoned` or similar) if funnel visibility into
> this step matters."

`sleeper_connect.abandoned` is **dotted**. Every registered name in
`analytics_taxonomy.py:38-99` is snake_case with no dots; the dotted form is not in
`ALLOWED_CLIENT_EVENTS` and would be **counted-and-dropped behind a 200**
(`analytics_ingest.py:379-384`) if a future builder copied it into `track()`.

**Intended:** replace the parenthetical with the four shipped snake_case names, mark the
funnel gap closed, and link the T1 addendum. This is the one doc file A2 owns
(`HLD-p1.md` §B, Wave A / A2).

### E.4 Files explicitly NOT touched by A2

`backend/analytics_taxonomy.py`, `backend/analytics_queries.py`,
`backend/tests/test_events_api.py`, `backend/tests/test_analytics_p0.py`,
`docs/business/analytics/2026-07-17-tracking-plan-v2.md`,
`docs/cross-client-invariants.md` — **all T1's**, and frozen after T1 merges.
`living-memory/DECISIONS.md` / `CHANGELOG.md` / `TEST_LEDGER.md` are written by A2 at ship
time with **IDs allocated at write time**, never the ID printed in the plan
(`HLD-p1.md` §A.6 — nine claimants on `D-011`).

---

## F. Trigger moments — code location and condition, per event

### F.1 `sleeper_connect_opened`

- **Location:** first statement of the new mount effect's body (E1.6), which sits between the
  `source` resolution and `onMessage` (`:54`).
- **Condition:** unconditional, once per mount. Dependency array `[]` — `source` is captured
  at mount and cannot change; add the repo's existing
  `// eslint-disable-next-line react-hooks/exhaustive-deps` (precedent:
  `LeaguePickerScreen.tsx:128`, `TiersScreen.tsx:499`).
- **Mirror:** `EspnConnectScreen.tsx:199`.
- **Call:** `track('sleeper_connect_opened', { source }, 'SleeperConnect')`.

### F.2 `sleeper_connect_failed`

- **Location:** first statements of the `catch` at `:96`, **above** `capturedRef.current =
  false` at `:100`.
- **Condition:** every throw out of the `try` at `:67`. Ordering is load-bearing twice over:
  the read of `attemptsRef` must precede nothing in particular, but the `track()` must
  precede `:100` so the retry-enabling reset can never be interleaved with the read; and the
  binding change at E1.9 must land or `e` is undefined.
- **Guard — a precision the plan omits (see [I-1](#i-corrections-to-the-plan)):** fire only
  `if (!linkedRef.current)`. The `try` block at `:67-95` is **wider than the awaited call** —
  it also contains `useSession.getState().setVerification(...)` (`:85-90`) and
  `setPhase('done')` (`:94`). A throw from those lands in the same `catch` *after*
  `sleeper_connect_captured` has already fired, which would emit a `failed` for a connection
  that succeeded and break the funnel's arithmetic. The guard costs one boolean and makes the
  event mean exactly "the link attempt was rejected".
- **Call:** `track('sleeper_connect_failed', { reason, status, attempt: attemptsRef.current },
  'SleeperConnect')`.

### F.3 `sleeper_connect_captured`

- **Location:** immediately after `const isVerified = res?.verified === true;` (`:78`) and
  **before** the `if (isVerified)` block at `:80-91` and `setPhase('done')` at `:94`.
- **Condition:** the link POST resolved. Set `linkedRef.current = true` and
  `phaseRef.current = 'done'` on the two lines above the call, so an unmount racing the
  remaining synchronous work is already suppressed.
- **Why before `setVerification`:** a throw inside `:80-91` must not swallow the success
  signal. With F.2's guard, such a throw now produces `captured` and no `failed` — the honest
  reading.
- **Deviation from the ESPN twin, stated:** `espn_connect_captured` fires the instant the
  credential is in hand (`EspnConnectScreen.tsx:186-187`) because on that screen that *is*
  the terminal. Here the credential in hand is the **middle**. Firing at token arrival
  (`:65`) would make `opened → captured` mean "logged in to Sleeper", not "connected", and
  would double-count on retry (`capturedRef` is reset to `false` at `:100`). "Did they ever
  log in?" is preserved as `attempts ≥ 1` on whichever terminal fires. **This is operator
  gate AN-2 / Ckpt B — unresolved.**
- **Call:** `track('sleeper_connect_captured', { verified: isVerified, saw_error:
  sawErrorRef.current, attempts: attemptsRef.current }, 'SleeperConnect')`.

### F.4 `sleeper_connect_abandoned` — the unmount-cleanup guard

**Mechanism:** the mount effect's **cleanup function**, i.e. React unmount — *not* a
back-press listener, *not* a timeout, *not* a blur/focus event. This is exactly the ESPN
twin's mechanism (`EspnConnectScreen.tsx:198-209`), and it **transfers unchanged**: the
Sleeper screen simply has no `useEffect` today. `SleeperConnect` is registered
`presentation: 'modal'` with the **native** chevron and swipe-down dismissal
(`RootNav.tsx:701-712`; unlike `EspnConnect` at `:720-745` it has **no custom `headerLeft`
and no back-button testID**) — both dismissal routes unmount the screen, so a cleanup-based
signal is sound and complete.

**Exact shape:**

```ts
useEffect(() => {
  track('sleeper_connect_opened', { source }, 'SleeperConnect');
  return () => {
    if (!linkedRef.current) {
      track('sleeper_connect_abandoned', {
        phase: phaseRef.current,
        saw_error: sawErrorRef.current,
        attempts: attemptsRef.current,
      }, 'SleeperConnect');
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

Four properties of that guard, each load-bearing — **a mis-specified cleanup double-fires or
never fires**:

1. **Empty dependency array.** With any dependency, the effect re-runs on change, firing a
   second `opened` and a spurious `abandoned`. `[]` gives exactly one mount and one unmount.
2. **The guard is `linkedRef`, NOT `capturedRef`.** `capturedRef` is set at **token arrival**
   (`:65`), before the server leg. Guarding on it would mean a user who logs in and backs out
   while `linkSleeperToken` is still in flight fires **neither** terminal — no `abandoned`
   (guard already true) and no `captured` (the awaited continuation never reaches `:78`).
   That mount would vanish from the funnel entirely. `linkedRef` is set **only** on the
   success path (E1.8), so that case correctly emits `abandoned{phase:'linking'}`.
   `capturedRef` keeps its existing job — the post-once message guard and the retry enabler
   — and is not read by any `track()` call.
3. **Every value read in the cleanup is a `ref`, never state.** A `useEffect(…, [])` cleanup
   closes over the render in which it was created; reading `phase` (`useState` at `:50`) there
   would return `'browsing'` **always**, and the metric would look plausible while being
   wrong. `phaseRef` / `sawErrorRef` / `attemptsRef` / `linkedRef` exist for correctness, not
   style. Same pattern as the twin's `sawOtpRef` (`EspnConnectScreen.tsx:129`) and
   `capturedRef` (`:128`).
4. **No `unmountedRef` is needed here.** The twin carries one (`:130`, `:201`) because its
   capture is an async cookie read that can resolve *after* the abandon path ran. Here the
   only async continuation is the `onMessage` handler, and if it reaches `:78` after unmount
   it sets `linkedRef` and fires `captured` — which is the truth (the link did succeed). If
   an `unmountedRef` is added anyway it must **not** suppress `captured`, or a successful
   late link would report as an abandon.

**Known, accepted exposure:** an OS-initiated unmount (memory pressure, a backgrounding that
tears the modal down) reads as a user decision. Identical exposure to the ESPN twin;
`screen_left`'s `reason: 'background'` (`RootNav.tsx:181-193`) is available to cross-check.
Recorded, not engineered around.

### F.5 The per-mount partition

```
sleeper_connect_opened            × 1
  sleeper_connect_failed          × 0..n     (one per rejected link attempt)
  then exactly ONE of:
    sleeper_connect_captured      (linked; verified true or false)
    sleeper_connect_abandoned     (phase = browsing | linking | error)
```

With F.2's guard this partition is **mutually exclusive and exhaustive per mount**, which is
what makes `captured / opened` a clean connect-success rate and makes
[§G.3](#g3-partition-assertion) mechanically checkable.

---

## G. Proof of landing — the probe procedure

**The wall is default-deny and silent.** A 200 proves nothing:
`analytics_ingest.py:379-384` increments `accepted` *and* `dropped` and `continue`s for an
unknown `event_type`; `:385-390` silently strips unlisted props. Worse, the **mobile client
never reads `dropped`** — `events.ts:311-316` parses only `accepted`, `deduped`, `rejected`,
`disposition`. There is no error signal on either side of the wire. Every check below
verifies **at the destination**.

### G.1 T1 gate probe — before any client wiring

Run **after T1 merges and Render deploys**, before A2 writes a `track()` call. This is
`HLD-p1.md` §C step 1's verification, in P1-10's terms.

1. `POST /api/events` by hand (curl/httpie), one envelope per name, each carrying its **full**
   prop set and a valid envelope (`event_id` 8–64 chars `^[A-Za-z0-9_-]+$`, `session_id`,
   `seq` from 1, `client_ts`, `screen: "SleeperConnect"`) — shape per
   `docs/cross-client-invariants.md:274-283`.
2. **Assert on the response body: `dropped == 0`** (and `accepted == 4`). A non-zero `dropped`
   means at least one name is not registered — **stop; the client wave does not start.**
3. **Assert every prop is echoed back at the destination.** Read the stored `props` for each
   row and confirm all 3–4 keys survive. `dropped == 0` proves the *name* landed; only this
   proves the *props* did. (R-3 in `HLD-p1.md` §F is exactly the failure where the name
   survives and the props vanish.)
4. Secondary, weaker signal: `GET /api/admin/analytics/health` — see the two caveats in
   [I-2](#i-corrections-to-the-plan). It is **not** a substitute for steps 2–3.

### G.2 End-to-end on the simulator — after client wiring

Dev backend, both `analytics.client_events` and `analytics.ingest` **on** (`true` at
`config/features.json:68-69` today). Drive every leg:

| Leg | How to produce it | Expected rows |
|---|---|---|
| A | Settings → "Verify account" → dismiss without logging in | `opened{source:'settings_row'}` + `abandoned{phase:'browsing', saw_error:false, attempts:0}` |
| B | Log in on the WebView as a **different** Sleeper account, then dismiss | `opened` + `failed{reason:'token_user_mismatch', status:403, attempt:1}` + `abandoned{phase:'error', saw_error:true, attempts:1}` |
| C | Log in as the session's own Sleeper account | `opened` + `captured{verified:true, saw_error:false, attempts:1}` |
| D | Repeat once from each of the four entry points | four distinct `source` values |

Then:

1. Force a flush: wait ≥10 s (`FLUSH_INTERVAL_MS`, `events.ts:59`) or background the app.
2. **The row is the proof, not the 200:**
   `SELECT event_type, COUNT(*), platform FROM user_events WHERE event_type LIKE
   'sleeper_connect_%' GROUP BY 1, 3;`
3. **Assert `platform` = `'ios'`, not NULL** — the direct regression check for the
   2026-08-05 incident ([§C.1](#c1-no-platform-prop-of-either-meaning--explicit)).
4. Spot-read `props` for one row of each type and confirm no key was stripped.

### G.3 Partition assertion

Events carry a **per-session monotonic `seq` from 1**
(`docs/cross-client-invariants.md:281`; `events.ts` increments per `track()`), and
`session_id` rotates after 30 min idle or cold start — so a `session_id` can span **several
mounts**. Two assertions, at the right granularity:

- **Aggregate, per `session_id`:** `count(captured) + count(abandoned) == count(opened)`.
- **Sequential, ordering rows by `seq` within `session_id`:** every `opened` is followed by
  exactly one terminal before the next `opened`, and never by both.

The sequential form is the one that actually catches a `capturedRef`-vs-`linkedRef` mix-up
and a state-vs-ref cleanup bug; the aggregate form alone can net out.

### G.4 Post-ship read (within 7 days of first real traffic)

(a) `opened` rows exist with a `source` distribution across all four entry points;
(b) `captured / opened` is a plausible connect success rate; (c) the `reason` histogram is
dominated by `token_user_mismatch` if the screen's error copy describes the real failure.
**A flat zero on any of the four is the silent-drop signature** — re-run G.1 before concluding
that users simply are not connecting.

### G.5 Static checks

- `cd mobile && npx tsc --noEmit` — **not runnable in this worktree** (`node_modules` is a
  stale symlink; never run `npm install` here). Run it in the build worktree.
- `mobile/scripts/testid-lint.sh` — expected exit 0; **no `testID` is added or renamed** under
  the Maestro waiver.

---

## H. Re-verify after P0 merge

`HLD-p1.md` §G is a **gate, not a formality**: answer every row **in writing in
`scope-p1-10.md`** before A2's first edit. **A row that comes back "the premise no longer
holds" stops this item's build and returns it to planning** — it is not patched around at the
keyboard. P0-7 owns the analytics taxonomy and lands before this item.

**§G.0 — every item:**

1. `git fetch origin && git rev-parse origin/main` — record the sha in `scope-p1-10.md`.
2. Confirm the P0 commits are present (P0-1, -2, -3, -5, -6, -7, -8/9).
3. Rebase the P1 branch onto post-P0 `origin/main`; resolve nothing blind.
4. Re-read `living-memory/DECISIONS.md` (and `GOTCHAS.md`, `MISTAKES.md`,
   `OPEN_QUESTIONS.md`) for the next free IDs. **Do not use `D-011` from the plan** — nine
   claimants (`HLD-p1.md` §A.6).
5. Re-grep every `file:line` this LLD cites.
6. Confirm `mobile/node_modules` is still symlinked. **Never run `npm install`.**

**§G.3 — P1-10 specifically:**

- [ ] `SendInSleeperButton.tsx` — **`goConnect` is not at `:114` any more.** P0-6 rewrote the
      gate (`:59-66`) and render tail (`:273`+); P0-7 inserted into `onPress` (`:231`) and the
      `:143` catch. **Re-grep `goConnect`, then edit.**
- [ ] `RootNav.tsx` — P0-5 edits `:297-301`, `:410`; P0-3 edits `:397-421`, `:341`. Re-locate
      the `SleeperConnect` param-list entry (`:58`) and the `navigate('SleeperConnect')` call
      (`:437`).
- [ ] `SettingsScreen.tsx` — **P0-5 extracted the inline Sleeper form into `LinkSleeperSheet`
      (`:423-472`, `:1210-1236`)**, so `:488` and `:1261` have both moved. Re-grep
      `navigateFromSettings('SleeperConnect')`.
- [ ] `SleeperConnectScreen.tsx` — confirm still untouched by P0 (expected: sole owner).
      **Re-confirm the `catch` at `:96` is still bare** — E1.9 requires it to take the error
      binding, and a P0 edit that already bound `e` changes that diff.
- [ ] Confirm all four names are in `ALLOWED_CLIENT_EVENTS` on `main` **and** that T1's live
      probe returned `dropped == 0` with every prop echoed. **No `track()` before that.**

**Two P1-10-specific additions to §G.3, from this LLD's verification pass:**

- [ ] Re-read `analytics_ingest.py`'s allowlist branch (`:379-390` at `ab9368f`) and confirm
      the counted-and-dropped-behind-200 behaviour is unchanged. G.1's entire proof rests on
      the response's `dropped` field remaining meaningful.
- [ ] Re-confirm `POST /api/sleeper/link`'s error enum (`server.py:12181-12257`) is still the
      same eight strings with the same statuses. It is the `reason` vocabulary; P0 does not
      claim this function, but the file takes edits from P0-1, -3, -5, -7 elsewhere.

---

## I. Corrections to the plan

`plan-p1-10.md` is accurate on nearly every citation. Five departures, each verified against
code at `ab9368f`.

**I-1 · `sleeper_connect_failed` needs a `!linkedRef.current` guard; the plan's partition claim
does not otherwise hold.**
`plan-p1-10.md:241-253` claims the per-mount partition is "mutually exclusive and exhaustive",
and `§2.3(a)` places `captured` before the `setVerification` block "so a throw there cannot
swallow the success signal". Both are right about `captured` — but the `try` at
`SleeperConnectScreen.tsx:67` **wraps `:68-95`, not just the awaited call**, so a throw from
`useSession.getState().setVerification(...)` (`:85-90`) or `setPhase('done')` (`:94`) reaches
the same `catch` at `:96` **after** `captured` already fired, emitting a `failed` for a
connection that succeeded. The guard in [§F.2](#f2-sleeper_connect_failed) closes it. **This
changes no event, no prop, and no name — only the firing condition.**

**I-2 · The health endpoint's path and auth are wrong in the plan, the scope block and the
HLD; and its counters are a weak signal.**
All three say `GET /api/analytics/health` (`plan-p1-10.md:569`, `scope-p1-10.md:186`,
`HLD-p1.md` §C step 1). The real route is **`GET /api/admin/analytics/health`**
(`backend/server.py:6977-6978`) and it is **operator-only, gated by `_require_cron_auth()`
(`:6991`) — the `X-Cron-Secret` header, `CRON_SECRET` from `secrets.local.env`.** Two further
caveats the plan does not state: the counters are **in-process and reset on deploy**
(`"since": "deploy"`, `:6995`; `analytics_ingest.py:57-59`), so "stayed flat" is only
meaningful **within one deploy generation**; and on a multi-worker Render instance the probe
may not hit the process that served the events. **Treat the response body's `dropped == 0` and
the stored row as the authoritative proof; treat the health counters as corroboration.**

**I-3 · The route-param union does NOT make a bad `source` a compile error at three of the
four call sites.**
`plan-p1-10.md:581-583` (and `scope-p1-10.md:175-177`) claim the union at `RootNav.tsx:58`
makes any mistyped `source` "a compile error, which is exactly the enforcement wanted".
Verified: only **E2.2** is typed — `RootNav.tsx:437` gets `navigation` from the
`<Stack.Screen>` render prop of `createNativeStackNavigator<AuthStack>()` (`:101`), so it is
checked. The other three are not: `SendInSleeperButton.tsx:67` uses `useNavigation<any>()`;
`SettingsScreen` receives `{ navigation }: any` (`:78`) and routes through
`navigateFromSettings(route: string, params?: object)` (`:220`), which erases the type. **The
enforcement is therefore the screen-side allowlist coercion ([§C](#c-property-shapes--types-value-domains-derivation)),
plus G.2 leg D observing four distinct `source` values.** The param-type widening is still
worth doing — it documents the contract and types the one call site it can — but it must not
be relied on as the vocabulary guard.

**I-4 · The `docs/cross-client-invariants.md` and tracking-plan edits are T1's, not this
item's commit.**
`plan-p1-10.md:322` specifies a standalone in-file addendum after `:146-156`, and `:378`
places the `cross-client-invariants.md:268` bullet in P1-10's own "commit 3". `HLD-p1.md`
§A.5 and §B reassign **both** to the T1 owner (one append point, one `:268` edit, because
three P1 items target each). A2's docs commit carries **only** `docs/integrations/sleeper.md`
plus the `living-memory` write-back. *(Minor: the ESPN addendum's heading is at
`tracking-plan-v2.md:145`, not `:146`.)*

**I-5 · Two small citation drifts, stated for the record.**
(a) `plan-p1-10.md:49` cites the `SleeperConnect` route registration at `RootNav.tsx:702-711`;
the `<Stack.Screen>` element actually spans **`:701-712`** (`:702` is the `name` prop).
(b) `backend/server.py`'s own docstring at `:12172` says "**401** token_rejected", while the
code returns **403** at `:12243`. The plan's enum (403) is right and the docstring is stale;
**this LLD does not fix it** — `server.py` is P1-7's exclusive hold in Wave A
(`HLD-p1.md` §B) and it is a drive-by. File it separately.

---

## J. Deliberately not instrumented

Named so a future session sees these were considered, not overlooked. Each also belongs in
the T1 addendum's "What is deliberately NOT here" paragraph.

- **The OTP step** — [§B.2](#b2-the-otp-step-does-not-map-and-must-not-be-made-to-map).
- **The JWT's `valid_2fa` claim** — server-side, and a property of the *account*, not of
  *this capture*.
- **The confirm/cancel beats around `goConnect`** (`SendInSleeperButton.tsx:157`, `:170`,
  `:267`) — three `Alert` buttons; P0-7 already owns instrumentation in that component.
- **The Keychain silent-replay path** (`sendInSleeper.ts:160-190`) — a background
  re-verification with no screen; a separate funnel, not this one.
- **`persistSleeperToken`'s outcome** (`SleeperConnectScreen.tsx:76`) — already swallowed by
  `.catch(() => {})` and deliberately non-blocking.
- **The WebView's own load / redirect / error events** — `docs/integrations/sleeper.md:400-409`
  states plainly that the server cannot see them; neither can we without DOM observation we
  have no verified basis for.
- **`DELETE /api/sleeper/link`** (disconnect) — a Settings action, not this screen.
- **The stray `setTimeout(navigation.goBack, 1200)` at `:95`, never cleared on unmount** — a
  pre-existing latent warning the new cleanup will sit next to. **Deliberately not fixed**
  (surgical-change rule). Named so a reader sees it was considered; candidate for its own
  ticket.

---

## K. Operator gates — unresolved

**Five checkpoints. This LLD does not resolve any of them.** Three are build-blocking and two
of those must be answered **before T1 freezes the taxonomy** — a wrong answer there means
re-opening a frozen file behind a full re-deploy-and-probe cycle.

| Gate | HLD id | Question | Plan's recommendation | Blocks |
|---|---|---|---|---|
| **A** | **AN-1** | Slot 4: `sleeper_connect_failed`, or the resolutions doc's literal `sleeper_connect_otp_step`? | `_failed` — Option 2 needs a MutationObserver against an **unverified** Sleeper DOM and would ship a permanently-zero event indistinguishable from a real zero | **BUILD — and before T1.** It is T1's name list. |
| **B** | **AN-2** | Does `captured` fire on **link success** or on **token arrival** (the literal ESPN mirror)? | Link success, with the deviation stated in the addendum so the two platforms' curves are never naively compared | **BUILD.** A2's wiring **and** T1's prop-row comment. |
| **C** | **RL-10** | Ship the optional Sleeper-Connect Maestro flow? Closes half of A-31, costs 4 `testID`s **and** a custom `headerLeft` — header chrome, which moves the sim gate **tier 2 → tier 1** | Out; spin off as its own A-31 ticket | **BUILD.** A2's sim-gate tier and testID set. |
| **D** | *adjudicated* | Coordinate the taxonomy registration with P1-5? | **Removed from the operator's queue** — `HLD-p1.md` §A.2 adopted it and widened it to three items as commit **T1**. Recorded here so nobody re-asks. | — |
| **E** | **RL-11** | Also rename `sleeperconnect.done` (`:157`, referenced by **zero** flows) → `sleeper-connect.done`? | Only if RL-10 is taken, so the screen's ids land in one convention at once | release |

Everything in [§B](#b-the-event-set--finalised-with-the-otp-non-mapping) through
[§G](#g-proof-of-landing--the-probe-procedure) is written on the **recommended** answers to A
and B. If either is overturned, this LLD's §B–§D change and T1's contents change with it.
