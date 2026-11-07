# Preference-save admission and trade handoff

The accepted tap owns its exact selection, search ID, account/token/league/format authority and screen attempt. A pending DNA save no longer lets the builder send a request against inputs that are about to change. The builder pushes immediately; the destination waits for input writes before binding the data revision and sending one request. The existing loading/error/retry presentation remains in use.

DNA's logical transition spans all coalesced saves, including the interval between the API settlement for A and the send for queued B. A failed save releases the barrier and reports a failure. Its monotonic failure time is compared with the original tap, so a failure during navigation is not forgotten. A later explicit retry can use the actual saved preferences. Waiting and HTTP share the existing endpoint deadline, reduced by elapsed time since the original tap. Neither the first-card telemetry clock nor the search ID restarts.

The mutation variables own dispatch authority even when asynchronous `onMutate` throws before React Query supplies a context. Account, token, league, format, unmount, epoch or newer-attempt replacement discards the obsolete work. The HTTP client rechecks authority after asynchronous token lookup and before each fetch, including session-readiness retries. A still-current attempt whose input revision changes after admission gets an actionable error; old cards are never adopted. Billing and verification refusals retain precedence after the immutable authority check. An accepted dispatch without ready session authority gets a readiness error rather than being silently dropped or rebound to a later account.

Retry retains the accepted model selection even when admission failed before the POST. The one-shot canvas selection is consumed synchronously at dispatch; a delayed mutation cannot clear a later edit. Fair-package requests similarly detach their arrays before waiting. No automatic generation retry was added, and the existing onboarding retry, preview gates, full validation, pagination and server behavior remain intact.

## Verification boundary

`mobile/tests/check-trade-input-readiness.js` executes the production readiness store, deadline implementation, handoff identity, model mutation callbacks, model dispatch, fair loader and DNA coalescing loop with synthetic dependencies. It covers pending and failed saves, continuation races, successful delivery, exact requested terms, request counts, expired deadlines, listener cleanup, undefined mutation context, billing precedence and context replacement. Existing source-pinning tests were updated to recognize asynchronous admission while retaining their original epoch, key and telemetry assertions.

These controls establish the client lifecycle behavior. They do not establish a 200 ms device result or prove that this defect caused either recorded build 178 failure. The observed account's cold backend publications took roughly 59–66 seconds; that is separate work.

## TestFlight follow-up

After integration, exercise an immediate Find a Trade tap after changing DNA preferences, including a second edit while the first save is pending. Verify one search ID from tap through delivery, correct league/selection, visible failure and working retry if the save fails, and no obsolete card after an account/league/format switch. Count the original tap duration, all failures and missing cards. No new device run is claimed here.
