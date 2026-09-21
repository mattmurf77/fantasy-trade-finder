# Structured diagnostic evidence — implementation and validation

Implemented against research baseline `c1805dc7` on 2026-09-21. This record describes code and local evidence; release/deployment status belongs to the parent release record.

## Production change

The owner publication path can pass structured feature dictionaries through `_log_deck_signal_impressions` to the existing synchronous `save_deck_impressions` writer. Captured request configuration, manager preferences and generation diagnostics retain their actual shared object identities until compaction. No broad fixture interning or content cache is introduced into the application.

`deck_diagnostics.compact_rows` now accepts either legacy JSON strings or structured dictionaries. It normalizes only nodes whose representation differs from a JSON round trip: tuples become arrays, JSON dictionary keys become strings with matching duplicate-key behavior, and previously `default=str` values become strings. Unchanged JSON-compatible nodes retain their identity. Normalization is scoped to a single compaction call, retains original objects against identity reuse and rejects cycles. Only detached feature roots are modified; original request/proof/report structures remain untouched.

The existing scoped hash, shared-node threshold, packing algorithm, 100-row insert limit and database schema remain in place. Every output row contains a JSON string before SQL insertion. All valuation, propensity, attribution, package terms and other non-feature columns retain their existing values. Each `save_deck_impressions` invocation commits all its pages and diagnostic snapshots in one transaction; failures roll back that invocation.

The logger also supplies the delivery agent's single-invocation publication seam: `structured_features`, `initial_publication_batch_size`, `publication_batch_size`, `on_batch_committed`, and `should_continue`. The default preserves one atomic save and legacy JSON rows. The owner streaming caller requests an initial 30 rows followed by 100-row batches. Board state, candidate-set context, served timestamp, presentation indices and global card ordinals are captured once for the full job. Callbacks receive only non-ghost cards and their committed impression IDs, after the batch save returns. Liveness is checked before row assembly and immediately before each save. Worker publication, partial-failure behavior, response paging and mobile handling are owned and validated separately by the delivery workstream.

## Focused verification

The following command passed **101 tests in 3.84 seconds**, using Python 3.14.4 and an isolated SQLite target:

```sh
python3 -m pytest backend/tests/test_structured_deck_evidence.py \
  backend/tests/test_deck_diagnostics.py backend/tests/test_deck_impressions_paging.py \
  backend/tests/test_owner_generator_routes.py backend/tests/test_bakeoff_serving.py -q
```

The new tests cover exact compacted-row and snapshot bytes against the legacy JSON path, unchanged source objects, actual shared-identity reuse, tuples/dates/numeric and duplicate JSON keys, circular data rejection, cross-user diagnostic access, mutation after commit, all non-feature columns, and rollback of both snapshots and impressions on a later SQL-page failure. Logger tests cover an initial 30 then 100 rows, one board query, global ranks, callbacks observing already-durable rows, no callback for a failed batch, supersession stopping subsequent writes, revocation during assembly caught immediately before storage, and exclusion of ghost-only batches from publication.

Named sabotage **CALLBACK_BEFORE_COMMIT** moved the save below the publication callback in an isolated in-memory recompiled logger. The durable-callback test failed RED; the untouched production implementation then passed the full 101-test command above. No application source file was changed for the sabotage.

An initial test command used a research-only environment without Flask/cryptography: 18 checks passed and five imports failed. The complete runtime command above resolved those environment failures. No evidence or assertion was weakened.

A full-suite compatibility check exposed a whitespace-only regression in the historical research adapter: native structured compaction now serializes already-packed roots itself, bypassing that adapter's former canonical serialization. The research helper now supplies canonical JSON for already-packed/plain roots, preserving its exact byte-idempotence contract without changing production formatting or the timed unpacked-root path. The existing exact-equality test remains unchanged, and an additional plain-root/no-mutation repeatability test covers the same boundary. Fresh research, structured-evidence, diagnostic and paging suites passed **33 tests in 2.60 seconds** after this fix. Historical benchmark artifacts remain unchanged.

## Actual-source-reference measurement

[Sanitized benchmark](structured-evidence-benchmark.json): three alternating samples per variant, same 2,843 bilateral-constructor cards, the real projected owner request and one real shared generation report, no fixture interning. The baseline logger and compactor were loaded from `c1805dc7`; the candidate used the production implementation. Both used 100-row compaction pages and one logger invocation. UUIDs and the logger clock were fixed; **no comparison fields were omitted**. Measurement covers real logger assembly plus compaction and excludes SQL, publication, construction, route/client work and setup.

| Variant | Samples, seconds | Median, seconds |
| --- | --- | ---: |
| Baseline eager feature serialization | 3.628, 3.775, 3.711 | 3.711 |
| Structured production path | 2.019, 2.027, 2.096 | 2.027 |

This boundary saved **1.684 seconds locally**. All 2,843 compacted rows, all 2,930 snapshot writes, and all impression-ID mappings matched exactly. The full source request and generation report also remained unchanged. This replaces the earlier broad-interning hypothesis with a measurement using real source sharing. It does not establish production savings, PostgreSQL cost, p95 or three-second tap-to-tile latency. The parent full-worker comparison measures the combined changes against the 2,354 cards remaining after significance checks.

| Content | SHA256 |
| --- | --- |
| Complete compacted rows | `27ed8acfc09668a3a17e341a33e5bc8b1acae3262f727d4f6f326015ccf439cd` |
| Snapshot-write content and order | `9dbe9a953ab56131fdd9c05e0e5adc9a24b8fa73d89da480acc1dbcc88bb3143` |
| Impression-ID mapping | `84d63bac2688a83ae871dd39f46aaa301e53d6e0bba7aacdf314108cd43d7f8a` |
| Private benchmark script | `9f47e7601e847d6835ba6649e9bae2ff40857ed1ad232e634096b001cc7098fa` |
| Measured compactor source | `6ceec11b1489cb2c8d5a7b24b4614ed48327033b7e380fe0b5bad9e7f1b07ee5` |

The operator-local benchmark script is `/private/tmp/benchmark_structured_actual.py`; private input remains outside Git. Its runtime was Python 3.14.4 arm64 on the same local machine and fixed hash seed, with socket egress blocked and cleanup threads disabled. CPU windows were coordinated with the parent and delivery agent. The repository production runtime is Python 3.12.3, so release CI and production observation remain separate evidence.

## Canonical documentation and rollback

Parent owns canonical edits: architecture should describe structured immutable evidence through compaction and commit-before-publication batches; data dictionary should clarify unchanged durable JSON columns and scoped diagnostic snapshots; API/runbook should document the delivery workstream's publication/failure contract. This work adds no schema, flag or model tuning. Disabling the structured logger option restores eager JSON assembly; disabling batching restores the original single-invocation atomic storage boundary. Existing stored diagnostic references and valuation rows remain readable in either direction.
