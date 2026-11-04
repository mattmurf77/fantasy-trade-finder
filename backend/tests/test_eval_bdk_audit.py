"""backend.eval.bdk_audit, the B-DK-4..7 production audit (models-lead-launch.md
addendum C §C5): each rule with a violating and a clean card, read from the
filter's own inputs (models-lead D2: the pack's run["filter_inputs"], #492),
B-DK-6 reproducing the filter on the recorded holdings, a deck's record
states, protection from the record (or, without one, each recorded flag), a
repeat breach of protected cards only reported as explained, the repeat window by
displayed position, the U6 audit set (a viewed card past the window audited,
an unviewed one not, "viewed" from outcomes, never a row), a viewed card with
no full row reported by its upgrade_miss_cards cause (`other` when absent),
the not-auditable paths never reading as 0, skipped decks, the
no-threshold-literal source check, each exit status, the read-only guard, and
that the module never imports backend.server.

In-memory SQLite DBs built with the v5 tests' helpers; the CLI tests write the
same tables to a temporary file and read it through flip_read's read-only
engine.
"""

import ast
import json
import re
import subprocess
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, insert, text

import backend.deck_quality as dq
import backend.eval.bdk_audit as ba
import backend.eval.flip_read as fr
from backend.eval import data as eval_data
from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval.bdk_audit import (
    FAIL, INCOMPLETE, NOT_AUDITABLE, PASS, ReadOnlyViolation, audit, main, render,
)
from backend.eval.contract import REDACTED_PARTNER_PREFIX, card_impression_id
from backend.tests.test_eval_pack_reader import SERVED, _card, _deck_cards, _row, pack_table
from backend.tests.test_eval_withdrawals_and_paging import (
    DB, _after, act, make_db, put_pack, withdraw, withdrawals_table,
)

REPO = Path(__file__).resolve().parents[2]
SINCE = "2026-10-23T00:00:00+00:00"
AS_OF = _after(2)
W, CAP = dq.REPEAT_WINDOW, dq.REPEAT_CAP

# Market values from deck_quality's own thresholds: a clean pair is HEAD for
# HEAD; LOW breaks a HEAD piece up but is no filler; FILL is filler.
HEAD = 2000.0
LOW = HEAD * dq.BREAKUP_MIN_RATIO * 0.9
FILL = dq.FILLER_FLOOR / 2


def shape(rule, job, i):
    """(give, receive) {asset id: market} for a card tripping `rule` (None: clean)."""
    g, r = f"{job}-g{i}", f"{job}-r{i}"
    return {"breakup": ({g: HEAD}, {r: LOW}),
            "filler": ({g: HEAD}, {r: HEAD, f"{job}-f{i}": FILL}),
            None: ({g: HEAD}, {r: HEAD})}[rule]


def row(job, i, give=None, receive=None, *, valuation="policy", source_like=None,
        full=True, **features):
    """A served deck_impressions row at card_index i: assets_json from the give /
    receive maps (full=False: none, as a packed card's upgrade miss writes),
    valuation_json in the personal-market snapshot's shape ("policy"), the
    value core's ("value_core") or none (None), `features` merged into
    features_json, and the source_like_impression_id column. The audit never
    reads valuation_json (D2 (c)); deck(record=...) records its values as
    the filter's market."""
    if give is None:
        give, receive = shape(None, job, i)
    sides = {"give": give, "receive": receive}
    val = ({"assets": {s: [{"id": a, "market_value": v} for a, v in m.items()]
                       for s, m in sides.items()}} if valuation == "policy"
           else {"assets": [{"id": a, "side": s, "market": v} for s, m in sides.items()
                            for a, v in m.items()]} if valuation == "value_core" else None)
    return {**_row({**_card(job, i), **features}),
            "assets_json": json.dumps({s: list(m) for s, m in sides.items()}) if full else None,
            "valuation_json": json.dumps(val) if full and val else None,
            "source_like_impression_id": source_like}


def with_x(job, i, **kw):
    """A clean card that also gives asset X."""
    return row(job, i, {f"{job}-g{i}": HEAD, "X": HEAD}, {f"{job}-r{i}": HEAD}, **kw)


def filter_record(market: dict, *, positions=None, **over) -> dict:
    """run["filter_inputs"] as #492 writes it: `market`, each asset a WR
    unless `positions` says otherwise, no QB/TE holdings, no lineup, nothing
    protected; `over` replaces any field."""
    return {"v": 1, "filter_ran": True, "viewer_team": "u1", "lineup_slots": None,
            "market": dict(market),
            "position": {**dict.fromkeys(market, "WR"), **(positions or {})},
            "qb_te": {}, "protected": [], **over}


def deck(db: DB, job, n, special=None, *, skip=(), viewed=(), served_at=SERVED, record=None,
         deliveries=None):
    """Rows for 0..n-1 not in `skip`: a clean card unless `special` maps the
    index to a row; a viewed outcome per index in `viewed`. `record` (a dict
    of filter_record keywords; {} for none): also a pack of all n cards,
    delivered, whose run["filter_inputs"] records the rows' markets (the
    values their valuation_json shows)."""
    special = special or {}
    rows = [special.get(i) or row(job, i) for i in range(n) if i not in skip]
    for r in rows:
        r["served_at"] = served_at
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp), rows)
    for i in viewed:
        act(db, job, i, "viewed", at=served_at)
    if record is not None:
        record = dict(record)
        market = record.pop("market", None)
        if market is None:
            market = {a: v for r in rows for a, v in eval_data.valuation_markets(
                eval_data._json_dict(r.get("valuation_json"))).items()}
        put_pack(db, job, _deck_cards(job, n), card_count=n,
                 deliveries=deliveries or [[n - 1, served_at]],
                 served_at=served_at, filter_inputs=filter_record(market, **record))


def th(i) -> str:
    """The trade_hash of the test cards at card_index i (test_eval_pack_reader._card)."""
    return f"{i:016x}"


def run(db: DB, **kw):
    return audit(db.eng, since=kw.pop("since", SINCE), as_of=AS_OF, **kw)


# ---------------------------------------------------------------------------
# The per-card rules (B-DK-4, B-DK-5), on the filter's recorded inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule, other", [("breakup", "filler"), ("filler", "breakup")])
def test_each_value_rule_counts_a_violating_card_and_passes_a_clean_one(rule, other):
    give, receive = shape(rule, "d", 1)
    rule_fn = {"breakup": dq._breakup, "filler": dq._filler}
    assert rule_fn[rule](list(give), list(receive), {**give, **receive}.get)
    assert not rule_fn[other](list(give), list(receive), {**give, **receive}.get)
    db = make_db()
    deck(db, "d", 3, {1: row("d", 1, give, receive)}, record={})
    r = run(db)
    hit, miss = r.rules[rule], r.rules[other]
    assert (hit["violations"], hit["audited"], hit["not_auditable"], hit["status"]) == (
        1, 3, 0, FAIL)
    assert hit["examples"] == [{"deck_job_id": "d", "card_index": 1, "position": 1,
                                "trade_hash": th(1)}]
    assert (miss["violations"], miss["audited"], miss["status"]) == (0, 3, PASS)
    assert r.overall == FAIL and hit["bdk"] == {"breakup": "B-DK-4", "filler": "B-DK-5"}[rule]
    assert r.filter_inputs == {"recorded": 1}
    assert f"| {hit['bdk']} | {rule}: " in render(r)


@pytest.mark.parametrize("recorded, expected", [("clean", 0), ("breakup", 1)])
def test_the_record_is_read_never_valuation_json(recorded, expected):
    """release-lead's #492 QA: valuation_json's approximate market read false
    FAILs. A card whose valuation_json shows a breakup is judged on the
    filter's recorded market, and the other way round."""
    db = make_db()
    shown = "breakup" if recorded == "clean" else None
    g, r_ = shape(shown, "d", 0)
    rec_g, rec_r = shape(None if recorded == "clean" else "breakup", "d", 0)
    deck(db, "d", 1, {0: row("d", 0, g, r_)}, record={"market": {**rec_g, **rec_r}})
    t = run(db).rules["breakup"]
    assert (t["violations"], t["audited"]) == (expected, 1)


def test_a_recorded_deck_takes_protection_from_the_record():
    """The filter's protected trade_hashes exempt a card; a protection flag
    on the served row that the filter didn't see (owner_published is set
    after it) exempts nothing."""
    db = make_db()
    deck(db, "p", 2, {1: row("p", 1, *shape("breakup", "p", 1))},
         record={"protected": [th(1)]})
    deck(db, "f", 2, {1: row("f", 1, *shape("breakup", "f", 1), likes_you=True)}, record={})
    t = run(db).rules["breakup"]
    assert (t["violations"], t["protected"], t["audited"]) == (1, 1, 3)
    assert [e["deck_job_id"] for e in t["examples"]] == ["f"]


@pytest.mark.parametrize("flag", [{"likes_you": True}, {"standing_offer": True},
                                  {"wildcard": True}, {"source_like": "other-card:0"}],
                         ids=["likes_you", "standing_offer", "wildcard", "source_like"])
def test_without_a_record_each_row_flag_still_protects(flag):
    """A deck without a record: each protection the served row records
    exempts its card; its other cards are not auditable for B-DK-4..6."""
    db = make_db()
    deck(db, "p", 2, {1: row("p", 1, *shape("breakup", "p", 1), **flag)})
    for name in ("breakup", "filler", "redundant"):
        t = run(db).rules[name]
        assert (t["violations"], t["protected"], t["not_auditable"], t["audited"]) == (
            None, 1, 1, 0)


# ---------------------------------------------------------------------------
# B-DK-6: the recorded holdings and lineup
# ---------------------------------------------------------------------------

# The viewer (u1) holds a TE and a QB worth HEAD; opp1 holds a QB worth HEAD.
# The lineup starts one QB and one TE, so the caps are 1 and 1.
LINEUP = ["QB", "RB", "WR", "TE", "FLEX", "BN"]
HOLDINGS = {"u1": ["myTE", "myQB"], "opp1": ["oppQB"]}
POSITIONS = {"myTE": "TE", "myQB": "QB", "oppQB": "QB", "inTE": "TE"}


def test_redundant_reads_the_viewer_and_counterparty_holdings():
    db = make_db()
    special = {1: row("d", 1, {"wr1": HEAD}, {"inTE": HEAD}),
               2: row("d", 2, {"myTE": HEAD}, {"inTE": HEAD}),
               4: row("d", 4, {"myQB": HEAD}, {"rb4": HEAD})}
    market = {**{a: v for i in (0, 3) for side in shape(None, "d", i) for a, v in side.items()},
              "wr1": HEAD, "inTE": HEAD, "myTE": HEAD, "myQB": HEAD, "rb4": HEAD, "oppQB": HEAD}
    deck(db, "d", 5, special, record={"market": market, "lineup_slots": LINEUP,
                                      "qb_te": HOLDINGS, "positions": POSITIONS})
    t = run(db).rules["redundant"]
    assert (t["violations"], t["audited"], t["status"]) == (2, 5, FAIL)
    assert [e["card_index"] for e in t["examples"]] == [1, 4]


def test_the_recorded_holdings_reproduce_the_filter_on_full_rosters():
    """_redundant_side reads only QB/TE holdings, so the record's qb_te gives
    the filter's own verdict: on every card of a grid, filter_deck's drop of
    a redundant card equals the audit's check on the recorded subset."""
    positions = {"q1": "QB", "q2": "QB", "t1": "TE", "t2": "TE", "w1": "WR", "r1": "RB",
                 "inQ": "QB", "inT": "TE", "inW": "WR"}
    values = [HEAD, HEAD * dq.REDUNDANT_MIN_RATIO * 0.9, None]
    rosters = {"me": ["q1", "t1", "w1", "r1"], "opp": ["q2", "t2", "w1"]}
    qb_te = {team: [a for a in held if positions[a] in ("QB", "TE")]
             for team, held in rosters.items()}
    caps = dq.position_caps(LINEUP)
    checked = 0
    for value in values:
        market = {a: value if a in ("q1", "t1", "q2", "t2") else HEAD for a in positions}
        for give, receive in ((["w1"], ["inT"]), (["t1"], ["inT"]), (["q1"], ["inQ"]),
                              (["w1"], ["inW"]), (["q2"], ["w1"]), (["inQ"], ["r1"])):
            card = types.SimpleNamespace(give_player_ids=give, receive_player_ids=receive,
                                         target_user_id="opp")
            kept, counts = dq.filter_deck([card], viewer_id="me", market=market.get,
                                          position=positions.get, rosters=rosters,
                                          lineup_slots=LINEUP)
            audit_says = (dq._redundant_side(qb_te["me"], give, receive, market.get,
                                             positions.get, caps)
                          or dq._redundant_side(qb_te["opp"], receive, give, market.get,
                                                positions.get, caps))
            assert audit_says == (counts["redundant"] == 1), (value, give, receive)
            checked += audit_says
    assert checked >= 2                      # the grid has redundant cards


def test_an_unknown_lineup_means_the_filter_skipped_redundant_a_pass():
    db = make_db()
    special = {1: row("d", 1, {"wr1": HEAD}, {"inTE": HEAD})}
    market = {**{a: v for i in (0, 2) for side in shape(None, "d", i) for a, v in side.items()},
              "wr1": HEAD, "inTE": HEAD}
    deck(db, "d", 3, special, record={"market": market, "lineup_slots": None,
                                      "qb_te": HOLDINGS, "positions": POSITIONS})
    t = run(db).rules["redundant"]
    assert (t["violations"], t["audited"], t["status"]) == (0, 3, PASS)


# ---------------------------------------------------------------------------
# A deck's record state
# ---------------------------------------------------------------------------

def _pack_with(db, job, n, **run):
    put_pack(db, job, _deck_cards(job, n), card_count=n, deliveries=[[n - 1, SERVED]], **run)


@pytest.mark.parametrize("pack, state", [
    (None, "no_pack"),
    ({}, "pack_without_record"),
    ({"filter_inputs": {"v": 1, "filter_ran": True}}, "record_failed"),   # recording failed
    ({"filter_inputs": {**filter_record({}), "v": 2}}, "record_failed"),   # another version
    ({"filter_inputs": {**filter_record({}), "v": True}}, "record_failed"),
    ({"filter_inputs": {**filter_record({}), "filter_ran": "yes"}}, "record_failed"),
    ({"filter_inputs": "x"}, "record_failed"),
    ({"filter_inputs": {**filter_record({}), "qb_te": []}}, "record_failed"),
    ({"filter_inputs": {**filter_record({}), "lineup_slots": "QB"}}, "record_failed"),
], ids=lambda v: repr(v)[:40])
def test_a_deck_without_a_usable_record_is_not_auditable_for_b_dk_4_to_6(pack, state):
    """Never a pass: its unprotected cards are not auditable for B-DK-4..6
    (NOT_AUDITABLE, violations None), while B-DK-7 still reads its ids."""
    db = make_db()
    deck(db, "d", 3, {1: row("d", 1, *shape("breakup", "d", 1))})
    if pack is not None:
        _pack_with(db, "d", 3, **pack)
    r = run(db)
    assert r.filter_inputs == {state: 1}
    for name in ("breakup", "filler", "redundant"):
        t = r.rules[name]
        assert (t["violations"], t["not_auditable"], t["status"]) == (None, 3, NOT_AUDITABLE)
    assert r.rules["repeat"]["audited"] == 3 and r.overall == INCOMPLETE
    assert f"audited decks by record: {state}=1;" in render(r)


def test_a_deck_the_filter_didnt_run_on_is_skipped_and_counted():
    """filter_ran false: the deck went out unfiltered (flag off, an empty
    deck, or the filter raised). It is skipped for every rule, counted, and
    the read is not a pass."""
    db = make_db()
    _all_protected(db)
    deck(db, "raw", W + 1, {i: with_x("raw", i) for i in range(CAP + 1)})
    _pack_with(db, "raw", W + 1, filter_inputs={"v": 1, "filter_ran": False})
    r = run(db)
    assert (r.decks, r.skipped_decks, r.filter_inputs) == (1, {"filter_not_run": 1},
                                                           {"no_pack": 1})
    assert r.rules["repeat"]["violations"] == 0 and r.overall == INCOMPLETE
    assert "filter_not_run: served unfiltered): filter_not_run=1" in render(r)


def test_an_asset_the_filter_never_saw_is_not_auditable():
    db = make_db()
    give, receive = shape("breakup", "d", 1)
    deck(db, "d", 2, {1: row("d", 1, give, receive)},
         record={"market": {**shape(None, "d", 0)[0], **shape(None, "d", 0)[1], **give}})
    for name in ("breakup", "filler", "redundant"):
        t = run(db).rules[name]
        assert (t["violations"], t["audited"], t["not_auditable"]) == (0, 1, 1)


@pytest.mark.parametrize("value, audited", [(None, 1), (float("nan"), 1)], ids=["null", "nan"])
def test_a_recorded_null_or_nan_market_goes_to_the_rules_as_the_filter_saw_it(value, audited):
    """The filter priced an unseeded asset None (a NaN seed gives NaN): the
    rules get the same value, so the card is audited as the filter judged
    it. The header's NaN token is read."""
    db = make_db()
    give, receive = shape("breakup", "d", 0)
    deck(db, "d", 1, {0: row("d", 0, give, receive)},
         record={"market": {**dict.fromkeys(give, value), **receive}})
    with db.eng.connect() as conn:
        header = conn.execute(text("SELECT header_json FROM deck_evidence_packs")).scalar()
    assert ("NaN" in header) == (value != value)
    t = run(db).rules["breakup"]
    expected = dq._breakup(list(give), list(receive), {**dict.fromkeys(give, value),
                                                       **receive}.get)
    assert (t["audited"], t["violations"]) == (audited, int(expected))


def test_ids_are_read_as_strings():
    """#453 QA P3-3: integer ids in assets_json match the record's str ids."""
    db = make_db()
    deck(db, "d", W, {0: {**row("d", 0), "assets_json": json.dumps({"give": [101], "receive": [202]})}},
         record={"market": {**{a: v for i in range(1, W) for side in shape(None, "d", i)
                              for a, v in side.items()}, "101": HEAD, "202": LOW}})
    t = run(db).rules["breakup"]
    assert t["audited"] == W and t["violations"] == 1


# ---------------------------------------------------------------------------
# B-DK-7: the repeat cap over the first REPEAT_WINDOW displayed cards
# ---------------------------------------------------------------------------

def test_repeat_counts_an_asset_over_the_cap_in_the_window():
    """X in CAP + 1 window cards is a breach; in CAP window cards plus one
    past the window it is not."""
    db = make_db()
    deck(db, "rep", W, {i: with_x("rep", i) for i in range(CAP + 1)})
    deck(db, "ok", W + 1, {**{i: with_x("ok", i) for i in range(CAP)}, W: with_x("ok", W)})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained"], t["audited"], t["status"]) == (1, 0, 2 * W, FAIL)
    assert t["examples"] == [{"deck_job_id": "rep", "asset": "X",
                              "card_indexes": list(range(CAP + 1)), "why": None,
                              "over_cap_protected": [False], "ghost_slots": 0,
                              "withdrawn_removed": 0}]


def test_a_repeat_breach_of_protected_cards_only_is_explained():
    """_repeat_cap lets protected cards hold their positions: an over-cap
    appearance on a protected card is explained, not a violation. Protected
    cards still count toward the cap, so a later unprotected one breaches."""
    db = make_db()
    deck(db, "ok", W, {**{i: with_x("ok", i) for i in range(CAP)},
                       CAP: with_x("ok", CAP, likes_you=True)})
    deck(db, "bad", W, {**{i: with_x("bad", i, wildcard=True) for i in range(CAP)},
                        CAP: with_x("bad", CAP)})
    r = run(db)
    t = r.rules["repeat"]
    assert (t["violations"], t["explained"]) == (1, 1)
    assert [(e["deck_job_id"], e["over_cap_protected"]) for e in t["explained_examples"]] == [
        ("ok", [True])]
    assert [(e["deck_job_id"], e["over_cap_protected"]) for e in t["examples"]] == [
        ("bad", [False])]
    assert (t["explained_protected"], t["explained_short_deck"]) == (1, 0)
    assert "1 (explained: 1 by protected cards, 0 by a short deck, 0 by a response boundary)" in render(r)


def test_the_repeat_window_is_by_displayed_position():
    """A never-delivered withdrawal at index 2 moves card W up to displayed
    position W - 1, inside the window: X there is a fourth appearance. (The
    deck has a card past it, so it isn't a short deck. Its rows are an S1b
    partial run, so G-b4 audits it from rows.)"""
    db = make_db()
    special = {**{i: with_x("w", i) for i in (10, 11, 12)}, W: with_x("w", W)}
    deck(db, "w", W + 2, {i: {**special.get(i, row("w", i)), "evidence_tier": "partial_run"}
                          for i in range(W + 2) if i != 2}, skip={2})
    withdraw(db, "w", 2, 0, reason="disposition_cut")
    t = run(db).rules["repeat"]
    assert t["violations"] == 1 and t["audited"] == W
    assert t["examples"][0]["card_indexes"] == [10, 11, 12, W]
    assert t["examples"][0]["withdrawn_removed"] == 1


def _x_deck(db, job, n, x_at, **kw):
    deck(db, job, n, {i: with_x(job, i) for i in x_at}, **kw)


def test_a_short_deck_served_as_the_filter_ordered_it_is_explained():
    """#453 QA P2-1: _repeat_cap defers an over-cap card to just after the
    cards it keeps; with fewer than W cards to keep, the deferred ones still
    land in the window. A 12-card deck with X in 6 cards, served in the
    order filter_deck gave it, is _repeat_cap's own fixed point: explained."""
    db = make_db()
    _x_deck(db, "short", 12, (0, 1, 2, 9, 10, 11))      # 3 kept, 6 clean, 3 deferred after
    r = run(db)
    t = r.rules["repeat"]
    assert (t["violations"], t["explained"], t["explained_short_deck"]) == (0, 1, 1)
    assert t["status"] == PASS
    assert [(e["deck_job_id"], e["why"]) for e in t["explained_examples"]] == [
        ("short", "short_deck")]
    text = render(r)
    assert "0 (explained: 0 by protected cards, 1 by a short deck, 0 by a response boundary)" in text
    assert "short asset X at card_index 0, 1, 2, 9, 10, 11 (short_deck, over-cap" in text


def test_a_short_deck_out_of_the_filters_order_is_a_violation():
    """The same assets, but an over-cap card served ahead of cards the
    filter would have kept: re-running _repeat_cap moves it, so it's real."""
    db = make_db()
    _x_deck(db, "bad", 12, (0, 1, 2, 3, 10, 11))
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (1, 0)


def test_the_short_deck_check_reads_every_displayed_card(monkeypatch):
    """A packed 35-card deck with X in 10 (every card viewed, so every row is
    full): _repeat_cap keeps 28, so 2 of the 7 deferred X cards sit at
    positions 28-29. The check reads the 5 cards past the window too
    (fetched; they're not in the audit set). The same deck with no pack may
    have stopped after a 30-card batch, so it reads FAIL (the safe side). A
    displayed card with no full row can't be checked: a violation stands."""
    db = make_db()
    x_at = (0, 1, 2, *range(28, 35))
    for job in ("long", "packless"):
        _x_deck(db, job, 35, x_at)
    put_pack(db, "long", _deck_cards("long", 35), card_count=35, deliveries=[[34, SERVED]])
    deck(db, "gap", 12, {**{i: with_x("gap", i) for i in (0, 1, 2, 9, 10, 11)},
                         5: row("gap", 5, full=False)})       # displayed, no full row
    reads = []
    real = ba._full_rows
    monkeypatch.setattr(ba, "_full_rows", lambda conn, ids: reads.append(list(ids)) or real(conn, ids))
    t = run(db).rules["repeat"]
    assert t["explained_short_deck"] == 1 and t["violations"] == 2
    assert [e["deck_job_id"] for e in t["explained_examples"]] == ["long"]
    assert sorted(e["deck_job_id"] for e in t["examples"]) == ["gap", "packless"]
    past = sorted(card_impression_id("long", i) for i in range(30, 35))
    assert any(sorted(r) == past for r in reads)            # fetched for the check
    assert t["incomplete_decks"] == 1                       # "gap"


def test_a_pack_less_batch_with_a_never_delivered_withdrawal_is_not_a_short_deck():
    """#469 QA round 3: a pack-less deck stopped after its 30-card first batch,
    one of them a never-delivered withdrawal the loader drops, shows 29 cards.
    W0s count toward the 30, so X's fourth copy at the tail stays a breach."""
    db = make_db()
    deck(db, "w0", W, {i: with_x("w0", i) for i in (0, 1, 2, W - 1)}, skip={5})
    withdraw(db, "w0", 5, 0, reason="disposition_cut")
    (d,) = [d for d in eval_data.load_decks(engine=db.eng, since=SINCE, as_of=AS_OF)]
    assert (len(d.cards), d.withdrawn_removed) == (W - 1, 1)
    rows = ba._full_rows(db.eng.connect(), [c.impression_id for c in d.cards])
    assert not ba._short_deck(d, rows, lambda ids: {}, False, lambda deck, c, row: row[3])
    # A live-evidence deck with a cut in its window isn't checked at all (G-b4):
    # never explained, and B-DK-7 can't PASS on it.
    t = run(db).rules["repeat"]
    assert (t["explained_short_deck"], t["after_cut"]["live_evidence"], t["status"]) == (
        0, 1, NOT_AUDITABLE)


def test_a_pack_less_short_deck_in_flight_is_not_explained(monkeypatch):
    """Only a PACKED in_flight deck is known complete: a pack-less one holds
    its first 30 and viewed rows, so even a short one stays a violation."""
    monkeypatch.setattr(eval_data, "PACK_REQUIRED_SINCE", SINCE)
    db = make_db()
    deck(db, "nopack", 12, {i: {**(with_x("nopack", i) if i in (0, 1, 2, 9, 10, 11)
                                   else row("nopack", i)),
                                "evidence_tier": "first30", "delivered_at": SERVED}
                            for i in range(12)})
    assert [d.exclusion for d in eval_data.load_decks(engine=db.eng, since=SINCE,
                                                      as_of=AS_OF)] == ["in_flight"]
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (1, 0)


def test_a_packed_short_deck_in_flight_is_still_explained():
    """#469 QA P3-1: a pack holds every built card, so a packed deck that is
    only in_flight (its pack not retired yet) is complete: explained."""
    db = make_db()
    _x_deck(db, "short", 12, (0, 1, 2, 9, 10, 11))
    put_pack(db, "short", _deck_cards("short", 12), card_count=12,
             deliveries=[[11, SERVED]], retired=False)
    assert [d.exclusion for d in eval_data.load_decks(engine=db.eng, since=SINCE,
                                                      as_of=AS_OF)] == ["in_flight"]
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (0, 1)


@pytest.mark.parametrize("head, why", [
    ("deferred", "short_deck"),        # the cap kept 0..4 and deferred 5 onward
    ("kept", None),                    # the record says it kept card 5: a violation
    (None, None),                      # no repeat_head: the re-run needs rows past the window
], ids=["deferred", "kept", "absent"])
def test_repeat_head_explains_a_short_cap_without_rows_past_the_window(head, why):
    """release-lead's #492 QA: a packed deck whose cap ran short (473 deferred)
    read a false FAIL, since re-running _repeat_cap needs every displayed
    card's row and packed-only cards have none. With repeat_head (v6) the
    record says which cards the cap kept: X's fourth appearance at 5 is on a
    deferred card, so the breach is explained."""
    db = make_db()
    heads = {"deferred": [th(i) for i in range(5)], "kept": [th(i) for i in range(6)],
             None: None}
    deck(db, "s", W + 10, {i: with_x("s", i) for i in (0, 1, 2, 5)}, skip=range(W, W + 10),
         record={"repeat_head": heads[head]})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (int(why is None), int(why is not None))
    assert [e["why"] for e in t["explained_examples"] + t["examples"]] == [why]


def test_a_repeat_head_naming_the_over_cap_card_is_a_violation_even_where_a_re_run_explains():
    """A 4-card deck, X on all four: re-running _repeat_cap leaves it unchanged
    (the fourth is deferred to the end it already sits at), so without the
    field it reads short_deck. A record saying the cap kept that card is the
    filter's own word: the over-cap appearance wasn't deferred, a violation."""
    db = make_db()
    _x_deck(db, "k", 4, range(4))
    assert run(db).rules["repeat"]["explained_short_deck"] == 1
    db = make_db()
    deck(db, "k", 4, {i: with_x("k", i) for i in range(4)},
         record={"repeat_head": [th(i) for i in range(4)]})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained"]) == (1, 0)


def test_repeat_head_ignores_protected_over_cap_cards_it_kept():
    """A protected card holds its place in the cap's head; only the
    unprotected over-cap appearances need to have been deferred."""
    db = make_db()
    deck(db, "s", W + 10, {i: with_x("s", i) for i in (0, 1, 2, 4, 5)}, skip=range(W, W + 10),
         record={"repeat_head": [th(i) for i in range(5)], "protected": [th(4)]})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (0, 1)
    assert t["explained_examples"][0]["over_cap_protected"] == [True, False]


def _prefix_deck(db, job, tier, x_at=(0, 1, 2, W - 1)):
    """Only W rows (the first W cards of what would be a longer built deck;
    nothing past them is written), X at `x_at`: what the loader holds for a
    pack-less tiered deck (the first 30), a partial_run one (its delivered
    rows), or a pack-less untiered one stopped after its first 30-card
    publication batch."""
    deck(db, job, W, {i: {**(with_x(job, i) if i in x_at else row(job, i)),
                          "evidence_tier": tier, "delivered_at": SERVED} for i in range(W)})


@pytest.mark.parametrize("tier, hours, exclusion", [
    ("first30", 2, "in_flight"),           # no pack yet, inside 25 h
    ("first30", 30, "incomplete_deck"),    # a lost pack
    ("partial_run", 2, None),              # its delivered rows only
    (None, 2, None),                       # untiered, stopped after batch 1: no marker
], ids=["in_flight", "lost_pack", "partial_run", "stopped_after_batch_1"])
def test_a_deck_whose_cards_are_a_prefix_is_never_a_short_deck(monkeypatch, tier, hours,
                                                                exclusion):
    """#469 QA P1-1: these decks' cards are a prefix of what was displayed,
    so an over-cap card at the prefix's end would look deferred; X's fourth
    copy at W - 1 is a real breach and must stay one."""
    monkeypatch.setattr(eval_data, "PACK_REQUIRED_SINCE", SINCE)
    db = make_db()
    _prefix_deck(db, "pre", tier)
    as_of = _after(hours)
    assert [d.exclusion for d in eval_data.load_decks(engine=db.eng, since=SINCE,
                                                      as_of=as_of)] == [exclusion]
    t = audit(db.eng, since=SINCE, as_of=as_of).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (1, 0)


def test_a_short_deck_holding_a_redacted_card_is_still_explained():
    """Addendum J1: a partner_redacted deck is excluded from replay, not from
    the audit. It holds every card, so the short-deck proof still runs."""
    db = make_db()
    redacted = row("short", 5, partner_user_id=f"{REDACTED_PARTNER_PREFIX}aa11")
    deck(db, "short", 12, {**{i: with_x("short", i) for i in (0, 1, 2, 9, 10, 11)}, 5: redacted})
    assert [d.exclusion for d in eval_data.load_decks(engine=db.eng, since=SINCE,
                                                      as_of=AS_OF)] == ["partner_redacted"]
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (0, 1)


def test_ghost_rows_are_not_part_of_the_displayed_order():
    """#469 QA P3-1: the fixed point is over displayed cards only. A ghost
    carrying X at index 3 would break it if it were counted."""
    db = make_db()
    _x_deck(db, "short", 12, (0, 1, 2, 9, 10, 11))
    ghost = {**row("short", 3, {"X": HEAD, "short-gh": HEAD}, {"short-rh": HEAD}),
             "impression_id": card_impression_id("short", 3) + ":ghost", "is_ghost": 1,
             "served_at": SERVED}
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp), [ghost])
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_short_deck"]) == (0, 1)


def test_the_rules_never_take_dq_repeat_caps_place():
    """B-DK-7's short-deck check calls deck_quality._repeat_cap itself."""
    assert ba._repeat_cap is dq._repeat_cap


@pytest.mark.parametrize("bad", [
    {"assets_json": json.dumps({"give": 5, "receive": ["d-r0"]})},
    {"assets_json": json.dumps({"give": True, "receive": ["d-r0"]})},
    {"assets_json": json.dumps({"receive": ["d-r0"]})},
    {"assets_json": json.dumps({"give": [], "receive": []})},
], ids=["int_side", "bool_side", "missing_side", "empty_sides"])
def test_a_malformed_assets_side_is_not_auditable_never_a_crash(bad):
    """#453 QA P3-1: a non-list side made the weekly run exit 4."""
    db = make_db()
    deck(db, "d", W, {0: {**row("d", 0, *shape("breakup", "d", 0)), **bad}}, record={})
    r = run(db)
    for name in ("breakup", "filler"):
        assert r.rules[name]["not_auditable"] == 1
    assert r.rules["repeat"]["not_auditable"] == 1 and r.rules["repeat"]["incomplete_decks"] == 1


# ---------------------------------------------------------------------------
# The U6 audit set and the viewed cards with no full row (U4-R3)
# ---------------------------------------------------------------------------

def test_a_viewed_card_past_the_window_is_audited_and_an_unviewed_one_is_not():
    """Both past the window, both breakup cards with full rows: only the one
    with a `viewed` outcome is in the audit set."""
    db = make_db()
    deck(db, "d", W + 3, {W + 1: row("d", W + 1, *shape("breakup", "d", W + 1)),
                          W + 2: row("d", W + 2, *shape("breakup", "d", W + 2))},
         viewed=[0, W + 1], record={})
    r = run(db)
    assert (r.audit_cards, r.viewed_past_window) == (W + 1, 1)
    t = r.rules["breakup"]
    assert (t["violations"], t["audited"]) == (1, W + 1)
    assert [e["card_index"] for e in t["examples"]] == [W + 1]


@pytest.mark.parametrize("mapped", [True, False], ids=["miss_map", "no_miss_map"])
def test_a_viewed_card_with_no_full_row_is_reported_by_cause(mapped):
    """Rows for the window, a pack of every card past it: a viewed packed card
    and a viewed card whose row the upgrade miss built from the pack (no
    assets) are reported by their upgrade_miss_cards cause; a card with no
    entry, or a pack with no map, reads other. They count as not auditable,
    and an unviewed packed card is not in the audit set at all."""
    db = make_db()
    n = W + 10
    deck(db, "pk", W, viewed=[0, W + 3, W + 4, W + 5])
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp), [row("pk", W + 5, full=False)])
    misses = {str(W + 3): "restart_split", str(W + 5): "evicted_split"}
    market = {a: v for i in range(W) for side in shape(None, "pk", i) for a, v in side.items()}
    put_pack(db, "pk", _deck_cards("pk", n)[W:], card_count=n, deliveries=[[n - 1, SERVED]],
             filter_inputs=filter_record(market),
             **({"upgrade_miss_cards": misses} if mapped else {}))
    r = run(db)
    nf = r.no_full_row
    expect = ({"evicted_split": 1, "other": 1, "restart_split": 1} if mapped else {"other": 3})
    assert nf["viewed_by_cause"] == expect and nf["unviewed"] == 0
    assert [(e["card_index"], e["cause"]) for e in nf["examples"]] == [
        (W + 3, "restart_split" if mapped else "other"), (W + 4, "other"),
        (W + 5, "evicted_split" if mapped else "other")]
    assert r.audit_cards == W + 3 and r.decks == 1
    for name in ("breakup", "filler"):
        assert r.rules[name]["not_auditable"] == 3 and r.rules[name]["status"] == INCOMPLETE
    assert r.rules["repeat"]["status"] == PASS and r.overall == INCOMPLETE
    assert "Viewed, no full row (U4-R3), by cause: " in render(r)


def test_an_unviewed_window_card_with_no_full_row_leaves_its_deck_incomplete():
    """A window card with no assets (a packed card moved up by a withdrawal)
    can't be checked: not auditable for every rule, and its deck's repeat
    window incomplete."""
    db = make_db()
    deck(db, "d", W, {5: row("d", 5, full=False)}, record={})
    r = run(db)
    assert r.no_full_row["unviewed"] == 1 and r.no_full_row["viewed_by_cause"] == {}
    t = r.rules["repeat"]
    assert (t["not_auditable"], t["incomplete_decks"], t["status"]) == (1, 1, INCOMPLETE)
    assert r.rules["breakup"]["not_auditable"] == 1


# ---------------------------------------------------------------------------
# Which decks, and the overall verdict
# ---------------------------------------------------------------------------

def _all_protected(db: DB, job="safe", n=4):
    deck(db, job, n, {i: row(job, i, likes_you=True) for i in range(n)})


def test_every_card_exempt_or_checked_and_no_violation_passes():
    db = make_db()
    _all_protected(db)
    r = run(db)
    assert {k: t["status"] for k, t in r.rules.items()} == dict.fromkeys(r.rules, PASS)
    assert r.overall == PASS and r.notes == []


def test_untrusted_decks_are_skipped_and_counted_and_refresh_decks_left_out():
    """A withdrawal_conflict deck's positions can't be trusted: skipped,
    counted, and the read is not a pass. A Calibration refresh deck isn't a
    Trades deck: not audited, not counted."""
    db = make_db()
    _all_protected(db)
    deck(db, "refresh", 3, {i: row("refresh", i, deck_source="grading_refresh")
                            for i in range(3)})
    deck(db, "conflict", 3, viewed=[1])
    withdraw(db, "conflict", 1, 0)           # never delivered, yet viewed
    r = run(db)
    assert (r.decks, r.skipped_decks) == (1, {"withdrawal_conflict": 1})
    assert r.overall == INCOMPLETE
    assert "G1 / G8 signals; filter_not_run: served unfiltered): withdrawal_conflict=1" \
        in render(r)


def test_nothing_to_audit_is_not_a_pass_and_an_early_since_is_noted():
    db = make_db()
    r = run(db, since="2026-10-01T00:00:00+00:00")
    assert {t["status"] for t in r.rules.values()} == {NOT_AUDITABLE}
    assert all(t["violations"] is None for t in r.rules.values())
    assert r.overall == INCOMPLETE
    assert r.notes == [f"--since 2026-10-01T00:00:00+00:00 is before deck.quality_filters "
                       f"went live ({ba.FILTERS_LIVE_AT}): earlier decks were served "
                       "unfiltered."]


# ---------------------------------------------------------------------------
# Source checks
# ---------------------------------------------------------------------------

def test_no_threshold_literal_appears_in_the_module():
    """Every threshold is imported from deck_quality. A numeric literal equal
    to one is allowed only as an exit code (EXIT: 3 is INCOMPLETE, and
    REPEAT_CAP is 3); none may appear in the text either."""
    source = Path(ba.__file__).read_text()
    tree = ast.parse(source)
    thresholds = {dq.BREAKUP_MIN_RATIO, dq.FILLER_FLOOR, dq.FILLER_FRAC,
                  dq.REDUNDANT_MIN_RATIO, dq.REPEAT_WINDOW, dq.REPEAT_CAP}
    exit_map = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(getattr(t, "id", None) == "EXIT" for t in n.targets))
    allowed = {id(n) for n in ast.walk(exit_map)}
    restated = [(n.lineno, n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and type(n.value) in (int, float)
                and n.value in thresholds and id(n) not in allowed]
    assert restated == []
    for value in (dq.BREAKUP_MIN_RATIO, dq.FILLER_FLOOR, dq.FILLER_FRAC,
                  dq.REDUNDANT_MIN_RATIO, dq.REPEAT_WINDOW):
        text_forms = {f"{value:g}", repr(value), f"{value:.2f}"}
        for form in text_forms:
            assert not re.search(rf"(?<![\w.]){re.escape(form)}(?![\w])", source), form
    for name in ("_breakup", "_filler", "is_protected", "REPEAT_CAP", "REPEAT_WINDOW",
                 "BREAKUP_MIN_RATIO", "FILLER_FLOOR", "FILLER_FRAC", "REDUNDANT_MIN_RATIO"):
        assert getattr(ba, name) is getattr(dq, name)


def test_the_unrecorded_protections_are_deck_qualitys_less_the_recorded_ones():
    assert ba.UNRECORDED_PROTECTION == ("injected", "fatigue_retest", "retest",
                                        "owner_published")
    assert set(ba.UNRECORDED_PROTECTION) | set(ba._RECORDED_FEATURES) | {
        "source_like_impression_id"} == set(dq.PROTECTED_ATTRS)


def test_importing_bdk_audit_never_imports_the_server():
    code = "import sys, backend.eval.bdk_audit; print('backend.server' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# CLI: exit statuses, read-only, redaction, the settle clamp
# ---------------------------------------------------------------------------

def _file_db(path) -> DB:
    md = MetaData()
    imp = deck_impressions_table.to_metadata(md)
    deck_outcomes_table.to_metadata(md)
    packs, wd = pack_table(md), withdrawals_table(md)
    eng = create_engine(f"sqlite:///{path}")
    md.create_all(eng)
    return DB(eng, packs, wd, imp)


def _cli(path, *extra):
    return main(["--db", str(path), "--since", SINCE, "--as-of", AS_OF, *extra])


@pytest.mark.parametrize("build, code, overall", [
    (lambda db: _all_protected(db), 0, PASS),
    (lambda db: deck(db, "d", 3), 3, INCOMPLETE),
    (lambda db: deck(db, "d", 3, {1: row("d", 1, *shape("filler", "d", 1))}, record={}), 1,
     FAIL),
], ids=["pass", "incomplete", "fail"])
def test_the_cli_reads_a_sqlite_file_read_only_and_exits_by_the_verdict(
        tmp_path, capsys, build, code, overall):
    path = tmp_path / "audit.db"
    db = _file_db(path)
    build(db)
    db.eng.dispose()
    before = path.read_bytes()
    assert _cli(path) == code
    assert f"OVERALL: {overall}" in capsys.readouterr().out
    assert _cli(path, "--json") == code
    got = json.loads(capsys.readouterr().out)
    assert got["overall"] == overall and set(got["rules"]) == {
        "breakup", "filler", "redundant", "repeat"}
    assert path.read_bytes() == before

    eng = fr.read_only_engine(str(path))
    try:
        with pytest.raises(ReadOnlyViolation):
            with eng.begin() as conn:
                conn.execute(text("DELETE FROM deck_outcomes"))
    finally:
        eng.dispose()


def test_a_read_only_violation_inside_the_read_exits_2(tmp_path, capsys, monkeypatch):
    path = tmp_path / "audit.db"
    _file_db(path).eng.dispose()

    def writes(engine, **_kw):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM deck_outcomes"))

    monkeypatch.setattr(ba, "load_decks", writes)
    assert _cli(path) == 2
    out, err = capsys.readouterr()
    assert out == "" and "bdk_audit: blocked a non-read statement" in err


def test_a_non_sqlite_database_is_refused_without_the_flag(capsys):
    assert main(["--db", "postgresql://reader:hunter2@db.invalid/ftf", "--since", SINCE]) == 2
    err = capsys.readouterr().err
    assert "--allow-postgres-readonly" in err and "hunter2" not in err


def test_a_crash_exits_4_with_the_credentials_redacted(capsys, monkeypatch):
    def refused(url, **_kw):
        raise RuntimeError('could not translate host name "RET123@192.0.2.1" to address')

    monkeypatch.setattr(ba, "read_only_engine", refused)
    assert main(["--db", "postgresql://ftf:SEC@RET123@192.0.2.1:5432/ftf",
                 "--allow-postgres-readonly", "--since", SINCE, "--as-of", AS_OF]) == 4
    out, err = capsys.readouterr()
    assert out == "" and "Traceback (most recent call last)" in err and "***" in err
    for secret in ("SEC", "RET123", "192.0.2.1"):
        assert secret not in err


def test_a_malformed_time_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as usage:
        main(["--db", "unused.db", "--since", "tomorrow"])
    assert usage.value.code == 2
    assert "argument --since: not an ISO 8601 time: 'tomorrow'" in capsys.readouterr().err


def test_the_cli_settles_as_of_behind_the_clock(tmp_path, capsys, monkeypatch):
    clock = datetime.fromisoformat(_after(3))
    settled = (clock - timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(fr, "_now", lambda: clock)
    path = tmp_path / "audit.db"
    _file_db(path).eng.dispose()
    args = ["--db", str(path), "--since", SINCE, "--json"]
    assert main(args) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == settled and err == ""
    assert main(args + ["--as-of", clock.isoformat()]) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == settled
    assert err == (f"bdk_audit: note: --as-of {clock.isoformat()} is later than now minus "
                   f"STAMP_SETTLE (5 min); clamped to {settled}\n")


def test_help_documents_the_exit_codes(capsys):
    with pytest.raises(SystemExit) as done:
        main(["--help"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    for line in ("0  PASS", "1  FAIL", "2  a refused database or a ReadOnlyViolation",
                 "3  INCOMPLETE", "4  an unexpected error"):
        assert line in out


# ---------------------------------------------------------------------------
# #503 QA follow-ups; models-lead F3 / F4; #515's market_coerced
# ---------------------------------------------------------------------------

def _clean_market(job, idx):
    return {a: v for i in idx for side in shape(None, job, i) for a, v in side.items()}


def test_a_card_holding_a_coerced_value_is_not_auditable_for_breakup_and_filler():
    """#515: the filter saw NaN/inf there, recorded null and listed in
    market_coerced. Breakup and filler read it order-dependently, so they
    can't be checked; B-DK-6 reads it as None and still checks the card."""
    db = make_db()
    give, receive = shape("breakup", "d", 1)
    market = {**_clean_market("d", (0,)), **dict.fromkeys(give), **receive}
    deck(db, "d", 2, {1: row("d", 1, give, receive)},
         record={"market": market, "market_coerced": sorted(give)})
    r = run(db)
    for name in ("breakup", "filler"):
        assert (r.rules[name]["audited"], r.rules[name]["not_auditable"]) == (1, 1), name
    assert r.rules["redundant"]["audited"] == 2 and r.filter_inputs == {"recorded": 1}


@pytest.mark.parametrize("over", [
    {"market": {"d-g0": "2000"}},             # #503 QA P3-2: a string crashed the read
    {"market": {"d-g0": True}},               # and a bool read as 1.0
    {"market_coerced": "d-g0"},
    {"market_coerced": [5]},
], ids=["string", "bool", "coerced_not_list", "coerced_not_str"])
def test_a_record_with_a_malformed_value_is_record_failed(over):
    db = make_db()
    deck(db, "d", 2, record=over)
    r = run(db)
    assert r.filter_inputs == {"record_failed": 1}
    assert r.rules["breakup"]["status"] == NOT_AUDITABLE


def test_an_asset_with_a_market_but_no_position_is_not_auditable():
    """#503 QA P3-1: coverage needs both halves of the record."""
    db = make_db()
    market = _clean_market("d", (0, 1))
    positions = dict.fromkeys(market, "WR")
    del positions["d-r1"]
    deck(db, "d", 2, record={"market": market, "position": positions})
    for name in ("breakup", "filler", "redundant"):
        t = run(db).rules[name]
        assert (t["audited"], t["not_auditable"]) == (1, 1), name


def test_exemptions_are_split_by_deck_type():
    """models-lead F3: a protected card is exempt with or without a record;
    the split shows how much of a PASS rests on each."""
    db = make_db()
    deck(db, "rec", 2, record={"protected": [th(1)]})
    deck(db, "row", 2, {1: row("row", 1, likes_you=True)})
    r = run(db)
    for name in ("breakup", "filler", "redundant"):
        assert r.rules[name]["protected_by_deck"] == {"recorded": 1, "no_record": 1}, name
    assert "B-DK-4..6 exempt (protected) cards by deck (F3): recorded 1, no record 1." in render(r)


def test_live_evidence_decks_cut_inside_the_window_are_counted_not_checked():
    """models-lead F4: D3's serve-time re-cap runs only on packed decks, so a
    live-evidence deck with a never-delivered withdrawal in its first W
    cards is counted, never certified; one cut past W, or a packed deck, is
    not."""
    db = make_db()
    deck(db, "cut", W + 2)
    withdraw(db, "cut", 5, 0, reason="disposition_cut")
    deck(db, "late", W + 2)
    withdraw(db, "late", W + 1, 0, reason="disposition_cut")
    deck(db, "packed", W + 2, record={})
    withdraw(db, "packed", 5, 0, reason="disposition_cut")
    r = run(db)
    assert r.rules["repeat"]["after_cut_not_checked"] == 1
    assert r.rules["repeat"]["after_cut"] == {"audited_packed": 1, "audited_rows": 0,
                                              "live_evidence": 1, "no_evidence": None}
    assert ("not checked, live evidence 1 (F4: n > 0 goes to head-eng); not checked, no rows "
            "and no pack not read (no --no-evidence-log)") in render(r)


REDACTED = f"{REDACTED_PARTNER_PREFIX}9f0c"


@pytest.mark.parametrize("record", [{}, None], ids=["recorded", "no_record"])
def test_a_redacted_partner_s_cards_are_not_auditable_for_b_dk_4_to_6(record):
    """head-eng 2026-10-29, models-lead H1: the deletion scrub drops a
    redacted partner's hashes from filter_inputs.protected and its qb_te
    entry (and may clear its rows' likes_you), so its cards' protection and
    holdings are unknown: not auditable for B-DK-4..6, never a violation and
    never a pass. Card 1 trips breakup."""
    db = make_db()
    deck(db, "r", W, {1: row("r", 1, *shape("breakup", "r", 1), partner_user_id=REDACTED)},
         record=record)
    r = run(db)
    for name in ("breakup", "filler", "redundant"):
        t = r.rules[name]
        assert (t["violations"] or 0, t["protected"]) == (0, 0), name
        assert t["not_auditable_by_cause"].get("redacted") == 1, name
    assert r.rules["breakup"]["not_auditable"] == (1 if record is not None else W)
    assert r.redacted_cards == 1 and r.overall == INCOMPLETE
    assert r.incomplete_from_redaction_only is (record is not None)
    out = render(r)
    assert ("Redacted partners (account deletion): 1 of 30 audit-set cards (3.3%). Not "
            "auditable for B-DK-4..6") in out
    assert "INCOMPLETE from redaction only: " + ("yes" if record is not None else "no") in out


def test_a_redacted_card_still_counts_toward_the_cap():
    """models-lead H-a1, the defect: X on cards 0-3 and card 1 redacted. Card
    3 is X's real fourth copy on a fully checkable card, so B-DK-7 FAILs."""
    db = make_db()
    deck(db, "r", W, {**{i: with_x("r", i) for i in (0, 2, 3)},
                      1: with_x("r", 1, partner_user_id=REDACTED)}, record={})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["status"], t["not_auditable"]) == (1, FAIL, 0)
    assert t["examples"][0]["card_indexes"] == [0, 1, 2, 3]


@pytest.mark.parametrize("protected_after", [False, True], ids=["alone", "beside_protected"])
def test_a_redacted_over_cap_card_is_unknown_never_explained(protected_after):
    """H-a1: when X's only unprotected-or-unknown over-cap copy is the
    redacted card 3, its verdict is unknown: not a violation, never explained
    as protected (even beside a protected over-cap copy at 4), and its deck
    incomplete for redaction (H-a2)."""
    db = make_db()
    special = {**{i: with_x("r", i) for i in (0, 1, 2)},
               3: with_x("r", 3, partner_user_id=REDACTED)}
    if protected_after:
        special[4] = with_x("r", 4, likes_you=True)
    deck(db, "r", W, special)
    r = run(db)
    t = r.rules["repeat"]
    assert (t["violations"], t["explained"], t["status"]) == (0, 0, INCOMPLETE)
    assert (t["not_auditable_by_cause"], t["incomplete_decks_by_cause"]) == (
        {"redacted": 1}, {"redacted": 1})
    assert "B-DK-7 repeat: 1 decks have an unchecked window card, by cause: redacted=1." in (
        render(r))


def test_only_the_token_marks_a_redacted_partner():
    """A partner id that merely contains the prefix is audited as usual, and
    a deck without redacted cards prints no redaction line."""
    db = make_db()
    deck(db, "p", 2, {1: row("p", 1, *shape("breakup", "p", 1),
                             partner_user_id=f"x{REDACTED_PARTNER_PREFIX}1")}, record={})
    r = run(db)
    assert (r.rules["breakup"]["violations"], r.redacted_cards) == (1, 0)
    assert "Redacted partners" not in render(r)


# ---------------------------------------------------------------------------
# models-lead addendum G2: the response boundary (G-b1), its line (G-b2) and
# F4's four buckets (G-b4); G-b5's fixture for each bucket and each outcome.
# ---------------------------------------------------------------------------

def _boundary_deck(db, job="b", *, cut=True, skip=(), x_at=(4, 5, 6, W), last=W):
    """40 packed cards in three responses: 0..19, 20..`last`, `last`+1..39.
    X is on `x_at`; the filter deferred its fourth copy to card W, just past
    the window. With `cut`, a never-delivered withdrawal at card 2 pulls card
    W up to position W - 1, and response 2 (20..W) has no clean card left
    after it to fill the window: D3 can do no better inside the boundary."""
    deck(db, job, 40, {i: with_x(job, i) for i in x_at}, skip={2, *skip} if cut else skip,
         record={}, deliveries=[[19, SERVED], [last, SERVED], [39, SERVED]])
    if cut:
        withdraw(db, job, 2, 0, reason="disposition_cut")


def test_g_b1_a_boundary_breach_is_explained_only_with_both_proofs():
    """The explained outcome: a recorded cut before the over-cap card, inside
    the window, and its own response is a fixed point of the cap."""
    db = make_db()
    _boundary_deck(db)
    r = run(db)
    t = r.rules["repeat"]
    assert (t["violations"], t["explained_boundary"], t["boundary_decks"]) == (0, 1, 1)
    assert t["status"] == PASS and t["packed_decks"] == 1
    assert t["after_cut"]["audited_packed"] == 1
    assert [e["card_indexes"] for e in t["boundary_examples"]] == [[4, 5, 6, W]]
    out = render(r)
    assert out.splitlines()[0].startswith(
        "B-DK-7 PASS with 1 breaches explained by a response boundary on 1 decks (100.0% of "
        "audited packed decks)")
    assert "0 (explained: 0 by protected cards, 0 by a short deck, 1 by a response boundary)" in out
    assert "B-DK-7 response boundary (models-lead G-b1): 1 breaches on 1 decks, 100.0% of 1" in out


def test_g_b1_no_recorded_cut_is_a_violation():
    """The no-cut outcome: X's fourth copy at card W - 1, at the end of its
    response (20..W - 1, a fixed point), but nothing recorded pulled it in:
    the build order already broke the cap, a serve bug or a filter bug."""
    db = make_db()
    _boundary_deck(db, cut=False, x_at=(4, 5, 6, W - 1), last=W - 1)
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_boundary"], t["status"]) == (1, 0, FAIL)


def test_g_b1_a_missing_row_is_a_violation():
    """The missing-row outcome: card 25, inside the over-cap card's response,
    has no full row, so the re-run can't be shown to be a fixed point."""
    db = make_db()
    _boundary_deck(db, skip={25})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_boundary"], t["status"]) == (1, 0, FAIL)
    assert t["not_auditable_by_cause"] == {"no_full_row": 1}


def test_g_b1_a_response_with_a_clean_card_left_is_a_violation():
    """D3 should have moved the over-cap card behind a later clean card of its
    own response; served where it is, the re-run isn't a fixed point."""
    db = make_db()
    _boundary_deck(db, x_at=(4, 5, 6, W - 1))      # card W, clean, still in response 2
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained_boundary"]) == (1, 0)


def test_g_b4_every_deck_with_a_cut_lands_in_exactly_one_bucket():
    """audited packed (D3), audited from rows (an S1b partial run), not
    checked live evidence (F4's trigger, its cards unchecked), and #535's
    decks from the read's captured log lines."""
    db = make_db()
    deck(db, "packed", W + 2, skip={5}, record={})
    deck(db, "rows", W + 2, {i: {**row("rows", i), "evidence_tier": "partial_run"}
                             for i in range(W + 2) if i != 5}, skip={5})
    deck(db, "live", W + 2, {1: row("live", 1, *shape("breakup", "live", 1))}, skip={5})
    deck(db, "nocut", W + 2, skip={W + 1})
    for job, i in (("packed", 5), ("rows", 5), ("live", 5), ("nocut", W + 1)):
        withdraw(db, job, i, 0, reason="disposition_cut")
    log = ("ERROR deck-evidence ghost1: 4 delivered cards of a deck with no evidence (no rows, no "
           "pack); eval can't see them\nERROR deck-evidence ghost1: 1 delivered card of a deck "
           "with no evidence\n")
    r = run(db, no_evidence=fr.parse_no_evidence_log(log))
    t = r.rules["repeat"]
    assert t["after_cut"] == {"audited_packed": 1, "audited_rows": 1, "live_evidence": 1,
                              "no_evidence": 1}
    assert t["after_cut_not_checked"] == 1
    assert (t["not_auditable_by_cause"], t["incomplete_decks_by_cause"]) == (
        {"live_cut": W}, {"live_cut": 1})
    assert fr.parse_no_evidence_log(log) == {"ghost1": 5}
    assert ("audited, packed 1 (D3 re-caps them); audited from rows, no pack 1 (S1b partial "
            "runs, lost or in-flight packs: D3 didn't run, so a breach is a violation); not "
            "checked, live evidence 1 (F4: n > 0 goes to head-eng); not checked, no rows and no "
            "pack 1 (#535's lines; an upper bound: every captured #535 deck, cut or "
            "not).") in render(r)


def test_the_cli_reads_the_captured_no_evidence_lines(tmp_path, capsys):
    path, log = tmp_path / "audit.db", tmp_path / "535.log"
    db = _file_db(path)
    deck(db, "d", 3, record={})
    db.eng.dispose()
    log.write_text("deck-evidence gone: 2 delivered cards of a deck with no evidence\n",
                   encoding="utf-8")
    assert _cli(path, "--json", "--no-evidence-log", str(log)) == 0
    assert json.loads(capsys.readouterr().out)["rules"]["repeat"]["after_cut"][
        "no_evidence"] == 1


def test_h_a2_says_why_a_rule_is_incomplete():
    """Every rule's unchecked cards by cause, B-DK-7's incomplete decks by
    cause, and whether redaction alone made the read INCOMPLETE."""
    db = make_db()
    deck(db, "d", 3, {1: row("d", 1, full=False)}, record={})
    r = run(db)
    assert r.rules["breakup"]["not_auditable_by_cause"] == {"no_full_row": 1}
    assert r.rules["repeat"]["incomplete_decks_by_cause"] == {"no_full_row": 1}
    assert r.overall == INCOMPLETE and r.incomplete_from_redaction_only is False
    out = render(r)
    assert "Not auditable, by cause (models-lead H-a2): B-DK-4 breakup no_full_row=1;" in out
    assert "INCOMPLETE from redaction only: no" in out
