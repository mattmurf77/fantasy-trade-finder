# QA round 1 — agent A — 2026-08-24

## Summary: PASS (0 findings)

Group C (#395/#396) — lineup-impact alignment + honest platform template + rank-chip `#`
disambiguation. All six backend sabotages (A–F) and the mobile 6a/6b sabotage reproduced
independently; the R-1 pinned scan-order contract is implemented as written; totals path
verified unreachable from the alignment call.

## Environment

- Commit: `c8b0e224`, branch `claude/new-user-feedback-55320e`, clean tree.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`; backend `__pycache__` cleared after
  every python sabotage/restore; fresh `data/` dir for suite runs.

## Results

| Test | Result | Evidence |
|---|---|---|
| Baseline: `test_power_rankings.py` + `test_trade_evaluate.py` on merged tree | PASS | 119 passed (within the full 4238-pass sweep; targeted re-runs green) |
| PRD tests T1–T6 present under their contracted names | PASS | `test_align_starter_slots_superflex_cascade`, `_wr_flex_cascade`, `test_align_preserves_totals_and_eligibility` (incl. mandatory mixed-flex fixture), `test_align_forced_change_is_noop`, `test_starter_impact_slots_aligned_display`, `test_platform_template_has_no_wr3` (incl. `_MOCK_DEFAULT_LINEUP` literal pin) |
| Sabotage A — identity alignment | PASS (RED as mapped) | exactly 5 red: tests 1, 2, 5 + the two updated pairing tests (`…numbered_labels_and_null_after`, `…null_after_carries_no_tier_or_rank`) |
| Sabotage B — eligibility check dropped | PASS (RED as mapped) | exactly test 3 red on the mixed-flex fixture: `AssertionError: assert 'TE' in ('RB', 'WR')` (byte-matches the build report); test 4 stayed green — confirms the PRD's "eligibility alone is a no-op there" hand-verification |
| Sabotage C — both guards dropped (net-≥0 + no eligibility, single pass) | PASS (RED as mapped) | test 4 red (the net-0 QB↔TE2 swap applies); test 3 also red (its eligibility assert fires too — superset of the named mapping, acceptable) |
| Sabotage D — `align_starter_slots` call removed from `_starter_impact` | PASS (RED as mapped) | test 5 red + the two pairing tests (3 red) |
| Sabotage E — platform branch reverted to `_MOCK_DEFAULT_LINEUP` | PASS (RED as mapped) | test 6 red + 4 existing #311 label tests red (`test_espn_league_gets_standard_1qb_template`, `test_espn_sf_tep_…`, `test_mfl_league_…`, `test_numeric_espn_id_…`) |
| Sabotage F — mock constant literal swapped to platform shape | PASS (RED as mapped) | test 6's literal pin red |
| Mobile sabotage — `#` prefix removed from rank template | PASS (RED as mapped) | `check-card-impact-order.js` 6a + 6b red, anchored messages name the literals; revert → 9 passed |
| R-1 contract vs implementation | PASS | `power_rankings.py:134-197`: before side first; `(i, j)` ascending; first strictly-improving eligibility-valid swap applies + restarts the side; sides alternate to joint fixpoint; inputs copied (`:161-162`), not mutated |
| R-2 single call site | PASS | `git grep align_starter_slots backend/` → definition, `server.py:1197` import, `:1287` call, tests only |
| R-4/R-5 template + labels | PASS | `_PLATFORM_DEFAULT_LINEUP` `server.py:14596`, used only in the platform branch `:24180-24184` (+`SUPER_FLEX` for sf_tep); `_MOCK_DEFAULT_LINEUP` (`:14587`) and mock-draft call sites untouched |
| R-6 mobile one-liner | PASS | `CardImpactBlock.tsx:157` renders `${position} #${rank}` on both halves; header comment example updated; `posRankLabel` in `InLeagueCalculator.tsx` untouched (out of scope per PRD §3) |
| R-7 docs | PASS | `docs/api-reference.md:378` `/api/trade/evaluate` row now documents QB/2RB/2WR/TE/2FLEX (+SF) and the #395 aligned-display semantics note |
| Totals unreachable from alignment | PASS | `your_delta`/`their_delta`/`note` computed at `server.py:1229-1247` from `optimal_starters` totals, before the `:1287` alignment call |
| Web/extension untouched | PASS | `git grep starter_impact -- web/ extension/` → 0 hits; wave diff on `web/`/`extension/` empty |

## Findings

None blocking or major. Two observations:

- **Obs-1 (informational):** sabotage C reds test 3 in addition to the named test 4 —
  expected (dropping eligibility trips test 3's validity assert as well); the named case
  fired, so the mapping holds.
- **Obs-2 (informational):** the two revised pairing-test expectations (build-report
  deviation #2) were re-checked under sabotage A/D: both go red whenever alignment is
  removed or made identity, so they genuinely double as identity-sabotage guards as the
  build report claims.

## TestFlight checklist (operator-run) — verified as executable, refined

Code-side references confirmed: `trade.position_impact` true (`features.json:219`);
the calculator's `SLOT_SHORT` map (`InLeagueCalculator.tsx:1554`) shortens `SUPER_FLEX`
→ `SF` as step 5's parenthetical says. Steps 5–6 depend on the operator having ESPN/MFL
leagues linked (stated true in the PRD; not verifiable from code — if neither is linked,
record steps 5–6 as BLOCKED in TEST_LEDGER rather than skipped).

Superflex Sleeper league (your own):

1. Evaluate a trade sending **Jayden Daniels away for picks only** (build Daniels → picks
   in the In-league calculator if no such card fronts — an incoming starter legitimately
   adds rows). Expected: "Your starting lineup" shows **exactly one** row — `SF: Jayden
   Daniels › <replacement>` — and **no QB row** claiming Maye was displaced.
2. Same trade in the In-league calculator. Expected: BEFORE column shows Daniels at `SF`
   and Maye at `QB`; totals row present.
3. Compare lineup totals/deltas for the same trade against a pre-update screenshot or
   build if available. Expected: numbers identical — alignment moves rows, never numbers.
4. Any changed row with rank chips. Expected: `WR #3 → WR #12` style (with `#`), never
   `WR3`. Also glance at truncation on a narrow device — the chip is ~4 chars wider.
5. ESPN or MFL league: front a card (or calculator-evaluate) involving a WR. Expected:
   **no `WR3` anywhere**; slots read `QB RB1 RB2 WR1 WR2 TE FLEX1 FLEX2` (+`SF` in
   sf_tep — the calculator table shortens `SUPER_FLEX`→`SF`); a flex-started WR is
   labeled `FLEX1`/`FLEX2`.
6. Sanity on the same platform league: the note and totals still render; slight value
   shifts vs the old build are expected (honest template: a 3rd RB / 2nd TE may now start
   over the fabricated 3rd WR).

Outcome interpretation (log which in status.md): #396 from an ESPN/MFL league → step 5
clears it; from a Sleeper 2-WR league → only the rank chip could have produced it and
step 4 clears it.
