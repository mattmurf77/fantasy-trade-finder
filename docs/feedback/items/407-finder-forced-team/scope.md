# Feature Scope — FB-407: Find a Trade forces the calculator's auto-defaulted team (bug fix)

**Date:** 2026-08-30
**Entry point:** feedback #407 (fast-track bug; batch plan `../406-target-any-leaguemate/plan.md`, G-407)
**Builder:** Planner agent 2026-08-30 (this scope); build agent to follow
**Operator sign-off on waivers:** not yet surfaced — waivers below are planner-proposed; surface before build

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this is a client-side bug fix with no
  new user action or moment to measure; the existing `calc_find_a_trade_tapped` event and its
  registered `has_partner` prop (`mobile/src/utils/canvasSearch.ts:59`) already cover the surface
  and become *more* accurate under the fix (false when the partner was only the auto-default).
  `find_trades_tapped` (source `calculator`) is likewise unchanged. No event added, removed,
  renamed, or re-propertied.

## 2. Schema & flag scope

- New/changed tables or columns: **none** — client-only fix; no `docs/data-dictionary.md` change.
- New/changed feature flags: **none** — the fix lives inside behavior already gated by the
  existing `calc.merged_layout` / `calc.inline_home` / `calc.canvas_results` /
  `trades.sheet_targeting` flags; no default flips, no new keys. Rollback lever = ship revert
  (single-file change), not a flag.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [x] **Structural guard:** extend `mobile/tests/check-calc-merged-behavior.js` (the suite already
  pinning the `onFindATrade` contract for this surface) — pins: (1) the default-opponent effect
  never marks the partner as chosen; (2) both user-tap `setOpponentId` sites mark it chosen;
  (3) the find-a-trade payload gates `opponent` on `opponentChosenRef.current || receiveIds.length > 0`.
  Each assertion sabotage-verified red→green. Runs under plain node via the existing
  `npm run` wiring for that suite (no new script needed unless a new file is chosen instead).
- [ ] **Unit tests:** none — no backend change; the server's `opponent_user_id` handling is
  untouched and already covered.
- [x] **Code-walk proof:** outline in `mini-prd.md` §"Code-walk proof outline" — 7-hop
  file:line-cited trace (default → payload null → fork → `setSheetOpponent(null)` →
  `opponent_user_id: undefined` → all-teams sweep; plus the explicit-pick counter-case and the
  remount-loop check). Build agent executes it against the fixed sha and logs it in TEST_LEDGER.
- [x] **Manual TestFlight checklist:** `mini-prd.md` §"Manual TestFlight checklist" — 5 steps
  (fresh unscoped search, dropdown not hijacked, explicit pick still scopes, built trade still
  addressed, fresh-session sentinel). Runtime proof matters here: the bug is a runtime search-scope
  defect the structural guard can only pin textually.
- `testID`s added/renamed: **none** (existing `calc.action.find-a-trade`, `calc.team-dropdown`
  untouched); `mobile/scripts/testid-lint.sh` stays green by construction.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed; `/api/trades/generate` and `/api/trades/fair-packages` contracts unchanged (`opponent_user_id` was already optional — the client just stops sending it when unchosen) |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifts; the D-153 "canvas Team dropdown is the search scope" convention is refined, not replaced — recorded in DECISIONS.md instead (row below) |
| `docs/architecture.md` | n/a | no module wiring or data-flow change; same components, same call chain |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors touched |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | **update at ship** | one DECISIONS.md entry: "a partner counts as the search scope only when chosen (tap, prefill, or receive-side assets) — the calculator's auto-default never scopes a search"; non-obvious because it deliberately narrows the #384 checklist-23 reading |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (`tsc --noEmit`) + `maestro-testid-lint`
  required on the pushed sha before merge.
- **Evidence recorded:** TEST_LEDGER entry naming the extended check suite (with sabotage
  cycles), the executed code-walk proof, and the pending TestFlight checklist.
- **TestFlight verification:** operator runs the 5-step checklist in `mini-prd.md`; outcome
  logged in TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates (fast-track affects rigor of
  process cadence, not the gate set; no schema/API/flag/analytics surface is touched, so no
  bright-line confirmation needed).
