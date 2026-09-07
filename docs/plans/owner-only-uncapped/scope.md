# Owner-only discovery without returned-offer quotas

**Date:** 2026-09-06 (America/New_York)
**Entry point:** Operator: “Turn it on”, “And disable the other arms”, “No artificial limits to the number of offers either”.
**Baseline:** freshly fetched `origin/main` at `0e3d6b703c1351f51a7b38d3a561d340eda5e44b`; isolated worktree derived from Fleeced. The dirty organization checkout and historical checkout remain untouched.
**Builder:** Parent integration/release; separate Astra Ultra runner and route builders; independent Astra Ultra review.
**Waivers:** none. No express lane; no simulator/Maestro (D-056).
**Status:** implemented; parent full backend and client/web checks passed, independent review approved. Exact-head hosted CI/deployment/activation remain separate gates.

## Behavior and boundaries

The current operator request supersedes the earlier three-control-arm comparison for newly captured discovery requests. Add one default-off, captured owner-exclusive mode, effective only when owner generation and serving are enabled. In that mode organic and selected discovery run and serve only `owner_v1`; legacy generators must not execute as hidden controls or fallbacks. Selected assignment is deterministic owner exposure with probability 1 and distinct policy attribution, not a 50/50 experiment.

Return every distinct eligible package found: bypass deck/group/first-session quotas and random ghost withholding, and stop collapsing distinct companion packages sharing the same headliners. Exact duplicate suppression, market/ownership safety, prior user dispositions, explicit selections and the operator's small-package construction rules remain. Genuine inbound likes-you/standing-interest offers retain their separate source identity; they are not competing generated arms and must not be relabelled as owner recommendations.

Candidate-pool and evaluation budgets are computational search bounds, not output limits. They remain unchanged in this slice pending the operator's asynchronous clarification about widening the search. No claim of exhaustive enumeration or unlimited computational work is made. Zero must not be applied to owner search-budget knobs: existing clamping would reduce the search.

## 1. Analytics scope

Existing impression JSON, bakeoff diagnostics, `trade_card_viewed`, `deck_card_viewed`, `match_swiped` and `trade_proposed` cover exposure and outcomes. No new event names. Preserve immutable decision context and fail-closed impression publication. Record exclusive selected policy/version and probability 1 accurately; do not mix this window with historical randomized selected-control results. Real incoming-interest cards remain separately attributed. Generation count is not view count or acceptance evidence.

## 2. Schema and flag scope

- No new tables, columns, environment variables, shared client feature flags or dependencies.
- Add registered `model_config` knob `bakeoff_owner_only`, default 0. Effective mode requires include + serve. Capture mode with serving state once per request and include it in cache freshness.
- Rollback by setting `bakeoff_owner_only=0` restores the configured comparison path for newly captured requests; restoring the previous include/serve/deck settings is a separate logged operator action. Previously captured requests and stored cards are not revoked.
- Production activation must follow reviewed source deployment. Preserve a before snapshot and log each config mutation through `scripts/set_knob.py`; never raw SQL.

## 3. Evidence scope

- Backend tests: owner-only roster and dark mode; no legacy generator execution; selected/targeted routes and truthful attribution; captured hot-flip/cache behavior; more than 60 distinct eligible cards; same-headliner companions retained; rollback defaults; privacy and atomic impressions.
- Code walk: mobile/web mapping and rendering must not introduce downstream returned-card slicing. No client changes expected; add a focused guard if inspection finds one is required.
- Full frozen backend suite plus exact-head hosted CI (backend, mobile, test-ID lint, web) before merge. Independent review required.
- Manual TestFlight checklist: on existing 1.17.2 (150), start a fresh organic search, selected SEND, GET, partner search, More Offers and league buy/sell; verify matching selection labels, Back behavior, server order and no crash on a long deck. Confirm production snapshot identifies exclusive mode. Device checks remain unexecuted until actually run.
- No test IDs or visual changes planned. No new TestFlight build unless client code changes require one.

## 4. Canonical documentation

| Concern | Target |
|---|---|
| Model-config activation, limits and rollback | `docs/config-reference.md` |
| Serving/data flow | `docs/architecture.md` |
| Selected-route policy contract | `docs/api-reference.md` |
| Attribution JSON semantics | `docs/data-dictionary.md` |
| Shared client constants, UI, glossary | n/a: no new client enum, visual treatment or vocabulary |
| Product decision and implementation evidence | This initiative, linked from verification/ledger |
| HLD/LLD | n/a: compatibility pointers, not parallel update targets |

## 5. Ship gates

Parent diff review, independent acceptance review, full automated checks and green exact-head CI precede merge. Verify the exact Render commit and effective settings after deployment and activation. Submission of build 150 is not proof of installation or device acceptance. Record actual commands/results and any remaining runtime limits in `verification.md` and `living-memory/TEST_LEDGER.md`.
