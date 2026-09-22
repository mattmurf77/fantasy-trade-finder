# Release CI: expired synthetic session fixture

2026-09-22. Test-harness-only repair; no application runtime, auth policy,
generation logic, schema, production setting or CI gate changes.

[PR304 first hosted run](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/35725439638)
tested head `29acac6432df6e2892d0e181a7ee08b3648c7280` on Python3.12.14:
6,860 passed, one optional-data skip, one failure in734.50s. Three other jobs
passed. The failed `test_m2_11c_qc_branch_is_skipped_under_scope` received401
`session_expired` instead of200. Release did not proceed on that red check.

The rookie-scope fixture registered `last_active=0.0`, immediately older than
the production four-hour idle threshold. The live cleanup thread sweeps every
300s; its second tick coincided with the failure. A successful request normally
refreshes activity, so this is evidence of a vulnerable pre-first-request fixture,
not proof of expiry after successful repeated requests. CI does not identify
the loop iteration. Missing SQLite table warnings are consistent with the
fixture's thread-local in-memory connections and caught cleanup operations;
they do not establish a production database fault.

Use `time.time()` at fixture construction, as real sessions do. Preserve every
HTTP200/QC-suppression assertion and all production expiry behavior. Do not
disable cleanup globally, introduce StaticPool changes, rerun blindly until
green, or loosen the feature test.

The new `test_route_fixture_starts_inside_session_idle_window` was proven RED
against the original epoch-zero fixture (one failure1.27s), then GREEN after
the timestamp fix. Focused rookie-scope, persistent-session and request-scoring
tests: **61 passed in2.31s**, isolated SQLite, local Python3.14.4. This does not
substitute for the new full hosted run. Independent Astra review confirms the
minimal fix and the causal-claim limits above.

Runtime `backend/server.py` remains SHA256
`0b24ad25d90c23e2306282d6d96f30f99414da6d046cc971cf92710ace6f2ea6`.
Only this test file and documentation change after the previous release head.

The completed [starter-impact plan](starter-impact-plan.md) and three primary-
source/internal research reports are included in the replacement release head.
Independent review found source recommendations and bilateral weekly/season
design aligned; parent clarified fixed calendar horizons, exact cache content
identity and pending-release wording. All local links checked; no projection
pipeline, purchases or model changes were implemented. Full CI/merge/deploy/
activation are still pending at the time of this repair record.
