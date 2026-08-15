"""Deterministic, template-based trade rationale narratives.

No LLM calls. Pure function over signals already computed by the trade
engine — keeps cost at zero and output predictable for snapshot tests.

Used by trade_service.generate_trades() to populate TradeCard.narrative.
"""
from __future__ import annotations

from typing import Optional


def _player_name(pid: str, players: dict) -> Optional[str]:
    p = players.get(pid)
    if p is None:
        return None
    return getattr(p, "name", None)


def _top_received(card, players: dict,
                  positions: Optional[set] = None) -> tuple[Optional[str],
                                                            Optional[str]]:
    """(name, position) of the highest-value received player (by dynasty
    value). When `positions` is given, only players at one of those
    positions are considered — so any sentence that names a position and a
    player names that player's *own* position, never one asserted from a
    separate source. (None, None) when nothing received qualifies.
    """
    # Lazy import to avoid circular import at module load.
    from .trade_service import dynasty_value

    best: tuple[Optional[str], Optional[str]] = (None, None)
    best_value = -1.0
    for pid in card.receive_player_ids:
        player = players.get(pid)
        if player is None:
            continue
        pos = getattr(player, "position", None)
        if positions is not None and pos not in positions:
            continue
        value = dynasty_value(player)
        if value > best_value:
            best_value = value
            best = (getattr(player, "name", None), pos)
    return best


def _top_received_name(card, players: dict) -> Optional[str]:
    """Name of the highest-value received player (by dynasty value)."""
    return _top_received(card, players)[0]


def _fairness_label(score: float) -> str:
    if score >= 0.95:
        return "perfectly balanced"
    if score >= 0.85:
        return "balanced"
    if score >= 0.70:
        return "slight tilt"
    return "uneven on paper"


def _has_picks(card, players: dict) -> bool:
    for pid in (*card.give_player_ids, *card.receive_player_ids):
        p = players.get(pid)
        if p is not None and getattr(p, "position", None) == "PICK":
            return True
    return False


def _give_side_now_lean(card, players: dict) -> float:
    """Mean now-lean of what the user sends (interview phase 2 framing).
    Positive = proven production leaving; negative = youth/picks leaving."""
    from .trade_service import _now_lean   # lazy: avoids circular import

    leans = []
    for pid in card.give_player_ids:
        p = players.get(pid)
        if p is None:
            continue
        leans.append(_now_lean(getattr(p, "position", None),
                               getattr(p, "age", None)))
    return sum(leans) / len(leans) if leans else 0.0


def _opponent_frame(card, match_context: Optional[dict],
                    players: dict) -> Optional[str]:
    """Interview phase 2 — acceptance framing: pitch the trade in the
    counterparty's window terms ("their team story") when what the user
    sends actually fits it. None when there's no story to tell."""
    opp = (match_context or {}).get("opponent_outlook") or {}
    outlook = opp.get("value")
    if outlook not in ("rebuilder", "jets", "contender", "championship"):
        return None
    lean = _give_side_now_lean(card, players)
    if outlook in ("rebuilder", "jets") and lean <= -0.05:
        return "They're rebuilding — the youth going back fits their timeline."
    if outlook in ("contender", "championship") and lean >= 0.05:
        return "They're pushing to win now — your proven pieces fit their window."
    return None


def build_narrative(card, match_context: Optional[dict], players: dict) -> str:
    """
    Compose ≤2 sentences explaining why this trade fits the user.

    Sentence 1: the honest fit-premium note (when the card pays one) OR
                positional fit OR a fairness statement.
    Sentence 2: counterparty-window framing (when their story fits) OR
                dynasty / pick context (only when picks are involved).
    """
    sentences: list[str] = []

    needs   = (match_context or {}).get("user_needs", [])
    surplus = (match_context or {}).get("opponent_surplus", [])
    overlap = [p for p in needs if p in surplus]
    target  = _top_received_name(card, players)

    # Positional claims name a player who actually plays that position.
    # `needs` / `overlap` come from the roster analysis and the received
    # players come from the card — pairing the two blindly asserted things
    # like "Adds Brock Bowers to address your thin QB group". Each branch
    # below resolves the player and the position together, and falls
    # through to the neutral fairness sentence when nothing received fills
    # a need, rather than inventing a benefit.
    fit_prem = getattr(card, "fit_premium", None)
    fit_pos  = (fit_prem or {}).get("position")
    fit_name = _top_received(card, players, {fit_pos})[0] if fit_pos else None
    overlap_name, overlap_pos = (_top_received(card, players, set(overlap))
                                 if overlap else (None, None))
    needs_name, needs_pos = (_top_received(card, players, set(needs))
                             if needs else (None, None))

    if fit_name:
        sentences.append(
            f"Fills your {fit_pos} hole with {fit_name} — you pay a little on "
            f"your own board for the fit."
        )
    elif overlap_name:
        sentences.append(
            f"You shore up {overlap_pos} by acquiring {overlap_name}."
        )
    elif needs_name:
        sentences.append(
            f"Adds {needs_name} to address your thin {needs_pos} group."
        )
    elif target:
        fair = _fairness_label(card.fairness_score)
        sentences.append(
            f"{target} comes back in a {fair} package."
        )

    fair = _fairness_label(card.fairness_score)
    if not sentences:
        sentences.append(f"Trade looks {fair}.")

    frame = _opponent_frame(card, match_context, players)
    if frame:
        sentences.append(frame)
    elif _has_picks(card, players):
        settings = (match_context or {}).get("league_settings", {})
        if settings.get("dynasty"):
            sentences.append("Includes a dynasty pick — value scales with your league size.")
        else:
            sentences.append("Pick value reflects league depth.")

    # Cap at 2 sentences.
    return " ".join(sentences[:2])
