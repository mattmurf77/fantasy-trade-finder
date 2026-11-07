# Calibration provider capture

Date: 2026-11-06. Entry: user request to prepare the new comparison for every connected account/league. No production actions by implementation agent.

## 1. Analytics scope
Existing grading session source, status/errors, exact-version round report and answer records cover readiness and feedback. No new analytics events, organic impressions, ranking updates or provider writes. Provider errors remain aggregate counts without customer identifiers.

## 2. Schema and flags
No schema, configuration or model changes. Existing grading.outlook_prepare / grading.outlook_round control preparation/exposure; both false stop new work/exposure while exposed sessions remain frozen. Add calibration-only raw provider normalization. ESPN/MFL support is conditional on known account binding, fresh fetched rosters and completely represented rules. Stored credentials only; failures require honest reconnection outcomes. No arbitrary fallback to a standard lineup, no dropped roster assets and no fabricated picks. Normal serving is unchanged.

## 3. Evidence scope
Offline raw-shape tests cover exact slots/capacity, reserve/taxi, duplicate/missing/unmapped/out-of-domain assets, own/coowner credentials, changed bindings, authentic picks, and two-arm complete safety/proof execution. Lifecycle deletion/export/first-exposure suites must remain green. Synthetic raw fixtures are labeled as such; existing trimmed provider examples do not prove actual production coverage. No mobile code or test IDs change; no simulator/Maestro. Manual operator check after CI: inspect aggregate per-platform ready/error outcomes, open a newly prepared supported league and confirm captured date/blind grading, preserve already exposed history. Code walk and results will be recorded in validation.md and TEST_LEDGER.

## 4. Docs scope
| Document | Disposition |
|---|---|
| docs/api-reference.md | Update conditional provider coverage; no new route |
| living-memory/LLD.md | Update calibration capture normalization |
| docs/architecture.md | Update provider data flow |
| living-memory/HLD.md | Update conditional comparison reach |
| docs/cross-client-invariants.md | No constants/enum changes; wire shape unchanged |
| docs/glossary.md | No new domain terms |
| ADR / decision | Existing ADR027 extension recorded in architecture and this scope |

## 5. Ship gates
Exact-head full CI, independent provider review and ledger required. No express waiver. Parent handles commit review, push, merge and activation. Deploy changes backend code identity: every unexposed old snapshot must be re-prepared; exposed/answered snapshots stay immutable. The preparation batch must not claim all-ready if unknown settings or missing/expired credentials remain.

## Input and acceptance contract
Keep each provider snapshot separate from models: authenticated/previously authorized account-to-team binding, raw native-to-canonical map, exact supported starter slots, active capacity, inactive holdings, observed provider metadata and owned picks. Source stores only selected private facts, no cookie/token and no unrelated leagues. ESPN mapped slot IDs must be supported exactly. MFL min/max starter constraints must have a provably equivalent supported slot template; other configurations fail closed. K/DST/IDP and unresolved assets are explicit unsupported until the complete common gate can represent them. Preserve both complete model inventories, all gates and full budgets.
