"""Team Review — the six-beat guided read of the caller's own team.

Feedback #357 / #358 / #359 (tester `jonbonjourvi`, v1.15.0). Design and
contract: `docs/feedback/items/357-team-review/` (scope / hld-delta /
lld-delta / prd). Operator framing 2026-08-19: a **Team Review button inside
the find-a-trade experience**, **analyst-guided** rather than a static
dashboard, built from **valuations and features that already exist**, with two
jobs — help the user *set their trade preferences*, and *determine team
strategy*.

THIS MODULE COMPUTES NOTHING NEW, AND THAT IS THE POINT.
--------------------------------------------------------
It is a pure composer over five things that already ship:

    power_rankings.compute_power_rankings   value rank, positional split
    power_rankings.optimal_starter_slots    the weakest starting slot
    trade_service.infer_team_outlook        the contend/rebuild window
    trade_service.analyze_roster_strengths  tier_depth / needs / surplus
    trends_service.compute_consensus_gap    board-vs-market divergence

No new model means no new calibration, and therefore no new way to be wrong.
Every number this surface shows is already shown somewhere else in the app
under exactly the same definition. If you find yourself adding arithmetic
here, that is the signal to stop: a second source of truth for a number the
League tab also renders is the failure mode this design exists to avoid.

THE FLOW'S EXIT IS A CONFIGURED DECK, NOT A REPORT.
---------------------------------------------------
Four of the six beats offer an action, and those actions write the
`league_preferences` fields the trade engine ALREADY reads (`team_outlook`,
`acquire_positions`, `trade_away_positions`) through the EXISTING
`POST /api/league/preferences`. This module is read-only; it returns the
current stored values alongside each finding so the client can render its
controls pre-selected.

Pure: no DB, no HTTP, no Flask. Everything is passed in, mirroring
`compute_power_rankings`.
"""

from __future__ import annotations

from typing import Any, Callable

# Beat order is a cross-client encoding: the analytics `beat` property and the
# `team-review.beat.<id>` testIDs both bind to these exact strings, and the
# client renders `beats` minus `beats_skipped` in this order rather than
# deciding for itself that a beat is empty.
BEATS: tuple[str, ...] = (
    "standing", "window", "depth", "divergence", "partners", "plan",
)

# The five declarable outlooks. `infer_team_outlook` deliberately never infers
# the two extremes — inference confidence does not justify alpha = 1.00 / 0.10 —
# so `window.inferred` is only ever contender | rebuilder | not_sure, while
# `window.options` carries all five because a user may DECLARE an extreme.
OUTLOOK_OPTIONS: tuple[str, ...] = (
    "championship", "contender", "rebuilder", "jets", "not_sure",
)

CORE_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

# Caps. Small on purpose: a beat is one finding, and a list of ten is a
# dashboard again.
MAX_DIVERGENCE_ROWS = 5
MAX_PARTNER_ROWS = 3

# Minimum interactions before the divergence beat is trustworthy. This is the
# RANKING SERVICE'S OWN BAR (`RankingService.POSITION_THRESHOLDS[None]`), not a
# number invented here — see `_divergence` for why a count of `user_elo` keys
# is the wrong test entirely.
BOARD_INTERACTION_BAR = 16


def _pos_share(teams: list[dict], me: dict) -> list[dict]:
    """Per-position value + share of the caller's roster, with the caller's
    LEAGUE rank at that position. The rank is what makes "you're 3rd at WR but
    11th at TE" sayable, and it is the reason this walks every team rather
    than just the caller's."""
    def by_pos(team: dict) -> dict[str, float]:
        out = {p: 0.0 for p in CORE_POSITIONS}
        for grp in (team.get("roster") or []):
            pos = grp.get("position")
            if pos in out:
                out[pos] += float(grp.get("value") or 0.0)
        return out

    mine = by_pos(me)
    everyone = [(t["user_id"], by_pos(t)) for t in teams]
    total = sum(mine.values()) or 1.0

    rows = []
    for pos in CORE_POSITIONS:
        ordered = sorted(everyone, key=lambda kv: kv[1][pos], reverse=True)
        rank = next(
            (i + 1 for i, (uid, _) in enumerate(ordered) if uid == me["user_id"]),
            None,
        )
        rows.append({
            "position": pos,
            "value": round(mine[pos], 1),
            "share": round(mine[pos] / total, 4),
            "rank": rank,
        })
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def _standing(teams: list[dict], me: dict, scoring: dict | None) -> dict:
    ordered = sorted(teams, key=lambda t: float(t.get("value") or 0.0), reverse=True)
    rank = next(
        (i + 1 for i, t in enumerate(ordered) if t["user_id"] == me["user_id"]),
        None,
    )
    return {
        "value_rank": rank,
        "value_total": len(teams),
        "roster_value": round(float(me.get("value") or 0.0), 1),
        "position_value": _pos_share(teams, me),
        # `scoring` is retrospective FACT (points actually scored), never a
        # projection — and it is None in preseason and on non-Sleeper leagues.
        # The client names the actual reason rather than hiding the row.
        "scoring": scoring,
    }


def _window(inferred: str, signals: dict, declared: str | None,
            num_teams: int) -> dict:
    return {
        "inferred": inferred,
        "declared": declared,
        "signals": {
            "vet_share": round(float(signals.get("vet_share") or 0.0), 4),
            "youth_share": round(float(signals.get("youth_share") or 0.0), 4),
            "pick_share": round(float(signals.get("pick_share") or 0.0), 4),
            # Shipped explicitly rather than left as 1/num_teams for the client
            # to re-derive: it is the centring constant `infer_team_outlook`
            # actually uses, and a client that re-derives it drifts the day the
            # centring changes. Same rule as tier bands and outlook bands — a
            # client reads an encoding, it never recomputes one.
            "equal_pick_share": round(1.0 / max(num_teams, 1), 4),
            "score": round(float(signals.get("score") or 0.0), 4),
        },
        # #365 — the inference MODEL alongside its inputs, so the beat can show
        # the user every number that produced the verdict: the two age
        # thresholds, the three weights, and the two cuts `score` is bucketed
        # against. Passed straight through from `infer_team_outlook` rather
        # than restated here, for the same reason `equal_pick_share` is.
        "model": dict(signals.get("model") or {}),
        "options": list(OUTLOOK_OPTIONS),
    }


def _depth(profile: dict, weakest_slot: dict | None,
           acquire: list[str], shed: list[str]) -> dict:
    out = {
        # `tier_depth` is computed by analyze_roster_strengths on every trade
        # job today and surfaced NOWHERE. This beat is its first consumer — it
        # is the "you're missing depth" finding, stated as elite/starter/bench
        # counts rather than as two hardcoded player names.
        "tier_depth": profile.get("tier_depth") or {},
        "position_needs": list(profile.get("position_needs") or []),
        "position_surplus": list(profile.get("position_surplus") or []),
        "weakest_slot": weakest_slot,
        "acquire_positions": list(acquire or []),
        "trade_away_positions": list(shed or []),
    }
    # #366 — both keys are PASSED THROUGH from the profile, never recomputed
    # here, and both are present only when their flag put them there. Same rule
    # as `equal_pick_share` on the window beat and the tier bands generally: a
    # client reads an encoding, it never derives one, and this module computes
    # nothing new (see the module docstring — that is the whole design).
    #
    #   tier_basis   which banding actually ran, per position (flag
    #                `trade.position_tiers`). Reported rather than inferred so
    #                a fixture-sized pool falling back to the absolute cuts is
    #                visible instead of silent.
    #   handcuff_rb  how many of the roster's RBs are the RB2 on their NFL
    #                depth chart (flag `trade.rb_handcuff`). Absent, not zero,
    #                when the flag is off — "we did not look" and "we looked
    #                and found none" are different claims and the card says so.
    if "tier_basis" in profile:
        out["tier_basis"] = dict(profile.get("tier_basis") or {})
    if "handcuff_rb" in profile:
        out["handcuff_rb"] = int(profile.get("handcuff_rb") or 0)
    return out


def _divergence(
    *,
    user_elo: dict[str, float] | None,
    board_interactions: int,
    judged_ids: set[str],
    seed_elo: dict[str, float],
    community_gap: dict | None,
    user_roster: set[str],
    players: dict,
    pos_rank_of: Callable[[str], int | None] | None,
) -> dict:
    """Where the caller's board disagrees with the market.

    THE TRAP THIS FUNCTION EXISTS TO AVOID — read before editing.

    `user_elo` is NOT a list of players the user has ranked.
    `RankingService.get_rankings(position=None)` calls `_pool(None)`, which is
    documented as returning *"ALL players for a position (unfiltered)"*, and
    assigns an Elo to every one of them. A user who has never made a single
    comparison still gets a full-pool map, every entry sitting at the seed.

    Two consequences, both load-bearing:

      * Any gate of the form `len(user_elo) < N` NEVER FIRES. The real bar is
        the ranking service's own: `interaction_count >= 16`
        (`POSITION_THRESHOLDS[None]`), passed in as `board_interactions`.
      * A player the user has never judged has a structurally ZERO gap,
        because his board Elo *is* the seed. Including him pads both lists
        with non-opinions. `judged_ids` (wins + losses > 0) is the filter.

    FIELD CONVENTION (both source ladders, #367). `higher_than_market` is
    where YOUR board sits above the market on a player you do NOT own — your
    buy list, because you would be paying less than you think he is worth.
    `lower_than_market` is where the market sits above your board on a player
    you DO own — your sell list, because someone pays you more than he is
    worth to you. `gap` is a POSITIVE edge magnitude on both sides.

    Source ladder: the league-community comparison when >= 3 other members
    have ranked (`compute_consensus_gap` says so via `has_baseline`), else the
    universal consensus seed, else the beat is skipped by the caller.
    """
    empty = {
        "source": None, "baseline_user_count": 0,
        "board_judged_players": len(judged_ids),
        "board_interactions": board_interactions,
        "higher_than_market": [], "lower_than_market": [],
    }
    if not user_elo or board_interactions < BOARD_INTERACTION_BAR:
        return empty

    def enrich(pid: str, gap: float, comparison: float, on_roster: bool) -> dict:
        p = players.get(pid)
        return {
            "player_id": pid,
            "name": getattr(p, "name", None) or pid,
            "position": getattr(p, "position", None) or "?",
            "user_elo": round(float(user_elo.get(pid) or 0.0), 1),
            "comparison_elo": round(float(comparison), 1),
            "gap": round(float(gap), 1),
            "pos_rank": pos_rank_of(pid) if pos_rank_of else None,
            "on_roster": on_roster,
        }

    if community_gap and community_gap.get("has_baseline"):
        sells = [r for r in (community_gap.get("easiest_sells") or [])
                 if str(r.get("player_id")) in judged_ids]
        buys = [r for r in (community_gap.get("easiest_buys") or [])
                if str(r.get("player_id")) in judged_ids]
        return {
            "source": "league_community",
            "baseline_user_count": int(community_gap.get("baseline_user_count") or 0),
            "board_judged_players": len(judged_ids),
            "board_interactions": board_interactions,
            # #367 — the field names are literal, and the lists were crossed.
            # `easiest_buys` IS the set you are higher than the market on
            # (your board over the OWNER's, off your roster); `easiest_sells`
            # is the set you are lower on (the market over your board, on your
            # roster). Shipped the other way round, which is why the screen
            # offered your best buys under "Skip these".
            "higher_than_market": [
                enrich(str(r["player_id"]), float(r.get("gap") or 0.0),
                       float(r.get("owner_elo") or 0.0), False)
                for r in buys[:MAX_DIVERGENCE_ROWS]
            ],
            "lower_than_market": [
                enrich(str(r["player_id"]), float(r.get("gap") or 0.0),
                       float(r.get("community_elo") or 0.0), True)
                for r in sells[:MAX_DIVERGENCE_ROWS]
            ],
        }

    # Fallback: the caller's board vs the universal seed. Always available for
    # a judged player, and meaningful by construction — a board STARTS at the
    # seed and diverges as the user ranks, so this gap is exactly "how far you
    # have moved him from consensus".
    highs: list[dict] = []
    lows: list[dict] = []
    for pid in judged_ids:
        base = seed_elo.get(pid)
        if base is None:
            continue
        gap = float(user_elo.get(pid, base)) - float(base)
        if gap > 0 and pid not in user_roster:
            # Higher than the market on a player you do NOT own → buy him.
            highs.append(enrich(pid, gap, base, False))
        elif gap < 0 and pid in user_roster:
            # Lower than the market on a player you DO own → sell him. `gap`
            # is negated so both lists carry a positive edge magnitude, the
            # same convention compute_consensus_gap uses.
            lows.append(enrich(pid, -gap, base, True))
    highs.sort(key=lambda r: r["gap"], reverse=True)
    lows.sort(key=lambda r: r["gap"], reverse=True)
    return {
        "source": "consensus_seed",
        "baseline_user_count": 0,
        "board_judged_players": len(judged_ids),
        "board_interactions": board_interactions,
        "higher_than_market": highs[:MAX_DIVERGENCE_ROWS],
        "lower_than_market": lows[:MAX_DIVERGENCE_ROWS],
    }


_CONTENDING = ("contender", "championship")
_REBUILDING = ("rebuilder", "jets")


def _partners(
    *,
    teams: list[dict],
    me_user_id: str,
    my_window: str,
    member_windows: dict[str, str],
    member_profiles: dict[str, dict],
    my_needs: list[str],
    pick_share_by_owner: dict[str, float],
    first_round_by_owner: dict[str, int],
) -> dict:
    """Who to deal with. Two lists, and a member may legitimately appear in
    both — a league-mate pointed the opposite way who is ALSO deep exactly
    where you are thin is the single best partner in the league, and
    suppressing the second appearance would hide the strongest signal the
    beat can produce.

    `not_sure` members are excluded from `opposed_window` entirely. Inference
    that declined to commit must not be laundered into a recommendation.
    """
    rank_of = {t["user_id"]: i + 1 for i, t in enumerate(
        sorted(teams, key=lambda t: float(t.get("value") or 0.0), reverse=True))}
    name_of = {t["user_id"]: (t.get("username") or t.get("display_name") or "")
               for t in teams}

    if my_window in _CONTENDING:
        want = _REBUILDING
    elif my_window in _REBUILDING:
        want = _CONTENDING
    else:
        want = ()

    opposed = []
    for uid, w in member_windows.items():
        if uid == me_user_id or w == "not_sure" or w not in want:
            continue
        opposed.append({
            "user_id": uid,
            "username": name_of.get(uid, ""),
            "value_rank": rank_of.get(uid),
            "inferred_outlook": w,
            "pick_capital_share": round(float(pick_share_by_owner.get(uid, 0.0)), 4),
            "first_round_picks": int(first_round_by_owner.get(uid, 0)),
        })
    # A contender is shopping for the picks a rebuilder holds; a rebuilder is
    # shopping for the vets the best rosters hold. Sort accordingly.
    if my_window in _CONTENDING:
        opposed.sort(key=lambda r: r["pick_capital_share"], reverse=True)
    else:
        opposed.sort(key=lambda r: (r["value_rank"] is None, r["value_rank"]))

    fills = []
    need_set = set(my_needs or [])
    for uid, prof in member_profiles.items():
        if uid == me_user_id:
            continue
        for pos in (prof.get("position_surplus") or []):
            if pos not in need_set:
                continue
            td = (prof.get("tier_depth") or {}).get(pos) or {}
            fills.append({
                "user_id": uid,
                "username": name_of.get(uid, ""),
                "position": pos,
                "startable_count": int(td.get("elite", 0)) + int(td.get("starter", 0)),
            })
    fills.sort(key=lambda r: r["startable_count"], reverse=True)

    return {
        "opposed_window": opposed[:MAX_PARTNER_ROWS],
        "fills_your_need": fills[:MAX_PARTNER_ROWS],
    }


def build_team_review(
    *,
    teams: list[dict],
    you_user_id: str,
    num_teams: int,
    scoring_format: str,
    completed_weeks: int,
    scoring: dict | None,
    scoring_unavailable_reason: str | None,
    inferred_outlook: str,
    outlook_signals: dict,
    stored_prefs: dict,
    roster_profile: dict,
    member_profiles: dict[str, dict],
    member_windows: dict[str, str],
    weakest_slot: dict | None,
    user_elo: dict[str, float] | None,
    board_interactions: int,
    judged_ids: set[str],
    seed_elo: dict[str, float],
    community_gap: dict | None,
    user_roster: list[str],
    players: dict,
    pos_rank_of: Callable[[str], int | None] | None = None,
    pick_share_by_owner: dict[str, float] | None = None,
    first_round_by_owner: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the six beats. Returns the full payload including
    `meta.beats_skipped`, which is AUTHORITATIVE: the client renders
    `beats` minus `beats_skipped` in `beats` order and never decides for
    itself that a beat is empty, so analytics `beat` values and step indices
    stay consistent between client and server.
    """
    me = next((t for t in teams if t["user_id"] == you_user_id), None)
    if me is None:
        return {}

    prefs = stored_prefs or {}
    divergence = _divergence(
        user_elo=user_elo,
        board_interactions=board_interactions,
        judged_ids=judged_ids,
        seed_elo=seed_elo,
        community_gap=community_gap,
        user_roster=set(user_roster or []),
        players=players,
        pos_rank_of=pos_rank_of,
    )
    my_window = prefs.get("team_outlook") or inferred_outlook
    partners = _partners(
        teams=teams,
        me_user_id=you_user_id,
        my_window=my_window,
        member_windows=member_windows or {},
        member_profiles=member_profiles or {},
        my_needs=list(roster_profile.get("position_needs") or []),
        pick_share_by_owner=pick_share_by_owner or {},
        first_round_by_owner=first_round_by_owner or {},
    )

    skipped: list[str] = []
    if divergence["source"] is None:
        skipped.append("divergence")
    if len(teams) < 3:
        # Fewer than two OTHER members: there is nobody to deal with, so the
        # beat has no content. Not an error — a fact about the league.
        skipped.append("partners")

    return {
        "meta": {
            "num_teams": num_teams,
            "scoring_format": scoring_format,
            "completed_weeks": completed_weeks,
            "beats": list(BEATS),
            "beats_skipped": skipped,
            "scoring_available": scoring is not None,
            "scoring_unavailable_reason": scoring_unavailable_reason,
        },
        "standing": _standing(teams, me, scoring),
        "window": _window(inferred_outlook, outlook_signals or {},
                          prefs.get("team_outlook"), num_teams),
        "depth": _depth(roster_profile or {}, weakest_slot,
                        prefs.get("acquire_positions") or [],
                        prefs.get("trade_away_positions") or []),
        "divergence": divergence,
        "partners": partners,
    }
