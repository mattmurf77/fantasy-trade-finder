"""Offer-learnings WS8 — revised-offer cards for declined offers.

Scope block: docs/plans/offer-learnings/scope-revised-offer-cards.md

Synthetic boards and synthetic outcome rows only; every eligibility claim is
the engine evaluator's own (`bakeoff_runner.owner_evaluator`). Covers:

  * the generator: `swap_in_give` (same size, the asked-for pieces kept, one
    offered piece swapped for a slightly more valuable one inside 5-15%, the
    smallest step wins; untouchables and viewer-check failures never offered;
    nothing when no piece qualifies); the declined path uses only the swap,
    and WS5's default kinds are unchanged; `propose_middle_ground` (shared
    assets kept, about half of the gap, neither version itself, nothing
    without a positive gap, untouchables never added, flag off no work);
  * the card builder: a card for each trigger (declined; countered and the
    counter declined; sent through the app or imported) and none for pending,
    accepted, withdrawn, lapsed, a counter pending / accepted / withdrawn /
    lapsed / countered back, a received offer, another user's offer, an old
    decline, FAAB; once only (the same terms re-served, never rebuilt; a pass
    or like retires it; a "none" is never retried; a moved asset retires it);
    never a revision of a revision; cap and newest-first order; flag off reads
    nothing;
  * the copy: deterministic, says what changed, guesses no reason;
  * the deck: the real worker with the owner arm serving puts the card first,
    with a public `revised_offer` and frozen features naming it, and nothing
    with the flag off;
  * revoking the import consent deletes cards built from imported offers.
"""
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select

from backend import bakeoff_runner as bo, database as db, feature_flags as ff
from backend import trade_narrative as tn, trade_next_move as nm
from backend import trade_revised_offers as ro, trade_service as ts
from backend.database import metadata
from backend.tests.test_bilateral_contracts import world
from backend.tests.test_outlook_evidence_candidate import qualified

LEAGUE = "synthetic_bilateral"
NOW = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
ARMS = {
    "owner-v1": {},
    "bilateral-1": {"owner_bilateral_enabled": 1.},
    "bilateral-2": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.},
    "bilateral-3": {"owner_bilateral_enabled": 1., "owner_bilateral_revision_enabled": 1.,
                    "owner_outlook_evidence_enabled": 1.},
}
# At the engine's package pricing a 1000-for-1150 offer gains the other
# manager ~7% of the trade when `give` becomes `up1`, ~10% for `up2`, ~26%
# for `up3`; adding `mid` gains ~15%, adding `half` about half of that.
MARKET = {"give": 1000., "target": 1150., "target2": 1160., "up1": 1080., "up2": 1110.,
          "up3": 1300., "mid": 300., "half": 200., "small": 60., "q": 260., "near": 970.}
VIEWER = {"give": 800., "target": 1400., "target2": 1410., "up1": 860., "up2": 880.,
          "up3": 1040., "mid": 250., "half": 160., "small": 50., "q": 210., "near": 780.}
PARTNER = {"give": 1350., "target": 900., "target2": 905., "up1": 1450., "up2": 1500.,
           "up3": 1750., "mid": 380., "half": 250., "small": 70., "q": 330., "near": 1310.}
OWN = ("give", "up1", "up2", "up3", "mid", "half", "small")


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", {**ff.DEFAULT_FLAGS, nm.FLAG: True})
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)


def context(arm="owner-v1", own=OWN, other=("target", "target2"), viewer=VIEWER, **extra):
    args = world(own=own, other=other, market=MARKET, viewer=viewer, partner=PARTNER,
                 config=dict(ARMS[arm]), **extra)
    return qualified(args) if arm == "bilateral-3" else args


def card(give=("give",), receive=("target",)):
    return ts.TradeCard("", LEAGUE, "viewer", "partner", "Partner", list(give), list(receive), 0, 0, 0)


def evaluate(ctx, give, receive):
    return bo.owner_evaluator(ctx["config"])([card(give, receive)], **{**ctx, **nm._ORGANIC})[0]


def swap(ctx, offer=None):
    return nm.propose_revision(offer or card(), ctx, step_min=nm.SWAP_STEP_MIN,
                               step_max=nm.SWAP_STEP_MAX, kinds=(nm.SWAP,))


# ---------------------------------------------------------------------------
# The swap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("arm", ARMS)
def test_swap_keeps_the_size_and_the_ask_and_takes_one_slight_step(arm):
    ctx = context(arm)
    move = swap(ctx)
    if move is None:
        pytest.skip(f"{arm}: no swap in band on this board")
    c, proof = move.card, move.proof
    assert proof.eligible and proof.matches(c)
    assert move.change["kind"] == nm.SWAP
    assert c.receive_player_ids == ["target"]                       # the ask kept
    assert len(c.give_player_ids) == 1                              # same size
    assert c.give_player_ids == [move.change["asset_id"]]
    assert move.change["replaces"] == "give"
    assert MARKET[move.change["asset_id"]] > MARKET["give"]         # more valuable
    assert nm.SWAP_STEP_MIN <= move.step_fraction <= nm.SWAP_STEP_MAX


def test_the_smallest_slight_step_wins():
    move = swap(context())
    assert move.change == {"kind": nm.SWAP, "asset_id": "up1", "replaces": "give"}
    assert move.card.give_player_ids == ["up1"]
    without = swap(context(own=("give", "up2", "up3", "mid", "half", "small")))
    assert without.change["asset_id"] == "up2" and without.step_fraction > move.step_fraction


def test_a_big_step_or_no_better_piece_gives_nothing():
    ctx = context(own=("give", "up3", "mid", "small"))
    assert evaluate(ctx, ["up3"], ["target"]).eligible               # valid, but ~26%
    assert swap(ctx) is None
    assert swap(context(own=("give", "mid", "half", "small"))) is None


def test_the_declined_path_never_adds_or_drops_a_piece():
    ctx = context(own=("give", "mid", "half", "small"))
    # WS5's default kinds would add `mid`; the swap-only path offers nothing.
    assert nm.propose_revision(card(), ctx).change == {"kind": "add_to_give", "asset_id": "mid"}
    assert swap(ctx) is None
    # A two-piece ask keeps both pieces: the swap never drops one.
    two = swap(context(), card(receive=("target", "target2")))
    assert two is None or (two.change["kind"] == nm.SWAP
                           and sorted(two.card.receive_player_ids) == ["target", "target2"])


def test_default_kinds_are_unchanged_with_a_swap_available():
    move = nm.propose_revision(card(), context())
    assert move.change == {"kind": "add_to_give", "asset_id": "mid"}
    # Even where the swap (up1, ~7%) would be the smallest step, the default
    # kinds never offer it.
    wide = nm.propose_revision(card(), context(), step_min=.05)
    assert wide.change["kind"] in nm.DEFAULT_KINDS and "replaces" not in wide.change


def test_a_swap_is_always_to_a_more_valuable_piece():
    # With the band opened below zero, a cheaper piece would be the smallest
    # "step"; the swap still only ever moves up in value.
    ctx = context(own=OWN + ("near",))
    assert evaluate(ctx, ["near"], ["target"]).eligible        # a cheaper, valid swap exists
    move = nm.propose_revision(card(), ctx, step_min=-1., step_max=1., kinds=(nm.SWAP,))
    assert MARKET[move.change["asset_id"]] > MARKET[move.change["replaces"]]


def test_an_untouchable_is_never_swapped_in():
    ctx = context(manager_preferences={"viewer": {"untouchables": ["up1"]}})
    assert swap(ctx).change["asset_id"] == "up2"


def test_a_swap_that_fails_the_viewers_own_checks_is_never_offered():
    ctx = context(viewer={**VIEWER, "up1": 5000.})
    assert not evaluate(ctx, ["up1"], ["target"]).eligible
    assert swap(ctx).change["asset_id"] == "up2"


def test_swap_flag_off_does_no_work(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(bo, "owner_evaluator", lambda *a, **k: pytest.fail("evaluated"))
    assert swap(context()) is None


# ---------------------------------------------------------------------------
# The middle ground
# ---------------------------------------------------------------------------

def middle(ctx, counter_give=("give", "mid"), counter_receive=("target",), original=None):
    return nm.propose_middle_ground(original or card(), card(counter_give, counter_receive), ctx)


def _net(ctx, give, receive):
    m = evaluate(ctx, give, receive).as_dict()["market"]
    return m["give"] - m["receive"]


def test_middle_ground_keeps_the_shared_assets_and_meets_about_half_way():
    ctx = context()
    move = middle(ctx)
    assert move is not None and move.change["kind"] == "middle_ground"
    c = move.card
    assert "give" in c.give_player_ids and c.receive_player_ids == ["target"]
    assert move.proof.eligible and move.proof.matches(c)
    assert (sorted(c.give_player_ids), c.receive_player_ids) not in (
        (["give"], ["target"]), (["give", "mid"], ["target"]))
    n0, n1 = _net(ctx, ["give"], ["target"]), _net(ctx, ["give", "mid"], ["target"])
    moved = (_net(ctx, c.give_player_ids, c.receive_player_ids) - n0) / (n1 - n0)
    assert nm.MIDDLE_BAND[0] <= moved <= nm.MIDDLE_BAND[1]
    assert move.change["gap_share"] == pytest.approx(moved, abs=1e-4)
    assert move.change["added_give"] == sorted(set(c.give_player_ids) - {"give"})
    assert move.change["removed_give"] == [] and move.change["removed_receive"] == []


def test_no_middle_ground_when_the_counter_asked_for_less():
    assert middle(context(), counter_give=("give",), counter_receive=("target", "small")) is None
    # A "counter" that asks the user for less than the original: a negative
    # gap, so no card, even though a package sits half way between them.
    assert middle(context(), counter_give=("give",), original=card(["give", "mid"])) is None


def test_middle_ground_takes_the_candidate_closest_to_half():
    ctx = context(own=OWN + ("q",))
    move = nm.propose_middle_ground(card(), card(["give", "mid"]), ctx, band=(0., 1.))
    n0, n1 = _net(ctx, ["give"], ["target"]), _net(ctx, ["give", "mid"], ["target"])
    q = (_net(ctx, ["give", "q"], ["target"]) - n0) / (n1 - n0)
    assert evaluate(ctx, ["give", "q"], ["target"]).eligible and 0 < q < 1 and abs(q - .5) > .1
    assert move.change["added_give"] == ["half"]


def test_middle_ground_never_adds_an_untouchable():
    first = middle(context())
    added = first.change["added_give"]
    ctx = context(manager_preferences={"viewer": {"untouchables": added}})
    again = middle(ctx)
    assert again is None or not set(again.change["added_give"]) & set(added)


def test_middle_ground_flag_off_does_no_work(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(bo, "owner_evaluator", lambda *a, **k: pytest.fail("evaluated"))
    assert middle(context()) is None


def test_middle_ground_needs_a_small_difference():
    many = tuple(f"x{i}" for i in range(nm.MIDDLE_MAX_POOL + 1))
    ctx = context(own=OWN + many)
    for pid in many:
        ctx["players"][pid] = ctx["players"]["small"].__class__(pid, pid, "WR", "TST", 26)
        ctx["seed_elo"][pid] = ts.value_to_elo(40.)
    assert middle(ctx, counter_give=("give",) + many) is None


# ---------------------------------------------------------------------------
# The card builder
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    yield eng
    eng.dispose()


_TX = iter(range(10 ** 6))


def outcome(status="declined", *, give=("give",), receive=("target",), user="viewer",
            at=NOW - timedelta(hours=2), counter_status=None, counter=None, source="app",
            direction="sent", extras=None, league=LEAGUE):
    tx = f"tx-{next(_TX)}"
    db.save_trade_offer_outcome({
        "user_id": user, "league_id": league, "provider": "sleeper",
        "provider_transaction_id": tx, "my_roster_id": 1, "their_roster_id": 2,
        "give_asset_ids": json.dumps(list(give)), "receive_asset_ids": json.dumps(list(receive)),
        "sent_at": (at - timedelta(days=1)).isoformat(), "status": status,
        "status_at": at.isoformat(), "source": source, "direction": direction,
        "counter_status": counter_status,
        "counter_status_at": (at + timedelta(minutes=30)).isoformat() if counter_status else None,
        "counter_terms_json": json.dumps({"give_asset_ids": list(counter[0]),
                                          "receive_asset_ids": list(counter[1])}) if counter else None,
        "extras_json": json.dumps(extras) if extras else None,
    })
    return next(r for r in db.load_user_trade_offer_outcomes(user, league, "sleeper")
                if r["provider_transaction_id"] == tx)["id"]


def build(ctx=None, **kw):
    return ro.build(user_id="viewer", league_id=LEAGUE, context=ctx or context(),
                    name=lambda pid: pid.upper(), now=NOW, **kw)


def stored():
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(db.revised_offer_cards_table).order_by(db.revised_offer_cards_table.c.id))]


def test_a_declined_offer_gets_one_revised_card(engine):
    oid = outcome()
    [c] = build()
    assert c.give_player_ids == ["up1"] and c.receive_player_ids == ["target"]
    assert c.target_user_id == "partner" and c.injected is True
    assert c.owner_evaluation.eligible and c.owner_evaluation.matches(c)
    row = stored()[0]
    assert c.trade_id == f"revised_{row['id']}"
    assert c.revised_offer == {
        "kind": "revision", "version": ro.VERSION, "card_id": row["id"], "outcome_id": oid,
        "source": "app", "step_fraction": round(row["step_fraction"], 4),
        "line": "Your offer for TARGET was declined. Another idea: UP1 in place of GIVE."}
    assert (row["status"], row["kind"], json.loads(row["give_asset_ids"])) == ("active", "revision", ["up1"])


def test_a_declined_counter_gets_a_middle_ground(engine):
    outcome("countered", counter_status="declined", counter=(("give", "mid"), ("target",)))
    [c] = build()
    assert c.revised_offer["kind"] == "middle_ground"
    assert "give" in c.give_player_ids and c.receive_player_ids == ["target"]
    assert c.revised_offer["line"].startswith(
        "You turned down their counter to your offer for TARGET. A middle ground: add ")


def test_an_imported_offer_sent_in_sleeper_also_gets_a_card(engine):
    outcome(source="sleeper_import")
    [c] = build()
    assert c.revised_offer["source"] == "sleeper_import"


@pytest.mark.parametrize("status,counter_status", [
    ("sent", None), ("accepted", None), ("withdrawn", None), ("lapsed", None),
    ("completed_different_terms", None), ("countered", "pending"), ("countered", "accepted"),
    ("countered", "withdrawn"), ("countered", "lapsed"), ("countered", "countered"),
])
def test_no_card_unless_declined_or_the_counter_declined(engine, status, counter_status):
    outcome(status, counter_status=counter_status,
            counter=(("give", "mid"), ("target",)) if counter_status else None)
    assert build() == [] and stored() == []


@pytest.mark.parametrize("why,kwargs", [
    ("a received offer", {"direction": "received"}),
    ("another user's offer", {"user": "someone-else"}),
    ("a decline older than the window", {"at": NOW - timedelta(days=ro.SOURCE_WINDOW_DAYS + 1)}),
    ("FAAB in the offer", {"extras": {"give_faab": 5}}),
    ("another league", {"league": "other-league"}),
])
def test_no_card_for(engine, why, kwargs):
    outcome(**kwargs)
    assert build() == [], why


def test_once_only_the_same_card_comes_back_and_is_never_rebuilt(engine):
    outcome()
    first = build()[0]
    # A cheaper in-band piece now exists; the stored card does not change.
    ctx = context(own=OWN + ("cheap",))
    ctx["players"]["cheap"] = ctx["players"]["small"].__class__("cheap", "cheap", "WR", "TST", 26)
    ctx["seed_elo"]["cheap"] = ts.value_to_elo(1060.)
    again = build(ctx)[0]
    assert (again.give_player_ids, again.trade_id) == (first.give_player_ids, first.trade_id)
    assert len(stored()) == 1


@pytest.mark.parametrize("decision", ["pass", "like"])
def test_acting_on_the_card_retires_it_for_good(engine, decision):
    outcome()
    c = build()[0]
    acted = context(past_decision_keys={(frozenset(c.give_player_ids), frozenset(c.receive_player_ids))})
    assert build(acted) == []
    assert (stored()[0]["status"], stored()[0]["retired_reason"]) == ("retired", "acted")
    assert build() == []                                            # never rebuilt


def test_a_card_that_no_longer_passes_is_retired(engine):
    outcome()
    build()
    assert build(context(own=("give", "up2", "mid"))) == []        # `up1` traded away
    assert stored()[0]["retired_reason"] == "unavailable"
    assert build() == []


def test_no_proven_card_is_recorded_once_and_never_retried(engine):
    outcome()
    assert build(context(own=("give", "mid", "small"))) == []
    assert stored()[0]["status"] == "none"
    assert build() == []                                            # up1 is back; still nothing


def test_never_a_revision_of_a_revision(engine):
    outcome(at=NOW - timedelta(days=3))
    c = build()[0]
    sent_back = context(past_decision_keys={(frozenset(c.give_player_ids),
                                             frozenset(c.receive_player_ids))})
    # The user sent the card; it was declined too.
    outcome(give=tuple(c.give_player_ids), at=NOW - timedelta(hours=1))
    assert build(sent_back) == []
    assert len(stored()) == 1


def test_cap_newest_decline_first_and_no_duplicate_card(engine):
    oldest = outcome(at=NOW - timedelta(days=5))                     # give -> target
    second = outcome(receive=("target2",), at=NOW - timedelta(days=4))
    middle_id = outcome("countered", counter_status="declined",
                        counter=(("give", "mid"), ("target",)), at=NOW - timedelta(days=3))
    newest = outcome(at=NOW - timedelta(days=1))                     # same terms as `oldest`
    assert [c.revised_offer["outcome_id"] for c in build(cap=2)] == [newest, middle_id]
    cards = build()
    assert [c.revised_offer["outcome_id"] for c in cards] == [newest, middle_id, second]
    assert len(cards) == ro.CAP
    # A fourth source exists; it would repeat the newest card's package, and
    # the cap holds either way.
    more = outcome(receive=("target2",), give=("give",), at=NOW - timedelta(hours=1))
    cards = build()
    assert len(cards) == ro.CAP and cards[0].revised_offer["outcome_id"] == more
    assert oldest not in [c.revised_offer["outcome_id"] for c in cards]
    # Uncapped, the two offers that yield the same package still show it once.
    cards = build(cap=10)
    keys = [(tuple(c.give_player_ids), tuple(c.receive_player_ids)) for c in cards]
    assert len(keys) == len(set(keys)) == 3


def test_flag_off_reads_nothing(engine, monkeypatch):
    outcome()
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(db, "load_user_trade_offer_outcomes",
                        lambda *a, **k: pytest.fail("read with the flag off"))
    assert build() == []


def test_revoking_the_import_deletes_cards_built_from_imports(engine):
    outcome(source="sleeper_import")
    build()
    app_id = outcome(give=("up2",), at=NOW - timedelta(hours=1))
    build()
    assert {r["outcome_id"] for r in stored()} >= {app_id}
    db.withdraw_offer_import_consent("viewer", "v", NOW.isoformat())
    assert [r["outcome_id"] for r in stored()] == [app_id]


# ---------------------------------------------------------------------------
# The copy
# ---------------------------------------------------------------------------

def test_the_lines_say_what_changed_and_guess_no_reason():
    name = {"a": "Alpha", "b": "Bravo", "c": "Charlie", "p": "2027 1st"}.get
    rev = tn.revised_offer_line("revision", original_give=["a"], original_receive=["b", "c"],
                                give=["p"], receive=["b", "c"], name=name)
    assert rev == ("Your offer for Bravo and Charlie was declined. "
                   "Another idea: 2027 1st in place of Alpha.")
    mid = tn.revised_offer_line("middle_ground", original_give=["a"], original_receive=["b", "c"],
                                give=["a", "p"], receive=["b"], name=name)
    assert mid == ("You turned down their counter to your offer for Bravo and Charlie. "
                   "A middle ground: add 2027 1st and no longer ask for Charlie.")
    for line in (rev, mid):
        assert not any(w in line.lower() for w in ("because", "why", "probably", "likely", "they want"))


# ---------------------------------------------------------------------------
# The deck: the real worker, owner arm serving
# ---------------------------------------------------------------------------

from backend import server  # noqa: E402
from backend.tests.test_owner_generator_routes import (  # noqa: E402,F401
    harness, owner_harness, rows, worker, ME, LEAGUE as H_LEAGUE)
from backend.tests.test_owner_only_routes import exclusive  # noqa: E402,F401
from backend.tests.test_fair_packages import OPP  # noqa: E402


def _seed_declined(engine):
    db.save_trade_offer_outcome({
        "user_id": ME, "league_id": H_LEAGUE, "provider": "sleeper",
        "provider_transaction_id": "tx-deck", "my_roster_id": 1, "their_roster_id": 2,
        "give_asset_ids": json.dumps(["a2"]), "receive_asset_ids": json.dumps(["b1"]),
        "sent_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "status": "declined", "status_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "source": "app", "direction": "sent"})


def _real_proof_builder(monkeypatch):
    """The real builder, with the one revision fixed to a package the
    harness's evaluator proves (a1 for b1), so the deck test does not depend
    on the harness board's step sizes."""
    def build_move(league_id, src, context, member):
        c = ro._card(league_id, context, member, ["a1"], src["receive"])
        proof = bo.owner_evaluator(dict(context.get("config") or {}))(
            [c], **{**context, **nm._ORGANIC})[0]
        if not proof.eligible:
            return None
        m = proof.as_dict()["market"]
        c.give_value, c.receive_value, c.fairness_score = m["give"], m["receive"], m["ratio"]
        c.owner_evaluation = proof
        return ro._Built(c, proof, {"kind": nm.SWAP, "asset_id": "a1", "replaces": "a2"}, .1)
    monkeypatch.setattr(ro, "_build_move", build_move)


def test_the_worker_serves_the_revised_card_first_and_freezes_its_features(exclusive, monkeypatch):
    client, engine, sess, service, league = exclusive
    ff._flags_cache[nm.FLAG] = True
    _seed_declined(engine)
    _real_proof_builder(monkeypatch)
    job = worker(exclusive, monkeypatch)
    first = job["cards"][0]
    assert first["trade_id"].startswith("revised_")
    assert first["revised_offer"] == {
        "kind": "revision",
        "line": "Your offer for B1 was declined. Another idea: A1 in place of A2."}
    assert [c["trade_id"] for c in job["cards"]].count(first["trade_id"]) == 1
    imp = next(r for r in rows(engine, db.deck_impressions_table)
               if r["impression_id"] == first["impression_id"])
    features = json.loads(imp["features_json"]) if isinstance(imp["features_json"], str) else imp["features_json"]
    if "revised_offer" not in (features or {}):
        features = db.load_deck_diagnostics(imp["impression_id"], imp["user_id"]) or {}
    assert features["revised_offer"]["kind"] == "revision"
    assert features["revised_offer"]["version"] == ro.VERSION
    assert "line" not in features["revised_offer"]
    assert imp["card_index"] == 0 and imp["valuation_json"]


def test_a_revised_card_shares_the_jobs_fit_block_context(exclusive, monkeypatch):
    # Integration of WS8 with the fit block (WS4b): a revised-offer card is
    # composed with the job's one league context, like every owner card.
    client, engine, sess, service, league = exclusive
    ff._flags_cache[nm.FLAG] = True
    ff._flags_cache["trade.fit_first_copy"] = True
    _seed_declined(engine)
    _real_proof_builder(monkeypatch)
    from backend import trade_narrative as tn
    seen, real = {}, tn.fit_block
    def spy(proof, card, players, context):
        seen[card.trade_id] = context
        return real(proof, card, players, context)
    monkeypatch.setattr(tn, "fit_block", spy)
    job = worker(exclusive, monkeypatch)
    first = job["cards"][0]
    assert first["trade_id"].startswith("revised_") and first["revised_offer"]["kind"] == "revision"
    assert seen.get(first["trade_id"]) is not None
    assert len(seen) > 1 and len({id(context) for context in seen.values()}) == 1


def test_the_worker_with_the_flag_off_adds_nothing(exclusive, monkeypatch):
    client, engine, sess, service, league = exclusive
    ff._flags_cache[nm.FLAG] = False
    _seed_declined(engine)
    monkeypatch.setattr(db, "load_user_trade_offer_outcomes",
                        lambda *a, **k: pytest.fail("read with the flag off"))
    job = worker(exclusive, monkeypatch)
    assert job["cards"]
    assert not any("revised_offer" in c or c["trade_id"].startswith("revised_") for c in job["cards"])
    assert rows(engine, db.revised_offer_cards_table) == []
    for r in rows(engine, db.deck_impressions_table):
        assert "revised_offer" not in json.dumps(r["features_json"], default=str)


def test_no_production_module_imports_the_builder_but_the_server_helper():
    import re
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    pat = re.compile(r"^\s*(from\s+\S*trade_revised_offers\s+import|from\s+\S+\s+import\s+[^#\n]*"
                     r"\btrade_revised_offers\b|import\s+[^#\n]*\btrade_revised_offers\b)", re.M)
    users = sorted(p.relative_to(repo).as_posix() for p in (repo / "backend").rglob("*.py")
                   if "tests" not in p.parts and p.name != "trade_revised_offers.py"
                   and pat.search(p.read_text()))
    assert users == ["backend/server.py"]
