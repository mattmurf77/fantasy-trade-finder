# LLD — Fit challenger build (arm `fit` + serving re-light + measurement rail)

**Date:** 2026-08-20
**Status:** implementation-ready low-level design. Sits under
[PLAN-v2.md](PLAN-v2.md) (authoritative; rulings R-1..R-12 binding) and
[HLD.md](HLD.md) (architecture; findings F-1..F-9 all resolved in §8 below). Product
spec: [PRD.md](PRD.md) (§3 knockouts operator-CLOSED). Review concerns C1–C7 / traps
T1–T4: [../../reviews/2026-08-20-fit-challenger-review.md](../../reviews/2026-08-20-fit-challenger-review.md).
**Rule of citation:** every signature and line anchor below was re-verified against this
checkout on 2026-08-20. Where this LLD had to rule on something no upstream doc ruled,
the ruling is listed in §8 so no build agent decides it silently.

Contents:
§1 [`backend/trade_gen_fit.py`](#1-backendtrade_gen_fitpy--the-module) ·
§2 [`bakeoff_runner.py` changes](#2-bakeoff_runnerpy-changes) ·
§3 [`server.py` changes](#3-serverpy-changes-callsite-m3-stamp-features_json-serialization) ·
§4 [Knob table (17 keys)](#4-knob-table--17-keys-final-count) ·
§5 [M-rail](#5-m-rail-m1m2m4) ·
§6 [Test plan](#6-test-plan-f6--plan-v2-2) ·
§7 [Docs deltas](#7-config--docs-deltas) ·
§8 [Rulings and punts](#8-closing-table--every-open-item-resolved-or-punted)

---

## 1. `backend/trade_gen_fit.py` — the module

New file. One module, five stages, external shape identical to
`trade_gen_v2.generate_league_suggestions` (`backend/trade_gen_v2.py:844`) so
`bakeoff_runner.gen_fit_cards` can call it exactly the way `gen_v2_cards`
(`bakeoff_runner.py:1133`) calls its module.

### 1.1 Imports and module constants

```python
"""trade_gen_fit.py — bake-off arm `fit`: thin knockouts, dual 0–100 scores.

Spec: docs/plans/fit-challenger/PRD.md (§3 knockouts CLOSED), PLAN-v2.md, LLD.md.

LENS PROVENANCE (T3 — binding): every lens reads RAW boards.
  * viewer lens map  = elo_to_value(user_elo[pid])          — the job's raw
    `elo_map_rt`, NEVER passed through `_shrink_user_elo`
  * partner lens map = elo_to_value(member.elo_ratings[pid]) — raw by
    construction (LeagueMember carries no confidence map)
  * consensus map    = elo_to_value(seed_elo[pid])
This module must never import or call `_shrink_user_elo`. Enforced by
`test_fit_lens_provenance_raw`.

ORGANIC ISOLATION: imported by exactly one production caller,
`bakeoff_runner.gen_fit_cards`. `trade_service` must never import this module.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from . import trade_service as ts        # T1 — MODULE import; call ts.overpay_ok(...)
from . import trade_optimizer as topt    # T1 — same discipline for _feasible_after

logger = logging.getLogger(__name__)

#: Pinned scorer version. Stamped into `fit.ver` and `fit_diag.ver`; the M2
#: readout refuses to bucket-match across versions (failure-mode row 11).
#: Bump on ANY change to _score, weights semantics, or bucket thresholds.
SCORER_VERSION = "fit-1"

#: K1 (PRD §3, operator-CLOSED): the legal (n_give, n_recv) shapes. Note the
#: closed list EXCLUDES 2-2 and 3-3 (equal multi-asset swaps) — see LLD §8 R-b.
_LEGAL_SHAPES: frozenset[tuple[int, int]] = frozenset(
    {(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (3, 2), (2, 3)})

#: Bucket names, pinned (also the M2 SQL vocabulary).
_BUCKETS = ("both_high", "mixed", "you_tilt", "them_tilt", "both_ok", "weak")
```

**Nothing else is imported.** `TradeCard`, `League`, `LeagueMember`,
`_harmonic_mean`, `need_fit_score`, `analyze_roster_strengths`, `elo_to_value`,
`package_value_v2`, `is_pick_asset`, `filler_ok`, `deck_centerpiece`, `_c` and the six
predicates are all reached as `ts.<name>` at call time; `_feasible_after`,
`_subset_pos_delta`, `_pos_counts`, `_consensus_packages` as `topt.<name>`. This is
the whole of T1 — a monkeypatch/knob rebind on `trade_service` propagates to fit.

### 1.2 `FitReport` — the diagnostics dataclass (draft B §2.6, adopted by PLAN-v2 §4)

```python
@dataclass
class FitReport:
    """Per-batch diagnostics. `diagnostics()` is the flat dict that rides
    `bakeoff_runs.arms_json['fit'].diagnostics` — every key below is present
    on EVERY run (zero/None-valued, never absent)."""
    league_id: str
    user_id: str
    opponents: int = 0                 # opponents that reached the pair loop
    boarded_opponents: int = 0         # partner has_rankings AND elo_ratings
    enumerated: int = 0                # candidates that ENTERED the K-chain
    scored: int = 0                    # K-chain survivors handed to the scorer
    killed: dict = field(default_factory=lambda: {
        "K0": 0, "K1": 0, "K2": 0, "K3": 0, "K4": 0,
        "K5": 0, "K6": 0, "K7": 0, "junk": 0})
    r5_fail_scored: int = 0            # fit_r5_mode=0 only: K7 fails that scored
    capped_pairs: int = 0              # pairs that hit fit_max_packages_per_pair
    post_filtered: dict = field(default_factory=lambda: {
        "untouchable": 0, "not_interested": 0, "position_prefs": 0,
        "r4_swiped": 0, "c4_centerpiece": 0, "min_them": 0, "min_aggregate": 0})
    emitted: int = 0                   # cards returned to the adapter
    # Bucket/character metrics — computed over the SCORED, RANKED, PRE-F4 set
    # (they describe the generator; F4 filters describe the viewer's prefs).
    one_sided_pct: float | None = None     # share with them < 40
    both_high_pct: float | None = None
    mixed_pct: float | None = None
    you_tilt_pct: float | None = None
    median_aggregate: float | None = None
    # C5 — over the top quartile BY AGGREGATE of the same pre-F4 set:
    top_q_pick_share: float | None = None  # share of cards containing ≥1 pick
    top_q_junk_share: float | None = None  # share containing an asset with
                                           # consensus value < asset_floor_abs
    ms: int = 0                        # module-internal wall time

    def diagnostics(self) -> dict:
        """Flat dict for arms_json. Every §2.6 key, always."""
        return {
            "opponents": self.opponents,
            "boarded_opponents": self.boarded_opponents,
            "enumerated": self.enumerated,
            "scored": self.scored,
            "killed": dict(self.killed),
            "r5_fail_scored": self.r5_fail_scored,
            "capped_pairs": self.capped_pairs,
            "post_filtered": dict(self.post_filtered),
            "emitted": self.emitted,
            "one_sided_pct": self.one_sided_pct,
            "both_high_pct": self.both_high_pct,
            "mixed_pct": self.mixed_pct,
            "you_tilt_pct": self.you_tilt_pct,
            "median_aggregate": self.median_aggregate,
            "top_q_pick_share": self.top_q_pick_share,
            "top_q_junk_share": self.top_q_junk_share,
            "ms": self.ms,
        }
```

W3 soak bars read `top_q_junk_share ≤ 0.10`, `top_q_pick_share ≤ arm B + 10pp`,
`killed["K7"]` directly from this dict.

### 1.3 Entry point

```python
def generate_league_suggestions(
    *,
    players: dict,
    league: ts.League,
    user_id: str,
    user_elo: dict[str, float],
    user_roster: list[str],
    seed_elo: dict[str, float],
    scoring_format: str = "1qb_ppr",
    outlook: str | None = None,
    bypass_need_gate: bool = False,
    untouchable_ids: set | None = None,
    not_interested_ids: set | None = None,
    target_ids: set | None = None,          # accepted for kwarg parity; v1 unused
    acquire_positions: list[str] | None = None,
    trade_away_positions: list[str] | None = None,
    opponent_user_id: str | None = None,
    past_decision_keys: set | None = None,
    max_per_opponent: int | None = None,    # None = full ranked list (gen_v2 contract)
    on_opponent_done=None,                  # accepted, IGNORED (fit is a quiet arm)
) -> tuple[list[ts.TradeCard], FitReport]:
    """Fit arm: pool → enumerate → K-chain → dual scorer → rank → post filters.
    Returns (cards, report). Cards are ordinary TradeCards carrying the `fit`
    payload; `lane`/`lane_shift`/intent/C4b are applied by gen_fit_cards."""
```

Behavioral spec, in order (each step is one private function, below):

1. Build value accessors (all cached dicts, `elo_to_value` fallback at Elo 1500):
   `cval` (seed), `uval` (raw viewer board), and per-opponent `oval` (raw partner
   board). `viewer_boarded = bool(user_elo)`.
2. `user_profile = ts.analyze_roster_strengths(user_roster, players, scoring_format)`;
   `user_pos_values` built once per job: `{pos: [(pid, cval(pid)), ...]}` over the
   user's full pre-trade roster, players only (`ts.is_pick_asset` excluded), positions
   QB/RB/WR/TE only — the exact shape `ts.need_gate_ok` consumes
   (`trade_service.py:1824`). `user_counts = topt._pos_counts(user_roster, players)`.
3. Eligible opponents = `[m for m in league.members if m.user_id != user_id and
   m.roster]`, narrowed to `opponent_user_id` when set (parity with
   `trade_gen_v2.py:921–924`). **Every** opponent is a pair — boarded or not (the
   PRD's core difference from gen_v2).
4. Per pair: build pools (§1.4), enumerate + kill + score (§1.5–§1.7), collect
   scored candidates.
5. Rank all candidates (§1.8), apply C4 + post-score filters (§1.9), fill the
   report's bucket metrics from the pre-F4 set, construct cards (§1.10), return.

Errors: no internal try/except around the whole pipeline — the per-arm try/except in
`run_bakeoff` (`bakeoff_runner.py:1400–1402`) is the containment layer, same posture
as `trade_gen_v2`.

### 1.4 Pool builder

```python
def _build_pool(*, roster: list[str], players: dict, cval,
                board_val=None, opp_board_val=None) -> list[str]:
    """PRD §5 union pool for ONE roster within one pair. Deterministic.

    board_val    — that roster owner's OWN raw board accessor, None if unboarded
    opp_board_val — the pair's OTHER board accessor, None unless BOTH boarded
    """
```

- Sub-pool A: top `int(ts._c("fit_pool_consensus"))` roster assets by `cval`,
  descending, tie-break `pid` ascending.
- Sub-pool B (only if `board_val`): top `int(ts._c("fit_pool_div_seed"))` by
  `abs(board_val(p) - cval(p))` descending.
- Sub-pool C (only if `board_val` and `opp_board_val`): top
  `int(ts._c("fit_pool_div_opp"))` by `abs(board_val(p) - opp_board_val(p))`.
- Picks: every roster asset with `ts.is_pick_asset(players.get(p))` enters the union
  unconditionally. K0/horizon note: the roster only ever holds the owned-pick
  pseudo-assets `server._owned_pick_assets` injected for the league horizon, so
  "owned picks in the league horizon" ≡ "pick assets on the roster" — no separate
  horizon check exists or is needed.
- Cap: if `len(union) > int(ts._c("fit_pool_cap"))`, rank every union member by
  `max(pct_consensus, pct_div)` and keep the top `fit_pool_cap`.
  `pct_consensus(p)` = fractional rank of `cval(p)` within the union (1.0 = best);
  `pct_div(p)` = fractional rank of `div(p)` within the union where
  `div(p) = max(|board−seed|, |board−opp_board|)` over whichever divergences are
  defined, `0.0` for assets with no board data (picks land here — both boards share
  one pick Elo, so their divergence is structurally ~0 and they compete on
  consensus percentile alone; C5's flooding watch covers the consequence).
  Ties: `(-rank, pid)`. **Picks compete under the cap like everything else** — the
  PRD's "always include" places them in the union, the cap is a hard cap on unique
  ids (LLD ruling, §8 R-c).
- Returns a `pid` list sorted by the cap rank (descending) — phase-2 expansion
  draws in this order.

Built twice per pair (user roster, opponent roster). Sub-ms; no caching across pairs
needed (opp pools differ per pair because of sub-pool C).

### 1.5 Enumerator

```python
def _enumerate_pair(user_pool: list[str], opp_pool: list[str],
                    kill, score, report: FitReport,
                    cap: int, expand_from: int) -> list[dict]:
    """PRD §5 budget shape: full 1-for-1 cartesian, then 2-/3-asset shapes
    expanded around the top `expand_from` surviving 1-for-1 centerpieces.
    `kill(give, recv) -> str | None`; `score(give, recv) -> dict` (a scored
    candidate). Increments report.enumerated per candidate ENTERING the
    K-chain; hard stop when a pair's enumerated count reaches `cap`."""
```

- **Phase 1 — 1-for-1 cartesian.** For `g` in `user_pool`, `r` in `opp_pool`
  (≤ 15×15 = 225): count `enumerated`, run the K-chain, score survivors.
- **Phase 2 — expansion.** Seeds = top `expand_from` (`fit_expand_from`, 25) phase-1
  *survivors* by `aggregate` descending (deterministic tie: pair pids). For each seed
  `(g0, r0)`, enumerate `G ∋ g0`, `G ⊆ user_pool`, `|G| ≤ 3` and `R ∋ r0`,
  `R ⊆ opp_pool`, `|R| ≤ 3` with `(|G|, |R|) ∈ _LEGAL_SHAPES − {(1,1)}`, additions
  drawn in pool-rank order via `itertools.combinations`. A `seen:
  set[tuple[frozenset, frozenset]]` dedupes across seeds **before** counting
  `enumerated` (a dedupe hit costs nothing and is not budget).
- **Budget:** the per-pair counter stops the pair at
  `int(ts._c("fit_max_packages_per_pair"))`; `report.capped_pairs += 1`. Leave-short
  is data (PRD §5) — `enumerated` vs the cap in the diagnostics is the record.
- If phase 1 yields zero survivors, phase 2 does not run for that pair (no
  centerpieces — mirrors the PRD's "no 1-for-1 signal supports them" rationale).
- No randomness anywhere (HLD §5f: deterministic diagnostics; frozen fixtures).

### 1.6 Knockout chain — cost order, K3 LAST

```python
def _kill(give_ids: list[str], recv_ids: list[str], ctx) -> str | None:
    """Returns the FIRST failing K-code, else None. Execution order is the
    COST order (HLD §5b), not the PRD's table order: K1 K2 K4 K5 K6 [junk]
    K7 K3. Counters stay attributable because the order is fixed."""
```

`ctx` is a per-pair namespace holding `players`, `cval`, `uval`, `oval`,
`user_counts`, `opp_counts`, `user_pos_values`, `user_profile`, `outlook`,
`scoring_format`, `bypass_need_gate`, and the two roster boards' presence bits.

The exact calls, one per predicate, verified against this checkout:

| K | Call (verbatim) | Signature source |
|---|---|---|
| K0 | *structural* — the enumerator draws only from the two rosters' pools; `killed["K0"]` stays 0 and is reported | PRD §3 K0 |
| K1 | `(len(give_ids), len(recv_ids)) in _LEGAL_SHAPES` — local `_k1_shape_ok`; structurally guaranteed by the enumerator, kept as a guard (kills count under `"K1"`) | PRD §3 K1 |
| K2 | `ts.pick_swap_ok(give_ids, recv_ids, ctx.players, ctx.cval)` — the 4th positional is `seed_value`; passing `cval` activates the C3 strip (`strip_matched_pick_pairs`, `pick_pair_strip_frac`) exactly as live | `trade_service.py:1686` `pick_swap_ok(give_ids, recv_ids, players, seed_value=None)` |
| K4 | `ts.overpay_ok(give_ids, recv_ids, ctx.cval)` | `trade_service.py:1743` `overpay_ok(give_ids, recv_ids, seed_value)` |
| K5 | `ts.pos_net_ok(give_ids, recv_ids, ctx.players)` | `trade_service.py:1765` `pos_net_ok(give_ids, recv_ids, players)` |
| K6 | `ts.pick_gap_ok(give_ids, recv_ids, ctx.cval, ctx.players)` | `trade_service.py:1790` `pick_gap_ok(give_ids, recv_ids, seed_value, players)` |
| junk | only when `ts._c("fit_junk_floor") >= 1.0` (default 0 = absent): `ts.filler_ok(give_ids, recv_ids, ctx.uval_or_cval, ctx.oval_or_cval)` — each accessor is that team's raw board when boarded, else `cval` (the live max-of-boards metric, degraded honestly for unboarded teams). Kills count under `"junk"` | `trade_service.py:1602` `filler_ok(give_ids, recv_ids, user_val, opp_val)`; C5 / PRD §10 |
| K7 | skipped when `ctx.bypass_need_gate` (targeted-job parity — unreachable on bake-off decks, kept for correctness). When `ts._c("fit_r5_mode") >= 1.0` (default): `ts.need_gate_ok(give_ids, recv_ids, seed_value=ctx.cval, players=ctx.players, user_pos_values=ctx.user_pos_values, outlook=ctx.outlook, position_needs=ctx.user_profile.get("position_needs"), position_surplus=ctx.user_profile.get("position_surplus"), scoring_format=ctx.scoring_format)` — viewer roster only, live-as-written (PRD K7). When `fit_r5_mode = 0`: the predicate still RUNS; a failure does not kill — the candidate is tagged `r5_fail`, `report.r5_fail_scored += 1`, and the payload carries `"r5_fail": true`. **No score change in v1** (LLD ruling §8 R-d) | `trade_service.py:1824` `need_gate_ok(give_ids, recv_ids, *, seed_value, players, user_pos_values, outlook, position_needs, position_surplus, scoring_format)` |
| K3 (LAST) | `g = topt._subset_pos_delta(give_ids, ctx.players)`; `r = topt._subset_pos_delta(recv_ids, ctx.players)`; kill unless `topt._feasible_after(ctx.user_counts, g, r, ctx.scoring_format) and topt._feasible_after(ctx.opp_counts, r, g, ctx.scoring_format)` — BOTH rosters, every path | `trade_optimizer.py:161` `_feasible_after(base_counts, out_delta, in_delta, scoring_format)`; `_pos_counts` `:150`, `_subset_pos_delta` `:181` (HLD F-9 confirmed) |

`opp_counts = topt._pos_counts(member.roster, players)` computed once per pair.
Every kill increments `report.killed[code]`; a candidate is attributed to exactly one
code (first failure, fixed order — `test_k3_runs_last_in_kill_order` pins it).
Note the predicates read their knobs through `ts._c` (`trade_service.py:878`,
thread-local overrides first), so fit's K2–K7 see the same live values arm B sees.

### 1.7 Scorer

```python
def _score(surplus: float) -> float:
    """PRD §4 curve: clamp(even + 50·tanh(s / scale), 0, 100).
    even = _c("fit_score_even") (50), scale = _c("fit_score_scale") (400).
    Pinned by computed values (HLD F-5 — never hand-rounded):
        s=0      → 50.0
        s=+200   → 50 + 50·tanh(0.5) = 73.105857863…   (−200 → 26.894142137…)
        s=+400   → 50 + 50·tanh(1)   = 88.079707797…   (−400 → 11.920292202…)
        s=+800   → 50 + 50·tanh(2)   = 98.201379003…   (−800 → 1.798620996…)
        s=+1200  → 50 + 50·tanh(3)   = 99.752737684…   (−1200 → 0.247262315…)
    (The PLAN-v2 F3 note's "88.4/11.6" was itself rounded wrong; the test pins
    the computed values above with abs tolerance 1e-6.)"""
    scale = ts._c("fit_score_scale")
    return max(0.0, min(100.0,
        ts._c("fit_score_even") + 50.0 * math.tanh(surplus / scale)))
```

```python
def _surplus(recv_ids: list[str], give_ids: list[str], value_of) -> float:
    """Directed surplus of ONE team in the live v2 value space: elo_to_value →
    package_value_v2 (trade-wide v_max, other_values crown credit) → waiver
    slot cost on the receiving-more side. Byte-parallel to the live formula at
    trade_service.py:4780–4806 so fit numbers are comparable to live ones."""
    rvals = [value_of(p) for p in recv_ids]
    gvals = [value_of(p) for p in give_ids]
    v_max = max(rvals + gvals)
    recvd = ts.package_value_v2(rvals, v_max, n_other=len(give_ids),
                                other_values=gvals)
    sent  = ts.package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                other_values=rvals)
    extra = len(recv_ids) - len(give_ids)      # raw id counts, picks included —
    if extra > 0:                              # identical to live A3
        recvd -= ts._c("waiver_slot_cost") * extra
    return recvd - sent
```

Per candidate, with `give_ids`/`recv_ids` in the VIEWER's frame:

- `s_cons_you = _surplus(recv_ids, give_ids, cval)`;
  `s_cons_them = _surplus(give_ids, recv_ids, cval)` (frame swapped).
- `s_board_you = _surplus(recv_ids, give_ids, uval)` iff `viewer_boarded`;
  `s_board_them = _surplus(give_ids, recv_ids, oval)` iff partner boarded
  (`member.has_rankings and member.elo_ratings` — the `trade_gen_v2.py:925` test).
- **Provenance (T3, binding):** `uval(pid) = elo_to_value(user_elo.get(pid, 1500.0))`
  — the raw job board; `oval(pid) = elo_to_value(member.elo_ratings.get(pid, 1500.0))`;
  `cval(pid) = elo_to_value(seed_elo.get(pid, 1500.0))`. `_shrink_user_elo` is never
  called (contrast `trade_gen_v2.py:902`, which does — deliberately not copied).

Lenses per team T (PRD §4):

- `L1(T) = _score(s_board_T)` — fires iff T boarded.
- `L2(T) = _score(s_board_T − s_cons_T)` — fires iff T boarded **and** at least one
  traded asset has a real seed row (`any(pid in seed_elo for pid in give_ids +
  recv_ids)`); otherwise omitted ("all assets unseeded", PRD §4) and the remaining
  weights renormalize (LLD ruling §8 R-e).
- `L3(T) = _score(s_cons_T)` — always fires.

Combine: weights `w = (fit_w_board, fit_w_div, fit_w_cons)` = (0.40, 0.30, 0.30)
over the fired lenses, renormalized to sum 1 (boarded, all fired: 0.4·L1 + 0.3·L2 +
0.3·L3; boarded, L2 omitted: (0.4·L1 + 0.3·L3)/0.7; unboarded: 1.0·L3).

```python
def _bucket(you: float, them: float) -> str:
    """PRD §4 presentment buckets. Evaluation order is pinned — the first
    matching row wins (mixed requires the lower side ≥ 40)."""
    if you >= 70 and them >= 70:  return "both_high"
    if (you >= 70 and 40 <= them < 70) or (them >= 70 and 40 <= you < 70):
        return "mixed"
    if you >= 70 and them < 40:   return "you_tilt"
    if them >= 70 and you < 40:   return "them_tilt"
    if 40 <= you < 70 and 40 <= them < 70:  return "both_ok"
    return "weak"
```

`boards` (the C4/R-11 analysis key): `"both"` when both boarded, `"viewer"` when
only the viewer, `"partner"` when only the partner, `"none"` when neither. The
fourth value `"partner"` is an additive LLD extension of the pinned 3-value enum —
§8 R-f explains why collapsing partner-only pairs into `"none"` would corrupt the
analysis key.

The fit payload (built by `_score_candidate`, attached later as `card.fit`):

```python
{
  "you": round(you, 1), "them": round(them, 1),
  "aggregate": round(you + them, 1),          # 0–200
  "bucket": bucket, "boards": boards, "ver": SCORER_VERSION,
  "r5_fail": r5_fail,                          # bool; True only under fit_r5_mode=0
  "lenses": {
    "you":  {"board": l1y, "vs_consensus": l2y, "consensus": l3y},
    "them": {"board": l1t, "vs_consensus": l2t, "consensus": l3t},
  },  # all six keys ALWAYS present; None where the lens did not fire —
      # nulls DO serialize (M4 null-share contract; HLD §9 question answered)
}
```

Lens values in the payload are `round(x, 1)`; ranking uses the unrounded floats.

### 1.8 Ranker

Sort key over all scored candidates, descending:
`(aggregate, fairness, tiebreak)` where `fairness` is the card's consensus ratio
(§1.10) and `tiebreak = (target_user_id, tuple(sorted(give_ids)),
tuple(sorted(recv_ids)))` ascending for full determinism.

The `fairness` term IS the C7c rule: every unranked-pair card (`boards == "none"`)
has `aggregate ≈ 100` by construction (both sides are the same consensus surplus
mirrored), so within that plateau the consensus-fairness ratio decides order — and
the same tie-break harmlessly orders any other aggregate tie. Documented in the
module docstring; `test_unranked_pair_aggregate_mirror` asserts both the mirror and
the tie-break.

`composite_score = aggregate` (0–200). Safe: the draft consumes list ORDER only
(`_draft_core`, `bakeoff_runner.py:777` — cursor walk, no score reads; C7b), and
`test_draft_rank_only` proves nothing downstream reads it as a magnitude.

### 1.9 Post-score filters (F4 — the module half)

Applied to the ranked list, in this order (PRD §6), each counting into
`report.post_filtered`:

1. `fit_min_them` / `fit_min_aggregate` (both default 0 = off): drop cards with
   `them < fit_min_them` or `aggregate < fit_min_aggregate`. Presentment knobs,
   placed first so later counters describe the visible universe.
2. Untouchables — drop when `set(give_ids) & untouchable_ids`.
3. Not-interested — drop when `set(recv_ids) & not_interested_ids`.
4. Position pins — only when the user set them: `acquire_positions` ⇒ receive side
   must contain ≥1 non-pick player at a listed position; `trade_away_positions` ⇒
   give side likewise. (Pinned give/receive **players** and opponent scoping never
   reach this module on a bake-off deck — `bakeoff_active`
   (`bakeoff_runner.py:360`) excludes those jobs entirely; the kwargs exist for
   parity and are honored the same way if ever passed.)
5. G6 R4 + already-swiped — drop when `(frozenset(give_ids), frozenset(recv_ids))
   ∈ past_decision_keys` (the adapter merges `_past_decision_keys` with the job's
   `exclusion_keys`, same as `gen_v2_cards`, `bakeoff_runner.py:1185–1186`).
   Post-score by operator ruling (PRD §6.4) — unlike gen_v2, which skips them
   during enumeration; fit's `enumerated` therefore includes them.
6. C4 centerpiece cap — replicate the live loop (`trade_service.py:3521–3534`):
   key = `ts.deck_centerpiece(give_ids, recv_ids, seed_elo)`, cap =
   `int(ts._c("deck_headliner_cap"))` (2), keep-first in rank order, cap ≤ 0 or
   empty seed map ⇒ no-op. (C4b, the give-side cap, is applied by the ADAPTER —
   §2.3 — exactly where `gen_v2_cards` applies it, so the two challenger arms get
   identical deck-assembly treatment.)
7. `max_per_opponent` — when an int, keep the top N per `target_user_id` in rank
   order; `None` (the adapter's value) = full list, the gen_v2/operator
   no-truncation contract (§8 R-g).

Filters 2–5 run per-viewer AFTER scoring — a preference hides the card, it never
shrinks the search (`test_untouchable_enumerated_then_filtered`).

### 1.10 TradeCard construction — every field

Template: the gen_v2 constructor call (`trade_gen_v2.py:1001–1016`).
`TradeCard` definition: `trade_service.py:2922` — the nine required positionals
first, in order:

| Field | Value fit assigns |
|---|---|
| `trade_id` | `str(uuid.uuid4())[:8]` |
| `league_id` | `league.league_id` |
| `proposing_user_id` | `user_id` |
| `target_user_id` | `member.user_id` |
| `target_username` | `member.username` |
| `give_player_ids` / `receive_player_ids` | the FULL package lists. K2's strip is judgment-only (`pick_swap_ok` semantics) — stored lists are never stripped |
| `mismatch_score` | **`round(ts._harmonic_mean(you, them), 1)`** — harmonic mean (`trade_service.py:1298`) of the two 0–100 team scores. Ruling (HLD F-4): it keeps the client's "higher = more compelling" rendering meaningful (0 when either side scores 0, high only when both sides like it) instead of a constant 0.0, and it is never used for ranking. `features_json.surplus_margin` inherits it (`server.py:4149`) — data-dictionary row notes the fit-arm meaning |
| `fairness_score` | the **live consensus ratio** (PLAN.md note 5): `gv, rv = topt._consensus_packages(give_ids, recv_ids, cval)` (`trade_optimizer.py:99`); `fairness = min(gv, rv) / max(gv, rv)` when both > 0 else `1.0` (the `_fairness_v3` degenerate convention, `trade_optimizer.py:131`). Existing UI (TradeValueBar, filters) keeps meaning; NOT a fit-lens number |
| `composite_score` | `round(aggregate, 4)` — 0–200 (C7b constraints per §1.8) |
| `basis` (default field) | `"divergence"` iff both members boarded else `"consensus"` (PLAN.md note 6). Analysis NEVER keys on it for fit (C4) — `features_json.fit.boards` is the analysis key |
| `give_value` / `receive_value` | `round(gv, 1)` / `round(rv, 1)` from the same `_consensus_packages` call — drives the value bar, same as `trade_gen_v2.py:1015–1016` |
| `fit` (new attribute) | the §1.7 payload dict |
| `need_fit` | `ts.need_fit_score(user_profile, opp_profile, give_ids, recv_ids, players, scoring_format)` (`trade_service.py:2014`) — STAMPED for telemetry, never multiplied (PRD §4). `opp_profile` computed once per pair via `ts.analyze_roster_strengths` |
| `lane` / `lane_shift` | NOT set by the module — applied by `gen_fit_cards` post-generation (§2.3), exactly as `gen_v2_cards` does (`bakeoff_runner.py:1262–1272`) |
| NOT run | `_tier_mult_v2`, `need_fit` multiplier, `block_boost`, `outlook_dir`, aggression, `_shrink_user_elo` — live rank overlays this scorer replaces (PRD §4) |
| every other optional field | dataclass default (None/False/[]) — untouched |

### 1.11 M3 helper (lives in this module so the scorer has one home)

```python
def stamp_fit_diag(arm_lists: dict[str, list], *, players: dict,
                   league: ts.League, user_elo: dict[str, float],
                   seed_elo: dict[str, float]) -> None:
    """M3/R-11 — set `card.fit_diag = {"you", "them", "bucket", "ver"}` on
    EVERY card of EVERY arm's ranked list. Fit's own cards reuse `card.fit`
    (identical numbers by construction). Other arms' cards are scored fresh:
    resolve the partner via {m.user_id: m for m in league.members}, compute
    you/them per §1.7 (weights and lenses included), bucket per _bucket.
    Per-card try/except: a card that cannot be scored (unknown partner,
    empty sides) gets `card.fit_diag = None` — the key must exist DOWNSTREAM
    (features_json writes it null), absence is impossible (M4 contract).
    Purely attribute-setting: no return, no reordering, no score mutation —
    inertness is enforced by test_fit_diag_inert."""
```

Cost: one scorer pass over ≤ ~160 already-ranked cards — noise (HLD §5d).

---

## 2. `bakeoff_runner.py` changes

All anchors verified against this checkout.

### 2.1 Constants and roster (F5)

- After `ARM_CHALLENGER` (`:120`): `ARM_FIT = "fit"` with a comment pointing at
  this LLD.
- `ALL_ARMS` (`:135`) → `(ARM_BASELINE, ARM_CURRENT, ARM_CHALLENGER, ARM_GEN_V2,
  ARM_FIT)`. **`ARMS` (`:131`) is untouched** — Phase-3 tests pin it as the
  historical three-arm fixture (HLD F-8).
- **`ENGINE_ARMS` (`:146`) is untouched** — fit must NOT join it (HLD F-7):
  `groups_for()` (`:521`) would give fit basis-narrowed divergence/consensus groups
  keyed on the overloaded `basis` meaning C4 flags, and
  `effective_fairness_threshold` (`:413`) would apply divergence-floor logic to
  cards whose `basis` means data-availability. With fit outside `ENGINE_ARMS`,
  `groups_for()`'s else-branch already yields `Group("fit", "fit", None)` — **no
  edit to `groups_for()` is needed**.
- `GENERATION_ORDER` (`:190`) → append `ARM_FIT` LAST: `(ARM_CURRENT,
  ARM_CHALLENGER, ARM_BASELINE, ARM_GEN_V2, ARM_FIT)`. Arm B stays first
  (`DARK_SERVED_ARM`, `:194`, unchanged).
- `arm_roster()` (`:247`): add to the `included` dict (`:274–279`):
  `ARM_FIT: _cfg("bakeoff_include_fit", 0.0) >= 1.0` — default OFF the roster.
- New knob reader beside `serve_interleaved()` (`:218`):

```python
def serve_fit() -> bool:
    """F5b — `bakeoff_serve_fit` (default 0): 0 = fit generates, logs, and is
    stamped, but is EXCLUDED from the draft participants on BOTH draft paths;
    1 = fit drafts like any arm. Fit-only bit by design (PLAN-v2 F5b) —
    generalize on the second consumer, not the first."""
    return _cfg("bakeoff_serve_fit", 0.0) >= 1.0
```

### 2.2 Diagnostics thread-local

Beside `_gen2_diag` (`:1120`):

```python
_fit_diag_tl = threading.local()

def last_fit_diagnostics() -> dict:
    """FitReport.diagnostics() from the most recent gen_fit_cards call ON THIS
    THREAD, then CLEARED — the _gen2_diag drain pattern (:1123–1130) verbatim."""
    diag = getattr(_fit_diag_tl, "value", None) or {}
    _fit_diag_tl.value = {}
    return dict(diag)
```

### 2.3 `gen_fit_cards` adapter

After `gen_v2_cards` (which ends `:1273`). Mirrors it step for step:

```python
def gen_fit_cards(trade_service, kwargs: dict) -> list:
    """Arm `fit` — trade_gen_fit.generate_league_suggestions called DIRECTLY.
    Same presentation-side parity treatment as gen_v2_cards and for the same
    reason: intent filter, C4b give-headliner cap, lane labelling are what
    arms A/B/D get, so fit gets them — the bake-off compares generation."""
    from .trade_gen_fit import generate_league_suggestions
    from .trade_service import (_c, _filter_by_trade_intent, cap_give_headliners,
                                classify_lane, elo_to_value,
                                pinned_stud_tax_mode, signed_lane_shift,
                                stud_tax_mode_for_user, stud_tax_override)
    from .feature_flags import FLAGS

    _fit_diag_tl.value = {}                       # cleared on entry (leak guard)
    league = trade_service._leagues.get(kwargs["league_id"])
    if league is None:
        _fit_diag_tl.value = {"S0_no_league": 1}
        return []
    past_keys = set(getattr(trade_service, "_past_decision_keys", None) or set())
    past_keys |= set(kwargs.get("exclusion_keys") or set())
    mode = pinned_stud_tax_mode() or stud_tax_mode_for_user(kwargs.get("user_id"))
    with stud_tax_override(mode):                 # same pin gen_v2_cards re-applies
        cards, report = generate_league_suggestions(
            players              = trade_service._players,
            league               = league,
            user_id              = kwargs["user_id"],
            user_elo             = kwargs["user_elo"],
            user_roster          = kwargs["user_roster"],
            seed_elo             = kwargs["seed_elo"],
            scoring_format       = kwargs.get("scoring_format", "1qb_ppr"),
            outlook              = kwargs.get("outlook"),
            bypass_need_gate     = bool(kwargs.get("bypass_need_gate")),
            untouchable_ids      = kwargs.get("untouchable_ids"),
            not_interested_ids   = kwargs.get("not_interested_ids"),
            target_ids           = kwargs.get("target_ids"),
            acquire_positions    = kwargs.get("acquire_positions"),
            trade_away_positions = kwargs.get("trade_away_positions"),
            opponent_user_id     = kwargs.get("opponent_user_id"),
            past_decision_keys   = past_keys,
            max_per_opponent     = None,          # no engine truncation (§8 R-g)
        )
    cards = list(cards or [])

    _diag_fn = getattr(report, "diagnostics", None)      # gen_v2's getattr guard
    diag = dict(_diag_fn()) if callable(_diag_fn) else {}

    seed_elo = kwargs.get("seed_elo") or {}
    scoring_format = kwargs.get("scoring_format", "1qb_ppr")
    _n = len(cards)
    cards = _filter_by_trade_intent(
        cards, effective_trade_intent(kwargs.get("trade_intent")),
        seed_elo, trade_service._players, scoring_format)
    diag["S7_intent_filter"] = _n - len(cards)
    _n = len(cards)
    cards = cap_give_headliners(cards, seed_elo, trade_service._players,
                                int(_c("deck_give_headliner_cap")))     # C4b
    diag["S7_headliner_cap"] = _n - len(cards)
    diag["S7_served_to_deck"] = len(cards)
    _fit_diag_tl.value = diag

    # lane_shift (unconditional) + lane (flagged) — byte-for-byte the
    # gen_v2_cards block at :1252–1273, sharing its _vs consensus accessor shape.
    ...
    return cards
```

### 2.4 `run_bakeoff` — third callable + serve-bit (HLD F-3, F-6)

**Signature** (`:1322–1333`) — one additive keyword, default `None`, so every
existing caller (`server.py:5669`; `test_bakeoff_composition.py:601/617/675`,
`test_bakeoff_runner.py:287/349`, `test_bakeoff_challenger.py:576` — all
keyword-style) compiles unchanged:

```python
def run_bakeoff(
    *,
    generate: Callable[..., list],
    gen_v2: Callable[..., list],
    gen_fit: Callable[..., list] | None = None,     # NEW — arm `fit`
    league_id: str,
    fairness_threshold: float | None = None,
    trade_intent: str | None = None,
    iso_week: str | None = None,
    interleave: bool | None = None,
    limit: int | None = None,
    roster: tuple[str, ...] | list[str] | None = None,
) -> BakeoffRun:
```

**Dispatch** — extend the if/elif chain (`:1371–1399`) before the final `else`:

```python
            elif arm == ARM_FIT:
                cfg_seen = snapshot_config()
                if gen_fit is None:      # rostered without a callable is a
                    raise RuntimeError(  # recorded arm error, never a job failure
                        "arm fit rostered but no gen_fit callable bound")
                cards = list(gen_fit(**quiet) or [])
```

(the `raise` lands in the existing per-arm `except` at `:1400–1402` →
`ArmResult(error=..., cards=[])`).

**Diag drain** (`:1406`):

```python
        if arm == ARM_GEN_V2:
            diag = last_gen_v2_diagnostics()
        elif arm == ARM_FIT:
            diag = last_fit_diagnostics()
        else:
            diag = {}
```

**Fairness threshold** (`:1414–1415`): fit joins gen_v2's None — its fairness is a
score, not a gate (HLD F-7):

```python
            fairness_threshold=(None if arm in (ARM_GEN_V2, ARM_FIT)
                                else fairness_threshold),
```

**Serve-bit exclusion — BOTH draft paths** (HLD F-6, the leak the unit tests would
miss). Replace `:1420–1427`:

```python
    arm_lists = {a: arms[a].cards for a in roster}          # FULL lists — the
    # agreement scan below runs over these, so a dark fit still shows up in
    # `also_proposed_by` (HLD §2.2 lean: adopted — free telemetry, no serving
    # effect, since fit is absent from every participant order).
    serving_roster = tuple(a for a in roster
                           if a != ARM_FIT or serve_fit())  # F5b
    groups, group_order, draft = compose_deck(
        arm_lists, league_id=league_id, iso_week=iso_week,
        roster=serving_roster, limit=limit)
    if not groups:
        # bakeoff_group_size = 0 — Phase 3's plain per-ARM team draft. THIS is
        # the live path for the whole program (W1 sets group_size = 0), so the
        # serve-bit MUST act here too: fit's list stays in `arm_lists` (for
        # _agreement) but fit is absent from the rotation, so _draft_core
        # (:794 `order = [p for p in order if p in lists]`) never draws it.
        group_order = draft_order_for(serving_roster, league_id, iso_week)
        draft = team_draft(arm_lists, group_order, limit=limit)
```

Why this shape is sufficient on both paths, cited:

- `compose_deck` (`:1293`) builds groups from `groups_for(roster)` (`:1312`) —
  passing `serving_roster` means no fit group exists, so `group_draft` cannot seat
  fit; but it still receives the FULL `arm_lists` (`:1319`), and `_agreement`
  (`:828`) runs a membership scan over `arm_lists`, so fit's proposals register.
- `team_draft` (`:850`) → `_draft_core` (`:777`) reads only participants in
  `order` (`:794`); fit's key in `lists` without a rotation slot is inert for
  drafting, live for `_agreement` (`:856–857`).
- Everything else still happens for a dark fit: `ArmResult` in `arms` →
  `run_row()` arms_json (`:1058–1081`, no change needed — fit's diagnostics ride
  `ArmResult.diagnostics` exactly like gen_v2's, HLD §2.2 "arms_json: no schema
  change"); `fit_diag` stamping (§3.2); no fit card in `draft.deck` ⇒ no
  `deck_impressions` row with `model_arm='fit'` (`attribution_for`, `:960`) — the
  M4 serve-bit-leak tripwire's exact assertion.

`BakeoffRun.arm_order` records the serving rotation (fit absent while dark) — the
honest record of who could draft.

---

## 3. `server.py` changes (callsite, M3 stamp, features_json, serialization)

### 3.1 Callsite — bind the third callable

`_run_trade_job` (`server.py:5402`), the `run_bakeoff` call (`:5669–5681`): add one
line after the `gen_v2` binding (`:5672–5673`), mirroring it:

```python
                gen_fit   = lambda **ov: _bakeoff.gen_fit_cards(
                    trade_service, {**_generate_kwargs, **ov}),
```

`_generate_kwargs` (`:5633–5662`) already carries every key §2.3 reads
(`user_elo = elo_map_rt` at `:5636`, `seed_elo = seed_map`, `outlook`,
`bypass_need_gate`, `acquire_positions`, `trade_away_positions`, `exclusion_keys`,
`scoring_format = active_format`, …). No kwarg additions needed.

### 3.2 M3 — the `fit_diag` stamp site

Insertion point: **immediately after the `bakeoff_on` if/else closes** — i.e. after
`final_cards = trade_service.generate_trades(**_generate_kwargs)` (`:5684`), before
the F7 exploration block (`:5686`). Both the ranked lists
(`bakeoff_run.arms[arm].cards`) and the scorer's inputs (`elo_map_rt`, `seed_map`,
`g_league`, `players_dict`) are in scope here, and every arm's list is already
ranked and the draft already run (post-ranking by construction):

```python
        # M3 (R-11) — diagnostic fit stamp on EVERY bake-off card of EVERY arm,
        # so the readout can bucket-match arm B against fit. Post-ranking,
        # attribute-only, and inert: nothing downstream reads fit_diag except
        # the features_json copy below (test_fit_diag_inert enforces).
        if bakeoff_run is not None:
            try:
                from backend.trade_gen_fit import stamp_fit_diag  # lazy — the
                # organic (bakeoff_run is None) path never executes this import
                stamp_fit_diag(
                    {a: r.cards for a, r in bakeoff_run.arms.items()},
                    players  = players_dict,
                    league   = g_league,
                    user_elo = elo_map_rt,
                    seed_elo = seed_map,
                )
            except Exception as fd_err:
                log.warning("fit_diag stamp failed (non-fatal): %s", fd_err)
```

Inertness guarantee, mechanically: (1) the stamp runs after `served_deck()` was
computed at `:5682` and mutates only a new attribute; (2) the only reader is the
features copy below; (3) `test_fit_diag_inert` deletes the attribute from every
card and asserts the served deck identical. Version pinning: `ver` inside each
stamp equals `SCORER_VERSION`.

### 3.3 `_log_deck_signal_impressions` — the features keys

In the existing `if bakeoff_run is not None:` features block (`:4193–4196`, the
`also_proposed_by` stamp), add two UNCONDITIONAL lines:

```python
        if bakeoff_run is not None:
            _agree = bakeoff_run.also_proposed_by(card)
            if _agree:
                features["also_proposed_by"] = _agree
            # Both keys on EVERY bake-off row, null-valued when absent — the M4
            # null-share tripwire needs absence to be impossible. They ride
            # INSIDE features_json (one column), so the T2 executemany
            # first-row-keys trap (save_deck_impressions, database.py:5427)
            # cannot drop them.
            features["fit"]      = getattr(card, "fit", None)
            features["fit_diag"] = getattr(card, "fit_diag", None)
```

`features_json.fit` is therefore non-null only on served fit cards (attribute
exists only on fit cards); `features_json.fit_diag` non-null on every card the
stamp reached (HLD §3.3). Flag-off rows are byte-identical — both lines are inside
the `bakeoff_run is not None` guard.

### 3.4 `trade_card_to_dict` — additive serialization

`trade_card_to_dict` (`server.py:10944`): one additive block, same shape as the
other optional attributes:

```python
    _fit = getattr(card, "fit", None)
    if _fit is not None:
        d["fit"] = _fit          # bake-off fit cards only; clients ignore unknown keys
```

No mobile/web change in v1 (scope.md §3 waiver stands).

---

## 4. Knob table — 17 keys (final count)

**Count reconciliation (HLD F-2):** PRD §9 lists **13** keys (`bakeoff_include_fit`,
`fit_score_scale`, `fit_w_board`, `fit_w_div`, `fit_w_cons`, `fit_pool_consensus`,
`fit_pool_div_seed`, `fit_pool_div_opp`, `fit_pool_cap`,
`fit_max_packages_per_pair`, `fit_expand_from`, `fit_min_them`,
`fit_min_aggregate`). Add `fit_score_even` (PRD §4 names it as a knob; ruled a KNOB
here — F-2 resolved, §8), `fit_r5_mode`, `fit_junk_floor` (PLAN-v2 F1/F4
pre-wires), `bakeoff_serve_fit` (F5b). **Total = 17.** PLAN-v2's "16" undercounted
by omitting `fit_score_even`; its T4 paragraph is amended by this table.

Every key gets ALL FIVE registrations **in the same commit as its consumer**
(T4 + HLD F-1): `trade_service._DEFAULT_CFG` (ends `trade_service.py:841` — which
also puts it in `snapshot_config()` → `config_json`, the contamination-diff
mechanism, `bakeoff_runner.py:400/410`), `database._MODEL_CONFIG_DEFAULTS`
(`database.py:2157`; without the row, `set_config` raises `KeyError`
(`database.py:4120/4129–4130`) and `PUT /api/admin/config` 404s — the knob-rollback
ladder would be theater), `_PINNED_KNOBS`
(`backend/tests/test_bakeoff_arm_a_golden.py:454` — fails BY NAME), the disposition
sentence in `docs/plans/three-model-bakeoff/scope-phase2.md`, and the
`docs/config-reference.md` row (§7).

| Key | Default | Consumer (function) | Disposition sentence |
|---|---:|---|---|
| `fit_score_scale` | 400.0 | `trade_gen_fit._score` | A |
| `fit_score_even` | 50.0 | `trade_gen_fit._score` | A |
| `fit_w_board` | 0.40 | `trade_gen_fit._score_candidate` (lens combine) | A |
| `fit_w_div` | 0.30 | same | A |
| `fit_w_cons` | 0.30 | same | A |
| `fit_pool_consensus` | 8.0 | `trade_gen_fit._build_pool` | A |
| `fit_pool_div_seed` | 8.0 | same | A |
| `fit_pool_div_opp` | 8.0 | same | A |
| `fit_pool_cap` | 15.0 | same | A |
| `fit_max_packages_per_pair` | 20000.0 | `trade_gen_fit._enumerate_pair` | A |
| `fit_expand_from` | 25.0 | same | A |
| `fit_min_them` | 0.0 | `trade_gen_fit._apply_post_filters` step 1 | A |
| `fit_min_aggregate` | 0.0 | same | A |
| `fit_r5_mode` | 1.0 | `trade_gen_fit._kill` (K7 row, §1.6) | A |
| `fit_junk_floor` | 0.0 | `trade_gen_fit._kill` (junk row, §1.6) | A |
| `bakeoff_include_fit` | 0.0 | `bakeoff_runner.arm_roster` | B |
| `bakeoff_serve_fit` | 0.0 | `bakeoff_runner.serve_fit` (read in exactly one place) | B |

Disposition sentences (D-095 wording, PLAN-v2 T4):

- **A** (15 keys): *"Generation knob for `trade_gen_fit`, a module arm A never
  imports; no effect on MODEL_A_PROFILE output."*
- **B** (2 keys): *"Arm roster / serving bit, not generation — read only by
  `bakeoff_runner` before or after any arm runs; an arm cannot observe it."*
  (the `bakeoff_include_challenger` precedent row in scope-phase2.md `:96`).

`_MODEL_CONFIG_DEFAULTS` descriptions: one line each, ≤ 90 chars, e.g.
`("fit_score_scale", 400.0, "fit arm: tanh surplus scale — surplus 400 → score ≈ 88.1")`.
Reused live knobs (`waiver_slot_cost`, `deck_headliner_cap`,
`deck_give_headliner_cap`, `pick_pair_strip_frac`, `max_overpay_*`, `pos_net_cap`,
`pick_gap_*`, `need_gate_*`, `asset_floor_abs`, `filler_min_frac`) are already
registered everywhere — changing them moves BOTH arms (PRD §9; snapshot per run is
the isolation).

---

## 5. M-rail (M1/M2/M4)

### 5.1 M1 — `model_config_changes` + `updated_at` (database.py)

**Table** (SQLAlchemy Core def next to `model_config_table`, `database.py:1489`;
`metadata.create_all` in `init_db` (`:3329–3331`) creates it on both dialects — the
repo's new-table idiom, no migration entry needed for a NEW table):

```python
model_config_changes_table = Table("model_config_changes", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("key",        String,  nullable=False),
    Column("old_value",  Float),                    # NULL on first logged write
    Column("new_value",  Float,   nullable=False),
    Column("changed_at", String,  nullable=False),  # ISO UTC
    Column("source",     String),                   # 'operator' | 'admin-api' | …
)
Index("ix_model_config_changes_key",
      model_config_changes_table.c.key, model_config_changes_table.c.changed_at)
```

**Column add** (`model_config.updated_at`): add `Column("updated_at", String)` to
`model_config_table` **and** the tuple `("model_config", "updated_at", "VARCHAR")`
to `migration_cols` (`database.py:2432`; the loop at `:2587–2592` try/excepts each
`ALTER TABLE` in its own transaction — the Postgres aborted-transaction idiom
already handled). ISO-string VARCHAR matches every other timestamp column. Existing
rows keep NULL `updated_at` until first logged write — additive, no backfill.

**Write-path helper** — extend `set_config` in place (single funnel, no second
name; additive default arg so every existing caller keeps working and gets logged):

```python
def set_config(key: str, value: float, source: str = "unspecified") -> dict:
    """Update one model_config value, stamping updated_at and appending a
    model_config_changes row — one transaction. Raises KeyError for unknown
    keys (unchanged contract — no ad-hoc keys)."""
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        existing = conn.execute(
            select(model_config_table).where(model_config_table.c.key == key)
        ).fetchone()
        if existing is None:
            raise KeyError(f"Unknown config key: {key!r}")
        conn.execute(update(model_config_table)
                     .where(model_config_table.c.key == key)
                     .values(value=value, updated_at=now))
        conn.execute(insert(model_config_changes_table).values(
            key=key, old_value=existing.value, new_value=value,
            changed_at=now, source=source))
    return {"key": key, "value": value, "old_value": existing.value}
```

**Its two callers:**

1. `PUT /api/admin/config/<key>` (`server.py:16652`, handler `admin_config_update`):
   parse optional `body["source"]` (string, truncated to 64 chars), default
   `"admin-api"`; call `set_config(key, new_value, source=src)`. The handler's
   existing `reload_config()` pair (`:16670–16672`) is untouched — it is what makes
   every flip deploy-free. Response gains `old_value` (additive).
2. `scripts/set_knob.py` (§5.2) — passes `"source": "operator"` through the route
   body (default mode), or calls `set_config(..., source="operator-local")`
   directly in `--local` mode.

Raw-SQL bypass caveat stands (PLAN-v2 M1): a bypassed write is dated-not-attributed
(no `updated_at` stamp either); the per-run `config_json` snapshot diff catches it
and R-5 defines the consequence (discard).

### 5.2 M1 — `scripts/set_knob.py` (repo root `scripts/`, alongside the other operator scripts)

```
usage: python3 scripts/set_knob.py KEY VALUE [--base URL] [--source NAME] [--local]
```

- **Default mode (prod/remote):** `PUT {base}/api/admin/config/{KEY}` with header
  `X-Cron-Secret: $CRON_SECRET` and body `{"value": VALUE, "source": SOURCE}`.
  `base` from `--base`, else `FTF_API_BASE` in `secrets.local.env`, `CRON_SECRET`
  from `secrets.local.env` (never a CLI arg, never prompted — repo secrets
  convention). SOURCE default `"operator"`. Goes through the ROUTE, not the DB,
  because only the route triggers the live `reload_config()` pair — a direct prod
  DB write would log the change and change nothing until restart.
- **`--local`:** calls `backend.database.set_config(KEY, VALUE,
  source="operator-local")` against the local DB, then prints a reminder that a
  RUNNING local server reloads only via the PUT route or restart.
- **Output:** one line — `keyname: <old_value> -> <new_value> (source=operator,
  logged <changed_at>)`.
- **Refusal cases (non-zero exit, message, nothing written):**
  1. VALUE not parseable as float (`model_config` is Float-only).
  2. Route returns 404 → `unknown key {KEY!r} — every knob needs its
     _MODEL_CONFIG_DEFAULTS row (LLD §4)`.
  3. No `CRON_SECRET` in `secrets.local.env` → tells the operator to fill it there
     (never paste into chat).
  4. No base URL resolvable in default mode.
  5. `--local` while the `DATABASE_URL` env var points at a non-SQLite URL —
     a direct write against prod Postgres would skip the live reload; use the
     route.
- ~60 lines, stdlib only (`urllib.request`, `argparse`).

### 5.3 M2/M4 — `scripts/bakeoff_readout.sql`

One file, sectioned; run under the `backend/tools/prod_analytics.py` read-only
posture. Header comment carries the two standing bans: **never split fit by
`basis`** (analysis keys on `features_json.fit.boards ∈
{both, viewer, partner, none}` — C4) and **never compare `composite_score`
across arms as a magnitude** (C7b).

| § | Section | Source |
|---|---|---|
| 1 | Window header: decided cards per arm; knob changes in window (`SELECT * FROM model_config_changes WHERE changed_at >= :window_start`); config-snapshot diff instructions (`bakeoff_runs.config_json` vs round-start) | draft B §2.3.2 + M1 |
| 2 | Co-primary 1 — decided like-rate by arm × fit bucket (`COALESCE(features_json fit.bucket, fit_diag.bucket)`) | draft B §2.4 q1, verbatim |
| 3 | Co-primary 2 — decline-reason mix by arm (`value_giving` share) | draft B §2.4 q2, verbatim |
| 4 | Deck-integrity daily: median `deck_size`, p95 `total_ms` on interleaved runs | draft B §2.4 q3, verbatim; R-9 bars in comment (median < 22 investigate / < 18 ×2 days revert; SC2 ≥ 24) |
| 5 | Position balance: per-arm mean `card_index` | draft B §2.4 q4, verbatim |
| 6 | Fit diagnostics extract from `bakeoff_runs.arms_json->'fit'->'diagnostics'` (`enumerated`, `scored`, `killed`, `one_sided_pct`, bucket mix, `top_q_pick_share`, `top_q_junk_share`, `ms`) | draft B §2.4 q5 |
| 7 | **M4 tripwires** (the four A-added rows + the standing set): (a) serve-bit leak — `SELECT COUNT(*) FROM deck_impressions WHERE model_arm='fit' AND served_at >= :window_start` cross-referenced against `model_config_changes` for `bakeoff_serve_fit`: any fit rows while the bit was 0 → **stop** (M4); (b) per-arm `error`/`forfeits` from `arms_json`; (c) re-ranker bypass assertion — interleaved runs (`served_arm IS NULL`) present ⇒ served rows in window must carry `model_arm`; a decided window with NULL-`model_arm` majority → discard; (d) ghost share vs configured rate (±5pp); (e) max single-tester share of decided cards; (f) `fit_diag` null-share per arm (`features_json.fit_diag IS NULL` rate > 5% → data bug, window suspect); (g) cross-round arm-B drift check — arm B bucketed like-rate vs its own prior round ±; (h) `fit.ver`/`fit_diag.ver` mixed-version check (row 11) | draft B §6 rows + PLAN-v2 §4 |
| 8 | Guardrail — pooled like-rate per arm, printed last, labelled `GUARDRAIL (never the verdict — C3)`; R-12 tripwire comment (fit pooled < 5% for a week at n ≥ 100 → pause) | draft B §2.2 |

SQLite/Postgres note at top: queries are written for Postgres (prod);
`features_json::json->` operators need `json_extract` on SQLite — a comment block
carries the two-line translation, since the readout only ever runs against prod.

### 5.4 M5 — tester protocol

Doc-only (`docs/plans/trade-engine-accuracy/tester-protocol.md` + runbook §): ≥40
decided/wk, always a decline reason, ≥1 real send attempt, onboarding = board ≥100
votes + declared outlook. No code surface — out of this LLD's file set.

---

## 6. Test plan (F6 + PLAN-v2 §2)

Fixture idiom (all new tests): the `test_bakeoff_challenger.py` pattern — a local
`_Player` class, literal Elo maps, `LeagueMember`/`League`/`TradeService`
constructed inline, **every input a literal** (HANDOVER trap 7: pin inputs, so
goldens isolate generation logic from board-computation drift). Shared fixture for
the fit suite:

```
_USER roster: 6 players (QB/RB/RB/WR/WR/TE, Elos 1700…1400) + 2 owned-pick
pseudo-assets (position="PICK", seeded 1520/1450)
_OPP_BOARDED: 5 players + 1 pick, member.has_rankings=True with a board that
disagrees with seed on 2 assets (one over, one under)
_OPP_UNRANKED: 4 players, has_rankings=False, elo_ratings={}
seed map: literal Elos for every asset
```

### 6.1 `backend/tests/test_trade_gen_fit.py` (new)

| Test | Fixture shape | Asserts |
|---|---|---|
| `test_k1_shapes` | direct `_k1_shape_ok` + a tiny pool run | every `_LEGAL_SHAPES` member passes incl. (3,1)/(1,3)/(3,2)/(2,3); (4,1), (1,4), (3,0), **(2,2), (3,3)** fail (the closed PRD list excludes equal multi-asset swaps — §8 R-b) |
| `test_k2_byte_identical_to_live_c3` | two 1sts priced equal across years (2026 vs 2027, seed 1520/1515); two late 2nds vs one 1st | for each shared fixture package: fit's K2 verdict `== ts.pick_swap_ok(g, r, players, cval)` exactly; the 1-for-1 cross-year swap dies; the 2-for-1 consolidation lives |
| `test_k3_both_rosters_all_paths` | trade that leaves the OPPONENT with 0 RB (viewer fine), and its mirror | both die with `killed["K3"]` incremented; a startable 3-for-1 passes K3 |
| `test_k3_runs_last_in_kill_order` | candidate failing BOTH K4 (overpay gap ≥ 500 & ≥ 25%) and K3 | `killed["K4"] == 1`, `killed["K3"] == 0` — first-failure attribution proves the chain order |
| `test_negative_surplus_scores` | boarded pair, package where them-side consensus surplus < 0 | card is in the output; `fit["them"] < 50`; not killed (the volume unlock) |
| `test_unranked_partner_l3_only` | `_OPP_UNRANKED` pair | every card: `lenses["them"]["board"] is None`, `["vs_consensus"] is None`, `["consensus"]` set; them-score == L3(them); `boards == "viewer"` (viewer boarded) |
| `test_unranked_pair_aggregate_mirror` | viewer `user_elo={}` + `_OPP_UNRANKED` | every card `boards == "none"`, `abs(aggregate − 100) < ε` for balanced shapes; list order within the plateau follows `fairness_score` desc (C7c) |
| `test_fit_score_curve_pinned` | none (pure fn) | `_score` at 0/±200/±400/±800/±1200 equals the §1.7 computed table, `abs=1e-6`; clamp at ±10⁶ → 100/0; `fit_score_even` override moves the midpoint |
| `test_fit_lens_provenance_raw` | viewer board with an asset the confidence map would shrink hard (confidence=0 → shrunk == seed; raw ≠ seed) | lens L1 reflects the RAW value: monkeypatch `ts._shrink_user_elo` with a sentinel that raises — module never calls it; and the computed L1 equals the hand-computed raw-board score (T3) |
| `test_untouchable_enumerated_then_filtered` | untouchable = the viewer's best asset | that asset appears in ≥1 K-chain candidate (`report.enumerated` unchanged vs no-untouchable run; `post_filtered["untouchable"] ≥ 1`) and in NO returned card's give side |
| `test_prefs_filter_not_kill` | not_interested = partner's best asset | same pattern on the receive side |
| `test_pool_cap_respected` | 30-asset rosters, `fit_pool_cap=15`, `fit_max_packages_per_pair=500` | per-pair `enumerated ≤ 500`; `capped_pairs == 1`; pool ≤ 15 unique ids per roster |
| `test_fit_r5_mode_knob` | contender outlook + a lateral (non-upgrade, non-hole) primary receive ≥ floor | mode 1 (default): killed, `killed["K7"] ≥ 1`; mode 0 (via `ts._cfg_override({"fit_r5_mode": 0.0})`): same candidate scored, `r5_fail_scored ≥ 1`, payload `r5_fail is True`, scores unchanged vs a control candidate |
| `test_fit_junk_floor_knob` | 2-asset side padded with a sub-`asset_floor_abs` body | default 0: survives (junk scores badly instead); `fit_junk_floor=1`: `killed["junk"] ≥ 1` |
| `test_fit_gate_binding_sabotage` (T1 — **sabotage 1**) | normal boarded fixture | baseline run emits N > 0 with `killed["K4"] == k`. Then `monkeypatch.setattr(backend.trade_service, "overpay_ok", lambda *a, **kw: False)` — the MODULE attribute, no reload — and rerun: **expected failure mode being proven**: output = 0 cards, `killed["K4"] == report.enumerated_survivors_of_K1K2`; if fit had bound by value the sabotage would be a perfect no-op and the assert fails the build. Monkeypatch auto-restores |
| `test_organic_never_imports_fit` | flag `trade.bakeoff` off; run a fixture `generate_trades` | `"backend.trade_gen_fit" not in sys.modules` after the organic generate; plus source-grep: `inspect.getsource(backend.trade_service)` contains no `trade_gen_fit` |
| `test_diagnostics_keys_complete` | any run, incl. a zero-opponent league | `report.diagnostics()` contains every §1.2 key, always (None/zero-valued, never absent) |
| `test_mismatch_and_fairness_fields` | one known package | `mismatch_score == round(harmonic_mean(you, them), 1)`; `fairness_score == min(gv,rv)/max(gv,rv)` from `_consensus_packages`; `give_value/receive_value` match; `composite_score == round(aggregate, 4)`; `basis` divergence iff both boarded |

### 6.2 `backend/tests/test_bakeoff_serving.py` (extend) / `test_bakeoff_runner.py`

| Test | Fixture shape | Asserts |
|---|---|---|
| `test_serve_fit_bit_excludes_from_draft` | `run_bakeoff` with stub callables (challenger-test idiom); fit stub returns 3 cards; **parametrized over `bakeoff_group_size` ∈ {0, 10}** (the F-6 leak lives on the 0 path — the W1 posture) | with `bakeoff_serve_fit=0`: no fit card in `run.draft.deck`; `"fit" not in run.arm_order`; `arms_json` (via `run_row`) still has `fit` with `cards=3` and its diagnostics; `also_proposed_by` may cite fit. With bit =1: fit cards drafted |
| `test_zero_card_arm_deck_still_fills` (S1b) | `group_size=0`, one arm returns `[]`, others return ≥ deck_limit combined | `len(run.draft.deck) == deck_limit`; empty arm's forfeits > 0 (the 08-18 shrink inverted) |
| `test_impressions_uniform_columns` (T2) | build a mixed-arm row batch through `_log_deck_signal_impressions` with a bakeoff_run whose deck's FIRST card is an unattributed injection | every row dict has the identical key set; every `features_json` decodes with `fit` and `fit_diag` keys present (null allowed) |
| `test_draft_rank_only` (C7b — **sabotage 2**) | two stub arms, identical trades, then multiply ONE arm's every `composite_score` ×100 | **expected failure mode being proven**: the drafted deck (ids in order) is IDENTICAL before and after the scaling — the draft is rank-based; a magnitude-reading draft would reorder and fail the assert |
| `test_fit_diag_inert` (M3 — **sabotage 3**) | full `_run_trade_job`-level fixture or runner-level equivalent: run once with the stamp, capture served deck; run again with `stamp_fit_diag` monkeypatched to **delete** the attribute from every card (`delattr`) | **expected failure mode being proven**: served deck (trade ids in order) byte-identical with and without stamps; impressions differ ONLY in `features_json.fit_diag` (null vs dict). Any ranking path reading `fit_diag` breaks this |
| `test_run_bakeoff_gen_fit_optional` | call `run_bakeoff` WITHOUT `gen_fit` and without fit rostered | passes unchanged (backward compat); with fit rostered and `gen_fit=None` → `arms["fit"].error` non-null, job completes |
| `test_fit_fairness_threshold_none` | fit rostered run | `arms["fit"].fairness_threshold is None` (F-7 posture, like gen_v2) |

### 6.3 `backend/tests/test_model_config_log.py` (new)

| Test | Asserts |
|---|---|
| `test_set_config_logs_change` | `set_config("fit_score_scale", 500.0, source="test")` → `model_config` row value 500.0 with non-null `updated_at`; one `model_config_changes` row with `old_value=400.0, new_value=500.0, source="test"`; return dict carries `old_value` |
| `test_set_config_unknown_key_still_raises` | `KeyError` on an unregistered key; NO change row written |
| `test_admin_put_stamps_source` | PUT via test client with `{"value": 1, "source": "operator"}` → change row `source="operator"`; without source → `"admin-api"` |
| `test_migration_additive` | `_migrate_db()` twice on a seeded DB: idempotent; pre-existing `model_config` rows' values untouched, `updated_at` NULL until first logged write |

**Knob-inventory guard:** `test_no_generation_knob_was_added_without_an_arm_a_decision`
(`test_bakeoff_arm_a_golden.py:527`) goes green only when all 17 names are appended
to `_PINNED_KNOBS` (`:454`) — with the §4 disposition sentences landed in
scope-phase2.md in the same commit. PR-F3 does not merge before this passes
(PLAN-v2 T4).

---

## 7. Config / docs deltas

**`docs/config-reference.md`** — 17 rows (model_config section), one per §4 key:
key, default, consumer, one-line role; plus a note on `PUT /api/admin/config`
gaining optional `source` and the change log.

**`docs/data-dictionary.md`** — rows for: `model_config.updated_at` (ISO UTC, NULL
until first logged write); `model_config_changes` (all 6 columns + index);
`bakeoff_runs.arms_json['fit'].diagnostics` key list (§1.2);
`deck_impressions.features_json.fit` (payload shape, non-null on served fit cards
only) and `.fit_diag` (`{you, them, bucket, ver}` | null, present on every
bake-off row); note that `features_json.surplus_margin` on `model_arm='fit'` rows
is the harmonic mean of the two 0–100 scores, not a value-space surplus.

**`docs/api-reference.md`** — additive `fit` object on trade-card JSON (bake-off
decks only; §1.7 shape; clients ignore unknown keys); `PUT /api/admin/config/<key>`
body gains optional `source`, response gains `old_value`, side effect: change-log
row.

**`docs/plans/fit-challenger/scope-measurement.md`** (owed before PR-M; skeleton —
build fills):
- What: M1 schema (2 DDL items) + set_config funnel + set_knob CLI + readout SQL.
- Analytics: no new events; `model_config_changes` is operator telemetry.
- Schema rows: the two data-dictionary items above.
- Evidence: `test_model_config_log.py`; code-walk that every write path calls
  `set_config`; refusal-case list §5.2.
- Docs table: config-reference / data-dictionary / api-reference rows in-PR.
- Rollback: table is additive; readout is read-only; no flag.

**`docs/plans/fit-challenger/scope-serving.md`** (owed before PR-S; skeleton):
- What: serving re-light knob values (W1 table), serve-bit posture, revert
  playbook (rollback ladder = HLD §6 rungs 1–5).
- Evidence: S1b regression test, re-ranker-bypass code-walk (`bypass_rerankers`,
  `bakeoff_runner.py:374`; bypass sites `server.py:5728–5858`), operator
  TestFlight checklist (draft B §7's 8 steps).
- No code in-PR beyond tests + docs; **no knob values change in-PR** (flips are
  config, post-merge, logged).

**Also owed at build time** (PLAN-v2 §7, unchanged by this LLD): three-model-bakeoff
PLAN addendum, cross-client-invariants n/a note, ADRs ×2, DECISIONS/CHANGELOG/
TEST_LEDGER/NEXT entries, `living-memory/LLD.md` conventions (prefs filter after
score; fit analysis keys on `fit.boards` never `basis`; every fit knob in
`_DEFAULT_CFG` + `_MODEL_CONFIG_DEFAULTS`).

---

## 8. Closing table — every open item resolved or punted

HLD findings (a)–(g) = F-1/F-6/F-7/F-3/F-4/F-2/F-5 + the LLD's own rulings
(R-a…R-j). **Nothing below is left for a coding agent to decide silently.**

| ID | Item | Resolution |
|---|---|---|
| F-1 (a→§3.4-HLD) | serve-bit must act on the `team_draft` fallback, not only `groups_for()` | §2.4: `serving_roster` feeds BOTH `compose_deck(roster=…)` and the `group_size=0` fallback's `draft_order_for`; full `arm_lists` still feed `_agreement`. Test parametrized over both paths |
| F-1 (b) | every knob needs a `_MODEL_CONFIG_DEFAULTS` row or `set_config` KeyErrors | §4: five registrations per key, same commit; `set_knob.py` refusal case 2 names the failure |
| F-7 (c) | fit must NOT join `ENGINE_ARMS` | §2.1: untouched; `groups_for()` else-branch already yields `Group("fit","fit",None)`; `fairness_threshold=None` like gen_v2 |
| F-3 (d) | `run_bakeoff` API extension | §2.4: additive keyword `gen_fit=None`; all six existing callsites keyword-style → compile unchanged; missing-callable-while-rostered = recorded arm error |
| F-4 (e) | `mismatch_score` for fit | §1.10: `round(harmonic_mean(you, them), 1)` — meaningful client rendering, zero when either side is zero, never used for ranking |
| F-2 (f) | `fit_score_even` knob-vs-constant; knob count | §4: it is a KNOB; final count **17** (PRD §9's 13 + even + r5_mode + junk_floor + serve_fit). PLAN-v2's "16" superseded |
| F-5 (g) | tanh table must pin computed values | §1.7: full computed table to 9 decimals; test tolerance 1e-6; PLAN-v2's "88.4/11.6" corrected to 88.0797…/11.9203… |
| F-8 | `ARMS` stays the three-arm fixture | §2.1: `ALL_ARMS` + `GENERATION_ORDER` only |
| F-9 | `_feasible_after` location | §1.6: `trade_optimizer.py:161`, imported module-style (`topt._feasible_after`), with `_pos_counts` `:150` / `_subset_pos_delta` `:181` |
| R-a | HLD §2.2 open lean: fit in the agreement scan while dark | **Adopted** — full `arm_lists` to both draft fns; free `also_proposed_by` telemetry, provably no serving effect |
| R-b | K1 legal-shape list excludes (2,2) and (3,3) | The PRD's closed list is taken literally (equal-count multi-asset swaps are not legal shapes); pinned in `_LEGAL_SHAPES` + `test_k1_shapes`. If the operator intended 2-2/3-3 legal, it is a one-line frozenset edit + test row — flag at review, do not silently widen |
| R-c | "always include owned picks" vs the pool cap | Picks enter the union unconditionally but compete under the `fit_pool_cap` ranking (div-percentile 0, consensus percentile only). The cap is hard (PRD: "Cap unique ids at fit_pool_cap") |
| R-d | `fit_r5_mode = 0` ("score into viewer lens") semantics | v1: predicate still runs; failure does not kill; card tagged `r5_fail` + counted `r5_fail_scored`; **no score penalty** — no operator-authorized math exists for one. Any L4/multiplier treatment is F7's decision at the S4 verdict |
| R-e | when is L2 "missing" for a boarded team | Fires iff ≥1 traded asset has a real `seed_elo` row; otherwise omitted and weights renormalize. (The 1500-default fallback would otherwise make L2 always-computable and the PRD's renorm clause dead) |
| R-f | `boards` enum | Extended additively to `{both, viewer, partner, none}` — a partner-only-boarded pair scores them-side L1/L2, and stamping it `none` would corrupt the C4 analysis key. M2 SQL groups by the value; no query enumerates the closed set |
| R-g | PRD §6.6 "max_per_opponent / global target — same numbers as the job" | Adapter passes `max_per_opponent=None` (gen_v2 parity; operator 2026-08-16 no-truncation). The job's per-target caps live in `_order_deck` (`deck_max_per_target`, `server.py:3933`) which `bypass_rerankers` disables on interleaved decks for EVERY arm equally; deck size is bounded by `bakeoff_deck_limit` + C4/C4b. Applying an extra module-side per-opponent cap would treat fit differently from the arms it is compared against |
| R-h | do `fit.lenses` nulls serialize? (HLD §9) | Yes — all six lens keys always present, null-valued when unfired (M4 null-share contract) |
| R-i | `fit_min_them`/`fit_min_aggregate` placement | Post-score filter step 1 (before preference filters) so `post_filtered` counters describe the visible universe; defaults 0 = off (PRD: "leave 0") |
| R-j | diagnostics population basis | Bucket/character metrics (`one_sided_pct`, bucket mix, `median_aggregate`, top-quartile shares) computed over the scored, ranked, **pre-F4** set — they describe the generator; F4 counters describe the viewer's prefs. W3 soak bars read the same fields |
| Punt-1 | M2 §1's config-snapshot *diff tooling* (beyond the SQL comment block) | Manual per the Friday runbook in v1; automating the diff is a build-time nice-to-have, not a gate |
| Punt-2 | `need_fit` stamp cost | Stamped via the existing helper (§1.10); if the dry run shows it material in `ms`, dropping the stamp is pre-authorized (PRD: "may be stamped") — record in the dry-run TEST_LEDGER entry |
| Punt-3 | SQLite translations of the readout SQL | Comment block only (readout runs against prod Postgres); not tested in CI |
