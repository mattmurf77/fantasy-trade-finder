# Feature Scope — owner ranking authority and trade-mode policy

**Date:** 2026-09-05

**Entry point:** direct owner implementation request, following the owner-decisions engineering handoff

**Builder:** Astra Ultra policy subagent, `codex/owner-contracts-policy-20260905`
**Operator sign-off on waivers:** not needed; no waivers

Source of truth: the September 5 owner-decisions handoff and interview response log in the shared project root. Baseline: fresh `origin/main` `5cf34182374a80159e13d22ba7989eba1697b6ff`. This is a bounded implementation, not approval of the older brief's market floors, personal-surplus-primary ordering, method confidence hierarchy or deck quotas.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `trades_generated` records generation, `trade_card_viewed` separates actual viewing, and `trade_proposed`/`trade_declined` record existing action semantics. `stud_tax_mode_changed` records deliberate setting changes if that separately coordinated correction proceeds. Existing deck impressions/outcomes and valuation/shadow snapshots retain served assets, viewer/partner board evidence, generator arm and policy variant: they permit comparing selection, subsequent actions and fallback usage without a new client event. Their existing enablement is unchanged. This change does not claim that dark snapshots are currently being collected or add a new exposure definition. The parent owns offer/action attribution work and the integrated analytics documentation.

## 2. Schema & flag scope

- Tables/columns: none owned by this slice. Preserve existing per-player `member_rankings.confidence_source` provenance; coordinate an additive in-memory per-player map through parent-owned database/server readers, not a new schema.
- Feature flags: none added or changed. Preserve `current`/`challenger`/`gen_v2`, every live/dark flag, experiment assignment, threshold and package-pricing coefficient. Existing intent enablement remains authoritative.
- Env/model-config keys: none added or changed. In the **dark policy** known deliberate entries use full personal authority rather than method-dependent blending; absent entries fall back individually. The live generator shrink function is deliberately unchanged: applying this rule there broke historical arm-A golden output, and the parent required preserving that experiment baseline. This slice does not claim equal authority is fully live. Unresolved loss caps, within-tier upgrade/close-value thresholds, soft-Untouchable premium gates, and pick forecasts are not invented. Revert the scoped commit to roll back; do not activate the dark policy to roll out these corrections.
- Stud-tax proposal pending coordination before code: normalize saved/legacy `off` to the existing default `market`, preserve `heavy`, accept legacy writes as a compatibility alias, with no destructive bulk database rewrite. Parent owns route/database normalization and final decision.

## 3. Evidence scope

- Structural guard: backend-only slice; no mobile code or test IDs authored here. Parent/mobile slice owns integrated source guards and `testid-lint`.
- Unit tests: focused owner-contract regressions plus existing `test_trade_intent_modes.py`, `test_asset_ideas*.py`, `test_trade_policy.py`, `test_trade_policy_wiring.py`, `test_trade_engine_v2.py`, `test_trade_optimizer.py`, `test_trade_gen*.py`, and stud-tax coverage where affected. Tests run hermetically; record actual selection/results and named red-before-fix sabotage in `policy-code-walk.md`.
- Code-walk proof: `policy-code-walk.md` records input sources, mode classification versus market companion pricing, confidence/provenance behavior, retained gates and explicit deferrals with file:line references.
- Manual TestFlight checklist: the parent/mobile slice will own integrated navigation/settings checks. For this slice, a controlled personal/market tier disagreement must show matching Tier up/Same value direction and preserve market-priced companion values. The written checklist is not runtime evidence; no physical-device run is claimed.
- Test IDs: none added/renamed. Per D-056 no Maestro execution, authoring or simulator captures.

## 4. Docs scope

| Doc | Disposition | Section / reason |
| --- | --- | --- |
| `docs/api-reference.md` | Parent integrated update | Personal-tier asset-ideas semantics and any approved legacy Off normalization. |
| `living-memory/LLD.md` | Parent integrated update | Per-entry personal authority/fallback and compatibility handling. |
| `docs/architecture.md` | Parent integrated update | Per-player provenance shared across policy seams, generator identities unchanged. |
| `living-memory/HLD.md` | n/a | No new client, subsystem or major architectural flow in this slice. |
| `docs/cross-client-invariants.md` | Parent integrated update | Personal-tier mode language and approved stud-tax enum compatibility. |
| `docs/glossary.md` | n/a | Reuses existing tier, consensus and package-adjustment vocabulary; no new user term. |
| `DECISIONS.md` | Parent integrated update | Latest owner authority supersedes historical method-confidence assumptions; unresolved pricing rules explicitly deferred. |

Parent also owns the initiative index and central test ledger; this subagent supplies exact evidence and scoped commit, not a claim that central docs are already updated.

## 5. Ship gate declaration

- Parent runs integrated backend tests, mobile typecheck/structural checks and test-ID lint. No push, merge, production mutation or release is authorized to this subagent; no CI-on-pushed-SHA claim is made.
- Actual focused results and remaining failures are handed to the parent for `living-memory/TEST_LEDGER.md`.
- Any operator TestFlight checklist remains pending until physically executed and recorded.
- Express lane: **no**. No implicit gate waiver.

## Final narrowed implementation boundary

Implemented here: raw-personal-tier precedence in the existing post-generation intent filter, including the two direct generator-adapter seams in `bakeoff_runner.py` (argument-only changes, profiles unchanged); personal-tier Same value membership for `lateral_scope="tier"`, with unchanged consensus package prices; row-level provenance-aware authority in the dark policy. Parent integrates existing-column provenance read wiring.

Not implemented here: live generator shrink-rule changes, broader candidate-universe fallback, asset-ideas Upgrade/Downgrade band reclassification, removal of implicit same-position restrictions, soft-Untouchable pricing, forecasts or any stud-tax migration without the requested owner answer. Two broad candidate/position patches were rejected by the safety reviewer and were not applied. Parent explicitly directed preserving historical profiles and deferring these expansions. Detailed evidence and exact remaining sites are in `policy-code-walk.md`.

## Upfront amendment — public counterparty-value redaction

2026-09-05, parent-authorized privacy follow-up before code. The owner permits sharing acquisition interests/Untouchable signals, not private partner tier placements or derived personal values. The current public serializer exposes two exact partner-derived numbers: `rationale.counterparty.own_board_gain` and `meso_variants[].recipient_value_delta_pct`. Tracked mobile/web/extension sources have no consumer or wire type for either structure. The current counterparty timeline contains only categorical outlook and declared/inferred source; the remaining rationale fields are qualitative roster/timeline-fit explanations.

- **Analytics scope:** existing `trade_card_viewed`, `trades_generated` and deck impression/outcome attribution continue unchanged. This is output redaction, not new collection; internal generated cards and privileged snapshots retain both values for existing evaluation. No event/property changes or waivers.
- **Schema/flag/config scope:** none. Redact only those two fields using copied dictionaries at `trade_card_to_dict`; retain the viewer's own number, qualitative explanations, MESO shape and asset IDs. No generator math, flags, DB or experiment changes. This is a known-field fix, not certification of every public endpoint or possible future field.
- **Evidence scope:** a dedicated backend privacy test covers the real `GET /api/trades` route, serializer output, original-card immutability, and no-rationale/no-variant behavior. Tests first fail against the unredacted serializer, then pass. Existing generator tests continue asserting the internal values. Code-walk and exact results are appended to `policy-code-walk.md`. No mobile structural/test-ID changes; D-056 prohibits Maestro/simulator use. Optional manual TestFlight check: existing trade cards and alternatives still render; no new UI needs device-only proof.
- **Docs scope:** this slice updates only the exact affected `docs/api-reference.md` card-shape example and its explanation. Parent owns the integrated `living-memory/LLD.md`, `DECISIONS.md` and central test ledger. `docs/architecture.md`/`living-memory/HLD.md`: n/a, same existing serializer boundary and no new wiring. Cross-client invariants: n/a, no shared enum/constant. Glossary: n/a, no new domain term. The initiative index remains parent-owned.
- **Ship gate:** focused hermetic tests plus parent review before integration; parent reruns integrated CI-equivalent checks. No push, merge, deployment or production query by this subagent. Express lane remains **no**.
