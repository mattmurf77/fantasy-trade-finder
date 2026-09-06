# G420 — Win Now session recovery and request deadlines

Date: 2026-09-06

Phase: **1 — planner proposal; runtime implementation not started**

Feedback: #420 and #421, iOS 1.17.0, reported 2026-09-05 09:54–09:55 UTC

Audited source: `4026ebc81eaae50b345b42421641125c5b8d413e`

Branch: `codex/feedback-420-421-win-now-20260906`

## Outcome sought

Opening season projections must recover a valid user's lost server-side league initialization, finish a legitimately slow projection read within a deliberate finite budget, and explain actual failures without inventing a hosting condition. Recovery must never restore the wrong account or league. No change to forecast mathematics, trade policy, privacy, authorization, or supported-source rules is proposed.

This is a planner handoff for a separate author/review phase, not the final scope/PRD or permission to push, deploy, build, or mutate production. The feedback skill's phase-1 planning guidance and repository coding/design instructions were read. D-056 applies: no Maestro, simulator, or capture work.

## Evidence and diagnosis

### Production sequence: both symptoms are substantiated

The orchestrator supplied the following [sanitized read-only production reconstruction](production-evidence.md). The planner independently checked the matching source paths, but did not operate the tester's device or read response bodies.

| UTC on 2026-09-05 | Sanitized evidence | What it establishes |
|---|---|---|
| 09:48:52 | Successful session initialization before the release rollover | The account had initialized successfully before the later failure. |
| 09:51:59 | Backend `4026ebc8` became live after `c28ec6d8` | A process rollover intervened. A paid service can restart for a deploy. |
| 09:52 onward; report-associated attempts 09:53:34–09:54:17 | Season-projections requests repeatedly returned `409 session_not_initialized`; server processing about 0 ms. Client failures took about 1.95–2.41 seconds, `timeout:false` | This is the initialized-session guard plus the client's short retries, not a slow forecast calculation or HTTP 503. |
| 09:54:42 | A fresh `/api/session/init` completed HTTP 200 in 303 ms | The missing league initialization was subsequently repaired. |
| 09:54:58 | Season-projections completed server-side HTTP 200 after 15,186 ms; the client reported status 0 after 15,034 ms, `timeout:true` | The legitimate HTTP operation exceeded the mobile 15-second deadline. HTTP 200 does **not** establish that forecasts were available; an unavailable result also uses 200. |
| Same interval | A `/api/trades/liked` client request also timed out around 15 seconds before its server-side HTTP 200 | Consistent with contention behind the synchronous single worker; not proof of the exact expensive sub-operation. |

The experimental trade-policy change occurred later that day, around 16:01 UTC; it cannot explain these earlier reports. There is no evidence here of free-tier sleep or a cold start. The bounded outbound sample in the relevant interval contains successful provider calls, but is system-level and sampled, not an end-to-end request trace; summing those durations cannot explain the full projection latency. Raw reports, account/league/session identifiers, tokens and response bodies are deliberately absent from this document.

### #420: confirmed recovery gap, not a request for weaker server guards

1. Both entry points navigate to the same unconditional root `WinNow` route without an independently captured league: `mobile/src/screens/LeagueSummaryScreen.tsx:1518`, `mobile/src/screens/TradesScreen.tsx:6473`, `mobile/src/navigation/RootNav.tsx:142` and `:787`.
2. The screen reads the global current user/league and keys its content by both, which is useful existing isolation (`mobile/src/screens/WinNowScreen.tsx:52`). Its baseline effect depends only on league, season flag, navigation focus and manual refresh (`:90`). It neither waits for league-session reconciliation nor observes its completion. Refresh only repeats the GET (`:189`).
3. A cached user, league and token become available before network reconciliation (`mobile/src/state/useSession.ts:313`; `mobile/App.tsx:105`). `hasToken` explicitly means a device token exists, **not** that the backend still has this league initialized (`useSession.ts:128`). Boot/foreground reconciliation is detached and throttled (`mobile/App.tsx:115`, `:210`).
4. `revalidateSession` silently returns while another run is active, silently returns within 60 seconds, and swallows failures. Its internal boolean is not an awaitable join or reactive readiness signal (`mobile/src/state/useSession.ts:56`, `:352`). Same-user/same-league completion therefore does not restart a failed Win Now effect. More importantly, a still-open app can have apparently valid local state after a server restart with **no new init running at all**.
5. Durable-token restoration explicitly reconstructs a league-uninitialized Sleeper session after restart; `/api/session/init` must reattach league context using the existing token (`backend/server.py:2360`). The actual Win Now installation passes `_require_initialized_session` (`:30633`), which correctly returns the observed typed 409 before route business logic if league/player/trade-service context is missing (`:2535`, `:2269`).
6. The shared client retries only `409` with exact `error:'session_not_initialized'`, twice, with nominal 400/1,200 ms backoff. It never initializes the session (`mobile/src/api/client.ts:252`, `:562`). Waiting about 1.6 seconds cannot repair absent context when nothing is rebuilding it.

**Do not blame the current league picker:** it already awaits `submitSessionInit` before `setLeague` and Main (`mobile/src/screens/LeaguePickerScreen.tsx:438`). Older comments in the shared client, session store and App still describe optimistic navigation or minting a new token; those comments are not current behavior. `sessionInit` reuses the verified token and checks that it remains current before/after the protected request (`mobile/src/api/auth.ts:242`).

### #421: confirmed false explanation and too-short endpoint deadline

`getSeasonProjections` is an ordinary GET with no special request allowance (`mobile/src/api/winNow.ts:4`). The shared client defaults to 15 seconds; only two named POSTs receive 30 seconds (`mobile/src/api/client.ts:227`). The deadline surrounds fetch/retries/backoff (`:432`). When its timer, rather than the caller's cancellation, aborts the request, the client constructs `ApiError(0, null, TIMEOUT_MESSAGE, true)` (`:479`). `TIMEOUT_MESSAGE` is literally the waking-server assertion (`:272`).

The screen correctly prefers a structured backend message/reason when one exists (`mobile/src/screens/WinNowScreen.tsx:47`). For this client-generated timeout there is no body, so it displays the misleading shared message. A 503 is separately handled as a retryable HTTP gateway status and is **not**, on its own, evidence for this copy.

The endpoint is synchronous (`backend/win_now_api.py:76`). Its cold source path reads league/rosters/users, remaining matchup weeks, then weekly projections serially (`backend/win_now_service.py:90`, `:150`, `:183`; `backend/season_forecasts.py:212`). Each injected Sleeper request may take up to 15 seconds (`backend/server.py:575`). Successful source responses have short process-local caches; failures and expired data are not substituted (`win_now_service.py:70`). Baseline simulation and optional editable-asset context also run in the HTTP request (`win_now_service.py:261`; `win_now_api.py:85`). Production declares one synchronous worker (`render.yaml:16`). These are concrete sources of aggregate latency/contended requests, but the supplied evidence does not attribute the observed 15,186 ms to one particular stage.

## Minimal proposed contracts

The author should turn R-1–R-7 into the group's mini-PRD and filled feature scope, preserving these boundaries. A new helper name or exact signature below is not prescribed; the ownership and behavior are.

### R-1 — One bounded, context-owned recovery of a typed missing session

- Add an awaitable **state-owned** league-session reconciliation/recovery operation. Win Now calls this owner, not a duplicate direct `/api/session/init` implementation.
- An already-running initialization for the **same current context** is joined, not treated as success and not duplicated. A normal readiness wait must finish successfully before the baseline read proceeds; boot's splash remains local-only/nonblocking.
- If a projection read returns exact `409 session_not_initialized`, allow **one forced same-context repair and one replay of that projection read** for the user attempt, even if local state believed initialization was complete or normal background revalidation is throttled. Merely adding a readiness effect dependency cannot recover a post-deploy stale token context.
- Do not recursively repeat repairs. Existing low-level retries are finite; document the composed maximum requests/time in the LLD. After a failed repair or a second missing-context refusal, show a recoverable failure and end loading. A fresh explicit Refresh begins a new bounded attempt.
- Do not automatically replay search/evaluation/decision writes as part of this baseline fix. The shared client's existing narrowly safe pre-handler 409 behavior is distinct from permission to retry arbitrary writes.

### R-2 — Context and switch safety are part of recovery

- Bind work to current account, real league, session-token identity and a lifecycle/request generation. A token alone is insufficient: switching leagues can legitimately reuse it.
- Join only matching work. Coordinate same-token init writers so delayed repair for league A cannot be sent/published after the user has selected league B. An abort/ignored promise alone does not undo a server-side session mutation already sent; the new league's initialization must remain the last applicable writer.
- Before issuing the repaired GET and before publishing readiness, seeds or screen results, verify the initiating context is still current. Switching, sign-out, replacement sign-in, blur/unmount, and flag removal must invalidate affected screen work. A canceled screen may detach from a shared init without canceling another legitimate consumer's recovery.
- Audit all existing init callers at the shared seam, including picker, switch, background revalidation and league connect. `switchLeague` currently has a switch-only lock, not a lock shared with background revalidation (`mobile/src/state/useSession.ts:442`); do not introduce a third competing writer.
- Preserve token rotation/401 safeguards and verification-before-init. Never mint a fallback token, relax membership, use a query-string league to override the authenticated server context, or seed caches for a superseded user. No league/account-only sentinel should initiate a real-league projections request.

### R-3 — Projection-specific finite time allowance

- Proposed immediate correction: give **exact GET `/api/league/season-projections`**, with its query string accounted for, a 30-second total transport allowance. This reuses the existing slow-request budget and accommodates the measured 15.186-second HTTP completion with headroom. Match normalized pathname + method, not an arbitrary substring.
- Keep the default 15-second allowance for unrelated routes and keep existing slow POST rules. No unbounded timeout, whole-app timeout increase, or automatic retry storm. Caller abort must still win over deadline classification. The finite budget includes the request's retry/backoff attempts, not a fresh 30 seconds per gateway retry.
- A 30-second allowance is a bounded correction for the observed completion, **not a production latency SLO** or proof that every supported league finishes in that time. It also does not solve the single-worker contention observed on unrelated requests; see the focused spike below. Do not silently claim it does.

### R-4 — Honest error semantics using existing presentation

| Condition | Required outcome |
|---|---|
| Initialization actually in progress / forced repair | Existing loading/refresh area indicates loading or reconnecting league data. Keep navigation usable; do not show standings or enable search from absent/stale data. |
| Successful baseline HTTP 200 `status:'available'` | Render current-context standings and existing provenance; enable controls only under existing capability/freshness gates. |
| HTTP 200 `status:'unavailable'` | Render the backend message or reason, not empty standings, a fabricated zero or transport-error copy. Refresh does not bypass source/rule restrictions. |
| Client deadline | Neutral copy, proposed: **“This request took too long. Please try again.”** Retain `status:0`, `isTimeout:true`. No assertion about hosting plan or sleep. |
| Offline/native network failure | A connection-oriented or existing accurate network failure plus manual retry; `timeout:false` unless the client's own deadline actually fired. Do not call it a source refusal. |
| Backend 502/503/504 | Existing bounded safe-GET retry, then backend message when supplied or neutral service-unavailable fallback. Never equate all 503s with cold starts or expired login. |
| Genuine 401 / verification or membership 403 / unrelated 409 | Existing auth/verification/conflict path; no league-repair loop. A stale 401 must not clear a newer token. |
| User/navigation cancellation | No failure alert, no timeout telemetry, no late results. |

No new panels, receipts, badges or card redesign. Reuse Chalkline text/buttons and current testIDs (`win-now.refresh`, `win-now.unavailable`, `win-now.stale`); add a stable loading/error identifier only if required for the executable wiring test. Update the shared timeout comment as well as its string. Other screen-local “waking” strings are a separate copy audit, not a reason to modify unrelated trade flow in this group.

### R-5 — Preserve source, cache and authorization truth

Win Now actor construction requires exact session league and distinct account/league-owner identities (`backend/win_now_api.py:24`). Expected source/rule failures return HTTP 200 `{status:'unavailable',reason,message}` (`:48`); global initialized-session failures remain 409. Keep those contracts distinct. Source-success cache TTLs, immutable forecast timestamps, cutoff/expiry, live-week refusal, league membership and capability checks must survive any timing optimization. No stale dynasty/outlook cache fallback and no use of receipt HTTP status alone as forecast availability.

### R-6 — Preserve telemetry semantics

Use existing `api_request_failed` coverage: normalized route, method, status, trusted duration, background-span flag and timeout flag (`mobile/src/api/client.ts:349`). Preserve caller-abort exclusion and background-duration omission. Server inbound/outbound events already supply timing evidence. The author must enumerate this existing coverage in scope, not silently waive analytics. Do not log raw responses, asset selections, private IDs or tokens. Any genuinely new event/property requires taxonomy/tracking-plan review before implementation.

### R-7 — Keep the feature and release scope narrow

No schema or flag change, no policy calibration changes, no pricing/model/ranking changes, no server worker-count change, no web contract change, no production reset or real-user test mutation. The current initialized-session guard is retained. Preserve current Win Now request epochs, 90-second search polling cap, stop-on-expiry, server result order, independent season decisions and title gating. The app's local-first launch must remain intact.

## Ownership proposed for phase 2

| Owner | Files / boundary | Notes |
|---|---|---|
| G420 mobile/session owner | `mobile/src/state/useSession.ts`; a narrowly scoped state helper if warranted; `mobile/src/api/auth.ts` and existing init call sites only where required for one shared lifecycle | Own reconciliation, in-flight joining, supersession and token/league-safe commit. Preserve picker initialization-before-navigation. No upward store import added to the API client. |
| G420 mobile transport/screen owner | `mobile/src/api/client.ts`, `mobile/src/api/winNow.ts`, `mobile/src/screens/WinNowScreen.tsx` | Exact-route allowance, neutral timeout, bounded repair/read orchestration and existing loading/error surface. Coordinate `client.ts` exclusively with the batch owner; no competing #419 edit. |
| G420 test owner | New executable `mobile/tests/check-win-now-recovery.js` and/or focused helper tests; augment `check-win-now.js` as needed | Execute actual exported/transpiled implementation with deferred requests and fake timers. AST guards supplement, not replace, behavior. |
| Backend validation owner | `backend/tests/test_win_now_api.py`, persistent/verified-session regression files as necessary | Real installed initialized-session guard plus isolated fixtures; existing API harness currently injects a ready session and does not cover this restoration failure. Runtime backend edits require the focused spike's evidence and author/reviewer agreement. |
| Orchestrator | Scope/PRD/reconciliation, integration docs/ledger/index, evidence archive and final review | This planner writes only this file. Separate author/review phase must settle blocking ambiguities before code. No push/deploy authorization in this batch. |

### Optional focused latency spike; explicit remaining contention limitation

The orchestrator accepts context recovery, truthful copy and the exact-GET 30-second allowance as this group's core fix. The supplied sampled outbound spans do not attribute the full delay. If an additional bounded investigation is useful, run a hermetic cold-cache/warm-cache benchmark using synthetic league/forecast data and injected source delays, with separate timings/call counts for source collection, simulation and optional `build_context`. No live provider loops or production writes. Compare the installed synchronous route with concurrent lightweight requests in an isolated local test server only if claiming a contention fix.

If an obviously duplicated/context operation is demonstrated, propose the smallest shared-source/cache-safe correction for review. Otherwise record synchronous contention as a remaining limitation without delaying the bounded core fix for an architectural redesign. If later evidence requires asynchronous baseline preparation, it needs a separate contract including old-client behavior, state/job ownership and cancellation. **Do not invent a 202/polling response in a GET whose shipped clients expect the current body.** The projection timeout correction is not a worker-throughput fix. No server concurrency/deployment configuration change is implied.

## RED regressions required before implementation is credited

Every behavioral case must execute the implementation seam, fail against the original defect or a named sabotage, then pass with the fix. Use fake time/deferred transports and isolated test databases; no sleeps, network, real account or repository DB. Keep failure output and sabotage names for the orchestrator's ledger.

| Test | Given / action | Mechanical pass criterion | Requirement |
|---|---|---|---|
| T1 — redeploy after prior success | Client believes same token/league ready; server session is restored bare; projection GET receives typed 409 | One bounded forced init using the existing context, then one logical read replay succeeds without requiring a new app launch or a second tap; no arbitrary repeated GET loop. Original code must fail. | R-1 |
| T2 — slow in-flight initialization | Boot/foreground init for the same context remains pending beyond the old ~1.6-second retry window; open Win Now | Actual request orchestration joins it, does not report ready early or duplicate init; successful completion triggers the baseline for that same user/league. | R-1 |
| T3 — repair failure and manual recovery | Init fails offline or by typed refusal; later the connection is restored and Refresh is tapped | Loading ends, honest failure remains, Refresh starts one fresh bounded attempt; failed or successful throttle bookkeeping cannot permanently suppress it. A second typed 409 cannot recurse forever. | R-1, R-4 |
| T4 — same-token league race | Defer A repair before POST and separately after POST; select B and complete requests in both orders | B is the final applicable server context; no late A readiness/cache/baseline commit; no replay of A's GET after supersession. Also cover switch failure without relabeling A data as B. Token-only comparison sabotage must fail. | R-2 |
| T5 — user/token/screen supersession | Sign out or replace sign-in during recovery; separately blur/unmount/kill flag | No late token/store/cache/result resurrection; no protected replay with new token and old league; new user remains intact. Caller cancellation produces neither an alert nor failure telemetry. | R-2, R-6 |
| T6 — actual installed backend guard | Restore a synthetic persisted verified session lacking league context, then initialize through an isolated route fixture | Before init: exact 409 without forecast/source work. After init: normal available or typed unavailable response. Foreign league/verification denial still blocks. Avoid the existing fake-ready-session API harness as sole proof. | R-1, R-5 |
| T7 — measured slow GET and deadline boundary | Execute actual `apiRequest`/Win Now API path with a result at ~15.2 seconds, then beyond 30 seconds | First completes and its body is interpreted; latter fails once with neutral typed timeout. Unrelated GET remains 15 seconds; slow POSTs remain 30; query strings and lookalike paths test exact matching. Reset-per-retry sabotage must fail. | R-3 |
| T8 — refusal vs transport matrix | Feed actual client/screen: 200 unavailable, typed init 409, unrelated 409, 401, verification 403, 503 with message, offline reject, deadline and caller abort | Each follows R-4; only the exact init refusal invokes recovery; server reason/message survives; no 503/caller abort falsely becomes “waking up.” Exercise the shipped error parser, not a test reimplementation. | R-4, R-6 |
| T9 — cache/freshness and feature preservation | Warm/expired source cache, unsupported live/source input, old baseline, disabled season/title flags | No expired success fallback, no zeros for missing forecasts, no numbers/search before available current baseline; existing `check-win-now.js` and backend Win Now/forecast/verified-session suites remain green. | R-5, R-7 |

The current mobile `check-win-now.js` executes formatter helpers and web async races, but its mobile lifecycle coverage is structural. Add executable mobile orchestration/component-or-hook coverage so a missing recovery call, dropped `await`, or stale completion actually makes the test red. Preserve `check-session-seed.js`'s behavior contract if coordinator refactoring changes its structural shape; do not delete a guard merely to get green.

Phase-2 validation includes targeted pytest, all mobile `check-*.js`, TypeScript `--noEmit`, testID lint, `git diff --check`, and integrated CI as owned by the orchestrator. This documentation-only planner phase has not run app tests or physical-device QA.

## Manual TestFlight checklist — operator, not executed

Use an authorized tester account and controlled staging conditions for induced failures/restarts; never restart production or alter real membership just to test. Record binary/backend SHA, entry route, timing and visible result, with no private identifiers in public evidence.

1. From a restored signed-in app, open League → season projections immediately while league initialization is deliberately slow. The existing loading area remains responsive, then shows standings **or the actual source/rule refusal** without another tap. Back still works. Repeat from Acquire → Win Now.
2. Leave the app signed in, roll the authorized staging backend so its persisted token restores without league context, and reopen/refresh Win Now without signing out. One automatic repair resolves the loading refusal; no repeated “try again” loop. Verify request ordering in sanitized logs.
3. During that repair, go Back and switch leagues. Open Win Now for the new league. Complete the old delayed work; no old-league standings, success toast, restored selection or wrong-league request may appear. Repeat with sign-out followed by another authorized test login.
4. Delay a valid projection response to about 16 seconds. It remains loading past 15 seconds and renders the eventual available/unavailable body. Then exceed the finite deadline: see neutral timeout text and an enabled Refresh, not “server waking up.” Back/foreground transitions must not show a late timeout from an abandoned screen.
5. In staging, return a provider/source-unavailable or live-week refusal. Its explanation appears, no zero standings are manufactured, and search stays unavailable. A 503/offline failure instead shows a transport/service explanation; reconnect and Refresh recover without clearing the session unnecessarily.
6. While a cold projection request is running, visit another ordinary read surface. Record any delay/timeouts as the **separate contention measurement**, not a passed performance claim merely because Win Now's budget is longer. Do not label #421's performance aspect complete if the agreed author scope promised to resolve this and it still fails.
7. After a successful baseline, verify existing objective/budget/protection controls, expiry warning, search cancellation, edit/evaluate, title capability and Back behavior. Check Dynamic Type/VoiceOver for the existing loading/error/Refresh area; no duplicated FAB or new panel.

## Author/reviewer decisions still needed

- Confirm the shared init coordination seam and exact finite end-to-end recovery budget; prove same-token league supersession before accepting any retry helper.
- Finalize the orchestrator-accepted 30-second route-specific correction in the PRD; explicitly record that synchronous contention remains a measured limitation unless an optional bounded, reviewed correction actually resolves it.
- Fill the feature scope/analytics/doc-trigger table and phase reconciliation log. No waiver is inferred from this narrow planner assignment. Re-diff fresh main before runtime edits and preserve newer security/session and Win Now behavior.
