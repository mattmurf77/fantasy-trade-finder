"""Account-deletion redaction, the eval side (legal R28.20; models-lead E-b1,
E-b5 and the partner-hash rule).

The deletion scrub replaces a deleted user's platform id in other users'
records with one random token per deleted user (contract.
REDACTED_PARTNER_PREFIX). Eval counts the distinct tokens in a run's window
(EvalRun.redacted_partners, persisted and printed), so a refit that differs
across a deletion is explained, and never resolves one.
"""

from backend.eval.contract import REDACTED_PARTNER_PREFIX
from backend.eval.data import load_decks
from backend.eval.persistence import run_record
from backend.eval.replay import evaluate, redacted_partners, render_report
from backend.eval.scorers import get_scorer
from backend.tests.test_eval_pack_reader import _card, make_engine, write_deck

TOKEN_A, TOKEN_B = f"{REDACTED_PARTNER_PREFIX}aa11", f"{REDACTED_PARTNER_PREFIX}bb22"


def _with_partner(job, i, partner):
    return {**_card(job, i), "partner_user_id": partner}


def _decks():
    """Two decks: rows and packed cards, two cards on one token, one on
    another, the rest platform ids."""
    eng, packs = make_engine()
    partners = {0: TOKEN_A, 3: TOKEN_A, 7: TOKEN_B}       # 7 is a packed card
    cards = [_with_partner("j", i, partners.get(i, f"opp{i % 3}")) for i in range(10)]
    write_deck(eng, packs, cards, full=range(5), packed=range(5, 10), card_count=10)
    write_deck(eng, packs, [_card("k", i) for i in range(4)], full=range(4))
    return load_decks(engine=eng)


def test_the_window_counts_each_redaction_token_once():
    decks = _decks()
    assert redacted_partners(decks) == 2
    assert redacted_partners([d for d in decks if d.deck_job_id == "k"]) == 0


def test_the_count_is_on_the_run_its_record_and_its_report():
    decks = _decks()
    run = evaluate(get_scorer("logged"), decks, ess_min=1, bootstrap=0, seed=0)
    assert run.redacted_partners == 2
    assert run_record(run, run)["redacted_partners"] == 2
    assert "redacted_partners=2" in render_report([run], run)


def test_a_platform_id_that_merely_contains_the_prefix_is_not_a_token():
    eng, packs = make_engine()
    write_deck(eng, packs, [_with_partner("j", 0, f"x{REDACTED_PARTNER_PREFIX}1")],
               full=range(1))
    assert redacted_partners(load_decks(engine=eng)) == 0
