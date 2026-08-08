# Test Ledger — Fantasy Trade Finder

> **Purpose:** authoritative record of what's been tested, what shipped, what was measured, and on what version of the stack. Prevents "works on my machine / claimed earlier without evidence" failure modes.
>
> **Read at:** before claiming a result, before proposing a new test that may duplicate a prior one, before shipping a feature.
> **Write at:** immediately after running a test, regardless of outcome.
>
> Companion files: [`MISTAKES.md`](MISTAKES.md), [`DECISIONS.md`](DECISIONS.md), [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) (sample data), [`trade_output.json`](../trade_output.json).

---

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
- [2026-05-21](#2026-05-21)
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
- **Result:** **PASS 4/4**, in CI ([backend/tests/test_three_team_cycles.py](../backend/tests/test_three_team_cycles.py)).
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
- **Result:** **PASS 4/4**, in CI ([backend/tests/test_engine_gates_config.py](../backend/tests/test_engine_gates_config.py)).
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
- **Result:** **PASS 6/6**, in CI ([backend/tests/test_rnk_elo_golden.py](../backend/tests/test_rnk_elo_golden.py)).
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
- **Result:** **PASS 8/8**, stable ×3; full backend suite now **178 passed** with the new file (no pollution). Graduated into the pytest suite (runs in CI).
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

## 2026-05-21

### Living-memory layer adoption
- **Test:** verify all 18 living-memory files exist and pass the `living-memory-format-check` skill.
- **Status:** pending — skill created same session; run after files settle.
- **Doc:** this ledger.

## Manual Verification History

The project does not currently have a `pytest` suite. Verification has been ad-hoc via:

| Verification artifact | What it tests |
|---|---|
| [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) | Expected trade matches for a test league configuration |
| [`Trade_Matches.xlsx`](../Trade_Matches.xlsx) | Reference trade-match output for validation |
| `dump_mismatches.py` | DynastyProcess ↔ Sleeper player-name mismatches |
| `tmp_check_db.py`, `tmp_check_db2.py` | Ad-hoc DB integrity scripts |
| `GET /api/debug/log?n=100` | In-memory ring-buffer log (last 200 entries) for forensic checks |
| Manual smoke: `python3 run.py` → web client login → roster import → swipe → trade card | End-to-end happy-path verification |

**Caveat:** no automated regression suite. A change that breaks one of these flows is detectable only by manual re-run. See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-002.

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
