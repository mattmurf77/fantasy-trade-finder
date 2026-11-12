"""Deterministic, template-based trade rationale narratives.

No LLM calls. Pure function over signals already computed by the trade
engine — keeps cost at zero and output predictable for snapshot tests.

Used by trade_service.generate_trades() to populate TradeCard.narrative.
"""
from __future__ import annotations

from bisect import bisect_right
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


# ─────────────── fit block, version 3 (flag trade.fit_first_copy) ───────────────
# docs/plans/offer-learnings/scope-fit-block-v3.md (WS4b). Replaces WS4's one
# optional line per side (`fit_lines`, scope-fit-first-copy.md). Per team, the
# other team first: an outlook tag, one short lead phrase naming the strongest
# reason (or only what moves), and the team's league rank at every position the
# trade moves, before and after. Read from the bilateral generator's frozen
# proof (`card.owner_evaluation.as_dict()`) plus `FitLeagueContext`, the
# league-wide consensus position values captured once per trade job. No new
# proof field. `build_narrative` and the hesitation surface above are
# untouched; nothing here reads a flag or a knob (the flag lives at the server
# seam).
#
# Privacy: the other team's block uses only what the app already shows a viewer
# about a league-mate: rosters, consensus values, ages, consensus position
# ranks (League rankings) and the engine's roster read of their window (Team
# Review's partners beat). It reads exactly two things from the counterparty
# side of the proof, `usable_depth_before` and `usable_depth_delta` (a
# market-value proxy), and never their personal board, benefits, intent,
# preferences or their outlook as the proof records it (which is their
# DECLARED setting when they have one).

#: The payload's `v`. Installed apps (TestFlight 1.22.0 (184) on) show the block
#: only when it is exactly this (mobile/src/api/trades.ts), so it names the
#: payload SHAPE: a wording change keeps it, a shape change needs a new value
#: and an app that reads it.
FIT_TMPL_VERSION = "fit-2"

#: Need: the receiving side's usable-depth proxy at the named position rises
#: by at least this share of its value before the trade.
FIT_NEED_MIN_LIFT = 0.10
#: Need: the gain must also exceed the backup credit the proxy gives the named
#: player (trade_gen_owner._lineup counts one backup per position at 15%), so a
#: phrase is only written when he moves into the counted starters.
_FIT_BACKUP_SHARE = 0.15
#: Win-now asset: `trade_service._now_lean(pos, age)` at least this.
FIT_WIN_NOW_MIN_LEAN = 0.05
#: Other team's plan: their market-weighted now-lean shift must reach this in
#: the plan's direction (the same ±0.05 band as `_opponent_frame`).
FIT_THEIR_PLAN_MIN_SHIFT = 0.05
#: Rank noise bar: a position's consensus value must change by at least this
#: share of the league median at that position (server._position_medians) for
#: its rank move to show. A starting value to grade, not a measured one.
FIT_RANK_MIN_MOVE = 0.05
#: Fewer valued teams than this: no ranks at all (Home's MIN_SPLIT_TEAMS).
FIT_RANK_MIN_TEAMS = 3

_FIT_REBUILD = ("rebuilder", "jets")
_FIT_WIN_NOW = ("contender", "championship")
_FIT_DEPTH_POSITIONS = ("QB", "RB", "WR", "TE")
#: The viewer's plan benefit as each bilateral revision names it.
_FIT_PLAN_BENEFITS = ("outlook", "future_pick_capital")
_FIT_ARM = "owner_v2_bilateral"

FIT_TEMPLATES: dict[str, str] = {
    # `.you` = the viewer DECLARED this window; `.you_roster` / `.them` = the
    # engine's roster read, so the phrase says "-leaning" instead of a plan.
    "plan_rebuild.you":        "Rebuilding: adds {asset}",
    "plan_rebuild.you_roster": "Rebuild-leaning: adds {asset}",
    "plan_rebuild.them":       "Rebuild-leaning: adds {asset}",
    "plan_win_now.you":        "Win-now: adds {asset}",
    "plan_win_now.you_roster": "Win-now-leaning: adds {asset}",
    "plan_win_now.them":       "Win-now-leaning: adds {asset}",
    "need.you":                "Upgrades {pos}: adds {name}",
    "need.them":               "Upgrades {pos}: adds {name}",
    # No supported gain: no praise and no restating the card. What the trade
    # does to the team's league rank at the positions it touches instead.
    # `holds`: ranks that do not move ("RB stays 4th, WR stays 9th"); the moves
    # are the rank row beneath. `shifts`: every touched rank moves ("Up at
    # RB, down at WR"). `flat`: the value changes are under the noise bar.
    # `none`: no ranked position is touched (picks only).
    "holds.you":               "{ranks}",
    "holds.them":              "{ranks}",
    "shifts.you":              "{shift}",
    "shifts.them":             "{shift}",
    "flat.you":                "Little change in league rank",
    "flat.them":               "Little change in league rank",
    "none.you":                "No league rank change",
    "none.them":               "No league rank change",
}

#: Outlook tag words. `declared`: the app's display name for a declared
#: outlook (mobile OutlookBiasReceipt.tsx OUTLOOK_DISPLAY_NAME). `roster`:
#: Team Review's words for a league-mate's inferred window (partners beat,
#: "Rebuilding teams" / "Contending teams"), marked "Looks", the deck receipt's
#: wording for an inferred outlook ("you look" rather than "you're"). The
#: roster read never infers the extremes, and `not_sure` gets no tag (Team
#: Review drops a read that declined to commit). `projection`: a league-mate's
#: assumed outlook taken from their playoff chance in the saved forecast
#: (trade.partner_outlook_projection); same words as `roster`, since installed
#: builds print the text verbatim, and never the extremes.
FIT_TAGS: dict[str, dict[str, str]] = {
    "declared": {"championship": "All-in", "contender": "Contending",
                 "rebuilder": "Rebuilding", "jets": "Tanking"},
    "roster":   {"contender": "Looks contending", "rebuilder": "Looks rebuilding"},
    "projection": {"contender": "Looks contending", "rebuilder": "Looks rebuilding"},
}


class FitLeagueContext:
    """League-wide inputs for the fit block, captured once per trade job and
    shared (by reference) by every card the job builds.

    `teams` is `power_rankings.compute_power_rankings` on the consensus basis
    (the numbers League rankings, Home and Team Review show); `medians` is
    `server._position_medians(teams)`; `rosters` maps each team id to its
    non-pick player ids (to check a card's assets sit where the card says);
    `reads` maps each team id to the engine's roster read of its window;
    `sources` names the teams whose read came from the saved forecast
    (`projection`), every other read being the roster read.
    `position_ranks` is the job's `trade.fit_position_ranks` (read once per
    job): False ⇒ the block states no league rank (no `ranks`, `positions`
    or rank-fact lead), and the job passes no teams (it skips the walk).
    Immutable once built: copies return the same object.
    """
    __slots__ = ("viewer_id", "values", "medians", "player_value", "owner",
                 "valued", "reads", "ranked", "sources", "position_ranks")

    def __init__(self, *, viewer_id: str, teams: list, medians: dict,
                 rosters: dict, reads: dict, sources: dict | None = None,
                 position_ranks: bool = True):
        self.viewer_id = viewer_id
        self.position_ranks = position_ranks is True
        self.values = {t["user_id"]: {p: float(t["positions"][p]["value"])
                                      for p in _FIT_DEPTH_POSITIONS} for t in teams}
        # Every team's value per position, ascending: a card's rank is then a
        # binary search, not a walk over the league.
        self.ranked = {p: sorted(v[p] for v in self.values.values())
                       for p in _FIT_DEPTH_POSITIONS}
        self.medians = {p: float((medians.get(p) or {}).get("value") or 0.0)
                        for p in _FIT_DEPTH_POSITIONS}
        self.player_value = {r["player_id"]: (r["position"], float(r["value"]))
                             for t in teams for r in t["roster"]}
        self.owner = {pid: uid for uid, ids in rosters.items() for pid in ids}
        self.valued = sum(1 for t in teams if t["positions_value"] > 0)
        self.reads = dict(reads)
        self.sources = dict(sources or {})

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def _fit_finite(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value == value and value not in (float("inf"), float("-inf")))


def _fit_text(value) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def _fit_asset(pid, players: dict) -> Optional[dict]:
    """Public facts about one asset, or None when it cannot be described."""
    from .trade_service import is_pick_asset   # lazy: avoids circular import
    player = players.get(pid)
    name = _fit_text(getattr(player, "name", None))
    if player is None or name is None:
        return None
    if is_pick_asset(player):
        return {"id": pid, "name": name, "pos": "PICK", "age": None}
    pos, age = getattr(player, "position", None), getattr(player, "age", None)
    return {"id": pid, "name": name, "pos": pos if isinstance(pos, str) else None,
            "age": int(age) if _fit_finite(age) and age > 0 else None}


def _fit_describe(asset: dict) -> Optional[str]:
    if asset["pos"] == "PICK":
        return f"the {asset['name']}"
    if asset["age"] is None or not asset["pos"]:
        return None
    return f"{asset['name']}, {asset['age']}"


def _fit_lean(asset: dict) -> Optional[float]:
    from .trade_service import _now_lean   # lazy: avoids circular import
    if asset["pos"] == "PICK":
        return _now_lean("PICK", None)
    if asset["age"] is None:
        return None
    return _now_lean(asset["pos"], asset["age"])


def _fit_plan(side: str, team: dict, incoming: list, outgoing: list,
              market: dict, season_usable: bool = False,
              season_rows: Optional[dict] = None) -> Optional[tuple[str, dict]]:
    outlook = team.get("outlook")
    if outlook not in _FIT_REBUILD + _FIT_WIN_NOW:
        return None
    if season_usable and outlook in _FIT_WIN_NOW:
        # Copy rule 1 (PRD §6): with a usable forecast "Win-now" is said only
        # when the season facts support it (`_season_lead`), never from age.
        return None
    if side == "you":
        benefits = team.get("benefits")
        if not isinstance(benefits, list) or not set(benefits) & set(_FIT_PLAN_BENEFITS):
            return None
    else:
        # `team` is the public view (the roster read). The plan must also show
        # in the public shape of the trade, as in WS4.
        shift = gross = 0.0
        for sign, assets in ((1, incoming), (-1, outgoing)):
            for asset in assets:
                lean = _fit_lean(asset)
                if lean is None:
                    return None
                shift += sign * market[asset["id"]] * lean
                gross += market[asset["id"]]
        shift /= gross
        if (shift > -FIT_THEIR_PLAN_MIN_SHIFT if outlook in _FIT_REBUILD
                else shift < FIT_THEIR_PLAN_MIN_SHIFT):
            return None
    from .trade_gen_bilateral import _YOUNG   # the generator's own youth bands
    if outlook in _FIT_REBUILD:
        # Picks, or young non-RB players: the assets the bilateral plan scores
        # as clearly positive for a rebuild (a young RB scores near zero).
        fits = [a for a in incoming if a["pos"] == "PICK" or (
            a["pos"] in ("QB", "WR", "TE") and a["age"] is not None
            and a["age"] <= _YOUNG[a["pos"]])]
        key = "plan_rebuild"
    else:
        fits = [a for a in incoming if a["pos"] in _FIT_DEPTH_POSITIONS
                and (_fit_lean(a) or 0.0) >= FIT_WIN_NOW_MIN_LEAN]
        key = "plan_win_now"
    variant = side
    if side == "you" and team.get("outlook_source") != "declared":
        variant = "you_roster"
    for asset in sorted(fits, key=lambda a: (-market[a["id"]], a["id"])):
        described = _fit_describe(asset)
        if described:
            if (season_rows is not None and key == "plan_win_now"
                    and (season_rows.get(asset["id"]) or {}).get("label") not in SEASON_WIN_NOW_LABELS):
                # A season-scored viewer's card: the other team's win-now lead
                # stands only for an asset the engine labelled win-now or cornerstone.
                return None
            return f"{key}.{variant}", {"asset": described}
    return None


def _fit_depth(team: dict) -> Optional[tuple[dict, dict]]:
    before, delta = team.get("usable_depth_before"), team.get("usable_depth_delta")
    if not isinstance(before, dict) or not isinstance(delta, dict):
        return None
    if not all(_fit_finite(before.get(p)) and _fit_finite(delta.get(p))
               for p in _FIT_DEPTH_POSITIONS):
        return None
    return before, delta


def _fit_need(side: str, team: dict, incoming: list,
              market: dict) -> Optional[tuple[str, dict]]:
    # A rebuilding or tanking team's lineup is not its goal (the generator
    # weights roster need at 0.05 and 0 for them), so no need phrase for one.
    depth = _fit_depth(team)
    if depth is None or team.get("outlook") in _FIT_REBUILD:
        return None
    from .trade_service import age_now_mult   # lazy: avoids circular import
    before, delta = depth
    best = None
    for pos in sorted({a["pos"] for a in incoming if a["pos"] in _FIT_DEPTH_POSITIONS}):
        top = max((a for a in incoming if a["pos"] == pos),
                  key=lambda a: (market[a["id"]], a["id"]))
        if top["age"] is None:
            continue
        gain = delta[pos]
        # More than a bench body: the proxy credits one backup at 15% of its
        # lineup value, so a gain at or under that is a backup, not an upgrade.
        backup = _FIT_BACKUP_SHARE * market[top["id"]] * age_now_mult(pos, top["age"])
        if gain <= backup or (before[pos] > 0 and gain < FIT_NEED_MIN_LIFT * before[pos]):
            continue
        lift = gain / before[pos] if before[pos] > 0 else float("inf")
        if best is None or lift > best[0]:
            best = (lift, pos, top["name"])
    if best is None:
        return None
    return f"need.{side}", {"pos": best[1], "name": best[2]}


#: What a tag's `source` reads on the wire. Installed app builds keep a tag
#: only when its source is `declared` or `roster` (mobile/src/api/trades.ts),
#: so a projection read is sent as `roster` ("assumed, not declared"); the
#: request evidence and the owner proof record the true source.
FIT_TAG_WIRE_SOURCE = {"projection": "roster"}


def _fit_tag(source: str, outlook) -> Optional[dict]:
    text = FIT_TAGS[source].get(outlook)
    wire = FIT_TAG_WIRE_SOURCE.get(source, source)
    return {"code": outlook, "source": wire, "text": text} if text else None


# ── Win-now season signal copy (bilateral revision 5) ───────────────────────
# docs/plans/win-now-season-signal/prd.md §3, §5.3, §6; lld.md §5.1-§5.2.
# Composed only from the proof's `season_signal` (trade_gen_bilateral_season):
# every label printed is the label the engine read there (I13), and a player
# with no projection gets no figure, label or claim (I11). With no usable
# evidence nothing here runs and the fit block is today's.

#: You-side leads for the fit block (installed builds print `lead.text`).
#: Kept apart from FIT_TEMPLATES so that table, and the fit-2 shape, stay as
#: they are.
SEASON_FIT_TEMPLATES: dict[str, str] = {
    "conflict.you":       "Away from {plan}: {pts} pts/wk",
    "conflict_plan.you":  "Away from {plan}: adds a win-now piece",
    "season_win_now.you": "Win-now: {name} starts, +{pts}/wk",
    "season_starter.you": "Starts for you: {name}, +{pts}/wk",
    # A Rebuilding / Tanking viewer's card that sheds lineup points for future value
    # (amended 2026-11-11). {plan}: the saved plan's name, or "Rebuild-leaning" for
    # a roster read; {asset}: the most valuable incoming rebuild piece, cornerstone or pick.
    "season_shed.you":    "{plan}: {pts} pts/wk, adds {asset}",
}
#: The season block's text (next app build).
SEASON_BLOCK_VERSION = "season-1"
SEASON_TEMPLATES: dict[str, str] = {
    "season":               "Season {pts} pts/wk",
    "season_flat":          "Season no change",
    "dynasty_cost":         "Dynasty cost {pct}%",
    "dynasty_gain":         "Dynasty gain {pct}%",
    "dynasty_even":         "Dynasty even",
    "conflict.board.above": "You rank {name} above market, but this moves away from {plan}",
    "conflict.board.below": "You rank {name} below market, but this moves away from {plan}",
    "conflict.target":      "{name} is on your target list, but this moves away from {plan}",
    "conflict.position":    "You asked for {pos}s, but this moves away from {plan}",
    "conflict.trade_block": "You marked {name} to move, but this moves away from {plan}",
    "conflict.trade_away":  "You are shopping {pos}s, but this moves away from {plan}",
}
#: Joins the season and dynasty halves of the line (PRD §3).
SEASON_LINE_SEPARATOR = " · "
#: Printed label tags. `depth` and no label print nothing.
SEASON_LABELS: dict[str, str] = {"win_now": "Win-now piece", "cornerstone": "Cornerstone",
                                 "rebuild": "Rebuild piece"}
#: What the shed lead names: an incoming asset with one of these labels, or a pick.
SEASON_FUTURE_LABELS = ("rebuild", "cornerstone")
#: The shed lead's plan word for a Rebuilding roster read with no saved plan.
SEASON_SHED_ROSTER = "Rebuild-leaning"
#: For a season-scored viewer, the other team's "Win-now-leaning: adds X" lead
#: is kept only when X carries one of these labels.
SEASON_WIN_NOW_LABELS = ("win_now", "cornerstone")
#: Inside this many points a week the season half reads "no change", and a
#: season lead needs at least this gain (copy rule 1).
SEASON_MIN_PTS = 0.5
#: Inside this share of roster value the dynasty half reads "even".
SEASON_EVEN_PCT = 0.5
#: One line in the app's fit block lead.
FIT_LEAD_MAX = 44


def _season_view(proof: dict) -> Optional[dict]:
    """The proof's season record when its evidence is usable, else None.
    Raises on a malformed usable record (the composers then yield None)."""
    signal = proof.get("season_signal")
    if not isinstance(signal, dict):
        return None
    evidence = signal.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("state") != "usable":
        return None
    viewer, conflict = signal["viewer"], signal["conflict"]
    scored = viewer["scored"] is True
    delta = viewer["delta_pts_week"] if scored else None
    if scored and not _fit_finite(delta):
        raise ValueError("delta_pts_week")
    # The direction the engine scored the viewer in, as the proof states it: never
    # inferred from the outlook ("add": All-in / Contending; "shed": Rebuilding / Tanking).
    direction = viewer.get("season_direction") if scored else None
    if scored and direction not in ("add", "shed"):
        raise ValueError("season_direction")
    rows = {row["id"]: row for row in signal["assets"]}
    return {"scored": scored, "delta": delta, "direction": direction, "assets": rows, "evidence": evidence,
            "dynasty": viewer.get("dynasty_cost_pct"), "outlook": viewer.get("outlook"),
            "declared": viewer.get("outlook_source") == "declared",
            # A saved Rebuilding or Tanking plan: the one unscored viewer the
            # season copy speaks to (labels, the mirror conflict).
            "mirror": (not scored and viewer.get("outlook") in _FIT_REBUILD
                       and viewer.get("outlook_source") == "declared"),
            "conflict": conflict if conflict.get("fired") is True else None}


def _season_projected(row: Optional[dict]) -> bool:
    return isinstance(row, dict) and _fit_finite(row.get("ppg"))


def _season_short(name: str) -> str:
    """First initial and the rest ("J. Croskey-Merritt"), used only when the
    full name would push a lead past one line."""
    first, _, rest = name.partition(" ")
    return f"{first[0]}. {rest}" if rest else name


def _season_lead(season: dict, incoming: list, market: dict) -> Optional[tuple[str, dict]]:
    """The You lead from the season record (copy rule 2), or None for today's."""
    conflict = season["conflict"]
    if conflict:
        plan = FIT_TAGS["declared"][conflict["plan"]]
        if conflict["plan"] in _FIT_REBUILD and conflict.get("trigger") != "points":
            return "conflict_plan.you", {"plan": plan}
        if season["delta"] is None:
            raise ValueError("conflict without a season delta")
        return "conflict.you", {"plan": plan, "pts": f"{season['delta']:+.1f}"}
    if not season["scored"]:
        return None
    if season["direction"] == "shed":
        return _season_shed_lead(season, incoming, market)
    if season["delta"] < SEASON_MIN_PTS:
        return None
    rows = season["assets"]
    starters = [a for a in incoming if a["pos"] in _FIT_DEPTH_POSITIONS
                and _season_projected(rows.get(a["id"]))
                and rows[a["id"]].get("starts_for_viewer") is True]
    starters.sort(key=lambda a: (-(rows[a["id"]].get("gain_for_viewer") or 0.0),
                                 -market[a["id"]], a["id"]))
    pts = f"{season['delta']:.1f}"
    for code, wanted in (("season_win_now.you", True), ("season_starter.you", False)):
        for asset in starters:
            if (rows[asset["id"]].get("label") == "win_now") is not wanted:
                continue
            for name in (asset["name"], _season_short(asset["name"])):
                values = {"name": name, "pts": pts}
                if len(SEASON_FIT_TEMPLATES[code].format(**values)) <= FIT_LEAD_MAX:
                    return code, values
    return None


def _season_shed_lead(season: dict, incoming: list, market: dict) -> Optional[tuple[str, dict]]:
    """A shed-scored viewer's lead for a card that gives up at least SEASON_MIN_PTS a week
    of lineup points and brings back future value, or None for today's lead. Names the
    most valuable incoming pick or projected rebuild piece / cornerstone, as labelled."""
    if season["delta"] > -SEASON_MIN_PTS:
        return None
    rows = season["assets"]
    future = [a for a in incoming if a["pos"] == "PICK" or (
        a["pos"] in _FIT_DEPTH_POSITIONS and _season_projected(rows.get(a["id"]))
        and rows[a["id"]].get("label") in SEASON_FUTURE_LABELS)]
    if not future:
        return None
    top = max(future, key=lambda a: (market[a["id"]], a["id"]))
    plan = (FIT_TAGS["declared"][season["outlook"]] if season["declared"] else SEASON_SHED_ROSTER)
    names = ([f"the {top['name']}"] if top["pos"] == "PICK"
             else [top["name"], _season_short(top["name"])])
    for asset in names:
        values = {"plan": plan, "pts": f"{season['delta']:+.1f}", "asset": asset}
        if len(SEASON_FIT_TEMPLATES["season_shed.you"].format(**values)) <= FIT_LEAD_MAX:
            return "season_shed.you", values
    return None


def _fit_ordinal(n: int) -> str:
    """A league rank as the app writes it (TradeCard.tsx fitRankOrdinal)."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _fit_rank_fallback(side: str, moves: list, held: list,
                       touched: bool) -> tuple[str, dict]:
    """The lead for a team with no supported reason: rank facts, never the
    card's own player list."""
    if held:
        return f"holds.{side}", {"ranks": ", ".join(
            f"{h['pos']} stays {_fit_ordinal(h['rank'])}" for h in held)}
    if moves:
        order = sorted(moves, key=lambda m: _FIT_DEPTH_POSITIONS.index(m["pos"]))
        parts = [f"{word} at {' and '.join(m['pos'] for m in group)}"
                 for word, group in (
                     ("up", [m for m in order if m["after"] < m["before"]]),
                     ("down", [m for m in order if m["after"] > m["before"]]))
                 if group]
        text = ", ".join(parts)
        return f"shifts.{side}", {"shift": text[0].upper() + text[1:]}
    return f"{'flat' if touched else 'none'}.{side}", {}


def _fit_rank_rows(context: FitLeagueContext, other_id, give: list, receive: list,
                   assets: dict) -> Optional[dict]:
    """Per team ("them", "you"): `moves` (league rank moves, the payload's
    `ranks`), `held` (touched positions whose rank does not move), `all`
    (every touched position's true before and after, noise-level moves
    included, in QB, RB, WR, TE order) and `touched` (the trade moves a
    ranked position at all). None when no rank
    can be stated (too few valued teams, or a team or an asset the context
    does not place where the card does)."""
    you, them = context.viewer_id, other_id
    if (context.valued < FIT_RANK_MIN_TEAMS or you not in context.values
            or them not in context.values or you == them):
        return None
    after = {you: dict(context.values[you]), them: dict(context.values[them])}
    touched = {you: set(), them: set()}
    for ids, src, dst in ((give, you, them), (receive, them, you)):
        for pid in ids:
            if assets[pid]["pos"] == "PICK":
                continue                        # a pick has no position rank
            if context.owner.get(pid) != src:
                return None                     # the context disagrees with the card
            pos, value = context.player_value.get(pid, (None, 0.0))
            if pos not in _FIT_DEPTH_POSITIONS:
                continue
            after[src][pos] -= value
            after[dst][pos] += value
            touched[src].add(pos)
            touched[dst].add(pos)
    for uid in after:
        # A team's position value is a sum of 0.1-rounded player values,
        # rounded to 0.1 (compute_power_rankings); stay on the same grid.
        after[uid] = {p: round(v, 1) for p, v in after[uid].items()}
    def above(pos, value):
        """Teams strictly above `value` at `pos` before the trade."""
        ranked = context.ranked[pos]
        return len(ranked) - bisect_right(ranked, value)

    rows = {}
    for side, uid in (("them", them), ("you", you)):
        moves, held, every = [], [], []
        for pos in _FIT_DEPTH_POSITIONS:
            if pos not in touched[uid]:
                continue
            was, now = context.values[uid][pos], after[uid][pos]
            # Ties share a rank: 1 + the teams strictly above (League rankings).
            # After the trade only the two teams' values differ, so swap their
            # before values for their after values in the count.
            before = 1 + above(pos, was)
            later = 1 + above(pos, now) + sum(
                (after[t][pos] > now) - (context.values[t][pos] > now) for t in after)
            every.append({"pos": pos, "before": before, "after": later})
            if before == later:
                held.append({"pos": pos, "rank": before})
            elif abs(now - was) >= FIT_RANK_MIN_MOVE * context.medians[pos]:
                moves.append({"pos": pos, "before": before, "after": later})
            # else: a rank move on a value change under the noise bar is
            # neither shown as a move nor called unchanged.
        # Gains first, larger moves first, then position order.
        moves.sort(key=lambda m: (m["after"] > m["before"], -abs(m["after"] - m["before"]),
                                  _FIT_DEPTH_POSITIONS.index(m["pos"])))
        rows[side] = {"moves": moves, "held": held, "all": every,
                      "touched": bool(touched[uid])}
    return rows


def _fit_positions(row: Optional[dict]) -> list:
    """The app's before/after table for one team: every ranked position the
    trade touches, with its true rank before and after, in QB, RB, WR, TE
    order. That includes a rank move under the noise bar, which is in neither
    `moves` nor `held` (operator, 2026-11-11: "We should just show it").
    Empty when no rank can be stated (`row` is None)."""
    return [dict(p) for p in row["all"]] if row else []


def fit_block(proof: dict, card, players: dict, context) -> Optional[dict]:
    """The version-3 fit block for one bilateral card, or None (today's card:
    the caller adds nothing).

    `proof` is `card.owner_evaluation.as_dict()`, already matched to `card`;
    `context` is the job's `FitLeagueContext`. Returned only when at least
    one team has a supported lead (plan, then need) or a rank move; a team
    without a supported lead gets a rank fact (`_fit_rank_fallback`), never
    the card's player list, and is left out when no rank can be stated for
    it. With `context.position_ranks` False (flag trade.fit_position_ranks
    off) no rank is stated at all: every team carries `ranks: []` and
    `positions: []`, a team without a supported lead is left out (its tag
    with it: installed apps drop a team with no lead), and the block is
    returned only when some team has a supported lead. Pure; raises nothing
    (any malformed input yields None).
    """
    try:
        if (not isinstance(proof, dict) or proof.get("generator") != _FIT_ARM
                or proof.get("eligible") is not True
                or not isinstance(context, FitLeagueContext)):
            return None
        give, receive = list(card.give_player_ids), list(card.receive_player_ids)
        market = {}
        for row in proof.get("assets") or ():
            if isinstance(row, dict) and _fit_finite(row.get("market")) and row["market"] > 0:
                market[row.get("id")] = row["market"]
        if not give or not receive or set(market) != set(give + receive):
            return None
        assets = {pid: _fit_asset(pid, players if isinstance(players, dict) else {})
                  for pid in give + receive}
        if any(a is None for a in assets.values()):
            return None
        other = card.target_user_id
        season = _season_view(proof)
        if season is not None and set(season["assets"]) != set(give + receive):
            return None
        ranks = (_fit_rank_rows(context, other, give, receive, assets)
                 if context.position_ranks else None)
        teams, shown = [], False
        for side, incoming, outgoing in (("them", give, receive), ("you", receive, give)):
            inc = [assets[p] for p in incoming]
            out = [assets[p] for p in outgoing]
            if side == "them":
                counterparty = proof.get("counterparty")
                counterparty = counterparty if isinstance(counterparty, dict) else {}
                read = context.reads.get(other)
                # The public view: the roster read in place of whatever outlook
                # the proof holds, and nothing else of theirs but the depth proxy.
                view = {"outlook": read, "outlook_source": "inferred",
                        "usable_depth_before": counterparty.get("usable_depth_before"),
                        "usable_depth_delta": counterparty.get("usable_depth_delta")}
                tag = _fit_tag(context.sources.get(other, "roster"), read)
            else:
                view = proof.get("viewer")
                view = view if isinstance(view, dict) else {}
                tag = _fit_tag("declared" if view.get("outlook_source") == "declared"
                               else "roster", view.get("outlook"))
            if season is None or not season["scored"]:
                # A viewer the season does not score: today's copy on both sides.
                # Only a saved Rebuilding / Tanking plan's fired mirror conflict
                # takes the You lead ("Away from Rebuilding: adds a win-now piece").
                mirror = (side == "you" and season is not None and season["mirror"]
                          and season["conflict"] is not None)
                chosen = ((_season_lead(season, inc, market) if mirror else None)
                          or _fit_plan(side, view, inc, out, market)
                          or _fit_need(side, view, inc, market))
            elif side == "you":
                # A season-scored viewer: the season lead first, never the
                # age-based win-now lead or the dynasty-value need phrase.
                chosen = (_season_lead(season, inc, market)
                          or _fit_plan(side, view, inc, out, market, season_usable=True))
            else:
                chosen = (_fit_plan(side, view, inc, out, market, season_rows=season["assets"])
                          or _fit_need(side, view, inc, market))
            row = ranks[side] if ranks else None
            if chosen:
                shown = True
                code, values = chosen
            elif row is None:
                continue               # nothing true to say for this team
            else:
                code, values = _fit_rank_fallback(side, row["moves"], row["held"],
                                                  row["touched"])
            moves = row["moves"] if row else []
            template = FIT_TEMPLATES.get(code) or SEASON_FIT_TEMPLATES[code]
            entry = {"side": side, "lead": {"code": code, "text": template.format(**values)},
                     "ranks": moves,
                     "positions": _fit_positions(row)}
            if tag:
                entry["tag"] = tag
            shown = shown or bool(moves)
            teams.append(entry)
        return {"v": FIT_TMPL_VERSION, "teams": teams} if shown else None
    except Exception:
        return None


def _season_conflict(conflict: dict, assets: dict, give: list, receive: list) -> dict:
    """The conflict sentence (PRD §5.3), naming `conflict.named`: the asset
    whose ranking qualified the card (`board`), or the asset the viewer's
    declaration is about (incoming for `target` / `position`, outgoing for
    `trade_block` / `trade_away`). Raises when the named asset is not on the
    side its kind requires."""
    plan = FIT_TAGS["declared"][conflict["plan"]]
    named = assets[conflict["named"]]
    name = f"the {named['name']}" if named["pos"] == "PICK" else named["name"]
    kind = conflict["kind"]
    if kind == "board":
        code = ("conflict.board.above" if named["id"] in receive
                else "conflict.board.below" if named["id"] in give else None)
    elif kind in ("target", "position"):
        code = f"conflict.{kind}" if named["id"] in receive else None
    elif kind in ("trade_block", "trade_away"):
        code = f"conflict.{kind}" if named["id"] in give else None
    else:
        code = None
    if code is None:
        raise ValueError("conflict")
    return {"code": code, "text": SEASON_TEMPLATES[code].format(
        name=name, pos=named["pos"], plan=plan)}


def season_block(proof: dict, card, players: dict) -> Optional[dict]:
    """The season block for one revision 5 card (lld §5.2), or None.

    None unless the proof's season evidence is usable, the viewer is
    season-scored or holds a saved Rebuilding / Tanking plan (never for Not
    sure), and there is something to show. `line` (with `season_pts_week`,
    `dynasty_pct`, `dynasty_dir`) only for a season-scored viewer, in either
    direction (All-in, Contending; Rebuilding, Tanking); `labels` only for
    projected players whose engine label prints; `conflict` only when the
    plan-conflict rule fired. Pure; raises nothing (malformed input: None).
    """
    try:
        if (not isinstance(proof, dict) or proof.get("generator") != _FIT_ARM
                or proof.get("eligible") is not True):
            return None
        season = _season_view(proof)
        if season is None:
            return None
        give, receive = list(card.give_player_ids), list(card.receive_player_ids)
        if not give or not receive or set(season["assets"]) != set(give + receive):
            return None
        assets = {pid: _fit_asset(pid, players if isinstance(players, dict) else {})
                  for pid in give + receive}
        if any(a is None for a in assets.values()):
            return None
        if not (season["scored"] or season["mirror"]):
            return None                  # Not sure, or no saved plan: today's card
        block = {"v": SEASON_BLOCK_VERSION}
        if season["scored"]:
            delta, cost = season["delta"], season["dynasty"]
            if not _fit_finite(cost):
                return None
            if abs(delta) < SEASON_MIN_PTS:
                first = SEASON_TEMPLATES["season_flat"]
            else:
                first = SEASON_TEMPLATES["season"].format(pts=f"{delta:+.1f}")
            pct = float(int(abs(cost) + 0.5))
            if abs(cost) < SEASON_EVEN_PCT:
                pct, direction = 0.0, "even"
                second = SEASON_TEMPLATES["dynasty_even"]
            else:
                direction = "cost" if cost > 0 else "gain"
                second = SEASON_TEMPLATES[f"dynasty_{direction}"].format(pct=f"{pct:.0f}")
            block.update(line=first + SEASON_LINE_SEPARATOR + second,
                         season_pts_week=round(delta, 1), dynasty_pct=pct, dynasty_dir=direction)
        evidence = season["evidence"]
        captured = evidence.get("captured_at")
        block.update(weeks=len(evidence["weeks"]),
                     as_of=captured[:10] if isinstance(captured, str) else None)
        labels = []
        for pid in receive + give:
            row = season["assets"][pid]
            text = SEASON_LABELS.get(row.get("label"))
            if text is None or assets[pid]["pos"] == "PICK" or not _season_projected(row):
                continue                 # no claim about a pick or an unprojected player
            labels.append({"id": pid, "label": row["label"], "text": text,
                           "starts_for_you": row.get("starts_for_viewer") is True})
        if labels:
            block["labels"] = labels
        if season["conflict"]:
            block["conflict"] = _season_conflict(season["conflict"], assets, give, receive)
        if not ({"line", "labels", "conflict"} & set(block)):
            return None
        return block
    except Exception:
        return None


# ── WS8 revised-offer cards (flag trade.next_move) ──────────────────────────
# One sentence on a card built because Sleeper showed the user's own offer
# declined (a revision) or showed the user declining the other manager's
# counter (a middle ground). It states what the platform showed and what
# changed, never a reason for the decline. Assets are named by the caller's
# `name(asset_id)` (player names, pick labels); the sentence sits above the
# fit lines and reads on its own beside them.

def _revised_names(ids, name) -> str:
    labels = [str(name(i) or "an asset") for i in ids]
    if len(labels) <= 1:
        return labels[0] if labels else "that trade"
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def revised_offer_line(kind: str, *, original_give, original_receive, give, receive,
                       name) -> str:
    """The card's first line, from the original offer and the card's terms.

    revision      "Your offer for {asked} was declined. Another idea: {new}
                   in place of {old}."
    middle_ground "You turned down their counter to your offer for {asked}.
                   A middle ground: {changes}."  changes, relative to the
                   user's original offer: "add X", "keep X" (no longer
                   offered), "also ask for X", "no longer ask for X".
    """
    asked = _revised_names(list(original_receive), name)
    if kind == "revision":
        old = [p for p in original_give if p not in give]
        new = [p for p in give if p not in original_give]
        return (f"Your offer for {asked} was declined. Another idea: "
                f"{_revised_names(new, name)} in place of {_revised_names(old, name)}.")
    parts = []
    for verb, ids in (("add", [p for p in give if p not in original_give]),
                      ("keep", [p for p in original_give if p not in give]),
                      ("also ask for", [p for p in receive if p not in original_receive]),
                      ("no longer ask for", [p for p in original_receive if p not in receive])):
        if ids:
            parts.append(f"{verb} {_revised_names(ids, name)}")
    changes = (", ".join(parts[:-1]) + " and " + parts[-1]) if len(parts) > 1 else parts[0]
    return (f"You turned down their counter to your offer for {asked}. "
            f"A middle ground: {changes}.")
