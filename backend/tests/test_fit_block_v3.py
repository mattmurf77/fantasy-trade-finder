"""WS4b fit block, version 3 (flag trade.fit_first_copy, template fit-2).

docs/plans/offer-learnings/scope-fit-block-v3.md. Replaces WS4's `fit_lines`
(test_fit_first_copy.py, retired with it). Covers:
- league position ranks: equal to compute_power_rankings' consensus values
  ranked as League rankings ranks them (1 + teams strictly above), before AND
  after the trade, on randomised leagues; ties share a rank; the 5%-of-median
  noise bar at its edge; picks have no rank; fewer than three valued teams
  means no ranks; a context that disagrees with the card means no ranks;
- the lead table: every plan and need phrase, declared vs roster-read
  variants, and the moves-only phrase (no praise, losses still shown);
- the outlook tags: the viewer's declared word or roster read, the other
  team's roster read ALWAYS, never their declared setting, no tag for
  not_sure;
- privacy: the other team's whole block is byte-identical when their declared
  outlook, personal board, benefits, intent or preferences change;
- the block is omitted when no team has a lead or a rank move; malformed
  proofs yield nothing; the template table, tags, constants and version are
  pinned;
- serialization: flag off adds nothing and never builds a context or calls
  the composer; flag on without a context adds nothing; flag on with the
  job's context adds `fit_block` equal to the composer's output on real
  revision-2 cards, with no private field; a mutated card gets none;
- the job context (_fit_league_context): League rankings' inputs, picks out,
  the generator's own roster read (equal to the proof's outlook for an
  undeclared team), declared outlooks ignored; shared on copy;
- prepared inventories accept the card and carry the block in its public
  record; the worker attaches the context once per job;
- registration of the flag in all mirrors.
"""
import ast
import copy
import inspect
import json
import random
from pathlib import Path

import pytest

from backend import feature_flags, power_rankings, server, trade_narrative as tn, trade_service as ts
from backend import trade_gen_bilateral_candidate as rev2
from backend.ranking_service import Player

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


def flag(monkeypatch, on):
    monkeypatch.setitem(feature_flags._flags_cache, "trade.fit_first_copy", on)


# ── a small league with a hand-checkable shape ─────────────────────────────

P = {
    "vqb": Player("vqb", "Arlo Vance", "QB", "TST", 31),
    "vwr": Player("vwr", "Finn Calder", "WR", "TST", 22),
    "vrb": Player("vrb", "Dex Hollins", "RB", "TST", 29),
    "vte": Player("vte", "Ivo Marsh", "TE", "TST", 26),
    "vpk": Player("vpk", "2027 1st", "PICK", "PICK", None),
    "oqb": Player("oqb", "Rafe Odum", "QB", "TST", 27),
    "owr": Player("owr", "Lars Quill", "WR", "TST", 30),
    "orb": Player("orb", "Otto Vail", "RB", "TST", 22),
    "ote": Player("ote", "Dov Hesk", "TE", "TST", 23),
    "opk": Player("opk", "2028 2nd", "PICK", "PICK", None),
    **{f"{t}{pos.lower()}": Player(f"{t}{pos.lower()}", f"{t.upper()} {pos}", pos, "TST", 26)
       for t in ("x", "y") for pos in ("QB", "RB", "WR", "TE")},
}
VALUE = {"vqb": 3000, "vwr": 3000, "vrb": 1500, "vte": 800, "vpk": 2800,
         "oqb": 2500, "owr": 3500, "orb": 2000, "ote": 1500, "opk": 900,
         "xqb": 3200, "xrb": 2600, "xwr": 4200, "xte": 1200,
         "yqb": 1800, "yrb": 1400, "ywr": 2400, "yte": 1700}
ROSTERS = {"me": ["vqb", "vwr", "vrb", "vte", "vpk"], "opp": ["oqb", "owr", "orb", "ote", "opk"],
           "x": ["xqb", "xrb", "xwr", "xte"], "y": ["yqb", "yrb", "ywr", "yte"]}
BEFORE = {"QB": 3000.0, "RB": 5000.0, "WR": 9000.0, "TE": 1500.0}
FLAT = {pos: -.3 * value for pos, value in BEFORE.items()}   # no need anywhere by default


def context(rosters=ROSTERS, values=VALUE, players=P, reads=None, viewer="me"):
    """A FitLeagueContext built the way the job builds one (picks out)."""
    seed = {p: ts.value_to_elo(v) for p, v in values.items()}
    ids = {u: [p for p in r if players[p].position != "PICK"] for u, r in rosters.items()}
    teams = power_rankings.compute_power_rankings(
        [{"user_id": u, "player_ids": r} for u, r in ids.items()], seed, players)
    return tn.FitLeagueContext(viewer_id=viewer, teams=teams, medians=server._position_medians(teams),
                               rosters=ids, reads=reads if reads is not None else {})


def team(outlook="not_sure", source="declared", benefits=(), delta=None):
    return {"outlook": outlook, "outlook_source": source, "benefits": list(benefits),
            "usable_depth_before": dict(BEFORE), "usable_depth_delta": {**FLAT, **(delta or {})}}


def proof(give, receive, viewer=None, counterparty=None):
    return {"generator": "owner_v2_bilateral", "generator_version": "owner-v2-bilateral-2",
            "eligible": True,
            "assets": [{"id": p, "market": VALUE[p]} for p in give + receive],
            "viewer": viewer or team(), "counterparty": counterparty or team()}


def card(give, receive, target="opp"):
    return ts.TradeCard("t", "L", "me", target, "Other", list(give), list(receive), 0, 0, 0)


def block(give, receive, reads=None, ctx=None, **kw):
    return tn.fit_block(proof(give, receive, **kw), card(give, receive),
                        P, ctx or context(reads=reads))


def side(out, which):
    return next(t for t in out["teams"] if t["side"] == which)


# ── ranks ──────────────────────────────────────────────────────────────────

def ref_rank(teams, uid, pos):
    """League rankings' teamPosRank (LeagueSummaryScreen.tsx): 1 + the teams
    with strictly more value at the position, over compute_power_rankings."""
    mine = next(t for t in teams if t["user_id"] == uid)["positions"][pos]["value"]
    return 1 + sum(t["positions"][pos]["value"] > mine for t in teams)


def test_ranks_equal_power_rankings_before_and_after_on_random_leagues():
    rng = random.Random(11)
    checked = 0
    for league in range(60):
        n = rng.randint(4, 12)
        players, values, rosters = {}, {}, {}
        for t in range(n):
            uid = "me" if t == 0 else f"u{t}"
            rosters[uid] = []
            for i in range(rng.randint(6, 14)):
                pid = f"{uid}_{i}"
                pos = rng.choice(["QB", "RB", "WR", "WR", "TE"])
                players[pid] = Player(pid, pid, pos, "TST", rng.randint(21, 33))
                # A coarse grid makes exact ties common, so tie handling is exercised.
                values[pid] = rng.choice([100, 200, 300, 500, 800, 1200, 2000, 3000])
                rosters[uid].append(pid)
        ctx = context(rosters, values, players)
        seed = {p: ts.value_to_elo(v) for p, v in values.items()}
        members = lambda r: [{"user_id": u, "player_ids": ids} for u, ids in r.items()]
        before = power_rankings.compute_power_rankings(members(rosters), seed, players)
        medians = server._position_medians(before)
        for _ in range(8):
            other = rng.choice([u for u in rosters if u != "me"])
            give = rng.sample(rosters["me"], rng.randint(1, 3))
            receive = rng.sample(rosters[other], rng.randint(1, 3))
            assets = {p: {"pos": players[p].position} for p in give + receive}
            rows = tn._fit_rank_rows(ctx, other, give, receive, assets)
            moved = {u: list(ids) for u, ids in rosters.items()}
            moved["me"] = [p for p in moved["me"] if p not in give] + receive
            moved[other] = [p for p in moved[other] if p not in receive] + give
            after = power_rankings.compute_power_rankings(members(moved), seed, players)
            for label, uid in (("you", "me"), ("them", other)):
                shown = {m["pos"]: m for m in rows[label]}
                for pos in ("QB", "RB", "WR", "TE"):
                    old = next(t for t in before if t["user_id"] == uid)["positions"][pos]["value"]
                    new = next(t for t in after if t["user_id"] == uid)["positions"][pos]["value"]
                    b, a = ref_rank(before, uid, pos), ref_rank(after, uid, pos)
                    bar = tn.FIT_RANK_MIN_MOVE * medians[pos]["value"]
                    expected = new != old and abs(new - old) >= bar and b != a
                    assert (pos in shown) is expected, (league, uid, pos, old, new, b, a)
                    if expected:
                        assert shown[pos] == {"pos": pos, "before": b, "after": a}
                        checked += 1
    assert checked > 200


def test_ties_share_a_rank():
    # WR: x 4000, viewer 3000, y 2500, opp 2000. The viewer sends a 500 WR:
    # viewer, y and opp all sit on 2500, tied for 2nd behind x.
    players = {**{f"{u}w": Player(f"{u}w", f"{u} W", "WR", "TST", 26) for u in "mxyo"},
               "mw2": Player("mw2", "Sent W", "WR", "TST", 26),
               "pk": Player("pk", "2028 2nd", "PICK", "PICK", None)}
    values = {"mw": 2500, "mw2": 500, "xw": 4000, "yw": 2500, "ow": 2000, "pk": 500}
    rosters = {"me": ["mw", "mw2"], "x": ["xw"], "y": ["yw"], "opp": ["ow", "pk"]}
    ctx = context(rosters, values, players)
    rows = tn._fit_rank_rows(ctx, "opp", ["mw2"], ["pk"], {"mw2": {"pos": "WR"}, "pk": {"pos": "PICK"}})
    assert rows["them"] == [{"pos": "WR", "before": 4, "after": 2}]
    assert rows["you"] == []          # 2nd before, tied 2nd after: no move


@pytest.mark.parametrize("sent,shown", [(147.5, True), (147.4, False)])
def test_noise_bar_is_five_percent_of_the_league_median(sent, shown):
    # WR: x 4000, viewer 3000, opp 2900, y 1000 -> median 2950, bar 147.5.
    players = {**{f"{u}w": Player(f"{u}w", f"{u} W", "WR", "TST", 26) for u in "mxyo"},
               "mw2": Player("mw2", "Sent W", "WR", "TST", 26),
               "pk": Player("pk", "2028 2nd", "PICK", "PICK", None)}
    values = {"mw": 3000 - sent, "mw2": sent, "xw": 4000, "ow": 2900, "yw": 1000, "pk": 500}
    rosters = {"me": ["mw", "mw2"], "x": ["xw"], "opp": ["ow", "pk"], "y": ["yw"]}
    ctx = context(rosters, values, players)
    assert ctx.medians["WR"] == 2950.0
    rows = tn._fit_rank_rows(ctx, "opp", ["mw2"], ["pk"], {"mw2": {"pos": "WR"}, "pk": {"pos": "PICK"}})
    assert rows["you"] == ([{"pos": "WR", "before": 2, "after": 3}] if shown else [])
    assert rows["them"] == ([{"pos": "WR", "before": 3, "after": 2}] if shown else [])


def test_picks_have_no_rank_and_a_pick_only_side_shows_none():
    out = block(["vqb"], ["opk"], viewer=team("rebuilder", benefits=["outlook"]))
    you = side(out, "you")
    assert you["lead"]["text"] == "Rebuilding: adds the 2028 2nd"
    # QB: x 3200, viewer 3000, opp 2500, y 1800. Only the QB moves a rank.
    assert you["ranks"] == [{"pos": "QB", "before": 2, "after": 4}]
    assert side(out, "them")["ranks"] == [{"pos": "QB", "before": 3, "after": 1}]
    pick_for_pick = tn._fit_rank_rows(context(), "opp", ["vpk"], ["opk"],
                                      {"vpk": {"pos": "PICK"}, "opk": {"pos": "PICK"}})
    assert pick_for_pick == {"them": [], "you": []}


def test_fewer_than_three_valued_teams_means_no_ranks():
    small = {"me": ROSTERS["me"], "opp": ROSTERS["opp"], "x": [], "y": []}
    ctx = context(small)
    assert ctx.valued == 2
    out = tn.fit_block(proof(["vwr"], ["owr"], viewer=team("contender", benefits=["outlook"])),
                       card(["vwr"], ["owr"]), P, ctx)
    assert [t["ranks"] for t in out["teams"]] == [[], []]
    assert side(out, "you")["lead"]["code"] == "plan_win_now.you"
    big = context()
    assert big.valued == 4 and tn._fit_rank_rows(
        big, "opp", ["vwr"], ["owr"], {"vwr": {"pos": "WR"}, "owr": {"pos": "WR"}}) is not None


def test_a_context_that_disagrees_with_the_card_shows_no_ranks():
    moved = {**ROSTERS, "me": [p for p in ROSTERS["me"] if p != "vwr"], "x": ROSTERS["x"] + ["vwr"]}
    assert tn._fit_rank_rows(context(moved), "opp", ["vwr"], ["owr"],
                             {"vwr": {"pos": "WR"}, "owr": {"pos": "WR"}}) is None
    assert tn._fit_rank_rows(context(), "nobody", ["vwr"], ["owr"],
                             {"vwr": {"pos": "WR"}, "owr": {"pos": "WR"}}) is None


def test_gains_come_first_then_losses():
    # The viewer sends a WR and gets an RB plus a pick: one gain, one loss each.
    out = block(["vwr"], ["orb", "opk"])
    assert side(out, "them")["ranks"] == [{"pos": "WR", "before": 2, "after": 1},
                                          {"pos": "RB", "before": 2, "after": 4}]
    assert side(out, "you")["ranks"] == [{"pos": "RB", "before": 3, "after": 1},
                                         {"pos": "WR", "before": 3, "after": 4}]


# ── lead phrases and tags ──────────────────────────────────────────────────

def test_viewer_declared_rebuild_and_its_tag():
    out = block(["vqb"], ["opk"], viewer=team("rebuilder", benefits=["outlook"]))
    you = side(out, "you")
    assert you["lead"] == {"code": "plan_rebuild.you", "text": "Rebuilding: adds the 2028 2nd"}
    assert you["tag"] == {"code": "rebuilder", "source": "declared", "text": "Rebuilding"}


def test_viewer_roster_read_says_leaning_and_its_tag_says_looks():
    out = block(["vqb"], ["ote"], viewer=team("rebuilder", "inferred", ["future_pick_capital"]))
    you = side(out, "you")
    assert you["lead"] == {"code": "plan_rebuild.you_roster", "text": "Rebuild-leaning: adds Dov Hesk, 23"}
    assert you["tag"] == {"code": "rebuilder", "source": "roster", "text": "Looks rebuilding"}


def test_viewer_win_now_declared_and_roster():
    out = block(["vpk"], ["owr"], viewer=team("contender", benefits=["outlook"]))
    assert side(out, "you")["lead"] == {"code": "plan_win_now.you", "text": "Win-now: adds Lars Quill, 30"}
    assert side(out, "you")["tag"]["text"] == "Contending"
    out = block(["vpk"], ["owr"], viewer=team("contender", "inferred", ["outlook"]))
    assert side(out, "you")["lead"]["text"] == "Win-now-leaning: adds Lars Quill, 30"
    assert side(out, "you")["tag"]["text"] == "Looks contending"


@pytest.mark.parametrize("outlook,text", [("championship", "All-in"), ("jets", "Tanking")])
def test_viewer_declared_extremes(outlook, text):
    out = block(["vqb"], ["owr"], viewer=team(outlook))
    assert side(out, "you")["tag"] == {"code": outlook, "source": "declared", "text": text}


def test_viewer_plan_needs_the_engines_plan_benefit():
    out = block(["vqb"], ["opk"], viewer=team("rebuilder", benefits=["market_terms"]))
    assert side(out, "you")["lead"]["code"] == "moves.you"


def test_their_roster_read_plan_lead_and_tag():
    out = block(["vwr", "vpk"], ["owr"], reads={"opp": "rebuilder"})
    them = out["teams"][0]
    assert them["side"] == "them"
    assert them["lead"] == {"code": "plan_rebuild.them", "text": "Rebuild-leaning: adds Finn Calder, 22"}
    assert them["tag"] == {"code": "rebuilder", "source": "roster", "text": "Looks rebuilding"}


def test_their_win_now_lead():
    out = block(["vqb"], ["ote"], reads={"opp": "contender"})
    assert side(out, "them")["lead"] == {"code": "plan_win_now.them",
                                         "text": "Win-now-leaning: adds Arlo Vance, 31"}


def test_their_plan_needs_the_public_shift():
    # They get an older player for a young one: not a rebuild shape.
    out = block(["vrb"], ["ote"], reads={"opp": "rebuilder"})
    assert side(out, "them")["lead"]["code"] == "moves.them"


def test_rebuild_never_names_a_young_rb():
    out = block(["vqb"], ["orb"], viewer=team("rebuilder", benefits=["outlook"]))
    assert side(out, "you")["lead"]["code"] == "moves.you"


@pytest.mark.parametrize("lift,fires", [(0.10, True), (0.09, False)])
def test_need_threshold(lift, fires):
    out = block(["vqb"], ["owr"], viewer=team("contender", delta={"WR": BEFORE["WR"] * lift, "QB": -2500}))
    lead = side(out, "you")["lead"]
    assert (lead == {"code": "need.you", "text": "Upgrades WR: adds Lars Quill"}) is fires


def test_need_is_not_written_for_a_backup_body():
    backup = .15 * VALUE["owr"] * ts.age_now_mult("WR", 30)
    small = {**BEFORE, "WR": backup * 5}
    def lead(delta):
        viewer = {**team("contender", delta={"WR": delta}), "usable_depth_before": small}
        return side(block(["vqb"], ["owr"], viewer=viewer), "you")["lead"]["code"]
    assert lead(backup) == "moves.you"
    assert lead(backup + 1) == "need.you"


def test_their_need_lead_uses_the_roster_read_not_their_declared_outlook():
    cp = team("rebuilder", "declared", delta={"WR": 2000})       # declared rebuild
    out = block(["vwr"], ["ote"], counterparty=cp, reads={"opp": "contender"})
    assert side(out, "them")["lead"] == {"code": "need.them", "text": "Upgrades WR: adds Finn Calder"}
    out = block(["vwr"], ["ote"], counterparty=cp, reads={"opp": "rebuilder"})
    assert side(out, "them")["lead"]["code"] != "need.them"       # the read is a rebuild


def test_moves_only_has_no_praise_and_still_shows_losses():
    # The mockup's weak case: neither side has a reason; ranks still move.
    out = block(["vwr"], ["orb"])
    them, you = out["teams"]
    assert them["lead"] == {"code": "moves.them", "text": "Gets Finn Calder, gives Otto Vail"}
    assert you["lead"] == {"code": "moves.you", "text": "Gets Otto Vail, gives Finn Calder"}
    assert any(m["after"] > m["before"] for m in them["ranks"] + you["ranks"])
    multi = block(["vwr", "vpk"], ["orb", "opk"])
    assert side(multi, "them")["lead"]["text"] == "Gets Finn Calder + 2027 1st, gives Otto Vail + 2028 2nd"


def test_no_lead_and_no_rank_move_means_no_block():
    # A TE-for-TE swap of equal value moves no rank and has no reason.
    values = {**VALUE, "vte": 1500}
    assert block(["vte"], ["ote"], ctx=context(values=values)) is None


def test_other_team_first_and_at_most_two_teams():
    out = block(["vwr"], ["orb"])
    assert [t["side"] for t in out["teams"]] == ["them", "you"]
    assert out["v"] == "fit-2"


@pytest.mark.parametrize("read", ["not_sure", None])
def test_no_tag_without_a_read(read):
    out = block(["vwr"], ["orb"], reads={"opp": read} if read else {})
    assert "tag" not in side(out, "them")
    out = block(["vwr"], ["orb"], viewer=team("not_sure", "inferred"))
    assert "tag" not in side(out, "you")


def test_the_other_teams_declared_outlook_is_never_the_tag():
    for declared in ("championship", "contender", "rebuilder", "jets", "not_sure"):
        out = block(["vwr"], ["orb"], counterparty=team(declared, "declared"), reads={"opp": "rebuilder"})
        assert side(out, "them")["tag"] == {"code": "rebuilder", "source": "roster",
                                            "text": "Looks rebuilding"}


def test_their_whole_block_ignores_every_private_counterparty_field():
    reads = {"opp": "rebuilder"}
    base = proof(["vwr", "vpk"], ["owr"], counterparty=team("contender", "declared"))
    ctx = context(reads=reads)
    expected = tn.fit_block(base, card(["vwr", "vpk"], ["owr"]), P, ctx)
    assert side(expected, "them")["lead"]["code"] == "plan_rebuild.them"
    for mutate in (
        lambda c: c.update(outlook="jets"),
        lambda c: c.update(outlook="rebuilder", outlook_source="inferred"),
        lambda c: c.update(outlook=None, outlook_source=None),
        lambda c: c.update(benefits=["personal_preference", "declared_intent", "outlook"]),
        lambda c: c.update(intent={"net_preference": -.9, "buy_target": "vpk"}),
        lambda c: c.update(preferences={"untouchables": ["owr"], "targets": ["vwr"],
                                        "acquire_positions": ["RB"], "team_outlook": "jets"}),
        lambda c: c.update(preference_evidence={"state": "known"}, personal_gain_fraction=-.5,
                           team_plan_gain=-.5, consideration_profile={"incoming_plan_mean": -1}),
    ):
        private = copy.deepcopy(base)
        mutate(private["counterparty"])
        for row in private["assets"]:
            row.update(counterparty_personal=1.0, counterparty_source="explicit",
                       counterparty_preference={"direction": -1, "known": True})
        got = tn.fit_block(private, card(["vwr", "vpk"], ["owr"]), P, ctx)
        assert json.dumps(side(got, "them"), sort_keys=True) == json.dumps(side(expected, "them"), sort_keys=True)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(generator="owner_v1"),
    lambda d: d.update(eligible=False),
    lambda d: d["assets"].pop(),
    lambda d: d["assets"][0].update(market=float("nan")),
])
def test_fallback_on_wrong_or_malformed_proof(mutate):
    data = proof(["vqb"], ["owr"], viewer=team("contender", delta={"WR": 3000}))
    assert tn.fit_block(data, card(["vqb"], ["owr"]), P, context())
    mutate(data)
    assert tn.fit_block(data, card(["vqb"], ["owr"]), P, context()) is None


def test_no_context_or_unknown_asset_means_no_block():
    data = proof(["vqb"], ["owr"], viewer=team("contender", delta={"WR": 3000}))
    assert tn.fit_block(data, card(["vqb"], ["owr"]), P, None) is None
    assert tn.fit_block(data, card(["vqb"], ["owr"]), P, {"values": {}}) is None
    nameless = {**P, "owr": Player("owr", "", "WR", "TST", 30)}
    assert tn.fit_block(data, card(["vqb"], ["owr"]), nameless, context()) is None


def test_template_table_tags_and_version_are_pinned():
    assert tn.FIT_TMPL_VERSION == "fit-2"
    assert tn.FIT_TEMPLATES == {
        "plan_rebuild.you":        "Rebuilding: adds {asset}",
        "plan_rebuild.you_roster": "Rebuild-leaning: adds {asset}",
        "plan_rebuild.them":       "Rebuild-leaning: adds {asset}",
        "plan_win_now.you":        "Win-now: adds {asset}",
        "plan_win_now.you_roster": "Win-now-leaning: adds {asset}",
        "plan_win_now.them":       "Win-now-leaning: adds {asset}",
        "need.you":                "Upgrades {pos}: adds {name}",
        "need.them":               "Upgrades {pos}: adds {name}",
        "moves.you":               "Gets {gets}, gives {gives}",
        "moves.them":              "Gets {gets}, gives {gives}",
    }
    assert tn.FIT_TAGS == {
        "declared": {"championship": "All-in", "contender": "Contending",
                     "rebuilder": "Rebuilding", "jets": "Tanking"},
        "roster": {"contender": "Looks contending", "rebuilder": "Looks rebuilding"},
    }
    for text in [*tn.FIT_TEMPLATES.values(), *tn.FIT_TAGS["declared"].values(),
                 *tn.FIT_TAGS["roster"].values()]:
        assert "!" not in text and "good fit" not in text.lower() and text.isascii()
    assert (tn.FIT_NEED_MIN_LIFT, tn.FIT_WIN_NOW_MIN_LEAN, tn.FIT_THEIR_PLAN_MIN_SHIFT,
            tn.FIT_RANK_MIN_MOVE, tn.FIT_RANK_MIN_TEAMS) == (.10, .05, .05, .05, 3)
    assert not hasattr(tn, "fit_lines")       # fit-1 is retired, not left beside fit-2


# ── the job context and serialization on real revision-2 cards ─────────────

SPEC = {
    "m1": ("QB", 31, 3200), "m2": ("QB", 24, 2600), "m3": ("RB", 23, 4200),
    "m4": ("RB", 29, 1500), "m5": ("WR", 27, 5200), "m6": ("WR", 22, 3000),
    "m7": ("WR", 30, 1400), "m8": ("TE", 28, 1900), "mp": ("PICK", None, 2800),
    "a1": ("QB", 34, 2400), "a2": ("RB", 28, 3600), "a3": ("WR", 31, 3900),
    "a4": ("WR", 23, 3400), "a5": ("TE", 31, 2200), "ap": ("PICK", None, 3000),
    "b1": ("QB", 27, 4800), "b2": ("RB", 25, 4400), "b3": ("WR", 29, 4000),
    "b4": ("WR", 24, 3700), "b5": ("TE", 24, 2900), "bp": ("PICK", None, 1000),
    "c1": ("QB", 29, 2000), "c2": ("RB", 26, 2500), "c3": ("WR", 26, 2600), "c4": ("TE", 27, 900),
}


def owner_league():
    players = {p: Player(p, f"Player {p.upper()}", pos, "PICK" if pos == "PICK" else "TST", age)
               for p, (pos, age, _) in SPEC.items()}
    seed = {p: ts.value_to_elo(v) for p, (_, _, v) in SPEC.items()}
    board = lambda tweak: {p: ts.value_to_elo(v * tweak.get(p, 1.)) for p, (_, _, v) in SPEC.items()}
    roster = lambda c: [p for p in SPEC if p.startswith(c)]
    members = [ts.LeagueMember("A", "Harbor", roster("a"), board({"m6": 1.3, "mp": 1.25}), True),
               ts.LeagueMember("B", "Ridge", roster("b"), board({"m5": 1.25, "m8": 1.2}), True),
               ts.LeagueMember("C", "Cove", roster("c"), {}, False)]
    league = ts.League("L", "Synthetic", "sleeper", members)
    kwargs = dict(players=players, league=league, user_id="me", user_roster=roster("m"),
                  seed_elo=seed, user_elo=board({"a2": 1.25, "b2": 1.2, "a4": 1.2, "b4": 1.15, "m6": .85}),
                  outlook="contender", opponent_outlooks={"B": "contender"},
                  inferred_outlooks={"A": "rebuilder"}, fairness_threshold=.75)
    owner_context = {"user_id": "me", "players": players, "league": league,
                     "user_roster": roster("m"), "scoring_format": "1qb_ppr",
                     "config": dict(ts._cfg), "inferred_outlooks": {"A": "rebuilder"},
                     "manager_preferences": {"B": {"team_outlook": "contender"}}}
    return kwargs, owner_context, seed


@pytest.fixture
def league(monkeypatch):
    kwargs, owner_context, seed = owner_league()
    monkeypatch.setattr(server, "_get_universal_pool",
                        lambda fmt: (list(kwargs["players"].values()), dict(seed)))
    cards, _ = rev2.generate_bilateral_trades(**kwargs)
    assert cards
    return cards, kwargs["players"], owner_context


def test_job_context_ranks_from_league_rankings_inputs_without_picks(monkeypatch, league):
    _, players, owner_context = league
    flag(monkeypatch, True)
    ctx = server._fit_league_context(owner_context, None)
    seed, meta = server._power_value_inputs("1qb_ppr", None, players.values())
    members = [{"user_id": u, "player_ids": [p for p in SPEC if p.startswith(c) and SPEC[p][0] != "PICK"]}
               for u, c in (("me", "m"), ("A", "a"), ("B", "b"), ("C", "c"))]
    teams = power_rankings.compute_power_rankings(members, seed, meta)
    assert ctx.values == {t["user_id"]: {p: t["positions"][p]["value"] for p in ("QB", "RB", "WR", "TE")}
                          for t in teams}
    assert not any(pid.endswith("p") for pid in ctx.owner)            # no picks
    assert ctx.medians == {p: v["value"] for p, v in server._position_medians(teams).items()}


def test_job_context_reads_are_the_generators_and_ignore_declared_outlooks(monkeypatch, league):
    cards, _, owner_context = league
    flag(monkeypatch, True)
    ctx = server._fit_league_context(owner_context, None)
    assert ctx.reads["A"] == "rebuilder"                              # the stored roster read
    # B declared contender; its tag comes from its roster, the same function the
    # generator runs for an undeclared team.
    assert ctx.reads["B"] == ts.infer_team_outlook(list(owner_context["league"].members[1].roster),
                                                   owner_context["players"], num_teams=4)[0]
    for declared in ("rebuilder", "jets", None):
        changed = copy.deepcopy(owner_context)
        changed["manager_preferences"]["B"]["team_outlook"] = declared
        assert server._fit_league_context(changed, None).reads == ctx.reads
    # Where the counterparty is undeclared, the tag's read IS the proof's outlook.
    for c in cards:
        cp = c.owner_evaluation.as_dict()["counterparty"]
        if cp["outlook_source"] == "inferred":
            assert ctx.reads[c.target_user_id] == cp["outlook"]


def test_job_context_is_none_with_the_flag_off_or_no_owner_context(monkeypatch, league):
    _, _, owner_context = league
    assert server._fit_league_context(owner_context, None) is None
    flag(monkeypatch, True)
    assert server._fit_league_context(None, None) is None


def stamp(cards, ctx):
    for c in cards:
        c.fit_context = ctx
    return cards


def test_flag_off_payload_is_unchanged_and_composer_never_runs(monkeypatch, league):
    cards, players, owner_context = league
    flag(monkeypatch, True)
    stamp(cards, server._fit_league_context(owner_context, None))
    on = [server.trade_card_to_dict(c, players) for c in cards]
    assert any("fit_block" in p for p in on)
    flag(monkeypatch, False)
    def forbidden(*a, **k):
        raise AssertionError("fit_block composed with the flag off")
    monkeypatch.setattr(tn, "fit_block", forbidden)
    off = [server.trade_card_to_dict(c, players) for c in cards]
    assert all("fit_block" not in p and "fit_lines" not in p for p in off)
    assert json.dumps([{k: v for k, v in p.items() if k != "fit_block"} for p in on]) == json.dumps(off)


def test_flag_on_without_a_context_is_byte_identical(monkeypatch, league):
    cards, players, _ = league
    flag(monkeypatch, True)
    on = [server.trade_card_to_dict(c, players) for c in cards]
    flag(monkeypatch, False)
    off = [server.trade_card_to_dict(c, players) for c in cards]
    assert json.dumps(on) == json.dumps(off)


def test_flag_on_cards_carry_the_composers_block_and_no_private_fields(monkeypatch, league):
    cards, players, owner_context = league
    flag(monkeypatch, True)
    ctx = server._fit_league_context(owner_context, None)
    payloads = [server.trade_card_to_dict(c, players) for c in stamp(cards, ctx)]
    assert any("fit_block" in p for p in payloads)
    for p, c in zip(payloads, cards):
        assert p.get("fit_block") == tn.fit_block(c.owner_evaluation.as_dict(), c, players, ctx)
        if "fit_block" in p:
            assert [t["side"] for t in p["fit_block"]["teams"]] == ["them", "you"]
            for t in p["fit_block"]["teams"]:
                assert set(t) <= {"side", "tag", "lead", "ranks"} and t["lead"]["code"] in tn.FIT_TEMPLATES
                if "tag" in t and t["side"] == "them":
                    assert t["tag"]["source"] == "roster"
    blob = json.dumps(payloads)
    for private in ("counterparty_benefits", "counterparty_preference", "weaker_support",
                    "valuation_json", "owner_evaluation", "fit_context", "fit_lines"):
        assert private not in blob


def test_a_mutated_card_gets_no_block(monkeypatch, league):
    cards, players, owner_context = league
    flag(monkeypatch, True)
    stamp(cards, server._fit_league_context(owner_context, None))
    target = next(c for c in cards if server.trade_card_to_dict(c, players).get("fit_block"))
    mutated = copy.deepcopy(target)
    assert mutated.fit_context is target.fit_context                 # shared, never copied
    mutated.give_value = mutated.give_value + 1
    assert "fit_block" not in server.trade_card_to_dict(mutated, players)


def test_prepared_inventory_accepts_the_card_and_carries_the_block(monkeypatch, league):
    from backend import prepared_trade_payload as payload
    cards, players, owner_context = league
    flag(monkeypatch, True)
    stamp(cards, server._fit_league_context(owner_context, None))
    target = next(c for c in cards if server.trade_card_to_dict(c, players).get("fit_block"))
    public = server.trade_card_to_dict(target, players)
    record = payload.capture_runtime_card(target, public)
    assert record["public"]["fit_block"] == public["fit_block"]
    restored = payload.restore_runtime_card(record, user_id="me", league_id="L")
    assert not hasattr(restored, "fit_context")


def test_the_worker_builds_the_context_once_and_stamps_owner_cards():
    tree = ast.parse(inspect.getsource(server._run_trade_job).lstrip())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_fit_league_context"]
    assert len(calls) == 1
    gen = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_gen_owner")
    assert any(isinstance(n, ast.Attribute) and n.attr == "fit_context" and isinstance(n.ctx, ast.Store)
               for n in ast.walk(gen))


# ── speed guards on the real worker (owner route harness, revision 2) ──────

from backend.tests.test_owner_generator_routes import harness, owner_harness  # noqa: E402,F401
from backend.tests.test_trade_fast_deck import revised, run, spy  # noqa: E402,F401


def test_flag_on_job_computes_the_league_once_and_never_per_card(revised, monkeypatch):
    flag(monkeypatch, True)
    contexts = spy(monkeypatch, server, "_fit_league_context")
    league_walks = spy(monkeypatch, power_rankings, "compute_power_rankings")
    # The harness league (three all-RB teams) rarely earns a real block, so the
    # composer is replaced by a marker that proves the published card carries it.
    marker = lambda proof, card, players, context: {"v": "fit-2", "teams": [], "id": card.trade_id}
    composed = spy(monkeypatch, tn, "fit_block", marker)
    job = run(monkeypatch)
    assert job["cards"]
    assert len(contexts) == 1 and contexts[0] is not None
    assert len(league_walks) == 1                       # one league-wide walk per deck
    # The per-card step ran once per published card; nothing walked the league again.
    assert len(composed) == len(job["cards"])
    assert [c["fit_block"]["id"] for c in job["cards"]] == [c["trade_id"] for c in job["cards"]]


def test_flag_off_job_builds_nothing_and_composes_nothing(revised, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("fit-block work ran with the flag off")
    league_walks = spy(monkeypatch, power_rankings, "compute_power_rankings")
    value_reads = spy(monkeypatch, server, "_power_value_inputs")
    monkeypatch.setattr(tn, "fit_block", forbidden)
    job = run(monkeypatch)
    assert job["cards"] and not league_walks and not value_reads
    assert all("fit_block" not in c for c in job["cards"])


def test_serving_a_stored_or_running_page_never_recomposes():
    # Pages are served from the dicts stored at publication (job["cards"],
    # trade_page_store blobs, prepared public records): none of the serve
    # paths can reach the composer or the league step.
    for name in ("_trade_job_public_view", "_trade_job_page_view", "_trade_page_read",
                 "_trade_page_view", "_trade_page_status_view", "_trade_page_past_stored",
                 "_serve_stored_trade_page"):
        source = inspect.getsource(getattr(server, name))
        for forbidden in ("trade_card_to_dict", "fit_block", "_fit_league_context"):
            assert forbidden not in source, (name, forbidden)


def test_flag_registered_everywhere_default_off_in_code_on_in_config():
    # Turned on by the operator's instruction of 2026-11-10 ("turn it on"); the code
    # default stays off, so a missing or unreadable config still means off.
    assert "trade.fit_first_copy" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["trade.fit_first_copy"] is False
    assert json.loads((REPO / "config/features.json").read_text())["trade.fit_first_copy"] is True
    for name in ("release", "profiles-on", "onboarding-v2"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture["trade.fit_first_copy"] is True, name
    assert "`trade.fit_first_copy`" in (REPO / "docs/config-reference.md").read_text()
