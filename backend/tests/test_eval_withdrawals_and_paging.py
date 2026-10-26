"""models-lead R2.4 addendum §2–§3 and models-eng's pack-at-first-delivery
changes, the eval side (EXCLUSION_RULE_VERSION 5).

§2, serve-time withdrawals: trades-eng's server writes one deck_card_withdrawals
row per card ownership rule I-1 withdrew. load_decks reads the rows for the
loaded decks (as_of: first_withdrawn_at <= as_of). A served_before=0 card was
never delivered: it is removed from the deck for eval (its card dropped when
present, as a packed card or an undelivered first30 row; never scored, exposed
or ranked) and explains the gap at its index, and the cards after it move up a
DISPLAYED position (LoggedCard.position), which e(k), the IPS weight's
logged-position term and value_model's training position read. A
served_before=1 card keeps its position and outcomes. A served_before=0 row
with a delivered_at, or a withdrawal outside the deck, is withdrawal_conflict.
Ghost rows are ignored by every withdrawal rule.

§3, paging defense in depth: a deck carrying a page-store marker (page_store 1
in a card's features or its pack's run metadata, or an evidence_tier on a
non-ghost row) is never read under the legacy rule (delivered = served) unless
served before PAGING_RELEASED_AT. Without a pack it is delivered where a row's
delivered_at says so, and no_delivery_evidence when nothing does.

In-flight packs: a pack written at first delivery carries run["retired"]; until
it is final (retired by as_of, or past IN_FLIGHT_WINDOW) the deck is in_flight,
and only deliveries made by as_of count. An outcome past a packed deck's last
delivered index is incomplete_deck.

The deck_card_withdrawals table is defined HERE, test-locally, in the agreed
shape (trades-eng builds it in backend/database.py after #370). The paging
tests build deck_impressions bare (test_eval_refresh_and_live_columns) plus
the #370 columns, so they hold whether or not the code's metadata has them.
"""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import (
    Column, Integer, MetaData, Table, Text, UniqueConstraint, create_engine, insert,
)

import backend.eval.data as data_mod
import backend.eval.replay as replay_mod
import backend.value_model as vm
from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval import evidence_pack as ep
from backend.eval.calibration import calibration_pairs, reliability_table
from backend.eval.contract import card_impression_id
from backend.eval.data import (
    CALIBRATION_REFRESH, IN_FLIGHT, INCOMPLETE_DECK, NO_DELIVERY_EVIDENCE, PACK_INTEGRITY,
    PARTIAL_RUN_TIER, WITHDRAWAL_CONFLICT, LoggedCard, LoggedDeck, load_decks,
)
from backend.eval.persistence import run_record
from backend.eval.replay import EXCLUSION_RULE_VERSION, evaluate, exposure_curve, render_report
from backend.eval.scorers import get_scorer
from backend.tests.test_eval_pack_reader import (
    AS_OF, REQUIRED, SERVED, _deck_cards, _row, _Spy, insert_pack, pack_table, write_deck,
)
from backend.tests.test_eval_refresh_and_live_columns import _bare_impressions, _sourced

LATER = "2026-10-23T12:04:00+00:00"
PAGING_COLUMNS = ("evidence_tier", "delivered_at")


def _after(hours: float) -> str:
    """SERVED plus `hours`, ISO UTC."""
    return (datetime.fromisoformat(SERVED) + timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# The withdrawals table, and a DB to write decks into
# ---------------------------------------------------------------------------

def withdrawals_table(md: MetaData) -> Table:
    """deck_card_withdrawals in the shape agreed with trades-eng (models-lead
    R2.4 addendum §2)."""
    return Table(
        "deck_card_withdrawals", md,
        Column("deck_job_id", Text, nullable=False),
        Column("card_index", Integer, nullable=False),      # the build index
        Column("user_id", Text, nullable=False),
        Column("league_id", Text, nullable=False),
        Column("impression_id", Text),
        Column("reason", Text, nullable=False),             # informational only
        Column("first_withdrawn_at", Text, nullable=False),  # ISO UTC
        Column("served_before", Integer, nullable=False),   # 1 iff delivered earlier
        UniqueConstraint("deck_job_id", "card_index"),
    )


@dataclass
class DB:
    eng: object
    packs: Table
    wd: Table | None
    imp: Table


def make_db(live=None, *, withdrawals=True) -> DB:
    """The impression, outcome and pack tables, and (withdrawals=True) the
    withdrawals table. live=None: deck_impressions as the code's metadata
    declares it; else bare (no optional column) plus these Text columns, as
    a DB migrated by #370 has them."""
    md = MetaData()
    imp = (deck_impressions_table.to_metadata(md) if live is None
           else _bare_impressions(md, live))
    deck_outcomes_table.to_metadata(md)
    packs = pack_table(md)
    wd = withdrawals_table(md) if withdrawals else None
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    md.create_all(eng)
    return DB(eng, packs, wd, imp)


def withdraw(db: DB, job, index, served_before, *, at=SERVED, reason="owner_changed"):
    with db.eng.begin() as conn:
        conn.execute(insert(db.wd).values(
            deck_job_id=job, card_index=index, user_id="u1", league_id="lg",
            impression_id=card_impression_id(job, index) if served_before else None,
            reason=reason, first_withdrawn_at=at, served_before=served_before))


def act(db: DB, job, index, *actions, at=SERVED):
    with db.eng.begin() as conn:
        conn.execute(insert(deck_outcomes_table), [
            {"impression_id": card_impression_id(job, index), "action": a, "acted_at": at}
            for a in actions])


def put_deck(db: DB, job, n, *, rows=None, tier=None, delivered=(), ghosts=(), viewed=(),
             w0=(), w1=(), served_at=SERVED, extra=None, source=None):
    """A row deck of n built cards: rows for the indexes in `rows` (default:
    every index not in w0), evidence_tier `tier` (a str, or a function of
    the index) and delivered_at on the indexes in `delivered` where the DB
    has those columns, `extra` merged into each features_json (`source`:
    its deck_source), ghost rows copying `ghosts` (tier 'ghost', never
    delivered), a viewed outcome per listed index, and the withdrawals:
    w0 served_before=0, w1 served_before=1."""
    cards = _deck_cards(job, n, served_at=served_at)
    cards = _sourced([{**c, **(extra or {})} for c in cards], source)
    rows = [i for i in range(n) if i not in w0] if rows is None else rows
    tier_of = tier if callable(tier) else (lambda _i: tier)
    out = [{**_row(cards[i]), "evidence_tier": tier_of(i),
            "delivered_at": served_at if i in delivered else None} for i in rows]
    out += [{**_row(cards[i], ghost=True), "evidence_tier": "ghost", "delivered_at": None}
            for i in ghosts]
    keys = [k for k in db.imp.c.keys() if any(k in r for r in out)]
    with db.eng.begin() as conn:
        if out:
            conn.execute(insert(db.imp), [{k: r.get(k) for k in keys} for r in out])
    for i in viewed:
        act(db, job, i, "viewed", at=served_at)
    for i in w0:
        withdraw(db, job, i, 0, at=served_at)
    for i in w1:
        withdraw(db, job, i, 1, at=served_at)


def put_pack(db: DB, job, cards, *, card_count, deliveries, served_at=SERVED, **run):
    """A pack row for `cards` (the packed card dicts) with run metadata
    `run` (e.g. retired, retired_at, page_store) and `deliveries`."""
    packed = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": served_at,
                          "deliveries": deliveries, **run}, cards, card_count=card_count)
    with db.eng.begin() as conn:
        insert_pack(conn, db.packs, run_id=job, user_id="u1", league_id="lg",
                    served_at=served_at, packed=packed)


def update_pack(db: DB, job, cards, *, card_count, deliveries, served_at=SERVED, **run):
    """The writer's later-delivery update: the header (deliveries, retired)
    and its checksum change; the cards blob is the build's."""
    packed = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": served_at,
                          "deliveries": deliveries, **run}, cards, card_count=card_count)
    with db.eng.begin() as conn:
        conn.execute(db.packs.update().where(db.packs.c.run_id == job).values(**asdict(packed)))


def _by_job(decks):
    return {d.deck_job_id: d for d in decks}


# A fitted value model (as test_eval_pack_reader's U2 test): value_model
# scores and emits P(like), so it grades and calibrates here.
_MODEL = vm.ValueModel(
    like_head=vm.LogisticHead(weights={"bias": -0.4, "value_delta": 0.8, "pref_long": 1.1,
                                       "pref_short": -0.6, "partner_rate": 0.9}),
    propose_head=None, propose_constant=0.2,
    partner_rates={"u1|opp1": 0.7}, global_like_rate=0.3, position_mean=0.4,
    trained_at="t", train_date="t")


# ---------------------------------------------------------------------------
# The equivalence (models-lead's words): a deck with recorded withdrawals
# replays exactly as if the withdrawn, never-delivered cards had never been
# generated.
# ---------------------------------------------------------------------------

# (deck_job_id, build N, never-delivered withdrawn indexes). "a" is the
# ruling's deck; the rest put withdrawals at the head, the tail, in a run, or
# nowhere.
EQUIV_DECKS = (("a", 10, {3, 6}), ("b", 12, {0}), ("c", 9, {8}), ("d", 11, set()),
               ("e", 10, {1, 2, 5}))
# rows / packed: the withdrawn cards are absent. *_present: they are there, as
# rows (no delivered_at) or as packed cards and first30 rows (the pack holds
# every built card), and are dropped.
EQUIV_MODES = ("rows", "rows_present", "packed", "packed_present")


def _actions(d, p):
    """The outcomes on the kept card at displayed position p of deck d."""
    if not (p < 5 or (p + d) % 3 == 0):
        return ()
    liked = (p + d) % 2 == 0
    acts = ["viewed", "like" if liked else "pass"]
    if liked and p % 3 == 0:
        acts.append("propose")
    if (d, p) == (2, 1):
        acts.append("undo")
    return acts


def _equivalent_dbs(mode: str):
    """(A, B). A: the decks as built (build N cards), the withdrawn indexes
    recorded served_before=0. B: the same kept cards re-indexed 0..K-1,
    nothing withdrawn. Packed: rows for build indexes below 5, the rest
    packed (A's pack card_count N, B's K), pages delivered through displayed
    positions 3 and K-2 (A's boundaries in build index space), and outcomes
    only on delivered cards."""
    a, b = make_db(), make_db()
    packed = mode.startswith("packed")
    for d, (job, n, w0) in enumerate(EQUIV_DECKS):
        cards = _deck_cards(job, n)
        kept = [i for i in range(n) if i not in w0]
        k = len(kept)
        reindexed = [{**cards[i], "card_index": p} for p, i in enumerate(kept)]
        for i in sorted(w0):
            withdraw(a, job, i, 0)
        built = range(n) if mode.endswith("present") else kept
        bounds = [3, k - 2]
        if packed:
            write_deck(a.eng, a.packs, cards, full={i for i in built if i < 5},
                       packed={i for i in built if i >= 5}, card_count=n,
                       deliveries=[[kept[bounds[0]], SERVED], [kept[bounds[1]], LATER]])
            write_deck(b.eng, b.packs, reindexed,
                       full={p for p, i in enumerate(kept) if i < 5},
                       packed={p for p, i in enumerate(kept) if i >= 5}, card_count=k,
                       deliveries=[[bounds[0], SERVED], [bounds[1], LATER]])
        else:
            write_deck(a.eng, a.packs, cards, full=built)
            write_deck(b.eng, b.packs, reindexed, full=range(k))
        for p, i in enumerate(kept):
            if packed and p > bounds[1]:
                continue
            acts = _actions(d, p)
            if acts:
                act(a, job, i, *acts)
                act(b, job, p, *acts)
    return a, b


@pytest.mark.parametrize("mode", EQUIV_MODES)
def test_withdrawn_never_delivered_cards_replay_as_if_never_generated(monkeypatch, mode):
    db_a, db_b = _equivalent_dbs(mode)
    a, b = load_decks(engine=db_a.eng), load_decks(engine=db_b.eng)
    removed = sum(len(w0) for _job, _n, w0 in EQUIV_DECKS)
    assert [d.deck_job_id for d in a] == [d.deck_job_id for d in b]
    assert [d.exclusion for d in a] == [d.exclusion for d in b] == [None] * len(EQUIV_DECKS)
    assert [d.withdrawn_removed for d in a] == [len(w0) for _j, _n, w0 in EQUIV_DECKS]
    assert all(d.withdrawn_removed == 0 for d in b)
    assert [len(d.cards) for d in a] == [len(d.cards) for d in b]
    # A kept card sits at its displayed position: B's index, not A's past a withdrawal.
    assert ([[c.position for c in d.cards] for d in a]
            == [[c.card_index for c in d.cards] for d in b])
    assert any(c.position != c.card_index for d in a for c in d.cards)
    assert ([[(c.delivered, c.viewed, c.liked, c.proposed, c.undone) for c in d.cards]
             for d in a]
            == [[(c.delivered, c.viewed, c.liked, c.proposed, c.undone) for c in d.cards]
                for d in b])
    assert mode.startswith("packed") == (not all(c.delivered for d in a for c in d.cards))
    assert exposure_curve(a) == exposure_curve(b)

    monkeypatch.setattr(vm, "load_latest_model", lambda: _MODEL)
    for name in ("logged", "production", "base_score", "random", "value_model"):
        run_a = evaluate(get_scorer(name, seed=3), a, ess_min=1, bootstrap=200, seed=7)
        run_b = evaluate(get_scorer(name, seed=3), b, ess_min=1, bootstrap=200, seed=7)
        assert run_a.withdrawn_removed_cards == removed and run_b.withdrawn_removed_cards == 0
        assert replace(run_a, withdrawn_removed_cards=0) == run_b, name
        like = run_a.metrics["like"]
        assert like.n > 10 and like.ci_low is not None and like.ips_ci_low is not None, name

    pairs_a, excluded_a = calibration_pairs(get_scorer("value_model"), a)
    pairs_b, excluded_b = calibration_pairs(get_scorer("value_model"), b)
    assert pairs_a and pairs_a == pairs_b and excluded_a == excluded_b
    assert reliability_table(pairs_a) == reliability_table(pairs_b)
    assert vm.build_training_rows(a) == vm.build_training_rows(b)


def test_removed_cards_are_reported_and_recorded_and_the_version_is_5():
    db_a, _db_b = _equivalent_dbs("rows")
    run = evaluate(_Spy(), load_decks(engine=db_a.eng), ess_min=1, bootstrap=0, seed=0)
    removed = sum(len(w0) for _job, _n, w0 in EQUIV_DECKS)
    assert run.withdrawn_removed_cards == removed
    assert sum(run.excluded.values()) + run.n_included == run.n_total   # not an exclusion
    text = render_report([run], run)
    assert f"withdrawn_removed_cards={removed}" in text and "WARNING" not in text
    assert "Exclusion rules: version 5." in text
    record = run_record(run, run)
    assert record["withdrawn_removed_cards"] == removed
    assert EXCLUSION_RULE_VERSION == 5 == run.exclusion_rule_version == record[
        "exclusion_rule_version"]


# ---------------------------------------------------------------------------
# Present W0 cards, served_before=1, gaps, conflicts
# ---------------------------------------------------------------------------

def test_a_packed_card_or_an_undelivered_first30_row_at_a_withdrawn_index_is_removed():
    """The pack (written at first delivery) holds every built card; the first
    30 rows were written then too. 3 (a first30 row, delivered_at NULL) and
    7 (a packed card) were withdrawn before they were delivered."""
    db = make_db(live=PAGING_COLUMNS)
    cards = _deck_cards("j", 10)
    put_deck(db, "j", 10, rows=range(5), tier="first30", delivered=[0, 1, 2, 4],
             w0=[3, 7], viewed=[0, 4])
    put_pack(db, "j", cards, card_count=10, deliveries=[[8, SERVED]])
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and deck.withdrawn_removed == 2
    assert [c.card_index for c in deck.cards] == [0, 1, 2, 4, 5, 6, 8, 9]
    assert [c.position for c in deck.cards] == list(range(8))
    assert [c.delivered for c in deck.cards] == [True] * 7 + [False]   # through build 8
    assert exposure_curve([deck]) == {0: 2 / 3, 1: 1 / 3, 2: 1 / 3, 3: 2 / 3, 4: 1 / 3,
                                      5: 1 / 3, 6: 1 / 3}


def test_a_delivered_withdrawal_keeps_its_card_position_and_outcomes():
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), full={*range(10)} - {2}, viewed=[4, 5])
    act(db, "j", 4, "like")
    withdraw(db, "j", 2, 0)      # never delivered: removed
    withdraw(db, "j", 4, 1)      # delivered, then withdrawn: stays
    write_deck(db.eng, db.packs, _deck_cards("k", 10), full=range(10), viewed=[4])
    withdraw(db, "k", 4, 1)
    by_job = _by_job(load_decks(engine=db.eng))
    j, k = by_job["j"], by_job["k"]
    assert j.exclusion is None and j.withdrawn_removed == 1
    assert [c.position for c in j.cards] == list(range(9))
    four = next(c for c in j.cards if c.card_index == 4)
    assert four.position == 3 and four.delivered and four.viewed and four.liked
    assert k.exclusion is None and k.withdrawn_removed == 0
    assert [c.position for c in k.cards] == list(range(10)) and k.cards[4].viewed
    assert exposure_curve([k])[4] == 2 / 3


@pytest.mark.parametrize("layout", [
    {"full": {*range(10)} - {2, 5}},                                       # rows
    {"full": {0, 1, 3, 4}, "packed": {6, 7, 8, 9}, "card_count": 10},      # packed
], ids=["rows", "packed"])
def test_a_delivered_withdrawal_with_no_card_is_an_unexplained_gap(layout):
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), **layout)
    withdraw(db, "j", 2, 0)
    withdraw(db, "j", 5, 1)      # delivered: its card should be there
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == INCOMPLETE_DECK


@pytest.mark.parametrize("layout", [
    {"full": {*range(10)} - {3, 7}},                                       # a row lost
    {"full": {0, 1, 2, 4}, "packed": {5, 6, 8, 9}, "card_count": 10},      # a card unpacked
    {"full": {0, 1, 2, 4}, "packed": {5, 6, 7, 8}, "card_count": 10},      # the tail lost
], ids=["rows", "packed", "pack_tail"])
def test_an_unexplained_gap_is_still_incomplete(layout):
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), **layout)
    withdraw(db, "j", 3, 0)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == INCOMPLETE_DECK


def test_a_trailing_delivered_withdrawal_with_no_card_and_no_pack_is_a_gap():
    """Without a pack every withdrawal index bounds N: index 5 is the deck's
    sixth card, delivered and lost, not a withdrawal outside the deck."""
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 6), full=range(5))
    withdraw(db, "j", 5, 1)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == INCOMPLETE_DECK


@pytest.mark.parametrize("layout, withdrawals", [
    ({"full": range(10), "packed": (), "card_count": 10}, [(10, 0)]),      # W0 past card_count
    ({"full": range(10), "packed": (), "card_count": 10}, [(12, 1)]),      # W1 past card_count
    ({"full": range(1, 10)}, [(0, 0), (-1, 0)]),                           # a negative index
], ids=["w0_past_card_count", "w1_past_card_count", "negative"])
def test_a_withdrawal_outside_the_deck_is_a_conflict(layout, withdrawals):
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), viewed=[1], **layout)
    for index, served_before in withdrawals:
        withdraw(db, "j", index, served_before)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == WITHDRAWAL_CONFLICT


@pytest.mark.parametrize("packed", [False, True], ids=["rows", "packed"])
def test_a_never_delivered_withdrawal_whose_row_was_delivered_is_a_conflict(packed):
    """The evidence says the user got the card the withdrawal says they never got."""
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "j", 10, rows=range(5) if packed else range(10), tier="first30",
             delivered=range(5), w0=[3])
    if packed:
        put_pack(db, "j", _deck_cards("j", 10), card_count=10, deliveries=[[9, SERVED]])
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == WITHDRAWAL_CONFLICT


def test_replay_and_calibration_exclude_a_conflict_deck_whole_and_count_it():
    db = make_db(live=PAGING_COLUMNS)
    for job in ("good1", "good2"):
        put_deck(db, job, 12, viewed=range(0, 12, 2))
    put_deck(db, "bad", 12, rows=range(12), delivered=[4], w0=[4], viewed=range(12))
    decks = load_decks(engine=db.eng)
    by_job = _by_job(decks)
    good = [by_job["good1"], by_job["good2"]]
    assert by_job["bad"].exclusion == WITHDRAWAL_CONFLICT
    spy = _Spy()
    run = evaluate(spy, decks, ess_min=1, bootstrap=50, seed=0)
    assert run.excluded["withdrawal_conflict"] == 12 and run.withdrawal_conflict_decks == 1
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert spy.scored == {"good1", "good2"} and run.withdrawn_removed_cards == 0
    assert exposure_curve(decks) == exposure_curve(good)
    alone = evaluate(_Spy(), good, ess_min=1, bootstrap=50, seed=0)
    assert run.metrics == alone.metrics
    text = render_report([run], run)
    assert "withdrawal_conflict=12" in text and "withdrawal_conflict_decks=1" in text
    record = run_record(run, run)
    assert record["withdrawal_conflict_decks"] == 1
    assert record["excluded"]["withdrawal_conflict"] == 12
    _pairs, excluded = calibration_pairs(_Spy(), decks)
    assert excluded["withdrawal_conflict"] == 12


@pytest.mark.parametrize("packed", [False, True], ids=["rows", "packed"])
def test_a_ghost_row_at_a_withdrawn_index_is_ignored(packed):
    db = make_db()
    layout = ({"full": {0, 1, 2}, "packed": range(4, 10), "card_count": 10} if packed
              else {"full": {*range(10)} - {3}})
    write_deck(db.eng, db.packs, _deck_cards("j", 10), ghosts=[3], **layout)
    withdraw(db, "j", 3, 0)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None and deck.withdrawn_removed == 1
    (ghost,) = [c for c in deck.cards if c.is_ghost]
    assert ghost.card_index == ghost.position == 3            # no withdrawal rule touches it
    assert [c.position for c in deck.cards if not c.is_ghost] == list(range(9))


# ---------------------------------------------------------------------------
# The read: as_of, scope, chunking, and no table
# ---------------------------------------------------------------------------

def test_as_of_reads_only_withdrawals_first_withdrawn_by_then():
    db = make_db()
    write_deck(db.eng, db.packs, _deck_cards("j", 10), full={*range(10)} - {3}, viewed=[4])
    withdraw(db, "j", 3, 0, at="2026-10-23T13:00:00+00:00")
    (before,) = load_decks(engine=db.eng, as_of="2026-10-23T12:30:00+00:00")
    (at,) = load_decks(engine=db.eng, as_of="2026-10-23T13:00:00+00:00")
    (no_clock,) = load_decks(engine=db.eng)
    assert before.exclusion == INCOMPLETE_DECK and before.withdrawn_removed == 0
    assert at.exclusion is None and at.withdrawn_removed == 1
    assert at.cards[3].card_index == 4 and at.cards[3].position == 3
    assert no_clock.exclusion is None and no_clock.withdrawn_removed == 1


def test_withdrawals_are_read_for_every_loaded_deck_past_one_chunk():
    db = make_db()
    jobs = [f"j{d:03d}" for d in range(520)]
    with db.eng.begin() as conn:
        conn.execute(insert(deck_impressions_table),
                     [_row(c) for job in jobs for c in _deck_cards(job, 3) if c["card_index"] != 1])
        conn.execute(insert(db.wd), [
            {"deck_job_id": job, "card_index": 1, "user_id": "u1", "league_id": "lg",
             "reason": "owner_changed", "first_withdrawn_at": SERVED, "served_before": 0}
            for job in jobs])
    decks = load_decks(engine=db.eng)
    assert len(decks) == 520
    assert all(d.exclusion is None and d.withdrawn_removed == 1 for d in decks)


def test_without_the_table_or_the_decks_rows_nothing_changes():
    loaded = []
    for withdrawals in (False, True):
        db = make_db(withdrawals=withdrawals)
        write_deck(db.eng, db.packs, _deck_cards("j", 34), full=range(30), packed=range(30, 34),
                   ghosts=[5], viewed=[0, 3, 12], deliveries=[[19, SERVED]])
        write_deck(db.eng, db.packs, _deck_cards("old", 12), full={*range(12)} - {4})
        if withdrawals:
            withdraw(db, "other", 4, 0)     # another deck's: not read
        loaded.append(load_decks(engine=db.eng))
    without, with_table = loaded
    assert without == with_table
    assert [d.exclusion for d in without] == [None, INCOMPLETE_DECK]
    assert all(c.position == c.card_index for d in without for c in d.cards)
    assert all(d.withdrawn_removed == 0 for d in without)


# ---------------------------------------------------------------------------
# Paging (R2.4 addendum §3): marked decks are never legacy
# ---------------------------------------------------------------------------

def test_a_paged_row_deck_counts_only_rows_with_delivered_at():
    """#370 stage 1 writes every card a row; the full_interim / archive rows
    of undelivered cards must not count as served."""
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "interim", 10, tier=lambda i: "first30" if i < 4 else "full_interim",
             delivered=range(6), viewed=[0, 1, 2, 5])
    put_deck(db, "archive", 8, tier="archive", delivered=range(4), viewed=[0, 3])
    decks = load_decks(engine=db.eng)
    by_job = _by_job(decks)
    assert [d.exclusion for d in decks] == [None, None]
    assert [c.delivered for c in by_job["interim"].cards] == [i < 6 for i in range(10)]
    assert [c.delivered for c in by_job["archive"].cards] == [i < 4 for i in range(8)]
    # served: 0-3 twice, 4-5 once; viewed: 0 twice, 1, 2, 3 and 5 once
    assert exposure_curve(decks) == {0: 3 / 4, 1: 2 / 4, 2: 2 / 4, 3: 2 / 4, 4: 1 / 3, 5: 2 / 3}


@pytest.mark.parametrize("live, deck, delivered", [
    (PAGING_COLUMNS, {"tier": "first30"}, [True] * 3 + [False] * 3),
    (("delivered_at",), {"extra": {"page_store": 1}}, [True] * 3 + [False] * 3),
    (("features_compact", "delivered_at"), {"compact": True}, [True] * 3 + [False] * 3),
    (PAGING_COLUMNS, {}, [True] * 6),                                   # unmarked: legacy
    (PAGING_COLUMNS, {"extra": {"page_store": 0}}, [True] * 6),
    (PAGING_COLUMNS, {"ghosts": [2]}, [True] * 7),                      # a ghost's tier doesn't mark
], ids=["evidence_tier", "page_store", "page_store_compact", "unmarked", "page_store_0",
        "ghost_tier"])
def test_a_marker_takes_delivered_from_the_rows(live, deck, delivered):
    db, deck = make_db(live=live), dict(deck)
    if deck.pop("compact", False):
        cards = _deck_cards("j", 6)
        rows = [{**_row(c), "features_json": None,
                 "features_compact": '{"shape": "2x1", "page_store": 1}',
                 "delivered_at": SERVED if c["card_index"] < 3 else None} for c in cards]
        with db.eng.begin() as conn:
            conn.execute(insert(db.imp), rows)
    else:
        put_deck(db, "j", 6, delivered=range(3), **deck)
    (got,) = load_decks(engine=db.eng)
    assert got.exclusion is None
    assert [c.delivered for c in got.cards] == delivered


@pytest.mark.parametrize("live, deck", [
    (("evidence_tier",), {"tier": "first30"}),                          # no delivered_at column
    (PAGING_COLUMNS, {"tier": "first30"}),                              # every delivered_at NULL
    (PAGING_COLUMNS, {"tier": "first30", "ghosts": [1], "ghost_delivered": True}),
    (("delivered_at",), {"extra": {"page_store": 1}}),
], ids=["no_column", "all_null", "only_a_ghost", "page_store"])
def test_a_paged_deck_without_delivery_evidence_is_excluded(live, deck):
    db, deck = make_db(live=live), dict(deck)
    ghost_delivered = deck.pop("ghost_delivered", False)
    put_deck(db, "j", 6, viewed=[0, 1], **deck)
    if ghost_delivered:
        with db.eng.begin() as conn:
            conn.execute(db.imp.update().where(db.imp.c.is_ghost == 1)
                         .values(delivered_at=SERVED))
    put_deck(db, "good", 6, viewed=[0, 1])             # unmarked: legacy, whatever the columns
    decks = load_decks(engine=db.eng)
    by_job = _by_job(decks)
    assert by_job["j"].exclusion == NO_DELIVERY_EVIDENCE and by_job["good"].exclusion is None
    run = evaluate(_Spy(), decks, ess_min=1, bootstrap=0, seed=0)
    n = len(by_job["j"].cards)
    assert run.excluded["no_delivery_evidence"] == n and run.no_delivery_evidence_decks == 1
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert exposure_curve(decks) == exposure_curve([by_job["good"]])
    assert f"no_delivery_evidence={n}" in render_report([run], run)
    assert "no_delivery_evidence_decks=1" in render_report([run], run)
    record = run_record(run, run)
    assert record["no_delivery_evidence_decks"] == 1
    assert record["excluded"]["no_delivery_evidence"] == n
    _pairs, excluded = calibration_pairs(_Spy(), decks)
    assert excluded["no_delivery_evidence"] == n


@pytest.mark.parametrize("released, legacy", [
    (None, False),                                     # marker-only
    ("2026-10-24T00:00:00+00:00", True),               # served before the release
    (SERVED, False),                                   # served at it
], ids=["unset", "before", "at"])
def test_paging_released_at_keeps_older_marked_decks_legacy(monkeypatch, released, legacy):
    monkeypatch.setattr(data_mod, "PAGING_RELEASED_AT", released)
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "some", 6, tier="first30", delivered=range(3))
    put_deck(db, "none", 6, tier="first30")
    put_deck(db, "plain", 6)                           # unmarked: always legacy
    by_job = _by_job(load_decks(engine=db.eng))
    assert by_job["plain"].exclusion is None and all(c.delivered for c in by_job["plain"].cards)
    if legacy:
        assert by_job["some"].exclusion is by_job["none"].exclusion is None
        assert all(c.delivered for c in by_job["some"].cards + by_job["none"].cards)
    else:
        assert [c.delivered for c in by_job["some"].cards] == [True] * 3 + [False] * 3
        assert by_job["none"].exclusion == NO_DELIVERY_EVIDENCE


@pytest.mark.parametrize("marker", ["evidence_tier", "run_metadata"])
def test_a_marked_packed_deck_takes_delivered_from_its_deliveries(marker):
    """The rows' delivered_at (only 0-1, or none) disagree with the pack's
    deliveries (through 6): the pack wins, and a pack is evidence enough."""
    db = make_db(live=PAGING_COLUMNS)
    put_deck(db, "j", 10, rows=range(5), tier="first30" if marker == "evidence_tier" else None,
             delivered=range(2) if marker == "evidence_tier" else ())
    run = {"page_store": 1} if marker == "run_metadata" else {}
    put_pack(db, "j", _deck_cards("j", 10)[5:], card_count=10, deliveries=[[6, SERVED]], **run)
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion is None
    assert [c.delivered for c in deck.cards] == [i <= 6 for i in range(10)]


# ---------------------------------------------------------------------------
# In-flight packs (written at first delivery) and outcome consistency
# ---------------------------------------------------------------------------

def _first_delivery_deck(db, job="j", n=10):
    """Rows for the first 5 and a pack of every built card, as the writer
    leaves them at first delivery."""
    cards = _deck_cards(job, n)
    write_deck(db.eng, db.packs, cards, full=range(5), viewed=[0, 2])
    return cards


@pytest.mark.parametrize("run, as_of, final", [
    ({"retired": False}, _after(2), False),                         # within the window
    ({"retired": False}, _after(26), True),                         # past it: final
    ({"retired": False}, None, False),                              # no clock: not retired
    ({"retired": True, "retired_at": _after(3)}, _after(2), False),  # retired after as_of
    ({"retired": True, "retired_at": _after(3)}, _after(3), True),   # retired by as_of
    ({"retired": True, "retired_at": _after(3)}, None, True),
    ({}, _after(2), True),                                          # no key: written at retirement
    ({}, None, True),
], ids=["unretired_live", "unretired_past_window", "unretired_no_clock", "retired_after",
        "retired_by", "retired_no_clock", "legacy", "legacy_no_clock"])
def test_a_pack_is_in_flight_until_final(run, as_of, final):
    db = make_db()
    cards = _first_delivery_deck(db)
    put_pack(db, "j", cards, card_count=10, deliveries=[[4, SERVED]], **run)
    (deck,) = load_decks(engine=db.eng, as_of=as_of)
    assert deck.exclusion == (None if final else IN_FLIGHT)
    if final:
        assert [c.delivered for c in deck.cards] == [i <= 4 for i in range(10)]
    replay = evaluate(_Spy(), [deck], ess_min=1, bootstrap=0, seed=0)
    assert replay.in_flight_decks == (0 if final else 1)


def test_deliveries_after_as_of_are_not_read_and_a_re_read_is_stable():
    """The writer updates the header after as_of (a later page, then the
    retirement); a re-read at the same as_of is the same deck."""
    db = make_db()
    cards = _first_delivery_deck(db)
    as_of = _after(26)                       # past the window: final, unretired or not
    put_pack(db, "j", cards, card_count=10, deliveries=[[4, SERVED]], retired=False)
    (first,) = load_decks(engine=db.eng, as_of=as_of)
    update_pack(db, "j", cards, card_count=10, retired=True, retired_at=_after(27),
                deliveries=[[4, SERVED], [9, _after(26.5)]])
    act(db, "j", 7, "viewed", at=_after(26.6))
    (again,) = load_decks(engine=db.eng, as_of=as_of)
    (later,) = load_decks(engine=db.eng, as_of=_after(28))
    assert first.exclusion is None and first == again
    assert [c.delivered for c in again.cards] == [i <= 4 for i in range(10)]
    assert later.exclusion is None and all(c.delivered for c in later.cards)
    assert later.cards[7].viewed and not again.cards[7].viewed


@pytest.mark.parametrize("where, inconsistent", [
    ("packed", True),          # a packed card past the deliveries has an outcome
    ("row", True),             # an upgraded row past them does
    ("ghost", False),          # a ghost row's outcome is not a card's
    ("withdrawn", False),      # a removed card is not in the deck
    ("delivered", False),
], ids=lambda v: str(v))
def test_an_outcome_past_the_last_delivery_means_under_recorded_deliveries(where, inconsistent):
    db = make_db()
    cards = _deck_cards("j", 10)
    full = {*range(5), 7} if where == "row" else range(5)
    write_deck(db.eng, db.packs, cards, full=full, packed=range(10), ghosts=[8],
               deliveries=[[5, SERVED]], viewed=[0, 2])
    if where == "ghost":
        with db.eng.begin() as conn:
            conn.execute(insert(deck_outcomes_table).values(
                impression_id=f"{card_impression_id('j', 8)}:ghost", action="viewed",
                acted_at=SERVED))
    elif where == "withdrawn":
        withdraw(db, "j", 9, 0)
        act(db, "j", 9, "viewed")
    else:
        act(db, "j", {"packed": 7, "row": 7, "delivered": 5}[where], "viewed")
    (deck,) = load_decks(engine=db.eng)
    assert deck.exclusion == (INCOMPLETE_DECK if inconsistent else None)


# ---------------------------------------------------------------------------
# Precedence: calibration_refresh → pack_integrity → withdrawal_conflict →
# in_flight / lost pack → incomplete_deck → no_delivery_evidence; replay and
# calibration put calibration_refresh, then partial_run, first.
# ---------------------------------------------------------------------------

def test_loader_precedence_among_the_new_reasons_and_the_old():
    db = make_db(live=PAGING_COLUMNS)
    conflict = {"rows": range(8), "delivered": [3], "w0": [3]}     # W0's row was delivered
    put_deck(db, "refresh_conflict", 8, source="grading_refresh", **conflict)
    put_deck(db, "conflict_gap", 8, rows={*range(8)} - {6}, delivered=[3], w0=[3])
    put_deck(db, "conflict_undelivered", 8, tier="first30", **conflict)
    put_deck(db, "gap_undelivered", 8, tier="first30", rows={*range(8)} - {6})
    put_deck(db, "undelivered", 8, tier="first30")
    write_deck(db.eng, db.packs, _deck_cards("bad_pack_conflict", 10), full=range(5),
               packed=range(5, 10), edit=lambda p: replace(p, checksum="0" * 64))
    withdraw(db, "bad_pack_conflict", 15, 0)
    # An unretired pack within the window: in flight, after a conflict, before a gap.
    for job, w0 in (("in_flight_conflict", [2]), ("in_flight_gap", [])):
        cards = _deck_cards(job, 10)
        put_deck(db, job, 10, rows=range(5) if w0 else range(4), tier="first30",
                 delivered=range(5), w0=w0, viewed=[0])
        put_pack(db, job, cards[5:], card_count=10, deliveries=[[4, SERVED]], retired=False)
    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=db.eng, as_of=_after(2))}
    assert got == {
        "refresh_conflict": CALIBRATION_REFRESH,
        "bad_pack_conflict": PACK_INTEGRITY,
        "conflict_gap": WITHDRAWAL_CONFLICT,
        "conflict_undelivered": WITHDRAWAL_CONFLICT,
        "in_flight_conflict": WITHDRAWAL_CONFLICT,
        "in_flight_gap": IN_FLIGHT,
        "gap_undelivered": INCOMPLETE_DECK,
        "undelivered": NO_DELIVERY_EVIDENCE,
    }


def test_a_conflict_comes_before_a_missing_pack_and_in_flight_before_delivery(monkeypatch):
    monkeypatch.setattr(data_mod, "PACK_REQUIRED_SINCE", REQUIRED)
    db = make_db(live=PAGING_COLUMNS)
    live, lost = "2026-10-23T12:00:00+00:00", "2026-10-21T12:00:00+00:00"
    conflict = {"rows": range(8), "delivered": [3], "w0": [3]}
    put_deck(db, "live_conflict", 8, served_at=live, **conflict)
    put_deck(db, "lost_conflict", 8, served_at=lost, **conflict)
    put_deck(db, "live_undelivered", 8, tier="first30", served_at=live)
    put_deck(db, "lost_undelivered", 8, tier="first30", served_at=lost)
    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=db.eng, as_of=AS_OF)}
    assert got == {"live_conflict": WITHDRAWAL_CONFLICT, "lost_conflict": WITHDRAWAL_CONFLICT,
                   "live_undelivered": IN_FLIGHT, "lost_undelivered": INCOMPLETE_DECK}


def test_replay_and_calibration_put_refresh_then_partial_run_first():
    db = make_db(live=PAGING_COLUMNS)
    partial = lambda i: PARTIAL_RUN_TIER if i == 2 else "first30"
    put_deck(db, "partial_undelivered", 6, tier=partial, viewed=range(6))
    put_deck(db, "partial_conflict", 6, tier=partial, delivered=range(6), rows=range(6),
             w0=[4], viewed=range(6))
    put_deck(db, "refresh_partial_conflict", 6, tier=partial, source="grading_refresh",
             delivered=range(6), rows=range(6), w0=[4], viewed=range(6))
    decks = load_decks(engine=db.eng)
    assert {d.deck_job_id: d.exclusion for d in decks} == {
        "partial_undelivered": NO_DELIVERY_EVIDENCE,
        "partial_conflict": WITHDRAWAL_CONFLICT,
        "refresh_partial_conflict": CALIBRATION_REFRESH,
    }
    run = evaluate(_Spy(), decks, ess_min=1, bootstrap=0, seed=0)
    assert run.excluded["partial_run"] == 12 and run.partial_run_decks == 2
    assert run.excluded["calibration_refresh"] == 6 and run.calibration_refresh_decks == 1
    assert run.no_delivery_evidence_decks == run.withdrawal_conflict_decks == 0
    _pairs, excluded = calibration_pairs(_Spy(), decks)
    assert excluded["calibration_refresh"] == 6 and excluded["partial_run"] == 2
    assert excluded["no_delivery_evidence"] == 5 and excluded["withdrawal_conflict"] == 5


# ---------------------------------------------------------------------------
# release-lead's #406 QA P3s: refresh decks in fit rows and in packs
# ---------------------------------------------------------------------------

def test_a_packed_deck_whose_run_metadata_says_grading_refresh_is_calibration_refresh():
    db = make_db()
    for job, run in (("refresh", {"deck_source": "grading_refresh"}), ("trades", {})):
        cards = _deck_cards(job, 10)
        write_deck(db.eng, db.packs, cards, full=range(5))
        put_pack(db, job, cards[5:], card_count=10, deliveries=[[9, SERVED]], **run)
    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=db.eng)}
    assert got == {"refresh": CALIBRATION_REFRESH, "trades": None}


def test_fit_rows_skip_only_calibration_refresh_decks():
    db = make_db()
    put_deck(db, "refresh", 4, source="grading_refresh")
    put_deck(db, "trades", 4)
    put_deck(db, "gap", 4, rows=[0, 2])
    decks = load_decks(engine=db.eng)
    assert {r["card"]["deck_job_id"] for r in replay_mod._fit_rows(decks)} == {"trades", "gap"}


# ---------------------------------------------------------------------------
# value_model's training-only position feature reads the displayed position
# ---------------------------------------------------------------------------

def test_the_value_model_position_feature_is_the_displayed_position():
    def card(index, position=None):
        return LoggedCard(
            impression_id=f"j:{index}", deck_job_id="j", user_id="u1", league_id="lg",
            card_index=index, trade_hash=None, propensity=1.0, base_score=1.0,
            final_score=1.0, archetype=None, shape_bucket=None, served_at=SERVED,
            features={"partner_user_id": "opp1"}, viewed=True, liked=True, position=position)

    assert card(7).position == 7                          # defaults to card_index
    cards = [card(0, 0), card(2, 1), card(5, 3), card(40, 30), card(9)]
    like_rows, propose_rows = vm.build_training_rows(
        [LoggedDeck(deck_job_id="j", user_id="u1", league_id="lg", served_at=SERVED,
                    cards=cards)])
    assert [r["position"] for r in like_rows] == [0.0, 0.1, 0.3, 1.0, 0.9]
    assert [r["position"] for r in propose_rows] == [0.0, 0.1, 0.3, 1.0, 0.9]
