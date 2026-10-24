"""ADR-025 stage 2, the reader side: backend.eval.data.load_decks merges
deck_evidence_packs into decks (C7 (i)); replay excludes a deck whose pack
fails integrity or whose card indexes have a gap, whole and never sunk, and
calibration excludes its cards (C7 (iv)); every run carries
EXCLUSION_RULE_VERSION (R2.5 (2)).

The pack table is defined HERE, test-locally (pack_table): it is the row
contract trades-eng builds in backend/database.py
(docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6). The golden
over real decks (C7 (ii)) is in test_evidence_pack.py.
"""

import json
from dataclasses import asdict, replace

import pytest
from sqlalchemy import (
    Column, Index, Integer, LargeBinary, MetaData, String, Table, Text, create_engine, insert,
)

from backend.database import deck_impressions_table, deck_outcomes_table, metadata
from backend.eval import evidence_pack as ep
from backend.eval.calibration import calibration_pairs
from backend.eval.contract import FROZEN_INPUT_KEYS, PROJECTION_KEYS
from backend.eval.data import INCOMPLETE_DECK, PACK_INTEGRITY, card_dict, load_decks
from backend.eval.persistence import record_rule_version, run_record
from backend.eval.replay import (
    EXCLUSION_RULE_VERSION, evaluate, exposure_curve, render_report, rule_version_note, verdict,
)

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
        "ranked_player_count": 12, "user_value_basis": "personal",
        "model_arm": "current", "arm_rank": i, "need_fit": 0.5,
    }


def _row(card: dict, *, ghost: bool = False) -> dict:
    suffix = "_g" if ghost else ""
    return {
        **{k: card[k] for k in ROW_KEYS if k in card},
        "impression_id": f"{card['deck_job_id']}_{card['card_index']}{suffix}",
        "features_json": json.dumps({k: v for k, v in card.items() if k not in ROW_KEYS}),
        "is_ghost": 1 if ghost else 0,
    }


def write_deck(eng, packs, cards, *, full, packed=None, card_count=None, ghosts=(),
               viewed=(), served_at=SERVED, edit=None):
    """Rows for the indexes in `full` (+ ghost rows copying `ghosts`), a pack
    holding the indexes in `packed` (None: no pack), a `viewed` outcome per
    listed index. `edit(packed_run) -> packed_run` tampers before storing."""
    job = cards[0]["deck_job_id"]
    with eng.begin() as conn:
        rows = [_row(c) for c in cards if c["card_index"] in full]
        rows += [_row(cards[i], ghost=True) for i in ghosts]
        if rows:
            conn.execute(insert(deck_impressions_table), rows)
        for i in viewed:
            conn.execute(insert(deck_outcomes_table).values(
                impression_id=f"{job}_{i}", action="viewed", acted_at=served_at))
        if packed is not None:
            run = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": served_at},
                              [c for c in cards if c["card_index"] in packed],
                              card_count=len(cards) if card_count is None else card_count)
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
    assert a.integrity is None and b.integrity is None
    assert [card_dict(c) for c in a.cards] == [card_dict(c) for c in b.cards]


def test_pack_merges_unseen_cards_and_a_full_row_wins():
    """Rows 0-29 and a viewed row at 35; the pack holds 30-39 (35 included,
    as an upgraded card would be); a ghost row at 33 collides with packed 33."""
    cards = _deck_cards("j", 40)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full={*range(30), 35}, packed=range(30, 40),
               ghosts=[33], viewed=[0, 35])
    (deck,) = load_decks(engine=eng)
    assert deck.integrity is None
    assert [(c.card_index, c.is_ghost) for c in deck.cards] == (
        [(i, False) for i in range(34)] + [(33, True)] + [(i, False) for i in range(34, 40)])
    by_index = {c.card_index: c for c in deck.cards if not c.is_ghost}
    assert by_index[35].impression_id == "j_35" and by_index[35].viewed     # the row won
    packed = by_index[34]
    assert packed.impression_id == "pack:j:34" and not packed.viewed
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
    assert packed.impression_id == "pack:j:31"
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
        assert deck.deck_job_id == job and len(deck.cards) == 33 and deck.integrity is None


def test_an_empty_pack_carries_the_card_count():
    """Every served deck gets a pack row (ADR-025), even with nothing past the
    first 30 to pack: its card_count still pins the deck's size."""
    cards = _deck_cards("j", 12)
    eng, packs = make_engine()
    write_deck(eng, packs, cards, full=range(12), packed=())
    (deck,) = load_decks(engine=eng)
    assert deck.integrity is None and len(deck.cards) == 12


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
    assert deck.integrity == PACK_INTEGRITY
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
    assert deck.integrity == INCOMPLETE_DECK


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
    assert by_job["bad_pack"].integrity == PACK_INTEGRITY
    assert by_job["gap"].integrity == INCOMPLETE_DECK
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
    assert EXCLUSION_RULE_VERSION == 2 and run.exclusion_rule_version == 2
    record = run_record(run, run)
    assert record["exclusion_rule_version"] == 2 and record_rule_version(record) == 2
    assert record_rule_version({"scorer": "production"}) == 1      # written before the field

    assert rule_version_note([2, 2]) is None
    assert "not comparable" in rule_version_note([1, 2])
    assert rule_version_note(map(record_rule_version, [record, {}])) is not None

    old = replace(run, exclusion_rule_version=1)
    assert verdict(run, run) != "RULE-MISMATCH"
    assert verdict(run, old) == "RULE-MISMATCH" == verdict(old, run)
    assert "Exclusion rules: version 2." in render_report([run], run)
    mixed = render_report([run], old)
    assert "WARNING: exclusion rules differ" in mixed and "RULE-MISMATCH" in mixed
