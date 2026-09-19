# W4-F8 build report — Offline Eval Harness (replay/IPS + calibration)

**PRD:** docs/plans/tiktok-discovery/prds/F8-offline-eval.md
**Flag:** none (operator tooling, per PRD — `config/features.json` / `FLAG_KEYS` untouched)
**Branch:** teardown-remediation (no git commands run — lead commits)
**File-ownership compliance:** zero edits to backend/server.py, trade_service.py, database.py, mobile/**, config/. All new code lives in `backend/eval/` + two new test files + appended doc sections.

## Files created

| File | What |
|---|---|
| `backend/eval/__init__.py` | Package docstring / module map |
| `backend/eval/data.py` | Loads deck_impressions ⨝ deck_outcomes into `LoggedDeck`/`LoggedCard`; outcome reduction (viewed/liked/passed/proposed/not_interested/undone, max dwell); `card_dict()` (frozen features merged with logged fields — the scorer input); `split_decks()` (time-ordered split; no shuffled-CV API exists on purpose); engine resolution: explicit engine > `--db` URL > `backend.database.engine` read at call time (test-patch idiom preserved) |
| `backend/eval/scorers.py` | Registered-scorer registry + the Scorer stub interface for F6 (`score(card)`, optional `fit(rows)`, optional `predict_proba(card)`). Built-ins: `production` (final_score ordering reconstructed from logs), `logged` (exact served order — the self-check identity), `base_score` (pre-presentation composite — first real candidate), `random` (seeded canary, must grade worse) |
| `backend/eval/replay.py` | The IPS/SNIPS evaluator, cluster bootstrap, verdicts, self-check, markdown report, CLI (`python3 -m backend.eval.replay`) |
| `backend/eval/calibration.py` | Reliability tables by fixed-width predicted-probability decile + ECE + markdown render; `calibration_pairs()` applies the same inclusion rules as replay (F6 consumer) |
| `backend/eval/persistence.py` | Append-only JSON-lines run records (`data/eval_runs/runs.jsonl`), `run_record()`/`append_run()`/`load_runs()`, `EVAL_RUNS_DIR` override, schema_version=1 |
| `backend/eval/nightly.py` | `run_all(window_days=30)` — grades every registered scorer vs `production` on the trailing window; idempotent per (UTC day, scorer, window); per-scorer failures recorded as `status:"error"` records, never raised; `python3 -m backend.eval.nightly` runnable today (cron hook = handoff below) |
| `backend/eval/synth.py` | Synthetic F1-shaped log generator (standalone SQLite; refuses existing files without `--force`) — demo + CLI end-to-end check |
| `backend/tests/test_eval_replay.py` | 16 tests (estimator, exclusions, ESS, time split, loader, CLI e2e, nightly idempotency) |
| `backend/tests/test_eval_calibration.py` | 6 tests (hand-computed table, ECE, bounds, inclusion) |
| `docs/config-reference.md` | New appended section "Offline eval harness (F8)" — `EVAL_ESS_MIN`, `EVAL_BOOTSTRAP`, `EVAL_RUNS_DIR` + fixed estimator constants |
| `docs/runbook.md` | New appended section "Offline eval harness — replay/IPS on the F1 impression spine (F8)" — usage, self-check discipline, UNRELIABLE semantics, nightly handoff status, the graduation gate |

## Estimator (modeling choices, stated honestly)

Estimand: expected like-rate / propose-rate **among viewed cards** had decks been ordered by the candidate scorer. Per included impression:

```
w_i = [ e(rank_candidate(i)) / e(rank_logged(i)) ]      exposure shift
      × clip( p̄_deck / p_i , 0.5 , 2.0 )                propensity tilt
V_IPS = mean(w·r)   V_SNIPS = Σw·r / Σw   ESS = (Σw)²/Σw²
```

- `e(k)` = P(viewed | served at position k), estimated from the loaded log (Laplace +1/+2, floor 0.02 — smoothing/floor printed in every report).
- The propensity tilt uses F1's logged `propensity` (Thompson multiplier, or F7's exploration propensity, 1.0 deterministic). The Thompson multiplier is a sort-key multiplier, **not** a true probability — the tilt is a documented first-order correction of the stochastic ordering (lucky-draw cards down-weighted), clipped to [0.5, 2.0] with the **clip count reported on every run** (no silent caps, per PRD).
- CIs: percentile 95% from cluster bootstrap over **deck jobs** (impressions within a deck are correlated). Default 1000 resamples.
- Self-check (`--self-check`): replaying the logged order makes the exposure ratio exactly 1 per card; under deterministic serving (p=1) SNIPS equals the observed rate identically; under Thompson noise the check asserts observed ∈ 95% CI, per metric. Exit 1 on failure.
- Candidate ranks are computed over ALL cards of a deck (excluded cards still occupy counterfactual slots); unparseable-feature cards sink to the bottom; ties broken by logged position so replaying `logged` reproduces the served order exactly.
- This is an approximate slate OPE — full slate propensities are unrecoverable from a single logged multiplier. The approximation and its assumptions are in the `replay.py` module docstring; the self-check + random-canary discipline is what keeps it honest operationally.

## Exclusion rules (counted per reason, printed every run, accounting asserted in tests)

Precedence order: `null_propensity` (NULL/≤0/non-finite — defensive, column is NOT NULL) → `never_viewed` (no `viewed` outcome; served ≠ seen — F2 cascade rule, unseen is not a negative) → `undo_reversed` (any `undo` outcome — disposition retracted) → `bad_features` (features_json missing/unparseable) → `scorer_error` (scorer raised anywhere in a deck ⇒ whole deck excluded; a partially scored deck can't be ranked consistently). Report prints `total = included + Σ excluded` and WARNs on mismatch.

## ESS threshold + rationale

Default **100** (env `EVAL_ESS_MIN`, CLI `--ess-min`). At ESS≈100 a 95% CI on a 10–20% base rate spans roughly ±6–8pp — wider than any plausible ranking effect at FTF volume, so verdicts below it are labeled `UNRELIABLE` (the numbers still print; the label refuses to bless them). ESS is Kish `(Σw)²/Σw²`, so heavy weight concentration (poor overlap between candidate and logged ordering) degrades it exactly when the estimate deserves distrust.

## Persistence choice

**JSON-lines under `data/eval_runs/runs.jsonl`** (env `EVAL_RUNS_DIR`), not a DB table. Justification: (1) F8 cannot edit backend/database.py this wave (F7 owns it), and a parallel `MetaData()`/create in backend/eval would fork the schema-migration conventions; (2) the writer is a single operator CLI/cron — no concurrency to referee; (3) records are greppable/diffable and zero-migration; (4) `/data/` is already gitignored (.gitignore line 8) so nothing ships. Every record carries `schema_version: 1` so a later wave can lift the file into an `eval_runs` table verbatim if SQL joins are ever needed. Torn trailing lines are skipped on read, never crash.

## Verification

- `python3 -m pytest backend/tests -q` → **1246 passed, 1 skipped** (baseline before F8 was 1224 passed, 1 skipped; +22 F8 tests, no transient F7 interference observed).
- CLI end-to-end against a synthetic SQLite db:

```
$ python3 -m backend.eval.synth --db $SCRATCH/eval_demo.db --decks 60 --seed 7
Wrote 480 impressions / 530 outcomes across 60 decks to .../eval_demo.db

$ python3 -m backend.eval.replay --db $SCRATCH/eval_demo.db --self-check --ess-min 100 --bootstrap 500
| scorer | metric | N | ESS | observed | IPS | SNIPS | 95% CI (SNIPS) | vs production | verdict |
|---|---|---|---|---|---|---|---|---|---|
| logged | like | 260 | 238.8 | 20.38% | 22.63% | 20.86% | [15.36%, 26.58%] | +0.00pp | FLAT |
| logged | propose | 260 | 238.8 | 3.85% | 4.27% | 3.93% | [1.62%, 6.51%] | +0.00pp | FLAT |
Exclusion accounting (impressions in eval window, per scorer):
- logged: total=480 included=260 excluded[never_viewed=220] tilt_clipped=4 (bounds [0.5, 2.0])
SELF-CHECK PASS

$ python3 -m backend.eval.replay --db $SCRATCH/eval_demo.db --scorer base_score --scorer random --ess-min 100 --bootstrap 500 --seed 3
| production | like | 260 | 240.7 | 20.38% | 19.98% | 20.04% | [15.30%, 24.99%] | +0.00pp | FLAT |
| base_score | like | 260 | 238.8 | 20.38% | 22.63% | 20.86% | [15.36%, 26.77%] | +0.83pp | FLAT |
| random    | like | 260 | 168.4 | 20.38% | 17.96% | 17.17% | [11.85%, 23.12%] | -2.86pp | FLAT |
Run records appended to .../eval_runs/runs.jsonl
```

Random grades worse (−2.86pp SNIPS, lower ESS from weight dispersion) as required; at this synthetic volume the CI still overlaps (verdict FLAT, honestly). The unit test asserts the strict ordering on a larger deterministic fixture.

## PRD acceptance-criteria status

- Self-consistency check: BUILT (`--self-check`, exact under p=1, within-CI under noise; tested both ways).
- Random grades measurably worse: BUILT + tested.
- ESS/CI on every run, UNRELIABLE labeling: BUILT + tested.
- Interleaving mode: **NOT BUILT this wave by design** — requires server.py/_run_trade_job edits (F7-owned). Full design handed off below.
- Nightly job idempotent, failures logged: BUILT (`nightly.run_all`, idempotent per day/scorer/window, error records); the daily-tick call site is the handoff snippet below; runbook section written.

## HANDOFF (a) — nightly cron hook (server.py, DO NOT let me apply it)

Paste into `/api/cron/daily-tick` (backend/server.py, directly after the F10 replenishment block that ends `replenish_stats = {"error": str(e)}`, before `log.info("daily-tick: %s", counters)`):

```python
    # ── F8 — offline eval nightly (operator tooling, unflagged) ──
    # Idempotent per (UTC day, scorer, window) via data/eval_runs/runs.jsonl,
    # so daily-tick retries are free. Never fails the tick.
    eval_summary: str | None = None
    try:
        from .eval.nightly import run_all as _eval_run_all
        _eval_stats = _eval_run_all(window_days=30)
        eval_summary = _eval_stats.get("summary")
        counters["eval_scorers_graded"] = _eval_stats.get("ran", 0)
        if _eval_stats.get("errors"):
            log.warning("daily-tick eval: %s scorer(s) errored (recorded in runs.jsonl)",
                        _eval_stats["errors"])
    except Exception as e:
        log.warning("daily-tick: offline-eval pass failed (non-fatal): %s", e)
    if eval_summary:
        log.info("daily-tick eval: %s", eval_summary)
```

Notes for the lead: local import keeps backend.eval out of server's import graph; the additive `counters` key changes the daily-tick JSON response only when the pass runs (mirrors the F10 pattern of additive keys); `run_all` already swallows per-scorer errors into records. No flag needed per PRD (operator tooling), but if a kill lever is wanted, wrap the block in a `model_config` check rather than a feature flag to avoid FLAG_KEYS churn.

## HANDOFF (b) — team-draft interleaving design (against backend/experiments.py; build in a later wave)

Goal: the small-traffic online gate — blend rankers A (production) and B (candidate) into ONE deck per user, credit dispositions to the source ranker, sign-test across users. Needs server.py edits (F7-owned this wave) — design only.

1. **Experiment spec** (existing engine, no engine changes): layer `engine`, unit `account`, key `deck.interleave_<candidate>` (e.g. `deck.interleave_base_score`), variants `control` / `interleaved` (start 8000/2000 bp). Launch/monitor via the existing CRON-gated admin lifecycle. Gated on `experiments.engine` flag as usual. Primary metric `like_rate` is already in `METRIC_CATALOG`; PFO guardrails auto-attach (FR-45).
2. **Call site**: in `server._run_trade_job`, AFTER `_order_deck` + likes-you injection, BEFORE `_log_deck_signal_impressions`:
   ```python
   variant = experiments.variant_for(user_id, "deck.interleave_base_score")
   if variant == "interleaved":
       cards, il_meta = _interleave_team_draft(cards, candidate_scorer, job_id)
   ```
   `_interleave_team_draft`: ranking A = current `cards` order (production, post-presentation); ranking B = same card list sorted by `backend.eval.scorers.get_scorer(candidate).score(card_dict)` over the SAME frozen feature dict `_log_deck_signal_impressions` builds (factor the feature assembly into a helper so serve-time and eval-time features cannot skew). Likes-you pinned cards stay at the top and are **excluded from crediting** (they're not either ranker's work). Team-draft proper: seed an RNG with `job_id`; each round flip which team drafts first; each team picks its highest-ranked not-yet-picked card; record `team[card] ∈ {"A","B"}` and the coin sequence.
3. **Logging (pure F1, no schema change)**: extend the card's features_json with `"interleave": {"exp_key": ..., "variant": "interleaved", "team": "A"|"B", "coin_seed": job_id}` at impression time. Position + propensity already logged by F1. `stamp_for_event` already stamps user_events for scoped analytics events.
4. **Crediting (offline read, new `backend/eval/interleave.py` in the build wave)**: load impressions whose features_json carries `interleave`; per (user, window): credits_A = Σ like/propose outcomes on viewed team-A cards (undo-reversed excluded — same rules as replay), likewise B; user preference = sign(credits_B − credits_A), ties dropped. Decision: two-sided binomial sign test across users (p<0.05), plus report mean per-deck credit share. This is Chapelle-style team-draft interleaving — ~10× less traffic than a parallel-cohort A/B for the same sensitivity, which is the point at FTF volume.
5. **Guardrail interactions**: interleaving runs after gates/diversity caps, so every blended card is gate-passing; F7's wildcard slot (fixed positions 4–6) must be re-pinned after the draft (same rule F4 re-rank obeys); F3 fatigue applies upstream at generation, unaffected.
6. **Graduation process (recorded in runbook)**: replay win with adequate ESS → interleaving win → flag/config graduates. Nightly replay keeps running as the regression alarm afterward.

## Caveats

- `base_score` vs `production` on real logs will read near-FLAT until presentation multipliers meaningfully reorder decks — expected, not a bug.
- Propose-rate ESS will lag like-rate ESS (rarer event); expect UNRELIABLE propose verdicts for a while after F1 volume starts.
- The exposure curve conditions on position only; if F7's wildcard slot (fixed positions 4–6) changes view behavior at those positions, the curve absorbs it on average — a position×wildcard split is a cheap future refinement inside backend/eval (no cross-file work).
- `nightly.run_all` grades `base_score` + `random` today; F6 registers its scorer via `backend.eval.scorers.register` and inherits the nightly + time-split machinery for free.
