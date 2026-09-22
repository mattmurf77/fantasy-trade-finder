# Trade-engine evaluation

Independent operator tooling, separate from generation and the live presentation policy. It never changes a trade, user's rankings, runtime arm or production database. The initial implementation is a **descriptive offline baseline**, not a trained acceptance predictor or automatic release approver.

## Contracts

- [Charter](charter.md): objective, authority and evidence boundaries.
- [Metrics](metrics.md): six dimensions, time-aware outcomes and denominators.
- [Evidence contract](evidence-contract.md) and [source audit](source-audit.md): existing fields, read-only exports, gaps and privacy.
- [Registry](registry.json): constructor identities versus policy/delivery layers.
- [Operating workflow](workflow.md) and [artifact templates](templates.md): development and post-release responsibilities.
- [Reviewed plan](../plans/model-evaluation-framework/README.md): full specification and adversarial decisions.

## Commands

Run from repository root, using the project's Python environment. No production connection is inferred from environment variables.

```sh
python -m backend.eval.scorecard_runner --manifest PRIVATE_MANIFEST.json --output NEW_PRIVATE_DIRECTORY
python -m backend.eval.scorecard_replay --snapshot PRIVATE_OWNER_REQUEST.json --config CAPTURED_CONFIG.json --source-commit FULL_SHA --output NEW_PRIVATE_DIRECTORY
python -m pytest backend/tests/test_scorecard_dimensions.py backend/tests/test_scorecard_outcomes.py backend/tests/test_scorecard_evidence.py backend/tests/test_scorecard_runner.py backend/tests/test_scorecard_replay.py -q
```

The runner supports normalized `offers` directly or compact `contexts` plus per-row `terms` (A/B give lists). Each row names a model/version, request, stage and rank. Register failed/empty requests too. Optional `cohort`, `episodes` and `cutoff` invoke the behavioral reducer. See committed synthetic fixtures under `backend/tests/fixtures/model-evaluation/`; those fixtures are not production evidence.

Full and compact offer envelopes are mutually exclusive; use separate variant IDs for different versions of a model. Invalid identities are quarantined while request denominators remain. Normalized evidence needs a timezone-qualified `captured_at`, source provenance and explicit pick-validity proof where applicable; fresh projections require an attestation. Replay snapshot identity binds the original inputs, effective values, common configuration and normalization version, preventing an old annotation from grading a different price reconstruction.

Outputs are new-directory-only, mode 0700 with report files 0600. Default reports aggregate evidence and omit private rows; `--private-details` is an explicit local disclosure. Do not commit exported data or publish personal boards. Replay outputs also contain a private compact input manifest and isolated SQLite scratch database.

## Current limits

Contextual ordinal grades require independent, exact-term-bound annotations or explicit reviewed reference bands. Favorable raw metrics alone do not create a passing grade. Existing logs do not establish a fixed randomized eligible cohort or universal exact completion evidence. Historical rank/market freshness, projections, full policy replay, representative populations, threshold ratification and production instrumentation remain separately tracked work. No model may be promoted from this baseline tool's output alone.

Initial [three-model comparison](../plans/model-evaluation-framework/comparison-2026-09-22.md), [revision plan](../plans/model-evaluation-framework/model-revision-plan.md) and [validation](../plans/model-evaluation-framework/validation.md) state the implemented scope and remaining evidence explicitly.
