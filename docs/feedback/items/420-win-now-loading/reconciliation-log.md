# G420 reconciliation log — #420 / #421

Date: 2026-09-06

Planner: `ux_astra`, completed [plan-g420.md](plan-g420.md) at `7fd1ba9a49904287a80e14cad545c9bce5160eeb`

Author: `release_review`, separate documentation-only pass

Runtime source reviewed: `4026ebc81eaae50b345b42421641125c5b8d413e`

Artifacts: [PRD](prd.md), [scope](scope.md), [sanitized production evidence](production-evidence.md).

## Round 0 — author reconciliation before independent critique

This is the author incorporating the completed planner investigation and the orchestrator's scope clarifications. It is **not** a planner review of the authored PRD and does not count as independent approval. No runtime implementation, RED/GREEN app testing, build, deployment, production action or feedback closure occurred in this pass.

| Issue / objection | Classification | Resolution in author draft |
|---|---|---|
| Error-text-only treatment would leave the production `409 session_not_initialized` loop intact. | Blocking if omitted | R-1 and §4.3 require an awaited current-context join plus one forced repair and one projection GET replay, bypassing the normal foreground throttle. A previously ready local context is explicitly not server proof. |
| Planner leaves the shared seam and complete init-writer census for the author. A Win Now/store-only mutex would miss other writers. | Blocking if omitted | Verified revalidate/switch/connect, picker two-phase submission, ESPN resync and both auth cache-missing retry paths. PRD §3 assigns one state-owned protocol and shared submission fence, including guarded seed/verification/navigation completion. API gains no new upward store/cache dependency. |
| Token-only safety does not distinguish same-token A→B league intent, and the picker currently writes its seed before init succeeds. | Blocking if omitted | R-2 / §4.1 require account+token+real league+generation, intent invalidation before async work, and guarded publication. Picker retains init-before-Main; its seed moves to guarded success or must prove equivalent rejection/supersession safety. T4/T11 name meaningful token-only and pre-guard seed sabotages. |
| The planner's “B is the final applicable server context” wording would overpromise after an accepted init times out locally. | Blocking ambiguity, orchestrator clarified | Narrowed to normal **successful acknowledged** A→B serialization. §4.2 requires uncertain dispatched-init failures to stop automatic dependent work and suppress stale publication. No assertion that client abort stopped server work or that a prior accepted request can never finish later. Residual server-order uncertainty is explicit. |
| Need finite whole-attempt duration, not 30 seconds per step or an unbounded joined promise. | Blocking if omitted; orchestrator accepted 90 seconds conditionally | R-3 / §4.3 choose fixed 90,000 ms from the user attempt, encompassing every wait/preparation/init/read/replay and body read; projection logical request is at most 30,000 ms and remaining attempt time. Shared init also has a finite non-resetting lifecycle budget. T10 must show bounded/detachable waits and no late dispatch/publication. Scheduling while JS is suspended is not falsely guaranteed. |
| “One replay” could hide layered retry multiplication or unsafe write retries. | Blocking if omitted | §4.3 states at most two logical projection reads / ten physical GET attempts under existing finite retry budgets, one forced init, possible normal pre-read init/join, and existing one cache-missing init retry only. Every layer consumes its fixed deadline. No automatic recovery around search/evaluate/decision writes. |
| HTTP 200 evidence does not establish forecast availability; timeout does not establish sleep; sampled outbound spans do not prove queue attribution. | Blocking accuracy concern | Evidence and PRD preserve those qualifications. Exact neutral timeout is selected. Existing 200 unavailable / typed-refusal body remains authoritative; no async status, fake forecast or relaxed guard. |
| Wider latency/worker contention is plausible but not diagnosed to a specific operation. | Scope clarification, accepted limitation | The bounded core fix does not claim to remove synchronous contention, meet an SLO, or change worker configuration. Optional hermetic spike is not a required new build task. Manual step 6 records the limitation rather than inventing a passed performance claim. |
| Existing tests inject ready sessions and native lifecycle assertions are partly structural. | Blocking evidence gap | T6 requires the real installed restored-session guard; new executable native orchestration tests use deferred transports/fake time. Every new behavioral case needs original-defect or named-sabotage RED followed by GREEN; AST text checks cannot substitute. |
| Analytics, shared docs and physical iOS verification could be silently waived on a small fix. | Blocking scope gap | Scope selects existing `api_request_failed`, lists all properties/privacy rules, assigns targeted HLD/LLD/module-doc follow-through, and keeps manual TestFlight evidence separate from upload/availability. No waiver, express lane, new event or premature completion claim. |
| Phase-reference capture paragraph conflicts with the later D-056 rule. | Instruction reconciliation | Follow root/mobile instructions, feedback lessons and current feature-scope template: no simulator, Maestro, screen capture or mockup round. Existing UI reused; executable guard, code-walk and manual TestFlight checklist remain mandatory. |

### Orchestrator clarification recorded

The orchestrator explicitly instructed the author to keep the fix bounded and distinguish local transport termination from server mutation cancellation. A local timeout is not proof that the server stopped. Normal deferred successful A→B serialization must be tested; ambiguous init must have safe client publication/read gating and a documented residual limit. A 90-second total user-attempt cap is acceptable only when every wait, init, read and replay is bounded within it and caller abort detaches cleanly. No new server API or broad auth redesign is authorized.

The author has incorporated that direction, not inferred a product choice to remove server-side safety guards. The PRD intentionally stops a current automatic chain after ambiguous init; a later deliberate attempt does not retroactively certify server cancellation or final ordering. The reviewer should scrutinize whether this bounded safety contract is sufficiently precise for implementation.

## Independent critique — pending

The author pass is complete once the three documentation files are committed and delivered to the orchestrator. The original planner must then review that exact author SHA. No parallel “review” of half-written documents is counted.

Requested focus, not unresolved product decisions:

1. Does §4.2's uncertain-write behavior avoid both an unsafe automatic continuation and a falsely permanent success hint? Does the later explicit retry wording avoid claiming server cancellation?
2. Does §4.3's 90-second composition actually constrain token/provider/verification preparation, lane wait, body consumption, init cache retry and both logical GETs, while one consumer abort cannot kill another's valid shared init?
3. Can every existing native init writer participate through the proposed state/API seam without adding an upward dependency or changing identity/verification/membership behavior? Are all affected late publications fenced?
4. Do T1–T12 execute the production behavior and prove RED/GREEN sensitivity rather than merely repeat the specification in a mock?

No independent blocking objections have yet been raised because critique has not happened. **Do not interpret that as zero unresolved blockers or a Phase-1 exit.** The orchestrator records each critique round below; accepted/rebutted objections require concrete paths and reasoning, with any remaining arbitration explicit. Build begins only after that gate.

## Author verification performed

- Read applicable root/backend/mobile/API/state/docs instructions; feedback skill, full lessons and plan-phase reference; coding guidelines and feature-scope template; completed planner investigation and production evidence.
- Checked current source for actual route registration/request/error shapes, initialized-session guard, verified-token init, init-writer census, picker ordering/seed, ESPN resync completion, shared timeout/retry/parser/telemetry semantics, and user+league keyed Win Now baseline behavior.
- Authored only `prd.md`, `scope.md` and this log; no shared ledger/index/status/lesson edit, runtime code or private evidence copied. Shared docs/lesson follow-through remains the orchestrator's responsibility.
- Documentation validation: 14 local Markdown links resolve; all seven requirement rows and twelve test rows are present. The author handoff also requires staged `git diff --check` and exact three-file commit scope. No app test execution or release status is claimed from these checks.

Potential lesson for the orchestrator to evaluate after critique (not appended to the shared lessons file by this bounded author): inventory every writer at the actual session-init choke point before promising switch safety, and distinguish acknowledged client ordering from ambiguous server completion after transport timeout.
