# QA round 1 — agent B — 2026-08-24

## Summary: PASS (0 findings)

Group C — #395/#396 starter-slot alignment + platform template + rank-chip
disambiguation. All six backend sabotages (A–F) and the mobile 6a/6b sabotage
reproduced independently — every one RED on its named test, every revert
green, including the two PRD hand-verifications (eligibility-alone is a no-op
on test 4's fixture; identity alignment reds the two updated pairing tests).
`align_starter_slots` implements the pinned R-1 scan-order contract verbatim.

## Environment

- Commit: `c8b0e224`; tree clean after QA. `backend/__pycache__` +
  `backend/tests/__pycache__` cleared after every python restore.
- node v24.14.1 · Python 3.14.4 · fresh `npm ci`
- Suites: `pytest backend/tests/test_power_rankings.py backend/tests/test_trade_evaluate.py`
  (baseline **119 passed**, matching the build report); guard
  `node tests/check-card-impact-order.js`.

## Results

| Test | Result |
|---|---|
| Batch gates (npm ci / tsc / testid-lint / 78-guard sweep / full pytest 4238+1 / empty web diff) | PASS |
| Baseline: two touched suites | PASS — 119 passed |
| PRD tests 1–6 present and green: `test_align_starter_slots_superflex_cascade`, `test_align_starter_slots_wr_flex_cascade`, `test_align_preserves_totals_and_eligibility` (incl. the mandatory WRRB_FLEX+REC_FLEX mixed-flex fixture), `test_align_forced_change_is_noop`, `test_starter_impact_slots_aligned_display`, `test_platform_template_has_no_wr3` (incl. both constants' literal pins at `test_trade_evaluate.py:1119-1121`) | PASS |
| Sabotage A — identity alignment (fixpoint loop removed) → red | PASS — RED on tests 1, 2, 5 **plus** the two updated pairing tests (`test_starter_impact_slots_numbered_labels_and_null_after`, `…_null_after_carries_no_tier_or_rank`), exactly the build report's set; test 3 stays green (identity preserves totals — correct) |
| Sabotage B — eligibility check dropped (`_fits` → True) → red | PASS — RED on `test_align_preserves_totals_and_eligibility` only (the mixed-flex fixture fires); **test 4 stayed green**, confirming the PRD's "eligibility alone is a no-op there" hand-verification |
| Sabotage C — both guards dropped (net-≥0 + no eligibility, single pass) → red | PASS — RED on `test_align_forced_change_is_noop` (named case) + collateral (test 3, three route-level slot tests) |
| Sabotage D — `align_starter_slots` call removed from `_starter_impact` → red | PASS — RED on `test_starter_impact_slots_aligned_display` + the two pairing tests |
| Sabotage E — platform branch reverted to `_MOCK_DEFAULT_LINEUP` → red | PASS — RED on `test_platform_template_has_no_wr3` + 4 existing #311 label tests (`test_espn_league_gets_standard_1qb_template`, `test_espn_sf_tep_league_appends_super_flex_and_seats_second_qb`, `test_mfl_league_gets_standard_1qb_template`, `test_numeric_espn_id_never_fetches_sleeper_meta`) — the build report's exact set |
| Sabotage F — mock constant literal swapped to the platform shape → red | PASS — RED on `test_platform_template_has_no_wr3` (the N-3 literal pin has teeth) |
| Mobile R-6 sabotage — `#` prefix removed from the rank template literal → red | PASS — RED with exactly `6a` and `6b` ("rank chip before/after-half is '#'-prefixed"), other checks unaffected; revert green |
| R-1 contract: implementation at `backend/power_rankings.py:134-197` — before side first; pairs (i,j) i<j ascending; first strictly-improving eligibility-valid swap; restart from (0,1); sides alternate to fixpoint (`while _align_side(before, after) \| _align_side(after, before)`, non-short-circuit); inputs copied, not mutated; None fits any slot, None-matches-None | VERIFIED line-by-line against R-1's pinned contract |
| R-2 single call site: `git grep align_starter_slots backend/` → `power_rankings.py:134` (def), `server.py:1197` (import), `server.py:1287` (the only call, between the fills at :1279-1282 and the labeling loop) + tests | VERIFIED |
| R-4: `_PLATFORM_DEFAULT_LINEUP` (`server.py:14596`) used only in `_league_lineup_slots`' platform branch (`:24181`), `SUPER_FLEX` appended for `sf_tep`; `_MOCK_DEFAULT_LINEUP` (`:14587`) and mock-draft call sites (`:14767`, `:14815`) untouched | VERIFIED |
| R-5: labeling loop numbers repeated slots (`FLEX1/FLEX2`), single slots bare (`server.py:1291-1299`); `_STANDARD_1QB_LABELS` (`test_trade_evaluate.py:906`) updated to the R-5 list — the recorded PRD deviation, not a loosening | VERIFIED |
| R-6: `CardImpactBlock.tsx:157` single template literal `` `${s.before?.position ?? ''} #${beforeRank} → ${s.after?.position ?? ''} #${afterRank}` ``; guard anchors are the exact rank literals (`check-card-impact-order.js:169-170`), not a bare `/#\$\{/`; `posRankLabel` in `InLeagueCalculator.tsx` untouched | VERIFIED |
| R-7: `docs/api-reference.md:378` `/api/trade/evaluate` row carries QB/2RB/2WR/TE/2FLEX (+SF for sf_tep) and the "Aligned display (#395)" pairwise-alignment semantics note | VERIFIED |
| File ownership: mobile commit `71d70153` = CardImpactBlock.tsx + check-card-impact-order.js + status only | VERIFIED |

## Findings

None. Two observations, no action required:

- Sabotage C reddens four tests beyond the named `test_align_forced_change_is_noop`
  (collateral from the degenerate single-pass alignment); the named case fires
  as contracted.
- The PRD's `test_trade_evaluate.py:1034` cite for the expected-template
  update now sits at `:1043` in the merged tree (lines shifted by the new
  tests). Content is exactly as specced (`slots == list(srv._PLATFORM_DEFAULT_LINEUP)`).

## TestFlight checklist (operator-run)

Verified executable: the In-league calculator, its `LineupImpactTable`, the
`SLOT_SHORT` map (SUPER_FLEX→SF, `InLeagueCalculator.tsx:1554`), and the
card's changed-row filter (`CardImpactBlock.tsx:110-111`) all exist at the
cited surfaces. Refined version:

Superflex Sleeper league (the operator's own):

1. Evaluate a trade sending **Jayden Daniels away for picks only** (build
   Daniels → picks in the In-league calculator if no such card fronts — an
   incoming starter legitimately adds rows). Expected: "Your starting lineup"
   shows **exactly one** row — `SF: Jayden Daniels › <replacement>` — and
   **no QB row** claiming Maye was displaced.
2. Same trade in the In-league calculator. Expected: BEFORE column shows
   Daniels at `SF` and Maye at `QB`; totals row present.
3. Compare lineup **totals and deltas** against a pre-update screenshot or
   build if available. Expected: numbers identical — alignment moves rows,
   never numbers.
4. Any changed row with rank chips. Expected: `WR #3 → WR #12` style (with
   `#`), never `WR3`. Give the chip one look on a narrow device — it is ~4
   characters wider inside a one-line row (accepted N-5 residual; the
   after-half truncates first).

ESPN or MFL league (operator has both linked):

5. Front a card (or calculator-evaluate) involving a WR. Expected: **no
   `WR3` label anywhere**; slots read `QB RB1 RB2 WR1 WR2 TE FLEX1 FLEX2`
   (+`SF` in sf_tep — the calculator table shortens `SUPER_FLEX`→`SF`); a
   flex-started WR's row is labeled `FLEX1`/`FLEX2`.
6. Sanity: the `your_delta` note and totals still render; slight value shifts
   vs the old build are expected here (honest template: a 3rd RB / 2nd TE may
   now start over the fabricated 3rd WR).

Outcome interpretation (log which in status.md): #396 from an ESPN/MFL league
→ step 5 clears it; from a Sleeper 2-WR league → only the rank chip could
have produced it, step 4 clears it.
