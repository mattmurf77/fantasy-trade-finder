# qa/ — Notes for Claude

Backend QA charter (see `README.md`). Live, tracked harness: `api/`, `db/`, `e2e/`, `eng/`, `lib/` (harness.py), `perf/`, `sec/` (`tc_*.py` test cases) and `results/` (`TC-*.md` write-ups) — treat these as real code/docs, not scratch. Root also has `TEST_CASE_TEMPLATE.md`, `accessibility-release-checklist.md`, one-off audit notes (`teardown-remediation-qa.md`, `tiktok-discovery-qa.md`), and prod-support scripts (`push_lakeview_to_prod.py`, `seed_test_dispositions.py`).

`sim-runs/` is gitignored — per-machine pre-ship simulator-gate evidence (`docs/runbook.md` § Pre-ship simulator gate), not committed history. Any `**/scratch*/` subfolder is likewise gitignored throwaway.
