"""Team Review composer (#357 / #358 / #359).

Contract: `docs/feedback/items/357-team-review/lld-delta.md` §3.

The load-bearing test here is `test_divergence_ignores_unjudged_players`. It
guards a trap that already bit this design once during planning: `user_elo` is
a FULL-POOL map (RankingService._pool returns every player unfiltered), so a
user who has ranked nothing still gets an entry for everyone, sitting at the
seed. Any gate written as `len(user_elo) < N` silently never fires, and any
list built without a judged filter fills with structurally-zero non-opinions.
"""

from __future__ import annotations

import pytest

from backend.team_review import (
    BEATS,
    BOARD_INTERACTION_BAR,
    OUTLOOK_OPTIONS,
    build_team_review,
)


class P:
    def __init__(self, pid, name, position, age=25):
        self.id, self.name, self.position, self.age = pid, name, position, age


def _players():
    out = {}
    for i in range(1, 40):
        pos = ["QB", "RB", "WR", "TE"][i % 4]
        out[f"p{i}"] = P(f"p{i}", f"Player {i}", pos)
    return out


def _teams(n=12):
    teams = []
    for t in range(1, n + 1):
        roster = [
            {"player_id": f"p{(t * 3 + k) % 39 + 1}",
             "position": ["QB", "RB", "WR", "TE"][k % 4],
             "value": float(3000 - t * 100 - k * 40)}
            for k in range(8)
        ]
        teams.append({
            "user_id": f"u{t}",
            "username": f"team{t}",
            "display_name": f"Team {t}",
            "value": float(sum(r["value"] for r in roster)),
            "roster": roster,
        })
    return teams


def _build(**over):
    teams = over.pop("teams", _teams())
    base = dict(
        teams=teams,
        you_user_id="u1",
        num_teams=len(teams),
        scoring_format="1qb_ppr",
        completed_weeks=0,
        scoring=None,
        scoring_unavailable_reason="preseason",
        inferred_outlook="contender",
        outlook_signals={"vet_share": 0.61, "youth_share": 0.12,
                         "pick_share": 0.05, "score": 0.31},
        stored_prefs={},
        roster_profile={"tier_depth": {"TE": {"elite": 0, "starter": 0, "bench": 1}},
                        "position_needs": ["TE"], "position_surplus": ["RB"]},
        member_profiles={},
        member_windows={},
        weakest_slot=None,
        user_elo=None,
        board_interactions=0,
        judged_ids=set(),
        seed_elo={},
        community_gap=None,
        user_roster=[],
        players=_players(),
    )
    base.update(over)
    return build_team_review(**base)


# ---------------------------------------------------------------------------
# The trap
# ---------------------------------------------------------------------------

def test_divergence_ignores_unjudged_players():
    """A full-pool `user_elo` with only TWO judged players must produce at most
    those two rows.

    The unjudged players here carry a SMALL NONZERO drift rather than an exact
    zero, and that is the whole point of the fixture: `RankingService._compute_elo`
    recomputes over the entire pool, so ranking one player nudges everyone
    else's rating slightly. With an exact-zero fixture this test passes even
    with the judged filter deleted — the `gap > 0` / `gap < 0` sign checks
    exclude untouched players on their own — and it would prove nothing. The
    drift is what makes the filter load-bearing, and it is what the real
    ranking service produces."""
    seed = {f"p{i}": 1500.0 for i in range(1, 40)}
    user = dict(seed)
    user["p1"] = 1700.0      # judged, genuinely high
    user["p2"] = 1300.0      # judged, genuinely low
    # Pool-wide recompute drift on players the user never compared.
    for i in range(3, 40):
        user[f"p{i}"] = 1500.0 + (2.5 if i % 2 else -2.5)
    out = _build(
        user_elo=user,
        seed_elo=seed,
        judged_ids={"p1", "p2"},
        board_interactions=BOARD_INTERACTION_BAR,
        # p1 is high and NOT owned (a buy); p2 is low and owned (a sell).
        # Under #367's corrected rule this is what makes both lists non-empty,
        # which is what keeps the leak assertion below meaningful.
        user_roster=["p2", "p3", "p5", "p7"],
    )
    d = out["divergence"]
    assert d["source"] == "consensus_seed"
    assert d["higher_than_market"] and d["lower_than_market"], (
        "both lists must carry a row or the leak assertion below is vacuous")
    ids = {r["player_id"] for r in d["higher_than_market"]} | {
        r["player_id"] for r in d["lower_than_market"]}
    leaked = ids - {"p1", "p2"}
    assert not leaked, (
        f"unjudged players leaked into the divergence lists: {sorted(leaked)}. "
        "Their board Elo differs from the seed only because of pool-wide "
        "recompute drift — the user never expressed an opinion about them.")
    assert d["board_judged_players"] == 2


def test_len_user_elo_is_not_the_bar():
    """A user with a FULL-POOL map but too few interactions still skips the
    beat. A `len(user_elo)` gate would pass here — 39 entries — which is the
    whole reason the bar is `board_interactions`."""
    seed = {f"p{i}": 1500.0 for i in range(1, 40)}
    out = _build(
        user_elo=dict(seed), seed_elo=seed,
        judged_ids={"p1"},
        board_interactions=BOARD_INTERACTION_BAR - 1,
    )
    assert out["divergence"]["source"] is None
    assert "divergence" in out["meta"]["beats_skipped"]


# ---------------------------------------------------------------------------
# Beat contract
# ---------------------------------------------------------------------------

def test_beats_and_skips_are_authoritative():
    out = _build()
    assert out["meta"]["beats"] == list(BEATS)
    # No board ⇒ divergence skipped; a full 12-team league keeps partners.
    assert "divergence" in out["meta"]["beats_skipped"]
    assert "partners" not in out["meta"]["beats_skipped"]


def test_tiny_league_skips_partners():
    out = _build(teams=_teams(2))
    assert "partners" in out["meta"]["beats_skipped"]


def test_window_never_infers_an_extreme_but_offers_all_five():
    out = _build(inferred_outlook="contender")
    assert out["window"]["inferred"] in ("contender", "rebuilder", "not_sure")
    assert out["window"]["options"] == list(OUTLOOK_OPTIONS)


def test_equal_pick_share_is_served_not_left_to_the_client():
    out = _build(teams=_teams(12))
    assert out["window"]["signals"]["equal_pick_share"] == pytest.approx(1 / 12, abs=1e-4)


def test_standing_ranks_the_caller_and_splits_by_position():
    out = _build()
    s = out["standing"]
    assert s["value_rank"] == 1          # u1 is built as the most valuable
    assert s["value_total"] == 12
    assert {r["position"] for r in s["position_value"]} == {"QB", "RB", "WR", "TE"}
    assert all(r["rank"] is not None for r in s["position_value"])


def test_preseason_scoring_is_null_with_a_named_reason():
    out = _build(scoring=None, scoring_unavailable_reason="preseason")
    assert out["standing"]["scoring"] is None
    assert out["meta"]["scoring_available"] is False
    assert out["meta"]["scoring_unavailable_reason"] == "preseason"


def test_non_sleeper_reason_is_distinct_from_preseason():
    out = _build(scoring=None, scoring_unavailable_reason="platform_unsupported")
    assert out["meta"]["scoring_unavailable_reason"] == "platform_unsupported"


def test_stored_prefs_come_back_so_controls_render_preselected():
    out = _build(stored_prefs={"team_outlook": "rebuilder",
                               "acquire_positions": ["TE"],
                               "trade_away_positions": ["RB"]})
    assert out["window"]["declared"] == "rebuilder"
    assert out["depth"]["acquire_positions"] == ["TE"]
    assert out["depth"]["trade_away_positions"] == ["RB"]


def test_depth_passes_through_366_keys_without_recomputing_them():
    """#366 — `tier_basis` and `handcuff_rb` ride the profile, not this module.

    `team_review` computes nothing new by design (module docstring), so the
    only correct behaviour is verbatim pass-through. If this beat ever starts
    DERIVING either value, the depth card and the trade engine acquire two
    different definitions of the same word — the exact failure the composer
    exists to prevent.
    """
    out = _build(roster_profile={
        "tier_depth": {"RB": {"elite": 1, "starter": 2, "bench": 3,
                              "replacement": 3}},
        "position_needs": ["TE"], "position_surplus": ["RB"],
        "tier_basis": {"QB": "position_relative", "RB": "position_relative",
                       "WR": "position_relative", "TE": "absolute"},
        "handcuff_rb": 2,
    })
    assert out["depth"]["handcuff_rb"] == 2
    assert out["depth"]["tier_basis"]["TE"] == "absolute"
    # `replacement` is an alias of `bench`, carried through untouched.
    assert out["depth"]["tier_depth"]["RB"]["replacement"] == 3
    assert out["depth"]["tier_depth"]["RB"]["bench"] == 3


def test_depth_omits_366_keys_entirely_when_the_flags_are_off():
    """Flags OFF means the profile carries neither key, and the payload must
    then carry neither — ABSENT, not `null` and not `0`.

    "we did not look" and "you own none" are different claims and the card
    renders them differently; a defaulted `0` would make the screen assert the
    second one on the strength of the first.
    """
    out = _build()   # the default fixture profile has neither key
    assert "handcuff_rb" not in out["depth"]
    assert "tier_basis" not in out["depth"]


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------

def test_not_sure_members_never_appear_as_opposed():
    out = _build(
        stored_prefs={"team_outlook": "contender"},
        member_windows={"u2": "not_sure", "u3": "rebuilder"},
        pick_share_by_owner={"u2": 0.9, "u3": 0.2},
    )
    ids = {r["user_id"] for r in out["partners"]["opposed_window"]}
    assert "u2" not in ids, "an undecided member was laundered into a recommendation"
    assert "u3" in ids


def test_a_member_may_appear_in_both_partner_lists():
    """Opposite window AND deep where you are thin = the best partner in the
    league. Suppressing the second appearance would hide the strongest signal."""
    out = _build(
        stored_prefs={"team_outlook": "contender"},
        member_windows={"u4": "rebuilder"},
        member_profiles={"u4": {"position_surplus": ["TE"],
                                "tier_depth": {"TE": {"elite": 1, "starter": 2}}}},
        roster_profile={"tier_depth": {}, "position_needs": ["TE"],
                        "position_surplus": []},
    )
    assert "u4" in {r["user_id"] for r in out["partners"]["opposed_window"]}
    assert "u4" in {r["user_id"] for r in out["partners"]["fills_your_need"]}


def test_contender_sorts_partners_by_pick_capital():
    out = _build(
        stored_prefs={"team_outlook": "contender"},
        member_windows={"u2": "rebuilder", "u3": "rebuilder"},
        pick_share_by_owner={"u2": 0.05, "u3": 0.40},
    )
    assert out["partners"]["opposed_window"][0]["user_id"] == "u3"


# ---------------------------------------------------------------------------
# Honesty
# ---------------------------------------------------------------------------

def test_payload_carries_no_odds_fields():
    """Team Review's own payload stays odds-free: the playoff band reaches the
    `standing` beat from the OUTLOOK route, composed by the server layer, so
    this pure module must not invent one."""
    import json
    blob = json.dumps(_build())
    for forbidden in ("title_pct", "playoff_pct", "bye_pct"):
        assert forbidden not in blob


def test_unknown_caller_returns_empty_rather_than_guessing():
    assert _build(you_user_id="nobody") == {}


# ---------------------------------------------------------------------------
# #367 — which list is the sell list
# ---------------------------------------------------------------------------

def test_seed_ladder_buys_are_off_roster_and_sells_are_on_roster():
    """The shipped screen offered the user's best BUYS under "Skip these".

    `higher_than_market` is where your board sits above the market on a player
    you do NOT own — you would pay less than you think he is worth. It shipped
    holding on-roster players you rate above the market, which is the set
    nobody overpays for.
    """
    seed = {"p1": 1500.0, "p2": 1500.0}
    user = {"p1": 1700.0, "p2": 1300.0}
    out = _build(
        user_elo=user, seed_elo=seed, judged_ids={"p1", "p2"},
        board_interactions=BOARD_INTERACTION_BAR,
        user_roster=["p2"],
    )
    d = out["divergence"]
    highs = {r["player_id"]: r for r in d["higher_than_market"]}
    lows = {r["player_id"]: r for r in d["lower_than_market"]}

    assert "p1" in highs, "you rate p1 above the market and do not own him → buy"
    assert highs["p1"]["on_roster"] is False
    assert "p2" in lows, "the market rates p2 above you and you own him → sell"
    assert lows["p2"]["on_roster"] is True
    assert "p1" not in lows and "p2" not in highs

    # Both sides ship a POSITIVE edge magnitude, matching compute_consensus_gap.
    assert highs["p1"]["gap"] == 200.0
    assert lows["p2"]["gap"] == 200.0


def test_community_ladder_maps_buys_to_higher_and_sells_to_lower():
    """The two source ladders must agree on what each field means."""
    community_gap = {
        "has_baseline": True,
        "baseline_user_count": 4,
        "easiest_sells": [
            {"player_id": "p2", "gap": 150.0, "community_elo": 1650.0},
        ],
        "easiest_buys": [
            {"player_id": "p1", "gap": 120.0, "owner_elo": 1380.0},
        ],
    }
    out = _build(
        user_elo={"p1": 1500.0, "p2": 1500.0},
        seed_elo={"p1": 1500.0, "p2": 1500.0},
        judged_ids={"p1", "p2"},
        board_interactions=BOARD_INTERACTION_BAR,
        community_gap=community_gap,
        user_roster=["p2"],
    )
    d = out["divergence"]
    assert d["source"] == "league_community"
    assert [r["player_id"] for r in d["higher_than_market"]] == ["p1"], (
        "easiest_buys belongs in higher_than_market — it IS the set you are "
        "higher than the market on")
    assert [r["player_id"] for r in d["lower_than_market"]] == ["p2"]
    assert d["higher_than_market"][0]["on_roster"] is False
    assert d["lower_than_market"][0]["on_roster"] is True
    # Comparison elo is the OWNER's for a buy, the community's for a sell.
    assert d["higher_than_market"][0]["comparison_elo"] == 1380.0
    assert d["lower_than_market"][0]["comparison_elo"] == 1650.0


# ---------------------------------------------------------------------------
# #365 — the inference model travels with its output
# ---------------------------------------------------------------------------

def test_window_ships_the_model_so_no_client_restates_a_threshold():
    """The screen rendered "Value age 23 and under" while `youth_age` was 26.

    A client that hardcodes a knob drifts the moment the knob moves, so the
    thresholds, weights and cuts ride the payload — the same rule that already
    governs `equal_pick_share`.
    """
    from backend.trade_service import infer_team_outlook
    _outlook, _score, signals = infer_team_outlook([], {}, 0.0, 12)
    assert "model" in signals
    out = _build(outlook_signals=signals)
    model = out["window"]["model"]
    for key in ("vet_age", "youth_age", "w_vet_share", "w_youth_share",
                "w_pick_share", "contender_cut", "rebuilder_cut"):
        assert key in model, f"window.model is missing {key}"
    assert model["vet_age"] != model["youth_age"] or model["vet_age"] is not None


def test_window_model_is_absent_not_faked_when_signals_lack_it():
    """An older caller passing bare signals gets `{}` — the client hides the
    breakdown rather than rendering invented numbers."""
    out = _build(outlook_signals={"vet_share": 0.5, "youth_share": 0.2,
                                  "pick_share": 0.08, "score": 0.1})
    assert out["window"]["model"] == {}


# ---------------------------------------------------------------------------
# #368 — the route must actually PASS what it computes
# ---------------------------------------------------------------------------

def test_partners_carry_first_round_counts_when_supplied():
    out = _build(
        teams=_teams(4),
        inferred_outlook="contender",
        member_windows={"u2": "rebuilder", "u3": "rebuilder"},
        first_round_by_owner={"u2": 5, "u3": 1},
        pick_share_by_owner={"u2": 0.40, "u3": 0.05},
    )
    rows = out["partners"]["opposed_window"]
    assert [r["user_id"] for r in rows] == ["u2", "u3"], (
        "a contender sorts opposed partners by pick capital, so the team "
        "holding 40% of the picks leads")
    assert rows[0]["first_round_picks"] == 5
    assert rows[1]["first_round_picks"] == 1


def test_team_review_route_passes_the_pick_capital_it_computes():
    """#368 was a DROPPED ARGUMENT, not a logic error.

    `league_team_review_route` builds `pick_share` and `first_rounds` for every
    member and then called `build_team_review` without them, so `_partners`
    fell back to `{}`: every team reported "0 firsts" and the contender sort
    key was uniformly 0.0, leaving the beat in arbitrary order. No unit test on
    the pure module can see that — the wiring is the defect, so the wiring is
    what this pins.
    """
    import ast
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1] / "server.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    call = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_team_review"):
            call = node
            break
    assert call is not None, "build_team_review call not found in server.py"
    kwargs = {k.arg for k in call.keywords}
    for name in ("pick_share_by_owner", "first_round_by_owner"):
        assert name in kwargs, (
            f"the team-review route computes pick capital but does not pass "
            f"{name}; _partners then reports 0 firsts for every member (#368)")
