# Owned owner pricing execution — bounded scope

**2026-11-07.** Isolated branch `perf/owner-pricing-inputs` from fresh main `0eee4bb9`, with the reviewed offline envelope from PR615. Keep unmerged; parent owns Calibration release sequencing. No production activation or latency claim.

## Behavior and evidence boundary

Add an unwired execution API that makes actual owner generation and fresh final owner evaluation consume the same owned package-pricing policy and detached request values. The policy owns resolved numerical configuration, crown flag, fixed owner market mode, and sampled first-round pick classifications. Existing shared formulas retain arithmetic/rounding order; their default wrappers keep live behavior. No global swapping, proof reuse, output cap, budget reduction or quality-gate removal.

This establishes a consumed **pricing domain**, not a complete coherent engine. Tier/age/roster static reads, capture atomicity/ABA, model code mutation, source provenance rebinding, provider freshness, account/request currentness and downstream gates remain explicit obligations. Effective cached pick classifications are sampled as values; no claim that stale memo contents become authoritative provider facts. V2 provenance remains observed but not rebound. Explicit v3 evidence is preserved.

## Verification

- Stable-input complete generation/final-proof/report parity for owner/bilateral/current/outlook models and supported selected requests.
- Adversarial config/flag/pick-cache/player/board mutation after capture and between generation/final; nested and simultaneous contexts; unchanged live callers and exception cleanup.
- Unknown pricing IDs/invalid policy state fail explicitly, never assume zero/no exemption.
- Retained synthetic actual-worker full ordered/public/durable parity; no performance distribution or 200 ms inference.
- Independent review and full CI before any merge; release remains held even when CI passes.

## Analytics, schema, access and docs

No new event, persistence, provider request, schema, feature flag, dependency, route, client/API behavior or access policy. No customer data. Private policy/envelope values must not enter public cards/logs. [Contract](contract.md), [validation](validation.md), architecture's unwired-experiment note, and TEST_LEDGER/HANDOFF are updated. Data dictionary/API/config/client docs are N/A because their contracts do not change. No simulator/Maestro; normal test-ID and TypeScript CI remain intact.
