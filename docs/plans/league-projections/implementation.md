# Implementation and remaining release gates

This is a default-off implementation for review, not an activated forecast service. The specification preserves its substantive requirements with private reference identity redacted; the later weekly-cadence instruction is in steering-addendum.md.

## Implemented

- Independent Decimal scorer, finite expected-event coverage contract, exact native position/flex assignment, actual lock and hindsight pools, negative points, and position-specific IDP bye counterfactuals. Healthy coverage has priority over hypothetical replacements; dual-position reassignment remains legal.
- Engine v3 uses a named mean-preserving positive-gap policy: actual Gaussian draws are unchanged, the latent Max PF mean shifts before flooring so the requested unrounded mean is preserved. Zero-gap and deterministic cases are explicit; negative dominance gaps fail. Advanced diagnostics distinguish target/latent/realized means and dependence; old-engine baselines cannot be reused for a weight-only comparison. Server-owned engine/baseline versions are pinned at enqueue and rechecked on worker admission/recovery; old/unversioned queued work fails without a view-triggered refresh.
- Shared-world actual-score/Max PF simulations, expected and modal W-L-T plus full record distributions, matchup probabilities, official Max PF baseline, realized projected means/quantiles, unconditional/conditional draft probabilities, and year/round-specific original/current ownership. Owner expected counts and probability of at least one pick are distinct.
- Immutable normalized consumed inputs, source hashes and exact capture times; semantic reuse ignores ingestion clocks while preserving source revisions and actual facts. Historical Max PF reconstruction discrepancies do not replace official aggregates.
- Durable viewer-owned run and target tables; account deletion/export coverage; target generation and worker-token fencing; one bounded recovery of an interrupted attempt reuses its captured snapshot. One serial worker, eight queued/running jobs globally, one per viewer, four requests per ten minutes, four new targets per dispatch. No partial result is published complete.
- Weekly Tuesday09:30 America/New_York configuration with DST handling. The existing15-minute cron checks eligibility only. New league synchronization registers a DB-only target for the next weekly slot. Repeated sync, league entry and roster changes never advance it. A separate projection-only cron supports isolated operator checks without notification routes.
- Existing mobile Projected standings and League Summary use the stored result under the new flag and disable legacy outlook reads in that mode. Home links to that same Standings screen. Web League Summary uses the same contract. Current official standings remain available. Fixed-width mobile probability columns, weekly explanations, coverage/assumption labels, saved-input40/60/80 comparisons and web CSV/manifest exports are included.
- Failed weekly refreshes retain the last success beyond the ordinary seven-day run-history retention. Read errors keep the same-context displayed result. League/account changes clear the old context. Numeric unavailable values stay null. Only admitted finite common-offense omissions receive explicit model-assumed zeros; all other unknowns remain unknown.

## Actual provider readiness — not complete

Native timing is now sourced from observed Sleeper scores fields, not invented raw projection attributes. Full-season schedule validation establishes byes. Captures crossing kickoff fail closed. Native fantasy eligibility, raw reserve/taxi membership, official aggregate PF/PA/Max PF and matchup reconciliation are preserved.

The raw expected-stat feed is sparse. The versioned `sleeper_sparse_offense_v1` candidate now admits populated RotoWire offensive forecasts only after three generic totals reconcile within an observed two-decimal rounding bound. It preserves every direct event, labels omitted common offensive events as model-assumed zero, derives finite native-primary position bonuses, and removes only explicitly registered scoring domains with no corresponding lineup slot. Manifest coverage lists every assumed key and provenance count. See [decoder evidence](decoder-evidence.md). Strict supplied-only mode remains available; old snapshots are never silently promoted to the candidate.

This establishes a usable ordinary offense scoring seam on admitted rows, not universal league coverage. Missing player rows, missing aggregates, required rare IDP/return events, and unreliable missing kicker bands still refuse a numeric result. The reference custom-IDP league therefore remains incomplete. Future participation remains an explicit conditional forecast scenario, not a verified probability. Live/mixed current weeks are unsupported by the initial ingestion path; pure optimizer lock behavior is tested separately.

The original November6 prototype and draft input package were not found. Existing preseason fixtures are not relabeled as that baseline. No original parity, held-out calibration, production p95, native device or numerical reference-league completion is claimed. No contemporaneously captured historical projection dataset is available for a leakage-free backtest; rebuilding past forecasts from today's data would not establish accuracy.

## Concrete activation decisions/evidence still needed

1. Review the bounded offense contract for activation; establish separate evidence before adding missing kicker/IDP/rare events or entire missing player forecasts. Keep unsupported categories explicit.
2. Record permission evidence for the new commercial consumption of the projection/stat/schedule/scores feeds, with required attribution and operational terms. Existing app integrations are unaffected by this gate.
3. Review proposed IR Max PF policy, reserve/availability assumptions, exact draft/seeding tie scenarios, variance proxy/correlation, sample threshold, weekly wall-clock time, retention and launch league cohort. Weekly frequency itself is confirmed.
4. Supply true historical as-of forecasts/outcomes for held-out evaluation and the original prototype artifacts if parity is still desired. Until then outputs are model/scenario estimates.
5. Run hosted cron readback/load checks and the TestFlight checklist after review. A configured existing cron is not evidence that this new job has run.

The two new feature flags and policy_approved remain false. No deployment, provider activation, GitHub push, production mutation or outreach was performed by this implementation agent.

## Scale and ownership boundaries

Snapshot/result reuse is currently viewer-scoped. Multiple viewers in one league can still repeat capture/computation; cross-account sharing is deliberately not introduced without a privacy/lifetime design. Large-cohort backlog and DB size need load measurement before activation. One last successful baseline per connected target is retained; superseded runs follow configured retention. No existing per-league Sleeper read-disconnect API was found; write-credential disconnection does not imply revocation of public read access. Each new capture revalidates the actual account's bound Sleeper owner/co-owner seat, not another account's credentials. Account deletion removes all targets and runs.
