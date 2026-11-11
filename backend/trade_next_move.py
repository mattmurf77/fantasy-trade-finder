"""The next move (offer-learnings R2, WS5): at most one revision of a sent offer.

Behind flag ``trade.next_move`` (default off). Off, ``propose_revision``
returns ``None`` before any evaluation. Nothing outside the tests calls this
module yet: the app UI waits for the operator to pick a treatment from
``mockups/next-move/``.

The rule, for a sent offer (viewer gives G, receives R):

1. **Core assets stay.** The focal asset on each side, the one with the
   highest consensus value (ties by id, as the engine's ``_head``), is never
   removed.
2. **One change.** A candidate either adds one asset from the viewer's roster
   to G, or removes one non-focal asset from R. The viewer's own untouchables
   are never added.
3. **Proven by the evaluator in force.** Every candidate is judged by
   ``bakeoff_runner.owner_evaluator(config)``, the same function that proves
   any served card for the selected engine revision, with organic gates (no
   pins, no intent): market floor and overpay ceiling, both sides' benefit and
   intent checks (the viewer's included), untouchables, previous dispositions,
   organic shape and, for the bilateral revisions, unnecessary compensation.
   An ineligible candidate is never offered.
4. **Bounded step.** The other manager's net market position, priced by the
   same evaluator's package pricing, must improve by between 10% and 20% of
   the trade's market value: the larger side of the original offer at that
   pricing. The original is priced by the evaluator with dispositions ignored
   (a sent offer is normally a liked card); if the evaluator cannot price it
   (an asset has moved, a non-organic shape), there is no revision.
5. **At most one.** Among eligible, in-band candidates the smallest step wins;
   then a removal before an addition (smaller trades); then asset id.

Leaf module: no database, server, provider or network access.
"""

from dataclasses import dataclass

from . import bakeoff_runner, feature_flags
from . import trade_service as ts

FLAG = "trade.next_move"
VERSION = "next-move-1"
STEP_MIN = .10
STEP_MAX = .20
_EPS = 1e-9
# A revision must stand as an organic card: the original's selection does not
# carry over, so explicit-selection paths cannot qualify it.
_ORGANIC = dict(pinned_give_players=None, pinned_receive_players=None, exact_give=False,
                require_all_give=False, trade_intent=None, swap_positions=None,
                lateral_scope=None, max_cards=None)


@dataclass(frozen=True)
class NextMove:
    card: object               # TradeCard bound to ``proof`` (proof.matches(card))
    proof: object              # the evaluator's frozen eligible decision
    change: dict               # {"kind": "add_to_give" | "remove_from_receive", "asset_id"}
    core: dict                 # {"give": focal id, "receive": focal id}
    step_value: float          # other manager's net market gain vs the original
    step_fraction: float       # step_value / trade_market_value
    trade_market_value: float  # larger side of the original at evaluator pricing
    version: str = VERSION


def _focal(ids, value):
    return max(ids, key=lambda pid: (value(pid), pid))


def propose_revision(offer, context, *, step_min=STEP_MIN, step_max=STEP_MAX):
    """Return one ``NextMove`` for ``offer`` (a TradeCard), or ``None``.

    ``context`` is the owner evaluation context for the viewer, as built by
    ``server._owner_generation_context``.
    """
    if not feature_flags.is_enabled(FLAG):
        return None
    give, receive = list(offer.give_player_ids), list(offer.receive_player_ids)
    if not give or not receive:
        return None
    config = dict(context.get("config") or {})
    evaluate = bakeoff_runner.owner_evaluator(config)
    kwargs = {**context, **_ORGANIC}

    baseline = evaluate([offer], **{**kwargs, "past_decision_keys": (), "exclusion_keys": ()})[0]
    market = baseline.as_dict().get("market")
    if not market:
        return None
    base_net = market["give"] - market["receive"]
    trade_value = max(market["give"], market["receive"])

    players, seed = context["players"], context["seed_elo"]
    with ts._cfg_override(config):
        value = ts.make_consensus_value_fn(seed, players)
        def known(pid):
            return pid in players and pid in seed and value(pid) > 0
        if not all(known(p) for p in give + receive):
            return None
        core = {"give": _focal(give, value), "receive": _focal(receive, value)}
        prefs = (context.get("manager_preferences") or {}).get(context["user_id"]) or {}
        untouchable = set(prefs.get("untouchables") or ())
        changes = [("remove_from_receive", pid) for pid in receive
                   if len(receive) > 1 and pid != core["receive"]]
        changes += [("add_to_give", pid) for pid in context["user_roster"]
                    if pid not in give and pid not in untouchable and known(pid)]
    if not changes:
        return None

    def revised(kind, pid):
        # A fresh card, as the engine builds one: nothing of the original's
        # evidence or selection carries over.
        g = give + [pid] if kind == "add_to_give" else list(give)
        r = [p for p in receive if p != pid] if kind == "remove_from_receive" else list(receive)
        return ts.TradeCard("", offer.league_id, offer.proposing_user_id, offer.target_user_id,
                            offer.target_username, g, r, 0, 0, 0)

    cards = [revised(kind, pid) for kind, pid in changes]
    proofs = evaluate(cards, **kwargs)
    found = []
    for (kind, pid), card, proof in zip(changes, cards, proofs):
        if not proof.eligible:
            continue
        terms = proof.as_dict()["market"]
        step = (terms["give"] - terms["receive"]) - base_net
        fraction = step / trade_value
        if step_min - _EPS <= fraction <= step_max + _EPS:
            found.append((fraction, kind != "remove_from_receive", pid, kind, card, proof, step, terms))
    if not found:
        return None
    fraction, _, pid, kind, card, proof, step, terms = min(found, key=lambda f: f[:3])
    card.give_value, card.receive_value, card.fairness_score = terms["give"], terms["receive"], terms["ratio"]
    card.owner_evaluation = proof
    return NextMove(card=card, proof=proof, change={"kind": kind, "asset_id": pid}, core=core,
                    step_value=step, step_fraction=fraction, trade_market_value=trade_value)
