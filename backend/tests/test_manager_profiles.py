"""Manager revealed-preference profiles (docs/plans/manager-profiles/).

Pins, offline (committed fixture + the `_opener` seam of
`sleeper_trades_service.fetch_week_transactions`, no network):

  * parsing — terminal waiver / free-agent rows only; FAAB bid from
    settings.waiver_bid; failed-claim reason kept; pending rows skipped
  * winning and losing bids — dollars, share of budget, share of remaining
    budget (trade FAAB included), the clearing price of an outbid claim,
    and non-valuation failures kept apart
  * identity — a co-owner's claim lands on the roster owner's profile (no
    second row); an ownerless roster gets no row; a non-owner's move is
    excluded and counted
  * a manager with no history gets a row of zeros
  * the sweep — first pass backfills, re-sweeps are idempotent, a backfill
    that lost a leg writes no profile and is retried
  * flag off (profiles=False, or no roster map) — no rows, no extra fetches
  * session_init — the flag gates the daemon wiring
  * the leaf stays a leaf
"""

import ast
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

import backend.database as db_module
import backend.sleeper_trades_service as svc
from backend import manager_profiles as mp
from backend.database import (
    load_manager_profiles,
    manager_profiles_table,
    metadata,
    record_sleeper_trades,
    sleeper_waiver_moves_table,
)

FIX = Path(__file__).parent / "fixtures" / "sleeper" / "manager-profiles"
LEAGUE = "1000000000000000001"
U1, U2, U2_CO, U3 = ("9000000000000000001", "9000000000000000002",
                     "9000000000000000022", "9000000000000000003")
NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _load(name):
    return json.loads((FIX / name).read_text())


ROSTERS = _load("rosters.json")
META = _load("league.json")
PLAYERS = _load("players.json")
WEEK = {1: _load("transactions_1.json"), 2: _load("transactions_2.json")}


def _players_fn(ids):
    return {i: PLAYERS[i] for i in ids if i in PLAYERS}


def _all_txns():
    return WEEK[1] + WEEK[2]


def _profiles(**overrides):
    txns = _all_txns()
    kwargs = dict(
        trades=[t for t in txns if t["type"] == "trade"],
        moves=[t for t in txns if t["type"] != "trade"],
        rosters=ROSTERS, players=PLAYERS, league_meta=META, now=NOW)
    kwargs.update(overrides)
    rows = mp.build_league_profiles(LEAGUE, **kwargs)
    return {r["owner_id"]: dict(r, profile=json.loads(r["profile"])) for r in rows}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class _Opener:
    """Fake urlopen: serves the fixture legs, counts every call, and can be
    told to fail one leg."""

    def __init__(self, fail_week=None):
        self.calls = []
        self.fail_week = fail_week

    def __call__(self, request, timeout=15):
        week = int(request.full_url.rsplit("/", 1)[-1])
        self.calls.append(week)
        if week == self.fail_week:
            raise OSError("synthetic leg failure")
        return _Resp(json.dumps(WEEK.get(week, [])).encode("utf-8"))


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    yield eng
    eng.dispose()


def _count(eng, table):
    with eng.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


def _sync(opener, **kw):
    kw.setdefault("profiles", True)
    kw.setdefault("rosters", ROSTERS)
    kw.setdefault("league_meta", META)
    kw.setdefault("players_fn", _players_fn)
    return svc.sync_league_trades(LEAGUE, _opener=opener, **kw)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_keeps_terminal_waiver_and_free_agent_rows_only():
    rows = mp.parse_waiver_transactions(WEEK[1], LEAGUE, now=NOW)
    by_id = {r["transaction_id"]: r for r in rows}
    # 3 terminal waivers + 2 free agents; the trades and both pending rows go.
    assert set(by_id) == {"7000000000000000011", "7000000000000000012",
                          "7000000000000000013", "7000000000000000021",
                          "7000000000000000022"}
    won = by_id["7000000000000000011"]
    assert (won["type"], won["status"], won["waiver_bid"], won["roster_id"],
            won["failure_note"]) == ("waiver", "complete", 30, 1, None)
    lost = by_id["7000000000000000012"]
    assert lost["status"] == "failed" and lost["waiver_bid"] == 25
    assert lost["failure_note"] == "This player was claimed by another owner."
    assert lost["creator"] == U2_CO
    fa = by_id["7000000000000000021"]
    assert fa["waiver_bid"] is None and json.loads(fa["adds"]) == {"TB": 1}
    assert won["processed_at"].startswith("2026-")
    assert json.loads(won["raw"])["settings"]["waiver_bid"] == 30


def test_parse_tolerates_garbage():
    assert mp.parse_waiver_transactions(None, LEAGUE) == []
    assert mp.parse_waiver_transactions(
        ["x", {"type": "waiver", "status": "complete"}], LEAGUE) == []


# ---------------------------------------------------------------------------
# Winning and failed bids
# ---------------------------------------------------------------------------

def test_winning_bids_priced_against_budget_and_remaining():
    wb = _profiles()[U1]["profile"]["waiver_bids"]
    assert wb["faab"] is True and wb["budget"] == 100
    assert (wb["n"], wb["won"], wb["outbid"], wb["failed_other"]) == (2, 2, 0, 0)
    assert wb["spent"] == 80 and wb["reported_spent"] == 80
    first, second = wb["bids"]
    # Before the first run: 100 budget + $10 received in the trade.
    assert (first["player_id"], first["bid"], first["share_of_budget"]) == ("1005", 30, 0.3)
    assert first["share_of_remaining"] == round(30 / 110, 4)
    # Before the second: 100 − 30 won + 10 = 80.
    assert (second["player_id"], second["position"]) == ("1003", "WR")
    assert second["share_of_remaining"] == 0.625
    assert wb["median_won_share"] == 0.4 and wb["max_share"] == 0.5
    assert wb["usable"] is False            # 2 bids < MIN_FAAB_BIDS


def test_failed_bids_split_outbid_from_other_failures():
    wb = _profiles()[U2]["profile"]["waiver_bids"]
    assert (wb["n"], wb["won"], wb["outbid"], wb["failed_other"]) == (2, 0, 1, 1)
    outbid = next(b for b in wb["bids"] if b["outcome"] == "outbid")
    # Lost $25 to roster 1's $30 on the same player in the same run.
    assert (outbid["player_id"], outbid["bid"], outbid["clearing_bid"]) == ("1005", 25, 30)
    other = next(b for b in wb["bids"] if b["outcome"] == "failed")
    assert other["clearing_bid"] is None and other["bid"] == 5
    assert wb["spent"] == 0 and wb["median_won_share"] is None


def test_non_faab_league_records_claims_without_pricing():
    meta = {"settings": {"waiver_type": 0, "waiver_budget": 100}}
    wb = _profiles(league_meta=meta)[U1]["profile"]["waiver_bids"]
    assert wb["faab"] is False and wb["budget"] is None
    assert wb["n"] == 0 and wb["bids"] == [] and wb["claims_without_bid"] == 2


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def test_trade_style_assets_and_activity():
    p1 = _profiles()[U1]["profile"]
    p2 = _profiles()[U2]["profile"]
    assert p1["trade_style"]["picks_for_players"] == 1
    assert p2["trade_style"]["players_for_picks"] == 1
    assert p1["trade_style"]["faab_net_in_trades"] == 10
    assert p2["trade_style"]["faab_net_in_trades"] == -10
    acq, given = p1["trade_assets"]["acquired"], p1["trade_assets"]["given"]
    assert acq["by_position"] == {"RB": 1} and acq["by_age_band"] == {"<=23": 1}
    assert given["by_position"] == {"QB": 1} and given["by_age_band"] == {"30+": 1}
    assert given["n_picks"] == 1 and given["picks_by_round"] == {"1": 1}
    assert p2["trade_assets"]["acquired"]["n_picks"] == 1
    act = p1["trade_activity"]
    assert act["n"] == 1 and act["counterparties"] == 1
    assert act["last_trade_at"].startswith("2026-09-")
    assert act["days_since_last_trade"] > 0
    assert act["league_mean_n"] == round(2 / 3, 2)   # 2 trade sides / 3 owned rosters
    assert p1["trade_style"]["usable"] is False      # 1 trade < MIN_TRADES_FOR_STYLE


def test_classify_trade_side():
    c = mp.classify_trade_side
    assert c(2, 1, 0, 0) == "players_only"
    assert c(0, 0, 1, 1) == "picks_only"
    assert c(1, 1, 0, 1) == "picks_for_players"
    assert c(1, 2, 1, 0) == "players_for_picks"
    assert c(1, 1, 1, 1) == "mixed"


def test_duplicate_transactions_count_once():
    txns = _all_txns() * 2
    rows = _profiles(trades=[t for t in txns if t["type"] == "trade"],
                     moves=[t for t in txns if t["type"] != "trade"])
    assert rows[U1]["n_trades"] == 1 and rows[U1]["n_waiver_bids"] == 2


# ---------------------------------------------------------------------------
# Identity: co-owners, ownerless rosters, non-owner moves, empty history
# ---------------------------------------------------------------------------

def test_co_owned_roster_is_one_profile_keyed_on_the_owner():
    rows = _profiles()
    assert U2_CO not in rows
    assert rows[U2]["roster_id"] == 2
    # The co-owner's $25 claim is on the owner's profile.
    assert any(b["bid"] == 25 for b in rows[U2]["profile"]["waiver_bids"]["bids"])


def test_ownerless_roster_gets_no_row():
    rows = _profiles()
    assert sorted(r["roster_id"] for r in rows.values()) == [1, 2, 3]


def test_non_owner_move_is_excluded_and_counted():
    p2 = _profiles()[U2]["profile"]
    assert p2["excluded"]["foreign_creator_moves"] == 1
    assert p2["free_agents"]["n"] == 0
    p1 = _profiles()[U1]["profile"]
    assert p1["free_agents"] == {"n": 1, "by_position": {"DEF": 1}}


def test_manager_with_no_history_gets_zeros():
    r = _profiles()[U3]
    assert (r["n_trades"], r["last_trade_at"], r["n_waiver_bids"],
            r["n_free_agent_adds"]) == (0, None, 0, 0)
    p = r["profile"]
    assert p["trade_activity"]["n"] == 0 and p["trade_activity"]["usable"] is True
    assert p["trade_style"]["usable"] is False
    assert p["trade_assets"]["usable"] is False
    assert p["waiver_bids"]["usable"] is False
    assert p["rookie_draft"]["captured"] is False


def test_no_rosters_means_no_rows():
    assert mp.build_league_profiles(LEAGUE, trades=[], moves=[], rosters=[],
                                    players={}, league_meta=META) == []


def test_empty_league_history_still_profiles_every_owner():
    rows = _profiles(trades=[], moves=[])
    assert len(rows) == 3 and all(r["n_trades"] == 0 for r in rows.values())


# ---------------------------------------------------------------------------
# The sweep (DB + fetch seam)
# ---------------------------------------------------------------------------

def test_sweep_backfills_then_resweeps_idempotently(engine):
    first = _Opener()
    assert _sync(first) == 1                       # one completed trade
    assert sorted(first.calls) == list(svc.WEEKS)  # the one-time backfill
    assert _count(engine, sleeper_waiver_moves_table) == 6
    before = load_manager_profiles(LEAGUE)
    assert [r["owner_id"] for r in before] == [U1, U2, U3]

    second = _Opener()
    assert _sync(second) == 0
    assert len(second.calls) <= 2                  # incremental from now on
    assert _count(engine, sleeper_waiver_moves_table) == 6
    after = load_manager_profiles(LEAGUE)
    strip = lambda rows: [{k: v for k, v in r.items()
                           if k not in ("id", "computed_at")} for r in rows]
    assert strip(after) == strip(before)


def test_backfill_with_a_failed_leg_writes_no_profile_and_retries(engine):
    lossy = _Opener(fail_week=2)
    _sync(lossy)
    assert _count(engine, manager_profiles_table) == 0
    # Leg 1's moves are kept (idempotent), but no marker: retry the backfill.
    assert _count(engine, sleeper_waiver_moves_table) == 5
    retry = _Opener()
    _sync(retry)
    assert sorted(retry.calls) == list(svc.WEEKS)
    assert _count(engine, manager_profiles_table) == 3
    assert _count(engine, sleeper_waiver_moves_table) == 6


def test_profile_step_failure_never_breaks_trade_capture(engine, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(svc, "capture_manager_profiles", boom)
    assert _sync(_Opener()) == 1
    assert _count(engine, db_module.sleeper_trades_table) == 1


# ---------------------------------------------------------------------------
# Flag off: no rows, no extra fetches
# ---------------------------------------------------------------------------

def _seed_swept_league():
    record_sleeper_trades(svc.parse_trade_transactions(WEEK[1], LEAGUE))


def test_profiles_off_writes_nothing_and_fetches_no_more(engine):
    _seed_swept_league()
    off = _Opener()
    _sync(off, profiles=False)
    assert len(off.calls) <= 2                     # unchanged incremental sweep
    assert _count(engine, sleeper_waiver_moves_table) == 0
    assert _count(engine, manager_profiles_table) == 0


def test_profiles_on_without_rosters_is_the_same_as_off(engine):
    _seed_swept_league()
    no_rosters = _Opener()
    _sync(no_rosters, rosters=None)
    assert len(no_rosters.calls) <= 2              # no backfill without a roster map
    assert _count(engine, sleeper_waiver_moves_table) == 0
    assert _count(engine, manager_profiles_table) == 0


def test_profiles_on_costs_one_backfill_for_an_already_swept_league(engine):
    _seed_swept_league()
    on = _Opener()
    _sync(on)
    assert sorted(on.calls) == list(svc.WEEKS)
    again = _Opener()
    _sync(again)
    assert len(again.calls) <= 2


def test_sweep_weeks_default_unchanged(engine):
    _seed_swept_league()
    assert svc.sweep_weeks(LEAGUE) == svc.sweep_weeks(LEAGUE, profiles=False)
    assert len(svc.sweep_weeks(LEAGUE)) <= 2
    assert svc.sweep_weeks(LEAGUE, profiles=True) == list(svc.WEEKS)


def test_flag_registered_dark():
    from backend import feature_flags as ff
    assert "market.manager_profiles" in ff.FLAG_KEYS
    repo = Path(__file__).resolve().parents[2]
    features = json.loads((repo / "config/features.json").read_text())
    release = json.loads(
        (repo / "backend/tests/fixtures/flags/release.json").read_text())
    assert features["market.manager_profiles"] is False
    assert release["market.manager_profiles"] is False


# ---------------------------------------------------------------------------
# The leaf stays a leaf
# ---------------------------------------------------------------------------

def test_manager_profiles_is_a_pure_leaf():
    src = Path(mp.__file__).read_text()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {"__future__", "json", "statistics", "datetime",
                        ".sleeper_roster"}, imported
