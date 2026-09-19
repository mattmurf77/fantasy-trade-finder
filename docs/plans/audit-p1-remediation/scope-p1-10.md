# Feature Scope — P1-10 · Sleeper Connect analytics (audit A-19)

<!--
Copied from docs/templates/feature-scope.md. Every section answered or explicitly WAIVED.
Full plan: plan-p1-10.md (all file:line citations re-verified against this worktree).
-->

**Date:** 2026-08-11
**Entry point:** mobile UX audit `docs/business/product/2026-08-09-mobile-ux-audit/` —
`04-priority-backlog.md` §P1 row **P1-10**, `06-resolutions.md:104` row **A-19**
**Builder:** planning session on worktree `ftf-p1-remediation`, branch
`p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main`). Build session TBD.
**Operator sign-off on waivers:** **REQUIRED — not yet given.** Two waivers below
(§3 Maestro delta; §1 the OTP-step deviation is a *design decision*, surfaced as
Checkpoint A, not a waiver). Five operator checkpoints in plan §9.

**Gate posture:** FULL gates. Root `CLAUDE.md` bright line — *"a change touching schema,
API contracts, feature-flag surfaces, or **analytics events** is not a quick fix."*
Analytics events are the entire item. **Express lane not available and not requested.**

**Upstream dependency:** P0-7 (`ftf-p0-remediation`, branch `p0-remediation-2026-08-10`)
owns the analytics taxonomy and **merges to `main` before this item builds**. Rebase onto
post-P0 `main` before touching a line — P0-6 and P0-7 both rewrite
`SendInSleeperButton.tsx`, so its line numbers will have moved.

---

## 1. Analytics scope

**(a) New events specced.** Four client-fired events, mirroring the naming *pattern* of the
ESPN twin (`EspnConnectScreen.tsx:187,199,204,245` → `espn_connect_opened / _otp_step /
_captured / _abandoned`, registered at `analytics_taxonomy.py:97-98` + `:251-254`).
`screen` = `'SleeperConnect'` on every call.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `sleeper_connect_opened` | `source` str ∈ `send_button \| verify_banner \| settings_row \| settings_stepup \| unknown` | New mount `useEffect`, first statement (`SleeperConnectScreen.tsx:~53`) | mobile only |
| `sleeper_connect_failed` | `reason` str (11-value closed enum: the 8 `POST /api/sleeper/link` codes at `server.py:12163-12290` + `timeout \| network \| unknown`); `status` int\|null; `attempt` int | First statement of the existing `catch`, `:96` — above the `capturedRef.current = false` retry reset at `:100` | mobile only |
| `sleeper_connect_captured` | `verified` bool; `saw_error` bool; `attempts` int | Link **success** path, after `isVerified` (`:78`), before `setPhase('done')` (`:94`) | mobile only |
| `sleeper_connect_abandoned` | `phase` str ∈ `browsing \| linking \| error`; `saw_error` bool; `attempts` int | Mount effect **cleanup**, guarded by `!linkedRef.current`. Mirrors `EspnConnectScreen.tsx:204` | mobile only |

**Reserved-name check — done.** `backend/analytics_queries.py` reserves **no**
`sleeper_connect_*` name (read `:45-105`: `WAT_LIVE`/`WAT_DARK` `:51-53` reserve only
`sleeper_send_*`, which is P0-7's item; `FUNNEL_STAGES` `:69-80` and `FEATURE_VERTICALS`
`:83-96` have no connect stage). A repo-wide grep returns one prose hit,
`docs/integrations/sleeper.md:408`, suggesting `sleeper_connect.abandoned` — a **dotted
string that violates the snake_case taxonomy convention** and would be silently dropped if
copied into `track()`. The idea is adopted; the string is corrected and the doc line fixed
(§4 below).

**Intent classification — stated per event, because INTENT is a deny-list.**
`analytics_queries.py:65` computes `INTENT = (SERVER_FIRED | ALLOWED_CLIENT) − NON_INTENT`,
so any new name is intent **by default**. All four `espn_connect_*` events are INTENT today
(none appears in `NON_INTENT_EVENTS`, `:60-63`).
**Decision: all four `sleeper_connect_*` events are INTENT. `analytics_queries.py` gets NO
edit — this is a decision, not an omission.** Rationale: none is impression-class (there is
no passive path onto this modal — four deliberate tap entry points, no deep link, no
auto-navigate); `screen_viewed` for this route already fires and is already NON_INTENT
(`:61`), so mount volume is not what these add; and matching the twin keeps the two
platforms' connect funnels diffable in every series.

**`platform` — the NULL-`platform` trap, explicitly handled.** **No event here carries a
`platform` prop of either meaning.** Device platform is a **server-derived column** stamped
by `analytics_ingest.py` from the `X-Device*` headers that `events.ts:283-290` spreads into
every `POST /api/events` (the 2026-08-05 incident fix). Where a *league* platform prop is
legitimate, `platform` means Sleeper/ESPN/MFL/Fleaflicker (the `league_selected` precedent,
`analytics_taxonomy.py:185`). Neither applies: the league platform of a `sleeper_connect_*`
event is a tautology, and the device platform arrives as a column for free. A prop-stripping
test (§3) pins this by posting a bogus `platform` prop and asserting it is stripped; the
end-to-end check asserts the **column** reads `'ios'` and not NULL.

**No credential ever becomes a property.** No JWT, fragment, length, `sleeper_user_id`, or
`valid_2fa` claim. The token goes to `POST /api/sleeper/link` and nowhere else — the same
invariant the ESPN registry states for its cookies (`analytics_taxonomy.py:249-250`).

**Registration ordering — the load-bearing constraint.** `ALLOWED_CLIENT_EVENTS` is
default-deny and its failure mode is `_health_bump("dropped_unknown_type")` +
**HTTP 200**. There is no error signal on either side. **The taxonomy commit
(`analytics_taxonomy.py` + tracking-plan addendum + acceptance test) merges to `main` before
a single `track()` call exists in the client.** A missing `CLIENT_EVENT_PROPS` row raises
`ValueError` at import (`:327-332`) and the app will not boot, so both registries ship
together.

→ Follow-through: `docs/business/analytics/2026-07-17-tracking-plan-v2.md` gains an
**in-file addendum** ("Addendum 2026-08-11 — Sleeper Connect") directly after the ESPN
addendum at `:146-156` — the precedent for a connect-flow addendum, and this item mirrors
its twin. `docs/data-dictionary.md` is **n/a**: verified that no client event name appears
in it (neither `espn_connect_*` nor `draft_room_*`); its `event_type` rule applies to
server-fired types and this item adds none.

**(b) Existing events cover it** — partially, and the correction matters. `RootNav.tsx:352`
(boot) and `:376` (`onStateChange`) already fire `screen_viewed`, and `:366` fires
`screen_left` with a real `dwell_ms`, for **every** route including this modal
(`getCurrentRoute()` resolves to `SleeperConnect` when presented). So mount count and dwell
exist today; the audit's "zero analytics" is overstated. **What is missing is every in-flow
outcome** — logged in or not, linked or rejected, verified or inconclusive. Nothing in this
scope duplicates `screen_viewed`.

**(c) WAIVED** — not applicable; this feature *is* analytics.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** `user_events` already stores every one of these.
  No migration, no column, no index. `docs/data-dictionary.md` not in scope (see §1).
- **New/changed feature flags: none.** No flag is added and none is warranted — root
  `CLAUDE.md` reserves flags for user-visible behaviour, and there is none here. Emission
  rides the existing `analytics.client_events` (client gate, `events.ts:52`) +
  `analytics.ingest` (server gate) pair, both `true` in `config/features.json` today. That
  pair **is** the kill switch, so `config/features.json`, `backend/feature_flags.py`
  `FLAG_KEYS`, and `docs/config-reference.md` are all untouched.
  *Ship-the-knob:* the deploy-free rollback lever is `analytics.client_events → false`
  (stops emission) or `analytics.ingest → false` (stops storage). Note **G-017**: the two
  gates fail silently in tandem — verify at the destination, never at the 200.
- **New env vars / `model_config` keys: none.** `docs/config-reference.md` n/a.
- **API routes: none added, renamed, removed, or contract-changed.** `POST /api/events`
  accepts the four names purely by registry membership; its request/response shape is
  untouched. `POST /api/sleeper/link` is **read-only reference** — its error enum supplies
  the `reason` vocabulary and is not modified. `docs/api-reference.md` n/a.

## 3. Test scope (mobile test platform)

**Maestro delta: WAIVED, with reasoning** (root `CLAUDE.md` §Conventions permits a written
waiver; same waiver class P0-7 §7 takes).

- **Grep result stated first:** `grep -rn "sleeperconnect\|SleeperConnect\|sleeper-connect"
  mobile/.maestro/` returns **zero hits** — **no existing flow asserts this surface**, so
  there is no flow to update as part of the fix. (The twin has one:
  `mobile/.maestro/flows/espn-connect-capture.yaml`.) The only related hits are
  `capture/matches@espn.yaml:118,154`, which assert the *Send in Sleeper* button label —
  untouched by this item.
- **Waived because the change is not user-visible.** No rendered element, copy, layout,
  colour, timing, or navigation behaviour changes. Every insertion is a `track()` call
  (synchronous, `void`, swallows all errors — `events.ts:186-215`), a ref mutation, or a
  route param. Maestro asserts on rendered UI and cannot observe the analytics queue or a
  `POST /api/events` batch; a flow here would assert the *absence* of a regression, which
  the existing suite already does. **Verification moves to the backend + a simulator
  observation** (below).
- **Conditions that keep the waiver honest:** the existing smoke suite must pass
  **unchanged** — any flow diff invalidates the waiver — and **no `testID` is added or
  renamed**.
- **Optional new flow (NOT taken as written — plan §9 Checkpoint C):**
  `mobile/.maestro/flows/sleeper-connect-capture.yaml` mirroring the ESPN flow would drive
  `opened` + the `phase:'browsing'` abandon leg and close half of audit **A-31**. Cost: 4
  new `testID`s (`sleeper-connect.banner` `:109`, `sleeper-connect.webview` `:138`,
  `sleeper-connect.back-btn`, `settings.verify-account-row`) **and** a custom
  `headerLeft`/`HeaderBack` on the `SleeperConnect` route (`RootNav.tsx:702-711`, mirroring
  `EspnConnect` `:730-743`) — a header-chrome change that moves the sim gate to **tier 1**.
  **Recommendation: spin off as its own A-31 ticket.**
- **`testID`s added/renamed: none** as scoped ⇒ `mobile/scripts/testid-lint.sh` unaffected
  and expected clean. (If Checkpoint C is taken, all four IDs above are static string
  literals, so the grep-based check passes with no `testid-lint-allow.txt` entry; the
  screen's lone existing ID `sleeperconnect.done` `:157` is referenced by zero flows and
  could be renamed to `sleeper-connect.done` for free at that point — Checkpoint E.)
- **Capture delta: none** — no visual change, so no `mobile/scripts/screen-capture.sh` run.
  `mobile/scripts/screen-freshness.sh` is run per the tier-2 requirement; expected to flag
  nothing.
- **Smoke-suite impact:** the flows crossing `SettingsScreen`, `SendInSleeperButton` and the
  `RootNav` authed root are the affected subset. All must stay green **unchanged**.
- **Backend pytest, added/updated:**
  - `backend/tests/test_events_api.py` — **new** `test_sleeper_connect_events_accepted`
    (shape of `:335` / `:366`). Asserts `accepted == 4` **and `dropped == 0`** **and** an
    exact `set(by_type)` of the four names, plus prop round-trips
    (`reason == "token_user_mismatch"`, `phase == "linking"`, `verified is False`).
    `accepted` alone is insufficient — dropped events are *counted as accepted*
    (`analytics_ingest.py:379-383`).
  - Same file — **negative control** mirroring `:246` `test_unknown_type_dropped`: a
    misspelled `sleeper_connect_capturd` must be counted-and-dropped, proving the guard is
    armed rather than the test tautological.
  - Same file — **prop-stripping control**: post `sleeper_connect_opened` with a bogus
    `platform` prop; assert the event lands and the prop is stripped.
  - `backend/tests/test_analytics_p0.py` — extend `test_live_taxonomy_is_disjoint`'s
    membership assertion with the four names.
  - Import-time invariants need no test: a missing props row or a namespace collision makes
    **the whole suite fail to import** (`analytics_taxonomy.py:298-322`, `:327-332`).
- **Mobile static:** `cd mobile && npx tsc --noEmit`. The route-param union makes a mistyped
  `source` at any of the four call sites a **compile error** — the taxonomy can only police
  prop *keys*, not *values*, so the compiler is the enforcement for the vocabulary.
- **End-to-end (the only proof that survives a silent-drop wall):** on the simulator against
  a dev backend with both analytics gates on, drive all four legs (dismiss without logging
  in → `abandoned{phase:'browsing',attempts:0}`; log in as a *different* Sleeper account →
  `failed{reason:'token_user_mismatch'}` then `abandoned{phase:'error'}`; log in as the
  session's own account → `captured{verified:true}`; repeat once per entry point for
  `source` coverage). Flush (≥10 s or background), then
  `SELECT event_type, COUNT(*), platform FROM user_events WHERE event_type LIKE
  'sleeper_connect_%' GROUP BY 1,3;` — **assert `platform = 'ios'`, not NULL**; assert
  `GET /api/analytics/health` `dropped_unknown_type` / `dropped_unknown_prop` stay **flat**;
  and assert the partition `captured + abandoned == opened` per `session_id`, never both
  terminals in one mount.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (route added/renamed/removed/contract-changed) | **n/a** | No route touched. `POST /api/events` accepts the new names by registry membership alone — shape unchanged. `POST /api/sleeper/link` read-only. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **n/a** | No convention shifts. "Register before wiring" is P0-7's existing convention, obeyed here, not invented here. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No new module or path. `track()` → existing queue → existing `POST /api/events` → `user_events`. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No architectural shift; no new client, module, or major flow. |
| `docs/cross-client-invariants.md` (shared constants/enums/strings) | **YES** | §"Client analytics event contract" (`:268`) — add the four `sleeper_connect_*` names to "Allowed client event names" + addendum link, and note that `web/js/events.js` and `extension/background.js` fire none of them so the omission reads as deliberate. *(Observed, out of scope: that list is already stale — it is missing `espn_connect_*`, `draft_room_*`, `guide_*` and `screen_left`. Add the four ESPN names alongside if cheap; a full reconciliation is its own ticket.)* |
| `docs/glossary.md` (new domain term) | **n/a** | No new term. "connect", "capture", "verified session" are all in use. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **YES — `DECISIONS.md`** | Three decisions worth the record: (i) **no `sleeper_connect_otp_step`** — Sleeper's OTP is handled inside Sleeper's page (`sleeper-write-capture-runbook.md:128,134`) and this repo holds no verified selector, so a detector would ship a permanently-zero event indistinguishable from a real zero (the A-33 failure class); (ii) `captured` fires on **link success**, not token arrival, so `captured/opened` is a clean connect-success rate; (iii) all four events are **INTENT** and `analytics_queries.py` is deliberately untouched. **Not an ADR** — instrumentation inside an existing pipeline; D-021 already covers the connect-capture architecture. **ID:** next free — root `CLAUDE.md` says `D-011`, but **P0-7 also claims `D-011`; re-check at build time.** |
| `docs/integrations/sleeper.md` (external-API reference) | **YES** | `:408` — replace the illegal dotted `sleeper_connect.abandoned` with the shipped snake_case names and mark the funnel gap closed. Left as-is, a future builder copies a string that gets silently dropped. |
| `docs/business/analytics/2026-07-17-tracking-plan-v2.md` (taxonomy precondition) | **YES — mandatory, ships in the registration commit** | New "Addendum 2026-08-11 — Sleeper Connect (A-19 / P1-10)" after the ESPN addendum (`:146-156`), same shape: four-row event table, the no-credential-prop rule, and a "What is deliberately NOT here" paragraph (OTP step, `valid_2fa`, confirm/cancel beats, Keychain silent-replay, WebView load events, the `DELETE` disconnect leg). `analytics_taxonomy.py:9-10` and `cross-client-invariants.md:268` both make the addendum a **precondition** of registration. |
| `docs/data-dictionary.md` | **n/a** | No schema change. Verified: no client event name appears in this file (neither `espn_connect_*` nor `draft_room_*`); its `event_type` rule covers server-fired types, and this item adds none. |
| `docs/config-reference.md` | **n/a** | No env var, flag, or `model_config` key. |
| `docs/design/` | **n/a** as scoped | No rendered change. Becomes in-scope only under Checkpoint C's `HeaderBack` — which reuses the `EspnConnect` header pattern verbatim and adds no new visual token. |
| `docs/runbook.md` | **Conditional** | Only if the end-to-end check surprises. G-017 already covers the paired-gate trap. |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` | **YES, on ship** | Root `CLAUDE.md` §Session memory. TEST_LEDGER carries the sim tier **and** the row-landed evidence. |
| `living-memory/GOTCHAS.md` · `MISTAKES.md` · `OPEN_QUESTIONS.md` | **Conditional** | Only if verification surprises. |

## 5. Ship gate declaration

- **Simulator-gate tier: 2** — `docs/runbook.md:97`, *"Mobile logic touched, no UI change →
  feature's flow + affected smoke subset **+ run `mobile/scripts/screen-freshness.sh`;
  re-capture only the screens it flags**"* (expected: none). The feature has no flow of its
  own under the §3 waiver, so the run is the affected smoke subset: the flows crossing
  `SettingsScreen`, `SendInSleeperButton`, and the `RootNav` authed root.
- **Evidence:** `TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after the
  run, per root `CLAUDE.md` gate 4. Local `githooks/pre-push` enforces
  (`git config core.hooksPath githooks`). `FTF_SKIP_SIM_GATE=1` is **not** available —
  express lane was not declared.
- **Operator deviation from the matrix:** none proposed. **Two paths would raise the tier
  and are operator decisions, not agent calls:**
  1. **Checkpoint C** (optional Maestro flow) adds a custom `headerLeft` to the
     `SleeperConnect` route → navigation/screen chrome change → **tier 1** (full 11-flow
     smoke + `screen-capture.sh` for the touched screen).
  2. An argument exists for tier 1 regardless, since `RootNav.tsx` is navigation. It is
     answered by the fact that no navigation *behaviour* changes — `:437` gains one argument
     and `:58` gains a param type; the route, presentation, and header are untouched. If the
     operator prefers tier 1 anyway, that is a recordable deviation, not a correction.
- **Cross-item ship coordination (plan §8.1):** **P1-5 also registers new client events** in
  the same two frozensets (`ALLOWED_CLIENT_EVENTS` `:98`, `CLIENT_EVENT_PROPS` `:254`). Two
  competing single-item registration commits conflict textually on adjacent lines and, worse,
  invite a merge that keeps one name set and silently drops the other — reproducing the exact
  counted-and-dropped-behind-200 failure this item exists to prevent. **Recommended: one
  shared "P1 taxonomy registration" commit carrying both items' names, merged before either
  item's client wiring.** If shipped separately, P1-10's registration goes first (Effort S,
  fully specced) and P1-5 rebases; each item's exact-`set(by_type)` assertion then fails
  loudly on a bad merge.
- **Rebase precondition:** P0 merges to `main` first. **P0-6 rewrites
  `SendInSleeperButton.tsx`'s render path and P0-7 inserts `track()` into its `onPress`/
  `catch`** — re-locate `goConnect` (currently `:112-115`) before editing. P0-5 edits
  `RootNav.tsx:398`, a different region from this item's `:58` and `:437`.
- **Open operator checkpoints blocking build (plan §9):** **A** the fourth event
  (`sleeper_connect_failed`, recommended, vs the literal `sleeper_connect_otp_step`) ·
  **B** `captured` on link success (recommended) vs token arrival · **C** the optional
  Maestro flow (recommended: out, spin off under A-31) · **D** shared taxonomy commit with
  P1-5 (recommended: yes) · **E** rename `sleeperconnect.done` (recommended: only with C).
