# Feature Scope — #318 awaiting dismiss (mobile half) + #319 value disclosure + #307 carried Matches contract

**Date:** 2026-08-13
**Entry point:** feedback #318 + #319 (Matches group, 2026-08-13 wave) + carried #307 handoff (frozen, `wave-league` @ `6368e31` §4.3)
**Builder:** wave-matches build agent (branch `wave-matches`, base `origin/main` @ `60fccc7`)
**Operator sign-off on waivers:** carried from the committed plan (`plan-2026-08-13.md`) — the waivers below are the plan's written waivers; C-7 (no new flag) is the orchestrator-resolved operator directive.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — verdict per surface (plan § Analytics, DEFAULT-DENY):
  - **#319 expand (mutual):** fires the existing, client-registered `match_opened {match_id}` (taxonomy `backend/analytics_taxonomy.py:52`, props `:441`) — previously dark, so adoption distorts no live funnel. Ref-guarded: once per row per mount, first expand only.
  - **#319 calc CTA:** fires the app-wide `trade_edit_in_calculator_tapped` (screen `'Matches'`) — the TradesScreen #190 convention. Known gap, stated honestly: not in `ALLOWED_CLIENT_EVENTS`, so ingest accepts-and-drops it today, exactly as it does the existing TradesScreen emitter; registration is the flagged repo-wide defect (out of scope) and the emitter lights up the moment it lands.
  - **#318 dismiss:** the server fires `awaiting_trade_dismissed` on the POST (C-5) — the client fires **nothing** (the `match_*` family is SERVER_FIRED and namespace-disjoint; a client twin is forbidden by the taxonomy assertion).
- [x] **(c) WAIVED (partial, in writing):**
  - **Awaiting expand:** no event — `match_opened` allows only `match_id` and awaiting rows have none; registering a new event is a bright-line taxonomy change this mobile-only item doesn't rate.
  - **Awaiting undo:** nothing fired — the mutual path's `match_dismiss_undone` is unregistered/dropped today; we don't replicate a dead emitter.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (backend half lives on `wave-backend`).
- New/changed feature flags: **none — C-7 resolved: NO new flag** (orchestrator directive, 2026-08-13). Rationale, recorded per the directive: the D-035 precedent — a new flag here is a five-file change (`config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, `docs/config-reference.md`, client `useFlag`, fixture files) and `revalidateFlags`' map-replace semantics make a half-registered flag *worse than none* (an unknown key reads as permanently false and the affordance can never be turned on without a re-ship anyway). The affordance is small, additive, and rollback is a client revert; the undo toast still honours the **existing** `ux.swipe_undo`. Pinned by `check-awaiting-dismiss.js` #13 (no `awaiting_dismiss` flag key anywhere in `mobile/src`). Consequence vs the plan: the client renders the Dismiss affordance unconditionally; against a pre-#318 server the POST 404s and the S-9 rollback path restores the row with the honest toast — degraded honestly, nothing fake-succeeds.
- New env vars / `model_config` keys: **none**.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/matches-awaiting-dismiss.yaml` (tags `[matches, dismiss]`) — M-2 500-injection rollback assert (ordered first: `standard` seeds one awaiting row), M-1 happy dismiss + undo toast, M-3 empty state. **Depends on `wave-backend`'s route — authored + lint-clean, first run at the wave's pre-ship sim gate.**
- [x] **Extended flow:** `mobile/.maestro/capture/matches.yaml` — mutual expand → `Dynasty value swing` assert → `matches__value-expanded`; open-in-calc → `calc.find-a-trade`; awaiting expand assert + capture; launch-2 evaluate 500 injection → `Could not value this trade.` → `matches__value-error`.
- `testID`s added: `matches.value-details`, `matches.open-in-calc`, `matches.awaiting-dismiss`, `matches.league-chip.all` / `matches.league-chip.<league_id>` (frozen #307 grammar; template-literal → `scripts/testid-lint-allow.txt` entry). `testid-lint.sh` passes (output in the status file).
- **Capture delta:** `matches` (new value-expanded / awaiting-value-expanded / value-error variants) — rerun `screen-capture.sh --screen matches` at ship.
- Smoke-suite impact: `08-matches.yaml` crosses this surface — no id it references changed; collapsed-by-default disclosure keeps the populated screen's existing anchors valid. To re-verify at the sim gate.
- Backend pytest: none here — the dismiss route's tests belong to `wave-backend`.
- Structural suites (all sabotage-pinned, RED-then-green run this session — matrix in the status file): `check-match-value-section.js` (19), `check-matches-calc-handoff.js` (12), `check-awaiting-dismiss.js` (21), `check-matches-league-param.js` (9).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a here | #319 uses the already-documented `POST /api/trade/evaluate`; the #318 route's row is **wave-backend's** (they own the endpoint). |
| `living-memory/LLD.md` | n/a | no convention shift — reuses the delayed-POST undo, footer-slot, and disclosure grammars already established. |
| `docs/architecture.md` | n/a | no module wiring / data-flow change. |
| `living-memory/HLD.md` | n/a | no architecture shift. |
| `docs/cross-client-invariants.md` | n/a | bar semantics unchanged; no new enum/threshold; web parity is a separate item if the operator wants it. |
| `docs/glossary.md` | n/a | no new term ("Dynasty value swing" already defined). |
| `docs/plans/mobile-testing/lld.md` Appendix A (Matches row) | **proposed text in the status file** — shared doc, deliberately not edited on this branch to avoid cross-wave merge conflicts; orchestrator applies at merge. | adds `matches.value-details` `matches.open-in-calc` `matches.awaiting-dismiss` `matches.league-chip.<league_id\|all>`. |
| `mobile/src/components/CLAUDE.md` / `mobile/src/screens/CLAUDE.md` | **proposed text in the status file** — same shared-doc reasoning. | `MatchValueSection` row; `TradeCard` footer amendment; `MatchesScreen` amendment. |
| ADR / `DECISIONS.md` | n/a | C-7 rationale recorded here + status file; the wave-level ship session logs living-memory (per the wave protocol). |

## 5. Ship gate declaration

- **Simulator-gate tier:** the wave merges as one unit — tier per the runbook matrix for a user-visible mobile change (**tier 2: feature flow + affected smoke subset** — `matches-awaiting-dismiss.yaml`, `capture/matches.yaml`, smoke `08-matches`), run at the **wave's** pre-ship gate once `wave-backend`'s route is merged (the dismiss flow cannot go green against this branch's backend).
- Evidence: TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` to be written by the wave ship session after that run. This session's evidence is static-only (tsc, testid-lint, 4 suites, RED-then-green sabotage matrix) — recorded in `status-mobile-2026-08-13.md`.
- Operator deviation: none beyond the plan's carried waivers + the C-7 directive above.
