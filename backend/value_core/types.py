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
