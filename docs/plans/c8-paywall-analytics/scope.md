# Feature Scope — C8: paywall analytics events (`entitlement_granted`, `paywall_gate_hit`)

**Date:** 2026-10-28
**Entry point:** direct ask (head-eng's pre-launch triage item C8; analytics-lead's C8 spec, 2026-10-27)
**Builder:** platforms-eng
**Operator sign-off on waivers:** not needed (the one waiver is evidence for a backend-only change)

Kill criteria K0–K3 for the 2026-11-18 paywall enforcement flip can't be read without these two
events. The spec is analytics-lead's (head-eng's shared notes, `analytics-lead-c8-spec.md`, which
supersedes `reports/analytics-lead.md` §2). It lands in two PRs, because the gate code lives only on
the held paywall stack:

- **§A, `entitlement_granted`:** this branch, `feat/c8-entitlement-granted`, off `main`.
- **§B, `paywall_gate_hit`:** stacked on #473 (`feat/paywall-hardening`), with its own addendum,
  [`scope-gate-hit.md`](scope-gate-hit.md), on that branch.

## 1. Analytics scope

- [x] **(a) New events specced** (the taxonomy is analytics-lead's):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `entitlement_granted` (§A: registration only; the emitter already ships) | `entitlement` (pro \| ad_free), `source` (`entitlements.VALID_SOURCES`), `expires_at`. Closed, unchanged | `entitlements.grant()` inserts a row: the first grant per (user, product) from a webhook projection, plus manual, comp, bulk, Founders, referral and group-unlock grants. A renewal on an existing row returns before `grant()` | server |
  | `paywall_gate_hit` (§B) | `gate`, `route_family`, `enforced` | the paywall gate sends a 402 | server |

  - **§A class: NON_INTENT** (overrides #393's draft "INTENT"). Most grants aren't the recipient acting
    in a session; INTENT would mint a user-day for every recipient of a bulk grant. Registered in
    `SERVER_FIRED_EVENTS` and `analytics_queries.NON_INTENT_EVENTS` in the same commit, and written
    non-touching (`touch_user=False`), so it no longer moves the recipient's `last_active_at` or
    `events_count`.
  - Trial vs paid is read from `subscription_events.payload` `period_type`, not from this event.
  - **Seam:** registration is retroactive. Historical `entitlement_granted` rows start appearing in
    taxonomy-driven reads from this commit, as NON_INTENT, so no DAU/WAU series moves. Rows written
    before this commit did bump `last_active_at` / `events_count`; that history is not rewritten.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [ ] **Structural guard:** n/a (backend only).
- [x] **Unit tests:** `backend/tests/test_entitlement_granted_event.py`: both set memberships and not
      client-registered; exact props; `users.last_active_at` and `events_count` unchanged after
      `grant()`. Sabotage: drop `touch_user=False` → the non-touching test is red.
- [ ] **Code-walk proof:** n/a (mechanically checked).
- [ ] **Manual TestFlight checklist:** n/a.
- [x] **WAIVED** (structural guard, code walk, TestFlight): backend-only, no user-visible surface.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. |
| `living-memory/LLD.md` | n/a | No convention shift: this follows the existing "register + classify in the same commit" rule. |
| `docs/architecture.md` | n/a | No module wiring change. |
| `living-memory/HLD.md` | n/a | No architecture change. |
| `docs/cross-client-invariants.md` | n/a | Its paywall line already names `entitlement_granted` as conversion truth; the client event names are unchanged. |
| `docs/glossary.md` | n/a | No new term. |
| ADR or `DECISIONS.md` entry | n/a | The NON_INTENT class is analytics-lead's call, recorded in the spec and in the code comments. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-10-28.
- **TestFlight verification:** none needed.
- Express lane declared by the operator? No.
