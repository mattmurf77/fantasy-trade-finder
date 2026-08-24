# FB-346 + FB-381 — QuickSet tier drop (Group F canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #346 (jonbonjourvi, 1.13.4), #381 (mattmurf77, 1.15.0 — detailed repro)
- **Path:** fast-track bug, full gates
- Batch plan: [plan.md](plan.md) (this folder is also the batch home — lowest selected id)
- Group F plan: [plan-group-f.md](plan-group-f.md) · PRD: [prd.md](prd.md) · Scope: [scope.md](scope.md)
- Verdict: the #161 demote rule (commit `a8898a7`, v1.10.0) is the cause; the
  operator's #381 ruling supersedes it → contract is **HOLD** (saves touch
  only selected players). Fix is backend + mobile; decision records as D-160.

Repro (#381): player set tier "4+ 1sts"; operator saves that tier having
selected 3 other WRs; on moving to the "3+ 1sts" screen the unselected player
has been silently reset to FA instead of staying at 4+ (preferred) or stepping
to 3+. #346 is the same defect class reported earlier: preselected values drop
to zero rather than the next tier. "This is new behavior that is broken."

## Backend build report (2026-08-24, branch `feat/fb346-quickset-hold-backend`)

**Status: backend half BUILT** (R-2/R-3/R-4/R-5 + the backend rows of R-8/R-9).
Mobile half (R-1/R-6/R-7, `check-quickset-hold.js`) is a separate agent.

- `backend/server.py` `save_tiers_route`: `demoted_pids` parse deleted (the
  key is now an ignored unknown body key), emptiness guard reverted to
  `total_assigned == 0 and not cleared_pids` (line 8732), both `apply_tiers*`
  kwargs dropped, docstring rewritten to the HOLD contract.
- `backend/ranking_service.py`: `apply_tiers` / `apply_tiers_subset` lose the
  `demoted_pids` param, pin loops, and docstring sections; `DEMOTED_ELO`
  (1785) kept and re-commented as the anchor-no-value/unranked pin value; the
  D-085 frozen-populations bullet (~549-560) reworded per O-2 — rule kept in
  force, #161 clause moved to past tense.
- `backend/tests/test_quickset_demote.py` rewritten to T-1…T-7 (7 tests);
  `test_override_pin_unpin.py` parametrize entry updated;
  `test_rookie_scope.py::test_m2_08` rewritten in place to the scoped hold
  contract (unshown-vet assertion kept verbatim); `test_m2_08b`/`test_m2_09*`
  untouched. `test_pin_tier_bounded.py` green **untouched** (R-5).
- Docs: `docs/api-reference.md` `/api/tiers/save` row rewritten with scope.md
  §4's exact wording (Body listing drops `demoted_pids`; scoped clause (2)
  trimmed to `cleared_pids`); D-160 appended to `living-memory/DECISIONS.md`
  (verified next free id); superseded note added to `../161-quickset-demote/
  status.md`. `living-memory/LLD.md` one-liner + CHANGELOG/TEST_LEDGER are
  ship-commit items for the orchestrator (LLD.md not in this group's backend
  ownership split).

**Gate results (D-056 static evidence):**

- Targeted: `test_quickset_demote.py` + `test_override_pin_unpin.py` +
  `test_rookie_scope.py` — 82 passed.
- Full sweep: `python3 -m pytest backend/tests -q -x` — **4232 passed,
  1 skipped** (5m11s), includes the blast-radius modules (threshold/unlock,
  cross-format derive, D-085 goldens, trends writers).
- Sabotage-red proof (committed first, then sabotaged, then restored +
  `__pycache__` cleared, re-green 7/7):
  - Old code (`server.py`+`ranking_service.py` from `e5759628`) → T-1 red
    (`assert 1100.0 == 1950.0`), T-2 red (`assert 1100.0 == 1500.0`), T-3 red
    (`'jamo' in {'jamo': 1100.0, …}` — demote-beats-clear), T-5 red
    (`assert 1100.0 == 1480.0`), T-6 red (200 == 400; response showed
    `saved:["WR"]` — the old demote-only body marked the position saved while
    writing nothing), T-7 red (`DID NOT RAISE TypeError`). T-4 green, as
    specified (survives-affordance pin).
  - T-4 sabotage (skip the `waivers` tier in `apply_tiers`) → red
    (`KeyError: 'mid'`, no override written).
  - T-2 echo sabotage (`demoted_pids_ignored` key added to the response) →
    red (`Extra items in the left set: 'demoted_pids_ignored'`).
- Route smoke (live Flask on a scratch sqlite DB, port 5099, demo session):
  old-binary payload (3 WRs into `firsts_4plus` + `demoted_pids=[top WR]`) →
  200, response keys exactly `{ok, position, saved, all_done, count,
  scoring_format}` (no echo), passed-over player's elo byte-unchanged
  (1927.3 → 1927.3, tier `firsts_4plus` held; old code → 1100/unranked),
  assigned trio landed in-band. Server killed after; no operator data touched.

## Code-walk proof — backend half (CW-4, CW-5)

CW-1…CW-3 (mobile) are the mobile agent's half.

- **CW-4 — the route never reads `demoted_pids`.** `save_tiers_route`
  (`backend/server.py:8697`) parses `position`, `tiers`, `cleared_pids`
  (8714–8723) and nothing else from the mutation surface; `scope`/`via` are
  read for routing/analytics only. The guard at 8732 is
  `total_assigned == 0 and not cleared_pids`. The two service calls
  (8752–8759 scoped, 8765–8770 unscoped) pass `position/tiers/scoring_format/
  cleared_pids` (+`scope_pids`) only. `git grep demoted_pids backend/` hits
  only the route docstring's back-compat note (server.py:8708) and the tests
  that pin the ignore contract. In `ranking_service.py` no caller of
  `_pin(…, DEMOTED_ELO)` remains — the remaining `_pin` sites (1836/1839
  band spread, 1961 subset merge, 1982 anchor, 2050/2096 anchor/value paths)
  all pin band or anchor values; the anchor no-value path pins via
  `server.ANCHOR_NO_VALUE_ELO` (server.py:1313), which merely shares the
  1100.0 value.
- **CW-5 — Trends unaffected.** `_record_trends_snapshot` is called with
  `assigned_pids + cleared_pids` (server.py:8809–8810), exactly as before —
  demotions never fed `elo_history`, so removing them changes no Trends
  behavior (`test_trends_history_writers.py` green in the full sweep).
