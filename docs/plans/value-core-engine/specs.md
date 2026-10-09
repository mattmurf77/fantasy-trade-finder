# Build specs — Value-core trade engine (parallel work packages)

**Date:** 2026-09-30 · **Status:** build contract · Companion: [scope.md](scope.md), [prd.md](prd.md), [hld.md](hld.md), [lld.md](lld.md)

This is the contract for **five parallel build agents**. Every file below is owned by exactly one package. Nobody edits a file they do not own. If a package finds it needs a change to someone else's file, it stops and reports to the lead. The algorithms, signatures and exact integration edits live in [lld.md](lld.md). This document fixes the ownership, the shared interface, the tests and the gates.

## Contents
1. [Ground rules](#1-ground-rules)
2. [Work packages](#2-work-packages)
3. [Shared interface: `backend/value_core/types.py` (verbatim)](#3-shared-interface-backendvalue_coretypespy-verbatim)
4. [Sequencing](#4-sequencing)
5. [Package specs](#5-package-specs)
6. [Integration checklist (lead)](#6-integration-checklist-lead)
7. [Docs matrix](#7-docs-matrix)
8. [Lead-only items](#8-lead-only-items)

---

## 1. Ground rules

- **Branching.** Each package branches from `feat/value-core-engine` **after** the WP1 contract commit (§4). Agents work in their own worktree.
- **Guidelines.** Follow `docs/coding-guidelines.md`: simplicity first and surgical edits. No drive-by refactors in `server.py`, `database.py` or any existing module.
- **Search.** Use tracked files only: `git grep -n`.
- **Import rules.**
  - No new dependency. Standard library plus what the repo already imports.
  - Nothing under `backend/value_core/` or the new `backend/eval/` files imports `backend.server`.
  - `server.py` imports `backend.value_core.*` lazily, inside `_run_value_core_job` only.
- **Determinism.** Every public function is deterministic for identical inputs. RNG appears only where a seed is an explicit argument.
- **Tests.** Each package's tests run with `python3 -m pytest backend/tests/<file> -q` on Python 3.12, which is the CI version (`backend/CLAUDE.md` §Gotchas). No network, and no real DB beyond the in-memory SQLite patterns the suite already uses.
- **Out of bounds.** Do not touch `living-memory/*`, `docs/plans/README.md` or any `CLAUDE.md`. These are lead-only (§8).

## 2. Work packages

| Package | Owned files (C = create, E = edit) | Purpose |
|---|---|---|
| **WP1 — Contract + value core** | C `backend/value_core/__init__.py` · C `backend/value_core/types.py` · C `backend/value_core/core.py` · C `backend/tests/test_value_core_core.py` · C `backend/tests/test_value_core_perf.py` | The shared contract, plus value-only enumeration of fair 1–3 × 1–3 trades with the hard rules |
| **WP2 — Ranking layer** | C `backend/value_core/windows.py` · C `backend/value_core/ranking.py` · C `backend/value_core/deck.py` · C `backend/tests/test_value_core_windows.py` · C `backend/tests/test_value_core_ranking.py` · C `backend/tests/test_value_core_deck.py` | Team windows, the three scores and priority, card reasons, and greedy deck assembly with the repeat cap |
| **WP3 — Serving integration** | C `backend/value_core/pipeline.py` · C `backend/value_core/adapter.py` · E `backend/server.py` · E `backend/feature_flags.py` · E `config/features.json` · E `backend/tests/fixtures/flags/release.json` · E `backend/database.py` · E `backend/prepared_trade_runtime.py` · C `backend/tests/test_value_core_adapter.py` · C `backend/tests/test_value_core_serving.py` · C `docs/plans/value-core-engine/code-walk.md` | Flag, knobs and branch in `_run_trade_job`; app objects → contract → `TradeCard`; evidence logged to impressions |
| **WP4 — Eval bench** | C `backend/eval/value_core_bench.py` · C `backend/eval/value_core_recall.py` · C `backend/eval/blind_grade.py` · C `backend/tests/test_value_core_bench.py` · C `backend/tests/test_value_core_recall.py` · C `backend/tests/test_blind_grade.py` · C `backend/tests/test_value_core_e2e.py` | Freeze, guardrails, real-trade recall and band calibration, blind-grade export and import, end-to-end tests |
| **WP5 — Reference docs** | E `docs/config-reference.md` · E `docs/api-reference.md` · E `docs/data-dictionary.md` · E `docs/architecture.md` · E `docs/glossary.md` · E `docs/runbook.md` · C `docs/adr/adr-024-value-core-engine.md` · E `living-memory/HLD.md` · E `living-memory/LLD.md` | Every trigger-table doc update, written from this spec |

**Shared interface file:** `backend/value_core/types.py`, owned and written by WP1, verbatim from §3.

## 3. Shared interface: `backend/value_core/types.py` (verbatim)

WP1 writes this file **exactly** as below, byte for byte including comments, and commits it first (§4). Every other package codes against it.

```python
"""Shared contract for the value-core trade engine.

Written verbatim from docs/plans/value-core-engine/specs.md section 3 by WP1.
Every other package codes against these names. Pure data: this module imports
only the standard library, never an app module. Changing it after build start
needs the lead's sign-off recorded in specs.md section 3.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

ENGINE_ID = "value_core"
ENGINE_VERSION = "value-core-2"   # 2: breakup + picks_for_players rules (operator, 2026-10-09)
TOP_WINDOW = 30  # the guardrails and the per-asset cap are defined on the first 30 cards
CORE_POSITIONS = ("QB", "RB", "WR", "TE")

Window = Literal["contender", "rebuilder", "middle"]
AssetKind = Literal["player", "pick"]
Side = Literal["give", "receive"]


@dataclass(frozen=True)
class Asset:
    """One roster item the engine can see.

    Every core-position player is present (market may be 0.0 for an unvalued
    deep backup: he still fills lineup slots). Picks carry position "PICK".
    Only assets with market >= CoreConfig.asset_floor_abs can enter a package.
    """
    id: str
    kind: AssetKind
    position: str            # "QB" | "RB" | "WR" | "TE" | "PICK"
    name: str
    age: float | None        # None for picks and unknown ages
    market: float            # consensus value in engine value units: elo_to_value(seed_elo)


@dataclass(frozen=True)
class Standing:
    wins: int
    losses: int
    ties: int
    points_for: float


@dataclass(frozen=True)
class TeamWindow:
    window: Window
    score: float                                      # outlook score incl. standings term (>0 leans contender)
    source: Literal["declared", "inferred", "default"]
    pf_index: float | None                            # points-for index in [-1, 1]; None = standings unavailable
    standings_weight: float                           # effective weight applied to pf_index (0.0 if none)


DEFAULT_WINDOW = TeamWindow("middle", 0.0, "default", None, 0.0)


@dataclass(frozen=True)
class Team:
    team_id: str                 # LEAGUE identity (roster owner_id == LeagueMember.user_id)
    name: str
    asset_ids: tuple[str, ...]   # every core-position player and owned pick on the roster
    other_players: int = 0       # K / DEF / IDP / unknown-position players: roster size only
    window: TeamWindow = DEFAULT_WINDOW


@dataclass(frozen=True)
class RosterRules:
    lineup_slots: tuple[str, ...]   # starting slots; only power_rankings.LINEUP_SLOT_ELIGIBILITY keys are enforced
    max_players: int | None         # roster capacity incl. IR/taxi, players only; None = unknown (size rule skipped)


@dataclass(frozen=True)
class LeagueSnapshot:
    league_id: str
    scoring_format: str             # "1qb_ppr" | "sf_tep"
    assets: Mapping[str, Asset]
    teams: Mapping[str, Team]       # every team, including the viewer's
    rules: RosterRules
    first_round_value: float        # market value at the first_1 tier floor (tier_config.json)
    elite_value: float              # market value at the firsts_4plus tier floor
    # team_id -> that partner's published board, confidence-shrunk toward consensus. Only
    # partners who really ranked (server has_rankings) appear; absent = no evidence.
    partner_boards: Mapping[str, Board] = field(default_factory=dict)


@dataclass(frozen=True)
class Board:
    """The viewer's personal board, already shrunk toward consensus (w = n/(n+4))."""
    values: Mapping[str, float]     # asset_id -> personal value in engine value units; absent => market
    comparisons: Mapping[str, int]  # asset_id -> matchup count n behind the shrink (evidence only)


@dataclass(frozen=True)
class Request:
    viewer_team_id: str
    board: Board | None = None
    untouchable_ids: frozenset[str] = frozenset()
    not_interested_ids: frozenset[str] = frozenset()
    pinned_give_ids: frozenset[str] = frozenset()
    pinned_give_mode: Literal["any", "all"] = "any"
    pinned_receive_ids: frozenset[str] = frozenset()
    partner_team_id: str | None = None
    fairness_threshold: float | None = None   # client preference: may tighten the band, never loosen it


@dataclass(frozen=True)
class CoreConfig:
    band: float = 0.20        # how much MORE market value the viewer may give (overpay side)
    gain_band: float = 0.10   # how much MORE market value the viewer may receive (the partner's loss)
    stud_premium: float = 0.15
    untouchable_min_ratio: float = 1.08
    max_assets_per_side: int = 14
    max_per_partner: int = 200
    asset_floor_abs: float = 450.0
    filler_min_frac: float = 0.25
    throwin_min_ratio: float = 2.0   # recipient's value / consensus market a throw-in needs
    breakup_min_ratio: float = 0.70  # the viewer's best piece received / best piece given; below = "breakup"
    rebuilders_keep_picks: bool = True   # a rebuilding team never gives a pick while receiving a player


@dataclass(frozen=True)
class RankConfig:
    w_value: float = 1.0
    w_outlook: float = 1.0
    w_rank: float = 1.0
    repeat_penalty: float = 0.15
    player_cap: int = 3


@dataclass(frozen=True)
class FairTrade:
    partner_team_id: str
    give: tuple[str, ...]           # viewer gives; sorted by (-market, id)
    receive: tuple[str, ...]        # viewer receives; sorted by (-market, id)
    give_market: float              # raw sum
    receive_market: float           # raw sum
    adjusted_ratio: float           # premium-adjusted receive / give, viewer's perspective
    premium: float                  # stud premium applied; 0.0 when none
    premium_side: Side | None       # viewer side whose package was credited with the premium
    uses_untouchable: bool
    drops_needed: tuple[int, int]   # (viewer, partner) sub-floor bench drops needed to stay within max_players
    throwin: str | None = None      # the one piece exempt from the junk rules: its recipient values it
                                    # >= throwin_min_ratio x market (and >= the asset floor)

    @property
    def key(self) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        return (self.partner_team_id, self.give, self.receive)


@dataclass(frozen=True)
class TradeVerdict:
    ok: bool
    reason: str | None              # first failing rule code (core.REJECT_CODES); None when ok
    trade: FairTrade | None         # priced trade whenever both sides are non-empty, even when not ok


@dataclass
class CoreDiagnostics:
    partners: int = 0
    packages_viewer: int = 0
    pairs_checked: int = 0
    fair: int = 0
    rejected: dict[str, int] = field(default_factory=dict)   # reason code -> count
    truncated_partners: int = 0     # partners that hit max_per_partner or the check cap
    budget_exhausted: bool = False  # the time budget stopped enumeration early
    elapsed_ms: int = 0


@dataclass(frozen=True)
class Scores:
    value: float                    # [0, 1]
    outlook: float                  # [0, 1]
    rank: float                     # [0, 1]
    priority: float                 # weighted mean of the three


@dataclass(frozen=True)
class ScoredTrade:
    trade: FairTrade
    scores: Scores
    detail: Mapping[str, object]    # component evidence; keys fixed in lld.md section 5.4


@dataclass(frozen=True)
class DeckEntry:
    position: int                   # 0-based served position
    scored: ScoredTrade
    effective: float                # priority minus repeat penalties at selection time
    reasons: tuple[str, ...]


@dataclass
class PipelineResult:
    entries: list[DeckEntry]
    core: CoreDiagnostics
    elapsed_ms: int
```

### 3.1 Change control

**Changing the interface.** Any change to `types.py` after the WP1 contract commit follows three steps:
1. The requesting package stops and reports the exact diff to the lead.
2. The lead applies the change as a new contract commit and records it here as a dated line: *"2026-10-0X — added field Y to Z (requested by WPn): reason"*.
3. Every package rebases.

**The public signatures in lld.md** (§4.1, §5.1, §5.2, §5.6, §6, §7.1, §8) are part of the contract too. Change them only through the lead.

**Changes to date:**
- 2026-10-09 — `value-core-2`, lead-applied on the operator's rules after the first Calibration round: two hard rules, `breakup` and `picks_for_players`, after `filler` in `REJECT_CODES`, with two `CoreConfig` fields (`breakup_min_ratio` 0.70, `rebuilders_keep_picks` True). Code defaults only — no `model_config` knob yet (Calibration builds with `CoreConfig()`). [lld §4.3](lld.md#43-hard-rules-in-order), [D-199](../../../living-memory/DECISIONS.md).
- 2026-10-01 — throw-ins, lead-applied on the operator's rule: *"throwins are fine, but only if there is a clear throwin that the recipient values much higher than consensus (double the value)"*. `types.py` gained `LeagueSnapshot.partner_boards: Mapping[str, Board]` (default empty), `FairTrade.throwin: str | None` (default None) and `CoreConfig.throwin_min_ratio = 2.0` (seed `vc_throwin_min_ratio`, clamp [1, 10]). lld §4.1 gained `core.throwin_ok`, `MAX_THROWIN_OPTIONS = 3` and `THROWIN_MIN_COMPARISONS = 3`; lld §7.1 gained `adapter.partner_board_from` and the `partner_boards=` keyword of `adapter.build_snapshot`. A throw-in needs evidence on both sides (market > 0, and at least `THROWIN_MIN_COMPARISONS` comparisons behind the recipient's value for that player): before that rule, unranked or unpriced players produced up to 28 of 30 cards on one real seat. A review pass the same day fixed three more things: a throw-in is not a piece for the stud premium, so it never switches the premium on or off; the throw-in shortlist is cut to `MAX_THROWIN_OPTIONS` per candidate pair after the junk check, not per partner before it; and throw-in variants have their own check budget, so they never starve base pairs. Real bench (6 leagues, 77 seats, first 30 cards): throw-ins on 17 of 2,220 cards, 4 to the viewer and 13 to the partner. Tests added: core `test_throwin_to_viewer_needs_double_value`, `test_throwin_value_must_clear_the_floor`, `test_throwin_to_partner_uses_their_published_board`, `test_throwin_is_exempt_from_reducible_and_at_most_one`, `test_evaluate_trade_marks_the_explicit_throwin`, `test_throwin_needs_real_evidence_on_both_sides`, `test_throwin_never_switches_the_stud_premium`, `test_throwin_shortlist_is_cut_per_pair_after_the_junk_check`, `test_throwin_needs_three_comparisons`; ranking `test_reasons_explain_the_throwin`; adapter `test_partner_board_from_no_evidence_stays_at_consensus`, `test_build_snapshot_keeps_partner_boards_for_known_partners_and_assets`, `test_core_config_reads_throwin_ratio`. The knob count is now 14.
- 2026-10-01 — asymmetric band, lead-applied on the operator's decision. `types.py` gained `CoreConfig.gain_band = 0.10` (seed `vc_gain_band`, clamp [0.01, 0.50]); `CoreConfig.band` (0.20) is now the **overpay** side only, and `vc_band`'s description says so. The viewer may give up to `band` more market value than they get (ratio ≥ 1/(1+band)) but may take at most `gain_band` more (ratio ≤ 1+gain_band); the client fairness preference tightens both through `effective_band`. The evidence `core` block gained `gain_band`, and `ratio_ceiling` is now 1+gain_band. Evidence on the frozen real bench (6 leagues, 77 seats, first 30 cards): symmetric ±10% gives insult 0.3% and median value given +8.8%; symmetric ±20% gives insult **5.6%** (fails the 3% guardrail) and +17.1%; pay 20% / take 10% (the default) gives insult 0.2% and +8.4%, real piece back 93.3%, 0 near-duplicates and 0 repeat acquisitions. Overpays above 10% reach only 16 of the 2,220 first-30 cards: they surface only where the viewer's rankings justify them. This supersedes the symmetric ±20% line below the same day; that recommendation rested on a synthetic insult rate (1.1%) the real leagues did not reproduce. `CFG10 = CoreConfig(band=0.10)` in `test_value_core_core.py` is now symmetric ±10% (gain_band defaults to 0.10).
- 2026-10-01 — `types.py` `CoreConfig.band` default 0.10 → 0.20 (and the `vc_band` seed), lead-applied on the operator's decision that real trades should steer the band significantly. Evidence: ±20% covers 38% of real FFV3/Lakeview trades (±10%: 20%; ±25%: 39%); synthetic insult rate 1.1% (±25%: 2.8%, ±30%: 29%). `test_value_core_core.py` pins `CFG10 = CoreConfig(band=0.10)` because it tests band mechanics.
- 2026-09-30 — lld §4.5 cap order (not `types.py`), lead-initiated at WP1 review: enumeration and the per-partner cap round-robin over headliners instead of biggest-first. `test_per_partner_cap_keeps_biggest_headliners` became `test_per_partner_cap_spreads_headliner_pairs`, and `test_value_core_perf.py::test_pool_spreads_across_give_headliners` was added. Reason: the biggest-first caps acted as a hidden ranking (92% of the pool gave away a top-3 asset).
- 2026-09-30 — lld §5.6 deck variety rules + §8.2 guardrails (not `types.py`), operator request: *"I don't want to see the same iteration of a trade with a trade partner with only minor pieces swapped out... or the same trade partner with different years' draft picks"*. `deck.py` gained `idea_key`, `acquisition_key` and `partner_cap`: one card per trade idea (lower-priority versions are dropped), acquisitions shown in rounds, and a partner cap beside the per-asset cap in the first 30. The bench appearances guardrail now counts acquired assets only (`max_acquired_appearances`), and `near_duplicates` = 0 is a new guardrail. Deck tests: `test_minor_piece_swaps_are_one_idea`, `test_pick_years_are_one_idea_and_one_acquisition`, `test_each_acquisition_once_before_any_repeat` and `test_partner_cap_in_first_30` were added, and `test_lazy_equals_naive`'s reference implements all three rules. Bench tests: `test_guardrails_count_near_duplicates_and_repeat_acquisitions` was added. On the 12-seat synthetic league (first 30 cards, before → after): near-duplicates median 1.5 / max 5 → 0; repeat acquisitions median 8 / max 11 → 0; distinct acquisitions 22 → 30; the deck shrank from about 2,200 to about 1,050 ideas.

## 4. Sequencing

1. **Contract commit, 15 minutes.** WP1 creates `backend/value_core/__init__.py` (a docstring only, no imports) and `types.py` verbatim, and runs `python3 -c "import backend.value_core.types"`. It commits `value-core: shared contract (types.py)` on `feat/value-core-engine`.
2. **Fan-out.** WP1 (the rest), WP2, WP3, WP4 and WP5 start in parallel from that commit.
3. **Merge order** onto `feat/value-core-engine`: WP1 → WP2 → WP3 → WP4 → WP5. There are no file conflicts by construction, so the order only keeps each intermediate state importable. After each merge the lead runs that package's tests.
4. **Integration** (§6), after all five have merged.

**Cross-package runtime dependencies.** Each package stubs these for its isolated run:

| Package | Imports at runtime from | Isolation strategy |
|---|---|---|
| WP1 | `backend.power_rankings` (exists) | none needed |
| WP2 | `backend.trade_service`, `backend.power_rankings` (exist) | Tests build `FairTrade` objects by hand; no dependency on WP1 code |
| WP3 | WP2 `windows`, and WP1/WP2 through `pipeline.run` | `pipeline.py` imports core/ranking/deck lazily inside `run`. The serving tests use the `vc_stubs` fixture (§5.3) to stub `pipeline.run` and `windows.infer_windows`. |
| WP4 | `pipeline.run`, `windows.infer_windows`, `core.evaluate_trade`, `adapter.tier_values`, `adapter.default_lineup_slots` | All five are imported **lazily inside functions**. Unit tests inject `engine=` stubs and hand-built `DeckEntry` lists. Where a function under test needs `windows`/`adapter`/`core` before they land, the test installs a `sys.modules` stub the same way as WP3's `vc_stubs`, and after integration the same tests pass against the real modules. `test_value_core_e2e.py` is **integration-only** and excluded from the isolated run. |
| WP5 | none (docs) | — |

---

## 5. Package specs

Shared test helper conventions: each test file defines its own tiny builders. Nothing is shared between packages. Here is the builder the WP1 and WP2 examples use; each file copies it inline.

```python
from backend.value_core.types import *   # in tests only

def A(id, pos, market, age=25.0):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None if kind == "pick" else age, float(market))

BODIES = lambda t: [A(f"{t}qb", "QB", 300), A(f"{t}rb1", "RB", 300), A(f"{t}rb2", "RB", 300),
                    A(f"{t}wr1", "WR", 300), A(f"{t}wr2", "WR", 300), A(f"{t}te", "TE", 300)]
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")

def snap(teams, *, slots=SLOTS, max_players=None, other=None, windows=None):
    assets = {a.id: a for lst in teams.values() for a in lst}
    return LeagueSnapshot("L1", "1qb_ppr", assets,
        {t: Team(t, t, tuple(a.id for a in lst), (other or {}).get(t, 0),
                 (windows or {}).get(t, DEFAULT_WINDOW)) for t, lst in teams.items()},
        RosterRules(tuple(slots), max_players), first_round_value=1492.0, elite_value=8457.0)
```

`BODIES(t)` gives every team a full lineup of sub-floor (300) players. They never enter packages (the floor is 450), but they keep lineups filled, so tests that are not about lineups are never rejected by the lineup rule.

### 5.1 WP1 — Contract + value core

**Owns:** see §2. Implements [lld.md §4](lld.md#4-core-backendvalue_corecorepy) exactly.

**Acceptance criteria.**
1. `types.py` is byte-identical to §3.
2. `core.py` exposes exactly the §4.1 public names and constants, and imports only stdlib, `.types` and `backend.power_rankings`.
3. The rules are applied in the order of `REJECT_CODES`, and the rejection counts are recorded in `CoreDiagnostics.rejected`.
4. The output is deterministic, and ordered as in lld §4.5.
5. The complexity bounds in lld §4.6 are enforced by code: `max_checks_per_partner`, `time_budget_s`, `max_per_partner`.
6. No logging, no I/O, no flag or config reads.

**Tests: `backend/tests/test_value_core_core.py`.** Every team carries `BODIES(t)` unless stated. The default config is `CFG10 = CoreConfig(band=0.10)`, a symmetric ±10% band (`gain_band` defaults to 0.10), because these tests pin band mechanics; the "outside ±10%" notes below refer to it.

| Test | Fixture | Asserts |
|---|---|---|
| `test_one_for_one_inside_band_kept` | V: `a1` WR 3000 · P: `b1` WR 3150 | one trade `give=("a1",)`, `receive=("b1",)`; `adjusted_ratio == approx(1.05)`; `premium == 0` |
| `test_one_for_one_outside_band_rejected` | as above with `b1` = 3400 | no trade containing `b1`; `rejected["band"] >= 1` |
| `test_stud_premium_consolidation` | P: `s1` WR 8457 · V: `a1` WR 4200, `a2` WR 4200 | no trade receiving `s1`. Re-run with `a1` = 4600, `a2` = 4400: trade `(("a1","a2"), ("s1",))` kept, `premium == approx(0.15)`, `premium_side == "receive"`, `adjusted_ratio == approx(8457*1.15/9000)` |
| `test_stud_premium_scaling` | none | `stud_premium(4228.5, 8457, 0.15) == approx(0.0375)`; `stud_premium(2117, 8457, 0.15) == approx(0.15*(2117/8457)**2)`; `stud_premium(9000, 8457, 0.15) == 0.15` |
| `test_no_premium_equal_counts` | V: `a1` 3000, `a2` 2000 · P: `b1` 3100, `b2` 1900 | the 2-for-2 trade has `premium == 0` and `premium_side is None` |
| `test_absolute_floor` | V: `a1` 3000, `a3` WR 400 | `a3` never appears in any trade |
| `test_relative_filler_vs_trade_headliner` | V: `a1` 6000, `a4` 1600 · P: `b3` 7300 | `(("a1","a4"), ("b3",))` absent. It passes the within-package pre-prune (1600 ≥ 0.25·6000) and the band (adjusted ≈ 1.068), but 1600 < 0.25·7300 = 1825; `rejected["filler"] >= 1` |
| `test_reducible_trade_rejected` | `CoreConfig(filler_min_frac=0.0)`; V: `a1` 3000, `a5` 500 · P: `b1` 3250 | `(("a1","a5"), ("b1",))` absent, `rejected["reducible"] >= 1`; `(("a1",), ("b1",))` present |
| `test_untouchable_needs_above_market` | V: `a1` 3000 (untouchable) · P: `b1` 3100, `b2` 3280 | `a1→b1` absent (`rejected["untouchable"] >= 1`); `a1→b2` present with `uses_untouchable is True` |
| `test_not_interested_never_received` | P: `b1`, `b2` fair vs `a1`; `not_interested_ids={"b1"}` | no trade has `b1` in `receive` |
| `test_pinned_give_any_and_all` | V: `a1` 3000, `a2` 3100 · P: `b1` 3050, `b2` 3150 | `any {"a1"}`: every give contains `a1`. `all {"a1","a2"}`: every give ⊇ {a1, a2}, and `(("a2","a1"), ("b2","b1"))` is present |
| `test_pinned_receive_skips_partners` | three teams; `pinned_receive_ids={"c1"}` owned by P2 | every trade has partner P2 and `c1` in `receive` |
| `test_partner_scope` | three teams; `partner_team_id="P2"` | every trade has `partner_team_id == "P2"`; `diag.partners == 1` |
| `test_roster_size_uses_droppable_bench` | `max_players=10`; V: `a1` WR 1600, `a2` RB 1500 + bodies · P: `b1` WR 3300 + bodies (7 players, other_players=3) | trade `(("a1","a2"), ("b1",))` kept with `drops_needed == (0, 1)`. Re-run with P's bodies at market 500 (not droppable): absent, `rejected["roster_size"] >= 1` |
| `test_lineup_blocks_losing_only_qb` | no `BODIES`; slots `("QB","WR")`; V: `vq` QB 3000, `vw` WR 300 · P: `pw` WR 3100, `pw2` WR 300, `pq` QB 300 | `(("vq",), ("pw",))` absent (`rejected["lineup"] >= 1`). Add V `vq2` QB 300: present |
| `test_fairness_threshold_only_tightens` | V `a1` 3000 · P `b1` 3150 | `fairness_threshold=0.97`: absent (band 0.03). `0.5`: present. `effective_band(0.10, 0.5) == 0.10`; `effective_band(0.10, 0.99) == 0.02` |
| `test_per_partner_cap_spreads_headliner_pairs` | V: 4 WRs 3000/3000/2000/2000 · P: 4 WRs 3050/3050/2050/2050; `max_per_partner=2` | 2 trades kept with distinct (give, receive) headliner pairs, both with headliner market ≥ 3000; `diag.truncated_partners == 1` |
| `test_check_cap_and_budget` | synthetic 2-team league, 14 assets per side | `max_checks_per_partner=50` gives `pairs_checked <= 50` and `truncated_partners == 1`; `time_budget_s=0.0` gives `budget_exhausted is True` |
| `test_deterministic` | any fixture | two calls return equal lists in equal order |
| `test_evaluate_trade_agrees_with_find` | the stud fixture | for every kept trade, `evaluate_trade(...).ok` and an equal `adjusted_ratio`; for the 4200+4200 package, `ok is False`, `reason == "band"`, `trade is not None` |
| `test_evaluate_trade_rejects_foreign_ids` | — | a give id not on the viewer's team raises `ValueError` |
| `test_unknown_viewer_raises` | — | `ValueError` |
| `test_throwin_to_viewer_needs_double_value` | V: `a1` WR 3000 · P: `b1` WR 2600, `pw9` WR 300, `pw8` WR 280 (0.867 alone: outside ±10%) | board `pw9` = 700 (n 12, ≥ 2 × 300 and ≥ 450): trade `(("a1",), ("b1","pw9"))` with `throwin == "pw9"`, `premium_side is None` (a throw-in is not a piece for the premium) and `adjusted_ratio == approx(2900/3000)`. Board 550: no `a1` → `b1` trade. No board: no throw-in anywhere |
| `test_throwin_value_must_clear_the_floor` | P: `b1` 2850, `pw9` 150 | board `pw9` = 400 (≥ 2 × 150 but < 450): no throw-in; 460: a `pw9` throw-in |
| `test_throwin_to_partner_uses_their_published_board` | V: `a1` 3000, `va9` 300, `va8` 280 · P: `b1` 3500 (1.167: outside ±10%) | no `partner_boards`: nothing receives `b1` alone. `partner_boards={"P": va9 = 900, n 20}`: `(("a1","va9"), ("b1",))` with `throwin == "va9"`, `premium_side is None`, `adjusted_ratio == approx(3500/3300)` |
| `test_throwin_is_exempt_from_reducible_and_at_most_one` | V: `a1` 3000 · P: `b1` 3000, `pw9` 250, `pw7` 260, `pw8` 280; board `pw9` 600, `pw7` 700 | `a1 → b1`, `a1 → (b1, pw7)` and `a1 → (b1, pw9)` all present; no trade carries two sub-floor pieces |
| `test_evaluate_trade_marks_the_explicit_throwin` | the `pw9` gap league | with the board: `ok`, `trade.throwin == "pw9"`. Without: `reason == "floor"`, `trade.throwin is None` |
| `test_throwin_needs_real_evidence_on_both_sides` | the gap league | board `pw9` = 900 with `comparisons` 0: no throw-in. `pw9` at market 0 with a ranked board: no throw-in |
| `test_throwin_never_switches_the_stud_premium` | V: `a` 4000, `b` 3600 · P: `s` 8000, `ti` 300 (board 700, n 5) | `(("a","b"), ("s",))` absent (1.194 with the premium: too big a gain), and `(("a","b"), ("s","ti"))` absent too: the throw-in does not turn the 2-for-1 into a premium-free 2-for-2 |
| `test_throwin_shortlist_is_cut_per_pair_after_the_junk_check` | the gap league plus P's `m1`–`m3` RBs (1100–1300) that the viewer's board also rates ≥ 2× | `(("a1",), ("b1","pw9"))` present with `throwin == "pw9"` (the bigger, non-junk RBs do not crowd it off the shortlist); `evaluate_trade` agrees |
| `test_throwin_needs_three_comparisons` | the gap league | board `pw9` = 700 with 2 comparisons: no throw-in; with `THROWIN_MIN_COMPARISONS`: a `pw9` throw-in |

**Tests: `backend/tests/test_value_core_perf.py`.**
- **`test_fourteen_team_league_bounded`.** The fixture is generated in the test: `random.Random(11)`, 14 teams, each with 26 core players (QB 3 / RB 8 / WR 10 / TE 5) and 6 picks. Markets are `min(9500, max(100, exp(gauss(ln 1200, 1.0))))` and ages are `uniform(21, 33)`. Slots are `("QB","RB","RB","WR","WR","WR","TE","FLEX","FLEX","SUPER_FLEX")` with `max_players=30`. It asserts:
  - `diag.pairs_checked <= 13 * 40_000`;
  - `not diag.budget_exhausted`;
  - `len(trades) <= 13 * 200`;
  - elapsed < 10 s. This is a loose CI bound; the log prints the actual ms.
- **`test_package_count_bound`.** 17 candidates give ≤ 833 packages, checked through `diag.packages_viewer` with 3 pins.

**Isolated verification.**
```
python3 -m pytest backend/tests/test_value_core_core.py backend/tests/test_value_core_perf.py -q
```
Also run `python3 -c "import backend.value_core.core"`.

**Docs:** none. WP5 owns them.

### 5.2 WP2 — Ranking layer

**Owns:** see §2. Implements [lld.md §5](lld.md#5-ranking-layer-windows-ranking-deck) exactly.
- `windows.py` imports `infer_team_outlook` and `_c` **as module-level names**: `from ..trade_service import infer_team_outlook, _c`. Tests monkeypatch `backend.value_core.windows.infer_team_outlook`.
- `ranking.py` imports `optimal_starters` from `..power_rankings`.

**Acceptance criteria.**
1. The public names and constants are exactly as in lld §5.1, §5.2 and §5.6.
2. Score formulas follow §5.3, `detail` keys follow §5.4, and reason templates follow §5.5, **character for character**.
3. `assemble_deck` returns one card per trade idea (lld §5.6 `idea_key`), its highest-priority version, and no trade twice. The idea's other versions are dropped; nothing else is.
4. Every acquisition (`acquisition_key`) is shown once before any is shown twice. In the first `TOP_WINDOW` entries, no asset appears in more than `player_cap` cards and no partner takes more than `partner_cap(n)`, whenever the pool allows it.
5. The output is deterministic.
6. No logging or I/O. The only config reads are the two outlook cuts, through `_c`.

**Tests: `backend/tests/test_value_core_windows.py`.**

| Test | Asserts |
|---|---|
| `test_standings_weight_ramp` | `standings_weight_for(0, 0.3) == 0`; `(3, 0.3) == approx(0.1125)`; `(8, 0.3) == 0.3`; `(12, 0.3) == 0.3`; `(5, -1) == 0` |
| `test_pf_indices` | PF [100, 200, 300, 400] → [−1, −1/3, 1/3, 1]; two teams tied → [0, 0]; one team → `{}` |
| `test_standings_move_middle_team` | monkeypatch `infer_team_outlook` → `("not_sure", 0.0, {})`; 4 teams, team T has the top PF. At week 8 with weight 0.3, T is `contender` with `score == approx(0.3)` and `pf_index == 1.0`. At week 0 it is `middle` with `standings_weight == 0.0` |
| `test_declared_overrides` | declared `{"T": "jets"}` → `window == "rebuilder"`, `source == "declared"` |
| `test_outlook_flags_do_not_move_windows` | the same inputs with `trade.outlook_composite` / `trade.outlook_net_firsts` monkeypatched on give identical `TeamWindow`s |
| `test_infer_exception_defaults` | `infer_team_outlook` raises for one team → that team gets `DEFAULT_WINDOW`, and the others are unaffected |

**Tests: `backend/tests/test_value_core_ranking.py`.** `FairTrade` objects are built by hand; the core is not involved.

| Test | Fixture | Asserts |
|---|---|---|
| `test_value_even_small_return` | V has two WR starters worth 2000; the trade gives `x` WR 800 (age 26, bench) and receives `y` WR 800 (age 26) | `value == approx(0.5*0.5 + 0.5*(800/1492))`; `detail["value"]["best_in_starter"] is False` |
| `test_value_starter_back_scores_one` | V's WR2 is worth 500; receive WR 1300 | `s_piece == 1.0`; `best_in_starter is True` |
| `test_value_first_round_pick_scores_one` | receive PICK 2117 | `s_piece == 1.0` |
| `test_value_delta_saturation` | receive/give = 1.25 → `s_delta == 1.0`; = 0.8 → `s_delta == approx(0.0)` | — |
| `test_outlook_rewards_both_windows` | V contender gives prospect `p` WR 2500 (age 21, not a V starter) and receives vet `v` WR 2400 (age 29), replacing V's WR2 worth 1000. P is rebuilder. | `outlook > 0.5`. With the windows swapped (V rebuilder, P contender), `outlook < 0.5` |
| `test_rank_neutral_without_board` | `board=None` | `rank == 0.5`; `detail["rank"]["has_board"] is False` |
| `test_rank_above_in_below_out` | receive `b1` (market 3000, personal 3600); give `a1` (market 3000, personal 2700) | `gap_rel == approx(0.30)`; `rank == 1.0`; `top_asset == "b1"`; `top_side == "receive"` |
| `test_priority_weighted_mean` | `RankConfig(2, 1, 1)` | `priority == approx((2v + o + r)/4)` |
| `test_zero_weights_raise` | `RankConfig(0, 0, 0)` | `ValueError` |
| `test_reasons_value_outlook_rank` | 20 WRs `w01..w20`, markets `5000 − 200·(i−1)`. V receives `w20` (1200, age 30) and gives `x` (1200, age 22); P is rebuilder; board `personal(w20) = 3700` | `card_reasons(...) == ("Fair on value", "Fits their rebuild", "You rank W20 12 spots above market")` |
| `test_reasons_pay_over_market` | give 1100, receive 1000 | the first reason is `"You pay 9% over market"` |
| `test_reasons_piece_fills_slot` | no board, neutral windows, receive a would-be starter named `Y` | `("Fair on value", "Y would start for you")` |
| `test_score_order_preserved` | 5 trades | the output order equals the input order |
| `test_reasons_explain_the_throwin` | V receives `pt` (market 250) as a throw-in, board 575; P receives `vt` (market 200) as a throw-in, `partner_boards` 600 | the reasons contain `"Throw-in: you rank PT at 2.3× market"`, then `"Throw-in: they rank VT at 3.0× market"`; never more than 3 lines |

**Tests: `backend/tests/test_value_core_deck.py`.** `ScoredTrade` objects are built by hand with chosen priorities.

| Test | Fixture | Asserts |
|---|---|---|
| `test_cap_in_first_30_nothing_dropped` | 100 trades containing `stud` (priorities 0.99 → 0.90, distinct partners and other assets) plus 100 without (0.50 → 0.40); every trade a distinct idea | at most 3 of the first 30 contain `stud`; `len == 200`; same set of keys as the input |
| `test_repeat_penalty_order` | t1 (x, A, 0.80), t2 (x, B, 0.78), t3 (y, C, 0.70); penalty 0.15 | order t1, t3, t2; t2's `effective == approx(0.63)` |
| `test_partner_half_penalty` | t1 (x, A, 0.80), t2 (y, A, 0.78), t3 (z, B, 0.72) | order t1, t3, t2 (0.78 − 0.075 = 0.705 < 0.72) |
| `test_cap_relaxes_when_only_capped_remain` | 5 trades all containing x | all 5 returned at positions 0..4 |
| `test_lazy_equals_naive` | 30 seeded random pools of 60 trades over 8 assets (6 players, 2 picks) and 4 partners | the key order equals a naive O(n²) reference written in the test that implements all three rules: best version per idea, acquisition rounds, partner and asset caps |
| `test_reasons_attached` | any | every entry's `reasons` equals `ranking.card_reasons(...)` for its trade |
| `test_minor_piece_swaps_are_one_idea` | P: x → (y, m1) 0.80, x → (y, m2) 0.79, (x, m3) → y 0.78; Q: z → w 0.50 | only the best P version is shown: order `[best, other]` |
| `test_pick_years_are_one_idea_and_one_acquisition` | P: x → 2026 1st 0.90, x → 2027 1st 0.89, z → 2027 2nd 0.88; Q and R one trade each (0.40, 0.30) | the 2027-1st version is dropped; `z → 2027 2nd` is a new idea but the same acquisition ("a pick from P"), so it waits for round 2: order y26, q1, q2, other_give |
| `test_each_acquisition_once_before_any_repeat` | P: x1 → y 0.95, x2 → y 0.94; five one-card partners at 0.30 → 0.26 | the second y-from-P card comes last, after every round-1 card |
| `test_partner_cap_in_first_30` | P: 40 strong distinct trades (0.99 →); ten more partners with 5 trades each (0.40 →) | `partner_cap(11) == 4`; P has exactly 4 of the first 30; `len == 90` (nothing dropped: every card is a distinct idea) |

**Isolated verification.**
```
python3 -m pytest backend/tests/test_value_core_windows.py backend/tests/test_value_core_ranking.py backend/tests/test_value_core_deck.py -q
```
Only `types.py` from WP1 is needed.

**Docs:** none. WP5 owns them.

### 5.3 WP3 — Serving integration

**Owns:** see §2. Implements [lld.md §6, §7 and §9](lld.md#9-integration-edits-in-existing-files) **exactly**, including the anchor-quoted insertion points. No other edits to `server.py`.

**Acceptance criteria.**
1. **Flag off: zero behavior change.** The existing `backend/tests/test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden` (`:184`) and the full suite pass unchanged. `backend.value_core` is never imported on the flag-off path.
2. **Flag on, tester (or `vc_testers_only = 0`):**
   - organic, pinned and opponent-scoped jobs are served by the value core;
   - `trade_intent` jobs, `league_demo` and preparation jobs are served by the legacy engine;
   - `prepared_trade_runtime.supported()` is False.
3. Value-core cards match lld §7.2: prefix `vc_`, `basis="consensus"`, `preserve_server_order`, `reasons`, the value bar fields.
4. Every served card has a `deck_impressions` row carrying the §7.3 evidence and the `model_arm`/`policy_variant`/`policy_version` values.
5. `trades_generated` carries `engine_version="value_core"`.
6. The 14 `vc_*` keys are seeded (12 at build, plus `vc_gain_band` and `vc_throwin_min_ratio` on 2026-10-01, §3.1), and none is in `trade_service._DEFAULT_CFG`, so `test_bakeoff_arm_a_golden.py:897` is untouched and passing.
   - The owner request hash ignores `vc_*` keys (lld §9.1e), so owner experiment units are not reshuffled on deploy.
7. `code-walk.md` is written with real post-edit file:line citations covering the three items in scope §3.

**`vc_stubs` fixture** (in `test_value_core_serving.py`). It stubs WP1 and WP2 so the serving plumbing is testable before they land. It keeps stubbing after integration, so these tests stay pure plumbing tests.
```python
@pytest.fixture
def vc_stubs(monkeypatch):
    import importlib, sys, types as _t
    try:
        win = importlib.import_module("backend.value_core.windows")
    except ImportError:
        win = _t.ModuleType("backend.value_core.windows")
        monkeypatch.setitem(sys.modules, "backend.value_core.windows", win)
    monkeypatch.setattr(win, "infer_windows", lambda **kw: {}, raising=False)
    from backend.value_core import pipeline
    def fake_run(snapshot, request, core_cfg, rank_cfg, **kw):
        # one entry: viewer gives its highest-market asset for the first partner's highest one
        ...  # builds FairTrade/Scores/ScoredTrade/DeckEntry from snapshot, reasons=("Fair on value",)
    monkeypatch.setattr(pipeline, "run", fake_run)
```

**Tests: `backend/tests/test_value_core_adapter.py`.** Isolated: this needs only `types.py`, `trade_service` and `ranking_service`.

| Test | Asserts |
|---|---|
| `test_core_config_defaults_and_clamps` | `{}` → `CoreConfig()`; `{"vc_band": 5}` → `band == 0.5`; `{"vc_max_assets_per_side": 3.7}` → 4; `{"asset_floor_abs": 600}` → 600.0 |
| `test_rank_config_zero_weights_equalize` | all three weights 0 → (1, 1, 1); a negative weight → 0 |
| `test_tier_values` | `tier_values("1qb_ppr") == approx((elo_to_value(1580), elo_to_value(1927)))`, read from `tier_config.json` bands |
| `test_build_snapshot_raw_market_no_age_pref` | Player age 21, seed 1650 → `market == elo_to_value(1650)` (≈ 2117.0, **not** ×1.10) |
| `test_build_snapshot_other_players` | K and DL roster ids are counted in `other_players`, not in `asset_ids` |
| `test_build_snapshot_picks` | a `PICK` Player with seed Elo gives `kind == "pick"`, `age is None`, `market == elo_to_value(seed)` |
| `test_build_snapshot_default_sf_lineup` | `lineup_slots=None`, `sf_tep` → `DEFAULT_LINEUP + ("SUPER_FLEX",)` |
| `test_build_request_shrink` | user Elo 1700, seed 1600, n = 4 → `board.values[pid] == approx(elo_to_value(1650))`; `comparisons[pid] == 4` |
| `test_build_request_no_board` | `user_elo={}` → `board is None` |
| `test_build_request_filters_ids` | untouchable/pin ids not in the snapshot are dropped; `pinned_give_mode="bogus"` → `"any"` |
| `test_to_trade_cards_shape` | a hand-built `PipelineResult` with 2 entries gives 2 `TradeCard`s: `trade_id` starts `vc_`, `basis == "consensus"`, `preserve_server_order is True`, `composite_score == priority`, `give_value`/`receive_value` equal the market sums, the evidence map is keyed by `id(card)` |
| `test_evidence_schema_v1` | the evidence dict has exactly the top-level keys in lld §7.3; `json.dumps` round-trips; `core.ratio_floor == approx(1/1.2)` (band 0.20), `core.ratio_ceiling == approx(1.1)` and `core.gain_band == approx(0.10)` (the asymmetric band) |
| `test_payload_via_trade_card_to_dict` | `backend.server.trade_card_to_dict(card, players)` has `preserve_server_order: True`, `favors`/`gap` keys, and no `lane`. `reasons` is present when `FLAGS.trade_math_human_explanations` is monkeypatched on |
| `test_partner_board_from_no_evidence_stays_at_consensus` | a published Elo of 1900 with no comparisons prices at `elo_to_value(seed)`; with 6 votes it prices higher; empty Elo → `None` |
| `test_build_snapshot_keeps_partner_boards_for_known_partners_and_assets` | of boards for `opp`, the viewer `me` and an unknown `stranger`, only `opp` survives, cut to known asset ids; a snapshot built without `partner_boards` has `{}` |
| `test_core_config_reads_throwin_ratio` | `{}` → 2.0; `vc_throwin_min_ratio` 0.5 → 1.0 (clamp); 3 → 3.0 |

**Tests: `backend/tests/test_value_core_serving.py`.** These use `backend/tests/support/bakeoff_harness.run_capture(extra_patches=...)` (`bakeoff_harness.py:135`) plus `vc_stubs`. Every flag-on test must patch three network touches:
- `server._value_core_standings` → `({}, 0)`;
- `server._league_lineup_slots` → `None`;
- `server._sleeper_roster_limit` → `None`.

| Test | Asserts |
|---|---|
| `test_flag_registered_default_off_and_mirrored` | `"trade.value_core" in FLAG_KEYS`; `config/features.json` and `fixtures/flags/release.json` both hold `false` |
| `test_model_config_defaults_seeded_not_in_default_cfg` | 14 `vc_*` keys in `database._MODEL_CONFIG_DEFAULTS` with the lld §3 defaults; none in `trade_service._DEFAULT_CFG` |
| `test_flag_off_never_imports_value_core` | purge `backend.value_core*` from `sys.modules`; run `run_capture()` with the flag off → still not imported; `capture["status"] == "complete"` |
| `test_flag_on_serves_value_core` | patch `server._value_core_enabled → True` and `_trade_service_mod._cfg["vc_testers_only"] = 0.0`. Every card in the job has `trade_id` starting `vc_` and `preserve_server_order`. `deck_impressions` rows have `model_arm == "value_core"` and `policy_variant == "value_core"`; `json.loads(valuation_json)["generator"] == "value_core"`. `job["final_checks_pending"] is False` |
| `test_testers_only_gate` | flag on, `vc_testers_only = 1`, `_load_tester_allowlist → set()` → legacy path (no `vc_` cards); `→ {"user_me"}` → value-core path |
| `test_trade_intent_stays_legacy` | flag on and `run_capture(trade_intent="consolidate")` → no `vc_` cards |
| `test_prepared_inventory_unsupported_when_on` | `prepared_trade_runtime.supported(server, "L")` is False when `_value_core_enabled` is True; the pre-existing value when False |
| `test_safety_signature_entry` | `"value_core" in _trade_safety_signature()` iff the flag is on |
| `test_owner_request_hash_ignores_vc_keys` | build the same owner context twice, once with the 14 `vc_*` defaults added to `context["config"]` → `_owner_selected_assignment(...)["request_hash"]` is identical |
| `test_standings_failure_non_fatal` | `outlook.build_league_state` raises → `_value_core_standings(...) == ({}, 0)` and a warning is logged |
| `test_pipeline_error_falls_back_to_legacy` | `pipeline.run` raises → the error is logged, `job["status"] == "complete"`, cards come from the legacy engine (no `vc_` ids, no `value_core` impression rows). Revised 2026-10-01 (PRD Q1) |
| `test_fallback_matches_flag_off_output` | the fallback capture equals the flag-off capture, except for the `safety_policy` job key the flag adds |
| `test_trades_generated_engine_version` | patch `server.record_event` → called once with `props["engine_version"] == "value_core"` |

**Isolated verification.**
```
python3 -m pytest backend/tests/test_value_core_adapter.py backend/tests/test_value_core_serving.py backend/tests/test_bakeoff_serving.py backend/tests/test_seed_ui_test_db.py backend/tests/test_entitlements.py backend/tests/test_bakeoff_arm_a_golden.py -q
```

**Docs:** `docs/plans/value-core-engine/code-walk.md` only. WP5 writes the reference docs.

### 5.4 WP4 — Eval bench

**Owns:** see §2. Implements [lld.md §8](lld.md#8-eval-bench) exactly: CLI flags, file modes, the frozen schema and the guardrail definitions.

**Acceptance criteria.**
1. `freeze` only reads prod through the read-only connection, and asserts `transaction_read_only = on`. It refuses to overwrite and writes 0600. Its stdout carries no user ids.
2. `run` computes the five guardrails exactly as in lld §8.2, and writes `results.json` and `cards-<variant>.json` into a new 0600 directory.
3. `value_core_recall` builds cases only from the committed fixtures, and reports exact and close recall@10, the in-pool rate, reject reasons and the band calibration.
4. `blind_grade export` hides the source (no variant name appears anywhere in the CSV), dedupes identical trades across variants, and writes a private key. `import` validates the grades and tags.
5. No test touches the network or prod.

**Tests: `backend/tests/test_value_core_bench.py`.**

| Test | Asserts |
|---|---|
| `test_guardrails_exact_numbers` | Hand-built 4 entries: (g 1000, r 1000, starter); (g 1000, r 1300, best_in 1600); (g 1200, r 1000, no starter, best_in 1000); (g 1000, r 950, starter). Asset `x` is given in the first three. Results: `insult_rate == 0.25`, `real_piece_back_share == 0.75`, `median_value_given == approx(-0.025)`, `max_asset_appearances == 3` (reported only), `max_acquired_appearances == 1`, `near_duplicates == 0`, `acquisition_repeats == 0`, `max_partner_cards == 3`, `pass["insult"] is False` and every other pass flag true |
| `test_guardrails_count_near_duplicates_and_repeat_acquisitions` | P: x → (b1, m1), x → (b1, m2) (a near-duplicate: same headliners, throw-ins differ), z → b1 (a repeat acquisition); Q: y → c1 → `near_duplicates == 1`, `acquisition_repeats == 2`, `pass["near_duplicates"] is False` |
| `test_guardrails_top_window_only` | 40 entries → only the first 30 are counted (`cards == 30`) |
| `test_synthetic_league_valid_and_deterministic` | `synthetic_league(7)` equals `synthetic_league(7)`; 12 teams; every team's `asset_ids` exist in `assets`; the schema keys match lld §8.1 |
| `test_snapshot_for_seat_shrinks_board` | frozen board Elo 1700, seed 1600, n = 4 → personal `elo_to_value(1650)` |
| `test_run_verdict_with_stub_engine` | a stub engine returning entries where one received asset appears 4 times in the first 30 → `worst_seat_acquired_appearances == 4`, `verdict == "FAIL"`; a clean stub → `"PASS"` |
| `test_league_record_pure_transform` | canned rows → the record has the exact keys and values: `max_players` = slots + reserve + taxi; top 6 picks per owner; boards joined by `user_id` |
| `test_assert_read_only` | a fake connection returning `"off"` raises `ValueError`; `"on"` passes |
| `test_outputs_private_and_fresh` | the output directory already exists → error; the written files have mode `0o600` |

**Tests: `backend/tests/test_value_core_recall.py`.**

| Test | Asserts |
|---|---|
| `test_is_close` | real give (`h` 3000, `a` 800), receive (`c` 3500); card give (`h`,), receive (`c`,) → close; card give (`a`,) → not close (headliner missing) |
| `test_band_calibration` | `[0.0, 0.05, 0.1, 0.2, 0.3]` → p50 0.1, p80 0.2, p90 0.3, `recommended_band == 0.22` |
| `test_cases_from_fixtures_ffv3_2024` | `only={("ffv3", 2024)}`: `skipped["offseason_leg"] == 21`; ≤ 9 cases; each case has non-empty `a_gives`/`b_gives`, all present on the pre-trade roster of its side, all priced |
| `test_run_recall_stub_pipeline` | a stub pipeline that ranks the real trade 3rd → `exact_at_k == 1.0` for that orientation; `per_case[...]["rank_exact"] == 3` |

**Tests: `backend/tests/test_blind_grade.py`.**

| Test | Asserts |
|---|---|
| `test_export_samples_and_hides_source` | two card sets of 50 → 80 rows when there are no duplicates. The CSV text contains neither variant name. The key covers every `card_id`. Ids run `c01`… Deterministic for a fixed seed |
| `test_export_dedupes_across_variants` | the same trade in both sets → one row, whose key `variants == ["A", "B"]` |
| `test_import_scores` | a sheet with grades gives per-variant `mean`, `share_ge_4` and `tag_counts`; a shared card is credited to both variants |
| `test_import_rejects_bad_values` | grade 6 → `ValueError` naming the card; tag `"meh"` → `ValueError` |
| `test_private_files` | the sheet and key have mode `0o600`; an existing output directory raises |

**Tests: `backend/tests/test_value_core_e2e.py`.** These are **integration-only**: they fail until WP1–WP3 land, and are excluded from WP4's isolated run.

| Test | Asserts |
|---|---|
| `test_pipeline_on_synthetic_league` | `value_core_bench.run(synthetic_league frozen, variants={"default": {}})` with the real engine, twice. The two results are equal once `elapsed_ms` is stripped; there are 12 seats and at least one has a fair pool of ≥ 90 cards. Total elapsed < 60 s (a loose CI bound; latency is checked in §6) |
| `test_deck_cap_breaks_only_when_nothing_else_fits` | for every seat of `synthetic_league(7)`, a card inside the first 30 may exceed `player_cap` only when no cap-respecting card is left. A big pool does not make the cap feasible: the viewer has at most `vc_max_assets_per_side` tradeable assets, and multi-piece gives spend several appearances at once |
| `test_run_trade_job_flag_on_real_engine` | `bakeoff_harness.run_capture` with patches: `_value_core_enabled → True`, `vc_testers_only = 0`, `_league_lineup_slots → ["QB"]`, `_sleeper_roster_limit → None`, `_value_core_standings → ({}, 0)`. The job completes with ≥ 1 card, where the harness fair pair `rb1 ↔ rb3 + wr3` is present. Every card's `trade_id` starts `vc_`. Every `deck_impressions` row has `model_arm == "value_core"`, and its `valuation_json` has `scores` and `weights` |
| `test_evaluate_trade_matches_pool_on_synthetic` | for 50 pool trades, `core.evaluate_trade` agrees |

**Isolated verification.**
```
python3 -m pytest backend/tests/test_value_core_bench.py backend/tests/test_value_core_recall.py backend/tests/test_blind_grade.py -q
```
Recall cases take their lineup slots from the fixture's own `league.roster_positions`, so they have no WP3 dependency. `league_record` imports `adapter.default_lineup_slots` lazily, and only for non-Sleeper leagues. Its unit test uses Sleeper meta.

**Docs:** none. WP5 writes the runbook section from lld §8.

### 5.5 WP5 — Reference docs

**Owns:** see §2. Write from hld/lld/scope, describing the system "as if it had always been that way" (`docs/CLAUDE.md`). Leave a `<!-- verify after WP3 merge: line refs -->` marker wherever a line number depends on WP3's edits.

| File | Content |
|---|---|
| `docs/config-reference.md` | **Flag:** a `trade.value_core` row with its description and rollback, near the trade flag sections (`:249`–`:337`), plus the TOC (`:80-152`). **Knobs:** a `### Value core (trade.value_core)` subsection under `## model_config keys` (`:733`) with all 14 `vc_*` keys (defaults, clamps, where read), a list of the reused keys, and the rollout lever `vc_testers_only` |
| `docs/api-reference.md` | Under `### Trade card object` (`:440`), a "Value-core cards" paragraph (lld §7.2 payload). Add a note on the `/api/trades/generate` row (`:357`): engine selection, and intent jobs stay legacy. No route changes |
| `docs/data-dictionary.md` | `## deck_impressions` (`:490`): the value-core row values (`model_arm`/`policy_variant = "value_core"`, `policy_version = "value-core-1"`, `arm_rank`, `fairness_threshold = ratio floor`) and the `valuation_json` schema v1 (lld §7.3). Analytics list (`:1357`): `trades_generated.engine_version` gains `"value_core"` |
| `docs/architecture.md` | New section "Value-core engine" before `## Data flow` (`:258`), summarising hld §1–§4. A Components/Backend table row (`:376`) for `backend/value_core/` and the three eval tools |
| `docs/glossary.md` | The terms from scope §4 (value core, fair pool, fairness band (value core), stud premium, irreducible trade, priority, value score, outlook score, rank score, repeat penalty, bench guardrails, blind grade), in the file's bold-term style. Also update the stale `**Model arm**` entry (`:60`) to note that `value_core` is recorded in `model_arm` but is **not** a bake-off arm |
| `docs/runbook.md` | New `## Value-core bench (freeze / run / recall / blind grade)` covering the four CLIs (lld §8), private output handling, reading the verdict, and the kill switch steps (PRD §7) |
| `docs/adr/adr-024-value-core-engine.md` | **Context:** D-180, the prod findings and the operator's 2026-09-30 decision. **Decision:** a value-only core plus a 3-weight ranking; one branch point bypasses the legacy gate stack; no silent fallback; flag plus tester lever. **Alternatives:** patch v2/v3/bilateral, or a hybrid (plan step 5). **Consequences** |
| `living-memory/HLD.md` | Major Components (`:80-99`): a value-core row. Key Flows (`:140`): a "Flow C′ — value-core deck" paragraph. Keep the TOC in sync (`FORMAT.md`) |
| `living-memory/LLD.md` | A new H2 "Value-core engine seams" with the leaf rules, the lazy import, the single branch point, the evidence-on-every-row rule, and no fallback. TOC updated |

**Verification.**
- Links resolve: run `python3 - <<EOF` with a quick relative-link existence check over the edited files.
- The living-memory TOC matches its H2s. Run the `living-memory-format-check` skill if available.

---

## 6. Integration checklist (lead)

Run on `feat/value-core-engine` after all five packages have merged, from the worktree root with Python 3.12.

1. **Contract intact.** `git diff <contract-commit> -- backend/value_core/types.py` is empty, or matches the §3.1 log.
2. **Imports and leaf rules.**
   - `python3 -c "import backend.value_core.core, backend.value_core.ranking, backend.value_core.deck, backend.value_core.windows, backend.value_core.pipeline, backend.value_core.adapter, backend.eval.value_core_bench, backend.eval.value_core_recall, backend.eval.blind_grade"`.
   - `git grep -n "backend.server\|from \.\.server\|from \. import server" -- backend/value_core backend/eval/value_core_bench.py backend/eval/value_core_recall.py backend/eval/blind_grade.py` must return nothing.
3. **Full suite.** `python3 -m pytest backend/tests -q` is green, including:
   - `test_value_core_e2e.py`;
   - `test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden`;
   - `test_bakeoff_arm_a_golden.py`;
   - `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`;
   - `test_entitlements.py::test_features_json_keys_known`.
4. **Flag-off byte identity beyond the golden.** In a scratch dir, run `backend/tests/support/bakeoff_harness.run_capture()` with `PYTHONHASHSEED=0` at `3bb981ed` (a temporary worktree) and on the branch, both with default flags. Compare the canonical capture dicts; the harness already strips uuids and timestamps.
   - First run `3bb981ed` twice, to prove the harness is deterministic.
   - If any key differs between base and branch, stop: that is a flag-off regression.
5. **Flag-on smoke on a fixture league.**
   - `python3 -m backend.eval.value_core_bench run --frozen <tmp>/synthetic.json --output <tmp>/run1`, where `synthetic.json` is written from `value_core_bench.synthetic_league(7)` by a one-line script.
   - Check that the verdict line prints, that `worst_seat_acquired_appearances <= 3` and that `worst_seat_near_duplicates == 0`.
   - Record the pooled numbers in TEST_LEDGER. Synthetic numbers are a smoke check, **not** the bench verdict.
6. **Latency.** Time `pipeline.run` on the 14-team perf fixture from WP1. Record p50/p95 over 10 runs; the target is p95 < 8 s locally.
7. **Recall baseline.** Run `python3 -m backend.eval.value_core_recall --fixtures backend/tests/fixtures --output <tmp>/recall`. Record the case count, exact and close recall@10, the in-pool rate and `recommended_band`. Do **not** change `vc_band` without the operator.
8. **Code-walk.** Read `docs/plans/value-core-engine/code-walk.md`. Spot-check three citations against the code, and resolve WP5's `verify after WP3 merge` markers.
9. **CI.** Push the branch (not `main`) and confirm `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` are green. Mobile is untouched, so the last two are regressions only.
10. **Operator hand-off, before any flag flip.**
    - Surface the scope §3 structural-guard waiver.
    - Ask PRD open questions Q1–Q6.
    - Ask the operator to run `value_core_bench freeze` on the five bench leagues. The credentials are in `secrets.local.env`, and it is a prod read.
      Done 2026-10-01: six leagues (two 2026 leagues share the name "Bush League"; both are frozen), 77 teams, 10 boards.
    - Run the bench and the blind-grade export.

## 7. Docs matrix

| Doc | Trigger (CLAUDE.md) | Package |
|---|---|---|
| `docs/config-reference.md` | new flag + 14 `model_config` keys | WP5 |
| `docs/api-reference.md` | card payload contract (additive); generate route note | WP5 |
| `docs/data-dictionary.md` | new `valuation_json` shape / column values; `trades_generated` prop value | WP5 |
| `docs/architecture.md` + `living-memory/HLD.md` | new backend package and data flow | WP5 |
| `living-memory/LLD.md` | new seam conventions (leaf package, single branch, evidence rows) | WP5 |
| `docs/glossary.md` | new domain terms | WP5 |
| `docs/runbook.md` | new operator tooling | WP5 |
| `docs/adr/adr-024-value-core-engine.md` | non-obvious architectural decision | WP5 |
| `docs/cross-client-invariants.md` | — n/a: no client-shared constant changes | — |
| `docs/plans/value-core-engine/code-walk.md` | scope §3 evidence | WP3 |
| `living-memory/DECISIONS.md` (D-196), `CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md`/`HANDOFF.md` | session write-back | **lead** |
| `docs/plans/README.md` row for `value-core-engine/` | `docs/plans/CLAUDE.md` "add the README row" | **lead** |

## 8. Lead-only items

- Add the `docs/plans/README.md` status row for `value-core-engine/`. `docs/plans/CLAUDE.md` requires it in the session that created the folder, but this spec author was restricted to writing inside this folder.
- Add **D-196** to `living-memory/DECISIONS.md`: the 2026-09-30 rebuild decision; flag-on decks supersede the D-193 ordering. First grep for the maximum D-id.
- Update `living-memory/TEST_LEDGER.md` with the §6 results, and `CHANGELOG.md` on merge. Update NEXT/HANDOFF as work moves.
- **Optional.** Add a one-line `backend/value_core/` entry to `backend/CLAUDE.md` §Subpackages. That is an operating-contract file, so it is the lead's call.
- **Decide with the operator:**
  - PRD Q1–Q6;
  - whether the parallel `backend/eval/deck_scoreboard.py` (uncommitted, in `.claude/worktrees/trade-quality-scoreboard`) lands, and whether its "giving too much" threshold (< 0.95 return) should be reported next to this bench's median-value-given guardrail.
