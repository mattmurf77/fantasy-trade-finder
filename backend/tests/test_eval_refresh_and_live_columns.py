"""Release-lead's QA of #370 (ADR-025 packed evidence), the eval side.

P2-3: a deck Calibration's targeted refresh built (a card's deck_source is
'grading_refresh', ADR-025 S4) is never shown in Trades. load_decks marks it
calibration_refresh, ahead of every other loader exclusion (a refresh deck is
never packed, so past PACK_REQUIRED_SINCE it would otherwise read as a lost
pack); replay excludes it whole and counts it, e(k) skips it, calibration
excludes its cards; EXCLUSION_RULE_VERSION became 4 (5 since the withdrawal
and paging rules).

P3: load_decks selects an optional column (features_compact, evidence_tier)
iff the LIVE table has it, never because the code's metadata declares it: an
unmigrated DB still loads, and a DB column the metadata lacks is still read.

The decks are the hand-built ones of test_eval_pack_reader.py. The P3 tables
are bare copies of deck_impressions (names and types) built without the
optional columns, so the tests hold whether or not the code's metadata has
them (#370 adds evidence_tier).
"""

import json
from dataclasses import replace

import pytest
from sqlalchemy import Column, MetaData, Table, Text, create_engine, insert

import backend.eval.data as data_mod
from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval.calibration import calibration_pairs
from backend.eval.data import (
    CALIBRATION_REFRESH, CALIBRATION_REFRESH_SOURCE, EVAL_COLUMNS, IN_FLIGHT, INCOMPLETE_DECK,
    OPTIONAL_COLUMNS, PACK_INTEGRITY, PARTIAL_RUN_TIER, load_decks,
)
from backend.eval.persistence import run_record
from backend.eval.replay import EXCLUSION_RULE_VERSION, evaluate, exposure_curve, render_report
from backend.tests.test_eval_nightly_lean import _selected_columns
from backend.tests.test_eval_pack_reader import (
    AS_OF, REQUIRED, _deck_cards, _row, _Spy, make_engine, write_deck,
)


def _sourced(cards, source=CALIBRATION_REFRESH_SOURCE):
    """The cards with deck_source set (None: absent), as the impression
    writer freezes it into features_json."""
    if source is None:
        return cards
    return [{**c, "deck_source": source} for c in cards]


# ---------------------------------------------------------------------------
# P2-3: the loader marks a refresh deck
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("project", [False, True])
def test_a_refresh_deck_is_calibration_refresh(project):
    eng, packs = make_engine()
    write_deck(eng, packs, _sourced(_deck_cards("refresh", 12)), full=range(12))
    write_deck(eng, packs, _deck_cards("trades", 12), full=range(12))
    by_job = {d.deck_job_id: d
              for d in load_decks(engine=eng, project_features=project)}
    assert by_job["refresh"].exclusion == CALIBRATION_REFRESH
    assert by_job["trades"].exclusion is None
    # deck_source is not a projection key: the trim drops it, after the check.
    assert ("deck_source" in by_job["refresh"].cards[0].features) is not project


@pytest.mark.parametrize("source", ["replenish", "prepared_adoption", None])
def test_other_deck_sources_are_not_excluded(source):
    """Refresh decks built before #370's relabel carry 'replenish' and stay in."""
    eng, packs = make_engine()
    write_deck(eng, packs, _sourced(_deck_cards("j", 12), source), full=range(12))
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion is None


@pytest.mark.parametrize("layout, trades", [
    ({"full": {*range(10)} - {4}}, INCOMPLETE_DECK),                       # a gap, no pack
    ({"full": range(30), "packed": range(30, 34),
      "edit": lambda p: replace(p, checksum="0" * 64)}, PACK_INTEGRITY),  # a bad pack
], ids=["gap", "pack_integrity"])
def test_refresh_takes_precedence_over_a_gap_and_a_bad_pack(layout, trades):
    eng, packs = make_engine()
    write_deck(eng, packs, _sourced(_deck_cards("refresh", 34)), **layout)
    write_deck(eng, packs, _deck_cards("trades", 34), **layout)
    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=eng)}
    assert got == {"refresh": CALIBRATION_REFRESH, "trades": trades}


@pytest.mark.parametrize("as_of", [AS_OF, None])
def test_refresh_takes_precedence_over_in_flight_and_a_lost_pack(monkeypatch, as_of):
    """Refresh decks keep full rows and are never packed: once a pack is
    required, the same decks without the marker are in flight or lost."""
    monkeypatch.setattr(data_mod, "PACK_REQUIRED_SINCE", REQUIRED)
    eng, packs = make_engine()
    served = {"live": "2026-10-23T12:00:00+00:00",     # 2 h before AS_OF
              "lost": "2026-10-21T12:00:00+00:00"}     # 50 h before
    for job, at in served.items():
        cards = _deck_cards(job, 30, served_at=at)
        write_deck(eng, packs, cards, full=range(30), served_at=at)
        write_deck(eng, packs, _sourced(_deck_cards(f"refresh-{job}", 30, served_at=at)),
                   full=range(30), served_at=at)
    got = {d.deck_job_id: d.exclusion for d in load_decks(engine=eng, as_of=as_of)}
    assert got == {"live": IN_FLIGHT if as_of else INCOMPLETE_DECK,
                   "lost": INCOMPLETE_DECK,
                   "refresh-live": CALIBRATION_REFRESH,
                   "refresh-lost": CALIBRATION_REFRESH}


# ---------------------------------------------------------------------------
# P2-3: replay, e(k) and calibration leave it out
# ---------------------------------------------------------------------------

def _refresh_engine():
    """Two Trades decks and a refresh deck whose every card has an outcome
    (so it would move e(k) if it counted)."""
    eng, packs = make_engine()
    for job in ("good1", "good2"):
        write_deck(eng, packs, _deck_cards(job, 34), full=range(30), packed=range(30, 34),
                   viewed=range(0, 30, 2))
    write_deck(eng, packs, _sourced(_deck_cards("refresh", 20)), full=range(20),
               viewed=range(20))
    return eng


def test_replay_excludes_a_refresh_deck_whole_and_counts_it():
    decks = load_decks(engine=_refresh_engine())
    by_job = {d.deck_job_id: d for d in decks}
    good = [by_job["good1"], by_job["good2"]]
    spy = _Spy()
    run = evaluate(spy, decks, ess_min=1, bootstrap=50, seed=0)
    assert run.excluded["calibration_refresh"] == 20 and run.calibration_refresh_decks == 1
    assert run.n_total == run.n_included + sum(run.excluded.values())
    assert spy.scored == {"good1", "good2"}
    alone = evaluate(_Spy(), good, ess_min=1, bootstrap=50, seed=0)
    assert run.n_included == alone.n_included and run.metrics == alone.metrics

    assert exposure_curve(decks) == exposure_curve(good)
    counted = replace(by_job["refresh"], exclusion=None)
    assert exposure_curve([*good, counted]) != exposure_curve(good)   # the test can fail

    text = render_report([run], run)
    assert "calibration_refresh=20" in text and "calibration_refresh_decks=1" in text
    assert "Exclusion rules: version 5." in text
    record = run_record(run, run)
    assert record["calibration_refresh_decks"] == 1
    assert record["excluded"]["calibration_refresh"] == 20
    assert EXCLUSION_RULE_VERSION == 5
    assert run.exclusion_rule_version == 5 and record["exclusion_rule_version"] == 5


def test_calibration_excludes_refresh_deck_cards():
    pairs, excluded = calibration_pairs(_Spy(), load_decks(engine=_refresh_engine()))
    assert excluded["calibration_refresh"] == 20
    assert len(pairs) == 2 * 15                                   # the Trades decks' viewed cards


def test_a_refresh_deck_counts_ahead_of_partial_run():
    eng, packs = make_engine()
    write_deck(eng, packs, _sourced(_deck_cards("refresh", 6)), full=range(6), viewed=range(6))
    (deck,) = load_decks(engine=eng)
    deck.cards[2].evidence_tier = PARTIAL_RUN_TIER
    run = evaluate(_Spy(), [deck], ess_min=1, bootstrap=0, seed=0)
    assert run.excluded["calibration_refresh"] == 6 and run.calibration_refresh_decks == 1
    assert run.excluded["partial_run"] == 0 and run.partial_run_decks == 0
    _pairs, excluded = calibration_pairs(_Spy(), [deck])
    assert excluded["calibration_refresh"] == 6 and excluded["partial_run"] == 0


# ---------------------------------------------------------------------------
# P3: optional columns come from the live table
# ---------------------------------------------------------------------------

def _bare_impressions(md, extra=()):
    """deck_impressions by column name and type only, without the optional
    columns whatever the code's metadata declares, plus `extra` Text columns."""
    return Table("deck_impressions", md,
                 *[Column(c.name, c.type) for c in deck_impressions_table.c
                   if c.name not in OPTIONAL_COLUMNS],
                 *[Column(name, Text) for name in extra])


def _db(extra=()):
    md = MetaData()
    imp = _bare_impressions(md, extra)
    deck_outcomes_table.to_metadata(md)
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    md.create_all(eng)
    return eng, imp


def test_an_optional_column_the_db_lacks_is_not_selected(monkeypatch):
    """The code's metadata has every optional column (as once #370 lands);
    the DB, an unmigrated snapshot, has none."""
    eng, imp = _db()
    code = deck_impressions_table.to_metadata(MetaData())
    for name in OPTIONAL_COLUMNS:
        if name not in code.c:
            code.append_column(Column(name, Text))
    monkeypatch.setattr(data_mod, "deck_impressions_table", code)
    with eng.begin() as conn:
        conn.execute(insert(imp), [_row(c) for c in _deck_cards("j", 5)])
    assert _selected_columns(eng, lambda: load_decks(engine=eng)) == set(EVAL_COLUMNS)
    (deck,) = load_decks(engine=eng)
    assert deck.exclusion is None and len(deck.cards) == 5
    assert all(c.evidence_tier is None and c.features_compact is None for c in deck.cards)


def test_optional_columns_the_metadata_lacks_are_read_from_the_db(monkeypatch):
    """The DB has every optional column; the code's metadata has none. A
    'partial_run' tier still takes replay's deck out, and a refresh marker
    in a narrow row's compact block still marks its deck."""
    eng, imp = _db(extra=OPTIONAL_COLUMNS)
    monkeypatch.setattr(data_mod, "deck_impressions_table", _bare_impressions(MetaData()))
    marked = {"shape": "2x1", "deck_source": CALIBRATION_REFRESH_SOURCE}
    # delivered_at: a tiered (paged) deck is never legacy, so it needs delivery evidence.
    rows = [{**_row(c), "features_compact": None, "delivered_at": c["served_at"],
             "evidence_tier": PARTIAL_RUN_TIER if c["card_index"] == 1 else "first30"}
            for c in _deck_cards("partial", 4)]
    rows += [{**_row(c), "features_json": None, "features_compact": json.dumps(marked),
              "evidence_tier": "first30", "delivered_at": c["served_at"]}
             for c in _deck_cards("narrow", 3)]
    with eng.begin() as conn:
        conn.execute(insert(imp), rows)
    assert (_selected_columns(eng, lambda: load_decks(engine=eng))
            == set(EVAL_COLUMNS) | set(OPTIONAL_COLUMNS))
    by_job = {d.deck_job_id: d for d in load_decks(engine=eng)}
    partial, narrow = by_job["partial"], by_job["narrow"]
    assert [c.evidence_tier for c in partial.cards] == [
        "first30", PARTIAL_RUN_TIER, "first30", "first30"]
    assert partial.exclusion is None
    assert narrow.cards[0].features is None and narrow.cards[0].features_compact == marked
    assert narrow.exclusion == CALIBRATION_REFRESH
    run = evaluate(_Spy(), [partial, narrow], ess_min=1, bootstrap=0, seed=0)
    assert run.excluded["partial_run"] == 4 and run.partial_run_decks == 1
    assert run.excluded["calibration_refresh"] == 3 and run.calibration_refresh_decks == 1
