# Feature Scope — P0-1: write `ranking_method` at the point of use

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
Every section is answered or explicitly WAIVED with a reason. Silence is not a waiver.
Companion plan: docs/plans/audit-p0-remediation/plan-p0-1.md
-->

**Date:** 2026-08-10
**Entry point:** 2026-08-09 mobile UX audit → finding P0-1 (build handoff
`docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-1)
**Builder:** planning agent, worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10` (off `origin/main @ ab9368f`)
**Operator sign-off on waivers:** **PENDING** — waivers in §1(b-note), §3 (push-primer assertion), §4 (four n/a rows), and open questions Q1-Q6 in the plan. Surface before build starts.

**Express lane:** **NOT declared.** No operator express declaration exists for
this item, and agents never self-select express. Full gates apply.

**Bright line:** this change does **not** touch schema, does **not** change any
API contract shape, and adds **no** feature flag or analytics event — but it
does change the value distribution of `users.ranking_method`, which is a
registered **experiment targeting attribute** (`backend/experiments.py:59`) and
an analytics segmentation dimension. Per `CLAUDE.md` that puts it on the
non-quick-fix side of the bright line. Full gates assumed; if the operator
declares express, this paragraph is the explicit callout and a confirming yes is
required before proceeding.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** — **none.** No `record_event` call is added by
  this change, so nothing needs registering against the default-deny taxonomy
  (`backend/analytics_taxonomy.py`).

- [x] **(b) Existing events cover it** — named, with the question each answers:

  | Event | Already fires from | Question it answers |
  |---|---|---|
  | `tier_save` (`props.via` ∈ `tiers`/`quickset`/`rookie_*`) | `server.py` `/api/tiers/save` | Did the user commit a tier board, and through which surface? |
  | `quickset_completed` (`position, players_placed, duration_ms, skipped`) | same route, `via == 'quickset'` | How many Quick Set positions were completed, and how long did each take? |
  | `trio_swipe` | `/api/rank3` | Did the user rank a trio? |
  | `ranking_reorder` | `/api/rankings/reorder` | Did the user manually reorder? |
  | `anchor_answered` (`props.via` ∈ `anchors`/`draft_room`) | `/api/anchor/save` | Did the user answer a pick anchor, and where? |
  | `ranking_complete_first_time` (`props.scoring_format`) | `/api/rankings/progress`, `was_first` branch | **The metric this fix moves.** Did the user reach the unlock, and when? Pre-fix, Quick Set users never emitted it. Post-fix they do — that step change is the measurable proof the fix landed. |
  | `ranking_method_changed` (`props.method`) | `/api/ranking-method` only | Did the user *explicitly choose* a method from the chooser or Settings? |

  **Deliberate omission, stated as a decision not an oversight:** the implicit
  point-of-use writes do **not** fire `ranking_method_changed`. That event's
  meaning is "the user chose a method"; firing it from every first tier save
  would silently redefine a shipped funnel event and corrupt its history. If an
  implicit-write signal is wanted, it needs a **new** event name registered
  server-side first (default-deny). Raised as plan open question **Q3** —
  operator/`an-data-architect` call, non-blocking.

  **Follow-through:** `docs/data-dictionary.md` is updated (§4) because the
  *stored* column's write contract changes, even though no event is added.

- [ ] **(c) WAIVED — no analytics needed because:** n/a — answered under (b).

**Analytics dimension change (must be read before merge).**
`users.ranking_method` is registered as an account-scope experiment targeting
attribute (`backend/experiments.py:59`, hydrated at `:258`). After this change
plus the backfill, the NULL bucket largely collapses into `'quickset'`. Any live
experiment targeting on `ranking_method` sees its eligible population move
mid-flight. **Blocking check before merge, not before build** — plan open
question **Q4**.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `users.ranking_method` already
  exists (`backend/database.py:181`; migration entry `:1861`). No column added,
  no type change, no index. `docs/data-dictionary.md:105` is nonetheless updated
  because its documented value set is *already stale* (omits `'anchor'` and
  `'quickset'`, both shipped) and because the write contract changes.
  **Migration entry reviewed:** the only migration-slot addition is a **data
  backfill** (`backfill_ranking_method_from_tiers`) invoked from `_migrate_db()`
  alongside the existing `_backfill_dual_format` / `_backfill_mfl_name_entities`
  — same slot, same idempotent-every-boot contract, no DDL.

- **New/changed feature flags:** **none.** Deliberate: the change removes a wrong
  answer rather than adding a surface, so a flag's OFF position would be "keep
  the bug". No entry needed in `config/features.json`,
  `backend/feature_flags.py` `FLAG_KEYS`, or `docs/config-reference.md`.
  *Graduation criterion:* n/a (no flag). Raised as plan open question **Q2** in
  case the operator wants a lever anyway.

- **New env vars / `model_config` keys:** **none.**
  **Ship-the-knob / deploy-free rollback lever:** the risky component is the
  one-time backfill, not the per-request writes. The honest levers, in order of
  preference:
  1. `git revert` the commit — the point-of-use writes stop immediately on the
     next Render deploy; already-written rows are correct data, not damage.
  2. A single SQL statement reverses the backfill if it ever needs undoing
     (`UPDATE users SET ranking_method = NULL WHERE ranking_method = 'quickset'
     AND …` scoped by the backfill's own logged cohort — **log the affected
     user_ids at backfill time so this is possible**). Recorded here as a build
     requirement, not an afterthought.
  3. If the operator answers **Q2** with "give me a knob", add a `model_config`
     key `migrations.ranking_method_backfill_enabled` rather than a client flag.

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/p0-1-quickset-unlock.yaml` — covers
  the acceptance criterion in one session on profile `quickset-done` /
  `flags: release`: sign in → League → progress ring asserts
  `".*4 of 4 positions ranked.*"` (accessibilityLabel, not the collapsed in-ring
  numeral — flow law 3) → Rank → Trios → `assertVisible: id:
  "rank.unlocked-banner"`. Both halves in one run, because the criterion is
  "4/4 **and** unlocked **together**". Cold start (`clearState: true`) is
  mandatory — the react-query cache is persisted (law 6). No injections.

- [x] **Extended flow:** `mobile/.maestro/capture/league@quickset-done.yaml` —
  the capture exists to photograph the 4/4-**locked** contradiction, which this
  change deletes. Rename the capture
  `progress-ring--4-4-locked` → `progress-ring--4-4-unlocked`, rewrite the
  header rationale, keep the ring assertion, and re-justify or drop the
  `league.works-now` step (it still passes but its stated reason becomes false).

- [ ] **WAIVED because:** n/a — flows are being written.

- **Waiver *within* the flow, stated explicitly:** the **iOS push-permission
  alert is not asserted**. It is a SpringBoard alert outside the app's
  hierarchy, not reliably assertable by Maestro, and `usePushNotifications`
  short-circuits when permission was already granted on the device. Covered
  three other ways: (i) `rank.unlocked-banner` ⇔ `progress.unlocked` ⇔
  `pushEnabled` (`RootNav.tsx:267`) as the on-device proxy, (ii) pytest **T-15**
  asserting the raw `unlocked` boolean, (iii) a manual step on a
  permission-reset simulator (`xcrun simctl privacy … reset all`) in the plan
  §8.4. **Operator sign-off requested on this waiver.**

- **`testID`s added/renamed:** one added — `rank.unlocked-banner` on the
  unlocked banner `View` (`mobile/src/screens/RankScreen.tsx:686`). A literal
  string, so `mobile/scripts/testid-lint.sh` covers it once registered in the
  `mobile/src/components/CLAUDE.md` registry. None renamed, none removed.

- **Capture delta:** `league@quickset-done` (renamed capture — must be re-run
  and re-indexed). Otherwise **none — no visual change**: the only mobile edit
  is a `testID` prop. Run `mobile/scripts/screen-freshness.sh` and re-capture
  only what it flags.

- **Smoke-suite impact:** crossing surfaces are `flows/smoke/04-tiers.yaml`
  (tier-save path), `06-trades-deck.yaml` (unlock-gated deck), and
  `09-league.yaml` (the ring). All three expected unchanged and green — their
  profiles do not complete a four-position Quick Set board, so `unlocked` does
  not move for them. **Verified, not assumed**, in the gate run.

- **Backend: pytest files added/updated:**
  - **Added:** `backend/tests/test_ranking_method_point_of_use.py` — 23 cases
    (T-1…T-23 in plan §8.1): per-route writes, rookie/`draft_room` exclusions,
    first-use-wins precedence, the single `'anchor'` upgrade, failed-save
    no-write, the end-to-end acceptance case (**T-15**), the partial-board
    negative (**T-16**), backfill cohort/idempotence/malformed-JSON, and the
    trio-user no-re-lock regression guard (**T-23**).
  - **Updated (fixtures, forced by the fix):**
    `backend/tests/fixtures/profiles/quickset-done.json` (→ `ranking_method:
    "quickset"`, `unlocked: true`, rewritten description) and
    `backend/tests/fixtures/seed_ui_test_db.py` `_validate_quickset` (**invert
    THE guard**: post-fix the incoherent profile is all-four-Quick-Set +
    `unlocked:false`, *regardless of* `ranking_method`, because the startup
    backfill tags NULL as `'quickset'`). Without both, the seeder starts
    refusing the only coherent post-fix configuration and a shipped capture
    asserts a state the server no longer produces.
  - **Must stay green:** `test_test_users.py`, `test_seed_ui_test_db.py`,
    `test_account_first.py`, `test_accounts.py`, `test_verified_sessions.py`,
    `test_verified_reads.py`, `test_trio_cross_position.py`,
    `test_rookie_scope.py`, `test_deck_first_session.py`.
  - Full suite: `python3 -m pytest backend/tests/ -q`; mobile:
    `cd mobile && npx tsc --noEmit`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Updated** | `/api/rankings/progress` row: `ranking_method` is now written at the point of use, so it is non-null for anyone who has taken a ranking action, and tier-based users no longer need the chooser to unlock. Annotate `/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save` with the new side effect. No route added/renamed/removed; no request or response key changes. |
| `living-memory/LLD.md` | **Updated** | New convention: implicit column writes from save handlers, and the `set_ranking_method_if_unset(…, allow_over=…)` conditional-write idiom (first-use wins; one `'anchor'` upgrade). |
| `docs/architecture.md` | **n/a because** | No module wiring or data-flow change — same routes, same services, same tables, same clients. |
| `living-memory/HLD.md` | **n/a because** | No new module, client, or major flow; a bug fix inside an existing endpoint's decision ladder. |
| `docs/cross-client-invariants.md` | **Updated** | §Ranking method strings (`:205`): the string set is unchanged, but the shared contract changes from "the chooser records a preference" to "written at the point of use, first-use wins, `'anchor'` upgradable by a completeness-marking tiers save". Both backend and web read this value. |
| `docs/glossary.md` | **n/a because** | No new domain term — `ranking_method`, `quickset`, `unlock` are all already defined. |
| ADR or `DECISIONS.md` entry | **Updated — `DECISIONS.md` D-011** | Non-obvious choices: (1) first-use-wins over last-use-wins, because overwriting can re-lock a user who qualified under the old method (the re-lock hazard already documented at `server.py:6177-6183`); (2) the single `'anchor'` → tiers/quickset upgrade exception and why it is strictly improving; (3) rookie-scope and `draft_room` exclusions; (4) backfilling to `'quickset'` rather than `'tiers'` and the labelling assumption that carries; (5) startup migration over lazy repair or one-shot script. Not ADR weight — no architectural shift. |
| **Additional rows beyond the template** | | |
| `docs/data-dictionary.md` | **Updated** | `:105` `users.ranking_method` — correct the stale value set (add `'anchor'`, `'quickset'`) and document the implicit-write + backfill contract. |
| `docs/runbook.md` | **Updated** | Operational note: the backfill runs at boot inside `_migrate_db`, what it touches, its expected one-time cohort size, how to confirm it ran, how to reverse it, and the seed-fixture interaction (it rewrites `quickset-done`'s seeded NULL on every UI-test boot). |
| `docs/config-reference.md` | **n/a because** | No env var, no `config/features.json` key, no `model_config` key added. |
| `screens/CLAUDE.md` (screen library index) | **Updated** | The `league@quickset-done` capture is renamed; its index entry follows. |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | pytest + `tsc` + testid-lint + the sim-gate run. |
| `living-memory/DEPENDENCIES.md` | **n/a because** | No dependency added, bumped, or removed. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if the build loses >30 min to something new. The known trap (startup backfill mutating seeded UI-test fixtures) is already documented in the runbook row above. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a because** | The audit is a dated artifact; outcomes are recorded in `CHANGELOG.md`, not by rewriting the audit. |

### 4.1 Execution record — W3-DOCS, commit 14 (2026-08-11)

> Row-by-row closure of the table above, per the feature-gate contract. **IDs are `hld.md` §7 / §10.4's**, which supersede any `D-011` / `G-013` written above — root `CLAUDE.md`'s next-ID columns were stale when these scope blocks were authored (they have since been changed to "max existing + 1 — grep first", so the trap is closed at the source).

| Row | Status | Where it landed |
|---|---|---|
| `docs/api-reference.md` | **updated** | § Progress / method — `/api/rankings/progress` behavioural note, `/api/ranking-method` cross-ref, and a new point-of-use block covering all four save routes, first-use-wins, the `'anchor'` upgrade and the three exclusions. Verified against `server.py:_note_ranking_method` + its four call sites. |
| `docs/data-dictionary.md` | **updated** | `users.ranking_method` — stale enum corrected (`'anchor'`, `'quickset'` added), write contract + backfill documented. `users.unlocked_formats` — the pre-seed and its fan-out-suppression purpose. |
| `docs/cross-client-invariants.md` | **updated** | § Ranking method strings — contract shift recorded; string set unchanged. |
| `docs/runbook.md` | **updated** | New § *Quick Set unlock backfill (P0-1, 2026-08-11)*: cohort, exclusion rationale, confirming `SELECT`, the boot log line that makes the undo expressible, the scoped reversal SQL, and the seed-fixture interaction. |
| `living-memory/LLD.md` | **updated** | § Code Conventions — the conditional-write idiom and implicit save-handler column writes. |
| `living-memory/DECISIONS.md` | **updated — D-026** (not D-011) | Full entry incl. the suppressed fan-out and the `'quickset'` labelling assumption. |
| `living-memory/GOTCHAS.md` | **updated — G-034** | The conditional fired: *a boot-time backfill silently rewrites your seeded test fixtures*. |
| `living-memory/CHANGELOG.md` | **updated** | Batch H2, P0-1 bullet. |
| `screens/CLAUDE.md` | **deferred** | See below. |
| `mobile/src/components/CLAUDE.md` | **n/a (revised)** | `rank.unlocked-banner` is a screen testID (`RankScreen.tsx`), not a component-map row; `testid-lint.sh` greps `mobile/src` and never opens this file, so nothing is load-bearing. |
| `docs/architecture.md` · `living-memory/HLD.md` · `docs/glossary.md` · `docs/config-reference.md` · `living-memory/DEPENDENCIES.md` | **n/a — confirmed** | As stated above; re-verified against the landed diff. |

**Not executed, and why:** `screens/CLAUDE.md` + `screens/manifest.json` re-capture rows are **deferred** — the renamed/new frames require a run of `mobile/scripts/screen-capture.sh` against the simulator, which `W3-QA` holds for the sim gate. Writing index entries for PNGs that do not exist would make the manifest lie. Tracked for the capture pass. `living-memory/TEST_LEDGER.md` is owned by `W3-QA` and is deliberately untouched here.

## 5. Ship gate declaration

- **Simulator-gate tier** (matrix in `docs/runbook.md` § Pre-ship simulator gate):
  the change spans **Tier 3** (backend route/schema behaviour consumed by
  mobile) and **Tier 2** (a mobile file is edited — a `testID` only, no UI
  change). **Declared tier: 2** — take the stricter of the two.

  Concretely: the new `flows/p0-1-quickset-unlock.yaml`, plus the affected smoke
  subset (`flows/smoke/04-tiers.yaml`, `06-trades-deck.yaml`, `09-league.yaml`),
  plus `mobile/scripts/screen-freshness.sh` with re-capture of whatever it
  flags, plus a forced re-run of the renamed
  `capture/league@quickset-done.yaml`.

  Pre-run hygiene per the flow-authoring laws: kill orphans on :5001 (law 19),
  and `shutdown` + `erase` + `boot` the canonical UDID if the sim has been
  through several cycles (law 18). Eyeball every screenshot — a green run is not
  a good capture (law 23).

- **Evidence:** `living-memory/TEST_LEDGER.md` entry (flows run, pass/fail, sim
  device, SHA) **and** `qa/sim-runs/last-sim-run.json` written after the run.
  Enforced locally by `githooks/pre-push` (`git config core.hooksPath githooks`).

- **Operator deviation from the matrix (if any) and why:** none proposed. If the
  operator wants Tier 3 instead (arguing the `testID` is not a mobile change),
  that is a legitimate call and gets recorded here — but the renamed capture
  still has to be re-run, so the saving is small.

- **Additional pre-merge gate, specific to this change:** confirm no live
  experiment targets `ranking_method` (§1, plan **Q4**). Not answerable from the
  code; blocking on merge, not on build.

---

## Waiver register (for operator sign-off)

| # | Waived | Reason | Blocking? |
|---|---|---|---|
| W-1 | iOS push-permission alert not asserted in Maestro | SpringBoard alert outside the app hierarchy; covered by the `rank.unlocked-banner` proxy, pytest T-15, and a manual permission-reset check | No — needs sign-off, not a decision |
| W-2 | No new analytics event for implicit method writes | `ranking_method_changed` means "user chose"; reusing it would corrupt a shipped funnel event. Action events already cover the behaviour | No (plan Q3) |
| W-3 | No feature flag / rollback knob | The OFF position of such a flag is the bug. Revert + a scoped SQL undo (with backfill cohort logged) is the lever | No (plan Q2) |
| W-4 | `docs/architecture.md`, `living-memory/HLD.md`, `docs/glossary.md`, `docs/config-reference.md`, `DEPENDENCIES.md` not updated | Reasons stated per row in §4 | No |
| W-5 | Backfill labels the whole cohort `'quickset'` though some boards were built on the Tiers screen | Unknowable retroactively; both unlock identically; the default route lands on Quick Set. Recorded in D-011 | No |

**Decisions still owed by the operator/orchestrator before merge:** plan open
questions **Q1** (approve the `'anchor'` upgrade — default: yes, proceed),
**Q4** (live-experiment check — blocking), **Q5** (suppress the first-unlock
push fan-out for the backfilled cohort — deliberate either way), **Q6** (preserve
the pre-fix 4/4-locked capture as historic evidence).
