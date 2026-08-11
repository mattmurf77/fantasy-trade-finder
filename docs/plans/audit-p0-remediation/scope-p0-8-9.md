# Feature Scope — P0-8 guided-tour sign-off gate + P0-9 first-session test prep

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
Every section is answered or explicitly WAIVED with a reason.
Companion plan: docs/plans/audit-p0-remediation/plan-p0-8-9.md
-->

**Date:** 2026-08-10
**Entry point:** UX/product audit `docs/business/product/2026-08-09-mobile-ux-audit/` — findings **P0-8** (Bug, effort S, build) and **P0-9** (Idea/A-B candidate, effort M, **test prep only**)
**Builder:** planning agent (worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`, from `origin/main @ ab9368f`); build to be executed by the P0-8/P0-9 build agent
**Operator sign-off on waivers:** **PENDING** — four waivers below (§1, §2, §3, §4) plus the open questions in plan §9. No express lane was declared, so full gates are assumed.

**Scope in one line.** P0-8: stop the guided tour announcing completion after a single first-like celebration, and delete the orphaned `err.burst` script entry. P0-9: validate the already-built 13-beat trades-first tour under a pinned flag set, fix only what is genuinely broken in it, and hand the operator a per-device test mechanism — **with every `onboarding.*` default left OFF**.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — named, with the question each answers:

| Event | Registered at | Question it answers for this work |
|---|---|---|
| `guide_step_shown` | `analytics_taxonomy.py:78`, props `{step, pose, screen}` (`:229`) | Which beats were actually delivered — the direct measurement of the P0-8 bug and of the P0-9 validation pass |
| `guide_step_advanced` | `:78`, props `{step, via}` (`:230`) | Whether a beat advanced by tap, real action, CTA or timeout — proves `s2.2` was acted on, not just displayed |
| `guide_step_skipped` | `:78`, props `{step}` (`:231`) | Per-beat skip rate; a dead-end beat shows up here |
| `guide_tour_dismissed` | `:79`, props `{at_step}` (`:232`) | Where users abandon the tour |
| `guide_tour_completed` | `:79`, props `{steps_seen}` (`:233`) | **The P0-8 acceptance signal.** Before the fix this fires with `steps_seen: 1`; after it, it must not fire at all on the release path |
| `quickset_prompt_shown` / `_accepted` / `_snoozed` | `:72-73` | The S3 pitch funnel |
| `quickset_completed` | `:111` | Per-position ranking completion |
| `deck_regenerated` | fired `TradesScreen.tsx:2562` | The S5 reveal, incl. `new_trades` — distinguishes `s5.1` from `s5.0` |
| `first_session_like`, `first_session_deck_completed` | `:65-66` | Activation, both arms |
| `deck_exhausted_viewed` | `:76` | The S7 trigger |
| `apple_prompt_shown/accepted/declined/dismissed` | `:70-71` | The S6.2 handoff |

  Experiment arm identification needs **no new event**: `experiments.stamp_for_event` (FR-32) already attaches `{key: variant}` to events inside a running experiment's scope.

- [x] **(a) One existing event is being REPAIRED, not added** — defect **D2** in the plan:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `celebration_shown` | `{beat}` — already allowlisted at `analytics_taxonomy.py:225` as `{beat_key, beat}` | first-like and first-quickset-save celebration beats | mobile (`TradesScreen.tsx:2547`, `:3135`, `:3153`) |

  The client currently emits **`celebration_fired`**, which is **not in the taxonomy**. Ingest is default-deny — *"unknown types are counted + dropped, never 4xx'd"* (`analytics_taxonomy.py:10`) — so all three call sites have been silently discarded. The fix is a **client-side rename to the already-registered name**; no taxonomy edit, no new key, no schema change, props already match. This is the second occurrence of this failure mode in this repo and is logged as `GOTCHAS.md` **G-013**.

  → follow-through: `docs/data-dictionary.md` **n/a** (no stored schema change — `user_events` shape is unchanged); taxonomy doc **n/a** (target name already registered).

- [ ] **(c) WAIVED** — not applicable; (a)+(b) answered.

**⚠ Waiver surfaced to the operator — analytics dependency, not a gap in this work.** Reading the P0-9 funnel needs `screen_viewed` **emission**, which the audit found absent (zero client instrumentation on navigation) even though the event is registered (`:40`, props `{screen, prev_screen, tab}`). Without it there is no time-to-first-value and no LeaguePicker→Trades drop-off — the two numbers the trades-first hypothesis turns on. **This is P0-7's scope, deferred by the operator.** Flagged here rather than absorbed, per the build handoff's instruction to raise it before investing in a test that cannot be read. See plan §3.4 and open question Q5.

**Coordination:** the P0-7 agent is speccing these events as an optional section. D2's rename must be done **once** — by this build, with P0-7 *not* adding a `celebration_fired` alias. Open question Q3.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No backend file is touched. `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** **none. No default is flipped — not one key.** This is load-bearing and is stated explicitly because P0-9 is *about* flags:
  - `config/features.json` is **not edited**. Every `onboarding.*` key keeps its current value (`v2: true`, `guided_avatar: true`, all ten siblings `false`), and `landing.try_before_sync` stays `false`.
  - No key is added to `backend/feature_flags.py` `FLAG_KEYS`.
  - `docs/config-reference.md` needs **no flag row change**.
  - The P0-8 fix must be correct under **both** the release defaults and the full onboarding-v2 set — the behavior matrix in plan §2.3 covers nine configuration × path combinations, and the gate reads persisted product state (`guideSeen['s2.2']`), never a flag, which is what makes it config-independent.
- **Config surfaces that DO change** (enumerated because they count as surfaces even though they are not flags):
  - `config/tester_allowlist.json` — possibly one added device pseudo-id, if the operator's has rotated. Git-deployed (Render does not apply `render.yaml` envVars to a dashboard-created service, observed 2026-07-19). Read by `experiments.load_tester_allowlist` and by the `/api/test-users` gate. Reversible by deleting the line.
  - **Prod experiment registry (runtime state, not a repo change)** — one new device-unit experiment `trades_first_operator_test` in the `onboarding` layer, created through the existing CRON-gated `POST /api/admin/experiments`. Its `treatment` variant carries `client_config.flags`, which `mobile/src/api/flags.ts` merges **over** the global map for the targeted unit only. Non-allowlisted users receive a byte-identical `/api/feature-flags` response throughout.
- **New env vars / `model_config` keys:** **none.**
- **Ship-the-knob — the deploy-free rollback lever:** `POST /api/admin/experiments/trades_first_operator_test/transition {"to":"stopped"}`. No build, no deploy, no App Store round trip. The P0-8 code fix itself has no kill switch and needs none: it removes a false statement from a flag-off path and is a strict subset of current behavior.
- **Graduation criterion** for the operator's test: `POST .../revise` with the `is_tester_allowlist` targeting dropped and weights rebalanced — the documented `onboarding_v2_rollout` path, requiring no client or server code change.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/guide-no-false-signoff@release.yaml` — the P0-8 regression, **pinned to release flags** (`# flags: release`, `# profile: fresh`). Covers: sign in → league → first like → assert `s6.1` still renders (`guide.avatar.*celebrate`) → assert the bubble **clears** and nothing replaces it (`extendedWaitUntil notVisible: {id: "guide.bubble"}`, 8 s). Under the bug, `s8.1` is `advance:'tap'` so its bubble persists and the wait times out. **The flow fails on the unfixed tree and passes on the fixed one** — a real regression test, not a smoke check. Id selectors only, no text matching, no bare sleeps.
- [x] **Extended flow:** `mobile/.maestro/capture/onboarding-tour@fresh.yaml` — **comment-only** edit at the S8.1 block, recording that s8.1 now additionally requires `guideSeen['s2.2']`, so the flow's own s2-2 step is a precondition rather than an ordering coincidence.
- [x] **Reused as-is (the flag-pinned onboarding-v2 flow already exists):** that same capture flow is tagged `# flags: onboarding-v2` and declares all thirteen beats. `mobile/scripts/screen-capture.sh:113` resolves the header to `backend/tests/fixtures/flags/onboarding-v2.json` and passes it to `sim-run.sh --flags`, which merges it over the profile map (`:56-68`) and round-trips the pinned map through `/api/feature-flags` as a handshake (`:118-119`). **Authoring a duplicate under `flows/` was considered and rejected** — it would clone ~300 lines carrying hard-won timing knowledge (three documented failed runs tuning the S2.wait window), and duplicates drift.
- [x] **Validation-only variant run** for defect **D3**: the same tour walked with **real** Quick Set chip selections so `fresh > 0` and `s5.1` renders. The existing flow saves empty tiers, which always lands on `s5.0` — which is why `s5-1.png` is absent from `screens/mobile/onboarding/` and why the tour's payoff beat has never been observed in this repo. Whether this becomes a permanent second cell or a hand-walked capture is the build agent's call once they know whether the player-id-templated chip ids can be selected deterministically. **If deterministic selection is impossible, walk it by hand and file the screenshot — do not fake it.**
- **`testID`s added/renamed:** **none.** Every selector used already exists: `guide.overlay`, `guide.tap-catcher`, `guide.avatar.<pose>`, `guide.bubble`, `guide.step-x`, `guide.cta.<action>`, `guide.dismiss-tour` (`AnalystGuide.tsx:91-189`); `trades.card-top`, `trades.like-btn`, `trades.pass-btn`, `leagues.row.*`, `signin.username-input`, `signin.continue-btn`. `mobile/scripts/testid-lint.sh` passes unchanged.
- **Capture delta:** **none for P0-8.** Deleting an unreferenced script entry and tightening a boolean on a flag-off path changes no pixels on any release-flag screen. The onboarding-v2 captures are re-run as **P0-9 validation evidence**, not as a screen-library refresh — with two currently-missing frames to obtain: `s5-1.png` (D3) and `s6-2.png`.
- **Smoke-suite impact:** the six flows in `mobile/.maestro/` (`01-launch` … `06-tiers-drag-no-crash`) plus the wider smoke set cross `TradesScreen`. None asserts on guide bubbles, so all are expected green; the Tier-1 gate runs them anyway.
- **Backend: pytest files added/updated — none.** No backend file is touched by either finding. `python3 -m pytest backend/tests/ -q` is run as a regression check only (concurrent sessions write to this repo).

**⚠ Waiver surfaced:** three checks cannot be made by the harness and are **manual on the simulator/device** — (1) a real finger swipe advancing `s2.2` (the deck's PanResponder rejects Maestro's synthetic directional swipe, so the harness always exercises the button path; `decide()` is shared by both, `TradesScreen.tsx:3008`); (2) the `s3.2` "Not now" and `s5.5` "Later" dismiss paths not trapping the user (script §1: never trap — the capture flow only walks accept on s3.2); (3) Settings → tour toggle off → on replaying from the first beat (full-replay semantics, `useGuide.ts:66-70`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. The operator's test uses the already-documented CRON-gated `POST /api/admin/experiments` + `/transition`. |
| `living-memory/LLD.md` | **n/a** | No schema, route, or invariant *convention* shifted. One boolean tightened inside an existing effect. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, colour, or threshold. Guide step ids are single-client (mobile) and are not read by web or extension. |
| `docs/glossary.md` | **n/a** | No new domain term — "guided tour", "beat", "Analyst" are all existing vocabulary. |
| `docs/config-reference.md` | **Conditional** | No flag row changes (§2). Update **only if** the operator's device pseudo-id is added to `config/tester_allowlist.json`. |
| `docs/data-dictionary.md` | **n/a** | No schema change. `user_events` and `experiments` shapes unchanged. |
| `docs/runbook.md` | **Updated** | New subsection: *"Operator-only onboarding test (`trades_first_operator_test`)"* — the create/transition recipe, the allowlist prerequisite, the two non-obvious flag values (`landing.try_before_sync` must be in the overlay; `onboarding.league_autoskip` must stay false or `s1.1` becomes unreachable), and the one-call rollback. This operational knowledge currently exists only inside a feedback status doc for a *different* experiment (`docs/feedback/items/279-aggregate-tier-labels/status.md`). |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | **Updated** | Record that `err.burst` is deleted from the implementation, and that S8.1 now requires the S2.2 beat. The script is the design source of truth; leaving it describing a step that no longer exists in code is precisely how audit finding **A-33** (config comments asserting the opposite of runtime behaviour) came about. |
| ADR / `living-memory/DECISIONS.md` | **Updated — `D-011`** | Non-obvious choice: gate the tour sign-off on a **named beat** (`guideSeen['s2.2']`) rather than a **step count**. The three reasons the count option fails (non-durable in-memory counter; `guideSeen` only records `once:true` steps so a real tour under-counts while an empty one over-counts; any `N` is a magic number that silently changes meaning when a beat is added) will otherwise be re-litigated. |
| `living-memory/GOTCHAS.md` | **Updated — `G-013`** | A client `track()` name absent from `backend/analytics_taxonomy.py` is counted and dropped in silence — `celebration_fired` has been dead at three call sites. Second occurrence in this repo. |
| `living-memory/CHANGELOG.md` | **Updated at ship** | Dated H2. |
| `living-memory/TEST_LEDGER.md` | **Updated at ship** | Tier-1 sim-gate run (§5). |
| `living-memory/HANDOFF.md` / `NEXT.md` | **At ship** | Overwrite HANDOFF if stopping mid-flight; NEXT as P0 blockers close. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a — do not edit** | The audit is a historical record. Its P0-8 counts are superseded by plan §1.3 (the audit graded "nine of fifteen unreachable"; the verified figure is **16 of 20**), and the correction lives in the plan, not in the audit. |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `docs/runbook.md` | **updated** | New § *Operator-only onboarding test (`trades_first_operator_test`)* carrying the load-bearing points — the `secrets.local.env` rule, the step-0 collision branch, the one-way `stopped` door and the save-the-row-first instruction, the two non-obvious overlay values, the step-4 pre-flight verification and what it proves, device-id rotation, `reseed-layers`' refusal-after-assignment, and the one-call rollback. The full seven-step sequence stays in `prd-p0-8-9.md` §5 and is linked, rather than duplicated where it would drift. |
| `docs/plans/onboarding-conversion/guided-avatar-script.md` | **not executed** | See below. |
| `docs/config-reference.md` | **n/a — condition not met** | Conditional on the operator's device id being added to `config/tester_allowlist.json`; the file is unchanged by this build. No flag row changes. |
| `living-memory/DECISIONS.md` | **updated — D-032 and D-033** | D-032 beat-identity gate with all three reasons a count fails; the candidate entry was allocated as **D-033** (request-first, consume-on-success). |
| `living-memory/GOTCHAS.md` | **updated — G-031** | Shared with P0-7; carries the 33-of-73 sweep and names `guide_tour_reenabled` as still broken. |
| `living-memory/NEXT.md` | **updated** | Item 0h — the remaining 29 names, starting with `guide_tour_reenabled` (it blocks a manual QA check). |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2 — no false sign-off, the recovered first-like celebration, `celebration_shown` landing, and the corrected 16-of-20 count. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a — not edited, by rule** | Dated artifact. Its 9-of-15 count is superseded by `plan-p0-8-9.md` §1.3 (16 of 20); the correction lives in the plan and in the CHANGELOG, not by rewriting the audit. |
| `docs/api-reference.md` · `living-memory/LLD.md` · `docs/architecture.md` · `living-memory/HLD.md` · `docs/cross-client-invariants.md` · `docs/glossary.md` · `docs/data-dictionary.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above. |

**Not executed, and why:** `docs/plans/onboarding-conversion/guided-avatar-script.md` — the `err.burst` deletion and the S8.1/S2.2 requirement were **not** written into the script doc. That file is the onboarding programme's design spec with its own owner and its own live rollout, and editing another workstream's spec from a remediation batch is exactly the kind of cross-ownership edit the wave partition exists to prevent. The implementation facts are recorded in D-032; the script-doc reconciliation belongs to whoever next touches that programme. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 1** — *"Mobile screen / navigation / state change"*. P0-8 changes guide state behaviour on `TradesScreen`, the app's most-trafficked screen. Required before merge to `main`:
  - full smoke suite (11 flows) on sim, plus
  - the feature's own flow `guide-no-false-signoff@release.yaml`, plus
  - `onboarding-tour@fresh.yaml` under the `onboarding-v2` fixture (proves A2: the V2 tour still signs off), plus
  - `mobile/scripts/screen-capture.sh` — **not required**; no release-path visual changes. Run `mobile/scripts/screen-freshness.sh` to confirm nothing else drifted.
- **Also required (non-simulator):** `python3 -m pytest backend/tests/ -q` green; `cd mobile && npx tsc --noEmit` clean; `mobile/scripts/testid-lint.sh` clean.
  **`mobile/node_modules` is a symlink in this worktree — never run `npm install`.**
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written after the run. Enforced locally by `githooks/pre-push` (install: `git config core.hooksPath githooks`).
- **Operator deviation from the matrix:** none requested. **No express lane was declared**, and agents never self-select express, so full gates apply.
- **Bright line (`CLAUDE.md` §Conventions):** P0-8 **does not cross it** — no schema, no API contract, no feature-flag surface, no new analytics event. P0-9 as scoped here **does not cross it either**, because it flips **no** flag defaults; the operator's test rides a per-unit experiment overlay that leaves the global flag map byte-identical. The one adjacent item is the D2 analytics rename, which restores an already-registered event rather than adding one. **If the operator later asks to flip `onboarding.trades_first` in `config/features.json`, that IS the bright line** and requires an explicit confirming yes.
