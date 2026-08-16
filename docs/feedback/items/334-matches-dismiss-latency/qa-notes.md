# G9 build QA notes — sabotage RED runs (2026-08-16)

> Proven-to-fail evidence per `prd.md` § Test plan: each named sabotage was
> applied to the working tree, the suite run RED, the file reverted
> (`git checkout`), and both suites re-run green before the next sabotage.
> S-10c's sabotage is exactly the pre-fix ordering ("unhide before await"),
> as the PRD pins.

| # | Named sabotage (what was changed) | Suite | RED assertions | Reverted |
|---|---|---|---|---|
| SAB-1 | **U-1**: drop the `hiddenKeys` test from `filterVisible` | check-matches-counts | U-1a, U-1b, U-2, U-4b, U-5a, U-5b (6 failures) | green |
| SAB-2 | **U-2**: latch hidden keys permanently (module-level accumulating set) | check-matches-counts | U-2 (`[4,4,false]` — row never restores), plus U-3a/U-4b/U-5a collateral | green |
| SAB-3 | **U-3-count**: `countsByLeague(undefined)` returns `{}` instead of `null` | check-matches-counts | U-3-count (fabricated empty-count before first resolve) | green |
| SAB-4 | **U-4/S-11a**: derive the mutual pill count from the raw array (`matchesQuery.data.length`) | check-matches-counts | S-11a | green |
| SAB-5 | **U-5**: ignore the league filter in `filterVisible` (swap/flatten the inputs) | check-matches-counts | U-3b, U-5a | green |
| SAB-6 | **S-10c "unhide before await" (B-1)** — move the `onSuccess` hidden-key clear above the awaited `invalidateQueries` in BOTH mutations (the exact pre-fix ordering) | check-awaiting-dismiss | 27 and 28 (`ordered=false` both) | green |
| SAB-7 | **S-10a**: delete `cancelQueries` at two of the four sites (mutual `onMutate`, awaiting tap-time) | check-awaiting-dismiss | 22, 25 (each site pinned independently) | green |
| SAB-8 | **S-10b**: revert `visibleMatches` to a raw league filter | check-awaiting-dismiss | 26 | green |
| SAB-9 | **S-10d**: drop `undoDismiss`'s unhide | check-awaiting-dismiss | 29 | green |
| SAB-10 | **S-10e**: set `refetchOnWindowFocus: true` on `awaitingQuery` | check-awaiting-dismiss | 30 | green |

Final state after all reverts: `check-awaiting-dismiss.js` 30/30,
`check-matches-counts.js` 21/21, all 38 `mobile/tests/check-*.js` green,
`testid-lint.sh` OK, `npx tsc --noEmit` clean (fresh `npm ci`).

Code-walk proof over P1–P6 + B-1 ordering + unmounted-tab dual: see
[`qa-code-walk.md`](qa-code-walk.md).

Runtime gate: operator TestFlight checklist, `prd.md` § Test plan (8 steps).
