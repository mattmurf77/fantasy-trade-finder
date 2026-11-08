# Calibration cooperative yielding

Date: 2026-11-07. Entry: direct request following two physical Find Trade attempts without a first card. Base: fresh `origin/main` at `fabb5e36`. Root owns rollout; no production mutations or push in this slice.

## Problem and bounded change

Paired Calibration currently computes both full arms on its serial background thread without the execution callbacks already available in owner generation and final evaluation. It can contend for Python CPU with interactive trade jobs. Root's aggregate operational readback reported two roughly 59–66 s first publications during a queued Calibration rebuild; that observation is not a causal benchmark or proof of every device failure.

Thread a private scheduler checkpoint from the real durable queue into both arm generation and fresh owner validation and between coarse postprocessing stages. At most once per 100 ms of elapsed work, inspect the existing conservative live-job pressure predicate. While pressured, sleep in 100 ms increments, up to one second; then allow at least another 100 ms of monotonic elapsed time without advisory sleeping before checking again. This is a scheduling interval, not an OS/GIL guarantee of 100 ms CPU service. Scheduling pressure or unavailable pressure information never becomes an arm error, restart, smaller inventory, or partial publication. The foreground trade itself is unchanged.

Keep both arms, randomized execution order, all captured inputs and complete count budgets, suppression, roster legality, significance, presentment, quality, proof checks, lease heartbeat and atomic completion. Non-checkpointed provider/SQL stages remain bounded only by their existing operations. The current pressure predicate includes passive prewarm and old-league jobs; it is not an attended-search or global admission contract. No claim of 200 ms follows from this change.

## Analytics and schema

No new events, tables, flags, configuration or environment variables. Existing trade-job timing/evidence and Calibration build counts/status cover outcome diagnostics; retained local synthetic timing measures this scheduling intervention. No customer fixtures or export. Private callback is not serialized into proof/model inputs. Rollback is the code change, coordinated by root.

## Evidence

Planned pytest: deterministic throttling, bounded sleep, guaranteed progress under continuous pressure, idle/error behavior, both-arm callback forwarding and stage coverage, exact output/proof parity excluding elapsed diagnostics only. Source-bound full-arm parity and controlled mixed Calibration/trade first-publication and memory evidence must retain final hashes and serial conditions. Independent peer review follows. Mobile files/test IDs are unchanged, so no simulator, Maestro or new device-only assertion. Operator's final device check remains necessary to establish real delivery improvement.

## Documentation and ship gate

- API/schema/cross-client/glossary: not applicable; no contract/enum changes.
- Architecture: update Calibration dataflow with advisory bounded yielding; no new service.
- HLD/LLD conventions: unchanged; full quality and atomic build remain.
- This scope/code walk, existing initiative index and living-memory ledger record implementation/evidence/limitations.
- Full CI and root-reviewed integration precede release. Calibration source identity changes require root-coordinated unexposed comparison rebuilding. This does not preserve old proofs by weakening currentness.
