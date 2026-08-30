# Feature Scope — G-410: merged-canvas trade-card polish (#410 · #411 · #412 · #409-copy)

<!-- Copied from docs/templates/feature-scope.md. Every section answered or
     explicitly waived with a reason. §Maestro delta and §Simulator-gate tier
     are RETIRED per D-056 (2026-08-15) and are absent from the template's
     current revision — nothing is skipped silently here. -->

**Date:** 2026-08-30
**Entry point:** feedback #410, #411, #412 (group G-410, canonical folder = lowest id) + the #409 client-side copy correction folded in by orchestrator decision
**Builder:** `claude/fb-410-412-trade-card-polish`, cut from `origin/main` `bd83fe94`, currently `11c8903c`
**Operator sign-off on waivers:** **not needed — there are no waivers.** Every section below is answered. The two *rulings* that needed operator authority (the bare ✕ in the D-157 cell; tag-move-plus-shrink over wrapping) were obtained on 2026-08-30 and are recorded verbatim in [reconciliation-log.md](reconciliation-log.md).
**PRD:** [prd.md](prd.md) · **Plan:** [plan.md](plan.md)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new events, no changed properties, no changed emitters.

| Event | Status under this change | Question it still answers |
|---|---|---|
| `trade_pass_overlay_opened` / `_layer1` / `_layer2*` | **Unchanged.** The action-row decline routes into `handleBrowsePass` (`mobile/src/screens/TradesScreen.tsx:5750`), the same handler the pager ✕ called. Same emitters, same properties, same `/api/trades/pass-reason` writes. | Why users decline engine ideas. |
| `shop_opened` | **Unchanged, and this was verified rather than assumed.** It is emitted from exactly one call site, inside `openShopWindow`, at the navigate site (P-3), with `screen: 'Trades'`. #412 moves the *entry control's position in the tree*; it does not touch the fork (`openShopForCard`, `TradesScreen.tsx:3240`), the gate, or the emitter. `check-shop-deck.js` h4a/h4c/h4d/h5a/h5b pass **unedited** — that passing run is the verification. | "More offers" tap rate on Trades. |
| `calc_cleared` | **Not removed, not re-defined.** It simply cannot fire from the action row during a live browse session, because the cell is not a Clear there. A *reduction in emission on one state* — the event's meaning ("the user emptied the calculator canvas") is unchanged and still true everywhere it fires. | Canvas abandonment. |
| `calc_trade_queued` | **Unchanged.** #409's copy fix is on the refusal path, not the success path. | ✓ queue rate — which the FB-409 server fix (`11c8903c`) has just made non-zero for the first time. |

Nothing is registered in `backend/analytics_taxonomy.py`, and
`analytics_queries.NON_INTENT_EVENTS` is untouched. No `platform`-style
taxonomy hazard: no event's properties change.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No backend file is in this change's footprint; `backend/` is explicitly out of scope (PRD §11). `docs/data-dictionary.md` not applicable.
- **New/changed feature flags:** **none.** All three UI items ride the existing `calc.canvas_results` / `calc.inline_home` / `calc.merged_layout` conjunction, which **is** the rollback lever — turning `calc.canvas_results` off restores the pager, the deck and today's entry placement without a client build. `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS` and `docs/config-reference.md` are unchanged.
  - **Stated honestly:** #411 (the compact-row re-flow) and #409-copy are **not** flag-gated. #411 is inside `TradeSide`'s `compact` branch, which is reached only under the merged layout, so `calc.merged_layout` off still restores the stacked row — but the 13pt name and the moved chip are unconditional *within* compact mode. #409-copy is unconditional everywhere. Rollback for those two is `git revert` + an EAS build, not a flag flip.
- **New env vars / `model_config` keys:** **none.** `docs/config-reference.md` not applicable.
- **Ship-the-knob:** the deploy-free lever is `calc.canvas_results` → `false` via `POST /api/feature-flags/reload`. It covers #410 and #412 completely.

## 3. Evidence scope

- [x] **Structural guard:** **no new suite file** — three existing dependency-free suites are extended, which keeps CI's `tests/check-*.js` glob and the `npm run` script list unchanged.
  - `mobile/tests/check-canvas-results.js` — §3 pager-id loop **re-specced** (asserts `trades.canvas-results.pass` is absent, pager/prev/next still present); `4l` (`:270-271`) **re-messaged and extended** (assertion stays green; new sibling pins `browseDecline?:` as optional in both threading files); `12i` and `12i2` (`:584-591`) **re-specced** for the entry's new home. `12i5`'s `openShopForCard` count of 3 stays green.
  - `mobile/tests/check-calc-merged-layout.js` — rule `17` (`:273-275`) **re-specced** for `compactMetaText`'s added `minWidth: 0`, plus a new sibling pinning `flexShrink: 0` on the chip and badge slots. Rules `16` and `16b` (`:261-272`) **stay green unedited** — verified, contrary to the plan's claim (PRD §7.1). New assertions pin the chip's meta-line home, the token-sourced 13pt name, and `TierBadge size="sm"` compact-only.
  - `mobile/tests/check-calc-merged-behavior.js` — **additions, not a re-spec** (nothing there covers the middle cell today): the branch's `onPress` is the host prop's handler; `clear` has exactly one JSX call site; the two static testIDs; `disabled={!anySide}` on the Clear branch only; the `declineReasonProps` kill-switch parity; the single warning haptic; and the `not_league_member` copy + its comment carve-out.
  - **Untouched and expected green:** `check-shop-deck.js`, `check-any-partner.js` (A-1…A-15 — FB-406/407 code from hours earlier; its A-10 and A-11b pins are whitespace/textually exact), `check-picker-chip-alignment.js`, `check-inline-home.js`, `check-calc-tour.js`. Baseline run 2026-08-30 on `11c8903c`: all pass.
  - **15 named sabotages** (PRD §7.3, T-1…T-15), each a plausible wrong implementation rather than a regex negation, each proven RED before its assertion is accepted.
- [x] **Unit tests:** **none added, and none needed.** No Python file is touched. `pytest backend/tests` runs as an untouched-proof. (The FB-409 server fix already on this branch carries its own `backend/tests/test_calc_trade_queue.py` coverage — it is not re-litigated here.)
- [x] **Code-walk proof:** `docs/feedback/items/410-found-trade-decline-position/code-walk.md`, 7 steps, outlined with anchors in PRD §8. Load-bearing step: proving `clear()` and `track('calc_cleared')` are unreachable from the action row during a browse session, which is what closes the R-6 edit-map corruption.
- [x] **Manual TestFlight checklist:** `docs/feedback/items/410-found-trade-decline-position/testflight-checklist.md`, **18 numbered steps** (PRD §9), covering all four fixes plus #409's ✓ success (which ships in the same build) and the flag-off/pushed-page byte-identity check. Runtime proof genuinely matters here: three of the four fixes are purely visual, and step 11 is a **falsification test** for the PRD's own truncation predictions.
- [x] `testID`s added/renamed:
  - **added:** `calc.action.decline` (the browse-state middle cell)
  - **renamed:** `trades.canvas-results.more-offers` → `calc.give.more-offers` (the id should not claim a pager home it no longer has)
  - **removed:** `trades.canvas-results.pass` (the pager ✕; the control moved, R-4)
  - **unchanged, deliberately:** `calc.action.clear`, `calc.action.confirm`, `calc.action.find-a-trade`, `calc.action-row`, `calc.league-give-add`, `calc.league-receive-add`, `trade-card.keep-give`
  - All are static string literals; `bash mobile/scripts/testid-lint.sh` (still in CI) must pass with the additions/rename registered.
- **WAIVED:** nothing.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **n/a** | No route is added, renamed, removed or contract-changed. The decline path reuses `/api/trades/pass-reason` verbatim; the ✓ reuses `POST /api/trades/queue` verbatim. #409's fix is client copy only — the `not_league_member` wire reason is **deliberately not** split (PRD §11). |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated** | One convention genuinely shifts and is worth writing down: *a host-declared UI state reaches `InLeagueCalculator` as an optional prop, never as a flag read* — established by `hideFormatChips`/`seededPrefill`/`onSidesChange` and now extended to `browseDecline` and `TradeSide.belowAdd`. Add it beside the existing calculator-hosting notes. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No backend module is added, removed or re-wired; no data flow changes. Two optional presentational props are threaded through an existing client component chain. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client or major flow. The browse session, the decline machinery and the shop window all pre-exist and are reused unchanged. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **n/a** | Position hexes and tier labels/colors are untouched. The position chip is **moved** and the tier badge's **padding preset** changes (`size="sm"`, an existing prop); the invariants file governs colors and labels, not badge padding — verified against `docs/cross-client-invariants.md:9-28`. The `CalcQueueReason` enum is untouched. |
| `docs/glossary.md` (new domain term) | **n/a** | No new domain term. "browse session", "decline reason", "shop window", "compact row" all already exist. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **updated — required** | **`living-memory/DECISIONS.md` gains D-169**, amending D-157 and `docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4. Full verbatim text in PRD §13; the **Decision index** table at `living-memory/DECISIONS.md:438` gains the matching row. Next id verified as 169 (`D-168` at `:1043` is the current max). |

**Additional doc rows this change owes, beyond the template's list:**

| Doc | Updated? | Section / reason |
|---|---|---|
| `docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4 | **updated — required** | The placement clause *"never inside the action row's 50/30/20 cells"* is amended in the same commit as the code, with the exact replacement text given in PRD R-9. Its stated rationale (the 50/30/20 proportions) survives and is re-pinned. |
| `docs/design/components.md` | **updated** | The compact calculator asset row earns a construction entry: name on line 1 at `body-sm` metrics in Archivo 600 / `chalk.base`; meta line = position chip · team·age (yields first) · tier badge `sm`. Recorded because `docs/design/design-system.md:97-105` documents `title` as the token for "card titles, **player names**", and this row deliberately departs from that at a measured width budget — an undocumented departure is how a scale quietly stops being a scale. |
| `docs/design/design-system.md` | **n/a** | No token is added, removed or re-valued. The 11pt floor is respected with 2pt of headroom. |
| `mobile/src/components/CLAUDE.md` | **updated** | Rows for `InLeagueCalculator` (new `browseDecline` prop; the middle cell forks on it), `TradeBuildCanvas` (threads two more optional props), `TradeSide` (compact re-flow + the `belowAdd` slot). |
| `mobile/src/screens/CLAUDE.md` | **updated** | `TradesScreen` row: the pager no longer carries the ✕ or the shop entry. |
| `living-memory/CHANGELOG.md` | **updated at ship** | Dated H2 for the merge. |
| `living-memory/TEST_LEDGER.md` | **updated at ship** | Suite names + pass counts, the 15 sabotages, the code-walk and the checklist named as the mobile evidence, per D-056. |
| `living-memory/NEXT.md` | **updated at ship** | Queue items for #410/#411/#412 closed. |
| `docs/feedback/items/{410,411,412}/status.md` | **updated at ship** | Status → shipped, with the sha. |
| `docs/feedback/items/409-like-not-league-member/` | **n/a — deliberately not touched** | Owned by the FB-409 thread. The client copy change is recorded here and in the changelog; that folder is not edited by this group. |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (`pytest backend/tests`, untouched-proof) + `mobile-typecheck` (`tsc --noEmit` strict, which also runs the `check-*.js` suites) + `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`).
- **Evidence recorded** in `living-memory/TEST_LEDGER.md`: which suites ran, their pass counts, the 15 sabotages proven RED, and the code-walk + checklist named as the mobile runtime evidence.
- **TestFlight verification:** a checklist **was** written (§3), so it is run by the operator and its outcome — **including the answer to step 11's truncation pressure test** — is logged in TEST_LEDGER. The PRD makes a falsifiable prediction there; the checklist is what falsifies it.
- **Pre-push hook:** `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056; the note records the structural suites + code-walk + checklist as the evidence run instead. Install the hooks once per clone: `git config core.hooksPath githooks`.
- **Express lane declared by the operator?** **No.** Full gates apply. The operator ruled on *two design questions* (the ✕; tag-move-plus-shrink) — that is not an express declaration, and agents never self-select express. Note also that this change touches a **feature-flag surface** only as a consumer (no flag is added or flipped) and touches **no** schema, API contract or analytics event, so no bright-line confirmation is owed.
