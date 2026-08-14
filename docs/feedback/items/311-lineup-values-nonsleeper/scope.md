# Feature Scope — 2026-08-13 backend wave: #311 lineup templates + #318 awaiting-dismiss (backend half)

<!-- Lowest-ID convention: this folder also carries the wave plan
     (plan-2026-08-13.md) and #318's backend half. #313 is NOT in this
     scope — it awaits an operator decision and was excluded from the
     build brief. Shared docs are orchestrator-owned this wave; this
     block records what THIS group did and the proposed row text lives
     in status-backend-2026-08-13.md. -->

**Date:** 2026-08-13
**Entry point:** feedback #311 + #318 (2026-08-13 wave, backend group)
**Builder:** wave-backend build agent (worktree `wave-backend`, base `origin/main` @ `60fccc7`)
**Operator sign-off on waivers:** pending — waivers listed below are surfaced via the orchestrator before ship

---

## 1. Analytics scope

- **#311 → (c) WAIVED — no analytics needed because:** no new user action
  exists; the change is a server field (`starter_impact`) appearing where it
  was previously omitted. The success signal is the existing
  `lineup_impact_unavailable` client event (props `{platform}`) dropping
  toward zero for `platform in ('espn','mfl')` after ship — a new event
  would be a second encoding of the same fact. (Plan #311 §Analytics,
  waived in writing there and here.)
- **#318 → (a) New event specced** (registered in `analytics_taxonomy.py`
  `SERVER_FIRED_EVENTS`, registration-only commit; INTENT by default —
  deliberately NOT added to `analytics_queries.NON_INTENT_EVENTS`):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `awaiting_trade_dismissed` | `partner_id`, `dismissed_likes` (league_id rides the envelope column, never a prop; no platform prop — source `api`) | `POST /api/trades/awaiting/dismiss` returns ok with `dismissed_likes >= 1` (a 0-row idempotent repeat fires nothing — no phantom intent) | SERVER-fired only; the mobile client fires nothing (one event, one source of truth; `trade_match` precedent) |

  → follow-through: tracking-plan addendum placement is orchestrator-owned
  (taxonomy docstring demand); props documented in place at the
  registration site.

## 2. Schema & flag scope

- New/changed tables or columns: `trade_decisions.retracted_at` (String,
  nullable, ISO UTC; NULL = live like). Additive boot-migration row
  (`("trade_decisions", "retracted_at", "VARCHAR")` in `_migrate_db`);
  existing rows read NULL, which is the correct backfill — no backfill pass
  needed. Verified against an old-schema SQLite DB: column added, existing
  row NULL, re-run idempotent. → `docs/data-dictionary.md` row text
  proposed in status-backend-2026-08-13.md (orchestrator applies).
- New/changed feature flags: none.
- New env vars / `model_config` keys: none. (#313's knobs are NOT built —
  out of this scope.)

## 3. Test scope (mobile test platform)

- **#311 → WAIVED because:** the change is mobile-visible only for users
  with linked ESPN/MFL/Fleaflicker leagues, and the hermetic Maestro
  harness seeds Sleeper leagues only — there is no hermetic platform-league
  fixture today. Covered by backend tests (plan tests 1-6, all
  sabotage-proven) in `backend/tests/test_trade_evaluate.py`. Operator to
  accept this waiver or direct a fixture build (plan #311 §Docs rows).
- **#318 → owned by the Matches mobile group:** the dismiss CTA's Maestro
  flow ships with the mobile half; the backend waives nothing and freezes
  the route contract the flow exercises.
- `testID`s added/renamed: none (no client files touched by this group).
- **Capture delta:** none — no visual change ships from this group.
- Smoke-suite impact: none of the 11 smoke flows POST the new route or
  depend on platform-league starter impact; Sleeper-path template
  resolution is byte-identical (sabotage-proven).
- Backend: pytest files added/updated:
  `backend/tests/test_trade_evaluate.py` (7 new #311 tests + 2 re-seamed
  monkeypatches), `backend/tests/test_awaiting_dismiss.py` (new, 14 tests),
  `backend/tests/test_trade_match_flow.py` (2 receiver-side filter tests).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

<!-- Shared docs are orchestrator-owned this wave; "proposed" = exact row
     text ready in status-backend-2026-08-13.md. -->

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **proposed** (orchestrator applies) | New route block `POST /api/trades/awaiting/dismiss` (frozen contract verbatim) + `starter_impact` availability note change |
| `living-memory/LLD.md` | n/a | no schema/route *convention* shifted — nullable-marker dismissal follows the existing `notifications.dismissed_at` shape |
| `docs/architecture.md` | n/a | no module wiring or data-flow change (one helper, one route, three query filters) |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared enum/threshold change — slot keys unchanged; #318 response strings are route-local (plan) |
| `docs/glossary.md` | **proposed** (orchestrator applies) | "Standard lineup template" (#311) + "Retracted like" (#318) |
| ADR or `DECISIONS.md` entry | n/a | both designs follow the committed plan; no choice was made beyond it (the two plan-recommended scope calls — include fleaflicker, defer power-rankings call site — were fixed by the build brief) |

## 5. Ship gate declaration

- **Simulator-gate tier:** backend-only diff from this group; the wave's
  mobile groups ship the user-visible halves. Proposed: this group's changes
  ride the WAVE's sim run (tier per the orchestrator's matrix call for the
  combined ship) — no standalone sim run from a backend-only branch.
- Evidence: wave TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` at the
  orchestrator's merge; this group's pytest evidence is in
  status-backend-2026-08-13.md (baseline 2714 passed/1 skipped → final, all
  15 sabotages RED-then-green with clean-diff guards).
- Operator deviation from the matrix (if any) and why: none requested.
