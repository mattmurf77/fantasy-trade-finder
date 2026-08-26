"""#365 net first-round capital + #371 playoff-odds window.

Scope: `docs/feedback/items/365-window-signals/scope.md`. Decisions D-110/D-111.

WHAT THIS FILE IS ACTUALLY GUARDING, because it is not the arithmetic.

`infer_team_outlook` is not a Team Review function. Its verdict feeds
`outlook_alpha`, which the trade engine (`trade_gen_v2.py:986`,
`trade_service.py:4250`), the mock draft (`server.py:14013`) and the outlook
seed (`server.py:5320`) all consume, so **changing its score changes every deck
for every user**. The net-firsts term therefore ships behind
`trade.outlook_net_firsts`, and the load-bearing tests here are the two that
pin what happens when it is NOT on:

  INV-365   flag OFF ⇒ the new `first_round_ledger` kwarg is accepted and
            ignored, and the returned tuple equals what `origin/main` returned.
            Proved against goldens CAPTURED FROM `bc43b6f` — code that had
            never heard of the kwarg — not against a re-derivation of the same
            formula this module now contains, which would prove nothing.
  INV-365b  flag ON but no ledger ⇒ the score is STILL unchanged, because the
            term needs a ledger and only the Team Review route builds one.
            This is what makes "lighting the flag moves the window beat and not
            one deck" a fact rather than a hope.

The #371 half changes no engine value at all: it composes in the route, after
the heuristic has already run, and the heuristic's verdict always survives in
`window.roster_inferred`.
"""

from __future__ import annotations

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.team_review import (
    WINDOW_FROM_BAND,
    build_team_review,
    resolve_window_from_odds,
)
from backend.trade_service import first_round_signal, infer_team_outlook


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


# Captured by running these exact fixtures against `git archive bc43b6f
# backend` — the tree immediately before #365 — via
# scratchpad/gen_golden.py. If a future change moves one of these numbers it
# has changed every deck in production, and that is the alarm.
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

# A ledger that WOULD move every one of the goldens if it were ever applied:
# three firsts shipped out of four, i.e. net_share −0.75, worth +0.075.
LOUD_LEDGER = {"held": 1, "own_total": 4, "traded_away": 3, "acquired": 0,
               "league_any_traded": True}


# ---------------------------------------------------------------------------
# INV-365 — flag OFF is byte-identical to origin/main, ledger or no ledger
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_off_matches_origin_main_goldens(case):
    g = GOLDEN[case]
    players = g["args"][0]()
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2])
    assert out == g["outlook"]
    assert score == g["score"], "the score MOVED — every deck moved with it"
    assert sig["vet_share"] == g["vet_share"]
    assert sig["youth_share"] == g["youth_share"]


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_off_ignores_a_supplied_ledger_entirely(case):
    """A caller that starts passing a ledger early must not move a deck.

    The kwarg is accepted while the flag is down, and the WHOLE return value —
    including every key of `signals` — is what it was without it.
    """
    g = GOLDEN[case]
    players = g["args"][0]()
    bare = infer_team_outlook(list(players), players, g["args"][1], g["args"][2])
    with_ledger = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2], LOUD_LEDGER)
    assert with_ledger == bare
    assert with_ledger[1] == g["score"]
    assert "firsts" not in with_ledger[2]
    assert "w_net_firsts" not in with_ledger[2]["model"], (
        "window.model advertises a term the score is not applying")


def test_flag_off_empty_roster_golden():
    out, score, sig = infer_team_outlook([], {}, 0.0, 12, LOUD_LEDGER)
    assert (out, score) == ("not_sure", 0.0)
    assert sig["vet_share"] == 0.0 and sig["youth_share"] == 0.0
    assert "firsts" not in sig


# ---------------------------------------------------------------------------
# INV-365b — flag ON without a ledger still moves nothing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_flag_on_without_a_ledger_is_still_the_golden(case):
    """The engine, the mock draft and the outlook seed pass four arguments.

    So lighting `trade.outlook_net_firsts` changes the WINDOW BEAT and not one
    deck: deck movement needs a second, deliberate change to those callers.
    """
    _set_flags(**{"trade.outlook_net_firsts": True})
    g = GOLDEN[case]
    players = g["args"][0]()
    out, score, sig = infer_team_outlook(
        list(players), players, g["args"][1], g["args"][2])
    assert (out, score) == (g["outlook"], g["score"])
    assert "firsts" not in sig
    assert "w_net_firsts" not in sig["model"]


# ---------------------------------------------------------------------------
# The term itself, once both conditions hold
# ---------------------------------------------------------------------------

def test_selling_firsts_raises_the_score_and_hoarding_lowers_it():
    """Direction, stated as the operator stated it: a manager who has shipped
    his firsts has declared a window in a way no birthday can."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    players = _mixed()
    base = infer_team_outlook(list(players), players, 1 / 12, 12)[1]
    sold = infer_team_outlook(list(players), players, 1 / 12, 12, {
        "held": 1, "own_total": 4, "traded_away": 3, "acquired": 0,
        "league_any_traded": True})[1]
    hoarded = infer_team_outlook(list(players), players, 1 / 12, 12, {
        "held": 7, "own_total": 4, "traded_away": 0, "acquired": 3,
        "league_any_traded": True})[1]
    assert sold > base > hoarded
    # Magnitude is bounded by the knob, not incidental: ±0.075 at net ∓0.75.
    assert sold == pytest.approx(base + 0.075)
    assert hoarded == pytest.approx(base - 0.075)


def test_the_term_can_move_one_bucket_and_never_two():
    """`infer_w_net_firsts` is 0.10 against a not_sure band of ±0.08, so an
    extreme ledger can lift a mild rebuilder to not_sure and can NEVER lift a
    committed rebuilder to contender. That bound is the whole reason the cuts
    were left where they are (scope §7.1)."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    kids = _kids()
    out, score, _ = infer_team_outlook(list(kids), kids, 0.18, 12, LOUD_LEDGER)
    assert score == pytest.approx(GOLDEN["kids_pick_hoard"]["score"] + 0.075)
    assert out == "rebuilder", (
        "a −0.89 roster must stay a rebuilder no matter what the picks say")


def test_net_firsts_is_acquired_minus_traded_away():
    sig = first_round_signal({"held": 5, "own_total": 4, "traded_away": 1,
                              "acquired": 2, "league_any_traded": True})
    assert sig["net"] == 1
    assert sig["net_share"] == pytest.approx(0.25)
    assert sig["provenance"] == "observed"


def test_net_share_is_clamped_by_the_knob():
    """A team that shipped more firsts than it originally owned cannot produce
    an unbounded term."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    ts._cfg["infer_net_firsts_cap"] = 0.5
    sig = first_round_signal({"held": 0, "own_total": 2, "traded_away": 6,
                              "acquired": 0, "league_any_traded": True})
    assert sig["net"] == -6
    assert sig["net_share"] == -0.5, "raw −3.0 must clamp to the cap"


def test_zero_weight_neutralises_the_term_without_changing_the_payload():
    """The deploy-free softer lever: keep the card showing the ledger, stop it
    scoring. Named in the scope as the ship-the-knob rollback."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    ts._cfg["infer_w_net_firsts"] = 0.0
    players = _mixed()
    _o, score, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, LOUD_LEDGER)
    assert score == pytest.approx(GOLDEN["mixed_even_picks"]["score"])
    assert sig["firsts"]["applied"] is True, (
        "the ledger is still SHOWN and still labelled applied — only its "
        "weight is zero; hiding it would make the zero unexplainable")


# ---------------------------------------------------------------------------
# Provenance — the honesty gate (operator decision 3)
# ---------------------------------------------------------------------------

def test_a_league_with_no_recorded_trades_is_none_traded_not_a_confident_zero():
    """The whole point. A league synced before pick provenance was captured
    looks exactly like a league where nobody traded a first, so we refuse to
    score it and label which world we might be in."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    sig = first_round_signal({"held": 4, "own_total": 4, "traded_away": 0,
                              "acquired": 0, "league_any_traded": False})
    assert sig["provenance"] == "none_traded"
    assert sig["applied"] is False
    assert sig["net_share"] == 0.0


def test_none_traded_contributes_nothing_to_the_score():
    _set_flags(**{"trade.outlook_net_firsts": True})
    players = _mixed()
    _o, score, sig = infer_team_outlook(list(players), players, 1 / 12, 12, {
        "held": 4, "own_total": 4, "traded_away": 0, "acquired": 0,
        "league_any_traded": False})
    assert score == pytest.approx(GOLDEN["mixed_even_picks"]["score"])
    assert sig["firsts"]["provenance"] == "none_traded"


def test_a_league_with_no_pick_rows_at_all_is_absent():
    _set_flags(**{"trade.outlook_net_firsts": True})
    sig = first_round_signal({"held": 0, "own_total": 0, "traded_away": 0,
                              "acquired": 0, "league_any_traded": False})
    assert sig["provenance"] == "absent" and sig["applied"] is False
    assert first_round_signal(None)["provenance"] == "absent"
    assert first_round_signal({})["provenance"] == "absent"


def test_empty_roster_never_reports_an_applied_term():
    """No readable roster ⇒ no window. Half a model is not an opinion, and the
    early return must not leave `applied` claiming otherwise."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    out, score, sig = infer_team_outlook([], {}, 0.0, 12, LOUD_LEDGER)
    assert (out, score) == ("not_sure", 0.0)
    assert sig["firsts"]["applied"] is False


def test_model_carries_the_new_knobs_whenever_the_term_is_live():
    """D-101 generalised: a term the score applies is a term the card renders,
    and the card can only render what `window.model` carries."""
    _set_flags(**{"trade.outlook_net_firsts": True})
    players = _mixed()
    _o, _s, sig = infer_team_outlook(
        list(players), players, 1 / 12, 12, LOUD_LEDGER)
    assert sig["model"]["w_net_firsts"] == 0.10
    assert sig["model"]["net_firsts_cap"] == 1.00
    assert sig["firsts"]["applied"] is True


# ---------------------------------------------------------------------------
# The window beat's payload — #365 passthrough and #371 shape
# ---------------------------------------------------------------------------

def _review(**over):
    base = dict(
        teams=[{"user_id": f"u{i}", "username": f"t{i}", "value": 1000.0 - i,
                "roster": []} for i in range(1, 5)],
        you_user_id="u1",
        num_teams=4,
        scoring_format="1qb_ppr",
        completed_weeks=0,
        scoring=None,
        scoring_unavailable_reason="preseason",
        inferred_outlook="contender",
        outlook_signals={"vet_share": 0.61, "youth_share": 0.12,
                         "pick_share": 0.05, "score": 0.31},
        stored_prefs={},
        roster_profile={},
        member_profiles={},
        member_windows={},
        weakest_slot=None,
        user_elo=None,
        board_interactions=0,
        judged_ids=set(),
        seed_elo={},
        community_gap=None,
        user_roster=[],
        players={},
    )
    base.update(over)
    return build_team_review(**base)


def test_window_is_shape_identical_when_both_flags_are_off():
    """Flag-off `window` carries none of the six new keys. A shipped client
    parsing today's payload must see today's payload."""
    w = _review()["window"]
    assert set(w) == {"inferred", "declared", "signals", "model", "options"}
    assert set(w["signals"]) == {"vet_share", "youth_share", "pick_share",
                                 "equal_pick_share", "score"}


def test_window_passes_the_firsts_ledger_through_untouched():
    ledger = {"held": 1, "own_total": 4, "traded_away": 3, "acquired": 0,
              "net": -3, "net_share": -0.75, "provenance": "observed",
              "applied": True}
    w = _review(outlook_signals={"vet_share": 0.5, "youth_share": 0.2,
                                 "pick_share": 0.08, "score": 0.1,
                                 "firsts": ledger})["window"]
    assert w["signals"]["firsts"] == ledger


def test_window_reports_which_model_drove_and_keeps_the_other_one():
    """#371's contract in one assertion: both definitions of 'contender' ship,
    so the client can say which one it is showing."""
    w = _review(inferred_outlook="rebuilder", window_source="odds",
                window_roster_inferred="contender",
                window_odds={"band": "unlikely", "playoff_pct": 0.12,
                             "implied": "rebuilder"})["window"]
    assert w["inferred"] == "rebuilder"
    assert w["source"] == "odds"
    assert w["roster_inferred"] == "contender", (
        "the heuristic's verdict must survive the odds overriding it")
    assert w["odds"]["implied"] == "rebuilder"
    assert w["odds_reason"] is None


def test_window_names_the_reason_when_the_odds_did_not_drive():
    w = _review(window_source="roster", window_roster_inferred="contender",
                window_odds={"band": "likely", "playoff_pct": 0.8,
                             "implied": "contender"},
                window_odds_reason="preseason")["window"]
    assert w["source"] == "roster"
    assert w["inferred"] == "contender"
    assert w["odds_reason"] == "preseason"
    assert w["odds"]["band"] == "likely", (
        "the band is SHOWN even when refused — the user is told what was "
        "available and why it was not used")


def test_the_odds_window_also_reorients_the_partners_beat():
    """`build_team_review` derives the partners comparison from the same window,
    so an odds-driven flip must carry through — two definitions of 'contender'
    inside one payload is the failure this build is arranged to avoid."""
    teams = [{"user_id": f"u{i}", "username": f"t{i}", "value": 1000.0 - i,
              "roster": []} for i in range(1, 5)]
    out = _review(teams=teams, inferred_outlook="rebuilder",
                  window_source="odds", window_roster_inferred="contender",
                  window_odds={"band": "unlikely", "playoff_pct": 0.1,
                               "implied": "rebuilder"},
                  member_windows={"u2": "contender", "u3": "rebuilder"})
    rows = [r["user_id"] for r in out["partners"]["opposed_window"]]
    assert rows == ["u2"], (
        "an odds-driven REBUILDER is pointed at contenders; the roster "
        "heuristic said contender and would have selected u3 instead")


# ---------------------------------------------------------------------------
# The band → window map (a cross-client encoding)
# ---------------------------------------------------------------------------

def test_band_map_covers_every_band_and_never_infers_an_extreme():
    from backend.outlook.trade_delta import playoff_band
    bands = {playoff_band(p) for p in (0.95, 0.8, 0.65, 0.5, 0.35, 0.2, 0.0)}
    assert bands == set(WINDOW_FROM_BAND), (
        "a band with no mapping would silently fall through to the heuristic")
    assert set(WINDOW_FROM_BAND.values()) == {"contender", "not_sure", "rebuilder"}
    assert "championship" not in WINDOW_FROM_BAND.values()
    assert "jets" not in WINDOW_FROM_BAND.values()


# ---------------------------------------------------------------------------
# #371 — the refusal ladder (extracted from the route so it can be tested)
# ---------------------------------------------------------------------------

BAND = {"band": "likely", "playoff_pct": 0.81, "projected_seed": 2}


def test_odds_drive_the_window_once_games_have_been_played():
    source, odds, reason = resolve_window_from_odds(BAND, completed_weeks=6)
    assert source == "odds" and reason is None
    assert odds == {"band": "likely", "playoff_pct": 0.81,
                    "implied": "contender"}


def test_preseason_refuses_the_band_but_still_reports_it():
    """The single most important refusal: `completed_weeks == 0` is the
    simulator's weakest window (D-094) and it is exactly when a manager sets
    his window. The band is still returned so the card can say what it saw."""
    source, odds, reason = resolve_window_from_odds(BAND, completed_weeks=0)
    assert source == "roster"
    assert reason == "preseason"
    assert odds["band"] == "likely" and odds["implied"] == "contender"


def test_no_band_falls_back_and_names_it():
    """ESPN, MFL, Fleaflicker, `outlook.odds` off, or a simulator failure —
    all reach here, and none of them may cost the user a window."""
    for band in (None, {}):
        source, odds, reason = resolve_window_from_odds(band, completed_weeks=9)
        assert (source, odds, reason) == ("roster", None, "odds_unavailable")


def test_an_unmapped_band_falls_back_rather_than_implying_none():
    source, odds, reason = resolve_window_from_odds(
        {"band": "who_knows", "playoff_pct": 0.5}, completed_weeks=9)
    assert source == "roster" and reason == "odds_unavailable"
    assert odds["implied"] is None, (
        "an unknown band must surface as None, never as a silent not_sure")


@pytest.mark.parametrize("pct,expect", [
    (0.90, "contender"), (0.65, "contender"),
    (0.50, "not_sure"), (0.35, "not_sure"),
    (0.10, "rebuilder"), (0.0, "rebuilder"),
])
def test_every_band_boundary_maps_the_way_the_clients_render_it(pct, expect):
    from backend.outlook.trade_delta import playoff_band
    source, odds, _r = resolve_window_from_odds(
        {"band": playoff_band(pct), "playoff_pct": pct}, completed_weeks=4)
    assert odds["implied"] == expect
    assert source == "odds"


# ---------------------------------------------------------------------------
# The route's ledger reader
# ---------------------------------------------------------------------------

def test_ledger_reader_splits_held_owned_traded_and_acquired():
    import backend.server as srv

    rows = [
        # u1 owns three of his own firsts and shipped the fourth to u2.
        {"round": 1, "owner_user_id": "u1", "original_user_id": "u1"},
        {"round": 1, "owner_user_id": "u1", "original_user_id": "u1"},
        {"round": 1, "owner_user_id": "u1", "original_user_id": "u1"},
        {"round": 1, "owner_user_id": "u2", "original_user_id": "u1"},
        # u2's own four, one of which u1 acquired.
        {"round": 1, "owner_user_id": "u2", "original_user_id": "u2"},
        {"round": 1, "owner_user_id": "u2", "original_user_id": "u2"},
        {"round": 1, "owner_user_id": "u2", "original_user_id": "u2"},
        {"round": 1, "owner_user_id": "u1", "original_user_id": "u2"},
        # Second-rounders must not be counted at all.
        {"round": 2, "owner_user_id": "u2", "original_user_id": "u1"},
        {"round": 2, "owner_user_id": "u2", "original_user_id": "u1"},
    ]
    # The function reads the DB itself, so exercise it through its one seam.
    orig = srv.load_draft_picks
    try:
        srv.load_draft_picks = lambda **kw: rows
        out = srv._first_round_ledgers("L1")
    finally:
        srv.load_draft_picks = orig

    assert out["u1"] == {"held": 4, "own_total": 4, "traded_away": 1,
                         "acquired": 1, "league_any_traded": True}
    assert out["u2"] == {"held": 4, "own_total": 4, "traded_away": 1,
                         "acquired": 1, "league_any_traded": True}
    # Round 2 is invisible: u1 shipped two seconds and neither shows up.
    assert out["u1"]["traded_away"] == 1


def test_ledger_reader_flags_a_league_with_no_recorded_movement():
    import backend.server as srv
    rows = [{"round": 1, "owner_user_id": u, "original_user_id": u}
            for u in ("u1", "u2", "u3")]
    orig = srv.load_draft_picks
    try:
        srv.load_draft_picks = lambda **kw: rows
        out = srv._first_round_ledgers("L1")
    finally:
        srv.load_draft_picks = orig
    assert all(v["league_any_traded"] is False for v in out.values())
    assert first_round_signal(out["u1"])["provenance"] == "none_traded"


def test_ledger_reader_treats_a_null_original_owner_as_never_moved():
    """An un-attributable row is not evidence of a trade. Reading NULL as
    "traded" would invent a counterparty and manufacture the signal."""
    import backend.server as srv
    rows = [{"round": 1, "owner_user_id": "u1", "original_user_id": None},
            {"round": 1, "owner_user_id": "u1", "original_user_id": ""}]
    orig = srv.load_draft_picks
    try:
        srv.load_draft_picks = lambda **kw: rows
        out = srv._first_round_ledgers("L1")
    finally:
        srv.load_draft_picks = orig
    assert out["u1"] == {"held": 2, "own_total": 2, "traded_away": 0,
                         "acquired": 0, "league_any_traded": False}


def test_ledger_reader_returns_empty_when_the_league_has_no_first_round_rows():
    import backend.server as srv
    orig = srv.load_draft_picks
    try:
        srv.load_draft_picks = lambda **kw: [
            {"round": 3, "owner_user_id": "u1", "original_user_id": "u2"}]
        assert srv._first_round_ledgers("L1") == {}
        srv.load_draft_picks = lambda **kw: (_ for _ in ()).throw(RuntimeError("db down"))
        assert srv._first_round_ledgers("L1") == {}, (
            "a pick-read failure costs the signal, never the review")
    finally:
        srv.load_draft_picks = orig
