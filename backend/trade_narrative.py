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


def _top_received_name(card, players: dict) -> Optional[str]:
    """Name of the highest-value received player (by dynasty value)."""
    # Lazy import to avoid circular import at module load.
    from .trade_service import dynasty_value

    best_name: Optional[str] = None
    best_value = -1.0
    for pid in card.receive_player_ids:
        player = players.get(pid)
        if player is None:
            continue
        value = dynasty_value(player)
        if value > best_value:
            best_value = value
            best_name = getattr(player, "name", None)
    return best_name


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

    fit_prem = getattr(card, "fit_premium", None)
    if fit_prem and target:
        pos = fit_prem.get("position") or (needs[0] if needs else "a need")
        sentences.append(
            f"Fills your {pos} hole with {target} — you pay a little on "
            f"your own board for the fit."
        )
    elif overlap and target:
        sentences.append(
            f"You shore up {overlap[0]} by acquiring {target}."
        )
    elif needs and target:
        sentences.append(
            f"Adds {target} to address your thin {needs[0]} group."
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
