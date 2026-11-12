"""Fast deck v2: rules-first construction of the whole owner deck (ADR-030, flag ``deck.rules_first``).

``serve`` builds the complete admitted inventory of a bilateral generator: every card that
passes the deck's per-card rules (``deck_rules.DeckRules``), ranked by the generator's own
ranker over admitted cards only. It runs the page-first search (``trade_first_page``) with
the rules as its admission predicate, taken to exhaustion, and falls back to the gated full
solve (``gated_full``) when the page cannot prove the whole inventory within its work limit
or does not support the request. There is no deck-size cap and no prefix length anywhere.

Both paths build the same deck for the same inputs (pinned by ``test_rules_first_deck``):
the gated full solve evaluates everything the incumbent's stream evaluates except
expansions whose terms already fail a rule, then ranks the admitted survivors. One caveat,
by design (operator, 2026-11-11): where the incumbent's stream budgets bind (very large
leagues), the page search covers the whole un-budgeted universe and the gated fallback the
budgeted one, so the page is the definition and a fallback there may serve a subset; the
result says which path ran and why, and the worker logs it.

What the user is served, against today's full solve then the downstream filters: the same
SET of cards for organic owner decks on the recorded production requests and the synthetic
leagues, in a different order (rejected cards no longer take ranking slots), EXCEPT
(a) leagues large enough for the incumbent's stream budgets to bind (16+ teams in the
tests): a superset, the evaluator-eligible cards the budgeted solve never reached;
(b) users at the decline-suppression floor (``server._DECK_MIN_CARDS``): the floor counts
admitted cards, so a heavy-decline user with a small admitted inventory can get up to 5
recently declined near-duplicates restored where today's deck was thinner; (c) the one
fatigue-retest grant can go to a different card (it goes to the first matching card in deck
order). Liked trades are not an exception: they are an overlay the worker evaluates after
generation, never an input to it. A liked mirror the generator did build is flagged as
before; one it did not build is proven on demand by the job's owner evaluator and gets a
full engine card (a bare consensus card when not eligible, as before).

The old 150-card fast deck (ADR-028, flags ``trade.fast_deck`` / ``trade.fast_deck_shadow``)
is retired: those flags are read nowhere.

Leaf module: no server, database, flag, provider or network access. The worker
(``server._run_trade_job``) reads the flag, builds the rules and owns logging and the
final fallback to today's full solve.
"""

import sys
from time import perf_counter

# Exact evaluations the page may spend before the gated full solve runs instead. The
# heaviest recorded production request needed 1,637 to exhaust its admitted inventory.
MAX_VERIFICATIONS = 12000
# Revision 5 (the season layer) joined with WI-8: its page bounds read the season lineup
# through its ``_page_bound_terms`` hook (``trade_first_page``); a request whose season
# inputs break the bounds' premise is declined by the page (``unsupported_inputs:*``) and
# served by the gated full solve.
_PARITY_TESTED = ("trade_gen_bilateral", "trade_gen_bilateral_candidate", "trade_gen_bilateral_season")
_ALL = 1 << 30  # take(n) with n past any inventory: run the search to exhaustion
# The clients read mismatch_score as "Match strength" = mismatch / MATCH_SCALE x 100, clamped
# (mobile/src/api/trades.ts). The generators set it to the card's position counted up from the
# bottom of what they emitted, so a full solve's thousands of cards read 100 for nearly every
# served card, while a rules-first inventory of a few hundred would read less and less down
# the deck (0 past the 300th card). Operator, 2026-11-11: the rollout must not visibly move
# the bar, so every rules-first card carries MATCH_SCALE (reads 100), what today's served
# cards read. It is a constant, so it carries no information (the impression feature
# surplus_margin copies it). composite_score, the ordering key the worker's layers read, is
# left as the generator set it.
MATCH_SCALE = 300.0


def _module(generate):
    """The generator's module when it is one with a page-search parity suite, else None."""
    module = sys.modules.get(getattr(generate, "__module__", None) or "")
    if module is None or module.__name__.rpartition(".")[2] not in _PARITY_TESTED:
        return None
    return module


def supported(generate) -> bool:
    """Whether rules-first construction can build this generator's deck at all."""
    return _module(generate) is not None


def _identity(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def page(generate, context, rules, *, check=None):
    """``(cards, report)``: the whole admitted inventory from the page search, or
    ``(None, reason)`` when it cannot be proven (``unsupported_request``, ``over_limit``,
    ``unsupported_inputs:<reason>``)."""
    from . import trade_first_page
    module = _module(generate)
    if module is None:
        return None, "unsupported_generator"
    if not trade_first_page._supported(context):
        return None, "unsupported_request"
    try:
        search = trade_first_page.PageSearch(generator=module, max_verifications=MAX_VERIFICATIONS,
                                             admit=rules.admits, rules_version=_version(),
                                             **context, _check_current=check)
    except trade_first_page.Unsupported as error:
        return None, "unsupported_inputs:" + error.reason
    cards, report = search.take(_ALL)
    if not report.as_dict()["complete"]:
        return None, "over_limit"
    return cards, report


def gated_full(generate, context, rules, *, check=None):
    """``(cards, report)``: the generator's full solve with the rules as a gate.

    Expansions (more than two assets) whose terms fail a rule are not evaluated (they get
    an ineligible ``deck_rules`` result, counted under ``rejections``); focal pairs are
    still evaluated because they are parents of expansions; failing survivors are dropped
    before the generator's own ranker runs. The generator modules are not modified."""
    from . import trade_first_page, trade_gen_bilateral as bilateral
    module = _module(generate)
    if module is None:
        raise ValueError("rules-first construction has no gated solve for this generator")
    started = perf_counter()
    base = getattr(module, "_GenerationSearch", None) or module._Search
    gated = trade_first_page._Rejected("deck_rules")

    class _Gated(base):
        def evaluate(self, card, *, partial=False):
            if (len(card.give_player_ids) + len(card.receive_player_ids) > 2
                    and not rules.admits(card.target_user_id, card.give_player_ids,
                                         card.receive_player_ids)):
                return gated
            return super().evaluate(card, partial=partial)

    def ranker(cards):
        return module._rank([c for c in cards if rules.admits(
            c.target_user_id, c.give_player_ids, c.receive_player_ids)])

    search = _Gated(**context, _check_current=check)
    cards, raw = bilateral._generate_with_search(search, ranker=ranker, version=module.VERSION)
    report = raw.as_dict()
    if hasattr(module, "_generation_report"):
        # Revision 5: the generator's own report over the gated result (same fields).
        report = module._generation_report(search, cards, raw, started).as_dict()
    elif getattr(module, "term_precedence", None) is not None:
        # The revision-2 report fields generate_bilateral_trades adds (same values).
        counts = {}
        for card in cards:
            data = card.owner_evaluation.as_dict()
            key = "efficient" if data["term_efficiency"]["efficient"] else "avoidable_alternative"
            counts[key] = counts.get(key, 0) + 1
            counts["companion_comparisons"] = (counts.get("companion_comparisons", 0)
                                               + data["term_efficiency"]["audited_alternatives"])
        report.update(support_weights=module._WEIGHTS, term_efficiency=counts,
                      term_ordering={"version": module.TERM_ORDERING_VERSION,
                                     "comparisons_per_family": module.TERM_LOOKAHEAD,
                                     "policy": "same_focal_precedence_preserve_inventory"},
                      starter_evidence="dynasty_proxy_only_no_projected_points")
    report.update(rules_version=_version(), construction="rules_first_gated_full",
                  elapsed_seconds=round(perf_counter() - started, 6))
    from . import trade_gen_owner as owner
    return cards, owner.OwnerGenerationReport(owner._dump(report))


def serve(generate, context, rules, *, check=None):
    """``(cards, report, info)`` for the whole admitted deck, or None when the generator
    has no rules-first construction (the caller runs today's full solve).

    ``info`` is aggregate-only, for the worker's log line: ``path`` (``page`` or
    ``gated_full``), ``fallback`` (why the page did not serve, else None), ``cards``,
    ``verified`` (page evaluations), ``budgets_bind``, ``ms`` and ``rules_rejected``
    (distinct packages rejected, by rule). A cancellation raised by ``check`` propagates."""
    if _module(generate) is None:
        return None
    started = perf_counter()
    info = {"rules_version": _version(), "fallback": None, "verified": None, "budgets_bind": None}
    try:
        cards, report = page(generate, context, rules, check=check)
    except Exception as error:  # noqa: BLE001 - a page failure falls back to the gated solve
        if _is_cancel(error):
            raise
        cards, report = None, "error:" + type(error).__name__
    if cards is not None:
        data = report.as_dict()
        info.update(path="page", verified=data["verified"], budgets_bind=data["incumbent_budgets_bind"])
    else:
        info.update(fallback=report)
        cards, report = gated_full(generate, context, rules, check=check)
        info.update(path="gated_full")
    for card in cards:
        card.mismatch_score = MATCH_SCALE
    info.update(cards=len(cards), ms=round((perf_counter() - started) * 1000, 1),
                rules_rejected=rules.rejected())
    return cards, report, info


def _is_cancel(error):
    from .trade_work_control import TradeWorkCancelled
    return isinstance(error, TradeWorkCancelled)


def _version():
    from .deck_rules import VERSION
    return VERSION
