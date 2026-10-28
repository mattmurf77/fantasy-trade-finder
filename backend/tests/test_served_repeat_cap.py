"""models-lead addendum D3: deck_quality's repeat cap re-applied to the
displayed order at a serve.

A disposition cut, or I-1's drop at trade_i1_mode 2, of a never-delivered card
ahead of the cards the filter deferred pulls them into the displayed first
REPEAT_WINDOW; B-DK-7 counts what users see. The serve moves an over-cap card
to just after the last card the window takes from its response, and the pack
header's display_moves tells eval (backend/eval/data.py), so displayed
positions follow it.

Covers: _served_repeat_cap as a pure function (and differentially against
deck_quality._repeat_cap); the legacy body, a later page (stored and job view,
and after the job left the process), a replace serve, each with a disposition
cut and with I-1 at mode 2; what never moves (flag off, an unpacked deck, no
withdrawal); and the header (written, merged, first delivery wins, each
move's anchor a card its response sent first).

Harness: test_deferred_evidence's `deferred` (p1's real worker and routes,
flag on, evidence writes inline), with the synthetic deck giving asset mine0
on cards 0-2 (the filter's three in the window) and 30-31 (the two it
deferred past it). eval's reading of the header is models-eng's #501; the
tests here check the header against that order rule (_display_key).
"""
import json
import random
import types

import pytest

import backend.server as server
import backend.tests.test_deferred_evidence as de
from backend import deck_quality as dq
from backend.eval import contract
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, run_job, status  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import HEADERS, deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import (
    deck_ids, own_all_but, pack_of, pass_elsewhere, restart, unpack, withdrawals)

W, CAP = dq.REPEAT_WINDOW, dq.REPEAT_CAP
X_AT = (0, 1, 2, 30, 31)


# ── _served_repeat_cap, pure ─────────────────────────────────────────────────

def card(i, *assets, job="d", **kw):
    return {"impression_id": f"{job}:{i}", "give": [{"id": a} for a in assets or (f"g{i}",)],
            "receive": [{"id": f"r{i}"}], **kw}


def indexes(cards):
    return [int(c["impression_id"].split(":")[1]) for c in cards]


def window_deck(cut=29):
    """0..33 less `cut`, X on 0-2 and 30-31: the cut pulls 30 into the window."""
    return [card(i, "X") if i in X_AT else card(i) for i in range(34) if i != cut]


def test_a_card_pulled_into_the_window_moves_behind_the_next_clean_one():
    out, moves = server._served_repeat_cap(window_deck(), "d")
    assert indexes(out) == [*range(29), 32, 30, 31, 33]
    assert moves == {30: 32, 31: 32}


def test_a_later_page_counts_the_cards_earlier_responses_displayed():
    deck = window_deck()
    out, moves = server._served_repeat_cap(deck[29:], "d", prior=deck[:29])
    assert (indexes(out), moves) == ([32, 30, 31, 33], {30: 32, 31: 32})


def test_a_full_window_moves_nothing():
    deck = [card(i, "X") if i in X_AT else card(i) for i in range(34)]
    cards = deck[30:]
    assert server._served_repeat_cap(cards, "d", prior=deck[:30]) == (cards, {})


@pytest.mark.parametrize("held", ["likes_you", "standing_offer_reason", "wildcard", "retest",
                                  "delivered"])
def test_a_protected_or_delivered_card_holds_its_place(held):
    """It holds, and counts: the next over-cap card still moves."""
    deck = [card(i, "X") if i in X_AT else card(i) for i in range(34) if i not in (28, 29)]
    if held != "delivered":
        deck[28] = {**deck[28], held: "yes"}             # card 30
    delivered = {"d:30"} if held == "delivered" else frozenset()
    out, moves = server._served_repeat_cap(deck[28:], "d", prior=deck[:28], delivered=delivered)
    assert (indexes(out), moves) == ([30, 32, 31, 33], {31: 32})


@pytest.mark.parametrize("bad", ["no_id", "uuid", "other_deck", "out_of_order"])
def test_nothing_moves_without_contract_ids_in_build_order(bad):
    deck = window_deck()
    if bad == "out_of_order":
        deck[-1], deck[-2] = deck[-2], deck[-1]
    else:
        deck[-1] = {**deck[-1], "impression_id": {"no_id": None, "uuid": "ab12" * 8,
                                                  "other_deck": "e:33"}[bad]}
    assert server._served_repeat_cap(deck, "d") == (deck, {})


def test_a_delivered_card_withdrawn_since_holds_its_slot_unsent():
    """served_before 1: eval keeps it in place, so nothing is pulled up."""
    deck = window_deck(cut=None)
    gone = deck.pop(29)                                   # card 29, delivered, now withdrawn
    out, moves = server._served_repeat_cap(deck, "d", delivered={gone["impression_id"]},
                                           withheld=[gone])
    assert (indexes(out), moves) == ([*range(29), 30, 31, 32, 33], {})


def test_recorded_moves_are_re_applied_and_not_recorded_again():
    """A whole-deck re-serve: every card delivered, the earlier moves kept."""
    deck = window_deck()
    out, moves = server._served_repeat_cap(
        deck, "d", delivered={c["impression_id"] for c in deck}, recorded={30: 32, 31: 32})
    assert (indexes(out), moves) == ([*range(29), 32, 30, 31, 33], {})


@pytest.mark.parametrize("last", ["delivered", "withheld"])
def test_the_anchor_is_always_a_card_this_response_sends_first(last):
    """eval reads a move only with its card and anchor in one delivery (#501):
    when the window's last card went out earlier, nothing moves."""
    deck = window_deck()                                  # 0..28, 30, 31, 32, 33
    kw = ({"delivered": {"d:32"}} if last == "delivered"
          else {"delivered": {"d:32"}, "withheld": [deck.pop(31)]})   # card 32, unsent
    out, moves = server._served_repeat_cap(deck, "d", **kw)
    assert moves == {}
    assert indexes(out) == [*range(29), 30, 31, *([32] if last == "delivered" else []), 33]


def test_a_recorded_move_is_never_an_anchor():
    """The window's last card is itself a recorded move (35 behind 40),
    delivered earlier: a card deferred behind it would read, by eval's key,
    ahead of it. Nothing moves."""
    deck = [*(card(i, "X") if i in X_AT else card(i) for i in range(29)),
            card(33, "X"), card(35), card(41)]
    out, moves = server._served_repeat_cap(deck, "d", delivered={"d:35"}, recorded={35: 40})
    assert (indexes(out), moves) == ([*range(29), 33, 35, 41], {})


def test_a_response_with_no_clean_card_to_take_leaves_its_order():
    deck = window_deck()
    cards = deck[29:31]                                   # 30, 31: nothing to put first
    assert server._served_repeat_cap(cards, "d", prior=deck[:29]) == (cards, {})


@pytest.mark.parametrize("seed", range(40))
def test_a_whole_deck_serve_orders_as_deck_quality_repeat_cap(seed):
    """Differential: on a whole deck (no prior, nothing delivered) the serve's
    order is _repeat_cap's own, protected cards included."""
    rng = random.Random(seed)
    n = rng.randint(5, 70)
    deck = [card(i, *rng.sample("ABCDEFGH", rng.randint(1, 2)),
                 **({"likes_you": True} if rng.random() < 0.1 else {})) for i in range(n)]
    ns = [types.SimpleNamespace(i=i, give_player_ids=[p["id"] for p in c["give"]],
                                receive_player_ids=[p["id"] for p in c["receive"]],
                                likes_you=c.get("likes_you", False))
          for i, c in enumerate(deck)]
    want = [c.i for c in dq._repeat_cap(ns)[0]]
    out, moves = server._served_repeat_cap(deck, "d")
    assert indexes(out) == want
    keyed = sorted(range(n), key=lambda i: server._display_key(i, moves))
    assert keyed == want                                  # eval's key reproduces it


# ── through the serve paths ──────────────────────────────────────────────────

@pytest.fixture()
def x_deck(deferred, monkeypatch):
    """`deferred` with the filters on and the synthetic deck's mine0 on X_AT."""
    real = de.synthetic_cards

    def with_x(n):
        cards, players = real(n)
        for i in X_AT[1:]:
            cards[i].give_player_ids = ["mine0"]
        return cards, players
    monkeypatch.setattr(de, "synthetic_cards", with_x)
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)
    return deferred


def ids(job_id, *idx):
    return [contract.card_impression_id(job_id, i) for i in idx]


def withdraw_5(engine, how):
    """Card 5, never delivered, withdrawn at the next serve."""
    if how == "cut":
        pass_elsewhere(engine, 5)
    else:
        own_all_but(engine, 5)                            # live: trade_i1_mode 2


def header_moves(engine, job_id):
    run, _cards = unpack(pack_of(engine, job_id))
    return run.get("display_moves")


def displayed(engine, job_id):
    """The order eval reads from the evidence alone (models-eng's #501): the
    pack's cards less the never-delivered withdrawals, each moved card right
    after its anchor."""
    run, cards = unpack(pack_of(engine, job_id))
    moves = {int(k): a for k, a in (run.get("display_moves") or {}).items()}
    w0 = {i for i, r in withdrawals(engine).items() if r["served_before"] == 0}
    kept = [c["card_index"] for c in cards if c["card_index"] not in w0]
    return sorted(kept, key=lambda i: server._display_key(i, moves))


def assert_moved(engine, job_id):
    assert header_moves(engine, job_id) == {"30": 32, "31": 32}
    shown = displayed(engine, job_id)
    assert 5 not in shown                                 # W0: removed for eval
    assert shown[28:33] == [29, 32, 30, 31, 33]
    assert sum(1 for i in shown[:W] if i in X_AT) == CAP  # B-DK-7: X in 3 of the first 30


@pytest.mark.parametrize("how", ["cut", "i1"])
@pytest.mark.parametrize("path", ["stored", "job_view", "left_process"])
def test_a_later_page_moves_the_pulled_card_and_records_it(x_deck, how, path):
    client, engine, _ = x_deck
    job_id, *_ = de.deferred_deck(120, packed=True, store=path != "job_view")
    withdraw_5(engine, how)
    first = deck_ids(status(client, job_id, 0).get_json())
    assert first == ids(job_id, *(i for i in range(30) if i != 5))
    assert {i: r["reason"] for i, r in withdrawals(engine).items()} == {
        5: "disposition_cut" if how == "cut" else "i1_dropped"}
    if path == "left_process":
        restart()
    page = deck_ids(status(client, job_id, 30).get_json())
    assert page == ids(job_id, 32, 30, 31, *range(33, 60))
    assert_moved(engine, job_id)


@pytest.mark.parametrize("how", ["cut", "i1"])
def test_the_legacy_body_moves_it_and_a_repeat_poll_keeps_the_order(x_deck, how):
    client, engine, _ = x_deck
    job_id, *_ = de.deferred_deck(120, packed=True, store=False)
    withdraw_5(engine, how)
    want = ids(job_id, *(i for i in range(30) if i != 5), 32, 30, 31, *range(33, 120))
    for _poll in range(2):
        body = client.get(f"/api/trades/status?job_id={job_id}", headers=HEADERS).get_json()
        assert deck_ids(body) == want
    assert_moved(engine, job_id)


@pytest.mark.parametrize("how", ["cut", "i1"])
def test_a_replace_serve_after_a_delivered_cards_withdrawal_moves_nothing(x_deck, how):
    client, engine, _ = x_deck
    job_id, *_ = de.deferred_deck(120, packed=True, store=False)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["append_only"] = False   # a re-sorting job: cursor > 0 replaces
    status(client, job_id, 0)
    withdraw_5(engine, how)
    body = status(client, job_id, 30).get_json()
    assert body["replace"] is True
    # Card 5 was delivered on page 1, so its withdrawal is served_before 1 and
    # keeps its position: nothing is pulled, nothing moves.
    assert deck_ids(body) == ids(job_id, *(i for i in range(120) if i != 5))
    assert header_moves(engine, job_id) is None


@pytest.mark.parametrize("how", ["cut", "i1"])
def test_a_replace_serve_after_a_never_delivered_withdrawal_moves_it(x_deck, how):
    client, engine, _ = x_deck
    job_id, *_ = de.deferred_deck(120, packed=True, store=False)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["append_only"] = False
    withdraw_5(engine, how)
    status(client, job_id, 0)                             # page 1: card 5 withdrawn, W0
    body = status(client, job_id, 30).get_json()
    assert body["replace"] is True
    assert deck_ids(body) == ids(job_id, *(i for i in range(30) if i != 5), 32, 30, 31,
                                 *range(33, 120))
    assert_moved(engine, job_id)


@pytest.mark.parametrize("off", ["flag_off", "unpacked", "no_withdrawal"])
def test_nothing_moves_when_it_cannot_be_recorded_or_nothing_was_pulled(x_deck, monkeypatch, off):
    client, engine, _ = x_deck
    if off == "flag_off":
        monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: False)
    job_id, *_ = de.deferred_deck(120, packed=off != "unpacked", store=False)
    if off != "no_withdrawal":
        withdraw_5(engine, "cut")
    status(client, job_id, 0)
    page = deck_ids(status(client, job_id, 30).get_json())
    assert page == ids(job_id, *range(30, 60))
    if off != "unpacked":
        assert header_moves(engine, job_id) is None


def test_the_header_keeps_a_cards_first_move():
    """A deploy overlap: the stored header's move for a card wins."""
    stored = {"deliveries": [[29, "t1"]], "display_moves": {"30": 32}}
    ours = {"deliveries": [[59, "t2"]], "display_moves": {"30": 33, "31": 33}}
    merged = server._merge_pack_runs(stored, ours, None)
    assert merged["display_moves"] == {"30": 32, "31": 33}
    assert "display_moves" not in server._merge_pack_runs({"deliveries": []}, {"deliveries": []},
                                                          None)
