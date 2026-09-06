# Feature Scope — G420 Win Now recovery and deadlines

**Date:** 2026-09-06

**Entry point:** feedback #420 and #421

**Builder:** G420 implementation owner, not yet assigned in this author pass

**Operator sign-off on waivers:** not needed; no waivers requested

**Stage:** Phase-1 author revision after independent critique of `25347324`; focused planner recheck pending. No runtime evidence or release completion claimed.

Specification: [PRD](prd.md). Investigation: [plan](plan-g420.md), [production evidence](production-evidence.md). Decisions and limitations: [reconciliation log](reconciliation-log.md).

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it:** `api_request_failed` already records normalized `route`, `method`, `status`, trusted `ms`, `timeout`, and `bg` (`mobile/src/api/client.ts:349`; `backend/analytics_taxonomy.py:894`). It answers whether projection reads exhaust retries, retain typed session refusals, or hit the deadline. Existing sampled server inbound/outbound timing informs, but does not prove, the full latency path.
- [ ] **(c) WAIVED:** not applicable; existing coverage is explicitly retained.

Keep one failure event per logical request, not per physical retry; caller-abort exclusion; background-duration omission; and normalized paths with query/identifier stripping. Do not invent an HTTP failure event for a timeout solely in a local join. R-6/T12 pin the existing schema. No new event/property, success sampling change, raw body logging, identifier-bearing coordination metric, or private fixture. A genuinely new observability requirement returns to taxonomy/tracking-plan review before implementation; it is not implicitly approved here.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. No migration or data-dictionary change.
- New/changed feature flags: **none**. Existing season/Win Now/title flags and all policy/roster/valuation settings remain unchanged; no experimental-policy graduation claim.
- New env vars / `model_config` keys: **none**. Projection GET 30,000 ms and composed native attempt 90,000 ms are bounded client implementation constants, not new remote knobs. Ordinary route rules and search polling budget remain as specified in R-3/R-7.
- Rollback lever: no new flag. Withhold/withdraw an unverified native release and use the normal reviewed native corrective release process; installed binaries cannot be instantly reverted by a backend flag. Using an existing feature kill switch requires separate operator authorization and would disable that feature, not undo shared session/timeout behavior.
- Backend API/worker deployment: **none**. Keep synchronous available/unavailable response contract and current authorization guard. Any new server ordering/cancellation protocol or concurrency change is outside scope.

## 3. Evidence scope

- [ ] **Structural guard — required, not yet run:** new `mobile/tests/check-win-now-recovery.js`, registered as `npm run test:win-now-recovery`, pins actual lifecycle wiring, all init callers, safe GET-only recovery, finite attempts, and layer boundaries. It must execute production logic with deferred transports/fake time, not rely only on source strings. Preserve/extend `check-win-now.js` and `check-session-seed.js`; package-script registration belongs to the integrator to avoid a shared-file conflict.
- [ ] **Unit tests — required, not yet run:** native behavioral T1–T5/T7–T12 in the executable guard/helper harness; existing `backend/tests/test_win_now_api.py` and a narrow real installed persistent/verified-session guard regression in the existing session test suite selected by the evidence owner. The latter is required because a harness injected with an already-ready session cannot prove restoration. No backend runtime change or live provider access is implied.
- [ ] **Code-walk proof — required after implementation:** final file:line trace for every init writer, generation-before-intent transition, init dispatch/settlement, seeds/verification/navigation commits, exact 409 repair/replay, same-token successful A→B ordering, uncertainty latched across automatic re-entry until new explicit retry/selection or replacement-token authorization, caller detach, stale 401, the earlier shared API stale-403 verification callback, and all deadline-bound awaits. Baseline diagnosis and required trace appear in [PRD §§3–5](prd.md); the baseline is not a GREEN proof.
- [ ] **Manual TestFlight checklist — required and not executed:** [PRD §5](prd.md) has seven numbered steps, including both entry points, process rollover, same-token switch, ambiguous POST, ~16-second response, complete attempt deadline, structured refusal, accessibility, and existing feature preservation. This is the required runtime net; never infer device availability or success from a build upload.
- [ ] **WAIVED:** no evidence waiver requested. D-056 retires simulator/Maestro/capture work; it is not permission to omit executable guards or the manual checklist.
- `testID`s added/renamed: none required. Preserve `win-now.refresh`, `win-now.source`, `win-now.unavailable`, `win-now.stale`, `win-now.disabled` and both entry IDs. An additive `win-now.load-error` is allowed only if needed for the existing error surface's focused guard; no new UI structure. Run `mobile/scripts/testid-lint.sh` regardless.

Every new behavioral test must have a saved failing baseline or named meaningful-sabotage run and a passing fixed run. Record commands, test names/counts, failure reasons and exact SHAs in the parent-owned ledger. All T1–T12 map to R-1–R-7 in the PRD. No screenshot, simulator, flow authoring, or production-user mutation is part of the evidence plan.

Independent-critique additions are mandatory evidence, not advisory tests: T10 must show ambiguous A → queued B rejected → automatic refocus/foreground causes zero init/read → new explicit retry is bounded, with no readiness hint in between. T8 must exercise the actual shared client's verification callback before caller rejection, proving a stale 403 cannot mutate replacement-session verification while a valid current-session denial still can. Neither addition broadens the wire/API or runtime file ownership.

## 4. Docs scope — HLD / LLD / API

Rows below declare the required follow-through; “required” is intentionally not “updated.” Only this scope, PRD and reconciliation are this author task's file ownership. The integrator assigns shared documentation edits during implementation and marks them complete at the exact reviewed code SHA.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a: no HTTP route or wire contract change | Existing init and projection request/response/error shapes are pinned in PRD §4.4. Native-only timing/lifecycle changes belong in the mobile API/state references, not a fictitious server API delta. |
| `living-memory/LLD.md` | Required at integration | Targeted native session-generation, shared init ordering, uncertain completion, and 30-second projection / 90-second total attempt invariants; no schema section change. |
| `docs/architecture.md` | Required at integration | Targeted native data-flow note: state-owned join/repair, every init writer participating, API layering unchanged. Embedded HLD/LLD in PRD §§3–4 are the Phase-1 contract. |
| `living-memory/HLD.md` | Required at integration | Concise update to existing native session reconciliation flow, not a new backend service or async baseline architecture. |
| `docs/cross-client-invariants.md` | n/a: no shared constants/enums/colors or wire behavior changed | Preserve current verified identity, account/co-owner distinction, source/freshness rules, error bodies and result order; native deadline is not imposed on web. |
| `docs/glossary.md` | n/a: no new domain term | Context generation / request budget are internal implementation terms. |
| ADR or `DECISIONS.md` | n/a: bounded correction, not a new architectural platform decision | Non-obvious local choice (serialization is conditional on acknowledged settlement; no server cancellation guarantee) is explicit in PRD §4.2 and reconciliation. A stronger server protocol would require a separately reviewed design. |
| `mobile/src/api/README.md`, `mobile/src/state/README.md` | Required at integration where their current maps describe these paths | Correct changed lifecycle/timeout and stale “mint/optimistic” descriptions in touched code; API returns seed, state owns cache remains intact. No general auth documentation rewrite. |
| `living-memory/TEST_LEDGER.md` and selected item status/index | Required, orchestrator-owned | Exact RED/GREEN/CI evidence and actual implementation/delivery/device status; do not close the reports or label runtime verification complete from this author pass. |

No HLD/LLD/API requirement is silently waived. No separate feature-path delta files are added because this is the requested lighter-path native bug fix with full interfaces embedded in the PRD.

## 5. Ship gate declaration

- **Independent spec review:** planner critiques completed author documents sequentially; blocking objections resolved and reconciliation updated before Phase 2. Current author completion is not this gate's completion.
- **Fresh-main reconciliation:** orchestrator re-diffs before runtime edits and before final integration, preserving newer security/session/Win Now changes and the disjoint #419 boundary.
- **CI green:** `backend-tests`, `mobile-typecheck` (including the `check-*.js` suites), and `maestro-testid-lint`, plus every required PR check, pass on the pushed reviewed SHA. The historical CI job name does not authorize Maestro execution.
- **Evidence recorded:** orchestrator-owned `living-memory/TEST_LEDGER.md` entry records executable RED/GREEN proof, targeted and integrated tests, final code-walk, limitations, and exact source/artifact identifiers. A 30-second response allowance is not a throughput benchmark result.
- **TestFlight verification:** operator runs the PRD checklist with the actual new binary and records outcome. Build submission, Apple processing/tester availability and observed behavior are separate facts; none is complete now.
- **Privacy/release safety:** only sanitized paraphrases/fixtures and intended source/docs may enter the commit/archive. No raw DB snapshots, tokens, account/league IDs, private rankings, env files, or screenshots of private accounts. No network, production changes or publication performed by this author.
- Express lane declared by the operator? **No.** No gates skipped; no waivers requested.
