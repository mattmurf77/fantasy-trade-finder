# QA round 1 — agent B — 2026-08-24

## Summary: PASS (1 finding)

Group F — #346/#381 QuickSet HOLD (D-160). Backend and mobile halves both
re-proved from scratch: the old-code restore reddens exactly T-1/T-2/T-3/T-5/
T-6/T-7 with T-4 green; the waivers-skip and (conditional) echo sabotages red;
all five mobile guard sabotages red with the named A-assertions. Cross-platform
payload shape verified mobile↔backend. One minor finding on the T-2 sabotage
wording ("any echo/warning key" — an *unconditional* echo key is not caught,
and by the letter of R-3 correctly so).

## Environment

- Commit: `c8b0e224`; tree clean after QA. `backend/__pycache__` +
  `backend/tests/__pycache__` cleared after every python restore; old code
  taken from `e5759628` (pre-fix), reverted via `git checkout HEAD --`.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`
- Suites: `pytest backend/tests/test_quickset_demote.py` (7 tests);
  `node tests/check-quickset-hold.js` (13 checks).

## Results

| Test | Result |
|---|---|
| Batch gates (npm ci / tsc / testid-lint / 78-guard sweep / full pytest 4238 passed + 1 skipped on a fresh data dir / empty web-extension diff) | PASS |
| Known issue check: `test_deck_signal_v2.py::test_flag_on_writes_impressions_in_served_order` | PASS inside the full fresh-dir sweep — the state-sensitivity did not fire this run |
| Baseline `test_quickset_demote.py` | PASS — 7 passed |
| Sabotage: old code (`server.py` + `ranking_service.py` @ `e5759628`) → T-1/T-2/T-3/T-5/T-6/T-7 red, T-4 green | PASS — RED exactly {T-1, T-2, T-3, T-5, T-6, T-7}; `test_fa_rung_save_pins_waivers_band` (T-4) stayed green as specified (survives-affordance pin) |
| Sabotage: **conditional** echo key (`demoted_pids_ignored` added to the response when the body carries the legacy key) → T-2 red | PASS — RED, `Extra items in the left set: 'demoted_pids_ignored'` (the build report's exact evidence) |
| Sabotage: **unconditional** echo key → | STAYED GREEN — see finding F-1 |
| Sabotage: skip the `waivers` tier in `apply_tiers` → T-4 red | PASS — RED exactly {T-4} |
| Mobile M1: pre-fix client wholesale (3 src files @ `e5759628`) → red | PASS — RED exactly {A1a, A1b, A1c, A1d, A2b, A2e} — the build report's exact 6 |
| Mobile M2: re-add `demoted: []` to the mutate payload → red | PASS — RED {A1a, A1c} |
| Mobile M3: delete the `mutate({ ids, cleared })` call (O-5 vacuity probe) → red | PASS — RED {A1c} — the positive anchor stands alone |
| Mobile M4: re-add `demoted_pids: []` to the POST body → red | PASS — RED {A2e} |
| Mobile M5: named `demoted` local at a TiersScreen call site → red | PASS — RED {A3a} |
| All reverts (backend + mobile) | PASS — green after every revert |
| R-2 code-walk (CW-4): `save_tiers_route` (`server.py:8702`) parses only `position`/`tiers`/`cleared_pids` (+`scope`/`via`); emptiness guard `total_assigned == 0 and not cleared_pids` (`:8738`); `git grep demoted_pids backend/` hits only the route docstring's back-compat note (`:8714`) + the tests; no `_pin(…, DEMOTED_ELO)` caller remains in `ranking_service.py` | VERIFIED |
| R-4: `_unpin` on `cleared_pids` before the tier-write loop (`ranking_service.py` apply_tiers body) — legacy both-keys request now clears | VERIFIED (T-3 red under old code proves the precedence flip) |
| R-5: `DEMOTED_ELO = 1100.0` kept (`ranking_service.py:1785`), re-commented; `test_pin_tier_bounded.py` untouched and green in the full sweep; D-085 frozen-populations docstring bullet reworded not removed (`:549-560`, #161 clause past tense) | VERIFIED |
| R-7: 4 TiersScreen call sites now 4-arg (`:339, :380, :1096, :1103`); tsc enforces arity | VERIFIED |
| R-8: `waivers` is the 8th rung (`tierBands.ts:35`, TIER_LABEL `waivers: 'FA'`); T-4 pins the write path | VERIFIED |
| R-9 docs: `docs/api-reference.md:217` row rewritten (Body drops `demoted_pids`; ignore contract; clear-restores; empty-save 400s even with the key); D-160 at `living-memory/DECISIONS.md:1496` with the O-1 rollback caveat; superseded note atop `../161-quickset-demote/status.md` | VERIFIED |
| Cross-platform consistency (mobile payload vs backend parse): `saveTiers` POST body = `{position, tiers, cleared_pids, scope?, via?}` (`api/rankings.ts:344-350`); route reads exactly those (`server.py:8727-8731`, scope behind `ranks.rookie_subset` = true, `via` whitelist includes `rookie_quickset`); same names, same semantics; no `demoted_pids`/`demotedPids` anywhere under `mobile/src` | VERIFIED |
| File ownership: mobile commit `f55c90fa` = QuickSetTiersScreen.tsx, api/rankings.ts, TiersScreen.tsx, check-quickset-hold.js, package.json — exactly the owned set | VERIFIED |

## Findings

**F-1 · minor · T-2's sabotage row overstates: "any echo/warning key" is not
mechanically caught — only a key conditional on the legacy field is.**
- Repro: add `"demoted_pids_ignored": True` **unconditionally** to
  `save_tiers_route`'s success payload → `test_demoted_pids_key_is_ignored`
  stays green (it compares the response key set with-the-key vs
  without-the-key; an unconditional extra key appears in both and cancels
  out). Re-apply the same key **conditionally** on
  `body.get("demoted_pids")` → RED with `Extra items in the left set:
  'demoted_pids_ignored'`.
- Expected (prd.md §6a T-2 row: "RED under … any echo/warning key") vs
  actual: only the conditional variant is red. By the letter of R-3 ("the
  response stays byte-identical to one without the key") the test is
  arguably *correct* — an unconditional shape change is not a reaction to
  the key — but the PRD's sabotage wording promises more than the test
  delivers. Doc-level: tighten the T-2 row to "any echo/warning key
  conditioned on the legacy field", or add a response-key golden if the
  stronger property is wanted. No code defect; do not change the test
  without deciding which property is the contract.
- Evidence: both runs reproduced this session (see Results rows above);
  test at `backend/tests/test_quickset_demote.py:160-178`.

## TestFlight checklist (operator-run)

Verified executable: Quick set walk (`QuickSetTiersScreen`, 8 rungs incl. the
FA rung — `TIERS` from `tierBands.ts` ends in `waivers`, label "FA"), rung
labels "4+ 1STS"/"3 1sts"/"1 1st" all exist in `TIER_LABEL`, Tiers board =
`TiersScreen`. Refined version:

1. Rank tab → Quick set → WR, format as in your league. On **4+ 1sts**:
   confirm Nabers' chip shows "4+ 1STS". Select 3 other WRs — **not**
   Nabers. Save.
2. On **3 1sts**: Nabers is still near the **top** of the grid, chip still
   "4+ 1STS" — not FA, not missing. *(Old behavior: bottom of the ~200-player
   list as FA — this step alone catches the regression.)*
3. Tap Nabers + Save → back on the Tiers board: the 3 WRs sit in 4+ 1sts,
   Nabers in 3 1sts, nobody new in FA.
4. Explicit demote still works: walk to the **FA** rung, select a
   currently-tiered depth player, Save → Tiers board shows him in FA.
5. Revisit path — **must use a rung where you placed two or more players
   this run**: deselect one, keep the rest selected, Save → the deselected
   player returns to his consensus-suggested tier chip, not FA. (Deselecting
   a rung's only player takes the clear-only branch, which never demoted
   even on old code — non-differentiating.)
6. #346 angle: on the **1 1st** rung, select only some of the preseeded
   1-1st players and Save → the unselected ones still read "1 1ST" on the
   next rung.
7. Cleanup: re-place any player the old behavior FA'd (Nabers included —
   the fix does not retro-repair historical 1100-pins; they are
   indistinguishable from anchor "no value" answers).
