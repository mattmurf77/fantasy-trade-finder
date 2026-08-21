# LLD: Negative-results memory

**Version:** candidate v1 (merged per orchestrator ruling sheet; cross-review pending)
**Date:** 2026-08-21
**Serves:** [HLD.md](HLD.md) (FINAL — D-1..D-10 binding; §7 is this document's work order) ·
[PRD.md](PRD.md) (FINAL — R1-R11, NG1-NG9, C1-C5, GR1-GR4, §8.3) ·
Facts: [research-verification.md](research-verification.md) ("memo") ·
Settled: [reconciliation-log.md](reconciliation-log.md) — nothing decided there is reopened here.
**Provenance:** merged from [LLD-draft-A.md](LLD-draft-A.md) (implementer lens; structural base)
and [LLD-draft-B.md](LLD-draft-B.md) (reviewer lens; hazard handlings, dialect decisions,
id-space fix) under the orchestrator's binding ruling sheet. The drafts remain in-tree; this
candidate stands alone. All file:line citations verified on this checkout
(worktree `claude/vigilant-spence-8583f5`) by the draft that contributed them.

---

## 0. The LLD-owned DECIDEs, up front (rulings applied)

| # | Question (HLD §7) | Decision | Where argued |
|---|---|---|---|
| DE-1 | D-5 combine rule: product vs min across a partner's family cells | **MIN** (ruling 1) | §4.4 (with the 3-row fixture table) |
| DE-2 | Netting mechanism: decrement vs reset; magnitude; bounds | **DECREMENT** by knob `negmem_like_net` (default 1.0) per admitted viewed like, folded chronologically against every (P, ✱) cell with a clamp-at-zero after **every** fold step — the per-step clamp is what answers the bounds question (a cell can never go negative; a like can never bank credit) (ruling 2) | §4.5 |
| DE-3 | Build-time knob read path | **Pass-in-from-server** (ruling 3): `server._run_trade_job` reads ALL build knobs — including `gen2_accept_prior_strength` — via `trade_service._c(...)` on the job thread *before* the arm fan-out (no overlay active) and passes plain floats into `build_map`. negmem.py holds **zero** default literals. | §4.2 |
| DE-4 | Admission dialect | **Python predicate over a plain dual-dialect row fetch** (ruling 4): no SQL JSON extraction, no SQL timestamp arithmetic; `substr(served_at,1,10)` day-prefix bounds. The FETCH SQL + the Python predicate are the ONE shared implementation pair (builder, readout, RFPS). Perf math §5.6. | §5 |
| DE-5 | Id-space for M2 + evidence partner keys | **`owner_alias` injection** (ruling 5): the server builds the co-owner→canonical-owner map from the in-hand league object via `sleeper_roster` helpers and passes it into `build_map`. negmem never imports `sleeper_roster` — the ADR-012 predicate stays single-sourced, and the D-2 leaf import list is preserved. | §5.5 |
| DE-6 | GR4 computability: accept score-ratio pollution vs stamp `fatigue_m`/`taste_m` | **Accept the ratio pollution** (diversity penalty pollutes the joint *downward* = the false-trip direction = conservative; the 0.15 bar has margin). No new per-layer stamps in v1. | §7.3 |
| DE-7 | League-allowlist mechanism (build_map's None seam) | **`config/negmem_leagues.json`** (JSON array of league_id strings; `"*"` = all leagues) ∪ env `FTF_NEGMEM_LEAGUES` (comma-separated), 60s cache — the `tester_allowlist.json` pattern (`backend/experiments.py:87,120-127`; Render-ignores-envVars precedent says ship via file). Missing/empty ⇒ **no** leagues (flipping the flag alone activates nothing). (ruling 9) | §4.1 |
| DE-8 | gen_v2 seam placement | **m at pair-card creation, NOT in `_Candidate.score`** (ruling 8 — the membership-never-affected argument, reasoning verbatim §6.3). | §6.3 |
| DE-9 | Fit ordering | **Multiply BEFORE the 1e-9 quantization**, end-to-end pinned through `restore_order` (ruling 7). | §6.4 |
| DE-10 | B2 stamp assembly | **Copy-only** — assembly copies card state, computes nothing; the recompute sabotage is a named test (ruling 6). Stamp schema + byte estimates from draft A. | §6.5 |

---

## 1. Scope & Reference

### 1.1 What is built

One new leaf module `backend/negmem.py` (D-2; the `suggestion_telemetry.py` leaf precedent —
its header at `backend/suggestion_telemetry.py:12-16` is the model), plus:

- three consultation seams (serving stack / gen_v2 / fit) of ≤ ~10 lines each (D-4, D-10),
- one build + threading block in `server._run_trade_job` (D-3), including the server-built
  `owner_alias` map (DE-5),
- one stamp block in the features assembly (`server.py:4135-4212` region),
- the M2 `acceptance_stats` feed into gen_v2's two call sites
  (`trade_service.py:4001`, `bakeoff_runner.py:1212`),
- 6 `model_config` knobs + 1 feature flag (`trade.negmem`) with full triple registration (R10, D-8),
- readout SQL pack additions + the RFPS frozen-cohort artifact (§7),
- the test plan of §10 (27 tests).

**No new tables** (NG6, D-1). **No new analytics events.** **No new routes** (readout is a
function/script — R8; see §7.1).

### 1.2 What is explicitly not built (guards)

No hard suppression at any seam (NG1); no modification of `acceptance_prior`'s ratified math
(`trade_gen_v2.py:283-308` — the guard lives in the *feed*, NG9); no consumption of unacted
impressions (NG8); no per-shape keys (P2-gated); no UI (NG5); no touching F3/F5/D-067/R4/Thompson
semantics (NG9). Gate ordering unchanged everywhere — the multiplier applies after all gates,
membership is never affected (R4).

### 1.3 Code anchors (verified on this checkout by the contributing draft)

| Anchor | Where |
|---|---|
| Serving per-member multiplier stack | `trade_service._generate_trades_v2`, member loop `trade_service.py:4943` (`for idx, member in enumerate(eligible):`), multiplier blocks through `:5196`; the `_m != 1.0` skip idiom at `:5125-5127`; block-boost `:5097-5104`, outlook-dir `:5120-5127` |
| Config accessor + overlay | `trade_service._c` `:1004-1010`; `_cfg_override` `:994-1001`; `_DEFAULT_CFG` ends `:963` |
| exclusion_keys overwrite-per-call seam | `trade_service.py:3980-3986` |
| Relaxed pass | `trade_service._relaxed_targeted_pass` `:4271-4325` (re-invokes `_generate_trades_v2` under `_cfg_override`) |
| `_dedup_and_sort` (no score writes — §6.2 once-only proof) | `trade_service.py:4180-4256` |
| gen_v2 acceptance prior + per-pair loop | `trade_gen_v2.py:283-308` (E-B math, reproduced §5.4); orchestrator kwarg `acceptance_stats` `:862`; per-pair loop `:939-975`, `acceptance_prior` consumed `:951`; card build `:999` ff. |
| fit ranker + composite | `trade_gen_fit.py:389-392` (sort key, `-round(c["aggregate_raw"], 9)` quantization), `composite_score` set at `:442` |
| `_generate_kwargs` | `server.py:5644-5671`; bake-off fan-out lambdas `:5679-5685`; organic call `:5696` |
| features assembly | `server.py:4135-4212` (`features = {...}`), row build `:4219-4233`, `base_score` = `card.composite_score` at `:4213` |
| `_deck_fatigue_multipliers` (bulk-read pattern + MIN precedent + fail-open precedent) | `server.py:4482-4541`; MIN-never-product `:4494-4496`; fail-open `:4499-4503` |
| `restore_order` | `bakeoff_runner.py:1415-1430`, called `server.py:5766` |
| `snapshot_config` (D-8 mechanism) | `bakeoff_runner.py:423-433` |
| `MODEL_A_PROFILE` | `bakeoff_profiles.py:69-87` |
| `_PINNED_KNOBS` + inventory test | `backend/tests/test_bakeoff_arm_a_golden.py:471-542`, test `:545-559`; profile-names-real-knobs test `:562-567` |
| `_MODEL_CONFIG_DEFAULTS` (tuple shape `(key, value, description)`) | `database.py:2188` |
| `save_deck_impressions` (executemany, first-row-keys trap) | `database.py:5503-5515`; comment `server.py:4251-4256` |
| Spine tables | `deck_impressions` `database.py:500-608` (`served_at` NOT NULL `:513`, `features_json` Text `:507`, `propensity` `:508`), `deck_outcomes` `:741-761` (dup labels legal `:743`), `trade_pass_reasons` `:873-943` (layer-1 column `:894-902`, free_text quarantine `:903-905`), `trade_matches` `:417-436`, `trade_decisions` `:319-337` (`retracted_at` `:328-336`) |
| Spine indexes | `ix_deck_impressions_user_league` `database.py:610`; `ix_deck_outcomes_impression` `:758`; `ix_trade_matches_user_*_league` `:443-452` |
| Dialect precedent (no JSON/date SQL; `substr` day buckets; Python parsing) | `analytics_queries.py:8-12` |
| Identity predicate (server-side only — DE-5) | `backend/sleeper_roster.py` (`canonical_owner_id`, `co_owner_ids`) — ADR-012 |
| Tester-allowlist precedent | `backend/experiments.py:87, 120-127` + `config/tester_allowlist.json` |
| Timestamp writer (ISO `+00:00` text) | `datetime.now(timezone.utc).isoformat()` — `database.py:5542`, `server.py:4115` |
| Batched events side-channel (`viewed` can land after the swipe) | `server.py:8088-8107` |

---

## 2. Interfaces — `backend/negmem.py` module skeleton

Leaf discipline (D-2, T1): imports **only** `feature_flags` and `database` (plus stdlib).
**Not** `sleeper_roster` — identity arrives by injection (`owner_alias`, DE-5). Never imports
`server`, `trade_service`, or any engine module. Cycle check: `negmem → database →
pick_values`; `pick_values` imports `trade_service` lazily inside functions
(`database.py:36-38`), so no import-time cycle exists. Engines consume it via
`from . import negmem as _negmem` + attribute call — **never**
`from .negmem import effective_mult` (T1 rule; value import freezes the binding;
sabotage-tested §10 N-11). **No module-global map, ever.** A structural test asserts the
import list (§10 N-24).

```python
"""negmem.py — negative-results memory (flag `trade.negmem`, default OFF).

M1: per-(league, partner, reason-family) soft down-weight built from reasoned
rejections; M2: the acceptance_stats feed for trade_gen_v2.acceptance_prior.
Derive-on-read, zero tables (NG6). LEAF: imports feature_flags + database
only; engines `import negmem` and call attributes (T1) — the map moves
exclusively as an argument (D-3). Identity: co-owner canonicalization is
INJECTED (`owner_alias`) — the ADR-012 predicate lives server-side. PRD/HLD:
docs/plans/negative-results-memory/. Admission is the ONE closed list (R1):
the fetch-SQL + Python-predicate pair below are the only implementation —
builder, readout, and RFPS all go through _admit_events()."""

NEGMEM_VER = 1                      # stamp schema version; bump on any change
                                    # to admission, decay, or netting semantics
NEGMEM_CLEAN_EPOCH_DAY = "2026-08-20"        # R1(e); subsumes D-091 (ends 08-19)
NEGMEM_ADMITTED_FAMILIES = ("value", "fit")  # R2 — closed set
NEGMEM_HORIZON_HALFLIVES = 4.0               # HLD §3.1 read horizon
NEGMEM_BUILD_BUDGET_MS = 250.0               # S6 absolute ceiling (HLD §3.1)
NEGMEM_DEGRADE_MS = 2.0 * NEGMEM_BUILD_BUDGET_MS   # slow-but-valid ⇒ degraded
_DECISION_ACTIONS = frozenset({"like", "pass", "not_interested", "propose"})

ALLOWLIST_FILE = ".../config/negmem_leagues.json"   # os.path.join like experiments.py:87

def negmem_league_allowed(league_id: str) -> bool:
    """PRD §8.2 league scoping: True iff league_id ∈ (file ∪ env) allowlist,
    or the allowlist contains "*". 60s cache; unreadable file ⇒ empty (warn)."""

def load_negmem_league_allowlist() -> set[str]:
    """The raw allowlist (env FTF_NEGMEM_LEAGUES ∪ config/negmem_leagues.json).
    Exposed for the readout pack's allowlist-scoped denominators."""

@dataclass(frozen=True)
class NegmemCell: ...          # §3.1

@dataclass(frozen=True)
class NegmemMap: ...           # §3.2
    # method: m2_feed() -> dict[str, tuple[int, int]]   — §3.2

def build_map(user_id: str, league_id: str, *,
              halflife_days: float, min_evidence: float, sat_k: float,
              like_net: float, floor_b: float,
              accept_prior_strength: float,
              owner_alias: dict[str, str] | None = None,
              as_of: str | None = None) -> NegmemMap | None:
    """One bulk read → NegmemMap for this job; None iff league not allowlisted
    (the PRD §8.2 None seam — downstream indistinguishable from flag-off).
    NEVER raises except KeyboardInterrupt/SystemExit (BaseException passes
    through `except Exception` untouched); any internal Exception returns a
    degraded identity map (§8.1). All knobs arrive as arguments — no config
    access in this module (DE-3). Degenerate knobs sanitized once at entry:
    floor_b → min(max(floor_b, 0.0), 1.0); halflife_days, min_evidence,
    sat_k → max(value, 1e-6) — a fat-fingered admin PUT must not produce
    ZeroDivisionError or a mult > 1. owner_alias None ⇒ identity mapping."""

def effective_mult(nm_map: "NegmemMap | None", partner_league_id: str, *,
                   strength: float, floor: float) -> float:
    """PURE (D-10): eff = clamp(1 + strength·(mult−1), floor, 1.0). No config
    access, no defaults, no I/O. Total function — §4.6 defines every input
    class including NaN. None/degraded map, unknown partner, or
    strength ≤ 0 ⇒ exactly 1.0."""

def stamp_payload(nm_map: "NegmemMap", partner_league_id: str,
                  eff: float) -> dict:
    """The consult-time stamp the card carries (B2): {m, keys, ev, ver}. §3.3."""

def load_admitted_events(user_id: str, league_id: str, *, as_of: str,
                         horizon_floor_day: str,
                         owner_alias: dict[str, str] | None = None
                         ) -> tuple[list[dict], list[dict], int]:
    """R1's closed list, THE one implementation: runs _SPINE_SQL (the plain
    dual-dialect fetch), then applies the Python predicate (per-impression
    replay + closed-list checks + retraction leg + canonicalization + context
    tags). Returns (evidence_events, netting_events, parse_errors). Consumed
    by build_map, negmem_readout, and the RFPS artifact generator — nobody
    re-implements."""

def negmem_readout(user_id: str, league_id: str, as_of: str | None = None,
                   knobs: dict | None = None,
                   owner_alias: dict[str, str] | None = None) -> dict:
    """R8 operator dump (§7.1 format). Same builder, allowlist check BYPASSED
    (the readout must work for a not-yet-allowlisted league — it reports
    `allowlisted` as data; a readout that returns None there is a tautology).
    knobs=None ⇒ read database.get_config() (leaf-legal, database.py:4153);
    a missing knob key raises KeyError('negmem seed rows missing — run
    init_db') — negmem holds no default literals (DE-3)."""

_SPINE_SQL: str        # §5.1 — the fetch half of the admission pair
_RETRACTED_SQL: str    # §5.3 — the retraction-leg fetch
_MATCHES_SQL: str      # §5.4 — the M2 fetch

# internal: _admit_events (§5.2 — the predicate half of the pair),
#           _fold_events (§4.3/§4.5), _cell_mult (§4.4),
#           _acceptance_fold (§5.4)
```

Type notes (reviewer's first questions):

- `min_evidence` arrives as `float` because `model_config` is Float-valued; compare
  `n_decayed >= min_evidence` in float, never `int()`-truncate (an `int(2.9)==2` truncation
  silently lowers the gate).
- `NegmemMap` and `NegmemCell` are `frozen=True`: the map is shared read-only across the
  bake-off fan-out and must be structurally immutable (H-4 defense; a seam cannot "fix up" a
  cell in place).
- `cells` uses league-identity partner keys only (R9); `owner_alias` maps any co-owner id
  seen in source rows to the roster's canonical `owner_id` before keying (ADR-012, via
  injection).

### 2.1 Threading interface changes (exact signatures)

The map travels **only as a kwarg** — **no `self._negmem` instance slot exists** (draft B's
strengthening, adopted: there is no shared slot for a concurrent same-session job to
overwrite, which discharges H-4 more strongly than the `_exclusion_keys` overwrite-per-call
precedent it was first modeled on; `trade_service.py:3983` remains the precedent for kwarg
*semantics*, not for storage). `_generate_kwargs["negmem"] = nm_map` is set **only when
`nm_map is not None`** (key absent otherwise — flag-off kwargs are byte-identical, C1).

| Site | Change |
|---|---|
| `server._run_trade_job` | build `nm_map` once per job after the flag check, before the fan-out (§6.1); conditionally add `negmem` to `_generate_kwargs` (`server.py:5669` region — after `exclusion_keys`); pass `nm_map` into `_log_deck_signal_impressions` |
| `TradeService.generate_trades` / `_generate_trades_impl` (`trade_service.py:3899`) | new kwarg `negmem: "negmem.NegmemMap | None" = None`, documented alongside `exclusion_keys` (`:3951-3956`); threaded directly (no attribute) into `_generate_trades_v2(negmem_map=negmem, ...)` **and** inside the `v2_kwargs` dict handed to `_relaxed_targeted_pass` (`:4271`) — the relaxed pass then reuses the identical map at the same `_c`-read strength with zero special-casing (HLD §3.5) |
| `TradeService._generate_trades_v2` (`:4747`) | new kwarg `negmem_map=None` |
| `trade_gen_v2.generate_league_suggestions` (`:844`) | new kwarg `negmem_map=None` (beside `acceptance_stats` `:862`) |
| `trade_gen_fit.generate_league_suggestions` (`:237`) | new kwarg `negmem_map=None` |
| `bakeoff_runner.gen_v2_cards` (`:1317` region, call at `:1212`) | forward `kwargs.get("negmem")` as `negmem_map` + the M2 feed (§6.3) |
| `bakeoff_runner.gen_fit_cards` (`:1317`) | forward `kwargs.get("negmem")` as `negmem_map` |

Arms A/B need no forwarding code: the fan-out lambdas splat `**_generate_kwargs`
(`server.py:5680-5681`), so `negmem=` arrives at `generate_trades` unchanged — **one frozen
map, all arms** (H-3), differing only via each arm's overlay-read `negmem_strength`.

---

## 3. Data Structures

### 3.1 `NegmemCell`

```python
@dataclass(frozen=True)
class NegmemCell:
    n_raw: int          # admitted rejection events in the horizon (pre-decay, pre-net)
    n_decayed: float    # decayed, like-netted evidence mass at as_of; ≥ 0.0 always; rounded 1e-9
    likes_net: float    # decayed like mass subtracted (readout transparency)
    mult: float         # base multiplier from §4.4; ∈ [floor_b, 1.0]; 1.0 below min_evidence; rounded 1e-6
    floored: bool       # True when the §4.4 curve landed within 1e-9 of floor_b
```

Nullability: none — every field always set. Cells exist for every
`(partner_league_id, family)` with ≥1 admitted rejection **or** ≥1 netting like in the horizon
(identity cells kept: the readout and the RFPS numerator rule both need sub-threshold state).

### 3.2 `NegmemMap`

```python
@dataclass(frozen=True)
class NegmemMap:
    user_id: str
    league_id: str
    as_of: str                                   # ISO UTC, build time or caller's as_of
    ver: int                                     # = NEGMEM_VER
    cells: dict[tuple[str, str], NegmemCell]     # key: (partner_league_id, family);
                                                 # family ∈ NEGMEM_ADMITTED_FAMILIES
    partner_mult: dict[str, float]               # collapsed per-partner base mult (DE-1 MIN),
                                                 # precomputed at build so effective_mult is
                                                 # O(1) per call; only partners with any cell;
                                                 # absent ⇒ 1.0
    acceptance_stats: dict[str, tuple[int, int]] # M2: partner → (accepts, responses);
                                                 # NOTE tuple order follows CODE
                                                 # (trade_gen_v2.py:305 unpacks
                                                 # `accepts, responses`) — the HLD §2.1
                                                 # comment has it flipped; code wins (§9 delta a).
                                                 # {} when accept_prior_strength ≤ 0 (feed guard,
                                                 # HLD §3.5) — never emitted with 0-response keys.
    degraded: bool                               # build exception OR build_ms > NEGMEM_DEGRADE_MS
    build_ms: float
    parse_errors: int                            # skipped rows (§8.1 row-level failures)

    def m2_feed(self) -> dict[str, tuple[int, int]]:
        """{} when degraded, else acceptance_stats — the ONE degraded-⇒-{} rule
        (HLD §3.5); both gen_v2 call sites go through this, never the field."""
```

All partner keys are **league identities** (R9): global platform ids from the spine are
canonicalized through the injected `owner_alias` (§5.5) before they become keys. Account ids
never enter the map.

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
- `ver`: `NEGMEM_VER` — on **every** variant (uniform SQL probing; the `ver`-everywhere widening
  over the HLD sketch costs ~8 bytes/row, stated).

Partner is deliberately **not** repeated (it is already `features.partner_user_id`). Expected
storage residue at 100% stamp-rate ≈ 20–85 B/row — inside the HLD's accepted ~60 B/row budget.
`stamp_payload()` is the only producer; seams set `card.negmem_stamp` at consult time; the
features assembly **copies**, never builds (B2, DE-10).

### 3.4 Knob table (R10 — full triple registration; ruling 11 carries this verbatim)

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
made structural by the feed guard (§5.4). **Kill M2 via the GLOBAL knob only, never an arm
overlay pin** (HLD §5.3; runbook line §8.4; wording status in §9 delta d).

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
   the arm-A golden itself runs flag-off (no map ⇒ seams never execute), and the profile pin
   adds a key `_cfg_override` merely overlays — `snapshot_config` output changes, deck bytes do
   not; §10 N-7 asserts this pair explicitly.

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

### 4.1 Allowlist gate (DE-7) and the None seam

`negmem_league_allowed(league_id)`: allowlist = `set(env FTF_NEGMEM_LEAGUES.split(","))` ∪
`json.load(config/negmem_leagues.json)` (array of strings), cached 60s (the
`experiments._load_cache` idiom). `"*"` anywhere ⇒ every league allowed. Missing file, empty
list, parse error ⇒ empty set (log a warning once per cache period on error). **Empty ⇒
`build_map` returns None** for every league: flag-on with an unpopulated allowlist is inert by
construction, and global rollout is the one-line diff `["*"]`.

`build_map` calls this first and returns `None` when not allowed — no map, no kwarg effect
downstream, **no stamps** (the trichotomy's ON-condition is flag ∧ allowlisted, HLD §3.4), and
the stamp-rate tripwire's denominator is scoped by `load_negmem_league_allowlist()` (§7.2), so a
partial rollout never reads as build failures. Caveat carried from draft B: an unparseable
allowlist file makes leagues silently non-allowlisted — the tripwire's denominator goes to zero
rather than alarming; the warning log plus the readout's `allowlisted` field are the
compensating checks, and the runbook names "denominator empty" as itself a triage trigger
(§8.4 line 7).

### 4.2 Build-time knob read path (DE-3 — ruling 3)

`_run_trade_job` reads, on the job thread, **before** any arm context is entered (so reads are
global-config, which is correct: build-time knobs are deliberately overlay-blind, HLD §2.1 note —
arm A's opt-out is strength-only; stated so nobody "fixes" it):

```python
# server.py, immediately before _generate_kwargs (:5644) —
from .trade_service import _c as _ts_c       # module-scope import at top of server.py
from . import negmem as _negmem

nm_map = None
if FLAGS.trade_negmem and league_id != "league_demo":
    try:
        nm_map = _negmem.build_map(
            g_user_id, league_id,
            halflife_days         = _ts_c("negmem_halflife_days"),
            min_evidence          = _ts_c("negmem_min_evidence"),
            sat_k                 = _ts_c("negmem_sat_k"),
            like_net              = _ts_c("negmem_like_net"),
            floor_b               = _ts_c("negmem_floor"),
            accept_prior_strength = _ts_c("gen2_accept_prior_strength"),
            owner_alias           = _owner_alias_map(g_league),   # §5.5; {} for sole owners
        )
    except Exception as nm_err:               # belt — build_map already never raises
        log.warning("negmem build failed hard (no stamps this job): %s", nm_err)
        nm_map = None
    if nm_map is not None:
        with _trade_jobs_lock:                # the suppression_note pattern (:5811-5814)
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["negmem_note"] = {"degraded": nm_map.degraded,
                                    "build_ms": round(nm_map.build_ms, 1),
                                    "cells": len(nm_map.cells)}
if nm_map is not None:
    _generate_kwargs["negmem"] = nm_map       # key ABSENT otherwise (C1)
```

`_owner_alias_map(g_league)` is a small server-side helper:
`{co_id: m.owner_id for m in league.members for co_id in co_owner_ids(m)}` via
`sleeper_roster` helpers (the ONE predicate — ADR-012, DE-5). Sole-owner leagues yield `{}`
(identity).

Why pass-in wins (HLD §7 tilt, confirmed; both drafts converged): `gen2_accept_prior_strength`'s
seeded default lives in `_DEFAULT_CFG` (`trade_service.py:660`) and negmem is a leaf that cannot
import it — a direct-read would force negmem to duplicate the default (stale-copy drift).
Uniformly passing ALL build knobs keeps negmem literal-free; the only DB config read in the
module is `negmem_readout(knobs=None)`'s `database.get_config()` convenience, which reads the
*seeded table*, not a copied literal (missing key ⇒ KeyError, §2). The general two-read-paths
drift surface is thereby collapsed to one path for serving and one **seeded-table** path for
offline tooling.

### 4.3 Decay — formula and worked example

Exponential half-life decay, folded event-by-event (numerically identical to per-event
`0.5^(Δdays/halflife)` weighting, but a single chronological fold is what makes the netting
clamp (§4.5) well-defined):

```
acc ← max(0.0, acc · 0.5^(max(0, t_i − t_{i−1})/H) + w_i)   # w = +1 rejection, −like_net like
n_decayed = acc · 0.5^(max(0, as_of − t_last)/H)
```

with `H = negmem_halflife_days` in days (timestamps parsed as ISO UTC; sub-day resolution kept).
The `max(0, Δ)` on every exponent is the clock-skew guard (draft B): a server clock that jumped
back between writes would otherwise make an exponent positive → a weight > 1; skewed rows count
as weight-1, never amplified.

Event ordering for the fold: sort merged events by `(ts, kind, row_id)` where `kind` orders
evidence before netting at identical timestamps (a same-instant like should net the evidence it
accompanies, not miss it); `row_id` (autoincrement on both engines) breaks same-instant ties
deterministically.

**Worked example (no likes)** — H=45, as_of = day 90, rejections at day 0, 0, 45, 80:
day 0: acc=2.0 → day 45: 2·0.5^1 + 1 = 2.0 → day 80: 2·0.5^(35/45) + 1 = 2·0.583 + 1 = 2.166
→ as_of: 2.166·0.5^(10/45) = 2.166·0.857 = **1.857**. n_raw = 4.

Rounding discipline (C5): `n_decayed` rounded 1e-9, cell `mult` 1e-6, stamp `m` 1e-4 — the
rounding absorbs any cross-platform libm-`pow` last-bit variance between the SQLite dev box and
the Postgres prod box. Determinism argument in full: (1) inputs are append-only rows filtered by
`acted_at ≤ as_of` (the `trade_pass_reasons` upsert is the R6-conceded exception); (2) event
order is a total order on `(ts, kind, row_id)` — no dict/set iteration influences any sum;
(3) IEEE-754 double ops with identical operands in identical order are bit-identical on one
platform; (4) `as_of` is captured once at build entry (`datetime.now` called exactly once) —
nothing else reads a clock. Sabotage that proves the test can fail: §10 N-14.

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
sanctioned arm pin is `negmem_strength` per D-6). Note for cross-review (OQ-4b): this curve is
deliberately *not* continuous at the threshold (mult steps 1.0 → 0.900 as `n_decayed` crosses
`min_evidence`); draft B flagged the day-to-day ordering flap as decay re-crosses the gate — the
ruling sheet pins this curve via the `negmem_sat_k` knob, and the flap hazard is recorded in §11.

**Worked examples** (floor_b=0.6, min_evidence=3, sat_k=3):

| n_decayed | n_eff | mult |
|---:|---:|---:|
| 2.9 | — | 1.000 (identity) |
| 3.0 | 1.0 | 1 − 0.4·(1/4) = **0.900** |
| 5.0 | 3.0 | 1 − 0.4·(3/6) = **0.800** |
| 9.0 | 7.0 | 1 − 0.4·(7/10) = **0.720** |
| ∞ | ∞ | → 0.600 |

**DE-1 — combine rule across a partner's family cells: MIN, not product (ruling 1).**
`partner_mult[P] = min(cells[(P, f)].mult for f in admitted families present)` (missing cell = 1.0),
precomputed at build so `effective_mult` is O(1) per call, not O(cells) inside the per-candidate
fit loop.

Why (3-row fixture table, committed as the §10 N-4 fixture):

| Row | (P, value).mult | (P, fit).mult | MIN | product | Verdict |
|---|---:|---:|---:|---:|---|
| value-only evidence | 0.80 | 1.00 | **0.80** | 0.80 | identical — no cost |
| two barely-admitted objections | 0.90 | 0.90 | **0.90** | 0.81 | product punishes 3+3 passes across *different* objections as hard as ~6 same-family passes — it compounds exactly the over-reach D-5 already concedes in the per-partner collapse (HLD §6 Residual) |
| one strong + one weak | 0.70 | 0.90 | **0.70** | 0.63 | product drives toward floor² pre-clamp; GR4 exists because soft layers must not compound into de-facto exclusion — negmem must not do internally what GR4 polices externally |

House precedent seals it: F3 fatigue takes the MIN of its keys — *"never a product — one
impression must not be triple-counted"* (`server.py:4494-4496`). The same event never
double-counts here either: one rejection has one family, but one *partner* has two families, and
MIN reads as "the strongest single standing objection governs." (Draft B's independent framing
agrees: the two families are distinct objection classes but not independent samples — a partner
at value-mult 0.8 and fit-mult 0.8 has told us two things once each, not one thing twice.) C2's
clamp invariant holds under either rule (the clamp is in `effective_mult`); MIN is chosen on
semantics, not safety.

### 4.5 Netting (DE-2 — ruling 2) — decrement, chronological fold, clamp-at-zero

- **Mechanism: DECREMENT** (not reset), by knob `negmem_like_net` (default 1.0). Reset would let
  one like erase a long, consistent, decayed record in one step — over-correcting a lock-in
  problem that decay + soft floor + min-evidence already bound (PRD §5.3, §7 risk table), and
  making the map non-smooth in a way the readout can't explain. A decrement of 1.0 is symmetric
  ("one viewed like cancels one viewed reasoned pass") and knob-tunable.
- **Target: every (P, ✱) cell** (PRD §5.3 — a like carries no reason code, so it cannot target
  one family). The same like event (weight `−like_net` at its `acted_at`) is folded into **each**
  admitted-family stream of partner P independently.
- **Bounds (the ruling notes this explicitly answers draft B's bounds question):** the fold of
  §4.3 applies `max(0.0, …)` after **every** step, in timestamp order — so (i) a cell can never
  go negative; (ii) one like erases at most `like_net` decayed units per cell — it cannot reset
  a 5-evidence cell; (iii) a like that precedes any evidence nets nothing and cannot bank credit
  against future rejections; (iv) a like older than the evidence nets less (it decays like
  everything else), a newer like nets a full unit — both directions fall out of one formula, no
  special cases. The clamp is why netting must be event-folded in the as-of domain (D-7) rather
  than subtracted at the end.
- **Like admission** (mirror of R1 minus the reason clauses): replay-surviving `like` (§5.2),
  viewed-gated, non-ghost, clean-epoch, inside the horizon, and not retracted per the §5.3
  retraction leg — likes are exactly where `retracted_at` fires in practice (awaiting-dismiss,
  memo §1.1), so the retraction check does real work here. `propose` survivors net **nothing**
  (PRD §5.3 names likes only; adding propose is scope creep — recorded, not implemented).
- Readout transparency: `likes_net` on the cell (§3.1) + a `likes` count per partner in the
  readout (PRD §5.3 "the mechanism is stamped in the readout").

**Worked example** — H=45, min_evidence=3, like_net=1.0; partner P, family `value`:
passes day 0, 0, 10; like day 20; as_of day 30.
day 0: acc=2.0 → day 10: 2·0.5^(10/45)+1 = 2.714 → day 20 (like): 2.714·0.857 − 1.0 = 1.326
→ as_of: 1.326·0.857 = **1.137** ⇒ below min_evidence ⇒ identity. Without the like: 1.994 —
still identity; a fourth pass would have crossed the threshold, which the like now delays. The
like also nets the (P, fit) cell (empty here: fold of a lone −1.0 clamps to 0, cell records
likes_net only).

### 4.6 `effective_mult` (D-10 — the ONE implementation; total function)

```python
def effective_mult(nm_map, partner_league_id, *, strength, floor) -> float:
    if nm_map is None or nm_map.degraded:      # degraded ⇒ identity, even slow-but-valid
        return 1.0
    mult = nm_map.partner_mult.get(partner_league_id, 1.0)
    if mult >= 1.0:
        return 1.0
    s = float(strength)
    if s != s:                                  # NaN strength — treat as kill, not poison
        return 1.0
    if s <= 0.0:
        return 1.0                              # structural short-circuit (D-6)
    f = min(max(float(floor), 0.0), 1.0)        # sanitize a bad knob read
    return round(min(1.0, max(f, 1.0 + s * (mult - 1.0))), 6)
```

Exactly the HLD D-6 formula `eff = clamp(1 + strength·(mult−1), floor, 1.0)` — verified against
the HLD wording (§2.1, D-10). Pure: no config, no defaults, no I/O; `degraded` is **data on the
map**, so branching on it does not violate D-10 — centralizing it here is what makes "seams
treat a degraded map as identity" a one-line invariant instead of a per-seam convention (the
`eff != 1.0` *skip* stays seam-side as the HLD specifies). Sink-never-rise is structural
(`mult ≤ 1` and the `min(1.0, …)`); C2's invariants are tested against this single function
(§10 N-5).

Behavior table (total-function inputs, draft B):

| input | eff | why safe |
|---|---|---|
| `strength = 0` | exactly 1.0 (short-circuited, no float artifact), and the seam skip fires — no multiply, no round | C1 |
| `strength = 1` | `m` clamped | the intended live setting |
| `strength > 1` | extrapolates below `m`, **clamped at floor** — an operator over-crank cannot exceed the floor | D-6 clamp is the authority |
| `strength < 0` | 1.0 (short-circuit) — sink-never-rise survives a negative knob | C2 |
| `floor > 1.0` (misconfig) | sanitized to 1.0 ⇒ eff = 1.0 | clamp args never invert |
| NaN strength | 1.0 | NaN propagating into every composite_score is the alternative |
| unknown partner / empty cells | 1.0 before any arithmetic | new league-mate = identity |

Worked: mult 0.8 → strength 0.5 ⇒ 0.9; strength 1 ⇒ 0.8; strength 2 ⇒ clamp(0.6) = 0.6.

### 4.7 Read horizon

`horizon_floor_day = max(NEGMEM_CLEAN_EPOCH_DAY, (as_of − 4·halflife_days).date())` as
`YYYY-MM-DD` — applied **in-query** as a day-prefix bound (§5.1). At default H=45 the window
caps at 180d; evidence older than four half-lives contributes < 6.25% of an event — below the
shrinkage floor's resolution (HLD §3.1). Day-granularity is deliberately conservative by at most
one day of *extra* rows — never one day short, because `>=` on the day prefix admits the whole
boundary day. The M2 aggregation carries its own 180d lookback (R5), independent of H,
enforced in the Python fold (§5.4).

---

## 5. SQL & admission — the ONE implementation pair (DE-4)

### 5.1 Dialect decision + the spine fetch

House constraints (verified): `analytics_queries.py:8-12` is the binding precedent — **no
`json_extract`/`->>`, no dialect date functions; day bucket = `substr(col,1,10)`; JSON parsed in
Python; window bounds compare the DATE PREFIX against `YYYY-MM-DD` binds** — never a
`Z`-suffixed instant against the stored `+00:00` text (all timestamps in this table family are
ISO strings written by `datetime.now(timezone.utc).isoformat()`, e.g. `database.py:5542`,
`server.py:4115`). `features_json` is a Text column (`database.py:507`) and **no existing SQL
extracts JSON fields from it**; SQLite `json1` vs Postgres `jsonb` operators differ enough that
dual-dialect extraction means two SQL texts kept in sync forever — exactly the drift class the
ONE-implementation rule exists to kill.

So the SQL does only what both dialects do identically — equality binds, day-prefix bounds on
ISO text, index-served joins. Family mapping, viewed-gating, ghost checks, undo replay, epoch
checks, retraction, and decay all run in Python from one fetched row set. **The fetch SQL + the
Python predicate are the one shared implementation pair** (draft A's shared-fragment discipline
kept, per ruling 4): builder, readout, and RFPS all call `load_admitted_events()` /
`_admit_events()` — nobody re-implements.

```sql
-- negmem._SPINE_SQL (params :uid :lid :horizon_day)
SELECT di.impression_id,
       di.served_at,            -- ISO text, NOT NULL (database.py:513)
       di.features_json,        -- Text, nullable → Python-parsed, §5.2
       di.is_ghost,             -- Integer, NULL on pre-telemetry rows
       di.assets_json,          -- Text, NULL while telemetry off (§5.3 leg)
       di.shape_bucket,         -- recorded on evidence rows (PRD §2.2)
       di.trade_intent,         -- R11 context tag (COLUMN, not features key)
       o.id       AS outcome_id,
       o.action,                -- NOT NULL, closed enum (database.py:5531)
       o.acted_at,              -- ISO text, NOT NULL
       r.reason,                -- 'value'|'fit'|'other'|NULL (no reason row)
       r.detail,
       r.key_source             -- 'impression'|'local'|NULL
FROM deck_impressions di
JOIN deck_outcomes o        ON o.impression_id = di.impression_id
LEFT JOIN trade_pass_reasons r ON r.impression_id = di.impression_id
WHERE di.user_id = :uid
  AND di.league_id = :lid
  AND substr(di.served_at, 1, 10) >= :horizon_day
```

- **Off-by-one check:** clean epoch is "`served_at` ≥ 2026-08-20" (PRD R1(e));
  `substr(...) >= '2026-08-20'` includes 2026-08-20 exactly. D-091 (08-16→08-19) is excluded
  structurally because the floor never goes below `'2026-08-20'` — no separate NOT-BETWEEN
  clause to get wrong.
- **Index path:** outer filter on `ix_deck_impressions_user_league` (`database.py:610`), join on
  `ix_deck_outcomes_impression` (`database.py:758`), reason PK join. Same plan class on both
  engines; no SQL `ORDER BY` (ordering is Python's job — SQL sorts differ in NULL/collation
  corners across engines for zero benefit).
- **`LEFT JOIN` fan-out check:** `trade_pass_reasons.impression_id` is the PK — at most one
  reason row per impression, so the join cannot duplicate outcome rows.
- **Result-set shape:** one row per outcome event. `viewed`, `like`, `pass`, `not_interested`,
  `propose`, `undo` all arrive; Python partitions them.
- Unknown future layer-2 `detail` codes need no handling: `r.reason` IS the layer-1 family
  (`database.py:894-902`), so R2's "unknown codes map to their layer-1 family" is satisfied by
  construction.

### 5.2 The Python predicate — per-impression replay + the closed list

`_admit_events(rows, *, as_of_dt, retracted_keys, owner_alias) ->
(evidence: list, netting: list, parse_errors: int)`.

**Undo pairing = per-impression replay.** Group fetched rows by `impression_id`; within a
group, order outcome rows by `(acted_at, outcome_id)` ascending (`acted_at` is server-clock ISO
text, identical format every row, lexicographic = chronological; `outcome_id` breaks
same-instant ties deterministically). Drop rows with `acted_at > as_of` (as-of reconstruction,
R6). Then:

```python
stack: list[str] = []                  # surviving decision-class actions, in order
viewed = False
for action in ordered_actions:
    if action == "viewed":  viewed = True
    elif action in _DECISION_ACTIONS:  stack.append(action)
    elif action == "undo":
        if stack: stack.pop()          # undo negates the MOST RECENT surviving decision
        # else: stray undo — no-op (late/duplicate labels are legal, database.py:743)
final = stack[-1] if stack else None   # ONE net disposition per impression
```

Edge cases, each with its ruling:

- **Multiple undos** — each pops one decision; extra undos are no-ops. pass→undo→pass→undo nets
  to None. Deterministic for any row multiset.
- **Duplicate labels** (two `pass` rows, legal per `database.py:743`) — the stack holds both;
  one undo removes one. Final disposition is the last survivor; the impression still contributes
  **at most one** evidence or netting unit (impression-keyed) — dup rows can never double-count
  a cell.
- **`pass` then `like` with no undo** (data-legal even if UI-improbable) — last survivor wins:
  the impression is a netting like, not evidence.
- **Undo arriving after `as_of`** — invisible to this build by the `acted_at ≤ as_of` cut; a
  later build sees it and the cell moves. That is R6's definition, not a bug.
- **`viewed` ordering** — the viewed gate is "a viewed row exists with `acted_at ≤ as_of`", NOT
  "viewed precedes the decision": the client fires `deck_card_viewed` through the batched events
  side-channel (`server.py:8088-8107`) and it can land after the swipe row. Requiring precedence
  would drop legitimate evidence on a delivery race.

**The closed admission list (R1(a)–(e)) as executed checks.** An impression contributes
**evidence** `(partner, family)` iff ALL of:

(a) `viewed` is True; (b) `final in {"pass","not_interested"}` and a reason row exists with
`key_source == 'impression'` and `reason in NEGMEM_ADMITTED_FAMILIES` — `family = reason`
(layer-1 column directly; `reason` NULL or `'other'` ⇒ not admitted; `key_source='local'` ⇒
not admitted, no spine join); (c) `is_ghost` is NULL or ≠ 1 (Integer nullable — the `!= 1`
form treats NULL as not-ghost, matching pre-telemetry rows); (d) not retracted: the replay
survived (that IS the undo half) AND its asset key ∉ `retracted_keys` when `assets_json`
parses (§5.3); (e) epoch + horizon: enforced by the SQL bound (§5.1) — no second Python check
to drift.

`partner` = `features_json["partner_user_id"]` (global platform id, memo §2e) passed through
`owner_alias` (DE-5); NULL/missing partner ⇒ row skipped, counted in `parse_errors` (a
partnerless card cannot key a partner-keyed prior). The requesting user's own id is
canonicalized the same way before the `partner != user` guard. `evidence.ts` = the **`acted_at`
of the last surviving decision row** (the decision is the evidence event, not the serve — decay
must age the rejection, not the impression). Context tags (R11, recorded-not-consulted):
`lane`, `user_value_basis` from `features_json`; `trade_intent` from the COLUMN
(NULL-expected per R11; the readout annotates, never errors). A `value` family row with
`user_value_basis == 'personal'` gets `context_tags["basis_note"] = "board-fit"` (R2/taxonomy
§2.6) — a tag, not a family change (re-keying personal-basis value evidence into `fit` would
silently merge two objection classes under the MIN-combine and is deliberately not done).

An impression contributes **netting** iff: viewed, `final == "like"`, non-ghost, in-epoch, and
not retracted (§5.3). Reason row not required (likes carry none). `ts` = the like row's
`acted_at`. `propose` survivors contribute nothing.

Per-impression dedupe is structural in the replay (one net disposition per impression) —
append-only `deck_outcomes` permits duplicate labels (`database.py:5525-5532` docstring), and
the replay collapses them.

### 5.3 R1(d) — the retraction leg (`deck_outcomes` ↔ `trade_decisions`, asymmetric)

The two tables share no key (PRD R1(d) note). One batch fetch per build:

```sql
-- negmem._RETRACTED_SQL (params :uid :lid :horizon_day)
SELECT decision, give_player_ids, receive_player_ids, retracted_at, created_at
FROM trade_decisions
WHERE user_id = :uid AND league_id = :lid
  AND decision IN ('pass', 'like')
  AND retracted_at IS NOT NULL
  AND substr(created_at, 1, 10) >= :horizon_day
```

Small by construction (`retracted_at` is set in practice by awaiting-dismiss on **like** rows,
memo §1.1; retracted passes are near-nonexistent). Python builds
`retracted_keys = {(decision, frozenset(give), frozenset(receive))}`; admission drops any
evidence or netting event whose parsed `i.assets_json` (`{"give": [...], "receive": [...]}` —
`server.py:4245`; present on every clean-epoch row: the telemetry columns predate the epoch,
PRD §7 boundary (a)) matches a key of the corresponding decision class (`'pass'` for
pass/not_interested — the UI's dismiss IS `decision='pass'`, memo §1.1 — `'like'` for netting
likes). `assets_json` NULL ⇒ leg skipped for that row.

**Asymmetry, stated (PRD R1(d))**: the pass-side retraction signal is the paired `undo`
outcome, which the §5.2 replay already consumes — so no retracted-decision match for a pass
event ⇒ admit (the check passes vacuously; there is no pass-side retraction state to miss). The
like side is where `retracted_at` does real work, and the leg covers it (draft A's hazard,
carried; draft B's fetch fetched `'pass'` only and would have missed retracted likes).
Set-equality matching carries no time window — an old retracted decision over the identical
asset set would drop a later re-pass of the same package; rare, and conservative (drops
evidence, never invents it); flagged as OQ-3.

### 5.4 M2 aggregation (R5) — fetch + Python fold + feed guard

Runs inside `build_map` (D-9: one build, one as_of, one S6 envelope). **Guard first**: if
`accept_prior_strength <= 0` ⇒ `acceptance_stats = {}` — the E-B pseudo-count `m` in the memo
§2f formula IS that knob, and the guard lives in the FEED, never inside the ratified
`acceptance_prior` math (NG9, HLD §3.5). Under ruling 3 the guard fires on the job-level
**global** read (see §9 delta d for the arm-overlay interplay).

```sql
-- negmem._MATCHES_SQL (param :lid)
SELECT user_a_id, user_a_decision, user_a_decided_at,
       user_b_id, user_b_decision, user_b_decided_at,
       matched_at
FROM trade_matches
WHERE league_id = :lid
```

Column semantics verified against `database.py:417-436`: `user_a_id` = first swiper,
`user_b_id` = counterparty; `user_{a,b}_decision ∈ {'accept','decline', NULL}`;
`user_{a,b}_decided_at` String **nullable**; `status ∈ pending|accepted|declined` is derived
and deliberately NOT used (a `pending` row where one side already declined-first would be
missed by status-filtering; per-side decisions are the response events). `user_*_dismissed` is
inbox-archive only (memo §2c) — never read here; a decided decision row is the response record,
nothing re-litigates it.

Python fold (no SQL date math — the table is tiny; matches are rare):

```python
for row in rows:
    for uid, dec, dts in ((a_id, a_dec, a_ts), (b_id, b_dec, b_ts)):
        if dec not in ("accept", "decline"):    continue
        ts = _parse(dts) or _parse(matched_at)  # NULL decided_at → matched_at fallback
        if ts is None or ts > as_of_dt:          continue
        if ts < as_of_dt - timedelta(days=180):  continue   # PRD R5 lookback
        key = owner_alias.get(uid, uid)          # DE-5: id-space conversion
        acc, resp = stats.get(key, (0, 0))
        stats[key] = (acc + (dec == "accept"), resp + 1)
```

Post-fold: drop keys that map to no league member (counted —
`dropped_unmapped_partner_ids`, the memo's id-space check: `trade_matches.user_a/b_id` vs
league member space), drop the requesting user. Result:
`{partner: (int(accepts), int(responses))}` — **tuple order (accepts, responses), per code**
(`trade_gen_v2.py:305`; §9 delta a).

- **The fold never emits zero-response keys** (structurally: a key exists only via `resp + 1`)
  — HLD §3.5 guard half. At n=0 a partner is simply absent and `acceptance_prior` returns
  exactly `p0` (`trade_gen_v2.py:303-304`). Empty table ⇒ zero rows ⇒ `{}` on both engines (no
  aggregate SQL, so no SQLite-`SUM`-returns-NULL vs Postgres divergence to reconcile — the bug
  class the Python fold avoids outright); `{}` ⇒ uniform `p0` (C4's explicit empty case; S4
  expected-null: with the decline route having essentially never fired, memo §2c/§8, `stats`
  will be near-empty — a uniform read is annotated expected, not a bug).
- **Why the id conversion is load-bearing (draft B's hazard):** `trade_matches.user_{a,b}_id`
  come from `trade_decisions.user_id` = session account-side platform ids; a co-owner's id is
  NOT the roster's canonical `owner_id`, while gen_v2 looks up
  `acceptance_stats[member.user_id]` = canonical owner ids. Without conversion a co-owner's
  responses silently vanish (dict miss → global prior — no error, wrong data).
- 0/0 cannot reach `acceptance_prior`: a partner with responses ≥ 1 divides by
  `responses + m ≥ 1` even at `m = 0`; the `accepts ≤ responses` clamp already exists (`:307`).

### 5.5 The ratified E-B math (REPRODUCED from memo §2f — not modified)

```python
p = (accepts + m·p0) / (responses + m)   # m = gen2_accept_prior_strength (10.0)
                                         # p0 = gen2_accept_global_prior (0.5)
```

`acceptance_prior` (`trade_gen_v2.py:283-308`) is not edited in any way. C4 parity (§10 N-15)
pins feed × function against hand-computed values at both call sites, including empty-table.

### 5.6 The bulk read, assembled + perf math (S6)

`build_map` issues, in order: (1) `_SPINE_SQL`, (2) `_RETRACTED_SQL`, (3) `_MATCHES_SQL` — all
on `database.engine` (product path; WAL/busy_timeout set, `database.py:79-87`), each in its own
short-lived `engine.connect()` — **no long transaction**: consistency-within-job comes from
building once per job (H-3), not snapshot isolation; holding a read txn across three queries on
SQLite WAL would pin the WAL for the duration for no benefit. (`league_members` is NOT read here
— the alias map arrives injected, DE-5.)

Perf math (draft B, carried per ruling 4): worst-case spine rows at 10× current volume ≈
10k–40k in the 180-day cap. Two costs dominate: row fetch (~1–3 µs/row → ≤120 ms worst case,
but the league-scoped index makes the realistic case ≤3k rows ≪ 10 ms) and `json.loads` of
`features_json` (~5–15 µs at its ~500–900 byte size). **Mitigation that keeps the ceiling:**
`features_json` is parsed **only** for impressions that survive the cheap pre-filters
(decision-class survivor, reason-family admitted OR netting-like) — bounded by ~120 clean
reason rows/week × 26 weeks ≈ 3.1k parses ≈ 30–50 ms at 10×. Total worst-case ≈ **150 ms
against the 250 ms ceiling**; measured p95 is the real gate (S6), and any build over
`NEGMEM_DEGRADE_MS` (500 ms = 2× ceiling) is marked degraded — **discarded by design**
(§4.6 returns 1.0, `m2_feed()` returns `{}`), not just stamped. One honest tail note:
`SELECT di.features_json` transfers the text for every spine row even when Python won't parse
it — at 40k × ~700 B ≈ 28 MB worst case that is transfer, not parse, and it is the 10× tail;
if S6 shows it, the surgical fix is a **two-pass fetch** (ids first, features for admitted ids
via chunked `IN`, 500 ids/chunk, both dialects) — the first knob to turn, not built
speculatively. If S6 measures a breach at 10×, the HLD §5.4 materialized-cache fallback
triggers (same builder, `negmem_cells` cache, its own scope block); **nothing in this LLD may
be "optimized" into a second source of truth first.**

Budget: p95 ≤ 2× the fatigue read's measured p95, absolute ceiling 250ms
(`NEGMEM_BUILD_BUDGET_MS`); `build_ms` is wall-clock around all reads + the fold; the
`negmem build_ms=` log line is the S6 timing source. Tighten-only: this LLD may lower these
numbers after measurement, never raise them silently (HLD §3.1).

---

## 6. Seam diffs (insertion points + pseudodiffs)

### 6.1 Server: build + threading (D-3)

Insertion: after the R4 exclusion build (`server.py:5498-5505`), immediately before
`_generate_kwargs` (`:5644`); the build block is §4.2 verbatim (including the conditional
`_generate_kwargs["negmem"] = nm_map` — key absent when None, C1). Both fan-out lambdas
(`:5680-5685`) and the organic call (`:5696`) inherit it via the splat — **one map, all arms**
(H-3). `_log_deck_signal_impressions` gains a `nm_map=` parameter (§6.5). The timing/note
write happens before generation, so a fan-out failure for unrelated reasons still leaves the
note on the job dict.

### 6.2 TradeService: kwarg threading + serving-stack seam

`_generate_trades_impl` (`:3899`): new kwarg `negmem=None`, documented alongside
`exclusion_keys` (`:3951-3956`). **No `self._negmem` attribute** (§2.1). Threaded directly:
`_generate_trades_v2(negmem_map=negmem, ...)` and into `v2_kwargs` for
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
+            if negmem_map is not None:
+                _eff = _negmem.effective_mult(negmem_map, member.user_id,
+                                              strength=_c("negmem_strength"),
+                                              floor=_c("negmem_floor"))
+                if _eff != 1.0:
+                    _stamp = _negmem.stamp_payload(negmem_map, member.user_id, _eff)
+                    for c in cards:
+                        c.negmem_stamp = _stamp               # B2: consult-time, rides the card
+                        c.composite_score = round(c.composite_score * _eff, 3)
```

(`from . import negmem as _negmem` at trade_service module top — module import + attribute
call, T1. The 3-dp round matches every neighbor in this stack, e.g. `:5127`, `:5071`, `:5088`,
`:5104`.) `member.user_id` here is `league_members.user_id` = the canonical roster owner id
(ADR-012 keeps `league_members` single-valued on `owner_id`) — already league identity, the
same space the map keys; aliasing was needed on the *data* side (§5.2, §5.4), not at this seam.

**Once-only proof under streaming (the invariant the HLD demands proven; draft B):** each
`cards` list is created fresh per member by the pair generators (`:5021`/`:5057`/`:5059`),
passes through this block exactly once, then `new_cards.extend(cards)` (`:5200`). The streaming
callback calls `self._dedup_and_sort(new_cards)` per snapshot (`:5202-5205`) and again at final
assembly — and `_dedup_and_sort` (`:4180-4256`) **contains no score write**: it filters
(past-decision `:4192-4196`, R4 `:4197-4202`), sorts (`:4205`), and caps (C4 `:4224-4237`,
C4b `:4254`). Re-running it N times re-reads `composite_score`, never mutates it. Therefore a
card's composite is multiplied by `_eff` exactly once no matter how many snapshots fire — the
compounding failure the HLD rejected for the `_dedup_and_sort` seam (D-4) cannot occur here.

Legacy path caveat, stated (draft B): the pre-v2 loop (`:4095-4178`, `trade_engine_v2` flag
OFF) gets **no seam** — `trade_engine_v2` is ON in prod and arm A runs through the v2/v3 stack
too (`MODEL_A_PROFILE` is a knob overlay, not the legacy branch). If that flag were ever
flipped off, negmem goes silently inert on that path; recorded in §9 delta list (HLD
assumption now written down), not plumbed. `generate_asset_ideas` (`:4332`) and the likes-you
injector never consult the map — injector cards are the exempt class (§6.5).

### 6.3 gen_v2 seam + M2 feed (DE-8 — ruling 8)

`generate_league_suggestions` gains `negmem_map=None` (beside `acceptance_stats` `:862`);
`from . import negmem as _negmem` at module top (attribute call, T1). Per-pair loop
(`trade_gen_v2.py:951`):

```diff
         prior = acceptance_prior(member.user_id, acceptance_stats)
         weight = max(priority_weights.get(member.user_id, 1.0), 0.0)
+        # trade.negmem (D-4) — pair-constant M1 multiplier; distinct from the
+        # acceptance prior above (different math, same map — HLD §2.2).
+        _nm_eff, _nm_stamp = 1.0, None
+        if negmem_map is not None:
+            _nm_eff = _negmem.effective_mult(negmem_map, member.user_id,
+                                             strength=_c("negmem_strength"),
+                                             floor=_c("negmem_floor"))
+            if _nm_eff != 1.0:
+                _nm_stamp = _negmem.stamp_payload(negmem_map, member.user_id, _nm_eff)
```

…and at the pair's card build inside the same loop (where each `_Candidate` becomes a
`TradeCard`, `:999` ff.):

```diff
+            if _nm_stamp is not None:
+                card.negmem_stamp = _nm_stamp
+                card.composite_score = round(card.composite_score * _nm_eff, 4)
```

Placement rationale (draft A, verbatim, per ruling 8): the multiplier lands on the emitted
card's composite, **after** `_pair_survivors`' within-pair selection and after the pair-pool
trims — a pair-constant multiplier cannot change within-pair selection anyway, and applying at
card creation keeps `_Candidate.score`, the exposure/dedup machinery, and the MESO layer
byte-identical (membership untouched, R4). Rounding matches the module's card-build precision
(verify at implementation; 4 dp is this family's norm, `trade_gen_fit.py:442`).

**M2 feed — both call sites** (the kwarg is added ONLY when a map exists; flag-off calls are
byte-identical, C1):

`trade_service.py:4001` (flag-on branch):

```diff
             cards, _gen2_report = generate_league_suggestions(
                 ...
                 past_decision_keys=(...),
+                negmem_map=negmem,
+                **({"acceptance_stats": negmem.m2_feed()} if negmem is not None else {}),
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
`gen2_accept_prior_strength ≤ 0` (§5.4) — so "degraded ⇒ identity" covers M2 and the
strength-0 kill is structural, per HLD §3.5. Arm A never reaches this code (it is the v1/v3
engine; gen_v2 runs only as arm C / the dark flag-on path) — clean M1 comparator, no code
needed.

### 6.4 fit seam — multiply BEFORE the 1e-9 quantization (DE-9 — ruling 7)

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
+            m = (_negmem.effective_mult(negmem_map, uid,
+                                        strength=ts._c("negmem_strength"),
+                                        floor=ts._c("negmem_floor"))
+                 if negmem_map is not None else 1.0)
+            _nm_cache[uid] = m
+        return m
     candidates.sort(key=lambda c: (
-        -round(c["aggregate_raw"], 9), -c["fairness"],
+        -round(c["aggregate_raw"] * _nm_eff(c["member"].user_id), 9), -c["fairness"],
         (c["member"].user_id, tuple(sorted(c["give_ids"])),
          tuple(sorted(c["recv_ids"])))))
```

Why the order is load-bearing (draft B's proof, folded in): the C7c plateau ties are
same-partner (`aggregate_raw` mirrored-tanh sums equal up to ~1e-13, `:385-388`), so both tied
candidates carry the SAME `eff` — the scaled noise is ~1e-13·eff < 0.5e-9 and the round still
collapses them onto one quantum; the deterministic tie-break survives. Multiplying **after**
the round would compare unquantized products and let float noise outrank the tie-break — the
review-blocking bug the order exists to prevent. Sort-lambda cost: dict-get per comparison over
≤ `fit_max_packages_per_pair` × pairs candidates — same shape as the existing lambda, no
measurable delta.

Card build (`:442` region) — `composite_score = round(c["aggregate_raw"], 4)` is **unchanged**
(ordering only; fit's aggregate is a published diagnostic); the stamp still rides so influence
is observable and the GR4 joint computable:

```diff
         card.need_fit = ts.need_fit_score(...)
+        if _nm_eff(member.user_id) != 1.0:
+            card.negmem_stamp = _negmem.stamp_payload(
+                negmem_map, member.user_id, _nm_eff(member.user_id))
         cards.append(card)
```

**Fragility, named (HLD §2.2) — the end-to-end pin:** fit's negmem effect lives only in list
order, and `composite_score` is pure — so any downstream composite re-sort erases it. The
bake-off's protection is `restore_order` (`bakeoff_runner.py:1415-1429`, called
`server.py:5765-5767` after the likes-you injector's re-sort, restoring every arm card to its
interleaved index by `id()`) plus Channel 2's re-ranker bypass (`server.py:5890-5893`, `:5843`,
`:5866`). §10 N-17 asserts the ordering end-to-end through that path: a fixture where negmem
swaps two fit cards' ranks must show the swap in the FINAL served deck after injection — this
dependency is load-bearing, not incidental. On bake-off decks `final_score` falls back to base
(`server.py:4229`, rerankers bypassed), so fit's GR4 joint equals `m` exactly — uniform with
HLD §5.3.

### 6.5 Features-assembly stamp (B2 + the trichotomy; DE-10 — ruling 6, copy-only)

`_log_deck_signal_impressions` gains `nm_map=None`; insertion directly after the base
`features = {...}` dict closes (`server.py:4160`), before the flag-gated additive keys — so the
key exists on **every** row the job writes (served AND ghost: the `entries` loop `:4120-4122`
covers both — including ghost rows should the disabled holdout ever return), in every arm,
whenever `nm_map is not None`:

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

Precedence rule, stated: a consult-time stamp on the card **always rides** (provenance, B2);
the `exempt` default applies only to cards with no consult site — likes-you *injections* (built
by the injector, which has no seam — R4 exemption). An organic card the injector merely boosted
was consulted at generation before its like status was known; its real stamp is the honest
record. **No `effective_mult` call, no `_c` read exists in assembly** — the recompute is the
named sabotage of §10 N-10 (draft B's T-12 sabotage, per ruling 6). Inside `features_json` (one
Text column, always present) the executemany first-row-keys trap cannot drop it — the
fit/fit_diag argument (`server.py:4197-4204`) verbatim.

`nm_map is None` (flag off OR not allowlisted OR hard build failure §6.1) ⇒ the key never
appears anywhere ⇒ features_json byte-identical (C1).

**C1 byte-identical-off proof, assembled per path (draft B §13, carried):** flag OFF ∨ not
allowlisted → map never built → `negmem` key absent from `_generate_kwargs` → `negmem=None`
default in every signature → every seam guard short-circuits before any arithmetic → no
`round()` calls, no attribute writes → `nm_map=None` at assembly → no `features_json` key →
M2 kwarg absent at both call sites. Byte-identical in full. `negmem_strength = 0`:
`effective_mult` returns exactly 1.0, seams skip (no multiply, no round), stamps follow the
trichotomy (`{m:1.0}` on every row — the deliberate HLD strengthening over PRD R7,
golden-tested against stamp-inclusive fixtures); the ONE exception: arm C may still differ via
the M2 feed, which `negmem_strength` does not govern — its kill is
`gen2_accept_prior_strength = 0`, and golden (b) sets BOTH.

---

## 7. Observability: readout, SQL pack, RFPS artifact

### 7.1 `negmem_readout` output format (R8 — function/script, no route; ruling 11)

```python
{
  "user_id": ..., "league_id": ..., "as_of": ..., "ver": 1,
  "allowlisted": true,                               # reported as DATA — the builder runs
                                                     # with the allowlist check bypassed, so
                                                     # "why no stamps in league X" is
                                                     # answerable (draft B; a readout that
                                                     # returns None there is a tautology)
  "degraded": false, "build_ms": 41.2, "parse_errors": 0,
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
dict is the substance of the operator TestFlight checklist (§8.5) — the checklist's expected
values are readout fields, so the operator verifies runtime behavior against numbers, not
vibes. Exposure as a CRON-authed admin route is deliberately out of v1 (OQ-5).

### 7.2 Stamp-rate tripwire SQL (allowlist-scoped denominator)

Added to the readout pack as `negmem-stamp-rate.sql` (shipped in this folder; the pack runner
substitutes the allowlist from `load_negmem_league_allowlist()` — the SAME loader as the build,
so a partial rollout can never read as build failures):

```sql
SELECT substr(i.served_at, 1, 10) AS day,
       COALESCE(i.model_arm, 'organic') AS arm,
       COUNT(*) AS rows_,
       SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END) AS stamped,
       ROUND(1.0 * SUM(CASE WHEN i.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END)
             / COUNT(*), 4) AS stamp_rate          -- expected 1.0000 while flag ON
  FROM deck_impressions i
 WHERE substr(i.served_at, 1, 10) >= :flag_on_day
   AND i.league_id IN ({allowlist})                 -- ALLOWLIST-SCOPED (HLD §7)
 GROUP BY 1, 2 ORDER BY 1, 2;
```

The `LIKE '%"negmem"%'` probe is deliberate: dual-dialect (no JSON operator), and the key
string cannot appear inside any value we write — no free text enters `features_json` (the one
free-text field in this family is quarantined in `trade_pass_reasons.free_text`,
`database.py:903-905`), and the substring includes the JSON quoting. The pack's Postgres
variant may use `features_json::jsonb ? 'negmem'`; both forms ship, SQLite form is normative.

### 7.3 GR4 joint-multiplier audit (DE-6)

Definition (round-3 requirements honored):

```
joint(row) = negmem_m(row) × final_score / base_score        -- non-bake-off rows only
```

- `negmem_m` = `features_json.negmem.m`.
- **The ratio EXCLUDES negmem's own multiply on the score-multiplied paths by construction**:
  `base_score` is `card.composite_score` at logging (`server.py:4213`), which on the serving and
  gen_v2 paths already CONTAINS m (§6.2/§6.3 multiply composite at generation) — so
  `final/base` is purely the post-generation ordering stack (Thompson × fatigue × taste ×
  diversity) and `joint` counts m exactly once, never m². On fit rows composite is pure (§6.4)
  and on bake-off decks `final == base`, so joint = m — the same formula is uniform.
- **Thompson layer, named**: the Thompson draw multiplier folds into the ordering key that
  becomes `final_score` — it enters the joint **via the ratio**; the `propensity` column
  (`database.py:508`, which records the same draw) is **not** multiplied in again (that would
  double-count) and remains separately recoverable for isolation.
- Pollution accepted (DE-6): A6 diversity penalties and session demotions also ride
  `final/base`, pushing `joint` DOWN — i.e. toward a false trip of the 0.15 bar, the safe
  direction. Margin math (draft B): four layers at their floors — 0.6 × 0.7 × 0.25 × 0.5 =
  0.0525 — is the theoretical worst without negmem even firing; GR4's job is trend detection.
  If p5 approaches 0.15, the runbook's first question is ratio pollution (§8.4); stamping
  `fatigue_m`/`taste_m` under the same uniformity rule is the P2-shaped escalation, not built
  now.
- Pack query `negmem-gr4-joint.sql`: select `negmem_m`, `base_score`, `final_score` for
  allowlisted, flag-era, non-bake-off (`model_arm IS NULL`), `base_score > 0` rows; the runner
  computes p5 in Python (SQLite has no percentile function). Trip: `p5(joint) < 0.15` ⇒ raise
  floors (GR4).

### 7.4 RFPS (§4.2 PRD) — metric SQL + the R-X frozen-cohort artifact

Computation (offline, `backend/scripts/negmem_rfps.py`, imports `backend.negmem` — one-off
operator script per house convention):

1. Cohort: all **viewed** pass/`not_interested` outcomes in the window for allowlisted leagues
   (viewed-gate, ghost-exclusion, clean-epoch — the same closed-list clauses via
   `load_admitted_events`; RFPS additionally needs reason-LESS rejections per the
   pre-registered numerator rule, so the reason requirement is relaxed for cohort membership
   only — the admission implementation is still the one shared code path).
2. For each outcome, rebuild the map **as-of `served_at`** (the builder is a pure function of
   (user, league, as_of) — C5; same Python, guaranteeing metric/map agreement) and record the
   card's partner cells.
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
  "id_mapping": "features_json.partner_user_id (global platform id) -> canonical league owner_id via the server-built owner_alias over league members (ADR-012, injected per DE-5); inline alias_map below is the mapping OF RECORD for this cohort",
  "alias_map": {"<global_id>": "<league_owner_id>"},
  "admission_ver": 1,
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

### 8.1 Error contract table (failure taxonomy)

| Failure | Behavior | Visible as |
|---|---|---|
| League not allowlisted | `build_map` → `None`; no kwarg effect, **no stamps** | indistinguishable from flag-off (by design) |
| Allowlist file missing / unparseable / wrong shape | empty allowlist (⇒ None everywhere) + warning log | log line; stamp-rate pack uses the same loader so no false alarm — but the denominator goes to zero rather than alarming; "denominator empty" is itself a runbook triage trigger (§8.4 line 7) |
| `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` | **propagate** — `except Exception` does not catch `BaseException` subclasses | never swallow interpreter shutdown |
| Any `Exception` inside `build_map` (DB down, SQL error; `MemoryError` included*) | caught internally → degraded identity map (`cells={}`, `acceptance_stats={}`, `degraded=True`); **never raises** (F3 precedent `server.py:4499-4503`) | `{m:1.0, degraded:true}` on every row; `j["negmem_note"]` |
| Slow-but-valid build (`build_ms > 500ms` = `NEGMEM_DEGRADE_MS`) | map marked degraded — **discarded by design**, not just stamped: `effective_mult` → 1.0, `m2_feed()` → `{}` (the cells are gone to every consumer) | same as above + `build_ms` in the note |
| One row's `features_json`/`assets_json`/timestamp unparseable | skip the row, `parse_errors += 1` (surfaced in readout + job note) — a single corrupt row must not zero a league's memory | readout counter |
| `trade_matches` read raises | whole map degraded (single degraded bit — no partial-degrade state machine; M1-healthy-M2-degraded would need its own stamp vocabulary for zero operational value) | one bit, one triage path |
| Hard failure in the server wrapper (belt) | `nm_map = None` + warning | stamp ABSENCE while flag ON + allowlisted = the §8.4 tripwire |
| `effective_mult` edge inputs | None/degraded/unknown partner/strength≤0/NaN ⇒ exactly 1.0; never raises (§4.6 total-function table) | — |
| Degenerate knob values (zero/negative halflife, floor>1, …) | sanitized once at `build_map` entry (§2) — near-instant decay / always-on gate, both safe, both visible in the readout | readout knobs block |
| M2 partner id unmapped to league member | dropped + counted (`dropped_unmapped_partner_ids`) | readout counter |
| Assembly stamping raises | already inside the impression-logging try/except (non-fatal by existing contract) | no new path |
| `negmem_readout` with missing seed rows | `KeyError` with remediation text (operator tool — loud is correct) | script failure |
| Job death | **never for negmem** (C1/NG1): every path above degrades to identity | — |

*`MemoryError` → degraded is accepted: fail-open is the ruling posture (C1/NG1 — identity is
always a legal output), and the 500 ms discard bounds the damage window.

**Concurrency statement (draft B, carried):** job workers are daemon threads; a session's
`TradeService` is shared across its jobs. Negmem adds **zero shared mutable state**: no module
global (T1), no instance attribute (§2.1), a frozen map passed by argument, and thread-local
`_c` reads at seams. The only cross-thread writes are the job-dict note (under
`_trade_jobs_lock`, existing discipline) and log lines. A concurrent same-session job builds
its own map from its own reads — mixed-map decks are impossible by construction, not by
convention. Re-entrant streaming callbacks touch only `new_cards`/`_dedup_and_sort` (§6.2
proof).

### 8.2 Edge cases (PRD §5.3, pinned to mechanisms)

- Empty league / no evidence → zero cells → `partner_mult` empty → every consult 1.0 → every
  row `{m: 1.0}` (flag ON). New league-mate → identity until min-evidence.
- Duplicate/late outcome labels → per-impression replay collapses them (§5.2).
- Reason lateness (H-1) → `as_of` = build time; builder/readout/RFPS share the one admission
  implementation, so they can never disagree about the same instant.
- Reason upsert hop (H-2) → conceded per R6; RFPS contained by the frozen cohort (§7.4).
- Concurrent same-session jobs (H-4) → kwarg-only threading, no shared slot (§2.1, §8.1).
- Mid-week taxonomy extension → layer-1 column routing (§5.1 note).
- Co-owned rosters → injected `owner_alias` (§5.4/§5.5).
- Clock skew between rows → decay exponents clamped ≥ 0 (§4.3).
- Deleted user data → derive-on-read: deleting spine rows IS deleting the memory (D3(c)).
- Likes-you injections → exempt stamp (§6.5); boosted organic cards keep their real stamp.
- Ghost rows → excluded as *evidence* (R1(c)); still *stamped* like every row the job writes
  (HLD §3.4 wording — moot while the holdout is operator-ruled off, covered regardless).

### 8.3 Backcompat & migration

- **Schema:** none (NG6 — zero tables, zero columns; nothing for `_migrate_db()`). The stamp is
  a JSON key inside an existing Text column; old rows simply lack it (and pre-flag rows are
  outside every flag-era query window). The `negmem_` table-name prefix stays reserved-unspent
  unless §5.6's measured failure triggers the HLD §5.4 cache (its own scope block then).
- **Knobs:** seeded via `INSERT OR IGNORE` (`database.py:2186-2188` mechanism) — existing DBs
  pick them up on next boot; `PUT /api/admin/config/<key>` hot-applies (re-runs
  `reload_config()`).
- **Flag:** default False in code; ships dark. Byte-identical-off is C1's golden set, per path
  (§6.5 proof).
- **Rollback ladder** (all deploy-free, nothing left behind — derive-on-read):
  `trade.negmem` off (everything incl. M2) → `negmem_strength = 0` (M1 inert; M2 still feeds —
  its own kill is `gen2_accept_prior_strength = 0`; map still builds for readout/stamps) →
  `negmem_floor = 1.0` (clamp to identity; diagnostic posture, stamps keep flowing with m=1.0).
- **Downgrade note (documented divergence):** PRD R10's "0 = byte-identical disable"
  parenthetical is M1-SCOPED after the round-3 decision (HLD §5.3) — carried into
  `docs/config-reference.md` wording.
- **Rollout order** (PRD §6 severability respected): P0 = M2 feed (§5.4/§6.3) + harness +
  its goldens ⇒ mergeable alone behind the flag; P1 = builder + seams + stamps + readout +
  knobs + goldens. Dark (flag off, goldens green) → operator flips at a round boundary →
  allowlist the pilot league → ≥4-week read → §8.3 graduation.
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
   NEVER an arm overlay pin — arm overlays are bake-off instruments, not kill switches, and the
   feed guard fires on the job-level GLOBAL read (§5.4), so only the global knob verifiably
   empties the feed; a per-arm pin with a nonzero global leaves the feed populated and
   `acceptance_prior` computing the raw unshrunk ratio (the guard lives in the feed, NG9)."*
   (Wording status: §9 delta d — final re-word owed at finalization.)
5. *"`trade.negmem` flag flips and every `negmem_*` / `gen2_accept_prior_*` knob move land at
   bake-off ROUND BOUNDARIES only (GR3; a mid-round flip censors the window — ADR-014)."*
6. *"GR4: p5 of (negmem_m × final_score/base_score) on allowlisted non-bake-off rows < 0.15 ⇒
   raise floors; first check the known downward pollution (diversity penalty in the ratio)
   before concluding real compounding."*
7. *"negmem stamp-rate query returns ZERO rows (empty denominator) while the flag is ON ⇒ the
   allowlist file is missing/unparseable or empty — check the build warning log and the
   readout's `allowlisted` field before assuming build failures."*

### 8.5 Operator TestFlight checklist (D-056 — the runtime evidence mobile gets)

Concrete steps, built on the readout:

1. Before the round-boundary flip: run `negmem_readout` for your league; confirm cells match
   your remembered pass history (partners you've repeatedly reasoned-passed show `n_raw > 0`)
   and `allowlisted` reads true after the allowlist edit.
2. After the flip, generate a deck; in the readout confirm `degraded: false`,
   `parse_errors: 0`, and `build_ms < 250`.
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

## 9. HLD deltas (for the reconciliation log)

Four discrepancies between this LLD and the FINAL HLD, found while implementing on paper —
flagged here, resolved per the orchestrator's rulings, owed to the reconciliation log at
finalization:

- **(a) `acceptance_stats` tuple order — THE CODE WINS.** HLD §2.1 writes
  `{partner: (responses, accepts)}`; the ratified consumer unpacks
  `accepts, responses = acceptance_stats[user_id]` (`trade_gen_v2.py:305`), and the memo §2f
  interface `uid → (accepts, responses)` agrees. This LLD follows the code —
  **(accepts, responses)** — and treats the HLD line as a transcription slip. Sabotage-pinned:
  §10 N-15's named sabotage is exactly the tuple flip.
- **(b) §2.1-vs-§7 build-knob read contradiction — resolved by ruling 3 (pass-in).** The HLD
  component diagram says build-time knobs are "read ONCE here, globally" *inside* `build_map`,
  while §7 tilts the read path to pass-in-from-server; these cannot both be literal. This LLD
  implements pass-in for ALL build knobs including `gen2_accept_prior_strength` (§4.2) — the
  only reading consistent with D-2's leaf import list — and records that §2.1's phrase should
  read "resolved once per job, before any arm context".
- **(c) Co-owner canonicalization is impossible inside the leaf — resolved by injection
  (ruling 5).** HLD §7 hands this LLD "co-owner canonicalization call sites" but D-2's import
  list forbids the module that owns the predicate (`sleeper_roster`). The server builds
  `owner_alias` from the in-hand league object and passes it into `build_map` (§4.2, §5.5) —
  the ADR-012 predicate stays single-sourced, and D-2's import list needs no amendment.
- **(d) §5.3 "kill M2 via the GLOBAL knob only" — PROCEDURE kept; rationale superseded by the
  feed-guard (draft B's finding); re-word owed at finalization.** The rule is retained verbatim
  as operational procedure (runbook line 4: arm overlays are bake-off instruments, not kill
  switches). Draft B established that a *feed-side* guard structurally addresses the
  raw-unshrunk-ratio failure the HLD's rationale feared; under the merged design the guard
  fires on the job-level global read (ruling 3), which is precisely why the global knob is the
  only rung that verifiably empties the feed — so the procedure is load-bearing, and the HLD's
  stated rationale needs re-wording, not the rule. Final wording assigned to the
  reconciliation log.

Also recorded (assumption made explicit, no ruling needed): the legacy pre-v2 serving loop
(`trade_service.py:4095-4178`, `trade_engine_v2` flag OFF) receives no seam — the HLD's seam
table assumes the v2/v3 stack is the serving engine, true in prod today (§6.2 caveat). And the
HLD §3.5 "degraded ⇒ the feed returns `{}`" is implemented exactly as written via `m2_feed()`
(§3.2); the map-absent case is implemented as kwarg-absence, strictly stronger for C1.

---

## 10. Testing (every test named; fixture shape; what it proves)

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
(2 accepts, 5 responses) including one response recorded under a co-owner alias id.
**Fixture-power rule (HLD §7)**: this world yields m < 1.0 for X on a non-A arm in-job —
N-7/N-9/N-10/N-11 all run against it, so none can pass vacuously.

Merged plan — draft A's 24 tests ∪ draft B's 20, deduplicated by intent, renumbered N-1..N-27.
Where both drafts named a sabotage for the same intent, both are listed (primary first).

| # | Test | Fixture / shape | Proves | Sabotage (RED proof) | Drafts |
|---|---|---|---|---|---|
| N-1 | `test_admission_closed_list_matrix` | the inadmissible-row matrix above, run through `_admit_events` (the ONE implementation) | each R1 clause excludes exactly its row; the SQL bound + Python predicate together are the closed list (H-1 defense) | drop the ghost clause from the predicate | A T-1 (reshaped for DE-4) |
| N-2 | `test_undo_replay_table` | unit table: pass→undo; pass→undo→pass; like→undo; stray undo; dup pass + one undo; pass→like no-undo | per-impression replay (§5.2): one net disposition; undo pops the most recent survivor | make undo pop the OLDEST decision — the pass→undo→pass case flips | B T-9 |
| N-3 | `test_decay_shrinkage_worked_examples` | §4.3/§4.4 tables as literals; a clock-skew pair (later row with earlier ts) | formulas match this doc to 1e-9; identity below min_evidence; skew exponent clamped | flip `n_eff` off-by-one | A T-2 |
| N-4 | `test_combine_rule_min` | the DE-1 3-row table | partner_mult is MIN; product regression caught | change MIN→product (0.7/0.9 partner reads 0.63) | A T-3 / B T-6 |
| N-5 | `test_effective_mult_invariants` | property sweep: mult∈[0,1], strength∈[−1,3]∪{NaN}, floor∈[0.4,1.2] (§4.6 table) | C2: eff∈[floor,1]; sink-never-rise; strength 0 ⇒ exactly 1.0; NaN/negative/floor>1 safe; pure (module engine patched to a poisoned object) | remove the upper `min(1.0, ·)` clamp — negative strength yields eff>1 | A T-4 + B T-4 |
| N-6 | `test_netting_order_clamp_bounds` | like-before-evidence; like-after; 5 evidences + 1 like (≥ 3.9 decay-adjusted); 1 evidence + 5 likes (⇒ 0.0, mult 1.0); retracted like | DE-2: chronological fold, clamp-at-zero every step, no banked credit, cells never negative, one like ≤ `like_net`/cell; retracted like nets nothing | replace fold-clamp with end-clamp (early-like banking trips the like-before-evidence case) | A T-15 + B T-5 |
| N-7 | `test_serving_golden_strength0_stamp_inclusive` | `_negmem_world`, flag ON, `negmem_strength=0`, serving path + fit fixture | golden (a): FULL byte-equality of decks **against a stamp-inclusive fixture** — every row carries `{m:1.0,"ver":1}`; deck content/scores/order identical to pre-negmem capture; also asserts the arm-A profile pin changes `snapshot_config` output but not deck bytes | make the seam round() at identity; bake strength into `build_map` cell mults (the overlay-blind read) | A T-5 + B T-2 |
| N-8 | `test_arm_c_dual_kill_golden` | `_negmem_world` bake-off job, `negmem_strength=0` ∧ `gen2_accept_prior_strength=0` | golden (b): arm-C deck byte-identical — verifies M2's structural kill AND gen_v2's M1 seam (which M2 could otherwise mask) | move the feed guard into `acceptance_prior`; remove the guard (pass stats at strength 0) | A T-6 + B T-3 |
| N-9 | `test_arm_a_rows_stamp_exactly_identity` | `_negmem_world` bake-off (fixture-power: live arm has m<1.0 in the same job) | golden (c): every `model_arm='baseline'` row stamps exactly `{m:1.0,"ver":1}` — never absence, never a live m | drop `negmem_strength` from MODEL_A_PROFILE | A T-7 |
| N-10 | `test_stamp_provenance_b2_copy_only` | consult under arm overlay with strength 1.0, then flip live `_cfg` to strength 0 BEFORE logging | B2/DE-10: assembly copies card state — the stamp still shows the consult-time m (a recompute would show 1.0) | recompute m at assembly via `effective_mult` + live `_c` (draft B's named sabotage, per ruling 6) | A T-8 + B T-12 |
| N-11 | `test_t1_sabotage_live_binding` | `_negmem_world`; monkeypatch-rebind `negmem.effective_mult` to return 0.5 | T1: fit + serving output CHANGES ⇒ live module-attribute binding, no frozen import | `from .negmem import effective_mult` at a seam | A T-9 / B T-11 |
| N-12 | `test_likes_you_led_deck_batch_stamps` | deck whose FIRST card is a likes-you injection (the model_arm scar scenario), flag ON | C3: batch-wide `negmem` key retention through `save_deck_impressions`' executemany; injection stamps `exempt`, boosted organic keeps real stamp | move the stamp outside features_json; stamp only cards with `negmem_stamp` set | A T-10 + B T-14 |
| N-13 | `test_c1_flag_off_and_unallowlisted_byte_identity` | `_negmem_world` with (i) flag OFF, (ii) flag ON + league NOT allowlisted | C1: `negmem` key absent from `_generate_kwargs`, no stamp key anywhere, features_json byte-identical; the None seam is indistinguishable from flag-off | stamp on `nm_map is None` (assembly stamps `{m:1.0}` when ctx None) | A T-11 + B T-1 |
| N-14 | `test_map_determinism_and_asof` | build twice at same as_of; permute row insert order; build at historical as_of | C5 determinism to the bit incl. insert-order independence; as-of reproducibility incl. netting events in-domain (R6) | inject `now()` into the fold (or iterate a set for the fold) | A T-12 + B T-10 |
| N-15 | `test_m2_parity_both_call_sites_incl_empty` | hand-computed E-B values; empty tables | C4: feed × `acceptance_prior` reproduces memo §2f exactly at `trade_service.py:4001` and `bakeoff_runner.py:1212`; empty ⇒ `{}` ⇒ uniform p0 (S4 expected-null) | flip the tuple to (responses, accepts) (§9 delta a pin) | A T-13 + B T-7 |
| N-16 | `test_m2_feed_guard_and_zero_response_keys` | knob ≤ 0; a partner with matches but no decisions | feed `{}` at strength ≤ 0; zero-response keys structurally absent; global-kill (not overlay) semantics documented-in-assert | emit partners with `responses=0` | A T-14 + B T-7 |
| N-17 | `test_fit_end_to_end_ordering_restore_order` | bake-off fixed-order deck, fit arm rostered, likes-you injection active; fixture where negmem swaps two fit ranks | DE-9: the fit arm's negmem ordering survives to the FINAL served deck through `restore_order` (`server.py:5766`) — the composite re-sort does not erase it | skip `restore_order` | A T-16 + B T-13 |
| N-18 | `test_fit_quantization_order` | C7c plateau pair (same partner, aggregate Δ ~1e-13) + cross-partner pair | m applied BEFORE the 1e-9 round: same-partner tie survives; cross-partner order splits by m | multiply after the round | A T-17 + B T-13 |
| N-19 | `test_degraded_and_failure_taxonomy` | (i) builder raises mid-read; (ii) valid build with build_ms forced > 500ms; (iii) KeyboardInterrupt raised in a patched reader; (iv) one corrupt features_json row | degraded map: seams identity (incl. slow-but-valid discard), stamps `{m:1.0,degraded:true}` on every row, `m2_feed() == {}`, job survives; KI propagates (`except Exception`, not BaseException); corrupt row ⇒ `parse_errors` +1, map healthy | stamp degraded but keep multiplying; catch `BaseException` | A T-18 + B T-17 |
| N-20 | `test_streaming_callback_golden` | serving path with `on_opponent_done` capturing every snapshot | strength-0 snapshots byte-identical; strength-1 snapshots multiply-once (composite == pre-capture base × m at every snapshot — `_dedup_and_sort` re-runs never compound, §6.2 proof) | multiply inside `_dedup_and_sort` | A T-19 |
| N-21 | `test_identity_hygiene_owner_alias` | co-owned league; decisions/matches recorded under the alias id; injected `owner_alias` | DE-5/R9: map + M2 keys are canonical owner ids; the co-owner's decline lands on the canonical key; alias rows fold into the owner's cells; account ids never appear as keys; `owner_alias=None` ⇒ identity | key on raw `partner_user_id` (drop `owner_alias` — stats dict misses) | A T-20 + B T-8 |
| N-22 | `test_horizon_and_epoch_day_prefix_boundaries` | one event at as_of−4H−1d, one inside; served 2026-08-20T00:00:00 (admitted) vs 2026-08-19T23:59 (not) | §4.7 horizon applied in-query (out-of-horizon rows never loaded); the day-prefix bound admits the whole boundary day and excludes D-091 structurally | filter horizon in Python instead; change the bound to full-timestamp comparison vs a 'Z' bind | A T-21 + B T-15 |
| N-23 | `test_dual_dialect_sql_compiles` | compile `_SPINE_SQL`/`_RETRACTED_SQL`/`_MATCHES_SQL` + pack SQL via `sqlalchemy.text` against the `postgresql` dialect | no accidental SQLite-only syntax, without a live PG | introduce `json_extract` into the spine | B T-15 |
| N-24 | `test_leaf_import_contract` | static assert on `negmem`'s module imports | imports ⊆ {stdlib, feature_flags, database} — no `sleeper_roster` (DE-5), no engines (D-2) | import trade_service (or sleeper_roster) in negmem | B T-16 |
| N-25 | `test_knob_and_flag_registration` | — | six knobs present in `_DEFAULT_CFG` + seed rows + `_PINNED_KNOBS` (the existing inventory test `test_bakeoff_arm_a_golden.py:545` fails by name otherwise — this test pins the negmem-specific rows and the `MODEL_A_PROFILE` pin; the profile-names-real-knobs test `:562-567` covers deletion drift); `trade.negmem` in FLAG_KEYS; release.json mirror test already enforces the flag file | — (the inventory tests ARE the alarm) | A T-22 + B T-19 |
| N-26 | `test_readout_format` | `_negmem_world`, incl. a non-allowlisted league | §7.1 dict shape snapshot incl. `allowlisted` (bypass semantics), `parse_errors`, `likes_net`, context-tag NULL annotation, dropped-id counter | — | A T-23 + B §12.1 |
| N-27 | `test_relaxed_pass_same_map` | targeted job yielding zero cards then relaxed cards | relaxed re-run consults the SAME map/strength; relaxed cards stamped; no special case (HLD §3.5) | drop `negmem` from `v2_kwargs` (rebuild-in-relaxed also RED) | A T-24 + B T-20 |

Coverage check (per ruling 11 — every C1-C5/GR invariant has a test + sabotage): C1 → N-7,
N-8, N-13; C2 → N-5, N-6; C3 → N-12; C4 → N-15, N-16; C5 → N-14; GR4 computability → N-17,
N-18 (fit joint uniformity) + the §7.3 pack; GR3 is procedure (runbook line 5); B2 → N-10;
T1 → N-11; R9 → N-21.

Evidence ledger: all runs logged in `living-memory/TEST_LEDGER.md` with sabotage names; CI green
(pytest + tsc + testid-lint) is the pre-ship gate; `FTF_SKIP_SIM_GATE=1` standing posture per
D-056.

---

## 11. Open Questions (for cross-review)

- **OQ-1 (RESOLVED by ruling 10a; retained for the record):** the tuple-order discrepancy is
  now §9 delta (a) — code wins, sabotage-pinned in N-15.
- **OQ-2:** allowlist file name `config/negmem_leagues.json` — operator to confirm at the D1
  ruling touchpoint (mechanics are DE-7 regardless of name).
- **OQ-3:** the retraction leg's set-equality matching (§5.3) carries no time window — draft A
  proposed a 600s nearest-timestamp pairing, draft B a windowless retracted-keys set; the merge
  took B's (simpler, and conservative: it can only drop evidence) extended to the `'like'`
  decision class (A's hazard). Cross-review to confirm the windowless form, or reinstate a
  proximity bound as a reviewable constant (not a knob).
- **OQ-4:** `negmem_floor`'s double role (curve asymptote at build, clamp at seam — §4.4). The
  alternative (a separate `negmem_curve_floor` knob) was rejected to keep the knob surface at
  R10's four + two; revisit only if an arm-overlay use case for `negmem_floor` ever appears
  (none is sanctioned — D-6 is strength-only).
- **OQ-4b (flagged for the orchestrator):** the §4.4 curve is discontinuous at the
  min-evidence threshold (1.0 → 0.900 as decay crosses the gate) — draft B's continuous curve
  avoided a day-to-day ordering flap there. The ruling sheet pins the 6-knob table (hence
  `negmem_sat_k` and this curve); the flap hazard stands recorded. If cross-review wants
  continuity, the curve change is localized to `_cell_mult` + N-3's literals.
- **OQ-5:** readout exposure as a CRON-authed admin route — deliberately out of v1 (R8 is
  scripts/pytest); noted for the explainer-UI feature's future gates (NG5). (Draft B specced a
  route; ruling 11 carries draft A's readout — no route, `docs/api-reference.md` stays n/a.)
- **OQ-6:** stamp `ev` payload — carried as A's per-family dict (`{family: n_decayed}`);
  draft B asked whether the binding cell alone suffices (−12 bytes). A's form is the merged
  default (richer readout cross-check); flag only if the byte budget ever matters.
- **OQ-7:** the §5.6 two-pass-fetch fallback — folded into S6's measurement plan as "the first
  knob to turn"; not built speculatively.

---

## 12. Docs owed (scope-block Docs table rows)

| Doc | Row |
|---|---|
| `docs/config-reference.md` | `trade.negmem` flag + six `negmem_*` knobs + allowlist file (+ the M1-scoped disable wording, §8.3) |
| `docs/data-dictionary.md` | `deck_impressions.features_json.negmem` stamp key (schema §3.3) |
| `docs/architecture.md` + `living-memory/HLD.md` | new leaf module + seam wiring |
| `living-memory/LLD.md` | the T1/consult-seam + kwarg-threading convention rows |
| `docs/runbook.md` | the seven lines of §8.4 |
| `docs/glossary.md` | negmem, reason family, RFPS, evidence cell, like-netting |
| `docs/api-reference.md` | n/a — no route changes (readout is a function; admin config PUT pre-exists) |
| `docs/cross-client-invariants.md` | n/a — no client consumes the stamp in v1 |
| shared taxonomy v1.1.0 | `shape_aversion` PRODUCER=negmem entry + pass-reason anchoring (authorship per PRD §7 — breaker session owns §5; our two entries carried; dependency: taxonomy on main first) |
| `reconciliation-log.md` | the four §9 deltas, incl. the (d) re-word |
