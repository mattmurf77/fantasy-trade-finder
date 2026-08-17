# Feature Scope — G2: Mock draft room UI (#322–#327)

**Date:** 2026-08-16
**Entry point:** feedback #322/#323/#324/#325/#326/#327 (2026-08-16 wave, group G2)
**Builder:** G2 author agent (Phase 1); build agent TBD (Phase 2)
**Operator sign-off on waivers:** REQUIRED — see §1 (proposed new analytics events) and the D-056-backed n/a rows in §3/§5

---

## 1. Analytics scope

- [x] **(a) New events specced** — the existing mock family
  (`mock_started`, `mock_pick_made`, `mock_completed`, `mock_abandoned`,
  `mock_create_refused` — `backend/analytics_taxonomy.py:265`) covers draft
  lifecycle but says nothing about the three new affordances. Proposed,
  following the family's registration-first convention
  (`analytics_taxonomy.py:254` — registration commit ordered first) and its
  low-cardinality prop style (`:855–:862`):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `mock_team_sheet_opened` | `platform`, `mode`, `round`, `pick_no` | "Your team" link tapped (sheet opens) | mobile |
  | `mock_pool_filtered` | `platform`, `mode`, `position` | A non-All position chip is selected | mobile |
  | `mock_pool_searched` | `platform`, `mode`, `filter_position` | Once per turn, on the first non-empty query (never per keystroke; the query string is NOT sent) | mobile |

  → follow-through: `backend/analytics_taxonomy.py` registration +
  props-map entries; no `docs/data-dictionary.md` change (events ride the
  existing `user_events` pipe; no new storage). **Operator note:** new
  analytics events are a bright-line surface — these three are a proposal
  from this scope, not an operator decision from the batch chat. A "drop
  them" answer downgrades this section to (c) waived and removes PRD R-15 /
  T-S8; nothing else in G2 depends on them.
- [ ] (b) Existing events cover it — no (see above).
- [ ] (c) WAIVED — n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none** — the `tier` key is computed at
  payload-build time from the in-process consensus map; nothing is stored.
  `docs/data-dictionary.md`: no change.
- New/changed feature flags: **none.** The mock room already ships behind
  `draft.mock`; G2 changes render inside it and inherit that kill switch.
- New env vars / `model_config` keys: **none.** Rollback lever: the changes
  are UI + one additive nullable payload key — revert = revert the merge;
  old clients ignore the key, new clients render no badge when it is absent,
  so backend and mobile can roll independently.

## 3. Test scope (mobile test platform)

- [ ] New flow / [ ] Extended flow — **n/a per D-056** (Maestro/simulator
  retired entirely, `living-memory/DECISIONS.md` D-056, 2026-08-15).
  Replacement evidence per the batch plan QA regime: structural
  `check-mock-g2-ui.js` (10 assertions, PRD §5.3), transpile-and-call unit
  tests (PRD §5.2), pytest (PRD §5.1), and the operator TestFlight checklist
  (PRD §5.5).
- [x] **WAIVED (Maestro only) because:** D-056 — cite above. Not an
  agent-selected skip: decision-backed, and the TestFlight checklist is the
  runtime proof.
- `testID`s added: `mock-draft.view-team`, `mock-draft.team-sheet`,
  `mock-draft.pos-filter.all|qb|rb|wr|te`, `mock-draft.pool-search` — must
  pass `mobile/scripts/testid-lint.sh`. None renamed/removed.
- **Capture delta:** n/a per D-056 — `screen-capture.sh` drives the retired
  simulator harness. Visual evidence = operator TestFlight pass (PRD §5.5),
  screenshots attached to this folder's `status.md` if taken.
- Smoke-suite impact: n/a per D-056 (the 11 smoke flows are Maestro flows);
  the four existing mock structural suites + `testid-lint` + `tsc` must stay
  green (PRD §5.4).
- Backend pytest: `backend/tests/test_mock_draft.py` — four additions
  (T-P1…T-P4, PRD §5.1), each with a named sabotage.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (at build) | § Mock draft state payload — add the `picks[].tier` / `my_picks[].tier` field row per PRD §2 (no route added/renamed; contract-changed additively). Shared block with G3's `ownership_source` rows — G2 lands second per PRD §3 serialization |
| `living-memory/LLD.md` | n/a | No convention shift: additive nullable payload key under the existing plan-D10 open-payload convention; server-computed tier follows the standing #263/#277/#278 rule |
| `docs/architecture.md` | **updated** (at build) | § module table, `mock_draft_service.py` row — one-line amendment: `state_payload` labels picks via `RankingService.tier_for_elo` (new import; pure classmethod over checked-in `tier_config.json`, loaded at module import — "zero platform egress after creation" unchanged). The row currently says the module "imports no HTTP client and performs no I/O at all", which stays true at runtime; the amendment keeps it honest |
| `living-memory/HLD.md` | n/a | No architecture shift: no new module, client, or major flow — one new intra-backend import edge, covered by the architecture.md line above |
| `docs/cross-client-invariants.md` | **updated** (at build) | § Tier enum "Locations" list — add `picks[].tier` (mock-draft payload) as an enum consumer. The rendering rule itself (server-computed key, client maps through `TIER_LABEL`/`TierBadge`, null ⇒ hidden) is already stated and unchanged — verified: `TierBadge` no-ops on falsy tier and the invariants doc already pins the null-tier answer (`tier: null` ⇒ no badge). Also shared with G3 (`ownership_source` vocabulary) — G2 lands second per PRD §3 |
| `docs/glossary.md` | n/a | No new domain term — "tier", "mock draft", "on the clock", "ticker" all pre-exist; the team sheet reuses existing vocabulary |
| ADR or `DECISIONS.md` entry | n/a | No non-obvious choice beyond what operator decisions already fixed (sheet-not-navigation, reset-per-turn, search-scopes-to-filter, 8-rung ladder — all recorded in the batch plan § G2). The 3-per-row grid is a Chalkline-precedent application (components.md § Tier bins, #140), not a new pattern |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a per **D-056** (Maestro/simulator retired,
  2026-08-15) — the runbook matrix's tiers are all simulator runs.
  Replacement gate per the batch plan: `check-mock-g2-ui.js` + the four
  existing mock structural suites + `testid-lint` + `tsc` + pytest green in
  CI, plus the operator TestFlight checklist (PRD §5.5) before ship
  sign-off.
- Evidence: `living-memory/TEST_LEDGER.md` entry after the suite run;
  `qa/sim-runs/last-sim-run.json` n/a per D-056 (no sim run exists to
  record).
- Operator deviation from the matrix: none beyond D-056 itself, which is
  the operator's standing decision, not a per-feature deviation.
