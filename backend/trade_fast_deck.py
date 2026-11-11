"""Fast deck: page-first search as the trade worker's owner generator (ADR-028).

``serve`` answers an owner generation request with the proven first
``DECK_SIZE`` cards of the selected bilateral generator instead of its full
inventory, or ``None`` when the caller must run the full solve: a generator the
page search has no parity suite for, a request it does not support (pinned
assets, exact give), a search that could not prove its page, or a league large
enough for the incumbent's stream budgets to bind (the two universes may then
differ). ``shadow`` runs the same page next to a finished full solve and
reports how far the two agree; it changes nothing.

The cards and proofs are the unchanged evaluator's, so every downstream check
treats them as it treats a full solve's. What changes is depth: the deck ends at
``DECK_SIZE`` cards and the rest of the inventory is not built for it.

Leaf module: no server, database, flag, provider or network access. The worker
(``server._run_trade_job``) reads the flags and owns the fallback and logging.
"""

import sys
from time import perf_counter

DECK_SIZE = 150
# Exact evaluations a page may spend before it gives up and the full solve runs.
# A full solve spends about 45,000; the heaviest recorded production request
# needed 5,015 for 150 cards (a sparse 13-team league), the median about 900.
MAX_VERIFICATIONS = 12000
_PARITY_TESTED = ("trade_gen_bilateral", "trade_gen_bilateral_candidate")


def _page(generate, context, check, k):
    module = sys.modules.get(getattr(generate, "__module__", None) or "")
    if module is None or module.__name__.rpartition(".")[2] not in _PARITY_TESTED:
        return None
    from . import trade_first_page
    return trade_first_page.first_page(k=k, generator=module, max_verifications=MAX_VERIFICATIONS,
                                       **context, _check_current=check)


def _identity(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def serve(generate, context, *, check=None, k=DECK_SIZE):
    """``(cards, report)`` for the proven first ``k``, or None: run the full solve."""
    result = _page(generate, context, check, k)
    if result is None:
        return None
    data = result[1].as_dict()
    if not data["complete"] or data["incumbent_budgets_bind"]:
        return None
    return result


def shadow(cards, generate, context, *, check=None, k=DECK_SIZE):
    """Compare a page with the finished full solve ``cards``: counts only, or None."""
    started = perf_counter()
    result = _page(generate, context, check, k)
    if result is None:
        return None
    page, report = result
    data = report.as_dict()
    got, want = [_identity(c) for c in page], [_identity(c) for c in cards[:k]]
    agree = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
    return {"k": k, "identical": got == want, "agree_prefix": agree, "page": len(got),
            "full": len(cards), "complete": data["complete"],
            "budgets_bind": data["incumbent_budgets_bind"], "verified": data["verified"],
            "page_first_version": data["page_first_version"],
            "page_ms": round((perf_counter() - started) * 1000, 1)}
