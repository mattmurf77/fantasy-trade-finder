"""Product's final label rule on the share card's value bar (legal R28.27),
stacked on #564 (test_share_card_value_bar.py holds the bar itself).

  B1 "≈ a Mid 2nd in value"     a generic pick fits the gap, at any size
  B2 "≈ 1.4 Mid 1sts in value"  no pick fits and the gap is 1 first or more
  B3 "About even in value"      no pick fits and the gap is under 1 first
                                (or `favors` is even with no pick); the
                                fill is the centre mark

Pins:
  1. B1 whenever a pick fits, including at 1 first or more.
  2. B2 only at 1 first or more with no pick.
  3. B3 below 1 first with no pick: the ice nub, no lean, "about even" alt.
  4. Legal condition 1 (property): over a 0-3 firsts sweep, "About even"
     never covers a gap `_pick_gap_equivalent` fits a pick to.
  5. Legal condition 2 (property): whenever the label is "About even", the
     fill is the centre mark.
  6. The OPEN even-band-with-pick case (favors even, a pick label) keeps
     today's "About even" + centre mark, pinned as such until it is decided.
  7. Parity with the app's B2 guard (#567, mobile/tests/check-value-bar-b2.js).
  8. Legal (f): a traded owned pick reads "2026 1st", never "(from ...)".
"""
import json

import pytest
from sqlalchemy import insert

import backend.database as db_module
import backend.server as server
from backend.tests.test_share_card_value_bar import (  # noqa: F401  (env, world are fixtures)
    AS_OF, EVEN, HUGE, LEAGUE, MID_1ST, SECOND_IN_FIRSTS, USER_A, USER_B,
    _e2v, _has_track, _label_runs, _meta, _share, _spied, _texts,
    _token_snapshot, _track_fills, _v2e, env, world,
)

pytest.importorskip("PIL")
from backend import og_image  # noqa: E402

ABOUT_EVEN = "About even in value"
NUB = ([594, 452, 606, 470], og_image.ICE_BASE)
LEANS = (og_image.SEMANTIC_POS, og_image.SEMANTIC_WARN)
LATE_4TH = _e2v(server.GENERIC_PICK_SEEDS[(4, "Late")])

# id: (name, position, seed Elo), added to #564's world for this file.
EXTRA = {
    # A 1.3-first gap: past one Mid 1st, but still a pick fit (the fit runs
    # to 1.25 x an Early 1st, ~1.77 firsts), so B1 "an Early 1st".
    "b2_o1a": ("Nico Overfirst", "WR", _v2e(9000.0)),
    "b2_o1b": ("Oakley Overfirst", "WR", _v2e(9000.0 - 1.3 * MID_1ST)),
    # A 0.056-first gap: under half a Late 4th, so no pick fits, and the
    # point ratio is ~0.89, so `favors` leans. Before this rule the card read
    # "≈ 0.1 Mid 1sts in value"; now B3.
    "b2_s1a": ("Parker Sliver", "TE", _v2e(1000.0 + 0.056 * MID_1ST)),
    "b2_s1b": ("Quinn Sliver", "TE", _v2e(1000.0)),
}
GAP_OVER_1ST = (["b2_o1b"], ["b2_o1a"])     # YOU GET heavier by 1.3 firsts
SLIVER = (["b2_s1b"], ["b2_s1a"])           # YOU GET heavier by 0.06 firsts

TRADED_PICK = f"{LEAGUE}_2026_1_5"
TRADED_FROM = "tradedfromleaguemate"


@pytest.fixture()
def b2world(world):
    for fmt in ("1qb_ppr", "sf_tep"):
        seed = server.g_universal_by_format[fmt]["seed"]   # this test's own dict
        for pid, (_, _, elo) in EXTRA.items():
            seed[pid] = elo
    with db_module.engine.begin() as conn:
        for pid, (name, pos, _) in EXTRA.items():
            conn.execute(insert(db_module.players_table).values(
                player_id=pid, full_name=name, position=pos, search_rank=10))
    yield world


def _verdict(favors, firsts, label=None):
    """A verdict as `_value_bar_from_snapshot` builds one."""
    return {"favors": favors,
            "gap": {"firsts": firsts,
                    "pick_equivalent": {"label": label} if label else None},
            "second_in_firsts": SECOND_IN_FIRSTS}


def _fit(firsts):
    """The real pick fit for a gap of `firsts` Mid 1sts: (snapshot firsts,
    label or None), exactly what the mint stores."""
    eq = server._pick_gap_equivalent(firsts * MID_1ST)
    pick = eq["pick_equivalent"]
    return eq["firsts"], (pick["label"] if pick else None)


def _text(verdict):
    return "".join(og_image.value_bar_label(verdict))


def _alt(verdict):
    return og_image.value_bar_alt(verdict, AS_OF, "1qb_ppr")


_FONTS = {}


def _cached_font(size, bold=False):
    if (size, bold) not in _FONTS:
        _FONTS[size, bold] = _REAL_LOAD_FONT(size, bold)
    return _FONTS[size, bold]


_REAL_LOAD_FONT = og_image._load_font


def _draw_bar(verdict):
    """Draw just the value bar for `verdict` under the draw spy, on a plain
    card-sized canvas with the fonts loaded once (speed only); returns
    (label line text, track fills)."""
    import unittest.mock as mock
    calls = []
    cls = og_image.ImageDraw.ImageDraw

    def spy(name):
        real = getattr(cls, name)

        def wrapper(self, *a, **kw):
            calls.append((name, a, kw))
            return real(self, *a, **kw)
        return wrapper
    img = og_image.Image.new("RGB", (og_image.CARD_W, og_image.CARD_H))
    with mock.patch.object(og_image, "_load_font", _cached_font), \
         mock.patch.object(cls, "text", spy("text")), \
         mock.patch.object(cls, "rounded_rectangle", spy("rounded_rectangle")), \
         mock.patch.object(cls, "rectangle", spy("rectangle")):
        draw = og_image.ImageDraw.Draw(img)
        og_image._draw_value_bar(draw, verdict, AS_OF, "1qb_ppr", SECOND_IN_FIRSTS)
    label = "".join(t for t, _ in _label_runs(calls))
    return label, _track_fills(calls)


SWEEP = [round(i * 0.01, 2) for i in range(301)]          # 0.00 .. 3.00 firsts


# ---------------------------------------------------------------------------
# 1-3. B1, B2, B3
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("favors", ["give", "receive"])
@pytest.mark.parametrize("firsts, short", [
    (0.06, "a Late 4th"), (0.29, "a Mid 2nd"), (0.7, "a Late 1st"),
    (1.0, "a Mid 1st"), (1.3, "an Early 1st"), (1.77, "an Early 1st")])
def test_b1_a_pick_that_fits_is_the_label_whatever_the_gap(favors, firsts, short):
    snap_firsts, label = _fit(firsts)
    v = _verdict(favors, snap_firsts, label)
    assert og_image.value_bar_branch(v) == og_image.VB_B1
    assert _text(v) == f"≈ {short} in value"
    assert "Mid 1sts" not in _text(v) and ABOUT_EVEN not in _text(v)


def test_b1_at_over_one_first_on_the_card(b2world):
    """A 1.3-first lean that a pick still fits reads the pick, not "≈ 1.3
    Mid 1sts", and leans (clamped) toward YOU GET."""
    tok = _share(b2world, *GAP_OVER_1ST)
    snap = json.loads(_token_snapshot(tok))
    assert (snap["favors"], snap["label"]) == ("receive", "Early 1st Round Pick")
    assert 1.0 < snap["firsts"] < 1.5, snap["firsts"]   # ~1.3 (market stud tax)
    _, calls = _spied(b2world, f"/og/trade/{tok}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == "≈ an Early 1st in value"
    assert _track_fills(calls) == [([600, 452, 1140, 470], og_image.SEMANTIC_POS)]
    page = b2world.get(f"/s/trade/{tok}").get_data(as_text=True)
    assert _meta(page, "property", "og:image:alt").startswith(
        "Trade card: the give/get breakdown and a value bar leaning to the get side, "
        "≈ an Early 1st in value.")


@pytest.mark.parametrize("favors", ["give", "receive"])
@pytest.mark.parametrize("firsts, text", [
    (1.0, "≈ 1.0 Mid 1sts in value"), (1.4, "≈ 1.4 Mid 1sts in value"),
    (2.5, "≈ 2.5 Mid 1sts in value"), (4.9, "≈ 4.9 Mid 1sts in value"),
    (0.99, ABOUT_EVEN), (0.4, ABOUT_EVEN), (0.06, ABOUT_EVEN), (0.0, ABOUT_EVEN)])
def test_b2_only_at_one_first_or_more_with_no_pick(favors, firsts, text):
    v = _verdict(favors, firsts)
    assert _text(v) == text
    assert (og_image.value_bar_branch(v) == og_image.VB_B2) == (firsts >= 1.0)


def test_b2_sweep_no_pick_reads_mid_1sts_exactly_from_one_first():
    for f in SWEEP:
        for favors in ("give", "receive"):
            text = _text(_verdict(favors, f))
            assert ("Mid 1sts" in text) == (f >= 1.0), (favors, f, text)


def test_b3_below_one_first_with_no_pick_draws_the_centre_mark(b2world):
    """The real sliver (0.06 firsts, no pick fits, `favors` leans): "About
    even in value", the ice nub and no lean rectangle, "about even" alt."""
    tok = _share(b2world, *SLIVER)
    snap = json.loads(_token_snapshot(tok))
    assert (snap["favors"], snap["firsts"], snap["label"]) == ("receive", 0.06, None)
    _, calls = _spied(b2world, f"/og/trade/{tok}.png")
    runs = _label_runs(calls)
    assert "".join(t for t, _ in runs) == ABOUT_EVEN
    assert {fill for _, fill in runs} == {og_image.VB_CHALK}
    assert _track_fills(calls) == [NUB]
    assert not any(name == "rounded_rectangle" and kw.get("fill") in LEANS
                   for name, _, kw in calls)
    page = b2world.get(f"/s/trade/{tok}").get_data(as_text=True)
    alt = _meta(page, "property", "og:image:alt")
    assert alt == ("Trade card: the give/get breakdown and a value bar, about even "
                   f"in value. Estimate from consensus dynasty values, 1QB PPR, {AS_OF}.")


@pytest.mark.parametrize("favors", ["give", "receive"])
def test_b3_a_four_tenths_gap_with_no_pick_is_about_even_not_mid_1sts(favors):
    """The "≈ 0.4 Mid 1sts" case (a snapshot only a synthetic gap reaches):
    About even, the nub, the even alt."""
    v = _verdict(favors, 0.4)
    assert _draw_bar(v) == (ABOUT_EVEN, [NUB])
    assert "about even in value" in _alt(v) and "leaning" not in _alt(v)


# ---------------------------------------------------------------------------
# 4-5. Legal's two conditions, as properties
# ---------------------------------------------------------------------------

def test_legal_condition_1_about_even_never_covers_a_gap_a_pick_fits():
    """Every gap 0-3 firsts (0.01 steps) the real fit gives a pick to, with
    `favors` leaning, reads B1 through the snapshot reader, the label and
    the alt text: never "About even"."""
    fitted, over_one = 0, 0
    for f in SWEEP:
        snap_firsts, label = _fit(f)
        if label is None:
            continue
        for favors in ("give", "receive"):
            raw = json.dumps({
                "v": 1, "favors": favors, "firsts": snap_firsts, "label": label,
                "format": "1qb_ppr", "league_id": None,
                "computed_at": "2026-11-14T02:30:00+00:00",
                "second_in_firsts": SECOND_IN_FIRSTS,
                "pool": {"snapshot": "vsn1:x", "version": "evaluate-mode-a/x/x"}})
            v = server._value_bar_from_snapshot(raw)["verdict"]
            assert og_image.value_bar_branch(v) == og_image.VB_B1, (f, favors)
            assert _text(v) == f"≈ {og_image._short_pick(label)} in value", (f, favors)
            assert ABOUT_EVEN not in _text(v)
            assert "about even" not in _alt(v).lower(), (f, favors, _alt(v))
        fitted += 1
        over_one += f >= 1.0
    # The sweep really covers the fit, including past one Mid 1st.
    assert fitted > 150 and over_one > 50, (fitted, over_one)


def test_legal_condition_2_about_even_always_draws_the_centre_mark():
    """Every verdict across `favors` (give, receive, even, missing) x gaps
    0-3 firsts x (the real pick fit, no pick): when the drawn label is
    "About even" the only track fill is the ice nub and the alt reads about
    even; otherwise it is one lean, never the nub."""
    seen = set()
    for f in SWEEP[::5]:
        snap_firsts, label = _fit(f)
        for favors in ("give", "receive", "even", None):
            for lab in {label, None}:
                v = _verdict(favors, snap_firsts, lab)
                text, fills = _draw_bar(v)
                alt = _alt(v)
                if text == ABOUT_EVEN:
                    assert fills == [NUB], (favors, f, lab, fills)
                    assert "about even in value" in alt and "leaning" not in alt
                    seen.add("even")
                else:
                    assert len(fills) == 1 and fills[0][1] in LEANS, (favors, f, lab, fills)
                    assert ABOUT_EVEN not in text and "leaning" in alt
                    seen.add("lean")
    assert seen == {"even", "lean"}


# ---------------------------------------------------------------------------
# 6. The open question: `favors` even AND a pick label
# ---------------------------------------------------------------------------

def test_open_question_even_band_with_a_pick_keeps_todays_about_even_and_centre_mark(world):
    """NOT a ruling. Condition 1 would show the pick (B1); models-lead M7
    gives the even band only the centre mark; the snapshot stores no lean
    direction for an even trade. Until that is decided the card keeps the
    behaviour from before the rule. #564's EVEN pair is the real case: point
    ratio 0.951 (favors even), and its 0.13-first gap fits a Mid 4th. When
    the question is settled, this test changes on purpose."""
    tok = _share(world, *EVEN)
    snap = json.loads(_token_snapshot(tok))
    assert (snap["favors"], snap["firsts"], snap["label"]) == (
        "even", 0.13, "Mid 4th Round Pick")
    v = server._value_bar_from_snapshot(_token_snapshot(tok))["verdict"]
    assert og_image.value_bar_branch(v) == og_image.VB_OPEN_EVEN_BAND_WITH_PICK
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    assert "".join(t for t, _ in _label_runs(calls)) == ABOUT_EVEN
    assert _track_fills(calls) == [NUB]
    for label in ("Late 4th Round Pick", "Late 3rd Round Pick", "Mid 2nd Round Pick",
                  "Early 1st Round Pick"):
        for favors in ("even", None):
            v = _verdict(favors, 0.5, label)
            assert og_image.value_bar_branch(v) == og_image.VB_OPEN_EVEN_BAND_WITH_PICK
            assert _draw_bar(v) == (ABOUT_EVEN, [NUB])
            assert "about even in value" in _alt(v)


# ---------------------------------------------------------------------------
# 7. Parity with the app (#567 @ 955f83c3, mobile/tests/check-value-bar-b2.js)
# ---------------------------------------------------------------------------

MID_2ND_LABEL = "Mid 2nd Round Pick"
APP_B2_CASES = [
    # (app case, favors, signed gap.firsts, pick label, app `even`, card label)
    ("a 40-point lean with no pick label reads Even",
     "receive", 0.02, None, True, ABOUT_EVEN),
    ("a negative lean under 1 first with no pick label reads Even",
     "give", -0.4, None, True, ABOUT_EVEN),
    ("exactly 1 first with no pick label leans",
     "receive", 1.0, None, False, "≈ 1.0 Mid 1sts in value"),
    ("1.4 firsts with no pick label leans",
     "give", -1.4, None, False, "≈ 1.4 Mid 1sts in value"),
    ("a lean with a pick label leans (a Mid 2nd)",
     "receive", 0.29, MID_2ND_LABEL, False, "≈ a Mid 2nd in value"),
    ("a small lean WITH a pick label still leans",
     "give", -0.06, MID_2ND_LABEL, False, "≈ a Mid 2nd in value"),
    ("favors 'even' reads Even", "even", 0.1, MID_2ND_LABEL, True, ABOUT_EVEN),
    ("favors null reads Even", None, 0.0, None, True, ABOUT_EVEN),
]


@pytest.mark.parametrize("case, favors, signed, label, app_even, text",
                         APP_B2_CASES, ids=[c[0] for c in APP_B2_CASES])
def test_the_card_matches_the_app_b2_guard(case, favors, signed, label, app_even, text):
    """The sign is the direction: + leans toward YOU GET (favors receive,
    green, right of centre), - toward YOU GIVE (favors give, amber, left).
    The snapshot stores abs(firsts) with that `favors`."""
    firsts = abs(signed)
    v = _verdict(favors, firsts, label)
    assert og_image.value_bar_is_even(v) is app_even
    drawn, fills = _draw_bar(v)
    assert drawn == text
    if app_even:
        assert fills == [NUB]
    else:
        length = round(min(1.0, firsts) * og_image.VB_HALF)
        want = (([600, 452, 600 + length, 470], og_image.SEMANTIC_POS) if signed > 0
                else ([600 - length, 452, 600, 470], og_image.SEMANTIC_WARN))
        assert fills == [want]


# ---------------------------------------------------------------------------
# 8. Legal (f): a traded owned pick never names where it came from
# ---------------------------------------------------------------------------

def test_legal_f_a_traded_owned_pick_reads_2026_1st_with_no_from(world, monkeypatch):
    """A real draft_picks row, traded (is_traded=1) with an original_username:
    the app's own label for it carries "(from ...)"; the card and its share
    page never do, and never the username."""
    row = {"pick_id": TRADED_PICK, "league_id": LEAGUE, "season": 2026, "round": 1,
           "owner_user_id": USER_A, "owner_username": "sharer",
           "original_roster_id": "5", "original_user_id": USER_B,
           "original_username": TRADED_FROM, "is_traded": 1,
           "pick_value": 80.0, "pool_value": 3000.0, "platform": "sleeper"}
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.draft_picks_table).values(**row))
    # The real loader, not #564's stub, so the mint prices the row itself.
    monkeypatch.setattr(server, "load_draft_picks", db_module.load_draft_picks)
    (loaded,) = [p for p in db_module.load_draft_picks(league_id=LEAGUE)
                 if p["pick_id"] == TRADED_PICK]
    assert server._owned_pick_label(loaded) == f"2026 1st (from {TRADED_FROM})"

    tok = _share(world, [TRADED_PICK], ["vb_wr1"])
    assert _token_snapshot(tok) is not None            # priced at mint: the bar draws
    _, calls = _spied(world, f"/og/trade/{tok}.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "2026 1st" in drawn
    assert not any("(from" in t or TRADED_FROM in t for t in drawn), drawn
    assert _has_track(calls)
    page = world.get(f"/s/trade/{tok}").get_data(as_text=True)
    assert "(from" not in page and TRADED_FROM not in page
