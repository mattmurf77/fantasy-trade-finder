"""#372 — the COMPOSITE window model (starter dynasty value + playoff
likelihood + down-weighted age).

Scope: `docs/feedback/items/372-window-composite/scope.md`. Decision D-140.

WHAT THIS FILE IS GUARDING, because it is not the arithmetic.

`infer_team_outlook` is not a Team Review function. Its verdict feeds
`outlook_alpha`, which the trade engine (`trade_gen_v2.py:986`,
`trade_service.py:4250`), the mock draft (`server.py:14013`) and the outlook
seed (`server.py:5320`) all consume, so **changing its score changes every deck
for every user**. #372 does not add a term — it RE-WEIGHTS THE WHOLE VECTOR,
which is a bigger blast radius than #365's, so the load-bearing tests are again
the ones that pin what happens when the flag is NOT on:

  INV-372   flag OFF ⇒ the two new kwargs are accepted and IGNORED. The whole
            returned tuple — outlook, score, every key of `signals`, every key
            of `signals["model"]` — equals what `origin/main` (c00a9a6)
            returned. The goldens below were CAPTURED BY RUNNING THESE EXACT
            FIXTURES against a `git archive c00a9a6` tree, not re-derived from
            the formula this module now contains, which would prove nothing.
  INV-372b  flag ON but no APPLIED starter signal ⇒ the LEGACY vector still
            scores. This is what makes "lighting the flag moves the window beat
            and not one deck" a fact: the three generation callers pass four
            positional arguments and cannot supply a starter signal, because
            starter value can only be summed off a league-wide power-rankings
            call that no generation path makes.

The rest of the file is the model itself: that age really did get lighter (by
exactly the ratio the operator asked for, not approximately), that each signal
degrades on its own with a named reason rather than scoring an absent term as
a neutral zero, and that a term which scores is a term the payload carries.
"""

from __future__ import annotations

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.team_review import (
    _window,
    resolve_window_from_odds,
    resolve_window_precedence,
)
from backend.trade_service import (
    infer_team_outlook,
    playoff_odds_signal,
    starter_value_signal,
)


@pytest.fixture(autouse=True)
def _isolate():
    """Flags + `_cfg` snapshot-restored, per `backend/tests/CLAUDE.md` §3/§4."""
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _composite_on():
    _set_flags(**{"trade.outlook_composite": True})


class P:
    def __init__(self, pid, position="RB", age=24, search_rank=50):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = age
        self.search_rank = search_rank
        self.pick_value = None


def _vets():
    return {"a": P("a", "RB", 29, 3), "b": P("b", "WR", 30, 8),
            "c": P("c", "QB", 28, 15), "d": P("d", "WR", 24, 40)}


def _kids():
    return {"a": P("a", "RB", 22, 5), "b": P("b", "WR", 21, 9),
            "c": P("c", "WR", 23, 20), "d": P("d", "RB", 29, 60)}


def _mixed():
    return {"a": P("a", "RB", 26, 5), "b": P("b", "WR", 27, 9),
            "c": P("c", "WR", 25, 20), "d": P("d", "QB", 28, 30)}


# Captured by running these exact fixtures against a `git archive c00a9a6
# backend config` tree — origin/main immediately before #372 — via
# scratchpad/golden_372.py. `model_keys` is pinned as tightly as `score`
# because `window.model` is RENDERED: a key appearing there that the score is
# not applying is the D-101 defect ("age 23 and under" against a youth_age of
# 26) all over again, and a key silently vanishing breaks the card's rows.
GOLDEN = {
    "vets_low_picks": {
        "args": (_vets, 0.03, 12),
        "outlook": "contender",
        "score": 0.740418470159306,
        "vet_share": 0.8168759017463196,
        "youth_share": 0.1831240982536803,
    },
    "kids_pick_hoard": {
        "args": (_kids, 0.18, 12),
        "outlook": "rebuilder",
        "score": -0.8882925160248699,
        "vet_share": 0.15252040865423167,
        "youth_share": 0.8474795913457682,
    },
    "mixed_even_picks": {
        "args": (_mixed, 1 / 12, 12),
        "outlook": "not_sure",
        "score": -0.04194269749818641,
        "vet_share": 0.4790286512509068,
        "youth_share": 0.5209713487490932,
    },
}

GOLDEN_SIGNAL_KEYS = {"model", "pick_share", "score", "vet_share", "youth_share"}
GOLDEN_MODEL_KEYS = {"contender_cut", "rebuilder_cut", "vet_age", "youth_age",
                     "w_pick_share", "w_vet_share", "w_youth_share"}

# Signals LOUD enough to move every golden if they were ever applied: a
# starting lineup 50 % above the league mean (index +0.50, worth +0.30) and a
# 90 % playoff team (index +0.80, worth +0.32).
LOUD_STARTERS = {"starter_value": 300.0, "league_starter_value": 2400.0,
                 "share": 0.125, "index": 0.5, "index_raw": 0.5,
                 "provenance": "observed", "applied": True}
LOUD_ODDS = {"playoff_pct": 0.9, "band": "likely", "index": 0.8,
             "center": 0.5, "provenance": "observed", "applied": True}


# ---------------------------------------------------------------------------
# INV-372 — flag OFF is byte-identical to origin/main, signals or no signals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_off_matches_origin_main_goldens(case):
    g = GOLDEN[case]
    players = g["args"][0]()
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2])
    assert out == g["outlook"]
    assert score == g["score"], "the score MOVED — every deck moved with it"
    assert set(sig) == GOLDEN_SIGNAL_KEYS
    assert set(sig["model"]) == GOLDEN_MODEL_KEYS


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_off_ignores_supplied_composite_signals_entirely(case):
    """A caller that starts passing the new signals early must not move a deck.

    Both kwargs are accepted while the flag is down, and the WHOLE return value
    — including every key of `signals` and of `signals["model"]` — is what it
    was without them.
    """
    g = GOLDEN[case]
    players = g["args"][0]()
    bare = infer_team_outlook(list(players), players, g["args"][1], g["args"][2])
    loud = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2],
        None, LOUD_STARTERS, LOUD_ODDS)
    assert loud == bare
    assert loud[1] == g["score"]
    assert "starters" not in loud[2] and "playoff" not in loud[2]
    assert set(loud[2]["model"]) == GOLDEN_MODEL_KEYS, (
        "window.model advertises terms the score is not applying")
    # The legacy weights, unmoved. `w_vet_share` reading 0.40 while the score
    # used 1.00 would be the same class of defect from the other direction.
    assert loud[2]["model"]["w_vet_share"] == 1.00
    assert loud[2]["model"]["w_youth_share"] == 1.00


def test_flag_off_empty_roster_golden():
    out, score, sig = infer_team_outlook(
        [], {}, 0.0, 12, None, LOUD_STARTERS, LOUD_ODDS)
    assert (out, score) == ("not_sure", 0.0)
    assert set(sig) == GOLDEN_SIGNAL_KEYS


# ---------------------------------------------------------------------------
# INV-372b — flag ON without an APPLIED starter signal still moves nothing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_on_without_a_starter_signal_is_still_the_golden(case):
    """The engine, the mock draft and the outlook seed pass four arguments.

    So lighting `trade.outlook_composite` re-weights the WINDOW BEAT and not
    one deck. This is the test that makes that claim checkable rather than
    hopeful — and it is stricter than #365's sibling, because #372 changes the
    weights on terms those callers DO compute.
    """
    _composite_on()
    g = GOLDEN[case]
    players = g["args"][0]()
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2])
    assert (out, score) == (g["outlook"], g["score"])
    assert set(sig) == GOLDEN_SIGNAL_KEYS
    assert set(sig["model"]) == GOLDEN_MODEL_KEYS


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_on_with_an_UNAPPLIED_starter_signal_is_still_the_golden(case):
    """A league with no lineup template scores the LEGACY vector.

    Halving age without putting starter value in its place is not a model, it
    is a quieter model — every team would drift toward not_sure for a reason
    the user never asked for. So an unapplied starter signal falls all the way
    back, and the payload SAYS SO (`provenance`) instead of hiding it.
    """
    _composite_on()
    g = GOLDEN[case]
    players = g["args"][0]()
    unreadable = starter_value_signal(None, None, 12)
    assert unreadable["applied"] is False
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2], None,
        unreadable, LOUD_ODDS)
    assert (out, score) == (g["outlook"], g["score"])
    assert sig["starters"]["provenance"] == "lineup_unknown"
    # Shown but not scored, and the model block must not claim otherwise.
    assert "w_starter_index" not in sig["model"]
    assert "composite" not in sig["model"]
    assert sig["model"]["w_vet_share"] == 1.00


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_an_unapplied_starter_signal_with_a_LOUD_index_still_scores_nothing(case):
    """The sibling of the playoff test below, and for the same reason.

    `starter_value_signal` zeroes the index whenever it refuses, so a test
    built on its own output cannot distinguish "the guard works" from "the
    number happened to be 0". Hand the function a refused block carrying a
    +0.50 index: only the `applied` check can keep it out.
    """
    _composite_on()
    g = GOLDEN[case]
    players = g["args"][0]()
    loud_but_refused = dict(LOUD_STARTERS, applied=False,
                            provenance="lineup_unknown")
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2], None,
        loud_but_refused, None)
    assert (out, score) == (g["outlook"], g["score"])
    assert sig["starters"]["index"] == 0.5, (
        "the block ships what it was given — only `applied` gates the score")


def test_flag_on_empty_roster_suppresses_every_composite_term():
    """A team whose roster we cannot price has no window. Half a model is not
    an opinion — the same guard #365 put on the firsts term."""
    _composite_on()
    out, score, sig = infer_team_outlook(
        [], {}, 0.0, 12, None, dict(LOUD_STARTERS), dict(LOUD_ODDS))
    assert (out, score) == ("not_sure", 0.0)
    assert sig["starters"]["applied"] is False
    assert sig["playoff"]["applied"] is False


# ---------------------------------------------------------------------------
# The composite itself, once both conditions hold
# ---------------------------------------------------------------------------

def test_the_composite_reweights_rather_than_adding_a_fourth_term():
    """The operator's actual instruction, as arithmetic.

    Not "age plus a starter bonus" — the WHOLE vector changes at once. Pinned
    against a hand-built expectation rather than against the function's own
    output, so a weight drifting in `_DEFAULT_CFG` fails here.
    """
    _composite_on()
    players = _mixed()
    g = GOLDEN["mixed_even_picks"]
    out, score, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None, dict(LOUD_STARTERS), None)
    expected = (0.40 * g["vet_share"] - 0.40 * g["youth_share"]
                - 2.00 * (1 / 12 - 1 / 12) + 0.60 * 0.50)
    assert score == pytest.approx(expected)
    assert out == "contender"
    assert sig["model"]["composite"] is True
    assert sig["model"]["w_vet_share"] == 0.40
    assert sig["model"]["w_youth_share"] == 0.40
    assert sig["model"]["w_starter_index"] == 0.60


def test_age_is_a_lighter_driver_by_exactly_the_ratio_claimed():
    """"The age distribution can stay but make it a lighter driver."

    Both age terms drop to 40 %, and they drop TOGETHER on purpose: `vet_age`
    27 and `youth_age` 26 are ADJACENT, so every aged player is one or the
    other and the pair is close to one rescaled quantity. Halving only one
    would tilt the model, not lighten it.
    """
    _composite_on()
    for case, fixture in (("vets_low_picks", _vets), ("kids_pick_hoard", _kids)):
        players = fixture()
        g = GOLDEN[case]
        legacy_age = 1.00 * g["vet_share"] - 1.00 * g["youth_share"]
        # Neutral starter index and even picks isolate the age contribution.
        flat = dict(LOUD_STARTERS, index=0.0)
        _o, score, _s = infer_team_outlook(
            list(players), players, 1 / 12, 12, None, flat, None)
        assert score == pytest.approx(0.40 * legacy_age), case
        assert abs(score) < abs(legacy_age), case


def test_better_starters_raise_the_score_and_worse_ones_lower_it():
    """Direction, stated as the operator stated it: a team is strong where it
    STARTS, which is exactly what roster age cannot see."""
    _composite_on()
    players = _mixed()

    def at(index):
        return infer_team_outlook(
            list(players), players, 1 / 12, 12, None,
            dict(LOUD_STARTERS, index=index), None)[1]

    assert at(0.5) > at(0.0) > at(-0.5)
    # Magnitude is bounded by the knob, not incidental.
    assert at(0.5) == pytest.approx(at(0.0) + 0.30)
    assert at(-0.5) == pytest.approx(at(0.0) - 0.30)


def test_better_playoff_odds_raise_the_score():
    _composite_on()
    players = _mixed()
    flat = dict(LOUD_STARTERS, index=0.0)

    def at(index):
        return infer_team_outlook(
            list(players), players, 1 / 12, 12, None, flat,
            dict(LOUD_ODDS, index=index))[1]

    assert at(0.8) > at(0.0) > at(-0.8)
    assert at(0.8) == pytest.approx(at(0.0) + 0.32)


def test_a_refused_playoff_term_is_absent_from_the_score_not_a_zero():
    """The operator's degrade-honestly ruling (D-110), one report later.

    A preseason team and a team whose simulated odds are exactly even must not
    score the same by accident — the first has NO playoff term, the second has
    one worth 0. They coincide numerically here, and the difference the payload
    must carry is `provenance`, which is what the card reads.
    """
    _composite_on()
    players = _mixed()
    refused = playoff_odds_signal({"band": "likely", "playoff_pct": 0.9}, "preseason")
    assert refused["applied"] is False
    assert refused["band"] == "likely", (
        "the band must still SHIP when it is refused — the card says what was "
        "available and why it was not used")

    # `applied` IS THE TEST, not `index == 0`. The helper happens to zero the
    # index on refusal, so asserting against the helper's own output would
    # pass even if `infer_team_outlook` scored every signal it was handed —
    # the guard would be untested and the assertion decorative. So hand it a
    # refused block whose index is LOUD: the only thing that can keep it out
    # of the score is the `applied` check.
    loud_but_refused = dict(refused, index=0.8)
    without = infer_team_outlook(
        list(players), players, 1 / 12, 12, None, dict(LOUD_STARTERS), None)[1]
    _o, score, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None, dict(LOUD_STARTERS),
        loud_but_refused)
    assert score == pytest.approx(without), (
        "an unapplied playoff term entered the score — 0.40 × 0.8 of it")
    assert sig["playoff"]["provenance"] == "preseason"
    assert sig["playoff"]["applied"] is False
    assert "w_playoff_index" not in sig["model"], (
        "a weight rendered beside a term that did not score")


def test_a_scored_term_is_always_a_rendered_term():
    """D-101 in one assertion: every weight the score used is in `model`, and
    every weight in `model` was used. The screen once said "age 23 and under"
    against a `youth_age` of 26 — a term the card cannot show is that bug."""
    _composite_on()
    players = _mixed()
    _o, _s, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None,
        dict(LOUD_STARTERS), dict(LOUD_ODDS))
    for key in ("w_vet_share", "w_youth_share", "w_pick_share",
                "w_starter_index", "starter_index_cap", "composite",
                "w_playoff_index", "playoff_center", "playoff_index_cap"):
        assert key in sig["model"], key
    assert sig["model"]["playoff_center"] == sig["playoff"]["center"]


def test_the_cuts_did_not_move():
    """D-140 records that `infer_contender_cut` / `infer_rebuilder_cut` were
    LEFT ALONE — the re-weighting did not require moving them (12 prod leagues
    / 156 teams, scope §7). Moving them later is a headline, not a footnote,
    so it should break a test."""
    assert ts._DEFAULT_CFG["infer_contender_cut"] == 0.08
    assert ts._DEFAULT_CFG["infer_rebuilder_cut"] == -0.08


def test_the_knobs_are_a_rollback_lever_below_the_flag():
    """Both new weights at 0 ⇒ a down-weighted age model, the payload SHAPE
    unchanged. That is the deploy-free lever under the flag itself."""
    _composite_on()
    ts._cfg["infer_composite_w_starter"] = 0.0
    ts._cfg["infer_composite_w_playoff"] = 0.0
    players = _mixed()
    g = GOLDEN["mixed_even_picks"]
    _o, score, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None,
        dict(LOUD_STARTERS), dict(LOUD_ODDS))
    assert score == pytest.approx(0.40 * g["vet_share"] - 0.40 * g["youth_share"])
    assert "starters" in sig and "playoff" in sig
    assert sig["model"]["w_starter_index"] == 0.0


# ---------------------------------------------------------------------------
# starter_value_signal — the provenance matrix
# ---------------------------------------------------------------------------

def test_starter_signal_provenance_matrix():
    _composite_on()
    observed = starter_value_signal(3000.0, 24000.0, 12)
    assert observed["provenance"] == "observed" and observed["applied"] is True
    # 3000/24000 = 0.125 share; ×12 − 1 = +0.50.
    assert observed["share"] == 0.125
    assert observed["index"] == 0.5

    assert starter_value_signal(None, None, 12)["provenance"] == "lineup_unknown"
    assert starter_value_signal(0.0, 0.0, 12)["provenance"] == "absent"
    for bad in (starter_value_signal(None, None, 12),
                starter_value_signal(0.0, 0.0, 12)):
        assert bad["applied"] is False
        assert bad["index"] == 0.0


def test_starter_index_is_league_size_independent():
    """The whole reason the index is `share × num_teams − 1` rather than
    `share − 1/num_teams`: a lineup twice the league mean indexes at +1.00 in
    a 10-team league and in a 14-team league alike, so ONE weight is correct
    everywhere instead of one per league shape."""
    ts._cfg["infer_composite_starter_cap"] = 5.0
    for n in (8, 10, 12, 14):
        sig = starter_value_signal(200.0, 100.0 * n, n)
        assert sig["index"] == pytest.approx(1.0), n


def test_the_starter_cap_binds_so_one_absurd_roster_cannot_swamp_the_model():
    """FFV3's own caller hits this: his starters are 82 % above the league
    mean, which the cap holds at +0.50 (scope §7)."""
    _composite_on()
    # 82 % above the mean in a 12-team league.
    sig = starter_value_signal(1.82, 12.0, 12)
    assert sig["index"] == 0.5
    assert ts._DEFAULT_CFG["infer_composite_starter_cap"] == 0.50


def test_the_signal_ships_the_MEASURED_index_as_well_as_the_scored_one():
    """The cap binds on real rosters, so `index` alone is not a fact about the
    team — it is a fact about the model. A card printing only `index` would
    tell the FFV3 caller his starters are 50 % above average when they are
    82 % above, which is the same class of lie as "age 23 and under" against a
    `youth_age` of 26 (D-101). Both numbers ship; the card shows the
    measurement and names the cap when they differ."""
    _composite_on()
    sig = starter_value_signal(1.82, 12.0, 12)
    assert sig["index_raw"] == pytest.approx(0.82, abs=1e-4)
    assert sig["index"] == 0.5
    assert sig["index_raw"] != sig["index"], "the cap bound and nothing said so"
    # Uncapped teams report the same number twice — the card then says nothing
    # about a cap, which is correct.
    mild = starter_value_signal(1.2, 12.0, 12)
    assert mild["index_raw"] == mild["index"] == pytest.approx(0.2)
    # The SCORE uses the capped value, never the measurement.
    players = _mixed()
    base = infer_team_outlook(
        list(players), players, 1 / 12, 12, None,
        dict(LOUD_STARTERS, index=0.0, index_raw=0.0), None)[1]
    capped = infer_team_outlook(
        list(players), players, 1 / 12, 12, None, dict(sig), None)[1]
    assert capped == pytest.approx(base + 0.60 * 0.5), (
        "the score used index_raw — the cap is not a display concern")


def test_starter_signal_is_unapplied_while_the_flag_is_down():
    """`applied` is the flag's footprint on the block itself, so a caller that
    builds the signal early cannot accidentally score it."""
    assert starter_value_signal(3000.0, 24000.0, 12)["applied"] is False


# ---------------------------------------------------------------------------
# playoff_odds_signal — the provenance matrix, incl. the fourth value
# ---------------------------------------------------------------------------

def test_playoff_signal_indexes_off_the_tossup_midpoint():
    """The centre is NOT invented here: 0.50 is the midpoint of the `tossup`
    band (`playoff_band`: likely >= 0.65, unlikely < 0.35), so the neutral
    point of this term is the neutral point of the map every client renders.
    ±0.30 at the band edges is what makes the weight legible."""
    _composite_on()
    from backend.outlook.trade_delta import playoff_band
    edge_up = playoff_odds_signal({"band": playoff_band(0.65), "playoff_pct": 0.65}, None)
    edge_down = playoff_odds_signal({"band": playoff_band(0.35), "playoff_pct": 0.35}, None)
    even = playoff_odds_signal({"band": playoff_band(0.50), "playoff_pct": 0.50}, None)
    assert edge_up["band"] == "likely" and edge_down["band"] == "tossup"
    assert edge_up["index"] == pytest.approx(0.30)
    assert edge_down["index"] == pytest.approx(-0.30)
    assert even["index"] == pytest.approx(0.0)
    assert even["provenance"] == "observed", (
        "an exactly even team WAS read — that is different from not reading it")
    # 0.40 × 0.30 = 0.12, which clears the 0.08 contender cut on its own.
    assert 0.40 * edge_up["index"] > ts._DEFAULT_CFG["infer_contender_cut"]


def test_playoff_signal_provenance_matrix():
    _composite_on()
    assert playoff_odds_signal(None, None)["provenance"] == "odds_unavailable"
    assert playoff_odds_signal(None, "odds_disabled")["provenance"] == "odds_disabled"
    band = {"band": "likely", "playoff_pct": 0.9}
    assert playoff_odds_signal(band, "preseason")["provenance"] == "preseason"
    assert playoff_odds_signal(band, None)["provenance"] == "observed"
    for refused in (playoff_odds_signal(None, None),
                    playoff_odds_signal(None, "odds_disabled"),
                    playoff_odds_signal(band, "preseason")):
        assert refused["applied"] is False
        assert refused["index"] == 0.0


def test_odds_disabled_is_not_odds_unavailable():
    """"We did not ask" and "we asked and got nothing" are different claims and
    the card says which. Distinct strings, deliberately — and the new one must
    NOT leak into #371's `window.odds_reason` vocabulary."""
    _composite_on()
    from backend.team_review import WINDOW_FROM_BAND
    disabled = playoff_odds_signal(None, "odds_disabled")
    assert disabled["provenance"] == "odds_disabled"
    assert disabled["provenance"] not in {
        r for r in (resolve_window_from_odds(None, 0)[2],
                    resolve_window_from_odds({"band": "likely"}, 0)[2])}
    assert set(WINDOW_FROM_BAND) == {"likely", "tossup", "unlikely"}


# ---------------------------------------------------------------------------
# Precedence — the band drives ONCE or not at all
# ---------------------------------------------------------------------------

def test_composite_suppresses_the_band_replacement():
    """Both flags on: the band is already a weighted term, so letting it ALSO
    overwrite the verdict would count one simulation twice."""
    source, inferred = resolve_window_precedence(True, "odds", "contender", "rebuilder")
    assert (source, inferred) == ("composite", "rebuilder"), (
        "the odds replaced a verdict they had already been scored into")


def test_without_the_composite_371_is_untouched():
    assert resolve_window_precedence(False, "odds", "contender", "rebuilder") \
        == ("odds", "contender")
    assert resolve_window_precedence(False, "roster", None, "rebuilder") \
        == ("roster", "rebuilder")
    # #371's flag off ⇒ source stays None, which is what keeps `window`
    # key-for-key identical for a client on an older build.
    assert resolve_window_precedence(False, None, None, "rebuilder") \
        == (None, "rebuilder")


def test_composite_source_ships_even_when_the_odds_flag_is_off():
    """The card has to know the composite ran — it renders different weights
    and different copy — so `source` appears on the composite's own account."""
    assert resolve_window_precedence(True, None, None, "contender") \
        == ("composite", "contender")


# ---------------------------------------------------------------------------
# `_window` — passthrough, never re-derivation
# ---------------------------------------------------------------------------

def test_window_passes_both_signal_blocks_through_whole():
    _composite_on()
    players = _mixed()
    _o, _s, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None,
        dict(LOUD_STARTERS), dict(LOUD_ODDS))
    out = _window("contender", sig, None, 12, source="composite",
                  roster_inferred="contender", odds=None, odds_reason=None)
    assert out["signals"]["starters"] == sig["starters"]
    assert out["signals"]["playoff"] == sig["playoff"]
    assert out["model"]["w_starter_index"] == 0.60
    assert out["source"] == "composite"


def test_window_omits_the_blocks_entirely_while_the_flag_is_off():
    """A client on an older build must see the payload it already parses —
    not two keys it will not read."""
    players = _mixed()
    _o, _s, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, None, LOUD_STARTERS, LOUD_ODDS)
    out = _window("not_sure", sig, None, 12)
    assert "starters" not in out["signals"]
    assert "playoff" not in out["signals"]
    assert "source" not in out
    assert set(out["model"]) == GOLDEN_MODEL_KEYS
