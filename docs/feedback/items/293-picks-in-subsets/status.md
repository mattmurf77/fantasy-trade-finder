# Status — #293 / #294 · G3 mobile build

- **Date:** 2026-08-10 · **Lane:** G3 (mobile build agent)
- **Branch:** `worktree-agent-a70747a176183674d`, worktree
  `.claude/worktrees/agent-a70747a176183674d`
- **Base:** `origin/main` @ `16b1dcb`. The PRD cites `7cea1fa`; `16b1dcb` is four
  commits later and **byte-identical on every owned path**
  (`git diff 7cea1fa origin/main -- mobile/src/screens/LeagueSummaryScreen.tsx
  backend/feature_flags.py backend/tests/fixtures/flags/release.json
  mobile/scripts/testid-lint-allow.txt` → empty). Every PRD line citation was
  re-checked and resolved to the cited construct.
- **Contract:** [prd.md](prd.md) R-0…R-13. **No deviations.** Two findings that
  the PRD got wrong are recorded in §5 below; neither changed the behavioral spec.
- **State: code complete, verification green, NOT merged, NOT pushed.**

---

## 1. ⚠️ Read this first — one coupled edit the orchestrator MUST apply

**`backend/tests/test_seed_ui_test_db.py::test_release_flags_mirror_features_json`
is RED on this branch, by design, and the orchestrator's `config/features.json`
insert is what turns it green.**

That test asserts `backend/tests/fixtures/flags/release.json` is an **exact
mirror** of `config/features.json` (non-`_`-prefixed keys). R-13 touches 2 and 3
are therefore **atomically coupled** — they cannot land in separate commits.

The PRD says the opposite. scope.md §3 states *"Existing
`backend/tests/test_seed_ui_test_db.py` must stay green unmodified — verified it
will, since the new key is not an inventory flag."* The `INVENTORY_FLAG_KEYS`
reasoning is correct as far as it goes; it just checked the wrong test. The
mirror assertion at `test_seed_ui_test_db.py:113` is not an inventory check.

**Why the release.json entry stays in this branch rather than being dropped.**
It is an owned-path deliverable (R-13 touch 3) and this is the safe handoff: the
orchestrator applies **one** documented edit and the suite goes green. Drop it
and that same one edit turns the suite red the *other* way (features.json would
carry one more key than release.json), and fixing it would require the
orchestrator to reach into G3's owned path.

**Proven locally, then reverted:** with the §3 features.json insert applied,
`python3 -m pytest backend/tests/test_seed_ui_test_db.py -q` → **31 passed**.
`config/features.json` is untouched in this branch (`git status` clean for it).

---

## 2. Files touched

| File | Change |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | The whole behavioral change — G1–G14, the flag read, the `activeTotal` 4th parameter, the `BarColumn` prop, eight comment sites |
| `backend/feature_flags.py` | **One** `FLAG_KEYS` tuple entry (+ its comment). `DEFAULT_FLAGS = {key: False for key in FLAG_KEYS}` gives the default automatically. Nothing else in the file |
| `backend/tests/fixtures/flags/release.json` | One line: `"league.picks_always_counted": false` — see §1 |
| `mobile/scripts/testid-lint-allow.txt` | The five `league-summary.*` globs from PRD §7.1, with the constructing file noted per the file's own convention |
| `mobile/tests/check-picks-subset-invariance.js` | **New** — T-S1, the 16-assertion structural check |
| `mobile/package.json` | One script: `test:picks-subset-invariance` |
| `mobile/.maestro/flows/league/01…04.yaml` | **New directory**, four flows (T1–T7) |
| `docs/feedback/items/293-picks-in-subsets/status.md` | This file |

**Not touched, deliberately:** `config/features.json`, `docs/config-reference.md`,
`docs/cross-client-invariants.md`, `docs/api-reference.md`, `living-memory/*`,
`mobile/src/*/CLAUDE.md` (orchestrator-owned); `qa/**` and
`mobile/scripts/sim-run.sh` (separate harness lane); every G1/G2 path.

---

## 3. Verification evidence

| Check | Result |
|---|---|
| **T-S4** `cd mobile && npx tsc --noEmit` | **exit 0, clean.** `node_modules` was absent in this worktree; installed with `npm ci` (796 packages), **not** symlinked from the main checkout |
| **T-S3** `bash mobile/scripts/testid-lint.sh` | **exit 0** (`testid-lint OK`) |
| **T-S1** `npm run test:picks-subset-invariance` | **exit 0** — all 16 assertion groups (71 individual assertions) PASS |
| **T-S2** `node mobile/tests/check-member-entered-marker.js`, **unmodified** | **exit 0** — surface 5/5 still passes, as V4 predicted |
| Other structural checks (`espn-cookies`, `league-unlocks`, `feedback-badge`, `session-rerank`, `mock-mode-marker`) | **all exit 0** |
| `python3 -m pytest backend/tests/ -q` | **2297 passed, 1 failed, 1 skipped** in 283.68s. Baseline was 2297 passed, 1 skipped. The single failure is `test_release_flags_mirror_features_json` — §1. No other test moved; total collected is unchanged |
| Maestro | **NOT run.** Other agents are active and simulator contention has broken prior runs. Flows are authored and their selectors verified statically |

### 3.1 Discrimination proof — the assertions can fail

Required by the build brief. Each mutation was applied to a copy, verified, then
reverted; the file is back to its verified state (`tsc` 0, T-S1 0).

| Mutation | `tsc --noEmit` | T-S1 |
|---|---|---|
| **Escape hatch 1 (O-1).** Give `activeTotal`'s 4th param `= false` and un-thread the `otherByTeam` call site — the #248 overlay half-gating that reintroduces #208 | **exit 0 — SILENT.** Exactly as the PRD predicts: a defaulted parameter lets the unthreaded caller compile | **FAIL ×2**: `13b — activeTotal call site 2 passes picksAlwaysCounted as its 4th argument: saw: activeTotal(tc, subset, posFilter)` and `13c — activeTotal's 4th parameter has NO default and is not optional` |
| **Escape hatch 2 (O-2).** `<BarColumn picksAlwaysCounted={false} />` — the literal that half-gates the bar | **exit 0 — SILENT.** The prop exists and is a boolean | **FAIL ×1**: `14c — <BarColumn picksAlwaysCounted={picksAlwaysCounted}> is a BARE identifier: saw: {false}`. **Assertions 1, 2 and 3 all still PASSED** — which is precisely the O-2 finding, and why 14 is the only mechanical link between the two halves of atomicity |
| **Miss one G-row.** Revert G12 `shownBase` alone — the `segSum` lie: the bar grows by `P` while the four position segments stretch to fill it | **exit 0 — SILENT** | **FAIL ×2**: `3 — G12 shownBase branches on its own picksAlwaysCounted binding` and `7e — shownBase's unfiltered condition is <flag prop> \|\| subset === 'all': saw: subset === 'all'` |

**Reading:** all three defects are invisible to `tsc`, and two of them are
invisible to any screenshot. T-S1 catches every one.

### 3.2 Blocker C1 re-proven — the allowlist entries are load-bearing

`testid-lint.sh` with the five new globs stripped out: **exit 1**, ten missing
ids (`league-summary.{subset,roster-subset}.{all,starters,bench}`,
`.{posfilter,roster-posfilter}.{all,rb,picks}`). Restored → `testid-lint OK`.

Two honest notes:
- Only **four** of the five globs are load-bearing against the flows as written.
  `league-summary.bar.*` is not currently needed, because the flows select bars
  with the regex `league-summary.bar..*`, whose static prefix the lint's grep
  does resolve. It is kept because PRD §7.1 names all five and because a future
  flow using a concrete `user_id` would need it.
- A bare `league-summary.*` was **deliberately not** added — it would
  blanket-exempt the five static ids (`roster-picks`, `filter-caption`,
  `roster-close`, `avg-line`, `league-home`) the lint currently checks for real.

---

## 4. Requirement → implementation → test

Line numbers are post-change. G-IDs are R-0.2's enumeration.

| Req | Implemented | Test |
|---|---|---|
| **R-0** flag exists, one read site | **`:430`** `const picksAlwaysCounted = useFlag('league.picks_always_counted')`, placed with `hasPicks` so every consumer is in scope | T-S1 1, 1b, 1c |
| **R-0.1** OFF is byte-identical | Every gated expression keeps its current branch verbatim on the OFF arm | T-S1 4b, 5a, 5b, 6c, 7c, 7g, 8b, 9b, 12b, 15d · Maestro T7 · manual T-S6b |
| **R-0.2** atomicity | One read; three gating symbols (body identifier, `activeTotal` param, `BarColumn` prop); no `useFlag` in either module-scope function | T-S1 1, 2, 3, **13**, **14** + §3.1 |
| **R-0.3** absent key ⇒ false | Nothing added to `LAUNCHED_FLAG_DEFAULTS` — verified absent | grep; `useFlag` is `!!s.flags[key]` |
| **R-0.4** ON→OFF reconciliation | **`:458-466`** `useEffect`, OFF branch only, modelled on the `startersAvailable` precedent at **`:416-418`** | T-S1 **16a–16e** · manual **T-S6c** (no executable coverage — §7.2) |
| **R-0.5** graduation | Not done here — this lands dark. Checklist relayed in §6 | — |
| **R-1** unfiltered value + picks (G1) | `activeTotal` empty-filter branch **`:309-312`**; required no-default 4th param **`:307`**; **both** call sites threaded (**`:480`** bars, **`:537`** overlay) | T-S1 4a, 4b, 4c, **13a–13d** |
| **R-2** filtered value + picks (G2) | `activeTotal` `'PICKS'` branch **`:315-321`** | T-S1 5a, 5b, 5c |
| **R-3** bar composition (G12, G13) | `BarColumn` `shownBase` **`:1449-1454`**, `segValue` **`:1460-1465`**; prop passed **`:987`** (bare identifier), destructured **`:1431`**, declared **`:1438`** — required, no `?`, no default | T-S1 3, 7a–7g, **14a–14f** |
| **R-4** pill + legend in every subset (G3) | **`:439`** `showPicksKey` | T-S1 6a, 6b, 6c · Maestro T1 |
| **R-5** subset switch never mutates the filter (G6) | **`:696-706`** `switchSubset`, `setPosFilter` under `!picksAlwaysCounted` only | T-S1 8a, 8b · **no executable coverage** (§7.2) · manual T-S6 |
| **R-6** filter state machine, rules A + B (G4, G5) | **`:671-685`** `togglePos` (rule A **`:680`**, rule B **`:681`**); qualified pill invariant in the comment at **`:665-670`** | T-S1 3 · Maestro T3 (Tier B) |
| **R-7** drill Draft-capital group (G11) | **`:1186-1188`** | T-S1 9a, 9b, 9c · Maestro T2 (Tier B) |
| **R-8.1** subset prefix (G8) | **`:928-937`**, via `picksInView` (**`:444-445`**) | T-S1 3, 10a, 10b |
| **R-8.2** filtered hint (G9) | **`:943`**, gated on the **raw flag**, `filterPosLabel` vs `[...posFilter].join(' + ')` | T-S1 **15a–15e** · Maestro T4 |
| **R-8.3** drill subline (G10) | **`:1091-1093`**, via `picksInView` | T-S1 3, 10a |
| **R-9** eight comment sites | **`:53-62`** header filter block · **`:167-173`** `FilterKey` · **`:266-302`** `activeTotal` · **`:432-437`** `showPicksKey` · **`:687-695`** `switchSubset` · **`:1175-1185`** drill group · **`:1346-1354`** `PosFilterPills` · **`:1406-1422`** `BarColumn`. Each states the new rule **and** names the flag. Site 3 (`activeTotal`) additionally carries the §4 non-partition consequence and the R-6 pill invariant **in its qualified form**. The judgment-call site **`:68-73`** (subset recompute) was **extended**, not blocked on | grep audit in §4.1 |
| **R-10** guardrails | `teamPosRank` / `playerPosRank` untouched; `total_value_label` gate unwidened; `BarColumn`'s `subset` prop **not** deleted; `coreTotal`'s `:227-228` "players only, no picks" comment **not** edited (still true); no backend logic change. The one mandatory exception — threading `activeTotal` at the overlay call site — **is made** | T-S1 11, 12a, 12b, 12c, **13** |
| **R-11** no-picks leagues untouched | `picksInView` and rule A both gated on `hasPicks`; zero-value segments already skipped | T-S1 10b · Maestro T5 (Tier A, runs today) |
| **R-12** lint green | Five allowlist globs | T-S3 + §3.2 |
| **R-13** four registration touches | 1 ✅ `feature_flags.py` · 2 ⏳ orchestrator · 3 ✅ `release.json` (**coupled to 2**, §1) · 4 ⏳ orchestrator (`docs/config-reference.md`) | pytest, §1 |

### 4.1 Comment-site audit

`grep -n "neither starters nor bench\|All subset is active\|only exists in the
All\|All subset only\|in the All view\|would zero bars"` returns **six** hits,
and every one now sits inside a sentence scoping it to the flag-OFF branch
("the shipped pre-#293 rule", "when that flag is OFF", "OFF, only in the All
view", "a REVERSAL of the shipped … rule"). No site asserts the retired rule as
current behavior. All eleven `league.picks_always_counted` / `#293` comment
mentions are listed by `grep -n "picks_always_counted"`.

---

## 5. Where the PRD was wrong (two findings, neither changing the spec)

1. **scope.md §3 / §7.2: "`test_seed_ui_test_db.py` must stay green unmodified."**
   False — `test_release_flags_mirror_features_json` couples R-13 touches 2 and 3.
   Full write-up and remediation in §1. **This is the one thing the orchestrator
   must not miss.**
2. **PRD §7.4 T3's open selector question — closed as far as it can be here.**
   Installed Maestro is **2.5.1**, read from
   `/opt/homebrew/Cellar/maestro/2.5.1`. `maestro --version` still **cannot be
   executed on this machine** — it dies with *"Unable to locate a Java
   Runtime"*, the same failure the PRD author hit, and `/usr/libexec/java_home`
   confirms no JRE. So: `selected:` **is** a documented Maestro 2.x
   element-matcher property and the pills do expose
   `accessibilityState={{ selected }}`, so T3 uses the mechanical assertion
   **and** keeps the screenshots. What is **not** verified is that React
   Native's `accessibilityState.selected` reaches `XCUIElement.isSelected`
   through the iOS driver — this lane could not run Maestro and was forbidden
   from holding the simulator. The two-branch fallback and the version checked
   are recorded in `02-picks-in-position-filter.yaml`'s header so the next
   author does not re-litigate it.

**No deviations from the contract.** Every G-row is implemented as specified,
both `activeTotal` call sites are threaded, the `BarColumn` prop is required and
passed as a bare identifier, R-8.2 gates on the raw flag, and R-0.4 exists.

---

## 6. What the orchestrator must apply

| # | File | Action |
|---|---|---|
| **1** | **`config/features.json`** | **Required, and coupled to `release.json` — see §1.** The `_comment_league_picks_always_counted` + `"league.picks_always_counted": false` pair from **prd.md §6.1, verbatim**, in the `league.*` neighbourhood after `"league.power_rankings": false`. Verified locally that this single insert turns `test_seed_ui_test_db.py` green (31 passed) |
| 2 | `docs/config-reference.md` | R-13 touch 4 — new flag-table row. Text in scope.md §4 |
| 3 | `docs/cross-client-invariants.md` | The neutral-Picks append from **prd.md §9.3**, into the "Position color tokens (segmented progress bar)" section. Still only a proposal; the code at `:159-162` cites a rule the doc does not contain |
| 4 | `living-memory/DECISIONS.md` | New entry (next id = `max + 1`, **grep first**). Content per scope.md §4: the ruling verbatim; the four rejected alternatives; the §4 non-partition consequence; R-6's operator-silent zone; **and the flag override** — the Author recommended unflagged and the operator overrode it because a reversal of shipped behavior on a live surface gets a kill switch |
| 5 | `living-memory/LLD.md` | Retire *"picks are neither starters nor bench"*; record the pill invariant **in its qualified form** (scope.md §4 gives the exact sentence — the unqualified version is false for an empty filter) |
| 6 | `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `docs/feedback/items/INDEX.md` | Append at ship. TEST_LEDGER must record **each flow's flag state** |
| 7 | `mobile/src/screens/CLAUDE.md` | Optional — the `LeagueSummaryScreen` row still reads "draft-capital section"; no longer strictly wrong, but the subset-independence is worth a clause |

**Not an orchestrator action, but do not forget it (R-0.5 graduation):** flipping
the flag on means setting `config/features.json` to `true` **and** adding
`'league.picks_always_counted': true` to `LAUNCHED_FLAG_DEFAULTS`
(`mobile/src/state/useFeatureFlags.ts:44-51`) **in the same change**. Flipping
only the server value leaves first-boot users on the old behavior until their
first successful `/api/flags` fetch — a silent, hard-to-reproduce split. The key
is correctly **absent** from that map today.

---

## 7. QA checklist

### 7.1 Sim-gate tier 1 — automated

Change class "Mobile screen / navigation / state change". **The flag does not
lower the tier; it adds to it — both states must be exercised.** No express
declaration was made, and a feature-flag surface is on CLAUDE.md's bright line.

| Flow | Flag | Tier | Run in the gate? |
|---|---|---|---|
| `flows/smoke/01…11` (all 11) | **OFF** (default) | 1 | **Yes** — these are the byte-identity evidence for R-0.1 |
| `flows/rookie/d1`, `d2`, `r5` | OFF | 1 | **Yes** — the only other consumers of this screen's ids |
| `flows/league/04-picks-flag-off.yaml` (T7) | **OFF** | A | **Yes** — no flag forcing, no pick data needed |
| `flows/league/03-no-picks-league.yaml` (T5, T6) | **ON** | A | **Yes** — proves the reversal is correctly gated on `hasPicks` |
| `flows/league/01-picks-in-subsets.yaml` (T1, T2) | ON | **B** | **No** — `--exclude-tags picks`. Waiver §7.3 |
| `flows/league/02-picks-in-position-filter.yaml` (T3, T4) | ON | **B** | **No** — `--exclude-tags picks`. Waiver §7.3 |

Log in `living-memory/TEST_LEDGER.md` **with each flow's flag state**; write
`qa/sim-runs/last-sim-run.json`.

**Forcing the flag ON — two verified `sim-run.sh` traps, both silent false-PASS
generators. G3 touched no `qa/` or `sim-run.sh` file; work around them by hand:**
1. `--flags` **REPLACES** the seeded map, it does not merge. Build the payload
   from the profile's `<out>/<name>.manifest.json` `flags` object with this one
   key flipped — **never** a one-key object, or you silently revert all thirteen
   of `standard`'s other overrides.
2. `--flags @file` is documented but **unimplemented** and fails **open** to
   `config/features.json` (flag OFF, flows assert old behavior, exit 0). **Use
   inline JSON.**
3. Root cause of both being silent: the handshake fetches the effective map to
   `report-dir/flags.json` and **never asserts it**. Until the harness lane
   lands its fix, **paste `report-dir/flags.json` into the TEST_LEDGER entry** as
   manual proof the flag was actually `true`.

### 7.2 Manual passes — required

| # | Pass | What to do | Gates |
|---|---|---|---|
| **T-S6** | Real Sleeper dynasty league, **flag ON** | Walk §3.1 rows 2, 3, 5, 9 and §3.2 rows 11, 12, 14. Screenshot each into this folder. Confirm: Starters/Bench bar values exceed their pre-change values by **exactly** `picks.value`; the All value is unchanged; the neutral Picks segment sits at the **base**; the hint reads *"Best starting lineup + draft capital."*; the drill subline reads *"… starter + picks value"* | R-1…R-7 (the only coverage T1–T4 would have given) |
| **T-S6b** | **Same league, flag OFF** — the paired control | Indistinguishable from the shipped 1.11.0 build: no Picks pill or legend in Starters/Bench, no Draft-capital group outside All, *"Best starting lineup only. "*, and the filtered hint still prints the **raw `PICKS` enum in tap order**. Screenshot the same seven views for a side-by-side. **The only test of flag-OFF with real pick data** — T7 cannot see it, the seed has no picks | **R-0.1** |
| **T-S6c** | **The kill-switch drill — a §9.1 done-criterion** | Flag **ON**: go to Starters and leave `PICKS` in the filter (rule A's default). Now flip `league.picks_always_counted` to `false` server-side and force a client revalidate (background→foreground past the 30-min throttle, or cold start). **Pass:** the chart returns to the `origin/main` Starters view — `PICKS` is gone from the filter, **no bars are zeroed**, the average line is still drawn, the drill panel still shows position groups, and no invisible filter member remains. **Run this before the operator is ever asked to rely on the switch.** The only test of R-0.4 | **R-0.4** |
| **T-S5** | Operator account with `aggregate_tier_labels` on | The `≈N firsts` label still appears **only** in All + no filter; Starters/Bench/filtered show the numeric — now picks-inclusive | R-10 |

### 7.3 Coverage waiver carried forward (operator-accepted, D-11 / W3)

**T1–T4 cannot execute meaningfully.** The hermetic world has **zero**
`draft_picks` rows — `seed_ui_test_db.py` writes none, `build_cassettes` emits no
`traded_picks`, `profiles/standard.json` has no picks key — so `hasPicks` is
false and every surface under test is invisible. Authored, tagged
`[league, picks]`, skipped; covered manually by T-S6.

**Two requirements have NO executable coverage under Option B**, and QA must not
record a green for them from the flow suite:

| Req | Why | Covered by |
|---|---|---|
| **R-5** | The only thing `switchSubset` has ever stripped is `'PICKS'`; `RB` survives a subset switch on `origin/main`, so a position-filtered flow passes identically on fixed and unfixed code in both flag states | T-S1 assertion 8 + manual T-S6 |
| **R-0.4** | Needs `PICKS` reachable in a non-All subset (⇒ pick data) **and** a live flag transition | T-S1 assertion 16 + manual **T-S6c** |

`flows/league/03`'s T6 leg is mapped to **no requirement** — it is a navigation
regression only. It was previously credited to R-5 while testing nothing.

**Follow-up to file:** seed `draft_picks` into the hermetic world (a **new**
`picks` profile, not `standard` — adding picks to `standard` shifts
`total_value` for the whole 11-flow smoke suite and feeds
`_inject_owned_picks`). That unblocks T1–T4, R-5 and R-0.4, and the wider
systemic gap: **the hermetic world can exercise none of the five priced pick
surfaces** (trade-away picker, swap-suggestions sheet, evener chip, calculator
pick rows, power-rankings draft capital). Predates #293.
