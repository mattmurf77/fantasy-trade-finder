# Round 7 — retire unconsumed rejected-candidate serialization

Parent specification, September 22, 2026. The completed-simple-phase prototype
reaches a promising local first-durable lower bound, but its eight-context first
batch loses counterparty preference coverage/alignment and has worse seller
terms. Do not implement or activate that presentation change as an optimization.

Agent A: one bounded private equivalence experiment. The full search retains
53,170 decision objects, including49,334 rejections in the measured request.
Establish which rejected decision fields are actually consumed by generation,
companion expansion, caches and reports. Current per-candidate rejected snapshot
JSON is not itself the durable served-offer ledger; verify every caller before
relying on that distinction.

Only if proven unconsumed, let the INTERNAL generation search retain a compact
final rejection status/reason instead of repeatedly serializing and decoding an
unused rejection snapshot. All eligibility/authority/market/intent/compensation
checks still execute, with identical final reason precedence and counters. Every
eligible original/core proof and every published exact offer retains the full
unchanged immutable evidence. External single/batch evaluators must still return
their full rejection diagnostics. Do not delete required evidence, change search
budgets/inventory/order, suppress rejections from reports, or use an approximate
precheck as an eligibility decision. No persistent/global cache.

Prefer an explicit generation-only mode and a narrow final-freeze hook; do not
monkeypatch shared live globals or infer permission from a class name. The prior
single-freeze hook can be reused privately if needed, with its full contracts.
Instrumentation must fail the experiment if any consumer requests a discarded
rejection field. If callers need those snapshots, report that concrete result
instead of reconstructing them under later state or growing a lazy replay system.

Compare the complete native emitted cards/proof bytes, full generation report,
all rejection counts/per-partner budgets, final public/persisted inventory and
prefixes, and external rejected-evaluator results. Include invalid inputs, partial
selection, discarded companions, cache aliases and unsupported mode fallback.
Use fixed hash seed0, source/HEAD manifests and the unchanged full first30. Measure
actual worker first-durable/completion and peakRSS in an exclusive CPU window.
Keep C's proof-boundary experiment separate until independently approved.

Own private scripts and rejected-work-evidence.md only. No shared runtime before
parent review; one prototype maximum. This is an execution improvement, not a
new model, thinner served evidence or a lowered release standard.
