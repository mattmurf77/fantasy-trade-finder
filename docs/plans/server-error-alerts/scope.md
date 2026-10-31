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
  - `exception` / `threads`: type, module, mechanism and frames. Frames carry file, function and line only: no locals, and no source lines (`include_source_context=False`). **No `value`**: the exception's text.
  - `logentry`:
    - the **template** (`record.msg`), **only from a logger we control** (`backend.*`, `trade_finder`, `ftf.*`, `gunicorn.error`), with the pattern scrub over it as a second layer. Any other logger's template becomes `[Filtered]`; its name and level still go;
    - `params`: **every one is `[Filtered]`, numbers included**, because a `match_id` is a `/s/trade/` link code;
    - `formatted`, rebuilt from those two, or dropped if they don't format (a `%d`).
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

The source is legal-lead's R28.23, row 2 ("Server error reports (Sentry)"), in `docs/plans/org-bringup/leads/legal-lead.md` in the org-bringup worktree. Rows below follow legal's order. File:line refs are `backend/error_alerts.py` unless noted, and tests are in `backend/tests/test_error_alerts.py`. A sabotage, named in brackets, turns its test red.

| # | Legal's condition | Where it's met | Test |
|---|---|---|---|
| 1 | **The address is the route pattern** (or id/username/token segments replaced); **the query string is dropped** | `_route` `:285-294`: method + `url_rule.rule`, else `<unmatched>`, read on the capturing thread; `_allowlisted` `:299-302` sends it only inside a request context | `test_legal_condition_7_no_planted_value_leaves`, `test_scrub_event_request_and_message_edges`, `test_a_match_id_never_reaches_the_envelope` [real path; query kept] |
| 2 | **No request headers are sent** (cookies, `Authorization`, `X-Forwarded-For`, `X-Real-IP`) | `_route` builds `request` from method and pattern only, so the SDK's `headers`, `cookies`, `env`, `data` and `query_string` never pass `_allowlisted` (`:297-314`); `max_request_body_size="never"` `:161` | condition 7 (all four, plus `X-Session-Token`), `test_no_credential_reaches_the_envelope` [headers kept] |
| 3 | **Stack traces go without local variables** | `include_local_variables=False` `:159`; frame `vars` popped `:280`. Stricter: no source lines either (`include_source_context=False` `:160`) and no exception text (`_stack` `:272-282`, `_CODE_KEYS` `:136`) | condition 7 (the planted values are held in a local), `test_frames_carry_no_source_lines`, `test_scrub_event_is_an_allowlist` [`value` kept; `include_source_context=True`] |
| 4 | **`send_default_pii=False`; no user context; logging breadcrumbs pass the scrub** | `send_default_pii=False` `:158`; `_allowlisted` drops `user`, `extra` and `breadcrumbs` (`:297-314`). Breadcrumbs, the strictest form, are off: `LoggingIntegration(level=None, …, sentry_logs_level=None)` `:168`, and `scrub_breadcrumb` returns None (`:327-331`). The log lines that *are* sent (events) carry the template from our loggers only (`_ours` `:248`, `_OUR_LOGGERS` `:80`), every param `[Filtered]` (`_logentry` `:253-269`), and the pattern scrub over it (`_scrub_str` `:242`). Templates are constants (the AST guard). Tags `:311` and contexts `:313` are allowlisted | condition 7, `test_a_match_id_never_reaches_the_envelope`, `test_a_third_party_template_is_filtered`, `test_template_only_from_our_loggers`, `test_breadcrumbs_are_off`, `test_init_options`, `test_every_error_log_template_in_backend_is_a_constant` [raw params kept; ints pass; templates from every logger; breadcrumbs re-enabled; an f-string `log.error`] |
| 5 | **Sentry's own server-side scrubbing stays on**, as a second layer | operator-side: `docs/runbook.md` § Server error alerts, "Turning it on" step 2 (Data Scrubber, Use Default Scrubbers, Prevent Storing of IP Addresses ON; the last also answers legal's Q11) | none in code; the runbook's first-hour check opens three events |
| 6 | **The feedback alert carries only the id and the severity** | `notify` (`:188-203`, fresh scopes, the given tags only), called from `server.py:16269` in `submit_feedback_route` with `feedback_id` and `kind` only; `_MESSAGES` `:71` | `test_new_feedback_is_one_tag_only_alert_and_a_duplicate_none` [notify on a fork; the duplicate guard removed] |
| 7 | **A test pins it:** an error carrying a user id, a username, a share token, an email and an IP in the path, the query, a log line and a local comes out clean, or isn't sent | `test_legal_condition_7_no_planted_value_leaves`. It asserts none of the 8 planted values is in the serialized envelope bytes, `request.url` is the route pattern, the SDK did collect the values before the allowlist (not vacuous), and no breadcrumbs were collected. "Or isn't sent": `scrub_event` `:317-324`, where any exception → None (`test_a_scrubber_exception_*`) | the six R28.23 sabotages, plus `before_send` removed and fail-open |

**Legal's gate (MUST):** the operator sets `SENTRY_DSN` only after the page with these lines (#373) is live. Per legal, it doesn't wait on A2/Q11.

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
- [x] **Unit tests:** `backend/tests/test_error_alerts.py`, 68 tests, with a recording transport and a fake DSN, so nothing goes over the network:
  - (a) no DSN: no client, nothing sent, the SDK never imported; a malformed DSN doesn't fail boot; the init options are pinned;
  - (b) a raising route is one event, with the stack but without its text;
  - (c) a handled 503 is one `http_5xx`, with its tags and fingerprint; a 404 is none; a handled 500 after `log.exception` is one event;
  - (d) a `_cleanup_loop` step raising is one event;
  - (e) a `daily_tick` step raising is one event;
  - (f) the allowlist: legal's condition-7 request, the credential request, a `match_id` log param and a third-party logger's template (no planted value in the envelope bytes), frames without source lines, templates only from our loggers, the event shape and edges, the pattern layer, breadcrumbs off, and fail closed (e2e too);
  - (g) see the SUP-M7 block;
  - (h) a thread started in a request carries no request;
  - (i) the AST guard: every error-level log template in `backend/` is a constant (177 calls in 153 files).

  Twenty sabotages, each red then green; see `living-memory/TEST_LEDGER.md` 2026-10-31.
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
