# Saved projection reads

Date: 2026-11-07. Base: main `57b8d7c3`. User-directed performance work; backend-only resource improvement, not evidence of a 200 ms result.

## Scope and contract

Saved projection views currently read full durable run rows, including large private input snapshots that no view returns. The latest view independently loads success and attempt even when they identify the same run, then decodes the same result twice.

Select only the explicit public row fields, retaining exact run-ID, account and league predicates. Read the latest view's unique success/attempt IDs together; share the row and decoded public object within that request when both IDs match. Other authenticated read/export/cancel lookups use the same column projection. Scenario baseline creation deliberately retains the full snapshot read because it needs those immutable inputs. Worker and account lifecycle paths are untouched.

Preserve all API keys, values and status codes, including duplicated `run` and `attempt` objects on the wire. This change removes unnecessary database transfer and duplicate JSON decoding; it does not reduce the public result's wire size or change Home's API contract. No persistent cache, schema, feature flag, background work, mobile edits, model/configuration changes or weekly schedule changes.

## Verification

Use isolated synthetic SQLite rows and captured SQL to prove excluded snapshot/input/control columns, exact ownership filters, one result query for same or distinct IDs, no query for no IDs, missing/deleted/wrong-owner cases, and unchanged current/stale/running/failed states. Compare authenticated API responses against the previous full-row read path, including detail, export and scenario baseline behavior. Retain read-only GET tests. A synthetic large-snapshot fixture demonstrates avoided selected bytes without production access, copied databases or PostgreSQL JSON casts.

## Required scope checks

- Analytics: no event change; no latency claim from query-count evidence.
- Schema and flags: unchanged; rollback restores previous read implementation.
- UI and test IDs: unchanged, no simulator or Maestro.
- Docs: update API/architecture read-path notes and TEST_LEDGER. No data dictionary, config, glossary or cross-client constant change.
- Release: independent review and exact-head CI before any merge. Backend source revision changes require coordinated Calibration handling by the release owner.
