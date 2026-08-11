# Feature Scope — P0-6: platform-generic send fallback ("copy this trade")

<!-- Copied from docs/templates/feature-scope.md. Every section answered or
     explicitly WAIVED with a reason. No express lane was declared for this
     work, so the full gates apply. -->

**Date:** 2026-08-10
**Entry point:** UX audit finding P0-6 — `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md`
**Builder:** planning agent (plan-only), worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10` (worktree of `origin/main @ ab9368f`)
**Plan:** [`plan-p0-6.md`](plan-p0-6.md)
**Operator sign-off on waivers:** **pending** — three items need a yes/no before build (see § Waivers requiring sign-off)

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics fired by this change, because:** the analytics taxonomy is
  **default-deny** (`backend/analytics_taxonomy.py` → `ALLOWED_CLIENT_EVENTS`, enforced at
  `backend/analytics_ingest.py:376`), so any new client `track()` call requires a server-side
  taxonomy registration first. That is an **analytics-event surface change**, which `CLAUDE.md`'s
  bright line says is not a quick fix — inside a finding typed *Bug, effort S*. It is also
  **already owned by another agent**: P0-7 is planning client instrumentation on this exact
  component (`SendInSleeperButton.tsx`). Firing events from P0-6 would duplicate or conflict with
  that work.

- **(a) Specced and handed to P0-7, not built here.** These are the two events this surface wants;
  P0-7 registers and emits them:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `send_unavailable_shown` | `platform` (`espn`\|`mfl`\|`fleaflicker`), `league_id`, `surface` (`match`\|`deck`\|`awaiting`\|`calculator`) | the non-Sleeper branch of `SendInSleeperButton` mounts | mobile |
  | `trade_copied` | `platform`, `league_id`, `surface`, `give_count`, `receive_count` | `Copy trade` tapped, after a successful clipboard write | mobile |

  → follow-through owned by P0-7: `backend/analytics_taxonomy.py` registration, then
  `docs/data-dictionary.md` if stored.

- **(b) Existing events that partially cover it:** none. There is **zero client instrumentation on
  Send-in-Sleeper today** — that absence is P0-7's finding, and it is why P0-6 cannot measure its own
  effect. Stated so the gap is a known, owned one rather than an omission.

- **Cross-agent warning (repeated from `plan-p0-6.md` §9):** P0-6 changes what "the send button was
  shown" *means*. After this fix a non-Sleeper mount renders an affordance that is **not** a send
  button. An unconditional mount-time impression event would conflate copy-affordance impressions
  with send impressions and corrupt the send-funnel denominator — the same defect class as the
  NULL-`platform` incident already on the record in `CLAUDE.md`.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No migration. `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** **none proposed.** The change lives entirely inside the existing
  `trade.send_in_sleeper` flag (`config/features.json:45`, currently `true`), whose semantics are
  unchanged: off → the component returns `null` on every platform, i.e. exactly today's ESPN
  behaviour everywhere. **That existing flag is the deploy-free rollback lever** ("ship the knob" —
  already shipped).
  **Alternative, if the operator wants flag-per-finding on this branch** (see § Waivers, W1): one
  boolean `trade.copy_fallback` guarding only the non-Sleeper branch — ~4 lines in the component
  plus `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, and
  `docs/config-reference.md`. Default state would be **on** (the branch it guards replaces nothing
  with something); graduation criterion: the first sim run + one TestFlight session confirms the
  copied string pastes correctly.
- **New env vars / `model_config` keys:** **none.** `docs/config-reference.md` n/a.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/p0-6-espn-copy-trade.yaml` — profile `espn`, flags
  `release`. Covers **both halves of the acceptance criterion** on a matched ESPN user: the stated
  reason (`assertVisible` on `send-in-sleeper.unavailable` and on the "Sending is Sleeper-only" copy)
  and the useful action (`tapOn` `send-in-sleeper.copy` → `assertVisible ".*Copied.*"`). Uses the
  sign-in-through-the-league-picker preamble copied verbatim from `capture/matches@espn.yaml` —
  load-bearing, because the platform gate **fails open** on a league id missing from the session
  cache, so any entry that skips the picker would test the wrong branch.

- [x] **Extended flow:** `mobile/.maestro/capture/matches@espn.yaml` — add
  `assertVisible: id: "send-in-sleeper.copy"`, rewrite the present-tense bug commentary, and
  re-capture both shutters (`populated--espn-mutual`, `populated--espn-awaiting`).
  **Why this is not optional:** the flow's existing `assertNotVisible ".*Send in Sleeper.*"` stays
  **green after the fix** (the new label is "Copy trade"), so without the added assertion the flow
  would silently keep passing while documenting behaviour that no longer exists — and a regression
  of the fix would go undetected.
  Also update the bug-as-current-behaviour paragraph in
  `backend/tests/fixtures/profiles/espn.json` (`description`, line 4) in the same commit.

- [x] **WAIVED, partially — MFL / Fleaflicker have no simulator coverage, because:**
  `backend/tests/fixtures/profiles/` contains `espn.json` and no MFL or Fleaflicker profile, and no
  other profile seeds a non-Sleeper league. Covering them on-sim means authoring a new profile
  (fixture seed + league snapshot; raw material exists at
  `backend/tests/fixtures/mfl_league_snapshot_2026-07-17.json` and
  `fleaflicker_league_snapshot_2026-07-17.json`) — real scope inside a *Bug, effort S* wave.
  **Compensating coverage:** after the design in `plan-p0-6.md` §2.2, *all* platform-specific
  behaviour lives in two pure exports (`resolveSendPlatform`, `NO_SEND_REASON`) in
  `mobile/src/utils/tradeText.ts`, and `mobile/tests/check-trade-text.js` pins both for all four
  platform values. The MFL profile is filed as a `NEXT.md` item.
  **This waiver needs operator sign-off (W2).**

- **`testID`s added:** `send-in-sleeper.unavailable` (wrapper `View`), `send-in-sleeper.copy`
  (ghost Button). Both must pass `mobile/scripts/testid-lint.sh`. No renames, no removals.

- **Capture delta:** `matches` under the **`espn` profile only** — `matches__populated--espn-mutual`
  and `matches__populated--espn-awaiting`. Run
  `mobile/scripts/screen-capture.sh --screen matches` (see `docs/runbook.md` § Screen library).
  The pre-fix PNGs are the audit's before-evidence and stay in git history; per `screens/CLAUDE.md`
  a mockup's "current" pane is not redrawn.
  **Sleeper-profile captures must be pixel-identical** — that is the primary regression assertion.
  Run `mobile/scripts/screen-freshness.sh` and expect it to flag ESPN screens only.
  No `trades@espn` capture exists in the library, so the deck's non-Sleeper state is not currently
  photographed; filed as a capture request rather than built here.

- **Smoke-suite impact:** none of the 11 smoke flows cross a non-Sleeper send surface.
  `flows/smoke/08-matches.yaml` runs profile `standard` (Sleeper) and asserts only that the empty
  state does not render; `05-trades-render.yaml` and `06-trades-deck.yaml` are likewise Sleeper
  profiles. All expected to stay green untouched — and that absence of coverage is precisely the
  hole the new flow fills.

- **Backend: pytest files added/updated — none.** **No backend file is changed by this plan**
  (`plan-p0-6.md` §4). `python3 -m pytest backend/tests/ -q` is expected untouched-green; a failure
  there indicates a concurrent session's commit, not this work.

- **New mobile unit test:** `mobile/tests/check-trade-text.js` + `npm run test:trade-text`, following
  the `check-session-rerank.js` transpile idiom. Pins `formatTradeForClipboard` (including the
  ids-when-names-absent fallback, so the copy action can never produce an empty clipboard),
  `resolveSendPlatform` (**including the fail-open invariant: a league id absent from the session
  cache resolves to `'sleeper'`** — the most load-bearing property in the design), and
  `NO_SEND_REASON` for all three non-Sleeper platforms.

- **Manual step the harness cannot perform:** Maestro cannot read the iOS pasteboard. After the flow's
  copy tap, paste into Notes on the simulator and confirm the string matches the spec
  (`plan-p0-6.md` §2.3). Record verbatim in `TEST_LEDGER.md` — this is the only end-to-end proof the
  clipboard write lands.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `POST /api/sleeper/propose`, `POST /api/trades/matches/<id>/disposition` and `/dismiss` are all untouched — the change is client-only |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shifted. The platform-generic gate is a component-local rule |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change; two new leaf utilities under `mobile/src/utils/` |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, or color. `NO_SEND_REASON` is mobile-only copy; web has no send-in-Sleeper surface |
| `docs/glossary.md` | **n/a** | No new domain term ("platform-linked league" is already in use) |
| `docs/design/components.md` | **n/a** | Reuses the specced `ghost` Button variant, `type.bodySm` and `chalk.dim`; no new component spec, no new token |
| `mobile/src/components/CLAUDE.md` | **updated** | `SendInSleeperButton` registry row — "self-gates to Sleeper leagues" becomes misleading after the change |
| `mobile/src/api/CLAUDE.md` | **check at build** | Only if it names `setMatchDisposition`; verify at edit time |
| ADR or `DECISIONS.md` (`D-011`) | **updated** | Two non-obvious choices: **(a)** React Native core `Clipboard` over `expo-clipboard` — native module, no `npm install`/prebuild available in this build — behind a one-function `utils/clipboard.ts` migration seam; **(b)** delete the unused mobile `setMatchDisposition` wrapper while **keeping** the route (`web/js/app.js:4342` is a live caller and `record_match_disposition` carries ELO signal) and deferring accept/decline UX to its own PRD |
| `living-memory/GOTCHAS.md` (`G-013`) | **updated** | MFL/Fleaflicker league ids are **numeric**, so the `league_id.isdigit()` check at `backend/server.py:12336` does not exclude them from the Sleeper propose path — the same bug class as `#200` and `#220` |
| `living-memory/NEXT.md` | **updated** | Three items: accept/decline match UX (deferred; evaluation in `plan-p0-6.md` §2.5); MFL/Fleaflicker harness profile (this doc §3 waiver W2); `is_linked_platform_league` guard on `/api/sleeper/propose` (W3) |
| `living-memory/CHANGELOG.md` | **updated at ship** | Dated H2. Must name the MFL/Fleaflicker behaviour change explicitly — this is not a purely additive change (see W3 rationale) |
| `living-memory/TEST_LEDGER.md` | **updated at ship** | Sim-run tier, result, and the manual paste verification |
| `living-memory/DEPENDENCIES.md` | **n/a** | **No dependency added, bumped, or removed** — deliberately (see D-011a) |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `mobile/src/components/CLAUDE.md` | **updated** | The misleading "self-gates to Sleeper leagues" replaced with the platform-generic gate, the fail-open note, the required `surface` prop, and both new testIDs (verified at `SendInSleeperButton.tsx:393/398`). |
| `mobile/src/api/CLAUDE.md` | **n/a (verified)** | The file contains zero occurrences of `setMatchDisposition`; its `trades.ts` row is "Trade card fetch + decisions". Recorded as verified, closing the HLD's "check at build" row. |
| `living-memory/DECISIONS.md` | **updated — D-029** | Both halves: RN-core `Clipboard` (with the `npm install`-unavailable constraint and the one-file migration seam) and deleting the wrapper while keeping the route. |
| `living-memory/GOTCHAS.md` | **updated — G-028** | Numeric MFL/Fleaflicker ids vs `isdigit()`, cross-referenced to G-014 / #200 / #220 as the **third** instance of the class. |
| `living-memory/NEXT.md` | **updated ×3** | Items 0e (accept/decline, with the evaluation), 0f (`is_linked_platform_league` guard), 0j (MFL/Fleaflicker harness profile). |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2 — the MFL/Fleaflicker behaviour change is named explicitly in the lede, not buried. |
| `docs/cross-client-invariants.md` | **updated (revised from n/a)** | The `SendSurface` enum **did** become a cross-client constant once P0-7 put `surface` on three event names — recorded under § Client analytics event contract with `awaiting` ≠ `suggested` called out. `NO_SEND_REASON` copy remains mobile-only and is not recorded. |
| `screens/CLAUDE.md` | **deferred** | See below. |
| `living-memory/DEPENDENCIES.md` · `docs/api-reference.md` · `docs/data-dictionary.md` · `docs/config-reference.md` · `docs/design/components.md` · `docs/glossary.md` · `docs/architecture.md` · `living-memory/HLD.md` · `living-memory/LLD.md` · `docs/runbook.md` | **n/a — confirmed** | As stated above. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier** (per the matrix in `docs/runbook.md` § Pre-ship simulator gate):
  **Tier 1 — mobile screen / navigation / state change.** Required: full smoke suite (11 flows)
  + the feature's own flow (`p0-6-espn-copy-trade.yaml`) + the updated `capture/matches@espn.yaml`
  + `mobile/scripts/screen-capture.sh --screen matches` for the ESPN-profile frames whose visuals
  changed.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after
  the run. Enforced locally by `githooks/pre-push` (`git config core.hooksPath githooks`).
- **Static gates before the sim run:** `cd mobile && npx tsc --noEmit` clean;
  `python3 -m pytest backend/tests/ -q` green; `bash mobile/scripts/testid-lint.sh` exit 0;
  `node mobile/tests/check-trade-text.js` green.
- **Operator deviation from the matrix (if any):** none requested. **Note on batching:** if P0-6 ships
  inside one combined P0 wave, a single tier-1 run covering all seven findings satisfies the gate —
  that is a sequencing decision for the operator, and if taken it is recorded here and in
  `TEST_LEDGER.md` as the deviation.

---

## Waivers requiring operator sign-off

Three, all surfaced before build per `CLAUDE.md` ("waivers are surfaced to the operator before
build"). None is agent-selected.

| # | Waiver / decision | Default if unanswered |
|---|---|---|
| **W1** | **No new feature flag.** The change rides `trade.send_in_sleeper`. If this branch's convention is flag-per-finding, the alternative is `trade.copy_fallback` (§2). A new flag is itself a feature-flag-surface change, which `CLAUDE.md`'s bright line excludes from "quick fix" | **Proceed with no new flag** |
| **W2** | **MFL / Fleaflicker get unit coverage, not simulator coverage** (§3). No harness profile exists for either; building one is out of scope for a *Bug, effort S* wave. Compensated by pure-module tests over all four platform values | **Proceed; file the profile in `NEXT.md`** |
| **W3** | **`/api/sleeper/propose` keeps its missing platform guard.** Verification found no `is_linked_platform_league` check at `backend/server.py:12336`, so a hand-crafted request with an MFL league id still reaches Sleeper's roster space. Fixing it is a backend/API-contract change — the bright line. P0-6 fixes the client, which is the whole of the acceptance criterion | **Proceed client-only; file the guard in `NEXT.md`** |

**Related decision made in the plan, not a waiver:** `setMatchDisposition` — the mobile client
wrapper (`mobile/src/api/trades.ts:504-516`, zero call sites) is **deleted**; the route,
`record_match_disposition`, the live web caller, and the read-only `my_disposition` /
`their_disposition` fields are **kept**; accept/decline UX is **deferred** to its own PRD. Full
three-option evaluation in `plan-p0-6.md` §2.5. This is decided, not open — but if the operator
prefers to build the accept/decline UX instead, say so before build starts, because it changes the
finding's type from *Bug, effort S* to a feature with its own scope block.
