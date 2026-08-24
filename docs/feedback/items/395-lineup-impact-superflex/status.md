# FB-395 + FB-396 — starting-lineup impact: superflex + flex labels (Group C canonical)
- **Status:** backend built 2026-08-24 (branch `feat/fb395-lineup-impact-backend`) — mobile half (R-6) separate agent; integration runs the full sweep + living-memory
- **Covered:** #395 (SF slot attribution), #396 (flex slot labeled "WR3")
- **Path:** fast-track bug, full gates
- Docs: [plan.md](plan.md) · [prd.md](prd.md) · [scope.md](scope.md)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

#395: trading away Jayden Daniels in a superflex league, the lineup-change
readout claims Maye was the QB starter and Fannin the SF starter, rather than
Daniels occupying SF. Verdict: math right, presentation wrong — the two
canonical greedy fills are diffed row-by-row with no churn minimization. Fix A:
pure `align_starter_slots` display alignment inside `_starter_impact` only.

#396: change readout says "WR3" in a league with 2 WR slots + flex. Verdict:
ESPN/MFL/Fleaflicker leagues substitute the 3-WR `_MOCK_DEFAULT_LINEUP` for the
real template (`server.py:24171-24175`). Fix B: honest
`_PLATFORM_DEFAULT_LINEUP` (QB/2RB/2WR/TE/2FLEX, +SF for sf_tep), unconditional.
Plus a one-line rank-chip disambiguation (`WR3 → WR12` becomes `WR #3 → WR #12`,
`CardImpactBlock.tsx:155`) — the chip is the only source that can read "WR3" in
a Sleeper 2-WR league. TestFlight checklist covers both league types so the
operator's pass settles which one the report came from.

---

## Backend build report (2026-08-24)

**Plain words:** both backend fixes are in. Trading a superflex QB now shows one
honest lineup change instead of a phantom two-row cascade, and platform-imported
leagues can no longer display a "WR3" slot they don't have. No number the app
shows moved — only which row a change is displayed on.

### What shipped

- `backend/power_rankings.py` — new pure `align_starter_slots(before, after)`
  implementing R-1's pinned contract verbatim: before side first; pairs
  `(i, j)`, `i < j`, ascending; first strictly-improving eligibility-valid swap
  applies and restarts that side from `(0, 1)`; sides alternate until both pass
  a full scan clean. Inputs unmutated; aligned copies returned.
- `backend/server.py` — (i) `_starter_impact` calls `align_starter_slots`
  between the two `optimal_starter_slots` fills and the labeling loop (the ONLY
  call site — `git grep -n align_starter_slots backend/` shows power_rankings +
  this one + tests); (ii) new `_PLATFORM_DEFAULT_LINEUP`
  (`QB RB RB WR WR TE FLEX FLEX`) used only in `_league_lineup_slots`' platform
  branch; `_MOCK_DEFAULT_LINEUP` and its mock-draft call sites (:14759, :14807)
  byte-untouched.
- Tests: PRD matrix 1–6 added (`test_align_starter_slots_superflex_cascade`,
  `test_align_starter_slots_wr_flex_cascade`,
  `test_align_preserves_totals_and_eligibility` incl. the mandatory mixed-flex
  fixture, `test_align_forced_change_is_noop`,
  `test_starter_impact_slots_aligned_display`,
  `test_platform_template_has_no_wr3` incl. the `_MOCK_DEFAULT_LINEUP` literal
  pin). `test_trade_evaluate.py:1034` updated to `_PLATFORM_DEFAULT_LINEUP` as
  specced.
- `docs/api-reference.md` — `/api/trade/evaluate` row: platform template now
  QB/2RB/2WR/TE/2FLEX (+SF for sf_tep); `slots` aligned-display semantics note.

### Deviations from the PRD (recorded, not loosened)

1. **`_STANDARD_1QB_LABELS` (test_trade_evaluate.py:900)** — the shared
   constant three existing #311 tests assert against still carried
   `WR3`/single-`FLEX`; updated to the R-5 label list. A necessary consequence
   of R-4 the PRD's test-7 row didn't enumerate.
2. **Two existing slot-pairing expectations**
   (`test_starter_impact_slots_numbered_labels_and_null_after`,
   `test_starter_impact_slots_null_after_carries_no_tier_or_rank`) asserted the
   UNALIGNED cascade on their own fixtures (give `good`, RB2 empties):
   alignment now correctly keeps the surviving starter on its row and shows the
   departing player on the emptied row. Expectations updated (`bench`→`good`,
   delta `−v(bench)`→`−v(good)`); per-row-delta sum and totals unchanged. These
   two now double as extra identity-sabotage guards.
3. **Worktree base** — the assigned worktree was cut from `main` before the
   spec commit; branch re-cut from `f84633f5` directly (contains the signed-off
   Group C PRD).

### Evidence (D-056 static)

- Suites: baseline 113 passed → **119 passed** post-build
  (`test_power_rankings.py` + `test_trade_evaluate.py`); targeted blast-radius
  sweep `test_mock_draft.py test_mock_pick_ownership.py test_team_review.py
  test_window_composite.py test_window_signals.py` → **240 passed**. Full
  `pytest backend/tests` sweep runs at integration.
- Sabotages (committed first; `__pycache__` cleared after each restore):
  - A identity alignment → 5 red: tests 1, 2, 5 + the two updated pairing tests.
  - B eligibility check dropped → test 3 red exactly on the mixed-flex fixture:
    `AssertionError: assert 'TE' in ('RB', 'WR')` (teQ into WRRB_FLEX); test 4
    stayed green under B, confirming the PRD's "eligibility alone is a no-op
    there" hand-verification.
  - C both guards dropped (net-≥0 + no eligibility, single pass) → test 4 red:
    the net-0 QB↔TE2 swap applies, before renders `QB: —` with daniels in the
    TE2 row.
  - D `align_starter_slots` call removed from `_starter_impact` → test 5 red
    (changed-row set), plus the two pairing tests.
  - E platform branch reverted to `_MOCK_DEFAULT_LINEUP` → test 6 red
    (`At index 5 diff: 'WR3' != 'TE'`) + 4 existing #311 label tests red.
  - F mock-constant literal swapped to the platform shape → test 6's literal
    pin red.
- Scripted Daniels repro (plan §1) through the real
  `optimal_starter_slots` → `align_starter_slots` path: pre-fix changed rows =
  `QB daniels→maye` + `SUPER_FLEX maye→fannin`; post-fix = `SUPER_FLEX
  daniels→fannin` only; totals byte-equal (32100/25900 both sides of the fix).

### Code-walk proof (backend half, file:line on this branch)

Evaluate Mode B → `_starter_impact` (`backend/server.py:1167`) resolves the
template via `_league_lineup_slots` (:1202) — platform branch now returns
`list(_PLATFORM_DEFAULT_LINEUP)` (constant :14603; branch :24187-24191, with
`SUPER_FLEX` appended for sf_tep), so no template can carry three literal `WR`
entries and the numbering loop (:1291-1299, unchanged logic) can never emit
`WR3` for a platform league (it emits `FLEX1/FLEX2` for the repeated flex). The
two canonical fills (:1279-1282) are re-paired by `align_starter_slots` (:1287;
`backend/power_rankings.py:134`) before labeling, so a value-identical
assignment reaches the client with the minimal changed-row set;
`your_delta`/`their_delta`/`note` are computed earlier (:1229-1247) from
`optimal_starters` totals and are unreachable from the alignment call. Mobile `CardImpactBlock.tsx:108-111` filters to changed rows —
the #395 payload now passes it exactly one row. (Rank-chip R-6 trace: mobile
agent's half.)
