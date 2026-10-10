# LLD — Value-core trade engine

**Date:** 2026-09-30 · **Status:** spec · Companion: [prd.md](prd.md), [hld.md](hld.md), [specs.md](specs.md)

Line numbers are for `origin/main` at `3bb981ed` and are approximate once other edits land. Anchor on the quoted code, not the number. The shared dataclasses are written out in full in [specs.md §3](specs.md#3-shared-interface-backendvalue_coretypespy-verbatim). This document refers to them by name.

## Contents

1. [Module map](#1-module-map)
2. [Shared contract](#2-shared-contract)
3. [Configuration](#3-configuration)
4. [Core: `backend/value_core/core.py`](#4-core-backendvalue_corecorepy)
5. [Ranking layer: windows, ranking, deck](#5-ranking-layer-windows-ranking-deck)
6. [Pipeline: `backend/value_core/pipeline.py`](#6-pipeline-backendvalue_corepipelinepy)
7. [Adapter: `backend/value_core/adapter.py`](#7-adapter-backendvalue_coreadapterpy)
8. [Eval bench](#8-eval-bench)
9. [Integration edits in existing files](#9-integration-edits-in-existing-files)
10. [Logging and error handling summary](#10-logging-and-error-handling-summary)

---

## 1. Module map

| File | Package | Imports allowed | Purpose |
|---|---|---|---|
| `backend/value_core/__init__.py` | WP1 | nothing | Docstring only: "Value-core trade engine; see docs/plans/value-core-engine/". **No imports**, so importing one submodule never pulls in the others. |
| `backend/value_core/types.py` | WP1 | stdlib | The shared contract ([specs.md §3](specs.md#3-shared-interface-backendvalue_coretypespy-verbatim)) |
| `backend/value_core/core.py` | WP1 | stdlib, `.types`, `backend.power_rankings` (`optimal_starter_slots`, `LINEUP_SLOT_ELIGIBILITY`) | Value-only enumeration + hard rules |
| `backend/value_core/windows.py` | WP2 | stdlib, `.types`, `backend.trade_service` (`infer_team_outlook`, `_c`) | Team windows |
| `backend/value_core/ranking.py` | WP2 | stdlib, `.types`, `backend.power_rankings` (`optimal_starters`) | Three scores, priority, card reasons |
| `backend/value_core/deck.py` | WP2 | stdlib, `.types`, `.ranking` (`card_reasons`) | Deck assembly |
| `backend/value_core/pipeline.py` | WP3 | `.types` at module level; `.core`, `.ranking`, `.deck` **lazily inside `run`** | One-call composition. The lazy imports let WP3's serving tests stub `run` before WP1 and WP2 land. |
| `backend/value_core/adapter.py` | WP3 | stdlib, `.types`, `backend.trade_service` (`TradeCard`, `elo_to_value`, `value_to_elo`, `_shrink_user_elo`), `backend.ranking_service` (`RankingService`), `backend.trade_policy` (`shrink_board`, `confidence_map`; imported inside `partner_board_from`) | App objects → contract → `TradeCard` |
| `backend/eval/value_core_bench.py` | WP4 | stdlib, `backend.value_core.*`, `backend.tools.prod_analytics`, `backend.outlook.league_state`, `backend.trade_service` (`elo_to_value`), `sqlalchemy` (freeze only) | Freeze / run / guardrails |
| `backend/eval/value_core_recall.py` | WP4 | stdlib, `backend.value_core.*`, `backend.dp_values_history`, `backend.data_loader` (`seed_elo_for_value`), `backend.pick_values` (`pick_pool_value`), `backend.trade_service` (`elo_to_value`) | Historical recall + band calibration |
| `backend/eval/blind_grade.py` | WP4 | stdlib, `backend.tools.prod_analytics` (served card sets only) | Grade sheet export / import |

**Leaf rules.**
- Nothing in `backend/value_core/` or the three eval files imports `backend.server`.
- `server.py` imports `backend.value_core.*` **lazily, inside `_run_value_core_job`**. With the flag off the package is never imported. A test pins this ([specs.md](specs.md), WP3).

## 2. Shared contract

All dataclasses live in `backend/value_core/types.py`, written verbatim from [specs.md §3](specs.md#3-shared-interface-backendvalue_coretypespy-verbatim):

- **Constants:** `ENGINE_ID`, `ENGINE_VERSION`, `TOP_WINDOW`, `CORE_POSITIONS`.
- **Aliases:** `Window`, `AssetKind`, `Side`.
- **Dataclasses:** `Asset`, `Standing`, `TeamWindow` (with `DEFAULT_WINDOW`), `Team`, `RosterRules`, `LeagueSnapshot`, `Board`, `Request`, `CoreConfig`, `RankConfig`, `FairTrade`, `TradeVerdict`, `CoreDiagnostics`, `Scores`, `ScoredTrade`, `DeckEntry`, `PipelineResult`.

**Identity.** `Team.team_id` and `FairTrade.partner_team_id` are **league** identities: the roster `owner_id`, which is `LeagueMember.user_id`. The viewer's team id is `ctx.league_user_id`, never the account id. See `backend/CLAUDE.md` §Identity.

**Units.** Every `market` and board value is in engine value units: `trade_service.elo_to_value(elo) = 1000·exp(0.005·(elo−1500))` (`trade_service.py:1648`).

## 3. Configuration

**Flag.** `trade.value_core`, attribute `FLAGS.trade_value_core`, default `false`. It is read only through `server._value_core_enabled()` ([§9.1](#91-backendserverpy)).

**`model_config` keys.** All are new Floats. They are seeded in `database._MODEL_CONFIG_DEFAULTS` ([§9.4](#94-backenddatabasepy)) and read by the adapter from the job's captured config dict `dict(_trade_service_mod._cfg)`. `reload_config()` merges every `model_config` row into `_cfg` (`trade_service.py:1331`), and `_trade_request_signature` hashes `_cfg` (`server.py:3090`), so changing a knob invalidates cached decks. **None are added to `trade_service._DEFAULT_CFG`**, which keeps `test_bakeoff_arm_a_golden.py:897` untouched. If a key is missing from `_cfg`, the dataclass default is used.

| Key | Default | Clamp (adapter) | Maps to | Meaning |
|---|---:|---|---|---|
| `vc_band` | 0.20 | [0.01, 0.50] | `CoreConfig.band` | The **overpay** side of the fairness band: the most MORE market value the viewer may give. A trade needs premium-adjusted ratio (receive/give) ≥ 1/(1+band). |
| `vc_gain_band` | 0.10 | [0.01, 0.50] | `CoreConfig.gain_band` | The **gain** side: the most MORE market value the viewer may receive, i.e. the partner's loss. A trade needs ratio ≤ 1+gain_band. The band is asymmetric by the operator's 2026-10-01 decision; the real-bench evidence is in the specs §3.1 change log. |
| `vc_stud_premium` | 0.15 | [0.0, 0.50] | `CoreConfig.stud_premium` | Premium at an elite headliner; scales as (headliner/elite)² |
| `vc_untouchable_min_ratio` | 1.08 | [1.0, 2.0] | `CoreConfig.untouchable_min_ratio` | A give package containing an untouchable needs adjusted ratio ≥ this |
| `vc_max_assets_per_side` | 14 | int [4, 20] | `CoreConfig.max_assets_per_side` | Top-N eligible assets per team used to build packages (pins always added) |
| `vc_max_per_partner` | 200 | int [10, 1000] | `CoreConfig.max_per_partner` | Fair trades kept per partner |
| `vc_throwin_min_ratio` | 2.0 | [1.0, 10.0] | `CoreConfig.throwin_min_ratio` | A piece too small for the junk rules may ride along as a **throw-in** only if its recipient's board values it at ≥ this × consensus market, and at ≥ `asset_floor_abs` (§4.3) |
| `vc_w_value` | 1.0 | ≥ 0 | `RankConfig.w_value` | Weight of the value score |
| `vc_w_outlook` | 1.0 | ≥ 0 | `RankConfig.w_outlook` | Weight of the outlook score |
| `vc_w_rank` | 1.0 | ≥ 0 | `RankConfig.w_rank` | Weight of the rank score. If all three weights are 0, they become (1, 1, 1). |
| `vc_repeat_penalty` | 0.15 | [0.0, 1.0] | `RankConfig.repeat_penalty` | Priority points subtracted per prior appearance of the card's most-shown asset. Partner repeats cost half. |
| `vc_player_cap` | 3 | int [1, 30] | `RankConfig.player_cap` | Max cards any one asset, on either side, may appear in within the first `TOP_WINDOW` (30). The bench guardrail (§8.2) counts acquired assets only. |
| `vc_standings_weight` | 0.30 | [0.0, 1.0] | `windows.infer_windows(standings_weight=)` | Full weight of the points-for index in the window score; ramps linearly from week 0 to week 8 |
| `vc_testers_only` | 1.0 | ≥ 1 means on | `server._value_core_live` | 1 = serve only the tester allowlist while the flag is on |

**Existing keys reused, read-only.** These are not duplicated:
- `asset_floor_abs` (450) → `CoreConfig.asset_floor_abs`
- `filler_min_frac` (0.25) → `CoreConfig.filler_min_frac`. These two are the operator's two floors from #141 (`trade_service.py:271`, `:278`).
- `shrink_pseudocount` (4), `user_elo_shrink` and `placement_tier_clamp`, all via `_shrink_user_elo`
- `infer_contender_cut` / `infer_rebuilder_cut` (±0.08), via `trade_service._c` in `windows.py`

**Code constants.** Not knobs; each is named in its module:
- `core.py`: `TIME_BUDGET_S = 8.0`, `MAX_CHECKS_PER_PARTNER = 40_000`, `MAX_PACKAGE_SIZE = 3`, `MAX_THROWIN_OPTIONS = 3` (qualifying throw-ins tried per side, per candidate pair), `THROWIN_MIN_COMPARISONS = 3` (the recipient's evidence a throw-in needs), `PREMIUM_EXPONENT = 2.0`, `RATIO_TOL = 1e-9`
- `ranking.py`: `DELTA_SATURATION = math.log(1.25)`, `RANK_GAP_SATURATION = 0.30`, `SIDE_THRESHOLD = 0.60`, `FAIR_PCT = 3`, `RANK_SPOTS_MIN = 5`, `YOUTH_WEIGHTS`
- `deck.py`: `PARTNER_PENALTY_FACTOR = 0.5`, `PICK_IDEA = "PICK"`
- `windows.py`: `STANDINGS_RAMP_WEEKS = 8`
- `adapter.py`: `DEFAULT_LINEUP`

---

## 4. Core: `backend/value_core/core.py`

### 4.1 Public API

```python
TIME_BUDGET_S = 8.0
MAX_CHECKS_PER_PARTNER = 40_000
MAX_PACKAGE_SIZE = 3
MAX_THROWIN_OPTIONS = 3   # qualifying throw-ins tried per side, per candidate pair (best recipient surplus first)
THROWIN_MIN_COMPARISONS = 3   # recipient evidence a throw-in needs: one matchup is not an opinion
PREMIUM_EXPONENT = 2.0
RATIO_TOL = 1e-9
REJECT_CODES = ("floor", "band", "filler", "breakup", "picks_for_players", "redundant", "untouchable",
                "reducible", "roster_size", "lineup")   # value-core-2: breakup, picks_for_players; -3: redundant


def throwin_ok(asset_id: str, recipient_board: Board | None, *,
               market: float, cfg: CoreConfig) -> bool:
    """Throw-in rule: a piece too small for the junk rules may ride along only if its
    RECIPIENT values it at >= cfg.throwin_min_ratio x consensus market and at least the
    asset floor. Evidence is required on both sides: the piece has a consensus value
    (market > 0) and the recipient really ranked him (comparisons >=
    THROWIN_MIN_COMPARISONS). Otherwise False."""


def effective_band(band: float, fairness_threshold: float | None) -> float:
    """The band actually applied. The client's fairness preference may only TIGHTEN it:
    min(band, max(0.02, 1 - fairness_threshold)); None -> band unchanged."""


def stud_premium(headliner_market: float, elite_value: float, max_premium: float) -> float:
    """max_premium * min(1, headliner_market / elite_value) ** PREMIUM_EXPONENT.
    elite_value <= 0 or headliner_market <= 0 -> 0.0."""


def evaluate_trade(snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig, *,
                   partner_team_id: str, give: Sequence[str],
                   receive: Sequence[str]) -> TradeVerdict:
    """Judge ONE explicit package with the same rules find_fair_trades applies, in the
    order of REJECT_CODES, ignoring top-N truncation, pins and not-interested. `trade`
    is populated whenever both sides are non-empty and priced (even when ok is False),
    so callers can read adjusted_ratio for calibration. Package size is NOT limited here
    (real trades can have 4+ pieces a side; find_fair_trades never generates them).
    Raises ValueError when a give id is not on the viewer's team, a receive id is not on
    the partner's team, a side is empty, or an id is not in snapshot.assets."""


def find_fair_trades(snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig, *,
                     time_budget_s: float = TIME_BUDGET_S,
                     max_checks_per_partner: int = MAX_CHECKS_PER_PARTNER,
                     ) -> tuple[list[FairTrade], CoreDiagnostics]:
    """The unranked fair pool for the viewer against every partner (or request.partner_team_id).
    Deterministic: same inputs -> same list, same order. Never raises for an empty result.
    Raises ValueError only when request.viewer_team_id is not in snapshot.teams."""
```

### 4.2 Pricing a trade: ratio and stud premium

For a viewer package G and a partner package R, each a tuple of asset ids:

1. `give = Σ market(G)` and `receive = Σ market(R)`, both raw.
2. **Headliner.** H is the single asset with the highest market in G ∪ R. Ties on market are broken by id ascending. If the top market value is tied *across* the two sides, set `premium = 0` and `premium_side = None`: nobody is consolidating a unique best asset.
3. **Premium.** Let `side_H` be the side containing H, `n_H` that side's piece count and `n_other` the other side's count. A throw-in (§4.3) is not counted as a piece here.
   - If `n_H < n_other`: `p = stud_premium(market(H), snapshot.elite_value, cfg.stud_premium)`, and the package on `side_H` is credited `×(1+p)`.
   - Otherwise `p = 0`.
   - `premium_side` is `"receive"` when the viewer receives H and is credited, `"give"` when the viewer gives H and is credited.
4. `adjusted_ratio = (receive·(1+p if premium_side=="receive" else 1)) / (give·(1+p if premium_side=="give" else 1))`.
5. **Band (asymmetric).** `b = effective_band(cfg.band, request.fairness_threshold)` is the overpay side and `g = effective_band(cfg.gain_band, request.fairness_threshold)` the gain side. The trade passes iff `1/(1+b) − RATIO_TOL ≤ adjusted_ratio ≤ 1+g + RATIO_TOL`: the viewer may give up to `b` more market value than they get, but take at most `g` more. The client preference tightens both sides, never loosens either.

**Worked example.** `elite_value = 8457`, `band = 0.20`, `gain_band = 0.10`, `stud_premium = 0.15`.
- The viewer receives an 8457 stud for two WRs worth 4200 + 4200.
- p = 0.15, so adjusted receive = 9725.6 and ratio = 9725.6 / 8400 = 1.158. That is above 1 + gain_band = 1.10, so the trade is **rejected**: the partner would be under-paid.
- With 4600 + 4400 = 9000 given, ratio = 1.081, so the trade is **kept**. The viewer pays 6.4% raw over the stud's value.
- The mirror trade, where the viewer **gives** the stud for the 4200 + 4200 pair, has ratio = 8400 / 9725.6 = 0.864 ≥ 1/1.2 = 0.833, so it is **kept**: the viewer may overpay by up to 20%.
- A mid-tier headliner of 2117 (a Mid 1st) gets p = 0.15·(2117/8457)² = 0.0094, i.e. "barely any".

### 4.3 Hard rules, in order

These are applied per candidate pair in `find_fair_trades`, and identically in `evaluate_trade`. The first failure increments `CoreDiagnostics.rejected[code]`.

| # | Code | Rule |
|---|---|---|
| 1 | `floor` | Every asset in G ∪ R except the trade's throw-in has `market ≥ cfg.asset_floor_abs`. In `find_fair_trades` this holds by construction (candidates are pre-filtered, and a throw-in is added only as one), so it only fires in `evaluate_trade`. |
| 2 | `band` | §4.2 step 5 |
| 3 | `filler` | Every asset in G ∪ R except the throw-in has `market ≥ max(cfg.asset_floor_abs, cfg.filler_min_frac × market(H))`. The floor is relative to the **trade** headliner, which is stricter than `filler_ok`'s per-side headliner (`trade_service.py:2230`). |
| 3a | `breakup` | **value-core-2 (operator, 2026-10-09, from the Calibration grades).** The viewer never breaks up their best piece: `R.top ≥ cfg.breakup_min_ratio × G.top − RATIO_TOL` (0.70; `top` = the side's biggest non-throw-in piece). Viewer side only — a partner selling their best piece for several of the viewer's is left to the band and the outlook score. In the first Calibration round the cards this removes graded 2.00 (23% would-send) against 2.72 for the rest. `breakup_min_ratio = 0` disables it. |
| 3b | `picks_for_players` | **value-core-2 (operator, 2026-10-09).** A team whose window is `rebuilder` (declared `rebuilder` or `jets` / "blow it up", or inferred) never gives a pick while receiving a player: reject when the viewer is rebuilding and G holds a pick and R a player, or the partner is rebuilding and R holds a pick and G a player. Pick-for-pick and player-for-pick are untouched. This is the one rule that reads a team window (`Team.window`); `cfg.rebuilders_keep_picks = False` disables it. |
| 3c | `redundant` | **value-core-3 (operator, 2026-10-10: McBride offered to the Bowers owner).** Applied to both sides. A team does not take a **TE** (every format) or a **QB** (only when the lineup has no `SUPER_FLEX`) when, after the trade, it keeps as many players at that position as it has dedicated slots for it (min 1), each worth `≥ cfg.redundancy_min_ratio × market` of the incoming player (0.70). Other incoming players at the position count too. Sending a comparable one back frees the slot. A throw-in is never judged. `redundancy_min_ratio = 0` disables it. In round-2 Calibration decks it would have removed 19–30% of every engine's cards, and the operator graded those lower. |
| 4 | `untouchable` | If G ∩ `request.untouchable_ids` ≠ ∅: `adjusted_ratio ≥ cfg.untouchable_min_ratio − RATIO_TOL`. Sets `uses_untouchable = True`. |
| 5 | `reducible` | For each side with ≥ 2 assets, and each asset x on that side that is **not** the side's top asset, **not** in `request.pinned_give_ids ∪ request.pinned_receive_ids` and **not** the throw-in: re-price the trade without x (§4.2 fully recomputed, premium included). If the result passes the band, reject: x is filler, since the trade is fair without it. |
| 6 | `roster_size` | Only when `snapshot.rules.max_players` is not None. For each team T: `players_before(T) = #{a ∈ T.asset_ids : kind=="player"} + T.other_players`; `after = before − players_out + players_in`; `drops = max(0, after − max(max_players, before))`; `droppable(T) = #{a ∈ T.asset_ids : kind=="player" and market < cfg.asset_floor_abs}`, minus the sub-floor players T gives in this trade (only a throw-in can be one): a piece leaving in the trade is not bench T can drop. Reject if `drops > droppable(T)` for either team. Otherwise record `drops_needed = (drops_viewer, drops_partner)`. |
| 7 | `lineup` | For each team, the number of unfillable lineup slots after the trade must be ≤ the number before (§4.4). |

The pins and not-interested filter are applied at package construction (§4.5), not as reject codes.

**Throw-ins (operator, 2026-10-01).** *"Throwins are fine, but only if there is a clear throwin that the recipient values much higher than consensus (double the value)."* A **throw-in** is one piece that is junk for this trade, `market < max(cfg.asset_floor_abs, cfg.filler_min_frac × market(H))`, and that `throwin_ok` qualifies for its **recipient**:
- The recipient's board values it at `≥ cfg.throwin_min_ratio × market` (2×) **and** `≥ cfg.asset_floor_abs`.
- Evidence on both sides: `market > 0` (an unpriced player has no "double" to clear) and the recipient's board has `comparisons ≥ THROWIN_MIN_COMPARISONS` (3) for that player (a default Elo, or one or two matchups, is not an opinion).
- **Whose board.** A throw-in the viewer receives is judged on `request.board`. A throw-in the partner receives is judged on that partner's **published** board, `snapshot.partner_boards[partner]`. A partner with no entry there (no real rankings) can never receive a throw-in.

A trade carries **at most one** throw-in, and each side keeps ≤ `MAX_PACKAGE_SIZE` pieces including it. The throw-in is exempt from `floor`, `filler` and `reducible`, and it never sets a side's top or low. It still counts in the market sums (so in the band), in the positions (lineup) and in the roster sizes, and the giver no longer counts it as droppable bench. It is **not** a piece for the stud premium (§4.2 step 3, also in the `reducible` re-pricing), so adding one never switches the premium on or off. `FairTrade.throwin` names it; it is `None` otherwise. `evaluate_trade` finds the throw-in of an explicit package itself: a piece that is junk for the trade, is not its side's only piece, and qualifies for its recipient. If several qualify, the biggest recipient surplus (board value − market, then id) wins.

### 4.4 Lineup check

`LINEUP_SLOT_ELIGIBILITY` (`power_rankings.py:38-47`) defines the enforced slots. K, DEF, IDP, BN, IR and TAXI are ignored: no IDP or kicker ever enters a package, so those lineups cannot change.

**Precompute per team, once per call:**
- `count[p]` for p in `CORE_POSITIONS`;
- `need[p]` = the number of enforced slots in `rules.lineup_slots` whose eligibility contains p;
- `unfilled_before` = the number of `None` players in `optimal_starter_slots(rows(T), list(rules.lineup_slots))` (`power_rankings.py:120`), where rows are `{"player_id", "position", "value": market}` for the team's core players.

**Per trade:**
1. `count'[p] = count[p] − out[p] + in[p]`.
2. **Fast accept:** if every position whose count dropped still has `count'[p] ≥ need[p]`, the trade cannot open a slot. Proof: that position alone can refill every slot that could have used it.
3. Otherwise compute `unfilled_after` with `optimal_starter_slots` on the post-trade rows, and reject if `unfilled_after > unfilled_before`.

### 4.5 Enumeration algorithm

```
b      = effective_band(cfg.band, request.fairness_threshold)        # overpay side
gb     = effective_band(cfg.gain_band, request.fairness_threshold)   # gain side
lo, hi = 1/(1+b), 1+gb
pmax   = cfg.stud_premium
viewer = snapshot.teams[request.viewer_team_id]           # KeyError -> ValueError
partners = [request.partner_team_id] if request.partner_team_id else sorted(t for t in teams if t != viewer)
           (a partner id not in teams, or equal to the viewer -> no partners, empty result)

candidates(T, exclude, must):
    eligible = [a in T.asset_ids if market(a) >= cfg.asset_floor_abs and a not in exclude]
    sort by (-market, id); keep first cfg.max_assets_per_side; append any a in must∩eligible not kept
packages(cands):                                           # sizes 1..3
    for combo in combinations(cands, k), k = 1..MAX_PACKAGE_SIZE:
        ids sorted by (-market, id); top = market(ids[0])
        keep iff every other id has market >= cfg.filler_min_frac * top      # within-package pre-prune
        record Package(ids, total, top, low=min market, n_players, pos_delta Counter)

V = packages(candidates(viewer, exclude=∅, must=request.pinned_give_ids))
V = [g for g in V if pinned_give satisfied]   # "any": g∩pins≠∅ ; "all": pins ⊆ g ; no pins: all
V sorted by (-total, ids), then round-robin interleaved by headliner (g.ids[0])   # lead change 2026-09-30
for partner in partners (deterministic order):
    if budget exceeded: diag.budget_exhausted = True; break
    P = packages(candidates(partner, exclude=request.not_interested_ids, must=request.pinned_receive_ids))
    if request.pinned_receive_ids: P = [r for r in P if r ∩ pinned_receive ≠ ∅]; skip partner if P empty
    P sorted by (total, ids); totals = [r.total for r in P]
    # throw-in pools (§4.3), uncapped, biggest recipient surplus (value - market) first
    give_tis = [a in viewer.asset_ids, not untouchable, throwin_ok(a, snapshot.partner_boards.get(partner))]
    recv_tis = [a in partner.asset_ids, not untouchable, not not-interested, throwin_ok(a, request.board)]
    max_give_ti, max_recv_ti = largest market in each pool (0 if empty)
    checks = {base: 0, throwin: 0}; fair = []; truncated = False   # two separate check budgets
    for g in V:
        lo_raw = g.total * lo / (1+pmax);  hi_raw = g.total * hi * (1+pmax)   # widest window any premium allows
        # the bisect window is widened just enough to reach pairs a throw-in can close
        for r in P[bisect_left(totals, lo_raw - max_recv_ti) : bisect_right(totals, (g.total + max_give_ti) * hi * (1+pmax))]:
            variants = []
            if lo_raw <= r.total <= hi_raw: variants.append((base, g, r))
            if len(g) < MAX_PACKAGE_SIZE:   # first MAX_THROWIN_OPTIONS of give_tis that pass, in pool order:
                for ti in give_tis (ti not in g, junk vs max(g.top, r.top), r.total inside g+ti's raw window):
                    variants.append((throwin, g + ti, r))   # the viewer adds a piece the partner values >= 2x
            if len(r) < MAX_PACKAGE_SIZE:   # same cut for recv_tis
                for ti in recv_tis (ti not in r, junk vs max(g.top, r.top), r.total + m(ti) inside g's raw window):
                    variants.append((throwin, g, r + ti))   # the partner adds a piece the viewer values >= 2x
            for (kind, gg, rr) in variants:                 # at most one throw-in per trade
                checks[kind] += 1
                if checks[kind] > max_checks_per_partner:
                    truncated = True
                    if kind == base: stop this partner
                    else: skip this variant                 # throw-ins never starve base pairs
                if sum(checks) % 1000 == 0 and elapsed > time_budget_s: diag.budget_exhausted = True; stop all
                verdict = rules §4.2–§4.4 on (gg, rr)
                if ok: fair.append(FairTrade(..., throwin=the added piece or None))
    if len(fair) > cfg.max_per_partner:
        fair.sort(key=(-market(H), len(give)+len(receive), abs(log(adjusted_ratio)), give, receive))
        fair = round_robin(fair, group=(give[0], receive[0]))[:cfg.max_per_partner]; truncated = True
    diag.truncated_partners += int(truncated)          # at most once per partner, either cap
    out.extend(fair)
out.sort(key=(partner_team_id, -market(H), n_assets, abs(log(adjusted_ratio)), give, receive))
```

**Throw-in variants.** A throw-in is tried as an add-on to each candidate pair, not as a package of its own: it can close a gap the pair alone misses (0.867 → inside the band) or sweeten a pair that is already fair. When both versions survive, they share a trade idea (§5.6) and the deck keeps the higher-priority one. The shortlist is cut per candidate pair, **after** the junk check: a bigger piece the recipient also loves is not junk in that pair, so it cannot crowd a real throw-in off the list. Throw-in variants have their own budget of `max_checks_per_partner` checks, separate from base pairs. When it runs out the partner counts as truncated, but only variants stop, so throw-ins never starve distinct base pairs.

**Cap order and the value-only principle (revised by the lead, 2026-09-30).** Both caps spread across headliners instead of favoring the biggest. The viewer's packages are enumerated round-robin by headliner, so the check cap can't be spent entirely on the viewer's top assets. When the per-partner cap binds, it keeps trades round-robin over (give headliner, receive headliner) pairs, each pair in the order above. Neither step uses a preference signal. The original rule, biggest headliner first, made 92% of a 14-team pool give away one of the viewer's top 3 assets, and only 8 give assets reached the first 30 cards. With the revised rule the share is 12% and 14 give assets reach the first 30. `test_pool_spreads_across_give_headliners` pins this. The diagnostics record every truncation.

### 4.6 Complexity caps and pruning

| Bound | Value | Enforced by |
|---|---|---|
| Candidate assets per side | ≤ `max_assets_per_side` + pins, so 14 + 3 = 17 | `candidates()` |
| Packages per side | ≤ C(17,1)+C(17,2)+C(17,3) = **833**; ≤ 469 without pins | `MAX_PACKAGE_SIZE = 3` |
| Pair checks per partner | ≤ **40,000** base pairs, plus ≤ 40,000 throw-in variants (a separate budget; only when a board qualifies throw-ins) | `max_checks_per_partner` |
| Pair checks per league (14 teams) | ≤ 13 × 40,000 = **520,000** base pairs (twice that with throw-in variants) | the above |
| Per-check cost | O(1), plus ≤ 4 re-pricings (reducible), plus a lineup fill only when the fast accept fails | §4.3–§4.4 |
| Wall clock | stops at **8 s**, checked every 1,000 checks | `time_budget_s` |
| Output | ≤ `max_per_partner` × partners, so **≤ 2,600** for 14 teams | per-partner cap |

**Expected load.** A 12-team league with about 250 packages per side after the within-package pre-prune, and a raw window of about ±27% (band ±10% × premium ≤ 15%), sees around 30 candidates per give package. That is about 7.5k checks per partner and about 80k per league: roughly 0.5–1.5 s in CPython. That estimate predates the asymmetric band: the default pay-20% / take-10% band moves the low edge of the raw window from about 0.79× to about 0.72× of the give total, and each pair can add up to 2 × `MAX_THROWIN_OPTIONS` throw-in variants. Those run on their own check budget (§4.5) and inside the same time budget. The perf test ([specs.md](specs.md), WP1) pins the deterministic bounds.

### 4.7 Diagnostics and logging

- `CoreDiagnostics` is filled as it goes: `partners` is the number actually enumerated, `packages_viewer = len(V)`, `pairs_checked`, `fair`, `rejected`, `truncated_partners`, `budget_exhausted`, and `elapsed_ms`.
- `core.py` does **no logging** and no I/O. The caller logs the diagnostics ([§10](#10-logging-and-error-handling-summary)).

---

## 5. Ranking layer: windows, ranking, deck

### 5.1 `backend/value_core/windows.py`

```python
STANDINGS_RAMP_WEEKS = 8
DECLARED_MAP = {"championship": "contender", "contender": "contender",
                "rebuilder": "rebuilder", "jets": "rebuilder", "not_sure": "middle"}


def standings_weight_for(completed_weeks: int, full_weight: float) -> float:
    """max(0, full_weight) * min(1, max(0, completed_weeks) / STANDINGS_RAMP_WEEKS).
    Week 0 -> 0.0; week 3 at 0.30 -> 0.1125; week >= 8 -> full_weight."""


def pf_indices(standings: Mapping[str, Standing]) -> dict[str, float]:
    """Points-for index in [-1, 1] per team: pct = (#teams with lower PF
    + 0.5 * (#other teams with equal PF)) / (n - 1); index = 2*pct - 1.
    Fewer than 2 teams -> {}. PF [100, 200, 300, 400] -> [-1, -1/3, 1/3, 1]."""


def window_from_declared(value: str | None) -> Window | None:
    """DECLARED_MAP lookup; unknown/None -> None."""


def infer_windows(*, team_rosters: Mapping[str, Sequence[str]], players: Mapping[str, object],
                  pick_shares: Mapping[str, float], standings: Mapping[str, Standing],
                  completed_weeks: int, declared: Mapping[str, str | None],
                  standings_weight: float) -> dict[str, TeamWindow]:
    """One TeamWindow per team in team_rosters. `players` holds duck-typed Player objects
    (position, age, search_rank, pick_value). This is what trade_service.infer_team_outlook
    reads (trade_service.py:3999, :4095-4110)."""
```

**`infer_windows` algorithm.**
1. `n = len(team_rosters)` and `w = standings_weight_for(completed_weeks, standings_weight)`.
2. `pf = pf_indices({t: s for t, s in standings.items() if t in team_rosters})` if `w > 0`, else `{}`.
3. For each team t, in sorted order:
   1. Call `label, score, _ = trade_service.infer_team_outlook(list(roster), players, pick_share=pick_shares.get(t, 0.0), num_teams=n)`.
      - No `starter_signal`, `odds_signal` or `first_round_ledger` is passed. That gives the legacy age+picks vector regardless of `trade.outlook_composite` / `trade.outlook_net_firsts` (INV-372b / INV-365b, `trade_service.py:4074-4083`), so value-core windows never move when those flags move.
      - On any exception, use `DEFAULT_WINDOW` for that team.
   2. `s = score + w * pf[t]` if t is in pf, else `score`.
   3. `window = "contender"` if `s ≥ _c("infer_contender_cut")`, `"rebuilder"` if `s ≤ _c("infer_rebuilder_cut")`, else `"middle"`.
   4. If `window_from_declared(declared.get(t))` is not None, it replaces `window` and `source = "declared"`. Otherwise `source = "inferred"`.
   5. Build `TeamWindow(window, round(s, 4), source, pf.get(t), w if t in pf else 0.0)`.

### 5.2 `backend/value_core/ranking.py`: public API

```python
DELTA_SATURATION = math.log(1.25)
RANK_GAP_SATURATION = 0.30
SIDE_THRESHOLD = 0.60
FAIR_PCT = 3
RANK_SPOTS_MIN = 5
YOUTH_WEIGHTS = ((24, 1.0), (26, 0.7), (28, 0.4))   # age <= k -> weight; older -> 0.15; picks 1.0; unknown 0.5


def youth_weight(asset: Asset) -> float: ...
def lineup_value(asset_ids: Iterable[str], snapshot: LeagueSnapshot) -> tuple[float, frozenset[str]]:
    """(sum of market over the value-optimal starters, starter ids) via
    power_rankings.optimal_starters on core-position players (power_rankings.py:99)."""
def positional_ranks(snapshot: LeagueSnapshot, values: Mapping[str, float]) -> dict[str, int]:
    """1-based rank of every player asset within its position by (-value, id). Picks absent."""
def score_trades(snapshot: LeagueSnapshot, request: Request, trades: Sequence[FairTrade],
                 cfg: RankConfig) -> list[ScoredTrade]:
    """Same length and order as `trades`. Raises ValueError if cfg weights sum <= 0."""
def card_reasons(scored: ScoredTrade, snapshot: LeagueSnapshot, request: Request) -> tuple[str, ...]:
    """1-3 strings, templates in §5.5."""
```

### 5.3 Score formulas

`clamp01(x) = min(1, max(0, x))`.

**Precompute once per `score_trades` call:**
- `pre[T] = lineup_value(T.asset_ids)` for the viewer and every partner that appears.
- `S` = the median market over the union of all teams' pre-trade starters. If S ≤ 0 or undefined, use 1000.0.
- `consensus_rank = positional_ranks(snapshot, {id: market})`.
- If `request.board` is set: `personal(a) = board.values.get(a, market(a))` and `personal_rank = positional_ranks(snapshot, personal)`.

**Value score.**
```
delta_ln = ln(receive_market / give_market)
s_delta  = clamp01(0.5 + delta_ln / (2 * DELTA_SATURATION))          # +25% -> 1.0, -20% -> 0.0
b        = argmax market over receive (ties: id asc)
post_v   = lineup_value(viewer.asset_ids - give + receive)
best_in_starter = asset(b).kind == "player" and b in post_v.starters
s_piece  = 1.0 if best_in_starter or market(b) >= snapshot.first_round_value
           else market(b) / snapshot.first_round_value
value    = 0.5 * s_delta + 0.5 * s_piece
```

**Outlook score.** For each side, the viewer V and the partner P, with `out`/`in` from that team's perspective:
```
lineup_gain(T) = lineup_value(T.asset_ids - out + in).value - pre[T].value
future_gain(T) = Σ_in market*youth_weight - Σ_out market*youth_weight
s_con = clamp01(0.5 + 0.5 * lineup_gain / S)
s_reb = clamp01(0.5 + 0.5 * future_gain / S)
side(T) = s_con if T.window.window == "contender" else s_reb if "rebuilder" else (s_con + s_reb) / 2
outlook = (side(V) + side(P)) / 2
```

**Rank score.**
```
if request.board is None: rank = 0.5
else:
    contrib(a) = personal(a) - market(a) for a in receive; market(a) - personal(a) for a in give
    gap_rel = Σ contrib / ((give_market + receive_market) / 2)
    rank = clamp01(0.5 + gap_rel / (2 * RANK_GAP_SATURATION))          # +30% relative gap -> 1.0
    top = the player asset with the largest contrib > 0 (ties: id asc), else None
    rank_delta(top) = consensus_rank[top] - personal_rank[top]        # + means viewer ranks him higher
```

**Priority.**
```
priority = (w_value*value + w_outlook*outlook + w_rank*rank) / (w_value + w_outlook + w_rank)
```

### 5.4 `ScoredTrade.detail` keys

These are fixed. The bench, the evidence and the reasons read them.

```python
{
  "value":   {"delta_ln": float, "s_delta": float, "best_in_id": str, "best_in_market": float,
              "best_in_starter": bool, "s_piece": float},
  "outlook": {"scale": float,
              "viewer":  {"window": str, "lineup_gain": float, "future_gain": float, "score": float},
              "partner": {"window": str, "lineup_gain": float, "future_gain": float, "score": float}},
  "rank":    {"has_board": bool, "gap_rel": float, "top_asset": str | None,
              "top_side": "give" | "receive" | None, "rank_delta": int | None},
}
```

Floats are rounded to 4 decimals.

### 5.5 Card reasons: `card_reasons`

The order is fixed: value, then outlook, then the throw-in line, then rank. The rank and piece lines only fill a free slot. There are at most 3 lines.

| Slot | Condition | Text |
|---|---|---|
| value (always) | `pct = round(100*(receive/give − 1))`; abs(pct) ≤ 3 | `"Fair on value"` |
| | pct > 3 | `f"You get {pct}% more market value"` |
| | pct < −3 | `f"You pay {-pct}% over market"` |
| outlook | partner side score ≥ 0.60: rebuilder / contender / middle | `"Fits their rebuild"` / `"Helps their title push"` / `"Works for their roster"` |
| | else viewer side score ≥ 0.60: contender / rebuilder / middle | `"Upgrades your starting lineup"` / `"Adds youth for your rebuild"` / `"Works for your roster"` |
| throw-in | `trade.throwin` set and received by the viewer (value from `request.board`) | `f"Throw-in: you rank {name} at {value/market:.1f}× market"`, e.g. `"Throw-in: you rank PT at 2.3× market"` |
| | `trade.throwin` set and received by the partner (value from `snapshot.partner_boards[partner]`) | `f"Throw-in: they rank {name} at {value/market:.1f}× market"` |
| | either, with no board value or `market ≤ 0` (defensive; `throwin_ok` rules both out) | `f"Throw-in: {name}, valued well above market by you"` / `"… by them"` |
| rank (fill) | has board, top asset set and not the throw-in (its line already explains that player), `top_side=="receive"` and `rank_delta ≥ 5` | `f"You rank {name} {rank_delta} spots above market"` |
| | `top_side=="give"` and `rank_delta ≤ −5` | `f"You rank {name} {-rank_delta} spots below market"` |
| piece (fill) | `best_in_starter` | `f"{name} would start for you"` |
| | else market(best_in) ≥ first_round_value | `"Brings back 1st-round value"` |

`name` is `snapshot.assets[id].name`.

### 5.6 `backend/value_core/deck.py`

```python
PARTNER_PENALTY_FACTOR = 0.5
PICK_IDEA = "PICK"


def idea_key(trade: FairTrade, snapshot: LeagueSnapshot) -> tuple[str, str, str]:
    """(partner, give headliner, receive headliner), picks collapsed to "PICK". Trades that
    share it differ only in minor pieces or pick years: the same trade idea."""

def acquisition_key(trade: FairTrade, snapshot: LeagueSnapshot) -> tuple[str, str]:
    """(partner, acquired headliner), picks collapsed to "PICK"."""

def partner_cap(n_partners: int) -> int:
    """Most cards one partner may take in the first TOP_WINDOW: a fair share plus one,
    never below 2. 11 partners -> 4; 5 -> 7; 1 -> 31 (no effect)."""
    return max(2, ceil(TOP_WINDOW / max(1, n_partners)) + 1)

def assemble_deck(scored: Sequence[ScoredTrade], cfg: RankConfig, *,
                  snapshot: LeagueSnapshot, request: Request) -> list[DeckEntry]:
    """Order the scored trades, one card per trade idea (lower-priority versions of an idea
    are dropped). Greedy by (acquisition round, effective priority):
        effective = priority - cfg.repeat_penalty * max(shown[a] for a in give+receive)
                             - PARTNER_PENALTY_FACTOR * cfg.repeat_penalty * shown_partner[partner]
    While position < TOP_WINDOW a card is deferred if any of its assets has
    shown[a] >= cfg.player_cap or its partner has partner_cap(n) cards. Deferred cards
    re-enter at position TOP_WINDOW, or earlier if nothing eligible remains (caps relaxed for
    that position only). DeckEntry.reasons = ranking.card_reasons(...)."""
```

A headliner is the first asset on a side (each side is sorted by market, descending). An asset whose `kind` is `"pick"` counts as `PICK_IDEA` in both keys, whatever its year or round.

**Variety rules (operator request, 2026-09-30:** *"I don't want to see the same iteration of a trade with a trade partner with only minor pieces swapped out... or the same trade partner with different years' draft picks"*). Three rules, applied before and during the greedy order:
1. **One card per trade idea.** Trades that share an `idea_key` are one idea. Only the highest-priority version is kept (ties broken by trade key); the other versions are dropped from the deck. This is the only place the ranking layer removes a trade.
2. **Acquisitions in rounds.** A card's round is how many earlier cards share its `acquisition_key`. The greedy key is (round, −effective, trade key), so every acquisition is shown once before any is shown a second time.
3. **Caps in the first 30.** A partner may take at most `partner_cap(n)` of the first `TOP_WINDOW` cards, where `n` is the number of partners among the kept ideas, and no asset may appear in more than `cfg.player_cap` of them. A card that breaks either cap is deferred. The caps relax for one position only when nothing eligible is left.

The repeat penalty (`vc_repeat_penalty`, partner at half rate) is unchanged and orders cards within a round.

**Algorithm: lazy greedy.** It is exact because a card's (round, −effective) key only grows as cards are shown: the round counters and the `shown` counters only rise.
```
ideas = best version per idea_key                 # by (-priority, key); the rest are dropped
entry(i) = (shown_acq[acq(i)], -eff(i), key(i), i)  # key = (partner, give, receive) for determinism
heap = [(0, -priority, key, i)]
deferred = []
while heap or deferred:
    if not heap:                                  # only capped cards left before position 30
        heap = [entry(i) for i in deferred]; heapify; deferred = []; relax_once = True
    i = heappop(heap)[3]
    pos = len(out)
    if pos < TOP_WINDOW and not relax_once and capped(i):   # partner cap or any asset cap
        deferred.append(i); continue
    fresh = entry(i)
    if heap and fresh[:3] > heap[0][:3]:          # stale bound: re-queue with the fresh key
        heappush(heap, fresh); continue
    out.append(DeckEntry(pos, ideas[i], round(-fresh[1], 6), card_reasons(...)))
    shown[a] += 1 for a in assets(i); shown_partner[partner(i)] += 1
    shown_acq[acq(i)] += 1; relax_once = False
    if len(out) == TOP_WINDOW and deferred:
        for j in deferred: heappush(heap, entry(j)); deferred = []
```

**Complexity.** O(P log P · r), where r is the average number of re-queues, which is small because penalties are bounded. A property test compares the result against an O(P²) naive greedy that implements all three rules (WP2).

---

## 6. Pipeline: `backend/value_core/pipeline.py`

```python
def run(snapshot: LeagueSnapshot, request: Request, core_cfg: CoreConfig, rank_cfg: RankConfig, *,
        time_budget_s: float = 8.0) -> PipelineResult:      # literal; equals core.TIME_BUDGET_S (core is imported lazily)
    """core.find_fair_trades -> ranking.score_trades -> deck.assemble_deck.
    `from . import core, ranking, deck` happens INSIDE this function (never at module
    level). elapsed_ms is wall time for the three steps. No logging, no I/O, no
    exception handling: errors propagate to the caller."""
```

---

## 7. Adapter: `backend/value_core/adapter.py`

### 7.1 API

```python
DEFAULT_LINEUP = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX")   # mirrors server._PLATFORM_DEFAULT_LINEUP (server.py:18023)


def core_config_from(cfg: Mapping[str, float]) -> CoreConfig: ...        # §3 keys + clamps; missing -> default
def rank_config_from(cfg: Mapping[str, float]) -> RankConfig: ...        # all-zero weights -> (1, 1, 1)
def standings_weight_from(cfg: Mapping[str, float]) -> float: ...        # vc_standings_weight, clamp [0, 1]
def default_lineup_slots(scoring_format: str) -> tuple[str, ...]:
    """DEFAULT_LINEUP + ("SUPER_FLEX",) when scoring_format == "sf_tep"."""
def tier_values(scoring_format: str) -> tuple[float, float]:
    """(first_round_value, elite_value) = elo_to_value of the lower Elo bound of tiers
    first_1 and firsts_4plus from RankingService.tier_bands_for(None, scoring_format)
    (ranking_service.py:1768; today 1580 -> ~1492, 1927 -> ~8457)."""
def build_snapshot(*, league_id: str, scoring_format: str, viewer_team_id: str, viewer_name: str,
                   viewer_roster: Sequence[str], opponents: Sequence[object],
                   players: Mapping[str, object], seed_elo: Mapping[str, float],
                   lineup_slots: Sequence[str] | None, max_players: int | None,
                   windows: Mapping[str, TeamWindow],
                   partner_boards: Mapping[str, Board] | None = None) -> LeagueSnapshot: ...
def partner_board_from(*, elo_ratings: Mapping[str, float] | None, seed_elo: Mapping[str, float],
                       comparison_counts: Mapping[str, int] | None = None,
                       confidence_source: str | None = None,
                       confidence_weights: Mapping[str, float] | None = None,
                       confidence_sources: Mapping[str, str] | None = None) -> Board | None: ...
def build_request(*, snapshot: LeagueSnapshot, user_elo: Mapping[str, float] | None,
                  seed_elo: Mapping[str, float], confidence: Mapping[str, int] | None,
                  placements: Mapping[str, tuple[float, float]] | None,
                  untouchable_ids: Iterable[str], not_interested_ids: Iterable[str],
                  pinned_give: Iterable[str], pinned_give_mode: str,
                  pinned_receive: Iterable[str], partner_team_id: str | None,
                  fairness_threshold: float | None) -> Request: ...
def evidence(entry: DeckEntry, snapshot: LeagueSnapshot, request: Request,
             core_cfg: CoreConfig, rank_cfg: RankConfig, *, budget_exhausted: bool) -> dict: ...
def to_trade_cards(result: PipelineResult, snapshot: LeagueSnapshot, request: Request, *,
                   league_id: str, proposing_user_id: str, core_cfg: CoreConfig,
                   rank_cfg: RankConfig) -> tuple[list[TradeCard], dict[int, dict]]: ...
```

### 7.2 Behavior

**`build_snapshot`.** `opponents` are `LeagueMember`-like objects with `.user_id`, `.username` and `.roster`. The viewer's team is built from `viewer_team_id`, `viewer_name` and `viewer_roster`. For every roster id `pid`:
- `p = players.get(pid)`. If `p is None`, count it in `other_players`.
- If `p.position == "PICK"`: `Asset(kind="pick", position="PICK", age=None, market=elo_to_value(seed_elo[pid]) if pid in seed_elo else 0.0)`.
- If `p.position in CORE_POSITIONS`: `Asset(kind="player", age=float(p.age) if p.age else None, market=elo_to_value(seed_elo[pid]) if pid in seed_elo else 0.0)`.
- Any other position counts in `other_players`.
- `Asset.name = p.name`.
- An id already seen on another team keeps its first owner, and `adapter` logs a warning. This is the co-owner/duplicate guard.

The rest of the snapshot:
- `windows.get(team_id, DEFAULT_WINDOW)`;
- `rules = RosterRules(tuple(lineup_slots or default_lineup_slots(fmt)), max_players)`;
- `first_round_value, elite_value = tier_values(fmt)`;
- `partner_boards`: each given board is kept only for a known team that is not the viewer, cut to asset ids in the snapshot (`comparisons` default 0 for a kept id); a board left with no values is dropped. Omitted → `{}`.

**`partner_board_from`.** A leaguemate's **published** board, priced for throw-ins (§4.3). It returns `None` for an empty `elo_ratings`. Otherwise it shrinks with the personal-market policy's symmetric rule, `trade_policy.shrink_board(elo, seed_elo, trade_policy.confidence_map(comparison_counts, source=confidence_source, weights=confidence_weights, sources=confidence_sources))`, and returns `Board(values={a: elo_to_value(e)}, comparisons={a: comparison_counts.get(a, 0)})`. A player with no evidence prices at consensus, so a thin board can never qualify a throw-in. The caller passes only members whose Elo came from real `member_rankings` rows (server `has_rankings`, §9.1); the bench passes every other seat's frozen board (§8.2).

**The market is raw `elo_to_value(seed)`**, with no age preference. It is the same number the calculator shows (`server.py:12726-12729`), and it means age is never double-counted (operator interview, 2026-07-17).

**`build_request`.**
- **Board.** If `user_elo` is empty or None, `board = None`. Otherwise:
  - `shrunk = trade_service._shrink_user_elo(dict(user_elo), dict(seed_elo), dict(confidence) if confidence else None, dict(placements) if placements else None)` (`trade_service.py:1878`, w = n/(n+4));
  - `Board(values={a: elo_to_value(shrunk[a]) for a in snapshot.assets if a in shrunk}, comparisons={a: int((confidence or {}).get(a, 0)) for a in values})`.
- **Id sets** are intersected with `snapshot.assets`.
- `pinned_give_mode` is `"all"` iff the input is `"all"`, else `"any"`.
- **Partner.** `partner_team_id` passes through unchanged. An unknown partner gives an empty pool; the core handles it.

**`to_trade_cards`.** For each `entry` in `result.entries`, with `t = entry.scored.trade`:
```python
card = TradeCard(
    trade_id="vc_" + uuid.uuid4().hex, league_id=league_id, proposing_user_id=proposing_user_id,
    target_user_id=t.partner_team_id, target_username=snapshot.teams[t.partner_team_id].name,
    give_player_ids=list(t.give), receive_player_ids=list(t.receive),
    mismatch_score=round(entry.scored.scores.rank, 4),
    fairness_score=round(min(r, 1 / r), 4) where r = t.receive_market / t.give_market,
    composite_score=round(entry.scored.scores.priority, 6),
    basis="consensus", reasons=list(entry.reasons),
    give_value=round(t.give_market, 1), receive_value=round(t.receive_market, 1))
card.preserve_server_order = True           # disables client re-rank (TradesScreen.tsx:2778, :4084)
```
It returns the cards in `entries` order, plus `{id(card): evidence(entry, ...)}`. The fields `lane`, `narrative`, `match_context`, `tier` and `rationale` are left None, so `trade_card_to_dict` omits them and the lane chips stay hidden (`TradesScreen.tsx:7332`).

### 7.3 Evidence schema (`deck_impressions.valuation_json`)

```json
{
  "schema_version": 1,
  "generator": "value_core",
  "generator_version": "value-core-1",
  "deck_position": 4,
  "weights": {"value": 1.0, "outlook": 1.0, "rank": 1.0, "repeat_penalty": 0.15, "player_cap": 3},
  "scores": {"value": 0.6123, "outlook": 0.7021, "rank": 0.5, "priority": 0.6048},
  "effective": 0.4548,
  "market": {"give": 5120.0, "receive": 5480.0, "adjusted_ratio": 1.0703,
             "premium": 0.0, "premium_side": null},
  "core": {"band": 0.20, "gain_band": 0.10, "ratio_floor": 0.8333, "ratio_ceiling": 1.10,
           "stud_premium": 0.15, "untouchable_min_ratio": 1.08, "uses_untouchable": false,
           "drops_needed": [0, 1], "budget_exhausted": false, "throwin_min_ratio": 2.0,
           "throwin": null},
  "windows": {"viewer":  {"window": "contender", "score": 0.21, "source": "inferred",
                          "pf_index": 0.33, "standings_weight": 0.1125},
              "partner": {"window": "rebuilder", "score": -0.30, "source": "declared",
                          "pf_index": -1.0, "standings_weight": 0.1125}},
  "detail": {"value": {}, "outlook": {}, "rank": {}},
  "assets": [{"id": "4046", "side": "give", "market": 5120.0, "personal": 4800.0, "n": 12},
             {"id": "L_2027_1_4", "side": "receive", "market": 2117.0, "personal": null, "n": null}]
}
```

- `detail` is the `ScoredTrade.detail` of §5.4, verbatim.
- `personal` and `n` are null when there is no board, or when the asset has no board entry.
- `band` and `gain_band` are the effective bands, after the client's fairness preference. `ratio_floor` = 1/(1+band) and `ratio_ceiling` = 1+gain_band.
- `throwin` is null when the trade has none. Otherwise it is `{"id", "recipient", "market", "recipient_value"}`, e.g. `{"id": "7611", "recipient": "viewer", "market": 300.0, "recipient_value": 700.0}`: `recipient` is `"viewer"` (the viewer receives it; value from `request.board`) or `"partner"` (value from the partner's published board), and `recipient_value` is that board's value for it.
- The JSON is written with `json.dumps(..., sort_keys=True)`.
- The schema version bumps on any key change. (`core.gain_band`, `core.throwin_min_ratio` and `core.throwin` joined v1 on 2026-10-01, before the branch had served any value-core row, so v1 was not bumped.)

---

## 8. Eval bench

### 8.1 `backend/eval/value_core_bench.py`: freeze

```python
SCHEMA = "value-core-bench-1"

def freeze(*, secrets: Path, league_ids: Sequence[str], output: Path, today: date | None = None,
           fetch_json: Callable[[str], object] | None = None) -> dict:
    """Write ONE private frozen file (os.open O_CREAT|O_EXCL, mode 0600; refuses an existing
    path) holding every requested league. Returns an aggregate summary with no user ids:
    {leagues, teams, assets, boards, standings_leagues}. Network: prod Postgres read-only +
    Sleeper public GET via fetch_json (default urllib, 20 s timeout)."""
```

**Structure.** Split `freeze` into a thin I/O shell and a pure transform, so the transform is testable offline:
```python
def league_record(*, league_row: Mapping, members: Sequence[Mapping], picks: Sequence[Mapping],
                  rankings: Sequence[Mapping], players: Mapping[str, Mapping],
                  consensus_elo: Mapping[str, float], declared: Mapping[str, str | None],
                  meta: Mapping | None, state: object | None) -> dict
    # pure: rows in, one frozen league record (below) out; meta/state None for non-Sleeper
def assert_read_only(connection) -> None
    # raises ValueError unless `SHOW transaction_read_only` returns "on"
```

**Connection.** `prod_analytics.SECRETS = secrets`, then `engine = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 15000)` (`backend/tools/prod_analytics.py:39`, `:57`). Assert `SHOW transaction_read_only` is `on` before any read, as `capture_owner_benchmark.capture` does (`capture_owner_benchmark.py:61-95`).

**Reads per league.** All are parameterized and read-only.
- `leagues` (PK `sleeper_league_id`): `name`, `platform`, `default_scoring`. The format is `default_scoring or "1qb_ppr"`.
- `league_members`: `user_id`, `username`, `display_name`, `roster_data` (a JSON player-id list).
- `draft_picks` with `source = 'platform'`: `pick_id`, `season`, `round`, `owner_user_id`, `pick_value`, `pool_value`. The top 6 per owner by `pool_value` are kept, to mirror `picks_pool_cap` (`database.py:2927`).
- `member_rankings` for the format: `user_id`, `player_id`, `elo`, `comparison_count`. Rows join to teams where `user_id` equals the `league_members.user_id`, the same equality `_run_trade_job` uses (`server.py:7509`).
- `players` for the roster ids: `full_name`, `position`, `age`, `search_rank`.
- `player_value_history` for the format at the latest `snapshot_date ≤ today`: `player_id`, `consensus_elo`.

**Sleeper leagues.** `fetch_json(f"https://api.sleeper.app/v1/league/{id}")` supplies `roster_positions` and `settings.reserve_slots`/`taxi_slots`. `max_players` is `len(roster_positions) + reserve + taxi`, mirroring `server._sleeper_roster_limit` (`server.py:29701`). Standings and `completed_weeks` come from `backend.outlook.league_state.SleeperLeagueState(fetch=fetch_json).load(league_id)` (`league_state.py:142-177`), the reused parser.

**Non-Sleeper leagues.** `lineup_slots = adapter.default_lineup_slots(fmt)`, `max_players = None`, standings empty.

**Frozen league record.**
```json
{"league_id": "...", "name": "...", "platform": "sleeper", "scoring_format": "sf_tep",
 "lineup_slots": ["QB","RB","RB","WR","WR","TE","FLEX","SUPER_FLEX"], "max_players": 30,
 "completed_weeks": 4, "standings": {"<team_id>": {"wins":3,"losses":1,"ties":0,"points_for":512.4}},
 "assets": {"<id>": {"kind":"player","position":"WR","name":"...","age":24.0,"market":4012.3,
                     "search_rank":31,"pick_value":null}},
 "teams": [{"team_id":"...","name":"...","asset_ids":["..."],"other_players":2,
            "declared_outlook":null,"pick_share":0.083}],
 "boards": {"<team_id>": {"elo": {"<id>": 1712.0}, "comparisons": {"<id>": 9}}},
 "seed_elo": {"<id>": 1650.0}}
```
- `market` is `elo_to_value(consensus_elo)`, and for picks `pool_value`.
- `seed_elo` is kept so a board can be shrunk at run time.
- `declared_outlook` comes from `league_preferences.team_outlook` where present. It is null otherwise. That is one more read-only query per league: `SELECT user_id, team_outlook FROM league_preferences WHERE league_id = :lid`.

**`synthetic_league(seed=7, n_teams=12, scoring_format="1qb_ppr") -> dict`** returns a frozen-format league: `random.Random(seed)`, 22 core players and 4 picks per team, ln-normal markets (median 1200, σ 1.0) clamped to [100, 9500], ages 21–33, two boards, and PF standings at week 4. It is used by the tests and by the flag-on smoke run.

### 8.2 `value_core_bench.py`: run and guardrails

```python
TARGETS = {"insult_loss": 0.20, "insult_rate_max": 0.03, "real_piece_min": 0.70,
           "median_given_min": -0.10, "max_appearances": 3}

def load_frozen(path: Path) -> dict
def snapshot_for_seat(league: Mapping, seat_team_id: str, *, standings_weight: float
                      ) -> tuple[LeagueSnapshot, Board | None]:
    """Build windows (windows.infer_windows with SimpleNamespace players from assets)
    and the snapshot from frozen data; board = shrink(boards[seat]) via
    trade_service._shrink_user_elo(elo, seed_elo, comparisons, None) -> elo_to_value.
    Every OTHER seat's frozen board becomes snapshot.partner_boards[seat] through
    adapter.partner_board_from(..., confidence_source="votes"), the server's partner
    shrink, so throw-ins to partners are benched the way they are served."""
def guardrails(entries: Sequence[DeckEntry], snapshot: LeagueSnapshot, *, top: int = 30) -> dict
def run(frozen: Mapping, *, variants: Mapping[str, Mapping], seats: str = "all",
        engine: Callable[[LeagueSnapshot, Request, CoreConfig, RankConfig], PipelineResult] | None = None
        ) -> dict
def main(argv: Sequence[str] | None = None) -> int
```

**`guardrails` on the first `top` entries.** Let `g` be the give market, `r` the receive market and `b` the best incoming asset.
- `insult_rate` = the share of entries with `(r − g)/r > 0.20`.
- `real_piece_back_share` = the share with `detail.value.best_in_starter` or `best_in_market ≥ snapshot.first_round_value`.
- `median_value_given` = the median of `(r − g)/g`.
- `max_acquired_appearances` is taken from a Counter over the **acquired** (received) asset ids; `most_acquired_asset` is reported alongside it. This is the appearances guardrail (≤ `max_appearances`, 3).
- `max_asset_appearances` counts every asset id, both sides, with `most_repeated_asset` alongside. It is reported, not a guardrail: giving the same asset in several cards is expected.
- `near_duplicates` = the cards that repeat an earlier card's trade idea (§5.6 `idea_key`): the sum over ideas of (count − 1). A guardrail: it must be 0.
- `acquisition_repeats` = the same sum over `acquisition_key`. Reported, not a guardrail.
- `max_partner_cards` = the most cards any one partner has. Reported.
- `partners` = the number of distinct partners.
- `cards` = the entries evaluated.
- `pass` = `{insult, real_piece, median_given, appearances, near_duplicates}` booleans against `TARGETS` (`near_duplicates` passes at exactly 0).

**`run`.**
- For each variant, the overrides are `{"core": {...}, "rank": {...}, "standings_weight": x}` on top of the defaults.
- For each league and each seat (`"all"` is every team; `"boarded"` is only seats with a board):
  1. Build the snapshot and a `Request(viewer, board)`.
  2. Run `engine(...)`, which defaults to `pipeline.run`.
  3. Compute the guardrails.
- The returned summary has three parts:
  - **Pooled per variant:** the pooled rates over all first-30 cards, plus the worst seat's numbers: `worst_seat_acquired_appearances`, `worst_seat_near_duplicates` and `worst_seat_acquisition_repeats` (each the maximum over seats with at least 1 card).
  - **`verdict`:** `PASS` iff the pooled insult rate < 0.03, the pooled real-piece share ≥ 0.70, the pooled median ≥ −0.10, and every seat with at least 1 card has acquired-asset appearances ≤ 3 and 0 near-duplicates.
  - **Per seat:** league name, team name, pass flags and core diagnostics.

**CLI.**
```
python -m backend.eval.value_core_bench freeze --secrets secrets.local.env --league ID [--league ID ...] --output PRIVATE.json
python -m backend.eval.value_core_bench run --frozen PRIVATE.json --output NEW_DIR [--variant NAME=overrides.json ...] [--seats all|boarded]
```
`run` writes into `NEW_DIR`, which must not already exist, and writes every file with mode 0600:
- `results.json`;
- `cards-<variant>.json`, which is a blind-grade card set (§8.4) of the first 30 cards per seat;
- a markdown table printed to stdout: per variant, the card count, the three pooled rates, the worst-seat acquired-asset appearances, near-duplicates and repeat acquisitions, and the verdict.

### 8.3 Real-trade recall: `backend/eval/value_core_recall.py`

```python
@dataclass(frozen=True)
class RecallCase:
    case_id: str                   # f"{label}-{season}-w{leg}-{transaction_id}"
    label: str                     # "ffv3" | "lakeview"
    season: int
    leg: int
    scoring_format: str
    lineup_slots: tuple[str, ...]
    assets: Mapping[str, Asset]
    teams: Mapping[str, tuple[str, ...]]   # roster_id(str) -> pre-trade asset ids (week leg-1)
    a_team: str
    b_team: str
    a_gives: tuple[str, ...]
    b_gives: tuple[str, ...]

def cases_from_fixtures(fixture_root: Path, *, only: Iterable[tuple[str, int]] | None = None
                        ) -> tuple[list[RecallCase], dict[str, int]]
    # only: e.g. {("ffv3", 2024)}; None = every (label, season) present in both fixture dirs
def is_close(trade: FairTrade, real_give: Sequence[str], real_receive: Sequence[str],
             assets: Mapping[str, Asset]) -> bool
    # headliner = the real trade's max-market asset (ties: id asc)
def band_calibration(log_ratios: Sequence[float]) -> dict
def run_recall(cases: Sequence[RecallCase], core_cfg: CoreConfig, rank_cfg: RankConfig, *,
               top: int = 10) -> dict
def main(argv: Sequence[str] | None = None) -> int
```

**`cases_from_fixtures`** takes each `(label, season)` present in both `outlook-hypotheses/{label}-{season}.json` (trades by leg) and `outlook-calibration/{label}-{season}.json` (league meta and weekly `matchups`).
- **Skip counts** by reason: `offseason_leg` (leg < 2), `multi_team`, `roster_mismatch`, `no_values`, `unpriced_asset`.
- **Pre-trade rosters.** The rosters are those of `matchups[str(leg−1)]`, by `roster_id`. Every player in a roster's `drops` must be on that roster, otherwise the case is skipped as `roster_mismatch`.
- **Values.**
  - The key is the latest `dp-values-history/index.json` key with date ≤ the trade's `status_updated` date.
  - `values_as_of(key, scoring="2qb" if sf_tep else "1qb")` is called offline (`dp_values_history.py:327`).
  - The market is `elo_to_value(seed_elo_for_value(v))` (`data_loader.py:103`).
- **Positions** come from `outlook-hypotheses/player-positions.json` ∪ `outlook-calibration/players_team_pos.json`.
- **Ages** are None. The fixtures carry no ages: this is a documented limitation, and it means youth weights fall to 0.5.
- **Picks.** Only the traded picks are present, as assets `hist_{season}_{round}_{roster_id}` on the sending roster, with market `pick_pool_value(round, int(season) − trade_season, fmt)` (`pick_values.py:264`). Other held picks are absent (a limitation).
- **Lineup slots** come from the calibration fixture's `league.roster_positions`. The core enforces only the `LINEUP_SLOT_ELIGIBILITY` keys; IDP, K and BN are ignored. `max_players` is None, so the size rule is skipped.
- **Format:** `sf_tep` if the league has a `SUPER_FLEX` slot, 2 or more `QB` slots, or `scoring_settings.bonus_rec_te > 0`, mirroring `server._detect_scoring_format_from_meta` (`server.py:750`). Otherwise `1qb_ppr`.
- **Expected yield:** 77 in-season two-team trades (counted on `3bb981ed`: FFV3 2022–2025 has 7/20/9/16, Lakeview 2024–2025 has 16/9), minus skips.

**`run_recall`.** For each case and both orientations (A as viewer, B as viewer):
1. Snapshot with all teams from that week, **every window = `DEFAULT_WINDOW`**, `board = None`, `partner_team_id` = the other side. The fixtures carry no ages or search ranks, so outlook is neutral here: recall measures the core plus the value score, and the ranking is neutral on outlook and rank.
2. Run `pipeline.run`, then check the top `top` entries:
   - **`exact`**: the same give and receive sets.
   - **`close`**: `is_close` is true, meaning the card has the real trade's headliner on the same viewer side **and** at least 50% of the real trade's asset ids across both sides.
3. Also call `core.evaluate_trade` on the real trade. Record `verdict.ok`, the failing reason, and `ln(adjusted_ratio)` when priced.

It returns:
```
{cases, orientations, exact_at_k, close_at_k,
 in_pool_rate,                      # share of orientations whose exact real trade is anywhere in the fair pool
 reject_reasons{},                  # evaluate_trade reasons for real trades that failed
 band: band_calibration(|ln adjusted_ratio| once per CASE, orientation A),
 per_case: [{case_id, orientation, rank_exact, rank_close, ok, reason, log_ratio}]}
```

**`band_calibration`** returns `{n, p50, p80, p90, recommended_band}`. Percentiles use the nearest rank on the sorted values: `v[ceil(q·n) − 1]`. The recommended band is `round(exp(p80) − 1, 2)`, which is the band that would admit 80% of the real trades. Example: `[0.0, 0.05, 0.1, 0.2, 0.3]` gives p50 = 0.1, p80 = 0.2, p90 = 0.3 and a recommended band of 0.22.

**CLI.** `python -m backend.eval.value_core_recall --fixtures backend/tests/fixtures --output NEW_DIR [--variant NAME=overrides.json]`.

### 8.4 `backend/eval/blind_grade.py`

```python
TAGS = ("same_guy_again", "too_small", "never_accept", "wrong_my_window",
        "wrong_their_window", "junk_filler", "overpay")

# CardSet JSON: {"variant": str, "source": "value_core_bench" | "served",
#                "cards": [{"league": str, "seat": str, "partner": str,
#                           "give": [{"id","name","position","market"}],
#                           "receive": [{"id","name","position","market"}],
#                           "reasons": [str]}]}

def export(card_sets: Sequence[Mapping], *, per_variant: int = 40, seed: int = 7,
           output_dir: Path, show_reasons: bool = False) -> dict
def import_grades(sheet: Path, key: Path) -> dict
def served_card_set(*, secrets: Path, league_ids: Sequence[str], user_id: str,
                    top: int = 30, variant: str = "incumbent") -> dict
def main(argv: Sequence[str] | None = None) -> int
```

**`export`.**
- **Sampling.** Sample `per_variant` cards uniformly without replacement from each set, with `random.Random(seed)`. A set with fewer cards contributes all of them.
- **Dedupe.** Identical trades across variants are merged into one row: the key is `(league, seat, partner, sorted give ids, sorted receive ids)`.
- **Shuffle.** All rows are shuffled with the same RNG.
- **Card ids** are `c01`, `c02`, and so on, carrying no source information.
- **Files written** (`output_dir` must not exist; mode 0600):
  - `grade-sheet.csv`, with columns `card_id, league, you_give, you_get, give_value, get_value, reasons, grade, tags, note`.
    - `you_give`/`you_get` are `"Name (POS) · Name (POS)"`.
    - `reasons` is blank unless `show_reasons`: engine-specific phrasing would reveal the source.
    - `grade`, `tags` and `note` are empty.
  - `key.private.json`: `{card_id: {"variants": [..], "seat", "league"}}`.
- It returns `{rows, per_variant: {name: n}}`.

**`import_grades`.**
- Validates that each `grade` is an integer in 1–5 (blank means ungraded and is skipped).
- `tags` is `;`-separated and each tag must be in `TAGS`. Otherwise it raises `ValueError` naming the card and the bad value.
- It returns per variant `{n, mean, share_ge_4, tag_counts}` plus `overall`, and writes `summary.json` next to the sheet. The target is mean ≥ 4.0 (PRD §6).

**`served_card_set`** reads prod through the read-only connection (§8.1). For each league:
- the latest `deck_job_id` for `(user_id, league_id)` in `deck_impressions`;
- its rows with `card_index < top` and `COALESCE(is_ghost, 0) = 0`, ordered by `card_index`;
- `assets_json` for the give/receive ids, and per-asset `market` from `valuation_json.assets[*].market` where present (owner and bilateral rows), else null;
- names and positions from `players`.

This lets the operator grade the incumbent alongside the value-core variants.

**CLI.**
```
python -m backend.eval.blind_grade served --secrets secrets.local.env --user ID --league ID [...] --output served.json
python -m backend.eval.blind_grade export --cards A.json --cards B.json [...] --per-variant 40 --seed 7 --output NEW_DIR
python -m backend.eval.blind_grade import --sheet NEW_DIR/grade-sheet.csv --key NEW_DIR/key.private.json
```

---

## 9. Integration edits in existing files

### 9.1 `backend/server.py`

**(a) New helpers.** Insert immediately **before** `def _run_trade_job(` (`server.py:7427`), after `_capture_trade_execution` (`:7397`).

```python
# ── Value-core engine (docs/plans/value-core-engine/) ────────────────────────
def _value_core_enabled() -> bool:
    return bool(getattr(FLAGS, "trade_value_core", False))


def _value_core_live(*, league_id: str, user_id: str, league_user_id: str | None,
                     trade_intent: str | None, preparation: bool) -> bool:
    """Does THIS job run the value core? Flag off => False before any other read."""
    if not _value_core_enabled():
        return False
    if league_id == "league_demo" or trade_intent or preparation:
        return False
    if float(_trade_service_mod._cfg.get("vc_testers_only", 1.0)) >= 1.0:
        allow = _load_tester_allowlist()          # experiments.load_tester_allowlist (server.py:26591)
        return str(user_id) in allow or (league_user_id is not None and str(league_user_id) in allow)
    return True


def _value_core_standings(league_id: str, platform: str | None) -> tuple[dict, int]:
    """({league_user_id: Standing}, completed_weeks). Sleeper only; fail-soft to ({}, 0)."""
    from .value_core.types import Standing
    if (platform or "sleeper") != "sleeper":
        return {}, 0
    try:
        from . import outlook as outlook_pkg
        state = outlook_pkg.build_league_state(league_id, platform="sleeper",
                                               fetch=_outlook_sleeper_fetch())
    except Exception as err:
        log.warning("value-core: standings unavailable league=%s: %s", league_id, err)
        return {}, 0
    return ({str(t.user_id): Standing(int(t.wins), int(t.losses), int(t.ties), float(t.points_for))
             for t in state.teams if t.user_id}, int(state.completed_weeks or 0))


def _run_value_core_job(*, job_id, ctx, service, trade_service, g_user_id, g_league, g_user_roster,
                        players_dict, seed_map, elo_map_rt, confidence_counts, placement_bands,
                        untouchable_ids, not_interested_ids, explicit_outlook, opponent_outlooks,
                        real_user_ids, outlook_value, pinned_give, pinned_give_mode,
                        pinned_receive, opponent_user_id, fairness_threshold, job_draft_picks):
    """Serve one value-core deck and finish the job; return True. If building the deck
    fails before anything is served (everything through adapter.to_trade_cards sits in
    one try), log it and return False: _run_trade_job then finishes the same job with the
    legacy engine (PRD Q1, operator 2026-10-01)."""
    from .value_core import adapter as vc_adapter, pipeline as vc_pipeline, windows as vc_windows
    started = time.monotonic()
    league_id, fmt, viewer = ctx.league_id, ctx.scoring_format, str(ctx.league_user_id)
    cfg = dict(_trade_service_mod._cfg)
    core_cfg, rank_cfg = vc_adapter.core_config_from(cfg), vc_adapter.rank_config_from(cfg)
    opponents = [m for m in g_league.members if m.user_id not in {g_user_id, ctx.league_user_id}]
    platform = getattr(g_league, "platform", None)
    standings, completed_weeks = _value_core_standings(league_id, platform)
    try:
        slots = _league_lineup_slots(league_id)
    except Exception:
        slots = None
    try:
        max_players = _sleeper_roster_limit(league_id) if (platform or "sleeper") == "sleeper" else None
    except Exception:
        max_players = None
    totals, grand = {}, 0.0
    for pk in job_draft_picks():
        owner, pv = pk.get("owner_user_id"), pk.get("pick_value") or 0.0
        if owner:
            totals[str(owner)] = totals.get(str(owner), 0.0) + pv
        grand += pv
    pick_shares = {u: t / grand for u, t in totals.items()} if grand > 0 else {}
    rosters = {viewer: list(g_user_roster), **{str(m.user_id): list(m.roster) for m in opponents}}
    declared = {viewer: explicit_outlook, **{str(k): v for k, v in (opponent_outlooks or {}).items()}}
    windows = vc_windows.infer_windows(
        team_rosters=rosters, players=players_dict, pick_shares=pick_shares, standings=standings,
        completed_weeks=completed_weeks, declared=declared,
        standings_weight=vc_adapter.standings_weight_from(cfg))
    viewer_name = next((m.username for m in g_league.members if m.user_id == ctx.league_user_id), "You")
    # Throw-ins to a partner need that partner's real published board (has_rankings is set
    # only for members whose Elo came from member_rankings rows; others carry seeded noise).
    partner_boards = {}
    for m in opponents:
        if getattr(m, "has_rankings", False) and m.elo_ratings:
            pb = vc_adapter.partner_board_from(
                elo_ratings=m.elo_ratings, seed_elo=seed_map,
                comparison_counts=getattr(m, "comparison_counts", None),
                confidence_source=getattr(m, "confidence_source", None) or "votes",
                confidence_weights=getattr(m, "confidence_weights", None),
                confidence_sources=getattr(m, "confidence_sources", None))
            if pb is not None:
                partner_boards[str(m.user_id)] = pb
    snapshot = vc_adapter.build_snapshot(
        league_id=league_id, scoring_format=fmt, viewer_team_id=viewer, viewer_name=viewer_name,
        viewer_roster=g_user_roster, opponents=opponents, players=players_dict, seed_elo=seed_map,
        lineup_slots=slots, max_players=max_players, windows=windows,
        partner_boards=partner_boards)
    request = vc_adapter.build_request(
        snapshot=snapshot, user_elo=elo_map_rt, seed_elo=seed_map, confidence=confidence_counts,
        placements=placement_bands, untouchable_ids=untouchable_ids,
        not_interested_ids=not_interested_ids, pinned_give=pinned_give or (),
        pinned_give_mode=pinned_give_mode, pinned_receive=pinned_receive or (),
        partner_team_id=opponent_user_id, fairness_threshold=fairness_threshold)
    result = vc_pipeline.run(snapshot, request, core_cfg, rank_cfg)
    cards, evidence = vc_adapter.to_trade_cards(
        result, snapshot, request, league_id=league_id, proposing_user_id=g_user_id,
        core_cfg=core_cfg, rank_cfg=rank_cfg)
    for card in cards:
        trade_service._trade_cards[card.trade_id] = card
    served = _project_trade_dispositions(cards, g_user_id, league_id)
    with _trade_jobs_lock:
        job_source = (_trade_jobs.get(job_id) or {}).get("source")
    try:
        log_trade_impressions(g_user_id, league_id, served)
    except Exception as imp_err:
        log.warning("value-core: trade impression logging failed (non-fatal): %s", imp_err)
    imp_by_card = {}
    if not _job_superseded(job_id):
        try:
            imp_by_card = _log_deck_signal_impressions(
                user_id=g_user_id, league_id=league_id, job_id=job_id, cards=served,
                players_dict=players_dict, scoring_format=fmt, source=job_source, seed_map=seed_map,
                capture={"propensity": {}, "final_key": {id(c): evidence[id(c)]["effective"]
                                                          for c in served}},
                value_core_evidence=evidence)
        except Exception as sig_err:
            log.warning("value-core: deck impression logging failed (non-fatal): %s", sig_err)
    snapshot_rows = []
    for card in served:
        row = trade_card_to_dict(card, players_dict)
        row["real_opponent"] = card.target_user_id in real_user_ids
        row["outlook"] = outlook_value
        if imp_by_card.get(id(card)):
            row["impression_id"] = imp_by_card[id(card)]
        snapshot_rows.append(row)
    diag = result.core
    total_ms = int((time.monotonic() - started) * 1000)
    with _trade_jobs_lock:
        j = _trade_jobs.get(job_id)
        if _job_live(j):
            j["cards"] = snapshot_rows
            j["final_checks_pending"] = False
            j["opponents_done"] = j["opponents_total"] = len(opponents)
            j["value_core"] = {"fair": diag.fair, "served": len(served),
                               "core_ms": diag.elapsed_ms, "total_ms": total_ms,
                               "truncated_partners": diag.truncated_partners,
                               "budget_exhausted": diag.budget_exhausted}
    log.info("trade-job %s value_core: partners=%d packages=%d checked=%d fair=%d served=%d "
             "truncated=%d budget_exhausted=%s core_ms=%d total_ms=%d", job_id, diag.partners,
             diag.packages_viewer, diag.pairs_checked, diag.fair, len(served),
             diag.truncated_partners, diag.budget_exhausted, diag.elapsed_ms, total_ms)
    gen_ms = _finish_trade_job(job_id)
    if gen_ms is None:
        return
    try:
        props = {"count": len(served), "gen_ms": gen_ms, "engine_version": "value_core", "lanes": {}}
        if job_source:
            props["deck_source"] = job_source
        record_event(g_user_id, "trades_generated", league_id=league_id, source="api", props=props)
    except Exception as ev_err:
        log.warning("value-core: record_event(trades_generated) failed: %s", ev_err)
```

**(b) The branch in `_run_trade_job`.** Insert immediately **after** the owned-pick injection `try/except` that ends with `log.warning("trade-job: owned-pick injection failed (continuing): %s", pick_inj_err)` (`server.py:7767-7768`), and **before** the `# F7 (flag deck.exploration)` comment that precedes `bakeoff_run = None` (`:7785`).

```python
        if _value_core_live(league_id=league_id, user_id=g_user_id,
                            league_user_id=ctx.league_user_id,
                            trade_intent=trade_intent, preparation=preparation):
            _run_value_core_job(
                job_id=job_id, ctx=ctx, service=service, trade_service=trade_service,
                g_user_id=g_user_id, g_league=g_league, g_user_roster=g_user_roster,
                players_dict=players_dict, seed_map=seed_map, elo_map_rt=elo_map_rt,
                confidence_counts=confidence_counts, placement_bands=placement_bands,
                untouchable_ids=untouchable_ids, not_interested_ids=not_interested_ids,
                explicit_outlook=explicit_outlook, opponent_outlooks=opponent_outlooks,
                real_user_ids=real_user_ids, outlook_value=outlook_value,
                pinned_give=pinned_give, pinned_give_mode=pinned_give_mode,
                pinned_receive=pinned_receive, opponent_user_id=opponent_user_id,
                fairness_threshold=fairness_threshold, job_draft_picks=_job_draft_picks)
            return
```

- Every name passed is already bound at that point: `ctx` at `:7477`; `elo_map_rt` at `:7495`; `untouchable_ids`/`not_interested_ids` at `:7676-7686`; `players_dict` at `:7688`; `confidence_counts` at `:7735`; `placement_bands` at `:7742`; `seed_map`/`g_user_roster` rebound by pick injection at `:7752`; `_job_draft_picks` at `:7548`; `preparation` at `:7458`.
- The `return` sits inside the outer `try`, so an exception inside the helper reaches `except Exception as e:` (`:9002`) and `_finish_trade_job(job_id, error=str(e))`.
- The owner/safety block at `:7695-7727` has already run. It stamps `safety_policy`, including the new entry from edit (c), and `final_checks_pending`, which the helper clears when it publishes.
- **Known limitation, not a regression.** `explicit_outlook` (`:7583`) and `opponent_outlooks` (`:7635-7670`) are populated exactly as today. `opponent_outlooks` stays `{}` when `trade.outlook_infer` is off; it is on in `config/features.json`.

**(c) `_trade_safety_signature` (`server.py:3367`).** Append one tuple after `("owner_only", len(owner_state) > 2 and owner_state[2]),` (`:3384`):
```python
        ("value_core", _value_core_enabled()),
```
When the flag is off, the entry is filtered out by `if enabled`, so the signature list is byte-identical. When it is on, every job stamps and expects `"value_core"`. Flipping the flag therefore makes cached and running jobs of the other engine stale in `_trade_job_is_fresh` (`:3488`) and `_trade_running_policy_matches` (`:3110`).

**(d) `_log_deck_signal_impressions` (`server.py:5039`).**
- Add a keyword parameter at the end of the signature: `value_core_evidence: dict | None = None,  # {id(card): evidence} — lld.md §7.3`.
- Insert this block immediately **before** `rows.append(row)` (`:5536`), after the `if owner_rows:` block (`:5496-5535`):
```python
        if value_core_evidence is not None:
            # Every row, every key: save_deck_impressions compiles its INSERT from the FIRST
            # row's keys (the executemany rule documented at :5427-5431).
            _vc = value_core_evidence.get(id(card))
            row["model_arm"] = "value_core"
            row["arm_rank"] = pos
            row["policy_variant"] = "value_core"
            row["policy_version"] = (_vc or {}).get("generator_version", "value-core-1")
            row["fairness_threshold"] = ((_vc or {}).get("core") or {}).get("ratio_floor")
            row["valuation_json"] = json.dumps(_vc, sort_keys=True) if _vc is not None else None
            row["trade_concept_id"] = _trade_policy.trade_concept_id(
                league_id=league_id, viewer_user_id=user_id, partner_user_id=target,
                viewer_gives=give, viewer_receives=recv)
            row["source_like_impression_id"] = None
            row.setdefault("assets_json", json.dumps({"give": give, "receive": recv}))
```
With the default `None`, no existing caller changes behavior.

**(e) `_owner_selected_assignment` (`server.py:15062`).** Extend the canonical-config filter (`:15089-15092`):
```python
    canonical["config"] = {k: v for k, v in canonical["config"].items()
                           if not k.startswith("bakeoff_include_") and not k.startswith("bakeoff_serve_")
                           and not k.startswith("significance_")
                           and not k.startswith("vc_")                 # value core: never reshuffle owner units
                           and k != "bakeoff_owner_only"}
```

**Why.** The 14 new `vc_*` rows enter `_trade_service_mod._cfg` after `reload_config()`. From there they reach the owner request context (`server.py:14905`), which is hashed into the owner experiment's `request_hash` and its 50/50 treatment parity (`:15110-15117`). Without this filter, merely deploying the seeded knobs would reshuffle established owner request units while the flag is **off**. That is the exact hazard the existing `owner_bilateral_enabled` pop guards against (`:15093-15095`).

**Other effects, accepted and documented rather than filtered.** Two other hashes of the full config change once on deploy:
- the job cache's request signature (`server.py:3090-3094`), which costs one regenerate per key;
- the dark prepared-inventory dependency receipt (`prepared_trade_runtime.py:330`).

Adding the flag key has the same one-time effect through `flags_dict()`. Neither changes what any user is served.

### 9.2 `backend/feature_flags.py`

Add `"trade.value_core",` to the `FLAG_KEYS` tuple, as the last entry before the closing paren, after `"trade.mutual_benefit_v1"` (`feature_flags.py:1171`). `DEFAULT_FLAGS` derives from the tuple (`:1174`), so nothing else changes.

### 9.3 `config/features.json` and `backend/tests/fixtures/flags/release.json`

In **both files**, add after the `"trade.mutual_benefit_v1": false` line (`features.json:266`):
```json
  "_comment_value_core": "2026-09-30 value-core engine rebuild (docs/plans/value-core-engine/). ON = organic/pinned/opponent-scoped trade jobs for allowlisted testers (model_config vc_testers_only=1) or everyone (vc_testers_only=0) are served by backend/value_core/: consensus-fair 1-3 x 1-3 packages ranked by value/outlook/rank with a per-asset cap of 3 in the first 30. Intent-mode jobs, the demo league and prepared inventories stay legacy. OFF (default) = backend/value_core is never imported and every path is byte-identical. Rollback: flip false + POST /api/feature-flags/reload.",
  "trade.value_core": false,
```
The mirror test `test_seed_ui_test_db.py:107` ignores `_`-prefixed keys. The comment is still copied, to keep the files identical.

### 9.4 `backend/database.py`

Append these 14 rows before the closing `]` of `_MODEL_CONFIG_DEFAULTS` (`database.py:3190`):
```python
    ("vc_band",                   0.20, "value core: most the viewer may OVERPAY on the premium-adjusted market ratio (ratio >= 1/(1+band)); vc_gain_band is the other side"),
    ("vc_gain_band",              0.10, "value core: most the viewer may GAIN on the premium-adjusted market ratio (ratio <= 1+gain_band); vc_band is the overpay side"),
    ("vc_stud_premium",           0.15, "value core: consolidation premium at an elite headliner; scales with (headliner/elite)^2"),
    ("vc_untouchable_min_ratio",  1.08, "value core: an untouchable is offered only when the adjusted return is at least this"),
    ("vc_max_assets_per_side",   14.0,  "value core: top-N eligible assets per team used to build 1-3 asset packages (pins always added)"),
    ("vc_max_per_partner",      200.0,  "value core: fair trades kept per partner, round-robin over (give, receive) headliner pairs"),
    ("vc_w_value",                1.0,  "value core ranking: weight of the value score"),
    ("vc_w_outlook",              1.0,  "value core ranking: weight of the outlook (both windows) score"),
    ("vc_w_rank",                 1.0,  "value core ranking: weight of the viewer-rankings score"),
    ("vc_repeat_penalty",         0.15, "value core ranking: priority points subtracted per prior appearance of a card's most-shown asset (partner at half rate)"),
    ("vc_player_cap",             3.0,  "value core ranking: max cards any one asset may appear in within the first 30"),
    ("vc_standings_weight",       0.30, "value core windows: full weight of the points-for index; ramps linearly from week 0 to week 8"),
    ("vc_throwin_min_ratio",      2.0,  "value core: a piece too small for the junk rules may ride along only if its recipient's board values it at >= this x consensus market (and >= the asset floor)"),
    ("vc_testers_only",           1.0,  "value core rollout: 1 = serve only the tester allowlist while trade.value_core is on; 0 = everyone"),
```
There is no schema change: `model_config` rows are seeded by `INSERT OR IGNORE` (`database.py:3723-3727`).

### 9.5 `backend/prepared_trade_runtime.py`

In `supported(server, league_id)` (`prepared_trade_runtime.py:86-96`), append `and not server._value_core_enabled()` to the returned conjunction. The effect is that no legacy-prepared inventory is adopted (`server.py:9121`) or prepared while the flag is on. When the flag is off the expression is unchanged.

**No other existing file changes** beyond (a)–(e) and §9.2–§9.5. In particular, the following stay untouched: `trade_service.py`, `trade_optimizer.py`, the bake-off runner, `trade_card_to_dict`, `_kickoff_trade_job`, `_trade_job_public_view`, `analytics_taxonomy.py`, `analytics_queries.py`, and every mobile and web file.

---

## 10. Logging and error handling summary

| Where | What |
|---|---|
| `core`, `windows`, `ranking`, `deck`, `pipeline` | No logging and no I/O. Invalid inputs raise `ValueError` with a message naming the id: unknown viewer, invalid `evaluate_trade` ids, or weights summing to ≤ 0. |
| `windows.infer_windows` | An `infer_team_outlook` exception becomes `DEFAULT_WINDOW` for that team. This is the one swallowed error, and it is visible in the evidence as `source == "default"`. |
| `adapter` | `log.warning` on a duplicate asset id across rosters (first owner wins). Nothing else is logged. |
| `server._value_core_standings` | `log.warning` and `({}, 0)` on any failure |
| `server._run_value_core_job` | `log.info` one summary line per job (§9.1a); `log.warning` on non-fatal impression or event failures; every other exception propagates, so the job ends in error |
| Eval tools | Write only to new private paths (mode 0600, refuse existing ones). Print aggregate numbers, never user ids. The prod connection is read-only and asserted. |
