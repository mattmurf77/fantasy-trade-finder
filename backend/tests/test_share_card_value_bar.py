"""The app's value bar on the og share cards (docs/plans/share-card-value-bar/
scope.md; words: marketing addendum 14; geometry: design-lead v2; colours:
the app's TradeValueBar, operator 2026-11-01; storage: models-lead K-a2).

Pins:
  1. `_consensus_verdict` is evaluate's own verdict (parity, same ids and
     format), and evaluate prices through it.
  2. The share-time snapshot (K-a2): both mints store `value_snapshot` with
     exactly the allowed keys and no values, usernames or gap points; a
     re-share keeps its snapshot; K-a6 stores NULL; a user_b mint is oriented
     to user_b; a package stores one only with `scoring_format`.
  3. A view never prices: the card and both share pages draw from the stored
     snapshot only, even with the pricing functions broken, a changed pool,
     or a different clock (the date is `computed_at`'s). NULL = no bar.
  4. The bar per snapshot: the ice even nub, green toward YOU GET, amber
     toward YOU GIVE (the app's tokens, read from the mobile source), the
     clamp at one Mid 1st, ticks where a Mid 2nd sat at mint.
  5. The words: the label line, the basis and date line (both branches),
     none of the never-list.
  6. Draft picks get a label and a neutral "PK" chip, never "Unknown player".
  7. The sharer's private board and stud-tax setting never move a snapshot.
  8. No bar is the #511 card, byte for byte; the moved-up layout only with a
     bar. The share pages' descriptions and og:image:alt follow the image.
  9. The migration adds the column to an existing DB; old rows read NULL.

Synthetic SQLite only (test_trade_share_tokens.py's fixture); the universal
pool is injected, as in test_trade_evaluate.py.
"""
import io
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, insert, inspect, select, text

import backend.database as db_module
import backend.server as server
from backend.tests.test_trade_share_tokens import (  # noqa: F401  (env is a fixture)
    SHARE_ON, TOKENS, USER_A, USER_B, _mint, env,
)

pytest.importorskip("PIL")
from backend import og_image  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LEAGUE = "vb-league"
# The clock every `world` test mints on: 02:30 UTC on Nov 14 is still Nov 13
# in every US zone, so a non-UTC date would show.
FROZEN_NOW = datetime(2026, 11, 14, 2, 30, tzinfo=timezone.utc)
AS_OF = "Nov 14, 2026"

_e2v = server._trade_service_mod.elo_to_value
_v2e = server._trade_service_mod.value_to_elo
MID_1ST = _e2v(server.GENERIC_PICK_SEEDS[(1, "Mid")])
MID_2ND = _e2v(server.GENERIC_PICK_SEEDS[(2, "Mid")])
LATE_1ST = _e2v(server.GENERIC_PICK_SEEDS[(1, "Late")])
SECOND_IN_FIRSTS = MID_2ND / MID_1ST        # ~0.287 today
SEC_PX = round(SECOND_IN_FIRSTS * 540)      # the +/-2nd tick offset from x=600

# id: (name, position, 1qb_ppr seed Elo). sf_tep adds 150 to the QB.
PLAYERS = {
    "vb_wr1": ("Avery Wideout", "WR", 1850.0),
    "vb_rb1": ("Blake Runner", "RB", 1840.0),
    "vb_te1": ("Casey Tightend", "TE", 1600.0),
    "vb_qb1": ("Dana Passer", "QB", 1700.0),
    "vb_wr2": ("Emery Slot", "WR", 1450.0),
    "vb_rb2": ("Frankie Depth", "RB", 1300.0),
    "vb_wr3": ("Gale Flanker", "WR", 1760.0),
    # 1-for-1 pairs whose consensus gap IS one generic pick's value, so the
    # label is that pick: "a Mid 2nd" and "a Late 1st".
    "vb_m2a": ("Harper Second", "WR", _v2e(3000.0)),
    "vb_m2b": ("Indy Secondo", "WR", _v2e(3000.0 - MID_2ND)),
    "vb_l1a": ("Jules Latefirst", "RB", _v2e(4000.0)),
    "vb_l1b": ("Kai Latefirst", "RB", _v2e(4000.0 - LATE_1ST)),
    # A gap of 0.57 Mid 1sts: still labelled "a Late 1st", and exactly where
    # the app's static tick sits (the render that showed the contradiction).
    "vb_l5a": ("Lane Boundary", "WR", _v2e(4000.0)),
    "vb_l5b": ("Morgan Boundary", "WR", _v2e(4000.0 - 0.57 * MID_1ST)),
}
OWNED_PICK = f"{LEAGUE}_2026_1_3"
UNPRICED_PICK = f"{LEAGUE}_2027_2_9"      # well-formed, not in the league's picks
LEAGUEMATE = "someleaguemate"
LEAGUE_PICKS = [{
    "pick_id": OWNED_PICK, "league_id": LEAGUE, "owner_user_id": USER_B,
    "season": 2026, "round": 1, "original_roster_id": "3", "pool_value": 3000.0,
    "is_traded": 0, "original_username": LEAGUEMATE,
}]

EVEN = (["vb_wr1"], ["vb_rb1"])                  # point ratio 0.951
LEAN_GET = (["vb_te1"], ["vb_qb1"])              # YOU GET heavier, ~0.5 firsts
LEAN_GIVE = (["vb_wr1"], ["vb_wr3"])             # YOU GIVE heavier, ~1.0 firsts
HUGE = (["vb_wr1", "vb_rb1"], ["vb_wr2"])        # ~4.9 firsts: clamped
FIVE_FOR_ONE = (["vb_te1", "vb_wr2", "vb_rb2", "vb_qb1", "generic_pick_3_late"],
                ["vb_wr1"])
GAP_MID_2ND = (["vb_m2b"], ["vb_m2a"])           # label "≈ a Mid 2nd in value"
GAP_LATE_1ST = (["vb_l1b"], ["vb_l1a"])          # label "≈ a Late 1st in value"
GAP_057 = (["vb_l5b"], ["vb_l5a"])               # also "≈ a Late 1st in value"

SNAPSHOT_KEYS = {"v", "favors", "firsts", "label", "format", "league_id",
                 "computed_at", "second_in_firsts", "pool"}
CARD_W = og_image.CARD_W
TRACK = [60, 452, 1140, 470]
PANEL_FILL = (255, 255, 255, 18)
BAR_FILLS = (og_image.SEMANTIC_POS, og_image.SEMANTIC_WARN, og_image.ICE_BASE)
NEVER = re.compile(r"\b(win|wins|won|lose|loses|lost|you|they|fair|unfair|fairness|"
                   r"steal|rob|worth|owes|today|apart)\b|%|\+|−|\d,\d{3}", re.I)
TRADE_WITH_BAR = ("A dynasty fantasy trade. See the give/get breakdown and how the "
                  "values compare in draft-pick terms. Values are an estimate from "
                  "market consensus, not a guarantee.")
TRADE_NO_BAR = "A dynasty fantasy trade. See the give/get breakdown."


def _frozen_datetime(instant):
    """`server.datetime` with now() pinned to `instant` (aware, UTC)."""
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)
    return _Frozen


def _seed(fmt, bump=0.0):
    seed = {pid: elo + bump + (150.0 if fmt == "sf_tep" and pos == "QB" else 0.0)
            for pid, (_, pos, elo) in PLAYERS.items()}
    for (rnd, tier), elo in server.GENERIC_PICK_SEEDS.items():
        seed[f"generic_pick_{rnd}_{tier.lower()}"] = elo
    return seed


def _install_pool(monkeypatch, seeds):
    for fmt, seed in seeds.items():
        monkeypatch.setitem(server.g_universal_by_format, fmt,
                            {"players": [], "seed": seed})


@pytest.fixture()
def world(env, monkeypatch):
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    _install_pool(monkeypatch, {fmt: _seed(fmt) for fmt in ("1qb_ppr", "sf_tep")})
    monkeypatch.setattr(server, "datetime", _frozen_datetime(FROZEN_NOW))
    monkeypatch.setattr(
        server, "load_draft_picks",
        lambda league_id=None, owner_user_id=None, **_k:
        [dict(p) for p in LEAGUE_PICKS if p["league_id"] == league_id])
    with db_module.engine.begin() as conn:
        for pid, (name, pos, _) in PLAYERS.items():
            conn.execute(insert(db_module.players_table).values(
                player_id=pid, full_name=name, position=pos, search_rank=10))
    yield env


def _set_league_format(fmt):
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id=LEAGUE, user_id=USER_A, default_scoring=fmt))


def _add_match(give, recv, league=LEAGUE) -> int:
    with db_module.engine.begin() as conn:
        return conn.execute(insert(db_module.trade_matches_table).values(
            league_id=league, user_a_id=USER_A, user_b_id=USER_B,
            user_a_give=json.dumps(give), user_a_receive=json.dumps(recv),
            matched_at="2026-10-30T00:00:00+00:00", status="pending",
        )).inserted_primary_key[0]


def _mint_token(c, mid, sharer=USER_A) -> str:
    with patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(c, sharer, mid)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["token"]


def _share(c, give, recv, sharer=USER_A) -> str:
    """A new match, shared through POST /api/share/trade (the snapshot mint)."""
    return _mint_token(c, _add_match(give, recv), sharer)


def _legacy_share(give, recv) -> str:
    """A token minted the pre-snapshot way: value_snapshot NULL."""
    return db_module.create_trade_share_token(_add_match(give, recv), USER_A)


def _share_package(c, give, recv, scoring_format=None) -> str:
    body = {"give_player_ids": list(give), "receive_player_ids": list(recv)}
    if scoring_format is not None:
        body["scoring_format"] = scoring_format
    with patch.object(server, "is_enabled", SHARE_ON):
        r = c.post("/api/share/package", json=body,
                   headers={"X-Session-Token": TOKENS[USER_A]})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["short_id"]


def _token_snapshot(tok):
    t = db_module.trade_share_tokens_table
    with db_module.engine.connect() as conn:
        return conn.execute(select(t.c.value_snapshot).where(t.c.token == tok)).scalar()


def _package_snapshot(sid):
    t = db_module.shared_packages_table
    with db_module.engine.connect() as conn:
        return conn.execute(select(t.c.value_snapshot).where(t.c.short_id == sid)).scalar()


def _spied(c, path, flags=SHARE_ON):
    """GET an og PNG, recording text / rounded_rectangle / rectangle / line
    calls on any canvas, in draw order."""
    calls = []
    cls = og_image.ImageDraw.ImageDraw

    def spy(name):
        real = getattr(cls, name)

        def wrapper(self, *a, **kw):
            calls.append((name, a, kw))
            return real(self, *a, **kw)
        return wrapper

    with patch.object(server, "is_enabled", flags), \
         patch.object(cls, "text", spy("text")), \
         patch.object(cls, "rounded_rectangle", spy("rounded_rectangle")), \
         patch.object(cls, "rectangle", spy("rectangle")), \
         patch.object(cls, "line", spy("line")):
        r = c.get(path)
    assert r.status_code == 200, r.status_code
    assert r.headers["Content-Type"] == "image/png"
    return r, calls


def _texts(calls):
    return [(a[0], a[1], kw) for name, a, kw in calls if name == "text"]


def _track_fills(calls):
    """(box, colour) of what is drawn on the track: the lean or the nub."""
    return [(list(a[0]), kw.get("fill")) for name, a, kw in calls
            if name == "rounded_rectangle" and kw.get("fill") in BAR_FILLS
            and a[0][1] == TRACK[1] and a[0][3] == TRACK[3]]


def _has_track(calls):
    return any(name == "rounded_rectangle" and list(a[0]) == TRACK
               for name, a, _ in calls)


def _label_runs(calls):
    return [(text, kw["fill"]) for (x, y), text, kw in _texts(calls)
            if y == og_image.VB_LABEL_Y]


def _meta(html, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', html)
    return m.group(1) if m else None


def _evaluate(c, give, recv, fmt="1qb_ppr", league_id=LEAGUE):
    r = c.post("/api/trade/evaluate", json={
        "give_player_ids": give, "receive_player_ids": recv,
        "scoring_format": fmt, "league_id": league_id})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ---------------------------------------------------------------------------
# 1. Parity with POST /api/trade/evaluate
# ---------------------------------------------------------------------------

PARITY_CASES = [EVEN, LEAN_GET, LEAN_GIVE, HUGE, FIVE_FOR_ONE,
                (["vb_qb1", "generic_pick_2_mid"], ["vb_wr3"]),
                (["vb_te1"], [OWNED_PICK])]


@pytest.mark.parametrize("fmt", ["1qb_ppr", "sf_tep"])
@pytest.mark.parametrize("give, recv", PARITY_CASES)
def test_consensus_verdict_equals_evaluate(world, fmt, give, recv):
    d = _evaluate(world, give, recv, fmt)
    v = server._consensus_verdict(give, recv, fmt, LEAGUE)
    for key in ("give_value", "receive_value", "favors", "gap",
                "point_ratio", "fairness"):
        assert v[key] == d[key], key
    assert v["dropped_ids"] == d["dropped_player_ids"] == []


def test_evaluate_prices_through_consensus_verdict(world):
    """One code path: evaluate's favors and gap ARE _consensus_verdict's."""
    real = server._consensus_verdict
    seen = []

    def spy(*a, **kw):
        out = real(*a, **kw)
        seen.append(out)
        return out
    with patch.object(server, "_consensus_verdict", side_effect=spy):
        d = _evaluate(world, *LEAN_GIVE)
    assert len(seen) == 1
    assert (d["favors"], d["gap"]) == (seen[0]["favors"], seen[0]["gap"])


def test_consensus_verdict_is_none_for_an_empty_side(world):
    assert server._consensus_verdict(["vb_wr1"], [], "1qb_ppr") is None
    assert server._consensus_verdict(["vb_wr1"], ["ghost"], "1qb_ppr") is None
    v = server._consensus_verdict(["vb_wr1", "ghost"], ["vb_rb1"], "1qb_ppr")
    assert v["dropped_ids"] == ["ghost"]


# ---------------------------------------------------------------------------
# 2. The share-time snapshot (K-a2)
# ---------------------------------------------------------------------------

def test_trade_mint_stores_exactly_the_allowed_keys(world):
    _set_league_format("sf_tep")
    give, recv = (["vb_te1"], [OWNED_PICK])       # an owned pick: K-a7 pricing
    raw = _token_snapshot(_share(world, give, recv))
    snap = json.loads(raw)
    assert set(snap) == SNAPSHOT_KEYS
    assert set(snap["pool"]) == {"snapshot", "version"}
    d = _evaluate(world, give, recv, "sf_tep")
    pick = d["gap"]["pick_equivalent"]
    assert snap == {
        "v": 1, "favors": d["favors"], "firsts": d["gap"]["firsts"],
        "label": pick["label"] if pick else None, "format": "sf_tep",
        "league_id": LEAGUE, "computed_at": "2026-11-14T02:30:00+00:00",
        "second_in_firsts": SECOND_IN_FIRSTS,
        "pool": {"snapshot": snap["pool"]["snapshot"],
                 "version": "evaluate-mode-a/market/market_slots"}}
    assert re.fullmatch(r"vsn1:[0-9a-f]{32}", snap["pool"]["snapshot"])
    # No values, totals, gap points, ids or names.
    for value in (d["give_value"], d["receive_value"], d["gap"]["value"]):
        assert str(value) not in raw, value
    for forbidden in (USER_A, USER_B, LEAGUEMATE, "vb_te1", OWNED_PICK,
                      "Casey", "value\"", "board", "elo"):
        assert forbidden not in raw, forbidden


def test_package_mint_stores_a_snapshot_only_with_a_scoring_format(world):
    give, recv = LEAN_GET
    none = _share_package(world, give, recv)
    bogus = _share_package(world, give, recv, scoring_format="SF_TEP")
    sf = _share_package(world, give, recv, scoring_format="sf_tep")
    assert _package_snapshot(none) is None and _package_snapshot(bogus) is None
    snap = json.loads(_package_snapshot(sf))
    assert set(snap) == SNAPSHOT_KEYS
    assert (snap["format"], snap["league_id"]) == ("sf_tep", None)
    v = server._consensus_verdict(give, recv, "sf_tep")
    assert (snap["favors"], snap["firsts"]) == (v["favors"], v["gap"]["firsts"])
    # Anonymized: the package's snapshot holds values, labels and the date only.
    assert USER_A not in _package_snapshot(sf)


def test_a_reshare_keeps_its_snapshot_and_a_legacy_token_stays_null(world, monkeypatch):
    mid = _add_match(*LEAN_GET)
    tok = _mint_token(world, mid)
    first = _token_snapshot(tok)
    # The pool moves: a re-share must not recompute.
    _install_pool(monkeypatch, {fmt: _seed(fmt, bump=40.0) for fmt in ("1qb_ppr", "sf_tep")})
    with patch.object(server, "datetime", _frozen_datetime(
            datetime(2026, 12, 1, tzinfo=timezone.utc))):
        assert _mint_token(world, mid) == tok
    assert _token_snapshot(tok) == first
    # A token minted before the column existed stays NULL when re-shared.
    legacy = _legacy_share(*LEAN_GIVE)
    legacy_mid = db_module.resolve_trade_share_token(legacy)["id"]
    assert _mint_token(world, legacy_mid) == legacy
    assert _token_snapshot(legacy) is None


@pytest.mark.parametrize("why", ["unpriced", "empty_side", "zero_side", "raises"])
def test_k_a6_stores_null(world, why, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    give, recv = LEAN_GET
    if why == "unpriced":
        assert _token_snapshot(_share(world, give + ["ghost"], recv)) is None
        return
    if why == "empty_side":
        assert _token_snapshot(_share(world, give, [])) is None
        return
    real = server._consensus_verdict

    def zero(*a, **kw):
        out = real(*a, **kw)
        out["receive_value"] = 0.0
        return out
    effect = zero if why == "zero_side" else RuntimeError("boom " + USER_A)
    with patch.object(server, "_consensus_verdict", side_effect=effect):
        tok = _share(world, give, recv)
    assert _token_snapshot(tok) is None
    if why == "raises":
        msgs = [r.getMessage() for r in caplog.records]
        assert "share value snapshot failed (stored NULL): RuntimeError" in msgs
        assert not any(USER_A in m or tok in m for m in msgs)


def test_a_user_b_mint_is_oriented_to_user_b(world):
    mid = _add_match(*LEAN_GET)
    a = json.loads(_token_snapshot(_mint_token(world, mid, USER_A)))
    b = json.loads(_token_snapshot(_mint_token(world, mid, USER_B)))
    assert (a["favors"], b["favors"]) == ("receive", "give")
    assert a["firsts"] == b["firsts"] and a["label"] == b["label"]


class _GuardedMatch(dict):
    """A resolved trade_matches row that raises if anything reads an
    A-oriented per-side column: the bar must come from the sharer-oriented
    lists and the token's own snapshot only."""
    def __init__(self, row, forbidden):
        super().__init__(row)
        self._forbidden = forbidden

    def _check(self, key):
        if key in self._forbidden:
            raise AssertionError(f"the share view read {key!r}")

    def __getitem__(self, key):
        self._check(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._check(key)
        return super().get(key, default)


def test_user_b_card_bar_leans_on_b_columns(world):
    """Legal R28.25 (release-lead QA P3-2): user_b's card draws B's side.

    One match where A's receive side is worth more (LEAN_GET from A's view).
    A's card: A's give under YOU GIVE and a green fill leaning right toward
    YOU GET. B's card: B's give (A's receive) under YOU GIVE and an amber
    fill leaning left toward YOU GIVE. Same label on both. Neither view reads
    match_valuation_json or any other A-oriented per-side column."""
    a_give, a_recv = LEAN_GET
    mid = _add_match(a_give, a_recv)
    a_tok = _mint_token(world, mid, USER_A)
    b_tok = _mint_token(world, mid, USER_B)

    cols = db_module.trade_matches_table.c.keys()
    forbidden = {"match_valuation_json"} | {
        c for c in cols if c.startswith(("user_a_", "user_b_"))
        and c not in ("user_a_give", "user_a_receive")}
    assert "match_valuation_json" in cols and "user_a_decision" in forbidden
    real = server._resolve_trade_share
    with patch.object(server, "_resolve_trade_share",
                      side_effect=lambda tok: _GuardedMatch(real(tok), forbidden)):
        _, a_calls = _spied(world, f"/og/trade/{a_tok}.png")
        _, b_calls = _spied(world, f"/og/trade/{b_tok}.png")
        a_page = world.get(f"/s/trade/{a_tok}").get_data(as_text=True)
        b_page = world.get(f"/s/trade/{b_tok}").get_data(as_text=True)

    names = {PLAYERS[pid][0]: pid for pid in a_give + a_recv}

    def columns(calls):
        drawn = [(x, t) for (x, _), t, _ in _texts(calls) if t in names]
        return ([names[t] for x, t in drawn if x < CARD_W // 2],
                [names[t] for x, t in drawn if x >= CARD_W // 2])

    v = server._consensus_verdict(a_give, a_recv, "1qb_ppr", LEAGUE)
    length = round(min(1.0, abs(v["gap"]["firsts"])) * 540)
    assert v["favors"] == "receive" and 0 < length < 540

    # A's card: A's give under YOU GIVE; leans right toward YOU GET, green.
    assert columns(a_calls) == (a_give, a_recv)
    assert _track_fills(a_calls) == [([600, 452, 600 + length, 470], og_image.SEMANTIC_POS)]
    # B's card: B's give (A's receive) under YOU GIVE; leans left, amber.
    assert columns(b_calls) == (a_recv, a_give)
    assert _track_fills(b_calls) == [([600 - length, 452, 600, 470], og_image.SEMANTIC_WARN)]
    # The same label on both, and both pages promise the comparison.
    a_label = "".join(t for t, _ in _label_runs(a_calls))
    assert a_label == "".join(t for t, _ in _label_runs(b_calls)) == "≈ an Early 2nd in value"
    assert _meta(a_page, "name", "description") == _meta(b_page, "name", "description") \
        == TRADE_WITH_BAR
    assert "leaning to the get side" in _meta(a_page, "property", "og:image:alt")
    assert "leaning to the give side" in _meta(b_page, "property", "og:image:alt")


# ---------------------------------------------------------------------------
# 3. A view never prices
# ---------------------------------------------------------------------------

def _no_pricing():
    """Patches that fail loudly if any view prices anything."""
    boom = AssertionError("a view priced")
    return (patch.object(server, "_consensus_verdict", side_effect=boom),
            patch.object(server, "_consensus_pricing", side_effect=boom),
            patch.object(server, "_get_universal_pool", side_effect=boom),
            patch.object(server, "_share_value_snapshot", side_effect=boom))


def test_views_draw_from_the_snapshot_without_pricing(world):
    tok = _share(world, *LEAN_GET)
    sid = _share_package(world, *LEAN_GIVE, scoring_format="1qb_ppr")
    p1, p2, p3, p4 = _no_pricing()
    with p1, p2, p3, p4:
        _, trade_calls = _spied(world, f"/og/trade/{tok}.png")
        _, pkg_calls = _spied(world, f"/og/p/{sid}.png")
        with patch.object(server, "is_enabled", SHARE_ON):
            trade_page = world.get(f"/s/trade/{tok}").get_data(as_text=True)
            pkg_page = world.get(f"/s/p/{sid}").get_data(as_text=True)
    assert _track_fills(trade_calls)[0][1] == og_image.SEMANTIC_POS
    assert _track_fills(pkg_calls)[0][1] == og_image.SEMANTIC_WARN
    assert _meta(trade_page, "name", "description") == TRADE_WITH_BAR
    assert "how the values compare" in _meta(pkg_page, "name", "description")


def test_a_pool_change_after_mint_does_not_move_the_image(world, monkeypatch):
    tok = _share(world, *LEAN_GET)
    before = world.get(f"/og/trade/{tok}.png").data
    moved = {fmt: _seed(fmt) for fmt in ("1qb_ppr", "sf_tep")}
    for seed in moved.values():
        seed["vb_qb1"] = seed["vb_te1"]          # now an even trade
    _install_pool(monkeypatch, moved)
    assert server._consensus_verdict(*LEAN_GET, "1qb_ppr")["favors"] == "even"
    assert world.get(f"/og/trade/{tok}.png").data == before
    assert json.loads(_token_snapshot(_share(world, *LEAN_GET)))["favors"] == "even"


def test_the_date_is_computed_at_not_the_view_clock(world):
    tok = _share(world, *LEAN_GET)               # minted at FROZEN_NOW (Nov 14)
    view_clock = _frozen_datetime(datetime(2026, 12, 25, 18, 0, tzinfo=timezone.utc))
    with patch.object(server, "datetime", view_clock):
        _, calls = _spied(world, f"/og/trade/{tok}.png")
    basis = [text for (x, y), text, _ in _texts(calls) if y == og_image.VB_BASIS_Y]
    assert len(basis) == 1 and basis[0].endswith(f"· 1QB PPR · {AS_OF}"), basis


@pytest.mark.parametrize("instant, shown", [
    (datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), "Dec 31, 2026"),
    (datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc), "Jan 1, 2027"),
])
def test_computed_at_is_the_mint_clock_in_utc(world, instant, shown):
    with patch.object(server, "datetime", _frozen_datetime(instant)):
        tok = _share(world, *LEAN_GET)
    snap = json.loads(_token_snapshot(tok))
    assert snap["computed_at"] == instant.isoformat(timespec="seconds")
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    basis = [text for (x, y), text, _ in _texts(calls) if y == og_image.VB_BASIS_Y]
    assert basis[0].endswith(f"· {shown}")


def test_a_null_snapshot_draws_no_bar_and_the_fallback_lines(world):
    tok = _legacy_share(*LEAN_GET)               # priceable, but no snapshot
    sid = "vbLegacy1"
    assert db_module.create_shared_package(sid, USER_A, *LEAN_GET)
    _, trade_calls = _spied(world, f"/og/trade/{tok}.png")
    _, pkg_calls = _spied(world, f"/og/p/{sid}.png")
    assert not _has_track(trade_calls) and not _has_track(pkg_calls)
    with patch.object(server, "is_enabled", SHARE_ON):
        trade_page = world.get(f"/s/trade/{tok}").get_data(as_text=True)
        pkg_page = world.get(f"/s/p/{sid}").get_data(as_text=True)
    assert _meta(trade_page, "name", "description") == TRADE_NO_BAR
    assert _meta(trade_page, "property", "og:image:alt") == "Trade card: the give/get breakdown."
    assert _meta(pkg_page, "name", "description") == \
        "A 2-player dynasty trade package. See the give/get breakdown."


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(v=2),
    lambda s: s.update(favors="you"),
    lambda s: s.update(format="2qb"),
    lambda s: s.update(firsts="0.5"),
    lambda s: s.update(firsts=-0.5),
    lambda s: s.update(computed_at="yesterday"),
    lambda s: s.update(computed_at="2026-11-14T02:30:00"),     # naive: no zone
    lambda s: s.pop("favors"),
])
def test_a_malformed_snapshot_draws_no_bar(world, mutate):
    tok = _share(world, *LEAN_GET)
    snap = json.loads(_token_snapshot(tok))
    mutate(snap)
    t = db_module.trade_share_tokens_table
    with db_module.engine.begin() as conn:
        conn.execute(t.update().where(t.c.token == tok).values(value_snapshot=json.dumps(snap)))
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    assert not _has_track(calls)
    assert server._value_bar_from_snapshot("{not json") is None
    assert server._value_bar_from_snapshot(None) is None


# ---------------------------------------------------------------------------
# 4. The bar
# ---------------------------------------------------------------------------

def _bar_length(give, recv, fmt="1qb_ppr"):
    v = server._consensus_verdict(give, recv, fmt, LEAGUE)
    return v, round(min(1.0, abs(v["gap"]["firsts"])) * 540)


def test_even_draws_the_centred_ice_nub(world):
    v, _ = _bar_length(*EVEN)
    assert v["favors"] == "even"
    _, calls = _spied(world, f"/og/trade/{_share(world, *EVEN)}.png")
    assert _has_track(calls)
    assert _track_fills(calls) == [([594, 452, 606, 470], og_image.ICE_BASE)]


def test_a_lean_toward_you_get_fills_right_in_green(world):
    v, length = _bar_length(*LEAN_GET)
    assert v["favors"] == "receive" and 0 < length < 540
    _, calls = _spied(world, f"/og/trade/{_share(world, *LEAN_GET)}.png")
    assert _track_fills(calls) == [([600, 452, 600 + length, 470], og_image.SEMANTIC_POS)]


def test_a_lean_toward_you_give_fills_left_in_amber(world):
    v, length = _bar_length(*LEAN_GIVE)
    assert v["favors"] == "give" and 0 < length < 540
    _, calls = _spied(world, f"/og/trade/{_share(world, *LEAN_GIVE)}.png")
    assert _track_fills(calls) == [([600 - length, 452, 600, 470], og_image.SEMANTIC_WARN)]


def test_a_huge_gap_clamps_at_one_first(world):
    v, length = _bar_length(*HUGE)
    assert abs(v["gap"]["firsts"]) > 1 and length == 540
    _, calls = _spied(world, f"/og/trade/{_share(world, *HUGE)}.png")
    assert _track_fills(calls) == [([60, 452, 600, 470], og_image.SEMANTIC_WARN)]


def test_fill_colours_are_the_apps_tokens():
    """SEMANTIC_POS / SEMANTIC_WARN / ICE_BASE are chalkline.ts's semantic.pos,
    semantic.warn and ice.base, and TradeValueBar.tsx still maps favors to
    them the way the card does (receive -> pos, give -> warn, even -> ice)."""
    theme = (REPO / "mobile" / "src" / "theme" / "chalkline.ts").read_text()

    def token(block, name):
        body = theme.split(f"export const {block} = {{", 1)[1].split("};", 1)[0]
        hexv = re.search(rf"^\s*{name}: '#([0-9A-Fa-f]{{6}})'", body, re.M).group(1)
        return tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))
    assert og_image.SEMANTIC_POS == token("semantic", "pos")
    assert og_image.SEMANTIC_WARN == token("semantic", "warn")
    assert og_image.ICE_BASE == token("ice", "base")
    bar = (REPO / "mobile" / "src" / "components" / "TradeValueBar.tsx").read_text()
    assert "const youWin = favors === 'receive';" in bar
    assert "const fillColor = even ? ice.base : youWin ? semantic.pos : semantic.warn;" in bar


def test_ticks_and_centre_line(world):
    """The +/-2nd ticks sit at 600 -/+ SEC_PX (the snapshot's fraction) and
    the centre at 600, 2px wide, 8px past the track."""
    for case in (EVEN, LEAN_GET, LEAN_GIVE):
        _, calls = _spied(world, f"/og/trade/{_share(world, *case)}.png")
        rects = [(list(a[0]), kw.get("fill")) for name, a, kw in calls
                 if name == "rectangle"]
        lo, hi = 600 - SEC_PX, 600 + SEC_PX
        assert rects == [([lo - 1, 444, lo, 478], og_image.VB_TICK),
                         ([hi - 1, 444, hi, 478], og_image.VB_TICK),
                         ([599, 444, 600, 478], og_image.VB_CENTER)], rects


def _tick_xs(calls):
    """x of the two VB_TICK rectangles (their right pixel column)."""
    return [a[0][2] for name, a, kw in calls
            if name == "rectangle" and kw.get("fill") == og_image.VB_TICK]


def _scale_label_centres(calls):
    draw = og_image.ImageDraw.Draw(og_image.Image.new("RGB", (1, 1)))
    return [(text, xy[0] + og_image._text_width(draw, text, kw["font"]) // 2)
            for xy, text, kw in _texts(calls) if xy[1] == og_image.VB_SCALE_Y]


def test_second_ticks_sit_at_the_snapshots_mid_2nd_fraction(world):
    assert 0.2 < SECOND_IN_FIRSTS < 0.35        # not the app's 0.57
    tok = _share(world, *LEAN_GET)
    assert json.loads(_token_snapshot(tok))["second_in_firsts"] == SECOND_IN_FIRSTS
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    assert _tick_xs(calls) == [600 - SEC_PX, 600 + SEC_PX]
    seconds = [cx for text, cx in _scale_label_centres(calls) if text == "2nd"]
    assert len(seconds) == 2
    assert abs(seconds[0] - (600 - SEC_PX)) <= 1 and abs(seconds[1] - (600 + SEC_PX)) <= 1


@pytest.mark.parametrize("case", [GAP_LATE_1ST, GAP_057])
def test_a_late_1st_fill_ends_past_the_drawn_2nd_tick(world, case):
    _, calls = _spied(world, f"/og/trade/{_share(world, *case)}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == "≈ a Late 1st in value"
    ((fill, _),) = _track_fills(calls)
    assert fill[0] == 600                       # leans right, toward YOU GET
    right_tick = _tick_xs(calls)[1]
    assert fill[2] > right_tick + 20, (fill, right_tick)


def test_a_mid_2nd_fill_ends_at_the_drawn_2nd_tick(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *GAP_MID_2ND)}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == "≈ a Mid 2nd in value"
    ((fill, _),) = _track_fills(calls)
    assert fill[0] == 600
    right_tick = _tick_xs(calls)[1]
    assert abs(fill[2] - right_tick) <= 20, (fill, right_tick)


_MISSING = object()
BAD_FRACTIONS = pytest.mark.parametrize(
    "bad", [_MISSING, 0, 1, "0.287"], ids=["missing", "zero", "one", "string"])


@BAD_FRACTIONS
def test_a_snapshot_without_a_valid_second_in_firsts_draws_no_bar(world, bad):
    """There is no default tick fraction (#567 moved the app's to ~0.287; a
    stale 0.57 would put a Late 1st on the 2nd tick). A snapshot whose
    second_in_firsts is missing, 0, 1 or a string is malformed: the card is
    the #511 no-bar card, byte for byte, and the page uses the fallback
    lines."""
    give, recv = LEAN_GET
    tok = _share(world, give, recv)
    snap = json.loads(_token_snapshot(tok))
    if bad is _MISSING:
        snap.pop("second_in_firsts")
    else:
        snap["second_in_firsts"] = bad
    raw = json.dumps(snap)
    t = db_module.trade_share_tokens_table
    with db_module.engine.begin() as conn:
        conn.execute(t.update().where(t.c.token == tok).values(value_snapshot=raw))
    assert server._value_bar_from_snapshot(raw) is None

    r, calls = _spied(world, f"/og/trade/{tok}.png")
    assert not _has_track(calls)
    assert r.data == _legacy_card(give, recv)
    assert [xy for xy, text, _ in _texts(calls) if text == "Trade Match"] == [(60, 85)]
    assert _panels(calls) == [(175, 455), (175, 455)]
    page = world.get(f"/s/trade/{tok}").get_data(as_text=True)
    assert _meta(page, "name", "description") == TRADE_NO_BAR
    assert _meta(page, "property", "og:image:alt") == "Trade card: the give/get breakdown."


@BAD_FRACTIONS
def test_the_renderer_has_no_default_tick_fraction(bad):
    """The renderer itself draws no bar for a verdict without a valid
    second_in_firsts, rather than ticks from a stale constant."""
    players = {"p1": {"full_name": "Pat One", "position": "WR"},
               "p2": {"full_name": "Sam Two", "position": "RB"}}
    verdict = {"favors": "receive", "gap": {"firsts": 0.5, "pick_equivalent": None}}
    plain = og_image._render_trade_card_png(["p1"], ["p2"], players)
    with_bar = og_image._render_trade_card_png(
        ["p1"], ["p2"], players, verdict={**verdict, "second_in_firsts": SECOND_IN_FIRSTS},
        as_of=AS_OF, scoring_format="1qb_ppr")
    assert with_bar != plain                      # the control: a valid fraction draws
    if bad is not _MISSING:
        verdict["second_in_firsts"] = bad
    assert og_image._render_trade_card_png(
        ["p1"], ["p2"], players, verdict=verdict,
        as_of=AS_OF, scoring_format="1qb_ppr") == plain
    assert not hasattr(og_image, "APP_SECOND_IN_FIRSTS")


# ---------------------------------------------------------------------------
# 5. The words
# ---------------------------------------------------------------------------

def test_label_line_pick_terms(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *LEAN_GET)}.png")
    runs = _label_runs(calls)
    assert runs == [("≈ ", og_image.VB_CHALK), ("an Early 2nd", og_image.VB_PICK),
                    (" in value", og_image.VB_CHALK)], runs


def test_label_line_firsts_when_no_single_pick_fits(world):
    v, _ = _bar_length(*HUGE)
    assert v["gap"]["pick_equivalent"] is None
    _, calls = _spied(world, f"/og/trade/{_share(world, *HUGE)}.png")
    text = "".join(t for t, _ in _label_runs(calls))
    assert text == f"≈ {abs(v['gap']['firsts']):.1f} Mid 1sts in value" == \
        "≈ 4.9 Mid 1sts in value"


def test_label_line_about_even(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *EVEN)}.png")
    runs = _label_runs(calls)
    assert "".join(t for t, _ in runs) == "About even in value"
    assert {fill for _, fill in runs} == {og_image.VB_CHALK}


def test_even_when_firsts_round_to_zero():
    """B3: a gap rounding to 0.0 firsts reads even, whatever `favors` says."""
    v = {"favors": "receive", "gap": {"firsts": 0.04, "pick_equivalent": None}}
    assert og_image.value_bar_is_even(v)
    assert og_image.value_bar_label(v) == ("", "About even", " in value")


def test_short_pick_matches_the_app():
    assert og_image._short_pick("Mid 2nd Round Pick") == "a Mid 2nd"
    assert og_image._short_pick("Early 1st Round Pick") == "an Early 1st"
    assert og_image._short_pick("Late 3rd Round Pick") == "a Late 3rd"


LONG = ("Estimate from consensus dynasty values, not a guarantee · "
        "{fmt} · " + AS_OF)
SHORT = "Estimate from consensus dynasty values · {fmt} · " + AS_OF


@pytest.mark.parametrize("long_width, expected", [(1080, LONG), (1081, SHORT)])
def test_basis_line_long_form_when_it_fits(world, long_width, expected):
    """B4-long when it fits within 1080px at the loaded font, else B4; always
    its own row at (60, 518). The measured width is patched so both
    branches run whatever font the host has."""
    _set_league_format("sf_tep")
    real = og_image._text_width

    def width(draw, text, font):
        if text.startswith("Estimate from consensus dynasty values, not a guarantee"):
            return long_width
        return real(draw, text, font)
    tok = _share(world, *LEAN_GET)
    with patch.object(og_image, "_text_width", side_effect=width):
        _, calls = _spied(world, f"/og/trade/{tok}.png")
    basis = [(xy, text, kw["fill"]) for xy, text, kw in _texts(calls)
             if text.startswith("Estimate")]
    assert basis == [((60, 518), expected.format(fmt="SF TEP"), og_image.VB_DIM)]


def test_scale_labels_have_no_signs_and_no_end_labels(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *LEAN_GIVE)}.png")
    scale = [text for (x, y), text, _ in _texts(calls) if y == og_image.VB_SCALE_Y]
    assert scale == ["1st", "2nd", "Even", "2nd", "1st"]


@pytest.mark.parametrize("case", [EVEN, LEAN_GET, LEAN_GIVE, HUGE])
def test_bar_words_avoid_the_never_list(world, case):
    _, calls = _spied(world, f"/og/trade/{_share(world, *case)}.png")
    footer = "Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com"
    bar_texts = [text for (x, y), text, _ in _texts(calls)
                 if 375 <= y < 560 and text != footer]
    assert bar_texts
    for t in bar_texts:
        assert not NEVER.search(t), t
        assert "swing" not in t.lower(), t


def test_value_bar_date_format():
    assert server._value_bar_date(date(2026, 11, 3)) == "Nov 3, 2026"
    assert server._value_bar_date(date(2026, 12, 25)) == "Dec 25, 2026"


# ---------------------------------------------------------------------------
# 6. Draft picks: labels and a neutral PK chip
# ---------------------------------------------------------------------------

def test_picks_get_labels_and_a_neutral_pk_chip(world):
    give = ["generic_pick_1_mid", OWNED_PICK]
    recv = ["vb_wr1"]
    _, calls = _spied(world, f"/og/trade/{_share(world, give, recv)}.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "Mid 1st Round Pick" in drawn and "2026 1st" in drawn
    assert "Unknown player" not in drawn
    assert not any(LEAGUEMATE in t for t in drawn)
    pk_labels = [(xy, kw["fill"]) for xy, text, kw in _texts(calls) if text == "PK"]
    assert len(pk_labels) == 2 and {f for _, f in pk_labels} == {(12, 14, 17)}
    pk_chips = [a[0] for name, a, kw in calls if name == "rounded_rectangle"
                and kw.get("fill") == og_image.PICK_CHIP_FILL
                and a[0][2] - a[0][0] == 56]
    assert len(pk_chips) == 2
    assert og_image.PICK_CHIP_FILL not in og_image.POS_COLORS.values()
    assert _has_track(calls)                     # both picks priced at mint


def test_an_unpriceable_pick_keeps_its_label_but_draws_no_bar(world):
    tok = _share(world, [UNPRICED_PICK], ["vb_wr1"])
    assert _token_snapshot(tok) is None
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "2027 2nd" in drawn and "Unknown player" not in drawn
    assert not _has_track(calls)


def test_share_pick_labels():
    assert server._share_pick_labels(
        ["generic_pick_2_early", f"{LEAGUE}_2028_3_12", "4034", "o8p1", ""]) == {
        "generic_pick_2_early": "Early 2nd Round Pick",
        f"{LEAGUE}_2028_3_12": "2028 3rd"}


# ---------------------------------------------------------------------------
# Packages: the format lives in the snapshot; the view takes no ?fmt=
# ---------------------------------------------------------------------------

def _panels(calls):
    return [(a[0][1], a[0][3]) for name, a, kw in calls
            if name == "rounded_rectangle" and kw.get("fill") == PANEL_FILL]


def test_package_card_draws_its_snapshot_format_and_ignores_fmt(world):
    sf = _share_package(world, *LEAN_GET, scoring_format="sf_tep")
    bare = _share_package(world, *LEAN_GET)
    _, calls = _spied(world, f"/og/p/{sf}.png?fmt=1qb_ppr")
    assert _panels(calls) == [(125, 375), (125, 375)]
    v = server._consensus_verdict(*LEAN_GET, "sf_tep")
    length = round(min(1.0, abs(v["gap"]["firsts"])) * 540)
    assert _track_fills(calls) == [([600, 452, 600 + length, 470], og_image.SEMANTIC_POS)]
    assert any(t.endswith(f"· SF TEP · {AS_OF}") for _, t, _ in _texts(calls))
    for query in ("", "?fmt=sf_tep"):
        _, calls = _spied(world, f"/og/p/{bare}.png{query}")
        assert not _has_track(calls)
        assert _panels(calls) == [(175, 455), (175, 455)]


def test_share_package_page_has_no_fmt_and_follows_the_snapshot(world):
    sf = _share_package(world, *LEAN_GET, scoring_format="sf_tep")
    bare = _share_package(world, *LEAN_GET)
    with patch.object(server, "is_enabled", SHARE_ON):
        with_bar = world.get(f"/s/p/{sf}?fmt=1qb_ppr").get_data(as_text=True)
        without = world.get(f"/s/p/{bare}?fmt=sf_tep").get_data(as_text=True)
    assert _meta(with_bar, "property", "og:image") == f"http://localhost/og/p/{sf}.png"
    assert _meta(without, "property", "og:image") == f"http://localhost/og/p/{bare}.png"
    assert "fmt=" not in with_bar and "fmt=" not in without
    assert _meta(with_bar, "property", "og:description") == (
        "A 2-player dynasty trade package. See the give/get breakdown and how the "
        "values compare in draft-pick terms. Values are an estimate from market "
        "consensus, not a guarantee.")
    # Superflex prices the QB higher: ~1.9 firsts here, ~an Early 2nd in 1QB.
    assert _meta(with_bar, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar leaning to the get side, "
        f"≈ 1.9 Mid 1sts in value. Estimate from consensus dynasty values, SF TEP, {AS_OF}.")
    assert _meta(without, "property", "og:description") == \
        "A 2-player dynasty trade package. See the give/get breakdown."
    assert _meta(without, "property", "og:image:alt") == "Trade card: the give/get breakdown."


# ---------------------------------------------------------------------------
# 7. The sharer's private board and settings never move a snapshot
# ---------------------------------------------------------------------------

def test_private_boards_do_not_change_the_snapshot(world):
    give, recv = LEAN_GIVE
    before = _token_snapshot(_share(world, give, recv))
    assert before is not None
    with db_module.engine.begin() as conn:
        for uid in (USER_A, USER_B):
            for fmt in ("1qb_ppr", "sf_tep"):
                for pid, elo in (("vb_wr1", 1200.0), ("vb_wr3", 2100.0)):
                    conn.execute(insert(db_module.member_rankings_table).values(
                        user_id=uid, league_id=LEAGUE, player_id=pid, elo=elo,
                        scoring_format=fmt))
    db_module.save_tier_overrides(USER_A, {"vb_wr1": 1200.0, "vb_wr3": 2100.0},
                                  scoring_format="1qb_ppr")
    assert db_module.load_member_rankings(LEAGUE, exclude_user_id="",
                                          scoring_format="1qb_ppr")[USER_A]
    assert _token_snapshot(_share(world, give, recv)) == before
    boom = AssertionError("a board was read")
    with patch.object(server, "load_member_rankings", side_effect=boom, create=True), \
         patch.object(db_module, "load_member_rankings", side_effect=boom), \
         patch.object(db_module, "load_tier_overrides", side_effect=boom):
        assert _token_snapshot(_share(world, give, recv)) == before


def test_market_mode_regardless_of_the_sharers_stud_tax_setting(world):
    give, recv = FIVE_FOR_ONE
    with patch.object(server._trade_service_mod, "stud_tax_mode_for_user",
                      lambda uid: "heavy"):
        snap = json.loads(_token_snapshot(_share(world, give, recv)))
    market = server._consensus_verdict(give, recv, "1qb_ppr", LEAGUE)
    with server._trade_service_mod.stud_tax_override("heavy"):
        heavy = server._consensus_verdict(give, recv, "1qb_ppr", LEAGUE)
    assert (snap["favors"], snap["firsts"]) == (market["favors"], market["gap"]["firsts"])
    assert heavy["gap"]["firsts"] != market["gap"]["firsts"]


# ---------------------------------------------------------------------------
# 8. No bar: the #511 card, byte for byte; layouts; the share pages
# ---------------------------------------------------------------------------

def _legacy_card(give, recv):
    players = db_module.load_players_by_ids([str(x) for x in give + recv])
    return og_image._render_trade_card_png(give_ids=give, receive_ids=recv,
                                           players_by_id=players)


@pytest.mark.parametrize("give, recv, legacy", [
    (["vb_wr1", "ghost_player"], ["vb_rb1"], False),   # unpriceable at mint
    (["vb_wr1"], [], False),                           # an empty side
    (["vb_te1"], ["vb_qb1"], True),                    # priceable, NULL snapshot
])
def test_no_bar_card_is_the_511_card_byte_for_byte(world, give, recv, legacy):
    tok = _legacy_share(give, recv) if legacy else _share(world, give, recv)
    r, calls = _spied(world, f"/og/trade/{tok}.png")
    assert not _has_track(calls)
    assert r.data == _legacy_card(give, recv)
    titles = [xy for xy, text, _ in _texts(calls) if text == "Trade Match"]
    assert titles == [(60, 85)]
    assert _panels(calls) == [(175, 455), (175, 455)]


def test_verdict_none_renders_the_default_card():
    players = {"p1": {"full_name": "Pat One", "position": "WR"},
               "p2": {"full_name": "Sam Two", "position": "RB"}}
    plain = og_image._render_trade_card_png(["p1"], ["p2"], players)
    assert og_image._render_trade_card_png(
        ["p1"], ["p2"], players, verdict=None, as_of=None,
        scoring_format=None, pick_labels=None) == plain
    assert og_image._render_trade_card_png(
        ["p1"], ["p2"], players, verdict=None, as_of=AS_OF,
        scoring_format="sf_tep", pick_labels={}) == plain


def test_bar_layout_moves_the_block_up_and_stays_in_its_band(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *LEAN_GET)}.png")
    titles = [xy for xy, text, _ in _texts(calls) if text == "Trade Match"]
    assert titles == [(60, 45)]
    assert _panels(calls) == [(125, 375), (125, 375)]
    rules = [a[0] for name, a, _ in calls if name == "line"]
    assert rules == [[(60, 560), (CARD_W - 60, 560)]]
    bar_y = [a[0][1] for name, a, kw in calls
             if name in ("rectangle", "rounded_rectangle")
             and kw.get("fill") != PANEL_FILL and a[0][1] > 375]
    bar_y += [xy[1] for xy, text, _ in _texts(calls) if 375 < xy[1] < 560]
    assert bar_y and all(375 < y < 560 for y in bar_y)


def test_five_for_one_keeps_plus_n_more_inside_the_panel(world):
    _, calls = _spied(world, f"/og/trade/{_share(world, *FIVE_FOR_ONE)}.png")
    more = [xy for xy, text, _ in _texts(calls) if text == "+3 more"]
    assert more == [(84, 125 + 70 + 2 * 66 + 6)]
    assert _has_track(calls)


def test_trade_page_description_and_alt_follow_the_bar(world):
    with_bar = world.get(f"/s/trade/{_share(world, *LEAN_GIVE)}").get_data(as_text=True)
    even = world.get(f"/s/trade/{_share(world, *EVEN)}").get_data(as_text=True)
    no_bar = world.get(
        f"/s/trade/{_share(world, ['ghost'], ['vb_wr1'])}").get_data(as_text=True)
    assert _meta(with_bar, "name", "description") == TRADE_WITH_BAR
    assert _meta(with_bar, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar leaning to the give side, "
        f"≈ a Mid 1st in value. Estimate from consensus dynasty values, 1QB PPR, {AS_OF}.")
    assert _meta(even, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar, about even in value. "
        f"Estimate from consensus dynasty values, 1QB PPR, {AS_OF}.")
    assert _meta(no_bar, "name", "description") == TRADE_NO_BAR
    assert _meta(no_bar, "property", "og:image:alt") == "Trade card: the give/get breakdown."
    for html in (with_bar, even, no_bar):
        assert "fair" not in html.lower()


def test_card_png_is_valid(world):
    r, _ = _spied(world, f"/og/trade/{_share(world, *LEAN_GET)}.png")
    img = og_image.Image.open(io.BytesIO(r.data))
    assert img.size == (1200, 630)


# ---------------------------------------------------------------------------
# Deletion and export (accounts.delete_user_data / export_user_data)
# ---------------------------------------------------------------------------

def test_deletion_and_export_cover_the_snapshot(world):
    """A trade token's snapshot leaves with the sharer's row on deletion and
    is exported with it (only `token` is omitted). A package row is
    anonymized, and its snapshot holds nothing that names the sharer."""
    from backend import accounts
    mid = _add_match(*LEAN_GET)
    a_tok = _mint_token(world, mid, USER_A)
    b_tok = _mint_token(world, mid, USER_B)
    sid = _share_package(world, *LEAN_GIVE, scoring_format="1qb_ppr")
    a_snap, b_snap, pkg_snap = _token_snapshot(a_tok), _token_snapshot(b_tok), _package_snapshot(sid)
    assert a_snap and b_snap and pkg_snap

    exported = accounts.export_user_data(USER_A)["tables"]["trade_share_tokens"]
    assert [(r["match_id"], r["value_snapshot"]) for r in exported] == [(mid, a_snap)]
    assert all("token" not in r for r in exported)

    accounts.delete_user_data(USER_A)
    t = db_module.trade_share_tokens_table
    with db_module.engine.connect() as conn:
        left = conn.execute(select(t.c.created_by, t.c.value_snapshot)).all()
    assert [tuple(r) for r in left] == [(USER_B, b_snap)]
    pkg = db_module.load_shared_package(sid)
    assert pkg["user_id"] == accounts.DELETED_USER_PLACEHOLDER
    assert pkg["value_snapshot"] == pkg_snap and USER_A not in pkg_snap


# ---------------------------------------------------------------------------
# 9. The migration (database._migrate_db, migration_cols)
# ---------------------------------------------------------------------------

def test_migration_adds_the_column_and_old_rows_read_null(tmp_path, monkeypatch):
    """A DB from before this change (both tables without value_snapshot,
    with rows) gets exactly the two ALTERs on boot, and its rows read NULL:
    a pre-snapshot share draws no bar."""
    engine = create_engine("sqlite:///" + str(tmp_path / "old.sqlite3"),
                           connect_args={"check_same_thread": False})
    db_module.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    db_module._migrate_db()
    with engine.begin() as conn:
        for table in ("trade_share_tokens", "shared_packages"):
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN value_snapshot"))
        conn.execute(insert(db_module.trade_matches_table).values(
            id=7, league_id=LEAGUE, user_a_id=USER_A, user_b_id=USER_B,
            user_a_give='["vb_te1"]', user_a_receive='["vb_qb1"]', status="pending"))
        conn.execute(text("INSERT INTO trade_share_tokens (token, match_id, created_by, "
                          "created_at) VALUES ('OLDTOKEN0000000000000A', 7, :u, "
                          "'2026-10-20T00:00:00+00:00')"), {"u": USER_A})
        conn.execute(text("INSERT INTO shared_packages (short_id, user_id, give_ids, "
                          "receive_ids, created_at) VALUES ('oldPkg', :u, '[\"vb_te1\"]', "
                          "'[\"vb_qb1\"]', '2026-10-20T00:00:00+00:00')"), {"u": USER_A})
    for table in ("trade_share_tokens", "shared_packages"):
        assert "value_snapshot" not in {c["name"] for c in inspect(engine).get_columns(table)}

    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):
        statements.append(" ".join(statement.split()))

    db_module._migrate_db()
    assert [s for s in statements if "ADD COLUMN" in s.upper()] == [
        "ALTER TABLE trade_share_tokens ADD COLUMN value_snapshot TEXT",
        "ALTER TABLE shared_packages ADD COLUMN value_snapshot TEXT"]
    for table in ("trade_share_tokens", "shared_packages"):
        assert "value_snapshot" in {c["name"] for c in inspect(engine).get_columns(table)}
    assert db_module.resolve_trade_share_token("OLDTOKEN0000000000000A")["value_snapshot"] is None
    assert db_module.load_shared_package("oldPkg")["value_snapshot"] is None
    assert server._value_bar_from_snapshot(None) is None
    engine.dispose()
