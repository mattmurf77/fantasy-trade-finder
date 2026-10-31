"""Cards whose partner deleted their account (models-lead addendum G: G-a5;
addendum J: J1, J2).

The deletion scrub puts a redaction token in the card's partner_user_id,
strips likes_you and nulls the blended scores (base_score, final_score,
surplus_margin), which a scorer would read as 0 and sink. So the loader
marks the card (LoggedCard.partner_redacted) and excludes its deck as
partner_redacted, below every integrity reason (J1). Replay, e(k) and
calibration leave the deck out and never score it, and a clean deck is
bit-identical across the scrub (J2). The B-DK audit, G3's joins and the flip
read's checks keep the deck, and the fit drops every redacted card. Replay's
record also counts what the scrub cleared, and the decks redacted since the
previous read of the same window (G-a5).
"""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.eval.flip_read as fr
from backend import value_model as vm
from backend.database import metadata
from backend.eval import evidence_pack as ep
from backend.eval.calibration import calibration_pairs
from backend.eval.contract import REDACTED_PARTNER_PREFIX
from backend.eval.data import (INCOMPLETE_DECK, PARTNER_REDACTED, LoggedDeck, load_decks,
                               partner_redacted_share)
from backend.eval.persistence import append_run, previous_read_at, run_record
from backend.eval.replay import (_fit_rows, evaluate, exposure_curve, redaction_counts,
                                 render_report)
from backend.eval.scorers import get_scorer, registered_names
from backend.eval.synth import build_synthetic_db
from backend.tests.test_eval_pack_reader import (SERVED, _card, _deck_cards, _row, insert_pack,
                                                 make_engine, write_deck)
from backend.tests.test_eval_withdrawals_and_paging import _after, act, make_db

TOKEN = f"{REDACTED_PARTNER_PREFIX}aa11"
AS_OF = datetime(2026, 10, 31, tzinfo=timezone.utc)
EARLY, LATE = "2026-10-30T12:00:00+00:00", "2026-10-31T06:00:00+00:00"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path / "vm"))
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "runs"))


def _scrubbed(card: dict, keep_like: bool = False) -> dict:
    """The scrub's card (legal R28.22 b2; E-b2 items 1-5): the token as
    partner, likes_you gone (unless `keep_like`, to show a count reads the
    key), the blended scores nulled."""
    out = {**card, "partner_user_id": TOKEN, "base_score": None, "final_score": None,
           "surplus_margin": None}
    if not keep_like:
        del out["likes_you"]
    return out


# ---------------------------------------------------------------------------
# J1: the loader's mark and the deck exclusion
# ---------------------------------------------------------------------------

def _pack(eng, packs, cards, *, card_count, redacted_at):
    """A pack the scrub rewrote: its run carries redacted_at."""
    run = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": SERVED,
                       "deliveries": [[card_count - 1, SERVED]], "redacted_at": redacted_at},
                      cards, card_count=card_count)
    with eng.begin() as conn:
        insert_pack(conn, packs, run_id=cards[0]["deck_job_id"], user_id="u1",
                    league_id="lg", served_at=SERVED, packed=run)


def _decks():
    """j: rows 0-4 and a redacted pack of 5-9; cards 0 and 7 redacted, card 3
    redacted with its like kept. k: rows, no redaction. m: a pack only,
    redacted later, holding no redacted card."""
    eng, packs = make_engine()
    j = _deck_cards("j", 10)
    j[0], j[3], j[7] = _scrubbed(j[0]), _scrubbed(j[3], keep_like=True), _scrubbed(j[7])
    write_deck(eng, packs, j, full=range(5))
    _pack(eng, packs, j[5:], card_count=10, redacted_at=EARLY)
    write_deck(eng, packs, _deck_cards("k", 4), full=range(4))
    _pack(eng, packs, _deck_cards("m", 3), card_count=3, redacted_at=LATE)
    return load_decks(engine=eng)


def test_the_loader_marks_redacted_cards_and_excludes_their_deck():
    decks = {d.deck_job_id: d for d in _decks()}
    marked = {(d, c.card_index) for d, deck in decks.items() for c in deck.cards
              if c.partner_redacted}
    assert marked == {("j", 0), ("j", 3), ("j", 7)}          # rows and a packed card
    assert {d: deck.exclusion for d, deck in decks.items()} == {
        "j": PARTNER_REDACTED, "k": None, "m": None}
    assert {d: deck.redacted_at for d, deck in decks.items()} == {
        "j": EARLY, "k": None, "m": LATE}
    assert len(decks["j"].cards) == 10                       # excluded, nothing dropped


def _one_deck(cards, **kw):
    db = make_db()
    write_deck(db.eng, db.packs, cards, **kw)
    return load_decks(engine=db.eng)[0]


def test_only_the_token_marks_a_deck():
    nulled = [{**c, "base_score": None, "final_score": None} if c["card_index"] == 2 else c
              for c in _deck_cards("n", 6)]
    assert _one_deck(nulled, full=range(6)).exclusion is None      # a writer defect: today's path
    near = [{**c, "partner_user_id": f"x{TOKEN}"} if c["card_index"] == 2 else c
            for c in _deck_cards("x", 6)]
    deck = _one_deck(near, full=range(6))
    assert deck.exclusion is None and not any(c.partner_redacted for c in deck.cards)


def test_a_redacted_ghost_row_excludes_its_deck():
    """Replay ranks ghosts too (_candidate_ranks scores every card)."""
    db = make_db()
    cards = _deck_cards("g", 6)
    write_deck(db.eng, db.packs, cards, full=range(6))
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp).values({**_row(_scrubbed(cards[3]), ghost=True),
                                            "impression_id": "ghost-uuid-1"}))
    assert load_decks(engine=db.eng)[0].exclusion == PARTNER_REDACTED


def test_partner_redacted_ranks_below_the_integrity_reasons():
    cards = _deck_cards("i", 6)
    cards[2] = _scrubbed(cards[2])
    gap = _one_deck(cards, full=[0, 1, 2, 4, 5])                   # index 3 missing
    assert gap.exclusion == INCOMPLETE_DECK
    partial = _one_deck(cards, full=range(6), tier="partial_run")
    assert partial.exclusion is None                               # replay's partial_run
    run = evaluate(get_scorer("logged"), [partial], ess_min=1, bootstrap=0, seed=0)
    assert (run.partial_run_decks, run.partner_redacted_decks) == (1, 0)


@pytest.mark.parametrize("excluded, over", [(1, False), (2, True)], ids=["at_5_percent", "above"])
def test_the_share_trigger_is_above_5_percent_of_the_window(excluded, over):
    decks = [LoggedDeck(f"d{i}", "u1", "lg", SERVED,
                        exclusion=PARTNER_REDACTED if i < excluded else None) for i in range(20)]
    assert partner_redacted_share(decks) == {"decks": excluded, "window_decks": 20,
                                             "over_gate": over}


# ---------------------------------------------------------------------------
# J2: replay across the scrub
# ---------------------------------------------------------------------------

def _two_decks(scrubbed: bool):
    """c: clean. r: card 2 scrubbed when `scrubbed`. Each: rows 0-2 and a pack
    of 3-5, viewed whole, with likes, a pass and a propose."""
    db = make_db()
    for job in ("c", "r"):
        cards = _deck_cards(job, 6)
        if job == "r" and scrubbed:
            cards[2] = _scrubbed(cards[2])
        write_deck(db.eng, db.packs, cards, full=range(3), packed=range(3, 6), viewed=range(6))
        act(db, job, 1, "like")
        act(db, job, 2, "like", "propose")
        act(db, job, 4, "pass")
    return db


@pytest.mark.parametrize("name", registered_names())
def test_j2_a_clean_deck_is_bit_identical_across_the_scrub_and_a_redacted_one_never_scored(name):
    before = [d for d in load_decks(engine=_two_decks(False).eng) if d.deck_job_id == "c"]
    after = load_decks(engine=_two_decks(True).eng)
    assert {d.deck_job_id: d.exclusion for d in after} == {"c": None, "r": PARTNER_REDACTED}
    scorer, seen = get_scorer(name), []
    score = scorer.score
    scorer.score = lambda card: seen.append(card["deck_job_id"]) or score(card)
    run = evaluate(scorer, after, ess_min=1, bootstrap=30, seed=0)
    clean = evaluate(get_scorer(name), before, ess_min=1, bootstrap=30, seed=0)
    assert "r" not in seen and "c" in seen
    assert repr(run.metrics) == repr(clean.metrics)                # every estimate, bit for bit
    assert exposure_curve(after) == exposure_curve(before)
    assert (run.partner_redacted_decks, run.excluded["partner_redacted"]) == (1, 6)
    record = run_record(run, run)
    assert (record["partner_redacted_decks"], record["excluded"]["partner_redacted"],
            record["exclusion_rule_version"]) == (1, 6, 7)


def test_j2_calibration_leaves_the_redacted_deck_out():
    scorer, seen = get_scorer("value_model"), []
    proba = scorer.predict_proba
    scorer.predict_proba = lambda card: seen.append(card["deck_job_id"]) or proba(card)
    _pairs, excluded = calibration_pairs(scorer, load_decks(engine=_two_decks(True).eng))
    assert excluded["partner_redacted"] == 6 and "r" not in seen and "c" in seen


def test_the_flip_read_and_g3_keep_the_redacted_deck():
    """An outcome on a redacted card joins (not an orphan), and the weekly B4
    ceiling reads the deck as it did before the scrub."""
    late = _after(30)
    r = fr.flip_read(_two_decks(True).eng, since="2026-10-23T00:00:00+00:00", as_of=late)
    assert (r.g3["orphans"], r.g3["joined"]) == (0, r.g3["outcomes"])
    assert r.exclusions.get(PARTNER_REDACTED) == 1
    assert (fr.weekly_read(_two_decks(True).eng, as_of=late)
            == fr.weekly_read(_two_decks(False).eng, as_of=late))


# ---------------------------------------------------------------------------
# J1: the fit drops every redacted card
# ---------------------------------------------------------------------------

def _world(tmp_path, k=25):
    """Synthetic decks with k of the cards the fit reads scrubbed in memory
    (the token as partner, likes_you gone, surplus_margin nulled)."""
    db = tmp_path / "synth.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=300, seed=7)
    decks = load_decks(db_url=f"sqlite:///{db}")
    read = [c for d in decks for c in d.cards if c.viewed and not c.undone and c.features]
    for c in read[1::7][:k]:
        c.features = {**{key: v for key, v in c.features.items() if key != "likes_you"},
                      "partner_user_id": TOKEN, "surplus_margin": None}
    return decks, k


def _without_meta(model):
    return {key: v for key, v in model.to_dict().items() if key != "meta"}


def test_j1_no_redacted_card_becomes_a_training_row(tmp_path, mem_engine):
    decks, k = _world(tmp_path)
    like_rows, propose_rows = vm.build_training_rows(decks)
    assert not any(r["partner"] == TOKEN for r in like_rows + propose_rows)
    assert not any(r["card"].get("partner_user_id") == TOKEN for r in _fit_rows(decks))
    model = vm.train_model(decks, as_of=AS_OF)
    assert model.meta["exclusions"] == {vm.PARTNER_REDACTED: k}
    kept = [replace(d, cards=[c for c in d.cards if not c.partner_redacted]) for d in decks]
    assert _without_meta(model) == _without_meta(vm.train_model(kept, as_of=AS_OF))
    assert sum(c.partner_redacted for d in decks for c in d.cards) == k   # still loaded
    assert vm.PARTNER_REDACTED == PARTNER_REDACTED


# ---------------------------------------------------------------------------
# G-a5: what the scrub cleared, and the previous read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("previous, since", [(None, None), (EARLY, 1), ("2026-10-29", 2)],
                         ids=["no_previous_read", "between_the_two", "before_both"])
def test_g_a5_counts_what_the_scrub_cleared(previous, since):
    assert redaction_counts(_decks(), previous) == {
        "redacted_cards": 3, "redacted_cards_lacking": {"likes_you": 2},
        "redacted_at_decks": 2, "redacted_since_previous_read": since,
        "previous_read_at": previous}


def test_g_a5_and_the_share_are_on_the_run_its_record_and_its_report():
    run = evaluate(get_scorer("logged"), _decks(), ess_min=1, bootstrap=0, seed=0,
                   previous_read_at=EARLY)
    assert (run.redacted_cards, run.redacted_cards_lacking, run.redacted_at_decks,
            run.redacted_since_previous_read) == (3, {"likes_you": 2}, 2, 1)
    record = run_record(run, run)
    assert (record["redacted_cards"], record["redacted_since_previous_read"],
            record["previous_read_at"]) == (3, 1, EARLY)
    assert record["partner_redacted_share"] == {"decks": 1, "window_decks": 3, "over_gate": True}
    out = render_report([run], run)
    assert ("G-a5 redaction (every deck loaded): 3 redacted cards; lacking likes_you: 2 (an "
            "upper bound on what the scrub removed); 2 decks carry a pack redacted_at, 1 since "
            f"the previous read of this window ({EARLY}). Redacted decks are excluded, not "
            "compared.") in out
    assert ("partner_redacted (J1): 1 of 3 decks in the window excluded (33.3%); above 5%: a "
            "read used for a gate goes to models-lead before it's used.") in out
    assert "partner_redacted_decks=1" in out
    assert "no previous read of this window" in render_report(
        [r := evaluate(get_scorer("logged"), _decks(), ess_min=1, bootstrap=0, seed=0)], r)


def test_the_previous_read_is_the_latest_record_of_the_same_window():
    window = {"db": "x.db", "since": None, "until": "2026-10-30", "as_of": "2026-10-31"}
    assert previous_read_at(**window) is None
    append_run({**window, "recorded_at": "2026-10-31T01:00:00+00:00"})
    append_run({**window, "recorded_at": "2026-10-31T03:00:00+00:00"})
    append_run({**window, "as_of": "2026-11-01", "recorded_at": "2026-10-31T09:00:00+00:00"})
    assert previous_read_at(**window) == "2026-10-31T03:00:00+00:00"


def test_the_cli_reads_the_previous_read_of_its_window(tmp_path, capsys):
    from backend.eval.persistence import load_runs
    from backend.eval.replay import main
    db = tmp_path / "cli.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=20, seed=13)
    args = ["--db", str(db), "--scorer", "base_score", "--ess-min", "1", "--bootstrap", "10",
            "--until", "2030-01-01T00:00:00+00:00", "--as-of", "2030-01-02T00:00:00+00:00"]
    assert main(args) == 0
    first = load_runs()
    assert {r["previous_read_at"] for r in first} == {None}
    assert main(args) == 0
    second = load_runs()[len(first):]
    assert {r["previous_read_at"] for r in second} == {max(r["recorded_at"] for r in first)}
    out = capsys.readouterr().out
    assert "0 since the previous read of this window" in out
    assert "partner_redacted (J1): 0 of " in out
