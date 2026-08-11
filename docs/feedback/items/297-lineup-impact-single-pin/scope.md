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

**REWRITTEN 2026-08-11 from waiver to spec — the operator rejected the #297 waiver
below and made analytics the top priority of this batch.** Built by the analytics
instrumentation agent. Full tracking-plan addendum, including intent-vs-non-intent
reasoning and the sabotage matrix: **[`analytics.md`](analytics.md)**.

- [x] **(a) New events specced against the taxonomy.**

  | Event | New? | Fires from | Trigger | Props | Intent? |
  |---|---|---|---|---|---|
  | `lineup_impact_unavailable` | **new name** | `InLeagueCalculator.tsx` → `LeagueVerdict` | The honest-empty "Starting lineup" row renders (`both && !ev.starter_impact`), keyed on `ev` so it is one row per **evaluation**, not per mount | `platform` (LEAGUE platform: `sleeper`\|`espn`\|`mfl`\|`fleaflicker`\|`unknown`) | **NON-INTENT** |
  | `find_trades_tapped` | no — props widened | `TradesScreen.tsx` ×2 emitters | unchanged | **+`mode`** (`single_pin`\|`deck`), **+`source`** | INTENT, unchanged |
  | `trade_card_viewed` | no — props widened | `TradesScreen.tsx:2380` | unchanged | **+`mode`** | INTENT, unchanged |

  - **`mode` is a property, not a new event, on purpose.** #298 is a regression in
    *where existing controls render*. The question is "do the events that always fired
    on this path still fire from the pinned surface" — only a property on those same
    events can answer it, because a new name would have no pre-fix baseline. All three
    emitters read one `const deckMode`, so the legacy and consolidated CTA arms cannot
    disagree.
  - **`source` is a bug fix.** `handleFindTrades` has sent it since #257 and the empty
    prop registry (`frozenset()`) popped it on **every row** — the live twin of
    `trade_card_shared`'s discarded `landing`. Name survival and prop survival are
    separate silent failures on this endpoint.
  - **`platform` is the LEAGUE platform**, read from the session's cached league list —
    never from the league id's shape, because **ESPN and MFL ids can be numeric** (MFL
    `990062846` is live in this project's DB). Device platform is a server-derived
    *column*, never a prop (the NULL-`platform` incident).
  - **DAU guard.** `INTENT_EVENTS` is derived by SUBTRACTION, so taxonomy growth is
    intent-by-default. `lineup_impact_unavailable` was added to
    `analytics_queries.NON_INTENT_EVENTS` in the **same commit** as its allowlist entry
    — it is a passive impression, and the evaluation that produced it already counts
    the user via the server-fired `calc_trade_evaluated`. #298 added no event name, so
    it cannot perturb the series at all.
  - **#169 re-check.** #169 moved the Pass/Like *controls* into `TradeCard.tsx`; it did
    **not** move the `trade_card_viewed` emitter (still `TradesScreen.tsx:2380`) or
    change `advance()`'s server-fired `swipe`. Verified by call-site grep, so the
    property placement holds.

  Still true from the original spec, unchanged by this work: `swipe` (server-fired,
  from `advance()`, which every restored control funnels into) and
  `trade_keep_side_tapped` (`TradesScreen.tsx`) cover the disposition and the route
  *into* single-pin mode.

- **Deliberately NOT instrumented:** the server-side cause split on
  `calc_trade_evaluated` (`no_slot_template` vs `roster_missing`). It needs a
  `server.py` edit outside the analytics agent's ownership, `platform` already answers
  the product question, and the residual (`platform:sleeper` rows on the new event) is
  itself the signal that the finer split is worth adding. Cost to add later: one prop
  on one server `record_event` call. Reasoning in `analytics.md` §2.

- **Pre-wiring gate, owed at ship:** the deploy-then-probe check in `analytics.md` §7 —
  one hand-rolled `POST /api/events` per new name with its full property set, asserting
  `dropped == 0` **and** every property echoed back from `user_events.props`. Not run
  here; it needs a deploy.

<details><summary>Superseded — the original #297 waiver (rejected by the operator 2026-08-11)</summary>

> **WAIVED for #297** — the new `calc.lineup-impact-unavailable` row emits **no event**.
> Reason: it is a static explanatory row with no interaction. Instrumenting an
> impression would require a new registered event, a taxonomy edit in `backend/`
> (out of scope for this agent), and would answer a question — "how many users hit a
> non-Sleeper league in the calculator" — that is already answerable from the
> `platform` column on the leagues table without any client work.

Rejected because the leagues table answers "how many users *have* a non-Sleeper
league", not "how many users hit the wall in the calculator" — the impression is the
thing #297's fix creates, and only the client can witness it.
</details>

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
- [x] **New structural test:** `mobile/tests/check-single-pin-actions.js` (house
      `mobile/tests/check-*.js` convention; `npm run test:single-pin-actions`). AST check
      over `TradesScreen.tsx` pinning four invariants — no `singlePin ? null` gate may
      exclude any action control, `singlePinDeckActive` is keyed on `deck.length` not
      `topCard`, `FeaturedTradeWindow` stays gated on `!singlePinDeckActive` (#241), and
      both disposition buttons dispatch `advance()`. **All five of its sabotages were
      executed and each failed as intended** — output in `status.md` §4a. It needs no
      simulator, so unlike the Maestro flow it could be, and was, verified here.
- **Post-#169 note (integration round):** `f27c0f5` moved `trades.pass-btn` /
  `trades.like-btn` into `TradeCard.tsx` (`:538`, `:555`). No testID changed, so the
  Maestro flow and `testid-lint` are unaffected. The structural test WAS rewritten —
  not repointed — to pin the wiring chain across the new seam instead of co-location,
  with four added sabotages aimed at it: `status.md` §4a.
- **`testID`s added:** `trades.single-pin-deck-count` (TradesScreen.tsx:4771),
  `calc.lineup-impact-unavailable` (InLeagueCalculator.tsx:1062). No renames, no
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
- **CI gap found in passing:** none of the eight `mobile/tests/check-*.js` invariant
  tests run in `.github/workflows/ci.yml` today — they are `npm run`-only. Pre-existing,
  not caused here; proposed wiring in `status.md` §5.5 (I did not edit `ci.yml`, it is
  shared this batch).
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
