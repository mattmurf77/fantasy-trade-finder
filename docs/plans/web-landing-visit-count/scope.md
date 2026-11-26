# Feature Scope — Landing page visit count (anonymous)

**Date:** 2026-11-25
**Entry point:** direct ask (owner, after PR 729 / D-284 merged as `917eeae2`): keep seeing website traffic; restore anonymous visit counting on the marketing landing. Nothing else about the cut is reversed.
**Builder:** builder subagent, branch `feat/web-landing-visit-count`
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `app_opened` with `launch_type: "web"`, the event the pre-cut landing fired from `web/js/app.js` `boot()` through `events.js`. Registered in `ALLOWED_CLIENT_EVENTS`, props allowlist `{launch_type, from_push, push_kind}` (`backend/analytics_taxonomy.py`), and already `NON_INTENT` (`analytics_queries.py`), so it never counts as DAU. It answers "how many times was the landing page loaded". No taxonomy change.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `app_opened` | `launch_type: "web"` (no `screen`) | once per landing page load, when `/api/feature-flags` returns `analytics.client_events` true | website landing (`web/js/landing-visit.js`) |

  **What changes against the pre-cut event (D-287):** the device id is a fresh `visit_<uuid>` per page load, never stored, instead of the persistent `ftf.deviceId` in localStorage; no `X-Session-Token`; no queue. So the row counts a visit, not a visitor: unique visitors and returning visitors cannot be counted, on purpose. Stored row: `user_id device:visit_<uuid>`, `device_id visit_<uuid>`, `source web`, `platform web`, `props {launch_type: web, seq: 1}`, `session_id` one-way hash, `country` from a CDN header only (NULL on bare Render), `client_ts`, server `occurred_at`; account, league, screen, device snapshot and experiments NULL. User agent and IP are not stored in `user_events`.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none. Gated on the existing `analytics.client_events` (client emission gate, true in production); the server's `analytics.ingest` still decides acceptance. Rollback lever: flip `analytics.client_events` false (no deploy), or revert the commit.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `qa/web/check_web_structure.py` (web-structure CI job) gains `CUT-landing-scripts[index.html]` (landing loads exactly `landing-steps.js` then `landing-visit.js`; no served page loads `events.js`) and `CUT-landing-visit-anonymous[landing-visit.js]` (two fetches only, one to `/api/events`; one event `app_opened`; props exactly `{launch_type: "web"}`; flag-gated; per-load `X-Device-Id`; no storage, cookie, session token, `location`, referrer, beacon, timer, league or user id; `credentials: "omit"` on both; a `.catch`). 10 sabotages red then restored (TEST_LEDGER).
- [x] **Unit tests:** `backend/tests/test_landing_visit_event.py` (4): the landing's exact request is accepted and the stored row is read back; two loads are two rows with two ids; country only from the CDN header; with no device id the intake rejects `no_identity` (why the page sends a throwaway id). `test_events_source.py` already covered `app_opened` `{launch_type: web}`, but only in events.js's beacon shape.
- [x] **Code-walk proof / runtime:** loaded in headless Chrome and the Claude browser pane against a local test server (port 5061, throwaway SQLite): one row per load, nothing in cookies or local/session storage; with `/api/events` answering 500 or dropping the connection the page renders and the step picker works, the only console line is the browser's own network log.
- [ ] **Manual TestFlight checklist:** n/a, website only.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `POST /api/events` row: the website caller and its exact request |
| `living-memory/LLD.md` | n/a | no schema, route or invariant convention changed |
| `docs/architecture.md` | n/a | no module wiring change; one static script |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant; the envelope is the existing contract |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | updated | D-287 (per-load id instead of the stored device id) |

`web/CLAUDE.md` updated (landing scripts, shared-code table, checker count).

**Privacy text (not edited, owner's ruling pending on the web-cut wording):** see the PR description for the sentence-by-sentence result. In short, the website sends usage events again (privacy line 107) and country (line 112) applies again; the local-storage sentences (109 website clause, 165) stay untrue; "Our website sets no cookies" stays true; nothing becomes newly untrue.

## 5. Ship gate declaration

- **CI green:** required on the pushed sha (backend-tests, web-structure, mobile-typecheck, testid-lint).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-25 landing visit count entry.
- **TestFlight verification:** n/a.
- Express lane declared by the operator? no.
