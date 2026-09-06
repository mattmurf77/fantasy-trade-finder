# Feature Scope — G419 rejected interest resurfacing

**Date:** 2026-09-06
**Entry point:** approved feedback #419
**Builder:** separate backend/mobile owners assigned by root after Phase-1 critique
**Operator sign-off on waivers:** not needed (no evidence or analytics waivers)

Source: [PRD](prd.md), requirements R1–R4 and acceptance T1–T8; [planner diagnosis](plan-g419.md). This scope is planned, not evidence of a completed implementation. Root owns shared-document edits.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `match_swiped` records the server pass; `trade_pass_layer1` / `trade_pass_layer2` separate the first pass from progressive refinement; `trade_proposed` and `calc_trade_queued` cover new/repeated positive actions. Existing `trades_generated`, `deck_card_viewed` and `swipe_undone`, together with existing `deck_impressions`/`deck_outcomes` and decision timestamps, cover serve/action/Undo chronology where linkage exists. Existing Awaiting-dismiss event covers caller withdrawal. Keep event names, props, ownership checks, flags and counts unchanged; no events are emitted by read filtering.
- No new event or analytics field is justified. Historical rows without impression/concept links remain unlinked; do not infer which source job the reported card came from. Do not log raw reason text, private boards, or new per-card history dumps. Query-count tests and synthetic fixture evidence verify the projection itself.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. Read existing action history; no migration, synthetic action, retraction backfill or unique constraint.
- New/changed feature flags: **none**. Preserve existing source/queue/reason flags, D-170 behavior and all arm assignments.
- New env vars / `model_config` keys: **none**. Preserve `pass_cooldown_days` (14 default), `pass_cooldown_start_epoch`, independent like window, fatigue and quality knobs. Existing cooldown knob is not a rollback for stale-evidence resolution; the bounded code commits are reverted through normal release process if necessary. No flag or deploy-free rollback lever is invented.

## 3. Evidence scope

- [x] **Structural guard planned:** `mobile/tests/check-trade-disposition.js` plus matching `npm run test:trade-disposition`; pins actual extracted state behavior and narrow screen wiring. Backend AST guards pin all public snapshot/publication routes, shared pass binding and restoration callers. Existing decline, browse and Undo checks remain required.
- [x] **Unit tests planned:** new `test_trade_interest_disposition.py`, `test_trade_disposition_replay.py`; extend existing trade-match, decline-reason, pass-cooldown, queue, Awaiting, summary and replenishment tests as required by PRD T1–T8. All DB data in isolated memory/scratch, clock fixed and egress stubbed. No global fixture broadening.
- [x] **Code-walk proof planned:** verified baseline seams and findings in [reconciliation log](reconciliation-log.md); build evidence must replace baseline-only claims with final file:line traces for source read → injection/match/Awaiting, pass write → live sets → worker/cache serve, and mobile pending/success/failure → lane/snapshot state.
- [x] **Manual TestFlight checklist:** [PRD](prd.md#manual-testflight-checklist--operator-run-not-run), five concrete sequences. Not run by the author; operator records physical-device results after build availability.
- `testID`s added/renamed: **none planned**. Existing test-ID lint still runs. No Maestro or simulator work under D-056.
- Record baseline incident RED and named sabotage RED→GREEN before claiming regression coverage; a written test plan is not passing evidence.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Planned disposition | Section / owner |
|---|---|---|
| `docs/api-reference.md` | Update at integration | Root: Trades route rows for actionable likes, queue `already_queued` after a resolved offer, Awaiting, consistent pass/cache semantics. Shapes/codes unchanged. |
| `living-memory/LLD.md` | Update at integration | Root: exact source-evidence projection separate from discovery cooldown; shared pass binding/restoration and job-owned serve projection. |
| `docs/architecture.md` | Update at integration | Root: existing trade-card lifecycle/read flow gains shared history projection and serve revalidation. No new subsystem. |
| `living-memory/HLD.md` | n/a | No new module/subsystem/client/major flow; detailed changes belong to architecture and LLD. Reassess only if implementation expands. |
| `docs/cross-client-invariants.md` | Update at integration | Root: existing Match bucket semantics clarify only actionable one-sided likes appear in Awaiting; visible summary counts retain parity. Existing pass controls, enums and constants stay unchanged. |
| `docs/glossary.md` | n/a | No new user-facing term; interested, like, pass, Awaiting and match retain their UI vocabulary. |
| ADR or `DECISIONS.md` | Decision entry at integration | Root records reviewed exact stale-source precedence and its separation from D-067 discovery amnesty/expiry. This is a semantic interpretation with explicit fresh-like cases, not a broad cooldown policy reversal. |
| `docs/data-dictionary.md` | n/a | No schema or stored-field meaning change; existing retraction ownership and timestamps remain history. |
| `docs/config-reference.md` | n/a | No new/changed setting, default, flag, or experiment surface. |
| Item documents / central index / test ledger | Item docs authored; shared updates pending root | Author's three files are complete for critique. Root records reviewed status, actual tests, manual results and release state; no claim this is built or shipped. |

## 5. Ship gate declaration

- **CI green required before eventual ship:** `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` on the actual pushed SHA. Structural scripts also run explicitly; the legacy job name does not authorize Maestro.
- **Evidence recorded:** root's `living-memory/TEST_LEDGER.md` entry names focused/full checks, incident RED, named sabotages and final code-walk. No execution claimed in this Phase-1 artifact.
- **TestFlight verification:** operator runs PRD checklist and logs the exact build/backend result before mobile runtime behavior is described as verified.
- Express lane declared? **No.** Full evidence/doc gates apply. `FTF_SKIP_SIM_GATE=1` is the D-056 standing posture if a later authorized push runs the old hook.
- Current authorization covers the fix and local commits. This author task stops after the documents and independent critique handoff; no push/deploy or production/user action.
