# Owner interview contracts — implementation scope

**Date:** 2026-09-05
**Entry point:** Owner interview and explicit request to use subagents to implement, with parent review and validation before push.
**Builder:** Parent integration review plus independent Astra Ultra mobile and policy builders.
**Operator sign-off on waivers:** Not needed; no waivers. D-056 prohibits simulator/Maestro evidence.
**Baseline:** `origin/main` at `5cf34182`; separate worktrees protect the owner's unrelated working changes.
**Status:** Bounded implementation parent-reviewed and committed locally as `86128700`; final local gates passed. Publication requires explicit approval for the public repository; no push/PR occurred and hosted CI is unrun. No deployment or experiment activation authorized by this scope.

## Behavior and boundaries

Implement the confirmed, independently testable owner interview contracts: preserve mobile search intent through navigation and retries; use personal tiers for requested trade direction with per-entry consensus fallback in that classification; give explicit ranking methods equal authority in the dark policy; constrain interaction-driven ranking movement to the current tier. Preserve market companion pricing, recent telemetry/security/Win Now releases, all three generator arms, and existing dark flags. Candidate-universe fallback and live generator method-weight changes are deferred after review identified control-arm regressions; no golden recapture or unapproved thresholds. Raw interview/source documents remain local and are not published to this public repository.

This is a bounded first implementation, not completion of every interview idea. Do not invent market-loss caps, deck quotas, untouchable premium formulas, partial-selection coverage rules, partner-expansion defaults, or interest-window start/renewal semantics. Do not remove persistent player tags. Legacy stud-tax Off handling awaits the owner's compatibility decision before changing saved preference semantics. Outstanding work is tracked in `review.md` at handoff.

## 1. Analytics scope

- [x] Existing events cover the interactions: `find_trades_tapped` records requests; `trade_card_viewed`/`deck_card_viewed` record exposure; `calc_trade_queued` records calculator queue actions; `swipe_undone` records reversals. Existing server trade-decision and immutable valuation snapshot paths remain authoritative for offers and outcomes. No new user action or event name is introduced by the ranking bound or per-entry provenance read. Mobile scope names any additional existing events at its touched call sites.
- Outcome comparisons must use impression-linked decisions and distinct manager exposure/action times; this change does not substitute today's rankings for historical snapshots or claim observational differences establish a winning generator.

## 2. Schema & flag scope

- New/changed tables or columns: none planned. Read existing per-row `member_rankings.confidence_source` into a per-player internal map; do not expose private partner tier values. Any additive internal read contract is documented in the data dictionary and LLD.
- New/changed feature flags: none. Preserve `trade.personal_market_policy_v1`, valuation telemetry and roster-enforcement defaults, generator allocation, and existing numerical thresholds.
- New env vars / model configuration: none. Code rollback is a revert of this scoped change; no irreversible data rewrite is planned. No production database read/write is required to implement or validate these contracts.

## 3. Evidence scope

- [x] Mobile structural and executable pure-helper guards (all 93; see `mobile-scope.md`), TypeScript and test-ID lint passed.
- [x] Backend regression tests for repeated trade/disposition signals across all scoring-format/position tier boundaries, retained-row persistence replay, explicit ranking actions, cache invalidation, and per-row provenance plumbing; policy builder tests personal trade intent and classification fallback. Full final suite: **5,455 passed / 1 skipped**. Retained-row replay is a prerequisite, **not implementation proof of committed-action Undo**; Browse Undo currently retains server feedback and is a P1 follow-up.
- [x] Parent code-walk and review in `review.md`; lane-specific code walks identify exact call paths.
- [x] Manual TestFlight navigation checklist written in `mobile-testflight.md`. **Runtime execution is UNRUN** and remains an owner action; checklist creation is not a device pass.
- `testID`s: retain existing IDs unless mobile scope explicitly records an addition. Test-ID lint remains mandatory; no simulator execution or captures.

## 4. Docs scope

| Doc | Disposition |
|---|---|
| `docs/api-reference.md` | Update only if an external request/preference contract changes; search fixes otherwise forward existing fields. |
| `docs/data-dictionary.md` | Document internal per-entry provenance use, no new database columns. |
| `living-memory/LLD.md` | Record within-tier interaction bound and per-entry authority; distinguish ranking actions from trade feedback. |
| `docs/architecture.md` | No new service/client; update relevant ranking/trade-flow contract if needed after integration. |
| `living-memory/HLD.md` | No architectural topology change; no new module/client or major flow. |
| `docs/cross-client-invariants.md` | Record shared tier-feedback and ranking authority semantics, and stud-tax normalization only if approved. |
| `docs/glossary.md` | No new domain term; use existing personal tiers, market, fairness, and trade intent. |
| `living-memory/DECISIONS.md` | Explicitly reconcile D-180's older method-confidence/primary-ordering policy with the owner's later direction; leave unresolved ordering/caps dark. |

## 5. Ship gate declaration

- No subagent pushes, merges, deployment, or worktree deletion. Parent reviews each diff before integration.
- Python 3.12 complete backend suite, mobile TypeScript plus **every** `check-*.js` guard, web structural guard, and test-ID lint must pass locally before a reviewed branch push. CI must then pass on the pushed SHA before considering merge.
- Record exact commands, outcomes, environment, and pending physical-device evidence in `living-memory/TEST_LEDGER.md` and the parent review.
- No express-lane exemption. No automatic Render/EAS release or main merge is promised by this coding request.
