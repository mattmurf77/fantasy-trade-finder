# Feature Scope — evidence-bound dynasty outlook candidate

**Date:** 2026-11-06
**Entry point:** direct authorization following independent dynasty outlook research
**Builder:** outlook model implementation agent; separate research and evaluation reviewers
**Operator sign-off on waivers:** not needed (no waivers)

## 1. Analytics scope

- [x] **(b) Existing events cover it:** `trades_generated`, `trade_card_viewed`, existing immutable owner request/offer snapshots and deck outcomes retain version, exact terms, preferences and action evidence. No new events or probability/acceptance claims. Candidate evidence extends the existing private proof, never the public counterparty board.

## 2. Schema & flag scope

- Tables/columns: none. Existing model-config registration only.
- Feature flags: none.
- Model config: `owner_outlook_evidence_enabled`, default 0; exactly 1 requires existing bilateral and revision selectors. Selects `owner-v2-bilateral-3`; setting 0 restores -2 without rewriting historical evidence. No production activation in this work.
- No KTC, public Calibration, paid access, website456, prepared inventory or fast-decoder changes.

## 3. Evidence scope

- Unit tests: new outlook policy/input/generation/route regressions, prior owner/bilateral tests, full backend suite.
- Structural guard: existing mobile structural suites and test-ID lint; no client source or test IDs change.
- Code-walk: `architecture.md` in this folder will trace capture, constructor, evaluator, presentment, version and rollback fences.
- Manual TestFlight: no new binary or changed client interactions; production activation is withheld pending independent output review/full CI. Existing runtime coverage is not claimed by backend tests.
- Required acceptance cases: QB27/28 and WR/TE25/26 no categorical sell; true25 versus missing/imputed25; RB22/32 same personal tier has different known age/window evidence but no tier-derived longevity; missing QB role/production remains unknown; actual QB/SUPER_FLEX/FLEX slots with replacement alternatives and full roster; both managers and explicit selections; immutable old proofs and default-off hashes; unchanged package/stud/fairness/ownership/untouchable/full-roster gates and budgets.

## 4. Docs scope

| Doc | Disposition | Section / reason |
|---|---|---|
| `docs/api-reference.md` | updated | New opt-in generator identity; unchanged public response shape |
| `living-memory/LLD.md` | updated | Strict evidence kwargs and version-fenced immutable capture |
| `docs/architecture.md` | updated | New candidate wiring and age consumption |
| `living-memory/HLD.md` | updated | Reference to candidate policy and missing forecasting layer |
| `docs/cross-client-invariants.md` | n/a | No shared client constants/enum contract changes |
| `docs/glossary.md` | updated | Window evidence versus dynasty roster proxy |
| ADR / `DECISIONS.md` | updated | ADR-026: conservative neutral production fit pending actual evidence |
| `docs/config-reference.md` | updated | Dark selector, dependency and rollback |

## 5. Ship gate declaration

- No express lane. Parent owns push/PR/merge and any later activation.
- Full backend tests, mobile typecheck/structural checks and test-ID lint must pass on final SHA; independent output review must finish before activation. No simulator/Maestro.
- Results recorded in `living-memory/TEST_LEDGER.md`; frozen independent evaluation retains empty/failed requests and separates synthetic evidence from real observations.

## Policy and input contract approved for implementation review

Source audit found age, experience, injury/depth-chart metadata but no qualified production history, role timestamps, starting probabilities, scoring-compatible future projections or cut evidence on the owner request path. Historical forecast storage is a separate unconnected pipeline; old September counts are not asserted current.

V3 receives a strict optional `input_evidence` kwarg containing validated age rows detached from the existing pool-bound sidecar. Missing/invalid/unbound/imputed ages remain unknown: never fall back to legacy `Player.age=25`. The private candidate age channel exposes validated age or None; shared/public Player objects and existing market pricing remain unchanged. V3 fit, eligibility and diagnostic age rules never fall back to raw Player.age. Exact request evidence and proofs identify consumption separately from collection-only -2 evidence. No provider calls or new DB reads.

Player future-production fit is neutral with explicit uncertainty until actual role/production/projections exist. Remove all age-only categorical fit and personal-tier RB longevity exceptions in v3. Preferences continue to authorize desire; future picks retain a capital-direction thesis, not projected production. Age and position/window endpoint facts remain private diagnostics, not a second market multiplier. Default interpretation of existing outlooks: contender/all-in current through next season; rebuilder next one through three seasons; tanking two through four. These are disclosed provisional scenario windows, not asserted manager answers. Unknown outlook has unknown horizon. No new scored historical-quality branch: proven/developing/fragile classifications remain unknown until a real qualified adapter exists.

Use existing legal lineup assignment on raw market values, without `age_now_mult`, as a clearly named roster-price proxy. Actual observed slots determine eligible alternatives, including non-QB SUPER_FLEX replacements; estimated slots remain labeled. The marginal proxy is separate from window evidence. Rebuilding support uses .05 times the negative-only normalized delta and construction .025 times the negative-only marginal delta; contenders retain .25/.15. These are bounded normative policy weights, not forecast estimates. Full before/after roster QB inventories and actual assignment replacements are captured; no claim that all roster QBs have NFL starting jobs or that a SUPER_FLEX slot requires a second QB. Unsolicited QB depletion can be a price-proxy tradeoff, never an age-driven future gain; explicit selected sells remain authoritative subject to existing safety gates.

Preserve construction budgets, package shapes, exact selection/ownership/untouchable/own-pick protection, market/stud/overpay gates, term efficiency, both-manager support and final served roster checks. Candidate construction, evaluator, private proof and presentment use v3 identity; -1/-2 immutable proofs remain untouched. Shared code changes must demonstrate old-version parity.


## Reviewed amendment after first independent replay

The first candidate allowed RB-centered rebuild buys from market terms alone. The corrected candidate requires incoming-specific desire for every max-market incoming RB headliner: selected receive, declared target/acquire-RB, or known positive personal preference. This applies to both managers and every age, not an old-RB ban. Lower-priced RB companions need their own desire, or an independently desired non-RB headliner / net-capital-gain pick headliner AND necessary unchanged price consideration. A smaller price alone cannot bypass the thesis. Contender pick spending no longer earns positive plan fit. The first replay is retained as a failed candidate observation, not erased.

Prepared payload changes are restricted to registering the new proof identity and testing same-version adoption / cross-version refusal; the existing inventory enablement is untouched. A bounded v3-only assignment cache reuses the same full legal solver for support and diagnostics, with no approximation or budget change.
