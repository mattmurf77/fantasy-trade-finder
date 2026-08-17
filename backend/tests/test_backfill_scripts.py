"""Organic-trade backfill scripts (operator directive 2026-08-16):
scripts/backfill_sleeper_trades.py + scripts/backfill_suggestion_links.py.

Covers:
  • previous_league_id chain walking — depth cap, "0"/null terminators,
    mid-chain fetch-failure resilience (mock opener, house pattern);
  • sweep dry-run writes nothing / real run is idempotent across re-runs;
  • retro exact-hash linking — exact match via the imported server-side
    _deck_trade_hash (players + owned-pick pseudo-ids), direction
    sensitivity, lookback window edges, ghost-vs-rendered split,
    idempotency, never-overwriting rows the live matcher already wrote;
  • retro dry-run writes nothing; telemetry-era trades left to the live
    matcher.

Harness: test_market_data_readiness / test_suggestion_telemetry pattern —
isolated in-memory SQLite patched into backend.database, fake urlopen
injected via each helper's `_opener` seam.
"""

import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
from backend.database import (
    deck_impressions_table,
    metadata,
    save_suggestion_trade_links,
    sleeper_trades_table,
    suggestion_trade_links_table,
)
from backend.server import _deck_trade_hash

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import backfill_sleeper_trades as bst  # noqa: E402
import backfill_suggestion_links as bsl  # noqa: E402

LEAGUE = "5550001112223334445"
ME, OPP = "user_me", "user_opp"
ROSTER_MAP = {"1": ME, "2": OPP}

TRADED_AT = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _opener_for(routes: dict):
    """Fake urlopen keyed by URL suffix; unmatched transaction URLs get [],
    unmatched league-object URLs raise (like a Sleeper 404)."""
    def _open(request, timeout=15):
        url = request.full_url
        for suffix, payload in routes.items():
            if url.endswith(suffix):
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResponse(json.dumps(payload).encode("utf-8"))
        if "/transactions/" in url:
            return _FakeResponse(b"[]")
        raise OSError(f"unrouted url: {url}")
    return _open


def _league_obj(lid: str, season: str, prev: str | None) -> dict:
    return {"league_id": lid, "season": season, "previous_league_id": prev}


# ---------------------------------------------------------------------------
# Chain walking
# ---------------------------------------------------------------------------

def test_chain_walk_caps_at_max_prior_seasons():
    opener = _opener_for({
        "/league/100": _league_obj("100", "2026", "99"),
        "/league/99":  _league_obj("99",  "2025", "98"),
        "/league/98":  _league_obj("98",  "2024", "97"),
        "/league/97":  _league_obj("97",  "2023", "96"),
        "/league/96":  _league_obj("96",  "2022", "95"),   # never reached
    })
    chain = bst.walk_prior_chain("100", max_prior=3, _opener=opener)
    assert chain == [("100", "2026"), ("99", "2025"),
                     ("98", "2024"), ("97", "2023")]


def test_chain_walk_stops_at_zero_previous_league_id():
    opener = _opener_for({
        "/league/100": _league_obj("100", "2026", "99"),
        "/league/99":  _league_obj("99",  "2025", "0"),
    })
    chain = bst.walk_prior_chain("100", max_prior=3, _opener=opener)
    assert chain == [("100", "2026"), ("99", "2025")]


def test_chain_walk_survives_mid_chain_fetch_failure():
    opener = _opener_for({
        "/league/100": _league_obj("100", "2026", "99"),
        "/league/99":  OSError("sleeper flake"),
    })
    chain = bst.walk_prior_chain("100", max_prior=3, _opener=opener)
    assert chain == [("100", "2026")]


def test_chain_walk_root_fetch_failure_still_returns_root():
    opener = _opener_for({"/league/100": OSError("down")})
    chain = bst.walk_prior_chain("100", max_prior=3, _opener=opener)
    assert chain == [("100", None)]


# ---------------------------------------------------------------------------
# Sweep — dry-run writes nothing; real run idempotent
# ---------------------------------------------------------------------------

def _completed_trade(txid: str) -> dict:
    return {
        "type": "trade", "status": "complete", "transaction_id": txid,
        "leg": 3, "status_updated": int(TRADED_AT.timestamp() * 1000),
        "roster_ids": [1, 2],
        "adds": {"4034": 1, "6786": 2},
        "drops": {"4034": 2, "6786": 1},
        "draft_picks": [], "waiver_budget": [],
    }


def _txn_opener(txid: str):
    return _opener_for({"/transactions/3": [_completed_trade(txid)]})


def test_sweep_dry_run_writes_nothing(mem_engine):
    found, new, failed = bst.sweep_league(
        LEAGUE, dry_run=True, _opener=_txn_opener("t1"))
    assert (found, new, failed) == (1, 1, 0)
    with mem_engine.connect() as conn:
        assert conn.execute(select(sleeper_trades_table)).fetchall() == []


def test_sweep_real_run_is_idempotent(mem_engine):
    found, new, _ = bst.sweep_league(
        LEAGUE, dry_run=False, _opener=_txn_opener("t1"))
    assert (found, new) == (1, 1)
    found2, new2, _ = bst.sweep_league(
        LEAGUE, dry_run=False, _opener=_txn_opener("t1"))
    assert (found2, new2) == (1, 0)
    with mem_engine.connect() as conn:
        rows = conn.execute(select(sleeper_trades_table)).fetchall()
    assert len(rows) == 1 and rows[0].league_id == LEAGUE


def test_sweep_counts_failed_weeks_and_keeps_going(mem_engine):
    routes = {"/transactions/3": [_completed_trade("t9")],
              "/transactions/5": OSError("flake")}
    found, new, failed = bst.sweep_league(
        LEAGUE, dry_run=False, _opener=_opener_for(routes))
    assert (found, new, failed) == (1, 1, 1)


# ---------------------------------------------------------------------------
# Retro linking — fixtures
# ---------------------------------------------------------------------------

def _store_trade(txid: str, *, adds=None, picks=None, roster_ids=(1, 2),
                 traded_at: datetime = TRADED_AT) -> dict:
    """Insert one captured sleeper_trades row; returns the row dict."""
    row = {
        "transaction_id": txid, "league_id": LEAGUE, "week": 3,
        "traded_at": traded_at.isoformat(),
        "synced_at": traded_at.isoformat(),
        "roster_ids": json.dumps(list(roster_ids)),
        "adds": json.dumps(adds or {}),
        "drops": json.dumps({}),
        "draft_picks": json.dumps(picks or []),
        "waiver_budget": json.dumps([]),
        "raw": json.dumps({}),
    }
    with db_module.engine.begin() as conn:
        conn.execute(insert(sleeper_trades_table), [row])
    return row


def _store_impression(imp_id: str, *, user_id: str, trade_hash: str,
                      served_at: datetime, is_ghost: int | None = None):
    with db_module.engine.begin() as conn:
        conn.execute(insert(deck_impressions_table), [{
            "impression_id": imp_id, "user_id": user_id, "league_id": LEAGUE,
            "deck_job_id": "job-x", "card_index": 0, "trade_hash": trade_hash,
            "propensity": 1.0, "served_at": served_at.isoformat(),
            "is_ghost": is_ghost,
        }])


# me (roster 1) sends p_me, receives p_opp from opp (roster 2).
ADDS = {"p_me": 2, "p_opp": 1}
HASH_TO_ME = _deck_trade_hash(["p_me"], ["p_opp"], OPP)   # served to ME
HASH_TO_OPP = _deck_trade_hash(["p_opp"], ["p_me"], ME)   # served to OPP


def _link(*, dry_run=False, cutoff=None):
    return bsl.link_league(LEAGUE, dry_run=dry_run, cutoff_iso=cutoff,
                           lookback_days=14, roster_map=dict(ROSTER_MAP))


def _stored_links(conn):
    return conn.execute(select(suggestion_trade_links_table)).fetchall()


# ---------------------------------------------------------------------------
# Retro linking — behavior
# ---------------------------------------------------------------------------

def test_retro_exact_match_links_and_marks_retro(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=2))
    stats = _link()
    assert stats["recommended"] == 1 and stats["written"] == 1
    with mem_engine.connect() as conn:
        (row,) = _stored_links(conn)
    assert row.was_recommended == 1
    assert row.matched_impression_id == "imp1"
    assert row.match_type == "retro_exact"
    assert row.overlap_score == 1.0


def test_retro_matches_mirror_direction_served_to_partner(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=OPP, trade_hash=HASH_TO_OPP,
                      served_at=TRADED_AT - timedelta(days=1))
    stats = _link()
    assert stats["recommended"] == 1


def test_retro_rejects_hash_served_to_wrong_user(mem_engine):
    # HASH_TO_ME on an impression served to OPP: direction disagrees — the
    # give/receive perspective doesn't belong to that user. No link.
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=OPP, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=1))
    stats = _link()
    assert stats["recommended"] == 0 and stats["no_match"] == 1


def test_retro_matches_owned_pick_pseudo_ids(mem_engine):
    pick = {"season": "2027", "round": 1, "roster_id": 2,
            "previous_owner_id": 2, "owner_id": 1}
    _store_trade("tx1", adds={"p_me": 2}, picks=[pick])
    # me sends p_me; opp sends their own 2027 1st (pick pseudo-id).
    pick_id = f"{LEAGUE}_2027_1_2"
    h = _deck_trade_hash(["p_me"], [pick_id], OPP)
    _store_impression("imp1", user_id=ME, trade_hash=h,
                      served_at=TRADED_AT - timedelta(days=3))
    stats = _link()
    assert stats["recommended"] == 1


def test_retro_window_excludes_served_before_lookback(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=14, seconds=1))
    stats = _link()
    assert stats["recommended"] == 0 and stats["no_match"] == 1


def test_retro_window_excludes_served_after_execution(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT + timedelta(seconds=1))
    stats = _link()
    assert stats["recommended"] == 0 and stats["no_match"] == 1


def test_retro_picks_most_recent_and_splits_ghost(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("old", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=5))
    _store_impression("new", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=1))
    _store_impression("ghost", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=2), is_ghost=1)
    stats = _link()
    assert stats["recommended"] == 1 and stats["ghost"] == 1
    with mem_engine.connect() as conn:
        (row,) = _stored_links(conn)
    assert row.matched_impression_id == "new"
    assert row.ghost_impression_id == "ghost"
    assert row.ghost_match_type == "retro_exact"


def test_retro_multi_team_trade_gets_denominator_row(mem_engine):
    _store_trade("tx1", adds={"p1": 1, "p2": 2, "p3": 3}, roster_ids=(1, 2, 3))
    stats = _link()
    assert stats["no_match"] == 1 and stats["written"] == 1
    with mem_engine.connect() as conn:
        (row,) = _stored_links(conn)
    assert row.was_recommended == 0 and row.match_type is None


def test_retro_is_idempotent_across_reruns(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=2))
    assert _link()["written"] == 1
    stats2 = _link()
    assert stats2["unlinked"] == 0 and stats2["written"] == 0
    with mem_engine.connect() as conn:
        assert len(_stored_links(conn)) == 1


def test_retro_never_overwrites_live_matcher_rows(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=2))
    # Live matcher already examined this trade (no-match denominator row).
    save_suggestion_trade_links([{
        "transaction_id": "tx1", "league_id": LEAGUE, "was_recommended": 0,
        "matched_impression_id": None, "match_type": None,
        "overlap_score": None, "ghost_impression_id": None,
        "ghost_match_type": None, "ghost_overlap_score": None,
        "traded_at": TRADED_AT.isoformat(), "computed_at": "2026-08-16T00:00:00+00:00",
    }])
    stats = _link()
    assert stats["unlinked"] == 0 and stats["written"] == 0
    with mem_engine.connect() as conn:
        (row,) = _stored_links(conn)
    assert row.match_type is None and row.was_recommended == 0


def test_retro_dry_run_writes_nothing(mem_engine):
    _store_trade("tx1", adds=ADDS)
    _store_impression("imp1", user_id=ME, trade_hash=HASH_TO_ME,
                      served_at=TRADED_AT - timedelta(days=2))
    stats = _link(dry_run=True)
    assert stats["recommended"] == 1 and stats["written"] == 0
    with mem_engine.connect() as conn:
        assert _stored_links(conn) == []


def test_retro_skips_telemetry_era_trades_for_live_matcher(mem_engine):
    _store_trade("tx1", adds=ADDS)  # traded_at = TRADED_AT
    cutoff = (TRADED_AT - timedelta(days=1)).isoformat()
    stats = _link(cutoff=cutoff)
    assert stats["skipped_telemetry_era"] == 1 and stats["examined"] == 0
    with mem_engine.connect() as conn:
        assert _stored_links(conn) == []


def test_telemetry_start_iso_reads_first_assets_json_row(mem_engine):
    assert bsl.telemetry_start_iso() is None
    with db_module.engine.begin() as conn:
        conn.execute(insert(deck_impressions_table), [
            {"impression_id": "a", "user_id": ME, "league_id": LEAGUE,
             "deck_job_id": "j", "card_index": 0, "propensity": 1.0,
             "served_at": "2026-08-10T00:00:00+00:00", "assets_json": None},
            {"impression_id": "b", "user_id": ME, "league_id": LEAGUE,
             "deck_job_id": "j", "card_index": 1, "propensity": 1.0,
             "served_at": "2026-08-16T09:00:00+00:00",
             "assets_json": json.dumps({"give": [], "receive": []})},
        ])
    assert bsl.telemetry_start_iso() == "2026-08-16T09:00:00+00:00"
