# Offline owner-input observation contract

This first unit records a detached observation for controlled differential tests. It is deliberately **not atomic, not proof of consumed inputs, not provider-bound after materialization, and not authorization to reuse a proof**. Normal routes, workers, Calibration and model selection do not import it. No evaluation or quality gate is removed.

## Interface and ownership

`observe_ambient_inputs()` reads the declared ambient inventory below into detached native values. It may initialize the existing feature-flag cache; it never reloads settings or calls a database/provider. Unsupported custom proxies/callables raise `UnsupportedOwnerInput` with a reason and structural path.

`capture_owner_inputs(context, model_version=..., ambient=...)` accepts an exact native dictionary or the existing exact `OwnerInputContext`. It returns an immutable `OwnerInputEnvelope` or a structured unsupported result. The private JSON payload owns its complete representation; no input object is retained. Every read materializes a new detached tree. The fingerprint identifies the recorded representation, not a coherent execution, fresh provider state, authenticity, or eligibility. Direct construction of an envelope is not trusted authority either.

`evaluator_kwargs()` returns kwargs only. It does not install recorded global settings, replace code, reconstruct shared alias topology, or return a serving context. Serialization support does not validate all evaluator value semantics: the existing evaluator still decides whether a request/model combination is valid. `ambient_observation()` and `provenance_observation()` are diagnostic reads, never automatic overrides. No production persistence or logging is provided; payloads can contain private boards and must remain private.

## Declared inventory

| Source | Recorded values | Contract boundary |
|---|---|---|
| `server._owner_generation_context` (server.py:21624), owner `_Search.__init__` (trade_gen_owner.py:182) | Full supplied kwargs: entire player universe, league/members, both boards and sources, seed values, format, outlooks, preferences, ordered pins, scope/intent/opponent, fairness, exact/partial selections, exclusions/dispositions, budgets/config and explicit v3 evidence | All supplied fields are retained; omitted defaults remain omitted. Unknown top-level keys are refused. No projection to offer assets or selected owners. |
| Player/LeagueMember/League dataclasses (ranking_service.py:257; trade_service.py:4538,4739) | Every declared field, including unrelated-player ranks, metadata, board stamps, reserve/taxi/inactive/slot/capacity data when present in those fields | Exact known record classes only; missing/dynamic attributes and subclasses refuse. This does not ingest provider fields absent from the supplied context. |
| trade_service `_cfg_override`/`_c` (1367,1376), owner constructor | Effective trade config plus raw owner-limit lookups, supplied request config, current stud-tax mode | Effective and raw groups are separate because constructor precedence differs. Recorded values are not injected into subsequent evaluation. |
| ranking_service `_c` (177), feature_flags | Effective ranking config and current flags; missing cached flags resolve false, matching `is_enabled`, not shipped defaults | Unknown custom proxies refuse. Observation can race a writer. |
| Loaded engine/static state | Primitive uppercase constants of all four owner engines, tier order/config, roster eligibility/unavailability, generic pick seeds, age-curve function bytecode/defaults, outlook-alpha keys and optional-decoder enabled state | Known age functions with closures/custom callable types refuse. Loaded function globals/transitive overrides and decoder internals are not certified. |
| Implementation/runtime | Hashes of 11 explicitly listed source files; Python version/cache tag/byte order and one string-hash observation | File bytes do not prove loaded executable identity; the string hash is not a complete set-layout/seed attestation. No cross-runtime equivalence is asserted. |
| `trade_input_evidence.request_evidence` (154) | Detached evidence rows in a sidecar labeled `observation_not_rebound`; explicit consumed v3 payload remains a kwarg | Exact internal evidence wrapper/row types and safe field graphs are checked before any helper runs. V2 provider evidence is tied to original object identity. Fresh kwargs do not acquire that authority. Tests assert it becomes unknown rather than forge the binding. |

Each declared ambient group and required nested key is checked, including every current primitive model-constant name. New unrecognized context keys fail explicitly. Tests assert the context key inventory tracks the current owner constructor. These checks catch declared schema drift; they are not an exhaustive transitive dependency audit.

## Representation and unsupported cases

The tagged representation distinguishes bool/int/float, preserves finite float bits (including negative zero), Unicode, list/tuple distinction and native dictionary insertion order. Sets/frozensets record canonical membership only. Their reconstruction may change iteration layout; that remains explicitly unbound. Native duplicate references are copied independently, so alias topology is also unbound.

Unsupported types/subclasses, callbacks, cycles, nonfinite numbers, unknown models/keys, record schema drift, missing declared ambient keys and excessive nesting or JSON integer encoding limits return explicit reasons. No `default=str`, partial success or silently omitted field is used. A detected dictionary mutation returns `input_changed_during_copy`; undetected changes, especially change-and-change-back, are still possible. Before/after equal fingerprints never establish atomicity.

## Obligations before any proof reuse

1. Establish a complete dependency boundary and make both generation and final owner evaluation consume the same owned values, including configuration, flags and mutable tables. This is a separate semantics decision for concurrent edits.
2. Establish coherent capture/currentness with all writers and ABA-safe revisions, provider observation limits, both account lifetimes/seats and exact request epochs. Existing local observations cannot prove un-ingested provider state.
3. Rebind source evidence through a separately reviewed authoritative mechanism. Copying diagnostic rows cannot manufacture provider authority.
4. Add private request-local occurrence/ordered-package/proof identity and all-or-nothing fallback only after the above. Keep every roster, ownership, market, significance, quality, disposition, publication and supersession gate.
5. Prove full ordered output parity and repeatable first-durable-publication improvement before any runtime routing. Device/cold-process/network/failure attempts remain separate evidence.

The current full evaluator remains authoritative. No global preparation or optional decoder activation is part of this unit. See [validation.md](validation.md) for what the controlled oracle establishes and what it does not.
