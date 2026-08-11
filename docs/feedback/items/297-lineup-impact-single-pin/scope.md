# Feature Scope — #297 lineup-impact honest copy · #298 single-pin trade recovery

**Date:** 2026-08-11
**Entry point:** feedback #297 + #298 (both filed 2026-08-10 against shipped v1.12.0)
**Builder:** `/feedback` phase-2 build agent, branch `feedback-build-trades-297-298`
**Operator sign-off on waivers:** **needed** — three waivers below (§1 for #297, §2 flag,
§5 tier), each with its reason. Surfaced to the operator via the orchestrator.

Design contract: `mockups/polish-lab-2026-08-11/OPERATOR-DECISIONS.md` (#298 → **V1**,
buttons named **Pass / Like**) + `mockups/polish-lab-2026-08-11/trades-single-pin-recovery.html`.

---

## 0. What these two items are

| Item | Report | What it actually is |
|---|---|---|
| **#298** | "The UI when selecting a team or player is regressing. All versions should still have the find a trade UI and let the user accept / decline the trades as any other suggested trade." | Reproduces. Two `singlePin` null-gates removed the Find-a-Trade CTA **and the whole deck wrapper**, which carried every accept/decline path. Fires identically in the `trades_home_inline` **control** group — the experiment is not the cause and is not touched. |
| **#298b** | (not reported; found in the lab) | The strip's team pill leaves the user in `'guided'`, so `scopedOpponent` changing reset the deck and regenerated nothing. Folded in, operator-approved. |
| **#297** | "The lineup change feature that shows the players traded and the impact on starting lineup doesn't appear anymore." | **Not a regression.** `LineupImpactTable` was never mounted on a deck or featured card; `git log -S` shows only additive commits. The real defect is that the client rendered a bare `null` when the server omitted `starter_impact`, so a section vanished with no copy. Fix = honest copy. |

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new events. Every restored control already
      emits through paths this change does not modify:

  | Event | Registered at | Question it answers post-fix |
  |---|---|---|
  | `find_trades_tapped` | `backend/analytics_taxonomy.py:51`, props `frozenset()` (`:191`) | Are pinned users generating decks again? Pre-fix this could not fire in single-pin mode at all — the button did not exist. A non-zero count from a pinned session is itself the fix's telemetry. |
  | `swipe` | `analytics_taxonomy.py:111` | Are pinned users dispositioning trades? Emitted from `advance()`, which every restored control (swipe, `trades.pass-btn`/`trades.like-btn`, VoiceOver actions) funnels into. |
  | `trade_keep_side_tapped` | emitted at `TradesScreen.tsx:2003` | Unchanged; it is the main route *into* single-pin mode. |

  No taxonomy edit needed, so the DEFAULT-DENY drop path is not in play: every event
  this change can cause is already registered and will be accepted server-side.

- **WAIVED for #297** — the new `calc.lineup-impact-unavailable` row emits **no event**.
  Reason: it is a static explanatory row with no interaction. Instrumenting an
  impression would require a new registered event, a taxonomy edit in `backend/`
  (out of scope for this agent), and would answer a question — "how many users hit a
  non-Sleeper league in the calculator" — that is already answerable from the
  `platform` column on the leagues table without any client work. Recommend the
  orchestrator route that question to `/an-user-data` instead of new instrumentation.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No backend file is touched by this change.
- **New env vars / `model_config` keys:** none.
- **New/changed feature flags: NONE — and this is a deliberate, argued deviation from
  the default-to-a-kill-switch instruction. WAIVER, operator sign-off requested.**

  The instruction was to default to a kill-switch flag for #298 V1 unless it could be
  argued against convincingly. Three findings, all from source, say a new flag here is
  worse than none:

  1. **A client-only flag cannot exist.** `useFeatureFlags.revalidateFlags`
     (`mobile/src/state/useFeatureFlags.ts`) does `set({ flags })` — a **whole-map
     replace**, not a merge. `LAUNCHED_FLAG_DEFAULTS` only survives until the first
     successful `/api/feature-flags` fetch. A key present only in that map would be
     `true` at first paint and `false` a second later. That is a *worse* failure than
     FB-115: not a hidden feature, a flickering one.
  2. **Registering it properly requires a `backend/` edit, which is out of scope for
     this agent.** `_load_from_json` (`backend/feature_flags.py:653-659`) drops any key
     not in `DEFAULT_FLAGS` with `ignoring unknown key`, so `config/features.json` alone
     does nothing. The flag needs `FLAG_KEYS` + `DEFAULT_FLAGS` in
     `backend/feature_flags.py`, and I was instructed not to touch `backend/`.
  3. **A kill switch already exists and already covers exactly this blast radius.**
     `singlePin` (`TradesScreen.tsx:1038-1045`) requires `trade.asset_ideas`. Set that
     flag `false` and `singlePin` is `null`, so `singlePinFeatured` /
     `singlePinDeckActive` are both false and every line this change touches falls back
     to the classic unconditional CTA + deck. The reverted surface is the pre-#216
     home rather than v1.12.0's featured window — a slightly larger hammer, but a real
     server-side, deploy-free lever that turns off 100% of this diff.

  **If the orchestrator disagrees, the exact diff to add one is written out verbatim in
  `status.md` § "Proposed edits to files I do not own"** — four touches
  (`backend/feature_flags.py`, `config/features.json`,
  `backend/tests/fixtures/flags/release.json`, `docs/config-reference.md`) plus the
  `useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS` entry, ready to apply.

  **Deploy-free rollback lever (the "ship-the-knob" answer):** `trade.asset_ideas → false`
  in `config/features.json` or `FTF_FLAGS`.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml` — signs in,
      enters `finderMode === 'player'` by launch argument (the board is player-mode only,
      and the mode-bar chips that reached it are hidden under `trades.sheet_targeting`),
      pins exactly one asset, then asserts all three things #298 says went missing:
      `trades.find-btn` survives the pin, a deck renders (`trades.card-top` +
      `trades.single-pin-deck-count`), and `trades.pass-btn` / `trades.like-btn` are both
      present and the accept path works.
- **`testID`s added:** `trades.single-pin-deck-count` (TradesScreen.tsx:4647),
  `calc.lineup-impact-unavailable` (InLeagueCalculator.tsx:1024). No renames, no
  removals — every existing id on this surface is preserved deliberately, because #298's
  whole point is that the *existing* vocabulary should still be reachable.
  `mobile/scripts/testid-lint.sh` → `testid-lint OK`, exit 0.
- **Capture delta:** `trades` — and note the gap the lab called out: `screens/manifest.json`
  lists seven `trades` states and **none of them is single-pin**, so there is no "before"
  frame for either item. Request
  `mobile/scripts/screen-capture.sh --screen trades --state single-pin` at ship.
- **Smoke-suite impact:** `05-trades-render.yaml` and `06-trades-deck.yaml` cross this
  surface. Both operate with **zero pins**, where `singlePin` is `null` and every branch
  this change adds is inert — `singlePinFeatured` is false, so the CTA, the progress
  strip, the deck wrapper and the featured block all evaluate exactly as before. Expected
  still-green; must be re-run in the QA round (see `status.md` QA checklist), not claimed
  here.
- **Backend: no pytest files added or updated** — WAIVED because no backend file is
  touched. The `_starter_impact` / `_sleeper_lineup_slots` behaviour #297 explains is
  pre-existing and already correct; the change is client copy for a case the server
  already handles by omission.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

Shared docs are orchestrator-owned for this batch (three agents editing the same files
caused real merge conflicts in a prior batch), so the rows below are answered with the
verdict and, where an edit is owed, the **verbatim text is in `status.md`** for the
orchestrator to apply.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `starter_impact` on `POST /api/trade/evaluate` is already documented (`:286`) as optional; this change adds client copy for the documented-absent case. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant convention shifted. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change; one screen and one component, same imports. |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | **TEXT PROVIDED** → `status.md` | The operator's "Pass / Like" naming decision is cross-client and the decisions doc explicitly says to settle it here. Orchestrator applies. |
| `docs/glossary.md` | **TEXT PROVIDED** → `status.md` | "single-pin mode" is used across TradesScreen, the lab and both items and is not defined anywhere. Orchestrator applies. |
| ADR / `DECISIONS.md` | **TEXT PROVIDED** → `status.md` | Two non-obvious choices: (1) V1's deck-yields-the-featured-slot rule, which is how #241's fix is preserved rather than reverted; (2) shipping #298 without a new flag, with the `trade.asset_ideas` reasoning above. Orchestrator applies. |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` | **TEXT PROVIDED** → `status.md` | Orchestrator applies at ship. |

## 5. Ship gate declaration

- **Simulator-gate tier: 2** (feature flow + affected smoke subset) — the new
  `12-trades-single-pin.yaml` plus `05-trades-render.yaml` and `06-trades-deck.yaml`.
  Rationale: a user-visible change to one live surface, no schema, no API contract, no
  new flag; the two smoke flows are the ones that cross TradesHome.
- **WAIVED for this agent, deferred to the batch QA round:** I ran **no** simulator and
  **no** Maestro. Explicit instruction — multiple parallel agents contending for one
  simulator and one harness Flask reseed each other's DBs and strand processes. My
  verification is static only (`tsc`, `testid-lint`, targeted greps); actual output is in
  `status.md`.
- **Evidence owed at ship (not by me):** TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json`
  written after the QA round's tier-2 run.
- **Operator deviation from the matrix:** none proposed. If the QA round cannot reach the
  pinned surface on the `standard` profile (deck contents are server-chosen), that is a
  fixture question, not a reason to drop the tier — see the QA checklist's fallback.
