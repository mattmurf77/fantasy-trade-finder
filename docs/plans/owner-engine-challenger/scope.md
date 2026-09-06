# Owner-driven package construction challenger

**Date:** 2026-09-06
**Entry point:** Owner explicitly requested fixing the interview-to-generation gap and giving the new model a proper test.
**Builder:** Parent integration, separate Astra Ultra generator and route builders, independent Astra Ultra acceptance review.
**Baseline:** freshly fetched `origin/main` at `4c343a48`; isolated Fleeced worktree. Existing organization and legacy checkouts are preserved.
**Waivers:** none. Simulator/Maestro remains retired (D-056).
**Status:** implemented and locally validated; publication/release gates remain separate.

## Behavior and testable boundaries

Introduce a genuinely separate generator, attributed as `owner_v1`. Keep `current`, `challenger` and `gen_v2` code, profiles and control goldens intact. Do not relabel an existing arm or silently change its historical meaning. Construction must not depend on legacy both-board intersections, comparison-count shrinkage, or a requirement that both managers gain raw dynasty value before outlook/need is considered.

- Personal rankings identify desirable acquisitions/disposals and requested tier direction. Use consensus for each absent personal entry, not an arbitrary placeholder or missing-board exclusion. Deliberate ranking methods have equal authority.
- Owner clarification during implementation: **personal rankings + outlook + needs jointly determine the intended trade; market value determines workable terms**. Candidate-pool selection must use all three before truncation. An early cheap market veto is computational ordering only, not a product hierarchy that chooses targets first and checks team purpose later.
- Market package values, including the established consolidation/stud adjustment, guide the price. A personal preference is not permission for an unlimited overpay. Retain established market-safety ceilings; record the actual fairness setting and any permitted preference/outlook/need trade-off. Do not disable stud adjustment for this challenger.
- Evaluate both teams: declared outlook takes precedence over inference, and improvement may be personal preference, outlook utility or a meaningful positional improvement. A contender may trade future value for usable production; a rebuilder may do the reverse. Shopping/chasing influence priority, not universal position exclusions. Missing personal data must be distinguished from observed preference.
- Construct one-for-one and one-for-two/two-for-one asset packages first (picks are assets too). No organic three-for-three enumeration. Any broader search is explicit-selection-driven or an honestly labelled, measured small-search exhaustion fallback; broad results must not displace available suitable small offers merely because summed gain is larger.
- Honor explicit SEND, GET and partner selections. Try the full selected package first. Partial alternatives must identify omitted selected assets and never silently substitute a different requested target. Apply the same generator/evaluator on model deck, SEND-anchored search and More Offers/asset-ideas, including league buy/sell entrances that use those routes.
- Tier direction uses the user's tiers, with meaningful within-tier movement allowed. Market terms determine companion pieces. Untouchables are reluctance, not an unconditional ban: an unsolicited suggestion must offer an above-market, personally/outlook/need-compelling return with positional replacement where required. Exploring an explicitly selected asset does not rewrite saved preferences.

This is the construction/test slice. Causal Undo, complete original-offer display/14-day lifecycle and future-pick forecasting are separate work, not claimed complete by this implementation. Preserve existing security, ownership, rejected-interest and final legality protections.

## 1. Analytics scope

Existing `trade_card_viewed`, `deck_card_viewed`, `match_swiped`, `trade_proposed`, `deck_outcomes` and impression-linked pass reasons cover exposure, intent and response. No new event names are planned. Extend existing immutable impression JSON and bakeoff diagnostics, not client-visible private partner rankings.

Every treatment impression must identify generator/version, entry surface, exact package, experiment assignment/draft position, selection coverage, market package values, both private personal-value views with per-entry provenance/fallback, outlook and need context used, fairness limits, and construction/rejection summary. Frozen serve context and later manager-specific view/action times remain separate. Ensure selected-route cards receive real impression IDs and emit linked views, closing the present audit hole.

Measure outcomes using viewed impressions (not all generated cards), stratified by arm, surface, shape, league/manager and position. Report N with rates. Track small-package supply, no-result/partial-result frequency, generation time, market overpay, both-side fit, repeated headliners, likes, pass reasons and downstream matches separately. Sparse observational results cannot establish a winner.

## 2. Schema, flags and experiment scope

- Tables/columns: no new tables planned; use existing `deck_impressions` JSON, outcomes and `bakeoff_runs` diagnostics. Update data dictionary for new JSON/version/arm contracts.
- Shared feature flags: no new flag required; existing bakeoff policy plus new model-config include/serve controls own activation. No independent mobile flag.
- New model configuration: `bakeoff_include_owner` and `bakeoff_serve_owner`, both default **0**. Include enables generation/logging; serve separately authorizes exposure. Add bounded generator tuning only where needed, document experimental defaults and preserve baseline exclusions.
- Organic comparison: new arm joins existing team-draft attribution without replacing the three current controls. Treatment must not be silently reinterpreted or removed by the superseded personal-gain policy after it passes its own owner-aligned evaluator.
- Selected-route comparison: retain a labelled legacy control and owner treatment on the same surface; preserve complete package, ordering/assignment and exposure metadata. Generated-only treatment is not a served experiment. Never misattribute a legacy fallback to `owner_v1`.
- Rollback: serve=0 removes treatment exposure; include=0 stops its generation. Existing controls and stored evidence remain intact. No production switch is changed during implementation.

The versioned first-test utility uses raw personal package gain plus an outlook
component (coefficient 0.5) and a usable-roster-change component (0.25; rebuilding
0.05; tanking 0). These are provisional implementation choices, not calibrated
acceptance probabilities. They never rewrite personal tiers or market prices.
Recorded component values must make any permitted personal-value loss auditable.
Selection/pool priority incorporates outlook and needs jointly with personal
preference; these coefficients do not establish a rankings-first product hierarchy.

## 3. Evidence scope

- Unit tests: deterministic generator fixtures proving newly admitted candidates; incomplete rankings; outlook-asymmetric gains; market price independent of willingness; shape bounds; pins/partial coverage; tier direction; soft preferences; safety; bounded runtime and diversity.
- Integration tests: all entry routes reach shared generation when enabled; controls unchanged when disabled; immutable attribution and selected-route impression/view linkage; privacy; generation failures and no-result behavior; include/serve separation and cache compatibility.
- Mobile structural guard/typecheck: retain additive impression metadata when mapping selected results and emit existing linked-view events; no visual redesign or test-ID renaming planned.
- Independent review: audit implementation against owner-answer acceptance cases, verify actual candidate differences and inspect final parent diff.
- Manual TestFlight checklist: selected SEND, GET, partner, More Offers each direction and league buy/sell; verify recognizable simple packages, persisted Back context and correct partial notices. Checklist is not device evidence; no simulator substitute.

## 4. Canonical documentation

| Concern | Target |
|---|---|
| Route and additive response contract | `docs/api-reference.md` |
| Snapshot JSON / arm attribution | `docs/data-dictionary.md` |
| Shared generator and serving pipeline | `docs/architecture.md` |
| Include/serve and generator tunables | `docs/config-reference.md` |
| Shared enum / response metadata | `docs/cross-client-invariants.md` if changed |
| Product decision and evidence | This initiative; decision log entry as appropriate |
| HLD/LLD | No parallel update: newer Fleeced workflow makes these compatibility pointers |

## 5. Release gates

No express lane. Parent reviews all implementation and independent QA; full backend tests, all mobile structural checks/typecheck/test-ID lint and web checks must pass. Record exact commands/source and limitations. Any GitHub release requires green exact-head CI. Verify effective production source/config independently before saying the experiment is live; a code merge or successful build alone is not exposure. TestFlight is required only if client changes need a new binary, and submission is not tester availability.
