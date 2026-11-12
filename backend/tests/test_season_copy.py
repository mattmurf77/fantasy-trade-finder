"""Win-now season signal, WI-3: the card copy (`trade_narrative`).

Spec: docs/plans/win-now-season-signal/prd.md §3, §5.3, §6 (copy rules 1-6);
lld.md §5.1 (fit block leads), §5.2 (season block), §10 invariants I13, I14;
build-plan.md WI-3.

Proofs come from the real revision 5 generator on the WI-1 fixture league
(`test_trade_gen_bilateral_season.world` / `deck` / `_operator_world`: public NFL
players, synthetic owners, boards and picks) and the job's `FitLeagueContext` built
the way the worker builds it. Hand edits of a real proof only where the generator
cannot reach a case (a plan name the operator world does not hold, a corrupted row).
No network, no database.

Covered (each proven red against the named sabotage, then green on revert):
- I14 test_win_now_only_under_copy_rule_1. Sabotage: leave `_fit_plan`'s age branch
  reachable for a scored side (drop the `season_usable` gate).
- I13 test_label_printed_is_the_label_the_plan_fit_table_read. Sabotage: recompute
  the label in the composer (from age).
- test_conflict_sentence_per_kind, test_conflict_names_the_qualifying_asset_on_the_deck,
  test_conflict_sentence_per_plan_name. Sabotage: name the most valuable asset
  instead of `conflict.named`. Per kind (board, target, position, trade_block,
  trade_away) also: print the position sentence for a trade_away conflict.
- test_unscored_not_sure_viewer_sees_revision_2s_card_on_the_whole_deck. Sabotages:
  suppress the Them win-now lead for unscored viewers; emit a labels-only block for
  Not sure.
- test_rebuilding_and_tanking_copy_on_the_deck (amended 2026-11-11: these viewers are
  season-scored in the shed direction): the line reads as for contenders; the shed lead
  ("Rebuilding: -3.2 pts/wk, adds X") only when the card sheds >= 0.5 a week and X is
  the most valuable incoming pick or projected rebuild piece / cornerstone; the points
  conflict lead ("Away from Tanking: +2.1 pts/wk") only when the points rule fired; the
  label conflict lead only when the label rule fired; otherwise today's You lead.
  Sabotages: drop the -0.5 gate on the shed lead; read the conflict lead by plan, not
  trigger (`conflict_plan.you` for every Rebuilding/Tanking conflict).
- test_shed_lead_needs_its_facts (hand edits of a real proof): no shed lead under 0.5 a
  week, without a future-labelled or pick asset, or for an "add" viewer. Sabotage:
  name the most valuable incoming asset whatever its label.
- test_unsaved_rebuilding_roster_is_scored_never_flagged. Sabotage: print the saved-plan
  name ("Rebuilding") for a roster read.
- test_scored_viewer_keeps_their_win_now_lead_only_for_a_labelled_asset. Sabotage:
  keep the Them lead for every asset.
- test_without_usable_evidence_the_fit_block_is_revision_2s_and_no_season_block.
  Sabotage: emit an empty season block (`{"v": "season-1"}`) without usable evidence.
- test_no_figure_or_label_for_an_unprojected_asset. Sabotage: treat a missing ppg
  as 0.0 (projected).
- test_every_season_lead_fits_one_line (a length assertion, no sabotage): every name
  in the fixture pool, the longest (22 characters) shortened to "J. Croskey-Merritt".
- test_fit_template_version_is_still_fit_2. Sabotage: bump FIT_TMPL_VERSION.
- Also: the season line's wording at its bands, a conflict named on the wrong side
  prints nothing, an unscored viewer gets no line, the
  template lint (extends test_fit_block_v3's to the new templates), the block's keys.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

import pytest

from backend import feature_flags as ff, power_rankings, server, trade_narrative as tn, trade_service as ts
from backend import trade_gen_bilateral_season as r5
from backend.ranking_service import Player
from backend.tests import test_trade_gen_bilateral_season as gen

ADAMS = gen.ADAMS
LONGEST = max((gen.POOL[p]["full_name"] for t in gen.LEAGUE["teams"] for p in t["players"]), key=len)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


def context(args, reads=None):
    """The job's FitLeagueContext for a world (picks out), as `_fit_league_context` builds it."""
    players = args["players"]
    rosters = {args["user_id"]: [p for p in args["user_roster"] if players[p].position != "PICK"]}
    for member in args["league"].members:
        rosters[member.user_id] = [p for p in member.roster if players[p].position != "PICK"]
    teams = power_rankings.compute_power_rankings(
        [{"user_id": u, "player_ids": r} for u, r in rosters.items()], args["seed_elo"], players)
    return tn.FitLeagueContext(viewer_id=args["user_id"], teams=teams,
                               medians=server._position_medians(teams), rosters=rosters,
                               reads=args["opponent_outlooks"] if reads is None else reads)


@lru_cache(maxsize=None)
def composed(revision, outlook, season="usable"):
    """[(card, proof, fit_block, season_block)] for a whole generated deck."""
    args = gen.world(outlook)
    ctx = context(args)
    cards, _ = gen.deck(revision, outlook, season) if revision == 5 else gen.deck(2, outlook)
    out = []
    for card in cards:
        proof = card.owner_evaluation.as_dict()
        out.append((card, proof, tn.fit_block(proof, card, args["players"], ctx),
                    tn.season_block(proof, card, args["players"])))
    return out


def you(block):
    return next((t for t in (block or {}).get("teams", ()) if t["side"] == "you"), None)


def leads(block):
    return [t["lead"] for t in (block or {}).get("teams", ())]


def operator(**prefs):
    """(args, evidence, card, twin) for PRD §7's world: Adams (a starter) for a backup RB."""
    args, ev, (card, twin) = gen._operator_world(**prefs)
    return args, ev, card, twin


def evaluate(card, args, ev):
    return r5.evaluate_bilateral_trade(card, **args, season_evidence=ev).as_dict()


# ── I14: "Win-now" only under copy rule 1 ─────────────────────────────────────

@pytest.mark.parametrize("outlook", ["championship", "contender", "rebuilder", "not_sure"])
def test_win_now_only_under_copy_rule_1(outlook):
    rows = composed(5, outlook)
    args = gen.world(outlook)
    said = 0
    for card, proof, block, _ in rows:
        signal = proof["season_signal"]
        assets = {a["id"]: a for a in signal["assets"]}
        # The You side (the Them side: test_scored_viewer_keeps_their_win_now_lead_only_for_a_labelled_asset;
        # an unscored viewer's Them side is revision 2's: test_unscored_viewer_*).
        for team in (block or {}).get("teams", ()):
            lead = team["lead"]
            if team["side"] != "you":
                continue
            assert not lead["code"].startswith("plan_win_now"), lead
            if "win-now" not in lead["text"].lower():
                continue
            said += 1
            if lead["code"] == "season_win_now.you":
                # The named player is a win-now piece, starts for the viewer, and the
                # trade adds at least 0.5 a week to the viewer's lineup.
                named = [p for p in card.receive_player_ids
                         if lead["text"].startswith(f"Win-now: {args['players'][p].name} ")
                         or lead["text"].startswith(f"Win-now: {tn._season_short(args['players'][p].name)} ")]
                assert len(named) == 1
                row = assets[named[0]]
                assert row["label"] == "win_now" and row["starts_for_viewer"] is True and row["ppg"] is not None
                assert signal["viewer"]["delta_pts_week"] >= .5
                assert lead["text"].endswith(f", +{signal['viewer']['delta_pts_week']:.1f}/wk")
            else:
                # Rebuilding / Tanking conflict: the PRD's rule is that the most valuable
                # piece received is a win-now piece.
                assert lead["code"] == "conflict_plan.you" and signal["conflict"]["fired"]
                assert any(assets[p]["label"] == "win_now" for p in card.receive_player_ids)
    if outlook in ("championship", "contender"):
        assert said > 0
    # Teeth: the same proofs read as revision 2 (no season record) do say "Win-now: adds"
    # from age, on the side the season copy now governs.
    base = 0
    ctx = context(args)
    for card, proof, _, _ in rows[:400]:
        stripped = {k: v for k, v in proof.items() if k != "season_signal"}
        base += any(l["code"].startswith("plan_win_now")
                    for l in leads(tn.fit_block(stripped, card, args["players"], ctx)))
    assert base > 0


# ── I13: the label printed is the label the plan-fit table read ───────────────

@pytest.mark.parametrize("outlook", ["championship", "rebuilder"])
def test_label_printed_is_the_label_the_plan_fit_table_read(outlook):
    printed = 0
    for card, proof, _, block in composed(5, outlook):
        signal = proof["season_signal"]
        rows = {a["id"]: a for a in signal["assets"]}
        shown = {l["id"]: l for l in (block or {}).get("labels", ())}
        for pid, row in rows.items():
            is_pick = pid not in gen.POOL               # fixture picks are not pool players
            expected = (row["label"] in tn.SEASON_LABELS and row["ppg"] is not None and not is_pick)
            assert (pid in shown) is expected, (pid, row)
            if expected:
                printed += 1
                assert shown[pid]["label"] == row["label"]
                assert shown[pid]["text"] == tn.SEASON_LABELS[row["label"]]
                assert shown[pid]["starts_for_you"] is (row["starts_for_viewer"] is True)
            if signal["viewer"].get("season_direction") == "add" and row["starts_for_viewer"]:
                # The plan-fit table's read: full credit exactly for a labelled starter.
                assert (row["plan_lean"] == r5.LEAN_STARTS_LABELLED) is (row["label"] in ("win_now", "cornerstone"))
    assert printed > 0


# ── conflict sentences ────────────────────────────────────────────────────────

def _below_market_world():
    """The operator world with no lift on the RB and the viewer's board 20% under market
    on Adams: the card qualifies through the board on the player given away."""
    args, ev, card, twin = operator(lift=False)
    args["user_elo"][ADAMS] = ts.value_to_elo(gen.POOL[ADAMS]["dp_value_1qb"] * .8)
    return args, ev, card


CASES = {
    "board.above": (lambda: operator()[:3], "conflict.board.above",
                    "You rank rb_kid above market, but this moves away from All-in"),
    "board.below": (_below_market_world, "conflict.board.below",
                    "You rank Davante Adams below market, but this moves away from All-in"),
    "target": (lambda: operator(lift=False, me={"targets": ["rb_kid"]})[:3], "conflict.target",
               "rb_kid is on your target list, but this moves away from All-in"),
    "position": (lambda: operator(lift=False, me={"acquire_positions": ["RB"]})[:3], "conflict.position",
                 "You asked for RBs, but this moves away from All-in"),
    "trade_block": (lambda: operator(lift=False, me={"trade_block": [ADAMS]})[:3], "conflict.trade_block",
                    "You marked Davante Adams to move, but this moves away from All-in"),
    "trade_away": (lambda: operator(lift=False, me={"trade_away_positions": ["WR"]})[:3], "conflict.trade_away",
                   "You are shopping WRs, but this moves away from All-in"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_conflict_sentence_per_kind(case):
    build, code, text = CASES[case]
    args, ev, card = build()
    proof = evaluate(card, args, ev)
    conflict = proof["season_signal"]["conflict"]
    assert proof["eligible"] and conflict["fired"] and conflict["plan"] == "championship"
    assert conflict["kind"] == case.split(".")[0]
    block = tn.season_block(proof, card, args["players"])
    assert block["conflict"] == {"code": code, "text": text}
    # The sentence names `conflict.named` (or its position): the asset the kind is about.
    named = args["players"][conflict["named"]]
    assert (named.position + "s" if case in ("position", "trade_away") else named.name) in text
    delta = proof["season_signal"]["viewer"]["delta_pts_week"]
    lead = you(tn.fit_block(proof, card, args["players"], context(args)))["lead"]
    assert lead == {"code": "conflict.you", "text": f"Away from All-in: {delta:+.1f} pts/wk"}
    assert lead["text"].startswith("Away from All-in: -")
    if case == "board.below":
        # Adams is not the most valuable asset on this card: the sentence names the
        # asset whose ranking qualified it.
        market = {a["id"]: a["market"] for a in proof["assets"]}
        assert conflict["named"] == ADAMS and max(market, key=market.get) != ADAMS


def test_conflict_names_the_qualifying_asset_on_the_deck():
    checked = not_top = 0
    for outlook in ("championship", "rebuilder"):
        args = gen.world(outlook)
        for card, proof, _, block in composed(5, outlook):
            conflict = proof["season_signal"]["conflict"]
            if not conflict["fired"]:
                assert "conflict" not in (block or {})
                continue
            name = args["players"][conflict["named"]].name
            assert name in block["conflict"]["text"]
            above = conflict["named"] in card.receive_player_ids
            assert block["conflict"]["code"] == ("conflict.board.above" if above else "conflict.board.below")
            plan = tn.FIT_TAGS["declared"][outlook]
            assert block["conflict"]["text"].endswith(f", but this moves away from {plan}")
            market = {a["id"]: a["market"] for a in proof["assets"]}
            not_top += max(market, key=lambda p: (market[p], p)) != conflict["named"]
            checked += 1
    assert checked > 0 and not_top > 0


@pytest.mark.parametrize("plan, name", sorted(tn.FIT_TAGS["declared"].items()))
def test_conflict_sentence_per_plan_name(plan, name):
    args, ev, card, _ = operator()
    proof = evaluate(card, args, ev)
    proof["season_signal"]["conflict"]["plan"] = plan
    block = tn.season_block(proof, card, args["players"])
    assert block["conflict"]["text"] == f"You rank rb_kid above market, but this moves away from {name}"
    if plan in ("rebuilder", "jets"):
        # The lead follows the rule that fired: the label rule, or the points rule.
        proof["season_signal"]["conflict"]["trigger"] = "label"
        lead = you(tn.fit_block(proof, card, args["players"], context(args)))["lead"]
        assert lead == {"code": "conflict_plan.you", "text": f"Away from {name}: adds a win-now piece"}
        proof["season_signal"]["conflict"]["trigger"] = "points"
        proof["season_signal"]["viewer"]["delta_pts_week"] = 2.14
        lead = you(tn.fit_block(proof, card, args["players"], context(args)))["lead"]
        assert lead == {"code": "conflict.you", "text": f"Away from {name}: +2.1 pts/wk"}
    else:
        lead = you(tn.fit_block(proof, card, args["players"], context(args)))["lead"]
        delta = proof["season_signal"]["viewer"]["delta_pts_week"]
        assert lead == {"code": "conflict.you", "text": f"Away from {name}: {delta:+.1f} pts/wk"}


def test_a_conflict_named_on_the_wrong_side_prints_nothing():
    """A declared kind whose `named` asset is not on the side the kind is about (a
    corrupted proof): no sentence is composed, so the block is withheld."""
    args, ev, card, _ = operator(lift=False, me={"trade_block": [ADAMS]})
    proof = evaluate(card, args, ev)
    proof["season_signal"]["conflict"]["named"] = "rb_kid"
    assert tn.season_block(proof, card, args["players"]) is None


# ── a viewer the season does not score: today's fit block ─────────────────────

def test_unscored_not_sure_viewer_sees_revision_2s_card_on_the_whole_deck():
    """Not sure with usable evidence: every fit block is revision 2's byte for byte,
    on both sides, and no card gets a season block."""
    base, rows = composed(2, "not_sure"), composed(5, "not_sure")
    assert len(base) == len(rows) > 0
    them_win_now = 0
    for (card2, _, block2, _), (card5, proof5, block5, season5) in zip(base, rows):
        assert gen.ident(card2) == gen.ident(card5)
        assert proof5["season_signal"]["evidence"]["state"] == "usable"
        assert proof5["season_signal"]["viewer"]["scored"] is False
        assert json.dumps(block5, sort_keys=False) == json.dumps(block2, sort_keys=False)
        assert season5 is None
        them_win_now += any(l["code"] == "plan_win_now.them" for l in leads(block5))
    assert them_win_now > 0  # teeth: the age-based Them lead is on this deck and kept


def _stripped(proof):
    return {k: v for k, v in proof.items() if k != "season_signal"}


@pytest.mark.parametrize("outlook", ["rebuilder", "jets"])
def test_rebuilding_and_tanking_copy_on_the_deck(outlook):
    """A saved Rebuilding / Tanking plan with usable evidence: scored in the shed direction.
    Each You lead is the one its facts support; the season line reads as for contenders."""
    args = gen.world(outlook)
    ctx = context(args)
    plan = tn.FIT_TAGS["declared"][outlook]
    counts = {"shed": 0, "points": 0, "label": 0, "today": 0}
    for card, proof, block, season in composed(5, outlook):
        signal = proof["season_signal"]
        viewer, conflict = signal["viewer"], signal["conflict"]
        delta = viewer["delta_pts_week"]
        assert viewer["season_direction"] == "shed"
        assert season["line"].startswith("Season no change" if abs(delta) < .5 else f"Season {delta:+.1f} pts/wk")
        lead = you(block)["lead"] if you(block) else None
        assert lead is None or len(lead["text"]) <= tn.FIT_LEAD_MAX
        rows = {a["id"]: a for a in signal["assets"]}
        if conflict["fired"]:
            if conflict["trigger"] == "points":
                counts["points"] += 1
                assert delta >= sv_threshold(outlook) - 1e-9
                assert lead == {"code": "conflict.you", "text": f"Away from {plan}: {delta:+.1f} pts/wk"}
            else:
                counts["label"] += 1
                assert lead == {"code": "conflict_plan.you", "text": f"Away from {plan}: adds a win-now piece"}
            continue
        if lead and lead["code"] == "season_shed.you":
            counts["shed"] += 1
            assert delta <= -.5
            future = [p for p in card.receive_player_ids if args["players"][p].position == "PICK"
                      or (rows[p]["ppg"] is not None and rows[p]["label"] in ("rebuild", "cornerstone"))]
            market = {a["id"]: a["market"] for a in proof["assets"]}
            top = max(future, key=lambda p: (market[p], p))
            name = args["players"][top].name
            assert lead["text"].startswith(f"{plan}: {delta:+.1f} pts/wk, adds ")
            assert lead["text"].removeprefix(f"{plan}: {delta:+.1f} pts/wk, adds ") in (
                f"the {name}", name, tn._season_short(name))
            continue
        counts["today"] += 1
        stripped = tn.fit_block(_stripped(proof), card, args["players"], ctx)
        if block is None and stripped is not None:
            # Nothing supported on either side: the only lead revision 2 had was the Them
            # side's age-based "Win-now-leaning" for an asset not labelled win-now (copy rule 1).
            them = [t["lead"] for t in stripped["teams"] if t["side"] == "them"]
            assert them and them[0]["code"] == "plan_win_now.them" and not any(t["ranks"] for t in stripped["teams"])
            counts["them_dropped"] = counts.get("them_dropped", 0) + 1
            continue
        today = you(stripped or {})
        assert (lead or None) == (today["lead"] if today else None)
    assert counts["shed"] > 0 and counts["points"] > 0 and counts["today"] > 0, counts


def sv_threshold(outlook):
    from backend import season_value as sv
    return sv.CONFLICT_ADD[outlook]


def _shed_proof():
    """A real Tanking viewer's proof for the operator card (Adams out, rb_kid in)."""
    args, ev, card, _ = operator()
    args["outlook"] = "jets"
    proof = evaluate(card, args, ev)
    assert proof["eligible"] and proof["season_signal"]["viewer"]["season_direction"] == "shed"
    return args, card, proof


def test_shed_lead_needs_its_facts():
    args, card, proof = _shed_proof()
    signal = proof["season_signal"]
    delta = signal["viewer"]["delta_pts_week"]
    assert delta <= -.5 and not signal["conflict"]["fired"]
    assert {a["id"]: a["label"] for a in signal["assets"]}["rb_kid"] == "rebuild"
    ctx = context(args)
    lead = you(tn.fit_block(proof, card, args["players"], ctx))["lead"]
    assert lead == {"code": "season_shed.you", "text": f"Tanking: {delta:+.1f} pts/wk, adds rb_kid"}
    today = you(tn.fit_block(_stripped(proof), card, args["players"], ctx))
    for edit in ("small", "unlabelled", "add"):
        changed = copy.deepcopy(proof)
        sig = changed["season_signal"]
        if edit == "small":
            sig["viewer"]["delta_pts_week"] = -.49
        elif edit == "unlabelled":
            next(a for a in sig["assets"] if a["id"] == "rb_kid")["label"] = "depth"
        else:
            sig["viewer"]["season_direction"] = "add"
        got = you(tn.fit_block(changed, card, args["players"], ctx))
        assert not got or got["lead"]["code"] != "season_shed.you", edit
        if edit != "add":
            assert (got and got["lead"]) == (today and today["lead"]), edit
    missing = copy.deepcopy(proof)
    del missing["season_signal"]["viewer"]["season_direction"]
    assert tn.fit_block(missing, card, args["players"], ctx) is None   # never inferred from the outlook
    assert tn.season_block(missing, card, args["players"]) is None


def test_unsaved_rebuilding_roster_is_scored_never_flagged():
    args, ev, card, _ = operator()
    args["outlook"] = None
    args["inferred_outlooks"] = {"me": "rebuilder"}
    proof = evaluate(card, args, ev)
    viewer = proof["season_signal"]["viewer"]
    assert viewer["scored"] is True and viewer["season_direction"] == "shed"
    assert proof["season_signal"]["conflict"]["fired"] is False
    block = tn.season_block(proof, card, args["players"])
    assert block["line"].startswith(f"Season {viewer['delta_pts_week']:+.1f} pts/wk") and "conflict" not in block
    lead = you(tn.fit_block(proof, card, args["players"], context(args)))["lead"]
    assert lead == {"code": "season_shed.you",
                    "text": f"Rebuild-leaning: {viewer['delta_pts_week']:+.1f} pts/wk, adds rb_kid"}


def test_unsaved_not_sure_roster_gets_no_season_block_and_todays_fit_block():
    args, ev, card, _ = operator()
    args["outlook"] = None
    args["inferred_outlooks"] = {"me": "not_sure"}
    proof = evaluate(card, args, ev)
    assert proof["season_signal"]["viewer"]["scored"] is False
    assert proof["season_signal"]["evidence"]["state"] == "usable"
    assert tn.season_block(proof, card, args["players"]) is None
    ctx = context(args)
    assert (tn.fit_block(proof, card, args["players"], ctx)
            == tn.fit_block(_stripped(proof), card, args["players"], ctx))


@pytest.mark.parametrize("outlook", ["championship", "contender"])
def test_scored_viewer_keeps_their_win_now_lead_only_for_a_labelled_asset(outlook):
    """The other team's "Win-now-leaning: adds X" stands for a season-scored viewer only
    when the engine labelled X win-now or cornerstone; otherwise the need / rank-fact lead."""
    args = gen.world(outlook)
    ctx = context(args)
    kept = dropped = 0
    for card, proof, block, _ in composed(5, outlook):
        stripped = {k: v for k, v in proof.items() if k != "season_signal"}
        today = tn.fit_block(stripped, card, args["players"], ctx)
        them_today = next((t for t in (today or {}).get("teams", ()) if t["side"] == "them"), None)
        them = next((t for t in (block or {}).get("teams", ()) if t["side"] == "them"), None)
        if not them_today or them_today["lead"]["code"] != "plan_win_now.them":
            assert not them or them["lead"]["code"] != "plan_win_now.them"
            continue
        rows = {a["id"]: a for a in proof["season_signal"]["assets"]}
        described = {tn._fit_describe(tn._fit_asset(p, args["players"])): p for p in card.give_player_ids}
        named = described[them_today["lead"]["text"].removeprefix("Win-now-leaning: adds ")]
        if rows[named]["label"] in ("win_now", "cornerstone"):
            kept += 1
            assert them["lead"] == them_today["lead"]
        else:
            dropped += 1
            assert not them or them["lead"]["code"] != "plan_win_now.them"
    assert kept > 0 and dropped > 0


# ── without usable evidence: today's copy, byte for byte, and no season block ─

@pytest.mark.parametrize("outlook", ["championship", "jets"])
@pytest.mark.parametrize("season", ["absent", "unavailable"])
def test_without_usable_evidence_the_fit_block_is_revision_2s_and_no_season_block(season, outlook):
    base, rows = composed(2, outlook), composed(5, outlook, season)
    assert len(base) == len(rows) > 0
    for (card2, proof2, block2, season2), (card5, proof5, block5, season5) in zip(base, rows):
        assert gen.ident(card2) == gen.ident(card5)
        assert json.dumps(block5, sort_keys=False) == json.dumps(block2, sort_keys=False)
        assert season2 is None and season5 is None
        assert proof5["season_signal"]["evidence"]["state"] == ("absent" if season == "absent" else "unavailable")


def test_a_revision_2_proof_never_gets_a_season_block_and_keeps_its_age_rule():
    rows = composed(2, "championship")
    assert all(s is None for *_, s in rows)
    assert any(l["code"] == "plan_win_now.you" for *_, b, _ in rows for l in leads(b))


# ── unprojected assets ────────────────────────────────────────────────────────

def test_no_figure_or_label_for_an_unprojected_asset():
    args, ev, card, _ = operator()
    del ev["players"]["rb_kid"]                      # the RB has no forecast row
    proof = evaluate(card, args, ev)
    rows = {a["id"]: a for a in proof["season_signal"]["assets"]}
    assert rows["rb_kid"]["ppg"] is None and rows["rb_kid"]["label"] is None
    # Engine output plus a corrupted row (a label and a start claim with no ppg):
    # neither may print a label, a figure or a season lead for him.
    corrupt = copy.deepcopy(proof)
    sig = corrupt["season_signal"]
    row = next(a for a in sig["assets"] if a["id"] == "rb_kid")
    row.update(label="win_now", starts_for_viewer=True, gain_for_viewer=None)
    sig["viewer"]["delta_pts_week"] = 2.0
    sig["conflict"]["fired"] = False
    ctx = context(args)
    for p in (proof, corrupt):
        block = tn.season_block(p, card, args["players"])
        fit = tn.fit_block(p, card, args["players"], ctx)
        assert all(l["id"] != "rb_kid" for l in (block or {}).get("labels", ()))
        texts = [l["text"] for l in leads(fit)] + [block["line"]] + (
            [block["conflict"]["text"]] if "conflict" in block else [])
        assert not any("0.0" in t for t in texts), texts
        assert not any(l["code"].startswith("season_") for l in leads(fit))


# ── one line per lead ─────────────────────────────────────────────────────────

def test_every_season_lead_fits_one_line():
    assert LONGEST == "Jacory Croskey-Merritt" and len(LONGEST) == 22
    names = sorted({gen.POOL[p]["full_name"] for t in gen.LEAGUE["teams"] for p in t["players"]})
    for name in names:
        for label in ("win_now", "cornerstone"):
            season = {"scored": True, "delta": 12.34, "direction": "add", "conflict": None,
                      "assets": {"x": {"ppg": 14.0, "label": label, "starts_for_viewer": True,
                                       "gain_for_viewer": 12.34}}}
            code, values = tn._season_lead(season, [{"id": "x", "name": name, "pos": "RB", "age": 25}],
                                           {"x": 1000.0})
            text = tn.SEASON_FIT_TEMPLATES[code].format(**values)
            assert len(text) <= tn.FIT_LEAD_MAX, text
            assert values["name"] == (name if len(tn.SEASON_FIT_TEMPLATES[code].format(name=name, pts="12.3"))
                                      <= tn.FIT_LEAD_MAX else tn._season_short(name))
    assert tn._season_short(LONGEST) == "J. Croskey-Merritt"
    for plan in tn.FIT_TAGS["declared"].values():
        for text in (tn.SEASON_FIT_TEMPLATES["conflict.you"].format(plan=plan, pts="-12.3"),
                     tn.SEASON_FIT_TEMPLATES["conflict_plan.you"].format(plan=plan)):
            assert len(text) <= tn.FIT_LEAD_MAX, text
    # The shed lead: every pool name, either plan word, or no lead (today's) when even
    # the short name does not fit.
    for name in names:
        for outlook, declared in (("jets", True), ("rebuilder", True), ("rebuilder", False)):
            season = {"scored": True, "delta": -12.34, "direction": "shed", "conflict": None,
                      "outlook": outlook, "declared": declared,
                      "assets": {"x": {"ppg": 4.0, "label": "rebuild"}}}
            got = tn._season_lead(season, [{"id": "x", "name": name, "pos": "WR", "age": 22}], {"x": 900.0})
            if got is not None:
                assert len(tn.SEASON_FIT_TEMPLATES[got[0]].format(**got[1])) <= tn.FIT_LEAD_MAX
    # And on the generated decks.
    for outlook in ("championship", "contender", "rebuilder", "jets"):
        for *_, block, _ in composed(5, outlook):
            for lead in leads(block):
                if lead["code"] in tn.SEASON_FIT_TEMPLATES:
                    assert len(lead["text"]) <= tn.FIT_LEAD_MAX, lead


# ── version, shape, wording ───────────────────────────────────────────────────

def test_fit_template_version_is_still_fit_2():
    assert tn.FIT_TMPL_VERSION == "fit-2"
    blocks = [b for *_, b, _ in composed(5, "championship") if b]
    assert blocks and all(b["v"] == "fit-2" for b in blocks)
    assert all(set(t) <= {"side", "tag", "lead", "ranks", "positions"} for b in blocks for t in b["teams"])


def test_season_block_shape_and_unscored_viewer():
    for outlook in ("championship", "rebuilder", "not_sure"):
        for card, proof, _, block in composed(5, outlook):
            if block is None:
                continue
            scored = proof["season_signal"]["viewer"]["scored"]
            keys = {"v", "weeks", "as_of", "labels", "conflict"} | (
                {"line", "season_pts_week", "dynasty_pct", "dynasty_dir"} if scored else set())
            assert {"v", "weeks", "as_of"} <= set(block) <= keys
            assert block["v"] == tn.SEASON_BLOCK_VERSION == "season-1"
            assert scored is (outlook in ("championship", "rebuilder")) and ("line" in block) is scored
            assert block["weeks"] == len(proof["season_signal"]["evidence"]["weeks"])


@pytest.mark.parametrize("delta, cost, line, pts, pct, direction", [
    (2.14, 3.2, "Season +2.1 pts/wk · Dynasty cost 3%", 2.1, 3.0, "cost"),
    (-1.82, 0.0, "Season -1.8 pts/wk · Dynasty even", -1.8, 0.0, "even"),
    (0.49, -2.5, "Season no change · Dynasty gain 3%", 0.5, 3.0, "gain"),
    (-0.49, 0.49, "Season no change · Dynasty even", -0.5, 0.0, "even"),
    (0.5, -0.5, "Season +0.5 pts/wk · Dynasty gain 1%", 0.5, 1.0, "gain"),
])
def test_season_line_wording(delta, cost, line, pts, pct, direction):
    args, ev, card, twin = operator()
    proof = evaluate(twin, args, ev)
    proof["season_signal"]["viewer"].update(delta_pts_week=delta, dynasty_cost_pct=cost)
    block = tn.season_block(proof, twin, args["players"])
    assert (block["line"], block["season_pts_week"], block["dynasty_pct"], block["dynasty_dir"]) == (
        line, pts, pct, direction)


def test_new_templates_are_pinned_and_pass_the_template_lint():
    assert tn.SEASON_FIT_TEMPLATES == {
        "conflict.you":       "Away from {plan}: {pts} pts/wk",
        "conflict_plan.you":  "Away from {plan}: adds a win-now piece",
        "season_win_now.you": "Win-now: {name} starts, +{pts}/wk",
        "season_starter.you": "Starts for you: {name}, +{pts}/wk",
        "season_shed.you":    "{plan}: {pts} pts/wk, adds {asset}",
    }
    assert tn.SEASON_TEMPLATES == {
        "season":               "Season {pts} pts/wk",
        "season_flat":          "Season no change",
        "dynasty_cost":         "Dynasty cost {pct}%",
        "dynasty_gain":         "Dynasty gain {pct}%",
        "dynasty_even":         "Dynasty even",
        "conflict.board.above": "You rank {name} above market, but this moves away from {plan}",
        "conflict.board.below": "You rank {name} below market, but this moves away from {plan}",
        "conflict.target":      "{name} is on your target list, but this moves away from {plan}",
        "conflict.position":    "You asked for {pos}s, but this moves away from {plan}",
        "conflict.trade_block": "You marked {name} to move, but this moves away from {plan}",
        "conflict.trade_away":  "You are shopping {pos}s, but this moves away from {plan}",
    }
    assert tn.SEASON_LABELS == {"win_now": "Win-now piece", "cornerstone": "Cornerstone",
                                "rebuild": "Rebuild piece"}
    assert tn.SEASON_LINE_SEPARATOR == " · "        # PRD §3's line; the one non-ASCII glyph
    assert not set(tn.SEASON_FIT_TEMPLATES) & set(tn.FIT_TEMPLATES)
    # test_fit_block_v3's lint, extended: no exclamation, no praise, ASCII, and (copy
    # rule 5) no engine name or version.
    for text in [*tn.FIT_TEMPLATES.values(), *tn.SEASON_FIT_TEMPLATES.values(),
                 *tn.SEASON_TEMPLATES.values(), *tn.SEASON_LABELS.values()]:
        low = text.lower()
        assert "!" not in text and "good fit" not in low and text.isascii()
        assert not any(w in low for w in ("revision", "owner-v2", "bilateral", "season-signal", "engine"))
