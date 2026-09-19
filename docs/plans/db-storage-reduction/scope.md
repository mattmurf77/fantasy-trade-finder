# Feature Scope — database storage incident

Date: 2026-09-15. Direct user request: implement storage recommendations and recover full DB. No express lane or gate waivers.

## 1. Analytics scope
Existing deck_impressions, deck_outcomes, trade_impressions remain the records of generated/served candidates and explicit viewed/actions. No emitters, sample rates, card limits or denominators change. Heavy debugging fields use scoped references; numerical features, frozen valuations and all outcomes remain inline/durable.

## 2. Schema & flag scope
Add deck_diagnostic_snapshots: immutable content-addressed diagnostic JSON, scoped to user/job with creation time. New tables use metadata.create_all. Atomic writes with impressions. Private export/deletion manifest includes snapshots. No feature flags. Add FTF_DECK_DIAGNOSTIC_RETENTION_DAYS (14 default; 0 disables expiry). Legacy inline rows stay readable; explicit resumable maintenance converts them after backup. The retention policy only applies to these debugging snapshots; no impression/outcome/valuation deletion.

## 3. Evidence scope
Backend tests: exact diagnostic round trip, dedup across repeated context, isolation across users/jobs, atomicity, retention batching and active evidence preservation, legacy compatibility, account export/deletion. Existing trade/receipt/learning tests plus full CI. New tests must fail under named sabotage. Mobile structural/test IDs/manual TestFlight: n/a, no client or rendered behavior changes; runtime verification is deployed commit, database writer/maintenance and health evidence.

## 4. Docs scope
Data dictionary: new storage representation, retention, private lifecycle. Architecture: write path/shared diagnostic store. Config reference: retention knob. Runbook: headroom, backup, bounded compaction, vacuum caveats and rollback. API reference: additive account export table, no other route changes. HLD/LLD compatibility stubs untouched per root AGENTS. Cross-client/glossary n/a. Architectural choice recorded with this scope: normalize diagnostics and preserve complete core evidence; don't reduce returned cards or bias analytics to cut storage.

## 5. Ship gates
Full pushed-SHA CI: backend, mobile, testid, web. Ledger and incident evidence. Minimal Render disk increase/resume authorized to restore incident headroom; no compute change or autoscaling. Maintenance only after recovery point and validated backup, with bounded transactions and verification. No bulk table deletion or unreviewed vacuum full.
