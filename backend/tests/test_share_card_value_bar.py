"""The app's value bar on the og share cards (docs/plans/share-card-value-bar/
scope.md; words: marketing addendum 14; geometry: design-lead v2).

Pins:
  1. `_consensus_verdict` is evaluate's own verdict (parity, same ids and
     format), and evaluate prices through it.
  2. The bar is drawn per verdict: the even nub, a lean right toward YOU GET,
     a lean left toward YOU GIVE, the clamp at one Mid 1st, one neutral fill.
  3. The words: the label line, the basis and date line (both branches; the
     date is the render's UTC date), and none of the never-list.
  3b. The +/-2nd ticks sit where a Mid 2nd sits today, not at the app's
     drifted 0.57.
  4. Draft picks get a label and a neutral "PK" chip, never "Unknown player".
  5. A package draws a bar only with a real `?fmt=`, and /s/p carries it into
     og:image.
  6. The sharer's private board and rankings never move the verdict.
  7. No bar (unpriceable id, empty or zero side, no snapshot) is the #511
     no-bar card, byte for byte; the bar's moved-up layout only with a bar.
  8. The share pages' descriptions and og:image:alt follow the image.

Synthetic in-memory SQLite only (test_trade_share_tokens.py's fixture); the
universal pool is injected, as in test_trade_evaluate.py.
"""
import io
import json
import re
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.server as server
from backend.tests.test_trade_share_tokens import (  # noqa: F401  (env is a fixture)
    SHARE_ON, USER_A, USER_B, env,
)

pytest.importorskip("PIL")
from backend import og_image  # noqa: E402

LEAGUE = "vb-league"
# The clock every `world` test runs on: 02:30 UTC on Nov 14 is still Nov 13
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
    # A gap of 0.57 Mid 1sts: still labelled "a Late 1st" (nearer it than an
    # Early 2nd), and exactly where the app's static tick sits. The render
    # that showed the contradiction.
    "vb_l5a": ("Lane Boundary", "WR", _v2e(4000.0)),
    "vb_l5b": ("Morgan Boundary", "WR", _v2e(4000.0 - 0.57 * MID_1ST)),
}
OWNED_PICK = f"{LEAGUE}_2026_1_3"
UNPRICED_PICK = f"{LEAGUE}_2027_2_9"      # well-formed, not in the league's picks
LEAGUE_PICKS = [{
    "pick_id": OWNED_PICK, "league_id": LEAGUE, "owner_user_id": USER_B,
    "season": 2026, "round": 1, "original_roster_id": "3", "pool_value": 3000.0,
    "is_traded": 0, "original_username": "someleaguemate",
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

CARD_W = og_image.CARD_W
TRACK = [60, 452, 1140, 470]
PANEL_FILL = (255, 255, 255, 18)
NEVER = re.compile(r"\b(win|wins|won|lose|loses|lost|you|they|fair|unfair|fairness|"
                   r"steal|rob|worth|owes|today|apart)\b|%|\+|−|\d,\d{3}", re.I)


def _frozen_datetime(instant):
    """`server.datetime` with now() pinned to `instant` (aware, UTC)."""
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)
    return _Frozen


def _seed(fmt):
    seed = {pid: elo + (150.0 if fmt == "sf_tep" and pos == "QB" else 0.0)
            for pid, (_, pos, elo) in PLAYERS.items()}
    for (rnd, tier), elo in server.GENERIC_PICK_SEEDS.items():
        seed[f"generic_pick_{rnd}_{tier.lower()}"] = elo
    return seed


@pytest.fixture()
def world(env, monkeypatch):
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    for fmt in ("1qb_ppr", "sf_tep"):
        monkeypatch.setitem(server.g_universal_by_format, fmt,
                            {"players": [], "seed": _seed(fmt)})
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


def _share(give, recv, sharer=USER_A, league=LEAGUE) -> str:
    with db_module.engine.begin() as conn:
        mid = conn.execute(insert(db_module.trade_matches_table).values(
            league_id=league, user_a_id=USER_A, user_b_id=USER_B,
            user_a_give=json.dumps(give), user_a_receive=json.dumps(recv),
            matched_at="2026-10-30T00:00:00+00:00", status="pending",
        )).inserted_primary_key[0]
    return db_module.create_trade_share_token(mid, sharer)


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
    """Boxes drawn on the track in the bar's fill colour (lean or nub)."""
    return [list(a[0]) for name, a, kw in calls
            if name == "rounded_rectangle" and kw.get("fill") == og_image.VB_FILL
            and a[0][1] == TRACK[1] and a[0][3] == TRACK[3]]


def _has_track(calls):
    return any(name == "rounded_rectangle" and list(a[0]) == TRACK
               for name, a, _ in calls)


def _label_runs(calls):
    return [(text, kw["fill"]) for (x, y), text, kw in _texts(calls)
            if y == og_image.VB_LABEL_Y]


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


def test_card_verdict_is_evaluates_verdict(world):
    """The trade card's verdict is evaluate's, on the drawn lists, in the
    league's own format."""
    _set_league_format("sf_tep")
    give, recv = LEAN_GET
    tok = _share(give, recv)
    card = server._trade_share_card_kwargs(db_module.resolve_trade_share_token(tok))
    d = _evaluate(world, give, recv, "sf_tep")
    assert card["verdict"] == {"favors": d["favors"], "gap": d["gap"],
                               "second_in_firsts": SECOND_IN_FIRSTS}
    assert (card["as_of"], card["scoring_format"]) == (AS_OF, "sf_tep")


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
# 2. The bar
# ---------------------------------------------------------------------------

def _bar_length(give, recv, fmt="1qb_ppr"):
    v = server._consensus_verdict(give, recv, fmt, LEAGUE)
    return v, round(min(1.0, abs(v["gap"]["firsts"])) * 540)


def test_even_draws_the_centred_nub(world):
    v, _ = _bar_length(*EVEN)
    assert v["favors"] == "even"
    _, calls = _spied(world, f"/og/trade/{_share(*EVEN)}.png")
    assert _has_track(calls)
    assert _track_fills(calls) == [[594, 452, 606, 470]]


def test_lean_toward_you_get_fills_right_of_centre(world):
    v, length = _bar_length(*LEAN_GET)
    assert v["favors"] == "receive" and 0 < length < 540
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GET)}.png")
    assert _track_fills(calls) == [[600, 452, 600 + length, 470]]


def test_lean_toward_you_give_fills_left_of_centre(world):
    v, length = _bar_length(*LEAN_GIVE)
    assert v["favors"] == "give" and 0 < length < 540
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GIVE)}.png")
    assert _track_fills(calls) == [[600 - length, 452, 600, 470]]


def test_a_huge_gap_clamps_at_one_first(world):
    v, length = _bar_length(*HUGE)
    assert abs(v["gap"]["firsts"]) > 1 and length == 540
    _, calls = _spied(world, f"/og/trade/{_share(*HUGE)}.png")
    assert _track_fills(calls) == [[60, 452, 600, 470]]


def test_one_neutral_fill_ticks_and_centre_line(world):
    """No pos/warn/ice on the public card: lean and nub are VB_FILL. The
    +/-2nd ticks sit at 600 -/+ SEC_PX and the centre at 600, 2px wide, 8px
    past the track."""
    for case in (EVEN, LEAN_GET, LEAN_GIVE):
        _, calls = _spied(world, f"/og/trade/{_share(*case)}.png")
        bar_fills = {kw.get("fill") for name, a, kw in calls
                     if name == "rounded_rectangle" and 452 <= a[0][1] <= 470}
        assert bar_fills == {og_image.VB_TRACK, og_image.VB_FILL}, bar_fills
        rects = [(list(a[0]), kw.get("fill")) for name, a, kw in calls
                 if name == "rectangle"]
        lo, hi = 600 - SEC_PX, 600 + SEC_PX
        assert rects == [([lo - 1, 444, lo, 478], og_image.VB_TICK),
                         ([hi - 1, 444, hi, 478], og_image.VB_TICK),
                         ([599, 444, 600, 478], og_image.VB_CENTER)], rects


# ---------------------------------------------------------------------------
# 3b. The +/-2nd ticks: where a Mid 2nd sits today
# ---------------------------------------------------------------------------

def _tick_xs(calls):
    """x of the two VB_TICK rectangles (their right pixel column)."""
    return [a[0][2] for name, a, kw in calls
            if name == "rectangle" and kw.get("fill") == og_image.VB_TICK]


def _scale_label_centres(calls):
    draw = og_image.ImageDraw.Draw(og_image.Image.new("RGB", (1, 1)))
    return [(text, xy[0] + og_image._text_width(draw, text, kw["font"]) // 2)
            for xy, text, kw in _texts(calls) if xy[1] == og_image.VB_SCALE_Y]


def test_second_ticks_sit_at_the_current_mid_2nd_fraction(world):
    assert 0.2 < SECOND_IN_FIRSTS < 0.35        # not the app's 0.57
    v = server._share_value_bar(*LEAN_GET, "1qb_ppr", LEAGUE)
    assert v["verdict"]["second_in_firsts"] == SECOND_IN_FIRSTS
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GET)}.png")
    assert _tick_xs(calls) == [600 - SEC_PX, 600 + SEC_PX]
    # The "2nd" labels are centred on their ticks.
    seconds = [cx for text, cx in _scale_label_centres(calls) if text == "2nd"]
    assert len(seconds) == 2
    assert abs(seconds[0] - (600 - SEC_PX)) <= 1 and abs(seconds[1] - (600 + SEC_PX)) <= 1


@pytest.mark.parametrize("case", [GAP_LATE_1ST, GAP_057])
def test_a_late_1st_fill_ends_past_the_drawn_2nd_tick(world, case):
    _, calls = _spied(world, f"/og/trade/{_share(*case)}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == "≈ a Late 1st in value"
    (fill,) = _track_fills(calls)
    assert fill[0] == 600                       # leans right, toward YOU GET
    right_tick = _tick_xs(calls)[1]
    assert fill[2] > right_tick + 20, (fill, right_tick)


def test_a_mid_2nd_fill_ends_at_the_drawn_2nd_tick(world):
    _, calls = _spied(world, f"/og/trade/{_share(*GAP_MID_2ND)}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == "≈ a Mid 2nd in value"
    (fill,) = _track_fills(calls)
    assert fill[0] == 600
    right_tick = _tick_xs(calls)[1]
    assert abs(fill[2] - right_tick) <= 20, (fill, right_tick)


def test_ticks_fall_back_to_the_apps_constant_without_the_fraction():
    players = {"p1": {"full_name": "Pat One", "position": "WR"},
               "p2": {"full_name": "Sam Two", "position": "RB"}}
    verdict = {"favors": "receive",
               "gap": {"firsts": 0.5, "pick_equivalent": None}}
    calls = []
    cls = og_image.ImageDraw.ImageDraw
    real = cls.rectangle

    def spy(self, *a, **kw):
        calls.append(("rectangle", a, kw))
        return real(self, *a, **kw)
    with patch.object(cls, "rectangle", spy):
        og_image._render_trade_card_png(["p1"], ["p2"], players, verdict=verdict,
                                        as_of=AS_OF, scoring_format="1qb_ppr")
    sec = round(og_image.APP_SECOND_IN_FIRSTS * 540)
    assert og_image.APP_SECOND_IN_FIRSTS == 0.57 and sec == 308
    assert _tick_xs(calls) == [600 - sec, 600 + sec]


# ---------------------------------------------------------------------------
# 3. The words
# ---------------------------------------------------------------------------

def test_label_line_pick_terms(world):
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GET)}.png")
    runs = _label_runs(calls)
    assert runs == [("≈ ", og_image.VB_CHALK), ("an Early 2nd", og_image.VB_PICK),
                    (" in value", og_image.VB_CHALK)], runs


def test_label_line_firsts_when_no_single_pick_fits(world):
    v, _ = _bar_length(*HUGE)
    assert v["gap"]["pick_equivalent"] is None
    _, calls = _spied(world, f"/og/trade/{_share(*HUGE)}.png")
    text = "".join(t for t, _ in _label_runs(calls))
    assert text == f"≈ {abs(v['gap']['firsts']):.1f} Mid 1sts in value" == \
        "≈ 4.9 Mid 1sts in value"


def test_label_line_about_even(world):
    _, calls = _spied(world, f"/og/trade/{_share(*EVEN)}.png")
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
    tok = _share(*LEAN_GET)
    with patch.object(og_image, "_text_width", side_effect=width):
        _, calls = _spied(world, f"/og/trade/{tok}.png")
    basis = [(xy, text, kw["fill"]) for xy, text, kw in _texts(calls)
             if text.startswith("Estimate")]
    assert basis == [((60, 518), expected.format(fmt="SF TEP"), og_image.VB_DIM)]


def test_scale_labels_have_no_signs_and_no_end_labels(world):
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GIVE)}.png")
    scale = [text for (x, y), text, _ in _texts(calls) if y == og_image.VB_SCALE_Y]
    assert scale == ["1st", "2nd", "Even", "2nd", "1st"]


@pytest.mark.parametrize("case", [EVEN, LEAN_GET, LEAN_GIVE, HUGE])
def test_bar_words_avoid_the_never_list(world, case):
    """Nothing drawn in the bar band (y >= 375) says win/lose/you/they/fair,
    a percentage, a sign or a value number; no heading."""
    _, calls = _spied(world, f"/og/trade/{_share(*case)}.png")
    footer = "Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com"
    bar_texts = [text for (x, y), text, _ in _texts(calls)
                 if 375 <= y < 560 and text != footer]
    assert bar_texts
    for text in bar_texts:
        assert not NEVER.search(text), text
        assert "swing" not in text.lower(), text


# ---------------------------------------------------------------------------
# 4. Draft picks: labels and a neutral PK chip
# ---------------------------------------------------------------------------

def test_picks_get_labels_and_a_neutral_pk_chip(world):
    give = ["generic_pick_1_mid", OWNED_PICK]
    recv = ["vb_wr1"]
    _, calls = _spied(world, f"/og/trade/{_share(give, recv)}.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "Mid 1st Round Pick" in drawn and "2026 1st" in drawn
    assert "Unknown player" not in drawn
    assert not any("someleaguemate" in t for t in drawn)       # no leaguemate name
    pk_labels = [(xy, kw["fill"]) for xy, text, kw in _texts(calls) if text == "PK"]
    assert len(pk_labels) == 2 and {f for _, f in pk_labels} == {(12, 14, 17)}
    pk_chips = [a[0] for name, a, kw in calls if name == "rounded_rectangle"
                and kw.get("fill") == og_image.PICK_CHIP_FILL
                and a[0][2] - a[0][0] == 56]
    assert len(pk_chips) == 2
    assert og_image.PICK_CHIP_FILL not in og_image.POS_COLORS.values()
    assert _has_track(calls)                     # both picks priced: a bar


def test_an_unpriceable_pick_keeps_its_label_but_draws_no_bar(world):
    _, calls = _spied(world, f"/og/trade/{_share([UNPRICED_PICK], ['vb_wr1'])}.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "2027 2nd" in drawn and "Unknown player" not in drawn
    assert not _has_track(calls)


def test_share_pick_labels():
    assert server._share_pick_labels(
        ["generic_pick_2_early", f"{LEAGUE}_2028_3_12", "4034", "o8p1", ""]) == {
        "generic_pick_2_early": "Early 2nd Round Pick",
        f"{LEAGUE}_2028_3_12": "2028 3rd"}


# ---------------------------------------------------------------------------
# 5. Packages: a bar only with a real ?fmt=, carried by /s/p into og:image
# ---------------------------------------------------------------------------

SID = "vbPkg01"


def _package(give=LEAN_GET[0], recv=LEAN_GET[1]):
    assert db_module.create_shared_package(SID, USER_A, list(give), list(recv))


def _panels(calls):
    return [(a[0][1], a[0][3]) for name, a, kw in calls
            if name == "rounded_rectangle" and kw.get("fill") == PANEL_FILL]


@pytest.mark.parametrize("query", ["", "?fmt=", "?fmt=bogus", "?fmt=SF_TEP"])
def test_package_without_a_real_format_draws_no_bar(world, query):
    _package()
    _, calls = _spied(world, f"/og/p/{SID}.png{query}")
    assert not _has_track(calls)
    assert _panels(calls) == [(175, 455), (175, 455)]


@pytest.mark.parametrize("fmt, label", [("sf_tep", "SF TEP"), ("1qb_ppr", "1QB PPR")])
def test_package_with_fmt_draws_the_bar_in_that_format(world, fmt, label):
    _package()
    _, calls = _spied(world, f"/og/p/{SID}.png?fmt={fmt}")
    assert _has_track(calls)
    assert _panels(calls) == [(125, 375), (125, 375)]
    v = server._consensus_verdict(*LEAN_GET, fmt)
    length = round(min(1.0, abs(v["gap"]["firsts"])) * 540)
    assert _track_fills(calls) == [[600, 452, 600 + length, 470]]
    assert any(text.endswith(f"· {label} · {AS_OF}") for _, text, _ in _texts(calls))


def _meta(html, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', html)
    return m.group(1) if m else None


def test_share_package_page_carries_fmt_into_og_image(world):
    _package()
    with patch.object(server, "is_enabled", SHARE_ON):
        with_fmt = world.get(f"/s/p/{SID}?fmt=sf_tep").get_data(as_text=True)
        bogus = world.get(f"/s/p/{SID}?fmt=bogus").get_data(as_text=True)
        bare = world.get(f"/s/p/{SID}").get_data(as_text=True)
    assert _meta(with_fmt, "property", "og:image") == \
        f"http://localhost/og/p/{SID}.png?fmt=sf_tep"
    assert _meta(with_fmt, "name", "twitter:image") == \
        f"http://localhost/og/p/{SID}.png?fmt=sf_tep"
    assert f'<img src="/og/p/{SID}.png?fmt=sf_tep"' in with_fmt
    for html in (bogus, bare):
        assert _meta(html, "property", "og:image") == f"http://localhost/og/p/{SID}.png"

    assert _meta(with_fmt, "property", "og:description") == (
        "A 2-player dynasty trade package. See the give/get breakdown and how the "
        "values compare in draft-pick terms. Values are an estimate from market "
        "consensus, not a guarantee.")
    # Superflex prices the QB higher: the same package reads ~1.9 firsts in
    # sf_tep and ~an Early 2nd in 1qb_ppr, which is why no fmt means no bar.
    assert _meta(with_fmt, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar leaning to the get side, "
        f"≈ 1.9 Mid 1sts in value. Estimate from consensus dynasty values, SF TEP, {AS_OF}.")
    for html in (bogus, bare):
        assert _meta(html, "property", "og:description") == \
            "A 2-player dynasty trade package. See the give/get breakdown."
        assert _meta(html, "property", "og:image:alt") == \
            "Trade card: the give/get breakdown."


# ---------------------------------------------------------------------------
# 6. The sharer's private board never moves the verdict
# ---------------------------------------------------------------------------

def test_private_boards_do_not_change_the_verdict(world):
    give, recv = LEAN_GIVE
    tok = _share(give, recv)
    match = db_module.resolve_trade_share_token(tok)
    before = server._trade_share_card_kwargs(match)
    assert before["verdict"] is not None

    # Both parties rank the trade's players far from consensus, in both
    # formats, and the sharer saves tier overrides and an active session.
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

    after = server._trade_share_card_kwargs(match)
    assert after == before
    # The card never even asks for a board.
    boom = AssertionError("a board was read")
    with patch.object(server, "load_member_rankings", side_effect=boom, create=True), \
         patch.object(db_module, "load_member_rankings", side_effect=boom), \
         patch.object(db_module, "load_tier_overrides", side_effect=boom):
        assert server._trade_share_card_kwargs(match) == before
        _, calls = _spied(world, f"/og/trade/{tok}.png")
    assert _has_track(calls)


def test_market_mode_regardless_of_the_sharers_stud_tax_setting(world):
    """The card is priced in market mode even when the sharer's stored
    stud-tax mode is heavy; evaluate prices that user in heavy."""
    give, recv = FIVE_FOR_ONE
    tok = _share(give, recv)
    with patch.object(server._trade_service_mod, "stud_tax_mode_for_user",
                      lambda uid: "heavy"):
        card = server._trade_share_card_kwargs(db_module.resolve_trade_share_token(tok))
    market = server._consensus_verdict(give, recv, "1qb_ppr", LEAGUE)
    with server._trade_service_mod.stud_tax_override("heavy"):
        heavy = server._consensus_verdict(give, recv, "1qb_ppr", LEAGUE)
    assert card["verdict"] == {"favors": market["favors"], "gap": market["gap"],
                               "second_in_firsts": SECOND_IN_FIRSTS}
    assert heavy["gap"] != market["gap"]


def test_user_b_share_draws_the_mirrored_verdict(world):
    with db_module.engine.begin() as conn:
        mid = conn.execute(insert(db_module.trade_matches_table).values(
            league_id=LEAGUE, user_a_id=USER_A, user_b_id=USER_B,
            user_a_give=json.dumps(LEAN_GET[0]), user_a_receive=json.dumps(LEAN_GET[1]),
            matched_at="2026-10-30T00:00:00+00:00", status="pending",
        )).inserted_primary_key[0]
    a = server._trade_share_card_kwargs(db_module.resolve_trade_share_token(
        db_module.create_trade_share_token(mid, USER_A)))
    b = server._trade_share_card_kwargs(db_module.resolve_trade_share_token(
        db_module.create_trade_share_token(mid, USER_B)))
    assert (a["verdict"]["favors"], b["verdict"]["favors"]) == ("receive", "give")
    assert a["verdict"]["gap"]["value"] == b["verdict"]["gap"]["value"]


# ---------------------------------------------------------------------------
# 7. No bar: the #511 card, byte for byte; layouts
# ---------------------------------------------------------------------------

def _legacy_card(give, recv):
    players = db_module.load_players_by_ids([str(x) for x in give + recv])
    return og_image._render_trade_card_png(give_ids=give, receive_ids=recv,
                                           players_by_id=players)


@pytest.mark.parametrize("give, recv", [
    (["vb_wr1", "ghost_player"], ["vb_rb1"]),     # an unpriceable id
    (["vb_wr1"], []),                             # an empty side
])
def test_no_bar_card_is_the_511_card_byte_for_byte(world, give, recv):
    r, calls = _spied(world, f"/og/trade/{_share(give, recv)}.png")
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
    _, calls = _spied(world, f"/og/trade/{_share(*LEAN_GET)}.png")
    titles = [xy for xy, text, _ in _texts(calls) if text == "Trade Match"]
    assert titles == [(60, 45)]
    assert _panels(calls) == [(125, 375), (125, 375)]
    rules = [a[0] for name, a, _ in calls if name == "line"]
    assert rules == [[(60, 560), (CARD_W - 60, 560)]]
    # Everything the bar draws sits between the panels and the footer rule.
    bar_y = [a[0][1] for name, a, kw in calls
             if name in ("rectangle", "rounded_rectangle")
             and kw.get("fill") not in (PANEL_FILL,) and a[0][1] > 375]
    bar_y += [xy[1] for xy, text, _ in _texts(calls) if 375 < xy[1] < 560]
    assert bar_y and all(375 < y < 560 for y in bar_y)


def test_five_for_one_keeps_plus_n_more_inside_the_panel(world):
    give, recv = FIVE_FOR_ONE
    _, calls = _spied(world, f"/og/trade/{_share(give, recv)}.png")
    more = [xy for xy, text, _ in _texts(calls) if text == "+3 more"]
    assert more == [(84, 125 + 70 + 2 * 66 + 6)]
    assert _has_track(calls)


@pytest.mark.parametrize("why", ["zero_side", "dropped"])
def test_rule_c_no_bar(world, why):
    give, recv = LEAN_GET
    if why == "zero_side":
        real = server._consensus_verdict

        def zero(*a, **kw):
            out = real(*a, **kw)
            out["receive_value"] = 0.0
            return out
        with patch.object(server, "_consensus_verdict", side_effect=zero):
            assert server._share_value_bar(give, recv, "1qb_ppr", LEAGUE) is None
        return
    assert server._share_value_bar(give + ["ghost"], recv, "1qb_ppr", LEAGUE) is None
    assert server._share_value_bar(give, recv, "1qb_ppr", LEAGUE) is not None


# ---------------------------------------------------------------------------
# 8. /s/trade description and alt follow the image
# ---------------------------------------------------------------------------

def test_trade_page_description_and_alt_follow_the_bar(world):
    with_bar = world.get(f"/s/trade/{_share(*LEAN_GIVE)}").get_data(as_text=True)
    even = world.get(f"/s/trade/{_share(*EVEN)}").get_data(as_text=True)
    no_bar = world.get(f"/s/trade/{_share(['ghost'], ['vb_wr1'])}").get_data(as_text=True)
    assert _meta(with_bar, "name", "description") == (
        "A dynasty fantasy trade. See the give/get breakdown and how the values "
        "compare in draft-pick terms. Values are an estimate from market consensus, "
        "not a guarantee.")
    assert _meta(with_bar, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar leaning to the give side, "
        f"≈ a Mid 1st in value. Estimate from consensus dynasty values, 1QB PPR, {AS_OF}.")
    assert _meta(even, "property", "og:image:alt") == (
        "Trade card: the give/get breakdown and a value bar, about even in value. "
        f"Estimate from consensus dynasty values, 1QB PPR, {AS_OF}.")
    assert _meta(no_bar, "name", "description") == \
        "A dynasty fantasy trade. See the give/get breakdown."
    assert _meta(no_bar, "property", "og:image:alt") == "Trade card: the give/get breakdown."
    for html in (with_bar, even, no_bar):
        assert "fair" not in html.lower()


def test_value_bar_date_format():
    assert server._value_bar_date(date(2026, 11, 3)) == "Nov 3, 2026"
    assert server._value_bar_date(date(2026, 12, 25)) == "Dec 25, 2026"


@pytest.mark.parametrize("instant, shown", [
    (FROZEN_NOW, "Nov 14, 2026"),
    (datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), "Dec 31, 2026"),
    (datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc), "Jan 1, 2027"),
])
def test_the_date_is_the_renders_utc_date(world, instant, shown):
    """Legal: render-time values carry the day they were computed, so the
    basis line's date is the UTC date of the render (frozen clock), never a
    snapshot's date."""
    tok = _share(*LEAN_GET)
    with patch.object(server, "datetime", _frozen_datetime(instant)):
        assert server._share_value_bar(*LEAN_GET, "1qb_ppr", LEAGUE)["as_of"] == shown
        _, calls = _spied(world, f"/og/trade/{tok}.png")
    basis = [text for (x, y), text, _ in _texts(calls) if y == og_image.VB_BASIS_Y]
    assert len(basis) == 1 and basis[0].endswith(f"· 1QB PPR · {shown}"), basis


def test_card_png_is_valid(world):
    r, _ = _spied(world, f"/og/trade/{_share(*LEAN_GET)}.png")
    img = og_image.Image.open(io.BytesIO(r.data))
    assert img.size == (1200, 630)
