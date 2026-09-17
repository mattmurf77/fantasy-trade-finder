# Implementation and validation

Date: 2026-09-17. Branch: codex/trade-significance-20260917. Base: 62ba9b3d22d804153a12b34a6e84c73ce0282521. Three bounded subagents implemented the leaf, server wiring, and independent integration tests; the parent reviewed their combined diffs. Implementation complete and locally validated; not pushed or deployed. Mode defaults off.

## Code walk

- `backend/trade_significance.py:42`: pure raw-tier evaluator; each asset judged individually, no summed-value qualification or offer-count cap.
- `backend/server.py:3160`: capture numeric settings outside arm profiles.
- `backend/server.py:3198`: shared evaluation and private evidence; shadow retains rejected candidates, enforcement removes them.
- `backend/server.py:8148`: worker gate after mutations and owner/legacy merge, before final publication/impressions.
- `backend/server.py:5026`: evidence copied into private impression features only.
- `backend/server.py:8579`: kickoff stamps settings before scheduling; running/complete/pregen/replenishment caches require compatible signatures.
- `backend/server.py:3017`: polling old incompatible jobs cannot leak pre-rule results.
- `backend/server.py:14956`: retained pending inventory is independently checked, including canonical owned-pick hydration.
- `backend/server.py:3185`: exact-package exception state is shared across captured worker/session services and pruned against live card inventory; fingerprint includes object, league, trade identity, partner and both sides.
- `backend/server.py:14476`: arm-independent significance knobs excluded from owner/control assignment hashing.
- `backend/server.py:14544`: selected owner/control route checks and private snapshot recording; manual evaluate/send/match APIs unchanged.
- `backend/server.py:8332`: distinct final-served counts; atomic impression failure/supersession explicitly records withholding at line 8461, not successful publication.

Line citations refer to this implementation branch, not the deployed base SHA. Re-check after merge/rebase.

## Executed checks

- 66 pure significance unit cases passed.
- 39 independent integration cases passed: all six arm identities, no reordering/caps, real worker filtering, trusted incoming provenance, explicit searches, raw-source handling, cached/running jobs, kickoff race, first-round-pick hydration, assignment stability, private output, atomic impression failures.
- Expanded 11-file regression run: 378 passed in 9.11 seconds (significance leaf/integration, owner routes, roster/policy math and wiring, bakeoff serving and pinned baseline golden, owned picks).
- Parent independent six-file regression: 204 passed in 7.20 seconds after inventory acknowledgement.
- Web structural checks: 195/195 passed. Mobile test-ID lint passed. `git diff --check` passed.
- Frozen raw-board calibration rerun produces the same counts in [calibration](calibration.md); no production feedback writes.
- Agent-reported runtime-only sabotage: force finite checks false -> boundary tests fail; classify a second-round pick as first -> identity test fails; bypass shared filtering -> all six arm regression cases fail. Normal reruns green. No sabotage edits retained.

An initial full run started while source was still being edited and is not accepted as final evidence: 4,843 passed, one skipped, five failures. One was the now-resolved config inventory guard. Four `inspect.getsource` checks read moved on-disk lines against already-imported function offsets; all four pass on a stable rerun.

Final stable-tree full backend suite: **6,058 passed, 1 skipped in 358.54 seconds**, using `DATABASE_URL=sqlite:// /private/tmp/fleeced-significance-venv/bin/python -m pytest backend/tests -q --maxfail=3`. Dedicated Python 3.12 environment; no production test connections. Existing mocked background paths emit missing-table diagnostic logs against isolated SQLite; no failing assertions. Lightweight evaluator-only microbenchmark: 10,000 repeated synthetic cards in 0.101 seconds; not a production latency benchmark.

## Remaining release gates

- Full stable-tree backend suite passed; rerun relevant gates if implementation changes.
- Hosted CI/mobile typecheck and mobile structural suites not run in this coding phase; no client source changed. Required before merge/push under repository workflow.
- No device/TestFlight runtime claim. Backend-only change needs no new native build unless client work becomes necessary. Manual checklist: discovery drops low-value trades; selected inexpensive asset still returns offers; inbound offer remains visible; old cached job requires regeneration; no trivial backfill when exhausted.
- Broader fresh two-league calibration and review of the five removed Yes examples before enforcement. Do not infer threshold sign-off merely from this implementation.
- Production config mutation, release SHA verification, cache regeneration, and round-two browser batch have not occurred. Original review data remains unchanged.
