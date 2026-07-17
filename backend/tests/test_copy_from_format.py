"""Value-aware cross-format copy (#124/#139).

POST /api/tiers/copy-from-format used to preserve each player's tier
LABEL across formats — but the labels are pick-denominated ("worth 4+
firsts") and the formats' value curves differ, so a label-preserving
copy systematically overvalued QBs on SF→1QB and undervalued them on
1QB→SF. The fix: preserve the user's per-position RANK ORDER and
re-seed the value magnitudes from the TARGET format's consensus seed
Elos at those ranks (RankingService.apply_value_map — a permutation of
the copied group's own target-format seeds).

Pins:
  * SF→1QB demotes QBs relative to non-QBs (tier labels drop; the
    QB/WR cross-position ordering flips to the target consensus).
  * 1QB→SF promotes QBs (both directions).
  * Rank order within a position is preserved exactly — including a
    user's manual (override) ordering that disagrees with consensus.
  * Re-copying an unchanged source board is idempotent.
  * Route contract: {ok, from_format, to_format, mapping: 'value_rank',
    position_counts, total} + overrides persisted per target format.

Elo landmarks (tier_config.json — bands are position/format-uniform):
  firsts_4plus ≥1927, firsts_3 ≥1869, firsts_2 ≥1788, first_1 ≥1580,
  second ≥1400, third ≥1280, fourth ≥1220, waivers ≥1150, below → None.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend.database import metadata, users_table
from backend.ranking_service import Player, RankingService

USER = "313560442465169408"

# Consensus seed maps. The SF curve puts QBs on top (superflex premium);
# the 1QB curve drops them well below the elite WRs — mirroring the real
# DynastyProcess distributions (e.g. 2026-07-10 snapshot: SF QB1 seed
# ≈1927 = firsts_4plus, 1QB QB1 seed ≈1854 = firsts_2).
SF_SEEDS = {
    "qb1": 1940.0,  # firsts_4plus
    "qb2": 1900.0,  # firsts_3
    "qb3": 1795.0,  # firsts_2
    "wr1": 1905.0,  # firsts_3
    "wr2": 1790.0,  # firsts_2
    "wrX": 1100.0,  # below waivers floor — not on the board
}
ONEQB_SEEDS = {
    "qb1": 1850.0,  # firsts_2
    "qb2": 1770.0,  # first_1
    "qb3": 1500.0,  # second
    "wr1": 1920.0,  # firsts_3
    "wr2": 1800.0,  # firsts_2
    "wrX": 1100.0,
}


def _players():
    return [
        Player(id="qb1", name="QB One",   position="QB", team="AAA", age=25),
        Player(id="qb2", name="QB Two",   position="QB", team="BBB", age=26),
        Player(id="qb3", name="QB Three", position="QB", team="CCC", age=27),
        Player(id="wr1", name="WR One",   position="WR", team="DDD", age=24),
        Player(id="wr2", name="WR Two",   position="WR", team="EEE", age=25),
        Player(id="wrX", name="WR Waiver", position="WR", team="FFF", age=29),
    ]


def _svc(seeds, fmt):
    svc = RankingService(players=_players(), seed_ratings=dict(seeds))
    svc._scoring_format = fmt
    return svc


def _tier(elo, pos, fmt):
    return RankingService.tier_for_elo(elo, pos, fmt)


# ---------------------------------------------------------------------------
# Unit: RankingService.apply_value_map
# ---------------------------------------------------------------------------

class TestApplyValueMap:
    def test_permutes_target_seeds_in_given_order(self):
        to_svc = _svc(ONEQB_SEEDS, "1qb_ppr")
        n = to_svc.apply_value_map("QB", ["qb1", "qb2", "qb3"])
        assert n == 3
        ov = to_svc._elo_overrides
        # Rank i gets the group's i-th largest 1QB seed.
        assert ov["qb1"] == pytest.approx(1850.0)
        assert ov["qb2"] == pytest.approx(1770.0)
        assert ov["qb3"] == pytest.approx(1500.0)

    def test_user_order_beats_consensus_order(self):
        # Source board has qb2 ahead of qb1 — qb2 must get the higher seed.
        to_svc = _svc(ONEQB_SEEDS, "1qb_ppr")
        to_svc.apply_value_map("QB", ["qb2", "qb1", "qb3"])
        ov = to_svc._elo_overrides
        assert ov["qb2"] == pytest.approx(1850.0)
        assert ov["qb1"] == pytest.approx(1770.0)
        assert ov["qb2"] > ov["qb1"] > ov["qb3"]

    def test_tie_break_keeps_strict_order(self):
        seeds = dict(ONEQB_SEEDS, qb1=1700.0, qb2=1700.0, qb3=1700.0)
        to_svc = _svc(seeds, "1qb_ppr")
        to_svc.apply_value_map("QB", ["qb3", "qb1", "qb2"])
        ov = to_svc._elo_overrides
        assert ov["qb3"] > ov["qb1"] > ov["qb2"]

    def test_unknown_ids_skipped_and_counted(self):
        to_svc = _svc(ONEQB_SEEDS, "1qb_ppr")
        n = to_svc.apply_value_map("QB", ["qb1", "nope", "qb2"])
        assert n == 2
        assert "nope" not in to_svc._elo_overrides

    def test_empty_is_noop(self):
        to_svc = _svc(ONEQB_SEEDS, "1qb_ppr")
        v = to_svc._version
        assert to_svc.apply_value_map("QB", []) == 0
        assert to_svc._elo_overrides == {}
        assert to_svc._version == v


# ---------------------------------------------------------------------------
# Route: POST /api/tiers/copy-from-format
# ---------------------------------------------------------------------------

def _headers(token, to_format):
    return {
        "X-Session-Token": token,
        "X-Scoring-Format": to_format,
        "Content-Type": "application/json",
    }


@pytest.fixture()
def ctx():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(sleeper_user_id=USER))

    from_svc = _svc(SF_SEEDS, "sf_tep")
    to_svc = _svc(ONEQB_SEEDS, "1qb_ppr")

    token = "copyfmt-tok"
    sess = {
        "user_id":       USER,
        "league":        SimpleNamespace(league_id="league_demo"),
        "players":       _players(),
        "services":      {"sf_tep": from_svc, "1qb_ppr": to_svc},
        "trade_svcs":    {"sf_tep": object(), "1qb_ppr": object()},
        "active_format": "1qb_ppr",
        "verified":      True,   # bypass the unverified-write gate
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield SimpleNamespace(client=client, token=token, engine=engine,
                                  from_svc=from_svc, to_svc=to_svc, sess=sess)
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _copy(ctx_, from_format, to_format):
    return ctx_.client.post(
        "/api/tiers/copy-from-format",
        headers=_headers(ctx_.token, to_format),
        data=json.dumps({"from_format": from_format, "to_format": to_format}),
    )


class TestCopyRouteSFto1QB:
    def test_contract_and_counts(self, ctx):
        r = _copy(ctx, "sf_tep", "1qb_ppr")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["mapping"] == "value_rank"
        assert body["from_format"] == "sf_tep"
        assert body["to_format"] == "1qb_ppr"
        # wrX sits below the SF waivers floor → not part of the board copy.
        assert body["position_counts"] == {"QB": 3, "WR": 2}
        assert body["total"] == 5

    def test_qbs_demoted_relative_to_wrs(self, ctx):
        _copy(ctx, "sf_tep", "1qb_ppr")
        ov = ctx.to_svc._elo_overrides
        # Source (SF): qb1 was the top asset overall, a tier above wr1.
        assert SF_SEEDS["qb1"] > SF_SEEDS["wr1"]
        assert _tier(SF_SEEDS["qb1"], "QB", "sf_tep") == "firsts_4plus"
        # Target (1QB): tier labels re-seeded from 1QB consensus — qb1
        # drops two rungs and falls below wr1.
        assert _tier(ov["qb1"], "QB", "1qb_ppr") == "firsts_2"
        assert _tier(ov["qb2"], "QB", "1qb_ppr") == "first_1"
        assert _tier(ov["qb3"], "QB", "1qb_ppr") == "second"
        assert ov["qb1"] < ov["wr1"]
        # WRs hold roughly steady (their curves match across formats).
        assert _tier(ov["wr1"], "WR", "1qb_ppr") == "firsts_3"
        assert _tier(ov["wr2"], "WR", "1qb_ppr") == "firsts_2"

    def test_rank_order_within_position_preserved(self, ctx):
        # User's SF board disagrees with consensus: qb2 pinned above qb1.
        ctx.from_svc._elo_overrides = {"qb2": 1950.0, "qb1": 1935.0}
        _copy(ctx, "sf_tep", "1qb_ppr")
        ov = ctx.to_svc._elo_overrides
        assert ov["qb2"] > ov["qb1"] > ov["qb3"]
        # qb2 inherits the group's best 1QB seed value.
        assert ov["qb2"] == pytest.approx(1850.0)

    def test_below_board_player_not_copied(self, ctx):
        _copy(ctx, "sf_tep", "1qb_ppr")
        assert "wrX" not in ctx.to_svc._elo_overrides

    def test_recopy_is_idempotent(self, ctx):
        _copy(ctx, "sf_tep", "1qb_ppr")
        first = dict(ctx.to_svc._elo_overrides)
        r = _copy(ctx, "sf_tep", "1qb_ppr")
        assert r.status_code == 200
        assert ctx.to_svc._elo_overrides == first

    def test_overrides_persisted_per_format(self, ctx):
        _copy(ctx, "sf_tep", "1qb_ppr")
        stored = db_module.load_tier_overrides(USER, scoring_format="1qb_ppr")
        assert stored == pytest.approx(ctx.to_svc._elo_overrides)
        assert db_module.load_tier_overrides(USER, scoring_format="sf_tep") == {}
        # All touched positions marked saved for the target format.
        assert set(db_module.get_tiers_saved(USER, scoring_format="1qb_ppr")) == {"QB", "WR"}

    def test_wholesale_replace_drops_stale_target_overrides(self, ctx):
        ctx.to_svc._elo_overrides = {"wrX": 1900.0}   # stale target-only override
        _copy(ctx, "sf_tep", "1qb_ppr")
        assert "wrX" not in ctx.to_svc._elo_overrides


class TestCopyRoute1QBtoSF:
    def test_qbs_promoted(self, ctx):
        ctx.sess["active_format"] = "sf_tep"
        r = _copy(ctx, "1qb_ppr", "sf_tep")
        assert r.status_code == 200
        ov = ctx.from_svc._elo_overrides   # sf_tep is the target here
        # 1QB board had wr1 as the top asset; in SF the QB group's own
        # seed curve tops the board again.
        assert _tier(ONEQB_SEEDS["qb1"], "QB", "1qb_ppr") == "firsts_2"
        assert _tier(ov["qb1"], "QB", "sf_tep") == "firsts_4plus"
        assert ov["qb1"] > ov["wr1"]
        assert ov["qb1"] > ov["qb2"] > ov["qb3"]


class TestCopyRouteValidation:
    def test_same_format_rejected(self, ctx):
        r = _copy(ctx, "1qb_ppr", "1qb_ppr")
        assert r.status_code == 400

    def test_bad_format_rejected(self, ctx):
        r = _copy(ctx, "half_ppr", "1qb_ppr")
        assert r.status_code == 400
