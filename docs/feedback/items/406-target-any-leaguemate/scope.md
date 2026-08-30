# Feature Scope — FB-406: "Any league mate" partner scope on the merged calculator

**Date:** 2026-08-30
**Entry point:** feedback #406 (polish; batch plan [plan.md](plan.md), G-406; serialized behind #407)
**Builder:** Author agent 2026-08-30 (this scope + [prd.md](prd.md)); build agent to follow
**Operator sign-off on waivers:** not yet surfaced — waivers below are author-proposed; surface before build

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new events, no renames, no property changes:
  - `calc_find_a_trade_tapped {path, give_count, receive_count, has_partner}`
    (`mobile/src/utils/canvasSearch.ts:52-61`): `has_partner: false` is the unscoped-run
    signal and already fires for the post-#407 untouched default. Under an explicit
    "Anyone" the same `false` fires. **Honest limitation, stated plainly:** the event
    cannot distinguish explicit-Anyone from default-unchosen. Measuring adoption of the
    Anyone row would need a new property (e.g. `partner_scope`) — that is a
    taxonomy change (CLAUDE.md bright line) and is **deliberately out of scope**; noted
    in the PRD's out-of-scope list for the operator to rule in later if wanted.
  - `find_trades_tapped {source:'calculator', mode}` — unchanged, fires on the sweep
    as today.
  - No semantics of any registered event change: `has_partner` already means "the
    payload carried a partner", which stays exactly true.

## 2. Schema & flag scope

- New/changed tables or columns: **none** — client-only; no `docs/data-dictionary.md` change.
- New/changed feature flags: **none** — the Anyone row lives inside the existing
  `calc.merged_layout` surface (sheet renders only in the merged branch) and dies with
  it; rollback lever = ship revert of the three production files
  (`InLeagueCalculator.tsx` + R-10's marker lines in `TradesScreen.tsx` /
  `TradeBuildCanvas.tsx`) together with the 20a re-spec in
  `mobile/tests/check-calc-merged-behavior.js` (reverts as a pair with the
  initializer, critic B-4). The planner
  considered and rejected a dedicated flag ([plan-g406.md](plan-g406.md) §5
  Alternatives); the author concurs — a flag would add a key + docs + guard forever
  for one picker row. Re-raise only if the operator wants independent kill.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

*(The template's former §Maestro delta is retired per D-056 — no flow authoring, no
flow execution, no `screens/` captures; nothing to declare.)*

- [x] **Structural guard:** NEW `mobile/tests/check-any-partner.js` + `npm run
  test:any-partner` — 15 assertions (A-1…A-15, incl. A-11b) pinning: the Anyone
  row and its three-write tap handler; the member-row reset (A-13, critic B-3);
  the guarded default-to-first effect; the intact FB-407 payload gate; the
  verbatim ✓ disabled expression; the partner-gated `evalQ` `enabled` and the
  exactly-once `evalQ.data` derivation (closes the `placeholderData`
  stale-verdict leak; N-2 form); the no-sentinel rule (component +
  `canvasSearch.ts` type; best-effort, N-6); the honest dropdown/a11y branches;
  the scope-note **exact predicate text** (critic B-2 — token presence is not
  enough); the ref↔state mirror adjacency (±3 lines) + initializer equality
  (N-1); and the receive-add redirect + hint. R-10 adds A-14/A-15 over
  `TradesScreen.tsx` + `TradeBuildCanvas.tsx` (seed marker + seed-negated
  initializers). Full table with a **named, non-self-satisfying sabotage per
  assertion** in [prd.md](prd.md) §E-1; every sabotage cycle run red→green and
  logged in TEST_LEDGER. Dependency-free, plain node, per
  `mobile/tests/README.md` convention. **These suites do NOT run in CI** (N-3) —
  the build agent runs the full `mobile/tests` set explicitly pre-push.
  **Declared edit to an existing suite (critic B-4):** R-10's initializer turns
  FB-407's `check-calc-merged-behavior.js` assertion 20a red — the build updates
  20a's pinned declaration to the twin-initializer form (+ hint text), nothing
  else in that suite (20b…20d verified unaffected); see prd.md R-10.
- [x] **Unit tests:** none new — backend diff is zero; the unscoped sweep is already
  covered by `backend/tests/test_fair_packages.py:15`/`:203`. Full
  `pytest backend/tests` green remains the regression floor.
- [x] **Code-walk proof:** 13-hop file:line-cited outline in [prd.md](prd.md) §E-3
  (Anyone tap → null payload → unscoped wire → all-members sweep; scoped
  counter-case; browse-session seeding + R-10 Clear-after-browse trace; NB-1
  zero-results remount trace). Build agent executes it against the shipped sha
  and logs it in TEST_LEDGER.
- [x] **Manual TestFlight checklist:** 7 steps in [prd.md](prd.md) §E-4, written
  against the shipping `calc.canvas_results`-LIT browse-session UI (pager-based
  counterparty verification, critic B-1): honest default note, Anyone unscoped
  sweep with mixed counterparties by paging, scoped counter-case, pre-search
  no-stale-verdict check, reversibility loop, R-10 Clear-after-browse sentinel,
  browse-lock regression. Runtime proof matters: search scope and stale-verdict
  absence are runtime behaviors the guard pins only textually — and no `screens/`
  capture covers the merged surface (frozen 2026-08-11, predates it; stated in
  the PRD).
- `testID`s added/renamed: **added** `calc.team-sheet.any`,
  `calc.search-scope-note`, `calc.receive-any-hint` (all static literals — no
  `testid-lint-allow.txt` entries needed); none renamed/removed.
  `mobile/scripts/testid-lint.sh` must stay green.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/contract-changed — the client starts *using* the already-documented omitted-`opponent_user_id` form of `/api/trades/fair-packages` and `/api/trades/generate`; the fair-packages row already reads "or from every league-mate's when no partner is named" |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shift; the partner-scope convention refinement is a DECISIONS.md entry (row below), continuing the FB-407 entry |
| `docs/architecture.md` | n/a | no module wiring or data-flow change — same components, same call chain, same choke points |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors; "Anyone" is mobile-only copy, not a cross-client enum (the wire form is *absence* of `opponent_user_id`) |
| `docs/glossary.md` | n/a | no new domain term — "unscoped/league-wide sweep" already exists in the fair-packages docs; "Anyone" is a UI label |
| ADR or `DECISIONS.md` entry | **update at ship** | one DECISIONS.md entry extending FB-407's: "the merged canvas partner has three states — chosen (scopes), auto-default (never scopes, labeled honestly), and explicit Anyone (unscoped by choice, reversible); unscoped is boolean state + null id, never a sentinel; a browse-session **seed prefill never counts as chosen** (R-10 — in-session scoping rides the receive-side clause instead), closing FB-407's known limitation" |
| **Beyond the template** — `mobile/src/components/CLAUDE.md` (InLeagueCalculator row) | **update at ship** | the row documents the Team sheet/dropdown contract; add the Anyone state + scope note + receive-add redirect ([plan-g406.md](plan-g406.md) §8 names this file) |
| **Beyond the template** — `docs/design/components.md` | **update at ship** | new constructions on a specced surface: the Anyone sheet row, the scope-truth note, the receive hint (Chalkline: chalk-dim hints, ice active state, no icons) |

## 5. Ship gate declaration

*(The template's former §Simulator-gate tier matrix is retired per D-056 — no tier
to declare, no `qa/sim-runs/last-sim-run.json`; `FTF_SKIP_SIM_GATE=1` is the
standing pre-push posture, noting the evidence above ran instead.)*

- **CI green:** `backend-tests` + `mobile-typecheck` (bare `tsc --noEmit`) +
  `maestro-testid-lint` — all passing on the pushed sha. **CI does not run the
  `check-*.js` suites** (N-3; root CLAUDE.md §Stack — `npm run`-only, gating
  nothing yet): the build agent runs the full `mobile/tests` set explicitly
  before push and records the run in TEST_LEDGER.
- **Evidence recorded:** TEST_LEDGER entry naming the new `check-any-partner.js`
  (with all sabotage cycles, A-1…A-15), the explicit full `mobile/tests` run, the
  executed code-walk proof, and the pending 7-step TestFlight checklist.
- **TestFlight verification:** operator runs [prd.md](prd.md) §E-4; outcome logged
  in TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates ([plan-g406.md](plan-g406.md)
  §4: no express declared; no schema/API/flag/analytics surface touched, so no
  bright-line confirmation needed either).
