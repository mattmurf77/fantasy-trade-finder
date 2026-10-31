"""What the deletion scrub cleared, and the fit's named exclusion (models-lead
addendum G, G-a5 and G-a6; addendum I5).

The loader marks a card whose partner is a redaction token
(LoggedCard.partner_redacted) and reads its pack's redacted_at. Replay's
per-window record counts the redacted cards, those lacking each c2 field, and
the decks redacted since the previous read of the same window (G-a5). The
fit keeps redacted cards until those lacking likes_you exceed 1% of the fit
window's cards with likes_you true, then leaves them all out as the named
exclusion partner_redacted (value_model, G-a6); replay and every other
reader still see every card.
"""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
from backend import value_model as vm
from backend.database import metadata
from backend.eval import evidence_pack as ep
from backend.eval.contract import REDACTED_PARTNER_PREFIX
from backend.eval.data import LoggedCard, LoggedDeck, load_decks
from backend.eval.persistence import append_run, previous_read_at, run_record
from backend.eval.replay import evaluate, redaction_counts, render_report
from backend.eval.scorers import get_scorer
from backend.eval.synth import build_synthetic_db
from backend.tests.test_eval_pack_reader import (SERVED, _card, insert_pack, make_engine,
                                                 write_deck)

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


# ---------------------------------------------------------------------------
# The loader's mark and G-a5's counts
# ---------------------------------------------------------------------------

def _redacted(card: dict, keep_like: bool = False) -> dict:
    """The scrub's card: the token as partner, likes_you gone (b2's
    uniformity), unless `keep_like` (to show the count reads the key)."""
    out = {**card, "partner_user_id": TOKEN}
    if not keep_like:
        del out["likes_you"]
    return out


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
    redacted later."""
    eng, packs = make_engine()
    j = [_card("j", i) for i in range(10)]
    j[0], j[3], j[7] = _redacted(j[0]), _redacted(j[3], keep_like=True), _redacted(j[7])
    write_deck(eng, packs, j, full=range(5))
    _pack(eng, packs, j[5:], card_count=10, redacted_at=EARLY)
    write_deck(eng, packs, [_card("k", i) for i in range(4)], full=range(4))
    _pack(eng, packs, [_card("m", i) for i in range(3)], card_count=3, redacted_at=LATE)
    return load_decks(engine=eng)


def test_the_loader_marks_redacted_cards_and_reads_the_packs_redacted_at():
    decks = {d.deck_job_id: d for d in _decks()}
    marked = {(d, c.card_index) for d, deck in decks.items() for c in deck.cards
              if c.partner_redacted}
    assert marked == {("j", 0), ("j", 3), ("j", 7)}          # rows and a packed card
    assert {d: deck.redacted_at for d, deck in decks.items()} == {
        "j": EARLY, "k": None, "m": LATE}


def test_a_platform_id_that_merely_contains_the_prefix_is_not_marked():
    eng, packs = make_engine()
    write_deck(eng, packs, [{**_card("j", 0), "partner_user_id": f"x{TOKEN}"}], full=range(1))
    assert not load_decks(engine=eng)[0].cards[0].partner_redacted


@pytest.mark.parametrize("previous, since", [(None, None), (EARLY, 1), ("2026-10-29", 2)],
                         ids=["no_previous_read", "between_the_two", "before_both"])
def test_g_a5_counts_what_the_scrub_cleared(previous, since):
    assert redaction_counts(_decks(), previous) == {
        "redacted_cards": 3, "redacted_cards_lacking": {"likes_you": 2},
        "redacted_at_decks": 2, "redacted_since_previous_read": since,
        "previous_read_at": previous}


def test_g_a5_and_g_a6_are_on_the_run_its_record_and_its_report():
    run = evaluate(get_scorer("logged"), _decks(), ess_min=1, bootstrap=0, seed=0,
                   previous_read_at=EARLY)
    assert (run.redacted_cards, run.redacted_cards_lacking, run.redacted_at_decks,
            run.redacted_since_previous_read) == (3, {"likes_you": 2}, 2, 1)
    record = run_record(run, run)
    assert (record["redacted_cards"], record["redacted_since_previous_read"],
            record["previous_read_at"]) == (3, 1, EARLY)
    assert record["partner_redacted_test"] == run.partner_redacted_test
    out = render_report([run], run)
    assert ("G-a5 redaction (every deck loaded): 3 redacted cards; lacking likes_you: 2 (an "
            "upper bound on what the scrub removed); 2 decks carry a pack redacted_at, 1 since "
            f"the previous read of this window ({EARLY}).") in out
    # No card is viewed here, so the fit reads none of them and the test can't fire.
    assert ("G-a6: a refit on this window keeps the partner_redacted cards (0 redacted cards "
            "lacking likes_you, within 1% of 0 cards with likes_you, among the cards a fit "
            "reads).") in out
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
    assert "0 since the previous read of this window" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# G-a6: the 1% test and the fit's named exclusion
# ---------------------------------------------------------------------------

def _logged(i, *, likes_you=None, partner="opp1", viewed=True, undone=False) -> LoggedCard:
    f = {"partner_user_id": partner}
    if likes_you is not None:
        f["likes_you"] = likes_you
    return LoggedCard(impression_id=f"d:{i}", deck_job_id="d", user_id="u1", league_id="lg",
                      card_index=i, trade_hash=None, propensity=None, base_score=None,
                      final_score=None, archetype=None, shape_bucket=None, served_at=SERVED,
                      features=f, viewed=viewed, undone=undone)


@pytest.mark.parametrize("lost, fires", [(1, False), (2, True)], ids=["at_1_percent", "above"])
def test_the_1_percent_test_counts_only_cards_the_fit_reads(lost, fires):
    cards = [_logged(i, likes_you=True) for i in range(100)]
    cards += [_logged(100 + i, partner=TOKEN) for i in range(lost)]
    cards += [_logged(200, partner=TOKEN, viewed=False),           # the fit never reads these
              _logged(201, partner=TOKEN, undone=True),
              _logged(202, likes_you=True, viewed=False)]
    assert vm.partner_redacted_test([LoggedDeck("d", "u1", "lg", SERVED, cards=cards)]) == {
        "lost_likes": lost, "liked": 100, "fires": fires, "excluded": lost if fires else 0}


def _world(tmp_path, extra):
    """Synthetic decks: every other card the fit reads carries likes_you
    true; then liked // 100 + `extra` of the others are redacted (the token
    as partner, likes_you gone). Returns (decks, redacted count)."""
    db = tmp_path / "synth.db"
    build_synthetic_db(f"sqlite:///{db}", n_decks=300, seed=7)
    decks = load_decks(db_url=f"sqlite:///{db}")
    read = [c for d in decks for c in d.cards if c.viewed and not c.undone and c.features]
    for i, c in enumerate(read):
        c.features = {**c.features, "likes_you": i % 2 == 0}
    liked = sum(1 for c in read if c.features["likes_you"])
    assert liked >= 200, liked
    k = liked // 100 + extra
    for c in read[1::2][:k]:
        c.features = {**{key: v for key, v in c.features.items() if key != "likes_you"},
                      "partner_user_id": TOKEN}
    return decks, k


def _without_meta(model):
    return {key: v for key, v in model.to_dict().items() if key != "meta"}


def test_g_a6_below_1_percent_the_fit_keeps_every_redacted_card(tmp_path, mem_engine):
    decks, k = _world(tmp_path, extra=0)                       # k * 100 <= liked
    model = vm.train_model(decks, as_of=AS_OF)
    like_rows, propose_rows = vm.build_training_rows(decks)
    assert any(r["partner"] == TOKEN for r in like_rows)
    assert (model.meta["n_like_rows"], model.meta["n_propose_rows"]) == (
        len(like_rows), len(propose_rows))
    assert model.meta["exclusions"] == {}
    assert (model.meta["partner_redacted_test"]["lost_likes"],
            model.meta["partner_redacted_test"]["fires"]) == (k, False)


def test_g_a6_above_1_percent_the_fit_leaves_the_redacted_cards_out(tmp_path, mem_engine,
                                                                     monkeypatch, caplog):
    decks, k = _world(tmp_path, extra=1)                       # k * 100 > liked
    model = vm.train_model(decks, as_of=AS_OF)
    assert model.meta["exclusions"] == {vm.PARTNER_REDACTED: k}
    assert model.meta["partner_redacted_test"] == {
        "lost_likes": k, "liked": model.meta["partner_redacted_test"]["liked"],
        "fires": True, "excluded": k}
    assert "partner_redacted exclusion (G-a6): %d redacted cards" % k in caplog.text
    # The same fit as one on the decks without those cards.
    kept = [replace(d, cards=[c for c in d.cards if not c.partner_redacted]) for d in decks]
    assert _without_meta(model) == _without_meta(vm.train_model(kept, as_of=AS_OF))
    # It differs from keeping them, and the decks still hold every card.
    monkeypatch.setattr(vm, "PARTNER_REDACTED_MAX_PCT", 10 ** 9)
    assert _without_meta(model) != _without_meta(vm.train_model(decks, as_of=AS_OF))
    assert sum(c.partner_redacted for d in decks for c in d.cards) == k
