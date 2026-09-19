# Full sweep — score every leaguemate, rank globally

> **Status:** active, not built. Branch `claude/full-sweep-0822-a1c3` from `origin/main` @ `b6e906a`.
> Companion: [`scope.md`](scope.md). Origin: [`docs/reviews/2026-08-22-trade-model-second-read.html`](../../reviews/2026-08-22-trade-model-second-read.html) (on branch `claude/trade-model-restrictiveness-7f3975` until that review PR merges) §03 (the blind spot) and the operator's 2026-08-22 ruling that rotating the sweep is not the fix — generating everything and ranking globally is.

---

## 1. What this changes, in plain words

Today the trade engine walks your leaguemates one at a time, keeps the best few ideas with each, and **stops as soon as it has banked enough cards** — in a 12-team league, typically after six partners. The other five are never scored. Because the walk order is fixed (ranked members first, then roster order), in a league where only you have ranked it is the *same* five skipped every refresh: 5 of 13 and 7 of 13 leaguemates never appeared in any deck across 6–11 refreshes.

After this change, with the flag on, the engine scores **every** leaguemate and then ranks all the ideas together. The deck you see is the best of the whole league, not the best of whoever came first.

## 2. What the code does today (anchors on fresh `origin/main` @ `b6e906a` — re-grep before editing, these drift)

| Site | `backend/trade_service.py` | What it does |
|---|---|---|
| Legacy loop (`trade_engine.v2` off) | `:4414` `global_target = max(30, max_per_opponent * 6)`; `:4416` `for idx, member in enumerate(eligible)`; `:4454` `if len(new_cards) >= global_target: break` | v1 path; dead in prod (`trade_engine.v2 = true`) but the same rule |
| **Live loop** (`_generate_trades_v2`) | `:5343` `global_target = …`; `:5414` `for idx, member …`; `:5710` `if len(new_cards) >= global_target: break` | The served path for arms `current`, `challenger` (D-095 overlay, same callable) and `baseline` (arm A, same callable under `model_a()`) |
| Global ranking | `_dedup_and_sort` (after the loop) | Already sorts every collected card by `composite_score` desc and applies past-decision / R4 / C4 caps. **Removing the break is sufficient for global ranking — no new ranking code.** |
| Streaming | `on_opponent_done(idx+1, total, snapshot)` inside the loop | Fires after each opponent; the client progress bar reads it. Unchanged; it simply fires N times instead of ~6. |
| Per-pair budget | `max_cards = max_per_opponent` (5; 8 when `deck.exploration` over-generates) | Unchanged. Top-N *within* a partner was never the problem. |

| Site | `backend/server.py` | What it does |
|---|---|---|
| `:4854` `_EXPLORATION_BASE_PER_OPP = 5` | Hardcoded module constant | Read at `:5730` (over-generation = 5 + `exploration_overgen`) and `:5862` (`_split_exploration_pool(final_cards, 5)` trims back to 5 per opponent after generation). **No config knob** — [G-058](../../../living-memory/GOTCHAS.md). |

Other arms — **verify, don't assume**:

| Arm | Module | Expected finding |
|---|---|---|
| `gen_v2` | `backend/trade_gen_v2.py` `generate_league_suggestions` — `for idx, member in enumerate(boarded)` (~`:1111`) | No opponent-level early exit; the only budgets are per-pair (`_ITER_BUDGET`, pools). Divergence-only by design (unranked partners are served by the flag-off engine's consensus path, which *is* this change's live loop). **No code change; pin the behaviour with a test.** |
| `fit` | `backend/trade_gen_fit.py` — `for member in eligible` (~`:331`) | Same: per-pair `fit_max_packages_per_pair` cap only. Dark (`bakeoff_include_fit = 0`). **No code change; pin with a test.** |

## 3. Design

### 3.1 Flag — `trade.full_sweep`, ships **dark** (`false`)
- `config/features.json`: add the key with a `_comment_full_sweep` block in the house style (what ON does, what OFF does, why dark, kill switch = this key, hot-reload via `POST /api/feature-flags/reload`).
- Resolution: `FLAGS.trade_full_sweep` — follow whatever `backend/feature_flags.py` does for `trade_divergence_fallback` (it is resolved dynamically; read the module, do not invent a registry).
- **OFF = byte-identical to today.** Both loops keep the `global_target` break. This is the code-walk proof A3 must produce.

### 3.2 Behaviour ON
In **both** loops (`:4454`, `:5710`), the early exit becomes:

```python
if not FLAGS.trade_full_sweep and len(new_cards) >= global_target:
    break
```

Nothing else in the loop changes: ordering (ranked-first, then roster order) stays — it now only governs streaming order; `max_cards` per pair stays; the consensus fallback for a zero-divergence boarded member stays; `_dedup_and_sort` after the loop performs the global rank exactly as it does now. Keep `global_target` computed so the flag-off path is untouched. (`trade_service.py` has no logging; no log line is added — observability is `trades_generated.gen_ms`/`count` plus partner coverage derived from `deck_impressions`.)

### 3.3 Knobs — `exploration_base_per_opp` (default `5.0`) and `full_sweep_budget_s` (default `30.0`)

`full_sweep_budget_s` — the flag-on wall-clock rail from §3.5: both loops break once the sweep has run longer than this many seconds (≤ 0 disables). Registered in `_DEFAULT_CFG`, `_MODEL_CONFIG_DEFAULTS`, and pinned EXCLUDED from `MODEL_A_PROFILE` (job-level rail, inert to arm A's gate profile). Reads are clamped: `exploration_base_per_opp` → `max(1, int(...))` so a 0 cannot empty the deck.

#### `exploration_base_per_opp`
Replace the two reads of `_EXPLORATION_BASE_PER_OPP` in `server.py` with `_deck_cfg("exploration_base_per_opp", 5)` (the same accessor `exploration_overgen` uses at `:5727`). Register the default in **both** `trade_service._DEFAULT_CFG` and `database._MODEL_CONFIG_DEFAULTS` (format at `database.py:2394`). Keep the module constant as the fallback default so nothing moves at ship. This is flag-independent and byte-identical at `5.0`; it exists so the operator can raise the per-partner keep without a deploy, which G-058 records as the trap that makes `max_per_opponent` a no-op.

### 3.4 Deck size consequences (operator dial, not code)
With the flag on, a 12-team league produces up to 11 × 8 cards pre-trim → 11 × 5 = 55 after the exploration trim → capped by `bakeoff_deck_limit` (prod **60**) when interleaved, and `first_session_deck_max` (10) on a first deck. So the served deck grows from ~25–31 toward the cap. **The deck-size dial depends on serving posture:** with `bakeoff_serve_interleaved = 1` (prod today, read from the live `model_config`) the composer caps at `bakeoff_deck_limit` (prod 60, code default 30); in dark serving (`= 0`) the served deck is arm `current`'s list uncapped, so the dial is `exploration_base_per_opp` × partners. This change adds no cap of its own. Note both in `config-reference.md` under the flag.

### 3.5 Latency — the honest part
- Measured today (prod `trades_generated.gen_ms`, August): median **1.7 s**, p90 **5.3 s**, max 11.6 s, for ~6 partners.
- Full sweep is ~11 partners: expect median ≈ **3 s**, p90 ≈ **10 s**. **Correction (A3 review):** only the *consensus* pair path carries a 1.0 s per-pair deadline; the v3 divergence path has **no deadline and no iteration budget** (`trade_optimizer.py:231`). Because ranked members are visited first, today's decks already pay the v3 cost for every boarded partner — the sweep adds the unranked tail, which is bounded. But a league with many boards has no bound, so the flag-on path gets a job-level wall-clock rail: knob `full_sweep_budget_s` (default 30 s; ≤ 0 disables) breaks the sweep when exceeded, under `_JOB_HARD_TIMEOUT` = 60 s (`server.py:2230`). Note `_relaxed_targeted_pass` re-enters the loop, so a targeted job that comes back empty pays a second sweep under the same rail.
- The job is asynchronous and **streams** cards per opponent, so the user sees the deck fill rather than a spinner; the hard ceiling is `_JOB_HARD_TIMEOUT` in `server.py` (A1: read and record the value in scope.md).
- **Threads will not help.** The enumeration is pure-Python CPU work; under the GIL a thread pool buys nothing. The second-read summary's "~4 workers brings it back" was wrong and is withdrawn here. Real latency levers are a separate plan (**phase 2**, not this change): (a) a per-pair result cache keyed on `(user, opponent, roster hash, board version, knob snapshot)` — most refreshes change nothing, so the second sweep is nearly free; (b) a process pool, which needs a fork-safety review under gunicorn. Neither is built here. Record the deferral as part of D-154.

### 3.6 Decision to record — D-154
"Full sweep built dark; threads rejected (GIL); latency work deferred to a phase-2 plan; deck size is the operator's `bakeoff_deck_limit` dial." Also note it narrows the *accepted consequence* recorded in `_comment_compressed_board` ("rescued boarded members displace unranked members' consensus cards") — with the flag on, nobody is displaced.

## 4. Work split — disjoint file ownership, no shared edits

| Agent | Owns (may edit) | Must not touch |
|---|---|---|
| **A1 — builder** | `backend/trade_service.py` (the two `break` sites + `_DEFAULT_CFG` row), `backend/feature_flags.py` (if registration needs it), `config/features.json`, `backend/database.py` (`_MODEL_CONFIG_DEFAULTS` row), `backend/server.py` (the two constant reads), `backend/tests/test_full_sweep.py` | anything in A2's column |
| **A2 — arm parity + docs** | `backend/tests/test_arm_sweep_parity.py`, `docs/config-reference.md`, `living-memory/LLD.md`, `docs/plans/README.md` (one row) | engine source, `features.json`, `scope.md` (the lead owns it) |
| **A3 — reviewer** (after A1+A2) | nothing — read-only; reports findings | — |

## 5. Tests — what must exist before merge

`backend/tests/test_full_sweep.py` (A1), pytest, using the existing test-support fixtures (see `backend/tests/support/` and how `test_bakeoff_arm_a_golden.py` builds a league):
1. **Flag OFF, byte-identical:** with a fake per-pair generator that returns `max_per_opponent` cards per member and 12 members, the loop visits exactly the number of members today's `global_target` arithmetic implies (assert the call count == today's count, computed from the same formula), and the `break` fires.
2. **Flag ON, every member visited:** same fixture, call count == `len(eligible)`.
3. **Global ranking:** give the *last* member one card with the highest `composite_score`; with the flag on it is the first card returned.
4. **Streaming:** `on_opponent_done` fires `len(eligible)` times with `idx` monotonically increasing and a snapshot that never shrinks.
5. **Both loops:** tests 1–2 run against both `_generate_trades_impl` (legacy) and `_generate_trades_v2` (live), driven by the `trade_engine.v2` flag fixture.
6. **Knob:** `_split_exploration_pool` honours `exploration_base_per_opp` = 3 (keeps 3 per opponent) and the default 5 reproduces today's split exactly.
7. **Sabotage proof:** A1 records, in the test file's docstring, the one-line engine edit that makes each test fail (e.g. re-adding the unconditional break) and confirms it was tried.

`backend/tests/test_arm_sweep_parity.py` (A2):
8. **gen_v2 pin:** with N boarded members and a stubbed per-pair stage, `generate_league_suggestions` visits all N (no early exit). Sabotage: insert a break after 2 members, test fails.
9. **fit pin:** same for `trade_gen_fit`.

CI: `pytest backend/tests` green; `tsc --noEmit` and `testid-lint` unaffected (no client change) but must still run green before push.

## 6. Evidence & ship gate (D-056 — no Maestro, no simulator)
- Unit tests above, in the ledger with the sabotage lines.
- **Code-walk proof** (A3): flag-off path is byte-identical — cite both `break` sites and the knob default; prove no other read of `trade_full_sweep` exists (`git grep`).
- **Manual TestFlight checklist for the operator** (no client build needed — flag is server-side): (1) flip `trade.full_sweep` on, `POST /api/feature-flags/reload`; (2) refresh a deck in a 12-team league where only you have ranked; (3) count distinct partners in the deck — expect ≥ 9 of 11 (today: 6); (4) read `trades_generated.gen_ms` for that job — record it; (5) confirm the deck did not exceed `bakeoff_deck_limit`; (6) flip off, refresh, confirm the deck returns to ~6 partners. Put the numbers in `TEST_LEDGER.md`.
- Pre-push: `FTF_SKIP_SIM_GATE=1` (standing posture), CI green.

## 7. Out of scope — deliberately
- Any change to gates, knobs or ranking math (Track B is analysing those separately; nothing here pre-empts it).
- Parallelism, caching, or any latency work (phase 2).
- Client changes. The deck cap. Partner-order rotation (superseded by this plan).

## 8. Operator questions (file in Q-030 when answered — Q-028 is the merged-calculator tab question)
- When to flip: after the TestFlight checklist, or straight away on the operator's own leagues?
- Deck cap: keep `bakeoff_deck_limit = 60`, or lower it once the sweep fills it?
