"""models-lead addendum D3, the eval side: serve-time display moves.

When a never-delivered withdrawal pulls a repeat-capped card into the first
REPEAT_WINDOW, the server re-applies the cap and defers that card within its
response. The pack's run["display_moves"] ({"<card_index>": anchor}) records
it, and load_decks hands the displayed positions out in display order, so
B-DK-7, e(k) and the logged-position term read where the user saw each card.
A move counts once its response is delivered as of the read; a record that
breaks the writer's contract makes the deck pack_integrity.
"""

import pytest

import backend.deck_quality as dq
from backend.eval.bdk_audit import audit
from backend.eval.data import PACK_INTEGRITY, WITHDRAWAL_CONFLICT, card_dict, load_decks
from backend.eval.flip_read import flip_read
from backend.eval.scorers import get_scorer
from backend.tests.test_eval_bdk_audit import AS_OF as BDK_AS_OF, SINCE, deck, with_x
from backend.tests.test_eval_pack_reader import SERVED, _deck_cards, write_deck
from backend.tests.test_eval_withdrawals_and_paging import (
    LATER, _after, act, make_db, put_pack, update_pack, withdraw,
)

W = dq.REPEAT_WINDOW


def _packed_deck(db, *, moves=None, deliveries=((9, SERVED),), w0=(), job="j", n=10, **run):
    """n built cards: rows for the first 5, a pack of all n with `deliveries`
    and, when given, run["display_moves"] = moves; a W0 per index in w0."""
    cards = _deck_cards(job, n)
    extra = {} if moves is None else {"display_moves": moves}
    write_deck(db.eng, db.packs, cards, full=range(5))          # rows only (no pack)
    put_pack(db, job, cards, card_count=n, deliveries=[list(d) for d in deliveries],
             **extra, **run)
    for i in w0:
        withdraw(db, job, i, 0)
    return cards


def _positions(deck):
    return {c.card_index: c.position for c in deck.cards if not c.is_ghost}


@pytest.mark.parametrize("moves", [None, {}])
def test_no_moves_change_nothing(moves):
    db = make_db()
    _packed_deck(db, moves=moves)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None
    assert _positions(deck) == {i: i for i in range(10)}


def test_a_moved_card_is_displayed_right_after_its_anchor():
    db = make_db()
    _packed_deck(db, moves={"2": 4})
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None
    assert _positions(deck) == {0: 0, 1: 1, 3: 2, 4: 3, 2: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9}
    assert [c.card_index for c in deck.cards] == list(range(10))   # still card_index order


def test_cards_moved_behind_one_anchor_keep_their_build_order():
    db = make_db()
    _packed_deck(db, moves={"3": 5, "1": 5})
    (deck,) = load_decks(engine=db.eng)
    order = sorted(_positions(deck), key=_positions(deck).get)
    assert order == [0, 2, 4, 5, 1, 3, 6, 7, 8, 9]
    assert sorted(_positions(deck).values()) == list(range(10))


def test_moves_take_the_positions_left_after_never_delivered_withdrawals():
    """W0 at 6: the kept cards' positions are 0..8, handed out in display
    order (2 behind 4)."""
    db = make_db()
    _packed_deck(db, moves={"2": 4}, w0=(6,))
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and deck.withdrawn_removed == 1
    assert _positions(deck) == {0: 0, 1: 1, 3: 2, 4: 3, 2: 4, 5: 5, 7: 6, 8: 7, 9: 8}


def test_a_move_counts_once_its_response_is_delivered_as_of_the_read():
    """The writer records the move with its response's delivery, after as_of:
    a re-read at the same as_of is the same deck; a later one moves the card."""
    db = make_db()
    as_of = _after(26)                       # past the window: final, retired or not
    cards = _packed_deck(db, deliveries=[[4, SERVED]], retired=False)
    (first,) = load_decks(engine=db.eng, as_of=as_of)
    update_pack(db, "j", cards, card_count=10, retired=True, retired_at=_after(27),
                deliveries=[[4, SERVED], [9, _after(26.5)]], display_moves={"6": 8})
    act(db, "j", 7, "viewed", at=_after(26.6))
    (again,) = load_decks(engine=db.eng, as_of=as_of)
    (later,) = load_decks(engine=db.eng, as_of=_after(28))
    assert first.exclusion is None and first == again
    assert _positions(again) == {i: i for i in range(10)}
    assert later.exclusion is None
    assert _positions(later) == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 7: 6, 8: 7, 6: 8, 9: 9}


@pytest.mark.parametrize("moves, deliveries, w0", [
    ([["2", 4]], None, ()),                 # not a dict
    ({"x": 4}, None, ()),                   # a key that isn't a card_index
    ({"02": 4}, None, ()),
    ({"2.0": 4}, None, ()),
    ({"-1": 4}, None, ()),
    ({"2": "4"}, None, ()),                 # a value that isn't an int
    ({"2": True}, None, ()),
    ({"2": 4.0}, None, ()),
    ({"2": 2}, None, ()),                   # anchored to itself
    ({"2": 4, "4": 6}, None, ()),           # the anchor is itself moved
    ({"2": 12}, None, ()),                  # an anchor outside the deck
    ({"4": 2}, None, ()),                   # an anchor before its card (#501 QA P3-6)
    ({"2": 4}, None, (2,)),                 # the moved card is a W0
    ({"2": 4}, None, (4,)),                 # the anchor is a W0
    ({"3": 6}, [[4, SERVED], [9, LATER]], ()),   # card and anchor in different responses
], ids=lambda v: repr(v))
def test_a_move_record_breaking_the_writers_contract_is_pack_integrity(moves, deliveries, w0):
    db = make_db()
    _packed_deck(db, moves=moves, deliveries=deliveries or [[9, SERVED]], w0=w0)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == PACK_INTEGRITY


def test_a_move_inside_a_later_response_is_valid():
    db = make_db()
    _packed_deck(db, moves={"6": 8}, deliveries=[[4, SERVED], [9, LATER]])
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and _positions(deck)[6] == 8


def test_a_broken_move_record_comes_before_a_withdrawal_conflict():
    """pack_integrity precedes withdrawal_conflict (module doc): a deck with
    both reads pack_integrity."""
    db = make_db()
    _packed_deck(db, moves={"2": 2}, w0=(1,))
    act(db, "j", 1, "viewed")                # a never-delivered withdrawal with an outcome
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == PACK_INTEGRITY
    db = make_db()
    _packed_deck(db, moves={"2": 4}, w0=(1,))
    act(db, "j", 1, "viewed")
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == WITHDRAWAL_CONFLICT


@pytest.mark.parametrize("moved, violations", [(False, 1), (True, 0)])
def test_b_dk_7_reads_the_displayed_window_after_a_serve_time_move(moved, violations):
    """D3's case: a disposition cut at 2 pulls card W (X's fourth, deferred
    by the build-time cap) to displayed position W - 1. The server re-applies
    the cap and shows it after card W + 1, outside the window. Without the
    move record the audit sees a false breach."""
    db = make_db()
    deck(db, "w", W + 2, {**{i: with_x("w", i) for i in (10, 11, 12)}, W: with_x("w", W)},
         skip={2})
    put_pack(db, "w", _deck_cards("w", W + 2), card_count=W + 2,
             deliveries=[[W + 1, SERVED]],
             **({"display_moves": {str(W): W + 1}} if moved else {}))
    withdraw(db, "w", 2, 0, reason="disposition_cut")
    t = audit(db.eng, since=SINCE, as_of=BDK_AS_OF).rules["repeat"]
    assert (t["violations"], t["audited"]) == (violations, W)


# ---------------------------------------------------------------------------
# models-lead F1: the loader checks only delivered moves; G1 checks the whole
# header. #501 QA P3s: ghosts, null, the logged scorer, G7.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("moves, deliveries", [
    ({"12": 4}, [[9, SERVED]]),             # a card outside the deck, never delivered
    ({"6": 8}, [[4, SERVED]]),              # a move in no delivery at all
], ids=["outside", "undelivered"])
def test_an_undelivered_malformed_move_is_g1s_not_the_loaders(moves, deliveries):
    """F1: the loader reads only moves delivered as of the read, so it leaves
    these alone; G1's whole-header check FAILs them at once."""
    db = make_db()
    _packed_deck(db, moves=moves, deliveries=deliveries)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and _positions(deck) == {i: i for i in range(10)}
    g1 = flip_read(db.eng, since=SERVED, as_of=_after(2)).g1
    assert (g1["pack_integrity"], g1["display_moves_malformed"], g1["status"]) == (0, 1, "FAIL")
    assert g1["ids"] == ["j"]


@pytest.mark.parametrize("w0, malformed", [((6,), 1), ((), 0)], ids=["w0_moved", "no_w0"])
def test_g1_sees_a_later_move_that_names_a_never_delivered_card(w0, malformed):
    """#529 QA P3: the loader rejects a delivered move naming a W0 index; G1's
    whole-header check reads the deck's W0s too, so it sees a later one."""
    db = make_db()
    _packed_deck(db, moves={"6": 8}, w0=w0, retired=False,
                 deliveries=[[4, SERVED], [9, _after(5)]])
    (deck,) = load_decks(engine=db.eng, as_of=_after(2))
    assert deck.exclusion != PACK_INTEGRITY            # the move isn't delivered yet
    g1 = flip_read(db.eng, since=SERVED, as_of=_after(2)).g1
    assert (g1["display_moves_malformed"], g1["status"]) == (malformed,
                                                            "FAIL" if malformed else "PASS")


@pytest.mark.parametrize("moves, malformed", [({"1": 3}, 1), (None, 0)],
                         ids=["a_move", "no_moves"])
def test_g1_on_a_pack_with_no_deliveries(moves, malformed):
    """#529 QA P3: with no deliveries, no move can share one with its anchor."""
    db = make_db()
    _packed_deck(db, moves=moves, deliveries=[], retired=False)
    g1 = flip_read(db.eng, since=SERVED, as_of=_after(2)).g1
    assert (g1["pack_integrity"], g1["display_moves_malformed"]) == (0, malformed)


def test_a_malformed_move_recorded_after_as_of_keeps_a_re_read_stable():
    """F1: the header later records a malformed move for a response delivered
    after as_of. A re-read at the same as_of is the same deck; a read past
    that delivery is pack_integrity; G1 flags it at once."""
    db = make_db()
    as_of = _after(26)
    cards = _packed_deck(db, deliveries=[[4, SERVED]], retired=False)
    (first,) = load_decks(engine=db.eng, as_of=as_of)
    update_pack(db, "j", cards, card_count=10, retired=True, retired_at=_after(27),
                deliveries=[[4, SERVED], [9, _after(26.5)]], display_moves={"6": 6})
    (again,) = load_decks(engine=db.eng, as_of=as_of)
    (later,) = load_decks(engine=db.eng, as_of=_after(28))
    assert first.exclusion is None and first == again
    assert later.exclusion == PACK_INTEGRITY
    assert flip_read(db.eng, since=SERVED, as_of=as_of).g1["status"] == "FAIL"


@pytest.mark.parametrize("moves, expected", [
    ({"2": 5}, {0: 0, 1: 1, 3: 2, 4: 3, 5: 4, 2: 5, 6: 6, 7: 7, 8: 8, 9: 9}),
    ({"3": 6}, {0: 0, 1: 1, 2: 2, 4: 3, 5: 4, 6: 5, 3: 6, 7: 7, 8: 8, 9: 9}),
], ids=["ghosts_between", "ghost_neighbours_of_moved_and_anchor"])
def test_ghost_rows_are_never_moved_or_counted_as_kept(moves, expected):
    """#501 QA P3-4 (QA's probes): ghost rows at 3, 4 and 7 share the
    indexes of real cards; only the non-ghost cards take displayed slots, and
    each ghost's position is what it is with no record."""
    def ghosts(db, record):
        cards = _deck_cards("j", 10)
        write_deck(db.eng, db.packs, cards, full=range(5), ghosts=(3, 4, 7))
        put_pack(db, "j", cards, card_count=10, deliveries=[[9, SERVED]],
                 **({"display_moves": record} if record is not None else {}))
        (deck,) = load_decks(engine=db.eng)
        return deck
    moved, plain = ghosts(make_db(), moves), ghosts(make_db(), None)
    assert moved.exclusion is None and _positions(moved) == expected
    ghost_pos = lambda d: sorted((c.card_index, c.position) for c in d.cards if c.is_ghost)
    assert ghost_pos(moved) == ghost_pos(plain) and len(ghost_pos(moved)) == 3


def test_a_null_display_moves_reads_as_no_moves():
    """#501 QA P3-4: JSON null is the field absent, never malformed."""
    db = make_db()
    cards = _deck_cards("j", 10)
    write_deck(db.eng, db.packs, cards, full=range(5))
    put_pack(db, "j", cards, card_count=10, deliveries=[[9, SERVED]], display_moves=None)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and _positions(deck) == {i: i for i in range(10)}


def test_the_logged_scorer_ranks_by_displayed_position():
    """F2 / #501 QA P3-2: the self-check scorer reproduces a moved deck's
    displayed order, not its build order."""
    db = make_db()
    _packed_deck(db, moves={"2": 4})
    (deck,) = load_decks(engine=db.eng)
    logged = get_scorer("logged")
    ranked = sorted(deck.cards, key=lambda c: -logged.score(card_dict(c)))
    assert [c.card_index for c in ranked] == [0, 1, 3, 4, 2, 5, 6, 7, 8, 9]
    assert [c.position for c in ranked] == list(range(10))


def test_g7_leaves_a_pack_integrity_decks_upgrade_misses_to_g1():
    """#501 QA P3-5: a deck failing its move record is G1's: G7 counts
    neither its upgrade misses nor its row-gone misses."""
    db = make_db()
    _packed_deck(db, moves={"2": 2}, upgrade_misses={"other": 2})
    _packed_deck(db, job="k", upgrade_misses={"restart_split": 1})
    read = flip_read(db.eng, since=SERVED, as_of=_after(2))
    assert read.g1["pack_integrity"] == 1
    assert read.g7["upgrade_misses"] == {"restart_split": 1}
