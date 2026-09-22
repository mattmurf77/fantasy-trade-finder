# Implementation validation — September 22, 2026

## Scope and environment

Isolated branch `codex/model-evaluation-framework-20260922`, source base `73bfa41e358e8780b823f652cf8388ae209b977d`, worktree `/private/tmp/fleeced-model-evaluation-20260922`. Fresh upstream source; older dirty canonical/legacy app checkouts preserved. Three Astra Ultra implementation agents and parent integration; cross-review used different owners for each subsystem.

Local interpreter: Python **3.14.4**, pytest **9.1.1**, SQLAlchemy **2.0.54** in `/private/tmp/ktc-benchmark-venv`. Hosted CI targets Python 3.12; no hosted exact-head run or deployment was performed. No production credentials or DB connection used. Broad tests use isolated SQLite; replay forcibly sets its own scratch DB and blocks sockets.

## Automated checks

| Check | Result |
|---|---|
| Final focused evaluator/adapter/runner/replay suites | **172 passed in 0.56s** |
| Dimensions | 63 tests; independent targeted repair probes passed |
| Outcomes | 64 tests; independent targeted repair probes passed |
| Evidence + runner + replay | 45 tests; independent review passed |
| Full backend, initial environment attempt | Collection blocked by missing project dependencies; dependencies subsequently installed into temporary venv, no requirements change |
| Exploratory full backend during final outcome edits | 6,431 passed / 6 failed / 1 skipped; six newly added outcome regressions used the pre-fix module loaded earlier in the process |
| Fresh source-frozen full backend rerun | **6,437 passed / 1 skipped in 355.93s** |
| Frozen real three-model replay, repeated | Same 2,843 / 2,103 / 106 native cards; byte-identical normalized private manifest and aggregate scorecard; comparison identical excluding wall-clock timing |
| Source/evidence hashes and aggregate numeric checks | Independent review reconciled all reported counts/rates/coverage; source hashes match |
| Mobile/device/web runtime | Not run: no client or production runtime changes; no three-second qualification |

The exploratory six failures were not waived: the repaired 64-test outcome suite passed in a fresh interpreter, followed by the green source-frozen full regression run. Test-only background receipt threads logged missing scratch tables during teardown; the full suite's result above is the final process result, not a production error report.

Focused command:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  backend/tests/test_scorecard_dimensions.py \
  backend/tests/test_scorecard_outcomes.py \
  backend/tests/test_scorecard_evidence.py \
  backend/tests/test_scorecard_runner.py \
  backend/tests/test_scorecard_replay.py -q -p no:cacheprovider
```

Full command: `DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 python -m pytest backend/tests/ -q -p no:cacheprovider --tb=short`.

## Adversarial review and demonstrated failures

| Finding | Repair / failure-sensitive evidence |
|---|---|
| Untimed/future provenance, malformed slot eligibility, unsupported/invalid picks could produce misleading assessment | Timestamp/cutoff/freshness validation, typed eligible-position lists, explicit pick-ledger evidence. Focused pre-fix run: 12 failures / 1 pass; final 63 tests pass |
| Undo restoring an earlier like counted as withdrawal; completed offer remained actionable | Restore-stack and lifecycle semantics repaired; focused pre-fix regression suite across outcome findings: 9 failures / 1 pass |
| Invalidation interpreted as refusal; conflicting duplicate histories hid attrition; origin model identity mismatch | Separate validity/behavior, conservative duplicate-history quarantine and attribution; milestone retained but unsupported follow-up never passes |
| Early invalidation mislabeled expiry; early explicit expiry not recognized; post-completion withdrawal counted as reliable refusal | Six new tests failed before repair, then passed; actual closure time/reason drives expiry, stale post-completion actions are retained as evidence defects, not trusted reversals |
| Default aggregate diagnostics leaked private model pools/manager IDs | Explicit aggregate allowlist and default outcome-detail stripping; private rows require deliberate local opt-in |
| Mixed full/compact envelopes contaminated evaluation cache | Reject ambiguous envelopes; isolate immutable context/terms identity |
| Sparse boards created fake preference direction | Common captured reference universe for coordinates with explicit-source mask kept separate |
| Different versions mixed request denominators | Require separate variant IDs; reject mixed versions under one model ID |
| Owned-pick suffix conflated roster with manager | Preserve original roster identity, require frozen mapping for owner assertion |
| Reconstructed values/config reused historical snapshot identity | Fingerprint input + values + configuration + normalization version; original request hash remains separate provenance |
| Invalid offers could count as evaluated; outcome rows could escape in aggregate output | Quarantine invalid integrity, retain request denominators; default details removed and counted |

The evidence agent reproduced cache contamination, sparse-board false gaps and mixed-version denominator issues independently before correction. Final cross-review signed off runner/replay for descriptive offline use. Outcomes and dimensions owners independently re-reviewed one another after repairs. The comparison/revision documents were independently fact-checked; market-vintage and unresolved later-year pick-discount wording were corrected.

## Real replay reproduction

The private files existed from earlier authorized research; none are committed. From repository root:

```sh
PYTHONHASHSEED=0 \
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
python -m backend.eval.scorecard_replay \
  --snapshot /private/tmp/trade-latency-private-config.json \
  --config /private/tmp/trade-model-scorecard-live-baseline.json \
  --source-commit 73bfa41e358e8780b823f652cf8388ae209b977d \
  --output NEW_PRIVATE_DIRECTORY
```

The `source-commit` must match that checkout's full HEAD. Future commits require their actual SHA and record changed source hashes; do not mislabel them the original baseline. Output directory must not already exist. Reference publication dates are unknown; pinned files keep any auxiliary pricing deterministic, not historically fresh.

Repeated output directories: `/private/tmp/fleeced-scorecard-run-20260922-final` and `/private/tmp/fleeced-scorecard-run-20260922-repeat`.

- Raw manifest file SHA-256: `2376fff69ec7908d478b317f6b17a6373183cc3dda66ba880b590a5f6562a517` (identical).
- Canonical manifest identity: `1999f87270098333ede1c0a4b6e4097a4fd4db778b088f2c0006898be045b1ed` (identical).
- Aggregate scorecard file SHA-256: `90d1997580eeef2832b03a492c9b047b144cf4424868f1cbf2962b9000086118` (identical).
- Three registered model-request runs, all nonempty; no invalid offer quarantines in this input. **One independent underlying request**, no outcomes supplied, no justified behavioral CI.

Safe aggregate findings are committed in [comparison-summary.json](comparison-summary.json) and [context summary](comparison-context.json); private identity/board material is not.

## Remaining gates

This is an offline foundation, not completion of every phase of the reviewed plan. Representative benchmarks, domain-annotation calibration, threshold ratification, full live-policy replay, production instrumentation/cohort eligibility, post-release scheduling, acceptance calibration, hosted CI and authorized release remain separate. No model is promoted, no live arm/settings changed, no TestFlight build needed for these offline modules.
