# Validation — roster evaluator and balance review

Branch: `claude/fleeced-trade-engine-balance-c0c75d`. Base: `606e512c`.
Runtime: local Python 3.14.4; CI uses Python 3.12. No production execution.

## Completed local checks

- Final targeted backend regression set: **233 passed**, 5.13 s. Includes all new roster/policy tests, pick-value alignment, ownership, pass cooldown, presentment rules and decision idempotency. The canonical viewer fixture excludes the viewer from League.members.
- Mobile TypeScript: `./node_modules/.bin/tsc --noEmit` — passed.
- Mobile structural suites: all **90** `mobile/tests/check-*.js` suites passed.
- `bash mobile/scripts/testid-lint.sh` — passed.
- `python3 qa/web/check_web_structure.py` — **175/175** checks passed.
- HTML: subagent tested six team/scenario combinations and 320/390/768/1440px widths, keyboard disclosures and local assets. Main reviewer inspected the desktop layout, both-team weakness, unknown settings and replacement expansion. HTML, fonts and capture match the reviewed subagent output byte-for-byte; license text is retained with normalized line endings/trailing whitespace. Local HTML asset links resolve.
- Synthetic evaluator CPU check: **50 distinct packages, 24 players/team, 9 slots in 90.4 ms**, all 50 correctly eligible for same-position swaps. This excludes I/O and DB latency and is not a production benchmark.

## Full suite

`python3 -m pytest backend/tests -q` — **4,745 passed, 1 skipped**, 378.61 seconds (6m18s). The final run used a frozen backend snapshot; source hashes were verified unchanged afterward. The one skip is the existing opt-in captured-season outlook backtest. This is 39 additional passing cases beyond the first agent's 4,706-pass implementation baseline.

## Failures investigated

- New empty/small deck quota and partial-confidence tests passed after their fixes.
- The first new roster cut test caught an overconstraint: unrelated position groups must not be counted as real lineup demands. The evaluator now checks only unions of actual slot eligibility; the cut test passes.
- The flag-off golden caught two extra worker keys. They are now absent with the switches off; the golden passed in the 165/166-test focused runs.
- A full-suite attempt was interrupted after 581 passes to correct the flag-off job shape. A subsequent run had 4734 passes, 1 skip and 8 failures: seven source-inspection failures from editing the server after import and one legitimate pricing-call registration gap. With code frozen, all seven source cases pass. The new final-roster pricing surface is explicitly registered in the shared-pricing guard, and its value behavior is tested.

## Release gates and scope

All four new switches remain false. Pushed-SHA CI, Python-3.12 CI execution, production schema migration/activation and manual TestFlight verification have not been performed in this task. The mockup is not mounted in mobile. No measured acceptance uplift is claimed. See code-walk.md for observed/estimated, schedule and provenance limitations.
