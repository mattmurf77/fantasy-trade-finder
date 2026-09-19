# Feature Scope — three-model bake-off, Phase 3 (the runner)

**Date:** 2026-08-18
**Entry point:** [docs/plans/three-model-bakeoff/PLAN.md](PLAN.md) §7 Phase 3 (direct ask)
**Builder:** backend build agent, branch `feat/bakeoff-runner`
**Operator sign-off on waivers:** pending — §3's Maestro/simulator waiver is
backend-only and routine; the two open items in §6 need an operator decision
**before Phase 5**, not before merge.

---

## 0. What Phase 3 builds

One organic trade job fans out into three generations, run **sequentially on the
existing daemon thread** (PLAN.md §3.1 — the config seam is a `threading.local()`,
so sibling threads would each need their own context and the discipline is easy
to break):

| Arm | Name | Invocation |
|---|---|---|
| A | `baseline` | the live engine inside `bakeoff_profiles.model_a()` — the pinned `MODEL_A_PROFILE` + the arm-A R4 bypass, applied together |
| B | `current` | the live engine, live defaults, no override |
| C | `gen_v2` | `backend/trade_gen_v2.generate_league_suggestions` called directly |

The three ranked lists merge by **team-draft interleaving** (PLAN.md §4), every
served card is attributed to the arm that produced it, and one `bakeoff_runs` row
per job records the arm order, per-arm card counts, per-arm generation ms and
per-arm empty/forfeit counts.

Behind flag `trade.bakeoff`, **default OFF**. Serving nothing new until Phase 5.

New module map:

| File | Role |
|---|---|
| `backend/bakeoff_runner.py` | the whole runner: flag + knobs, arm order, team draft, fan-out, attribution, the §3.4 hygiene predicates |
| `backend/bakeoff_profiles.py` | the arm-A seam (`model_a()` = `MODEL_A_PROFILE` + the R4 bypass) — **owned by Phase 2**, consumed here |
| `backend/server.py` | `_run_trade_job` fan-out + re-ranker bypass + attribution stamping; swipe Elo freeze |
| `backend/database.py` | `bakeoff_runs` table; `deck_impressions.model_arm` / `.arm_rank` |

### `trade_gen.v2` stays FALSE — verified

`trade_gen.v2` gates whether `TradeService._generate_trades_impl` **routes** the
whole deck through the v2 pipeline instead of the v1/v3 engine
(`backend/trade_service.py:2960` — `if FLAGS.trade_gen_v2: … return cards`). It is
a serving-path switch, not a module guard. The bake-off does not route: it calls
`generate_league_suggestions` directly as a third generator
(`bakeoff_runner.gen_v2_cards`) and attributes its output separately. So the flag
stays false for the whole bake-off, and arms A/B keep running the engine they are
supposed to be. Asserted by
`test_bakeoff_serving.py::test_arm_c_runs_while_trade_gen_v2_stays_off`, which
reads the live flag from inside arm C's own invocation.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new client events and no new
  `user_events` rows. The measurement rides the telemetry spine that shipped
  2026-08-17, extended rather than reinvented:

  | Question | Field |
  |---|---|
  | which model produced this card | `deck_impressions.model_arm` (+ the arm encoded in `policy_version`) |
  | its rank within its own arm | `deck_impressions.arm_rank` |
  | where it sat in the deck | `deck_impressions.card_index` (existing) |
  | what the user did | `deck_outcomes.action` (existing) |
  | why they passed | `trade_pass_reasons.*` (existing) |
  | did two arms agree | `deck_impressions.features_json.also_proposed_by` + `bakeoff_runs.agreement_json` |
  | how often did an arm produce nothing | `bakeoff_runs.arms_json[arm].empty` / `.forfeits` |
  | what did the fan-out cost | `bakeoff_runs.arms_json[arm].gen_ms` / `.total_ms` |
  | **what threshold was this card generated under** | `deck_impressions.fairness_threshold` (per card, per arm) + `bakeoff_runs.arms_json[arm].fairness_threshold` |
  | **what configuration produced it** | `bakeoff_runs.config_json` (`base` + per-arm delta) |

  The existing `trades_generated` event is unchanged — it still fires once per
  completed job, so per-deck rates keep an honest denominator.

## 2. Schema & flag scope

- **New columns** — `deck_impressions.model_arm` (VARCHAR), `deck_impressions.arm_rank`
  (INTEGER), `deck_impressions.fairness_threshold` (FLOAT). All additive/nullable
  via the established `_migrate_db` pattern, no backfill (no arm produced
  pre-bake-off rows). → `docs/data-dictionary.md`.
- **New table** — `bakeoff_runs` (one row per bake-off job), incl. `config_json`.
  → `docs/data-dictionary.md`.
- **New flag** — `trade.bakeoff`, default **false**, in `config/features.json`,
  `backend/feature_flags.py` `FLAG_KEYS`, `backend/tests/fixtures/flags/*.json`
  and `docs/config-reference.md`.
  **Graduation criterion:** flip ON with `bakeoff_serve_interleaved = 0` (Phase 4
  dark validation) once Phase 2's `MODEL_A_PROFILE` golden is green; flip the knob
  to 1 (Phase 5) only after Phase 4 shows p95 job duration inside the 60 s job
  hard timeout and the empty-arm rate is understood (§6).
- **New `model_config` keys** — `bakeoff_serve_interleaved` (0.0 = dark, the
  default; 1.0 = interleaved serving), `bakeoff_deck_limit` (0.0 = uncapped).
  → `docs/config-reference.md`.
  **Deploy-free rollback lever:** the flag itself, and inside it the serving knob
  — an interleaved deck reverts to today's deck by setting
  `bakeoff_serve_interleaved` back to 0, no deploy.
- **No route added, renamed or contract-changed.**

## 3. Evidence scope

- [x] **Unit tests** — `backend/tests/test_bakeoff_runner.py` (35 tests): flag-off
  predicates, seeded arm order + its uniformity over 600 decks, team-draft
  alternation and own-rank credit, first-picker duplicate credit + agreement,
  short/empty-arm forfeits, position balance across 400 decks, sequential fan-out
  in generation order, arm A's profile + R4 bypass, dark-mode serving, the
  `bakeoff_runs` row shape.
- [x] **Integration tests** — `backend/tests/test_bakeoff_serving.py` (14 tests)
  drive the real `server._run_trade_job` end to end.
- [x] **Captured golden (not an assertion)** —
  `backend/tests/fixtures/bakeoff/flag_off_golden.json` was produced by running
  `backend/tests/support/bakeoff_harness.py` inside a **separate worktree at
  pre-bake-off `origin/main` (9a20ca8)**, then committed. With the flag off the
  branch reproduces it byte for byte: identical served card payloads and identical
  `deck_impressions` rows. The only admitted difference is the two additive
  columns (`model_arm`, `arm_rank`, `fairness_threshold`), asserted NULL on every
  row. The harness deliberately imports nothing
  from `bakeoff_runner`, which is what let it run on the pre-change SHA.
- [x] **Code-walk proof — §3.4 Channel 2 (see §4 below)** with a live test that
  turns every reordering layer ON, replaces each with a spy that REVERSES the
  deck, and asserts the served arm sequence is still the interleaver's
  (`test_post_generation_rerankers_cannot_touch_the_merged_deck`). Its mirror
  (`test_rerankers_do_run_when_the_bakeoff_is_off`) proves the spies would have
  fired, so the bypass is a bake-off property and not a broken harness.
- [x] **Structural guard — §3.4 Channel 1.**
  `test_every_swipe_k_multiplier_runs_through_the_elo_freeze` scans
  `backend/server.py` for every `fit_congruence_mult` K site and fails if one is
  missing `_bakeoff.elo_freeze_mult`. A new swipe path that forgot the freeze
  would let arms teach the shared board with no visible symptom.
- [x] **WAIVED — Maestro / simulator / `screens/` captures:** retired entirely by
  D-056, and this change is backend-only with no user-visible surface while the
  flag is off. No mobile `check-*.js` guard and no `testID` changes for the same
  reason.
- [x] **WAIVED — manual TestFlight checklist:** nothing user-visible ships in
  Phase 3. A checklist belongs to Phase 5 (lighting interleaved serving), where
  runtime proof actually matters.
- `testID`s added/renamed: none.

## 4. §3.4 measurement hygiene — the decisions, and why

### Channel 1 — arms teaching the shared board

`elo_freeze_mult()` returns `0.0` while `trade.bakeoff` is on, and is applied at
the fit-congruence multiplier that **both** halves of a trade swipe already share
— the in-memory `RankingService.record_trade_signal(fit_mult=…)` and the
persisted `swipe_decisions.k_factor`. One seam, so the live board and the DB
replay can never disagree. Three call sites in `backend/server.py`, guarded
structurally (§3).

Deliberately NOT frozen, per PLAN.md §3.4: ranking votes (`elo_k`, the Trios UI),
decline-reason capture, Phase 0's unpinning.

### Channel 2 — post-generation reordering

**Decision: BYPASS for bake-off decks, not per-arm pre-interleave.**

Five-plus layers currently reorder after generation. On an interleaved deck each
one silently destroys the team-draft position balance, converting the experiment
into a measurement of deck position with no visible symptom. The two options
PLAN.md allows are bypass, or apply per-arm before interleaving. Bypass was
chosen because:

1. **`arm_rank` must mean the model's own ranking.** Applying Thompson/fatigue/
   taste per-arm would reorder each arm's list before the draft, so `arm_rank`
   would record the presentation stack's opinion, not the generator's — and
   `arm_rank` is the field that separates "this model ranks badly" from "this
   card sat low in the deck".
2. **Two of the layers LEARN.** `deck.fatigue` and `deck.thompson_v2` update
   state from what they serve. Left live during the bake-off they start steering
   which shapes get served — a contamination channel independent of Elo, and one
   that would differ per arm.
3. **Bypass is verifiable in one predicate.** `bypass_rerankers()` is a single
   function; the test above proves the deck came out the other end untouched.
   Per-arm application would need a correctness proof per layer.

**Bypassed** when `trade.bakeoff` is on AND `bakeoff_serve_interleaved = 1`, for
that deck only:

| Layer | Where |
|---|---|
| F2 Thompson draw + A6 diversity penalty + `_cap_per_target` | the whole `_order_deck` call |
| F3 fatigue **multipliers** | `fatigue_mults = None` |
| F5 taste vectors | block skipped |
| F6 value model (base-key swap) | block skipped |
| F7 exploration wildcard **and its over-generation** | `explore_active` forced False |
| F9 first-session shaping | shaping skipped, the `first_deck` job marker kept |
| likes-you injector's composite re-sort | `bakeoff_runner.restore_order` puts the deck back |

**Deliberately still live:**

- **F3 decline suppression** — it only REMOVES cards. Removal shifts every arm
  equally and preserves relative order, and dropping it would re-serve trades the
  user durably declined (real user harm, no measurement benefit).
- **The likes-you injection itself** — a counterparty already liked the mirror of
  that trade; it is real user value. The injector returns the deck **re-sorted by
  `composite_score`**, so `restore_order` pins the injected cards to the top (a
  constant shift, identical for every arm) and returns every arm card to its
  interleaved index. Injected cards carry `model_arm = NULL`, which is the honest
  answer: no arm produced them.
- **Ghost holdout** — orthogonal, per-card, and already exempt from the
  targeted-deck cases the bake-off also skips.

**Dark mode (Phase 4) bypasses nothing.** It serves arm B through the untouched
presentation stack, which is what makes it zero-risk;
`test_dark_mode_serves_the_flag_off_deck` asserts the served payload equals the
flag-off golden.

### Channel 3 — the threshold a card was generated under

*(Added 2026-08-18 after `docs/reviews/2026-08-18-trade-logic-archaeology.md`.)*

`fairness_threshold` arrives per-request from the mobile client (0.75 fairness
toggle on / 0.50 off) and was persisted **nowhere** — not a `deck_impressions`
column, not one of the 28 `features_json` keys. All three arms inherit whatever
the client sent for that job, so a per-arm comparison spanning sessions with
different client settings would compare arms **and** thresholds at once, with
nothing in the data to separate them. That is the same silently-invalid class of
result as Channel 2, and it needed the same treatment: record it, do not infer
it. The field has already proven un-inferable — the mobile default flipped
0.75 → 0.50 on 2026-08-17 (`00b2a2c`), yet prod shows `min_fairness ≈ 0.50` back
in July, so the documented value and the effective value have diverged once
already.

**Decision: a `deck_impressions` column, not a `features_json` key.** It is a
scalar the analysis groups and filters by on every per-arm read; burying it in a
JSON blob would make the one query that matters (below) a JSON extract on every
dialect, and `features_json` is for frozen card attributes rather than the gate
the card had to clear.

**Per CARD, not per job,** because the effective bar is card-dependent —
`bakeoff_runner.effective_fairness_threshold()`:

| Card | Effective bar |
|---|---|
| `basis="consensus"` | the requested value in full (consensus IS the board there) |
| `basis="divergence"` | `min(requested, fairness_floor_divergence)` — both members have real boards, so the consensus check is an extreme-case veto (`trade_service._DEFAULT_CFG`, 2026-07-17) |
| `relaxed=True` (#189 stage 1) | the above, after `min(requested, relaxed_fairness_threshold)`. Reachable on an **organic** deck through the user's acquire / trade-away position preferences, so not hypothetical |
| any arm `gen_v2` card | **NULL** — `generate_league_suggestions` takes no `fairness_threshold`; its bar is the `gen2_*` dual-board ε stack. NULL is the fact a reader needs, not missing data |

**Per ARM as well** (`bakeoff_runs.arms_json[arm].fairness_threshold`): arm A runs
under `MODEL_A_PROFILE`, so what each arm actually used is recorded rather than
assumed to match.

**Config snapshot.** `model_config` has no `updated_at`, so a knob's change date
is unknowable after the fact — and `fairness_floor_divergence` /
`relaxed_fairness_threshold` are exactly the knobs that decide what a recorded
threshold *means*. `bakeoff_runs.config_json` therefore stores
`{"base": <arm current's effective config>, "arm_delta": {arm: {…}}}`, snapshotted
**inside each arm's own context** (outside it arm A's overlay is gone and it
would be recorded as having run on live defaults — the exact confusion this
exists to prevent). Whole values, not a fingerprint: a hash says the config
changed without saying to what. ~5 KB + a few delta keys per run. This is
deliberately **not** a config-versioning system — one snapshot per run, no
history, no dedup.

**The report surface** is the query in `docs/data-dictionary.md` §`bakeoff_runs`
("Was this comparison threshold-clean?") — one `GROUP BY model_arm` counting
distinct thresholds. Phase 3 builds no route or dashboard (there is none to
extend yet); the query is pinned by a test that runs it
(`test_threshold_clean_query_answers_itself_from_the_table`), so it cannot rot
into documentation-only.

### Known distortion, accepted and recorded

The G6 presentment **tripwire** (`_log_presentment_outcome`) reads per-job kill
counters that `_generate_trades_impl` overwrites per call, so after a fan-out
they reflect the LAST arm to run — arm A, whose profile zeroes every rule. It is a
log line only; no behaviour reads it. Noted in code rather than grown into
per-arm counters for a WARNING.

## 5. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed or contract-changed — Phase 3 is generation-path only |
| `living-memory/LLD.md` | updated | new module + attribution convention |
| `docs/architecture.md` | updated | `bakeoff_runner` in the backend module map + the fan-out in the trade-job flow |
| `living-memory/HLD.md` | n/a | no architectural shift: no new client, no new service, no new flow — one flag-gated branch inside an existing worker |
| `docs/cross-client-invariants.md` | n/a | arm names are server-side only; no client reads them |
| `docs/glossary.md` | updated | arm, team-draft interleaving, forfeit, agreement, dark validation |
| `docs/data-dictionary.md` | updated | `bakeoff_runs`, `deck_impressions.model_arm` / `.arm_rank` |
| `docs/config-reference.md` | updated | `trade.bakeoff`, `bakeoff_serve_interleaved`, `bakeoff_deck_limit` |
| ADR / `DECISIONS.md` | updated | the Channel-2 bypass choice + the arm-C-vs-`trade_gen.v2` distinction |

## 6. Open items for the operator

1. **RESOLVED — arm A rides Phase 2's real seam.** Phase 3 was built against a
   temporary local stub of `backend/bakeoff_profiles.py` while
   `feat/bakeoff-arm-a` was still in flight, then rebased onto `origin/main`
   `9d24da3`, which carries Phase 2 (`3760f12`). The stub was dropped and the
   runner now calls Phase 2's **`model_a()`** — the only supported entry point,
   because it applies the pinned `MODEL_A_PROFILE` and the R4 bypass together and
   applying one without the other produces a silently wrong arm A. Arm A is
   golden-tested against reference SHA `92c31d5` by Phase 2's tests, and the R4
   bypass is really enforced via `trade_service.r4_bypassed()`. Nothing owed here.
2. **Job budget before Phase 5.** Measured fan-out cost is **2.35×** a single
   generation on a 12-team / 168-asset fixture (single 3.13 s → three arms 7.36 s;
   arm A 4.19 s, arm B 2.73 s, arm C 0.42 s — arm A is the slowest because its
   profile zeroes every gate, so more candidates survive). The per-opponent enumeration
   deadline is 1 s, so an 11-opponent league's worst case is ~11 s per arm and
   ~33–45 s for the fan-out, against `server._JOB_HARD_TIMEOUT = 60` seconds —
   inside the limit, but with thin headroom and no margin for a slow Postgres.
   Phase 4 should watch p95 job duration directly; `_JOB_HARD_TIMEOUT` may need
   raising before Phase 5.
3. **Deck size.** `bakeoff_deck_limit` defaults to 0 (uncapped), so an interleaved
   deck is roughly 3× today's. The fixture produced a 140-card deck. Set the knob
   before lighting Phase 5 unless a very long deck is wanted.

## 7. Ship gate declaration

- **CI green:** `backend-tests` — full suite **3363 passed, 1 skipped, 0 failed**, re-run after rebasing onto `origin/main` `9d24da3` (bake-off Phase 2 + tier-bounded pins) and after the fairness-threshold capture.
  `mobile-typecheck` and `maestro-testid-lint` untouched (no mobile files changed).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** n/a — nothing user-visible ships in Phase 3.
- **Express lane declared by the operator?** No — full gates.
