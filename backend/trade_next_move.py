"""The next move (offer-learnings R2, WS5): at most one revision of a sent offer.

Behind flag ``trade.next_move`` (default off). Off, ``propose_revision`` and
``propose_middle_ground`` return ``None`` before any evaluation. The one
production caller is ``trade_revised_offers`` (WS8, treatment A): a declined
offer gets ``propose_revision(..., kinds=(SWAP,))`` with the 5-15% band, a
declined counter gets ``propose_middle_ground``.

The rule, for a sent offer (viewer gives G, receives R):

1. **Core assets stay.** The focal asset on each side, the one with the
   highest consensus value (ties by id, as the engine's ``_head``), is never
   removed.
2. **One change.** A candidate either adds one asset from the viewer's roster
   to G, or removes one non-focal asset from R. The viewer's own untouchables
   are never added. A third kind, ``swap_in_give`` (WS8), is used only when
   asked for (``kinds``): one asset of G is replaced by one more valuable
   asset (consensus) from the viewer's roster, so the trade keeps its size
   and every asked-for asset; it may replace the focal asset of G.
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
   then a removal before an addition (smaller trades); then asset id (for a
   swap, the incoming asset's id, then the outgoing one's).

The middle ground (``propose_middle_ground``, WS8 1b) is documented on the
function.

Leaf module: no database, server, provider or network access.
"""

from dataclasses import dataclass
from itertools import combinations

from . import bakeoff_runner, feature_flags
from . import trade_service as ts

FLAG = "trade.next_move"
VERSION = "next-move-1"
STEP_MIN = .10
STEP_MAX = .20
SWAP = "swap_in_give"
DEFAULT_KINDS = ("remove_from_receive", "add_to_give")
# WS8 — a declined offer's revision ("slightly more valuable"): 5-15% of the
# trade's market value.
SWAP_STEP_MIN = .05
SWAP_STEP_MAX = .15
# WS8 1b — the middle ground: about half of the gap, accepted from 35% to 65%;
# at most MIDDLE_MAX_POOL assets held by only one of the two versions.
MIDDLE_SHARE = .5
MIDDLE_BAND = (.35, .65)
MIDDLE_MAX_POOL = 6
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
    change: dict               # {"kind": "add_to_give" | "remove_from_receive", "asset_id"};
                               # swap_in_give adds "replaces"; middle_ground: see that function
    core: dict                 # {"give": focal id, "receive": focal id}
    step_value: float          # other manager's net market gain vs the original
    step_fraction: float       # step_value / trade_market_value
    trade_market_value: float  # larger side of the original at evaluator pricing
    version: str = VERSION


def _focal(ids, value):
    return max(ids, key=lambda pid: (value(pid), pid))


def propose_revision(offer, context, *, step_min=STEP_MIN, step_max=STEP_MAX,
                     kinds=DEFAULT_KINDS):
    """Return one ``NextMove`` for ``offer`` (a TradeCard), or ``None``.

    ``context`` is the owner evaluation context for the viewer, as built by
    ``server._owner_generation_context``. ``kinds`` selects the changes tried
    (the default is WS5's two; WS8's declined-offer path passes ``(SWAP,)``).
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
        changes = []
        if "remove_from_receive" in kinds:
            changes += [("remove_from_receive", pid, "") for pid in receive
                        if len(receive) > 1 and pid != core["receive"]]
        if "add_to_give" in kinds:
            changes += [("add_to_give", pid, "") for pid in context["user_roster"]
                        if pid not in give and pid not in untouchable and known(pid)]
        if SWAP in kinds:
            changes += [(SWAP, pid, old) for old in give for pid in context["user_roster"]
                        if pid not in give and pid not in untouchable and known(pid)
                        and value(pid) > value(old)]
    if not changes:
        return None

    def revised(kind, pid, old):
        # A fresh card, as the engine builds one: nothing of the original's
        # evidence or selection carries over.
        if kind == SWAP:
            g = [pid if p == old else p for p in give]
        else:
            g = give + [pid] if kind == "add_to_give" else list(give)
        r = [p for p in receive if p != pid] if kind == "remove_from_receive" else list(receive)
        return ts.TradeCard("", offer.league_id, offer.proposing_user_id, offer.target_user_id,
                            offer.target_username, g, r, 0, 0, 0)

    cards = [revised(kind, pid, old) for kind, pid, old in changes]
    proofs = evaluate(cards, **kwargs)
    found = []
    for (kind, pid, old), card, proof in zip(changes, cards, proofs):
        if not proof.eligible:
            continue
        terms = proof.as_dict()["market"]
        step = (terms["give"] - terms["receive"]) - base_net
        fraction = step / trade_value
        if step_min - _EPS <= fraction <= step_max + _EPS:
            found.append((fraction, kind != "remove_from_receive", pid, old, kind, card, proof, step, terms))
    if not found:
        return None
    fraction, _, pid, old, kind, card, proof, step, terms = min(found, key=lambda f: f[:4])
    card.give_value, card.receive_value, card.fairness_score = terms["give"], terms["receive"], terms["ratio"]
    card.owner_evaluation = proof
    change = {"kind": kind, "asset_id": pid, **({"replaces": old} if kind == SWAP else {})}
    return NextMove(card=card, proof=proof, change=change, core=core,
                    step_value=step, step_fraction=fraction, trade_market_value=trade_value)


def propose_middle_ground(original, counter, context, *, share=MIDDLE_SHARE, band=MIDDLE_BAND):
    """One card between ``original`` (the user's offer, as sent) and
    ``counter`` (the other manager's counter to it, from the user's side,
    which the user declined), or ``None`` (WS8 1b).

    Rule. Every asset both versions share stays. On each side any subset of the
    assets only one version holds may be added and, on the user's side, at
    most one further asset from the user's roster (never an untouchable the
    original did not already offer). The card is no larger than the larger
    version and is neither version. The other manager's net market gain at
    evaluator pricing (``market.give - market.receive``) must move from the
    original's toward the counter's by ``band`` of the gap; the one closest to
    ``share`` wins (then fewer assets, then asset ids). The counter must have
    asked for more (a positive gap), and at most ``MIDDLE_MAX_POOL`` assets
    may differ between the two versions. Proven by ``owner_evaluator(config)``
    with organic gates, like every revision.
    """
    if not feature_flags.is_enabled(FLAG):
        return None
    g0, r0 = list(original.give_player_ids), list(original.receive_player_ids)
    g1, r1 = list(counter.give_player_ids), list(counter.receive_player_ids)
    if not (g0 and r0 and g1 and r1):
        return None
    config = dict(context.get("config") or {})
    evaluate = bakeoff_runner.owner_evaluator(config)
    kwargs = {**context, **_ORGANIC}
    base, asked = evaluate([original, counter],
                           **{**kwargs, "past_decision_keys": (), "exclusion_keys": ()})
    m0, m1 = base.as_dict().get("market"), asked.as_dict().get("market")
    if not m0 or not m1:
        return None
    n0 = m0["give"] - m0["receive"]
    gap, trade_value = (m1["give"] - m1["receive"]) - n0, max(m0["give"], m0["receive"])
    if gap <= _EPS or trade_value <= 0:
        return None
    shared_g = [p for p in g0 if p in g1]
    shared_r = [p for p in r0 if p in r1]
    pool_g, pool_r = sorted(set(g0) ^ set(g1)), sorted(set(r0) ^ set(r1))
    if len(pool_g) + len(pool_r) > MIDDLE_MAX_POOL:
        return None
    size = max(len(g0) + len(r0), len(g1) + len(r1))
    players, seed = context["players"], context["seed_elo"]
    with ts._cfg_override(config):
        value = ts.make_consensus_value_fn(seed, players)
        def known(pid):
            return pid in players and pid in seed and value(pid) > 0
        if not all(known(p) for p in g0 + r0 + g1 + r1):
            return None
        prefs = (context.get("manager_preferences") or {}).get(context["user_id"]) or {}
        untouchable = set(prefs.get("untouchables") or ()) - set(g0)
        extras = [None] + [p for p in context["user_roster"] if p not in g0 and p not in g1
                           and p not in untouchable and known(p)]
    versions = {(frozenset(g0), frozenset(r0)), (frozenset(g1), frozenset(r1))}
    seen, shapes, cards = set(), [], []
    for gi in range(len(pool_g) + 1):
        for sub_g in combinations(pool_g, gi):
            for extra in extras:
                give = shared_g + list(sub_g) + ([extra] if extra else [])
                if not give or set(give) & untouchable:
                    continue
                for ri in range(len(pool_r) + 1):
                    for sub_r in combinations(pool_r, ri):
                        receive = shared_r + list(sub_r)
                        key = (frozenset(give), frozenset(receive))
                        if (not receive or len(give) + len(receive) > size
                                or key in versions or key in seen):
                            continue
                        seen.add(key)
                        shapes.append((give, receive))
                        cards.append(ts.TradeCard(
                            "", original.league_id, original.proposing_user_id,
                            original.target_user_id, original.target_username,
                            give, receive, 0, 0, 0))
    if not cards:
        return None
    found = []
    for (give, receive), card, proof in zip(shapes, cards, evaluate(cards, **kwargs)):
        if not proof.eligible:
            continue
        terms = proof.as_dict()["market"]
        moved = ((terms["give"] - terms["receive"]) - n0) / gap
        if band[0] - _EPS <= moved <= band[1] + _EPS:
            found.append((abs(moved - share), len(give) + len(receive), sorted(give),
                          sorted(receive), moved, card, proof, terms))
    if not found:
        return None
    _, _, give, receive, moved, card, proof, terms = min(found, key=lambda f: f[:4])
    card.give_value, card.receive_value, card.fairness_score = terms["give"], terms["receive"], terms["ratio"]
    card.owner_evaluation = proof
    step = (terms["give"] - terms["receive"]) - n0
    change = {"kind": "middle_ground", "gap_share": round(moved, 4),
              "added_give": sorted(set(give) - set(g0)), "removed_give": sorted(set(g0) - set(give)),
              "added_receive": sorted(set(receive) - set(r0)),
              "removed_receive": sorted(set(r0) - set(receive))}
    return NextMove(card=card, proof=proof, change=change,
                    core={"give": shared_g, "receive": shared_r}, step_value=step,
                    step_fraction=step / trade_value, trade_market_value=trade_value)
