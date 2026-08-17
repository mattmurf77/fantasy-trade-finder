# Build verification — trade presentment rules (G6, 2026-08-16 wave)

> Build-phase evidence per D-056 (no Maestro/simulator): sabotage-proven
> pytest, deck-eval replays with two-sided bands, code-walk proof
> ([code-walk-proof.md](code-walk-proof.md)). Branch
> `feat/fb304-presentment`, base `56856f7` (= origin/main `96f6945` +
> Phase-1 specs; `3c0541c` suggestion.telemetry-ON verified in ancestry).

## 1. Pytest

- `backend/tests/test_presentment_rules.py` — **45 passed** (predicate
  boundaries, engine-level kills through v3/v2/consensus/sweetener/relaxed
  paths, R4 DB + engine + injector, R-5b derivation + wiring pins, R8
  byte-identity proxies, R9 tripwire, R10 serialization contract).
- Regression on touched modules: 281 passed across the trade/deck suites
  (test_trade_engine_v2, test_trade_optimizer, test_trade_gen_prune/_v2,
  test_trade_phase2/_tier2, test_trade_intent_modes, test_trade_match_flow,
  test_user_gain_gate, test_filler_threshold, test_pick_swap_gate,
  test_pick_values_in_suggestions, test_consensus_consolidation_gate,
  **test_finder_targeting** (pin enforcement, per batch-plan),
  test_relaxed_fallback, test_not_interested, test_engine_gates_config,
  test_fit_congruence, test_need_fit, test_awaiting_dismiss,
  test_dismiss_match, test_suggestion_telemetry, test_deck_exploration,
  test_deck_fatigue, test_deck_ordering).
- `python3 -c "import backend.server"` — IMPORT-OK.
- **Full backend suite on the branch: 2969 passed / 1 skipped / 0 failed
  (264s).** The base was already red on
  `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`
  (pre-existing: `3c0541c` lit `suggestion.telemetry` in features.json
  without updating the parity fixtures — verified via `git show` at
  `56856f7`); fixed here alongside mirroring `trade.presentment_rules`
  into release/onboarding-v2/profiles-on fixtures.

## 2. Sabotage protocol (every behavioral test proven RED, then green)

Runner: scripted apply → full-file pytest → revert → clean re-run
(44-test suite state at protocol time; clean run green after every revert;
the engine R3 test was added after and its control assert is its own
attribution proof).

| Sabotage (named in prd §3.1 / test docstring) | Verdict | RED tests |
|---|---|---|
| S-R1 `max(g,r)` → `min(g,r)` | RED as expected | test_r1_frac_boundary |
| S-R2 count PICK as a position | RED as expected | test_r2_picks_uncounted |
| S-R2-5 drop `presentment_ok_fn` from `_try_sweeten` | RED as expected | test_r2_sweetener_revalidation |
| S-R3a evaluate lighter side's picks | RED as expected | 3 tests (heavier-side kill, lighter-side pass, band edges) |
| S-R3b drop the band's upper bound | RED as expected | test_r3_large_pick_small_gap_passes, test_r3_band_edges |
| S-R5 internal needs/surplus swap | RED as expected | not_sure predicate + engine tests |
| S-R5 call-site needs/surplus swap | RED as expected | test_r5_engine_not_sure_surplus_kill |
| S-R5-10 full-pre-trade-roster incumbent | RED as expected | test_r5_post_give_incumbent |
| S-R5b drop server-side bypass derivation | RED as expected | test_r5b_run_trade_job_wiring |
| S-R4 reintroduce `since_days=7` into the exclusion query | RED as expected | test_r4_awaiting_like_excluded_windowless |
| S-R4 accumulate exclusion set instead of overwrite | RED as expected | test_r4_engine_overwrite_per_call_two_league |
| S-R7 add the R1 knob to the relaxed-stage overrides | RED as expected | test_r7_relaxed_pass_never_relaxes_r1 |
| S-R8 drop the flag check (`if True:`) | RED as expected | 3 tests (flag-off spy, knob-parity deck, sweetener) |
| S-R9 drop the rule-kill term from the tripwire | RED as expected | test_r9_tripwire_warning_with_attribution |

## 3. Distributional evidence (DB-1..DB-4)

**Corpus/engine drift, declared up front (DB-1's purpose):** the D-055
corpus (`deck_eval_20260815T220047Z.json`) was generated against the
production DB (110 ranked-opponent boards, 66 likes-you injections,
126 divergence cards) under a pre-`d6de017` flag set. This build
environment's permission system **blocked running deck_eval against the
production DB** (DATABASE_URL_PROD), so the live replays below ran against
the local repo DB, which holds no member boards/likes for the 9 leagues —
its decks are all-consensus. The two evidence arms are therefore split:

**(a) Exact offline predicate replay over the authoritative D-055 corpus**
(same 474 organic first-5 cards the §2 bands were derived from — the
predicates ARE the deliverable; this reproduces the Planner's measurement
to the card):

| Rule | Replay result | §2 band | Verdict |
|---|---|---|---|
| R1 #340 | **42/474 = 8.9%** | 4–16% | PASS (exact match to baseline) |
| R2 #341 | **37/474 = 7.8%**, all 37 multi-asset (420/540 1-for-1s pass by construction) | 3–14%, multi-asset only | PASS (exact match) |
| R5 proxy (need_fit<0.45 not replayable offline; window split via my audit proxy) | contender 14.9% | 7–25% band target | consistent with baseline L2 |
| Insult coverage | control-nofloor corpus: 11 likes-you insult cards; floor-500 corpus: **0** (D-055 floor, already live, kills all) | 8/8 hard floor | PASS |

**(b) Live instrumented replays, 9 leagues × 12 teams (local-state decks;
exact in-context audit incl. R5 with roster/window/format):**

| Metric | flag OFF (deck_eval_20260816T235403Z) | flag ON (…235751Z) | Band / bar | Verdict |
|---|---|---|---|---|
| Served-card rule violations (R1∪R2∪R3∪R5, organic first-5) | 30/540 = 5.6% | **0/540** | == 0 flag-ON | PASS |
| R5 exact kill rate (over flag-OFF served) | 29/540 = 5.4% | killed+refilled | 2–10% overall | PASS |
| R5 contender | 16/140 = 11.4% | 0 served | 7–25% | PASS |
| R5 rebuilder | **0/295 = 0.0%** | 0 | exactly 0 (window bug tripwire) | PASS |
| R4 kills | 0 (no like/match history — any kill = key bug) | 0 | 0 expected | PASS |
| Mean deck size | 29.7 | **29.6 (99.7%)** | ≥ 80% of flag-OFF | PASS (construction-time refill works) |
| Empty decks | 0/108 | **0/108** | < 5% | PASS |
| Insult (Δ ≤ −500, first-5) | 0 | **0** | ≤ flag-OFF, < 3% | PASS |
| Per-job counters (summed) | all 0 | R1 61,653 / R2 2 / R3 0 / R5 4,273 candidate kills | logged always | PASS (R-9 live) |
| Tripwire | — | 0 firings | 0 on healthy leagues | PASS |

R1/R2 flag-ON kill-rate bands are not measurable on the local corpus (no
divergence boards ⇒ no R1-shaped candidates; R1's 61k candidate-level
kills are enumeration-stage, exactly as lld §5/N2 specifies). Their band
evidence is arm (a) plus the unit fixtures. **The full-fidelity prod
replay (divergence boards + likes-you arms) remains an operator-run item
before/at ship** — same command, prod DATABASE_URL:
`python3 scripts/deck_eval.py <9 league ids> (flag off, then flag on)`
then `presentment_bands.py` (this branch's instrumented deck_eval emits
`presentment_audit` + `presentment_kills` per team).

**DB-4 — pick-league replay (R-12), league 1312076055586050048 (156
draft_picks rows), `--with-picks`** (deck_eval_20260817T000003Z flag-ON,
…000035Z flag-OFF control; local rows carried legacy NULL `pool_value`,
backfilled scratch-DB-only via the documented `elo_to_value(1200 +
6*pick_value)` bridge):

- 864 pick pseudo-assets injected (72/job); pick-carrying served cards
  exist (e.g. Javonte Williams → 2026 1st; DK Metcalf → 2027 1st).
- R3 kills: **0 flag-ON, 0 would-kill flag-OFF** — the local consensus
  decks construct only fair 1-for-1 player-for-pick swaps; zero #339-shaped
  candidates exist in this corpus, so the knob **cannot be tuned from this
  replay** (the corpus limitation, not a silent no-op:
  `test_r3_engine_kill_through_v2_path` proves the hook kills the #339
  shape through the live v2 path, knob-attributed).
- Per R-12's fallback clause: **shipping at defaults (0.8 / 300) with
  `pick_gap_frac` named as the tuning lever + a NEXT.md follow-up** to
  tune on a prod-state divergence replay.
- Display note: the deck-eval card record prices injected picks through
  the format seed (which lacks pick elos), so recorded pick `value`s read
  1000 and one card false-flags as Δ ≤ −500; the in-context audit uses
  the real job seed and is authoritative (that card passes all rules with
  true Δ ≈ +29).

## 4. Deviations from the PRD, with reasons

1. **U-R2-3 corrected per orchestrator mid-build message** (also fixed in
   this folder's prd.md): the original "pick+RB→2WR passes" gloss
   contradicted the R-2 formula. Implemented the formula; pick+RB→2WR
   KILLS (pinned by `test_r2_pick_plus_rb_for_two_wr_kills`), and the
   pick-exclusion discriminator is 2 picks + RB → 1 WR
   (`test_r2_picks_uncounted`, RED under the count-PICK sabotage).
2. **`need_gate_ok` signature carries `give_ids`** (lld §3's signature
   line omitted it, but its post-give-incumbent prose — round-1 B2 —
   requires it; the prose binds).
3. **`need_gate_ok` accepts `position_needs` but the hole check is the
   post-give body count** (lld §3 pseudo exactly); the value-tiered needs
   profile is threaded for the not_sure/surplus symmetry and the swap
   sabotage, documented in the predicate.
4. **U-R5-8 (declared window beats inferred)** not re-tested here: window
   resolution is upstream, pre-existing behavior (`_run_trade_job` prefs →
   `_infer_user_outlook` fallback), already pinned by test_outlook_seed;
   the predicate consumes the single resolved value (D-060, no second
   resolution path).
5. **DB-1/DB-2 full-fidelity prod replay blocked** by the environment's
   permission system (no prod-DB access from this agent). Split evidence
   per §3; operator-run replay named as the pre-ship step (fits the prd §2
   band-miss arbitration posture: report, never silently improvise).
6. **R2 picks-uncounted uses `is_pick_asset`** (position=="PICK" OR
   team=="PICK") rather than the lld's literal `position == "PICK"` — the
   universal pool's generic picks carry a real position with team=="PICK";
   "a pick is not a positional body" binds for both encodings, and R3
   already keys on the same helper (`trade_service.py:1071`).
