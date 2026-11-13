# Max PF moves fixtures

`v1-example.json` is the contract's §5.1 `ready` example exactly as it stood before v1.1
(D-261, 2026-11-13), copied out of `docs/plans/league-projections/max-pf-trade-away/contract.md`
at `origin/main` `cdaf10fe`. It is the v1 golden: `test_maxpf_moves_combined.py::test_v1_keys_unchanged`
pins that the served block still carries every one of these keys with the same JSON types, so
installed builds that read v1 keep working. Never edit it; a v2 gets its own file.
