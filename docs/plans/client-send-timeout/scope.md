# Feature Scope — ESPN/MFL client send timeout (no double send)

**Date:** 2026-10-28
**Entry point:** direct ask. head-eng GO 2026-10-28 for the 11-06 iOS binary (in release-lead's queue by 11-03); the client half of C10 (server half: PR #513, `docs/plans/c10-send-failures/` on that branch).
**Builder:** platforms-eng worker, branch `fix/espn-mfl-client-send-timeout`
**Operator sign-off on waivers:** not needed. The only skipped rows are the template's retired Maestro/simulator ones (D-056).

---

## The problem

The app gives every request 15 s (`DEFAULT_TIMEOUT_MS`, `mobile/src/api/client.ts`). An ESPN or MFL send can take longer on the server: live pre-flight reads, then a provider write with its own 15 s timeout. So the app could give up while the write was still running and show "Something went wrong sending to ESPN. Please try again." A user who tapped Send again could send the same trade twice. The team-overhaul send, which sends a whole batch inside one request, could show "Send failed — nothing went out" when some offers had gone out.

## What changes

1. **One long timeout for the three sends, derived from the server.** `mobile/src/api/sendOutcome.ts` holds `SERVER_SEND_WORST_CASE_S = 76` and `PLATFORM_SEND_TIMEOUT_MS = 91_000`. The comment cites each server term (file:line at `bef9f5db`):

   | Term | Server constant | s |
   |---|---|---|
   | Crosswalk refresh (24 h cache stale) | `fetch_crosswalk(timeout=15)`, `backend/espn_service.py:755`, via `get_crosswalk` :774 | 15 |
   | MFL host resolution (row has no `platform_host`) | `resolve_host(timeout=15)`, `backend/mfl_service.py:129` | 15 |
   | MFL I-2 rosters read | `fetch_rosters(timeout=15)`, `backend/mfl_service.py:441` | 15 |
   | MFL I-2 picks read | `fetch_future_draft_picks(timeout=15)`, `backend/mfl_service.py:401` | 15 |
   | MFL write spacing | `_REQUEST_SPACING_SECONDS = 1.0`, `backend/mfl_write.py:63` | 1 |
   | MFL write | `_HTTP_TIMEOUT = 15`, `backend/mfl_write.py:58` | 15 |
   | **MFL total** (`_mfl_propose_core`, `server.py:37659`) | | **76** |
   | ESPN pre-flight league read | `fetch_league(timeout=15)`, `backend/espn_service.py:139` | 15 |
   | ESPN write | `_HTTP_TIMEOUT = 15`, `backend/espn_write.py:80` | 15 |
   | **ESPN total** (`_espn_propose_core`, `server.py:38259`): crosswalk + read + write | | **45** |

   One constant covers both platforms, so it is MFL's 76 s, plus a 15 s margin (one `DEFAULT_TIMEOUT_MS`, for the mobile round trip and the server's database work) = **91 s**. urllib's timeout is per socket operation, not per request, so a provider that stalls at two stages can run longer. The app then shows "couldn't confirm", which is the safe answer.

   The overhaul send (`POST /api/overhauls/{id}/send`) is **one request for N sends**: `overhaul_send_route` (`backend/overhaul_api.py:950`) loops over the batch, calling the propose core once per offer (:1029). So `overhaulSendTimeoutMs(n) = (n × 76 + 15) s`, with n = the prepare's `counts.offers`. Sleeper's core, which an overhaul on a Sleeper league reaches, is at most 70 s (rosters 15 + traded_picks 15 + league meta 10 + drafts 15 + write 15), so the 76 s per offer covers it.

   Every other call keeps its timeout. The `api/client.ts` change is additive: an optional `timeoutMs` in `RequestOptions`, used in place of `timeoutForRequest(...)` at the two places that read it.
2. **An unknown outcome says "couldn't confirm", never "try again".** `isSendOutcomeUnknown(err)` is true for our timeout, no HTTP answer (status 0, or fetch's network error), the server's `espn_outcome_unknown` / `mfl_outcome_unknown` (#513), the global 500 `internal_error` (an unhandled exception can be raised after the provider took the write), and a 5xx with no error code (a gateway page). Every structured error keeps its own handling. `SendInEspnButton` / `SendInMflButton` check it first: title "Check before resending", message "Couldn’t confirm whether this trade reached ESPN. Check ESPN before sending it again." (MFL likewise), buttons OK and Open ESPN / Open MFL. The copy lives in `mobile/src/utils/sendOutcomeCopy.ts` and is a **placeholder pending marketing** (copy routes head-eng → head-bizops → marketing-lead).
3. **Overhaul: re-read the attempts, no resend.** `OverhaulSummaryScreen` sends the offer count with the batch. On an unknown outcome it invalidates the overhaul queries, `replace`s to `OverhaulPlan` (which re-reads `GET /api/overhauls/{id}`), and alerts "Couldn’t confirm whether these offers reached {platform}. Each offer’s status is on your plan. Check {platform} before sending any of them again." The old "Send failed — nothing went out" toast is no longer reachable for these cases. See the code walk below for why this is safe.
4. **No automatic retry of a POST.** Unchanged: `canRetry` in `api/client.ts` is GET-only. It is now pinned. The one POST replay that exists, the 409 `session_not_initialized` backoff, is safe because that guard raises before the route runs; it is pinned as the only one.

Out of scope: Sleeper's own single send (`propose`), the server (PR #513), and the button staying tappable after an unknown outcome. The message tells the user to check first; a dedicated "check ESPN" state is a product call.

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it.** `api_request_failed` (client, `api/client.ts` `_reportApiFailure`) already fires once per failed call with `route` (`/api/trades/propose-espn`, `/api/trades/propose-mfl`, `/api/overhauls/:id/send`), `method`, `status` and `timeout`. A client timeout is `status: 0, timeout: true`; a dropped connection is `status: 0, timeout: false`; a server unknown is `status: 502`. That answers "how often does a send time out on the client, per platform". Server side, `trade_sent` fires only on a confirmed send, and `overhaul_batch_reconciled` carries `unknown_count`. One caveat: `api_request_failed` drops `ms` above `MAX_PLAUSIBLE_MS` (60 s, `api/client.ts:413`), so a send that times out at 91 s reports without `ms`; `timeout: true` is still there. No ESPN/MFL client send events exist (the button comments say they are unregistered), and none is added here.
- [ ] (c) Waived: n/a.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. Sends stay behind `espn.send`, `trade.send_in_mfl` and `overhaul.enabled` (OFF for launch, 2026-10-27).
- New env vars / `model_config` keys: none. Rollback is reverting the client change; there is no server knob.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-send-timeout.js` (`npm run test:send-timeout`), 19 checks. It executes the real `api/client.ts`, `sendOutcome.ts`, `sendInEspn.ts`, `sendInMfl.ts`, `overhaul.ts` and `sendOutcomeCopy.ts` under a fake clock with a scripted `fetch`:
  - A: the constant equals the server sum, every term parsed from the backend files; each propose core makes exactly the counted provider calls on their default timeouts (a new provider call goes red); the comment cites every term.
  - B: each send is still waiting at 15 s and times out at its long timeout; link-status GETs, prepare-send, refresh and a plain POST still time out at 15 s.
  - C: a timeout or a network drop on each send is outcome-unknown; 18 server answers classified through the real client; the copy.
  - D: both buttons and the overhaul summary branch on it first, with no resend in that branch.
  - E: no POST is retried on 502/503/504/network drop (a GET control is); `session_not_initialized` is the only POST replay.
- [x] **Unit tests:** none in the backend (no backend change). The server half is pinned by `backend/tests/test_c10_send_failures.py` on #513.
- [x] **Code-walk proof** (file:line on this branch):
  1. `SendInEspnButton.tsx:141` `doPropose` → `proposeTradeToEspn` (`sendInEspn.ts:83`) → `api.post(..., {timeoutMs: PLATFORM_SEND_TIMEOUT_MS})` → `apiRequest` sets `deadlineAt = now + opts.timeoutMs` (`client.ts:482`) and the inner abort timer to the same value (`client.ts:534`). No `timeoutMs` = `timeoutForRequest(...)`, as before.
  2. At 91 s with no answer, `runWithDeadline` rejects `ApiError(0, null, TIMEOUT_MESSAGE, true)`. `canRetry` is false for POST (`client.ts:550`), so nothing is resent.
  3. The catch (`SendInEspnButton.tsx:167`) checks `isSendOutcomeUnknown(err)` first (`sendOutcome.ts:86`: `isTimeout` → true) and alerts the check-before-resending copy. The generic "Please try again" `else` is never reached for it. MFL is the same at `SendInMflButton.tsx:126`.
  4. Overhaul: `OverhaulSummaryScreen.tsx:181` passes `pv.counts.offers`; `overhaul.ts:434` sets `timeoutMs: overhaulSendTimeoutMs(offerCount)`. On an unknown outcome (`:188`) the screen invalidates `['overhaul', overhaulId]` and replaces to `OverhaulPlan` (`:194`), whose `useQuery` re-reads `GET /api/overhauls/{id}` (`OverhaulPlanScreen.tsx:118`).
  5. Why that is safe: the server stores every attempt before its first provider call (`overhaul_api.py:1026`) and drops the prepare token (:1027). If the request reached the server, the plan shows each attempt as Queued / Sending / Sent, awaiting reply / Send status unknown (`overhaul.ts:459-462`). Those are live states (`overhaul_service.py:66`): the package shows "N offers out" instead of "Send next tier" (`OverhaulPlanScreen.tsx:101` `nextTier` skips every attempted offer). A `sending` row a dead batch left behind becomes `outcome_unknown` on Refresh after 300 s (`overhaul_service.py:80`, the zombie sweep at `overhaul_api.py:1098`). If the request never reached the server, there are no attempts and "Send next tier" re-prepares a fresh batch, which is correct because nothing went out. A same-key replay was already deduplicated server-side (`batch_by_key`, `overhaul_api.py:960`); the client just no longer invites one.
- [x] **Manual TestFlight checklist** (the only runtime evidence; real leagues only, and every send in them needs the operator's go at action time, since each is a real write to a platform):
  1. iPhone on the 11-06 build, signed in, with an MFL test league linked and MFL sign-in stored. In Settings → Developer → Network Link Conditioner, enable "Very Bad Network" (or a custom profile with 100% downlink loss).
  2. Open a trade card for that MFL league, tap **Send in MFL**, confirm. Expected: "Sending…" holds for about 1.5 minutes and does not fail at about 15 s.
  3. Expected after that: an alert titled **Check before resending** with "Couldn’t confirm whether this trade reached MFL. Check MFL before sending it again." and buttons **OK** / **Open MFL**. No "Please try again", no "Couldn’t send".
  4. Turn the conditioner off. Tap Open MFL (or check MFL on the web) → the league shows **at most one** pending offer for that trade.
  5. Repeat 1–4 on an ESPN test league with Send in ESPN (`espn.send` is on). Expected: the ESPN copy and Open ESPN; ESPN shows at most one pending offer.
  6. Airplane mode right after tapping Send (MFL league). Expected: the same check-before-resending alert, not the generic error.
  7. Normal network: send one MFL trade. Expected: "Trade sent" as before, with no delay added.
  8. Regression, normal network: with an MFL sign-in removed (Settings → Disconnect MFL sign-in), tap Send. Expected: the existing "Sign in with MFL" prompt, unchanged. A trade with a moved player still shows its ownership refusal, not the new alert.
  9. Overhaul (only if `overhaul.enabled` is turned on for testing; it is OFF for launch): with Very Bad Network on, tap **Send all offers**. Expected: the app lands on the plan with the "Couldn’t confirm whether these offers reached {platform}" alert; each sent offer shows Sending / Sent, awaiting reply / Send status unknown, and there is no Send next tier on those packages. After Refresh with the network back, the platform shows each offer at most once.
- [ ] Waived: n/a.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. The `*_outcome_unknown` codes are documented by #513. |
| `living-memory/LLD.md` | n/a | No schema/route/invariant convention changed. The per-call `timeoutMs` follows the existing per-route deadline mechanism. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. |
| `living-memory/HLD.md` | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` | n/a | The timeout and the outcome-unknown branch are mobile-only. The web and the extension have no ESPN/MFL send, and the codes are the server's (#513). Nothing is shared between clients. |
| `docs/glossary.md` | n/a | "Outcome unknown" is already the overhaul's attempt state (`ATTEMPT_STATE_LABEL`, "Send status unknown"). |
| ADR or `DECISIONS.md` | n/a | head-eng's spec, followed as given. The two judgment calls (an unstructured 5xx and `internal_error` count as unknown; one constant at MFL's worst case for both platforms) are recorded here. |
| `mobile/src/api/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | updated | `sendOutcome.ts` row; the `OverhaulSummaryScreen` row's send outcomes. |

## 5. Ship gate declaration

- **CI green:** `tsc --noEmit`, every `mobile/tests/check-*.js`, testid-lint. Mobile-only, so `pytest backend/tests` is untouched.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-10-28 entry (suite, sabotage counts, tsc, testid-lint).
- **TestFlight verification:** §3's checklist, run by the operator on the 11-06 build, logged in TEST_LEDGER.
- Express lane declared by the operator? No. Full gates.
