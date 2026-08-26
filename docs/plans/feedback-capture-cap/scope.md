# Feature Scope — Feedback note cap raise + silent-loss fix

<!-- Copied from docs/templates/feature-scope.md. Its §Maestro delta and
     §Simulator-gate tier are dead sections under D-056 and are omitted. -->

**Date:** 2026-08-22
**Entry point:** operator incident — a long in-app feedback report was typed, submitted, and lost with no error shown anywhere
**Builder:** three parallel agents on `claude/new-user-feedback-d4c47d` — orchestrator (`backend/server.py`), mobile agent (`mobile/src/**`), guard+docs agent (`mobile/tests/`, `docs/`)
**Operator sign-off on waivers:** required — see §6. **One** waiver (§1, the `feedback_submit_failed` analytics event), plus the express-lane ruling recorded in §6.

---

## 0. What broke, and why nothing caught it

`POST /api/feedback` rejected a note over 2000 characters with `400 {"error":"text_too_long","limit":2000}`. Four independent gaps turned that into silent data loss:

1. `FeedbackSheet.tsx` had no character counter and no cap awareness — the user could not see the note was already unsendable.
2. Save was enabled at any length.
3. `onSave` cleared the draft unconditionally after calling `add()`, so the note left the screen whether or not it was delivered.
4. `useFeedback.add()` synced in a detached `void (async …)` IIFE and returned the pre-sync item, so no caller *could* have checked the outcome.

The local AsyncStorage copy survived with `synced:false`, but a 400 is permanent: `retrySync()` re-POSTed it on every foreground forever and it was never going to land. No typecheck, no backend test, and no runtime smoke pass sees any of this — the app looks like it works.

**The change:** raise the cap 2000 → 8000, surface the count and the cap in the compose sheet, gate Save on the length, and make `add()` report delivery so the draft survives a failure.

## 1. Analytics scope

**(b) Existing events cover it.** No new event is being added. Named coverage:

| Question | Answered by | Notes |
|---|---|---|
| Is the server rejecting feedback notes, and why? | `api_request` (`backend/api_observability.py`, flag `obs.api_events` — **currently ON**) | `route="/api/feedback"`, `status=400`, `error_code="text_too_long"`. **Failures are written unsampled** (`record_inbound`: `if not ok: _write_event(...)` before the 1-in-N success sampler), and `/api/feedback` is not in `EXCLUDED_ROUTES`. This is a direct, already-live counter of exactly the event that caused the incident. |
| How many notes are getting through? | `feedback_submitted` (`SERVER_FIRED_EVENTS`) | Server-fired on the success path only, signed-in users only, never carrying note text (tracking plan v2 §S4). |
| Is a specific user's note stuck undelivered? | the FAB badge (`utils/feedbackBadge.ts`, #184) + `last_sync_error` on the local item | Product surface, not analytics, but it is the user-visible half of the same signal. |

**A `feedback_submit_failed` client event was considered and deliberately NOT added.** It would need three coordinated registrations — `ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`, and `analytics_queries.NON_INTENT_EVENTS` — in the same commit as its emitter, and `analytics.client_events` is ON so it *would* collect real data. It is still not worth it here:

- The server-rejection half, which is the half that caused the incident, is already captured by `api_request` at full fidelity and with a closed `error_code` enum. A client event would duplicate it less reliably (client events are forgeable and batch-dropped; `api_request` is not).
- The only residual blind spot is a note whose POST never reaches the server (offline / transport failure). That case is **not a loss**: the item stays durable in AsyncStorage, `retrySync()` drains it on the next foreground, and the user now sees "Saved on this device, but not sent yet."
- An event fired on the failure path would also be the one most likely to be lost — the client that cannot POST feedback generally cannot POST an analytics batch either.

**If the operator wants it anyway**, the spec is: `feedback_submit_failed`, client-fired from `FeedbackSheet.onSave`, props `{reason: "too_long"|"network"|"server", severity, screen, length_bucket}` — closed enums only, **never the note text or its length in the clear** (§S4). It must be classified NON_INTENT (a failed submit is not a user decision worth minting a user-day from) and registered in the same commit as the emitter.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `app_feedback.text` is an existing SQLAlchemy `Text` column and is **unbounded in storage** in both SQLite and Postgres — the cap is application-level validation in the route, never a column constraint. `docs/data-dictionary.md` was corrected to say so (it previously implied a `1..2000` storage bound).
- **New/changed feature flags:** none. Deliberate: a flag here would mean shipping a build that can still lose a note. The rollback lever is the constant itself — `FEEDBACK_TEXT_MAX` in `backend/server.py` is one line and one redeploy, no client release needed to *lower* it.
- **New env vars / `model_config` keys:** none. The cap was considered as a `model_config` key (deploy-free adjustment) and rejected: the client must mirror the value to render an honest counter, and a server-side knob the client cannot see reintroduces exactly the drift this change exists to prevent.

**Ship-the-knob note.** The risk being accepted is a 4x larger anonymous write. `POST /api/feedback` accepts unauthenticated bodies, so the cap is the only bound on payload size; 8000 characters is still small next to the route's other traffic, and the route is `@_gate_unverified_write`-gated. If abuse appears, lower `FEEDBACK_TEXT_MAX` server-side and redeploy — old clients then show a counter that is too generous until the next TestFlight build, which is the *safe* direction of drift (Save stays enabled, the server rejects, and the sheet now keeps the draft and says so).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-feedback-capture.js` (+ `npm run test:feedback-capture`). Dependency-free — `fs` plus source-shape parsing, no `typescript`, no jest. Pins six things:
  1. `FEEDBACK_TEXT_MAX` is exported from `mobile/src/api/feedback.ts`.
  2. **The client constant equals the server cap** — resolved through `backend/server.py`'s own named constant — *and* equals the number the 400 reports. This is the assertion that matters most: the two copies ship on different cadences (Render vs TestFlight) and nothing else in the repo notices when they drift.
  3. A character counter is **rendered** from that constant (a `<Text>` whose children carry both the live length and the cap, or locals derived from them) and the sheet contains no hardcoded copy of the number.
  4. The Save button's `disabled` expression is gated on both empty and over-cap.
  5. Every `setText('')` in `onSave` sits inside a conditional, and the result of `add()` is actually consulted — the draft clear must be unreachable except on a successful sync.
  6. `add()` awaits the sync **in its own body** (not in a detached IIFE) and does not return the pre-sync `item`.
- [x] **Red-proof:** the guard was run against the pristine defect tree (commit `9e1a8be`, the branch point before any of this landed) — **6 of 6 assertions red**, each naming the real defect — and then against 20 individually sabotaged variants covering *every* named failure branch. Each fired the branch it was aimed at, and each was restored and re-verified green. Full log handed to the orchestrator to write into `living-memory/TEST_LEDGER.md` — `living-memory/` is written once per session by one agent so three concurrent sessions do not race the same file. The cycles ran against an isolated file replica rather than the live worktree on purpose: the three parallel changes were **uncommitted while the proof was running**, so a `git checkout --` restore would have destroyed a peer agent's work instead of restoring it. Harness: `git show 9e1a8be:<path>` for the defect baseline, working-tree copies for the fixed baseline, byte-compare after every restore.
- [x] **Unit tests:** `backend/tests/test_feedback_text_cap.py` — 3 tests, passing. Pins the boundary from **both** sides, which is what stops the cap being quietly removed *or* quietly lowered: a note of exactly `FEEDBACK_TEXT_MAX` is accepted (201), one character past it is refused with the full `text_too_long` body, and a 2001-character note — the length class the old cap ate — now lands **and is stored whole**. That last assertion is the sharp one: a cap that truncated instead of refusing would also return 201, and would be the same data loss wearing a success code. Every assertion reads `server.FEEDBACK_TEXT_MAX` rather than a literal, except the deliberate `> 2000` floor check that fails if anyone reverts the raise.
- [x] **Code-walk proof** (the mobile behaviour, which nothing mechanical can execute post-D-056). Line numbers are as of 2026-08-22 on `claude/new-user-feedback-d4c47d`; two peer agents were still editing these files, so trust the quoted code over the number:
  - `mobile/src/components/FeedbackSheet.tsx:92-93` — `noteLength = text.trim().length`, `overLimit = noteLength > FEEDBACK_TEXT_MAX`. Gating on the **trimmed** length is what makes the client agree with `backend/server.py:8130` (`text_body = text_raw.strip()` then `len(text_body) > FEEDBACK_TEXT_MAX`); gating on the raw length would reject notes the server accepts.
  - `FeedbackSheet.tsx:236-242` — the counter `<Text testID="feedback.char-count">` renders `{groupDigits(noteLength)} / {MAX_LABEL}`, where `MAX_LABEL` is derived from the imported constant. No `maxLength` on the input, deliberately: silent truncation is the same data loss in a nicer coat.
  - `FeedbackSheet.tsx:269` — `disabled={!noteLength || overLimit}` on the Save button; `FeedbackSheet.tsx:130` repeats the check as an early return inside `onSave`.
  - `FeedbackSheet.tsx:135-151` — `const saved = await add({...})`; `if (!saved.synced) { setSaveFailed(true); return; }`. The only `setText('')` sits **after** that guard, so the draft survives every failure path. The sheet stays open and shows `SAVE_FAILED_MESSAGE`.
  - `mobile/src/state/useFeedback.ts:170-176` — the detached `void (async () => …)()` is gone; `const patch = await _syncOne(item)` runs inline and the function returns `{ ...item, ...patch }`, so `synced` and `server_id` are the post-round-trip truth. `_syncOne` still swallows its own errors, so `add()` continues to never reject.
  - `backend/server.py:8078-8086, 8130-8133` — `FEEDBACK_TEXT_MAX = 8000` module constant; both the comparison and the 400's `limit` field read it, so the route can no longer disagree with itself.
- [x] **Manual TestFlight checklist** — runtime proof genuinely matters here, because the *entire* defect was a UI state machine that no automated layer in this repo can execute:
  1. Open any screen → tap the feedback FAB. **Expect:** counter reads `0 / 8,000` under the note box.
  2. Type a short note. **Expect:** counter increments; Save enabled.
  3. Paste ~9,000 characters (any long text). **Expect:** counter turns red and reads e.g. `9,013 / 8,000`; the note box border turns red; Save is **disabled**; the message names how many characters to trim and says "Your text is still here."
  4. Delete text until under 8,000. **Expect:** counter returns to normal colour, Save re-enables — with the note text still intact, never truncated.
  5. Save a ~7,900-character note while online. **Expect:** sheet closes, draft cleared; the note appears in the feedback inbox as synced; it arrives in `/api/feedback/admin` **with its full text, not clipped at 2000**.
  6. Turn on Airplane Mode. Type a note, tap Save. **Expect:** the sheet **stays open**, the draft is **still in the box**, and the notice reads "Saved on this device, but not sent yet…". Nothing is lost.
  7. Turn Airplane Mode off, background and foreground the app. **Expect:** `retrySync()` drains the note; the FAB badge count drops; the note shows as synced in the inbox.
  8. Regression on the draft guard (`ux.sheet_guard` is ON): type a note, tap the backdrop to dismiss, reopen the FAB. **Expect:** the draft is restored, as before this change.
- **`testID`s added:** `feedback.char-count`, `feedback.note-error`, `feedback.save-error` (added by the mobile agent). `mobile/scripts/testid-lint.sh` passes — it is a flow↔source cross-check and no `.maestro` flow references these.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | § In-app feedback — body now `1..8000 chars`; the `400` bullet now spells the `text_too_long` payload shape (`{"error":"text_too_long","limit":8000}`), says it is measured on the trimmed body, names the client mirror and the guard that pins them, and dates the raise. |
| `living-memory/LLD.md` | n/a | No convention shifted. The route, its validation order, its response shapes, and the mirrored-constant pattern (`FEEDBACK_CLOSED_STATUSES` is the existing precedent) are all unchanged in kind — only a number moved. |
| `docs/architecture.md` | n/a | No module added, removed, or re-wired. `add()` changing from detached to awaited is a call-ordering change inside one existing store, not a data-flow change: the same two writes (AsyncStorage, then POST) happen in the same order. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated** | New § "Feedback note length cap (2026-08-22)" — the value, both locations, which is authority and which is mirror, what each direction of drift costs, and the guard that enforces agreement. This is the doc's exact remit: a threshold that must stay in sync across backend and mobile. |
| `docs/glossary.md` | n/a | No new domain term. "Feedback note", "synced", and "draft" are all already in use. |
| ADR or `DECISIONS.md` entry | **pending — owed by this session** | The non-obvious choices are (1) mirroring the cap in the client rather than serving it from `/api/config`, and (2) no `maxLength` on the input — refusing to truncate, and holding the draft instead. Both need a `DECISIONS.md` entry (next ID = max + 1, grep first); neither rises to an ADR (no architecture changed). Not written by the guard+docs agent — `living-memory/` is written once per session by the orchestrator to avoid three agents racing the same file. |

Also corrected, outside the trigger table: `docs/data-dictionary.md` (`app_feedback.text` said `1..2000 chars`, implying a storage bound that does not exist — now states the column is unbounded `TEXT` and the cap is route validation), and `docs/plans/feedback-backend-sync/plan.md` (the June contract doc that both `backend/server.py` and `mobile/src/api/feedback.ts` cite as "locked"; it is `abandoned` in the plans README, so its three `2000` figures were left in place as the historical record and annotated, under a dated banner pointing at `api-reference.md` as current truth).

## 5. Ship gate declaration

- **CI green:** required before merge — `backend-tests` (pytest), `mobile-typecheck` (`tsc --noEmit` **plus** the `tests/check-*.js` glob, which now includes `check-feedback-capture.js`), and `maestro-testid-lint`. Locally: all 71 guards in `mobile/tests/` pass, including the new one; `mobile/node_modules` was installed with `npm ci` (no symlink — that is a recorded project failure that produces phantom `tsc` errors).
- **Evidence recorded:** **pending** — `living-memory/TEST_LEDGER.md` needs the red-proof log (6/6 red on the pristine defect tree, 20/20 sabotage branches fired and restored) plus the CI result on the pushed sha. Content is ready; the write is the orchestrator's (single-writer rule for `living-memory/` while three agents are live).
- **TestFlight verification:** the §3 checklist is **outstanding** — it must be run by the operator on the build that carries this change. Steps 3, 4 and 6 are the ones that would have caught the original incident; step 5 is the one that proves the raise actually took effect end to end.
- **Express lane declared by the operator?** **No — and specifically not.** The operator confirmed the cap raise *out of* the express lane. Raising `FEEDBACK_TEXT_MAX` changes the accepted request body of `POST /api/feedback`, which is an **API-contract change** and therefore on the root `CLAUDE.md` bright-line list ("schema, API contracts, feature-flag surfaces, or analytics events is not a quick fix"). Full gates apply: this scope block, the evidence delta above, the docs table in §4, and the pre-ship gate in this section.

## 6. Waivers requiring operator sign-off

| # | Waived | Reason | Risk if the operator disagrees |
|---|---|---|---|
| 1 | New `feedback_submit_failed` analytics event | `api_request` already captures every server rejection unsampled with a closed `error_code`; the residual gap (offline POST) is not a loss and self-heals via `retrySync()` | Low — spec is written out in §1 and ready to build |

**One live cross-change risk, flagged rather than waived:** the cap raise is only correct if **both** halves ship. A Render deploy carrying `FEEDBACK_TEXT_MAX = 8000` with an old TestFlight build in the field is harmless (the old client caps itself lower). The reverse — a client build allowing 8000 against a server still at 2000 — reproduces the original defect for notes between 2001 and 8000 characters, except that the sheet now *keeps the draft and tells the user*, which is the point of the fix. `check-feedback-capture.js` makes the mismatched state impossible to merge, but it cannot police deploy ordering: **deploy the backend first.**
