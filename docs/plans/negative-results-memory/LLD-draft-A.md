# LLD (draft A — Implementer lens): Negative-results memory

**Version:** draft A, round 1 · **Date:** 2026-08-21
**Serves:** [HLD.md](HLD.md) (FINAL — D-1..D-10 binding; §7 is this document's work order) ·
[PRD.md](PRD.md) (FINAL — R1-R11, NG1-NG9, C1-C5, GR1-GR4, §8.3) ·
Facts: [research-verification.md](research-verification.md) ("memo") ·
Settled: [reconciliation-log.md](reconciliation-log.md) — nothing decided there is reopened here.
All file:line citations verified on this checkout (worktree `claude/vigilant-spence-8583f5`).

---

## 0. The four LLD-owned DECIDEs, up front

| # | Question (HLD §7) | Decision | Where argued |
|---|---|---|---|
| DE-1 | D-5 combine rule: product vs min across a partner's family cells | **MIN** | §4.4 (with the 3-row fixture table) |
| DE-2 | Netting mechanism: decrement vs reset; magnitude; bounds | **DECREMENT** by `negmem_like_net` (default 1.0) per admitted viewed like, folded chronologically against every (P, ✱) cell with a clamp-at-zero after every fold step | §4.5 |
| DE-3 | Build-time knob read path | **Pass-in-from-server**: `server._run_trade_job` reads every build-time knob via `trade_service._c(...)` on the job thread *before* the arm fan-out (no overlay active) and passes plain floats into `build_map`. negmem.py contains **zero** knob defaults. | §4.2 |
| DE-4 | GR4 computability: accept score-ratio pollution vs stamp `fatigue_m`/`taste_m` | **Accept the ratio pollution** (diversity penalty pollutes the joint *downward* = the false-trip direction = conservative; the 0.15 bar has margin). No new per-layer stamps in v1. | §7.3 |
| DE-5 | League-allowlist mechanism (build_map's None seam) | New git-deployed file **`config/negmem_leagues.json`** (JSON array of league_id strings; `"*"` = all leagues) ∪ env `FTF_NEGMEM_LEAGUES` (comma-separated), 60s cache — the `tester_allowlist.json` pattern (`backend/experiments.py:87,120-127`; Render-ignores-envVars precedent says ship via file). Missing/empty ⇒ **no** leagues (flipping the flag alone activates nothing). | §4.1 |

---

## 1. Scope & Reference

### 1.1 What is built

One new leaf module `backend/negmem.py` (D-2; the `suggestion_telemetry.py` leaf precedent —
its header at `backend/suggestion_telemetry.py:12-16` is the model), plus:

- three consultation seams (serving stack / gen_v2 / fit) of ≤ ~10 lines each (D-4, D-10),
- one build + threading block in `server._run_trade_job` (D-3),
- one stamp block in the features assembly (`server.py:4135-4212` region),
- the M2 `acceptance_stats` feed into gen_v2's two call sites
  (`trade_service.py:4001`, `bakeoff_runner.py:1212`),
- 6 `model_config` knobs + 1 feature flag (`trade.negmem`) with full triple registration (R10, D-8),
- readout SQL pack additions + the RFPS frozen-cohort artifact (§7),
- the test plan of §9.

**No new tables** (NG6, D-1). **No new analytics events.** **No new routes.**

### 1.2 What is explicitly not built (guards)

No hard suppression at any seam (NG1); no modification of `acceptance_prior`'s ratified math
(`trade_gen_v2.py:283-308` — the guard lives in the *feed*, NG9); no consumption of unacted
impressions (NG8); no per-shape keys (P2-gated); no UI (NG5); no touching F3/F5/D-067/R4/Thompson
semantics (NG9). Gate ordering unchanged everywhere — the multiplier applies after all gates,
membership is never affected (R4).

### 1.3 Code anchors (verified this checkout)

| Anchor | Where |
|---|---|
| Serving per-member multiplier stack | `trade_service._generate_trades_v2`, member loop `trade_service.py:4943` (`for idx, member in enumerate(eligible):`), multiplier blocks through `:5196`; the `_m != 1.0` skip idiom at `:5125-5127` |
| Config accessor + overlay | `trade_service._c` `:1004-1010`; `_cfg_override` `:994-1001`; `_DEFAULT_CFG` ends `:963` |
| exclusion_keys overwrite-per-call seam | `trade_service.py:3980-3986` |
| Relaxed pass | `trade_service._relaxed_targeted_pass` `:4271-4325` (re-invokes `_generate_trades_v2` under `_cfg_override`) |
| gen_v2 acceptance prior + per-pair loop | `trade_gen_v2.py:283-308` (E-B math, reproduced §5.6); orchestrator kwarg `acceptance_stats` `:862`; per-pair loop `:939-975`, `acceptance_prior` consumed `:951` |
| fit ranker + composite | `trade_gen_fit.py:389-392` (sort key, `-round(c["aggregate_raw"], 9)` quantization), `composite_score` set at `:442` |
| `_generate_kwargs` | `server.py:5644-5671`; bake-off fan-out lambdas `:5679-5685`; organic call `:5696` |
| features assembly | `server.py:4135-4212` (`features = {...}`), row build `:4219-4233`, `base_score` = `card.composite_score` at `:4213` |
| `_deck_fatigue_multipliers` (bulk-read pattern + MIN precedent + fail-open precedent) | `server.py:4482-4541`; fail-open `:4499-4503` |
| `restore_order` | `bakeoff_runner.py:1415-1430`, called `server.py:5766` |
| `snapshot_config` (D-8 mechanism) | `bakeoff_runner.py:423-433` |
| `MODEL_A_PROFILE` | `bakeoff_profiles.py:69-87` |
| `_PINNED_KNOBS` + inventory test | `backend/tests/test_bakeoff_arm_a_golden.py:471-542`, test `:545-559` |
| `_MODEL_CONFIG_DEFAULTS` (tuple shape `(key, value, description)`) | `database.py:2188` |
| `save_deck_impressions` (executemany, first-row-keys trap) | `database.py:5503-5515` |
| Spine tables | `deck_impressions` `database.py:500-608`, `deck_outcomes` `:741-761`, `trade_pass_reasons` `:873-943`, `trade_matches` `:417-436`, `trade_decisions` `:319-337` |
| Identity predicate | `backend/sleeper_roster.py` (`canonical_owner_id`, `co_owner_ids`) — ADR-012 |
| Tester-allowlist precedent | `backend/experiments.py:87, 120-127` + `config/tester_allowlist.json` |

---

## 2. Interfaces — `backend/negmem.py` module skeleton

Leaf discipline (D-2, T1): imports **only** `feature_flags`, `database`, and `sleeper_roster`
(pure identity predicate, no heavier than `pick_values` in the telemetry leaf). Never imports
`server`, `trade_service`, or any engine module. Engines consume it via `import negmem` +
attribute call — **never** `from .negmem import effective_mult` (T1 rule, §5.2 of the HLD;
sabotage-tested §9 T-11). **No module-global map, ever.**

```python
"""negmem.py — negative-results memory (flag `trade.negmem`, default OFF).

M1: per-(league, partner, reason-family) soft down-weight built from reasoned
rejections; M2: the acceptance_stats feed for trade_gen_v2.acceptance_prior.
Derive-on-read, zero tables (NG6). LEAF: imports feature_flags + database +
sleeper_roster only; engines `import negmem` and call attributes (T1) — the
map moves exclusively as an argument (D-3). PRD/HLD:
docs/plans/negative-results-memory/. Admission is the ONE closed list (R1):
the SQL fragment + Python predicate pair below are the only implementation —
builder, readout, and RFPS all call load_admitted_events()."""

NEGMEM_VER = 1                      # stamp schema version; bump on any change
                                    # to admission, decay, or netting semantics
NEGMEM_CLEAN_EPOCH = "2026-08-20T00:00:00"   # R1(e); subsumes D-091 (ends 08-19)
NEGMEM_ADMITTED_FAMILIES = ("value", "fit")  # R2 — closed set
NEGMEM_HORIZON_HALFLIVES = 4.0               # HLD §3.1 read horizon
NEGMEM_BUILD_BUDGET_MS = 250.0               # S6 absolute ceiling (HLD §3.1)
NEGMEM_DEGRADE_MS = 2.0 * NEGMEM_BUILD_BUDGET_MS   # slow-but-valid ⇒ degraded

ALLOWLIST_FILE = ".../config/negmem_leagues.json"   # os.path.join like experiments.py:87

def negmem_league_allowed(league_id: str) -> bool:
    """PRD §8.2 league scoping: True iff league_id ∈ (file ∪ env) allowlist,
    or the allowlist contains "*". 60s cache; unreadable file ⇒ empty (warn)."""

def load_negmem_league_allowlist() -> set[str]:
    """The raw allowlist (env FTF_NEGMEM_LEAGUES ∪ config/negmem_leagues.json).
    Exposed for the readout pack's allowlist-scoped denominators."""

@dataclass
class NegmemCell: ...          # §3.1

@dataclass
class NegmemMap: ...           # §3.2
    # method: m2_feed() -> dict[str, tuple[int, int]]   — §3.2

def build_map(user_id: str, league_id: str, *,
              halflife_days: float, min_evidence: float, sat_k: float,
              like_net: float, floor_b: float,
              accept_prior_strength: float,
              as_of: str | None = None) -> NegmemMap | None:
    """One bulk read → NegmemMap for this job; None iff league not allowlisted
    (the PRD §8.2 None seam — downstream indistinguishable from flag-off).
    NEVER raises: any internal failure returns a degraded identity map."""

def effective_mult(nm_map: "NegmemMap | None", partner_league_id: str, *,
                   strength: float, floor: float) -> float:
    """PURE (D-10): eff = clamp(1 + strength·(mult−1), floor, 1.0). No config
    access, no defaults, no I/O. None/degraded map, unknown partner, or
    strength ≤ 0 ⇒ exactly 1.0."""

def stamp_payload(nm_map: "NegmemMap", partner_league_id: str,
                  eff: float) -> dict:
    """The consult-time stamp the card carries (B2): {m, keys, ev, ver}."""

def load_admitted_events(user_id: str, league_id: str, *, as_of: str,
                         horizon_floor: str) -> list[dict]:
    """R1's closed list, THE one implementation: runs _ADMISSION_SQL, then
    applies admission_predicate row-by-row (retraction join, dedupe,
    partner canonicalization, context tags). Consumed by build_map,
    negmem_readout, and the RFPS artifact generator — nobody re-implements."""

def load_like_events(user_id: str, league_id: str, *, as_of: str,
                     horizon_floor: str) -> list[dict]:
    """§5.3 netting inputs: viewed, non-ghost, clean-epoch, un-undone,
    un-retracted likes toward each partner (no reason join — likes carry none)."""

def admission_predicate(row: dict, *, as_of: str) -> bool:
    """The Python half of the pair: full R1(a)-(e) closed list evaluated on a
    joined row dict (includes the clauses the SQL fragment already enforced —
    that redundancy is what the parity test T-1 pins)."""

_ADMISSION_SQL: str      # the SQL WHERE fragment (§5.1) — module constant

def negmem_readout(user_id: str, league_id: str, as_of: str | None = None,
                   knobs: dict | None = None) -> dict:
    """R8 operator dump (§7.1 format). Same builder. knobs=None ⇒ read
    database.get_config() (leaf-legal, database.py:4153); a missing knob key
    raises KeyError('negmem seed rows missing — run init_db') — negmem holds
    no default literals (DE-3)."""

# internal: _load_acceptance_rows (M2 aggregation SQL §5.5),
#           _fold_events (§4.3/§4.5), _cell_mult (§4.4),
#           _alias_map(league_id) (ADR-012 canonicalization §5.4)
```

### 2.1 Threading interface changes (exact signatures)

| Site | Change |
|---|---|
| `server._run_trade_job` | build `nm_map` once per job after the flag check, before the fan-out (§6.1); add `negmem = nm_map` to `_generate_kwargs` (`server.py:5669` — after `exclusion_keys`); pass `nm_map` into `_log_deck_signal_impressions` |
| `TradeService.generate_trades` / `_generate_trades_impl` (`trade_service.py:3899`) | new kwarg `negmem: "negmem.NegmemMap | None" = None`, documented alongside `exclusion_keys` (`:3951-3956`); stored overwrite-per-call `self._negmem = negmem` in the `:3983` state block (None ⇒ None, never keep-previous); **read once into a local** `_nm = self._negmem` immediately after (H-4) and threaded from the local |
| `TradeService._generate_trades_v2` (`:4747`) | new kwarg `negmem_map=None`; `_generate_trades_impl` passes `negmem_map=_nm` in the direct call **and** inside the `v2_kwargs` dict handed to `_relaxed_targeted_pass` (`:4271`) — the relaxed pass then reuses the identical map with zero special-casing (HLD §3.5) |
| `trade_gen_v2.generate_league_suggestions` (`:844`) | new kwarg `negmem_map=None` (beside `acceptance_stats` `:862`) |
| `trade_gen_fit.generate_league_suggestions` (`:237`) | new kwarg `negmem_map=None` |
| `bakeoff_runner.gen_v2_cards` (`:1317` region, call at `:1212`) | forward `kwargs.get("negmem")` as `negmem_map` + the M2 feed (§6.3) |
| `bakeoff_runner.gen_fit_cards` (`:1317`) | forward `kwargs.get("negmem")` as `negmem_map` |

Arms A/B need no forwarding code: the fan-out lambdas splat `**_generate_kwargs`
(`server.py:5680-5681`), so `negmem=` arrives at `generate_trades` unchanged.

---

## 3. Data Structures

### 3.1 `NegmemCell`

```python
@dataclass
class NegmemCell:
    n_raw: int          # admitted rejection events in the horizon (pre-decay, pre-net)
    n_decayed: float    # decayed, like-netted evidence mass at as_of; ≥ 0.0 always
    likes_net: float    # decayed like mass subtracted (readout transparency)
    mult: float         # base multiplier from §4.4; ∈ [floor_b, 1.0]; 1.0 below min_evidence
    floored: bool       # True when the §4.4 curve was clamped at floor_b
```

Nullability: none — every field always set. Cells exist for every
`(partner_league_id, family)` with ≥1 admitted rejection **or** ≥1 netting like in the horizon
(identity cells kept: the readout and the RFPS numerator rule both need sub-threshold state).

### 3.2 `NegmemMap`

```python
@dataclass
class NegmemMap:
    user_id: str
    league_id: str
    as_of: str                                   # ISO UTC, build time or caller's as_of
    ver: int                                     # = NEGMEM_VER
    cells: dict[tuple[str, str], NegmemCell]     # key: (partner_league_id, family);
                                                 # family ∈ NEGMEM_ADMITTED_FAMILIES
    partner_mult: dict[str, float]               # collapsed per-partner base mult (DE-1 MIN);
                                                 # only partners with any cell; absent ⇒ 1.0
    acceptance_stats: dict[str, tuple[int, int]] # M2: partner → (accepts, responses);
                                                 # NOTE tuple order follows CODE
                                                 # (trade_gen_v2.py:305 unpacks
                                                 # `accepts, responses`) — the HLD §2.1
                                                 # comment has it flipped; code wins (§10 OQ-1).
                                                 # {} when accept_prior_strength ≤ 0 (feed guard,
                                                 # HLD §3.5) — never emitted with 0-response keys.
    degraded: bool                               # build exception OR build_ms > NEGMEM_DEGRADE_MS
    build_ms: float

    def m2_feed(self) -> dict[str, tuple[int, int]]:
        """{} when degraded, else acceptance_stats — the ONE degraded-⇒-{} rule
        (HLD §3.5); both gen_v2 call sites go through this, never the field."""
```

All partner keys are **league identities** (R9): the `_league_user_id` contract — global platform
ids from the spine are canonicalized through `sleeper_roster.canonical_owner_id` (§5.4) before
they become keys. Account ids never enter the map.

### 3.3 Stamp payload (`features_json.negmem`) — schema + size

Written inside `features_json` (the always-present Text column — first-row-keys-proof, HLD §3.4;
same argument as the fit/fit_diag precedent at `server.py:4197-4204`).

| Variant | Payload | ~bytes |
|---|---|---|
| Influenced | `{"m": 0.8123, "keys": ["value","fit"], "ev": {"value": 4.25, "fit": 3.1}, "ver": 1}` | 70–85 |
| Uninfluenced | `{"m": 1.0, "ver": 1}` | 18 |
| Likes-you exempt | `{"m": 1.0, "ver": 1, "exempt": true}` | 32 |
| Degraded | `{"m": 1.0, "ver": 1, "degraded": true}` | 34 |

- `m`: the effective multiplier actually applied (4 dp), = `eff` from `effective_mult`.
- `keys`: the admitted families whose cells were non-identity for this partner (the cells that
  *drove* `partner_mult` — i.e. `mult < 1.0`), sorted.
- `ev`: `{family: round(n_decayed, 2)}` for those keys.
- `ver`: `NEGMEM_VER`.

Partner is deliberately **not** repeated (it is already `features.partner_user_id`). Expected
storage residue at 100% stamp-rate ≈ 20–85 B/row — inside the HLD's accepted ~60 B/row budget.
`stamp_payload()` is the only producer; the features assembly **copies**, never builds (B2).

### 3.4 Knob table (R10 — full triple registration)

| Key | Default | Role | Read at |
|---|---|---|---|
| `negmem_strength` | 1.0 | M1 lever; `0` = byte-identical M1 disable (deck content/scores/order; stamps follow the trichotomy — HLD §5.1). **M1-ONLY** (round-3 decision): does not govern M2. | seam, via `_c` inside the arm's overlay (D-6/D-10) |
| `negmem_floor` | 0.6 | clamp floor for `eff`; ALSO the build-time curve asymptote `floor_b` (§4.4 — double role documented there) | seam via `_c` (clamp); build pass-in (asymptote) |
| `negmem_min_evidence` | 3.0 | shrinkage threshold — cells with `n_decayed <` this are identity | build pass-in |
| `negmem_halflife_days` | 45.0 | exponential decay half-life; also sets the read horizon (×4) | build pass-in |
| `negmem_sat_k` | 3.0 | **(new this LLD)** saturation pseudo-count of the §4.4 curve | build pass-in |
| `negmem_like_net` | 1.0 | **(new this LLD)** evidence mass one admitted viewed like nets against every (P, ✱) cell (DE-2) | build pass-in |

M2's strength is governed by the EXISTING seeded `gen2_accept_prior_strength` /
`gen2_accept_global_prior` (`trade_service.py:660-661`; already in `_PINNED_KNOBS`
`test_bakeoff_arm_a_golden.py:501`); its deploy-free kill is `gen2_accept_prior_strength = 0`,
made structural by the feed guard (§5.5). **Kill M2 via the GLOBAL knob only, never an arm
overlay pin** (HLD §5.3; runbook line §8.4).

Registration rows, all six keys, same commit:

1. **`trade_service._DEFAULT_CFG`** (append after the fit-challenger block, `:963`) — with a
   comment block naming the flag and this folder. Required for D-8: `snapshot_config()` iterates
   `_DEFAULT_CFG` (`bakeoff_runner.py:432-433`), so registration alone yields per-arm
   `config_json` coverage including arm A's strength-0 delta.
2. **`database._MODEL_CONFIG_DEFAULTS`** (`:2188` list; `(key, value, description)` tuples) seed
   rows:

```python
("negmem_strength",       1.0,  "negmem M1 strength; 0 = byte-identical M1 disable (M1-only — M2 is governed by gen2_accept_prior_strength)"),
("negmem_floor",          0.6,  "negmem clamp floor for the effective multiplier; also the evidence-curve asymptote"),
("negmem_min_evidence",   3.0,  "negmem shrinkage threshold: cells with decayed evidence below this are identity"),
("negmem_halflife_days", 45.0,  "negmem evidence exponential-decay half-life (days); read horizon = 4x this"),
("negmem_sat_k",          3.0,  "negmem evidence-curve saturation pseudo-count (mult = 1 - (1-floor)*n_eff/(n_eff+k))"),
("negmem_like_net",       1.0,  "negmem: evidence mass one admitted viewed like nets against every (partner, *) cell"),
```

3. **`_PINNED_KNOBS`** (`test_bakeoff_arm_a_golden.py:471`): add all six names.
4. **Arm-A disposition sentences** (verbatim, for `docs/plans/three-model-bakeoff/scope-phase2.md`
   § Scope and the `_PINNED_KNOBS` comment):
   - `negmem_strength`: *"Pinned in MODEL_A_PROFILE at 0.0 — negmem post-dates
     MODEL_A_REFERENCE_SHA and its seam multiplies composite_score inside generation; 0.0 is the
     documented byte-identical M1 disable, so the pin preserves the pre-wave engine exactly
     (golden re-run and verified unchanged after the pin)."*
   - `negmem_floor`, `negmem_min_evidence`, `negmem_halflife_days`, `negmem_sat_k`,
     `negmem_like_net`: *"Excluded from MODEL_A_PROFILE — inert to arm A by construction: with
     negmem_strength pinned at 0.0, negmem.effective_mult returns exactly 1.0 before any of these
     is consulted (they shape the map, not the gate), so pinning a kill value would falsely
     assert they reach an arm-A deck; they provably do not."*
5. **`MODEL_A_PROFILE`** (`bakeoff_profiles.py:69`): add `"negmem_strength": 0.0` with the D-6
   comment. Golden re-run required by that file's edit rule; expected byte-identical (C1) —
   §9 T-5 makes that an assertion, not a hope.

### 3.5 Flag registration

`trade.negmem` — dark ship, default OFF everywhere:

| Surface | Row |
|---|---|
| `feature_flags.FLAG_KEYS` (`feature_flags.py:47`) | `"trade.negmem",` (attr `FLAGS.trade_negmem` via `_key_to_attr` — never hand-mapped) |
| `feature_flags.DEFAULT_FLAGS` (`:939`) | automatic (`{key: False for key in FLAG_KEYS}`) — nothing to write |
| `config/features.json` | `"trade.negmem": false` (+ a `_comment_trade_negmem` line naming this folder) |
| `backend/tests/fixtures/flags/release.json` | regenerate mirror — `test_seed_ui_test_db.test_release_flags_mirror_features_json` enforces |

Flag flips (and knob moves) land **only at bake-off round boundaries** (GR3; runbook §8.4).

---

## 4. Core Logic

### 4.1 Allowlist gate (DE-5) and the None seam

`negmem_league_allowed(league_id)`: allowlist = `set(env FTF_NEGMEM_LEAGUES.split(","))` ∪
`json.load(config/negmem_leagues.json)` (array of strings), cached 60s (the
`experiments._load_cache` idiom). `"*"` anywhere ⇒ every league allowed. Missing file, empty
list, parse error ⇒ empty set (log a warning once per cache period on error). **Empty ⇒
`build_map` returns None** for every league: flag-on with an unpopulated allowlist is inert by
construction, and global rollout is the one-line diff `["*"]`.

`build_map` calls this first and returns `None` when not allowed — no map, no kwarg effect
downstream, **no stamps** (the trichotomy's ON-condition is flag ∧ allowlisted, HLD §3.4), and
the stamp-rate tripwire's denominator is scoped by `load_negmem_league_allowlist()` (§7.2), so a
partial rollout never reads as build failures.

### 4.2 Build-time knob read path (DE-3)

`_run_trade_job` reads, on the job thread, **before** any arm context is entered (so reads are
global-config, which is correct: build-time knobs are deliberately overlay-blind, HLD §2.1 note —
arm A's opt-out is strength-only):

```python
# server.py, immediately before _generate_kwargs (:5644) —
from .trade_service import _c as _ts_c       # module-scope import at top of server.py
from . import negmem as _negmem

nm_map = None
if FLAGS.trade_negmem:
    try:
        nm_map = _negmem.build_map(
            g_user_id, league_id,
            halflife_days         = _ts_c("negmem_halflife_days"),
            min_evidence          = _ts_c("negmem_min_evidence"),
            sat_k                 = _ts_c("negmem_sat_k"),
            like_net              = _ts_c("negmem_like_net"),
            floor_b               = _ts_c("negmem_floor"),
            accept_prior_strength = _ts_c("gen2_accept_prior_strength"),
        )
    except Exception as nm_err:               # belt — build_map already never raises
        log.warning("negmem build failed hard (no stamps this job): %s", nm_err)
        nm_map = None
    if nm_map is not None:
        with _trade_jobs_lock:                # the suppression_note pattern (:5811-5814)
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["negmem_note"] = {"degraded": nm_map.degraded,
                                    "build_ms": round(nm_map.build_ms, 1)}
```

Why pass-in wins (HLD §7 tilt, confirmed): `gen2_accept_prior_strength`'s seeded default lives in
`_DEFAULT_CFG` (`trade_service.py:660`) and negmem is a leaf that cannot import it — a
direct-read would force negmem to duplicate the default (stale-copy drift). Uniformly passing
ALL build knobs keeps negmem literal-free; the only DB config read in the module is
`negmem_readout(knobs=None)`'s `database.get_config()` convenience, which reads the *seeded
table*, not a copied literal (missing key ⇒ KeyError, §2). The general two-read-paths drift
surface is thereby collapsed to one path for serving and one **seeded-table** path for offline
tooling.

### 4.3 Decay — formula and worked example

Exponential half-life decay, folded event-by-event (numerically identical to per-event
`0.5^(Δdays/halflife)` weighting, but a single chronological fold is what makes the netting
clamp (§4.5) well-defined):

```
acc ← max(0.0, acc · 0.5^((t_i − t_{i−1})/H) + w_i)      # w = +1 rejection, −like_net like
n_decayed = acc · 0.5^((as_of − t_last)/H)
```

with `H = negmem_halflife_days` in days (timestamps parsed as ISO UTC; sub-day resolution kept).

**Worked example (no likes)** — H=45, as_of = day 90, rejections at day 0, 0, 45, 80:
day 0: acc=2.0 → day 45: 2·0.5^1 + 1 = 2.0 → day 80: 2·0.5^(35/45) + 1 = 2·0.583 + 1 = 2.166
→ as_of: 2.166·0.5^(10/45) = 2.166·0.857 = **1.857**. n_raw = 4.

### 4.4 Shrinkage + the cell multiplier + the DE-1 combine rule

```
n_eff = n_decayed − min_evidence + 1
mult  = 1.0                                          if n_decayed < min_evidence
      = 1 − (1 − floor_b) · n_eff / (n_eff + sat_k)  otherwise
```

Saturating E-B-flavored curve: identity below the shrinkage threshold (R3), first effect exactly
at threshold, asymptote `floor_b`, never below it and never above 1.0 by construction (`floored`
is set when `mult` lands within 1e-9 of `floor_b` — with this curve only asymptotically, so it
records knob-driven extremes). **Double role of `negmem_floor`, documented:** the same knob is
the curve asymptote at build (global read) and the clamp floor at consult (seam `_c` read, so an
arm overlay of `negmem_floor` moves the clamp but not the curve — accepted, since the only
sanctioned arm pin is `negmem_strength` per D-6).

**Worked examples** (floor_b=0.6, min_evidence=3, sat_k=3):

| n_decayed | n_eff | mult |
|---:|---:|---:|
| 2.9 | — | 1.000 (identity) |
| 3.0 | 1.0 | 1 − 0.4·(1/4) = **0.900** |
| 5.0 | 3.0 | 1 − 0.4·(3/6) = **0.800** |
| 9.0 | 7.0 | 1 − 0.4·(7/10) = **0.720** |
| ∞ | ∞ | → 0.600 |

**DE-1 — combine rule across a partner's family cells: MIN, not product.**
`partner_mult[P] = min(cells[(P, f)].mult for f in admitted families present)` (missing cell = 1.0).

Why (3-row fixture table, committed as the T-3 fixture):

| Row | (P, value).mult | (P, fit).mult | MIN | product | Verdict |
|---|---:|---:|---:|---:|---|
| value-only evidence | 0.80 | 1.00 | **0.80** | 0.80 | identical — no cost |
| two barely-admitted objections | 0.90 | 0.90 | **0.90** | 0.81 | product punishes 3+3 passes across *different* objections as hard as ~6 same-family passes — it compounds exactly the over-reach D-5 already concedes in the per-partner collapse (HLD §6 Residual) |
| one strong + one weak | 0.70 | 0.90 | **0.70** | 0.63 | product drives toward floor² pre-clamp; GR4 exists because soft layers must not compound into de-facto exclusion — negmem must not do internally what GR4 polices externally |

House precedent seals it: F3 fatigue takes the MIN of its keys — *"never a product — one
impression must not be triple-counted"* (`server.py:4494-4496`). The same event never
double-counts here either: one rejection has one family, but one *partner* has two families, and
MIN reads as "the strongest single standing objection governs." C2's clamp invariant holds under
either rule (the clamp is in `effective_mult`); MIN is chosen on semantics, not safety.

### 4.5 Netting (DE-2) — decrement, chronological fold, clamp-at-zero

- **Mechanism: DECREMENT** (not reset). Reset would let one like erase a long, consistent,
  decayed record in one step — over-correcting a lock-in problem that decay + soft floor +
  min-evidence already bound (PRD §5.3, §7 risk table), and making the map non-smooth in a way
  the readout can't explain. A decrement of `negmem_like_net = 1.0` is symmetric ("one viewed
  like cancels one viewed reasoned pass") and knob-tunable.
- **Target: every (P, ✱) cell** (PRD §5.3 — a like carries no reason code, so it cannot target
  one family). The same like event (weight `−like_net` at its `acted_at`) is folded into **each**
  admitted-family stream of partner P independently.
- **Bounds:** the fold of §4.3 applies `max(0.0, …)` after **every** step, in timestamp order —
  so a cell can never go negative, and a like that precedes any evidence nets nothing and cannot
  bank credit against future rejections (the clamp is why netting must be event-folded in the
  as-of domain — D-7 — rather than subtracted at the end).
- **Like admission** (mirror of R1 minus the reason clauses): action `like`, viewed-gated,
  non-ghost, clean-epoch, inside the horizon, no later `undo` on the impression, and the paired
  `trade_decisions` row (if matched, §5.3) has `retracted_at IS NULL` — likes are exactly where
  `retracted_at` fires in practice (awaiting-dismiss), so the dual check does real work here.
- Readout transparency: `likes_net` on the cell (§3.1) + a `likes` count per partner in the
  readout (PRD §5.3 "the mechanism is stamped in the readout").

**Worked example** — H=45, min_evidence=3, like_net=1.0; partner P, family `value`:
passes day 0, 0, 10; like day 20; as_of day 30.
day 0: acc=2.0 → day 10: 2·0.5^(10/45)+1 = 2.714 → day 20 (like): 2.714·0.857 − 1.0 = 1.326
→ as_of: 1.326·0.857 = **1.137** ⇒ below min_evidence ⇒ identity. Without the like: 1.994 —
still identity; a fourth pass would have crossed the threshold, which the like now delays. The
like also nets the (P, fit) cell (empty here: fold of a lone −1.0 clamps to 0, cell records
likes_net only).

### 4.6 `effective_mult` (D-10 — the ONE implementation)

```python
def effective_mult(nm_map, partner_league_id, *, strength, floor) -> float:
    if nm_map is None or nm_map.degraded:      # degraded ⇒ identity, even slow-but-valid
        return 1.0
    if strength <= 0.0:
        return 1.0                             # structural short-circuit (D-6)
    mult = nm_map.partner_mult.get(partner_league_id, 1.0)
    if mult >= 1.0:
        return 1.0
    return min(1.0, max(floor, 1.0 + strength * (mult - 1.0)))
```

Exactly the HLD D-6 formula `eff = clamp(1 + strength·(mult−1), floor, 1.0)` — verified against
the HLD wording (§2.1, D-10). Pure: no config, no defaults, no I/O. Sink-never-rise is
structural (`mult ≤ 1` and the `min(1.0, …)`); C2's invariants are tested against this single
function (§9 T-4) and each seam contributes only the `_c` reads + the `eff != 1.0` skip.
Worked: mult 0.8 → strength 0.5 ⇒ 0.9; strength 1 ⇒ 0.8; strength 2 ⇒ clamp(0.6) = 0.6;
strength 0 ⇒ 1.0 exactly (no float artifact — short-circuited).

### 4.7 Read horizon

`horizon_floor = max(NEGMEM_CLEAN_EPOCH, as_of − 4·halflife_days)` — applied **in-query**
(`o.acted_at >= :horizon_floor` / like-side same). At default H=45 the window caps at 180d;
evidence older than four half-lives contributes < 6.25% of an event — below the shrinkage
floor's resolution (HLD §3.1). The M2 aggregation carries its own in-query 180d lookback (R5),
independent of H.

---

## 5. SQL & joins (exact)

### 5.1 The admission pair — SQL fragment

Executed on `database.engine` (leaf-legal). JSON extraction is deliberately **absent** from SQL:
`features_json` is selected whole and parsed by the Python predicate — this dodges the
SQLite-vs-Postgres JSON-operator split entirely, and the reason-join bounds the row count to the
reason-row volume (~120/wk × 26wk cap ≈ ~3k rows — trivially parseable inside the S6 budget).

```sql
-- negmem._ADMISSION_SQL (module constant; named params:
--   :user_id :league_id :as_of :horizon_floor :clean_epoch)
SELECT o.id            AS outcome_id,
       o.impression_id AS impression_id,
       o.action        AS action,
       o.acted_at      AS acted_at,
       i.served_at     AS served_at,
       i.features_json AS features_json,     -- partner/lane/user_value_basis parsed in Python
       i.assets_json   AS assets_json,       -- R1(d) retraction join key material
       i.shape_bucket  AS shape_bucket,      -- recorded on evidence rows (§2.2 PRD)
       i.trade_intent  AS trade_intent,      -- R11 context tag (COLUMN, not features key)
       r.reason        AS family,
       r.detail        AS detail
  FROM deck_outcomes o
  JOIN deck_impressions   i ON i.impression_id = o.impression_id
  JOIN trade_pass_reasons r ON r.impression_id = o.impression_id
 WHERE i.user_id   = :user_id
   AND i.league_id = :league_id
   AND o.action IN ('pass', 'not_interested')                    -- R1 event class
   AND o.acted_at <= :as_of
   AND o.acted_at >= :horizon_floor                              -- §4.7, in-query
   AND EXISTS (SELECT 1 FROM deck_outcomes v                     -- R1(a) viewed-gated (F1)
                WHERE v.impression_id = o.impression_id
                  AND v.action = 'viewed' AND v.acted_at <= :as_of)
   AND r.key_source = 'impression'                               -- R1(b) spine-joined reason
   AND r.reason IN ('value', 'fit')                              -- R2 admitted families
   AND COALESCE(i.is_ghost, 0) != 1                              -- R1(c) not a ghost
   AND NOT EXISTS (SELECT 1 FROM deck_outcomes u                 -- R1(d) undo half
                    WHERE u.impression_id = o.impression_id
                      AND u.action = 'undo'
                      AND u.acted_at > o.acted_at
                      AND u.acted_at <= :as_of)
   AND i.served_at >= :clean_epoch                               -- R1(e); subsumes D-091
 ORDER BY o.acted_at
```

Unknown future layer-2 `detail` codes need no handling here: `r.reason` IS the layer-1 family
(`database.py:894-902`), so R2's "unknown codes map to their layer-1 family" is satisfied by
construction, and a non-admitted family fails the `IN ('value','fit')` clause.

### 5.2 The admission pair — Python predicate

`admission_predicate(row, *, as_of)` re-evaluates the FULL closed list on a joined row dict
(action class, viewed flag, key_source, family, ghost, undo, epoch, horizon, as_of) — the SQL
and predicate deliberately overlap so T-1 can prove them equivalent on a fixture matrix — and
additionally owns the clauses SQL cannot express:

1. **R1(d) retraction half** — §5.3's `trade_decisions` join; drop when the matched decision has
   `retracted_at IS NOT NULL`.
2. **Per-impression dedupe** — append-only `deck_outcomes` permits duplicate labels
   (`database.py:5525-5532` docstring): the FIRST admitted pass/not_interested per
   `impression_id` is the evidence event; later duplicates are ignored.
3. **Partner extraction + canonicalization** — `features_json.partner_user_id` (global platform
   id, memo §2e) → league identity via §5.4.
4. **Context tags (R11, recorded-not-consulted)** — `lane`, `user_value_basis` from
   `features_json`; `trade_intent` from the COLUMN (NULL-expected per R11; the readout annotates,
   never errors). A `value` family row with `user_value_basis == 'personal'` gets
   `context_tags["basis_note"] = "board-fit"` (R2/taxonomy §2.6) — a tag, not a family change.

Yield per admitted event:
`(league_id, user_id, partner_league_id, reason_family, shape_bucket, context_tags, ts=acted_at)` —
the PRD R1 in-memory evidence row, derived on read, never stored.

### 5.3 R1(d) — the `deck_outcomes` ↔ `trade_decisions` join (asymmetric retraction)

The two tables share no key (PRD R1(d) note). Join rule (Python, one batch load per build):

- Load `trade_decisions` rows for (user, league) with `created_at >= horizon_floor`.
- Key each by `(decision, frozenset(give_player_ids), frozenset(receive_player_ids))`.
- For an outcome event, parse `i.assets_json` (`{"give": [...], "receive": [...]}` —
  `server.py:4245`; present on every clean-epoch row: the telemetry columns predate the epoch,
  PRD §7 boundary (a)) and probe with `decision='pass'` for pass/not_interested events (the UI's
  dismiss IS `decision='pass'`, memo §1.1), `decision='like'` for netting likes.
- Among key-matches, pick the row with the smallest `|created_at − acted_at|`; accept only if
  ≤ **600s** (both writes come from the same request — swipe route `server.py:11662` — so real
  pairs land within seconds; 600s absorbs clock skew and retries).
- **Asymmetry, stated (PRD R1(d))**: `retracted_at` is set in practice only on like-side rows
  (awaiting-dismiss, `database.py:328-336`); the pass-side retraction signal is the paired
  `undo` outcome, which §5.1 already excludes in SQL. Therefore: **no decision-row match for a
  pass event ⇒ admit** (the check passes vacuously — there is no pass-side retraction state to
  miss); no match for a like event ⇒ the like still nets (its own undo check already ran).
  Matched row with `retracted_at NOT NULL` ⇒ drop the event (pass or like).

### 5.4 Identity canonicalization (ADR-012 call sites — HLD §7)

`_alias_map(league_id)`: one read of `league_members` rows (`database.py:340-349`) for the
league; for each roster, `sleeper_roster.co_owner_ids(roster_data)` → map every co-owner alias
id → the roster's canonical `owner_id`. Applied at exactly three places (the ONLY id-touching
sites in the module):

1. evidence/netting partner ids (§5.2 step 3),
2. M2 aggregation partner keys (§5.5) — plus a drop-with-counter for ids that map to no league
   member (the memo's id-space check: `trade_matches.user_a/b_id` vs league member space),
3. the readout/RFPS SQL documentation of the mapping (R9; §7).

The requesting user's own id is canonicalized the same way before the `partner != user` guard.

### 5.5 M2 aggregation (R5) — exact SQL + feed guard

Runs inside `build_map` (D-9: one build, one as_of, one S6 envelope). **Guard first**: if
`accept_prior_strength <= 0` ⇒ `acceptance_stats = {}` — the E-B pseudo-count `m` in the memo
§2f formula IS that knob, and the guard lives in the FEED, never inside the ratified
`acceptance_prior` math (NG9, HLD §3.5).

```sql
-- negmem._ACCEPTANCE_SQL (params :league_id :lookback_floor :as_of)
SELECT partner,
       SUM(is_accept)  AS accepts,
       COUNT(*)        AS responses          -- accepts + declines = responses (R5)
  FROM (
    SELECT m.user_b_id AS partner,
           CASE WHEN m.user_b_decision = 'accept' THEN 1 ELSE 0 END AS is_accept,
           COALESCE(m.user_b_decided_at, m.matched_at) AS ts
      FROM trade_matches m
     WHERE m.league_id = :league_id AND m.user_b_decision IS NOT NULL
    UNION ALL
    SELECT m.user_a_id,
           CASE WHEN m.user_a_decision = 'accept' THEN 1 ELSE 0 END,
           COALESCE(m.user_a_decided_at, m.matched_at)
      FROM trade_matches m
     WHERE m.league_id = :league_id AND m.user_a_decision IS NOT NULL
  ) t
 WHERE t.ts >= :lookback_floor AND t.ts <= :as_of
 GROUP BY partner
 HAVING COUNT(*) > 0
```

- `:lookback_floor = as_of − 180d` (R5 default; **in-query**, the formula untouched).
- Zero-response keys are structurally impossible (`decision IS NOT NULL` + `HAVING`) — at n=0 a
  partner is simply absent and `acceptance_prior` returns exactly `p0`
  (`trade_gen_v2.py:303-304`). The empty-table case returns `{}` ⇒ uniform `p0` (C4's explicit
  empty case; S4 expected-null).
- Post-SQL (Python): canonicalize partner ids (§5.4), drop non-members with a counter, drop the
  requesting user, then `{partner: (int(accepts), int(responses))}` — **tuple order
  (accepts, responses), per code** (`trade_gen_v2.py:305`; see §10 OQ-1 re the HLD comment).
- Retractions/dismissals: deliberately untouched — `user_*_dismissed` is inbox-archive only
  (memo §2c) and a decided decision row is the response record; nothing here re-litigates it.

### 5.6 The ratified E-B math (REPRODUCED from memo §2f — not modified)

```python
p = (accepts + m·p0) / (responses + m)   # m = gen2_accept_prior_strength (10.0)
                                         # p0 = gen2_accept_global_prior (0.5)
```

`acceptance_prior` (`trade_gen_v2.py:283-308`) is not edited in any way. C4 parity (§9 T-13)
pins feed × function against hand-computed values at both call sites, including empty-table.

### 5.7 The bulk read, assembled (S6)

`build_map` issues, in order, on one connection: (1) `_ADMISSION_SQL`, (2) the like-events query
(§4.5 admission — same joins minus `trade_pass_reasons`), (3) the `trade_decisions` batch (§5.3),
(4) `league_members` for the alias map (§5.4), (5) `_ACCEPTANCE_SQL`. All league-scoped and
index-served (`ix_deck_outcomes_impression` join path; `ix_trade_matches_user_*_league`
`database.py:443-452`). Budget: p95 ≤ 2× the fatigue read's measured p95, absolute ceiling
250ms (`NEGMEM_BUILD_BUDGET_MS`); `build_ms` is wall-clock around all five reads + the fold, and
`build_ms > 500ms` (`NEGMEM_DEGRADE_MS`) marks the map degraded even when valid (HLD §7
degraded-behavior rule: discarded by design — §4.6 returns 1.0, `m2_feed()` returns `{}`).
The `negmem build_ms=` log line is the S6 timing source. Tighten-only: the LLD may lower these
numbers after measurement, never raise them silently (HLD §3.1).

---

## 6. Seam diffs (insertion points + pseudodiffs)

### 6.1 Server: build + threading (D-3)

Insertion: `server.py:5644` (immediately before `_generate_kwargs`); the build block is §4.2
verbatim. Then:

```diff
         _generate_kwargs = dict(
             ...
             bypass_need_gate     = bypass_need_gate,
             exclusion_keys       = exclusion_keys,
+            negmem               = nm_map,        # trade.negmem (D-3) — one map per job,
+                                                  # never rebuilt mid-job (H-3); None ⇒ identity
             **gen_kwargs,
         )
```

Both fan-out lambdas (`:5680-5685`) and the organic call (`:5696`) inherit it via the splat —
**one map, all arms** (H-3). `_log_deck_signal_impressions` gains a `nm_map=` parameter (§6.5).

### 6.2 TradeService: storage + serving-stack seam

`_generate_trades_impl` state block (`:3980-3986`):

```diff
         self._exclusion_keys = set(exclusion_keys) if exclusion_keys else set()
+        # trade.negmem (D-3): overwrite-per-call like _exclusion_keys; then READ
+        # ONCE INTO A LOCAL (H-4) — a concurrent same-session job overwriting the
+        # slot mid-generation must not produce a mixed-map deck.
+        self._negmem = negmem
+        _nm = self._negmem
         self._job_seed_elo = seed_elo or {}
```

`_nm` is passed to `_generate_trades_v2(negmem_map=_nm, ...)` and rides `v2_kwargs` into
`_relaxed_targeted_pass` (`:4271`) — the relaxed re-run consults the same map at the same
`_c`-read strength, no special case (HLD §3.5). A soft multiplier cannot trigger the
`not cards` relaxed rerun (NG1 structural — the seam never changes membership).

Seam, inside the per-member loop of `_generate_trades_v2` — insert after the aggression block
(`:5196`), i.e. LAST in the per-member multiplier stack, before the `match_ctx` stamping
(`:5197`), covering v2-pair, v3, and consensus-fallback cards uniformly (they all flow through
this loop):

```diff
+            # trade.negmem (D-4/D-10) — partner-constant soft prior, AFTER all
+            # gates: reorders acceptable trades, never rescues or removes one.
+            # Seam owns the eff != 1.0 skip (C1: no multiply, no round at identity).
+            if _nm is not None:
+                _eff = negmem.effective_mult(_nm, member.user_id,
+                                             strength=_c("negmem_strength"),
+                                             floor=_c("negmem_floor"))
+                if _eff != 1.0:
+                    _stamp = negmem.stamp_payload(_nm, member.user_id, _eff)
+                    for c in cards:
+                        c.negmem_stamp = _stamp               # B2: consult-time, rides the card
+                        c.composite_score = round(c.composite_score * _eff, 3)
```

(`import negmem` at trade_service module top — module import + attribute call, T1. The 3-dp
round matches every neighbor in this stack, e.g. `:5127`.) `member.user_id` here is the league
member's canonical owner id — the same space the map keys (§5.4).

### 6.3 gen_v2 seam + M2 feed

`generate_league_suggestions` per-pair loop (`trade_gen_v2.py:951`):

```diff
         prior = acceptance_prior(member.user_id, acceptance_stats)
         weight = max(priority_weights.get(member.user_id, 1.0), 0.0)
+        # trade.negmem (D-4) — pair-constant M1 multiplier; distinct from the
+        # acceptance prior above (different math, same map — HLD §2.2).
+        _nm_eff, _nm_stamp = 1.0, None
+        if negmem_map is not None:
+            _nm_eff = negmem.effective_mult(negmem_map, member.user_id,
+                                            strength=_c("negmem_strength"),
+                                            floor=_c("negmem_floor"))
+            if _nm_eff != 1.0:
+                _nm_stamp = negmem.stamp_payload(negmem_map, member.user_id, _nm_eff)
```

…and at the pair's card build inside the same loop (where each `_Candidate` becomes a
`TradeCard`, `:999` ff.):

```diff
+            if _nm_stamp is not None:
+                card.negmem_stamp = _nm_stamp
+                card.composite_score = round(card.composite_score * _nm_eff, 4)
```

Placement rationale: the multiplier lands on the emitted card's composite, **after**
`_pair_survivors`' within-pair selection and after the pair-pool trims — a pair-constant
multiplier cannot change within-pair selection anyway, and applying at card creation keeps
`_Candidate.score`, the exposure/dedup machinery, and the MESO layer byte-identical (membership
untouched, R4). Rounding matches the module's card-build precision (verify at implementation;
4 dp is this family's norm, `trade_gen_fit.py:442`).

**M2 feed — both call sites** (the kwarg is added ONLY when a map exists; flag-off calls are
byte-identical, C1):

`trade_service.py:4001` (flag-on branch):

```diff
             cards, _gen2_report = generate_league_suggestions(
                 ...
                 past_decision_keys=(...),
+                negmem_map=_nm,
+                **({"acceptance_stats": _nm.m2_feed()} if _nm is not None else {}),
                 on_opponent_done=on_opponent_done,
             )
```

`bakeoff_runner.gen_v2_cards` (`:1212`):

```diff
+    _nm = kwargs.get("negmem")
     with stud_tax_override(mode):
         cards, _report = generate_league_suggestions(
             ...
             past_decision_keys   = past_keys,
+            negmem_map           = _nm,
+            **({"acceptance_stats": _nm.m2_feed()} if _nm is not None else {}),
             on_opponent_done     = kwargs.get("on_opponent_done"),
         )
```

`m2_feed()` (§3.2) returns `{}` when degraded; the aggregation already returned `{}` when
`gen2_accept_prior_strength ≤ 0` (§5.5) — so "degraded ⇒ identity" covers M2 and the
strength-0 kill is structural, per HLD §3.5. Arm A never reaches this code (it is the v1/v3
engine; gen_v2 runs only as arm C / the dark flag-on path).

### 6.4 fit seam — multiply BEFORE the 1e-9 quantization

`trade_gen_fit.py:389-392` (rank), `:428-444` (card build):

```diff
+    # trade.negmem (D-4) — ordering-only rank-key multiplier (fit's aggregate
+    # payload stays pure). Applied to the aggregate BEFORE the 1e-9 quantization
+    # so C7c plateau noise (~1e-13) scaled by m stays below the quantum and the
+    # same-partner plateau tie survives (m is partner-constant ⇒ equal keys).
+    _nm_cache: dict[str, float] = {}
+    def _nm_eff(uid: str) -> float:
+        m = _nm_cache.get(uid)
+        if m is None:
+            m = (negmem.effective_mult(negmem_map, uid,
+                                       strength=ts._c("negmem_strength"),
+                                       floor=ts._c("negmem_floor"))
+                 if negmem_map is not None else 1.0)
+            _nm_cache[uid] = m
+        return m
     candidates.sort(key=lambda c: (
-        -round(c["aggregate_raw"], 9), -c["fairness"],
+        -round(c["aggregate_raw"] * _nm_eff(c["member"].user_id), 9), -c["fairness"],
         (c["member"].user_id, tuple(sorted(c["give_ids"])),
          tuple(sorted(c["recv_ids"])))))
```

Card build (`:442` region) — `composite_score = round(c["aggregate_raw"], 4)` is **unchanged**
(ordering only); the stamp still rides so influence is observable and the GR4 joint computable:

```diff
         card.need_fit = ts.need_fit_score(...)
+        if _nm_eff(member.user_id) != 1.0:
+            card.negmem_stamp = negmem.stamp_payload(
+                negmem_map, member.user_id, _nm_eff(member.user_id))
         cards.append(card)
```

**Fragility, named (HLD §2.2):** fit's negmem effect lives only in list order, and
`composite_score` is pure — so any downstream composite re-sort erases it. The bake-off's
protection is `restore_order` (`bakeoff_runner.py:1415`, called at `server.py:5766` after the
likes-you injector's re-sort) plus Channel 2's re-ranker bypass (`server.py:5890-5893`,
`:5843`, `:5866`). §9 T-16 asserts the ordering end-to-end through that path — this dependency
is load-bearing, not incidental.

### 6.5 Features-assembly stamp (B2 + the trichotomy)

`_log_deck_signal_impressions` gains `nm_map=None`; insertion directly after the base
`features = {...}` dict closes (`server.py:4160`), before the flag-gated additive keys — so the
key exists on **every** row the job writes (served AND ghost: the `entries` loop `:4120-4122`
covers both), in every arm, whenever `nm_map is not None`:

```diff
+        # trade.negmem — §3.4 trichotomy. ON-condition = flag ∧ allowlisted
+        # (nm_map is not None). Assembly COPIES card state (B2) and computes
+        # NOTHING: by logging time every arm's _cfg_override context has exited,
+        # so a recompute here would stamp arm-A rows with the live arm's m.
+        if nm_map is not None:
+            if nm_map.degraded:
+                features["negmem"] = {"m": 1.0, "ver": _negmem.NEGMEM_VER,
+                                      "degraded": True}
+            else:
+                _st = getattr(card, "negmem_stamp", None)
+                if _st is not None:
+                    features["negmem"] = _st          # consult-time stamp always wins
+                elif features["likes_you"]:
+                    features["negmem"] = {"m": 1.0, "ver": _negmem.NEGMEM_VER,
+                                          "exempt": True}
+                else:
+                    features["negmem"] = {"m": 1.0, "ver": _negmem.NEGMEM_VER}
```

Precedence rule, stated: a consult-time stamp on the card **always rides** (provenance, B2); the
`exempt` default applies only to cards with no consult site — likes-you *injections* (built by
the injector, which has no seam — R4 exemption). An organic card the injector merely boosted was
consulted at generation before its like status was known; its real stamp is the honest record.
Inside `features_json` (one Text column, always present) the executemany first-row-keys trap
cannot drop it — the fit/fit_diag argument (`server.py:4197-4204`) verbatim.

`nm_map is None` (flag off OR not allowlisted OR hard build failure §6.1) ⇒ the key never
appears anywhere ⇒ features_json byte-identical (C1).

---

## 7. Observability: readout, SQL pack, RFPS artifact

### 7.1 `negmem_readout` output format (R8)

```python
{
  "user_id": ..., "league_id": ..., "as_of": ..., "ver": 1,
  "degraded": false, "build_ms": 41.2,
  "knobs": {"negmem_strength": ..., "negmem_floor": ..., "negmem_min_evidence": ...,
            "negmem_halflife_days": ..., "negmem_sat_k": ..., "negmem_like_net": ...,
            "gen2_accept_prior_strength": ..., "gen2_accept_global_prior": ...},
  "cells": [   # sorted (partner, family); EVERY cell incl. identity ones
    {"partner_league_id": "...", "family": "value", "n_raw": 4, "n_decayed": 1.86,
     "likes_net": 0.86, "mult": 1.0, "floored": false, "below_min_evidence": true,
     "context_tag_counts": {"lane": {"window": 3, null: 1},
                            "user_value_basis": {"personal": 4},
                            "trade_intent": {null: 4}}},   # R11: annotated, NULL expected
    ...
  ],
  "partner_mult": {"<partner>": 0.9, ...},           # DE-1 MIN collapse
  "acceptance_stats": {"<partner>": [3, 7], ...},    # (accepts, responses); {} when guard fired
  "dropped_unmapped_partner_ids": 0                  # §5.4 id-space counter
}
```

Same builder, same admission implementation (C5 determinism holds for the readout too). This
dict is the substance of the operator TestFlight checklist (§8.5).

### 7.2 Stamp-rate tripwire SQL (allowlist-scoped denominator)

Added to the readout pack as `negmem-stamp-rate.sql` (shipped in this folder; the pack runner
substitutes the allowlist from `load_negmem_league_allowlist()` — the SAME loader as the build,
so a partial rollout can never read as build failures):

```sql
SELECT date(i.served_at) AS day,
       COALESCE(i.model_arm, 'organic') AS arm,
       COUNT(*) AS rows_,
       SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END) AS stamped,
       ROUND(1.0 * SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END)
             / COUNT(*), 4) AS stamp_rate          -- expected 1.0000 while flag ON
  FROM deck_impressions i
 WHERE i.served_at >= :flag_on_at
   AND i.league_id IN ({allowlist})                 -- ALLOWLIST-SCOPED (HLD §7)
 GROUP BY 1, 2 ORDER BY 1, 2;
```

(The `LIKE` probe is dialect-neutral and safe: `"negmem"` cannot appear as a features key any
other way — the substring includes the JSON quoting. The pack's Postgres variant may use
`features_json::jsonb ? 'negmem'`; both forms ship, SQLite form is normative.)

### 7.3 GR4 joint-multiplier audit (DE-4)

Definition (round-3 requirements honored):

```
joint(row) = negmem_m(row) × final_score / base_score        -- non-bake-off rows only
```

- `negmem_m` = `features_json.negmem.m`.
- **The ratio EXCLUDES negmem's own multiply on the score-multiplied paths by construction**:
  `base_score` is `card.composite_score` at logging (`server.py:4213`), which on the serving and
  gen_v2 paths already CONTAINS m (§6.2/§6.3 multiply composite at generation) — so
  `final/base` is purely the post-generation ordering stack and `joint` counts m exactly once,
  never m². On fit rows composite is pure (§6.4) and the ratio likewise excludes m, so the same
  formula is uniform.
- **Thompson layer, named**: the Thompson draw multiplier folds into the ordering key that
  becomes `final_score` — it enters the joint **via the ratio**; the `propensity` column (which
  records the same draw) is **not** multiplied in again (that would double-count).
- Pollution accepted (DE-4): A6 diversity penalties and session demotions also ride
  `final/base`, pushing `joint` DOWN — i.e. toward a false trip of the 0.15 bar, the safe
  direction. If p5 approaches 0.15, the runbook's first question is ratio pollution
  (§8.4); stamping `fatigue_m`/`taste_m` is the P2-shaped escalation, not built now.
- Pack query `negmem-gr4-joint.sql`: select `negmem_m`, `base_score`, `final_score` for
  allowlisted, flag-era, non-bake-off (`model_arm IS NULL`), `base_score > 0` rows; the runner
  computes p5 in Python (SQLite has no percentile function). Trip: `p5(joint) < 0.15` ⇒ raise
  floors (GR4).

### 7.4 RFPS (§4.2 PRD) — metric SQL + the R-X frozen-cohort artifact

Computation (offline, `backend/scripts/negmem_rfps.py`, imports `backend.negmem` — one-off
operator script per house convention):

1. Cohort: all **viewed** pass/`not_interested` outcomes in the window for allowlisted leagues
   (viewed-gate, ghost-exclusion, clean-epoch — the same closed-list clauses via
   `load_admitted_events`'s SQL with the reason-join made a LEFT JOIN: RFPS needs reason-LESS
   rejections too, per the pre-registered numerator rule).
2. For each outcome, rebuild the map **as-of `served_at`** (the builder is a pure function of
   (user, league, as_of) — C5) and record the card's partner cells.
3. Numerator: reason-carrying rejection whose `(partner, family)` cell held
   `n_decayed ≥ negmem_min_evidence` at `served_at`; reason-LESS rejection iff ANY admitted
   `(partner, ✱)` cell held ≥ threshold (the PRD's fixed rule).
4. Read per arm via `model_arm` + `bakeoff_runs.config_json` knob snapshots.

**Frozen-cohort artifact (R-X fix — binding)** — committed at pre-registration as
`docs/plans/negative-results-memory/rfps-baseline-<YYYYMMDD>.json`:

```json
{
  "generated_at": "2026-08-2XT..Z", "pre_registered": true,
  "window": {"start": "...", "end": "..."},
  "leagues": ["..."],
  "knobs_frozen": {"negmem_min_evidence": 3.0, "negmem_halflife_days": 45.0,
                   "negmem_sat_k": 3.0, "negmem_like_net": 1.0},
  "id_mapping": "features_json.partner_user_id (global platform id) -> canonical league owner_id via sleeper_roster.canonical_owner_id over league_members.roster_data (ADR-012); inline alias_map below is the mapping OF RECORD for this cohort",
  "alias_map": {"<global_id>": "<league_owner_id>"},
  "cohort": [
    {"impression_id": "…", "served_at": "…", "outcome_id": 123,
     "partner_league_id": "…", "reason_family": "value",
     "cells_at_serve": {"value": 4.25, "fit": 0.0},
     "numerator": true}
  ],
  "baseline_rfps": 0.31, "n": 412, "family_switch_rate": 0.0
}
```

Window-close evaluation runs over the **frozen `impression_id` cohort** with cell assignments
frozen at close; the script reports the in-window family switch-rate (reason rows whose
`switched_from` hop changed their family vs the artifact) alongside the point estimate;
switch-rate > 5% ⇒ the window extends (§8.3 ladder). H-2's mutable-reason drift is thereby
contained to a reported number, never a silent baseline shift.

**Power line for §8.3 (pre-registered formula, numbers filled at baseline freeze):**
`n_per_period = (z_{0.975} + z_{0.80})² · (p₁(1−p₁) + p₂(1−p₂)) / (p₁ − p₂)²` with
`p₂ = 0.75·p₁` (the 25% target). Worked at a plausible `p₁ = 0.30`: `7.849 · 0.3844 / 0.005625 ≈
536` qualifying rejections per side ⇒ at ~120 clean reason rows/wk, ≈ 4.5 weeks per side of a
within-arm before/after — consistent with the HLD's "the honest early outcome may be extend."
Max-extension review trigger: operator review at 2× the planned window (PRD §8.3).

---

## 8. Error Handling, Edge Cases, Rollout

### 8.1 Error contract table

| Failure | Behavior | Visible as |
|---|---|---|
| League not allowlisted | `build_map` → `None`; no kwarg effect, **no stamps** | indistinguishable from flag-off (by design) |
| Allowlist file unreadable | empty allowlist (⇒ None everywhere) + warning log | log line; stamp-rate pack uses the same loader so no false alarm |
| Any exception inside `build_map` | caught internally → degraded identity map (`cells={}`, `acceptance_stats={}`, `degraded=True`); **never raises** (F3 precedent `server.py:4499-4503`) | `{m:1.0, degraded:true}` on every row; `j["negmem_note"]` |
| Slow-but-valid build (`build_ms > 500ms`) | map marked degraded — **discarded by design**, not just stamped: `effective_mult` → 1.0, `m2_feed()` → `{}` | same as above + `build_ms` in the note |
| Hard failure in the server wrapper (belt) | `nm_map = None` + warning | stamp ABSENCE while flag ON + allowlisted = the §8.4 tripwire |
| `effective_mult` edge inputs | None/degraded/unknown partner/strength≤0 ⇒ exactly 1.0; never raises | — |
| M2 aggregation partner id unmapped to league member | dropped + counted (`dropped_unmapped_partner_ids`) | readout counter |
| `negmem_readout` with missing seed rows | `KeyError` with remediation text (operator tool — loud is correct) | script failure |
| Job death | **never for negmem** (C1/NG1): every path above degrades to identity | — |

### 8.2 Edge cases (PRD §5.3, pinned to mechanisms)

- Empty league / no evidence → zero cells → `partner_mult` empty → every consult 1.0 → every
  row `{m: 1.0}` (flag ON). New league-mate → identity until min-evidence.
- Duplicate/late outcome labels → per-impression dedupe (§5.2.2).
- Reason lateness (H-1) → `as_of` = build time; builder/readout/RFPS share the one admission
  implementation, so they can never disagree about the same instant.
- Reason upsert hop (H-2) → conceded per R6; RFPS contained by the frozen cohort (§7.4).
- Concurrent same-session jobs (H-4) → overwrite-per-call + read-once-into-local (§6.2).
- Mid-week taxonomy extension → layer-1 column routing (§5.1 note).
- Co-owned rosters → §5.4.
- Deleted user data → derive-on-read: deleting spine rows IS deleting the memory (D3(c)).
- Likes-you injections → exempt stamp (§6.5); boosted organic cards keep their real stamp.
- Ghost rows → excluded as *evidence* (R1(c)); still *stamped* like every row the job writes
  (HLD §3.4 wording — moot while the holdout is operator-ruled off, covered regardless).

### 8.3 Backcompat & migration

- **Schema:** none. The stamp is a JSON key inside an existing Text column; old rows simply lack
  it (and pre-flag rows are outside every flag-era query window).
- **Knobs:** seeded via `INSERT OR IGNORE` (`database.py:2186-2188` mechanism) — existing DBs
  pick them up on next boot; `PUT /api/admin/config/<key>` hot-applies (re-runs
  `reload_config()`).
- **Flag:** default False in code; ships dark. Byte-identical-off is C1's golden set, per path.
- **Rollback ladder** (all deploy-free, nothing left behind — derive-on-read):
  `trade.negmem` off (everything incl. M2) → `negmem_strength = 0` (M1 inert; M2 still feeds —
  its own kill is `gen2_accept_prior_strength = 0`; map still builds for readout/stamps) →
  `negmem_floor = 1.0` (clamp to identity; diagnostic posture, stamps keep flowing).
- **Downgrade note (documented divergence):** PRD R10's "0 = byte-identical disable"
  parenthetical is M1-SCOPED after the round-3 decision (HLD §5.3) — carried into
  `docs/config-reference.md` wording.
- **Feature-gate posture:** this change adds a flag + knobs ⇒ crosses the express-lane bright
  line ⇒ full gates (scope block, evidence, docs table, ledger), regardless of operator mood.

### 8.4 Runbook lines (verbatim, for `docs/runbook.md`)

1. *"negmem stamp-rate < 100% on allowlisted leagues while `trade.negmem` is ON ⇒ map builds are
   failing silently (flag ON + no `negmem` keys is the failure signature — failure is in the
   data, never inferred from absence). Triage order: stamp rate → degraded notes
   (`negmem_note` on job dicts / `{degraded:true}` stamps) → knob triple
   (`negmem_strength` / `negmem_floor` / `gen2_accept_prior_strength`)."*
2. *"negmem degraded-rate > 1% of jobs over 24h ⇒ set `negmem_strength = 0` and investigate;
   window censored at the flip timestamp (§8.3 PRD)."*
3. *"Any §8.3 guardrail breach at any time ⇒ `negmem_strength = 0` (deploy-free). A breach
   plausibly originating in the acceptance prior additionally takes
   `gen2_accept_prior_strength = 0` (or rung 1: flag off) — `negmem_strength` does NOT govern
   M2."*
4. *"Kill M2 via the GLOBAL knob only (`PUT /api/admin/config/gen2_accept_prior_strength` = 0),
   NEVER an arm overlay pin — a per-arm pin with a nonzero global leaves the feed populated and
   `acceptance_prior` returning the raw unshrunk ratio (the guard lives in the feed, NG9)."*
5. *"`trade.negmem` flag flips and every `negmem_*` / `gen2_accept_prior_*` knob move land at
   bake-off ROUND BOUNDARIES only (GR3; a mid-round flip censors the window — ADR-014)."*
6. *"GR4: p5 of (negmem_m × final_score/base_score) on allowlisted non-bake-off rows < 0.15 ⇒
   raise floors; first check the known downward pollution (diversity penalty in the ratio)
   before concluding real compounding."*

### 8.5 Operator TestFlight checklist (D-056 — the runtime evidence mobile gets)

Concrete steps, built on the readout:

1. Before the round-boundary flip: run `negmem_readout` for your league; confirm cells match
   your remembered pass history (partners you've repeatedly reasoned-passed show `n_raw > 0`).
2. After the flip, generate a deck; in the readout confirm `degraded: false` and
   `build_ms < 250`.
3. Swipe pass **with a reason** (value or fit) on a card toward partner P three separate times
   across sessions; regenerate; confirm cards toward P **still appear** (soft ≠ hidden — NG1)
   but lead less often, and the readout's (P, family) cell crossed `min_evidence`.
4. Like a card toward P; re-run the readout; confirm `likes_net` moved and the cell's
   `n_decayed` dropped by ~1 (netting visible).
5. Stamp spot-check (operator SQL or the pack): today's rows all carry `features_json.negmem`;
   any influenced row's `m` < 1.0 matches the readout's `partner_mult` × strength math.
6. Kill-switch drill: set `negmem_strength = 0` via the admin config PUT; regenerate; confirm
   deck order reverts and every stamp reads `{m: 1.0}`.

---

## 9. Testing (every test named; fixture shape; what it proves)

New file `backend/tests/test_negmem.py` (+ additions to `test_bakeoff_arm_a_golden.py` and the
readout script's self-test). House patterns: in-memory engine (tests/CLAUDE.md pattern 1), flag
idiom 3, cfg snapshot idiom 4 (`test_trade_engine_v2._isolate_flags_and_cfg` is canonical), and
the bake-off harness fixture idiom (`backend/tests/support/bakeoff_harness.py`) for in-job
arm-attributed decks. **Sabotage discipline**: each behavioral test lists its named sabotage;
proven RED against it, green on revert (TEST_LEDGER records the names).

**Shared fixture `_negmem_world()`** — in-memory DB seeding: 12-member league (one co-owned
roster from the `fixtures/sleeper/co-owned-league` shape); partner X with 5 admitted `value`
passes (day −10..−1), partner Y with 2 (sub-threshold), partner Z with 3 `fit` passes + 1
viewed like; one ghost pass, one unviewed pass, one `other`-family pass, one `key_source='local'`
reason, one undone pass, one pre-epoch pass (all inadmissible); `trade_matches` rows giving X
(2 accepts, 5 responses). **Fixture-power rule (HLD §7)**: this world yields m < 1.0 for X on a
non-A arm in-job — T-5/T-9/T-11 all run against it, so none can pass vacuously.

| # | Test | Fixture / shape | Proves | Sabotage (RED proof) |
|---|---|---|---|---|
| T-1 | `test_admission_sql_predicate_parity` | the inadmissible-row matrix above, run BOTH through `_ADMISSION_SQL` and `admission_predicate` row-by-row | the pair is ONE implementation (H-1 defense); each R1 clause excludes exactly its row | drop the ghost clause from the predicate |
| T-2 | `test_decay_shrinkage_worked_examples` | §4.3/§4.4 tables as literals | formulas match this doc to 1e-9; identity below min_evidence | flip `n_eff` off-by-one |
| T-3 | `test_combine_rule_min` | the DE-1 3-row table | partner_mult is MIN; product regression caught | change MIN→product |
| T-4 | `test_effective_mult_invariants` | property sweep: mult∈[0,1], strength∈[0,3], floor∈[0.4,1] | C2: eff∈[floor,1]; sink-never-rise; strength 0 ⇒ exactly 1.0; pure (no DB in scope — module engine patched to a poisoned object) | remove the clamp |
| T-5 | `test_serving_golden_strength0_stamp_inclusive` | `_negmem_world`, flag ON, `negmem_strength=0`, serving path + fit fixture | golden (a): FULL byte-equality of decks **against a stamp-inclusive fixture** — every row carries `{m:1.0,"ver":1}`; deck content/scores/order identical to pre-negmem capture | make the seam round() at identity |
| T-6 | `test_arm_c_dual_kill_golden` | `_negmem_world` bake-off job, `negmem_strength=0` ∧ `gen2_accept_prior_strength=0` | golden (b): arm-C deck byte-identical — verifies M2's structural kill AND gen_v2's M1 seam (which M2 could otherwise mask) | move the feed guard into `acceptance_prior` |
| T-7 | `test_arm_a_rows_stamp_exactly_identity` | `_negmem_world` bake-off (fixture-power: live arm has m<1.0 in the same job) | golden (c): every `model_arm='baseline'` row stamps exactly `{m:1.0,"ver":1}` — never absence, never a live m | drop `negmem_strength` from MODEL_A_PROFILE |
| T-8 | `test_stamp_provenance_b2` | consult under arm overlay with strength 1.0, then flip live `_cfg` to strength 0 BEFORE logging | B2: assembly copies card state — the stamp still shows the consult-time m (a recompute would show 1.0) | recompute the stamp at assembly |
| T-9 | `test_t1_sabotage_live_binding` | `_negmem_world`; monkeypatch-rebind `negmem.effective_mult` to return 0.5 | T1: fit + serving output CHANGES ⇒ live module-attribute binding, no frozen import | `from negmem import effective_mult` at a seam |
| T-10 | `test_likes_you_led_deck_batch_stamps` | deck whose FIRST card is a likes-you injection (the model_arm scar scenario), flag ON | batch-wide `negmem` key retention through `save_deck_impressions`' executemany; injection stamps `exempt`, boosted organic keeps real stamp | move the stamp outside features_json |
| T-11 | `test_c1_flag_off_and_unallowlisted_byte_identity` | `_negmem_world` with (i) flag OFF, (ii) flag ON + league NOT allowlisted | C1: no kwarg effect, no stamp key anywhere, features_json byte-identical; the None seam is indistinguishable from flag-off | stamp on `nm_map is None` |
| T-12 | `test_map_determinism_and_asof` | build twice at same as_of; build at historical as_of | C5 determinism; as-of reproducibility incl. netting events in-domain (R6) | inject `now()` into the fold |
| T-13 | `test_m2_parity_both_call_sites_incl_empty` | hand-computed E-B values; empty tables | C4: feed × `acceptance_prior` reproduces memo §2f exactly at `trade_service.py:4001` and `bakeoff_runner.py:1212`; empty ⇒ `{}` ⇒ uniform p0 (S4 expected-null) | flip the tuple to (responses, accepts) |
| T-14 | `test_m2_feed_guard_and_zero_response_keys` | knob ≤ 0; a partner with matches but no decisions | feed `{}` at strength ≤ 0; zero-response keys structurally absent; global-kill (not overlay) semantics documented-in-assert | emit partners with `responses=0` |
| T-15 | `test_netting_order_clamp` | like-before-evidence; like-after; retracted like | DE-2: chronological fold, clamp-at-zero every step, no banked credit, cells never negative; retracted like nets nothing | clamp only at fold end |
| T-16 | `test_fit_end_to_end_ordering_restore_order` | bake-off fixed-order deck, fit arm rostered, likes-you injection active | the fit arm's negmem ordering survives to the served deck through `restore_order` (`server.py:5766`) — the composite re-sort does not erase it | skip `restore_order` |
| T-17 | `test_fit_quantization_order` | C7c plateau pair (same partner, aggregate Δ ~1e-13) + cross-partner pair | m applied BEFORE the 1e-9 round: same-partner tie survives; cross-partner order splits by m | multiply after the round |
| T-18 | `test_degraded_behavior` | (i) builder raises mid-read; (ii) valid build with build_ms forced > 500ms | degraded map: seams identity (incl. slow-but-valid discard), stamps `{m:1.0,degraded:true}` on every row, `m2_feed() == {}` | stamp degraded but keep multiplying |
| T-19 | `test_streaming_callback_golden` | serving path with `on_opponent_done` capturing every snapshot | strength-0 snapshots byte-identical; strength-1 snapshots multiply-once (composite == pre-capture base × m at every snapshot — `_dedup_and_sort` re-runs never compound, `trade_service.py:4152-4157`) | multiply inside `_dedup_and_sort` |
| T-20 | `test_identity_hygiene_co_owner` | co-owned league; decisions/matches recorded under the alias id | §5.4: map + M2 keys are canonical owner ids; alias rows fold into the owner's cells; account ids never appear as keys (R9) | key on raw `partner_user_id` |
| T-21 | `test_horizon_in_query` | one event at as_of−4H−1d, one inside | out-of-horizon event never loaded (query-level, not fold-level) | filter in Python instead |
| T-22 | `test_knob_and_flag_registration` | — | six knobs present in `_DEFAULT_CFG` + seed rows + `_PINNED_KNOBS` (the existing inventory test `test_bakeoff_arm_a_golden.py:545` fails by name otherwise — this test pins the negmem-specific rows and the `MODEL_A_PROFILE` pin); `trade.negmem` in FLAG_KEYS; release.json mirror test already enforces the flag file | — (inventory test is the alarm) |
| T-23 | `test_readout_format` | `_negmem_world` | §7.1 dict shape snapshot incl. `likes_net`, context-tag NULL annotation, dropped-id counter | — |
| T-24 | `test_relaxed_pass_same_map` | targeted job yielding zero cards then relaxed cards | relaxed re-run consults the SAME map/strength; relaxed cards stamped; no special case (HLD §3.5) | rebuild map in the relaxed pass |

Evidence ledger: all runs logged in `living-memory/TEST_LEDGER.md` with sabotage names; CI green
(pytest + tsc + testid-lint) is the pre-ship gate; `FTF_SKIP_SIM_GATE=1` standing posture per
D-056.

---

## 10. Open Questions (for cross-review)

- **OQ-1 (flagged, resolved by code — needs B's ack):** HLD §2.1 writes
  `acceptance_stats{partner: (responses, accepts)}`; the ratified consumer unpacks
  `accepts, responses = acceptance_stats[user_id]` (`trade_gen_v2.py:305`). This LLD follows the
  code — `(accepts, responses)` — and treats the HLD line as a transcription slip (the memo §2f
  interface `uid → (accepts, responses)` agrees). T-13's sabotage is exactly this flip.
- **OQ-2:** allowlist file name `config/negmem_leagues.json` — operator to confirm at the D1
  ruling touchpoint (mechanics are DE-5 regardless of name).
- **OQ-3:** the 600s pairing window in §5.3 is a chosen constant (same-request writes land in
  seconds); if cross-review prefers, it can widen to session-length with no admission change in
  practice — flagged as a reviewable constant, not a knob (it guards a vacuous-by-construction
  check on the pass side).
- **OQ-4:** `negmem_floor`'s double role (curve asymptote at build, clamp at seam — §4.4). The
  alternative (a separate `negmem_curve_floor` knob) was rejected to keep the knob surface at
  R10's four + two; revisit only if an arm-overlay use case for `negmem_floor` ever appears
  (none is sanctioned — D-6 is strength-only).
- **OQ-5:** readout exposure as a CRON-authed admin route — deliberately out of v1 (R8 is
  scripts/pytest); noted for the explainer-UI feature's future gates (NG5).

## 11. Docs owed (scope-block Docs table rows)

| Doc | Row |
|---|---|
| `docs/config-reference.md` | `trade.negmem` flag + six `negmem_*` knobs (+ the M1-scoped disable wording, §8.3) |
| `docs/data-dictionary.md` | `deck_impressions.features_json.negmem` stamp key (schema §3.3) |
| `docs/architecture.md` + `living-memory/HLD.md` | new leaf module + seam wiring |
| `living-memory/LLD.md` | the T1/consult-seam convention rows |
| `docs/runbook.md` | the six lines of §8.4 |
| `docs/glossary.md` | negmem, reason family, RFPS, evidence cell, like-netting |
| `docs/api-reference.md` | n/a — no route changes (readout is a function; admin config PUT pre-exists) |
| `docs/cross-client-invariants.md` | n/a — no client consumes the stamp in v1 |
| shared taxonomy v1.1.0 | `shape_aversion` PRODUCER=negmem entry + pass-reason anchoring (authorship per PRD §7 — breaker session owns §5; our two entries carried) |
