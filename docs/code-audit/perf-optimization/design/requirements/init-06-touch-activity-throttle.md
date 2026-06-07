# REQ — INIT-06: Throttle `touch_user_activity`

- **Initiative / Wave / Scope:** INIT-06 · Wave 1 · [B]
- **Source observations:** OBS-ROUTE-04
- **Peak RICE-P:** 5.6

## Problem statement

`_stash_device_and_touch_activity`, registered as `@app.before_request`
(`server.py:971`), executes a synchronous `UPDATE users SET last_active_at=…`
database write on every single authenticated request — including high-frequency
polling endpoints like `/api/trades/status` — producing unbounded write
amplification and adding a blocking DB round-trip to the hot path of every
authed call on the single-worker free dyno.

## User stories

- As a **dynasty manager**, I want trade-status polls and ranking requests to
  return faster, so that the app feels responsive during a trade-generation run.
- As an **operator**, I want the free-tier Postgres write load reduced during
  active user sessions, so that the single gunicorn worker is less frequently
  blocked on `last_active_at` updates that provide no sub-minute signal.
- As a **developer**, I want `last_active_at` still updated on a reasonable
  cadence, so that re-engagement and last-seen features retain their coarse
  accuracy without being driven per-request.

## Functional requirements

- **FR-1** — In `_stash_device_and_touch_activity` (`server.py:971–995`), check
  the in-session `last_active` timestamp (already maintained in the Flask session
  at `server.py:2788`) before calling `touch_user_activity`. Only call
  `touch_user_activity` if `now - sess.get('last_active', 0) >= TOUCH_THROTTLE_S`
  where `TOUCH_THROTTLE_S = 60` (seconds).
- **FR-2** — When `touch_user_activity` is called (i.e., the throttle interval
  has elapsed), update `sess['last_active']` to the current timestamp immediately
  after the call, so the next N calls within 60 s are skipped.
- **FR-3** — When the throttle skips the write, the `before_request` hook must
  still complete all non-write work (device-info stash, session validation) and
  must not alter any auth behavior or response status.
- **FR-4** — `TOUCH_THROTTLE_S` must be defined as a named constant (not a magic
  number) in or near `server.py:971`, so future operators can adjust it without
  hunting for the value.
- **FR-5** — On the **first** authenticated request in a fresh session (no
  `last_active` in the session), `touch_user_activity` must always execute
  unconditionally, ensuring a cold-start login records an accurate
  `last_active_at`.

## Acceptance criteria

- [ ] **AC-1** — Given a `/api/trades/status` poll loop running at 1.5 s
  cadence for 60 s, when the throttle is active, then the `UPDATE users`
  statement in `database.py:929–935` is executed at most once per 60-second
  window (verified by a test or log counter, not by timer alone).
- [ ] **AC-2** — Given a burst of 40 authed requests within 60 s from the same
  session, when inspecting the DB, then `users.last_active_at` is updated no
  more than 2 times (once at t=0, once at t≥60 s if the burst spans the window).
- [ ] **AC-3** — Given a brand-new session (no `last_active` key), when the
  first authenticated request arrives, then `touch_user_activity` is called
  immediately (no skip).
- [ ] **AC-4** — Given the throttle is active, when a user makes requests for
  10 minutes (600 s), then `last_active_at` precision is within ~1 min of the
  actual last request time (i.e., the timestamp is no more than ~60 s stale).
- [ ] **AC-5** — Given no code changes to auth or session validation, the
  throttle change does not alter HTTP status codes, response bodies, or session
  cookie behavior on any existing endpoint.
- [ ] **AC-6** — A code review confirms no re-engagement query, notification
  dispatch, or scheduling logic in `server.py` or `database.py` relies on
  sub-minute precision in `users.last_active_at` (discrete user actions continue
  to write precise rows via `record_event` / `user_events`).

## Related components

- `backend/server.py:971–995` — `_stash_device_and_touch_activity`
  (`before_request` hook)
- `backend/server.py:2788` — in-session `last_active` timestamp
- `backend/database.py:907–937` — `touch_user_activity` (the DB write)
- `backend/database.py:914–918` — comment documenting coarse-pointer intent for
  `last_active_at`
- `render.yaml:13` — `--workers 1` (single-worker context that makes write
  contention acute)

## Prerequisite components / dependencies

None. The in-session `last_active` field is already present at `server.py:2788`;
the change is a guard clause in the existing `before_request` hook. No other INIT
must land first.

## Non-functional requirements & invariants

- **Perf target:** `UPDATE users` write frequency for any one user drops from
  once-per-authed-request to at most once per 60 s; worst-case status-poll
  contention on the single worker is reduced proportionally.
- **`last_active_at` precision:** the field's documented purpose is a coarse
  "last seen" pointer (per `database.py:914–918`). Relaxing precision to ~1 min
  is by design; confirm no downstream code path queries it at sub-minute
  granularity. The `user_events` table continues to record precise timestamps
  for discrete actions and is unaffected.
- **No ELO / tier-band invariant:** this change is request-middleware only; no
  ranking, scoring, or trade logic is touched.
- **Both dialects (SQLite + Postgres):** the throttle lives in Python; no SQL
  change. Both dialects unaffected beyond receiving fewer `UPDATE` calls.
- **Rollback:** removing the guard clause fully restores prior behavior (every
  request writes). No migration or schema change required.

## Out of scope

- Moving `touch_user_activity` off the request thread entirely (fire-and-forget
  background queue — Option B in OBS-ROUTE-04). That is a more complex change
  with worker-lifecycle concerns on the free tier.
- Endpoint-specific allowlists (Option C in OBS-ROUTE-04 — skip only on
  `/api/trades/status`). The in-session throttle is simpler and covers all
  authed endpoints uniformly.
- Changes to `user_events` write frequency or precision.
- Notification, leaderboard, or re-engagement query changes.
