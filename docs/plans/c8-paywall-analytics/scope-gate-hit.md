# Scope addendum: C8 §B, the `paywall_gate_hit` server event

> C8 §B only. §A (`entitlement_granted`) is PR #508, off `main`; its `scope.md` lands
> with it in this folder and is not on this branch. Branch `feat/c8-paywall-gate-hit`,
> cut from `feat/paywall-hardening` @ `b214ce12` (#473, the top of the held paywall stack
> #394 → #395 → #397 → #473). Spec: analytics-lead, 2026-10-27, head-eng-approved.
> Lead: platforms-eng. Date: 2026-10-28.

- [What changes](#what-changes)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope)
- [5. Known gaps](#5-known-gaps)

## What changes

- **Emitter:** the paywall gate's `before_request` hook (`_paywall_gate_hook`), at the one
  point it sends a 402 (`backend/server.py:33015`). `_emit_paywall_gate_hit`
  (`server.py:33019`) calls `paywall_gate.record_gate_hit` inside a `try/except`: a failure is
  logged at WARNING with the exception type name only and the 402 goes out unchanged.
- **Owner and envelope:** the session's `user_id`, written with
  `record_event(..., touch_user=False)` (no `users` update, no streak). `device_type` /
  `os_version` / `app_version` are the `X-Device` / `X-OS-Version` / `X-App-Version`
  headers; `source` is `mobile` when `paywall_gate.is_mobile_request()`, else `web`.
- **`route_family`:** `paywall_gate.route_family(rule)` (`paywall_gate.py:360`), a pure
  function of the matched rule (never the raw path), next to `ROUTES`.
- **The cap:** `paywall_gate._first_hit_today` (`paywall_gate.py:675`), the first row per
  (user_id, gate, route_family) per UTC day, held in process under a lock (gthread). Bounded
  two ways: the key set is cleared when the UTC date changes, and past
  `GATE_HIT_MAX_KEYS` (10,000) the oldest key is evicted. An evicted key, or a restart
  mid-day, can write a second row for that key that day: an over-count, never unbounded
  memory. Readers count distinct (user, gate, route_family, day).
- **`record_event` gains `touch_user` (and `bind`).** The stack predates #419, which added
  them on `main`. This branch carries #419's `database.py` hunk unchanged, so
  `record_event` is byte-identical to `main`'s and the next `main` merge into the stack
  resolves cleanly. Every existing caller is unchanged (both default to today's behavior).

## 1. Analytics scope

**(a) New event**, registered in the same commit as its emitter:
`analytics_taxonomy.SERVER_FIRED_EVENTS` and `analytics_queries.NON_INTENT_EVENTS`, each with
a comment. Both entries sit mid-set (after `standing_offer_card_shown` and after
`paywall_restore`), not at the end, so they don't conflict with #508's append.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `paywall_gate_hit` | `gate`: the 402 body's, verbatim (`preview_used` \| `never_trialed` \| `trial_expired` \| `lapsed` \| `verify_required`). `route_family`: `deck` (`DECK_ROUTES`) \| `send` (propose, propose-espn, propose-mfl, queue, respond-mfl, standing-offer) \| `matches` (`matches/<id>/disposition`) \| `calculator` (fair-packages) \| `shop` (asset-ideas) \| `overhaul` (every `/api/overhauls*` rule) \| `win_now` (every `/api/win-now/*` rule) \| `other` (any gated rule not listed; none today). `enforced`: bool. No path params, ids or prices. | The gate hook sends a 402, at most once per (user, gate, route_family) per UTC day | Server (NON_INTENT, never client-submittable) |

`enforced` is always true. While dark the hook returns before any verdict and writes nothing
(P3-4's invariant), so there are no observe-mode rows. The field stays for K0/K3, which read
`enforced=true`.

## 2. Schema & flag scope

- Tables or columns: none (rows go to `user_events`; props are JSON).
- Feature flags: none. The event rides the gate: it can only fire while
  `entitlements.is_enforcing()`, so `paywall_enforce_enabled` = 0 stops it with the 402s.
- Env vars / `model_config` keys: none.

## 3. Evidence scope

- **Unit tests:** `backend/tests/test_paywall_gate_hit.py` (new, 53 tests):
  - membership in both sets, never a client event;
  - exact props and envelope columns on a real gated 402, mobile and web;
  - `gate` verbatim for all five reasons;
  - every gated rule in `ROUTES` maps off `other`, and the eight values are the closed set
    (all seven non-`other` families are in use);
  - the hook reports the matched rule, never the path's ids;
  - the cap: same day one row, another gate or route_family a second, the next UTC day (injected
    clock) a new one; bounded (date change clears, the key cap evicts the oldest); 16 threads
    on one key give exactly one row;
  - `touch_user=False`: the `users` row is unchanged;
  - a free rule, a dark server (flags off; knob 0) and a route's own 403
    `verification_required` write nothing;
  - a raising `record_event` returns the byte-identical 402 (status, body, headers but Date),
    and the warning carries the type name only.
- **Sabotage, each red then restored:**

  | # | Sabotage | Red (of 53) |
  |---|---|---|
  | S1 | `try/except` dropped from `_emit_paywall_gate_hit` and `record_event` raises | 1: the byte-identical 402 test (the request answers 500) |
  | S2 | the cap dropped (`record_gate_hit` skips `_first_hit_today`) | 1: the per-day cap test |
  | S3 | one gated rule (`fair-packages`) mapped to `other` | 3: the closed set, that rule's mapping cell, the spec mapping |
  | S4 | `touch_user=True` | 1: the `users` row test |

- **Targeted runs:** 828 passed, 0 failed (the new file, every paywall file including the
  P3-4 `test_p34_*` tests, every `test_analytics*` / taxonomy file, both entitlements files).
  Counts per file are in `living-memory/TEST_LEDGER.md` (2026-10-28).

- **Code-walk proof:** the 402 path is `_paywall_gate_hook` → `verdict()` returns
  `(402, body)` → `_emit_paywall_gate_hit(sess.get("user_id"), rule, body)` →
  `record_gate_hit` → `route_family(rule)` → `_first_hit_today` → `db.record_event(...,
  touch_user=False)` → `return jsonify(body), 402`. The 402 tuple is built from the same
  `result` before and after the emit, so the emit can't change it.
- **Manual TestFlight checklist:** waived, backend-only and dark (no user-visible surface).
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Paywall gate (402): one sentence, each 402 also records `paywall_gate_hit` |
| `living-memory/LLD.md` | n/a because | no schema, route or invariant convention shifted; the event follows the server-fired registration rule |
| `docs/architecture.md` | n/a because | no module wiring or data flow change beyond one more `record_event` call site |
| `living-memory/HLD.md` | n/a because | no architecture shift |
| `docs/cross-client-invariants.md` | n/a because | server-only event; no client reads these enums |
| `docs/glossary.md` | n/a because | no new domain term (`gate` and route families are paywall-gate vocabulary already documented in api-reference) |
| ADR or `DECISIONS.md` | n/a because | the choices (no observe-mode rows, in-process cap) are analytics-lead's and platforms-eng's spec calls, recorded here |

## 5. Known gaps

- The serve-time `record_preview` claim-failure 402s in `_serve_stored_trade_page`,
  `_serve_deck_status` and `_serve_trade_job` (`server.py:33092`, `:33114`, `:33140`) emit
  nothing. They fire only when another deck already holds the preview.
