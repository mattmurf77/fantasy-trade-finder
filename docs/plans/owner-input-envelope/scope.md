# Offline owner evaluation input envelope

**Date:** 2026-11-07  
**Entry point:** authorized next bounded unit after rejected scalar latency trials  
**Base:** calibration PR612 `e0aa9e36f9b62bdbabc5d9e0e905a1dceabd0067`, fast-forwarded from freshly fetched main  
**Disposition:** offline helper and differential oracle only; no activation

**Release hold:** keep this branch unmerged until the parent coordinates Calibration. `outlook_calibration_adapter.code_revision()` hashes non-test Python files throughout `backend/`; adding this unwired module changes that identity on deployment. This is not a behavior change to normal trade serving, but it can stale unexposed Calibration snapshots. Existing exposed/answered comparisons remain frozen. No latency improvement is claimed.

## 1. Analytics scope

No events or production collection. Synthetic tests and aggregate offline measurements establish input preservation, unsupported cases and proof parity. Private boards and provenance must not be emitted to public cards, logs or new persistence.

## 2. Schema and flag scope

No database, API, client, feature flag, environment or dependency change. New helper types represent an owned immutable observation, not a currentness/consumption certificate. They cannot authorize evaluation skipping. Existing serving and calibration imports/wiring remain unchanged.

## 3. Evidence scope

- Preserve evaluator kwargs, full known Player/League/LeagueMember fields, ordered sequences and dictionary iteration order, numeric types, set membership, both boards and sources, preferences, selections and explicit v3 evidence.
- Bind explicitly observed effective config/flags, loaded tier/roster/pick/age tables and declared implementation identity. State unbound dependencies and capture non-atomicity; do not claim a complete execution identity.
- Keep v2 object-bound provenance as an observed sidecar. Materialization returns evaluator kwargs only and does not manufacture new provider/object-identity authority or a serving context.
- Reject unsupported graphs/types/keys/models with a structured reason; no `default=str`, silent drop or mutable retained input.
- Tests cover alias mutation, encoding types/order, cycles/nonfinite/subclasses, unknown fields, both-side and unrelated-player mutations, ambient changes and complete native/final proof parity on controlled stable fixtures. No normal evaluation or quality gate is bypassed.
- No mobile structure/test IDs, simulator/Maestro or device latency claim. No runtime speedup follows from an offline capture helper.

## 4. Documentation

| Document | Disposition |
|---|---|
| API/data dictionary/config/cross-client/glossary | N/A: no external contract/schema/flag/domain change |
| Architecture/HLD/LLD | N/A: no runtime wiring or established execution contract changes; explicit offline limitations documented beside this scope |
| TEST_LEDGER/HANDOFF | Update verification and next coherence obligations |
| Evidence and dependency inventory | [inventory.md](inventory.md) and [validation.md](validation.md), including declared coverage and exclusions |

## 5. Gate

Parent owns review/full CI/merge. No production changes, provider/customer data, purchases, new services or routing/activation. The coherent consumption boundary and proof registry require separate implementation/review. Until then, existing full evaluation remains authoritative.
