# Feature Scope — G419 rejected interest resurfacing

**Date:** 2026-09-06
**Entry point:** approved feedback #419
**Builder:** separate backend/mobile owners assigned by root after Phase-1 critique
**Operator sign-off on waivers:** not needed (no evidence or analytics waivers)

Source: [PRD](prd.md), requirements R1–R4 and acceptance T1–T8; [planner diagnosis](plan-g419.md). Independent planner approved revised specification `481b1809`; root ratified the contract and held boundaries. Backend `e02d074e`, mobile `396d92fc` and current-episode repair `8f27421d` passed root review and both full independent round-2 reviews on `7d3e071f`. All four PR #283 CI jobs passed on runtime-equivalent `d97459dc`, including 5,645 backend tests / one skip; merge `988fa2d6` is live on Render. iOS 1.17.1 (149) build/submission are FINISHED and feedback #419 is verified `fixed`. Apple processing/tester availability and physical-device checks remain unverified/UNRUN. [Release evidence](release.md). Root owns shared-document edits.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `match_swiped` records the server pass; `trade_pass_layer1` / `trade_pass_layer2` separate the first pass from progressive refinement; `trade_proposed` and `calc_trade_queued` cover new/repeated positive actions. Existing `trades_generated`, `deck_card_viewed` and `swipe_undone`, together with existing `deck_impressions`/`deck_outcomes` and decision timestamps, cover serve/action/Undo chronology where linkage exists. Existing Awaiting-dismiss event covers caller withdrawal. Keep event names, props, ownership checks, flags and counts unchanged; no events are emitted by read filtering.
- No new event or analytics field is justified. Historical rows without impression/concept links remain unlinked; do not infer which source job the reported card came from. Do not log raw reason text, private boards, or new per-card history dumps. Query-count tests and synthetic fixture evidence verify the projection itself.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. Read existing action history and verify durable exact-pass evidence for idempotent reason repair; no migration, synthetic action, retraction backfill or unique constraint. The queue's existing ten-second guard gains only the server-verified intervening exact-pass exception for an explicit renewal, not a general bypass.
- New/changed feature flags: **none**. Preserve existing source/queue/reason flags, D-170 behavior and all arm assignments.
- New env vars / `model_config` keys: **none**. Preserve `pass_cooldown_days` (14 default), `pass_cooldown_start_epoch`, independent like window, fatigue and quality knobs. Existing cooldown knob is not a rollback for stale-evidence resolution; the bounded code commits are reverted through normal release process if necessary. No flag or deploy-free rollback lever is invented.

## 3. Evidence scope

**Executed evidence:** [backend tests and named RED controls](build-evidence.md), [backend code walk](backend-code-walk.md), [28 mobile behavioral cases and baseline controls](mobile-build-evidence.md), [mobile code walk](mobile-code-walk.md). Root reran the original round-1 defect reproduction GREEN and 424 focused backend cases on the repair, then all 95 integrated mobile guards, TypeScript/testID and the full backend suite. The requirements below describe implemented coverage; not every proposed sabotage was executed, and no blanket per-test RED or physical-device pass is claimed. Actual commands and distinctions are retained in the linked evidence and QA reports.

- [x] **Structural guard planned:** `mobile/tests/check-trade-disposition.js` plus matching `npm run test:trade-disposition`; pins extracted state behavior for locally observed passes, structured reason response consumption (`passed === true`), context/edited identity serialization and narrow screen wiring. Backend AST guards pin public snapshot/publication routes, shared pass binding/repair and restoration callers. Existing decline, browse and Undo checks remain required. Remote-only invalidation of a retained append-only deck without a local pass record is explicitly held.
- [x] **Unit tests planned:** new `test_trade_interest_disposition.py`, `test_trade_disposition_replay.py`; extend existing trade-match, decline-reason, pass-cooldown, queue, Awaiting, summary and replenishment tests as required by PRD T1–T8. Required focused additions: actual queue→own/receiver mirrored pass→requeue inside ten seconds with retry/Elo/event counts; contextless reason bank→valid-context repair with no companion swipe; failed disposition persistence→repair; truthful passed state on repeats beyond ten seconds; edited identity; mixed timestamp normalization/order through DB consumers. All DB data in isolated memory/scratch, clock fixed and egress stubbed. No global fixture broadening.
- [x] **Code-walk proof planned:** verified baseline seams and findings in [reconciliation log](reconciliation-log.md); build evidence must replace baseline-only claims with final file:line traces for source read → injection/match/Awaiting, pass write → live sets → worker/cache serve, and mobile pending/success/failure → lane/snapshot state.
- [x] **Manual TestFlight checklist:** [PRD](prd.md#manual-testflight-checklist--operator-run-not-run), five concrete sequences. Not run by the author; operator records physical-device results after build availability.
- `testID`s added/renamed: **none planned**. Existing test-ID lint still runs. No Maestro or simulator work under D-056.
- Record baseline incident RED and named sabotage RED→GREEN before claiming regression coverage; a written test plan is not passing evidence.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Planned disposition | Section / owner |
|---|---|---|
| `docs/api-reference.md` | Updated | Root: Trades route rows for actionable likes, queue renewal within ten seconds, Awaiting, consistent pass/cache semantics, and `passed` as verified durable disposition state (including existing committed retries), not reason-row creation. Contextless/best-effort failed writes return passed false and remain repairable. Field names/types/status codes unchanged; the boolean meaning correction is explicit. |
| `living-memory/LLD.md` | Updated | Root: exact source-evidence projection separate from discovery cooldown; narrow queue replay exception, idempotent banked-reason repair, structured client commit evidence, shared pass binding/restoration and job-owned serve projection. |
| `docs/architecture.md` | Updated | Root: existing trade-card lifecycle/read flow gains shared history projection and serve revalidation. No new subsystem. |
| `living-memory/HLD.md` | n/a | No new module/subsystem/client/major flow; detailed changes belong to architecture and LLD. Reassess only if implementation expands. |
| `docs/cross-client-invariants.md` | Updated | Root: existing Match bucket semantics clarify only actionable one-sided likes appear in Awaiting; visible summary counts retain parity. Existing pass controls, enums and constants stay unchanged. |
| `docs/glossary.md` | n/a | No new user-facing term; interested, like, pass, Awaiting and match retain their UI vocabulary. |
| ADR or `DECISIONS.md` | Updated | D-186 records exact stale-source precedence and its separation from D-067 discovery amnesty/expiry, plus truthful passed/repair semantics. QA's current-episode repair remains an implementation gate, not a broad cooldown policy reversal. |
| `docs/data-dictionary.md` | n/a | No schema or stored-field meaning change; existing retraction ownership and timestamps remain history. |
| `docs/config-reference.md` | n/a | No new/changed setting, default, flag, or experiment surface. |
| Item documents / central index / test ledger | Updated | Root records integrated checks, confirmed round-1 finding/repair, both passing round-2 reviews, exact-head CI, live deployment, completed native submission and selected feedback readback. Consolidated 23-step physical TestFlight checklist remains UNRUN. |

## 5. Ship gate declaration

- **CI gate passed:** all four PR #283 jobs on `d97459dc`, including `backend-tests`, `mobile-typecheck` and `maestro-testid-lint`. Structural scripts also ran explicitly; the legacy job name does not authorize Maestro. Merge/live source is `988fa2d6`.
- **Evidence recorded:** root's `living-memory/TEST_LEDGER.md` entry names actual focused/full checks, original incident RED/GREEN, meaningful baseline controls, attributed builder evidence and final code walks. Proposed-but-unrun sabotages are not passing evidence; no simulator or physical-device execution is claimed.
- **TestFlight verification:** operator runs PRD checklist and logs the exact build/backend result before mobile runtime behavior is described as verified.
- Express lane declared? **No.** Full evidence/doc gates apply. `FTF_SKIP_SIM_GATE=1` is the D-056 standing posture if a later authorized push runs the old hook.
- Current-batch owner authorization covers reviewed merge/live/TestFlight delivery, as recorded in the batch plan. It does not waive QA/CI/privacy gates or authorize unrelated changes and real-user trade actions. Build completion is not delivery or physical-device verification.
