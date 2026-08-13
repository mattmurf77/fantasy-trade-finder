# Feature Scope — #295 / #296: the mock draft never puts the user in the draft

**Date:** 2026-08-10
**Entry point:** feedback **#295** (MockDraft) + **#296** (DraftRoom) — one defect, two reports
**Builder:** Author agent (Phase 1) → build agent (Phase 2)
**Operator sign-off on waivers:** **REQUIRED — two waivers (§1 analytics, §3 Maestro) and three open items (§7).**

> Copied from [`docs/templates/feature-scope.md`](../../../templates/feature-scope.md).
> Companion docs: [`prd.md`](./prd.md) · [`plan.md`](./plan.md) ·
> [`reconciliation-log.md`](./reconciliation-log.md).
>
> **Rigor: FULL GATES.** No express declaration was made. This change alters an
> **API contract** (a new `reason` value on the typed-empty, a new keyword
> parameter on the shared refusal ladder) on a **feature-flagged surface** —
> both are on the bright line in `CLAUDE.md` §Conventions, which excludes them
> from "quick fix" even if express were declared. Agents never self-select
> express.

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
- [x] **(c) WAIVED — no analytics in this fix. Reason below. Operator must accept or reject.**

**Verified against the taxonomy, not assumed.** `backend/analytics_taxonomy.py`
is **DEFAULT-DENY**: `ALLOWED_CLIENT_EVENTS` (`:38-104`) is a frozenset and
unregistered client events are counted and **dropped** server-side, never 4xx'd.
`git grep -n "mock" backend/analytics_taxonomy.py` returns **zero** `mock_*`
events. The four registered `draft_room_*` events (`:87-88`, properties at
`:241-246`) cover the Draft Room's per-player row actions and nothing on the
mock surface.

Adding a `track()` call for this fix would therefore produce instrumentation
that **looks live and records nothing** — the NULL-`platform` failure mode this
convention exists to prevent. The #290 batch reached the same conclusion and the
waiver was accepted; `DraftRoomScreen.tsx:604-609` carries the reasoning in a
code comment.

**Recommendation: accept the waiver again — and treat this bug as the strongest
argument yet for the backlogged mock event family.** A 100 % failure rate on a
lit feature ran for two days, on every league and every platform, and the only
signal that reached us was two typed feedback reports. A registered funnel
(`mock_started` / `mock_pick_made` / `mock_completed` / `mock_abandoned` /
`mock_create_refused` with a `reason` property) would have shown
`mock_pick_made == 0` on day one. That is a four-touch registration in an
**orchestrator-owned** file plus client wiring, i.e. its own workstream, and
widening a regression-critical bug fix into an instrumentation project would
delay the repair. **Spin it out; do not fold it in.**

→ follow-through if the operator rejects the waiver: `backend/analytics_taxonomy.py`
(`ALLOWED_CLIENT_EVENTS` + the property map), the tracking-plan addendum under
`docs/business/analytics/`, `docs/cross-client-invariants.md`, and client call
sites — a fifth file-ownership claim that this batch does not currently hold.

---

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No migration. `mock_drafts` is
  written through the shipped `create_mock_draft` / `update_mock_draft` helpers
  with unchanged arguments. `docs/data-dictionary.md` → **n/a because** no
  schema object changes.
- **New/changed feature flags:** **none.** `draft.mock` (`config/features.json`,
  currently `true`) remains the only lever and the only kill switch.
  `backend/feature_flags.py` `FLAG_KEYS` unchanged; `docs/config-reference.md`
  flag table unchanged.
- **New env vars / `model_config` keys:** **none.** One new module constant,
  `REASON_USER_NOT_IN_DRAFT` (`mock_draft_service.py`, beside `:81-86`), which
  is a protocol string, not a tunable — deliberately not a `model_config` row,
  matching the existing three reasons.

### 2.1 Should the fix ship behind a new flag? — **No.**

*The case for one:* the create path's owner resolution changes for every league
on a surface that is already lit in production, with no dark landing.

*Why a flag is the wrong call here:*

1. **A default-OFF flag would ship the reported bug unfixed** — the feature is
   100 % broken today, so "off" is not a safe default, it is the defect.
2. **A default-ON flag is a flag nobody will ever turn off** — the only reason
   to flip it is to restore a state in which no user can take a pick.
3. **The kill switch already exists and is correctly sized.** If the repaired
   mock misbehaves, the honest lever is `draft.mock → false`, which is exactly
   "turn the mock off" and needs no deploy.
4. **The change is a one-hunk revert.** Four small server edits, one
   `build_settings` clause, one refusal rung.

**If the operator disagrees**, the shape is `draft.mock_user_seat` (default
**true**), read once in `server.py` and threaded into `_mock_league_context` —
never read inside `mock_draft_service`, so the engine and the calibration
harness stay flag-free. Say so and it will be specced.

### 2.2 Ship-the-knob (deploy-free rollback lever)

`draft.mock → false` disables all four `/api/mock-draft` routes (404
`feature_disabled` before any session work) and the mobile mock surface, with no
redeploy and no effect on the real Draft Room. That is the named lever.

---

## 3. Test scope (mobile test platform)

- [ ] New flow
- [x] **Extended flow:** `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml`
  — add **T-295-12**: immediately after `mock-draft.on-the-clock` becomes
  visible in lap 1 and **before** any `scrollUntilVisible`/`tapOn` of an
  undrafted row, `assertVisible` the on-the-clock card naming the user's own
  team. #291's flow asserted the *affordance* ("Tap to draft") was visible; it
  never asserted the user was ever **on the clock**, which is the UI-level
  statement of this bug and the one assertion that would have caught it.
- [x] **PARTIAL WAIVER — the extended flow CANNOT BE RUN. Reason below.**

### 3.1 The `d3` blocker is real, pre-existing, and this fix does not close it

Stated honestly rather than optimistically, because the last batch's estimate
here was wrong and it cost the sim gate.

- `backend/tests/fixtures/profiles/standard.json` declares exactly **one**
  league, `990000000000000001`.
- `d1`, `d2` and `d3` all target `1312140920132497408` (ffv3), which appears in
  **no** profile. `d3`'s own header (lines 24–32) records this as an inherited
  precondition.
- `backend/tests/fixtures/seed_ui_test_db.py` writes **nothing** for
  `mock_drafts` (grep: zero hits) — though that is *not* the blocker, since `d3`
  creates its mock live through the API.
- The real blocker is that the profile seeder **synthesises** leagues with
  generated members and rosters (`:383-399`), while ffv3 is a *recorded* Sleeper
  corpus reached through the `FTF_SLEEPER_FIXTURES_DIR` seam (`:1048`). Making
  `d3` runnable means either merging the recorded corpus into a profile's
  fixture dir — the "corpus merged into the fixture dir" step the flow headers
  assume, which is **unimplemented** — or giving the synthetic profile league a
  synthetic Sleeper draft object.

`living-memory/TEST_LEDGER.md` (2026-08-10, batch #289–#294) already records the
verdict: *"The build agent's 'one `leagues[]` entry' estimate was checked and
does not hold; this is real seeder work."* **I agree.** It is its own item with
its own tests, and folding it into a regression-critical repair would delay the
repair and widen the blast radius.

**Consequence the operator must see:** the Tier-1 gate's "feature's own flow"
cannot run — for the **second batch running, on the same feature**. The Tier-2
live-league verification ([`prd.md` §9.4](./prd.md#9-done-criteria)) therefore
becomes the batch's **load-bearing evidence**, not a nice-to-have. The T-295-12
assertion is authored into `d3` in this batch so it is ready the moment the
profile work lands.

### 3.2 testIDs

- **Added:** exactly one — **`mock-entry.blocked.user_not_in_draft`**
  (`mobile/src/screens/DraftRoomScreen.tsx`, the new `mockBlock` arm), matching
  the five shipped siblings (`mock-entry.blocked.cpu_model_unvalidated`,
  `.class_not_loaded`, `.startup_draft`, `.league_too_small`, `.live`,
  `.complete`).
- **Renamed / moved / removed:** **none.**
- `bash mobile/scripts/testid-lint.sh` MUST be run and exit 0 after authoring
  (required CI job `maestro-testid-lint`). No flow references the new id, so it
  needs no allow-list entry, but it must still lint clean.

### 3.3 Smoke-suite impact

- Of the 11 smoke flows, **none** touches the Draft Room or the mock surface.
- `d1-draft-room-complete.yaml` and `d2-draft-room-order-not-set.yaml` are the
  no-regression check for the shared `UndraftedRowView` — but **both are
  themselves blocked by the same profile gap** (§3.1) and cannot run either.
  Substituted coverage: an assertion that `GET /api/draft/board` for ffv3 is
  **byte-identical** before and after the fix (`prd.md` §9.3), which is the
  property those flows would have checked.

### 3.4 Backend pytest

`backend/tests/test_mock_draft.py` — **additions, plus one fixture rewrite.**

The shared `session` fixture (`:936-945`) makes the session user the league's
**only** member — the exact inverse of production, and the reason 40-odd
route-level tests passed on this defect. It MUST be rewritten to the production
shape (caller excluded from `members`, ≥ `MOCK_MIN_TEAMS` other members) and
pinned by a standing assertion (T-295-02) so it cannot drift back. **This is a
fixture correction, not an assertion weakening:** it makes the fixture *harder*,
and it un-short-circuits every route test in the file, which currently answers
`league_too_small` before order resolution is reached at all. Expect churn in
those tests' expectations, and treat any that get *easier* as a defect in the
change.

**The rewrite has exactly two casualties, both enumerated and both with a
specified repair** ([`prd.md` §8.1 T-295-02](./prd.md#81-required-tests)) —
`test_w2_20_g2_the_capability_probe_answers_without_starting_a_mock`
(`:1232-1249`, fails loudly) and `test_the_abort_criterion_is_enforced_at_the_route`
(`:1036-1051`, **keeps passing while its stated premise at `:1048` becomes
false**). The second is the dangerous one and it is the §8.0 disease arriving
through this fix's own largest diff. A builder must not improvise these repairs:
the obvious fix to the first would **delete the suite's only route-level
`league_too_small` coverage**, which is why T-295-15 relocates it.

**Commit discipline (PRD R-8.2b):** the fixture rewrite lands as its **own
commit**, with the full suite run immediately before and after and **every test
whose status changes enumerated** in `TEST_LEDGER.md`. A status diff is the only
reliable detector of a test that breaks by passing — no assertion can catch that,
because by construction there is nothing to assert on.

New tests: **T-295-01 … T-295-15** ([`prd.md` §8.1](./prd.md#81-required-tests)),
including three added in Round 3: **T-295-13** (the route's `UserNotInDraft`
mapping — untested in Round 1, and its failure mode is a silent **500** via
`server.py:2071`'s catch-all `errorhandler(Exception)`), **T-295-14** (the
co-owner degrade, R15), and **T-295-15** (the relocated `league_too_small`
route coverage).

**Failing-first is mandatory** for every behavioural test, with the red output
recorded in `TEST_LEDGER.md`. The #289–#294 batch found three separate lanes
where a test passed on the very defect it named — including one whose grep
matched the JSX comment explaining the behaviour. **Round 3 adds the distinction
that makes this enforceable:** a *pre-fix regression* goes red on `2e0b2c7`; a
*half-implementation tripwire* cannot, so its red-first evidence is a **named
plausible wrong fix**, constructed deliberately and shown red. "New code, could
not be shown red" is not an acceptable answer — every tripwire names its
half-implementation.

### 3.5 Also mandatory, not in CI

- `cd mobile && npm run test:mock-lifecycle` (`MockDraftScreen.tsx` /
  `DraftRoomScreen.tsx` are touched).
- `npx tsc --noEmit` after a **real `npm ci` in this worktree**. Never symlink
  the main checkout's `node_modules` — it is stale and yields phantom errors.

---

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **YES — three edits, all orchestrator-owned (propose, don't apply)** | (1) **`:426`** — the § Mock draft status blockquote still says *"the CPU-bot mock is **CUT**"* and `CPU_MODEL_VALIDATED` is `False`. **False since `6caca35` (2026-08-08).** `git grep -n CPU_MODEL_VALIDATED -- docs config` returns exactly one wrong hit and this is it — the #289–#294 batch enumerated **six** such locations and corrected all six, missing the seventh, which is the *route contract* document. Exact replacement text: [`prd.md` §6 R10](./prd.md#6-requirements--docs). (2) **`:441`** — the capability-probe ladder is now **four** rungs: `class_not_loaded → cpu_model_unvalidated → league_too_small → user_not_in_draft` (R11). (3) **`:448`** — add `user_not_in_draft` to the typed-empty reason enumeration (R12). No route added/renamed/removed; `SCHEMA` stays `1`; no request or response *shape* changes. |
| `living-memory/LLD.md` | **YES — one convention row** | Two conventions shift and both are reusable: (a) **`sess["league"].members` is the leaguemates, caller excluded** — any consumer that needs "everyone in the league" must add `sess["user_id"]` itself; (b) **a refusal that can only be produced by a silent divergence gets a rung AND a raise** — the ladder for what the probe can see, an engine exception at the point of truth for what it cannot. |
| `docs/architecture.md` | **n/a because** | No module is added, removed or re-wired, and the data flow is unchanged: the create route still calls `_mock_league_context` → `_mock_real_draft` → `build_settings` → `advance_cpu` in that order. The `mock_draft_service.py` row (`:135`) was corrected by the previous batch and remains accurate. |
| `living-memory/HLD.md` | **n/a because** | No new module, client, boundary or major flow. This is a bug fix inside an existing module plus one new value on an already-open enum. |
| `docs/cross-client-invariants.md` | **n/a because** | `reason` is documented as an **open** set (plan D10) precisely so a new member needs no cross-client coordination — `mobile/src/api/mockDraft.ts:35-39` types it with a `(string & {})` arm and `MockDraftScreen.tsx:785-795` has a `default:` arm. No closed enum, colour, threshold or shared constant changes. (`MOCK_MIN_TEAMS`'s client/server disagreement is real and **already backlogged** — see §6.) |
| `docs/glossary.md` | **n/a because** | No new domain term. `user_not_in_draft` is a protocol string on an existing documented enum, not a concept. |
| ADR or `DECISIONS.md` entry | **`DECISIONS.md`, no ADR** | The durable, challengeable decision is **"repair and guard together, and do not widen `league.members`"** — including the blast-radius measurement (~20 `.members` references in `server.py`, plus the trade engine, matches, power rankings, free agents and the League summary) and the precedent that FB #41 deliberately went the other way. An ADR is for a non-obvious *architectural* choice; this is a scoping decision inside an existing module. Also **one `GOTCHAS.md` entry**: *"`sess["league"].members` never contains the caller"* — second occurrence (FB #41 was the first, `backend/tests/test_league_total_teams.py:1-20`, on this same ffv3 league). Next IDs are `max + 1` — grep first. |
| `mobile/src/api/CLAUDE.md:18` | **found in passing — NOT required for this fix** | It still describes the capability probe as a contract gap (*"`GET` has no capability probe … POST-only, G2"*), which W2d closed on the server. The *client* still doesn't consume it, so the line is half-true. Flagged, not fixed — see §6. |

---

## 5. Ship gate declaration

- **Simulator-gate tier: 1.** Per the matrix in `docs/runbook.md` § Pre-ship
  simulator gate: the change touches `mobile/src` (a rendered `mockBlock` arm
  and screen copy), which is *"Mobile screen / navigation / state change"*.
  The backend half alone would be Tier 3 (*"Backend route/schema consumed by
  mobile"*), but the group ships together and the highest tier governs.
- **Required by the matrix before merge to `main`:** the full 11-flow smoke
  suite **+ the feature's own flow** (`d3-mock-draft-loop.yaml`) **+ `d1`/`d2`
  as the shared-`UndraftedRowView` no-regression check.**
- **Operator deviation from the matrix — REQUESTED, and it is not a formality.**
  `d3`, `d1` and `d2` are **unrunnable** on a pre-existing fixture-profile gap
  (§3.1) that this fix does not and should not close. The 11 smoke flows are
  runnable and MUST be run. The three draft flows cannot be, for the second
  batch running on this same feature.
  - **Substitute evidence, which the operator must weigh as the real gate:**
    the Tier-2 live-league sign-off in [`prd.md` §9.4](./prd.md#9-done-criteria)
    — **a mock started and a pick taken on ffv3 AND on Dependables (MFL 62846)**
    — plus the byte-identical `GET /api/draft/board` check for ffv3 (§3.3), plus
    T-295-01/03/04 running the **real route** against the two `recorded-live`
    corpora, which is as close to production as an automated test in this repo
    gets.
- **Evidence:** append to `living-memory/TEST_LEDGER.md` (flows run, pass/fail,
  sim device, SHA, and the deviation with its reason) **and** write
  `qa/sim-runs/last-sim-run.json`. Enforced locally by `githooks/pre-push`
  (`git config core.hooksPath githooks`).
- **`FTF_SKIP_SIM_GATE` is NOT used** for the smoke suite. If the operator
  chooses to bypass entirely, that is a recorded decision — but note that the
  previous batch bypassed the gate on **this exact feature**, and the defect
  that shipped is the one being fixed now.

---

## 6. Out of scope and flagged

Full list with reasons in [`prd.md` §7](./prd.md#7-out-of-scope--guardrails).
Flagged here because each is a **real defect or gap discovered in passing**,
not a deliberate product exclusion:

1. **The `league.members`-means-opponents convention itself.** Named
   `members`, means *leaguemates*, has now produced two user-visible defects
   (FB #41's team count; this one). Recommended long-term fix — rename the
   concept or add a derived `all_owner_ids` — with measured blast radius, in
   [`prd.md` §7.1](./prd.md#71-the-leaguemembers-excludes-the-caller-convention-itself).
   **Kept out of this fix on coding-guidelines §3.** Backlog.
2. **The mobile client never reads the `capability` block.** `git grep
   capability -- mobile/src` finds no consumer, so every mock refusal — the
   three shipped ones and the new one — is discovered only *after* POSTing a
   create. The server-side G2 invariant still holds and is still worth having.
   Backlog: wire the probe into `MockEntryPanel`. (`mobile/src/api/CLAUDE.md:18`
   is stale in the same area — §4.)
3. **The `d3`/`d1`/`d2` profile-seeder gap** (§3.1). Blocks the sim gate on the
   whole draft surface. **Needs an owner.**
4. **`MOCK_MIN_TEAMS` client/server disagreement** — client `6`
   (`mobile/src/components/draft/MockEntryPanel.tsx:41`), server `4`
   (`backend/mock_draft_service.py:91`). A 4- or 5-owner league is refused by
   the client for a reason the server would allow. Already backlogged by the
   #290 batch; **untouched here**, and note that R4 makes the *server* count
   correct, which widens the disagreement by one team rather than creating it.
5. **Registering the mock analytics event family** (§1). Backlog.
6. **Co-ownership is unimplemented app-wide** (PRD R16). `git grep -n
   "co_owners" -- backend mobile web extension` returns **fixture hits only**.
   ffv3 roster 2 carries `co_owners: ["867866820202364928"]` = `lofman`, a real
   signin-capable member of that league. Every client's roster lookup keys on
   `owner_id` (`mobile/src/api/auth.ts:377`), so a co-owner matches no roster.
   Consequence under R15: he gets a **working** mock that is one team wider than
   his league, with his roster represented twice (his co-owner's seat and his
   own) — on ffv3, 12 teams where a primary owner sees 11. **This fix makes the
   case survivable, not correct.** Resolving it touches `session_init`, every
   client's roster lookup, the trade engine's member list and the League
   summary's team count. **Needs an owner.**
7. **The cross-league create path** (PRD §7.3). `_mock_resolve_league`
   (`server.py:11734-11744`) accepts any league in the `leagues` table with no
   session scoping (`backend/database.py:7458-7476`), while
   `_mock_league_context` (`:11543-11544`) reads the **session** league's
   members — so owners can come from league A and the order from league B. Same
   class as `5cf81e5` ("outlook: resolve platform from the requested league_id,
   not the session"), three commits ago. **Deliberately not guarded here** — the
   guard would be dead code today and would pre-emptively break the documented
   multi-league Draft tab (`DraftRoomScreen.tsx:153-155`); reasoning in
   [`prd.md` §7.3](./prd.md#73-the-cross-league-path-j-7--decision-and-reasons).
   It is nonetheless **R5's only live trigger**, so it must be filed.

---

## 7. Open items for the operator

**O-1 — ffv3's ownerless roster makes the post-fix mock an 11-team draft in a
12-roster league.** Roster 6 carries `owner_id: null`. **Recommendation: leave
it at 11**, with `order_source: "randomized"` carrying the disclosure —
inventing a manager is worse than omitting an empty chair, and a "vacant" CPU
seat needs a name, a persona and a rendering decision it does not have. Flagged
because it is a visible number on your own league.

**O-2 — accept the analytics waiver (§1)?** Recommend **yes**, with "register
the mock event family" spun out as its own item. Rejecting it adds a fifth
workstream touching an orchestrator-owned file, on a regression-critical fix.

**O-3 — accept the sim-gate deviation (§5), making the ffv3 + Dependables
live-league checks the batch's real gate?** Recommend **yes**, and schedule the
profile-seeder work separately. The alternative — blocking this ship on the
seeder — leaves a 100 %-broken feature broken for longer. **But you should hear
the uncomfortable version too:** this is the second consecutive batch on this
feature to ship without a simulator run, and the first one is why we are here.
If you want the seeder work done first, say so now; it changes the batch's
shape and its timeline, and it is a defensible call.

**O-4 — confirm the `docs/api-reference.md` handoff (§4).** Three edits, all
proposed here with exact text and **not applied**, per the orchestrator-owned
convention. The `:426` blockquote was missed once already by the batch that
claimed to correct five such locations; please confirm who applies it so it is
not missed twice.
