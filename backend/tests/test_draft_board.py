"""rookie-draft M3 — draft board service (plan §M3, lld §4.4, §7 M3).

Every case is driven by the M1 replay harness against the committed corpora,
with no Flask app, no route and no network: ``build_board`` takes injected
fetchers, so the corpora reach it directly.

  T-M3-01  complete draft (Lakeview) -> full board, 48 picks, order assigned
  T-M3-02  pre-draft with an assigned order -> true slots + traded overlay
  T-M3-03  draft_order:null -> unset, notice, round-level ownership; the
           identity slot_to_roster_id map is never read   [VFF]
  T-M3-04  drafts == [] -> state unavailable, never a fabricated board
  T-M3-05  fan-in: 20 concurrent calls on a cold draft -> 1 detail, 1 picks
  T-M3-06  poll rule: last_picked unchanged -> ZERO /picks fetches, 10 cycles
  T-M3-07  import graph: no load_draft_picks                              [I-7]
  T-M3-08  no platform writes: no POST/PUT, no sleeper_write import       [I-8]
  T-M3-09  undrafted = rookie ids - drafted - rostered; unvalued tail kept
  T-M3-10  startup-shaped -> kind startup, suppressed, notice
  T-M3-11  breaker: 3 failures -> open, zero upstream for 120 s; one success closes
  T-M3-12  budget: a 4th cycle inside 60 s -> degraded.budget_exceeded
  T-M5-01..05  MFL grids through the injected `_opener` seam (the RENDERER)
  T-M3-13  route shim: flag off -> 404 feature_disabled, no other route moves
  T-M5-06..10  route shim: the MFL BINDING behind `draft.mfl` (the WIRING)

The T-M3-13 block at the bottom is the only part that needs Flask: it drives
`GET /api/draft/board` to pin what belongs to the shim rather than to the
service — the `draft.room` gate, session/league resolution, and the platform
binding (Sleeper only this wave; M5 wires MFL behind `draft.mfl`).

Run: ``python3 -m pytest backend/tests/test_draft_board.py``
"""

from __future__ import annotations

import ast
import json
import pathlib
import threading
import urllib.error

import pytest

import backend.draft_board_service as dbs
import backend.server as server
from backend.tests.support.draft_replay import (
    DraftReplay,
    FakeClock,
    mfl_manifest,
    mfl_opener,
)

MODULE_PATH = pathlib.Path(dbs.__file__)

LAKEVIEW_LEAGUE = "1312076055586050048"
LAKEVIEW_DRAFT = "1312076055594430464"
FFV3_LEAGUE = "1312140920132497408"
EMPTY_LEAGUE = "9000000000000000001"
# mattmurf77 — roster 2 in Lakeview, and the FFv3 commissioner.
OPERATOR = "313560442465169408"


# ── harness ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_cache():
    dbs.reset_cache()
    yield
    dbs.reset_cache()


class CountingGet:
    """``server._sleeper_get`` with a call log and an optional failure switch."""

    def __init__(self, fail_on: str | None = None):
        self.urls: list[str] = []
        self.fail_on = fail_on

    def __call__(self, url: str):
        self.urls.append(url)
        if self.fail_on and self.fail_on in url:
            raise urllib.error.HTTPError(url, 500, "boom", None, None)
        return server._sleeper_get(url)

    def count(self, suffix: str) -> int:
        return sum(1 for u in self.urls if u.endswith(suffix))


def fetchers(get, *, rookie_ids=(), players=None, mfl=None) -> dbs.PlatformFetchers:
    rows = players or {}
    return dbs.PlatformFetchers(
        sleeper_get=get,
        mfl_opener=mfl,
        rookie_ids_fn=lambda season: set(rookie_ids),
        players_fn=lambda ids: {p: rows[p] for p in ids if p in rows},
    )


def board(corpus, tmp_path, monkeypatch, *, league_id, k=None, get=None,
          **req_kwargs):
    replay = DraftReplay(corpus, tmp_path)
    replay.install(monkeypatch, server)
    if k is not None:
        replay.truncate_picks(k)
    get = get or CountingGet()
    f = req_kwargs.pop("fetchers", None) or fetchers(get)
    req = dbs.BoardRequest(league_id=league_id, platform="sleeper", season=2026,
                           **req_kwargs)
    return dbs.build_board(req, f), replay, get


# ── payload shape ────────────────────────────────────────────────────────

EXPECTED_KEYS = {
    "schema", "league_id", "platform", "state", "kind", "season", "rounds",
    "teams", "order_confidence", "order", "picks", "undrafted",
    "undrafted_basis", "undrafted_suppressed", "my_picks", "as_of", "stale",
    "degraded", "notice", "deep_link",
}
ORDER_KEYS = {"slot", "round", "pick_no", "owner_user_id", "owner_username",
              "original_user_id", "original_username", "is_traded"}
PICK_KEYS = {"round", "pick_no", "slot", "player_id", "name", "position",
             "team", "picked_by_user_id", "picked_at"}


def test_payload_is_schema_1_field_for_field(tmp_path, monkeypatch):
    payload, _, _ = board("lakeview-complete", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE)
    assert payload["schema"] == 1
    assert set(payload) == EXPECTED_KEYS
    assert set(payload["order"][0]) == ORDER_KEYS
    assert set(payload["picks"][0]) == PICK_KEYS
    # `slot_value` is omitted entirely until M6 lands (the omit-when-absent
    # convention), never rendered as null.
    assert all("slot_value" not in o for o in payload["order"])
    assert payload["state"] in {"upcoming", "live", "complete", "unavailable"}
    assert payload["kind"] in {"rookie", "startup", "unknown"}
    assert payload["order_confidence"] in {"assigned", "unset", "unknown"}


def test_basis_is_echoed_and_defaults_to_consensus(tmp_path, monkeypatch):
    payload, _, _ = board("lakeview-complete", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE, basis="my_board")
    assert payload["undrafted_basis"] == "my_board"


def test_unsupported_platform_is_unavailable_not_an_error():
    req = dbs.BoardRequest(league_id="x", platform="espn", season=2026)
    payload = dbs.build_board(req, fetchers(CountingGet()))
    assert payload["state"] == "unavailable"
    assert payload["notice"]["code"] == "platform_unsupported"
    assert payload["order"] == [] and payload["picks"] == []


# ── T-M3-01 ──────────────────────────────────────────────────────────────

def test_m3_01_complete_draft_renders_the_full_board(tmp_path, monkeypatch):
    payload, _, _ = board("lakeview-complete", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE, user_id=OPERATOR)

    assert payload["state"] == "complete"
    assert payload["kind"] == "rookie"
    assert (payload["rounds"], payload["teams"]) == (4, 12)
    assert payload["order_confidence"] == "assigned"
    assert len(payload["picks"]) == 48
    assert len(payload["order"]) == 48
    assert [p["pick_no"] for p in payload["picks"]] == list(range(1, 49))
    assert payload["degraded"] is None and payload["stale"] is False
    assert payload["deep_link"] == f"https://sleeper.com/draft/nfl/{LAKEVIEW_DRAFT}"

    # my_picks is exactly the slots this user owns after trades.
    assert payload["my_picks"] == [o for o in payload["order"]
                                   if o["owner_user_id"] == OPERATOR]
    assert payload["my_picks"], "the operator owns picks in this corpus"


def test_m3_01a_order_ownership_matches_every_pick_actually_made(
        tmp_path, monkeypatch):
    """The strongest available check on the overlay: for a COMPLETE draft the
    board's predicted owner of (round, slot) must equal who actually picked."""
    payload, _, _ = board("lakeview-complete", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE)
    predicted = {(o["round"], o["slot"]): o["owner_user_id"] for o in payload["order"]}
    for pick in payload["picks"]:
        assert predicted[(pick["round"], pick["slot"])] == pick["picked_by_user_id"], \
            f"overlay disagrees with the recorded pick {pick['pick_no']}"
        assert predicted[(pick["round"], pick["slot"])] is not None


# ── T-M3-02 ──────────────────────────────────────────────────────────────

def test_m3_02_predraft_with_assigned_order_has_true_slots_and_overlay(
        tmp_path, monkeypatch):
    payload, _, _ = board("lakeview-complete", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE, k=0)

    assert payload["state"] == "upcoming"
    assert payload["order_confidence"] == "assigned"
    assert payload["picks"] == []
    assert len(payload["order"]) == 48
    assert all(o["slot"] is not None and o["pick_no"] is not None
               for o in payload["order"])
    # Linear draft: pick_no == (round-1)*teams + slot, matching the recorded
    # 48 picks exactly. `reversal_round: 3` is a stale default on a linear
    # draft and must not move the numbering.
    assert all(o["pick_no"] == (o["round"] - 1) * 12 + o["slot"]
               for o in payload["order"])

    by_slot = {(o["round"], o["slot"]): o for o in payload["order"]}
    # Recorded traded_picks: 2026 round 1, roster 6 -> owner 11. Slot 3 is
    # roster 6's (draft_order user 862148445476081664 -> slot 3).
    traded = by_slot[(1, 3)]
    assert traded["is_traded"] is True
    assert traded["original_user_id"] == "862148445476081664"
    assert traded["owner_user_id"] == "454869184224948224"   # roster 11
    # Round 1, roster 12 -> owner 12: a pick that came home is NOT traded.
    home = by_slot[(1, 1)]
    assert home["is_traded"] is False
    assert home["owner_user_id"] == home["original_user_id"] == "911858813945528320"
    assert home["owner_username"] and home["original_username"]


# ── T-M3-03 [VFF] ────────────────────────────────────────────────────────

def test_m3_03_draft_order_null_is_unset_and_round_level_only(
        tmp_path, monkeypatch):
    """VFF: fails against any implementation that reads slot_to_roster_id.

    The FFv3 corpus pins the trap — `draft_order: null` while
    `slot_to_roster_id` is the identity map `{"1":1 … "12":12}`. An
    implementation that took that map for an order would emit slots 1..12 and
    `order_confidence: "assigned"`; both assertions below would fail.
    """
    # Roster 10's owner: he acquired roster 1's first two rounds, so the
    # round-level overlay has something to prove.
    acquirer = "867831697150996480"
    payload, _, _ = board("ffv3-predraft", tmp_path, monkeypatch,
                          league_id=FFV3_LEAGUE, user_id=acquirer)

    assert payload["order_confidence"] == "unset"
    assert payload["notice"]["code"] == "order_not_set"
    assert payload["state"] == "upcoming"
    assert payload["picks"] == []
    assert len(payload["order"]) == 4 * 12               # round-level ownership
    assert all(o["slot"] is None and o["pick_no"] is None for o in payload["order"])
    assert {o["round"] for o in payload["order"]} == {1, 2, 3, 4}
    # Roster 6 is ownerless in this live corpus: its rounds are still rendered,
    # with a null owner, rather than dropped from the board.
    per_round = [o for o in payload["order"] if o["round"] == 1]
    assert len(per_round) == 12
    assert sum(1 for o in per_round if o["original_user_id"] is None) == 1
    # Round-level ownership still resolves through the traded-pick overlay.
    mine = payload["my_picks"]
    assert {(o["round"], o["original_user_id"]) for o in mine} >= {
        (1, OPERATOR), (2, OPERATOR)}
    assert all(o["slot"] is None for o in mine)
    assert any(o["is_traded"] for o in mine)


def test_m3_03a_slot_to_roster_id_is_never_read(tmp_path, monkeypatch):
    """Structural half of the VFF: the string does not appear in the module.

    Parsed rather than grepped so the docstring's description of the trap does
    not count as a read.
    """
    tree = ast.parse(MODULE_PATH.read_text())

    # Attribute access — detail.slot_to_roster_id
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "slot_to_roster_id"

    # String literals — detail["slot_to_roster_id"] / detail.get(...) — with
    # docstring nodes excluded BY IDENTITY, so prose about the trap is allowed
    # but a lookup is not.
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc_nodes.add(id(body[0].value))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in doc_nodes):
            assert "slot_to_roster_id" not in node.value, \
                "slot_to_roster_id is the identity-map trap — never read it (D5)"


# ── T-M3-04 ──────────────────────────────────────────────────────────────

def test_m3_04_empty_drafts_is_unavailable_never_fabricated(tmp_path, monkeypatch):
    payload, _, _ = board("empty-drafts", tmp_path, monkeypatch,
                          league_id=EMPTY_LEAGUE, user_id=OPERATOR)
    assert payload["state"] == "unavailable"
    assert payload["order"] == [] and payload["picks"] == []
    assert payload["my_picks"] == []
    assert payload["order_confidence"] == "unknown"
    assert payload["degraded"] is None          # ambiguity is not a failure


# ── T-M3-05 ──────────────────────────────────────────────────────────────

def test_m3_05_fan_in_twenty_viewers_cause_one_upstream_read(
        tmp_path, monkeypatch):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    replay.truncate_picks(24)                    # a live draft: 20 s TTL
    get = CountingGet()
    f = fetchers(get)
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper",
                           season=2026, user_id=OPERATOR)

    results: list = []
    lock = threading.Lock()

    def run():
        payload = dbs.build_board(req, f)
        with lock:
            results.append(payload)

    threads = [threading.Thread(target=run) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    assert all(r["state"] == "live" for r in results)
    assert get.count(f"/draft/{LAKEVIEW_DRAFT}") == 1
    assert get.count(f"/draft/{LAKEVIEW_DRAFT}/picks") == 1
    assert get.count(f"/league/{LAKEVIEW_LEAGUE}/drafts") == 1


# ── T-M3-06 ──────────────────────────────────────────────────────────────

def test_m3_06_unchanged_last_picked_never_refetches_picks(
        tmp_path, monkeypatch):
    """The 20 KB pick list is fetched once; the 1.2 KB detail carries the poll."""
    clock = FakeClock()
    monkeypatch.setattr(dbs, "_now_monotonic", clock)
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    replay.truncate_picks(24)
    get = CountingGet()
    f = fetchers(get)
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper",
                           season=2026)

    dbs.build_board(req, f)
    for _ in range(10):
        clock.advance(21)                        # past the 20 s live TTL
        payload = dbs.build_board(req, f)
        assert payload["state"] == "live"

    assert get.count(f"/draft/{LAKEVIEW_DRAFT}/picks") == 1, "picks refetched"
    assert get.count(f"/draft/{LAKEVIEW_DRAFT}") == 11       # detail every cycle
    assert get.count(f"/league/{LAKEVIEW_LEAGUE}/drafts") == 1

    # A pick lands -> last_picked moves -> exactly one more picks fetch.
    replay.advance(1)
    clock.advance(21)
    payload = dbs.build_board(req, f)
    assert get.count(f"/draft/{LAKEVIEW_DRAFT}/picks") == 2
    assert len(payload["picks"]) == 25


def test_cache_hit_inside_the_ttl_makes_no_upstream_call(tmp_path, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(dbs, "_now_monotonic", clock)
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    replay.truncate_picks(24)
    get = CountingGet()
    f = fetchers(get)
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026)

    dbs.build_board(req, f)
    before = len(get.urls)
    clock.advance(19.999)
    dbs.build_board(req, f)
    assert len(get.urls) == before


# ── T-M3-07 / T-M3-08 — structural invariants ────────────────────────────

def _imported_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {a.name for a in node.names}
    return names


def test_m3_07_board_never_imports_load_draft_picks():
    """I-7 — the divergence rule, enforced structurally.

    #228 deletes the season's `draft_picks` rows when a draft completes, so a
    board sourced from them empties at the finish line. The draft object is
    truth for the board; `draft_picks` is truth for pre-draft ownership only
    and is passed in by the route.
    """
    tree = ast.parse(MODULE_PATH.read_text())
    names = _imported_names(tree)
    assert "load_draft_picks" not in names
    assert not any("draft_picks" in n and n != "load_draft_picks" and
                   n.startswith("load_") for n in names)
    calls = [n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "load_draft_picks" not in calls


def test_m3_08_board_never_writes_to_a_platform():
    """I-8 / D9 — read-only. The terminal CTA is a deep link."""
    tree = ast.parse(MODULE_PATH.read_text())
    assert "sleeper_write" not in _imported_names(tree)
    source = MODULE_PATH.read_text()
    docstrings = {ast.get_docstring(n) or "" for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
    code = source
    for doc in docstrings:
        if doc:
            code = code.replace(doc, "")
    for verb in ('"POST"', "'POST'", '"PUT"', "'PUT'", '"DELETE"', "'DELETE'"):
        assert verb not in code, f"{verb} appears in draft_board_service"
    assert "urlopen" not in code, "the module must not do its own HTTP"


# ── T-M3-09 ──────────────────────────────────────────────────────────────

def _player_row(pid, name, pos="WR", team="ARI", rank=None):
    return {"player_id": pid, "full_name": name, "position": pos, "team": team,
            "rookie_year": "2026", "search_rank": rank}


def test_m3_09_undrafted_is_rookies_minus_drafted_minus_rostered(
        tmp_path, monkeypatch):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    corpus = replay.tmp_dir
    picks = json.loads((corpus / "draft" / LAKEVIEW_DRAFT / "picks.json").read_text())
    rosters = json.loads(
        (corpus / "league" / LAKEVIEW_LEAGUE / "rosters.json").read_text())
    drafted = str(picks[0]["player_id"])
    rostered = str(rosters[0]["players"][0])

    rows = {
        drafted: _player_row(drafted, "Drafted Guy"),
        rostered: _player_row(rostered, "Rostered Guy"),
        "free-a": _player_row("free-a", "Valued A", rank=10),
        "free-b": _player_row("free-b", "Valued B", rank=20),
        "free-c": _player_row("free-c", "Unvalued C", rank=5),
        "free-k": _player_row("free-k", "Kicker", pos="K"),
    }
    f = fetchers(CountingGet(), rookie_ids=set(rows), players=rows)
    req = dbs.BoardRequest(
        league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026,
        consensus_elo={"free-a": 1500.0, "free-b": 1700.0})
    payload = dbs.build_board(req, f)

    assert payload["undrafted_suppressed"] is False
    ids = [u["player_id"] for u in payload["undrafted"]]
    assert drafted not in ids, "a drafted rookie is still on the board"
    assert rostered not in ids, "a rostered rookie is still on the board"
    assert "free-k" not in ids, "non-skill positions are not board members"
    # Valued rows first, by value desc; the unvalued tail is KEPT, sorted last.
    assert ids == ["free-b", "free-a", "free-c"]
    assert [u["valued"] for u in payload["undrafted"]] == [True, True, False]
    assert payload["undrafted"][-1]["value"] is None
    assert [u["rank"] for u in payload["undrafted"]] == [1, 2, 3]
    assert payload["undrafted"][0]["rookie_year"] == "2026"


def test_undrafted_honours_my_board_basis(tmp_path, monkeypatch):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    rows = {"free-a": _player_row("free-a", "A"), "free-b": _player_row("free-b", "B")}
    f = fetchers(CountingGet(), rookie_ids=set(rows), players=rows)
    req = dbs.BoardRequest(
        league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026,
        basis="my_board",
        consensus_elo={"free-a": 9999.0},
        board_elo={"free-b": 1800.0, "free-a": 1200.0})
    payload = dbs.build_board(req, f)
    assert [u["player_id"] for u in payload["undrafted"]] == ["free-b", "free-a"]


def test_empty_rookie_class_is_a_designed_state(tmp_path, monkeypatch):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    f = fetchers(CountingGet(), rookie_ids=set(), players={})
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026)
    payload = dbs.build_board(req, f)
    assert payload["undrafted"] == []
    assert payload["undrafted_suppressed"] is True
    assert payload["notice"]["code"] == "class_not_loaded"


# ── T-M3-10 ──────────────────────────────────────────────────────────────

def test_m3_10_startup_shaped_is_labelled_and_degraded(tmp_path, monkeypatch):
    rows = {"free-a": _player_row("free-a", "A")}
    f = fetchers(CountingGet(), rookie_ids=set(rows), players=rows)
    payload, _, _ = board("startup-shaped", tmp_path, monkeypatch,
                          league_id=LAKEVIEW_LEAGUE, fetchers=f,
                          consensus_elo={"free-a": 1500.0})
    assert payload["kind"] == "startup"
    assert payload["rounds"] == 28
    assert payload["undrafted"] == []
    assert payload["undrafted_suppressed"] is True
    assert payload["notice"]["code"] == "startup_draft"
    # It is still a real board — the startup corpus keeps its live order.
    assert payload["order_confidence"] == "assigned"
    assert len(payload["order"]) == 28 * 12


# ── T-M3-11 ──────────────────────────────────────────────────────────────

def test_m3_11_breaker_opens_after_three_failures_and_one_success_closes(
        tmp_path, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(dbs, "_now_monotonic", clock)
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    replay.truncate_picks(24)
    get = CountingGet()
    f = fetchers(get)
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026)

    assert dbs.build_board(req, f)["state"] == "live"

    get.fail_on = f"/draft/{LAKEVIEW_DRAFT}"
    for _ in range(3):
        clock.advance(25)
        payload = dbs.build_board(req, f)
        assert payload["degraded"]["reason"] == "upstream_error"
        assert payload["stale"] is True

    calls_when_open = len(get.urls)
    clock.advance(30)                       # breaker is open for 120 s
    payload = dbs.build_board(req, f)
    assert payload["degraded"]["reason"] == "breaker_open"
    assert payload["stale"] is True
    assert len(get.urls) == calls_when_open, "an open breaker made an upstream call"
    # ...and the last good board is still served, not an empty one.
    assert payload["state"] == "live" and len(payload["picks"]) == 24

    clock.advance(120)
    get.fail_on = None
    payload = dbs.build_board(req, f)
    assert payload["degraded"] is None
    assert len(get.urls) > calls_when_open
    assert payload["state"] == "live"


# ── T-M3-12 ──────────────────────────────────────────────────────────────

def test_m3_12_a_fourth_fetch_inside_sixty_seconds_is_refused(
        tmp_path, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(dbs, "_now_monotonic", clock)
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server)
    replay.truncate_picks(24)
    get = CountingGet()
    f = fetchers(get)
    req = dbs.BoardRequest(league_id=LAKEVIEW_LEAGUE, platform="sleeper", season=2026)

    for _ in range(3):                       # cycles at t = 0, 20, 40
        dbs.build_board(req, f)
        clock.advance(20)

    calls = len(get.urls)
    payload = dbs.build_board(req, f)        # the 4th, at t = 60
    assert payload["degraded"]["reason"] == "budget_exceeded"
    assert payload["stale"] is True
    assert len(get.urls) == calls, "the budget did not stop the fetch"
    assert payload["state"] == "live" and len(payload["picks"]) == 24

    clock.advance(21)                        # the window rolls forward
    dbs.build_board(req, f)
    assert len(get.urls) > calls


# ── MFL — the `_opener` seam (T-M5-01..05) ───────────────────────────────

MFL_EXPECTED = {
    "mfl-made0": ("upcoming", 10, 6),
    "mfl-partial": ("live", 12, 6),
    "mfl-complete": ("complete", 10, 3),
    "mfl-multi-unit": ("complete", 32, 6),
}


@pytest.mark.parametrize("corpus", sorted(MFL_EXPECTED))
def test_m5_mfl_grid_states_through_the_injected_opener(corpus):
    state, teams, rounds = MFL_EXPECTED[corpus]
    man = mfl_manifest(corpus)
    calls: list[str] = []
    f = fetchers(None, mfl=mfl_opener(corpus, calls=calls))
    req = dbs.BoardRequest(league_id=man["league_id"], platform="mfl",
                           season=man["year"], mfl_host=man["host"],
                           mfl_year=man["year"])
    payload = dbs.build_board(req, f)

    assert set(payload) == EXPECTED_KEYS
    assert payload["platform"] == "mfl"
    assert payload["state"] == state
    assert (payload["teams"], payload["rounds"]) == (teams, rounds)
    assert payload["kind"] == "rookie"
    # MFL pre-populates the grid, so every unmade pick carries its franchise —
    # which makes MFL's pre-draft order strictly better than Sleeper's.
    assert payload["order_confidence"] == "assigned"
    assert len(payload["order"]) == man["total"]
    assert len(payload["picks"]) == man["made"]
    assert len(calls) == 1 and "TYPE=draftResults" in calls[0]
    # No crosswalk injected ⇒ the undrafted list is suppressed, not guessed.
    assert payload["undrafted"] == [] and payload["undrafted_suppressed"] is True


def test_m5_mfl_traded_picks_are_flagged_from_the_grid_comments():
    f = fetchers(None, mfl=mfl_opener("mfl-partial"))
    man = mfl_manifest("mfl-partial")
    payload = dbs.build_board(
        dbs.BoardRequest(league_id=man["league_id"], platform="mfl",
                         season=man["year"], mfl_host=man["host"]), f)
    assert any(o["is_traded"] for o in payload["order"]), \
        "mfl-partial carries trade provenance in its comments"


def test_m5_mfl_franchise_and_player_maps_are_honoured():
    man = mfl_manifest("mfl-complete")
    f = fetchers(None, mfl=mfl_opener("mfl-complete"),
                 rookie_ids={"ours-1"},
                 players={"ours-1": _player_row("ours-1", "Still Here")})
    payload = dbs.build_board(
        dbs.BoardRequest(league_id=man["league_id"], platform="mfl",
                         season=man["year"], mfl_host=man["host"],
                         mfl_franchise_to_user={"0007": "user-7"},
                         mfl_player_ids={"17472": "ours-x"},
                         consensus_elo={"ours-1": 1500.0}), f)
    first = payload["picks"][0]
    assert first["player_id"] == "ours-x"          # crosswalked into our id space
    assert first["picked_by_user_id"] == "user-7"
    assert first["picked_at"] is not None          # MFL picks DO carry timestamps
    assert [u["player_id"] for u in payload["undrafted"]] == ["ours-1"]


def test_m5_05_auth_failure_serves_a_notice_never_stale_as_live():
    man = mfl_manifest("mfl-complete")

    def refusing_opener(req, timeout=None):
        raise urllib.error.HTTPError(getattr(req, "full_url", ""), 401,
                                     "unauthorized", None, None)

    f = fetchers(None, mfl=refusing_opener)
    payload = dbs.build_board(
        dbs.BoardRequest(league_id=man["league_id"], platform="mfl",
                         season=man["year"], mfl_host=man["host"]), f)
    assert payload["state"] == "unavailable"
    assert payload["stale"] is True
    assert payload["degraded"]["reason"] == "auth_expired"
    assert payload["notice"]["code"] == "mfl_reconnect"
    assert payload["picks"] == []


# ── hermeticity ──────────────────────────────────────────────────────────

def test_the_whole_matrix_is_replayed_never_live(tmp_path, monkeypatch):
    """Every Sleeper read in this file goes through the fixture seam."""
    from backend import test_support
    before = dict(test_support.counters)
    for key in test_support.counters:
        test_support.counters[key] = 0
    try:
        board("lakeview-complete", tmp_path, monkeypatch, league_id=LAKEVIEW_LEAGUE)
        board("ffv3-predraft", tmp_path, monkeypatch, league_id=FFV3_LEAGUE)
        assert test_support.counters["sleeper_live_egress_attempts"] == 0
        assert test_support.counters["vcr_misses"] == 0
    finally:
        test_support.counters.update(before)


# ---------------------------------------------------------------------------
# T-M3-13 — the route shim (GET /api/draft/board)
#
# Everything above drives `build_board` directly. These drive the Flask
# route, because three things are the SHIM's job and cannot be asserted at
# the service layer: the `draft.room` gate, the session/league resolution,
# and the platform binding (only Sleeper is bound in this wave — M5 wires
# MFL behind `draft.mfl`).
# ---------------------------------------------------------------------------

import backend.feature_flags as ff                             # noqa: E402
from backend.ranking_service import Player, RankingService     # noqa: E402
from backend.trade_service import League, LeagueMember         # noqa: E402

ROUTE = "/api/draft/board"
ROUTE_TOKEN = "test-token-m3-13"


def _pin_flags(**overrides) -> dict:
    """The repo's flag-pinning idiom (there is no conftest.py). Returns the
    previous cache so the caller can restore it."""
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, **overrides}
    return saved


@pytest.fixture()
def flag_off():
    saved = _pin_flags()
    try:
        yield
    finally:
        ff._flags_cache = saved


@pytest.fixture()
def flag_on():
    saved = _pin_flags(**{"draft.room": True})
    try:
        yield
    finally:
        ff._flags_cache = saved


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


@pytest.fixture()
def session(monkeypatch):
    """A minimal initialized session for the Lakeview league.

    `_get_universal_pool` is stubbed so the route never depends on the
    process-wide pool build, and `_rookie_player_ids` so the undrafted list
    is deterministic rather than whatever the local players table holds.
    """
    pool = [Player(id="p1", name="Rookie One", position="WR", team="ARI", age=22)]
    service = RankingService(players=pool)
    league = League(league_id=LAKEVIEW_LEAGUE, name="Lakeview", platform="sleeper",
                    members=[LeagueMember(user_id=OPERATOR, username="op",
                                          roster=[], elo_ratings={})])
    sess = {
        "user_id":       OPERATOR,
        "league":        league,
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svc":     object(),
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (pool, {"p1": 1500.0}))
    monkeypatch.setattr(server, "_rookie_player_ids", lambda season: set())
    with server._sessions_lock:
        server._sessions[ROUTE_TOKEN] = sess
    try:
        yield sess
    finally:
        with server._sessions_lock:
            server._sessions.pop(ROUTE_TOKEN, None)


def _get(client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"{ROUTE}?{qs}" if qs else ROUTE,
                      headers={"X-Session-Token": ROUTE_TOKEN})


def test_m3_13_flag_off_is_404_feature_disabled(client, flag_off, session):
    resp = _get(client)
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "feature_disabled"}


def test_m3_13_flag_off_gates_before_any_session_work(client, flag_off):
    """No token at all still gets the 404 — the gate is the route's first
    statement, so an unauthenticated probe learns nothing about the session."""
    resp = client.get(ROUTE)
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "feature_disabled"}


def test_m3_13_flag_off_changes_no_other_route(client):
    """D10: the tranche is inert while dark — a neighbouring unflagged route
    answers byte-identically with `draft.room` off and on."""
    saved = ff._flags_cache
    try:
        _pin_flags()
        off = client.get("/api/tier-config")
        off_body = off.get_data()
        _pin_flags(**{"draft.room": True, "draft.live_poll": True})
        on = client.get("/api/tier-config")
        assert (on.status_code, on.get_data()) == (off.status_code, off_body)
    finally:
        ff._flags_cache = saved


def test_m3_13_flag_on_without_a_session_is_401(client, flag_on):
    resp = client.get(ROUTE)
    assert resp.status_code == 401


def test_route_rejects_an_unknown_basis(client, flag_on, session):
    resp = _get(client, basis="vibes")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad_basis"}


def test_route_404s_a_league_it_has_never_seen(client, flag_on, session,
                                               monkeypatch):
    monkeypatch.setattr(server, "get_league_draft_context", lambda lid: None)
    resp = _get(client, league_id="9999999999")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "league_not_found"}


def test_route_renders_the_honest_state_for_an_unbound_platform(
        client, flag_on, session, monkeypatch):
    """Only Sleeper is bound this wave. An MFL league must say "not available
    here" — NOT "reconnect MyFantasyLeague", which would blame the user for a
    feature (M5) that has not shipped."""
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "mfl", "season": 2026})
    resp = _get(client)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["platform"] == "mfl"
    assert payload["state"] == "unavailable"
    assert payload["notice"]["code"] == "platform_unsupported"


def test_route_serves_a_schema_1_board_from_the_corpus(
        client, flag_on, session, monkeypatch, tmp_path):
    """End-to-end through the shim: session → league → fetchers → payload."""
    DraftReplay("lakeview-complete", tmp_path).install(monkeypatch, server)
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "sleeper", "season": 2026})
    resp = _get(client, basis="my_board")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert set(payload) == EXPECTED_KEYS
    assert payload["schema"] == 1
    assert payload["platform"] == "sleeper"
    assert payload["state"] == "complete"
    assert payload["undrafted_basis"] == "my_board"
    assert payload["league_id"] == LAKEVIEW_LEAGUE
    assert len(payload["picks"]) == 48
    assert payload["deep_link"].startswith("https://sleeper.com/draft/nfl/")
    # D9 — the terminal CTA is a link; the route wrote nothing anywhere.
    assert payload["my_picks"], "the operator owns picks in this corpus"


# ---------------------------------------------------------------------------
# T-M5-06..10 — the MFL BINDING in the route shim (rookie-draft M5, lld §4.6)
#
# T-M5-01..05 above drive `build_board` directly and already prove the MFL
# RENDERER. What they cannot prove is the production wiring, which is this
# route's job and nothing else's:
#
#   T-M5-06  `draft.mfl` OFF -> the byte-identical pre-M5 platform_unsupported
#            payload, and ZERO MFL reads attempted (row, crosswalk, export)
#   T-M5-07  `draft.mfl` ON  -> a real board from the committed grid, driven
#            entirely through the injected `_opener` (RB-3, zero live egress)
#   T-M5-08  the crosswalk is actually injected -> the undrafted list is
#            POPULATED with an exact count; without it, honestly suppressed
#   T-M5-09  auth failure -> notice.mfl_reconnect + stale:true, never live
#   T-M5-10  `draft.mfl` ON changes no Sleeper league's response (D10)
#
# MFL has no fixtures-dir env seam, so the transport is injected through
# `server._mfl_draft_opener()` — the one-line seam the route exposes for
# exactly this.
# ---------------------------------------------------------------------------

MFL_CORPUS = "mfl-complete"
MFL_LEAGUE = mfl_manifest(MFL_CORPUS)["league_id"]
MFL_HOST = mfl_manifest(MFL_CORPUS)["host"]
# The first three players taken in the mfl-complete grid, in MFL id space.
MFL_TAKEN = ["17472", "17473", "17497"]
FROZEN_AS_OF = "2026-08-06T00:00:00+00:00"


@pytest.fixture()
def mfl_league(monkeypatch):
    """An MFL league linked exactly the way the MFL import path links one.

    Returns the mutable call log of MFL export URLs, so a test can assert
    that a flag-off request attempts *nothing*.
    """
    from backend import database as db

    calls: list[str] = []
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "mfl", "season": 2026})
    monkeypatch.setattr(db, "get_platform_league", lambda lid, plat: {
        "sleeper_league_id": MFL_LEAGUE, "platform": "mfl",
        "platform_host": MFL_HOST, "platform_season": 2026,
        "platform_my_team": "0007", "user_id": OPERATOR,
    })
    monkeypatch.setattr(server, "load_league_members", lambda lid: [
        {"user_id": OPERATOR, "player_ids": []},
        {"user_id": f"mfl:{MFL_LEAGUE}.f0010", "player_ids": ["ours-rostered"]},
    ])
    monkeypatch.setattr(server, "_mfl_cookie_for", lambda sess, uid: None)
    monkeypatch.setattr(server, "_mfl_draft_opener",
                        lambda: mfl_opener(MFL_CORPUS, calls=calls))
    monkeypatch.setattr(dbs, "_now_iso", lambda: FROZEN_AS_OF)
    return calls


def _xwalk(mapping):
    class _X:
        by_mfl_sleeper = mapping
    return _X()


def _mfl_flags(**extra):
    return _pin_flags(**{"draft.room": True, **extra})


def test_m5_06_flag_off_is_todays_payload_byte_for_byte_and_reads_nothing(
        client, session, monkeypatch, mfl_league):
    """The flag-off MFL response must be the payload M3 shipped, to the byte —
    and must not touch MFL at all on the way there.

    'Byte-identical to today' is asserted against a flag cache that does not
    CONTAIN `draft.mfl`, which is literally the pre-M5 build (`is_enabled`
    returns False for an unknown key). `as_of` is frozen so the comparison is
    exact rather than modulo a timestamp.
    """
    from backend import database as db

    def _explode(*a, **kw):
        raise AssertionError("flag off must attempt no MFL read")

    monkeypatch.setattr(db, "get_platform_league", _explode)
    monkeypatch.setattr(server, "_shared_crosswalk", _explode)

    saved = ff._flags_cache
    try:
        # The pre-M5 build: the key does not exist at all.
        pre_m5 = {k: v for k, v in ff.DEFAULT_FLAGS.items() if k != "draft.mfl"}
        ff._flags_cache = {**pre_m5, "draft.room": True}
        before = _get(client, league_id=MFL_LEAGUE)
        # This build, flag off.
        _mfl_flags(**{"draft.mfl": False})
        after = _get(client, league_id=MFL_LEAGUE)
    finally:
        ff._flags_cache = saved

    assert before.status_code == after.status_code == 200
    assert before.get_data() == after.get_data()
    payload = after.get_json()
    assert payload["platform"] == "mfl"
    assert payload["state"] == "unavailable"
    assert payload["notice"]["code"] == "platform_unsupported"
    assert mfl_league == [], "flag off attempted an MFL export call"


def test_m5_07_flag_on_renders_a_real_board_through_the_injected_opener(
        client, session, monkeypatch, mfl_league):
    man = mfl_manifest(MFL_CORPUS)
    monkeypatch.setattr(server, "_shared_crosswalk", lambda: _xwalk({}))

    saved = _mfl_flags(**{"draft.mfl": True})
    try:
        resp = _get(client, league_id=MFL_LEAGUE)
    finally:
        ff._flags_cache = saved

    assert resp.status_code == 200
    payload = resp.get_json()
    assert set(payload) == EXPECTED_KEYS
    assert payload["schema"] == 1
    assert payload["platform"] == "mfl"
    assert payload["league_id"] == MFL_LEAGUE
    assert payload["state"] == "complete"
    assert payload["kind"] == "rookie"
    assert payload["order_confidence"] == "assigned"
    assert len(payload["order"]) == man["total"]
    assert len(payload["picks"]) == man["made"]
    assert payload["as_of"] == FROZEN_AS_OF        # `as_of` is ALWAYS surfaced
    assert payload["stale"] is False
    assert payload["degraded"] is None
    # `platform_my_team` = franchise 0007 = the operator, so my_picks resolves
    # through the synthetic-id scheme rather than being empty.
    assert payload["my_picks"], "franchise 0007 belongs to the session user"
    assert all(o["owner_user_id"] == OPERATOR for o in payload["my_picks"])
    # Exactly ONE MFL export call: nothing in this path needs the >=1s spacing
    # `_REQUEST_SPACING_SECONDS` exists for.
    assert len(mfl_league) == 1 and "TYPE=draftResults" in mfl_league[0]


def test_m5_08_the_crosswalk_is_injected_so_undrafted_is_counted_not_suppressed(
        client, session, monkeypatch, mfl_league):
    """The MFL player-id crosswalk is load-bearing.

    `_render_mfl` suppresses `undrafted` outright when `mfl_player_ids` is
    missing, because subtracting MFL-space ids from our rookie ids would
    silently UNDER-COUNT. The count is asserted exactly, so a half-wired
    crosswalk fails loudly instead of quietly shrinking the list.
    """
    from backend import database as db

    rookies = {"ours-1", "ours-2", "ours-3", "ours-4", "ours-rostered"}
    monkeypatch.setattr(server, "_rookie_player_ids", lambda season: set(rookies))
    monkeypatch.setattr(db, "load_players_by_ids", lambda ids: {
        p: _player_row(p, p.title()) for p in ids})
    # ours-1..3 were taken in the grid; ours-rostered sits on a roster;
    # ours-4 is the only one genuinely still available.
    monkeypatch.setattr(server, "_shared_crosswalk",
                        lambda: _xwalk(dict(zip(MFL_TAKEN,
                                                ["ours-1", "ours-2", "ours-3"]))))

    saved = _mfl_flags(**{"draft.mfl": True})
    try:
        resp = _get(client, league_id=MFL_LEAGUE)
    finally:
        ff._flags_cache = saved

    payload = resp.get_json()
    assert payload["undrafted_suppressed"] is False
    assert [u["player_id"] for u in payload["undrafted"]] == ["ours-4"]
    assert len(payload["undrafted"]) == 1
    # The crosswalk really did move the picks into our id space.
    assert {p["player_id"] for p in payload["picks"]} >= {"ours-1", "ours-2", "ours-3"}


def test_m5_08b_a_missing_crosswalk_suppresses_honestly_rather_than_undercounting(
        client, session, monkeypatch, mfl_league):
    """The contrast case that makes T-M5-08 meaningful."""
    def _boom():
        raise RuntimeError("DP crosswalk unavailable")

    monkeypatch.setattr(server, "_rookie_player_ids",
                        lambda season: {"ours-1", "ours-4"})
    monkeypatch.setattr(server, "_shared_crosswalk", _boom)

    saved = _mfl_flags(**{"draft.mfl": True})
    try:
        payload = _get(client, league_id=MFL_LEAGUE).get_json()
    finally:
        ff._flags_cache = saved

    assert payload["undrafted"] == []
    assert payload["undrafted_suppressed"] is True
    assert payload["state"] == "complete"          # the rest of the board is fine


def test_m5_09_auth_failure_serves_the_snapshot_never_stale_as_live(
        client, session, monkeypatch, mfl_league):
    """An expired MFL cookie must never produce a live-looking board."""
    def refusing():
        def _opener(req, timeout=None):
            raise urllib.error.HTTPError(getattr(req, "full_url", ""), 401,
                                         "unauthorized", None, None)
        return _opener

    monkeypatch.setattr(server, "_mfl_draft_opener", refusing)
    monkeypatch.setattr(server, "_shared_crosswalk", lambda: _xwalk({}))

    saved = _mfl_flags(**{"draft.mfl": True})
    try:
        resp = _get(client, league_id=MFL_LEAGUE)
    finally:
        ff._flags_cache = saved

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["state"] == "unavailable"       # never "live", never "complete"
    assert payload["stale"] is True
    assert payload["degraded"]["reason"] == "auth_expired"
    assert payload["notice"]["code"] == "mfl_reconnect"
    assert payload["picks"] == [] and payload["order"] == []
    assert payload["as_of"]                        # age is always surfaced


def test_m5_10_flag_on_changes_no_sleeper_response(
        client, session, monkeypatch, tmp_path):
    """D10: `draft.mfl` is inert for every Sleeper league, on or off."""
    DraftReplay("lakeview-complete", tmp_path).install(monkeypatch, server)
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "sleeper", "season": 2026})
    monkeypatch.setattr(dbs, "_now_iso", lambda: FROZEN_AS_OF)
    monkeypatch.setattr(server, "_mfl_draft_opener",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("a Sleeper league must not bind MFL")))

    saved = ff._flags_cache
    try:
        _mfl_flags(**{"draft.mfl": False})
        off = _get(client, basis="my_board")
        dbs.reset_cache()
        _mfl_flags(**{"draft.mfl": True})
        on = _get(client, basis="my_board")
    finally:
        ff._flags_cache = saved

    assert off.status_code == on.status_code == 200
    assert off.get_data() == on.get_data()
    assert off.get_json()["platform"] == "sleeper"


def test_m5_mfl_binding_is_hermetic(client, session, monkeypatch, mfl_league):
    """No Sleeper egress and no live MFL egress on the MFL path.

    The route deliberately leaves `sleeper_get` unbound for MFL, so a stray
    Sleeper read would raise rather than reach the network; and the MFL
    transport is the corpus opener, so the only URL touched is the fixture's.
    """
    from backend import test_support

    monkeypatch.setattr(server, "_shared_crosswalk", lambda: _xwalk({}))
    before = dict(test_support.counters)
    for key in test_support.counters:
        test_support.counters[key] = 0
    saved = _mfl_flags(**{"draft.mfl": True})
    try:
        payload = _get(client, league_id=MFL_LEAGUE).get_json()
        assert payload["state"] == "complete"
        assert test_support.counters["sleeper_live_egress_attempts"] == 0
    finally:
        ff._flags_cache = saved
        test_support.counters.update(before)
