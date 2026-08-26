# QA round 1 — agent A — 2026-08-24

## Summary: PASS (1 finding, minor)

Group F (#346/#381) — QuickSet HOLD contract. T-1…T-7 all present and green on a fresh
data dir; the old-code sabotage (both backend files from `e5759628`) reproduced the exact
6-red/T-4-green split the build report claims; every mobile guard sabotage reproduced;
cross-platform payload shape verified mobile↔backend. One minor test-design observation
on T-2's response-shape pin (F-1).

## Environment

- Commit: `c8b0e224`, branch `claude/new-user-feedback-55320e`, clean tree.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`; `backend/__pycache__` cleared after
  every python sabotage/restore; `data/trade_finder.db*` removed before the full sweep.

## Results

| Test | Result | Evidence |
|---|---|---|
| T-1…T-7 on merged tree | PASS | `test_quickset_demote.py` 7/7 green (within targeted 82-pass run of the three touched suites) |
| Touched suites: `test_override_pin_unpin.py`, `test_rookie_scope.py` | PASS | 82 passed total |
| `test_pin_tier_bounded.py` untouched + green (R-5) | PASS | green in the full sweep; goldens still read `RankingService.DEMOTED_ELO` (`:113,214,407`) |
| Sabotage: old code (`server.py`+`ranking_service.py` from `e5759628`) | PASS (RED as mapped) | T-1, T-2, T-3, T-5, T-6, T-7 red; **T-4 green** — exactly the split the PRD specifies (T-4 is a survives-affordance pin) |
| Sabotage: skip `waivers` tier in `apply_tiers` | PASS (RED as mapped) | T-4 red (KeyError, no override written) |
| Sabotage: echo key on the response (conditional on `demoted_pids` in body) | PASS (RED as mapped) | T-2 red — see F-1 for the unconditional variant |
| Mobile sabotage: re-add `demoted` to the mutate payload | PASS (RED as mapped) | A1a + A1c red |
| Mobile sabotage: delete `mutate({ ids, cleared })` (O-5 vacuity probe) | PASS (RED as mapped) | A1c red alone — the positive anchor works |
| Mobile sabotage: re-add `demoted_pids: []` to the POST body | PASS (RED as mapped) | A2e red |
| Mobile sabotage: named `demoted` local at a TiersScreen call site | PASS (RED as mapped) | A3a red |
| `check-quickset-hold.js` on merged tree | PASS | 13/13 |
| R-2/R-3 route contract | PASS | `save_tiers_route` (`server.py:8703`) parses only `position`/`tiers`/`cleared_pids` (+`scope`/`via`/`duration_ms`/`skipped` for routing/analytics); guard reverted to `total_assigned == 0 and not cleared_pids` (`:8738`); docstring states the D-160 back-compat contract |
| CW-4: no `_pin(…, DEMOTED_ELO)` caller remains | PASS | `git grep "_pin(.*DEMOTED_ELO" backend/ranking_service.py` → 0 hits; anchor path pins via `server.py:1319` `ANCHOR_NO_VALUE_ELO` |
| Removal proof | PASS | `git grep demoted_pids backend/ mobile/src/` → route docstring back-compat note + tests only; zero hits under `mobile/src/` |
| **Cross-platform consistency (mobile payload ↔ backend parse)** | PASS | mobile `saveTiers` body is exactly `{position, tiers, cleared_pids}` + conditional `scope`/`via` (`rankings.ts:342-348`); backend reads exactly those names with the same semantics (`server.py:8724-8743`, via-whitelist `:8841-8844`); no key sent that the server drops silently except by design (none), none read that mobile doesn't send except the optional `duration_ms`/`skipped` analytics riders old callers may omit |
| R-9 docs | PASS | `api-reference.md` `/api/tiers/save` row drops `demoted_pids` from the Body listing; D-160 present at `living-memory/DECISIONS.md:1496` with the O-1 rollback caveat; SUPERSEDED note atop `161-quickset-demote/status.md:3` |
| `tsc --noEmit` / testid-lint / full 78-guard sweep | PASS | all green |

## Findings

- **F-1 (minor, test design — do not fix, report only).** T-2
  (`test_demoted_pids_key_is_ignored`) pins "the response is byte-identical to a request
  without the key" by comparing the two responses' key sets. I first applied the echo
  sabotage as an **unconditional** new response key (added to every response) — T-2
  **stayed green**, because both compared responses gain the key symmetrically. Re-applied
  **conditionally** on `demoted_pids` being present in the body (the realistic
  echo-implementation shape, and evidently what the build agent ran), T-2 goes red as
  logged. Repro: add `{"demoted_pids_ignored": True}` to the `save_tiers_route` response
  unconditionally → `pytest backend/tests/test_quickset_demote.py::test_demoted_pids_key_is_ignored`
  passes; make it conditional on `"demoted_pids" in body` → fails. Expected (PRD R-3): the
  test guards the *conditional* leak, which it does; an unconditional response-shape change
  is ordinary API evolution and arguably out of T-2's scope — but the build report's
  sabotage row ("`demoted_pids_ignored` key added to the response → red") is only true for
  the conditional form. Severity minor: no code defect, the shipped contract holds.

## TestFlight checklist (operator-run) — verified as executable, refined

Code-side references confirmed: the walk's tier ladder includes `waivers` as the final
rung, chip label "FA" (`mobile/src/utils/tierBands.ts:35,50`); the clear-only branch
(`ids.length === 0`) exists, which is why step 5's ≥2-player requirement is load-bearing.

1. Rank tab → Quick set → WR, format as in your league. On **4+ 1sts**: confirm Nabers'
   chip shows "4+ 1STS". Select 3 other WRs — **not** Nabers. Save.
2. On **3 1sts**: Nabers is still near the **top** of the grid, chip still "4+ 1STS" —
   not FA, not missing. *(Old behavior: bottom of the ~200-player list as FA — this step
   alone catches the regression.)*
3. Tap Nabers + Save → back on the Tiers board: the 3 WRs in 4+ 1sts, Nabers in 3 1sts,
   nobody new in FA.
4. Explicit demote still works: walk to the **FA** rung, select a currently-tiered depth
   player, Save → Tiers board shows him in FA.
5. Revisit path — **must use a rung where you placed two or more players this run**:
   deselect one, keep the rest selected, Save → the deselected player returns to his
   consensus-suggested tier chip, not FA. *(Deselecting a rung's only player takes the
   clear-only branch, which never demoted even on old code — only the ≥2 path exercises
   the reversed demote-beats-clear case, matching T-3.)*
6. #346 angle: on the **1 1st** rung, select only some of the preseeded 1-1st players and
   Save → the unselected ones still read "1 1ST" on the next rung.
7. Cleanup: re-place any player the old behavior FA'd (Nabers included — the fix does not
   retro-repair historical 1100-pins; they are indistinguishable from anchor "no value").
