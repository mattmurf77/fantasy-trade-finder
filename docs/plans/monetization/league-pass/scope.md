# Feature Scope — League pass, server side (phase 1, dark)

**Date:** 2026-11-22
**Entry point:** direct ask (operator: "Build server now")
**Builder:** Opus builder subagents; the main session reviews and merges
**Operator sign-off on waivers:** pending. One waiver, in §3: no mobile evidence,
because this phase ships no client change.

Design: [prd.md](prd.md), [hld.md](hld.md), [lld.md](lld.md). This scope covers the
server only: schema, `backend/league_pass.py`, the gate, the routes and the operator
routes. The client, the store products and the legal copy are phase 2.

---

## 1. Analytics scope

- [x] **(a) New events specced.** All four are emitted by the server.

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `league_pass_quote_viewed` | `tier`, `platform`, `teams` | An intent is created | server |
  | `league_pass_bound` | `origin`, `tier`, `platform`, `via` | A pass row is inserted | server |
  | `league_pass_ended` | `reason` | A pass stops being live | server |
  | `league_pass_coverage_used` | `family` | A gated request is allowed by a pass; first per user, league and day | server |

  → registered in `backend/analytics_taxonomy.py` and classified in
  `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitters.

## 2. Schema & flag scope

- New tables: `league_passes`, `league_pass_intents`. New column:
  `leagues.previous_league_id` → `docs/data-dictionary.md` + `migration_cols`.
- New feature flag: `monetize.league_pass`, default off. Graduation: phase 3 of the
  PRD rollout (allow-list, then everyone) → `config/features.json`,
  `backend/feature_flags.py`, `backend/tests/fixtures/flags/release.json`,
  `docs/config-reference.md`.
- New `model_config` keys: `league_pass_repoint_cooldown_days` (30),
  `league_pass_seat_allowance` (2), `league_pass_intent_ttl_minutes` (60). The league
  allow-list is not a float, so its storage is settled in the build (LLD §1).
  Rollback lever: turn `monetize.league_pass` off; the gate and the entitlements
  response return to today's behaviour with no deploy.
- New billing source `league_pass_iap` in `entitlements.py`.

## 3. Evidence scope

- [x] **Unit tests:** `test_league_pass_coverage.py`, `test_league_pass_bind.py`,
      `test_league_pass_tiers.py`, `test_paywall_league_resolvers.py`,
      `test_paywall_gate_pass.py`; updates to `test_paywall_gate_allowlist.py` and
      `test_entitlements.py` (LLD §11).
- [x] **Structural guard, TestFlight checklist — WAIVED because:** backend-only and
      dark. No client reads the new fields and no route is reachable with the flag off.
      Both return in phase 2 with the client.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `/api/league-pass/*`, the admin routes, the `league_passes` field |
| `living-memory/LLD.md` | updated | Derived coverage; the league-match check on gated handlers |
| `docs/architecture.md` | updated | `league_pass.py` wiring |
| `living-memory/HLD.md` | updated | New module |
| `docs/cross-client-invariants.md` | n/a | No client reads the new values in this phase |
| `docs/glossary.md` | updated | League pass, covered member, bind, re-point |
| ADR or `DECISIONS.md` entry | updated | Hybrid coverage; derived, not stored |

Also `docs/data-dictionary.md` and `docs/config-reference.md` (§2).

## 5. Ship gate declaration

- **CI green:** `backend-tests` on the pushed sha. No mobile change.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-22: 16,098 passed, 0 failed.
- Express lane declared by the operator? No.
