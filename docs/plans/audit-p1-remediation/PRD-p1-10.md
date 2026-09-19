# PRD — P1-10 · Sleeper Connect in-flow analytics (audit A-19)

> **Status:** requirements only. **No source file is changed by this document.**
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f`. All `file:line` verified at that sha and
> **will move after the P0 merge** — re-locate by content.
> **Design of record:** [`LLD-p1-10.md`](LLD-p1-10.md). **Sequencing of record:**
> [`HLD-p1.md`](HLD-p1.md) (wave A / agent A2; merges after commit **T1**).
> **Binding operator decisions:** [`DECISIONS-p1.md`](DECISIONS-p1.md).
> **Gate posture:** FULL gates. Analytics events are a root-`CLAUDE.md` bright line; the
> express lane is neither available nor requested.

## Contents

- [1. Problem — stated accurately](#1-problem--stated-accurately)
- [2. The funnel this creates, and what it answers](#2-the-funnel-this-creates-and-what-it-answers)
- [3. Scope and non-goals](#3-scope-and-non-goals)
- [4. Acceptance criteria](#4-acceptance-criteria)
- [5. Maestro flow specs](#5-maestro-flow-specs)
- [6. Docs impact table](#6-docs-impact-table)
- [7. Operator gates](#7-operator-gates)
- [8. Rollback](#8-rollback)
- [9. Risks](#9-risks)

---

## 1. Problem — stated accurately

**The audit's framing — "Sleeper Connect has zero in-flight analytics" — is overstated, and
the correction changes what gets built.**

`RootNav.tsx` already instruments this modal. `:352` (boot) and `:376` (`onStateChange`) fire
`screen_viewed` for **every** route — `navigationRef.getCurrentRoute()` resolves to
`SleeperConnect` while the modal is presented — and `:366` fires `screen_left` with a real
`dwell_ms`. **Mount count and dwell already exist today.** A builder told "the screen is
dark" would duplicate `screen_viewed` and add nothing.

**The accurate problem: every in-flow OUTCOME is missing.**
`mobile/src/screens/SleeperConnectScreen.tsx` is 195 lines, contains **zero `track()` calls,
does not import `track` at all, and has no `useEffect` anywhere in the file**. So today we
can see that someone opened the screen and how long they stayed — and nothing else:

- Did they ever log in to Sleeper, or bounce off the login page?
- Did the server reject the token, and for which of eight reasons?
- Did they retry, and how many times?
- Did the link succeed, and did it produce a **verified** session or an inconclusive one?
- Which of the four entry points sends people who actually finish?

**Why this is worth a bright-line change.** This screen is the only way a Sleeper-keyed
session becomes verified, and `/api/trades/propose` hard-gates on `sess["verified"]` with
**no grace period** (`backend/server.py:12321-12329`). It also gates every account-data action
behind `promptVerifyStepUp`. It is the most consequential single action in the app, and its
drop-off curve is invisible.

**Second problem, smaller and cheap to fix.** `docs/integrations/sleeper.md:408` suggests a
client event named **`sleeper_connect.abandoned`** — a **dotted** name that violates the
snake_case taxonomy convention (`backend/analytics_taxonomy.py:38-99`). Copied into `track()`
as written, it would be **counted-and-dropped behind a 200** with no error anywhere. The idea
is adopted; the string must be corrected in the doc so a future builder does not inherit a
broken one.

**The wall this ships against.** `ALLOWED_CLIENT_EVENTS` is **default-deny and silent**:
`analytics_ingest.py:379-384` increments `accepted` *and* `dropped` and moves on for an
unregistered name; `:385-390` strips unlisted props. The mobile client never even reads
`dropped` (`events.ts:311-316`). **A 200 proves nothing.** Every acceptance criterion below is
written to be provable at the destination.

---

## 2. The funnel this creates, and what it answers

Four events, all client-fired, all INTENT, `screen = 'SleeperConnect'`:

| Event | Props | Fires |
|---|---|---|
| `sleeper_connect_opened` | `source` | screen mounts (1 per mount) |
| `sleeper_connect_failed` | `reason`, `status`, `attempt` | `POST /api/sleeper/link` rejected (0..n per mount) |
| `sleeper_connect_captured` | `verified`, `saw_error`, `attempts` | link **succeeded** (terminal) |
| `sleeper_connect_abandoned` | `phase`, `saw_error`, `attempts` | screen unmounted without a successful link (terminal) |

Per mount:

```
opened × 1
  failed × 0..n
  then exactly ONE of:  captured   |   abandoned
```

**Questions it answers that nothing answers today:**

1. **Connect success rate** = `captured / opened`, sliceable by `source` — which of the four
   entry points converts, and which just annoys people.
2. **Where people fall out** — `abandoned{phase:'browsing'}` (never logged in to Sleeper) vs
   `{phase:'error'}` (rejected, then gave up) vs `{phase:'linking'}` (left mid-request).
3. **Why the server said no** — the `reason` histogram over a closed 11-value enum. The
   screen's own error copy predicts `token_user_mismatch` dominates
   (`SleeperConnectScreen.tsx:130-135`); this is the first evidence either way.
4. **Whether retrying works** — `attempts` on the terminals against `attempt` on the failures.
5. **Verification quality** — `captured{verified:false}` isolates the "inconclusive oracle"
   branch (`server.py:12245-12248`): linked but not verified, which still blocks
   `/api/trades/propose`.

**Two things this funnel deliberately cannot answer, stated up front so nobody reads a
silence as a signal:**

- **Whether the user hit Sleeper's OTP/2FA step.** Sleeper resolves password/OTP/passkey/2FA
  inside **its own page** (`docs/plans/sleeper-write-capture-runbook.md:128,134`); the
  injected script only polls `localStorage['token']` and observes no DOM
  (`SleeperConnectScreen.tsx:27-46`); and this repo holds **no verified selector** for
  Sleeper's OTP input. A detector built on a guessed selector would ship a
  **permanently-zero event indistinguishable from a real zero** — the A-33 failure class
  (`HLD-p1.md` §F R-5). **It is not built, and must not be added later "for symmetry with
  ESPN."** `saw_error` occupies `saw_otp`'s structural slot; Sleeper's real hard step is the
  server-side link rejection, which slot 4 measures.
- **A before/after comparison.** There is no baseline; these events have never fired.

---

## 3. Scope and non-goals

**In scope:** four `track()` calls in `SleeperConnectScreen.tsx`, four refs, one mount effect,
one `useRoute()` read, one `catch {` → `catch (e)`; four navigate call sites gain a `source`
argument; one route-param type widens; the `sleeper.md:408` correction; this item's slice of
commit **T1**; the `living-memory` write-back.

**Explicitly NOT in scope:** any rendered element, copy string, layout, colour, timing,
navigation behaviour, route, schema, feature flag, env var, `model_config` key, or API
contract. No new `testID` (unless gate C is taken). No edit to
`backend/analytics_queries.py`. No `platform` prop of either meaning. No credential-derived
property of any kind. Full "deliberately not instrumented" list: `LLD-p1-10.md` §J.

---

## 4. Acceptance criteria

Numbered, individually testable. **Each event-landing criterion names the artifact that
proves it** — a 200 is never sufficient.

### 4.1 Registration and the T1 gate (must pass before any client wiring)

1. **The four names are registered.** `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS`
   contains exactly `sleeper_connect_opened`, `sleeper_connect_failed`,
   `sleeper_connect_captured`, `sleeper_connect_abandoned`, added as part of **commit T1** —
   not a P1-10-only commit.
   *Proof:* the names appear in the merged file on `origin/main`, and
   `backend/tests/test_analytics_p0.py::test_live_taxonomy_is_disjoint`'s membership
   assertion (T1's single combined edit) passes.
2. **All four have prop rows.** `CLIENT_EVENT_PROPS` carries the four frozensets in
   `LLD-p1-10.md` §D.2, in the same commit as criterion 1.
   *Proof:* the backend imports at all. A missing row raises `ValueError` at import
   (`analytics_taxonomy.py:326-332`) and the entire test suite fails to collect — it cannot
   ship half-registered.
3. **`backend/analytics_queries.py` receives no P1-10 row, by decision.** All four are INTENT.
   *Proof:* the merged diff shows no `sleeper_connect_*` string in that file, **and** the
   decision is recorded in the T1 addendum and `living-memory/DECISIONS.md` so a later reader
   cannot mistake it for an omission.
4. **The live T1 probe returns `dropped == 0` and echoes every prop.** After T1 merges and
   Render deploys, a hand-rolled `POST /api/events` carrying one envelope per name with its
   **full** prop set returns `accepted == 4, dropped == 0`, and the stored row for each name
   retains all of its props.
   *Proof:* the raw response body plus a destination read of `user_events.props`, both pasted
   into `scope-p1-10.md`. **`accepted` alone is not proof** — `analytics_ingest.py:379-384`
   counts a dropped event as accepted. **Failing this, no client wiring begins.**
5. **The guard is still armed.** A deliberately misspelled `sleeper_connect_capturd` is
   counted-and-dropped.
   *Proof:* the negative-control assertion in `test_sleeper_connect_events_accepted`'s
   sibling test, mirroring `test_unknown_type_dropped` (`test_events_api.py:246`).
6. **A bogus `platform` prop is stripped.** Posting `sleeper_connect_opened` with a
   `platform` prop lands the event with that key **absent** from the stored props.
   *Proof:* the prop-stripping control test. This is the direct regression guard for the
   pre-2026-08-05 NULL-`platform` incident and for the decision that no connect event carries
   a platform prop of either meaning.

### 4.2 Client emission — each event proven to land

7. **`sleeper_connect_opened` fires exactly once per mount, with a valid `source`.**
   *Proof (sim, G.2 leg D):* open the screen once from each of the four entry points; the
   destination shows four `opened` rows with four **distinct** `source` values —
   `send_button`, `verify_banner`, `settings_row`, `settings_stepup` — and no duplicate row
   for a single mount.
8. **`source` degrades to `unknown`, never to an unbounded value.** Navigating to
   `SleeperConnect` with no params, or with an unrecognised `source`, produces
   `source: 'unknown'`.
   *Proof:* code review of the allowlist coercion (`LLD-p1-10.md` §C) **plus** a destination
   query confirming `SELECT DISTINCT props->>'source'` is a subset of the five legal values.
   *(The compiler cannot enforce this — see criterion 20.)*
9. **`sleeper_connect_failed` fires on a real server rejection with the real `reason` and
   `status`.**
   *Proof (sim, G.2 leg B):* log in on the WebView as a **different** Sleeper account than
   the session; the destination shows one `failed` row with
   `reason: 'token_user_mismatch'`, `status: 403`, `attempt: 1`.
10. **`sleeper_connect_failed` fires above the retry reset.** The `track()` call precedes
    `capturedRef.current = false` (`SleeperConnectScreen.tsx:100`), so the retry enabler
    cannot race the read.
    *Proof:* code review of the merged diff; ordering is visible in the hunk.
11. **`sleeper_connect_failed` never fires after a successful link.** A throw from the
    post-success work inside the same `try` (`:80-95`) does not emit a `failed`.
    *Proof:* the `!linkedRef.current` guard is present in the merged diff, **and** the
    partition assertion (criterion 14) holds.
12. **`sleeper_connect_captured` fires on link success with the real `verified` value.**
    *Proof (sim, G.2 leg C):* log in as the session's own Sleeper account; the destination
    shows one `captured` row with `verified: true`, `saw_error: false`, `attempts: 1`, and
    **no** `abandoned` row for that mount.
13. **`sleeper_connect_abandoned` fires on modal dismissal with a truthful `phase`.**
    *Proof (sim, G.2 legs A and B):* dismissing without logging in yields
    `abandoned{phase:'browsing', saw_error:false, attempts:0}`; dismissing after a rejection
    yields `abandoned{phase:'error', saw_error:true, attempts:1}`. **`phase: 'error'` is the
    only assertion that catches a cleanup reading `phase` state instead of `phaseRef`** — the
    subtlest bug available here, because a state read returns `'browsing'` always and the
    metric still looks plausible.
14. **The per-mount partition holds.** Ordering rows by `seq` within `session_id`, every
    `opened` is followed by exactly one terminal before the next `opened`, and never by both.
    Aggregated per `session_id`, `captured + abandoned == opened`.
    *Proof:* the destination query in `LLD-p1-10.md` §G.3. `session_id` spans multiple mounts
    (it rotates on 30-min idle / cold start), so the **sequential** form is the load-bearing
    one; the aggregate form alone can net out.
15. **A dismissal while the link request is in flight still produces a terminal.** Backing out
    during the `linking` overlay emits `abandoned{phase:'linking'}` — it does not vanish.
    *Proof:* the abandon guard is `linkedRef` (set only on the success path), **not**
    `capturedRef` (set at token arrival, `:65`); verifiable in the merged diff and, where the
    timing can be reproduced, by criterion 14's sequential assertion.
16. **The `platform` column is populated.** Every `sleeper_connect_*` row stores
    `platform = 'ios'`, not NULL.
    *Proof:*
    `SELECT event_type, COUNT(*), platform FROM user_events WHERE event_type LIKE 'sleeper_connect_%' GROUP BY 1,3;`

### 4.3 No collateral change

17. **No user-visible change.** The merged diff contains no change to a rendered element,
    copy string, style, layout, navigation behaviour, route registration, or timing.
    *Proof:* diff review + the smoke subset passing **unchanged** (§5.1).
18. **No surface change.** No route added/renamed/removed/contract-changed; no schema change;
    no feature flag added or re-defaulted; no env var or `model_config` key.
    *Proof:* the diff touches none of `config/features.json`, `backend/feature_flags.py`,
    `backend/database.py`, or any `@app.route`.
19. **No credential-derived property exists.** No JWT, token fragment, token length,
    `sleeper_user_id`, or `valid_2fa` claim appears in any `track()` call.
    *Proof:* diff review, plus the four prop rows being closed frozensets — anything else is
    stripped server-side regardless.
20. **The route-param union is added and its limits are documented.**
    `RootNav.tsx`'s `AuthStack` entry for `SleeperConnect` carries the four-value `source`
    union.
    *Proof:* `npx tsc --noEmit` clean in the build worktree. **Note explicitly:** this types
    only the `RootNav.tsx` call site; `SendInSleeperButton.tsx` uses `useNavigation<any>()`
    and `SettingsScreen` routes through `navigateFromSettings(route: string, params?: object)`,
    so the compiler does **not** police the vocabulary at three of four sites. Criterion 8 is
    the real guard.
21. **`docs/integrations/sleeper.md:408`'s dotted name is gone.** The prose no longer contains
    `sleeper_connect.abandoned`; it names the four shipped snake_case events and links the T1
    addendum.
    *Proof:* `grep -rn "sleeper_connect\." docs/` returns zero hits.

### 4.4 Ship gates

22. **`pytest backend/tests/` green** (T1's tests included) and **`npx tsc --noEmit` clean**
    in the build worktree.
23. **`mobile/scripts/testid-lint.sh` exits 0** with **no `testID` added or renamed** — the
    condition that keeps the Maestro waiver honest (§5.1).
24. **The sim gate is run, logged, and evidenced.** Tier 2 as scoped
    (`docs/runbook.md:97` — "Mobile logic touched, no UI change"): the affected smoke subset
    (§5.1) plus `mobile/scripts/screen-freshness.sh` (expected: flags nothing).
    *Proof:* a `living-memory/TEST_LEDGER.md` entry carrying the tier, the flows run, the sim
    device and the sha, **plus** the criterion-4/16 destination evidence; and
    `qa/sim-runs/last-sim-run.json` written. `FTF_SKIP_SIM_GATE=1` is **not** available.
25. **The `living-memory` write-back is complete, with IDs allocated at write time.**
    `DECISIONS.md` records (i) no `sleeper_connect_otp_step` and why an unverifiable detector
    is worse than no event, (ii) `captured` = link success not token arrival, (iii) all four
    INTENT. `CHANGELOG.md` and `TEST_LEDGER.md` updated on ship.
    *Proof:* **the ID is re-derived by reading the file at write time — never `D-011` from the
    plan** (nine claimants, `HLD-p1.md` §A.6). `living-memory-format-check` passes.

---

## 5. Maestro flow specs

**Starting fact, stated first:**
`grep -rn "sleeperconnect\|SleeperConnect\|sleeper-connect" mobile/.maestro/` returns
**zero hits** at `ab9368f`. **No existing flow asserts this surface**, so there is no flow to
update as part of the fix. (The twin does have one:
`mobile/.maestro/flows/espn-connect-capture.yaml`, 94 lines.) The only nearby hits are
`mobile/.maestro/capture/matches@espn.yaml:118,154`, which assert the *Send in Sleeper*
button label — untouched by this item.

### 5.1 Default path (RL-10 = out) — waiver + the subset that must pass unchanged

**Mandatory Maestro delta: WAIVED**, in writing, per root `CLAUDE.md` §Conventions — the same
waiver class P0-7 takes for the same change class.

*Reason:* every insertion is a `track()` call (synchronous, `void`, swallows all errors —
`events.ts:186-215`), a ref mutation, or a route param. Maestro asserts on **rendered UI** and
has no visibility into the analytics queue or a `POST /api/events` batch, so a flow here would
assert only the *absence* of a regression — which the existing suite already does.
Verification moves to the backend tests (§4.1) and the destination probe (§4.2).

**Two conditions keep the waiver honest — both are acceptance criteria:**
- The existing suite must pass **unchanged**. **Any diff to an existing flow file invalidates
  the waiver.**
- **No `testID` is added or renamed** (criterion 23).

**Concrete subset to run (tier 2), and why each:**

| Flow file | Why it is affected |
|---|---|
| `mobile/.maestro/04-tabs-navigation.yaml` | authed `RootNav` root — the region containing the `VerifyAccountBanner` navigate edit |
| `mobile/.maestro/flows/smoke/01-signin.yaml` | reaches the authed root; boot-path `screen_viewed` still fires |
| `mobile/.maestro/flows/smoke/08-matches.yaml` | `SendInSleeperButton` renders here |
| `mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` | crosses `SettingsScreen` |
| `mobile/.maestro/capture/settings.yaml` | `SettingsScreen` capture; runs only if `screen-freshness.sh` flags it (expected: it does not) |

Re-derive this list by grep at build time — P0-5's `LinkSleeperSheet` extraction and P0-6's
`SendInSleeperButton` rewrite may have moved which flows touch which screens.

### 5.2 Conditional path (RL-10 = in) — the concrete flow, if the operator takes gate C

**New file:** `mobile/.maestro/flows/sleeper-connect-capture.yaml`, mirroring
`espn-connect-capture.yaml` in structure and header conventions.

**Header:** `appId: com.fantasytradefinder.app`; `# tc:` id; `# profile: standard`;
`# flags: release`; `tags: [sleeper, webview]`; and a header note recording that the
**in-WebView Sleeper login is WAIVED** — it is a live third-party page the hermetic harness
cannot drive. The flow covers app-side chrome only.

**Steps — `id:` selectors only** (no text selectors, no coordinate taps, no fixed `sleep`;
`testid-lint.sh:14-22` fails the build on any of those):

1. `launchApp` with `clearState / clearKeychain / stopApp`.
2. `extendedWaitUntil visible id: "signin.username-input"` → `tapOn` → `inputText qa_standard`
   → `tapOn id: "signin.continue-btn"`.
3. Navigate to Settings and `extendedWaitUntil visible id: "settings.verify-account-row"`.
4. `tapOn id: "settings.verify-account-row"`.
5. `extendedWaitUntil visible id: "sleeper-connect.webview"`; `assertVisible id:
   "sleeper-connect.banner"` — **consent copy asserted by id**, because Maestro text selectors
   are full-match regexes (the ESPN flow's own header note).
6. `takeScreenshot: sleeper-connect-mounted`.
7. `tapOn id: "sleeper-connect.back-btn"` → `extendedWaitUntil visible id:
   "settings.verify-account-row"` → `takeScreenshot: sleeper-connect-backed-out`.

This drives `sleeper_connect_opened` and the `phase: 'browsing'` abandon leg end to end, and
closes half of audit **A-31** (Settings has no flow at all).

**Its cost, stated plainly — this is why the recommendation is "out":**

| New `testID` | Where | Note |
|---|---|---|
| `sleeper-connect.banner` | `SleeperConnectScreen.tsx:109` (banner `View`) | |
| `sleeper-connect.webview` | `:138` (`WebView`) | mirrors `espn-connect.webview` |
| `settings.verify-account-row` | `SettingsScreen.tsx:1259` (`Pressable`) | matches the existing `settings.*` convention (`:787`, `:806`, `:1074`) |
| `sleeper-connect.back-btn` | **requires `headerBackVisible: false` + a `HeaderBack` `headerLeft`** on the `SleeperConnect` route (`RootNav.tsx:701-712`), exactly as `EspnConnect` does at `:730-744` (the #151 iOS-26 pattern) | **This is the one real cost — it changes the modal's header chrome, moving the sim gate from tier 2 to tier 1** (full 11-flow smoke + `screen-capture.sh` for the touched screen) |

All four are static string literals, so `testid-lint.sh`'s grep check passes with no
`testid-lint-allow.txt` entry. Taking this path also makes gate **E** (renaming the screen's
lone existing `sleeperconnect.done` at `:157`, referenced by **zero** flows, to
`sleeper-connect.done`) free, and `docs/design/` becomes an in-scope doc row.

**Recommendation carried from `HLD-p1.md` RL-10: out for this item; spin the flow off as its
own A-31 ticket.** Bundling a header-chrome change into an instrumentation fix is the
drive-by the coding guidelines forbid, and it triples the ship cost of an Effort-S item.

---

## 6. Docs impact table

One row per `docs/CLAUDE.md` trigger. Every row answered. **Ownership column matters:**
`HLD-p1.md` §A.5 and §B fold three items' analytics-doc edits into **T1**, so several rows
this item is responsible for *authoring* are *committed* by the T1 owner.

| Doc | Updated? | Owner | Section / reason n/a |
|---|---|---|---|
| `docs/integrations/sleeper.md` | **YES** | **A2** | `:408` — replace the illegal dotted `sleeper_connect.abandoned` with the four shipped snake_case names, mark the funnel gap closed, link the addendum. Left as-is, a future builder copies a string that is silently dropped. |
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` | **YES — mandatory, precondition of registration** | **T1** | P1-10's rows go into T1's single "Addendum 2026-08-11 — P1 round" section, appended after the ESPN addendum (`:145-156`). Required content: `LLD-p1-10.md` §D.6 — four-row table, the no-credential rule, the "deliberately NOT here" paragraph (OTP step, `valid_2fa`, confirm/cancel beats, Keychain silent replay, WebView load events, `DELETE` leg), the `captured`-deviation warning, INTENT-by-decision, and the DAU/WAU seam date. `analytics_taxonomy.py:9-10` makes the addendum a **precondition**, not a follow-up. |
| `docs/cross-client-invariants.md` | **YES** | **T1** | §"Client analytics event contract" (`:268`) — add the four names to the allowed-names list at `:285-292` and note that `web/js/events.js` and `extension/background.js` fire none of them, so the omission reads as deliberate. Three P1 items target `:268`, hence T1 ownership. *(Observed, out of scope: the list is already stale — missing `espn_connect_*`, `draft_room_*`, `guide_*`, `screen_left`, `api_request_failed`.)* |
| `living-memory/DECISIONS.md` | **YES** | **A2** | Three decisions: (i) no `sleeper_connect_otp_step` and why; (ii) `captured` = link success, not token arrival; (iii) all four INTENT and `analytics_queries.py` deliberately untouched. **ID allocated at write time — not `D-011`.** Not an ADR: instrumentation inside an existing pipeline, and D-021 already covers the connect-capture architecture. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **YES, on ship** | **A2** | Root `CLAUDE.md` §Session memory. TEST_LEDGER carries the sim tier **and** the criterion-4/16 destination evidence. |
| `docs/api-reference.md` | **n/a** | — | No route added, renamed, removed, or contract-changed. `POST /api/events` accepts the four names purely by registry membership; its request/response shape is untouched. `POST /api/sleeper/link` is **read-only reference** — its error enum supplies the `reason` vocabulary and is not modified. |
| `docs/data-dictionary.md` | **n/a** | — | No schema change. Verified: **no client event name appears in this file** (neither `espn_connect_*` nor `draft_room_*`); its `event_type` rule covers **server-fired** types, and this item adds none. |
| `docs/config-reference.md` | **n/a** | — | No env var, flag, or `model_config` key. |
| `docs/architecture.md` · `living-memory/HLD.md` | **n/a** | — | No new module or path. `track()` → existing queue → existing `POST /api/events` → `user_events`. |
| `living-memory/LLD.md` | **n/a** | — | No convention shifts. "Register before wiring" is P0-7's existing convention, obeyed here, not invented here. |
| `docs/glossary.md` | **n/a** | — | No new domain term; "connect", "capture", "verified session" are all in use. |
| `docs/adr/` | **n/a** | — | `DECISIONS.md` is the right weight. |
| `docs/design/` | **n/a** as scoped | — | No rendered change. Becomes **YES** only under gate C's `HeaderBack` — and even then it reuses the `EspnConnect` header pattern verbatim, adding no new visual token. |
| `docs/runbook.md` | **Conditional** | A2 | Only if the destination probe surprises. G-017 (paired analytics gates fail silently) already covers the known trap. |
| `living-memory/GOTCHAS.md` · `MISTAKES.md` · `OPEN_QUESTIONS.md` | **Conditional** | A2 | Only if verification surprises. |
| `docs/templates/feature-scope.md` | **YES (copied, not edited)** | A2 | [`scope-p1-10.md`](scope-p1-10.md) — and it must be **updated** with the §G re-verification answers and the post-P0 sha before build. |

**Correction carried into this table:** `plan-p1-10.md:322` and `:378` place the tracking-plan
addendum and the `cross-client-invariants.md:268` bullet in P1-10's own commit; `HLD-p1.md`
reassigns both to T1. A2's docs commit carries **only** `docs/integrations/sleeper.md` plus
the `living-memory` write-back.

---

## 7. Operator gates

**Five checkpoints. None is resolved by this document.** Three are build-blocking, and two of
those must be answered **before T1 freezes the taxonomy** — after T1 merges,
`analytics_taxonomy.py` and `analytics_queries.py` are frozen for the round and any change
costs a T1 amendment commit with the full re-deploy-and-probe gate.

| Gate | HLD id | Question | Recommendation of record | Blocks |
|---|---|---|---|---|
| **A** | **AN-1** | Slot 4: `sleeper_connect_failed`, or the resolutions doc's literal `sleeper_connect_otp_step`? | `_failed`. Option 2 needs a MutationObserver against an **unverified** Sleeper DOM and would ship a permanently-zero event indistinguishable from a real zero. This deviates from the resolutions doc's wording, and deviates **toward** a verified signal. | **BUILD — before T1.** It is T1's name list. |
| **B** | **AN-2** | Does `captured` fire on **link success** or on **token arrival** (the literal ESPN mirror)? | Link success — a clean `captured / opened` success rate and a mutually-exclusive partition; token arrival double-counts on retry and makes the curve mean "logged in", not "connected". Either way `attempts` preserves the other measurement. | **BUILD.** A2's wiring **and** T1's prop-row comment. |
| **C** | **RL-10** | Ship the optional Sleeper-Connect Maestro flow (§5.2)? | **Out** — spin off as its own A-31 ticket. It costs 4 `testID`s **and** a custom `headerLeft`, moving the sim gate tier 2 → tier 1. | **BUILD.** A2's sim-gate tier and testID set. |
| **D** | *adjudicated* | Coordinate the taxonomy registration with P1-5? | **Removed from the operator's queue.** `HLD-p1.md` §A.2 adopted P1-10's shared-commit recommendation and **widened it to three items** as commit T1. Recorded so nobody re-asks. | — |
| **E** | **RL-11** | Also rename `sleeperconnect.done` (`:157`, referenced by zero flows) → `sleeper-connect.done`? | Only if C is taken, so the screen's ids land in one convention at once. | release |

Everything in this PRD is written on the **recommended** answers to A and B. If either is
overturned, §2, §4.2 and T1's contents change with it.

**Round-level context the operator should hold alongside gate C** (`HLD-p1.md` §F R-1):
**P1-10 is the only invisible item in the P1 round** — four of the seven items ship
user-visible change **live on merge**, with `git revert` rather than a flag flip as their
rollback. That is a release-plan fact, not a P1-10 footnote.

---

## 8. Rollback

**Three levers, in increasing cost. Note G-017: the analytics gates fail silently — verify at
the destination, never at the 200.**

1. **Deploy-free kill switch (preferred).** Set `analytics.client_events` → `false`
   (`config/features.json:68`) to stop emission client-side, or `analytics.ingest` → `false`
   (`:69`) to stop storage server-side. Both are `true` today. **This is a blunt instrument:
   it silences *all* client analytics, not just these four events** — there is no per-event
   flag, and none is warranted (root `CLAUDE.md` reserves flags for user-visible behaviour,
   and there is none here).
2. **Revert the client commit (A2's Wave-A commit).** Removes the four `track()` calls, the
   refs, the mount effect and the four navigate arguments. **Safe in isolation** — the
   registry entries left behind in T1 are inert; an allowlisted name that nothing emits costs
   nothing.
3. **Revert T1 — do not, without coordination.** T1 carries **nine** names across three items
   plus **two modified prop rows**. Reverting it to undo P1-10 would silently un-register
   P1-5's and P1-1/2's events, reproducing the exact counted-and-dropped-behind-200 failure
   the commit exists to prevent. **If a registry change must be undone, it goes through a T1
   amendment commit with the same deploy-and-verify gate**, never a bulk revert.

**What rollback cannot undo:** the DAU/WAU seam. These four events are INTENT, so their first
emission adds a small number of otherwise-uncounted active users to the series. Reverting
stops the addition but leaves the discontinuity in history — which is why the seam date is a
mandatory line in the T1 addendum and the CHANGELOG (`HLD-p1.md` §F R-9).

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Client wired before T1 is on `main` and deployed** → all four counted-and-dropped behind 200s; a dashboard that renders empty with no error anywhere. **Prior art in this repo** — `invite_shared` has been firing into the wall since it shipped. | **High** | Criterion 4's live probe is a hard gate on the client wave. Criteria 1–2 and 5 are the automated guards. |
| **T1's merge drops a name set or strips a modified prop row** (`HLD-p1.md` R-2 / R-3) | **High** | One commit, one owner; T1.6's **single exact-set** disjointness assertion; every acceptance test asserts **prop survival**, not merely acceptance. |
| **Someone "restores symmetry" by adding a `sleeper_connect_otp_step`** against a guessed Sleeper selector → permanently-zero event indistinguishable from a real zero (`HLD-p1.md` R-5) | **High if built** | The reasoning is written into the registry comment (`LLD-p1-10.md` §D.1), the addendum, and `DECISIONS.md` — three places a future reader hits before the code. |
| **Cleanup reads `phase` state instead of `phaseRef`** → every `abandoned` reports `phase: 'browsing'`; the metric looks plausible and is wrong | **Medium — the subtlest bug here** | Criterion 13's explicit `phase: 'error'` assertion is the only check that catches it. |
| **Abandon guarded on `capturedRef` instead of `linkedRef`** → every in-flight-dismissal mount vanishes from the funnel | Medium | Criterion 15 + criterion 14's sequential partition assertion. |
| **P0 moved the three shared files** (`SendInSleeperButton.tsx`, `SettingsScreen.tsx`, `RootNav.tsx`) and an agent edits by line number | Medium | `HLD-p1.md` §G.3, restated in `LLD-p1-10.md` §H — re-grep `goConnect` and `navigateFromSettings('SleeperConnect')`; answer every row **in writing** in `scope-p1-10.md` before the first edit. |
| **`abandoned` fires on an OS-initiated unmount** (memory pressure, backgrounding) and reads as a user decision | Low | Identical exposure to the ESPN twin. `screen_left`'s `reason: 'background'` (`RootNav.tsx:181-193`) cross-checks. Recorded, not engineered around. |
| **Retry loop inflates raw row counts** — 3 retries = 3 `failed` + 1 terminal | Low — intended | `attempt` / `attempts` disambiguate; analysts count mounts via `session_id` + `seq`, not raw rows. Documented in the addendum. |
| **Volume** — 4 events on a rare flow | Negligible | Far inside the 500-item queue cap; none is `FUNNEL_CRITICAL`, so `trimQueue` degrades gracefully. |
