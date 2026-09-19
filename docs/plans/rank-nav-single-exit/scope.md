# Feature Scope — One rank exit: Back removed, "More ways to rank" → the chooser

**Date:** 2026-08-16
**Entry point:** direct ask (operator, 2026-08-16) — "The need for a back button and a
more ways to rank button is unnecessarily redundant. Let's remove the back button from the
page and just have the 'more ways to rank' button bring users back to … 'build your board'."
**Builder:** this session
**Operator sign-off on waivers:** yes — §3 and §5 are n/a under [D-056]

## 0. The change

Flag-on (`ux.rank_tab_destination: true`, live in prod) rank surfaces carried **two controls
for one destination**: a Back control whose fallback was `RankHome`, and "More ways to rank"
which opened the `RankMenu` sheet listing the same three methods `RankHome` already shows.

- **Back is removed** from all 8 flag-on rank surfaces (Trios, Pick Anchors, Tiers, Quick Set
  Tiers, Quick Rank, Overall Ranks, Rookie Ranks, Trends).
- **"More ways to rank" now navigates to `RankHome`** ("Build your board") instead of opening
  the sheet — the fuller page, and the **only** surface carrying the rankings-import entry
  point ("Have rankings already?"), which the operator could not find from the sheet.
- `RankHome` **keeps its own Back** (it has no More-ways control; stripping it would strand
  the chooser). iOS edge-swipe is untouched everywhere.
- The `RankMenu` sheet component stays mounted — the **flag-off** tab-press path still opens
  it, so `ux.rank_tab_destination: false` remains a true rollback.

**Consequence, stated:** with the flag on (production), the three-option sheet is no longer
reachable from anywhere. That is the intent — the chooser replaces it.

## 1. Analytics scope

**(c) WAIVED — no analytics needed because:** neither control emits an event today (verified:
no `track()` call in `MoreWaysButton`, `RankMenu`, or `HeaderBack`), so there is no funnel to
preserve or re-point, and this change adds no new user-visible capability to measure — it
removes a redundant control. Tab-level `trackTab('rank', …)` is untouched. If the chooser's
reachability later needs measuring, that is a new event on `RankHome`, not on this edit.

## 2. Schema & flag scope

- Tables/columns: **none**
- Feature flags: **none added.** Behavior rides the existing `ux.rank_tab_destination`
  (already `true` in prod); its **off** path is deliberately left byte-identical, which is the
  rollback lever — no deploy needed, flip the flag and Back returns.
- Env vars / `model_config`: **none**

## 3. Test scope

- **Maestro delta: n/a per [D-056]** (Maestro/simulator retired). Replacement, mandatory and
  shipped: `mobile/tests/check-rank-nav-exit.js` (9 assertions, `npm run test:rank-nav-exit`),
  **6 sabotages run and caught**: restoring `headerLeft`, dropping `headerBackVisible`,
  re-pointing More-ways at the sheet, stripping RankHome's own Back, breaking the flag-off
  branch, and dropping MoreWaysButton from the header.
- The suite exists specifically to guard the repo's oldest nav trap (#162/#165 "stuck in a
  ranking loop") — a rank surface with no path to the chooser. Removing a back control is
  exactly the edit that recreates it.
- `testID`s added/renamed: **none** (`rank.more-ways` keeps its id; `stack.back-btn` still
  ships on League/Draft/RankHome headers). `testid-lint OK`.
- Backend pytest: **n/a** — client-only navigation change.
- **Existing `mobile/.maestro/` flows that tap `rank.more-ways` expecting the sheet
  (`capture/sheets/sheets-rank-menu.yaml` and others) now document stale behavior.** Left
  in place per [D-056] ("historical artifacts — kept, never run"); flagged here so a future
  reader doesn't mistake them for current truth.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route touched |
| `living-memory/LLD.md` | n/a | carries no back-control/nav convention (verified by grep); the convention lives in `mobile/src/navigation/CLAUDE.md` |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | nothing shared across clients (mobile-only nav) |
| `docs/glossary.md` | n/a | no new domain term |
| `mobile/src/navigation/CLAUDE.md` | **updated** | the "every surface falls back to RankHome on back" line + the never-strand rule now describe the single-exit topology |
| ADR / `DECISIONS.md` | **n/a** | a UI-redundancy removal inside an existing flag's on-path, reversible by that flag; the reasoning lives in the code comment + this scope block. No design choice a future session could unknowingly overturn |
| `docs/config-reference.md` | n/a | no flag added; `ux.rank_tab_destination`'s description still accurate |

## 5. Ship gate declaration

- **Simulator-gate tier: retired per [D-056]** — standing `FTF_SKIP_SIM_GATE=1`.
- Evidence: structural suite + sabotage above, `tsc` clean, `testid-lint OK`, CI green.
- **Runtime proof owed:** operator TestFlight pass — the header renders on device only.
  Check: on each rank surface the header shows **no Back**, "More ways to rank" lands on
  "Build your board", the chooser's own Back returns to the ranking surface, and edge-swipe
  still works. Requires a build newer than 112.
- Operator deviation from the matrix: none beyond [D-056] (the standing rule).
