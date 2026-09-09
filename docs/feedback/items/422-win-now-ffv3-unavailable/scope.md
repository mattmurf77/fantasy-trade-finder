# Feature Scope — FB-422 Win Now on FFV3: early, specific K/IDP refusal

**Date:** 2026-09-08
**Entry point:** feedback #422 (batch 2026-09-08, group G-422, fast-track bug path)
**Builder:** G-422 build agent (planner: investigating planner, this folder)
**Operator sign-off on waivers:** required for §1(c) — surfaced in `prd.md` §7 / planner report

Specification: [prd.md](prd.md). Root cause and evidence: [investigation.md](investigation.md).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** no — the route answers HTTP 200 for a structured refusal, so `api_request_failed` never fires, and no server event is emitted for `status:"unavailable"`.
- [x] **(c) WAIVED — no analytics needed because:** this change only alters the text of an existing refusal and the order in which an existing refusal is detected. The refusal already reaches operators through the sampled server request log (route + status + body size — exactly how #422 was diagnosed) and through the response body itself. An `unavailable`-reason event would be a new taxonomy question (an-data-architect), not part of a fast-track copy/ordering fix; recommend raising it with the §7 policy item if the operator wants refusal rates measured.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. `outlook.season_projections` / `trades.win_now` remain the kill switches; rollback lever = revert the one-file backend change (deploy-only, no binary).
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [ ] **Structural guard:** none added — no mobile/web code changes. Existing `mobile/tests/check-win-now.js` and `check-win-now-recovery.js` must still pass (they pin the unchanged `win-now.unavailable` surface).
- [x] **Unit tests:** `backend/tests/test_win_now_service.py` — new `ffv3_source_fixture()` (real FFV3 roster_positions / settings / 55-key scoring) and `test_ffv3_active_kicker_idp_slots_refused_before_any_projection_fetch`, `test_ffv3_load_bundle_refusal_is_the_slot_reason_not_a_forecast_reason`, `test_unsupported_slots_message_names_distinct_slots_in_roster_order`, `test_offense_only_lakeview_slots_pass_the_slot_gate`; `backend/tests/test_win_now_api.py` — `test_projection_route_returns_slot_refusal_message_verbatim`. The two FFV3 defect tests and the helper test must be run RED on `b8d37085` and the failure output saved before the fix is applied (`prd.md` §5 states why each is red).
- [x] **Code-walk proof:** rendering path unchanged and cited — `mobile/src/screens/WinNowScreen.tsx:99-101` (200 body becomes `baseline`), `:125` (`available` false for `status:"unavailable"`), `:195` (`baseline.message` rendered under `win-now.unavailable`); `web/js/win-now.js:231`. Server path: `win_now_api.py:76-93` → `win_now_service.load_bundle:212` → `load_league:90` (new gate) → `_forecast_batch:183` (now unreachable for K/IDP leagues). Local reproduction of both production bodies (98 B FFV3, 114 B Lakeview) is recorded in `investigation.md` §2.
- [x] **Manual TestFlight checklist:** `prd.md` §8 — four steps, FFV3 expected sentence + timing, Render-log absence of the projection burst, Lakeview must not show the slot sentence. Runtime proof matters here because the text is what the user reported on; the checklist is the only runtime evidence (D-056).
- [ ] **WAIVED because:** no evidence waiver.
- `testID`s added/renamed: **none** (`win-now.unavailable`, `win-now.disabled`, `win-now.refresh`, `win-now.source` preserved; `mobile/scripts/testid-lint.sh` still runs in CI).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (one sentence)** | § "Season projections and Win Now" (~`:1005`): active K/DEF/IDP slots or >12 active slots answer `unsupported_roster_slots` before any projection fetch, `message` names the slots. Contract shape unchanged. |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifts; reason vocabulary unchanged |
| `docs/architecture.md` | n/a | module wiring unchanged — same call chain, one check moved earlier inside `load_league` |
| `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/colour; clients keep rendering `message` |
| `docs/glossary.md` | n/a | no new term (IDP already used across docs) |
| ADR or `DECISIONS.md` entry | n/a | the "K/DEF/IDP unsupported" decision already exists in `docs/plans/win-now/BUILD.md:78`; ordering format refusals before transient ones is documented in `prd.md` §3 |
| `living-memory/TEST_LEDGER.md` | **to be updated by build/QA** | RED/GREEN test names + counts, CI sha, checklist outcome |
| `docs/feedback/items/INDEX.md`, this folder's `status.md` | **to be updated by build/QA** | phase log |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (incl. `check-*.js`) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the five tests, the saved RED run on `b8d37085`, and the GREEN run on the fix sha; `FTF_SKIP_SIM_GATE=1` on push per D-056 with this evidence cited.
- **TestFlight verification:** `prd.md` §8 run by the operator after Render is LIVE (no new binary required); outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **no** — full gates (bright line not crossed: no schema/API-contract/flag/analytics change).
