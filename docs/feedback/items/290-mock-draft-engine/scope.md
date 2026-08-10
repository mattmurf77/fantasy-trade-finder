# Feature Scope — G2: mock draft engine, lifecycle, interactivity (#290 / #291 / #292 / D-16)

**Date:** 2026-08-10
**Entry point:** feedback #290, #291, #292 + operator scope addition **D-16**
**Builder:** G2 author agent (Phase 1) → G2 build agent (Phase 2)
**Operator sign-off on waivers:** **REQUIRED — three waivers below (§1, §3, §6) plus one flag recommendation (§2) and one file-ownership gap (§7).**

> Copied from [`docs/templates/feature-scope.md`](../../../templates/feature-scope.md).
> Companion docs: [`prd.md`](./prd.md) · [`hld-delta.md`](./hld-delta.md) ·
> [`lld-delta.md`](./lld-delta.md) · [`plan.md`](./plan.md) ·
> [`reconciliation-log.md`](./reconciliation-log.md).
>
> **Rigor:** no express declaration was made, so **full gates apply.** This change
> touches feature-flag surfaces and a live production model, which is on the
> bright line in `CLAUDE.md` §Conventions — express would need an explicit,
> confirmed operator yes.

---

## Table of Contents

- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Test scope (mobile test platform)](#3-test-scope-mobile-test-platform)
- [4. Docs scope (MANDATORY — HLD / LLD / API)](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [6. Out of scope and flagged](#6-out-of-scope-and-flagged)
- [7. Open items for the operator](#7-open-items-for-the-operator)

---

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED — no analytics needed because:**

**Waiver, with reason — the operator must accept or reject it.**

The mock surface deliberately ships **zero** analytics today, and the reason is
written into the code. `DraftRoomScreen.tsx:604-609`:

> *"No `track()` here on purpose. `backend/analytics_taxonomy.py` is DEFAULT-DENY
> and carries no mock events, and this wave owns `mobile/` only — firing
> `draft_room_mode_switched` would be dropped server-side while reading like live
> instrumentation. Register the events, then add the calls."*

Verified: `ALLOWED_CLIENT_EVENTS` (`backend/analytics_taxonomy.py:38-104`) holds
four `draft_room_*` events (`draft_room_row_menu_opened`,
`draft_room_action_taken`, `draft_room_coverage_nudge_shown`,
`draft_room_rank_rookies_tapped`, with props at `:241-246`) and **no** `mock_*`
event of any kind. Unregistered events are counted and dropped server-side, never
4xx'd — so adding a `track()` call without a four-touch taxonomy registration
would produce instrumentation that looks live and records nothing. That is the
NULL-`platform` failure mode the feature-gates convention exists to prevent.

**Registering mock events is a real and probably worthwhile piece of work** — a
mock funnel (`mock_started` / `mock_pick_made` / `mock_completed` /
`mock_abandoned` / `mock_create_failed`) would answer "does anyone finish a mock,
and where do they drop?", which is exactly the question #292 raises. But it
requires touching `backend/analytics_taxonomy.py`, which is **outside G2's
ownership**, and it would widen a bug-fix batch into an instrumentation project.

**Recommendation: accept the waiver, and spin out "register the mock event
family" as its own backlog item.** If the operator wants it in this batch
instead, say so and it becomes a fifth workstream with its own owner.

---

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No `mock_drafts` change, no
  migration, no `backend/database.py` edit at all (the abandon route already
  accepts a completed row — [`prd.md` §2.3](./prd.md#23-292--three-dead-ends-all-client-side-d-8)).
  `docs/data-dictionary.md`: **n/a**.
- **New/changed feature flags:** **none proposed.** Recommendation below.
- **New env vars / `model_config` keys:** **none.** Four new module constants
  (`MOCK_RUN_GAP_MULTIPLE`, `MOCK_RUN_MEDIAN_WINDOW`,
  `MOCK_RUN_CROSS_ALLOWANCE_LATE`, `MOCK_IDIOSYNCRASY_FLOOR`) are deliberately
  **not** `model_config` rows, for the same reason the W2e policy tables are not
  (`mock_draft_service.py:104-113`): they are support bounds on the model, and a
  bound an operator can retune from the DB silently invalidates the calibration
  verdict the gate records. Documented in `docs/config-reference.md` beside the
  W2e policy section.

### 2.1 Does the engine change need its own kill switch?

**Recommendation: NO. Ship on `draft.mock`.** Reasoning, then the operator's call.

*The case for a switch:* `draft.mock` is already `true`
(`config/features.json:157`) and `CPU_MODEL_VALIDATED = True`
(`mock_draft_service.py:294`), so the surface is **lit in production** and this
alters live behaviour behind an already-on flag. There is no dark landing.

*Why a switch is still the wrong call here:*
1. **The revert lever already exists and is cheaper.** A new flag would gate a
   `min()` and a scalar. Rolling back is a two-constant edit
   (`MOCK_RUN_GAP_MULTIPLE = 0` ⇒ every gap is a boundary — wrong; the honest
   neutral is to remove the `min()`), which is a one-hunk revert of a
   single-purpose commit. A flag buys deploy-free rollback of *behaviour the flag
   would have to thread through two functions and the calibration harness*.
2. **A flag inside the calibration harness is a correctness hazard.** `cap` is
   composed identically in `advance_cpu` and `simulate_reaches`
   ([`lld-delta.md` §3](./lld-delta.md#3-reach-cap-composition)). A flag read in
   one and not the other would make the harness measure a model the product does
   not run — which is precisely the divergence W2e's comment says must never
   happen. A flag read in *both* means `is_enabled()` inside a pure,
   injection-only module that currently imports nothing but stdlib and two
   sibling services (`test_w2_13`, `:764`).
3. **`draft.mock` is already the right-sized blast radius.** If the new bot
   behaviour is bad, the honest lever is "turn the mock off", which exists.
4. **Precedent.** The W2e round-tiered policy — a strictly larger behaviour change
   to the same model — shipped with no flag of its own.

*What the operator gets instead of a flag:* the numbers in
[`prd.md` §4](./prd.md#4-the-tate-case) before merge, a Tier-1 sim run, and a
one-hunk revert.

**If the operator disagrees**, the shape is `draft.mock_runs` (default **true**,
because a default-false flag would ship the reported bug unfixed), read **once**
in `server.py` and passed into `advance_cpu` as a parameter — never read inside
`mock_draft_service`, so the harness can set it explicitly. Say so and it will be
specced.

### 2.2 Stale flag/config documentation — a real defect to correct (plan R10, extended)

**Three files, not two, all wrong since `6caca35` (2026-08-08).** Every one is
**orchestrator-owned**; proposed text below, to be applied at integration.

**(a) `config/features.json:155`** — the `_comment_draft_extensions` string. Two
false claims. Replace:

> `draft.mock gates the four /api/mock-draft routes and the mobile mock surface; effective gating is draft.room AND draft.mock, and it is independent of draft.live_poll (the mock never polls), draft.mfl and picks.slot_values.` ~~`It stays OFF beyond the usual lands-dark convention: W2's calibration gate FAILED (docs/plans/draft-extensions/mock-calibration-2026-08.md), so the plan's W2 abort criterion cut the CPU-bot mock. With the flag ON the create route answers the typed-empty {empty:true, reason:'cpu_model_unvalidated'} instead of serving bots whose noise model failed hold-out validation.`~~

with:

> `draft.mock gates the four /api/mock-draft routes and the mobile mock surface; effective gating is draft.room AND draft.mock, and it is independent of draft.live_poll (the mock never polls), draft.mfl and picks.slot_values. IT IS ON. It shipped ON on 2026-08-08 (6caca35) by explicit operator override, NOT by the calibration gate passing: mock_draft_service.CPU_MODEL_VALIDATED was flipped True after the operator specified CPU reach behaviour directly as a product rule (W2e round-tiered caps, R1 3/3 - R2 5/2 - R3+ 15/5) and declined further validation. The statistical verdict in docs/plans/draft-extensions/mock-calibration-2026-08d.md is STILL FAILED and test_w2_16_calibration_gate pins that independently, so the two facts stay visible together. Turning this flag off is the kill switch for the CPU-bot mock.`

**(b) `docs/config-reference.md:309`** — the `draft.mock` flag row. Its default
column reads `false` and its body asserts the flag "stays OFF" and
`CPU_MODEL_VALIDATED` is `False`. Change the default column to **`true`** and
replace the final three sentences ("`mock_draft_service.CPU_MODEL_VALIDATED` is
`False` … re-run green against a re-specced model.") with:

> `Shipped ON 2026-08-08 (6caca35) by operator override, not by the gate passing. mock_draft_service.CPU_MODEL_VALIDATED is True; the recorded statistical verdict is still FAILED and test_w2_16_calibration_gate asserts that independently, so a change that makes the model pass turns the suite red and forces a deliberate artifact re-publish. Revert by setting CPU_MODEL_VALIDATED back to False; nothing else needs to change.`

**(c) `docs/config-reference.md:565`** — the ⚠ paragraph under the
`_DEFAULT_CFG` table. Replace `` `CPU_MODEL_VALIDATED` is `False`, the CPU-bot
mock stays cut, and `` with `` `CPU_MODEL_VALIDATED` is `True` by operator
override while the statistical verdict remains FAILED, so ``. The rest of the
sentence (*"a deliberate re-fit + re-gate is owed before either value means
anything"*) is still true and should stay.

**(d) NEW — `docs/architecture.md:135`** and **(e) NEW — `docs/glossary.md:30`
and `:42`** carry the same stale `CPU_MODEL_VALIDATED = False` claim, and
`architecture.md` additionally says *"`advance_cpu` raise[s] unless a caller
explicitly opts in … the routes never do"*, which is now false. Exact clause-level
replacements: [`hld-delta.md` §12](./hld-delta.md#12-docsarchitecturemd-rows-to-amend).
These two were **not** in the plan's R10 and are the same defect.

---

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` —
  the repo's **first** mock flow. Covers: entering Mock mode; creating a mock;
  **#291's acceptance** (`assertVisible: "Tap to draft"` on the board *before* any
  row tap); making a user pick through the confirm bar; reaching the recap; and
  **#292's acceptance** (back to the room → the complete state's **primary** is
  "Start a new mock" → a second mock reaches `mock-draft.on-the-clock`).
  Full step list: [`prd.md` §7.3](./prd.md#73-maestro).
- [ ] Extended flow: none.
- [x] **PARTIAL WAIVER — three uncovered areas, each with its reason:**
  1. **#292 dead-ends 2 and 3** (sticky create error; sticky `postRefusal`).
     *Reason:* both need a server failure or a typed-empty refusal injected
     mid-session, and the mobile harness has no fault-injection seam. Substituted
     coverage: structural tests T-292-02 (no reachable panel branch renders zero
     controls) and T-292-03 (`setPostRefusal(null)` present in both clearing
     paths). Backlog: a fault-injection knob for the harness.
  2. **#290's engine behaviour.** *Reason:* it is a distribution over seeds, not
     a UI state — no Maestro assertion can express it. Substituted coverage:
     T-290-01…T-290-11, eleven backend tests, two of them failing-first.
  3. **D-16.** *Reason:* the harness is Sleeper-fixture-driven and has **zero**
     MFL references in `backend/test_users.py`, `backend/test_support.py`, `qa/`
     or `mobile/.maestro/*.yaml`; MFL's only test seam is a pytest monkeypatch
     Maestro cannot reach. Substituted coverage: T-290-12 / T-290-13, plus a
     recorded observation of the **Mock Draft** screen's owner names during G1's
     live-league QA pass on Dependables (62846) — same session, one extra
     screenshot.

- **`testID`s added:** exactly one — **`mock-entry.retry`**
  (`MockEntryPanel.tsx`, fed a literal from `DraftRoomScreen.tsx`). **No flow
  references it**, so it needs no allow-list entry. No testID is renamed, moved
  or removed; the complete-state button swap deliberately keeps
  `mock-entry.run-it-back` bound to the *start-another action* and
  `mock-entry.recap` to the *recap action*, so existing selectors keep meaning
  what they meant.
- **Lint status — RUN, not assumed.** `bash mobile/scripts/testid-lint.sh` in
  this worktree at `7cea1fa`: **`testid-lint OK`, exit 0.** Every id the new flow
  references was individually verified to exist as a literal `testID=` in
  `mobile/src` (list in [`prd.md` §7.3](./prd.md#73-maestro)). Re-run after
  authoring the flow — it is a required CI job (`maestro-testid-lint`).
- **Smoke-suite impact:** `UndraftedRowView` is shared between the Draft Room and
  the mock, so **`d1-draft-room-complete.yaml` and
  `d2-draft-room-order-not-set.yaml` are the no-regression checks** and must stay
  green. Neither asserts on the trailing slot's content, and neither is on the
  user's turn (they are the read-only room, which passes no `onPress`/`actionLabel`),
  so the row renders byte-identically there. Of the 11 smoke flows, none touches
  the Draft Room or the mock; all 11 still run under the Tier-1 gate.
- **Also mandatory, not in CI:** `cd mobile && npm run test:mock-mode-marker` on
  **every** commit touching `MockDraftScreen.tsx` or `DraftRoomScreen.tsx`.
  Constraints: [`lld-delta.md` §6.5](./lld-delta.md#65-structural-constraints-this-must-not-break).
- **Backend pytest:** `backend/tests/test_mock_draft.py` — **additions only**,
  plus **one** helper-fixture line corrected with a comment explaining why it is
  not an assertion weakening ([`prd.md` §7.2](./prd.md#72-the-one-shipped-test-that-must-change-and-why-it-is-not-a-weakening)).
  Full-file prototype result: **80 passed, 0 failed**, tripwire did not fire.

---

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | **No route added, renamed, removed or contract-changed.** `SCHEMA` unchanged; every `/api/mock-draft` response key set unchanged. The plan expected an abandon-contract widening; the route already accepts a `complete` row (`server.py:11781-11794` → `database.py:10786-10805`, `WHERE` on id + user_id only). D-16 changes the *value* of `order[].owner_username` from a machine id to a name — same type, same nullability. Orchestrator-owned either way. |
| `living-memory/LLD.md` | **YES** | A convention shifts: the mock engine gains a **gap-derived, engine-internal cluster ("run")** that is explicitly *not* the cross-client tier enum, computed by a forward walk to satisfy amendment 1's no-`sorted` rule, and composed with the W2e cap through `min()` so product policy can only be tightened. Also record that mock CPU support bounds are module constants, never `model_config` rows. Orchestrator-owned. |
| `docs/architecture.md` | **YES** | The `mock_draft_service.py` row (`:135`). Two clauses amended for this change (need-conditional mixture weight; the run as a second, tighter bound) and **two corrected as pre-existing staleness** (`CPU_MODEL_VALIDATED = False`; "the routes never do"). Clause-level text: [`hld-delta.md` §12](./hld-delta.md#12-docsarchitecturemd-rows-to-amend). Orchestrator-owned. |
| `living-memory/HLD.md` | **n/a** | No new module, no new client, no new major flow. This is a change to a model's internals inside an existing module; the convention half lands in `LLD.md`. |
| `docs/cross-client-invariants.md` | **YES, one sentence** | The closing note under § Tier colors already quarantines three engine-internal lookalikes (`web/css`'s 4-level set, `tier_depth`, `tier_mult_*`) as **NOT** the tier enum. A run is a fourth and gets a clause: *"Likewise `mock_draft_service`'s gap-derived **run** — a locally-significant value drop used to bound a CPU drafter's reach — is an engine-internal cluster, not a tier: it is computed per pick, never persisted, never sent to a client, and carries no key, colour or label."* Orchestrator-owned. |
| `docs/glossary.md` | **YES, one new term + two corrections** | **New — "Run (draft)":** *"A gap-derived cluster of adjacent players on the mock draft's consensus board (`mock_draft_service.run_offset`, draft-extensions W2f). A boundary is cut where a value drop is at least 2.5× the median gap in a 9-gap local window — adaptive rather than a fixed Elo threshold, because the value curve flattens in the tail. On the 2026 board this yields a median run of 5 players with no size clamp. A CPU drafter may not reach past its run's boundary in rounds 1-2 and may cross exactly one from round 3, composed with the W2e round cap through `min()` so the operator's policy is only ever tightened. **Not a tier band** — engine-internal, per-pick, never persisted or sent to a client."* **Corrections:** `:30` (Mock draft) and `:42` (Calibration gate) both still say `CPU_MODEL_VALIDATED` is `False` / the CPU half is "cut" — stale since `6caca35`. Orchestrator-owned. |
| ADR / `DECISIONS.md` | **DECISIONS.md entry, no ADR** | *Judgement, stated so it can be challenged.* An ADR is for a non-obvious **architectural** choice; this is a bounded change to one model's internals inside an existing module, with no new module, boundary, storage or contract — the same class as W2b's mixture re-spec and W2e's reach policy, **neither of which took an ADR** (both are recorded in `docs/plans/draft-extensions/`). What *is* worth a durable record is the reusable decision: **an engine-internal cluster must never be expressed through the cross-client tier enum**, which is the second time that call has been made (#279 was the first). One `DECISIONS.md` entry (next id = `max + 1`, grep first), cross-linking [`hld-delta.md` §3](./hld-delta.md#3-new-engine-notion-the-run). If the operator or the reviewing Planner wants an ADR instead, it is cheap to add and the argument is already written. |

---

## 5. Ship gate declaration

- **Simulator-gate tier: 1** — *Mobile screen / navigation / state change*, per the
  matrix in `docs/runbook.md` § Pre-ship simulator gate. #291 changes a rendered
  screen and #292 changes client state; either alone is Tier 1. (#290 and D-16
  are backend-only and would be Tier 4 and Tier 3 respectively, but the group
  ships together and the highest tier governs.)
- **Required before merge to `main`:** the **full 11-flow smoke suite** + the
  feature's own flow `d3-mock-draft-loop.yaml`, **plus**
  `d1-draft-room-complete.yaml` and `d2-draft-room-order-not-set.yaml` as the
  shared-`UndraftedRowView` no-regression check.
- **Evidence:** append to `living-memory/TEST_LEDGER.md` (flows, pass/fail, sim
  device, SHA) **and** write `qa/sim-runs/last-sim-run.json`. Enforced locally by
  `githooks/pre-push` (`git config core.hooksPath githooks`).
- **Also logged in TEST_LEDGER:** the D-10 calibration numbers, before and after
  ([`prd.md` §8 G-2](./prd.md#8-guardrails)) — recorded regardless of outcome.
- **Operator deviation from the matrix:** none requested.
- **`FTF_SKIP_SIM_GATE` is NOT used.** No express declaration was made.

---

## 6. Out of scope and flagged

Full list in [`prd.md` §6](./prd.md#6-out-of-scope). Two items are flagged here
because they are *newly discovered defects* rather than deliberate exclusions:

1. **`MOCK_MIN_TEAMS` disagreement — client `6` (`MockEntryPanel.tsx:41`) vs
   server `4` (`mock_draft_service.py:85`).** A 4- or 5-team league is refused by
   the client with "Needs 6+ teams" for a reason the server would allow. This is
   a genuine fourth "can't do a mock" dead-end, but it is not a *second*-mock
   dead-end and is not one of D-8's three. **Not fixed. Backlog item.**
2. **`MockSetupSheet` busy-stranding** (`:182`). Named by the plan, not in D-8.
   **Not fixed. Backlog item.**

Also spun out as backlog, not defects: registering the mock analytics event
family (§1); a fault-injection seam for the mobile harness (§3); an MFL seam for
the mobile harness (G1's item, restated here because G2's D-16 coverage depends
on it).

---

## 7. Open items for the operator

Five, in descending order of consequence. Each blocks or reshapes build.

**O-1 — The Tate case does not say what the report implies, and you should see
the numbers before we build.** Carnell Tate is the consensus **#2** rookie on the
shipped board (1qb_ppr 1817.5 · sf_tep 1776.5), behind only Jeremiyah Love.
**Tate going 4th is a two-slot fall, and under the shipped engine it happens
10.1 % of the time — less often than the consensus #1 landing there (15.8 %).**
The real defect is that the top of the board is near-random, and the fix targets
that. **After the fix Tate will still go 4th roughly one time in six**, because
Tate / Tyson / Lemon are separated by 46 and 71 Elo — they are one tight group,
and a value-gap tier rule (what you asked for) says a bot may take any of the
three. What changes: Love can no longer fall past 3, Tate can no longer fall past
4, and Sadiq / Concepcion / Price — 79 to 219 Elo below Tate — can essentially
never reach pick 4. **If that is not what you meant, the complaint is about how
the consensus prices Tate against the other WRs, which is a different fix in a
different lane.** Full argument: [`prd.md` §4](./prd.md#4-the-tate-case).

**O-2 — Accept the analytics waiver (§1)?** Recommend yes, with "register the
mock event family" spun out. Rejecting it adds a fifth workstream touching an
orchestrator-owned file.

**O-3 — Accept "no new kill switch" (§2.1)?** Recommend yes; `draft.mock` is the
lever and a flag inside the calibration harness is a correctness hazard. The
alternative is specced if you disagree.

**O-4 — Accept the partial Maestro waiver (§3)?** Recommend yes. Note what
*improved* against the plan: the plan concluded no hermetic mock seeding exists;
it does — the `ffv3-predraft` corpus is 12 teams, `pre_draft`, 4 rounds, and
clears every block predicate, so the first mock flow is authorable with **no**
seeder work.

**O-5 — File-ownership gap, needs a ruling before Phase 2.** The batch plan's
ownership table gives G2 `mock_draft_service.py`, `MockDraftScreen.tsx`, the
`/api/mock-draft` shims and this folder — but **not**
`mobile/src/screens/DraftRoomScreen.tsx` or
`mobile/src/components/draft/MockEntryPanel.tsx`, both of which #291 and #292
require. G1's PRD R-14 states G1 touches no file under `mobile/`, and G3 owns only
`LeagueSummaryScreen.tsx`, so the claim looks uncontested — but it should be
confirmed, not assumed. G2 correspondingly **releases** `backend/database.py`
(no edit needed).
