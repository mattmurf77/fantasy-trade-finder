# Consumed pricing domain, remaining engine boundaries

This is a real execution seam: `OwnerPricingExecution.generate()` and `.evaluate(cards)` call the existing actual model functions with fresh detached kwargs and the same immutable `PackagePricingPolicy`. Both full evaluations still run, with independent search caches. It is unwired from serving, Calibration and preparation. It is not proof reuse or a complete coherent engine.

## Capture and consumption

1. `capture_owner_pricing` observes the existing envelope inventory and freezes supported request data. Unsupported config shapes/numbers return a reason. Config precedence is effective trade config, raw owner-limit lookups, then explicit request config, matching the existing constructor. Nonfinite/non-numeric values refuse, so the experiment cannot silently consult a live fallback limit. Private `_pricing_policy` is excluded from the serialized user-kwargs schema.
2. Sample the actual first-round classifier once for every player-universe ID. Preserve its effective memo results; this does not attest the underlying generic-pick table's freshness. Missing/unknown offer IDs refuse explicitly, including raw-sum or disabled overpay branches. Never fall back to a live classification after capture.
3. Own copied numeric config and boolean masks behind read-only mappings. The crown flag is a captured boolean. The mode is `market`, matching all owner entrypoints' existing forced mode. The execution fingerprint covers the original envelope and this policy/mask data; equality still has no authentication/currentness authority.
4. Each operation materializes fresh Player/League/board/preference values. It enters the existing thread-local full config overlay and passes the private policy explicitly. No process globals are replaced. The owner constructor requires matching complete config, avoiding a mixed explicit policy and unrelated value conversion config. Nested scopes and exceptions restore the prior overlay; concurrent workers remain separate.
5. The unchanged package arithmetic consumes policy values through `price_consensus_package`/`overpay_ok` → `package_value_v2` → `_package_value_market`. The V3 incidental-RB companion overpay check also receives the same policy. Default `pricing_policy=None` follows live configuration/flags/mode/classifier behavior. Formula order and rounding are unchanged.

## What is and is not established

| Domain | This unit |
|---|---|
| Request Player/League/board/preferences/selections | Owned fresh data on every call, with the envelope's exact-type/order/float and unsupported-input rules |
| Numerical config used by owner/pricing | Complete resolved override for each operation; explicit pricing reads come directly from the immutable policy |
| Crown flag, owner pricing mode, pick mask | Explicit immutable values consumed throughout pricing, including the V3 companion path |
| Native generation and final owner proofs | Independently computed; no occurrence cache or certificate; existing selection/eligibility checks remain |
| Tier order/bands, age functions, roster eligibility/assignment, other model constants | Still live/unbound; no whole-engine same-input guarantee |
| Source provenance | V2 observation remains not rebound; V3 explicit evidence stays a kwarg. Original serving context remains separate |
| Capture coherence and freshness | Non-atomic; no writer coverage, ABA protection, provider ingestion guarantee or account/request epoch fence |
| Other serving gates/publication | Untouched. Roster/ownership, significance, quality, dispositions, authorization, supersession and durable publication still apply |

The helper does not lock a database or source, replay loaded code, restore alias topology, install age/tier/roster tables, or make arbitrary externally constructed objects authoritative. A malicious concurrent writer is outside this observation contract. This limited domain can now be extended through explicit dependencies; it cannot yet justify dropping duplicate final owner evaluation.

## Smallest next unit and stop condition

The next bounded extension should own tier bands/order and finite per-player age-derived values, then explicitly supply the roster solver's legal-edge map. Keep shared formulas with unchanged default wrappers. Avoid copying implementations, rebinding function globals or temporarily replacing module tables. Independently inventory and test all consumers, including imported aliases and V3/native lineup helpers.

After all consumed values are actually bound, a separate currentness/atomicity policy must define what an in-flight edit does. Only then can a request-local proof-occurrence registry be considered with full-evaluation fallback and every serving gate preserved. Repeated first-publication and real phone cold/network/failure evidence remain necessary. This unit makes no latency or capacity claim and does not activate preparation or the optional decoder.

## Release handling

Keep this branch unmerged while the parent coordinates Calibration source freezing. These non-test backend changes alter its whole-backend code identity on deployment. Unexposed snapshots may need repreparation; exposed/answered comparisons stay frozen. No production action is included in this experiment.
