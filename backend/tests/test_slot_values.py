"""rookie-draft M6 — display-only per-slot pick values (plan §M6, lld §4.7).

  T-M6-01  FTF_TEST_MODE=1 without FTF_DP_PICK_VALUES_FILE -> SystemExit at
           import (the hermetic rail extended to DynastyProcess's SECOND file)
  T-M6-02  flag OFF -> `slot_value` absent ENTIRELY from every order entry,
           values.csv never fetched, GENERIC_PICK_SEEDS + tier bands unchanged
  T-M6-03  fetch failure -> the board renders without the axis (no exception,
           no null key)
  plus     parse correctness against a committed DP-shaped values.csv,
           the 12-team exact path (no approx marker), the non-12-team
           percentile map (approx marker), and the future-year rungs.

Run: ``python3 -m pytest backend/tests/test_slot_values.py``
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

import backend.data_loader as data_loader
import backend.draft_board_service as dbs
import backend.feature_flags as ff
import backend.pick_values as pick_values
import backend.server as server
from backend.tests.support.draft_replay import DraftReplay, mfl_manifest, mfl_opener

REPO = pathlib.Path(__file__).resolve().parents[2]
PICK_CSV = pathlib.Path(__file__).resolve().parent / "fixtures" / "dp_values_picks_2026-08-06.csv"

LAKEVIEW_LEAGUE = "1312076055586050048"      # complete, 4 rounds x 12 teams
FFV3_LEAGUE = "1312140920132497408"          # pre-draft, draft_order: null


# ── harness ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    dbs.reset_cache()
    data_loader.reset_pick_values_cache()
    monkeypatch.setenv("FTF_DP_PICK_VALUES_FILE", str(PICK_CSV))
    yield
    dbs.reset_cache()
    data_loader.reset_pick_values_cache()


@pytest.fixture
def slot_values_on():
    """Pin `picks.slot_values` ON (repo idiom — there is no conftest.py)."""
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.slot_values": True}
    yield
    ff._flags_cache = saved


@pytest.fixture
def slot_values_off():
    """Pin `picks.slot_values` OFF **explicitly**.

    These tests originally relied on the ambient flag state, which was
    correct only while the flag shipped false in `config/features.json`.
    Once it was flipped on for release they started failing, asserting a
    default rather than the behaviour they name. A flag-off test must pin
    the flag off, so it proves the same thing at every point in the
    flag's rollout.
    """
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.slot_values": False}
    yield
    ff._flags_cache = saved


def _fetchers():
    return dbs.PlatformFetchers(
        sleeper_get=server._sleeper_get,
        rookie_ids_fn=lambda season: set(),
        players_fn=lambda ids: {},
    )


def sleeper_board(corpus, league_id, tmp_path, monkeypatch, **kw):
    DraftReplay(corpus, tmp_path).install(monkeypatch, server)
    req = dbs.BoardRequest(league_id=league_id, platform="sleeper", season=2026, **kw)
    return dbs.build_board(req, _fetchers())


def mfl_board(corpus, **kw):
    manifest = mfl_manifest(corpus)
    req = dbs.BoardRequest(
        league_id=str(manifest["league_id"]), platform="mfl", season=2026,
        mfl_host=manifest["host"], mfl_year=manifest["year"], **kw)
    f = dbs.PlatformFetchers(
        sleeper_get=server._sleeper_get,
        mfl_opener=mfl_opener(corpus),
        rookie_ids_fn=lambda season: set(),
        players_fn=lambda ids: {},
    )
    return dbs.build_board(req, f)


# ── T-M6-01 — the hermetic rail ──────────────────────────────────────────

def test_m6_01_test_mode_without_pick_values_file_aborts_at_import(tmp_path):
    """values.csv is a SECOND live DynastyProcess egress. A test-mode backend
    that can reach it is a rails hole — the same one `FTF_DP_VALUES_FILE`
    exists to close for values-players.csv."""
    fixtures = tmp_path / "sleeper-fixtures"
    (fixtures / "user").mkdir(parents=True)
    cache = tmp_path / "players-cache.json"
    cache.write_text("{}")
    dp = tmp_path / "dp-values.csv"
    dp.write_text("player,pos,value_1qb,value_2qb\nTest Stud,WR,9000,9100\n")

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("FTF_") and k != "DATABASE_URL"}
    env.update({
        "DATABASE_URL": f"sqlite:///{tmp_path / 'scratch.db'}",
        "FTF_TEST_MODE": "1",
        "FTF_SLEEPER_FIXTURES_DIR": str(fixtures),
        "FTF_PLAYERS_CACHE_FILE": str(cache),
        "FTF_DP_VALUES_FILE": str(dp),
    })
    r = subprocess.run([sys.executable, "-c", "import backend.server"],
                       capture_output=True, text=True, cwd=REPO, env=env, timeout=180)
    assert r.returncode != 0
    assert "FTF_DP_PICK_VALUES_FILE" in (r.stdout + r.stderr)

    env["FTF_DP_PICK_VALUES_FILE"] = str(PICK_CSV)
    ok = subprocess.run([sys.executable, "-c", "import backend.server"],
                        capture_output=True, text=True, cwd=REPO, env=env, timeout=180)
    assert ok.returncode == 0, ok.stderr[-2000:]


def test_m6_01b_reader_refuses_live_egress_under_test_mode(monkeypatch):
    """Belt and braces below the import rail: even if something started a
    test-mode process without the assertion, the reader itself will not
    reach out."""
    monkeypatch.delenv("FTF_DP_PICK_VALUES_FILE")
    monkeypatch.setenv("FTF_TEST_MODE", "1")
    with pytest.raises(RuntimeError, match="FTF_DP_PICK_VALUES_FILE"):
        data_loader._fetch_pick_values_csv()
    # …and load_pick_slot_values swallows it into the honest empty map.
    assert data_loader.load_pick_slot_values() == {}


# ── parse correctness ────────────────────────────────────────────────────

def test_parses_current_year_slot_curve():
    prices = data_loader.load_pick_slot_values("1qb_ppr")
    # Every current-year slot of rounds 1-5 is priced.
    for round_no in range(1, 6):
        for slot in range(1, 13):
            label = data_loader.pick_slot_label(2026, round_no, slot)
            assert label in prices, label
    # Monotone decreasing down the board.
    curve = [prices[data_loader.pick_slot_label(2026, r, s)]
             for r in range(1, 6) for s in range(1, 13)]
    assert curve == sorted(curve, reverse=True)
    # The seed-Elo mapping is the shipped one (data_loader:seed_elo_for_value).
    assert prices["2026 Pick 1.01"] == round(data_loader.seed_elo_for_value(5633), 1)
    assert prices["2026 Pick 1.01"] == pytest.approx(1816.5, abs=0.05)


def test_parses_future_year_rungs():
    prices = data_loader.load_pick_slot_values("1qb_ppr")
    for label in ("2027 Early 1st", "2027 Mid 1st", "2027 Late 1st",
                  "2028 1st", "2027 Early 2nd", "2028 2nd"):
        assert label in prices, label
    assert prices["2027 Early 1st"] > prices["2027 Mid 1st"] > prices["2027 Late 1st"]


def test_both_formats_parse_and_superflex_prices_higher():
    one_qb = data_loader.load_pick_slot_values("1qb_ppr")
    superflex = data_loader.load_pick_slot_values("sf_tep")
    assert one_qb and superflex
    assert superflex["2026 Pick 1.01"] > one_qb["2026 Pick 1.01"]
    # DP's own column suffixes are accepted too.
    assert data_loader.load_pick_slot_values("2qb") == superflex


def test_player_rows_are_not_pick_rows():
    """The committed fixture carries real player rows; none may leak in."""
    prices = data_loader.load_pick_slot_values()
    assert not any("Chase" in label or "Robinson" in label for label in prices)


def test_ttl_cache_reads_the_file_once(monkeypatch):
    calls = []
    real = data_loader._fetch_pick_values_csv

    def counting(timeout=10):
        calls.append(timeout)
        return real(timeout)

    monkeypatch.setattr(data_loader, "_fetch_pick_values_csv", counting)
    data_loader.load_pick_slot_values("1qb_ppr")
    data_loader.load_pick_slot_values("sf_tep")
    data_loader.load_pick_slot_values("1qb_ppr")
    assert len(calls) == 1


def test_missing_source_returns_empty_map(monkeypatch, tmp_path):
    monkeypatch.setenv("FTF_DP_PICK_VALUES_FILE", str(tmp_path / "nope.csv"))
    assert data_loader.load_pick_slot_values() == {}


# ── the percentile map (O3) ──────────────────────────────────────────────

def test_percentile_map_is_the_identity_at_twelve_teams():
    assert [dbs._basis_slot(s, 12) for s in range(1, 13)] == list(range(1, 13))


@pytest.mark.parametrize("teams", [4, 6, 8, 10, 12, 14, 16, 20, 32])
def test_percentile_map_is_monotone_and_in_range(teams):
    mapped = [dbs._basis_slot(s, teams) for s in range(1, teams + 1)]
    assert mapped == sorted(mapped)
    assert all(1 <= m <= 12 for m in mapped)
    assert mapped[0] == 1 and mapped[-1] == 12


def test_percentile_map_examples():
    # 10-team: slot 5 sits at percentile 4/9 -> 12-team slot 6.
    assert dbs._basis_slot(5, 10) == 6
    # Both ends are anchored: pick 1 of a round is still 1.01, last is last.
    assert dbs._basis_slot(1, 10) == 1
    assert dbs._basis_slot(10, 10) == 12
    assert dbs._basis_slot(14, 14) == 12
    assert dbs._basis_slot(1, 1) == 1          # degenerate league, no crash


# ── T-M6-02 — flag off ───────────────────────────────────────────────────

def test_m6_02_flag_off_omits_the_key_entirely(slot_values_off, tmp_path, monkeypatch):
    """Not `None`, not `0.0` — ABSENT. A null would render as 'this pick is
    worthless' on every client (the repo's omit-when-absent convention)."""
    assert ff.DEFAULT_FLAGS["picks.slot_values"] is False
    board = sleeper_board("lakeview-complete", LAKEVIEW_LEAGUE, tmp_path, monkeypatch)
    assert board["order"], "corpus should produce an order"
    for entry in board["order"] + board["my_picks"]:
        assert "slot_value" not in entry
    assert "slot_value_approx" not in board


def test_m6_02_flag_off_never_reads_the_source(slot_values_off, tmp_path, monkeypatch):
    def boom(*a, **kw):                       # pragma: no cover — must not run
        raise AssertionError("values.csv read with picks.slot_values OFF")

    monkeypatch.setattr(data_loader, "_fetch_pick_values_csv", boom)
    board = sleeper_board("lakeview-complete", LAKEVIEW_LEAGUE, tmp_path, monkeypatch)
    assert board["state"] == "complete"


def test_m6_02_ladder_and_bands_are_byte_unchanged(slot_values_on, tmp_path, monkeypatch):
    """KD-9's bound. M6 is a display axis; the engine's pick pricing is the
    separate M6b repricing decision (plan O2)."""
    seeds_before = dict(pick_values.GENERIC_PICK_SEEDS)
    sleeper_board("lakeview-complete", LAKEVIEW_LEAGUE, tmp_path, monkeypatch)
    assert dict(pick_values.GENERIC_PICK_SEEDS) == seeds_before
    # The shipped rungs, spelled out: a future edit that "adopts" DP's much
    # steeper slot curve into the ladder has to change this test on purpose.
    assert seeds_before[(1, "Early")] == 1720
    assert seeds_before[(1, "Mid")] == 1650
    assert seeds_before[(1, "Late")] == 1580


@pytest.mark.parametrize("module", ["trade_service.py", "trade_optimizer.py",
                                    "ranking_service.py"])
def test_m6_02_slot_values_do_not_reach_the_valuation_lanes(module):
    """Structural bound on KD-9: the trade engine's scoring lanes and the
    ranking service must not read the pick-price map.

    **M6b amended this test on purpose, exactly as its own docstring said it
    would have to.** Operator decision O2 authorises engine adoption behind
    `trade.slot_pricing`, so `pick_values.py` — which now owns
    `market_pick_pool_value` — dropped out of the parametrize list. Everything
    else stands: the map reaches the engine through ONE named seam
    (`pick_values.priced_pool_value`) and nowhere else. The replacement
    guarantee is the behavioural one below plus T-M6B-01/02/04 in
    `test_pick_pricing_m6b.py`.
    """
    source = (REPO / "backend" / module).read_text()
    assert "load_pick_slot_values" not in source
    assert "PICK_VALUES_URL" not in source


def test_m6_02b_pick_values_reads_dp_only_through_the_m6b_seam():
    """The M6b replacement for `pick_values.py`'s structural bound: the module
    may reach `load_pick_slot_values`, but ONLY from
    `market_pick_pool_value`, and it must never hold the URL itself."""
    source = (REPO / "backend" / "pick_values.py").read_text()
    assert "PICK_VALUES_URL" not in source
    code = [ln for ln in source.splitlines()
            if "load_pick_slot_values" in ln and not ln.lstrip().startswith("#")
            and "`" not in ln]
    assert code == ["    from .data_loader import load_pick_slot_values",
                    "    slot_map = load_pick_slot_values(scoring_format)"], code
    # …and both lines sit inside market_pick_pool_value.
    body = source.split("def market_pick_pool_value")[1].split("\ndef ")[0]
    assert all(ln.strip() in body for ln in code)


# ── T-M6-03 — fetch failure ──────────────────────────────────────────────

def test_m6_03_fetch_failure_renders_without_the_axis(slot_values_on, tmp_path,
                                                     monkeypatch):
    def boom(timeout=10):
        raise OSError("values.csv unreachable")

    monkeypatch.setattr(data_loader, "_fetch_pick_values_csv", boom)
    board = sleeper_board("lakeview-complete", LAKEVIEW_LEAGUE, tmp_path, monkeypatch)
    assert board["state"] == "complete"
    assert board["order"]
    assert all("slot_value" not in e for e in board["order"])
    assert "slot_value_approx" not in board
    assert board["degraded"] is None          # a missing axis is not a degraded board


# ── flag on ──────────────────────────────────────────────────────────────

def test_twelve_team_board_is_exact_and_carries_no_approx_marker(
        slot_values_on, tmp_path, monkeypatch):
    board = sleeper_board("lakeview-complete", LAKEVIEW_LEAGUE, tmp_path, monkeypatch)
    assert board["teams"] == 12
    prices = data_loader.load_pick_slot_values()
    priced = [e for e in board["order"] if "slot_value" in e]
    assert len(priced) == len(board["order"]) == board["rounds"] * 12
    for entry in priced:
        assert entry["slot_value"] == prices[
            data_loader.pick_slot_label(2026, entry["round"], entry["slot"])]
    assert "slot_value_approx" not in board
    # my_picks is a slice of the same entries, so it carries the axis too.
    assert all("slot_value" in e for e in board["my_picks"])


def test_order_unset_entries_are_never_priced(slot_values_on, tmp_path, monkeypatch):
    """`slot: null` means we do not know which pick this is (D5). Pricing it
    would be inventing an order through the back door."""
    board = sleeper_board("ffv3-predraft", FFV3_LEAGUE, tmp_path, monkeypatch)
    assert board["order_confidence"] == "unset"
    assert board["order"]
    assert all(e["slot"] is None and "slot_value" not in e for e in board["order"])
    assert "slot_value_approx" not in board


def test_rounds_beyond_the_published_curve_are_omitted(slot_values_on, tmp_path,
                                                       monkeypatch):
    """DP publishes rounds 1-5. Round 6+ has no price and gets NO key —
    never a zero, never a null."""
    replay = DraftReplay("lakeview-complete", tmp_path)
    detail = replay.detail
    detail["settings"]["rounds"] = 7
    (replay.tmp_dir / "draft" / f"{replay.draft_id}.json").write_text(
        json.dumps(detail))
    replay.install(monkeypatch, server)
    board = dbs.build_board(
        dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026),
        _fetchers())
    by_round = {}
    for entry in board["order"]:
        by_round.setdefault(entry["round"], []).append("slot_value" in entry)
    for round_no in range(1, 6):
        assert all(by_round[round_no]), round_no
    assert not any(by_round[6])
    assert not any(by_round[7])


def test_future_season_board_has_no_axis(slot_values_on, tmp_path, monkeypatch):
    """The corpus is a 2026 draft; ask for it as 2029 and DP has no per-slot
    rows for that year. Honest omission beats a wrong price (the future-year
    RUNGS are parsed, but mixing two pricing bases in one column would poison
    M6b's calibration read)."""
    replay = DraftReplay("lakeview-complete", tmp_path)
    detail = replay.detail
    detail["season"] = "2029"
    (replay.tmp_dir / "draft" / f"{replay.draft_id}.json").write_text(
        json.dumps(detail))
    replay.install(monkeypatch, server)
    board = dbs.build_board(
        dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2029),
        _fetchers())
    assert all("slot_value" not in e for e in board["order"])
    assert "slot_value_approx" not in board


# ── MFL parity — the two render paths must not drift ─────────────────────

def test_mfl_non_twelve_team_gets_the_percentile_map_and_the_marker(slot_values_on):
    board = mfl_board("mfl-complete")
    assert board["teams"] and board["teams"] != 12
    priced = [e for e in board["order"] if "slot_value" in e]
    assert priced, "MFL order should carry the axis"
    assert board["slot_value_approx"] is True
    prices = data_loader.load_pick_slot_values()
    for entry in priced:
        expected = prices[data_loader.pick_slot_label(
            2026, entry["round"], dbs._basis_slot(entry["slot"], board["teams"]))]
        assert entry["slot_value"] == expected


def test_mfl_flag_off_omits_the_key(slot_values_off):
    board = mfl_board("mfl-complete")
    assert board["order"]
    assert all("slot_value" not in e for e in board["order"])
    assert "slot_value_approx" not in board
