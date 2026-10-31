# Feature Scope — "Feedback received" alert (SUP-M7)

**Date:** 2026-10-31
**Entry point:** support item SUP-M7 (direct ask, rankings-eng's design), built with GNG-1
**Builder:** rankings-eng build worker, branch `feat/server-error-alerts`
**Operator sign-off on waivers:** not needed (no waivers)

Rides on GNG-1's Sentry wiring: [scope.md](scope.md). It is **dark until `SENTRY_DSN` is set**, and has the same two gates as GNG-1 before then. The privacy-page gate applies here too: legal updates `web/privacy.html` (`:175-182`, `:190`, `:209` name Sentry for the mobile app only) before the operator sets the DSN.

## What it is

- **What happens.** After `POST /api/feedback` stores a **new** row, `submit_feedback_route` calls `error_alerts.notify("feedback_received", feedback_id=<server_id>, kind=<severity>)`.
- **What doesn't.** The idempotent duplicate return (same `client_id`, including the rate-limited duplicate path) sends nothing, and neither does a failed save.
- **The event.** One `level="info"` message event on a fresh isolation scope: no breadcrumbs, request, user or transaction.
  - Its tags are exactly `feedback_id` (the row's autoincrement id) and `kind` (`bug` / `polish` / `idea`).
  - Never the text, screen, user, username, session token or hash, client id or device headers.
- **No-op when Sentry is off;** it never raises into the route. The response is unchanged: same status, same body.
- **The operator's alert rule** is in `docs/runbook.md` § "Server error alerts (Sentry)": per event, or a digest. The note itself is read where it always was: `GET /api/feedback/admin`, or the `feedback` skill.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** `feedback_received` is a **Sentry alert event, not an analytics-taxonomy event**. It is not written to `user_events`, and not registered in `analytics_taxonomy.py`. The existing analytics event for this moment, `feedback_submitted` (verified users only), is unchanged.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none (`SENTRY_DSN` is the switch, as in GNG-1)
- New env vars: none beyond GNG-1's

## 3. Evidence scope

- Maestro: **retired (D-056)**. Simulator captures: **retired (D-056)**.
- [x] **Unit tests:** `backend/tests/test_error_alerts.py` case (g), `test_new_feedback_is_one_tag_only_alert_and_a_duplicate_none`.
  - A verified session posts the note `MY-PRIVATE-FEEDBACK`. That gives exactly one info event `feedback_received`, whose tags are exactly `{feedback_id, kind}`, with no request, user, transaction or breadcrumbs.
  - The serialized envelopes contain none of: the text, screen, client id, session token, user id, username, display name or device id.
  - Re-posting the same `client_id` gives 200 `duplicate: true` and no second event.
  - Case (a) shows `notify` is a no-op with no DSN.
  - Sabotages, both red then green: notify on a fork of the request scope; the duplicate guard removed.
- [x] **WAIVED (structural guard, code-walk, TestFlight checklist) because:** backend-only; the route's response is unchanged.
- The existing feedback route suites pass unchanged, with and without `sentry-sdk` installed: `test_feedback_public.py`, `test_feedback_public_limits.py`, `test_feedback_text_cap.py` and `test_feedback_attach_on_verify.py`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `POST /api/feedback`: one line on the alert side effect, response unchanged |
| `living-memory/LLD.md` | n/a because | no convention change |
| `docs/architecture.md` | updated | the `error_alerts.py` row (shared with GNG-1) |
| `living-memory/HLD.md` | n/a because | see GNG-1's block |
| `docs/cross-client-invariants.md` | n/a because | no shared constant |
| `docs/glossary.md` | n/a because | no new term |
| ADR or `DECISIONS.md` | n/a because | the only choice is "id and severity only", which is the design itself |

## 5. Ship gate declaration

- **CI green:** as GNG-1.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-31, the same entry as GNG-1.
- Express lane declared by the operator? No.
