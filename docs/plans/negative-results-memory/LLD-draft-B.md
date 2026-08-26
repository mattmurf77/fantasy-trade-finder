# LLD (draft B — Reviewer lens): Negative-results memory

**Version:** round-1 independent draft (Agent B) · **Date:** 2026-08-21
**Serves:** [HLD.md](HLD.md) (FINAL — D-1..D-10 + §7 binding) · [PRD.md](PRD.md) (FINAL) ·
Facts: [research-verification.md](research-verification.md) ("memo")
**Checkout:** worktree `claude/vigilant-spence-8583f5`; every line number below re-verified on this checkout.
**Lens:** what breaks in review and production — exact types and nullability, error paths,
races, off-by-ones, unbounded resources, SQLite-vs-Postgres hazards. Every hazard carries its
handling in place.

---

## 0. Decision register (what this draft decides; each traces to an HLD §7 handoff)

| # | Decision | HLD trace |
|---|---|---|
| L-1 | **Admission and decay run in Python over a plain, dialect-neutral row fetch.** No SQL JSON extraction, no SQL timestamp arithmetic. Perf math in §3.4. | §7 "admission SQL fragment + predicate pair"; §3.1 |
| L-2 | Undo pairing = **per-impression replay** in `(acted_at, id)` order; an `undo` pops the most recent un-undone decision-class row; one net disposition per impression. | §7 / PRD R1(d) |
| L-3 | Like-netting = **in-order running fold, decrement by 1.0 decayed unit** per viewed like against every `(P, ✱)` cell, clamped at 0 at each step. Magnitude is a module **constant**, not a knob. | §7 "netting magnitude + decrement-vs-reset"; D-7 |
| L-4 | Rounding discipline: events sorted `(ts, id)`, sequential fold; `n_decayed` rounded 1e-9, cell `mult` 1e-6, stamp `m` 1e-4. Determinism argument in §5.4. | C5 |
| L-5 | Cell curve built from the four R10 knobs only; **continuous at the min-evidence threshold** (no flapping). | §7 "decay/shrinkage formulas" |
| L-6 | D-5 combine rule = **MIN** across a partner's family cells, not product. | §7 / D-5 |
| L-7 | `effective_mult` is total for any float input: floor sanitized, strength>1 extrapolates and hits the floor clamp, strength<0 hits the 1.0 clamp. Degraded/None/absent-partner all return exactly 1.0 **inside** the pure function. | D-10, D-6 |
| L-8 | Map threading is **pure kwarg, no instance slot** — strictly stronger than D-3's read-once-into-local (there is no shared slot to race on). | D-3, H-4 |
| L-9 | Build-time knobs (`halflife`, `min_evidence`, `floor`) are read by **the server via `ts._c` at job level (no arm overlay active) and passed into `build_map`**; seam-time knobs (`strength`, `floor`) via `_c` at each call site; the M2 feed guard reads `gen2_accept_prior_strength` via `_c` at the two call sites. | §7 knob-read-path (tilted pass-in) |
| L-10 | Co-owner canonicalization: the **server builds an `owner_alias` map (ADR-012 helpers) and passes it in**; negmem never imports `sleeper_roster` (leaf contract preserved by injection — see §16 flag). | §7 "co-owner canonicalization call sites" |
| L-11 | League allowlist = tracked **`config/negmem_allowlist.json`** (`{"league_ids": [...]}`), read per build; missing/unparseable ⇒ empty ⇒ `build_map` returns None everywhere (feature inert even when the flag is ON). | §8.2 PRD / HLD §2.1 |
| L-12 | GR4: **accept the diversity-penalty pollution** of the `final/base` ratio; do NOT stamp `fatigue_m`/`taste_m` in v1. Revisit trigger stated in §12.4. | §7 GR4 computability |
| L-13 | Only **viewed likes** net. `propose` outcomes do NOT net (PRD §5.3 names likes only; adding propose is scope creep — recorded, not implemented). | D-7 |
| L-14 | R1(d) retraction: undo-replay always; the `trade_decisions.retracted_at` leg joins **via `assets_json` set-equality** and is skipped where `assets_json` is NULL (asymmetry stated, matches PRD's own caveat). | PRD R1(d) LLD note |
| L-15 | Stamp payload carries `ver` on **every** variant (uniform SQL; +8 bytes/row over the HLD sketch — stated extension). | §3.4 |

---

## 1. Module layout and the import graph (checked for cycles)

```
backend/negmem.py                       NEW LEAF (~450 lines + tests)
  imports: json, logging, math, os, dataclasses, datetime,
           from .feature_flags import FLAGS        (leaf-legal)
           from .database import engine, text|select helpers (leaf-legal)
  imports NO engine module. Engines import the MODULE:
    trade_service.py:  from . import negmem as _negmem     # T1: attribute call
    trade_gen_v2.py:   (no import — the multiplier arrives as a float kwarg, §7.2)
    trade_gen_fit.py:  from . import negmem as _negmem
    server.py:         from . import negmem as _negmem
```

Cycle check: `negmem → database → pick_values`; `pick_values` imports `trade_service`
**lazily inside functions** (`database.py:36-38`), so no import-time cycle exists. `negmem`
must never import `trade_service`, `server`, or `sleeper_roster` (L-10). A structural test
asserts `negmem`'s import list (§14, T-16).

The kwarg name is `negmem`; inside modules that receive it, the module alias is `_negmem`
so the parameter can shadow nothing. `from .negmem import effective_mult` is **forbidden**
(T1 — value import freezes the binding; the sabotage test T-11 exists to catch it).

---

## 2. Public API — exact signatures and types

```python
# backend/negmem.py

NEGMEM_VER: int = 1                 # stamp/schema version
LIKE_NET_UNITS: float = 1.0         # L-3: netting magnitude, constant (not a knob)
ADMITTED_FAMILIES: frozenset[str] = frozenset({"value", "fit"})   # PRD R2
CLEAN_EPOCH_DAY: str = "2026-08-20"                                # PRD R1(e)
_DECISION_ACTIONS: frozenset[str] = frozenset({"like", "pass", "not_interested", "propose"})

@dataclass(frozen=True)
class CellStats:
    n_raw: int          # admitted negative events, un-netted, un-decayed (readout honesty)
    n_decayed: float    # post-netting decayed evidence, ≥ 0.0, rounded 1e-9
    mult: float         # base multiplier ∈ [floor, 1.0], rounded 1e-6
    floored: bool       # mult hit the floor clamp

@dataclass(frozen=True)
class NegmemMap:
    user_id: str
    league_id: str
    as_of: str                                   # ISO UTC, tz-aware
    ver: int                                     # = NEGMEM_VER
    degraded: bool
    build_ms: float | None                       # None only on degraded-before-timing
    cells: dict[tuple[str, str], CellStats]      # (partner_league_id, family) → stats
    acceptance_stats: dict[str, tuple[int, int]] # partner_league_id → (accepts, responses)
    parse_errors: int                            # skipped rows (§13 row-level failures)

def build_map(user_id: str, league_id: str, as_of: str | None = None, *,
              halflife_days: float, min_evidence: float, floor: float,
              owner_alias: dict[str, str] | None = None) -> NegmemMap | None:
    """None ⇔ league not allowlisted (PRD §8.2 seam) — indistinguishable from
    flag-off downstream. NEVER raises except KeyboardInterrupt/SystemExit
    (BaseException passes through `except Exception` untouched); any internal
    Exception returns a degraded map (§13). All knobs arrive as arguments —
    no config access in this module (L-9)."""

def effective_mult(nm_map: "NegmemMap | None", partner_league_id: str, *,
                   strength: float, floor: float) -> float:
    """PURE (D-10): no config, no I/O, no defaults read. Total function —
    §6.2 defines every input class including NaN. Returns 1.0 for
    None map, degraded map, unknown partner, or all-identity cells."""

def acceptance_stats_for(nm_map: "NegmemMap | None") -> dict[str, tuple[int, int]] | None:
    """M2 feed accessor (§8.3): None when nm_map is None, degraded, or empty
    stats — the caller then OMITS the kwarg entirely (C1 posture)."""

def negmem_readout(user_id: str, league_id: str, as_of: str | None = None, *,
                   halflife_days: float, min_evidence: float, floor: float,
                   owner_alias: dict[str, str] | None = None) -> dict:
    """R8. Same builder (calls build_map with allowlist BYPASSED — the readout
    must work for a not-yet-allowlisted league, §12.1). JSON-serializable."""

def admission_sql() -> str:      # §4.1 — the ONE spine query, shared verbatim
def rfps_sql() -> str:           # §12.3 — embeds admission_sql(); doc + operator use
```

Type notes a reviewer will ask about:
- `min_evidence` arrives as `float` because `model_config` is Float-valued
  (`backend/CLAUDE.md` §Database); compare `n_decayed >= min_evidence` in float, never
  `int()`-truncate (an `int(2.9)==2` truncation silently lowers the gate).
- `NegmemMap` and `CellStats` are `frozen=True`: the map is shared read-only across the
  bake-off fan-out on one thread and must be structurally immutable (H-4 defense; a seam
  cannot "fix up" a cell in place).
- `cells` uses league-identity partner keys only (R9). `owner_alias` maps any co-owner id
  seen in source rows to the roster's canonical `owner_id` before keying (ADR-012); None ⇒
  identity mapping.

---

## 3. The bulk read — dialect decision with the numbers

### 3.1 House constraints (verified)

- `analytics_queries.py:8-12` is the binding precedent: **no `json_extract`/`->>`, no
  dialect date functions; day bucket = `substr(col,1,10)`; JSON parsed in Python; window
  bounds compare the DATE PREFIX against `YYYY-MM-DD` binds** — never a `Z`-suffixed
  instant against the stored `+00:00` text. All timestamps in this table family are ISO
  strings written by `datetime.now(timezone.utc).isoformat()` (e.g. `database.py:5542`,
  `server.py:4115`), i.e. `2026-08-21T17:03:12.123456+00:00`.
- `features_json` is a `Text` column (`database.py:507`); **no existing SQL extracts JSON
  fields from it** — every consumer loads it in Python. SQLite's `json1` and Postgres's
  `jsonb` operators differ enough (`json_extract(features_json,'$.partner_user_id')` vs
  `features_json::jsonb->>'partner_user_id'`) that a dual-dialect extraction means two SQL
  texts kept in sync forever — exactly the drift class the ONE-implementation rule exists
  to kill.

### 3.2 DECISION (L-1): Python admission over a plain fetch

The SQL does only what both dialects do identically — equality binds, day-prefix bounds on
ISO text, and index-served joins. Family mapping, viewed-gating, ghost checks, undo replay,
epoch checks, and decay all run in Python from one fetched row set. One implementation
serves builder, readout, and the RFPS doc SQL (H-1).

### 3.3 The spine query (`admission_sql()`, verbatim, both dialects)

```sql
SELECT di.impression_id,
       di.served_at,            -- ISO text, NOT NULL (database.py:513)
       di.features_json,        -- Text, nullable → Python-parsed, §4.2
       di.is_ghost,             -- Integer, NULL on pre-telemetry rows
       di.assets_json,          -- Text, NULL while telemetry off (L-14 leg)
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

- **Bound:** `:horizon_day = max(CLEAN_EPOCH_DAY, (as_of − 4·halflife_days).date())` as
  `YYYY-MM-DD` (HLD §3.1 read horizon). Day-granularity is deliberately conservative by at
  most one day of extra rows — never one day short, because `>=` on the day prefix admits
  the whole boundary day.
- **Off-by-one check:** clean epoch is "`served_at` ≥ 2026-08-20" (PRD R1(e));
  `substr(...) >= '2026-08-20'` includes 2026-08-20 exactly. D-091 (08-16→08-19) is
  excluded structurally because the floor never goes below `'2026-08-20'` — no separate
  NOT-BETWEEN clause to get wrong.
- **Index path:** outer filter on `ix_deck_impressions_user_league` (`database.py:610`),
  join on `ix_deck_outcomes_impression` (`database.py:758`), reason PK join. Same plan
  class on both engines; no sort requested (ordering is Python's job — an SQL `ORDER BY`
  would differ in NULL/collation corners across engines for zero benefit).
- **`LEFT JOIN` fan-out check:** `trade_pass_reasons.impression_id` is the PK — at most
  one reason row per impression, so the join cannot duplicate outcome rows.
- **Result-set shape:** one row per outcome event. `viewed`, `like`, `pass`,
  `not_interested`, `propose`, `undo` all arrive; Python partitions them.

### 3.4 Perf math (why Python admission holds the S6 budget)

Worst-case rows at 10× current volume: HLD §3.1 bounds the spine at ~10k–40k rows in the
180-day cap. Two costs dominate: row fetch (~1–3 µs/row → ≤120 ms worst case, but the
league-scoped index makes the realistic case ≤3k rows ≪ 10 ms) and `json.loads` of
`features_json` (~5–15 µs at its ~500–900 byte size). **Mitigation that keeps the ceiling:**
`features_json` is parsed **only** for rows that survive the cheap Python pre-filters
(decision-class action, reason-family admitted OR netting-like) — bounded by ~120 clean
reason rows/week × 26 weeks ≈ 3.1k parses ≈ 30–50 ms at 10×. Total worst-case ≈ 150 ms
against the 250 ms ceiling; measured p95 is the real gate (S6), and §13 discards any build
that exceeds 500 ms (= 2× ceiling) as degraded. If S6 measures a breach at 10×, the
HLD §5.4 materialized-cache fallback triggers — same builder, `negmem_cells` cache, its own
scope block; **nothing in this LLD may be "optimized" into a second source of truth first.**

A note the optimist dodges: `SELECT di.features_json` fetches the text for every spine row
even when Python won't parse it. At 40k × ~700 B ≈ 28 MB worst case that is transfer, not
parse, and it is the 10× tail; if S6 shows it, the surgical fix is a two-pass fetch (ids
first, features for admitted ids via chunked `IN` — 500 ids/chunk, both dialects) — noted
as the first knob to turn, not built speculatively.

### 3.5 Companion reads (same job, same transaction scope)

All three reads run on `database.engine` (product path; WAL/busy_timeout set,
`database.py:79-87`), each in its own short-lived `engine.connect()` — **no long
transaction**: consistency-within-job comes from building once per job (H-3), not from
snapshot isolation, and holding a read txn across three queries on SQLite WAL would pin the
WAL for the duration for no benefit.

**Q2 — retraction leg (L-14):**
```sql
SELECT give_player_ids, receive_player_ids, retracted_at, created_at
FROM trade_decisions
WHERE user_id = :uid AND league_id = :lid AND decision = 'pass'
  AND retracted_at IS NOT NULL
  AND substr(created_at, 1, 10) >= :horizon_day
```
Small by construction (retracted passes are near-nonexistent — the marker is set by
awaiting-dismiss on like rows, memo §1.1). Python builds
`retracted_keys = {(frozenset(give), frozenset(receive))}` and admission drops any evidence
row whose parsed `assets_json` matches a key. `assets_json` NULL ⇒ leg skipped for that row
(the PRD-stated asymmetry: pass-side retraction signal is the paired undo).

**Q3 — M2 aggregation (§8):** plain league-scoped `SELECT` on `trade_matches` (§8.1).

---

## 4. Admission — the ONE implementation (SQL fragment + Python predicate pair)

### 4.1 Structure

```python
def _admit_events(rows, *, as_of_dt, retracted_keys, owner_alias) -> tuple[
        list[_Evidence], list[_Netting], int]:   # (evidence, netting, parse_errors)
```
Called by `build_map` and `negmem_readout` (same object code); `rfps_sql()` embeds
`admission_sql()` and documents the Python predicate as the metric's admission definition —
builder, readout, and metric literally share one implementation (H-1).

### 4.2 Per-impression replay (L-2) — the undo pairing rule, precisely

Group fetched rows by `impression_id`. Within a group, order outcome rows by
`(acted_at, outcome_id)` ascending — `acted_at` is server-clock ISO text (identical format
every row, lexicographic = chronological); `outcome_id` (autoincrement on both engines)
breaks same-instant ties deterministically. Drop rows with `acted_at > as_of` (as-of
reconstruction, R6). Then replay:

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
- **Multiple undos** — each pops one decision; extra undos are no-ops. A
  pass→undo→pass→undo chain nets to None. Deterministic for any row multiset.
- **Duplicate labels** (two `pass` rows, legal per `database.py:743`) — the stack holds
  both; one undo removes one. Final disposition is the last survivor; the impression still
  contributes **at most one** evidence or netting unit (impression-keyed, §5.1) — dup rows
  can never double-count a cell.
- **`pass` then `like` with no undo** (data-legal even if UI-improbable) — last survivor
  wins: the impression is a netting like, not evidence.
- **Undo arriving after `as_of`** — invisible to this build by the `acted_at ≤ as_of` cut;
  a later build sees it and the cell moves. That is R6's definition, not a bug.
- **`viewed` ordering** — the viewed gate is "a viewed row exists with
  `acted_at ≤ as_of`", NOT "viewed precedes the decision": the client fires
  `deck_card_viewed` through the batched events side-channel (`server.py:8088-8107`) and
  it can land after the swipe row. Requiring precedence would drop legitimate evidence on
  a delivery race.

### 4.3 The closed admission list (R1(a)–(e)) as executed checks

An impression contributes **evidence** `(partner, family)` iff ALL of:
(a) `viewed` is True; (b) `final in {"pass","not_interested"}`; a reason row exists with
`key_source == 'impression'` and `reason in ADMITTED_FAMILIES` — `family = reason`
(layer-1 column directly; unknown future layer-2 `detail` codes are irrelevant because the
layer-1 column is what's read — R2's forward-compat rule holds by construction; `reason`
NULL or `'other'` ⇒ not admitted; `key_source='local'` ⇒ not admitted, no spine join);
(c) `is_ghost` is NULL or ≠ 1 (Integer nullable — the `!= 1` form treats NULL as
not-ghost, matching pre-telemetry rows); (d) not retracted: the replay survived (that IS
the undo check) AND its asset key ∉ `retracted_keys` when `assets_json` parses (L-14);
(e) epoch: enforced by the SQL bound (§3.3) — no second Python check to drift.

`partner` = `features_json["partner_user_id"]` passed through `owner_alias` (L-10);
NULL/missing partner ⇒ row skipped, counted in `parse_errors` (a partnerless card cannot
key a partner-keyed prior). `evidence.ts` = the **`acted_at` of the last surviving
decision row** (the decision is the evidence event, not the serve — decay must age the
rejection, not the impression). Context tags (R11, recorded-not-consulted):
`lane`, `user_value_basis` from `features_json`; `basis_tag='board_fit'` when
`family=='value'` and `user_value_basis=='personal'` (PRD R2/taxonomy §2.6 — the family
**key stays `value`**; the tag is readout-only. Re-keying personal-basis value evidence
into `fit` would silently merge two objection classes under the v1 MIN-combine and is
deliberately not done).

An impression contributes **netting** iff: viewed, `final == "like"`, non-ghost, in-epoch.
Reason row not required (likes carry none). `ts` = the like row's `acted_at`.
`propose` survivors contribute nothing (L-13).

---

## 5. Cell arithmetic — decay, netting, curve

### 5.1 Event streams per cell

For each cell `(P, fam)`: its evidence events (impression-deduped, §4.3). Netting likes
target **every `(P, ✱)` cell** (PRD §5.3): a like toward partner P is appended to the
event stream of each existing `(P, fam)` cell — and to no cell if P has no evidence cells
(no credit banking against future evidence; see fold below, which makes this structural
rather than special-cased… with one exception handled here: a like *between* two evidence
events of a not-yet-created cell is not an exception at all, because the fold processes
the merged stream in time order, so a like preceding all evidence decays against an empty
cell and clamps to 0 — the same outcome).

### 5.2 The fold (L-3, D-7): in-order, clamped at every step

Merge evidence (+1.0 unit) and netting (−`LIKE_NET_UNITS`) events; sort by
`(ts, kind, row_id)` where `kind` orders evidence before netting at identical timestamps
(a same-instant like should net the evidence it accompanies, not miss it). Then:

```python
v, t_prev, n_raw = 0.0, None, 0
for ev in events:
    if t_prev is not None:
        v *= 0.5 ** ((ev.ts - t_prev).total_seconds() / 86400.0 / halflife_days)
    v = max(0.0, v + ev.delta)          # clamp EVERY step — a like never banks credit
    if ev.delta > 0: n_raw += 1
    t_prev = ev.ts
v *= 0.5 ** ((as_of_dt - t_prev).total_seconds() / 86400.0 / halflife_days)
n_decayed = round(max(0.0, v), 9)
```

Bounds this construction guarantees (the questions a reviewer asks first):
- **A cell can never go negative** — `max(0.0, ·)` at every fold step and at the end.
- **One like erases at most `LIKE_NET_UNITS` (=1.0) decayed units per cell** — it cannot
  reset a 5-evidence cell (reset was REJECTED: it would let one exploratory like erase a
  month of consistent reasoned rejections; decrement-by-one mirrors the evidence quantum).
- **A like older than the evidence nets less** (it decays like everything else); a like
  newer nets a full unit. Both directions fall out of one formula — no special cases.
- `ts` strictly in the past relative to `as_of` by construction (rows filtered
  `acted_at ≤ as_of`); a clock-skew future `ts` (server clock jumped back between writes)
  would make an exponent positive → weight >1. Handling: clamp each decay exponent at ≥0
  (`max(0.0, Δdays)`), so skewed rows count as weight-1, never amplified.

### 5.3 The curve (L-5) — four knobs, no fifth

```python
if n_decayed < min_evidence:
    mult, floored = 1.0, False                      # shrinkage gate (R3)
else:
    span = max(min_evidence, 1.0)                   # e-fold count reuses min_evidence
    raw = floor + (1.0 - floor) * 0.5 ** ((n_decayed - min_evidence) / span)
    mult = min(1.0, max(floor, round(raw, 6)))
    floored = (mult <= floor + 1e-9)
```

Properties: **continuous at the threshold** (`n_decayed == min_evidence` ⇒ mult exactly
1.0 — no day-to-day ordering flap as decay crosses the gate); monotone decreasing;
asymptote = `floor`; at defaults (floor 0.6, min_ev 3) evidence 3→1.0, 6→0.8, 9→0.7,
12→0.65. Uses only R10's four knobs — no `negmem_step` knob to seed, pin, snapshot, and
disposition (the knob-inventory test at `test_bakeoff_arm_a_golden.py:545-559` makes every
extra knob a five-file change; the curve above makes the fifth knob unnecessary).
Degenerate-input handling: `floor` sanitized to `min(max(floor, 0.0), 1.0)` and
`halflife_days`/`min_evidence` to `max(value, 1e-6)` **once at `build_map` entry** —
a zero or negative knob from a fat-fingered `PUT /api/admin/config` must not produce
`ZeroDivisionError` or a mult > 1 (it produces near-instant decay / an always-on gate,
both safe, both visible in the readout).

### 5.4 Determinism (C5) — stated, not hoped

Same `(user, league, as_of)` ⇒ same map because: (1) inputs are append-only rows filtered
by `acted_at ≤ as_of` (the `trade_pass_reasons` upsert is the R6-conceded exception);
(2) event order is a total order on `(ts, kind, row_id)` — no dict/set iteration
influences any sum; (3) IEEE-754 double ops with identical operands in identical order are
bit-identical on one platform, and the 1e-9/1e-6 rounding absorbs any cross-platform
libm-`pow` last-bit variance between the SQLite dev box and the Postgres prod box;
(4) `as_of` is captured once at build entry (`datetime.now` called exactly once) — nothing
else reads a clock. Sabotage that proves the test can fail: T-10 (§14).

---

## 6. `effective_mult` — exact arithmetic

### 6.1 Per-partner collapse (L-6)

```python
fam_mults = [cell.mult for (p, f), cell in nm_map.cells.items() if p == partner_league_id]
m_partner = min(fam_mults) if fam_mults else 1.0
```
MIN, not product: the two families are distinct objection classes but not independent
samples — a partner at value-mult 0.8 and fit-mult 0.8 has told us two things once each,
not one thing twice; product (0.64) races toward the floor faster than either cell earned
and directly feeds the GR4 compounding risk. MIN is the conservative reading and keeps
`m_partner ∈ [floor, 1.0]` by construction. Fixture: T-6 pins product≠min on a two-cell
partner. (Implementation detail: `build_map` precomputes `{partner: m_partner}` so
`effective_mult` is O(1) per call, not O(cells) inside the per-candidate fit loop.)

### 6.2 The formula (verifying HLD D-6's wording)

```python
def effective_mult(nm_map, partner_league_id, *, strength, floor):
    if nm_map is None or nm_map.degraded:
        return 1.0                               # degraded ⇒ identity (HLD §3.2 round-3 rule)
    m = nm_map._partner_mult.get(partner_league_id, 1.0)
    if m >= 1.0:
        return 1.0
    f = min(max(float(floor), 0.0), 1.0)         # sanitize a bad knob read
    s = float(strength)
    if s != s:                                    # NaN strength — treat as kill, not poison
        return 1.0
    eff = 1.0 + s * (m - 1.0)
    return round(min(1.0, max(f, eff)), 6)
```

Behavior table (the review questions, answered in the math):
| input | eff | why safe |
|---|---|---|
| `strength = 0` | exactly 1.0 (`1 + 0·(m−1)`), and the seam skip fires — no multiply, no round | C1 structural short-circuit |
| `strength = 1` | `m` clamped | the intended live setting |
| `strength > 1` | extrapolates below `m`, **clamped at floor** — allowed, bounded; an operator over-crank cannot exceed the floor | D-6 clamp is the authority |
| `strength < 0` | `eff > 1.0` → **upper clamp 1.0** — sink-never-rise survives a negative knob | C2 |
| `floor > 1.0` (misconfig) | sanitized to 1.0 ⇒ eff = 1.0 | clamp args never invert |
| NaN strength | 1.0 | NaN propagating into every composite_score is the alternative |
| unknown partner / empty cells | 1.0 before any arithmetic | new league-mate = identity |

Degraded-inside-the-pure-function note: `degraded` is **data on the map**, so branching on
it does not violate D-10's "no config access"; centralizing it here is what makes "seams
treat a degraded map as identity" a one-line invariant instead of a per-seam convention
(the HLD assigns the eff==1.0 *skip* to seams; the identity *decision* lives here — skip
stays seam-side as specified).

---

## 7. Consultation seams — exact code shapes, once-only proofs

The map travels **only as a kwarg** (L-8): `_generate_kwargs["negmem"] = nm_map` is set in
`_run_trade_job` **only when `nm_map is not None`** (key absent otherwise — flag-off
kwargs are byte-identical, C1). `generate_trades`/`_generate_trades_impl` gain
`negmem=None`; `_generate_trades_impl` threads it into `_generate_trades_v2(...,
negmem=negmem)` and into `_v2_kwargs` (so the #189 relaxed rerun at
`trade_service.py:4088-4089` consults the SAME map with the same `_c`-read strength —
HLD §3.5). **No `self._negmem` attribute exists** — there is no slot for a concurrent
same-session job to overwrite, which discharges H-4 more strongly than the
`_exclusion_keys` precedent it was modeled on (`trade_service.py:3983` remains the
precedent for the *kwarg overwrite* semantics, not for storage).

### 7.1 Serving engine (v1/v3 + consensus fallback) — the per-member stack

Location: inside `_generate_trades_v2`'s per-member loop, joining the bounded-multiplier
stack **after** block-boost (`trade_service.py:5097-5104`) and outlook-dir
(`:5120-5127`), before the lane-shift stamp (`:5135`):

```python
# negmem (flag trade.negmem) — reasoned-rejection prior, D-4/D-6/D-10.
# Applied AFTER all gates, at candidate creation, exactly once per card.
if negmem is not None:
    _nm_eff = _negmem.effective_mult(
        negmem, member.user_id,
        strength=_c("negmem_strength"), floor=_c("negmem_floor"))
    if _nm_eff != 1.0:                      # the seam-owned skip (:5125 pattern)
        for c in cards:
            c.negmem_m  = _nm_eff           # consult-time provenance (B2)
            c.negmem_ev = negmem.evidence_for(member.user_id)   # (keys, n) tuple, §9
            c.composite_score = round(c.composite_score * _nm_eff, 3)
```

`member.user_id` here is `league_members.user_id` = the canonical roster owner id
(ADR-012 keeps `league_members` single-valued on `owner_id`), i.e. already league
identity — no aliasing needed at this seam; aliasing was needed on the *data* side
(§4.3, §8.2).

**Once-only proof under streaming (the invariant the HLD demands proven):** each `cards`
list is created fresh per member by the pair generators (`:5021`/`:5057`/`:5059`), passes
through this block exactly once, then `new_cards.extend(cards)` (`:5200`). The streaming
callback calls `self._dedup_and_sort(new_cards)` per snapshot (`:5202-5205`) and again at
final assembly — and `_dedup_and_sort` (`:4180-4256`) **contains no score write**: it
filters (past-decision `:4192-4196`, R4 `:4197-4202`), sorts (`:4205`), and caps
(C4 `:4224-4237`, C4b `:4254`). Re-running it N times over the accumulating list re-reads
`composite_score`, never mutates it. Therefore a card's composite is multiplied by
`_nm_eff` exactly once no matter how many snapshots fire — the compounding failure the
HLD rejected for the `_dedup_and_sort` seam (D-4) cannot occur at this one.

Rounding note: `round(·, 3)` matches every neighbor in the stack (`:5071`, `:5088`,
`:5104`, `:5127`) — stamping `negmem_m` unrounded while rounding the composite is why GR4
computes the joint from the stamp, not by re-dividing composites.

Legacy path caveat, stated: the pre-v2 loop (`:4095-4178`, `trade_engine_v2` flag OFF)
gets **no seam** — `trade_engine_v2` is ON in prod and arm A runs through the v2/v3 stack
too (`MODEL_A_PROFILE` is a knob overlay, not the legacy branch). If the flag were ever
flipped off, negmem goes silently inert on that path; recorded in §16 rather than plumbed.

`generate_asset_ideas` (`:4332`) and the likes-you injector never consult the map —
injector cards are the exempt class (stamped `{m:1.0, exempt}` at assembly, §9).

### 7.2 gen_v2 — pair-constant multiplier at candidate creation

`generate_league_suggestions` gains **`negmem_mult_by_uid: dict[str, float] | None = None`**
— a plain dict, NOT the map (keeps `trade_gen_v2` free of any negmem import; the arm C
runner and the flag-on branch compute it from the map at the boundary where they already
compute nothing else per member… precisely: the two callers build it as
`{m.user_id: _negmem.effective_mult(nm_map, m.user_id, strength=_c("negmem_strength"),
floor=_c("negmem_floor")) for m in league.members}` — the `_c` reads execute on the
caller's thread INSIDE the arm's `_cfg_override` context (arm C's lambda body runs inside
`run_bakeoff`'s per-arm context), which is exactly the D-6 overlay mechanism).

Consumption, at the score line (`trade_gen_v2.py:655`):
```python
score = joint * accept_prior * priority_weight * nm_mult    # nm_mult pair-constant
```
with `nm_mult = (negmem_mult_by_uid or {}).get(member.user_id, 1.0)` resolved once per
member next to `prior`/`weight` (`:951-952`) and passed into `_pair_survivors` like
`accept_prior`. `card.composite_score = round(cand.score / 1500.0, 4)` (`:1012`) then
carries it; the per-pair MESO/dedup/exposure stages sort by `cand.score` (`:1038-1040`,
`:1054`) — computed once at `:655`, never recomputed — so the once-only property is
structural on this path too. `card.negmem_m` is stamped in the card loop when
`nm_mult != 1.0`. Within-pair ordering is untouched (pair-constant factor); cross-pair
ordering shifts — that is the feature.

Call sites to update (both, memo §2f): `trade_service.py:4001-4033` (flag-on branch —
compute from the `negmem` kwarg) and `bakeoff_runner.py:1212-1232` (arm C — compute from
`kwargs.get("negmem")`). C1: when the map is None the kwarg is **omitted** at both sites.

### 7.3 fit — rank-key multiplier, ordering only

In `generate_fit_suggestions` (`trade_gen_fit.py`): accept `negmem=None` kwarg
(threaded from `gen_fit_cards`'s `kwargs`, `bakeoff_runner.py:1317`). Per member in the
pair loop (`:320`), resolve `eff_by_uid[member.user_id]` once via
`_negmem.effective_mult(negmem, member.user_id, strength=ts._c("negmem_strength"),
floor=ts._c("negmem_floor"))`. Then the rank (`:389-392`) becomes:

```python
candidates.sort(key=lambda c: (
    -round(c["aggregate_raw"] * eff_by_uid.get(c["member"].user_id, 1.0), 9),
    -c["fairness"],
    (c["member"].user_id, tuple(sorted(c["give_ids"])), tuple(sorted(c["recv_ids"])))))
```

- **Multiply BEFORE the 1e-9 round** (HLD §2.2, verified sound): the C7c plateau ties are
  same-partner (`aggregate_raw` mirrored-tanh sums equal up to ~1e-13, `:385-388`), so
  both tied candidates carry the SAME `eff` — the scaled noise is ~1e-13·eff < 0.5e-9 and
  the round still collapses them onto one quantum; the deterministic tie-break survives.
  Multiplying after the round would compare unquantized products and let float noise
  outrank the tie-break — the review-blocking bug the order exists to prevent.
- `composite_score` (`:442`) and the `fit` payload stay **pure** — fit's aggregate is a
  published diagnostic; negmem influences rank only (HLD's "ordering only").
- Stamp: `card.negmem_m = eff` in the card loop (`:424-452`) when `eff != 1.0` — the GR4
  joint reads `m × final/base` and fit's `final==base` on bake-off decks (rerankers
  bypassed ⇒ `final_score` falls back to base, `server.py:4229`), so the joint equals `m`
  exactly — uniform with HLD §5.3.
- **The `restore_order` dependency (HLD fragility, end-to-end test required):** fit's
  order reaches the served deck only through the interleaver; the likes-you injector then
  re-sorts by composite (which never saw eff) and `_bakeoff.restore_order`
  (`bakeoff_runner.py:1415-1429`, called `server.py:5765-5767`) restores every arm card to
  its interleaved index by `id()`. T-13 pins this end-to-end: a fixture where negmem swaps
  two fit cards' ranks must show the swap in the FINAL deck after injection.
- Sort-lambda cost check: dict-get per comparison over ≤ `fit_max_packages_per_pair` ×
  pairs candidates — same shape as the existing lambda; no measurable delta.

### 7.4 Rejected seam shapes (carried from HLD D-4, restated as review ammunition)

Post-generation multiplier: dies under GR3 (bake-off decks bypass the post-gen stack,
`server.py:5884-5893` — the prior would vanish exactly when measured). `_dedup_and_sort`:
compounds per snapshot (§7.1 proof is of the *chosen* seam's immunity). Key-set extension:
membership = exclusion = NG1.

---

## 8. M2 — the acceptance-stats feed

### 8.1 Aggregation (both dialects, empty-table behavior identical)

```sql
SELECT user_a_id, user_a_decision, user_a_decided_at,
       user_b_id, user_b_decision, user_b_decided_at,
       matched_at
FROM trade_matches
WHERE league_id = :lid
```

Column semantics verified against `database.py:417-436`: `user_a_id` = first swiper,
`user_b_id` = counterparty; `user_{a,b}_decision ∈ {'accept','decline', NULL}`;
`user_{a,b}_decided_at` String **nullable**; `status ∈ pending|accepted|declined` is
derived and deliberately NOT used (a `pending` row where one side already declined-first
would be missed by status-filtering; per-side decisions are the response events).
`user_{a,b}_dismissed` is inbox-archive only (memo correction 2) — never read here.

Python fold (no SQL date math — the table is tiny; matches are rare):
```python
for row in rows:
    for uid, dec, dts in ((a_id, a_dec, a_ts), (b_id, b_dec, b_ts)):
        if dec not in ("accept", "decline"):    continue
        ts = _parse(dts) or _parse(matched_at)  # NULL decided_at → matched_at fallback
        if ts is None or ts > as_of_dt:          continue
        if ts < as_of_dt - timedelta(days=180):  continue   # PRD R5 lookback IN-QUERY-layer
        key = owner_alias.get(uid, uid)          # L-10: id-space conversion (§8.2)
        acc, resp = stats.get(key, (0, 0))
        stats[key] = (acc + (dec == "accept"), resp + 1)
```
- **The aggregation never emits zero-response keys** (structurally: a key exists only via
  `resp + 1`) — HLD §3.5 guard half 1.
- Empty table ⇒ zero rows ⇒ `{}` on both engines (no aggregate SQL, so no
  SQLite-`SUM`-returns-NULL vs Postgres row-shape divergence to reconcile — the class of
  bug the Python fold avoids outright).
- 0/0 cannot reach `acceptance_prior`: a partner with responses ≥ 1 divides by
  `responses + m ≥ 1` even at `m = 0`; a partner absent from the dict returns `p0`
  (`trade_gen_v2.py:303-304`). The `accepts ≤ responses` clamp already exists (`:307`).
- S4 expected-null: with the decline route having essentially never fired (memo §2c/§8),
  `stats` will be near-empty; a uniform read is annotated expected, not a bug.

### 8.2 Id-space conversion (the flagged hazard, resolved)

`trade_matches.user_{a,b}_id` come from `trade_decisions.user_id` = session account-side
platform ids; a co-owner's id is NOT the roster's canonical `owner_id`, while gen_v2 looks
up `acceptance_stats[member.user_id]` = canonical owner ids. Without conversion a
co-owner's responses silently vanish (dict miss → global prior — no error, wrong data).
`owner_alias` is built by the SERVER from the in-hand league object:
`{co_id: m.owner_id for m in league.members for co_id in co_owner_ids(m)}` via
`sleeper_roster` helpers (the ONE predicate, `backend/CLAUDE.md` §Identity) and passed
into `build_map`. Sole-owner leagues yield an empty dict (identity). T-8 fixes this with
the co-owned-league fixture (`tests/fixtures/sleeper/co-owned-league/`).

### 8.3 The feed and its guards (both call sites)

```python
_nm_stats = _negmem.acceptance_stats_for(nm_map)          # None if map None/degraded/empty
if _nm_stats and _c("gen2_accept_prior_strength") > 0:    # guard half 2 — feed-side, NG9
    call_kwargs["acceptance_stats"] = _nm_stats           # kwarg OMITTED otherwise (C1)
```
- The `_c` read executes at the call site **inside the arm's overlay context**, so a
  per-arm pin of `gen2_accept_prior_strength = 0` ALSO empties the feed — this closes the
  raw-unshrunk-ratio hole the HLD's runbook line warns about (`(a + 0·p0)/(r + 0)` can
  never be computed on a populated dict, because a ≤0 strength means the dict is never
  passed). The HLD's "kill via the GLOBAL knob only" runbook line is retained as
  *procedure* (arm overlays are bake-off instruments, not kill switches), but the guard
  makes the failure it feared unreachable. Flagged in §16 as a strengthening, not a
  deviation.
- The ratified `acceptance_prior` math is untouched (NG9): the guard lives entirely feed-side.
- Degraded map ⇒ `acceptance_stats_for` returns None ⇒ kwarg absent ⇒ arm C behaves
  identically to flag-off (HLD §3.5 "degraded ⇒ the feed returns `{}`" — implemented as
  kwarg-absence, which is strictly stronger byte-parity; `{}` vs absent both yield `p0`
  but absence keeps the call signature byte-identical to today).
- Arm A never reaches gen_v2 (it is the v1/v3 engine; gen_v2 runs only as arm C /
  flag-on) — clean M1 comparator, no code needed.

---

## 9. Stamps — provenance rule B2, executed

### 9.1 Card-side (consult time)

Seams set `card.negmem_m` (float, the eff actually multiplied/ranked) and
`card.negmem_ev` (`(keys, ev)` from `negmem.evidence_for(partner)`: `keys` = sorted list
of families whose cells cleared min-evidence for that partner; `ev` = `n_decayed` of the
**binding** (min) cell, rounded 1e-3). `evidence_for` is O(1) (precomputed at build).
Attributes only ever set when eff ≠ 1.0.

### 9.2 Assembly-side (`server._log_deck_signal_impressions`)

New parameter `negmem_ctx: dict | None = None`; `_run_trade_job` passes
`{"degraded": nm_map.degraded, "ver": NEGMEM_VER}` **iff `nm_map is not None`**. Inside
the per-entry loop (after `:4160`, inside the features dict assembly — INSIDE
`features_json`, so the executemany first-row-keys trap (`server.py:4251-4256` comment)
structurally cannot drop it):

```python
if negmem_ctx is not None:                       # flag ON ∧ league allowlisted
    if negmem_ctx["degraded"]:
        features["negmem"] = {"m": 1.0, "degraded": True, "ver": negmem_ctx["ver"]}
    elif features["likes_you"]:
        features["negmem"] = {"m": 1.0, "exempt": True, "ver": negmem_ctx["ver"]}
    else:
        _m = getattr(card, "negmem_m", None)     # COPY card state; compute NOTHING (B2)
        if _m is not None:
            _keys, _ev = getattr(card, "negmem_ev", ([], None))
            features["negmem"] = {"m": round(_m, 4), "keys": _keys, "ev": _ev,
                                  "ver": negmem_ctx["ver"]}
        else:
            features["negmem"] = {"m": 1.0, "ver": negmem_ctx["ver"]}
```

- Trichotomy exactly as HLD §3.4: map None (flag off ∨ not allowlisted) ⇒ **no key on any
  row** (byte-identical features_json); ON+degraded ⇒ every row `{m:1.0, degraded}`;
  ON+healthy ⇒ every row carries the key (real m / `{m:1.0}` / `{m:1.0, exempt}`) —
  including ghost rows should the disabled holdout ever return (the loop covers `entries`,
  served + ghost, `:4120-4122`).
- **No `effective_mult` call, no `_c` read exists in assembly** — by logging time every
  arm's `_cfg_override` has exited, so any assembly-side recompute would stamp arm-A rows
  with the live arm's m (the B2 poisoning). T-12's sabotage is exactly that recompute.
- ~68 bytes/row healthy-influenced, ~30 uninfluenced — inside the HLD's accepted ~60 B/row
  envelope (the `ver`-everywhere extension, L-15, costs 8).

---

## 10. Job wiring, threading, and failure taxonomy

### 10.1 Build site in `_run_trade_job` (one map per job, H-3)

Placed after the R4 exclusion build (`server.py:5498-5505`) and before the bake-off
fan-out (`:5672`) — after flag+allowlist, before any arm:

```python
nm_map = None
if FLAGS.trade_negmem and league_id != "league_demo":
    _nm_t0 = time.monotonic()
    try:
        nm_map = _negmem.build_map(
            g_user_id, league_id,
            halflife_days=_c("negmem_halflife_days"),
            min_evidence=_c("negmem_min_evidence"),
            floor=_c("negmem_floor"),
            owner_alias=_owner_alias_map(g_league))     # §8.2; {} for sole owners
    except Exception as nm_err:                          # KeyboardInterrupt/SystemExit pass through
        log.warning("negmem build failed (degraded): %s", nm_err)
        nm_map = _negmem.degraded_map(g_user_id, league_id)
    _nm_ms = (time.monotonic() - _nm_t0) * 1000.0
    if nm_map is not None:
        if not nm_map.degraded and _nm_ms > 2 * _NEGMEM_BUILD_CEILING_MS:   # 500ms
            nm_map = _negmem.degraded_map(g_user_id, league_id)   # slow-but-valid: DISCARDED
        with _trade_jobs_lock:                            # the suppression_note pattern (:5811-5814)
            j = _trade_jobs.get(job_id)
            if j is not None:
                j["negmem_note"] = {"build_ms": round(_nm_ms, 1),
                                    "degraded": nm_map.degraded,
                                    "cells": len(nm_map.cells)}
if nm_map is not None:
    _generate_kwargs["negmem"] = nm_map                   # key ABSENT otherwise (C1)
```

- These job-level `_c` reads run on the job thread **before any arm context exists** —
  they are the global values by construction (the D-6-accepted build-knob asymmetry: arm
  A's opt-out is strength-only, stated so nobody "fixes" it).
- The timing measurement cannot itself fail-open a broken build: `time.monotonic()` does
  not raise; `_nm_t0` is bound before the `try`, so the `except` path still yields a valid
  `_nm_ms`. If the fan-out later raises for unrelated reasons, the note is already on the
  job dict (written before generation).
- Bake-off: both fan-out lambdas spread `_generate_kwargs` (`:5679-5685`), so all arms see
  the **same frozen map** — identical memory across arms (H-3), differing only via each
  arm's overlay-read `negmem_strength`.

### 10.2 Failure taxonomy (which exceptions produce what)

| Failure | Behavior | Why |
|---|---|---|
| `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` | **propagate** — `except Exception` does not catch `BaseException` subclasses | never swallow interpreter shutdown |
| Any `Exception` inside `build_map` (DB down, SQL error, `MemoryError`* included) | degraded map — every row stamps `{m:1.0, degraded}`; seams identity; M2 feed absent | F3 precedent `server.py:4498-4503`; failure is in the data, never inferred from absence |
| Slow-but-valid build (> 500 ms) | **discarded by design** → degraded map (round-3 rule: not just stamped — the cells are gone, so no seam can use a map that blew the budget) | S6 integrity |
| Allowlist file missing / unparseable JSON / wrong shape | empty allowlist → `build_map` returns None; `log.error` once per build | fail-inert, not fail-degraded — but see the tripwire caveat in §12.2 |
| One row's `features_json`/`assets_json`/timestamp unparseable | skip the row, `parse_errors += 1` (surfaced in readout + job note) | a single corrupt row must not zero a league's memory; bounded because rows are bounded |
| `trade_matches` read raises | whole map degraded (single degraded bit — no partial-degrade state machine; M1-healthy-M2-degraded would need its own stamp vocabulary for zero operational value) | one bit, one triage path |
| Assembly stamping raises | already inside the impression-logging try/except (non-fatal by existing contract) | no new path |

*`MemoryError` → degraded is accepted: fail-open is the ruling posture (C1/NG1 — identity
is always a legal output), and the 500 ms discard bounds the damage window.

### 10.3 Concurrency statement

Job workers are daemon threads; a session's `TradeService` is shared across its jobs.
Negmem adds **zero shared mutable state**: no module global (T1), no instance attribute
(L-8), a frozen map passed by argument, and thread-local `_c` reads at seams. The only
cross-thread writes are the job-dict note (under `_trade_jobs_lock`, existing discipline)
and log lines. A concurrent same-session job builds its own map from its own reads —
mixed-map decks are impossible by construction, not by convention. Re-entrant streaming
callbacks touch only `new_cards`/`_dedup_and_sort` (§7.1 proof).

---

## 11. Knobs, flag, allowlist — registration (R10's triple, CI-enforced)

| Knob | Seed (`_MODEL_CONFIG_DEFAULTS`) | Consulted | Arm-A disposition sentence |
|---|---|---|---|
| `negmem_strength` | 1.0 | seams via `_c` (M1 ONLY — never governs M2) | **pinned 0.0 in `MODEL_A_PROFILE`** — arm A is the pre-negmem engine; 0 is the byte-identical M1 disable (M1-scoped per HLD §5.3) |
| `negmem_floor` | 0.6 | build (cell clamp) + seams via `_c` | not pinned — floor is unreachable at strength 0 |
| `negmem_min_evidence` | 3.0 | build (pass-in) | not pinned — build-time, strength-0 makes it moot for arm A |
| `negmem_halflife_days` | 45.0 | build (pass-in) | not pinned — same reason |

Registration is a **five-point** change and every point has an existing tripwire:
(1) `_MODEL_CONFIG_DEFAULTS` seed rows (`database.py`); (2) `_DEFAULT_CFG` entries
(`trade_service.py` — D-8: `snapshot_config()` iterates `_DEFAULT_CFG` via `_c` per arm
inside each arm's context, `bakeoff_runner.py:423-433`, so registration alone yields
`config_json` coverage including arm A's strength-0 delta); (3) `_PINNED_KNOBS` additions
in `test_bakeoff_arm_a_golden.py:496-542` (the inventory test `:545-559` fails by name
otherwise); (4) `MODEL_A_PROFILE["negmem_strength"] = 0.0` (`bakeoff_profiles.py:69-87`;
the profile-names-real-knobs test `:562-567` covers deletion drift); (5)
`docs/config-reference.md` rows. The arm-A golden needs **no recapture**: the golden runs
flag-off (no map ⇒ seams never execute), and the profile pin adds a key `_cfg_override`
merely overlays — `snapshot_config` output changes, deck bytes do not (T-2 asserts this
pair explicitly).

Flag: `trade.negmem` — `FLAG_KEYS` + `DEFAULT_FLAGS` (False) in `feature_flags.py`,
`config/features.json` (false), `backend/tests/fixtures/flags/release.json` (the mirror
test fails otherwise).

Allowlist (L-11): `config/negmem_allowlist.json` = `{"league_ids": ["..."]}`; tracked,
git-deployed (the `tester_allowlist.json` precedent, `experiments.py:87` — chosen over
env vars because Render ignores `render.yaml` envVars, per the onboarding-v2 rollout
record). Read on every `build_map` call (one small file read per job; no cache to go
stale). Missing file ⇒ feature inert with the flag ON — the SAFE default for the dark
phase, and the reason §12.2's tripwire is allowlist-scoped.

---

## 12. Observability

### 12.1 Readout (R8)

`negmem_readout(...)` returns
`{user_id, league_id, as_of, ver, degraded, build_ms, parse_errors, allowlisted: bool,
cells: [{partner, family, n_raw, n_decayed, mult, floored, tags_summary}],
partner_mults: {partner: m}, acceptance_stats: {partner: [accepts, responses]},
netting_events: int}`. It calls the same builder with the allowlist check **bypassed** and
reports `allowlisted` as data — an operator diagnosing "why no stamps in league X" needs
the map the league WOULD have, plus the fact that it isn't allowlisted; a readout that
returns None there is a tautology. Route: `GET /api/admin/negmem/readout?user_id=&league_id=[&as_of=]`,
`_require_cron_auth()` (fails closed in prod), knobs read via `ts._c` at request time,
`owner_alias` built from `league_members` rows. New route ⇒ `docs/api-reference.md` row
(§15 docs table). This readout is the substrate of the operator TestFlight checklist
(D-056): the checklist's expected values are readout fields, so the operator verifies
runtime behavior against numbers, not vibes.

### 12.2 Stamp-rate tripwire (allowlist-scoped denominator)

```sql
SELECT substr(di.served_at,1,10) AS day, di.model_arm,
       COUNT(*) AS rows_,
       SUM(CASE WHEN di.features_json LIKE '%"negmem"%' THEN 1 ELSE 0 END) AS stamped
FROM deck_impressions di
WHERE di.league_id IN (<allowlisted league ids — substituted by the readout pack from
                        config/negmem_allowlist.json, NEVER hardcoded>)
  AND substr(di.served_at,1,10) >= :flag_on_day
GROUP BY 1, 2
```
`LIKE '%"negmem"%'` is deliberate: dual-dialect (no JSON operator), and the key string
cannot appear inside any value we write (no free text enters features_json — the one
free-text field in this family is quarantined in `trade_pass_reasons.free_text`,
`database.py:903-905`). Expected 100% per (day, arm) while ON∧allowlisted; flag ON + rate
< 100% = builds failing or plumbing dropped — one SQL from visible (HLD §3.2 tripwire 2).
Runbook lines (numeric, HLD §3.2/§5.3): degraded rate > 1% of jobs over 24 h ⇒
`negmem_strength = 0` and investigate; triage order stamp rate → degraded notes
(`negmem_note` on jobs / log lines) → knob triple. **Caveat carried from §10.2:** an
unparseable allowlist file makes leagues silently non-allowlisted — the tripwire's
denominator goes to zero rather than alarming; the `log.error` plus the readout's
`allowlisted` field are the compensating checks, and the runbook names "denominator
empty" as itself a triage trigger.

### 12.3 RFPS + the R-X frozen cohort

`rfps_sql()` embeds `admission_sql()` and documents: numerator = viewed pass/NI outcomes
whose card's `(partner, family)` cell held ≥ `negmem_min_evidence` decayed units **at
`served_at`** (computed by replaying the builder with `as_of = served_at` — the same
Python, guaranteeing metric/map agreement); the pre-registered reason-less-rejection rule
(any admitted `(P,✱)` cell ≥ threshold) verbatim from PRD §4.2; the global-id→league-id
mapping note (R9). **R-X artifact:** at pre-registration, a committed JSON file
`docs/plans/negative-results-memory/rfps-baseline-<ISO-date>.json`:
`{"frozen_at": ..., "window": [...], "rows": [{"impression_id": ..., "partner": ...,
"family": ..., "n_decayed_at_serve": ...}], "admission_ver": NEGMEM_VER}` — the baseline
cohort snapshot by impression_id + cell assignment. Window-close evaluation runs on state
frozen at close; the family switch-rate inside the window (`trade_pass_reasons.switched_from`
non-NULL share) is reported alongside; switch-rate > 5% ⇒ extend per §8.3's ladder.

### 12.4 GR4 joint-multiplier audit

Non-bake-off rows: `joint = negmem_stamp.m × (final_score / base_score)`. **No m² —
verified against the write path:** `base_score` is the card's `composite_score` at logging
(`server.py:4213`), which on the serving/gen_v2 paths already CONTAINS the negmem multiply
(applied at creation, §7.1/§7.2); `final_score` is the ordering key (`:4229`) whose delta
over base is exactly the post-generation stack (Thompson × fatigue × taste × diversity).
So the ratio excludes negmem's own multiply by construction and the product counts m
exactly once. Thompson enters the joint via `final/base` and is *separately* recoverable
from the `propensity` column (`database.py:508`) for isolation. Fit rows: `final == base`
on bake-off decks ⇒ joint = m (uniform). Pollution decision (L-12): the A6 diversity
penalty rides `final/base` and is not a "soft personalization layer", so it inflates the
apparent joint downward; **accepted** — the 0.15 bar has margin (four layers at their
floors: 0.6 × 0.7 × 0.25 × 0.5 = 0.0525 is the theoretical worst without negmem even
firing; GR4's job is trend detection, and a diversity-implicated p5 approaching 0.15
triggers the revisit: stamp `fatigue_m`/`taste_m` under the same uniformity rule then,
not now). Breach remedy rides the HLD ladder: floors raised; a breach plausibly
originating in the acceptance prior takes `gen2_accept_prior_strength = 0` alongside
`negmem_strength = 0`.

### 12.5 Rollback ladder (deploy-free at every rung, restated)

`trade.negmem` off (everything, incl. M2 feed) → `negmem_strength = 0` (M1 inert; M2
still feeds; map still builds; stamps still flow `{m:1.0}`) → `negmem_floor = 1.0`
(diagnostic: clamp forces identity, stamps carry m=1.0 with keys). M2's independent kill:
global `gen2_accept_prior_strength = 0` (feed-guard structural, §8.3). Flag/knob flips at
bake-off round boundaries only (GR3).

---

## 13. Byte-identical-off proof, per path (C1, assembled from the parts above)

Flag OFF ∨ not allowlisted: map never built (§10.1 guard) → `negmem` key absent from
`_generate_kwargs` → `negmem=None` default in every signature → every seam guard
(`if negmem is not None` / `eff_by_uid` empty / `negmem_mult_by_uid=None`) short-circuits
before any arithmetic → no `round()` calls, no attribute writes → `negmem_ctx=None` at
assembly → no `features_json` key → M2 kwarg absent at both call sites. Byte-identical in
full. `negmem_strength = 0`: `effective_mult` returns exactly 1.0 (§6.2 row 1), seams skip
(no multiply, no round), stamps follow the trichotomy (`{m:1.0}` on every row — the
deliberate HLD strengthening over PRD R7, golden-tested against stamp-inclusive fixtures);
the ONE exception: arm C may still differ via the M2 feed, which `negmem_strength` does
not govern — its kill is `gen2_accept_prior_strength = 0`, and golden (b) sets BOTH.

---

## 14. Test plan — every invariant with the sabotage that proves the test can fail

Shared fixture rule (HLD round-3): T-2/T-11/T-12 run against a fixture whose map yields
m < 1.0 on at least one non-A arm in the same job — no vacuous passes. Harness: in-memory
SQLite engine patch (pattern 1, `tests/CLAUDE.md`), plus one Postgres-syntax smoke via
`sqlalchemy.text` compilation against the `postgresql` dialect (T-15 — catches accidental
SQLite-only syntax without needing a live PG).

| # | Invariant | Test | Named sabotage (must go RED) |
|---|---|---|---|
| T-1 | C1 flag-off byte-identical (serving + fit + arm C kwargs) | golden: full deck + features_json bytes, flag off | make assembly stamp `{m:1.0}` when `negmem_ctx is None` |
| T-2 | C1 strength-0 deck-content parity, stamp-inclusive | golden at flag ON, strength 0: scores/order byte-equal, every row `{m:1.0}` | bake strength into `build_map` cell mults (the overlay-blind read) — arm-A parity then fails while T-1 stays green |
| T-3 | C1 arm-C dual-kill parity | golden with `negmem_strength=0` ∧ `gen2_accept_prior_strength=0` | remove the feed guard (pass stats at strength 0) |
| T-4 | C2 clamp: eff ∈ [floor, 1.0]; sink-never-rise; strength>1 / <0 / NaN / floor>1 | property test over the §6.2 table | delete the upper `min(1.0, ·)` clamp — negative strength yields eff>1 |
| T-5 | C2 netting bounds: cell never negative; one like ≤ 1 unit/cell | unit: 5 evidences + 1 like ⇒ n_decayed ≥ 3.9 (decay-adjusted); 1 evidence + 5 likes ⇒ 0.0, mult 1.0 | replace fold-clamp with end-clamp — early-like credit banking drives an assert on the like-before-evidence case |
| T-6 | D-5 combine = MIN | fixture partner with cells 0.9/0.7 ⇒ m_partner 0.7 | switch to product (0.63) |
| T-7 | C4 M2 parity + empty-table | unit: E-B math at both call sites on both engines' empty result; `(0,0)` never in dict | make the aggregation emit zero-response keys |
| T-8 | R9 id conversion | co-owned fixture: co-owner's decline lands on canonical owner's key | drop `owner_alias` (stats key misses; assert fails on dict key) |
| T-9 | Undo pairing (L-2) | unit table: pass→undo; pass→undo→pass; like→undo; stray undo; dup pass + one undo; pass→like no-undo | make undo pop the OLDEST decision — the pass→undo→pass case flips |
| T-10 | C5 determinism | build twice at fixed `as_of` ⇒ maps equal to the bit; permute row insert order ⇒ still equal | use `datetime.now()` inside decay instead of `as_of` (or iterate a set for the fold) |
| T-11 | T1 live binding | monkeypatch `negmem.effective_mult` → deck order changes | change `from . import negmem as _negmem` to `from .negmem import effective_mult` — rebind no longer observed |
| T-12 | B2 provenance | bake-off fixture (m<1 on arm B): arm-A rows stamp exactly `{m:1.0, ver:1}`, arm-B rows the real m | recompute m at assembly via `effective_mult` + live `_c` |
| T-13 | Fit end-to-end ordering (restore_order dependency) | fixture where negmem swaps fit ranks; assert final interleaved deck order post-likes-you injection | apply eff after the 1e-9 round (C7c tie test also reddens) |
| T-14 | C3 batch stamp coverage (likes-you-led deck — the model_arm scar) | deck whose first entry is a likes-you injection: every row carries the key; injection row `{m:1.0, exempt}` | stamp only cards with `negmem_m` set |
| T-15 | Dual-dialect SQL compiles + day-prefix bounds | compile `admission_sql()`/M2 SQL under both dialects; boundary-day fixture: served 2026-08-20T00:00:00 admitted, 08-19T23:59 not | change bound to full-timestamp comparison vs 'Z' bind |
| T-16 | Leaf import contract | assert `negmem`'s module imports ⊆ {stdlib, feature_flags, database} | import trade_service in negmem |
| T-17 | Failure taxonomy | raise inside build ⇒ degraded map, job survives, every row `{m:1.0, degraded}`; KeyboardInterrupt propagates (subprocess-free: assert `except Exception` via raising KI in a patched reader) | catch `BaseException` |
| T-18 | Curve continuity + gate | mult(min_ev − ε)=1.0; mult(min_ev)=1.0; mult(min_ev+ε)<1.0; monotone | reintroduce the halfway-jump curve |
| T-19 | Knob inventory (existing test, extended) | `_PINNED_KNOBS` + `MODEL_A_PROFILE` additions land together | (self-enforcing: the existing test IS the tripwire) |
| T-20 | Relaxed-pass same-map consult | targeted-empty fixture: relaxed rerun cards carry same m as a direct run | drop `negmem` from `_v2_kwargs` |

TEST_LEDGER records each sabotage by name (repo sabotage discipline, `tests/CLAUDE.md`).

---

## 15. Migration, rollout, docs

**Schema migration: none** (NG6 — zero tables, zero columns; the stamp rides the existing
`features_json` Text). Nothing for `_migrate_db()`; nothing dialect-divergent to migrate.
The `negmem_` prefix stays reserved-unspent unless §3.4's measured failure triggers the
HLD §5.4 cache (its own scope block then).

Rollout order (PRD §6 severability respected): P0 = §8 (M2) + harness + T-3/T-7/T-8 ⇒
mergeable alone behind the flag; P1 = builder + seams + stamps + readout + knobs + goldens.
Dark (flag off, goldens green) → operator flips at a round boundary → allowlist the pilot
league → ≥4-week read → §8.3 graduation.

Docs table (gates item 3): `docs/api-reference.md` (readout route) · `docs/config-reference.md`
(flag, 4 knobs, allowlist file) · `docs/data-dictionary.md` (features_json.negmem payload
row) · `docs/glossary.md` (negmem, evidence cell, netting) · `living-memory/LLD.md`
(kwarg-threading + T1 conventions) · `docs/architecture.md` + `living-memory/HLD.md`
(new leaf module) · shared taxonomy v1.1.0 `shape_aversion` producer row (dependency:
taxonomy must be ON MAIN first — PRD §7 flag stands) · `docs/runbook.md` (§12.2 lines).
`docs/cross-client-invariants.md`: n/a (no client consumes the stamp in v1).

---

## 16. HLD contracts flagged (found while implementing on paper — flagged, not silently fixed)

1. **HLD §2.1 internal tension on build-knob reads:** the component diagram says
   build-time knobs are "read ONCE here, globally" *inside* `build_map`, while §7 tilts
   the knob-read path to pass-in-from-server. These cannot both be literal. This LLD
   implements pass-in (L-9) — it is the only reading consistent with D-2's leaf import
   list (negmem may import `database.get_config`, but the `gen2_*` default would then need
   duplicating — the stale-copy drift the HLD itself names) — and records that §2.1's
   phrase should read "resolved once per job, before any arm context".
2. **Leaf contract vs ADR-012:** §7 hands this LLD "co-owner canonicalization call sites"
   but D-2 forbids the only module that owns the predicate (`sleeper_roster`). Resolved by
   injection (`owner_alias`, L-10) — the predicate stays single-sourced server-side. If
   reconciliation prefers negmem importing `sleeper_roster` (it is itself a leaf), the
   D-2 import list needs amending first; this draft did not amend it.
3. **HLD §3.5 "degraded ⇒ the feed returns `{}`"** is implemented as kwarg-absence
   (§8.3) — behaviorally identical through `acceptance_prior` (`not {}` ≡ `not None`) and
   strictly stronger for C1 byte-parity. Flagged as a strengthening.
4. **HLD §5.3 "kill M2 via the GLOBAL knob only, never an arm overlay pin":** with the
   feed guard reading `_c` at the call sites (which the same HLD section mandates), a
   per-arm pin now ALSO safely empties the feed — the raw-unshrunk-ratio hazard the rule
   guards against is unreachable. The rule is kept as operational procedure; its stated
   rationale is obsolete. Reconciliation should re-word, not this draft.
5. **PRD R7 vs HLD §3.4 stamp scope** (influenced-only vs every-row) — already declared a
   deliberate strengthening by the HLD; carried, with L-15 adding `ver` to every variant
   (a further widening of the same divergence, +8 bytes/row).
6. **Legacy engine path** (`trade_engine_v2` flag OFF branch) receives no seam (§7.1
   caveat). The HLD's seam table silently assumes the v2/v3 stack is the serving engine —
   true in prod today; the assumption is now written down.

## 17. Open items for cross-review

- The §3.4 two-pass-fetch fallback threshold: fold into S6's measurement plan or drop?
- `evidence_for` payload: is the binding-cell `ev` alone enough for the readout-driven
  TestFlight checklist, or should the stamp carry both family evidences (+12 bytes)?
- T-17's KeyboardInterrupt assertion without a subprocess: acceptable as a patched-reader
  unit, or does review want the subprocess harness (slow) for fidelity?
