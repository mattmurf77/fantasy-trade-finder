"""Shared recommendation significance, independent of arm fairness and scoring.

Only individual centerpieces qualify; summing small assets never creates one.
Callers supply frozen raw boards and trusted request context. This leaf performs
no database/provider/config reads and never changes a card, board, or ranking.
"""

from dataclasses import dataclass
import json
import math

from .pick_values import parse_generic_pick_id
from .ranking_service import ORDERED_TIERS, RankingService


VERSION = "significance-v1"
_POSITIONS = frozenset(("QB", "RB", "WR", "TE"))
_PERSONAL_SOURCES = frozenset(("explicit", "votes", "cross_format", "legacy"))


@dataclass(frozen=True)
class SignificanceResult:
    eligible: bool
    reason: str
    snapshot_json: str

    def as_dict(self):
        """Detached private diagnostic record, never another manager's board."""
        return json.loads(self.snapshot_json)


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _ids(value):
    return (isinstance(value, (list, tuple)) and bool(value)
            and all(isinstance(pid, str) and bool(pid) for pid in value))


def evaluate_significance(card, *, players, user_elo, seed_elo,
                          owned_pick_parser, is_pick_asset,
                          scoring_format="1qb_ppr", user_sources=None,
                          context="discovery", selected_give_ids=(),
                          selected_receive_ids=(), player_min_tier="second",
                          allow_first_round_pick=True):
    """Evaluate an exact viewer-oriented package, without limiting its size.

    ``context`` must come from the trusted caller, never a card payload.
    ``explicit_search`` exempts only a package retaining a selected asset on
    its intended side. ``inbound`` and ``manual`` are outside recommendation
    significance. All ordinary generated cards use ``discovery`` regardless
    of arm, card markers, or whether an opponent was selected.

    Raw board Elo determines tiers through the shared tier config, not the
    package's adjusted trade values. Missing personal entries fall back to
    consensus; with no provenance map, supplied entries are legacy personal.
    First-round picks qualify by validated identity and a finite positive
    consensus seed, never by a display label or summed pick values.
    """
    give = getattr(card, "give_player_ids", None)
    receive = getattr(card, "receive_player_ids", None)
    league_id = getattr(card, "league_id", "")
    valid_threshold = (isinstance(player_min_tier, str) and player_min_tier in ORDERED_TIERS
                       and type(allow_first_round_pick) is bool)
    thresholds = {"player_min_tier": player_min_tier if valid_threshold else None,
                  "allow_first_round_pick": allow_first_round_pick if valid_threshold else None,
                  "scoring_format": scoring_format}

    def finish(eligible, reason, centerpiece=None):
        record = {"version": VERSION, "eligible": eligible, "reason": reason,
                  "context": context, "thresholds": thresholds,
                  "centerpiece": centerpiece}
        return SignificanceResult(eligible, reason, json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False))

    if context in ("manual", "inbound"):
        return finish(True, "exempt_" + context)
    if context not in ("discovery", "explicit_search"):
        return finish(False, "invalid_context")
    if not _ids(give) or not _ids(receive):
        return finish(False, "invalid_package")
    if context == "explicit_search" and (
            set(give).intersection(selected_give_ids)
            or set(receive).intersection(selected_receive_ids)):
        return finish(True, "exempt_selected_asset")
    if not valid_threshold:
        return finish(False, "invalid_threshold")

    # Scan every asset before choosing: a later player centerpiece is more
    # explanatory than an earlier pick when both qualify. No value summation.
    candidates = []
    for side, ids in (("give", give), ("receive", receive)):
        for pid in ids:
            player = players.get(pid)
            if player is None:
                continue
            pos = getattr(player, "position", None)
            pseudo_pick = is_pick_asset(player)
            generic = parse_generic_pick_id(pid)
            owned = owned_pick_parser(pid, league_id)
            pick_identity = bool(generic or owned)
            if owned:
                tail = pid[len(league_id) + 1:].split("_", 2)
                if not (len(owned) == 2 and all(type(n) is int and n > 0 for n in owned)
                        and len(tail) == 3 and len(tail[0]) == 4 and bool(tail[2])):
                    owned = None
            if pseudo_pick:
                round_ = generic[0] if generic else owned[1] if owned else None
                market = seed_elo.get(pid)
                if (allow_first_round_pick and round_ == 1
                        and _finite(market) and market > 0):
                    candidates.append((1, {"asset_id": pid, "side": side,
                                            "kind": "pick", "source": "consensus",
                                            "round": round_}))
                continue
            # A pick-shaped identity with conflicting player metadata is not
            # a player, and unknown positions cannot earn a default RB tier.
            if pick_identity or pos not in _POSITIONS:
                continue
            floor = RankingService.tier_bands_for(pos, scoring_format)[player_min_tier][0]
            source = user_sources.get(pid) if user_sources is not None else "legacy"
            personal = user_elo.get(pid) if source in _PERSONAL_SOURCES else None
            for basis, elo in (("personal", personal), ("consensus", seed_elo.get(pid))):
                if _finite(elo) and elo >= floor:
                    candidates.append((0, {"asset_id": pid, "side": side,
                                            "kind": "player", "source": basis,
                                            "tier": RankingService.tier_for_elo(
                                                elo, pos, scoring_format),
                                            "threshold_elo": floor}))
                    break
    if candidates:
        _, centerpiece = min(candidates, key=lambda candidate: candidate[0])
        return finish(True, "meaningful_" + centerpiece["kind"], centerpiece)
    return finish(False, "no_meaningful_centerpiece")
