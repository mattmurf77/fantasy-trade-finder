"""Unit tests for compute_tile_trade_scores (TestFlight #71 tile meters).

Tradeability (owned) / Acquirability (unowned) are 0-1 scores derived from
the SAME gaps the Trends consensus-gap feature surfaces:

  owned:   gap = user_elo - community_mean_elo   ("easiest sells")
  unowned: gap = user_elo - owner_elo            ("easiest buys",
           owner board → community-mean fallback)

Scaling: score = clamp01(0.5 + gap / 800) — gap ±400 saturates the bar,
gap 0 is a neutral half-full bar (which is what a never-really-ranked,
seed-only player produces, since seeds equal consensus).
"""
from backend.trends_service import compute_tile_trade_scores


# Three community rankers (the module's minimum baseline). Rankers agree on
# most players so the community mean is easy to reason about.
COMMUNITY = {
    "u_a": {"username": "a", "elo_ratings": {"p1": 1500, "p2": 1600, "p3": 1500, "p5": 1400}},
    "u_b": {"username": "b", "elo_ratings": {"p1": 1500, "p2": 1600, "p3": 1500, "p5": 1500}},
    "u_c": {"username": "c", "elo_ratings": {"p1": 1500, "p2": 1600, "p3": 1500, "p5": 1600}},
}
# Community mean: p1=1500, p2=1600, p3=1500, p5=1500

MEMBERS = [
    {"user_id": "u_a", "username": "a", "roster": ["p2"]},
    {"user_id": "u_me", "username": "me", "roster": ["p1", "p3"]},
    {"user_id": "u_nr", "username": "no_rankings", "roster": ["p5"]},
    # p4 is on nobody's roster (free agent).
]

ROSTER = ["p1", "p3"]


def _scores(user_elo, community=COMMUNITY, roster=ROSTER, members=MEMBERS):
    return compute_tile_trade_scores(user_elo, community, roster, members)


# ── Owned / unowned classification ──────────────────────────────────────────

def test_owned_player_gets_tradeability_flag():
    out = _scores({"p1": 1700})
    assert out["p1"]["owned"] is True


def test_unowned_league_rostered_player_gets_acquirability_flag():
    out = _scores({"p2": 1700})
    assert out["p2"]["owned"] is False


def test_free_agent_gets_no_score():
    # p4 is rostered by nobody → not acquirable via trade → omitted.
    out = _scores({"p4": 1700})
    assert "p4" not in out


def test_owned_player_missing_from_community_pool_is_omitted():
    # px is on the user's roster but no community ranker has ranked them →
    # no market comparison basis.
    out = _scores({"px": 1700}, roster=["px"])
    assert "px" not in out


# ── Gap → score scaling ─────────────────────────────────────────────────────

def test_positive_gap_scales_above_neutral():
    # Owned p1: user 1700 vs community mean 1500 → gap +200 → 0.5 + 200/800.
    out = _scores({"p1": 1700})
    assert out["p1"]["score"] == 0.75


def test_negative_gap_scales_below_neutral():
    # Owned p1: user 1300 vs 1500 → gap −200 → 0.25.
    out = _scores({"p1": 1300})
    assert out["p1"]["score"] == 0.25


def test_score_clamps_at_full_and_empty():
    out = _scores({"p1": 2500, "p3": 500})
    assert out["p1"]["score"] == 1.0
    assert out["p3"]["score"] == 0.0


def test_seed_only_player_is_neutral():
    # A player the user never really ranked carries the consensus seed, so
    # user_elo == community mean → gap 0 → neutral half bar. Documented
    # behavior: no opinion → no signal.
    out = _scores({"p1": 1500})
    assert out["p1"]["score"] == 0.5


# ── Acquirability comparison basis ──────────────────────────────────────────

def test_acquirability_uses_owner_board_not_community_mean():
    # p5 belongs to u_nr... use p2 instead: owned by u_a whose board has
    # p2=1600 (== community mean here). Give the owner a divergent board.
    community = {
        **COMMUNITY,
        "u_a": {"username": "a", "elo_ratings": {"p1": 1500, "p2": 1200, "p3": 1500}},
    }
    # Community mean for p2 is now (1200+1600+1600)/3 = 1466.7, but the
    # OWNER (u_a) values p2 at 1200 → gap vs owner = +400 → saturated bar.
    out = _scores({"p2": 1600}, community=community)
    assert out["p2"]["score"] == 1.0


def test_acquirability_falls_back_to_community_mean_when_owner_unranked():
    # p5 is owned by u_nr, who has published no rankings — the comparison
    # falls back to the community mean (1500), mirroring "easiest buys".
    community = {k: v for k, v in COMMUNITY.items()}  # u_nr absent already
    out = _scores({"p5": 1700}, community=community)
    assert out["p5"]["owned"] is False
    assert out["p5"]["score"] == 0.75


# ── Baseline gate ───────────────────────────────────────────────────────────

def test_thin_community_baseline_returns_empty():
    two_rankers = {k: COMMUNITY[k] for k in ("u_a", "u_b")}
    assert _scores({"p1": 1700}, community=two_rankers) == {}


def test_no_community_returns_empty():
    assert _scores({"p1": 1700}, community={}) == {}


# ── Robustness ──────────────────────────────────────────────────────────────

def test_non_numeric_user_elo_is_skipped():
    out = _scores({"p1": "not-a-number", "p3": 1700})
    assert "p1" not in out
    assert out["p3"]["score"] == 0.75
