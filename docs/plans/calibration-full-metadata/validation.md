# Validation — full held metadata and pair-scoped Calibration

## Code walk

- `backend/calibration_roster_metadata.py:53`: capture-only refresh, bounded retained payload, lock/coalescing and atomic replacement; `:88` retains held facts only; `:94` compares applicable newer evidence with frozen as-of fallback.
- `backend/outlook_calibration_adapter.py:43`: semantic input identity includes consumed full metadata. `:98` currentness never refreshes it; `:287` starts the actual-observation consistency window and `:443` closes it.
- `backend/calibration_fixed_lineup.py:39`: unreachable-position intersection records original/effective evidence; `:58` marks coupled owners without converting the dual asset.
- `backend/calibration_provider_capture.py:225`: original ESPN native eligibility and actual configured intersection are retained.
- `backend/outlook_calibration_adapter.py:405`: unsupported viewer refusal and both-arm offensive slots/inactive IDs. `:164` full generation precedes pair masking; existing suppression, ownership, structural, significance, presentment and quality gates still run. Diagnostics at `:213` retain both unsupported participant and removed candidate counts.

## Independent evidence

Independent reviewer ran45 synthetic cases in5.11s with all4 runtime hashes unchanged before/after. Cases cover real filtered-cache boundary, K/DEF/IDP capture, observed offensive slots/inactive IDs, concurrent refresh coalescing, cache-loss/restart/currentness, newer changes/removals, pre-first-fingerprint race, native ESPN eligibility provenance, and both models' full inventory counters/pair-filter order/downstream gates. Tests copied with permission into the three `test_calibration_full_metadata_review_*` files.

An initial final-deck subsequence assertion was too strict: ordinary quality repeat deferral re-runs on eligible pairs and can reorder final cards. The corrected test checks exact pair-filter boundary order and the real downstream calls; runtime was not weakened. An inherited race fixture previously mutated the second cache read; the new coverage preflight moved that before the consistency window. It now mutates immediately after the real first fingerprint and still verifies rejection.

Production-shaped fixtures use `server._filter_bulk_players`/`_load_sleeper_cache` rather than inventing a complete normal cache. Real paired engines use synthetic provider transport/SQLite. No real manager corpus is copied and no predictive accuracy, production readiness or latency claim follows.

## Release limits

The cache's compact retained payload is bounded, but the existing HTTP reader materializes its response first. No peak-memory benchmark was run for this patch. Cache absence after deployment is deliberately unknown, not a changed observation. Actual exposure readiness must be checked after deploy/reprepare. Viewer-coupled ESPN remains unavailable; exact joint lineup support is separate engineering work. Ordinary grading feedback, exposed snapshots and public feature flags are unchanged.

## Final affected suite

**639 passed,19 skipped in28.55s** across Calibration, legacy blind grading, common roster, session input/deletion and account deletion. Provider transport is synthetic/network-blocked; SQLite is isolated. Python3.14 local; production3.12/fullCI remains required. `git diff --check` and py_compile of all4 runtime files pass. No mobile code changed.
