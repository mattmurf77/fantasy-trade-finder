# Feature Scope — Server error alerts through Sentry (GNG-1)

**Date:** 2026-10-31
**Entry point:** go/no-go item GNG-1 (direct ask, rankings-eng's design)
**Builder:** rankings-eng build worker, branch `feat/server-error-alerts`
**Operator sign-off on waivers:** not needed (no waivers; the evidence section is backend-only by nature, said below)

The companion SUP-M7 alert ("feedback received") has its own block: [scope-feedback-alert.md](scope-feedback-alert.md).

## What it is

`backend/error_alerts.py`, wired into `backend/server.py`. **Dark until `SENTRY_DSN` is set**: with no DSN, init returns False, `sentry_sdk` is never imported, and the two request hooks return at a module-flag check.

With a DSN:
- **Every ERROR+ log record becomes an event**, and INFO+ records become breadcrumbs (30 at most).
  - Route exceptions arrive this way. `handle_unexpected_error` handles every exception, so Flask's `got_request_exception` never fires, and its `log.exception` carries the stack.
  - So do the `_cleanup_loop` step guards and `daily_tick.run`'s per-step guard. Neither was edited.
- **A 5xx response that produced no event of its own** becomes one `http_5xx` event. Its tags are `route` (the url rule, or `<unmatched>`), `status` and `method`, and its fingerprint is `["http_5xx", route, status]`. 4xx never reports.
- **Dedupe.** A `before_request` hook notes the request's `sentry_sdk.last_event_id()`, and the `after_request` hook reports only if it is unchanged. So the generic handler's 500 is one event, and so is any handled 500 that logged an exception first (for example `save_feedback failed`).
- **Scrubbing** (`before_send` / `before_breadcrumb`) mirrors and extends mobile's S0 scrub. Both fail closed.
  - The request keeps only `method` and `url`, with no query.
  - The user is removed.
  - Every content string is scrubbed: JWTs, bearer, credential `key=value`s (cookies, `espn_s2`, `SWID`, `MFL_USER_ID`, `APIKEY`, `?token=`), emails, UUIDs and GUIDs, 80+ base64/percent blobs, 24+ hex or base64url runs, and **any run of 9+ digits**.
  - Sensitive dict keys are replaced wholesale.
  - Tag keys `route`, `status`, `method`, `feedback_id` and `kind` pass unscrubbed.
  - Outbound-HTTP breadcrumbs are dropped.
  - Stack frames keep file, function, line and source, and lose any locals.
- **No tracing, no profiling, no PII, no request bodies.**
  - `auto_enabling_integrations=False`. The SQLAlchemy integration would breadcrumb every query with its parameters.
  - `trace_propagation_targets=[]`. No `sentry-trace`/`baggage` header goes to Sleeper, ESPN, MFL or Anthropic.
  - `ThreadingIntegration(propagate_scope=False)`. `_cleanup_loop` starts inside the first request, so otherwise every loop event would carry that request.

## Gates before the operator sets `SENTRY_DSN`

1. **Privacy page (legal).** `web/privacy.html` names Sentry for the **mobile app only**: §1 "Crash and performance data (Sentry)" (`:175-182`), §3 "crash reports" (`:190`), and §4 Third parties "receives crash and performance reports from the mobile app" (`:209`).
   - Server events add a new flow to Sentry. It's scrubbed, but it's still a new flow: request method and path, server error messages, and log breadcrumbs.
   - **The DSN stays unset until legal updates that page.** head-eng is routing the one-line legal check.
2. **Volume (release-lead).** Every ERROR log line becomes an event. There are about 170 `log.error`/`log.exception` sites, 150 of them in `server.py`.
   - Before the DSN is set, release-lead counts prod ERROR lines per day from the Render logs and checks the count against the Sentry plan's quota.
   - Sentry groups repeats into one issue, but each one still counts against the quota.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this sends no product analytics. `http_5xx` and the log events are Sentry error events, not `analytics_taxonomy` events. Nothing is written to `user_events`, and `analytics_taxonomy.py` / `NON_INTENT_EVENTS` are untouched.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. The kill switch is the env var: unset `SENTRY_DSN` and restart.
- New env vars:
  - `SENTRY_DSN`: the on switch. The operator sets it on Render, and it is never committed.
  - `SENTRY_ENVIRONMENT`: optional, defaults to `production`.
  - `RENDER_GIT_COMMIT` is read as the release. Render sets it.

  All three are in `docs/config-reference.md`. The deploy-free rollback is to unset `SENTRY_DSN` in the Render dashboard; the restart that follows turns it off.
- API: no route added or changed. Every response is byte-identical; the hooks only read.

## 3. Evidence scope

<!-- D-056: Maestro and the simulator are retired. -->

- Maestro: **retired (D-056)**. Simulator captures: **retired (D-056)**.
- [x] **Unit tests:** `backend/tests/test_error_alerts.py`, 33 tests, with a recording transport and a fake DSN, so nothing goes over the network:
  - (a) no DSN: no client, nothing sent, the SDK never imported; a malformed DSN doesn't fail boot; the init options are pinned;
  - (b) a raising route is one event, with the stack;
  - (c) a handled 503 is one `http_5xx`, with its tags and fingerprint; a 404 is none; a handled 500 after `log.exception` is one event;
  - (d) a `_cleanup_loop` step raising is one event;
  - (e) a `daily_tick` step raising is one event;
  - (f) the scrub end to end: no secret in the serialized envelope bytes. Also the pattern table, the event shape, breadcrumbs, and fail closed (e2e too);
  - (g) see the SUP-M7 block;
  - (h) a thread started in a request carries no request.

  Ten sabotages, each red then green; see `living-memory/TEST_LEDGER.md` 2026-10-31.
- [x] **Code-walk proof** (fork safety under `--preload`; sentry-sdk 2.72.0):
  - `init_error_alerts()` runs in the gunicorn master and starts no thread. Checked: `threading.enumerate()` is unchanged after init.
  - In the forked worker, the first event calls `BackgroundWorker.submit` (`sentry_sdk/worker.py:140`), which calls `_ensure_thread` (`:65`).
  - `is_alive` is False for another pid (`:59`), so `start` (`:86`) starts a new sender thread and records the pid (`:95`).
  - The session flusher (`sessions.py:193`) and backpressure monitor (`monitor.py:50-58`) restart per pid as well.
- [x] **WAIVED (structural guard, TestFlight checklist) because:** backend-only, with no client surface. Runtime proof against a real Sentry project comes after the privacy gate: the operator sets the DSN, then the runbook's first-hour checks run.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `POST /api/feedback`: the SUP-M7 side effect, response unchanged. No other route changed. |
| `living-memory/LLD.md` | n/a because | no schema, route or invariant convention changed |
| `docs/architecture.md` | updated | Components → Backend: the `error_alerts.py` row |
| `living-memory/HLD.md` | n/a because | one dark observability module, with no new client or major flow; the HLD's external-dependency line is high level and points at DEPENDENCIES.md, which is updated |
| `docs/cross-client-invariants.md` | n/a because | no shared constant |
| `docs/glossary.md` | n/a because | no new domain term |
| ADR or `DECISIONS.md` | n/a here | the non-obvious choices are listed in this block and the module doc: the dedupe mechanism, the three options beyond the design, and the lazy import. A `D-` entry is rankings-eng's call at merge, which avoids an ID race with concurrent sessions. |
| `docs/config-reference.md` | updated | Environment variables: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `RENDER_GIT_COMMIT` |
| `docs/runbook.md` | updated | new § "Server error alerts (Sentry)" |
| `living-memory/DEPENDENCIES.md` | updated | 2026-10-31: the `sentry-sdk==2.72.0` pin |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (installs `requirements.txt`, so the new test file runs), `mobile-typecheck` and `maestro-testid-lint`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-31.
- **TestFlight verification:** n/a (backend-only).
- Express lane declared by the operator? No. Full gates.
- **Turning it on is a separate, later step**, behind both gates above. Merging ships the code dark.
