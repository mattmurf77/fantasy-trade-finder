# Provider capture validation — 2026-11-06

- Runtime digest: `3aa0c12d6d65ffa570f6f4783b114fb035a2c81d77b8ef169ea010705768c8ef` (all backend non-test Python plus tier configuration, same code_revision policy as frozen comparison).
- Local **378 passed in24.00s**: all Calibration/new-round tests, linked-provider parsers/credentials/currentness, actual paired capture/gates, legacy blind grading, deletion scrub and session deletion transaction guards. Network blocked; isolated synthetic SQLite. Pycompile and git diff --check passed.
- Independent **69 passed in3.99s** at the identical runtime digest. Eight paired capture artifacts retain510 ordered full owner+roster proofs. Four positive ESPN/MFL × picks-on/off captures use real engines and all final gates; the MFL pick belongs to the actual exported current owner, ESPN excludes picks without allowed assignments. Raw-only unknown-price holdings remain outside all trade legs.
- Reproduced pre-window pick-cache substitution on both MFL and Sleeper now fails, while unchanged-source controls pass. Unknown native mappings, incomplete team count, unsupported slot/position/range constraints, missing exports, duplicate/invalid picks, stale format/season, wrong/coowner credentials, missing/expired/undecryptable credentials and changed stored bindings are covered.
- Existing immutable answers, first-exposure/readiness, private export, participant deletion/recreation and lease fences remain green. No new mobile binary, simulator or Maestro evidence; clients are unchanged. Full exact-head CI remains parent-owned.

## Code walk

- [Stored binding fingerprint](../../../backend/calibration_provider_capture.py#L34) retains semantic team/season/format/auth and credential revision without secret values.
- [Same-source pick ownership](../../../backend/calibration_provider_capture.py#L78) validates consumed MFL rows against the raw bundle; [capture](../../../backend/outlook_calibration_adapter.py#L206) applies the equivalent returned-refresh comparison to Sleeper.
- [Native eligibility](../../../backend/calibration_provider_capture.py#L101) qualifies both ranked and unranked safety assets while preserving the model candidate pool.
- [ESPN rules](../../../backend/calibration_provider_capture.py#L130), [MFL exact constraints](../../../backend/calibration_provider_capture.py#L202), [authorized provider read](../../../backend/calibration_provider_capture.py#L316) reject unsupported/unknown cases explicitly.
- [Shared full two-arm generation](../../../backend/outlook_calibration_adapter.py#L148) retains all gates and full budgets; no provider read occurs after capture.

## Operational limits

Synthetic fixtures do not establish the four connected production ESPN/MFL leagues' rule/credential coverage. Prepare sequentially after CI and inspect aggregate outcomes. Deployment changes source identity: reprepare unexposed snapshots; preserve exposed/answered cohorts. Native TEP verification is unknown for ESPN's configured/manual format. The comparison remains as-of and nonactionable, not a complete platform transaction-legality certification. Missing K/DST/IDP/custom support remains a counted failure, never an alternate arm. No production or remote write was performed by implementation.
