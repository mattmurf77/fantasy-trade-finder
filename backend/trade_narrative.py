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


# ─────────────────── counterparty breaker — hesitation line ───────────────────
# Additive surface for the counterparty breaker (docs/plans/counterparty-breaker
# LLD §1.6, PRD §5.4). `build_narrative` and everything above is untouched: the
# breaker calls DOWN into this module, never the reverse, so nothing here may
# import `trade_breaker`, read a flag, or read a knob.

#: Template version — stamped by `trade_breaker.compose_narration` into
#: `breaker.tmpl_ver`. **Bump on ANY wording change** (including whitespace and
#: punctuation): the narration A/B readouts key on `(ver, tmpl_ver)`, so a
#: silent reword would pool two different copies into one arm.
#: `test_hesitation_templates_snapshot` fails on a reword without a bump.
#: (The pre-first-ship `roster_crunch` singular split kept "brt-1": no stamp has
#: ever been written, so no readout can be pooling two copies.)
HESITATION_TMPL_VERSION = "brt-1"

#: The fixed lead-in label. It lives INSIDE the sentence (LLD §1.6 template
#: table), not in the mobile element — LLD §1.8 renders `data.breaker.sentence`
#: bare, so the client contributes no copy of its own.
HESITATION_LEAD_IN = "Their likely hesitation:"

#: Codes that are scored for calibration but may NEVER render a sentence.
#: `other_player_keep` is permanently dark in v1 (D-6): it would advertise that
#: we read the partner's private untouchable list. `hesitation_line` returns
#: None for it unconditionally — it simply has no template.
HESITATION_DARK_CODES = frozenset({"other_player_keep"})

#: template key → exact v1 wording (LLD §1.6). Keys are `code` or
#: `code.branch`; `_hesitation_template_key` maps an objection onto one.
HESITATION_TEMPLATES: dict[str, str] = {
    "fit_outlook.rebuild": (
        "Their likely hesitation: their roster leans rebuild, and this sends "
        "them {name}, a {age}-year-old {pos}."
    ),
    "fit_outlook.win_now": (
        "Their likely hesitation: they look win-now, and this asks them to "
        "take back future capital."
    ),
    "fit_new_weakness": (
        "Their likely hesitation: giving up {name} may leave them thin at "
        "{pos}."
    ),
    "fit_duplicate": (
        "Their likely hesitation: they're already deep at {pos}, so {name} "
        "may not move their lineup."
    ),
    "value_giving": (
        "Their likely hesitation: by consensus value they'd likely see this "
        "as giving up more than they get."
    ),
    # `.one` is the singular branch: "1 more players" is ungrammatical and
    # 1-for-2 is the commonest crunch. Selected by the same branch-discriminator
    # pattern as `fit_outlook` — the count still comes from evidence, it just
    # picks the template instead of filling a slot.
    "roster_crunch.one": (
        "Their likely hesitation: taking back 1 more player than they send "
        "is a roster squeeze."
    ),
    "roster_crunch": (
        "Their likely hesitation: taking back {extra} more players than they "
        "send is a roster squeeze."
    ),
}

#: template key → the evidence-derived fields it interpolates, in order.
#: A template with an empty tuple renders no evidence at all and is therefore
#: immune to null evidence (LLD §1.6).
HESITATION_TEMPLATE_FIELDS: dict[str, tuple[str, ...]] = {
    "fit_outlook.rebuild":  ("name", "age", "pos"),
    "fit_outlook.win_now":  (),
    "fit_new_weakness":     ("name", "pos"),
    "fit_duplicate":        ("pos", "name"),
    "value_giving":         (),
    "roster_crunch.one":    (),
    "roster_crunch":        ("extra",),
}


def _hesitation_int(value) -> Optional[str]:
    """Render an integral evidence value, or None when it is missing, null,
    or not a number. `bool` is rejected on purpose — `True` is an `int`."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and value != value:      # NaN
        return None
    return str(int(value))


def _hesitation_enum(value) -> Optional[str]:
    """Render an enum evidence value (a position). Empty ⇒ missing."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _hesitation_name(evidence: dict, players: dict) -> Optional[str]:
    """Resolve a player NAME from the objection's own `asset` id — the D-053
    mechanism. The template never contains a name; it contains an id slot that
    only the analysis can fill. A null id, an id `players` doesn't know, or a
    player with no name ⇒ None (no sentence, rather than a guess)."""
    pid = evidence.get("asset")
    if pid is None:
        return None
    name = _player_name(pid, players if isinstance(players, dict) else {})
    if not isinstance(name, str) or not name.strip():
        return None
    return name


def _hesitation_template_key(code, evidence: dict) -> Optional[str]:
    """Pick the template for one objection, or None when the class is unknown,
    permanently dark, or its branch discriminator is missing/null."""
    if code == "fit_outlook":
        outlook = evidence.get("outlook")
        if outlook in ("rebuilder", "jets"):
            return "fit_outlook.rebuild"
        if outlook in ("contender", "championship"):
            return "fit_outlook.win_now"
        return None                     # not_sure / null ⇒ no window claim
    if code == "value_giving":
        # Board-basis rows stamp for calibration but are ineligible outright
        # (D-7): a sentence built on the partner's own private board would
        # advertise that we read it. Only the consensus basis has copy.
        return "value_giving" if evidence.get("basis") == "consensus" else None
    if code == "roster_crunch":
        # Singular only when the evidence itself says exactly one extra body;
        # a missing/null/non-numeric `extra` falls to the plural template,
        # whose `{extra}` slot then refuses to render (⇒ None). The count is
        # never assumed.
        return ("roster_crunch.one"
                if _hesitation_int(evidence.get("extra")) == "1"
                else "roster_crunch")
    if code in ("fit_new_weakness", "fit_duplicate"):
        return code                     # single-template, unbranched classes
    return None                         # unknown or dark code


def hesitation_line(objection: dict, players: dict) -> Optional[str]:
    """One deterministic hesitation sentence for one objection, or None.

    D-053 mechanically: renders ONLY ids/numbers/enums present in
    `objection["evidence"]` (LLD §2.4 enumerates the keys per code); player
    names resolve from evidence ids via `players` at render time — the sentence
    can never name what the analysis didn't produce. Returns None on an unknown
    code, a non-narratable code, or any missing evidence key the template
    renders — and a present-but-NULL value in such a key counts as missing
    (a null `age` must return None, never render "None-year-old"; never
    guesses, never substitutes; a template that renders no evidence fields is
    unaffected by nulls). Raises nothing (any internal error → None; the caller
    stamps suppressed="template_error", LLD §5.5 E-15). Pure; no flag reads, no
    knob reads — eligibility lives in trade_breaker.compose_narration, the flag
    at the server seam. Inherits the positional-honesty covenant
    (trade_narrative.py:119-126).
    """
    try:
        if not isinstance(objection, dict):
            return None
        evidence = objection.get("evidence")
        if not isinstance(evidence, dict):
            return None

        key = _hesitation_template_key(objection.get("code"), evidence)
        if key is None:
            return None

        values: dict[str, str] = {}
        for field in HESITATION_TEMPLATE_FIELDS[key]:
            if field == "name":
                rendered = _hesitation_name(evidence, players)
            elif field == "pos":
                rendered = _hesitation_enum(evidence.get("pos"))
            elif field in ("age", "extra"):
                rendered = _hesitation_int(evidence.get(field))
            else:                                    # unreachable by table
                rendered = None
            if rendered is None:
                return None                          # honest silence
            values[field] = rendered

        return HESITATION_TEMPLATES[key].format(**values)
    except Exception:
        return None
