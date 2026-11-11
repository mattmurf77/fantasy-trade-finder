"""WS4 fit-first card copy (flag trade.fit_first_copy).

docs/plans/offer-learnings/scope-fit-first-copy.md. Covers:
- each template's trigger and its threshold edge (plan rebuild / win-now for
  both sides, the declared-vs-roster viewer variants, need, surplus);
- the fallback: no specific reason, a non-bilateral or ineligible proof, or
  malformed input yields no line;
- privacy: the other team's line never reads their personal board, benefits,
  intent, preferences or a declared outlook;
- the template table and version are pinned (a reword needs a bump);
- serialization: flag off adds nothing and never calls the composer, flag on
  adds `fit_lines` only when a line fires, on real revision-2 bilateral cards;
- registration in FLAG_KEYS, config/features.json and the mirrored fixtures.
"""
import copy
import json
from pathlib import Path

import pytest

from backend import feature_flags, server, trade_narrative as tn, trade_service as ts
from backend import trade_gen_bilateral_candidate as rev2
from backend.ranking_service import Player

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


def flag(monkeypatch, on):
    monkeypatch.setitem(feature_flags._flags_cache, "trade.fit_first_copy", on)


# ── pure composer ──────────────────────────────────────────────────────────

PLAYERS = {
    "vqb": Player("vqb", "Arlo Vance", "QB", "TST", 31),
    "vwr": Player("vwr", "Finn Calder", "WR", "TST", 22),
    "vrb": Player("vrb", "Dex Hollins", "RB", "TST", 29),
    "vpk": Player("vpk", "2027 1st", "PICK", "PICK", None),
    "owr": Player("owr", "Lars Quill", "WR", "TST", 30),
    "orb": Player("orb", "Otto Vail", "RB", "TST", 22),
    "ote": Player("ote", "Dov Hesk", "TE", "TST", 23),
    "opk": Player("opk", "2028 2nd", "PICK", "PICK", None),
}
MARKET = {"vqb": 3000, "vwr": 3000, "vrb": 1500, "vpk": 2800,
          "owr": 3500, "orb": 2000, "ote": 1500, "opk": 900}
BEFORE = {"QB": 3000.0, "RB": 5000.0, "WR": 9000.0, "TE": 1500.0}
# Default: every position loses 30% (no need, no surplus) unless a test says so.
FLAT = {pos: -.3 * value for pos, value in BEFORE.items()}


def team(outlook="not_sure", source="declared", benefits=(), delta=None, before=None):
    return {"outlook": outlook, "outlook_source": source, "benefits": list(benefits),
            "usable_depth_before": dict(before or BEFORE),
            "usable_depth_delta": {**FLAT, **(delta or {})}}


def proof(give, receive, viewer=None, counterparty=None, **extra):
    data = {"generator": "owner_v2_bilateral", "generator_version": "owner-v2-bilateral-2",
            "eligible": True,
            "assets": [{"id": p, "market": MARKET[p]} for p in give + receive],
            "viewer": viewer or team(), "counterparty": counterparty or team()}
    data.update(extra)
    return data


def card(give, receive):
    return ts.TradeCard("t", "L", "me", "opp", "Other", list(give), list(receive), 0, 0, 0)


def lines(give, receive, **kw):
    return tn.fit_lines(proof(give, receive, **kw), card(give, receive), PLAYERS)


def test_viewer_declared_rebuild_names_the_pick():
    out = lines(["vqb"], ["opk"], viewer=team("rebuilder", benefits=["outlook"]))
    assert out == [{"side": "you", "code": "plan_rebuild.you",
                    "text": "Fits your rebuild: you add draft pick 2028 2nd."}]


def test_viewer_roster_read_rebuild_says_roster_and_rev3_benefit_name_counts():
    out = lines(["vqb"], ["ote"], viewer=team("jets", "inferred", ["future_pick_capital"]))
    assert out[0]["code"] == "plan_rebuild.you_roster"
    assert out[0]["text"] == "Fits your rebuild-leaning roster: you add Dov Hesk, a 23-year-old TE."


def test_viewer_plan_needs_the_engines_plan_benefit():
    assert lines(["vqb"], ["opk"], viewer=team("rebuilder", benefits=["market_terms"])) == []


def test_rebuild_never_names_a_young_rb():
    # Otto Vail is 22 but the generator scores a young RB near zero for a rebuild.
    assert lines(["vqb"], ["orb"], viewer=team("rebuilder", benefits=["outlook"])) == []


def test_viewer_win_now_names_a_now_age_player():
    out = lines(["vpk"], ["owr"], viewer=team("contender", benefits=["outlook"]))
    assert out == [{"side": "you", "code": "plan_win_now.you",
                    "text": "Fits your win-now plan: you add Lars Quill, a 30-year-old WR."}]
    assert ts._now_lean("WR", 30) >= tn.FIT_WIN_NOW_MIN_LEAN


def test_their_roster_read_rebuild_uses_public_shape_only():
    # They give a 30-year-old WR and get a 22-year-old WR plus a pick.
    out = lines(["vwr", "vpk"], ["owr"], counterparty=team("rebuilder", "inferred"))
    assert out == [{"side": "them", "code": "plan_rebuild.them",
                    "text": "Fits their rebuild-leaning roster: they add Finn Calder, a 22-year-old WR."}]


def test_their_declared_window_is_never_named():
    out = lines(["vwr", "vpk"], ["owr"], counterparty=team("rebuilder", "declared", ["outlook"]))
    assert out == []


def test_their_plan_needs_the_public_shift_not_their_benefits():
    # They get an older player for a young one: shift points away from a rebuild.
    out = lines(["vrb"], ["ote"], counterparty=team("rebuilder", "inferred", ["outlook"]))
    assert out == []


def test_their_win_now_line():
    out = lines(["vqb"], ["ote"], counterparty=team("contender", "inferred"))
    assert out == [{"side": "them", "code": "plan_win_now.them",
                    "text": "Fits their win-now roster: they add Arlo Vance, a 31-year-old QB."}]


@pytest.mark.parametrize("lift,fires", [(0.10, True), (0.09, False)])
def test_need_threshold(lift, fires):
    gain = BEFORE["WR"] * lift
    out = lines(["vqb"], ["owr"], viewer=team("contender", delta={"WR": gain, "QB": -2500}))
    assert (out == [{"side": "you", "code": "need.you",
                     "text": "Upgrades your WR group with Lars Quill."}]) is fires


def test_need_is_not_written_for_a_backup_body():
    # 15% of Lars Quill's lineup value is the backup credit; a gain at it is a backup.
    backup = .15 * MARKET["owr"] * ts.age_now_mult("WR", 30)
    small = {**BEFORE, "WR": backup * 5}
    assert lines(["vqb"], ["owr"], viewer=team("contender", delta={"WR": backup},
                                                before=small)) == []
    assert lines(["vqb"], ["owr"], viewer=team("contender", delta={"WR": backup + 1},
                                                before=small))[0]["code"] == "need.you"


@pytest.mark.parametrize("outlook", ["rebuilder", "jets"])
def test_need_is_not_a_reason_for_a_rebuild(outlook):
    assert lines(["vqb"], ["owr"], viewer=team(outlook, delta={"WR": 3000})) == []


def test_their_need_line():
    out = lines(["vwr"], ["ote"], counterparty=team("contender", "declared", delta={"WR": 2000}))
    assert out == [{"side": "them", "code": "need.them",
                    "text": "Upgrades their WR group with Finn Calder."}]


@pytest.mark.parametrize("drop,fires", [(0.02, True), (0.03, False)])
def test_surplus_threshold(drop, fires):
    out = lines(["vrb"], ["opk"], viewer=team(delta={"RB": -BEFORE["RB"] * drop}))
    assert (out == [{"side": "you", "code": "surplus.you",
                     "text": "Your RB group barely changes without Dex Hollins."}]) is fires


def test_surplus_needs_no_incoming_at_that_position():
    assert lines(["vrb"], ["orb"], viewer=team(delta={"RB": 0.0})) == []


def test_their_surplus_line_and_side_order():
    out = lines(["vrb"], ["ote"], viewer=team("contender", delta={"TE": 900}),
                counterparty=team(delta={"TE": -10.0}))
    assert [l["side"] for l in out] == ["them", "you"]
    assert out[0]["text"] == "Their TE group barely changes without Dov Hesk."
    assert out[1]["text"] == "Upgrades your TE group with Dov Hesk."


def test_plan_wins_over_need_and_need_over_surplus():
    viewer = team("contender", benefits=["outlook"], delta={"WR": 3000, "RB": 0.0})
    assert lines(["vrb", "vpk"], ["owr"], viewer=viewer)[0]["code"] == "plan_win_now.you"
    viewer = team("contender", delta={"WR": 3000, "RB": 0.0})
    assert lines(["vrb", "vpk"], ["owr"], viewer=viewer)[0]["code"] == "need.you"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(generator="owner_v1"),
    lambda d: d.update(eligible=False),
    lambda d: d["assets"].pop(),
    lambda d: d["assets"][0].update(market=float("nan")),
    lambda d: d["viewer"]["usable_depth_delta"].pop("QB"),
    lambda d: d.pop("viewer"),
])
def test_fallback_on_wrong_or_malformed_proof(mutate):
    data = proof(["vqb"], ["owr"], viewer=team("contender", delta={"WR": 3000}))
    assert tn.fit_lines(data, card(["vqb"], ["owr"]), PLAYERS)
    mutate(data)
    out = tn.fit_lines(data, card(["vqb"], ["owr"]), PLAYERS)
    assert all(l["side"] != "you" for l in out)


def test_unknown_player_or_nameless_asset_falls_back():
    players = {**PLAYERS, "owr": Player("owr", "", "WR", "TST", 30)}
    data = proof(["vqb"], ["owr"], viewer=team("contender", delta={"WR": 3000}))
    assert tn.fit_lines(data, card(["vqb"], ["owr"]), players) == []
    assert tn.fit_lines(data, card(["vqb"], ["owr"]), {}) == []


def test_no_specific_reason_means_no_line():
    assert lines(["vqb"], ["owr"]) == []


def test_their_line_ignores_every_private_counterparty_field():
    base = proof(["vwr", "vpk"], ["owr"], counterparty=team("rebuilder", "inferred"))
    expected = tn.fit_lines(base, card(["vwr", "vpk"], ["owr"]), PLAYERS)
    assert expected and expected[0]["side"] == "them"
    private = copy.deepcopy(base)
    private["counterparty"].update(
        benefits=["personal_preference", "declared_intent", "outlook"],
        intent={"net_preference": -.9, "buy_target": "vpk"},
        preferences={"untouchables": ["owr"], "targets": ["vwr"], "acquire_positions": ["RB"]},
        preference_evidence={"state": "known"}, personal_gain_fraction=-.5,
        team_plan_gain=-.5, consideration_profile={"incoming_plan_mean": -1})
    for row in private["assets"]:
        row.update(counterparty_personal=1.0, counterparty_source="explicit",
                   counterparty_preference={"direction": -1, "known": True})
    assert tn.fit_lines(private, card(["vwr", "vpk"], ["owr"]), PLAYERS) == expected


def test_template_table_and_version_are_pinned():
    assert tn.FIT_TMPL_VERSION == "fit-1"
    assert tn.FIT_TEMPLATES == {
        "plan_rebuild.you":        "Fits your rebuild: you add {asset}.",
        "plan_rebuild.you_roster": "Fits your rebuild-leaning roster: you add {asset}.",
        "plan_rebuild.them":       "Fits their rebuild-leaning roster: they add {asset}.",
        "plan_win_now.you":        "Fits your win-now plan: you add {asset}.",
        "plan_win_now.you_roster": "Fits your win-now roster: you add {asset}.",
        "plan_win_now.them":       "Fits their win-now roster: they add {asset}.",
        "need.you":                "Upgrades your {pos} group with {name}.",
        "need.them":               "Upgrades their {pos} group with {name}.",
        "surplus.you":             "Your {pos} group barely changes without {name}.",
        "surplus.them":            "Their {pos} group barely changes without {name}.",
    }
    for text in tn.FIT_TEMPLATES.values():
        assert "!" not in text and "good fit" not in text.lower() and text.isascii()
    assert (tn.FIT_NEED_MIN_LIFT, tn.FIT_SURPLUS_MAX_DROP, tn.FIT_WIN_NOW_MIN_LEAN,
            tn.FIT_THEIR_PLAN_MIN_SHIFT) == (.10, .02, .05, .05)


# ── serialization on real revision-2 cards ─────────────────────────────────

SPEC = {
    "m1": ("QB", 31, 3200), "m2": ("QB", 24, 2600), "m3": ("RB", 23, 4200),
    "m4": ("RB", 29, 1500), "m5": ("WR", 27, 5200), "m6": ("WR", 22, 3000),
    "m7": ("WR", 30, 1400), "m8": ("TE", 28, 1900), "mp": ("PICK", None, 2800),
    "a1": ("QB", 34, 2400), "a2": ("RB", 28, 3600), "a3": ("WR", 31, 3900),
    "a4": ("WR", 23, 3400), "a5": ("TE", 31, 2200), "ap": ("PICK", None, 3000),
    "b1": ("QB", 27, 4800), "b2": ("RB", 25, 4400), "b3": ("WR", 29, 4000),
    "b4": ("WR", 24, 3700), "b5": ("TE", 24, 2900), "bp": ("PICK", None, 1000),
}


def league_cards(viewer_outlook="contender"):
    players = {p: Player(p, f"Player {p.upper()}", pos, "PICK" if pos == "PICK" else "TST", age)
               for p, (pos, age, _) in SPEC.items()}
    seed = {p: ts.value_to_elo(v) for p, (_, _, v) in SPEC.items()}
    board = lambda tweak: {p: ts.value_to_elo(v * tweak.get(p, 1.)) for p, (_, _, v) in SPEC.items()}
    roster = lambda c: [p for p in SPEC if p.startswith(c)]
    members = [ts.LeagueMember("A", "Harbor", roster("a"), board({"m6": 1.3, "mp": 1.25}), True),
               ts.LeagueMember("B", "Ridge", roster("b"), board({"m5": 1.25, "m8": 1.2}), True)]
    cards, _ = rev2.generate_bilateral_trades(
        players=players, league=ts.League("L", "Synthetic", "sleeper", members),
        user_id="me", user_roster=roster("m"), seed_elo=seed,
        user_elo=board({"a2": 1.25, "b2": 1.2, "a4": 1.2, "b4": 1.15, "m6": .85}),
        outlook=viewer_outlook, opponent_outlooks={"B": "contender"},
        inferred_outlooks={"A": "rebuilder"}, fairness_threshold=.75)
    assert cards
    return cards, players


def test_flag_off_payload_is_unchanged_and_composer_never_runs(monkeypatch):
    cards, players = league_cards()
    flag(monkeypatch, True)
    on = [server.trade_card_to_dict(c, players) for c in cards]
    assert any("fit_lines" in p for p in on)
    flag(monkeypatch, False)
    def forbidden(*a, **k):
        raise AssertionError("fit_lines composed with the flag off")
    monkeypatch.setattr(tn, "fit_lines", forbidden)
    off = [server.trade_card_to_dict(c, players) for c in cards]
    assert all("fit_lines" not in p for p in off)
    stripped = [{k: v for k, v in p.items() if k != "fit_lines"} for p in on]
    assert json.dumps(stripped) == json.dumps(off)


def test_flag_on_cards_carry_wellformed_lines_and_no_private_fields(monkeypatch):
    cards, players = league_cards()
    flag(monkeypatch, True)
    payloads = [server.trade_card_to_dict(c, players) for c in cards]
    assert any("fit_lines" in p for p in payloads)
    for p, c in zip(payloads, cards):
        expected = tn.fit_lines(c.owner_evaluation.as_dict(), c, players)
        assert p.get("fit_lines", []) == expected
        assert "fit_lines" not in p or p["fit_lines"]
        sides = [line["side"] for line in expected]
        assert sides in ([], ["them"], ["you"], ["them", "you"])
        for line in expected:
            assert set(line) == {"side", "code", "text"} and line["code"] in tn.FIT_TEMPLATES
    blob = json.dumps(payloads)
    for private in ("counterparty_benefits", "counterparty_preference", "weaker_support",
                    "valuation_json", "owner_evaluation"):
        assert private not in blob


def test_flag_on_without_a_line_is_byte_identical(monkeypatch):
    cards, players = league_cards()
    monkeypatch.setattr(tn, "fit_lines", lambda *a, **k: [])
    flag(monkeypatch, True)
    on = [server.trade_card_to_dict(c, players) for c in cards]
    flag(monkeypatch, False)
    off = [server.trade_card_to_dict(c, players) for c in cards]
    assert json.dumps(on) == json.dumps(off)


def test_a_mutated_card_gets_no_line(monkeypatch):
    cards, players = league_cards()
    flag(monkeypatch, True)
    target = next(c for c in cards if server.trade_card_to_dict(c, players).get("fit_lines"))
    mutated = copy.deepcopy(target)
    mutated.give_value = mutated.give_value + 1
    assert "fit_lines" not in server.trade_card_to_dict(mutated, players)


def test_flag_registered_dark_everywhere():
    assert "trade.fit_first_copy" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["trade.fit_first_copy"] is False
    assert json.loads((REPO / "config/features.json").read_text())["trade.fit_first_copy"] is False
    for name in ("release", "profiles-on", "onboarding-v2"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture["trade.fit_first_copy"] is False, name
    assert "`trade.fit_first_copy`" in (REPO / "docs/config-reference.md").read_text()
