# Feature Scope — Package-benchmark fix + gap auto-sweetener

**Date:** 2026-08-21
**Entry point:** direct ask — operator approved 2026-08-21 ("I'm aligned. Let's fix that")
off the evidence memo [docs/reviews/2026-08-21-market-curve-comparison.md](../../reviews/2026-08-21-market-curve-comparison.md) §3b.
**Builder:** isolated worktree agent, branch `fix/package-benchmark-sweetener`.
**Merge posture:** built now, **MERGE HELD** for the operator's Monday window
boundary (change-control rule, trade-engine-accuracy PLAN Phase 0.4). Nothing
here is pushed or served until the main session ships it.
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

> **STATUS 2026-08-21 — COMPLETE on the branch, MERGE STILL HELD.** All
> three items are built, reviewed and test-green on
> `fix/package-benchmark-sweetener`; the branch is NOT pushed and NOT
> merged — the ship is the operator's Monday-boundary call.
>
> | Item | State |
> |---|---|
> | 1. Benchmark fix (`72ecd51`) | built, round-2 reviewed, clean |
> | 2. Gap auto-sweetener (`0e04d30`) | built; **two defects found and fixed in round-2 review (`49c1d76`)** — see §6 |
> | 3. `ghost_holdout_one_in` 10 → 0 (`6a61c05`) | done, all three read sites + config-reference |
> | Manual TestFlight checklist | [testflight-checklist.md](testflight-checklist.md) — written, operator runs it after the merge |
> | W0-style deck / gap measurement | run, both trees; numbers in `living-memory/TEST_LEDGER.md` 2026-08-21a; harness committed as [measure_gap_distribution.py](measure_gap_distribution.py) |
> | TEST_LEDGER entry | written (2026-08-21a) |
> | DECISIONS / CHANGELOG | **drafted, deliberately NOT applied** — [decisions-draft.md](decisions-draft.md), for the session that merges |
>
> **Owed at ship, by the merging session:** land the two drafted entries,
> then have the operator run the TestFlight checklist against the built
> app. Ratification items are listed at the end of §6.

Three changes, one branch:

1. **Benchmark fix** — `_package_value_market` depth-discounts a multi-asset
   side that does not hold the trade's best asset against the TRADE's best
   asset (`package_bench_trade_wide`, default ON; cross-side floor
   `package_floor_cross` 0.40). Kills the mid-package-buys-stud defect: the
   served Rice+Etienne+Swift+Corum → Nacua card moves 0.939 (served fair) →
   ~0.71 (blocked), between FantasyCalc (0.734) and pre-#214 heavy (0.692).
2. **Gap auto-sweetener** — `sweetener_gap_threshold` (default 1539 = one
   late 1st, the operator's agreed line): at generation time, per arm, a
   card whose absolute consensus gap exceeds the threshold gets the smallest
   sufficient equalizer asset ADDED from the richer side's roster, re-earning
   every gate; unclosable cards are kept unsweetened.
3. **Ghost holdout dies in code** (DONE, `6a61c05`) — `ghost_holdout_one_in`
   default 10 → 0 (operator ruling 2026-08-21, batch-wide; the prod DB row is
   already 0). Flipped at all three sites the value can be read from:
   `trade_service._DEFAULT_CFG`, `database._MODEL_CONFIG_DEFAULTS` (the seed)
   and `suggestion_telemetry.ghost_one_in`'s inline `_cfg` fallback — a
   non-zero fallback there would have quietly re-ghosted on any missed
   lookup. Each site carries the ruling as a comment.

## Which engines get the sweetener in v1 — decided, not silently skipped

| Path | v1? | Reason |
|---|---|---|
| v2 divergence pair generator (`trade_service._generate_for_pair_v2`) | **yes** | gap cards measured live from arm D, which overlays this path |
| consensus generator (`trade_service._generate_consensus_for_pair`) | **yes** | 84.5% of served cards; arm D's `consensus_both_ways` overlay runs through it |
| v3 optimizer (`trade_optimizer.generate_pair_trades_v3`) | **yes** | `trade_engine.v3` is ON in prod; the 3.4 sweetener machinery lives here and was generalized (`close_value_gap`) rather than duplicated |
| arm C (`trade_gen_v2`) | **follow-up** | decided by effort: arm C has its own value math (`consolidated_value`, `gen2_consol_*`), its own candidate pipeline (`_pair_survivors`) and its own gate stack — the pass would need its own integration and re-verification of the gen2 goldens, for an arm that serves only quota-capped bake-off slots. Its gap cards are real (CHANGELOG 2026-08-21 names C), so this is a named follow-up, not a skip. |
| fit arm (`trade_gen_fit`) | **follow-up** | same effort call: fit has its own enumerator/scorer/presentment pipeline and is not yet rostered for serving (`bakeoff_include_fit` 0). NOTE the fit arm **does** inherit the benchmark fix automatically — its `_surplus` calls `ts.package_value_v2` with a trade-wide `v_max` through the module namespace (verified at `backend/trade_gen_fit.py:640-649`). |

Arm A pins BOTH knobs at 0.0 (`MODEL_A_PROFILE`) — it reconstructs the
pre-wave engine, which had own-max math and no sweetener. The arm-A golden
did **not** need re-capturing: the kill values are proven byte-identical
no-ops (see §3), which is strictly better for D-075 than a moved baseline.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new client events. The
  measurement split rides `deck_impressions.features_json.gap_sweetener` —
  a server-side frozen feature key (the F1 spine), stamped on EVERY row
  (null when unsweetened) per the fit-arm uniform-key precedent, NOT an
  analytics event, so the taxonomy (`backend/analytics_taxonomy.py`) is
  untouched — confirmed against its rules: nothing here is a client-emitted
  event. Questions it answers: sweetened-card share, like/pass split on
  sweetened vs unsweetened, gap distribution before/after.
  Card payloads additionally carry `gap_sweetener` (only when present,
  same convention as the 3.4 `sweetener` key) for client inspection.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** (`features_json` is an existing
  Text column; a new key inside it is not schema.)
- New/changed feature flags: **none.** Knob-gated, not flag-gated.
- New `model_config` keys — all three follow the five-registration rule
  (`trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS` +
  `_PINNED_KNOBS` + disposition sentence in
  `docs/plans/three-model-bakeoff/scope-phase2.md` + `docs/config-reference.md` row):

  | Knob | Default | Deploy-free rollback |
  |---|---|---|
  | `package_bench_trade_wide` | 1.0 | set to 0 ⇒ pre-fix own-max math byte-identically |
  | `package_floor_cross` | 0.40 | inert while the knob above is ≤ 0 |
  | `sweetener_gap_threshold` | 1539.0 | set to 0 ⇒ pass skipped byte-identically |

- Changed default (**DONE — `6a61c05`**): `ghost_holdout_one_in` 10 → 0 in
  `trade_service._DEFAULT_CFG`, `database._MODEL_CONFIG_DEFAULTS` and the
  `suggestion_telemetry.ghost_one_in` inline fallback, each with a comment
  recording the operator ruling 2026-08-21 (batch-wide; prod row already 0 —
  the default change makes code agree with the ruling).

## 3. Evidence scope

- [x] **Structural guard:** WAIVED-equivalent — backend-only change; no
  mobile file touched, no testID added. (Mobile renders sweetened cards
  through the existing value-bar/id-list contract; see the checklist below.)
- [x] **Unit tests:**
  - `backend/tests/test_package_benchmark.py` (new, 8 tests) — the Nacua
    regression (serves under legacy math at the pinned literals, falls OUT
    of the ±15% band under the fix), kill-value byte-identity across four
    shapes, single-asset exemption, own-max path preservation, cap
    preservation, cross-floor isolation.
  - `backend/tests/test_gap_sweetener.py` (new, 12 tests) — helper unit
    (direction, smallest-sufficient, untouchables, unclosable→None, extra
    gates), consensus path on/off, v3 path on/off, v2 divergence path
    on/off. The "off" tests ARE the sabotage-verify: knob 0 ⇒ the exact
    gap cards reappear unsweetened with their full gap.
  - Updated with dated comments where a golden isolates a different claim:
    `test_stud_tax_modes.py` (own-max shape now pinned at the kill value +
    a new default-shape direction pin), `test_bakeoff_challenger.py` /
    `test_engine_quality_golden.py` / `test_asset_ideas.py` (kill-value
    pins), `test_bakeoff_arm_a_golden.py` (R4 victim from arm B's own
    deck), `test_engine_gates_config.py` (surplus sweep widened).
  - Re-captured: `backend/tests/fixtures/bakeoff/flag_off_golden.json`
    (flag-off parity golden — its contract is "flag off == non-bake-off
    path", which survives; the engine underneath moved deliberately).
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — the benchmark
  threading trace, callsite by callsite.
- [x] **Manual TestFlight checklist:** [testflight-checklist.md](testflight-checklist.md)
  — written 2026-08-21. Covers deck fill, the Nacua shape, sweetened-card
  value bars (totals include the equalizer, residual gap ≤ one late 1st),
  the untouchable / not-interested / pinned / acquire-position failure
  conditions, one real send, the readout SQL for the sweetened share and the
  per-arm gap distribution, the arm-C caveat, and the deploy-free rollback
  knobs. Operator runs it after the Monday merge.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added/renamed/removed. TradeCard payloads gain the optional `gap_sweetener` key following the documented optional-key convention of `sweetener` (Tier 3 3.4); no contract changed — clients that ignore it see the same shape |
| `living-memory/LLD.md` | n/a | No schema/route/invariant convention shifted; the knob follows the existing five-registration convention rather than changing it |
| `docs/architecture.md` | n/a | No module wiring change — `close_value_gap` lives in `trade_optimizer` next to `_try_sweeten` (its prior art) and `trade_service` lazy-imports it exactly as it already lazy-imports `_consensus_packages` |
| `living-memory/HLD.md` | n/a | Same — no new component |
| `docs/cross-client-invariants.md` | n/a | No shared constant/enum/color; 1539 is a backend knob, not a client constant |
| `docs/glossary.md` | n/a | "Sweetener" already exists as a term (Tier 3 3.4); this is a second kind of the same thing, discoverable from config-reference |
| `docs/config-reference.md` | **updated** | Rows for all three knobs + `package_floor_market`/`package_adj_gamma_market`/`package_discount_cap` amendments + `ghost_holdout_one_in` default 0 |
| ADR / `DECISIONS.md` entry | deferred to ship session | The merge is held; the D-entry (benchmark fix + arm-A pin-instead-of-recapture + sweetener line) belongs to the session that ships to `main`, alongside the CHANGELOG entry — noted in the final report so the operator can ratify |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` full suite on this branch (counts in
  `living-memory/TEST_LEDGER.md`); `tsc --noEmit` / `check-*.js` /
  `testid-lint` unaffected — zero mobile files touched, mobile CI is
  byte-identical to `origin/main`'s green.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-08-21a — full
  suite **3786 passed, 1 skipped** (baseline 3782 on `0e04d30`; +4 round-2
  regression tests, every delta accounted for), plus the W0-style fixture
  measurement of deck size and gap distribution at `origin/main` vs this
  branch, per league × path × arm.
- **TestFlight verification:** [testflight-checklist.md](testflight-checklist.md)
  written; run by the operator after the Monday merge.
- Express lane declared by the operator? **No — full gates.**

---

## 6. Round-2 adversarial review (2026-08-21, Opus re-delegation)

The operator re-delegated the sweetener to Opus for a hostile re-read of the
two inherited commits, with fix authority. Verdict: **the benchmark fix
(`72ecd51`) is clean; the sweetener (`0e04d30`) shipped two real defects,
both fixed in `49c1d76`.**

### What was verified and held

- **`v_max` really is trade-wide at every callsite.** All 14 constructions in
  `backend/` are `max(gvals + rvals)` or a per-board `max(give + recv)` — no
  caller ever passed a one-sided max, so the predecessor's one-line threading
  claim is correct. `server._evaluate_adjustments`'s calculator breakdown
  inherits the fix automatically (it derives its depth row by calling
  `package_value_v2` with the same trade-wide `v_max`).
- **The carve-outs are the right ones.** `len(values) > 1` keeps every 1-for-1
  fairness ratio untouched; `v_max > own_max` keeps the consolidating
  stud-plus-filler side on its original math. No multi-asset overpay shape is
  left un-fixed: a side holding the trade's best asset is *already* benchmarked
  against the trade's best asset, because they are the same number.
- **Kill-value byte-identity is genuinely tested**, not asserted:
  `test_kill_value_is_byte_identical_to_pre_fix_math` hand-derives the pre-fix
  expression from literals over four shapes rather than comparing the function
  to itself. It compares to 0.05 absolute, not exact equality — see the
  ratification list.
- **Interleave safety.** All three hook sites execute inside the arm's own
  `generate_trades` / `generate_pair_trades_v3` call, under that thread's
  `_cfg_override`. No post-draft code is touched, so deck positions and arm
  attribution are untouched — confirmed by reading `bakeoff_runner`, which only
  merges the returned lists.
- **`executemany` discipline.** `gap_sweetener` is built into the per-card
  `features` dict inside the impression loop, so it is present on **every**
  row, null when absent — and it rides inside the single `features_json` Text
  column, where the first-row-keys trap cannot reach it.
- **No oscillation.** `close_value_gap` rejects any candidate whose addition
  leaves `|gv − rv| > gap_threshold`, so an overshoot past the line in the
  other direction can never be selected; candidates are walked cheapest-first,
  so the first hit is the smallest sufficient equalizer.
- **Fairness bands are per-path and correct.** The consensus path passes its
  own `max(fairness_threshold, consensus_fairness_floor)`; v2 and v3 pass the
  already-lowered `min(threshold, fairness_floor_divergence)`. The helper's
  band check is a hard ratio test, which is *stricter* than v3's
  uncertainty-overlap allowance — it can only decline to sweeten, never smuggle
  a card in below the band.
- **The `_pair_surpluses` / `_composite_v2` extraction really is byte-identical**
  — sabotage-verified (`u_max` narrowed to the give side only) rather than
  taken on trust. Correction to `0e04d30`'s commit message, which credited
  "the arm-A/challenger/engine-quality goldens": those three run with
  `trade_engine.v3` ON, so they never enter `_generate_for_pair_v2` and all
  stayed green under the sabotage. The guards that actually caught it are
  `test_trade_optimizer.py::test_v3_top_card_matches_v2_on_1for1_fixture` and
  `test_trade_tier2.py::test_outlook_rebuilder_outranks_championship`. Full
  detail in TEST_LEDGER 2026-08-21a.
- **Five-registration rule** satisfied for all three knobs, and the
  knob-inventory guard is green with them in `_PINNED_KNOBS`.
- **Arm A's pin is real, and now measured.** On both fixture leagues and both
  engine paths, arm A produces byte-identical decks at `origin/main` and at
  this branch tip: 120 cards, 9 over-line, identical p90 and mean gaps. That is
  live evidence for the pin-instead-of-recapture choice, on top of the unit
  test — see TEST_LEDGER 2026-08-21a.

### Defect 1 — the sweetener bypassed the consensus path's pool pruning

`_generate_consensus_for_pair` does not gate pinned players and acquire
positions per combo the way v2 and v3 do: it **prunes its pools** —
`give_pool` down to the #174 pinned give players, `recv_pool` down to the
FB-47 pinned acquire targets or the needed positions. `close_value_gap` drew
its equalizer from the raw rosters, so:

- a pinned job ("trade away exactly G") emitted `[G, X1] → [R]` with `X1`
  never offered up by the user;
- a WR-only acquire job could hand back an off-need RB.

Both reproduced against `0e04d30` before the fix. Fixed with optional
`give_candidates` / `recv_candidates` parameters carrying the calling path's
eligible universe; `user_roster` / `opp_roster` still drive the 3.2
lineup-feasibility counts, so feasibility still sees the real team. v2 and v3
deliberately pass nothing — their pinned and acquire-position rules are
per-combo and **monotone under addition** (`pinned_set <= give_ids`,
`recv_ids & pinned_recv_set`, `any(pos in _acq)`), so adding an asset cannot
break them. Verified callsite by callsite rather than assumed.

Guards: `test_consensus_sweetener_never_adds_an_unpinned_give_player`,
`test_consensus_sweetener_respects_the_acquire_position_filter`,
`test_helper_candidate_pools_narrow_the_equalizer_universe`.

### Defect 2 — v3 shipped a stale `fit_premium` on sweetened cards

`fit_premium_1for1` can only price a 1×1 (it fires only when the #108
raw-board gate fails, which it can only do on a 1-for-1). The v3 gap pass
rewrote the card's asset lists in place and left the badge on, so a card that
had become a 1-for-2 still advertised "you paid 200 of raw-board value for a
need fill". The v2 divergence path already nulled its `fit_paid` for exactly
this reason; v3 now does the same.

Guard: `test_v3_gap_sweetener_clears_the_stale_fit_premium` (non-vacuous — the
knob-off half of the same fixture proves the organic winner really is a
fit-premium 1-for-1 carrying a 1600 gap).

### Two docstring corrections (no behaviour change)

- `close_value_gap` claimed "picks are not roster assets on this path".
  With `trade.picks_in_pool` on — the release posture — owned picks **are**
  injected into the rosters as PICK pseudo-assets, so a pick can be the
  equalizer. That is defensible (a pick is often the ideal equalizer) and is
  guarded by `pick_swap_ok` re-running inside every caller's `extra_ok_fn`,
  but the docstring said the opposite. The same inaccuracy is inherited from
  `_try_sweeten` and is left there for a separate pass.
- `test_bakeoff_serving`'s header still claimed the flag-off golden is
  evidence "not against an assertion about ourselves". After two re-captures
  on 2026-08-21 it is a self-capture, so that test is now a **drift
  detector**; what survives independently is
  `test_dark_mode_serves_the_flag_off_deck`, which compares the flag-ON deck
  to the same golden — two different code paths, one fixture. Stated plainly.

### Ratification list — operator calls, not agent judgement

1. **Arm A's golden was pinned, not re-captured** (inherited from `72ecd51`).
   Both new knobs sit in `MODEL_A_PROFILE` at 0.0 and the golden stands
   un-recaptured. This is *stronger* than a moved baseline for D-075, and the
   fixture measurement now confirms arm A is byte-identical across the change
   — but it is still a deviation from "re-capture when the engine moves" and
   the operator should ratify it explicitly.
2. **The flag-off serving golden was re-captured twice** (2 cards → 1, then
   the uniform features key). Its historical claim — parity with the
   pre-bake-off SHA — **died with the re-capture and cannot be re-proved**
   without a worktree at that SHA. Operator call: accept the drift-detector
   posture, or commission a re-capture at the reference SHA.
3. **Kill-value identity is proved to 0.05 absolute, not bit-for-bit.** The
   commit messages and comments say "byte-identical". The code path *is* the
   same expression, and the fixture measurement shows arm A's decks matching
   exactly, so the claim is true in substance — but the word in the test is
   `pytest.approx`, and that gap between wording and assertion is worth a
   conscious ratification rather than silent acceptance.
4. **A pricing discontinuity at the benchmark boundary.** The floor switches
   0.70 → 0.40 the instant `v_max` exceeds `own_max` by any amount, so two
   nearly identical trades can price a couple of percent apart across that
   line (worst constructed case ≈ 2.3 % on a stud-plus-three-scraps side; the
   headliner piece itself is continuous). Smoothing it would move the tuned
   Nacua number (0.709) the operator approved, so it is deliberately left
   alone and flagged instead.
5. **Arm C gets worse on this branch, and it is now measured.** Arm C
   (`trade_gen_v2`) inherits the benchmark fix in its DISPLAYED values but not
   the sweetener, so its share of cards above one late 1st RISES: 0 → 3 of 22
   on the 12-team fixture, 1 → 2 of 19 on the 16-team SF fixture. That is the
   cost of the "arm C is a v1 follow-up" decision, quantified. The follow-up
   is now a priority item, not a nicety.
6. **The measurement is fixture-based, with synthetic boards.** Levels are
   directional; the main-vs-branch deltas are the result. ~~The prod replay half
   (real league boards) needs prod read access and is an operator item, as it
   was for the fit W0 run.~~ **DONE 2026-08-21** — the prod replay ran read-only
   against league `1312140920132497408`; numbers and method in
   `living-memory/TEST_LEDGER.md` addendum 2026-08-21b, harness
   [replay_prod_boards.py](replay_prod_boards.py). It CONFIRMS the direction and
   softens the cost (deck −1.6% served roster, not the fixture's −3.9%;
   over-the-line share 8.1% → 3.8% on arm B from a real 8.1% baseline, not the
   fixture's 0–5%; sweetener fires on 9.2% of arm-B cards, ~2x the fixture rate,
   as owed-item (d) predicted). Two things it adds: arm C is worse on real
   boards than on the fixture (29.4% → 37.2%), and **the benchmark fix alone
   RAISES the over-the-line share** (6.7 → 11.3 on v3) — only the sweetener makes
   the pair a net win, so the two are not independently shippable.

### Operator ratifications — 2026-08-22 (recorded by the coordinating session)

| Item | Ruling |
|---|---|
| 1. Arm-A golden pinned, not re-captured | **RATIFIED "for now"** (operator: "Let's go with Y for now"). The pin stands; the deferred re-capture becomes MANDATORY if the legacy pricing path (`package_bench_trade_wide <= 0`) is ever removed — that removal must carry the re-capture in the same change. |
| 2. Flag-off serving golden = drift-detector posture (historical parity claim retired) | **RATIFIED** ("Aligned") |
| 3. Kill-value identity proven to 0.05 abs (not bit-for-bit) | Ratified as part of item 1 — arm-A deck-level byte-identity is the operative proof |
| 4. Pricing discontinuity at the benchmark boundary (≤2.3%) | **ACCEPTED as-is** ("Leave it") |
| 5. Arm C over-line regression | Ship rule recorded: the arm-C sweetener extension (separate session, in flight) rides the ship if green by merge time; otherwise `bakeoff_include_gen_v2 = 0` at ship until it lands |
| 6. Fixture-only measurement | Prod-replay measurement running (operator approved read access) |
