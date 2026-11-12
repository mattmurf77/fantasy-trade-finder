# Feature Scope — In-app add/drop and waiver claims: D1 Update 1 (MFL, dark)

**Date:** 2026-11-11
**Entry point:** direct ask (operator: "create add/drop and waiver claim transactions directly from the app rather than send the user to sleeper/espn or mfl")
**Builder:** `feat/in-app-claims` subagent (resume of D1, `docs/plans/sleeper-fa-write/`)
**Operator sign-off on waivers:** needed for the two waivers below (§3 TestFlight, §4 HLD) before any flip; nothing here flips anything

Design and findings: [design.md](design.md). Parent scope (product behaviour, states, copy): `docs/plans/sleeper-fa-write/scope.md` on `origin/plan/fa-moves-launch`; wire contract: [`../sleeper-fa-write/contract.md`](../sleeper-fa-write/contract.md), unchanged.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** The D1 set (`backend/analytics_taxonomy.py`, addendum `docs/business/analytics/2026-11-01-fa-move-events.md`) already carries `league_platform ∈ sleeper | mfl | espn`. The MFL path emits the same three server events with the same props: `fa_move_consent_recorded` (a grant), `fa_move_consent_withdrawn` (`via` `credential_expired` / `credential_rejected` when MFL refuses the cookie; non-touching), `fa_move_write_succeeded` (a 200). The client's four `fa_move_*` events need no change (they already read `league_platform` from the capability). Questions answered: MFL move volume and success, consent uptake, cookie churn. No new event, prop or value.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** `delete_mfl_credential` now appends withdrawals to the existing `platform_write_consents` (a no-op until an MFL grant can exist) → noted in `docs/data-dictionary.md`.
- New feature flag: **`mfl.send_add_drop`**, default **false**, server-only (`backend/feature_flags.py` `FLAG_KEYS`, `config/features.json`, the three flag fixtures, `docs/config-reference.md`). **Graduation:** (1) one supervised real MFL `fcfsWaiver` recorded and pinned (design.md §8) and `mfl_write.FA_MOVE_SHAPES_VERIFIED = True` in that commit; (2) legal's final MFL consent text and `CURRENT_CONSENT_VERSION["mfl"]`; (3) the TestFlight run below; then the operator flips `FTF_FLAGS`.
- `espn.send_add_drop`: **not added** (no ESPN shape exists to gate).
- New env vars / `model_config` keys: **none.** Rollback lever: `FTF_FLAGS` `"mfl.send_add_drop": false` on Render (no deploy); `docs/runbook.md` § Free-agent moves kill switch.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-in-app-claims.js` (`npm run test:in-app-claims`), 13 checks: every code the MFL server path emits (parsed from `server.py`) maps like its `sleeper_` twin; the MFL capability's three readings; confirm (no submit without a tick or a grant); one call site of the move API and state 12 for every may-have-landed answer; the 91 s timeout against the server's 76 s and MFL's write path inside 46 s; 404 → the hand-off with no Sleeper opener on MFL; no client read of any `send_add_drop` flag. 9 named sabotages, each red, trees checksummed unchanged.
- [x] **Unit tests:** `backend/tests/test_mfl_fa_move.py` (62): the builder pinned to MFL's docs (exact params, never REPLACE / FRANCHISE_ID, malformed → `input`), refusal before building while unverified, the shipped constants and flag off, error classification, the timeout budget; flag-off and flag-on-unverified capability **byte-identical** to the pre-Update-1 block and a 404 with zero MFL calls, zero rows; the live path end to end against a fake MFL (crosswalked params, grant bound to the MFL username and in force at the call, roster saved, replay, outcome unknown never retried and blocking, failure codes, cookie rejected → credential and grant gone, pre-write refusals send nothing, claims off, no consent text → no move, the cookie never logged or returned). 11 named sabotages, each red, files checksummed back.
- [x] **Code-walk proof:** design.md §4 (steps) with `server._fa_move_core` → `_fa_move_core_mfl` → `_fa_move_send`; the dispatch sits after step 7b, so every shared check runs first; `_fa_move_live("mfl")` reads the flag before the constant (pinned).
- [ ] **Manual TestFlight checklist — WAIVED for this branch:** nothing user-visible changes until the verification commit (both locks are off, the binary is unchanged). The checklist is design.md §8 MFL steps 5–6, run once at the flip.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | § Free-agent moves: heading flags, "MFL leagues (D1 Update 1)" paragraph |
| `living-memory/LLD.md` | n/a here | the builder was told not to touch `living-memory/`; the convention (two locks per platform: flag + verified-shape constant; credential deletion withdraws grants) is owed by the merging session |
| `docs/architecture.md` | n/a because | no module added or re-wired: `mfl_write` gains functions, `server.py`'s D1 block gains an MFL branch |
| `living-memory/HLD.md` | waived | not an architecture shift (no new module/client/flow); and not writable by this builder |
| `docs/cross-client-invariants.md` | n/a because | no shared constant changed (the timeout, codes and `league_platform` set are unchanged) |
| `docs/glossary.md` | updated | "Verified write shape" |
| `docs/integrations/mfl.md` | updated | §7 endpoints W3–W5, § Free-agent moves (safe-to-log / must-redact) |
| `docs/config-reference.md` | updated | `mfl.send_add_drop` row; the Sleeper row's Update 1 sentence |
| `docs/data-dictionary.md` | updated | `platform_write_consents`: credential deletion withdraws |
| `docs/runbook.md` | updated | § Free-agent moves kill switch: MFL bullet |
| ADR or `DECISIONS.md` entry | owed | design.md §9 decisions 1–6 await the operator; the merging session records the answers |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs every `check-*.js`) + `maestro-testid-lint`, on the pushed sha. Local results are in the builder's report; the merging session logs them in `living-memory/TEST_LEDGER.md` with `FTF_SKIP_SIM_GATE=1`.
- **Evidence recorded:** TEST_LEDGER entry owed by the merging session (this builder may not write `living-memory/`).
- **TestFlight verification:** at the MFL flip only (design.md §8).
- Express lane declared by the operator? **No.** Flag and API-contract surfaces are touched, so full gates.
