# Feature Scope — E1 F5: session-init per-token single-flight

**Date:** 2026-10-22
**Entry point:** direct ask — E1 concurrency audit row F5 / test row T6 (`docs/plans/org-bringup/e1-concurrency-audit.md` on the org-bringup branch), routed through onboarding-eng → head-eng
**Builder:** eng-backend worker for onboarding-eng (branch `fix/e1-f5-session-init-single-flight`)
**Operator sign-off on waivers:** waivers below are surfaced to the lead for the operator. Every one of them is "nothing of that kind changes," not a skipped gate.

---

## 0. The change

`POST /api/session/init` had no per-token single-flight. App-open and foreground both call it, so two inits for one token could each resolve input, each build fresh `RankingService`s, and each swap them into the session, and the last swap won. A swipe that landed on A's service between the two swaps was in the DB but missing from B's service, which had replayed earlier. Prod today runs a sync gunicorn worker. This matters once E1 moves to `gthread`.

The fix is a decorator, `_single_flight_session_init` (`backend/server.py:2256-2298`, next to the in-flight globals at :2250-2253), applied under the route at :22203. The body of `session_init()` is untouched (zero lines changed) and so is the Flask endpoint name `session_init`. `functools.wraps` keeps `inspect.getsource(server.session_init)` resolving to the body, which `test_trade_disposition_restoration.py` relies on.

- **Key:** each `X-Session-Token` gets one in-flight entry: `{sig, done: Event, result}`.
- **Identical requests coalesce.** The signature is `(user_id, league_id, active_format)` from the raw JSON body. A follower whose signature matches waits up to `_SESSION_INIT_WAIT_S = 60` and replays the leader's frozen `(body, status, content-type)`.
- **A different signature waits, then loops.** It may become the leader. It never returns another league's result.
- **Fallback:** if the leader raised or the wait timed out, the follower runs its own init. It stays serialized behind any newer leader.
- **Bypass:** no token, or a non-object body, calls the impl directly. Every real init has a token.
- **Logging:** one `log.info` per coalesced follower, showing only a 6-character token prefix.

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED.** No analytics are needed: this is a server-internal concurrency fix with no new user action, surface or outcome to measure. No event is added, removed or changed. The `api_request` inbound observability row still records one row per HTTP request, coalesced followers included, because `after_request` runs on the replayed response.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none.** The fix is unflagged, because a lone caller is byte-identical and the rollback lever is a revert of one commit.
- New env vars / `model_config` keys: **none.** `_SESSION_INIT_WAIT_S` is a module constant, not configuration.

## 3. Evidence scope

- [ ] **Structural guard:** n/a. The change is backend-only and no mobile file changes.
- [x] **Unit tests:** `backend/tests/test_session_init_single_flight.py` (audit T6). The fixture registers the production decorator around the real body, with an enter/exit recorder in between. Each test forces the overlap: the first entrant blocks in `resolve_session_input` until the other request's thread stack shows the single-flight view → `wait`.
  - **T6a (coalesce).** Identical inits coalesce: 1 `RankingService` build per format, 1 swap, final `services` is the one installed, response bytes are equal, and the coalesce log appears once with no full token.
  - **T6b (different league).** A different league for the same token runs strictly after the first one (`enter A, exit A, enter B, exit B`). Each response carries its own league, and the session ends on the league that finished last.
  - **T6c (leader error).** The leader raises and gets a 500. The follower doesn't hang, runs its own init and gets a 200.
  - **T6c (stuck leader).** Past the wait bound (patched to 0.05 s) the follower takes over and runs its own init. The stuck leader's cleanup leaves the follower's in-flight entry alone. This test is DB-free and uses a fake impl.
  - **T6d (single caller).** A lone call through the real registered view is byte-identical (status, content type, body) to calling the undecorated body (`session_init.__wrapped__`) directly. The endpoint is still `session_init`. The no-token and non-object-body bypasses keep their 401 and 400.
  - The inflight map is empty after every test.
- [x] **Sabotage proof.** With the decorator made a pass-through (`return fn`), T6a fails with `builds_per_format {'1qb_ppr': 2, 'sf_tep': 2}` and `distinct_services_installed 2`. T6b and both T6c tests fail too. The T6d byte-compare errors because there is no `__wrapped__` to unwrap, and the two bypass tests pass. The sabotage was reverted and never committed.
- [x] **Code-walk proof:** see the worker's report to onboarding-eng, which has the leader, follower and different-sig paths with `backend/server.py` line numbers.
- [ ] Manual TestFlight checklist: **WAIVED.** No mobile or web code changes and the response contract is byte-identical. Under today's sync worker a second init simply queues, so the coalesce path can't be observed on TestFlight until E1's `gthread` switch.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **proposed, not edited** (head-eng owns it) | Append to the `POST /api/session/init` row: "Concurrent inits for one token are single-flighted: identical requests share one result; different leagues run one after the other." |
| `living-memory/LLD.md` | n/a | release-lead's scribe owns `living-memory/*`. No convention shifted. |
| `docs/architecture.md` | **proposed, not edited** (head-eng owns it) | In § Local request and trade execution context, add one sentence: "E1 F5: `/api/session/init` is single-flighted per token (`_session_init_inflight`); identical concurrent inits replay one result and a different league waits for the in-flight one, so two inits never swap services side by side." |
| `living-memory/HLD.md` | n/a | release-lead's scribe owns it, and the architecture did not shift (still one worker and in-process state). |
| `docs/cross-client-invariants.md` | n/a | No shared constants, enums or colors change. |
| `docs/glossary.md` | n/a | No new domain term. "Single-flight" is an engineering term used only in code comments. |
| ADR or `DECISIONS.md` entry | n/a | The design is the audit's prescribed fix (F5 "Per-token in-flight map"), not a new choice. The scribe owns `DECISIONS.md` if the lead wants it logged. |
| `docs/plans/README.md` | n/a | No `e1-concurrency/` row was added. rankings-eng's E1 scope is not on `origin/main` yet, so the first E1 scope to land should add the row. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (full `pytest backend/tests`), `mobile-typecheck` and testid-lint. Mobile is untouched, so only `backend-tests` can move.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry is owed by release-lead's scribe, using the counts in the worker report.
- **TestFlight verification:** waived (§3).
- **Express lane declared by the operator?** No. Full gates apply.
