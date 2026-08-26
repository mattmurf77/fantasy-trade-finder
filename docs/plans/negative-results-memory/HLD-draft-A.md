# HLD — Negative-results memory (Draft A: Architecture-Coherence lens)

**Date:** 2026-08-21 · **Author:** Agent A (dual-agent HLD round 1)
**Requirements contract:** [PRD.md](PRD.md) (FINAL — R1–R11, NG1–NG9, C1–C5, GR1–GR4, §8.3 bind this design)
**Facts of record:** [research-verification.md](research-verification.md) ("memo") — §2h seams, §DC-1..10
**Gates:** [scope.md](scope.md) · Plan skeleton: [PLAN.md](PLAN.md) §2–3
All file:line citations verified on this checkout (`claude/vigilant-spence-8583f5`, branched from `origin/main` 451d2eb). Line numbers move; re-grep across merges.

---

## 1. Context & Goals

Rejected suggestions currently teach generation nothing family-shaped: the D-067 cooldown
is exact-pair and windowed, F3 fatigue needs the card to have been served, F5 taste never
reads `trade_pass_reasons`. This HLD designs the PRD's two mechanisms:

- **M1** — a per-(user, league) map of decayed, shrunk, reason-gated rejection evidence,
  keyed `(partner_league_id, reason_family)` with `reason_family ∈ {value, fit}` (PRD
  §2.2), consulted as a **soft, clamped, stamped score multiplier at generation time** in
  every arm (R3/R4).
- **M2** — feed gen_v2's ratified-but-unfed `acceptance_prior`
  (`backend/trade_gen_v2.py:283-308`) with real per-league-mate response stats at both
  call sites (`backend/trade_service.py:4001`, `backend/bakeoff_runner.py:1212`), flag-gated
  so flag-off arm C stays byte-identical (R5, C1).

Design bar, restated as architecture constraints: no per-candidate DB reads — one bulk
read per job (DC-1); no new tables — derive-on-read unless the S6 latency gate is
*measured* failing (NG6, DC-2); gates decide membership, this prior only decides order
(DC-3); byte-identical when `trade.negmem` is off or `negmem_strength = 0` (G4/C1);
league identity only (R9/DC-8); every influence stamped (R7), every state dumpable (R8).

Out of scope here (PRD non-goals): no suppression, no present-state evaluation, no value
grading, no UI, no modification of F3/D-067/F5/R4/Thompson semantics (NG1–NG9).

## 2. Architecture Overview

### 2.1 Components

```
backend/negmem.py                      NEW — leaf module (the suggestion_telemetry pattern)
server._run_trade_job                  builds the map once per job, threads it as a kwarg
trade_service._generate_trades_v2      M1 seam for the serving engine (v2-pair / v3 / consensus)
trade_gen_v2.generate_league_suggestions  M1 seam (new kwarg) + M2 acceptance_stats (existing kwarg)
trade_gen_fit.generate_fit_suggestions M1 seam (new kwarg, rank-key multiplier)
bakeoff_runner.gen_v2_cards            forwards both from the shared kwargs dict (arm C call site)
server._log_deck_impressions           R7 stamp into features_json (existing writer, one new key)
```

**`backend/negmem.py` is a LEAF — this is the load-bearing placement decision.**
Precedent: `suggestion_telemetry.py` ("This module is a LEAF: it imports feature_flags +
database …, never server.py" — `backend/suggestion_telemetry.py:12-16`, imports at
`:59-65`). negmem imports `feature_flags` and `database` only. It does **not** import
`trade_service`: knobs needed at build time (`negmem_floor`, `negmem_min_evidence`,
`negmem_halflife_days`) are read through `database.get_config()` with
`_MODEL_CONFIG_DEFAULTS` fallback (`backend/database.py:2188`, `:4166`), and
`negmem_strength` is deliberately **not** read here at all (see D-6). Because the engine
modules receive the map as plain data (a dataclass of dicts) and never import negmem,
there is no import cycle in either direction — unlike the `trade_optimizer` ↔
`trade_service` pair that needs a lazy import (`trade_service.py:4991-4993`).

**Public surface** (signatures finalized in the LLD; shapes fixed here):

```python
@dataclass(frozen=True)
class NegmemMap:
    cells: dict[tuple[str, str], Cell]   # (partner_league_id, reason_family) → Cell
    acceptance_stats: dict[str, tuple[int, int]]   # M2: league-mate uid → (accepts, responses)
    as_of: str                           # ISO ts the map was built at (R6)
    ver: int                             # builder version, stamped (R7)
    def partner_mult(self, partner_league_id) -> tuple[float, list[str]]
        # combined per-partner base multiplier in [negmem_floor, 1.0] + the cell keys
        # that produced it; (1.0, []) for identity — see D-5

def build_map(user_id, league_id, as_of=None) -> NegmemMap        # R3, R6, C5
def negmem_readout(user_id, league_id, as_of=None) -> dict        # R8: every cell,
        # raw + decayed counts, netting events applied, mult, floored?, context tags
```

- `Cell = {n_raw, n_decayed, mult}` per R3; identity below `negmem_min_evidence`;
  `mult` clamped to `[negmem_floor, 1.0]` at build.
- **Admission (R1)** and **like-netting (§5.3)** both live inside `build_map` — the
  builder is a pure function of (user, league, as_of) over admission timestamps and
  netting-event timestamps, which is exactly what makes R6 as-of reconstruction and C5
  determinism one property instead of two.
- **M2 aggregation** is a second query inside the same build (one bulk read *per job*,
  not per candidate — DC-1 counts round trips at candidate granularity; the build is 2–3
  bounded queries at job start, same shape as `_load_presentment_exclusions` +
  `_deck_fatigue_state` today, `server.py:5503-5505`, `:4430-4479`).

### 2.2 Who calls what

1. **`server._run_trade_job`** — immediately after the R4 exclusion build
   (`server.py:5503-5505`), gated on `FLAGS.trade_negmem` (+ the league allowlist, LLD):
   `negmem_map = negmem.build_map(g_user_id, league_id)`; else `None`. Timed for S6.
   Added to `_generate_kwargs` (`server.py:5644-5671`) as `negmem = negmem_map` — which
   automatically reaches the organic call (`:5696`), arm A/B via `generate(**kwargs)`
   (`:5680-5681`), and arms C/fit via `gen_v2_cards` / `gen_fit_cards`, which already read
   the same kwargs dict (`bakeoff_runner.py:1208-1231`).
2. **`trade_service._generate_trades_impl`** — accepts `negmem: NegmemMap | None = None`,
   stores it per-job with overwrite-per-call semantics, exactly like `exclusion_keys`
   (`trade_service.py:3983` — None ⇒ identity, never keep-previous). Forwards to the
   gen_v2 hand-off (`:4001-4033`) as `acceptance_stats=negmem.acceptance_stats` and
   `negmem_mults=<per-partner dict>`; consults it in the v2-serving loop (§2.3).
3. **`bakeoff_runner.gen_v2_cards`** — forwards `kwargs.get("negmem")` the same two ways
   into `generate_league_suggestions` (`bakeoff_runner.py:1212-1231`); `gen_fit_cards`
   forwards `negmem_mults` into the fit arm. Flag off ⇒ the kwarg is absent ⇒ both
   default to `None` ⇒ arm C byte-identical (C1's arm-C clause).
4. **`server._log_deck_impressions`** — stamps `features_json.negmem` from a card
   attribute set at consultation time (§3.4). The key rides **inside** `features_json`,
   dodging the executemany first-row-keys trap the fit keys already document
   (`server.py:4197-4202`).
5. **Likes-you injector** — untouched (R4 exemption): it runs post-generation in server
   (`server.py:5748-5759`) and never consults the map.

### 2.3 ONE consultation design, four paths

The consultation is **one rule** — *after all gates, multiply the candidate's ranking
score by the partner's effective multiplier, exactly once, at candidate-creation time* —
instantiated at three seams (the serving engine's loop covers both "v1" consensus and v3
optimizer cards):

| Path | Seam (verified) | How the rule lands |
|---|---|---|
| **Serving engine (arms A/B): v2-pair, v3 optimizer, consensus fallback** | the per-member loop of `_generate_trades_v2`, `trade_service.py:4943`; all three sub-generators return into it (`:4986-5059`) | One new block in the existing per-member bounded-multiplier stack — after aggression (`:5177-5196`), before the match-context stamp (`:5197`): `eff = _effective(negmem, member.user_id)`; if `eff != 1.0`: `c.composite_score = round(c.composite_score * eff, 3)` + set `c.negmem`. Identical discipline to partner-fit (`:5070`), need-fit (`:5087`), block-boost (`:5103`), outlook-direction (`:5120-5127`, incl. its `_m != 1.0` skip), aggression (`:5195`). |
| **gen_v2 (arm C + the dark `trade_gen.v2` serving branch)** | per-member loop, `trade_gen_v2.py:939-975` | New kwarg `negmem_mults: dict[uid → base_mult] | None = None` (`:862` region). Applied **pair-constant** — the same property `accept_prior`/`priority_weight` already have ("prior/priority are pair-constant here", `:679-681`): within-pair ordering untouched, cross-pair ranking shifted. Exact multiplication site (fold into `weight` at `:952` vs. post-`_dedup_batch` score pass) is an LLD choice; the HLD requirement is pair-constant, before cross-pair ranking, stamped on the emitted cards. |
| **fit arm** | rank scoring, upstream of `_apply_post_filters` (`trade_gen_fit.py:753`) | New kwarg `negmem_mults`; multiplies the **rank key only**, never the `fit` payload — `you/them/aggregate` are user-facing diagnostic values (`:733-744`) and corrupting them would leak the prior into displayed data. Memo §2h's ruling stands: "a *soft* prior belongs in the rank score", not at post-filter step 5 (that seam is for hard membership tests). |
| **M2 (gen_v2 only)** | `acceptance_stats` kwarg (`trade_gen_v2.py:862` → `:951` → `:655`) | The hook already exists; we feed it. No new math (R5). |

Membership is never touched: every seam multiplies a score **after** that path's gates
have already decided the candidate set (DC-3; taste's contract restated at
`taste_service.py:34-38` is the house articulation). `eff ∈ [negmem_floor, 1.0]` —
sink-never-rise, no gated-card rescue, no exclusion (C2, NG1).

**Why inside each arm's scoring and not a shared post-gate pre-rank step:** a single
post-generation multiplier map in the worker (the `_deck_fatigue_multipliers` pattern,
`server.py:4482-4541`) was Draft A's simplest candidate and is **rejected** — the memo
already names the two disqualifiers (§2h row 4): (a) bake-off decks bypass the entire
post-generation reranker stack (`server.py:5890-5910`, D-086), so the prior would vanish
exactly where GR3 requires it to be measurable per arm; (b) post-generation cannot shift
which candidates win an arm's *internal* ranking (gen_v2 returns a ranked survivor set
with tiers; fit ranks before post-filters), so the prior would act on presentation, not
generation — failing G1's "at generation time, in every arm". A generation-time prior is
part of the model under test; it must live inside the arms and ride the config snapshot
(DC-7). See D-4 for the third rejected variant.

## 3. Data Model & Flow

### 3.1 No new tables (NG6)

v1 persists nothing. All state derives at job start from the existing spine:

- `deck_impressions` (`database.py:500-608`) — frozen `features_json`
  (`partner_user_id`, `lane`, `user_value_basis`, shape), `trade_intent` column,
  `is_ghost`, `served_at`.
- `deck_outcomes` (`database.py:741-761`) — `pass`/`not_interested`/`viewed`/`like`/`undo`,
  append-only.
- `trade_pass_reasons` (`database.py:873-943`) — the reason record; `key_source='impression'`
  rows join the spine; upsert caveat honored in R6.
- `trade_decisions` (`database.py:319-337`) — `retracted_at` for the R1(d) dual check.
- `trade_matches` (`database.py:417-436`) — M2's accepts/responses source.

Deletion of source rows is deletion of memory — no orphaned aggregates (PRD §5.3, D3(c)).

### 3.2 Data flow (M1)

```
 SPINE (append-only)                         BUILD (once per job, backend/negmem.py)
┌──────────────────────┐
│ deck_impressions     │   ADMISSION (R1, closed list — one query)
│  features_json       │──┐  (a) viewed-gated: outcome row requires a viewed row (F1 join)
│  (frozen at serve)   │  │  (b) reason-carrying: ⨝ trade_pass_reasons
│ deck_outcomes        │──┤      key_source='impression', family ∈ {value, fit}  (R2)
│  pass/not_interested │  │  (c) is_ghost ≠ 1
│  viewed / like/undo  │  │  (d) not retracted: retracted_at IS NULL ∧ no paired undo
│ trade_pass_reasons   │──┤      (join path = LLD, R1(d) note)
│ trade_decisions      │──┘  (e) clean epoch: served_at ≥ 2026-08-20, ∉ D-091 window
└──────────────────────┘        │
                                ▼
              in-memory EVIDENCE ROWS (never stored)
              (league_id, user_id, partner_league_id, reason_family,
               shape_bucket, context_tags{lane, user_value_basis,
               trade_intent}, ts)                       (R1, R11: recorded-not-consulted)
                                │
        viewed LIKES toward P ──┤  LIKE-NETTING (§5.3): nets against every (P, ✱)
        (same admission gates   │  cell; mechanism (decrement/reset) = LLD; netting
         a,c,d,e; no reason)    │  events share the as-of domain (R6)
                                ▼
              CELLS  {(partner, family): n_raw, n_decayed}
                 n_decayed = Σ 2^(−Δt / negmem_halflife_days), net of netting
                                │
                                ▼
              SHRINK + CLAMP (R3): n_decayed < negmem_min_evidence ⇒ mult = 1.0
                 else mult = g(n_decayed)  clamped to [negmem_floor, 1.0]   (g = LLD)
                                │
                                ▼
              NegmemMap ── partner_mult(P): combine (P,value)·(P,fit), re-clamp  (D-5)
                                │
        ┌───────────────────────┼──────────────────────────┐
        ▼                       ▼                          ▼
  CONSULTATION            CONSULTATION                CONSULTATION
  serving loop            gen_v2 pair loop            fit rank key
  ts.py:4943 stack        tgv2.py:939-975             tgf.py pre-:753
  eff = 1 + s·(m−1)  (s = negmem_strength via each arm's _c — D-6)
  composite_score ×= eff   score ×= eff (pair-const)   rank_key ×= eff
        │                       │                          │
        └───────────────────────┴──────────────────────────┘
                                ▼
              STAMP (R7): card.negmem = {m: eff, keys, ev, ver}
                                ▼
              deck_impressions.features_json.negmem   (server.py:4135-4233 writer)
                                ▼
              READOUT (R8) + RFPS (§4.2) + GR4 joint audit — SQL over stamps
```

### 3.3 M2 flow (flag-gated with M1 — R5, C1, C4)

```
trade_matches (user_a/b_decision, decided_at, league_id)
      │  one aggregation query inside build_map; lookback (default 180d)
      │  applied IN THE QUERY — the E-B formula itself is untouched (R5)
      ▼
acceptance_stats: {league-mate uid → (accepts, responses)}
      │            uid = the id space league.members uses (= what
      │            trade_gen_v2.py:951 keys on); mapping documented per §4.2
      ├─► call site 1: trade_service.py:4001-4033 (the trade_gen.v2 serving
      │   branch — currently dark, flag false) — kwarg added iff negmem is on
      └─► call site 2: bakeoff_runner.py:1212-1231 (arm C) — same rule
              ▼
trade_gen_v2.acceptance_prior (:283-308, math untouched)
   p = (accepts + m·p0) / (responses + m)   knobs already seeded
              ▼
score = joint_gain × accept_prior × priority_weight   (:655)
```

Flag OFF ⇒ **the kwarg is not passed** (not "passed as None" from a built map — not
passed), so arm C's call is textually and behaviorally identical to today (C1). S4
expects a near-uniform read until decline volume exists — not a bug (memo §2c).

### 3.4 The stamp (R7)

Consultation sets `card.negmem = {"m": <eff>, "keys": [<cell keys hit>], "ev":
{<per-key n_decayed>}, "ver": <builder ver>}` only when `eff != 1.0`. The impressions
writer adds `features["negmem"] = card.negmem` only when the attribute exists — flag-off
and uninfluenced rows stay byte-identical, influenced rows can never miss the stamp
because the same code path that multiplied set the attribute (C3's 100% is structural,
not disciplinary). Data-dictionary row per scope §1.

## 4. Key Design Decisions (mini-ADRs)

**D-1 — Derive-on-read; no `negmem_*` table in v1.**
*Decision:* build the map from the spine at job start; persist nothing (NG6).
*Why:* house style — learned state derives, tables are for durable promises (DC-2:
fatigue state and Thompson posteriors are both derived on read, `server.py:4430-4479`,
`:3666-3724`); volumes are small (~845 outcomes lifetime, ~120 clean reason rows/week —
PRD §2.2); derive-on-read makes deletion structural (D3(c)) and R6 as-of trivial.
*Gate:* S6 measures build p95 inside the job budget; only a *measured* failure admits a
materialized cell table, as a cache of the same builder (same math, refreshed from the
same events), never a second source of truth.
*Rejected:* write-time aggregates (a cron or outcome-hook maintaining cells) — mutates
state no other learner mutates, breaks as-of replay, and the volume doesn't justify it.

**D-2 — Leaf-module placement: `backend/negmem.py`, imports flags + database only.**
*Why:* the `suggestion_telemetry` precedent is the only sanctioned shape for a new
learner module (`suggestion_telemetry.py:12-16`); `database.py` must never import
`server.py` and negmem must be importable by tests without the app. Engines never import
negmem (the map arrives as data), so no cycle exists and no lazy-import contortion is
needed.
*Rejected:* putting the builder in `server.py` (buries R8's readout behind the app; the
readout must be callable from scripts/pytest), or in `trade_service.py` (would force
`database`-heavy query code into the engine module and tempt a `trade_service` import
from database-side helpers).

**D-3 — Map threading: explicit kwarg, job-scoped, overwrite-per-call.**
*Decision:* `server._run_trade_job` builds once; `negmem=` rides `_generate_kwargs` into
`generate_trades` and both bake-off fan-out lambdas (`server.py:5680-5685`);
`_generate_trades_impl` stores per-job exactly like `exclusion_keys`
(`trade_service.py:3983` — kwarg replaces stored state every call, None ⇒ identity).
*Why:* this is the established seam for per-job generation inputs (`exclusion_keys`,
`server.py:5503→5669→trade_service.py:3983`; `past_decision_keys` to all four paths,
memo §2h). Explicit parameters keep the C1 proof legible: grep the kwarg, see every
consumer.
*Rejected — thread-local context* (the `_cfg_override`/`r4_bypass`/`stud_tax` pattern,
`trade_service.py:991-1048`): those exist for values that must cross an interface that
*cannot be widened* (arm callables bound by the caller, `bakeoff_runner.py:1136-1143`) or
must overlay module config per-thread. The map crosses interfaces we own; hidden state
would make byte-identical-off a runtime property instead of a structural one.
*Rejected — constructor state on `TradeService`* (the `past_decision_keys` slot,
`:3848-3857`): the service lives for the session; the map must be as-of the job
(freshness — a swipe between jobs must move the next map, and `past_decision_keys`'
session-staleness is a known wart, `server.py:11671-11694`'s live-bind workaround).
*Trap noted (T1, `docs/plans/fit-challenger/CRITIQUE-of-A.md:17`):* consumers reading
knobs at the seams import the **accessor** (`_c` / `ts._c`), never `from .trade_service
import _cfg` — module-attribute import binds the object at import time and goes stale
across `reload_config()`. negmem itself binds no engine state at import.

**D-4 — Consultation inside each arm's scoring; not post-gen, not `_dedup_and_sort`.**
*Decision:* per §2.3.
*Rejected — shared post-gen multiplier step:* fails GR3 + G1 (see §2.3 close).
*Rejected — the shared kill-site `_dedup_and_sort`:* superficially attractive (single
seam for the whole serving engine, `trade_service.py:4180`), but it re-runs on every
streaming snapshot **over the same accumulating card list** (`:4152-4157`, `:5202-5207`)
— an in-place `composite_score` multiply there compounds once per opponent callback.
Guarding with an already-stamped check would make the stamp load-bearing for correctness;
the per-member loop applies exactly once at card creation with no guard needed. It also
covers only the serving engine, so gen_v2/fit would need their own seams anyway — no
seam-count saving.
*Rejected — extending `past_decision_keys` with "doomed family" keys:* that is the
key-set membership seam (memo §2h close), i.e. an exclusion — NG1 territory, and exactly
the fourth hard filter this feature exists not to be.

**D-5 — The map collapses to a per-partner multiplier at consultation; families key
evidence, not candidates.**
*Decision:* `partner_mult(P)` combines the (P, value) and (P, fit) cells —
`clamp(mult_value × mult_fit, negmem_floor, 1.0)` proposed, min() the named alternative;
LLD finalizes with the fixture set.
*Why:* a reason family describes why the *user rejected*, not a property a candidate
card possesses — no card-side feature maps a fresh candidate to `value` vs `fit`, so at
the v1 key the honest consultation grain is the partner (G1's own wording down-weights
"a candidate toward a partner whose cell holds sufficient evidence"). Families still
earn their keep at v1: admission gating (R2 — `other` accrues nothing), independent
decay/netting bookkeeping, the readout, RFPS's numerator, and the P2 path where
shape-augmented keys make consultation finer without redesign (G5).
*Rejected:* attributing candidates to families via card features (e.g. fairness margin ⇒
"value") — invents an inference the PRD never ratified and would silently change which
cell fires; deferred to P2 alongside shape keys where the data can earn it.

**D-6 — `negmem_strength` applies at consultation time through each arm's `_c`, not
baked into the map.**
*Decision:* cells carry the base `mult` (floor-clamped, strength-free);
each seam computes `eff = clamp(1 + _c("negmem_strength") · (mult − 1), negmem_floor,
1.0)` and skips the multiply when `eff == 1.0` (the `:5125` `_m != 1.0` pattern).
*Why:* (a) `strength = 0` short-circuits to no multiply, no round-trip through `round()`,
no stamp — byte-identical structurally (C1, DC-9); (b) `_c` honors the thread-local
overlay (`trade_service.py:1004-1010`), so **arm A's disposition can be
`MODEL_A_PROFILE["negmem_strength"] = 0.0`** — the pre-wave engine stays negmem-free per
its charter without any negmem-specific bypass machinery (the R10 arm-A disposition
sentence, decided by the operator at knob registration); (c) deploy-free revert is one
knob PUT.
*Rejected:* baking strength into the map at build (arm-A could then only opt out via a
special-cased bypass — a second `r4_bypass`-shaped mechanism for no gain).

**D-7 — Like-netting lives in the builder, as events in the as-of domain.**
*Decision:* viewed likes toward P (same admission hygiene: viewed-gated, non-ghost,
non-retracted, clean-epoch) enter `build_map` as netting events folded in timestamp
order against every (P, ✱) cell; magnitude and decrement-vs-reset are LLD (§5.3 requires
only: positive evidence nets, and the mechanism is visible in the readout).
*Why:* R6 makes the builder a pure function over admission **and** netting timestamps —
netting anywhere else (consultation-time adjustment, a separate positive map) would
split the as-of domain and make `negmem_readout` lie about what generation saw.
*Rejected:* netting at consultation (two data sources to stamp), or treating likes as
negative-evidence deletions (destroys n_raw bookkeeping the readout and RFPS need).

**D-8 — Bake-off citizenship = `_DEFAULT_CFG` registration; verified mechanism.**
All four knobs get `_MODEL_CONFIG_DEFAULTS` seed rows (`database.py:2188` — the
settability rule) **and** `trade_service._DEFAULT_CFG` entries (`trade_service.py:40`).
`snapshot_config()` returns `{k: _c(k) for k in _DEFAULT_CFG}` **per arm, inside each
arm's own override context** (`bakeoff_runner.py:423-433`) into
`bakeoff_runs.config_json` (`:1059-1077`, `:1131`) — so negmem knobs (including arm A's
strength-0 delta) are snapshotted per run with zero new snapshot code, satisfying R10 +
GR3's "knobs snapshotted" clause. Flag flips align to round boundaries (GR3; ADR-014) —
an operator procedure, recorded in the rollout runbook, not enforceable in code here.

**D-9 — M2 rides the NegmemMap; one flag for both mechanisms.**
*Decision:* `acceptance_stats` is a field of the same built map; both gen_v2 call sites
pass it only when the map exists (flag ON). No separate M2 flag.
*Why:* R5 says flag-gated with M1 under `trade.negmem`; one build = one as-of = one S6
measurement; P0 severability is preserved because M2 ships first simply by building a map
whose M1 cells are empty (builder's M1 query lands in P1) — the P0/P1 phasing is a
build-order fact, not an architectural fork.
*Rejected:* a standalone M2 aggregation called from the two sites directly — two DB-read
seams to audit, two as-of clocks, and the fit/serving arms would still need the map
threading anyway.

## 5. Cross-Cutting

### 5.1 C1 — byte-identical-off proof, per path

| Path | OFF means | Proof |
|---|---|---|
| serving engine (arms A/B) | `negmem` kwarg never in `_generate_kwargs`; stored map None; seam block skipped before any arithmetic | golden pytest: full-deck serialize, flag off vs. absent-entirely (pre-merge base) — byte equality; plus strength-0 golden (flag on, s=0) |
| gen_v2 serving branch + arm C | `acceptance_stats` and `negmem_mults` kwargs not passed → both default None (`trade_gen_v2.py:862`, new kwarg same) → `acceptance_prior` returns p0 exactly as today (`:303-304`) | arm-C golden through `bakeoff_runner.gen_v2_cards`; unit: kwargs-not-passed assertion on both call sites |
| fit arm | `negmem_mults=None` default; rank key untouched | fit golden (existing fit fixture set) |
| impressions | no `card.negmem` attr ⇒ no `features_json` key ⇒ insert rows byte-identical (the F5/F7/bakeoff conditional-key precedent, `server.py:4175-4212`) | row-level golden on `features_json` |
| likes-you | never touched | code-walk citation only |
| strength-0 (flag ON) | `eff == 1.0` ⇒ skip branch: no multiply, no `round()`, no stamp | golden + unit on the skip predicate (C2's clamp suite) |

### 5.2 Observability

- **R7 stamps** — §3.4; stamp coverage audited by C3 SQL (influenced ⇒ stamped is
  structural; the SQL proves the converse direction: stamped ⇒ mult recorded ≠ 1.0).
- **R8 readout** — `negmem_readout` dumps every cell (raw, decayed, netting applied,
  mult, floored?, context tags) for scripts/pytest; companion SQL joins per-arm stamp
  rates into the existing readout pack, documents the §4.2 partner-id mapping, and the
  operator TestFlight checklist is written against it (scope §3).
- **GR4 joint-multiplier audit** — from stamps: negmem's `m` (features_json.negmem),
  taste/fatigue/Thompson's combined effect recoverable from `final_score / base_score`
  and `propensity` on the same row (`server.py:4227-4229`, `database.py:497-499`). The
  audit SQL computes p5 of the joint product per arm; breach ⇒ floors raised (the
  tripwire's response is a knob change, deploy-free). Exact SQL → LLD; the HLD commitment
  is that every factor is already on the impression row — no new logging needed.
- **S6** — build latency logged per job next to the existing job timings; feeds the D-1
  gate.

### 5.3 Rollback ladder

1. **`negmem_strength = 0`** (knob PUT, deploy-free): consultation inert, stamps stop,
   map still builds → readout stays warm for diagnosis. Guardrail-breach response
   (§8.3), window censored at the flip.
2. **`trade.negmem` off** (flag reload): no build, no reads, no M2 kwarg — full revert
   to today's bytes.
3. **Floors up** (`negmem_floor` toward 1.0): GR4's graduated response.
4. Code revert: nothing else depends on the module (leaf) or the kwargs (all default
   None) — a revert is one commit with no schema to unwind (NG6).

### 5.4 Identity hygiene (R9)

Map keys and `negmem_mults` keys are **league identities** — the id space
`league.members[*].user_id` / card `target_user_id` already use (what
`features_json.partner_user_id` freezes, `server.py:4148`), canonicalized through the
ADR-012 owner predicate: co-owner aliases resolve to the roster's primary `owner_id`
before keying, so a co-owned partner accrues one cell, not two. Account ids
(`sess["user_id"]` space) never enter the builder's queries or the map (DC-8). The §4.2
readout SQL documents the spine-id → map-key mapping so the RFPS join can't silently
violate this. LLD specifies the canonicalization call sites (`sleeper_roster.
canonical_owner_id`).

### 5.5 Privacy (PRD D3, recommended posture (c))

Aggregate-only, engine-internal, derive-on-read: M2 stats and M1 cells exist only inside
a job's memory and the readout; nothing per-person is persisted beyond the
already-existing spine; app and non-app league-mates are symmetric; deleting source rows
deletes the memory. The architecture makes posture (c) structural — there is no table a
DSAR or `delete_user_data` would have to learn about.

### 5.6 Analytics

No new events (scope §1). `features_json.negmem` is a data-dictionary row, not a
taxonomy entry — the stamp is server-written inside an existing column, so
`analytics_taxonomy.py` and `NON_INTENT_EVENTS` are untouched (memo §5's rule has no
trigger here; say so in the scope's docs table).

## 6. Risks & Open Questions

| # | Risk / question | Disposition |
|---|---|---|
| 1 | **R1(d) retraction join** — `deck_outcomes` and `trade_decisions` share no direct key; pass-side retraction signal is the paired `undo` (same `impression_id`, within `deck_outcomes`), like-side is `retracted_at` | LLD must specify the join path and prove the asymmetric dual check on fixtures; flagged in R1 verbatim |
| 2 | **Streaming snapshots see negmem'd scores mid-job** — the progress callback publishes `_dedup_and_sort` snapshots of already-multiplied cards | Correct by design (consultation at creation ⇒ snapshots consistent); noted so the C1 golden includes a streaming-callback fixture |
| 3 | **Rounding interplay** — `round(x·eff, 3)` stacks with five existing rounded multipliers; goldens must be exact | strength-0 path never rounds (D-6); on-path goldens tolerate nothing — exactness is the point |
| 4 | **`_c` availability in gen_v2/fit for strength** — both already read `_c` (`trade_gen_v2.py:301-302`, `trade_gen_fit.py:772-773` via `ts._c`) | no new import surface; T1 discipline restated in D-3 |
| 5 | **Family-combination rule** (product vs min, D-5) — product double-counts a partner rejected for both value and fit; min ignores corroboration | LLD decides on fixtures; floor clamp bounds the blast radius either way |
| 6 | **Allowlist mechanism for league-scoped rollout** — flag is global; PRD §8.2 names the `tester_allowlist.json` precedent | LLD; architecture reserves the seam: `build_map` returns None for non-allowlisted (user, league) ⇒ indistinguishable from flag-off |
| 7 | **Cells keyed on serve-time partner id vs current roster ownership** after a co-owner change mid-window | canonicalize at build time with current `league_members`; note in LLD; volume makes this cosmetic |
| 8 | **Shared taxonomy v1.0.0 not on main** (PRD §7) — `shape_bucket` recording on evidence rows cites it | land-or-vendor before build; the builder's shape field is the existing `deck_impressions.shape_bucket` string either way |
| 9 | **M2 id space** — `trade_matches.user_a/b_id` vs `league.members[*].user_id` must be the same space per league | LLD verifies on fixtures; readout documents the mapping (§4.2 discipline) |
| 10 | **Operator rulings D1–D3 pending** — D1=NO shelves M1 (P0/M2 ships alone; D-9 shows the builder survives as M2-only + analysis tooling) | phasing already severable; no architectural rework under any ruling |

## 7. Handed to the LLD (explicitly)

1. **Signatures** — `build_map`, `negmem_readout`, `partner_mult`, the `negmem` /
   `negmem_mults` / `acceptance_stats` kwarg additions, `Cell` dataclass.
2. **Decay/shrinkage math** — the `g(n_decayed)` curve from min-evidence to floor;
   half-life arithmetic; defaults (floor 0.6, min-ev 3, half-life 45d per R3).
3. **Netting mechanism** — decrement vs reset, magnitude, readout representation (D-7).
4. **Join paths** — the R1 admission query (incl. the R1(d) dual check), the M2
   aggregation SQL with in-query lookback, D-091/clean-epoch predicates, the
   canonicalization call sites.
5. **Knob table** — four `negmem_*` knobs with `_MODEL_CONFIG_DEFAULTS` rows,
   `_DEFAULT_CFG` entries, `_PINNED_KNOBS` entries, arm-A disposition sentences (D-6
   proposes `MODEL_A_PROFILE["negmem_strength"] = 0.0`), config-reference rows.
6. **Family-combination rule** (D-5) and the exact gen_v2 multiplication site (§2.3).
7. **Test fixtures** — goldens per §5.1 (incl. streaming-callback and arm-C), clamp/C2
   unit suite, C4 parity vectors, C5 determinism, identity-hygiene fixtures (co-owned
   league fixture reuse), latency harness for S6, RFPS power computation (§8.3).
8. **Readout SQL pack** — per-arm stamp rates, GR4 joint-product p5, §4.2 id mapping.
9. **Allowlist mechanism** (risk 6) and the TestFlight checklist text.
