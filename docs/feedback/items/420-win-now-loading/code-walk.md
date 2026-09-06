# G420 code walk and manual TestFlight checklist

Date: 2026-09-06

Source: `2de3e1d95dbcb98d491bc0dee2811c5380ec0bec`. References below are repository-relative paths and lines at that runtime commit. [Executed evidence](build-evidence.md) distinguishes automated checks from physical verification.

## Current-context recovery

`mobile/src/screens/WinNowScreen.tsx:55` retains the account+league keyed content subtree. Its baseline effect at `:90` captures the focused lifecycle and AbortController; `:97` consumes a deliberate Refresh marker exactly once, `:99` calls the state owner, and `:104` detaches on blur/unmount/flag dependency change. `:192` leaves the existing Refresh action enabled after terminal loading settles. Search/evaluate/decision operations retain their separate epochs and polling budget.

`mobile/src/state/useSession.ts:728` starts the immutable 90-second attempt before token preparation. `:733` refuses null/demo/sentinel/wrong active-league requests; `:734` captures account, real league, token revision and generation. `:744` subscribes this consumer to superseding intent, canceling its HTTP request even while the old league is still displayed. `:746` awaits readiness/join. `:749` sends the exact captured token and checks current context before every transport dispatch; `:751` checks before returning data.

Only the typed `ApiError`/409/body-error conjunction at `:756` enters forced repair. `:758` awaits the same shared owner with `force:true`; `:759` performs one logical replay. A replay refusal escapes; there is no recursive repair. The enclosing identity-only error fence at `:765` turns obsolete terminal failures into silent cancellation while allowing a current deadline to remain a truthful timeout. Its error argument preserves a current 401's own authorized token-clear transition, described below. The effect's existing active flag governs UI publication.

## Shared init ownership and ordering

`mobile/src/state/leagueSession.ts:45` captures intent before awaiting token lookup. Generation advances at `:38`; capture compares the authenticated account and token revision at `:41`, never substitutes a co-owned team's owner. Automatic entry into another desired selection is refused. An account-only real imported league is permitted; `no_league` is not.

`ensure` at `:72` first rejects unresolved uncertainty or consumes a later explicit authorization into an **uninitialized** state. `:80` joins a matching pending promise before considering a successful readiness hint. New work captures one deadline at `:84`; `:97` awaits the token lane predecessor, then rechecks the identity. Obsolete preparation is canceled at `:89`; an already dispatched POST is deliberately allowed to settle independently of the departing caller. `:115` awaits the actual initializer and `:116`–`:119` permit seed/readiness only after current successful completion.

The submit wrapper at `:105` distinguishes authoritative client denial from timeout/network/server ambiguity. `:91` invalidates readiness and records a monotonic uncertainty event. `:99` refuses a selection queued before its predecessor became uncertain. The latch belongs to the state owner's token lane and survives screen lifecycle, same-token generation changes, force calls and foreground throttle expiry. The operation does not claim the server stopped after a local timeout.

`mobile/src/state/useSession.ts:694` wires the actual auth initializer into the one owner, with the sole guarded seed publication. Foreground at `:358` awaits this owner and throttles only a successfully ready generation. Switch at `:444` retains its existing UI lock, registers selection before asynchronous work, awaits shared initialization, guards league commit and invalidates related queries; its request ID owns busy cleanup. `setUser` at `:386` and sign-out at `:663` invalidate generation synchronously before asynchronous persistence/cleanup.

Connect at `:592` retains the existing Sleeper-only URL workflow and imported-row merge. `:600` captures the deadline and `:601` reserves authorization at the initiating gesture, before the target is known. URL/list waits consume that deadline. The resolved target uses the **same** ticket and deadline at `:650`, so an old gesture cannot clear a newly latched uncertainty. A new Connect gesture after the latch can authorize a new attempt.

## Auth choke point and platform compatibility

`mobile/src/api/auth.ts:258` accepts a required lifecycle control. It awaits existing verification replay, rechecks context/token, and sends the captured token at `:268` with a final pre-dispatch fence and dispatch notification. Verification mirrors at `:311` and `:336` recheck the current generation before affecting the store. The one recognized player-cache denial can repeat init once at `:517` or `:611`; both repeats retain the same lifecycle/deadline. No new general POST retry was introduced.

`initLeagueSession` at `:421` routes ESPN/MFL/Fleaflicker through their existing imported-snapshot builders before the account-only Sleeper guard at `:449`. The guard therefore prevents an `acct_*` provider lookup without blocking valid imported leagues. Synthetic tests execute all three actual builder modules and assert the account identity remains the submitted actor.

## Picker, resync and honest failure publication

`mobile/src/screens/LeaguePickerScreen.tsx:436` labels automatic pinning automatic and actual picks selection. Immediately after synchronous intent capture, `:439` refreshes the identity guard, so a token-preparation failure can still release the picker. After capture, `:441` uses an identity-only guard for error publication; success uses the stronger deadline guard. Shared init/seed at `:443` precedes guarded `setLeague` at `:445` and navigation at `:447`. A current timeout reaches error text and `setSelectingId(null)` at `:462`; a superseded result stays silent.

`mobile/src/screens/LeagueScreen.tsx:144` keeps the explicit ESPN import action. It captures shared context before import at `:156`, guards afterward at `:161`, and forces only the existing init leg at `:163`. Success/refetch require the same context. Error and busy cleanup at `:170` and `:182` use identity-only guards, including the exact current-401 receipt: expiration shows the error and clears the spinner, while stale completions cannot affect a later context. Already dispatched native storage operations have the limitation documented in build evidence; neither handler claims a cancelable disk transaction.

## Transport deadlines, callbacks and reporting

`mobile/src/api/client.ts:298` bounds the entire logical operation, including preparation and body reads. It detaches on a caller signal; expiration is typed with the exact neutral copy at `:287`. Checks before starting resumed work, before fetch at `:535` and after body read at `:590` prevent late dispatch/publication when JS resumes after a deadline. `:332` classifies only normalized exact `GET /api/league/season-projections` as 30 seconds; ordinary GET/other rules retain their existing 15/30-second allowances. `:456` captures the earlier of caller and route deadlines once, outside retries.

Token mutations advance revision synchronously at `:99`/`:104`. A 401 clears only its still-current sent token; `:612` records the deletion revision and `:620` prevents a delayed expiration callback after replacement sign-in. `:614` records an internal from/to revision receipt only while that clear is still current. `isCurrentSessionExpiry` at `:212` accepts only that exact one-step revision transition; state guards still enforce account and generation. Thus a current 401 retains its original server message, while an old 401 after replacement remains silent. This receipt contains no token and changes no wire body or analytics property. Verification denial at `:633` checks current token/revision/caller/deadline plus the applicable context fence **before** calling the store callback. The existing failure wrapper reports once per logical request; caller aborts, including superseded projection consumers, remain excluded. No new event/property or identifier-bearing coordination log exists.

## Installed backend guard

`backend/tests/test_verified_sessions.py:538` persists a synthetic verified session, removes its in-memory copy, and exercises the installed restoration and real route guard. `:562` proves exact 409 before initialization and zero forecast calls. Real authorized init then permits the actual typed-unavailable response at `:572`; `:576` preserves foreign-league refusal. Only provider/forecast data and the existing fixture's heavy/background seams are isolated. Existing verified/persistent-session and Win Now suites cover the other refusal contracts; no backend runtime changed.

## Manual TestFlight checklist — unexecuted

Record actual binary/build and backend SHA with sanitized outcomes. Use controlled authorized staging for induced delays/restarts; no real trades or production learning writes.

1. Open League → season projections during a slow init, then Acquire → Win Now. Confirm responsive loading/Back and eventual available data or the actual source refusal without another tap.
2. Restore a signed-in token across a staging process rollover. Open/Refresh Win Now; verify one bounded missing-context repair/replay, without a repeated manual-retry loop.
3. During repair, select another league and repeat with sign-out/replacement login. Old results, verification errors and success messages must not appear in the new context. Induce an uncertain init, refocus/foreground without a tap, and verify zero new init/projection requests. A later explicit Refresh/selection permits a bounded retry.
4. Delay a projection response to approximately 16 seconds, then beyond its 30-second allowance. Separately stall a composed preparation/repair chain near 90 seconds. Check the neutral timeout, released loading, enabled Refresh and absence of a late alert after leaving.
5. Exercise source/live-week unavailable, verification denial, service failure and offline/recovered network. Preserve the truthful message; never show zero standings/search on unavailable data. Check the existing error/Refresh controls with Dynamic Type and VoiceOver.
6. Observe ordinary reads during a cold forecast calculation. Record remaining delay honestly; the deadline correction does not prove worker contention is solved.
7. With a valid baseline, verify objective/budget/protection controls, title gating, source expiry, search cancellation, edit/evaluate and Back. Confirm account-only imported-league selection still reaches the existing platform experience and sentinel-only accounts make no projection request.

Build upload, Apple processing, tester availability and these observed runtime outcomes are separate release facts; none is claimed by this builder.
