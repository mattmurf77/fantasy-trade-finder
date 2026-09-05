"""
Personal-market policy — WIRING.

Scope block: docs/plans/personal-market-policy/scope.md

`test_trade_policy.py` pins the evaluator's math. This file pins where it is
actually plugged in:

  * the single choke point in `_run_trade_job`, which every generator and
    every post-generation mutation must pass through;
  * v2 and v3 refusing to admit a candidate the policy rejects;
  * the sweetener, gap-sweetener, relaxed-fallback and likes-you paths not
    being bypasses;
  * confidence persisting symmetrically through `member_rankings`;
  * the impression / proposal / match telemetry;
  * and — the load-bearing one — **flag-off byte identity**.

Harness: a variant of `support/bakeoff_harness` with BOTH league-mates
carrying real boards (`has_rankings=True`) plus persisted confidence, because
the policy's whole subject is two-board trades and the shared harness
deliberately patches `load_member_rankings` to `{}`.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
import backend.trade_policy as tp
import backend.trade_service as ts
from backend.database import (deck_impressions_table, metadata,
                              trade_matches_table, trade_policy_shadow_table,
                              trade_proposals_table)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

LEAGUE = "league_policy_wiring"
ME, OPP, OPP2 = "user_me", "user_opp", "user_opp2"
TOKEN, JOB_ID = "tok-policy-wiring", "job-policy-wiring"

# A deliberately WIDER pool than `support/bakeoff_harness`'s eight players.
# The policy's subject is two-board trades, and composition rules (three Core
# leads, at most two Conviction) are meaningless on a one-card deck — the
# harness has to be able to produce real inventory on both sides.
_POOL = [
    ("qb1", "QB One",    "QB", "AAA", 26, 1750.0),
    ("qb2", "QB Two",    "QB", "EEE", 25, 1690.0),
    ("rb1", "RB One",    "RB", "AAA", 24, 1700.0),
    ("rb2", "RB Two",    "RB", "BBB", 27, 1520.0),
    ("rb3", "RB Three",  "RB", "DDD", 22, 1600.0),
    ("rb4", "RB Four",   "RB", "EEE", 23, 1470.0),
    ("wr1", "WR One",    "WR", "BBB", 25, 1680.0),
    ("wr2", "WR Two",    "WR", "CCC", 29, 1430.0),
    ("wr3", "WR Three",  "WR", "DDD", 28, 1490.0),
    ("wr4", "WR Four",   "WR", "EEE", 24, 1620.0),
    ("wr5", "WR Five",   "WR", "FFF", 26, 1540.0),
    ("te1", "TE One",    "TE", "CCC", 23, 1560.0),
    ("te2", "TE Two",    "TE", "FFF", 27, 1450.0),
]
SEED = {pid: elo for pid, _n, _p, _t, _a, elo in _POOL}
ME_ROSTER   = ["qb1", "rb1", "wr2", "te1", "wr5", "rb4"]
OPP_ROSTER  = ["rb2", "wr1", "qb2", "te2"]
OPP2_ROSTER = ["rb3", "wr3", "wr4"]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_cfg():
    """`trade_service._cfg` is process-global and `_c` reads it at call time
    (tests/CLAUDE.md harness pattern 4)."""
    saved = dict(ts._cfg)
    yield
    ts._cfg.clear()
    ts._cfg.update(saved)


def _knobs(**over):
    ts._cfg.update({k: float(v) for k, v in over.items()})


def _players():
    return [Player(id=pid, name=n, position=p, team=t, age=a)
            for pid, n, p, t, a, _e in _POOL]


# PER-PLAYER divergence, not a uniform roster bias.
#
# `support/bakeoff_harness` shifts a league-mate's whole roster up and
# everything else down. That is fine for a serving-order golden but it makes
# every opponent a pure hoarder: on their own raw board EVERY trade they could
# make is a loss, so no card can ever show two-sided personal gain, and a
# Conviction lane is unreachable by construction. The legacy engine still
# emits such cards because its surplus gate runs on MARGINAL (over-
# replacement) values, which collapse the hoarding — but the policy judges raw
# confidence-shrunk personal values, so the fixture has to contain real
# disagreement rather than uniform greed.
#
# Each map below makes the opponent OVERVALUE several of the viewer's players
# and UNDERVALUE some of their own — which is exactly what a divergence trade
# is, and what produces a spread of market ratios across the Core boundary.
_OPP_DELTA = {"wr2": 240, "te1": 180, "wr5": 200, "rb4": 150, "qb1": 60,
              "rb1": 90, "rb2": -110, "te2": -90, "wr1": -60, "qb2": -80}
_OPP2_DELTA = {"rb1": 210, "wr5": 190, "te1": 140, "wr2": 120, "rb4": 100,
               "qb1": 50, "rb3": -100, "wr3": -80, "wr4": -70}


def _opp_board(deltas, _roster=None):
    """A league-mate's personal board: consensus plus per-player deltas."""
    return {pid: elo + deltas.get(pid, 0.0)
            for pid, _n, _p, _t, _a, elo in _POOL}


def _member_rankings(counts_per_player=40):
    """What `load_member_rankings` returns once confidence is persisted."""
    def _one(deltas, roster):
        board = _opp_board(deltas, roster)
        return {
            "username": "opp",
            "elo_ratings": board,
            "comparison_counts": {p: counts_per_player for p in board},
            "confidence_weights": {
                p: tp.confidence_weight_for(counts_per_player, tp.SOURCE_VOTES)
                for p in board},
            "confidence_source": tp.SOURCE_VOTES,
            "board_updated_at": "2026-09-01T00:00:00+00:00",
        }
    return {OPP: _one(_OPP_DELTA, OPP_ROSTER), OPP2: _one(_OPP2_DELTA, OPP2_ROSTER)}


def _flag_patches(*, telemetry, policy, member_rankings=None):
    import backend.feature_flags as _ff
    _real = _ff.is_enabled
    pins = {"trade.valuation_telemetry": telemetry,
            "trade.personal_market_policy_v1": policy,
            "trade.outlook_direction": True}
    return [
        patch.object(_ff, "is_enabled",
                     lambda k: pins[k] if k in pins else _real(k)),
        patch.object(server, "_deck_signal_v2_enabled", lambda: True),
        patch.object(server, "_thompson_deck_enabled", lambda: True),
        patch.object(server, "_deck_thompson_v2_enabled", lambda: False),
        patch.object(server, "_deck_diversity_enabled", lambda: True),
        patch.object(server, "_deck_fatigue_enabled", lambda: False),
        patch.object(server, "_deck_taste_enabled", lambda: False),
        patch.object(server, "_deck_value_model_enabled", lambda: False),
        patch.object(server, "_deck_exploration_enabled", lambda: False),
        patch.object(server, "_deck_first_session_enabled", lambda: False),
        patch.object(server, "_suggestion_telemetry_enabled", lambda: False),
        patch.object(server, "_likes_you_enabled", lambda: True),
        patch.object(server, "load_member_rankings",
                     MagicMock(return_value=member_rankings
                               if member_rankings is not None else {})),
        patch.object(server, "load_league_preference", MagicMock(return_value=None)),
        patch.object(server, "create_notification", MagicMock()),
        patch.object(server, "_send_typed_push", MagicMock()),
    ]


def run_job(*, telemetry=False, policy=False, boards=True, seed_like=True,
            fairness_threshold=0.75, extra_patches=(), counts=40):
    """One complete `_run_trade_job` under a pinned flag configuration.

    Returns (job, engine, impression rows, shadow rows).
    """
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    pool = _players()
    service = RankingService(players=list(pool))
    service._seed = dict(SEED)
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Policy Wiring", platform="sleeper",
        members=[
            LeagueMember(user_id=ME, username="me", roster=list(ME_ROSTER),
                         elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=list(OPP_ROSTER),
                         elo_ratings=_opp_board(_OPP_DELTA, OPP_ROSTER)),
            LeagueMember(user_id=OPP2, username="opp2", roster=list(OPP2_ROSTER),
                         elo_ratings=_opp_board(_OPP2_DELTA, OPP2_ROSTER)),
        ],
    )
    trade_svc.add_league(league)

    sess = {"user_id": ME, "league": league, "user_roster": list(ME_ROSTER),
            "players": pool, "services": {"1qb_ppr": service},
            "trade_svcs": {"1qb_ppr": trade_svc}, "service": service,
            "trade_svc": trade_svc, "active_format": "1qb_ppr",
            "last_active": 0.0}
    job = {"job_id": JOB_ID, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
           "started_at": time.monotonic(), "finished_at": None,
           "opponents_done": 0, "opponents_total": 2, "cards": [],
           "error": None, "fairness_threshold": fairness_threshold,
           "outlook_value": None, "is_pinned": False}

    patches = _flag_patches(
        telemetry=telemetry, policy=policy,
        member_rankings=_member_rankings(counts) if boards else {},
    ) + list(extra_patches)

    with patch.object(db_module, "engine", engine):
        if seed_like:
            with engine.begin() as conn:
                created = (datetime.now(timezone.utc)
                           - timedelta(days=1)).isoformat()
                conn.execute(text(
                    "INSERT INTO trade_decisions (user_id, league_id, "
                    "give_player_ids, receive_player_ids, decision, "
                    "created_at, impression_id) VALUES "
                    "(:uid, :lid, :give, :recv, 'like', :created, :imp)"
                    # OPP offers wr1 (1680) for wr2 (1430). Mirrored, the
                    # VIEWER gains, so it survives the D-096 likes-you
                    # quality gates and actually reaches the deck — a like
                    # the viewer loses on is filtered before injection and
                    # would make this fixture silently test nothing.
                ), {"uid": OPP, "lid": LEAGUE, "give": json.dumps(["wr1"]),
                    "recv": json.dumps(["wr2"]), "created": created,
                    "imp": "their-imp-1"})
        stack = []
        try:
            for p in patches:
                p.start()
                stack.append(p)
            with server._sessions_lock:
                server._sessions[TOKEN] = sess
            with server._trade_jobs_lock:
                server._trade_jobs[JOB_ID] = job
            server._run_trade_job(JOB_ID, TOKEN, LEAGUE, fairness_threshold, [])
        finally:
            for p in reversed(stack):
                p.stop()
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                server._trade_jobs.pop(JOB_ID, None)
                server._trade_jobs_by_key.pop((ME, LEAGUE, "1qb_ppr"), None)

        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(
                select(deck_impressions_table)
                .order_by(deck_impressions_table.c.card_index)).fetchall()]
            shadow = [dict(r._mapping) for r in conn.execute(
                select(trade_policy_shadow_table)).fetchall()]
    return job, engine, rows, shadow


_POLICY_COLUMNS = ("valuation_json", "trade_concept_id", "policy_variant",
                   "source_like_impression_id")


# ---------------------------------------------------------------------------
# Flag-off byte identity — the load-bearing guarantee
# ---------------------------------------------------------------------------

def _canonical(job, rows):
    strip_card = ("trade_id", "impression_id", "expires_at", "created_at")
    strip_row = ("impression_id", "served_at", "candidate_set_id")
    return {
        "cards": [json.loads(json.dumps(
            {k: v for k, v in c.items() if k not in strip_card},
            sort_keys=True, default=str)) for c in (job.get("cards") or [])],
        "rows": [json.loads(json.dumps(
            {k: v for k, v in r.items() if k not in strip_row},
            sort_keys=True, default=str)) for r in rows],
    }


def test_flag_off_produces_no_policy_state_at_all():
    """Both flags off: no new column is populated, no shadow row is written,
    and no card is filtered or reordered. This is the whole safety claim of
    shipping dark, so it is asserted directly rather than inferred."""
    job, _eng, rows, shadow = run_job(telemetry=False, policy=False)
    assert job["status"] == "complete"
    assert rows, "the harness must actually produce impressions"
    for r in rows:
        for col in _POLICY_COLUMNS:
            assert r[col] is None, col
    assert shadow == []


def test_flag_off_deck_is_byte_identical_to_a_second_flag_off_run():
    """The engine is deterministic under this harness, so two flag-off runs
    must agree exactly. If a later change made any policy code run while the
    flags are off, this is what would catch it."""
    job_a, _eng_a, rows_a, _sh_a = run_job(telemetry=False, policy=False)
    job_b, _eng_b, rows_b, _sh_b = run_job(telemetry=False, policy=False)
    assert _canonical(job_a, rows_a) == _canonical(job_b, rows_b)
    assert rows_a, "a vacuous comparison of two empty decks proves nothing"


def test_telemetry_on_does_not_change_which_cards_are_served():
    """Phase 1 contract: "do not change candidate eligibility or served
    order". Telemetry adds columns; it must not add or remove a card."""
    off_job, _e1, off_rows, _s1 = run_job(telemetry=False, policy=False)
    on_job, _e2, on_rows, _s2 = run_job(telemetry=True, policy=False)

    def _ids(rows):
        return [(r["trade_hash"], r["card_index"], r["base_score"])
                for r in rows]
    assert _ids(off_rows) == _ids(on_rows)
    assert len(off_job["cards"]) == len(on_job["cards"])


# ---------------------------------------------------------------------------
# Telemetry completeness (brief test 16 + the instrumentation criteria)
# ---------------------------------------------------------------------------

def test_every_impression_carries_a_parseable_snapshot_matching_its_assets():
    """Instrumentation acceptance: a parseable `valuation_json` whose asset
    ids and DIRECTIONS match the served package, a canonical concept id, and
    the job's policy variant — on every row."""
    _job, _eng, rows, _shadow = run_job(telemetry=True, policy=False)
    assert rows
    for r in rows:
        assert r["policy_variant"] == tp.POLICY_LEGACY, \
            "shadow mode must still stamp the variant the job RAN under"
        assert r["trade_concept_id"], "every row needs the mirror-join key"
        snap = json.loads(r["valuation_json"])
        assert snap["schema_version"] == tp.VALUATION_SCHEMA_VERSION
        features = json.loads(r["features_json"])

        # DIRECTIONS match the served package. Checked against the row's own
        # `trade_hash` rather than against the snapshot itself — comparing a
        # snapshot to a set derived from that same snapshot would pass no
        # matter how wrong the snapshot was.
        assert server._deck_trade_hash(
            _give_of(snap), _recv_of(snap),
            features["partner_user_id"]) == r["trade_hash"], (
                "the snapshot's asset sets and sides must reproduce the row's "
                "own card identity")

        # Recomputed market ratio agrees with the stored consensus fairness
        # inside the documented 0.001 tolerance. `fairness_score` on an
        # ordinary row IS round(min/max, 3) of the consensus packages, so this
        # is the acceptance criterion measured directly, not a range check.
        #
        # ONE known exception, G-070: a likes-you SYNTHESIZED card computes
        # its fairness from summed RAW ELO, not from package values. Elo is a
        # log scale, so the ratio compresses toward 1.0 and a 3.5x value gap
        # reads as 0.85. It is asserted below as a known-wrong class rather
        # than skipped, so fixing G-070 makes this test fail loudly instead of
        # quietly passing.
        stored = features.get("fairness_score")
        synthesized_likes_you = (features.get("likes_you")
                                 and features.get("basis") == "consensus"
                                 and features.get("surplus_margin") == 0.0
                                 and features.get("give_value") is not None
                                 and features.get("receive_value") is not None
                                 and abs(features["give_value"]
                                         - features["receive_value"]) > 1.0)
        if stored is None:
            continue
        if synthesized_likes_you and abs(
                snap["market"]["ratio"] - stored) > 0.001:
            g, rv = features["give_value"], features["receive_value"]
            assert abs(snap["market"]["ratio"]
                       - min(g, rv) / max(g, rv)) <= 0.002, (
                "G-070: the snapshot must still agree with the card's OWN "
                "value bar even when `fairness_score` does not")
            continue
        assert abs(snap["market"]["ratio"] - stored) <= 0.001, (
            r["trade_hash"], snap["market"]["ratio"], stored)


def _give_of(snap):
    return [a["id"] for a in snap["assets"]["give"]]


def _recv_of(snap):
    return [a["id"] for a in snap["assets"]["receive"]]


def test_mirrored_impressions_of_one_package_share_a_concept_id():
    """Brief test 20, end to end: the id stamped on a real impression row is
    the same one the opposite perspective produces."""
    _job, _eng, rows, _s = run_job(telemetry=True, policy=False)
    row = rows[0]
    snap = json.loads(row["valuation_json"])
    features = json.loads(row["features_json"])
    partner = features["partner_user_id"]
    mirrored = tp.trade_concept_id(
        league_id=LEAGUE, viewer_user_id=partner, partner_user_id=ME,
        viewer_gives=_recv_of(snap), viewer_receives=_give_of(snap))
    assert row["trade_concept_id"] == mirrored


def test_both_boards_are_present_in_a_two_board_snapshot():
    """The point of the schema change: a league-mate's confidence now
    reaches generation, so the snapshot can show BOTH managers' raw and
    effective values instead of only the viewer's."""
    _job, _eng, rows, _s = run_job(telemetry=True, policy=False, counts=40)
    two_board = [r for r in rows
                 if json.loads(r["valuation_json"])["policy"]["value_basis"]
                 == tp.BASIS_TWO_BOARD]
    assert two_board, "the harness must produce at least one two-board card"
    snap = json.loads(two_board[0]["valuation_json"])
    for side in ("viewer_board", "partner_board"):
        assert snap[side]["source"] == "personal"
        assert snap[side]["package_confidence"] is not None
    assert snap["partner_board"]["package_confidence"] > 0.0, \
        "persisted opponent confidence must actually reach the evaluator"


def test_telemetry_failure_never_fails_the_job():
    """"Keep the write best-effort so telemetry can never fail trade
    generation." A snapshot builder that raises must leave a completed job
    and a served deck."""
    boom = patch.object(tp, "build_valuation_snapshot",
                        side_effect=RuntimeError("boom"))
    job, _eng, rows, _s = run_job(telemetry=True, policy=False,
                                  extra_patches=[boom])
    assert job["status"] == "complete"
    assert job["cards"], "cards must still be served"
    for r in rows:
        assert r["valuation_json"] is None


# ---------------------------------------------------------------------------
# The choke point actually gates (brief tests 4, 10)
# ---------------------------------------------------------------------------

def test_no_served_card_falls_below_the_absolute_floor():
    """Policy acceptance criterion 1, measured on the rows that were
    actually written. Every served card's own frozen snapshot must show a
    market ratio at or above `market_floor_absolute`."""
    _knobs(market_floor_absolute=0.65)
    _job, _eng, rows, _s = run_job(telemetry=True, policy=True)
    for r in rows:
        snap = json.loads(r["valuation_json"])
        assert snap["market"]["ratio"] >= 0.65 - 1e-9, snap["market"]


def test_raising_the_absolute_floor_removes_cards_rather_than_admitting_them():
    """A stricter floor must SHRINK the deck. If the count went up (or stayed
    put) the floor is not reaching the served set."""
    _knobs(market_floor_absolute=0.65, market_floor_one_board=0.65,
           market_floor_two_board_base=0.65)
    _j1, _e1, loose_rows, _s1 = run_job(telemetry=True, policy=True)

    _knobs(market_floor_absolute=0.98, market_floor_one_board=0.98,
           market_floor_two_board_base=0.98)
    _j2, _e2, strict_rows, strict_shadow = run_job(telemetry=True, policy=True)

    assert len(strict_rows) < len(loose_rows)
    for r in strict_rows:
        assert json.loads(r["valuation_json"])["market"]["ratio"] >= 0.98 - 1e-9


def test_rejected_candidates_are_recorded_not_silently_dropped():
    """"A candidate rejected by the treatment must remain visible in shadow
    telemetry with its generator arm and rejection reason; otherwise the
    treatment will appear artificially precise because its discarded
    candidates vanish from the denominator." """
    _knobs(market_floor_absolute=0.99, market_floor_one_board=0.99,
           market_floor_two_board_base=0.99, policy_shadow_log_cap=40)
    _job, _eng, _rows, shadow = run_job(telemetry=True, policy=True)
    assert shadow, "rejections must be written to trade_policy_shadow"
    for row in shadow:
        assert row["policy_variant"] == tp.POLICY_V1
        assert row["reason"]
        assert row["eligible"] == 0
        assert row["market_ratio"] is not None
        assert row["effective_floor"] is not None


def test_the_shadow_log_is_capped_per_job():
    _knobs(market_floor_absolute=0.99, market_floor_one_board=0.99,
           market_floor_two_board_base=0.99, policy_shadow_log_cap=2)
    _job, _eng, _rows, shadow = run_job(telemetry=True, policy=True)
    assert len(shadow) <= 2


def test_a_user_preference_can_tighten_the_served_deck_but_never_loosen_it():
    """Brief test 9, end to end. The LEGACY path composes the request with
    `min(...)`, so asking for 0.95 made the gate LOOSER (0.55). Under the
    policy a stricter request can only remove cards."""
    _knobs(market_floor_absolute=0.65, market_floor_one_board=0.70,
           market_floor_two_board_base=0.70)
    _j1, _e1, loose, _s1 = run_job(telemetry=True, policy=True,
                                   fairness_threshold=0.50)
    _j2, _e2, strict, _s2 = run_job(telemetry=True, policy=True,
                                    fairness_threshold=0.95)
    assert len(strict) <= len(loose)
    for r in strict:
        snap = json.loads(r["valuation_json"])
        assert snap["policy"]["effective_floor"] >= 0.95 - 1e-9
        assert snap["market"]["ratio"] >= 0.95 - 1e-9


def test_the_relaxed_fallback_cannot_reach_below_the_policy_floor():
    """Brief test 10, relaxed arm. `_relaxed_targeted_pass` lowers
    `fairness_threshold` and overrides `fairness_floor_divergence`; under the
    policy neither knob is read as a gate, and the lowered request is
    composed with `max`, so relaxation cannot descend past the policy floor.

    Asserted on the evaluator rather than through a targeted job, because
    that is where the composition lives and it is the composition that is
    the bypass risk."""
    _knobs(market_floor_absolute=0.65, market_floor_two_board_base=0.80,
           relaxed_fairness_threshold=0.30, fairness_floor_divergence=0.30)
    floor = tp.derive_policy_floor(two_board=True, trade_confidence=0.0,
                                   normalized_strength=1.0)
    assert tp.compose_effective_floor(floor, 0.30) == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# Deck composition (brief tests 12, 13)
# ---------------------------------------------------------------------------

def test_the_served_deck_respects_the_core_quotas():
    """Brief test 13, through the real job. When Core supply exists the deck
    leads with Core and carries at most two Conviction cards."""
    _knobs(market_floor_absolute=0.50, market_floor_one_board=0.50,
           market_floor_two_board_base=0.50, market_core_ratio=0.80,
           deck_core_lead_cards=3, conviction_deck_share=0.20,
           deck_core_min_share=0.70)
    _job, _eng, rows, _s = run_job(telemetry=True, policy=True)
    lanes = [json.loads(r["valuation_json"])["policy"]["eligibility_lane"]
             for r in rows]
    assert len(lanes) >= 4, "the fixture must produce a real deck to compose"
    # The fixture is built so BOTH lanes are reachable — otherwise the
    # conviction cap below would pass vacuously.
    assert tp.LANE_CONVICTION in lanes and tp.LANE_CORE in lanes, lanes
    assert lanes[:3] == [tp.LANE_CORE] * 3, lanes
    assert lanes.count(tp.LANE_CONVICTION) <= 2, lanes
    assert lanes.count(tp.LANE_CORE) >= len(lanes) * 0.70 - 1e-9, lanes
    # No ineligible card reached the deck.
    assert "ineligible" not in lanes


# ---------------------------------------------------------------------------
# v2 / v3 both route through the evaluator (brief: "cover both v2 and v3")
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("v3_on", [False, True])
def test_both_generators_refuse_a_candidate_the_policy_rejects(v3_on):
    """The gate is inside each generator's candidate loop as well as at the
    choke point, so an impossible floor starves the deck rather than merely
    filtering it afterwards. Run once with v3 off (v2 pair generator) and
    once with it on (the exact package optimizer)."""
    import backend.feature_flags as _ff
    _knobs(market_floor_absolute=0.999, market_floor_one_board=0.999,
           market_floor_two_board_base=0.999)
    _real = _ff.is_enabled
    extra = [patch.object(server, "_deck_diversity_enabled", lambda: False)]
    with patch.object(_ff, "is_enabled",
                      lambda k: v3_on if k == "trade_engine.v3" else _real(k)):
        _job, _eng, rows, _s = run_job(telemetry=True, policy=True,
                                       extra_patches=extra)
    for r in rows:
        assert json.loads(r["valuation_json"])["market"]["ratio"] >= 0.999 - 1e-6


def test_the_v2_pair_generator_builds_an_evaluator_only_when_the_flag_is_on():
    """Flag-off byte identity at the source: `make_pair_evaluator` returns
    None, so `_consider` does one `is None` check and evaluates nothing."""
    member = LeagueMember(user_id=OPP, username="o", roster=list(OPP_ROSTER),
                          elo_ratings=_opp_board(_OPP_DELTA, OPP_ROSTER),
                          has_rankings=True)
    kw = dict(consensus_value=lambda p: SEED.get(p, 1500.0),
              viewer_effective_value=lambda p: SEED.get(p, 1500.0),
              viewer_raw_value=None, viewer_confidence_of=lambda p: 0.0,
              opponent=member, seed_elo=SEED, requested_floor=0.5)
    with patch.object(tp, "policy_enabled", lambda: False):
        assert tp.make_pair_evaluator(**kw) is None
    with patch.object(tp, "policy_enabled", lambda: True):
        assert tp.make_pair_evaluator(**kw) is not None


def test_a_partner_without_real_rankings_gets_no_fabricated_board():
    """"If the opponent has no real personal board … treat it as a
    one-board/consensus fallback and label it honestly." A member whose Elo
    is seeded noise must not be handed a confidence map that dresses that
    noise as evidence."""
    unranked = LeagueMember(user_id=OPP, username="o", roster=list(OPP_ROSTER),
                            elo_ratings=_opp_board(_OPP_DELTA, OPP_ROSTER),
                            has_rankings=False)
    with patch.object(tp, "policy_enabled", lambda: True):
        ev = tp.make_pair_evaluator(
            consensus_value=lambda p: SEED.get(p, 1500.0),
            viewer_effective_value=lambda p: SEED.get(p, 1500.0),
            viewer_raw_value=None, viewer_confidence_of=lambda p: 0.0,
            opponent=unranked, seed_elo=SEED, requested_floor=0.5)
    res = ev(["rb1"], ["rb2"])
    assert res.basis in (tp.BASIS_ONE_BOARD, tp.BASIS_CONSENSUS)
    assert res.partner.gives_effective is None
    assert res.personal_opportunity is None


# ---------------------------------------------------------------------------
# Confidence persistence (brief: "populate them from every ranking workflow")
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    yield engine


def test_confidence_round_trips_through_member_rankings(db):
    db_module.upsert_member_rankings(
        "u1", "L1",
        [{"player_id": "p1", "elo": 1800.0},
         {"player_id": "p2", "elo": 1400.0,
          "confidence_source": tp.SOURCE_EXPLICIT}],
        "1qb_ppr",
        comparison_counts={"p1": 12, "p2": 0},
        confidence_source=tp.SOURCE_VOTES)

    out = db_module.load_member_rankings("L1", exclude_user_id="other",
                                         scoring_format="1qb_ppr")
    board = out["u1"]
    assert board["elo_ratings"] == {"p1": 1800.0, "p2": 1400.0}
    assert board["comparison_counts"] == {"p1": 12, "p2": 0}
    # September 5: deliberate votes and placements have equal authority.
    assert board["confidence_weights"]["p1"] == 1.0
    assert board["confidence_weights"]["p2"] == pytest.approx(1.0)
    assert board["board_updated_at"]


def test_a_legacy_ranking_row_reads_as_lowest_confidence(db):
    """"Legacy rows with null confidence must be treated as low confidence,
    not as fully trusted." """
    db_module.upsert_member_rankings(
        "u1", "L1", [{"player_id": "p1", "elo": 1900.0}], "1qb_ppr")
    board = db_module.load_member_rankings(
        "L1", exclude_user_id="x", scoring_format="1qb_ppr")["u1"]
    assert board["comparison_counts"] == {}
    assert board["confidence_weights"] == {}
    assert board["confidence_source"] is None
    # …and the evaluator therefore prices that player at consensus.
    conf = tp.confidence_map(board["comparison_counts"],
                             weights=board["confidence_weights"])
    assert tp.shrink_board({"p1": 1900.0}, {"p1": 1500.0}, conf) == {"p1": 1500.0}


def test_the_confidence_helper_marks_explicitly_placed_players(monkeypatch):
    """A tier save publishes the WHOLE board while only some of it was
    placed, so provenance is decided per player, not per snapshot."""
    svc = MagicMock()
    svc.comparison_counts.return_value = {"p1": 3, "p2": 9}
    svc.placement_bands.return_value = {"p2": (1600.0, 1700.0)}
    conf = server._ranking_confidence(svc)
    payload = server._confidence_payload(
        [{"player_id": "p1", "elo": 1500.0},
         {"player_id": "p2", "elo": 1650.0}], conf)
    assert payload[0].get("confidence_source") is None      # votes
    assert payload[1]["confidence_source"] == tp.SOURCE_EXPLICIT
    assert "_placed" not in conf, "the marker must be popped before splatting"
    assert conf["confidence_source"] == tp.SOURCE_VOTES


def test_a_broken_ranking_service_degrades_to_null_confidence():
    """A ranking save must never fail because confidence could not be read."""
    svc = MagicMock()
    svc.comparison_counts.side_effect = RuntimeError("nope")
    assert server._ranking_confidence(svc) == {}
    payload = [{"player_id": "p1", "elo": 1500.0}]
    assert server._confidence_payload(payload, {}) is payload


# ---------------------------------------------------------------------------
# Likes-you injection (brief tests 10, 22, 23)
# ---------------------------------------------------------------------------

def test_an_injected_mirror_names_the_like_that_caused_it():
    """"When a card is explicitly injected because another manager
    previously liked the mirror, also stamp `source_like_impression_id`.
    This distinguishes an organic independently generated mirror from a card
    shown because of the first manager's action." """
    _knobs(market_floor_absolute=0.10, market_floor_one_board=0.10,
           market_floor_two_board_base=0.10)
    _job, _eng, rows, _s = run_job(telemetry=True, policy=False, seed_like=True)
    stamped = [r for r in rows if r["source_like_impression_id"]]
    assert stamped, "the seeded counterparty like must produce a stamped card"
    assert all(r["source_like_impression_id"] == "their-imp-1" for r in stamped)
    # …and it is genuinely selective: organic cards carry NULL.
    assert any(r["source_like_impression_id"] is None for r in rows)


def test_a_stale_liked_mirror_records_a_closed_reason_not_a_rejection():
    """Brief tests 22 + 23. The counterparty's like is no longer actionable
    (they no longer roster what they offered). Before this change that card
    simply never appeared and every funnel query read the missing second
    like as a REJECTION. It must be a recorded, closed state instead."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    svc = TradeService(players={p.id: p for p in _players()})
    league = League(league_id=LEAGUE, name="x", platform="sleeper", members=[
        LeagueMember(user_id=ME, username="me", roster=list(ME_ROSTER),
                     elo_ratings={}),
        LeagueMember(user_id=OPP, username="opp", roster=list(OPP_ROSTER),
                     elo_ratings=_opp_board(_OPP_DELTA, OPP_ROSTER),
                     has_rankings=True),
    ])
    svc.add_league(league)
    like = {"user_id": OPP, "trade_id": "t1",
            # `wr3` is on OPP2's roster, not OPP's — no longer actionable.
            "give_player_ids": ["wr3"], "receive_player_ids": ["rb1"],
            "created_at": "2026-09-01T00:00:00+00:00",
            "impression_id": "their-imp-9"}

    with patch.object(db_module, "engine", engine), \
         patch.object(tp, "telemetry_enabled", lambda: True), \
         patch.object(server, "load_recent_league_likes",
                      MagicMock(return_value=[like])), \
         patch.object(server, "_standing_offers_enabled", lambda: False):
        out = server._inject_likes_you_cards_impl(
            [], svc, ME, LEAGUE, league, list(ME_ROSTER), dict(SEED))

    assert out == [], "an unactionable mirror must not be served"
    skips = getattr(svc, "_mirror_skips", [])
    assert len(skips) == 1
    assert skips[0]["reason"] == tp.REASON_ROSTER_CHANGED
    assert skips[0]["source_like_impression_id"] == "their-imp-9"


def test_mirror_skips_are_inert_while_telemetry_is_off():
    svc = TradeService(players={p.id: p for p in _players()})
    with patch.object(tp, "telemetry_enabled", lambda: False):
        server._note_mirror_skip(svc, {"give_player_ids": [],
                                       "receive_player_ids": []},
                                 MagicMock(), ME, LEAGUE, "roster_changed")
    assert not getattr(svc, "_mirror_skips", None)


# ---------------------------------------------------------------------------
# Proposal telemetry (brief tests 17, 18, 19)
# ---------------------------------------------------------------------------

def _proposal_row(**over):
    row = {
        "proposal_event_id": "evt-1", "impression_id": None, "match_id": None,
        "user_id": ME, "league_id": LEAGUE, "target_user_id": OPP,
        "provider": "sleeper", "provider_transaction_id": "tx-1",
        "source": "deck", "give_asset_ids": json.dumps(["rb1"]),
        "receive_asset_ids": json.dumps(["rb2"]),
        "origin_trade_hash": "h-origin", "final_trade_hash": "h-final",
        "edited_from_source": 1, "valuation_json": None,
        "proposed_at": "2026-09-04T00:00:00+00:00",
    }
    row.update(over)
    return row


def test_a_confirmed_send_creates_exactly_one_idempotent_proposal_row(db):
    """Brief test 18. "If the provider succeeds but the database write is
    retried, `proposal_event_id` and, where available,
    `provider_transaction_id` must make the write idempotent." """
    first_id, created = db_module.save_trade_proposal(_proposal_row())
    assert created and first_id

    # Same event id — the retry case the key exists for.
    again_id, created = db_module.save_trade_proposal(_proposal_row())
    assert not created and again_id == first_id

    # Fresh event id but the SAME provider transaction — the second key.
    tx_id, created = db_module.save_trade_proposal(
        _proposal_row(proposal_event_id="evt-2"))
    assert not created and tx_id == first_id

    with db.connect() as conn:
        assert len(conn.execute(select(trade_proposals_table)).fetchall()) == 1


def test_a_genuinely_different_send_is_not_deduped(db):
    db_module.save_trade_proposal(_proposal_row())
    _id, created = db_module.save_trade_proposal(
        _proposal_row(proposal_event_id="evt-3", provider_transaction_id="tx-9"))
    assert created
    with db.connect() as conn:
        assert len(conn.execute(select(trade_proposals_table)).fetchall()) == 2


def test_an_edited_package_keeps_the_origin_link_and_differing_hashes(db):
    """Brief test 19. The user swapped an asset before sending: the
    originating impression is preserved, the two hashes differ, and
    `edited_from_source` says so."""
    imp = "imp-origin"
    with db.begin() as conn:
        conn.execute(text(
            "INSERT INTO deck_impressions (impression_id, user_id, league_id, "
            "deck_job_id, card_index, trade_hash, propensity, served_at) "
            "VALUES (:i, :u, :l, 'job', 0, 'origin-hash', 1.0, :t)"),
            {"i": imp, "u": ME, "l": LEAGUE,
             "t": datetime.now(timezone.utc).isoformat()})

    with patch.object(tp, "telemetry_enabled", lambda: True):
        server._record_trade_proposal(
            sess={}, provider="sleeper", user_id=ME, league_id=LEAGUE,
            target_user_id=OPP,
            give_asset_ids=["rb1", "te1"],   # te1 added after the suggestion
            receive_asset_ids=["rb2"],
            impression_id=imp, proposal_event_id="evt-edit",
            provider_transaction_id="tx-edit", source="calculator")

    with db.connect() as conn:
        row = dict(conn.execute(select(trade_proposals_table)).fetchone()._mapping)
    assert row["impression_id"] == imp
    assert row["origin_trade_hash"] == "origin-hash"
    assert row["final_trade_hash"] != "origin-hash"
    assert row["edited_from_source"] == 1
    assert json.loads(row["give_asset_ids"]) == ["rb1", "te1"]
    assert row["source"] == "calculator"


def test_proposal_recording_is_inert_while_telemetry_is_off(db):
    with patch.object(tp, "telemetry_enabled", lambda: False):
        server._record_trade_proposal(
            sess={}, provider="sleeper", user_id=ME, league_id=LEAGUE,
            target_user_id=OPP, give_asset_ids=["rb1"],
            receive_asset_ids=["rb2"], impression_id=None,
            proposal_event_id="evt-off")
    with db.connect() as conn:
        assert conn.execute(select(trade_proposals_table)).fetchall() == []


def test_a_failed_proposal_snapshot_still_records_the_send(db):
    """"Attempted or failed sends are not successful proposals" — but a
    successful send whose SNAPSHOT failed is still a proposal, and losing
    the row would understate the one metric that matters most."""
    tp.reset_health()
    with patch.object(tp, "telemetry_enabled", lambda: True), \
         patch.object(server, "_policy_context_from_session",
                      side_effect=RuntimeError("boom")):
        server._record_trade_proposal(
            sess={}, provider="mfl", user_id=ME, league_id=LEAGUE,
            target_user_id=OPP, give_asset_ids=["rb1"],
            receive_asset_ids=["rb2"], impression_id=None,
            proposal_event_id="evt-snapfail")
    with db.connect() as conn:
        row = conn.execute(select(trade_proposals_table)).fetchone()
    assert row is not None
    assert row.valuation_json is None
    assert tp.HEALTH["snapshot_failures"] == 1
    tp.reset_health()


# ---------------------------------------------------------------------------
# Match attribution (brief test 21)
# ---------------------------------------------------------------------------

def test_a_match_records_both_impressions_both_like_times_and_the_lag(db):
    """Brief test 21. A mutual trade is a SEQUENCE — user_b liked earlier,
    user_a is deciding now — and the row must preserve both moments rather
    than pretending they were simultaneous."""
    earlier = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    match = db_module.create_trade_match(
        league_id=LEAGUE, user_a_id=ME, user_b_id=OPP,
        user_a_give=["rb1"], user_a_receive=["rb2"],
        trade_concept_id="concept-1",
        user_a_impression_id="imp-a", user_b_impression_id="imp-b",
        first_like_at=earlier, match_valuation_json='{"schema_version":1}')

    with db.connect() as conn:
        row = dict(conn.execute(
            select(trade_matches_table).where(
                trade_matches_table.c.id == match["id"])).fetchone()._mapping)
    assert row["trade_concept_id"] == "concept-1"
    assert row["user_a_impression_id"] == "imp-a"
    assert row["user_b_impression_id"] == "imp-b"
    assert row["first_like_at"] == earlier
    assert row["second_like_at"] == row["matched_at"]
    assert row["match_latency_seconds"] == pytest.approx(6 * 3600, abs=60)
    assert json.loads(row["match_valuation_json"])["schema_version"] == 1


def test_a_legacy_match_leaves_the_new_fields_null(db):
    """Every pre-existing caller writes exactly the row it wrote before."""
    match = db_module.create_trade_match(
        league_id=LEAGUE, user_a_id=ME, user_b_id=OPP,
        user_a_give=["rb1"], user_a_receive=["rb2"])
    with db.connect() as conn:
        row = dict(conn.execute(
            select(trade_matches_table).where(
                trade_matches_table.c.id == match["id"])).fetchone()._mapping)
    for col in ("trade_concept_id", "user_a_impression_id",
                "user_b_impression_id", "first_like_at", "second_like_at",
                "match_latency_seconds", "match_valuation_json"):
        assert row[col] is None, col


def test_a_malformed_first_like_time_yields_a_null_latency_not_an_error(db):
    match = db_module.create_trade_match(
        league_id=LEAGUE, user_a_id=ME, user_b_id=OPP,
        user_a_give=["rb1"], user_a_receive=["rb2"],
        first_like_at="not-a-timestamp")
    with db.connect() as conn:
        row = conn.execute(select(trade_matches_table).where(
            trade_matches_table.c.id == match["id"])).fetchone()
    assert row.match_latency_seconds is None


def test_find_mirror_like_returns_the_counterpartys_row_not_just_a_bool(db):
    """`check_for_match` is now a thin wrapper over `find_mirror_like`, so
    the two can never disagree — and the detail is what makes the timing
    attribution possible at all."""
    liked_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db_module.save_trade_decision(
        OPP, LEAGUE, "t-mirror", ["rb2"], ["rb1"], "like",
        impression_id="their-imp", trade_concept_id="concept-9")
    with db.begin() as conn:
        conn.execute(text("UPDATE trade_decisions SET created_at = :t"),
                     {"t": liked_at})

    hit = db_module.find_mirror_like(ME, LEAGUE, OPP, ["rb1"], ["rb2"])
    assert hit is not None
    assert hit["impression_id"] == "their-imp"
    assert hit["trade_concept_id"] == "concept-9"
    assert hit["liked_at"] == liked_at
    assert hit["exact"] is True
    assert db_module.check_for_match(ME, LEAGUE, OPP, ["rb1"], ["rb2"]) is True

    assert db_module.find_mirror_like(ME, LEAGUE, OPP, ["rb1"], ["wr1"]) is None
    assert db_module.check_for_match(ME, LEAGUE, OPP, ["rb1"], ["wr1"]) is False


def test_a_decision_carries_its_impression_and_concept_id(db):
    db_module.save_trade_decision(
        ME, LEAGUE, "t1", ["rb1"], ["rb2"], "like",
        impression_id="imp-1", trade_concept_id="concept-1")
    with db.connect() as conn:
        row = conn.execute(text(
            "SELECT impression_id, trade_concept_id FROM trade_decisions"
        )).fetchone()
    assert row.impression_id == "imp-1"
    assert row.trade_concept_id == "concept-1"


def test_an_unowned_impression_id_is_never_written_onto_a_decision(db):
    """A client-supplied id is untrusted input. Writing an unvalidated one
    would let a client attribute its decision to somebody else's card."""
    with db.begin() as conn:
        conn.execute(text(
            "INSERT INTO deck_impressions (impression_id, user_id, league_id, "
            "deck_job_id, card_index, propensity, served_at) "
            "VALUES ('imp-theirs', 'someone_else', :l, 'job', 0, 1.0, :t)"),
            {"l": LEAGUE, "t": datetime.now(timezone.utc).isoformat()})
    with patch.object(tp, "telemetry_enabled", lambda: True):
        assert server._owned_impression_id("imp-theirs", ME) is None
        assert server._owned_impression_id("does-not-exist", ME) is None
        assert server._owned_impression_id(None, ME) is None
    with patch.object(tp, "telemetry_enabled", lambda: False):
        assert server._owned_impression_id("imp-theirs", "someone_else") is None


def test_conviction_requires_two_sided_gain_but_core_does_not():
    """The eligibility asymmetry, asserted directly. A Core card is
    market-plausible on its own and is NOT rejected for failing the policy's
    personal-gain test — rejecting it would delete ordinary fair trades under
    a value definition the generator never used (the engine's own surplus
    gate runs on MARGINAL values when `trade.marginal_value` is on). A
    below-Core card has only the two managers' agreement to justify it, so
    there the test bites."""
    _knobs(market_floor_absolute=0.50, market_floor_one_board=0.50,
           market_floor_two_board_base=0.50, market_core_ratio=0.80,
           personal_gain_min_frac=0.0)
    _job, _eng, rows, _s = run_job(telemetry=True, policy=False)
    snaps = [json.loads(r["valuation_json"]) for r in rows]
    two_board = [s for s in snaps
                 if s["policy"]["value_basis"] == tp.BASIS_TWO_BOARD]
    assert two_board

    for s in two_board:
        lane = s["policy"]["eligibility_lane"]
        opp = s["mutual"]["personal_opportunity"]
        if lane == tp.LANE_CONVICTION:
            assert opp is not None and opp >= 0.0, s["market"]
        if s["policy"]["rejection_reason"] == tp.REASON_NO_MUTUAL_GAIN:
            # Only ever applied below the Core boundary.
            assert s["market"]["ratio"] < 0.80


def test_removing_the_choke_point_would_be_caught():
    """Sabotage discipline (tests/CLAUDE.md § Conventions). Neutering
    `_evaluate_deck_policy` to a pass-through — the single most likely way
    for this feature to silently stop working — must break the floor
    guarantee. If this test can be deleted without any other test failing,
    the choke point is not load-bearing."""
    _knobs(market_floor_absolute=0.98, market_floor_one_board=0.98,
           market_floor_two_board_base=0.98)
    real_job, _e1, real_rows, _s1 = run_job(telemetry=True, policy=True)

    sabotage = patch.object(
        server, "_evaluate_deck_policy",
        lambda cards, ctx, **kw: (cards, {}, []))
    _job, _e2, sabotaged_rows, sabotaged_shadow = run_job(
        telemetry=True, policy=True, extra_patches=[sabotage])

    assert len(sabotaged_rows) > len(real_rows), \
        "the choke point must be what removes the below-floor cards"
    assert sabotaged_shadow == [], \
        "and what records the rejections"


def test_every_mutation_path_re_asks_the_evaluator():
    """Brief test 10, as a source pin.

    A behavioural test cannot easily force each of the five in-generator
    gates on one fixture, but the failure mode is deletion, not subtlety: the
    likely regression is somebody removing a re-gate while refactoring a
    sweetener. Each site is pinned by name, with the enclosing function
    checked so the assertion cannot be satisfied by an unrelated occurrence.

    The behavioural half — that the choke point downstream catches whatever
    these miss — is `test_removing_the_choke_point_would_be_caught`.
    """
    import inspect
    import backend.trade_service as ts_mod
    import backend.trade_optimizer as opt

    v2 = inspect.getsource(ts_mod.TradeService._generate_for_pair_v2)
    # the candidate loop and the gap-sweetener re-gate
    assert v2.count("_policy_eval is not None") >= 2, (
        "v2 must re-ask the evaluator in BOTH _consider and _gap_extra_ok — "
        "a sweetener changes the package, so the pre-mutation verdict is void")
    assert "_gap_extra_ok" in v2

    v3 = inspect.getsource(opt.generate_pair_trades_v3)
    # candidate loop + §3.4 sweetener + gap sweetener
    assert v3.count("_policy_eval is not None") >= 3, (
        "v3 must re-ask in the candidate loop, the 3.4 sweetener pass and "
        "_gap_extra_ok")

    # …and the legacy divergence composition is behind the flag in both.
    for src in (v2, v3):
        assert "fairness_floor_divergence" in src
        assert "_policy_on" in src, (
            "the min(requested, fairness_floor_divergence) composition must be "
            "guarded — under the policy the request is composed with max()")


def test_a_confirmed_send_labels_its_impression_exactly_once(db):
    """Brief test 17. A confirmed provider proposal creates exactly ONE
    impression-linked `propose` outcome when it originated from a card — and
    exactly one `trade_proposals` row alongside it. The two writes are
    independent (`_save_deck_outcome_safe` and `_record_trade_proposal`), so
    a test that only counted one of them would miss half the contract."""
    from backend.database import deck_outcomes_table
    imp = "imp-propose-once"
    # The impression's hash is minted by the SAME function the proposal path
    # uses, which is the point: a second hash implementation would make
    # `edited_from_source` fire on every unedited send.
    origin_hash = server._deck_trade_hash(["rb1"], ["rb2"], OPP)
    with db.begin() as conn:
        conn.execute(text(
            "INSERT INTO deck_impressions (impression_id, user_id, league_id, "
            "deck_job_id, card_index, trade_hash, propensity, served_at) "
            "VALUES (:i, :u, :l, 'job', 0, :h, 1.0, :t)"),
            {"i": imp, "u": ME, "l": LEAGUE, "h": origin_hash,
             "t": datetime.now(timezone.utc).isoformat()})

    with patch.object(tp, "telemetry_enabled", lambda: True), \
         patch.object(server, "_deck_signal_v2_enabled", lambda: True):
        server._save_deck_outcome_safe(imp, "propose", acting_user_id=ME)
        server._record_trade_proposal(
            sess={}, provider="sleeper", user_id=ME, league_id=LEAGUE,
            target_user_id=OPP, give_asset_ids=["rb1"],
            receive_asset_ids=["rb2"], impression_id=imp,
            proposal_event_id="evt-once", provider_transaction_id="tx-once")

    with db.connect() as conn:
        outcomes = conn.execute(select(deck_outcomes_table).where(
            deck_outcomes_table.c.impression_id == imp)).fetchall()
        proposals = conn.execute(select(trade_proposals_table)).fetchall()
    assert [r.action for r in outcomes] == ["propose"]
    assert len(proposals) == 1
    assert proposals[0].impression_id == imp
    assert proposals[0].origin_trade_hash == origin_hash
    assert proposals[0].final_trade_hash == origin_hash
    assert proposals[0].edited_from_source == 0, (
        "an UNEDITED send must not read as edited — if this fails, the "
        "suggestion-time and proposal-time hashes have drifted apart and "
        "every send would be mis-attributed as an edit")
