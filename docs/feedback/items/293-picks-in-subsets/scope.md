# Feature Scope — #293 / #294: draft-pick value in Starters/Bench subsets and position filters

<!--
Copied from docs/templates/feature-scope.md per CLAUDE.md §Conventions "Feature gates".
Every section is answered or explicitly WAIVED with a reason. Waivers are surfaced to the
operator before build starts. NO express declaration has been made for this group, so all
four gates apply (scope block · Maestro delta · docs table · sim run).
-->

**Date:** 2026-08-10
**Entry point:** feedback #293 + #294 (group G3, polish path)
**Builder:** `/feedback` pipeline — Phase 1 Author agent (this doc), Phase 2 mobile build agent
**Operator sign-off on waivers:** **RECEIVED 2026-08-10** — all five items decided.
Four accepted as recommended; the unflagged recommendation was **OVERRIDDEN**:
*"Aligned to all recommendations but ship with G3 flagged."* See §6 for the disposition table
and §2 for the resulting flag spec.

**Contract:** [prd.md](prd.md) · **Plan:** [plan.md](plan.md) · **Disagreements:**
[reconciliation-log.md](reconciliation-log.md)

---

## 1. Analytics scope

- [ ] **(a) New events specced** — none.
- [ ] **(b) Existing events cover it** — **partially, and not the interesting question.**
      `screen_viewed` (`backend/analytics_taxonomy.py`, `ALLOWED_CLIENT_EVENTS`) already fires
      for `LeagueRankings`, so arrival on the screen is measured. There is **no** existing
      event for a subset switch, a position-pill toggle, or a Picks toggle — the taxonomy has
      nothing in that family for this screen. So `screen_viewed` cannot answer
      *"is the Picks opt-out used?"*, and claiming otherwise would be dishonest.
- [x] **(c) WAIVED — no analytics added, because:**
      1. This is a **defect fix restoring a value the payload already carries**, not a new
         capability whose adoption needs measuring. The success criterion is
         "picks stop vanishing", which is verified structurally (T-S1) and visually, not
         statistically.
      2. Instrumenting the pill would mean a **new client event type**, and
         `backend/analytics_taxonomy.py` is **DEFAULT-DENY** — an unregistered name is counted
         and dropped server-side while looking like working instrumentation (the module
         docstring: *"default-deny; unknown types are counted + dropped, never 4xx'd"*). Adding
         one correctly requires a tracking-plan addendum
         (`docs/business/analytics/2026-07-17-tracking-plan-v2.md`), the `EVENT_PROPS`
         allowlist entry, a client SDK call site, and a `docs/data-dictionary.md` follow-through
         — materially larger than the fix, and squarely the bright-line "analytics events" class
         that is not a quick fix.
      3. Adding it silently, or adding an unregistered name, are both worse than not adding it.

**Surfaced to the operator (this is the waiver, stated plainly):** *if you want to know
whether users deliberately turn Picks off after this ships, that is a separate, scoped
addition — one event (working name `rankings_filter_changed`, props `{subset, positions,
picks_included, surface}`), specced against the taxonomy up front, registered in all four
touches. Say the word and it becomes its own item. It is NOT in G3.*

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No `backend/database.py` change →
  `docs/data-dictionary.md` not in scope.
- **New/changed feature flags: ONE — `league.picks_always_counted`, default `false`.**
  *(Operator override of the Author's unflagged recommendation: it reverses shipped behavior on
  a live surface, so it gets a kill switch.)* Full specification in **prd.md R-0**; the
  reasoning that is now settled is not repeated here.

  | Item | Value |
  |---|---|
  | **Key** | `league.picks_always_counted` |
  | **Namespace** | `league.*` — sibling to `league.power_rankings` (the #14 feature this screen *is*), `league.activity_feed`, `league.rookie_board_entry`. **Not** `picks.*`: that family governs pick data availability and pricing, and this flag changes neither (`picks.value` and `pool_value` are byte-identical in both states) |
  | **Name form** | `_always_counted`, not `_in_subsets` — the flag governs #293 (subsets) **and** #294 (position filters); "subsets" would under-describe the latter |
  | **Default** | `false` — lands dark per convention; operator flips at the release gate |
  | **Kind** | Kill switch for a behavior reversal, not a dark launch of new machinery |
  | **Read sites** | **exactly one**, `mobile/src/state/useFeatureFlags.ts` → `useFlag('league.picks_always_counted')` in `LeagueSummaryScreen.tsx`. No backend read, no web read |
  | **OFF semantics** | byte-identical to `origin/main` @ `7cea1fa` — normatively tabulated per requirement in prd.md **R-0.1** |
  | **Atomicity** | one boolean, reaching **14 enumerated gated expressions (G1–G14)** by exactly three routes — the component-body identifier, `activeTotal`'s required 4th parameter, and `BarColumn`'s required prop. Partial gating is forbidden (prd.md **R-0.2**); both function-boundary crossings are `tsc`-enforced (no default, required prop) and pinned by T-S1 assertions 1–3, 13, 14 |
  | **Client absent-key** | `useFlag` is `!!s.flags[key]` ⇒ absent ⇒ `false` ⇒ today's behavior. **Deliberately NOT added to `LAUNCHED_FLAG_DEFAULTS`** while dark (prd.md **R-0.3**) |
  | **Graduation** | flipping to `true` must add `'league.picks_always_counted': true` to `LAUNCHED_FLAG_DEFAULTS` **in the same change**, or first-boot users stay on the old behavior until their first successful `/api/flags` fetch |

  **Four registration touches (prd.md R-13)** — a flag registered in fewer than four places
  silently does nothing somewhere:

  1. `backend/feature_flags.py` — `FLAG_KEYS` tuple (`:47`). `DEFAULT_FLAGS` (`:608`) gives it
     `False` automatically. **Load-bearing for testing:** `FTF_FLAGS` env overrides drop any key
     not in `DEFAULT_FLAGS` (`:668`), so without this the flag-ON test override is ignored.
  2. `config/features.json` — exact `_comment_*` + key insert text in **prd.md §6.1**,
     house-style-matched to `_comment_pick_assign_tradeable`. **Orchestrator-owned.**
  3. `backend/tests/fixtures/flags/release.json` — `"league.picks_always_counted": false`.
     Required: `_validate_profile` refuses a profile override naming a key absent from the base
     set (`seed_ui_test_db.py:234-236`).
  4. `docs/config-reference.md` — flag-table row (see §4).

  **Verified non-impact:** the key does **not** join `INVENTORY_FLAG_KEYS`
  (`seed_ui_test_db.py:108-122`, a separate hardcoded 13-key tuple), so adding it to
  `release.json` forces **no** decision in the five existing profiles and cannot invalidate
  `standard.json`. Hermetic default is OFF everywhere.

  **Ship-the-knob / rollback lever:** now a genuine deploy-free one — flip
  `league.picks_always_counted` to `false` in `config/features.json`; clients pick it up on the
  next successful `/api/flags` fetch (cold start, or the 30-min throttled foreground
  revalidate, `useFeatureFlags.ts:33`). No build, no EAS, no revert. The commit-revert path
  remains as a second-line lever.
- **New env vars / `model_config` keys:** **none.** `docs/config-reference.md` **is** now in
  scope, for the flag row (see §4).

## 3. Test scope (mobile test platform)

- [x] **New flows** (`mobile/.maestro/flows/league/` — new directory; G2 keeps its flows in
      `flows/draft/` so the directory creation is not a shared edit):
  - `01-picks-in-subsets.yaml` — Picks pill + legend present in All/Starters/Bench (T1);
    drill-in `league-summary.roster-picks` visible in Starters and Bench (T2). → R-1, R-4, R-7
  - `02-picks-in-position-filter.yaml` — R-6 state machine: tap RB ⇒ Picks selected; tap Picks
    ⇒ deselected; tap RB ⇒ back to All (rule B) (T3); #237 mirror leg + `filter-caption` reads
    `All · RB + Picks` (T4 — the flow never taps a Starters control, so `subsetLabel` is still
    `All`; the earlier `Starters ·` expectation would have failed on a correct build). → R-6, R-8.2
  - `03-no-picks-league.yaml` — `hasPicks === false` league: no Picks pill, no legend key, no
    Draft-capital group, any subset (T5); subset switching never clears the filter (T6).
    → R-11, R-5
  - **`04-picks-flag-off.yaml` — added by the flag override.** The no-regression proof: same
    navigation as T1/T6 but with the flag at its **default OFF**, asserting the Picks pill is
    absent in Starters/Bench, that tapping RB from All does **not** auto-add Picks, and that
    the OFF path is genuinely exercised; screenshots diffed against the same steps captured on
    `origin/main` @ `7cea1fa`. → **R-0.1**. Runs today, needs no flag forcing and no pick data
- [x] **New non-Maestro check:** `mobile/tests/check-picks-subset-invariance.js` + an
      `npm run test:picks-subset-invariance` script. **Sixteen** AST assertions pinning R-0…R-7
      and the R-10 guardrails — including **six** that pin the flag structure itself
      (assertions 1–3, 13, 14, 16: one read site; none inside `BarColumn`/`activeTotal`; each
      gated expression on its correct gating symbol; **both** `activeTotal` call sites threaded
      with no default parameter; the `<BarColumn>` prop pinned to a bare identifier; the R-0.4
      effect present). These are the only mechanical check of R-0.2 atomicity and are invisible
      to every screenshot and every Maestro flow. **Assertions 13 and 14 close two verified
      escape hatches** through which a build agent could otherwise pass the whole suite and
      still ship a half-gated screen (prd.md §7.3). Seed-independent. Follows the six existing
      `mobile/tests/check-*.js` checks, which parse real TSX with the project's `typescript`.
      **Honest note:** that family is **not** in CI (`.github/workflows/ci.yml` runs pytest +
      `tsc --noEmit` + `testid-lint.sh` only) — this runs manually and at the sim gate.
- [x] **Extended file:** `mobile/scripts/testid-lint-allow.txt` — 5 glob entries
      (prd.md §7.1). **Required, not optional:** proven by probe that the six templated
      `league-summary.*` id families fail `testid-lint.sh` (exit 1) without them, and
      `maestro-testid-lint` is a CI job.
- [ ] **PARTIAL WAIVER — pending operator sign-off.** Flows T1–T4 **cannot execute
      meaningfully today**: the hermetic QA world has **no draft-pick rows at all**
      (`backend/tests/fixtures/seed_ui_test_db.py` writes none; `build_cassettes` emits no
      `traded_picks`; `standard.json` has no picks key) ⇒ `hasPicks === false` ⇒ every surface
      under test is invisible. Full evidence and the two options in prd.md §7.2.
      **Recommendation: Option B** — author T1–T4 now tagged `[league, picks]`, run T5/T6 +
      T-S1…T-S4 in the gate, verify §3.1 rows 2/3/5/9 and §3.2 rows 11/12/14 **manually against
      the operator's real Sleeper dynasty league** with screenshots into this item folder
      (T-S6), and file the seeding as an immediate follow-up. Option A (seed a new `picks`
      profile now) is fully specced if the operator prefers real coverage in-change; it pulls
      backend test fixtures into G3 and roughly triples the change size.
- **`testID`s added/renamed:** **none.** Every id used already exists — all eleven verified with
  source line in prd.md §7.1.
- **Smoke-suite impact:** **none expected.** `flows/smoke/09-league.yaml` taps `tab.league` then
  waits on `league.hero` (a `LeagueScreen` id) and never touches the chart; the three
  `flows/rookie/*` flows use only `league-summary.league-home`, untouched. All 11 smoke flows
  re-run anyway under the tier-1 gate (§5) and must stay green — a useful independent signal
  that the change is contained. Under Option B the smoke world is **byte-identical** (no
  fixture change); under Option A it would still be byte-identical because the picks land in a
  **new** profile, deliberately not in `standard`.
- **Flag-state coverage (added by the override):** both states are exercised.
  **ON** — T1–T5 + the T-S6 manual pass. **OFF** — T7, the 11 smoke flows (which run the default
  flag set), T-S1's flag-OFF assertions, and the T-S6b manual control (the only test that sees
  flag-OFF **with real pick data**, since the hermetic seed has none). Forcing mechanics and
  **two verified traps** — `--flags` replaces rather than merges the seeded map, and
  `--flags @file` is documented but unimplemented and fails open — are in prd.md §7.6.
- **Backend: pytest files added/updated:** **none.** The two backend edits (R-13 touches 1 and
  3) are registry entries with no behavior: one string in the `FLAG_KEYS` tuple and one `false`
  in `release.json`. No production logic changes (prd.md §7.2 leg 1: the payload already carries
  `picks {count, value, items}` at team level for every subset; `_power_picks_by_owner(league_id,
  fmt)` takes no `basis`, so `picks.value` is identical on both bases). Existing
  `backend/tests/test_seed_ui_test_db.py` must stay green unmodified — verified it will, since
  the new key is not an inventory flag. Under Option A additionally:
  `backend/tests/fixtures/seed_ui_test_db.py`, `backend/tests/fixtures/profiles/picks.json`,
  `backend/tests/test_seed_ui_test_db.py` (`MVP_PROFILES`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `/api/league/power-rankings` already documents `total_value = positions_value + picks.value` and the team-level `picks:{count,value,items}` — this change only stops the **client** discarding it. Nothing to amend |
| `living-memory/LLD.md` | **UPDATE — required** | *"Picks are neither starters nor bench"* is a **retired client convention** and the LLD must not outlive it. Replace with: pick value is a subset- and filter-independent component of a team's charted value on `LeagueRankings` **when `league.picks_always_counted` is on**; it is excluded only by an explicit Picks-pill deselection; and Starters + Bench therefore deliberately do **not** partition All. Also record the R-6 pill invariant **in its qualified form** — *whenever the filter is non-empty, the Picks pill's selected state is exactly equal to whether pick value is in the chart; an empty filter means every key, including picks, with no pill selected.* The unqualified version is **false** in the empty-filter case (prd.md R-6 / Planner O-4) and must not be propagated here |
| `docs/architecture.md` | **n/a** | No backend module added, removed or re-wired; no data-flow change. One client screen's derivation changes |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow. Architecture unchanged |
| `docs/cross-client-invariants.md` | **PROPOSED, NOT MADE — orchestrator-owned** | The plan's row ("n/a, the neutral-Picks rule is preserved verbatim") is **wrong**: the rule is **not in the document**. `LeagueSummaryScreen.tsx:159-162` cites cross-client-invariants for the neutral-ink Picks treatment, but the "Position color tokens" section (`:186-194`) lists only QB/RB/WR/TE hexes. Exact proposed append text in **prd.md §9.3**; it also encodes the subset/filter-independence rule so a future web subset control cannot re-introduce #293. **The orchestrator makes this edit, not the build agent** |
| `docs/glossary.md` | **n/a** | No new domain term. "Draft capital", "Picks", "starters", "bench" are all already in use on this screen and in the glossary's existing vocabulary |
| ADR / `DECISIONS.md` | **`DECISIONS.md` entry — required** | This reverses a deliberate, seven-times-documented shipped design, on an operator ruling. That is exactly a non-obvious choice that must be findable later. Next id = `max(existing) + 1` — **grep `living-memory/DECISIONS.md` first**, do not assume. Content: the ruling verbatim; the four rejected alternatives (caption-only, proportional allocation, a fourth "Picks" subset, delete the Picks pill); the accepted §4 non-partition consequence; R-6's operator-silent zone; **and the flag decision — that the Author recommended unflagged and the operator overrode it on the grounds that a reversal of shipped behavior on a live surface gets a kill switch.** That override is precisely the kind of reasoning a future reader will want and cannot reconstruct. **No ADR** — no architectural boundary moves |
| `docs/config-reference.md` | **UPDATE — required** *(was n/a before the flag override)* | New flag-table row: `league.picks_always_counted` · default `false` · "League rankings chart counts draft-pick value in every subset and position filter (#293/#294); OFF = the pre-#293 behavior in which picks count only in All with no filter." Fourth of the four registration touches — the other three are `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json`, and `backend/tests/fixtures/flags/release.json` (§2) |
| `docs/runbook.md` | **n/a** | No new operational failure mode. The flag's rollback lever is a plain `config/features.json` flip, already covered by the § Feature flags section's general procedure — no feature-specific runbook entry needed. *(If the operator wants a graduation checklist recorded somewhere operational rather than in prd.md R-0.3, this is the file — orchestrator's call.)* |
| `docs/design/design-system.md` / `components.md` | **n/a (read, not written)** | Zero new tokens, styles or components. `PICKS_COLOR = chalk.faint` and `GRAY_SEGMENT.PICKS = ink.ink3` already exist; the change makes an already-specced element render in more states. All three copy strings reuse `type.bodySm` (13px) and `type.data` (13px) — nothing at or below the 11px floor, no emoji, no gradient, no new accent, ice still only on actions |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `docs/feedback/items/INDEX.md` | **UPDATE at ship** | Append-only, written by all three groups — G3 appends **one self-contained block per file**; the orchestrator either serialises the writes or resolves conflicts by keeping both |

## 5. Ship gate declaration

- **Simulator-gate tier: 1 — RECONFIRMED under the flag override** (prd.md §7.7). Per
  `docs/runbook.md` § Pre-ship simulator gate risk-tier matrix, change class **"Mobile screen /
  navigation / state change"**. Required before merge to `main`: **full smoke suite (11 flows) +
  this feature's own flows**, on simulator.
  - **The flag does not lower the tier — it adds to the gate.** The matrix keys on change class,
    not on risk-after-mitigation, and both flag states must now be exercised. "It lands dark so
    users see nothing" is not an argument for tier 2: the gate exists to validate the build the
    operator will flip, and an unexercised ON path is exactly what a kill switch cannot protect
    against.
  - Feature flows in the run: `flows/league/04-picks-flag-off.yaml` (T7, **flag OFF**) and
    `flows/league/03-no-picks-league.yaml` (T5, T6, **flag ON**) unconditionally;
    `flows/league/01-…` and `02-…` (T1–T4, **flag ON**) **only if** §3's picks-seeding option A
    is taken — otherwise they are authored, tagged `[league, picks]`, and skipped with the §3
    waiver as the recorded reason.
  - The 11 smoke flows run at the **default (OFF)** flag set and are the byte-identity evidence
    for R-0.1.
  - **Record each flow's flag state in the ledger entry** — a tier-1 run that does not say which
    state it exercised is not evidence for a flagged change.
  - **HARNESS DEPENDENCY — the gate's flag-ON evidence depends on work outside G3.** Three
    pre-existing `sim-run.sh` defects (prd.md §7.6) mean the repo currently has **no way to run
    a flag-ON Maestro tier and know that it did**: `--flags` replaces rather than merges the
    seeded map; `--flags @file` is documented but unimplemented and fails **open** to
    `config/features.json`; and the handshake fetches the effective flag map into
    `report-dir/flags.json` but **never asserts it** (`sim-run.sh:61` claims flags round-trip,
    `:67-74` checks four other things), which is the root cause of the first two being silent.
    **The orchestrator is fixing the harness in a separate lane; G3 touches no `qa/` or
    `sim-run.sh` file.** This scope block assumes a flag-ON run will be verifiably flag-ON once
    that lands.
    **Fallback if the fix has not landed by the G3 gate run:** paste `report-dir/flags.json`
    into the TEST_LEDGER entry as manual proof that `league.picks_always_counted` was `true`
    for the flag-ON flows, and build the `--flags` payload from the profile's
    `<out>/<name>.manifest.json` `flags` object with the one key flipped — never a one-key
    object, never `@file`.
  - Also required green before merge: `bash mobile/scripts/testid-lint.sh` (CI),
    `cd mobile && npx tsc --noEmit` (CI; **baseline verified clean in this worktree**),
    `python -m pytest backend/tests -q` (CI),
    `node mobile/tests/check-picks-subset-invariance.js`,
    `node mobile/tests/check-member-entered-marker.js` **unmodified**.
- **Evidence:** append to `living-memory/TEST_LEDGER.md` (flows run, pass/fail, sim device, SHA)
  **and** write `qa/sim-runs/last-sim-run.json` (`{"date","sha","tier":1,"flows":[…],"result"}`).
  `githooks/pre-push` enforces the marker for any push to `main` touching `mobile/src`
  (install once per clone: `git config core.hooksPath githooks`).
- **Operator deviation from the matrix:** **none requested.** Tier 1 in full. The only
  deviation on the table is the §3 partial Maestro waiver for T1–T4, which is a *coverage*
  waiver, not a *tier* waiver — the tier still runs.
- **Express lane:** **not declared.** Full gates apply. Agents never self-select express.

## 6. Waivers and decisions — operator disposition (2026-08-10)

All five items decided. **"Aligned to all recommendations but ship with G3 flagged."**

| # | Item | Author's recommendation | Operator | Effect |
|---|---|---|---|---|
| W1 | **Analytics waived** — no event for the Picks opt-out | Waive; offer `rankings_filter_changed` as a separate scoped item | **ACCEPTED** | §1 stands as written. The offer remains open as a separate item |
| W2 | Flag or unflagged, given a reversal of shipped behavior on a live surface | **Unflagged**; rollback = revert the single commit | **OVERRIDDEN — ships behind a flag** | §2 rewritten: `league.picks_always_counted`, default OFF. New prd.md **R-0** (+ R-0.1 OFF semantics, R-0.2 atomicity, R-0.3 client absent-key) and **R-13** (four registration touches). New flow T7, three added T-S1 assertions, `docs/config-reference.md` moves from n/a to required |
| W3 | **Partial Maestro waiver** — T1–T4 cannot see picks because the hermetic seed has none | Option B: Tier A flows + structural check now, manual verification on a real league, seeding as a follow-up | **ACCEPTED** | §3 stands. Seeding `draft_picks` into `seed_ui_test_db.py` is a follow-up backlog item, not part of a polish item |
| D1 | **R-6 rule B (exit)** — should removing the last position clear the whole filter? Ruling silent | Keep rule B (protects the common gesture) | **ACCEPTED** | prd.md R-6 stands |
| D2 | `docs/cross-client-invariants.md` neutral-Picks rule is **missing** from the doc | Text proposed; orchestrator applies | **ACCEPTED** | prd.md §9.3 text stands as a proposal; orchestrator applies it at integration |

### 6.1 What the override changed, in one place

For a reviewer diffing against the pre-override version:

- **prd.md** — new R-0 (flag, OFF semantics, atomicity, absent-key/`LAUNCHED_FLAG_DEFAULTS`) and
  R-13 (four touches); §3 scoped to flag-ON with OFF pointing at R-0.1; flag-conditionality
  table in §5; §6 change surface grows from 11 rows to 15 plus the §6.1 `config/features.json`
  insert; T-S1 grows 9 → 16 assertions; new flow T7 and new manual control T-S6b; new §7.6 on
  flag forcing and its two traps; tier 1 reconfirmed with reasoning in §7.7.
- **scope.md** — §2 rewritten from "none proposed / unflagged" to the full flag spec;
  `docs/config-reference.md` moves n/a → required in §4; DECISIONS.md content grows to record
  the override; §3 and §5 gain flag-state coverage.
- **Unchanged by the override:** every behavioral requirement R-1…R-12, the §3/§4 specification,
  the copy strings, the guardrails, the §7.1 lint finding, and the §7.2 seeding analysis.

### 6.1b What Round 3 changed (Planner adversarial review — 6 blocking, all adopted)

The override above was Round 1.5; the Planner then reviewed the flagged PRD and returned
**"not implementable blind"** with six blocking objections. All ten (6 blocking + 4
non-blocking) were adopted after independent re-verification. Net effect on this scope block and
the contract:

- **prd.md** — `activeTotal` gains a **required no-default 4th parameter** threaded at **both**
  call sites (`:384` and `:433`); R-10's first guardrail amended to *mandate* the `:433` edit it
  previously forbade (it forbade the edit its own safety argument depends on, which would have
  reintroduced #208). New **R-0.4** ON→OFF reconciliation effect — the kill switch previously
  stranded an invisible `PICKS` in the filter at the moment it was pulled. R-0.2's "nine sites"
  replaced by an enumerated **G1–G14** table with three named gating symbols. R-8.2 given its
  own gate on the raw flag. R-6's pill invariant qualified. R-9 → **eight** comment sites.
  T-S1 → **16** assertions (13 and 14 close two verified escape hatches through which a build
  agent could pass the whole suite and still ship a half-gated screen). New manual drill
  **T-S6c**; T6 unmapped from R-5; T7's false assertion deleted; T4's caption corrected;
  T3's selector converted to an instruction. New **§10** implementability statement.
- **scope.md** — §2 atomicity row rewritten to the three-route model; §3 assertion count and T4
  caption; §4 LLD row now carries the **qualified** invariant; §5 gains the harness dependency
  and its fallback; §6.2 gains two rows.
- **Coverage honesty:** **R-5 and R-0.4 have no executable coverage** under Option B — both are
  source-pinned and manually verified, and both are recorded against the follow-up seeding item.

### 6.2 Carried forward — not blocking, worth a backlog line

| Item | Why |
|---|---|
| Seed `draft_picks` into the hermetic world | The QA world can exercise **none** of the five priced pick surfaces. Systemic, predates #293 (prd.md §7.2) |
| `sim-run.sh --flags @file` is documented but unimplemented, and fails **open** to `config/features.json` | Found while writing prd.md §7.6. A silent false-PASS generator for any flag-gated test |
| Wire the six `mobile/tests/check-*.js` structural checks into CI | They are the strongest regression pins in the repo and run only when someone remembers |
| **`sim-run.sh` cannot verify flag state** — `--flags` replaces the seeded map, `@file` is unimplemented and fails open, and the fetched `PINNED` map is archived but never asserted | **Orchestrator lane, in progress.** Affects every flag-gated flow in this batch and every future one; G3 is just the first consumer to notice. The `PINNED` assertion is ~5 lines and is itself the verification that any flag-gated gate run is meaningful |
| R-5 and R-0.4 have **no executable coverage** until the seed carries picks | Both are source-pinned (T-S1 assertions 8, 16) and manually verified (T-S6, T-S6c), but the follow-up seeding item should know they are waiting on it |
| The #208 PRD specced a Maestro flow on this screen that was never created | Pre-existing unfulfilled commitment; G3's flows do not collide with it |
