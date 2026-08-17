# FB-328 — group canonical folder

- **Status:** built 2026-08-16 · **Phase:** 2 (build complete on `feat/fb328-picks`; awaiting group merge + operator TestFlight checklist prd §6.3)
- **Build evidence:** sabotage matrix SAB-A..H all proven RED on their mapped T-1..T-12 then reverted green (full table in `living-memory/TEST_LEDGER.md` 2026-08-16 #328 entry); targeted backend suite 327 passed; `tsc` clean; S-1/S-2/S-3 structural suites green.
- **Deviations from lld-delta (recorded):** `_mock_real_draft`'s `rounds` param is defaulted (`None` → `DEFAULT_ROUNDS`) so the existing W2d/G1 3-arg test calls run unchanged (R-9); `_mock_owned_pick_overlay` names `source=PICK_SOURCE_PLATFORM` explicitly (the lld's bare-default read would trip `test_w3_02`'s no-bare-default AST pin) and joins the sanctioned caller set in `test_pick_assignment.py`.
- **Group:** G3 — Mock draft pick assignment
- **Batch plan:** [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)
- **Base:** `origin/main` @ `d3fe3ac` (v1.13.4)

## Reported

> Mock drafts are not using the actual assigned draft picks (for example in Newton I got all four picks to slot 8 rather than my actual assigned/traded picks. [Operator: MFL provides real data; ESPN uses the manual assignment tool; applies to both modes.]
