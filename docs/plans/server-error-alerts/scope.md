# Feature Scope — Server error alerts through Sentry (GNG-1)

**Date:** 2026-10-31
**Entry point:** go/no-go item GNG-1 (direct ask, rankings-eng's design)
**Builder:** rankings-eng build worker, branch `feat/server-error-alerts`
**Operator sign-off on waivers:** not needed (no waivers; the evidence section is backend-only by nature, said below)

The companion SUP-M7 alert ("feedback received") has its own block: [scope-feedback-alert.md](scope-feedback-alert.md).

## What it is

`backend/error_alerts.py`, wired into `backend/server.py`. **Dark until `SENTRY_DSN` is set**: with no DSN, init returns False, `sentry_sdk` is never imported, and the two request hooks return at a module-flag check.

With a DSN:
- **Every ERROR+ log record becomes an event.** There are no breadcrumbs.
  - Route exceptions arrive this way. `handle_unexpected_error` handles every exception, so Flask's `got_request_exception` never fires, and its `log.exception` carries the stack.
  - So do the `_cleanup_loop` step guards and `daily_tick.run`'s per-step guard. Neither was edited.
- **A 5xx response that produced no event of its own** becomes one `http_5xx` event. Its tags are `route` (the url rule, or `<unmatched>`), `status` and `method`, and its fingerprint is `["http_5xx", route, status]`. 4xx never reports.
- **Dedupe.** A `before_request` hook notes the request's `sentry_sdk.last_event_id()`, and the `after_request` hook reports only if it is unchanged. So the generic handler's 500 is one event, and so is any handled 500 that logged an exception first (for example `save_feedback failed`).
- **Each event is built from an allowlist** (`scrub_event`, before_send), following legal R28.23. Anything not listed is dropped, unknown keys included. If building it raises, nothing is sent.
  - The SDK's own top-level fields, as before.
  - `request` is `{method, url}`, where `url` is the **Flask route pattern** (`url_rule.rule`, else `<unmatched>`), read on the capturing thread. It is never the path or query. With no request context, there is no `request`.
  - `exception` / `threads`: type, module, mechanism and frames, with no locals. **No `value`**: the exception's text.
  - `logentry`:
    - the **template** (`record.msg`), with the pattern scrub over it as a second layer;
    - `params`, keeping only numbers under 9 digits, `[Filtered]` otherwise;
    - `formatted`, rebuilt from those two, or dropped if they don't format.
  - `message`: only `http_5xx` or `feedback_received`, else `[Filtered]`.
  - `tags`: `route`, `status`, `method`, `feedback_id` and `kind` only.
  - `contexts`: `runtime`, `os` and `trace` only.
  - `user`, `extra` and `breadcrumbs`: dropped.
  - **Breadcrumbs are off:** `LoggingIntegration(level=None, sentry_logs_level=None)`, and `before_breadcrumb` returns None.
  - **Templates are constants:** an AST guard over `backend/**/*.py` (177 error-level calls) fails CI on a non-constant template.
  - **Sentry locates; the detail lives in the Render logs.**
- **No tracing, no profiling, no PII, no request bodies.**
  - `auto_enabling_integrations=False`. The SQLAlchemy integration would breadcrumb every query with its parameters.
  - `trace_propagation_targets=[]`. No `sentry-trace`/`baggage` header goes to Sleeper, ESPN, MFL or Anthropic.
  - `ThreadingIntegration(propagate_scope=False)`. `_cleanup_loop` starts inside the first request, so otherwise every loop event would carry that request.

## Gates before the operator sets `SENTRY_DSN`

1. **MUST, privacy page (legal R28.23).** Legal cleared backend Sentry on conditions; they are tabled below. **`SENTRY_DSN` is set only once the privacy page carrying legal's R28.23 lines is live.** Those lines ship in #373 (onboarding-eng).
   - Until then, `web/privacy.html` names Sentry for the mobile app only (`:175-182`, `:190`, `:209`).
   - The page promises: "names, IDs and link codes are taken out of the address, and personal details are taken out of the log lines. If that can't be done, the report isn't sent… Server reports don't include your account or platform user ID, your username, your IP address, sign-in details or the content of what you send us."
2. **Volume (release-lead).** Every ERROR log line becomes an event. The guard counts 177 error-level log calls in `backend/`, most of them in `server.py`.
   - Before the DSN is set, release-lead counts prod ERROR lines per day from the Render logs and checks the count against the Sentry plan's quota.
   - Sentry groups repeats into one issue, but each one still counts against the quota.

## Legal R28.23 conditions

Legal's R28.23 text isn't in the repo. Rows 5 and 7 carry the numbers rankings-eng gave; the other rows follow the brief's order and the page's promise, so **rankings-eng should confirm the numbering against legal's note**. File:line refs are `backend/error_alerts.py` unless noted. Tests are in `backend/tests/test_error_alerts.py`.

| Condition | Where it's met | Test (sabotage that turns it red) |
|---|---|---|
| Names, IDs and link codes out of the **address** | `_route` `:277-286`: method + `url_rule.rule` only; `_allowlisted` `:291-294` sends it only inside a request | `test_legal_condition_7_no_planted_value_leaves`, `test_scrub_event_request_and_message_edges` (real path; query kept) |
| Personal details out of the **log lines** | `_param` / `_logentry` `:239-261`: the template, numbers under 9 digits, `formatted` rebuilt; `_scrub_str` `:233` over the template as a second layer. Templates must be constants: AST guard (i) | condition 7, `test_scrub_event_is_an_allowlist`, `test_a_raising_daily_tick_step_is_one_event`, `test_every_error_log_template_in_backend_is_a_constant` (raw params kept; one f-string `log.error`) |
| No exception text or locals | `_stack` `:264-274` (`_CODE_KEYS` `:128`, no `value`, frame `vars` popped at `:272`); `include_local_variables=False` `:151` | condition 7, the allowlist test (`value` kept) |
| No account or platform user ID, username, IP, sign-in details or content | `_allowlisted` `:289-306`: no `user`, `extra` or `breadcrumbs`, and no headers, cookies or body in `request`; tags `:303` and contexts `:305` allowlisted; `send_default_pii=False` `:150`; `max_request_body_size="never"` `:152`. `feedback_received` carries id and severity only (`server.py` `submit_feedback_route`) | condition 7, `test_no_credential_reaches_the_envelope`, the feedback test (headers kept; notify on a fork) |
| **5**: Sentry project Data Scrubber, Default Scrubbers, Prevent Storing of IP Addresses ON | operator, `docs/runbook.md` § Server error alerts, "Turning it on" step 2 | none in code; the runbook's first-hour check opens three events |
| Logging breadcrumbs (strictest form: none) | `LoggingIntegration(level=None, …, sentry_logs_level=None)` `:159`; `scrub_breadcrumb` `:319-323` returns None; the allowlist drops `breadcrumbs` | `test_breadcrumbs_are_off`, `test_init_options`, condition 7's "none collected" check (breadcrumbs re-enabled) |
| "If that can't be done, the report isn't sent" | `scrub_event` `:309-316`: any exception → None | `test_a_scrubber_exception_drops_the_event`, `…_sends_nothing_unsafe` (fail open) |
| **7**: one request with the planted id, username, share token, email and IP in the path; `?ref=`/`token=`; X-Forwarded-For, X-Real-IP, Cookie, Authorization (plus X-Session-Token, which the SDK's own header filter doesn't know); the values logged, held in a local, and raised | `test_legal_condition_7_no_planted_value_leaves`. It checks that none of the planted values is in the serialized envelope bytes, and that `request.url` is the route pattern. It also checks the SDK did collect them before the allowlist, so the test isn't vacuous | all six legal sabotages, plus `before_send` removed |

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
- [x] **Unit tests:** `backend/tests/test_error_alerts.py`, 52 tests, with a recording transport and a fake DSN, so nothing goes over the network:
  - (a) no DSN: no client, nothing sent, the SDK never imported; a malformed DSN doesn't fail boot; the init options are pinned;
  - (b) a raising route is one event, with the stack but without its text;
  - (c) a handled 503 is one `http_5xx`, with its tags and fingerprint; a 404 is none; a handled 500 after `log.exception` is one event;
  - (d) a `_cleanup_loop` step raising is one event;
  - (e) a `daily_tick` step raising is one event;
  - (f) the allowlist: legal's condition-7 request and the credential request (no planted value in the envelope bytes), the event shape and edges, the pattern layer, breadcrumbs off, and fail closed (e2e too);
  - (g) see the SUP-M7 block;
  - (h) a thread started in a request carries no request;
  - (i) the AST guard: every error-level log template in `backend/` is a constant (177 calls in 153 files).

  Seventeen sabotages, each red then green; see `living-memory/TEST_LEDGER.md` 2026-10-31.
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
| `docs/runbook.md` | updated | new § "Server error alerts (Sentry)": the allowlist, the MUST gate (#373), and the Sentry project settings (condition 5) |
| `living-memory/DEPENDENCIES.md` | updated | 2026-10-31: the `sentry-sdk==2.72.0` pin |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (installs `requirements.txt`, so the new test file runs), `mobile-typecheck` and `maestro-testid-lint`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-31.
- **TestFlight verification:** n/a (backend-only).
- Express lane declared by the operator? No. Full gates.
- **Turning it on is a separate, later step**, behind both gates above. Merging ships the code dark.
