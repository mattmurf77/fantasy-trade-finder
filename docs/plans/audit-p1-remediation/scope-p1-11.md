# Feature Scope — P1-11: "Acquire" → "Trades" tab naming (audit A-20, naming half only)

<!--
Copied from docs/templates/feature-scope.md. Every section answered or explicitly WAIVED
with a reason. Silence is not a waiver.
-->

**Date:** 2026-08-11
**Entry point:** mobile UX audit finding **A-20 (partial — naming half only)**;
`docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md` row A-20.
The draft-tab seasonal-toggle half of A-20 is **excluded by operator decision** and is out
of scope for this block.
**Builder:** P1 remediation planning agent (plan only). Build agent TBD.
**Plan:** [plan-p1-11.md](plan-p1-11.md)
**Operator sign-off on waivers:** **REQUIRED — not yet obtained.**
Waivers requested: §1 (c), §3 (conditional), §5 (tier deviation, conditional).
Blocking checkpoints: CP-1, CP-2, CP-5, CP-7, CP-8 in the plan's *Operator checkpoints*.

**One-line summary:** change 5 user-visible strings (plus 1 in dead code) so the mobile
bottom tab reads **Trades** instead of **Acquire**, matching its own route name, the web
client, competitors, and App Store search. No behaviour changes.

---

## 1. Analytics scope

- [ ] **(a) New events specced** — none.
- [x] **(b) Existing events cover it.**

  | Event | What it answers | Why it is unaffected by this change |
  |---|---|---|
  | `tab_selected` (**arriving with P0-7**; `tab ∈ rank\|trades\|draft\|matches\|league`, plan-p0-7 `:164`) | Tab-level navigation share — the pre/post read for whether the label change moved traffic to the tab | Property value is the **route name** `trades`, not the label. Route name is unchanged, so the series is continuous across the rename — which is exactly what makes a pre/post comparison valid. |
  | `screen_viewed` (already live, `RootNav`) | Destination screens within the Trades stack | Derives from route names (`mobile/src/utils/testRouteEntry.ts:74-78`); unchanged. |

  **Measurement plan:** compare `tab_selected{tab='trades'}` share of all `tab_selected`,
  and downstream `screen_viewed` on `TradesHome`, for the 14 days before and after the
  release. This is a **directional pre/post read, not an experiment** — see §2 and CP-5.

- [ ] **(c) WAIVED — no NEW analytics needed because:** the change adds no new user action,
  no new surface, and no new decision point. It renames a label on an existing, already-
  instrumented navigation target. Adding an event would measure nothing that
  `tab_selected` does not already measure. **This is an explicit waiver on new
  instrumentation, not silence.**

  **Dependency:** the pre/post read is only possible once **P0-7 ships `tab_selected`**.
  P0 merges to `main` before this P1 build starts, so the dependency is satisfied by
  sequencing. If P0-7 slips, the change still ships — it just loses its measurement.

**Taxonomy allowlist:** **no edit.** No event name and no property *value* changes. The
server taxonomy is default-deny; nothing new is emitted, so nothing can be silently dropped
(the failure mode recorded in the growth doc does not apply here).

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `backend/database.py` is not touched. No
  migration. `docs/data-dictionary.md` unaffected.
- **New/changed feature flags:** **none.** No key added, removed, or default-flipped.
  `config/features.json` **values** stay byte-identical; `backend/feature_flags.py`
  `FLAG_KEYS` is unchanged; `docs/config-reference.md` is unaffected.

  **Deliberately un-flagged, with reasoning:** the change is 5 string literals with no
  behavioural branch. A flag would add a second code path, a config key, a `FLAG_KEYS`
  entry, a client fetch, and a graduation criterion — to guard one word. Rollback is a
  one-line revert plus a redeploy.

  **Ship-the-knob / rollback lever:** `git revert` of the single commit. There is no
  deploy-free lever, and none is warranted: the blast radius is a label, the failure mode
  is "users read a different word", and it is detectable by looking at the app.

  **On the audit's "A/B candidate" label:** `06-resolutions.md` §"Before you read the A/B
  labels" records 16 production users and a ~400-completions-per-arm floor below which an
  A/B is a directional read rather than a decision. A tab-label split cannot be powered.
  Recommendation is to ship the better-reasoned arm and read pre/post — **operator decision
  CP-5.**
- **New env vars / `model_config` keys:** **none.**

**Bright-line check (root CLAUDE.md §Conventions):** this change touches **no** schema,
**no** API contract, **no** feature-flag surface, and **no** analytics event. It is
therefore **not** on the bright line and *is* eligible for the express lane —
**but only if the operator declares it.** This agent does not self-select express; the full
gates below are planned by default.

## 3. Test scope (mobile test platform)

- [ ] **New flow:** none. A dedicated flow for a label would duplicate
  `04-tabs-navigation.yaml`, which already launches the app and waits on the tab bar.
- [x] **Extended flow:** `mobile/.maestro/04-tabs-navigation.yaml` — add one assertion after
  the existing `extendedWaitUntil: visible: id: "tab.trades"` (`:13-17`):

  ```yaml
  - assertVisible:
      id: "tab.trades"
      text: "Trades"
  ```

  **Rationale:** **zero** flows in the harness currently assert the tab label — verified
  exhaustively (`grep -rn "Acquire" mobile/.maestro/ | grep -v "#"` → 0 hits; every tab
  interaction across the 6 smoke flows, `flows/s1-spike-part-b-tabs.yaml`, and 51 capture
  flows uses `id: "tab.<name>"` selectors, per the 2026-07-12 QA F-2 migration). So nothing
  breaks — and nothing guards the label either. This assertion closes that gap.

- [x] **CONDITIONAL WAIVER — requested, operator sign-off needed (plan CP-6):** Maestro's
  combined `id` + `text` matcher must resolve to one element; `tabBarButtonTestID` lands on
  the pressable while the label is a descendant `Text`, so it may not match. If it does not
  resolve on a real sim run, the assertion is **dropped** and this section converts to a
  written waiver resting on the screen library (the tab bar appears in every tab-stack
  capture frame, so the PNG diff is the visual regression evidence).
  **A bare `text: "Trades"` is explicitly rejected as a fallback** — `04`'s frames contain
  other "Trades" copy ("Go to Trades"), so it would pass without asserting anything. A
  matcher that cannot fail is worse than no matcher.

- **Comment-only Maestro edits (12 capture flows, no assertion touched):**
  `capture/` → `trios@near-unlock.yaml:36`, `trades@single-format.yaml:43,49`,
  `trades@fresh.yaml:19`, `onboarding-tour@fresh.yaml:131`, `portfolio.yaml:21`,
  `portfolio@two-leagues.yaml:10`, `anchors.yaml:11`, `trios.yaml:11`, `trends.yaml:11`,
  `manual-ranks.yaml:11`, `quick-set.yaml:12`, `tiers.yaml:11`.
  `trios@near-unlock.yaml:36` is **required**, not optional — it reproduces verbatim the
  RankScreen banner string this change edits, and leaving it stale reintroduces the A-33
  failure mode (a comment asserting something the code no longer does) inside the QA layer.

- **`testID`s added/renamed:** **none.** `tab.trades` is unchanged. `testid-lint.sh` surface
  is unchanged and must still pass.

- **Capture delta:** `screen-freshness.sh` will flag **5 screens / 27 captures** —
  `matches` (9), `trios` (10), `quick-rank` (2), `draft-room` (4), `sheets-rank-menu` (2).

  **Declared gap, flagged rather than hidden:** that under-reports. Only 2 of 32 screens
  declare `mobile/src/navigation/TabNav.tsx` in their manifest `source` list, yet the bottom
  tab bar renders in every tab-stack frame — so `trades` (7), `league` (11), `portfolio` (2),
  `tiers` (7), `quick-set` (1) and others will silently retain stale "Acquire" PNGs.
  This is a **pre-existing manifest defect**, not caused by this change, but this change is
  the first to expose it.
  → Requested: re-capture **all tab-stack screens**, once, **after P0-2 also lands** (P0-2
  also invalidates `screens/mobile/trades/`), so `trades` is captured a single time.
  Command: `mobile/scripts/screen-capture.sh --screen <x>` (4–7 min each).
  **Operator decision CP-8** — this is the dominant cost of an otherwise five-word change.

- **Smoke-suite impact:** all 6 numbered smoke flows (`01`–`06`) plus
  `flows/s1-spike-part-b-tabs.yaml` cross the tab bar. **All use `tab.<name>` testID
  selectors, none asserts the label — so all stay green with no edit.** Verified by grep,
  not assumed.

- **Backend: pytest files added/updated — none, and why:** the only backend edits are two
  prose comments in `backend/feature_flags.py:532,536`. No Python behaviour changes, so no
  test can observe the diff. `python -m pytest backend/tests` is run for CI parity only.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (route added/renamed/removed/contract-changed) | **n/a** | No route touched. Zero backend route files in the change list. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **n/a** | No convention shifts. The existing convention — "a tab label is presentation-only over the route name" — is **reaffirmed**, not changed. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No wiring or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **n/a** | Verified 0 hits for `acquire` / `tabBar`. Tab labels are not a shared cross-client constant — mobile and web already differ (web nav reads "Find Trades", `web/index.html:246`). |
| `docs/glossary.md` (new domain term) | **YES** | `:120` — the **Acquire tab** entry *is* the canonical definition of this term. Retitle to **Trades tab**; preserve the #245/#246 history in the body; append the P1-11 reversal and rationale; keep the "route name stays `Trades`" invariant. **The load-bearing doc edit of this change.** |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **YES — `DECISIONS.md`, not an ADR** | Reversing a prior explicit operator decision (#245, 2026-08-05) is non-obvious and must be on the record: what changed, and that #246 removed the two-channel hub which was #245's stated rationale. Not an ADR — it is a copy decision, not an architectural one. Use the next free ID (`D-011` per root CLAUDE.md; **verify at build time** in case a concurrent session took it). |

**Additional docs required by root CLAUDE.md / `docs/CLAUDE.md`, beyond the template rows:**

| Doc | Updated? | Reason |
|---|---|---|
| `mobile/src/navigation/CLAUDE.md` | **YES** | `:6` tab list `Rank · Acquire · Draft · …`; `:8` the `**Acquire** (route Trades)` stack row. This file is the tab-label registry. |
| `mobile/src/screens/CLAUDE.md` | **YES** | `:19` — `TradesScreen` row, "also the Acquire tab's landing". |
| `mobile/src/components/CLAUDE.md` | **YES** | `:51` — `TradeFinderModeBar` row, "Acquire tab's mode chip strip". No testID registry change (no id added or renamed). |
| `living-memory/CHANGELOG.md` | **YES at ship** | Dated H2 at the top on merge. |
| `living-memory/TEST_LEDGER.md` | **YES at ship** | Sim-gate evidence, per §5. |
| `docs/config-reference.md` | **n/a** | No env var, flag key, or `model_config` key. (CP-4 concerns a JSON *comment* string only; no key or value moves.) |
| `docs/data-dictionary.md` | **n/a** | No schema change. |
| `docs/design/design-system.md` | **n/a** | No token, color, radius, or type change. |
| `docs/design/components.md` | **n/a** | `:69` specs the **direction toggle** (`Trade away` / `Acquire` chips) — Group 2, out of scope and unchanged. Verified the file carries no tab-bar label spec. |
| `docs/runbook.md` | **n/a** | No new operational failure mode or lever. |
| `docs/feedback/items/245-acquire-tab/status.md` | **NO — deliberately** | It is the historical record of what shipped on 2026-08-05. Amending it would falsify the archive. The reversal lives in `DECISIONS.md` + `docs/glossary.md`, which are the live surfaces. |

## 5. Ship gate declaration

- **Simulator-gate tier** (matrix in `docs/runbook.md` § Pre-ship simulator gate):

  **Planned: Tier 1** — *"Mobile screen / navigation / state change"*. `mobile/src/navigation/TabNav.tsx`
  is edited, so Tier 1 applies on the letter of the matrix: full smoke suite (11 flows) +
  the feature's flow + `screen-capture.sh --screen <touched>` for every screen whose visuals
  changed.

- **Operator deviation requested (plan CP-7):** **Tier 2** is arguably correct. No navigation
  *behaviour* changes — no route, no listener, no navigator structure, no state. Two string
  literals move inside an `options` block. Tier 2 = feature flow + affected smoke subset +
  `screen-freshness.sh`, re-capturing only what it flags.

  → **Recommendation: Tier 2**, recorded here as a deviation per the matrix's own
  "deviations are decisions, recorded in the feature's scope block" rule.
  **Absent an operator call, the build executes Tier 1.**
  Caveat: Tier 2's `screen-freshness.sh` is known to under-report here (§3 capture delta), so
  a Tier 2 election **must** still be paired with the CP-8 manual capture list — otherwise the
  screen library keeps a label the app no longer has.

- **Evidence:**
  1. `living-memory/TEST_LEDGER.md` — flows run, pass/fail, sim device, SHA.
  2. `qa/sim-runs/last-sim-run.json` — required by `githooks/pre-push`, which blocks any
     push to `main` touching `mobile/src` without a passing run on an ancestor commit.
     (Install once per clone: `git config core.hooksPath githooks`.)

- **Express lane:** **not declared.** Per root CLAUDE.md, agents never self-select express.
  If the operator declares it, the change qualifies (no schema, API, flag, or analytics
  surface — §2 bright-line check), and the ceremony reduces to `FTF_SKIP_SIM_GATE=1` plus a
  one-line ledger note: `express: Acquire→Trades tab label — gates skipped by operator`.

- **Merge sequencing (hard dependency):** the P0 build
  (`p0-remediation-2026-08-10`) merges to `main` **before** this P1 build starts. Rebase onto
  post-P0 `main` before the first edit. Two real line-level collisions must be re-resolved by
  content, not by line number: **P0-1** edit #14 (`RankScreen.tsx:686`, same JSX element as
  this change's `:693-694`) and **P0-7** edit #7 (`TabNav.tsx`, same `Tab.Screen` element as
  this change's `:655-656`). Full matrix in the plan's *Risks and cross-item collisions*.
