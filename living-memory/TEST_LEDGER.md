# Test Ledger — Fantasy Trade Finder

> **Purpose:** authoritative record of what's been tested, what shipped, what was measured, and on what version of the stack. Prevents "works on my machine / claimed earlier without evidence" failure modes.
>
> Retention: entries dated within the last 2 months (2026-06-08 onward) plus standing sections live here; older run entries are archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).
>
> **Read at:** before claiming a result, before proposing a new test that may duplicate a prior one, before shipping a feature.
> **Write at:** immediately after running a test, regardless of outcome.
>
> Companion files: [`MISTAKES.md`](MISTAKES.md), [`DECISIONS.md`](DECISIONS.md), [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) (sample data), [`trade_output.json`](../trade_output.json).

---

## 2026-08-10 — Feedback batch #289-#294 (sim gate DEVIATION, operator-directed bypass)

- **Change:** six feedback items in three groups on branch `feedback-289-294` (base `origin/main` @ `16b1dcb`), 16 commits, 51 files, +15,738/−106. **G1 #289** MFL Draft Room resolves franchise *and* player names (four ordered tiers, never a bare id). **G2 #290/#291/#292** value-aware mock run model + `need_pressure` + mock lifecycle (`abandon_completed_mock_drafts`) + pick affordance before tap + MFL owner names in the mock. **G3 #293/#294** draft-pick value counted in every subset and position filter, behind new flag `league.picks_always_counted` (**default OFF**). Plus: `mobile/scripts/sim-run.sh` flag-pin repairs, five stale "mock is OFF" doc locations corrected, D-022/D-023/D-024.
- **Suite:** baseline `2308 passed / 1 skipped` after G1+G3 → **2326 passed / 1 skipped**, exit 0 (+18, all new). `npx tsc --noEmit` **exit 0** (real `npm ci` in-worktree — the main checkout's `node_modules` is ~190 commits stale and lacks `@react-native-cookies/cookies`, which yields a phantom error). `testid-lint.sh` **exit 0**. **All nine** `mobile/tests/check-*.js` pass, including two new ones (`check-picks-subset-invariance.js` 71 assertions, `check-mock-lifecycle.js` 52).
- **Sim run: NOT PERFORMED** — operator-directed bypass (`FTF_SKIP_SIM_GATE=1`) after being presented with the coverage gap and choosing it explicitly. **This is a Tier-1 deviation and the batch's largest change is the least covered:** G2's mock engine ships with unit + distributional evidence only and **no end-to-end run**. Risk is asymmetric — G3 ships dark behind an OFF flag; **G2 ships live on merge** (`draft.mock` already ON, engine change unflagged), with `draft.mock` itself as the only kill switch.
- **Why the mock flow could not run:** `d3-mock-draft-loop.yaml` was authored but is unrunnable — `backend/tests/fixtures/profiles/standard.json` declares one league (`990000000000000001`) while d1/d2/d3 all target `1312140920132497408`, which is in no profile, and the seeder writes **nothing** for `mock_drafts` or draft status. The build agent's "one `leagues[]` entry" estimate was checked and does not hold; this is real seeder work. Pre-existing, unfixed, named.
- **Uncovered by any automated test** (do not read a green suite as covering these): G3 **R-5** and **R-0.4**, and the kill-switch drill **T-S6c** (manual). G1 has **no Maestro flow at all** by design — its acceptance surface is a live check against the operator's Dependables MFL league (62846), also not yet performed.
- **Harness findings — the gate had never actually run.** Every prior ledger entry since the gate's introduction reads "NOT PERFORMED", which is why three defects survived: `--flags` *replaced* the seeded flag map instead of merging; `--flags @file` was documented but unimplemented (the literal string was exported, JSON parsing failed with a stdout warning only, and the run continued with flags OFF); and the handshake fetched `/api/feature-flags` but **only archived it, never asserting** — so a flag-ON tier could assert flag-OFF behavior and exit 0. Additionally `$!` captured the subshell rather than python under bash 3.2 (macOS system bash), so the stale-Flask assertion fired on a clear port **every time** and the EXIT trap orphaned Flask on the port for the next run to talk to. All repaired and each proven by constructing the failure first; nine consecutive runs left no orphan.
- **Failing-first evidence captured** for every behavioral test (G2 T-290-04/10/11/14, T-292-01, D-16 keying; G1 T-289-06; G3 assertions 13/14). Three separate lanes found tests that **passed on the very defect they named** — G1's collision test (its stub raised on the triggering input), G2's one-sided distributional bars (a fully collapsed `sf_tep` board scored *higher* variety than a healthy one), and G3's atomicity assertions (`picksAlwaysCounted={false}` satisfied all twelve). G2's mobile agent also found two of its own first-cut assertions passing on their defects — one because the JSX comment explaining the behavior contained the string it was grepping for.
- **G2 measured results at pinned N=1500, both formats** (`1qb_ppr` / `sf_tep`): P(#1 at 1.01) 0.4553 / 0.6380; P(#1 past pick 3) 0.0893 / 0.0420 (shipped 0.1553); P(#7 at pick ≤4) 0.0000 / 0.0000 (shipped 0.1147); median run size 5.0 / 5.0. Calibration tripwire `test_w2_16` **did not fire**.
- **Fixed in passing:** two G2 tests used fixed user+league ids against the persistent SQLite DB and accumulated rows across runs (second full run reported `cleared 5 rows, expected 3`) — would have surfaced in QA as an unreproducible failure on any machine that had run the suite before. Both now self-clear.

## 2026-08-10 — Outlook: seed-type + IDP-coverage wiring, combined post-fix calibration (NOT merged, no flag change)

- **Change:** two wiring gaps closed, then one combined re-measurement. (1) `scripts/outlook_calibration_backtest.py` gains `seed_type(fx)` and threads `playoff_seed_type` into every `run_outlook` / `get_playoff_format` call, plus a **BUG-3 A/B block** mirroring the existing BUG-1 one; same wiring in `scripts/outlook_preseason_backtest.py`. (2) `pipeline.run_outlook` now calls `strength.lineup_pricing()` and `serialize.py` emits `meta.priced_slot_coverage = {fraction, total_slots, priced_slots, unpriced_slots[], affects_strength}`. `outlook.odds` untouched, `config/features.json` untouched, no `model_config` key, mobile diff is a **type-only** addition (`OutlookPricedSlotCoverage` in `mobile/src/api/league.ts`) with no UI/behaviour change.
- **Suite:** baseline on a fresh `origin/main` reset (`234a018`) **2284 passed / 1 skipped / 0 xfailed** (301 s) → **2297 passed / 1 skipped**, exit 0 (+13). `npx tsc --noEmit` clean (node_modules symlinked from a sibling worktree, removed after). New coverage: 4 payload/coverage tests in `test_outlook_odds.py` (fraction + named unpriced slots, full-coverage league, `affects_strength` false on `trailing_scores`, **prediction-neutrality vs a run serialized without the instrument**), 9 in `test_outlook_playoff_seed_type.py` (an **AST guard** that fails if any `run_outlook`/`get_playoff_format` call in either script omits the setting, the per-fixture seed-type helper, and a load-bearing check that fixed vs reseed brackets give different title distributions and identical playoff odds), plus the `meta` contract pin in `test_outlook_route_cache.py`.
- **Sim run: NOT PERFORMED** — measurement + dark-surface wiring with zero user-visible change (`outlook.odds` false everywhere, mobile diff is a type declaration); branch left unmerged for operator review.
- **Result — in-season, 6 league-seasons / 288 team-week predictions, 10k sims:** playoff Brier **0.0997** vs climatology 0.2500 (**+60.1 %**, cluster-bootstrap 90 % CI [+47.6, +72.2] — excludes 0); title Brier **0.0732** vs 0.0764 (**+4.2 %**, CI [−13.1, +20.0] — **includes 0**). Per week 0.2012 / 0.1065 / 0.0538 / 0.0372. Split by league: all six beat climatology on playoff, **three of six lose to climatology on title**.
- **Result — preseason (week 0), 72 team-seasons:** playoff Brier **0.1968** (+21.3 %, CI **[+2.9, +39.1]**); title 0.0746 (+2.3 %, CI [−18.9, +24.5]). Preseason − week-3 paired Δ **−0.0043** (CI spans 0) — preseason still nominally better than the week-3 model. Median-match leagues 0.2326, H2H 0.1789.
- **Result — the BUG-3 wiring in isolation:** pooled title Brier **0.0733 → 0.0732**; fixed-bracket leagues only 0.0817 → 0.0815; **playoff Brier bit-identical (max \|Δ\| = 0.000000)** and `playoff_seed_type: 1` leagues **bit-identical** (value 1 == reseed == pre-fix behaviour). The bracket rule was wrong for 4 of 6 league-seasons and correcting it moved the pooled title number by 0.0001 — **a null, reported as one.**
- **Over-confidence SURVIVED the fix wave.** Preseason top bucket 0.947 predicted → **0.778** realized (n = 9; was 0.949 → 0.750, n = 8); bottom bucket 0.034 → 0.167. In-season populated buckets stay inside ±0.05 (n = 99 and n = 100). Preseason skill lower CI bound moved the **wrong** way: +4.1 % → **+2.9 %**.
- **Also re-confirmed unchanged:** bye-week μ multiplier still NO-SHIP (Δ +0.0031, CI [−0.0054, +0.0125]; mechanism OLS slope −0.218 vs the naive −1.000); random-re-pairing fallback still costs ~7 % of playoff Brier.
- **Verdict:** (1) **bands, not percentages — stands, and is better supported than before**; a 5 %-rounded playoff percentage from week 6 is an operator risk call, not a validated result (calibration is pooled, not week-stratified). (2) **Gate numbers at week 6, allow bands from week 0, never gate at week 3** — week 3 is dominated by both neighbours and is the only week where title odds lose to a constant 1/12. Report: `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`; dated corrections issued to the three prior #169 reports.

## 2026-08-10 — Combined post-fix outlook calibration (sim gate DEVIATION, standing operator bypass)

- **Change:** seed-type + coverage wiring and the definitive combined calibration. Mobile diff is **type-only** (`mobile/src/api/league.ts` gains the `priced_slot_coverage` payload field) — no UI, no behaviour, `outlook.odds` false everywhere.
- **Sim run: NOT PERFORMED** — `FTF_SKIP_SIM_GATE=1` under standing operator authority; the smoke suite still doesn't exist and this change class renders nothing.
- **Verified:** full suite **2297 passed / 1 skipped**, exit 0; `tsc --noEmit` clean. Deliverable `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`.

## 2026-08-09 — ESPN numeric-id guard fix (backend-only, merged to main)

- **Change:** `server._fetch_sleeper_league_meta` + `trade_block_service.sync_league_trade_block` now pair their `isdigit()` guard with `database.is_linked_platform_league`, so ESPN/MFL/Fleaflicker-imported leagues (numeric native ids) no longer fire Sleeper requests that 404 on `/api/session/init` (prod noise + false `vcr_misses` in FTF_TEST_MODE). Same convention as the #149/#150 proxy fix. Commit `e7d0da7`.
- **Suite:** full `pytest backend/tests -q` → **2219 passed / 1 skipped / 1 xfailed**, exit 0 (562 s) — +2 regression tests in `test_espn_link_route.py` pinning both helpers to zero Sleeper calls on a linked ESPN league.
- **Sim run: NOT PERFORMED** — backend-only, no mobile diff, no schema/API/flag surface; pre-push hook gate not triggered (no `mobile/src/` change).
- **Follow-up:** revert the two harness workarounds in worktree `~/ftf-worktrees/screens-wt` (espn.json `sleeper.trade_block:false` pin; 404-cassette sentinel + gap-guard carve-out) once that branch rebases onto this fix.

## 2026-08-09 — BUG-5: IDP/K starting slots are unpriced (fix + backtest, NOT merged, no flag change)

- **Change:** `backend/outlook/strength.py` only — IDP slot eligibility in `select_starting_lineup()` (a `DL` slot now accepts DE/DT/NT, `DB` accepts CB/S/SS/FS, `IDP_FLEX` accepts any defender) plus a new `lineup_pricing()` instrument. New `scripts/outlook_idp_pricing_backtest.py`, `backend/tests/test_outlook_idp_pricing.py`, and one records fixture. No flag, no `config/features.json`, no `model_config` key, no mobile diff; `outlook.odds` still dark.
- **Suite:** baseline on a fresh `origin/main` reset (`359a0ff`) **2217 passed / 1 skipped / 1 xfailed** (706 s) → **2247 passed / 1 skipped / 1 xfailed**, exit 0 (+30). New file alone: 30 passed in 4.8 s.
- **Sim run: NOT PERFORMED** — validation-plus-neutral-fix change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), branch left unmerged for operator review.
- **Damage measured:** the DynastyProcess board carries QB/RB/WR/TE only, so in the operator's **FFv3** league **8 of 15 starting slots price at exactly 0.0** — **53.3 % of slots**, covering **33.0–34.3 % of the points those teams actually scored** (Sleeper `starters_points`, weeks 1–14). FFv3 is **4 of the 6 backtested league-seasons**; Lakeview is 0 %. The unpriced third is weakly differentiating: sd 58–65 season points vs 160–211 for the priced slots.
- **Result — five-variant preseason backtest, 10k sims, split by league.** V0 status quo reproduces the published baseline exactly (pooled playoff Brier **0.1959**, +21.6 %; FFv3 0.1789; Lakeview 0.2298). **Eligibility fix: 0 of 72 predictions moved** (asserted, not assumed). **League-mean fallback Δ +0.0005** (CI [−0.0056, +0.0061]); **coverage attenuation √ Δ −0.0019** (CI [−0.0167, +0.0070]), **linear Δ +0.0042**. Lakeview bit-identical under every variant.
- **Verdict: real defect, no available fix beats the status quo.** No license-clean dynasty IDP board exists (DynastyProcess, nflverse, FantasyCalc, KTC, Sleeper `search_rank` all checked). Shipped the correctness fix + the coverage instrument; the pricing gap is documented, not papered over. Preseason ship verdict unchanged; IDP-league odds must be **labelled offence-only** before the flag lights. Report: `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md`; gotcha G-026.

## 2026-08-09 — Dated DP value boards + preseason-source revalidation (validation only, NOT merged, no flag change)

- **Change:** no product behaviour touched. New `backend/dp_values_history.py` (research-only dated DynastyProcess boards), 24 committed board fixtures + index in `backend/tests/fixtures/dp-values-history/` (484 KB), three scripts (`scripts/dp_values_history_capture.py` — the only one that uses the network, `scripts/outlook_preseason_backtest.py`, `scripts/outlook_pick_capital_dated_values.py`), and two test files. `backend/outlook/` unchanged, `config/features.json` unchanged, `outlook.odds` still dark, no mobile diff.
- **Suite:** baseline on a fresh `origin/main` reset (`ea19d4b`) **2194 passed / 1 skipped / 1 xfailed** (151 s) → **2217 passed / 1 skipped / 1 xfailed**, exit 0 (+23). New files alone: `test_dp_values_history.py` 15 passed, `test_outlook_preseason_source.py` 8 passed, 0.5 s combined.
- **New coverage:** commit resolution (`until=`/`path=` query shape, empty-result `LookupError`), raw-URL sha pinning, `slim_csv` filtering, all three crosswalk join tiers + position-strictness, scoring-column selection, **offline path asserted against an opener that raises on any network call**, refusal-not-substitution for an uncaptured date, fixture-index integrity, **no-look-ahead invariant** (`scrape_date <= key` on all 24 boards), roster rewind to real week-1 rosters, `auto` → `roster_value` at week 0, board-is-load-bearing check, and four re-scoring guards on the committed per-team records (including a deliberate assertion that preseason title odds do **not** beat climatology, so the null cannot rot away).
- **Sim run: NOT PERFORMED** — validation-only change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), and the branch is left unmerged for operator review.
- **Result — preseason `roster_value`, as-of week 0, 6 league-seasons / 72 team-seasons / 6 champion events:** playoff Brier **0.1959** vs climatology 0.2500 (**+21.6 %**, cluster-bootstrap 90 % CI **[+4.1, +38.3]** — excludes 0); title Brier 0.0740 vs 0.0764 (+3.1 %, CI [−17.7, +24.9] — **includes 0, no skill**). Indistinguishable from the week-3 model (paired delta −0.0013, CI [−0.0573, +0.0470]). Over-confident at the extremes (0.9–1.0 bucket: 0.949 predicted, 0.750 realized, n = 8); beats climatology in 4/6 league-seasons. Board coverage 96.8–99.3 % roster, 100 % starting-slot; unmatched DP rows 0.2–1.8 %.
- **Result — hypothesis 1b re-test:** sub-test (i) −0.113 → **+0.076, CI spanning zero**; confound −0.349 → **−0.415**; (ii)/(iii)/buy:sell bit-identical. Verdict **WEAKENED**.
- **Verdict:** preseason **title** odds — do not render. Preseason **playoff** odds — conditional go, banded not precise, BUG-1 (G-024) first. Report: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

## 2026-08-09 — Outlook odds calibration backtest (validation only, no ship, no flag change)

- **Change:** no product code touched. Added `backend/tests/test_outlook_calibration.py` (22 permanent invariant/fixture tests + 1 strict `xfail` tracking BUG-1), two offline analysis scripts (`scripts/outlook_calibration_backtest.py`, `scripts/outlook_strength_source_compare.py`), 9 committed Sleeper fixtures, and the calibration report. `outlook.odds` remains dark.
- **Suite:** baseline **2136 passed / 1 skipped** → **2158 passed / 1 skipped / 1 xfailed**, exit 0 (142 s). New file alone: 22 passed / 1 xfailed in 3.6 s.
- **Sim run: NOT PERFORMED for the wave push** (`FTF_SKIP_SIM_GATE=1`, standing operator bypass) — the mobile diff is dark-flagged contract/nullability fixes only (`outlook.odds` false everywhere); zero user-visible change.
- **Backtest result:** as-of weeks 3/6/9/12 over 6 real captured Sleeper seasons (72 team-seasons, 6 champion events). Playoff Brier **0.1113** vs climatology 0.2500 (**+55.5 %** skill, cluster-bootstrap 90 % CI [+44.5, +65.9] — excludes 0). Title Brier **0.0725** vs 0.0764 (**+5.1 %**, CI [−13.2, +22.3] — **includes 0, no demonstrated skill**).
- **Verdict:** MARGINAL PASS, conditional — playoff odds ship-worthy after BUG-1 (median-match ingestion, G-024) is fixed; title odds not validated. Report: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`.

## 2026-08-09 — ESPN round-2 ship (sim gate DEVIATION, standing operator bypass)

- **Change:** cold-load login warm-up reload + reload control + wedge hint; league picker (`espn.league_picker` ON, `GET /api/espn/my-leagues`). Push `89c61b4`, build 96.
- **Sim run: NOT PERFORMED** (`FTF_SKIP_SIM_GATE=1`, standing authority). Maestro flow WAS extended (reload control) but not executed — no runnable dev client.
- **What WAS verified:** 2136 passed / 1 skipped, exit 0 (+27); tsc clean; testid-lint OK; **fan-API shape live-verified against an authenticated fetch on the operator's real ESPN session** — caught the lowercase-"ffl" filter bug (real abbrev is "FFL") pre-merge; fixture now mirrors the real payload. Round-1 fixes field-validated by the operator's successful private-league link (league_read 200 in events, 22:44 UTC).

## 2026-08-09 — ESPN-fix + morning-batch + observability ship (sim gate DEVIATION, standing operator bypass)

- **Change:** the wave below (ESPN webview fixes, #285, #286-288, integrations docs, api_observability) merged and pushed as one; combined suite **2109 passed / 1 skipped, exit 0**, tsc clean on final branch. `FTF_SKIP_SIM_GATE=1` under standing operator authority; ESPN fix's REAL validation is the operator's TestFlight walkthrough with the private league (checklist in `docs/feedback/items/espn-webview-escape/status.md`) — build 95.

## 2026-08-09 — API observability build (flag `obs.api_events` ON; worktree agent, merged/shipped same day — see entry above)

- **Change:** operator-directed observability program (`docs/feedback/items/api-observability/status.md`): `backend/api_observability.py` — outbound wrapper around every external egress chokepoint (Sleeper REST/GraphQL incl. the 3 documented bypass sites, ESPN, MFL, Fleaflicker, DP CSVs, KTC, Anthropic, Expo, Apple/Google) + inbound Flask hooks; events land in `user_events` (`api_call`/`api_request`, `user_id='system:api'`), errors always + successes 1-in-10 sampled (`model_config obs_success_sample_n`), 30 d retention purge, admin report `GET /api/admin/analytics/apihealth`. Backend + docs only; no mobile/web changes.
- **Sim run: NOT PERFORMED** — backend-only change class, and the branch is deliberately left unmerged for operator review (build agent has no merge authority; sim gate applies at ship).
- **What WAS verified:** baseline `pytest backend/tests -q` on the release base → **2086 passed / 1 skipped, exit 0**; after build → **2109 passed / 1 skipped, exit 0** (+23 in `backend/tests/test_api_observability.py`: per-service wrapper capture with cookie/JWT-never-stored redaction assertions, inbound hook capture + exclusions, 1-in-N sampling vs errors-always, kill-switch zero-writes, poisoned-event-store failure isolation, retention purge, apihealth report + `service` filter). `tsc --noEmit` n/a (no mobile diff).

## 2026-08-09 — Design-decision batch (#270/#272 A/B, #169, #279) (sim gate DEVIATION, standing operator bypass)

- **Change:** experiment `trades_home_inline` (strip/canvas variants, operator on strip), flag `trade.position_impact` ON, experiment `aggregate_tier_labels` (operator-only), two mock-lab revisions. Batched at operator direction ("Don't push E1 until we resolve these other two items too").
- **Sim run: NOT PERFORMED.** Standing bypass (`FTF_SKIP_SIM_GATE=1`). Both experiment builds carry explicit Maestro waivers (allowlist-gated to one real account, invisible to the QA harness identity).
- **What WAS verified:** `pytest backend/tests -q` → 2072 passed / 1 skipped, exit 0 (+8 new: experiment assignment/byte-identity ×2 builds, starter_impact tier/rank ×4 incl. tie-break determinism and the pure-weight-revise switch test); `tsc --noEmit` clean on the final combined branch; testid-lint OK; config-reference merge conflict union-resolved and re-gated.

## 2026-08-09 — Feedback wave 3 (#277/#278/#280/#281, #273-275, #269/#276) (sim gate DEVIATION, standing operator bypass)

- **Change:** tier labels app-wide (+3 routes gain additive `tier`), PickAssignment future-year/sheet fixes, sheet targeting (flag `trades.sheet_targeting` ON), scroll-to-trade, inline-home mockup lab. #282 held unmerged pending operator sign-off on prod-name fixtures.
- **Sim run: NOT PERFORMED.** Standing operator bypass (`FTF_SKIP_SIM_GATE=1`); smoke suite still doesn't exist.
- **What WAS verified:** `pytest backend/tests -q` → 2059 passed / 1 skipped, exit 0 (+6 tier-route tests); `tsc --noEmit` clean after every merge and post deferred-fix; flag mirror + testid-lint green; per-branch review before each merge.

## 2026-08-08 — Feedback wave #268/#267/#265/#263/#260/#257/#172 (sim gate DEVIATION, standing operator bypass)

- **Change:** 6 fixes/features + 2 mockup labs (see CHANGELOG same date). Two new flags ON (`trades.edit_full_sheet`, `trades.intent_modes`); one additive API field (`tier` on GET /api/trade/values); intent field in trade prefs.
- **Sim run: NOT PERFORMED.** Smoke suite still doesn't exist; standing operator bypass ("You can bypass the gate and push live to testflight", 2026-08-08) via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2053 passed / 1 skipped, exit 0 (+12 new: #268 repro, 11 intent-mode tests); `tsc --noEmit` clean after each merge and on the final combined branch; flag mirror tests green; `testid-lint.sh` OK; node tests (league-unlocks 4/4); per-branch code review before every merge. #268's fix carries a test that reproduces the exact pre-fix client request (405) and proves the corrected URL (200).

## 2026-08-08 — Context-slim batch (sim gate SKIP, express-class: docs/config only)

- express: context-overload remediation (branch `context-slim-2026-08-08`) — gates skipped by operator direction. Diff touches `mobile/src/**/CLAUDE.md` (docs), living-memory, docs/, skills, hook config — zero app code. `FTF_SKIP_SIM_GATE=1` used for the push; CI (pytest + tsc + testid-lint) is the verification gate.

## 2026-08-08 — Feedback #266/#258 fixes (sim gate DEVIATION, standing operator bypass)

- **Change:** #266 ESPN-path link buttons dead on LeaguePicker (transition-settled auto-open) + #258 MFL team-name HTML entities (startup backfill of pre-#210 stored rows). Merge `b682ee2`.
- **Sim run: NOT PERFORMED.** Same blocker as the two entries below: the 11-flow smoke suite doesn't exist. Bypass is now STANDING operator authority ("You can bypass the gate and push live to testflight", 2026-08-08) until the flows land; exercised via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2041 passed / 1 skipped, exit 0 (+4 new backfill tests, verified failing-first); `tsc --noEmit` clean under fresh `npm ci` (includes tonight's `@react-native-cookies/cookies` dep); fix-agent reproduced both root causes in code before changing anything.

## 2026-08-08 — ESPN Connect WebView ship (sim gate DEVIATION, recorded)

- **Change:** Phase 1b ESPN cookie capture (`EspnConnectScreen`, `EspnLinkSheet` auth-error self-serve, League-tab re-sync recovery), flag `espn.webview_capture` shipped ON. Commits `989343f`/`365e815`/`81a16a2` → pushed to `main` @ `d745146`.
- **Sim run: NOT PERFORMED.** Declared tier 2, waived by operator order at merge ("Merge now and push to testflight with the flag on" + explicit gate-bypass confirmation, 2026-08-08), exercised via `FTF_SKIP_SIM_GATE=1`. Same underlying blocker as the entry below: the new native dep (`@react-native-cookies/cookies`) needs a rebuilt dev client before any Maestro run, and the smoke flows don't exist yet.
- **What WAS verified:** `tsc --noEmit` clean (post-rebase); `node tests/check-espn-cookies.js` 14/14; `pytest -k "flag or feature or taxonomy"` 149 passed (post-rebase, flag ON + release-mirror green); manual testID cross-check (flow + registry + source agree); independent adversarial review — security clean, 8 findings fixed in `365e815`.
- **Compensating control:** EAS build 90 (v1.11.0) auto-submitted to TestFlight; QA checklist in `docs/plans/espn-connect-webview/scope.md` §3 (fresh capture / OTP hint / auth-recovery, real private league 493554) is the validation gate, with the flag flip-off as rollback.

## 2026-08-08 — ESPN auto-derived draft order (sim gate DEVIATION, recorded)

- **Change:** `suggested_order` prefill on PickAssignmentScreen (+ espn_service derivation). Tier 1 by the matrix (mobile screen change).
- **Sim run: NOT PERFORMED — the required artifact cannot exist yet.** The gate's tier-1 requirement is the 11-flow smoke suite; `mobile/maestro/` contains zero flows (the mobile-testing program has built seams/scripts/testIDs, not the flows). Maestro itself IS installed.
- **Deviation authority:** operator directive to ship ("Pick up and finish 3", 2026-08-08), exercised via the documented `FTF_SKIP_SIM_GATE=1` override. Receipts per the gate spec: this entry + the deviation note in `docs/plans/draft-extensions/build-espn-auto-order.md`.
- **What WAS verified:** `pytest backend/tests -q` → 2037 passed / 1 skipped, exit 0 (+42 new tests incl. the live-captured league-11896 fixture pinning the operator's inverse-regular-season decision); `tsc --noEmit` clean; all 4 mobile AST/behaviour check scripts pass. The mobile delta is a prefill of an existing editable list — no new writes.
- **Follow-up owed:** the 11 smoke flows are now the gate's own blocking dependency — until they exist, every tier-1/2 push needs this same override. Build them or re-tier the gate.

## Table of Contents
- [2026-08-08](#2026-08-08)
- [2026-07-04](#2026-07-04)
- [2026-06-11](#2026-06-11)
- [Archive: pre-2026-06 entries](archive/TEST_LEDGER-pre-2026-06.md)
- [Manual Verification History](#manual-verification-history)
- [Custom-Skill Benchmarks](#custom-skill-benchmarks)
- [Tests Planned but Not Yet Run](#tests-planned-but-not-yet-run)
- [Verification Discipline](#verification-discipline)

---

## 2026-08-08

### ESPN Connect WebView build (worktree `espn-webview-capture` off `origin/main` @ `cb6aacb`)
- **`cd mobile && npx tsc --noEmit` → clean, exit 0** (run after both the feature commit and the review-fix commit).
- **`node mobile/tests/check-espn-cookies.js` → 14/14 checks pass** — pure extractor `pickEspnCookies` (pair/half-pair/trim/braces/multi-bag), `readEspnCookies` polls both ESPN domains, `clearEspnCookies` clears 2 names × 2 domains × 2 native stores (the fresh-login guarantee).
- **`python3 -m pytest backend/tests/ -q -k "flag or feature"` → 148 passed**; broader `-k "taxonomy or analytics or events or flag or feature or seed_ui"` → **320 passed** (new flag `espn.webview_capture` in registry + release-mirror; 4 `espn_connect_*` events in the taxonomy with prop entries).
- **testID cross-check (manual):** every id referenced by `mobile/.maestro/flows/espn-connect-capture.yaml` and the components CLAUDE.md registry resolves in `mobile/src/`. `mobile/scripts/testid-lint.sh` does not exist on this branch (`mobile/scripts/` is gitignored — see below); a tracked lint script is a separate task.
- **NOT run:** the Maestro flow itself (needs a rebuilt dev client carrying the new `@react-native-cookies/cookies` native pod) and the in-WebView login leg (waived per scope §3 — live third-party page; covered by the scope block's TestFlight QA checklist). `pod install` fails on this machine (CocoaPods 1.16.2/Ruby 4.0.3 `Unicode Normalization not appropriate for ASCII-8BIT` on the spaces-in-path repo); the EAS build regenerates the lockfile.

### Suite trajectory, 2026-07-09 → 2026-08-06
- **252 → 1466.** Reconstructed from commit messages during the living-memory revival pass; each figure is the count the committing session reported. Checkpoints: 272 → 285 → 382 → 521 (accounts P1/P2) → 558 → 632 → 781 (v1.9.0) → 855 (analytics P3/P4) → 937 (teardown W2) → 979 (owned picks) → 998 → 1025 → 1209 → 1336 (deck engine) → 1359 → 1378 → 1405 → 1445 → 1455.
- **Counts are not strictly monotonic in log order.** Parallel worktree agents committed against different baselines — the 1414/1415 pair on 2026-08-03 is the clearest example. Treat a lower count in a later commit as a branch artifact, not a regression.

### Measured live on 2026-08-08 (this checkout, `teardown-remediation` @ `30492ac`)
- **`python3 -m pytest backend/tests/ -q` → 1466 passed, 1 skipped, 41.7s.**
- **`cd mobile && npx tsc --noEmit` → clean, exit 0.**
- ⚠️ **This is the 62-commits-behind base, not the project's test posture.** The rookie-draft QA handoff cites **1685 passed / 1 skipped on `origin/main` @ `cee4324`**. Quote the origin/main number when describing the project; quote this one only when describing this checkout.
- The 1466 includes two untracked test files not yet committed: `test_espn_pick_assignment.py` (6 tests), `test_finder_config_consolidated.py` (5 tests).

### Practices worth keeping (observed in this window)
- **Failing-first is used and stated in commit messages** — `#238` lineup before/after and the `market.movers` work both note tests written failing-first; several 07-25 fixes note the regression shape was "verified failing pre-fix via stash".
- **Flag-gated waves re-run the suite twice** — once as built, then again with flags ON as a separate gate. The deck-engine waves all did this.
- **A contrast guard runs in CI-shape** — `mobile/scripts/check-contrast.js` over 13 token pairs, `npm run test:contrast`.
- **`mobile/scripts/` is gitignored**, so JS regression checks live in `mobile/tests/` instead.

## 2026-07-04

### TC-API-001 — Manual Trade Calculator endpoints (/api/trade/evaluate, /api/trade/values)
- **Test:** 8 pytest cases over an injected universal pool ([backend/tests/test_trade_evaluate.py](../backend/tests/test_trade_evaluate.py)): symmetric→even, lopsided→unfair+favors, per-player values match `elo_to_value` exactly, unknown-id graceful drop, one-sided packages (no verdict), empty→400, bogus format→default, values-endpoint shape + ETag 304.
- **Result:** **PASS 8/8**; full suite **252 green**. Real-pool smoke (local Flask, live DP data): 671 valued players; top-vs-mid → `unfair/favors: give/ratio 0.008`; mirror trade → `even/1.0`.
- **Also verified:** mobile live mode end-to-end in Expo web with a contract-shaped fetch stub (backend has no CORS, so browser-origin calls can't hit it — native is unaffected); demo mode unchanged (Bijan parity scenario byte-identical since 07-02: 2,536/2,874, +9%/+12%).
- **Not yet run:** live mode against prod from a real device (needs deploy).

### TC-API-002 — Send in Sleeper error-contract hardening (/api/sleeper/link, /api/trades/propose)
- **Test:** +6 route tests ([backend/tests/test_sleeper_write_route.py](../backend/tests/test_sleeper_write_route.py)) locking each branch the mobile `SendInSleeperButton` depends on: no-key→503 `sleeper_unconfigured`; `bad_request` (non-numeric league / no counterparty); pre-flight **expired stored token**→409 `sleeper_expired` + credential dropped (the #1 real reconnect trigger, distinct from the mid-call auth-error branch); non-auth write failure→502 `sleeper_write_failed`; rosters-fetch exception degrades to 400 `roster_not_found` (never an unhandled 500); GET surfaces `expired:true`.
- **Result:** **PASS 14/14** in the file (8 prior + 6 new); full backend suite **258 green**; mobile tsc clean. These run the real Flask handlers against a real in-memory DB + real Fernet key, mocking only the Sleeper network — so they double as the local route smoke.
- **Reviewed, no code change needed:** runtime paths already fail safe (`_fetch_league_rosters` catches all → None → structured 400; adapter maps auth vs generic failures correctly). Hardening was coverage, not bug-fixing.
- **Still deferred by design:** slice-4 calculator Send surface (needs a real counterparty); flag `trade.send_in_sleeper` stays OFF; on-device link→propose against real Sleeper (needs a full EAS build — `react-native-webview` is native — + throwaway account).

## 2026-06-11

### TC-ENG-004 — 3-team cycle clearing (find_three_team_cycles)
- **Test:** 4 pytest goldens for the dark/uncovered kidney-exchange 3-team cycle clearer — Pareto A→B→C→A detection, no-benefit→empty, <3 members→empty, lineup-feasibility blocks a roster-breaking handoff.
- **Result:** **PASS 4/4** ([backend/tests/test_three_team_cycles.py](../backend/tests/test_three_team_cycles.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Findings:** **F-1 (P3 dead code)** `find_three_team_cycles` is implemented + exported but **never called** (no caller; trade.three_team flag only in a comment). Correct + now tested — a product decision away from wiring on.
- **Artifacts:** [`qa/results/TC-ENG-004.md`](../qa/results/TC-ENG-004.md).

### TC-DB-002 — DB concurrency, write integrity, recency
- **Test:** concurrent member_rankings upserts (atomic replace), concurrent distinct trade decisions (no loss), concurrent ranking swipes (WAL under contention), check_for_match 90-day recency bound. Threaded against scratch DB.
- **Result:** **PASS 5/5.** 8 concurrent upserts → exactly 20 rows (atomic), 16 decisions all persisted, 24 swipe rows no lock errors, stale (>90d) like excluded.
- **Findings:** none at thread scale. Postgres multi-process pool saturation remains a pre-scale Render load-test follow-up (not reproducible with threads on SQLite).
- **Artifacts:** [`qa/db/tc_db_002.py`](../qa/db/tc_db_002.py), [`qa/db/_concurrency_probe.py`](../qa/db/_concurrency_probe.py), [`qa/results/TC-DB-002.md`](../qa/results/TC-DB-002.md).

### TC-INT-001 — Sleeper-boundary input handling (G-003..G-008)
- **Test:** session_init defensive handling of null roster slots, int IDs, garbage IDs, empty roster, dup IDs; passthrough error handling (bad username, parse-url).
- **Result:** **PASS 8/8.** Nulls filtered, int IDs coerced, garbage filtered, empty roster degrades gracefully, bad username → 404 (not 500).
- **Findings:** F-1 (P3) duplicate roster IDs not deduped (3→6); harmless today, one-line `dict.fromkeys` fix.
- **Artifacts:** [`qa/sec/tc_int_001.py`](../qa/sec/tc_int_001.py), [`qa/results/TC-INT-001.md`](../qa/results/TC-INT-001.md).

### TC-CFG-001 — feature flags + model_config live-tuning contract
- **Test:** flag map + FTF_FLAGS env precedence; admin config auth (401)/unknown(404)/badval(400); live write→reload→readback; reload endpoint auth.
- **Result:** **PASS 11/11.** FTF_FLAGS override wins; config write persists + reloads (v3 reads same live _cfg).
- **Findings:** **F-1 (P3 operational)** surplus floors gate *divergence* cards only — *consensus-basis* decks (cold/low-coverage leagues) are fairness-gated, so cranking surplus floors has NO effect there (use fairness_threshold/consensus_score_scale). F-2 (P3) marginal flag makes min_side_surplus_marginal the live floor. Documented in config-reference.md.
- **Artifacts:** [`qa/api/tc_cfg_001.py`](../qa/api/tc_cfg_001.py), [`qa/results/TC-CFG-001.md`](../qa/results/TC-CFG-001.md).

### TC-PERF-001 — performance: cold-start, warm latency, concurrent load
- **Test:** measured backend vs charter budgets — cold boot, cold/warm session_init, warm GET p50/p95, generate end-to-end, per-opponent enumeration bound, 8-way concurrent init+generate, error-free-under-load.
- **Result:** **PASS 9/9.** Cold boot 1.0s; warm GET p50/p95 = 20/58ms; generate 31 cards in 1.28s; 8 concurrent users 0 errors. All within budget at local scale.
- **Caveats (honest):** concurrency test shares the trade-job cache (same fixture user) → proves session/cache thread-safety, not N independent generations. Real prod risks (cold Sleeper fetch in session_init, v3 enumeration on large league) NOT exercised locally — flagged for a Render-side load test.
- **Artifacts:** [`qa/perf/tc_perf_001.py`](../qa/perf/tc_perf_001.py), [`qa/results/TC-PERF-001.md`](../qa/results/TC-PERF-001.md).

### TC-ENG-003 — engine gate config-responsiveness (admin tuning surface)
- **Test:** 4 pytest goldens proving the tuning knobs are monotone/predictable — min_side_surplus (↑→fewer cards), trade_elo_gap_max knife-edge, waiver_slot_cost erodes extra-player side, tier_mult_elite scales composite.
- **Result:** **PASS 4/4** ([backend/tests/test_engine_gates_config.py](../backend/tests/test_engine_gates_config.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** the legacy parity fixture yields 4 cards legacy / 0 v2 — v2 correctly rejects one-sided trades legacy surfaced (reinforces "kill-switch is a real downgrade").
- **Artifacts:** [`qa/results/TC-ENG-003.md`](../qa/results/TC-ENG-003.md).

### TC-API-002 — public-route auth-intent audit
- **Test:** classify all public routes read vs mutating; allowlist-check public mutations; empty/garbage-body robustness; CORS posture.
- **Result:** **PASS 4/4.** 13 public /api routes (8 read, 5 mutating); all 5 mutations intentional (session/init, demo, feedback, extension/auth, parse-url). No 5xx on garbage; CORS same-origin-only. **No unauthenticated state-mutating routes** — recon "44 none-auth" concern resolved.
- **Findings:** F-1 (P3) no rate limiting on pre-auth mutations (session/init, extension/auth); F-2 (P3 process) new `_require_initialized_session` gate (25 routes) added since TC-API-001 → those counts stale.
- **Artifacts:** [`qa/api/tc_api_002.py`](../qa/api/tc_api_002.py), [`qa/results/TC-API-002.md`](../qa/results/TC-API-002.md).

### TC-E2E-004 — cross-league flow + cross-league disposition
- **Test:** matches/all across leagues; awaiting; portfolio over 2 leagues; create match in league A, switch session to league B, disposition the A match (cross-league branch).
- **Result:** **PASS 9/9.** Cross-league accept (session on B, match in A) → 200, decision persisted on the match's own league, Elo signal queued for replay. Correctly league-scoped.
- **Findings:** none. Observation: match fires on whichever swipe completes the mirror (locate by DB state, not response id).
- **Artifacts:** [`qa/e2e/tc_e2e_004.py`](../qa/e2e/tc_e2e_004.py), [`qa/results/TC-E2E-004.md`](../qa/results/TC-E2E-004.md).

### TC-RNK-001 — Elo math golden fixtures (engine input quality)
- **Test:** 6 pytest goldens for the Elo update — exact pairwise math (K=32 → ±16), K-factor by decision type (rank 32 / like 8 / pass 4, linear), zero-sum conservation, 3-player decomposition + order preservation, override pinning, replay determinism.
- **Result:** **PASS 6/6** ([backend/tests/test_rnk_elo_golden.py](../backend/tests/test_rnk_elo_golden.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** displayed Elo is rounded to 1 decimal in `get_rankings`, and that rounded value is what's published to member_rankings + fed to `elo_to_value` — whole valuation pipeline runs at 0.1-Elo precision. Zero-sum only holds without tier overrides.
- **Artifacts:** [`qa/results/TC-RNK-001.md`](../qa/results/TC-RNK-001.md).

### TC-E2E-003 — superflex (sf_tep) format path + isolation
- **Test:** sf_tep trio→rank3→generate via X-Scoring-Format header; format-partitioned persistence; 1qb_ppr isolation; per-format independent Elo; sf_tep card validity.
- **Result:** **PASS 8/8.** +9 sf_tep rank rows, 1qb_ppr unchanged (222→222, isolated), sf_tep member_rankings 0→685, sf_tep generate → 31 valid cards. **Same player 1qb=1605 vs sf=1800 Elo** (QB premium in superflex working as intended).
- **Artifacts:** [`qa/e2e/tc_e2e_003.py`](../qa/e2e/tc_e2e_003.py), [`qa/results/TC-E2E-003.md`](../qa/results/TC-E2E-003.md).

### TC-API-001 — API consistency + doc-drift audit
- **Test:** static analysis of all 92 server.py routes (naming, error-shape taxonomy, auth-gate distribution) + doc-drift vs api-reference.md + live envelope/error-contract sampling.
- **Result:** **COMPLETE 7/8** (the 1 FAIL is the surfaced naming finding). Error contracts solid (every error body has an `error` key; 401/404/400 correct). Auth gates: session 35 / none 44 / cron 13 / bearer 1.
- **Findings:** F-1 (P2) 39 `jsonify({"error": str(e)})` raw-exception leaks; F-2 (P3) error-value vocabulary split (42 code-style vs 44 sentence-style vs 23 code+message); F-3 (P3) 2 undocumented routes (`/api/feedback/admin`, `/api/tiers/copy-from-format`); F-4 (P3) lone snake_case segment `/api/sleeper/league_users`; F-5 (P3) no envelope standard / no version prefix.
- **Docs updated this cycle:** added `/api/trades/awaiting` + stochastic-deck-order note to api-reference.md; v3-feasibility "no trades" failure mode to runbook.md.
- **Artifacts:** [`qa/api/tc_api_001.py`](../qa/api/tc_api_001.py), [`qa/results/TC-API-001.md`](../qa/results/TC-API-001.md).

### TC-E2E-002 — restart resilience (in-memory session + job loss)
- **Test:** generate a deck, restart the server process against the same DB, verify graceful degradation: stale token→401, stale job→404 (no hang), data survives, FB-46 swipe of a pre-restart card reconstructs + persists, new session fully functional.
- **Result:** **PASS 9/9.** Old job 404 in 0.00s; 646 member_rankings survived; FB-46 swipe persisted +1 decision; post-restart generate → 31 cards.
- **Findings:** none. In-memory job/session loss is a graceful degradation, not a failure mode; recon operability concern closed.
- **Artifacts:** [`qa/e2e/tc_e2e_002.py`](../qa/e2e/tc_e2e_002.py), [`qa/results/TC-E2E-002.md`](../qa/results/TC-E2E-002.md).

### TC-DB-001 — schema integrity, migration idempotency, SQLite↔Postgres parity
- **Test:** fresh-init schema parity on SQLite AND a real local Postgres (table set + per-table columns), `_migrate_db()` idempotency on both, dialect-branched upsert smoke (leagues/league_members/member_rankings/skips + the F-1 second-member upsert), and a read-only live-DB quality audit (orphans, enum domains, ISO timestamps, boolean storage, dup guards).
- **Result:** **PASS 24/24** incl. Postgres plane. Exact 24-table/all-column parity; migrations idempotent both dialects; **F-1 fix verified cross-dialect** (works on Postgres too, leagues stays 1 row).
- **Findings:** the 41 orphaned `league_members` (recon "HIGH, fix before scale") are **benign** — 0 have rankings, 0 in trade_matches; never-logged-in leaguemates. Recon item downgraded P3. data-dictionary.md confirmed in sync (24 tables; recon "22/23" was a miscount).
- **Env note:** `psycopg2-binary` (declared dep) was missing locally; installed to run the PG plane. Throwaway PG db `ftf_qa_parity` created + dropped.
- **Artifacts:** [`qa/db/tc_db_001.py`](../qa/db/tc_db_001.py), [`qa/db/_dialect_probe.py`](../qa/db/_dialect_probe.py), [`qa/results/TC-DB-001.md`](../qa/results/TC-DB-001.md), `qa/db/scratch/TC-DB-001-run.json`.

### F-1 (TC-E2E-001) RESOLVED — verified
- Commit `ddf67df` fixed the second-member `upsert_league` UNIQUE-constraint crash (dialect-aware `on_conflict_do_update` on the `sleeper_league_id` PK) + added `backend/tests/test_league_upsert.py` (3 tests). Re-verified: IntegrityError gone, TC-E2E-001 back to 67/67, regression test passes. E2E harness allowlist updated (no longer masks the error; now allowlists only the synthetic-league Sleeper 404).

### TC-SEC-001 — operator-endpoint auth enforcement
- **Test:** sweep all 8 operator routes (`/api/admin/*`, `/api/feedback/admin*`, `/api/debug/log`, `/api/feature-flags/reload`, `/api/cron/*`) across CRON_SECRET set/unset; in-proc test of `_require_cron_auth` prod branch (fail-closed) without a real Postgres; session-gate control on mutating routes.
- **Result:** **PASS 35/35.** Cron-gate enforces (401 missing/wrong/near-miss, success on match); prod fails closed (503 when secret unset); session routes 401 tokenless/bogus.
- **Refutes recon:** the discovery report's "5 unprotected admin endpoints (P0)" is **FALSE** — every route calls `_require_cron_auth()`. Lesson: recon findings are hypotheses until a TC verifies them.
- **Findings:** **F-1 (P2)** `run.py` binds `0.0.0.0` + `debug=True` with no local CRON_SECRET → operator routes exposed on LAN for local/self-host runs (prod on Render unaffected: fail-closed).
- **Artifacts:** [`qa/sec/tc_sec_001.py`](../qa/sec/tc_sec_001.py), [`qa/results/TC-SEC-001.md`](../qa/results/TC-SEC-001.md), `qa/sec/scratch/TC-SEC-001-run.json`.

### TC-ENG-002 — fairness-gate golden fixtures (1-for-1 gate + package-discount watch item)
- **Test:** 8 pytest golden fixtures in `backend/tests/` covering `package_value_v2` discount math (exact + monotone in `package_adj_gamma`), 1-for-1 gate config-driven knife-edge, discount→`fairness_score` propagation, FR8 outlook market-neutrality, and v2↔v3 fairness-floor parity + monotonicity. Self-calibrating where exact propagation is hard to hand-predict.
- **Result:** **PASS 8/8**, stable ×3; full backend suite now **178 passed** with the new file (no pollution). Graduated into the pytest suite — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job.
- **Findings:** **F-1 (P3)** `_fairness_v3` is a hand-copied mirror of v2 `_fairness` (standing TODO) — drift risk; this test now guards parity, but a shared `score_trade` extraction is the real fix (already planned in competitor-top20/03).
- **Key observation:** v3 lineup-feasibility is all-or-nothing — a roster that can't field a full QB1/RB2/WR2/TE1 lineup gets ZERO v3 cards (v2 still serves). Sharp edge worth a runbook note for "no trades" diagnosis.
- **Artifacts:** [`backend/tests/test_fairness_gate_golden.py`](../backend/tests/test_fairness_gate_golden.py), [`qa/results/TC-ENG-002.md`](../qa/results/TC-ENG-002.md).

### TC-ENG-001 — trade-engine kill-switch regression (legacy/v2/v3)
- **Test:** three FTF_FLAGS-pinned server instances (legacy / v2 / v3), ordering flags off; per-engine card-validity battery, flag-routing proof, legacy≠v2 divergence, v2→v3 top-card stability. Same user+league.
- **Result:** **PASS 30/30**, stable across 3 runs. Deck sizes legacy 13 / v2 33 / v3 33; all roster-ownership + fairness checks clean on all engines. v2's #1 trade always survives into v3; v2 top-10 → v3 overlap a deterministic 5/10.
- **Findings:** none. Observations: legacy fallback is a real UX downgrade (random opp Elo, smaller deck) not a transparent swap; v2→v3 top-10 continuity is exactly 50% (watch item if product wants tighter migration continuity).
- **Artifacts:** [`qa/eng/tc_eng_001.py`](../qa/eng/tc_eng_001.py), [`qa/results/TC-ENG-001.md`](../qa/results/TC-ENG-001.md), `qa/eng/scratch/TC-ENG-001-run.json`.

### TC-E2E-001 — full-stack happy path (automated harness)
- **Test:** session_init → trio/rank3 ×3 → trade generate (async job) → swipe → mirrored-like match (likes_you instant + two-session two-step) → disposition lifecycle (accept/accept → accepted, 409 repeat, 404 unknown, 400 bad input) → DB integrity sweep. Driven via HTTP against a local Flask on a scratch copy of `data/trade_finder.db`; mobile client timeout budgets as pass bar. Flags: v3 engine + all Tier 2 trade flags on.
- **Result:** **PASS 67/67 checks**, reproducible across runs. 31 cards in 0.8–1.5 s; cache-hit re-generate ≤4 ms; all calls within mobile budget.
- **Findings:** **F-1 (P1)** `upsert_league` keys on `(league_id, user_id)` but PK is league_id alone → IntegrityError swallowed on every second-member session_init, their league row never persisted. **F-2 (P2)** 7-day card-dedup vs unbounded match-dedup mismatch → already-accepted trade re-served then silently no-ops on like.
- **Artifacts:** harness [`qa/e2e/tc_e2e_001.py`](../qa/e2e/tc_e2e_001.py), report [`qa/results/TC-E2E-001.md`](../qa/results/TC-E2E-001.md), machine-readable run `qa/e2e/scratch/TC-E2E-001-run.json`.
- **Planned variants:** TC-E2E-002 restart-resilience, TC-E2E-003 sf_tep format, TC-E2E-004 Postgres parity.

## Manual Verification History

*Historical — predates the pytest suite. As of 2026-08-08 the project has a pytest suite of ~2000 tests (`backend/tests/`, run in CI's `backend-tests` job per `.github/workflows/ci.yml`); the ad-hoc methods below were the verification approach before that suite existed and are largely superseded. The 2026-05-21 entry that used to open this file (living-memory layer adoption, status pending) is archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).*

| Verification artifact | What it tests |
|---|---|
| [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) | Expected trade matches for a test league configuration |
| [`Trade_Matches.xlsx`](../Trade_Matches.xlsx) | Reference trade-match output for validation |
| `dump_mismatches.py` | DynastyProcess ↔ Sleeper player-name mismatches |
| `tmp_check_db.py`, `tmp_check_db2.py` | Ad-hoc DB integrity scripts |
| `GET /api/debug/log?n=100` | In-memory ring-buffer log (last 200 entries) for forensic checks |
| Manual smoke: `python3 run.py` → web client login → roster import → swipe → trade card | End-to-end happy-path verification |

**Caveat (historical):** at the time this table was written there was no automated regression suite, so a change that broke one of these flows was detectable only by manual re-run. That gap is closed — see the pytest suite note above. [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-002 (pytest adoption) is resolved.

## Custom-Skill Benchmarks

| Skill | Benchmark | Result |
|---|---|---|
| **`project-reorganizer.skill`** | 6-phase methodology (scan, propose, cross-reference, execute, update imports, verify) vs ad-hoc reorganization | ~83% pass rate WITH skill vs ~43% WITHOUT (+40pp improvement). See [`project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html) |
| **`feature-evaluator.skill`** | Evaluates code across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability); produces severity-rated reports | Used in-repo for ongoing code review; no formal pass/fail benchmark yet |

---

## Tests Planned but Not Yet Run

See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) and [`NEXT.md`](NEXT.md). High-priority:

- **Pytest suite for backend services** — `ranking_service.py`, `trade_service.py`, and `data_loader.py` would benefit most. Currently zero coverage.
- **Integration test for full Sleeper flow** — mock Sleeper API responses; verify session/league/roster import.
- **Elo regression test** — golden-file comparison: given a fixed sequence of swipe inputs, verify Elo outputs match a recorded baseline.
- **Trade-card generation regression** — given a fixed league snapshot, verify trade cards generated.
- **Tiered matchup engine A/B** — compare global-Elo vs tier-prioritized matchup selection on information gain per swipe.
- **Postgres migration smoke test** — `DATABASE_URL` pointing at local Postgres; run through full flow.
- **Mobile client Elo parity** — verify mobile and web compute the same Elo values for the same swipe sequence.

---

## Verification Discipline

Rules of evidence for this ledger:
- **No claim without a verification artifact.** Either a docs file, a script output, a manual screenshot, or a recorded test run.
- **State the input set.** "Tested on test-league X with N players" beats "tested it."
- **Distinguish smoke from regression.** Smoke = "it ran"; regression = "the output matches a saved baseline."
- **When manual: name the path.** Click sequence in mobile? Curl call in web? Specifics make it reproducible.
- **When fixing a bug: capture the failing input.** Add to verification artifacts.
