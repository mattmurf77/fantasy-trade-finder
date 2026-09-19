# Feature Scope — G-428: Sleeper refuses spent-season pick sends (#428)

<!-- Copied from docs/templates/feature-scope.md (D-056 revision). Every section answered; one waiver, stated. -->

**Date:** 2026-09-08
**Entry point:** feedback #428 (mattmurf77, v1.17.2 build 154, screen `TradesHome`) — group G-428, batch [plan.md](../422-win-now-ffv3-unavailable/plan.md), fast-track bug path
**Builder:** Phase 2 build agent on branch `claude/feedback-422-428` (backend first; mobile copy optional)
**Operator sign-off on waivers:** **needed for one item** — see the bright-line notice
**PRD:** [prd.md](prd.md) · **Investigation:** [investigation.md](investigation.md)

**Bright-line notice (CLAUDE.md § Feature gates):** the batch plan filed this as "no schema/API/flag change". The fix as specced **adds one API contract value** — 422 `sleeper_pick_untradable` on `POST /api/trades/propose` (+ `pick_untradable` in the validate `code` vocabulary, + one `sleeper_send_failed.error_code` enum value, + `message`/`season_window` fields on existing bodies). No schema, no flag. The operator must confirm the contract addition before build; the fallback if refused is to fold untradable rows into the existing `sleeper_pick_unmapped` code (same server predicate, but the fielded mobile branch then shows the "Generic picks like Early 1st" copy for a spent pick — misleading, which is why the new code is preferred). Fielded build 154 renders `detail` for any unknown code, so the new code works without an EAS build.

---

## 1. Analytics scope

- [ ] **(a) New events specced** — none.
- [x] **(b) Existing events cover it — with one closed-enum extension:**

| Event | Change | Question it answers |
|---|---|---|
| `sleeper_send_failed` (client) | `error_code` closed enum 17 → 18: adds `sleeper_pick_untradable`. No emitter change (`SendInSleeperButton.tsx:254-264` sends `body?.error`); `CLIENT_EVENT_PROPS` constrains keys, not values; `WAT_LIVE` already lists the event; `NON_INTENT_EVENTS` untouched. Five comment/doc sites must agree on "18": `backend/analytics_taxonomy.py:1055-1074`, `docs/cross-client-invariants.md:872`, `docs/business/analytics/2026-08-11-p0-7-addendum.md:64-67`, `SendInSleeperButton.tsx:252-253`, `sendInSleeper.ts:5-7`. | How often a spent/out-of-window pick is refused server-side. **Reader warning:** `sleeper_write_failed` rows 2026-09-03 → deploy include this class (Sleeper-side refusals); do not read the drop as a Sleeper improvement. |
| `sleeper_send_succeeded` (server) | unchanged | — |

- [ ] **(c) WAIVED** — n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** The sync reads the existing `leagues.draft_status` verdict (#207) as a fallback; the grid is written by the existing replace-sync.
- New/changed feature flags: **none — stated, not waived.** The change lives inside `picks.owned_sync` (sync) and `trade.send_in_sleeper` (send/validate). A flag to gate a refusal that replaces a Sleeper-side 502 would add a second way to keep pick sends broken. Deploy-free levers already exist: `trade.send_in_sleeper` → false removes the surface; `picks.owned_sync` → false freezes the grid.
- New env vars / `model_config` keys: **none.**

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-send-button-platform.js` extended (existing `npm run test:send-button-platform`) — pins: the `sleeper_pick_untradable` branch exists, renders `detail`, never calls `goConnect`. Only if the optional mobile branch ships.
- [x] **Unit tests:** `backend/tests/test_pick_horizon.py`, `test_owned_picks.py`, `test_sleeper_write_route.py`, `test_sleeper_write.py`, `test_trade_send_validate.py` — names and fixture shapes in [prd.md §5](prd.md); the three RED-first cases are named there.
- [x] **Code-walk proof:** the QA agents cite (1) sync: `_sync_sleeper_owned_picks` → `completed_draft_seasons` → cached-verdict fallback → `sync_draft_picks(exclude_seasons=…)`; (2) send: `_sleeper_propose_core` → drafts + meta fetch only when a pick is present → `sleeper_pick_window` → `_sleeper_encode_ftf_picks(window=)` → 422 before `propose_trade`; (3) overhaul sends reach the same core (`backend/overhaul_api.py` → `_sleeper_propose_core`); (4) `_post_graphql` → first `errors[].message` → 502 `detail`.
- [x] **Manual TestFlight checklist:** [prd.md §7](prd.md), 5 steps, runs on build 154 after the Render deploy (no EAS needed).
- [ ] **WAIVED because:** —
- `testID`s added/renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `/api/trades/propose` error table: 422 `sleeper_pick_untradable` row; 502 row gains `message`; validate `code` vocabulary gains `pick_untradable` |
| `living-memory/LLD.md` | **updated** | the pick-send convention: three ground truths (grid, holder, tradable window) and the D-189 fallback order |
| `docs/architecture.md` | n/a | no module wiring change — `draft_status` already owns the horizon; the send path gains two conditional reads |
| `living-memory/HLD.md` | n/a | no new module, client or flow |
| `docs/cross-client-invariants.md` | **updated** | `:872` enum listing (18 values) and the validate `code` vocabulary |
| `docs/integrations/sleeper.md` | **updated** | §2 rows 6–7 consumers; §3.3 tradability rule + the confirmed field-1 semantics (Q-037 closed); §5 call budget: pick sends now `+drafts +meta` |
| `docs/glossary.md` | n/a | no new term ("tradable window" is D-089's existing pick horizon) |
| ADR or `DECISIONS.md` entry | **D-189** | the sync's unknown-draft fallback now consults the cached #207 verdict (narrows the D-089 "flake excludes nothing" fail-safe with corroboration); Q-037 closed on public Sleeper evidence |
| `docs/runbook.md` | **updated** | one row: "pick send refused by Sleeper with `These draft picks cannot be traded`" → check grid seasons vs `/drafts` |
