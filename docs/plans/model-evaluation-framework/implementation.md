# Implementation workstreams

Base: `origin/main` at `73bfa41e358e8780b823f652cf8388ae209b977d`, freshly fetched September 22, 2026. Isolated branch `codex/model-evaluation-framework-20260922`; no source from the older dirty canonical checkout copied. Only the reviewed planning packet was carried forward.

| Owner | Bounded responsibility | Files |
|---|---|---|
| Astra Ultra dimensions agent | Independent six-dimension, four-side metrics/grades and missingness | `backend/eval/scorecard_dimensions.py` and focused tests |
| Astra Ultra outcomes agent | Valid-overlap lifecycle, fixed cohort yield, attrition and attribution | `backend/eval/scorecard_outcomes.py` and focused tests |
| Astra Ultra evidence agent | Read-only snapshot adapter and source/coverage audit | `backend/eval/scorecard_evidence.py`, focused tests, canonical evidence docs |
| Parent | Integration, CLI/reporting, manifests, operating contracts, constructor comparison, independent validation and revision plan | Remaining evaluation tooling and canonical docs |

No agent may change production configuration, app routing, release state or private input data. Candidate scores cannot be reused as their own evaluation grades. Default report status is evidence-limited until required independent evidence and ratified thresholds exist.

## Requested follow-through

After evaluator verification, compare the newest constructor families by introduction commit: bilateral owner (`4913ad0c`, September 20), owner-v1 (`0e3d6b70`, September 6), fit (`c6e6c3c0`, August 20). Performance/publication-only revisions are not new trade models. Replay retained current-source implementations with explicit version/config identity, not falsely labeled original historical binaries. Write a separate revision plan based on the multidimensional findings; no single blended score and no unsupported acceptance winner.

## Implemented offline foundation

- Six-dimensional independent four-side/raw/package evaluator, legal lineup solver, temporal provenance, exact-term-bound independent annotations and honest missingness.
- Outcome reducer for overlapping interest, immutable historical mutual milestones, actual expiry, completion, reversals and distinct invalidation; fixed cohorts and guarded cross-arm attribution.
- Allowlisted read-only local evidence adapters, source/coverage audit and private-by-default reports.
- Manifest/report runner with full/compact context separation, version/identity validation, invalid-record quarantine and request denominators that retain zero/error results.
- Offline replay of the three constructor families with isolated SQLite, network blocking, common inputs/config and configuration-bound normalized evidence identity.
- Canonical charter, metric registry, operating workflow, artifact templates, constructor registry, architecture and operator instructions.
- Reproducible initial [comparison](comparison-2026-09-22.md) and an evidence-led [model-revision plan](model-revision-plan.md).

## Not yet implemented / not claimed complete

The reviewed plan extends beyond this foundation. A representative multi-context benchmark, adjudicated human grades, ratified empirical thresholds, full serving-policy/ablation runner, production eligibility/view/expiry instrumentation, hosted scheduled production scorecards, trained/calibrated acceptance probabilities and release automation remain subsequent work. Existing input deficiencies cannot be fixed merely by emitting a numerical score. No UI dashboard or app runtime integration was added.

Cross-review and final parent validation are in [validation](validation.md). The reviewed plan/spec/playbook retain their exact signed-off content; implementation results are additive documents rather than retroactively changing the plan's claims.
