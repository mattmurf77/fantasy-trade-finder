# REQ — INIT-12: API Client Resilience

- **Initiative / Wave / Scope:** INIT-12 · Wave 1 (timeout + warm dedup) / Wave 2 (GET retry) · [M]
- **Source observations:** OBS-API-01 (warm dedup), OBS-API-04 (timeout), OBS-API-05 (GET retry)
- **Peak RICE-P:** 4.0 (OBS-API-04)

## Problem statement

The mobile API wrapper (`client.ts:149–178`) issues a single `fetch` with no
timeout and no retry; a hung or cold-starting Render dyno can therefore pin the
user on an infinite spinner for 60–120 s with no error and no recovery path.
Separately, `warmPlayerCache()` is called at both app boot (`App.tsx:51`) and
inside `initLeagueSession` (`auth.ts:117`), adding a redundant round-trip and
cold-dyno worker contention on the most-contended path.

## User stories

- As a **dynasty manager**, I want a clear, actionable error message when the
  server is slow to respond, so that I know to retry rather than wait
  indefinitely on a blank spinner.
- As a **dynasty manager**, I want transient cold-start failures on GET
  requests to recover automatically, so that a single 5xx on league pick does
  not require a full manual re-tap.
- As a **dynasty manager**, I want the app to warm the player database exactly
  once at launch, so that the initial league-pick flow is not slowed by a
  redundant round-trip.
- As a **developer**, I want all timeout and retry logic centralized in the one
  `apiRequest` wrapper, so that future API functions are protected by default
  without per-call boilerplate.

---

## Wave 1 — Timeout + warm dedup (target: quick win, ≤1 day)

### Functional requirements (Wave 1)

- **FR-1** — `apiRequest` in `mobile/src/api/client.ts` must create an internal
  `AbortController` and set a default deadline of **15 s** for all requests not
  explicitly configured otherwise.
- **FR-2** — The endpoints `POST /api/session/init` and `POST
  /api/trades/generate` must receive a **30 s** deadline (not the 15 s default),
  reflecting their documented 5–10 s cost on the free tier
  (`auth.ts:98–99`).
- **FR-3** — The internal `AbortController.signal` must be **composed** with any
  caller-supplied `opts.signal` so that TanStack Query cancellation and the
  timeout can both abort the request; whichever fires first wins.
- **FR-4** — On timeout, `apiRequest` must throw a typed `ApiError` (or a
  subclass thereof) with a user-readable `message` of approximately
  `"Server is waking up — retry."` and a distinguishable `code` or `isTimeout`
  flag, so that UI layers can surface an actionable message rather than a generic
  network error.
- **FR-5** — A module-level `warmedOnce` boolean flag must be added to
  `mobile/src/api/sleeper.ts`. `warmPlayerCache()` must set `warmedOnce = true`
  on its first successful response and skip the network call on all subsequent
  calls within the same app launch.
- **FR-6** — The `initLeagueSession` warm call (`auth.ts:117`) must be gated:
  if `warmedOnce` is `true`, skip the call; if `false`, proceed as today and let
  the result set `warmedOnce`.
- **FR-7** — If a `session_init` call fails with a server message indicating the
  player database is not cached (the original rationale for the `auth.ts:117`
  warm), the `warmedOnce` flag must be reset to `false` so the next league pick
  attempts a fresh warm before `session_init`.

### Acceptance criteria (Wave 1)

- [ ] **AC-1** — Given the dyno is wedged (simulated with a request to a
  blackholed address or a test server that stalls), when a standard GET is made
  via `apiRequest`, then the call throws an `ApiError` with `isTimeout === true`
  (or equivalent) within 15 s ± 1 s.
- [ ] **AC-2** — Given `session_init` is called with no caller-supplied signal
  and the server stalls, when 30 s elapses, then `apiRequest` aborts and throws a
  typed timeout error.
- [ ] **AC-3** — Given a TanStack Query that is cancelled by navigation (its
  internal signal fires) before the 15 s deadline, when the signal fires, then
  the request is cancelled immediately — the 15 s timer does not prevent
  cancellation.
- [ ] **AC-4** — Given a warm launch (app already ran this session), when the
  user picks a league and `initLeagueSession` executes, then exactly **one** call
  to `GET /api/sleeper/players/warm` is observable in the network log (the boot
  warm), not two.
- [ ] **AC-5** — Given a cold launch (first session after app restart), when the
  boot fan-out and the subsequent league pick both execute, then exactly **one**
  `GET /api/sleeper/players/warm` call is made unless the `session_init` response
  triggers a flag reset.
- [ ] **AC-6** — Given the `warmedOnce` flag is `true` and a `session_init`
  fails with a "player database not cached" message, when `initLeagueSession` is
  retried, then a new `warmPlayerCache()` call is issued.

---

## Wave 2 — GET-only retry (target: Wave 2, ~0.5 day)

### Functional requirements (Wave 2)

- **FR-8** — `apiRequest` must support an optional `retry` parameter (default:
  enabled for GET, disabled for all other methods). When enabled, on HTTP
  502/503/504 or a network-level error (not a timeout), make up to **2 retry
  attempts** before surfacing an error.
- **FR-9** — Retry delays must use exponential backoff: first retry after
  **400 ms**, second after **1 200 ms**, each with ±20% jitter to avoid
  synchronized storms.
- **FR-10** — Retry must be **strictly limited to idempotent GETs**. The
  following must never be retried: `POST /api/session/init`, any swipe or save
  mutation (`/api/rankings/*` POST, `/api/tiers/*` POST, `/api/trades/swipe`),
  and any endpoint listed in the "no retry" allowlist in `client.ts`.
- **FR-11** — A retry attempt must reuse the same composed `AbortController`
  signal; if the timeout fires or the caller signal fires during a retry, the
  retry sequence is abandoned immediately.
- **FR-12** — After all retry attempts are exhausted, `apiRequest` must throw
  the same typed `ApiError` it would throw on a non-retried failure, so callers
  require no changes.

### Acceptance criteria (Wave 2)

- [ ] **AC-7** — Given a test server returns 503 on the first GET and 200 on the
  second, when `apiRequest` is called for that GET, then the caller receives the
  200 response transparently with no error surfaced to the UI.
- [ ] **AC-8** — Given a test server returns 503 on all attempts, when
  `apiRequest` exhausts 3 total attempts (1 + 2 retries), then an `ApiError` is
  thrown with a delay of approximately 400 ms + 1 200 ms (plus jitter) elapsed
  since the first attempt.
- [ ] **AC-9** — Given `POST /api/session/init` returns 503, when `apiRequest`
  handles the response, then **no retry is attempted** and the error is thrown
  immediately.
- [ ] **AC-10** — Given a swipe mutation POST returns 502, when `apiRequest`
  handles the response, then **no retry is attempted** and the error is thrown
  immediately (no double-mutation risk).
- [ ] **AC-11** — Given the timeout fires at 15 s on the first attempt of a
  retried GET, when the timer fires, then the retry sequence is abandoned (no
  additional attempt is made after the timeout).

---

## Related components

- `mobile/src/api/client.ts:136–140` — header block
- `mobile/src/api/client.ts:149–178` — `apiRequest` / single `fetch`, no
  timeout or retry
- `mobile/src/api/auth.ts:25` — `signIn` (un-signalled caller)
- `mobile/src/api/auth.ts:117` — `warmPlayerCache()` inside `initLeagueSession`
  (duplicate warm)
- `mobile/src/api/auth.ts:151` — `sessionInit` call (un-signalled, slow leg)
- `mobile/src/api/auth.ts:201,230` — `resolveSmartStart`, `startDemoSession`
  (un-signalled callers)
- `mobile/src/api/sleeper.ts:47` — `warmPlayerCache` / `GET
  /api/sleeper/players/warm`
- `mobile/App.tsx:51` — boot-time `warmPlayerCache()` call

## Prerequisite components / dependencies

- Wave 1 (timeout + warm dedup) has no hard prerequisites; it is self-contained
  in `client.ts` and `sleeper.ts`.
- Wave 2 (GET retry) must land **after** Wave 1, as retry deadlines must compose
  correctly with the timeout signal introduced in FR-3.
- INIT-02 (baked player cache) reduces the likelihood of a "player database not
  cached" `session_init` failure, but is not a prerequisite for this initiative.

## Non-functional requirements & invariants

- **Retry idempotency invariant:** retry must be strictly GET-only. Any endpoint
  that writes data — swipes, saves, `session_init`, trade generation — must never
  be retried automatically. A violation risks duplicate mutations or a
  partially-applied `session_init` being re-sent. This is a hard requirement, not
  a preference.
- **Timeout generosity on slow endpoints:** `session_init` and `trades/generate`
  are documented at 5–10 s on the free tier (`auth.ts:98–99`); their timeout must
  be ≥30 s to avoid aborting a legitimately slow-but-progressing cold start.
  Verify on a cold-dyno league pick that the full `session_init` completes within
  the 30 s deadline.
- **Signal composition:** composing the internal and caller signals must use the
  standard `AbortSignal.any([internalSignal, opts.signal])` (or equivalent)
  pattern; never suppress the caller signal or the timeout signal independently.
- **No ELO / tier-band invariant:** client networking only; no ranking math or
  tier config is touched.
- **Rollback:** removing the timeout `AbortController` and `warmedOnce` flag
  fully restores the current single-fetch behavior. The Wave 2 retry logic is
  independently removable.

## Out of scope

- Adding `Accept-Encoding: gzip` to `client.ts` headers. Measured as a no-op for
  mobile (RN auto-negotiates gzip); covered by INIT-15 documentation only.
- Single-flight / de-duplication of concurrent identical GETs (Option B of
  OBS-API-05). Deferred.
- Migrating `initLeagueSession` / `getLeagues` onto TanStack Query mutations
  (Option C of OBS-API-05). Larger refactor; deferred.
- Server-side changes to `session/init` response time (backend concern: INIT-08).
