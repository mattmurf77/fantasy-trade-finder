# Feature Scope — League drill-in: 32pt roster tiles (#299) + header back affordance (#302)

**Date:** 2026-08-11
**Entry point:** feedback #299 + #302 (grouped — same screen, same drill-in panel; lowest ID owns the folder)
**Builder:** `/feedback` Phase-2 build agent, worktree `build-league-299-302`, branch `feedback-build-league-299-302`, base `origin/main` @ `ab9368f`
**Operator sign-off on waivers:** **needed** — three waivers below (§1 analytics, §2 flags, §5 tier deviation). None was operator-declared; each is an agent recommendation awaiting sign-off.

Design contract: `mockups/polish-lab-2026-08-11/OPERATOR-DECISIONS.md` (#299 → **32pt**, #302 → **V2**), pages `league-tile-density.html` and `drilldown-back-affordance.html` on branch `feedback-mocks-297-302` @ `221c134`.

---

## 1. Analytics scope

**REWRITTEN 2026-08-11 from waiver to spec — the operator rejected the waiver below
and made analytics the top priority of this batch.** Built by the analytics
instrumentation agent. Full tracking-plan addendum, including intent-vs-non-intent
reasoning and the sabotage matrix, lives with the batch's lowest ID:
**[`../297-lineup-impact-single-pin/analytics.md`](../297-lineup-impact-single-pin/analytics.md)**.

- [x] **(a) One new event specced against the taxonomy. The enter half was already
  registered and is ADOPTED, not duplicated.**

  | Event | New? | Fires from | Trigger | Props | Intent? |
  |---|---|---|---|---|---|
  | `league_team_opened` | **no — already shipped (P0-7, `b904ff2`)** | `openTeam` in `LeagueSummaryScreen.tsx` | Drill-in opens, from the chart bar or the list row | `via` (`bar`\|`row`), `rank`, `basis`, `subset`, `filter_count` — **unchanged** | INTENT, unchanged |
  | `league_team_closed` | **new name** | `emitTeamClosed(via)` — the single exit choke point | Focus ends through any of its five controls | `via`, `dwell_ms`, `rank` | **NON-INTENT** |

  **The waiver's central premise is now false.** It said "no registered event covers
  the League drill-in at all" — true when it was written, and false by the time it
  shipped: `origin/main` gained 17 client events in the interim, including the whole
  P0-7 League family. `league_team_opened` is fired from the same `openTeam` helper
  both drill-in entry points route through, and it **fully covers the enter half**,
  including the same bar-vs-row `via` the waiver proposed re-minting as
  `chart_bar | list_row`.

  **So the focused/unfocused PAIR was not built.** Two events for one interaction on
  this screen is the two-sources-of-truth bug #208/#248/#293 are a catalog of.
  `mobile/tests/check-analytics-297-302.js` fails if `league_team_focused` or
  `league_team_unfocused` reappears in the screen **or** the taxonomy (sabotage J12).

  **The genuine gap was the EXIT, and it takes one event.** The drill-in is component
  state, not a stack push, so it emits no `screen_left` and no navigation event —
  there is no way to know whether a user leaves deliberately at all (literally #302's
  claim), which of the five exits they use, or how long a drill-in lasts.

  - `via` is a **closed 5-value enum**, one per control, each asserted to appear
    exactly once in the file: `header_back` (#302's stack-header control),
    `in_card_link` (the #243 link, root-stack push only), `hardware_back` (#302's
    `BackHandler`), `tab_retap` (#302's active-tab re-tap), `refocus` (opened a
    different team without leaving the panel).
  - **The only bare `setSelectedId(null)` in the file is the one inside `closeTeam`**
    — asserted, and sabotage-proven (J1). Any control that clears focus without
    routing through the choke point would vanish from the data while the UI kept
    working: a silent hole, not a visible bug.
  - The focus interval lives in a **ref, not state**: two of the five controls are
    registered in effects whose deps deliberately exclude `selectedId`, so a state
    closure would report the focus live when the handler was *registered*.
  - **The sixth case is measured by absence, deliberately.** A `league_team_opened`
    with no matching close before the next `screen_left` is "abandoned by navigating
    away" — the stranded-user state #302 exists to fix. No unmount-cleanup emitter,
    because it would double-fire on React strict-mode remounts and invent dwell.
    Exit rate = `count(closed) / count(opened)`; the shortfall is the abandon rate.
  - **DAU guard.** `INTENT_EVENTS` is derived by SUBTRACTION, so taxonomy growth is
    intent-by-default. `league_team_closed` went into
    `analytics_queries.NON_INTENT_EVENTS` in the **same commit** as its allowlist
    entry: it is a terminator, dismissal-class like `quickset_abandoned`, and every
    close is preceded by an opener that already counts the user. `league_team_opened`
    **stays INTENT, untouched.**
  - No `league_id` / `league_id_hash` prop, by decision: client rows carry
    `league_id=NULL` by ingest contract, and a per-user league hash is unbounded
    cardinality for no question anyone asked. No `scroll_depth_bucket` either — it was
    never derivable from the screen's state.

- **Test delta:** `mobile/tests/check-league-drill-in.js` stays at **30 assertions,
  30 PASS** — two regexes repointed from `setSelectedId(null)` to the choke-point
  call; none added, none removed. New: `mobile/tests/check-analytics-297-302.js`
  (`npm run test:analytics-297-302`), a client↔taxonomy cross-check with 12
  executed sabotage proofs.

- **Pre-wiring gate, owed at ship:** the deploy-then-probe check in `analytics.md` §7.
  Not run here; it needs a deploy.

<details><summary>Superseded — the original waiver (rejected by the operator 2026-08-11)</summary>

> - [x] **(c) WAIVED — no analytics needed because:**
>
> Both items are presentation/navigation polish on an existing surface. Nothing new is collected, no new decision point is introduced, and no existing funnel changes shape.
>
> - **No registered event covers the League drill-in at all.** There is no `team_focused`, no `drill_in_*`, no screen-view event for `LeagueRankings`.
> - Measuring #302's actual success claim would need a **new registered pair** (focus-entered / focus-exited with an exit-method property).
>
> **Recommendation, explicitly out of scope here:** `league_team_focused {league_id_hash, team_rank}` and `league_team_unfocused {exit_method, scroll_depth_bucket}`.

Rejected on both counts: the premise was stale (`league_team_opened` and
`league_view` shipped in P0-7), and the recommended pair would have duplicated the
enter half.
</details>

## 2. Schema & flag scope

- **New/changed tables or columns:** none. Both `r.tier` and `playerPosRank` were already on the `GET /api/league/power-rankings` payload and already rendered — #299 only moves where the tier badge sits in the tile. No migration, no `docs/data-dictionary.md` row.
- **New/changed feature flags: none — and this is a deliberate call, not an omission.**

  Reasoning, since a tile-geometry change to a shared primitive is a plausible kill-switch candidate:

  | | Argument |
  |---|---|
  | **For a flag** | `PlayerCard` is shared by three screens. A geometry regression there is app-wide, and FB-115 is the precedent for a live feature nobody could turn off. |
  | **Against (taken)** | The blast radius is **structurally** zero rather than conditionally zero. The new layout is reachable only through the opt-in `denseSingleLine` prop; `styles.cardDense` still declares `height: 60` and the Tiers/FreeAgents call sites are byte-identical. A flag would gate a code path that only one caller can even reach, so it would buy nothing a `denseSingleLine={false}` one-liner does not already buy. Both facts are pinned by `mobile/tests/check-league-drill-in.js` and each is proven to fail on a sabotaged build (S4, S5, S17). |
  | | #302 is navigation, not a feature surface: flagging a back button means shipping a state with no exit if the flag is off. Worse than the bug. |

  **The deploy-free rollback lever, named as required:** revert `denseSingleLine` at `LeagueSummaryScreen.tsx:1309` (one word) and `minHeight: 32 → 40` at `:2375`. Both are client-only and ride the next EAS build; there is **no server-side kill switch**, which is the honest cost of not adding a flag. If the operator wants a server-side lever, say so and it becomes `visual.league_tile_dense` added to `LAUNCHED_FLAG_DEFAULTS` in `useFeatureFlags.ts` in the same change (per FB-115) — roughly 15 lines.

  `league.picks_always_counted`'s long comment in `config/features.json` was read before deciding: it governs *which rows render* in this panel (whether the Draft-capital group appears under Starters/Bench). The `pickRow` change here is height only and is orthogonal — it does not read, widen, or narrow that flag's condition.
- **New env vars / `model_config` keys:** none.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` — tags `[league, nav]`, profile `standard`, flags fixture `release`.
  - **T1** drill in → assert the swapped header title + exit exist and the unfocused landmarks are gone → scroll deep into the roster → assert the exit is *still* there → **tap it at depth with no scroll-back** → assert `league-summary.league-home` + `league-summary.refresh` return and the exit is gone.
  - **T2** drill in → re-tap the active League tab → assert focus cleared (`league-summary.focus-caption` gone).
  - **How it discriminates** (flow-authoring law 2 — `visible:` counts off-screen ScrollView children, so "the exit is visible after scrolling" passes on the *unfixed* build too): it anchors on `league-summary.header-title`, a **native-header** element that does not exist before this change and is never a ScrollView child; and it taps the exit at depth, which on `origin/main` lands on dead coordinates ~740pt above the viewport.
- [x] **Extended flow:** none. `flows/league/01-picks-in-subsets.yaml` already taps `league-summary.roster-close` and keeps working unchanged — the id deliberately moved with the control (the #243 precedent).
- **`testID`s added/renamed:** one added — `league-summary.header-title` (`LeagueSummaryScreen.tsx:2059`). `league-summary.roster-close` and `league-summary.back-all-teams` are **kept, not renamed**, and move to the header control on the tab root. `mobile/scripts/testid-lint.sh` → `testid-lint OK`, exit 0.
- **Capture delta:** `league-summary` — **and it needs a new state first.** `screens/manifest.json` lists `loading | error | populated | basis--personal | populated--single-format`; there is **no `drill-in` state**, and `mobile/.maestro/capture/league-summary.yaml` never taps a bar. So the screen this item is entirely about has never been captured, and the lab's "current" frames are token-exact reconstructions rather than traced screenshots. **Requested:** add a `drill-in` state to the capture yaml, then `mobile/scripts/screen-capture.sh --screen league-summary --state drill-in`. One capture also unblocks #300, which reuses this tile.
- **Smoke-suite impact:** of the shipped flows, `04-tabs-navigation.yaml` crosses the League tab. It taps tabs and asserts tab-root landmarks; it never focuses a team, so nothing it asserts moved. **Not re-run — no simulator this round** (see §5).
- **Backend: none.** No route, serializer, or query changed. Verified by diff: the change set is `PlayerCard.tsx`, `LeagueSummaryScreen.tsx`, one new test, one new flow.
- **Structural tests:** `mobile/tests/check-league-drill-in.js` — 30 assertions, all passing. **All 30 were falsified**: 30 deliberate sabotages applied to the real tree one at a time, each confirmed to flip its assertion to FAIL, then reverted (full matrix in `status.md` § Sabotage proof). That pass caught one genuine false-positive — the gate assertions originally walked six JSX parents and concatenated their conditions, so the "relocated tier badge is gated on `denseSingleLine`" check passed on a build where the badge was unconditional. Fixed in `ba30464`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. `tier` and the positional rank were already on `GET /api/league/power-rankings` and already rendered; #299 moves a badge within a tile. |
| `living-memory/LLD.md` | **proposed — orchestrator to apply** | A new mobile convention was introduced: shared presentational primitives take **opt-in props** for per-caller density rather than being branched wholesale. Verbatim text in `status.md` § Proposed shared-doc edits. |
| `docs/architecture.md` | n/a | No module wiring or data flow changed. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. The drill-in remains component state inside `LeagueRankings` — V4 ("make it a real push") was considered and rejected in the lab, because a push breaks the 2026-07-26 Analyzer treatment (chart stays visible above the roster) and #237's shared filter state. |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, or hex changed. Tier hexes and their labels are untouched — the badge is the same `TierChalkBadge`, relocated. |
| `docs/glossary.md` | n/a | No new domain term. |
| ADR or `DECISIONS.md` entry | **proposed — orchestrator to apply** | Two non-obvious choices: (1) opt-in prop over a shared-branch change, and 32pt over the literally-requested 30pt; (2) the #302 header swap is scoped to the tab-root registration only, because the legacy root-stack push already owns its `headerLeft`. Verbatim text in `status.md`. |
| `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | **proposed — orchestrator to apply** | New prop + new testID belong in the component/testID registries. Verbatim text in `status.md`. |

Per the batch's file-ownership rule, **no shared doc was edited by this agent** — three agents independently editing the same shared docs caused real merge conflicts in a prior batch. Every proposed edit is written out verbatim in `status.md` for the orchestrator to apply.

## 5. Ship gate declaration

- **Simulator-gate tier: 1** — "Mobile screen / navigation / state change". Both items qualify twice over: #299 changes a shared component's geometry, #302 changes a navigator header and registers a `BackHandler`.
  Tier 1 requires: full smoke suite (11 flows) + `flows/league/05-drill-in-back-affordance.yaml`, on sim, **plus** `screen-capture.sh --screen league-summary` for the changed visuals.
- **Deviation — WAIVED for this agent, NOT for the change: the sim run has not happened and is still owed.**
  The batch orchestrator instructed static-only verification (`Do NOT use the iOS simulator, and do not run Maestro`) because parallel build agents contending for one simulator and one harness Flask reseed each other's DBs and strand processes. Runtime verification is deferred to the batch QA round, which owns the Tier-1 obligation in full. **This is a scheduling deviation, not a tier reduction — nothing here may merge to `main` on static evidence alone.**
- **Static evidence produced instead** (actual command output in `status.md`):
  - `npx tsc --noEmit` → exit 0, no output
  - `mobile/scripts/testid-lint.sh` → `testid-lint OK`, exit 0
  - `node mobile/tests/check-league-drill-in.js` → 30/30 PASS, exit 0
  - falsification: 30/30 sabotages detected, working tree clean after each
- **Evidence still owed at ship:** TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` written by the QA round, plus the `league-summary` captures (including the missing `drill-in` state).
- **Untested at runtime, flagged for the QA round** — the four things static analysis genuinely cannot settle are listed as the QA checklist in `status.md`; the two worth naming here are **Android hardware back** (no Android device or emulator was involved at any point) and the **32pt row under OS text scaling**.
