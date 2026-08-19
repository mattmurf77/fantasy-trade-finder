# Feature Scope — "Avoiding" positions (#360 / #361)

**Date:** 2026-08-19
**Entry point:** feedback #360 + #361 (jonbonjourvi, TradesHome, v1.15.0)
**Builder:** Author agent (session `wt-jon`), from `plan.md` in this folder
**Operator sign-off on waivers:** yes — the orchestrator ruled Q-A1…Q-A7 before authoring; every waiver below cites its ruling

> **Gate posture: FULL gates, not express.** This adds a column to
> `league_preferences` — the CLAUDE.md bright line. Every section below is
> answered; nothing is left silent.
>
> Base sha for every `file:line` in this document: `f68eddd`
> (`origin/main` + one commit). All citations re-verified this session
> against the files, not against prior prose — the Planner's own note that
> line numbers drift proved correct in five places (see §6).

---

## 1. Analytics scope

- [ ] **(a) New events specced** — no.
- [x] **(b) Existing events cover it.**
  - `outlook_saved` (registered `backend/analytics_taxonomy.py:412`; property
    allow-map `frozenset({"source"})` at `:1122`) fires once per sheet session
    at the first preference write — `mobile/src/components/TradeDnaSheet.tsx:452-457`,
    inside `queueDnaSave`, which is the single choke point every Chasing /
    Shopping / Avoiding tap passes through. Adding the Avoiding row adds no new
    write path, so the event's meaning ("the user configured their trade DNA in
    this sheet session") is unchanged and already covers the write moment.
  - **Adoption** ("how many users avoid a position, and which?") is answered by
    querying `league_preferences.avoid_positions` directly. It is durable stored
    state, not an ephemeral interaction; an event would be strictly redundant
    for that question and would double-count under #236 autosave, which POSTs on
    every tap.
- [ ] **(c) WAIVED** — n/a, (b) applies.

**Explicit waiver for the funnel question (orchestrator ruling Q-A6 — "no new
event, but write the waiver").** What was considered and rejected: a
`positions_avoided` (or `dna_avoid_toggled`) client event carrying
`{positions, action}`, which would let analytics attribute like-rate and
deck-abandon deltas to Avoiding specifically. **Rejected for this wave** because:

1. The question it answers ("does avoiding change like-rate?") needs a
   *cohort* comparison, and the cohort is definable from stored state joined to
   the existing `deck_card_viewed` / swipe spine — the event adds no
   information the join lacks.
2. Registering a new name is not boilerplate here and the cost is real: the
   client registry is **default-deny behind a 200** (`analytics_taxonomy.py:419-424`),
   so an unregistered name is silent, unrecoverable loss with a success-shaped
   response; and `NON_INTENT_EVENTS` (`analytics_queries.py:63`) is the
   *deny-list* half of an intent **default-allow** rule, so a new name is
   intent-by-default and would step-change DAU/WAU at the emitter's ship date.
   That is exactly the P0 seam documented in `analytics_queries.py:67-73`.
3. A preference toggle *is* a deliberate user action, so if the event is ever
   added it belongs in the intent class — i.e. correctly **absent** from
   `NON_INTENT_EVENTS`. Recording that now so a future adder does not read the
   omission as an oversight.

If the operator later wants funnel attribution, the constraints in (2) and (3)
are the spec, and registration must land in the **same commit** as the emitter.

---

## 2. Schema & flag scope

**New columns**

| Table | Column | Type | Default | Migration |
|---|---|---|---|---|
| `league_preferences` | `avoid_positions` | `TEXT` (JSON array) | declared `default="[]"`; **existing rows read NULL** | additive entry in `_migrate_db()`'s `migration_cols` (`backend/database.py:2432`…`:2583`), beside the two existing sibling rows at `:2445-2446` |

`ALTER TABLE … ADD COLUMN` is issued without a SQL `DEFAULT`
(`backend/database.py:2590`), so every pre-existing row reads `NULL`.
That is correct and needs **no backfill**: `load_league_preference`'s
`_parse_positions` returns `[]` for any falsy raw value
(`backend/database.py:8559-8560`). `docs/data-dictionary.md` §`league_preferences`
(`:650-661`) gains one row.

**New feature flags**

| Key | Default at ship | Kill-switch semantics | Graduation criterion |
|---|---|---|---|
| `trade.avoid_positions` | **`true`** | OFF ⇒ the engine never reads the column, every generation path is byte-identical to pre-#360, and the sheet renders no Avoiding row. The column keeps its data in both states, so flipping the flag back on restores every user's saved set. | Already graduated at ship — this is a user-requested feature, so the flag is a kill switch, not a dark launch. Remove the key no earlier than one full TestFlight cycle after ship. |

Registration: `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS`
(the tuple opened at `:47`; `"trade.presentment_rules"` at `:799` is the
comment-block template) + `docs/config-reference.md`.
Mobile: add `'trade.avoid_positions': true` to `LAUNCHED_FLAG_DEFAULTS`
(`mobile/src/state/useFeatureFlags.ts:45`) per the #115 fail-open lesson
documented at `:36-44` — and note the rule stated at `:62-70`: a key present in
only one of `features.json` / `LAUNCHED_FLAG_DEFAULTS` **disagrees with itself
across the first two paints**. Both files carry `true`; flipping it is a
two-file edit.

**New env vars / `model_config` keys: none.**

This is a deliberate dividend of choosing a hard pool exclusion over reviving the
dormant `pos_conflict_penalty` multiplier (`backend/database.py:2187`,
`backend/trade_service.py:98`) — see PRD D-093. Consequences worth stating
because a reviewer will look for them:

- **No edit to the knob-inventory golden** at
  `backend/tests/test_bakeoff_arm_a_golden.py` (the `model_config` key-name
  inventory), which is the test that would otherwise gate a new knob.
- No new tuning surface to calibrate, and no measured default to defend — §12 R1
  of `plan.md` explains why the measurement corpus is not reliably available.
- `pos_conflict_penalty`, `pos_acquire_bonus` and `pos_tradeaway_bonus` stay
  **untouched and dormant**. Pre-existing dead code is named, not deleted
  (coding-guidelines §3 surgical changes).

**API surface:** `GET` and `POST /api/league/preferences`
(`backend/server.py:15381`, `:15447`) each gain one additive array field.
Full contract pinned in `lld-delta.md` §3 — that section, not this one, is what
the backend and mobile build agents code against.

---

## 3. Evidence scope

D-056 (2026-08-15) retired Maestro and the simulator entirely. No flow
authoring, no flow execution, no `screens/` captures. The four rows below are
the whole verification story, plus CI.

- [x] **Structural guard:** `mobile/tests/check-avoid-positions.js`, plus
      `"test:avoid-positions": "node tests/check-avoid-positions.js"` in
      `mobile/package.json`. Dependency-free plain node parsing the real TSX with
      the project's own TypeScript, same harness family as
      `mobile/tests/check-dna-side-order.js` and `check-league-candidates-300.js`.
      **Assertions and the sabotage each detects are enumerated in `prd.md` §7.2.**
      The load-bearing one: `toggleDnaPos` clears the tapped position from
      Chasing but **not** from Shopping when side is `avoid` (the R-4 asymmetry),
      and the autosave payload carries all four keys at all six sites (R-11).

      > **Correction to CLAUDE.md, worth carrying back.** CLAUDE.md states the
      > `mobile/tests/check-*.js` suites "gate nothing yet". That is **stale** as
      > of `.github/workflows/ci.yml`: the `mobile-typecheck` job runs
      > `for f in tests/check-*.js; do node "$f" || exit 1; done`, so a new
      > `check-*.js` is live in CI the moment the file exists — no npm script
      > needed. The npm script is added anyway for local ergonomics and for
      > consistency with the 60 existing suites.

- [x] **Unit tests:** new `backend/tests/test_avoid_positions.py`. Twelve tests,
      each mapped to a requirement and each named with the sabotage that turns it
      red — `prd.md` §7.1. No existing pytest file is modified.
- [x] **Code-walk proof:** `docs/feedback/items/360-avoiding-positions/code-walk.md`,
      written by the build agent at the end of the backend wave. It must be a
      `file:line`-cited trace showing that **all seven** receive-side seams
      (`lld-delta.md` §4) plus **both** preference loaders are on the filtered
      path, and that the two exempt seams (eveners, `trade_gen_v2`) are exempt by
      the stated rule rather than by omission. This replaces what would once have
      been a simulator capture.
- [x] **Manual TestFlight checklist:** `prd.md` §7.3. Twelve numbered steps with
      expected results, written as a regression suite because it is now the only
      runtime evidence mobile gets. Run by the operator; outcome logged in
      `living-memory/TEST_LEDGER.md`.
- [ ] **WAIVED** — nothing waived in this section.

**`testID`s added:** `dna.avoid.qb`, `dna.avoid.rb`, `dna.avoid.wr`,
`dna.avoid.te`, `dna.avoid.picks` — mirroring the shipped
`dna.chase.<tid>` / `dna.shop.<tid>` shape at
`mobile/src/components/TradeDnaSheet.tsx:679` and `:698`. Must pass
`mobile/scripts/testid-lint.sh` (still in CI).

**Screen captures: waived, and they must not be used as a "before".**
`screens/` is frozen at 2026-08-11 under D-056 and the two Trade-DNA frames are
provably stale — `plan.md` §10.2 shows the captured POSITIONS block rendering
**four** chips per row while `DNA_POSITIONS`
(`mobile/src/components/TradeDnaSheet.tsx:75-81`) defines **five**. No new
capture can be produced. Any design review reads the source.

---

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | Rows for `GET`/`POST /api/league/preferences` (`:454-455`) restated to name `avoid_positions`, its flag-independence, and the normalize-and-drop write contract. |
| `docs/config-reference.md` | **updated** | New flag `trade.avoid_positions` — default, both flag states, kill-switch semantics. Explicit "no new `model_config` keys" line so a reader does not go looking. |
| `docs/data-dictionary.md` | **updated** | `league_preferences` table (`:650-661`) gains the `avoid_positions` row, with the NULL-reads-as-`[]` note. |
| `docs/glossary.md` | **updated** | "Positional preferences" (`:116`) currently names **two** lists and calls them a hard filter on candidate packages. It must name **three**, and record that Avoiding is a *receive-pool exclusion at source*, not a package gate — a materially different mechanism with a stronger guarantee. |
| `living-memory/LLD.md` | **updated** | New convention: *negative receive constraints are applied at pool construction, never as a package gate, and are therefore structurally un-relaxable.* Positions join players (#163) under that rule. |
| `docs/architecture.md` | **n/a because** no module wiring or data-flow change: one column, one flag, one predicate threaded through call signatures that already carry its two siblings adjacently. No new module, no new route, no new client. |
| `living-memory/HLD.md` | **n/a because** same reason — see `hld-delta.md`, which states it in one line rather than leaving the row blank. |
| `docs/cross-client-invariants.md` | **updated** | The "Mirror locations" table (`:398-404`) gains a row for the backend's new `_pos_for_avoid` re-derivation of pick identity. It is a **backend** re-derivation that calls the canonical `is_pick_asset` (`backend/trade_service.py:1549-1557`) rather than re-implementing it, so its Status reads "reads the canonical predicate" — but the register exists precisely because unregistered re-derivations drifted before (#222, the 2026-08-18 B3 sweep), so it gets a row. |
| ADR | **n/a because** no architectural decision of ADR weight. Two `DECISIONS.md` entries carry the non-obvious choices instead. |
| `living-memory/DECISIONS.md` | **updated ×4** — **D-093** (hard pool exclusion over reviving `pos_conflict_penalty`), **D-094** (Shopping + Avoiding co-selectable; Chasing ⊕ Avoiding exclusive), **D-095** (Avoiding applies exactly where `not_interested` applies; an exclusion beats a pin), **D-096** (the never-relaxed guarantee is structural — write it down anyway). Next free id verified this session: max is D-092. Full rationale for each is in `prd.md` §2; the DECISIONS entries should be its condensed form, not a pointer. |
| `living-memory/OPEN_QUESTIONS.md` | **updated ×1** — **Q-026**, the `trade_gen_v2` preference gap. (Written as Q-024; renumbered 2026-08-19 when `origin/main` advanced and took Q-024 + Q-025 — max is now Q-025.) Headline is the **pre-existing Chasing/Shopping gap**, not Avoiding (orchestrator ruling Q-A1). Wording constraint in `prd.md` §5.1. |
| `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md` | **updated at ship** | Standard write-back. TEST_LEDGER names the pytest file, the `check-*.js` suite, the code-walk doc, and the operator's checklist outcome. |

---

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (`python -m pytest backend/tests -q`),
  `mobile-typecheck` (`npx tsc --noEmit` **and** the `tests/check-*.js` loop —
  see the §3 correction), `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`).
- **Evidence recorded** in `living-memory/TEST_LEDGER.md`: the twelve pytest
  cases and what each sabotage proved, the `check-avoid-positions.js` assertions,
  the code-walk doc path, and the operator's TestFlight outcome.
- **TestFlight verification:** yes, a checklist was written (`prd.md` §7.3).
  Ship is not complete until the operator runs it and the outcome is logged.
- **`githooks/pre-push`** still enforces the retired simulator marker
  (`qa/sim-runs/last-sim-run.json`). Under D-056 `FTF_SKIP_SIM_GATE=1` is the
  standing posture — set it, and note in the TEST_LEDGER entry that the D-056
  evidence bundle above ran in its place.
- **Express lane declared by the operator?** **No.** This is the CLAUDE.md
  bright line (schema change + API contract change + a new feature-flag surface).
  Full gates.

---

## 6. Re-verification of `plan.md`

Every `file:line` in `plan.md` §3–§11 was re-read against sha `f68eddd`.
**The Planner's citations hold** — the six `not_interested` seams, the two
loaders, the signature chain, the `_positions_ok` duplication, the `targeted`
predicate, the never-relaxed docstring, the `DNA_POSITIONS` five-chip finding
and the stale-capture proof all resolve to within a line. Nothing in this
section is a nitpick about numbering.

**Four substantive corrections**, all of which change what a build agent must do:

| `plan.md` said | Actually at sha `f68eddd` |
|---|---|
| empty-state toast branch is `TradesScreen.tsx:6274-6293` | **Wrong region.** `:6276-6300` is the #330 scoped-empty **Card**. The intent-aware **toast** that R-9 must extend is at `:1509-1532`, inside the generate mutation's `onSuccess` (`intentCopy` map at `:1519-1523`, `setToast` at `:1524-1532`). |
| `TradesScreen.tsx` needs "exactly two narrow regions" (§11.1) | **Four.** §11.1 missed `confirmOutlookMutation` (`:1017-1023`) and `handleOutlookSubmit` (`:4443-4456`, still live via `onSubmit={handleOutlookSubmit}` at `:4574`). Both construct a `LeaguePreferences` object literal and will fail `tsc --noEmit` the moment the field is required. The file-ownership note in §11.2 must say four regions, not two. |
| the asset-ideas route "does its own pref load and pass-through; mirror both halves" (§4.1) | **It does not.** `backend/server.py:11020-11073` loads **asset** preferences only (`load_asset_preferences`, `:11033`) and passes no positional prefs at all. Wiring Avoiding there is **new** plumbing — a fresh `load_league_preference` call — not a mirror of an existing one. Still in scope (`prd.md` R-6), but it is more work than §4.1 implies. |
| `trade_gen_v2.py` "reads no positional preferences at all" (§8) | True for *positional* prefs — but it **does** apply `not_interested_ids` (`backend/trade_gen_v2.py:509`, applied at `:530`) and `untouchable_ids` (`:533`). Since this feature's whole architecture is "Avoiding is the positional twin of `not_interested`", that materially weakens the Q-A1 rationale. Escalated in `prd.md` §5.1; the ruling still stands, with a guardrail attached. |

Three further findings not in `plan.md` at all, all now specified:

- **An exclusion beats a pin — and it is already the house rule.**
  `backend/trade_service.py:4929-4930` states it in the consensus path's own
  comment: *"the target re-add below iterates this filtered list too, so an
  exclusion always wins."* The v3 path is built the same way — `known_opp` is
  filtered at `:359-361` and both the `pinned_recv_set` re-add (`:407-410`) and
  the `target_ids` re-add (`:412-415`) iterate that already-filtered list. This
  settles a question `plan.md` never raised (what happens when a user pins a
  receive target whose position they avoid) **by precedent rather than by
  invention** — see `prd.md` D-095 and R-8.

- **`backend/server.py:15483` defines `valid_positions = {"QB","RB","WR","TE"}`
  and never uses it.** Dead since it was written — no reference anywhere in the
  route. It also omits `PICK`, which the shipped client *does* send
  (`DNA_POSITIONS` includes `{ key: 'PICK' }`). Left untouched (surgical
  changes, and fixing it would newly reject live client payloads); the new field
  gets its own real normalization instead — `lld-delta.md` §3.3.
- **The legacy v1 generator `_generate_for_pair` (`backend/trade_service.py:5094`)
  has its own positional hard filter at `:5460-5470` and applies neither
  `untouchable_ids` nor `not_interested_ids`.** It is unreachable in production
  (`trade_engine.v2 = true`, `config/features.json`). Avoiding is **out of scope**
  there, by exactly the rule that keeps eveners out — `prd.md` §5.2.
