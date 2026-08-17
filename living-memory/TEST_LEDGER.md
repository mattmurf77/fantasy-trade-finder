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

## 2026-08-16 — Organic-trade backfill scripts + prod backfill run (Tier 4)

- **Change:** `feat/organic-backfill` (unmerged) — `scripts/backfill_sleeper_trades.py`, `scripts/backfill_suggestion_links.py`, `backend/tests/test_backfill_scripts.py`, docs. Backend/ops-only: **sim gate Tier 4** (pytest only), Maestro n/a (also retired per D-056). No schema/API/flag/analytics surface.
- **Tests:** new suite **20 passed** (chain-walk depth/terminator/flake cases, sweep dry-run + idempotency, retro exact/direction/window-edge/ghost-split/pick pseudo-id/idempotency/never-overwrite/dry-run/era-skip). Full backend suite on branch: **2943 passed / 1 skipped / 1 failed** — the failure is `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`, **pre-existing on clean origin/main** (verified by stash-and-rerun): `release-300.json` fixture still has `suggestion.telemetry: false` after the 2026-08-16 flag lighting. Flagged as a separate task; zero regressions from this branch.
- **Prod runs (evidence = script logs, dry-run-then-real, idempotency re-verified):** trades backfill dry-run 555 found/529 new → real run inserted **529** (22 league-seasons swept, 0 failed week fetches); retro linker dry-run 109/0-match → real run wrote **109** rows (0 recommended, 0 ghost); immediate re-runs of both wrote **0** (idempotent). Read-only validation: impressions era starts 2026-07-27; exactly 1 captured trade postdates it (already live-linked) — 0 retro matches is the honest expected result.

## 2026-08-16 — App identity (Fleeced name + ram icon) shipped to TestFlight; gates NOT run

- **Change:** `242a399` — `expo.name` + `CFBundleDisplayName` -> `Fleeced`; `AppIcon.appiconset/App-Icon-1024x1024@1x.png` replaced with the ram mark. 4 files = 2 text lines + 2 PNGs. No schema, API, feature-flag or analytics surface; no user flow altered.
- **Evidence:** EAS build **1.13.4 (113)** status FINISHED, profile `production`, distribution STORE, `error: null`. EAS-reported `gitCommitHash` matched the locally verified commit exactly, so binary contents are confirmed rather than assumed. Icon asserted 1024x1024, mode RGB (**alpha absent** — an alpha channel is an App Store rejection), sRGB profile embedded, `plutil -lint` OK on the plist. Label fit measured (36.5pt vs ~70pt budget) and rendered on an iOS 18 simulator home screen. **Operator confirmed name + icon on device** from the TestFlight build.
- **NOT run:** no Maestro tier, no `qa/sim-runs/last-sim-run.json`, no backend suite (nothing backend changed). The build and TestFlight submission **preceded any gate**. This was not an operator express declaration — recorded here as a deviation, not a waiver.
- **Unverified:** Apple's acceptance of submission `b900ad79` was never machine-confirmed; `eas-cli` 19.0.5 has no `submit:list` and `build:view` returns `submissions: null`. Confirmation is the operator's on-device sighting only.

## 2026-08-16 — Matchmaking engine phase 1 SHIPPED dark (telemetry + trade-gen v2)

- **Change:** two squash merges to `main` (operator directive: "waive Maestro, merge and ship"): `suggestion.telemetry` (branch tip `deb965c`) and `trade_gen.v2` (branch tip `c940a86`), both flags **OFF**, backend-only, zero mobile diff; plus research corpus + presentation mockup. Scope blocks + waivers: `docs/plans/matchmaking-engine/`.
- **Sim gate: Tier 4** (backend-only per runbook matrix — no sim run; pytest is the gate). Maestro **waived by operator 2026-08-16** (backend-only dark flags). Pre-push hook not implicated (no `mobile/src` changes).
- **Merged-state full backend suite (ship branch, post conflict-resolution): 2924 passed / 1 skipped / 0 failed (299s).** Branch-level baselines beforehand: telemetry worktree 2878/1/0; gen-v2 worktree 2888/1/0 (its 24-test suite incl. the 12-team fixture league + uncapped/tier assertions); clean-main-at-fork context: 2855/1 (premium-import session, 2026-08-15). Conflicts resolved in the merge: 3 flag-parity fixtures (keep-both, JSON-validated) + `trade_service.py` `_DEFAULT_CFG` adjacent insertion (both knob blocks kept, `ast.parse` verified).
- **Not run:** no simulator flows (Tier 4), no on-device pass — nothing user-visible shipped. First lighting of either flag owes its own checklist (NEXT.md 2026-08-16 section).

---

## 2026-08-15 — Fit-congruence signal weighting SHIPPED (PR #134)

- **Change:** `6f293f4` — swipe-signal K scaled by fit-congruence ([D-060](DECISIONS.md)): `signed_lane_shift` extracted from `classify_lane` (byte-identical, pinned incl. the `total <= 0` corner), `TradeCard.lane_shift` stamped unconditionally, `fit_congruence_mult` applied at the swipe route to BOTH the in-memory signal and the **persisted `k_factor`** — the build agent caught that `_compute_elo` replays `swipe_decisions` rows, so an in-memory-only mult would have reverted boards to flat K on every deploy. Reviewer verified the replay claim and the serializer allow-list (no client leak).
- **Tests:** new `backend/tests/test_fit_congruence.py` **26 passed** (re-run independently by reviewer). Full suite on branch **2859 passed / 1 skipped**; measured clean-main baseline same worktree = 2833/1 (branch adds exactly +26). Matrix: rebuild pass-on-win-now ×0.4; rebuild LIKE-on-win-now full K; contend mirror; not_sure/sub-threshold/reconstruction neutral; knobs-at-1.0 → byte-identical (`==`) Elo trajectory vs control + non-vacuousness assertion. CI green all three checks.
- **Neutral-by-design cases on record:** FB-46 client-echo reconstructions and `_likes_you` synthesized cards carry no `lane_shift` → 1.0.

---

## 2026-08-15 — Guided Onboarding v2 Phase 0+1 (built dark, merged; TestFlight walk OWED)

- **Context:** full gates (scope block `docs/plans/guided-onboarding-v2/scope.md`; Maestro n/a per D-056). Built dark behind `onboarding.guide_v2: false` — flag-off asserted as the v1 behavior graph (s6.1 toast + s2.3 restored on the flag-off arm by orchestrator review; copy trims + s7.1/s3.1 cuts ship unconditionally, documented in D-059).
- **Automated evidence:** `tsc --noEmit` 0 · `mobile/tests/check-guide-script.js` NEW, 228 assertions, sabotage-verified 4 ways (un-trimmed copy / plural fix removed / s7.1 revived / retirement dropped → all RED) · `check-s51-regen-diff.js` 32/32 after TradesScreen edits · all `mobile/tests/check-*.js` now run in CI · `testid-lint.sh` OK · backend pytest **2838 passed / 1 skipped** (taxonomy round-trips for 5 new events + spotlight prop; flag fixture mirrors ×5).
- **Code-walk proofs (in PRD/commit messages):** N6.1 gate evaluated in `swipeMutation.onSuccess` (like-time prefetch would race the POST); s6.2+Apple chain behind N6.1 completion with consume-only-on-successful-show; regen bus source guard (trios/import returns can't burn the `quickset_save` Apple class or mislabel `deck_regenerated.position`).
- **OWED (blocking graduation, not merge):** operator TestFlight checklist — 16 walks incl. both N8 arms, flag-off regression, v1-upgrader, `guideDismissed` zero-bubbles (`docs/plans/guided-onboarding-v2/testflight-checklist.md`).
## 2026-08-15 — Premium Rankings Import v1 (feat/premium-import-v1, dark)

- **Merged-state full backend suite: 2855 passed / 1 skipped (265s)** on `feat/premium-import-v1` (merge of `feat/premium-import-backend` `627dcd0` + `feat/premium-import-mobile` `52e4807`, base `d3fe3ac`). `test_rankings_import.py` 25 → 47.
- **Paste-path regression golden**: `rankings_paste_golden.json` captured from the pre-change implementation; sabotage #2 (backend) proved it detects drift.
- **Sabotage: 13/13 caught.** Backend 3 (hint-narrow winner, fallback-empty, rows-precedence). Mobile 10 (flag default flip, filter removal, contender override default, contender guard ×2, Value-column leak ×2, rows-unsupported, non-400 rethrow, FeedbackFAB unmount). All restored, trees verified clean.
- Mobile: `npx tsc --noEmit` clean; `testid-lint.sh` OK; **36/36 `check-*.js` suites** incl. new `check-premium-import.js` (27 checks) + `check-rank-presets.js` (42 parser cases).
- Maestro/sim: n/a per [D-056]. **Owed:** operator on-device DN export pass (`docs/plans/connected-rankings/build-v1-premium-import/testflight-checklist.md`) before `ranks.source.dynasty_nerds` flips; requires a **full EAS build** (new native dep `expo-document-picker`).

## 2026-08-15 — Open-access Phase A: gates run, fixes built, ALL SHIPPED (PRs #131, #132, #129)

- **Context:** operator ratified O-1…O-9 of `docs/business/product/2026-08-14-open-access-onboarding.md`, then D-055/D-056. Merge order: likes_you floor (#131) → s5.1 fix (#132) → flag flip (#129), all squash-merged to `main` 2026-08-15 (tip `0d8d7bb`). Full gate report: `docs/plans/open-access-phase-a-gates.md`. Still owed by the operator: the 5-step TestFlight check (gate report § Manual TestFlight check) and the deploy-day experiment retirement (`docs/runbook.md` § Retiring the onboarding experiment overlay).
- **Gate (a) — deck-quality eval: PASS** (first-ever execution of the scoring half — the 2026-07-17 report's insult columns were never filled). 9 prod Sleeper leagues, 108 first-run sims, prod Postgres read-only. Empty-deck 0.0% (<5%), insult 1.48% (<3%, |Δ|≥500 floor — bars ratified as standing, D-055). All 8 insulting cards were ungated `likes_you` injections → fixed by #131.
- **Gate (b) — S-43 `s5.1`: FAIL, then fixed.** Maestro walk (run pre-D-056) captured `s5-0` despite real tier saves + completed regen; root cause code-verified and independently re-read: the diff effect nulled `pendingRegenRef` on the status-flip commit while reading the pre-regen `deck` — `fresh` structurally 0, `s5.1` never rendered in repo history. Adjacent: per-generation UUID `trade_id` (naive fix would count identical packages as new) and the post-Quick-Set doubled deck.
- **#131 (likes_you floor):** suite 2817 passed / 1 skipped; CI green; eval re-run on preserved prod mirror **with floor-off control**: all 8 insults gone, 1.48% → 0.37% (residual 2 organic, present in control — Thompson-sampling noise); worst surviving injection Δ −486. Knob `likes_you_min_user_delta` (−500), seeded in `_MODEL_CONFIG_DEFAULTS`.
- **#132 (s5.1 fix):** content-based `tradePackageKey` diff over `job.cards`, late-bound to the forced job id; deck cleared on regen (kills doubling). `tsc` 0; `check-s51-regen-diff.js` **32/32** (re-run by reviewer; sabotage-verified 3 ways); CI green. **`s5.1` rendered for the first time** — sim runs completed before D-056 landed captured it on both chip-walk ("6 new trades…") and all-skip; evidence `qa/sim-runs/2026-08-15-s51-fix/` (gitignored, per-machine). **Standing caveat:** engine stochasticity means an all-skip walk can honestly celebrate small N (measured: 1 of 31 packages differed with zero saves) — the operator's all-skip check may legitimately see `new_trades: 1`. Copy nit at N=1 ("1 new trades") flagged, unshipped.
- **#129 (flip):** six flags true (five `onboarding.*` + `landing.try_before_sync`); fixture mirrors + rewritten pin test (reviewer re-ran 76/76); suite 2811/1 on branch; retirement of `onboarding_v2_rollout` is a **runtime operator action post-deploy** — procedure + stale-overlay hazard analysis in the runbook section above.

---

## 2026-08-15 — #313 1QB QB cap (SHIPPED, PR #128, deploy-verified)

- **Change:** backend-only — `backend/data_loader.py` gains `_compress_qb_1qb_values` (order-preserving piecewise-linear compression of `1qb_ppr` QB seed values, applied last in `_apply_consensus_blend`) + `seed_value_for_elo` inverse; `backend/database.py` seeds `qb_1qb_cap_elo=1785` / `qb_1qb_cap_knee_elo=1580`. [D-054](DECISIONS.md), scope block [`docs/feedback/items/313-1qb-qb-cap/scope.md`](../docs/feedback/items/313-1qb-qb-cap/scope.md).
- **Build agent's runs (worktree `build-313`, base `21df73f`):** baseline `2763 passed / 1 skipped` → final `2779 passed / 1 skipped` (+16 = exactly the new `test_qb_1qb_cap.py`). Sabotage matrix **6/6 RED** with tree-dirtied verification; kill-switch byte-identity proven over the full 633-player × 2-format pool (60,276 bytes). ⚠️ The agent's first two suite runs were issued from the main checkout, not the worktree — disclosed in `status-2026-08-14.md` §11; the wrong-cwd run masked a genuine `test_dp_format_mapping` failure until re-run in the worktree. **Anyone re-verifying must run pytest with the worktree as cwd.**
- **Orchestrator's independent run (this ship):** rebased onto `origin/main` @ `2529bef` (7 commits moved, zero footprint overlap) → `pytest backend/tests -q` → **2827 passed / 1 skipped** (4m45s). CI green on PR #128 (backend-tests, mobile-typecheck, testid-lint).
- **3 existing tests amended** (both `test_ktc_blend` kill-switch pins + `test_dp_format_mapping` raw-column pin now neutralise the #313 knobs) — the `ktc_blend_weight` byte-identity claim in config-reference was amended to match.
- **Deploy verified by behaviour:** prod `GET /api/trade/values?scoring_format=1qb_ppr` → Allen/Maye/Lamar all `tier: first_1` on the first post-merge poll.
- **Sim gate: Tier 4 (CI only) — operator decision**, recorded in the scope block §5 with the deviation rationale (change is user-visible but backend-only; the hermetic harness seeds its own values, so a sim run would exercise fixtures unaffected by this change). No `qa/sim-runs/last-sim-run.json` (no `mobile/src` in the push; the pre-push gate structurally does not fire).

---

## 2026-08-15 — Trade-card narrative positional accuracy (shipped, PR #125)

- **Change:** backend-only — `backend/trade_narrative.py` positional branches now resolve the player and the position from one source (`_top_received(card, players, positions)`); no received player at a needed position → neutral fairness sentence instead of an invented benefit. Decision [D-053](DECISIONS.md), scope block [`docs/plans/narrative-position-accuracy/scope.md`](../docs/plans/narrative-position-accuracy/scope.md).
- **Bug evidence (pre-fix, reported):** decks generated against the operator's four real Sleeper leagues → **23 of 32 cards** carried a position-inaccurate sentence (operator reads QB-thin in all four, so `needs[0]`=QB while the headline received asset was RB/WR/TE).
- **Ran (branch @ tree with fix):** `pytest backend/tests -q` → **2769 passed, 1 skipped** (4m40s, local SQLite). `backend/tests/test_trade_narrative.py` 5 → 12 tests.
- **Re-run after merging `origin/main` @ `19d4174`** (PR #121 co-owner rosters + PR #122 compressed boards, both engine flags ON): **2811 passed, 1 skipped** (4m18s). The +42 over 2769 is exactly what the two merged PRs brought plus nothing of mine changing count; main's own last recorded figure was 2804/1 and these 7 tests close the arithmetic.
- **Note:** the fix commit message cites `D-051`; the decision was renumbered **D-053** in the merge after main claimed D-051/D-052. Docs are correct; the commit message is not.
- **Negative control:** the 7 new tests were re-run with the fix stashed (`git stash push backend/trade_narrative.py`) → **5 failed**, including the reported repro (TE-only return for a QB-thin user) and the invariant sweep over every needs × received-position combination. The other 2 cover cases the old code got right by coincidence.
- **NOT re-run:** the four-real-league deck generation that surfaced the bug — needs the operator's live Sleeper leagues; the local dev DB has zero stored cards. The 23/32 figure is the reported pre-fix baseline, not a post-fix measurement.
- **Sim gate:** tier 4 (backend-only; no route, schema, or mobile change) — no sim run, no `qa/sim-runs/last-sim-run.json`. Tier call recorded in the scope block §5.

---

## 2026-08-15 — Compressed-board pool prune + boarded-member fallback (SHIPPED, PR #122)

- **Change:** backend-only, two dark flags — `trade.pool_calibration` (`trade_optimizer` prune ranks on a board-scale-calibrated divergence) and `trade.divergence_fallback` (`trade_service` falls back to the consensus generator when a boarded member yields zero divergence cards). Scope block: [`docs/plans/compressed-board-pool/scope.md`](../docs/plans/compressed-board-pool/scope.md); [D-052](DECISIONS.md), [G-045](GOTCHAS.md), [Q-017](OPEN_QUESTIONS.md).
- **Ran (worktree `loving-shtern-12e4b1`, branch `claude/loving-shtern-12e4b1` off `origin/main` @ `21df73f`):** `pytest backend/tests -q` → **2771 passed, 1 skipped** (6m48s, local SQLite, Python 3.14). Baseline for this tree was 2763/1, and this change adds exactly the 8 new tests in `test_compressed_board.py` — the arithmetic closes, no pre-existing test was deleted or skipped to get green. **Note `test_rookie_scope.py` passes on this interpreter** (it is the known local-3.14 flake in earlier entries; it did not fail here).
- **New tests (8, all paired):** every fixed behaviour is asserted alongside a **flag-off test pinning today's defect**, so the suite proves the flag is what changed the outcome and that the kill switch restores the current engine byte-for-byte. Includes an offset-invariance property test (+200 Elo to every opponent rating ⇒ identical deck with the flag on, different deck with it off).
- **One pre-existing pin found by the suite, as designed:** the flag-fixture mirrors. Adding two keys to `config/features.json` broke `test_seed_ui_test_db.py` three ways until `fixtures/flags/{release,onboarding-v2,profiles-on}.json` gained them; `all-on.json` is a 41-key overlay and correctly needs nothing.
- **FIELD-VERIFIED read-only against PROD boards** (`DATABASE_URL=$DATABASE_URL_PROD`, SELECT-only via the replay script's existing loaders — nothing written). League FFV3 `1312140920132497408`, user mattmurf77, production `v3_pool_size=12`. Board shapes confirm the diagnosis: the three zero-yield boards have median Elo **1201** (max 1800–1839) against jonbonjourvi's **1379**. Deck regeneration, cards per boarded opponent:

  | Config | jonbonjourvi | MangoPatti | Bcork | gdubs10 |
  |---|---|---|---|---|
  | today (both off) | 5 divergence | **0** | **0** | **0** |
  | `pool_calibration` | 5 divergence | 0 | 0 | **5 divergence** |
  | both flags | 5 divergence | **5 consensus** | **5 consensus** | 5 divergence |

- **What this evidence does NOT establish:** (a) deck **quality** — card counts are not card quality, and nobody has eyeballed the rescued cards; (b) behaviour on any league other than FFV3, in particular a healthy-board league (the byte-identity claim there rests on the unit fixture, not on field data); (c) that consensus cards for MangoPatti/Bcork are the *right* product answer versus the divergence cards a larger pool finds ([Q-017](OPEN_QUESTIONS.md)).
- **Latency, measured per pair on the real boards:** pool 12 ≈ 1.5–5.2 s regardless of the flag (no regression). Pool 30 — the "deploy-free mitigation" — costs **26 s (Bcork), 80 s (MangoPatti), 102 s (gdubs10)**; a full 11-opponent deck did not finish in 10 minutes. Raising `v3_pool_size` is not a shippable workaround.
- **Sim gate:** tier 4 (backend-only, no mobile file, no route contract) — no sim run, so **no `qa/sim-runs/last-sim-run.json` was written**; the tier call is recorded in the scope block. Maestro delta waived for the same reason.
- **Flags flipped ON** by operator instruction after the evidence above: `trade.pool_calibration` and `trade.divergence_fallback` are `true` in `config/features.json` and in the three fixture mirrors the mirror-tests police.
- **SHIP EVIDENCE:** squash [PR #122](https://github.com/mattmurf77/fantasy-trade-finder/pull/122) → `main` @ `19d4174`. PR CI green on **Python 3.12** — backend-tests, mobile-typecheck, maestro-testid-lint — which is the run that matters, since local is 3.14. **Deploy confirmed live** at 2026-08-15T18:21:21Z: prod `GET /api/feature-flags` returns both keys `true`; pre-deploy they were ABSENT (new `FLAG_KEYS` entries), so absent→true is the probe, not a value flip.
- **POST-DEPLOY deck regeneration against prod boards, flags loaded from the real `config/features.json`** (not overridden): every boarded member produces cards — jonbonjourvi **5 divergence**, gdubs10 **4 divergence**, MangoPatti **5 consensus**, Bcork **5 consensus**. Four unranked members (bsharp3, JohnStanfield, dondags20, KevinLake) returned 0, which is the displacement working as designed.
- **A CLAIM THIS RUN FALSIFIED:** the pre-deploy entries said the deck total "stays at 30". It does not. `global_target` is a stop-when-reached threshold — `if len(new_cards) >= global_target: break` runs *after* an opponent's whole batch is appended — so the deck overshoots by up to `max_per_opponent - 1`. The live read returned **34**. The three pre-deploy reads landed on exactly 30 only because every batch was a full 5 and the total hit the threshold precisely; three consistent observations of a coincidence read as a law. Also note gdubs10 returned **4** divergence cards live against 5 pre-deploy — within-run variance from the dedup/diversity/intent path, not investigated.
- **Re-run after merging `origin/main` (PR #121) and flipping both flags:** `pytest backend/tests -q` → **2804 passed, 1 skipped** (4m25s). The +33 over the 2771 above is everything PR #121 brought with it, `test_co_owner_rosters.py` included. First suite run with these two flags live by default — the engine tests that pin flag-OFF behaviour set their own flags explicitly, so they are unaffected, and the three flag-fixture mirrors had to be flipped alongside `config/features.json` or `test_seed_ui_test_db` fails.

---

## 2026-08-15 — Sleeper co-owned rosters (branch `claude/epic-hellman-6af20f`, commit `44c8bbf`, UNMERGED)

- **SHIPPED 2026-08-15:** squash [PR #121](https://github.com/mattmurf77/fantasy-trade-finder/pull/121) → `main` @ `6158e65`, all three CI checks green (backend-tests 7m36s, mobile-typecheck, maestro-testid-lint). Deploy verified live by probe: `/api/tier-config` 200 and prod `/js/app.js` contains the new `ownsRoster` predicate. **Sim gate overridden**, on the record: the marker says `result: "fail"` and the PR route bypasses `githooks/pre-push` (it only fires on a direct push to `main`); the operator said push live with that stated. **Mobile remains dark** until an EAS build — the client-side resolution is in the app binary, so the reported symptom persists on the current TestFlight build.
- **Change:** [ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md) — roster→user resolution now matches `owner_id` **or** `co_owners`; a co-owner is an alias of the roster's primary `owner_id`, which becomes the session's LEAGUE identity (`_league_user_id()`) alongside the ACCOUNT identity (`sess["user_id"]`). `POST /api/session/init` gains two optional additive fields. **FULL GATES** (API contract — the bright line; operator signed off the field and all three waivers, 2026-08-15). Scope block: `docs/plans/sleeper-co-owner-rosters/scope.md`.
- **Backend:** `pytest backend/tests -q` → **2796 passed / 1 skipped** (7m55s, local SQLite, Python 3.14). New `test_co_owner_rosters.py`: **33 tests** covering the predicate (owner / co-owner / stranger / empty-id / `co_owners` null·absent·non-list·non-str), `_league_user_id`'s pre-existing-session fallback, `_roster_id_for_owner` (Send in Sleeper), the mock-draft owner set + roster map, `_order_from`'s co-owner draft-order aliasing with an owner-primary inverse, and five session_init end-to-end cases run with the bg-writes daemon inlined.
- **The regression test is PROVEN, not assumed.** Narrowing `owns_roster` back to `uid == owner` and re-running: **7 failed / 25 passed** — `owns_roster` co-owner, `find_user_roster`, `canonical_owner_id`, `_roster_id_for_owner`, and all three co-owner session_init cases. Restored and re-verified green.
- **The load-bearing assertion** is `test_session_init_co_owner_writes_one_row_per_roster`: **12** `league_members` rows for a 12-team league, roster 3 keyed on `460238423161040896` (the primary owner) and the caller's account id keying nothing. That is the case a client-only fix would fail — it would write 13 rows and the DB-member merge would hand the engine a phantom copy of the caller's own team.
- **Sole-owner twins throughout**, including `test_session_init_without_league_user_id_defaults_to_the_caller` (an old client that omits both new fields), so "byte-identical for the 99% case" is asserted, not claimed.
- **Fixture:** `backend/tests/fixtures/sleeper/co-owned-league/` — the REAL Bush League (`1338231586314780672`) league id, twelve `owner_id`s and the roster-3 co-ownership, verified live against Sleeper the same day; player lists synthetic and globally unique per roster so "whose roster resolved?" is answerable from ids alone.
- **Mobile:** `tsc --noEmit` **clean**; `testid-lint.sh` **OK**; all **24** `check-*.js` structural suites exit 0. Both tsc and the suites re-run after a clean `npm ci` (see the harness note below).
- **Web:** `node --check web/js/app.js` clean; no `owner_id === user.user_id` comparisons remain in the file.

### Sim gate — tier 2, RUN on `FTF-iOS18` (89EEFD08) against `44c8bbf`. 2/4 pass; both failures are assertion staleness, changed path proven green

Release sim build **SUCCEEDED**; four flows run (`smoke/01-signin`,
`02-league-pick`, `05-trades-render`, `06-trades-deck`) — the subset that
crosses `initLeagueSession` / session_init / the deck. Evidence:
`qa/sim-runs/last-sim-run.json` (recorded **`result: "fail"`** on purpose, so
the pre-push hook blocks and the operator decides).

| Flow | Exit | Verdict |
|---|---|---|
| `smoke/01-signin` | 0 | **pass** |
| `smoke/05-trades-render` | 0 | **pass** |
| `smoke/02-league-pick` | 1 | fail — stale assertion |
| `smoke/06-trades-deck` | 1 | fail — visibility/scroll |

**The changed code path is proven green on-device.** Both flows that reached it
logged `=== /api/session/init … user_players=26 opponents=11` → `✅ session/init
done — 26 on roster, 11 opponents` → HTTP 200, and **no** `co-owned roster:
league identity` line — correct, because `seed_ui_test_db.py` emits roster
cassettes with no `co_owners` key at all, so every flow exercises the
sole-owner branch. That is exactly the regression assertion tier 2 is for.
`05-trades-render`'s screenshot shows *"Your roster reads as Rebuilder"* —
roster-derived inference, which cannot render without a resolved roster.

**Why neither failure is this change** (and the honest limit of that claim):

- **`02-league-pick`** reached `tab.trades` (session established, Main entered)
  and then failed asserting `rank-home.card.trio`. The failure screenshot shows
  the app on **Quick Set Tiers** — which `mobile/src/screens/CLAUDE.md`
  documents as the Rank tab's default launch route for no-pref users — with the
  correct league, SF TEP, and a populated board. Flow-vs-app drift, same class
  as the already-known-stale `smoke/09-league.yaml`.
- **`06-trades-deck`** failed asserting `trades.find-btn` is visible. The deck
  had **generated**: the screenshot shows a real card vs `@qa_opp_ranked`
  (match strength 100) with a correct send/get owner split — you send your own
  assets, you get theirs, which is precisely what the owner comparisons this
  change touches would break if they were wrong. `trades.find-btn` exists
  (`TradesScreen.tsx:4379,4565`); the view had scrolled past it (the outlook
  Confirm/Change card is clipped at the top of the shot).
- **Limit:** neither flow was re-run against `origin/main`, which would have
  cost a second ~45-minute cold Release build. "Pre-existing" is an inference
  from the evidence above, not a measurement. Stated so nobody reads it as one.

**Three harness defects found, all pre-existing, none caused by this change:**

1. **Maestro needs `JAVA_HOME` and this machine has none set.** Homebrew
   `openjdk` 26.0.2 is installed but unlinked, so `/usr/libexec/java_home`
   fails and maestro dies with *"Unable to locate a Java Runtime"* (surfacing
   as a spurious flow failure, exit 1). Fix:
   `export JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home`.
   **This alone means no local sim gate could have run on this machine** — which
   fits the last several ledger entries recording the gate as not-run/waived.
2. **`sim-build.sh` cannot bundle against a symlinked `mobile/node_modules`.**
   Node resolves the symlink's realpath, so `@expo/cli` looks for
   `metro-runtime` under the *other* checkout and dies with `Cannot find module
   'metro-runtime/package.json'` — in the "Bundle React Native code and images"
   phase, i.e. after ~30 min of Pods compilation. A real `npm ci` in the
   worktree fixes it (`export:embed` then bundles 2273 modules in 5.7s).
3. **A killed `sim-run.sh` leaves its Flask holding :5001**, and the next run
   aborts `INFRA: STALE FLASK: whoami pid … != started pid …` (exit 2). Clear
   with `lsof -ti:5001 | xargs kill -9`.

**Not re-captured:** `screens/manifest.json` was already stale for 20 of 21
screens before this change (sources changed 2026-08-10/11). Tier 2 asks for
re-capture of *flagged* screens; this change alters no visuals, and clearing
four days of unrelated capture debt is not this change's to pay. Flagged here
so the debt stays visible.

---

## 2026-08-14 — Deck-outcome impression-ownership validation (shipped, PR #119)

- **Change:** backend-only — `_save_deck_outcome_safe` ownership/existence/recency validation + `deck_outcome_rejects` health counters; [PR #119](https://github.com/mattmurf77/fantasy-trade-finder/pull/119), branch `claude/charming-lalande-6dc6b6`.
- **Ran (pre-merge tree @ `9910ae6`):** full backend suite `pytest backend/tests/ -q` → **2741 passed, 1 skipped** (4m12s, local SQLite). Includes 4 new/extended validation tests: `test_deck_taste.py` (foreign id writes nothing — owner's taste untouched; unknown/stale/no-user counted; own-recent path still writes outcome + taste) and `test_deck_signal_v2.py::test_foreign_or_stale_impression_rejected_across_routes` (swipe/flag//api/events all 200-but-write-nothing). Two pre-existing signal tests updated to seed real impressions (they minted ids with no backing row — exactly the pattern the fix rejects).
- **Merge race:** PR #120 (roster history, `81dd6d2`) landed on `main` mid-ship — merged into this branch (four living-memory conflicts resolved; D-049 → theirs, this fix's decision renumbered **D-050**). **Merged tree re-run:** `pytest backend/tests/ -q` → **2763 passed, 1 skipped** (3m53s; includes the 22 roster-history tests, `test_rookie_scope` included and passing on this interpreter). PR CI green additionally required before push to `main`.
- **Sim gate:** tier 4 (backend-only, no route-contract change for legitimate clients) — no sim run; tier call recorded in [`docs/plans/deck-outcome-validation/scope.md`](../docs/plans/deck-outcome-validation/scope.md).

---


## 2026-08-14 — Dynasty Year in Review P0: roster-history capture (branch `feat/roster-history`)

- **Change:** ADR-011 — `league_roster_history` + `league_board_history`, three write triggers (on-sync at 8 sites, daily-tick daemon sweep on all four platforms, manual cron route), flag `market.roster_history` ON, `espn_reconnect` notification type, `ix_pvh_format_date`. **FULL GATES** (schema + data collection — the bright line; not express-eligible). Scope block: `docs/plans/dynasty-year-in-review/scope.md`.
- **Backend:** `pytest backend/tests -q` (excluding `test_rookie_scope.py`, known local-3.14-only — CI on 3.12 is green on main) → **2725 passed / 1 skipped**. New `test_roster_history.py`: **22 tests** pinning precedence-not-recency (weekly beats sync; weekly never hash-suppressed; sync-over-sync suppressed on same hash; backfill never overwrites), NULL-not-zero `team_value`, `changed_from_prev`, synthetic-id owner rejection, the owner re-stamp leaving roster facts untouched, board idempotency + `board_updated_at`, per-owner pick exclusions, stalest-first sweep ordering, the weekday gate + `=7` kill lever, the platform hook swallowing failures, and the ESPN nudge firing once per credential-expiry episode.
- **Two pre-existing pins honoured, found by the suite:** the flag-off daily-tick payload stays byte-identical (`test_deck_replenishment`), and the five flag-fixture mirrors gained the new key surgically (`test_seed_ui_test_db`; `all-on.json` is an overlay and needs nothing).
- **Review-doc correction found by the FIRST test run:** their ISO-boundary example ("2026-12-31 is 2027-W01") is factually wrong — 2026 is a 53-week ISO year (`2026-W53`); the real crossing is 2025-12-29 ⇒ `2026-W01`. Both pinned.
- **Mobile:** `tsc --noEmit` clean (worktree, node_modules symlinked); `check-notif-glyphs.js` **10 types, 5/5**.
- **VERIFIED LIVE (post-merge, 2026-08-14):** squash PR [#120](https://github.com/mattmurf77/fantasy-trade-finder/pull/120) -> `main` @ `81dd6d2`, PR CI green on 3.12 (full suite incl. rookie_scope — local-3.14-only confirmed a third time). Deploy confirmed by route probe (roster-snapshot 405-catch-all -> 401 cron-auth), then **Writer C fired against prod with CRON_SECRET**: `{ok, started, period_key: 2026-W33}` -> sweep completed in ~8s over 12 leagues: **11 swept, 131 roster rows + 16 board rows inserted `source='weekly'`, all three present platforms proven live** — 9x Sleeper (12 teams, fetch p95 ~200ms), ESPN 11896 (14 teams, stored-cookie path, 420ms), MFL 62846 (14 teams, 5418ms — the budget's slow tail). One skip, legible: `test_league_lakeview` (fixture row) counted as `sleeper_fetch_failed`. No Fleaflicker league exists to exercise that adapter. Sim gate + Maestro: **WAIVED** (D-P1-08; server-only + one bell row type). No `qa/sim-runs/last-sim-run.json` — not fabricated. Remaining live-unproven: the espn_reconnect nudge path (no expired cookie in prod today) and the daily-tick gate itself (first scheduled firing = the liveness read).

---

## 2026-08-14 — sleeper FAAB Q-016 (docs-only; no new tests, no posture change)

- **Change:** docs + living-memory only — module docstring caveat in `backend/sleeper_write.py`, `docs/integrations/sleeper.md`, [Q-016](OPEN_QUESTIONS.md). **No behavior touched, no tests added.**
- **Ran:** `pytest backend/tests/test_sleeper_write.py backend/tests/test_sleeper_write_route.py -q` → **37 passed**, against the merged tree at `2f0fcbb`. Targeted by operator instruction; the full suite was not run and no posture is claimed from this entry beyond these two files.
- **Independently re-verified `79123a0`'s fix rather than trusting the commit message** — built `propose_trade` bodies and parsed them with a real GraphQL parser (`graphql.parse`, ambient dev dep, not in requirements): pre-fix FAAB body → `Syntax Error: Expected Name, found String 'sender'`; post-fix FAAB body, empty body, and draft-picks body → all parse. Confirms both the fix and its claim that `__DRAFT_PICKS__` was never affected.
- **The limit of all of the above:** every test here proves the document *parses*. **Nothing proves Sleeper accepts it** — the `[{sender, receiver, amount}]` element type is unverified ([Q-016](OPEN_QUESTIONS.md)) and no test can settle it without a real FAAB capture. A green suite on this path is not evidence FAAB works.

---

## 2026-08-14 — Feedback wave #307-#319 (sim gate NOT run; owed with the #295 Tier-1 debt)

- **Change:** `7057d86` (PR #117) + `7fb1e34` version bump, v1.13.4 **build 111**. Eleven items, four groups.
- **Verified (merged tree, orchestrator-run):** pytest **2737 passed / 1 skipped** · tsc exit 0 · testid-lint OK · 19 structural suites all exit 0 (~600 assertions; two "FAIL"-looking greps were the literal strings "FAIL-OPEN"/case text — exit codes are the authority).
- **Falsification:** 48 named sabotages across the four groups, all RED-then-green, apply-verified. One agent caught its own mis-sequenced two-part sabotage producing a bogus pass (the sixth false-pass-shaped defect this session).
- **Sim: NOT RUN.** Owed: the wave's flows (`07-matches-tile-scoped`, `matches-awaiting-dismiss` + 500-injection leg, `trades-banner-region`, repointed `p0-6-espn-copy-trade`) + the standing #295 Tier-1 debt (`d3`/`d4`). Known stale pre-existing: `smoke/09-league.yaml` waits on `league.hero` at a tab root that has been `LeagueRankings` since #181. `release-inline-strip.json` cannot exist as planned (experiment overlay ≠ flag key) — the #314/#315 flow runs under plain `release`.
- **QA riders:** #309 — verify real send buttons on the awaiting + calculator mounts for MFL/ESPN (operator retracted their confirmation; tripwire OPEN). #318 — server-fired `awaiting_trade_dismissed` verifies on first real dismissal (route liveness proven 405→401; the event needs a session).

---

## 2026-08-13 — Dropped-emitter backlog registration (built on branch; NOT shipped — bright-line hold)

- **Change:** branch `claude/elegant-mccarthy-ef63f8` (worktree), from `origin/main` @ `60fccc7`, rebased onto `1e69562`. 27 long-dropped mobile `track()` names registered in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` (props mirror the shipped emitters verbatim), 8 of them added to `NON_INTENT_EVENTS` in the same change; client `quickset_completed` emitter deleted from `QuickSetTiersScreen.tsx` (server-authoritative name, disjointness assert). Addendum: `docs/business/analytics/2026-08-13-dropped-emitter-backlog.md`; cross-client-invariants + G-031 + NEXT 0h updated. Zeroes the G-031 backlog.
- **Verified:** import-time asserts pass (namespace disjointness + props coverage; direct import probe). `pytest backend/tests/test_events_api.py backend/tests/test_analytics_p0.py -q` → **64 passed**. `pytest backend/tests/test_api_observability.py backend/tests/test_mock_draft.py backend/tests/test_pick_assignment.py -q` → **179 passed**. Mobile `npx tsc --noEmit` exit **0** (run in the worktree via a node_modules symlink from the main checkout).
- **NOT verified yet:** deploy-then-probe — owed post-ship for at least one newly registered name (`accepted ≥ 1 AND dropped == 0`, with `X-Device-Id` set, per the build-110 trap).
- **Sim gate: not applicable** — backend registries + one telemetry-line removal; zero user-visible behavior. Maestro delta n/a for the same reason.
- **SHIP EVIDENCE (2026-08-14, post-merge):** squash PR [#116](https://github.com/mattmurf77/fantasy-trade-finder/pull/116) → `main` @ `4733f78`; PR CI green (backend-tests 6m7s, mobile-typecheck 43s, maestro-testid-lint 7s). **Deploy-then-probe PASSED:** `help_opened {topic: matching}` posted to prod `POST /api/events` with `X-Device-Id` set, polled through the deploy — old build answered `{"accepted":1,"dropped":1}` twice (the accepted-and-dropped trap, caught by the strict condition), new build answered `{"accepted":1,"deduped":0,"dropped":0,"rejected":[]}`. Branch swept per `docs/recovery/2026-08-14-taxonomy-batch-sweep.md` (tip `7016850`, content-verified empty diff vs post-merge main).

---

## 2026-08-13 — Device-auth S0 (FAAB fix shipped; vault + Sentry scrub held, Maestro waived)

- **Change:** S0, the ship-now bundle (Plan §12). **Lane A — FAAB GraphQL object-literal fix: SHIPPED to `main`** (`79123a0`), backend-only so the pre-push sim gate did not apply. **Lane B — `credentialVault.ts` + legacy migration + Sentry credential-leak scrub: built, tested, HELD** on `feat/s0-bundle` awaiting an unrelated release. **Maestro gate WAIVED by the operator** ("Waive the Maestro gate"); no flow was authored or run.
- **The waiver is defensible on this change specifically:** S0 adds **no user-visible surface**. `credentialVault.ts` is referenced by no other module (verified by `git grep`), and the Sentry change is init config. There is nothing for a flow to drive. This does **not** extend to S4/S5, where the transport becomes reachable.
- **Backend:** `pytest backend/tests -q` → **2694 passed / 1 skipped / 0 failed** (286s). **Note the discrepancy with the entry below**, which recorded 6 `test_rookie_scope.py` failures: those are [G-028] — they fail only in checkouts carrying real data, and this is a clean worktree with no `data/` DB. **My green is the easier condition, not a fix.**
- **FAAB fix proven failing-first:** the 3 new tests were run against the pre-fix module via `git stash` → **2 failed / 1 passed**; against the fix → **3 passed**. The bare-key assertion and the injection-guard assertion are the two that flipped.
- **Mobile:** every `check-*.js` in `tests/` and `scripts/` → **24 passed / 0 failed** (22 pre-existing + 2 new). `tsc --noEmit` exit **0**, zero errors.
- **`check-keychain-accessible.js` is sabotage-proven:** appending a bare `setItemAsync("k","v")` to the vault made it exit 1; removing it returned exit 0. Its first cut was **too literal** — it demanded the accessibility inline and so failed the real code, which passes a `WRITE_OPTS` const. Fixed to resolve a same-file options identifier. A check that only passes when the option is inlined would have been abandoned the first time someone refactored.
- **`check-vault-subsumes-legacy.js`: 5/5** — migrate deletes the legacy slot and the token lands in the vault; **a simulated write failure RETAINS the legacy slot** (never delete-then-lose); no legacy slot ⇒ `none` with no vault write; a `user_id` mismatch returns `null` and does **not** wipe (D-047).
- **Sentry scrub behaviourally verified, 9 assertions** (drops credentialed-host fetch breadcrumbs incl. mixed-case host, keeps our-API and non-fetch crumbs, strips `request.headers`/`request.data`, keeps `request.url`, tolerates absent fields).
- **NOT verified anywhere — stated plainly:** nothing in lane B has executed on a simulator or a device. `WHEN_UNLOCKED_THIS_DEVICE_ONLY` actually excluding the item from an iCloud backup, Keychain survival across app update/reinstall, and the Sentry scrub's behaviour against a **real** captured event at tracing 1.0 are all device facts (LLD §6.6 items 1, 3, 5) and remain owed at Gates D/E. The vault has never run on hardware; its tests run against an in-memory SecureStore mock.
- **Analytics: none added, and none were needed.** S0 emits zero events — the diff adds no `track()` call site and the vault is unreferenced. Instrumenting dormant code would be dead instrumentation. The spec for the events S4/S5 **will** owe (closing OI-20, plus a `platform_vault_migrated` event the LLD never named) is in [`../docs/plans/device-side-platform-auth-analytics-spec-2026-08-13.md`](../docs/plans/device-side-platform-auth-analytics-spec-2026-08-13.md).

## 2026-08-13 — #295/#296/#305 mock-draft repair + manual mode (sim gate NOT run; Tier-1 owed)

- **Change:** `e71a654` (PR #114), v1.13.3 **build 110**. Five membership sites, `UserNotInDraft` raise, `user_not_in_draft` ladder rung, `mode: cpu|manual`, five-event analytics family.
- **Verified (merged tree, orchestrator-run):** `pytest backend/tests -q` **2714 passed / 1 skipped**; `tsc --noEmit` exit 0; `testid-lint OK`; ten `check-*` suites exit 0 (incl. new `check-mock-draft-modes` 78, `check-mock-user-not-in-draft` 18 — both proven red on the pre-build tree first: 27 and 8 FAILs).
- **Falsification: 34 named sabotages** (19 backend + 15 mobile), all RED-then-green, apply-verified per mutation. Live engine demonstration of the operator's slot-8 scenario ran before go/no-go — four clauses asserted, not narrated.
- **Sim gate: NOT RUN.** PRD recommends **Tier 1** (full-surface change to a feature that never worked; the prior two mock batches shipped without a sim run and the first is why the bug existed). Flows authored + lint-clean, never executed: `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` (retargeted to `draft-pre`), `d4-mock-manual-mode.yaml`. No `last-sim-run.json` written — not fabricated. **Owed at the next sim session, both flows + the blocked-entry state.**
- **Deploy-then-probe: PASSED in prod.** Five events posted with full property sets → `{"accepted":5,"dropped":0}` → every prop read back from `user_events.props`. **New trap documented:** the deploy-liveness poll must require `accepted ≥ 1 AND dropped == 0` — the old build answers `accepted:1, dropped:1` (envelope fine, type dropped), which a loose grep reads as live.
- Standing caveat: none of the twelve `check-*.js` suites run in CI.

---

## 2026-08-13 — Notification inbox growth surface phase 1 (SHIPPED to `main`)

- **Change:** five commits, rebased onto `3b64a44` and merged to `main` on the operator's ship directive (which also resolved the `counter_offer` four-not-five question and ratified the two adjacent dead-tap fixes). Taxonomy registration → backend inbox rows + coalescing + server-side dismiss → both clients (glyphs, routing, instrumentation, empty state) → docs. `express`-equivalent gate posture: **sim gate SKIPPED, `FTF_SKIP_SIM_GATE=1`**, per D-P1-08 restated in the build brief.
- **Backend:** `pytest backend/tests -q` → **2685 passed / 6 failed / 1 skipped**. The 6 failures are all in `test_rookie_scope.py`, are **pre-existing on `origin/main`** (verified by `git stash`-ing every change and re-running that file alone, which failed identically), and are **local-only**: CI runs Python 3.12 and is green on `main` (`gh run list --workflow ci.yml`); local is 3.14. **Not caused by this work, and not fixed by it.**
- **New:** `backend/tests/test_notif_inbox_growth.py` — 13 tests over the three things whose failure mode is silent: GD-8 coalescing (one row per league per UTC day, incl. the yesterday boundary and the dismissed-row-is-not-a-target case), the `match_expiring` idempotency gate (incl. cross-type metadata comparison and the fail-closed path), and server-side dismissal (retention, per-user scoping, and that clearing is point-in-time rather than a mute).
- **Mobile:** `npx tsc --noEmit` exit 0; `bash scripts/testid-lint.sh` OK; `node tests/check-notif-glyphs.js` **5/5**.
- **`check-notif-glyphs.js` earned its keep on its first run.** It failed immediately on `trade_accepted` / `trade_declined` — the DB writes `f"trade_{outcome}"` while only the push kind `match_accepted` was in `V2_MATCH_KINDS`, so two of the four ORIGINAL inbox types had a glyph and a dead tap. Code review had not caught it; the test did, before any of this shipped.
- **Web:** `node --check web/js/app.js` clean. **No web test harness exists**, so web's glyph map, tap router and the new `dismiss-all` call are covered only by the parity test's source-text assertions. The `switchView('matches')` fix and the dismiss round-trip have **never executed in a browser**.
- **NOT verified anywhere:** every row template, the new empty state, the empty-state invite gate, and all three analytics emitters. Nothing has rendered on a simulator or a device. The four backend write sites have not fired against a real DB — their tests exercise the DB helpers directly, not the routes.
- **Simulator gate + Maestro: WAIVED** under **D-P1-08**, restated by the operator in the build brief. No `qa/sim-runs/last-sim-run.json` written — **not fabricated**.
- **Standing caveat, unchanged and now one suite worse:** no `check-*.js` suite runs in CI (`.github/workflows/ci.yml` runs pytest, `tsc`, and testid-lint only). `check-notif-glyphs.js` therefore **gates nothing**, on a cross-client enum whose whole failure mode is silence.
- **SHIP EVIDENCE (2026-08-13, post-merge):** squash PR [#113](https://github.com/mattmurf77/fantasy-trade-finder/pull/113) → `main` @ `2b63511`; PR CI green (backend-tests 7m32s on Python 3.12 — **confirming the 6 rookie_scope failures are local-3.14-only**, mobile-typecheck, testid-lint). Render deploy confirmed live by route probe: `POST /api/notifications/dismiss-all` answers **401** (session required), not 404. **Analytics probe PASSED**: the three names posted to prod `POST /api/events` with `X-Device-Id` set → `{"accepted":3,"deduped":0,"dropped":0,"rejected":[]}` — positive acceptance, not the `no_identity` false-pass shape. Branch swept per the recovery ledger (`docs/recovery/2026-08-13-notif-inbox-growth-sweep.md`, tip `cbbd08c`, content-verified empty diff vs post-merge main). EAS iOS build **109** (v1.13.2) **FINISHED** (status read via `eas build:list --json`, never the exit code) with TestFlight submission `9668b9b2` scheduled at build time (`--auto-submit`); this eas-cli (21.6.x) has no submission-status command, so ASC arrival is confirmed via the expo.dev submissions dashboard / TestFlight itself.

---

## 2026-08-12 — Feedback #300 (position-scoped trade candidates), shipped LIT with gates waived

- **Change:** `5139b45` (PR #112), v1.13.1 **build 106**, both flags **ON**. Backend `medians` field on `/api/league/power-rankings`; mobile divider + Buyer/Seller bands + stacked-roster drill-in + Offer/Target handoff; rules A and B removed ([D-044](DECISIONS.md)); two analytics events.
- **Verified on the merged tree, re-run by the orchestrator rather than taken from agent reports:** `pytest backend/tests -q` **2610 passed / 1 skipped**; `tsc --noEmit` exit 0; `testid-lint OK`; `check-league-drill-in` 29; `check-analytics-297-302` 35; `check-single-pin-actions` 17; `check-league-candidates-300` 67; `check-picks-subset-invariance` 72; `check-analytics-300` 51. **271 structural assertions.**
- **Falsification:** 40 + 12 + 42 sabotages executed across the three build rounds. **One genuine false pass found and fixed** (S21: dropping `if (!query.isFetched) return` left the suite green because the assertion matched an identifier that also appears in the dep array). That is the **fifth** false-passing test caught in this session across five independently authored suites.
- **Simulator gate: WAIVED by operator. Maestro execution: WAIVED by operator.** `06-position-trade-candidates.yaml` is authored and **has never run**. No `last-sim-run.json` written — not fabricated. **The 44pt hit-slop treatment, the divider and the rule-A removal have never executed on a device or simulator.** The operator confirmed the shipped build behaves in TestFlight, which is the only runtime evidence in existence for this feature.
- **Analytics verified in production.** Deploy-then-probe run post-merge: 4 events posted, `{"accepted":4,"dropped":0,"rejected":[]}`, then every property read back out of `user_events.props` — both `league_pos_candidates_viewed` rows and both `league_candidate_pinned` mirror combinations `(offer, below)` / `(target, above)`. Note the trap this gate exists for: without `X-Device-Id` the response is `{"accepted":0,"dropped":0,"rejected":[{"reason":"no_identity"}]}`, which has `dropped == 0` and reads as a pass.
- **Still true and worth repeating:** none of the six `check-*.js` suites run in CI. They are `npm run`-only, so **none of the 271 assertions gate anything**.

---

## 2026-08-12 — P1 audit remediation shipped (sim gate retired by operator, not waived)

- **`express`: P1 remediation shipped — simulator gate SKIPPED, `FTF_SKIP_SIM_GATE=1`.** Not a
  one-off waiver: operator decision **D-P1-08** retires the Maestro/simulator/screenshot
  apparatus as standing policy — it consumed more budget than it returned and its quality
  degraded as the surface grew. **TestFlight is now the primary QA method.** No
  `qa/sim-runs/last-sim-run.json` written — **not fabricated**. The pre-push hook fired and was
  overridden deliberately, with the operator's explicit go. `CLAUDE.md`, `githooks/pre-push` and
  `docs/runbook.md` still describe the old policy and are **owed an update** (D-P1-08).
- **Verified instead:** full backend suite **2663 passed / 1 skipped** (3m51s) on the rebased
  tree; `npx tsc --noEmit` clean against a fresh in-worktree `npm ci`; `testid-lint` exit 0;
  `check-anchor-labels.js` 20/20; `check-invite-social-proof.js` 13/13. Baselines measured on
  this tree before editing, never quoted from another branch: 2467 → 2504 (P1-7) → 2663 (after
  rebase onto `main` plus the two pre-ship fixes).
- **NOT verified on device.** Five changed anchor rung labels, the anchor progress hint, both new
  invite surfaces and the share-image footer are visual and have never rendered on a simulator or
  a phone. This is the accepted cost of D-P1-08 and is owed on the TestFlight pass.
- **Sabotage-proven guards.** The anchor-label AST walker **false-passed on its first cut** — it
  inspected only the root of each initializer, so `key === '1_second' ? '1 2nd' : anchorLabel(key)`
  slipped through; fixed to walk the whole subtree, all five mutations now fail as intended. The
  tier-route 404 was proven to come from the flag guard rather than a missing route (body shape +
  `url_map` membership). The `league_id` scrub exemption was proven narrow three ways: an email
  under the same key is still redacted, a long digit run under any other key is still redacted,
  and the allowlist is exact-key rather than substring.
- **Analytics NOT yet proven end-to-end.** T1 registration ships in this push, but the corrected
  probe (**HLD §H-6**: `X-Device-Id`, valid envelope, `accepted > 0` **and** `dropped == 0`, then
  a read-back of `user_events.props`) runs against production **after** the Render deploy. Until
  it passes, treat every new event as unproven — the endpoint returns 200 while dropping. The
  original probe spec in this round would have passed against a broken build; that is why it was
  corrected before use.
- **Not shipped, deliberately:** email capture (built, then **reverted in full** — flag, policy,
  docs and living-memory — by operator decision: the sequencing was backwards and no
  email-sending infrastructure exists to consume it), P1-9 trade push and P1-10 Sleeper analytics
  (both still hold unanswered build-blocking decisions), P1-11 (dropped, D-P1-01).

---

## 2026-08-12 — Send in MFL + Send in ESPN shipped live (sim gate WAIVED all session, CI never ran)

- **`express`: Send in MFL + Send in ESPN + platform unlink + ESPN credential verification shipped — gates skipped by operator.** `FTF_SKIP_SIM_GATE=1` on every push (warning emitted each time); **no `qa/sim-runs/last-sim-run.json` written — not fabricated**. CI never ran: the operator directed direct-to-`main` pushes rather than PRs. `main` moved `3293f4a` → `cad99fb`.
- **Verified instead of CI**, per push: targeted backend suites (178 → 135 → 123 → 122 depending on surface), 12→18 `mobile/tests/check-*.js` including main's own P0-6/P0-7 pins, `testid-lint` exit 0, `tsc --noEmit` clean on a fresh in-worktree `npm ci`. The full ~2,400-test suite was **deliberately not run** — it stalled four separate agents mid-session.
- **Sabotage-proven guards** (each failed first, then restored): MFL pick hard-block (guard removed ⇒ the mocked write was reached with the pick silently dropped); ESPN pick + unmapped-asset hard-blocks; **cross-user unlink isolation** (removing the `WHERE user_id` clause made another user's row deletable — the security property that mattered most).
- **TestFlight 1.13.0 builds 102/103/104/105, then 1.13.1 build 107.** Every status read from `eas-cli build:list --json`, never the exit code — **`eas build` exits 0 even when the remote build ERRORED** (a concurrent session lost builds 99/100 that way). Build 106 was another session's. **Build-ordering lesson: flags are server-side, so `espn.send` could not be enabled until a build containing the lazy send-triggered auth existed (103) — enabling a flag whose client code is absent from the installed build *degrades* it.**
- **Live production verification, by content not by uptime:** `/api/feature-flags` serves `trade.send_in_mfl: true` and `espn.send: true` (neither key existed before); `DELETE /api/espn/link` and `DELETE /api/mfl/auth-link` both return 401 unauthenticated (route live and auth-gated, not 405).
- **MFL write path LIVE-VERIFIED** — a real 2-for-2 proposal succeeded from the app (`trade_sent {platform:"mfl", outcome:"proposed"}`). Because the adapter **refuses ambiguous success**, that outcome is positive evidence the real import response parsed unambiguously. `pendingTrades` also read live: field vocabulary confirmed, `FP_0002_2028_2` confirms the pick encoder against a real trade.
- **ESPN write validated without spending a real trade** — negative probes with a nonexistent `relatedTransactionId` returned 409 `TRAN_NOT_FOUND` for both `TRADE_ACCEPT` and `TRADE_DECLINE`, and `items:[]` returned 409 `TRAN_INVALID_TRADE_TEAM_COUNT` for propose. Both are validation-class errors only reachable *after* auth, so auth + envelope + `type` are all confirmed while nothing real was touched. **No real ESPN send has been made from the app — that remains owed.**
- **Sleeper iOS reachability probe: PASS 4/4** (Chrome-spoofed and honest headers × Wi-Fi and cellular, all HTTP 200), run from TestFlight build 107 and reported via `sleeper_probe_result` analytics rather than transcription. Probe shipped, run, and **deleted the same day**; result in `../docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`.
- **Analytics correctness checked, not assumed:** `trade_sent`'s NULL top-level `platform` column initially looked like a repeat of the NULL-`platform` incident. It is not — that column is the *emitter* (`ios`/`server`), the fantasy platform lives in `props.platform`, and `sleeper_send_succeeded` behaves identically. New event names were added to `NON_INTENT_EVENTS` in the same commit that registered them.
- **Flag-mirror trap fired twice.** Any new key in `config/features.json` must be mirrored into `release.json`, `onboarding-v2.json`, and `profiles-on.json` or `test_seed_ui_test_db.py` fails (69 tests). Caught both times before push.
## 2026-08-11 — P1-7 anchor + manual unlock, derived rung labels (NOT merged, branch-only)

- **Change:** branch `p1-remediation-2026-08-11`, three commits. (1) Per-method unlock ladder — `'anchor'` gains its first arm (audit A-16: it could never unlock), `'manual'` loses its unconditional `True` (A-17), both reading `RankingService.board_override_count()`; `_tiers_rule()` extracted; `database.backfill_anchor_unlocked_formats` added as the first-unlock fan-out suppression; additive `anchor_count`/`anchor_required` on `GET /api/rankings/progress`. (2) Anchor rung labels derived from `TIER_LABEL` (five of eight had drifted, not the two the audit found) + `mobile/tests/check-anchor-labels.js` + the wizard's unlock hint + `anchors.rung.*` testIDs. (3) The `anchors-done` seed profile and its `app_user.anchors` seeder handler.
- **Verified (this worktree, re-run after every commit):** `pytest backend/tests -q` **2504 passed / 1 skipped**, against a **2467 / 1 baseline measured on this same tree before the first edit**. The +37 is fully accounted for and contains no pre-existing failures: `test_anchor_unlock.py` **29 new** (one case parametrized ×2), `test_pick_anchor.py` 17 → **18** (the D15 lane-separation assertion), `test_seed_ui_test_db.py` 69 → **76**. `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-anchor-labels.js` **20/20**.
- **Falsification — and it earned its keep.** Every assertion in `check-anchor-labels.js` was run against a deliberately sabotaged tree. **The first cut false-passed on the single most important mutation:** re-typing a label as `label: key === '1_second' ? '1 2nd' : anchorLabel(key)` — the original defect wearing a ternary — because the assertion inspected only the *root* of each `label` initializer. This is exactly the case the design cited as the reason an AST walk beats a grep, and the AST walk fell into it anyway. Fixed to search the whole initializer subtree and to whitelist two exact initializer shapes; all five mutations (ternary, template literal, indirection through another function, `no_value → 'waivers'`, inlined `BELOW_LADDER_LABEL`, dropped `ANCHOR_TIER` key) now fail as intended. Same family as [G-035](GOTCHAS.md).
- **The seed fixture proves the unlock rather than assuming it.** `anchors-done.json` seeds `unlocked: false` deliberately — a seeded `unlocked_formats` row satisfies the monotonic floor *before* the new branch is consulted, so the obvious fixture would have gone green with the fix reverted ([G-037](GOTCHAS.md)). `_validate_anchors` now **refuses** the incoherent shape, and `test_anchors_done_actually_clears_the_unlock_bar` builds a real `RankingService` from the seeded board and asserts it clears the bar — so the fixture and the branch are proven to meet, not assumed to.
- **Sim run: none.** Per [D-P1-08](../docs/plans/audit-p1-remediation/DECISIONS-p1.md) the Maestro/simulator apparatus is retired and TestFlight is primary QA. No `last-sim-run.json` written — **not fabricated**.
- **Not verified on device, and it should be:** the wizard's new unlock hint (`anchors.unlock-hint`) and the five changed rung labels are visual changes no automated gate here can see. `check-anchor-labels.js` proves the labels are *derived*; it cannot prove they *render*. **Owed on the next TestFlight pass.**
- **Same pre-existing gap as the batch below:** none of the `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`, so `check-anchor-labels.js` **gates nothing** until that job is wired. It is a `npm run test:anchor-labels` a human has to remember.

## 2026-08-11 — Feedback #297/#298/#299/#302 + batch analytics (sim gate DEFERRED, operator-directed)

- **Change:** branch `feedback-integration-v2`, cut from `origin/main` @ `f65bab7`, merging `feedback-build-league-299-302` and `feedback-build-trades-297-298` plus an analytics round. #297 honest-empty lineup row; #298 single-pin deck recovery (V1) + the team-pill regenerate defect; #299 32pt League roster tiles (−47%, 728pt reclaimed on a 26-man roster, 4 → 8 players above the fold); #302 stack-header drill-in exit + the first Android `BackHandler` on that screen. Analytics: two new client events (`lineup_impact_unavailable`, `league_team_closed`), three widened props (`mode` on `find_trades_tapped` + `trade_card_viewed`, `source` on `find_trades_tapped` — the last a **bug fix**, that prop had been sent into an empty registry and popped on every row since #257).
- **Verified (merged tree, this worktree, re-run by the orchestrator — not taken from agent reports):** `pytest backend/tests -q` **2452 passed / 1 skipped**; `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-single-pin-actions.js` **17/17**; `check-league-drill-in.js` **29/29**; `check-analytics-297-302.js` **35/35**. 81 structural assertions total.
- **Falsification:** every behavioural assertion was run against a deliberately sabotaged tree — 30 (league) + 9 (trades, four aimed at the seam #169 created) + 20 (analytics). **Four false-passing tests were caught this way and fixed**, in four independently authored suites: an ancestor-walking JSX gate check ([G-035](GOTCHAS.md)); a first-element-only testID lookup; a platform assertion that survived a sabotage leaving the lookup line in place; and three raw-source scans matched by comments naming the constructs they forbade. Treat "my test passes" as unproven here until a sabotage fails it.
- **Sim run: DEFERRED by operator** ("Good to signoff that we ship without a flag & defer the sim gate"), after the bright-line disclosure that the batch touches analytics surfaces. **No `last-sim-run.json` written — not fabricated.** Two Maestro flows authored but **NOT executed**: `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` and `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml`.
- **The Android hardware `BackHandler` was WITHDRAWN from this ship, not verified** (operator, 2026-08-11) — precisely because no Android device or emulator was involved at any point and TestFlight is iOS-only. Removing it is what closes the batch's largest unverified-code gap. Two assertions now pin the withdrawal (a live registration turns both suites red), and both were **sabotage-proven** by re-adding the effect and confirming each suite fails. `'hardware_back'` remains a reserved analytics value with no emitter. **Owed with the first non-App-Store release:** restore the effect, flip both assertions in the same commit, and exercise it on a real Android device.
- **Owed at ship, not skippable by the sim-gate deferral — the deploy-then-probe gate.** After merge + Render deploy, hand-roll one `POST /api/events` per new name with its **full** property set and assert both `dropped == 0` **and** every property echoed back out of `user_events.props`. Name-survival and prop-survival are separate silent failures: `analytics_ingest.py` pops unregistered props with only a counter bump, and `trade_card_shared.landing` is a live in-tree example of a registered name whose prop is discarded. **Do not substitute `GET /api/admin/analytics/health`** — its counters are in-process and reset on deploy.
- **Pre-existing gap, now three times larger:** none of the ten `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`; they are `npm run`-only. **None of the 81 assertions above gate anything** until that is wired. Proposed job in `docs/feedback/items/297-lineup-impact-single-pin/status.md` §5.5.

## 2026-08-11 — P0 remediation batch (sim gate SKIPPED, operator-directed express)

- **Change:** branch `p0-remediation-2026-08-10` — eight P0 launch blockers from the 2026-08-09 mobile UX audit (P0-1/2/3/5/6/7/8 + P0-9 test-prep), 15 code commits + merge of #169. Full corpus in `docs/plans/audit-p0-remediation/`.
- **Verified (merged tree, this worktree):** `pytest backend/tests -q` **2448 passed / 1 skipped / 0 failed** (clean worktree — the 6 environmental `test_rookie_scope` failures of the data-carrying main checkout do not reproduce here, consistent with G-030[#169]); `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-trade-text.js` 28/28; `check-card-disposition.js` 10/10; taxonomy registration verified name-by-name (16 client + 1 server, zero unregistered emissions — grep table in the W2-P07 build record).
- **Sim run: tier-1 SKIPPED entirely** (operator: "proceed without the sim gate — eating up too much usage", confirmed after bright-line disclosure: batch touches route + flag + analytics surfaces). Push via `FTF_SKIP_SIM_GATE=1`; **no `last-sim-run.json` written (not fabricated)**. Pre-skip on-sim work: app built green (Release, localhost-pinned), dedicated simulator created, pre-flight of all six new flows (every copy string + testID resolves in source), control-run evidence prepared (`git grep` at ab9368f proves the new testIDs absent pre-fix, so the flows fail by construction on the unfixed tree). Runs were blocked twice by another session holding :7001/:5001 before the operator called the skip.
- **Tier decision (recorded for the record): tier 1**, not 2 — the batch adds a screen, changes navigation, and changes rendered state on six screens; tier 2 is "mobile logic, no UI change".
- **Owed at next sim session:** the full tier-1 set + the batch's six new flows (`p0-1-quickset-unlock`, `p0-5-account-only-picker`, `p0-6-espn-copy-trade`, `trades-generation-failure`, `guide-no-false-signoff@release`, `league/invite-join`) + modified captures (`trades`, `matches@espn`, `league@quickset-done`, `leagues@account-only`, `onboarding-tour@fresh`); the P0-9 flag-pinned beat validation incl. the s5.1 proof (use the now-registered `deck_regenerated` row); analytics destination checks; re-captures + freshness sweep (note: TabNav changes are analytics-only — PNGs stay visually accurate, hash-staleness flags under the corrected manifest are false positives).
- **Toolchain gotcha (load-bearing for every future worktree build):** the standing convention of symlinking `mobile/node_modules` from the main checkout makes the app UNBUILDABLE — expo's CLI branches on whether its own directory resolves inside the project root and then requires `metro-runtime`, which is not top-level in this lockfile. Real in-worktree `npm ci` + `pod install` required; `rm -rf mobile/ios/build` also deletes RN codegen sources, so re-run `pod install` before rebuilding.

## 2026-08-11 — #169 frame E + card frame C (sim gate DEVIATION mid-run, operator-directed)

- **Change:** branch `feedback-169-e-and-card` — League Summary collapsed outlook strip (flag-dark, `outlook.odds`) + Pass/Like moved inside the top deck card + `outlook_strip_toggled` analytics event (taxonomy + tracking plan; operator rejected the dark-flag analytics waiver). Doc set (plan/HLD/LLD/PRD/scope rev 2, adversarially reviewed, 21 findings applied) in `docs/feedback/items/169-outlook-league-summary/`.
- **Verified (merged tree):** `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-card-disposition.js` 10/10 **with double sabotage proof** (guard flip → FAIL; reintroduced TradesScreen testID → FAIL; restored → pass); taxonomy test 18/18 **with sabotage proof** (event removed from allowlist → FAIL → restored). Full `pytest backend/tests -q`: **2371 passed / 6 failed / 1 skipped** — all 6 in `test_rookie_scope.py`, **proven pre-existing and environmental** (fail with origin/main-identical backend bytes in the data-carrying main checkout; 34/34 pass in a clean worktree of the same commit; G-028, fix chip filed). CI on the PR is the clean-environment authority.
- **Sim run: Tier-1 HALTED mid-gate by operator** ("proceed without sim testing — eating up too much usage"); push via `FTF_SKIP_SIM_GATE=1`; no `last-sim-run.json` written (not fabricated). **Partial on-sim evidence before the halt:** extended `06-trades-deck` positional `childOf` asserts PASSED (both disposition buttons proven inside `trades.card-top`, no scroll — fails by construction on the old layout); screenshot proof of the operator's layout; `01-signin` full pass in the final harness config; manual launch-health check. Suite-level failures across 4 attempts were ALL environmental, diagnosed in sequence: `# flags: release` fixture not loaded (guided-avatar tour overlay swallowed taps), backend process reaped by shell teardown, **disk exhaustion to 0 bytes** (25 launch crash-loops in Hermes init — G-027 adjacent; ~4 GB freed), stale Maestro XCTest driver after `simctl erase`. None traced to the change under test.
- **Owed at next sim session:** green full-suite run; post-overlay like/pass tap-through of `06-trades-deck`; the four re-captures (`trades`, `matches`, `sheets-trade-dna`, `league-summary`) + `screen-freshness.sh` sweep; on-sim verification of the three re-derived `onboarding-tour@fresh` anchors.

## 2026-08-10 — Screen-library capture suite (sim gate tier-2 evidence)

- Full consolidated sweep on FTF-iOS18 (iOS 18.4): 43 capture flows, 7 cells
  (5 profiles × release/onboarding-v2), **102 captures, rails all zero in every
  cell** (vcr_misses / sleeper_live_egress_attempts / completed_proposes /
  propose_route_hits). One flaky flow (trios@near-unlock, tab-race — settle fix
  applied, still ~50% per run) recaptured green individually. tsc clean,
  testid-lint green, screen-freshness green ×25, backend suite 2207 passed
  (fixtures commit). Mobile app-code delta this branch: testRouteEntry.ts +
  one RootNav line — exercised by every launch-arg capture cell above.
## 2026-08-10 — Feedback batch #289-#294 (sim gate DEVIATION, operator-directed bypass)

- **SHIPPED 2026-08-10.** Squash-merged as `6c304c7` via PR #103; CI green (backend-tests, mobile-typecheck, maestro-testid-lint). Render deploy **verified by content**, not by uptime: `/api/feature-flags` serves `league.picks_always_counted = true` (155 flags), which only the new build can produce. iOS **1.12.0 build 98** uploaded to App Store Connect (submission `0095a36f`).
- **Version-bump trap, cost one wasted build.** `mobile/app.json` was bumped to 1.12.0 and **build 97 still shipped as 1.11.0**. This is a bare workflow — `mobile/ios/` is tracked — so EAS reads the version from the native Xcode project and ignores the Expo config. `eas build:version:set` manages the **build number** only. The three values that actually ship are two `MARKETING_VERSION` entries in `project.pbxproj` and the literal `CFBundleShortVersionString` in `Info.plist` (PR #104, `7553874`). Bumping `app.json` is necessary for the JS layer and **not sufficient for the binary**.

- **Change:** six feedback items in three groups on branch `feedback-289-294` (base `origin/main` @ `16b1dcb`), 16 commits, 51 files, +15,738/−106. **G1 #289** MFL Draft Room resolves franchise *and* player names (four ordered tiers, never a bare id). **G2 #290/#291/#292** value-aware mock run model + `need_pressure` + mock lifecycle (`abandon_completed_mock_drafts`) + pick affordance before tap + MFL owner names in the mock. **G3 #293/#294** draft-pick value counted in every subset and position filter, behind new flag `league.picks_always_counted`, **graduated to ON at ship by operator direction** ("293/294 ship live") together with its `LAUNCHED_FLAG_DEFAULTS` entry so it is visible from first paint; the flag remains the kill switch. Plus: `mobile/scripts/sim-run.sh` flag-pin repairs, five stale "mock is OFF" doc locations corrected, D-022/D-023/D-024.
- **Suite:** baseline `2308 passed / 1 skipped` after G1+G3 → **2326 passed / 1 skipped**, exit 0 (+18, all new). `npx tsc --noEmit` **exit 0** (real `npm ci` in-worktree — the main checkout's `node_modules` is ~190 commits stale and lacks `@react-native-cookies/cookies`, which yields a phantom error). `testid-lint.sh` **exit 0**. **All nine** `mobile/tests/check-*.js` pass, including two new ones (`check-picks-subset-invariance.js` 71 assertions, `check-mock-lifecycle.js` 52).
- **Sim run: NOT PERFORMED** — operator-directed bypass (`FTF_SKIP_SIM_GATE=1`) after being presented with the coverage gap and choosing it explicitly. **This is a Tier-1 deviation and the batch's largest change is the least covered:** G2's mock engine ships with unit + distributional evidence only and **no end-to-end run**. **Both groups ship live.** G3 was built dark and graduated to ON at ship on operator direction; it keeps a per-feature kill switch (`league.picks_always_counted` -> false, no redeploy). G2 has no per-change switch — `draft.mock` was already ON and the engine change is unflagged — so its only lever turns off the whole mock feature. G2 is therefore the largest change, the least covered, AND the least reversible.
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
