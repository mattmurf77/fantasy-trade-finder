"""ADR-025 stage 2, the reader side: backend.eval.data.load_decks merges
deck_evidence_packs into decks (C7 (i)); replay excludes a deck whose pack
fails integrity, whose card indexes have a gap, or whose required pack is
lost or not yet written (in_flight), whole and never sunk, and calibration
excludes its cards (C7 (iv)); the exposure model counts delivered positions
(R4.2 U1); outcomes join packed cards by their deterministic id (U2); every
run carries EXCLUSION_RULE_VERSION (R2.5 (2)).

The pack table is defined HERE, test-locally (pack_table): it is the row
contract trades-eng builds in backend/database.py
(docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6). The golden
over real decks (C7 (ii)) is in test_evidence_pack.py.
"""

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import (
    Column, Index, Integer, LargeBinary, MetaData, String, Table, Text, create_engine, insert,
)

from backend.database import deck_impressions_table, deck_outcomes_table, metadata
from backend.eval import evidence_pack as ep
import backend.eval.data as data_mod
import backend.eval.replay as replay_mod
import backend.value_model as vm
from backend.eval.calibration import calibration_pairs
from backend.eval.contract import FROZEN_INPUT_KEYS, PROJECTION_KEYS, card_impression_id
from backend.eval.data import (
    IN_FLIGHT, INCOMPLETE_DECK, PACK_INTEGRITY, card_dict, load_decks,
)
from backend.eval.persistence import record_rule_version, run_record
from backend.eval.replay import (
    EXCLUSION_RULE_VERSION, evaluate, exposure_curve, render_report, rule_version_note, verdict,
)
from backend.eval.scorers import get_scorer, registered_names

SERVED = "2026-10-23T12:00:00+00:00"
# The deck_impressions columns a card dict's logged fields come from.
ROW_KEYS = ("impression_id", "user_id", "league_id", "deck_job_id", "card_index",
            "trade_hash", "propensity", "base_score", "final_score", "archetype",
            "shape_bucket", "served_at")


# ---------------------------------------------------------------------------
# The row contract and the writer's two calls
# ---------------------------------------------------------------------------

def pack_table(md: MetaData) -> Table:
    """deck_evidence_packs, exactly as eng-evidence-contract.md §6 specifies."""
    return Table(
        "deck_evidence_packs", md,
        Column("run_id", String, primary_key=True),      # = deck_job_id
        Column("user_id", String, nullable=False),
        Column("league_id", String, nullable=False),
        Column("served_at", String, nullable=False),     # ISO UTC, first delivery
        Column("pack_version", Integer, nullable=False),
        Column("header_json", Text, nullable=False),
        Column("cards_blob", LargeBinary, nullable=False),
        Column("checksum", String(64), nullable=False),
        Column("card_count", Integer, nullable=False),
        Column("created_at", String, nullable=False),
        Index("ix_deck_evidence_packs_served_at", "served_at"),
        Index("ix_deck_evidence_packs_user_league", "user_id", "league_id"),
    )


def make_engine(with_packs: bool = True):
    """An in-memory DB with the impression tables and, optionally, the pack
    table. Returns (engine, packs Table or None)."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng, tables=[deck_impressions_table, deck_outcomes_table])
    packs = None
    if with_packs:
        md = MetaData()
        packs = pack_table(md)
        md.create_all(eng)
    return eng, packs


def insert_pack(conn, packs: Table, *, run_id, user_id, league_id, served_at,
                packed: ep.PackedRun) -> None:
    """The writer's store: pack_run's result verbatim, plus the row keys."""
    conn.execute(insert(packs).values(
        run_id=run_id, user_id=user_id, league_id=league_id, served_at=served_at,
        created_at=served_at, **asdict(packed)))


# ---------------------------------------------------------------------------
# A small hand-built deck
# ---------------------------------------------------------------------------

def _card(job: str, i: int, served_at: str = SERVED, user: str = "u1") -> dict:
    return {
        "user_id": user, "league_id": "lg", "deck_job_id": job, "served_at": served_at,
        "card_index": i, "trade_hash": f"{i:016x}", "propensity": 0.5 + (i % 7) / 10,
        "base_score": 10.0 - i / 3, "final_score": 10.0 - i / 4, "archetype": "value",
        "shape_bucket": "2x1", "shape": "2x1", "lane": "value", "basis": "consensus",
        "give_positions": ["WR", "WR"], "receive_positions": ["RB"],
        "give_value": 1000.0 + i, "receive_value": 1100.5, "surplus_margin": 3.25,
        "fairness_score": 0.9, "likes_you": False, "relaxed": False, "involves_pick": False,
        "partner_user_id": f"opp{i % 3}", "taste_attrs": ["arch:value", "givepos:WR"],
        "taste_pref_long": (i * 37 % 19 - 9) / 10.3, "taste_pref_short": (i % 5 - 2) / 7.1,
        "ranked_player_count": 12, "user_value_basis": "personal",
        "model_arm": "current", "arm_rank": i, "need_fit": 0.5,
    }


def _row(card: dict, *, ghost: bool = False) -> dict:
    """A deck_impressions row. A non-ghost card's id is card_impression_id
    (R4.2 U2); a ghost's never is."""
    iid = card_impression_id(card["deck_job_id"], card["card_index"])
    return {
        **{k: card[k] for k in ROW_KEYS if k in card},
        "impression_id": f"{iid}:ghost" if ghost else iid,
        "features_json": json.dumps({k: v for k, v in card.items() if k not in ROW_KEYS}),
        "is_ghost": 1 if ghost else 0,
    }


def write_deck(eng, packs, cards, *, full, packed=None, card_count=None, ghosts=(),
               viewed=(), served_at=SERVED, deliveries=None, edit=None):
    """Rows for the indexes in `full` (+ ghost rows copying `ghosts`), a pack
    holding the indexes in `packed` (None: no pack) with `deliveries`
    (default: the whole deck in one page), and a `viewed` outcome per listed
    index, posted with the card's id. `edit(packed_run) -> packed_run`
    tampers before storing."""
    job = cards[0]["deck_job_id"]
    n = len(cards) if card_count is None else card_count
    with eng.begin() as conn:
        rows = [_row(c) for c in cards if c["card_index"] in full]
        rows += [_row(cards[i], ghost=True) for i in ghosts]
        if rows:
            conn.execute(insert(deck_impressions_table), rows)
        for i in viewed:
            conn.execute(insert(deck_outcomes_table).values(
                impression_id=card_impression_id(job, i), action="viewed",
                acted_at=served_at))
        if packed is not None:
            run = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": served_at,
                               "deliveries": (deliveries if deliveries is not None
                                              else [[n - 1, served_at]])},
                              [c for c in cards if c["card_index"] in packed],
                              card_count=n)
            insert_pack(conn, packs, run_id=job, user_id=cards[0]["user_id"],
                        league_id="lg", served_at=served_at,
                        packed=edit(run) if edit else run)


def _deck_cards(job, n, **kw):
    return [_card(job, i, **kw) for i in range(n)]


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def test_missing_pack_table_means_no_packs():
    cards = _deck_cards("j", 5)
    with_table, packs = make_engine()
    without, _ = make_engine(with_packs=False)
    write_deck(with_table, packs, cards, full=range(5))
    write_deck(without, None, cards, full=range(5))
    (a,), (b,) = load_decks(engine=with_table), load_decks(engine=without)
    assert a.exclusion is None and b.exclusion is None
    assert [card_dict(c) for c in a.cards] == [card_dict(c) for c in b.cards]


def test_pack_merges_cards_a_full_row_wins_and_outcomes_join():
    """Rows 0-29 and an upgraded viewed row at 35; the pack holds 30-39 (35
    included); 37 was viewed but left packed, so its outcome joins the
    packed card by its id; a ghost row at 33 collides with packed 33."""
    cards = _deck_cards("j", 40)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full={*range(30), 35}, packed=range(30, 40),
               ghosts=[33], viewed=[0, 35, 37])
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion is None
    assert [(c.card_index, c.is_ghost) for c in deck.cards] == (
        [(i, False) for i in range(34)] + [(33, True)] + [(i, False) for i in range(34, 40)])
    by_index = {c.card_index: c for c in deck.cards if not c.is_ghost}
    assert by_index[35].features is not None and by_index[35].viewed       # the row won
    assert by_index[37].features is None and by_index[37].viewed           # joined, packed
    assert [c.impression_id for c in deck.cards if not c.is_ghost] == [
        f"j:{i}" for i in range(40)]
    packed = by_index[34]
    assert packed.impression_id == "j:34" and not packed.viewed
    assert packed.features is None and FROZEN_INPUT_KEYS <= set(packed.features_compact)
    assert not set(packed.features_compact) & set(ROW_KEYS)
    assert packed.features_compact["model_arm"] == "current"           # attribution kept
    assert "need_fit" not in packed.features_compact                   # not a contract key
    for k in (FROZEN_INPUT_KEYS | set(ROW_KEYS)) - {"impression_id"}:
        assert card_dict(packed)[k] == cards[34][k], k


def test_project_features_trims_packed_cards_too():
    cards = _deck_cards("j", 32)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full=range(30), packed=range(30, 32))
    (deck,) = load_decks(engine=eng, project_features=True)
    packed = deck.cards[-1]
    assert packed.impression_id == "j:31"
    assert FROZEN_INPUT_KEYS <= set(packed.features_compact) <= PROJECTION_KEYS
    assert "model_arm" not in packed.features_compact


def test_window_and_scope_filters_apply_to_packs():
    eng, packs = make_engine()
    early, late = "2026-10-01T00:00:00+00:00", "2026-10-20T00:00:00+00:00"
    write_deck(eng, packs, _deck_cards("ja", 33, served_at=early), full=range(30),
               packed=range(30, 33), served_at=early)
    write_deck(eng, packs, _deck_cards("jb", 33, served_at=late, user="u2"),
               full=range(30), packed=range(30, 33), served_at=late)
    for kw, job in (({"since": "2026-10-10"}, "jb"), ({"until": "2026-10-10"}, "ja"),
                    ({"user_id": "u2"}, "jb")):
        (deck,) = load_decks(engine=eng, **kw)
        assert deck.deck_job_id == job and len(deck.cards) == 33 and deck.exclusion is None


def test_an_empty_pack_carries_the_card_count():
    """Every served deck gets a pack row (ADR-025), even with nothing past the
    first 30 to pack: its card_count still pins the deck's size."""
    cards = _deck_cards("j", 12)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full=range(12), packed=())
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion is None and len(deck.cards) == 12


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------

def _other_run(packed):
    """A valid pack, stored under the wrong run_id."""
    run, cards = ep.unpack_run(packed)
    return ep.pack_run(run, [{**c, "deck_job_id": "someone-else"} for c in cards],
                       card_count=packed.card_count)


@pytest.mark.parametrize("edit", [
    lambda p: replace(p, checksum="0" * 64),
    lambda p: replace(p, cards_blob=p.cards_blob[:-3]),
    lambda p: replace(p, header_json=p.header_json.replace('"vsn1:t"', '"vsn1:x"')),
    lambda p: replace(p, card_count=p.card_count + 1),
    lambda p: replace(p, pack_version=ep.PACK_VERSION + 1,
                      header_json=p.header_json.replace(
                          f'"pack_version":{ep.PACK_VERSION}',
                          f'"pack_version":{ep.PACK_VERSION + 1}')),
    _other_run,
], ids=["checksum", "blob", "run_metadata", "card_count", "unknown_version", "other_run"])
def test_a_pack_failing_integrity_marks_the_deck(edit):
    cards = _deck_cards("j", 36)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full=range(30), packed=range(30, 36), edit=edit)
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion == PACK_INTEGRITY
    assert [c.card_index for c in deck.cards] == list(range(30))   # nothing merged


@pytest.mark.parametrize("layout", [
    {"full": range(30), "packed": range(30, 38), "card_count": 40},      # pack short of its count
    {"full": {*range(30), 35}, "packed": None},                          # pack dropped, a row past it
    {"full": {*range(30)} - {4}, "packed": range(30, 40)},               # a row lost
    {"full": (), "packed": range(30, 40)},                               # every row lost
    {"full": {*range(10)} - {4}, "packed": None},                        # gap, no pack
])
def test_a_gap_marks_the_deck_incomplete(layout):
    cards = _deck_cards("j", 40)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, **layout)
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion == INCOMPLETE_DECK


# ---------------------------------------------------------------------------
# Replay and calibration exclude those decks whole
# ---------------------------------------------------------------------------

class _Spy:
    name = "spy"

    def __init__(self):
        self.scored = set()

    def score(self, card):
        self.scored.add(card["deck_job_id"])
        return float(card["base_score"])

    def predict_proba(self, card):
        return 0.5


def _mixed_engine():
    """Two good decks, one pack_integrity deck, one incomplete deck."""
    eng, packs = make_engine()
    for job in ("good1", "good2"):
        write_deck(eng, packs, _deck_cards(job, 34), full=range(30), packed=range(30, 34),
                   viewed=range(0, 30, 2))
    write_deck(eng, packs, _deck_cards("bad_pack", 34), full=range(30),
               packed=range(30, 34), viewed=range(0, 30, 3),
               edit=lambda p: replace(p, checksum="f" * 64))
    write_deck(eng, packs, _deck_cards("gap", 34), full={*range(30), 33}, packed=None,
               viewed=[1, 33])
    return eng


def test_replay_excludes_integrity_decks_whole_and_counts_them():
    decks = load_decks(engine=_mixed_engine())
    by_job = {d.deck_job_id: d for d in decks}
    assert by_job["bad_pack"].exclusion == PACK_INTEGRITY
    assert by_job["gap"].exclusion == INCOMPLETE_DECK
    spy = _Spy()
    run = evaluate(spy, decks, ess_min=1, bootstrap=50, seed=0)
    assert run.excluded["pack_integrity"] == 30 and run.pack_integrity_decks == 1
    assert run.excluded["incomplete_deck"] == 31 and run.incomplete_decks == 1
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert spy.scored == {"good1", "good2"}                       # never scored, never sunk
    good = [by_job["good1"], by_job["good2"]]
    assert exposure_curve(decks) == exposure_curve(good)          # out of e(k) too
    alone = evaluate(_Spy(), good, ess_min=1, bootstrap=50, seed=0)
    assert run.n_included == alone.n_included and run.metrics == alone.metrics
    text = render_report([run], run)
    assert "pack_integrity=30" in text and "pack_integrity_decks=1" in text
    assert "incomplete_deck=31" in text and "incomplete_decks=1" in text
    record = run_record(run, run)
    assert record["pack_integrity_decks"] == 1 and record["incomplete_decks"] == 1
    assert record["excluded"]["incomplete_deck"] == 31


def test_calibration_excludes_integrity_deck_cards():
    decks = load_decks(engine=_mixed_engine())
    pairs, excluded = calibration_pairs(_Spy(), decks)
    assert excluded["pack_integrity"] == 30 and excluded["incomplete_deck"] == 31
    assert len(pairs) == 2 * 15                                   # the good decks' viewed cards


# ---------------------------------------------------------------------------
# Exclusion-rule version (R2.5 (2))
# ---------------------------------------------------------------------------

def test_exclusion_rule_version_is_stamped_and_mixed_versions_are_flagged():
    decks = load_decks(engine=_mixed_engine())
    run = evaluate(_Spy(), decks, ess_min=1, bootstrap=20, seed=0)
    assert EXCLUSION_RULE_VERSION == 4 and run.exclusion_rule_version == 4
    record = run_record(run, run)
    assert record["exclusion_rule_version"] == 4 and record_rule_version(record) == 4
    assert record_rule_version({"scorer": "production"}) == 1      # written before the field

    assert rule_version_note([3, 3]) is None
    assert "not comparable" in rule_version_note([2, 3])
    assert rule_version_note(map(record_rule_version, [record, {}])) is not None

    old = replace(run, exclusion_rule_version=2)      # before delivered-position exposure
    assert verdict(run, run) != "RULE-MISMATCH"
    assert verdict(run, old) == "RULE-MISMATCH" == verdict(old, run)
    assert "Exclusion rules: version 4." in render_report([run], run)
    mixed = render_report([run], old)
    assert "WARNING: exclusion rules differ" in mixed and "RULE-MISMATCH" in mixed


# ---------------------------------------------------------------------------
# R4.2 U1: delivered positions are the exposure model's served set
# ---------------------------------------------------------------------------

def test_delivered_positions_are_the_served_set():
    eng, packs = make_engine()
    write_deck(eng, packs, _deck_cards("j", 40), full=range(30), packed=range(30, 40),
               ghosts=[5], viewed=[0, 3],
               deliveries=[[9, SERVED], [19, "2026-10-23T12:05:00+00:00"]])
    write_deck(eng, packs, _deck_cards("old", 12), full=range(12))     # no pack: pre-paging
    deck, old = load_decks(engine=eng)
    assert [c.card_index for c in deck.cards if c.delivered] == list(range(20))
    assert not any(c.delivered for c in deck.cards if c.is_ghost)
    assert all(c.delivered for c in old.cards)
    assert set(exposure_curve([deck])) == set(range(20))
    assert set(exposure_curve([old])) == set(range(12))


def _ek_before_delivery(decks):
    """e(k) as replay computed it before R5.2 (d): every loaded card served."""
    served, viewed = {}, {}
    for d in decks:
        for c in d.cards:
            served[c.card_index] = served.get(c.card_index, 0) + 1
            viewed[c.card_index] = viewed.get(c.card_index, 0) + c.viewed
    return {k: max((viewed[k] + 1) / (served[k] + 2), replay_mod.EXPOSURE_FLOOR) for k in served}


def test_a_legacy_deck_keeps_its_exposure_and_a_paged_deck_uses_delivered_positions():
    """R5.2 (d): a deck from before paging (no pack) delivered every served
    card, so its e(k) is what it always was; a paged deck's undelivered
    tail no longer counts as served."""
    eng, packs = make_engine()
    for job in ("old1", "old2"):
        write_deck(eng, packs, _deck_cards(job, 12), full=range(12), ghosts=[3],
                   viewed=[0, 1, 2, 5])
    write_deck(eng, packs, _deck_cards("paged", 40), full=range(30), packed=range(30, 40),
               viewed=[0, 1, 2, 5, 12], deliveries=[[14, SERVED]])
    decks = load_decks(engine=eng)
    legacy = [d for d in decks if d.deck_job_id.startswith("old")]
    (paged,) = [d for d in decks if d.deck_job_id == "paged"]
    assert exposure_curve(legacy) == _ek_before_delivery(legacy)
    assert set(exposure_curve([paged])) == set(range(15))
    assert exposure_curve([paged]) != _ek_before_delivery([paged])


# ---------------------------------------------------------------------------
# R5.2 (b): the read's as_of, and the settle lag that picks it
# ---------------------------------------------------------------------------

def test_outcomes_acted_and_decks_served_after_as_of_are_not_read():
    eng, packs = make_engine()
    write_deck(eng, packs, _deck_cards("j", 32), full=range(30), packed=range(30, 32),
               viewed=[0, 1])
    late = "2026-11-02T00:00:00+00:00"
    with eng.begin() as conn:
        conn.execute(insert(deck_outcomes_table), [
            {"impression_id": card_impression_id("j", 0), "action": "like", "acted_at": late},
            {"impression_id": card_impression_id("j", 31), "action": "viewed", "acted_at": late},
        ])
    later = "2026-10-30T00:00:00+00:00"
    write_deck(eng, packs, _deck_cards("later", 30, served_at=later), full=range(30),
               served_at=later)

    (deck,) = load_decks(engine=eng, as_of="2026-10-26T12:00:00+00:00")
    cards = {c.card_index: c for c in deck.cards}
    assert deck.deck_job_id == "j"
    assert cards[0].viewed and not cards[0].liked and not cards[31].viewed
    everything = {d.deck_job_id: d for d in load_decks(engine=eng)}
    assert set(everything) == {"j", "later"}
    cards = {c.card_index: c for c in everything["j"].cards}
    assert cards[0].liked and cards[31].viewed


def test_the_settle_lag_picks_as_of():
    eng, packs = make_engine()
    for job, at in (("a", "2026-10-01T09:00:00+00:00"), ("b", "2026-10-10T18:30:00+00:00"),
                    ("c", "2026-10-20T08:00:00+00:00")):
        write_deck(eng, packs, _deck_cards(job, 30, served_at=at), full=range(30), served_at=at)
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    until, as_of = replay_mod.settled_read(now=now, settle_lag_days=7, engine=eng)
    assert until == "2026-10-17T12:00:00+00:00"            # the window ends a lag ago
    assert as_of == "2026-10-17T18:30:00+00:00"            # its last served_at + the lag
    assert [d.deck_job_id for d in load_decks(engine=eng, until=until, as_of=as_of)] == ["a", "b"]
    assert replay_mod.settled_read(now=now, settle_lag_days=7, engine=eng,
                                   until="2026-10-01T00:00:00+00:00") == (
        "2026-10-01T00:00:00+00:00", None)


# ---------------------------------------------------------------------------
# R5.2 (c): a refit is the same whether viewed cards were upgraded or not
# ---------------------------------------------------------------------------

def test_a_refit_is_the_same_upgraded_or_left_packed():
    late = {31, 33, 35, 37, 38}

    def engine(upgrade):
        eng, packs = make_engine()
        for d in range(8):
            job, viewed = f"r{d}", [*range(0, 30, 2), *sorted(late)]
            write_deck(eng, packs, _deck_cards(job, 40),
                       full=set(range(30)) | (late if upgrade else set()),
                       packed=range(30, 40), viewed=viewed)
            with eng.begin() as conn:
                conn.execute(insert(deck_outcomes_table), [
                    {"impression_id": card_impression_id(job, i),
                     "action": "like" if (i + d) % 3 == 0 else "pass", "acted_at": SERVED}
                    for i in viewed])
        return eng

    as_of = datetime(2026, 10, 24, tzinfo=timezone.utc)
    upgraded = vm.train_model(load_decks(engine=engine(True)), as_of=as_of)
    left_packed = vm.train_model(load_decks(engine=engine(False)), as_of=as_of)
    assert upgraded is not None and upgraded.meta["n_like_rows"] == 8 * 20
    assert upgraded.to_dict() == left_packed.to_dict()


# ---------------------------------------------------------------------------
# In flight, and lost packs (PACK_REQUIRED_SINCE)
# ---------------------------------------------------------------------------

REQUIRED = "2026-10-20T00:00:00+00:00"
AS_OF = "2026-10-23T14:00:00+00:00"


@pytest.mark.parametrize("required", [None, REQUIRED])
def test_pack_required_since_flags_in_flight_and_lost_packs(monkeypatch, required):
    monkeypatch.setattr(data_mod, "PACK_REQUIRED_SINCE", required)
    eng, packs = make_engine()
    served = {"live": "2026-10-23T12:00:00+00:00",     # 2 h before as_of: may be live
              "lost": "2026-10-21T12:00:00+00:00",     # 50 h before: retired, pack lost
              "legacy": "2026-10-19T12:00:00+00:00"}   # before the requirement
    for job, at in served.items():
        write_deck(eng, packs, _deck_cards(job, 30, served_at=at), full=range(30),
                   served_at=at, viewed=[0])
    write_deck(eng, packs, _deck_cards("packed", 34, served_at=served["lost"]),
               full=range(30), packed=range(30, 34), served_at=served["lost"])

    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=eng, as_of=AS_OF)}
    no_clock = {d.deck_job_id: d.exclusion for d in load_decks(engine=eng)}
    if required is None:      # the writer hasn't shipped: no pack is ever expected
        assert got == no_clock == dict.fromkeys(("live", "lost", "legacy", "packed"))
        return
    assert got == {"live": IN_FLIGHT, "lost": INCOMPLETE_DECK, "legacy": None,
                   "packed": None}
    assert no_clock["live"] == INCOMPLETE_DECK    # without as_of it can't be called live

    decks = load_decks(engine=eng, as_of=AS_OF)
    run = evaluate(_Spy(), decks, ess_min=1, bootstrap=0, seed=0)
    assert run.excluded["in_flight"] == 30 and run.in_flight_decks == 1
    assert run.incomplete_decks == 1 and run.pack_integrity_decks == 0
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert "in_flight=30" in render_report([run], run)
    assert run_record(run, run)["in_flight_decks"] == 1
    _pairs, excluded = calibration_pairs(_Spy(), decks)
    assert excluded["in_flight"] == 30


# ---------------------------------------------------------------------------
# R4.2 U2: a viewed card replays the same, upgraded or left packed
# ---------------------------------------------------------------------------

def _u2_engine(upgrade: bool):
    """Three decks; 31, 35 and 38 were viewed past the first 30. upgrade:
    they also have full rows (the upgrade on view); else they stay packed
    and their outcomes join by id."""
    eng, packs = make_engine()
    late = {31, 35, 38}
    for job in ("ua", "ub", "uc"):
        write_deck(eng, packs, _deck_cards(job, 40),
                   full=set(range(30)) | (late if upgrade else set()),
                   packed=range(30, 40), viewed=[*range(0, 30, 3), *late],
                   deliveries=[[19, SERVED], [39, "2026-10-23T12:07:00+00:00"]])
    return eng


def test_a_viewed_card_replays_the_same_upgraded_or_left_packed(monkeypatch):
    upgraded = load_decks(engine=_u2_engine(upgrade=True))
    packed = load_decks(engine=_u2_engine(upgrade=False))
    joined = [c for d in packed for c in d.cards if c.viewed and c.features is None]
    assert len(joined) == 9
    assert exposure_curve(upgraded) == exposure_curve(packed)

    model = vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.4, "value_delta": 0.8,
                                           "pref_long": 1.1, "pref_short": -0.6,
                                           "partner_rate": 0.9}),
        propose_head=None, propose_constant=0.2,
        partner_rates={"u1|opp1": 0.7}, global_like_rate=0.3, position_mean=0.4,
        trained_at="t", train_date="t")
    monkeypatch.setattr(vm, "load_latest_model", lambda: model)
    real = replay_mod._estimate
    for name in registered_names():
        out = []
        for decks in (upgraded, packed):
            weights = []
            monkeypatch.setattr(replay_mod, "_estimate",
                                lambda *a, w=weights: w.append(list(a[1])) or real(*a))
            run = evaluate(get_scorer(name, seed=3), decks, ess_min=1, bootstrap=100, seed=2)
            out.append((repr(run), weights))
        assert out[0] == out[1], name
        assert out[0][1][0], name     # the IPS weights were compared, not empty
