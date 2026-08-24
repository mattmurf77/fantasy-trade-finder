# FB-395 + FB-396 — starting-lineup impact: superflex + flex labels (Group C canonical)
- **Status:** planned 2026-08-24 — PRD ready
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

## Mobile half — R-6 rank-chip disambiguation (built 2026-08-24)

- **Branch:** `feat/fb395-rank-chip-mobile`, based on f84633f5 (Group C Phase-1 specs).
- **Diff:** two files, per the PRD's ownership table — no other file touched.
  - `mobile/src/components/CardImpactBlock.tsx` — the rank-chip template literal
    (now :157) changes from `` `${position}${rank}` `` to `` `${position} #${rank}` ``
    on both halves ("WR #3 → WR #12"); the header comment's example (:23-25)
    updated to match, with a one-line R-6 rationale. No layout, color, or logic
    change; the chip stays a positional rank (#169).
  - `mobile/tests/check-card-impact-order.js` — new check 6 (6a/6b) pinning the
    format, anchored to the rank literals `position ?? ''} #${beforeRank}` and
    the `afterRank` twin via exact `String.includes` on comment-stripped source —
    never a bare `/#\$\{/` (reconciliation N-4's non-vacuity bar).

### Gates (D-056 static evidence)

| Gate | Result |
|---|---|
| `npm ci` | clean install |
| `npx tsc --noEmit` | green |
| `node tests/check-card-impact-order.js` | 9 passed, 0 failed (checks 1-5 pre-existing, 6a/6b new) |
| `bash scripts/testid-lint.sh` | OK |

**Sabotage proof (R-6's named sabotage):** reverted the template to the bare
`${position}${rank}` form → guard red with exactly the named assertions —
`6a. rank chip before-half is "#"-prefixed ("WR #3", not "WR3")` and the 6b
twin — exit 1, other 7 checks unaffected; restored the `#` form → 9/9 green.
Comments are stripped before matching, so the header comment's "WR #3" example
cannot satisfy the guard.

### Code-walk (file:line)

1. `mobile/src/components/CardImpactBlock.tsx:149-159` — the chip renders only
   when `haveRanks` (both `s.before?.rank` and `s.after?.rank` are numbers, i.e.
   behind `trade.position_impact`); :157 is the single template literal producing
   the rank text, so the `#` prefix reaches every rendered chip and nothing else.
2. `:136` unchanged — the better/worse color still compares raw numeric ranks,
   untouched by the string format.
3. Truncation residual (reconciliation N-5): the chip sits in the same
   `numberOfLines={1}` `<Text>` (:155), ~4 chars wider — covered by TestFlight
   step 4's rank-chip look, no code change.
4. `InLeagueCalculator.tsx` `posRankLabel` untouched (PRD §3 out-of-scope):
   the two new `#` prefixes in `CardImpactBlock.tsx` are the only rank-format
   change in the diff.
