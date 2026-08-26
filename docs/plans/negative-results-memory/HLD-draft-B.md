# HLD Draft B — Negative-results memory (failure-modes / scale lens)

**Date:** 2026-08-21 · **Author:** Agent B (dual-agent HLD, adversarial lens)
**Parent:** [PRD.md](PRD.md) (FINAL) · Facts: [research-verification.md](research-verification.md) ("memo") ·
Gates: [scope.md](scope.md) · Plan: [PLAN.md](PLAN.md)
**Stance:** every section below asks "where does this break under reality?" first and designs
from the wreckage backward. Every attack carries a fix. The output is a buildable design,
not a list of reasons to not build.

All file:line citations are from this checkout (`origin/main` @ `451d2eb` lineage); `server.py`
and `database.py` move fast — re-grep before trusting a number across merges.

---

## 1. Context — what we are strapping the new part onto

The trade engine is a **single-process Flask app (one gunicorn worker on purpose —
`backend/CLAUDE.md` §Gotchas) that runs generation jobs on daemon threads**
(`server.py:6303-6310`, entry `_run_trade_job` at `server.py:5412`). Multiple jobs run
concurrently on sibling threads; per-job "config" state rides thread-locals
(`trade_service.py:991-1010` `_cfg_override`, `:1032-1048` `r4_bypass`,
`:1070` stud-tax, `:1134` pick-pricing); per-job *data* state rides either constructor/kwarg
seams (`exclusion_keys`, `trade_service.py:3951-3956`, with deliberate
**overwrite-per-call** semantics at `:3983`) or per-card multiplier dicts computed from one
bulk read (`_deck_fatigue_multipliers`, `server.py:4482-4541`).

The bake-off fans out three arms **sequentially on the one job thread**
(`server.py:5672-5694`), with arm A's whole personality expressed as a thread-local config
overlay (`bakeoff_profiles.MODEL_A_PROFILE` via `_cfg_override`) and per-arm config
snapshots taken *inside* each arm's context (`bakeoff_runner.snapshot_config`,
`bakeoff_runner.py:423-434`).

Negmem inserts one derived, decayed, clamped map into this machine, consulted at
generation time in three engine paths, plus one aggregation feed into gen_v2's already-
ratified `acceptance_prior` (`trade_gen_v2.py:283-308`, multiplied at `:655`, kwarg at
`:862`, consumed per member at `:951`). The PRD fixes the semantics (soft, clamped,
stamped, derive-on-read, no tables — NG6). This HLD fixes **where it breaks and what
happens then.**

### 1.1 The three inherited fragilities this design must not amplify

1. **Instance-state reuse.** `TradeService` objects live in the session
   (`sess["trade_svcs"]`, resolved at `server.py:5438-5440`) and are reused across jobs.
   State parked on `self` survives between jobs — which is exactly why `exclusion_keys`
   has overwrite-per-call semantics ("None ⇒ empty set, never keep-previous",
   `trade_service.py:3980-3983`). A pinned job and an organic job for the same session
   can run concurrently **on the same TradeService instance** — a pre-existing, accepted
   race on `self._exclusion_keys`. Negmem must not widen it.
2. **The executemany first-row-keys trap (T2-class).** `save_deck_impressions` inserts
   the batch with one `insert(...)` over a list of dicts (`database.py:5503-5515`);
   SQLAlchemy compiles the statement from the FIRST row's keys. The codebase already
   carries two scars and two documented fixes: bake-off attribution columns are set on
   EVERY row, never conditionally (`server.py:4251-4263`), and the fit stamps ride
   *inside* `features_json` precisely so the trap "cannot drop them"
   (`server.py:4197-4206`).
3. **The import-binding no-op trap (T1-class).** D-099-adjacent ruling in
   `living-memory/DECISIONS.md:1067`: live predicates are "called through the module
   namespace … never bound by name, never forked, so trade_service fixes propagate (the
   audit's import-binding no-op trap)." A module-global map rebound per job and consumed
   via `from .negmem import current_map` would freeze the import-time (empty) binding
   forever — and because empty map = identity = flag-off behavior, **every golden test
   would pass while the feature silently does nothing.**

---

## 2. Architecture

### 2.1 Components (all inside `backend/`, no new tables — NG6)

| Component | Home | What it is |
|---|---|---|
| **Map builder** | new `backend/negmem.py` (leaf: imports `database`, `feature_flags` only — the `suggestion_telemetry` discipline, `backend/CLAUDE.md` §Gotchas) | `build_negmem_map(user_id, league_id, as_of, *, cfg) -> NegmemMap` — pure function of (inputs, table state at read time). One bulk read; admission (R1), decay, netting (§5.3), shrinkage, clamp all in Python over the result set. |
| **`NegmemMap`** | `negmem.py` | Frozen job-scoped value object: `{(partner_league_id, reason_family): Cell(n_raw, n_decayed, mult)}` + `ver`, `built_at`, `build_ms`, `degraded: bool`. `mult_for(partner_league_id) -> float` returns the **min across admitted family cells** for that partner (one number per candidate consult — the per-opponent loops know the partner, not the family, of a *candidate*). Identity map when empty or degraded. |
| **Consultation seams** | `trade_service.py`, `trade_gen_v2.py`, `trade_gen_fit.py` | Additive kwarg per path (§2.2). Multiplies candidate scores after all gates; membership never touched. |
| **M2 feed** | `negmem.py` (`load_acceptance_stats(league_id, lookback_days)`) + the two call sites `trade_service.py:4001` and `bakeoff_runner.py:1212` | Aggregation over `trade_matches` per league-mate → `acceptance_stats` kwarg. Flag OFF ⇒ kwarg not passed (C1). |
| **Stamp** | `server._log_deck_impressions` features assembly (`server.py:4135-4212`) | `features_json.negmem` on EVERY row while influence was possible (§3.4) — inside `features_json`, never a top-level row key (fragility #2). |
| **Readout** | `negmem.py` (`negmem_readout`) + readout-pack SQL | R8. Dumps every cell as-of; joins stamp rates per arm; carries the GR4 joint-multiplier audit and the §4.2 id mapping. |
| **Knobs/flag** | `trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS` + `_PINNED_KNOBS` + `config/features.json` `trade.negmem` | R10, §5.1 — the triple registration is load-bearing, not bookkeeping (§4 KD-6). |

### 2.2 The threading decision — parameter, not thread-local (KD-1)

**The map travels as a parameter. Thread-locals are for the knobs only, and only via the
existing `_c()` overlay.**

Why not a thread-local map (the `_cfg_override` pattern)? Because the two failure surfaces
point opposite directions:

- **Between concurrent jobs** (different daemon threads): a thread-local map would be
  safe — that is the pattern's home turf.
- **Between bake-off arms** (same thread, sequential): a thread-local map set once per job
  is *shared* by all three arms — which is correct for the map (one job, one evidence
  snapshot, C5 determinism) but means **arm A cannot opt out through the map object**.
  Arm A ("the engine as it behaved before the 2026-08-16 wave",
  `trade_service.py:1017-1024`) must not consult negmem. Its opt-out must be expressible
  the way every other arm-A opt-out is: a config value in `MODEL_A_PROFILE` applied via
  `_cfg_override`. Hence: **strength/floor/min-evidence/half-life are read via
  `ts._c(...)` at consult time** (thread-local-override friendly, namespace-accessed per
  fragility #3), and `MODEL_A_PROFILE` pins `negmem_strength: 0.0`. The *map* itself
  carries no strength — it carries evidence; the multiplier is computed at consult time
  as `1 - strength·(1 - cell_mult)` clamped to `[negmem_floor, 1.0]`, so `strength 0` is
  arithmetic identity on every arm that pins it.
- **The leak scenario a naive thread-local invites:** an exception between arm fan-outs,
  or a code path that sets the local without a `finally`, leaves one job's map visible to
  the next job scheduled on a reused thread. The `contextmanager`+`finally` discipline
  prevents it — but a parameter cannot leak at all, and the additive-kwarg seam already
  exists on every path this feature touches.

**Signatures (all additive, default `None` = byte-identical):**

| Path | Change |
|---|---|
| v1/v3 | `generate_trades(..., negmem_map=None)` beside `exclusion_keys` (`trade_service.py:3951`). Stored per call as `self._negmem_map` with the SAME overwrite-per-call rule as `_exclusion_keys` (`:3983`) — `None` ⇒ identity, never keep-previous — because fragility #1 makes keep-previous a stale-evidence leak across jobs. Consulted in `_generate_for_pair`'s scoring (per-opponent loop at `trade_service.py:4124-4144`) — the multiplier folds into `composite_score` before `_dedup_and_sort` (`:4167`), so streaming snapshots and final assembly see the same numbers. |
| gen_v2 | `generate_league_suggestions(..., negmem_map=None)` beside `acceptance_stats` (`trade_gen_v2.py:862`); resolved once per member at the `:951` seam (`nm = negmem_map.mult_for(member.user_id) if negmem_map else 1.0`) and multiplied into `score` at `:655` alongside `accept_prior`. Both call sites updated: `trade_service.py:4001` and `bakeoff_runner.py:1212`. |
| fit | `negmem_map` kwarg on the fit entry (`trade_gen_fit.py:267` already receives `past_decision_keys`); the multiplier applies in the **rank score**, not in `_apply_post_filters` (`trade_gen_fit.py:753-850`) — fit's post-filters are hard drops by ruling; a soft prior in a drop-chain would be the fourth filter the PRD forbids (memo §2h table). |
| likes-you injector | **exempt** (R4 of the PRD) — no signature change; injected cards never pass through a consult site by construction (`server.py:5748-5759` runs after generation). |

**The relaxed targeted pass** (`trade_service.py:4271-4318`) re-runs generation inside
`_cfg_override(overrides)` on the same thread. Because the map is instance/param state and
the knobs ride `_c()`, the relaxed rerun consults the SAME map under the SAME strength —
no special case. (Attack considered: could negmem cause the `not cards` → relaxed-pass
trigger? No — soft multipliers cannot empty a list; only gates can. NG1 holds
structurally.)

**Where the naive implementation silently no-ops (T1, stated for the record):** a
`negmem.py` module global `_current_map` rebound in `_run_trade_job` and imported by name
into `trade_gen_v2.py` at module load. Consumers hold the import-time empty dict; every
rebuild rebinds the name in `negmem.py` only. Behavior = identity = flag-off, so C1's
golden passes, C5 passes, unit tests on the builder pass — only C3 (stamp coverage on
influenced rows) *could* catch it, and only if the stamp is written from the consumer side
(it is — §3.4 stamps from the map the *card* actually saw). Fix is the architecture above:
**there is no module-global map, anywhere, ever.** A structural test greps `negmem.py` for
module-level mutable map state (the `check-*.js` discipline, Python edition).

### 2.3 Composition diagram (job timeline, one daemon thread)

```
_run_trade_job (server.py:5412)
  ├─ session/service resolution (:5429-5447)
  ├─ exclusion_keys build (:5498-5505)                     [existing]
  ├─ NEW: negmem_map = build_negmem_map(user, league, now) [one bulk read; fail-open §3.2]
  ├─ NEW: acceptance_stats = load_acceptance_stats(league) [M2; flag-gated; fail-open]
  ├─ bake-off? ── arms A,B,C sequential, one thread (:5672-5694)
  │     arm A: _cfg_override(MODEL_A_PROFILE ∪ {negmem_strength:0}) → map inert
  │     arm B: live cfg → map consulted in v1/v3 loops
  │     arm C: gen_v2_cards → map + acceptance_stats kwargs (bakeoff_runner.py:1212)
  │     snapshot_config() per arm (bakeoff_runner.py:423) — sees negmem knobs iff in _DEFAULT_CFG (KD-6)
  ├─ else: generate_trades(**kwargs, negmem_map=…) (:5696)
  ├─ likes-you injection (:5748)          [exempt — after generation]
  ├─ F3 suppression + fatigue mults (:5794-5810)  [unchanged, NG9]
  ├─ F5 taste mults (:5845)               [unchanged, NG9]
  ├─ _order_deck (:5900)                  [unchanged — negmem is INSIDE base_score]
  └─ _log_deck_impressions (server.py:4040-…) — negmem stamp inside features_json (§3.4)
```

---

## 3. Data & Flow

### 3.1 The bulk read — exactly what it queries, and what it costs

One query, the `load_deck_fatigue_events` shape (`database.py:6133-6173`) widened with a
LEFT JOIN:

```
SELECT i.impression_id, i.trade_hash, i.features_json, i.shape_bucket,
       i.is_ghost, i.trade_intent, o.action, o.acted_at,
       r.reason, r.detail, r.key_source
FROM deck_outcomes o
JOIN deck_impressions i ON i.impression_id = o.impression_id
LEFT JOIN trade_pass_reasons r ON r.impression_id = o.impression_id
                              AND r.key_source = 'impression'
WHERE i.user_id = :u AND i.league_id = :l
  AND o.action IN ('viewed','pass','not_interested','like','undo')
  AND o.acted_at >= :horizon
```

- **Indexes it rides:** `ix_deck_impressions_user_league` (`database.py:610-614`) +
  `ix_deck_outcomes_impression` (`database.py:758-761`) + the `trade_pass_reasons` PK on
  `impression_id` (`database.py:925`). No table scan on either dialect.
- **`:horizon`** = `max(clean_epoch_floor '2026-08-20', as_of − 4·negmem_halflife_days)`.
  At the default 45d half-life the read is bounded at ~180 days regardless of how big the
  spine grows — evidence older than 4 half-lives contributes < 6.25% of a rejection and
  is below the shrinkage floor's resolution. **This cap is what keeps derive-on-read
  O(recent activity), not O(lifetime history)** — without it, 10x is a slow creep into
  the S6 gate with no alarm.
- **Viewed-gating and undo-pairing happen in Python** over the one result set (group by
  `impression_id`), NOT as extra self-joins — a pass row is admitted only if a `viewed`
  row exists for the same impression (R1a), and an `undo` row negates its paired pass
  (R1d). One round-trip, not three.
- **Cost today:** the largest known single-user slice is 4,003 impressions / 61 decisions
  in 14 days (memo §8). A 180-day horizon over that user ⇒ low-tens-of-thousands of
  impression rows but only outcome-bearing rows return (~hundreds–low-thousands).
  **Cost at 10x:** ~10k–40k returned rows worst case for a hyperactive league. Index-
  driven join, single round-trip: tens of ms on Render PG, similar on SQLite WAL (readers
  never block under WAL, `database.py:85-96`). The job already pays two reads of exactly
  this shape per generation — fatigue (`server.py:4430-4479`) and Thompson v2
  (`load_deck_arm_events`, `database.py:5998`) — so negmem is a third sibling, not a new
  class of cost. The S6 gate should be set relative to those siblings (LLD: p95 ≤ 2× the
  fatigue read's p95, absolute ceiling 250ms), and the timing log records `build_ms` per
  job from day one.
- **M2 aggregation** (`load_acceptance_stats`): GROUP BY over `trade_matches` for one
  league via `ix_trade_matches_user_{a,b}_league` (`database.py:443-452`), lookback 180d
  in the query (R5). `trade_matches` requires mutual likes to exist at all — it is and
  will remain the smallest table in this feature's blast radius. At 10x: still trivial.

### 3.2 When the bulk read is slow or FAILS mid-job — the answer, not a shrug

**Fail-open to the identity map. The job never dies for negmem.** This is forced, not
chosen: C1 says flag-off is byte-identical and NG1 says the mechanism is soft — therefore
identity is always a *legal* output, and the F3 precedent already rules ("Any read failure
degrades to all-1.0 — generation never breaks", `server.py:4497-4503`). Failing the job
would convert a read hiccup into zero deck supply — precisely the GR1 violation the
guardrail exists to catch.

But fail-open without observability is how features die silently (fragility #3's cousin).
Three trip-wires, all cheap:

1. **`NegmemMap.degraded = True`** on any build exception or on build_ms > the S6
   ceiling×2 (a build that slow is a problem even when it succeeds). A degraded map is
   identity AND is recorded on the job dict (`_trade_jobs[job_id]["negmem"] =
   {"degraded": true, "err": …}` — the `suppression_note` pattern,
   `server.py:5811-5814`).
2. **Stamp asymmetry as signal:** while the flag is ON and the build succeeded, every
   impression row carries a `negmem` key (§3.4). A day of rows with the flag ON and no
   `negmem` keys = builds failing = one SQL query away from visible. The readout pack
   computes exactly this: `stamp_rate BY day, arm` — expected 100%, alert below it.
3. **Persistent-failure escalation is an operator runbook line, not code:** if the
   degraded rate over 24h exceeds 1% of jobs, set `negmem_strength = 0` (stop paying for
   a read you throw away) and investigate; the materialization gate (§5.4) is the
   structural fix if the cause is scale rather than fault.

**Deliberately rejected:** fail-closed (job error) — converts soft feature into hard
availability risk; retry-in-job — a daemon thread retrying a slow DB read is how job
latency compounds under load; stale-map reuse across jobs — violates C5 determinism and
fragility #1.

### 3.3 Netting and read-time consistency — the ordering hazards, named

The map is a **read-time computation over an append-mostly event log written by three
different HTTP calls.** The hazards:

- **H-1: reason lateness.** The pass outcome and the reason row arrive in *separate
  requests* (swipe route `server.py:11662`; pass-reason route `server.py:12091`, which
  also writes its own outcome row via `server.py:12037`). A job that starts in the gap
  sees a bare pass — not admitted (R1b) — and the next job sees it admitted. **Evidence
  appears in the past**: the map is monotone per job (built once at job start, snapshot
  semantics) but NOT monotone in wall clock across jobs. *Fix:* accept and document —
  `as_of` = build time; the map is "table state at build time evaluated under the
  admission rule." What must NOT happen is the builder and the RFPS metric using two
  different admission predicates: **one shared admission implementation** (a single
  SQL/WHERE fragment + Python predicate pair in `negmem.py`, consumed by builder, readout,
  and the metric SQL — the `deck_centerpiece` "one definition so the cap and the metric
  cannot drift" discipline, `server.py:4405-4412`).
- **H-2: the upsert hop.** `trade_pass_reasons` upserts in place with one
  `switched_from` hop (`database.py:880-887`, `:933`). A reason can *change family after
  admission* — a cell that held 3 `value` rejections yesterday can hold 2 today with no
  new events. R6 already concedes this ("evaluated at its current state"). The failure
  nobody designed for hides here — see Risk R-X in §6: the *pre-registered RFPS
  baseline* is computed over mutable rows. *Fix:* at pre-registration time, snapshot the
  baseline cohort **by impression_id with its cell assignment** into a committed artifact
  (readout dump checked into the plan folder); at window close, evaluate on reason state
  frozen at close and report the switch-rate (rows whose family changed inside the
  window) alongside the point estimate. A switch-rate above ~5% invalidates the window —
  extend, per §8.3's ladder.
- **H-3: like-netting scope.** A viewed like on a card toward partner P nets against
  every (P, ✱) cell (PRD §5.3) — computed in the builder from the same result set (like
  rows are already in the §3.1 read). Because netting is derive-on-read there is NO
  write-path ordering hazard between a like landing and the map: a like is visible to
  every build that starts after its insert commits. The only consistency need is
  **within-job**: one map, built once, used by every arm of that job — never rebuilt
  mid-job (or arms would diverge for a non-model reason and the bake-off comparison
  would be contaminated). The parameter architecture makes mid-job rebuild structurally
  impossible (nothing holds a builder handle after job start).
- **H-4: concurrent same-session jobs** (fragility #1): a pinned job and an organic job
  on the same TradeService can interleave `self._negmem_map` writes. Same pre-existing
  race class as `_exclusion_keys`; same accepted blast radius (both maps are valid
  recent snapshots; the loser's ordering shifts within clamp bounds; membership is never
  affected). Recorded honestly here; not widened: the map reference is read ONCE into a
  local at the top of `_generate_trades_impl` and threaded through the loop from the
  local, so a mid-generation overwrite cannot produce a mixed-map deck. (That last
  clause is the delta over the existing `_exclusion_keys` behavior, and it is free.)

### 3.4 Stamps under executemany — uniformity is enforced, not hoped for (T2)

The stamp is `features_json.negmem = {"m": <final mult>, "keys": [...], "ev": {...},
"ver": 1}` — **inside `features_json`**, following the fit/fit_diag precedent verbatim
(`server.py:4197-4206`): one Text column always present in every row, so the first-row-keys
compilation of `save_deck_impressions` (`database.py:5503-5515`) *cannot* drop it.

What breaks if stamps appear on some rows and not others? C3's spine SQL
(`stamped/influenced = 100%`) becomes uncomputable — you cannot distinguish "uninfluenced"
from "stamp dropped," so the GR4 joint-multiplier audit and the RFPS arm attribution both
silently under-count. Uniformity rule, enforced in the features assembly
(`server.py:4135` block), mirroring the bake-off every-row rule:

- Flag OFF ⇒ **no row anywhere** carries the key (byte-identical features_json — the F5
  `taste_attrs` conditional-key precedent, `server.py:4180-4182`).
- Flag ON and this job's map non-degraded ⇒ **every served AND ghost row** carries the
  key: influenced rows with their real `m < 1.0` and evidence; uninfluenced rows with
  `{"m": 1.0}`; likes-you-exempt rows with `{"m": 1.0, "exempt": "likes_you"}`. Absence
  is impossible while ON, so absence = build failure (§3.2 trip-wire 2) and C3 reduces to
  `COUNT(m < 1.0 AND keys IS NULL) = 0`.
- Flag ON and degraded ⇒ every row `{"m": 1.0, "degraded": true}` — the failure is in
  the data, not inferred from its absence.

Unit + structural test: build a deck whose FIRST card is an unstamped-candidate (likes-you
injection leading the deck — the exact scenario from the model_arm scar,
`server.py:4251-4256`) and assert the whole batch retains the key.

### 3.5 The M2 feed — the stub's math at n=0, and the one real crash edge

`acceptance_prior` (`trade_gen_v2.py:283-308`): missing key or `None` stats → returns
`p0` (`:303-304`) — uniform, ordering untouched. A present key with `responses=0` →
`(0 + m·p0)/(0 + m) = p0`. **The math is total except one settable edge: `m = 0`.**
`gen2_accept_prior_strength` is a Float knob editable via `PUT /api/admin/config`; at
`m=0` with a zero-response key present the expression is `0/0` → `ZeroDivisionError` →
the whole generation job dies inside arm C. Today unreachable (no caller passes stats);
the feed makes it reachable. *Fix, two layers:* the aggregation query **never emits keys
with `responses = 0`** (they carry no information; omission = `p0` anyway), and the LLD
adds a guard clause to the feed path (not to `acceptance_prior` itself — NG9 forbids
touching the ratified math; the guard lives in `load_acceptance_stats`, which clamps
`m <= 0` handling by simply returning `{}`). C4's parity test covers `n=0`, `m→0`,
`accepts > responses` (already clamped at `:307`).

S4 honesty (PRD): with the decline route having essentially never fired (memo §2c,
`deck_suppressions` 0 rows; `trade_matches` decisions rare), the aggregation returns a
near-empty dict for months. **A uniform read is the expected, correct output** — the
readout prints the aggregation row-count next to the spread so "null result" and "broken
feed" are visually distinct.

### 3.6 Readout & observability (R8, GR4)

`negmem_readout(user, league, as_of)` re-runs the builder (same shared admission
predicate — H-1 fix) and dumps every cell raw/decayed/mult/floored. The readout-pack SQL
adds: stamp rate per arm per day; stamp magnitude histogram (S3); degraded-rate (§3.2);
S6 latency percentiles from the timing log; the §4.2 id-mapping join
(`features_json.partner_user_id` is a **global platform id** — memo §2e — while map keys
are league identity per R9/ADR-012; for Sleeper sole owners the strings coincide, for
co-owned rosters the readout maps through `canonical_owner_id`).

**GR4 has a computability gap the PRD does not flag — closed here.** GR4 audits the joint
product negmem × taste × fatigue × Thompson "from stamps," but taste and fatigue
multipliers are **not individually stamped today** — only `propensity` (Thompson,
`database.py:497-499`) and the score pair exist. The joint product is reconstructable as:

```
joint = negmem_stamp.m × (final_score / base_score)   -- non-bake-off rows only
```

because negmem is generation-time (inside `base_score`) and the entire post-generation
multiplier stack (Thompson × fatigue × taste × diversity) is what separates
`final_score` from `base_score` (`server.py:4048-4051`, `_order_deck` fold at
`server.py:3894-3904` per memo). The diversity penalty pollutes the ratio slightly; the
LLD either accepts it (GR4's 0.15 bar has margin) or adds `fatigue_m`/`taste_m` keys
into `features_json` under the same uniformity rule — a one-line change at
`server.py:5804/:5845` where both dicts are already in hand. **Decision for the LLD;
the HLD's requirement is that GR4 be *computable*, which the stamp shape above
guarantees.**

---

## 4. Key Decisions (each: attack → decision → fix residue)

**KD-1 — Map via parameter; knobs via `_c()`; arm A opts out via `MODEL_A_PROFILE`.**
Attack: thread-local map leaks between arms/jobs; module-global map no-ops (T1).
Decision: §2.2. Residue: one additive kwarg on three signatures + two call sites — all
default-None, C1-golden-safe.

**KD-2 — Fail-open to identity with three trip-wires.** Attack: silent fail-open = a
feature that dies quietly; fail-closed = availability coupled to a soft prior. Decision:
§3.2. Residue: a `degraded` bit on the job dict and readout SQL — no new storage.

**KD-3 — One shared admission predicate.** Attack: builder/metric/readout drift makes
RFPS unfalsifiable (H-1). Decision: single implementation in `negmem.py`, consumed
everywhere. Residue: the metric SQL imports a generated WHERE fragment or replicates it
under a parity test.

**KD-4 — Stamp inside features_json, every-row-while-ON.** Attack: T2 first-row-keys
drops the column; partial stamps break C3/GR4. Decision: §3.4. Residue: features_json
grows ~60 bytes/row while ON; flag-off byte-identical.

**KD-5 — Horizon cap at 4 half-lives.** Attack: derive-on-read cost grows with lifetime
history; S6 breach arrives as a slow creep with no alarm. Decision: §3.1. Residue: a
rejection older than ~180d contributes nothing even if `min_evidence` would otherwise
keep its cell alive — acceptable by construction (decay already made it < 0.0625 of an
event).

**KD-6 — Knob registration is a CI-enforced triple.** Attack (the GR3 question):
`snapshot_config()` iterates `_DEFAULT_CFG` (`bakeoff_runner.py:423-434` —
`{k: _c(k) for k in _DEFAULT_CFG}`). A negmem knob absent from `_DEFAULT_CFG` is
**invisible in `bakeoff_runs.config_json`** — a mid-round knob move becomes undetectable,
GR3's round-censoring rule cannot fire on data it cannot see, and the measurement window
quietly becomes the next D-091. Also: a knob absent from `_MODEL_CONFIG_DEFAULTS` cannot
be flipped at runtime at all (the settability trap, scope §2). Decision: all four knobs
land in `_DEFAULT_CFG` + `_MODEL_CONFIG_DEFAULTS` + `_PINNED_KNOBS` in the SAME commit;
the existing inventory test (`test_bakeoff_arm_a_golden.py:546-559`) then fails CI on any
future knob added to one and not the others. Residue: the `trade.negmem` FLAG is still
not in config_json (flags are not knobs) — mitigated by the stamp's `ver`/presence being
per-card evidence of the flag state, and by the rollout rule that flag flips happen only
at round boundaries with a CHANGELOG line.

**KD-7 — M2 feed emits no zero-response keys; `m<=0` returns `{}`.** Attack: §3.5's
`0/0` job-killer. Residue: none — omission is semantically identical to emission at `p0`.

**KD-8 — Rollback ladder, with the exact kill-surface of each rung (the PRD's G4 made
operational):**

| Rung | Mechanism | Kills | Keeps | State left behind |
|---|---|---|---|---|
| `trade.negmem` OFF | features.json + `POST /api/feature-flags/reload` | M1 build+consult+stamps AND the M2 kwarg (C1: arm C byte-identical) | nothing | **None live.** Residue = historical `features_json.negmem` stamps on already-served append-only rows + `config_json` snapshots — audit records, deliberately permanent, read by nothing at serve time |
| `negmem_strength = 0` | `PUT /api/admin/config` (deploy-free) | M1 arithmetic (mult ≡ 1.0) **and the build itself** (short-circuit before the bulk read — no point paying for a read whose output is discarded; this also makes strength-0 byte-identical in *timing*, not just bytes) | M2 feed (flag still ON) | none |
| `negmem_floor = 1.0` | same | M1 *effect* (clamp collapses to [1.0, 1.0]) | build + **stamps at m=1.0 with full evidence payloads** — this rung is SHADOW MODE: measure what the memory believes without letting it touch order | none |
| GR breach | `negmem_strength = 0` + window censored at flip ts (§8.3) | as strength-0 | — | none |

Derive-on-read is what makes every rung stateless: there is no aggregate to drain, no
cron to stop, no table to truncate. Deleting source rows deletes the memory (PRD §5.3) —
and that stays true on every rung.

**KD-9 — P0 (M2) and P1 (M1) share the flag but not the code path.** Attack: shipping
P0 first tempts wiring `acceptance_stats` unflagged ("it's just feeding a stub").
Decision: both behind `trade.negmem` from the first commit (PRD P0: "ships regardless of
rulings never means live regardless of the flag"); the C1 golden covers arm C explicitly.

---

## 5. Cross-Cutting

### 5.1 Bake-off citizenship (GR3, D-086)

Negmem is **generation-time**, so it is part of the model under test — it does not touch
the re-ranker bypass channel (`bypass_rerankers`, `server.py:5627`) and must never be
added to the post-generation stack (memo §2h's "presentation" row is explicitly the seam
this design rejects: it cannot stop doomed families consuming enumeration budget and it
is bypassed on bake-off decks — both disqualifying). Per-arm accounting works because
`snapshot_config()` runs inside each arm's `_cfg_override` context: arm A's snapshot
shows `negmem_strength: 0` in its delta, arms B/C show live values (KD-6). **Measurement
confound stated honestly:** with the flag global, "negmem-OFF arm" = arm A, which differs
from B by the whole `MODEL_A_PROFILE` — so the RFPS promotion read is within-arm
before/after across the round boundary against the pre-registered baseline (PRD §4.2),
never A-vs-B. The HLD makes this a readout-pack footnote so nobody runs the wrong
comparison in month three.

### 5.2 Identity & privacy

League ids everywhere in the map (R9; `_league_user_id`, ADR-012); the one deliberate
global-id touchpoint is the stamp/readout join (§3.6) which documents the mapping instead
of pretending it away. Privacy posture (c): all M2 state is aggregate, engine-internal,
derive-on-read; nothing per-person is persisted beyond the existing spine; ergo
`accounts.delete_user_data` needs **no change in v1** — and the §5.4 materialization, if
ever taken, adds a named deletion hook in the same commit (the memo §7 warning about
partner-keyed rows, pre-answered).

### 5.3 Operability (runbook lines shipped with the feature)

- Symptom: decks unchanged with flag ON → check stamp rate SQL (absent keys = builds
  failing, §3.2) → check `degraded` notes → check knob triple (KD-6) — in that order.
- Symptom: job latency up → S6 timing log percentiles; if build_ms is the driver at
  scale, take the §5.4 gate; if it is fault, strength-0 while investigating.
- Symptom: a tester reports "I keep seeing trades I rejected" with negmem ON → readout
  the (partner, family) cell as-of the serve; if `n_decayed < min_evidence` the answer
  is "working as designed, evidence below floor" — the readout makes that a lookup, not
  a debugging session.
- TestFlight checklist (D-056 evidence): operator flips flag for own league at a round
  boundary; verifies deck materially unchanged except named down-weights; runs the
  readout SQL against their own cells; passes a card twice with a reason and confirms
  the cell increments at the next job.

### 5.4 10x and the materialization fallback (the `negmem_` prefix, spent carefully)

When does derive-on-read hit S6? The read is O(outcome rows within horizon per
user-league). Breach requires roughly 100x today's per-league decision volume or a
pathological league — but the trigger is **measured, not assumed** (S6 p95 against the
LLD gate, reviewed at every window close). The fallback design, pre-committed so it is a
gate-flip and not a redesign:

- **`negmem_cell_rollups`** (the reserved prefix): one row per (user_id, league_id,
  partner_league_id, reason_family): `n_raw`, `n_decayed_at_anchor`, `anchor_ts`,
  `last_event_ts`, `schema_ver`. Exponential decay re-anchors exactly:
  `n(t) = n_anchor · 0.5^((t−anchor)/halflife)` — a sum of exponentials decays
  uniformly, so incremental maintenance is decay-then-add per new event, and a bulk
  rebuild from the spine reproduces it bit-for-bit (the parity test).
- **NG6's spirit preserved:** the table is a **cache, never a source of truth** —
  rebuildable from the spine at any moment, invalidated per (user, league) on any new
  admitted event, and versioned by `schema_ver` so a builder bugfix invalidates
  wholesale rather than serving stale math. Deletion stays structural: cache rows drop
  by user_id in `delete_user_data` (named in §5.2), and a rebuild after source-row
  deletion converges to the same emptiness derive-on-read would give.
- **Migration path:** ship the table dark behind `negmem_materialize` (0/1 knob,
  default 0, full KD-6 triple); dual-run for ≥1 week (build both, compare, log
  divergence count into the timing log); flip the read path only on zero divergence;
  keep the derive path as the readout's reference implementation forever (it IS the
  spec).

### 5.5 Docs & gates (scope §4/§5, unchanged by this draft)

config-reference (flag + 4 knobs + `negmem_materialize` reserved), data-dictionary
(`features_json.negmem` stamp row), architecture + HLD living-memory (the consult seam),
glossary, the soft-prior ADR citing D-067, taxonomy v1.1.0 three-way. Express lane: no —
bright line (flag surface + engine behavior). CI: pytest goldens (C1 both paths + arm C),
clamp/determinism units (C2/C5), M2 parity (C4), the T1 grep-test, the T2 first-row test,
knob-triple inventory (existing test extended, KD-6).

---

## 6. Risks (attack → fix, residual honestly sized)

| # | Failure mode | Blast radius | Fix in this design | Residual |
|---|---|---|---|---|
| R-1 | T1 import-binding no-op — feature silently inert while all goldens pass | weeks of "measurement" of nothing | no module-global map (KD-1); consumer-side stamps make inertness visible in stamp-rate SQL; grep-test | low |
| R-2 | T2 executemany drops stamps on decks led by exempt cards | C3/GR4 uncomputable; silent audit loss | stamp inside features_json + every-row-while-ON rule + the likes-you-first structural test (§3.4) | low |
| R-3 | Bulk read fails/slow mid-job | deck delayed or lost | fail-open identity + degraded bit + stamp-absence tripwire + runbook escalation (§3.2) | low; cost = occasional identity jobs, all visible |
| R-4 | Knob outside `_DEFAULT_CFG` → invisible to `config_json` → GR3 censoring blind → next D-091 | a poisoned measurement window | KD-6 triple + existing CI inventory test | low |
| R-5 | `m=0` × zero-response key → ZeroDivisionError kills arm C jobs | generation failures in prod | KD-7 (no zero-response keys; `{}` on m≤0) | nil |
| R-6 | Same-session concurrent jobs interleave `self._negmem_map` (H-4) | one deck ordered under the other job's equally-valid map | read-once-into-local; same accepted race class as `_exclusion_keys` | accepted, bounded by clamp |
| R-7 | Soft-layer compounding (negmem×taste×fatigue×Thompson) → de-facto exclusion | D-067 violated in spirit | GR4 with the §3.6 computability fix; floors raised on p5 < 0.15 | monitored |
| R-8 | Double-learning from one pass event (taste partner-attr + negmem cell) | over-punishment of a partner | same GR4 audit; R2's family gating keeps negmem's slice reason-carrying only; taste untouched (NG9) | monitored |
| R-9 | Derive-on-read cost creep at 10x | S6 breach as slow drift | horizon cap (KD-5) + S6 timing log + pre-committed materialization gate (§5.4) | low |
| **R-X** | **The one nobody designed for: mutable evidence under a pre-registered metric.** The `trade_pass_reasons` upsert (H-2) means the RFPS baseline cohort and the window-close numerator are computed over rows whose family assignment can change *after* pre-registration — the promotion decision's own input drifts under it, unfalsifiably, with no code bug anywhere | a graduation decision made on a moving target — the feature promotes or shelves on noise | snapshot the baseline cohort by impression_id + cell at pre-registration into a committed artifact; evaluate window-close on frozen-at-close state; report switch-rate; switch-rate > ~5% ⇒ extend, never adjudicate (§3.3 H-2) | low once snapshotted; the switch-rate line makes the residual measurable |

---

*End of Draft B. Reconciliation targets for the merge: KD-1 (parameter vs any thread-local
proposal in Draft A), the §3.4 uniformity rule, KD-6's CI triple, the §3.6 GR4
computability fix, and R-X's baseline-snapshot requirement — these five are the hills.*
