"""#232 follow-on — paste-first rankings import (flag `ranks.import`).

Covers the four contract layers:
  1. Parser tolerance (backend/rankings_import.py extract_name/parse):
     "rank. name", bare names, TSV/CSV rows with the name in any column,
     space-separated rows with trailing POS/TEAM codes, ignored headers
     and numbers-only lines.
  2. Match tiers: exact / suffix-normalized ("Kenneth Walker" → III) /
     initial form ("K. Walker") / ambiguous (≤3 candidates, seed-ordered) /
     unmatched.
  3. Apply semantics via POST /api/rankings/import-apply: the imported ids
     land at the top of the board in imported order and unlisted players
     keep their relative (consensus) order below — asserted both on the
     composed apply_reorder call and end-to-end on a real RankingService.
  4. Route auth/flag: 404 while `ranks.import` is off, 401 without a
     session, 400 on empty input.
  5. Structured rows + team/pos hints (premium rankings import v1,
     [D-058]; addendum §3.2): hints disambiguate same-name candidates,
     are ignored when the name already resolves, never reject a match,
     take precedence over names/text on the route, honour the row cap —
     and the paste path stays BYTE-IDENTICAL (golden fixture captured
     from the pre-hint implementation).

Isolation pattern mirrors test_rankings_submit_authz.py: Flask test
client, in-memory SQLite, injected sessions, no network.
"""
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.ranking_service import Player, RankingService
from backend.rankings_import import (
    extract_name,
    match_rank_list,
    normalize_player_name,
    parse_rank_lines,
)

# ---------------------------------------------------------------------------
# Fixtures — a small universal pool with the interesting name shapes
# ---------------------------------------------------------------------------

def _p(pid, name, pos="WR", team="FA"):
    return Player(id=pid, name=name, position=pos, team=team, age=25)


POOL = [
    _p("p_allen",    "Josh Allen",          "QB", "BUF"),
    _p("p_chase",    "Ja'Marr Chase",       "WR", "CIN"),
    _p("p_walker",   "Kenneth Walker III",  "RB", "SEA"),
    _p("p_mhj",      "Marvin Harrison Jr.", "WR", "ARI"),
    _p("p_stroud",   "C.J. Stroud",         "QB", "HOU"),
    _p("p_lamb",     "CeeDee Lamb",         "WR", "DAL"),
    # Ambiguity pair: two pool players normalizing to the same name.
    _p("p_lj_qb",    "Lamar Jackson",       "QB", "BAL"),
    _p("p_lj_wr",    "Lamar Jackson",       "WR", "FA"),
]
SEED = {"p_lj_qb": 1900.0, "p_lj_wr": 1200.0, "p_allen": 1950.0,
        "p_chase": 1940.0, "p_walker": 1700.0, "p_mhj": 1800.0,
        "p_stroud": 1750.0, "p_lamb": 1930.0}

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# 1. Parser tolerance
# ---------------------------------------------------------------------------

def test_extract_rank_dot_name():
    assert extract_name("1. Josh Allen") == "Josh Allen"
    assert extract_name("12) Ja'Marr Chase") == "Ja'Marr Chase"


def test_extract_bare_name():
    assert extract_name("Josh Allen") == "Josh Allen"


def test_extract_tsv_row_name_in_middle_column():
    assert extract_name("1\tJosh Allen\tQB\tBUF") == "Josh Allen"
    # POS code in an earlier column is skipped — name in ANY column.
    assert extract_name("1\tQB\tJosh Allen\tBUF") == "Josh Allen"


def test_extract_csv_row():
    assert extract_name("2,CeeDee Lamb,WR,DAL") == "CeeDee Lamb"


def test_extract_space_separated_row_drops_trailing_codes():
    assert extract_name("12 Josh Allen QB BUF") == "Josh Allen"


def test_headers_and_numbers_only_lines_ignored():
    assert extract_name("Rank,Player,Pos,Team") is None
    assert extract_name("Rank\tName\tValue") is None
    assert extract_name("123") is None
    assert extract_name("") is None
    assert extract_name("   ") is None


def test_parse_rank_lines_keeps_only_player_rows():
    lines = ["Rank,Player,Pos", "1. Josh Allen", "", "2,CeeDee Lamb,WR", "99"]
    parsed = parse_rank_lines(lines)
    assert [name for _line, name in parsed] == ["Josh Allen", "CeeDee Lamb"]


def test_normalize_strips_suffix_and_punctuation():
    assert normalize_player_name("Marvin Harrison Jr.") == "marvin harrison"
    assert normalize_player_name("Kenneth Walker III") == "kenneth walker"
    assert normalize_player_name("C.J. Stroud") == "cj stroud"


# ---------------------------------------------------------------------------
# 2. Match tiers
# ---------------------------------------------------------------------------

def _match_one(line):
    rows = match_rank_list([line], POOL, SEED)
    assert len(rows) == 1
    return rows[0]


def test_match_exact():
    row = _match_one("Josh Allen")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_allen"


def test_match_suffix_form_auto_accepts():
    # Pasted without the III — normalization makes it an exact match.
    row = _match_one("Kenneth Walker")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_walker"


def test_match_jr_suffix():
    row = _match_one("Marvin Harrison")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_mhj"


def test_match_initial_form():
    row = _match_one("K. Walker")
    assert row["status"] == "matched"
    assert row["player"]["id"] == "p_walker"


def test_match_ambiguous_two_candidates_seed_ordered():
    row = _match_one("Lamar Jackson")
    assert row["status"] == "ambiguous"
    assert row["player"] is None
    ids = [c["id"] for c in row["candidates"]]
    assert ids == ["p_lj_qb", "p_lj_wr"]  # seed-desc: QB first
    assert len(ids) <= 3


def test_match_unmatched():
    row = _match_one("Zzz Qqq")
    assert row["status"] == "unmatched"
    assert row["player"] is None
    assert row["candidates"] == []


def test_match_full_paste_counts():
    text = [
        "Rank\tPlayer\tPos",
        "1\tJosh Allen\tQB",
        "2. CeeDee Lamb",
        "Lamar Jackson",
        "Nobody Realname",
    ]
    rows = match_rank_list(text, POOL, SEED)
    statuses = [r["status"] for r in rows]
    assert statuses == ["matched", "matched", "ambiguous", "unmatched"]


# ---------------------------------------------------------------------------
# 2b. Structured rows + team/pos hints (premium import v1, [D-058])
# ---------------------------------------------------------------------------

def _match_rows(rows):
    return match_rank_list([], POOL, SEED, rows=rows)


def test_hint_team_resolves_same_name_pair():
    """The one thing hints exist for: two pool players named Lamar Jackson,
    the CSV's Team column picks the right one."""
    rows = _match_rows([{"name": "Lamar Jackson", "team": "BAL", "pos": None}])
    assert len(rows) == 1
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "p_lj_qb"
    assert rows[0]["candidates"] == []


def test_hint_pos_resolves_same_name_pair():
    rows = _match_rows([{"name": "Lamar Jackson", "team": None, "pos": "WR"}])
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "p_lj_wr"


def test_hint_codes_are_case_and_punctuation_insensitive():
    rows = _match_rows([{"name": "Lamar Jackson", "team": "bal.", "pos": "qb"}])
    assert rows[0]["player"]["id"] == "p_lj_qb"


def test_hint_stale_team_falls_back_to_position():
    """A traded player's CSV team code is stale — position still resolves it.
    (Strictest-first: both hints → 0 candidates → position alone → 1.)"""
    rows = _match_rows([{"name": "Lamar Jackson", "team": "NYJ", "pos": "QB"}])
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "p_lj_qb"


def test_hints_ignored_when_name_is_unambiguous():
    """Hints may NEVER reject a name-only match. Wrong team AND wrong
    position still matches the single Josh Allen in the pool."""
    rows = _match_rows([{"name": "Josh Allen", "team": "JAX", "pos": "LB"}])
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "p_allen"


def test_hints_ignored_when_fuzzy_match_is_unambiguous():
    rows = _match_rows([{"name": "Kenneth Walker", "team": "WAS", "pos": "WR"}])
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "p_walker"


def test_hints_matching_nothing_leave_the_ambiguity_intact():
    """No candidate satisfies the hints ⇒ the untouched name-only candidate
    list comes back (degrade to today's behaviour, never reject)."""
    rows = _match_rows([{"name": "Lamar Jackson", "team": "NYJ", "pos": "TE"}])
    assert rows[0]["status"] == "ambiguous"
    assert [c["id"] for c in rows[0]["candidates"]] == ["p_lj_qb", "p_lj_wr"]


def test_rows_without_hints_behave_like_names():
    rows = _match_rows([{"name": "Lamar Jackson"}])
    assert rows[0]["status"] == "ambiguous"
    assert [c["id"] for c in rows[0]["candidates"]] == ["p_lj_qb", "p_lj_wr"]


def test_rows_unmatched_and_order_preserved():
    rows = _match_rows([
        {"name": "CeeDee Lamb", "team": "DAL", "pos": "WR"},
        {"name": "Nobody Realname", "team": "FA", "pos": "WR"},
        {"name": "Josh Allen", "team": "BUF", "pos": "QB"},
    ])
    assert [r["status"] for r in rows] == ["matched", "unmatched", "matched"]
    assert [r["name"] for r in rows] == \
        ["CeeDee Lamb", "Nobody Realname", "Josh Allen"]
    assert rows[0]["input"] == "CeeDee Lamb"


def test_rows_drop_blank_and_non_dict_entries():
    rows = _match_rows([
        {"name": "  Josh Allen  ", "team": "BUF", "pos": "QB"},
        {"name": "   "},
        {"name": None},
        {"team": "DAL"},
        "Josh Allen",
        {"name": "CeeDee Lamb"},
    ])
    assert [r["name"] for r in rows] == ["Josh Allen", "CeeDee Lamb"]


def test_rows_never_read_value_columns():
    """Premium CSVs carry Value/Trend/PPG; the pipeline is order-only, so a
    row that smuggles them in is matched on name/team/pos and nothing else
    leaks into the response."""
    rows = _match_rows([{"name": "Josh Allen", "team": "BUF", "pos": "QB",
                         "value": 8655, "trend": "-63", "ppg": 24.9}])
    assert rows[0]["status"] == "matched"
    assert set(rows[0]) == {"input", "name", "status", "player", "candidates"}
    assert set(rows[0]["player"]) == {"id", "name", "team", "position"}


# ---------------------------------------------------------------------------
# 2c. Paste-path regression — the hint extension must not move the live path
# ---------------------------------------------------------------------------

def test_text_path_is_byte_identical_to_pre_hint_implementation():
    """fixtures/rankings_paste_golden.json holds match_rank_list's output for
    a realistic mixed-shape paste, CAPTURED FROM THE PRE-HINT CODE. This
    function serves the shipped paste import, so the structured-rows work is
    only allowed to be additive."""
    golden = json.loads((FIXTURES / "rankings_paste_golden.json").read_text())
    assert match_rank_list(golden["corpus"], POOL, SEED) == golden["golden"]
    # rows=None is the paste path, explicitly.
    assert match_rank_list(golden["corpus"], POOL, SEED,
                           rows=None) == golden["golden"]


# ---------------------------------------------------------------------------
# 2d. Dynasty Nerds premium CSV → the rows contract, end to end
# ---------------------------------------------------------------------------
# fixtures/dynasty_rankings_sflextep.csv is SYNTHESIZED FROM RESEARCH and is
# PENDING A REAL SUBSCRIBER EXPORT: its header
# (`Rank,Player,Team,Position,Age,Exp,Value,Trend,PPG,Pos Rank`), filename
# pattern and row shape come from
# docs/plans/connected-rankings/research/2026-08-15-dynasty-nerds.md, not
# from a file Dynasty Nerds actually produced. The preset does not graduate
# until a real export lands (addendum §3.4 fixture gate); when it does,
# replace this file and expect the assertions below to hold unchanged.

DN_CSV = FIXTURES / "dynasty_rankings_sflextep.csv"


def _dn_rows():
    """The client-side parse: NAME/TEAM/POS columns only, rank order kept."""
    with DN_CSV.open(newline="") as fh:
        return [{"name": r["Player"], "team": r["Team"], "pos": r["Position"]}
                for r in csv.DictReader(fh)]


def _dn_pool():
    """A universal pool covering the export, plus a real-world same-name
    collision (Josh Allen the QB vs Josh Allen the edge rusher)."""
    with DN_CSV.open(newline="") as fh:
        players = [_p(f"dn_{i}", r["Player"], r["Position"], r["Team"])
                   for i, r in enumerate(csv.DictReader(fh))]
    players.append(_p("dn_allen_lb", "Josh Allen", "LB", "JAX"))
    seed = {p.id: 2000.0 - i for i, p in enumerate(players)}
    return players, seed


def test_dn_fixture_header_is_the_documented_shape():
    header = DN_CSV.read_text().splitlines()[0]
    assert header == ("Rank,Player,Team,Position,Age,Exp,Value,Trend,PPG,"
                      "Pos Rank")
    assert DN_CSV.name == "dynasty_rankings_sflextep.csv"


def test_dn_rows_carry_only_name_team_pos():
    rows = _dn_rows()
    assert len(rows) == 30
    for row in rows:
        assert set(row) == {"name", "team", "pos"}


def test_dn_export_matches_end_to_end_with_hints():
    rows = _dn_rows()
    players, seed = _dn_pool()
    matched = match_rank_list([], players, seed, rows=rows)

    assert len(matched) == len(rows)
    assert [m["name"] for m in matched] == [r["name"] for r in rows]
    statuses = {m["status"] for m in matched}
    assert statuses == {"matched"}, [m for m in matched
                                     if m["status"] != "matched"]
    # The colliding name resolved to the QB, not the linebacker.
    allen = next(m for m in matched if m["name"] == "Josh Allen")
    assert allen["player"]["position"] == "QB"
    assert allen["player"]["team"] == "BUF"


def test_dn_export_without_hints_is_ambiguous_on_the_collision():
    """Proves the DN test above is actually exercising the hints: the same
    export matched name-only leaves Josh Allen ambiguous."""
    players, seed = _dn_pool()
    name_only = [{"name": r["name"]} for r in _dn_rows()]
    matched = match_rank_list([], players, seed, rows=name_only)
    allen = next(m for m in matched if m["name"] == "Josh Allen")
    assert allen["status"] == "ambiguous"
    assert {c["position"] for c in allen["candidates"]} == {"QB", "LB"}


# ---------------------------------------------------------------------------
# 3a. Apply semantics — real RankingService end-to-end
# ---------------------------------------------------------------------------

def test_apply_reorder_full_board_permutation_semantics():
    """Imported order lands on top; unlisted players keep their relative
    consensus order below the imported block."""
    players = [_p(f"x{i}", f"Player Num{i}") for i in range(6)]
    seed = {f"x{i}": 1800.0 - i * 50 for i in range(6)}  # consensus x0..x5
    svc = RankingService(players, seed_ratings=seed)

    imported = ["x4", "x1"]  # user's pasted order
    current = [rp.player.id for rp in svc.get_rankings(None).rankings]
    assert current == ["x0", "x1", "x2", "x3", "x4", "x5"]
    full = imported + [pid for pid in current if pid not in set(imported)]
    svc.apply_reorder(position=None, ordered_ids=full)

    after = [rp.player.id for rp in svc.get_rankings(None).rankings]
    assert after == ["x4", "x1", "x0", "x2", "x3", "x5"]
    # Pure permutation: the Elo multiset is unchanged (value curve intact).
    elos_after = sorted(rp.elo for rp in svc.get_rankings(None).rankings)
    assert elos_after == sorted(seed.values())


# ---------------------------------------------------------------------------
# 3b/4. Routes — flag, auth, composition
# ---------------------------------------------------------------------------

TOKEN = "sess-import-1"
USER = "555555555555555555"
LEAGUE = "league_import_test"


def _h(token=TOKEN):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


class _FakeService:
    """get_rankings in a fixed current order + apply_reorder capture."""

    def __init__(self, ordered_ids):
        self._ordered = list(ordered_ids)
        self._elo_overrides = {}
        self.applied = None

    def get_rankings(self, position=None):
        rankings = [
            SimpleNamespace(player=SimpleNamespace(id=pid), elo=1500.0 - i)
            for i, pid in enumerate(self._ordered)
        ]
        return SimpleNamespace(rankings=rankings)

    def apply_reorder(self, position, ordered_ids):
        assert position is None
        self.applied = list(ordered_ids)
        self._ordered = list(ordered_ids)


def _mk_sess(svc):
    return {
        "user_id":       USER,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [],
        "service":       svc,
        "services":      {"1qb_ppr": svc},
        "trade_svc":     object(),
        "trade_svcs":    {"1qb_ppr": object()},
    }


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    svc = _FakeService(["a", "b", "c", "d", "e"])

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled",
                      lambda k: k == "ranks.import"), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "_get_universal_pool",
                      lambda fmt: (POOL, SEED)), \
         patch.object(server, "_refresh_taste_board_prior", MagicMock()), \
         patch.object(server, "_record_trends_snapshot", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = _mk_sess(svc)
        try:
            yield c, svc
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def test_import_match_route(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"names": ["1. Josh Allen", "Lamar Jackson",
                                          "Nobody Realname", "Rank,Player"]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["scoring_format"] == "1qb_ppr"
    assert body["counts"] == {"matched": 1, "ambiguous": 1, "unmatched": 1}
    assert [row["status"] for row in body["rows"]] == \
        ["matched", "ambiguous", "unmatched"]


def test_import_match_accepts_raw_text(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"text": "1. Josh Allen\n2. CeeDee Lamb\n"}))
    assert r.status_code == 200
    assert r.get_json()["counts"]["matched"] == 2


def test_import_match_accepts_structured_rows(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"rows": [
                   {"name": "Lamar Jackson", "team": "BAL", "pos": "QB"},
                   {"name": "Lamar Jackson", "team": None, "pos": None},
                   {"name": "Nobody Realname", "team": "FA", "pos": "WR"},
               ]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["counts"] == {"matched": 1, "ambiguous": 1, "unmatched": 1}
    assert body["rows"][0]["player"]["id"] == "p_lj_qb"
    assert body["scoring_format"] == "1qb_ppr"


def test_import_match_rows_take_precedence_over_names_and_text(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({
                   "rows":  [{"name": "Josh Allen", "team": "BUF", "pos": "QB"}],
                   "names": ["CeeDee Lamb", "Ja'Marr Chase"],
                   "text":  "C.J. Stroud\nKenneth Walker III\n",
               }))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert [row["name"] for row in body["rows"]] == ["Josh Allen"]


def test_import_match_rows_requires_a_usable_name(client):
    c, _svc = client
    for payload in ({"rows": []},
                    {"rows": [{"team": "BUF"}, {"name": "  "}, "Josh Allen"]}):
        r = c.post("/api/rankings/import-match", headers=_h(),
                   data=json.dumps(payload))
        assert r.status_code == 400, payload
        assert r.get_json()["error"] == "rows[].name required"


def test_import_match_row_cap_applies_to_structured_rows(client):
    """Boundary: 500 rows pass, 501 are refused — counted on SUBMITTED rows,
    before unusable ones are dropped."""
    c, _svc = client
    row = {"name": "Josh Allen", "team": "BUF", "pos": "QB"}
    ok = c.post("/api/rankings/import-match", headers=_h(),
                data=json.dumps({"rows": [dict(row)] * 500}))
    assert ok.status_code == 200, ok.get_data(as_text=True)
    assert ok.get_json()["counts"]["matched"] == 500

    over = c.post("/api/rankings/import-match", headers=_h(),
                  data=json.dumps({"rows": [dict(row)] * 501}))
    assert over.status_code == 400
    assert over.get_json() == {"error": "too_many_rows", "max": 500}

    # …and a 501st row that would have been DROPPED still trips the cap.
    padded = c.post("/api/rankings/import-match", headers=_h(),
                    data=json.dumps({"rows": [dict(row)] * 500 + [{"name": ""}]}))
    assert padded.status_code == 400
    assert padded.get_json()["error"] == "too_many_rows"


def test_import_match_requires_input(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match", headers=_h(),
               data=json.dumps({"names": []}))
    assert r.status_code == 400


def test_import_match_requires_session(client):
    c, _svc = client
    r = c.post("/api/rankings/import-match",
               headers={"Content-Type": "application/json"},
               data=json.dumps({"names": ["Josh Allen"]}))
    assert r.status_code == 401


def test_import_routes_404_when_flag_off(client):
    c, _svc = client
    with patch.object(server, "is_enabled", lambda k: False):
        r1 = c.post("/api/rankings/import-match", headers=_h(),
                    data=json.dumps({"names": ["Josh Allen"]}))
        r2 = c.post("/api/rankings/import-apply", headers=_h(),
                    data=json.dumps({"ordered_player_ids": ["a", "b"]}))
    assert r1.status_code == 404
    assert r2.status_code == 404


def test_import_apply_composes_full_board_order(client):
    """Imported ids first (imported order, deduped, pool-filtered), then the
    remaining board in its current order."""
    c, svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids":
                                ["d", "b", "d", "not_in_pool"]}))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["imported_count"] == 2
    assert body["board_count"] == 5
    assert svc.applied == ["d", "b", "a", "c", "e"]


def test_import_apply_publishes_member_rankings(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids": ["c", "a"]}))
    assert r.status_code == 200
    stored = db_module.load_member_rankings(
        league_id=LEAGUE, exclude_user_id="", scoring_format="1qb_ppr")
    assert USER in stored


def test_import_apply_rejects_unknown_ids_only(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply", headers=_h(),
               data=json.dumps({"ordered_player_ids": ["zzz"]}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_matching_players"


def test_import_apply_requires_session(client):
    c, _svc = client
    r = c.post("/api/rankings/import-apply",
               headers={"Content-Type": "application/json"},
               data=json.dumps({"ordered_player_ids": ["a", "b"]}))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 5. Premium import v1 registrations ([D-058]) — flags + taxonomy
# ---------------------------------------------------------------------------

PREMIUM_SOURCE_FLAGS = ("ranks.source.dynasty_nerds", "ranks.source.dlf")


def test_premium_source_flags_registered_and_states_pinned():
    """Both keys exist in FLAG_KEYS, in config/features.json, and in every
    complete flag fixture (G-034: a key added to features.json but not the
    fixtures fails the suite later, in a file that has nothing to do with
    the feature). Compiled DEFAULT_FLAGS stay False (fail-closed) for both.
    Per-source config state pins the CURRENT graduation reality:
    dynasty_nerds graduated ON 2026-08-16 (operator flip after D-058);
    dlf stays dark until a real subscriber export pins its header shape
    (addendum §3.4 fixture gate)."""
    from backend import feature_flags

    expected = {"ranks.source.dynasty_nerds": True, "ranks.source.dlf": False}
    repo = Path(__file__).resolve().parents[2]
    sources = [repo / "config/features.json"] + [
        FIXTURES / "flags" / f"{n}.json"
        for n in ("release", "onboarding-v2", "profiles-on")
    ]
    for key in PREMIUM_SOURCE_FLAGS:
        assert key in feature_flags.FLAG_KEYS
        assert feature_flags.DEFAULT_FLAGS[key] is False
        for path in sources:
            flags = json.loads(path.read_text())
            assert flags.get(key) is expected[key], f"{key} in {path.name}"


def test_preset_events_registered_and_non_intent():
    """Registration lands BEFORE any emitter: this registry is default-deny
    behind a 200, so an unregistered name is silent data loss."""
    from backend import analytics_queries as aq
    from backend import analytics_taxonomy as tax

    for name in ("rankings_preset_detected", "rankings_preset_fallback"):
        assert name in tax.ALLOWED_CLIENT_EVENTS
        assert name in tax.CLIENT_EVENT_PROPS
        assert name in aq.NON_INTENT_EVENTS      # DAU-seam rule
        assert name not in aq.INTENT_EVENTS
    assert tax.CLIENT_EVENT_PROPS["rankings_preset_detected"] == \
        frozenset({"source", "via", "set_confirmed"})
    assert tax.CLIENT_EVENT_PROPS["rankings_preset_fallback"] == \
        frozenset({"via"})
    # The apply is the INTENT event of this funnel, and is server-fired.
    assert "rankings_import_applied" in tax.SERVER_FIRED_EVENTS
    assert "rankings_import_applied" not in tax.ALLOWED_CLIENT_EVENTS
    assert "rankings_import_applied" in aq.INTENT_EVENTS


# ── _NAME_ALIASES: formal-name forms premium sites export (2026-08-16) ─────
# Sleeper's canonical names are "Kenny Gainwell" / "Chig Okonkwo"; Dynasty
# Nerds exports "Kenneth Gainwell" / "Chigoziem Okonkwo" and the fuzzy tier
# cannot bridge either pair (proven by the operator's first real DN import).

def _alias_pool():
    return [
        SimpleNamespace(id="7567", name="Kenny Gainwell", position="RB", team="TB"),
        SimpleNamespace(id="8210", name="Chig Okonkwo", position="TE", team="WAS"),
        SimpleNamespace(id="1", name="Bijan Robinson", position="RB", team="ATL"),
    ]


def test_alias_bridges_formal_name_forms():
    rows = match_rank_list(["Kenneth Gainwell", "Chigoziem Okonkwo"], _alias_pool())
    assert [r["status"] for r in rows] == ["matched", "matched"]
    assert rows[0]["player"]["id"] == "7567"
    assert rows[1]["player"]["id"] == "8210"


def test_alias_applies_on_structured_rows_too():
    rows = match_rank_list([], _alias_pool(), rows=[
        {"name": "Kenneth Gainwell", "team": "TB", "pos": "RB"},
    ])
    assert rows[0]["status"] == "matched"
    assert rows[0]["player"]["id"] == "7567"


def test_alias_does_not_shadow_exact_canonical_names():
    rows = match_rank_list(["Kenny Gainwell", "Chig Okonkwo"], _alias_pool())
    assert [r["status"] for r in rows] == ["matched", "matched"]
