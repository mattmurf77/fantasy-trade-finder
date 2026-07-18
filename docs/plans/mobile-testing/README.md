# Mobile Testing System — Doc Suite (2026-07-10)

Dual-agent-validated documentation for the FTF iOS testing system (three layers: Maestro simulator matrix → release-build gate → TestFlight on real iPhone via iPhone Mirroring). Supersedes `../claude-xcode-testing-plan-2026-07-09.md`.

| Doc | What it is |
|---|---|
| [plan.md](plan.md) | Plan rev 3 — spikes S1–S3 (gating, with abort criteria), workstreams W0–W5, critical path, 12–15 day estimate, risks, open operator questions |
| [prd.md](prd.md) | Requirements R-01…R-32, success metrics M1–M9, guardrails G1–G5, MVP cut line, kill criteria |
| [hld.md](hld.md) | Architecture C1–C9, decisions ADR-1…10 (fixture seam, flag pinning, injection blueprint, reset scopes, gesture policy, matrix pruning, QA-account Layer 3) |
| [lld.md](lld.md) | Exact interfaces: script CLIs + exit codes, `app.config.js` env contract, seeder + profile schema, run-report schema, runner pseudocode, testID registry, edge-case table E-01…E-20 |
| [test-cases.md](test-cases.md) | 201 per-feature cases (45-case P0 gate, 10-case smoke set, 12-entry NOT-AUTOMATE register, coverage audit of all 82 inventory features) |
| [app-inventory-2026-07-10.md](app-inventory-2026-07-10.md) | Ground-truth app snapshot (v1.5.3): screens, flows, API surface, state, hazards, feature list #1–#82. Regenerate on material app change → re-audit coverage |
| [reconciliation-log.md](reconciliation-log.md) | Dual-agent review history: 5 rounds, 12 blocking objections raised and fixed, zero unresolved |
| `layer3-reports/` | One report per TestFlight build once W3 is live |

**Start here to implement:** plan.md §3 (spike S1) — nothing else starts until the three spikes pass.
